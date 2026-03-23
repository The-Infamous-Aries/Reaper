import discord
from discord.ext import commands
from discord import app_commands
from typing import Dict, List, Any, Optional, Union
import asyncio
import logging
from datetime import datetime
import math
import sys
import os

# Add parent directory for config imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from Systems.PnW.Util.query import get_color_info, create_v3_query_instance, V3GraphQuery
from Systems.Functions import emoji as emoji_mod
from Systems.Functions.config import PANDW_API_KEY

logger = logging.getLogger(__name__)

# Domestic Policy effects
DOMESTIC_POLICIES = {
    "Manifest Destiny": {
        "city_cost_reduction": 0.05,
        "type": "city_cost_reduction"
    },
    "Urbanization": {
        "infra_cost_reduction": 0.05,
        "type": "infra_cost_reduction"
    },
    "Technological Advancement": {
        "project_cost_reduction": 0.05,
        "type": "project_cost_reduction"
    },
    "Rapid Expansion": {
        "land_cost_reduction": 0.05,
        "type": "land_cost_reduction"
    },
}

PROJECT_BUILD_COSTS = {
    # Economic Projects
    'Activity Center': {"money": 500000, "food": 1000},
    'Advanced Engineering Corps': {"money": 50000000, "munitions": 10000, "gasoline": 10000, "uranium": 1000},
    'Arable Land Agency': {"money": 3000000, "coal": 1500, "lead": 1500},
    'Bureau of Domestic Affairs': {"money": 20000000, "food": 500000, "coal": 8000, "bauxite": 8000, "lead": 8000, "iron": 8000, "oil": 8000},
    'Center Civil Engineering': {"money": 3000000, "oil": 1000, "iron": 1000, "bauxite": 1000},
    'Clinical Research Center': {"money": 10000000, "food": 100000},
    'Government Support Agency': {"money": 20000000, "aluminum": 10000, "food": 200000},
    'Green Technologies': {"money": 50000000, "food": 100000, "aluminum": 10000, "iron": 10000, "oil": 10000},
    'International Trade Center': {"money": 50000000, "aluminum": 10000},
    
    # Military Projects
    'Advanced Pirate Economy': {"money": 50000000, "coal": 10000, "iron": 10000, "oil": 10000, "bauxite": 10000, "lead": 10000},
    'Central Intelligence Agency': {"money": 5000000, "steel": 500, "gasoline": 500},
    'Guiding Satellite': {"money": 200000000, "munitions": 40000, "aluminum": 40000, "uranium": 40000, "gasoline": 40000, "steel": 20000},
    'Iron Dome': {"money": 15000000, "munitions": 5000},
    'Missile Launch Pad': {"money": 5000000, "steel": 500, "gasoline": 500},
    'Nuclear Research Facility': {"money": 50000000, "aluminum": 10000, "uranium": 1000},
    'Propaganda Bureau': {"money": 5000000, "coal": 1000, "iron": 1000},
    'Space Program': {"money": 50000000, "aluminum": 10000, "steel": 10000, "gasoline": 10000},
    'Vital Defense System': {"money": 60000000, "steel": 25000, "aluminum": 25000, "munitions": 25000},
    'Military Research Center': {"money": 100000000, "steel": 10000, "aluminum": 10000, "munitions": 10000, "gasoline": 10000},
    'Military Doctrine': {"money": 10000000, "steel": 10000, "aluminum": 10000, "munitions": 10000, "gasoline": 10000},
    
    # Resource Projects
    'Arms Stockpile': {"money": 10000000, "coal": 500, "iron": 500, "oil": 500, "bauxite": 500, "lead": 500},
    'Bauxite Works': {"money": 10000000, "coal": 500, "iron": 500, "oil": 500, "bauxite": 500, "lead": 500},
    'Emergency Gasoline Reserve': {"money": 10000000, "coal": 500, "iron": 500, "oil": 500, "bauxite": 500, "lead": 500},
    'Fallout Shelter': {"money": 25000000, "food": 100000, "lead": 10000, "aluminum": 15000, "steel": 10000},
    'Iron Works': {"money": 10000000, "coal": 500, "iron": 500, "oil": 500, "bauxite": 500, "lead": 500},
    'Mars Landing': {"money": 200000000, "oil": 20000, "aluminum": 20000, "munitions": 20000, "steel": 20000, "gasoline": 20000, "uranium": 20000},
    'Mass Irrigation': {"money": 10000000, "food": 50000, "coal": 500, "iron": 500, "oil": 500, "bauxite": 500, "lead": 500},
    'Military Salvage': {"money": 20000000, "aluminum": 5000, "steel": 5000, "gasoline": 5000},
    'Moon Landing': {"money": 50000000, "oil": 5000, "aluminum": 5000, "munitions": 5000, "steel": 5000, "gasoline": 5000, "uranium": 10000},
    'Nuclear Launch Facility': {"money": 750000000, "uranium": 50000, "gasoline": 50000, "aluminum": 50000},
    'Pirate Economy': {"money": 25000000, "coal": 7500, "iron": 7500, "oil": 7500, "bauxite": 7500, "lead": 7500},
    'Recycling Initiative': {"money": 10000000, "food": 100000},
    'Research & Development Center': {"money": 50000000, "aluminum": 5000, "food": 100000, "uranium": 1000},
    'Specialized Police Training Program': {"money": 50000000, "food": 250000, "aluminum": 5000},
    'Spy Satellite': {"money": 20000000, "oil": 10000, "bauxite": 10000, "iron": 10000, "lead": 10000, "coal": 10000},
    'Surveillance Network': {"money": 50000000, "aluminum": 50000, "bauxite": 15000, "iron": 15000, "lead": 15000, "coal": 15000},
    'Telecommunications Satellite': {"money": 300000000, "oil": 10000, "aluminum": 10000, "iron": 10000, "uranium": 10000},
    'Uranium Enrichment Program': {"money": 25000000, "uranium": 2500, "coal": 500, "iron": 500, "oil": 500, "bauxite": 500, "lead": 500},
}

