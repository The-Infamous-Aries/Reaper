"""
GlobalWarsSubscription

Unfiltered WebSocket subscriptions for ALL wars in the game.

Behaviour:
  - war/create        → save NW wars to IRSWarsDB; all wars tracked in memory
  - war/update        → update NW wars in IRSWarsDB; update memory cache
  - warattack/create  → on every ground-win attack, update HoldingsDB immediately:
                          defender: SET holdings to back-calculated post-loot value
                          attacker: ADD looted amounts to their holdings

loot.db is populated separately by scripts/seed_holdings.py --war-wins.
This subscription only cares about keeping holdings.db current in real time.
"""

import asyncio
import logging
from collections import deque, defaultdict
from typing import Any, Dict, List, Optional

from pnwkit.new import QueryKit
from pnwkit import errors as pnwkit_errors

logger = logging.getLogger(__name__)

IRS_ALLIANCE_ID = 14225
EP_ALLIANCE_ID  = IRS_ALLIANCE_ID  # backward-compat alias

WAR_QUERY_FIELDS = (
    "id date end_date reason war_type ground_control air_superiority naval_blockade "
    "winner_id turns_left att_id def_id att_alliance_id att_alliance_position "
    "def_alliance_id def_alliance_position att_points def_points att_peace def_peace "
    "att_resistance def_resistance att_fortify def_fortify att_gas_used def_gas_used "
    "att_mun_used def_mun_used att_infra_destroyed def_infra_destroyed "
    "att_infra_destroyed_value def_infra_destroyed_value "
    "att_soldiers_lost def_soldiers_lost att_tanks_lost def_tanks_lost "
    "att_aircraft_lost def_aircraft_lost att_ships_lost def_ships_lost "
    "att_missiles_used def_missiles_used att_nukes_used def_nukes_used "
    "attacker { id nation_name leader_name war_policy advanced_pirate_economy alliance { name } } "
    "defender { id nation_name leader_name war_policy alliance { name } }"
)

ATTACK_QUERY_FIELDS = (
    "id date att_id def_id type war_id victor "
    "city_infra_before infra_destroyed infra_destroyed_value "
    "money_stolen money_destroyed military_salvage_aluminum military_salvage_steel "
    "att_missiles_lost def_missiles_lost att_nukes_lost def_nukes_lost "
    "improvements_destroyed "
    "money_looted coal_looted oil_looted uranium_looted iron_looted "
    "bauxite_looted lead_looted gasoline_looted munitions_looted "
    "steel_looted aluminum_looted food_looted"
)

_RESOURCES = (
    "coal", "oil", "uranium", "iron", "bauxite", "lead",
    "gasoline", "munitions", "steel", "aluminum", "food",
)


def _obj_to_dict(obj: Any) -> Dict[str, Any]:
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return dict(obj)
    return vars(obj)


def _has_loot(attack: Dict[str, Any]) -> bool:
    if float(attack.get("money_looted") or 0) > 0:
        return True
    return any(float(attack.get(f"{r}_looted") or 0) > 0 for r in _RESOURCES)


def _is_win_attack(attack: Dict[str, Any]) -> bool:
    """Attacker won the ground battle and looted the defender."""
    victor = attack.get("victor")
    att_id = attack.get("att_id") or attack.get("attacker_id")
    if victor is None or att_id is None:
        return _has_loot(attack)
    return str(victor) == str(att_id) and _has_loot(attack)


def _norm(val: Any) -> str:
    """Normalise an enum/string value to lowercase plain string."""
    if val is None:
        return ""
    s = str(val)
    if "." in s:
        s = s.rsplit(".", 1)[-1]
    return s.lower()


