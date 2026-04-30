"""
Correct improvement upkeep constants based on official game values.

This module contains the accurate upkeep costs for all improvements
as specified in the game mechanics, using precise decimal values
for penny-accurate calculations.
"""

from decimal import Decimal, ROUND_HALF_UP

# Power Plant Upkeep (per turn) - Exact decimal values
POWER_UPKEEP_TURN = {
    "coal_power": Decimal("100.00"),        # $1200/day ÷ 12 = $100.00/turn
    "oil_power": Decimal("150.00"),         # $1800/day ÷ 12 = $150.00/turn  
    "nuclear_power": Decimal("875.00"),     # $10500/day ÷ 12 = $875.00/turn
    "wind_power": Decimal("41.67"),         # $500/day ÷ 12 = $41.666.../turn
}

# Civil Improvement Upkeep (per turn) - Exact decimal values
CIVIL_UPKEEP_TURN = {
    "police_station": Decimal("62.50"),     # $750/day ÷ 12 = $62.50/turn
    "hospital": Decimal("83.33"),           # $1000/day ÷ 12 = $83.333.../turn
    "recycling_center": Decimal("208.33"),  # $2500/day ÷ 12 = $208.333.../turn
    "subway": Decimal("270.83"),            # $3250/day ÷ 12 = $270.833.../turn
    "supermarket": Decimal("50.00"),        # $600/day ÷ 12 = $50.00/turn
    "bank": Decimal("150.00"),              # $1800/day ÷ 12 = $150.00/turn
    "shopping_mall": Decimal("450.00"),     # $5400/day ÷ 12 = $450.00/turn
    "stadium": Decimal("1012.50"),          # $12150/day ÷ 12 = $1012.50/turn
}

# Resource Production Upkeep (per turn) - Exact decimal values
RESOURCE_UPKEEP_TURN = {
    # Mines
    "coal_mine": Decimal("33.33"),          # $400/day ÷ 12 = $33.333.../turn
    "oil_well": Decimal("50.00"),           # $600/day ÷ 12 = $50.00/turn
    "lead_mine": Decimal("125.00"),         # $1500/day ÷ 12 = $125.00/turn
    "iron_mine": Decimal("133.33"),         # $1600/day ÷ 12 = $133.333.../turn
    "bauxite_mine": Decimal("133.33"),      # $1600/day ÷ 12 = $133.333.../turn
    "uranium_mine": Decimal("416.67"),      # $5000/day ÷ 12 = $416.666.../turn
    "farm": Decimal("25.00"),               # $300/day ÷ 12 = $25.00/turn
    
    # Manufacturing
    "oil_refinery": Decimal("333.33"),      # $4000/day ÷ 12 = $333.333.../turn
    "steel_mill": Decimal("333.33"),        # $4000/day ÷ 12 = $333.333.../turn
    "aluminum_refinery": Decimal("208.33"), # $2500/day ÷ 12 = $208.333.../turn
    "munitions_factory": Decimal("291.67"), # $3500/day ÷ 12 = $291.666.../turn
}

# Military Building Upkeep (per turn) - these have NO upkeep according to game mechanics
MILITARY_UPKEEP_TURN = {
    "barracks": Decimal("0.00"),    # No daily upkeep cost
    "hangar": Decimal("0.00"),      # No daily upkeep cost  
    "drydock": Decimal("0.00"),     # No daily upkeep cost
    "factory": Decimal("0.00"),     # No daily upkeep cost
}

# Power Plant Resource Consumption (per turn) - Exact decimal values
POWER_FUEL_CONSUMPTION_TURN = {
    # Coal power: 1.2 tons/day per 100 infra = 0.1/turn per 100 infra
    # 500 infra capacity = 5 blocks of 100 = 0.5/turn total per plant
    "coal_power": {"coal": Decimal("0.50")},
    
    # Oil power: 1.2 tons/day per 100 infra = 0.1/turn per 100 infra  
    # 500 infra capacity = 5 blocks of 100 = 0.5/turn total per plant
    "oil_power": {"oil": Decimal("0.50")},
    
    # Nuclear power: 3.0 tons/day per 1000 infra = 0.25/turn per 1000 infra
    # 2000 infra capacity = 2 blocks of 1000 = 0.5/turn total per plant
    "nuclear_power": {"uranium": Decimal("0.50")},
    
    # Wind power: No resource consumption
    "wind_power": {},
}

# Power Plant Infrastructure Capacity
POWER_CAPACITY = {
    "coal_power": 500,      # Can power up to 500 infrastructure
    "oil_power": 500,       # Can power up to 500 infrastructure
    "nuclear_power": 2000,  # Can power up to 2000 infrastructure
    "wind_power": 250,      # Can power up to 250 infrastructure
}

