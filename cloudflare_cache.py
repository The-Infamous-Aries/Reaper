"""
Cloudflare Cache Management Utility
Handles cache purging and management for the Reaper website
"""

import asyncio
import logging
import os
from typing import List, Optional, Dict, Any

import httpx
from Systems.Functions.config import CF_API_TOKEN, CF_ACCOUNT_ID

logger = logging.getLogger("Reaper.CloudflareCache")

class CloudflareCacheManager:
    """Manages Cloudflare cache operations"""
    
    def __init__(self):
        self.api_token = CF_API_TOKEN
        self.account_id = CF_ACCOUNT_ID
        self.base_url = "https://api.cloudflare.com/client/v4"
        self.zone_id = None  # Will be fetched dynamically
        
    async def get_zone_id(self, domain: str = "reaper.qzz.io") -> Optional[str]:
        """Get the zone ID for the domain"""
        if self.zone_id:
            return self.zone_id
            
        if not self.api_token:
            logger.error("CF_API_TOKEN not configured")
            return None
            
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/zones",
                    headers=headers,
                    params={"name": domain}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data["success"] and data["result"]:
                        self.zone_id = data["result"][0]["id"]
                        logger.info(f"Found zone ID for {domain}: {self.zone_id}")
                        return self.zone_id
                else:
                    logger.error(f"Failed to get zone ID: {response.status_code} - {response.text}")
                    
        except Exception as e:
            logger.error(f"Error getting zone ID: {e}")
            
        return None
    
    async def purge_all_cache(self) -> bool:
        """Purge all cache for the domain"""
        zone_id = await self.get_zone_id()
        if not zone_id:
            return False
            
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/zones/{zone_id}/purge_cache",
                    headers=headers,
                    json={"purge_everything": True}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data["success"]:
                        logger.info("Successfully purged all cache")
                        return True
                    else:
                        logger.error(f"Cache purge failed: {data.get('errors', [])}")
                else:
                    logger.error(f"Cache purge request failed: {response.status_code} - {response.text}")
                    
        except Exception as e:
            logger.error(f"Error purging cache: {e}")
            
        return False
    
    async def purge_files(self, files: List[str]) -> bool:
        """Purge specific files from cache"""
        zone_id = await self.get_zone_id()
        if not zone_id:
            return False
            
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/zones/{zone_id}/purge_cache",
                    headers=headers,
                    json={"files": files}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data["success"]:
                        logger.info(f"Successfully purged {len(files)} files from cache")
                        return True
                    else:
                        logger.error(f"File cache purge failed: {data.get('errors', [])}")
                else:
                    logger.error(f"File cache purge request failed: {response.status_code} - {response.text}")
                    
        except Exception as e:
            logger.error(f"Error purging files from cache: {e}")
            
        return False
    
    async def purge_by_tags(self, tags: List[str]) -> bool:
        """Purge cache by tags"""
        zone_id = await self.get_zone_id()
        if not zone_id:
            return False
            
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/zones/{zone_id}/purge_cache",
                    headers=headers,
                    json={"tags": tags}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data["success"]:
                        logger.info(f"Successfully purged cache for tags: {tags}")
                        return True
                    else:
                        logger.error(f"Tag cache purge failed: {data.get('errors', [])}")
                else:
                    logger.error(f"Tag cache purge request failed: {response.status_code} - {response.text}")
                    
        except Exception as e:
            logger.error(f"Error purging cache by tags: {e}")
            
        return False
    
    async def purge_dashboard_assets(self) -> bool:
        """Purge common dashboard assets that cause issues"""
        files = [
            "https://reaper.qzz.io/css/dashboard.css",
            "https://reaper.qzz.io/css/main.css",
            "https://reaper.qzz.io/css/bootstrap.min.css",
            "https://reaper.qzz.io/js/dashboard.js",
            "https://reaper.qzz.io/js/page_loader.js",
            "https://reaper.qzz.io/js/cache-buster.js",
            "https://reaper.qzz.io/dashboard.html",
            "https://reaper.qzz.io/"
        ]
        
        return await self.purge_files(files)
    
    async def set_development_mode(self, enabled: bool) -> bool:
        """Enable or disable development mode"""
        zone_id = await self.get_zone_id()
        if not zone_id:
            return False
            
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.patch(
                    f"{self.base_url}/zones/{zone_id}/settings/development_mode",
                    headers=headers,
                    json={"value": "on" if enabled else "off"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data["success"]:
                        mode = "enabled" if enabled else "disabled"
                        logger.info(f"Development mode {mode}")
                        return True
                    else:
                        logger.error(f"Development mode change failed: {data.get('errors', [])}")
                else:
                    logger.error(f"Development mode request failed: {response.status_code} - {response.text}")
                    
        except Exception as e:
            logger.error(f"Error changing development mode: {e}")
            
        return False

# Global instance
cache_manager = CloudflareCacheManager()

# Convenience functions
async def purge_all_cache() -> bool:
    """Purge all Cloudflare cache"""
    return await cache_manager.purge_all_cache()

async def purge_dashboard_cache() -> bool:
    """Purge dashboard-specific cache"""
    return await cache_manager.purge_dashboard_assets()

async def enable_development_mode() -> bool:
    """Enable Cloudflare development mode"""
    return await cache_manager.set_development_mode(True)

async def disable_development_mode() -> bool:
    """Disable Cloudflare development mode"""
    return await cache_manager.set_development_mode(False)