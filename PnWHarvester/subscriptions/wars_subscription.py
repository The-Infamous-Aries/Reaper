"""
GlobalWarsSubscription

Unfiltered WebSocket subscriptions for ALL wars in the game.

Behaviour:
  - war/create        → save NW wars to IRSWarsDB; all wars tracked in memory
  - war/update        → update NW wars in IRSWarsDB; update memory cache
  - warattack/create  → on every ground-win attack, update HoldingsDB immediately:
                          defender: SET holdings to back-calculated post-loot value
                          attacker: ADD looted amounts to their holdings
"""

import asyncio
import logging
from collections import deque, defaultdict
from typing import Any, Dict, List, Optional

import aiohttp
from pnwkit.new import QueryKit
from pnwkit import errors as pnwkit_errors

logger = logging.getLogger(__name__)

# ── News writer (optional — imported lazily so harvester works without it) ────
def _get_news_writer():
    try:
        import PnWHarvester.db.news_writer as nw
        return nw
    except Exception:
        return None

IRS_ALLIANCE_ID = 14225
EP_ALLIANCE_ID  = IRS_ALLIANCE_ID  # backward-compat alias

def _clean_aname(name: Any) -> Optional[str]:
    """Return None if name is falsy or the PnW '0' placeholder, else return name."""
    return name if (name and name != '0') else None

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
    "attacker { id nation_name leader_name war_policy advanced_pirate_economy alliance { id name flag } } "
    "defender { id nation_name leader_name war_policy alliance { id name flag } }"
)

ATTACK_QUERY_FIELDS = (
    "id date att_id def_id type war_id victor success "
    "city_infra_before infra_destroyed infra_destroyed_value "
    "money_stolen money_destroyed military_salvage_aluminum military_salvage_steel "
    "attcas1 defcas1 attcas2 defcas2 "
    "att_aircraft_lost def_aircraft_lost att_ships_lost def_ships_lost "
    "att_missiles_lost def_missiles_lost att_nukes_lost def_nukes_lost "
    "att_mun_used def_mun_used att_gas_used def_gas_used "
    "improvements_destroyed "
    "money_looted coal_looted oil_looted uranium_looted iron_looted "
    "bauxite_looted lead_looted gasoline_looted munitions_looted "
    "steel_looted aluminum_looted food_looted"
)

_RESOURCES = (
    "coal", "oil", "uranium", "iron", "bauxite", "lead",
    "gasoline", "munitions", "steel", "aluminum", "food",
)


def _calc_loot_value(money_looted: float, resources_looted: Dict[str, float]) -> float:
    """
    Calculate total loot value using real market prices from the DB cache.
    Uses best_sell_price — same column loot.py uses via get_latest_resource_prices.
    Falls back to conservative per-resource estimates only if the DB has no data.
    """
    _FALLBACK_PRICES = {
        "coal": 2000, "oil": 2000, "uranium": 4000, "iron": 2000,
        "bauxite": 2000, "lead": 2000, "gasoline": 3000, "munitions": 2000,
        "steel": 3000, "aluminum": 2000, "food": 150,
    }
    try:
        import sqlite3
        from Systems.Functions.db_paths import REAPER_DB_STR
        conn = sqlite3.connect(REAPER_DB_STR)
        # resource_prices table: (timestamp, resource, avg_price, best_buy_price, best_sell_price)
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


def _obj_to_dict(obj: Any) -> Dict[str, Any]:
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


def _norm(val: Any) -> str:
    """Normalise an enum/string value to lowercase plain string."""
    if val is None:
        return ""
    s = str(val)
    if "." in s:
        s = s.rsplit(".", 1)[-1]
    return s.lower()


