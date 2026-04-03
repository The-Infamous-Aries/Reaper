
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import json
import os
import logging

# Setup logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Project root to construct file paths
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

router = APIRouter()

@router.get("/pets-data")
async def get_pets_data():
    """Get comprehensive pets data from the Pets system."""
    try:
        pets_file_path = os.path.join(project_root, "Systems", "Pets", "Logic", "info.json")
        logger.info(f"Attempting to load pets data from: {pets_file_path}")
        
        with open(pets_file_path, "r", encoding="utf-8") as f:
            pets_data = json.load(f)
        
        logger.info("Successfully loaded and parsed pets data.")
        return JSONResponse(content=pets_data)
    except FileNotFoundError:
        logger.error(f"Pets info.json file not found at {pets_file_path}")
        raise HTTPException(status_code=404, detail="Pets data file not found")
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing pets JSON: {e}")
        raise HTTPException(status_code=500, detail="Error parsing pets data")
    except Exception as e:
        logger.error(f"An unexpected error occurred while fetching pets data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch pets data")

@router.get("/equipment-data")
async def get_equipment_data():
    """Get comprehensive equipment data from the Pets system."""
    try:
        equipment_file_path = os.path.join(project_root, "Systems", "Pets", "Logic", "equipment.json")
        logger.info(f"Attempting to load equipment data from: {equipment_file_path}")
        
        with open(equipment_file_path, "r", encoding="utf-8") as f:
            equipment_data = json.load(f)
            
        logger.info("Successfully loaded and parsed equipment data.")
        return JSONResponse(content=equipment_data)
    except FileNotFoundError:
        logger.error(f"Equipment equipment.json file not found at {equipment_file_path}")
        raise HTTPException(status_code=404, detail="Equipment data file not found")
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing equipment JSON: {e}")
        raise HTTPException(status_code=500, detail="Error parsing equipment data")
    except Exception as e:
        logger.error(f"An unexpected error occurred while fetching equipment data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch equipment data")