# --- INFRASTRUCTURE COST FORMULAS ---
def infra_price(amount: float) -> float:
    return ((abs(amount - 10) ** 2.2) / 710.0) + 300.0

def calc_infra_value(starting_amount: float, ending_amount: float) -> float:
    start = round(float(starting_amount), 2)
    end = round(float(ending_amount), 2)
    diff = end - start

    if diff > 10000: return float('inf')
    if diff == 0: return 0.0
    if diff < 0: return 150.0 * diff

    if diff > 100 and (diff % 100 == 0):
        cost_of_chunk = round(infra_price(start), 2) * 100.0
        return cost_of_chunk + calc_infra_value(start + 100.0, end)
    if diff > 100 and (diff % 100 != 0):
        remainder = diff % 100.0
        cost_of_chunk = round(infra_price(start), 2) * remainder
        return cost_of_chunk + calc_infra_value(start + remainder, end)
    if diff <= 100:
        cost_of_chunk = round(infra_price(start), 2) * diff
        return cost_of_chunk
    return 0.0

# --- LAND COST FORMULAS ---
def land_price(amount: float) -> float:
    return (0.002 * (amount - 20) * (amount - 20)) + 50.0

def calc_land_value(starting_amount: float, ending_amount: float) -> float:
    start = round(float(starting_amount), 2)
    end = round(float(ending_amount), 2)
    diff = end - start

    if diff > 10000: return float('inf')
    if diff == 0: return 0.0
    if diff < 0: return 50.0 * diff

    if diff > 500 and (diff % 500 == 0):
        cost_of_chunk = round(land_price(start), 2) * 500.0
        return cost_of_chunk + calc_land_value(start + 500.0, end)
    if diff > 500 and (diff % 500 != 0):
        remainder = diff % 500.0
        cost_of_chunk = round(land_price(start), 2) * remainder
        return cost_of_chunk + calc_land_value(start + remainder, end)
    if diff <= 500:
        cost_of_chunk = round(land_price(start), 2) * diff
        return cost_of_chunk
    return 0.0

# --- DISCOUNT HELPERS ---
def calculate_project_discounts(nation_data: Dict[str, Any]) -> Dict[str, float]:
    """Calculate additive project discounts and domestic policy multiplier based on a nation's boolean project flags."""
    if not isinstance(nation_data, dict):
        logger.error(f"calculate_project_discounts received non-dict: {type(nation_data)}")
        return {"infra_cost_reduction": 0.0, "land_cost_reduction": 0.0, "domestic_policy_multiplier": 1.0}
    
    discounts = {"infra_cost_reduction": 0.0, "land_cost_reduction": 0.0, "domestic_policy_multiplier": 1.0}
    
    # Check for projects using the boolean flags from the nation_data
    if nation_data.get('center_for_civil_engineering', False):
        discounts["infra_cost_reduction"] += 0.05
    if nation_data.get('advanced_engineering_corps', False):
        discounts["infra_cost_reduction"] += 0.05
        discounts["land_cost_reduction"] += 0.05
    if nation_data.get('arable_land_agency', False):
        discounts["land_cost_reduction"] += 0.05
        
    # Domestic multipliers
    if nation_data.get('bureau_of_domestic_affairs', False):
        discounts["domestic_policy_multiplier"] += 0.25
    if nation_data.get('government_support_agency', False):
        discounts["domestic_policy_multiplier"] += 0.50
        
    return discounts

