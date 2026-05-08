"""
GlobalNationsSubscription

Unfiltered WebSocket subscriptions for ALL nations in the game.
All data goes to a single GlobalNations.db — there is no separate NW DB.

Behaviour:
  - nation/update  → save to GlobalNationsDB (all nations)
  - nation/create  → same
  - account/update → patch last_active/discord_id
  - city/update    → upsert city in GlobalNationsDB
  - city/create    → same

NW membership is tracked in a local set (_nw_nation_ids) purely for
informational logging — it no longer controls any write routing.
"""

import asyncio
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

import aiohttp
from pnwkit.new import QueryKit

logger = logging.getLogger(__name__)

NW_ALLIANCE_ID  = 14225
IRS_ALLIANCE_ID = NW_ALLIANCE_ID   # backward-compat alias
EP_ALLIANCE_ID  = NW_ALLIANCE_ID   # backward-compat alias


def _obj_to_dict(obj: Any) -> Dict[str, Any]:
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return dict(obj)
    return vars(obj)


class GlobalNationsSubscription:
    def __init__(self, global_db, nw_db=None, api_key: str = "", holdings_db=None):
        """
        global_db   : GlobalNationsDB — single DB for ALL nations
        nw_db       : ignored (kept for call-site backward compatibility)
        api_key     : PnW API v3 key
        holdings_db : HoldingsDB — tracks per-nation cash/resource ledger
        """
        self.global_db   = global_db
        self.holdings_db = holdings_db
        self.api_key     = api_key
        self.kit         = QueryKit(api_key)
        self.running     = False
        self._tasks: list[asyncio.Task] = []

        # In-memory set of NW nation IDs — used only for logging, not write routing.
        self._nw_nation_ids: Set[int] = set()

    async def _seed_nw_set(self):
        """Seed the in-memory NW set from GlobalNations.db."""
        if not self.global_db:
            return
        try:
            async with self.global_db._lock:
                with sqlite3.connect(self.global_db.db_path) as conn:
                    rows = conn.execute(
                        "SELECT id FROM nations WHERE alliance_id = ?",
                        (NW_ALLIANCE_ID,),
                    ).fetchall()
                    self._nw_nation_ids = {r[0] for r in rows}
            logger.info(f"NW nation set seeded: {len(self._nw_nation_ids)} members in GlobalNations.db")
        except Exception as e:
            logger.error(f"Failed to seed NW nation set: {e}", exc_info=True)

    def _is_nw_by_alliance(self, nation: Dict[str, Any]) -> bool:
        return int(nation.get("alliance_id") or 0) == NW_ALLIANCE_ID

    def _is_nw_id(self, nation_id: int) -> bool:
        return nation_id in self._nw_nation_ids

    # ── Read helpers ──────────────────────────────────────────────────────────

    async def _get_existing_nation(self, nation_id: int) -> Optional[Dict[str, Any]]:
        if not self.global_db:
            return None
        try:
            return await self.global_db.get_nation(nation_id)
        except Exception as e:
            logger.debug(f"_get_existing_nation({nation_id}): {e}")
            return None

    async def _get_existing_city(self, city_id: int) -> Optional[Dict[str, Any]]:
        if not self.global_db:
            return None
        try:
            async with self.global_db._lock:
                with sqlite3.connect(self.global_db.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute(
                        "SELECT * FROM cities WHERE id = ?", (city_id,)
                    ).fetchone()
                    return dict(row) if row else None
        except Exception as e:
            logger.debug(f"_get_existing_city({city_id}): {e}")
            return None

    # ── Alliance extraction helper ────────────────────────────────────────────

    @staticmethod
    def _extract_alliance(nation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Flatten nested alliance object into top-level alliance_id / alliance_name /
        alliance_flag.  The nested object from the live subscription is authoritative
        and always overwrites the flat fields (not just when they're absent).
        """
        alliance_obj = nation.get("alliance") or {}
        if isinstance(alliance_obj, dict):
            # Always prefer the nested object — it's the freshest source
            if alliance_obj.get("id"):
                nation["alliance_id"] = alliance_obj["id"]
            if alliance_obj.get("name"):
                nation["alliance_name"] = alliance_obj["name"]
            if alliance_obj.get("flag"):
                nation["alliance_flag"] = alliance_obj["flag"]
        # PnW API returns '0' as alliance_name for nations with no alliance.
        # Treat it as None so it never overwrites a real name.
        if nation.get("alliance_name") == '0':
            nation["alliance_name"] = None
        return nation

    # ── Holdings spending detection ───────────────────────────────────────────

    async def _detect_and_record_nation_spending(
        self,
        nation_id: int,
        old_nation: Dict[str, Any],
        new_nation: Dict[str, Any],
        event_date: Optional[str] = None,
    ):
        """
        Compare old vs new nation snapshot to detect purchases and deduct
        the cost from holdings BEFORE the new snapshot is saved.

        Guards:
          - old_num_cities > 0: we must have a real prior city count baseline.
            If old is 0 this is a first-seen snapshot, not a purchase event.
          - old_turns_proj > 2 AND old_num_cities > 0: same baseline guard for projects.
          - Military: HoldingsDB.apply_military_update already guards with
            confidence != 'seeded' before deducting costs.
        """
        if not self.holdings_db:
            return

        from PnWHarvester.db.pnw_costs import (
            city_cost, projects_purchased_cost, projects_purchased_resource_costs,
        )

        nation_name = new_nation.get("nation_name") or old_nation.get("nation_name")
        ev_date = event_date or self._now_str()

        # ── City purchase detection ───────────────────────────────────────────
        old_turns_city = int(old_nation.get("turns_since_last_city") or 0)
        new_turns_city = int(new_nation.get("turns_since_last_city") or 0)
        old_num_cities = int(old_nation.get("num_cities") or 0)
        new_num_cities = int(new_nation.get("num_cities") or 0)

        # Guard: old_num_cities == 0 means no prior baseline — first-seen snapshot,
        # not a purchase. Never charge for cities we didn't know they had before.
        if old_num_cities > 0:
            cities_bought = max(0, new_num_cities - old_num_cities)
            # turns_since_last_city reset without city count updating yet in this payload
            if cities_bought == 0 and old_turns_city > 2 and new_turns_city == 0:
                cities_bought = 1

            if cities_bought > 0:
                total_city_cost = 0.0
                base_cities = old_num_cities
                for _ in range(cities_bought):
                    total_city_cost += city_cost(base_cities, nation_data=new_nation)
                    base_cities += 1
                if total_city_cost > 0:
                    await self.holdings_db.deduct_spending(
                        nation_id=nation_id,
                        cash_cost=total_city_cost,
                        event_type="city_purchase",
                        description=f"Bought {cities_bought} city/cities ({old_num_cities}→{new_num_cities})",
                        event_date=ev_date,
                        nation_name=nation_name,
                        item_type="city",
                        item_quantity=cities_bought,
                        item_details=f"Cities {old_num_cities}→{new_num_cities}",
                    )
                    logger.info(
                        f"Holdings: nation {nation_id} city purchase "
                        f"${total_city_cost:,.0f} ({old_num_cities}→{new_num_cities} cities)"
                    )
                    # ── News: city purchase ───────────────────────────────────
                    try:
                        import PnWHarvester.db.news_writer as _nw
                        asyncio.create_task(_nw.record_city_purchase(
                            nation_id=nation_id,
                            nation_name=nation_name,
                            nation_flag=new_nation.get("flag"),
                            alliance_id=int(new_nation.get("alliance_id") or 0) or None,
                            alliance_name=new_nation.get("alliance_name"),
                            alliance_flag=new_nation.get("alliance_flag"),
                            old_cities=old_num_cities,
                            new_cities=new_num_cities,
                            cash_cost=total_city_cost,
                            event_date=ev_date,
                        ))
                    except Exception as _ne:
                        logger.debug(f"news city_purchase: {_ne}")

        # ── Project purchase detection ────────────────────────────────────────
        old_turns_proj = int(old_nation.get("turns_since_last_project") or 0)
        new_turns_proj = int(new_nation.get("turns_since_last_project") or 0)

        # Guard: turns reset AND we had a real prior snapshot (old_num_cities > 0)
        if old_turns_proj > 2 and new_turns_proj == 0 and old_num_cities > 0:
            proj_cost = projects_purchased_cost(old_nation, new_nation)
            proj_rss  = projects_purchased_resource_costs(old_nation, new_nation)
            if proj_cost > 0 or proj_rss:
                await self.holdings_db.deduct_spending(
                    nation_id=nation_id,
                    cash_cost=proj_cost,
                    event_type="project_purchase",
                    description=f"Project(s) purchased (turns_proj {old_turns_proj}→{new_turns_proj})",
                    event_date=ev_date,
                    nation_name=nation_name,
                    item_type="project",
                    item_quantity=1,
                    item_details="Project purchase detected",
                    resource_costs=proj_rss if proj_rss else None,
                )
                rss_str = ", ".join(f"{r}={v:,.1f}" for r, v in proj_rss.items()) if proj_rss else ""
                logger.info(
                    f"Holdings: nation {nation_id} project purchase ${proj_cost:,.0f}"
                    + (f" + {rss_str}" if rss_str else "")
                )
                # ── News: project purchase ────────────────────────────────────
                try:
                    import PnWHarvester.db.news_writer as _nw
                    proj_names = _nw._detect_projects_purchased(old_nation, new_nation)
                    asyncio.create_task(_nw.record_project_purchase(
                        nation_id=nation_id,
                        nation_name=nation_name,
                        nation_flag=new_nation.get("flag"),
                        alliance_id=int(new_nation.get("alliance_id") or 0) or None,
                        alliance_name=new_nation.get("alliance_name"),
                        alliance_flag=new_nation.get("alliance_flag"),
                        project_names=proj_names,
                        cash_cost=proj_cost,
                        resource_costs=proj_rss if proj_rss else None,
                        event_date=ev_date,
                    ))
                except Exception as _ne:
                    logger.debug(f"news project_purchase: {_ne}")

        # ── Military unit tracking ────────────────────────────────────────────
        _MIL_KEYS = ("soldiers", "tanks", "aircraft", "ships", "missiles", "nukes", "spies")

        # Skip if the incoming event doesn't contain any military fields
        # (partial events like account/update don't include them)
        has_military_fields = any(k in new_nation for k in _MIL_KEYS)
        if not has_military_fields:
            return

        # Only diff keys present in the new payload — absent keys can't be diffed
        present_keys = [k for k in _MIL_KEYS if k in new_nation]
        old_military = {k: int(old_nation.get(k) or 0) for k in present_keys}
        new_military = {k: int(new_nation.get(k) or 0) for k in present_keys}

        if old_military != new_military:
            await self.holdings_db.apply_military_update(
                nation_id=nation_id,
                old_military=old_military,
                new_military=new_military,
                event_date=ev_date,
                nation_name=nation_name,
            )

    async def _detect_and_record_city_spending(
        self,
        nation_id: int,
        old_city: Dict[str, Any],
        new_city: Dict[str, Any],
        nation_data: Optional[Dict[str, Any]] = None,
        event_date: Optional[str] = None,
    ):
        """
        Compare old vs new city snapshot to detect infra/land/improvement purchases
        and deduct the cost from holdings BEFORE the new snapshot is saved.
        """
        if not self.holdings_db:
            return

        from PnWHarvester.db.pnw_costs import (
            infra_cost, land_cost, city_improvements_cost, city_improvements_resource_costs,
        )

        # Use current time as event date — city.date is the founding date, not the event time
        ev_date = event_date or self._now_str()
        nation_name = (nation_data or {}).get("nation_name") if nation_data else None
        nd = nation_data or {}

        total_cost = 0.0
        breakdown = []
        item_details = []

        old_infra = float(old_city.get("infrastructure") or 0)
        new_infra = float(new_city.get("infrastructure") or 0)
        infra_cost_val = 0.0
        if new_infra > old_infra:
            infra_cost_val = infra_cost(old_infra, new_infra, nation_data=nd)
            total_cost += infra_cost_val
            breakdown.append(f"infra {old_infra:.0f}→{new_infra:.0f} ${infra_cost_val:,.0f}")
            item_details.append(f"infrastructure:{old_infra:.1f}→{new_infra:.1f}")

        old_land = float(old_city.get("land") or 0)
        new_land = float(new_city.get("land") or 0)
        land_cost_val = 0.0
        if new_land > old_land:
            land_cost_val = land_cost(old_land, new_land, nation_data=nd)
            total_cost += land_cost_val
            breakdown.append(f"land {old_land:.0f}→{new_land:.0f} ${land_cost_val:,.0f}")
            item_details.append(f"land:{old_land:.1f}→{new_land:.1f}")

        imp_cost = city_improvements_cost(old_city, new_city)
        imp_rss  = city_improvements_resource_costs(old_city, new_city)
        if imp_cost > 0 or imp_rss:
            total_cost += imp_cost
            rss_str = ", ".join(f"{r}={v:,.1f}" for r, v in imp_rss.items()) if imp_rss else ""
            breakdown.append(f"improvements ${imp_cost:,.0f}" + (f" + {rss_str}" if rss_str else ""))
            item_details.append("improvements")

        if total_cost > 0 or imp_rss:
            await self.holdings_db.deduct_spending(
                nation_id=nation_id,
                cash_cost=total_cost,
                event_type="city_upgrade",
                description=f"City {old_city.get('id')} upgrades: {'; '.join(breakdown)}",
                event_date=ev_date,
                nation_name=nation_name,
                item_type="city_upgrade",
                item_quantity=len([
                    x for x in [
                        old_infra != new_infra,
                        old_land != new_land,
                        bool(imp_cost or imp_rss),
                    ] if x
                ]),
                item_details="; ".join(item_details),
                resource_costs=imp_rss if imp_rss else None,
            )
            rss_str = ", ".join(f"{r}={v:,.1f}" for r, v in imp_rss.items()) if imp_rss else ""
            logger.info(
                f"Holdings: nation {nation_id} city {old_city.get('id')} "
                f"upgrade ${total_cost:,.0f}: {'; '.join(breakdown)}"
                + (f" + {rss_str}" if rss_str else "")
            )
            # ── News: city upgrade ────────────────────────────────────────────
            try:
                import PnWHarvester.db.news_writer as _nw
                from PnWHarvester.db.pnw_costs import _DB_COL_TO_WAR_CALC
                _nd = nation_data or {}
                # Build improvements_built dict: {col: delta} for all increases
                _imps_built: Dict[str, int] = {}
                for _col in _DB_COL_TO_WAR_CALC:
                    _before = int(old_city.get(_col) or 0)
                    _after  = int(new_city.get(_col) or 0)
                    _delta  = max(0, _after - _before)
                    if _delta > 0:
                        _imps_built[_col] = _delta
                asyncio.create_task(_nw.record_city_upgrade(
                    nation_id=nation_id,
                    nation_name=nation_name,
                    nation_flag=_nd.get("flag"),
                    alliance_id=int(_nd.get("alliance_id") or 0) or None,
                    alliance_name=_nd.get("alliance_name"),
                    alliance_flag=_nd.get("alliance_flag"),
                    infra_spent=infra_cost_val,
                    land_spent=land_cost_val,
                    improvements_spent=float(imp_cost),
                    total_spent=total_cost,
                    detail_str="; ".join(breakdown),
                    city_id=old_city.get("id"),
                    city_name=old_city.get("name"),
                    event_date=ev_date,
                    improvements_built=_imps_built if _imps_built else None,
                    improvement_resource_costs=imp_rss if imp_rss else None,
                    infra_before=old_infra if new_infra > old_infra else None,
                    infra_after=new_infra if new_infra > old_infra else None,
                    land_before=old_land if new_land > old_land else None,
                    land_after=new_land if new_land > old_land else None,
                ))
            except Exception as _ne:
                logger.debug(f"news city_upgrade: {_ne}")

    @staticmethod
    def _now_str() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # ── Save helpers ──────────────────────────────────────────────────────────

    async def _save_nation(
        self,
        nation: Dict[str, Any],
        old_nation: Optional[Dict[str, Any]] = None,
    ):
        """
        1. Flatten alliance object into top-level fields (already done by caller).
        2. Detect and record any spending using the pre-fetched old_nation snapshot.
        3. Write new state to GlobalNationsDB, stripping holdings columns so
           HoldingsDB-tracked values are never overwritten with stale API snapshots.

        old_nation is passed in from the caller to avoid a redundant DB read
        (the caller already fetched it for alliance-change logging).
        """
        nation_id = nation.get("id")
        if not nation_id:
            return

        nation_id_int = int(nation_id)

        # Detect spending before overwriting (use pre-fetched old_nation if available)
        if self.holdings_db and self.global_db:
            if old_nation is None:
                old_nation = await self._get_existing_nation(nation_id_int)
            if old_nation:
                await self._detect_and_record_nation_spending(
                    nation_id=nation_id_int,
                    old_nation=old_nation,
                    new_nation=nation,
                    event_date=nation.get("last_active"),
                )

        # Strip money/resources/military on UPDATE — owned by HoldingsDB.
        # Writing them here would overwrite holdings-tracked values with stale snapshots.
        # For new nations (INSERT), we pass the full payload so they start with real
        # API values rather than zeros — HoldingsDB will take over from there.
        # Reuse old_nation (already fetched above) as the existence check — no extra DB read.
        _HOLDINGS_COLS = frozenset((
            "money", "coal", "oil", "uranium", "iron", "bauxite", "lead",
            "gasoline", "munitions", "steel", "aluminum", "food",
            "soldiers", "tanks", "aircraft", "ships", "missiles", "nukes", "spies",
        ))
        if self.global_db:
            if old_nation is not None:
                # Existing nation — strip holdings to avoid overwriting HoldingsDB values
                nation_for_db = {k: v for k, v in nation.items() if k not in _HOLDINGS_COLS}
            else:
                # New nation — include all fields as the initial seed
                nation_for_db = dict(nation)
            await self.global_db.save_nation(nation_for_db)

    async def _save_city(self, nation_id: int, city: Dict[str, Any]):
        """
        1. Read existing city state.
        2. Detect and record any spending (infra/land/improvement purchases).
        3. Write new state to GlobalNationsDB.
        4. If this is a brand-new city (no prior row), increment num_cities on
           the parent nation immediately — don't wait for the next nation/update.
        """
        city_id = city.get("id")
        if not city_id:
            return

        is_new_city = False
        if self.holdings_db and self.global_db:
            old_city = await self._get_existing_city(int(city_id))
            if old_city:
                nation_data = await self._get_existing_nation(nation_id)
                await self._detect_and_record_city_spending(
                    nation_id=nation_id,
                    old_city=old_city,
                    new_city=city,
                    nation_data=nation_data,
                    event_date=self._now_str(),
                )
            else:
                is_new_city = True

        if self.global_db:
            await self.global_db.upsert_city(nation_id, city)
            # Increment num_cities immediately for new cities so the count
            # stays accurate without waiting for the next nation/update event.
            if is_new_city:
                await self.global_db.increment_num_cities(nation_id)

    # ── Beige early-exit detection ────────────────────────────────────────────

    async def _check_beige_early_exit(
        self,
        new_nation: Dict[str, Any],
        old_nation: Optional[Dict[str, Any]],
    ):
        """
        Detect when a tracked nation leaves beige before their alert expires.

        Triggers when ALL of the following are true:
          1. The nation has active beige_alerts rows (someone is watching them).
          2. The old snapshot had beige_turns > 0 OR color == "beige" (was on beige).
          3. The new snapshot has beige_turns == 0 AND color != "beige" (left beige).

        The fast path returns early if EITHER beige signal is still active
        (beige_turns > 0 OR color == "beige") to avoid false positives from
        API event ordering where the two fields briefly disagree.

        When triggered:
          - Enqueues an early-exit notification in beige_early_exit_queue for
            each user who had an alert (the reaper sends the Discord DM).
          - Deletes the alert rows so the reminders box clears immediately.

        This runs in the harvester process which has no Discord bot, so we
        write to the queue table and let the reaper drain it.
        """
        nation_id = int(new_nation.get("id") or 0)
        if not nation_id:
            return

        new_beige_turns = int(new_nation.get("beige_turns") or 0)
        new_color       = str(new_nation.get("color") or "").lower()
        if "." in new_color:
            new_color = new_color.rsplit(".", 1)[-1]

        # Fast path: nation is still on beige by either signal — nothing to do.
        # Use OR: if beige_turns > 0 OR color == "beige", they're still on beige.
        # (The two fields can briefly disagree due to API event ordering.)
        if new_beige_turns > 0 or new_color == "beige":
            return

        # We need the old snapshot to confirm they *were* on beige
        if old_nation is None:
            return
        old_beige_turns = int(old_nation.get("beige_turns") or 0)
        old_color       = str(old_nation.get("color") or "").lower()
        if "." in old_color:
            old_color = old_color.rsplit(".", 1)[-1]

        was_on_beige = old_beige_turns > 0 or old_color == "beige"
        if not was_on_beige:
            return

        # Check if any users have this nation in their beige_alerts
        try:
            from Systems.Functions.beige_alerts_db import (
                get_beige_alerts_for_nation,
                enqueue_early_exit,
                delete_beige_alerts_for_nation,
            )
            alerts = await get_beige_alerts_for_nation(nation_id)
        except Exception as e:
            logger.warning(f"_check_beige_early_exit: DB read failed for nation {nation_id}: {e}")
            return

        if not alerts:
            return

        nation_name = new_nation.get("nation_name") or old_nation.get("nation_name") or f"nation {nation_id}"

        # Enqueue one notification per user, then delete all alert rows
        for alert in alerts:
            stored_turns = int(alert.get("beige_turns") or 0)
            # Only fire if the alert still had turns remaining (> 0).
            # stored_turns == 0 means the alert was already expired/cleaned up
            # by the normal turn-decrement path — don't double-notify.
            if stored_turns < 1:
                continue
            try:
                await enqueue_early_exit(
                    user_id=str(alert["user_id"]),
                    nation_id=str(nation_id),
                    nation_name=nation_name,
                    projected_loot=float(alert.get("projected_loot") or 0),
                )
            except Exception as e:
                logger.warning(
                    f"_check_beige_early_exit: enqueue failed for user {alert['user_id']} "
                    f"nation {nation_id}: {e}"
                )

        # Remove all alert rows for this nation — they're no longer on beige
        try:
            removed = await delete_beige_alerts_for_nation(nation_id)
            logger.info(
                f"_check_beige_early_exit: {nation_name} (id={nation_id}) left beige early "
                f"(had {old_beige_turns} turns stored) — removed {removed} alert(s)"
            )
        except Exception as e:
            logger.warning(f"_check_beige_early_exit: delete failed for nation {nation_id}: {e}")

    # ── Subscription listeners ────────────────────────────────────────────────

    async def _listen_nation_updates(self):
        try:
            subscription = await self.kit.subscribe("nation", "update")
            logger.info("nation/update subscription active (all nations → GlobalNations.db)")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    nation = _obj_to_dict(event)
                    nation_id = nation.get("id")
                    if not nation_id:
                        continue

                    nation_id_int = int(nation_id)

                    # Flatten nested alliance object — always prefer nested over flat
                    self._extract_alliance(nation)
                    is_nw = self._is_nw_by_alliance(nation)

                    # Keep in-memory NW set current (for logging only)
                    if is_nw:
                        self._nw_nation_ids.add(nation_id_int)
                    elif nation_id_int in self._nw_nation_ids:
                        self._nw_nation_ids.discard(nation_id_int)
                        logger.info(
                            f"nation/update → nation {nation_id} left NW "
                            f"(alliance_id now {nation.get('alliance_id')})"
                        )

                    # Fetch old state once — reused for both alliance-change logging
                    # and spending detection inside _save_nation (avoids double read)
                    old_nation: Optional[Dict[str, Any]] = None
                    if self.global_db:
                        old_nation = await self._get_existing_nation(nation_id_int)
                        if old_nation:
                            old_aid = old_nation.get("alliance_id")
                            new_aid = nation.get("alliance_id")
                            if old_aid != new_aid:
                                logger.info(
                                    f"nation/update → nation {nation_id} alliance change: "
                                    f"{old_aid} ({old_nation.get('alliance_name','?')}) → "
                                    f"{new_aid} ({nation.get('alliance_name','?')})"
                                )
                                # ── News: alliance change ─────────────────────
                                try:
                                    import PnWHarvester.db.news_writer as _nw
                                    asyncio.create_task(_nw.record_alliance_change(
                                        nation_id=nation_id_int,
                                        nation_name=nation.get("nation_name"),
                                        nation_flag=nation.get("flag"),
                                        old_alliance_id=int(old_aid) if old_aid else None,
                                        old_alliance_name=old_nation.get("alliance_name"),
                                        new_alliance_id=int(new_aid) if new_aid else None,
                                        new_alliance_name=nation.get("alliance_name"),
                                        new_alliance_flag=nation.get("alliance_flag"),
                                        event_date=nation.get("last_active"),
                                    ))
                                except Exception as _ne:
                                    logger.debug(f"news alliance_change: {_ne}")

                    await self._save_nation(nation, old_nation=old_nation)
                    logger.debug(
                        f"nation/update → {nation_id} → GlobalNations.db"
                        + (" [NW]" if is_nw else "")
                    )

                    # ── Beige early-exit detection ────────────────────────────
                    # If this nation had active beige alerts AND the new snapshot
                    # shows beige_turns == 0 (or color changed away from beige)
                    # while the stored alert still had turns remaining, the nation
                    # left beige early.  Enqueue a notification for the reaper to
                    # send as a Discord DM, then remove the alert rows.
                    await self._check_beige_early_exit(nation, old_nation)

                except Exception as e:
                    logger.error(f"nation/update error: {e}", exc_info=True)

        except asyncio.CancelledError:
            logger.info("nation/update listener cancelled")
            raise
        except (ConnectionResetError, OSError, aiohttp.ClientError) as e:
            logger.warning(f"nation/update WebSocket disconnected: {e} — will restart")
            raise
        except Exception as e:
            logger.error(f"nation/update subscription crashed: {e}", exc_info=True)
            raise

    async def _listen_nation_creates(self):
        try:
            subscription = await self.kit.subscribe("nation", "create")
            logger.info("nation/create subscription active (all nations → GlobalNations.db)")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    nation = _obj_to_dict(event)
                    nation_id = nation.get("id")
                    if not nation_id:
                        continue

                    self._extract_alliance(nation)
                    is_nw = self._is_nw_by_alliance(nation)
                    if is_nw:
                        self._nw_nation_ids.add(int(nation_id))

                    # New nation — no old state to diff against
                    await self._save_nation(nation, old_nation=None)
                    logger.debug(
                        f"nation/create → {nation_id} → GlobalNations.db"
                        + (" [NW]" if is_nw else "")
                    )

                except Exception as e:
                    logger.error(f"nation/create error: {e}", exc_info=True)

        except asyncio.CancelledError:
            logger.info("nation/create listener cancelled")
            raise
        except (ConnectionResetError, OSError, aiohttp.ClientError) as e:
            logger.warning(f"nation/create WebSocket disconnected: {e} — will restart")
            raise
        except Exception as e:
            logger.error(f"nation/create subscription crashed: {e}", exc_info=True)
            raise

    async def _listen_account_updates(self):
        """account/update — patches last_active/discord_id for any nation."""
        try:
            subscription = await self.kit.subscribe("account", "update")
            logger.info("account/update subscription active")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    account = _obj_to_dict(event)
                    nation_id = account.get("id") or account.get("nation_id")
                    if not nation_id:
                        continue

                    # Only patch the fields this event actually carries
                    patch: Dict[str, Any] = {"id": nation_id}
                    if account.get("last_active") is not None:
                        patch["last_active"] = account["last_active"]
                    if account.get("discord_id") is not None:
                        patch["discord_id"] = account["discord_id"]

                    if len(patch) > 1 and self.global_db:
                        await self.global_db.save_nation(patch)
                    logger.debug(f"account/update → patched nation {nation_id}")

                except Exception as e:
                    logger.error(f"account/update error: {e}", exc_info=True)

        except asyncio.CancelledError:
            logger.info("account/update listener cancelled")
            raise
        except (ConnectionResetError, OSError, aiohttp.ClientError) as e:
            logger.warning(f"account/update WebSocket disconnected: {e} — will restart")
            raise
        except Exception as e:
            logger.error(f"account/update subscription crashed: {e}", exc_info=True)
            raise

    async def _listen_city_updates(self):
        try:
            subscription = await self.kit.subscribe("city", "update")
            logger.info("city/update subscription active (all cities → GlobalNations.db)")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    city = _obj_to_dict(event)
                    city_id   = city.get("id")
                    nation_id = city.get("nation_id")
                    if not city_id or not nation_id:
                        continue
                    await self._save_city(int(nation_id), city)
                    logger.debug(f"city/update → city {city_id} nation {nation_id}")

                except Exception as e:
                    logger.error(f"city/update error: {e}", exc_info=True)

        except asyncio.CancelledError:
            logger.info("city/update listener cancelled")
            raise
        except (ConnectionResetError, OSError, aiohttp.ClientError) as e:
            logger.warning(f"city/update WebSocket disconnected: {e} — will restart")
            raise
        except Exception as e:
            logger.error(f"city/update subscription crashed: {e}", exc_info=True)
            raise

    async def _listen_city_creates(self):
        try:
            subscription = await self.kit.subscribe("city", "create")
            logger.info("city/create subscription active (all cities → GlobalNations.db)")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    city = _obj_to_dict(event)
                    city_id   = city.get("id")
                    nation_id = city.get("nation_id")
                    if not city_id or not nation_id:
                        continue
                    await self._save_city(int(nation_id), city)
                    logger.debug(f"city/create → city {city_id} nation {nation_id}")

                except Exception as e:
                    logger.error(f"city/create error: {e}", exc_info=True)

        except asyncio.CancelledError:
            logger.info("city/create listener cancelled")
            raise
        except (ConnectionResetError, OSError, aiohttp.ClientError) as e:
            logger.warning(f"city/create WebSocket disconnected: {e} — will restart")
            raise
        except Exception as e:
            logger.error(f"city/create subscription crashed: {e}", exc_info=True)
            raise

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self):
        if self.running:
            logger.warning("GlobalNationsSubscription already running")
            return
        self.running = True
        await self._seed_nw_set()
        logger.info("Starting GlobalNationsSubscription → GlobalNations.db (single DB)")
        self._tasks = [
            asyncio.create_task(self._listen_nation_updates()),
            asyncio.create_task(self._listen_nation_creates()),
            asyncio.create_task(self._listen_account_updates()),
            asyncio.create_task(self._listen_city_updates()),
            asyncio.create_task(self._listen_city_creates()),
        ]
        try:
            # Wait for the FIRST task to finish (any disconnect/crash triggers restart)
            done, pending = await asyncio.wait(
                self._tasks, return_when=asyncio.FIRST_COMPLETED
            )
            # Cancel all remaining listeners immediately — don't wait for next event
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            # Re-raise the first exception so run_forever() can log it
            for t in done:
                if t.exception():
                    raise t.exception()
        finally:
            self.running = False
            for t in self._tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def stop(self):
        self.running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("GlobalNationsSubscription stopped")

    async def run_forever(self):
        """Run indefinitely, restarting all listeners on any disconnect or crash."""
        from pnwkit import errors as pnwkit_errors
        while True:
            try:
                await self.start()
                logger.warning("GlobalNationsSubscription ended — restarting in 30s")
            except asyncio.CancelledError:
                logger.info("GlobalNationsSubscription cancelled")
                break
            except (pnwkit_errors.NoReconnect, aiohttp.ClientError,
                    ConnectionResetError, OSError) as e:
                logger.warning(f"GlobalNationsSubscription disconnected ({e}) — restarting in 30s")
            except Exception as e:
                logger.error(f"GlobalNationsSubscription crashed ({e}) — restarting in 30s",
                             exc_info=True)
            finally:
                await self.stop()
            await asyncio.sleep(30)

    async def verify_alliance_data_integrity(self) -> Dict[str, int]:
        """Return basic stats about GlobalNations.db coverage."""
        stats: Dict[str, int] = {
            "global_nations_total": 0,
            "global_nations_with_alliance": 0,
            "nw_nations_in_global": 0,
            "distinct_alliances": 0,
        }
        if not self.global_db:
            return stats
        try:
            async with self.global_db._lock:
                with sqlite3.connect(self.global_db.db_path) as conn:
                    stats["global_nations_total"] = conn.execute(
                        "SELECT COUNT(*) FROM nations"
                    ).fetchone()[0]
                    stats["global_nations_with_alliance"] = conn.execute(
                        "SELECT COUNT(*) FROM nations WHERE alliance_id IS NOT NULL AND alliance_id != 0"
                    ).fetchone()[0]
                    stats["nw_nations_in_global"] = conn.execute(
                        "SELECT COUNT(*) FROM nations WHERE alliance_id = ?",
                        (NW_ALLIANCE_ID,),
                    ).fetchone()[0]
                    stats["distinct_alliances"] = conn.execute(
                        "SELECT COUNT(DISTINCT alliance_id) FROM nations WHERE alliance_id IS NOT NULL"
                    ).fetchone()[0]
        except Exception as e:
            logger.error(f"verify_alliance_data_integrity: {e}", exc_info=True)
        return stats
