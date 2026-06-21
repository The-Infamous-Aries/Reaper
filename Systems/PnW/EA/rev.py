import discord
from discord.ext import commands
from discord import app_commands
from typing import Dict, List, Any, Optional, Union, cast
import asyncio
import logging
from datetime import datetime, timezone
import sys
import os

# Add parent directory for config imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from Systems.PnW.Util.query import V3GraphQuery, create_v3_query_instance
from Systems.Functions import emoji as emoji_mod
from Systems.PnW.Util.rev_correct import calculate_full_revenue_with_query
from Systems.Functions.config import PANDW_API_KEY
from Systems.Functions.db_paths import GLOBAL_NATIONS_DB
from Systems.Functions.nation_emoji_store import get_nation_emoji, get_alliance_emoji, strip_emoji_prefix
from pathlib import Path

logger = logging.getLogger(__name__)

NIGHTS_WATCH_ALLIANCE_ID = 10259

def _get_global_nations_db():
    """Lazy-import GlobalNationsDB so harvester module isn't required at Reaper startup."""
    try:
        from PnWHarvester.db.global_nations_db import GlobalNationsDB
        return GlobalNationsDB(str(GLOBAL_NATIONS_DB))
    except Exception:
        return None

# Create a simple alliance calculator for revenue purposes

