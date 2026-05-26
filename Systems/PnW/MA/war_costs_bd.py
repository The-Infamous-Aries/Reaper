import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
import re
from Systems.PnW.Util.Graphs.war_graph import war_graph_generator
import asyncio
import os
import io
import math
from PIL import Image, ImageDraw, ImageFont
import random

from Systems.PnW.Util.query import get_wars, create_v3_query_instance, get_trade_resource_values
from Systems.PnW.Util.war_calc import get_resource_prices, calculate_war_costs, calculate_improvement_cost, IMPROVEMENT_COSTS, calculate_unit_cost
from Systems.Functions.emoji import resource_emoji, military_codes, improvement_emoji_map, mention, get_animated_partial
from Systems.Functions.utils import get_web_public_url
from Systems.Functions.irs_wars_db import IRSWarsDB
from Systems.Functions.db_paths import NW_WARS_DB_STR

class WarBreakdownView(discord.ui.View):
    """A view for paginating war cost breakdowns for an alliance."""

    def __init__(self, embeds: dict, graph_file: Optional[discord.File], leaderboard_embed: discord.Embed):
        super().__init__(timeout=1800)
        self.embeds = embeds
        self.graph_file = graph_file
        self.leaderboard_embed = leaderboard_embed
        self.current_page_name = "summary"
        self.message = None

        # Define and add buttons
        self.summary_btn = discord.ui.Button(label="Summary", style=discord.ButtonStyle.secondary, emoji=get_animated_partial("bars"), row=0)
        self.military_btn = discord.ui.Button(label="Military", style=discord.ButtonStyle.primary, emoji=get_animated_partial("kill"), row=0)
        self.destruction_btn = discord.ui.Button(label="Destruction", style=discord.ButtonStyle.danger, emoji=get_animated_partial("bombq"), row=0)
        self.loot_btn = discord.ui.Button(label="Loot", style=discord.ButtonStyle.success, emoji=get_animated_partial("mimic"), row=0)
        self.leaderboard_btn = discord.ui.Button(label="Leaderboard", style=discord.ButtonStyle.success, emoji=get_animated_partial("winners"), row=0)

        # Assign callbacks
        self.summary_btn.callback = self.summary_button_callback
        self.military_btn.callback = self.military_button_callback
        self.destruction_btn.callback = self.destruction_button_callback
        self.loot_btn.callback = self.loot_button_callback
        self.leaderboard_btn.callback = self.leaderboard_button_callback

        self.add_item(self.summary_btn)
        self.add_item(self.military_btn)
        self.add_item(self.destruction_btn)
        self.add_item(self.loot_btn)
        self.add_item(self.leaderboard_btn)

        self.update_view()

    def update_view(self):
        """Enables/disables buttons based on the current page."""
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.label:
                item.disabled = item.label.lower() == self.current_page_name
    
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass

    async def show_page(self, interaction: discord.Interaction, page_name: str):
        if self.current_page_name == page_name:
            await interaction.response.defer()
            return

        self.current_page_name = page_name
        attachments = []
        embed = None

        if page_name == "leaderboard":
            embed = self.leaderboard_embed
        else:
            embed = self.embeds[page_name]
            if page_name == 'summary' and self.graph_file:
                self.graph_file.fp.seek(0)
                attachments.append(self.graph_file)

        self.update_view()
        await interaction.response.edit_message(embed=embed, view=self, attachments=attachments)

    async def summary_button_callback(self, interaction: discord.Interaction):
        await self.show_page(interaction, 'summary')

    async def military_button_callback(self, interaction: discord.Interaction):
        await self.show_page(interaction, 'military')

    async def destruction_button_callback(self, interaction: discord.Interaction):
        await self.show_page(interaction, 'destruction')

    async def loot_button_callback(self, interaction: discord.Interaction):
        await self.show_page(interaction, 'loot')
    
    async def leaderboard_button_callback(self, interaction: discord.Interaction):
        await self.show_page(interaction, 'leaderboard')

