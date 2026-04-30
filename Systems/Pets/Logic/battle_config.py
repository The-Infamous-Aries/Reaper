"""
Battle Configuration System
===========================

Allows users and admins to configure battle scaling behavior.
Provides options to enable/disable scaling, adjust scaling parameters,
and set level thresholds for when scaling kicks in.
"""

import json
import os
from typing import Dict, Any, Optional
from Systems.Functions.user_data_manager import user_data_manager


class BattleConfig:
    """Manages battle scaling configuration settings."""
    
    DEFAULT_CONFIG = {
        "scaling_enabled": True,
        "scaling_threshold": 50,  # Level at which scaling starts
        "health_log_factor": 2.0,
        "damage_log_factor": 1.8,
        "max_health_cap": 50000,
        "max_damage_cap": 15000,
        "speed_multiplier_enabled": True,
        "emergency_scaling_enabled": True,
        "max_battle_turns": 25,
        "show_scaling_messages": True
    }
    
    @staticmethod
    def get_config() -> Dict[str, Any]:
        """Get current battle configuration, falling back to defaults."""
        try:
            config_data = user_data_manager.file_manager.get_data("battle_config")
            if config_data:
                # Merge with defaults to ensure all keys exist
                merged_config = BattleConfig.DEFAULT_CONFIG.copy()
                merged_config.update(config_data)
                return merged_config
        except Exception:
            pass
        
        return BattleConfig.DEFAULT_CONFIG.copy()
    
    @staticmethod
    def save_config(config: Dict[str, Any]) -> bool:
        """Save battle configuration."""
        try:
            user_data_manager.file_manager.save_data("battle_config", config)
            return True
        except Exception:
            return False
    
    @staticmethod
    def is_scaling_enabled() -> bool:
        """Check if battle scaling is enabled."""
        config = BattleConfig.get_config()
        return config.get("scaling_enabled", True)
    
    @staticmethod
    def get_scaling_threshold() -> int:
        """Get the level threshold for when scaling starts."""
        config = BattleConfig.get_config()
        return config.get("scaling_threshold", 50)
    
    @staticmethod
    def should_show_scaling_messages() -> bool:
        """Check if scaling messages should be shown to users."""
        config = BattleConfig.get_config()
        return config.get("show_scaling_messages", True)
    
    @staticmethod
    def get_scaling_factors() -> Dict[str, float]:
        """Get the scaling factors for health and damage."""
        config = BattleConfig.get_config()
        return {
            "health_log_factor": config.get("health_log_factor", 2.0),
            "damage_log_factor": config.get("damage_log_factor", 1.8)
        }
    
    @staticmethod
    def get_caps() -> Dict[str, int]:
        """Get the maximum caps for health and damage."""
        config = BattleConfig.get_config()
        return {
            "max_health": config.get("max_health_cap", 50000),
            "max_damage": config.get("max_damage_cap", 15000)
        }
    
    @staticmethod
    def reset_to_defaults() -> bool:
        """Reset configuration to default values."""
        return BattleConfig.save_config(BattleConfig.DEFAULT_CONFIG.copy())


def create_default_config_if_missing():
    """Create default battle config file if it doesn't exist."""
    try:
        existing_config = user_data_manager.file_manager.get_data("battle_config")
        if not existing_config:
            BattleConfig.save_config(BattleConfig.DEFAULT_CONFIG.copy())
    except Exception:
        # If there's any error, try to create the default config
        try:
            BattleConfig.save_config(BattleConfig.DEFAULT_CONFIG.copy())
        except Exception:
            pass  # Fail silently if we can't create config


# Auto-create config on import
create_default_config_if_missing()