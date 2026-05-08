import discord
from discord.ext import commands
from discord import app_commands
import logging
import re
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import asyncio
import math
from pathlib import Path

from Systems.PnW.Util.query import create_v3_query_instance, V3GraphQuery
import io
import requests
from PIL import Image
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image as ReportLabImage
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER

from Systems.Functions.emoji import (
    resource_emoji, military_codes, get_animated_partial,
    SOLDIER_EMOJI, TANK_EMOJI, JET_EMOJI, SHIP_EMOJI, MISSILE_EMOJI, BOMB_EMOJI, mention, EMOJI_IDS
)
from Systems.Functions.db_paths import GLOBAL_NATIONS_DB_STR, HOLDINGS_DB_STR
from Systems.Functions.nation_emoji_store import get_nation_emoji, strip_emoji_prefix
from Systems.Functions.autocomplete_utils import nation_autocomplete as _nation_autocomplete_util
import Systems.Functions.database_manager as db_manager

class Raids(commands.Cog):
    """Cog for P&W raid target finding with V3 graph queries."""

    def __init__(self, bot, query_instance: V3GraphQuery):
        self.bot = bot
        self.query_instance = query_instance
        self.logger = logging.getLogger(__name__)

        
        # War range constants
        self.WAR_RANGE_MIN = 0.75
        self.WAR_RANGE_MAX = 2.5
        
        # Inactivity threshold (7 days)
        self.INACTIVITY_DAYS = 7

    def has_project(self, nation: Dict[str, Any], project_name: str) -> bool:
        """Check if a nation has a specific project."""
        project_mapping = {
            "Missile Launch Pad": "missile_launch_pad",
            "Space Program": "space_program",
            "Nuclear Research Facility": "nuclear_research_facility",
            "Nuclear Launch Facility": "nuclear_launch_facility",
            "Iron Dome": "iron_dome",
            "Vital Defense System": "vital_defense_system",
        }
        field_name = project_mapping.get(project_name)
        if field_name:
            return nation.get(field_name, False)
        return False

    async def _fetch_page(self, page: int, min_score: Optional[float], max_score: Optional[float]) -> Optional[dict]:
        """Helper function to fetch a single page of nations from the API."""
        try:
            score_filters = []
            if min_score is not None:
                score_filters.append(f"min_score: {min_score}")
            if max_score is not None:
                score_filters.append(f"max_score: {max_score}")
            score_filter_str = ", ".join(score_filters)
            if score_filter_str:
                score_filter_str = f", {score_filter_str}"

            query = f'''
            query RaidsFetchPage {{
              nations(first: 100, page: {page}{score_filter_str},vmode: false){{
                paginatorInfo {{
                  currentPage
                  lastPage
                  hasMorePages
                }}
                data {{
                  id nation_name leader_name score num_cities
                  soldiers tanks aircraft ships missiles nukes  
                  vacation_mode_turns beige_turns last_active
                  defensive_wars_count war_policy
                  alliance {{ id name }}
                  missile_launch_pad space_program nuclear_research_facility nuclear_launch_facility iron_dome vital_defense_system
                  domestic_policy color continent population
                  iron_works bauxite_works arms_stockpile emergency_gasoline_reserve
                  mass_irrigation international_trade_center telecommunications_satellite
                  recycling_initiative green_technologies clinical_research_center
                  specialized_police_training_program uranium_enrichment_program
                  fallout_shelter government_support_agency bureau_of_domestic_affairs
                  cities {{
                    id infrastructure land date
                    wind_power nuclear_power oil_power coal_power
                    coal_mine oil_well bauxite_mine iron_mine lead_mine uranium_mine
                    farm oil_refinery steel_mill aluminum_refinery munitions_factory
                    police_station hospital recycling_center subway supermarket
                    bank shopping_mall stadium barracks factory hangar drydock
                  }}
                  bankrecs(limit: 30, orderBy: [{{ column: DATE, order: DESC }}]) {{
                      id date
                      sender_id sender_type
                      receiver_id receiver_type
                      money coal oil uranium iron bauxite lead
                      gasoline munitions steel aluminum food
                  }}
                  wars(limit: 1, status: INACTIVE, orderBy: {{ column: DATE, order: DESC }}) {{
                      id date end_date war_type
                      att_money_looted def_money_looted
                      winner_id
                      att_id def_id
                      attacker {{ id nation_name leader_name }}
                      defender {{ id nation_name leader_name }}
                      attacks {{
                          id date type
                          money_stolen money_destroyed
                          money_looted coal_looted oil_looted uranium_looted iron_looted
                          bauxite_looted lead_looted gasoline_looted munitions_looted
                          steel_looted aluminum_looted food_looted
                          att_id def_id
                      }}
                    }}
                  }}
                }}
              }}
            '''
            data = await self.query_instance._request_with_retries(query, timeout=60)
            return data.get('data', {}).get('nations')
        except Exception as e:
            self.logger.error(f"Error fetching nations page {page}: {e}")
            return None

    async def _fetch_all_nations_local(
        self,
        min_score: Optional[float] = None,
        max_score: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch raid candidates from GlobalNations.db — no API call.
        Returns nations with cities attached for revenue calculation.
        """
        try:
            import sqlite3
            from PnWHarvester.db.global_nations_db import GlobalNationsDB
            db = GlobalNationsDB(GLOBAL_NATIONS_DB_STR)

            async with db._lock:
                with sqlite3.connect(db.db_path) as conn:
                    conn.row_factory = sqlite3.Row

                    score_clause = ""
                    params: list = []
                    if min_score is not None and max_score is not None:
                        score_clause = "AND score BETWEEN ? AND ?"
                        params = [min_score, max_score]
                    elif min_score is not None:
                        score_clause = "AND score >= ?"
                        params = [min_score]
                    elif max_score is not None:
                        score_clause = "AND score <= ?"
                        params = [max_score]

                    rows = conn.execute(
                        f"""SELECT * FROM nations
                            WHERE vacation_mode_turns = 0
                              AND nation_name IS NOT NULL
                              AND nation_name != ''
                              {score_clause}
                            ORDER BY score""",
                        params
                    ).fetchall()
                    nations = [dict(r) for r in rows]

                    if nations:
                        nation_ids = [n["id"] for n in nations]
                        placeholders = ",".join("?" * len(nation_ids))
                        city_rows = conn.execute(
                            f"SELECT * FROM cities WHERE nation_id IN ({placeholders})",
                            nation_ids
                        ).fetchall()
                        cities_by_nation: Dict[int, list] = {}
                        for cr in city_rows:
                            cd = dict(cr)
                            cities_by_nation.setdefault(cd["nation_id"], []).append(cd)
                        for n in nations:
                            n["cities"] = cities_by_nation.get(n["id"], [])
                            n["alliance"] = {
                                "id":   n.get("alliance_id"),
                                "name": n.get("alliance_name", "None"),
                            }

                    self.logger.info(f"Loaded {len(nations)} nations from GlobalNations.db")
                    return nations
        except Exception as e:
            self.logger.error(f"_fetch_all_nations_local error: {e}", exc_info=True)
            return []

    async def _get_attacker_nation_data(self, nation_identifier: str) -> Optional[Dict[str, Any]]:
        """
        Look up the attacking nation from local DBs (no API call).
        Checks GlobalNationsDB first (all nations), falls back to IRSNationsDB.
        """
        self.logger.info(f"Looking up attacker from local DB: {nation_identifier}")
        try:
            clean_id = strip_emoji_prefix(nation_identifier)
            self.logger.info(f"Cleaned identifier: '{clean_id}'")

            from PnWHarvester.db.global_nations_db import GlobalNationsDB
            global_db = GlobalNationsDB(GLOBAL_NATIONS_DB_STR)

            if clean_id.isdigit():
                nation = await global_db.get_nation(int(clean_id))
                if nation:
                    nation["cities"] = await global_db.get_cities_for_nation(int(clean_id))
                    return nation
            else:
                nation = await global_db.get_nation_by_name(clean_id)
                if nation:
                    nation["cities"] = await global_db.get_cities_for_nation(int(nation["id"]))
                    return nation

            # Fall back to API — GlobalNations.db didn't have this nation
            self.logger.warning(f"Nation '{clean_id}' not found in GlobalNations.db.")
            return None
        except Exception as e:
            self.logger.error(f"Error fetching attacker nation from DB: {e}", exc_info=True)
            return None

    async def _get_best_sell_prices(self) -> Dict[str, float]:
        """Get the best sell prices for all resources from the reaper DB."""
        try:
            prices = await db_manager.get_latest_resource_prices()
            if not prices:
                self.logger.warning("No resource prices found in reaper DB.")
                return {}
            price_map = {}
            for resource, data in prices.items():
                sell_price = data.get('sell', 0)
                if sell_price and sell_price > 0:
                    price_map[resource.lower()] = sell_price
            self.logger.info(f"Loaded best sell prices for {len(price_map)} resources from reaper DB.")
            return price_map
        except Exception as e:
            self.logger.error(f"Could not fetch best sell prices from reaper DB: {e}")
            return {}

    def _get_loot_multipliers(self) -> Dict[str, Any]:
        """
        Returns a nested dictionary of multipliers for loot calculation.
        This is self-contained to ensure the correct structure for raid projections.
        """
        self.logger.info("Using self-contained loot multipliers for raid calculations.")
        return {
            # War Type Base Loot Percentage
            "war_type": {
                "ordinary_war": 0.10,
                "raid": 0.075,
                "attrition_war": 0.12,
                "blockade": 0.05, 
            },
            # Offensive policies
            "offense": {
                "pirate": 1.4,         
                "ape": 1.1,            
            },
            # Defensive policies
            "defense": {
                "fortress": 0.9,
                "moneybags": 0.6, # This is a penalty, not a bonus
                "turtle": 1.2,    # Defender loses 20% more loot
                "pirate": 1.1, # Pirate also affects defense
            }
        }

    # ── Revenue helpers ───────────────────────────────────────────────────────

    _TURNS_PER_DAY  = 12
    _TURNS_PER_YEAR = 365 * 12  # 4380

    def _turns_since_last_looted(self, nation: Dict[str, Any]) -> int:
        """Return turns elapsed since the nation was last looted (1 turn = 2 hours).
        Uses holdings last_loot_date."""
        holdings = nation.get("_holdings")
        dt = self._last_looted_dt_from_holdings(holdings) if holdings else None
        if dt is None:
            return 0
        return max(0, int((datetime.now(timezone.utc) - dt).total_seconds() / 7200))

    def _accumulated_revenue_for_nation(self, nation: Dict[str, Any]) -> float:
        """Synchronous stub — use _accumulated_revenue_for_nation_async instead."""
        raise NotImplementedError("Use _accumulated_revenue_for_nation_async")

    async def _accumulated_revenue_for_nation_async(self, nation: Dict[str, Any]) -> float:
        """Estimate money accumulated since the nation was last looted.
        Uses the full city-build revenue engine. Capped at 30 days."""
        turns = self._turns_since_last_looted(nation)
        if turns == 0:
            return 0.0
        if not nation.get("cities"):
            return 0.0
        try:
            from Systems.PnW.Util.rev_correct import calculate_full_revenue_with_query
            result = await calculate_full_revenue_with_query(nation_data=nation, is_war=False)
            net_per_turn = float(result.get("gross_income") or 0.0)
        except Exception as e:
            self.logger.warning(f"Revenue calc failed for {nation.get('id')}: {e}")
            return 0.0
        cap = 30 * self._TURNS_PER_DAY
        return net_per_turn * min(turns, cap)

    def _last_looted_dt_from_holdings(self, holdings: Optional[Dict[str, Any]]) -> Optional[datetime]:
        """Return the last loot datetime from a holdings row."""
        if not holdings:
            return None
        raw = holdings.get("last_loot_date")
        if not raw:
            return None
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00").replace(" ", "T"))
        except Exception:
            return None

    async def _calculate_loot_amount(self, nation: Dict[str, Any], attacker_has_ape: bool, buy_prices: Dict[str, float]) -> Dict[str, float]:
        """
        Holdings-first loot projection.

        Primary path (holdings row exists):
          holdings.money_held and holdings.*_held are the complete picture —
          already net of all spending (city/infra/land/improvements/projects)
          and all transfers (bankrecs). The subscription keeps this current.
          No bankrecs reading needed at query time.

        Fallback path (no holdings row — nation never seen in a loot event):
          Revenue-based accumulation since last_loot_date.

        nation must have _holdings set before calling.
        """
        RESOURCES_LIST = ["coal", "oil", "uranium", "iron", "bauxite", "lead",
                          "gasoline", "munitions", "steel", "aluminum", "food"]

        m        = self._get_loot_multipliers()
        bp       = m["war_type"]["raid"]
        off      = m["offense"]["pirate"] * (m["offense"]["ape"] if attacker_has_ape else 1.0)
        dfn      = m["defense"].get((nation.get("war_policy") or "fortress").lower(), 1.0)
        loot_pct = bp * off * dfn

        holdings: Optional[Dict[str, Any]] = nation.get("_holdings")

        if holdings:
            # ── PRIMARY PATH: holdings is the complete picture ────────────────
            cash_pool = max(0.0, float(holdings.get("money_held") or 0))
            rss_pool  = {
                r: max(0.0, float(holdings.get(f"{r}_held") or 0))
                for r in RESOURCES_LIST
            }
            confidence = holdings.get("confidence", "tracked")
        else:
            # ── FALLBACK PATH: revenue accumulation (no holdings row) ─────────
            turns     = self._turns_since_last_looted(nation)
            cap_turns = 30 * self._TURNS_PER_DAY
            eff_turns = min(turns, cap_turns)

            accum_rev = await self._accumulated_revenue_for_nation_async(nation)
            cash_pt   = accum_rev / eff_turns if eff_turns > 0 else 0.0

            rss_pt: Dict[str, float] = {}
            if nation.get("cities"):
                try:
                    from Systems.PnW.Util.rev_correct import calculate_full_revenue_with_query
                    rev_result = await calculate_full_revenue_with_query(nation_data=nation, is_war=False)
                    rss_pt = {r: float((rev_result.get("resources") or {}).get(r) or 0.0)
                              for r in RESOURCES_LIST}
                except Exception as e:
                    self.logger.warning(f"Resource revenue calc failed for {nation.get('id')}: {e}")

            cash_pool  = max(0.0, cash_pt * eff_turns)
            rss_pool   = {r: max(0.0, rss_pt.get(r, 0) * eff_turns) for r in RESOURCES_LIST}
            confidence = "estimated"

        # ── Project loot from pool ────────────────────────────────────────────
        proj_cash      = cash_pool * loot_pct
        proj_rss       = {r: rss_pool[r] * loot_pct for r in RESOURCES_LIST}
        proj_rss_value = sum(proj_rss[r] * buy_prices.get(r, 0) for r in RESOURCES_LIST)
        total_projected = proj_cash + proj_rss_value

        rss_pool_value   = sum(rss_pool[r] * buy_prices.get(r, 0) for r in RESOURCES_LIST)
        total_pool_value = cash_pool + rss_pool_value

        return {
            "projected_loot":      total_projected,
            "projected_cash":      proj_cash,
            "projected_resources": proj_rss,
            "proj_rss_value":      proj_rss_value,
            "cash_pool":           cash_pool,
            "rss_pool":            rss_pool,
            "rss_pool_value":      rss_pool_value,
            "total_pool_value":    total_pool_value,
            "total_loot_value":    total_projected,
            "confidence":          confidence,
        }

    def _is_in_war_range(self, attacker_score: float, defender_score: float) -> bool:
        """Check if defender is in war range of attacker."""
        ratio = defender_score / attacker_score
        return self.WAR_RANGE_MIN <= ratio <= self.WAR_RANGE_MAX

    def _is_inactive(self, nation: Dict[str, Any]) -> bool:
        """Check if nation is inactive (7+ days)."""
        last_active = nation.get('last_active')
        if not last_active:
            return True
        
        try:
            last_active_dt = datetime.fromisoformat(last_active.replace('Z', '+00:00'))
            days_inactive = (datetime.now(timezone.utc) - last_active_dt).days
            return days_inactive >= self.INACTIVITY_DAYS
        except:
            return True

    def _is_weaker_military(self, attacker: Dict[str, Any], defender: Dict[str, Any]) -> bool:
        """Check if defender has weaker military than attacker using units and projects only."""
        
        # Attacker's military strength (units only)
        attacker_strength = (
            (attacker.get('soldiers', 0) or 0) * 0.1 +
            (attacker.get('tanks', 0) or 0) * 5 +
            (attacker.get('aircraft', 0) or 0) * 50 +
            (attacker.get('ships', 0) or 0) * 100 +
            (attacker.get('missiles', 0) or 0) * 250 +
            (attacker.get('nukes', 0) or 0) * 1000
        )

        # Defender's military strength (units only)
        defender_strength = (
            (defender.get('soldiers', 0) or 0) * 0.1 +
            (defender.get('tanks', 0) or 0) * 5 +
            (defender.get('aircraft', 0) or 0) * 50 +
            (defender.get('ships', 0) or 0) * 100 +
            (defender.get('missiles', 0) or 0) * 250 +
            (defender.get('nukes', 0) or 0) * 1000
        )

        # Consider defensive projects as strength multipliers
        if self.has_project(defender, 'Iron Dome'):
            defender_strength *= 1.1  # 10% defensive bonus
        if self.has_project(defender, 'Vital Defense System'):
            defender_strength *= 1.15  # 15% defensive bonus

        return defender_strength < attacker_strength

    def _parse_loot_filter(self, loot_str: Optional[str]) -> Optional[float]:
        """Parse loot filter string (e.g., 10m, 500k) into a float."""
        if not loot_str:
            return None
        loot_str = loot_str.lower()
        multiplier = 1
        if 'm' in loot_str:
            multiplier = 1_000_000
            loot_str = loot_str.replace('m', '')
        elif 'k' in loot_str:
            multiplier = 1_000
            loot_str = loot_str.replace('k', '')
        try:
            return float(loot_str) * multiplier
        except ValueError:
            return None

    async def _filter_nations_async(self, nations: List[Dict[str, Any]], 
                           attacker_nation: Optional[Dict[str, Any]] = None,
                           attacker_has_ape: bool = False,
                           active_only: bool = True,
                           weak_only: bool = False,
                           min_loot: float = 0,
                           show_beige: bool = False,
                           buy_prices: Dict[str, float] = None,
                           holdings_db=None,
                           excluded_alliance_names: set = None,
                           active_wars_filter: Optional[int] = None):
        """Filter nations using holdings as the sole loot source. No bankrecs needed."""
        sem = asyncio.Semaphore(20)

        # Bulk-fetch all holdings in one query up front
        holdings_map: Dict[int, Dict] = {}
        if holdings_db and nations:
            nation_ids = [int(n.get("id")) for n in nations if n.get("id")]
            holdings_map = await holdings_db.get_holdings_bulk(nation_ids)

        async def _process(nation):
            if nation.get('vacation_mode_turns', 0) > 0:
                return None

            if attacker_nation:
                if not self._is_in_war_range(float(attacker_nation.get('score', 0)), float(nation.get('score', 0))):
                    return None
                if weak_only and not self._is_weaker_military(attacker_nation, nation):
                    return None

            if active_only and self._is_inactive(nation):
                return None

            if not show_beige and nation.get('beige_turns', 0) > 0:
                return None

            def_wars = nation.get('defensive_wars_count', 0)

            # Exclude nations with a full 3 def wars (can't be declared on)
            if def_wars >= 3:
                return None

            # Filter by max defensive war count if requested
            if active_wars_filter is not None and def_wars > active_wars_filter:
                return None

            # Exclude by alliance name (case-insensitive)
            if excluded_alliance_names:
                nation_alliance = (
                    (nation.get("alliance") or {}).get("name")
                    or nation.get("alliance_name")
                    or ""
                ).lower()
                if nation_alliance and nation_alliance in excluded_alliance_names:
                    return None

            async with sem:
                nation_id = int(nation.get('id'))

                # Attach holdings — sole source of truth for loot calculation
                nation['_holdings'] = holdings_map.get(nation_id)

                loot_data  = await self._calculate_loot_amount(nation, attacker_has_ape, buy_prices or {})
                total_loot = loot_data.get('projected_loot', 0)

                if total_loot < min_loot:
                    return None

                nation['calculated_loot'] = loot_data
                nation['total_loot_value'] = total_loot
                return nation

        tasks = [_process(n) for n in nations]
        results = await asyncio.gather(*tasks)
        for r in results:
            if r is not None:
                yield r
            
    async def nation_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for nation — all nations from local databases."""
        try:
            return await _nation_autocomplete_util(current, nw_only=False, limit=25)
        except Exception as e:
            self.logger.warning(f"nation_autocomplete error: {e}")
            return []

    async def alliance_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for exclude_alliances — returns matching alliance names.
        Supports comma-separated input: completes the last token after the final comma."""
        try:
            from PnWHarvester.db.global_nations_db import GlobalNationsDB
            db = GlobalNationsDB(GLOBAL_NATIONS_DB_STR)

            # Split on comma and complete only the last segment
            parts = current.split(",")
            search_term = parts[-1].strip()
            already_chosen = [p.strip() for p in parts[:-1] if p.strip()]

            alliances = await db.get_distinct_alliances(current=search_term)

            choices = []
            for a in alliances:
                name = a.get("alliance_name") or ""
                if not name:
                    continue
                # Skip alliances already in the comma-separated list
                if name in already_chosen:
                    continue
                # Build the full value: keep prior selections + this one
                if already_chosen:
                    value = ", ".join(already_chosen) + ", " + name
                else:
                    value = name
                # Discord choice values max 100 chars
                if len(value) > 100:
                    continue
                choices.append(app_commands.Choice(name=value, value=value))
                if len(choices) >= 25:
                    break
            return choices
        except Exception as e:
            self.logger.warning(f"alliance_autocomplete error: {e}")
            return []

    @app_commands.command(name="raids", description="Find raid targets using last looted amount")
    @app_commands.describe(
        nation="Your nation name (for war range calculation)",
        active="Show only active nations (True) or inactive 7+ days (False)",
        weak="Show only nations with weaker military than yours",
        min_loot="Minimum loot amount to show",
        beige="Show beige nations (True) or hide them (False, default)",
        targets="Number of targets to show (defaults to 20)",
        display="How to display the results (Message or PDF)",
        exclude_alliances="Exclude nations from these alliances (comma-separated, use autocomplete)",
        active_wars="Filter by number of ongoing defensive wars (0, 1, or 2)",
    )
    @app_commands.autocomplete(nation=nation_autocomplete, exclude_alliances=alliance_autocomplete)
    @app_commands.choices(
        display=[
            app_commands.Choice(name="Message", value="message"),
            app_commands.Choice(name="PDF", value="pdf"),
        ],
        active_wars=[
            app_commands.Choice(name="0 — no active def wars", value=0),
            app_commands.Choice(name="1 — 1 or fewer active def wars", value=1),
            app_commands.Choice(name="2 — 2 or fewer active def wars", value=2),
        ],
    )
    async def raids(self, interaction: discord.Interaction, 
                    nation: Optional[str] = None,
                    active: bool = True,
                    weak: bool = False,
                    min_loot: Optional[str] = None,
                    beige: bool = False,
                    targets: Optional[int] = 20,
                    display: str = "message",
                    exclude_alliances: Optional[str] = None,
                    active_wars: Optional[int] = None):
        """Find raid targets based on specified criteria."""
        try:
            # Defer interaction
            await interaction.response.defer(thinking=True)

            attacker_nation = None
            attacker_has_ape = False
            if nation:
                attacker_nation = await self._get_attacker_nation_data(nation)
                if not attacker_nation:
                    await interaction.followup.send(f"❌ Nation '{nation}' not found.")
                    return
                attacker_has_ape = attacker_nation.get('advanced_pirate_economy', False)
            
            # Parse loot filter
            min_loot_val = self._parse_loot_filter(min_loot)

            # Parse excluded alliances — split on comma, normalise to lowercase set
            excluded_alliance_names: set = set()
            if exclude_alliances:
                excluded_alliance_names = {
                    a.strip().lower() for a in exclude_alliances.split(",") if a.strip()
                }
            
            # Calculate score range for the query
            min_score, max_score = None, None
            if attacker_nation:
                attacker_score = float(attacker_nation.get('score', 0))
                if attacker_score > 0:
                    min_score = attacker_score * self.WAR_RANGE_MIN
                    max_score = attacker_score * self.WAR_RANGE_MAX

            self.logger.info("Fetching raid data from GlobalNations.db...")
            all_nations = await self._fetch_all_nations_local(min_score=min_score, max_score=max_score)

            self.logger.info("Fetching resource prices from reaper DB...")
            buy_prices = await self._get_best_sell_prices()
            self.logger.info(f"Fetched prices for {len(buy_prices)} resources.")

            # Open holdings DB — sole source of truth for loot estimation
            from PnWHarvester.db.holdings_db import HoldingsDB
            holdings_db = HoldingsDB(HOLDINGS_DB_STR)

            # Filter nations based on criteria
            self.logger.info(f"Filtering {len(all_nations)} nations...")
            raid_targets = []
            async for nation in self._filter_nations_async(
                all_nations,
                attacker_nation=attacker_nation,
                attacker_has_ape=attacker_has_ape,
                active_only=active,
                weak_only=weak,
                min_loot=min_loot_val or 0,
                show_beige=beige,
                buy_prices=buy_prices,
                holdings_db=holdings_db,
                excluded_alliance_names=excluded_alliance_names,
                active_wars_filter=active_wars,
            ):
                raid_targets.append(nation)
            
            # Sort by loot value (highest first)
            raid_targets.sort(key=lambda x: x.get('total_loot_value', 0), reverse=True)
            
            self.logger.info(f"Found {len(raid_targets)} raid targets")
            
            if not raid_targets:
                await interaction.followup.send("❌ No raid targets found matching your criteria.")
                return
            
            # Display results
            if display == "pdf":
                pdf_file = await self._generate_raids_pdf(raid_targets)
                await interaction.followup.send(file=pdf_file)
            else:
                messages = self._create_message_output(raid_targets, targets)
                # Send first message
                await interaction.followup.send(messages[0])
                # Send additional messages if needed
                for message in messages[1:]:
                    await interaction.followup.send(message)

        except Exception as e:
            self.logger.error(f"Error in raids command: {e}", exc_info=True)
            await interaction.followup.send(f"❌ An error occurred while finding raid targets: {str(e)}")

    def _create_message_output(self, raid_targets: List[Dict[str, Any]], num_targets: int) -> List[str]:
        """Create plain text messages for the raid targets, splitting if needed for Discord character limit."""
        # Discord character limit is 2000, but we'll use 1800 to be safe
        DISCORD_LIMIT = 1800
        
        messages = []
        current_message = []
        current_length = 0
        
        for i, target in enumerate(raid_targets[:num_targets]):
            loot_data = target.get('calculated_loot', {})
            total_loot = target.get('total_loot_value', 0)
            
            nation_name = target.get('nation_name', 'Unknown')
            leader_name = target.get('leader_name', 'Unknown')
            nation_id = target.get('id', 0)
            nation_url = f"https://politicsandwar.com/nation/id={nation_id}"
            header_name = f"[{nation_name}](<{nation_url}>)"
            
            alliance_name = target.get('alliance', {}).get('name') if target.get('alliance') else 'None'
            
            score = float(target.get('score', 0))
            cities = target.get('num_cities', 0)
            
            beige_turns = target.get('beige_turns', 0)
            beige_info = f"\nBeige Turns: {beige_turns}" if beige_turns > 0 else ""
            
            previous_loot = loot_data.get('previous_loot_total', 0)
            previous_info = f" (prev: ${previous_loot:,.0f})" if previous_loot > 0 else ""
            
            mmr_string = None
            try:
                alliance_cog = self.bot.get_cog("AllianceManager")
                if alliance_cog and hasattr(alliance_cog, 'calc_system'):
                    building_ratios = alliance_cog.calc_system.calculate_building_ratios(target)
                    if building_ratios and isinstance(building_ratios, dict):
                        mmr = building_ratios.get('mmr_string')
                        if mmr and mmr != '0/0/0/0' and mmr != '0.0/0.0/0.0/0.0':
                            mmr_string = mmr
            except Exception:
                pass

            projects_info = []
            has_missile_launch = self.has_project(target, 'Missile Launch Pad')
            has_space_program = self.has_project(target, 'Space Program')
            has_nuke_research = self.has_project(target, 'Nuclear Research Facility')
            has_nuke_launch = self.has_project(target, 'Nuclear Launch Facility')
            has_iron_dome = self.has_project(target, 'Iron Dome')
            has_vital_defense = self.has_project(target, 'Vital Defense System')

            # Build emoji string for projects
            project_emojis = []
            
            # Missile capabilities
            if has_missile_launch:
                missile_capacity = 3 if has_space_program else 2
                project_emojis.append(mention('missile') * missile_capacity)
            
            # Iron Dome
            if has_iron_dome:
                project_emojis.append(mention('dome'))
            
            # Nuke capabilities
            if has_nuke_research:
                nuke_capacity = 2 if has_nuke_launch else 1
                project_emojis.append(mention('bomb') * nuke_capacity)
            
            # Vital Defense System
            if has_vital_defense:
                project_emojis.append(mention('vital'))
            
            field_value = (
                f"**#{i+1}. {header_name}**\n"
                f"**Leader:** {leader_name}\n"
                f"**Score:** {score:,.0f}\n"
                f"**Cities:** {cities}{beige_info}\n"
                f"**Alliance:** {alliance_name}\n"
                f"**Units:** {SOLDIER_EMOJI}{target.get('soldiers', 0):,} "
                f"{TANK_EMOJI}{target.get('tanks', 0):,} "
                f"{JET_EMOJI}{target.get('aircraft', 0):,} "
                f"{SHIP_EMOJI}{target.get('ships', 0):,}\n"
                f"**Projects:** {' '.join(project_emojis) or 'None'}\n"
                f"**Est. Loot:** ${total_loot:,.0f}{previous_info}"
            )
            
            # Check if adding this target would exceed Discord limit
            if current_length + len(field_value) > DISCORD_LIMIT:
                # Add current message to messages list and start new one
                if current_message:
                    messages.append("\n\n".join(current_message))
                current_message = [field_value]
                current_length = len(field_value)
            else:
                # Add to current message
                current_message.append(field_value)
                current_length += len(field_value)
        
        # Add any remaining targets
        if current_message:
            messages.append("\n\n".join(current_message))
        
        # Add footer message if needed
        if len(raid_targets) > num_targets:
            footer = f"Showing top {num_targets} targets. {len(raid_targets) - num_targets} more available."
            # Check if we can add footer to last message or need new one
            if messages and len(messages[-1]) + len(footer) < DISCORD_LIMIT:
                messages[-1] += f"\n\n{footer}"
            else:
                messages.append(footer)
        
        return messages

    async def _get_emoji_image(self, emoji_name: str) -> ReportLabImage:
        """Fetch an emoji image from Discord's CDN and return it as a ReportLab Image object."""
        emoji_id = EMOJI_IDS.get(emoji_name)
        if not emoji_id:
            return None
        
        url = f"https://cdn.discordapp.com/emojis/{emoji_id}.png"
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            image_data = io.BytesIO(response.content)
            img = ReportLabImage(image_data, width=16, height=16)
            return img
        except Exception as e:
            self.logger.warning(f"Could not fetch emoji image for {emoji_name}: {e}")
            return None

    async def _generate_raids_pdf(self, raid_targets: List[Dict[str, Any]]) -> discord.File:
        """Generate a rich PDF file for the raid targets."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, rightMargin=inch/4, leftMargin=inch/4, topMargin=inch/2, bottomMargin=inch/2)
        styles = getSampleStyleSheet()
        story = []

        for target in raid_targets:
            loot_data = target.get('calculated_loot', {})
            total_loot = target.get('total_loot_value', 0)
            
            nation_name = target.get('nation_name', 'Unknown')
            leader_name = target.get('leader_name', 'Unknown')
            nation_id = target.get('id', 0)
            nation_url = f"https://politicsandwar.com/nation/id={nation_id}"
            header_name = f'<a href="{nation_url}">{nation_name}</a>'
            
            alliance_name = target.get('alliance', {}).get('name') if target.get('alliance') else 'None'
            
            score = float(target.get('score', 0))
            cities = target.get('num_cities', 0)
            
            beige_turns = target.get('beige_turns', 0)
            beige_info = f" | Beige Turns: {beige_turns}" if beige_turns > 0 else ""
            
            previous_loot = loot_data.get('previous_loot_total', 0)
            previous_info = f" (prev: ${previous_loot:,.0f})" if previous_loot > 0 else ""
            
            # Projects - clean emoji display
            projects_data = []
            has_missile_launch = self.has_project(target, 'Missile Launch Pad')
            has_space_program = self.has_project(target, 'Space Program')
            has_nuke_research = self.has_project(target, 'Nuclear Research Facility')
            has_nuke_launch = self.has_project(target, 'Nuclear Launch Facility')
            has_iron_dome = self.has_project(target, 'Iron Dome')
            has_vital_defense = self.has_project(target, 'Vital Defense System')

            # Build project emoji list for clean display
            project_items = []
            
            # Missile capabilities
            if has_missile_launch:
                missile_capacity = 3 if has_space_program else 2
                project_items.extend([await self._get_emoji_image('missile')] * missile_capacity)
            
            # Iron Dome
            if has_iron_dome:
                project_items.append(await self._get_emoji_image('dome'))
            
            # Nuke capabilities
            if has_nuke_research:
                nuke_capacity = 2 if has_nuke_launch else 1
                project_items.extend([await self._get_emoji_image('bomb')] * nuke_capacity)
            
            # Vital Defense System
            if has_vital_defense:
                project_items.append(await self._get_emoji_image('vital'))
            
            # Add project items to display
            if project_items:
                projects_data.append(project_items)
            else:
                projects_data.append([Paragraph("None", styles['Normal'])])

            # Units (Current only)
            units_current_data = [
                [
                    await self._get_emoji_image('soldier'), Paragraph(f"{target.get('soldiers', 0):,}", styles['Normal']),
                    await self._get_emoji_image('tank'), Paragraph(f"{target.get('tanks', 0):,}", styles['Normal']),
                ],
                [
                    await self._get_emoji_image('jet'), Paragraph(f"{target.get('aircraft', 0):,}", styles['Normal']),
                    await self._get_emoji_image('ship'), Paragraph(f"{target.get('ships', 0):,}", styles['Normal']),
                ]
            ]
            units_current_table = Table(units_current_data, colWidths=[20, (doc.width-80)/2, 20, (doc.width-80)/2])
            units_current_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))

            # Main table for the target
            target_table_data = [
                [Paragraph(header_name, styles['h2'])],
                [Paragraph(f"Leader: {leader_name}", styles['Normal'])],
                [Paragraph(f"Score: {score:,.0f} | Cities: {cities}{beige_info}", styles['Normal'])],
                [Paragraph(f"Alliance: {alliance_name}", styles['Normal'])],
                [Table([['Projects:']], colWidths=[doc.width], hAlign='LEFT')],
                [Table(projects_data, colWidths=[doc.width], hAlign='LEFT')],
                [Spacer(1, 0.1*inch)],
                [Paragraph("<b>Current Units:</b>", styles['Normal'])],
                [units_current_table],
                [Spacer(1, 0.1*inch)],
                [Paragraph(f"<b>Est. Loot:</b> ${total_loot:,.0f}{previous_info}", styles['Normal'])],
            ]
            
            story.append(Table(target_table_data, colWidths=[doc.width]))
            story.append(Spacer(1, 0.2*inch))

        doc.build(story)
        buffer.seek(0)
        return discord.File(buffer, filename="raids.pdf")
