"""
BeigeAlertComponent — GPP component for beige alert management.

Handles:
- Beige alert creation, updates, and deletion
- Early-exit notification queue management
- Alert expiry tracking

This component writes to beige_alerts_db.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BeigeAlertManager:
    """Manages beige alerts for nations."""
    
    def __init__(self):
        """Initialize the beige alert manager."""
        pass
    
    async def create_alert(
        self,
        user_id: str,
        nation_id: str,
        nation_name: str,
        beige_turns: int,
        projected_loot: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Create a new beige alert.
        
        Args:
            user_id: User ID (Discord ID)
            nation_id: Nation ID
            nation_name: Nation name
            beige_turns: Current beige turns
            projected_loot: Projected loot value
            
        Returns:
            Creation result
        """
        try:
            from Systems.Functions.beige_alerts_db import upsert_beige_alert
            await upsert_beige_alert(
                user_id=user_id,
                nation_id=nation_id,
                nation_name=nation_name,
                beige_turns=beige_turns,
                projected_loot=projected_loot,
            )
            return {"status": "created", "user_id": user_id, "nation_id": nation_id}
        except Exception as e:
            logger.error(f"Failed to create beige alert: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}
    
    async def update_alert(
        self,
        alert_id: int,
        beige_turns: int,
        projected_loot: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Update an existing beige alert.
        
        Args:
            alert_id: Alert ID
            beige_turns: New beige turns
            projected_loot: New projected loot
            
        Returns:
            Update result
        """
        try:
            from Systems.Functions.beige_alerts_db import update_beige_alert_turns_and_loot
            await update_beige_alert_turns_and_loot(alert_id, beige_turns, projected_loot)
            return {"status": "updated", "alert_id": alert_id}
        except Exception as e:
            logger.error(f"Failed to update beige alert: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}
    
    async def delete_alert(self, alert_id: int) -> Dict[str, Any]:
        """
        Delete a beige alert.
        
        Args:
            alert_id: Alert ID
            
        Returns:
            Deletion result
        """
        try:
            from Systems.Functions.beige_alerts_db import delete_beige_alert_by_id
            await delete_beige_alert_by_id(alert_id)
            return {"status": "deleted", "alert_id": alert_id}
        except Exception as e:
            logger.error(f"Failed to delete beige alert: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}
    
    async def get_alerts_for_nation(self, nation_id: int) -> List[Dict[str, Any]]:
        """
        Get all alerts for a nation.
        
        Args:
            nation_id: Nation ID
            
        Returns:
            List of alerts
        """
        try:
            from Systems.Functions.beige_alerts_db import get_beige_alerts_for_nation
            return await get_beige_alerts_for_nation(nation_id)
        except Exception as e:
            logger.error(f"Failed to get alerts for nation {nation_id}: {e}", exc_info=True)
            return []
    
    async def get_all_alerts(self) -> List[Dict[str, Any]]:
        """
        Get all beige alerts.
        
        Returns:
            List of all alerts
        """
        try:
            from Systems.Functions.beige_alerts_db import get_all_beige_alerts
            return await get_all_beige_alerts()
        except Exception as e:
            logger.error(f"Failed to get all alerts: {e}", exc_info=True)
            return []


class EarlyExitQueueManager:
    """Manages the early-exit notification queue."""
    
    def __init__(self):
        """Initialize the early-exit queue manager."""
        pass
    
    async def enqueue_early_exit(
        self,
        user_id: str,
        nation_id: str,
        nation_name: str,
        projected_loot: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Enqueue an early-exit notification.
        
        Args:
            user_id: User ID
            nation_id: Nation ID
            nation_name: Nation name
            projected_loot: Projected loot
            
        Returns:
            Enqueue result
        """
        try:
            from Systems.Functions.beige_alerts_db import enqueue_early_exit
            await enqueue_early_exit(
                user_id=user_id,
                nation_id=nation_id,
                nation_name=nation_name,
                projected_loot=projected_loot,
            )
            return {"status": "enqueued", "user_id": user_id, "nation_id": nation_id}
        except Exception as e:
            logger.error(f"Failed to enqueue early exit: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}
    
    async def drain_queue(self) -> List[Dict[str, Any]]:
        """
        Drain the early-exit queue.
        
        Returns:
            List of drained notifications
        """
        try:
            from Systems.Functions.beige_alerts_db import drain_early_exit_queue
            return await drain_early_exit_queue()
        except Exception as e:
            logger.error(f"Failed to drain early exit queue: {e}", exc_info=True)
            return []


class BeigeAlertComponent:
    """
    GPP component for beige alert management.
    
    Orchestrates the sub-components for beige alert operations.
    """
    
    def __init__(self):
        """Initialize the BeigeAlertComponent."""
        self.alert_manager = BeigeAlertManager()
        self.queue_manager = EarlyExitQueueManager()
    
    async def initialize(self):
        """Initialize the component."""
        logger.info("BeigeAlertComponent initialized")
    
    async def create_alert(
        self,
        user_id: str,
        nation_id: str,
        nation_name: str,
        beige_turns: int,
        projected_loot: float = 0.0,
    ) -> Dict[str, Any]:
        """Create a new beige alert."""
        return await self.alert_manager.create_alert(
            user_id, nation_id, nation_name, beige_turns, projected_loot
        )
    
    async def update_alert(
        self,
        alert_id: int,
        beige_turns: int,
        projected_loot: float = 0.0,
    ) -> Dict[str, Any]:
        """Update an existing beige alert."""
        return await self.alert_manager.update_alert(alert_id, beige_turns, projected_loot)
    
    async def delete_alert(self, alert_id: int) -> Dict[str, Any]:
        """Delete a beige alert."""
        return await self.alert_manager.delete_alert(alert_id)
    
    async def get_alerts_for_nation(self, nation_id: int) -> List[Dict[str, Any]]:
        """Get all alerts for a nation."""
        return await self.alert_manager.get_alerts_for_nation(nation_id)
    
    async def get_all_alerts(self) -> List[Dict[str, Any]]:
        """Get all beige alerts."""
        return await self.alert_manager.get_all_alerts()
    
    async def enqueue_early_exit(
        self,
        user_id: str,
        nation_id: str,
        nation_name: str,
        projected_loot: float = 0.0,
    ) -> Dict[str, Any]:
        """Enqueue an early-exit notification."""
        return await self.queue_manager.enqueue_early_exit(
            user_id, nation_id, nation_name, projected_loot
        )
    
    async def drain_queue(self) -> List[Dict[str, Any]]:
        """Drain the early-exit queue."""
        return await self.queue_manager.drain_queue()
    
    async def get_component_stats(self) -> Dict[str, Any]:
        """Get component statistics."""
        alerts = await self.get_all_alerts()
        return {
            "type": "BeigeAlertComponent",
            "total_alerts": len(alerts),
        }
