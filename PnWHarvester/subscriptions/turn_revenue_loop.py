"""
TurnRevenueLoop

Fires at every PnW turn boundary (midnight UTC, then every 2 hours) and
credits each tracked nation's holdings with one turn of net revenue using
our own revenue_calc formulas — NOT the GNI field from the API.

Turn schedule (UTC):
  00:00, 02:00, 04:00, 06:00, 08:00, 10:00, 12:00,
  14:00, 16:00, 18:00, 20:00, 22:00

What gets applied per nation per turn:
  money       += net_cash_num   (cash income minus all upkeep; can be negative)
  <rss>       += net <rss> production (net can be negative — e.g. steel mills consuming coal)

Game context (colors, prices, radiation, seasonal_mod) is loaded entirely
from reaper.db via database_manager — NO API calls are made.  Nation and
city data come from GlobalNationsDB.  The API is never queried during turn
processing.

Nations that have no city data in GlobalNationsDB are skipped silently.
Nations on vacation mode (vacation_mode_turns > 0) are skipped — they
produce no income.

War detection priority (mirrors revenue command exactly):
  1. IRSWarsDB is_active=1 rows  → authoritative for NW nations
  2. GlobalNationsDB offensive_wars_count / defensive_wars_count snapshot
     → used for all nations not covered by IRSWarsDB
  A nation is considered at war if it appears in EITHER source.

Missed-turn catch-up:
  On startup the loop checks how many turns have elapsed since the last
  revenue was applied (last_revenue_date in GlobalNationsDB) and applies
  each missed turn in sequence using the same game context.  A maximum of
  MAX_CATCHUP_TURNS missed turns are replayed to avoid runaway catch-up on
  a long outage.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# PnW turn length in seconds (2 hours)
TURN_SECONDS = 7200

# Maximum number of missed turns to replay on startup catch-up.
# 12 turns = 24 hours.  Beyond that we just start fresh from the next live turn.
MAX_CATCHUP_TURNS = 12

# Resources tracked in holdings (must match RESOURCE_COLS in holdings_db.py)
_RESOURCE_COLS = (
    "coal", "oil", "uranium", "iron", "bauxite", "lead",
    "gasoline", "munitions", "steel", "aluminum", "food",
)


# ── Turn boundary helpers ─────────────────────────────────────────────────────

def _turn_boundary_before(dt: datetime) -> datetime:
    """Return the most-recent turn boundary at or before *dt* (UTC even hour, :00:00)."""
    h = (dt.hour // 2) * 2
    return dt.replace(hour=h, minute=0, second=0, microsecond=0)


def _next_turn_dt(now: datetime) -> datetime:
    """Return the next UTC turn boundary strictly after *now*.

    Turn boundaries are at 00:00, 02:00, 04:00, … 22:00 UTC.
    If *now* is exactly on a boundary this returns the NEXT one (2 h later).
    """
    # Floor to current even-hour boundary, then add one full turn
    current_boundary = _turn_boundary_before(now)
    candidate = current_boundary + timedelta(seconds=TURN_SECONDS)
    # If we're exactly on the boundary, candidate == now + 2h — correct.
    # If we're past the boundary by any amount, candidate is still the next one.
    if candidate <= now:
        candidate += timedelta(seconds=TURN_SECONDS)
    return candidate


def _seconds_until(target: datetime, now: datetime) -> float:
    return max((target - now).total_seconds(), 0.0)


def _missed_turn_boundaries(since: datetime, now: datetime) -> List[datetime]:
    """Return all turn boundaries in (since, now] in chronological order."""
    boundaries: List[datetime] = []
    # Start from the first boundary strictly after *since*
    candidate = _turn_boundary_before(since) + timedelta(seconds=TURN_SECONDS)
    while candidate <= now:
        boundaries.append(candidate)
        candidate += timedelta(seconds=TURN_SECONDS)
    return boundaries


# ── Main class ────────────────────────────────────────────────────────────────

class TurnRevenueLoop:
    """
    Standalone asyncio task that applies turn revenue to all tracked nations.

    Parameters
    ----------
    holdings_db   : HoldingsDB instance
    global_db     : GlobalNationsDB instance (for nation + city data)
    query_instance: kept for call-site compatibility but never used for turn revenue
    """

    def __init__(self, holdings_db, global_db, query_instance=None):
        self.holdings_db    = holdings_db
        self.global_db      = global_db
        # query_instance is intentionally unused — all game context comes from
        # reaper.db via database_manager, so no API calls are made during turns.
        self.running        = False
        self._task: Optional[asyncio.Task] = None
        # Cache last successful game context so a DB hiccup doesn't skip a turn.
        self._last_game_ctx: Optional[Dict[str, Any]] = None

    # ── Active-war set ────────────────────────────────────────────────────────

    async def _build_active_war_ids(self) -> Set[int]:
        """
        Build the complete set of nation IDs currently at war.

        Two sources, unioned together:
          1. IRSWarsDB  — authoritative for NW nations (is_active=1 rows).
          2. GlobalNationsDB snapshot — offensive_wars_count or
             defensive_wars_count > 0 for every other nation.

        Using both sources means NW nations get the accurate IRSWarsDB signal
        AND non-NW nations get the best available signal from their snapshot.
        """
        active_ids: Set[int] = set()

        # ── Source 1: IRSWarsDB (NW wars, authoritative) ──────────────────────
        try:
            from Systems.Functions.irs_wars_db import IRSWarsDB
            from Systems.Functions.db_paths import NW_WARS_DB_STR
            wars_db = IRSWarsDB(NW_WARS_DB_STR)
            nw_ids = await wars_db.get_active_war_nation_ids()
            active_ids.update(nw_ids)
            logger.debug(f"TurnRevenueLoop: {len(nw_ids)} NW nations at war (IRSWarsDB)")
        except Exception as e:
            logger.warning(f"TurnRevenueLoop: IRSWarsDB unavailable — {e}")

        # ── Source 2: GlobalNationsDB snapshot counts ─────────────────────────
        try:
            loop = asyncio.get_event_loop()
            def _query_war_nations():
                import sqlite3 as _sq
                from Systems.Functions.db_paths import GLOBAL_NATIONS_DB_STR
                with _sq.connect(GLOBAL_NATIONS_DB_STR, timeout=15) as conn:
                    conn.execute("PRAGMA busy_timeout=15000")
                    rows = conn.execute(
                        """
                        SELECT id
                        FROM nations
                        WHERE (
                            (offensive_wars_count  IS NOT NULL AND offensive_wars_count  > 0)
                         OR (defensive_wars_count IS NOT NULL AND defensive_wars_count > 0)
                        )
                        AND nation_name IS NOT NULL AND nation_name != ''
                        """
                    ).fetchall()
                return {int(r[0]) for r in rows}
            snapshot_ids = await loop.run_in_executor(None, _query_war_nations)
            active_ids.update(snapshot_ids)
            logger.debug(
                f"TurnRevenueLoop: {len(snapshot_ids)} nations at war (GlobalNationsDB snapshot)"
            )
        except Exception as e:
            logger.warning(f"TurnRevenueLoop: GlobalNationsDB war-count query failed — {e}")

        return active_ids

    # ── Game context fetch ────────────────────────────────────────────────────

    async def _fetch_game_context(self) -> Optional[Dict[str, Any]]:
        """
        Load game context entirely from reaper.db via database_manager.
        No API calls are made — all data must already be present in the DB
        (kept fresh by the reaper bot's timed queries).

        Keys returned: colors, prices, treasures, radiation, seasonal_mod
        """
        try:
            from Systems.Functions.database_manager import (
                get_latest_resource_prices,
                get_latest_game_data,
                get_latest_game_info,
                get_latest_radiation_data,
            )

            # ── Prices ────────────────────────────────────────────────────────
            prices: Dict[str, float] = {}
            price_data = await get_latest_resource_prices()
            if price_data:
                # revenue_calc uses sell price
                prices = {res: float(p["sell"]) for res, p in price_data.items()}
            if not prices:
                logger.warning("TurnRevenueLoop: no resource prices in reaper.db — skipping turn")
                return None
            prices["money"] = 1.0

            # ── Colors ────────────────────────────────────────────────────────
            colors: Dict[str, float] = {}
            colors_data = await get_latest_game_data("colors")
            if colors_data:
                colors = {c["color"].lower(): float(c.get("turn_bonus") or 0) for c in colors_data}
            if not colors:
                logger.warning("TurnRevenueLoop: no color data in reaper.db — using empty colors")

            # ── Radiation ─────────────────────────────────────────────────────
            radiation: Dict[str, float] = {
                "na": 0.0, "sa": 0.0, "eu": 0.0, "as": 0.0,
                "af": 0.0, "au": 0.0, "an": 0.0,
            }
            rad_data = await get_latest_radiation_data()
            if rad_data:
                g = float(rad_data.get("global") or 0)
                radiation = {
                    "na": (float(rad_data.get("north_america") or 0) + g) / -1000,
                    "sa": (float(rad_data.get("south_america") or 0) + g) / -1000,
                    "eu": (float(rad_data.get("europe")        or 0) + g) / -1000,
                    "as": (float(rad_data.get("asia")          or 0) + g) / -1000,
                    "af": (float(rad_data.get("africa")        or 0) + g) / -1000,
                    "au": (float(rad_data.get("australia")     or 0) + g) / -1000,
                    "an": (float(rad_data.get("antarctica")    or 0) + g) / -1000,
                }

            # ── Game date → seasonal modifiers ────────────────────────────────
            month = 1
            gi = await get_latest_game_info()
            if gi and gi.get("game_date"):
                try:
                    parsed = datetime.fromisoformat(gi["game_date"].replace("Z", "+00:00"))
                    month = parsed.month
                except Exception:
                    pass

            seasonal_mod: Dict[str, float] = {
                "na": 1.0, "sa": 1.0, "eu": 1.0, "as": 1.0,
                "af": 1.0, "au": 1.0, "an": 0.5,
            }
            if month in (6, 7, 8):
                seasonal_mod.update({"na": 1.2, "as": 1.2, "eu": 1.2,
                                     "sa": 0.8, "af": 0.8, "au": 0.8})
            elif month in (12, 1, 2):
                seasonal_mod.update({"na": 0.8, "as": 0.8, "eu": 0.8,
                                     "sa": 1.2, "af": 1.2, "au": 1.2})

            # Treasures are stored with nations — revenue_calc reads them from
            # the nation dict directly, so we pass an empty list here.
            treasures: List[Dict[str, Any]] = []

            return {
                "colors":       colors,
                "prices":       prices,
                "treasures":    treasures,
                "radiation":    radiation,
                "seasonal_mod": seasonal_mod,
            }
        except Exception as e:
            logger.error(f"TurnRevenueLoop: failed to build game context from DB: {e}", exc_info=True)
            return None

    # ── Per-nation revenue calculation ────────────────────────────────────────

    async def _calc_and_apply_nation(
        self,
        nation_id: int,
        ctx: Dict[str, Any],
        turn_date: str,
        active_war_ids: Set[int],
    ) -> bool:
        """
        Fetch nation + cities from GlobalNationsDB, run revenue_calc_sync with
        data entirely from local DBs, and apply the result to holdings.

        No API calls are made — nation/city data comes from GlobalNationsDB,
        game context from reaper.db.

        Returns True if revenue was applied, False if skipped or failed.
        """
        try:
            nation = await self.global_db.get_nation(nation_id)
            if not nation:
                return False

            # Skip nations on vacation mode — they earn nothing
            if int(nation.get("vacation_mode_turns") or 0) > 0:
                return False

            # Skip nations with no cities recorded — can't calculate revenue
            cities = await self.global_db.get_cities_for_nation(nation_id)
            if not cities:
                return False

            # Attach cities list to nation dict (revenue_calc expects nation['cities'])
            nation["cities"] = cities

            # War status from the pre-built set — no API query needed
            is_war: bool = nation_id in active_war_ids

            # Use the synchronous variant — no async overhead, no API calls
            from Systems.PnW.Util.rev_correct import revenue_calc_sync

            rev = revenue_calc_sync(
                nation=nation,
                radiation=ctx["radiation"],
                treasures=ctx["treasures"],
                prices=ctx["prices"],
                colors=ctx["colors"],
                seasonal_mod=ctx["seasonal_mod"],
                build=None,
                single_city=False,
                include_spies=True,
                is_war=is_war,
            )

            if not rev:
                return False

            # net_cash_num = cash income minus ALL upkeep (can be negative)
            money_delta = float(rev.get("net_cash_num") or 0)

            # Resource net production per turn (positive = produced, negative = consumed)
            resource_deltas = {r: float(rev.get(r) or 0) for r in _RESOURCE_COLS}

            await self.holdings_db.apply_turn_revenue(
                nation_id=nation_id,
                money_delta=money_delta,
                resource_deltas=resource_deltas,
                turn_date=turn_date,
                nation_name=nation.get("nation_name"),
            )
            return True

        except Exception as e:
            logger.error(
                f"TurnRevenueLoop: error processing nation {nation_id}: {e}",
                exc_info=True,
            )
            return False

    # ── Beige alert maintenance ───────────────────────────────────────────────

    async def _update_beige_alerts_for_turn(self, ctx: Dict[str, Any]):
        """
        Called once per game turn after revenue is applied.

        For every row in beige_alerts:
          1. Pull the authoritative beige_turns from GlobalNations.db.
          2. Recalculate projected_loot from the nation's current holdings.
          3. Remove alerts where beige_turns has reached 0 (nation left beige).

        Uses the shared beige_alerts_db module so writes are consistent with
        the reaper process (both use WAL mode; no explicit locking needed).
        """
        import sqlite3 as _sq
        from Systems.Functions.db_paths import GLOBAL_NATIONS_DB_STR as _GN_DB
        from Systems.Functions.beige_alerts_db import (
            get_all_beige_alerts as _get_all,
            batch_update_beige_alerts as _batch_update,
        )

        # ── Load all current beige alerts ─────────────────────────────────────
        try:
            alerts = await _get_all()
        except Exception as e:
            logger.warning(f"TurnRevenueLoop._update_beige_alerts: could not read alerts.db — {e}")
            return

        if not alerts:
            return

        nation_ids = list({int(a["nation_id"]) for a in alerts})

        # ── Fetch live beige_turns + war_policy from GlobalNations.db ─────────
        live_nation_map: Dict[int, Dict] = {}
        try:
            placeholders = ",".join("?" * len(nation_ids))
            with _sq.connect(_GN_DB) as _gconn:
                _gconn.row_factory = _sq.Row
                _rows = _gconn.execute(
                    f"SELECT id, beige_turns, war_policy FROM nations WHERE id IN ({placeholders})",
                    nation_ids,
                ).fetchall()
            for _r in _rows:
                live_nation_map[int(_r["id"])] = {
                    "beige_turns": int(_r["beige_turns"] or 0),
                    "war_policy":  str(_r["war_policy"] or ""),
                }
        except Exception as e:
            logger.warning(f"TurnRevenueLoop._update_beige_alerts: GlobalNations query failed — {e}")

        # ── Fetch holdings for projected_loot recalculation ───────────────────
        holdings_map: Dict[int, Dict] = {}
        try:
            holdings_map = await self.holdings_db.get_holdings_bulk(nation_ids)
        except Exception as e:
            logger.warning(f"TurnRevenueLoop._update_beige_alerts: holdings fetch failed — {e}")

        # ── Loot multipliers ──────────────────────────────────────────────────
        try:
            from web.api.raids_api import LOOT_MULTIPLIERS as _LM, RESOURCES as _RES
        except ImportError:
            _LM = None
            _RES = ()

        prices = ctx.get("prices", {})

        # ── Build update / delete lists ───────────────────────────────────────
        to_delete: List[int] = []
        to_update: List[tuple] = []  # (beige_turns, projected_loot, alert_id)

        for alert in alerts:
            nid  = int(alert["nation_id"])
            live = live_nation_map.get(nid)

            # Authoritative value from GlobalNations.db; fall back to stored − 1
            if live is not None:
                new_turns = int(live["beige_turns"])
            else:
                new_turns = max(0, int(alert.get("beige_turns") or 0) - 1)

            if new_turns <= 0:
                to_delete.append(int(alert["id"]))
                continue

            # Recalculate projected_loot from current holdings
            fresh_loot = float(alert.get("projected_loot") or 0)
            h = holdings_map.get(nid)
            if h and _LM:
                def_policy = str((live or {}).get("war_policy") or "").lower()
                if "." in def_policy:
                    def_policy = def_policy.rsplit(".", 1)[-1]
                bp  = _LM["war_type"]["raid"]
                off = _LM["offense"]["pirate"] * _LM["offense"]["ape"]
                dfn = _LM["defense"].get(def_policy, 1.0)
                pct = bp * off * dfn
                cash    = max(0.0, float(h.get("money_held") or 0)) * pct
                rss_val = sum(
                    max(0.0, float(h.get(f"{r}_held") or 0)) * pct * prices.get(r, 0)
                    for r in _RES
                )
                fresh_loot = cash + rss_val

            to_update.append((new_turns, fresh_loot, int(alert["id"])))

        try:
            await _batch_update(to_update, to_delete)
        except Exception as e:
            logger.warning(f"TurnRevenueLoop._update_beige_alerts: DB write failed — {e}")
            return

        logger.info(
            f"TurnRevenueLoop: beige alerts updated — "
            f"{len(to_update)} updated, {len(to_delete)} expired/removed"
        )

    # ── Turn processing ───────────────────────────────────────────────────────

    async def _process_turn(self, turn_date: str, active_war_ids: Optional[Set[int]] = None):
        """
        Apply one turn of revenue to all nations in GlobalNationsDB.

        Parameters
        ----------
        turn_date      : ISO timestamp string for this turn (used as last_revenue_date)
        active_war_ids : Pre-built war set.  If None, builds it fresh (normal path).
                         Pass an existing set during catch-up to avoid redundant queries.
        """
        logger.info(f"TurnRevenueLoop: processing turn {turn_date}")

        ctx = await self._fetch_game_context()
        if ctx is None:
            if self._last_game_ctx is not None:
                logger.warning(
                    "TurnRevenueLoop: game context unavailable from reaper.db — "
                    "using cached context from previous turn"
                )
                ctx = self._last_game_ctx
            else:
                logger.error(
                    "TurnRevenueLoop: skipping turn — could not load game context "
                    "from reaper.db and no cache available"
                )
                return
        else:
            self._last_game_ctx = ctx

        # Build the complete active-war set if not supplied by the caller
        if active_war_ids is None:
            active_war_ids = await self._build_active_war_ids()
            logger.info(
                f"TurnRevenueLoop: {len(active_war_ids)} nations currently at war "
                f"(IRSWarsDB + GlobalNationsDB snapshot)"
            )

        # ── Bulk-load all nations + cities in two queries ─────────────────────
        # This avoids N individual DB round-trips (one per nation) and keeps the
        # asyncio lock held for the minimum possible time.
        try:
            loop = asyncio.get_event_loop()
            nations_and_cities = await loop.run_in_executor(
                None, self._load_all_nations_and_cities_sync
            )
        except Exception as e:
            logger.error(f"TurnRevenueLoop: failed to load nations+cities: {e}")
            return

        nations_map, cities_map = nations_and_cities
        nation_ids = list(nations_map.keys())
        logger.info(f"TurnRevenueLoop: applying revenue to {len(nation_ids)} nations")

        # ── Calculate revenue for all nations (CPU-bound, no I/O) ─────────────
        from Systems.PnW.Util.rev_correct import revenue_calc_sync

        revenue_rows: List[tuple] = []  # (nation_id, money_delta, {rss: delta})
        applied = 0
        skipped = 0

        BATCH = 200
        for i in range(0, len(nation_ids), BATCH):
            batch = nation_ids[i : i + BATCH]
            for nid in batch:
                nation = nations_map[nid]
                # Skip vacation mode
                if int(nation.get("vacation_mode_turns") or 0) > 0:
                    skipped += 1
                    continue
                cities = cities_map.get(nid)
                if not cities:
                    skipped += 1
                    continue
                nation["cities"] = cities
                is_war = nid in active_war_ids
                try:
                    rev = revenue_calc_sync(
                        nation=nation,
                        radiation=ctx["radiation"],
                        treasures=ctx["treasures"],
                        prices=ctx["prices"],
                        colors=ctx["colors"],
                        seasonal_mod=ctx["seasonal_mod"],
                        build=None,
                        single_city=False,
                        include_spies=True,
                        is_war=is_war,
                    )
                    if rev:
                        money_delta = float(rev.get("net_cash_num") or 0)
                        rss_deltas  = {r: float(rev.get(r) or 0) for r in _RESOURCE_COLS}
                        revenue_rows.append((nid, money_delta, rss_deltas))
                        applied += 1
                    else:
                        skipped += 1
                except Exception as e:
                    logger.error(f"TurnRevenueLoop: revenue_calc nation {nid}: {e}")
                    skipped += 1
            # Yield between calculation batches so subscriptions stay responsive
            await asyncio.sleep(0)

        # ── Bulk-write all revenue in a single transaction ────────────────────
        if revenue_rows:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    self._apply_revenue_bulk_sync,
                    revenue_rows,
                    turn_date,
                )
            except Exception as e:
                logger.error(f"TurnRevenueLoop: bulk revenue write failed: {e}", exc_info=True)

        logger.info(
            f"TurnRevenueLoop: turn {turn_date} complete — "
            f"{applied} applied, {skipped} skipped/failed"
        )

        # ── Decrement beige_turns + refresh projected_loot in alerts.db ──────
        try:
            await self._update_beige_alerts_for_turn(ctx)
        except Exception as e:
            logger.error(f"TurnRevenueLoop: beige alert update failed: {e}", exc_info=True)

    def _load_all_nations_and_cities_sync(self):
        """
        Load all nations and cities from GlobalNations.db in two queries.
        Runs in a thread-pool executor — never blocks the event loop.
        Returns (nations_map: {id: dict}, cities_map: {id: [city_dict]}).
        """
        import sqlite3 as _sq
        from Systems.Functions.db_paths import GLOBAL_NATIONS_DB_STR
        nations_map: Dict[int, Dict[str, Any]] = {}
        cities_map:  Dict[int, List[Dict[str, Any]]] = {}
        try:
            conn = _sq.connect(GLOBAL_NATIONS_DB_STR, timeout=30)
            conn.row_factory = _sq.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            # Nations — exclude rows with no name (skeleton rows)
            for row in conn.execute(
                "SELECT * FROM nations WHERE nation_name IS NOT NULL AND nation_name != ''"
            ).fetchall():
                d = dict(row)
                nations_map[int(d["id"])] = d
            # Cities — all at once
            for row in conn.execute("SELECT * FROM cities").fetchall():
                d = dict(row)
                nid = int(d.get("nation_id") or 0)
                if nid:
                    cities_map.setdefault(nid, []).append(d)
            conn.close()
        except Exception as e:
            logger.error(f"TurnRevenueLoop._load_all_nations_and_cities_sync: {e}", exc_info=True)
        return nations_map, cities_map

    def _apply_revenue_bulk_sync(
        self,
        revenue_rows: List[tuple],  # (nation_id, money_delta, {rss: delta})
        turn_date: str,
    ):
        """
        Write all turn revenue in a single SQLite transaction.
        Runs in a thread-pool executor — never blocks the event loop.

        Uses a single UPDATE per nation with all resource columns in one
        statement to minimise round-trips and lock contention.
        """
        import sqlite3 as _sq
        from Systems.Functions.db_paths import GLOBAL_NATIONS_DB_STR

        try:
            conn = _sq.connect(GLOBAL_NATIONS_DB_STR, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("PRAGMA wal_autocheckpoint=1000")

            with conn:  # auto-commit / rollback
                for nid, money_delta, rss_deltas in revenue_rows:
                    # Build a single UPDATE covering money + all non-zero resources.
                    # last_revenue_date is ALWAYS updated — even if all deltas are zero
                    # (e.g. a nation with no production) — so the catch-up logic doesn't
                    # replay this turn on the next startup.
                    parts = [
                        "money=MAX(0, COALESCE(money,0)+?)",
                        "confidence=CASE WHEN confidence='seeded' THEN 'tracked' ELSE confidence END",
                        "last_revenue_date=?",
                        "last_event_date=?",
                    ]
                    vals: List[Any] = [money_delta, turn_date, turn_date]

                    for r, v in rss_deltas.items():
                        if v != 0 and r in _RESOURCE_COLS:
                            parts.append(f"{r}=MAX(0,COALESCE({r},0)+?)")
                            vals.append(v)

                    vals.append(nid)
                    conn.execute(
                        f"UPDATE nations SET {', '.join(parts)} WHERE id=?",
                        vals,
                    )
            conn.close()
        except Exception as e:
            logger.error(f"TurnRevenueLoop._apply_revenue_bulk_sync: {e}", exc_info=True)
            raise

    # ── Missed-turn catch-up ──────────────────────────────────────────────────

    async def _get_last_revenue_time(self) -> Optional[datetime]:
        """
        Read the most-recent last_revenue_date across all nations in GlobalNationsDB.
        Returns a UTC-aware datetime, or None if no revenue has ever been applied.
        """
        loop = asyncio.get_event_loop()
        def _query():
            try:
                import sqlite3 as _sq
                from Systems.Functions.db_paths import GLOBAL_NATIONS_DB_STR
                with _sq.connect(GLOBAL_NATIONS_DB_STR, timeout=15) as conn:
                    conn.execute("PRAGMA busy_timeout=15000")
                    row = conn.execute(
                        "SELECT MAX(last_revenue_date) FROM nations "
                        "WHERE last_revenue_date IS NOT NULL"
                    ).fetchone()
                if row and row[0]:
                    dt = datetime.fromisoformat(str(row[0]).replace(" ", "T"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
            except Exception as e:
                logger.warning(f"TurnRevenueLoop: could not read last_revenue_date: {e}")
            return None
        return await loop.run_in_executor(None, _query)

    async def _catchup(self):
        """
        On startup, detect and replay any turns missed while the harvester was down.

        Strategy:
          - Find the most-recent last_revenue_date in GlobalNationsDB.
          - Compute all turn boundaries between that time and now.
          - Replay up to MAX_CATCHUP_TURNS of them in order.
          - Build the active-war set once and reuse it for all catch-up turns
            (war status at the time of catch-up is the best we can do).
        """
        now = datetime.now(timezone.utc)
        last_rev = await self._get_last_revenue_time()

        if last_rev is None:
            logger.info("TurnRevenueLoop: no prior revenue found — skipping catch-up")
            return

        missed = _missed_turn_boundaries(last_rev, now)
        if not missed:
            logger.info("TurnRevenueLoop: no missed turns to catch up")
            return

        if len(missed) > MAX_CATCHUP_TURNS:
            logger.warning(
                f"TurnRevenueLoop: {len(missed)} missed turns detected — "
                f"capping catch-up at {MAX_CATCHUP_TURNS} (last {MAX_CATCHUP_TURNS} turns)"
            )
            missed = missed[-MAX_CATCHUP_TURNS:]

        logger.info(
            f"TurnRevenueLoop: catching up {len(missed)} missed turn(s) "
            f"(last revenue: {last_rev.strftime('%Y-%m-%d %H:%M UTC')})"
        )

        # Build war set once for the entire catch-up batch
        active_war_ids = await self._build_active_war_ids()

        for boundary in missed:
            turn_date = boundary.strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"TurnRevenueLoop: catch-up turn {turn_date}")
            try:
                await self._process_turn(turn_date, active_war_ids=active_war_ids)
            except Exception as e:
                logger.error(
                    f"TurnRevenueLoop: catch-up turn {turn_date} failed: {e}",
                    exc_info=True,
                )
            # Small yield between catch-up turns
            await asyncio.sleep(0)

        logger.info("TurnRevenueLoop: catch-up complete")

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def _loop(self):
        """Run catch-up, then sleep until each turn boundary and process it."""
        logger.info("TurnRevenueLoop started")

        # Replay any turns missed while the harvester was offline
        try:
            await self._catchup()
        except Exception as e:
            logger.error(f"TurnRevenueLoop: catch-up failed: {e}", exc_info=True)

        while self.running:
            now = datetime.now(timezone.utc)
            next_turn = _next_turn_dt(now)
            wait = _seconds_until(next_turn, now)
            logger.info(
                f"TurnRevenueLoop: next turn at "
                f"{next_turn.strftime('%Y-%m-%d %H:%M UTC')} "
                f"(in {wait / 60:.1f} min)"
            )
            # Sleep in short chunks so we can respond to self.running=False
            # without being stuck for up to 2 hours.
            elapsed = 0.0
            while elapsed < wait and self.running:
                chunk = min(30.0, wait - elapsed)
                try:
                    await asyncio.sleep(chunk)
                except asyncio.CancelledError:
                    return
                elapsed += chunk

            if not self.running:
                break

            turn_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            try:
                # Shield _process_turn so that an external task cancellation
                # (e.g. from the shutdown watcher) does not interrupt a turn
                # mid-write.  The shield lets the turn complete; the outer
                # CancelledError is re-raised after it finishes so the loop
                # exits cleanly.
                await asyncio.shield(self._process_turn(turn_date))
            except asyncio.CancelledError:
                # Turn completed (shield absorbed the cancel); now exit cleanly.
                logger.info("TurnRevenueLoop: cancelled after turn completed")
                return
            except Exception as e:
                logger.error(
                    f"TurnRevenueLoop: unhandled error in _process_turn: {e}",
                    exc_info=True,
                )

        logger.info("TurnRevenueLoop stopped")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self):
        if self.running:
            logger.warning("TurnRevenueLoop already running")
            return
        self.running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("TurnRevenueLoop stopped")
