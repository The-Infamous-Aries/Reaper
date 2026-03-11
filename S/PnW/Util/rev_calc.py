import math
from typing import Dict, Any, List, cast, Optional
from datetime import datetime, timezone
from Systems.PnW.Util.query import PNWAPIQuery
import asyncio

RAW_BASE_PER_IMP = {
    "farm": None, 
    "coal_mine": 0.25,      
    "oil_well": 0.25,       
    "uranium_mine": 0.25,   
    "iron_mine": 0.25,      
    "bauxite_mine": 0.25,       
    "lead_mine": 0.25,      
}

RESOURCES_MAX = {
    "coal_mine": 10,
    "oil_well": 10,
    "uranium_mine": 5,
    "iron_mine": 10,
    "bauxite_mine": 10,
    "lead_mine": 10,
    "farm": 20,
    "oil_refinery": 5,
    "munitions_factory": 5, 
    "steel_mill": 5,
    "aluminum_refinery": 5,
}

STACK_BONUS = 0.50  

MANUFACTURED_RESOURCE_MAP = {
    "oil_refinery": "gasoline",
    "munitions_factory": "munitions", 
    "steel_mill": "steel",
    "aluminum_refinery": "aluminum",
}

MANUFACTURED_BASE_PER_IMP = {
    "oil_refinery": 6.0,
    "munitions_factory": 18.0, 
    "steel_mill": 9.0,
    "aluminum_refinery": 9.0,
}

MANU_CONSUME_PER_IMP = { 
    "oil_refinery": {"oil": 6.0},
    "munitions_factory": {"lead": 6.0}, 
    "steel_mill": {"coal": 3.0, "iron": 3.0},
    "aluminum_refinery": {"bauxite": 6.0},
}

POWER_PLANT_BUILD_COSTS = {
    "coal_power": {"money": 5000, "steel": 0, "aluminum": 0},
    "oil_power": {"money": 7000, "steel": 0, "aluminum": 0},
    "wind_power": {"money": 30000, "steel": 0, "aluminum": 25},
    "nuclear_power": {"money": 500000, "steel": 100, "aluminum": 0},
}

POWER_PLANT_CAPACITY = {
    "coal_power": 500,
    "oil_power": 500,
    "wind_power": 250,
    "nuclear_power": 2000,
}

POWER_PLANT_POLLUTION = {
    "coal_power": 8,
    "oil_power": 6,
    "wind_power": 0,
    "nuclear_power": 0,
}

IMP_UPKEEP_TURN = {
    "supermarket": 50,
    "bank": 150,
    "shopping_mall": 450, 
    "stadium": 1013,
    "oil_refinery": 334,
    "munitions_factory": 292, 
    "steel_mill": 334,
    "aluminum_refinery": 209,
    "hospital": 84,
    "recycling_center": 209,
    "subway": 271,
    "police_station": 63,
    "coal_power": 100,
    "oil_power": 150,
    "wind_power": 42,
    "nuclear_power": 875,
    "barracks": 0,
    "factory": 0,
    "hangar": 0,
    "drydock": 0,
    "coal_mine": 400,
    "oil_well": 600,
    "bauxite_mine": 1600,
    "iron_mine": 1600,
    "lead_mine": 1500,
    "uranium_mine": 5000,
    "farm": 300,
}

POWER_FUEL_TURN = {
    "coal_power": {"coal": 0.1},    
    "oil_power": {"oil": 0.1},      
    "nuclear_power": {"uranium": 0.25}, 
    "wind_power": {},               
}

RAW_BUILD_COSTS = {
    "coal_mine": {"money": 1000, "steel": 0, "aluminum": 0},
    "oil_well": {"money": 1500, "steel": 0, "aluminum": 0},
    "bauxite_mine": {"money": 9500, "steel": 0, "aluminum": 0},
    "iron_mine": {"money": 9500, "steel": 0, "aluminum": 0},
    "lead_mine": {"money": 7500, "steel": 0, "aluminum": 0},
    "uranium_mine": {"money": 25000, "steel": 0, "aluminum": 0},
    "farm": {"money": 1000, "steel": 0, "aluminum": 0},
}

IMP_POLLUTION = {
    "barracks": 0,
    "factory": 0,
    "hangar": 0,
    "drydock": 0,
    "hospital": 4,
    "bank": 0,
    "supermarket": 0,
    "shopping_mall": 2, 
    "stadium": 5,
    "subway": -45,
    "recycling_center": -70,
    "police_station": 1,
    "oil_refinery": 32,
    "steel_mill": 40,
    "aluminum_refinery": 40,
    "munitions_factory": 32, 
    "coal_mine": 12,
    "oil_well": 12,
    "bauxite_mine": 12,
    "iron_mine": 12,
    "lead_mine": 12,
    "uranium_mine": 20,
    "farm": 2,
}

CONTINENT_MODIFIERS = {
    "antarctica": {"food": 0.5},  
}

def infra_upkeep(infra: float) -> float:
    return (infra ** 2) * 0.0045

def land_upkeep(land: float) -> float:
    return 0.0

