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
import threading
import http.server
import socketserver

from Systems.PnW.Util.query import get_wars, create_v3_query_instance, get_trade_resource_values
from Systems.PnW.Util.war_calc import get_resource_prices, calculate_war_costs, calculate_improvement_cost, IMPROVEMENT_COSTS, calculate_unit_cost
from Systems.Functions.emoji import resource_emoji, military_codes, improvement_emoji_map, mention, get_animated_partial
from Systems.Functions.utils import get_local_ip, get_service_port, SERVICE_WARS_BD, release_port

try:
    from pyngrok import ngrok
except ImportError:
    ngrok = None

class WarBreakdownView(discord.ui.View):
    """A view for paginating war cost breakdowns for an alliance."""

    def __init__(self, embeds: dict, graph_file: Optional[discord.File], members_pages: List[discord.Embed] = None):
        super().__init__(timeout=300)
        self.embeds = embeds
        self.graph_file = graph_file
        self.members_pages = members_pages or []
        self.current_page_name = "summary"
        self.current_member_page = 0
        self.message = None

        # Define buttons programmatically
        self.summary_btn = discord.ui.Button(label="Summary", style=discord.ButtonStyle.secondary, emoji=get_animated_partial("bars"), row=0)
        self.military_btn = discord.ui.Button(label="Military", style=discord.ButtonStyle.primary, emoji=get_animated_partial("kill"), row=0)
        self.destruction_btn = discord.ui.Button(label="Destruction", style=discord.ButtonStyle.danger, emoji=get_animated_partial("bombq"), row=0)
        self.members_btn = discord.ui.Button(label="Members", style=discord.ButtonStyle.success, emoji=get_animated_partial("group"), row=0)
        self.back_btn = discord.ui.Button(label="Back", style=discord.ButtonStyle.grey, emoji=get_animated_partial("back"), row=1)
        self.next_btn = discord.ui.Button(label="Next", style=discord.ButtonStyle.grey, emoji=get_animated_partial("next"), row=1)

        # Assign callbacks
        self.summary_btn.callback = self.summary_button_callback
        self.military_btn.callback = self.military_button_callback
        self.destruction_btn.callback = self.destruction_button_callback
        self.members_btn.callback = self.members_button_callback
        self.back_btn.callback = self.back_button_callback
        self.next_btn.callback = self.next_button_callback

        self.update_view()

    def update_view(self):
        """Clears and adds the correct buttons based on the current page."""
        self.clear_items()
        self.add_item(self.summary_btn)
        self.add_item(self.military_btn)
        self.add_item(self.destruction_btn)
        
        if self.members_pages:
            self.add_item(self.members_btn)

        # Disable the button for the current main page
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.label and item.label.lower() == self.current_page_name:
                item.disabled = True

        # Add and configure pagination buttons only for the members page
        if self.current_page_name == "members":
            self.back_btn.disabled = self.current_member_page == 0
            self.next_btn.disabled = self.current_member_page >= len(self.members_pages) - 1
            self.add_item(self.back_btn)
            self.add_item(self.next_btn)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass

    async def show_page(self, interaction: discord.Interaction, page_name: str):
        attachments = []
        embed = None

        if page_name == "members":
            self.current_page_name = "members"
            embed = self.members_pages[self.current_member_page]
        elif self.current_page_name != page_name:
            self.current_page_name = page_name
            embed = self.embeds[page_name]
            if page_name == 'summary' and self.graph_file:
                self.graph_file.fp.seek(0)
                attachments.append(self.graph_file)
        else:
            await interaction.response.defer()
            return

        self.update_view()
        await interaction.response.edit_message(embed=embed, view=self, attachments=attachments)

    async def summary_button_callback(self, interaction: discord.Interaction):
        await self.show_page(interaction, 'summary')

    async def military_button_callback(self, interaction: discord.Interaction):
        await self.show_page(interaction, 'military')

    async def destruction_button_callback(self, interaction: discord.Interaction):
        await self.show_page(interaction, 'destruction')
    
    async def members_button_callback(self, interaction: discord.Interaction):
        await self.show_page(interaction, 'members')

    async def back_button_callback(self, interaction: discord.Interaction):
        if self.current_member_page > 0:
            self.current_member_page -= 1
            await self.show_page(interaction, "members")
        else:
            await interaction.response.defer()

    async def next_button_callback(self, interaction: discord.Interaction):
        if self.current_member_page < len(self.members_pages) - 1:
            self.current_member_page += 1
            await self.show_page(interaction, "members")
        else:
            await interaction.response.defer()

