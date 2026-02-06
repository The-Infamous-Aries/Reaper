import requests
import logging
from typing import List, Dict, Optional, Any, Union
import os
import json
import sys
import time
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from functools import partial
# ZoneInfo fallback for Python < 3.9
try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    try:
        from backports.zoneinfo import ZoneInfo  # type: ignore
    except Exception:  # pragma: no cover
        ZoneInfo = None  # type: ignore

# Add parent directory to path for config import
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
try:
    from config import PANDW_API_KEY
except ImportError:
    # Fallback for when running from different directory
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from config import PANDW_API_KEY

# Disk-backed UserDataManager disabled in favor of in-memory caching
UserDataManager = None

class PNWAPIQuery:
    """Centralized class for handling all PNW API GraphQL queries with optimized caching."""
    
    def __init__(self, api_key: str = None, logger: logging.Logger = None):
        """Initialize the PNW API Query handler.
        
        Args:
            api_key: P&W API key. If None, will use PANDW_API_KEY from config.
            logger: Logger instance. If None, will create a default logger.
        """
        self.api_key = api_key or PANDW_API_KEY
        self.logger = logger or logging.getLogger(__name__)
        self.base_url = "https://api.politicsandwar.com/graphql"
        self.cache_ttl_seconds = 3600
        self.user_data_manager = None
        
        # Persistent HTTP session with retries and keep-alive to speed requests
        self._session = requests.Session()
        retry = Retry(total=3, backoff_factor=0.3, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=frozenset(["GET", "POST"]))
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        self._default_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            # Avoid 'br' (Brotli) since requests does not decode it by default
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "User-Agent": "ReaperPNW/1.0 (+https://discordbots/reaper)"
        }
        # Gentle spacing to avoid spamming while staying fast
        self._last_request_ts = 0.0
        try:
            self._min_interval_seconds = float(os.getenv("PNW_MIN_INTERVAL", "0.15"))
        except Exception:
            self._min_interval_seconds = 0.15
        
        # Small in-memory cache to dedupe identical rapid queries
        self._query_cache: Dict[str, Dict[str, Any]] = {}
        self._query_cache_expiry: Dict[str, float] = {}
        self._query_cache_ttl_seconds = 3600

        # Timezone configuration: default local server tz is America/New_York (EST/EDT)
        # Normalization will convert any provided cutoff to UTC for consistent comparisons
        self.local_tz_name = os.getenv("PNW_LOCAL_TZ", "America/New_York")
        try:
            self.local_tz = ZoneInfo(self.local_tz_name)
        except Exception:
            self.local_tz = None
        try:
            self.utc_tz = ZoneInfo("UTC")
        except Exception:
            self.utc_tz = None
        
        # Targeted caches
        self._resolve_cache: Dict[str, Dict[str, Any]] = {}
        self._resolve_cache_expiry: Dict[str, float] = {}
        self._resolve_cache_ttl_seconds = 3600
        self._trade_cache: Optional[Dict[str, Any]] = None
        self._trade_cache_expiry: float = 0.0
        self._trade_cache_ttl_seconds = 3600
        # General KV cache for JSON-like payloads
        self._kv_cache: Dict[str, Any] = {}
        self._kv_cache_expiry: Dict[str, float] = {}
        
        # Add processing flags to prevent infinite loops
        self._processing_alliances = set()
        self._processing_projects = set()
        self._processing_improvements = set()
        self._processing_cache = {}
        
        # Validate API key
        if not self.api_key or self.api_key == "YOUR_API_KEY_HERE":
            error_msg = "P&W API key not configured. Please set PANDW_API_KEY in your .env file."
            self.logger.error(error_msg)
            raise ValueError(error_msg)

    def _nation_fields(self) -> str:
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
            "alliance { id name acronym flag } "
            "cities { id name date infrastructure land powered nuke_date oil_power wind_power coal_power nuclear_power coal_mine oil_well uranium_mine lead_mine iron_mine bauxite_mine gasrefinery aluminum_refinery steel_mill munitions_factory factory farm police_station hospital recycling_center subway supermarket bank shopping_mall stadium barracks airforcebase drydock }"
        )

    def _normalize_nation(self, nation: Dict[str, Any]) -> Dict[str, Any]:
        try:
            a = nation.get("alliance") or {}
            if isinstance(a, dict):
                if a.get("name") is not None:
                    nation["alliance_name"] = a.get("name")
                if a.get("acronym") is not None:
                    nation["alliance_acronym"] = a.get("acronym")
                if a.get("flag") is not None:
                    nation["alliance_flag"] = a.get("flag")
                if nation.get("alliance_id") in (None, 0, ""):
                    nation["alliance_id"] = a.get("id")
        except Exception:
            pass
        try:
            cs = nation.get("cities") or []
            if isinstance(cs, list):
                for c in cs:
                    if isinstance(c, dict):
                        if "gasoline_refinery" not in c and "gasrefinery" in c:
                            c["gasoline_refinery"] = c.get("gasrefinery")
                        
                        # Convert individual improvement fields to improvements dictionary
                        improvements = {}
                        improvement_fields = [
                            'oil_power', 'wind_power', 'coal_power', 'nuclear_power',
                            'coal_mine', 'oil_well', 'uranium_mine', 'lead_mine', 
                            'iron_mine', 'bauxite_mine', 'gasrefinery', 'gasoline_refinery',
                            'aluminum_refinery', 'steel_mill', 'munitions_factory', 
                            'factory', 'farm', 'police_station', 'hospital', 
                            'recycling_center', 'subway', 'supermarket', 'bank', 
                            'shopping_mall', 'stadium', 'barracks', 'airforcebase', 'drydock'
                        ]
                        
                        for field in improvement_fields:
                            if field in c and isinstance(c[field], (int, float)):
                                improvements[field] = c[field]
                        
                        # Only set improvements if we found any valid improvement fields
                        if improvements:
                            c['improvements'] = improvements
        except Exception:
            pass
        return nation

    async def search_alliances(self, text: str, max_results: int = 25) -> Optional[List[Dict[str, Any]]]:
        try:
            q = (
                "query { alliances(search: \"" + str(text).replace("\"", "\\\"") + "\", first: " + str(max(1, int(max_results))) + ") { data { id name acronym flag } } }"
            )
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(None, self._make_request, q)
            items = (((data or {}).get("data") or {}).get("alliances") or {}).get("data") or []
            out: List[Dict[str, Any]] = []
            for it in items[:max_results]:
                out.append({
                    "id": it.get("id"),
                    "name": it.get("name"),
                    "acronym": it.get("acronym"),
                    "flag": it.get("flag"),
                })
            return out
        except Exception:
            try:
                url = "https://politicsandwar.com/api/alliances/?key=" + self.api_key + "&search=" + requests.utils.quote(str(text))
                
                # Offload blocking requests.get to thread
                def _fetch_search():
                    return self._session.get(url, timeout=20)
                
                resp = await asyncio.to_thread(_fetch_search)
                
                if resp.status_code != 200:
                    return None
                payload = resp.json() or {}
                arr = payload.get("alliances") or []
                out: List[Dict[str, Any]] = []
                for it in arr[:max_results]:
                    out.append({
                        "id": it.get("id"),
                        "name": it.get("name"),
                        "acronym": it.get("acronym"),
                        "flag": it.get("flag"),
                    })
                return out
            except Exception:
                return None

    async def resolve_alliance(self, identifier: Union[str, int]) -> Optional[Dict[str, Any]]:
        """Resolve an alliance by ID, name, or acronym, with targeted caching.

        Returns a dict like { 'id': str, 'name': str, 'acronym': str } or None if not found.
        """
        try:
            raw = str(identifier).strip() if identifier is not None else ""
            if not raw:
                return None

            # Check targeted cache first
            cache_key = f"resolve:{raw.lower()}"
            now = time.monotonic()
            exp = self._resolve_cache_expiry.get(cache_key, 0.0)
            if exp > now:
                cached = self._resolve_cache.get(cache_key)
                if cached:
                    return cached

            # Attempt to parse numeric id or link fragment
            aid: Optional[int] = None
            try:
                m = None
                try:
                    import re as _re
                    m = _re.search(r"id\s*=\s*(\d+)", raw)
                except Exception:
                    m = None
                if m:
                    aid = int(m.group(1))
                elif raw.isdigit():
                    aid = int(raw)
            except Exception:
                aid = None

            # Precise lookup by id
            if isinstance(aid, int) and aid > 0:
                q = f"""
                query {{
                  alliances(id: {aid}) {{
                    data {{ id name acronym }}
                  }}
                }}
                """
                data = await self._request_with_retries(q, timeout=30, attempts=3, cache_ttl_seconds=self._resolve_cache_ttl_seconds)
                items = ((((data or {}).get('data') or {}).get('alliances') or {}).get('data') or [])
                if items:
                    item = {
                        'id': str(items[0].get('id')),
                        'name': items[0].get('name') or '',
                        'acronym': items[0].get('acronym') or ''
                    }
                    self._resolve_cache[cache_key] = item
                    self._resolve_cache_expiry[cache_key] = time.monotonic() + self._resolve_cache_ttl_seconds
                    return item
                return None

            # Single request fetching by name via alias
            safe = raw.replace("\"", "\\\"")
            # Offline fallbacks: static config IDs for home alliance
            try:
                def _norm_local(s: str) -> str:
                    s2 = (s or '').strip().lower()
                    if s2.startswith('the '):
                        s2 = s2[4:]
                    return " ".join(s2.split())
                target_norm = _norm_local(raw)
                from config import HOME_ALLIANCE_ID
                static_map = {
                    'db4d': str(HOME_ALLIANCE_ID),
                    'death before dishonor': str(HOME_ALLIANCE_ID),
                }
                if target_norm in static_map:
                    aid = static_map[target_norm]
                    item = {'id': str(aid), 'name': raw, 'acronym': ''}
                    self._resolve_cache[cache_key] = item
                    self._resolve_cache_expiry[cache_key] = time.monotonic() + self._resolve_cache_ttl_seconds
                    return item
            except Exception:
                pass
            q = (
                "query { "
                + "byName: alliances(name: \"" + safe + "\") { data { id name acronym } } "
                + "}"
            )
            data = await self._request_with_retries(q, timeout=30, attempts=3, cache_ttl_seconds=self._resolve_cache_ttl_seconds)
            by_name = (((data or {}).get('data') or {}).get('byName') or {}).get('data') or []
            all_items = by_name

            # Optional secondary: try a broader server-side search if supported
            if not all_items:
                try:
                    q_search = ("query { alliances(search: \"" + safe + "\") { data { id name acronym } } }")
                    data_search = await self._request_with_retries(q_search, timeout=30, attempts=3, cache_ttl_seconds=self._resolve_cache_ttl_seconds)
                    all_items = ((((data_search or {}).get('data') or {}).get('alliances') or {}).get('data') or [])
                except Exception:
                    all_items = []

            if not all_items:
                all_items = []

            lowered = safe.lower()
            def is_exact(it: Dict[str, Any]) -> bool:
                return (
                    str(it.get('name') or '').lower() == lowered
                    or str(it.get('acronym') or '').lower() == lowered
                )

            if not all_items:
                # Final local fallback: scan cached bloc files for alliance name/acronym
                try:
                    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                    bloc_dir = os.path.join(base_dir, 'Systems', 'Data', 'Bloc')
                    if os.path.isdir(bloc_dir):
                        def _norm2(s: str) -> str:
                            s2 = (s or '').strip().lower()
                            if s2.startswith('the '):
                                s2 = s2[4:]
                            return " ".join(s2.split())
                        target2 = _norm2(raw)
                        for name in os.listdir(bloc_dir):
                            if not name.startswith('alliance_') or not name.endswith('.json'):
                                continue
                            full_path = os.path.join(bloc_dir, name)
                            try:
                                def _read_bloc():
                                    with open(full_path, 'r', encoding='utf-8') as f:
                                        return json.load(f)
                                obj = await asyncio.to_thread(_read_bloc)
                                aid_local = obj.get('id') or obj.get('alliance_id')
                                nm_local = obj.get('name') or ''
                                acr_local = obj.get('acronym') or ''
                                if not aid_local and name.startswith('alliance_'):
                                    try:
                                        aid_local = int(name[len('alliance_'):-len('.json')])
                                    except Exception:
                                        aid_local = None
                                if aid_local and (_norm2(nm_local) == target2 or _norm2(acr_local) == target2):
                                    item = {'id': str(aid_local), 'name': nm_local or raw, 'acronym': acr_local or ''}
                                    self._resolve_cache[cache_key] = item
                                    self._resolve_cache_expiry[cache_key] = time.monotonic() + self._resolve_cache_ttl_seconds
                                    return item
                            except Exception:
                                continue
                except Exception:
                    pass
                return None
            exact = [it for it in all_items if is_exact(it)]
            chosen = (exact[0] if exact else all_items[0])
            item = {
                'id': str(chosen.get('id')),
                'name': chosen.get('name') or '',
                'acronym': chosen.get('acronym') or ''
            }
            self._resolve_cache[cache_key] = item
            self._resolve_cache_expiry[cache_key] = time.monotonic() + self._resolve_cache_ttl_seconds
            return item
        except Exception as e:
            try:
                self.logger.warning(f"resolve_alliance: failed to resolve '{identifier}': {e}")
            except Exception:
                pass
            return None

    async def resolve_alliance_names_batched(self, names: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """Resolve multiple alliance names to IDs via a single GraphQL query using aliases.

        Returns mapping of input name -> item dict {id, name, acronym} or None if not found.
        Uses the 'alliances(name: ...) { data { id name acronym } }' filter.
        """
        try:
            # Sanitize and de-duplicate while preserving order
            seen = set()
            inputs: List[str] = []
            for n in (names or []):
                s = str(n or '').strip().lower()  # Normalize for dedupe
                if not s or s in seen:
                    continue
                seen.add(s)
                inputs.append(n)  # Keep original casing for mapping

            if not inputs:
                return {}

            # Build aliased query blocks
            blocks: List[str] = []
            for idx, nm in enumerate(inputs):
                safe = nm.replace("\"", "\\\"")
                alias = f"n{idx}"
                blocks.append(
                    f"{alias}: alliances(name: \"{safe}\") {{ data {{ id name acronym }} }}"
                )
            query = "query { " + " ".join(blocks) + " }"

            data = await self._request_with_retries(query, timeout=30, attempts=3, cache_ttl_seconds=self._resolve_cache_ttl_seconds)

            # Parse response
            result: Dict[str, Optional[Dict[str, Any]]] = {}
            now = time.monotonic()
            for idx, nm in enumerate(inputs):
                alias = f"n{idx}"
                block = ((data or {}).get('data') or {}).get(alias) or {}
                items = block.get('data') or []
                if not items:
                    result[nm] = None
                    continue

                # Prefer exact match (case-insensitive)
                lowered = nm.lower()
                exact = [it for it in items if str(it.get('name') or '').lower() == lowered or str(it.get('acronym') or '').lower() == lowered]
                chosen = exact[0] if exact else items[0]  # Fallback to first if no exact

                item = {
                    'id': str(chosen.get('id')),
                    'name': chosen.get('name') or '',
                    'acronym': chosen.get('acronym') or ''
                }

                # Cache individually
                cache_key = f"resolve:{nm.lower()}"
                self._resolve_cache[cache_key] = item
                self._resolve_cache_expiry[cache_key] = now + self._resolve_cache_ttl_seconds

                result[nm] = item

            return result
        except Exception as e:
            self.logger.error(f"resolve_alliance_names_batched failed: {e}")
            return {nm: None for nm in (names or [])}

    def _make_request(self, query: str, timeout: int = 30, cache_ttl_seconds: float = 0) -> Dict[str, Any]:
        # Dedupe cache check (short TTL for identical queries)
        cache_key = hash(query)
        now = time.monotonic()
        if cache_key in self._query_cache_expiry and self._query_cache_expiry[cache_key] > now:
            return self._query_cache[cache_key]

        # Rate limit wait
        elapsed = now - self._last_request_ts
        if elapsed < self._min_interval_seconds:
            time.sleep(self._min_interval_seconds - elapsed)
        self._last_request_ts = time.monotonic()

        # Use query-param API key (known-good for PnW GraphQL)
        url = f"{self.base_url}?api_key={self.api_key}"
        payload = {"query": query}
        headers = dict(self._default_headers)

        # Perform the request; rely on session-level retry adapter
        resp = self._session.post(url, json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()

        # Parse JSON
        data = resp.json()

        # If GraphQL errors present, raise for caller to handle
        if isinstance(data, dict) and data.get("errors"):
            errs = data.get("errors") or []
            msg = None
            try:
                if errs and isinstance(errs[0], dict):
                    msg = errs[0].get("message") or str(errs[0])
                else:
                    msg = str(errs)
            except Exception:
                msg = "GraphQL error"
            raise Exception(msg or "GraphQL error")

        ttl = cache_ttl_seconds if cache_ttl_seconds and cache_ttl_seconds > 0 else self._query_cache_ttl_seconds
        if ttl and ttl > 0:
            self._query_cache[cache_key] = data
            self._query_cache_expiry[cache_key] = now + ttl

        return data

    async def _request_with_retries(
        self,
        query: str,
        timeout: int = 30,
        attempts: int = 3,
        cache_ttl_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        last_error: Optional[Exception] = None
        for i in range(max(1, int(attempts))):
            try:
                fn = partial(self._make_request, query, timeout=timeout, cache_ttl_seconds=float(cache_ttl_seconds or 0))
                return await loop.run_in_executor(None, fn)
            except Exception as e:
                last_error = e
                try:
                    await asyncio.sleep(0.5 * (2 ** i))
                except Exception:
                    pass
        return {}

    def _to_utc(self, dt: Optional[datetime]) -> Optional[datetime]:
        """Convert a datetime to naive UTC.

        - If `dt` is naive, interpret it in the local server timezone (default America/New_York),
          then convert to UTC and drop tzinfo.
        - If `dt` is aware, convert to UTC and drop tzinfo.
        - Returns None if conversion fails.
        """
        if dt is None:
            return None
        try:
            base = dt
            if base.tzinfo is None:
                tz = getattr(self, "local_tz", None)
                if tz is None:
                    try:
                        tz = ZoneInfo(os.getenv("PNW_LOCAL_TZ", "America/New_York"))
                    except Exception:
                        tz = None
                    self.local_tz = tz
                if tz is not None:
                    base = base.replace(tzinfo=tz)
            # Convert to UTC then drop tzinfo so comparisons work with API's naive timestamps
            if self.utc_tz is not None:
                return base.astimezone(self.utc_tz).replace(tzinfo=None)
            # Fallback: assume input is already UTC
            return base.replace(tzinfo=None)
        except Exception:
            try:
                return dt.replace(tzinfo=None)
            except Exception:
                return None

    async def get_game_info(self, request_timeout_seconds: int = 30) -> Optional[Dict[str, Any]]:
        """Fetch GameInfo (game_date, radiation, city_average) with robust parsing and caching."""
        try:
            q = """
            query {
              gameInfo: game_info {
                game_date
                city_average
                radiation {
                  global
                  north_america
                  south_america
                  europe
                  africa
                  asia
                  australia
                  antarctica
                }
              }
            }
            """
            data = await self._request_with_retries(q, timeout=int(request_timeout_seconds), attempts=2, cache_ttl_seconds=3600)
            root = (data or {}).get("data") or {}
            gi = root.get("gameInfo") or root.get("game_info") or {}
            if not gi:
                q2 = """
                query {
                  game {
                    date
                    city_average
                    radiation {
                      global
                      north_america
                      south_america
                      europe
                      africa
                      asia
                      australia
                      antarctica
                    }
                  }
                }
                """
                data2 = await self._request_with_retries(q2, timeout=int(request_timeout_seconds), attempts=2, cache_ttl_seconds=3600)
                root2 = (data2 or {}).get("data") or {}
                gi = root2.get("game") or {}
            out: Dict[str, Any] = {}
            out["game_date"] = gi.get("game_date") or gi.get("date")
            # Coerce city_average to float if possible
            ca = gi.get("city_average")
            try:
                out["city_average"] = float(ca) if ca is not None else None
            except Exception:
                out["city_average"] = ca
            # Radiation may be dict or scalar
            rad = gi.get("radiation")
            if isinstance(rad, dict):
                out["radiation"] = rad
            else:
                out["radiation"] = {"global": rad} if rad is not None else {}
            return out
        except Exception as e:
            try:
                self.logger.warning(f"get_game_info: {e}")
            except Exception:
                pass
            return None

    async def get_trade_resource_values(self, resources: Optional[List[str]] = None) -> Optional[List[Dict[str, Any]]]:
        """Fetch latest trade prices using the Tradeprice paginator with caching.

        Returns list of dicts: { "resource": <NAME>, "average_price": <Float> }.
        If ``resources`` is provided, filters to those resource names (case-insensitive).
        """
        try:
            loop = asyncio.get_running_loop()

            # Use cache if fresh
            now = time.monotonic()
            if self._trade_cache and now < self._trade_cache_expiry:
                latest = self._trade_cache
            else:
                query = """
                query {
                  tradeprices(first: 1, page: 1) {
                    data {
                      id
                      date
                      coal
                      oil
                      uranium
                      iron
                      bauxite
                      lead
                      gasoline
                      munitions
                      steel
                      aluminum
                      food
                      credits
                    }
                  }
                }
                """
                fn = partial(self._make_request, query, timeout=30, cache_ttl_seconds=self._trade_cache_ttl_seconds)
                data = await loop.run_in_executor(None, fn)
                block = (data.get("data") or {}).get("tradeprices") or {}
                entries = block.get("data") or []
                if not entries:
                    self.logger.warning("get_trade_resource_values: tradeprices returned no data")
                    return []
                latest = entries[0] or {}
                # Update cache
                self._trade_cache = latest
                self._trade_cache_expiry = time.monotonic() + self._trade_cache_ttl_seconds

            price_map = {
                "FOOD": latest.get("food"),
                "COAL": latest.get("coal"),
                "OIL": latest.get("oil"),
                "URANIUM": latest.get("uranium"),
                "LEAD": latest.get("lead"),
                "IRON": latest.get("iron"),
                "BAUXITE": latest.get("bauxite"),
                "GASOLINE": latest.get("gasoline"),
                "MUNITIONS": latest.get("munitions"),
                "STEEL": latest.get("steel"),
                "ALUMINUM": latest.get("aluminum"),
                "CREDIT": latest.get("credits"),
            }

            if resources:
                requested = {str(r).upper() for r in resources}
                keys = [k for k in price_map.keys() if k in requested]
            else:
                keys = list(price_map.keys())

            result: List[Dict[str, Any]] = []
            for k in keys:
                v = price_map.get(k)
                try:
                    price = float(v) if v is not None else 0.0
                except Exception:
                    price = 0.0
                result.append({"resource": k, "average_price": price})

            return result
        except Exception as e:
            self.logger.error(f"get_trade_resource_values: failed to fetch trade prices via paginator: {e}")
            return None
    
    async def get_alliance_nations(self, alliance_id: str, bot=None, force_refresh: bool = False) -> Optional[List[Dict[str, Any]]]:
        """Get all nations from a specific alliance with caching via UserDataManager.
        
        Args:
            alliance_id: The alliance ID to query
            bot: Discord bot instance for fetching Discord usernames (optional)
            force_refresh: If True, bypass cache and fetch fresh data
            
        Returns:
            List of nation dictionaries or None if failed
        """
        try:
            # Prevent infinite recursion
            cache_key = f"alliance_{alliance_id}"
            if cache_key in self._processing_alliances:
                self.logger.warning(f"Detected recursive call to get_alliance_nations for alliance {alliance_id}, returning cached data")
                return self._processing_cache.get(cache_key, [])
            
            # Mark as processing
            self._processing_alliances.add(cache_key)
            now = time.time()

            if not force_refresh:
                try:
                    kv_key = f'alliance_{alliance_id}'
                    exp = self._kv_cache_expiry.get(kv_key, 0.0)
                    now_mono = time.monotonic()
                    if exp > now_mono:
                        alliance_data = self._kv_cache.get(kv_key) or {}
                        if alliance_data and isinstance(alliance_data, dict):
                            nations = alliance_data.get('nations', [])
                            if nations:
                                if bot:
                                    await self._fetch_discord_usernames(nations, bot)
                                self._processing_cache[cache_key] = nations
                                return nations
                except Exception:
                    pass

            # Fetch via nations paginator with full pagination
            try:
                def nation_fields() -> str:
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
                        "cities { id name date infrastructure land powered nuke_date oil_power wind_power coal_power nuclear_power coal_mine oil_well uranium_mine lead_mine iron_mine bauxite_mine gasrefinery aluminum_refinery steel_mill munitions_factory factory farm police_station hospital recycling_center subway supermarket bank shopping_mall stadium barracks airforcebase drydock }"
                    )
            except Exception:
                def nation_fields() -> str:
                    return "id nation_name leader_name alliance_id score num_cities last_active"

            nations: List[Dict[str, Any]] = []
            loop = asyncio.get_running_loop()
            first = 500
            page_num = 1
            last_page: Optional[int] = None
            while True:
                query = (
                    "query {\n"
                    + f"  nations(alliance_id: {alliance_id}, first: {first}, page: {page_num}) {{\n"
                    + "    paginatorInfo { currentPage lastPage hasMorePages }\n"
                    + f"    data {{ {self._nation_fields()} }}\n"
                    + "  }\n"
                    + "}"
                )
                data = await loop.run_in_executor(None, self._make_request, query)
                block = (data.get('data') or {}).get('nations') or {}
                items = block.get('data') or []
                if not items:
                    break
                for it in items:
                    nations.append(self._normalize_nation(it))
                try:
                    pi = block.get('paginatorInfo') or {}
                    last_page = int(pi.get('lastPage') or 0) or last_page
                except Exception:
                    pass
                if isinstance(last_page, int) and last_page > 0 and page_num >= last_page:
                    break
                page_num += 1
            self.logger.info(f"get_alliance_nations: Retrieved {len(nations)} nations for alliance {alliance_id}")

            try:
                kv_key = f'alliance_{alliance_id}'
                alliance_data = {
                    'nations': nations,
                    'alliance_id': alliance_id,
                    'last_updated': datetime.now().isoformat(),
                    'total_nations': len(nations)
                }
                self._kv_cache[kv_key] = alliance_data
                self._kv_cache_expiry[kv_key] = time.monotonic() + float(self.cache_ttl_seconds or 3600)
            except Exception:
                pass

            # Fetch Discord usernames for nations that have Discord IDs
            if bot:
                await self._fetch_discord_usernames(nations, bot)

            # Store in processing cache to prevent infinite loops
            self._processing_cache[cache_key] = nations
            
            # Remove from processing set
            self._processing_alliances.discard(cache_key)
            
            return nations

        except Exception as e:
            self.logger.error(f"get_alliance_nations: Error retrieving alliance nations: {str(e)}")
            # Remove from processing set even on error
            if cache_key in self._processing_alliances:
                self._processing_alliances.discard(cache_key)
            return None

    async def get_alliances_nations_batched(
        self,
        alliance_ids: List[Union[int, str]],
        side_label: Optional[str] = None,
        bot=None,
        force_refresh: bool = True,
    ) -> Dict[int, List[Dict[str, Any]]]:
        """Fetch nations for multiple alliances in a single GraphQL request.

        - Builds one query using field aliases per `alliances(id: ...)`.
        - Optionally persists aggregated Home/Away results to `war_party_<side>` for quick reuse.

        Args:
            alliance_ids: List of alliance IDs to fetch.
            side_label: Optional label 'home' or 'away' to persist the aggregate.
            bot: Optional Discord bot for enriching with usernames.
            force_refresh: If False, attempts to use per-alliance cache; otherwise fetch fresh.

        Returns:
            Dict mapping alliance_id -> list of nation dicts.
        """
        try:
            ids: List[int] = []
            for a in alliance_ids or []:
                try:
                    ai = int(str(a).strip())
                    if ai > 0:
                        ids.append(ai)
                except Exception:
                    continue
            ids = sorted(set(ids))
            if not ids:
                return {}

            # Always fetch fresh in batched mode to avoid per-alliance cache reads

            # Build single GraphQL query using field aliases
            def nation_fields() -> str:
                return self._nation_fields()

            alias_blocks = []
            for aid in ids:
                alias = f"alli_{aid}"
                block = (
                    f"{alias}: alliances(id: {aid}) {{ data {{ nations {{ {nation_fields()} }} }} }}"
                )
                alias_blocks.append(block)
            query = "query { " + " ".join(alias_blocks) + " }"

            data = await self._request_with_retries(query, timeout=30, attempts=2)

            root = data.get('data') or {}
            result: Dict[int, List[Dict[str, Any]]] = {}
            nations_all: List[Dict[str, Any]] = []
            for aid in ids:
                alias = f"alli_{aid}"
                alli_block = root.get(alias) or {}
                alli_list = alli_block.get('data') or []
                nations = []
                if alli_list:
                    raw = alli_list[0].get('nations') or []
                    nations = [self._normalize_nation(n) for n in raw]
                result[aid] = nations
                if bot and nations:
                    try:
                        await self._fetch_discord_usernames(nations, bot)
                    except Exception:
                        pass
            for n in nations or []:
                nations_all.append(n)

            if side_label:
                try:
                    agg_payload = {
                        'role': 'party',
                        'side': str(side_label).lower(),
                        'alliances': [{'id': a} for a in ids],
                        'nations': nations_all,
                        'last_updated': datetime.now().isoformat(),
                        'total_nations': len(nations_all),
                    }
                    kv_key = f"war_party_{str(side_label).lower()}"
                    self._kv_cache[kv_key] = agg_payload
                    self._kv_cache_expiry[kv_key] = time.monotonic() + float(self.cache_ttl_seconds or 3600)
                except Exception:
                    pass

            return result
        except Exception as e:
            try:
                self.logger.error(f"get_alliances_nations_batched: error: {e}")
            except Exception:
                pass
            return {}

    async def get_alliance_treaties(
        self,
        alliance_id: str,
        limit: Optional[int] = None,
        force_refresh: bool = True,
        cutoff_dt: Optional[datetime] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """Get treaties for a specific alliance.

        Args:
            alliance_id: The alliance ID to query
            limit: Optional maximum number of treaties to fetch (API may support this arg)
            force_refresh: If False, attempt to read cached treaties; otherwise fetch fresh data

        Returns:
            List of treaty dictionaries or None if failed
        """
        try:
            cache_key = f"treaties_{alliance_id}"

            if not force_refresh:
                try:
                    exp = self._kv_cache_expiry.get(cache_key, 0.0)
                    if exp > time.monotonic():
                        treaties_data = self._kv_cache.get(cache_key, {})
                        if treaties_data and isinstance(treaties_data, dict):
                            items = treaties_data.get('treaties', [])
                            if items:
                                return items
                except Exception:
                    pass

            # Build GraphQL query
            limit_arg = f"(limit: {int(limit)})" if isinstance(limit, int) and limit > 0 else ""
            query = f"""
                query {{
                  alliances(id: {alliance_id}) {{
                    data {{
                      id
                      name
                      acronym
                      treaties{limit_arg} {{
                        id
                        date
                        treaty_type
                        treaty_url
                        turns_left
                        alliance1_id
                        alliance2_id
                        approved
                        alliance1 {{ id name acronym flag }}
                        alliance2 {{ id name acronym flag }}
                      }}
                    }}
                  }}
                }}
            """

            # Execute request off the event loop
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(None, self._make_request, query)

            alliances_block = data.get('data', {}).get('alliances', {})
            alliance_list = alliances_block.get('data') or []
            if not alliance_list:
                self.logger.warning(f"get_alliance_treaties: No alliance data returned for {alliance_id}")
                return []

            treaties = alliance_list[0].get('treaties') or []

            # Normalize cutoff to UTC (naive)
            cutoff_utc = self._to_utc(cutoff_dt) if cutoff_dt else None

            # Apply cutoff filter by treaty date if provided
            def _parse_dt(val: Any) -> Optional[datetime]:
                try:
                    if isinstance(val, datetime):
                        return val
                    if isinstance(val, str) and val:
                        s = val.strip().replace('Z', '')
                        return datetime.fromisoformat(s)
                except Exception:
                    return None
                return None

            if cutoff_utc:
                filtered: List[Dict[str, Any]] = []
                for t in treaties:
                    dt = _parse_dt(t.get('date'))
                    if dt and dt >= cutoff_utc:
                        filtered.append(t)
                treaties = filtered

            # Enforce limit client-side if provided
            if isinstance(limit, int) and limit > 0 and len(treaties) > limit:
                treaties = treaties[:limit]

            self.logger.info(f"get_alliance_treaties: Retrieved {len(treaties)} treaties for alliance {alliance_id}")

            try:
                payload = {
                    'treaties': treaties,
                    'alliance_id': alliance_id,
                    'last_updated': datetime.now().isoformat(),
                    'total_treaties': len(treaties),
                    'cutoff': cutoff_utc.isoformat() if cutoff_utc else None
                }
                self._kv_cache[cache_key] = payload
                self._kv_cache_expiry[cache_key] = time.monotonic() + float(self.cache_ttl_seconds or 3600)
            except Exception:
                pass

            return treaties

        except Exception as e:
            # GraphQL failed — try REST v2 fallback
            try:
                self.logger.warning(f"get_alliance_treaties: GraphQL error '{e}'. Falling back to REST API v2")
                url = f"https://politicsandwar.com/api/treaties/?alliance_id={alliance_id}&key={self.api_key}"
                
                def _fetch_rest():
                    return requests.get(url, timeout=30)
                
                resp = await asyncio.to_thread(_fetch_rest)
                if resp.status_code != 200:
                    self.logger.error(f"get_alliance_treaties REST fallback: HTTP {resp.status_code}")
                    return None

                payload = resp.json()
                if not payload or not payload.get('success', False):
                    self.logger.error(f"get_alliance_treaties REST fallback: API error {payload}")
                    return None

                treaties = payload.get('treaties') or []

                # Normalize cutoff
                cutoff_utc = self._to_utc(cutoff_dt) if cutoff_dt else None

                def _parse_dt(val: Any) -> Optional[datetime]:
                    try:
                        if isinstance(val, datetime):
                            return val
                        if isinstance(val, str) and val:
                            s = val.strip().replace('Z', '')
                            return datetime.fromisoformat(s)
                    except Exception:
                        return None
                    return None

                if cutoff_utc:
                    filtered: List[Dict[str, Any]] = []
                    for t in treaties:
                        dt = _parse_dt(t.get('date'))
                        if dt and dt >= cutoff_utc:
                            filtered.append(t)
                    treaties = filtered

                if isinstance(limit, int) and limit > 0 and len(treaties) > limit:
                    treaties = treaties[:limit]

                try:
                    cache_key = f"treaties_{alliance_id}"
                    payload = {
                        'treaties': treaties,
                        'alliance_id': alliance_id,
                        'last_updated': datetime.now().isoformat(),
                        'total_treaties': len(treaties),
                        'cutoff': cutoff_utc.isoformat() if cutoff_utc else None
                    }
                    self._kv_cache[cache_key] = payload
                    self._kv_cache_expiry[cache_key] = time.monotonic() + float(self.cache_ttl_seconds or 3600)
                except Exception:
                    pass

                self.logger.info(f"get_alliance_treaties REST fallback: Retrieved {len(treaties)} treaties for alliance {alliance_id}")
                return treaties
            except Exception as rest_err:
                self.logger.error(f"get_alliance_treaties: REST fallback failed: {rest_err}")
                return None

    async def get_treaties_for_alliances(
        self,
        alliance_ids: List[int],
        limit: Optional[int] = None,
        force_refresh: bool = True,
        cutoff_dt: Optional[datetime] = None,
        request_timeout_seconds: Optional[int] = 30,
    ) -> Dict[int, List[Dict[str, Any]]]:
        """Batch-fetch treaties for multiple alliances using GraphQL aliases.

        - Consolidates multiple `alliances(id: ...) { treaties }` lookups into one request via aliases.
        - Applies optional cutoff filter (`date >= cutoff_dt`) per alliance.
        - Respects optional per-alliance `limit` client-side.
        - Saves per-alliance cache files, same format as `get_alliance_treaties`.

        Returns a mapping of alliance_id -> list of treaty dicts.
        """
        try:
            ids = [int(x) for x in (alliance_ids or []) if str(x).strip()]
            ids = [i for i in ids if i > 0]
            if not ids:
                return {}

            # Allow optional limit argument in GraphQL, if provided
            limit_arg = f"(limit: {int(limit)})" if isinstance(limit, int) and limit > 0 else ""

            # Build aliased blocks for all alliances
            blocks = []
            for aid in ids:
                alias = f"alli_{aid}"
                blocks.append(
                    f"{alias}: alliances(id: {aid}) {{\n"
                    f"  data {{\n"
                    f"    id\n"
                    f"    name\n"
                    f"    acronym\n"
                    f"    treaties{limit_arg} {{\n"
                    f"      id\n"
                    f"      date\n"
                    f"      treaty_type\n"
                    f"      treaty_url\n"
                    f"      turns_left\n"
                    f"      alliance1_id\n"
                    f"      alliance2_id\n"
                    f"      approved\n"
                    f"      alliance1 {{ id name acronym flag }}\n"
                    f"      alliance2 {{ id name acronym flag }}\n"
                    f"    }}\n"
                    f"  }}\n"
                    f"}}\n"
                )

            query = "query {\n" + "".join(blocks) + "}"

            data = await self._request_with_retries(
                query,
                timeout=int(request_timeout_seconds) if isinstance(request_timeout_seconds, int) and request_timeout_seconds > 0 else 30,
                attempts=2,
            )

            # Helper: parse ISO date
            def _parse_dt(val: Any) -> Optional[datetime]:
                try:
                    if isinstance(val, datetime):
                        return val
                    if isinstance(val, str) and val:
                        s = val.strip().replace('Z', '')
                        return datetime.fromisoformat(s)
                except Exception:
                    return None
                return None

            # Normalize cutoff to UTC (naive)
            cutoff_utc = self._to_utc(cutoff_dt) if cutoff_dt else None
            result: Dict[int, List[Dict[str, Any]]] = {}
            root = data.get('data') or {}
            save_tasks = []
            for aid in ids:
                alias = f"alli_{aid}"
                block = root.get(alias) or {}
                alli_list = block.get('data') or []
                treaties = []
                if alli_list:
                    treaties = alli_list[0].get('treaties') or []

                # Apply cutoff per alliance
                if cutoff_utc:
                    treaties = [t for t in treaties if (_parse_dt(t.get('date')) or datetime.min) >= cutoff_utc]

                # Enforce limit client-side if needed
                if isinstance(limit, int) and limit > 0 and len(treaties) > limit:
                    treaties = treaties[:limit]

                result[aid] = treaties

                try:
                    cache_key = f"treaties_{aid}"
                    payload = {
                        'treaties': treaties,
                        'alliance_id': str(aid),
                        'last_updated': datetime.now().isoformat(),
                        'total_treaties': len(treaties),
                        'cutoff': cutoff_utc.isoformat() if cutoff_utc else None,
                    }
                    self._kv_cache[cache_key] = payload
                    self._kv_cache_expiry[cache_key] = time.monotonic() + float(self.cache_ttl_seconds or 3600)
                except Exception:
                    pass

            # Summary log
            total = sum(len(v) for v in result.values())

            self.logger.info(f"get_treaties_for_alliances: Retrieved {total} treaties across {len(ids)} alliances")
            return result

        except Exception as e:
            self.logger.error(f"get_treaties_for_alliances: Error retrieving treaties: {str(e)}")
            return {}

    async def get_wars_for_alliances(
        self,
        alliance_ids: List[int],
        limit: Optional[int] = None,
        page: Optional[int] = 1,
        force_refresh: bool = True,
        cutoff_dt: Optional[datetime] = None,
        page_size: Optional[int] = 1000,
        max_pages: Optional[int] = None,
        active_mode: Optional[str] = 'both',
        mode_delay_seconds: Optional[float] = 0.0,
        page_delay_seconds: Optional[float] = 0.0,
        request_timeout_seconds: Optional[int] = 20,
        request_retries: Optional[int] = 3,
        retry_backoff_seconds: Optional[float] = 1.0,
        concurrency_limit: Optional[int] = 4,
    ) -> Dict[int, List[Dict[str, Any]]]:
        """Fetch wars for multiple alliances using aliased fields, with full pagination and optional cutoff.

        - Supports `active_mode`: 'active', 'inactive', or 'both' (default). When 'both', fetches active and inactive wars separately and merges results.
        - Staggers mode requests with `mode_delay_seconds` between runs to avoid spamming the API.
        - Iterates pages until no rows are returned (or until `max_pages` if provided).
        - Always requests a fixed `page_size` per page (default 100) to avoid API defaults.
        - Applies `cutoff_dt` using attack dates first, then war start/end as fallback.
        Returns a mapping of alliance_id -> list of war dicts (deduped across modes and pages).
        """
        try:
            ids = [int(x) for x in (alliance_ids or []) if str(x).strip()]
            ids = [int(x) for x in ids if int(x) > 0]
            if not ids:
                return {}

            # Normalize cutoff to UTC (naive treated as local server TZ)
            cutoff_utc = self._to_utc(cutoff_dt) if cutoff_dt else None

            # Per-request page size and iteration limit
            try:
                first = int(page_size) if page_size is not None else 500
            except Exception:
                first = 500
            if first > 500:
                first = 500
            if first <= 0:
                first = 500
            try:
                start_page = int(page) if page is not None else 1
            except Exception:
                start_page = 1
            # max_pages: None or <=0 means unlimited; only honor explicit positive values
            if max_pages is not None and (not isinstance(max_pages, int) or max_pages <= 0):
                max_pages = None

            first_arg_tpl = ", first: {first}"
            page_arg_tpl = ", page: {page}"  # We always paginate; default to provided page

            # Common field selection (mirrors get_alliance_wars); include paginatorInfo to short-circuit at lastPage
            wars_fields = """
              paginatorInfo {
                currentPage
                lastPage
                hasMorePages
              }
              data {
                id
                date
                end_date
                winner_id
                att_id
                def_id
                att_alliance_id
                def_alliance_id
                attacker { id alliance_id }
                defender { id alliance_id }
                reason
                war_type
                ground_control
                air_superiority
                naval_blockade
                attacks {
                  id
                  date
                  att_id
                  attid
                  def_id
                  defid
                  type
                  war_id
                  warid
                  victor
                  success
                  city_id
                  cityid
                  infra_destroyed
                  infradestroyed
                  infra_destroyed_value
                  resistance_lost
                  resistance_eliminated
                  money_stolen
                  moneystolen
                  money_looted
                  att_mun_used
                  def_mun_used
                  att_gas_used
                  def_gas_used
                  att_soldiers_lost
                  def_soldiers_lost
                  att_tanks_lost
                  def_tanks_lost
                  att_aircraft_lost
                  def_aircraft_lost
                  att_ships_lost
                  def_ships_lost
                  att_missiles_lost
                  def_missiles_lost
                  att_nukes_lost
                  def_nukes_lost
                  gasoline_looted
                  munitions_looted
                  aluminum_looted
                  steel_looted
                  food_looted
                  coal_looted
                  oil_looted
                  uranium_looted
                  iron_looted
                  bauxite_looted
                  lead_looted
                }
              }
            """

            def _war_in_window(w: Dict[str, Any]) -> bool:
                if not cutoff_utc:
                    return True
                attacks = w.get('attacks') or []
                for a in attacks or []:
                    try:
                        ad_raw = a.get('date')
                        ad = datetime.fromisoformat(ad_raw.replace('Z', '+00:00')) if ad_raw else None
                        # Normalize parsed attack date to naive UTC for comparison
                        if ad is not None:
                            try:
                                ad = ad.astimezone(self.utc_tz).replace(tzinfo=None) if self.utc_tz is not None else ad.replace(tzinfo=None)
                            except Exception:
                                ad = ad.replace(tzinfo=None)
                    except Exception:
                        ad = None
                    if ad and ad >= cutoff_utc:
                        return True
                for k in ('date', 'end_date'):
                    try:
                        d_raw = w.get(k)
                        d = datetime.fromisoformat(d_raw.replace('Z', '+00:00')) if d_raw else None
                        # Normalize parsed war date to naive UTC for comparison
                        if d is not None:
                            try:
                                d = d.astimezone(self.utc_tz).replace(tzinfo=None) if self.utc_tz is not None else d.replace(tzinfo=None)
                            except Exception:
                                d = d.replace(tzinfo=None)
                    except Exception:
                        d = None
                    if d and d >= cutoff_utc:
                        return True
                return False

            # Concurrent per-alliance fetching with bounded concurrency
            result: Dict[int, List[Dict[str, Any]]] = {aid: [] for aid in ids}
            seen_ids_per_aid: Dict[int, set] = {aid: set() for aid in ids}
            loop = asyncio.get_running_loop()
            sem = asyncio.Semaphore(int(concurrency_limit) if isinstance(concurrency_limit, int) and concurrency_limit and concurrency_limit > 0 else 4)

            mode_val = (active_mode or 'both').lower()
            modes = ['active', 'inactive'] if mode_val not in ('active', 'inactive') else [mode_val]

            async def _fetch_alliance_mode(aid: int, mode: str):
                async with sem:
                    pages_fetched = 0
                    page_num = start_page
                    while True:
                        first_arg = first_arg_tpl.format(first=first) if isinstance(first, int) and first > 0 else ""
                        page_arg = page_arg_tpl.format(page=page_num) if isinstance(page_num, int) and page_num > 0 else ""
                        filter_arg = ", active: true" if mode == 'active' else ", active: false"

                        query = (
                            "query {\n"
                            f"  wars(alliance_id: {aid}{first_arg}{page_arg}{filter_arg}) {{\n"
                            f"{wars_fields}\n"
                            "  }\n"
                            "}"
                        )

                        data: Dict[str, Any] = await self._request_with_retries(
                            query,
                            timeout=int(request_timeout_seconds) if isinstance(request_timeout_seconds, int) and request_timeout_seconds > 0 else 20,
                            attempts=int(request_retries) if isinstance(request_retries, int) and request_retries and request_retries > 0 else 1,
                        )

                        block = (data.get("data") or {}).get("wars") or {}
                        wars = block.get("data") or []

                        try:
                            pi = block.get("paginatorInfo") or {}
                            last_page = int(pi.get("lastPage") or 0)
                        except Exception:
                            last_page = 0

                        page_all_older_than_cutoff = True if cutoff_utc else False
                        for w in wars:
                            if not cutoff_dt or _war_in_window(w):
                                try:
                                    wid = int(w.get('id') or 0)
                                except Exception:
                                    wid = 0
                                if wid and wid not in seen_ids_per_aid[aid]:
                                    result[aid].append(w)
                                    seen_ids_per_aid[aid].add(wid)
                                    page_all_older_than_cutoff = False

                        pages_fetched += 1
                        if isinstance(max_pages, int) and max_pages > 0 and pages_fetched >= max_pages:
                            break
                        if not wars:
                            break
                        if isinstance(last_page, int) and last_page > 0 and page_num >= last_page:
                            break
                        if cutoff_utc and page_all_older_than_cutoff:
                            break

                        page_num += 1
                        try:
                            if isinstance(page_delay_seconds, (int, float)) and page_delay_seconds:
                                await asyncio.sleep(float(page_delay_seconds))
                        except Exception:
                            pass

                    try:
                        if isinstance(mode_delay_seconds, (int, float)) and mode_delay_seconds:
                            await asyncio.sleep(float(mode_delay_seconds))
                    except Exception:
                        pass

            tasks = []
            for aid in ids:
                for mode in modes:
                    tasks.append(_fetch_alliance_mode(aid, mode))
            if tasks:
                await asyncio.gather(*tasks)

            return result
        except Exception as e:
            self.logger.error(f"get_wars_for_alliances: failed to fetch wars for alliances {alliance_ids}: {e}")
            return {}

    async def get_wars_for_alliances_batched(
        self,
        alliance_ids: List[int],
        limit: Optional[int] = None,
        page: Optional[int] = 1,
        force_refresh: bool = True,
        cutoff_dt: Optional[datetime] = None,
        page_size: Optional[int] = 1000,
        max_pages: Optional[int] = None,
        active_mode: Optional[str] = 'both',
        mode_delay_seconds: Optional[float] = 0.0,
        page_delay_seconds: Optional[float] = 0.0,
        request_timeout_seconds: Optional[int] = 20,
        request_retries: Optional[int] = 3,
        retry_backoff_seconds: Optional[float] = 1.0,
        batch_size: Optional[int] = 2,
        ) -> Dict[int, List[Dict[str, Any]]]:
        """Batch wars fetching across multiple alliances using GraphQL aliases in chunks.

        - Splits `alliance_ids` into chunks of `batch_size` to avoid oversized alias queries.
        - For each chunk, calls `get_wars_for_alliances` which already performs aliased multi-alliance
          requests with full pagination and supports `active_mode` ('active', 'inactive', 'both').
        - Merges results across chunks and deduplicates per-alliance by war id.
        - Does not modify or replace existing single-alliance helpers.
        """
        try:
            ids = [int(x) for x in (alliance_ids or []) if str(x).strip()]
            ids = [int(x) for x in ids if int(x) > 0]
            if not ids:
                return {}

            try:
                bs = int(batch_size) if batch_size is not None else 3
            except Exception:
                bs = 3
            if bs <= 0:
                bs = 3

            combined: Dict[int, List[Dict[str, Any]]] = {aid: [] for aid in ids}
            seen_ids_per_aid: Dict[int, set] = {aid: set() for aid in ids}

            for i in range(0, len(ids), bs):
                chunk = ids[i:i+bs]
                chunk_map = await self.get_wars_for_alliances(
                    chunk,
                    limit=limit,
                    page=page,
                    force_refresh=force_refresh,
                    cutoff_dt=cutoff_dt,
                    page_size=page_size,
                    max_pages=max_pages,
                    active_mode=active_mode,
                    mode_delay_seconds=mode_delay_seconds,
                    page_delay_seconds=page_delay_seconds,
                    request_timeout_seconds=request_timeout_seconds,
                    request_retries=request_retries,
                    retry_backoff_seconds=retry_backoff_seconds,
                )

                for aid, wars_list in (chunk_map or {}).items():
                    for w in wars_list or []:
                        try:
                            wid = int(w.get('id') or 0)
                        except Exception:
                            wid = 0
                        if wid and wid not in seen_ids_per_aid.get(aid, set()):
                            combined.setdefault(aid, []).append(w)
                            seen_ids_per_aid.setdefault(aid, set()).add(wid)

            return combined
        except Exception as e:
            self.logger.error(f"get_wars_for_alliances_batched: failed to fetch wars for alliances {alliance_ids}: {e}")
            return {}

    async def get_wars_for_alliances_aliased(
        self,
        alliance_ids: List[int],
        page_size: Optional[int] = 1000,
        active_mode: Optional[str] = 'both',
        cutoff_dt: Optional[datetime] = None,
        request_timeout_seconds: Optional[int] = 20,
        request_retries: Optional[int] = 2,
        retry_backoff_seconds: Optional[float] = 0.5,
        alias_batch_size: Optional[int] = 8,
    ) -> Dict[int, List[Dict[str, Any]]]:
        try:
            ids = [int(x) for x in (alliance_ids or []) if str(x).strip()]
            ids = [int(x) for x in ids if int(x) > 0]
            if not ids:
                return {}

            cutoff_utc = self._to_utc(cutoff_dt) if cutoff_dt else None
            try:
                first = int(page_size) if page_size is not None else 1000
            except Exception:
                first = 1000
            if first > 1000:
                first = 1000
            if first <= 0:
                first = 1000

            wars_fields = """
              paginatorInfo {
                currentPage
                lastPage
                hasMorePages
              }
              data {
                id
                date
                end_date
                winner_id
                att_id
                def_id
                att_alliance_id
                def_alliance_id
                attacker { id alliance_id }
                defender { id alliance_id }
                reason
                war_type
                ground_control
                air_superiority
                naval_blockade
                attacks {
                  id
                  date
                  att_id
                  attid
                  def_id
                  defid
                  type
                  war_id
                  warid
                  victor
                  success
                  city_id
                  cityid
                  infra_destroyed
                  infradestroyed
                  infra_destroyed_value
                  resistance_lost
                  resistance_eliminated
                  money_stolen
                  moneystolen
                  money_looted
                  att_mun_used
                  def_mun_used
                  att_gas_used
                  def_gas_used
                  att_soldiers_lost
                  def_soldiers_lost
                  att_tanks_lost
                  def_tanks_lost
                  att_aircraft_lost
                  def_aircraft_lost
                  att_ships_lost
                  def_ships_lost
                  att_missiles_lost
                  def_missiles_lost
                  att_nukes_lost
                  def_nukes_lost
                  gasoline_looted
                  munitions_looted
                  aluminum_looted
                  steel_looted
                  food_looted
                  coal_looted
                  oil_looted
                  uranium_looted
                  iron_looted
                  bauxite_looted
                  lead_looted
                }
              }
            """

            def _war_in_window(w: Dict[str, Any]) -> bool:
                if not cutoff_utc:
                    return True
                attacks = w.get('attacks') or []
                for a in attacks or []:
                    try:
                        ad_raw = a.get('date')
                        ad = datetime.fromisoformat(ad_raw.replace('Z', '+00:00')) if ad_raw else None
                        if ad is not None:
                            try:
                                ad = ad.astimezone(self.utc_tz).replace(tzinfo=None) if self.utc_tz is not None else ad.replace(tzinfo=None)
                            except Exception:
                                ad = ad.replace(tzinfo=None)
                    except Exception:
                        ad = None
                    if ad and ad >= cutoff_utc:
                        return True
                for k in ('date', 'end_date'):
                    try:
                        d_raw = w.get(k)
                        d = datetime.fromisoformat(d_raw.replace('Z', '+00:00')) if d_raw else None
                        if d is not None:
                            try:
                                d = d.astimezone(self.utc_tz).replace(tzinfo=None) if self.utc_tz is not None else d.replace(tzinfo=None)
                            except Exception:
                                d = d.replace(tzinfo=None)
                    except Exception:
                        d = None
                    if d and d >= cutoff_utc:
                        return True
                return False

            result: Dict[int, List[Dict[str, Any]]] = {aid: [] for aid in ids}
            seen_ids_per_aid: Dict[int, set] = {aid: set() for aid in ids}

            mode_val = (active_mode or 'both').lower()
            modes = ['active', 'inactive'] if mode_val not in ('active', 'inactive') else [mode_val]

            loop = asyncio.get_running_loop()

            for mode in modes:
                pages: Dict[int, int] = {aid: 1 for aid in ids}
                finished: set = set()

                while len(finished) < len(ids):
                    batch_ids = [aid for aid in ids if aid not in finished][:int(alias_batch_size) if isinstance(alias_batch_size, int) and alias_batch_size and alias_batch_size > 0 else len(ids)]
                    if not batch_ids:
                        break
                    blocks: List[str] = []
                    aliases: List[str] = []
                    for aid in batch_ids:
                        alias = f"a{aid}p{pages[aid]}"
                        aliases.append(alias)
                        blocks.append(
                            f"{alias}: wars(alliance_id: {aid}, first: {first}, page: {pages[aid]}, active: {'true' if mode=='active' else 'false'}) {{\n{wars_fields}\n}}"
                        )
                    query = "query {\n" + "\n".join(blocks) + "\n}"

                    try:
                        data: Dict[str, Any] = await self._request_with_retries(
                            query,
                            timeout=int(request_timeout_seconds) if isinstance(request_timeout_seconds, int) and request_timeout_seconds > 0 else 20,
                            attempts=int(request_retries) if isinstance(request_retries, int) and request_retries and request_retries > 0 else 1,
                        )
                    except Exception:
                        if isinstance(alias_batch_size, int) and alias_batch_size and alias_batch_size > 1:
                            return await self.get_wars_for_alliances_aliased(
                                alliance_ids,
                                page_size=first,
                                active_mode=active_mode,
                                cutoff_dt=cutoff_dt,
                                request_timeout_seconds=request_timeout_seconds,
                                request_retries=1,
                                retry_backoff_seconds=0,
                                alias_batch_size=max(1, int(alias_batch_size) // 2),
                            )
                        seq_map = await self.get_wars_for_alliances(
                            alliance_ids,
                            limit=None,
                            page=1,
                            force_refresh=True,
                            cutoff_dt=cutoff_dt,
                            page_size=first,
                            active_mode=active_mode,
                            request_timeout_seconds=max(60, int(request_timeout_seconds or 20)),
                            request_retries=1,
                            retry_backoff_seconds=0,
                            concurrency_limit=6,
                        )
                        return seq_map

                    root = data.get('data') or {}
                    for aid in batch_ids:
                        alias = f"a{aid}p{pages[aid]}"
                        block = root.get(alias) or {}
                        wars = block.get('data') or []
                        try:
                            pi = block.get('paginatorInfo') or {}
                            last_page = int(pi.get('lastPage') or 0)
                        except Exception:
                            last_page = 0
                        page_all_older_than_cutoff = True if cutoff_utc else False
                        for w in wars:
                            if not cutoff_dt or _war_in_window(w):
                                try:
                                    wid = int(w.get('id') or 0)
                                except Exception:
                                    wid = 0
                                if wid and wid not in seen_ids_per_aid[aid]:
                                    result[aid].append(w)
                                    seen_ids_per_aid[aid].add(wid)
                                    page_all_older_than_cutoff = False
                        # Advance or finish
                        if not wars or (isinstance(last_page, int) and last_page > 0 and pages[aid] >= last_page) or (cutoff_utc and page_all_older_than_cutoff):
                            finished.add(aid)
                        else:
                            pages[aid] += 1

            return result
        except Exception as e:
            self.logger.error(f"get_wars_for_alliances_aliased: failed for alliances {alliance_ids}: {e}")
            return {}
    
    async def get_wars_between_parties(
        self,
        home_alliance_ids: List[int],
        away_alliance_ids: List[int],
        cutoff_dt: Optional[datetime] = None,
        limit: Optional[int] = None,
        force_refresh: bool = True,
    ) -> List[Dict[str, Any]]:
        """Fetch all wars (offensive and defensive) for the given Home vs Away parties,
        combine and deduplicate by war id, filter to wars between the two parties (both directions),
        apply optional time cutoff, save to a unified parties file, and return the wars list.

        This centralizes war collection so downstream consumers calculate exclusively from one saved file.
        """
        try:
            # Normalize and sort party identifiers for deterministic cache key
            home_ids = sorted({int(x) for x in (home_alliance_ids or []) if int(x) > 0})
            away_ids = sorted({int(x) for x in (away_alliance_ids or []) if int(x) > 0})
            home_party_id = "-".join([str(a) for a in home_ids]) or "none"
            away_party_id = "-".join([str(a) for a in away_ids]) or "none"
            parties_key = f"war_parties_{home_party_id}_vs_{away_party_id}"

            # Normalize cutoff to UTC (naive treated as local server TZ)
            cutoff_utc = self._to_utc(cutoff_dt) if cutoff_dt else None

            # Helper to check time window
            def _war_in_window(w: Dict[str, Any]) -> bool:
                if not cutoff_utc:
                    return True
                attacks = w.get('attacks') or []
                for a in attacks or []:
                    try:
                        ad_raw = a.get('date')
                        ad = datetime.fromisoformat(ad_raw.replace('Z', '+00:00')) if ad_raw else None
                        if ad is not None:
                            try:
                                ad = ad.astimezone(self.utc_tz).replace(tzinfo=None) if self.utc_tz is not None else ad.replace(tzinfo=None)
                            except Exception:
                                ad = ad.replace(tzinfo=None)
                    except Exception:
                        ad = None
                    if ad and ad >= cutoff_utc:
                        return True
                for k in ('date', 'end_date'):
                    try:
                        d_raw = w.get(k)
                        d = datetime.fromisoformat(d_raw.replace('Z', '+00:00')) if d_raw else None
                        if d is not None:
                            try:
                                d = d.astimezone(self.utc_tz).replace(tzinfo=None) if self.utc_tz is not None else d.replace(tzinfo=None)
                            except Exception:
                                d = d.replace(tzinfo=None)
                    except Exception:
                        d = None
                    if d and d >= cutoff_utc:
                        return True
                return False

            # Collect wars with two distinct calls: ACTIVE then INACTIVE; deduplicate by id
            combined_map: Dict[int, Dict[str, Any]] = {}
            all_ids = sorted(set(home_ids) | set(away_ids))
            if not all_ids:
                return []

            by_aid = await self.get_wars_for_alliances_aliased(
                all_ids,
                page_size=500,
                active_mode='both',
                cutoff_dt=cutoff_utc,
                request_timeout_seconds=30,
                request_retries=1,
                retry_backoff_seconds=0,
                alias_batch_size=4,
            )
            for aid, wars_list in (by_aid or {}).items():
                for w in wars_list or []:
                    try:
                        wid = int(w.get('id') or 0)
                    except Exception:
                        wid = 0
                if wid and wid not in combined_map:
                    combined_map[wid] = w

            if not combined_map:
                seq_active = await self.get_wars_for_alliances(
                    all_ids,
                    limit=limit,
                    page=1,
                    force_refresh=force_refresh,
                    cutoff_dt=cutoff_utc,
                    page_size=500,
                    active_mode='active',
                    request_timeout_seconds=60,
                    request_retries=1,
                    retry_backoff_seconds=0,
                    concurrency_limit=6,
                )
                seq_inactive = await self.get_wars_for_alliances(
                    all_ids,
                    limit=limit,
                    page=1,
                    force_refresh=force_refresh,
                    cutoff_dt=cutoff_utc,
                    page_size=500,
                    active_mode='inactive',
                    request_timeout_seconds=60,
                    request_retries=1,
                    retry_backoff_seconds=0,
                    concurrency_limit=6,
                )
                for aid, wars_list in (seq_active or {}).items():
                    for w in wars_list or []:
                        try:
                            wid = int(w.get('id') or 0)
                        except Exception:
                            wid = 0
                        if wid and wid not in combined_map:
                            combined_map[wid] = w
                for aid, wars_list in (seq_inactive or {}).items():
                    for w in wars_list or []:
                        try:
                            wid = int(w.get('id') or 0)
                        except Exception:
                            wid = 0
                        if wid and wid not in combined_map:
                            combined_map[wid] = w

            wars_between_map: Dict[int, Dict[str, Any]] = {}
            for w in combined_map.values():
                # Collect candidate alliance IDs for attacker/defender from both top-level and nested fields
                att_ids_candidates: List[int] = []
                def_ids_candidates: List[int] = []
                try:
                    att_ids_candidates.append(int(w.get('att_alliance_id') or 0))
                except Exception:
                    pass
                try:
                    def_ids_candidates.append(int(w.get('def_alliance_id') or 0))
                except Exception:
                    pass
                att_nested = (w.get('attacker') or {})
                def_nested = (w.get('defender') or {})
                try:
                    att_ids_candidates.append(int(att_nested.get('alliance_id') or 0))
                except Exception:
                    pass
                try:
                    def_ids_candidates.append(int(def_nested.get('alliance_id') or 0))
                except Exception:
                    pass
                # Remove zeros and duplicates
                att_ids_candidates = [i for i in {i for i in att_ids_candidates if isinstance(i, int) and i > 0}]
                def_ids_candidates = [i for i in {i for i in def_ids_candidates if isinstance(i, int) and i > 0}]

                # Check any candidate pairing matches Home vs Away (both directions)
                match_forward = any(i in home_ids for i in att_ids_candidates) and any(j in away_ids for j in def_ids_candidates)
                match_reverse = any(i in away_ids for i in att_ids_candidates) and any(j in home_ids for j in def_ids_candidates)

                if (match_forward or match_reverse) and _war_in_window(w):
                    try:
                        wid = int(w.get('id') or 0)
                    except Exception:
                        wid = 0
                    if wid and wid not in wars_between_map:
                        wars_between_map[wid] = w

            wars_between = list(wars_between_map.values())

            try:
                payload = {
                    'role': 'parties',
                    'home_alliances': [{'id': a} for a in home_ids],
                    'away_alliances': [{'id': b} for b in away_ids],
                    'wars': wars_between,
                    'created_at': datetime.now().isoformat(),
                    'total_wars': len(wars_between),
                    'cutoff': cutoff_utc.isoformat() if cutoff_utc else None,
                }
                self._kv_cache[parties_key] = payload
                self._kv_cache_expiry[parties_key] = time.monotonic() + float(self.cache_ttl_seconds or 3600)
            except Exception:
                pass

            return wars_between
        except Exception as e:
            self.logger.error(f"get_wars_between_parties: Error retrieving combined wars: {str(e)}")
            return []

    async def get_party_wars_batched(
        self,
        alliance_ids: List[int],
        side_label: Optional[str] = None,
        cutoff_dt: Optional[datetime] = None,
        limit: Optional[int] = None,
        force_refresh: bool = True,
        page_size: Optional[int] = 1000,
        request_timeout_seconds: Optional[int] = 20,
        request_retries: Optional[int] = 1,
    ) -> List[Dict[str, Any]]:
        """Fetch all wars and actions for a single party (Home or Away) in batched queries.

        - Queries all provided `alliance_ids` together for ACTIVE then INACTIVE wars using aliased GraphQL blocks.
        - Deduplicates by war id across alliances and modes.
        - Applies optional cutoff using attack dates first, then war start/end.
        - Persists to a deterministic `war_party_<side>_<id_join>_wars` file via UserDataManager.
        """
        try:
            # Normalize and sort party identifiers and label
            ids = sorted({int(x) for x in (alliance_ids or []) if str(x).strip() and int(x) > 0})
            if not ids:
                return []
            side = (side_label or "unknown").strip().lower()
            if side not in ("home", "away"):
                side = "unknown"
            party_id = "-".join([str(a) for a in ids]) or "none"
            party_key = f"war_party_{side}_{party_id}_wars"

            # Normalize cutoff to UTC (naive treated as local server TZ)
            cutoff_utc = self._to_utc(cutoff_dt) if cutoff_dt else None

            # Helper to check time window
            def _war_in_window(w: Dict[str, Any]) -> bool:
                if not cutoff_utc:
                    return True
                attacks = w.get('attacks') or []
                for a in attacks or []:
                    try:
                        ad_raw = a.get('date')
                        ad = datetime.fromisoformat(ad_raw.replace('Z', '+00:00')) if ad_raw else None
                        if ad is not None:
                            try:
                                ad = ad.astimezone(self.utc_tz).replace(tzinfo=None) if self.utc_tz is not None else ad.replace(tzinfo=None)
                            except Exception:
                                ad = ad.replace(tzinfo=None)
                    except Exception:
                        ad = None
                    if ad and ad >= cutoff_utc:
                        return True
                for k in ('date', 'end_date'):
                    try:
                        d_raw = w.get(k)
                        d = datetime.fromisoformat(d_raw.replace('Z', '+00:00')) if d_raw else None
                        if d is not None:
                            try:
                                d = d.astimezone(self.utc_tz).replace(tzinfo=None) if self.utc_tz is not None else d.replace(tzinfo=None)
                            except Exception:
                                d = d.replace(tzinfo=None)
                    except Exception:
                        d = None
                    if d and d >= cutoff_utc:
                        return True
                return False

            combined_map: Dict[int, Dict[str, Any]] = {}

            # Fast-mode: temporarily disable inter-request spacing to speed up batched queries
            old_min_interval = getattr(self, "_min_interval_seconds", 0.0)
            try:
                self._min_interval_seconds = 0.0
                # Active wars first for speed
                aliased_map = await self.get_wars_for_alliances_aliased(
                    ids,
                    page_size=500,
                    active_mode='both',
                    cutoff_dt=cutoff_utc,
                    request_timeout_seconds=max(20, int(request_timeout_seconds or 20)),
                    request_retries=1,
                    retry_backoff_seconds=0,
                    alias_batch_size=4,
                )
                for aid, wars_list in (aliased_map or {}).items():
                    for w in wars_list or []:
                        try:
                            wid = int(w.get('id') or 0)
                        except Exception:
                            wid = 0
                        if wid and wid not in combined_map:
                            combined_map[wid] = w
            finally:
                # Restore original rate-limit spacing
                self._min_interval_seconds = (
                    float(old_min_interval) if isinstance(old_min_interval, (int, float)) else 0.15
                )

            # Apply cutoff and emit list
            wars_party = [w for w in combined_map.values() if _war_in_window(w)] if cutoff_dt else list(combined_map.values())

            try:
                payload = {
                    'role': 'party',
                    'side': side,
                    'alliances': [{'id': a} for a in ids],
                    'wars': wars_party,
                    'created_at': datetime.now().isoformat(),
                    'total_wars': len(wars_party),
                    'cutoff': cutoff_utc.isoformat() if cutoff_utc else None,
                }
                self._kv_cache[party_key] = payload
                self._kv_cache_expiry[party_key] = time.monotonic() + float(self.cache_ttl_seconds or 3600)
            except Exception:
                pass

            return wars_party
        except Exception as e:
            self.logger.error(f"get_party_wars_batched: Error retrieving wars for party {side_label} {alliance_ids}: {str(e)}")
            return []

    async def get_home_and_away_wars_batched(
        self,
        home_alliance_ids: List[int],
        away_alliance_ids: List[int],
        cutoff_dt: Optional[datetime] = None,
        limit: Optional[int] = None,
        force_refresh: bool = True,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Convenience wrapper to fetch Home and Away party wars concurrently in batched mode.

        Returns a dict with keys 'home' and 'away', each containing the party's wars (with actions).
        Persists both party files via `get_party_wars_batched`.
        """
        try:
            home_task = self.get_party_wars_batched(
                home_alliance_ids,
                side_label='home',
                cutoff_dt=cutoff_dt,
                limit=limit,
                force_refresh=force_refresh,
            )
            away_task = self.get_party_wars_batched(
                away_alliance_ids,
                side_label='away',
                cutoff_dt=cutoff_dt,
                limit=limit,
                force_refresh=force_refresh,
            )
            home_wars, away_wars = await asyncio.gather(home_task, away_task)
            return {'home': home_wars or [], 'away': away_wars or []}
        except Exception as e:
            self.logger.error(f"get_home_and_away_wars_batched: Error fetching parties: {str(e)}")
            return {'home': [], 'away': []}
    
    async def _fetch_discord_usernames(self, nations: List[Dict[str, Any]], bot) -> None:
        """Fetch Discord usernames for nations with Discord IDs."""
        
        # Limit concurrent API calls to avoid rate limits
        sem = asyncio.Semaphore(10)

        async def _process_nation(nation):
            discord_id = nation.get('discord_id', '')
            if not discord_id or not str(discord_id).strip():
                return False
            
            try:
                discord_id_int = int(discord_id)
                # Try to fetch Discord user from cache first (fast)
                user = bot.get_user(discord_id_int)
                if user:
                    nation['discord_username'] = user.name
                    nation['discord_display_name'] = user.display_name
                    return True
                
                # If not in cache, try to fetch from API (throttled)
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

        # Process all nations concurrently
        results = await asyncio.gather(*[_process_nation(n) for n in nations])
        discord_fetch_count = sum(1 for r in results if r)
        
        if discord_fetch_count > 0:
            self.logger.info(f"Fetched Discord info for {discord_fetch_count} nations")
    
    async def get_nation_by_id(self, nation_id: str) -> Optional[Dict[str, Any]]:
        """Get a single nation by ID with comprehensive fields.
        
        Args:
            nation_id: The nation ID to query
            
        Returns:
            Nation dictionary or None if not found
        """
        try:
            query = f"""
                query {{
                  nations(id: {nation_id}) {{
                    data {{
                      id
                      nation_name
                      leader_name
                      color
                      flag
                      discord
                      discord_id
                      beige_turns
                      num_cities
                      score
                      espionage_available
                      date
                      last_active
                      soldiers
                      tanks
                      aircraft
                      ships
                      missiles
                      nukes
                      spies
                      wars_won
                      wars_lost
                      offensive_wars_count
                      defensive_wars_count
                      offensive_wars {{
                        id
                        date
                        war_type
                        groundcontrol
                        airsuperiority
                        navalblockade
                        winner
                        turns_left
                      }}
                      defensive_wars {{
                        id
                        date
                        war_type
                        groundcontrol
                        airsuperiority
                        navalblockade
                        winner
                        turns_left
                      }}
                      soldier_casualties
                      tank_casualties
                      aircraft_casualties
                      ship_casualties
                      missile_casualties
                      missile_kills
                      nuke_casualties
                      nuke_kills
                      spy_casualties
                      spy_kills
                      spy_attacks
                      soldier_kills
                      tank_kills
                      aircraft_kills
                      ship_kills
                      money_looted
                      total_infrastructure_destroyed
                      total_infrastructure_lost
                      missile_launch_pad
                      nuclear_research_facility
                      nuclear_launch_facility
                      iron_dome
                      vital_defense_system
                      propaganda_bureau
                      military_research_center
                      space_program
                      activity_center
                      advanced_engineering_corps
                      advanced_pirate_economy
                      arable_land_agency
                      arms_stockpile
                      bauxite_works
                      bureau_of_domestic_affairs
                      center_for_civil_engineering
                      clinical_research_center
                      emergency_gasoline_reserve
                      fallout_shelter
                      green_technologies
                      government_support_agency
                      guiding_satellite
                      central_intelligence_agency
                      international_trade_center
                      iron_works
                      mass_irrigation
                      military_doctrine
                      military_salvage
                      mars_landing
                      pirate_economy
                      recycling_initiative
                      research_and_development_center
                      specialized_police_training_program
                      spy_satellite
                      surveillance_network
                      telecommunications_satellite
                      uranium_enrichment_program
                      military_research {{
                        ground_capacity
                        air_capacity
                        naval_capacity
                        ground_cost
                        air_cost
                        naval_cost
                      }}
                      projects
                      alliance_id
                      alliance_position
                      alliance {{
                        id
                        name
                        acronym
                        flag
                      }}
                      population
                      gross_national_income
                      domestic_policy
                      tax_id
                      cities {{
                        id
                        name
                        infrastructure
                        land
                        powered
                        oil_power
                        wind_power
                        coal_power
                        nuclear_power
                        coal_mine
                        oil_well
                        uranium_mine
                        barracks
                        farm
                        police_station
                        hospital
                        recycling_center
                        subway
                        supermarket
                        bank
                        shopping_mall
                        stadium
                        lead_mine
                        iron_mine
                        bauxite_mine
                        oil_refinery
                        aluminum_refinery
                        steel_mill
                        munitions_factory
                        factory
                        hangar
                        drydock
                      }}
                    }}
                  }}
                }}
            """
            
            # Run blocking HTTP in a thread to avoid blocking event loop
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(None, self._make_request, query)
            
            nations = data.get('data', {}).get('nations', {}).get('data', [])
            if not nations:
                self.logger.warning(f"get_nation_by_id: No nation found with ID {nation_id}")
                return None
            
            return self._normalize_nation(nations[0])
            
        except Exception as e:
            self.logger.error(f"get_nation_by_id: Error retrieving nation {nation_id}: {str(e)}")
            return None
    
    async def get_nation_by_name(self, nation_name: str) -> Optional[Dict[str, Any]]:
        """Get a single nation by name with comprehensive fields.
        
        Args:
            nation_name: The nation name to query
            
        Returns:
            Nation dictionary or None if not found
        """
        try:
            # Escape quotes in nation name for GraphQL and handle spaces
            escaped_name = nation_name.replace('"', '\\"')
            # Wrap the entire nation name in quotes for GraphQL
            query = f"""
                query {{
                  nations(first: 1, nation_name: "{escaped_name}") {{
                    data {{
                      id
                      nation_name
                      leader_name
                      color
                      flag
                      discord
                      discord_id
                      beige_turns
                      num_cities
                      score
                      espionage_available
                      date
                      last_active
                      soldiers
                      tanks
                      aircraft
                      ships
                      missiles
                      nukes
                      spies
                      wars_won
                      wars_lost
                      offensive_wars_count
                      defensive_wars_count
                      offensive_wars {{
                        id
                        date
                        war_type
                        groundcontrol
                        airsuperiority
                        navalblockade
                        winner
                        turns_left
                      }}
                      defensive_wars {{
                        id
                        date
                        war_type
                        groundcontrol
                        airsuperiority
                        navalblockade
                        winner
                        turns_left
                      }}
                      soldier_casualties
                      tank_casualties
                      aircraft_casualties
                      ship_casualties
                      missile_casualties
                      missile_kills
                      nuke_casualties
                      nuke_kills
                      spy_casualties
                      spy_kills
                      spy_attacks
                      soldier_kills
                      tank_kills
                      aircraft_kills
                      ship_kills
                      money_looted
                      total_infrastructure_destroyed
                      total_infrastructure_lost
                      missile_launch_pad
                      nuclear_research_facility
                      nuclear_launch_facility
                      iron_dome
                      vital_defense_system
                      propaganda_bureau
                      military_research_center
                      space_program
                      activity_center
                      advanced_engineering_corps
                      advanced_pirate_economy
                      arable_land_agency
                      arms_stockpile
                      bauxite_works
                      bureau_of_domestic_affairs
                      center_for_civil_engineering
                      clinical_research_center
                      emergency_gasoline_reserve
                      fallout_shelter
                      green_technologies
                      government_support_agency
                      guiding_satellite
                      central_intelligence_agency
                      international_trade_center
                      iron_works
                      mass_irrigation
                      military_doctrine
                      military_salvage
                      mars_landing
                      pirate_economy
                      recycling_initiative
                      research_and_development_center
                      specialized_police_training_program
                      spy_satellite
                      surveillance_network
                      telecommunications_satellite
                      uranium_enrichment_program
                      military_research {{
                        ground_capacity
                        air_capacity
                        naval_capacity
                        ground_cost
                        air_cost
                        naval_cost
                      }}
                      projects
                      alliance_id
                      alliance_position
                      alliance {{
                        id
                        name
                        acronym
                        flag
                      }}
                      population
                      gross_national_income
                      domestic_policy
                      tax_id
                      cities {{
                        id
                        name
                        infrastructure
                        land
                        powered
                        oil_power
                        wind_power
                        coal_power
                        nuclear_power
                        coal_mine
                        oil_well
                        uranium_mine
                        barracks
                        farm
                        police_station
                        hospital
                        recycling_center
                        subway
                        supermarket
                        bank
                        shopping_mall
                        stadium
                        lead_mine
                        iron_mine
                        bauxite_mine
                        oil_refinery
                        aluminum_refinery
                        steel_mill
                        munitions_factory
                        factory
                        hangar
                        drydock
                      }}
                    }}
                  }}
                }}
            """
            
            
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(None, self._make_request, query)
            
            nations = data.get('data', {}).get('nations', {}).get('data', [])
            if not nations:
                self.logger.warning(f"get_nation_by_name: No nation found with name '{nation_name}'")
                return None
            
            return self._normalize_nation(nations[0])
            
        except Exception as e:
            self.logger.error(f"get_nation_by_name: Error retrieving nation '{nation_name}': {str(e)}")
            return None
    
    async def get_nation_by_leader(self, leader_name: str) -> Optional[Dict[str, Any]]:
        """Get a single nation by leader name with comprehensive fields.
        
        Args:
            leader_name: The leader name to query
            
        Returns:
            Nation dictionary or None if not found
        """
        try:
            # Escape quotes in leader name for GraphQL
            escaped_leader = leader_name.replace('"', '\\"')
            query = f"""
                query {{
                  nations(first: 1, leader_name: "{escaped_leader}") {{
                    data {{
                      id
                      nation_name
                      leader_name
                      color
                      flag
                      discord
                      discord_id
                      beige_turns
                      num_cities
                      score
                      espionage_available
                      date
                      last_active
                      soldiers
                      tanks
                      aircraft
                      ships
                      missiles
                      nukes
                      spies
                      wars_won
                      wars_lost
                      offensive_wars_count
                      defensive_wars_count
                      offensive_wars {{
                        id
                        date
                        war_type
                        groundcontrol
                        airsuperiority
                        navalblockade
                        winner
                        turns_left
                      }}
                      defensive_wars {{
                        id
                        date
                        war_type
                        groundcontrol
                        airsuperiority
                        navalblockade
                        winner
                        turns_left
                      }}
                      soldier_casualties
                      tank_casualties
                      aircraft_casualties
                      ship_casualties
                      missile_casualties
                      missile_kills
                      nuke_casualties
                      nuke_kills
                      spy_casualties
                      spy_kills
                      spy_attacks
                      soldier_kills
                      tank_kills
                      aircraft_kills
                      ship_kills
                      money_looted
                      total_infrastructure_destroyed
                      total_infrastructure_lost
                      missile_launch_pad
                      nuclear_research_facility
                      nuclear_launch_facility
                      iron_dome
                      vital_defense_system
                      propaganda_bureau
                      military_research_center
                      space_program
                      activity_center
                      advanced_engineering_corps
                      advanced_pirate_economy
                      arable_land_agency
                      arms_stockpile
                      bauxite_works
                      bureau_of_domestic_affairs
                      center_for_civil_engineering
                      clinical_research_center
                      emergency_gasoline_reserve
                      fallout_shelter
                      green_technologies
                      government_support_agency
                      guiding_satellite
                      central_intelligence_agency
                      international_trade_center
                      iron_works
                      mass_irrigation
                      military_doctrine
                      military_salvage
                      mars_landing
                      pirate_economy
                      recycling_initiative
                      research_and_development_center
                      specialized_police_training_program
                      spy_satellite
                      surveillance_network
                      telecommunications_satellite
                      uranium_enrichment_program
                      military_research {{
                        ground_capacity
                        air_capacity
                        naval_capacity
                        ground_cost
                        air_cost
                        naval_cost
                      }}
                      projects
                      alliance_id
                      alliance_position
                      alliance {{
                        id
                        name
                        acronym
                        flag
                      }}
                      population
                      gross_national_income
                      domestic_policy
                      tax_id
                      cities {{
                        id
                        name
                        infrastructure
                        stadium
                        barracks
                        factory
                        airforcebase
                        drydock
                      }}
                    }}
                  }}
                }}
            """
            
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(None, self._make_request, query)
            
            nations = data.get('data', {}).get('nations', {}).get('data', [])
            if not nations:
                self.logger.warning(f"get_nation_by_leader: No nation found with leader '{leader_name}'")
                return None
            
            return self._normalize_nation(nations[0])
            
        except Exception as e:
            self.logger.error(f"get_nation_by_leader: Error retrieving nation with leader '{leader_name}': {str(e)}")
            return None

    async def get_projects_data(self, alliance_id: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Get projects data for an alliance with caching."""
        try:
            # Prevent infinite recursion
            cache_key = f"projects_{alliance_id}"
            if cache_key in self._processing_projects:
                self.logger.warning(f"Detected recursive call to get_projects_data for alliance {alliance_id}")
                return self._processing_cache.get(cache_key, {})
            
            # Mark as processing
            self._processing_projects.add(cache_key)
            
            # Get nations data
            nations = await self.get_alliance_nations(alliance_id, force_refresh=force_refresh)
            if not nations:
                self._processing_projects.discard(cache_key)
                return {}
                
            # Process project data
            project_counts = {}
            for nation in nations:
                for project in nation.get('projects', []):
                    project_counts[project] = project_counts.get(project, 0) + 1
            
            # Store in processing cache
            result = {
                'total_nations': len(nations),
                'project_counts': project_counts
            }
            self._processing_cache[cache_key] = result
            
            # Remove from processing set
            self._processing_projects.discard(cache_key)
            
            return result
        except Exception as e:
            self.logger.error(f"get_projects_data: Error processing projects: {str(e)}")
            if cache_key in self._processing_projects:
                self._processing_projects.discard(cache_key)
            return {}
            
    async def get_improvements_data(self, alliance_id: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Get improvements data for an alliance with caching."""
        try:
            # Prevent infinite recursion
            cache_key = f"improvements_{alliance_id}"
            if cache_key in self._processing_improvements:
                self.logger.warning(f"Detected recursive call to get_improvements_data for alliance {alliance_id}")
                return self._processing_cache.get(cache_key, {})
            
            # Mark as processing
            self._processing_improvements.add(cache_key)
            
            # Get nations data
            nations = await self.get_alliance_nations(alliance_id, force_refresh=force_refresh)
            if not nations:
                self._processing_improvements.discard(cache_key)
                return {}
                
            # Process improvements data
            improvements_counts = {}
            for nation in nations:
                for city in nation.get('cities', []):
                    for improvement, count in city.items():
                        if improvement not in ['id', 'name', 'date', 'infrastructure', 'land', 'powered', 'nuke_date']:
                            improvements_counts[improvement] = improvements_counts.get(improvement, 0) + count
            
            # Store in processing cache
            result = {
                'total_nations': len(nations),
                'improvements_counts': improvements_counts
            }
            self._processing_cache[cache_key] = result
            
            # Remove from processing set
            self._processing_improvements.discard(cache_key)
            
            return result
        except Exception as e:
            self.logger.error(f"get_improvements_data: Error processing improvements: {str(e)}")
            if cache_key in self._processing_improvements:
                self._processing_improvements.discard(cache_key)
            return {}
            
    async def get_cache_info(self) -> Dict[str, Any]:
        try:
            info = []
            now_mono = time.monotonic()
            for k, v in list(self._kv_cache.items()):
                if not isinstance(k, str):
                    continue
                if not k.startswith('alliance_'):
                    continue
                try:
                    ttl_exp = float(self._kv_cache_expiry.get(k, 0.0) or 0.0)
                except Exception:
                    ttl_exp = 0.0
                ttl_remaining = max(0, int(ttl_exp - now_mono)) if ttl_exp > 0 else 0
                alliance_id = (v or {}).get('alliance_id') if isinstance(v, dict) else None
                if not alliance_id and k.startswith('alliance_'):
                    alliance_id = k.replace('alliance_', '')
                count = len((v or {}).get('nations') or []) if isinstance(v, dict) else 0
                info.append({
                    'key': k,
                    'alliance_id': str(alliance_id) if alliance_id is not None else '',
                    'count': count,
                    'ttl_remaining_seconds': ttl_remaining,
                })
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

    async def get_nations_by_color(self, color: str, first: int = 100) -> Optional[List[Dict[str, Any]]]:
        """Get nations filtered by color.
        
        Args:
            color: Color name to filter by (e.g., "beige", "green", "blue")
            first: Number of nations to fetch (default: 100)
            
        Returns:
            List of nation dictionaries or None if failed
        """
        try:
            loop = asyncio.get_running_loop()
            query = f"""
                query {{
                  nations(color: "{color}", first: {first}) {{
                    paginatorInfo {{ currentPage lastPage hasMorePages }}
                    data {{
                      id
                      nation_name
                      leader_name
                      color
                      score
                      population
                      num_cities
                      last_active
                      gross_national_income
                      gross_domestic_product
                    }}
                  }}
                }}
            """
            
            data = await loop.run_in_executor(None, self._make_request, query)
            nations_data = (data.get('data') or {}).get('nations') or {}
            nations_list = nations_data.get('data') or []
            
            if not nations_list:
                return []
                
            # Normalize the nation data
            normalized_nations = []
            for nation in nations_list:
                normalized_nations.append(self._normalize_nation(nation))
                
            return normalized_nations
            
        except Exception as e:
            self.logger.error(f"Error fetching nations by color {color}: {e}")
            return None

    def _calculate_turn_bonus_for_color(self, nations: List[Dict[str, Any]], color: str) -> float:
        """Calculate turn bonus for a color based on nation economic data.
        
        Args:
            nations: List of nation dictionaries for the color
            color: Color name
            
        Returns:
            Turn bonus value in dollars (economic value)
        """
        try:
            # Special case for beige - always $50,000
            if color.lower() == 'beige':
                return 50000.0
            
            if not nations:
                # For gray and other colors with no nations, return 0
                if color.lower() == 'gray':
                    return 0.0
                # For other colors, estimate based on typical values
                return 75000.0  # Default middle value
            
            # Calculate total economic value of all nations in the color
            total_gdp = 0.0
            total_gni = 0.0
            active_nations = 0
            
            for nation in nations:
                # Skip inactive or invalid nations
                if not nation or nation.get('vacation_mode_turns', 0) > 0:
                    continue
                    
                # Get economic data
                gdp = nation.get('gross_domestic_product', 0) or 0
                gni = nation.get('gross_national_income', 0) or 0
                
                # If GDP/GNI not available, estimate from population and score
                if gdp == 0 and gni == 0:
                    population = nation.get('population', 0) or 0
                    score = nation.get('score', 0) or 0
                    
                    # Rough estimation based on typical game values
                    if population > 0 and score > 0:
                        # Estimate GDP based on population and infrastructure (score)
                        estimated_income_per_capita = max(50, score / 10)  # Minimum $50 per capita
                        gdp = estimated_income_per_capita * population * 365.25  # Annual GDP
                        gni = gdp * 1.1  # GNI is typically slightly higher than GDP
                
                total_gdp += gdp
                total_gni += gni
                active_nations += 1
            
            if active_nations == 0:
                return 0.0
            
            # Calculate average economic indicators
            avg_gdp = total_gdp / active_nations
            avg_gni = total_gni / active_nations
            
            # Calculate turn bonus based on economic factors
            # This is a simplified version of the actual P&W formula
            # The real formula considers multiple factors including:
            # - Total economic output of the bloc
            # - Number of nations in the bloc
            # - Economic diversity and stability
            
            base_bonus = (avg_gdp + avg_gni) / 1000000  # Convert to millions
            
            # Scale factor based on number of nations (more nations = more trade opportunities)
            nation_multiplier = min(2.0, 1.0 + (active_nations / 100))  # Cap at 2x multiplier
            
            # Calculate final bonus (capped at $125,000)
            turn_bonus = base_bonus * nation_multiplier * 25000  # Scale to reasonable dollar amount
            
            # Apply cap
            return min(125000.0, max(0.0, turn_bonus))
                
        except Exception as e:
            self.logger.error(f"Error calculating turn bonus for color {color}: {e}")
            # Fallback to reasonable defaults
            if color.lower() == 'beige':
                return 50000.0
            elif color.lower() == 'gray':
                return 0.0
            else:
                return 75000.0  # Default middle value

    async def _fetch_colors_from_api(self) -> Optional[List[Dict[str, Any]]]:
        """Fetch color data from the GraphQL API colors endpoint.
        
        Returns:
            List of color dictionaries from API, or None if error
        """
        query = """
        query {
            colors {
                color
                bloc_name
                turn_bonus
            }
        }
        """
        
        try:
            # Use the actual _make_request method that exists in the class
            response = await self._request_with_retries(query)
            if response and 'data' in response and 'colors' in response['data']:
                return response['data']['colors']
            else:
                self.logger.error(f"Invalid response from colors API: {response}")
                return None
        except Exception as e:
            self.logger.error(f"Error fetching colors from API: {e}")
            return None

    async def get_color_info(self, color: str = None) -> Optional[List[Dict[str, Any]]]:
        """Get color bloc information with turn bonus data from the P&W GraphQL API.
        
        This method fetches actual color data from the API colors endpoint including 
        dynamic bloc names and economic turn bonus values as voted by players in-game.
        
        Args:
            color: Optional color name to filter by (e.g., "beige", "green", "blue")
            
        Returns:
            List of color dictionaries with color, bloc_name, and turn_bonus fields,
            or None if not found. If no color specified, returns all colors.
            Turn bonus values are actual economic values from the game API (e.g., 197214.00).
        """
        try:
            # Fetch color data from the API
            api_colors = await self._fetch_colors_from_api()
            if not api_colors:
                return None
            
            if color:
                # Return specific color if it exists
                color_lower = color.lower()
                for api_color in api_colors:
                    if api_color['color'].lower() == color_lower:
                        return [{
                            'color': api_color['color'],
                            'bloc_name': api_color['bloc_name'],
                            'turn_bonus': float(api_color['turn_bonus'])  # Convert to float for consistency
                        }]
                return None
            else:
                # Return all colors
                result = []
                for api_color in api_colors:
                    result.append({
                        'color': api_color['color'],
                        'bloc_name': api_color['bloc_name'],
                        'turn_bonus': float(api_color['turn_bonus'])  # Convert to float for consistency
                    })
                return result
                
        except Exception as e:
            self.logger.error(f"Error fetching color info: {e}")
            return None

# Convenience function for creating a query instance
def create_query_instance(api_key: str = None, logger: logging.Logger = None) -> PNWAPIQuery:
    """Create a new PNWAPIQuery instance.
    
    Args:
        api_key: P&W API key. If None, will use PANDW_API_KEY from config.
        logger: Logger instance. If None, will create a default logger.
        
    Returns:
        PNWAPIQuery instance
    """
    return PNWAPIQuery(api_key=api_key, logger=logger)

# Convenience function for getting color info
async def get_color_info(color: str = None, api_key: str = None, logger: logging.Logger = None) -> Optional[List[Dict[str, Any]]]:
    """Convenience function to get color bloc information.
    
    Args:
        color: Optional color name to filter by (e.g., "beige", "green", "blue")
        api_key: P&W API key. If None, will use PANDW_API_KEY from config.
        logger: Logger instance. If None, will create a default logger.
        
    Returns:
        List of color dictionaries with color, bloc_name, and turn_bonus fields,
        or None if not found. If no color specified, returns all colors.
    """
    query_instance = create_query_instance(api_key=api_key, logger=logger)
    return await query_instance.get_color_info(color=color)