def base_population(infrastructure: float) -> float:
    return float(infrastructure) * 100.0

def city_age_modifier(city_age_days: float) -> float:
    return 1 + max(math.log(city_age_days) / 15, 0) if city_age_days > 0 else 1

def population_formula(base_population: float, city_age_modifier: float) -> float:
    return ((base_population ** 2) / 125000000) + ((base_population * city_age_modifier - base_population) / 850)

def police_modifier(police_stations: int) -> float:
    return float(police_stations) * 2.5

def crime_rate_percent(commerce: float, infrastructure: float, police_stations: int) -> float:
    rate = ((103 - commerce)**2 + (infrastructure * 100)) / 111111 - police_modifier(police_stations)
    return max(0, min(rate, 100))

def pollution_modifier(pollution_index: float) -> float:
    return float(pollution_index) * 0.05

def hospital_modifier(hospital_count: int) -> float:
    return float(hospital_count) * 2.5

def disease_rate_percent(base_pop: float, land_area: float, pollution_index: float, hospital_count: int) -> float:
    pop_density = base_pop / max(1, land_area)
    disease_rate = ((((pop_density**2) * 0.01) - 25) / 100) + (base_pop / 100000) + pollution_modifier(pollution_index) - hospital_modifier(hospital_count)
    return disease_rate

def city_population(base_pop: float, disease_rate: float, crime_rate: float, city_age_in_days: float, infra: float) -> float:
    return (base_pop - ((disease_rate * 100 * infra) / 100) - max((crime_rate / 10) * (100 * infra) - 25, 0)) * (1 + math.log(city_age_in_days) / 15)


PROJECT_EFFECTS = {    
    "Advanced Engineering Corps": {
        "infra_cost_reduction": 0.05,  
        "land_cost_reduction": 0.05,   
        "requirements": ["Center for Civil Engineering", "Arable Land Agency"],
        "type": "cost_reduction"
    },
    "Government Support Agency": {
        "domestic_policy_effect_bonus": 0.50,
        "type": "domestic_policy_modifier"
    },
    "Bureau of Domestic Affairs": {
        "domestic_policy_effect_bonus": 0.25,
        "type": "domestic_policy_modifier"
    },
    "Arable Land Agency": { 
        "land_cost_reduction": 0.05,  
        "type": "land_cost_reduction"
    },
    "Center for Civil Engineering": { 
        "infra_cost_reduction": 0.05,  
        "type": "infra_cost_reduction"
    },
    "Fallout Shelter": {
        "radiation_food_penalty_reduction": 0.15,  
        "nuclear_damage_reduction": 0.10,  
        "fallout_length_reduction": 0.25,  
        "requirements": ["Research & Development Center", "Mass Irrigation"],
        "type": "radiation_protection"
    },
    "Green Technologies": {
        "manufacturing_pollution_reduction": 0.25,  
        "farm_pollution_reduction": 0.50,  
        "subway_effectiveness_bonus": 25,  
        "resource_upkeep_reduction": 0.10,  
        "requirements": ["Space Program"],
        "type": "pollution_reduction"
    },
    "International Trade Center": {
        "max_commerce_bonus": 15,  
        "type": "commerce_bonus"
    },
    "Arms Stockpile": {
        "munitions_factory_bonus": 0.20,  
        "type": "resource_production_bonus"
    },
    "Bauxite Works": { 
        "aluminum_refinery_bonus": 0.36,  
        "type": "resource_production_bonus"
    },
    "Emergency Gasoline Reserve": {
        "oil_refinery_bonus": 1.0,  
        "type": "resource_production_bonus"
    },
    "Iron Works": { 
        "steel_mill_bonus": 0.36,  
        "type": "resource_production_bonus"
    },
    "Mars Landing": {
        "type": "novelty",  
        "requirements": ["Space Program", "Moon Landing"],
        "indestructible": True
    },
    "Mass Irrigation": {
        "food_production_bonus": 0.25,  
        "type": "food_production_bonus"
    },
    "Military Salvage": {
        "salvage_bonus": 0.05,  
        "type": "military_bonus"
    },
    "Missile Launch Pad": {
        "missile_production_bonus": 1,  
        "type": "military_production"
    },
    "Moon Landing": {
        "type": "novelty",  
        "requirements": ["Space Program"],
        "indestructible": True
    },
    "Nuclear Launch Facility": {
        "nuclear_weapon_bonus": 1,  
        "requirements": ["Nuclear Research Facility", "Missile Launch Pad", "Space Program"],
        "type": "military_production"
    },
    "Nuclear Research Facility": {
        "nuclear_weapon_unlock": True,  
        "type": "military_unlock"
    },
    "Pirate Economy": {
        "offensive_war_slot": 1,  
        "loot_bonus": 0.05,  
        "war_requirement": 50,  
        "requirements": ["Propaganda Bureau"],
        "type": "military_bonus"
    },
    "Propaganda Bureau": {
        "recruitment_bonus": 0.10,  
        "unit_types": ["soldiers", "tanks", "aircraft", "ships"],  
        "type": "military_bonus"
    },
    "Military Research Center": {
        "project_slot_bonus": 2,  
        "requirements": ["Propaganda Bureau"],  
        "type": "utility_bonus"
    },
    "Military Doctrine": {
        "military_research_cost_reduction": 0.05,  
        "requirements": ["Military Research Center"],  
        "type": "military_bonus"
    },
    "Recycling Initiative": {
        "recycling_center_pollution_bonus": 5,  
        "recycling_center_max_bonus": 1,  
        "requirements": ["Center for Civil Engineering"],
        "type": "pollution_reduction"
    },
    "Research & Development Center": {
        "project_slot_bonus": 2,  
        "fallout_shelter_requirement": True,  
        "type": "utility_bonus"
    },
    "Space Program": {
        "space_project_unlock": True,  
        "missile_production_bonus": 1,  
        "requirements": ["Missile Launch Pad"],
        "type": "unlock"
    },
    "Specialized Police Training Program": {
        "police_station_crime_reduction": 0.01,  
        "commerce_bonus": 0.04,  
        "type": "city_bonus"
    },
    "Spy Satellite": {
        "spy_production_bonus": 1,  
        "espionage_damage_bonus": 0.50,  
        "espionage_cost_reduction": 0.20,  
        "requirements": ["Space Program", "Intelligence Agency"],
        "type": "espionage_bonus"
    },
    "Surveillance Network": {
        "espionage_defense_bonus": 0.10,  
        "espionage_identification_bonus": 0.10,  
        "espionage_damage_reduction": 0.25,  
        "requirements": ["Spy Satellite"],
        "type": "espionage_defense"
    },
    "Telecommunications Satellite": {
        "commerce_bonus": 0.10,  
        "mall_effectiveness_bonus": 0.10,  
        "requirements": ["Space Program"],
        "type": "commerce_bonus"
    },
    "Uranium Enrichment Program": {
        "uranium_mine_bonus": 1.0,
        "type": "resource_production_bonus"
    },
    "Vital Defense System": {
        "nuclear_thwart_chance": 0.10,  
        "type": "nuclear_defense"
    },
}

