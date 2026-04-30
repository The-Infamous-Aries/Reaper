"""
Battle Scaling System for High-Level Pet Combat
===============================================

This module provides logarithmic scaling functions to keep battles balanced
and reasonably fast at all levels, including extreme levels like 500+.

The core principle: Instead of linear/exponential scaling that creates
millions of HP and damage, we use logarithmic curves that grow more slowly
at high levels while still rewarding progression.

Key Features:
- Battles stay under 20 turns at any level
- Damage scales meaningfully but not exponentially  
- Health pools remain manageable (under 50k even at level 1000+)
- Preserves the feel of progression without breaking combat speed
- Configurable scaling parameters
"""

import math
from typing import Dict, Any, Optional


class BattleScaler:
    """Handles all battle scaling calculations for high-level combat balance."""
    
    @staticmethod
    def _get_config():
        """Get battle configuration, with fallback to defaults."""
        try:
            from Systems.Pets.Logic.battle_config import BattleConfig
            return BattleConfig.get_config()
        except ImportError:
            # Fallback defaults if config system unavailable
            return {
                "health_log_factor": 2.0,
                "damage_log_factor": 1.8,
                "max_health_cap": 50000,
                "max_damage_cap": 15000
            }
    
    @staticmethod
    def calculate_scaled_health(base_stats: Dict[str, int], level: int = 1, 
                               equipment_multiplier: float = 1.0,
                               mastery_multipliers: Optional[Dict[str, float]] = None) -> int:
        """
        Calculate health using logarithmic scaling to prevent extreme values.
        
        Formula: base_health * log_scale_factor * equipment_factor
        Where log_scale_factor grows slowly: log(1 + level/100) + 1
        
        This keeps level 1 pets around 100-500 HP, level 100 around 1000-3000 HP,
        and level 500+ around 5000-15000 HP instead of millions.
        """
        config = BattleScaler._get_config()
        
        # Get base stats with mastery multipliers applied
        stats = base_stats.copy()
        if mastery_multipliers:
            for stat, multiplier in mastery_multipliers.items():
                if stat in stats:
                    stats[stat] = int(stats[stat] * multiplier)
        
        # Calculate base health using current formula
        hap = stats.get('HAP', 0)
        ene = stats.get('ENE', 0) 
        avg_stat = sum(stats.values()) / len(stats)
        
        base_health = (avg_stat + hap * ene) * 10  # Base multiplier
        
        # Apply logarithmic level scaling instead of linear
        health_log_factor = config.get("health_log_factor", 2.0)
        level_factor = math.log(1 + level / 100.0) * health_log_factor + 1.0
        
        # Apply equipment multiplier with diminishing returns
        equipment_factor = math.log(1 + equipment_multiplier) + 1.0
        
        scaled_health = int(base_health * level_factor * equipment_factor)
        
        # Cap at reasonable maximum
        max_health = config.get("max_health_cap", 50000)
        return min(scaled_health, max_health)
    
    @staticmethod
    def calculate_scaled_damage(base_damage: int, level: int = 1,
                               equipment_multiplier: float = 1.0,
                               charge_multiplier: float = 1.0) -> int:
        """
        Scale damage using logarithmic growth to prevent one-shot kills.
        
        Keeps damage meaningful but prevents the exponential growth that
        makes battles take forever or end in one hit.
        """
        config = BattleScaler._get_config()
        
        # Apply logarithmic level scaling
        damage_log_factor = config.get("damage_log_factor", 1.8)
        level_factor = math.log(1 + level / 150.0) * damage_log_factor + 1.0
        
        # Apply equipment multiplier with diminishing returns  
        equipment_factor = math.log(1 + equipment_multiplier * 0.5) + 1.0
        
        # Charge multiplier stays linear (it's a tactical choice)
        scaled_damage = int(base_damage * level_factor * equipment_factor * charge_multiplier)
        
        # Cap at reasonable maximum
        max_damage = config.get("max_damage_cap", 15000)
        return min(scaled_damage, max_damage)
    
    @staticmethod
    def get_battle_speed_multiplier(attacker_level: int, defender_level: int) -> float:
        """
        Return a multiplier to speed up battles between high-level pets.
        
        At very high levels, apply a speed multiplier to damage to ensure
        battles don't drag on forever even with scaled health pools.
        """
        config = BattleScaler._get_config()
        if not config.get("speed_multiplier_enabled", True):
            return 1.0
            
        avg_level = (attacker_level + defender_level) / 2.0
        
        if avg_level < 100:
            return 1.0
        elif avg_level < 300:
            return 1.2
        elif avg_level < 500:
            return 1.5
        else:
            return 2.0  # 2x damage at extreme levels for faster resolution
    
    @staticmethod
    def calculate_turn_estimate(attacker_health: int, defender_health: int,
                               attacker_damage: int, defender_damage: int) -> int:
        """
        Estimate how many turns a battle will take and suggest adjustments.
        
        Returns estimated turn count. If over 25 turns, the scaling system
        should apply additional speed multipliers.
        """
        if attacker_damage <= 0 or defender_damage <= 0:
            return 999  # Invalid battle state
        
        # Simple estimation: turns = max(health/damage) for both sides
        attacker_turns_to_kill = math.ceil(defender_health / attacker_damage)
        defender_turns_to_kill = math.ceil(attacker_health / defender_damage)
        
        # Battle ends when first pet dies
        estimated_turns = min(attacker_turns_to_kill, defender_turns_to_kill)
        
        return estimated_turns
    
    @staticmethod
    def apply_battle_balancing(attacker_stats: Dict[str, Any], 
                              defender_stats: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply complete battle balancing to two pets before combat.
        
        Returns adjusted stats that will result in balanced, fast battles
        regardless of the pets' actual levels.
        """
        config = BattleScaler._get_config()
        
        attacker_level = attacker_stats.get('level', 1)
        defender_level = defender_stats.get('level', 1)
        
        # Calculate speed multiplier for high-level battles
        speed_mult = BattleScaler.get_battle_speed_multiplier(attacker_level, defender_level)
        
        # Scale health using logarithmic formula
        attacker_health = BattleScaler.calculate_scaled_health(
            attacker_stats, attacker_level,
            attacker_stats.get('equipment_multiplier', 1.0),
            attacker_stats.get('mastery_multipliers', {})
        )
        
        defender_health = BattleScaler.calculate_scaled_health(
            defender_stats, defender_level, 
            defender_stats.get('equipment_multiplier', 1.0),
            defender_stats.get('mastery_multipliers', {})
        )
        
        # Scale base damage (before rolls and multipliers)
        attacker_base_damage = BattleScaler.calculate_scaled_damage(
            attacker_stats.get('attack', 10), attacker_level,
            attacker_stats.get('equipment_multiplier', 1.0)
        )
        
        defender_base_damage = BattleScaler.calculate_scaled_damage(
            defender_stats.get('attack', 10), defender_level,
            defender_stats.get('equipment_multiplier', 1.0)
        )
        
        # Apply speed multiplier for high-level battles
        attacker_base_damage = int(attacker_base_damage * speed_mult)
        defender_base_damage = int(defender_base_damage * speed_mult)
        
        # Estimate battle length and apply emergency scaling if needed
        estimated_turns = BattleScaler.calculate_turn_estimate(
            attacker_health, defender_health,
            attacker_base_damage * 10,  # Rough damage estimate with rolls
            defender_base_damage * 10
        )
        
        # If battle would still take too long, apply emergency scaling
        max_turns = config.get("max_battle_turns", 25)
        emergency_enabled = config.get("emergency_scaling_enabled", True)
        
        if emergency_enabled and estimated_turns > max_turns:
            emergency_mult = min(3.0, estimated_turns / 15.0)
            attacker_base_damage = int(attacker_base_damage * emergency_mult)
            defender_base_damage = int(defender_base_damage * emergency_mult)
        
        return {
            'attacker': {
                **attacker_stats,
                'scaled_health': attacker_health,
                'scaled_attack': attacker_base_damage,
                'scaling_applied': True
            },
            'defender': {
                **defender_stats,
                'scaled_health': defender_health,
                'scaled_attack': defender_base_damage,
                'scaling_applied': True
            },
            'battle_info': {
                'speed_multiplier': speed_mult,
                'estimated_turns': estimated_turns,
                'scaling_reason': f'Level {max(attacker_level, defender_level)} battle optimization'
            }
        }


def should_use_battle_scaling(pet1_level: int, pet2_level: int) -> bool:
    """
    Determine if battle scaling should be applied based on pet levels.
    
    Apply scaling for any battle involving pets above the configured threshold.
    """
    try:
        from Systems.Pets.Logic.battle_config import BattleConfig
        if not BattleConfig.is_scaling_enabled():
            return False
        threshold = BattleConfig.get_scaling_threshold()
    except ImportError:
        threshold = 50  # Default threshold
    
    return max(pet1_level, pet2_level) >= threshold


def get_scaling_explanation(level: int) -> str:
    """Return a user-friendly explanation of why scaling was applied."""
    try:
        from Systems.Pets.Logic.battle_config import BattleConfig
        if not BattleConfig.should_show_scaling_messages():
            return ""
    except ImportError:
        pass
    
    if level < 50:
        return ""
    elif level < 200:
        return "⚡ Battle optimized for mid-level combat"
    elif level < 500:
        return "⚡ Battle optimized for high-level combat" 
    else:
        return "⚡ Battle optimized for extreme-level combat"