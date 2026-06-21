"""
SpendingDetector — Detects and records spending from nation/city events.

Handles:
- City purchase detection
- Project purchase detection
- Military unit changes
- City upgrades (infra, land, improvements)

Deducts costs from HoldingsDB and generates news events.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class SpendingDetector:
    """Detects spending from nation and city snapshots."""
    
    def __init__(self, holdings_db):
        """
        Initialize the spending detector.
        
        Args:
            holdings_db: HoldingsDB instance
        """
        self.holdings_db = holdings_db
    
    @staticmethod
    def _now_str() -> str:
        """Get current UTC time as string."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    
    async def detect_city_purchase(
        self,
        nation_id: int,
        old_nation: Dict[str, Any],
        new_num_cities: int,
        event_date: Optional[str] = None,
    ):
        """
        Detect and deduct cost for a city purchase (called from city/create event).
        
        Args:
            nation_id: Nation ID
            old_nation: Nation data from DB before the purchase
            new_num_cities: City count after the purchase
            event_date: Event date string
        """
        if not self.holdings_db:
            return
        
        from PnWHarvester.db.pnw_costs import city_cost
        
        old_num_cities = int(old_nation.get("num_cities") or 0)
        cities_bought = new_num_cities - old_num_cities
        
        if cities_bought <= 0:
            return
        
        nation_name = old_nation.get("nation_name")
        ev_date = event_date or self._now_str()
        
        # Calculate cost for the new city
        total_city_cost = city_cost(old_num_cities, nation_data=old_nation)
        
        if total_city_cost > 0:
            await self.holdings_db.deduct_spending(
                nation_id=nation_id,
                cash_cost=total_city_cost,
                event_type="city_purchase",
                description=f"Bought {cities_bought} city/cities ({old_num_cities}→{new_num_cities})",
                event_date=ev_date,
                nation_name=nation_name,
                item_type="city",
                item_quantity=cities_bought,
                item_details=f"Cities {old_num_cities}→{new_num_cities}",
            )
            logger.info(
                f"Holdings: nation {nation_id} city purchase "
                f"${total_city_cost:,.0f} ({old_num_cities}→{new_num_cities} cities)"
            )
            # News: city purchase
            try:
                import PnWHarvester.db.news_writer as _nw
                await _nw.record_city_purchase(
                    nation_id=nation_id,
                    nation_name=nation_name,
                    nation_flag=old_nation.get("flag"),
                    alliance_id=int(old_nation.get("alliance_id") or 0) or None,
                    alliance_name=old_nation.get("alliance_name"),
                    alliance_flag=old_nation.get("alliance_flag"),
                    old_cities=old_num_cities,
                    new_cities=new_num_cities,
                    cash_cost=total_city_cost,
                    event_date=ev_date,
                )
            except Exception as _ne:
                logger.debug(f"news city_purchase: {_ne}")
    
    async def detect_nation_spending(
        self,
        nation_id: int,
        old_nation: Dict[str, Any],
        new_nation: Dict[str, Any],
        event_date: Optional[str] = None,
    ):
        """
        Compare old vs new nation snapshot to detect purchases.
        
        Deducts costs from holdings BEFORE the new snapshot is saved.
        
        Note: City purchases are detected in city/create events to avoid double-detection
        since city/create fires before nation/update and increments num_cities in the DB.
        """
        if not self.holdings_db:
            return
        
        from PnWHarvester.db.pnw_costs import (
            projects_purchased_cost, projects_purchased_resource_costs,
        )
        
        nation_name = new_nation.get("nation_name") or old_nation.get("nation_name")
        ev_date = event_date or self._now_str()
        
        # Skip city purchase detection here - handled in city/create events
        # to avoid double-detection since city/create increments num_cities
        # before nation/update fires.
        
        # Project purchase detection
        old_turns_proj = int(old_nation.get("turns_since_last_project") or 0)
        new_turns_proj = int(new_nation.get("turns_since_last_project") or 0)
        
        if old_turns_proj > 2 and new_turns_proj == 0:
            proj_cost = projects_purchased_cost(old_nation, new_nation)
            proj_rss = projects_purchased_resource_costs(old_nation, new_nation)
            if proj_cost > 0 or proj_rss:
                await self.holdings_db.deduct_spending(
                    nation_id=nation_id,
                    cash_cost=proj_cost,
                    event_type="project_purchase",
                    description=f"Project(s) purchased (turns_proj {old_turns_proj}→{new_turns_proj})",
                    event_date=ev_date,
                    nation_name=nation_name,
                    item_type="project",
                    item_quantity=1,
                    item_details="Project purchase detected",
                    resource_costs=proj_rss if proj_rss else None,
                )
                rss_str = ", ".join(f"{r}={v:,.1f}" for r, v in proj_rss.items()) if proj_rss else ""
                logger.info(
                    f"Holdings: nation {nation_id} project purchase ${proj_cost:,.0f}"
                    + (f" + {rss_str}" if rss_str else "")
                )
                # News: project purchase
                try:
                    import PnWHarvester.db.news_writer as _nw
                    proj_names = _nw._detect_projects_purchased(old_nation, new_nation)
                    await _nw.record_project_purchase(
                        nation_id=nation_id,
                        nation_name=nation_name,
                        nation_flag=new_nation.get("flag"),
                        alliance_id=int(new_nation.get("alliance_id") or 0) or None,
                        alliance_name=new_nation.get("alliance_name"),
                        alliance_flag=new_nation.get("alliance_flag"),
                        project_names=proj_names,
                        cash_cost=proj_cost,
                        resource_costs=proj_rss if proj_rss else None,
                        event_date=ev_date,
                    )
                except Exception as _ne:
                    logger.debug(f"news project_purchase: {_ne}")
        
        # Military unit tracking
        _MIL_KEYS = ("soldiers", "tanks", "aircraft", "ships", "missiles", "nukes", "spies")
        has_military_fields = any(k in new_nation for k in _MIL_KEYS)
        if not has_military_fields:
            return
        
        present_keys = [k for k in _MIL_KEYS if k in new_nation]
        old_military = {k: int(old_nation.get(k) or 0) for k in present_keys}
        new_military = {k: int(new_nation.get(k) or 0) for k in present_keys}
        
        if old_military != new_military:
            await self.holdings_db.apply_military_update(
                nation_id=nation_id,
                old_military=old_military,
                new_military=new_military,
                event_date=ev_date,
                nation_name=nation_name,
            )
    
    async def detect_city_spending(
        self,
        nation_id: int,
        old_city: Dict[str, Any],
        new_city: Dict[str, Any],
        nation_data: Optional[Dict[str, Any]] = None,
        event_date: Optional[str] = None,
    ):
        """
        Compare old vs new city snapshot to detect upgrades.
        
        Deducts costs from holdings BEFORE the new snapshot is saved.
        """
        if not self.holdings_db:
            return
        
        from PnWHarvester.db.pnw_costs import (
            infra_cost, land_cost, city_improvements_cost, city_improvements_resource_costs,
        )
        
        ev_date = event_date or self._now_str()
        nation_name = (nation_data or {}).get("nation_name") if nation_data else None
        nd = nation_data or {}
        
        total_cost = 0.0
        breakdown = []
        item_details = []
        
        old_infra = float(old_city.get("infrastructure") or 0)
        new_infra = float(new_city.get("infrastructure") or 0)
        infra_cost_val = 0.0
        if new_infra > old_infra:
            infra_cost_val = infra_cost(old_infra, new_infra, nation_data=nd)
            total_cost += infra_cost_val
            breakdown.append(f"infra {old_infra:.0f}→{new_infra:.0f} ${infra_cost_val:,.0f}")
            item_details.append(f"infrastructure:{old_infra:.1f}→{new_infra:.1f}")
        
        old_land = float(old_city.get("land") or 0)
        new_land = float(new_city.get("land") or 0)
        land_cost_val = 0.0
        if new_land > old_land:
            land_cost_val = land_cost(old_land, new_land, nation_data=nd)
            total_cost += land_cost_val
            breakdown.append(f"land {old_land:.0f}→{new_land:.0f} ${land_cost_val:,.0f}")
            item_details.append(f"land:{old_land:.1f}→{new_land:.1f}")
        
        imp_cost = city_improvements_cost(old_city, new_city)
        imp_rss = city_improvements_resource_costs(old_city, new_city)
        if imp_cost > 0 or imp_rss:
            total_cost += imp_cost
            rss_str = ", ".join(f"{r}={v:,.1f}" for r, v in imp_rss.items()) if imp_rss else ""
            breakdown.append(f"improvements ${imp_cost:,.0f}" + (f" + {rss_str}" if rss_str else ""))
            item_details.append("improvements")
        
        if total_cost > 0 or imp_rss:
            await self.holdings_db.deduct_spending(
                nation_id=nation_id,
                cash_cost=total_cost,
                event_type="city_upgrade",
                description=f"City {old_city.get('id')} upgrades: {'; '.join(breakdown)}",
                event_date=ev_date,
                nation_name=nation_name,
                item_type="city_upgrade",
                item_quantity=len([
                    x for x in [
                        old_infra != new_infra,
                        old_land != new_land,
                        bool(imp_cost or imp_rss),
                    ] if x
                ]),
                item_details="; ".join(item_details),
                resource_costs=imp_rss if imp_rss else None,
            )
            rss_str = ", ".join(f"{r}={v:,.1f}" for r, v in imp_rss.items()) if imp_rss else ""
            logger.info(
                f"Holdings: nation {nation_id} city {old_city.get('id')} "
                f"upgrade ${total_cost:,.0f}: {'; '.join(breakdown)}"
                + (f" + {rss_str}" if rss_str else "")
            )
            # News: city upgrade
            try:
                import PnWHarvester.db.news_writer as _nw
                from PnWHarvester.db.pnw_costs import _DB_COL_TO_WAR_CALC
                _nd = nation_data or {}
                _imps_built: Dict[str, int] = {}
                for _col in _DB_COL_TO_WAR_CALC:
                    _before = int(old_city.get(_col) or 0)
                    _after = int(new_city.get(_col) or 0)
                    _delta = max(0, _after - _before)
                    if _delta > 0:
                        _imps_built[_col] = _delta
                await _nw.record_city_upgrade(
                    nation_id=nation_id,
                    nation_name=nation_name,
                    nation_flag=_nd.get("flag"),
                    alliance_id=int(_nd.get("alliance_id") or 0) or None,
                    alliance_name=_nd.get("alliance_name"),
                    alliance_flag=_nd.get("alliance_flag"),
                    infra_spent=infra_cost_val,
                    land_spent=land_cost_val,
                    improvements_spent=float(imp_cost),
                    total_spent=total_cost,
                    detail_str="; ".join(breakdown),
                    city_id=old_city.get("id"),
                    city_name=old_city.get("name"),
                    event_date=ev_date,
                    improvements_built=_imps_built if _imps_built else None,
                    improvement_resource_costs=imp_rss if imp_rss else None,
                    infra_before=old_infra if new_infra > old_infra else None,
                    infra_after=new_infra if new_infra > old_infra else None,
                    land_before=old_land if new_land > old_land else None,
                    land_after=new_land if new_land > old_land else None,
                )
            except Exception as _ne:
                logger.debug(f"news city_upgrade: {_ne}")
