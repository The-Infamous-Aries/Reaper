"""
GlobalNationsSubscription

Unfiltered WebSocket subscriptions for ALL nations in the game.

Behaviour:
  - nation/update  → save to GlobalNationsDB (all nations); also save to NWNationsDB if NW
  - nation/create  → same dual-write
  - account/update → patch last_active/discord_id in both DBs if present
  - city/update    → upsert city in GlobalNationsDB (always);
                     also NWNationsDB if nation_id is in the NW set
  - city/create    → same dual-write

NW membership is tracked in a local set (_nw_nation_ids) that is seeded from
the NW DB on startup and kept current by nation/update events. City events
check this set in O(1) — no DB lookup per city event.

pnwkit requires one subscribe() call per event type — we run each as a
separate asyncio task within the same process.
"""

import asyncio
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

from pnwkit.new import QueryKit

logger = logging.getLogger(__name__)

IRS_ALLIANCE_ID = 14225
EP_ALLIANCE_ID  = IRS_ALLIANCE_ID  # backward-compat alias


def _obj_to_dict(obj: Any) -> Dict[str, Any]:
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return dict(obj)
    return vars(obj)


class GlobalNationsSubscription:
    def __init__(self, global_db, nw_db, api_key: str, holdings_db=None):
        """
        global_db   : GlobalNationsDB — receives ALL nation/city events (game-wide)
        nw_db       : IRSNationsDB    — receives NW-only events
        api_key     : PnW API v3 key
        holdings_db : HoldingsDB (optional) — tracks per-nation cash/resource ledger
        """
        self.global_db   = global_db
        self.nw_db       = nw_db
        self.holdings_db = holdings_db
        self.api_key     = api_key
        self.kit         = QueryKit(api_key)
        self.running     = False
        self._tasks: list[asyncio.Task] = []

        # In-memory set of NW nation IDs — seeded on startup, kept current by
        # nation/update events. Lets city handlers avoid a DB lookup per event.
        self._nw_nation_ids: Set[int] = set()

    async def _seed_nw_set(self):
        """Load all current NW nation IDs from the NW DB into the in-memory set."""
        try:
            async with self.nw_db._lock:
                with sqlite3.connect(self.nw_db.db_path) as conn:
                    rows = conn.execute("SELECT id FROM nations").fetchall()
                    self._nw_nation_ids = {r[0] for r in rows}
            logger.info(f"NW nation set seeded: {len(self._nw_nation_ids)} nations")
        except Exception as e:
            logger.error(f"Failed to seed NW nation set: {e}", exc_info=True)

    def _is_nw_by_alliance(self, nation: Dict[str, Any]) -> bool:
        return int(nation.get("alliance_id") or 0) == IRS_ALLIANCE_ID

    def _is_nw_id(self, nation_id: int) -> bool:
        return nation_id in self._nw_nation_ids

    # ── Holdings spending detection ───────────────────────────────────────────

    async def _get_existing_nation(self, nation_id: int) -> Optional[Dict[str, Any]]:
        """Read the current nation row from GlobalNationsDB before overwriting it."""
        if not self.global_db:
            return None
        try:
            return await self.global_db.get_nation(nation_id)
        except Exception as e:
            logger.debug(f"_get_existing_nation({nation_id}): {e}")
            return None

    async def _get_existing_city(self, city_id: int) -> Optional[Dict[str, Any]]:
        """Read the current city row from GlobalNationsDB before overwriting it."""
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

        Detects:
          - City purchase: turns_since_last_city reset to 0 (or decreased significantly)
          - Project purchases: any project flag flipped 0→1
        """
        if not self.holdings_db:
            return

        from PnWHarvester.db.pnw_costs import city_cost, projects_purchased_cost

        nation_name = new_nation.get("nation_name") or old_nation.get("nation_name")
        ev_date = event_date or self._now_str()

        # ── City purchase detection ───────────────────────────────────────────
        old_turns_city = int(old_nation.get("turns_since_last_city") or 0)
        new_turns_city = int(new_nation.get("turns_since_last_city") or 0)
        old_num_cities = int(old_nation.get("num_cities") or 0)
        new_num_cities = int(new_nation.get("num_cities") or 0)

        # A city was bought if turns_since_last_city reset to 0 AND city count increased,
        # OR if city count increased regardless (catches edge cases).
        cities_bought = max(0, new_num_cities - old_num_cities)
        if cities_bought == 0 and old_turns_city > 2 and new_turns_city == 0:
            # turns reset but num_cities didn't update yet in this payload
            cities_bought = 1

        if cities_bought > 0:
            # Build nation_data dict for discount calculation
            nd = new_nation
            # Cost is for each city bought sequentially
            total_city_cost = 0.0
            base_cities = old_num_cities
            for _ in range(cities_bought):
                total_city_cost += city_cost(base_cities, nation_data=nd)
                base_cities += 1
            if total_city_cost > 0:
                await self.holdings_db.deduct_spending(
                    nation_id=nation_id,
                    cash_cost=total_city_cost,
                    event_type="city_purchase",
                    description=f"Bought {cities_bought} city/cities (had {old_num_cities} → {new_num_cities})",
                    event_date=ev_date,
                    nation_name=nation_name,
                )
                logger.info(
                    f"Holdings: nation {nation_id} city purchase "
                    f"${total_city_cost:,.0f} ({old_num_cities}→{new_num_cities} cities)"
                )

        # ── Project purchase detection ────────────────────────────────────────
        old_turns_proj = int(old_nation.get("turns_since_last_project") or 0)
        new_turns_proj = int(new_nation.get("turns_since_last_project") or 0)

        # Only run project diff if turns_since_last_project reset
        if old_turns_proj > 2 and new_turns_proj == 0:
            proj_cost = projects_purchased_cost(old_nation, new_nation)
            if proj_cost > 0:
                await self.holdings_db.deduct_spending(
                    nation_id=nation_id,
                    cash_cost=proj_cost,
                    event_type="project_purchase",
                    description=f"Project(s) purchased (turns_proj {old_turns_proj}→{new_turns_proj})",
                    event_date=ev_date,
                    nation_name=nation_name,
                )
                logger.info(
                    f"Holdings: nation {nation_id} project purchase ${proj_cost:,.0f}"
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

        from PnWHarvester.db.pnw_costs import infra_cost, land_cost, city_improvements_cost

        ev_date = event_date or self._now_str()
        nation_name = (nation_data or {}).get("nation_name") if nation_data else None

        # Build a minimal nation_data dict for discount calculation
        nd = nation_data or {}

        total_cost = 0.0
        breakdown = []

        # ── Infrastructure ────────────────────────────────────────────────────
        old_infra = float(old_city.get("infrastructure") or 0)
        new_infra = float(new_city.get("infrastructure") or 0)
        if new_infra > old_infra:
            cost = infra_cost(old_infra, new_infra, nation_data=nd)
            total_cost += cost
            breakdown.append(f"infra {old_infra:.0f}→{new_infra:.0f} ${cost:,.0f}")

        # ── Land ──────────────────────────────────────────────────────────────
        old_land = float(old_city.get("land") or 0)
        new_land = float(new_city.get("land") or 0)
        if new_land > old_land:
            cost = land_cost(old_land, new_land, nation_data=nd)
            total_cost += cost
            breakdown.append(f"land {old_land:.0f}→{new_land:.0f} ${cost:,.0f}")

        # ── Improvements ──────────────────────────────────────────────────────
        imp_cost = city_improvements_cost(old_city, new_city)
        if imp_cost > 0:
            total_cost += imp_cost
            breakdown.append(f"improvements ${imp_cost:,.0f}")

        if total_cost > 0:
            await self.holdings_db.deduct_spending(
                nation_id=nation_id,
                cash_cost=total_cost,
                event_type="city_upgrade",
                description=f"City {old_city.get('id')} upgrades: {'; '.join(breakdown)}",
                event_date=ev_date,
                nation_name=nation_name,
            )
            logger.info(
                f"Holdings: nation {nation_id} city {old_city.get('id')} "
                f"upgrade ${total_cost:,.0f}: {'; '.join(breakdown)}"
            )

    @staticmethod
    def _now_str() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # ── Save helpers ──────────────────────────────────────────────────────────

    async def _save_nation(self, nation: Dict[str, Any]):
        """
        1. Read existing nation state from GlobalNationsDB.
        2. Detect and record any spending (city/project purchases).
        3. Write new state to GlobalNationsDB (and NWNationsDB if NW).
        """
        nation_id = nation.get("id")
        if not nation_id:
            return

        nation_id_int = int(nation_id)

        # Step 1: read old state BEFORE overwriting
        if self.holdings_db and self.global_db:
            old_nation = await self._get_existing_nation(nation_id_int)
            if old_nation:
                await self._detect_and_record_nation_spending(
                    nation_id=nation_id_int,
                    old_nation=old_nation,
                    new_nation=nation,
                    event_date=nation.get("last_active"),
                )

        # Step 2: write new state
        if self.global_db:
            await self.global_db.save_nation(nation)
        if self._is_nw_by_alliance(nation):
            await self.nw_db.save_nation(nation)

    async def _save_city(self, nation_id: int, city: Dict[str, Any]):
        """
        1. Read existing city state from GlobalNationsDB.
        2. Detect and record any spending (infra/land/improvement purchases).
        3. Write new state to GlobalNationsDB (and NWNationsDB if NW).
        """
        city_id = city.get("id")
        if not city_id:
            return

        # Step 1: read old city state BEFORE overwriting
        if self.holdings_db and self.global_db:
            old_city = await self._get_existing_city(int(city_id))
            if old_city:
                # Fetch nation data for project modifier flags (cached in global_db)
                nation_data = await self._get_existing_nation(nation_id)
                await self._detect_and_record_city_spending(
                    nation_id=nation_id,
                    old_city=old_city,
                    new_city=city,
                    nation_data=nation_data,
                    event_date=city.get("date"),
                )

        # Step 2: write new state
        if self.global_db:
            await self.global_db.upsert_city(nation_id, city)
        if self._is_nw_id(nation_id):
            await self.nw_db.upsert_city(nation_id, city)

    async def _listen_nation_updates(self):
        try:
            subscription = await self.kit.subscribe("nation", "update")
            logger.info("nation/update subscription active (unfiltered — all game nations)")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    nation = _obj_to_dict(event)
                    nation_id = nation.get("id")
                    if not nation_id:
                        continue

                    nation_id_int = int(nation_id)
                    is_nw = self._is_nw_by_alliance(nation)

                    # Keep the in-memory NW set current
                    if is_nw:
                        self._nw_nation_ids.add(nation_id_int)
                    elif nation_id_int in self._nw_nation_ids:
                        # Nation left NW — remove from set and NW DB
                        self._nw_nation_ids.discard(nation_id_int)
                        await self.nw_db.remove_departed_nations({nation_id_int})
                        logger.info(f"nation/update → nation {nation_id} left NW — removed from NW DB")

                    # _save_nation: diffs old state → detects spending → saves new state
                    await self._save_nation(nation)
                    logger.debug(
                        f"nation/update → nation {nation_id} → "
                        f"GlobalNations" + (" + NWNations" if is_nw else "")
                    )

                except Exception as e:
                    logger.error(f"nation/update error: {e}", exc_info=True)

        except asyncio.CancelledError:
            logger.info("nation/update listener cancelled")
        except Exception as e:
            logger.error(f"nation/update subscription crashed: {e}", exc_info=True)
            self.running = False

    # ── nation/create ─────────────────────────────────────────────────────────

    async def _listen_nation_creates(self):
        try:
            subscription = await self.kit.subscribe("nation", "create")
            logger.info("nation/create subscription active (unfiltered — all game nations)")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    nation = _obj_to_dict(event)
                    nation_id = nation.get("id")
                    if not nation_id:
                        continue

                    is_nw = self._is_nw_by_alliance(nation)
                    if is_nw:
                        self._nw_nation_ids.add(int(nation_id))

                    await self._save_nation(nation)
                    logger.debug(
                        f"nation/create → nation {nation_id} → "
                        f"GlobalNations" + (" + NWNations" if is_nw else "")
                    )

                except Exception as e:
                    logger.error(f"nation/create error: {e}", exc_info=True)

        except asyncio.CancelledError:
            logger.info("nation/create listener cancelled")
        except Exception as e:
            logger.error(f"nation/create subscription crashed: {e}", exc_info=True)

    # ── account/update ────────────────────────────────────────────────────────

    async def _listen_account_updates(self):
        """account/update patches last_active/discord_id for any nation."""
        try:
            subscription = await self.kit.subscribe("account", "update")
            logger.info("account/update subscription active (unfiltered)")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    account = _obj_to_dict(event)
                    nation_id = account.get("id") or account.get("nation_id")
                    if not nation_id:
                        continue

                    patch = {
                        "id":          nation_id,
                        "last_active": account.get("last_active"),
                        "discord_id":  account.get("discord_id"),
                    }

                    if self.global_db:
                        await self.global_db.save_nation(patch)

                    if self._is_nw_id(int(nation_id)):
                        await self.nw_db.save_nation(patch)
                        logger.debug(f"account/update → patched NW nation {nation_id}")
                    else:
                        logger.debug(f"account/update → patched global nation {nation_id}")

                except Exception as e:
                    logger.error(f"account/update error: {e}", exc_info=True)

        except asyncio.CancelledError:
            logger.info("account/update listener cancelled")
        except Exception as e:
            logger.error(f"account/update subscription crashed: {e}", exc_info=True)

    # ── city/update ───────────────────────────────────────────────────────────

    async def _listen_city_updates(self):
        try:
            subscription = await self.kit.subscribe("city", "update")
            logger.info("city/update subscription active (unfiltered — all game cities)")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    city = _obj_to_dict(event)
                    city_id   = city.get("id")
                    nation_id = city.get("nation_id")
                    if not city_id or not nation_id:
                        continue

                    nation_id_int = int(nation_id)
                    await self._save_city(nation_id_int, city)
                    logger.debug(
                        f"city/update → city {city_id} nation {nation_id} "
                        f"(nw={self._is_nw_id(nation_id_int)})"
                    )

                except Exception as e:
                    logger.error(f"city/update error: {e}", exc_info=True)

        except asyncio.CancelledError:
            logger.info("city/update listener cancelled")
        except Exception as e:
            logger.error(f"city/update subscription crashed: {e}", exc_info=True)

    # ── city/create ───────────────────────────────────────────────────────────

    async def _listen_city_creates(self):
        try:
            subscription = await self.kit.subscribe("city", "create")
            logger.info("city/create subscription active (unfiltered — all game cities)")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    city = _obj_to_dict(event)
                    city_id   = city.get("id")
                    nation_id = city.get("nation_id")
                    if not city_id or not nation_id:
                        continue

                    nation_id_int = int(nation_id)
                    await self._save_city(nation_id_int, city)
                    logger.debug(
                        f"city/create → city {city_id} nation {nation_id} "
                        f"(nw={self._is_nw_id(nation_id_int)})"
                    )

                except Exception as e:
                    logger.error(f"city/create error: {e}", exc_info=True)

        except asyncio.CancelledError:
            logger.info("city/create listener cancelled")
        except Exception as e:
            logger.error(f"city/create subscription crashed: {e}", exc_info=True)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self):
        if self.running:
            logger.warning("GlobalNationsSubscription already running")
            return
        self.running = True

        # Seed the NW set before starting listeners so city events are routed
        # correctly from the very first event
        await self._seed_nw_set()

        logger.info("Starting GlobalNationsSubscription (all nations → GlobalNations; NW → NWNations)")
        self._tasks = [
            asyncio.create_task(self._listen_nation_updates()),
            asyncio.create_task(self._listen_nation_creates()),
            asyncio.create_task(self._listen_account_updates()),
            asyncio.create_task(self._listen_city_updates()),
            asyncio.create_task(self._listen_city_creates()),
        ]
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def stop(self):
        self.running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("GlobalNationsSubscription stopped")
