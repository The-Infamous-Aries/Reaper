import math
from typing import Dict, Any, List

# Raw resource base production rates (tons per day)
# Note: 3.0 tons/day = 0.25 tons/turn (3/12 = 0.25)
RAW_BASE_PER_IMP = {
    "farm": None, 
    "coal_mine": 3.0,      # 3 tons/day = 0.25 tons/turn
    "oil_well": 3.0,       # 3 tons/day = 0.25 tons/turn
    "uranium_mine": 1.5,   # 1.5 tons/day = 0.125 tons/turn (special case for uranium)
    "iron_mine": 3.0,      # 3 tons/day = 0.25 tons/turn
    "bauxite_mine": 3.0,   # 3 tons/day = 0.25 tons/turn
    "lead_mine": 3.0,      # 3 tons/day = 0.25 tons/turn
}

RAW_MAX = {
    "coal_mine": 10,
    "oil_well": 10,
    "uranium_mine": 5,
    "iron_mine": 10,
    "bauxite_mine": 10,
    "lead_mine": 10,
    "farm": 20,
}

STACK_BONUS = 0.50  

MANU_BASE_DAILY = {
    "gasoline_refinery": 4.5,
    "munitions_refinery": 4.5,
    "steel_mill": 4.5,
    "aluminum_refinery": 4.5,
}

MANU_CONSUME_PER_IMP = { 
    "gasoline_refinery": {"oil": 6.0},
    "munitions_refinery": {"lead": 6.0},
    "steel_mill": {"coal": 3.0, "iron": 3.0},
    "aluminum_refinery": {"bauxite": 6.0},
}

RESOURCE_PROJECTS = {
    "Arable Land Initiative": "food",
    "Mass Irrigation": "food", 
    "Advanced Uranium Mining": "uranium",
    "Coal Mining Initiative": "coal",
    "Oil Extraction Initiative": "oil",
    "Iron Mining Initiative": "iron",
    "Bauxite Extraction Initiative": "bauxite",
    "Lead Mining Initiative": "lead",
    "Gasoline Refinement": "gasoline",
    "Munitions Production": "munitions",
    "Steel Production": "steel",
    "Aluminum Production": "aluminum",
    "Ironworks": "steel",
    "Bauxiteworks": "aluminum",
    "Arms Stockpile": "munitions",
    "Emergency Gasoline Reserve": "gasoline",
    "Uranium Enrichment Program": "uranium",
}

# Power plant build costs and resource requirements
POWER_PLANT_BUILD_COSTS = {
    "coal_power": {"money": 5000, "steel": 0, "aluminum": 0},
    "oil_power": {"money": 7000, "steel": 0, "aluminum": 0},
    "wind_power": {"money": 30000, "steel": 0, "aluminum": 25},
    "nuclear_power": {"money": 500000, "steel": 100, "aluminum": 0},
}

# Power plant infrastructure capacity limits
POWER_PLANT_CAPACITY = {
    "coal_power": 500,
    "oil_power": 500,
    "wind_power": 250,
    "nuclear_power": 2000,
}

# Power plant pollution index
POWER_PLANT_POLLUTION = {
    "coal_power": 8,
    "oil_power": 6,
    "wind_power": 0,
    "nuclear_power": 0,
}

IMP_UPKEEP_DAILY = {
    "supermarket": 1500,
    "bank": 2500,
    "mall": 3500,
    "stadium": 10000,
    "gasoline_refinery": 4000,
    "munitions_refinery": 4000,
    "steel_mill": 3500,
    "aluminum_refinery": 4000,
    "hospital": 2500,
    "recycling_center": 2500,
    "subway": 5000,
    "police_station": 2500,
    "coal_power": 1200,    # $1200/day operational cost
    "oil_power": 1800,     # $1800/day operational cost
    "wind_power": 500,     # $500/day operational cost
    "nuclear_power": 10500, # $10,500/day operational cost
    "barracks": 0,
    "factory": 0,
    "hangar": 0,
    "drydock": 0,
}

# Power plant fuel consumption per 100 infrastructure per day
POWER_FUEL_PER_100_INFRA = {
    "coal_power": {"coal": 1.2},    # 1.2 tons coal per 100 infra per day
    "oil_power": {"oil": 1.2},      # 1.2 tons oil per 100 infra per day
    "nuclear_power": {"uranium": 0.3}, # 0.3 tons uranium per 100 infra per day (3.0 per 1000 infra)
    "wind_power": {},               # no fuel required
}

# Legacy fuel consumption (per plant per day) - keeping for backward compatibility
POWER_FUEL = {
    "coal_power": {"coal": 1.2},
    "oil_power": {"oil": 1.2},
    "nuclear_power": {"uranium": 0.5},
    "wind_power": {},  # none
}

# Raw resource improvement build costs
RAW_BUILD_COSTS = {
    "coal_mine": {"money": 1000, "steel": 0, "aluminum": 0},
    "oil_well": {"money": 1500, "steel": 0, "aluminum": 0},
    "bauxite_mine": {"money": 9500, "steel": 0, "aluminum": 0},
    "iron_mine": {"money": 9500, "steel": 0, "aluminum": 0},
    "lead_mine": {"money": 7500, "steel": 0, "aluminum": 0},
    "uranium_mine": {"money": 25000, "steel": 0, "aluminum": 0},
    "farm": {"money": 1000, "steel": 0, "aluminum": 0},
}