class GlobalWarsSubscription:
    def __init__(self, global_db, nw_db, query_instance, api_key: str, holdings_db=None,
                 nw_nations_db=None, global_nations_db=None):
        """
        global_db         : None (disabled)
        nw_db             : IRSWarsDB       — receives NW-only war/attack events
        query_instance    : kept for call-site compatibility, not used
        api_key           : PnW API v3 key (WebSocket only)
        holdings_db       : HoldingsDB      — updated on every ground-win attack
        nw_nations_db     : ignored (kept for call-site compatibility)
        global_nations_db : GlobalNationsDB — war stats updated via nation/update subscription
        """
        self.global_db          = None
        self.nw_db              = nw_db
        self.holdings_db        = holdings_db
        self.global_nations_db  = global_nations_db
        self.api_key            = api_key
        self.kit                = QueryKit(api_key)
        self.running            = False
        self._listener_tasks: list[asyncio.Task] = []

        # Dedup rings
        self._processed_attack_ids: deque = deque(maxlen=2000)
        self._processed_war_ids:    set   = set()   # war IDs whose end has been processed
        self._processed_war_ids_order: deque = deque(maxlen=5000)  # eviction order

        # In-memory war cache — maps war_id -> war context dict
        # Stores war_type, policies, and nation names needed for holdings updates
        self._war_cache: Dict[int, Dict[str, Any]] = {}
        self._war_cache_maxsize = 5000

        # Pending attacks whose parent war hasn't arrived yet
        self._pending_attacks: dict[int, list[Dict[str, Any]]] = defaultdict(list)

        # Watchdog: last-seen timestamps per subscription channel.
        # Updated on every received event; checked every 60s.
        # If any channel goes silent for > its timeout the watchdog raises
        # RuntimeError so start() exits and run_forever() restarts.
        import time as _time_mod
        _now = _time_mod.monotonic()
        self._last_seen: Dict[str, float] = {
            "war/create":       _now,
            "war/update":       _now,
            "warattack/create": _now,
        }
        # Per-channel timeouts:
        #   war/update      — fires every turn (2h) for ALL active wars; 35 min
        #                     of silence means the socket is dead.
        #   warattack/create — fires on every attack; quiet periods are normal
        #                     (no active wars), so use a longer timeout.
        #   war/create      — fires only when a new war is declared; can be
        #                     legitimately quiet for hours, so we do NOT use it
        #                     as a liveness signal (timeout = None = disabled).
        self._WATCHDOG_TIMEOUTS: Dict[str, Optional[float]] = {
            "war/update":       35 * 60,   # 35 minutes
            "warattack/create": 4 * 3600,  # 4 hours (quiet periods are normal)
            "war/create":       None,      # disabled — can be quiet for hours
        }
        # Legacy scalar kept for backward compat (not used by new watchdog)
        self._WATCHDOG_TIMEOUT_SECS = 35 * 60

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

        # Nation names: prefer nested objects (live subscription), fall back to
        # flat columns (DB row returned by get_war).
        att_name = (
            att_obj.get("nation_name")
            or war_data.get("att_nation_name")
        )
        def_name = (
            def_obj.get("nation_name")
            or war_data.get("def_nation_name")
        )

        self._war_cache[war_id] = {
            "id":              war_id,
            "att_id":          war_data.get("att_id"),
            "def_id":          war_data.get("def_id"),
            "att_alliance_id": war_data.get("att_alliance_id"),
            "def_alliance_id": war_data.get("def_alliance_id"),
            "att_nation_name": att_name,
            "def_nation_name": def_name,
            # Alliance names from nested objects (live subscription) or flat fields.
            # Treat '0' as None — PnW uses '0' for nations with no alliance.
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
            # Alliance flags from nested objects (live subscription) or flat fields
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
            # Nation flags from nested objects if available
            "att_nation_flag": att_obj.get("flag") or war_data.get("att_nation_flag"),
            "def_nation_flag": def_obj.get("flag") or war_data.get("def_nation_flag"),
            # These three are critical for correct loot % in holdings
            "war_type":        _norm(war_data.get("war_type")),
            "att_war_policy":  _norm(att_obj.get("war_policy") or war_data.get("att_war_policy")),
            "def_war_policy":  _norm(def_obj.get("war_policy") or war_data.get("def_war_policy")),
            "att_has_ape":     bool(att_obj.get("advanced_pirate_economy") or war_data.get("att_has_ape")),
        }

        if len(self._war_cache) > self._war_cache_maxsize:
            del self._war_cache[next(iter(self._war_cache))]

    def _get_cached_war(self, war_id: int) -> Optional[Dict[str, Any]]:
        return self._war_cache.get(int(war_id))

    async def _fetch_war(self, war_id: int) -> Optional[Dict[str, Any]]:
        """Memory cache → NW DB only. No API calls — war arrives via subscription."""
        cached = self._get_cached_war(war_id)
        if cached:
            return cached
        nw = await self.nw_db.get_war(war_id)
        if nw:
            self._cache_war(nw)
            return nw
        return None

    async def _fetch_war_from_api(self, war_id: int) -> Optional[Dict[str, Any]]:
        """
        Direct API fetch for a single war by ID.
        Used as a fallback when a war was missed by the subscription
        (e.g. brief disconnect, race condition on startup).
        Caches the result in memory and saves to NW DB if it's an NW war.
        """
        _WAR_FIELDS = (
            "id date end_date reason war_type ground_control air_superiority naval_blockade "
            "winner_id turns_left att_id def_id att_alliance_id att_alliance_position "
            "def_alliance_id def_alliance_position att_points def_points att_peace def_peace "
            "att_resistance def_resistance att_fortify def_fortify att_gas_used def_gas_used "
            "att_mun_used def_mun_used att_infra_destroyed def_infra_destroyed "
            "att_infra_destroyed_value def_infra_destroyed_value "
            "att_soldiers_lost def_soldiers_lost att_tanks_lost def_tanks_lost "
            "att_aircraft_lost def_aircraft_lost att_ships_lost def_ships_lost "
            "att_missiles_used def_missiles_used att_nukes_used def_nukes_used "
            "attacker { id nation_name leader_name war_policy advanced_pirate_economy "
            "           alliance { id name flag } } "
            "defender { id nation_name leader_name war_policy "
            "           alliance { id name flag } }"
        )
        try:
            # Build a lightweight V3GraphQuery for the REST call
            from Systems.PnW.Util.query import create_v3_query_instance
            qi = create_v3_query_instance(api_key=self.api_key, logger=logger)
            query = f"""
            query {{
              wars(id: [{war_id}]) {{
                data {{ {_WAR_FIELDS} }}
              }}
            }}
            """
            raw = await qi._make_graphql_request(query, timeout=30)
            wars = ((raw or {}).get("wars") or {}).get("data") or []
            if not wars:
                logger.debug(f"API fetch: war {war_id} not found")
                return None
            war_data = wars[0]
            self._cache_war(war_data)
            if self._is_nw_war(war_data):
                await self.nw_db.save_war(war_data)
            logger.debug(f"API fetch: war {war_id} retrieved and cached")
            return war_data
        except Exception as e:
            logger.debug(f"_fetch_war_from_api({war_id}): {e}")
            return None

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

        Also applies military losses to both sides so military unit counts stay
        accurate without waiting for the next nation/update subscription event.
        """
        if not self.holdings_db:
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
        # att_name / def_name: resolve based on which war role matches the
        # attack's attacker.  The war's att_nation_name is the war's original
        # attacker; when the war defender launches an attack their nation ID
        # appears as att_id in attack_data but their name is under def_nation_name
        # in war_data.  We defer the final resolution to the news block below
        # where we have the _att_prefix/_def_prefix logic, but we still need
        # sensible defaults here for the loot / holdings code above.
        _war_att_id_early = int(war_data.get("att_id") or 0)
        if att_id == _war_att_id_early:
            att_name = war_data.get("att_nation_name")
            def_name = war_data.get("def_nation_name")
        else:
            att_name = war_data.get("def_nation_name")
            def_name = war_data.get("att_nation_name")

        # ── Loot update (only if this is a winning ground attack with loot) ──
        if _is_win_attack(attack_data):
            resources_looted = {r: float(attack_data.get(f"{r}_looted") or 0) for r in _RESOURCES}

            await self.holdings_db.apply_loot_event(
                attacker_id=att_id,
                defender_id=def_id,
                money_looted=float(attack_data.get("money_stolen") or attack_data.get("money_looted") or 0),
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
                f"ape={att_has_ape} money_stolen=${float(attack_data.get('money_stolen') or 0):,.0f}"
                + (
                    " | resources: " + ", ".join(
                        f"{r}={v:,.2f}" for r, v in resources_looted.items() if v > 0
                    ) if any(v > 0 for v in resources_looted.values()) else ""
                )
            )

        # ── Military loss tracking ────────────────────────────────────────────
        # Apply military losses from the attack to both sides so holdings
        # military counts stay current without waiting for nation/update events.
        # attcas1/defcas1 = soldiers lost; attcas2/defcas2 = tanks lost
        # att_aircraft_lost/def_aircraft_lost, att_ships_lost/def_ships_lost
        # att_missiles_lost/def_missiles_lost, att_nukes_lost/def_nukes_lost
        att_soldiers_lost = int(attack_data.get("attcas1") or 0)
        def_soldiers_lost = int(attack_data.get("defcas1") or 0)
        att_tanks_lost    = int(attack_data.get("attcas2") or 0)
        def_tanks_lost    = int(attack_data.get("defcas2") or 0)
        att_aircraft_lost = int(attack_data.get("att_aircraft_lost") or 0)
        def_aircraft_lost = int(attack_data.get("def_aircraft_lost") or 0)
        att_ships_lost    = int(attack_data.get("att_ships_lost") or 0)
        def_ships_lost    = int(attack_data.get("def_ships_lost") or 0)
        att_missiles_lost = int(attack_data.get("att_missiles_lost") or 0)
        def_missiles_lost = int(attack_data.get("def_missiles_lost") or 0)
        att_nukes_lost    = int(attack_data.get("att_nukes_lost") or 0)
        def_nukes_lost    = int(attack_data.get("def_nukes_lost") or 0)

        # ── War resource consumption (gasoline / munitions used in this attack) ─
        # att_gas_used / att_mun_used are per-attack fields from the API — the
        # exact amount consumed by the attacker in this specific attack.
        # def_gas_used / def_mun_used are the defender's consumption (e.g. from
        # fortify actions or defensive missile/nuke launches).
        att_gas_consumed = float(attack_data.get("att_gas_used") or 0)
        att_mun_consumed = float(attack_data.get("att_mun_used") or 0)
        def_gas_consumed = float(attack_data.get("def_gas_used") or 0)
        def_mun_consumed = float(attack_data.get("def_mun_used") or 0)

        if att_gas_consumed > 0 or att_mun_consumed > 0:
            try:
                await self.holdings_db.apply_war_consumption(
                    nation_id=att_id,
                    gasoline=att_gas_consumed,
                    munitions=att_mun_consumed,
                    event_date=loot_date,
                    nation_name=att_name,
                )
                logger.debug(
                    f"Holdings: war consumption attack {attack_data.get('id')} "
                    f"att={att_id} gas={att_gas_consumed:.2f} mun={att_mun_consumed:.2f}"
                )
            except Exception as e:
                logger.debug(f"apply_war_consumption(att) failed for attack {attack_data.get('id')}: {e}")

        if def_gas_consumed > 0 or def_mun_consumed > 0:
            try:
                await self.holdings_db.apply_war_consumption(
                    nation_id=def_id,
                    gasoline=def_gas_consumed,
                    munitions=def_mun_consumed,
                    event_date=loot_date,
                    nation_name=def_name,
                )
                logger.debug(
                    f"Holdings: war consumption attack {attack_data.get('id')} "
                    f"def={def_id} gas={def_gas_consumed:.2f} mun={def_mun_consumed:.2f}"
                )
            except Exception as e:
                logger.debug(f"apply_war_consumption(def) failed for attack {attack_data.get('id')}: {e}")
        has_att_losses = any([att_soldiers_lost, att_tanks_lost, att_aircraft_lost,
                               att_ships_lost, att_missiles_lost, att_nukes_lost])
        has_def_losses = any([def_soldiers_lost, def_tanks_lost, def_aircraft_lost,
                               def_ships_lost, def_missiles_lost, def_nukes_lost])

        if has_att_losses or has_def_losses:
            try:
                await self.holdings_db.apply_combat_losses(
                    attacker_id=att_id,
                    defender_id=def_id,
                    att_losses={
                        "soldiers": att_soldiers_lost,
                        "tanks":    att_tanks_lost,
                        "aircraft": att_aircraft_lost,
                        "ships":    att_ships_lost,
                        "missiles": att_missiles_lost,
                        "nukes":    att_nukes_lost,
                    },
                    def_losses={
                        "soldiers": def_soldiers_lost,
                        "tanks":    def_tanks_lost,
                        "aircraft": def_aircraft_lost,
                        "ships":    def_ships_lost,
                        "missiles": def_missiles_lost,
                        "nukes":    def_nukes_lost,
                    },
                    event_date=loot_date,
                    attacker_name=att_name,
                    defender_name=def_name,
                )
            except Exception as e:
                logger.debug(f"apply_combat_losses failed for attack {attack_data.get('id')}: {e}")

        # ── News: nuke/missile/loot events ────────────────────────────────────
        try:
            nw = _get_news_writer()
            if nw:
                attack_type_raw  = _norm(attack_data.get("type", ""))

                # ── Infra destroyed value: calculate from attack payload ──────
                # Use calc_infra_value(infra_after, infra_before) — cost to
                # rebuild from post-impact level back to pre-impact level.
                # This is backwards-compatible: falls back to the API value if
                # city_infra_before / infra_destroyed are missing.
                try:
                    from PnWHarvester.db.pnw_costs import calc_infra_value as _calc_infra_val
                    _city_infra_before = float(attack_data.get("city_infra_before") or 0)
                    _infra_destroyed   = float(attack_data.get("infra_destroyed") or 0)
                    if _city_infra_before > 0 and _infra_destroyed > 0:
                        _infra_after = max(0.0, _city_infra_before - _infra_destroyed)
                        infra_val = _calc_infra_val(_infra_after, _city_infra_before)
                    else:
                        infra_val = float(attack_data.get("infra_destroyed_value") or 0)
                except Exception:
                    infra_val = float(attack_data.get("infra_destroyed_value") or 0)

                # Determine which war role (att/def) corresponds to the attack's
                # attacker and defender.  att_id/def_id come from attack_data and
                # correctly identify who fired and who was targeted in THIS attack.
                # The war's att_* / def_* fields describe the war's original
                # attacker/defender, which may be the OPPOSITE of the attack's
                # attacker when the war defender launches a counter-strike.
                _war_att_id = int(war_data.get("att_id") or 0)
                if att_id == _war_att_id:
                    # Attack's attacker == war's attacker
                    _att_prefix, _def_prefix = "att", "def"
                else:
                    # Attack's attacker == war's defender (counter-strike)
                    _att_prefix, _def_prefix = "def", "att"

                att_alliance_id  = int(war_data.get(f"{_att_prefix}_alliance_id") or 0) or None
                def_alliance_id  = int(war_data.get(f"{_def_prefix}_alliance_id") or 0) or None
                # Treat "0" or blank strings as missing alliance names so the
                # DB lookup in record_wmd_attack can fill them in correctly.
                _att_aname = war_data.get(f"{_att_prefix}_alliance_name") or ""
                _def_aname = war_data.get(f"{_def_prefix}_alliance_name") or ""
                att_alliance_name = _att_aname if _att_aname and _att_aname != "0" else None
                def_alliance_name = _def_aname if _def_aname and _def_aname != "0" else None
                att_flag          = war_data.get(f"{_att_prefix}_nation_flag")
                def_flag          = war_data.get(f"{_def_prefix}_nation_flag")
                att_alliance_flag = war_data.get(f"{_att_prefix}_alliance_flag") or None
                def_alliance_flag = war_data.get(f"{_def_prefix}_alliance_flag") or None
                # Parse improvements_destroyed (comes as a list of strings from API)
                _raw_imps = attack_data.get("improvements_destroyed") or []
                _imps_destroyed: Dict[str, int] = {}
                if isinstance(_raw_imps, list):
                    for _imp_raw in _raw_imps:
                        _imp = str(_imp_raw).lower().replace(" ", "_")
                        _imps_destroyed[_imp] = _imps_destroyed.get(_imp, 0) + 1
                elif isinstance(_raw_imps, dict):
                    _imps_destroyed = {k: int(v) for k, v in _raw_imps.items() if int(v) > 0}

                # Determine if the attack missed
                # Priority 1: Check if attack type explicitly indicates a miss (missilefail/nukefail)
                # Priority 2: Check success field from API
                # Priority 3: Check victor field (if victor != attacker, it's a miss)
                _victor = attack_data.get("victor")
                _success = attack_data.get("success")
                _attack_missed = False
                
                # For missile/nuke attacks, the attack type itself tells us if it missed
                if attack_type_raw in ("missilefail", "nukefail"):
                    _attack_missed = True
                elif _success is not None:
                    _attack_missed = not bool(_success)
                elif _victor is not None:
                    _attack_missed = str(_victor) != str(att_id)

                _resistance_lost = int(attack_data.get("resistance_lost") or 0) or None

                # Helper to safely execute news recording tasks with error logging
                async def _safe_record_wmd(attack_type: str, **kwargs):
                    try:
                        await nw.record_wmd_attack(attack_type=attack_type, **kwargs)
                    except Exception as e:
                        logger.error(f"record_wmd_attack({attack_type}) failed for attack {attack_data.get('id')}: {e}", exc_info=True)

                # Nuke attack (exact match for "nuke" or "nukefail")
                if attack_type_raw in ("nuke", "nukefail"):
                    asyncio.create_task(_safe_record_wmd(
                        attack_type="nuke",
                        att_nation_id=att_id,
                        att_nation_name=att_name,
                        att_nation_flag=att_flag,
                        att_alliance_id=att_alliance_id,
                        att_alliance_name=att_alliance_name,
                        att_alliance_flag=att_alliance_flag,
                        def_nation_id=def_id,
                        def_nation_name=def_name,
                        def_nation_flag=def_flag,
                        def_alliance_id=def_alliance_id,
                        def_alliance_name=def_alliance_name,
                        def_alliance_flag=def_alliance_flag,
                        infra_destroyed_value=infra_val,
                        event_date=loot_date,
                        missed=_attack_missed,
                        resistance_lost=_resistance_lost,
                        improvements_destroyed=_imps_destroyed if _imps_destroyed else None,
                    ))
                # Missile attack (exact match for "missile" or "missilefail")
                elif attack_type_raw in ("missile", "missilefail"):
                    asyncio.create_task(_safe_record_wmd(
                        attack_type="missile",
                        att_nation_id=att_id,
                        att_nation_name=att_name,
                        att_nation_flag=att_flag,
                        att_alliance_id=att_alliance_id,
                        att_alliance_name=att_alliance_name,
                        att_alliance_flag=att_alliance_flag,
                        def_nation_id=def_id,
                        def_nation_name=def_name,
                        def_nation_flag=def_flag,
                        def_alliance_id=def_alliance_id,
                        def_alliance_name=def_alliance_name,
                        def_alliance_flag=def_alliance_flag,
                        infra_destroyed_value=infra_val,
                        event_date=loot_date,
                        missed=_attack_missed,
                        resistance_lost=_resistance_lost,
                        improvements_destroyed=_imps_destroyed if _imps_destroyed else None,
                    ))
                # Loot attack — record stats for ALL loots, feed only for large ones
                if _is_win_attack(attack_data):
                    money_looted = float(attack_data.get("money_stolen") or attack_data.get("money_looted") or 0)
                    res_looted = {r: float(attack_data.get(f"{r}_looted") or 0) for r in _RESOURCES}
                    total_loot = _calc_loot_value(money_looted, res_looted)
                    if total_loot > 0:
                        asyncio.create_task(nw.record_loot_attack(
                            att_nation_id=att_id,
                            att_nation_name=att_name,
                            att_nation_flag=att_flag,
                            att_alliance_id=att_alliance_id,
                            att_alliance_name=att_alliance_name,
                            att_alliance_flag=att_alliance_flag,
                            def_nation_id=def_id,
                            def_nation_name=def_name,
                            def_nation_flag=def_flag,
                            def_alliance_id=def_alliance_id,
                            def_alliance_name=def_alliance_name,
                            money_looted=money_looted,
                            total_loot_value=total_loot,
                            event_date=loot_date,
                            resources_looted={r: v for r, v in res_looted.items() if v > 0},
                            improvements_destroyed=_imps_destroyed if _imps_destroyed else None,
                            infra_destroyed_value=infra_val,
                        ))
        except Exception as _ne:
            logger.debug(f"news attack event: {_ne}")

    # ── Attack processing ─────────────────────────────────────────────────────

    async def _process_attack(self, attack_dict: Dict[str, Any]) -> bool:
        """
        Route an attack. Returns True if the parent war was found.
        Returns False if the war is unknown (attack queued for retry).

        Priority:
          1. In-memory war cache (populated by war/create and war/update events).
             This is the freshest source and covers ALL wars (NW and non-NW).
          2. NW DB (IRSWars.db) — fallback for NW wars that arrived before the
             in-memory cache was populated (e.g. after a restart).
          3. API fetch — last resort.

        For NW wars the attack is also saved to IRSWars.db.
        Holdings are updated for ALL wars regardless of NW membership.
        """
        war_id = attack_dict.get("war_id")
        if not war_id:
            return False
        war_id = int(war_id)

        # ── 1. Memory cache (fastest, covers all wars) ────────────────────────
        mem_cached = self._get_cached_war(war_id)
        if mem_cached:
            await self._save_attack_nw(attack_dict, mem_cached)
            await self._apply_win_to_holdings(attack_dict, mem_cached)
            return True

        # ── 2. NW DB fallback (NW wars only) ─────────────────────────────────
        nw_cached = await self.nw_db.get_war(war_id)
        if nw_cached:
            # Re-cache so future attacks for this war hit path 1
            self._cache_war(nw_cached)
            await self._save_attack_nw(attack_dict, nw_cached)
            await self._apply_win_to_holdings(attack_dict, nw_cached)
            return True

        return False

    # ── Retry worker ──────────────────────────────────────────────────────────

    async def _retry_pending_attacks(self):
        """
        Retry attacks whose parent war hadn't arrived via subscription yet.

        Each 60s cycle:
          1. Try the memory cache and NW DB (same as _process_attack path 1+2).
          2. If still not found and age > 120s, attempt a direct API fetch for
             the war — covers wars that arrived before the subscription started
             or were missed due to a brief disconnect.
          3. If age > 600s and the API fetch also failed, drop with a warning.
        """
        import time
        while self.running:
            await asyncio.sleep(60)
            if not self._pending_attacks:
                continue

            total = sum(len(a) for a in self._pending_attacks.values())
            if total:
                logger.info(f"Pending attacks: {total} across {len(self._pending_attacks)} wars")

            now = time.time()
            for war_id in list(self._pending_attacks.keys()):
                attacks = self._pending_attacks.get(war_id)
                if not attacks:
                    self._pending_attacks.pop(war_id, None)
                    continue

                age = now - attacks[0].get("_queued_at", now)

                # ── Try cache + NW DB first ───────────────────────────────────
                try:
                    war_data = await self._fetch_war(war_id)
                    if war_data:
                        for atk in attacks:
                            await self._save_attack_nw(atk, war_data)
                            await self._apply_win_to_holdings(atk, war_data)
                        self._pending_attacks.pop(war_id, None)
                        logger.info(
                            f"Resolved {len(attacks)} pending attacks for war {war_id} "
                            f"(age={age:.0f}s, via cache/DB)"
                        )
                        continue
                except Exception as e:
                    logger.error(f"Error retrying pending attacks for war {war_id} (cache): {e}")

                # ── API fallback after 120s ───────────────────────────────────
                if age > 120:
                    try:
                        war_data = await self._fetch_war_from_api(war_id)
                        if war_data:
                            self._cache_war(war_data)
                            for atk in attacks:
                                await self._save_attack_nw(atk, war_data)
                                await self._apply_win_to_holdings(atk, war_data)
                            self._pending_attacks.pop(war_id, None)
                            logger.info(
                                f"Resolved {len(attacks)} pending attacks for war {war_id} "
                                f"(age={age:.0f}s, via API fetch)"
                            )
                            continue
                    except Exception as e:
                        logger.debug(f"API fetch for war {war_id} failed: {e}")

                # ── Drop after 600s ───────────────────────────────────────────
                if age > 600:
                    removed = self._pending_attacks.pop(war_id, [])
                    attack_ids = [a.get("id") for a in removed]
                    logger.warning(
                        f"Dropped {len(removed)} stale pending attacks for war {war_id} "
                        f"(age={age:.0f}s > 600s, war not found in cache, DB, or API) "
                        f"— attack IDs: {attack_ids}"
                    )

    # ── War end detection ─────────────────────────────────────────────────────

    @staticmethod
    def _classify_war_end(war_dict: Dict[str, Any]) -> Optional[str]:
        """Return the end reason if this war payload signals the war is over, else None.

        End conditions (any one is sufficient):
          - turns_left <= 0  (PnW sends 0 on expiry, but also negative values like
                              -3, -8, -12 for wars that expired between subscription events)
          - end_date is a non-empty string
          - winner_id is set (non-zero)
          - att_peace == 1 AND def_peace == 1  (mutual peace)
        """
        turns_left = war_dict.get("turns_left")
        winner_id  = war_dict.get("winner_id")
        end_date   = war_dict.get("end_date")
        att_peace  = war_dict.get("att_peace")
        def_peace  = war_dict.get("def_peace")

        if winner_id is not None and int(winner_id) != 0:
            return "win"
        if att_peace is not None and def_peace is not None and int(att_peace) == 1 and int(def_peace) == 1:
            return "peace"
        if turns_left is not None and int(turns_left) <= 0:
            return "expire"
        if end_date and str(end_date).strip():
            return "ended"
        return None

    def _log_war_end(self, war_dict: Dict[str, Any], end_reason: str, source: str = "war/update"):
        """Emit a structured INFO log when a war ends."""
        war_id   = war_dict.get("id")
        att_name = war_dict.get("att_nation_name") or (war_dict.get("attacker") or {}).get("nation_name") or f"att={war_dict.get('att_id')}"
        def_name = war_dict.get("def_nation_name") or (war_dict.get("defender") or {}).get("nation_name") or f"def={war_dict.get('def_id')}"
        winner   = war_dict.get("winner_id")
        turns    = war_dict.get("turns_left")
        att_p    = war_dict.get("att_peace")
        def_p    = war_dict.get("def_peace")

        if end_reason == "win":
            winner_name = att_name if str(winner) == str(war_dict.get("att_id")) else def_name
            logger.info(
                f"[{source}] War {war_id} ENDED — WIN — {att_name} vs {def_name} | "
                f"winner={winner_name} (id={winner})"
            )
        elif end_reason == "peace":
            logger.info(
                f"[{source}] War {war_id} ENDED — PEACE — {att_name} vs {def_name} | "
                f"att_peace={att_p} def_peace={def_p}"
            )
        elif end_reason == "expire":
            logger.info(
                f"[{source}] War {war_id} ENDED — EXPIRE — {att_name} vs {def_name} | "
                f"turns_left={turns}"
            )
        else:
            logger.info(
                f"[{source}] War {war_id} ENDED — {end_reason.upper()} — {att_name} vs {def_name}"
            )

    # ── Nation war-stats update on war end ───────────────────────────────────
    # offensive_wars_count / defensive_wars_count are managed EXCLUSIVELY by
    # update_war_counts() below — save_nation() intentionally excludes them.
    # wars_won / wars_lost are also managed exclusively by update_war_counts().
    # beige_turns is written by save_nation() from the nation/update payload AND
    # proactively patched by _handle_war_loss_beige() so GlobalNations.db is
    # accurate before the next nation/update event arrives.

    # ── Beige: war-loss tracking ──────────────────────────────────────────────

    async def _handle_war_loss_beige(self, war_dict: Dict[str, Any], loser_id: int):
        """
        Called when a war ends and a nation is placed on beige.

        PnW places the loser on beige for 24 turns on a decisive win.
        On peace/expire the defender also goes to beige (PnW game rule).

        Two things happen here:
          1. GlobalNations.db beige_turns is patched to 24 immediately so the
             reaper's beige notification loop sees the correct value before the
             next nation/update WebSocket event arrives.
          2. Any existing beige_alerts rows for this nation are updated to
             reflect the new 24-turn period so the reminders box stays accurate.
             If the nation already has more turns stored (stacked beige from a
             previous loss) we leave the higher value in place.

        We do NOT create new alerts here — only the user can subscribe to a
        nation for beige notifications.
        """
        BEIGE_TURNS_ON_LOSS = 24

        loser_name = (
            war_dict.get("def_nation_name")
            if int(war_dict.get("def_id") or 0) == loser_id
            else war_dict.get("att_nation_name")
        ) or f"nation {loser_id}"

        # ── 1. Patch GlobalNations.db beige_turns immediately ─────────────────
        # This ensures the reaper's beige loop sees the correct value before the
        # next nation/update event arrives (which may be delayed by up to one turn).
        if self.global_nations_db:
            try:
                # Read current beige_turns so we only write if it's lower than 24
                # (PnW stacks beige turns — never reduce a higher existing value).
                existing = await self.global_nations_db.get_nation(loser_id)
                current_beige = int((existing or {}).get("beige_turns") or 0)
                if current_beige < BEIGE_TURNS_ON_LOSS:
                    await self.global_nations_db.save_nation({
                        "id": loser_id,
                        "beige_turns": BEIGE_TURNS_ON_LOSS,
                    })
                    logger.info(
                        f"beige: patched GlobalNations.db beige_turns for {loser_name} "
                        f"(id={loser_id}): {current_beige} → {BEIGE_TURNS_ON_LOSS}"
                    )
                else:
                    logger.debug(
                        f"beige: {loser_name} (id={loser_id}) already has "
                        f"{current_beige} beige_turns ≥ {BEIGE_TURNS_ON_LOSS} — no patch needed"
                    )
            except Exception as e:
                logger.warning(f"_handle_war_loss_beige: GlobalNations.db patch failed for {loser_id}: {e}")

        # ── 2. Update beige_alerts rows in alerts.db ──────────────────────────
        try:
            from Systems.Functions.beige_alerts_db import (
                get_beige_alerts_for_nation,
                update_beige_alert_turns,
            )
            alerts = await get_beige_alerts_for_nation(loser_id)
            if not alerts:
                return

            for alert in alerts:
                stored_turns = int(alert.get("beige_turns") or 0)
                # Only update if the new value is higher (PnW stacks beige turns)
                new_turns = max(stored_turns, BEIGE_TURNS_ON_LOSS)
                if new_turns != stored_turns:
                    await update_beige_alert_turns(int(alert["id"]), new_turns)
                    logger.info(
                        f"beige_alerts: war loss — updated {loser_name} (id={loser_id}) "
                        f"turns {stored_turns} → {new_turns} for user {alert['user_id']}"
                    )
                else:
                    logger.debug(
                        f"beige_alerts: war loss — {loser_name} (id={loser_id}) already has "
                        f"{stored_turns} turns ≥ {BEIGE_TURNS_ON_LOSS}, no update needed"
                    )
        except Exception as e:
            logger.warning(f"_handle_war_loss_beige: alerts.db update failed for {loser_id}: {e}")

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
                    self._last_seen["warattack/create"] = __import__("time").monotonic()
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
            raise
        except (ConnectionResetError, OSError, aiohttp.ClientError) as e:
            logger.warning(f"warattack/create WebSocket disconnected: {e} — will restart")
            raise
        except Exception as e:
            logger.error(f"warattack/create subscription crashed: {e}", exc_info=True)
            raise

    async def _listen_war_creates(self):
        """war/create — all new wars."""
        try:
            subscription = await self.kit.subscribe("war", "create")
            logger.info("war/create subscription active")

            async for war in subscription:
                if not self.running:
                    break
                try:
                    self._last_seen["war/create"] = __import__("time").monotonic()
                    war_dict   = _obj_to_dict(war)
                    war_id     = war_dict.get("id")
                    if not war_id:
                        continue

                    war_id_int = int(war_id)
                    is_nw      = self._is_nw_war(war_dict)
                    end_reason = self._classify_war_end(war_dict)

                    await self._save_war_nw(war_dict)

                    if end_reason:
                        # War arrived already ended (very rare — e.g. instant peace)
                        self._log_war_end(war_dict, end_reason, source="war/create")
                    else:
                        att_id = war_dict.get("att_id") or (war_dict.get("attacker") or {}).get("id")
                        def_id = war_dict.get("def_id") or (war_dict.get("defender") or {}).get("id")
                        logger.info(
                            f"war/create → {'NW' if is_nw else 'non-NW'} war {war_id} "
                            f"att={att_id} (alliance={war_dict.get('att_alliance_id')}) "
                            f"def={def_id} (alliance={war_dict.get('def_alliance_id')}) "
                            f"turns_left={war_dict.get('turns_left')}"
                        )
                        # ── News: war declared ────────────────────────────────
                        try:
                            nw = _get_news_writer()
                            if nw:
                                att_obj = war_dict.get("attacker") or {}
                                def_obj = war_dict.get("defender") or {}
                                if not isinstance(att_obj, dict): att_obj = {}
                                if not isinstance(def_obj, dict): def_obj = {}
                                # Extract alliance names and flags from nested objects
                                att_aname = (att_obj.get("alliance") or {}).get("name") if isinstance(att_obj.get("alliance"), dict) else None
                                def_aname = (def_obj.get("alliance") or {}).get("name") if isinstance(def_obj.get("alliance"), dict) else None
                                att_aflag = (att_obj.get("alliance") or {}).get("flag") if isinstance(att_obj.get("alliance"), dict) else None
                                def_aflag = (def_obj.get("alliance") or {}).get("flag") if isinstance(def_obj.get("alliance"), dict) else None
                                asyncio.create_task(nw.record_war_declared(
                                    war_id=int(war_id),
                                    att_nation_id=int(war_dict.get("att_id") or 0),
                                    att_nation_name=att_obj.get("nation_name") or war_dict.get("att_nation_name"),
                                    att_nation_flag=att_obj.get("flag"),
                                    att_alliance_id=int(war_dict.get("att_alliance_id") or 0) or None,
                                    att_alliance_name=att_aname,
                                    att_alliance_flag=att_aflag,
                                    def_nation_id=int(war_dict.get("def_id") or 0),
                                    def_nation_name=def_obj.get("nation_name") or war_dict.get("def_nation_name"),
                                    def_nation_flag=def_obj.get("flag"),
                                    def_alliance_id=int(war_dict.get("def_alliance_id") or 0) or None,
                                    def_alliance_name=def_aname,
                                    war_type=_norm(war_dict.get("war_type", "")),
                                    reason=war_dict.get("reason"),
                                    event_date=str(war_dict.get("date") or "").replace("+00:00", "").strip(),
                                    att_leader_name=att_obj.get("leader_name"),
                                    def_leader_name=def_obj.get("leader_name"),
                                ))
                        except Exception as _ne:
                            logger.debug(f"news war_declared: {_ne}")

                        # ── War count: +1 off for attacker, +1 def for defender ──
                        if self.global_nations_db:
                            att_id_wc = int(war_dict.get("att_id") or 0)
                            def_id_wc = int(war_dict.get("def_id") or 0)
                            if att_id_wc:
                                asyncio.create_task(
                                    self.global_nations_db.update_war_counts(att_id_wc, off_delta=1)
                                )
                            if def_id_wc:
                                asyncio.create_task(
                                    self.global_nations_db.update_war_counts(def_id_wc, def_delta=1)
                                )

                        # ── War policy patch: update both nations immediately ──
                        # The war payload carries the current war_policy for both
                        # attacker and defender — patch it now so loot calculations
                        # use the correct policy without waiting for nation/update.
                        if self.global_nations_db:
                            att_obj_wp = war_dict.get("attacker") or {}
                            def_obj_wp = war_dict.get("defender") or {}
                            if not isinstance(att_obj_wp, dict): att_obj_wp = {}
                            if not isinstance(def_obj_wp, dict): def_obj_wp = {}
                            att_policy = _norm(att_obj_wp.get("war_policy") or war_dict.get("att_war_policy") or "")
                            def_policy = _norm(def_obj_wp.get("war_policy") or war_dict.get("def_war_policy") or "")
                            att_id_wp  = int(war_dict.get("att_id") or 0)
                            def_id_wp  = int(war_dict.get("def_id") or 0)
                            if att_id_wp and att_policy:
                                asyncio.create_task(
                                    self.global_nations_db.save_nation({"id": att_id_wp, "war_policy": att_policy})
                                )
                            if def_id_wp and def_policy:
                                asyncio.create_task(
                                    self.global_nations_db.save_nation({"id": def_id_wp, "war_policy": def_policy})
                                )

                    # Flush any attacks that were waiting for this war (always)
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
            raise
        except (ConnectionResetError, OSError, aiohttp.ClientError) as e:
            logger.warning(f"war/create WebSocket disconnected: {e} — will restart")
            raise
        except Exception as e:
            logger.error(f"war/create subscription crashed: {e}", exc_info=True)
            raise

    async def _listen_war_updates(self):
        """war/update — all war state changes.

        Detects end conditions on every update:
          - WIN:    winner_id set (non-zero)
          - PEACE:  att_peace=1 AND def_peace=1
          - EXPIRE: turns_left=0 with no winner
          - Also handles partial peace (one side offered) for logging.
        """
        try:
            subscription = await self.kit.subscribe("war", "update")
            logger.info("war/update subscription active")

            async for war in subscription:
                if not self.running:
                    break
                try:
                    self._last_seen["war/update"] = __import__("time").monotonic()
                    war_dict = _obj_to_dict(war)
                    war_id   = war_dict.get("id")
                    if not war_id:
                        continue

                    is_nw      = self._is_nw_war(war_dict)
                    end_reason = self._classify_war_end(war_dict)

                    # Update cache and DB
                    self._cache_war(war_dict)
                    if is_nw:
                        await self.nw_db.save_war(war_dict)

                    if end_reason:
                        self._log_war_end(war_dict, end_reason, source="war/update")

                        # ── War count + wins/losses: fire once per war end ────
                        # war/update fires repeatedly as turns tick; use a dedup
                        # ring to ensure we only apply the stat changes once.
                        war_id_int = int(war_id)
                        already_ended = war_id_int in self._processed_war_ids
                        if not already_ended:
                            self._processed_war_ids.add(war_id_int)
                            self._processed_war_ids_order.append(war_id_int)
                            # Evict oldest entries if the set grows too large
                            while len(self._processed_war_ids) > 5000:
                                oldest = self._processed_war_ids_order.popleft()
                                self._processed_war_ids.discard(oldest)

                        if self.global_nations_db and not already_ended:
                            att_id_wc  = int(war_dict.get("att_id") or 0)
                            def_id_wc  = int(war_dict.get("def_id") or 0)
                            winner_id  = int(war_dict.get("winner_id") or 0)

                            # ── Slot decrements + wins/losses ─────────────────
                            # WIN:    winner gets wars_won+1, loser gets wars_lost+1.
                            #         Slot counts: attacker -1 off, defender -1 def.
                            # PEACE:  mutual agreement — no winner, no wars_lost.
                            #         Slot counts: attacker -1 off, defender -1 def.
                            # EXPIRE: time ran out — no winner, no wars_lost.
                            #         Slot counts: attacker -1 off, defender -1 def.
                            # ENDED:  end_date set but no other signal — treat same
                            #         as expire (slot decrement only, no wins/losses).
                            #
                            # Note: wars_lost only increments on a decisive loss
                            # (the losing side in a WIN). Peace and expire are not
                            # losses in PnW — they just close the war slot.
                            if end_reason == "win" and winner_id:
                                loser_id = def_id_wc if winner_id == att_id_wc else att_id_wc
                                if att_id_wc:
                                    asyncio.create_task(self.global_nations_db.update_war_counts(
                                        att_id_wc, off_delta=-1,
                                        won_delta=(1 if winner_id == att_id_wc else 0),
                                        lost_delta=(1 if winner_id != att_id_wc else 0),
                                    ))
                                if def_id_wc:
                                    asyncio.create_task(self.global_nations_db.update_war_counts(
                                        def_id_wc, def_delta=-1,
                                        won_delta=(1 if winner_id == def_id_wc else 0),
                                        lost_delta=(1 if winner_id != def_id_wc else 0),
                                    ))

                                # ── Beige: loser gets 24 turns on a decisive win ──
                                # Patch GlobalNations.db beige_turns immediately so
                                # the reaper's beige loop sees the correct value
                                # before the next nation/update event arrives.
                                asyncio.create_task(
                                    self._handle_war_loss_beige(war_dict, loser_id)
                                )
                            else:
                                # Peace, expire, or ended — decrement slots only.
                                # No wars_lost increment: these are not decisive losses.
                                if att_id_wc:
                                    asyncio.create_task(self.global_nations_db.update_war_counts(
                                        att_id_wc, off_delta=-1,
                                    ))
                                if def_id_wc:
                                    asyncio.create_task(self.global_nations_db.update_war_counts(
                                        def_id_wc, def_delta=-1,
                                    ))
                                # ── Beige: defender goes to beige on expire ───
                                # In PnW, when a war expires (turns_left=0) the
                                # defender is placed on beige for 24 turns.
                                # On peace, neither side is forced to beige.
                                if end_reason == "expire" and def_id_wc:
                                    asyncio.create_task(
                                        self._handle_war_loss_beige(war_dict, def_id_wc)
                                    )

                        # ── News: war ended ───────────────────────────────────
                        try:
                            nw = _get_news_writer()
                            if nw:
                                att_obj = war_dict.get("attacker") or {}
                                def_obj = war_dict.get("defender") or {}
                                if not isinstance(att_obj, dict): att_obj = {}
                                if not isinstance(def_obj, dict): def_obj = {}
                                att_aname = (att_obj.get("alliance") or {}).get("name") if isinstance(att_obj.get("alliance"), dict) else None
                                def_aname = (def_obj.get("alliance") or {}).get("name") if isinstance(def_obj.get("alliance"), dict) else None
                                att_aflag = (att_obj.get("alliance") or {}).get("flag") if isinstance(att_obj.get("alliance"), dict) else None
                                def_aflag = (def_obj.get("alliance") or {}).get("flag") if isinstance(def_obj.get("alliance"), dict) else None
                                asyncio.create_task(nw.record_war_ended(
                                    war_id=int(war_id),
                                    att_nation_id=int(war_dict.get("att_id") or 0),
                                    att_nation_name=att_obj.get("nation_name") or war_dict.get("att_nation_name"),
                                    att_nation_flag=att_obj.get("flag"),
                                    att_alliance_id=int(war_dict.get("att_alliance_id") or 0) or None,
                                    att_alliance_name=att_aname,
                                    att_alliance_flag=att_aflag,
                                    def_nation_id=int(war_dict.get("def_id") or 0),
                                    def_nation_name=def_obj.get("nation_name") or war_dict.get("def_nation_name"),
                                    def_nation_flag=def_obj.get("flag"),
                                    def_alliance_id=int(war_dict.get("def_alliance_id") or 0) or None,
                                    def_alliance_name=def_aname,
                                    def_alliance_flag=def_aflag,
                                    winner_id=int(war_dict.get("winner_id") or 0) or None,
                                    end_reason=end_reason,
                                    war_type=_norm(war_dict.get("war_type", "")),
                                    event_date=str(war_dict.get("end_date") or war_dict.get("date") or "").replace("+00:00", "").strip(),
                                ))
                        except Exception as _ne:
                            logger.debug(f"news war_ended: {_ne}")
                    else:
                        # Log partial peace offers (informational)
                        att_peace = war_dict.get("att_peace")
                        def_peace = war_dict.get("def_peace")
                        turns     = war_dict.get("turns_left")
                        if att_peace == 1 and def_peace != 1:
                            att_name = war_dict.get("att_nation_name") or f"att={war_dict.get('att_id')}"
                            logger.info(f"war/update {war_id}: attacker ({att_name}) offered peace | turns_left={turns}")
                        elif def_peace == 1 and att_peace != 1:
                            def_name = war_dict.get("def_nation_name") or f"def={war_dict.get('def_id')}"
                            logger.info(f"war/update {war_id}: defender ({def_name}) offered peace | turns_left={turns}")
                        else:
                            logger.debug(
                                f"war/update → {'NW' if is_nw else 'non-NW'} war {war_id} "
                                f"turns_left={turns} att_peace={att_peace} def_peace={def_peace}"
                            )

                except Exception as e:
                    logger.error(f"war/update event error: {e}", exc_info=True)

        except asyncio.CancelledError:
            logger.info("war/update listener cancelled")
            raise
        except (ConnectionResetError, OSError, aiohttp.ClientError) as e:
            logger.warning(f"war/update WebSocket disconnected: {e} — will restart")
            raise
        except Exception as e:
            logger.error(f"war/update subscription crashed: {e}", exc_info=True)
            raise

    # ── Watchdog ──────────────────────────────────────────────────────────────

    async def _watchdog(self):
        """
        Periodically checks that each subscription channel is still receiving
        events. If any monitored channel goes silent for longer than its
        per-channel timeout, the underlying pnwkit socket has likely been
        garbage-collected or silently dropped. Raises RuntimeError so start()
        exits and run_forever() triggers a full restart.

        Per-channel timeouts (see __init__):
          war/update      — 35 min  (fires every 2h turn for all active wars)
          warattack/create — 4 h    (can be quiet when no wars are active)
          war/create      — disabled (can be quiet for many hours legitimately)
        """
        import time
        CHECK_INTERVAL = 60  # seconds between checks
        while self.running:
            await asyncio.sleep(CHECK_INTERVAL)
            if not self.running:
                break
            now = time.monotonic()
            for channel, last in list(self._last_seen.items()):
                timeout = self._WATCHDOG_TIMEOUTS.get(channel)
                if timeout is None:
                    continue  # channel has no liveness requirement
                silence = now - last
                if silence > timeout:
                    logger.warning(
                        f"Watchdog: {channel} silent for {silence:.0f}s "
                        f"(> {timeout:.0f}s) — triggering restart"
                    )
                    raise RuntimeError(
                        f"Watchdog timeout: {channel} silent for {silence:.0f}s"
                    )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self):
        if self.running:
            logger.warning("GlobalWarsSubscription already running")
            return
        self.running = True
        logger.info("Starting GlobalWarsSubscription")
        # Reset watchdog timestamps so a fresh start doesn't immediately trip
        import time as _t
        _now = _t.monotonic()
        self._last_seen = {k: _now for k in self._last_seen}
        self._listener_tasks = [
            asyncio.create_task(self._listen_war_attacks()),
            asyncio.create_task(self._listen_war_creates()),
            asyncio.create_task(self._listen_war_updates()),
            asyncio.create_task(self._retry_pending_attacks()),
            asyncio.create_task(self._watchdog()),
        ]
        try:
            # Wait for the FIRST task to finish — any disconnect/crash triggers restart.
            # return_exceptions=False so the first exception propagates to run_forever.
            done, pending = await asyncio.wait(
                self._listener_tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            # Re-raise the first real exception so run_forever() can log it
            for t in done:
                exc = t.exception() if not t.cancelled() else None
                if exc:
                    raise exc
        finally:
            self.running = False
            for t in self._listener_tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*self._listener_tasks, return_exceptions=True)

    async def stop(self):
        self.running = False
        for t in self._listener_tasks:
            t.cancel()
        if self._listener_tasks:
            await asyncio.gather(*self._listener_tasks, return_exceptions=True)
        self._listener_tasks.clear()
        logger.info("GlobalWarsSubscription stopped")

    async def run_forever(self):
        from pnwkit import errors as pnwkit_errors
        while True:
            try:
                await self.start()
                logger.warning("GlobalWarsSubscription ended — restarting in 30s")
            except asyncio.CancelledError:
                logger.info("GlobalWarsSubscription cancelled")
                break
            except (pnwkit_errors.NoReconnect, aiohttp.ClientError,
                    ConnectionResetError, OSError) as e:
                logger.warning(f"GlobalWarsSubscription disconnected ({e}) — restarting in 30s")
            except Exception as e:
                logger.error(f"GlobalWarsSubscription crashed ({e}) — restarting in 30s",
                             exc_info=True)
            finally:
                await self.stop()
            await asyncio.sleep(30)