class WarsBD(commands.Cog):
    """Cog for P&W war breakdown commands."""

    def __init__(self, bot):
        self.bot = bot
        self.query_instance = create_v3_query_instance()
        self.httpd = None
        self.server_thread = None
        self.port = get_service_port(SERVICE_WARS_BD)  # Use port manager
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
        if ngrok and self.public_url:
            logging.info(f"Closing ngrok tunnel {self.public_url}...")
            ngrok.disconnect(self.public_url)
            self.public_url = None
            logging.info("ngrok tunnel closed.")
        # Release the allocated port
        release_port(SERVICE_WARS_BD)

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
            if ngrok:
                try:
                    for tunnel in ngrok.get_tunnels():
                        if tunnel.proto == 'http' and tunnel.config['addr'].endswith(f":{self.port}"):
                            ngrok.disconnect(tunnel.public_url)
                            logging.info(f"Disconnected existing ngrok tunnel: {tunnel.public_url}")

                    public_tunnel = ngrok.connect(self.port, "http")
                    self.public_url = public_tunnel.public_url
                    logging.info(f"ngrok tunnel opened at: {self.public_url}")
                except Exception as e:
                    logging.error(f"Could not start ngrok tunnel: {e}")
            else:
                logging.warning("pyngrok is not installed. Public URL will not be available.")
        except OSError as e:
            if e.winerror == 10048: # Address already in use
                 logging.warning(f"Port {self.port} is already in use. Assuming server is running.")
            else:
                raise



    def _generate_alliance_cost_graph(self, nation_breakdown: Dict[int, Any]) -> Optional[io.BytesIO]:
        nation_data = {costs['name']: costs['gross_cost'] for costs in nation_breakdown.values() if costs['gross_cost'] > 0}
        if not nation_data:
            return None

        width, height = 1200, 700
        img = Image.new('RGBA', (width, height), (48, 51, 57, 255))
        draw = ImageDraw.Draw(img)
        try:
            title_font = ImageFont.truetype("arialbd.ttf", 24)
            label_font = ImageFont.truetype("arial.ttf", 18)
        except IOError:
            title_font = ImageFont.load_default()
            label_font = ImageFont.load_default()

        pie_box = (50, 80, 650, 680)
        total_cost = sum(nation_data.values())
        
        palette = ["#3498db", "#e74c3c", "#2ecc71", "#f1c40f", "#9b59b6", "#34495e", "#1abc9c", "#e67e22", "#d35400", "#c0392b", "#8e44ad", "#2980b9"]
        colors = (palette * (len(nation_data) // len(palette) + 1))[:len(nation_data)]
        
        start_angle = -90
        sorted_nations = sorted(nation_data.items(), key=lambda item: item[1], reverse=True)

        for i, (name, value) in enumerate(sorted_nations):
            angle = (value / total_cost) * 360 if total_cost > 0 else 0
            end_angle = start_angle + angle
            draw.pieslice(pie_box, start_angle, end_angle, fill=colors[i], outline='white', width=2)
            start_angle = end_angle

        legend_x, legend_y = 700, 100
        box_size = 20
        for i, (name, value) in enumerate(sorted_nations):
            draw.rectangle([legend_x, legend_y, legend_x + box_size, legend_y + box_size], fill=colors[i])
            percentage = (value / total_cost) * 100 if total_cost > 0 else 0
            label = f"{name} - ${value:,.0f} ({percentage:.1f}%)"
            draw.text((legend_x + box_size + 10, legend_y), label, font=label_font, fill='white')
            legend_y += 30
            
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        return img_buffer

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
                details.append(f"${improvements_cost:,.0f}")
                improvement_emojis = improvement_emoji_map()
                destroyed_improvements = sorted(alliance_costs['improvements_destroyed'].items())
                limit = 15
                for i, (name, count) in enumerate(destroyed_improvements[:limit]):
                    emoji_name = improvement_emojis.get(name)
                    emoji = mention(emoji_name) if emoji_name else '🛠️'
                    details.append(f"{count} {name.replace('_', ' ').title()} {emoji}")
                
                if len(destroyed_improvements) > limit:
                    details.append(f"... and {len(destroyed_improvements) - limit} more.")
            
            # Add resistance and fortify information if available
            if alliance_costs.get('total_resistance_lost', 0) > 0:
                if details:
                    details.append("")
                details.append("**War Statistics:**")
                details.append(f"🔥 Total Resistance Lost: {alliance_costs['total_resistance_lost']:,.0f}")
                if alliance_costs.get('total_fortify_turns', 0) > 0:
                    details.append(f"🏰 Total Fortify Turns: {alliance_costs['total_fortify_turns']:,.0f}")
        
        return "\n".join(details) or "No costs in this category."

    def _create_category_embed(self, category: str, alliance_costs: dict, resource_prices: dict, alliance_name: str) -> discord.Embed:
        embed = discord.Embed(title=f"{alliance_name} - {category} Costs", color=discord.Color.blue(), timestamp=datetime.now(timezone.utc))
        
        details = self._get_category_details(alliance_costs, category, resource_prices)

        embed.add_field(name=f"⚔️ {category} Breakdown", value=details, inline=False)

        return embed

    @app_commands.command(name="wars_breakdown", description="Generates a paginated war cost breakdown for an alliance.")
    @app_commands.describe(alliance="The name or ID of the alliance to analyze.", time="Time range (e.g., '2d', '3w').", force_refresh="Set to True to bypass the cache and fetch fresh data.", opps_view="Set to True to view the breakdown from the opponent's perspective.")
    async def wars_breakdown(self, interaction: discord.Interaction, alliance: str, time: str, force_refresh: bool = False, opps_view: bool = False):
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
                # Get all wars this nation was involved in
                nation_wars = []
                for war in all_wars:
                    # Check if this nation was attacker or defender
                    if str(war.get('att_id')) == str(nation_id) or str(war.get('def_id')) == str(nation_id):
                        nation_wars.append(war)
                
                if not nation_wars:
                    continue
                
                # Aggregate detailed statistics for a comprehensive breakdown
                total_soldiers_lost, total_tanks_lost, total_aircraft_lost, total_ships_lost = 0, 0, 0, 0
                total_missiles_lost, total_nukes_lost = 0, 0
                total_gas_used, total_mun_used = 0, 0
                total_infra_destroyed, total_infra_destroyed_value = 0, 0
                loot_received, resource_loot_value = 0, 0
                loot_lost, resource_loot_lost_value, money_destroyed_val = 0, 0, 0
                improvements_destroyed_counts = {}
                total_resistance_lost = 0
                total_fortify_turns = 0

                for war in nation_wars:
                    # Determine if this nation was attacker or defender in this specific war
                    was_attacker = str(war.get('att_id')) == str(nation_id)
                    was_defender = str(war.get('def_id')) == str(nation_id)
                    
                    # Consumption and conventional unit losses
                    if was_attacker:
                        total_gas_used += war.get('att_gas_used', 0)
                        total_mun_used += war.get('att_mun_used', 0)
                        total_soldiers_lost += war.get('att_soldiers_lost', 0)
                        total_tanks_lost += war.get('att_tanks_lost', 0)
                        total_aircraft_lost += war.get('att_aircraft_lost', 0)
                        total_ships_lost += war.get('att_ships_lost', 0)
                        total_resistance_lost += (100 - war.get('att_resistance', 100))
                        total_fortify_turns += war.get('att_fortify', 0)
                    
                    if was_defender:
                        total_gas_used += war.get('def_gas_used', 0)
                        total_mun_used += war.get('def_mun_used', 0)
                        total_soldiers_lost += war.get('def_soldiers_lost', 0)
                        total_tanks_lost += war.get('def_tanks_lost', 0)
                        total_aircraft_lost += war.get('def_aircraft_lost', 0)
                        total_ships_lost += war.get('def_ships_lost', 0)
                        total_infra_destroyed += war.get('def_infra_destroyed', 0)
                        total_infra_destroyed_value += war.get('def_infra_destroyed_value', 0)
                        total_resistance_lost += (100 - war.get('def_resistance', 100))
                        total_fortify_turns += war.get('def_fortify', 0)

                    # Missile and Nuke strikes (cost for the attacker)
                    for strike in war.get('missile_strikes', []) + war.get('nuclear_strikes', []):
                        if str(strike.get('attacker_id')) == str(nation_id):
                            total_missiles_lost += strike.get('missiles_used', 0)
                            total_nukes_lost += strike.get('nukes_used', 0)

                    # Ground attacks (loot, money destroyed, improvements destroyed)
                    for attack in war.get('attacks', []):
                        if str(attack.get('att_id')) == str(nation_id): # Nation is the attacker (GAINS)
                            loot_received += attack.get('money_stolen', 0) + attack.get('money_looted', 0)
                            for res in ['coal', 'oil', 'uranium', 'iron', 'bauxite', 'lead', 'gasoline', 'munitions', 'steel', 'aluminum', 'food']:
                                looted = attack.get(f'{res}_looted', 0)
                                resource_loot_value += looted * resource_prices["sell"].get(res, 0)
                        
                        if str(attack.get('def_id')) == str(nation_id): # Nation is the defender (LOSSES)
                            money_destroyed_val += attack.get('money_destroyed', 0)
                            loot_lost += attack.get('money_stolen', 0) + attack.get('money_looted', 0)
                            for res in ['coal', 'oil', 'uranium', 'iron', 'bauxite', 'lead', 'gasoline', 'munitions', 'steel', 'aluminum', 'food']:
                                looted = attack.get(f'{res}_looted', 0)
                                resource_loot_lost_value += looted * resource_prices["sell"].get(res, 0)

                            if attack.get('improvements_destroyed'):
                                for imp_raw in attack['improvements_destroyed']:
                                    imp = imp_raw.lower().replace(' ', '_')
                                    improvements_destroyed_counts[imp] = improvements_destroyed_counts.get(imp, 0) + 1

                # Calculate total costs from aggregated data
                unit_costs = {
                    'soldiers': 5,
                    'tanks': 60 + (0.5 * resource_prices['buy'].get('steel', 0)),
                    'aircraft': 4000 + (10 * resource_prices['buy'].get('aluminum', 0)),
                    'ships': 50000 + (30 * resource_prices['buy'].get('steel', 0)),
                    'missiles': 150000 + (100 * resource_prices['buy'].get('gasoline', 0)) + (100 * resource_prices['buy'].get('munitions', 0)) + (150 * resource_prices['buy'].get('aluminum', 0)),
                    'nukes': 1750000 + (500 * resource_prices['buy'].get('uranium', 0)) + (500 * resource_prices['buy'].get('gasoline', 0)) + (1000 * resource_prices['buy'].get('aluminum', 0)),
                }
                consumption_cost = (total_gas_used * resource_prices['buy'].get('gasoline', 0)) + (total_mun_used * resource_prices['buy'].get('munitions', 0))
                improvements_cost = sum(calculate_improvement_cost(imp, resource_prices) * count for imp, count in improvements_destroyed_counts.items())

                gross_cost = (
                    (total_soldiers_lost * unit_costs['soldiers']) +
                    (total_tanks_lost * unit_costs['tanks']) +
                    (total_aircraft_lost * unit_costs['aircraft']) +
                    (total_ships_lost * unit_costs['ships']) +
                    (total_missiles_lost * unit_costs['missiles']) +
                    (total_nukes_lost * unit_costs['nukes']) +
                    total_infra_destroyed_value +
                    money_destroyed_val +
                    consumption_cost +
                    improvements_cost +
                    loot_lost +
                    resource_loot_lost_value
                )

                total_gains = loot_received + resource_loot_value
                net_cost = gross_cost - total_gains
                
                if gross_cost > 0 or total_gains > 0:
                    nation_breakdown[nation_id] = {
                        'name': nation_names.get(nation_id, f'Unknown {nation_id}'),
                        'gross_cost': gross_cost,
                        'net_cost': net_cost,
                        'total_gains': total_gains,
                        'wars_count': len(nation_wars),
                        'soldiers_lost': total_soldiers_lost,
                        'tanks_lost': total_tanks_lost,
                        'aircraft_lost': total_aircraft_lost,
                        'ships_lost': total_ships_lost,
                        'missiles_lost': total_missiles_lost,
                        'nukes_lost': total_nukes_lost,
                        'gas_used': total_gas_used,
                        'mun_used': total_mun_used,
                        'consumption_cost': consumption_cost,
                        'infra_destroyed': total_infra_destroyed,
                        'infra_destroyed_value': total_infra_destroyed_value,
                        'improvements_cost': improvements_cost,
                        'loot_received': loot_received,
                        'resource_loot_value': resource_loot_value,
                        'loot_lost': loot_lost,
                        'resource_loot_lost_value': resource_loot_lost_value,
                        'money_destroyed': money_destroyed_val,
                        'resistance_lost': total_resistance_lost,
                        'fortify_turns': total_fortify_turns,
                        'alliance_role': nation_alliance_info.get(nation_id, {}).get('role', 'unknown'),
                        'alliance_position': nation_alliance_info.get(nation_id, {}).get('alliance_position', 'unknown'),
                        'improvements_destroyed': improvements_destroyed_counts
                    }
            
            if not nation_breakdown:
                await interaction.followup.send(f"No war costs could be calculated for alliance '{alliance}' in the last {time}.")
                return

            # Calculate alliance totals by summing the nation-level breakdowns
            total_gross = sum(c['gross_cost'] for c in nation_breakdown.values())
            total_net = sum(c['net_cost'] for c in nation_breakdown.values())

            # Aggregate data for category embeds
            summed_alliance_costs = {
                "units": {},
                "consumption": {"munitions": 0, "gasoline": 0},
                "infra_lost_value": sum(c['infra_destroyed_value'] for c in nation_breakdown.values()),
                "infra_lost_levels": sum(c['infra_destroyed'] for c in nation_breakdown.values()),
                "money_destroyed": sum(c['money_destroyed'] for c in nation_breakdown.values()),
                "improvements_lost": sum(c['improvements_cost'] for c in nation_breakdown.values()),
                "improvements_destroyed": {},
                "total_resistance_lost": sum(c['resistance_lost'] for c in nation_breakdown.values()),
                "total_fortify_turns": sum(c['fortify_turns'] for c in nation_breakdown.values())
            }
            # This part requires a bit more detail for the unit breakdowns
            unit_types = ['soldiers', 'tanks', 'aircraft', 'ships', 'missiles', 'nukes']
            for unit in unit_types:
                total_lost = sum(c[f'{unit}_lost'] for c in nation_breakdown.values())
                if total_lost > 0:
                    # Note: Calculating the summed cost here is redundant as it's already in the gross cost.
                    # This is for display in the category embed only.
                    unit_cost = calculate_unit_cost(unit, resource_prices['buy'])
                    summed_alliance_costs["units"][unit] = {'lost': total_lost, 'cost': total_lost * unit_cost} 

            summed_alliance_costs["consumption"]["munitions"] = sum(c['mun_used'] for c in nation_breakdown.values())
            summed_alliance_costs["consumption"]["gasoline"] = sum(c['gas_used'] for c in nation_breakdown.values())

            # Aggregate destroyed improvements
            for costs in nation_breakdown.values():
                for imp, count in costs.get('improvements_destroyed', {}).items():
                    summed_alliance_costs["improvements_destroyed"][imp] = summed_alliance_costs["improvements_destroyed"].get(imp, 0) + count

            # Set public URL for the graph generator
            war_graph_generator.set_public_url(self.public_url, self.port)
            
            # Generate the interactive breakdown using the new module
            html_filename = war_graph_generator.generate_interactive_breakdown(nation_breakdown, alliance, resource_prices)
            
            graph_image_buffer = self._generate_alliance_cost_graph(nation_breakdown)
            graph_file = discord.File(graph_image_buffer, filename="alliance_war_cost.png") if graph_image_buffer else None
            
            if self.public_url:
                interactive_url = f"{self.public_url}/{html_filename}"
            else:
                local_ip = get_local_ip()
                interactive_url = f"http://{local_ip}:{self.port}/{html_filename}"

            # Calculate alliance totals by summing the nation-level breakdowns
            total_gross = sum(c['gross_cost'] for c in nation_breakdown.values())
            total_net = sum(c['net_cost'] for c in nation_breakdown.values())

            # The nation-level breakdown is for informational purposes to show member contributions.
            # It is NOT expected to sum up to the alliance total due to complex intra-war accounting.
            nation_ids = set()
            nation_names = {}
            for war in all_wars:
                for prefix in ['att', 'def']:
                    if str(war.get(f'{prefix}_alliance_id')) == str(alliance_id):
                        nid = war.get(f'{prefix}_id')
                        nation_obj = war.get('attacker') if prefix == 'att' else war.get('defender')
                        nname = nation_obj.get('nation_name') if nation_obj else None
                        if nid and nname:
                            nation_ids.add(nid)
                            nation_names[nid] = nname
            
            # For individual nation breakdown, we'll use a simplified approach
            # that aggregates war statistics directly from the war data
            nation_breakdown = {}
            for nation_id in nation_ids:
                nation_wars = [w for w in all_wars if str(w.get('att_id')) == str(nation_id) or str(w.get('def_id')) == str(nation_id)]
                if not nation_wars:
                    continue
                
                # Aggregate detailed statistics for a comprehensive breakdown
                total_soldiers_lost, total_tanks_lost, total_aircraft_lost, total_ships_lost = 0, 0, 0, 0
                total_missiles_lost, total_nukes_lost = 0, 0
                total_gas_used, total_mun_used = 0, 0
                total_infra_destroyed, total_infra_destroyed_value = 0, 0
                loot_received, resource_loot_value = 0, 0
                loot_lost, resource_loot_lost_value, money_destroyed_val = 0, 0, 0
                improvements_destroyed_counts = {}

                for war in nation_wars:
                    # Consumption and conventional unit losses
                    if str(war.get('att_id')) == str(nation_id):
                        total_gas_used += war.get('att_gas_used', 0)
                        total_mun_used += war.get('att_mun_used', 0)
                        total_soldiers_lost += war.get('att_soldiers_lost', 0)
                        total_tanks_lost += war.get('att_tanks_lost', 0)
                        total_aircraft_lost += war.get('att_aircraft_lost', 0)
                        total_ships_lost += war.get('att_ships_lost', 0)
                    if str(war.get('def_id')) == str(nation_id):
                        total_gas_used += war.get('def_gas_used', 0)
                        total_mun_used += war.get('def_mun_used', 0)
                        total_soldiers_lost += war.get('def_soldiers_lost', 0)
                        total_tanks_lost += war.get('def_tanks_lost', 0)
                        total_aircraft_lost += war.get('def_aircraft_lost', 0)
                        total_ships_lost += war.get('def_ships_lost', 0)
                        total_infra_destroyed += war.get('def_infra_destroyed', 0)
                        total_infra_destroyed_value += war.get('def_infra_destroyed_value', 0)

                    # Missile and Nuke strikes (cost for the attacker)
                    for strike in war.get('missile_strikes', []) + war.get('nuclear_strikes', []):
                        if str(strike.get('attacker_id')) == str(nation_id):
                            total_missiles_lost += strike.get('missiles_used', 0)
                            total_nukes_lost += strike.get('nukes_used', 0)

                    # Ground attacks (loot, money destroyed, improvements destroyed)
                    for attack in war.get('attacks', []):
                        if str(attack.get('att_id')) == str(nation_id): # Nation is the attacker (GAINS)
                            loot_received += attack.get('money_stolen', 0) + attack.get('money_looted', 0)
                            for res in ['coal', 'oil', 'uranium', 'iron', 'bauxite', 'lead', 'gasoline', 'munitions', 'steel', 'aluminum', 'food']:
                                looted = attack.get(f'{res}_looted', 0)
                                resource_loot_value += looted * resource_prices["sell"].get(res, 0)
                        
                        if str(attack.get('def_id')) == str(nation_id): # Nation is the defender (LOSSES)
                            money_destroyed_val += attack.get('money_destroyed', 0)
                            loot_lost += attack.get('money_stolen', 0) + attack.get('money_looted', 0)
                            for res in ['coal', 'oil', 'uranium', 'iron', 'bauxite', 'lead', 'gasoline', 'munitions', 'steel', 'aluminum', 'food']:
                                looted = attack.get(f'{res}_looted', 0)
                                resource_loot_lost_value += looted * resource_prices["sell"].get(res, 0)

                            if attack.get('improvements_destroyed'):
                                for imp_raw in attack['improvements_destroyed']:
                                    imp = imp_raw.lower().replace(' ', '_')
                                    improvements_destroyed_counts[imp] = improvements_destroyed_counts.get(imp, 0) + 1

                # Calculate total costs from aggregated data
                unit_costs = {
                    'soldiers': 5,
                    'tanks': 60 + (0.5 * resource_prices['buy'].get('steel', 0)),
                    'aircraft': 4000 + (10 * resource_prices['buy'].get('aluminum', 0)),
                    'ships': 50000 + (30 * resource_prices['buy'].get('steel', 0)),
                    'missiles': 150000 + (100 * resource_prices['buy'].get('gasoline', 0)) + (100 * resource_prices['buy'].get('munitions', 0)) + (150 * resource_prices['buy'].get('aluminum', 0)),
                    'nukes': 1750000 + (500 * resource_prices['buy'].get('uranium', 0)) + (500 * resource_prices['buy'].get('gasoline', 0)) + (1000 * resource_prices['buy'].get('aluminum', 0)),
                }
                consumption_cost = (total_gas_used * resource_prices['buy'].get('gasoline', 0)) + (total_mun_used * resource_prices['buy'].get('munitions', 0))
                improvements_cost = sum(calculate_improvement_cost(imp, resource_prices) * count for imp, count in improvements_destroyed_counts.items())

                gross_cost = (
                    (total_soldiers_lost * unit_costs['soldiers']) +
                    (total_tanks_lost * unit_costs['tanks']) +
                    (total_aircraft_lost * unit_costs['aircraft']) +
                    (total_ships_lost * unit_costs['ships']) +
                    (total_missiles_lost * unit_costs['missiles']) +
                    (total_nukes_lost * unit_costs['nukes']) +
                    total_infra_destroyed_value +
                    money_destroyed_val +
                    consumption_cost +
                    improvements_cost +
                    loot_lost +
                    resource_loot_lost_value
                )

                total_gains = loot_received + resource_loot_value
                net_cost = gross_cost - total_gains
                
                if gross_cost > 0 or total_gains > 0:
                    nation_breakdown[nation_id] = {
                        'name': nation_names.get(nation_id, f'Unknown {nation_id}'),
                        'gross_cost': gross_cost,
                        'net_cost': net_cost,
                        'total_gains': total_gains,
                        'wars_count': len(nation_wars),
                        'soldiers_lost': total_soldiers_lost,
                        'tanks_lost': total_tanks_lost,
                        'aircraft_lost': total_aircraft_lost,
                        'ships_lost': total_ships_lost,
                        'missiles_lost': total_missiles_lost,
                        'nukes_lost': total_nukes_lost,
                        'gas_used': total_gas_used,
                        'mun_used': total_mun_used,
                        'consumption_cost': consumption_cost,
                        'infra_destroyed': total_infra_destroyed,
                        'infra_destroyed_value': total_infra_destroyed_value,
                        'improvements_cost': improvements_cost,
                        'loot_received': loot_received,
                        'resource_loot_value': resource_loot_value,
                        'loot_lost': loot_lost,
                        'resource_loot_lost_value': resource_loot_lost_value,
                        'money_destroyed': money_destroyed_val
                    }
            
            if not nation_breakdown:
                await interaction.followup.send(f"No war costs could be calculated for alliance '{alliance}' in the last {time}.")
                return

            # Calculate alliance totals by summing the nation-level breakdowns
            total_gross = sum(c['gross_cost'] for c in nation_breakdown.values())
            total_net = sum(c['net_cost'] for c in nation_breakdown.values())

            # Aggregate data for category embeds
            summed_alliance_costs = {
                "units": {},
                "consumption": {"munitions": 0, "gasoline": 0},
                "infra_lost_value": sum(c['infra_destroyed_value'] for c in nation_breakdown.values()),
                "infra_lost_levels": sum(c['infra_destroyed'] for c in nation_breakdown.values()),
                "money_destroyed": sum(c['money_destroyed'] for c in nation_breakdown.values()),
                "improvements_lost": sum(c['improvements_cost'] for c in nation_breakdown.values()),
                "improvements_destroyed": {}
            }
            # This part requires a bit more detail for the unit breakdowns
            unit_types = ['soldiers', 'tanks', 'aircraft', 'ships', 'missiles', 'nukes']
            for unit in unit_types:
                total_lost = sum(c[f'{unit}_lost'] for c in nation_breakdown.values())
                if total_lost > 0:
                    # Note: Calculating the summed cost here is redundant as it's already in the gross cost.
                    # This is for display in the category embed only.
                    summed_alliance_costs["units"][unit] = {'lost': total_lost, 'cost': 0} 

            summed_alliance_costs["consumption"]["munitions"] = sum(c['mun_used'] for c in nation_breakdown.values())
            summed_alliance_costs["consumption"]["gasoline"] = sum(c['gas_used'] for c in nation_breakdown.values())

            html_filename = self._generate_interactive_breakdown(nation_breakdown, alliance, resource_prices)
            
            graph_image_buffer = self._generate_alliance_cost_graph(nation_breakdown)
            graph_file = discord.File(graph_image_buffer, filename="alliance_war_cost.png") if graph_image_buffer else None
            
            if self.public_url:
                interactive_url = f"{self.public_url}/{html_filename}"
            else:
                local_ip = get_local_ip()
                interactive_url = f"http://{local_ip}:{self.port}/{html_filename}"

            # Prepare summary embed based on view type
            if opps_view:
                summary_embed = discord.Embed(
                    title=f"Opponent War Summary for {alliance}",
                    description=f"Total costs for **{len(nation_breakdown)}** opponents over the last **{time}**.",
                    color=discord.Color.red(),  # Use a different color for opponent view
                    timestamp=datetime.now(timezone.utc)
                )
            else:
                summary_embed = discord.Embed(
                    title=f"Alliance War Summary for {alliance}",
                    description=f"Total costs for **{len(nation_breakdown)}** members over the last **{time}**.",
                    color=discord.Color.gold(),
                    timestamp=datetime.now(timezone.utc)
                )
            summary_embed.add_field(name="Total Gross Cost", value=f"${total_gross:,.0f}", inline=False)
            summary_embed.add_field(name="Total Net Cost", value=f"${total_net:,.0f}", inline=False)
            
            # Add active war turns info if there are active wars
            if active_wars > 0 and total_turns_left > 0:
                summary_embed.add_field(name="Active War Info", value=f"Total turns left: {total_turns_left:,}", inline=False)
            summary_embed.add_field(name="\u200b", value="\u200b", inline=True) # Spacer
            summary_embed.add_field(name="\u200b", value=f"[Click Here for a **VERY** Detailed Breakdown]({interactive_url})", inline=False)

            # Prepare member pages with a comprehensive cost/gain breakdown
            members_pages = []
            # Sort by net cost to see who profited and who lost the most
            sorted_nations = sorted(nation_breakdown.items(), key=lambda item: item[1]['net_cost'], reverse=True)

            if len(sorted_nations) > 10:
                summary_embed.add_field(name="War Participants", value=f"This alliance has {len(sorted_nations)} members with war costs. Use the 'Members' button to see them all.", inline=False)
                # Paginate members
                member_chunks = [sorted_nations[i:i + 10] for i in range(0, len(sorted_nations), 10)]
                for i, chunk in enumerate(member_chunks):
                    page_embed = discord.Embed(title=f"War Participants - Page {i+1}/{len(member_chunks)}", color=discord.Color.green())
                    page_description = ""
                    for nid, costs in chunk:
                        nation_name = costs['name']
                        wars_count = costs['wars_count']
                        gross_str = f"Gross: `${costs['gross_cost']:,.0f}`"
                        gains_str = f"Gains: `${costs['total_gains']:,.0f}`"
                        net_str = f"Net: `${costs['net_cost']:,.0f}`"
                        page_description += f"**{nation_name}** ({wars_count} wars):\n{gross_str} | {gains_str} | {net_str}\n"
                    page_embed.description = page_description
                    members_pages.append(page_embed)
            elif sorted_nations:
                member_info = ""
                for nid, costs in sorted_nations:
                    nation_name = costs['name']
                    wars_count = costs['wars_count']
                    gross_str = f"Gross: `${costs['gross_cost']:,.0f}`"
                    gains_str = f"Gains: `${costs['total_gains']:,.0f}`"
                    net_str = f"Net: `${costs['net_cost']:,.0f}`"
                    member_info += f"**{nation_name}** ({wars_count} wars):\n{gross_str} | {gains_str} | {net_str}\n"
                summary_embed.add_field(name="War Participants", value=member_info, inline=False)

            if graph_file:
                summary_embed.set_image(url=f"attachment://{graph_file.filename}")

            embeds = {
                'summary': summary_embed,
                'military': self._create_category_embed("Military", summed_alliance_costs, resource_prices, alliance),
                'destruction': self._create_category_embed("Destruction", summed_alliance_costs, resource_prices, alliance),
            }
            
            view = WarBreakdownView(embeds, graph_file, members_pages=members_pages)

            files_to_send = []
            if graph_file:
                files_to_send.append(graph_file)
            
            message = await interaction.followup.send(embed=summary_embed, view=view, files=files_to_send)
            view.message = message

        except Exception as e:
            logging.error(f"Error in /wars_breakdown command: {e}", exc_info=True)
            await interaction.followup.send(f"❌ An error occurred: {e}")

async def setup(bot):
    await bot.add_cog(WarsBD(bot))
