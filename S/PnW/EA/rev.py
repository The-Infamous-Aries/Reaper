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


from Systems.PnW.Util.query import get_color_info, V3GraphQuery, create_v3_query_instance
from Systems.Functions import emoji as emoji_mod
from Systems.PnW.Util.rev_calc import calculate_full_revenue, calculate_full_revenue_with_query
from Systems.Functions.config import PANDW_API_KEY

logger = logging.getLogger(__name__)

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
        query_value='Nation/Alliance name or ID'
    )
    @app_commands.choices(
        query_type=[
            app_commands.Choice(name='Nation', value='nation'),
            app_commands.Choice(name='Alliance', value='alliance')
        ]
    )
    async def revenue_command(self, ctx: commands.Context, query_type: str, query_value: str) -> None:
        try:
            if not query_value or not query_value.strip():
                await ctx.send("❌ Please provide a valid nation/alliance name or ID. Use `/revenuehelp` for examples.")
                return
                
            query_value = query_value.strip()
            loading_msg = await ctx.send(f"🔄 Calculating revenue for {query_type} '{query_value}'...")
            
            if query_type == 'nation':
                await self._calculate_nation_revenue(ctx, query_value, loading_msg)
            else:
                await self._calculate_alliance_revenue(ctx, query_value, loading_msg)
                
        except Exception as e:
            logger.error(f"Error in revenue command: {e}")
            error_msg = f"❌ Error calculating revenue: {str(e)}"
            if "not found" in str(e).lower():
                error_msg += "\n💡 Try using the exact name or check your spelling. Use `/revenuehelp` for examples."
            await ctx.send(error_msg)
    
    async def _calculate_nation_revenue(self, ctx, nation_query: str, loading_msg):
        try:
            if not self.query_instance:
                self.query_instance = create_v3_query_instance()

            nation_data = None
            if nation_query.isdigit():
                nation_data = await self.query_instance.get_nation_by_id(nation_query)

            if not nation_data:
                nation_data = await self.query_instance.get_nation_by_name(nation_query)

            if not nation_data:
                await loading_msg.edit(content=f"❌ Nation '{nation_query}' not found.")
                return

            revenue_data = await self._calculate_nation_revenue_data(nation_data)
            embed = await self._create_nation_revenue_embed(nation_data, revenue_data)
            await loading_msg.edit(content="", embed=embed)

        except Exception as e:
            logger.error(f"Error calculating nation revenue: {e}")
            await loading_msg.edit(content=f"❌ Error calculating nation revenue: {str(e)}")

    async def _calculate_alliance_revenue(self, ctx, alliance_query: str, loading_msg):
        try:
            if not self.query_instance:
                self.query_instance = create_v3_query_instance()

            alliance_data = await self.query_instance.resolve_alliance(alliance_query)
            if not alliance_data:
                await loading_msg.edit(content=f"❌ Alliance '{alliance_query}' not found.")
                return

            alliance_id = str(alliance_data.get('id', ''))
            nations = await self.query_instance.get_alliance_nations(alliance_id)
            if not nations:
                await loading_msg.edit(content="❌ No nations found in this alliance.")
                return

            alliance_revenue = await self._calculate_alliance_revenue_data(nations)
            embed = await self._create_alliance_revenue_embed(alliance_data, alliance_revenue)
            await loading_msg.edit(content="", embed=embed)

        except Exception as e:
            logger.error(f"Error calculating alliance revenue: {e}")
            await loading_msg.edit(content=f"❌ Error calculating alliance revenue: {str(e)}")

    async def _calculate_nation_revenue_data(self, nation_data: Dict[str, Any], trade_prices: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Calculate detailed unified revenue breakdown for a nation."""
        try:
            nation_name = nation_data.get('nation_name', 'Unknown')
            color = nation_data.get('color', 'beige').lower()
            cities = nation_data.get('cities', [])

            color_info = await get_color_info(color)
            color_bonus = color_info[0]['turn_bonus'] if color_info else 0.0

            # Use the new async wrapper
            full_revenue_data = await calculate_full_revenue_with_query(
                nation_data=nation_data,
                query_instance=self.query_instance,
                is_war=nation_data.get("war_policy") != "None" and nation_data.get("war", False) is not False,
                radiation_index=nation_data.get("radiation_index", 1000.0),
                domestic_policy=nation_data.get("domestic_policy", ""),
                color_bonus=color_bonus
            )

            day_revenue = full_revenue_data['net_income']
            turn_revenue = day_revenue / 12

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

    async def _calculate_alliance_revenue_data(self, nations: List[Dict[str, Any]]) -> Dict[str, Any]:
        try:
            if not self.query_instance:
                self.query_instance = create_v3_query_instance()

            total_revenue = 0
            nation_revenues = []
            color_breakdown: dict[str, int] = {}

            sem = asyncio.Semaphore(20)

            async def process_nation(nation):
                async with sem:
                    try:
                        return await self._calculate_nation_revenue_data(nation)
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

                color = nation_rev['color']
                color_breakdown[color] = color_breakdown.get(color, 0) + 1

            nation_revenues.sort(key=lambda x: x['turn_revenue'], reverse=True)

            return {
                'total_turn_revenue': total_revenue,
                'total_day_revenue': total_revenue * 12,
                'nation_count': len(nation_revenues),
                'nation_revenues': nation_revenues[:10],
                'color_breakdown': color_breakdown,
                'last_updated': datetime.now(tz=datetime.timezone.utc)
            }

        except Exception as e:
            logger.error(f"Error calculating alliance revenue data: {e}")
            raise

    async def _create_nation_revenue_embed(self, nation_data: Dict[str, Any], results: Dict[str, Any]) -> discord.Embed:
        nation_name = results.get('nation_name', 'Unknown Nation')
        nation_id = nation_data.get('id', '')
        nation_url = f"https://politicsandwar.com/nation/id={nation_id}"
        flag_url = nation_data.get('flag', None)
        color_name = results.get('color', 'beige').lower()

        embed_color_info = await get_color_info(color_name)
        embed_color = int(embed_color_info[0].get('hex', '000000'), 16) if embed_color_info and isinstance(embed_color_info[0], dict) else discord.Color.default()

        embed = discord.Embed(
            title=f"Revenue Report: {nation_name}",
            url=nation_url,
            color=embed_color,
            description="Calculated based on current in-game modifiers, policies, and projects.",
            timestamp=results.get('last_updated', datetime.now(tz=timezone.utc))
        )
        if flag_url:
            embed.set_thumbnail(url=flag_url)

        rev_data = results['revenue_data']

        # 1. Financial Breakdown
        gross_daily = rev_data['monetary_gross']
        gross_turn = rev_data.get('monetary_gross_turn', gross_daily / 12)
        taxes_daily = rev_data['alliance_tax']
        taxes_turn = taxes_daily / 12
        monetary_tax_daily = rev_data.get('monetary_tax', 0)
        resource_tax_daily = rev_data.get('resource_tax', 0)

        expenses = rev_data.get('expenses', {})
        imp_upkeep_turn = expenses.get('improvements', 0)
        imp_upkeep_daily = imp_upkeep_turn * 12
        infra_upkeep_turn = expenses.get('infra', 0)
        infra_upkeep_daily = infra_upkeep_turn * 12
        land_upkeep_turn = expenses.get('land', 0)
        land_upkeep_daily = land_upkeep_turn * 12
        mil_upkeep_turn = expenses.get('military', 0)
        mil_upkeep_daily = mil_upkeep_turn * 12
        res_deficit_turn = expenses.get('resource_deficit', 0)
        res_deficit_daily = res_deficit_turn * 12

        total_upkeep_turn = imp_upkeep_turn + infra_upkeep_turn + land_upkeep_turn + mil_upkeep_turn + res_deficit_turn
        total_upkeep_daily = total_upkeep_turn * 12
        
        net_daily = results['day_revenue']
        net_turn = results['turn_revenue']

        financial_text = (
            f"**Gross Income:** `${gross_daily:,.2f}` Daily / `${gross_turn:,.2f}` Turn\n"
            f"--- **Expenses (Daily / Turn)** ---\n"
            f"Improvements: `- ${imp_upkeep_daily:,.2f}` / `- ${imp_upkeep_turn:,.2f}`\n"
            f"Infrastructure: `- ${infra_upkeep_daily:,.2f}` / `- ${infra_upkeep_turn:,.2f}`\n"
            f"Land: `- ${land_upkeep_daily:,.2f}` / `- ${land_upkeep_turn:,.2f}`\n"
            f"Military: `- ${mil_upkeep_daily:,.2f}` / `- ${mil_upkeep_turn:,.2f}`\n"
            f"Resource Deficit: `- ${res_deficit_daily:,.2f}` / `- ${res_deficit_turn:,.2f}`\n"
            f"--- **Taxes (Daily / Turn)** ---\n"
            f"**Monetary Tax:** `- ${monetary_tax_daily:,.2f}` / `- ${monetary_tax_daily/12:,.2f}`\n"
            f"**Resource Tax:** `- ${resource_tax_daily:,.2f}` / `- ${resource_tax_daily/12:,.2f}`\n"
            f"**Total Alliance Tax:** `- ${taxes_daily:,.2f}` / `- ${taxes_turn:,.2f}`\n"
            f"**Net Income:** `${net_daily:,.2f}` Daily / `${net_turn:,.2f}` Turn"
        )
        embed.add_field(name="💰 Financials (Daily / Turn)", value=financial_text, inline=False)

        # 2. Gross Raw Resource Production
        gross_raw_res_text = ""
        for res_name, amount in rev_data.get('resource_production_gross', {}).items():
            daily_amount = amount
            turn_amount = amount / 12
            if daily_amount != 0:
                emoji = self._get_resource_emoji(res_name)
                gross_raw_res_text += f"{emoji} **{res_name.title()}:** +{daily_amount:,.2f} / +{turn_amount:,.2f}\n"

        if gross_raw_res_text:
            embed.add_field(name="🛠️ Gross Raw Production (Daily/Turn)", value=gross_raw_res_text, inline=True)

        # 3. Gross Manufactured Resource Production
        gross_manu_res_text = ""
        for res_name, amount in rev_data.get('manufactured_gross', {}).items():
            daily_amount = amount
            turn_amount = amount / 12
            if daily_amount != 0:
                emoji = self._get_resource_emoji(res_name)
                gross_manu_res_text += f"{emoji} **{res_name.title()}:** +{daily_amount:,.2f} / +{turn_amount:,.2f}\n"

        if gross_manu_res_text:
            embed.add_field(name="🏭 Gross Manufactured Production (Daily/Turn)", value=gross_manu_res_text, inline=True)

        # 4. Net Resource Production
        net_res_text = ""
        intermediate_goods = set(rev_data.get("intermediate_goods", []))
        for res_name, amount in rev_data.get('net_resource_production', {}).items():
            if res_name in intermediate_goods:
                continue

            daily_amount = amount
            turn_amount = amount / 12
            if daily_amount != 0:
                emoji = self._get_resource_emoji(res_name)
                if daily_amount > 0:
                    net_res_text += f"{emoji} **{res_name.title()}:** +{daily_amount:,.2f} / +{turn_amount:,.2f}\n"
                else:
                    net_res_text += f"{emoji} **{res_name.title()}:** {daily_amount:,.2f} / {turn_amount:,.2f}\n"

        if net_res_text:
            embed.add_field(name="📉 Net Production (Daily/Turn)", value=net_res_text, inline=True)

        # 4. Modifiers & Checks applied
        mods_applied = rev_data.get("domestic_policy_effects", {}).get("effects_applied", [])
        if mods_applied:
            mod_text = "\n".join([f"• {mod}" for mod in mods_applied])
            embed.add_field(name="📊 Applied Modifiers", value=mod_text, inline=True)
        else:
            embed.add_field(name="📊 Applied Modifiers", value="None", inline=True)

        embed.set_footer(text="Calculation includes Disease, Crime, and Alliance Tax deductions.")
        return embed

    async def _create_alliance_revenue_embed(self, alliance_data: Dict[str, Any], alliance_revenue: Dict[str, Any]) -> discord.Embed:
        alliance_name = alliance_data.get('name', 'Unknown Alliance')
        alliance_id = alliance_data.get('id', '')
        alliance_url = f"https://politicsandwar.com/alliance/id={alliance_id}"
        alliance_flag = alliance_data.get('flag', None)

        embed_color = discord.Color.blue()

        embed = discord.Embed(
            title=f"Alliance Revenue Report for {alliance_name}",
            url=alliance_url,
            color=embed_color,
            timestamp=alliance_revenue.get('last_updated', datetime.now(tz=datetime.timezone.utc))
        )
        if alliance_flag:
            embed.set_thumbnail(url=alliance_flag)

        embed.set_footer(text="Data from Politics and War API")

        embed.add_field(name="__Alliance Summary__", value="", inline=False)
        embed.add_field(name="Total Daily Revenue", value=f"${alliance_revenue['total_day_revenue']:,.2f}", inline=True)
        embed.add_field(name="Total Turn Revenue", value=f"${alliance_revenue['total_turn_revenue']:,.2f}", inline=True)
        embed.add_field(name="Nations in Alliance", value=f"{alliance_revenue['nation_count']:,}", inline=True)

        if alliance_revenue['nation_revenues']:
            top_nations_str = []
            for i, nation_rev in enumerate(alliance_revenue['nation_revenues'][:5]):
                nation_name = nation_rev.get('nation_name', 'Unknown')
                turn_rev = nation_rev.get('turn_revenue', 0)
                top_nations_str.append(f"{i+1}. {nation_name}: ${turn_rev:,.2f}")
            embed.add_field(name="__Top 5 Nations by Turn Revenue__", value="\n".join(top_nations_str), inline=False)

        if alliance_revenue['color_breakdown']:
            color_breakdown_str = []
            for color, count in alliance_revenue['color_breakdown'].items():
                color_breakdown_str.append(f"{color.title()}: {count}")
            embed.add_field(name="__Color Breakdown__", value="\n".join(color_breakdown_str), inline=False)

        return embed

async def setup(bot):
    await bot.add_cog(RevenueCommand(bot))
