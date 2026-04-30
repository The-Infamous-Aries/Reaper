"""
User Battle Settings System
==========================

Allows users to fully customize their battle formulas for single-player encounters
and configure PvP/Boss battle settings. Users can choose which stats to include,
set custom multipliers, and create their own battle experience.

Features:
- Custom health formulas (choose which stats to include)
- Custom attack/defense formulas
- Level/Equipment multiplier toggles
- Custom dividers and multipliers
- Stat averaging options
- Per-user settings storage
- PvP/Boss battle configuration
"""

from typing import Dict, Any, List, Optional, Union
import json
import logging
from dataclasses import dataclass, asdict
from Systems.Functions.user_data_manager import user_data_manager

logger = logging.getLogger(__name__)


@dataclass
class BattleFormula:
    """Represents a custom battle formula configuration."""
    
    # Health Formula Settings
    health_stats: List[str]  # Which stats to include: ['ATT', 'DEF', 'INT', 'DEX', 'HAP', 'ENE']
    health_use_average: bool  # Use average of selected stats vs sum
    health_multiplier: float  # Base multiplier (default 10)
    health_level_factor: bool  # Include level in calculation
    health_equipment_factor: bool  # Include equipment multiplier
    health_custom_multiplier: float  # Additional custom multiplier
    health_custom_divider: float  # Custom divider
    
    # Attack Formula Settings  
    attack_stats: List[str]  # Which stats to include for attack
    attack_use_average: bool  # Use average vs sum
    attack_multiplier: float  # Base multiplier
    attack_level_factor: bool  # Include level
    attack_equipment_factor: bool  # Include equipment
    attack_custom_multiplier: float  # Custom multiplier
    attack_custom_divider: float  # Custom divider
    
    # Defense Formula Settings
    defense_stats: List[str]  # Which stats to include for defense
    defense_use_average: bool  # Use average vs sum
    defense_multiplier: float  # Base multiplier
    defense_level_factor: bool  # Include level
    defense_equipment_factor: bool  # Include equipment
    defense_custom_multiplier: float  # Custom multiplier
    defense_custom_divider: float  # Custom divider
    
    # General Settings
    use_original_scaling: bool  # Fall back to original system
    formula_name: str  # User-defined name for this formula set
    
    @classmethod
    def get_default(cls) -> 'BattleFormula':
        """Get the default battle formula (matches original system)."""
        return cls(
            # Health: (HAP + ENE average + HAP*ENE) * 10
            health_stats=['HAP', 'ENE'],
            health_use_average=True,
            health_multiplier=10.0,
            health_level_factor=True,
            health_equipment_factor=True,
            health_custom_multiplier=1.0,
            health_custom_divider=1.0,
            
            # Attack: ATT + DEX
            attack_stats=['ATT', 'DEX'],
            attack_use_average=False,
            attack_multiplier=1.0,
            attack_level_factor=True,
            attack_equipment_factor=True,
            attack_custom_multiplier=1.0,
            attack_custom_divider=1.0,
            
            # Defense: DEF + INT
            defense_stats=['DEF', 'INT'],
            defense_use_average=False,
            defense_multiplier=1.0,
            defense_level_factor=True,
            defense_equipment_factor=True,
            defense_custom_multiplier=1.0,
            defense_custom_divider=1.0,
            
            use_original_scaling=False,
            formula_name="Default Formula"
        )
    
    @classmethod
    def get_balanced(cls) -> 'BattleFormula':
        """Get a balanced formula that uses all stats."""
        return cls(
            # Health: All stats average * 15
            health_stats=['ATT', 'DEF', 'INT', 'DEX', 'HAP', 'ENE'],
            health_use_average=True,
            health_multiplier=15.0,
            health_level_factor=True,
            health_equipment_factor=True,
            health_custom_multiplier=1.0,
            health_custom_divider=1.0,
            
            # Attack: All stats average
            attack_stats=['ATT', 'DEF', 'INT', 'DEX', 'HAP', 'ENE'],
            attack_use_average=True,
            attack_multiplier=1.0,
            attack_level_factor=True,
            attack_equipment_factor=True,
            attack_custom_multiplier=1.0,
            attack_custom_divider=1.0,
            
            # Defense: All stats average
            defense_stats=['ATT', 'DEF', 'INT', 'DEX', 'HAP', 'ENE'],
            defense_use_average=True,
            defense_multiplier=1.0,
            defense_level_factor=True,
            defense_equipment_factor=True,
            defense_custom_multiplier=1.0,
            defense_custom_divider=1.0,
            
            use_original_scaling=False,
            formula_name="Balanced All-Stats"
        )
    
    @classmethod
    def get_attack_focused(cls) -> 'BattleFormula':
        """Get an attack-focused formula."""
        return cls(
            # Health: HAP + ENE only
            health_stats=['HAP', 'ENE'],
            health_use_average=False,
            health_multiplier=8.0,
            health_level_factor=True,
            health_equipment_factor=True,
            health_custom_multiplier=1.0,
            health_custom_divider=1.0,
            
            # Attack: ATT + DEX + HAP (aggression)
            attack_stats=['ATT', 'DEX', 'HAP'],
            attack_use_average=False,
            attack_multiplier=1.2,
            attack_level_factor=True,
            attack_equipment_factor=True,
            attack_custom_multiplier=1.0,
            attack_custom_divider=1.0,
            
            # Defense: DEF + INT only
            defense_stats=['DEF', 'INT'],
            defense_use_average=False,
            defense_multiplier=0.8,
            defense_level_factor=True,
            defense_equipment_factor=True,
            defense_custom_multiplier=1.0,
            defense_custom_divider=1.0,
            
            use_original_scaling=False,
            formula_name="Attack Focused"
        )


