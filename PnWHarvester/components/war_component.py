"""
WarComponent — GPP component for war and attack event processing.

Sub-components:
- WarEventProcessor: Handles war/create, war/update events
- AttackEventProcessor: Handles warattack/create events
- WarCacheManager: In-memory war cache for fast lookups
- HoldingsUpdater: Updates HoldingsDB on ground-win attacks
- WarNewsGenerator: Generates news events for war activities
- BeigeManager: Manages beige state updates
- WarStatsUpdater: Updates war statistics

This component writes to IRSWarsDB, HoldingsDB, and GlobalNationsDB.
"""

import asyncio
import logging
from collections import deque, defaultdict
from typing import Any, Dict, List, Optional

import aiohttp
from pnwkit.new import QueryKit

logger = logging.getLogger(__name__)

IRS_ALLIANCE_ID = 14225
EP_ALLIANCE_ID = IRS_ALLIANCE_ID

_RESOURCES = (
    "coal", "oil", "uranium", "iron", "bauxite", "lead",
    "gasoline", "munitions", "steel", "aluminum", "food",
)


def _clean_aname(name: Any) -> Optional[str]:
    """Return None if name is falsy or the PnW '0' placeholder, else return name."""
    return name if (name and name != '0') else None


def _norm(val: Any) -> str:
    """Normalise an enum/string value to lowercase plain string."""
    if val is None:
        return ""
    s = str(val)
    if "." in s:
        s = s.rsplit(".", 1)[-1]
    return s.lower()


def _obj_to_dict(obj: Any) -> Dict[str, Any]:
    """Convert objects to dictionaries safely."""
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return dict(obj)
    return vars(obj)


def _has_loot(attack: Dict[str, Any]) -> bool:
    if float(attack.get("money_stolen") or attack.get("money_looted") or 0) > 0:
        return True
    return any(float(attack.get(f"{r}_looted") or 0) > 0 for r in _RESOURCES)


def _is_win_attack(attack: Dict[str, Any]) -> bool:
    """Attacker won the ground battle and looted the defender."""
    victor = attack.get("victor")
    att_id = attack.get("att_id") or attack.get("attacker_id")
    if victor is None or att_id is None:
        return _has_loot(attack)
    return str(victor) == str(att_id) and _has_loot(attack)