# Raw resource improvement operational costs (per day)
RAW_UPKEEP_DAILY = {
    "coal_mine": 400,      # $400/day operational cost
    "oil_well": 600,       # $600/day operational cost
    "bauxite_mine": 1600,  # $1600/day operational cost
    "iron_mine": 1600,     # $1600/day operational cost
    "lead_mine": 1500,     # $1500/day operational cost
    "uranium_mine": 5000,  # $5000/day operational cost
    "farm": 300,           # $300/day operational cost
}

# Raw resource improvement pollution
RAW_POLLUTION = {
    "coal_mine": 12,       # +12 pollution points
    "oil_well": 12,        # +12 pollution points
    "bauxite_mine": 12,    # +12 pollution points
    "iron_mine": 12,       # +12 pollution points
    "lead_mine": 12,       # +12 pollution points
    "uranium_mine": 20,    # +20 pollution points
    "farm": 2,             # +2 pollution points
}

# Continent-based production modifiers (Antarctica food penalty)
CONTINENT_MODIFIERS = {
    "antarctica": {"food": 0.5},  # 50% food production penalty in Antarctica
}

def infra_upkeep(infra: float) -> float:
    return (infra ** 2) * 0.0045

def land_upkeep(land: float) -> float:
    return land * 0.05

# Infrastructure purchase cost formula: [((Current Infra-10)^2.2) / 710] + 300
def infra_price(amount: float) -> float:
    if amount < 10:
        return 300.0
    return (abs(amount - 10) ** 2.2) / 710.0 + 300.0

def calc_infra_value(starting_amount: float, ending_amount: float) -> float:
    start = round(float(starting_amount), 2)
    end = round(float(ending_amount), 2)
    diff = end - start
    if diff == 0:
        return 0.0
    if diff < 0:
        return 150.0 * diff
    cost = 0.0
    remaining = diff
    while remaining > 0:
        chunk = 100.0 if remaining > 100.0 else remaining
        unit = round(infra_price(start), 2)
        cost += unit * chunk
        start += chunk
        remaining -= chunk
    return cost

def infra_purchase_cost(current_infra: float, infra_to_buy: float, projects: set = None, total_cities: int = 0, domestic_policy: str = None) -> float:
    base = calc_infra_value(current_infra, current_infra + infra_to_buy)
    mult = 1.0
    if check_project_requirements("Advanced Engineering Corps", projects, total_cities):
        mult *= 0.95
    if projects and "Center Civil Engineering" in projects:
        mult *= 0.95
    if domestic_policy == "Urbanization":
        mult *= 0.95
    return base * mult

# Land purchase cost formula: 0.002*(Current Land-20)^2 + 50
def land_price(amount: float) -> float:
    if amount < 20:
        return 50.0
    return 0.002 * (abs(amount - 20) ** 2) + 50.0

def calc_land_value(starting_amount: float, ending_amount: float) -> float:
    start = round(float(starting_amount), 2)
    end = round(float(ending_amount), 2)
    diff = end - start
    if diff == 0:
        return 0.0
    if diff < 0:
        return 50.0 * diff
    cost = 0.0
    remaining = diff
    while remaining > 0:
        chunk = 500.0 if remaining > 500.0 else remaining
        unit = round(land_price(start), 2)
        cost += unit * chunk
        start += chunk
        remaining -= chunk
    return cost

def land_purchase_cost(current_land: float, land_to_buy: float, projects: set = None, total_cities: int = 0, domestic_policy: str = None) -> float:
    base = calc_land_value(current_land, current_land + land_to_buy)
    mult = 1.0
    if check_project_requirements("Advanced Engineering Corps", projects, total_cities):
        mult *= 0.95
    if projects and "Arable Land Agency" in projects:
        mult *= 0.95
    if domestic_policy == "Rapid Expansion":
        mult *= 0.95
    return base * mult

def base_population(infrastructure: float) -> float:
    return float(infrastructure) * 100.0

def age_bonus(city_age_days: float) -> float:
    d = max(1.0, float(city_age_days))
    return 1.0 + math.log(d) / 15.0

def city_age_modifier(city_age_days: float) -> float:
    x = float(city_age_days)
    val = math.log(x) / 15.0 if x > 0 else 0.0
    return 1.0 + (val if val > 0.0 else 0.0)

def population_formula(base_pop: float, city_age_mod: float) -> float:
    return ((float(base_pop) ** 2) / 125_000_000.0) + (((float(base_pop) * float(city_age_mod)) - float(base_pop)) / 850.0)

def population_density_equation(base_pop: float, land_area: float) -> float:
    return float(base_pop) / max(1.0, float(land_area))

def population_density_display(actual_population: float, land_area: float) -> float:
    return float(actual_population) / max(1.0, float(land_area))

def police_modifier(police_stations: int) -> float:
    return float(police_stations) * 2.5

def pollution_modifier(pollution_index: float) -> float:
    return float(pollution_index) * 0.05

def hospital_modifier(hospital_count: int) -> float:
    return float(hospital_count) * 2.5

def crime_rate_percent(commerce: float, infrastructure: float, police_stations: int) -> float:
    rate = ((((103.0 - float(commerce)) ** 2) + (float(infrastructure) * 100.0)) / 111111.0) - police_modifier(police_stations)
    return max(0.0, min(100.0, rate))

def disease_rate_percent(pop_density: float, base_pop: float, pollution_index: float, hospital_count: int) -> float:
    return ((((float(pop_density) ** 2) * 0.01) - 25.0) / 100.0) + (float(base_pop) / 100000.0) + pollution_modifier(pollution_index) - hospital_modifier(hospital_count)

def crime_deaths(crime_rate_pct: float, infrastructure: float) -> float:
    return (float(crime_rate_pct) / 10.0) * (float(infrastructure) * 100.0) - 25.0