class UserBattleSettings:
    """Manages user battle settings and formula calculations."""
    
    AVAILABLE_STATS = ['ATT', 'DEF', 'INT', 'DEX', 'HAP', 'ENE']
    
    @staticmethod
    def get_user_settings(user_id: str) -> Dict[str, Any]:
        """Get user's battle settings from database."""
        try:
            settings_data = user_data_manager.file_manager.get_data("user_battle_settings")
            if not settings_data:
                settings_data = {}
            
            user_settings = settings_data.get(user_id, {})
            
            # If no settings exist, create default
            if not user_settings:
                default_formula = BattleFormula.get_default()
                user_settings = {
                    'formula': asdict(default_formula),
                    'presets': {
                        'default': asdict(BattleFormula.get_default()),
                        'balanced': asdict(BattleFormula.get_balanced()),
                        'attack_focused': asdict(BattleFormula.get_attack_focused())
                    },
                    'active_preset': 'default'
                }
                UserBattleSettings.save_user_settings(user_id, user_settings)
            
            return user_settings
            
        except Exception as e:
            logger.error(f"Error loading user battle settings for {user_id}: {e}")
            # Return default settings on error
            default_formula = BattleFormula.get_default()
            return {
                'formula': asdict(default_formula),
                'presets': {'default': asdict(default_formula)},
                'active_preset': 'default'
            }
    
    @staticmethod
    def save_user_settings(user_id: str, settings: Dict[str, Any]) -> bool:
        """Save user's battle settings to database."""
        try:
            # Load existing settings data
            settings_data = user_data_manager.file_manager.get_data("user_battle_settings")
            if not settings_data:
                settings_data = {}
            
            # Update user's settings
            settings_data[user_id] = settings
            
            # Save back to database
            user_data_manager.file_manager.save_data("user_battle_settings", settings_data)
            return True
            
        except Exception as e:
            logger.error(f"Error saving user battle settings for {user_id}: {e}")
            return False
    
    @staticmethod
    def get_user_formula(user_id: str) -> BattleFormula:
        """Get user's active battle formula."""
        try:
            settings = UserBattleSettings.get_user_settings(user_id)
            formula_data = settings.get('formula', {})
            
            # Convert dict back to BattleFormula
            return BattleFormula(**formula_data)
            
        except Exception as e:
            logger.error(f"Error getting user formula for {user_id}: {e}")
            return BattleFormula.get_default()
    
    @staticmethod
    def calculate_custom_health(pet_data: Dict[str, Any], formula: BattleFormula) -> int:
        """Calculate health using user's custom formula."""
        try:
            if formula.use_original_scaling:
                # Fall back to original system
                from Systems.Pets.Logic.pet_brain import StatsCalculator
                return StatsCalculator.calculate_max_health(pet_data)
            
            # Get base stats (after equipment and mastery)
            from Systems.Pets.Logic.pet_brain import StatsCalculator
            computed_stats = StatsCalculator.calculate_pet_stats(pet_data)
            
            # Extract selected stats
            selected_values = []
            for stat in formula.health_stats:
                if stat in computed_stats:
                    selected_values.append(computed_stats[stat])
            
            if not selected_values:
                return 100  # Fallback
            
            # Calculate base value (sum or average)
            if formula.health_use_average:
                base_value = sum(selected_values) / len(selected_values)
            else:
                base_value = sum(selected_values)
            
            # Apply multipliers
            result = base_value * formula.health_multiplier
            
            # Apply level factor
            if formula.health_level_factor:
                level = int(pet_data.get('level', 1))
                level_mult = 1.0 + (level - 1) * 0.1  # 10% per level
                result *= level_mult
            
            # Apply equipment factor
            if formula.health_equipment_factor:
                equipment_mult = StatsCalculator.get_equipment_xp_multiplier(pet_data)
                result *= equipment_mult
            
            # Apply custom multiplier and divider
            result *= formula.health_custom_multiplier
            result /= formula.health_custom_divider
            
            return max(1, int(result))
            
        except Exception as e:
            logger.error(f"Error calculating custom health: {e}")
            return 100
    
    @staticmethod
    def calculate_custom_attack(pet_data: Dict[str, Any], formula: BattleFormula) -> int:
        """Calculate attack using user's custom formula."""
        try:
            if formula.use_original_scaling:
                # Fall back to original system
                from Systems.Pets.Logic.pet_brain import StatsCalculator
                computed_stats = StatsCalculator.calculate_pet_stats(pet_data)
                return computed_stats.get('attack', 10)
            
            # Get base stats (after equipment and mastery)
            from Systems.Pets.Logic.pet_brain import StatsCalculator
            computed_stats = StatsCalculator.calculate_pet_stats(pet_data)
            
            # Extract selected stats
            selected_values = []
            for stat in formula.attack_stats:
                if stat in computed_stats:
                    selected_values.append(computed_stats[stat])
            
            if not selected_values:
                return 10  # Fallback
            
            # Calculate base value (sum or average)
            if formula.attack_use_average:
                base_value = sum(selected_values) / len(selected_values)
            else:
                base_value = sum(selected_values)
            
            # Apply multipliers
            result = base_value * formula.attack_multiplier
            
            # Apply level factor
            if formula.attack_level_factor:
                level = int(pet_data.get('level', 1))
                level_mult = 1.0 + (level - 1) * 0.05  # 5% per level for attack
                result *= level_mult
            
            # Apply equipment factor
            if formula.attack_equipment_factor:
                equipment_mult = StatsCalculator.get_equipment_xp_multiplier(pet_data)
                result *= equipment_mult
            
            # Apply custom multiplier and divider
            result *= formula.attack_custom_multiplier
            result /= formula.attack_custom_divider
            
            return max(1, int(result))
            
        except Exception as e:
            logger.error(f"Error calculating custom attack: {e}")
            return 10
    
    @staticmethod
    def calculate_custom_defense(pet_data: Dict[str, Any], formula: BattleFormula) -> int:
        """Calculate defense using user's custom formula."""
        try:
            if formula.use_original_scaling:
                # Fall back to original system
                from Systems.Pets.Logic.pet_brain import StatsCalculator
                computed_stats = StatsCalculator.calculate_pet_stats(pet_data)
                return computed_stats.get('defense', 5)
            
            # Get base stats (after equipment and mastery)
            from Systems.Pets.Logic.pet_brain import StatsCalculator
            computed_stats = StatsCalculator.calculate_pet_stats(pet_data)
            
            # Extract selected stats
            selected_values = []
            for stat in formula.defense_stats:
                if stat in computed_stats:
                    selected_values.append(computed_stats[stat])
            
            if not selected_values:
                return 5  # Fallback
            
            # Calculate base value (sum or average)
            if formula.defense_use_average:
                base_value = sum(selected_values) / len(selected_values)
            else:
                base_value = sum(selected_values)
            
            # Apply multipliers
            result = base_value * formula.defense_multiplier
            
            # Apply level factor
            if formula.defense_level_factor:
                level = int(pet_data.get('level', 1))
                level_mult = 1.0 + (level - 1) * 0.05  # 5% per level for defense
                result *= level_mult
            
            # Apply equipment factor
            if formula.defense_equipment_factor:
                equipment_mult = StatsCalculator.get_equipment_xp_multiplier(pet_data)
                result *= equipment_mult
            
            # Apply custom multiplier and divider
            result *= formula.defense_custom_multiplier
            result /= formula.defense_custom_divider
            
            return max(1, int(result))
            
        except Exception as e:
            logger.error(f"Error calculating custom defense: {e}")
            return 5
    
    @staticmethod
    def apply_user_formula_to_pet(pet_data: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """Apply user's custom formula to a pet's stats."""
        try:
            formula = UserBattleSettings.get_user_formula(user_id)
            
            # Calculate custom stats
            custom_health = UserBattleSettings.calculate_custom_health(pet_data, formula)
            custom_attack = UserBattleSettings.calculate_custom_attack(pet_data, formula)
            custom_defense = UserBattleSettings.calculate_custom_defense(pet_data, formula)
            
            # Create modified pet data
            modified_pet = pet_data.copy()
            modified_pet['custom_max_health'] = custom_health
            modified_pet['custom_attack'] = custom_attack
            modified_pet['custom_defense'] = custom_defense
            modified_pet['using_custom_formula'] = True
            modified_pet['formula_name'] = formula.formula_name
            
            return modified_pet
            
        except Exception as e:
            logger.error(f"Error applying user formula to pet: {e}")
            return pet_data
    
    @staticmethod
    def get_preset_formulas() -> Dict[str, BattleFormula]:
        """Get all available preset formulas."""
        return {
            'default': BattleFormula.get_default(),
            'balanced': BattleFormula.get_balanced(),
            'attack_focused': BattleFormula.get_attack_focused()
        }
    
    @staticmethod
    def validate_formula(formula_data: Dict[str, Any]) -> tuple[bool, str]:
        """Validate a formula configuration."""
        try:
            # Check required fields
            required_fields = [
                'health_stats', 'health_multiplier', 'attack_stats', 'attack_multiplier',
                'defense_stats', 'defense_multiplier', 'formula_name'
            ]
            
            for field in required_fields:
                if field not in formula_data:
                    return False, f"Missing required field: {field}"
            
            # Validate stats lists
            for stat_field in ['health_stats', 'attack_stats', 'defense_stats']:
                stats = formula_data[stat_field]
                if not isinstance(stats, list) or not stats:
                    return False, f"{stat_field} must be a non-empty list"
                
                for stat in stats:
                    if stat not in UserBattleSettings.AVAILABLE_STATS:
                        return False, f"Invalid stat '{stat}' in {stat_field}"
            
            # Validate multipliers
            for mult_field in ['health_multiplier', 'attack_multiplier', 'defense_multiplier']:
                mult = formula_data[mult_field]
                if not isinstance(mult, (int, float)) or mult <= 0:
                    return False, f"{mult_field} must be a positive number"
            
            # Validate custom multipliers and dividers
            for field in ['health_custom_multiplier', 'attack_custom_multiplier', 'defense_custom_multiplier',
                         'health_custom_divider', 'attack_custom_divider', 'defense_custom_divider']:
                if field in formula_data:
                    val = formula_data[field]
                    if not isinstance(val, (int, float)) or val <= 0:
                        return False, f"{field} must be a positive number"
            
            return True, "Formula is valid"
            
        except Exception as e:
            return False, f"Validation error: {str(e)}"


class PvPBattleSettings:
    """Manages PvP and Boss battle settings for rooms."""
    
    @staticmethod
    def create_room_settings(room_id: int, creator_user_id: str, battle_type: str = "pvp") -> Dict[str, Any]:
        """Create battle settings for a PvP/Boss room."""
        try:
            creator_formula = UserBattleSettings.get_user_formula(creator_user_id)
            
            room_settings = {
                'room_id': room_id,
                'battle_type': battle_type,
                'creator_user_id': creator_user_id,
                'formula': asdict(creator_formula),
                'participants_accepted': [creator_user_id],  # Creator auto-accepts
                'created_at': int(time.time()),
                'description': f"Using '{creator_formula.formula_name}' battle formula"
            }
            
            # Save room settings
            PvPBattleSettings.save_room_settings(room_id, room_settings)
            return room_settings
            
        except Exception as e:
            logger.error(f"Error creating room settings: {e}")
            return {}
    
    @staticmethod
    def get_room_settings(room_id: int) -> Optional[Dict[str, Any]]:
        """Get battle settings for a room."""
        try:
            room_data = user_data_manager.file_manager.get_data("pvp_battle_settings")
            if not room_data:
                return None
            
            return room_data.get(str(room_id))
            
        except Exception as e:
            logger.error(f"Error getting room settings for {room_id}: {e}")
            return None
    
    @staticmethod
    def save_room_settings(room_id: int, settings: Dict[str, Any]) -> bool:
        """Save battle settings for a room."""
        try:
            room_data = user_data_manager.file_manager.get_data("pvp_battle_settings")
            if not room_data:
                room_data = {}
            
            room_data[str(room_id)] = settings
            user_data_manager.file_manager.save_data("pvp_battle_settings", room_data)
            return True
            
        except Exception as e:
            logger.error(f"Error saving room settings for {room_id}: {e}")
            return False
    
    @staticmethod
    def add_participant_acceptance(room_id: int, user_id: str) -> bool:
        """Mark a user as accepting the room's battle settings."""
        try:
            settings = PvPBattleSettings.get_room_settings(room_id)
            if not settings:
                return False
            
            if user_id not in settings['participants_accepted']:
                settings['participants_accepted'].append(user_id)
                return PvPBattleSettings.save_room_settings(room_id, settings)
            
            return True
            
        except Exception as e:
            logger.error(f"Error adding participant acceptance: {e}")
            return False
    
    @staticmethod
    def cleanup_old_rooms(max_age_hours: int = 24):
        """Clean up old room settings."""
        try:
            import time
            current_time = int(time.time())
            max_age_seconds = max_age_hours * 3600
            
            room_data = user_data_manager.file_manager.get_data("pvp_battle_settings")
            if not room_data:
                return
            
            # Remove old rooms
            rooms_to_remove = []
            for room_id, settings in room_data.items():
                created_at = settings.get('created_at', 0)
                if current_time - created_at > max_age_seconds:
                    rooms_to_remove.append(room_id)
            
            for room_id in rooms_to_remove:
                del room_data[room_id]
            
            if rooms_to_remove:
                user_data_manager.file_manager.save_data("pvp_battle_settings", room_data)
                logger.info(f"Cleaned up {len(rooms_to_remove)} old PvP room settings")
                
        except Exception as e:
            logger.error(f"Error cleaning up old rooms: {e}")


# Import time for room cleanup
import time