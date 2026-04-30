"""Revenue and economic calculations for nation gameplay.

This module contains core economic simulation functions that calculate
nation income, resource production, population effects, and military upkeep.
These functions work with game data and are independent of Discord or database layer.

Reference: pwpedia_data.jsonl for all game mechanics and formulas.
"""

from __future__ import annotations

import json
import logging
import math
from decimal import Decimal
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    import discord

from Systems.Functions.db_paths import NW_WARS_DB_STR as NUKE_WARS_DB_PATH

logger = logging.getLogger(__name__)

# ── Nuke radiation constants ──────────────────────────────────────────────────
# Tested against city 'My' (ID 1298926): in-game pollution=416, best fit=150.75 turns=12.56 days
# Using 150 turns (12.5 days) — closest round number that matches observed game data.
# Fallout Shelter reduces decay time by 25% (wiki confirmed ratio).
NUKE_POLLUTION_BASE  = 400    # pollution added to a city per successful nuke
NUKE_FALLOUT_TURNS   = 133.0  # linear decay — verified against live game data (My/Joy cities)
NUKE_FALLOUT_TURNS_FS = 99.75 # 75% of 133 turns with Fallout Shelter
NUKE_FALLOUT_DAYS    = NUKE_FALLOUT_TURNS / 12.0   # kept for any legacy callers
NUKE_FALLOUT_DAYS_FS = NUKE_FALLOUT_TURNS_FS / 12.0


