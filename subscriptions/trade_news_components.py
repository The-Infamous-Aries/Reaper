"""
Trade News Generation Components

Handles generation of news events for trade-related activities.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

from PnWHarvester.db import news_writer as nw


def _obj_to_dict(obj: Any) -> Dict[str, Any]:
    """Convert objects to dictionaries safely."""
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return dict(obj)
    return vars(obj)


class TradeNewsGenerator:
    """Generates news events for trade-related activities."""
    
    def __init__(self, news_component=None):
        """
        Initialize the trade news generator.
        
        Args:
            news_component: NewsComponent instance (optional)
        """
        self.news_component = news_component
    
    async def generate_trade_completed_news(self, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate news for a completed trade.
        
        Callers pass only accepted marketplace transactions, not posted offers.
        """
        try:
            # Extract buyer and seller information
            # Trade can be either buying or selling from the perspective of the nation
            # We need to determine who is the buyer and who is the seller
            
            trade = _obj_to_dict(trade_data)
            
            # Determine trade direction
            is_buying = trade.get("buying", False)
            is_selling = trade.get("selling", False)
            
            # Extract nation data
            nation_obj = trade.get("nation") or {}
            if not isinstance(nation_obj, dict):
                nation_obj = {}
            
            # Extract alliance data from nation
            alliance_obj = nation_obj.get("alliance") or {}
            if isinstance(alliance_obj, dict):
                alliance_id = alliance_obj.get("id")
                alliance_name = alliance_obj.get("name")
                alliance_flag = alliance_obj.get("flag")
            else:
                alliance_id = None
                alliance_name = None
                alliance_flag = None
            
            # For buying trades: nation is the buyer, seller_nation is the seller
            # For selling trades: nation is the seller, buyer_nation is the buyer
            if is_buying:
                buyer_id = nation_obj.get("id")
                buyer_name = nation_obj.get("nation_name")
                buyer_flag = nation_obj.get("flag")
                buyer_alliance_id = alliance_id
                buyer_alliance_name = alliance_name
                buyer_alliance_flag = alliance_flag
                
                seller_obj = trade.get("seller_nation") or {}
                if isinstance(seller_obj, dict):
                    seller_id = seller_obj.get("id")
                    seller_name = seller_obj.get("nation_name")
                    seller_flag = seller_obj.get("flag")
                    seller_alliance_obj = seller_obj.get("alliance") or {}
                    if isinstance(seller_alliance_obj, dict):
                        seller_alliance_id = seller_alliance_obj.get("id")
                        seller_alliance_name = seller_alliance_obj.get("name")
                        seller_alliance_flag = seller_alliance_obj.get("flag")
                    else:
                        seller_alliance_id = None
                        seller_alliance_name = None
                        seller_alliance_flag = None
                else:
                    seller_id = None
                    seller_name = None
                    seller_flag = None
                    seller_alliance_id = None
                    seller_alliance_name = None
                    seller_alliance_flag = None
                    
            elif is_selling:
                seller_id = nation_obj.get("id")
                seller_name = nation_obj.get("nation_name")
                seller_flag = nation_obj.get("flag")
                seller_alliance_id = alliance_id
                seller_alliance_name = alliance_name
                seller_alliance_flag = alliance_flag
                
                buyer_obj = trade.get("buyer_nation") or {}
                if isinstance(buyer_obj, dict):
                    buyer_id = buyer_obj.get("id")
                    buyer_name = buyer_obj.get("nation_name")
                    buyer_flag = buyer_obj.get("flag")
                    buyer_alliance_obj = buyer_obj.get("alliance") or {}
                    if isinstance(buyer_alliance_obj, dict):
                        buyer_alliance_id = buyer_alliance_obj.get("id")
                        buyer_alliance_name = buyer_alliance_obj.get("name")
                        buyer_alliance_flag = buyer_alliance_obj.get("flag")
                    else:
                        buyer_alliance_id = None
                        buyer_alliance_name = None
                        buyer_alliance_flag = None
                else:
                    buyer_id = None
                    buyer_name = None
                    buyer_flag = None
                    buyer_alliance_id = None
                    buyer_alliance_name = None
                    buyer_alliance_flag = None
            else:
                # Cannot determine direction, skip
                logger.warning(f"Trade {trade.get('id')} has no buying/selling flag, skipping news generation")
                return {"status": "skipped", "reason": "no_direction", "generated": False}
            
            # Extract money and resources
            money_amount = float(trade.get("money") or 0)
            
            _RESOURCES = (
                "coal", "oil", "uranium", "iron", "bauxite", "lead",
                "gasoline", "munitions", "steel", "aluminum", "food",
            )
            resources_traded = {r: float(trade.get(r) or 0) for r in _RESOURCES}
            
            # Calculate price per unit (total money / total resources)
            total_resources = sum(resources_traded.values())
            price_per_unit = money_amount / total_resources if total_resources > 0 else 0
            
            # Get trade date
            trade_date = trade.get("accept_date") or trade.get("date")
            trade_date_str = str(trade_date).replace("+00:00", "").strip() if trade_date else None

            if not buyer_id or not seller_id:
                logger.warning(
                    "Trade %s missing buyer/seller ids, skipping news generation",
                    trade.get("id"),
                )
                return {
                    "status": "skipped",
                    "reason": "missing_buyer_seller_identity",
                    "generated": False,
                    "trade_id": trade.get("id"),
                    "buyer_id": buyer_id,
                    "seller_id": seller_id,
                }
            
            # Generate news
            recorded = await nw.record_trade_completed(
                buyer_id=int(buyer_id),
                buyer_name=buyer_name,
                buyer_flag=buyer_flag,
                buyer_alliance_id=int(buyer_alliance_id) if buyer_alliance_id else None,
                buyer_alliance_name=buyer_alliance_name,
                buyer_alliance_flag=buyer_alliance_flag,
                seller_id=int(seller_id),
                seller_name=seller_name,
                seller_flag=seller_flag,
                seller_alliance_id=int(seller_alliance_id) if seller_alliance_id else None,
                seller_alliance_name=seller_alliance_name,
                seller_alliance_flag=seller_alliance_flag,
                money_amount=money_amount,
                resources_traded=resources_traded,
                price_per_unit=price_per_unit,
                event_date=trade_date_str,
            )
            if not recorded:
                return {"status": "error", "reason": "record_event_failed", "generated": False}
            
            return {
                "status": "generated",
                "generated": True,
                "news_type": "trade_completed",
                "trade_id": trade.get("id"),
                "buyer_id": buyer_id,
                "seller_id": seller_id,
            }
            
        except Exception as e:
            logger.error(f"TradeNewsGenerator.generate_trade_completed_news: {e}", exc_info=True)
            return {"status": "error", "error": str(e), "generated": False}