class GlobalWarsSubscription:
    def __init__(self, global_db, nw_db, query_instance, api_key: str, holdings_db=None):
        """
        global_db      : None (disabled)
        nw_db          : IRSWarsDB    — receives NW-only war/attack events
        query_instance : V3GraphQuery — for fetching war details by ID
        api_key        : PnW API v3 key
        holdings_db    : HoldingsDB   — updated on every ground-win attack
        """
        self.global_db      = None
        self.nw_db          = nw_db
        self.holdings_db    = holdings_db
        self.query_instance = query_instance
        self.api_key        = api_key
        self.kit            = QueryKit(api_key)
        self.running        = False
        self._listener_tasks: list[asyncio.Task] = []

        # Dedup rings
        self._processed_attack_ids: deque = deque(maxlen=2000)
        self._processed_war_ids:    deque = deque(maxlen=1000)

        # In-memory war cache — maps war_id → war context dict
        # Stores war_type, policies, and nation names needed for holdings updates
        self._war_cache: Dict[int, Dict[str, Any]] = {}
        self._war_cache_maxsize = 5000

        # Pending attacks whose parent war hasn't arrived yet
        self._pending_attacks: dict[int, list[Dict[str, Any]]] = defaultdict(list)

        # Rate limiting for API fallback fetches
        self._last_api_call = 0.0
        self._min_api_interval = 1.0
        self._rate_limit_backoff = 0.0

    # ── War cache ─────────────────────────────────────────────────────────────

    def _cache_war(self, war_data: Dict[str, Any]):
        """Store war context in memory. Extracts all fields needed for holdings."""
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

        self._war_cache[war_id] = {
            "id":              war_id,
            "att_id":          war_data.get("att_id"),
            "def_id":          war_data.get("def_id"),
            "att_alliance_id": war_data.get("att_alliance_id"),
            "def_alliance_id": war_data.get("def_alliance_id"),
            "att_nation_name": att_obj.get("nation_name") or war_data.get("att_nation_name"),
            "def_nation_name": def_obj.get("nation_name") or war_data.get("def_nation_name"),
            # These three are critical for correct loot % in holdings
            "war_type":        _norm(war_data.get("war_type")),
            "att_war_policy":  _norm(att_obj.get("war_policy") or war_data.get("att_war_policy")),
            "def_war_policy":  _norm(def_obj.get("war_policy") or war_data.get("def_war_policy")),
            "att_has_ape":     bool(att_obj.get("advanced_pirate_economy")),
        }

        if len(self._war_cache) > self._war_cache_maxsize:
            del self._war_cache[next(iter(self._war_cache))]

    def _get_cached_war(self, war_id: int) -> Optional[Dict[str, Any]]:
        return self._war_cache.get(int(war_id))

    # ── API fallback ──────────────────────────────────────────────────────────

    async def _rate_limit_wait(self):
        import time
        now = time.time()
        if now < self._rate_limit_backoff:
            await asyncio.sleep(self._rate_limit_backoff - now)
            return
        elapsed = now - self._last_api_call
        if elapsed < self._min_api_interval:
            await asyncio.sleep(self._min_api_interval - elapsed)
        self._last_api_call = time.time()

    async def _fetch_war_from_api(self, war_id: int) -> Optional[Dict[str, Any]]:
        await self._rate_limit_wait()
        query = (
            f"query {{\n"
            f"  wars(id: [{war_id}], first: 1) {{\n"
            f"    data {{ {WAR_QUERY_FIELDS} }}\n"
            f"  }}\n"
            f"}}"
        )
        try:
            raw  = await self.query_instance._make_graphql_request(query, timeout=45)
            wars = ((raw or {}).get("wars") or {}).get("data") or []
            if wars:
                return wars[0] if isinstance(wars[0], dict) else _obj_to_dict(wars[0])
        except Exception as e:
            if "429" in str(e) or "Too Many Requests" in str(e):
                import time
                self._rate_limit_backoff = time.time() + 60
                logger.warning(f"Rate limited fetching war {war_id} — backing off 60s")
                raise
            if "403" in str(e):
                raise
            logger.debug(f"API fetch failed for war {war_id}: {e}")
        return None

    async def _fetch_war(self, war_id: int) -> Optional[Dict[str, Any]]:
        """NW DB → memory cache → API."""
        nw = await self.nw_db.get_war(war_id)
        if nw:
            return nw
        cached = self._get_cached_war(war_id)
        if cached:
            return cached
        data = await self._fetch_war_from_api(war_id)
        if data:
            self._cache_war(data)
            if self._is_nw_war(data):
                await self.nw_db.save_war(data)
        return data

    # ── Routing helpers ───────────────────────────────────────────────────────

    def _is_nw_war(self, war_data: Dict[str, Any]) -> bool:
        aid = str(IRS_ALLIANCE_ID)
        return (
            str(war_data.get("att_alliance_id")) == aid
            or str(war_data.get("def_alliance_id")) == aid
        )

    async def _save_war_nw(self, war_data: Dict[str, Any]):
        """Cache in memory always; save to IRSWars only if NW war."""
        self._cache_war(war_data)
        if self._is_nw_war(war_data):
            await self.nw_db.save_war(war_data)
            logger.info(f"War {war_data.get('id')} saved to IRSWars (NW war)")
        else:
            logger.debug(f"War {war_data.get('id')} cached in memory (non-NW)")

    async def _save_attack_nw(self, attack_data: Dict[str, Any], war_data: Dict[str, Any]):
        if self._is_nw_war(war_data):
            await self.nw_db.save_war_attack(attack_data)
            logger.debug(f"Attack {attack_data.get('id')} saved to IRSWars")

    # ── Holdings update on win attack ─────────────────────────────────────────

    async def _apply_win_to_holdings(
        self,
        attack_data: Dict[str, Any],
        war_data: Dict[str, Any],
    ):
        """
        On a ground-win attack, update holdings for both attacker and defender.

        Uses war_type + policies from the war cache for the correct loot %.
        Defender: SET holdings to back-calculated post-loot value (fresh baseline).
        Attacker: ADD looted amounts to their holdings.
        """
        if not self.holdings_db or not _is_win_attack(attack_data):
            return

        att_id = int(attack_data.get("att_id") or attack_data.get("attacker_id") or 0)
        def_id = int(attack_data.get("def_id") or attack_data.get("defender_id") or 0)
        if not att_id or not def_id:
            return

        loot_date      = str(attack_data.get("date") or "")
        war_type       = _norm(war_data.get("war_type", ""))
        att_war_policy = _norm(war_data.get("att_war_policy", ""))
        def_war_policy = _norm(war_data.get("def_war_policy", ""))
        att_has_ape    = bool(war_data.get("att_has_ape", False))
        att_name       = war_data.get("att_nation_name")
        def_name       = war_data.get("def_nation_name")

        resources_looted = {r: float(attack_data.get(f"{r}_looted") or 0) for r in _RESOURCES}

        await self.holdings_db.apply_loot_event(
            attacker_id=att_id,
            defender_id=def_id,
            money_looted=float(attack_data.get("money_looted") or 0),
            resources_looted=resources_looted,
            loot_date=loot_date,
            war_type=war_type,
            att_war_policy=att_war_policy,
            def_war_policy=def_war_policy,
            att_has_ape=att_has_ape,
            attacker_name=att_name,
            defender_name=def_name,
        )
        logger.info(
            f"Holdings: win attack {attack_data.get('id')} "
            f"att={att_id} ({att_name}) def={def_id} ({def_name}) "
            f"war_type={war_type} att_policy={att_war_policy} def_policy={def_war_policy} "
            f"ape={att_has_ape} money_looted=${float(attack_data.get('money_looted') or 0):,.0f}"
        )

    # ── Attack processing ─────────────────────────────────────────────────────

    async def _process_attack(self, attack_dict: Dict[str, Any]) -> bool:
        """
        Route an attack. Returns True if the parent war was found.
        Returns False if the war is unknown (attack queued for retry).
        """
        war_id = int(attack_dict.get("war_id"))

        nw_cached = await self.nw_db.get_war(war_id)
        if nw_cached:
            await self._save_attack_nw(attack_dict, nw_cached)
            await self._apply_win_to_holdings(attack_dict, nw_cached)
            return True

        mem_cached = self._get_cached_war(war_id)
        if mem_cached:
            await self._apply_win_to_holdings(attack_dict, mem_cached)
            return True

        return False

    # ── Retry worker ──────────────────────────────────────────────────────────

    async def _retry_pending_attacks(self):
        """Retry attacks whose parent war hadn't arrived yet."""
        while self.running:
            await asyncio.sleep(60)
            if not self._pending_attacks:
                continue

            total = sum(len(a) for a in self._pending_attacks.values())
            if total:
                logger.info(f"Pending attacks: {total} across {len(self._pending_attacks)} wars")

            import time
            now = time.time()
            for war_id in list(self._pending_attacks.keys()):
                attacks = self._pending_attacks[war_id]
                if not attacks:
                    del self._pending_attacks[war_id]
                    continue

                age = now - attacks[0].get("_queued_at", now)
                if age > 300:
                    removed = self._pending_attacks.pop(war_id, [])
                    logger.debug(f"Dropped {len(removed)} stale pending attacks for war {war_id}")
                    continue

                try:
                    war_data = await self._fetch_war(war_id)
                    if war_data:
                        for atk in attacks:
                            await self._save_attack_nw(atk, war_data)
                            await self._apply_win_to_holdings(atk, war_data)
                        del self._pending_attacks[war_id]
                        logger.info(f"Resolved {len(attacks)} pending attacks for war {war_id}")
                except Exception as e:
                    logger.error(f"Error retrying pending attacks for war {war_id}: {e}")

    # ── Subscription listeners ────────────────────────────────────────────────

    async def _listen_war_attacks(self):
        """warattack/create — all attacks in the game."""
        try:
            subscription = await self.kit.subscribe("warattack", "create")
            logger.info("warattack/create subscription active")

            async for attack in subscription:
                if not self.running:
                    break
                try:
                    attack_dict = _obj_to_dict(attack)
                    attack_id   = attack_dict.get("id")
                    if not attack_id or attack_id in self._processed_attack_ids:
                        continue
                    self._processed_attack_ids.append(attack_id)

                    war_id = attack_dict.get("war_id")
                    if not war_id:
                        continue

                    # Normalise ID fields
                    if attack_dict.get("attacker_id") is None and attack_dict.get("att_id") is not None:
                        attack_dict["attacker_id"] = attack_dict["att_id"]
                    if attack_dict.get("defender_id") is None and attack_dict.get("def_id") is not None:
                        attack_dict["defender_id"] = attack_dict["def_id"]

                    handled = await self._process_attack(attack_dict)
                    if not handled:
                        import time
                        attack_dict["_queued_at"] = time.time()
                        self._pending_attacks[int(war_id)].append(attack_dict)
                        logger.debug(f"Attack {attack_id} queued — war {war_id} not yet seen")

                except Exception as e:
                    logger.error(f"warattack/create event error: {e}", exc_info=True)

        except asyncio.CancelledError:
            logger.info("warattack/create listener cancelled")
        except Exception as e:
            logger.error(f"warattack/create subscription crashed: {e}", exc_info=True)
            self.running = False

    async def _listen_war_creates(self):
        """war/create — all new wars."""
        try:
            subscription = await self.kit.subscribe("war", "create")
            logger.info("war/create subscription active")

            async for war in subscription:
                if not self.running:
                    break
                try:
                    war_dict   = _obj_to_dict(war)
                    war_id     = war_dict.get("id")
                    if not war_id:
                        continue

                    war_id_int = int(war_id)
                    await self._save_war_nw(war_dict)

                    logger.info(
                        f"war/create → {'NW' if self._is_nw_war(war_dict) else 'non-NW'} "
                        f"war {war_id} "
                        f"(att_alliance={war_dict.get('att_alliance_id')}, "
                        f"def_alliance={war_dict.get('def_alliance_id')})"
                    )

                    # Flush any attacks that were waiting for this war
                    pending = self._pending_attacks.pop(war_id_int, [])
                    if pending:
                        for atk in pending:
                            await self._save_attack_nw(atk, war_dict)
                            await self._apply_win_to_holdings(atk, war_dict)
                        logger.info(f"war/create {war_id}: flushed {len(pending)} pending attack(s)")

                except Exception as e:
                    logger.error(f"war/create event error: {e}", exc_info=True)

        except asyncio.CancelledError:
            logger.info("war/create listener cancelled")
        except Exception as e:
            logger.error(f"war/create subscription crashed: {e}", exc_info=True)

    async def _listen_war_updates(self):
        """war/update — all war state changes."""
        try:
            subscription = await self.kit.subscribe("war", "update")
            logger.info("war/update subscription active")

            async for war in subscription:
                if not self.running:
                    break
                try:
                    war_dict = _obj_to_dict(war)
                    war_id   = war_dict.get("id")
                    if not war_id:
                        continue

                    self._cache_war(war_dict)
                    if self._is_nw_war(war_dict):
                        await self.nw_db.save_war(war_dict)
                        logger.debug(f"war/update → updated NW war {war_id}")
                    else:
                        logger.debug(f"war/update → cached non-NW war {war_id}")

                except Exception as e:
                    logger.error(f"war/update event error: {e}", exc_info=True)

        except asyncio.CancelledError:
            logger.info("war/update listener cancelled")
        except Exception as e:
            logger.error(f"war/update subscription crashed: {e}", exc_info=True)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self):
        if self.running:
            logger.warning("GlobalWarsSubscription already running")
            return
        self.running = True
        logger.info("Starting GlobalWarsSubscription")
        self._listener_tasks = [
            asyncio.create_task(self._listen_war_attacks()),
            asyncio.create_task(self._listen_war_creates()),
            asyncio.create_task(self._listen_war_updates()),
            asyncio.create_task(self._retry_pending_attacks()),
        ]
        await asyncio.gather(*self._listener_tasks, return_exceptions=True)

    async def stop(self):
        self.running = False
        for t in self._listener_tasks:
            t.cancel()
        await asyncio.gather(*self._listener_tasks, return_exceptions=True)
        self._listener_tasks.clear()
        logger.info("GlobalWarsSubscription stopped")

    async def run_forever(self):
        while True:
            try:
                await self.start()
                while self.running:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                logger.info("GlobalWarsSubscription cancelled")
                break
            except pnwkit_errors.NoReconnect as e:
                logger.warning(f"WebSocket disconnected ({e}) — restarting in 30s")
                await asyncio.sleep(30)
            except Exception as e:
                logger.error(f"GlobalWarsSubscription crashed ({e}) — restarting in 30s", exc_info=True)
                await asyncio.sleep(30)
            finally:
                await self.stop()
