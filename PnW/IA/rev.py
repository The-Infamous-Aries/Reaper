import discord
from discord.ext import commands
from discord import app_commands
from typing import Dict, List, Any, Optional, Union, cast
import asyncio
import logging
from datetime import datetime
import sys
import os

# Add parent directory for config imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from Systems.PnW.Util.query import get_color_info, PNWAPIQuery
from Systems.Functions import emoji as emoji_mod
from Systems.PnW.Util.rev_calc import (
    RAW_BASE_PER_IMP, RAW_MAX, STACK_BONUS, MANU_BASE_DAILY, 
    MANU_CONSUME_PER_IMP, RESOURCE_PROJECTS, CONTINENT_MODIFIERS,
    RAW_POLLUTION, RAW_UPKEEP_DAILY, IMP_UPKEEP_DAILY, POWER_PLANT_CAPACITY,
    POWER_PLANT_POLLUTION, POWER_FUEL_PER_100_INFRA, MIL_PEACETIME, 
    WAR_MULTIPLIER, SOLDIER_FOOD_PEACE, SOLDIER_FOOD_WAR, DOMESTIC_POLICIES, calculate_full_revenue,
    PROJECT_BUILD_COSTS, project_build_cost, PROJECT_EFFECTS,
    infra_purchase_cost, land_purchase_cost, city_purchase_cost
)
from config import PANDW_API_KEY
# Create a simple alliance calculator for revenue purposes
class SimpleAllianceCalculator:
    def __init__(self):
        pass
    
    def _safe_get(self, data: dict, key: str, default: Any = None, expected_type: Optional[type] = None) -> Any:
        try:
            value = data.get(key, default)
            if expected_type and value is not None:
                if not isinstance(value, expected_type):
                    try:
                        value = expected_type(value)
                    except (ValueError, TypeError):
                        return default
            return value
        except (AttributeError, TypeError):
            return default

logger = logging.getLogger(__name__)

