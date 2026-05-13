"""
AnimationComponent: Generates animation metadata (data, not rendering)
"""
from typing import Dict, Any
from enum import Enum


class AnimationType(Enum):
    """Animation types"""
    STAT_CHANGE = "stat_change"
    HEALTH_CHANGE = "health_change"
    LEVEL_UP = "level_up"
    LEVEL_DOWN = "level_down"
    ABILITY_LEARN = "ability_learn"
    ITEM_GAIN = "item_gain"
    BATTLE_ACTION = "battle_action"
    STATUS_EFFECT = "status_effect"


class AnimationComponent:
    """Generates animation metadata for frontend rendering"""
    
    # Default animation durations (milliseconds)
    DURATIONS = {
        AnimationType.STAT_CHANGE: 600,
        AnimationType.HEALTH_CHANGE: 400,
        AnimationType.LEVEL_UP: 1500,
        AnimationType.LEVEL_DOWN: 1000,
        AnimationType.ABILITY_LEARN: 1200,
        AnimationType.ITEM_GAIN: 800,
        AnimationType.BATTLE_ACTION: 300,
        AnimationType.STATUS_EFFECT: 500,
    }
    
    # Color schemes
    COLOR_MAP = {
        "ATT": "#FF4500",
        "DEF": "#4169E1",
        "INT": "#9932CC",
        "DEX": "#32CD32",
        "HAP": "#FF69B4",
        "ENE": "#FFD700",
        "success": "#00FF00",
        "failure": "#FF0000",
        "warning": "#FFA500",
    }
    
    @staticmethod
    def create_stat_animation(
        stat: str,
        old_value: int,
        new_value: int,
        success: bool,
        pet_type: str = "land",
        difficulty: str = "Average"
    ) -> Dict[str, Any]:
        """
        Create animation metadata for stat changes.
        
        Returns:
            Animation data for frontend to render
        """
        change = new_value - old_value
        color = AnimationComponent.COLOR_MAP.get("success" if success else "failure")
        
        return {
            "type": AnimationType.STAT_CHANGE.value,
            "stat": stat,
            "old_value": old_value,
            "new_value": new_value,
            "change": change,
            "success": success,
            "pet_type": pet_type,
            "difficulty": difficulty,
            "color": color,
            "duration_ms": AnimationComponent.DURATIONS[AnimationType.STAT_CHANGE],
            "easing": "ease-out",
            "show_number": True,
            "show_bar": True,
            "sound_effect": "success" if success else "failure",
        }
    
    @staticmethod
    def create_health_animation(
        old_health: int,
        new_health: int,
        max_health: int,
        is_damage: bool = True
    ) -> Dict[str, Any]:
        """Create animation metadata for health changes"""
        change = new_health - old_health
        damage_amount = abs(change)
        
        return {
            "type": AnimationType.HEALTH_CHANGE.value,
            "old_health": old_health,
            "new_health": new_health,
            "max_health": max_health,
            "change": change,
            "damage_amount": damage_amount,
            "is_damage": is_damage,
            "health_percentage": (new_health / max_health * 100) if max_health > 0 else 0,
            "color": "#FF0000" if is_damage else "#00FF00",
            "duration_ms": AnimationComponent.DURATIONS[AnimationType.HEALTH_CHANGE],
            "show_damage_number": True,
            "shake_intensity": min(3, damage_amount / 10),
        }
    
    @staticmethod
    def create_level_up_animation(
        old_level: int,
        new_level: int,
        levels_gained: int = 1,
        stat_gains: Dict[str, int] = None
    ) -> Dict[str, Any]:
        """Create animation metadata for level up"""
        if stat_gains is None:
            stat_gains = {}
        
        return {
            "type": AnimationType.LEVEL_UP.value,
            "old_level": old_level,
            "new_level": new_level,
            "levels_gained": levels_gained,
            "stat_gains": stat_gains,
            "duration_ms": AnimationComponent.DURATIONS[AnimationType.LEVEL_UP],
            "show_confetti": True,
            "show_level_popup": True,
            "show_stat_gains": True,
            "particle_color": "#FFD700",
            "sound_effect": "level_up",
            "easing": "ease-in-out",
        }
    
    @staticmethod
    def create_level_down_animation(
        old_level: int,
        new_level: int,
        levels_lost: int = 1,
        stat_losses: Dict[str, int] = None
    ) -> Dict[str, Any]:
        """Create animation metadata for level down"""
        if stat_losses is None:
            stat_losses = {}
        
        return {
            "type": AnimationType.LEVEL_DOWN.value,
            "old_level": old_level,
            "new_level": new_level,
            "levels_lost": levels_lost,
            "stat_losses": stat_losses,
            "duration_ms": AnimationComponent.DURATIONS[AnimationType.LEVEL_DOWN],
            "show_warning": True,
            "show_stat_losses": True,
            "particle_color": "#FF0000",
            "sound_effect": "level_down",
            "easing": "ease-in",
            "screen_flash": True,
        }
    
    @staticmethod
    def create_item_animation(
        item_name: str,
        item_type: str,
        count: int = 1,
        rarity: str = "Common"
    ) -> Dict[str, Any]:
        """Create animation metadata for item gain"""
        rarity_colors = {
            "Common": "#808080",
            "Uncommon": "#00FF00",
            "Rare": "#0000FF",
            "Epic": "#9932CC",
            "Mythic": "#FFD700",
        }
        
        color = rarity_colors.get(rarity, "#FFFFFF")
        
        return {
            "type": AnimationType.ITEM_GAIN.value,
            "item_name": item_name,
            "item_type": item_type,
            "count": count,
            "rarity": rarity,
            "color": color,
            "duration_ms": AnimationComponent.DURATIONS[AnimationType.ITEM_GAIN],
            "show_pop": True,
            "particle_color": color,
            "sound_effect": "item_gain",
            "easing": "ease-out",
        }
    
    @staticmethod
    def create_battle_action_animation(
        attacker_name: str,
        action_type: str,
        damage: int = 0,
        target_name: str = ""
    ) -> Dict[str, Any]:
        """Create animation metadata for battle actions"""
        action_colors = {
            "attack": "#FF4500",
            "defend": "#4169E1",
            "charge": "#FFD700",
            "heal": "#00FF00",
        }
        
        color = action_colors.get(action_type, "#FFFFFF")
        
        return {
            "type": AnimationType.BATTLE_ACTION.value,
            "attacker": attacker_name,
            "action": action_type,
            "damage": damage,
            "target": target_name,
            "color": color,
            "duration_ms": AnimationComponent.DURATIONS[AnimationType.BATTLE_ACTION],
            "show_damage_number": damage > 0,
            "sound_effect": action_type,
        }
    
    @staticmethod
    def create_batch_animation(animations: list) -> Dict[str, Any]:
        """
        Create a batch animation that plays multiple animations in sequence.
        
        Args:
            animations: List of animation dicts
        
        Returns:
            Batch animation metadata
        """
        total_duration = sum(
            anim.get("duration_ms", 0) for anim in animations
        )
        
        return {
            "type": "batch",
            "animations": animations,
            "total_duration_ms": total_duration,
            "sequential": True,
        }
