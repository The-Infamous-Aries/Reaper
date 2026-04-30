"""
TurnRevenueLoop

Fires at every PnW turn boundary (midnight UTC, then every 2 hours) and
credits each tracked nation's holdings with one turn of net revenue using
our own revenue_calc formulas — NOT the GNI field from the API.

Turn schedule (UTC):
  00:00, 02:00, 04:00, 06:00, 08:00, 10:00, 12:00,
  14:00, 16:00, 18:00, 20:00, 22:00

What gets applied per nation per turn:
  money_held  += net_cash_num   (cash income minus all upkeep; can be negative)
  <rss>_held  += net <rss> production (floored at 0 in HoldingsDB.apply_turn_revenue)

Game context (colors, prices, treasures, radiation, seasonal_mod) is fetched
once per turn from the PnW API and reused for all nations — same caching
strategy as the Discord bot's revenue command.

Nations that have no city data in GlobalNationsDB are skipped silently.
Nations on vacation mode (vacation_mode_turns > 0) are skipped — they
produce no income.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# PnW turn length in seconds (2 hours)
TURN_SECONDS = 7200

# Resources tracked in holdings (must match RESOURCE_COLS in holdings_db.py)
_RESOURCE_COLS = (
    "coal", "oil", "uranium", "iron", "bauxite", "lead",
    "gasoline", "munitions", "steel", "aluminum", "food",
)


def _next_turn_dt(now: datetime) -> datetime:
    """Return the next UTC turn boundary (00:00, 02:00, 04:00, … 22:00)."""
    # Turns fire at even hours UTC
    hour = now.hour
    next_hour = ((hour // 2) + 1) * 2
    if next_hour >= 24:
        # Roll over to midnight next day
        base = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    else:
        base = now.replace(hour=next_hour, minute=0, second=0, microsecond=0)
    return base


def _seconds_until(target: datetime, now: datetime) -> float:
    delta = (target - now).total_seconds()
    return max(delta, 0.0)


class TurnRevenueLoop:
    """
    Standalone asyncio task that applies turn revenue to all tracked nations.

    Parameters
    ----------
    holdings_db   : HoldingsDB instance
    global_db     : GlobalNationsDB instance (for nation + city data)
    query_instance: V3GraphQuery instance (for game context API calls)
    """

    def __init__(self, holdings_db, global_db, query_instance):
        self.holdings_db    = holdings_db
        self.global_db      = global_db
        self.query_instance = query_instance
        self.running        = False
        self._task: Optional[asyncio.Task] = None

    # ── Game context fetch ────────────────────────────────────────────────────

    async def _fetch_game_context(self) -> Optional[Dict[str, Any]]:
        """
        Fetch colors, prices, treasures, radiation, seasonal_mod from the PnW API.
        Returns a dict with those keys, or None on failure.
        """
        query = (
            "{colors{color turn_bonus} "
            "game_info{game_date radiation{"
            "global north_america south_america africa europe asia australia antarctica"
            "}} "
            "tradeprices(first:1){data{"
            "coal oil uranium iron bauxite lead gasoline munitions steel aluminum food"
            "}} "
            "treasures{bonus nation{id alliance_id}}}"
        )
        try:
            raw = await self.query_instance._make_graphql_request(query, timeout=30)
            data = (raw or {}).get("data") or raw or {}

            # Colors
            colors: Dict[str, float] = {}
            for c in (data.get("colors") or []):
                colors[c["color"]] = float(c.get("turn_bonus") or 0)

            # Prices
            prices_list = ((data.get("tradeprices") or {}).get("data") or [{}])
            prices: Dict[str, float] = dict(prices_list[0]) if prices_list else {}
            prices["money"] = 1.0

            # Treasures
            treasures: List[Dict[str, Any]] = data.get("treasures") or []

            # Radiation
            game_info = data.get("game_info") or {}
            rad = game_info.get("radiation") or {}
            g = float(rad.get("global") or 0)
            radiation: Dict[str, float] = {
                "na": (float(rad.get("north_america") or 0) + g) / -1000,
                "sa": (float(rad.get("south_america") or 0) + g) / -1000,
                "eu": (float(rad.get("europe")        or 0) + g) / -1000,
                "as": (float(rad.get("asia")          or 0) + g) / -1000,
                "af": (float(rad.get("africa")        or 0) + g) / -1000,
                "au": (float(rad.get("australia")     or 0) + g) / -1000,
                "an": (float(rad.get("antarctica")    or 0) + g) / -1000,
            }

            # Seasonal modifiers
            game_date = game_info.get("game_date") or ""
            try:
                month = int(game_date[5:7])
            except (ValueError, IndexError):
                month = 1
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

            return {
                "colors":       colors,
                "prices":       prices,
                "treasures":    treasures,
                "radiation":    radiation,
                "seasonal_mod": seasonal_mod,
            }
        except Exception as e:
            logger.error(f"TurnRevenueLoop: failed to fetch game context: {e}", exc_info=True)
            return None

    # ── Per-nation revenue calculation ────────────────────────────────────────

    async def _calc_and_apply_nation(
        self,
        nation_id: int,
        ctx: Dict[str, Any],
        turn_date: str,
    ) -> bool:
        """
        Fetch nation + cities from GlobalNationsDB, run revenue_calc,
        and apply the result to holdings.
        """
        try:
            nation = await self.global_db.get_nation(nation_id)
            if not nation:
                return False

            # Skip nations on vacation mode — they earn nothing
            if int(nation.get("vacation_mode_turns") or 0) > 0:
                return False

            # Skip nations with no cities recorded
            cities = await self.global_db.get_cities_for_nation(nation_id)
            if not cities:
                return False

            # Attach cities list to nation dict (revenue_calc expects nation['cities'])
            nation["cities"] = cities

            # Import here to avoid circular imports at module load time
            from Systems.PnW.Util.rev_correct import revenue_calc

            rev = await revenue_calc(
                message=None,
                nation=nation,
                radiation=ctx["radiation"],
                treasures=ctx["treasures"],
                prices=ctx["prices"],
                colors=ctx["colors"],
                seasonal_mod=ctx["seasonal_mod"],
                build=None,
                single_city=False,
                include_spies=True,
                is_war=None,
            )

            if not rev:
                return False

            # net_cash_num = cash income minus all upkeep (can be negative)
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

    # ── Turn processing ───────────────────────────────────────────────────────

    async def _process_turn(self, turn_date: str):
        """Apply one turn of revenue to all tracked nations."""
        logger.info(f"TurnRevenueLoop: processing turn {turn_date}")

        ctx = await self._fetch_game_context()
        if ctx is None:
            logger.error("TurnRevenueLoop: skipping turn — could not fetch game context")
            return

        nation_ids = await self.holdings_db.get_all_tracked_nation_ids()
        if not nation_ids:
            logger.info("TurnRevenueLoop: no tracked nations — nothing to do")
            return

        logger.info(f"TurnRevenueLoop: applying revenue to {len(nation_ids)} nations")

        applied = 0
        skipped = 0
        # Process in small batches to avoid hammering the DB
        batch_size = 50
        for i in range(0, len(nation_ids), batch_size):
            batch = nation_ids[i : i + batch_size]
            results = await asyncio.gather(
                *[self._calc_and_apply_nation(nid, ctx, turn_date) for nid in batch],
                return_exceptions=True,
            )
            for r in results:
                if r is True:
                    applied += 1
                else:
                    skipped += 1
            # Tiny yield between batches so we don't starve other tasks
            await asyncio.sleep(0)

        logger.info(
            f"TurnRevenueLoop: turn {turn_date} complete — "
            f"{applied} applied, {skipped} skipped/failed"
        )

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def _loop(self):
        """Sleep until the next turn boundary, then process, repeat forever."""
        logger.info("TurnRevenueLoop started — waiting for first turn boundary")
        while self.running:
            now  = datetime.now(timezone.utc)
            next_turn = _next_turn_dt(now)
            wait = _seconds_until(next_turn, now)
            logger.info(
                f"TurnRevenueLoop: next turn at {next_turn.strftime('%Y-%m-%d %H:%M UTC')} "
                f"(in {wait/60:.1f} min)"
            )
            try:
                await asyncio.sleep(wait)
            except asyncio.CancelledError:
                break

            if not self.running:
                break

            turn_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            try:
                await self._process_turn(turn_date)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"TurnRevenueLoop: unhandled error in _process_turn: {e}", exc_info=True)

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
