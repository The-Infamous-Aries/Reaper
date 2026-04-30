"""
Battle Configuration API
========================

Provides endpoints for configuring the battle scaling system.
Allows admins to adjust scaling parameters and users to view current settings.
"""

from fastapi import APIRouter, HTTPException, Request, Body
from fastapi.responses import JSONResponse
from Systems.Pets.Logic.battle_config import BattleConfig
from Systems.Pets.Logic.battle_scaling import BattleScaler, should_use_battle_scaling, get_scaling_explanation
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/battle/config")
async def get_battle_config(request: Request):
    """Get current battle scaling configuration."""
    try:
        config = BattleConfig.get_config()
        return JSONResponse(content={
            "success": True,
            "config": config,
            "scaling_active": config.get("scaling_enabled", True),
            "threshold": config.get("scaling_threshold", 50)
        })
    except Exception as e:
        logger.error(f"Error getting battle config: {e}")
        return JSONResponse(content={
            "success": False,
            "error": "Failed to get battle configuration"
        }, status_code=500)


@router.post("/battle/config")
async def update_battle_config(request: Request, config_data: Dict[str, Any] = Body(...)):
    """Update battle scaling configuration. Admin only."""
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # TODO: Add admin check here
    # For now, allow any authenticated user to modify config
    # In production, you'd want to check if user has admin permissions
    
    try:
        # Validate config data
        valid_keys = {
            "scaling_enabled", "scaling_threshold", "health_log_factor", 
            "damage_log_factor", "max_health_cap", "max_damage_cap",
            "speed_multiplier_enabled", "emergency_scaling_enabled",
            "max_battle_turns", "show_scaling_messages"
        }
        
        # Filter to only valid keys
        filtered_config = {k: v for k, v in config_data.items() if k in valid_keys}
        
        if not filtered_config:
            return JSONResponse(content={
                "success": False,
                "error": "No valid configuration keys provided"
            }, status_code=400)
        
        # Get current config and update with new values
        current_config = BattleConfig.get_config()
        current_config.update(filtered_config)
        
        # Save updated config
        success = BattleConfig.save_config(current_config)
        
        if success:
            return JSONResponse(content={
                "success": True,
                "message": "Battle configuration updated successfully",
                "config": current_config
            })
        else:
            return JSONResponse(content={
                "success": False,
                "error": "Failed to save configuration"
            }, status_code=500)
            
    except Exception as e:
        logger.error(f"Error updating battle config: {e}")
        return JSONResponse(content={
            "success": False,
            "error": "Failed to update battle configuration"
        }, status_code=500)


@router.post("/battle/config/reset")
async def reset_battle_config(request: Request):
    """Reset battle configuration to defaults. Admin only."""
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        success = BattleConfig.reset_to_defaults()
        
        if success:
            return JSONResponse(content={
                "success": True,
                "message": "Battle configuration reset to defaults",
                "config": BattleConfig.get_config()
            })
        else:
            return JSONResponse(content={
                "success": False,
                "error": "Failed to reset configuration"
            }, status_code=500)
            
    except Exception as e:
        logger.error(f"Error resetting battle config: {e}")
        return JSONResponse(content={
            "success": False,
            "error": "Failed to reset battle configuration"
        }, status_code=500)


@router.get("/battle/scaling/test")
async def test_battle_scaling(request: Request, level1: int = 500, level2: int = 500):
    """Test battle scaling calculations for given levels."""
    try:
        # Test if scaling would be applied
        scaling_enabled = should_use_battle_scaling(level1, level2)
        
        # Get scaling explanation
        explanation = get_scaling_explanation(max(level1, level2))
        
        # Calculate sample scaled values
        sample_stats = {
            'ATT': 100, 'DEF': 100, 'INT': 100, 
            'DEX': 100, 'HAP': 100, 'ENE': 100
        }
        
        # Test health scaling
        scaled_health_1 = BattleScaler.calculate_scaled_health(
            sample_stats, level1, 4.0, {'ATT': 2.0, 'DEF': 2.0, 'INT': 2.0, 'DEX': 2.0, 'HAP': 2.0, 'ENE': 2.0}
        )
        scaled_health_2 = BattleScaler.calculate_scaled_health(
            sample_stats, level2, 4.0, {'ATT': 2.0, 'DEF': 2.0, 'INT': 2.0, 'DEX': 2.0, 'HAP': 2.0, 'ENE': 2.0}
        )
        
        # Test damage scaling
        scaled_damage_1 = BattleScaler.calculate_scaled_damage(1000, level1, 4.0)
        scaled_damage_2 = BattleScaler.calculate_scaled_damage(1000, level2, 4.0)
        
        # Calculate original values for comparison
        original_health = (100 + 100 * 100) * 10 * 4.0 * 2.0  # Rough estimate
        original_damage = 1000 * 4.0 * 2.0  # Rough estimate
        
        # Get speed multiplier
        speed_mult = BattleScaler.get_battle_speed_multiplier(level1, level2)
        
        # Estimate battle turns
        estimated_turns = BattleScaler.calculate_turn_estimate(
            scaled_health_1, scaled_health_2,
            scaled_damage_1 * 10, scaled_damage_2 * 10  # Rough damage with rolls
        )
        
        return JSONResponse(content={
            "success": True,
            "scaling_enabled": scaling_enabled,
            "explanation": explanation,
            "levels": {"pet1": level1, "pet2": level2},
            "health": {
                "pet1_scaled": scaled_health_1,
                "pet2_scaled": scaled_health_2,
                "original_estimate": int(original_health)
            },
            "damage": {
                "pet1_scaled": scaled_damage_1,
                "pet2_scaled": scaled_damage_2,
                "original_estimate": int(original_damage)
            },
            "battle_info": {
                "speed_multiplier": speed_mult,
                "estimated_turns": estimated_turns
            },
            "config": BattleConfig.get_config()
        })
        
    except Exception as e:
        logger.error(f"Error testing battle scaling: {e}")
        return JSONResponse(content={
            "success": False,
            "error": "Failed to test battle scaling"
        }, status_code=500)