class RevenueCommand(commands.Cog):
    """Revenue calculation commands for P&W nations and alliances."""
    
    def __init__(self, bot):
        self.bot = bot
        self.query_instance: Optional[V3GraphQuery] = None  
        self.available_projects = [
            'Activity Center', 'Advanced Engineering Corps', 'Arable Land Agency', 'Bureau of Domestic Affairs',
            'Center Civil Engineering', 'Clinical Research Center', 'Government Support Agency', 'Green Technologies',
            'International Trade Center', 'Advanced Pirate Economy', 'Central Intelligence Agency', 'Guiding Satellite',
            'Iron Dome', 'Missile Launch Pad', 'Nuclear Research Facility', 'Propaganda Bureau', 'Space Program',
            'Vital Defense System', 'Military Research Center', 'Military Doctrine', 'Arms Stockpile', 'Bauxite Works',
            'Emergency Gasoline Reserve', 'Fallout Shelter', 'Iron Works', 'Mars Landing', 'Mass Irrigation',
            'Military Salvage', 'Nuclear Launch Facility', 'Pirate Economy', 'Recycling Initiative',
            'Research & Development Center', 'Specialized Police Training Program', 'Spy Satellite',
            'Surveillance Network', 'Telecommunications Satellite', 'Uranium Enrichment Program'
        ]

    def _get_resource_emoji(self, resource_name: str) -> str:
        """Get emoji for a resource name."""
        return emoji_mod.resource_emoji(resource_name) or ""
    
    async def _get_nights_watch_nations(self) -> List[Dict[str, Any]]:
        """Get all NW nations from GlobalNations.db."""
        try:
            from PnWHarvester.db.global_nations_db import GlobalNationsDB
            from Systems.Functions.db_paths import GLOBAL_NATIONS_DB, NW_ALLIANCE_ID
            db = GlobalNationsDB(str(GLOBAL_NATIONS_DB))
            nations = await db.get_nations_by_alliance(NW_ALLIANCE_ID)
            return nations
        except Exception as e:
            logger.error(f"Error getting NW nations: {e}")
            return []

    async def _get_nation_from_db(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Look up a nation from GlobalNations.db by name or ID.
        GlobalNations.db is the single source of truth — it contains all nations
        including Darkstar members.
        """
        try:
            from PnWHarvester.db.global_nations_db import GlobalNationsDB
            from Systems.Functions.db_paths import GLOBAL_NATIONS_DB
            db = GlobalNationsDB(str(GLOBAL_NATIONS_DB))

            if query.isdigit():
                nation = await db.get_nation(int(query))
                if nation:
                    nation['cities'] = await db.get_cities_for_nation(int(query))
                    return nation
                return None

            # Name search
            nation = await db.get_nation_by_name(query)
            if nation:
                nation['cities'] = await db.get_cities_for_nation(int(nation['id']))
                return nation

            return None
        except Exception as e:
            logger.error(f"Error getting nation from DB: {e}")
            return None
    
    async def nation_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for nation_query — All nations from local databases."""
        try:
            from Systems.Functions.autocomplete_utils import nation_autocomplete
            return await nation_autocomplete(current, nw_only=False, limit=25)
        except Exception as e:
            logger.error(f"Error in rev nation autocomplete: {e}")
            return []
    
    async def alliance_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for alliance names — pulls from GlobalNations.db, emojis from alliance emoji store."""
        try:
            from Systems.Functions.autocomplete_utils import alliance_autocomplete
            return await alliance_autocomplete(current, include_nw=True, limit=25)
        except Exception as e:
            logger.error(f"Error in rev alliance autocomplete: {e}")
            return []
        
    async def project_autocomplete(self, interaction: discord.Interaction, current: str):
        filtered_projects = [
            project for project in self.available_projects
            if current.lower() in project.lower()
        ]
        return [
            app_commands.Choice(name=project, value=project)
            for project in filtered_projects[:25]
        ]
        
    @commands.hybrid_command(name='revenue', aliases=['rev'], description='Calculate revenue for a nation or alliance')
    @app_commands.describe(
        query_type='Type of query: nation or alliance',
        query_value='Nation/Alliance name or ID',
        alliance_color='Alliance color for tax calculation (only used when query_type is alliance)',
        tax_rate='Optional alliance tax rate override (0–100). If omitted, uses the nation\'s actual bracket.'
    )
    @app_commands.choices(
        query_type=[
            app_commands.Choice(name='Nation', value='nation'),
            app_commands.Choice(name='Alliance', value='alliance')
        ],
        alliance_color=[
            app_commands.Choice(name='Beige', value='beige'),
            app_commands.Choice(name='White', value='white'),
            app_commands.Choice(name='Grey', value='grey'),
            app_commands.Choice(name='Black', value='black'),
            app_commands.Choice(name='Gold', value='gold'),
            app_commands.Choice(name='Pink', value='pink'),
            app_commands.Choice(name='Brown', value='brown'),
            app_commands.Choice(name='Mint', value='mint'),
            app_commands.Choice(name='Green', value='green'),
            app_commands.Choice(name='Aqua', value='aqua'),
            app_commands.Choice(name='Lavender', value='lavender'),
            app_commands.Choice(name='Lime', value='lime'),
            app_commands.Choice(name='Maroon', value='maroon'),
            app_commands.Choice(name='Olive', value='olive'),
            app_commands.Choice(name='Yellow', value='yellow'),
            app_commands.Choice(name='Turquoise', value='turquoise'),
            app_commands.Choice(name='Red', value='red'),
            app_commands.Choice(name='Purple', value='purple'),
            app_commands.Choice(name='Orange', value='orange'),
            app_commands.Choice(name='Blue', value='blue'),
        ]
    )
    async def revenue_command(self, ctx: commands.Context, query_type: str, query_value: str, alliance_color: Optional[str] = None, tax_rate: Optional[float] = None) -> None:
        try:
            if not query_value or not query_value.strip():
                await ctx.send("❌ Please provide a valid nation/alliance name or ID. Use `/revenuehelp` for examples.")
                return

            if tax_rate is not None and not (0 <= tax_rate <= 100):
                await ctx.send("❌ Tax rate must be between 0 and 100.")
                return

            query_value = query_value.strip()
            tax_display = f" (tax: {tax_rate:.0f}%)" if tax_rate is not None else ""
            loading_msg = await ctx.send(f"🔄 Calculating revenue for {query_type} '{query_value}'{tax_display}...")

            # Convert percentage to decimal for internal use
            tax_rate_decimal = tax_rate / 100.0 if tax_rate is not None else None

            if query_type == 'nation':
                await self._calculate_nation_revenue(ctx, query_value, loading_msg, tax_rate=tax_rate_decimal)
            else:
                await self._calculate_alliance_revenue(ctx, query_value, loading_msg, tax_rate=tax_rate_decimal, alliance_color=alliance_color)

        except Exception as e:
            logger.error(f"Error in revenue command: {e}")
            error_msg = f"❌ Error calculating revenue: {str(e)}"
            if "not found" in str(e).lower():
                error_msg += "\n💡 Try using the exact name or check your spelling. Use `/revenuehelp` for examples."
            await ctx.send(error_msg)
    
    @revenue_command.autocomplete('query_value')
    async def revenue_query_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for the query_value parameter based on query_type."""
        try:
            # Get the current query_type value
            query_type = interaction.namespace.query_type
            
            if query_type == 'nation':
                return await self.nation_autocomplete(interaction, current)
            elif query_type == 'alliance':
                return await self.alliance_autocomplete(interaction, current)
            else:
                return []
        except Exception as e:
            logger.error(f"Error in autocomplete: {e}")
            return []
    
    async def _calculate_nation_revenue(self, ctx, nation_query: str, loading_msg, tax_rate: Optional[float] = None):
        try:
            # Strip emoji prefix from autocomplete selection
            clean_query = strip_emoji_prefix(nation_query)
            logger.info(f"Starting revenue calculation for: '{nation_query}'")
            
            nation_data = await self._get_nation_from_db(clean_query)
            if not nation_data:
                logger.info(f"Nation not found in database, falling back to API")
                if not self.query_instance:
                    self.query_instance = create_v3_query_instance()
                nation_data = await self.query_instance.get_nation_by_id(clean_query) if clean_query.isdigit() else await self.query_instance.get_nation_by_name(clean_query)
            
            if not nation_data:
                logger.warning(f"Nation '{clean_query}' not found in database or API")
                await loading_msg.edit(content=f"❌ Nation '{clean_query}' not found.")
                return

            logger.info(f"Found nation: {nation_data.get('nation_name', 'Unknown')}")
            await loading_msg.edit(content=f"💰 Calculating revenue for '{nation_data.get('nation_name', clean_query)}'...")
            
            rev_ctx = await self._load_rev_ctx()
            revenue_data = await self._calculate_nation_revenue_data(nation_data, rev_ctx=rev_ctx, tax_rate=tax_rate)
            embed = await self._create_nation_revenue_embed(nation_data, revenue_data)
            await loading_msg.edit(content="", embed=embed)

        except Exception as e:
            logger.error(f"Error calculating nation revenue: {e}", exc_info=True)
            await loading_msg.edit(content=f"❌ Error calculating nation revenue: {str(e)}")

    async def _calculate_alliance_revenue(self, ctx, alliance_query: str, loading_msg, tax_rate: Optional[float] = None, alliance_color: Optional[str] = None):
        try:
            # Strip emoji prefix from autocomplete selection
            clean_query = strip_emoji_prefix(alliance_query)

            # Check if this is NW
            if clean_query.lower() in ["darkstar", "ds"]:
                await loading_msg.edit(content="⭐ Using Darkstar database...")

                # Get all NW nations from GlobalNations.db
                nations = await self._get_nights_watch_nations()
                if not nations:
                    await loading_msg.edit(content="❌ No Darkstar nations found in database.")
                    return

                # Attach cities (get_nations_by_alliance doesn't include cities)
                from PnWHarvester.db.global_nations_db import GlobalNationsDB
                from Systems.Functions.db_paths import GLOBAL_NATIONS_DB as _GNDB
                _db = GlobalNationsDB(str(_GNDB))
                for nation in nations:
                    if not nation.get('cities'):
                        nation['cities'] = await _db.get_cities_for_nation(int(nation['id']))
                
                # Load shared context from DB once for all nations
                rev_ctx = await self._load_rev_ctx()
                
                # Create fake alliance data for IRS
                alliance_data = {
                    'id': NIGHTS_WATCH_ALLIANCE_ID,
                    'name': "Darkstar",
                    'flag': None
                }
                
                alliance_revenue = await self._calculate_alliance_revenue_data(nations, rev_ctx=rev_ctx, tax_rate=tax_rate, alliance_color=alliance_color)
                embed = await self._create_alliance_revenue_embed(alliance_data, alliance_revenue, alliance_color=alliance_color)
                await loading_msg.edit(content="", embed=embed)
                return
            
            # Try GlobalNations.db first (no API call needed)
            global_db = _get_global_nations_db()
            if global_db and GLOBAL_NATIONS_DB.exists():
                # Resolve alliance_id from name if needed
                alliance_id_int = None
                if clean_query.isdigit():
                    alliance_id_int = int(clean_query)
                else:
                    alliances = await global_db.get_distinct_alliances(clean_query)
                    for a in alliances:
                        if (a.get("alliance_name") or "").lower() == clean_query.lower():
                            alliance_id_int = a.get("alliance_id")
                            break
                    if not alliance_id_int and alliances:
                        alliance_id_int = alliances[0].get("alliance_id")

                if alliance_id_int:
                    nations = await global_db.get_nations_by_alliance(alliance_id_int)
                    if nations:
                        # Attach cities to each nation
                        for nation in nations:
                            cities = await global_db.get_cities_for_nation(int(nation["id"]))
                            nation["cities"] = cities

                        rev_ctx = await self._load_rev_ctx()
                        # Get alliance name for embed
                        aname = (nations[0].get("alliance_name") or clean_query) if nations else clean_query
                        alliance_data = {"id": alliance_id_int, "name": aname, "flag": None}
                        alliance_revenue = await self._calculate_alliance_revenue_data(nations, rev_ctx=rev_ctx, tax_rate=tax_rate, alliance_color=alliance_color)
                        embed = await self._create_alliance_revenue_embed(alliance_data, alliance_revenue, alliance_color=alliance_color)
                        await loading_msg.edit(content="", embed=embed)
                        return

            # Fallback to API for alliances not yet in GlobalNations.db
            if not self.query_instance:
                self.query_instance = create_v3_query_instance()

            # Load shared context from DB once for all nations
            rev_ctx = await self._load_rev_ctx()

            alliance_data = await self.query_instance.resolve_alliance(clean_query)
            if not alliance_data:
                await loading_msg.edit(content=f"❌ Alliance '{clean_query}' not found.")
                return

            alliance_id = str(alliance_data.get('id', ''))
            nations = await self.query_instance.get_alliance_nations(alliance_id)
            if not nations:
                await loading_msg.edit(content="❌ No nations found in this alliance.")
                return

            alliance_revenue = await self._calculate_alliance_revenue_data(nations, rev_ctx=rev_ctx, tax_rate=tax_rate, alliance_color=alliance_color)
            embed = await self._create_alliance_revenue_embed(alliance_data, alliance_revenue, alliance_color=alliance_color)
            await loading_msg.edit(content="", embed=embed)

        except Exception as e:
            logger.error(f"Error calculating alliance revenue: {e}")
            await loading_msg.edit(content=f"❌ Error calculating alliance revenue: {str(e)}")

    async def _load_rev_ctx(self) -> Dict[str, Any]:
        """Load all revenue context from the DB in one shot — no API calls."""
        from Systems.Functions.database_manager import (
            get_latest_resource_prices, get_latest_game_data, get_latest_game_info
        )

        # Prices
        market_prices: Dict[str, float] = {}
        try:
            price_data = await get_latest_resource_prices()
            if price_data:
                market_prices = {res: p['sell'] for res, p in price_data.items()}
        except Exception as e:
            logger.warning(f"Could not load prices from DB: {e}")

        # Color map - use database data (turn_bonus is per-turn, no multiplier)
        color_map: Dict[str, float] = {}
        try:
            colors = await get_latest_game_data("colors")
            if colors:
                color_map = {c['color'].lower(): float(c.get('turn_bonus', 0)) for c in colors}
        except Exception as e:
            logger.warning(f"Could not load colors from DB: {e}")

        # Game date + city average
        game_date = None
        city_average = 0.0
        try:
            gi = await get_latest_game_info()
            if gi:
                raw = gi.get('game_date')
                if raw:
                    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    game_date = parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
                city_average = float(gi.get('city_average') or 0.0)
        except Exception as e:
            logger.warning(f"Could not load game_info from DB: {e}")

        return {
            'market_prices': market_prices or None,
            'color_map': color_map,
            'game_date': game_date,
            'city_average': city_average,
        }

    async def _is_nation_at_war(self, nation_id: int, active_war_ids: Optional[set] = None) -> Optional[bool]:
        """Check the EP wars DB for active wars (turns_left > 0) for this nation.

        Pass a pre-loaded active_war_ids set (from _load_active_war_ids) to avoid
        a DB round-trip per nation when processing an alliance.
        Returns True/False if the DB is available, None if it can't be reached.
        """
        if active_war_ids is not None:
            return nation_id in active_war_ids
        try:
            from Systems.Functions.irs_wars_db import IRSWarsDB
            wars_db = IRSWarsDB(EP_WARS_DB_STR)
            ids = await wars_db.get_active_war_nation_ids()
            return nation_id in ids
        except Exception as e:
            logger.debug(f"Wars DB check failed for nation {nation_id}: {e}")
            return None

    async def _load_active_war_ids(self) -> Optional[set]:
        """Load the full set of nation IDs currently at war in one DB query."""
        try:
            from Systems.Functions.irs_wars_db import IRSWarsDB
            wars_db = IRSWarsDB(EP_WARS_DB_STR)
            return await wars_db.get_active_war_nation_ids()
        except Exception as e:
            logger.warning(f"Could not load active war IDs from wars DB: {e}")
            return None

    async def _calculate_nation_revenue_data(self, nation_data: Dict[str, Any], trade_prices: Optional[List[Dict[str, Any]]] = None, rev_ctx: Optional[Dict] = None, tax_rate: Optional[float] = None, active_war_ids: Optional[set] = None) -> Dict[str, Any]:
        """Calculate detailed unified revenue breakdown for a nation."""
        try:
            nation_name = nation_data.get('nation_name', 'Unknown')
            color = nation_data.get('color', 'beige').lower()
            cities = nation_data.get('cities', [])

            if rev_ctx and rev_ctx.get('color_map') is not None:
                color_bonus = rev_ctx['color_map'].get(color, 0.0)
            else:
                from Systems.Functions.database_manager import get_latest_game_data
                colors = await get_latest_game_data("colors")
                color_map = {c['color'].lower(): float(c.get('turn_bonus', 0)) for c in (colors or [])}
                color_bonus = color_map.get(color, 0.0)

            # War detection — priority order:
            # 1. EP wars DB (turns_left > 0) — authoritative, kept live by subscription
            # 2. wars list on nation object — present when data came from the API
            # 3. offensive/defensive_wars_count — stale fallback from DB snapshot
            nation_id = int(nation_data.get('id', 0))
            at_war_db = await self._is_nation_at_war(nation_id, active_war_ids=active_war_ids) if nation_id else None
            if at_war_db is not None:
                at_war = at_war_db
            else:
                wars = nation_data.get('wars') or []
                if wars:
                    at_war = any(w.get('turnsleft', 0) > 0 for w in wars)
                else:
                    at_war = (
                        (nation_data.get('offensive_wars_count') or 0) > 0 or
                        (nation_data.get('defensive_wars_count') or 0) > 0
                    )

            full_revenue_data = await calculate_full_revenue_with_query(
                nation_data=nation_data,
                query_instance=self.query_instance,
                is_war=at_war,
                radiation_index=nation_data.get("radiation_index", 1000.0),
                domestic_policy=nation_data.get("domestic_policy", ""),
                color_bonus=color_bonus,
                market_prices=rev_ctx.get('market_prices') if rev_ctx else None,
                game_date=rev_ctx.get('game_date') if rev_ctx else None,
                override_tax_rate=tax_rate,
            )

            # Total monetary revenue = cash income + resource value (what the nation is actually worth per turn)
            turn_revenue = full_revenue_data.get('monetary_net_num') or full_revenue_data['gross_income']
            day_revenue  = turn_revenue * 12

            return {
                'nation_name': nation_name,
                'color': color,
                'color_bonus': color_bonus,
                'cities_count': len(cities),
                'revenue_data': full_revenue_data,
                'turn_revenue': turn_revenue,
                'day_revenue': day_revenue,
                'last_updated': datetime.now(tz=timezone.utc)
            }

        except Exception as e:
            logger.error(f"Error calculating nation revenue data: {e}")
            raise

    async def _calculate_alliance_revenue_data(self, nations: List[Dict[str, Any]], rev_ctx: Optional[Dict] = None, tax_rate: Optional[float] = None, alliance_color: Optional[str] = None) -> Dict[str, Any]:
        try:
            if not self.query_instance:
                self.query_instance = create_v3_query_instance()

            # Alliance color for tax calculation (default to black if not specified)
            tax_color = (alliance_color or 'black').lower()

            # Alliance totals for embed (like a nation's totals)
            alliance_population = 0
            alliance_gross_income_turn = 0.0
            alliance_color_bonus_turn = 0.0
            alliance_military_upkeep_turn = 0.0
            alliance_improvement_upkeep_turn = 0.0
            alliance_power_upkeep_turn = 0.0
            alliance_rss_upkeep_turn = 0.0

            # Alliance tax income (what alliance receives)
            alliance_tax_income_turn = 0.0
            alliance_tax_money_turn = 0.0
            alliance_tax_resources_turn = 0.0

            # Alliance net income (tax income minus alliance expenses if any)
            alliance_net_income_turn = 0.0

            # Individual nation data for display
            nation_revenues = []
            color_breakdown: dict[str, int] = {}

            # Resource totals for alliance
            alliance_resources = {}
            alliance_resource_values = {}
            resource_names = ['coal', 'oil', 'uranium', 'lead', 'iron', 'bauxite',
                            'gasoline', 'munitions', 'steel', 'aluminum', 'food']

            # Get best sell market prices for resource valuation
            market_prices = {}
            if rev_ctx and rev_ctx.get('market_prices'):
                market_prices = rev_ctx['market_prices']

            sem = asyncio.Semaphore(20)

            # Load active war IDs once for the whole alliance — one DB query instead of N
            active_war_ids = await self._load_active_war_ids()

            async def process_nation(nation):
                async with sem:
                    try:
                        return await self._calculate_nation_revenue_data(nation, rev_ctx=rev_ctx, tax_rate=tax_rate, active_war_ids=active_war_ids)
                    except Exception as e:
                        logger.warning(f"Error calculating revenue for nation {nation.get('nation_name', 'Unknown')}: {e}")
                        return None

            tasks = [process_nation(n) for n in nations]
            results = await asyncio.gather(*tasks)

            for nation_rev in results:
                if not nation_rev:
                    continue

                revenue_data = nation_rev['revenue_data']
                color = nation_rev['color']

                # Add to color breakdown
                color_breakdown[color] = color_breakdown.get(color, 0) + 1

                # Accumulate alliance totals (from all nations)
                alliance_population += revenue_data.get('nationpop', 0)
                alliance_gross_income_turn += revenue_data.get('gross_income', 0)
                alliance_color_bonus_turn += revenue_data.get('color_bonus_turn', 0)
                alliance_military_upkeep_turn += revenue_data.get('military_upkeep_turn', 0)
                alliance_improvement_upkeep_turn += revenue_data.get('improvement_upkeep_turn', 0)
                alliance_power_upkeep_turn += revenue_data.get('power_upkeep_turn', 0)
                alliance_rss_upkeep_turn += revenue_data.get('rss_upkeep_turn', 0)

                # Alliance tax income = sum of alliance tax from nations matching the alliance color.
                # Clamp to 0 — negative tax must never reduce the alliance total.
                if color == tax_color:
                    alliance_tax_turn = max(0.0, revenue_data.get('alliance_tax_turn', 0))
                    alliance_tax_money = max(0.0, revenue_data.get('alliance_tax_money_turn', 0))
                    alliance_tax_resources = max(0.0, revenue_data.get('alliance_tax_resource_turn', 0))

                    alliance_tax_income_turn += alliance_tax_turn
                    alliance_tax_money_turn += alliance_tax_money
                    alliance_tax_resources_turn += alliance_tax_resources

                # Accumulate alliance resource production
                for resource in resource_names:
                    resource_amount = revenue_data.get(resource, 0)
                    if resource_amount != 0:
                        alliance_resources[resource] = alliance_resources.get(resource, 0) + resource_amount
                        # Calculate resource value
                        price = market_prices.get(resource, 0) if market_prices else 0
                        alliance_resource_values[resource] = alliance_resource_values.get(resource, 0) + (resource_amount * price)

                # Store individual nation data for top nations display
                nation_revenues.append({
                    'nation_name': nation_rev['nation_name'],
                    'color': color,
                    'turn_revenue': nation_rev['turn_revenue'],  # Individual nation net revenue
                })

            # Calculate alliance net income (tax income is what alliance gets)
            alliance_net_income_turn = alliance_tax_income_turn

            # Sort nations by their individual net revenue for display
            nation_revenues.sort(key=lambda x: x['turn_revenue'], reverse=True)

            return {
                # Alliance totals (formatted like nation data for embed)
                'alliance_population': alliance_population,
                'alliance_gross_income_turn': alliance_gross_income_turn,
                'alliance_color_bonus_turn': alliance_color_bonus_turn,
                'alliance_military_upkeep_turn': alliance_military_upkeep_turn,
                'alliance_improvement_upkeep_turn': alliance_improvement_upkeep_turn,
                'alliance_power_upkeep_turn': alliance_power_upkeep_turn,
                'alliance_rss_upkeep_turn': alliance_rss_upkeep_turn,
                'alliance_tax_income_turn': alliance_tax_income_turn,
                'alliance_tax_money_turn': alliance_tax_money_turn,
                'alliance_tax_resources_turn': alliance_tax_resources_turn,
                'alliance_net_income_turn': alliance_net_income_turn,
                'alliance_resources': alliance_resources,
                'alliance_resource_values': alliance_resource_values,
                'market_prices': market_prices,

                # Individual nation data for display
                'nation_count': len(nation_revenues),
                'nation_revenues': nation_revenues[:10],
                'color_breakdown': color_breakdown,
                'tax_color_nations_count': color_breakdown.get(tax_color, 0),
                'tax_color': tax_color,
                'last_updated': datetime.now(tz=timezone.utc)
            }

        except Exception as e:
            logger.error(f"Error calculating alliance revenue data: {e}")
            raise

    async def _create_nation_revenue_embed(self, nation_data: Dict[str, Any], results: Dict[str, Any]) -> discord.Embed:
        nation_name = results.get('nation_name', 'Unknown Nation')
        nation_id   = nation_data.get('id', '')
        nation_url  = f"https://politicsandwar.com/nation/id={nation_id}"
        flag_url    = nation_data.get('flag', None)
        color_name  = results.get('color', 'beige').lower()

        _COLOR_HEX = {
            "beige": 0xDDDDDD, "white": 0xFFFFFF, "grey": 0x808080, "black": 0x000000,
            "gold": 0xFFD700, "pink": 0xFFC0CB, "brown": 0xA52A2A, "mint": 0x98FF98,
            "green": 0x00FF00, "aqua": 0x00FFFF, "lavender": 0xE6E6FA, "lime": 0x00FF00,
            "maroon": 0x800000, "olive": 0x808000, "yellow": 0xFFFF00, "turquoise": 0x40E0D0,
            "red": 0xFF0000, "purple": 0x800080, "orange": 0xFFA500, "blue": 0x0000FF,
        }
        embed_color = _COLOR_HEX.get(color_name, 0x2B2D31)

        embed = discord.Embed(
            title=f"Revenue: {nation_name}",
            url=nation_url,
            color=embed_color,
            timestamp=results.get('last_updated', datetime.now(tz=timezone.utc))
        )
        if flag_url:
            embed.set_thumbnail(url=flag_url)

        rev_data = results['revenue_data']

        population      = rev_data.get('nationpop', 0)
        color_bonus_t   = rev_data.get('color_bonus_turn', 0)
        mil_upkeep_t    = rev_data.get('military_upkeep_turn', 0)
        imp_upkeep_t    = rev_data.get('improvement_upkeep_turn', 0)
        gross_cash_t    = rev_data.get('gross_income', 0)
        gross_cash_d    = gross_cash_t * 12
        resources       = rev_data.get('resources', {})
        prices          = rev_data.get('prices', {})
        alliance_tax_t  = rev_data.get('alliance_tax_money_turn', 0)
        alliance_tax_r  = rev_data.get('alliance_tax_rate', 0)
        resource_tax_r = rev_data.get('resource_tax_rate', alliance_tax_r)
        resource_tax_t = rev_data.get('alliance_tax_resource_turn', 0)
        total_tax_t    = rev_data.get('alliance_tax_turn', 0)  # cash tax + resource tax (in money terms)
        net_after_tax_t = rev_data.get('net_income', 0)
        # monetary_net_num = net cash + all resource monetary values (already computed in rev_correct)
        total_mon_t_precomputed = rev_data.get('monetary_net_num', None)

        RESOURCE_ORDER = ['food', 'coal', 'oil', 'uranium', 'lead', 'iron', 'bauxite',
                          'gasoline', 'munitions', 'steel', 'aluminum']

        def ftd(per_turn: float, prefix: str = '') -> str:
            return f"{prefix}{per_turn:,.2f}/t\u2002|\u2002{prefix}{per_turn*12:,.2f}/d"

        # Description
        embed.description = (
            f"**Population:** {population:,}\n"
            f"**Color Bonus:** {ftd(color_bonus_t, '$')}"
        )

        # Upkeep
        embed.add_field(
            name="Upkeep",
            value=(
                f"**Military:** {ftd(-mil_upkeep_t, '$')}\n"
                f"**Improvement:** {ftd(-imp_upkeep_t, '$')}"
            ),
            inline=False,
        )

        # Net Cash Income (cash revenue - military upkeep - improvement upkeep - cash tax)
        tax_note = ""
        if alliance_tax_r > 0:
            tax_note = (
                f"\n*Pre-tax: ${gross_cash_t:,.2f}/t | Tax: -${alliance_tax_t:,.2f}/t*"
            )
        embed.add_field(
            name="Net Cash Income (After Tax)",
            value=f"**${net_after_tax_t:,.2f}/t**\u2002|\u2002**${net_after_tax_t*12:,.2f}/d**{tax_note}",
            inline=False,
        )

        # Resource Net Income (after tax for positive resources)
        rss_lines = []
        total_rss_value_t = 0.0
        for rss in RESOURCE_ORDER:
            amt_t = resources.get(rss, 0.0)
            if amt_t == 0.0:
                continue
            price = prices.get(rss, 0.0)
            # Apply tax to positive resources only
            if amt_t > 0 and resource_tax_r > 0:
                amt_t_after_tax = amt_t * (1 - resource_tax_r)
            else:
                amt_t_after_tax = amt_t
            total_rss_value_t += amt_t_after_tax * price
            sign = "+" if amt_t >= 0 else ""
            rss_lines.append(
                f"{self._get_resource_emoji(rss)} {sign}{amt_t_after_tax:,.2f}/t\u2002|\u2002{sign}{amt_t_after_tax*12:,.2f}/d"
            )
        if rss_lines:
            embed.add_field(name="Resource Net Income (After Tax)", value="\n".join(rss_lines), inline=False)

        # Total Monetary Value (after tax: cash after tax + resources after tax)
        # gross_cash_t is pre-tax cash, alliance_tax_t is cash tax only
        # total_rss_value_t is already after-tax resources (positive resources taxed, negative not)
        total_mon_t = (gross_cash_t - alliance_tax_t) + total_rss_value_t
        embed.add_field(
            name="Total Monetary Value (After Tax)",
            value=f"**${total_mon_t:,.2f}/t**\u2002|\u2002**${total_mon_t*12:,.2f}/d**",
            inline=False,
        )

        embed.set_footer(text="Revenue shown after alliance tax deduction.")
        return embed

    async def _create_alliance_revenue_embed(self, alliance_data: Dict[str, Any], alliance_revenue: Dict[str, Any], alliance_color: Optional[str] = None) -> discord.Embed:
        alliance_name = alliance_data.get('name', 'Unknown Alliance')
        alliance_id = alliance_data.get('id', '')
        alliance_url = f"https://politicsandwar.com/alliance/id={alliance_id}"
        alliance_flag = alliance_data.get('flag', None)

        # Get the tax color (used for tax calculations) - default to black
        tax_color = alliance_revenue.get('tax_color', 'black')
        tax_color_nations_count = alliance_revenue.get('tax_color_nations_count', 0)

        # Use alliance color or default to blue
        embed_color = discord.Color.blue()

        embed = discord.Embed(
            title=f"Alliance Revenue: {alliance_name}",
            url=alliance_url,
            color=embed_color,
            timestamp=alliance_revenue.get('last_updated', datetime.now(tz=timezone.utc))
        )
        if alliance_flag:
            embed.set_thumbnail(url=alliance_flag)

        # Resource order matching in-game display
        RESOURCE_ORDER = [
            'food', 'coal', 'oil', 'uranium',
            'lead', 'iron', 'bauxite',
            'gasoline', 'munitions', 'steel', 'aluminum',
        ]

        def fmt_turn_day(per_turn: float, prefix: str = '') -> str:
            """Format as 'prefix{per_turn}/t | prefix{per_day}/d'"""
            per_day = per_turn * 12
            return f"{prefix}{per_turn:,.2f}/t\u2002|\u2002{prefix}{per_day:,.2f}/d"

        # Raw components (per turn)
        alliance_population = alliance_revenue.get('alliance_population', 0)
        nation_count = alliance_revenue.get('nation_count', 0)

        # Alliance tax income (what alliance receives)
        alliance_tax_income = alliance_revenue.get('alliance_tax_income_turn', 0)
        alliance_tax_money = alliance_revenue.get('alliance_tax_money_turn', 0)
        alliance_tax_resources = alliance_revenue.get('alliance_tax_resources_turn', 0)

        # Alliance resources and prices
        alliance_resources = alliance_revenue.get('alliance_resources', {})
        market_prices = alliance_revenue.get('market_prices', {})

        # Description: Population + Nations (like nation format)
        desc_lines = []
        desc_lines.append(f"**Total Population:** {alliance_population:,}")
        desc_lines.append(f"**Nations:** {nation_count:,} ({tax_color_nations_count:,} on {tax_color})")
        embed.description = "\n".join(desc_lines)

        # Alliance Tax Income (what the alliance receives from nations on the tax color)
        tax_lines = []
        if alliance_tax_money > 0:
            tax_lines.append(f"**Money Tax:** {fmt_turn_day(alliance_tax_money, '$')}")
        if alliance_tax_resources > 0:
            tax_lines.append(f"**Resource Tax:** {fmt_turn_day(alliance_tax_resources, '$')}")
        tax_lines.append(f"*Received from {tax_color_nations_count} nations on {tax_color} color*")

        embed.add_field(name="Alliance Tax Income", value="\n".join(tax_lines), inline=False)

        # Alliance Net Income (cash from tax, like nation format)
        alliance_net_income = alliance_tax_income  # Tax income is alliance's net income
        alliance_net_day = alliance_net_income * 12
        embed.add_field(
            name="Net Income",
            value=f"**${alliance_net_income:,.2f}/t\u2002|\u2002${alliance_net_day:,.2f}/d**",
            inline=False,
        )

        # Alliance Resource Net Income (with emojis, like nation format)
        rss_lines = []
        total_rss_value_t = 0.0
        
        for rss in RESOURCE_ORDER:
            amt_t = alliance_resources.get(rss, 0.0)
            if abs(amt_t) < 0.01:  # Skip near-zero amounts
                continue
            amt_d = amt_t * 12
            price = market_prices.get(rss, 0.0)
            total_rss_value_t += amt_t * price
            emoji = self._get_resource_emoji(rss)
            sign = "+" if amt_t >= 0 else ""
            rss_lines.append(
                f"{emoji} {sign}{amt_t:,.2f}/t\u2002|\u2002{sign}{amt_d:,.2f}/d"
            )

        if rss_lines:
            embed.add_field(name="Resource Net Income", value="\n".join(rss_lines), inline=False)

        # Total Monetary Value (tax income + resource value, like nation format)
        total_mon_t = alliance_net_income + total_rss_value_t
        total_mon_d = total_mon_t * 12
        embed.add_field(
            name="Total Monetary Value",
            value=f"**${total_mon_t:,.2f}/t\u2002|\u2002${total_mon_d:,.2f}/d**",
            inline=False,
        )

        # Top Nations (compact, inline)
        if alliance_revenue.get('nation_revenues'):
            top_nations_str = []
            for i, nation_rev in enumerate(alliance_revenue['nation_revenues'][:3]):  # Only top 3
                nation_name = nation_rev.get('nation_name', 'Unknown')
                turn_rev = nation_rev.get('turn_revenue', 0)
                color = nation_rev.get('color', 'beige')
                # Map full color name to abbreviation used by the emoji module
                _COLOR_ABBR = {
                    'beige': 'be', 'aqua': 'aq', 'black': 'bla', 'blue': 'blu',
                    'brown': 'br', 'gold': 'go', 'green': 'gr', 'grey': 'gra',
                    'gray': 'gra', 'lavender': 'la', 'maroon': 'mar', 'mint': 'mi',
                    'olive': 'ol', 'lime': 'li', 'orange': 'or', 'pink': 'pi',
                    'purple': 'pu', 'red': 're', 'turquoise': 'tu', 'white': 'wh',
                    'yellow': 'ye',
                }
                abbr = _COLOR_ABBR.get(color.lower(), 'be')
                color_emoji = emoji_mod.mention(abbr) or '🔘'
                top_nations_str.append(f"{color_emoji} {nation_name}: ${turn_rev:,.2f}/t")
            
            if top_nations_str:
                embed.add_field(name="Top Nations", value="\n".join(top_nations_str), inline=True)

        # Color Breakdown (compact, inline)
        if alliance_revenue.get('color_breakdown'):
            color_breakdown_str = []
            _COLOR_ABBR = {
                'beige': 'be', 'aqua': 'aq', 'black': 'bla', 'blue': 'blu',
                'brown': 'br', 'gold': 'go', 'green': 'gr', 'grey': 'gra',
                'gray': 'gra', 'lavender': 'la', 'maroon': 'mar', 'mint': 'mi',
                'olive': 'ol', 'lime': 'li', 'orange': 'or', 'pink': 'pi',
                'purple': 'pu', 'red': 're', 'turquoise': 'tu', 'white': 'wh',
                'yellow': 'ye',
            }
            # Show only colors with nations, sorted by count
            for color, count in sorted(alliance_revenue['color_breakdown'].items(), key=lambda x: x[1], reverse=True)[:6]:
                abbr = _COLOR_ABBR.get(color.lower(), 'be')
                emoji = emoji_mod.mention(abbr) or '🔘'
                color_breakdown_str.append(f"{emoji} {count}")
            
            if color_breakdown_str:
                embed.add_field(name="Colors", value=" | ".join(color_breakdown_str), inline=True)

        embed.set_footer(text="Alliance revenue calculation includes tax from black nations only.")
        return embed

async def setup(bot):
    await bot.add_cog(RevenueCommand(bot))
