import requests
import logging
from typing import List, Dict, Optional, Any, Union, TypedDict
import os
import json
import sys
import re
import time
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from functools import partial
from urllib.parse import quote

# ZoneInfo fallback for Python < 3.9
try:
    from zoneinfo import ZoneInfo
except Exception:
    try:
        from backports.zoneinfo import ZoneInfo
    except Exception:
        ZoneInfo = None

# Add parent directory to path for config import
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
try:
    from config import PANDW_API_KEY
except ImportError:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from config import PANDW_API_KEY

class Radiation(TypedDict):
    global_: float  # Use global_ to avoid reserved keyword conflict
    north_america: float
    south_america: float
    europe: float
    africa: float
    asia: float
    australia: float
    antarctica: float

class GameInfo(TypedDict):
    game_date: str
    radiation: Radiation
    city_average: float

class NationResourceStat(TypedDict):
    date: str
    money: str
    food: str
    steel: str
    aluminum: str
    gasoline: str
    munitions: str
    uranium: str
    coal: str
    oil: str
    iron: str
    bauxite: str
    lead: str

class WarFilters(TypedDict, total=False):
    nation_ids: Optional[List[int]]
    alliance_ids: Optional[List[int]]
    min_score: Optional[int]
    max_score: Optional[int]
    min_cities: Optional[int]
    max_cities: Optional[int]
    min_infra: Optional[int]
    max_infra: Optional[int]
    min_land: Optional[int]
    max_land: Optional[int]
    min_pop: Optional[int]
    max_pop: Optional[int]
    min_gnp: Optional[int]
    max_gnp: Optional[int]
    min_tech: Optional[int]
    max_tech: Optional[int]
    min_offensive_wars: Optional[int]
    max_offensive_wars: Optional[int]
    min_defensive_wars: Optional[int]
    max_defensive_wars: Optional[int]
    min_wars_won: Optional[int]
    max_wars_won: Optional[int]
    min_wars_lost: Optional[int]
    max_wars_lost: Optional[int]
    min_money: Optional[int]
    max_money: Optional[int]
    min_food: Optional[int]
    max_food: Optional[int]
    min_oil: Optional[int]
    max_oil: Optional[int]
    min_uranium: Optional[int]
    max_uranium: Optional[int]
    min_coal: Optional[int]
    max_coal: Optional[int]
    min_iron: Optional[int]
    max_iron: Optional[int]
    min_bauxite: Optional[int]
    max_bauxite: Optional[int]
    min_lead: Optional[int]
    max_lead: Optional[int]
    min_aluminum: Optional[int]
    max_aluminum: Optional[int]
    min_steel: Optional[int]
    max_steel: Optional[int]
    min_gasoline: Optional[int]
    max_gasoline: Optional[int]
    min_munitions: Optional[int]
    max_munitions: Optional[int]
    min_credits: Optional[int]
    max_credits: Optional[int]
    min_soldiers: Optional[int]
    max_soldiers: Optional[int]
    min_tanks: Optional[int]
    max_tanks: Optional[int]
    min_aircraft: Optional[int]
    max_aircraft: Optional[int]
    min_ships: Optional[int]
    max_ships: Optional[int]
    min_missiles: Optional[int]
    max_missiles: Optional[int]
    min_nukes: Optional[int]
    max_nukes: Optional[int]
    min_spies: Optional[int]
    max_spies: Optional[int]
    active_mode: Optional[str]
    war_ids: Optional[List[int]]
    nation_id_home: Optional[int]
    nation_id_away: Optional[int]
    alliance_id_home: Optional[int]
    alliance_id_away: Optional[int]
    start_date: Optional[str]
    end_date: Optional[str]