def disease_deaths(disease_rate_pct: float, base_pop: float) -> float:
    return float(disease_rate_pct) * float(base_pop)

def city_population(infrastructure: float, land_area: float, commerce: float, police_stations: int, pollution_index: float, hospital_count: int, city_age_days: float) -> float:
    bp = base_population(infrastructure)
    pd = population_density_equation(bp, land_area)
    dr = disease_rate_percent(pd, bp, pollution_index, hospital_count)
    cr = crime_rate_percent(commerce, infrastructure, police_stations)
    dd = disease_deaths(dr, bp)
    cd = crime_deaths(cr, infrastructure)
    cam = city_age_modifier(city_age_days)
    val = (bp - dd - max(cd, 0.0)) * cam
    return max(0.0, val)

def city_purchase_cost(current_cities: int, projects: set = None, domestic_policy: str = None, top20_average: float = 0.0) -> float:
    ctb = float(current_cities)
    adj = ctb - (float(top20_average) / 4.0)
    a = (100000.0 * (adj ** 3)) + (150000.0 * adj) + 75000.0
    b = (ctb ** 2) * 100000.0
    base_cost = a if a >= b else b
    if domestic_policy == "Manifest Destiny":
        base_cost *= 0.95
    return base_cost

def project_build_cost(project_name: str, domestic_policy: str = None) -> Dict[str, int]:
    """Get project build costs, applying domestic policy discounts"""
    if project_name not in PROJECT_BUILD_COSTS:
        return {}
    
    costs = PROJECT_BUILD_COSTS[project_name].copy()
    
    # Apply Technological Advancement domestic policy 5% reduction to money cost
    if domestic_policy == "Technological Advancement" and "money" in costs:
        costs["money"] = int(costs["money"] * 0.95)
    
    return costs

# Project build costs from the comprehensive chart
PROJECT_BUILD_COSTS = {
    # Economic Projects
    "Activity Center": {"money": 500000, "food": 1000},
    "Advanced Engineering Corps": {"money": 50000000, "munitions": 10000, "gasoline": 10000, "uranium": 1000},
    "Arable Land Agency": {"money": 3000000, "coal": 1500, "lead": 1500},
    "Bureau of Domestic Affairs": {"money": 20000000, "food": 500000, "coal": 8000, "bauxite": 8000, "lead": 8000, "iron": 8000, "oil": 8000},
    "Center Civil Engineering": {"money": 3000000, "oil": 1000, "iron": 1000, "bauxite": 1000},
    "Clinical Research Center": {"money": 10000000, "food": 100000},
    "Government Support Agency": {"money": 20000000, "aluminum": 10000, "food": 200000},
    "Green Technologies": {"money": 50000000, "food": 100000, "aluminum": 10000, "iron": 10000, "oil": 10000},
    "International Trade Center": {"money": 50000000, "aluminum": 10000},
    
    # Military Projects
    "Advanced Pirate Economy": {"money": 50000000, "coal": 10000, "iron": 10000, "oil": 10000, "bauxite": 10000, "lead": 10000},
    "Central Intelligence Agency": {"money": 5000000, "steel": 500, "gasoline": 500},
    "Guiding Satellite": {"money": 200000000, "munitions": 40000, "aluminum": 40000, "uranium": 40000, "gasoline": 40000, "steel": 20000},
    "Iron Dome": {"money": 15000000, "munitions": 5000},
    "Missile Launch Pad": {"money": 5000000, "steel": 500, "gasoline": 500},
    "Nuclear Research Facility": {"money": 50000000, "aluminum": 10000, "uranium": 1000},
    "Propaganda Bureau": {"money": 5000000, "coal": 1000, "iron": 1000},
    "Space Program": {"money": 50000000, "aluminum": 10000, "steel": 10000, "gasoline": 10000},
    "Vital Defense System": {"money": 60000000, "steel": 25000, "aluminum": 25000, "munitions": 25000},
    "Military Research Center": {"money": 100000000, "steel": 10000, "aluminum": 10000, "munitions": 10000, "gasoline": 10000},
    "Military Doctrine": {"money": 10000000, "steel": 10000, "aluminum": 10000, "munitions": 10000, "gasoline": 10000},
    
    # Resource Projects
    "Arms Stockpile": {"money": 10000000, "coal": 500, "iron": 500, "oil": 500, "bauxite": 500, "lead": 500},
    "Bauxite Works": {"money": 10000000, "coal": 500, "iron": 500, "oil": 500, "bauxite": 500, "lead": 500},
    "Emergency Gasoline Reserve": {"money": 10000000, "coal": 500, "iron": 500, "oil": 500, "bauxite": 500, "lead": 500},
    "Fallout Shelter": {"money": 25000000, "food": 100000, "lead": 10000, "aluminum": 15000, "steel": 10000},
    "Iron Works": {"money": 10000000, "coal": 500, "iron": 500, "oil": 500, "bauxite": 500, "lead": 500},
    "Mars Landing": {"money": 200000000, "oil": 20000, "aluminum": 20000, "munitions": 20000, "steel": 20000, "gasoline": 20000, "uranium": 20000},
    "Mass Irrigation": {"money": 10000000, "food": 50000, "coal": 500, "iron": 500, "oil": 500, "bauxite": 500, "lead": 500},
    "Military Salvage": {"money": 20000000, "aluminum": 5000, "steel": 5000, "gasoline": 5000},
    "Missile Launch Pad": {"money": 15000000, "munitions": 5000, "gasoline": 5000, "aluminum": 5000},
    "Moon Landing": {"money": 50000000, "oil": 5000, "aluminum": 5000, "munitions": 5000, "steel": 5000, "gasoline": 5000, "uranium": 10000},
    "Nuclear Launch Facility": {"money": 750000000, "uranium": 50000, "gasoline": 50000, "aluminum": 50000},
    "Nuclear Research Facility": {"money": 75000000, "uranium": 5000, "gasoline": 5000, "aluminum": 5000},
    "Pirate Economy": {"money": 25000000, "coal": 7500, "iron": 7500, "oil": 7500, "bauxite": 7500, "lead": 7500},
    "Propaganda Bureau": {"money": 10000000, "gasoline": 2000, "munitions": 2000, "aluminum": 2000, "steel": 2000},
    "Recycling Initiative": {"money": 10000000, "food": 100000},
    "Research & Development Center": {"money": 50000000, "aluminum": 5000, "food": 100000, "uranium": 1000},
    "Space Program": {"money": 50000000, "aluminum": 25000},
    "Specialized Police Training Program": {"money": 50000000, "food": 250000, "aluminum": 5000},
    "Spy Satellite": {"money": 20000000, "oil": 10000, "bauxite": 10000, "iron": 10000, "lead": 10000, "coal": 10000},
    "Surveillance Network": {"money": 50000000, "aluminum": 50000, "bauxite": 15000, "iron": 15000, "lead": 15000, "coal": 15000},
    "Telecommunications Satellite": {"money": 300000000, "oil": 10000, "aluminum": 10000, "iron": 10000, "uranium": 10000},
    "Uranium Enrichment Program": {"money": 25000000, "uranium": 2500, "coal": 500, "iron": 500, "oil": 500, "bauxite": 500, "lead": 500},
    "Vital Defense System": {"money": 40000000, "steel": 5000, "aluminum": 5000, "munitions": 5000, "gasoline": 5000},
}