DOMESTIC_POLICIES = {
    "Manifest Destiny": {
        "city_cost_reduction": 0.05,  
        "type": "city_cost_reduction"
    },
    "Urbanization": {
        "infra_cost_reduction": 0.05,  
        "type": "infra_cost_reduction"
    },
    "Technological Advancement": {
        "project_cost_reduction": 0.05,  
        "type": "project_cost_reduction"
    },
    "Open Markets": {
        "gross_income_bonus": 0.01,  
        "type": "income_bonus"
    },
    "Imperialism": {
        "military_upkeep_reduction": 0.05,  
        "type": "military_upkeep_reduction"
    },
    "Rapid Expansion": {
        "land_cost_reduction": 0.05,  
        "type": "land_cost_reduction"
    },
}

MIL_PEACETIME = {
    "soldiers": 1.25,
    "tanks": 50.0,
    "aircraft": 750.0,
    "ships": 3750.0,
    "missiles": 21000.0,
    "nukes": 35000.0,
    "spies": 2400.0,
}
MIL_WARTIME = {
    "soldiers": 1.88,
    "tanks": 75.0,
    "aircraft": 1000.0,
    "ships": 5000.0,
    "missiles": 31500.0,
    "nukes": 52500.0,
    "spies": 2400.0,
}

SOLDIER_FOOD_PEACE = 1.0 / 750.0 
SOLDIER_FOOD_WAR = 1.0 / 500.0

def stacking_bonus(count: int, max_allowed: int) -> float:
    if count <= 1 or max_allowed <= 1:
        return 0.0
    bonus = (float(count - 1) / float(max_allowed - 1)) * 0.50
    return min(bonus, 0.50)

def check_project_requirements(project_name: str, projects: set, current_cities: int = 0) -> bool:
    if not projects or project_name not in projects:
        return False
    
    project_info = PROJECT_EFFECTS.get(project_name, {})
    min_cities = cast(float, project_info.get("min_cities", 0))
    max_cities = cast(float, project_info.get("max_cities", float('inf')))
    
    if current_cities < min_cities or current_cities > max_cities:
        return False
    
    requirements = cast(List[str], project_info.get("requirements", []))
    for req in requirements:
        if req not in projects:
            return False
    
    return True

def food_production(land: float, farms: int, has_mass_irr: bool, has_arable: bool, radiation_index: float = 1000.0, has_fallout_shelter: bool = False, is_food_winter: bool = False) -> float:
    prod = farms * (land / 500.0)
    
    if has_mass_irr:
        prod *= 1.25  
    if has_arable:
        prod *= 2.0  
        
    radiation_effect = radiation_index / 1000.0
    if has_fallout_shelter and radiation_index < 1000.0:
        radiation_penalty = 1.0 - radiation_effect  
        reduced_penalty = radiation_penalty * 0.85  
        radiation_effect = 1.0 - reduced_penalty
    
    prod *= radiation_effect
    if is_food_winter:
        prod *= 0.80 
    return prod

