"""
Cache Management API
Provides endpoints for managing Cloudflare cache
"""

import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional

from Systems.Functions.cloudflare_cache import (
    cache_manager,
    purge_all_cache,
    purge_dashboard_cache,
    enable_development_mode,
    disable_development_mode
)

logger = logging.getLogger("Reaper.CacheAPI")

router = APIRouter()

class CachePurgeRequest(BaseModel):
    files: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    purge_all: bool = False

class DevelopmentModeRequest(BaseModel):
    enabled: bool

@router.post("/cache/purge")
async def purge_cache(request: CachePurgeRequest):
    """Purge Cloudflare cache"""
    try:
        if request.purge_all:
            success = await purge_all_cache()
            if success:
                return {"success": True, "message": "All cache purged successfully"}
            else:
                raise HTTPException(status_code=500, detail="Failed to purge all cache")
        
        elif request.files:
            success = await cache_manager.purge_files(request.files)
            if success:
                return {"success": True, "message": f"Purged {len(request.files)} files from cache"}
            else:
                raise HTTPException(status_code=500, detail="Failed to purge files from cache")
        
        elif request.tags:
            success = await cache_manager.purge_by_tags(request.tags)
            if success:
                return {"success": True, "message": f"Purged cache for tags: {request.tags}"}
            else:
                raise HTTPException(status_code=500, detail="Failed to purge cache by tags")
        
        else:
            raise HTTPException(status_code=400, detail="No purge method specified")
            
    except Exception as e:
        logger.error(f"Cache purge error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cache/purge-dashboard")
async def purge_dashboard_cache_endpoint():
    """Purge dashboard-specific cache"""
    try:
        success = await purge_dashboard_cache()
        if success:
            return {"success": True, "message": "Dashboard cache purged successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to purge dashboard cache")
    except Exception as e:
        logger.error(f"Dashboard cache purge error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cache/development-mode")
async def set_development_mode(request: DevelopmentModeRequest):
    """Enable or disable Cloudflare development mode"""
    try:
        if request.enabled:
            success = await enable_development_mode()
            message = "Development mode enabled"
        else:
            success = await disable_development_mode()
            message = "Development mode disabled"
        
        if success:
            return {"success": True, "message": message}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to change development mode")
            
    except Exception as e:
        logger.error(f"Development mode change error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cache/status")
async def get_cache_status():
    """Get cache status information"""
    try:
        zone_id = await cache_manager.get_zone_id()
        return {
            "success": True,
            "zone_id": zone_id,
            "api_configured": bool(cache_manager.api_token),
            "message": "Cache API is operational" if zone_id else "Cache API configuration incomplete"
        }
    except Exception as e:
        logger.error(f"Cache status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))