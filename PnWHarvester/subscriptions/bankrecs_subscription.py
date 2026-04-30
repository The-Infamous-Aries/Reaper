"""
BankrecsSubscription

Unfiltered WebSocket subscription for ALL bank records in the game.

Listens to:
  - bankrec/create — every bank transfer in the game

On every event, updates HoldingsDB immediately:
  - Receiver (receiver_type=1): ADD cash + resources to their holdings.
  - Sender   (sender_type=1):   SUBTRACT cash + resources from their holdings.

bankrecs.db is populated separately by scripts/seed_holdings.py --bankrecs.
This subscription only cares about keeping holdings.db current in real time.
"""

import asyncio
import logging
from collections import deque
from typing import Any, Dict

from pnwkit.new import QueryKit
from pnwkit import errors as pnwkit_errors

logger = logging.getLogger(__name__)


def _obj_to_dict(obj: Any) -> Dict[str, Any]:
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return dict(obj)
    return vars(obj)


class BankrecsSubscription:
    def __init__(self, api_key: str, holdings_db=None):
        """
        api_key     : PnW API v3 key
        holdings_db : HoldingsDB — updated immediately on every bankrec/create event
        """
        self.holdings_db = holdings_db
        self.api_key     = api_key
        self.kit         = QueryKit(api_key)
        self.running     = False
        self._tasks: list[asyncio.Task] = []

        # Dedup ring — prevents double-applying if the subscription fires duplicates
        self._processed_ids: deque = deque(maxlen=5000)

    # ── bankrec/create ────────────────────────────────────────────────────────

    async def _listen_bankrec_creates(self):
        try:
            subscription = await self.kit.subscribe("bankrec", "create")
            logger.info("bankrec/create subscription active")

            applied_count = 0

            async for event in subscription:
                if not self.running:
                    break
                try:
                    rec    = _obj_to_dict(event)
                    rec_id = rec.get("id")
                    if not rec_id or rec_id in self._processed_ids:
                        continue
                    self._processed_ids.append(rec_id)

                    # Normalise date
                    date_val = rec.get("date")
                    if date_val is not None:
                        rec["date"] = str(date_val).replace("T", " ")

                    # Only update holdings for nation-type parties (type=1)
                    sid   = rec.get("sender_id")
                    stype = int(rec.get("sender_type") or 0)
                    rid   = rec.get("receiver_id")
                    rtype = int(rec.get("receiver_type") or 0)

                    has_nation_party = (rid and rtype == 1) or (sid and stype == 1)

                    if has_nation_party and self.holdings_db:
                        await self.holdings_db.apply_bankrec(rec)
                        applied_count += 1
                        # Build a compact summary of what was transferred
                        _RESOURCES = ("coal","oil","uranium","iron","bauxite","lead",
                                      "gasoline","munitions","steel","aluminum","food")
                        rss_parts = [
                            f"{r}={float(rec.get(r) or 0):,.2f}"
                            for r in _RESOURCES
                            if float(rec.get(r) or 0) != 0
                        ]
                        rss_str = " ".join(rss_parts) if rss_parts else "no resources"
                        logger.info(
                            f"Holdings: bankrec {rec_id} applied "
                            f"(sender={sid}/{stype} → receiver={rid}/{rtype}) "
                            f"money=${float(rec.get('money') or 0):,.0f} {rss_str} "
                            f"[session total: {applied_count}]"
                        )
                    else:
                        logger.debug(
                            f"bankrec/create → skipped rec {rec_id} "
                            f"(no nation-type party)"
                        )

                except Exception as e:
                    logger.error(f"bankrec/create event error: {e}", exc_info=True)

        except asyncio.CancelledError:
            logger.info("bankrec/create listener cancelled")
            raise
        except Exception as e:
            logger.error(f"bankrec/create subscription crashed: {e}", exc_info=True)
            raise

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self):
        if self.running:
            logger.warning("BankrecsSubscription already running")
            return
        self.running = True
        logger.info("Starting BankrecsSubscription")
        self._tasks = [
            asyncio.create_task(self._listen_bankrec_creates()),
        ]
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def stop(self):
        self.running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("BankrecsSubscription stopped")

    async def run_forever(self):
        """Run indefinitely, restarting on disconnects or crashes."""
        while True:
            try:
                await self.start()
            except asyncio.CancelledError:
                logger.info("BankrecsSubscription cancelled")
                break
            except pnwkit_errors.NoReconnect as e:
                logger.warning(f"BankrecsSubscription disconnected ({e}) — restarting in 30s")
            except Exception as e:
                logger.error(f"BankrecsSubscription crashed ({e}) — restarting in 30s", exc_info=True)
            finally:
                self.running = False
                await self.stop()

            await asyncio.sleep(30)