class RevenueCommand(commands.Cog):
    """Revenue calculation commands for P&W nations and alliances."""
    
    def __init__(self, bot):
        self.bot = bot
        self.calculator = SimpleAllianceCalculator()
        self.query_instance = None  # Will be initialized when needed
        self.available_projects = [
            'Activity Center',
            'Advanced Engineering Corps',
            'Arable Land Agency',
            'Bureau of Domestic Affairs',
            'Center Civil Engineering',
            'Clinical Research Center',
            'Government Support Agency',
            'Green Technologies',
            'International Trade Center',
            'Advanced Pirate Economy',
            'Central Intelligence Agency',
            'Guiding Satellite',
            'Iron Dome',
            'Missile Launch Pad',
            'Nuclear Research Facility',
            'Propaganda Bureau',
            'Space Program',
            'Vital Defense System',
            'Military Research Center',
            'Military Doctrine',
            'Arms Stockpile',
            'Bauxite Works',
            'Emergency Gasoline Reserve',
            'Fallout Shelter',
            'Iron Works',
            'Mars Landing',
            'Mass Irrigation',
            'Military Salvage',
            'Nuclear Launch Facility',
            'Pirate Economy',
            'Recycling Initiative',
            'Research & Development Center',
            'Specialized Police Training Program',
            'Spy Satellite',
            'Surveillance Network',
            'Telecommunications Satellite',
            'Uranium Enrichment Program'
        ]

        self.IMPROVEMENT_TO_RESOURCE_MAP = {
            "farm": "food",
            "coal_mine": "coal",
            "oil_well": "oil",
            "uranium_mine": "uranium",
            "iron_mine": "iron",
            "bauxite_mine": "bauxite",
            "lead_mine": "lead",
        }

        self.MANU_IMPROVEMENT_TO_BONUS_KEY = {
            "gasoline_refinery": "oil_refinery_bonus",
            "munitions_refinery": "munitions_factory_bonus",
            "steel_mill": "steel_mill_bonus",
            "aluminum_refinery": "aluminum_refinery_bonus",
        }

        self.BONUS_KEY_TO_PROJECT = {
            "oil_refinery_bonus": "Emergency Gasoline Reserve",
            "munitions_factory_bonus": "Arms Stockpile",
            "steel_mill_bonus": "Ironworks",
            "aluminum_refinery_bonus": "Bauxite Works",
        }
        
    def _get_resource_emoji(self, resource_name: str) -> str:
        """Get emoji for a resource name."""
        return emoji_mod.resource_emoji(resource_name) or ""
        
    async def project_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete function for project selection."""
        # Filter projects based on current input
        filtered_projects = [
            project for project in self.available_projects
            if current.lower() in project.lower()
        ]
        
        # Return up to 25 suggestions (Discord limit)
        return [
            app_commands.Choice(name=project, value=project)
            for project in filtered_projects[:25]
        ]
        
    @commands.hybrid_command(name='resourcerevenue', aliases=['resrev'], description='Calculate revenue for specific resources for a nation')  # type: ignore
    @app_commands.describe(
        nation_query='Nation name or ID',
        resources='Comma-separated list of resources (e.g., oil, steel, aluminum)'
    )
    async def resource_revenue_command(self, ctx: commands.Context, nation_query: str, resources: str) -> None:
        """
        Calculate revenue for specific resources for a nation.
        
        Usage:
        /resourcerevenue nation_query:"Test Nation" resources:"oil, steel"
        """
        try:
            if not nation_query or not nation_query.strip():
                await ctx.send("❌ Please provide a valid nation name or ID.")
                return
            
            if not resources or not resources.strip():
                await ctx.send("❌ Please provide a comma-separated list of resources.")
                return

            nation_query = nation_query.strip()
            resource_list = [r.strip().lower() for r in resources.split(',')]
            
            loading_msg = await ctx.send(f"🔄 Calculating resource revenue for nation '{nation_query}'...")
            
            await self._calculate_specific_resource_revenue(ctx, nation_query, resource_list, loading_msg)
            
        except Exception as e:
            logger.error(f"Error in resource_revenue_command: {e}")
            await ctx.send(f"❌ Error calculating resource revenue: {str(e)}")

    async def _calculate_specific_resource_revenue(self, ctx, nation_query, resource_list, loading_msg):
        try:
            if not self.query_instance:
                self.query_instance = PNWAPIQuery()

            nation_data = None
            if nation_query.isdigit(): # Check if it's a digit before trying to get by ID
                nation_data = await self.query_instance.get_nation_by_id(nation_query)
            
            if not nation_data: # If not found by ID or not a digit, try by name
                nation_data = await self.query_instance.get_nation_by_name(nation_query)
            if not nation_data:
                await loading_msg.edit(content=f"❌ Nation '{nation_query}' not found.")
                return

            trade_prices = await self.query_instance.get_trade_resource_values()
            price_map = {item['resource']: item['average_price'] for item in trade_prices or []}

            all_revenue_data = await self._calculate_resource_revenue(nation_data)
            
            specific_revenue = {}
            total_revenue = 0
            
            for resource in resource_list:
                gross_production = all_revenue_data['resource_production_gross'].get(resource, 0)
                consumption = all_revenue_data['resource_consumption'].get(resource, 0)
                net_production = gross_production - consumption
                price = price_map.get(resource, 0)
                revenue = net_production * price
                specific_revenue[resource] = {'production': net_production, 'price': price, 'revenue': revenue}
                total_revenue += revenue
            
            embed = self._create_specific_resource_revenue_embed(nation_data, specific_revenue, total_revenue)
            # await loading_msg.edit(content="", embed=embed)

        except Exception as e:
            logger.error(f"Error in _calculate_specific_resource_revenue: {e}")
            await loading_msg.edit(content=f"❌ Error calculating specific resource revenue: {str(e)}")

    def _create_specific_resource_revenue_embed(self, nation_data, revenue_data, total_revenue):
        nation_name = nation_data.get('nation_name', 'Unknown')
        nation_id = nation_data.get('nation_id', '')
        nation_url = f"https://politicsandwar.com/nation/id={nation_id}"
        
        embed = discord.Embed(
            title=f"Resource Revenue for {nation_name}",
            url=nation_url,
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        description = ""
        for resource, data in revenue_data.items():
            emoji = self._get_resource_emoji(resource)
            description += f"{emoji} **{resource.capitalize()}**: {data['production']:,.2f} x ${data['price']:,.2f} = ${data['revenue']:,.2f}/day\n"
            
        embed.description = description
        
        embed.add_field(name="Total Revenue", value=f"${total_revenue:,.2f}/day", inline=False)
        
        tax = total_revenue * 0.15 # Assuming 15% MPoP tax
        embed.add_field(name="Total Revenue (After 15% Tax)", value=f"${total_revenue - tax:,.2f}/day", inline=False)
        
        embed.set_footer(text=f"Nation ID: {nation_id}")
        
        return embed

    @commands.hybrid_command(name='revenuehelp', description='Show revenue command usage and examples')  # type: ignore
    async def revenue_help_command(self, ctx: commands.Context) -> None:
        """Show detailed usage instructions for revenue commands."""
        await self._send_revenue_usage_embed(ctx)
        
    @commands.hybrid_command(name='revenue', aliases=['rev'], description='Calculate revenue for a nation or alliance')  # type: ignore
    @app_commands.describe(
        query_type='Type of query: nation or alliance',
        query_value='Nation/Alliance name or ID'
    )
    @app_commands.choices(
        query_type=[
            app_commands.Choice(name='Nation', value='nation'),
            app_commands.Choice(name='Alliance', value='alliance')
        ]
    )
    async def revenue_command(
        self,
        ctx: commands.Context,
        query_type: str,
        query_value: str
    ) -> None:
        """
        Calculate revenue for a nation or alliance.
        
        Usage:
        /revenue query_type:Nation query_value:"Test Nation"
        /revenue query_type:Nation query_value:12345
        /revenue query_type:Alliance query_value:"Test Alliance"
        /revenue query_type:Alliance query_value:567
        
        Examples:
        /revenue query_type:Nation query_value:"Test Nation"
        /revenue query_type:Nation query_value:12345
        /revenue query_type:Alliance query_value:"Test Alliance"
        /revenue query_type:Alliance query_value:567
        """
        try:
            # Validate input
            if not query_value or not query_value.strip():
                await ctx.send("❌ Please provide a valid nation/alliance name or ID. Use `/revenuehelp` for examples.")
                return
                
            # Clean up query value
            query_value = query_value.strip()
            
            # Show loading message
            loading_msg = await ctx.send(f"🔄 Calculating revenue for {query_type} '{query_value}'...")
            
            # Fetch data based on type
            if query_type == 'nation':
                await self._calculate_nation_revenue(ctx, query_value, loading_msg)
            else:  # alliance
                await self._calculate_alliance_revenue(ctx, query_value, loading_msg)
                
        except Exception as e:
            logger.error(f"Error in revenue command: {e}")
            error_msg = f"❌ Error calculating revenue: {str(e)}"
            if "not found" in str(e).lower():
                error_msg += "\n💡 Try using the exact name or check your spelling. Use `/revenuehelp` for examples."
            await ctx.send(error_msg)
    
    async def _calculate_nation_revenue(self, ctx, nation_query: str, loading_msg):
        """Calculate revenue for a single nation."""
        try:
            # Initialize query instance if needed
            if not self.query_instance:
                self.query_instance = PNWAPIQuery()
            
            # Fetch nation data - try by ID first, then by name
            nation_data = None
            if nation_query.isdigit(): # Check if it's a digit before trying to get by ID
                nation_data = await self.query_instance.get_nation_by_id(nation_query)
            
            if not nation_data: # If not found by ID or not a digit, try by name
                nation_data = await self.query_instance.get_nation_by_name(nation_query)
            
            if not nation_data:
                await loading_msg.edit(content=f"❌ Nation '{nation_query}' not found.")
                return
            
            # Calculate revenue
            revenue_data = await self._calculate_nation_revenue_data(nation_data)
            
            # Create and send embed
            # TODO: Implement _create_nation_revenue_embed
            # embed = await self._create_nation_revenue_embed(nation_data, revenue_data)
            # await loading_msg.edit(content="", embed=embed) # Commented out due to embed not defined
            
        except Exception as e:
            logger.error(f"Error calculating nation revenue: {e}")
            await loading_msg.edit(content=f"❌ Error calculating nation revenue: {str(e)}")
    
    async def _calculate_alliance_revenue(self, ctx, alliance_query: str, loading_msg):
        """Calculate revenue for an alliance."""
        try:
            # Initialize query instance if needed
            if not self.query_instance:
                self.query_instance = PNWAPIQuery()
            
            # Fetch alliance data - try to resolve first
            alliance_data = await self.query_instance.resolve_alliance(alliance_query)
            if not alliance_data:
                await loading_msg.edit(content=f"❌ Alliance '{alliance_query}' not found.")
                return
            
            # Get alliance nations
            alliance_id = str(alliance_data.get('id', ''))
            nations = await self.query_instance.get_alliance_nations(alliance_id)
            if not nations:
                await loading_msg.edit(content="❌ No nations found in this alliance.")
                return
            
            # Calculate alliance revenue
            alliance_revenue = await self._calculate_alliance_revenue_data(nations)
            
            # Create and send embed
            # TODO: Implement _create_alliance_revenue_embed
            # embed = await self._create_alliance_revenue_embed(alliance_data, alliance_revenue)
            # await loading_msg.edit(content="", embed=embed) # Commented out due to embed not defined
            
        except Exception as e:
            logger.error(f"Error calculating alliance revenue: {e}")
            await loading_msg.edit(content=f"❌ Error calculating alliance revenue: {str(e)}")
    
    async def _calculate_nation_revenue_data(self, nation_data: Dict[str, Any], trade_prices: Optional[List[Dict[str, Any]]] = None, game_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Calculate detailed revenue breakdown for a nation."""
        try:
            # Get basic nation info
            nation_name = nation_data.get('nation_name', 'Unknown')
            color = nation_data.get('color', 'beige').lower()
            cities = nation_data.get('cities', [])
            
            # Get color bonus info
            color_info = await get_color_info(color)
            color_bonus = color_info[0]['turn_bonus'] if color_info else 0.0
            
            # Calculate resource production
            resource_revenue = await self._calculate_resource_revenue(nation_data)
            
            # Calculate monetary revenue
            # TODO: Implement _calculate_monetary_revenue
            monetary_revenue: Dict[str, Any] = {} # Initialize to avoid NameError
            # monetary_revenue = await self._calculate_monetary_revenue(nation_data)
            
            # Calculate totals using net income after tax from monetary revenue
            # Deduct military and improvements upkeep from total revenue
            total_upkeep = resource_revenue.get('expenses', {}).get('military', 0) + resource_revenue.get('expenses', {}).get('improvements', 0)
            # turn_revenue = resource_revenue['total_value'] + monetary_revenue['net_income_after_tax'] + color_bonus - total_upkeep # Commented out
            # day_revenue = turn_revenue * 12  # 12 turns per day
            
            return {
                'nation_name': nation_name,
                'color': color,
                'color_bonus': color_bonus,
                'cities_count': len(cities),
                'resource_revenue': resource_revenue,
                'monetary_revenue': monetary_revenue, # Keep it, but it's empty for now
                'turn_revenue': 0.0, # Placeholder
                'day_revenue': 0.0, # Placeholder
                'total_upkeep': total_upkeep,
                'military_upkeep': resource_revenue.get('expenses', {}).get('military', 0),
                'improvements_upkeep': resource_revenue.get('expenses', {}).get('improvements', 0),
                'city_commerce_rates': resource_revenue.get('city_commerce_rates', []),
                'city_resource_production': resource_revenue.get('city_resource_production', []),
                'last_updated': datetime.now()
            }
            
        except Exception as e:
            logger.error(f"Error calculating nation revenue data: {e}")
            raise
    
    async def _calculate_alliance_revenue_data(self, nations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate revenue breakdown for an alliance."""
        try:
            # Initialize query instance if needed
            if not self.query_instance:
                self.query_instance = PNWAPIQuery()
                
            # Prefetch shared data
            trade_prices = await self.query_instance.get_trade_resource_values()
            game_info = await self.query_instance.get_game_info()
            
            total_revenue = 0
            nation_revenues = []
            color_breakdown: dict[str, int] = {}
            
            # Process nations in parallel with semaphore
            sem = asyncio.Semaphore(20)
            
            async def process_nation(nation):
                async with sem:
                    try:
                        return await self._calculate_nation_revenue_data(nation, trade_prices=trade_prices, game_info=game_info)
                    except Exception as e:
                        logger.warning(f"Error calculating revenue for nation {nation.get('nation_name', 'Unknown')}: {e}")
                        return None

            tasks = [process_nation(n) for n in nations]
            results = await asyncio.gather(*tasks)
            
            for nation_rev in results:
                if not nation_rev:
                    continue
                    
                total_revenue += nation_rev['turn_revenue']
                nation_revenues.append(nation_rev)
                
                # Track color distribution
                color = nation_rev['color']
                color_breakdown[color] = color_breakdown.get(color, 0) + 1
            
            # Sort nations by revenue
            nation_revenues.sort(key=lambda x: x['turn_revenue'], reverse=True)
            
            return {
                'total_turn_revenue': total_revenue,
                'total_day_revenue': total_revenue * 12,
                'nation_count': len(nation_revenues),
                'nation_revenues': nation_revenues[:10],  # Top 10
                'color_breakdown': color_breakdown,
                'last_updated': datetime.now()
            }
            
        except Exception as e:
            logger.error(f"Error calculating alliance revenue data: {e}")
            raise
    
    async def _calculate_resource_revenue(self, nation_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate resource-based revenue using exact logic from rev_calc.py"""
        try:
            # Initialize query instance if needed
            if not self.query_instance:
                self.query_instance = PNWAPIQuery()
            
            # Get current trade prices
            trade_prices = await self.query_instance.get_trade_resource_values()
            price_map = {item['resource']: item['average_price'] for item in trade_prices or []}
            
            cities = nation_data.get('cities', [])
            
            # Handle projects data - it might be a count or a list
            projects_raw = nation_data.get("projects", [])
            if isinstance(projects_raw, list):
                projects = {p["name"] for p in projects_raw if isinstance(p, dict) and "name" in p}
            elif isinstance(projects_raw, int):
                # If projects is just a count, we can't determine which projects, so use empty set
                projects = set()
            else:
                projects = set()
                
            alliance_data = nation_data.get('alliance', {})
            continent = nation_data.get('continent', 'north_america')
            domestic_policy = nation_data.get('domestic_policy', '')

            result = {
                'resource_production_gross': {
                    'food': 0, 'coal': 0, 'oil': 0, 'uranium': 0, 'iron': 0, 
                    'bauxite': 0, 'lead': 0
                },
                'manufactured_gross': {
                    'gasoline': 0, 'munitions': 0, 'steel': 0, 'aluminum': 0
                },
                'resource_consumption': {
                    'food': 0, 'coal': 0, 'oil': 0, 'uranium': 0, 'iron': 0, 
                    'bauxite': 0, 'lead': 0
                },
                'expenses': {
                    'improvements': 0, 'infra': 0, 'land': 0, 'military': 0,
                    'power_fuel_value': 0
                },
                'monetary_gross': 0,
                'raw_improvements': {},
                'power_plants': {},
                'pollution_index': 0,
                'domestic_policy': domestic_policy,
                'domestic_policy_effects': {}
            }
            
            total_pop = 0.0
            total_power_capacity = 0
            total_pollution = 0
            total_cities = len(cities)
            
            # Calculate national average commerce multiplier
            national_commerce_mult = self._calculate_national_commerce_multiplier(cities, list(projects))
            
            # Get nation population (instead of summing city populations)
            nation_population = nation_data.get('population', 0)
            
            # Calculate monetary income using national average commerce multiplier and nation population
            national_income = 0.725 * national_commerce_mult * nation_population
            
            # Apply Open Markets domestic policy 1% bonus to gross income
            if domestic_policy == "Open Markets":
                national_income *= 1.01
                
            result["monetary_gross"] = national_income
            total_pop = nation_population  # Use nation population for consistency
            
            # Process each city for resource production and other calculations
            for city in cities:
                if not isinstance(city, dict):
                    continue
                    
                powered = city.get('powered', True)
                
                # Raw resources - Food (special handling)
                improvements = city.get('improvements', {})
                if not isinstance(improvements, dict):
                    improvements = {}
                farms = improvements.get('farm', 0)
                land = city.get('land', 0)
                
                # Check for food-related projects
                has_mass_irr = "Mass Irrigation" in projects
                has_arable = "Arable Land Initiative" in projects
                has_fallout_shelter = "Fallout Shelter" in projects
                
                # Get radiation index (default to 1000 if not available)
                radiation_index = nation_data.get('radiation_index', 1000.0)
                
                food_prod = self._food_production(land, farms, has_mass_irr, has_arable, 
                                                  radiation_index, has_fallout_shelter)
                # Apply continent modifier for food (Antarctica penalty)
                continent_food_modifier = CONTINENT_MODIFIERS.get(continent, {}).get("food", 1.0)
                food_prod *= continent_food_modifier
                result["resource_production_gross"]["food"] += food_prod
                
                # Track farm details
                if farms > 0:
                    if "farm" not in result["raw_improvements"]:
                        result["raw_improvements"]["farm"] = {"count": 0, "pollution": 0, "upkeep": 0}
                    result["raw_improvements"]["farm"]["count"] += farms
                    farm_pollution = farms * RAW_POLLUTION.get("farm", 0)
                    result["raw_improvements"]["farm"]["pollution"] += farm_pollution
                    total_pollution += farm_pollution
                    farm_upkeep = farms * RAW_UPKEEP_DAILY.get("farm", 0)
                    result["raw_improvements"]["farm"]["upkeep"] += farm_upkeep
                    result["expenses"]["improvements"] += farm_upkeep
                
                # Raw improvement tracking and production (excluding farms)
                for imp, base in RAW_BASE_PER_IMP.items():
                    if base is None:  # Skip farms as they're handled above
                        continue
                    count = improvements.get(imp, 0)
                    if count == 0:
                        continue
                        
                    if imp not in result["raw_improvements"]:
                        result["raw_improvements"][imp] = {"count": 0, "pollution": 0, "upkeep": 0}
                    
                    result["raw_improvements"][imp]["count"] += count
                    
                    # Calculate production
                    prod = self._calculate_raw_production(imp, count, powered, projects, continent)
                    result["resource_production_gross"][imp] += prod
                    
                    # Calculate pollution
                    pollution = count * RAW_POLLUTION.get(imp, 0)
                    result["raw_improvements"][imp]["pollution"] += pollution
                    total_pollution += pollution
                    
                    # Calculate upkeep
                    upkeep = count * RAW_UPKEEP_DAILY.get(imp, 0)
                    result["raw_improvements"][imp]["upkeep"] += upkeep
                    result["expenses"]["improvements"] += upkeep

                # Manufactured resources
                for imp, base in MANU_BASE_DAILY.items():
                    count = improvements.get(imp, 0)
                    if count == 0:
                        continue
                    
                    # Calculate production
                    prod = self._calculate_manu_production(imp, count, powered, projects)
                    result["manufactured_gross"][imp] += prod
                    
                    # Calculate consumption
                    consume_res, consume_amt = MANU_CONSUME_PER_IMP.get(imp, (None, 0))
                    if consume_res:
                        result["resource_consumption"][consume_res] += consume_amt * count
                        
                    # Calculate upkeep
                    upkeep = count * IMP_UPKEEP_DAILY.get(imp, 0)
                    result["expenses"]["improvements"] += upkeep
                
                # Power plants
                for plant, capacity in POWER_PLANT_CAPACITY.items():
                    count = improvements.get(plant, 0)
                    if count == 0:
                        continue
                        
                    if plant not in result["power_plants"]:
                        result["power_plants"][plant] = {"count": 0, "pollution": 0, "upkeep": 0}
                        
                    result["power_plants"][plant]["count"] += count
                    total_power_capacity += capacity * count
                    
                    # Pollution
                    pollution = count * POWER_PLANT_POLLUTION.get(plant, 0)
                    result["power_plants"][plant]["pollution"] += pollution
                    total_pollution += pollution
                    
                    # Upkeep
                    upkeep = count * IMP_UPKEEP_DAILY.get(plant, 0)
                    result["power_plants"][plant]["upkeep"] += upkeep
                    result["expenses"]["improvements"] += upkeep
            
            result['pollution_index'] = total_pollution
            
            # Calculate power needs and fuel consumption
            total_infra = nation_data.get('infrastructure', 0)
            power_needed = total_infra * 5  # 5 MW per 1 infra
            
            if total_power_capacity < power_needed:
                # Apply penalty for insufficient power
                power_deficit_ratio = total_power_capacity / power_needed if power_needed > 0 else 1
                for res in result['resource_production_gross']:
                    result['resource_production_gross'][res] *= power_deficit_ratio
                for res in result['manufactured_gross']:
                    result['manufactured_gross'][res] *= power_deficit_ratio
            
            # Fuel consumption for power plants
            for plant, fuel_info in POWER_FUEL_PER_100_INFRA.items():
                count = sum(city.get('improvements', {}).get(plant, 0) for city in cities)
                if count > 0:
                    fuel_type, fuel_amount = fuel_info
                    fuel_consumed = (total_infra / 100) * fuel_amount * count
                    result['resource_consumption'][fuel_type] += fuel_consumed
                    
                    # Calculate value of fuel consumed
                    fuel_price = price_map.get(fuel_type, 0)
                    result['expenses']['power_fuel_value'] += fuel_consumed * fuel_price

            # Military expenses
            soldiers = nation_data.get('soldiers', 0)
            tanks = nation_data.get('tanks', 0)
            aircraft = nation_data.get('aircraft', 0)
            ships = nation_data.get('ships', 0)
            spies = nation_data.get('spies', 0)
            missiles = nation_data.get('missiles', 0)
            nukes = nation_data.get('nukes', 0)
            is_war = nation_data.get('war', False)
            
            military_upkeep = self._calculate_military_upkeep(
                soldiers, tanks, aircraft, ships, spies, missiles, nukes, is_war, projects
            )
            result['expenses']['military'] = military_upkeep
            
            # Food consumption for military
            food_consumption_military = self._calculate_military_food_consumption(
                soldiers, is_war, projects
            )
            result['resource_consumption']['food'] += food_consumption_military
            
            # Calculate net resource production and total value
            net_production = {}
            total_value = 0
            
            all_resources = list(result['resource_production_gross'].keys()) + list(result['manufactured_gross'].keys())
            
            for res in set(all_resources):
                gross = result['resource_production_gross'].get(res, 0) + result['manufactured_gross'].get(res, 0)
                consumed = result['resource_consumption'].get(res, 0)
                net = gross - consumed
                net_production[res] = net
                
                price = price_map.get(res, 0)
                total_value += net * price
                
            result['net_production'] = net_production
            result['total_value'] = total_value
            
            return result

        except Exception as e:
            logger.error(f"Error in _calculate_resource_revenue: {e}")
            raise

    def _calculate_national_commerce_multiplier(self, cities: List[Dict[str, Any]], projects: List[str]) -> float:
        """Calculate the national average commerce multiplier."""
        if not cities:
            return 0.0
            
        total_commerce_value = 0
        total_population = 0
        
        for city in cities:
            commerce_value = city.get('commerce', 0)
            population = city.get('population', 0)
            
            # Apply project bonuses to commerce value
            if "Telecommunications Satellite" in projects:
                commerce_value *= 1.10  # 10% bonus
            if "International Trade Center" in projects:
                commerce_value *= 1.15  # 15% bonus
            
            total_commerce_value += commerce_value * population
            total_population += population
            
        return total_commerce_value / total_population if total_population > 0 else 0.0

    def _food_production(self, land: float, farms: int, has_mass_irr: bool, has_arable: bool, radiation: float, has_fallout_shelter: bool) -> float:
        """Calculate food production for a city."""
        base_food_per_farm = 3.6
        
        # Apply Mass Irrigation bonus
        if has_mass_irr:
            base_food_per_farm *= 1.25
            
        # Apply Arable Land Agency bonus
        if has_arable:
            base_food_per_farm *= 1.10
            
        food_prod = base_food_per_farm * farms
        
        # Apply radiation penalty
        if radiation > 0:
            penalty = 1 - (radiation / 2500)
            if has_fallout_shelter:
                penalty = 1 - (radiation / 5000)
            food_prod *= max(0, penalty)
            
        return food_prod

    def _calculate_raw_production(self, improvement: str, count: int, powered: bool, projects: set, continent: str) -> float:
        """Calculate raw resource production for a given improvement."""
        base_prod = RAW_BASE_PER_IMP.get(improvement, 0)
        if base_prod is None:
            return 0
            
        prod = base_prod * (count ** STACK_BONUS)
        
        resource_type = self.IMPROVEMENT_TO_RESOURCE_MAP.get(improvement)
        if resource_type == "food":
            if "Mass Irrigation" in projects and "Mass Irrigation" in PROJECT_EFFECTS:
                project_effect = PROJECT_EFFECTS["Mass Irrigation"]
                if project_effect.get("type") == "food_production_bonus" and "food_production_bonus" in project_effect:
                    prod *= (1 + cast(float, project_effect["food_production_bonus"]))
                
        # Apply continent modifiers
        continent_bonus = CONTINENT_MODIFIERS.get(continent, {}).get(improvement, 1.0)
        prod *= continent_bonus
        
        return prod

    def _calculate_manu_production(self, improvement: str, count: int, powered: bool, projects: set) -> float:
        """Calculate manufactured resource production."""
        base_prod = MANU_BASE_DAILY.get(improvement, 0)
        prod = base_prod * count
        
        bonus_key = self.MANU_IMPROVEMENT_TO_BONUS_KEY.get(improvement)
        if bonus_key:
            proj_name = self.BONUS_KEY_TO_PROJECT.get(bonus_key)
            if proj_name and proj_name in projects and proj_name in PROJECT_EFFECTS:
                project_effect = PROJECT_EFFECTS[proj_name]
                if project_effect.get("type") == "resource_production_bonus" and bonus_key in project_effect:
                    prod *= (1 + cast(float, project_effect[bonus_key]))
                
        return prod

    def _calculate_military_upkeep(self, soldiers: int, tanks: int, aircraft: int, ships: int, spies: int, missiles: int, nukes: int, is_war: bool, projects: set) -> float:
        """Calculate military upkeep cost."""
        upkeep = (
            (soldiers * MIL_PEACETIME['soldiers']) +
            (tanks * MIL_PEACETIME['tanks']) +
            (aircraft * MIL_PEACETIME['aircraft']) +
            (ships * MIL_PEACETIME['ships']) +
            (spies * MIL_PEACETIME['spies']) +
            (missiles * MIL_PEACETIME['missiles']) +
            (nukes * MIL_PEACETIME['nukes'])
        )
        
        if is_war:
            upkeep *= WAR_MULTIPLIER
            
        # Apply project bonuses
        if "Military Doctrine" in projects:
            upkeep *= 0.90  # 10% reduction
            
        return upkeep

    def _calculate_military_food_consumption(self, soldiers: int, is_war: bool, projects: set) -> float:
        """Calculate military food consumption."""
        consumption = soldiers * (SOLDIER_FOOD_WAR if is_war else SOLDIER_FOOD_PEACE)
        
        # Apply project bonuses
        if "Government Support Agency" in projects:
            consumption *= 0.90  # 10% reduction
            
        return consumption

    async def _send_revenue_usage_embed(self, ctx):
        """Sends a detailed embed on how to use the revenue commands."""
        embed = discord.Embed(
            title="Revenue Commands Help",
            description="Here's how to use the revenue calculation commands:",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="`/revenue` Command",
            value="""Calculates detailed revenue for a nation or alliance.

**Usage:**
`/revenue query_type:<type> query_value:<name_or_id>`

**Arguments:**
- `query_type`: Choose `Nation` or `Alliance`
- `query_value`: The name or ID of the nation/alliance.

**Examples:**
`/revenue query_type:Nation query_value:"Test Nation"`
`/revenue query_type:Nation query_value:12345`
`/revenue query_type:Alliance query_value:"Test Alliance"`
`/revenue query_type:Alliance query_value:567`""",
            inline=False
        )
        
        embed.add_field(
            name="`/costs` Command",
            value="""Calculates the cost of infrastructure, land, and new cities.

**Usage:**
`/costs nation_query:<name_or_id> [desired_infra:<amount>] [desired_land:<amount>] [show_city_cost:<True/False>]`

**Arguments:**
- `nation_query`: The name or ID of the nation.
- `desired_infra` (optional): The target infrastructure amount per city.
- `desired_land` (optional): The target land amount per city.
- `show_city_cost` (optional): Whether to show the cost of the next city (default: `False`).

**Examples:**
`/costs nation_query:"Test Nation" desired_infra:1000`
`/costs nation_query:12345 desired_land:5000 show_city_cost:True`""",
            inline=False
        )

        await ctx.send(embed=embed)

    @commands.hybrid_command(name='costs', aliases=['cost'], description='Calculate infra, land, and city costs')  # type: ignore
    @app_commands.describe(
        nation_query="The name or ID of the nation to calculate costs for.",
        desired_infra="The target infrastructure amount per city.",
        desired_land="The target land amount per city.",
        show_city_cost="Whether to show the cost of the next city.",
        projects_to_buy="A comma-separated list of projects to buy."
    )
    @app_commands.autocomplete(projects_to_buy=project_autocomplete)
    async def costs_command_new(self, ctx: commands.Context, 
                                nation_query: str, 
                                desired_infra: Optional[float] = None, 
                                desired_land: Optional[float] = None, 
                                show_city_cost: bool = False,
                                projects_to_buy: Optional[str] = None) -> None:
        """Calculates the cost of infrastructure, land, and new cities for a nation."""
        try:
            if not nation_query or not nation_query.strip():
                if ctx.interaction:
                    await ctx.interaction.response.send_message("❌ Please provide a valid nation name or ID.", ephemeral=True)
                else:
                    await ctx.send("❌ Please provide a valid nation name or ID.")
                return

            if ctx.interaction:
                await ctx.interaction.response.defer()

            if not self.query_instance:
                self.query_instance = PNWAPIQuery()

            nation_data = None
            if nation_query.isdigit(): # Check if it's a digit before trying to get by ID
                nation_data = await self.query_instance.get_nation_by_id(nation_query)
            
            if not nation_data: # If not found by ID or not a digit, try by name
                nation_data = await self.query_instance.get_nation_by_name(nation_query)
            if not nation_data:
                if ctx.interaction:
                    await ctx.interaction.followup.send(f"❌ Nation '{nation_query}' not found.")
                else:
                    await ctx.send(f"❌ Nation '{nation_query}' not found.")
                return

            cities_data = nation_data.get('cities', [])
            current_cities = len(cities_data)
            nation_projects = {p['name'] for p in nation_data.get('projects', []) if isinstance(p, dict) and 'name' in p}
            nation_policy = nation_data.get('domestic_policy', None)


            if cities_data and len(cities_data) > 0:
                city_infras = [float(city.get('infrastructure', 0)) for city in cities_data]
                city_lands = [float(city.get('land', 0)) for city in cities_data]
                current_infra = sum(city_infras) / len(city_infras) if city_infras else 0
                current_land = sum(city_lands) / len(city_lands) if city_lands else 0
            else:
                current_infra = float(nation_data.get('infrastructure', 0))
                city_infras = [current_infra]
                current_land = float(nation_data.get('land', 0))
                city_lands = [current_land]

            results: Dict[str, Union[float, Dict[str, Any]]] = {}
            trade_prices = await self.query_instance.get_trade_resource_values()

            if desired_infra is not None and desired_infra > current_infra:
                        infra_results = infra_purchase_cost(current_infra, desired_infra - current_infra, projects=nation_projects, total_cities=current_cities, domestic_policy=nation_policy)
                        results['infrastructure'] = infra_results

            if desired_land is not None and desired_land > current_land:
                        land_results = land_purchase_cost(current_land, desired_land - current_land, projects=nation_projects, total_cities=current_cities, domestic_policy=nation_policy)
                        results['land'] = land_results

            if show_city_cost:
                game_info = await self.query_instance.get_game_info()
                # Assuming top_20_average is available from game_info or another source
                top_20_average = game_info.get("city_average", 0)
                city_results = city_purchase_cost(current_cities + 1, top_20_average)
                results['city'] = city_results

            projects_to_buy_str = str(projects_to_buy) if projects_to_buy is not None else ""
            if projects_to_buy_str:
                project_list = [p.strip() for p in projects_to_buy_str.split(',')]
                project_results = await self._calculate_project_costs(project_list, nation_data, trade_prices)
                results['projects'] = project_results

            if not results:
                if ctx.interaction:
                    await ctx.interaction.followup.send("Please specify what you want to calculate: `desired_infra`, `desired_land`, `show_city_cost`, or `projects_to_buy`.")
                else:
                    await ctx.send("Please specify what you want to calculate: `desired_infra`, `desired_land`, `show_city_cost`, or `projects_to_buy`.")
                return

            embed = self._create_nation_costs_embed(nation_data, results, current_infra, current_land, current_cities)
            if ctx.interaction:
                await ctx.interaction.followup.send(embed=embed)
            else:
                await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in costs_command_new: {e}")
            if ctx.interaction:
                await ctx.interaction.followup.send(f"An error occurred: {e}")
            else:
                await ctx.send(f"An error occurred: {e}")

    async def _calculate_project_costs(self, projects_to_buy: List[str], nation_data: Dict[str, Any], trade_prices: List[Dict[str, Any]]) -> Dict[str, Any]:
        return await asyncio.to_thread(self._calculate_project_costs_sync, projects_to_buy, nation_data, trade_prices)

    def _calculate_project_costs_sync(self, projects_to_buy: List[str], nation_data: Dict[str, Any], trade_prices: List[Dict[str, Any]]) -> Dict[str, Any]:
        total_cost = 0
        total_resource_cost: Dict[str, float] = {}
        projects_info = []

        price_map = {item['resource']: item['average_price'] for item in trade_prices or []}

        nation_projects = {p['name'] for p in nation_data.get('projects', []) if isinstance(p, dict) and 'name' in p}
        domestic_policy = nation_data.get('domestic_policy', '')
        tech_adv_discount = 0.05 if domestic_policy == 'Technological Advancement' else 0

        for project_name in projects_to_buy:
            if project_name in nation_projects:
                projects_info.append({'name': project_name, 'cost': 0, 'status': 'Already Owned'})
                continue

            # Use the helper function from rev_calc.py to get costs with discounts applied
            project_costs = project_build_cost(project_name, domestic_policy)
            if not isinstance(project_costs, dict):
                project_costs = {}
            
            if not project_costs: # project_build_cost returns empty dict if project_name is not found
                projects_info.append({'name': project_name, 'cost': 0, 'status': 'Invalid'})
                continue

            money_cost = project_costs.get('money', 0)
            total_cost += money_cost

            resource_cost_str = ""
            current_project_resource_costs = {}
            for resource, amount in project_costs.items():
                if resource != 'money': # 'money' is handled separately
                    current_project_resource_costs[resource] = amount
                    total_resource_cost[resource] = total_resource_cost.get(resource, 0) + amount
                    resource_cost_str += f"{amount:,.2f} {resource}, "
            
            projects_info.append({
                'name': project_name, 
                'cost': money_cost, 
                'status': 'Priced',
                'resource_cost_str': resource_cost_str.strip(", ")
            })

        total_resource_value = sum(price_map.get(res, 0) * amount for res, amount in total_resource_cost.items())
        grand_total_cost = total_cost + total_resource_value

        return {
            'projects': projects_info,
            'total_money_cost': total_cost,
            'total_resource_cost': total_resource_cost,
            'total_resource_value': total_resource_value,
            'grand_total_cost': grand_total_cost
        }

    def _create_nation_costs_embed(self, nation_data: Dict[str, Any], results: Dict[str, Any], current_infra: float, current_land: float, current_cities: int) -> discord.Embed:
        nation_name = nation_data.get('nation_name', 'Unknown')
        nation_id = nation_data.get('nation_id', '')
        embed = discord.Embed(
            title=f"Cost Analysis for {nation_name}",
            url=f"https://politicsandwar.com/nation/id={nation_id}",
            color=discord.Color.from_rgb(*discord.Color.blue().to_rgb()) 
        )

        if 'infrastructure' in results:
            infra = results['infrastructure']
            embed.add_field(
                name="🏗️ Infrastructure Development",
                value=f"Current: {current_infra:.2f} avg ({current_infra * current_cities:.2f} total) → Target: {infra['target']:.2f} avg ({infra['target'] * current_cities:.2f} total)\n"
                      f"Amount to buy: {infra['amount'] / current_cities if current_cities > 0 else 0:.2f} per city ({infra['amount']:.2f} total)\n"
                      f"Base Cost: ${infra['base_cost']:,.2f} (${infra['base_cost_money']:,.2f} + ${infra['base_cost_resources']:,.2f} resources)\n"
                      f"With Urbanization: ${infra['urbanization_cost']:,.2f} (${infra['urbanization_cost_money']:,.2f} + ${infra['urbanization_cost_resources']:,.2f} resources)\n"
                      f"Urbanization Savings: ${infra['urbanization_savings']:,.2f}",
                inline=False
            )

        if 'land' in results:
            land = results['land']
            embed.add_field(
                name="🗺️ Land Acquisition",
                value=f"Current: {current_land:,.2f} avg ({current_land * current_cities:,.2f} total) → Target: {land['target']:,.2f} avg ({land['target'] * current_cities:,.2f} total)\n"
                      f"Amount to buy: {land['amount'] / current_cities if current_cities > 0 else 0:,.2f} per city ({land['amount']:,.2f} total)\n"
                      f"Base Cost: ${land['base_cost']:,.2f}\n"
                      f"With Pop. Density Rebate: ${land['pop_density_cost']:,.2f}\n"
                      f"Savings: ${land['pop_density_savings']:,.2f}",
                inline=False
            )

        if 'city' in results:
            city = results['city']
            embed.add_field(
                name=f"🏙️ City Purchase (City #{city['city_to_buy']})",
                value=f"Base Cost: ${city['base_cost']:,.2f}\n"
                      f"With Urban Planning: ${city['urban_planning_cost']:,.2f} (Saves ${city['urban_planning_savings']:,.2f})\n"
                      f"With Adv. Urban Planning: ${city['adv_urban_planning_cost']:,.2f} (Saves ${city['adv_urban_planning_savings']:,.2f})",
                inline=False
            )

        if 'projects' in results:
            projects_res = results['projects']
            project_details = ""
            for p_info in projects_res['projects']:
                if p_info['status'] == 'Priced':
                    project_details += f"- **{p_info['name']}:** ${p_info['cost']:,.2f}"
                    if p_info['resource_cost_str']:
                        project_details += f" ({p_info['resource_cost_str']})\n"
                    else:
                        project_details += "\n"
                elif p_info['status'] == 'Already Owned':
                    project_details += f"- **{p_info['name']}:** Already Owned\n"
                elif p_info['status'] == 'Invalid':
                    project_details += f"- **{p_info['name']}:** Invalid Project Name\n"

            embed.add_field(
                name=f"{self._get_resource_emoji('project')} Project Costs",
                value=project_details if project_details else "No projects to buy.",
                inline=False
            )

        embed.set_footer(text="All costs are estimates and subject to market fluctuations.")
        return embed

async def setup(bot):
    await bot.add_cog(RevenueCommand(bot))