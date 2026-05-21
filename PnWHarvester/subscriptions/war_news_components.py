"""
War News Generation Components

Handles generation of news events for war-related activities.
"""

import asyncio
import logging
from collections import deque
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _obj_to_dict(obj: Any) -> Dict[str, Any]:
    """Convert objects to dictionaries safely."""
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return dict(obj)
    return vars(obj)


def _norm(val: Any) -> str:
    """Normalise an enum/string value to lowercase plain string."""
    if val is None:
        return ""
    s = str(val)
    if "." in s:
        s = s.rsplit(".", 1)[-1]
    return s.lower()


def _clean_aname(name: Any) -> Optional[str]:
    """Return None if name is falsy or the PnW '0' placeholder, else return name."""
    return name if (name and name != '0') else None


class WarNewsGenerator:
    """Generates news events for war-related activities."""
    
    def __init__(self, news_component=None):
        """
        Initialize the war news generator.
        
        Args:
            news_component: NewsComponent instance (optional)
        """
        self.news_component = news_component
    
    async def generate_war_declared_news(self, war_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate news for war declaration."""
        if not self.news_component:
            return {"status": "no_news_component", "generated": False}
        
        try:
            att_obj = war_data.get("attacker") or {}
            def_obj = war_data.get("defender") or {}
            if not isinstance(att_obj, dict): att_obj = {}
            if not isinstance(def_obj, dict): def_obj = {}
            
            # Extract alliance data from nested objects
            att_aname = (att_obj.get("alliance") or {}).get("name") if isinstance(att_obj.get("alliance"), dict) else None
            def_aname = (def_obj.get("alliance") or {}).get("name") if isinstance(def_obj.get("alliance"), dict) else None
            att_aflag = (att_obj.get("alliance") or {}).get("flag") if isinstance(att_obj.get("alliance"), dict) else None
            def_aflag = (def_obj.get("alliance") or {}).get("flag") if isinstance(def_obj.get("alliance"), dict) else None
            
            # Create news event
            await self.news_component.record_event(
                event_type="war_declared",
                nation_id=int(war_data.get("att_id") or 0),
                nation_name=att_obj.get("nation_name") or war_data.get("att_nation_name"),
                nation_flag=att_obj.get("flag"),
                alliance_id=int(war_data.get("att_alliance_id") or 0) or None,
                alliance_name=att_aname,
                alliance_flag=att_aflag,
                sec_nation_id=int(war_data.get("def_id") or 0),
                sec_nation_name=def_obj.get("nation_name") or war_data.get("def_nation_name"),
                sec_alliance_id=int(war_data.get("def_alliance_id") or 0) or None,
                sec_alliance_name=def_aname,
                headline=f"{att_obj.get('nation_name')} declared war on {def_obj.get('nation_name')}",
                detail={
                    "war_id": int(war_data.get("id") or 0),
                    "war_type": _norm(war_data.get("war_type", "")),
                    "reason": war_data.get("reason"),
                    "att_leader_name": att_obj.get("leader_name"),
                    "def_leader_name": def_obj.get("leader_name"),
                },
                event_date=str(war_data.get("date") or "").replace("+00:00", "").strip(),
            )
            
            return {
                "status": "generated",
                "generated": True,
                "news_type": "war_declared",
                "war_id": war_data.get("id"),
                "att_nation_id": war_data.get("att_id"),
                "def_nation_id": war_data.get("def_id")
            }
        except Exception as e:
            logger.error(f"WarNewsGenerator.generate_war_declared_news: {e}", exc_info=True)
            return {"status": "error", "error": str(e), "generated": False}
    
    async def generate_war_ended_news(self, war_data: Dict[str, Any], end_reason: str) -> Dict[str, Any]:
        """Generate news for war end."""
        if not self.news_component:
            return {"status": "no_news_component", "generated": False}
        
        try:
            att_obj = war_data.get("attacker") or {}
            def_obj = war_data.get("defender") or {}
            if not isinstance(att_obj, dict): att_obj = {}
            if not isinstance(def_obj, dict): def_obj = {}
            
            # Extract alliance data
            att_aname = (att_obj.get("alliance") or {}).get("name") if isinstance(att_obj.get("alliance"), dict) else None
            def_aname = (def_obj.get("alliance") or {}).get("name") if isinstance(def_obj.get("alliance"), dict) else None
            att_aflag = (att_obj.get("alliance") or {}).get("flag") if isinstance(att_obj.get("alliance"), dict) else None
            def_aflag = (def_obj.get("alliance") or {}).get("flag") if isinstance(def_obj.get("alliance"), dict) else None
            
            # Create news event
            asyncio.create_task(nw.record_war_ended(
                war_id=int(war_data.get("id") or 0),
                att_nation_id=int(war_data.get("att_id") or 0),
                att_nation_name=att_obj.get("nation_name") or war_data.get("att_nation_name"),
                att_nation_flag=att_obj.get("flag"),
                att_alliance_id=int(war_data.get("att_alliance_id") or 0) or None,
                att_alliance_name=att_aname,
                att_alliance_flag=att_aflag,
                def_nation_id=int(war_data.get("def_id") or 0),
                def_nation_name=def_obj.get("nation_name") or war_data.get("def_nation_name"),
                def_nation_flag=def_obj.get("flag"),
                def_alliance_id=int(war_data.get("def_alliance_id") or 0) or None,
                def_alliance_name=def_aname,
                def_alliance_flag=def_aflag,
                winner_id=int(war_data.get("winner_id") or 0) or None,
                end_reason=end_reason,
                war_type=_norm(war_data.get("war_type", "")),
                event_date=str(war_data.get("end_date") or war_data.get("date") or "").replace("+00:00", "").strip(),
            ))
            
            return {
                "status": "generated",
                "generated": True,
                "news_type": "war_ended",
                "war_id": war_data.get("id"),
                "end_reason": end_reason,
                "winner_id": war_data.get("winner_id")
            }
        except Exception as e:
            logger.error(f"Failed to generate war ended news: {e}", exc_info=True)
            return {"status": "error", "generated": False, "error": str(e)}
    
    async def generate_attack_news(self, attack_data: Dict[str, Any], war_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate news for attack events (loot, WMD, etc.)."""
        if not self.news_component:
            return {"status": "no_news_component", "generated": False}
        
        try:
            # Determine which war role corresponds to attack's attacker/defender
            att_id = attack_data.get("att_id") or attack_data.get("attacker_id")
            _war_att_id = war_data.get("att_id")
            
            if str(att_id) == str(_war_att_id):
                _att_prefix, _def_prefix = "att", "def"
            else:
                _att_prefix, _def_prefix = "def", "att"
            
            # Extract alliance and nation data
            att_alliance_id = int(war_data.get(f"{_att_prefix}_alliance_id") or 0) or None
            def_alliance_id = int(war_data.get(f"{_def_prefix}_alliance_id") or 0) or None
            
            _att_aname = war_data.get(f"{_att_prefix}_alliance_name") or ""
            _def_aname = war_data.get(f"{_def_prefix}_alliance_name") or ""
            att_alliance_name = _att_aname if _att_aname and _att_aname != "0" else None
            def_alliance_name = _def_aname if _def_aname and _def_aname != "0" else None
            
            att_flag = war_data.get(f"{_att_prefix}_nation_flag")
            def_flag = war_data.get(f"{_def_prefix}_nation_flag")
            att_alliance_flag = war_data.get(f"{_att_prefix}_alliance_flag") or None
            def_alliance_flag = war_data.get(f"{_def_prefix}_alliance_flag") or None
            
            # Parse improvements destroyed
            _raw_imps = attack_data.get("improvements_destroyed") or []
            _imps_destroyed: Dict[str, int] = {}
            if isinstance(_raw_imps, list):
                for _imp_raw in _raw_imps:
                    _imp = str(_imp_raw).lower().replace(" ", "_")
                    _imps_destroyed[_imp] = _imps_destroyed.get(_imp, 0) + 1
            elif isinstance(_raw_imps, dict):
                _imps_destroyed = {k: int(v) for k, v in _raw_imps.items() if int(v) > 0}
            
            # Calculate infrastructure value
            infra_val = await self._calculate_infra_value(attack_data)
            
            # Determine attack type and generate appropriate news
            attack_type_raw = _norm(attack_data.get("type", ""))
            att_name = war_data.get(f"{_att_prefix}_nation_name")
            def_name = war_data.get(f"{_def_prefix}_nation_name")
            
            # Determine if attack missed
            _attack_missed = self._determine_attack_missed(attack_data, attack_type_raw)
            _resistance_lost = int(attack_data.get("resistance_lost") or 0) or None
            
            result = {
                "status": "generated",
                "generated": True,
                "attack_id": attack_data.get("id"),
                "attack_type": attack_type_raw,
                "news_events": []
            }
            
            # Generate WMD news for nuke/missile attacks
            if attack_type_raw in ("nuke", "nukefail"):
                asyncio.create_task(self._safe_record_wmd(
                    "nuke", attack_data, war_data, _att_prefix, _def_prefix,
                    att_alliance_id, def_alliance_id, att_alliance_name, def_alliance_name,
                    att_flag, def_flag, att_alliance_flag, def_alliance_flag,
                    infra_val, _attack_missed, _resistance_lost, _imps_destroyed
                ))
                result["news_events"].append("nuke_attack")
            
            elif attack_type_raw in ("missile", "missilefail"):
                asyncio.create_task(self._safe_record_wmd(
                    "missile", attack_data, war_data, _att_prefix, _def_prefix,
                    att_alliance_id, def_alliance_id, att_alliance_name, def_alliance_name,
                    att_flag, def_flag, att_alliance_flag, def_alliance_flag,
                    infra_val, _attack_missed, _resistance_lost, _imps_destroyed
                ))
                result["news_events"].append("missile_attack")
            
            # Generate loot news for successful attacks
            if self._is_win_attack(attack_data):
                money_looted = float(attack_data.get("money_stolen") or attack_data.get("money_looted") or 0)
                res_looted = {r: float(attack_data.get(f"{r}_looted") or 0) for r in [
                    "coal", "oil", "uranium", "iron", "bauxite", "lead",
                    "gasoline", "munitions", "steel", "aluminum", "food"
                ]}
                total_loot = self._calc_loot_value(money_looted, res_looted)
                
                if total_loot > 0:
                    asyncio.create_task(nw.record_loot_attack(
                        att_nation_id=attack_data.get("att_id") or attack_data.get("attacker_id"),
                        att_nation_name=att_name,
                        att_nation_flag=att_flag,
                        att_alliance_id=att_alliance_id,
                        att_alliance_name=att_alliance_name,
                        att_alliance_flag=att_alliance_flag,
                        def_nation_id=attack_data.get("def_id") or attack_data.get("defender_id"),
                        def_nation_name=def_name,
                        def_nation_flag=def_flag,
                        def_alliance_id=def_alliance_id,
                        def_alliance_name=def_alliance_name,
                        money_looted=money_looted,
                        total_loot_value=total_loot,
                        event_date=str(attack_data.get("date") or "").replace("+00:00", "").strip(),
                        resources_looted={r: v for r, v in res_looted.items() if v > 0},
                        improvements_destroyed=_imps_destroyed if _imps_destroyed else None,
                        infra_destroyed_value=infra_val,
                    ))
                    result["news_events"].append("loot_attack")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to generate attack news: {e}", exc_info=True)
            return {"status": "error", "generated": False, "error": str(e)}
    
    async def _safe_record_wmd(self, attack_type: str, attack_data: Dict[str, Any], war_data: Dict[str, Any],
                               _att_prefix: str, _def_prefix: str, att_alliance_id: Optional[int], 
                               def_alliance_id: Optional[int], att_alliance_name: Optional[str],
                               def_alliance_name: Optional[str], att_flag: Optional[str], def_flag: Optional[str],
                               att_alliance_flag: Optional[str], def_alliance_flag: Optional[str],
                               infra_val: float, _attack_missed: bool, _resistance_lost: Optional[int],
                               _imps_destroyed: Dict[str, int]) -> None:
        """Safely record WMD attack news."""
        if not self.news_component:
            return
        
        try:
            att_id = attack_data.get("att_id") or attack_data.get("attacker_id")
            def_id = attack_data.get("def_id") or attack_data.get("defender_id")
            
            await self.news_component.record_event(
                event_type=f"{attack_type}_attack",
                nation_id=att_id,
                nation_name=war_data.get(f"{_att_prefix}_nation_name"),
                nation_flag=att_flag,
                alliance_id=att_alliance_id,
                alliance_name=att_alliance_name,
                alliance_flag=att_alliance_flag,
                sec_nation_id=def_id,
                sec_nation_name=war_data.get(f"{_def_prefix}_nation_name"),
                sec_alliance_id=def_alliance_id,
                sec_alliance_name=def_alliance_name,
                value=infra_val,
                headline=f"{war_data.get(f'{_att_prefix}_nation_name')} fired {attack_type} at {war_data.get(f'{_def_prefix}_nation_name')}",
                detail={
                    "attack_type": attack_type,
                    "att_id": att_id,
                    "def_id": def_id,
                    "infra_destroyed_value": infra_val,
                    "attack_missed": _attack_missed,
                    "resistance_lost": _resistance_lost,
                    "improvements_destroyed": _imps_destroyed,
                },
                event_date=str(attack_data.get("date") or "").replace("+00:00", "").strip(),
            )
        except Exception as e:
            logger.error(f"record_wmd_attack({attack_type}) failed for attack {attack_data.get('id')}: {e}", exc_info=True)
    
    async def _calculate_infra_value(self, attack_data: Dict[str, Any]) -> float:
        """Calculate infrastructure value from attack data."""
        try:
            from PnWHarvester.db.pnw_costs import calc_infra_value as _calc_infra_val
            _city_infra_before = float(attack_data.get("city_infra_before") or 0)
            _infra_destroyed = float(attack_data.get("infra_destroyed") or 0)
            if _city_infra_before > 0 and _infra_destroyed > 0:
                _infra_after = max(0.0, _city_infra_before - _infra_destroyed)
                return _calc_infra_val(_infra_after, _city_infra_before)
            else:
                return float(attack_data.get("infra_destroyed_value") or 0)
        except Exception:
            return float(attack_data.get("infra_destroyed_value") or 0)
    
    def _determine_attack_missed(self, attack_data: Dict[str, Any], attack_type_raw: str) -> bool:
        """Determine if attack missed based on various indicators."""
        # Priority 1: Check if attack type explicitly indicates a miss (missilefail/nukefail)
        # Priority 2: Check success field from API
        # Priority 3: Check victor field (if victor != attacker, it's a miss)
        
        if attack_type_raw in ("missilefail", "nukefail"):
            return True
        
        _success = attack_data.get("success")
        if _success is not None:
            return not bool(_success)
        
        _victor = attack_data.get("victor")
        att_id = attack_data.get("att_id") or attack_data.get("attacker_id")
        if _victor is not None and att_id is not None:
            return str(_victor) != str(att_id)
        
        return False
    
    def _is_win_attack(self, attack_data: Dict[str, Any]) -> bool:
        """Check if attack is a winning attack with loot."""
        victor = attack_data.get("victor")
        att_id = attack_data.get("att_id") or attack_data.get("attacker_id")
        
        if victor is None or att_id is None:
            return self._has_loot(attack_data)
        
        return str(victor) == str(att_id) and self._has_loot(attack_data)
    
    def _has_loot(self, attack: Dict[str, Any]) -> bool:
        """Check if attack has loot."""
        if float(attack.get("money_stolen") or attack.get("money_looted") or 0) > 0:
            return True
        
        _RESOURCES = (
            "coal", "oil", "uranium", "iron", "bauxite", "lead",
            "gasoline", "munitions", "steel", "aluminum", "food",
        )
        return any(float(attack.get(f"{r}_looted") or 0) > 0 for r in _RESOURCES)
    
    def _calc_loot_value(self, money_looted: float, resources_looted: Dict[str, float]) -> float:
        """Calculate total loot value."""
        _FALLBACK_PRICES = {
            "coal": 2000, "oil": 2000, "uranium": 4000, "iron": 2000,
            "bauxite": 2000, "lead": 2000, "gasoline": 3000, "munitions": 2000,
            "steel": 3000, "aluminum": 2000, "food": 150,
        }
        
        try:
            import sqlite3
            from Systems.Functions.db_paths import REAPER_DB_STR
            conn = sqlite3.connect(REAPER_DB_STR)
            rows = conn.execute(
                """
                SELECT resource, best_sell_price FROM resource_prices
                WHERE timestamp = (SELECT MAX(timestamp) FROM resource_prices)
                """
            ).fetchall()
            conn.close()
            price_map = {r.lower(): float(p) for r, p in rows if p and float(p) > 0} if rows else _FALLBACK_PRICES
        except Exception:
            price_map = _FALLBACK_PRICES
        
        resource_value = sum(
            amt * price_map.get(resource, _FALLBACK_PRICES.get(resource, 1000))
            for resource, amt in resources_looted.items()
            if amt > 0
        )
        return money_looted + resource_value


class BeigeManager:
    """Manages beige state updates for war losses."""
    
    def __init__(self, global_nations_db=None):
        self.global_nations_db = global_nations_db
        self.BEIGE_TURNS_ON_LOSS = 24
    
    async def handle_war_loss_beige(self, war_dict: Dict[str, Any], loser_id: int) -> Dict[str, Any]:
        """
        Handle beige updates when a nation loses a war.
        
        1. Patch GlobalNations.db beige_turns immediately
        2. Update beige_alerts rows in alerts.db
        """
        result = {
            "status": "processed",
            "loser_id": loser_id,
            "beige_turns_updated": False,
            "alerts_updated": 0,
            "errors": []
        }
        
        # Determine loser name for logging
        loser_name = (
            war_dict.get("def_nation_name")
            if int(war_dict.get("def_id") or 0) == loser_id
            else war_dict.get("att_nation_name")
        ) or f"nation {loser_id}"
        
        # 1. Update GlobalNations.db beige_turns
        if self.global_nations_db:
            try:
                existing = await self.global_nations_db.get_nation(loser_id)
                current_beige = int((existing or {}).get("beige_turns") or 0)
                
                if current_beige < self.BEIGE_TURNS_ON_LOSS:
                    await self.global_nations_db.save_nation({
                        "id": loser_id,
                        "beige_turns": self.BEIGE_TURNS_ON_LOSS,
                    })
                    result["beige_turns_updated"] = True
                    logger.info(
                        f"beige: patched GlobalNations.db beige_turns for {loser_name} "
                        f"(id={loser_id}): {current_beige} → {self.BEIGE_TURNS_ON_LOSS}"
                    )
                else:
                    logger.debug(
                        f"beige: {loser_name} (id={loser_id}) already has "
                        f"{current_beige} beige_turns ≥ {self.BEIGE_TURNS_ON_LOSS} — no patch needed"
                    )
            except Exception as e:
                result["errors"].append(f"GlobalNations.db patch failed: {e}")
                logger.warning(f"_handle_war_loss_beige: GlobalNations.db patch failed for {loser_id}: {e}")
        
        # 2. Update beige_alerts rows
        try:
            from Systems.Functions.beige_alerts_db import (
                get_beige_alerts_for_nation,
                update_beige_alert_turns,
            )
            alerts = await get_beige_alerts_for_nation(loser_id)
            if alerts:
                for alert in alerts:
                    stored_turns = int(alert.get("beige_turns") or 0)
                    new_turns = max(stored_turns, self.BEIGE_TURNS_ON_LOSS)
                    
                    if new_turns != stored_turns:
                        await update_beige_alert_turns(int(alert["id"]), new_turns)
                        result["alerts_updated"] += 1
                        logger.info(
                            f"beige_alerts: war loss — updated {loser_name} (id={loser_id}) "
                            f"turns {stored_turns} → {new_turns} for user {alert['user_id']}"
                        )
                    else:
                        logger.debug(
                            f"beige_alerts: war loss — {loser_name} (id={loser_id}) already has "
                            f"{stored_turns} turns ≥ {self.BEIGE_TURNS_ON_LOSS}, no update needed"
                        )
        except Exception as e:
            result["errors"].append(f"alerts.db update failed: {e}")
            logger.warning(f"_handle_war_loss_beige: alerts.db update failed for {loser_id}: {e}")
        
        return result


class WarStatsUpdater:
    """Updates nation war statistics."""
    
    def __init__(self, global_nations_db=None):
        self.global_nations_db = global_nations_db
        self._processed_war_ids: set = set()
        self._processed_war_ids_order: deque = deque(maxlen=5000)
    
    def is_war_processed(self, war_id: int) -> bool:
        """Check if war end was already processed."""
        return war_id in self._processed_war_ids
    
    def mark_war_processed(self, war_id: int) -> None:
        """Mark war end as processed to prevent duplicate updates."""
        if war_id not in self._processed_war_ids:
            self._processed_war_ids.add(war_id)
            self._processed_war_ids_order.append(war_id)
            
            # Evict oldest entries if the set grows too large
            while len(self._processed_war_ids) > 5000:
                oldest = self._processed_war_ids_order.popleft()
                self._processed_war_ids.discard(oldest)
    
    async def update_war_counts_on_create(self, war_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update war counts when war is declared."""
        if not self.global_nations_db:
            return {"status": "no_db", "updated": False}
        
        result = {
            "status": "updated",
            "updated": True,
            "attacker_updated": False,
            "defender_updated": False,
            "errors": []
        }
        
        try:
            att_id = int(war_data.get("att_id") or 0)
            def_id = int(war_data.get("def_id") or 0)
            
            # Increment offensive war count for attacker
            if att_id:
                asyncio.create_task(
                    self.global_nations_db.update_war_counts(att_id, off_delta=1)
                )
                result["attacker_updated"] = True
            
            # Increment defensive war count for defender
            if def_id:
                asyncio.create_task(
                    self.global_nations_db.update_war_counts(def_id, def_delta=1)
                )
                result["defender_updated"] = True
                
        except Exception as e:
            result["errors"].append(f"War count update failed: {e}")
            logger.error(f"update_war_counts_on_create failed: {e}", exc_info=True)
        
        return result
    
    async def update_war_counts_on_end(self, war_data: Dict[str, Any], end_reason: str) -> Dict[str, Any]:
        """Update war counts and statistics when war ends."""
        if not self.global_nations_db:
            return {"status": "no_db", "updated": False}
        
        war_id = int(war_data.get("id") or 0)
        
        # Check if already processed
        if self.is_war_processed(war_id):
            return {"status": "already_processed", "updated": False, "war_id": war_id}
        
        result = {
            "status": "updated",
            "updated": True,
            "war_id": war_id,
            "end_reason": end_reason,
            "slot_updates": [],
            "win_loss_updates": [],
            "beige_updates": [],
            "errors": []
        }
        
        try:
            att_id = int(war_data.get("att_id") or 0)
            def_id = int(war_data.get("def_id") or 0)
            winner_id = int(war_data.get("winner_id") or 0)
            
            # WIN: winner gets wars_won+1, loser gets wars_lost+1
            # Slot counts: attacker -1 off, defender -1 def
            if end_reason == "win" and winner_id:
                loser_id = def_id if winner_id == att_id else att_id
                
                # Update attacker
                if att_id:
                    is_attacker_winner = winner_id == att_id
                    asyncio.create_task(self.global_nations_db.update_war_counts(
                        att_id, 
                        off_delta=-1,
                        won_delta=(1 if is_attacker_winner else 0),
                        lost_delta=(1 if not is_attacker_winner else 0),
                    ))
                    result["win_loss_updates"].append({
                        "nation_id": att_id,
                        "type": "attacker",
                        "won": is_attacker_winner,
                        "lost": not is_attacker_winner
                    })
                
                # Update defender
                if def_id:
                    is_defender_winner = winner_id == def_id
                    asyncio.create_task(self.global_nations_db.update_war_counts(
                        def_id,
                        def_delta=-1,
                        won_delta=(1 if is_defender_winner else 0),
                        lost_delta=(1 if not is_defender_winner else 0),
                    ))
                    result["win_loss_updates"].append({
                        "nation_id": def_id,
                        "type": "defender",
                        "won": is_defender_winner,
                        "lost": not is_defender_winner
                    })
                
                # Handle beige for loser
                if loser_id:
                    result["beige_updates"].append({
                        "nation_id": loser_id,
                        "action": "beige_from_loss"
                    })
            
            else:
                # Peace, expire, or ended — decrement slots only
                # No wars_lost increment: these are not decisive losses
                if att_id:
                    asyncio.create_task(self.global_nations_db.update_war_counts(att_id, off_delta=-1))
                    result["slot_updates"].append({"nation_id": att_id, "type": "attacker", "action": "slot_decrement"})
                
                if def_id:
                    asyncio.create_task(self.global_nations_db.update_war_counts(def_id, def_delta=-1))
                    result["slot_updates"].append({"nation_id": def_id, "type": "defender", "action": "slot_decrement"})
                
                # Handle beige for defender on expire
                if end_reason == "expire" and def_id:
                    result["beige_updates"].append({
                        "nation_id": def_id,
                        "action": "beige_from_expire"
                    })
            
            # Mark as processed
            self.mark_war_processed(war_id)
            
        except Exception as e:
            result["errors"].append(f"War end update failed: {e}")
            logger.error(f"update_war_counts_on_end failed: {e}", exc_info=True)
        
        return result