import discord
from discord.ext import commands
from discord import app_commands
from typing import Dict, List, Any, Optional, Union
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
    WAR_MULTIPLIER, SOLDIER_FOOD_PEACE, SOLDIER_FOOD_WAR, DOMESTIC_POLICIES, calculate_full_revenue
)
from config import PANDW_API_KEY
# Create a simple alliance calculator for revenue purposes
class SimpleAllianceCalculator:
    def __init__(self):
        pass
    
    def _safe_get(self, data: dict, key: str, default: Any = None, expected_type: type = None) -> Any:
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
        
    @commands.hybrid_command(name='revenuehelp', description='Show revenue command usage and examples')
    async def revenue_help_command(self, ctx):
        """Show detailed usage instructions for revenue commands."""
        await self._send_revenue_usage_embed(ctx)
        
    @commands.hybrid_command(name='revenue', aliases=['rev'], description='Calculate revenue for a nation or alliance')
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
    ):
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
            try:
                # Try as ID first
                nation_id = str(nation_query)
                nation_data = await self.query_instance.get_nation_by_id(nation_id)
            except (ValueError, TypeError):
                pass
            
            if not nation_data:
                # Try as name
                nation_data = await self.query_instance.get_nation_by_name(nation_query)
            
            if not nation_data:
                await loading_msg.edit(content=f"❌ Nation '{nation_query}' not found.")
                return
            
            # Calculate revenue
            revenue_data = await self._calculate_nation_revenue_data(nation_data)
            
            # Create and send embed
            embed = await self._create_nation_revenue_embed(nation_data, revenue_data)
            await loading_msg.edit(content="", embed=embed)
            
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
            embed = await self._create_alliance_revenue_embed(alliance_data, alliance_revenue)
            await loading_msg.edit(content="", embed=embed)
            
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
            resource_revenue = await self._calculate_resource_revenue_v2(nation_data, trade_prices=trade_prices, game_info=game_info)
            
            # Calculate monetary revenue
            monetary_revenue = await self._calculate_monetary_revenue(nation_data)
            
            # Calculate totals using net income after tax from monetary revenue
            # Deduct military and improvements upkeep from total revenue
            total_upkeep = resource_revenue.get('expenses', {}).get('military', 0) + resource_revenue.get('expenses', {}).get('improvements', 0)
            turn_revenue = resource_revenue['total_value'] + monetary_revenue['net_income_after_tax'] + color_bonus - total_upkeep
            day_revenue = turn_revenue * 12  # 12 turns per day
            
            return {
                'nation_name': nation_name,
                'color': color,
                'color_bonus': color_bonus,
                'cities_count': len(cities),
                'resource_revenue': resource_revenue,
                'monetary_revenue': monetary_revenue,
                'turn_revenue': turn_revenue,
                'day_revenue': day_revenue,
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
            color_breakdown = {}
            
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
                    
                    # Track raw improvement details
                    if imp not in result["raw_improvements"]:
                        result["raw_improvements"][imp] = {"count": 0, "pollution": 0, "upkeep": 0}
                    result["raw_improvements"][imp]["count"] += count
                    
                    # Calculate production with stacking bonus
                    bonus = self._stacking_bonus(count, RAW_MAX.get(imp, 10))
                    prod = count * base * (1 + bonus)
                    
                    # Apply project bonuses
                    res_name = imp.replace("_mine", "").replace("_well", "")
                    if any(p for p in projects if RESOURCE_PROJECTS.get(p) == res_name):
                        prod *= 2.0
                    
                    result["resource_production_gross"][res_name] += prod
                    
                    # Track pollution
                    pollution = count * RAW_POLLUTION.get(imp, 0)
                    
                    # Apply Green Technologies pollution reduction for farms
                    if imp == "farm" and self._check_project_requirements("Green Technologies", projects, total_cities):
                        pollution *= 0.5  # 50% pollution reduction from farms
                    
                    result["raw_improvements"][imp]["pollution"] += pollution
                    total_pollution += pollution
                    
                    upkeep = count * RAW_UPKEEP_DAILY.get(imp, 0)
                    
                    # Apply Green Technologies resource upkeep reduction
                    if self._check_project_requirements("Green Technologies", projects, total_cities):
                        upkeep *= 0.9  # 10% resource production upkeep reduction
                    
                    result["raw_improvements"][imp]["upkeep"] += upkeep
                    result["expenses"]["improvements"] += upkeep
                
                # Manufactured goods production
                for imp, base_prod_rate in MANU_BASE_DAILY.items():
                    count = improvements.get(imp, 0)
                    if count == 0: 
                        continue
                    bonus = self._stacking_bonus(count, 5)
                    prod = count * base_prod_rate * (1 + bonus)
                    manu_name = imp.replace("_refinery", "").replace("_mill", "")
                    
                    # Apply project bonuses
                    if any(p for p in projects if RESOURCE_PROJECTS.get(p) == manu_name):
                        prod *= 2.0
                    
                    # Apply specific manufacturing bonuses from projects
                    if manu_name == "munitions" and "Arms Stockpile" in projects:
                        prod *= 1.2  # 20% productivity bonus
                    elif manu_name == "aluminum" and "Bauxiteworks" in projects:
                        prod *= 1.36  # 36% productivity bonus
                    elif manu_name == "gasoline" and "Emergency Gasoline Reserve" in projects:
                        prod *= 2.0  # 100% productivity bonus (doubled)
                    elif manu_name == "steel" and "Ironworks" in projects:
                        prod *= 1.2  # 20% productivity bonus
                    
                    result["manufactured_gross"][manu_name] += prod
                
                # Improvement cash upkeep for non-raw improvements
                for imp, count in improvements.items():
                    if count == 0 or not isinstance(count, (int, float)):
                        continue
                    # Skip raw improvements as they're handled separately
                    if imp in RAW_UPKEEP_DAILY: 
                        continue
                    upkeep = IMP_UPKEEP_DAILY.get(imp, 0)
                    if upkeep > 0 and (powered or imp in ["coal_power","oil_power","wind_power","nuclear_power"]):
                        result["expenses"]["improvements"] += count * upkeep
                
                # Power plant tracking and fuel consumption
                city_power_capacity = 0
                city_pollution = 0
                infra = city.get('infrastructure', 0)
                
                for imp, count in improvements.items():
                    if count == 0 or not isinstance(count, (int, float)):
                        continue
                    if imp not in POWER_PLANT_CAPACITY: 
                        continue
                    
                    # Track power plant details
                    if imp not in result["power_plants"]:
                        result["power_plants"][imp] = {"count": 0, "capacity": 0, "pollution": 0}
                    result["power_plants"][imp]["count"] += count
                    capacity = count * POWER_PLANT_CAPACITY[imp]
                    result["power_plants"][imp]["capacity"] += capacity
                    city_power_capacity += capacity
                    
                    # Track pollution
                    pollution = count * POWER_PLANT_POLLUTION[imp]
                    
                    # Apply Green Technologies pollution reduction for manufacturing (power plants)
                    if self._check_project_requirements("Green Technologies", projects, total_cities):
                        pollution *= 0.75  # 25% pollution reduction from manufacturing
                    
                    result["power_plants"][imp]["pollution"] += pollution
                    city_pollution += pollution
                    
                    # Power plant fuel consumption - per plant based on infrastructure
                    if imp == "nuclear_power":
                        # Nuclear power plants: 3 uranium per 1000 infra (max 2000), 6 if over 1000 infra
                        for fuel, base_amt in POWER_FUEL_PER_100_INFRA.get(imp, {}).items():
                            if infra <= 1000:
                                # 3 uranium per 1000 infrastructure per plant
                                fuel_consumption = count * 3.0 * (infra / 1000.0)
                            else:
                                # Over 1000 infra: 6 uranium per plant
                                fuel_consumption = count * 6.0
                            result["resource_consumption"][fuel] += fuel_consumption
                    else:
                        # Other power plants: use infrastructure-based consumption
                        infra_fuel_multiplier = infra / 100.0
                        for fuel, base_amt in POWER_FUEL_PER_100_INFRA.get(imp, {}).items():
                            result["resource_consumption"][fuel] += count * base_amt * infra_fuel_multiplier
                
                total_power_capacity += city_power_capacity
                total_pollution += city_pollution
                
                # Infra & land upkeep
                result["expenses"]["infra"] += self._infra_upkeep(infra)
                result["expenses"]["land"] += self._land_upkeep(land)
            
            # Military upkeep
            military = nation_data.get('military', {})
            is_war = nation_data.get('war', False)
            mult = 1.0 if not is_war else 1.5  # WAR_MULTIPLIER
            
            military_upkeep = (
                military.get('soldiers', 0) * MIL_PEACETIME.get('soldiers', 0) +
                military.get('tanks', 0) * MIL_PEACETIME.get('tanks', 0) +
                military.get('aircraft', 0) * MIL_PEACETIME.get('aircraft', 0) +
                military.get('ships', 0) * MIL_PEACETIME.get('ships', 0) +
                military.get('missiles', 0) * MIL_PEACETIME.get('missiles', 0) +
                military.get('nukes', 0) * MIL_PEACETIME.get('nukes', 0)
            ) * mult
            
            # Apply Imperialism domestic policy 5% reduction to military upkeep
            if domestic_policy == "Imperialism":
                military_upkeep *= 0.95
            
            result["expenses"]["military"] += military_upkeep
            
            # Soldier food consumption
            food_rate = SOLDIER_FOOD_WAR if is_war else SOLDIER_FOOD_PEACE
            result["resource_consumption"]["food"] += military.get('soldiers', 0) * food_rate
            
            # Manufacturing consumption (based on actual production)
            for manu, prod in result["manufactured_gross"].items():
                base_per_imp = 4.5  # All manufacturing is 4.5 tons per day
                imps_equiv = prod / base_per_imp
                manu_key = manu + ("_refinery" if manu != "steel" else "_mill")
                for raw, base_cons in MANU_CONSUME_PER_IMP.get(manu_key, {}).items():
                    result["resource_consumption"][raw] += imps_equiv * base_cons
            
            # Net resources
            net_resources = {}
            for r in result["resource_production_gross"]:
                net = result["resource_production_gross"][r] - result["resource_consumption"].get(r, 0)
                net_resources[r] = net
            net_resources.update(result["manufactured_gross"])
            
            # Resource value (only positive net = income)
            resource_income = sum(max(0, amt) * price_map.get(r.upper(), 0) 
                              for r, amt in net_resources.items())
            power_fuel_cost = sum(result["resource_consumption"].get(r, 0) * price_map.get(r.upper(), 0) 
                                for r in ["coal","oil","uranium"])
            
            result["expenses"]["power_fuel_value"] = power_fuel_cost
            result["gross_income"] = result["monetary_gross"] + resource_income
            total_expenses = sum(result["expenses"].values())
            result["net_income"] = result["gross_income"] - total_expenses
            
            # Activity Center daily bonus (if applicable)
            if self._check_project_requirements("Activity Center", projects, total_cities):
                result["activity_center_bonus"] = 2000000
                result["monetary_gross"] += result["activity_center_bonus"]
                # Recalculate net income with bonus
                result["gross_income"] = result["monetary_gross"] + resource_income
                result["net_income"] = result["gross_income"] - total_expenses
            
            # Alliance tax (if any)
            tax_rate = alliance_data.get("tax_rate", 0) / 100.0
            result["alliance_tax"] = result["net_income"] * tax_rate
            result["final_net_after_tax"] = result["net_income"] - result["alliance_tax"]
            
            # Set final pollution index
            result["pollution_index"] = total_pollution
            
            # Track domestic policy effects
            if domestic_policy:
                result["domestic_policy_effects"] = {
                    "policy": domestic_policy,
                    "effects_applied": []
                }
                
                if domestic_policy == "Open Markets":
                    result["domestic_policy_effects"]["effects_applied"].append("1% gross income bonus")
                elif domestic_policy == "Imperialism":
                    result["domestic_policy_effects"]["effects_applied"].append("5% military upkeep reduction")
                elif domestic_policy == "Urbanization":
                    result["domestic_policy_effects"]["effects_applied"].append("5% infrastructure cost reduction")
                elif domestic_policy == "Rapid Expansion":
                    result["domestic_policy_effects"]["effects_applied"].append("5% land cost reduction")
                elif domestic_policy == "Manifest Destiny":
                    result["domestic_policy_effects"]["effects_applied"].append("5% city cost reduction")
                elif domestic_policy == "Technological Advancement":
                    result["domestic_policy_effects"]["effects_applied"].append("5% project cost reduction (money only)")
            
            # Convert to the format expected by the rest of the code
            resources = {}
            
            for res_name in ['coal', 'oil', 'uranium', 'iron', 'bauxite', 'lead', 'food']:
                gross_prod = result['resource_production_gross'].get(res_name, 0)
                net_prod = gross_prod - result['resource_consumption'].get(res_name, 0)
                
                resources[res_name] = {
                    'production': net_prod,
                    'gross_production': gross_prod,
                    'value': max(0, net_prod) * price_map.get(res_name.upper(), 0) * 12
                }
            
            for res_name in ['gasoline', 'munitions', 'steel', 'aluminum']:
                gross_prod = result['manufactured_gross'].get(res_name, 0)
                resources[res_name] = {
                    'production': gross_prod,
                    'gross_production': gross_prod,
                    'value': max(0, gross_prod) * price_map.get(res_name.upper(), 0) * 12
                }
            
            return {
                'resources': resources,
                'total_value': resource_income * 12,  # Convert to daily
                'trade_prices': price_map,
                'detailed_result': result  # Include full result for debugging
            }
            
        except Exception as e:
            logger.error(f"Error calculating resource revenue: {e}")
            return {'resources': {}, 'total_value': 0, 'trade_prices': {}}
    
    async def _calculate_resource_revenue_v2(self, nation_data: Dict[str, Any], trade_prices: Optional[List[Dict[str, Any]]] = None, game_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            if not self.query_instance:
                self.query_instance = PNWAPIQuery()
            
            if trade_prices is None:
                trade_prices = await self.query_instance.get_trade_resource_values()
            
            price_map_src = {str(item.get('resource') or '').lower(): float(item.get('average_price') or 0) for item in (trade_prices or [])}
            
            if game_info is None:
                game_info = await self.query_instance.get_game_info()
            
            gi = game_info
            rad = (gi or {}).get('radiation') or {}
            cont_key = str(nation_data.get('continent', 'north_america')).lower().replace(' ', '_')
            rad_index = None
            if isinstance(rad, dict):
                rad_index = rad.get(cont_key) or rad.get('global')
            try:
                if rad_index is None:
                    rad_index = 1000.0
                rad_index = float(rad_index)
            except Exception:
                rad_index = 1000.0
            dom_pol = nation_data.get('domestic_policy', None)
            is_war = bool(nation_data.get('war', False))
            
            # Offload heavy calculation to thread
            rev = await asyncio.to_thread(
                calculate_full_revenue,
                nation_data, 
                price_map_src, 
                is_war=is_war, 
                radiation_index=rad_index, 
                domestic_policy=dom_pol
            )
            
            resources = {}
            for res_name in ['coal', 'oil', 'uranium', 'iron', 'bauxite', 'lead', 'food']:
                gp = float(rev.get('resource_production_gross', {}).get(res_name, 0) or 0)
                cons = float(rev.get('resource_consumption', {}).get(res_name, 0) or 0)
                net = gp - cons
                price = float(price_map_src.get(res_name, 0) or 0)
                resources[res_name] = {'production': net, 'gross_production': gp, 'value': (max(0.0, net) * price * 12.0)}
            for res_name in ['gasoline', 'munitions', 'steel', 'aluminum']:
                gp = float(rev.get('manufactured_gross', {}).get(res_name, 0) or 0)
                price = float(price_map_src.get(res_name, 0) or 0)
                resources[res_name] = {'production': gp, 'gross_production': gp, 'value': (max(0.0, gp) * price * 12.0)}
            total_value = sum(v.get('value', 0) for v in resources.values())
            trade_upper = {k.upper(): v for k, v in price_map_src.items()}
            out = {'resources': resources, 'total_value': total_value, 'trade_prices': trade_upper, 'detailed_result': rev}
            try:
                out['expenses'] = rev.get('expenses', {})
            except Exception:
                pass
            return out
        except Exception as e:
            logger.error(f"Error calculating resource revenue v2: {e}")
            return {'resources': {}, 'total_value': 0, 'trade_prices': {}}
    
    async def _calculate_monetary_revenue(self, nation_data: Dict[str, Any]) -> Dict[str, Any]:
        """Async wrapper for _calculate_monetary_revenue_sync."""
        return await asyncio.to_thread(self._calculate_monetary_revenue_sync, nation_data)

    def _calculate_monetary_revenue_sync(self, nation_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate monetary revenue using ingame mechanics with corrected formula:
        Gross Income =(((Commerce/50)×0.725+0.725)×Population)×(domestic bonus+treasure bonus)+color bonus"""
        try:
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
                
            domestic_policy = nation_data.get('domestic_policy', '')
            
            # Get key revenue fields from nation data
            nation_population = nation_data.get('population', 0)
            gross_national_income = nation_data.get('gross_national_income', 0)
            tax_id = nation_data.get('tax_id', 0)
            
            # Convert tax_id to integer (API returns it as string)
            try:
                tax_id = int(tax_id)
            except (ValueError, TypeError):
                tax_id = 0
            
            # Convert tax_id to tax rate (0-100%)
            # Tax brackets: 0=0%, 1=10%, 2=15%, 3=20%, 4=25%, 5=28%, 6=30%
            tax_rates = [0, 10, 15, 20, 25, 28, 30]
            tax_rate = tax_rates[tax_id] / 100.0 if 0 <= tax_id < len(tax_rates) else 0.20
            
            # Calculate commerce rate for each city and get national average
            total_commerce_rate = 0
            valid_cities = 0
            
            for city in cities:
                if not isinstance(city, dict):
                    continue
                commerce_rate = city.get('commerce', 0)
                total_commerce_rate += commerce_rate
                valid_cities += 1
            
            # Calculate average commerce rate across all cities
            avg_commerce_rate = total_commerce_rate / valid_cities if valid_cities > 0 else 0
            
            # Calculate population income using the correct formula:
            # Gross Income =(((Commerce/50)×0.725+0.725)×Population)×(domestic bonus+treasure bonus)+color bonus
            
            # Base income calculation: ((Commerce/50)×0.725+0.725)×Population
            base_income_per_pop = ((avg_commerce_rate / 50) * 0.725 + 0.725)
            
            # Domestic policy bonus (1% for Open Markets = 0.01 bonus)
            domestic_bonus = 0.01 if domestic_policy == "Open Markets" else 0.0
            
            # Treasure bonus (not available in API, default to 0)
            treasure_bonus = 0.0
            
            # Apply domestic and treasure bonuses as additive multipliers
            # Formula: Base Income × (1 + domestic_bonus + treasure_bonus)
            bonus_multiplier = 1 + domestic_bonus + treasure_bonus
            population_income = (base_income_per_pop * nation_population) * bonus_multiplier
            
            # Note: Color bonus is handled separately in the main calculation, not here
            
            # Calculate new player bonus (for nations with <21 cities)
            new_player_bonus = 0
            total_cities = len(cities)
            if total_cities < 21:
                # New player bonus: +50% population income for nations with <21 cities
                new_player_bonus = population_income * 0.5
            
            # Calculate power revenue
            total_power_capacity = 0
            for city in cities:
                if not isinstance(city, dict):
                    continue
                
                improvements = city.get('improvements', {})
                if not isinstance(improvements, dict):
                    improvements = {}
                city_power_capacity = 0
                
                for imp, count in improvements.items():
                    if imp not in POWER_PLANT_CAPACITY: 
                        continue
                    
                    capacity = count * POWER_PLANT_CAPACITY[imp]
                    city_power_capacity += capacity
                
                total_power_capacity += city_power_capacity
            
            # Power revenue: $100 per MW capacity per day
            power_revenue = total_power_capacity * 100
            
            # Activity Center daily bonus (if applicable)
            activity_center_bonus = 0
            if self._check_project_requirements("Activity Center", projects, total_cities):
                activity_center_bonus = 2000000
            
            # Calculate gross income before tax
            gross_income = population_income + new_player_bonus + power_revenue + activity_center_bonus
            
            # Calculate alliance tax (if any)
            alliance_tax_rate = nation_data.get('alliance', {}).get('tax_rate', 0) / 100.0
            alliance_tax = gross_income * alliance_tax_rate
            
            # Calculate final net income after tax
            net_income_after_tax = gross_income - alliance_tax
            
            return {
                'population_income': population_income,
                'new_player_bonus': new_player_bonus,
                'power_revenue': power_revenue,
                'activity_center_bonus': activity_center_bonus,
                'gross_income': gross_income,
                'alliance_tax': alliance_tax,
                'net_income_after_tax': net_income_after_tax,
                'tax_rate': tax_rate,
                'total_population': nation_population,
                'total': net_income_after_tax
            }
            
        except Exception as e:
            logger.error(f"Error calculating monetary revenue: {e}")
            return {
                'population_income': 0, 'new_player_bonus': 0, 'power_revenue': 0, 
                'activity_center_bonus': 0, 'gross_income': 0, 'alliance_tax': 0, 
                'net_income_after_tax': 0, 'tax_rate': 0, 'total_population': 0, 'total': 0
            }
    
    async def _calculate_military_upkeep(self, nation_data: Dict[str, Any]) -> float:
        """Async wrapper for _calculate_military_upkeep_sync."""
        return await asyncio.to_thread(self._calculate_military_upkeep_sync, nation_data)

    def _calculate_military_upkeep_sync(self, nation_data: Dict[str, Any]) -> float:
        """Calculate daily military upkeep costs based on unit counts."""
        try:
            soldiers = nation_data.get('soldiers', 0)
            tanks = nation_data.get('tanks', 0)
            aircraft = nation_data.get('aircraft', 0)
            ships = nation_data.get('ships', 0)
            missiles = nation_data.get('missiles', 0)
            nukes = nation_data.get('nukes', 0)
            
            # Handle projects data - it might be a count or a list
            projects_raw = nation_data.get("projects", [])
            if isinstance(projects_raw, list):
                projects = {p["name"] for p in projects_raw if isinstance(p, dict) and "name" in p}
            elif isinstance(projects_raw, int):
                # If projects is just a count, we can't determine which projects, so use empty set
                projects = set()
            else:
                projects = set()
            
            # Daily upkeep costs per unit (based on war_cost.py values)
            soldier_upkeep = soldiers * 5.0
            tank_upkeep = tanks * 60.0
            aircraft_upkeep = aircraft * 500.0  # $500 per aircraft per day
            ship_upkeep = ships * 50000.0
            missile_upkeep = missiles * 150000.0
            nuke_upkeep = nukes * 1750000.0
            
            # Apply upkeep reduction bonuses
            upkeep_multiplier = 1.0
            
            # Military Research Center reduces all military upkeep by 5%
            if 'Military Research Center' in projects:
                upkeep_multiplier *= 0.95
            
            # Specialized reductions
            if 'Specialized Police Training Program' in projects:
                soldier_upkeep *= 0.75  # 25% reduction for soldiers
            
            if 'Military Salvage' in projects:
                tank_upkeep *= 0.75  # 25% reduction for tanks
            
            total_upkeep = (soldier_upkeep + tank_upkeep + aircraft_upkeep + ship_upkeep + missile_upkeep + nuke_upkeep) * upkeep_multiplier
            
            return total_upkeep
            
        except Exception as e:
            logger.error(f"Error calculating military upkeep: {e}")
            return 0
    
    async def _create_nation_revenue_embed(self, nation_data: Dict[str, Any], revenue_data: Dict[str, Any]) -> discord.Embed:
        """Create a rich embed for nation revenue."""
        nation_name = revenue_data['nation_name']
        color = revenue_data['color'].capitalize()
        
        embed = discord.Embed(
            title=f"💰 Revenue Analysis - {nation_name}",
            description=f"**Color:** {color} | **Cities:** {revenue_data['cities_count']}",
            color=discord.Color.gold(),
            timestamp=revenue_data['last_updated']
        )
        
        # 1. Color Turn Bonus (Turn/Daily)
        if revenue_data.get('color_bonus', 0) > 0:
            daily_color_bonus = revenue_data['color_bonus'] * 12  # 12 turns per day
            embed.add_field(
                name="🎨 Color Bloc Bonus",
                value=f"**Turn:** ${revenue_data['color_bonus']:,.2f} | **Daily:** ${daily_color_bonus:,.2f}",
                inline=False
            )
        
        # 2. Resource Production (with cash revenue, Turn/Daily, net after resource usage)
        resource_text = ""
        manufacturing_text = ""
        
        # Get trade prices for reference
        trade_prices = revenue_data['resource_revenue'].get('trade_prices', {})
        
        for res, data in revenue_data['resource_revenue']['resources'].items():
            # Show ALL resources regardless of production or value
            emoji = self._get_resource_emoji(res)
            daily_value = data['value']  # Already calculated as daily
            production = data['production']
            gross_production = data.get('gross_production', production)
            
            # Manufacturing resources (processed goods)
            if res in ['gasoline', 'munitions', 'steel', 'aluminum']:
                # Show ALL manufactured goods regardless of production value
                manufacturing_text += f"{emoji} **{res.capitalize()}:** {production:,.1f} tons/day\n"
                manufacturing_text += f"└─ **Value:** ${daily_value:,.2f}/day\n"
            
            # Raw resources
            else:
                # Show ALL raw resources regardless of production value
                resource_text += f"{emoji} **{res.capitalize()}:** {production:,.1f} tons/day\n"
                resource_text += f"└─ **Value:** ${daily_value:,.2f}/day\n"
        
        # Add raw resources section
        if resource_text:
            embed.add_field(
                name="⛏️ Raw Resource Production",
                value=resource_text[:1024],  # Discord field limit
                inline=False
            )
        
        # Add manufacturing section
        if manufacturing_text:
            embed.add_field(
                name="🏭 Manufacturing Production",
                value=manufacturing_text[:1024],  # Discord field limit
                inline=False
            )
        
        # Add trade prices reference - show ALL resources on separate lines
        if trade_prices:
            price_text = ""
            for res, price in trade_prices.items():
                if price > 0:  # Show ALL prices
                    emoji = self._get_resource_emoji(res.lower())
                    price_text += f"{emoji} {res}: ${price:.2f}\n"
            
            if price_text:
                embed.add_field(
                    name="💹 Current Trade Prices",
                    value=price_text.strip(),
                    inline=False
                )
        
        # 2.5 Manufacturing Improvements & Bonuses
        bonuses_text = ""
        
        # Check for projects that affect production
        projects_raw = nation_data.get('projects', [])
        if isinstance(projects_raw, list):
            projects = {p["name"] for p in projects_raw if isinstance(p, dict) and "name" in p}
        elif isinstance(projects_raw, int):
            projects = set()
        else:
            projects = set()
            
        if projects:
            if 'Arable Land Agency' in projects:
                bonuses_text += "🌾 **Arable Land Agency:** +5% food production\n"
            if 'Advanced Engineering Corps' in projects:
                bonuses_text += "⚙️ **Advanced Engineering Corps:** +10% manufacturing\n"
            if 'Center Civil Engineering' in projects:
                bonuses_text += "🏗️ **Center Civil Engineering:** +5% manufacturing\n"
        
        if bonuses_text:
            embed.add_field(
                name="✨ Production Bonuses",
                value=bonuses_text,
                inline=False
            )
        
        # 3. Military Upkeep (Daily with unit emojis)
        military_upkeep = await self._calculate_military_upkeep(nation_data)
        if military_upkeep > 0:
            upkeep_text = ""
            soldiers = nation_data.get('soldiers', 0)
            tanks = nation_data.get('tanks', 0)
            aircraft = nation_data.get('aircraft', 0)
            ships = nation_data.get('ships', 0)
            missiles = nation_data.get('missiles', 0)
            nukes = nation_data.get('nukes', 0)
            
            if soldiers > 0:
                upkeep_text += f"🪖 Soldiers: {soldiers:,}\n"
            if tanks > 0:
                upkeep_text += f"🚙 Tanks: {tanks:,}\n"
            if aircraft > 0:
                upkeep_text += f"✈️ Aircraft: {aircraft:,}\n"
            if ships > 0:
                upkeep_text += f"⚓ Ships: {ships:,}\n"
            if missiles > 0:
                upkeep_text += f"🚀 Missiles: {missiles:,}\n"
            if nukes > 0:
                upkeep_text += f"☢️ Nukes: {nukes:,}\n"
            
            upkeep_text += f"**Daily Upkeep:** ${military_upkeep:,.2f}"
            
            embed.add_field(
                name="⚔️ Military Upkeep",
                value=upkeep_text,
                inline=False
            )
        
        # 4. Monetary Revenue (simplified - no breakdown)
        monetary = revenue_data['monetary_revenue']
        total_resource_value = revenue_data['resource_revenue']['total_value']
        
        # 5. Total Revenue Summary
        total_turn_revenue = total_resource_value / 12 + monetary['net_income_after_tax'] / 12  # Convert both to turn
        total_daily_revenue = total_resource_value + monetary['net_income_after_tax']  # Both are daily
        
        total_text = f"**💰 Total Revenue Summary:**\n"
        total_text += f"**Turn:** ${total_turn_revenue:,.2f} | **Daily:** ${total_daily_revenue:,.2f}\n"
        
        # Resource breakdown
        resources = revenue_data['resource_revenue']['resources']
        raw_value = 0
        manufacturing_value = 0
        
        for res, data in resources.items():
            if res in ['coal', 'oil', 'uranium', 'iron', 'bauxite', 'lead', 'food']:
                raw_value += data['value']
            elif res in ['gasoline', 'munitions', 'steel', 'aluminum']:
                manufacturing_value += data['value']
        
        if raw_value > 0 or manufacturing_value > 0:
            total_text += f"**📦 Resources:** ${total_resource_value:,.2f}/day\n"
            if raw_value > 0:
                total_text += f"**⛏️ Raw:** ${raw_value:,.2f}/day\n"
            if manufacturing_value > 0:
                total_text += f"**🏭 Manufacturing:** ${manufacturing_value:,.2f}/day\n"
        
        total_text += f"**💵 Monetary:** ${monetary['net_income_after_tax']:,.2f}/day\n"
        if revenue_data.get('color_bonus', 0) > 0:
            color_bonus = revenue_data['color_bonus']
            total_text += f"**🎨 Color Bonus:** ${color_bonus:,.2f}/turn (${color_bonus * 12:,.2f}/day)\n"
        
        embed.add_field(
            name="📊 Total Revenue Value",
            value=total_text,
            inline=False
        )
        
        # Footer with nation info
        embed.set_footer(text=f"Nation ID: {nation_data.get('id', 'Unknown')} | Population: {nation_data.get('population', 0):,}")
        
        return embed
    
    async def _create_alliance_revenue_embed(self, alliance_data: Dict[str, Any], revenue_data: Dict[str, Any]) -> discord.Embed:
        """Create a rich embed for alliance revenue."""
        alliance_name = alliance_data.get('name', 'Unknown Alliance')
        acronym = alliance_data.get('acronym', '')
        
        title = f"🏛️ Alliance Revenue - {alliance_name}"
        if acronym:
            title += f" [{acronym}]"
        
        embed = discord.Embed(
            title=title,
            description=f"**Nations:** {revenue_data['nation_count']} | **Color Distribution Below**",
            color=discord.Color.blue(),
            timestamp=revenue_data['last_updated']
        )
        
        # Total revenue
        embed.add_field(
            name="💰 Total Alliance Revenue",
            value=f"**Per Turn:** ${revenue_data['total_turn_revenue']:,.2f}\n**Per Day:** ${revenue_data['total_day_revenue']:,.2f}",
            inline=False
        )
        
        # Color distribution
        color_text = ""
        for color, count in revenue_data['color_breakdown'].items():
            color_emoji = "🎨" if color.lower() == 'beige' else "🌈"
            color_text += f"{color_emoji} **{color.capitalize()}:** {count} nations\n"
        
        if color_text:
            embed.add_field(
                name="🎨 Color Distribution",
                value=color_text[:1024],
                inline=True
            )
        
        # Top revenue nations
        if revenue_data['nation_revenues']:
            top_text = ""
            for i, nation_rev in enumerate(revenue_data['nation_revenues'][:5], 1):
                top_text += f"**{i}.** {nation_rev['nation_name']}: ${nation_rev['turn_revenue']:,.2f}/turn\n"
            
            embed.add_field(
                name="🏆 Top Revenue Nations",
                value=top_text,
                inline=True
            )
        
        # Footer with alliance info
        embed.set_footer(text=f"Alliance ID: {alliance_data.get('id', 'Unknown')}")
        
        return embed
    
    async def _send_usage_embed(self, ctx):
        """Send usage instructions."""
        embed = discord.Embed(
            title="💰 Revenue Command Usage",
            description="Calculate revenue for nations and alliances",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🏛️ Nation Revenue (Slash Command)",
            value="`/revenue query_type:Nation query_value:Test Nation`\n`/revenue query_type:Nation query_value:12345`",
            inline=False
        )
        
        embed.add_field(
            name="🤝 Alliance Revenue (Slash Command)",
            value="`/revenue query_type:Alliance query_value:Test Alliance`\n`/revenue query_type:Alliance query_value:567`",
            inline=False
        )
        
        embed.add_field(
            name="🏛️ Nation Revenue (Prefix Command)",
            value="`!revenue nation <name_or_id>`\nExample: `!revenue nation Test Nation`\nExample: `!revenue nation 12345`",
            inline=False
        )
        
        embed.add_field(
            name="🤝 Alliance Revenue (Prefix Command)",
            value="`!revenue alliance <name_or_id>`\nExample: `!revenue alliance Test Alliance`\nExample: `!revenue alliance 567`",
            inline=False
        )
        
        embed.add_field(
            name="⚠️ Important Notes",
            value="• Use quotes for names with spaces in prefix commands\n• Revenue includes resources, cash, and color bonuses\n• Use /revenuehelp for detailed help",
            inline=False
        )
        
        await ctx.send(embed=embed)
        
    async def _send_revenue_usage_embed(self, ctx):
        """Send detailed revenue command usage instructions."""
        embed = discord.Embed(
            title="💰 Revenue Command Help",
            description="Complete guide for revenue calculations",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🔍 Slash Commands (Recommended)",
            value="**Nation Revenue:** `/revenue query_type:Nation query_value:Nation Name`\n"
                  "**Alliance Revenue:** `/revenue query_type:Alliance query_value:Alliance Name`\n"
                  "*Use dropdown menus for query_type selection*",
            inline=False
        )
        
        embed.add_field(
            name="⌨️ Prefix Commands",
            value="**Nation:** `!revenue nation <name_or_id>`\n"
                  "**Alliance:** `!revenue alliance <name_or_id>`\n"
                  "*Use quotes for names with spaces: `!revenue nation \"Test Nation\"`*",
            inline=False
        )
        
        embed.add_field(
            name="📊 What You'll See",
            value="• Daily resource production (Food, Iron, Coal, etc.)\n"
                  "• Daily cash income from taxes\n"
                  "• Color bonus calculations\n"
                  "• Infrastructure and land impact on production\n"
                  "• Project bonuses (if applicable)",
            inline=False
        )
        
        embed.add_field(
            name="💡 Tips",
            value="• Nation IDs work better than names for exact matches\n"
                  "• Alliance revenue shows combined totals for all members\n"
                  "• Revenue calculations use current game formulas\n"
                  "• Data is fetched from the P&W API in real-time",
            inline=False
        )
        
        embed.add_field(
            name="🆘 Need More Help?",
            value="• Use `/costs` for development cost calculations\n"
                  "• Join the support server for assistance\n"
                  "• Check the wiki for detailed game mechanics",
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='costs', description='Calculate development costs for a nation with desired infrastructure, land, and projects')
    @app_commands.describe(
        nation='Nation name or ID to query',
        desired_infra='Desired infrastructure level per city',
        desired_land='Desired land area per city',
        projects='Projects to include in cost calculations (comma-separated)'
    )
    @app_commands.autocomplete(projects=project_autocomplete)
    async def costs_command_new(
        self, 
        ctx: commands.Context,
        nation: str,
        desired_infra: Optional[float] = None,
        desired_land: Optional[float] = None,
        projects: Optional[str] = None
    ):
        """
        Calculate development costs for a nation with desired infrastructure, land, and projects.
        Shows base costs without policy discounts and potential savings from different policies.
        
        Usage:
        /costs nation:"Test Nation" desired_infra:1500 desired_land:2000 projects:"Center Civil Engineering, Arable Land Agency"
        /costs nation:12345 desired_infra:2000
        /costs nation:"My Nation" desired_infra:3000 desired_land:2500
        /costs nation:"My Nation"  # Shows only city costs
        /costs nation:12345  # Shows only city costs
        """
        try:
            # Show loading message
            loading_msg = await ctx.send(f"🔄 Querying nation data and calculating costs...")
            
            # Initialize query instance if not already done
            if not self.query_instance:
                self.query_instance = PNWAPIQuery(PANDW_API_KEY)
            
            # Query nation data
            nation_data = None
            if nation.isdigit():
                nation_data = await self.query_instance.get_nation_by_id(nation)
            else:
                nation_data = await self.query_instance.get_nation_by_name(nation)
            
            if not nation_data:
                await loading_msg.delete()
                await ctx.send(f"❌ Nation '{nation}' not found. Please check the name or ID.")
                return
            
            # Extract current nation data
            current_cities = int(nation_data.get('num_cities', 1))
            nation_name = nation_data.get('nation_name', 'Unknown Nation')
            
            # Calculate averaged infrastructure and land across all cities
            cities_data = nation_data.get('cities', [])
            if cities_data and len(cities_data) > 0:
                total_infra = sum(float(city.get('infrastructure', 0)) for city in cities_data)
                total_land = sum(float(city.get('land', 0)) for city in cities_data)
                current_infra = total_infra / len(cities_data) if len(cities_data) > 0 else 0
                current_land = total_land / len(cities_data) if len(cities_data) > 0 else 0
            else:
                # Fallback to nation-level data if cities data is not available
                current_infra = float(nation_data.get('infrastructure', 0))
                current_land = float(nation_data.get('land', 0))
            
            # Get nation's existing projects from nation data
            nation_projects = set()
            if 'projects' in nation_data:
                # Parse projects from nation data (assuming it's a list or comma-separated string)
                projects_data = nation_data['projects']
                if isinstance(projects_data, list):
                    nation_projects = set(projects_data)
                elif isinstance(projects_data, str):
                    nation_projects = {p.strip() for p in projects_data.split(',') if p.strip()}
            
            # Use provided desired values or None if not specified
            target_infra = desired_infra
            target_land = desired_land
            
            # Build projects set (only for specified projects, not nation projects)
            specified_projects = set()
            if projects:
                project_list = [p.strip() for p in projects.split(',')]
                for project in project_list:
                    if project:
                        specified_projects.add(project)
            
            # Prefetch shared data
            if not self.query_instance:
                self.query_instance = PNWAPIQuery()
            trade_prices = await self.query_instance.get_trade_resource_values()
            game_info = await self.query_instance.get_game_info()
            
            # Calculate costs
            results = {}
            
            # Infrastructure costs - only calculate if desired_infra is provided and greater than current
            if desired_infra is not None and desired_infra > current_infra:
                infra_results = await self._calculate_infra_costs_with_savings(current_infra, desired_infra, current_cities, nation_projects, trade_prices=trade_prices)
                results['infrastructure'] = infra_results
            
            # Land costs - only calculate if desired_land is provided and greater than current
            if desired_land is not None and desired_land > current_land:
                land_results = await self._calculate_land_costs_with_savings(current_land, desired_land, current_cities, nation_projects, trade_prices=trade_prices)
                results['land'] = land_results
            
            # Next city cost - always calculate since this is the default when no other parameters are provided
            city_results = await self._calculate_next_city_cost_with_savings(current_cities, nation_projects, game_info=game_info)
            results['next_city'] = city_results
            
            # Project costs - only calculate if projects are specified
            if specified_projects:
                project_results = await self._calculate_project_costs_with_savings(', '.join(specified_projects), trade_prices=trade_prices)
                results['projects'] = project_results
            
            # Create rich embed
            embed = self._create_nation_costs_embed(nation_name, results, current_infra, current_land, current_cities, target_infra, target_land, nation_projects, specified_projects)
            
            # Delete loading message and send results
            await loading_msg.delete()
            await ctx.send(embed=embed)
            
        except ValueError as e:
            await ctx.send(f"❌ Invalid number format: {e}")
        except Exception as e:
            await ctx.send(f"❌ Error calculating costs: {e}")
            logging.error(f"Error in costs_command_new: {e}", exc_info=True)

    # Legacy costs command removed - functionality merged into new costs command
    
    async def _calculate_infra_costs_with_savings(self, current_infra: float, target_infra: float, total_cities: int, nation_projects: set, trade_prices: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Async wrapper for infrastructure costs calculation."""
        try:
            if trade_prices is None:
                trade_prices = await self.query_instance.get_trade_resource_values()
        except Exception:
            trade_prices = []
            
        return await asyncio.to_thread(self._calculate_infra_costs_with_savings_sync, current_infra, target_infra, total_cities, nation_projects, trade_prices)

    def _calculate_infra_costs_with_savings_sync(self, current_infra: float, target_infra: float, total_cities: int, nation_projects: set, trade_prices: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate infrastructure costs with Urbanization policy savings comparison."""
        from Systems.PnW.Util.rev_calc import infra_purchase_cost
        
        infra_to_buy = target_infra - current_infra
        if infra_to_buy <= 0:
            return {"error": "Target infrastructure must be greater than current"}
        
        # Get current trade prices for resource value calculation
        price_map = {item['resource']: item['average_price'] for item in trade_prices or []}
        
        # Calculate base cost (no policy discount)
        base_cost = infra_purchase_cost(current_infra, infra_to_buy, nation_projects, total_cities, None)
        
        # Debug: Check if base_cost is complex
        if isinstance(base_cost, complex):
            print(f"DEBUG: base_cost is complex: {base_cost}, current_infra={current_infra}, infra_to_buy={infra_to_buy}")
            base_cost = base_cost.real  # Convert to real part
        
        # Calculate cost with Urbanization policy
        urbanization_cost = infra_purchase_cost(current_infra, infra_to_buy, nation_projects, total_cities, "Urbanization")
        
        # Debug: Check if urbanization_cost is complex
        if isinstance(urbanization_cost, complex):
            print(f"DEBUG: urbanization_cost is complex: {urbanization_cost}")
            urbanization_cost = urbanization_cost.real  # Convert to real part
        
        # Calculate savings
        urbanization_savings = base_cost - urbanization_cost
        
        # Calculate resource values (currently infrastructure only costs money, but include for future expansion)
        base_resource_value = 0  # No resources required for basic infrastructure
        urbanization_resource_value = 0  # No resources required for basic infrastructure
        
        return {
            "current_avg": current_infra,
            "target_avg": target_infra,
            "current_total": current_infra * total_cities,
            "target_total": target_infra * total_cities,
            "amount": infra_to_buy,
            "base_cost": base_cost,
            "base_resource_value": base_resource_value,
            "base_total_cost": base_cost + base_resource_value,
            "urbanization_cost": urbanization_cost,
            "urbanization_resource_value": urbanization_resource_value,
            "urbanization_total_cost": urbanization_cost + urbanization_resource_value,
            "urbanization_savings": urbanization_savings,
            "unit_cost": base_cost / infra_to_buy if infra_to_buy > 0 else 0,
            "trade_prices": price_map
        }
    
    async def _calculate_land_costs_with_savings(self, current_land: float, target_land: float, total_cities: int, nation_projects: set, trade_prices: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Async wrapper for land costs calculation."""
        try:
            if trade_prices is None:
                trade_prices = await self.query_instance.get_trade_resource_values()
        except Exception:
            trade_prices = []
            
        return await asyncio.to_thread(self._calculate_land_costs_with_savings_sync, current_land, target_land, total_cities, nation_projects, trade_prices)

    def _calculate_land_costs_with_savings_sync(self, current_land: float, target_land: float, total_cities: int, nation_projects: set, trade_prices: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate land costs with Rapid Expansion policy savings comparison."""
        from Systems.PnW.Util.rev_calc import land_purchase_cost
        
        land_to_buy = target_land - current_land
        if land_to_buy <= 0:
            return {"error": "Target land must be greater than current"}
        
        # Get current trade prices for resource value calculation
        price_map = {item['resource']: item['average_price'] for item in trade_prices or []}
        
        # Calculate base cost (no policy discount)
        base_cost = land_purchase_cost(current_land, land_to_buy, nation_projects, total_cities, None)
        
        # Debug: Check if base_cost is complex
        if isinstance(base_cost, complex):
            print(f"DEBUG: land base_cost is complex: {base_cost}, current_land={current_land}, land_to_buy={land_to_buy}")
            base_cost = base_cost.real  # Convert to real part
        
        # Calculate cost with Rapid Expansion policy
        rapid_expansion_cost = land_purchase_cost(current_land, land_to_buy, nation_projects, total_cities, "Rapid Expansion")
        
        # Debug: Check if rapid_expansion_cost is complex
        if isinstance(rapid_expansion_cost, complex):
            print(f"DEBUG: rapid_expansion_cost is complex: {rapid_expansion_cost}")
            rapid_expansion_cost = rapid_expansion_cost.real  # Convert to real part
        
        # Calculate savings
        rapid_expansion_savings = base_cost - rapid_expansion_cost
        
        # Calculate resource values (currently land only costs money, but include for future expansion)
        base_resource_value = 0  # No resources required for basic land
        rapid_expansion_resource_value = 0  # No resources required for basic land
        
        return {
            "current_avg": current_land,
            "target_avg": target_land,
            "current_total": current_land * total_cities,
            "target_total": target_land * total_cities,
            "amount": land_to_buy,
            "base_cost": base_cost,
            "base_resource_value": base_resource_value,
            "base_total_cost": base_cost + base_resource_value,
            "rapid_expansion_cost": rapid_expansion_cost,
            "rapid_expansion_resource_value": rapid_expansion_resource_value,
            "rapid_expansion_total_cost": rapid_expansion_cost + rapid_expansion_resource_value,
            "rapid_expansion_savings": rapid_expansion_savings,
            "unit_cost": base_cost / land_to_buy if land_to_buy > 0 else 0,
            "trade_prices": price_map
        }
    
    async def _calculate_next_city_cost_with_savings(self, current_cities: int, nation_projects: set, game_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Async wrapper for next city cost calculation."""
        try:
            if not self.query_instance:
                self.query_instance = PNWAPIQuery()
            
            if game_info is None:
                game_info = await self.query_instance.get_game_info()
        except Exception:
            game_info = {}
            
        return await asyncio.to_thread(self._calculate_next_city_cost_with_savings_sync, current_cities, nation_projects, game_info)

    def _calculate_next_city_cost_with_savings_sync(self, current_cities: int, nation_projects: set, game_info: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate cost for the next city only with Manifest Destiny policy savings comparison."""
        from Systems.PnW.Util.rev_calc import city_purchase_cost
        # Fetch GameInfo for city_average (top-20 average proxy)
        top20_avg = 0.0
        try:
            gi = game_info
            ca = (gi or {}).get("city_average")
            if isinstance(ca, (int, float)):
                top20_avg = float(ca)
        except Exception:
            top20_avg = 0.0
        
        # Calculate base cost (no policy discount)
        base_cost = city_purchase_cost(current_cities, nation_projects, None, top20_average=top20_avg)
        
        # Calculate cost with Manifest Destiny policy
        manifest_destiny_cost = city_purchase_cost(current_cities, nation_projects, "Manifest Destiny", top20_average=top20_avg)
        
        # Calculate savings
        manifest_destiny_savings = base_cost - manifest_destiny_cost
        
        return {
            "current": current_cities,
            "next_city_number": current_cities + 1,
            "base_cost": base_cost,
            "manifest_destiny_cost": manifest_destiny_cost,
            "manifest_destiny_savings": manifest_destiny_savings
        }
    
    async def _calculate_project_costs_with_savings(self, projects_str: str, trade_prices: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Async wrapper for project costs calculation."""
        if not self.query_instance:
            self.query_instance = PNWAPIQuery()
            
        if trade_prices is None:
            try:
                trade_prices = await self.query_instance.get_trade_resource_values()
            except Exception:
                trade_prices = []
                
        return await asyncio.to_thread(self._calculate_project_costs_with_savings_sync, projects_str, trade_prices)

    def _calculate_project_costs_with_savings_sync(self, projects_str: str, trade_prices: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate project costs with Technological Advancement policy savings comparison.
        
        Note: Only Technological Advancement policy affects project costs (5% money cost reduction).
        Manifest Destiny only affects city costs, not project costs."""
        from Systems.PnW.Util.rev_calc import project_build_cost
        
        # Parse projects from comma-separated string
        selected_projects = [p.strip() for p in projects_str.split(',') if p.strip()]
        
        if not selected_projects:
            return {"error": "No valid projects provided"}
        
        # Get price map from trade prices
        price_map = {item['resource']: item['average_price'] for item in trade_prices or []}
        
        project_results = []
        total_base_monetary_cost = 0
        total_tech_adv_monetary_cost = 0
        total_base_resource_value = 0
        total_tech_adv_resource_value = 0
        total_tech_adv_savings = 0
        
        for project_name in selected_projects:
            # Get base project build costs (no policy)
            base_costs = project_build_cost(project_name, None)
            
            # Get project build costs with Technological Advancement policy
            tech_adv_costs = project_build_cost(project_name, "Technological Advancement")
            
            if not base_costs:
                project_results.append({
                    "project": project_name,
                    "error": "Project not found or invalid"
                })
                continue
            
            # Calculate resource values using trade prices for base costs
            base_resource_costs = {}
            base_monetary_cost = base_costs.get("money", 0)
            base_resource_value = 0
            
            for resource, amount in base_costs.items():
                if resource == "money":
                    continue
                
                # Get trade price for resource
                price = price_map.get(resource, 0)
                resource_value = amount * price
                
                # Debug: Check if resource_value is complex
                if isinstance(resource_value, complex):
                    # print(f"DEBUG: resource_value is complex for {resource}: {resource_value}, amount={amount}, price={price}")
                    resource_value = resource_value.real
                
                base_resource_value += resource_value
                
                base_resource_costs[resource] = {
                    "amount": amount,
                    "price": price,
                    "value": resource_value
                }
            
            # Calculate resource values using trade prices for tech advancement costs
            tech_adv_resource_costs = {}
            tech_adv_monetary_cost = tech_adv_costs.get("money", 0)
            tech_adv_resource_value = 0
            
            for resource, amount in tech_adv_costs.items():
                if resource == "money":
                    continue
                
                # Get trade price for resource
                price = price_map.get(resource, 0)
                tech_adv_resource_value += amount * price
                
                tech_adv_resource_costs[resource] = {
                    "amount": amount,
                    "price": price,
                    "value": amount * price
                }
            
            # Calculate savings
            monetary_savings = base_monetary_cost - tech_adv_monetary_cost
            resource_savings = base_resource_value - tech_adv_resource_value
            total_project_savings = monetary_savings + resource_savings
            
            # Debug: Check if any totals are complex
            if isinstance(total_project_savings, complex):
                # print(f"DEBUG: total_project_savings is complex for {project_name}: {total_project_savings}")
                total_project_savings = total_project_savings.real
            
            # Update totals
            total_base_monetary_cost += base_monetary_cost
            total_tech_adv_monetary_cost += tech_adv_monetary_cost
            
            # Debug: Check before adding to totals
            if isinstance(total_base_resource_value, complex) or isinstance(base_resource_value, complex):
                # print(f"DEBUG: resource value complex for {project_name}: total={total_base_resource_value}, current={base_resource_value}")
                total_base_resource_value += base_resource_value.real if isinstance(base_resource_value, complex) else base_resource_value
            else:
                total_base_resource_value += base_resource_value
                
            if isinstance(total_tech_adv_resource_value, complex) or isinstance(tech_adv_resource_value, complex):
                # print(f"DEBUG: tech resource value complex for {project_name}: total={total_tech_adv_resource_value}, current={tech_adv_resource_value}")
                total_tech_adv_resource_value += tech_adv_resource_value.real if isinstance(tech_adv_resource_value, complex) else tech_adv_resource_value
            else:
                total_tech_adv_resource_value += tech_adv_resource_value
                
            total_tech_adv_savings += total_project_savings
            
            project_results.append({
                "project": project_name,
                "base_monetary_cost": base_monetary_cost,
                "base_resource_costs": base_resource_costs,
                "base_resource_value": base_resource_value,
                "base_total_cost": base_monetary_cost + base_resource_value,
                "tech_adv_monetary_cost": tech_adv_monetary_cost,
                "tech_adv_resource_costs": tech_adv_resource_costs,
                "tech_adv_resource_value": tech_adv_resource_value,
                "tech_adv_total_cost": tech_adv_monetary_cost + tech_adv_resource_value,
                "monetary_savings": monetary_savings,
                "resource_savings": resource_savings,
                "total_savings": total_project_savings
            })
        
        # Calculate final totals
        final_base_cost = total_base_monetary_cost + total_base_resource_value
        final_tech_adv_cost = total_tech_adv_monetary_cost + total_tech_adv_resource_value
        final_monetary_savings = total_base_monetary_cost - total_tech_adv_monetary_cost
        final_resource_savings = total_base_resource_value - total_tech_adv_resource_value
        
        # Debug: Check if final totals are complex
        if isinstance(final_base_cost, complex):
            # print(f"DEBUG: final_base_cost is complex: {final_base_cost}")
            final_base_cost = final_base_cost.real
        if isinstance(final_tech_adv_cost, complex):
            # print(f"DEBUG: final_tech_adv_cost is complex: {final_tech_adv_cost}")
            final_tech_adv_cost = final_tech_adv_cost.real
        if isinstance(final_monetary_savings, complex):
            # print(f"DEBUG: final_monetary_savings is complex: {final_monetary_savings}")
            final_monetary_savings = final_monetary_savings.real
        if isinstance(final_resource_savings, complex):
            # print(f"DEBUG: final_resource_savings is complex: {final_resource_savings}")
            final_resource_savings = final_resource_savings.real
        if isinstance(total_tech_adv_savings, complex):
            # print(f"DEBUG: total_tech_adv_savings is complex: {total_tech_adv_savings}")
            total_tech_adv_savings = total_tech_adv_savings.real
        
        return {
            "projects": project_results,
            "total_base_monetary_cost": total_base_monetary_cost,
            "total_tech_adv_monetary_cost": total_tech_adv_monetary_cost,
            "total_base_resource_value": total_base_resource_value,
            "total_tech_adv_resource_value": total_tech_adv_resource_value,
            "total_base_cost": final_base_cost,
            "total_tech_adv_cost": final_tech_adv_cost,
            "total_monetary_savings": final_monetary_savings,
            "total_resource_savings": final_resource_savings,
            "total_savings": total_tech_adv_savings,
            "trade_prices": price_map
        }
    
    def _create_nation_costs_embed(self, nation_name: str, results: Dict[str, Any], current_infra: float, current_land: float, current_cities: int, target_infra: float, target_land: float, nation_projects: set, specified_projects: set) -> discord.Embed:
        """Create rich embed for nation development costs with policy savings comparison."""
        embed = discord.Embed(
            title=f"🏛️ {nation_name} - Development Costs",
            description=f"Cost analysis for nation development with {current_cities} cities",
            color=discord.Color.blue()
        )
        
        # Add nation overview
        embed.add_field(
            name="📊 Current Status",
            value=f"Infrastructure: {current_infra:,.2f} per city\n"
                  f"Land: {current_land:,.2f} per city\n"
                  f"Cities: {current_cities}",
            inline=False
        )
        
        # Add nation's existing projects
        if nation_projects:
            embed.add_field(
                name="🏗️ Nation's Active Projects",
                value=", ".join(nation_projects) if len(nation_projects) <= 10 else f"{len(nation_projects)} projects (used for discounts)",
                inline=False
            )
        
        total_base_cost = 0
        total_savings = 0
        
        # Infrastructure costs with Urbanization savings
        if 'infrastructure' in results and "error" not in results['infrastructure']:
            infra = results['infrastructure']
            if target_infra is not None:
                target_display = f"Target: {target_infra:,.2f}"
            else:
                target_display = "Target: N/A"
            
            embed.add_field(
                name="🏗️ Infrastructure Development",
                value=f"Current: {infra['current_avg']:,.2f} avg ({infra['current_total']:,.2f} total) → {target_display}\n"
                      f"Target: {infra['target_avg']:,.2f} avg ({infra['target_total']:,.2f} total)\n"
                      f"Amount to buy: {infra['amount']:,.2f} per city ({infra['amount'] * current_cities:,.2f} total)\n"
                      f"Base Cost: **${infra['base_total_cost']:,.2f}** (${infra['base_cost']:,.2f} + ${infra['base_resource_value']:,.2f} resources)\n"
                      f"With Urbanization: **${infra['urbanization_total_cost']:,.2f}** (${infra['urbanization_cost']:,.2f} + ${infra['urbanization_resource_value']:,.2f} resources)\n"
                      f"💰 Urbanization Savings: **${infra['urbanization_savings']:,.2f}**",
                inline=False
            )
            total_base_cost += infra['base_total_cost']
            total_savings += infra['urbanization_savings']
        
        # Land costs with Rapid Expansion savings
        if 'land' in results and "error" not in results['land']:
            land = results['land']
            if target_land is not None:
                target_display = f"Target: {target_land:,.2f}"
            else:
                target_display = "Target: N/A"
            
            embed.add_field(
                name="🏕️ Land Development",
                value=f"Current: {land['current_avg']:,.2f} avg ({land['current_total']:,.2f} total) → {target_display}\n"
                      f"Target: {land['target_avg']:,.2f} avg ({land['target_total']:,.2f} total)\n"
                      f"Amount to buy: {land['amount']:,.2f} per city ({land['amount'] * current_cities:,.2f} total)\n"
                      f"Base Cost: **${land['base_total_cost']:,.2f}** (${land['base_cost']:,.2f} + ${land['base_resource_value']:,.2f} resources)\n"
                      f"With Rapid Expansion: **${land['rapid_expansion_total_cost']:,.2f}** (${land['rapid_expansion_cost']:,.2f} + ${land['rapid_expansion_resource_value']:,.2f} resources)\n"
                      f"💰 Rapid Expansion Savings: **${land['rapid_expansion_savings']:,.2f}**",
                inline=False
            )
            total_base_cost += land['base_total_cost']
            total_savings += land['rapid_expansion_savings']
        
        # Next city cost with Manifest Destiny savings
        if 'next_city' in results and "error" not in results['next_city']:
            next_city = results['next_city']
            embed.add_field(
                name="🏙️ Next City Cost",
                value=f"City #{next_city['next_city_number']}:\n"
                      f"Base Cost: **${next_city['base_cost']:,.2f}**\n"
                      f"With Manifest Destiny: **${next_city['manifest_destiny_cost']:,.2f}**\n"
                      f"💰 Manifest Destiny Savings: **${next_city['manifest_destiny_savings']:,.2f}**",
                inline=False
            )
            total_base_cost += next_city['base_cost']
            total_savings += next_city['manifest_destiny_savings']
        
        # Project costs with Technological Advancement savings
        if 'projects' in results and "error" not in results['projects']:
            project_results = results['projects']
            if project_results.get("projects"):
                # Show total project costs summary
                embed.add_field(
                    name="🏗️ Project Costs Summary",
                    value=f"Base Cost: **${project_results['total_base_cost']:,.2f}**\n"
                          f"With Technological Advancement: **${project_results['total_tech_adv_cost']:,.2f}**\n"
                          f"💰 Technological Advancement Savings: **${project_results['total_savings']:,.2f}**\n",
                    inline=False
                )
                total_base_cost += project_results['total_base_cost']
                total_savings += project_results['total_savings']
                
                # Show detailed breakdown for each project
                for project in project_results['projects']:
                    if 'error' not in project:
                        # Build resource display with emojis
                        resource_display = []
                        for resource, details in project['base_resource_costs'].items():
                            emoji = self._get_resource_emoji(resource)
                            resource_display.append(f"{emoji} {resource}: {details['amount']:,.0f} (${details['value']:,.2f})")
                        
                        resources_text = "\n".join(resource_display) if resource_display else "No resources required"
                        
                        # Individual project field
                        project_value = f"**Base Monetary Cost:** ${project['base_monetary_cost']:,.2f}\n"
                        project_value += f"**Resources Required:**\n{resources_text}\n"
                        project_value += f"**Total Resource Value:** ${project['base_resource_value']:,.2f}\n"
                        project_value += f"**Total Project Cost:** ${project['base_total_cost']:,.2f}\n"
                        project_value += f"💰 **Technological Advancement Savings:** ${project['total_savings']:,.2f}"
                        
                        embed.add_field(
                            name=f"📋 {project['project']}",
                            value=project_value,
                            inline=False
                        )
        
        # Total cost summary with savings
        if total_base_cost > 0:
            final_cost = total_base_cost - total_savings
            embed.add_field(
                name="💎 Cost Summary",
                value=f"Total Base Cost: **${total_base_cost:,.2f}**\n"
                      f"Total Policy Savings: **${total_savings:,.2f}**\n"
                      f"**Final Cost: ${final_cost:,.2f}**",
                inline=False
            )
        
        embed.set_footer(text="Costs show base prices vs potential policy savings. Only nation's existing projects apply discounts.")
        return embed
    
    async def _create_project_costs_embed(self, title: str, results: Dict[str, Any], domestic_policy: str) -> discord.Embed:
        """Create embed for project cost calculation results."""
        embed = discord.Embed(
            title=f"🏗️ {title}",
            color=discord.Color.purple()
        )
        
        # Add domestic policy info
        if domestic_policy:
            embed.add_field(
                name="📋 Domestic Policy",
                value=domestic_policy.title(),
                inline=False
            )
        
        if "error" in results:
            embed.add_field(
                name="❌ Error",
                value=results["error"],
                inline=False
            )
        else:
            # Add individual project costs
            for project in results["projects"]:
                if "error" in project:
                    embed.add_field(
                        name=f"❌ {project['project']}",
                        value=project["error"],
                        inline=False
                    )
                else:
                    # Monetary cost
                    project_details = f"💰 **${project['monetary_cost']:,.2f}**"
                    
                    # Resource costs
                    if project['resource_costs']:
                        resource_details = []
                        for resource, details in project['resource_costs'].items():
                            if details['price'] > 0:
                                resource_details.append(f"{details['amount']:,.0f} {resource} (${details['value']:,.2f})")
                            else:
                                resource_details.append(f"{details['amount']:,.0f} {resource} (price unavailable)")
                        
                        if resource_details:
                            project_details += f"\n📦 Resources: {', '.join(resource_details)}"
                    
                    # Total cost
                    project_details += f"\n💎 **Total: ${project['total_cost']:,.2f}**"
                    
                    embed.add_field(
                        name=f"🏗️ {project['project']}",
                        value=project_details,
                        inline=False
                    )
            
            # Add totals
            totals_text = f"💰 Monetary: **${results['total_monetary_cost']:,.2f}**"
            if results['total_resource_value'] > 0:
                totals_text += f"\n📦 Resources: **${results['total_resource_value']:,.2f}**"
            totals_text += f"\n💎 **Grand Total: ${results['total_cost']:,.2f}**"
            
            embed.add_field(
                name="📊 Total Costs",
                value=totals_text,
                inline=False
            )
            
            # Add trade prices info if available
            if results['trade_prices']:
                price_info = []
                for resource, price in results['trade_prices'].items():
                    if price > 0:
                        price_info.append(f"{resource}: ${price:.2f}")
                
                if price_info:
                    embed.add_field(
                        name="💹 Current Trade Prices",
                        value=f"{', '.join(price_info[:5])}{'...' if len(price_info) > 5 else ''}",
                        inline=False
                    )
        
        embed.set_footer(text="Project costs calculated using current trade prices and domestic policy discounts")
        return embed
    
    def _stacking_bonus(self, count: int, max_allowed: int) -> float:
        """Calculate stacking bonus for improvements"""
        if count <= 1:
            return 0.0
        return min(0.125 * (count - 1), 0.50)
    
    def _commerce_multiplier(self, commerce_pct: float, projects: List[str]) -> float:
        """Calculate commerce multiplier based on commerce percentage and projects.
        This function is deprecated - use direct formula calculation instead."""
        cap = 100.0
        if "International Trade Center" in projects:
            cap += 15
        if "Telecommunications Satellite" in projects:
            cap += 10
        commerce_pct = min(commerce_pct, cap)
        return (commerce_pct / 50.0) + 1.0  # Kept for backward compatibility
    
    def _calculate_national_commerce_multiplier(self, cities: List[Dict[str, Any]], projects: List[str]) -> float:
        """Calculate national average commerce multiplier across all cities"""
        if not cities:
            return 1.0  # Default multiplier if no cities
        
        total_multiplier = 0.0
        for city in cities:
            if not isinstance(city, dict):
                continue
            commerce = city.get('commerce', 0)
            city_multiplier = self._commerce_multiplier(commerce, projects)
            total_multiplier += city_multiplier
        
        return total_multiplier / len(cities)  # Average across all cities
    
    def _food_production(self, land: float, farms: int, has_mass_irr: bool, has_arable: bool, 
                       radiation_index: float = 1000.0, has_fallout_shelter: bool = False) -> float:
        """Calculate food production based on land and farms"""
        # Food Production = Farm Count * (Land Area / 500)
        prod = farms * (land / 500.0)
        
        # Apply Mass Irrigation bonus (if available)
        if has_mass_irr:
            prod *= 1.25  # 25% bonus from Mass Irrigation
        
        # Apply Arable Land Initiative bonus (if available)
        if has_arable:
            prod *= 1.25  # 25% bonus from Arable Land Initiative
        
        # Apply radiation modifier
        rad_modifier = radiation_index / 1000.0
        if has_fallout_shelter:
            rad_modifier = max(rad_modifier, 0.5)  # Minimum 50% production with fallout shelter
        prod *= rad_modifier
        
        return prod
    
    def _check_project_requirements(self, project_name: str, projects: set, current_cities: int = 0) -> bool:
        """Check if a project meets all its requirements"""
        if not projects or project_name not in projects:
            return False
        
        # For now, just check if project exists
        # TODO: Add full requirement checking if needed
        return True
    
    def _infra_upkeep(self, infra: float) -> float:
        """Calculate infrastructure upkeep"""
        return (infra ** 2) * 0.0045
    
    def _land_upkeep(self, land: float) -> float:
        """Calculate land upkeep"""
        return land * 0.5
    
async def setup(bot):
    """Add the revenue command cog to the bot."""
    await bot.add_cog(RevenueCommand(bot))
    logger.info("Revenue command cog loaded successfully")
