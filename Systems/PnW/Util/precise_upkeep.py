"""
Precise upkeep calculations using Decimal for penny-accurate results.

This module provides functions to calculate improvement upkeep costs
with exact decimal precision, ensuring accurate calculations down to the penny.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any
from correct_upkeep_constants import (
    POWER_UPKEEP_TURN,
    CIVIL_UPKEEP_TURN, 
    RESOURCE_UPKEEP_TURN,
    MILITARY_UPKEEP_TURN,
    get_improvement_upkeep_per_turn,
    round_to_cents
)

def calculate_precise_civil_upkeep(city: Dict[str, Any]) -> Decimal:
    """
    Calculate precise civil improvement upkeep for a city using exact decimal values.
    
    Args:
        city: City data dictionary with improvement counts
        
    Returns:
        Total civil improvement upkeep per turn as Decimal
    """
    total_upkeep = Decimal("0.00")
    
    # Civil improvements
    civil_improvements = [
        'police_station', 'hospital', 'recycling_center', 'subway',
        'supermarket', 'bank', 'shopping_mall', 'stadium'
    ]
    
    for improvement in civil_improvements:
        count = city.get(improvement, 0)
        if count > 0:
            upkeep = get_improvement_upkeep_per_turn(improvement, count)
            total_upkeep += upkeep
    
    return total_upkeep

def calculate_precise_power_upkeep(city: Dict[str, Any]) -> Decimal:
    """
    Calculate precise power plant upkeep for a city using exact decimal values.
    
    Args:
        city: City data dictionary with power plant counts
        
    Returns:
        Total power plant upkeep per turn as Decimal
    """
    total_upkeep = Decimal("0.00")
    
    # Power plants
    power_plants = ['coal_power', 'oil_power', 'nuclear_power', 'wind_power']
    
    for power_plant in power_plants:
        count = city.get(power_plant, 0)
        if count > 0:
            upkeep = get_improvement_upkeep_per_turn(power_plant, count)
            total_upkeep += upkeep
    
    return total_upkeep

def calculate_precise_resource_upkeep(city: Dict[str, Any], modifiers: Dict[str, float] = None) -> Decimal:
    """
    Calculate precise resource production upkeep for a city using exact decimal values.
    
    Args:
        city: City data dictionary with resource improvement counts
        modifiers: Optional modifiers dictionary (for future use)
        
    Returns:
        Total resource production upkeep per turn as Decimal
    """
    total_upkeep = Decimal("0.00")
    
    if modifiers is None:
        modifiers = {'rss_upkeep_mod': 1.0}
    
    # Resource production improvements
    resource_improvements = [
        'coal_mine', 'oil_well', 'lead_mine', 'iron_mine', 'bauxite_mine', 
        'uranium_mine', 'farm', 'oil_refinery', 'steel_mill', 
        'aluminum_refinery', 'munitions_factory'
    ]
    
    rss_upkeep_modifier = Decimal(str(modifiers.get('rss_upkeep_mod', 1.0)))
    
    for improvement in resource_improvements:
        count = city.get(improvement, 0)
        if count > 0:
            base_upkeep = get_improvement_upkeep_per_turn(improvement, count)
            modified_upkeep = base_upkeep * rss_upkeep_modifier
            total_upkeep += modified_upkeep
    
    return total_upkeep

def calculate_precise_military_upkeep(city: Dict[str, Any]) -> Decimal:
    """
    Calculate precise military building upkeep for a city using exact decimal values.
    
    Args:
        city: City data dictionary with military building counts
        
    Returns:
        Total military building upkeep per turn as Decimal (should be 0.00)
    """
    total_upkeep = Decimal("0.00")
    
    # Military buildings (all have $0 upkeep)
    military_buildings = ['barracks', 'hangar', 'drydock', 'factory']
    
    for building in military_buildings:
        count = city.get(building, 0)
        if count > 0:
            upkeep = get_improvement_upkeep_per_turn(building, count)
            total_upkeep += upkeep
    
    return total_upkeep

def calculate_total_precise_upkeep(city: Dict[str, Any], modifiers: Dict[str, float] = None) -> Dict[str, Decimal]:
    """
    Calculate all upkeep costs for a city with precise decimal values.
    
    Args:
        city: City data dictionary
        modifiers: Optional modifiers dictionary
        
    Returns:
        Dictionary with precise upkeep costs by category
    """
    civil_upkeep = calculate_precise_civil_upkeep(city)
    power_upkeep = calculate_precise_power_upkeep(city)
    resource_upkeep = calculate_precise_resource_upkeep(city, modifiers)
    military_upkeep = calculate_precise_military_upkeep(city)
    
    # Total improvement upkeep (civil + military buildings, excluding power and resource)
    improvement_upkeep = civil_upkeep + military_upkeep
    
    return {
        'civil_upkeep': civil_upkeep,
        'power_upkeep': power_upkeep,
        'resource_upkeep': resource_upkeep,
        'military_upkeep': military_upkeep,
        'improvement_upkeep': improvement_upkeep,
        'total_upkeep': civil_upkeep + power_upkeep + resource_upkeep + military_upkeep
    }

def format_currency_precise(amount: Decimal, show_cents: bool = True) -> str:
    """
    Format a Decimal amount as currency with optional cent precision.
    
    Args:
        amount: Decimal amount to format
        show_cents: Whether to show cents (default True)
        
    Returns:
        Formatted currency string
    """
    if show_cents:
        return f"${amount:,.2f}"
    else:
        # Round to nearest dollar for display
        rounded = round_to_cents(amount).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        return f"${rounded:,}"

def convert_decimal_to_float(decimal_dict: Dict[str, Decimal]) -> Dict[str, float]:
    """
    Convert a dictionary of Decimal values to float for compatibility.
    
    Args:
        decimal_dict: Dictionary with Decimal values
        
    Returns:
        Dictionary with float values
    """
    return {key: float(value) for key, value in decimal_dict.items()}

# Example usage and testing
if __name__ == "__main__":
    # Test with sample city data
    test_city = {
        'coal_power': 1,
        'oil_power': 1,
        'nuclear_power': 1,
        'wind_power': 1,
        'police_station': 1,
        'hospital': 1,
        'recycling_center': 1,
        'subway': 1,
        'supermarket': 1,
        'bank': 1,
        'shopping_mall': 1,
        'stadium': 1,
        'coal_mine': 1,
        'oil_well': 1,
        'lead_mine': 1,
        'iron_mine': 1,
        'bauxite_mine': 1,
        'uranium_mine': 1,
        'farm': 1,
        'oil_refinery': 1,
        'steel_mill': 1,
        'aluminum_refinery': 1,
        'munitions_factory': 1,
        'barracks': 1,
        'hangar': 1,
        'drydock': 1,
        'factory': 1,
    }
    
    upkeep_results = calculate_total_precise_upkeep(test_city)
    
    print("Precise Upkeep Calculation Test:")
    print("=" * 40)
    for category, amount in upkeep_results.items():
        print(f"{category:20}: {format_currency_precise(amount)}")
    
    print("\nDaily equivalents:")
    print("-" * 40)
    for category, amount in upkeep_results.items():
        daily_amount = amount * Decimal("12")
        print(f"{category:20}: {format_currency_precise(daily_amount)} per day")