# Project effects and bonuses
PROJECT_EFFECTS = {
    "Activity Center": {
        "daily_bonus": 1000000,  # $1M on first day, $2M on subsequent days
        "max_cities": 20,  # Only works for nations with ≤20 cities
        "type": "daily_income"
    },
    "Advanced Engineering Corps": {
        "infra_cost_reduction": 0.05,  # 5% infrastructure cost reduction
        "land_cost_reduction": 0.05,   # 5% land cost reduction
        "requirements": ["Center Civil Engineering", "Arable Land Agency"],
        "type": "cost_reduction"
    },
    "Arable Land Agency": {
        "land_cost_reduction": 0.05,  # 5% land cost reduction
        "type": "land_cost_reduction"
    },
    "Center Civil Engineering": {
        "infra_cost_reduction": 0.05,  # 5% infrastructure cost reduction
        "type": "infra_cost_reduction"
    },
    "Fallout Shelter": {
        "radiation_food_penalty_reduction": 0.15,  # 15% reduction in radiation food penalty
        "nuclear_damage_reduction": 0.10,  # 10% nuke damage reduction
        "fallout_length_reduction": 0.25,  # 25% fallout length reduction
        "requirements": ["Research & Development Center", "Mass Irrigation"],
        "type": "radiation_protection"
    },
    "Green Technologies": {
        "manufacturing_pollution_reduction": 0.25,  # 25% pollution from manufacturing
        "farm_pollution_reduction": 0.50,  # 50% pollution from farms
        "subway_effectiveness_bonus": 25,  # +25 subway pollution reduction
        "resource_upkeep_reduction": 0.10,  # 10% resource production upkeep reduction
        "requirements": ["Space Program"],
        "type": "pollution_reduction"
    },
    "International Trade Center": {
        "max_commerce_bonus": 15,  # +15% max commerce (115% total)
        "type": "commerce_bonus"
    },
    "Arms Stockpile": {
        "munitions_factory_bonus": 0.20,  # 20% productivity bonus
        "type": "resource_production_bonus"
    },
    "Bauxite Works": {
        "aluminum_refinery_bonus": 0.36,  # 36% productivity bonus
        "type": "resource_production_bonus"
    },
    "Emergency Gasoline Reserve": {
        "oil_refinery_bonus": 1.0,  # 100% productivity bonus (doubled)
        "type": "resource_production_bonus"
    },
    "Ironworks": {
        "steel_mill_bonus": 0.36,  # 36% productivity bonus (corrected from chart)
        "type": "resource_production_bonus"
    },
    "Mars Landing": {
        "type": "novelty",  # Prestige project, no competitive benefits
        "requirements": ["Space Program", "Moon Landing"],
        "indestructible": True
    },
    "Mass Irrigation": {
        "food_production_bonus": 0.25,  # Boosts food production (Land/500 → Land/400)
        "type": "food_production_bonus"
    },
    "Military Salvage": {
        "salvage_bonus": 0.05,  # 5% steel/aluminum recovery from victorious attacks
        "type": "military_bonus"
    },
    "Missile Launch Pad": {
        "missile_production_bonus": 1,  # Allows missile construction
        "type": "military_production"
    },
    "Moon Landing": {
        "type": "novelty",  # Prestige project, no competitive benefits
        "requirements": ["Space Program"],
        "indestructible": True
    },
    "Nuclear Launch Facility": {
        "nuclear_weapon_bonus": 1,  # Additional nuclear weapon per day
        "requirements": ["Nuclear Research Facility", "Missile Launch Pad", "Space Program"],
        "type": "military_production"
    },
    "Nuclear Research Facility": {
        "nuclear_weapon_unlock": True,  # Allows nuclear weapon construction
        "type": "military_unlock"
    },
    "Pirate Economy": {
        "offensive_war_slot": 1,  # +1 offensive war slot (6 total)
        "loot_bonus": 0.05,  # 5% bonus to loot from ground attacks
        "war_requirement": 50,  # Requires 50 combined wars won/lost
        "requirements": ["Propaganda Bureau"],
        "type": "military_bonus"
    },
    "Propaganda Bureau": {
        "recruitment_bonus": 0.10,  # 10% increase in military unit recruitment rate
        "unit_types": ["soldiers", "tanks", "aircraft", "ships"],  # Does not affect missiles/nukes/spies
        "type": "military_bonus"
    },
    "Military Research Center": {
        "project_slot_bonus": 2,  # +2 maximum National Project slots
        "requirements": ["Propaganda Bureau"],  # Requires Propaganda Bureau to construct
        "type": "utility_bonus"
    },
    "Military Doctrine": {
        "military_research_cost_reduction": 0.05,  # 5% reduction in military research cost
        "requirements": ["Military Research Center"],  # Requires Military Research Center
        "type": "military_bonus"
    },
    "Recycling Initiative": {
        "recycling_center_pollution_bonus": 5,  # +5 pollution reduction per center (70→75)
        "recycling_center_max_bonus": 1,  # Max centers increases from 3 to 4 per city
        "requirements": ["Center Civil Engineering"],
        "type": "pollution_reduction"
    },
    "Research & Development Center": {
        "project_slot_bonus": 2,  # +2 maximum National Project slots
        "fallout_shelter_requirement": True,  # Required for Fallout Shelter
        "type": "utility_bonus"
    },
    "Space Program": {
        "space_project_unlock": True,  # Enables space-related projects
        "missile_production_bonus": 1,  # Additional missile per day
        "requirements": ["Missile Launch Pad"],
        "type": "unlock"
    },
    "Specialized Police Training Program": {
        "police_station_crime_reduction": 0.01,  # Crime reduction 2.5%→3.5% per station
        "commerce_bonus": 0.04,  # +4% commerce in all cities
        "type": "city_bonus"
    },
    "Spy Satellite": {
        "spy_production_bonus": 1,  # Additional spy per day
        "espionage_damage_bonus": 0.50,  # +50% damage from successful espionage operations
        "espionage_cost_reduction": 0.20,  # -20% espionage operation cost
        "requirements": ["Space Program", "Intelligence Agency"],
        "type": "espionage_bonus"
    },
    "Surveillance Network": {
        "espionage_defense_bonus": 0.10,  # 10% less likely to succeed against nation
        "espionage_identification_bonus": 0.10,  # 10% more likely to identify attacker
        "espionage_damage_reduction": 0.25,  # 25% damage reduction from successful ops (excluding missile/nuke)
        "requirements": ["Spy Satellite"],
        "type": "espionage_defense"
    },
    "Telecommunications Satellite": {
        "commerce_bonus": 0.10,  # +10% commerce in all cities
        "mall_effectiveness_bonus": 0.10,  # +10% mall effectiveness
        "requirements": ["Space Program"],
        "type": "commerce_bonus"
    },
    "Uranium Enrichment Program": {
        "uranium_production_bonus": 1.0,  # 100% uranium production bonus (doubled)
        "type": "resource_production_bonus"
    },
    "Vital Defense System": {
        "nuclear_thwart_chance": 0.10,  # 10% chance to thwart nuclear attacks
        "type": "nuclear_defense"
    },
}

