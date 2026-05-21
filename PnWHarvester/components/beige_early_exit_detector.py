"""
BeigeEarlyExitDetector — Detects when nations leave beige early.

Triggers when a tracked nation leaves beige before their alert expires.
Enqueues notifications in beige_early_exit_queue for the reaper to send.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class BeigeEarlyExitDetector:
    """
    Detects early beige exits from nation update events.
    
    When a nation leaves beige before their alert expires:
    1. Enqueues early-exit notification for each user with an alert
    2. Deletes the alert rows
    """
    
    def __init__(self, beige_component=None):
        """
        Initialize the beige early exit detector.
        
        Args:
            beige_component: BeigeAlertComponent instance (optional)
        """
        self.beige_component = beige_component
    
    async def check_early_exit(
        self,
        new_nation: Dict[str, Any],
        old_nation: Optional[Dict[str, Any]],
    ):
        """
        Check if a nation left beige early.
        
        Args:
            new_nation: New nation snapshot from event
            old_nation: Old nation snapshot from database (optional)
        """
        nation_id = int(new_nation.get("id") or 0)
        if not nation_id:
            return
        
        new_beige_turns = int(new_nation.get("beige_turns") or 0)
        new_color = str(new_nation.get("color") or "").lower()
        if "." in new_color:
            new_color = new_color.rsplit(".", 1)[-1]
        
        # Fast path: nation is still on beige
        if new_beige_turns > 0 or new_color == "beige":
            return
        
        # Need old snapshot to confirm they were on beige
        if old_nation is None:
            return
        old_beige_turns = int(old_nation.get("beige_turns") or 0)
        old_color = str(old_nation.get("color") or "").lower()
        if "." in old_color:
            old_color = old_color.rsplit(".", 1)[-1]
        
        was_on_beige = old_beige_turns > 0 or old_color == "beige"
        if not was_on_beige:
            return
        
        # Check for active alerts
        try:
            if self.beige_component:
                alerts = await self.beige_component.get_alerts_for_nation(nation_id)
            else:
                from Systems.Functions.beige_alerts_db import get_beige_alerts_for_nation
                alerts = await get_beige_alerts_for_nation(nation_id)
        except Exception as e:
            logger.warning(f"check_early_exit: DB read failed for nation {nation_id}: {e}")
            return
        
        if not alerts:
            return
        
        nation_name = new_nation.get("nation_name") or old_nation.get("nation_name") or f"nation {nation_id}"
        
        # Enqueue notifications and delete alerts
        for alert in alerts:
            stored_turns = int(alert.get("beige_turns") or 0)
            if stored_turns < 1:
                continue
            try:
                if self.beige_component:
                    await self.beige_component.enqueue_early_exit(
                        user_id=str(alert["user_id"]),
                        nation_id=str(nation_id),
                        nation_name=nation_name,
                        projected_loot=float(alert.get("projected_loot") or 0),
                    )
                else:
                    from Systems.Functions.beige_alerts_db import enqueue_early_exit
                    await enqueue_early_exit(
                        user_id=str(alert["user_id"]),
                        nation_id=str(nation_id),
                        nation_name=nation_name,
                        projected_loot=float(alert.get("projected_loot") or 0),
                    )
            except Exception as e:
                logger.warning(
                    f"check_early_exit: enqueue failed for user {alert['user_id']} "
                    f"nation {nation_id}: {e}"
                )
        
        # Remove all alert rows
        try:
            if self.beige_component:
                # Delete each alert individually
                for alert in alerts:
                    await self.beige_component.delete_alert(alert["id"])
                removed = len(alerts)
            else:
                from Systems.Functions.beige_alerts_db import delete_beige_alerts_for_nation
                removed = await delete_beige_alerts_for_nation(nation_id)
            logger.info(
                f"check_early_exit: {nation_name} (id={nation_id}) left beige early "
                f"(had {old_beige_turns} turns stored) — removed {removed} alert(s)"
            )
        except Exception as e:
            logger.warning(f"check_early_exit: delete failed for nation {nation_id}: {e}")
