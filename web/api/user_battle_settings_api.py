"""
User Battle Settings API
=======================

API endpoints for managing user battle settings and formulas.
Handles both single-player settings and PvP/Boss room configurations.
"""

from fastapi import APIRouter, HTTPException, Request, Body
from fastapi.responses import JSONResponse
from Systems.Pets.Logic.user_battle_settings import (
    UserBattleSettings, BattleFormula, PvPBattleSettings
)
from Systems.Functions.user_data_manager import user_data_manager
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/battle/settings/my")
async def get_my_battle_settings(request: Request):
    """Get current user's battle settings."""
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    user_id = str(user.get("id"))
    
    try:
        settings = UserBattleSettings.get_user_settings(user_id)
        return JSONResponse(content={
            "success": True,
            "settings": settings
        })
    except Exception as e:
        logger.error(f"Error getting battle settings for {user_id}: {e}")
        return JSONResponse(content={
            "success": False,
            "error": "Failed to get battle settings"
        }, status_code=500)


@router.post("/battle/settings/save")
async def save_battle_settings(request: Request, settings_data: Dict[str, Any] = Body(...)):
    """Save user's battle settings."""
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    user_id = str(user.get("id"))
    
    try:
        # Validate the formula if provided
        if 'formula' in settings_data:
            is_valid, error_msg = UserBattleSettings.validate_formula(settings_data['formula'])
            if not is_valid:
                return JSONResponse(content={
                    "success": False,
                    "error": f"Invalid formula: {error_msg}"
                }, status_code=400)
        
        # Save settings
        success = UserBattleSettings.save_user_settings(user_id, settings_data)
        
        if success:
            return JSONResponse(content={
                "success": True,
                "message": "Battle settings saved successfully"
            })
        else:
            return JSONResponse(content={
                "success": False,
                "error": "Failed to save battle settings"
            }, status_code=500)
            
    except Exception as e:
        logger.error(f"Error saving battle settings for {user_id}: {e}")
        return JSONResponse(content={
            "success": False,
            "error": "Failed to save battle settings"
        }, status_code=500)


@router.get("/battle/settings/presets")
async def get_preset_formulas():
    """Get all available preset formulas."""
    try:
        presets = UserBattleSettings.get_preset_formulas()
        preset_data = {}
        
        for name, formula in presets.items():
            from dataclasses import asdict
            preset_data[name] = asdict(formula)
        
        return JSONResponse(content={
            "success": True,
            "presets": preset_data
        })
    except Exception as e:
        logger.error(f"Error getting preset formulas: {e}")
        return JSONResponse(content={
            "success": False,
            "error": "Failed to get preset formulas"
        }, status_code=500)


@router.post("/battle/settings/test")
async def test_battle_formula(request: Request, formula_data: Dict[str, Any] = Body(...)):
    """Test a battle formula with user's pet."""
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    user_id = str(user.get("id"))
    
    try:
        # Get user's pet
        user_data = user_data_manager.get_user_data(user_id)
        if not user_data or 'pet' not in user_data:
            return JSONResponse(content={
                "success": False,
                "error": "No pet found"
            }, status_code=404)
        
        pet_data = user_data['pet']
        
        # Validate formula
        is_valid, error_msg = UserBattleSettings.validate_formula(formula_data)
        if not is_valid:
            return JSONResponse(content={
                "success": False,
                "error": f"Invalid formula: {error_msg}"
            }, status_code=400)
        
        # Create formula object
        formula = BattleFormula(**formula_data)
        
        # Calculate stats with formula
        custom_health = UserBattleSettings.calculate_custom_health(pet_data, formula)
        custom_attack = UserBattleSettings.calculate_custom_attack(pet_data, formula)
        custom_defense = UserBattleSettings.calculate_custom_defense(pet_data, formula)
        
        # Get original stats for comparison
        from Systems.Pets.Logic.pet_brain import StatsCalculator
        original_stats = StatsCalculator.calculate_pet_stats(pet_data)
        
        return JSONResponse(content={
            "success": True,
            "test_results": {
                "original": {
                    "health": original_stats['max_health'],
                    "attack": original_stats['attack'],
                    "defense": original_stats['defense']
                },
                "custom": {
                    "health": custom_health,
                    "attack": custom_attack,
                    "defense": custom_defense
                },
                "pet_info": {
                    "name": pet_data.get('name', 'Unknown'),
                    "level": pet_data.get('level', 1),
                    "species": pet_data.get('species', 'Unknown')
                }
            }
        })
        
    except Exception as e:
        logger.error(f"Error testing battle formula for {user_id}: {e}")
        return JSONResponse(content={
            "success": False,
            "error": "Failed to test battle formula"
        }, status_code=500)