# Domestic Policy effects
DOMESTIC_POLICIES = {
    "Manifest Destiny": {
        "city_cost_reduction": 0.05,  # 5% reduction in new city costs
        "type": "city_cost_reduction"
    },
    "Urbanization": {
        "infra_cost_reduction": 0.05,  # 5% reduction in infrastructure costs
        "type": "infra_cost_reduction"
    },
    "Technological Advancement": {
        "project_cost_reduction": 0.05,  # 5% reduction in National Project costs
        "type": "project_cost_reduction"
    },
    "Open Markets": {
        "gross_income_bonus": 0.01,  # 1% increase in gross income
        "type": "income_bonus"
    },
    "Imperialism": {
        "military_upkeep_reduction": 0.05,  # 5% reduction in Military Upkeep Costs
        "type": "military_upkeep_reduction"
    },
    "Rapid Expansion": {
        "land_cost_reduction": 0.05,  # 5% reduction in land costs
        "type": "land_cost_reduction"
    },
}

MIL_PEACETIME = {
    "soldiers": 1.25,
    "tanks": 50.0,
    "aircraft": 500.0,
    "ships": 3755.0,
    "missiles": 21000.0,
    "nukes": 35000.0,
}
WAR_MULTIPLIER = 1.5

SOLDIER_FOOD_PEACE = 1.0 / 750.0 
SOLDIER_FOOD_WAR = 1.0 / 500.0

def stacking_bonus(count: int, max_allowed: int) -> float:
    if count <= 1:
        return 0.0
    return min(0.125 * (count - 1), 0.50)

def check_project_requirements(project_name: str, projects: set, current_cities: int = 0) -> bool:
    """Check if a project meets all its requirements"""
    if not projects or project_name not in projects:
        return False
    
    project_info = PROJECT_EFFECTS.get(project_name, {})
    
    # Check city requirements
    min_cities = project_info.get("min_cities", 0)
    max_cities = project_info.get("max_cities", float('inf'))
    
    if current_cities < min_cities or current_cities > max_cities:
        return False
    
    # Check prerequisite projects
    requirements = project_info.get("requirements", [])
    for req in requirements:
        if req not in projects:
            return False
    
    return True