class WarsBD(commands.Cog):
    """Cog for P&W war breakdown commands."""

    def __init__(self, bot):
        self.bot = bot
        self.query_instance = create_v3_query_instance()
        self.db = IRSWarsDB(NW_WARS_DB_STR)

    def _parse_time_to_utc_datetime(self, time_str: str) -> Optional[datetime]:
        if not time_str:
            return None
        
        combined_pattern = r'^(\d+m)?(\d+w)?(\d+d)?(\d+h)?$'
        combined_match = re.match(combined_pattern, time_str.lower())
        
        if combined_match:
            total_minutes = 0
            
            month_part = combined_match.group(1)
            if month_part:
                months = int(month_part[:-1])
                total_minutes += months * 28 * 24 * 60
            
            week_part = combined_match.group(2)
            if week_part:
                weeks = int(week_part[:-1])
                total_minutes += weeks * 7 * 24 * 60
            
            day_part = combined_match.group(3)
            if day_part:
                days = int(day_part[:-1])
                total_minutes += days * 24 * 60
            
            hour_part = combined_match.group(4)
            if hour_part:
                hours = int(hour_part[:-1])
                total_minutes += hours * 60
            
            if total_minutes > 0:
                return datetime.now(timezone.utc) - timedelta(minutes=total_minutes)
        
        match = re.match(r'(\d+)([dwm])', time_str.lower())
        if match:
            amount, unit = int(match.group(1)), match.group(2)
            delta = timedelta()
            if unit == 'd':
                delta = timedelta(days=amount)
            elif unit == 'w':
                delta = timedelta(weeks=amount)
            elif unit == 'm':
                delta = timedelta(days=amount * 28)
            return datetime.now(timezone.utc) - delta
        
        return None

    def _get_category_details(self, alliance_costs: dict, category: str, resource_prices: dict) -> str:
        details = []
        if category == "Military":
            military_emojis = military_codes()
            if alliance_costs["units"]:
                details.append("**Unit Losses:**")
                for unit, data in sorted(alliance_costs["units"].items(), key=lambda item: item[1]['cost'], reverse=True):
                    unit_emoji = military_emojis.get(unit, '')
                    units_lost = data['lost']
                    cost = data['cost']
                    details.append(f"{units_lost:,.0f} {unit.title()} {unit_emoji} - ${cost:,.0f}")

            if alliance_costs["consumption"]["munitions"] > 0 or alliance_costs["consumption"]["gasoline"] > 0:
                details.append("\n**Consumption:**")
                munitions_amount = alliance_costs['consumption']['munitions']
                gasoline_amount = alliance_costs['consumption']['gasoline']
                munitions_value = munitions_amount * resource_prices['buy'].get('munitions', 0)
                gasoline_value = gasoline_amount * resource_prices['buy'].get('gasoline', 0)
                munitions_emoji = resource_emoji('munitions') or '⛽'
                gasoline_emoji = resource_emoji('gasoline') or '⛽'
                details.append(f"{munitions_emoji}{munitions_amount:,.0f} = ${munitions_value:,.0f}\n{gasoline_emoji}{gasoline_amount:,.0f} = ${gasoline_value:,.0f}")
        elif category == "Destruction":
            if alliance_costs['infra_lost_value'] > 0:
                details.append("**Infrastructure:**")
                infra_value = alliance_costs['infra_lost_value']
                infra_levels = alliance_costs['infra_lost_levels']
                details.append(f"🏗️ {infra_levels:,.0f} levels = ${infra_value:,.0f}")

            if alliance_costs.get('money_destroyed', 0) > 0:
                if details:
                    details.append("")
                details.append("**Money Destroyed:**")
                money_destroyed_value = alliance_costs['money_destroyed']
                details.append(f"💸 ${money_destroyed_value:,.0f}")

            if alliance_costs['improvements_lost'] > 0:
                if details:
                    details.append("")
                details.append("**Improvements:**")
                improvements_cost = alliance_costs['improvements_lost']
                details.append(f"Total Value: ${improvements_cost:,.0f}")
                improvement_emojis = improvement_emoji_map()
                for name, count in sorted(alliance_costs['improvements_destroyed'].items()):
                    emoji_name = improvement_emojis.get(name)
                    emoji = mention(emoji_name) if emoji_name else '🛠️'
                    details.append(f"{emoji} {count} {name.replace('_', ' ').title()}")

        elif category == "Loot":
            cash_gained = alliance_costs.get('loot_received', 0)
            resource_gained = alliance_costs.get('resource_loot_gained', {})
            total_resource_value_gained = sum(amount * resource_prices["sell"].get(res, 0) for res, amount in resource_gained.items())
            total_gained = cash_gained + total_resource_value_gained

            cash_lost = alliance_costs.get('loot_lost', 0)
            resource_lost = alliance_costs.get('resource_loot_lost', {})
            total_resource_value_lost = sum(amount * resource_prices["sell"].get(res, 0) for res, amount in resource_lost.items())
            total_lost = cash_lost + total_resource_value_lost
            
            net_loot_value = total_gained - total_lost
            net_cash = cash_gained - cash_lost

            net_resources = {}
            for res, amount in resource_gained.items():
                net_resources[res] = net_resources.get(res, 0) + amount
            for res, amount in resource_lost.items():
                net_resources[res] = net_resources.get(res, 0) - amount

            details.append(f"**Net Loot Value:** ${net_loot_value:,.0f}")
            details.append(f"**Net Cash:** ${net_cash:,.0f} 💰")
            
            resource_lines = []
            for res, amount in sorted(net_resources.items()):
                if amount != 0:
                    emoji = resource_emoji(res) or '❔'
                    sign = '+' if amount > 0 else '-'
                    resource_lines.append(f"**{sign}{amount:,.0f}** {emoji}")
            
            if resource_lines:
                details.append("\n**Net Resources:**")
                details.append("\n".join(resource_lines))
        
        return "\n".join(details) or "No costs in this category."

    def _create_category_embed(self, category: str, alliance_costs: dict, resource_prices: dict, alliance_name: str) -> discord.Embed:
        embed = discord.Embed(title=f"{alliance_name} - {category} Costs", color=discord.Color.blue(), timestamp=datetime.now(timezone.utc))
        
        details = self._get_category_details(alliance_costs, category, resource_prices)

        if len(details) <= 1024:
            embed.add_field(name=f"⚔️ {category} Breakdown", value=details, inline=False)
        else:
            chunks = []
            remaining_text = details
            while len(remaining_text) > 0:
                if len(remaining_text) <= 1024:
                    chunks.append(remaining_text)
                    break
                split_at = remaining_text.rfind('\n', 0, 1024)
                if split_at == -1:
                    split_at = remaining_text.rfind(' ', 0, 1024)
                if split_at == -1:
                    split_at = 1024
                chunks.append(remaining_text[:split_at])
                remaining_text = remaining_text[split_at:].lstrip()

            if chunks:
                embed.add_field(name=f"⚔️ {category} Breakdown", value=chunks[0], inline=False)
                for chunk in chunks[1:]:
                    if chunk:
                        embed.add_field(name="\u200b", value=chunk, inline=False)
            else:
                embed.add_field(name=f"⚔️ {category} Breakdown", value=details, inline=False)

        return embed

    def _create_leaderboard_embed(self, nation_breakdown: dict, resource_prices: dict, alliance_name: str, opps_view: bool) -> discord.Embed:
        embed = discord.Embed(title=f"{alliance_name} - Leaderboard", color=discord.Color.gold(), timestamp=datetime.now(timezone.utc))

        rank_emojis_trophy = [mention("1st"), mention("2nd"), mention("3rd")]
        rank_emojis_war = [mention("1W"), mention("2W"), mention("3W")]
        rank_emojis_money = [mention("1M"), mention("2M"), mention("3M")]
        rank_emojis_alliance = [mention("1A"), mention("2A"), mention("3A")]

        def format_leaderboard(category_name: str, data: list, value_key: str, value_prefix: str = "$", rank_emojis: list = None) -> str:
            if rank_emojis is None:
                rank_emojis = rank_emojis_alliance
            lines = [f"**{category_name}**"]
            for i, (nation_id, stats) in enumerate(data):
                lines.append(f"{rank_emojis[i]} {stats['name']} - {value_prefix}{stats[value_key]:,.0f}")
            return "\n".join(lines)

        units_killed_data = sorted(nation_breakdown.items(), key=lambda item: (
            (item[1]['soldiers_lost'] * calculate_unit_cost('soldiers', resource_prices['buy'])) +
            (item[1]['tanks_lost'] * calculate_unit_cost('tanks', resource_prices['buy'])) +
            (item[1]['aircraft_lost'] * calculate_unit_cost('aircraft', resource_prices['buy'])) +
            (item[1]['ships_lost'] * calculate_unit_cost('ships', resource_prices['buy']))
            ), reverse=True)[:3]
        for nid, stats in units_killed_data:
            stats['units_killed_cost'] = (
                (stats['soldiers_lost'] * calculate_unit_cost('soldiers', resource_prices['buy'])) +
                (stats['tanks_lost'] * calculate_unit_cost('tanks', resource_prices['buy'])) +
                (stats['aircraft_lost'] * calculate_unit_cost('aircraft', resource_prices['buy'])) +
                (stats['ships_lost'] * calculate_unit_cost('ships', resource_prices['buy'])))
        embed.add_field(name="\u200b", value=format_leaderboard("Units Killed", units_killed_data, 'units_killed_cost', rank_emojis=rank_emojis_trophy), inline=False)

        cities_destruction_data = sorted(nation_breakdown.items(), key=lambda item: item[1]['infra_destroyed_value'] + item[1]['improvements_cost'], reverse=True)[:3]
        for nid, stats in cities_destruction_data:
            stats['cities_destruction_cost'] = stats['infra_destroyed_value'] + stats['improvements_cost']
        embed.add_field(name="\u200b", value=format_leaderboard("Cities Destruction", cities_destruction_data, 'cities_destruction_cost', rank_emojis=rank_emojis_trophy), inline=False)

        spent_on_bombs_data = sorted(nation_breakdown.items(), key=lambda item: (item[1]['missiles_lost'] * calculate_unit_cost('missiles', resource_prices['buy'])) + (item[1]['nukes_lost'] * calculate_unit_cost('nukes', resource_prices['buy'])), reverse=True)[:3]
        for nid, stats in spent_on_bombs_data:
            stats['bombs_cost'] = (stats['missiles_lost'] * calculate_unit_cost('missiles', resource_prices['buy'])) + (stats['nukes_lost'] * calculate_unit_cost('nukes', resource_prices['buy']))
        embed.add_field(name="\u200b", value=format_leaderboard("Spent on Bombs", spent_on_bombs_data, 'bombs_cost', rank_emojis=rank_emojis_war), inline=False)

        least_costs_data = sorted(nation_breakdown.items(), key=lambda item: item[1]['gross_cost'])[:3]
        embed.add_field(name="\u200b", value=format_leaderboard("Had the Least Costs", least_costs_data, 'gross_cost', rank_emojis=rank_emojis_money), inline=False)

        looted_most_data = sorted(nation_breakdown.items(), key=lambda item: item[1]['total_gains'], reverse=True)[:3]
        embed.add_field(name="\u200b", value=format_leaderboard("Looted the Most", looted_most_data, 'total_gains'), inline=False)

        best_net_data = sorted(nation_breakdown.items(), key=lambda item: item[1]['net_cost'])[:3]
        embed.add_field(name="\u200b", value=format_leaderboard("Best Net", best_net_data, 'net_cost'), inline=False)

        return embed

    async def _get_nation_breakdown(self, all_wars, alliance_id, opps_view, resource_prices):
        nation_ids = set()
        nation_names = {}
        nation_alliance_info = {}
        
        if opps_view:
            for war in all_wars:
                if str(war.get('def_alliance_id')) == str(alliance_id):
                    nid = war.get('att_id')
                    nation_obj = war.get('attacker')
                    if nation_obj and isinstance(nation_obj, dict):
                        nname = nation_obj.get('nation_name')
                        if nid and nname:
                            nation_ids.add(nid)
                            nation_names[nid] = nname
                            nation_alliance_info[nid] = {
                                'role': 'opponent_attacker',
                                'alliance_id': str(war.get('att_alliance_id', 'unknown')),
                                'alliance_position': war.get('att_alliance_position')
                            }
                
                if str(war.get('att_alliance_id')) == str(alliance_id):
                    nid = war.get('def_id')
                    nation_obj = war.get('defender')
                    if nation_obj and isinstance(nation_obj, dict):
                        nname = nation_obj.get('nation_name')
                        if nid and nname:
                            nation_ids.add(nid)
                            nation_names[nid] = nname
                            nation_alliance_info[nid] = {
                                'role': 'opponent_defender',
                                'alliance_id': str(war.get('def_alliance_id', 'unknown')),
                                'alliance_position': war.get('def_alliance_position')
                            }
        else:
            for war in all_wars:
                if str(war.get('att_alliance_id')) == str(alliance_id):
                    nid = war.get('att_id')
                    nation_obj = war.get('attacker')
                    if nation_obj and isinstance(nation_obj, dict):
                        nname = nation_obj.get('nation_name')
                        if nid and nname:
                            nation_ids.add(nid)
                            nation_names[nid] = nname
                            nation_alliance_info[nid] = {
                                'role': 'attacker',
                                'alliance_id': str(alliance_id),
                                'alliance_position': war.get('att_alliance_position')
                            }
                
                if str(war.get('def_alliance_id')) == str(alliance_id):
                    nid = war.get('def_id')
                    nation_obj = war.get('defender')
                    if nation_obj and isinstance(nation_obj, dict):
                        nname = nation_obj.get('nation_name')
                        if nid and nname:
                            nation_ids.add(nid)
                            nation_names[nid] = nname
                            nation_alliance_info[nid] = {
                                'role': 'defender',
                                'alliance_id': str(alliance_id),
                                'alliance_position': war.get('def_alliance_position')
                            }
        
        nation_breakdown = {}
        for nation_id in nation_ids:
            nation_wars = [war for war in all_wars if str(war.get('att_id')) == str(nation_id) or str(war.get('def_id')) == str(nation_id)]
            
            if not nation_wars:
                continue

            costs = await calculate_war_costs(nation_wars, resource_prices, team1_id_set={int(nation_id)})
            
            team1_costs = costs.get('team1', {})
            
            total_gains = team1_costs.get('loot_received', 0) + sum(team1_costs.get('resource_loot', {}).values())

            if team1_costs.get('gross', 0) > 0 or total_gains > 0:
                resource_loot_gained_amounts = {}
                for resource, value in team1_costs.get('resource_loot', {}).items():
                    price = resource_prices.get("sell", {}).get(resource, 0)
                    if price > 0:
                        resource_loot_gained_amounts[resource] = value / price
                        
                resource_loot_lost_amounts = {}
                for resource, value in team1_costs.get('resource_loot_lost', {}).items():
                    price = resource_prices.get("sell", {}).get(resource, 0)
                    if price > 0:
                        resource_loot_lost_amounts[resource] = value / price

                nation_breakdown[nation_id] = {
                    'name': nation_names.get(nation_id, f'Unknown {nation_id}'),
                    'gross_cost': team1_costs.get('gross', 0),
                    'net_cost': team1_costs.get('net', 0),
                    'total_gains': total_gains,
                    'wars_count': len(nation_wars),
                    'soldiers_lost': team1_costs.get('units', {}).get('soldiers', {}).get('lost', 0),
                    'tanks_lost': team1_costs.get('units', {}).get('tanks', {}).get('lost', 0),
                    'aircraft_lost': team1_costs.get('units', {}).get('aircraft', {}).get('lost', 0),
                    'ships_lost': team1_costs.get('units', {}).get('ships', {}).get('lost', 0),
                    'missiles_lost': team1_costs.get('units', {}).get('missiles', {}).get('lost', 0),
                    'nukes_lost': team1_costs.get('units', {}).get('nukes', {}).get('lost', 0),
                    'gas_used': team1_costs.get('consumption', {}).get('gasoline', 0),
                    'mun_used': team1_costs.get('consumption', {}).get('munitions', 0),
                    'consumption_cost': (team1_costs.get('consumption', {}).get('munitions', 0) * resource_prices['buy'].get("munitions", 0)) + \
                                        (team1_costs.get('consumption', {}).get('gasoline', 0) * resource_prices['buy'].get("gasoline", 0)),
                    'infra_destroyed': team1_costs.get('infra_lost_levels', 0),
                    'infra_destroyed_value': team1_costs.get('infra_lost_value', 0),
                    'improvements_cost': team1_costs.get('improvements_lost', 0),
                    'loot_received': team1_costs.get('loot_received', 0),
                    'resource_loot_value': sum(team1_costs.get('resource_loot', {}).values()),
                    'loot_lost': team1_costs.get('loot_lost', 0),
                    'resource_loot_lost_value': sum(team1_costs.get('resource_loot_lost', {}).values()),
                    'money_destroyed': team1_costs.get('money_destroyed', 0),
                    'alliance_role': nation_alliance_info.get(nation_id, {}).get('role', 'unknown'),
                    'alliance_position': nation_alliance_info.get(nation_id, {}).get('alliance_position', 'unknown'),
                    'improvements_destroyed': team1_costs.get('improvements_destroyed', {}),
                    'resource_loot_gained': resource_loot_gained_amounts,
                    'resource_loot_lost': resource_loot_lost_amounts
                }
        return nation_breakdown

    @app_commands.command(name="wars_cost_bd", description="Generates a paginated war cost breakdown for an alliance.")
    @app_commands.describe(alliance="The name or ID of the alliance to analyze.", time="Time range: '2d', '3w', '1m' or combined '2m2w5d3h'. Leave blank for ALL time.", force_refresh="Set to True to bypass the cache and fetch fresh data.", opps_view="Set to True to view the breakdown from the opponent's perspective.")
    async def wars_breakdown(self, interaction: discord.Interaction, alliance: str, time: Optional[str] = None, force_refresh: bool = False, opps_view: bool = False):
        await interaction.response.defer(thinking=True)

        try:
            after_datetime = None
            if time:
                after_datetime = self._parse_time_to_utc_datetime(time)
                if not after_datetime:
                    await interaction.followup.send("❌ Invalid time format. Use formats like '2d', '3w', '1m', or combined like '2m2w5d3h' (months=28d, weeks=7d, days=24h, hours=60m). Leave blank for all time.")
                    return

            time_label = time if time else "all time"

            # Check for Darkstar
            if alliance.lower() in ["darkstar", "ds", "10259"]:
                all_wars = await self.db.get_all_wars_for_alliance_in_range(
                    10259,
                    start_date=after_datetime.date() if after_datetime else None,
                )
                alliance_id = 10259
            else:
                resolved_alliance_ids = await self.query_instance.resolve_entities([alliance], 'alliance')
                if not resolved_alliance_ids:
                    await interaction.followup.send(f"❌ Could not find an alliance named '{alliance}'.")
                    return
                
                alliance_id = resolved_alliance_ids[0]
                all_wars = await get_wars(alliance_id=[alliance_id], active=False, status="ALL", after=after_datetime, before=datetime.now(timezone.utc), force_refresh=force_refresh)

            if not all_wars:
                await interaction.followup.send(f"No wars found for alliance '{alliance}'" + (f" in the last {time}." if time else "."))
                return

            # Attach attacks to each war so calculate_war_costs has loot + missile data
            if alliance.lower() in ["darkstar", "ds", "10259"]:
                war_ids = [int(w['id']) for w in all_wars if w.get('id')]
                attacks_by_war = await self.db.get_attacks_for_wars(war_ids)
                for war in all_wars:
                    war['attacks'] = attacks_by_war.get(int(war['id']), [])

            resource_prices = await get_resource_prices()
            nation_breakdown = await self._get_nation_breakdown(all_wars, alliance_id, opps_view, resource_prices)
            
            if not nation_breakdown:
                await interaction.followup.send(f"No war costs could be calculated for alliance '{alliance}'" + (f" in the last {time}." if time else "."))
                return

            total_gross = sum(c['gross_cost'] for c in nation_breakdown.values())
            total_net = sum(c['net_cost'] for c in nation_breakdown.values())

            summed_alliance_costs = {
                "units": {},
                "consumption": {
                    "munitions": sum(c['mun_used'] for c in nation_breakdown.values()),
                    "gasoline": sum(c['gas_used'] for c in nation_breakdown.values())
                },
                "infra_lost_value": sum(c['infra_destroyed_value'] for c in nation_breakdown.values()),
                "infra_lost_levels": sum(c['infra_destroyed'] for c in nation_breakdown.values()),
                "money_destroyed": sum(c['money_destroyed'] for c in nation_breakdown.values()),
                "improvements_lost": sum(c['improvements_cost'] for c in nation_breakdown.values()),
                "improvements_destroyed": {},
                "loot_received": sum(c['loot_received'] for c in nation_breakdown.values()),
                "resource_loot_gained": {},
                "loot_lost": sum(c['loot_lost'] for c in nation_breakdown.values()),
                "resource_loot_lost": {}
            }

            unit_types = ['soldiers', 'tanks', 'aircraft', 'ships', 'missiles', 'nukes']
            for unit in unit_types:
                total_lost = sum(c[f'{unit}_lost'] for c in nation_breakdown.values())
                if total_lost > 0:
                    unit_cost = calculate_unit_cost(unit, resource_prices['buy'])
                    summed_alliance_costs["units"][unit] = {'lost': total_lost, 'cost': total_lost * unit_cost}

            for costs in nation_breakdown.values():
                for imp, count in costs.get('improvements_destroyed', {}).items():
                    summed_alliance_costs["improvements_destroyed"][imp] = summed_alliance_costs["improvements_destroyed"].get(imp, 0) + count
                
                for res, amount in costs.get('resource_loot_gained', {}).items():
                    summed_alliance_costs["resource_loot_gained"][res] = summed_alliance_costs["resource_loot_gained"].get(res, 0) + amount

                for res, amount in costs.get('resource_loot_lost', {}).items():
                    summed_alliance_costs["resource_loot_lost"][res] = summed_alliance_costs["resource_loot_lost"].get(res, 0) + amount

            from urllib.parse import quote_plus
            public_url = get_web_public_url()
            interactive_url = f"{public_url}/api/pnw/war_costs?alliance={quote_plus(alliance)}&time={quote_plus(time or 'all')}&force_refresh={force_refresh}&opps_view={opps_view}"

            if opps_view:
                summary_embed = discord.Embed(
                    title=f"Opponent War Summary for {alliance}",
                    description=f"Total costs for **{len(nation_breakdown)}** opponents over **{time_label}**.",
                    color=discord.Color.red(),
                    timestamp=datetime.now(timezone.utc)
                )
            else:
                summary_embed = discord.Embed(
                    title=f"Alliance War Summary for {alliance}",
                    description=f"Total costs for **{len(nation_breakdown)}** members over **{time_label}**.",
                    color=discord.Color.gold(),
                    timestamp=datetime.now(timezone.utc)
                )
            summary_embed.add_field(name="Total Gross Cost", value=f"${total_gross:,.0f}", inline=False)
            summary_embed.add_field(name="Total Net Cost", value=f"${total_net:,.0f}", inline=False)
            summary_embed.add_field(name="\u200b", value=f"[Click Here for a **VERY** Detailed Breakdown]({interactive_url})", inline=False)

            leaderboard_embed = self._create_leaderboard_embed(nation_breakdown, resource_prices, alliance, opps_view)

            embeds = {
                'summary': summary_embed,
                'military': self._create_category_embed("Military", summed_alliance_costs, resource_prices, alliance),
                'destruction': self._create_category_embed("Destruction", summed_alliance_costs, resource_prices, alliance),
                'loot': self._create_category_embed("Loot", summed_alliance_costs, resource_prices, alliance),
                'leaderboard': leaderboard_embed
            }
            
            view = WarBreakdownView(embeds, None, leaderboard_embed)
            
            message = await interaction.followup.send(embed=summary_embed, view=view)
            view.message = message

        except Exception as e:
            logging.error(f"Error in /wars_breakdown command: {e}", exc_info=True)
            await interaction.followup.send(f"❌ An error occurred: {e}")

async def setup(bot):
    await bot.add_cog(WarsBD(bot))