@router.post("/battle/settings/preset/{preset_name}")
async def load_preset_formula(request: Request, preset_name: str):
    """Load a preset formula for the user."""
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    user_id = str(user.get("id"))
    
    try:
        presets = UserBattleSettings.get_preset_formulas()
        if preset_name not in presets:
            return JSONResponse(content={
                "success": False,
                "error": f"Preset '{preset_name}' not found"
            }, status_code=404)
        
        # Get current settings
        settings = UserBattleSettings.get_user_settings(user_id)
        
        # Update with preset formula
        from dataclasses import asdict
        settings['formula'] = asdict(presets[preset_name])
        settings['active_preset'] = preset_name
        
        # Save settings
        success = UserBattleSettings.save_user_settings(user_id, settings)
        
        if success:
            return JSONResponse(content={
                "success": True,
                "message": f"Loaded preset '{preset_name}'",
                "formula": settings['formula']
            })
        else:
            return JSONResponse(content={
                "success": False,
                "error": "Failed to save preset"
            }, status_code=500)
            
    except Exception as e:
        logger.error(f"Error loading preset {preset_name} for {user_id}: {e}")
        return JSONResponse(content={
            "success": False,
            "error": "Failed to load preset"
        }, status_code=500)


# PvP/Boss Battle Room Settings

@router.post("/battle/room/{room_id}/settings")
async def create_room_battle_settings(request: Request, room_id: int, battle_type: str = "pvp"):
    """Create battle settings for a PvP/Boss room."""
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    user_id = str(user.get("id"))
    
    try:
        room_settings = PvPBattleSettings.create_room_settings(room_id, user_id, battle_type)
        
        if room_settings:
            return JSONResponse(content={
                "success": True,
                "room_settings": room_settings
            })
        else:
            return JSONResponse(content={
                "success": False,
                "error": "Failed to create room settings"
            }, status_code=500)
            
    except Exception as e:
        logger.error(f"Error creating room settings for {room_id}: {e}")
        return JSONResponse(content={
            "success": False,
            "error": "Failed to create room settings"
        }, status_code=500)


@router.get("/battle/room/{room_id}/settings")
async def get_room_battle_settings(room_id: int):
    """Get battle settings for a room."""
    try:
        room_settings = PvPBattleSettings.get_room_settings(room_id)
        
        if room_settings:
            return JSONResponse(content={
                "success": True,
                "room_settings": room_settings
            })
        else:
            return JSONResponse(content={
                "success": False,
                "error": "Room settings not found"
            }, status_code=404)
            
    except Exception as e:
        logger.error(f"Error getting room settings for {room_id}: {e}")
        return JSONResponse(content={
            "success": False,
            "error": "Failed to get room settings"
        }, status_code=500)


@router.post("/battle/room/{room_id}/accept")
async def accept_room_battle_settings(request: Request, room_id: int):
    """Accept the battle settings for a room."""
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    user_id = str(user.get("id"))
    
    try:
        success = PvPBattleSettings.add_participant_acceptance(room_id, user_id)
        
        if success:
            return JSONResponse(content={
                "success": True,
                "message": "Battle settings accepted"
            })
        else:
            return JSONResponse(content={
                "success": False,
                "error": "Failed to accept settings"
            }, status_code=500)
            
    except Exception as e:
        logger.error(f"Error accepting room settings for {room_id}: {e}")
        return JSONResponse(content={
            "success": False,
            "error": "Failed to accept settings"
        }, status_code=500)


@router.get("/battle/settings/available-stats")
async def get_available_stats():
    """Get list of available stats for formulas."""
    return JSONResponse(content={
        "success": True,
        "stats": UserBattleSettings.AVAILABLE_STATS,
        "descriptions": {
            "ATT": "Attack - Raw offensive power",
            "DEF": "Defense - Physical damage resistance", 
            "INT": "Intelligence - Magical abilities and strategy",
            "DEX": "Dexterity - Speed and accuracy",
            "HAP": "Happiness - Morale and luck factors",
            "ENE": "Energy - Stamina and endurance"
        }
    })


@router.post("/battle/settings/validate")
async def validate_formula(formula_data: Dict[str, Any] = Body(...)):
    """Validate a battle formula configuration."""
    try:
        is_valid, message = UserBattleSettings.validate_formula(formula_data)
        
        return JSONResponse(content={
            "success": True,
            "valid": is_valid,
            "message": message
        })
        
    except Exception as e:
        logger.error(f"Error validating formula: {e}")
        return JSONResponse(content={
            "success": False,
            "error": "Failed to validate formula"
        }, status_code=500)