def food_production(land: float, farms: int, has_mass_irr: bool, has_arable: bool, radiation_index: float = 1000.0, has_fallout_shelter: bool = False) -> float:
    # Food Production = Farm Count * (Land Area / 500)
    # Final Food Prod = Food Production * (nation+continent+global rad index)/1000
    prod = farms * (land / 500.0)
    
    # Apply Mass Irrigation bonus (if available)
    if has_mass_irr:
        prod *= 1.25  # 25% bonus from Mass Irrigation
    
    # Apply Arable Land Initiative bonus (if available)
    if has_arable:
        prod *= 2.0  # 100% bonus from Arable Land Initiative
    
    # Apply radiation modifier
    radiation_effect = radiation_index / 1000.0
    
    # Apply Fallout Shelter radiation food penalty reduction (15%)
    if has_fallout_shelter and radiation_index < 1000.0:
        # Reduce the negative effect of radiation by 15%
        # If radiation is 500 (50% penalty), Fallout Shelter reduces it to 42.5% penalty
        radiation_penalty = 1.0 - radiation_effect  # How much radiation reduces food
        reduced_penalty = radiation_penalty * 0.85  # 15% reduction in penalty
        radiation_effect = 1.0 - reduced_penalty
    
    prod *= radiation_effect
    return prod

def commerce_multiplier(commerce_pct: float, projects: List[str]) -> float:
    """Calculate commerce multiplier based on commerce percentage and projects.
    This function is now deprecated - use the direct formula instead."""
    cap = 100.0
    if "International Trade Center" in projects:
        cap += 15
    if "Telecommunications Satellite" in projects:
        cap += 10
    commerce_pct = min(commerce_pct, cap)
    # Old formula: return (commerce_pct / 50.0) + 1.0
    # New approach: use direct calculation in revenue functions
    return (commerce_pct / 50.0) + 1.0  # Kept for backward compatibility

