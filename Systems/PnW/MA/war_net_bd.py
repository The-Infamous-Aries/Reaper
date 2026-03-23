import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
import re
from Systems.PnW.Util.Graphs.war_graph import war_graph_generator
from Systems.PnW.Util.Graphs.war_graph_net_bd import war_net_breakdown_graph_generator
import asyncio
import os
import io
import math
from PIL import Image, ImageDraw, ImageFont
import random
import threading
import http.server
import socketserver
import sys

from Systems.PnW.Util.query import get_wars, create_v3_query_instance, get_trade_resource_values
from Systems.PnW.Util.war_calc import get_resource_prices, calculate_war_costs, calculate_improvement_cost, IMPROVEMENT_COSTS, calculate_unit_cost
from Systems.Functions.emoji import resource_emoji, military_codes, improvement_emoji_map, mention, get_animated_partial
from Systems.Functions.utils import get_local_ip, get_service_port, SERVICE_WARS_NET_BD, release_port
from Systems.Functions.web_server import get_public_url

class WarNetBreakdownView(discord.ui.View):
    """A view for paginating war net breakdowns for an alliance."""

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

class WarsNetBD(commands.Cog):
    """Cog for P&W war net breakdown commands."""

    def __init__(self, bot):
        self.bot = bot
        self.query_instance = create_v3_query_instance()
        self.httpd = None
        self.server_thread = None
        self.port = get_service_port(SERVICE_WARS_NET_BD)  # Use port manager
        self.public_url = None

    def _parse_time_to_utc_datetime(self, time_str: str) -> Optional[datetime]:
        if not time_str:
            return None
        match = re.match(r'(\d+)([dwm])', time_str.lower())
        if not match:
            return None
        amount, unit = int(match.group(1)), match.group(2)
        delta = timedelta()
        if unit == 'd':
            delta = timedelta(days=amount)
        elif unit == 'w':
            delta = timedelta(weeks=amount)
        elif unit == 'm':
            delta = timedelta(days=amount * 30)  # Assuming 30 days per month
        return datetime.now(timezone.utc) - delta

    def cog_load(self):
        self.start_web_server()

    def cog_unload(self):
        if self.httpd:
            logging.info("Shutting down web server...")
            self.httpd.shutdown()
            self.httpd.server_close()
            logging.info("Web server shut down.")
        release_port(SERVICE_WARS_NET_BD)

    def start_web_server(self):
        if self.server_thread and self.server_thread.is_alive():
            logging.info("Web server is already running.")
            return

        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, '..', '..', '..'))
        web_dir = os.path.join(project_root, 'web')
        os.makedirs(web_dir, exist_ok=True)

        class CustomHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=web_dir, **kwargs)

        class SilentTCPServer(socketserver.TCPServer):
            def handle_error(self, request, client_address):
                # Suppress ConnectionResetError and ConnectionAbortedError
                if isinstance(sys.exc_info()[1], (ConnectionResetError, ConnectionAbortedError)):
                    pass
                else:
                    super().handle_error(request, client_address)

        try:
            self.httpd = SilentTCPServer(("0.0.0.0", self.port), CustomHandler)
            self.server_thread = threading.Thread(target=self.httpd.serve_forever)
            self.server_thread.daemon = True
            self.server_thread.start()
            logging.info(f"Started web server on port {self.port} serving from {web_dir}")
        except OSError as e:
            if e.winerror == 10048: # Address already in use
                 logging.warning(f"Port {self.port} is already in use. Assuming server is running.")
            else:
                raise

    def _generate_alliance_cost_graph(self, nation_breakdown: Dict[int, Any], alliance_name: str, time_str: str, opps_view: bool, total_wars: int) -> Optional[io.BytesIO]:
        nation_details = {}
        for nid, costs in nation_breakdown.items():
            if costs['gross_cost'] > 0 or costs.get('total_gains', 0) > 0:
                nation_details[costs['name']] = {
                    'gross_cost': costs['gross_cost'],
                    'net_damage': costs['net_damage'],
                    'total_gains': costs.get('total_gains', 0)
                }

        if not nation_details:
            return None

        sorted_by_cost = sorted(nation_details.items(), key=lambda item: item[1]['gross_cost'], reverse=True)
        num_nations = len(sorted_by_cost)

        try:
            title_font = ImageFont.truetype("arialbd.ttf", 28)
            label_font = ImageFont.truetype("arial.ttf", 13)
        except IOError:
            title_font = ImageFont.load_default()
            label_font = ImageFont.load_default()

        items_per_column = 7
        num_columns = math.ceil(num_nations / items_per_column)
        left_cols = num_columns // 2
        right_cols = num_columns - left_cols
        
        column_width = 275
        line_height = 18
        item_padding = 20
        box_size = 14
        legend_item_height = (4 * line_height + item_padding)
        
        chart_diameter = 500
        pie_radius = 200
        ring_radius = 250
        
        width = left_cols * column_width + chart_diameter + right_cols * column_width
        height = max(1000, items_per_column * legend_item_height + 250)

        img = Image.new('RGBA', (width, height), (48, 51, 57, 255))
        draw = ImageDraw.Draw(img)

        view_str = f"Opps for {alliance_name}" if opps_view else alliance_name
        war_str = f"{total_wars} {'Wars' if total_wars > 1 else 'War'}"
        title = f"{view_str} Costs (Pie) & Net {{Ring}} for {war_str}"
        title_bbox = draw.textbbox((0, 0), title, font=title_font)
        title_width = title_bbox[2] - title_bbox[0]
        draw.text(((width - title_width) / 2, 20), title, font=title_font, fill='white')
        
        palette = ["#3498db", "#e74c3c", "#2ecc71", "#f1c40f", "#9b59b6", "#34495e", "#1abc9c", "#e67e22", "#d35400", "#c0392b", "#8e44ad", "#2980b9"]
        colors = (palette * (num_nations // len(palette) + 1))
        color_map = {name: colors[i] for i, (name, _) in enumerate(sorted_by_cost)}

        total_cost = sum(d['gross_cost'] for d in nation_details.values())
        total_gains = sum(d['total_gains'] for d in nation_details.values())
        total_net_damage = sum(d['net_damage'] for d in nation_details.values())
        total_net_abs = sum(abs(d['net_damage']) for d in nation_details.values())

        chart_center_x = left_cols * column_width + chart_diameter / 2
        chart_center_y = height / 2
        
        pie_box = (chart_center_x - pie_radius, chart_center_y - pie_radius, chart_center_x + pie_radius, chart_center_y + pie_radius)
        gains_ring_box = (chart_center_x - ring_radius, chart_center_y - ring_radius, chart_center_x + ring_radius, chart_center_y + ring_radius)

        if total_net_abs > 0:
            start_angle_net = -90
            for name, details in sorted_by_cost:
                net_value_abs = abs(details['net_damage'])
                if net_value_abs > 0:
                    angle = (net_value_abs / total_net_abs) * 360
                    end_angle_net = start_angle_net + angle
                    draw.arc(gains_ring_box, start_angle_net, end_angle_net, fill=color_map[name], width=35)
                    start_angle_net = end_angle_net

        if total_cost > 0:
            start_angle_cost = -90
            for name, details in sorted_by_cost:
                cost_value = details['gross_cost']
                if cost_value > 0:
                    angle = (cost_value / total_cost) * 360
                    end_angle_cost = start_angle_cost + angle
                    draw.pieslice(pie_box, start_angle_cost, end_angle_cost, fill=color_map[name], outline='white', width=2)
                    start_angle_cost = end_angle_cost
        
        legend_y_start = (height - (items_per_column * legend_item_height)) / 2
        
        left_items = sorted_by_cost[:left_cols * items_per_column]
        right_items = sorted_by_cost[left_cols * items_per_column:]

        for i, (name, details) in enumerate(left_items):
            col_idx = i // items_per_column
            item_idx_in_col = i % items_per_column
            current_x = col_idx * column_width + 20
            current_y = legend_y_start + item_idx_in_col * legend_item_height
            self.draw_legend_item(draw, current_x, current_y, box_size, line_height, column_width, color_map[name], name, details, total_cost, total_gains, total_net_damage, label_font)

        for i, (name, details) in enumerate(right_items):
            col_idx = i // items_per_column
            item_idx_in_col = i % items_per_column
            current_x = left_cols * column_width + chart_diameter + col_idx * column_width + 20
            current_y = legend_y_start + item_idx_in_col * legend_item_height
            self.draw_legend_item(draw, current_x, current_y, box_size, line_height, column_width, color_map[name], name, details, total_cost, total_gains, total_net_damage, label_font)

        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        return img_buffer

    def draw_legend_item(self, draw, x, y, box_size, line_height, column_width, color, name, details, total_cost, total_gains, total_net_damage, font):
        draw.rectangle([x, y, x + box_size, y + box_size], fill=color)
        max_name_width = column_width - box_size - 30
        name_to_draw = name
        if font.getbbox(name)[2] > max_name_width:
            while font.getbbox(name_to_draw + '...')[2] > max_name_width and len(name_to_draw) > 1:
                name_to_draw = name_to_draw[:-1]
            name_to_draw += '...'
        
        draw.text((x + box_size + 10, y), name_to_draw, font=font, fill='white')
        
        y_offset = y + line_height

        cost_value = details['gross_cost']
        cost_percentage = (cost_value / total_cost) * 100 if total_cost > 0 else 0
        cost_label = f"Cost: ${cost_value:,.0f} ({cost_percentage:.1f}%)"
        draw.text((x + box_size + 10, y_offset), cost_label, font=font, fill='#dddddd')
        y_offset += line_height

        gain_value = details['total_gains']
        if gain_value > 0:
            gains_label = f"Gains: ${gain_value:,.0f}"
            draw.text((x + box_size + 10, y_offset), gains_label, font=font, fill='#2ecc71')
            y_offset += line_height

        net_damage = details['net_damage']
        net_contribution_percentage = (net_damage / total_net_damage) * 100 if total_net_damage != 0 else 0
        net_color = '#e74c3c' if net_damage < 0 else '#2ecc71'
        net_damage_str = f"Net: ${net_damage:,.0f} {{{net_contribution_percentage:.1f}%}}"
        draw.text((x + box_size + 10, y_offset), net_damage_str, font=font, fill=net_color)

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

            # Calculate net resources
            net_resources = {}
            for res, amount in resource_gained.items():
                net_resources[res] = net_resources.get(res, 0) + amount
            for res, amount in resource_lost.items():
                net_resources[res] = net_resources.get(res, 0) - amount

            details.append(f"**Net Loot Value:** ${net_loot_value:,.0f}")
            details.append(f"**Net Cash:** ${net_cash:,.0f} 💰")
            
            resource_lines = []
            for res, amount in sorted(net_resources.items()):
                if amount != 0: # Only show resources with a net change
                    emoji = resource_emoji(res) or '❔'
                    # Show a plus for positive values for clarity
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
                
                # Find the last newline in the first 1024 characters
                split_at = remaining_text.rfind('\n', 0, 1024)
                
                # If no newline, split at the last space
                if split_at == -1:
                    split_at = remaining_text.rfind(' ', 0, 1024)
                
                # If no space, force split at 1024
                if split_at == -1:
                    split_at = 1024
                    
                chunks.append(remaining_text[:split_at])
                remaining_text = remaining_text[split_at:].lstrip()

            # Add the fields
            if chunks:
                embed.add_field(name=f"⚔️ {category} Breakdown", value=chunks[0], inline=False)
                for chunk in chunks[1:]:
                    if chunk: # Avoid adding empty fields
                        embed.add_field(name="\u200b", value=chunk, inline=False)
            else: # Fallback
                embed.add_field(name=f"⚔️ {category} Breakdown", value=details, inline=False)

        return embed

    def _calculate_enemy_relationships(self, all_wars: List[dict], nation_breakdown: dict, alliance_id: str) -> Dict[int, Dict[int, Dict[str, Any]]]:
        """Calculate enemy relationships and net damage between nations."""
        enemy_relationships = {}
        
        # Create a mapping of nation ID to name from nation_breakdown
        nation_id_to_name = {}
        for nid, costs in nation_breakdown.items():
            nation_id_to_name[nid] = costs['name']
        
        for war in all_wars:
            # Determine who is the alliance member and who is the enemy
            att_alliance_id = str(war.get('att_alliance_id'))
            def_alliance_id = str(war.get('def_alliance_id'))
            att_id = war.get('att_id')
            def_id = war.get('def_id')
            
            # Skip if this war doesn't involve the alliance
            if att_alliance_id != alliance_id and def_alliance_id != alliance_id:
                continue
            
            # Determine alliance member and enemy
            if att_alliance_id == alliance_id:
                alliance_member_id = att_id
                enemy_id = def_id
                enemy_alliance_id = def_alliance_id
            else:  # def_alliance_id == alliance_id
                alliance_member_id = def_id
                enemy_id = att_id
                enemy_alliance_id = att_alliance_id
            
            # Skip if we don't have data for the alliance member
            if alliance_member_id not in nation_id_to_name:
                continue
            
            # Initialize enemy relationship tracking
            if alliance_member_id not in enemy_relationships:
                enemy_relationships[alliance_member_id] = {}
            
            if enemy_id not in enemy_relationships[alliance_member_id]:
                # Get enemy name from war data
                if att_alliance_id == alliance_id:
                    enemy_obj = war.get('defender')
                else:
                    enemy_obj = war.get('attacker')
                
                enemy_name = 'Unknown Enemy'
                if enemy_obj and isinstance(enemy_obj, dict):
                    enemy_name = enemy_obj.get('nation_name', f'Enemy {enemy_id}')
                
                enemy_relationships[alliance_member_id][enemy_id] = {
                    'name': enemy_name,
                    'net_damage': 0,
                    'wars_count': 0,
                    'enemy_alliance_id': enemy_alliance_id
                }
            
            # Calculate net damage for this war (positive = alliance member dealt damage to enemy)
            # This is a simplified calculation - in reality you'd want to calculate actual war costs
            # For now, we'll use a basic estimation based on war outcomes and basic stats
            
            # Get basic war stats
            att_infra_destroyed = war.get('att_infra_destroyed', 0)
            def_infra_destroyed = war.get('def_infra_destroyed', 0)
            att_units_lost = (war.get('att_soldiers_lost', 0) + war.get('att_tanks_lost', 0) + 
                            war.get('att_aircraft_lost', 0) + war.get('att_ships_lost', 0))
            def_units_lost = (war.get('def_soldiers_lost', 0) + war.get('def_tanks_lost', 0) + 
                            war.get('def_aircraft_lost', 0) + war.get('def_ships_lost', 0))
            
            # Estimate damage based on infrastructure and unit losses
            # This is a rough estimation - you may want to refine this
            estimated_damage = 0
            
            if att_alliance_id == alliance_id:  # Alliance was attacker
                # Alliance member dealt damage to defender
                damage_dealt = (att_infra_destroyed * 1000) + (def_units_lost * 50)  # Rough estimation
                # Alliance member received damage from defender  
                damage_received = (def_infra_destroyed * 1000) + (att_units_lost * 50)
                net_damage = damage_dealt - damage_received
            else:  # Alliance was defender
                # Alliance member dealt damage to attacker
                damage_dealt = (def_infra_destroyed * 1000) + (att_units_lost * 50)
                # Alliance member received damage from attacker
                damage_received = (att_infra_destroyed * 1000) + (def_units_lost * 50)
                net_damage = damage_dealt - damage_received
            
            enemy_relationships[alliance_member_id][enemy_id]['net_damage'] += net_damage
            enemy_relationships[alliance_member_id][enemy_id]['wars_count'] += 1
        
        return enemy_relationships

    def _create_leaderboard_embed(self, nation_breakdown: dict, resource_prices: dict, alliance_name: str, opps_view: bool) -> discord.Embed:
        embed = discord.Embed(title=f"{alliance_name} - Leaderboard", color=discord.Color.gold(), timestamp=datetime.now(timezone.utc))

        # Emojis for different categories
        rank_emojis_trophy = [mention("1st"), mention("2nd"), mention("3rd")]
        rank_emojis_war = [mention("1W"), mention("2W"), mention("3W")]
        rank_emojis_money = [mention("1M"), mention("2M"), mention("3M")]
        rank_emojis_alliance = [mention("1A"), mention("2A"), mention("3A")]

        # Helper function to format the leaderboard entries
        def format_leaderboard(category_name: str, data: list, value_key: str, value_prefix: str = "$", rank_emojis: list = None) -> str:
            if rank_emojis is None:
                rank_emojis = rank_emojis_alliance  # Default to alliance emojis
            lines = [f"**{category_name}**"]
            for i, (nation_id, stats) in enumerate(data):
                lines.append(f"{rank_emojis[i]} {stats['name']} - {value_prefix}{stats[value_key]:,.0f}")
            return "\n".join(lines)

        # 1. Units Killed - using trophy emojis
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

        # 2. Cities Destruction - using trophy emojis
        cities_destruction_data = sorted(nation_breakdown.items(), key=lambda item: item[1]['infra_destroyed_value'] + item[1]['improvements_cost'], reverse=True)[:3]
        for nid, stats in cities_destruction_data:
            stats['cities_destruction_cost'] = stats['infra_destroyed_value'] + stats['improvements_cost']
        embed.add_field(name="\u200b", value=format_leaderboard("Cities Destruction", cities_destruction_data, 'cities_destruction_cost', rank_emojis=rank_emojis_trophy), inline=False)

        # 3. Spent on Bombs - using war emojis
        spent_on_bombs_data = sorted(nation_breakdown.items(), key=lambda item: (item[1]['missiles_lost'] * calculate_unit_cost('missiles', resource_prices['buy'])) + (item[1]['nukes_lost'] * calculate_unit_cost('nukes', resource_prices['buy'])), reverse=True)[:3]
        for nid, stats in spent_on_bombs_data:
            stats['bombs_cost'] = (stats['missiles_lost'] * calculate_unit_cost('missiles', resource_prices['buy'])) + (stats['nukes_lost'] * calculate_unit_cost('nukes', resource_prices['buy']))
        embed.add_field(name="\u200b", value=format_leaderboard("Spent on Bombs", spent_on_bombs_data, 'bombs_cost', rank_emojis=rank_emojis_war), inline=False)

        # 4. Had the Least Costs - using money emojis
        least_costs_data = sorted(nation_breakdown.items(), key=lambda item: item[1]['gross_cost'])[:3]
        embed.add_field(name="\u200b", value=format_leaderboard("Had the Least Costs", least_costs_data, 'gross_cost', rank_emojis=rank_emojis_money), inline=False)

        # 5. Looted the Most - using alliance emojis
        looted_most_data = sorted(nation_breakdown.items(), key=lambda item: item[1]['total_gains'], reverse=True)[:3]
        embed.add_field(name="\u200b", value=format_leaderboard("Looted the Most", looted_most_data, 'total_gains'), inline=False)

        # 6. Best Net Damage - using alliance emojis
        best_net_data = sorted(nation_breakdown.items(), key=lambda item: item[1]['net_damage'], reverse=True)[:3]
        embed.add_field(name="\u200b", value=format_leaderboard("Best Net Damage", best_net_data, 'net_damage'), inline=False)

        return embed

    @app_commands.command(name="wars_net_bd", description="Generates a paginated war net breakdown for an alliance.")
    @app_commands.describe(alliance="The name or ID of the alliance to analyze.", time="Time range (e.g., '2d', '3w').", force_refresh="Set to True to bypass the cache and fetch fresh data.", opps_view="Set to True to view the breakdown from the opponent's perspective.")
    async def wars_net_breakdown(self, interaction: discord.Interaction, alliance: str, time: str, force_refresh: bool = False, opps_view: bool = False):
        await interaction.response.defer(thinking=True)

        try:
            after_datetime = self._parse_time_to_utc_datetime(time)
            if not after_datetime:
                await interaction.followup.send("❌ Invalid time format. Use formats like '2d' or '3w'.")
                return

            resolved_alliance_ids = await self.query_instance.resolve_entities([alliance], 'alliance')
            if not resolved_alliance_ids:
                await interaction.followup.send(f"❌ Could not find an alliance named '{alliance}'.")
                return
            
            alliance_id = resolved_alliance_ids[0]

            # Determine which wars to fetch based on opps_view
            if opps_view:
                # For Opps View, we want all wars where the alliance is involved, but we'll focus on opponents
                all_wars = await get_wars(alliance_id=[alliance_id], active=False, status="ALL", after=after_datetime, before=datetime.now(timezone.utc), force_refresh=force_refresh)
            else:
                # For normal view, fetch wars for the alliance
                all_wars = await get_wars(alliance_id=[alliance_id], active=False, status="ALL", after=after_datetime, before=datetime.now(timezone.utc), force_refresh=force_refresh)
            if not all_wars:
                await interaction.followup.send(f"No wars found for alliance '{alliance}' in the last {time}.")
                return
            logging.info(f"all_wars object: {all_wars}")

            resource_prices = await get_resource_prices()

            # The nation-level breakdown is for informational purposes to show member contributions.
            # It is NOT expected to sum up to the alliance total due to complex intra-war accounting.

            # Calculate war statistics based on opps_view
            total_wars = len(all_wars)
            wars_won = 0
            wars_lost = 0
            active_wars = 0
            peace_wars = 0
            war_types = {}
            total_turns_left = 0
            
            for war in all_wars:
                # Check if war is active (no end_date or war_ended is False/None)
                if not war.get('war_ended') or not war.get('end_date'):
                    active_wars += 1
                    continue # Skip win/loss calculation for active wars

                # Get winner information
                winner = war.get('winner')
                winner_id = war.get('winner_id')
                
                # Determine if this alliance was attacker or defender
                is_attacker = str(war.get('att_alliance_id')) == str(alliance_id)
                is_defender = str(war.get('def_alliance_id')) == str(alliance_id)
                
                # Skip if this alliance wasn't involved in this war
                if not is_attacker and not is_defender:
                    continue
                
                # Handle different war outcomes - reverse logic for opps_view
                if opps_view:
                    # For Opps View, we consider the opponents' perspective
                    if winner == 'attacker':
                        if is_defender:  # Opponent (attacker) won
                            wars_won += 1
                        elif is_attacker:  # Alliance (attacker) won, so opponent lost
                            wars_lost += 1
                    elif winner == 'defender':
                        if is_attacker:  # Opponent (defender) won
                            wars_won += 1
                        elif is_defender:  # Alliance (defender) won, so opponent lost
                            wars_lost += 1
                    elif winner == 'peace' or winner == 'negotiated':
                        peace_wars += 1
                    elif winner is None and winner_id is None:
                        # War ended without clear winner (expired, etc.)
                        peace_wars += 1
                    else:
                        # Handle any other cases
                        self.logger.warning(f"Unknown war outcome for war {war.get('id')}: winner={winner}, winner_id={winner_id}")
                else:
                    # Normal view - alliance perspective
                    if winner == 'attacker':
                        if is_attacker:
                            wars_won += 1
                        elif is_defender:
                            wars_lost += 1
                    elif winner == 'defender':
                        if is_defender:
                            wars_won += 1
                        elif is_attacker:
                            wars_lost += 1
                    elif winner == 'peace' or winner == 'negotiated':
                        peace_wars += 1
                    elif winner is None and winner_id is None:
                        # War ended without clear winner (expired, etc.)
                        peace_wars += 1
                    else:
                        # Handle any other cases
                        self.logger.warning(f"Unknown war outcome for war {war.get('id')}: winner={winner}, winner_id={winner_id}")
                
                # Track war types
                war_type = war.get('war_type', 'unknown')
                war_types[war_type] = war_types.get(war_type, 0) + 1
                
                # Track turns left for active wars
                if not war.get('war_ended') and war.get('turns_left'):
                    total_turns_left += war.get('turns_left', 0)

            # Collect nations based on opps_view setting
            nation_ids = set()
            nation_names = {}
            nation_alliance_info = {}
            
            if opps_view:
                # For Opps View, collect opponent nations (those fighting against the alliance)
                for war in all_wars:
                    # Check attacker side - if alliance is defender, then attacker is opponent
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
                    
                    # Check defender side - if alliance is attacker, then defender is opponent
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
                # For normal view, collect alliance members
                for war in all_wars:
                    # Check attacker side
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
                    
                    # Check defender side
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
            
            # For individual nation breakdown, we'll use a comprehensive approach
            # that aggregates war statistics directly from the war data
            nation_breakdown = {}
            for nation_id in nation_ids:
                nation_wars = [war for war in all_wars if str(war.get('att_id')) == str(nation_id) or str(war.get('def_id')) == str(nation_id)]
                
                if not nation_wars:
                    continue

                # Use calculate_war_costs for each nation - this handles all cost components correctly
                costs = await calculate_war_costs(nation_wars, resource_prices, team1_id_set={int(nation_id)})
                
                team1_costs = costs.get('team1', {})
                team2_costs = costs.get('team2', {})

                # Calculate net damage using the same logic as war_calc.py
                # Net damage = gross cost - (loot_received + resource_loot + salvage)
                gross_cost = team1_costs.get('gross', 0)
                total_gains = team1_costs.get('loot_received', 0) + sum(team1_costs.get('resource_loot', {}).values())
                total_salvage = (team1_costs.get('salvage', {}).get('aluminum', 0) * resource_prices['buy'].get('aluminum', 0)) + \
                                 (team1_costs.get('salvage', {}).get('steel', 0) * resource_prices['buy'].get('steel', 0))
                
                net_damage = gross_cost - total_gains - total_salvage

                # Include all wars regardless of cost - we want complete data
                if True:  # Always include to show all nations involved
                    # Convert resource values back to amounts for detailed loot breakdown
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
                        'nation_id': nation_id,  # Add nation_id for tracking
                        'name': nation_names.get(nation_id, f'Unknown {nation_id}'),
                        'gross_cost': gross_cost,
                        'net_damage': net_damage,
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
                        'resource_loot_lost': resource_loot_lost_amounts,
                        'salvage_aluminum': team1_costs.get('salvage', {}).get('aluminum', 0),
                        'salvage_steel': team1_costs.get('salvage', {}).get('steel', 0)
                    }
            
            if not nation_breakdown:
                await interaction.followup.send(f"No war costs could be calculated for alliance '{alliance}' in the last {time}.")
                return

            # Correctly aggregate data for category embeds
            total_gross = sum(c['gross_cost'] for c in nation_breakdown.values())
            total_net_damage = sum(c['net_damage'] for c in nation_breakdown.values())
            total_gains = sum(c['total_gains'] for c in nation_breakdown.values())

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
                
                for res, amount in costs.get('resource_loot', {}).items():
                    summed_alliance_costs["resource_loot_gained"][res] = summed_alliance_costs["resource_loot_gained"].get(res, 0) + amount

                for res, amount in costs.get('resource_loot_lost', {}).items():
                    summed_alliance_costs["resource_loot_lost"][res] = summed_alliance_costs["resource_loot_lost"].get(res, 0) + amount

            # Calculate enemy relationships
            enemy_relationships = self._calculate_enemy_relationships(all_wars, nation_breakdown, str(alliance_id))

            # Set public URL for the graph generator
            public_url = get_public_url()
            war_net_breakdown_graph_generator.set_public_url(public_url, self.port)
            
            # Generate the interactive breakdown using the new module
            html_filename = war_net_breakdown_graph_generator.generate_interactive_net_breakdown(nation_breakdown, alliance, resource_prices, enemy_relationships)
            
            graph_image_buffer = self._generate_alliance_cost_graph(nation_breakdown, alliance, time, opps_view, total_wars)
            graph_file = discord.File(graph_image_buffer, filename="alliance_war_net.png") if graph_image_buffer else None
            
            if public_url:
                interactive_url = f"{public_url}/Wars/{html_filename}"
            else:
                local_ip = get_local_ip()
                interactive_url = f"http://{local_ip}:{self.port}/Wars/{html_filename}"

            # Prepare summary embed based on view type
            if opps_view:
                summary_embed = discord.Embed(
                    title=f"Opponent War Summary for {alliance}",
                    description=f"Total costs for **{len(nation_breakdown)}** opponents over the last **{time}**.\n**NEW:** Interactive graph now shows enemy relationships and net damage breakdown!",
                    color=discord.Color.red(),  # Use a different color for opponent view
                    timestamp=datetime.now(timezone.utc)
                )
            else:
                summary_embed = discord.Embed(
                    title=f"Alliance War Summary for {alliance}",
                    description=f"Total costs for **{len(nation_breakdown)}** members over the last **{time}**.\n**NEW:** Interactive graph now shows enemy relationships and net damage breakdown!",
                    color=discord.Color.gold(),
                    timestamp=datetime.now(timezone.utc)
                )
            summary_embed.add_field(name="Total Gross Cost", value=f"${total_gross:,.0f}", inline=False)
            summary_embed.add_field(name="Total Gains", value=f"${total_gains:,.0f}", inline=False)
            summary_embed.add_field(name="Total Net Damage", value=f"${total_net_damage:,.0f}", inline=False)
            if total_net_damage > 0:
                summary_embed.add_field(name="Net Result", value="📈 Net Loss", inline=False)
            elif total_net_damage < 0:
                summary_embed.add_field(name="Net Result", value="📉 Net Gain", inline=False)
            else:
                summary_embed.add_field(name="Net Result", value="⚖️ Break Even", inline=False)
            
            # Add active war turns info if there are active wars
            if active_wars > 0 and total_turns_left > 0:
                summary_embed.add_field(name="Active War Info", value=f"Total turns left: {total_turns_left:,}", inline=False)
            summary_embed.add_field(name="\u200b", value=f"[Click Here for a **VERY** Detailed Breakdown]({interactive_url})", inline=False)

            leaderboard_embed = self._create_leaderboard_embed(nation_breakdown, resource_prices, alliance, opps_view)

            if graph_file:
                summary_embed.set_image(url=f"attachment://{graph_file.filename}")

            embeds = {
                'summary': summary_embed,
                'military': self._create_category_embed("Military", summed_alliance_costs, resource_prices, alliance),
                'destruction': self._create_category_embed("Destruction", summed_alliance_costs, resource_prices, alliance),
                'loot': self._create_category_embed("Loot", summed_alliance_costs, resource_prices, alliance),
                'leaderboard': leaderboard_embed
            }
            
            view = WarNetBreakdownView(embeds, graph_file, leaderboard_embed)

            files_to_send = []
            if graph_file:
                files_to_send.append(graph_file)
            
            message = await interaction.followup.send(embed=summary_embed, view=view, files=files_to_send)
            view.message = message

        except Exception as e:
            logging.error(f"Error in /wars_net_bd command: {e}", exc_info=True)
            await interaction.followup.send(f"❌ An error occurred: {e}")

async def setup(bot):
    await bot.add_cog(WarsNetBD(bot))