class PNWAPIQuery:
    """Centralized class for handling all PNW API GraphQL queries with optimized caching."""
    
    def __init__(self, api_key: Optional[str] = None, logger: Optional[logging.Logger] = None):
        self.api_key: str = api_key or self._get_api_key()
        self.logger: logging.Logger = logger or logging.getLogger(__name__)
        self.base_url = "https://api.politicsandwar.com/graphql"
        
        # Configuration
        self.cache_ttl_seconds = 3600
        self._min_interval_seconds = float(os.getenv("PNW_MIN_INTERVAL", "0.15"))
        
        # HTTP session with retries
        self._session = requests.Session()
        retry = Retry(total=3, backoff_factor=0.3, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        
        self._default_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "User-Agent": "ReaperPNW/1.0 (+https://discordbots/reaper)"
        }
        
        # Timezone configuration
        self.local_tz_name = os.getenv("PNW_LOCAL_TZ", "America/New_York")
        self.local_tz = self._get_timezone(self.local_tz_name)
        self.utc_tz = self._get_timezone("UTC")
        
        # Unified cache system
        self._cache = {
            'queries': {},  # Query result cache
            'resolve': {},  # Entity resolution cache
            'trade': {},  # Trade data cache
            'kv': {}  # Key-value cache
        }
        self._cache_expiry = {}
        
        # Processing flags to prevent infinite loops
        self._processing = {
            'alliances': set(),
            'projects': set(),
            'improvements': set()
        }
        
        # Rate limiting
        self._last_request_ts = 0.0
        
        # Validate API key
        if not self.api_key or self.api_key == "YOUR_API_KEY_HERE":
            raise ValueError("P&W API key not configured. Please set PANDW_API_KEY in your .env file.")

    def _get_api_key(self) -> str:
        """Get API key from config with fallbacks."""
        try:
            from config import PANDW_API_KEY as CONFIG_PANDW_API_KEY
            if CONFIG_PANDW_API_KEY:
                return CONFIG_PANDW_API_KEY
        except ImportError:
            pass
        raise ValueError("P&W API key not configured. Please set PANDW_API_KEY in your .env file.")

    def _get_timezone(self, tz_name: str) -> Optional[ZoneInfo]:
        """Get timezone object with error handling."""
        try:
            return ZoneInfo(tz_name)
        except Exception:
            return None

    def _get_cache_key(self, cache_type: str, key: str) -> str:
        """Generate standardized cache key."""
        return f"{cache_type}:{key}"

    def _is_cache_valid(self, cache_type: str, key: str) -> bool:
        """Check if cache entry is still valid."""
        cache_key = self._get_cache_key(cache_type, key)
        if cache_key not in self._cache_expiry:
            return False
        
        expiry = self._cache_expiry[cache_key]
        return time.monotonic() < expiry

    def _set_cache(self, cache_type: str, key: str, value: Any, ttl: Optional[float] = None):
        """Set cache value with optional TTL."""
        cache_key = self._get_cache_key(cache_type, key)
        self._cache[cache_type][cache_key] = value
        self._cache_expiry[cache_key] = time.monotonic() + (ttl or self.cache_ttl_seconds)

    def _get_cache(self, cache_type: str, key: str, default: Any = None) -> Any:
        """Get cached value if valid."""
        cache_key = self._get_cache_key(cache_type, key)
        if self._is_cache_valid(cache_type, key):
            return self._cache[cache_type].get(cache_key, default)
        return default

    def _rate_limit_wait(self):
        """Apply rate limiting between requests."""
        elapsed = time.monotonic() - self._last_request_ts
        if elapsed < self._min_interval_seconds:
            time.sleep(self._min_interval_seconds - elapsed)
        self._last_request_ts = time.monotonic()

    def _make_request(self, query: str, timeout: int = 30, cache_ttl: float = 0) -> Dict[str, Any]:
        """Make HTTP request with caching and rate limiting."""
        # Check query cache
        cache_key = str(hash(query))
        if self._is_cache_valid('queries', cache_key):
            return self._get_cache('queries', cache_key)

        self._rate_limit_wait()
        self.logger.debug(f"Sending GraphQL query: {query}")
        url = f"{self.base_url}?api_key={self.api_key}"
        payload = {"query": query}
        headers = dict(self._default_headers)

        try:
            resp = self._session.post(url, json=payload, headers=headers, timeout=timeout)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            msg = str(e).replace(self.api_key, "API_KEY_REDACTED")
            self.logger.error(f"Request failed: {msg}")
            raise Exception(f"API Request Failed: {msg}")

        data = resp.json()
        self.logger.debug(f"Received API response: {json.dumps(data, indent=2)}")

        if isinstance(data, dict) and data.get("errors"):
            errs = data.get("errors") or []
            msg = errs[0].get("message") if errs and isinstance(errs[0], dict) else str(errs)
            raise Exception(msg or "GraphQL error")

        # Cache the result
        if cache_ttl > 0:
            self._set_cache('queries', cache_key, data, cache_ttl)

        return data

    async def _request_with_retries(
        self,
        query: str,
        timeout: int = 30,
        attempts: int = 3,
        cache_ttl: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Make request with retries in async context."""
        loop = asyncio.get_running_loop()
        last_error = None
        
        for i in range(max(1, int(attempts))):
            try:
                fn = partial(self._make_request, query, timeout=timeout, cache_ttl=float(cache_ttl or 0))
                return await loop.run_in_executor(None, fn)
            except Exception as e:
                last_error = e
                await asyncio.sleep(0.5 * (2 ** i))
        
        if last_error:
            raise last_error
        return {}

    def _to_utc(self, dt: Optional[datetime]) -> Optional[datetime]:
        """Convert datetime to naive UTC."""
        if dt is None:
            return None
        
        try:
            base = dt
            if base.tzinfo is None and self.local_tz:
                base = base.replace(tzinfo=self.local_tz)
            
            if self.utc_tz:
                return base.astimezone(self.utc_tz).replace(tzinfo=None)
            return base.replace(tzinfo=None)
        except Exception:
            return dt.replace(tzinfo=None) if dt else None

    def _parse_entity_identifier(self, identifier: Union[int, str]) -> tuple[Optional[int], Optional[str], Optional[str]]:
        """Parse entity identifier into (id, name, type)."""
        if isinstance(identifier, int):
            return identifier, None, None
        
        s = str(identifier).strip()
        if not s:
            return None, None, None

        # Extract ID from URLs
        m = re.search(r"(?:nation_id=|alliance_id=|id=)(\d+)", s)
        if m:
            entity_id = int(m.group(1))
            if "nation_id=" in s or ("id=" in s and "alliance_id=" not in s):
                return entity_id, None, 'nation'
            elif "alliance_id=" in s:
                return entity_id, None, 'alliance'
            return entity_id, None, None

        # Handle numeric strings
        if s.isdigit():
            return int(s), None, None

        # Determine type based on content
        if ' ' in s:
            if ' of ' in s.lower() and s.count(' ') > 1:
                return None, s, 'leader_name'
            return None, s, 'nation_name'
        
        return None, s, None

    async def _resolve_entity_from_api(self, identifier: str, entity_type: Optional[str] = None) -> tuple[Optional[int], Optional[str], Optional[str]]:
        """Resolve entity from API with caching."""
        if not identifier:
            return None, None, None

        cache_key = f"resolve:{identifier.lower()}:{entity_type or 'any'}"
        
        # Check cache first
        cached = self._get_cache('resolve', cache_key)
        if cached:
            return cached

        item = None
        resolved_type = entity_type

        # Try different resolution strategies
        if entity_type == 'alliance':
            item = await self._resolve_alliance(identifier)
            if item: resolved_type = 'alliance'
        elif entity_type in ('nation_name', 'leader_name'):
            method = 'get_nation_by_name' if entity_type == 'nation_name' else 'get_nation_by_leader'
            item = await getattr(self, method)(identifier)
            if item: resolved_type = 'nation'
        elif entity_type == 'nation':
            if str(identifier).isdigit():
                item = await self.get_nation_by_id(identifier)
            if not item:
                item = await self._resolve_nation(identifier)
            if item: resolved_type = 'nation'
        else:
            # Try both alliance and nation
            item = await self._resolve_alliance(identifier)
            if not item:
                item = await self._resolve_nation(identifier)
            if item:
                resolved_type = 'alliance' if item.get('acronym') else 'nation'

        if item:
            eid = int(item.get('id') or item.get('nation_id') or 0)
            name = item.get('name') or item.get('nation_name') or identifier
            result = (eid, name, resolved_type)
            self._set_cache('resolve', cache_key, result)
            return result

        # Cache negative results
        self._set_cache('resolve', cache_key, (None, None, None))
        return None, None, None

    async def _resolve_nation(self, identifier: Union[str, int]) -> Optional[Dict[str, Any]]:
        """Resolve nation by ID, name, or leader."""
        if isinstance(identifier, int):
            return await self.get_nation_by_id(str(identifier))
        
        # Try name first
        nation = await self.get_nation_by_name(identifier)
        if nation:
            return nation
        
        # Try leader name
        return await self.get_nation_by_leader(identifier)

    async def resolve_alliance(self, identifier: Union[str, int]) -> Optional[Dict[str, Any]]:
        """Resolve alliance by ID, name, or acronym."""
        try:
            raw = str(identifier).strip()
            if not raw:
                return None

            # Check cache first
            cache_key = f"alliance:{raw.lower()}"
            cached = self._get_cache('resolve', cache_key)
            if cached:
                return cached

            # Try to parse ID
            aid = None
            m = re.search(r"id\s*=\s*(\d+)", raw)
            if m:
                aid = int(m.group(1))
            elif raw.isdigit():
                aid = int(raw)

            # Look up by ID if available
            if aid:
                query = f"""
                query {{
                  alliances(id: {aid}) {{
                    data {{ id name acronym color }}
                  }}
                }}
                """
                data = await self._request_with_retries(query, timeout=30, cache_ttl=3600)
                items = ((((data or {}).get('data') or {}).get('alliances') or {}).get('data') or [])
                if items:
                    result = {
                        'id': str(items[0].get('id')),
                        'name': items[0].get('name') or '',
                        'acronym': items[0].get('acronym') or '',
                        'color': items[0].get('color') or ''
                    }
                    self._set_cache('resolve', cache_key, result)
                    return result

            # Try name lookup
            safe = raw.replace('"', '\\"')
            query = f"""
            query {{
              alliances(name: "{safe}") {{
                data {{ id name acronym }}
              }}
            }}
            """
            data = await self._request_with_retries(query, timeout=30, cache_ttl=3600)
            items = (((data or {}).get('data') or {}).get('alliances') or {}).get('data') or []
            
            if items:
                result = items[0]
                self._set_cache('resolve', cache_key, result)
                return result

            return None
        except Exception as e:
            self.logger.warning(f"Failed to resolve alliance '{identifier}': {e}")
            return None

    async def _resolve_entities_batched(
        self, 
        identifiers: Optional[Union[int, str, List[Union[int, str]]]], 
        expected_type: Optional[str] = None
    ) -> List[int]:
        """Resolve multiple entity identifiers to IDs with batching."""
        if not identifiers:
            return []

        if not isinstance(identifiers, list):
            identifiers = [identifiers]

        resolved_ids = set()
        batch_tasks = []

        # First pass: parse identifiers and batch by type
        for ident in identifiers:
            s_ident = str(ident).strip()
            if not s_ident:
                continue

            parsed_id, parsed_name, parsed_type = self._parse_entity_identifier(s_ident)

            if parsed_id and (expected_type is None or parsed_type is None or parsed_type == expected_type):
                resolved_ids.add(parsed_id)
            elif parsed_type in ('nation_name', 'leader_name'):
                batch_tasks.append(('nation', parsed_name or s_ident))
            elif parsed_type == 'alliance':
                batch_tasks.append(('alliance', parsed_name or s_ident))
            elif parsed_type is None:
                # Try both types
                batch_tasks.append(('nation', s_ident))
                batch_tasks.append(('alliance', s_ident))

        # Batch resolve names
        for entity_type, name in batch_tasks:
            if entity_type == 'nation':
                result = await self._resolve_nation_batched([name])
                resolved_ids.update(result)
            else:
                result = await self._resolve_alliance_batched([name])
                resolved_ids.update(result)

        return sorted(list(resolved_ids))

    async def _resolve_nation_batched(self, names: List[str]) -> List[int]:
        """Batch resolve nation names to IDs."""
        if not names:
            return []

        try:
            # Build aliased query
            aliases = {f"n{i}": name for i, name in enumerate(names)}
            blocks = [f'{alias}: nations(name: "{name}", first: 1) {{ data {{ id nation_name }} }}' 
                     for alias, name in aliases.items()]
            query = "query { " + " ".join(blocks) + " }"
            
            data = await self._request_with_retries(query, timeout=30, cache_ttl=3600)
            results = data.get('data', {})
            
            ids = []
            for alias, name in aliases.items():
                nation_data = results.get(alias, {}).get('data', [])
                if nation_data:
                    ids.append(nation_data[0].get('id'))
            
            return [id for id in ids if id]
        except Exception as e:
            self.logger.error(f"Batch nation resolution failed: {e}")
            return []

    async def _resolve_alliance_batched(self, names: List[str]) -> List[int]:
        """Batch resolve alliance names to IDs."""
        if not names:
            return []

        try:
            # Build aliased query
            aliases = {f"a{i}": name for i, name in enumerate(names)}
            blocks = [f'{alias}: alliances(name: "{name}", first: 1) {{ data {{ id name acronym }} }}' 
                     for alias, name in aliases.items()]
            query = "query { " + " ".join(blocks) + " }"
            
            data = await self._request_with_retries(query, timeout=30, cache_ttl=3600)
            results = data.get('data', {})
            
            ids = []
            for alias, name in aliases.items():
                alliance_data = results.get(alias, {}).get('data', [])
                if alliance_data:
                    ids.append(alliance_data[0].get('id'))
            
            return [id for id in ids if id]
        except Exception as e:
            self.logger.error(f"Batch alliance resolution failed: {e}")
            return []

    def _nation_fields(self) -> str:
        """Get standard nation fields for GraphQL queries."""
        return (
            "id alliance_position nation_name leader_name continent color flag discord discord_id "
            "war_policy domestic_policy social_policy government_type economic_policy update_tz "
            "vacation_mode_turns beige_turns tax_id num_cities score population "
            "gross_national_income gross_domestic_product espionage_available date last_active "
            "turns_since_last_city turns_since_last_project soldiers tanks aircraft ships missiles nukes spies "
            "money coal oil uranium iron bauxite lead gasoline munitions steel aluminum food wars_won wars_lost "
            "offensive_wars_count defensive_wars_count soldier_casualties tank_casualties aircraft_casualties "
            "ship_casualties missile_casualties missile_kills nuke_casualties nuke_kills spy_casualties spy_kills "
            "spy_attacks soldier_kills tank_kills aircraft_kills ship_kills money_looted total_infrastructure_destroyed "
            "total_infrastructure_lost projects project_bits alliance_id alliance_seniority alliance_join_date credits "
            "credits_redeemed_this_month vip commendations denouncements cities_discount activity_center advanced_engineering_corps "
            "advanced_pirate_economy arable_land_agency arms_stockpile bauxite_works bureau_of_domestic_affairs center_for_civil_engineering "
            "clinical_research_center emergency_gasoline_reserve fallout_shelter government_support_agency green_technologies guiding_satellite "
            "central_intelligence_agency international_trade_center iron_dome iron_works moon_landing mars_landing mass_irrigation "
            "military_doctrine military_research_center military_salvage missile_launch_pad nuclear_launch_facility nuclear_research_facility "
            "pirate_economy propaganda_bureau recycling_initiative research_and_development_center space_program specialized_police_training_program "
            "spy_satellite surveillance_network telecommunications_satellite uranium_enrichment_program vital_defense_system "
            "military_research { ground_capacity air_capacity naval_capacity ground_cost air_cost naval_cost } "
            "alliance { id name acronym flag tax_brackets { id tax_rate } } "
            "cities { id name date infrastructure land powered nuke_date oil_power wind_power coal_power nuclear_power coal_mine oil_well uranium_mine lead_mine iron_mine bauxite_mine oil_refinery aluminum_refinery steel_mill munitions_factory factory farm police_station hospital recycling_center subway supermarket bank shopping_mall stadium barracks hangar drydock }"
        )

    def _war_fields(self) -> str:
        """Get standard war fields for GraphQL queries."""
        return (
            "id date war_type turns_left turns_since_declaration "
            "attacker_id defender_id attacker_alliance_id defender_alliance_id "
            "min_score max_score min_cities max_cities "
            "min_infra max_infra min_land max_land min_pop max_pop "
            "min_gnp max_gnp min_tech max_tech "
            "min_offensive_wars max_offensive_wars min_defensive_wars max_defensive_wars "
            "min_wars_won max_wars_won min_wars_lost max_wars_lost "
            "min_money max_money min_food max_food min_oil max_oil "
            "min_uranium max_uranium min_coal max_coal min_iron max_iron "
            "min_bauxite max_bauxite min_lead max_lead min_aluminum max_aluminum "
            "min_steel max_steel min_gasoline max_gasoline min_munitions max_munitions "
            "min_credits max_credits min_soldiers max_soldiers min_tanks max_tanks "
            "min_aircraft max_aircraft min_ships max_ships min_missiles max_missiles "
            "min_nukes max_nukes min_spies max_spies "
            "attacker_munitions_spent attacker_gasoline_spent attacker_money_spent "
            "defender_munitions_spent defender_gasoline_spent defender_money_spent "
            "total_munitions_spent total_gasoline_spent total_money_spent "
            "attacker_soldiers_killed attacker_tanks_killed attacker_aircraft_killed "
            "attacker_ships_killed attacker_missiles_fired attacker_nukes_fired "
            "attacker_spies_killed defender_soldiers_killed defender_tanks_killed "
            "defender_aircraft_killed defender_ships_killed defender_missiles_fired "
            "defender_nukes_fired defender_spies_killed "
            "attacker_score defender_score "
            "turns_since_peace "
            "attacker_alliance { id name acronym } "
            "defender_alliance { id name acronym } "
            "attacker_nation { id nation_name leader_name } "
            "defender_nation { id nation_name leader_name } "
        )

    def _normalize_nation(self, nation: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize nation data structure."""
        try:
            # Normalize alliance data
            alliance = nation.get("alliance") or {}
            if isinstance(alliance, dict):
                for key in ["name", "acronym", "flag"]:
                    if alliance.get(key) is not None:
                        nation[f"alliance_{key}"] = alliance.get(key)
                if nation.get("alliance_id") in (None, 0, ""):
                    nation["alliance_id"] = alliance.get("id")
        except Exception:
            pass

        # Normalize cities data
        try:
            cities = nation.get("cities") or []
            if isinstance(cities, list):
                for city in cities:
                    if isinstance(city, dict):
                        # Handle gasoline_refinery alias
                        if "gasoline_refinery" not in city and "gasrefinery" in city:
                            city["gasoline_refinery"] = city.get("gasrefinery")
                        
                        # Convert improvement fields to improvements dict
                        improvements = {}
                        improvement_fields = [
                            'oil_power', 'wind_power', 'coal_power', 'nuclear_power',
                            'coal_mine', 'oil_well', 'uranium_mine', 'lead_mine', 
                            'iron_mine', 'bauxite_mine', 'oil_refinery',
                            'aluminum_refinery', 'steel_mill', 'munitions_factory', 
                            'factory', 'farm', 'police_station', 'hospital', 
                            'recycling_center', 'subway', 'supermarket', 'bank', 
                            'shopping_mall', 'stadium', 'barracks', 'hangar', 'drydock'
                        ]
                        
                        for field in improvement_fields:
                            if field in city and isinstance(city[field], (int, float)):
                                improvements[field] = city[field]
                        
                        if improvements:
                            city['improvements'] = improvements
        except Exception:
            pass

        return nation

    async def search_nations(self, text: str, max_results: int = 25) -> Optional[List[Dict[str, Any]]]:
        """Search nations by name or leader."""
        try:
            escaped = str(text).replace('"', '\\"')
            query = f"""
            query {{
              nations(search: "{escaped}", first: {max(1, int(max_results))}) {{
                data {{ id nation_name leader_name }}
              }}
            }}
            """
            data = await self._request_with_retries(query, timeout=30)
            items = (((data or {}).get("data") or {}).get("nations") or {}).get("data") or []
            
            return [{
                "id": item.get("id"),
                "nation_name": item.get("nation_name"),
                "leader_name": item.get("leader_name"),
            } for item in items[:max_results]]
        except Exception:
            return None

    async def search_alliances(self, text: str, max_results: int = 25) -> Optional[List[Dict[str, Any]]]:
        """Search alliances by name or acronym."""
        try:
            escaped = str(text).replace('"', '\\"')
            query = f"""
            query {{
              alliances(search: "{escaped}", first: {max(1, int(max_results))}) {{
                data {{ id name acronym flag }}
              }}
            }}
            """
            data = await self._request_with_retries(query, timeout=30)
            items = (((data or {}).get("data") or {}).get("alliances") or {}).get("data") or []
            
            return [{
                "id": item.get("id"),
                "name": item.get("name"),
                "acronym": item.get("acronym"),
                "flag": item.get("flag"),
            } for item in items[:max_results]]
        except Exception:
            return None

    async def get_nation_by_id(self, nation_id: str) -> Optional[Dict[str, Any]]:
        """Get nation by ID with comprehensive fields."""
        self.logger.debug(f"get_nation_by_id called with nation_id: {nation_id}")
        try:
            query = f"""
            query {{
              nations(id: {nation_id}) {{
                data {{ {self._nation_fields()} }}
              }}
            }}
            """
            data = await self._request_with_retries(query, timeout=30)
            nations = data.get('data', {}).get('nations', {}).get('data', [])
            result = self._normalize_nation(nations[0]) if nations else None
            self.logger.debug(f"get_nation_by_id result: {result}")
            return result
        except Exception as e:
            self.logger.error(f"Error retrieving nation {nation_id}: {e}")
            return None

    async def get_nation_by_name(self, nation_name: str) -> Optional[Dict[str, Any]]:
        """Get nation by name with comprehensive fields."""
        self.logger.debug(f"get_nation_by_name called with nation_name: {nation_name}")
        try:
            escaped = nation_name.replace('"', '\\"')
            query = f"""
            query {{
              nations(first: 1, nation_name: "{escaped}") {{
                data {{ {self._nation_fields()} }}
              }}
            }}
            """
            data = await self._request_with_retries(query, timeout=30)
            nations = data.get('data', {}).get('nations', {}).get('data', [])
            result = self._normalize_nation(nations[0]) if nations else None
            self.logger.debug(f"get_nation_by_name result: {result}")
            return result
        except Exception as e:
            self.logger.error(f"Error retrieving nation '{nation_name}': {e}")
            return None

    async def get_nation_by_leader(self, leader_name: str) -> Optional[Dict[str, Any]]:
        """Get nation by leader name with comprehensive fields."""
        self.logger.debug(f"get_nation_by_leader called with leader_name: {leader_name}")
        try:
            escaped = leader_name.replace('"', '\\"')
            query = f"""
            query {{
              nations(first: 1, leader_name: "{escaped}") {{
                data {{ {self._nation_fields()} }}
              }}
            }}
            """
            data = await self._request_with_retries(query, timeout=30)
            nations = data.get('data', {}).get('nations', {}).get('data', [])
            result = self._normalize_nation(nations[0]) if nations else None
            self.logger.debug(f"get_nation_by_leader result: {result}")
            return result
        except Exception as e:
            self.logger.error(f"Error retrieving nation with leader '{leader_name}': {e}")
            return None

    async def get_alliance_nations(self, alliance_id: str, bot=None, force_refresh: bool = False) -> Optional[List[Dict[str, Any]]]:
        """Get all nations from an alliance with pagination."""
        self.logger.debug(f"get_alliance_nations called for alliance_id: {alliance_id}, force_refresh: {force_refresh}")
        try:
            # Prevent infinite recursion
            cache_key = f"alliance_nations_{alliance_id}"
            if cache_key in self._processing['alliances']:
                return self._get_cache('kv', cache_key, [])

            self._processing['alliances'].add(cache_key)

            # Check cache first
            if not force_refresh:
                cached = self._get_cache('kv', cache_key)
                if cached:
                    if bot:
                        await self._fetch_discord_usernames(cached, bot)
                    self.logger.debug(f"Returning cached alliance nations for {alliance_id}")
                    return cached

            # Fetch with pagination
            nations = []
            page = 1
            while True:
                query = f"""
                query {{
                  nations(alliance_id: {alliance_id}, first: 500, page: {page}) {{
                    paginatorInfo {{ currentPage lastPage hasMorePages }}
                    data {{ {self._nation_fields()} }}
                  }}
                }}
                """
                data = await self._request_with_retries(query, timeout=30)
                block = data.get('data', {}).get('nations', {})
                items = block.get('data', [])
                
                if not items:
                    break
                
                nations.extend([self._normalize_nation(n) for n in items])
                
                # Check if we've reached the last page
                paginator = block.get('paginatorInfo', {})
                if not paginator.get('hasMorePages', False):
                    break
                
                page += 1

            # Cache the result
            self._set_cache('kv', cache_key, nations)
            
            # Fetch Discord usernames if bot provided
            if bot and nations:
                await self._fetch_discord_usernames(nations, bot)

            self._processing['alliances'].discard(cache_key)
            self.logger.debug(f"Successfully fetched and cached {len(nations)} alliance nations for {alliance_id}")
            return nations

        except Exception as e:
            self.logger.error(f"Error retrieving alliance nations: {e}")
            self._processing['alliances'].discard(cache_key)
            return None

    async def get_alliance_tax_bracket(self, alliance_id: str, tax_bracket_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific tax bracket for an alliance."""
        try:
            query = f"""
            query {{
              alliances(id: {alliance_id}) {{
                data {{
                  tax_brackets(id: [{tax_bracket_id}]) {{
                    id
                    tax_rate
                  }}
                }}
              }}
            }}
            """
            data = await self._request_with_retries(query, timeout=15, cache_ttl=3600)
            alliances_data = data.get('data', {}).get('alliances', {}).get('data', [])
            if not alliances_data:
                return None

            brackets = alliances_data[0].get('tax_brackets', [])
            if brackets:
                return brackets[0]
            return None
        except Exception as e:
            self.logger.error(f"Error getting tax bracket {tax_bracket_id} for alliance {alliance_id}: {e}")
            return None

    async def _fetch_discord_usernames(self, nations: List[Dict[str, Any]], bot) -> None:
        """Fetch Discord usernames for nations with Discord IDs."""
        sem = asyncio.Semaphore(10)

        async def _process_nation(nation):
            discord_id = nation.get('discord_id', '')
            if not discord_id or not str(discord_id).strip():
                return False

            try:
                discord_id_int = int(discord_id)
                user = bot.get_user(discord_id_int)
                if user:
                    nation['discord_username'] = user.name
                    nation['discord_display_name'] = user.display_name
                    return True
                
                async with sem:
                    try:
                        user = await bot.fetch_user(discord_id_int)
                        if user:
                            nation['discord_username'] = user.name
                            nation['discord_display_name'] = user.display_name
                            return True
                    except:
                        pass
            except (ValueError, TypeError):
                pass
            return False

        results = await asyncio.gather(*[_process_nation(n) for n in nations])
        discord_count = sum(1 for r in results if r)
        
        if discord_count > 0:
            self.logger.info(f"Fetched Discord info for {discord_count} nations")

    async def get_alliance_treaties(
        self,
        alliance_id: str,
        limit: Optional[int] = None,
        force_refresh: bool = False,
        cutoff_dt: Optional[datetime] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """Get treaties for an alliance."""
        try:
            cache_key = f"treaties_{alliance_id}"

            # Check cache first
            if not force_refresh:
                cached = self._get_cache('kv', cache_key)
                if cached:
                    return cached

            # Build query
            limit_arg = f"(limit: {int(limit)})" if limit else ""
            query = f"""
            query {{
              alliances(id: {alliance_id}) {{
                data {{
                  id name acronym
                  treaties{limit_arg} {{
                    id date treaty_type treaty_url turns_left
                    alliance1_id alliance2_id approved
                    alliance1 {{ id name acronym flag }}
                    alliance2 {{ id name acronym flag }}
                  }}
                }}
              }}
            }}
            """

            data = await self._request_with_retries(query, timeout=30)
            treaties = (data.get('data', {}).get('alliances', {}).get('data', [{}])[0] or {}).get('treaties') or []

            # Apply cutoff filter
            if cutoff_dt:
                cutoff_utc = self._to_utc(cutoff_dt)
                if cutoff_utc:
                    def _parse_dt(val):
                        try:
                            if isinstance(val, datetime):
                                return val
                            if isinstance(val, str):
                                return datetime.fromisoformat(val.strip().replace('Z', ''))
                        except:
                            return None
                        return None

                    treaties = [t for t in treaties if (_parse_dt(t.get('date')) or datetime.min) >= cutoff_utc]

            # Apply limit
            if limit and len(treaties) > limit:
                treaties = treaties[:limit]

            # Cache result
            self._set_cache('kv', cache_key, treaties)
            return treaties

        except Exception as e:
            self.logger.error(f"Error retrieving treaties: {e}")
            return None

    async def get_alliances_treaties(
        self,
        alliance_ids: List[str],
        limit: Optional[int] = None,
        force_refresh: bool = False,
        cutoff_dt: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Get treaties for multiple alliances in a single batched query."""
        if not alliance_ids:
            return []
        
        try:
            limit_arg = f"(limit: {int(limit)})" if limit else ""
            
            aliases = {f"a{aid}": aid for aid in alliance_ids}
            blocks = [
                f"""
                {alias}: alliances(id: {aid}) {{
                  data {{
                    treaties{limit_arg} {{
                      id date treaty_type treaty_url turns_left
                      alliance1_id alliance2_id approved
                      alliance1 {{ id name acronym flag }}
                      alliance2 {{ id name acronym flag }}
                    }}
                  }}
                }}
                """
                for alias, aid in aliases.items()
            ]
            
            query = "query { " + " ".join(blocks) + " }"

            data = await self._request_with_retries(query, timeout=30)
            
            all_treaties = []
            results = data.get('data', {})
            
            for alias in aliases.keys():
                alliance_data_list = results.get(alias, {}).get('data', [])
                if alliance_data_list and isinstance(alliance_data_list, list) and alliance_data_list[0]:
                    treaties = (alliance_data_list[0] or {}).get('treaties') or []
                    all_treaties.extend(treaties)

            seen_treaty_ids = set()
            unique_treaties = []
            for treaty in all_treaties:
                treaty_id = treaty.get('id')
                if treaty_id and treaty_id not in seen_treaty_ids:
                    unique_treaties.append(treaty)
                    seen_treaty_ids.add(treaty_id)
            
            final_treaties = unique_treaties
            if cutoff_dt:
                cutoff_utc = self._to_utc(cutoff_dt)
                if cutoff_utc:
                    def _parse_dt(val):
                        try:
                            if isinstance(val, datetime):
                                return val
                            if isinstance(val, str):
                                return datetime.fromisoformat(val.strip().replace('Z', ''))
                        except:
                            return None
                        return None

                    final_treaties = [t for t in final_treaties if (_parse_dt(t.get('date')) or datetime.min) >= cutoff_utc]

            return final_treaties

        except Exception as e:
            self.logger.error(f"Error retrieving treaties for alliances {alliance_ids}: {e}")
            return []

    async def get_game_info(self, request_timeout: int = 30) -> Optional[GameInfo]:
        """Get game information like date, radiation, and city averages."""
        try:
            query = """
            query {
              gameInfo: game_info {
                game_date
                city_average
                radiation {
                  global north_america south_america europe africa asia australia antarctica
                }
              }
            }
            """
            data = await self._request_with_retries(query, timeout=request_timeout, cache_ttl=3600)
            
            gi = (data.get('data') or {}).get('gameInfo') or (data.get('data') or {}).get('game') or {}
            
            # Extract radiation data
            radiation_data = gi.get("radiation", {})
            if isinstance(radiation_data, dict):
                radiation = Radiation(
                    global_=float(radiation_data.get("global", radiation_data.get("global_", 0.0))),
                    north_america=float(radiation_data.get("north_america", 0.0)),
                    south_america=float(radiation_data.get("south_america", 0.0)),
                    europe=float(radiation_data.get("europe", 0.0)),
                    africa=float(radiation_data.get("africa", 0.0)),
                    asia=float(radiation_data.get("asia", 0.0)),
                    australia=float(radiation_data.get("australia", 0.0)),
                    antarctica=float(radiation_data.get("antarctica", 0.0))
                )
            else:
                # Fallback if radiation is just a single value
                radiation = Radiation(
                    global_=float(radiation_data or 0.0),
                    north_america=0.0,
                    south_america=0.0,
                    europe=0.0,
                    africa=0.0,
                    asia=0.0,
                    australia=0.0,
                    antarctica=0.0
                )
            
            return GameInfo(
                game_date=gi.get("game_date") or gi.get("date") or "Unknown",
                city_average=float(gi.get("city_average", 0.0)) if gi.get("city_average") is not None else 0.0,
                radiation=radiation
            )
        except Exception as e:
            self.logger.error(f"Error getting game info: {e}")
            return None

    async def get_trade_resource_values(self, resources: Optional[List[str]] = None) -> Optional[List[Dict[str, Any]]]:
        """Get trade resource values with caching."""
        try:
            # Check cache first
            if self._is_cache_valid('trade', 'resources'):
                cached = self._get_cache('trade', 'resources')
                if resources:
                    requested = {r.upper() for r in resources}
                    return [r for r in cached if r['resource'] in requested]
                return cached

            # Fetch fresh data
            query = """
            query {
              top_trade_info {
                resources {
                  resource average_price
                  best_buy_offer { price }
                  best_sell_offer { price }
                }
              }
            }
            """
            data = await self._request_with_retries(query, timeout=30, cache_ttl=300)
            
            resource_list = (data.get('data') or {}).get('top_trade_info', {}).get('resources') or []
            
            # Process and cache
            result = []
            for resource in resource_list:
                result.append({
                    "resource": resource['resource'],
                    "average_price": float(resource.get('average_price', 0)),
                    "best_buy_offer": {
                        "price": float(resource.get('best_buy_offer', {}).get('price', 0)),
                        "quantity": int(resource.get('best_buy_offer', {}).get('quantity', 0)),
                    },
                    "best_sell_offer": {
                        "price": float(resource.get('best_sell_offer', {}).get('price', 0)),
                        "quantity": int(resource.get('best_sell_offer', {}).get('quantity', 0)),
                    },
                })
            
            self._set_cache('trade', 'resources', result)
            
            # Filter if specific resources requested
            if resources:
                requested = {r.upper() for r in resources}
                return [r for r in result if r['resource'] in requested]
            
            return result
        except Exception as e:
            self.logger.error(f"Error getting trade values: {e}")
            return None

    async def get_nations_by_color(self, color: str, first: int = 100) -> Optional[List[Dict[str, Any]]]:
        """Get nations filtered by color."""
        try:
            query = f"""
            query {{
              nations(color: "{color}", first: {first}) {{
                paginatorInfo {{ currentPage lastPage hasMorePages }}
                data {{
                  id nation_name leader_name color score population num_cities
                  last_active gross_national_income gross_domestic_product
                }}
              }}
            }}
            """
            data = await self._request_with_retries(query, timeout=30)
            nations_data = data.get('data', {}).get('nations', {})
            nations_list = nations_data.get('data', [])
            
            if not nations_list:
                return []
            
            return [self._normalize_nation(n) for n in nations_list]
        except Exception as e:
            self.logger.error(f"Error fetching nations by color {color}: {e}")
            return None

    async def get_color_info(self, color: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """Get color bloc information from API."""
        try:
            query = """
            query {
              colors {
                color bloc_name turn_bonus
              }
            }
            """
            data = await self._request_with_retries(query, timeout=30, cache_ttl=3600)
            colors = data.get('data', {}).get('colors', [])
            
            if not colors:
                return None
            
            if color:
                color_lower = color.lower()
                for c in colors:
                    if c['color'].lower() == color_lower:
                        return [{
                            'color': c['color'],
                            'bloc_name': c['bloc_name'],
                            'turn_bonus': float(c['turn_bonus'])
                        }]
                return None
            
            return [{
                'color': c['color'],
                'bloc_name': c['bloc_name'],
                'turn_bonus': float(c['turn_bonus'])
            } for c in colors]
        except Exception as e:
            self.logger.error(f"Error fetching color info: {e}")
            return None

    async def get_projects_data(self, alliance_id: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Get projects data for an alliance."""
        try:
            cache_key = f"projects_{alliance_id}"
            if cache_key in self._processing['projects']:
                return self._get_cache('kv', cache_key, {})

            self._processing['projects'].add(cache_key)

            nations = await self.get_alliance_nations(alliance_id, force_refresh=force_refresh)
            if not nations:
                self._processing['projects'].discard(cache_key)
                return {}

            project_counts = {}
            for nation in nations:
                for project in nation.get('projects', []):
                    project_counts[project] = project_counts.get(project, 0) + 1

            result = {
                'total_nations': len(nations),
                'project_counts': project_counts
            }

            self._set_cache('kv', cache_key, result)
            self._processing['projects'].discard(cache_key)
            return result
        except Exception as e:
            self.logger.error(f"Error processing projects: {e}")
            self._processing['projects'].discard(cache_key)
            return {}

    async def get_improvements_data(self, alliance_id: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Get improvements data for an alliance."""
        try:
            cache_key = f"improvements_{alliance_id}"
            if cache_key in self._processing['improvements']:
                return self._get_cache('kv', cache_key, {})

            self._processing['improvements'].add(cache_key)

            nations = await self.get_alliance_nations(alliance_id, force_refresh=force_refresh)
            if not nations:
                self._processing['improvements'].discard(cache_key)
                return {}

            improvements_counts = {}
            for nation in nations:
                for city in nation.get('cities', []):
                    for improvement, count in city.items():
                        if improvement not in ['id', 'name', 'date', 'infrastructure', 'land', 'powered', 'nuke_date']:
                            improvements_counts[improvement] = improvements_counts.get(improvement, 0) + count

            result = {
                'total_nations': len(nations),
                'improvements_counts': improvements_counts
            }

            self._set_cache('kv', cache_key, result)
            self._processing['improvements'].discard(cache_key)
            return result
        except Exception as e:
            self.logger.error(f"Error processing improvements: {e}")
            self._processing['improvements'].discard(cache_key)
            return {}

    async def get_cache_info(self) -> Dict[str, Any]:
        """Get cache information and statistics."""
        try:
            info = []
            now = time.monotonic()
            
            for key, value in self._cache['kv'].items():
                if not isinstance(key, str) or not key.startswith('alliance_'):
                    continue
                
                try:
                    ttl_exp = self._cache_expiry.get(key, 0.0)
                    ttl_remaining = max(0, int(ttl_exp - now)) if ttl_exp > 0 else 0
                    alliance_id = (value or {}).get('alliance_id') or key.replace('alliance_', '')
                    count = len((value or {}).get('nations') or []) if isinstance(value, dict) else 0
                    
                    info.append({
                        'key': key,
                        'alliance_id': str(alliance_id),
                        'count': count,
                        'ttl_remaining_seconds': ttl_remaining,
                    })
                except Exception:
                    continue

            return {
                'total_cached_alliances': len(info),
                'cached_alliances': info,
                'cache_status': f"Active, TTL={self.cache_ttl_seconds}s",
            }
        except Exception:
            return {
                'total_cached_alliances': 0,
                'cached_alliances': [],
                'cache_status': 'Error',
            }

    async def get_treasures(self) -> Optional[List[Dict[str, Any]]]:
        """Get all available treasures."""
        try:
            query = """ 
            query {
              treasures {
                name
                color
                continent
                bonus
                spawn_date
                nation_id
                nation {
                  id
                  nation_name
                  last_active
                  vacation_mode_turns
                  score
                }
              }
            }
            """
            data = await self._request_with_retries(query, timeout=30, cache_ttl=300)
            treasures = (data.get('data') or {}).get('treasures') or []
            return treasures
        except Exception as e:
            self.logger.error(f"Error getting treasures: {e}")
            return None

    async def get_bounties(self, min_amount: Optional[float] = None, max_amount: Optional[float] = None, first: int = 50, page: int = 1) -> Optional[Dict[str, Any]]:
        """Get a paginated list of bounties with optional filters."""
        try:
            filters = []
            if min_amount is not None:
                filters.append(f"min_amount: {min_amount}")
            if max_amount is not None:
                filters.append(f"max_amount: {max_amount}")
            
            filter_str = ", ".join(filters)

            query = f""" 
            query {{
              bounties(first: {first}, page: {page}, {filter_str}) {{
                paginatorInfo {{
                  currentPage
                  lastPage
                  hasMorePages
                  total
                }}
                data {{
                  id
                  date
                  nation_id
                  nation {{
                    nation_name
                    last_active
                    vacation_mode_turns
                    score
                  }}
                  amount
                  type
                }}
              }}
            }}
            """
            data = await self._request_with_retries(query, timeout=30, cache_ttl=60)
            bounties_paginator = (data.get('data') or {}).get('bounties')
            return bounties_paginator
        except Exception as e:
            self.logger.error(f"Error getting bounties: {e}")
            return None

    async def get_treasure_trades(self) -> Optional[List[Dict[str, Any]]]:
        """Fetches all treasure trades from all pages within the last month."""
        all_trades = []
        current_page = 1
        one_month_ago = datetime.now(timezone.utc) - timedelta(days=30)

        while True:
            try:
                query = f"""
                query {{
                  treasure_trades(page: {current_page}, first: 50, orderBy: {{ column: ID, order: DESC }}) {{
                    paginatorInfo {{
                      hasMorePages
                    }}
                    data {{
                      id
                      offer_date
                      accept_date
                      sender_id
                      sender {{
                        id
                        nation_name
                      }}
                      receiver_id
                      receiver {{
                        id
                        nation_name
                      }}
                      buying
                      selling
                      treasure
                      money
                      accepted
                      rejected
                      seller_cancelled
                    }}
                  }}
                }}
                """
                
                data = await self._request_with_retries(query, timeout=30, cache_ttl=60)
                paginator = data.get('data', {}).get('treasure_trades')
                
                if not paginator or not paginator.get('data'):
                    break

                trades_page = paginator['data']
                all_trades.extend(trades_page)

                # Check if the last trade is older than a month
                last_trade_date_str = trades_page[-1].get('offer_date')
                if last_trade_date_str:
                    last_trade_date = datetime.fromisoformat(last_trade_date_str.replace('Z', '+00:00'))
                    if last_trade_date < one_month_ago:
                        break # Stop if we've gone back far enough
                
                if not paginator.get('paginatorInfo', {}).get('hasMorePages'):
                    break
                current_page += 1
            except Exception as e:
                self.logger.error(f"Error getting treasure trades: {e}")
                break
        return all_trades

    async def get_nation_resource_stats(self, before: Optional[str] = None, after: Optional[str] = None, 
                                       order_by: Optional[List[str]] = None) -> Optional[List[NationResourceStat]]:
        """Get nation resource statistics for a given time window."""
        try:
            # Build query arguments - the API doesn't support before/after parameters
            # It returns all historical data, so we'll just get everything
            query = """
            query {
              nation_resource_stats {
                date
                money
                food
                steel
                aluminum
                gasoline
                munitions
                uranium
                coal
                oil
                iron
                bauxite
                lead
              }
            }
            """
            
            data = await self._request_with_retries(query, timeout=30, cache_ttl=300)
            resource_stats = (data.get('data') or {}).get('nation_resource_stats')
            
            if resource_stats:
                return [stat for stat in resource_stats if stat]
            return None
        except Exception as e:
            self.logger.error(f"Error getting nation resource stats: {e}")
            return None

# Convenience functions
def create_query_instance(api_key: Optional[str] = None, logger: Optional[logging.Logger] = None) -> PNWAPIQuery:
    """Create a new PNWAPIQuery instance."""
    return PNWAPIQuery(api_key=api_key, logger=logger)

async def get_color_info(color: Optional[str] = None, api_key: Optional[str] = None, logger: Optional[logging.Logger] = None) -> Optional[List[Dict[str, Any]]]:
    """Convenience function to get color bloc information."""
    query_instance = create_query_instance(api_key=api_key, logger=logger)
    return await query_instance.get_color_info(color=color)