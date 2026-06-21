"""Activity tracking for subscription health monitoring."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


@dataclass
class SubscriptionHealth:
    """Health status for a single subscription."""
    name: str  # e.g., "nation/update"
    start_time: Optional[datetime] = None
    last_message_at: Optional[datetime] = None
    message_count: int = 0
    error_count: int = 0
    is_healthy: bool = True
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "message_count": self.message_count,
            "error_count": self.error_count,
            "is_healthy": self.is_healthy,
            "seconds_since_last_message": self.seconds_since_last_message(),
        }
    
    def seconds_since_last_message(self) -> Optional[float]:
        if not self.last_message_at:
            return None
        return (datetime.now(timezone.utc) - self.last_message_at).total_seconds()
    
    def record_message(self):
        self.last_message_at = datetime.now(timezone.utc)
        self.message_count += 1
        self.is_healthy = True
    
    def record_error(self):
        self.error_count += 1
        self.is_healthy = False


class ActivityTracker:
    """Tracks activity across multiple subscriptions."""
    
    def __init__(self, max_silence_seconds: float = 120.0):
        self.max_silence = max_silence_seconds
        self._subscriptions: Dict[str, SubscriptionHealth] = {}
        self._start_time = datetime.now(timezone.utc)
    
    def register_subscription(self, name: str) -> SubscriptionHealth:
        """Register a subscription for tracking."""
        health = SubscriptionHealth(name=name, start_time=datetime.now(timezone.utc))
        self._subscriptions[name] = health
        logger.info(f"ActivityTracker registered: {name}")
        return health
    
    def record_message(self, subscription_name: str):
        """Record a message received for a subscription."""
        if subscription_name not in self._subscriptions:
            self.register_subscription(subscription_name)
        self._subscriptions[subscription_name].record_message()
    
    def record_error(self, subscription_name: str):
        """Record an error for a subscription."""
        if subscription_name in self._subscriptions:
            self._subscriptions[subscription_name].record_error()
    
    def get_health(self, subscription_name: str) -> Optional[SubscriptionHealth]:
        """Get health for a specific subscription."""
        return self._subscriptions.get(subscription_name)
    
    def get_all_health(self) -> Dict[str, SubscriptionHealth]:
        """Get health for all subscriptions."""
        return dict(self._subscriptions)
    
    def is_healthy(self) -> bool:
        """Check if all subscriptions are healthy."""
        for health in self._subscriptions.values():
            if not health.is_healthy:
                return False
        return True
    
    def get_unhealthy_subscriptions(self) -> List[str]:
        """Get list of unhealthy subscription names.
        
        A subscription is considered unhealthy if:
        1. Its is_healthy flag is False (recorded error)
        2. It has received at least one message but has been silent for > max_silence
        3. It has never received a message and has been registered for > max_silence
        """
        unhealthy = []
        now = datetime.now(timezone.utc)
        logger.debug(f"get_unhealthy_subscriptions: checking {len(self._subscriptions)} subscriptions")
        for name, health in self._subscriptions.items():
            seconds = health.seconds_since_last_message()
            logger.debug(f"Subscription {name}: is_healthy={health.is_healthy}, seconds_since_last_message={seconds}")
            
            if not health.is_healthy:
                logger.debug(f"Subscription {name} unhealthy (is_healthy=False)")
                unhealthy.append(name)
            elif health.last_message_at and seconds is not None and seconds > self.max_silence:
                logger.debug(f"Subscription {name} unhealthy (silent {seconds:.0f}s > {self.max_silence}s)")
                unhealthy.append(name)
            elif health.last_message_at is None and health.start_time:
                elapsed = (now - health.start_time).total_seconds()
                if elapsed > self.max_silence:
                    logger.debug(f"Subscription {name} unhealthy (no messages after {elapsed:.0f}s)")
                    unhealthy.append(name)
        logger.debug(f"get_unhealthy_subscriptions: returning {unhealthy}")
        return unhealthy
    
    def get_oldest_last_message(self) -> Optional[datetime]:
        """Get the oldest last_message time across all subscriptions."""
        oldest = None
        for health in self._subscriptions.values():
            if health.last_message_at:
                if oldest is None or health.last_message_at < oldest:
                    oldest = health.last_message_at
        return oldest
    
    def to_dict(self) -> Dict:
        return {
            "start_time": self._start_time.isoformat(),
            "max_silence_seconds": self.max_silence,
            "subscriptions": {
                name: health.to_dict() 
                for name, health in self._subscriptions.items()
            },
            "overall_healthy": self.is_healthy(),
            "unhealthy_subscriptions": self.get_unhealthy_subscriptions(),
        }