def project_build_cost(project_name: str, nation_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculates the cost of a national project, applying relevant discounts.
    - Base Cost: The cost with only the nation's existing project discounts applied.
    - Final Cost: The cost with project discounts AND the 'Technological Advancement' policy discount.
    """
    if project_name not in PROJECT_BUILD_COSTS:
        return {}

    raw_costs = PROJECT_BUILD_COSTS[project_name].copy()
    project_discounts = calculate_project_discounts(nation_data)
    
    # Base cost for projects is the raw cost, as no projects discount other projects.
    base_cost = raw_costs.copy()
    
    # Final cost always includes the Technological Advancement policy discount.
    final_cost = raw_costs.copy()
    tech_adv_savings = 0.0
    
    if "money" in final_cost:
        policy_discount_multiplier = project_discounts.get("domestic_policy_multiplier", 1.0)
        discount_rate = 0.05 * policy_discount_multiplier
        discount_amount = final_cost["money"] * discount_rate
        final_cost["money"] -= discount_amount
        tech_adv_savings = discount_amount

    return {
        "base_costs": base_cost,
        "final_costs": final_cost,
        "technological_savings": tech_adv_savings
    }

# --- PURCHASE WRAPPERS ---
def infra_purchase_cost(current_infra: float, infra_to_buy: float, nation_data: Dict[str, Any]) -> Dict[str, float]:
    """
    Calculates infrastructure cost.
    - Base Cost: Includes discounts from the nation's existing projects.
    - Final Cost: Includes project discounts AND the 'Urbanization' policy discount.
    """
    target_infra = current_infra + infra_to_buy
    raw_cost = calc_infra_value(current_infra, target_infra)
    
    project_discounts = calculate_project_discounts(nation_data)
    
    # Base cost includes project discounts
    project_reduction = project_discounts["infra_cost_reduction"]
    base_cost = raw_cost * (1.0 - project_reduction)
    
    # Final cost also includes the 'Urbanization' policy discount
    policy_reduction = 0.05 * project_discounts["domestic_policy_multiplier"]
    final_cost = base_cost * (1.0 - policy_reduction)
    
    return {
        'target': target_infra,
        'amount': infra_to_buy,
        'base_cost': base_cost,
        'final_cost': final_cost
    }

def land_purchase_cost(current_land: float, land_to_buy: float, nation_data: Dict[str, Any]) -> Dict[str, float]:
    """
    Calculates land cost.
    - Base Cost: Includes discounts from the nation's existing projects.
    - Final Cost: Includes project discounts AND the 'Rapid Expansion' policy discount.
    """
    target_land = current_land + land_to_buy
    raw_cost = calc_land_value(current_land, target_land)
    
    project_discounts = calculate_project_discounts(nation_data)
    
    # Base cost includes project discounts
    project_reduction = project_discounts["land_cost_reduction"]
    base_cost = raw_cost * (1.0 - project_reduction)
    
    # Final cost also includes the 'Rapid Expansion' policy discount
    policy_reduction = 0.05 * project_discounts["domestic_policy_multiplier"]
    final_cost = base_cost * (1.0 - policy_reduction)
    
    return {
        'target': target_land,
        'amount': land_to_buy,
        'base_cost': base_cost,
        'final_cost': final_cost
    }

def city_purchase_cost(city_to_buy: int, top_20_average: float, nation_data: Dict[str, Any]) -> Dict[str, float]:
    """
    Calculates city cost.
    - Base Cost: Is the raw cost, as no projects discount it.
    - Final Cost: Includes the 'Manifest Destiny' policy discount.
    """
    term1 = 100000 * ((city_to_buy - (top_20_average / 4)) ** 3)
    term2 = 150000 * (city_to_buy - (top_20_average / 4))
    term3 = 75000
    cost1 = term1 + term2 + term3
    cost2 = (city_to_buy ** 2) * 100000
    
    base_cost = max(cost1, cost2)
    
    project_discounts = calculate_project_discounts(nation_data)
    
    # Final cost includes the 'Manifest Destiny' policy discount
    policy_reduction = 0.05 * project_discounts["domestic_policy_multiplier"]
    final_cost = base_cost * (1.0 - policy_reduction)
    
    return {
        'city_to_buy': float(city_to_buy),
        'base_cost': base_cost,
        'final_cost': final_cost
    }

class CostsCommand(commands.Cog):
    """Cost calculation commands for P&W nations."""
    
    def __init__(self, bot):
        self.bot = bot
        self.query_instance: V3GraphQuery = create_v3_query_instance()
        self.available_projects = list(PROJECT_BUILD_COSTS.keys())

    async def project_autocomplete(self, interaction: discord.Interaction, current: str):
        filtered_projects = [p for p in self.available_projects if current.lower() in p.lower()]
        return [app_commands.Choice(name=p, value=p) for p in filtered_projects[:25]]

    def _get_resource_emoji(self, resource_name: str) -> str:
        return emoji_mod.resource_emoji(resource_name) or ""

    async def _create_costs_embed(self, ctx: commands.Context, nation_data: Dict[str, Any], costs_data: Dict[str, Any], best_buy_price_map: Dict[str, float]) -> discord.Embed:
        nation_id = nation_data.get('nation_id', '')
        nation_name = nation_data.get('nation_name', 'Unknown')
        nation_color = nation_data.get('color', 'blue').lower()
        
        color_info = await get_color_info(nation_color)
        embed_color = discord.Color.blue()
        if color_info:
            hex_color_str = color_info[0].get('hex_color', '0000FF')
            try:
                embed_color = discord.Color(int(hex_color_str, 16))
            except ValueError:
                pass 

        embed = discord.Embed(title=f"Cost Analysis for {nation_name}", color=embed_color, timestamp=datetime.now())
        embed.set_thumbnail(url=f"https://cdn.politicsandwar.com/img/nations/{nation_id}.jpg")

        description_parts = []

        # --- INFRA DISPLAY ---
        if 'infra_cost' in costs_data:
            ic = costs_data['infra_cost']
            raw_cost = costs_data['raw_infra_cost']
            description_parts.append(f"{emoji_mod.mention('infra')} **Infrastructure:**")
            description_parts.append(f"  Target: {ic['target']:,.0f} (from {costs_data['current_infra']:,.0f} avg)")
            description_parts.append(f"  Base Cost: ${ic['base_cost']:,.2f}")
            
            total_saved = raw_cost - ic['final_cost']
            if total_saved > 0:
                description_parts.append(f"  **Final Cost:** ${ic['final_cost']:,.2f}")
                description_parts.append(f"  **Total Savings:** ${total_saved:,.2f}")
            else:
                description_parts.append(f"  **Final Cost:** ${ic['final_cost']:,.2f}")
            description_parts.append("")

        # --- LAND DISPLAY ---
        if 'land_cost' in costs_data:
            lc = costs_data['land_cost']
            raw_cost = costs_data['raw_land_cost']
            description_parts.append(f"{emoji_mod.mention('landbuy')} **Land:**")
            description_parts.append(f"  Target: {lc['target']:,.0f} (from {costs_data['current_land']:,.0f} avg)")
            description_parts.append(f"  Base Cost: ${lc['base_cost']:,.2f}")
            
            total_saved = raw_cost - lc['final_cost']
            if total_saved > 0:
                description_parts.append(f"  **Final Cost:** ${lc['final_cost']:,.2f}")
                description_parts.append(f"  **Total Savings:** ${total_saved:,.2f}")
            else:
                description_parts.append(f"  **Final Cost:** ${lc['final_cost']:,.2f}")
            description_parts.append("")

        # --- CITY DISPLAY ---
        if 'city_cost' in costs_data:
            cc = costs_data['city_cost']
            raw_cost = costs_data['raw_city_cost']
            description_parts.append(f"{emoji_mod.mention('newcity')} **Cities:**")
            description_parts.append(f"  Buying {int(cc['city_to_buy'] - costs_data['current_cities'])} cities (Target: {int(cc['city_to_buy'])})")
            description_parts.append(f"  Base Cost: ${cc['base_cost']:,.2f}")
            
            total_saved = raw_cost - cc['final_cost']
            if total_saved > 0:
                description_parts.append(f"  **Final Cost:** ${cc['final_cost']:,.2f}")
                description_parts.append(f"  **Total Savings:** ${total_saved:,.2f}")
            else:
                description_parts.append(f"  **Final Cost:** ${cc['final_cost']:,.2f}")
            description_parts.append("")

        # --- PROJECTS DISPLAY ---
        if 'project_costs' in costs_data:
            description_parts.append(f"{emoji_mod.mention('project')} **Projects:**")

            # Get nation's projects to correctly calculate policy multiplier effects
            raw_projects = nation_data.get('projects', [])
            if not isinstance(raw_projects, list): raw_projects = []
            nation_projects = {p['name'] for p in raw_projects if isinstance(p, dict) and 'name' in p}
            project_discounts = calculate_project_discounts(nation_projects)
            policy_discount_multiplier = project_discounts.get("domestic_policy_multiplier", 1.0)
            discount_rate = 0.05 * policy_discount_multiplier

            for project_name, cost_data in costs_data['project_costs'].items():
                base_costs = cost_data['base_costs']
                final_costs = cost_data['final_costs']
                
                description_parts.append(f"  **{project_name}:**")
                base_money = base_costs.get('money', 0)
                final_money = final_costs.get('money', 0)
                money_savings = base_money - final_money
                
                money_line = f"    Money: ${base_money:,.2f}"
                if money_savings > 0:
                    money_line += f" (Discounted: ${final_money:,.2f} - Saved: ${money_savings:,.2f})"
                description_parts.append(money_line)

                # Calculate resource values
                base_resource_value = 0.0
                for res, amount in base_costs.items():
                    if res != 'money':
                        res_emoji = self._get_resource_emoji(res)
                        value = best_buy_price_map.get(res.lower(), 0.0) * amount
                        base_resource_value += value
                        description_parts.append(f"    {res_emoji}{amount:,.0f} {res.capitalize()} (Est. Value: ${value:,.2f})")

                # Calculate total values
                total_base_value = base_money + base_resource_value
                final_resource_value = base_resource_value * (1.0 - discount_rate)
                total_final_value = final_money + final_resource_value

                description_parts.append(f"    **Total Est. Value:** ${total_base_value:,.2f}")
                if abs(total_base_value - total_final_value) > 0.01:
                    description_parts.append(f"    **Total Est. Value (with Policy):** ${total_final_value:,.2f}")
                
                description_parts.append("")

        if not description_parts:
            description_parts.append("No specific costs requested or calculated.")

        embed.description = "\n".join(description_parts)

        embed.add_field(name="Total Estimated Money Cost (with Project Discounts Only)", 
                        value=f"${costs_data.get('total_cost_projects_only', 0):,.2f}", 
                        inline=False)
        embed.add_field(name="Total Estimated Money Cost (with All Discounts)", 
                        value=f"${costs_data.get('total_cost_all_discounts', 0):,.2f}", 
                        inline=False)
        embed.set_footer(text=f"Nation ID: {nation_id} | Assumes perfectly balanced buying across all cities.")
        return embed

    @commands.hybrid_command(name='costs', description='Calculate various costs for a nation.')
    @app_commands.describe(
        nation_query='Nation name or ID',
        desired_infra='Desired infrastructure to reach (e.g., 1000)',
        desired_land='Desired land to reach (e.g., 500)',
        cities_to_buy='Number of new cities to buy (e.g., 1)',
        projects_to_buy='Comma-separated list of projects to buy'
    )
    @app_commands.autocomplete(projects_to_buy=project_autocomplete)
    async def costs_command_new(
        self,
        ctx: commands.Context,
        nation_query: str,
        desired_infra: Optional[int] = None,
        desired_land: Optional[int] = None,
        cities_to_buy: Optional[int] = None,
        projects_to_buy: Optional[str] = None
    ) -> None:
        await ctx.defer()

        trade_prices_data = await self.query_instance.get_trade_resource_values()
        best_buy_price_map = {item['resource'].lower(): item['best_buy_offer']['price'] for item in (trade_prices_data or []) if 'resource' in item and 'best_buy_offer' in item}

        nation_data = await self.query_instance.get_nation_by_id(nation_query) if nation_query.isdigit() else await self.query_instance.get_nation_by_name(nation_query)

        if not nation_data:
            await ctx.send(f"❌ Nation '{nation_query}' not found.", ephemeral=True)
            return

        raw_projects = nation_data.get('projects', [])
        if not isinstance(raw_projects, list):
            logger.warning(f"nation_data['projects'] was not a list, but {type(raw_projects)}. Treating as empty.")
            raw_projects = []
        nation_projects = {p['name'] for p in raw_projects if isinstance(p, dict) and 'name' in p}
        
        cities_data = nation_data.get('cities', [])
        num_cities = len(cities_data)
        current_cities_count = nation_data.get('num_cities', 0)
        avg_current_infra = sum(c.get('infrastructure', 0) for c in cities_data) / num_cities if num_cities else 0
        avg_current_land = sum(c.get('land', 0) for c in cities_data) / num_cities if num_cities else 0

        game_info = await self.query_instance.get_game_info()
        top_20_average = game_info.get('city_average', 40.0) if game_info else 40.0

        costs_data = {
            'current_infra': avg_current_infra,
            'current_land': avg_current_land,
            'current_cities': current_cities_count,
            'total_cost_projects_only': 0.0,
            'total_cost_all_discounts': 0.0,
        }

        # --- Infrastructure Costs ---
        if desired_infra is not None:
            total_base = 0.0
            total_final = 0.0
            total_raw = 0.0
            for city in cities_data:
                city_infra = city.get('infrastructure', 0)
                if city_infra < desired_infra:
                    res = infra_purchase_cost(city_infra, desired_infra - city_infra, nation_data)
                    total_base += res['base_cost']
                    total_final += res['final_cost']
                    total_raw += calc_infra_value(city_infra, desired_infra)
            
            costs_data['infra_cost'] = {'target': desired_infra, 'base_cost': total_base, 'final_cost': total_final}
            costs_data['raw_infra_cost'] = total_raw
            costs_data['total_cost_projects_only'] += total_base
            costs_data['total_cost_all_discounts'] += total_final

        # --- Land Costs ---
        if desired_land is not None:
            total_base = 0.0
            total_final = 0.0
            total_raw = 0.0
            for city in cities_data:
                city_land = city.get('land', 0)
                if city_land < desired_land:
                    res = land_purchase_cost(city_land, desired_land - city_land, nation_data)
                    total_base += res['base_cost']
                    total_final += res['final_cost']
                    total_raw += calc_land_value(city_land, desired_land)

            costs_data['land_cost'] = {'target': desired_land, 'base_cost': total_base, 'final_cost': total_final}
            costs_data['raw_land_cost'] = total_raw
            costs_data['total_cost_projects_only'] += total_base
            costs_data['total_cost_all_discounts'] += total_final

        # --- City Costs ---
        if cities_to_buy is not None and cities_to_buy > 0:
            total_base = 0.0
            total_final = 0.0
            total_raw = 0.0
            for i in range(cities_to_buy):
                res = city_purchase_cost(current_cities_count + i + 1, top_20_average, nation_data)
                total_base += res['base_cost']
                total_final += res['final_cost']
                
                # Recalculate raw cost for savings display
                raw_res = city_purchase_cost(current_cities_count + i + 1, top_20_average, {})
                total_raw += raw_res['base_cost']

            costs_data['city_cost'] = {'city_to_buy': current_cities_count + cities_to_buy, 'base_cost': total_base, 'final_cost': total_final}
            costs_data['raw_city_cost'] = total_raw
            costs_data['total_cost_projects_only'] += total_base
            costs_data['total_cost_all_discounts'] += total_final

        # --- Project Costs ---
        if projects_to_buy:
            project_names = [p.strip() for p in projects_to_buy.split(',') if p.strip()]
            project_costs_details = {}

            # Get policy multiplier once for all projects
            project_discounts = calculate_project_discounts(nation_data)
            policy_discount_multiplier = project_discounts.get("domestic_policy_multiplier", 1.0)
            discount_rate = 0.05 * policy_discount_multiplier

            for name in project_names:
                cost_data = project_build_cost(name, nation_data)
                if cost_data:
                    project_costs_details[name] = cost_data
                    
                    # Calculate monetary value for totals
                    base_money_cost = cost_data['base_costs'].get('money', 0.0)
                    final_money_cost = cost_data['final_costs'].get('money', 0.0)
                    
                    # Calculate base resource cost
                    resource_cost = 0.0
                    for res, amount in cost_data['base_costs'].items():
                        if res != 'money':
                            resource_cost += best_buy_price_map.get(res.lower(), 0.0) * amount
                    
                    # Apply policy discount to resource cost for the 'all discounts' total
                    discounted_resource_cost = resource_cost * (1.0 - discount_rate)
                            
                    costs_data['total_cost_projects_only'] += base_money_cost + resource_cost
                    costs_data['total_cost_all_discounts'] += final_money_cost + discounted_resource_cost
            
            costs_data['project_costs'] = project_costs_details

        embed = await self._create_costs_embed(ctx, nation_data, costs_data, best_buy_price_map)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(CostsCommand(bot))