def calculate_full_revenue(
    nation_data: Dict[str, Any],
    market_prices: Dict[str, float],
    game_date: datetime,
    is_war: bool = False,
    radiation_index: float = 1000.0,
    domestic_policy: Optional[str] = None,
    color_bonus: float = 0.0,
    is_food_winter: bool = False,
) -> Dict[str, Any]:

    all_project_names = [
        "Activity Center", "Advanced Engineering Corps", "Advanced Pirate Economy", "Arable Land Agency",
        "Arms Stockpile", "Bauxite Works", "Bureau of Domestic Affairs", "Center for Civil Engineering",
        "Clinical Research Center", "Emergency Gasoline Reserve", "Fallout Shelter", "Government Support Agency",
        "Green Technologies", "Guiding Satellite", "Central Intelligence Agency", "International Trade Center",
        "Iron Dome", "Iron Works", "Moon Landing", "Mars Landing", "Mass Irrigation", "Military Doctrine",
        "Military Research Center", "Military Salvage", "Missile Launch Pad", "Nuclear Launch Facility",
        "Nuclear Research Facility", "Pirate Economy", "Propaganda Bureau", "Recycling Initiative",
        "Research & Development Center", "Space Program", "Specialized Police Training Program",
        "Spy Satellite", "Surveillance Network", "Telecommunications Satellite", "Uranium Enrichment Program",
        "Vital Defense System"
    ]
    projects = set()
    for project_name in all_project_names:
        nation_data_key = project_name.lower().replace(" & ", "_and_").replace(" ", "_")
        if nation_data.get(nation_data_key):
            projects.add(project_name)
            
    has_green_tech = "Green Technologies" in projects  
    continent = nation_data.get("continent", "north_america").lower().replace(" ", "_")

    result: Dict[str, Any] = cast(Dict[str, Any], {
        "monetary_gross": 0.0,
        "monetary_gross_turn": 0.0,
        "resource_production_gross": {r: 0.0 for r in ["food","coal","oil","uranium","lead","iron","bauxite"]},
        "manufactured_gross": {"gasoline": 0.0, "munitions": 0.0, "steel": 0.0, "aluminum": 0.0},
        "net_resource_production": {r: 0.0 for r in ["food","coal","oil","uranium","lead","iron","bauxite", "gasoline", "munitions", "steel", "aluminum"]},
        "expenses": {"improvements": 0.0, "infra": 0.0, "land": 0.0, "military": 0.0, "power_fuel_value": 0.0, "resource_deficit": 0.0},
        "gross_income": 0.0,
        "net_income": 0.0,
        "pollution_index": 0,
        "power_plants": {},  
        "raw_improvements": {},  
        "domestic_policy": domestic_policy,  
        "domestic_policy_effects": {},  
        "city_commerce_rates": [],  
        "city_resource_production": [],  
        "total_military_upkeep": 0.0,  
        "total_improvements_upkeep": 0.0,
        "projects": list(projects),
        "intermediate_goods": [], 
    })

    domestic_policy_multiplier = 1.0
    if "Government Support Agency" in projects:
        domestic_policy_multiplier += PROJECT_EFFECTS["Government Support Agency"]["domestic_policy_effect_bonus"]
    if "Bureau of Domestic Affairs" in projects:
        domestic_policy_multiplier += PROJECT_EFFECTS["Bureau of Domestic Affairs"]["domestic_policy_effect_bonus"]

    total_pop = 0.0
    total_commerce_rate = 0.0 
    total_power_capacity = 0
    total_pollution = 0
    total_gross_income_day = 0.0
    cities_data = nation_data.get("cities", [])
    if not isinstance(cities_data, list):
        cities_data = []

    total_cities = len(cities_data)

    for city in cities_data:
        city_commerce_rate = city.get("commerce", 0)
        total_commerce_rate += city_commerce_rate 
        
        city_commerce_data = {
            "city_name": city.get("name", "Unknown City"),
            "commerce_rate": city_commerce_rate,
            "population": city.get("population", 0),
            "income": 0.0
        }
        
        city_infrastructure = city.get("infrastructure", 0) 
        city_land_area = city.get("land", 0)
        city_improvements = city.get("improvements", {})
        if not isinstance(city_improvements, dict):
            city_improvements = {}
            
        city_commerce = city.get("commerce", 0)
        
        commerce_bonus_percentage = 0.0
        for imp_name, imp_count in city_improvements.items():
            if imp_name == "subway":
                commerce_bonus_percentage += 0.08 * imp_count
            elif imp_name == "supermarket":
                commerce_bonus_percentage += 0.04 * imp_count
            elif imp_name == "bank":
                commerce_bonus_percentage += 0.06 * imp_count
            elif imp_name == "shopping_mall":
                commerce_bonus_percentage += 0.08 * imp_count
            elif imp_name == "stadium":
                commerce_bonus_percentage += 0.10 * imp_count
        
        if "Specialized Police Training Program" in projects:
            commerce_bonus_percentage += 0.04

        city_commerce *= (1 + commerce_bonus_percentage)

        if "International Trade Center" in projects:
            city_commerce += PROJECT_EFFECTS["International Trade Center"]["max_commerce_bonus"]

        city_police_stations = city_improvements.get("police_station", 0)
        city_hospital_count = city_improvements.get("hospital", 0)
        city_date_str = city.get("date")
        if city_date_str:
            dt_obj = datetime.fromisoformat(city_date_str.replace("Z", "+00:00"))
            if dt_obj.tzinfo is None:
                dt_obj = dt_obj.replace(tzinfo=timezone.utc)
            city_age_days = (game_date - dt_obj).days
        else:
            city_age_days = 0

        city_pollution_index = 0.0

        for imp_name, imp_count in city_improvements.items():
            if imp_name in IMP_POLLUTION:
                pollution_value = IMP_POLLUTION[imp_name]
                if imp_name == "recycling_center" and "Recycling Initiative" in projects:
                    pollution_value -= PROJECT_EFFECTS["Recycling Initiative"]["recycling_center_pollution_bonus"]
                city_pollution_index += pollution_value * imp_count
            elif imp_name in POWER_PLANT_POLLUTION:
                city_pollution_index += POWER_PLANT_POLLUTION[imp_name] * imp_count
        
        base_pop = base_population(city_infrastructure)
        crime_rate = crime_rate_percent(city_commerce, city_infrastructure, city_police_stations)
        disease_rate = disease_rate_percent(base_pop, city_land_area, city_pollution_index, city_hospital_count)

        pop = city_population(base_pop, disease_rate, crime_rate, city_age_days, city_infrastructure)
        total_pop += pop

        city_income_per_day = (((city_commerce / 50.0) * 0.725 + 0.725) * pop)
        total_gross_income_day += city_income_per_day
        city_commerce_data["income"] = city_income_per_day

        city_commerce_data["commerce_rate"] = city_commerce
        result["city_commerce_rates"].append(city_commerce_data)

        powered = city.get("powered", True)  

        city_resource_data = {
            "city_name": city.get("name", "Unknown City"),
            "raw_resources": {},
            "manufactured_resources": {},
            "total_raw_production": 0.0,
            "total_manufactured_production": 0.0
        }

        farms = city_improvements.get("farm", 0)
        food_prod = food_production(
            city.get("land", 0), farms,
            "Mass Irrigation" in projects,
            "Arable Land Agency" in projects, 
            radiation_index,  
            "Fallout Shelter" in projects,  
            is_food_winter
        )
        continent_food_modifier = CONTINENT_MODIFIERS.get(continent, {}).get("food", 1.0)
        food_prod *= continent_food_modifier
        result["resource_production_gross"]["food"] += food_prod
        
        city_resource_data["raw_resources"]["food"] = food_prod
        city_resource_data["total_raw_production"] += food_prod
        
        if farms > 0:
            if "farm" not in result["raw_improvements"]:
                result["raw_improvements"]["farm"] = {"count": 0, "pollution": 0, "upkeep": 0}
            result["raw_improvements"]["farm"]["count"] += farms
            farm_pollution = farms * IMP_POLLUTION["farm"]
            result["raw_improvements"]["farm"]["pollution"] += farm_pollution
            total_pollution += farm_pollution
            farm_upkeep = farms * IMP_UPKEEP_TURN["farm"]
            result["raw_improvements"]["farm"]["upkeep"] += farm_upkeep
            result["expenses"]["improvements"] += farm_upkeep

        for imp, base in RAW_BASE_PER_IMP.items():
            if base is None: continue  
            count = city_improvements.get(imp, 0)
            if count == 0: continue
            
            if imp not in result["raw_improvements"]:
                result["raw_improvements"][imp] = {"count": 0, "pollution": 0, "upkeep": 0}
            result["raw_improvements"][imp]["count"] += count
            
            bonus = stacking_bonus(count, RESOURCES_MAX.get(imp, 10))
            prod = count * base * (1 + bonus)
            
            res_name = imp.replace("_mine", "").replace("_well", "")

            if imp == "uranium_mine" and "Uranium Enrichment Program" in projects:
                project_effect = PROJECT_EFFECTS.get("Uranium Enrichment Program")
                if project_effect and "uranium_mine_bonus" in project_effect:
                    prod *= (1 + cast(float, project_effect["uranium_mine_bonus"]))

            continent_bonus = CONTINENT_MODIFIERS.get(continent, {}).get(res_name, 1.0)
            prod *= continent_bonus
            
            result["resource_production_gross"][res_name] += prod
            
            city_resource_data["raw_resources"][res_name] = prod
            city_resource_data["total_raw_production"] += prod
            
            pollution = count * IMP_POLLUTION[imp]
            
            if imp == "farm" and check_project_requirements("Green Technologies", projects, total_cities):
                pollution *= 0.5  
            
            result["raw_improvements"][imp]["pollution"] += pollution
            total_pollution += pollution
            
            upkeep = count * IMP_UPKEEP_TURN[imp]
            
            if check_project_requirements("Green Technologies", projects, total_cities):
                upkeep *= 0.9  
            
            result["raw_improvements"][imp]["upkeep"] += upkeep
            result["expenses"]["improvements"] += upkeep

        for imp, base_prod in MANUFACTURED_BASE_PER_IMP.items():
            count = city_improvements.get(imp, 0)
            if count == 0: continue

            prod = base_prod * count
            manu_bonus = stacking_bonus(count, RESOURCES_MAX.get(imp, 10))
            prod *= (1 + manu_bonus)

            manu_name = MANUFACTURED_RESOURCE_MAP.get(imp)
                       
            if "Emergency Gasoline Reserve" in projects and imp == "oil_refinery":
                project_effect = PROJECT_EFFECTS.get("Emergency Gasoline Reserve")
                if project_effect and "oil_refinery_bonus" in project_effect:
                    prod *= (1 + cast(float, project_effect["oil_refinery_bonus"]))
            if "Arms Stockpile" in projects and imp == "munitions_factory":
                project_effect = PROJECT_EFFECTS.get("Arms Stockpile")
                if project_effect and "munitions_factory_bonus" in project_effect:
                    prod *= (1 + cast(float, project_effect["munitions_factory_bonus"]))
            if "Bauxite Works" in projects and imp == "aluminum_refinery": 
                project_effect = PROJECT_EFFECTS.get("Bauxite Works")
                if project_effect and "aluminum_refinery_bonus" in project_effect:
                    prod *= (1 + cast(float, project_effect["aluminum_refinery_bonus"]))
            if "Iron Works" in projects and imp == "steel_mill":
                project_effect = PROJECT_EFFECTS.get("Iron Works")
                if project_effect and "steel_mill_bonus" in project_effect:
                    prod *= (1 + cast(float, project_effect["steel_mill_bonus"]))
            
            result["manufactured_gross"][manu_name] += prod
            
            city_resource_data["manufactured_resources"][manu_name] = prod
            city_resource_data["total_manufactured_production"] += prod

            consumption_mapping = MANU_CONSUME_PER_IMP.get(imp, {})
            for resource_consumed, amount_per_imp in consumption_mapping.items():
                total_consumed = count * amount_per_imp
                result["net_resource_production"][resource_consumed] -= total_consumed * 12

        for imp, count in city_improvements.items():
            if count == 0: continue
            upkeep = IMP_UPKEEP_TURN.get(imp, 0)
            if upkeep > 0 and (powered or imp in ["coal_power","oil_power","wind_power","nuclear_power"]):
                result["expenses"]["improvements"] += count * upkeep

        city_power_capacity = 0
        city_pollution = 0
        for imp, count in city_improvements.items():
            if imp not in POWER_PLANT_CAPACITY: continue
            
            if imp not in result["power_plants"]:
                result["power_plants"][imp] = {"count": 0, "capacity": 0, "pollution": 0}
            result["power_plants"][imp]["count"] += count
            capacity = count * POWER_PLANT_CAPACITY[imp]
            result["power_plants"][imp]["capacity"] += capacity
            city_power_capacity += capacity
            
            pollution = count * POWER_PLANT_POLLUTION[imp]
            
            if check_project_requirements("Green Technologies", projects, total_cities):
                pollution *= 0.75  
            
            result["power_plants"][imp]["pollution"] += pollution
            city_pollution += pollution
            
            # FIXED: Removed infrastructure multiplier scaling. Now burns a flat turn rate.
            infra_supported_by_power_plants = 0
            for imp, count in city_improvements.items():
                if imp in POWER_PLANT_CAPACITY:
                    infra_supported_by_power_plants += POWER_PLANT_CAPACITY[imp] * count
            
            infra_to_power = min(city_infrastructure, infra_supported_by_power_plants)

            for fuel, base_amt in POWER_FUEL_TURN.get(imp, {}).items():
                if imp == "coal_power" or imp == "oil_power":
                    fuel_consumed = (infra_to_power / 100) * base_amt
                    result["net_resource_production"][fuel] -= fuel_consumed * count * 12
                elif imp == "nuclear_power":
                    fuel_consumed = (infra_to_power / 1000) * base_amt
                    result["net_resource_production"][fuel] -= fuel_consumed * count * 12
        
        total_power_capacity += city_power_capacity
        total_pollution += city_pollution

        result["expenses"]["infra"] += infra_upkeep(city.get("infrastructure", 0)) 
        result["expenses"]["land"] += land_upkeep(city.get("land", 0))
        
        result["city_resource_production"].append(city_resource_data)

    domestic_bonus = 0.0
    if domestic_policy == "Open Markets":
        domestic_bonus = DOMESTIC_POLICIES["Open Markets"]["gross_income_bonus"] * domestic_policy_multiplier

    # treasure_bonus is not in the API data yet, so we default to 0
    treasure_bonus = nation_data.get('treasure_bonus', 0.0)

    # Gross Income =(((Commerce/50)×0.725+0.725)×Population)×(domestic bonus+treasure bonus)+color bonus
    nation_income_per_day = total_gross_income_day * (1 + domestic_bonus + treasure_bonus) + color_bonus
    result["monetary_gross_turn"] = nation_income_per_day / 12
    result["monetary_gross"] = nation_income_per_day

    for r, amount in result["resource_production_gross"].items():
        result["net_resource_production"][r] += amount
    for r, amount in result["manufactured_gross"].items():
        result["net_resource_production"][r] += amount

    upkeep_dict = MIL_WARTIME if is_war else MIL_PEACETIME
    military_upkeep = (
        nation_data.get("soldiers", 0) * upkeep_dict["soldiers"] +
        nation_data.get("tanks", 0) * upkeep_dict["tanks"] +
        nation_data.get("aircraft", 0) * upkeep_dict["aircraft"] +
        nation_data.get("ships", 0) * upkeep_dict["ships"] +
        nation_data.get("missiles", 0) * upkeep_dict["missiles"] +
        nation_data.get("nukes", 0) * upkeep_dict["nukes"] +
        nation_data.get("spies", 0) * upkeep_dict["spies"]
    )
    
    if domestic_policy == "Imperialism":
        military_upkeep *= 0.95
    
    result["expenses"]["military"] += military_upkeep
    result["total_military_upkeep"] = military_upkeep  
    result["total_improvements_upkeep"] = result["expenses"]["improvements"]  

    food_rate = SOLDIER_FOOD_WAR if is_war else SOLDIER_FOOD_PEACE
    result["net_resource_production"]["food"] -= nation_data.get("soldiers", 0) * food_rate * 12

    intermediate_goods = set()
    all_improvements = set()
    if cities_data:
        for city in cities_data:
            if city.get('improvements'):
                for imp_name in city.get('improvements', {}).keys():
                    all_improvements.add(imp_name)

    for imp_name in all_improvements:
        if imp_name in MANU_CONSUME_PER_IMP:
            for resource in MANU_CONSUME_PER_IMP[imp_name].keys():
                intermediate_goods.add(resource)
    result["intermediate_goods"] = list(intermediate_goods)

    resource_deficit_cost_daily = 0.0
    resource_surplus_value_daily = 0.0
    for resource, net_prod in result["net_resource_production"].items():
        if net_prod < 0:
            resource_price = market_prices.get(resource.lower(), 0.0)
            deficit_cost = -net_prod * resource_price
            resource_deficit_cost_daily += deficit_cost
        elif net_prod > 0:
            if resource not in intermediate_goods:
                resource_price = market_prices.get(resource.lower(), 0.0)
                surplus_value = net_prod * resource_price
                resource_surplus_value_daily += surplus_value
            
    result["expenses"]["resource_deficit"] = resource_deficit_cost_daily / 12
    result["monetary_gross"] += resource_surplus_value_daily
    result["monetary_gross_turn"] += resource_surplus_value_daily / 12

    alliance_data: Dict[str, Any] = nation_data.get("alliance", {})
    if not isinstance(alliance_data, dict): alliance_data = {}
    
    tax_brackets = alliance_data.get("tax_brackets", [])
    tax_id = nation_data.get("tax_id")
    tax_rate = 0.1  # Default 10% tax rate
    
    if tax_brackets:
        matched_bracket = next((b for b in tax_brackets if str(b.get("id")) == str(tax_id)), None)
        if not matched_bracket and len(tax_brackets) > 0:
            matched_bracket = tax_brackets[0]
        
        if matched_bracket:
            bracket_tax_rate = matched_bracket.get("tax_rate")
            if bracket_tax_rate is not None:
                tax_rate = bracket_tax_rate / 100.0
            # If tax_rate is None, keep the default 10% tax rate
            
    # Calculate tax on both monetary income and resource value
    monetary_tax = result["monetary_gross"] * tax_rate
    
    # Calculate tax on resource production (both raw and manufactured)
    resource_tax_value = 0.0
    
    # Tax raw resource production
    for res_name, amount in result.get("resource_production_gross", {}).items():
        if amount > 0 and res_name in market_prices:
            resource_value = amount * market_prices[res_name]
            resource_tax_value += resource_value * tax_rate
    
    # Tax manufactured resource production  
    for res_name, amount in result.get("manufactured_gross", {}).items():
        if amount > 0 and res_name in market_prices:
            resource_value = amount * market_prices[res_name]
            resource_tax_value += resource_value * tax_rate
    
    total_tax = monetary_tax + resource_tax_value
    result["alliance_tax"] = total_tax
    result["monetary_tax"] = monetary_tax
    result["resource_tax"] = resource_tax_value

    cash_expenses_turn = (
        result["expenses"].get("improvements", 0) +
        result["expenses"].get("infra", 0) +
        result["expenses"].get("land", 0) +
        result["expenses"].get("military", 0) +
        result["expenses"].get("resource_deficit", 0)
    )
    cash_expenses_daily = cash_expenses_turn * 12

    result["gross_income"] = result["monetary_gross"]
    result["net_income"] = result["monetary_gross"] - cash_expenses_daily
    result["final_net_after_tax"] = result["monetary_gross"] - result["alliance_tax"] - cash_expenses_daily
    
    result["pollution_index"] = total_pollution
    
    if domestic_policy:
        domestic_policy_effects_dict: Dict[str, Any] = {
            "policy": domestic_policy,
            "effects_applied": []
        }
        result["domestic_policy_effects"] = domestic_policy_effects_dict

        effects_applied_list: List[str] = domestic_policy_effects_dict["effects_applied"]
        
        if domestic_policy == "Open Markets":
            gross_income_bonus = DOMESTIC_POLICIES["Open Markets"]["gross_income_bonus"] * domestic_policy_multiplier
            result["gross_income"] += result["gross_income"] * gross_income_bonus
            effects_applied_list.append(f"{gross_income_bonus*100:.0f}% gross income bonus")
        elif domestic_policy == "Imperialism":
            military_upkeep_reduction = DOMESTIC_POLICIES["Imperialism"]["military_upkeep_reduction"] * domestic_policy_multiplier
            result["total_military_upkeep"] *= (1 - military_upkeep_reduction)
            effects_applied_list.append(f"{military_upkeep_reduction*100:.0f}% military upkeep reduction")
        elif domestic_policy == "Urbanization":
            infra_cost_reduction = DOMESTIC_POLICIES["Urbanization"]["infra_cost_reduction"] * domestic_policy_multiplier
            result["domestic_policy_effects"]["infra_cost_reduction"] = infra_cost_reduction
            effects_applied_list.append(f"{infra_cost_reduction*100:.0f}% infrastructure cost reduction")
        elif domestic_policy == "Rapid Expansion":
            land_cost_reduction = DOMESTIC_POLICIES["Rapid Expansion"]["land_cost_reduction"] * domestic_policy_multiplier
            result["domestic_policy_effects"]["land_cost_reduction"] = land_cost_reduction
            effects_applied_list.append(f"{land_cost_reduction*100:.0f}% land cost reduction")
        elif domestic_policy == "Manifest Destiny":
            city_cost_reduction = DOMESTIC_POLICIES["Manifest Destiny"]["city_cost_reduction"] * domestic_policy_multiplier
            result["domestic_policy_effects"]["city_cost_reduction"] = city_cost_reduction
            effects_applied_list.append(f"{city_cost_reduction*100:.0f}% city cost reduction")
        elif domestic_policy == "Technological Advancement":
            project_cost_reduction = DOMESTIC_POLICIES["Technological Advancement"]["project_cost_reduction"] * domestic_policy_multiplier
            result["domestic_policy_effects"]["project_cost_reduction"] = project_cost_reduction
            effects_applied_list.append(f"{project_cost_reduction*100:.0f}% project cost reduction")

    return result