class WarCacheManager:
    """Manages in-memory war cache for fast lookups during attack processing."""
    
    def __init__(self, max_size: int = 5000):
        self._war_cache: Dict[int, Dict[str, Any]] = {}
        self._war_cache_maxsize = max_size
    
    def cache_war(self, war_data: Dict[str, Any]):
        """Store war context in memory."""
        war_id = war_data.get("id")
        if not war_id:
            return
        war_id = int(war_id)

        att_obj = war_data.get("attacker") or {}
        def_obj = war_data.get("defender") or {}
        if not isinstance(att_obj, dict):
            att_obj = {}
        if not isinstance(def_obj, dict):
            def_obj = {}

        att_name = (
            att_obj.get("nation_name")
            or war_data.get("att_nation_name")
        )
        def_name = (
            def_obj.get("nation_name")
            or war_data.get("def_nation_name")
        )

        self._war_cache[war_id] = {
            "id": war_id,
            "att_id": war_data.get("att_id"),
            "def_id": war_data.get("def_id"),
            "att_alliance_id": war_data.get("att_alliance_id"),
            "def_alliance_id": war_data.get("def_alliance_id"),
            "att_nation_name": att_name,
            "def_nation_name": def_name,
            "att_alliance_name": _clean_aname(
                (att_obj.get("alliance") or {}).get("name")
                if isinstance(att_obj.get("alliance"), dict)
                else war_data.get("att_alliance_name")
            ),
            "def_alliance_name": _clean_aname(
                (def_obj.get("alliance") or {}).get("name")
                if isinstance(def_obj.get("alliance"), dict)
                else war_data.get("def_alliance_name")
            ),
            "att_alliance_flag": (
                (att_obj.get("alliance") or {}).get("flag")
                if isinstance(att_obj.get("alliance"), dict)
                else war_data.get("att_alliance_flag")
            ),
            "def_alliance_flag": (
                (def_obj.get("alliance") or {}).get("flag")
                if isinstance(def_obj.get("alliance"), dict)
                else war_data.get("def_alliance_flag")
            ),
            "att_nation_flag": att_obj.get("flag") or war_data.get("att_nation_flag"),
            "def_nation_flag": def_obj.get("flag") or war_data.get("def_nation_flag"),
            "war_type": _norm(war_data.get("war_type")),
            "att_war_policy": _norm(att_obj.get("war_policy") or war_data.get("att_war_policy")),
            "def_war_policy": _norm(def_obj.get("war_policy") or war_data.get("def_war_policy")),
            "att_has_ape": bool(att_obj.get("advanced_pirate_economy") or war_data.get("att_has_ape")),
        }

        if len(self._war_cache) > self._war_cache_maxsize:
            del self._war_cache[next(iter(self._war_cache))]
    
    def get_cached_war(self, war_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve war context from cache."""
        return self._war_cache.get(int(war_id))


class WarEventProcessor:
    """Processes war/create and war/update events."""
    
    def __init__(self, cache_manager: WarCacheManager, nw_db):
        self.cache_manager = cache_manager
        self.nw_db = nw_db
    
    def is_nw_war(self, war_data: Dict[str, Any]) -> bool:
        """Check if war involves the NW alliance."""
        aid = str(IRS_ALLIANCE_ID)
        return (
            str(war_data.get("att_alliance_id")) == aid
            or str(war_data.get("def_alliance_id")) == aid
        )
    
    async def process_war_create(self, war_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Process war/create event."""
        war_id = war_dict.get("id")
        if not war_id:
            return {"processed": False, "skipped": 1}
        
        self.cache_manager.cache_war(war_dict)
        
        if self.is_nw_war(war_dict) and self.nw_db:
            await self.nw_db.save_war(war_dict)
            logger.debug(f"war/create → {war_id} → IRSWars.db [NW]")
        
        return {"processed": True, "skipped": 0}
    
    async def process_war_update(self, war_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Process war/update event."""
        war_id = war_dict.get("id")
        if not war_id:
            return {"processed": False, "skipped": 1}
        
        self.cache_manager.cache_war(war_dict)
        
        if self.is_nw_war(war_dict) and self.nw_db:
            await self.nw_db.save_war(war_dict)
            logger.debug(f"war/update → {war_id} → IRSWars.db [NW]")
        
        return {"processed": True, "skipped": 0}


class HoldingsUpdater:
    """Updates HoldingsDB on ground-win attacks."""
    
    def __init__(self, holdings_db):
        self.holdings_db = holdings_db
    
    def _calc_loot_value(self, money_looted: float, resources_looted: Dict[str, float]) -> float:
        """Calculate total loot value using market prices."""
        _FALLBACK_PRICES = {
            "coal": 2000, "oil": 2000, "uranium": 4000, "iron": 2000,
            "bauxite": 2000, "lead": 2000, "gasoline": 3000, "munitions": 2000,
            "steel": 3000, "aluminum": 2000, "food": 150,
        }
        try:
            import sqlite3
            from Systems.Functions.db_paths import REAPER_DB_STR
            conn = sqlite3.connect(REAPER_DB_STR)
            rows = conn.execute(
                """
                SELECT resource, best_sell_price FROM resource_prices
                WHERE timestamp = (SELECT MAX(timestamp) FROM resource_prices)
                """
            ).fetchall()
            conn.close()
            price_map = {r.lower(): float(p) for r, p in rows if p and float(p) > 0} if rows else _FALLBACK_PRICES
        except Exception:
            price_map = _FALLBACK_PRICES

        resource_value = sum(
            amt * price_map.get(resource, _FALLBACK_PRICES.get(resource, 1000))
            for resource, amt in resources_looted.items()
            if amt > 0
        )
        return money_looted + resource_value
    
    async def update_holdings_for_attack(self, attack: Dict[str, Any], war_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update holdings for a ground-win attack."""
        if not self.holdings_db:
            return {"processed": False, "skipped": 1}
        
        if not _is_win_attack(attack):
            return {"processed": False, "skipped": 1}
        
        # Extract loot
        money_looted = float(attack.get("money_stolen") or attack.get("money_looted") or 0)
        resources_looted = {r: float(attack.get(f"{r}_looted") or 0) for r in _RESOURCES}
        
        # Determine attacker/defender
        att_id = attack.get("att_id") or attack.get("attacker_id")
        war_att_id = war_data.get("att_id")
        war_def_id = war_data.get("def_id")
        
        # Update holdings
        await self.holdings_db.apply_loot_event(
            attacker_id=int(war_att_id),
            defender_id=int(war_def_id),
            money_looted=money_looted,
            resources_looted=resources_looted,
            loot_date=attack.get("date"),
            war_type=war_data.get("war_type"),
            att_war_policy=war_data.get("att_war_policy"),
            def_war_policy=war_data.get("def_war_policy"),
            att_has_ape=war_data.get("att_has_ape", False),
            attacker_name=war_data.get("att_nation_name"),
            defender_name=war_data.get("def_nation_name"),
        )
        
        logger.debug(f"Holdings updated for attack {attack.get('id')}: att={war_att_id}, def={war_def_id}")
        
        return {"processed": True, "skipped": 0}


class AttackEventProcessor:
    """Processes warattack/create events."""
    
    def __init__(self, cache_manager: WarCacheManager, holdings_updater: HoldingsUpdater, nw_db):
        self.cache_manager = cache_manager
        self.holdings_updater = holdings_updater
        self.nw_db = nw_db
        self._attack_queue: deque = deque()
        self._processing_queue = False
    
    async def process_attack(self, attack_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Process a warattack/create event."""
        attack_id = attack_dict.get("id")
        war_id = attack_dict.get("war_id")
        
        if not attack_id or not war_id:
            return {"processed": False, "skipped": 1}
        
        war_data = self.cache_manager.get_cached_war(int(war_id))
        
        if not war_data:
            # Queue for later processing when war data arrives
            self._attack_queue.append(attack_dict)
            return {"processed": False, "skipped": 0, "status": "war_not_found_queued"}
        
        # Save attack to DB if NW war
        if self.nw_db:
            aid = str(IRS_ALLIANCE_ID)
            if (str(war_data.get("att_alliance_id")) == aid or
                str(war_data.get("def_alliance_id")) == aid):
                await self.nw_db.save_war_attack(attack_dict)
        
        # Update holdings on ground win
        if _is_win_attack(attack_dict):
            await self.holdings_updater.update_holdings_for_attack(attack_dict, war_data)
        
        logger.debug(f"Attack {attack_id} processed successfully")
        
        return {"processed": True, "skipped": 0}
    
    async def process_queued_attacks(self):
        """Process attacks that were queued waiting for war data."""
        if self._processing_queue:
            return
        
        self._processing_queue = True
        try:
            while self._attack_queue:
                attack = self._attack_queue.popleft()
                await self.process_attack(attack)
        finally:
            self._processing_queue = False


class WarComponent:
    """
    GPP component for war and attack event processing.
    
    Orchestrates the sub-components for processing war and attack events.
    Also manages WebSocket subscriptions for war and attack events.
    """
    
    def __init__(
        self,
        nw_db,
        holdings_db=None,
        global_nations_db=None,
        api_key: str = "",
    ):
        """
        Initialize the WarComponent.
        
        Args:
            nw_db: IRSWarsDB instance
            holdings_db: HoldingsDB instance (optional)
            global_nations_db: GlobalNationsDB instance (optional)
            api_key: PnW API v3 key
        """
        self.nw_db = nw_db
        self.holdings_db = holdings_db
        self.global_nations_db = global_nations_db
        self.api_key = api_key
        self.kit = QueryKit(api_key)
        
        # Sub-components
        self.cache_manager = WarCacheManager()
        self.war_processor = WarEventProcessor(self.cache_manager, nw_db)
        self.holdings_updater = HoldingsUpdater(holdings_db)
        self.attack_processor = AttackEventProcessor(
            self.cache_manager, self.holdings_updater, nw_db
        )
        
        # Subscription state
        self.running = False
        self._tasks: list[asyncio.Task] = []
        self._last_seen: Dict[str, float] = {}
    
    async def initialize(self):
        """Initialize the component."""
        logger.info("WarComponent initialized")
    
    async def process_war_create(self, event: Any) -> Dict[str, Any]:
        """Process a war/create event."""
        war_dict = _obj_to_dict(event)
        stats = await self.war_processor.process_war_create(war_dict)
        
        # Process queued attacks that may have been waiting for this war
        await self.attack_processor.process_queued_attacks()
        
        return stats
    
    async def process_war_update(self, event: Any) -> Dict[str, Any]:
        """Process a war/update event."""
        war_dict = _obj_to_dict(event)
        return await self.war_processor.process_war_update(war_dict)
    
    async def process_attack_create(self, event: Any) -> Dict[str, Any]:
        """Process a warattack/create event."""
        attack_dict = _obj_to_dict(event)
        return await self.attack_processor.process_attack(attack_dict)
    
    async def get_component_stats(self) -> Dict[str, Any]:
        """Get component statistics."""
        return {
            "type": "WarComponent",
            "cached_wars": len(self.cache_manager._war_cache),
            "queued_attacks": len(self.attack_processor._attack_queue),
            "nw_db_path": self.nw_db.db_path if self.nw_db else None,
            "holdings_db_path": self.holdings_db.db_path if self.holdings_db else None,
            "running": self.running,
        }
    
    # ── WebSocket subscription listeners ───────────────────────────────────────
    
    async def _listen_war_attacks(self):
        """Listen for warattack/create events."""
        try:
            subscription = await self.kit.subscribe("warattack", "create")
            logger.info("warattack/create subscription active")

            async for attack in subscription:
                if not self.running:
                    break
                try:
                    self._last_seen["warattack/create"] = __import__("time").monotonic()
                    await self.process_attack_create(attack)
                except Exception as e:
                    logger.error(f"warattack/create event error: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("warattack/create listener cancelled")
        except (ConnectionResetError, OSError, aiohttp.ClientError) as e:
            logger.warning(f"warattack/create WebSocket disconnected: {e} — will restart")
            raise
        except Exception as e:
            logger.error(f"warattack/create subscription crashed: {e}", exc_info=True)
            raise
    
    async def _listen_war_creates(self):
        """Listen for war/create events."""
        try:
            subscription = await self.kit.subscribe("war", "create")
            logger.info("war/create subscription active")

            async for war in subscription:
                if not self.running:
                    break
                try:
                    self._last_seen["war/create"] = __import__("time").monotonic()
                    await self.process_war_create(war)
                except Exception as e:
                    logger.error(f"war/create event error: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("war/create listener cancelled")
        except (ConnectionResetError, OSError, aiohttp.ClientError) as e:
            logger.warning(f"war/create WebSocket disconnected: {e} — will restart")
            raise
        except Exception as e:
            logger.error(f"war/create subscription crashed: {e}", exc_info=True)
            raise
    
    async def _listen_war_updates(self):
        """Listen for war/update events."""
        try:
            subscription = await self.kit.subscribe("war", "update")
            logger.info("war/update subscription active")

            async for war in subscription:
                if not self.running:
                    break
                try:
                    self._last_seen["war/update"] = __import__("time").monotonic()
                    await self.process_war_update(war)
                except Exception as e:
                    logger.error(f"war/update event error: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("war/update listener cancelled")
        except (ConnectionResetError, OSError, aiohttp.ClientError) as e:
            logger.warning(f"war/update WebSocket disconnected: {e} — will restart")
            raise
        except Exception as e:
            logger.error(f"war/update subscription crashed: {e}", exc_info=True)
            raise
    
    # ── Lifecycle ─────────────────────────────────────────────────────────────
    
    async def start(self):
        """Start all WebSocket subscriptions for war and attack events."""
        if self.running:
            logger.warning("WarComponent already running")
            return
        
        self.running = True
        logger.info("Starting WarComponent subscriptions")
        
        self._tasks = [
            asyncio.create_task(self._listen_war_attacks()),
            asyncio.create_task(self._listen_war_creates()),
            asyncio.create_task(self._listen_war_updates()),
        ]
        
        # Wait for the FIRST task to finish (any disconnect/crash triggers restart)
        done, pending = await asyncio.wait(
            self._tasks, return_when=asyncio.FIRST_COMPLETED
        )
        # Cancel all remaining listeners immediately
        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        # Re-raise the first exception
        for t in done:
            if t.exception():
                raise t.exception()
    
    async def stop(self):
        """Stop all subscriptions."""
        self.running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        
        # Close pnwkit socket
        await self._close_kit_socket()
        logger.info("WarComponent stopped")
    
    async def run_forever(self):
        """Run subscriptions indefinitely with automatic restart on disconnect/crash."""
        while True:
            try:
                await self.start()
            except asyncio.CancelledError:
                logger.info("WarComponent cancelled")
                break
            except (aiohttp.ClientError, ConnectionResetError, OSError) as e:
                logger.warning(f"WarComponent disconnected ({e}) — restarting in 30s")
            except Exception as e:
                logger.error(f"WarComponent crashed ({e}) — restarting in 30s", exc_info=True)
            finally:
                self.running = False
                await self.stop()
            
            await asyncio.sleep(30)
    
    async def _close_kit_socket(self):
        """Close the pnwkit socket to avoid pending task warnings."""
        socket = getattr(self.kit, "socket", None)
        if socket is None:
            return
        tasks_to_cancel = []
        for attr in ("task", "ping_pong_task"):
            t = getattr(socket, attr, None)
            if t is not None and not t.done():
                tasks_to_cancel.append(t)
                t.cancel()
        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        try:
            if not socket.closed:
                await socket.ws.close()
        except Exception:
            pass
        self.kit.socket = None
