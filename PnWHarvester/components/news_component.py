"""
NewsComponent - Encapsulates news event generation and writing.

The NewsComponent provides async methods for recording various types of news events
to all three news databases (weekly, monthly, yearly) simultaneously.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class NewsComponent:
    """
    Component for managing news event generation and writing.
    
    Wraps NewsDB functionality and provides a clean async interface
    for recording news events from subscriptions.
    """
    
    def __init__(self, news_db, global_nations_db=None):
        """
        Args:
            news_db: NewsDB instance (manages weekly, monthly, yearly DBs)
            global_nations_db: GlobalNationsDB instance for enrichment (optional)
        """
        self.news_db = news_db
        self.global_nations_db = global_nations_db
    
    async def initialize(self):
        """Initialize the component."""
        logger.info("NewsComponent initialized")
    
    async def record_event(
        self,
        event_type: str,
        nation_id: Optional[int] = None,
        nation_name: Optional[str] = None,
        nation_flag: Optional[str] = None,
        alliance_id: Optional[int] = None,
        alliance_name: Optional[str] = None,
        alliance_flag: Optional[str] = None,
        value: float = 0,
        value2: float = 0,
        headline: str = "",
        detail: Optional[Dict[str, Any]] = None,
        event_date: Optional[str] = None,
        alliance_delta: Optional[Dict[str, Any]] = None,
        nation_delta: Optional[Dict[str, Any]] = None,
        sec_nation_id: Optional[int] = None,
        sec_nation_name: Optional[str] = None,
        sec_alliance_id: Optional[int] = None,
        sec_alliance_name: Optional[str] = None,
        sec_alliance_delta: Optional[Dict[str, Any]] = None,
        sec_nation_delta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Record a news event to all three news DBs.
        
        Delegates to NewsDB.record_event which handles writing to
        weekly, monthly, and yearly DBs simultaneously.
        """
        if detail is None:
            detail = {}
        
        if event_date is None:
            from datetime import datetime, timezone
            event_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        
        await self.news_db.record_event(
            event_type=event_type,
            nation_id=nation_id,
            nation_name=nation_name,
            nation_flag=nation_flag,
            alliance_id=alliance_id,
            alliance_name=alliance_name,
            alliance_flag=alliance_flag,
            value=value,
            value2=value2,
            headline=headline,
            detail=detail,
            event_date=event_date,
            alliance_delta=alliance_delta,
            nation_delta=nation_delta,
            sec_nation_id=sec_nation_id,
            sec_nation_name=sec_nation_name,
            sec_alliance_id=sec_alliance_id,
            sec_alliance_name=sec_alliance_name,
            sec_alliance_delta=sec_alliance_delta,
            sec_nation_delta=sec_nation_delta,
        )
    
    async def update_stats_only(
        self,
        nation_id: Optional[int] = None,
        nation_name: Optional[str] = None,
        nation_flag: Optional[str] = None,
        alliance_id: Optional[int] = None,
        alliance_name: Optional[str] = None,
        alliance_flag: Optional[str] = None,
        alliance_delta: Optional[Dict[str, Any]] = None,
        nation_delta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Update stats without recording an event.
        
        Useful for bulk updates where you want to increment counters
        without creating event rows.
        """
        await self.news_db.update_stats_only(
            nation_id=nation_id,
            nation_name=nation_name,
            nation_flag=nation_flag,
            alliance_id=alliance_id,
            alliance_name=alliance_name,
            alliance_flag=alliance_flag,
            alliance_delta=alliance_delta,
            nation_delta=nation_delta,
        )
    
    async def get_component_stats(self) -> Dict[str, Any]:
        """Return component statistics."""
        return {
            "component": "NewsComponent",
            "news_db_initialized": self.news_db is not None,
        }