def calculate_full_revenue(
    nation_data: Dict[str, Any],
    market_prices: Dict[str, float],
    is_war: bool = False,
    radiation_index: float = 1000.0,  # Default to 1000 (no radiation effect)
    domestic_policy: str = None,  # Domestic policy selection
) -> Dict[str, Any]:

    projects = {p["name"] for p in nation_data.get("projects", [])}
    has_green_tech = "Green Technologies" in projects  # -10% resource production cash upkeep (but raw has none anyway)
    continent = nation_data.get("continent", "north_america").lower().replace(" ", "_")

    result = {
        "monetary_gross": 0.0,
        "resource_production_gross": {r: 0.0 for r in ["food","coal","oil","uranium","lead","iron","bauxite"]},
        "manufactured_gross": {"gasoline": 0.0, "munitions": 0.0, "steel": 0.0, "aluminum": 0.0},
        "resource_consumption": {r: 0.0 for r in ["food","coal","oil","uranium","lead","iron","bauxite"]},
        "expenses": {"improvements": 0.0, "infra": 0.0, "land": 0.0, "military": 0.0, "power_fuel_value": 0.0},
        "gross_income": 0.0,
        "net_income": 0.0,
        "pollution_index": 0,
        "power_plants": {},  # Track power plant details
        "raw_improvements": {},  # Track raw improvement details
        "domestic_policy": domestic_policy,  # Include domestic policy in results
        "domestic_policy_effects": {},  # Track applied domestic policy effects
        "city_commerce_rates": [],  # Track per-city commerce rates
        "city_resource_production": [],  # Track per-city resource production
        "total_military_upkeep": 0.0,  # Track total military upkeep
        "total_improvements_upkeep": 0.0,  # Track total improvements upkeep
    }

    total_pop = 0.0
    total_power_capacity = 0
    total_pollution = 0
    total_cities = len(nation_data.get("cities", []))

    for city in nation_data["cities"]:
        # Track per-city commerce rate
        city_commerce_rate = city.get("commerce", 0)
        
        # Store city commerce data
        city_commerce_data = {
            "city_name": city.get("name", "Unknown City"),
            "commerce_rate": city_commerce_rate,
            "population": city["population"],
            "income": 0.0
        }
        
        # Monetary tax income using corrected formula:
        # Gross Income =(((Commerce/50)×0.725+0.725)×Population)×(domestic bonus+treasure bonus)
        commerce_rate = city.get("commerce", 0)
        pop = city["population"]
        
        # Base income calculation: ((Commerce/50)×0.725+0.725)×Population
        base_income_per_pop = ((commerce_rate / 50) * 0.725 + 0.725)
        
        # Domestic policy bonus (1% for Open Markets = 0.01 bonus)
        domestic_bonus = 0.01 if domestic_policy == "Open Markets" else 0.0
        
        # Treasure bonus (not available in API, default to 0)
        treasure_bonus = 0.0
        
        # Apply domestic and treasure bonuses as additive multipliers
        # Formula: Base Income × (1 + domestic_bonus + treasure_bonus)
        bonus_multiplier = 1 + domestic_bonus + treasure_bonus
        city_income = (base_income_per_pop * pop) * bonus_multiplier
            
        result["monetary_gross"] += city_income
        total_pop += pop
        
        # Update city income in commerce data
        city_commerce_data["income"] = city_income
        result["city_commerce_rates"].append(city_commerce_data)

        powered = city.get("powered", True)  # assume true if not present

        # Initialize city resource production tracking
        city_resource_data = {
            "city_name": city.get("name", "Unknown City"),
            "raw_resources": {},
            "manufactured_resources": {},
            "total_raw_production": 0.0,
            "total_manufactured_production": 0.0
        }
        
        # Raw resources
        farms = city["improvements"].get("farm", 0)
        food_prod = food_production(
            city["land"], farms,
            "Mass Irrigation" in projects,
            "Arable Land Initiative" in projects,
            radiation_index,  # Pass radiation index to food production
            "Fallout Shelter" in projects  # Pass Fallout Shelter status
        )
        # Apply continent modifier for food (Antarctica penalty)
        continent_food_modifier = CONTINENT_MODIFIERS.get(continent, {}).get("food", 1.0)
        food_prod *= continent_food_modifier
        result["resource_production_gross"]["food"] += food_prod
        
        # Track food production for this city
        city_resource_data["raw_resources"]["food"] = food_prod
        city_resource_data["total_raw_production"] += food_prod
        
        # Track farm details
        if farms > 0:
            if "farm" not in result["raw_improvements"]:
                result["raw_improvements"]["farm"] = {"count": 0, "pollution": 0, "upkeep": 0}
            result["raw_improvements"]["farm"]["count"] += farms
            farm_pollution = farms * RAW_POLLUTION["farm"]
            result["raw_improvements"]["farm"]["pollution"] += farm_pollution
            total_pollution += farm_pollution
            farm_upkeep = farms * RAW_UPKEEP_DAILY["farm"]
            result["raw_improvements"]["farm"]["upkeep"] += farm_upkeep
            result["expenses"]["improvements"] += farm_upkeep

        # Raw improvement tracking and production (excluding farms which are handled separately)
        for imp, base in RAW_BASE_PER_IMP.items():
            if base is None: continue  # Skip farms as they're handled above
            count = city["improvements"].get(imp, 0)
            if count == 0: continue
            
            # Track raw improvement details
            if imp not in result["raw_improvements"]:
                result["raw_improvements"][imp] = {"count": 0, "pollution": 0, "upkeep": 0}
            result["raw_improvements"][imp]["count"] += count
            
            # Calculate production with stacking bonus
            bonus = stacking_bonus(count, RAW_MAX.get(imp, 10))
            prod = count * base * (1 + bonus)
            
            # Apply project bonuses
            res_name = imp.replace("_mine", "").replace("_well", "")
            if any(p for p in projects if RESOURCE_PROJECTS.get(p) == res_name):
                prod *= 2.0
            
            result["resource_production_gross"][res_name] += prod
            
            # Track per-city resource production
            city_resource_data["raw_resources"][res_name] = prod
            city_resource_data["total_raw_production"] += prod
            
            # Track pollution
            pollution = count * RAW_POLLUTION[imp]
            
            # Apply Green Technologies pollution reduction for farms
            if imp == "farm" and check_project_requirements("Green Technologies", projects, total_cities):
                pollution *= 0.5  # 50% pollution reduction from farms
            
            result["raw_improvements"][imp]["pollution"] += pollution
            total_pollution += pollution
            
            upkeep = count * RAW_UPKEEP_DAILY[imp]
            
            # Apply Green Technologies resource upkeep reduction
            if check_project_requirements("Green Technologies", projects, total_cities):
                upkeep *= 0.9  # 10% resource production upkeep reduction
            
            result["raw_improvements"][imp]["upkeep"] += upkeep
            result["expenses"]["improvements"] += upkeep

        # Manufactured
        for imp, base_prod in MANU_BASE_DAILY.items():
            count = city["improvements"].get(imp, 0)
            if count == 0: continue
            bonus = stacking_bonus(count, 5)
            prod = count * base_prod * (1 + bonus)
            manu_name = imp.replace("_refinery", "").replace("_mill", "")
            
            # Apply project bonuses
            if any(p for p in projects if RESOURCE_PROJECTS.get(p) == manu_name):
                prod *= 2.0
            
            # Apply specific manufacturing bonuses from projects
            if manu_name == "munitions" and "Arms Stockpile" in projects:
                prod *= 1.2  # 20% productivity bonus
            elif manu_name == "aluminum" and "Bauxiteworks" in projects:
                prod *= 1.36  # 36% productivity bonus
            elif manu_name == "gasoline" and "Emergency Gasoline Reserve" in projects:
                prod *= 2.0  # 100% productivity bonus (doubled)
            elif manu_name == "steel" and "Ironworks" in projects:
                prod *= 1.2  # 20% productivity bonus
            
            result["manufactured_gross"][manu_name] += prod
            
            # Track per-city manufactured production
            city_resource_data["manufactured_resources"][manu_name] = prod
            city_resource_data["total_manufactured_production"] += prod

        # Improvement cash upkeep for non-raw improvements (raw improvements handled above)
        for imp, count in city["improvements"].items():
            if count == 0: continue
            # Skip raw improvements as they're handled separately
            if imp in RAW_UPKEEP_DAILY: continue
            upkeep = IMP_UPKEEP_DAILY.get(imp, 0)
            if upkeep > 0 and (powered or imp in ["coal_power","oil_power","wind_power","nuclear_power"]):
                result["expenses"]["improvements"] += count * upkeep

        # Power plant tracking and fuel consumption
        city_power_capacity = 0
        city_pollution = 0
        for imp, count in city["improvements"].items():
            if imp not in POWER_PLANT_CAPACITY: continue
            
            # Track power plant details
            if imp not in result["power_plants"]:
                result["power_plants"][imp] = {"count": 0, "capacity": 0, "pollution": 0}
            result["power_plants"][imp]["count"] += count
            capacity = count * POWER_PLANT_CAPACITY[imp]
            result["power_plants"][imp]["capacity"] += capacity
            city_power_capacity += capacity
            
            # Track pollution
            pollution = count * POWER_PLANT_POLLUTION[imp]
            
            # Apply Green Technologies pollution reduction for manufacturing (power plants)
            if check_project_requirements("Green Technologies", projects, total_cities):
                pollution *= 0.75  # 25% pollution reduction from manufacturing
            
            result["power_plants"][imp]["pollution"] += pollution
            city_pollution += pollution
            
            # Infrastructure-based fuel consumption
            infra_fuel_multiplier = city["infra"] / 100.0
            for fuel, base_amt in POWER_FUEL_PER_100_INFRA.get(imp, {}).items():
                result["resource_consumption"][fuel] += count * base_amt * infra_fuel_multiplier
        
        total_power_capacity += city_power_capacity
        total_pollution += city_pollution

        # Infra & land
        result["expenses"]["infra"] += infra_upkeep(city["infra"])
        result["expenses"]["land"] += land_upkeep(city["land"])
        
        # Add city resource data to result
        result["city_resource_production"].append(city_resource_data)

    # Military upkeep
    mil = nation_data["military"]
    mult = WAR_MULTIPLIER if is_war else 1.0
    military_upkeep = (
        mil["soldiers"] * MIL_PEACETIME["soldiers"] +
        mil["tanks"] * MIL_PEACETIME["tanks"] +
        mil["aircraft"] * MIL_PEACETIME["aircraft"] +
        mil["ships"] * MIL_PEACETIME["ships"] +
        mil.get("missiles", 0) * MIL_PEACETIME["missiles"] +
        mil.get("nukes", 0) * MIL_PEACETIME["nukes"]
    ) * mult
    
    # Apply Imperialism domestic policy 5% reduction to military upkeep
    if domestic_policy == "Imperialism":
        military_upkeep *= 0.95
    
    result["expenses"]["military"] += military_upkeep
    result["total_military_upkeep"] = military_upkeep  # Store total military upkeep
    result["total_improvements_upkeep"] = result["expenses"]["improvements"]  # Store total improvements upkeep

    # Soldier food
    food_rate = SOLDIER_FOOD_WAR if is_war else SOLDIER_FOOD_PEACE
    result["resource_consumption"]["food"] += mil["soldiers"] * food_rate

    # Manufacturing consumption
    for manu, prod in result["manufactured_gross"].items():
        base_per_imp = list(MANU_BASE_DAILY.values())[0]  # all 4.5
        imps_equiv = prod / base_per_imp
        for raw, base_cons in MANU_CONSUME_PER_IMP.get(manu + ("_refinery" if manu != "steel" else "_mill"), {}).items():
            result["resource_consumption"][raw] += imps_equiv * base_cons

    # Net resources
    net_resources = {}
    for r in result["resource_production_gross"]:
        net = result["resource_production_gross"][r] - result["resource_consumption"].get(r, 0)
        net_resources[r] = net
        net_resources.update(result["manufactured_gross"])

    # Resource value (only positive net = income)
    resource_income = sum(max(0, amt) * market_prices.get(r, 0) for r, amt in net_resources.items())
    power_fuel_cost = sum(result["resource_consumption"].get(r, 0) * market_prices.get(r, 0) for r in ["coal","oil","uranium"])

    result["expenses"]["power_fuel_value"] = power_fuel_cost
    result["gross_income"] = result["monetary_gross"] + resource_income
    total_expenses = sum(result["expenses"].values())
    result["net_income"] = result["gross_income"] - total_expenses

    # Activity Center daily bonus (if applicable)
    total_cities = len(nation_data.get("cities", []))
    if check_project_requirements("Activity Center", projects, total_cities):
        # $1M on first day, $2M on subsequent days
        # For now, we'll use $2M as default (assuming not first day)
        result["activity_center_bonus"] = 2000000
        result["monetary_gross"] += result["activity_center_bonus"]
        # Recalculate net income with bonus
        result["gross_income"] = result["monetary_gross"] + resource_income
        result["net_income"] = result["gross_income"] - total_expenses
    
    # Alliance tax (if any)
    tax_rate = nation_data.get("alliance", {}).get("tax_rate", 0) / 100.0
    result["alliance_tax"] = result["net_income"] * tax_rate
    result["final_net_after_tax"] = result["net_income"] - result["alliance_tax"]
    
    # Set final pollution index
    result["pollution_index"] = total_pollution
    
    # Track domestic policy effects
    if domestic_policy:
        result["domestic_policy_effects"] = {
            "policy": domestic_policy,
            "effects_applied": []
        }
        
        if domestic_policy == "Open Markets":
            result["domestic_policy_effects"]["effects_applied"].append("1% gross income bonus")
        elif domestic_policy == "Imperialism":
            result["domestic_policy_effects"]["effects_applied"].append("5% military upkeep reduction")
        elif domestic_policy == "Urbanization":
            result["domestic_policy_effects"]["effects_applied"].append("5% infrastructure cost reduction")
        elif domestic_policy == "Rapid Expansion":
            result["domestic_policy_effects"]["effects_applied"].append("5% land cost reduction")
        elif domestic_policy == "Manifest Destiny":
            result["domestic_policy_effects"]["effects_applied"].append("5% city cost reduction")
        elif domestic_policy == "Technological Advancement":
            result["domestic_policy_effects"]["effects_applied"].append("5% project cost reduction (money only)")

    return result

def get_available_domestic_policies() -> List[str]:
    """Get list of available domestic policies"""
    return list(DOMESTIC_POLICIES.keys())

def validate_domestic_policy(policy_name: str) -> bool:
    """Validate if a domestic policy name is valid"""
    return policy_name in DOMESTIC_POLICIES