async def calculate_full_revenue_with_query(
    nation_data: Dict[str, Any],
    query_instance: Optional[PNWAPIQuery] = None,
    is_war: bool = False,
    radiation_index: float = 1000.0,
    domestic_policy: Optional[str] = None,
    color_bonus: float = 0.0,
    is_food_winter: bool = False,
) -> Dict[str, Any]:
    if query_instance is None:
        query_instance = PNWAPIQuery()

    game_info_task = query_instance.get_game_info()
    trade_prices_task = query_instance.get_trade_resource_values()
    game_info, trade_prices = await asyncio.gather(game_info_task, trade_prices_task)

    # FIXED: Convert API fetched resources to lowercase consistently
    market_prices = {item['resource'].lower(): item['average_price'] for item in trade_prices or []}

    game_date = datetime.now(timezone.utc)
    if game_info and game_info.get('game_date'):
        try:
            game_date = datetime.fromisoformat(game_info['game_date'].replace("Z", "+00:00"))
            if game_date.tzinfo is None:
                game_date = game_date.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass

    # Fallback for fetching tax bracket if not included in the main query
    # Note: calculate_full_revenue will apply a default 10% tax rate if no valid tax bracket is found
    alliance_data = nation_data.get("alliance")
    tax_id = nation_data.get("tax_id")

    if alliance_data and isinstance(alliance_data, dict) and tax_id:
        tax_brackets = alliance_data.get("tax_brackets")
        if tax_brackets is None:  # Permissions issue might cause this to be null
            alliance_id = alliance_data.get("id")
            if alliance_id and hasattr(query_instance, 'get_alliance_tax_bracket'):
                bracket = await query_instance.get_alliance_tax_bracket(str(alliance_id), str(tax_id))
                if bracket:
                    alliance_data["tax_brackets"] = [bracket]  

    return calculate_full_revenue(
        nation_data=nation_data,
        market_prices=market_prices,
        game_date=game_date,
        is_war=is_war,
        radiation_index=radiation_index,
        domestic_policy=domestic_policy,
        color_bonus=color_bonus,
        is_food_winter=is_food_winter,
    )

def get_available_domestic_policies() -> List[str]:
    return list(DOMESTIC_POLICIES.keys())

def validate_domestic_policy(policy_name: str) -> bool:
    return policy_name in DOMESTIC_POLICIES