def get_improvement_upkeep_per_turn(improvement_type: str, count: int) -> Decimal:
    """
    Get the total upkeep cost per turn for a given improvement type and count.
    
    Args:
        improvement_type: The type of improvement (e.g., 'hospital', 'coal_power')
        count: Number of improvements of this type
        
    Returns:
        Total upkeep cost per turn as Decimal for precise calculation
    """
    count_decimal = Decimal(str(count))
    
    if improvement_type in POWER_UPKEEP_TURN:
        return POWER_UPKEEP_TURN[improvement_type] * count_decimal
    elif improvement_type in CIVIL_UPKEEP_TURN:
        return CIVIL_UPKEEP_TURN[improvement_type] * count_decimal
    elif improvement_type in RESOURCE_UPKEEP_TURN:
        return RESOURCE_UPKEEP_TURN[improvement_type] * count_decimal
    elif improvement_type in MILITARY_UPKEEP_TURN:
        return MILITARY_UPKEEP_TURN[improvement_type] * count_decimal
    else:
        return Decimal("0.00")

def get_power_fuel_consumption_per_turn(power_type: str, count: int) -> dict:
    """
    Get the total fuel consumption per turn for power plants.
    
    Args:
        power_type: The type of power plant (e.g., 'coal_power', 'oil_power')
        count: Number of power plants of this type
        
    Returns:
        Dictionary with resource consumption per turn as Decimal values
    """
    if power_type in POWER_FUEL_CONSUMPTION_TURN:
        consumption = {}
        count_decimal = Decimal(str(count))
        for resource, amount in POWER_FUEL_CONSUMPTION_TURN[power_type].items():
            consumption[resource] = amount * count_decimal
        return consumption
    else:
        return {}

def round_to_cents(value: Decimal) -> Decimal:
    """
    Round a Decimal value to the nearest cent (2 decimal places).
    
    Args:
        value: Decimal value to round
        
    Returns:
        Decimal rounded to 2 decimal places
    """
    return value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

def validate_upkeep_constants():
    """
    Validate that all upkeep constants are correctly calculated from daily values.
    
    This function can be used to verify that the per-turn values match the 
    daily values divided by 12 (since there are 12 turns per day).
    """
    daily_to_turn_conversions = {
        # Power plants (daily cost -> exact per turn cost)
        "coal_power": (1200, Decimal("100.00")),
        "oil_power": (1800, Decimal("150.00")),
        "nuclear_power": (10500, Decimal("875.00")),
        "wind_power": (500, Decimal("41.67")),
        
        # Civil improvements
        "police_station": (750, Decimal("62.50")),
        "hospital": (1000, Decimal("83.33")),
        "recycling_center": (2500, Decimal("208.33")),
        "subway": (3250, Decimal("270.83")),
        "supermarket": (600, Decimal("50.00")),
        "bank": (1800, Decimal("150.00")),
        "shopping_mall": (5400, Decimal("450.00")),
        "stadium": (12150, Decimal("1012.50")),
        
        # Resource production
        "coal_mine": (400, Decimal("33.33")),
        "oil_well": (600, Decimal("50.00")),
        "lead_mine": (1500, Decimal("125.00")),
        "iron_mine": (1600, Decimal("133.33")),
        "bauxite_mine": (1600, Decimal("133.33")),
        "uranium_mine": (5000, Decimal("416.67")),
        "farm": (300, Decimal("25.00")),
        "oil_refinery": (4000, Decimal("333.33")),
        "steel_mill": (4000, Decimal("333.33")),
        "aluminum_refinery": (2500, Decimal("208.33")),
        "munitions_factory": (3500, Decimal("291.67")),
    }
    
    print("Validating upkeep constant conversions (exact decimal values):")
    print("=" * 70)
    
    for improvement, (daily_cost, expected_turn_cost) in daily_to_turn_conversions.items():
        calculated_turn_cost = Decimal(str(daily_cost)) / Decimal("12")
        calculated_rounded = round_to_cents(calculated_turn_cost)
        
        if abs(calculated_rounded - expected_turn_cost) < Decimal("0.01"):
            status = "✅ CORRECT"
        else:
            status = f"❌ ERROR (calculated {calculated_rounded})"
        
        print(f"{improvement:20} | ${daily_cost:5}/day -> ${expected_turn_cost:7}/turn | {status}")
    
    print("=" * 70)
    
    # Show total for sample calculation
    print("\nSample calculation with 1 of each improvement:")
    total_power = sum(POWER_UPKEEP_TURN.values())
    total_civil = sum(CIVIL_UPKEEP_TURN.values())
    total_resource = sum(RESOURCE_UPKEEP_TURN.values())
    total_all = total_power + total_civil + total_resource
    
    print(f"Power Plants:       ${total_power:8.2f}/turn")
    print(f"Civil Improvements: ${total_civil:8.2f}/turn")
    print(f"Resource Production: ${total_resource:8.2f}/turn")
    print(f"Total Upkeep:       ${total_all:8.2f}/turn")

if __name__ == "__main__":
    validate_upkeep_constants()