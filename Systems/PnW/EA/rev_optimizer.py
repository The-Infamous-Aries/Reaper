"""Revenue Optimizer — full economic brain for P&W nations.

Finds every profitable action a nation can take to increase cash AND resource
revenue, ranked by daily gain. Uses full game mechanics from rev_correct.py.

Key design decisions:
  - Civil/commerce improvements: cash baseline (they don't produce resources)
  - Resource improvements: monetary baseline (cash + resources @ market prices)
    Only suggested if the nation already produces that resource OR has all
    required inputs (no point making steel without coal + iron supply)
  - Infrastructure: only suggested if ROI ≤ 90 days (destroyable in war)
  - Land: suggested up to 365 days ROI (permanent, compounds); best increment
  - Projects: resource-boosting use monetary baseline, others use cash
    Project cost (money + resources @ market) used to calculate payoff
  - All gains are fully simulated — no approximations
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import discord
from discord.ext import commands
from discord import app_commands
from pathlib import Path

from Systems.PnW.Util.rev_correct import (
    calculate_nation_modifiers,
    calculate_power_generation,
    calculate_resource_production,
    calculate_manufacturing,
    calculate_civil_improvements,
    calculate_population_effects,
    revenue_calc_sync,
)
from Systems.PnW.IA.costs import (
    calc_land_value, calc_infra_value, PROJECT_BUILD_COSTS,
    calculate_project_discounts,
)
from Systems.PnW.Util.war_calc import IMPROVEMENT_COSTS
from Systems.Functions.nation_emoji_store import get_nation_emoji, strip_emoji_prefix
from Systems.PnW.Util.query import create_v3_query_instance, V3GraphQuery

logger = logging.getLogger(__name__)

# ── Game constants ─────────────────────────────────────────────────────────────

IMPROVEMENT_LIMITS = {
    'coal_mine': 10, 'oil_well': 10, 'bauxite_mine': 10,
    'iron_mine': 10, 'lead_mine': 10, 'uranium_mine': 5,
    'farm': 20,
    'oil_refinery': 5, 'steel_mill': 5, 'aluminum_refinery': 5, 'munitions_factory': 5,
    'police_station': 5, 'hospital': 5, 'recycling_center': 3,
    'subway': 6, 'supermarket': 5, 'bank': 5, 'shopping_mall': 4, 'stadium': 3,
    'coal_power': 5, 'oil_power': 5, 'nuclear_power': 5, 'wind_power': 50,
    'barracks': 5, 'factory': 5, 'hangar': 5, 'drydock': 3,
}

IMP_DISPLAY = {
    'stadium': 'Stadium', 'shopping_mall': 'Shopping Mall', 'subway': 'Subway',
    'bank': 'Bank', 'supermarket': 'Supermarket', 'police_station': 'Police Station',
    'hospital': 'Hospital', 'recycling_center': 'Recycling Center',
    'coal_mine': 'Coal Mine', 'oil_well': 'Oil Well', 'bauxite_mine': 'Bauxite Mine',
    'iron_mine': 'Iron Mine', 'lead_mine': 'Lead Mine', 'uranium_mine': 'Uranium Mine',
    'oil_refinery': 'Oil Refinery', 'steel_mill': 'Steel Mill',
    'aluminum_refinery': 'Aluminum Refinery', 'munitions_factory': 'Munitions Factory',
    'farm': 'Farm', 'infrastructure': 'Infrastructure', 'land': 'Land',
}

# Civil improvements that affect cash income (commerce, crime, disease, pollution)
CIVIL_IMPS = [
    'stadium', 'shopping_mall', 'subway', 'bank', 'supermarket',
    'police_station', 'hospital', 'recycling_center',
]

# Resource improvements: (key, output_resource, [required_input_resources])
# required_inputs: nation must produce ALL of these for the improvement to make sense
RESOURCE_IMPS: List[tuple] = [
    ('coal_mine',         'coal',      []),
    ('oil_well',          'oil',       []),
    ('bauxite_mine',      'bauxite',   []),
    ('iron_mine',         'iron',      []),
    ('lead_mine',         'lead',      []),
    ('uranium_mine',      'uranium',   []),
    ('farm',              'food',      []),
    ('oil_refinery',      'gasoline',  ['oil']),
    ('steel_mill',        'steel',     ['coal', 'iron']),
    ('aluminum_refinery', 'aluminum',  ['bauxite']),
    ('munitions_factory', 'munitions', ['lead']),
]

# Projects to evaluate: (api_flag, display_name, is_resource_project)
# is_resource_project=True → use monetary baseline for gain calculation
ALL_PROJECTS: List[tuple] = [
    # Cash / commerce
    ('international_trade_center',        'International Trade Center',        False),
    ('telecommunications_satellite',      'Telecommunications Satellite',      False),
    ('specialized_police_training_program','Specialized Police Training Program',False),
    ('green_technologies',                'Green Technologies',                False),
    ('recycling_initiative',              'Recycling Initiative',              False),
    ('clinical_research_center',          'Clinical Research Center',          False),
    ('bureau_of_domestic_affairs',        'Bureau of Domestic Affairs',        False),
    ('government_support_agency',         'Government Support Agency',         False),
    # Resource production
    ('mass_irrigation',                   'Mass Irrigation',                   True),
    ('emergency_gasoline_reserve',        'Emergency Gasoline Reserve',        True),
    ('iron_works',                        'Iron Works',                        True),
    ('bauxite_works',                     'Bauxite Works',                     True),
    ('arms_stockpile',                    'Arms Stockpile',                    True),
    ('uranium_enrichment_program',        'Uranium Enrichment Program',        True),
    ('fallout_shelter',                   'Fallout Shelter',                   True),
    # Cost-reduction (no direct revenue gain, but reduce future spend)
    ('center_for_civil_engineering',      'Center for Civil Engineering',      False),
    ('advanced_engineering_corps',        'Advanced Engineering Corps',        False),
    ('arable_land_agency',                'Arable Land Agency',                False),
]

PROJECT_REASONS: Dict[str, str] = {
    'international_trade_center':         '+15 max commerce, +1 base commerce/city',
    'telecommunications_satellite':       '+25 max commerce, +2 base commerce/city',
    'specialized_police_training_program':'crime reduction 3.5% (vs 2.5%), +4 base commerce/city',
    'green_technologies':                 '-25% mfg pollution, -50% farm pollution, subway -70 poll',
    'recycling_initiative':               'recycling centers reduce 75 pollution (vs 70)',
    'clinical_research_center':           'hospitals reduce 3.5% disease (vs 2.5%)',
    'bureau_of_domestic_affairs':         '+25% domestic policy bonus multiplier',
    'government_support_agency':          '+50% domestic policy bonus multiplier',
    'mass_irrigation':                    'food land modifier 500→400 → +25% food/farm',
    'emergency_gasoline_reserve':         '×2 gasoline production per refinery',
    'iron_works':                         '×1.36 steel production per steel mill',
    'bauxite_works':                      '×1.36 aluminum production per aluminum refinery',
    'arms_stockpile':                     '×1.2 munitions production per munitions factory',
    'uranium_enrichment_program':         '×2 uranium production per uranium mine',
    'fallout_shelter':                    'reduces radiation food penalty by 15%',
    'center_for_civil_engineering':       '-5% infra cost on future purchases',
    'advanced_engineering_corps':         '-5% infra cost, -5% land cost',
    'arable_land_agency':                 '-5% land cost on future purchases',
}

# Infra breakpoints to test (never suggest selling)
INFRA_TARGETS = [500, 1000, 1500, 2000, 2500, 3000]

# ROI gates
INFRA_MAX_PAYOFF_DAYS = 90   # destroyable in war — tight gate
LAND_MAX_PAYOFF_DAYS  = 365  # permanent — generous gate

# Civil improvement thresholds - only suggest if problems are above these levels
CRIME_THRESHOLD = 3.0        # Only suggest police stations if crime > 3%
DISEASE_THRESHOLD = 2.0      # Only suggest hospitals if disease > 2%  
POLLUTION_THRESHOLD = 30     # Only suggest recycling centers if pollution > 30

# Payoff display: show if ≤ 30 days OR gain is dramatic
PAYOFF_SHOW_DAYS    = 30
PAYOFF_DRAMATIC_DAY = 500_000  # $500k/day swing always shows payoff


# ── Core helpers ───────────────────────────────────────────────────────────────

def _slots(infra: float) -> int:
    """Calculate total improvement slots available based on infrastructure.
    
    Formula: 1 slot per 50 infrastructure, maximum 50 slots total.
    Examples: 500 infra = 10 slots, 1000 infra = 20 slots, 2500+ infra = 50 slots
    """
    return min(int(infra // 50), 50)


def _dc(nation: dict) -> dict:
    """Shallow-copy nation with a new cities list (each city is a plain dict shallow copy).
    Avoids copy.deepcopy which can hit recursion limits on sqlite3.Row-derived dicts
    and is ~10-50x slower than a targeted shallow copy."""
    n = {k: v for k, v in nation.items() if k != 'cities'}
    n['cities'] = [{k: v for k, v in c.items()} for c in nation.get('cities', [])]
    return n


def _rev(nation: dict, prices: dict, colors: dict,
         seasonal_mod: dict, radiation: dict, treasures: list) -> dict:
    """Single call returning both cash and monetary net per turn."""
    r = revenue_calc_sync(
        nation=nation, radiation=radiation, treasures=treasures,
        prices=prices, colors=colors, seasonal_mod=seasonal_mod, include_spies=True,
    )
    return {'cash': r.get('net_cash_num', 0.0), 'monetary': r.get('monetary_net_num', 0.0)}


def _city_stats(city: dict, modifiers: dict, seasonal_mod: dict,
                radiation: dict, nation: dict) -> dict:
    """Compute pollution, commerce, crime, disease, population for a city."""
    base_pop = city['infrastructure'] * 100
    power    = calculate_power_generation(city)
    unpow    = power['unpowered_infra']
    rss      = calculate_resource_production(city, modifiers)
    mfg      = calculate_manufacturing(city, modifiers, unpow)
    civil    = calculate_civil_improvements(city, modifiers, unpow)
    poll     = max(power['pollution'] + rss['pollution'] + mfg['pollution'] + civil['pollution'], 0)
    com      = civil['commerce']
    pop      = calculate_population_effects(city, modifiers, base_pop, com,
                                            civil['police_stations'], civil['hospitals'], poll)
    slots_used  = sum(city.get(k, 0) for k in IMPROVEMENT_LIMITS)
    slots_total = _slots(city['infrastructure'])
    return {
        'pollution':   poll,
        'commerce':    com,
        'crime':       pop['crime_rate'],
        'disease':     pop['disease_rate'],
        'population':  pop['population'],
        'slots_used':  slots_used,
        'slots_total': slots_total,
        'slots_free':  max(slots_total - slots_used, 0),
    }


def _produces(nation: dict, resource: str) -> bool:
    """True if any city currently produces this resource."""
    imp_map = {
        'coal': 'coal_mine', 'oil': 'oil_well', 'bauxite': 'bauxite_mine',
        'iron': 'iron_mine', 'lead': 'lead_mine', 'uranium': 'uranium_mine',
        'food': 'farm', 'gasoline': 'oil_refinery', 'steel': 'steel_mill',
        'aluminum': 'aluminum_refinery', 'munitions': 'munitions_factory',
    }
    key = imp_map.get(resource)
    return bool(key and any(c.get(key, 0) > 0 for c in nation.get('cities', [])))


def _improvement_cost(imp: str, count: int, prices: dict) -> float:
    """Total money-equivalent cost to buy `count` of an improvement at current market prices."""
    # Map rev_optimizer field names → war_calc IMPROVEMENT_COSTS keys
    _KEY_MAP = {
        'oil_refinery':       'oil_refinery',
        'steel_mill':         'steel_mill',
        'aluminum_refinery':  'aluminum_refinery',
        'munitions_factory':  'munitions_factory',
        'coal_mine':          'coal_mine',
        'oil_well':           'oil_well',
        'bauxite_mine':       'bauxite_mine',
        'iron_mine':          'iron_mine',
        'lead_mine':          'lead_mine',
        'uranium_mine':       'uranium_mine',
        'farm':               'farm',
        'police_station':     'police_station',
        'hospital':           'hospital',
        'recycling_center':   'recycling_center',
        'subway':             'subway',
        'supermarket':        'supermarket',
        'bank':               'bank',
        'shopping_mall':      'shopping_mall',
        'stadium':            'stadium',
    }
    key = _KEY_MAP.get(imp, imp)
    raw = IMPROVEMENT_COSTS.get(key)
    if not raw:
        return 0.0
    cash = raw.get('cash', 0.0)
    resource_cost = sum(
        qty * prices.get(rss, 0)
        for rss, qty in raw.items()
        if rss != 'cash'
    )
    return (cash + resource_cost) * count


def _project_cost_money(flag: str, nation: dict, prices: dict) -> float:
    """
    Total money-equivalent cost of a project at current market prices,
    applying the nation's existing project discounts.
    Looks up by display name since PROJECT_BUILD_COSTS uses display names.
    """
    # Map api flag → display name used in PROJECT_BUILD_COSTS
    flag_to_display = {
        'international_trade_center':         'International Trade Center',
        'telecommunications_satellite':       'Telecommunications Satellite',
        'specialized_police_training_program':'Specialized Police Training Program',
        'green_technologies':                 'Green Technologies',
        'recycling_initiative':               'Recycling Initiative',
        'clinical_research_center':           'Clinical Research Center',
        'mass_irrigation':                    'Mass Irrigation',
        'emergency_gasoline_reserve':         'Emergency Gasoline Reserve',
        'iron_works':                         'Iron Works',
        'bauxite_works':                      'Bauxite Works',
        'arms_stockpile':                     'Arms Stockpile',
        'uranium_enrichment_program':         'Uranium Enrichment Program',
        'center_for_civil_engineering':       'Center Civil Engineering',
        'advanced_engineering_corps':         'Advanced Engineering Corps',
        'arable_land_agency':                 'Arable Land Agency',
        'bureau_of_domestic_affairs':         'Bureau of Domestic Affairs',
        'government_support_agency':          'Government Support Agency',
        'fallout_shelter':                    'Fallout Shelter',
    }
    display = flag_to_display.get(flag)
    if not display or display not in PROJECT_BUILD_COSTS:
        return 0.0

    raw = PROJECT_BUILD_COSTS[display]
    discounts = calculate_project_discounts(nation)

    # Apply Technological Advancement policy discount to money cost only if
    # the nation currently has that domestic policy active.
    money = raw.get('money', 0.0)
    _raw_dp = str(nation.get('domestic_policy') or '').upper()
    _dp_norm = _raw_dp.replace('DOMESTICPOLICY.', '').replace(' ', '_')
    if _dp_norm == 'TECHNOLOGICAL_ADVANCEMENT':
        policy_mult = discounts.get('domestic_policy_multiplier', 1.0)
        discount_rate = 1.0 - 0.05 * policy_mult
    else:
        discount_rate = 1.0
    money *= discount_rate

    # Add resource costs at market prices, applying the same discount
    resource_cost = sum(
        qty * discount_rate * prices.get(rss, 0)
        for rss, qty in raw.items()
        if rss != 'money'
    )
    return money + resource_cost


def _stack(count: int, limit: int) -> float:
    if count <= 1 or limit <= 1:
        return 1.0
    return 1.0 + ((count - 1) / (limit - 1)) * 0.5


def _resource_reason(imp: str, output_rss: str, add: int, current: int,
                     prices: dict, modifiers: dict) -> str:
    """Human-readable reason with actual output/input numbers and net value."""
    new_n = current + add
    lim   = IMPROVEMENT_LIMITS.get(imp, 5)
    s     = _stack(new_n, lim)

    if imp == 'oil_refinery':
        gm    = modifiers.get('gas_mod', 1)
        out   = new_n * 6.0 * s * gm
        inp   = new_n * 3.0 * s * gm
        net   = out * prices.get('gasoline', 0) - inp * prices.get('oil', 0)
        return f'{current}→{new_n} refineries: {out:.1f} gas/day − {inp:.1f} oil/day = ${net:,.0f}/day'
    if imp == 'steel_mill':
        sm    = modifiers.get('ste_mod', 1)
        out   = new_n * 9.0 * s * sm
        c_in  = new_n * 3.0 * s * sm
        i_in  = new_n * 3.0 * s * sm
        net   = out * prices.get('steel', 0) - c_in * prices.get('coal', 0) - i_in * prices.get('iron', 0)
        return f'{current}→{new_n} mills: {out:.1f} steel/day − {c_in:.1f} coal − {i_in:.1f} iron = ${net:,.0f}/day'
    if imp == 'aluminum_refinery':
        am    = modifiers.get('alu_mod', 1)
        out   = new_n * 9.0 * s * am
        inp   = new_n * 3.0 * s * am
        net   = out * prices.get('aluminum', 0) - inp * prices.get('bauxite', 0)
        return f'{current}→{new_n} refineries: {out:.1f} alum/day − {inp:.1f} baux/day = ${net:,.0f}/day'
    if imp == 'munitions_factory':
        mm    = modifiers.get('mun_mod', 1)
        out   = new_n * 18.0 * s * mm
        inp   = new_n * 6.0 * s   # lead not boosted by Arms Stockpile
        net   = out * prices.get('munitions', 0) - inp * prices.get('lead', 0)
        return f'{current}→{new_n} factories: {out:.1f} muni/day − {inp:.1f} lead/day = ${net:,.0f}/day'
    # Raw mines / farms
    um  = modifiers.get('uranium_mod', 1) if imp == 'uranium_mine' else 1.0
    out = new_n * 0.25 * s * um * 12  # per day
    val = out * prices.get(output_rss, 0)
    return f'{current}→{new_n}: ~{out:.2f} {output_rss}/day @ ${prices.get(output_rss, 0):,.0f} = ${val:,.0f}/day gross'


def _civil_reason(imp: str, stats: dict, modifiers: dict, add: int) -> str:
    if imp in ('stadium', 'shopping_mall', 'bank', 'supermarket'):
        return f'+{add} {IMP_DISPLAY[imp]} → more commerce → higher tax income'
    if imp == 'subway':
        return f'+{add} Subway → +{8 * add} commerce, −{modifiers["subw_poll_red"] * add:.0f} pollution'
    if imp == 'police_station':
        crime_reduction = modifiers["pol_cri_red"] * add
        new_crime = max(0, stats["crime"] - crime_reduction)
        return (f'+{add} Police Station → −{crime_reduction:.1f}% crime '
                f'({stats["crime"]:.1f}% → {new_crime:.1f}%) → fewer crime deaths → more pop → more tax')
    if imp == 'hospital':
        disease_reduction = modifiers["hos_dis_red"] * add
        new_disease = max(0, stats["disease"] - disease_reduction)
        return (f'+{add} Hospital → −{disease_reduction:.1f}% disease '
                f'({stats["disease"]:.1f}% → {new_disease:.1f}%) → fewer disease deaths → more pop → more tax')
    if imp == 'recycling_center':
        pollution_reduction = modifiers["rec_poll"] * add
        new_pollution = max(0, stats["pollution"] - pollution_reduction)
        return (f'+{add} Recycling Center → −{pollution_reduction:.0f} pollution '
                f'({stats["pollution"]:.0f} → {new_pollution:.0f}) → less disease/crime → more pop → more tax')
    return f'+{add} {IMP_DISPLAY.get(imp, imp)}'


# ── Core analysis ──────────────────────────────────────────────────────────────

def analyze_revenue(nation: dict, prices: dict, colors: dict,
                    seasonal_mod: dict, radiation: dict, treasures: list) -> dict:
    """
    Full revenue optimization analysis. Returns:
      current_net       — cash/turn baseline
      current_monetary  — (cash + resources)/turn baseline
      city_analyses     — per-city list with ranked suggestions
      project_suggestions — ranked project list with cost + payoff
      top_suggestions   — globally ranked flat list of all actions
    """
    modifiers = calculate_nation_modifiers(nation)
    base      = _rev(nation, prices, colors, seasonal_mod, radiation, treasures)
    cur_cash  = base['cash']
    cur_mon   = base['monetary']

    city_analyses:    List[dict] = []
    all_suggestions:  List[dict] = []

    # ── Per-city analysis ──────────────────────────────────────────────────────
    for city_idx, city in enumerate(nation.get('cities', [])):
        infra     = city.get('infrastructure', 0)
        land      = city.get('land', 0)
        city_name = city.get('name', f'City {city_idx + 1}')
        stats     = _city_stats(city, modifiers, seasonal_mod, radiation, nation)
        slots_free = stats['slots_free']
        city_sugg: List[dict] = []

        # ── 1. Civil / commerce improvements ──────────────────────────────────
        # Use cash baseline — these don't produce resources
        # Only suggest if they would actually help with current problems
        for imp in CIVIL_IMPS:
            cur_n = city.get(imp, 0)
            limit = IMPROVEMENT_LIMITS[imp]
            if cur_n >= limit:
                continue
            
            # Check if this improvement would actually help current problems
            should_suggest = False
            if imp in ('stadium', 'shopping_mall', 'bank', 'supermarket'):
                # Commerce improvements - always suggest if under limit and have slots
                should_suggest = True
            elif imp == 'subway':
                # Subway helps with both commerce and pollution
                should_suggest = True
            elif imp == 'police_station':
                # Only suggest if crime is actually high and would benefit from reduction
                should_suggest = stats['crime'] > CRIME_THRESHOLD
            elif imp == 'hospital':
                # Only suggest if disease is actually high and would benefit from reduction
                should_suggest = stats['disease'] > DISEASE_THRESHOLD
            elif imp == 'recycling_center':
                # Only suggest if pollution is actually high and would benefit from reduction
                should_suggest = stats['pollution'] > POLLUTION_THRESHOLD
            
            if not should_suggest:
                continue
                
            best_add, best_gain = 0, 0.0
            sim_city   = {k: v for k, v in city.items()}
            sim_nation = _dc(nation)
            for n in range(1, limit - cur_n + 1):
                if n > slots_free:
                    break
                sim_city[imp] = cur_n + n
                sim_nation['cities'][city_idx] = sim_city
                gain = _rev(sim_nation, prices, colors, seasonal_mod, radiation, treasures)['cash'] - cur_cash
                if gain > best_gain:
                    best_gain, best_add = gain, n
                else:
                    break  # diminishing returns
            if best_add > 0 and best_gain > 0:
                imp_cost = _improvement_cost(imp, best_add, prices)
                payoff   = (imp_cost / (best_gain * 12)) if imp_cost > 0 and best_gain > 0 else 0.0
                city_sugg.append({
                    'type': 'improvement', 'city': city_name, 'city_idx': city_idx,
                    'improvement': imp, 'add': best_add,
                    'from': cur_n, 'to': cur_n + best_add,
                    'gain_per_turn': best_gain, 'gain_per_day': best_gain * 12,
                    'cost': imp_cost, 'payoff_days': payoff, 'slots_needed': best_add,
                    'reason': _civil_reason(imp, stats, modifiers, best_add),
                })

        # ── 2. Resource improvements ───────────────────────────────────────────
        # Use monetary baseline — production value only shows up there
        # Only suggest if nation already produces the output OR has all inputs
        for imp, out_rss, req_inputs in RESOURCE_IMPS:
            if not _produces(nation, out_rss) and not all(_produces(nation, r) for r in req_inputs):
                continue
            cur_n = city.get(imp, 0)
            limit = IMPROVEMENT_LIMITS[imp]
            if cur_n >= limit:
                continue
            best_add, best_gain = 0, 0.0
            sim_city   = {k: v for k, v in city.items()}
            sim_nation = _dc(nation)
            for n in range(1, min(limit - cur_n, slots_free) + 1):
                sim_city[imp] = cur_n + n
                sim_nation['cities'][city_idx] = sim_city
                gain = _rev(sim_nation, prices, colors, seasonal_mod, radiation, treasures)['monetary'] - cur_mon
                if gain > best_gain:
                    best_gain, best_add = gain, n
                else:
                    break
            if best_add > 0 and best_gain > 0:
                imp_cost = _improvement_cost(imp, best_add, prices)
                payoff   = (imp_cost / (best_gain * 12)) if imp_cost > 0 and best_gain > 0 else 0.0
                city_sugg.append({
                    'type': 'resource', 'city': city_name, 'city_idx': city_idx,
                    'improvement': imp, 'add': best_add,
                    'from': cur_n, 'to': cur_n + best_add,
                    'gain_per_turn': best_gain, 'gain_per_day': best_gain * 12,
                    'cost': imp_cost, 'payoff_days': payoff, 'slots_needed': best_add,
                    'reason': _resource_reason(imp, out_rss, best_add, cur_n, prices, modifiers),
                })

        # ── 2.6. Missing resource improvements (war damage detection) ───────────
        # Detect if they're missing resource improvements they should have based on their production
        for imp, out_rss, req_inputs in RESOURCE_IMPS:
            if not (_produces(nation, out_rss) or all(_produces(nation, r) for r in req_inputs)):
                continue
                
            cur_n = city.get(imp, 0)
            limit = IMPROVEMENT_LIMITS[imp]
            
            # Check if other cities have this improvement - if so, this city probably should too
            other_cities_have = any(
                other_city.get(imp, 0) > 0 
                for other_idx, other_city in enumerate(nation.get('cities', []))
                if other_idx != city_idx
            )
            
            # If they produce this resource but this city has 0 and others have it, suggest rebuilding
            if cur_n == 0 and other_cities_have and slots_free > 0:
                # Suggest rebuilding 1-2 based on what other cities have
                avg_in_other_cities = sum(
                    other_city.get(imp, 0) 
                    for other_idx, other_city in enumerate(nation.get('cities', []))
                    if other_idx != city_idx
                ) / max(1, len(nation.get('cities', [])) - 1)
                
                suggested_rebuild = min(max(1, int(avg_in_other_cities)), min(3, slots_free))
                
                sim_city = {k: v for k, v in city.items()}
                sim_nation = _dc(nation)
                sim_city[imp] = suggested_rebuild
                sim_nation['cities'][city_idx] = sim_city
                gain = _rev(sim_nation, prices, colors, seasonal_mod, radiation, treasures)['monetary'] - cur_mon
                
                if gain > 0:
                    imp_cost = _improvement_cost(imp, suggested_rebuild, prices)
                    payoff   = (imp_cost / (gain * 12)) if imp_cost > 0 and gain > 0 else 0.0
                    city_sugg.append({
                        'type': 'rebuild', 'city': city_name, 'city_idx': city_idx,
                        'improvement': imp, 'add': suggested_rebuild,
                        'from': 0, 'to': suggested_rebuild,
                        'gain_per_turn': gain, 'gain_per_day': gain * 12,
                        'cost': imp_cost, 'payoff_days': payoff, 'slots_needed': suggested_rebuild,
                        'reason': f'Rebuild {suggested_rebuild} {IMP_DISPLAY[imp]} (likely destroyed in war) for +{gain*12:.0f}/day',
                    })

        # ── 3. Infrastructure ──────────────────────────────────────────────────
        # Only suggest if very low infrastructure AND actually need more slots
        # Check if they have available slots for their current build needs
        if infra < 2000 and slots_free < 2:  # Only if they're actually short on slots
            # Find the minimum infra needed to get 2-3 more slots
            needed_slots = 3 - slots_free  # Target having 2-3 free slots
            for target in INFRA_TARGETS:
                if target <= infra:
                    continue
                target_slots = _slots(target)
                current_slots = _slots(infra)
                slots_gained = target_slots - current_slots
                if slots_gained >= needed_slots:
                    tn = _dc(nation)
                    tn['cities'][city_idx]['infrastructure'] = float(target)
                    gain = _rev(tn, prices, colors, seasonal_mod, radiation, treasures)['cash'] - cur_cash
                    cost = calc_infra_value(infra, float(target))
                    if gain > 0 and cost < float('inf'):
                        payoff = cost / (gain * 12)
                        if payoff <= INFRA_MAX_PAYOFF_DAYS:
                            city_sugg.append({
                                'type': 'infrastructure', 'city': city_name, 'city_idx': city_idx,
                                'improvement': 'infrastructure', 'add': target - infra,
                                'from': infra, 'to': target,
                                'gain_per_turn': gain, 'gain_per_day': gain * 12,
                                'cost': cost, 'payoff_days': payoff, 'slots_needed': 0,
                                'reason': (
                                    f'{infra:.0f}→{target} infra (+{target - infra:.0f}) → '
                                    f'+{slots_gained} improvement slots (currently {slots_free} free) | '
                                    f'ROI {payoff:.0f}d'
                                ),
                            })
                    break  # only the minimum needed infra

        # ── 4. Land ────────────────────────────────────────────────────────────
        # Permanent — suggest up to 365 days ROI, pick the best-ROI increment
        # Use monetary baseline (land affects food production value)
        best_land: Optional[dict] = None
        for land_add in [250, 500, 1000, 2000, 5000]:
            new_land = land + land_add
            tn = _dc(nation)
            tn['cities'][city_idx]['land'] = new_land
            gain = _rev(tn, prices, colors, seasonal_mod, radiation, treasures)['monetary'] - cur_mon
            cost = calc_land_value(land, new_land)
            if gain > 0 and 0 < cost < float('inf'):
                payoff = cost / (gain * 12)
                if payoff <= LAND_MAX_PAYOFF_DAYS:
                    if best_land is None or payoff < best_land['payoff_days']:
                        best_land = {
                            'type': 'land', 'city': city_name, 'city_idx': city_idx,
                            'improvement': 'land', 'add': land_add,
                            'from': land, 'to': new_land,
                            'gain_per_turn': gain, 'gain_per_day': gain * 12,
                            'cost': cost, 'payoff_days': payoff, 'slots_needed': 0,
                            'reason': (
                                f'+{land_add:,} land ({land:.0f}→{new_land:.0f}) → '
                                f'lower pop density → less disease + more food | ROI {payoff:.0f}d'
                            ),
                        }
        if best_land:
            city_sugg.append(best_land)

        city_sugg.sort(key=lambda x: x['gain_per_day'], reverse=True)
        city_analyses.append({
            'name': city_name, 'city_idx': city_idx,
            'infra': infra, 'land': land,
            'stats': stats, 'suggestions': city_sugg,
        })
        all_suggestions.extend(city_sugg)

    # ── Project analysis ───────────────────────────────────────────────────────
    project_suggestions: List[dict] = []
    for flag, display, is_resource in ALL_PROJECTS:
        if nation.get(flag):
            continue
        tn = _dc(nation)
        tn[flag] = True
        rev = _rev(tn, prices, colors, seasonal_mod, radiation, treasures)
        gain = (rev['monetary'] - cur_mon) if is_resource else (rev['cash'] - cur_cash)

        # Project cost in money-equivalent (money + resources @ market)
        proj_cost = _project_cost_money(flag, nation, prices)
        payoff    = (proj_cost / (gain * 12)) if gain > 0 and proj_cost > 0 else float('inf')

        project_suggestions.append({
            'project':      display,
            'flag':         flag,
            'is_resource':  is_resource,
            'gain_per_turn': gain,
            'gain_per_day':  gain * 12,
            'cost':          proj_cost,
            'payoff_days':   payoff,
            'reason':        PROJECT_REASONS.get(flag, ''),
        })

    # Sort: positive gain first (by gain desc), then zero/negative (by cost asc)
    project_suggestions.sort(key=lambda x: (-x['gain_per_day'], x['cost']))
    all_suggestions.sort(key=lambda x: x['gain_per_day'], reverse=True)

    return {
        'current_net':      cur_cash,
        'current_monetary': cur_mon,
        'city_analyses':    city_analyses,
        'project_suggestions': project_suggestions,
        'top_suggestions':  all_suggestions,
    }


# ── Formatting helpers ─────────────────────────────────────────────────────────

def _g(v: float) -> str:
    """Format a daily gain/loss."""
    return f"{'+'if v>=0 else ''}${v:,.0f}/day"


def _c(v: float) -> str:
    """Format a cost."""
    if v <= 0:
        return 'free slot'
    if v >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    return f"${v:,.0f}"


def _payoff(days: float, gain_day: float) -> str:
    """Show payoff string only when it matters."""
    if days in (float('inf'), 0) or days <= 0:
        return ''
    if days > PAYOFF_SHOW_DAYS and abs(gain_day) < PAYOFF_DRAMATIC_DAY:
        return ''
    if days < 1:
        return ' *(< 1 day)*'
    return f' *({days:.0f}d ROI)*'


def _sugg_line(s: dict) -> str:
    name = IMP_DISPLAY.get(s['improvement'], s['improvement'])
    add  = f"×{s['add']}" if s.get('add', 1) > 1 else '+1'
    pay  = _payoff(s.get('payoff_days', float('inf')), s['gain_per_day'])
    cost = f" | {_c(s['cost'])}" if s.get('cost', 0) > 0 else ''
    return f"`{s['city']}` {add} **{name}**: {_g(s['gain_per_day'])}{cost}{pay}"


# ── Discord Cog ────────────────────────────────────────────────────────────────

class RevenueOptimizer(commands.Cog):
    """Revenue Optimizer — full economic brain for P&W nations."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.query_instance: Optional[V3GraphQuery] = None

    async def _get_nation(self, query: str) -> Optional[dict]:
        clean = strip_emoji_prefix(query)
        try:
            from PnWHarvester.db.global_nations_db import GlobalNationsDB
            from Systems.Functions.db_paths import GLOBAL_NATIONS_DB as _GNDB
            db = GlobalNationsDB(str(_GNDB))
            if clean.isdigit():
                n = await db.get_nation(int(clean))
                if n:
                    n['cities'] = await db.get_cities_for_nation(int(clean))
                    return n
            else:
                n = await db.get_nation_by_name(clean)
                if n:
                    n['cities'] = await db.get_cities_for_nation(int(n['id']))
                    return n
        except Exception as e:
            logger.warning(f"DB lookup failed: {e}")
        if not self.query_instance:
            self.query_instance = create_v3_query_instance()
        try:
            return (await self.query_instance.get_nation_by_id(clean)
                    if clean.isdigit()
                    else await self.query_instance.get_nation_by_name(clean))
        except Exception as e:
            logger.error(f"API lookup failed: {e}")
            return None

    async def _load_ctx(self) -> dict:
        from Systems.Functions.database_manager import (
            get_latest_resource_prices, get_latest_game_data,
            get_latest_game_info, get_latest_radiation_data,
        )
        prices: Dict[str, float] = {}
        try:
            pd = await get_latest_resource_prices()
            if pd:
                prices = {r: p['sell'] for r, p in pd.items()}
        except Exception:
            pass

        colors: Dict[str, float] = {}
        try:
            cd = await get_latest_game_data("colors")
            if cd:
                colors = {c['color'].lower(): float(c.get('turn_bonus', 0)) for c in cd}
        except Exception:
            pass

        radiation = {k: 0 for k in ('na', 'sa', 'eu', 'as', 'af', 'au', 'an')}
        try:
            rd = await get_latest_radiation_data()
            if rd:
                g = rd.get('global', 0)
                for k, rk in [('na','north_america'),('sa','south_america'),('eu','europe'),
                               ('as','asia'),('af','africa'),('au','australia'),('an','antarctica')]:
                    radiation[k] = (rd.get(rk, 0) + g) / -1000
        except Exception:
            pass

        seasonal_mod = {'na':1,'sa':1,'eu':1,'as':1,'af':1,'au':1,'an':0.5}
        try:
            gi = await get_latest_game_info()
            if gi and gi.get('game_date'):
                month = int(gi['game_date'][5:7])
                if month in (6, 7, 8):
                    seasonal_mod.update({'na':1.2,'as':1.2,'eu':1.2,'sa':0.8,'af':0.8,'au':0.8})
                elif month in (12, 1, 2):
                    seasonal_mod.update({'na':0.8,'as':0.8,'eu':0.8,'sa':1.2,'af':1.2,'au':1.2})
        except Exception:
            pass

        return {'prices': prices, 'colors': colors,
                'radiation': radiation, 'seasonal_mod': seasonal_mod}

    async def nation_autocomplete(self, interaction: discord.Interaction, current: str):
        try:
            from Systems.Functions.autocomplete_utils import nation_autocomplete
            return await nation_autocomplete(current, nw_only=False, limit=25)
        except Exception:
            return []

    @commands.hybrid_command(
        name='revoptimize',
        aliases=['revopt', 'revincrease', 'revup'],
        description='Revenue Optimizer — full economic brain for maximizing nation income',
    )
    @app_commands.describe(nation_query='Nation name or ID')
    async def rev_optimize_command(self, ctx: commands.Context, *, nation_query: str) -> None:
        loading = await ctx.send(f"🔍 Analyzing **{nation_query}**...")
        try:
            nation = await self._get_nation(nation_query)
            if not nation:
                await loading.edit(content=f"❌ Nation **{nation_query}** not found.")
                return
            if not nation.get('cities'):
                await loading.edit(content="❌ No city data found for this nation.")
                return
            await loading.edit(content=f"⚙️ Optimizing **{nation.get('nation_name', nation_query)}**...")
            ctx_data = await self._load_ctx()
            result = analyze_revenue(
                nation=nation,
                prices=ctx_data['prices'],
                colors=ctx_data['colors'],
                seasonal_mod=ctx_data['seasonal_mod'],
                radiation=ctx_data['radiation'],
                treasures=[],
            )
            embeds = self._build_embeds(nation, result, ctx_data['prices'])
            await loading.edit(content='', embed=embeds[0])
            for e in embeds[1:]:
                await ctx.send(embed=e)
        except Exception as e:
            logger.error(f"rev_optimize_command error: {e}", exc_info=True)
            await loading.edit(content=f"❌ Error: {e}")

    @rev_optimize_command.autocomplete('nation_query')
    async def _autocomplete(self, interaction: discord.Interaction, current: str):
        return await self.nation_autocomplete(interaction, current)

    # ── Embed builder ──────────────────────────────────────────────────────────

    def _build_embeds(self, nation: dict, result: dict, prices: dict) -> List[discord.Embed]:
        name        = nation.get('nation_name', 'Unknown')
        cur_cash    = result['current_net']
        cur_mon     = result['current_monetary']
        city_an     = result['city_analyses']
        proj_sugg   = result['project_suggestions']
        top_sugg    = result['top_suggestions']
        modifiers   = calculate_nation_modifiers(nation)
        embeds: List[discord.Embed] = []

        # ── E1: Overview ───────────────────────────────────────────────────────
        e1 = discord.Embed(title=f"📈 Revenue Optimizer — {name}", color=discord.Color.gold())
        e1.add_field(
            name="Current Revenue",
            value=(
                f"**${cur_cash:,.0f}**/turn  |  **${cur_cash*12:,.0f}**/day  *(cash only)*\n"
                f"**${cur_mon:,.0f}**/turn  |  **${cur_mon*12:,.0f}**/day  *(cash + resources @ market)*"
            ),
            inline=False,
        )

        # City health table
        city_lines = []
        for ca in city_an:
            s = ca['stats']
            city_lines.append(
                f"**{ca['name']}** — {ca['infra']:.0f} infra | {ca['land']:.0f} land | "
                f"Pop {s['population']:,} | Com {s['commerce']:.0f}/{modifiers['max_commerce']} | "
                f"Crime {s['crime']:.1f}% | Dis {s['disease']:.1f}% | "
                f"Poll {s['pollution']:.0f} | Slots {s['slots_used']}/{s['slots_total']}"
            )
        for i in range(0, len(city_lines), 8):
            chunk = '\n'.join(city_lines[i:i+8])
            e1.add_field(name="City Health" if i == 0 else "City Health (cont.)",
                         value=chunk or 'N/A', inline=False)

        # Top 5 quick wins (free-slot or ≤ 30d ROI)
        quick = [s for s in top_sugg if s.get('cost', 0) == 0 or s.get('payoff_days', 999) <= 30][:5]
        if quick:
            lines = [_sugg_line(s) + f"\n  ↳ {s['reason']}" for s in quick]
            e1.add_field(name="⚡ Top Quick Wins", value='\n'.join(lines), inline=False)

        embeds.append(e1)

        # ── E2+: Per-city improvement breakdown (3 cities per embed) ──────────
        for chunk_start in range(0, len(city_an), 3):
            chunk = city_an[chunk_start:chunk_start + 3]
            title = f"🏗️ City Improvements — {name}"
            if len(city_an) > 3:
                title += f" ({chunk_start+1}–{chunk_start+len(chunk)})"
            e = discord.Embed(title=title, color=discord.Color.green())
            for ca in chunk:
                suggs = ca['suggestions']
                if not suggs:
                    e.add_field(name=f"✅ {ca['name']}", value="Fully optimized.", inline=False)
                    continue
                s0 = ca['stats']
                header = (
                    f"{ca['infra']:.0f} infra | {ca['land']:.0f} land | "
                    f"Slots {s0['slots_used']}/{s0['slots_total']} | "
                    f"Crime {s0['crime']:.1f}% | Dis {s0['disease']:.1f}% | Poll {s0['pollution']:.0f}"
                )
                lines = []
                for s in suggs[:7]:
                    nm   = IMP_DISPLAY.get(s['improvement'], s['improvement'])
                    add  = f"×{s['add']}" if s.get('add', 1) > 1 else '+1'
                    pay  = _payoff(s.get('payoff_days', float('inf')), s['gain_per_day'])
                    cost = f" | {_c(s['cost'])}" if s.get('cost', 0) > 0 else ''
                    lines.append(f"{add} **{nm}**: {_g(s['gain_per_day'])}{cost}{pay}\n  ↳ {s['reason']}")
                e.add_field(name=f"🏙️ {ca['name']} — {header}", value='\n'.join(lines), inline=False)
            embeds.append(e)

        # ── E: Infrastructure & Land (only if any suggestions exist) ──────────
        infra_s = [s for s in top_sugg if s['type'] == 'infrastructure']
        land_s  = [s for s in top_sugg if s['type'] == 'land']
        if infra_s or land_s:
            e3 = discord.Embed(title=f"🏛️ Infrastructure & Land — {name}", color=discord.Color.orange())
            if infra_s:
                lines = []
                for s in infra_s[:8]:
                    pay = _payoff(s['payoff_days'], s['gain_per_day'])
                    lines.append(
                        f"`{s['city']}` {s['from']:.0f}→{s['to']:.0f} (+{s['add']:.0f}): "
                        f"{_g(s['gain_per_day'])} | {_c(s['cost'])}{pay}\n  ↳ {s['reason']}"
                    )
                e3.add_field(name="🏛️ Infrastructure (ROI ≤ 90d only)", value='\n'.join(lines), inline=False)
            if land_s:
                lines = []
                for s in land_s[:8]:
                    pay = _payoff(s['payoff_days'], s['gain_per_day'])
                    lines.append(
                        f"`{s['city']}` +{s['add']:,} land ({s['from']:.0f}→{s['to']:.0f}): "
                        f"{_g(s['gain_per_day'])} | {_c(s['cost'])}{pay}\n  ↳ {s['reason']}"
                    )
                e3.add_field(name="🌾 Land (best ROI ≤ 365d)", value='\n'.join(lines), inline=False)
            embeds.append(e3)

        # ── E: Projects ────────────────────────────────────────────────────────
        e4 = discord.Embed(title=f"🔬 Project Suggestions — {name}", color=discord.Color.blue())

        positive = [p for p in proj_sugg if p['gain_per_day'] > 0]
        neutral  = [p for p in proj_sugg if p['gain_per_day'] <= 0]

        if positive:
            lines = []
            for p in positive[:10]:
                pay  = _payoff(p['payoff_days'], p['gain_per_day'])
                cost = f" | {_c(p['cost'])}" if p['cost'] > 0 else ''
                lines.append(f"**{p['project']}**: {_g(p['gain_per_day'])}{cost}{pay}\n  ↳ {p['reason']}")
            e4.add_field(name="💰 Revenue-Positive (buy these first)", value='\n'.join(lines), inline=False)

        if neutral:
            lines = []
            for p in neutral[:6]:
                cost = f" | {_c(p['cost'])}" if p['cost'] > 0 else ''
                lines.append(f"**{p['project']}**: {_g(p['gain_per_day'])}{cost} — {p['reason']}")
            e4.add_field(name="📦 Neutral / Cost-Reduction", value='\n'.join(lines), inline=False)

        all_flags = [f for f, _, _ in ALL_PROJECTS]
        owned = [f.replace('_', ' ').title() for f in all_flags if nation.get(f)]
        if owned:
            e4.add_field(name="✅ Already Owned", value=', '.join(owned), inline=False)

        embeds.append(e4)

        # ── E: Summary ─────────────────────────────────────────────────────────
        e5 = discord.Embed(title=f"📊 Optimization Summary — {name}", color=discord.Color.purple())

        if top_sugg:
            best = top_sugg[0]
            nm   = IMP_DISPLAY.get(best['improvement'], best['improvement'])
            add  = f"×{best['add']}" if best.get('add', 1) > 1 else '+1'
            e5.add_field(
                name="🥇 Best Single Action",
                value=f"`{best['city']}` {add} **{nm}**: {_g(best['gain_per_day'])}\n{best['reason']}",
                inline=False,
            )

        if positive:
            bp = positive[0]
            pay = _payoff(bp['payoff_days'], bp['gain_per_day'])
            e5.add_field(
                name="🥇 Best Project",
                value=f"**{bp['project']}**: {_g(bp['gain_per_day'])} | {_c(bp['cost'])}{pay}\n{bp['reason']}",
                inline=False,
            )

        # Free-slot potential
        free = [s for s in top_sugg if s.get('cost', 0) == 0][:10]
        if free:
            tot = sum(s['gain_per_day'] for s in free)
            e5.add_field(
                name="💡 Free-Slot Potential (top 10)",
                value=f"+{_g(tot)} | +${tot*30:,.0f}/month",
                inline=False,
            )

        # Total potential (all types)
        tot_all = sum(s['gain_per_day'] for s in top_sugg[:15])
        if tot_all > 0:
            e5.add_field(
                name="🚀 Max Potential (top 15 actions)",
                value=f"+{_g(tot_all)} | +${tot_all*30:,.0f}/month",
                inline=False,
            )

        e5.add_field(
            name="📝 How gains are calculated",
            value=(
                "• Civil/commerce improvements → cash baseline\n"
                "• Resource improvements → monetary baseline (cash + resources @ market)\n"
                "• Infra: only shown if ROI ≤ 90 days (destroyable in war)\n"
                "• Land: best-ROI increment up to 365 days (permanent asset)\n"
                "• Projects: cost includes money + resource inputs @ market prices\n"
                "• All gains fully simulated — no approximations"
            ),
            inline=False,
        )
        e5.set_footer(text="Revenue Optimizer | rev_correct.py full game mechanics")
        embeds.append(e5)

        return embeds


async def setup(bot: commands.Bot):
    await bot.add_cog(RevenueOptimizer(bot))