def calculate_nuke_pollution_for_city(
    city_id: int,
    has_fallout_shelter: bool = False,
    now: Optional[datetime] = None,
    wars_db_path: str = NUKE_WARS_DB_PATH,
) -> float:
    """Calculate current nuke-derived pollution for a single city.

    Uses the same hit-detection logic as war_net_bd.py leaderboard:
      HIT     = att_nukes_lost > 0 AND infra_destroyed > 0 AND defender = this city
      BLOCKED = att_nukes_lost > 0 AND infra_destroyed == 0  (no radiation)

    Fallout: 150 turns (~12.5 real days) linear decay using UTC time.
    75% duration with Fallout Shelter (112.5 turns).
    """
    import sqlite3 as _sqlite3
    if now is None:
        now = datetime.now(timezone.utc)
    fallout_turns = NUKE_FALLOUT_TURNS_FS if has_fallout_shelter else NUKE_FALLOUT_TURNS
    try:
        conn = _sqlite3.connect(wars_db_path)
        conn.row_factory = _sqlite3.Row
        rows = conn.execute(
            """
            SELECT date FROM war_attacks
            WHERE city_id = ?
              AND (type = 'NUKE' OR type = 5)
              AND att_nukes_lost > 0
              AND infra_destroyed > 0
            """,
            (city_id,),
        ).fetchall()
        conn.close()
    except Exception:
        return 0.0
    total = 0.0
    for row in rows:
        try:
            dt = datetime.fromisoformat(str(row['date']).replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            # UTC turns elapsed (1 turn = 2 hours = 7200 seconds)
            turns_elapsed = (now - dt).total_seconds() / 7200.0
            remaining = max(1.0 - turns_elapsed / fallout_turns, 0.0)
            total += NUKE_POLLUTION_BASE * remaining
        except Exception:
            continue
    return total


def get_nuke_pollution_for_nation(
    nation_id: int,
    city_ids: list[int],
    has_fallout_shelter: bool = False,
    now: Optional[datetime] = None,
    wars_db_path: str = NUKE_WARS_DB_PATH,
) -> dict[int, float]:
    """Batch-fetch nuke pollution for all cities of a nation.

    Hit detection (same as war_net_bd.py leaderboard):
      HIT     = infra_destroyed > 0 AND defender_id = our nation/city
      BLOCKED = infra_destroyed == 0  (no radiation, no pollution)

    Checks BOTH offensive and defensive wars:
      - Defensive: attacker nuked us  -> defender_id = our nation, city_id = our city
      - Offensive: we nuked them      -> att_id = our nation (irrelevant for radiation)
      Only nukes WHERE WE ARE THE DEFENDER matter for radiation.

    Two-pass lookup:
      Pass 1: city_id IN our city list (accurate, modern records)
      Pass 2: defender_id = nation_id WHERE city_id IS NULL (older records missing city_id)
              Assigns to the city with the most infra (most likely target).

    Fallout: 100 turns (50 real days) linear decay (75 turns with Fallout Shelter).
    """
    import sqlite3 as _sqlite3
    if not city_ids:
        return {}
    if now is None:
        now = datetime.now(timezone.utc)
    fallout_turns = NUKE_FALLOUT_TURNS_FS if has_fallout_shelter else NUKE_FALLOUT_TURNS
    result = {cid: 0.0 for cid in city_ids}
    try:
        conn = _sqlite3.connect(wars_db_path)
        conn.row_factory = _sqlite3.Row

        # ── Pass 1: known city_id ─────────────────────────────────────────────
        ph = ','.join('?' * len(city_ids))
        rows = conn.execute(
            f"""
            SELECT city_id, date FROM war_attacks
            WHERE city_id IN ({ph})
              AND (type = 'NUKE' OR type = 5)
              AND att_nukes_lost > 0
              AND infra_destroyed > 0
            """,
            city_ids,
        ).fetchall()
        for row in rows:
            cid = row['city_id']
            if cid not in result:
                continue
            try:
                dt = datetime.fromisoformat(str(row['date']).replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                # Use UTC turns elapsed (1 turn = 2 hours = 7200 seconds)
                turns_elapsed = (now - dt).total_seconds() / 7200.0
                remaining = max(1.0 - turns_elapsed / fallout_turns, 0.0)
                result[cid] += NUKE_POLLUTION_BASE * remaining
            except Exception:
                continue

        # ── Pass 2: defender_id match, city_id missing ────────────────────────
        rows2 = conn.execute(
            """
            SELECT date FROM war_attacks
            WHERE defender_id = ?
              AND (type = 'NUKE' OR type = 5)
              AND (city_id IS NULL OR city_id = 0)
              AND infra_destroyed > 0
            """,
            (nation_id,),
        ).fetchall()
        conn.close()
        if rows2 and city_ids:
            fallback = city_ids[0]  # caller should sort cities by infra desc
            for row in rows2:
                try:
                    dt = datetime.fromisoformat(str(row['date']).replace('Z', '+00:00'))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    turns_elapsed = (now - dt).total_seconds() / 7200.0
                    remaining = max(1.0 - turns_elapsed / fallout_turns, 0.0)
                    if remaining > 0:
                        result[fallback] += NUKE_POLLUTION_BASE * remaining
                except Exception:
                    continue
    except Exception:
        pass
    return result




# Simple cache decorator replacement
def cache_game_context(ttl=600):
    """Simple cache decorator for game context data."""
    def decorator(func):
        func._cache = {}
        func._cache_time = {}
        
        async def wrapper(*args, **kwargs):
            import time
            cache_key = str(args) + str(sorted(kwargs.items()))
            current_time = time.time()
            
            if (cache_key in func._cache and 
                cache_key in func._cache_time and 
                current_time - func._cache_time[cache_key] < ttl):
                return func._cache[cache_key]
            
            result = await func(*args, **kwargs)
            func._cache[cache_key] = result
            func._cache_time[cache_key] = current_time
            return result
        
        return wrapper
    return decorator

def weird_division(a: float, b: float) -> float:
    """Handle division with special cases."""
    if b == 0:
        return 0.0
    return a / b


def _normalize_domestic_policy(nation: dict[str, Any]) -> str:
    """Normalize domestic_policy to a canonical uppercase key.

    Handles both API format ('Open Markets') and DB enum format
    ('DomesticPolicy.OPEN_MARKETS').
    Returns e.g. 'OPEN_MARKETS', 'IMPERIALISM', 'MANIFEST_DESTINY'.
    """
    raw = (nation.get('domestic_policy') or '').upper()
    return raw.replace('DOMESTICPOLICY.', '').replace(' ', '_')


@cache_game_context(ttl=600)  # Cache for 10 minutes - game context changes slowly
async def get_cached_game_context(
    call_func,
    get_query_func,
    queries_module,
) -> Tuple[dict[str, float], dict[str, float], list[dict[str, Any]], dict[str, float], dict[str, float]]:
    """Fetch and cache shared game context data.
    
    This function caches the expensive P&W API call that fetches:
    - Color turn bonuses
    - Trade prices  
    - Treasures list
    - Radiation levels
    - Seasonal modifiers
    
    Returns:
        Tuple of (colors, prices, treasures, radiation, seasonal_mod)
        
    Note: Cache TTL is 10 minutes. This data changes slowly so caching
    significantly reduces P&W API load across multiple requests.
    """
    logger.debug("Fetching fresh game context from P&W API (cache miss or expired)")
    
    # Build the GraphQL query
    prices_query = get_query_func(queries_module.PRICES)
    query = f"{{colors{{color turn_bonus}} game_info{{game_date radiation{{global north_america south_america africa europe asia australia antarctica}}}} tradeprices(first:1){{data{prices_query}}} treasures{{bonus nation{{id alliance_id}}}}}}"
    res = await call_func(query)
    
    # Parse color turn bonuses
    res_colors = res['data']['colors']
    colors = {}
    for color in res_colors:
        colors[color['color']] = color['turn_bonus']
    
    # Parse resource prices
    prices = res['data']['tradeprices']['data'][0]
    prices['money'] = 1
    
    treasures = res['data']['treasures']
    game_info = res['data']['game_info']
    
    # Parse radiation by region
    rad = game_info['radiation']
    radiation = {
        "na": (rad['north_america'] + rad['global']) / -1000,
        "sa": (rad['south_america'] + rad['global']) / -1000,
        "eu": (rad['europe'] + rad['global']) / -1000,
        "as": (rad['asia'] + rad['global']) / -1000,
        "af": (rad['africa'] + rad['global']) / -1000,
        "au": (rad['australia'] + rad['global']) / -1000,
        "an": (rad['antarctica'] + rad['global']) / -1000
    }
    
    # Calculate seasonal modifiers based on game month
    month = int(game_info['game_date'][5:7])
    seasonal_mod = {"na": 1, "sa": 1, "eu": 1, "as": 1, "af": 1, "au": 1, "an": 0.5}
    if month in (6, 7, 8):
        seasonal_mod.update({'na': 1.2, 'as': 1.2, 'eu': 1.2, 'sa': 0.8, 'af': 0.8, 'au': 0.8})
    elif month in (12, 1, 2):
        seasonal_mod.update({'na': 0.8, 'as': 0.8, 'eu': 0.8, 'sa': 1.2, 'af': 1.2, 'au': 1.2})
    
    return colors, prices, treasures, radiation, seasonal_mod


async def pre_revenue_calc(
    message: Optional[discord.Message],
    query_for_nation: bool = False,
    nationid: Optional[int | str] = None,
    parsed_nation: Optional[dict[str, Any]] = None,
    call_func=None,
    get_query_func=None,
    queries_module=None,
):
    """Fetch game data needed for revenue calculations.
    
    Retrieves color bonuses, radiation, trade prices, treasures, and game date
    to support comprehensive nation revenue analysis.
    
    Args:
        message: Discord message to edit with status updates
        query_for_nation: If True, fetch nation from P&W API by ID
        nationid: Nation ID to query (used if query_for_nation=True)
        parsed_nation: Pre-fetched nation data (alternative to query_for_nation)
        call_func: Function to call P&W GraphQL API (from api_client)
        get_query_func: Function to build GraphQL queries (from merge_utils)
        queries_module: Queries module with query definitions
        
    Returns:
        Tuple of (nation, colors, prices, treasures, radiation, seasonal_mod)
        
    Note: Game context (colors, prices, treasures, radiation, seasonal_mod) is
    cached for 10 minutes via get_cached_game_context() to reduce API calls.
    """
    if call_func is None or get_query_func is None or queries_module is None:
        raise ValueError("call_func, get_query_func, and queries_module are required")
    
    if query_for_nation:
        nation = (await call_func(
            f"{{nations(first:1 id:{nationid}){{data{get_query_func(queries_module.REVENUE)}}}}}"
        ))['data']['nations']['data']
        if len(nation) == 0:
            raise ValueError("Nation not found in API")
        nation = nation[0]
    else:
        nation = parsed_nation

    if message is not None:
        await message.edit(content="Getting income modifiers...")
    
    # Use cached game context to reduce P&W API calls
    colors, prices, treasures, radiation, seasonal_mod = await get_cached_game_context(
        call_func, get_query_func, queries_module
    )
    
    return nation, colors, prices, treasures, radiation, seasonal_mod


def calculate_nation_modifiers(nation: dict[str, Any]) -> dict[str, float]:
    """Calculate all economic and production modifiers for a nation.
    
    Per PWPedia: Policies, government projects, and infrastructure provide
    various production and cost multipliers.
    
    Args:
        nation: Nation data from P&W API
        
    Returns:
        Dict with modifier values for economics, production, costs, etc.
    """
    modifiers = {
        'max_commerce': 100,
        'base_com': 0,
        'hos_dis_red': 2.5,
        'alu_mod': 1,
        'mun_mod': 1,
        'gas_mod': 1,
        'manu_poll_mod': 1,
        'farm_poll_mod': 1,
        'subw_poll_red': 45,
        'rss_upkeep_mod': 1,
        'ste_mod': 1,
        'rec_poll': 70,
        'pol_cri_red': 2.5,
        'food_land_mod': 500,
        'food_rad_effect_mod': 1,
        'uranium_mod': 1,
        'policy_bonus': 1,
        'mil_cost': 1,
        'new_player_bonus': 1,
    }
    
    # Project modifiers - using correct API field names
    if nation.get('iron_works'):
        modifiers['ste_mod'] = 1.36
    if nation.get('bauxite_works'):
        modifiers['alu_mod'] = 1.36
    if nation.get('arms_stockpile'):
        modifiers['mun_mod'] = 1.2
    if nation.get('emergency_gasoline_reserve'):
        modifiers['gas_mod'] = 2
    if nation.get('mass_irrigation'):
        modifiers['food_land_mod'] = 400
    if nation.get('international_trade_center'):
        modifiers['max_commerce'] = 115
        modifiers['base_com'] = 1
    if nation.get('telecommunications_satellite'):
        modifiers['max_commerce'] = 125
        modifiers['base_com'] += 2
    if nation.get('recycling_initiative'):
        modifiers['rec_poll'] = 75
    if nation.get('green_technologies'):
        modifiers['manu_poll_mod'] = 0.75
        modifiers['farm_poll_mod'] = 0.5
        modifiers['subw_poll_red'] = 70
        modifiers['rss_upkeep_mod'] = 0.9
    if nation.get('clinical_research_center'):
        modifiers['hos_dis_red'] = 3.5
    if nation.get('specialized_police_training_program'):
        modifiers['pol_cri_red'] = 3.5
        modifiers['base_com'] += 4
    if nation.get('uranium_enrichment_program'):
        modifiers['uranium_mod'] = 2
    if nation.get('fallout_shelter'):
        modifiers['food_rad_effect_mod'] = 0.85
    
    # New player bonus
    if nation.get('num_cities', 0) < 21:
        modifiers['new_player_bonus'] = 2.05 - 0.05 * nation['num_cities']
    
    # Domestic policy effects
    # Normalize: DB stores "DomesticPolicy.OPEN_MARKETS", API stores "Open Markets"
    raw_policy = nation.get('domestic_policy', '') or ''
    dp = raw_policy.upper().replace('DOMESTICPOLICY.', '').replace(' ', '_')
    
    if dp in ('OPEN_MARKETS', 'OPENMARKETS'):
        modifiers['policy_bonus'] = 1.01
        if nation.get('government_support_agency'):
            modifiers['policy_bonus'] = 1.015
        if nation.get('bureau_of_domestic_affairs'):
            modifiers['policy_bonus'] = 1.0175
    if dp == 'IMPERIALISM':
        modifiers['mil_cost'] = 0.95
        if nation.get('government_support_agency'):
            modifiers['mil_cost'] = 0.925
        if nation.get('bureau_of_domestic_affairs'):
            modifiers['mil_cost'] = 0.9125
    
    return modifiers


def calculate_power_generation(city: dict[str, Any]) -> dict[str, float]:
    """Calculate power generation and consumption for a city.

    Verified rates from game wiki:
      Wind:    $500/day ($42/turn), powers 250 infra, no pollution, no fuel
      Nuclear: $10,500/day ($875/turn), powers 2000 infra, no pollution,
               consumes 3.0 uranium/day (0.25/turn) per 1000 infra powered
               NOTE: uranium is charged per full 1000-infra block, not scaled
               by actual infra — a plant always consumes 0.5/turn total
               (2 blocks × 0.25) regardless of how much infra it powers.
      Oil:     $1,800/day ($150/turn), powers 500 infra, +6 pollution,
               consumes 1.2 oil/day (0.1/turn) per 100 infra powered
      Coal:    $1,200/day ($100/turn), powers 500 infra, +8 pollution,
               consumes 1.2 coal/day (0.1/turn) per 100 infra powered

    Returns:
        Dict with unpowered_infra, power_upkeep (per turn), and resource
        consumption (per turn, negative values = consumed).
    """
    result = {
        'unpowered_infra': city['infrastructure'],
        'power_upkeep': 0,
        'coal': 0,
        'oil': 0,
        'uranium': 0,
        'pollution': 0,
    }

    # ── Wind power ($41.67/turn exact, 250 infra, no fuel, no pollution) ─────
    for _ in range(city.get('wind_power', 0)):
        if result['unpowered_infra'] > 0:
            result['unpowered_infra'] -= 250
            result['power_upkeep'] += 41.67

    # ── Nuclear power ($875/turn, 2000 infra, 0.5 uranium/turn per plant) ────
    # Uranium: 0.25/turn per 1000-infra block, 2 blocks per plant = 0.5/turn
    # The game charges per full block regardless of actual infra level.
    for _ in range(city.get('nuclear_power', 0)):
        result['power_upkeep'] += 875
        blocks_powered = 0
        for _ in range(2):  # up to 2 blocks of 1000 infra
            if result['unpowered_infra'] > 0:
                infra_powered = min(result['unpowered_infra'], 1000)
                result['unpowered_infra'] -= infra_powered
                blocks_powered += 1
        # Charge 0.25/turn per block actually powered (not scaled by infra within block)
        result['uranium'] -= blocks_powered * 0.25

    # ── Oil power ($150/turn, 500 infra, +6 pollution, 0.1 oil/turn per 100 infra) ──
    for _ in range(city.get('oil_power', 0)):
        result['power_upkeep'] += 150
        result['pollution'] += 6
        for _ in range(5):  # 5 blocks of 100 infra = 500 infra total
            if result['unpowered_infra'] > 0:
                infra_powered = min(result['unpowered_infra'], 100)
                result['unpowered_infra'] -= infra_powered
                result['oil'] -= infra_powered / 100 * 0.1

    # ── Coal power ($100/turn, 500 infra, +8 pollution, 0.1 coal/turn per 100 infra) ─
    for _ in range(city.get('coal_power', 0)):
        result['power_upkeep'] += 100
        result['pollution'] += 8
        for _ in range(5):  # 5 blocks of 100 infra = 500 infra total
            if result['unpowered_infra'] > 0:
                infra_powered = min(result['unpowered_infra'], 100)
                result['unpowered_infra'] -= infra_powered
                result['coal'] -= infra_powered / 100 * 0.1

    return result


def calculate_resource_production(city: dict[str, Any], modifiers: dict[str, float]) -> dict[str, float]:
    """Calculate raw resource production for a city.

    Wiki-verified values (all per-turn unless noted):
      Base production: count × 0.25/turn × stacking_bonus
      Stacking bonus:  1 + ((count - 1) / (limit - 1)) × 0.5
        → at 1 mine:  ×1.00 (no bonus)
        → at limit:   ×1.50 (full 50% bonus)

      Mine       | Base/turn | Upkeep/turn | Pollution | Limit
      -----------|-----------|-------------|-----------|------
      Coal       |   0.25    |    $34      |    +12    |  10
      Oil        |   0.25    |    $50      |    +12    |  10
      Bauxite    |   0.25    |   $134      |    +12    |  10
      Iron       |   0.25    |   $134      |    +12    |  10
      Lead       |   0.25    |   $125      |    +12    |  10
      Uranium    |   0.25    |   $417      |    +20    |   5
    """
    result = {
        'coal':      0.0,
        'oil':       0.0,
        'uranium':   0.0,
        'lead':      0.0,
        'iron':      0.0,
        'bauxite':   0.0,
        'rss_upkeep': 0.0,
        'pollution':  0.0,
    }

    def _mine(count: int, limit: int, modifier: float = 1.0) -> float:
        """Return per-turn production for `count` mines with stacking bonus.
        
        Rounds to 2dp using ROUND_HALF_UP (matching game behaviour) before
        returning, so per-city values accumulate the same way the game does.
        """
        if count <= 0:
            return 0.0
        from decimal import Decimal, ROUND_HALF_UP
        stacking = 1.0 + ((count - 1) / (limit - 1)) * 0.5 if limit > 1 else 1.0
        raw = count * 0.25 * stacking * modifier
        return float(Decimal(str(raw)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

    # ── Coal mines ────────────────────────────────────────────────────────────
    n = city.get('coal_mine', 0)
    if n > 0:
        result['coal']       += _mine(n, 10)
        result['rss_upkeep'] += n * 33.33 * modifiers['rss_upkeep_mod']
        result['pollution']  += n * 12

    # ── Oil wells ─────────────────────────────────────────────────────────────
    n = city.get('oil_well', 0)
    if n > 0:
        result['oil']        += _mine(n, 10)
        result['rss_upkeep'] += n * 50 * modifiers['rss_upkeep_mod']
        result['pollution']  += n * 12

    # ── Bauxite mines ─────────────────────────────────────────────────────────
    n = city.get('bauxite_mine', 0)
    if n > 0:
        result['bauxite']    += _mine(n, 10)
        result['rss_upkeep'] += n * 133.33 * modifiers['rss_upkeep_mod']
        result['pollution']  += n * 12

    # ── Iron mines ────────────────────────────────────────────────────────────
    n = city.get('iron_mine', 0)
    if n > 0:
        result['iron']       += _mine(n, 10)
        result['rss_upkeep'] += n * 133.33 * modifiers['rss_upkeep_mod']
        result['pollution']  += n * 12

    # ── Lead mines ────────────────────────────────────────────────────────────
    n = city.get('lead_mine', 0)
    if n > 0:
        result['lead']       += _mine(n, 10)
        result['rss_upkeep'] += n * 125 * modifiers['rss_upkeep_mod']
        result['pollution']  += n * 12

    # ── Uranium mines ─────────────────────────────────────────────────────────
    n = city.get('uranium_mine', 0)
    if n > 0:
        result['uranium']    += _mine(n, 5, modifiers['uranium_mod'])
        result['rss_upkeep'] += n * 416.67 * modifiers['rss_upkeep_mod']
        result['pollution']  += n * 20

    return result


def calculate_food_production(city: dict[str, Any], nation: dict[str, Any], modifiers: dict[str, float], seasonal_mod: dict[str, float], radiation: dict[str, float]) -> float:
    """Calculate food production per turn for a city.

    Wiki formula (per turn, single farm, no Mass Irrigation):
        food = land / 500

    With Mass Irrigation (food_land_mod = 400):
        food = land / 400

    Stacking bonus (same rule as all resources, limit = 20):
        stacking = 1 + ((farms - 1) / (20 - 1)) × 0.5
        → 1 farm  = ×1.00
        → 20 farms = ×1.50

    Full formula per turn:
        food = (land / food_land_mod) × farms × stacking
               × seasonal_mod × (1 + radiation × food_rad_effect_mod)

    Upkeep: $25/turn per farm ($300/day) — charged in the calling loop.
    Pollution: +2 per farm (×0.5 with Green Technologies).
    Antarctica: 50% food penalty applied via seasonal_mod['an'] = 0.5.
    """
    farms = city.get('farm', 0)
    if farms <= 0:
        return 0.0

    stacking = 1.0 + ((farms - 1) / (20 - 1)) * 0.5 if farms > 1 else 1.0
    continent = (nation.get('continent') or 'na').lower()

    food_per_turn = (
        (city['land'] / modifiers['food_land_mod'])
        * farms
        * stacking
        * seasonal_mod[continent]
        * (1.0 + radiation[continent] * modifiers['food_rad_effect_mod'])
    )
    return max(food_per_turn, 0.0)


def calculate_manufacturing(city: dict[str, Any], modifiers: dict[str, float], unpowered_infra: float) -> dict[str, float]:
    """Calculate manufactured goods production for a city.

    Wiki-verified values (all per-turn):
      Improvement        | Produces  | Base/turn | Consumes/turn      | Upkeep/turn | Pollution | Limit
      -------------------|-----------|-----------|---------------------|-------------|-----------|------
      Oil Refinery       | Gasoline  |  6.0/ref  | 3.0 oil/ref         |    $334     |    +32    |   5
      Steel Mill         | Steel     |  9.0/mill | 3.0 coal+3.0 iron   |    $334     |    +40    |   5
      Aluminum Refinery  | Aluminum  |  9.0/ref  | 3.0 bauxite/ref     |    $209     |    +40    |   5
      Munitions Factory  | Munitions | 18.0/fac  | 6.0 lead/fac        |    $292     |    +32    |   5

    Stacking bonus (limit = 5 for all):
        stacking = 1 + ((count - 1) / (5 - 1)) × 0.5
        → 1 = ×1.00,  5 = ×1.50

    Project modifiers applied to output (and consumption scales with output):
        Emergency Gasoline Reserve: gas_mod = 2.0  (doubles gasoline + oil consumed)
        Iron Works:                 ste_mod = 1.36 (steel + inputs ×1.36)
        Bauxite Works:              alu_mod = 1.36 (aluminum + inputs ×1.36)
        Arms Stockpile:             mun_mod = 1.2  (munitions only, NOT lead consumed)

    Manufacturing halts entirely if any infra is unpowered.
    """
    result = {
        'gasoline':   0.0,
        'steel':      0.0,
        'aluminum':   0.0,
        'munitions':  0.0,
        'coal':       0.0,
        'oil':        0.0,
        'iron':       0.0,
        'bauxite':    0.0,
        'lead':       0.0,
        'rss_upkeep': 0.0,
        'pollution':  0.0,
    }

    if unpowered_infra > 0:
        return result

    from decimal import Decimal, ROUND_HALF_UP
    def _rhup(x: float) -> float:
        """Round to 2dp using ROUND_HALF_UP (matches game per-city rounding)."""
        return float(Decimal(str(x)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

    def _stack(count: int) -> float:
        """Stacking multiplier for manufacturing (limit = 5)."""
        if count <= 1:
            return 1.0
        return 1.0 + ((count - 1) / 4.0) * 0.5

    # ── Oil Refineries → Gasoline ─────────────────────────────────────────────
    n = city.get('oil_refinery', 0)
    if n > 0:
        s = _stack(n)
        # Base rates are DAILY (6 gasoline/day, 3 oil/day per refinery)
        # Divide by 12 to get per-turn; round gross output, leave consumption exact
        output = _rhup(n * 6.0 * s * modifiers['gas_mod'] / 12)
        result['gasoline']   += output
        result['oil']        -= n * 3.0 * s * modifiers['gas_mod'] / 12
        result['rss_upkeep'] += n * 333.33 * modifiers['rss_upkeep_mod']
        result['pollution']  += n * 32  * modifiers['manu_poll_mod']

    # ── Steel Mills → Steel ───────────────────────────────────────────────────
    n = city.get('steel_mill', 0)
    if n > 0:
        s = _stack(n)
        # Base rates are DAILY (9 steel/day, 3 coal + 3 iron/day per mill)
        result['steel']      += _rhup(n * 9.0 * s * modifiers['ste_mod'] / 12)
        result['coal']       -= n * 3.0 * s * modifiers['ste_mod'] / 12
        result['iron']       -= n * 3.0 * s * modifiers['ste_mod'] / 12
        result['rss_upkeep'] += n * 333.33 * modifiers['rss_upkeep_mod']
        result['pollution']  += n * 40  * modifiers['manu_poll_mod']

    # ── Aluminum Refineries → Aluminum ────────────────────────────────────────
    n = city.get('aluminum_refinery', 0)
    if n > 0:
        s = _stack(n)
        # Base rates are DAILY (9 aluminum/day, 3 bauxite/day per refinery)
        result['aluminum']   += _rhup(n * 9.0 * s * modifiers['alu_mod'] / 12)
        result['bauxite']    -= n * 3.0 * s * modifiers['alu_mod'] / 12
        result['rss_upkeep'] += n * 208.33 * modifiers['rss_upkeep_mod']
        result['pollution']  += n * 40  * modifiers['manu_poll_mod']

    # ── Munitions Factories → Munitions ───────────────────────────────────────
    n = city.get('munitions_factory', 0)
    if n > 0:
        s = _stack(n)
        # Base rates are DAILY (18 munitions/day, 6 lead/day per factory)
        # Arms Stockpile boosts munitions output only — lead consumed is NOT boosted
        result['munitions']  += _rhup(n * 18.0 * s * modifiers['mun_mod'] / 12)
        result['lead']       -= n * 6.0  * s / 12
        result['rss_upkeep'] += n * 291.67 * modifiers['rss_upkeep_mod']
        result['pollution']  += n * 32  * modifiers['manu_poll_mod']

    return result


def calculate_civil_improvements(city: dict[str, Any], modifiers: dict[str, float], unpowered_infra: float) -> dict[str, float]:
    """Calculate effects of civil improvements (hospitals, police, mall, etc).

    Verified daily/turn rates from game wiki:
      Police Station:  $750/day  = $63/turn,  +1 pollution,  -2.5% crime
      Hospital:        $1,000/day = $84/turn,  +4 pollution,  -2.5% disease
      Recycling Center:$2,500/day = $209/turn, -70 pollution  (−75 w/ Recycling Initiative)
      Subway:          $3,250/day = $271/turn, -45 pollution  (−70 w/ Green Technologies),
                                               +8 commerce
      Supermarket:     $600/day  = $50/turn,  +4 commerce
      Bank:            $1,800/day = $150/turn, +6 commerce
      Shopping Mall:   $5,400/day = $450/turn, +8 commerce,  +2 pollution
      Stadium:         $12,150/day= $1,013/turn,+10 commerce, +5 pollution
    """
    result = {
        'civil_upkeep': 0,
        'commerce': modifiers['base_com'],
        'pollution': 0,
        'police_stations': 0,
        'hospitals': 0,
    }

    if unpowered_infra > 0:
        return result

    # ── Upkeep (per turn) - Exact decimal values (daily cost ÷ 12) ───────────
    result['civil_upkeep'] += city.get('police_station', 0) * 62.50
    result['civil_upkeep'] += city.get('hospital', 0) * 83.33
    result['civil_upkeep'] += city.get('recycling_center', 0) * 208.33
    result['civil_upkeep'] += city.get('subway', 0) * 270.83
    result['civil_upkeep'] += city.get('supermarket', 0) * 50.00
    result['civil_upkeep'] += city.get('bank', 0) * 150.00
    result['civil_upkeep'] += city.get('shopping_mall', 0) * 450.00
    result['civil_upkeep'] += city.get('stadium', 0) * 1012.50

    # ── Counts for population calculations ───────────────────────────────────
    result['police_stations'] = city.get('police_station', 0)
    result['hospitals'] = city.get('hospital', 0)

    # ── Pollution ─────────────────────────────────────────────────────────────
    result['pollution'] += city.get('police_station', 0) * 1
    result['pollution'] += city.get('hospital', 0) * 4
    result['pollution'] -= city.get('recycling_center', 0) * modifiers['rec_poll']   # 70 or 75
    result['pollution'] -= city.get('subway', 0) * modifiers['subw_poll_red']        # 45 or 70
    result['pollution'] += city.get('shopping_mall', 0) * 2
    result['pollution'] += city.get('stadium', 0) * 5

    # ── Commerce ──────────────────────────────────────────────────────────────
    result['commerce'] += city.get('subway', 0) * 8
    result['commerce'] += city.get('supermarket', 0) * 4
    result['commerce'] += city.get('bank', 0) * 6
    result['commerce'] += city.get('shopping_mall', 0) * 8
    result['commerce'] += city.get('stadium', 0) * 10

    result['raw_commerce'] = result['commerce']
    result['commerce'] = min(result['commerce'], modifiers['max_commerce'])

    return result


def get_city_age_from_game_data(city: dict[str, Any]) -> float:
    """
    Get city age from game data instead of calculating from database dates.
    
    The database dates are often incorrect or not updated properly.
    This function attempts to use actual city age data if available,
    otherwise falls back to database date calculation.
    
    TODO: Implement proper city age fetching from game API or update
    database sync to capture actual city ages instead of just dates.
    """
    
    # Check if city has actual age data (this would need to be added to database sync)
    if 'actual_age_days' in city and city['actual_age_days'] is not None:
        return max(float(city['actual_age_days']), 1.0)
    
    # Check if city has game_age field (alternative field name)
    if 'game_age' in city and city['game_age'] is not None:
        return max(float(city['game_age']), 1.0)
    
    # Fallback: calculate from the stored date using UTC (game server time)
    try:
        date_str = city['date'].split(" ")[0].split("T")[0]
        today_utc = datetime.now(timezone.utc).date()
        city_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        city_age = (today_utc - city_date).days
    except Exception:
        city_age = 1
    
    return max(float(city_age), 1.0)


def calculate_population_effects(city: dict[str, Any], modifiers: dict[str, float], base_pop: float, commerce: float, police_stations: int, hospitals: int, pollution: float) -> dict[str, float]:
    """Calculate population growth, crime, and disease effects.

    Formulas (from PWPedia):

    Crime (%) = ((103 - Commerce)^2 + (Infrastructure * 100)) / 111111 - Police * pol_cri_red
      Note: Commerce here is the capped commerce value (≤ max_commerce).
      Note: 0 ≤ Crime Rate ≤ 100

    Disease Rate = ((((Pop Density^2) * 0.01) - 25) / 100) + (Base Pop / 100000)
                   + Pollution * 0.05 - Hospitals * hos_dis_red
      Pop density = base_pop / land  (uses base population, not displayed population)

    City Age Modifier = 1 + max(ln(age_in_days) / 15, 0)

    Population = (Base Pop
                  - (Disease Rate * Infrastructure)          ← disease deaths
                  - MAX((Crime Rate / 10) * (100 * Infra) - 25, 0)  ← crime deaths
                 ) * City Age Modifier

    Food Consumption = (base_pop^2 / 125_000_000) + ((base_pop * city_age_mod - base_pop) / 850)
    """
    infra = city['infrastructure']

    # ── Crime ────────────────────────────────────────────────────────────────
    crime_rate_raw = (math.pow(103 - commerce, 2) + base_pop) / 111111 - police_stations * modifiers['pol_cri_red']
    crime_rate = max(0.0, min(crime_rate_raw, 100.0))

    # ── Disease ──────────────────────────────────────────────────────────────
    population_density = base_pop / max(city['land'], 1)  # base pop / land
    disease_rate_raw = (
        (((population_density ** 2) * 0.01) - 25) / 100
        + (base_pop / 100000)
        + pollution * 0.05
        - hospitals * modifiers['hos_dis_red']
    )
    disease_rate = max(0.0, min(disease_rate_raw, 100.0))

    # ── City age modifier (improved method) ──────────────────────────────────
    city_age = get_city_age_from_game_data(city)
    city_age_mod = 1.0 + max(math.log(city_age) / 15.0, 0.0)

    # ── Deaths ───────────────────────────────────────────────────────────────
    # Disease deaths = disease_rate * infra  (disease_rate is a %, infra*100 = base_pop)
    disease_deaths = disease_rate * infra
    # Crime deaths = MAX((crime_rate / 10) * (infra * 100) - 25, 0)
    crime_deaths = max((crime_rate / 10.0) * (infra * 100.0) - 25.0, 0.0)

    # ── Population ───────────────────────────────────────────────────────────
    population = math.floor(max((base_pop - disease_deaths - crime_deaths) * city_age_mod, 0.0))

    # ── Food consumption ─────────────────────────────────────────────────────
    # Formula gives DAILY consumption — divide by 12 for per-turn
    # Uses base_pop (not final population) per the formula
    food_consumption = ((base_pop ** 2 / 125_000_000) + ((base_pop * city_age_mod - base_pop) / 850)) / 12

    return {
        'population': population,  # already floored integer
        'crime_rate': crime_rate,
        'crime_rate_raw': crime_rate_raw,
        'disease_rate': disease_rate,
        'disease_rate_raw': disease_rate_raw,
        'food_consumption': food_consumption,
        'city_age_mod': city_age_mod,
    }


def calculate_military_upkeep(nation: dict[str, Any], modifiers: dict[str, float], include_spies: bool = False, is_war: Optional[bool] = None) -> tuple[float, float]:
    """Calculate military unit upkeep and food consumption.

    All base rates are DAILY -- divide by 12 for per-turn.

    Peacetime money upkeep (game-verified):
      Soldiers $1.25/day per unit  | Tanks $50/day  | Aircraft $750/day
      Ships $3,300/day             | Missiles $21,000/day | Nukes $35,000/day
      Spies $2,400/day

    Wartime money upkeep (game-verified from military page):
      Soldiers $1.88/day per unit  | Tanks $75/day  | Aircraft $1,000/day
      Ships $5,000/day             | Missiles $31,500/day | Nukes $52,500/day
      Spies $2,400/day (unchanged)

    Military Research cost reductions (per level, applied to upkeep):
      ground_cost level → soldiers: -$0.02/peace, -$0.03/war per unit per day
                          tanks:    -$1/peace,    -$1.5/war  per unit per day
                          food:     +10 soldiers/food at peace, +15 at war per level
      air_cost    level → aircraft: -$15/peace,   -$10/war   per unit per day
      naval_cost  level → ships:    -$30/peace,   -$50/war   per unit per day

    Food consumption (DAILY, war-aware):
      Peace: soldiers / (750 + 10*ground_cost_lvl) per day
      War:   soldiers / (500 + 15*ground_cost_lvl) per day

    War detection priority:
      1. is_war parameter (explicit override)
      2. nation['wars'] list -- any war with turns_left/turnsleft > 0
      3. offensive_wars_count or defensive_wars_count > 0
    """
    military_upkeep_daily  = 0.0
    food_consumption_daily = 0.0

    # Detect war status
    if is_war is None:
        at_war = False
        for war in nation.get('wars', []):
            if war.get('turns_left', war.get('turnsleft', 0)) > 0:
                at_war = True
                break
        if not at_war:
            if (nation.get('offensive_wars_count') or 0) > 0:
                at_war = True
            elif (nation.get('defensive_wars_count') or 0) > 0:
                at_war = True
    else:
        at_war = is_war

    # Extract military research levels (0 if not present / no MRC project)
    # military_research may be a dict (from API) or a JSON string (from DB)
    _mr_raw = nation.get('military_research') or {}
    if isinstance(_mr_raw, str):
        import json as _json
        try:
            _mr_raw = _json.loads(_mr_raw)
        except Exception:
            _mr_raw = {}
    mr = _mr_raw if isinstance(_mr_raw, dict) else {}
    ground_cost_lvl = int(mr.get('ground_cost', 0) or 0)
    air_cost_lvl    = int(mr.get('air_cost',    0) or 0)
    naval_cost_lvl  = int(mr.get('naval_cost',  0) or 0)

    if include_spies:
        military_upkeep_daily += nation.get('spies', 0) * 2400

    if at_war:
        # Wartime rates with research reductions
        # Soldiers: $1.88/day base, -$0.03/level
        soldier_rate = max(0.0, 1.88 - 0.03 * ground_cost_lvl)
        # Tanks: $75/day base, -$1.5/level
        tank_rate    = max(0.0, 75   - 1.5  * ground_cost_lvl)
        # Aircraft: $1,000/day base, -$10/level
        air_rate     = max(0.0, 1000 - 10   * air_cost_lvl)
        # Ships: $5,000/day base, -$50/level
        ship_rate    = max(0.0, 5000 - 50   * naval_cost_lvl)

        military_upkeep_daily += nation.get('soldiers', 0) * soldier_rate
        military_upkeep_daily += nation.get('tanks',    0) * tank_rate
        military_upkeep_daily += nation.get('aircraft', 0) * air_rate
        military_upkeep_daily += nation.get('ships',    0) * ship_rate
        military_upkeep_daily += nation.get('missiles', 0) * 31500
        military_upkeep_daily += nation.get('nukes',    0) * 52500

        # Food: 1 per (500 + 15*level) soldiers/day
        food_divisor = 500 + 15 * ground_cost_lvl
        food_consumption_daily += nation.get('soldiers', 0) / food_divisor
    else:
        # Peacetime rates with research reductions
        # Soldiers: $1.25/day base, -$0.02/level
        soldier_rate = max(0.0, 1.25 - 0.02 * ground_cost_lvl)
        # Tanks: $50/day base, -$1/level
        tank_rate    = max(0.0, 50   - 1    * ground_cost_lvl)
        # Aircraft: $750/day base, -$15/level
        air_rate     = max(0.0, 750  - 15   * air_cost_lvl)
        # Ships: $3,300/day base, -$30/level
        ship_rate    = max(0.0, 3300 - 30   * naval_cost_lvl)

        military_upkeep_daily += nation.get('soldiers', 0) * soldier_rate
        military_upkeep_daily += nation.get('tanks',    0) * tank_rate
        military_upkeep_daily += nation.get('aircraft', 0) * air_rate
        military_upkeep_daily += nation.get('ships',    0) * ship_rate
        military_upkeep_daily += nation.get('missiles', 0) * 21000
        military_upkeep_daily += nation.get('nukes',    0) * 35000

        # Food: 1 per (750 + 10*level) soldiers/day
        food_divisor = 750 + 10 * ground_cost_lvl
        food_consumption_daily += nation.get('soldiers', 0) / food_divisor

    military_upkeep_per_turn  = military_upkeep_daily  / 12
    food_consumption_per_turn = food_consumption_daily / 12

    return military_upkeep_per_turn, food_consumption_per_turn


def calculate_military_upkeep_from_buildings(city: dict[str, Any]) -> float:
    """Calculate military building maintenance costs.

    Per game wiki: Barracks and Drydocks have NO daily upkeep cost.
    Factories and Hangars also have no upkeep.
    Military building costs are only paid at build time.

    Returns 0.0 — kept as a function so callers don't need to change.
    """
    return 0.0


def calculate_treasure_bonus(nation: dict[str, Any], treasures: list[dict[str, Any]]) -> float:
    """Calculate income multiplier from treasures.
    
    Nation treasures provide direct income bonus, alliance treasures add small bonus.
    
    Args:
        nation: Nation data (for alliance_id)
        treasures: List of all treasures in game
        
    Returns:
        Income multiplier (e.g., 1.05 = 5% bonus)
    """
    nation_treasure_bonus = 1.0
    alliance_treasures = 0
    
    for treasure in treasures:
        if treasure.get('nation') is None:
            continue
        if treasure['nation'].get('id') == nation.get('id'):
            nation_treasure_bonus += treasure.get('bonus', 0) / 100
        if nation.get('alliance') and treasure['nation'].get('alliance_id') == nation.get('alliance_id'):
            alliance_treasures += 1
    
    if alliance_treasures > 0:
        nation_treasure_bonus += math.sqrt(alliance_treasures * 4) / 100
    
    return nation_treasure_bonus


async def revenue_calc(
    message: Optional[discord.Message],
    nation: dict[str, Any],
    radiation: dict[str, float],
    treasures: list[dict[str, Any]],
    prices: dict[str, float],
    colors: dict[str, float],
    seasonal_mod: dict[str, float],
    build: Optional[str] = None,
    single_city: bool = False,
    include_spies: bool = True,
    is_war: Optional[bool] = None,
) -> dict[str, Any]:
    """Calculate complete nation revenue and resource production.
    
    This is the main revenue calculation function that aggregates all city-level
    calculations into nation-wide totals, including resource gains/losses,
    income/expenses, and final net revenue.
    
    Args:
        message: Discord message to edit with status (for UI feedback)
        nation: Complete nation data from P&W API
        radiation: Regional radiation modifiers
        treasures: List of all treasures in game (for bonuses)
        prices: Current market prices for all resources
        colors: Color bonus amounts (money per turn)
        seasonal_mod: Seasonal production modifiers by continent
        build: Optional custom city build as JSON string
        single_city: If True, calculate only one city; if False, all cities
        include_spies: If True, include spy upkeep in calculations
        
    Returns:
        Dict with detailed revenue breakdown including:
        - monetary_net_num: Total money + resource values
        - net_cash_num: Cash-only revenue
        - All resources (food, fuel, etc.)
        - Formatted text fields for embeds
    """
    rss_upkeep = 0.0
    civil_upkeep = 0.0
    military_upkeep = 0.0
    money_income = 0.0
    power_upkeep = 0.0
    nationpop = 0.0
    total_infra = 0
    coal = 0.0
    oil = 0.0
    uranium = 0.0
    lead = 0.0
    iron = 0.0
    bauxite = 0.0
    gasoline = 0.0
    munitions = 0.0
    steel = 0.0
    aluminum = 0.0
    food = 0.0
    
    starve_net_text = ""
    starve_money_text = ""
    starve_exp_text = ""
    color_text = ""
    new_player_text = ""
    policy_bonus_text = ""
    treasure_text = ""
    footer = ""
    
    modifiers = calculate_nation_modifiers(nation)
    
    # Handle custom build input
    if build is not None:
        try:
            build = json.loads(build)
        except json.JSONDecodeError:
            if message is not None:
                await message.edit(content="Something is wrong with the build you sent!")
            return {}
        land = 0
        for city in nation['cities']:
            land += city['land']
        city = {}
        for key, value in build.items():
            city[key[4:]] = int(value)
        city['infrastructure'] = city.pop('a_needed')
        city['land'] = round(land/nation['num_cities'])
        city['powered'] = True
        city['date'] = nation['cities'][math.ceil(nation['num_cities']/2)]['date']
        # Map hangar to airforcebase for build compatibility if needed
        if 'hangars' in city:
            city['airforcebase'] = city['hangars']
        nation['cities'] = [city]
    
     # Pre-fetch nuke radiation for all cities in one DB query
    _has_fs = bool(nation.get('fallout_shelter'))
    _city_ids = [c['id'] for c in nation['cities'] if c.get('id')]
    _nuke_poll = get_nuke_pollution_for_nation(
        nation_id=nation.get('id', 0),
        city_ids=_city_ids,
        has_fallout_shelter=_has_fs,
    )

    # Calculate per-city contributions
    for city in nation['cities']:
        total_infra += city['infrastructure']
        base_pop = city['infrastructure'] * 100
        
        power_result = calculate_power_generation(city)
        power_upkeep += power_result['power_upkeep']
        coal += power_result['coal']
        oil += power_result['oil']
        uranium += power_result['uranium']
        total_pollution = power_result['pollution']
        # Add nuke fallout radiation for this city (decays over 100 turns)
        total_pollution += _nuke_poll.get(city.get('id', 0), 0.0)
        unpowered_infra = power_result['unpowered_infra']
        
        resource_result = calculate_resource_production(city, modifiers)
        rss_upkeep += resource_result['rss_upkeep']
        total_pollution += resource_result['pollution']
        coal += resource_result['coal']
        oil += resource_result['oil']
        uranium += resource_result['uranium']
        lead += resource_result['lead']
        iron += resource_result['iron']
        bauxite += resource_result['bauxite']
        
        farms = city.get('farm', 0)
        if farms > 0:
            rss_upkeep += farms * 25.00 * modifiers['rss_upkeep_mod']  # $300/day ÷ 12 = $25.00/turn
            total_pollution += 2 * farms * modifiers['farm_poll_mod']
            food += calculate_food_production(city, nation, modifiers, seasonal_mod, radiation)
        
        manufacturing_result = calculate_manufacturing(city, modifiers, unpowered_infra)
        rss_upkeep += manufacturing_result['rss_upkeep']
        total_pollution += manufacturing_result['pollution']
        coal += manufacturing_result['coal']
        oil += manufacturing_result['oil']
        iron += manufacturing_result['iron']
        bauxite += manufacturing_result['bauxite']
        lead += manufacturing_result['lead']
        gasoline += manufacturing_result['gasoline']
        steel += manufacturing_result['steel']
        aluminum += manufacturing_result['aluminum']
        munitions += manufacturing_result['munitions']
        
        civil_result = calculate_civil_improvements(city, modifiers, unpowered_infra)
        civil_upkeep += civil_result['civil_upkeep']

        # Military buildings (barracks, factory, hangar, drydock) are
        # counted under Improvement Upkeep in the game
        civil_upkeep += calculate_military_upkeep_from_buildings(city)

        total_pollution += civil_result['pollution']
        commerce = civil_result['commerce']          # capped commerce (≤ max_commerce)
        police_stations = civil_result['police_stations']
        hospitals = civil_result['hospitals']

        city['real_pollution'] = total_pollution
        city['pollution'] = max(total_pollution, 0)
        raw_commerce = civil_result.get('raw_commerce', civil_result['commerce'])
        city['real_commerce'] = raw_commerce
        city['commerce'] = commerce

        # Pass capped commerce — crime formula uses capped value per spec
        pop_result = calculate_population_effects(
            city,
            modifiers,
            base_pop,
            commerce,
            police_stations,
            hospitals,
            city['pollution'],
        )
        # Store raw (uncapped) crime for display purposes only
        crime_rate_raw = (
            (math.pow(103 - raw_commerce, 2) + base_pop) / 111111
            - police_stations * modifiers['pol_cri_red']
        )
        city['real_crime_rate'] = crime_rate_raw
        city['crime_rate'] = max(crime_rate_raw, 0)
        city['real_disease_rate'] = pop_result.get('disease_rate_raw', pop_result['disease_rate'])
        city['disease_rate'] = pop_result['disease_rate']
        nationpop += pop_result['population']
        money_income += ((((commerce / 50) * 0.725) + 0.725) * pop_result['population']) / 12
        food -= pop_result['food_consumption']

    # ── Population correction ─────────────────────────────────────────────────
    # If the API/DB provides the real population, scale our calculated values to match.
    # City age estimation from stored dates drifts from the game's actual age, causing
    # small population errors. Using the authoritative game value fixes display and income.
    api_pop = nation.get('population') or 0
    if api_pop > 0 and nationpop > 0 and not single_city:
        pop_scale = api_pop / nationpop
        money_income *= pop_scale
        nationpop = api_pop

    # Apply nation-level bonuses
    nation_treasure_bonus = calculate_treasure_bonus(nation, treasures)
    if nation_treasure_bonus > 1:
        treasure_text = f"\n\nTreasure Bonus: ${round(money_income * (nation_treasure_bonus - 1)):,}"

    color_bonus = 0.0
    if not single_city:
        nation_color = (nation.get('color') or 'beige').lower()
        color_bonus = colors.get(nation_color, 0.0)
        color_text = f"\n\nColor Trade Bloc Bonus: ${round(color_bonus):,}"
    
    if modifiers['new_player_bonus'] > 1:
        new_player_text = f"\n\nNew Player Bonus: ${round((modifiers['new_player_bonus'] - 1) * money_income):,}"
    
    _dp = _normalize_domestic_policy(nation)
    if modifiers['policy_bonus'] != 1 and _dp == 'OPEN_MARKETS':
        policy_bonus_text = f"\n\nOpen Markets Bonus: ${round(money_income * (modifiers['policy_bonus'] - 1)):,}"
    
    if not single_city:
        military_upkeep_calc, food_consumption = calculate_military_upkeep(nation, modifiers, include_spies, is_war=is_war)
        military_upkeep += military_upkeep_calc
        food -= food_consumption
    else:
        # single_city: building upkeep already added above; no unit upkeep
        pass
    
    military_upkeep *= modifiers['mil_cost']
    if modifiers['mil_cost'] != 1 and _dp == 'IMPERIALISM':
        policy_bonus_text = f"\n\nImperialism Bonus: ${round(military_upkeep * (1 - modifiers['mil_cost'])):,}"
    
    # Check for starvation penalty
    if food < 0:
        starve_exp_text = f"\n\nPossible Starvation Penalty: ${round(money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * 0.33):,}*"
        starve_money_text = f" (${round(money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * 0.67 + color_bonus - power_upkeep - rss_upkeep - military_upkeep - civil_upkeep):,}*)"
        starve_net_text = f" (${round(money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * 0.67 + color_bonus - power_upkeep - rss_upkeep - military_upkeep - civil_upkeep + coal * prices['coal'] + oil * prices['oil'] + uranium * prices['uranium'] + lead * prices['lead'] + iron * prices['iron'] + bauxite * prices['bauxite'] + gasoline * prices['gasoline'] + munitions * prices['munitions'] + steel * prices['steel'] + aluminum * prices['aluminum'] + food * prices['food']):,}*)"
        footer = "* The income if the nation is suffering from a starvation penalty"
    
    max_infra = 0
    if nation.get('cities'):
        max_infra = sorted(nation['cities'], key=lambda k: k.get('infrastructure', 0), reverse=True)[0].get('infrastructure', 0)
    
    if single_city:
        rev_obj = nation['cities'][0]
    else:
        rev_obj = {}
    
    rev_obj['monetary_net_num'] = round(
        money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * nation_treasure_bonus
        + color_bonus - power_upkeep - rss_upkeep - military_upkeep - civil_upkeep
        + coal * prices['coal'] + oil * prices['oil'] + uranium * prices['uranium']
        + lead * prices['lead'] + iron * prices['iron'] + bauxite * prices['bauxite']
        + gasoline * prices['gasoline'] + munitions * prices['munitions']
        + steel * prices['steel'] + aluminum * prices['aluminum'] + food * prices['food']
    )
    rev_obj['net_cash_num'] = round(
        money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * nation_treasure_bonus
        + color_bonus - power_upkeep - rss_upkeep - military_upkeep - civil_upkeep
    )
    rev_obj['food'] = food
    rev_obj['aluminum'] = aluminum
    rev_obj['bauxite'] = bauxite
    rev_obj['coal'] = coal
    rev_obj['gasoline'] = gasoline
    rev_obj['iron'] = iron
    rev_obj['lead'] = lead
    rev_obj['munitions'] = munitions
    rev_obj['oil'] = oil
    rev_obj['steel'] = steel
    rev_obj['uranium'] = uranium
    
    if single_city and not build:
        rev_obj['money'] = rev_obj['net_cash_num']
        rev_obj['net income'] = rev_obj['monetary_net_num']
        rev_obj['disease_rate'] = city['disease_rate']
        rev_obj['crime_rate'] = city['crime_rate']
        rev_obj['commerce'] = city['commerce']
        rev_obj['pollution'] = city['pollution']
        rev_obj['population'] = pop_result['population']
        return rev_obj
    else:
        rev_obj['nation'] = nation
    
    rev_obj['footer'] = footer
    rev_obj['max_infra'] = max_infra
    rev_obj['avg_infra'] = round(total_infra / nation['num_cities']) if nation.get('num_cities') else 0
    # Expose gross money income (before expenses, after policy/treasure/color bonuses)
    # This is what alliance tax is applied to
    rev_obj['gross_money_income'] = round(
        money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * nation_treasure_bonus
        + color_bonus
    )
    # Expose raw components for embed formatting
    rev_obj['nationpop'] = round(nationpop)
    rev_obj['color_bonus_turn'] = color_bonus
    rev_obj['military_upkeep_turn'] = military_upkeep
    rev_obj['improvement_upkeep_turn'] = civil_upkeep + power_upkeep + rss_upkeep
    rev_obj['power_upkeep_turn'] = power_upkeep
    rev_obj['rss_upkeep_turn'] = rss_upkeep
    rev_obj['prices'] = prices
    rev_obj['income_txt'] = f"National Tax Revenue: ${round(money_income):,}{color_text}{new_player_text}{policy_bonus_text}{treasure_text}\n\u200b"
    rev_obj['expenses_txt'] = f"Power Plant Upkeep: ${round(power_upkeep):,}\n\nResource Prod. Upkeep: ${round(rss_upkeep):,}\n\nMilitary Upkeep: ${round(military_upkeep):,}\n\nCity Improvement Upkeep: ${round(civil_upkeep):,}{starve_exp_text}\n\u200b"
    rev_obj['net_rev_txt'] = f"Coal: {round(coal):,}\nOil: {round(oil):,}\nUranium: {round(uranium):,}\nLead: {round(lead):,}\nIron: {round(iron):,}\nBauxite: {round(bauxite):,}\nGasoline: {round(gasoline):,}\nMunitions: {round(munitions):,}\nSteel: {round(steel):,}\nAluminum: {round(aluminum):,}\nFood: {round(food):,}\nMoney: ${round(money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * nation_treasure_bonus + color_bonus - power_upkeep - rss_upkeep - military_upkeep - civil_upkeep):,}{starve_money_text}\n\u200b"
    rev_obj['mon_net_txt'] = f"${round(money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * nation_treasure_bonus + color_bonus - power_upkeep - rss_upkeep - military_upkeep - civil_upkeep + coal * prices['coal'] + oil * prices['oil'] + uranium * prices['uranium'] + lead * prices['lead'] + iron * prices['iron'] + bauxite * prices['bauxite'] + gasoline * prices['gasoline'] + munitions * prices['munitions'] + steel * prices['steel'] + aluminum * prices['aluminum'] + food * prices['food']):,}{starve_net_text}"
    rev_obj['money_txt'] = f"${round(money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * nation_treasure_bonus + color_bonus - power_upkeep - rss_upkeep - military_upkeep - civil_upkeep):,}{starve_money_text}"
    
    return rev_obj


def revenue_calc_sync(
    nation: dict[str, Any],
    radiation: dict[str, float],
    treasures: list[dict[str, Any]],
    prices: dict[str, float],
    colors: dict[str, float],
    seasonal_mod: dict[str, float],
    build: Optional[str] = None,
    single_city: bool = False,
    include_spies: bool = True,
    is_war: Optional[bool] = None,
) -> dict[str, Any]:
    """Synchronous revenue calculation for non-Discord contexts (e.g. API routes).

    Identical calculation logic to :func:`revenue_calc`, but avoids the
    async/await overhead of creating and tearing down an event loop for every
    call.  Use this in Flask routes or other synchronous code where Discord
    message editing is not needed.

    Args:
        nation: Complete nation data from P&W API
        radiation: Regional radiation modifiers
        treasures: List of all treasures in game (for bonuses)
        prices: Current market prices for all resources
        colors: Color bonus amounts (money per turn)
        seasonal_mod: Seasonal production modifiers by continent
        build: Optional custom city build as JSON string
        single_city: If True, calculate only one city; if False, all cities
        include_spies: If True, include spy upkeep in calculations

    Returns:
        Dict with detailed revenue breakdown including:
        - monetary_net_num: Total money + resource values
        - net_cash_num: Cash-only revenue
        - All resources (food, fuel, etc.)
        - Formatted text fields for embeds
    """
    rss_upkeep = 0.0
    civil_upkeep = 0.0
    military_upkeep = 0.0
    money_income = 0.0
    power_upkeep = 0.0
    nationpop = 0.0
    total_infra = 0
    coal = 0.0
    oil = 0.0
    uranium = 0.0
    lead = 0.0
    iron = 0.0
    bauxite = 0.0
    gasoline = 0.0
    munitions = 0.0
    steel = 0.0
    aluminum = 0.0
    food = 0.0

    starve_net_text = ""
    starve_money_text = ""
    starve_exp_text = ""
    color_text = ""
    new_player_text = ""
    policy_bonus_text = ""
    treasure_text = ""
    footer = ""

    modifiers = calculate_nation_modifiers(nation)

    # Handle custom build input
    if build is not None:
        try:
            build = json.loads(build)
        except json.JSONDecodeError:
            return {}
        land = 0
        for city in nation['cities']:
            land += city['land']
        city = {}
        for key, value in build.items():
            city[key[4:]] = int(value)
        city['infrastructure'] = city.pop('a_needed')
        city['land'] = round(land/nation['num_cities'])
        city['powered'] = True
        city['date'] = nation['cities'][math.ceil(nation['num_cities']/2)]['date']
        # Map hangar to airforcebase for build compatibility if needed
        if 'hangars' in city:
            city['airforcebase'] = city['hangars']
        nation['cities'] = [city]

     # Pre-fetch nuke radiation for all cities in one DB query
    _has_fs = bool(nation.get('fallout_shelter'))
    _city_ids = [c['id'] for c in nation['cities'] if c.get('id')]
    _nuke_poll = get_nuke_pollution_for_nation(
        nation_id=nation.get('id', 0),
        city_ids=_city_ids,
        has_fallout_shelter=_has_fs,
    )

    # Calculate per-city contributions
    for city in nation['cities']:
        total_infra += city['infrastructure']
        base_pop = city['infrastructure'] * 100

        power_result = calculate_power_generation(city)
        power_upkeep += power_result['power_upkeep']
        coal += power_result['coal']
        oil += power_result['oil']
        uranium += power_result['uranium']
        total_pollution = power_result['pollution']
        # Add nuke fallout radiation for this city (decays over 100 turns)
        total_pollution += _nuke_poll.get(city.get('id', 0), 0.0)
        unpowered_infra = power_result['unpowered_infra']

        resource_result = calculate_resource_production(city, modifiers)
        rss_upkeep += resource_result['rss_upkeep']
        total_pollution += resource_result['pollution']
        coal += resource_result['coal']
        oil += resource_result['oil']
        uranium += resource_result['uranium']
        lead += resource_result['lead']
        iron += resource_result['iron']
        bauxite += resource_result['bauxite']

        farms = city.get('farm', 0)
        if farms > 0:
            rss_upkeep += farms * 25.00 * modifiers['rss_upkeep_mod']  # $300/day ÷ 12 = $25.00/turn
            total_pollution += 2 * farms * modifiers['farm_poll_mod']
            food += calculate_food_production(city, nation, modifiers, seasonal_mod, radiation)

        manufacturing_result = calculate_manufacturing(city, modifiers, unpowered_infra)
        rss_upkeep += manufacturing_result['rss_upkeep']
        total_pollution += manufacturing_result['pollution']
        coal += manufacturing_result['coal']
        oil += manufacturing_result['oil']
        iron += manufacturing_result['iron']
        bauxite += manufacturing_result['bauxite']
        lead += manufacturing_result['lead']
        gasoline += manufacturing_result['gasoline']
        steel += manufacturing_result['steel']
        aluminum += manufacturing_result['aluminum']
        munitions += manufacturing_result['munitions']

        civil_result = calculate_civil_improvements(city, modifiers, unpowered_infra)
        civil_upkeep += civil_result['civil_upkeep']

        # Military buildings (barracks, factory, hangar, drydock) are
        # counted under Improvement Upkeep in the game
        civil_upkeep += calculate_military_upkeep_from_buildings(city)

        total_pollution += civil_result['pollution']
        commerce = civil_result['commerce']          # capped commerce (≤ max_commerce)
        police_stations = civil_result['police_stations']
        hospitals = civil_result['hospitals']

        city['real_pollution'] = total_pollution
        city['pollution'] = max(total_pollution, 0)
        raw_commerce = civil_result.get('raw_commerce', civil_result['commerce'])
        city['real_commerce'] = raw_commerce
        city['commerce'] = commerce

        # Pass capped commerce — crime formula uses capped value per spec
        pop_result = calculate_population_effects(
            city,
            modifiers,
            base_pop,
            commerce,
            police_stations,
            hospitals,
            city['pollution'],
        )
        # Store raw (uncapped) crime for display purposes only
        crime_rate_raw = (
            (math.pow(103 - raw_commerce, 2) + base_pop) / 111111
            - police_stations * modifiers['pol_cri_red']
        )
        city['real_crime_rate'] = crime_rate_raw
        city['crime_rate'] = max(crime_rate_raw, 0)
        city['real_disease_rate'] = pop_result.get('disease_rate_raw', pop_result['disease_rate'])
        city['disease_rate'] = pop_result['disease_rate']
        nationpop += pop_result['population']
        money_income += ((((commerce / 50) * 0.725) + 0.725) * pop_result['population']) / 12
        food -= pop_result['food_consumption']

    # ── Population correction ─────────────────────────────────────────────────
    # If the API/DB provides the real population, scale our calculated values to match.
    # City age estimation from stored dates drifts from the game's actual age, causing
    # small population errors. Using the authoritative game value fixes display and income.
    api_pop = nation.get('population') or 0
    if api_pop > 0 and nationpop > 0 and not single_city:
        pop_scale = api_pop / nationpop
        money_income *= pop_scale
        nationpop = api_pop

    # Apply nation-level bonuses
    nation_treasure_bonus = calculate_treasure_bonus(nation, treasures)
    if nation_treasure_bonus > 1:
        treasure_text = f"\n\nTreasure Bonus: ${round(money_income * (nation_treasure_bonus - 1)):,}"

    color_bonus = 0.0
    if not single_city:
        nation_color = (nation.get('color') or 'beige').lower()
        color_bonus = colors.get(nation_color, 0.0)
        color_text = f"\n\nColor Trade Bloc Bonus: ${round(color_bonus):,}"

    if modifiers['new_player_bonus'] > 1:
        new_player_text = f"\n\nNew Player Bonus: ${round((modifiers['new_player_bonus'] - 1) * money_income):,}"

    _dp = _normalize_domestic_policy(nation)
    if modifiers['policy_bonus'] != 1 and _dp == 'OPEN_MARKETS':
        policy_bonus_text = f"\n\nOpen Markets Bonus: ${round(money_income * (modifiers['policy_bonus'] - 1)):,}"

    if not single_city:
        military_upkeep_calc, food_consumption = calculate_military_upkeep(nation, modifiers, include_spies, is_war=is_war)
        military_upkeep += military_upkeep_calc
        food -= food_consumption
    else:
        # single_city: building upkeep already added above; no unit upkeep
        pass

    military_upkeep *= modifiers['mil_cost']
    if modifiers['mil_cost'] != 1 and _dp == 'IMPERIALISM':
        policy_bonus_text = f"\n\nImperialism Bonus: ${round(military_upkeep * (1 - modifiers['mil_cost'])):,}"

    # Check for starvation penalty
    if food < 0:
        starve_exp_text = f"\n\nPossible Starvation Penalty: ${round(money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * 0.33):,}*"
        starve_money_text = f" (${round(money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * 0.67 + color_bonus - power_upkeep - rss_upkeep - military_upkeep - civil_upkeep):,}*)"
        starve_net_text = f" (${round(money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * 0.67 + color_bonus - power_upkeep - rss_upkeep - military_upkeep - civil_upkeep + coal * prices['coal'] + oil * prices['oil'] + uranium * prices['uranium'] + lead * prices['lead'] + iron * prices['iron'] + bauxite * prices['bauxite'] + gasoline * prices['gasoline'] + munitions * prices['munitions'] + steel * prices['steel'] + aluminum * prices['aluminum'] + food * prices['food']):,}*)"
        footer = "* The income if the nation is suffering from a starvation penalty"

    max_infra = 0
    if nation.get('cities'):
        max_infra = sorted(nation['cities'], key=lambda k: k.get('infrastructure', 0), reverse=True)[0].get('infrastructure', 0)

    if single_city:
        rev_obj = nation['cities'][0]
    else:
        rev_obj = {}

    rev_obj['monetary_net_num'] = round(
        money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * nation_treasure_bonus
        + color_bonus - power_upkeep - rss_upkeep - military_upkeep - civil_upkeep
        + coal * prices['coal'] + oil * prices['oil'] + uranium * prices['uranium']
        + lead * prices['lead'] + iron * prices['iron'] + bauxite * prices['bauxite']
        + gasoline * prices['gasoline'] + munitions * prices['munitions']
        + steel * prices['steel'] + aluminum * prices['aluminum'] + food * prices['food']
    )
    rev_obj['net_cash_num'] = round(
        money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * nation_treasure_bonus
        + color_bonus - power_upkeep - rss_upkeep - military_upkeep - civil_upkeep
    )
    rev_obj['food'] = food
    rev_obj['aluminum'] = aluminum
    rev_obj['bauxite'] = bauxite
    rev_obj['coal'] = coal
    rev_obj['gasoline'] = gasoline
    rev_obj['iron'] = iron
    rev_obj['lead'] = lead
    rev_obj['munitions'] = munitions
    rev_obj['oil'] = oil
    rev_obj['steel'] = steel
    rev_obj['uranium'] = uranium

    if single_city and not build:
        rev_obj['money'] = rev_obj['net_cash_num']
        rev_obj['net income'] = rev_obj['monetary_net_num']
        rev_obj['disease_rate'] = city['disease_rate']
        rev_obj['crime_rate'] = city['crime_rate']
        rev_obj['commerce'] = city['commerce']
        rev_obj['pollution'] = city['pollution']
        rev_obj['population'] = pop_result['population']
        return rev_obj
    else:
        rev_obj['nation'] = nation

    rev_obj['footer'] = footer
    rev_obj['max_infra'] = max_infra
    rev_obj['avg_infra'] = round(total_infra / nation['num_cities']) if nation.get('num_cities') else 0
    # Expose gross money income (before expenses, after policy/treasure/color bonuses)
    rev_obj['gross_money_income'] = round(
        money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * nation_treasure_bonus
        + color_bonus
    )
    # Expose raw components for embed formatting (mirrors revenue_calc)
    rev_obj['nationpop'] = round(nationpop)
    rev_obj['color_bonus_turn'] = color_bonus
    rev_obj['military_upkeep_turn'] = military_upkeep
    rev_obj['improvement_upkeep_turn'] = civil_upkeep + power_upkeep + rss_upkeep
    rev_obj['power_upkeep_turn'] = power_upkeep
    rev_obj['rss_upkeep_turn'] = rss_upkeep
    rev_obj['income_txt'] = f"National Tax Revenue: ${round(money_income):,}{color_text}{new_player_text}{policy_bonus_text}{treasure_text}\n\u200b"
    rev_obj['expenses_txt'] = f"Power Plant Upkeep: ${round(power_upkeep):,}\n\nResource Prod. Upkeep: ${round(rss_upkeep):,}\n\nMilitary Upkeep: ${round(military_upkeep):,}\n\nCity Improvement Upkeep: ${round(civil_upkeep):,}{starve_exp_text}\n\u200b"
    rev_obj['net_rev_txt'] = f"Coal: {round(coal):,}\nOil: {round(oil):,}\nUranium: {round(uranium):,}\nLead: {round(lead):,}\nIron: {round(iron):,}\nBauxite: {round(bauxite):,}\nGasoline: {round(gasoline):,}\nMunitions: {round(munitions):,}\nSteel: {round(steel):,}\nAluminum: {round(aluminum):,}\nFood: {round(food):,}\nMoney: ${round(money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * nation_treasure_bonus + color_bonus - power_upkeep - rss_upkeep - military_upkeep - civil_upkeep):,}{starve_money_text}\n\u200b"
    rev_obj['mon_net_txt'] = f"${round(money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * nation_treasure_bonus + color_bonus - power_upkeep - rss_upkeep - military_upkeep - civil_upkeep + coal * prices['coal'] + oil * prices['oil'] + uranium * prices['uranium'] + lead * prices['lead'] + iron * prices['iron'] + bauxite * prices['bauxite'] + gasoline * prices['gasoline'] + munitions * prices['munitions'] + steel * prices['steel'] + aluminum * prices['aluminum'] + food * prices['food']):,}{starve_net_text}"
    rev_obj['money_txt'] = f"${round(money_income * modifiers['policy_bonus'] * modifiers['new_player_bonus'] * nation_treasure_bonus + color_bonus - power_upkeep - rss_upkeep - military_upkeep - civil_upkeep):,}{starve_money_text}"

    return rev_obj

async def calculate_full_revenue_with_query(
    nation_data: Dict[str, Any],
    query_instance: Optional['V3GraphQuery'] = None,
    is_war: bool = False,
    radiation_index: float = 1000.0,
    domestic_policy: Optional[str] = None,
    color_bonus: float = 0.0,
    is_food_winter: bool = False,
    is_food_summer: bool = False,
    market_prices: Optional[Dict[str, float]] = None,
    game_date: Optional[datetime] = None,
    override_tax_rate: Optional[float] = None,  # 0.0–1.0 decimal, overrides DB bracket lookup
) -> Dict[str, Any]:
    """Compatibility wrapper for the revenue calculation system.
    
    This function bridges the gap between the old interface and the new modular
    revenue calculation system. It fetches the required game context and calls
    the correct revenue calculation functions.
    """
    from Systems.Functions.database_manager import get_latest_resource_prices, get_latest_game_info, get_latest_game_data
    
    # --- Market prices: DB first, API fallback ---
    if market_prices is None:
        try:
            price_data = await get_latest_resource_prices()
            if price_data:
                market_prices = {res: p['sell'] for res, p in price_data.items()}
            else:
                raise ValueError("no db prices")
        except Exception:
            if query_instance is None:
                from .query import create_v3_query_instance
                query_instance = create_v3_query_instance()
            trade_prices = await query_instance.get_trade_resource_values()
            market_prices = {item['resource'].lower(): item['best_sell_offer']['price'] for item in trade_prices or [] if item.get('best_sell_offer')}
    
    # --- Game date: DB first, fallback to now ---
    if game_date is None:
        try:
            gi = await get_latest_game_info()
            if gi and gi.get('game_date'):
                parsed = datetime.fromisoformat(gi['game_date'].replace("Z", "+00:00"))
                game_date = parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
        except Exception:
            pass
        if game_date is None:
            game_date = datetime.now(timezone.utc)
    
    # --- Colors: DB first, API fallback ---
    colors = {}
    try:
        colors_data = await get_latest_game_data("colors")
        if colors_data:
            colors = {c['color']: c['turn_bonus'] for c in colors_data}
    except Exception:
        if query_instance is None:
            from .query import create_v3_query_instance
            query_instance = create_v3_query_instance()
        try:
            color_info = await query_instance.get_color_info()
            if color_info:
                colors = {c['color']: c['turn_bonus'] for c in color_info}
        except Exception:
            pass
    
    # --- Treasures: Check nation data first, then skip API call ---
    treasures = []
    # Note: Treasures are now stored with nations in the database, so we don't need to query for them
    # The nation data from the database should already include treasure information if the nation has one
    
    # --- Radiation: DB first, fallback to defaults ---
    radiation = {'na': 0, 'sa': 0, 'eu': 0, 'as': 0, 'af': 0, 'au': 0, 'an': 0}
    try:
        from Systems.Functions.database_manager import get_latest_radiation_data
        radiation_data = await get_latest_radiation_data()
        if radiation_data:
            # Map database keys to expected keys with proper formula (global + regional) / -1000
            global_rad = radiation_data.get('global', 0)
            radiation = {
                'na': (radiation_data.get('north_america', 0) + global_rad) / -1000,
                'sa': (radiation_data.get('south_america', 0) + global_rad) / -1000,
                'eu': (radiation_data.get('europe', 0) + global_rad) / -1000,
                'as': (radiation_data.get('asia', 0) + global_rad) / -1000,
                'af': (radiation_data.get('africa', 0) + global_rad) / -1000,
                'au': (radiation_data.get('australia', 0) + global_rad) / -1000,
                'an': (radiation_data.get('antarctica', 0) + global_rad) / -1000
            }
    except Exception as e:
        # Fallback to default values if database read fails
        pass
    
    # --- Seasonal modifiers: Calculate from game date ---
    seasonal_mod = {'na': 1, 'sa': 1, 'eu': 1, 'as': 1, 'af': 1, 'au': 1, 'an': 0.5}
    if game_date:
        month = game_date.month
        if month in (6, 7, 8):  # Summer in Northern Hemisphere
            seasonal_mod.update({'na': 1.2, 'as': 1.2, 'eu': 1.2, 'sa': 0.8, 'af': 0.8, 'au': 0.8})
        elif month in (12, 1, 2):  # Winter in Northern Hemisphere
            seasonal_mod.update({'na': 0.8, 'as': 0.8, 'eu': 0.8, 'sa': 1.2, 'af': 1.2, 'au': 1.2})
    
    # Calculate revenue using the correct function
    result = await revenue_calc(
        message=None,
        nation=nation_data,
        radiation=radiation,
        treasures=treasures,
        prices=market_prices or {},
        colors=colors,
        seasonal_mod=seasonal_mod,
        build=None,
        single_city=False,
        include_spies=True,
        is_war=is_war if is_war else None,
    )

    # --- Alliance tax: override if provided, else look up from DB ---
    alliance_tax_rate = 0.10   # default 10%
    resource_tax_rate = 0.10   # default 10%

    if override_tax_rate is not None:
        alliance_tax_rate = float(override_tax_rate)
        resource_tax_rate = float(override_tax_rate)
    else:
        try:
            from Systems.Functions.irs_nations_db import IRSNationsDB
            from Systems.Functions.db_paths import NW_NATIONS_DB
            if NW_NATIONS_DB.exists():
                _db = IRSNationsDB(str(NW_NATIONS_DB))
                alliance_id = nation_data.get("alliance_id") or (
                    nation_data.get("alliance", {}) or {}
                ).get("id")
                tax_id = nation_data.get("tax_id")
                if alliance_id and tax_id is not None:
                    bracket = await _db.get_tax_bracket_for_nation(int(alliance_id), int(tax_id))
                    if bracket:
                        alliance_tax_rate = float(bracket.get("tax_rate", 10)) / 100.0
                        resource_tax_rate = float(bracket.get("resource_tax_rate", bracket.get("tax_rate", 10))) / 100.0
        except Exception:
            pass

    # Calculate tax amounts (informational only — NOT deducted from gross income)
    gross_income = result.get('net_cash_num', 0)
    money_tax_turn = max(0.0, gross_income * alliance_tax_rate) if alliance_tax_rate > 0 else 0.0
    resource_tax_value_turn = sum(
        max(0.0, result.get(r, 0)) * (market_prices or {}).get(r, 0) * resource_tax_rate
        for r in ('coal', 'oil', 'uranium', 'lead', 'iron', 'bauxite',
                  'gasoline', 'munitions', 'steel', 'aluminum', 'food')
    ) if resource_tax_rate > 0 else 0.0
    alliance_tax_turn = money_tax_turn + resource_tax_value_turn

    # Net income after tax (for reference only — embed shows gross)
    net_income_after_tax = gross_income - money_tax_turn

    # Convert result to match expected interface
    return {
        'net_income': net_income_after_tax,          # after-tax (for reference)
        'gross_income': gross_income,                 # pre-tax (shown in embed)
        'monetary_net_num': result.get('monetary_net_num', 0),
        'alliance_tax_turn': alliance_tax_turn,
        'alliance_tax_money_turn': money_tax_turn,
        'alliance_tax_resource_turn': resource_tax_value_turn,
        'alliance_tax_rate': alliance_tax_rate,
        'resource_tax_rate': resource_tax_rate,
        'expenses': {'total': 0},
        # Raw component values (per turn) for embed formatting
        'nationpop': result.get('nationpop', 0),
        'color_bonus_turn': result.get('color_bonus_turn', 0),
        'military_upkeep_turn': result.get('military_upkeep_turn', 0),
        'improvement_upkeep_turn': result.get('improvement_upkeep_turn', 0),
        'power_upkeep_turn': result.get('power_upkeep_turn', 0),
        'rss_upkeep_turn': result.get('rss_upkeep_turn', 0),
        'prices': result.get('prices', market_prices or {}),
        'resources': {
            'food': result.get('food', 0),
            'coal': result.get('coal', 0),
            'oil': result.get('oil', 0),
            'uranium': result.get('uranium', 0),
            'lead': result.get('lead', 0),
            'iron': result.get('iron', 0),
            'bauxite': result.get('bauxite', 0),
            'gasoline': result.get('gasoline', 0),
            'munitions': result.get('munitions', 0),
            'steel': result.get('steel', 0),
            'aluminum': result.get('aluminum', 0),
        },
        'formatted_output': {
            'income_txt': result.get('income_txt', ''),
            'expenses_txt': result.get('expenses_txt', ''),
            'net_rev_txt': result.get('net_rev_txt', ''),
            'mon_net_txt': result.get('mon_net_txt', ''),
            'money_txt': result.get('money_txt', ''),
        }
    }