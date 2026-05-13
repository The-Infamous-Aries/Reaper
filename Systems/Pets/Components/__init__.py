"""
Pet System Components - Refactored using Component Pattern

This package contains the modular components for the pet system:
- StatsComponent: Handles stat calculations
- StateComponent: Manages pet state transitions
- AnimationComponent: Generates animation metadata
- EquipmentComponent: Manages equipment and bonuses
- InventoryComponent: Manages inventory operations
- PetEntity: Composes all components
"""

from .stats_component import StatsComponent
from .state_component import StateComponent
from .animation_component import AnimationComponent
from .equipment_component import EquipmentComponent
from .inventory_component import InventoryComponent
from .pet_entity import PetEntity

__all__ = [
    'StatsComponent',
    'StateComponent',
    'AnimationComponent',
    'EquipmentComponent',
    'InventoryComponent',
    'PetEntity',
]
