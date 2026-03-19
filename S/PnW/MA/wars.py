import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional, List, Union
from datetime import datetime, timedelta, timezone
import re
import io
import time
import math
from PIL import Image, ImageDraw, ImageFont
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER

from Systems.PnW.Util.query import get_wars, get_trade_resource_values, create_v3_query_instance
from Systems.Functions.emoji import resource_emoji, military_codes, improvement_emoji_map, mention, get_animated_partial
from Systems.PnW.Util.war_calc import (
    get_resource_prices,
    calculate_war_costs,
    calculate_single_war_costs,
    calculate_improvement_cost,
    WAR_SUMMARY_THRESHOLD
)
import uuid

class Wars(commands.Cog):
    """Cog for P&W war-related commands."""

    def __init__(self, bot):
        self.bot = bot
        self.query_instance = create_v3_query_instance()
        self._war_cache = {}  # Cache for war data
        self._cache_ttl = 300  # 5 minutes cache

    def _parse_time_to_utc_datetime(self, time_str: str) -> Optional[datetime]:
        """Parse time string like '1d', '3w' into a UTC datetime object."""
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

    def _get_cache_key(self, team1_ids, team2_ids, days_ago):
        """Generate a cache key for war data."""
        key_parts = []
        if team1_ids:
            key_parts.extend(sorted(team1_ids))
        if team2_ids:
            key_parts.extend(sorted(team2_ids))
        if days_ago is not None:
            key_parts.append(f"days_{days_ago}")
        return f"wars_{'_'.join(map(str, key_parts))}"

    def _get_cached_wars(self, cache_key):
        """Get cached war data if still valid."""
        if cache_key in self._war_cache:
            data, timestamp = self._war_cache[cache_key]
            if time.time() - timestamp < self._cache_ttl:
                return data
        return None

    def _set_cached_wars(self, cache_key, wars_data):
        """Cache war data with current timestamp."""
        self._war_cache[cache_key] = (wars_data, time.time())

    def _parse_identifiers(self, identifiers_str: str) -> List[Union[int, str]]:
        """Parse comma-separated identifiers (IDs or names)."""
        if not identifiers_str:
            return []
        
        identifiers = []
        for item in identifiers_str.split(','):
            item = item.strip()
            if item.isdigit():
                identifiers.append(int(item))
            else:
                identifiers.append(item)
        return identifiers

    @app_commands.command(name="wars", description="War-related commands for P&W")
    @app_commands.describe(
        team1_type="Type of Team 1 (Alliance or Nation)",
        team1="Comma-separated alliance/nation names or IDs for Team 1",
        time="Time range (e.g., '1d', '3w', '5m') for recent wars",
        team2="Optional: Comma-separated alliance/nation names or IDs for Team 2",
        team2_type="Optional: Type of Team 2 (Alliance or Nation)"
    )
    @app_commands.choices(
        team1_type=[
            app_commands.Choice(name="Alliance", value="alliance"),
            app_commands.Choice(name="Nation", value="nation"),
        ],
        team2_type=[
            app_commands.Choice(name="Alliance", value="alliance"),
            app_commands.Choice(name="Nation", value="nation"),
        ]
    )
    async def wars(self, interaction: discord.Interaction, team1_type: str, team1: str, time: Optional[str] = None, team2: Optional[str] = None, team2_type: Optional[str] = None):
        """Calculates the cost of a war for the given team1 and team2."""
        try:
            await interaction.response.defer(thinking=True)
        except discord.NotFound:
            logging.warning("Interaction expired before deferral. Command will not be processed.")
            return
        
        try:
            after_datetime = self._parse_time_to_utc_datetime(time)
            team1_ids = self._parse_identifiers(team1)

            if not team1_ids:
                await interaction.followup.send("❌ Please provide at least one Team 1 identifier.")
                return

            resource_prices = await get_resource_prices()

            all_nation_ids = []
            all_alliance_ids = []

            resolved_team1_ids = await self.query_instance.resolve_entities(team1_ids, team1_type)
            if team1_type == 'nation':
                all_nation_ids.extend(resolved_team1_ids)
            else:
                all_alliance_ids.extend(resolved_team1_ids)

            resolved_team2_ids = []
            if team2 and team2_type:
                team2_ids = self._parse_identifiers(team2)
                resolved_team2_ids = await self.query_instance.resolve_entities(team2_ids, team2_type)
                if team2_type == 'nation':
                    all_nation_ids.extend(resolved_team2_ids)
                else:
                    all_alliance_ids.extend(resolved_team2_ids)

            cache_key = self._get_cache_key(resolved_team1_ids, resolved_team2_ids, after_datetime.isoformat() if after_datetime else None)
            
            all_wars = self._get_cached_wars(cache_key)
            if all_wars is None:
                before_datetime = datetime.now(timezone.utc)
                all_wars = await get_wars(
                    nation_id=list(set(all_nation_ids)),
                    alliance_id=list(set(all_alliance_ids)),
                    active=False,
                    status="ALL",
                    before=before_datetime,
                    after=after_datetime
                )
                if all_wars is not None:
                    self._set_cached_wars(cache_key, all_wars)

            if all_wars is None:
                await interaction.followup.send("❌ Error fetching war data from the API.")
                return

            wars_data = []
            team1_id_set = set(resolved_team1_ids)
            
            if team2 and team2_type:
                team2_id_set = set(resolved_team2_ids)
                for war in all_wars:
                    # Collect all attacker and defender IDs from the war record
                    war_att_ids = {
                        int(war[key]) for key in ('att_id', 'att_alliance_id') if war.get(key)
                    }
                    war_def_ids = {
                        int(war[key]) for key in ('def_id', 'def_alliance_id') if war.get(key)
                    }

                    # Check for a match in either direction
                    is_match = (
                        (not team1_id_set.isdisjoint(war_att_ids) and not team2_id_set.isdisjoint(war_def_ids)) or
                        (not team1_id_set.isdisjoint(war_def_ids) and not team2_id_set.isdisjoint(war_att_ids))
                    )

                    if is_match:
                        wars_data.append(war)
            else:
                # If only a team1 is specified, find all wars they are involved in
                str_team1_id_set = {str(i) for i in team1_id_set}
                for war in all_wars:
                    if (str(war.get('att_id')) in str_team1_id_set or
                        str(war.get('att_alliance_id')) in str_team1_id_set or
                        str(war.get('def_id')) in str_team1_id_set or
                        str(war.get('def_alliance_id')) in str_team1_id_set):
                        wars_data.append(war)

            if not wars_data:
                await interaction.followup.send("❌ No wars found for the specified criteria.")
                return
            
            pov_ids = team1_id_set if not (team2 and team2_type) else None
            team2_id_set = set(resolved_team2_ids) if resolved_team2_ids else None
            costs = await calculate_war_costs(wars_data, resource_prices, team1_id_set=team1_id_set, team2_id_set=team2_id_set)
            
            embeds = {}
            
            # Summary Embed
            summary_embed = self._create_summary_embed(costs, wars_data, time, team1, pov_ids)
            embeds['summary'] = summary_embed

            # Category Embeds
            embeds['military'] = self._create_category_embed("Military", costs, resource_prices)
            embeds['destruction'] = self._create_category_embed("Destruction", costs, resource_prices)
            embeds['loot'] = self._create_category_embed("Loot", costs, resource_prices)

            war_report_file = None
            if len(wars_data) > WAR_SUMMARY_THRESHOLD:
                war_report_file = await self._generate_war_report_file(wars_data, resource_prices, pov_ids, team1_type, team1, team2_type, team2, team1_id_set, team2_id_set)
            else:
                for i, war in enumerate(wars_data):
                    team1_name, team2_name = self._get_war_participants(war, team1_type, team1, team2_type, team2, pov_ids)
                    reason = war.get('reason', 'No reason provided.')
                    winner_id = war.get('winner_id')
                    winner_name = "Ongoing"
                    if winner_id:
                        if str(winner_id) == str(war.get('att_id')) or str(winner_id) == str(war.get('att_alliance_id')):
                            winner_name = team1_name
                        elif str(winner_id) == str(war.get('def_id')) or str(winner_id) == str(war.get('def_alliance_id')):
                            winner_name = team2_name
                        else:
                            winner_name = f"ID: {winner_id}"

                    summary_embed.add_field(
                        name=f"War #{i+1}: {team1_name} vs {team2_name}",
                        value=f"**Reason:** {reason}\n**Winner:** {winner_name}",
                        inline=False
                    )

            graph_file = None
            try:
                graph_image = await self._generate_war_cost_graph(costs, resource_prices)
                if graph_image:
                    graph_file = discord.File(graph_image, filename="war_cost_graph.png")
                    summary_embed.set_image(url="attachment://war_cost_graph.png")
            except Exception as e:
                logging.error(f"Error generating war cost graph: {e}", exc_info=True)

            files_to_send = []
            if graph_file:
                files_to_send.append(graph_file)
            
            view = WarCostView(embeds, graph_file=graph_file, war_report_file=war_report_file)
            
            await interaction.followup.send(embed=summary_embed, view=view, files=files_to_send)
            
            view.message = await interaction.original_response()
            
        except Exception as e:
            logging.error(f"Error in wars cost command: {e}", exc_info=True)
            await interaction.followup.send(f"❌ An error occurred while calculating war costs: {str(e)}")

    def _get_war_participants(self, war: dict, team1_type: str, team1: str, team2_type: Optional[str], team2: Optional[str], pov_ids: Optional[set]) -> tuple[str, str]:
        """
        Determine the names of the war participants.
        If pov_ids is provided, returns (pov_entity_name, opponent_name).
        Otherwise, returns (actual_attacker_name, actual_defender_name).
        """
        str_pov_ids = {str(i) for i in pov_ids} if pov_ids else None

        if str_pov_ids:
            pov_name = team1
            is_pov_actual_attacker = str(war.get('att_id')) in str_pov_ids or str(war.get('att_alliance_id')) in str_pov_ids
            
            if is_pov_actual_attacker:
                opponent_name = (war.get('defender') or {}).get('nation_name') or (war.get('defender') or {}).get('alliance_name') or "Unknown"
            else:
                opponent_name = (war.get('attacker') or {}).get('nation_name') or (war.get('attacker') or {}).get('alliance_name') or "Unknown"
            return pov_name, opponent_name

        team1_name = (war.get('attacker') or {}).get('nation_name') or team1
        if team1_type == 'alliance':
            team1_name = team1

        team2_name = "Unknown"
        if team2_type and team2:
            if team2_type == 'alliance':
                team2_name = team2
            else:
                team2_name = (war.get('defender') or {}).get('nation_name') or team2
        else:
            team2_name = (war.get('defender') or {}).get('nation_name') or (war.get('defender') or {}).get('alliance_name') or "Unknown"
        
        return team1_name, team2_name

    def _create_summary_embed(self, costs: dict, wars_data: List[dict], time: Optional[str], team1: str, pov_ids: Optional[set]) -> discord.Embed:
        """Create the summary embed."""
        description = f"Summary of wars involving specified entities{f' in the last {time}' if time else ''}"
        if pov_ids:
            description = f"Summary of all wars for {team1}{f' in the last {time}' if time else ''}"

        summary_embed = discord.Embed(
            title="📊 War Cost Summary",
            description=description,
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )

        if pov_ids:
            overview_value = f"⚔️ Your Total Cost: `${costs['team1']['gross']:,.0f}`\n" \
                             f"🛡️ Opponent Total Cost: `${costs['team2']['gross']:,.0f}`\n" \
                             f"⚔️ Your Net: `${costs['team1']['net']:,.0f}`\n" \
                             f"🛡️ Opponent Net: `${costs['team2']['net']:,.0f}`\n" \
                             f"Wars Analyzed: **{len(wars_data)}**\n" \
                             f"Time Range: **{time or 'All time'}**"
        else:
            overview_value = f"⚔️ Team 1 Total Cost: `${costs['team1']['gross']:,.0f}`\n" \
                             f"🛡️ Team 2 Total Cost: `${costs['team2']['gross']:,.0f}`\n" \
                             f"⚔️ Team 1 Net: `${costs['team1']['net']:,.0f}`\n" \
                             f"🛡️ Team 2 Net: `${costs['team2']['net']:,.0f}`\n" \
                             f"Wars Analyzed: **{len(wars_data)}**\n" \
                             f"Time Range: **{time or 'All time'}**"
        
        summary_embed.add_field(name="Overview", value=overview_value, inline=False)

        if len(wars_data) > WAR_SUMMARY_THRESHOLD:
            summary_embed.add_field(
                name="Detailed War Report",
                value="Click the 'Breakdown PDF' button for a detailed report.",
                inline=False
            )
        return summary_embed

    def _create_category_embed(self, category: str, costs: dict, resource_prices: dict) -> discord.Embed:
        """Create an embed for a specific cost category."""
        embed = discord.Embed(title=f"{category} Costs", color=discord.Color.blue(), timestamp=datetime.now(timezone.utc))
        
        team1_details = self._get_category_details("team1", category, costs, resource_prices)
        team2_details = self._get_category_details("team2", category, costs, resource_prices)

        embed.add_field(name="⚔️ Team 1", value=team1_details if team1_details else "No costs", inline=True)
        embed.add_field(name="🛡️ Team 2", value=team2_details if team2_details else "No costs", inline=True)

        return embed

    def _get_category_details(self, side: str, category: str, costs: dict, resource_prices: dict) -> str:
        """Get formatted details for a specific category and side."""
        details = []
        if category == "Military":
            military_emojis = military_codes()
            if costs[side]["units"]:
                details.append("**Unit Losses:**")
                for unit, data in costs[side]["units"].items():
                    unit_emoji = military_emojis.get(unit, '')
                    units_lost = data['lost']
                    cost = data['cost']
                    details.append(f"{units_lost:,.0f} {unit.title()} {unit_emoji} - ${cost:,.0f}")

            if costs[side]["consumption"]["munitions"] > 0 or costs[side]["consumption"]["gasoline"] > 0:
                details.append("\n**Consumption:**")
                munitions_amount = costs[side]['consumption']['munitions']
                gasoline_amount = costs[side]['consumption']['gasoline']
                munitions_value = munitions_amount * resource_prices['buy'].get('munitions', 0)
                gasoline_value = gasoline_amount * resource_prices['buy'].get('gasoline', 0)
                munitions_emoji = resource_emoji('munitions') or '⛽'
                gasoline_emoji = resource_emoji('gasoline') or '⛽'
                details.append(f"{munitions_emoji}{munitions_amount:,.0f} = ${munitions_value:,.0f}\n{gasoline_emoji}{gasoline_amount:,.0f} = ${gasoline_value:,.0f}")
        elif category == "Destruction":
            if costs[side]['infra_lost_value'] > 0:
                details.append("**Infrastructure:**")
                infra_value = costs[side]['infra_lost_value']
                infra_levels = costs[side]['infra_lost_levels']
                details.append(f"🏗️ {infra_levels:,.0f} levels = ${infra_value:,.0f}")

            if costs[side].get('money_destroyed', 0) > 0:
                if details:
                    details.append("")
                details.append("**Money Destroyed:**")
                money_destroyed_value = costs[side]['money_destroyed']
                details.append(f"💸 ${money_destroyed_value:,.0f}")

            if costs[side]['improvements_lost'] > 0:
                if details:
                    details.append("")
                details.append("**Improvements:**")
                improvements_cost = costs[side]['improvements_lost']
                details.append(f"${improvements_cost:,.0f}")
                improvement_emojis = improvement_emoji_map()
                for name, count in sorted(costs[side]['improvements_destroyed'].items()):
                    emoji_name = improvement_emojis.get(name)
                    emoji = mention(emoji_name) if emoji_name else '🛠️'
                    details.append(f"{count} {name.replace('_', ' ').title()} {emoji}")
        elif category == "Loot":
            cash_gained = costs[side].get('loot_received', 0)
            resource_gained = costs[side].get('resource_loot', {})
            total_gained = cash_gained + sum(resource_gained.values())

            if total_gained > 0:
                details.append(f"**Gained: ${total_gained:,.0f}**")
                if cash_gained > 0:
                    details.append(f"  Cash: ${cash_gained:,.0f}")
                for resource, value in sorted(resource_gained.items(), key=lambda item: item[1], reverse=True):
                    price = resource_prices.get("sell", {}).get(resource, 1)
                    original_amount = value / price if price > 0 else 0
                    emoji = resource_emoji(resource) or ''
                    details.append(f"{emoji} {original_amount:,.0f}")
        
        return "\n".join(details)

    def _get_category_details_for_pdf(self, side: str, category: str, costs: dict, resource_prices: dict) -> str:
        """Get formatted details for a specific category and side, formatted for PDF output."""
        details = []
        if category == "Military":
            if costs[side]["units"]:
                details.append("<b>Unit Losses:</b>")
                for unit, data in costs[side]["units"].items():
                    details.append(f"{data['lost']:,.0f} {unit.title()} - ${data['cost']:,.0f}")

            if costs[side]["consumption"]["munitions"] > 0 or costs[side]["consumption"]["gasoline"] > 0:
                details.append("<br/><b>Consumption:</b>")
                munitions_amount = costs[side]['consumption']['munitions']
                gasoline_amount = costs[side]['consumption']['gasoline']
                munitions_value = munitions_amount * resource_prices['buy'].get('munitions', 0)
                gasoline_value = gasoline_amount * resource_prices['buy'].get('gasoline', 0)
                details.append(f"(Munitions) {munitions_amount:,.0f} = ${munitions_value:,.0f}<br/>(Gasoline) {gasoline_amount:,.0f} = ${gasoline_value:,.0f}")
        elif category == "Destruction":
            if costs[side]['infra_lost_value'] > 0:
                details.append("<b>Infrastructure:</b>")
                infra_value = costs[side]['infra_lost_value']
                infra_levels = costs[side]['infra_lost_levels']
                details.append(f"{infra_levels:,.0f} levels = ${infra_value:,.0f}")

            if costs[side].get('money_destroyed', 0) > 0:
                details.append("<br/><b>Money Destroyed:</b>")
                money_destroyed_value = costs[side]['money_destroyed']
                details.append(f"${money_destroyed_value:,.0f}")

            if costs[side]['improvements_lost'] > 0:
                details.append("<br/><b>Improvements:</b>")
                improvements_cost = costs[side]['improvements_lost']
                details.append(f"<b>Total: ${improvements_cost:,.0f}</b>")
                improvement_emojis = improvement_emoji_map()
                for name, count in sorted(costs[side]['improvements_destroyed'].items()):
                    cost_per_one = calculate_improvement_cost(name, resource_prices)
                    total_value = count * cost_per_one
                    emoji_name = improvement_emojis.get(name)
                    emoji_text = f" ({emoji_name})" if emoji_name else ""
                    details.append(f"{count} {name.replace('_', ' ').title()}{emoji_text} - ${total_value:,.0f}")
        elif category == "Loot":
            cash_gained = costs[side].get('loot_received', 0)
            resource_gained = costs[side].get('resource_loot', {})
            total_gained = cash_gained + sum(resource_gained.values())

            if total_gained > 0:
                details.append(f"<b>Gained: ${total_gained:,.0f}</b>")
                if cash_gained > 0:
                    details.append(f"  Cash: ${cash_gained:,.0f}")
                for resource, value in sorted(resource_gained.items(), key=lambda item: item[1], reverse=True):
                    price = resource_prices.get("sell", {}).get(resource, 1)
                    original_amount = value / price if price > 0 else 0
                    details.append(f"({resource.title()}) {original_amount:,.0f}")
        
        return "<br/>".join(details)

    async def _generate_war_report_file(self, wars_data: List[dict], resource_prices: dict, pov_ids: set, team1_type: str, team1: str, team2_type: Optional[str], team2: Optional[str], team1_id_set: set, team2_id_set: Optional[set] = None) -> Optional[discord.File]:
        """Generate a PDF file with a detailed list of wars and their costs."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, rightMargin=inch/4, leftMargin=inch/4, topMargin=inch/2, bottomMargin=inch/2)
        
        styles = getSampleStyleSheet()
        title_style = styles['h1']
        title_style.alignment = TA_CENTER
        h2_style = styles['h2']
        body_style = styles['BodyText']
        
        story = [Paragraph("War Report", title_style), Spacer(1, 0.2*inch)]

        # Overall Summary
        overall_costs = await calculate_war_costs(wars_data, resource_prices, team1_id_set, team2_id_set)
        pov_name = team1 if pov_ids else "Team 1"
        opp_name = "Opponent" if pov_ids else "Team 2"
        
        summary_data = [
            [f'Overall Summary for {pov_name}', ''],
            [f'Your Total Net', f"${overall_costs['team1']['net']:,.0f}"],
            [f'{opp_name} Total Net', f"${overall_costs['team2']['net']:,.0f}"]
        ]
        summary_table = Table(summary_data, colWidths=[doc.width/2.0]*2)
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.grey),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0,0), (-1,0), 12),
            ('BACKGROUND', (0,1), (-1,-1), colors.beige),
            ('GRID', (0,0), (-1,-1), 1, colors.black)
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 0.2*inch))

        # Detailed war breakdowns
        for war in wars_data:
            story.append(Paragraph(f"War ID: {war.get('id')}", h2_style))
            
            # Basic War Info
            pov_name_single, opponent_name_single = self._get_war_participants(war, team1_type, team1, team2_type, team2, pov_ids)
            actual_attacker, actual_defender = self._get_war_participants(war, team1_type, team1, team2_type, team2, pov_ids=None)
            winner_id = war.get('winner_id')
            winner_name = "Ongoing"
            if winner_id:
                if str(winner_id) == str(war.get('att_id')) or str(winner_id) == str(war.get('att_alliance_id')):
                    winner_name = actual_attacker
                elif str(winner_id) == str(war.get('def_id')) or str(winner_id) == str(war.get('def_alliance_id')):
                    winner_name = actual_defender
                else: winner_name = f"ID: {winner_id}"

            war_info_data = [
                [Paragraph(f"<b>Declared:</b> {actual_attacker} on {actual_defender}", body_style)],
                [Paragraph(f"<b>Reason:</b> {war.get('reason', 'N/A')}", body_style)],
                [Paragraph(f"<b>Winner:</b> {winner_name}", body_style)],
            ]
            war_info_table = Table(war_info_data, colWidths=[doc.width])
            war_info_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
            story.append(war_info_table)
            story.append(Spacer(1, 0.1*inch))

            # Detailed Costs for this war
            single_war_costs = await calculate_single_war_costs(war, resource_prices, team1_id_set, team2_id_set)
            
            cost_data = [[pov_name_single, opponent_name_single]]
            
            # Units
            att_units = self._get_category_details_for_pdf("team1", "Military", single_war_costs, resource_prices)
            def_units = self._get_category_details_for_pdf("team2", "Military", single_war_costs, resource_prices)
            cost_data.append([Paragraph(att_units, body_style), Paragraph(def_units, body_style)])
            
            # Destruction
            att_dest = self._get_category_details_for_pdf("team1", "Destruction", single_war_costs, resource_prices)
            def_dest = self._get_category_details_for_pdf("team2", "Destruction", single_war_costs, resource_prices)
            cost_data.append([Paragraph(att_dest, body_style), Paragraph(def_dest, body_style)])
            
            # Loot
            att_loot = self._get_category_details_for_pdf("team1", "Loot", single_war_costs, resource_prices)
            def_loot = self._get_category_details_for_pdf("team2", "Loot", single_war_costs, resource_prices)
            cost_data.append([Paragraph(att_loot, body_style), Paragraph(def_loot, body_style)])

            # Net
            att_gross = f"<b>Gross: ${single_war_costs['team1']['gross']:,.0f}</b>"
            def_gross = f"<b>Gross: ${single_war_costs['team2']['gross']:,.0f}</b>"
            att_net = f"<b>Net: ${single_war_costs['team1']['net']:,.0f}</b>"
            def_net = f"<b>Net: ${single_war_costs['team2']['net']:,.0f}</b>"
            cost_data.append([Paragraph(f"{att_gross}<br/>{att_net}", body_style), Paragraph(f"{def_gross}<br/>{def_net}", body_style)])

            cost_table = Table(cost_data, colWidths=[doc.width/2.0 - 5]*2, spaceAfter=20)
            cost_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.lightblue),
                ('TEXTCOLOR', (0,0), (-1,0), colors.black),
                ('ALIGN', (0,0), (-1,0), 'CENTER'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('GRID', (0,0), (-1,-1), 1, colors.black),
                ('VALIGN', (0,1), (-1,-1), 'TOP'),
            ]))
            story.append(cost_table)
            story.append(PageBreak())

        doc.build(story)
        buffer.seek(0)
        return discord.File(buffer, filename=f"war_report_{uuid.uuid4()}.pdf")

    def draw_rounded_rectangle(self, draw, xy, radius, fill=None, outline=None):
        x1, y1, x2, y2 = xy
        draw.rectangle(
            (x1 + radius, y1, x2 - radius, y2),
            fill=fill,
            outline=outline
        )
        draw.rectangle(
            (x1, y1 + radius, x2, y2 - radius),
            fill=fill,
            outline=outline
        )
        draw.pieslice(
            (x1, y1, x1 + radius * 2, y1 + radius * 2),
            180, 270, fill=fill, outline=outline
        )
        draw.pieslice(
            (x2 - radius * 2, y1, x2, y1 + radius * 2),
            270, 360, fill=fill, outline=outline
        )
        draw.pieslice(
            (x1, y2 - radius * 2, x1 + radius * 2, y2),
            90, 180, fill=fill, outline=outline
        )
        draw.pieslice(
            (x2 - radius * 2, y2 - radius * 2, x2, y2),
            0, 90, fill=fill, outline=outline
        )

    async def _generate_war_cost_graph(self, costs: dict, resource_prices: dict) -> io.BytesIO:
        """Generate pie charts for war costs with rich labels."""
        try:
            # --- Data Preparation ---
            cost_categories = {
                "Units": "#3498db", "Consumption": "#2ecc71", "Infrastructure": "#f1c40f",
                "Improvements": "#e67e22", "Loot Lost": "#9b59b6", "Money Destroyed": "#E74C3C"
            }

            team1_gross_costs = {
                "Units": sum(data['cost'] for data in costs['team1']['units'].values()),
                "Consumption": (costs['team1']['consumption']['munitions'] * resource_prices['buy'].get("munitions", 0) +
                                costs['team1']['consumption']['gasoline'] * resource_prices['buy'].get("gasoline", 0)),
                "Infrastructure": costs['team1']['infra_lost_value'],
                "Improvements": costs['team1']['improvements_lost'],
                "Loot Lost": costs['team1']['loot_lost'] + sum(costs['team1']['resource_loot_lost'].values()),
                "Money Destroyed": costs['team1'].get('money_destroyed', 0)
            }

            team2_gross_costs = {
                "Units": sum(data['cost'] for data in costs['team2']['units'].values()),
                "Consumption": (costs['team2']['consumption']['munitions'] * resource_prices['buy'].get("munitions", 0) +
                                costs['team2']['consumption']['gasoline'] * resource_prices['buy'].get("gasoline", 0)),
                "Infrastructure": costs['team2']['infra_lost_value'],
                "Improvements": costs['team2']['improvements_lost'],
                "Loot Lost": costs['team2']['loot_lost'] + sum(costs['team2']['resource_loot_lost'].values()),
                "Money Destroyed": costs['team2'].get('money_destroyed', 0)
            }

            team1_gross_costs = {k: v for k, v in team1_gross_costs.items() if v > 0}
            team2_gross_costs = {k: v for k, v in team2_gross_costs.items() if v > 0}

            # --- Image Setup ---
            width, height = 1200, 700
            img = Image.new('RGBA', (width, height), (255, 255, 255, 0))  # Transparent background
            draw = ImageDraw.Draw(img)
            try:
                title_font = ImageFont.truetype("arialbd.ttf", 20)
                label_font = ImageFont.truetype("arial.ttf", 16)
                small_label_font = ImageFont.truetype("arial.ttf", 14)
            except IOError:
                title_font, label_font, small_label_font = [ImageFont.load_default()] * 3

            # --- Helper Function for Drawing Pie ---
            def draw_pie(pie_box, data, title, draw_obj, is_attacker=True):
                total_cost = sum(data.values())
                
                if not data:
                    draw_obj.ellipse(pie_box, fill='#dcdcdc', outline='#b0b0b0')
                    draw_obj.text((pie_box[0] + (pie_box[2]-pie_box[0])/2, pie_box[1] + (pie_box[3]-pie_box[1])/2), "No Costs", fill='black', font=label_font, anchor="mm")
                    return

                start_angle = -90
                for category, value in data.items():
                    angle = (value / total_cost) * 360 if total_cost > 0 else 0
                    end_angle = start_angle + angle

                    mid_angle_rad = math.radians((start_angle + end_angle) / 2)
                    cx, cy = (pie_box[0] + pie_box[2]) / 2, (pie_box[1] + pie_box[3]) / 2

                    # Explode small slices
                    explode_dist = 10 if angle < 15 else 0
                    offset_x = int(explode_dist * math.cos(mid_angle_rad))
                    offset_y = int(explode_dist * math.sin(mid_angle_rad))
                    exploded_box = [pie_box[0] + offset_x, pie_box[1] + offset_y, pie_box[2] + offset_x, pie_box[3] + offset_y]
                    draw_obj.pieslice(exploded_box, start_angle, end_angle, fill=cost_categories[category], outline='white', width=2)

                    start_angle = end_angle

            # --- Draw Charts ---
            draw_pie((50, 100, 450, 500), team1_gross_costs, "Team 1 Gross Costs", draw, is_attacker=True)
            draw_pie((750, 100, 1150, 500), team2_gross_costs, "Team 2 Gross Costs", draw, is_attacker=False)

            # --- Draw Tighter, Rounded Legend ---
            legend_padding = 20
            legend_radius = 15
            content_width = 1050  # Estimated content width
            legend_height = 120  # Estimated height
            
            # Center the legend area
            legend_x0 = (width - content_width) / 2
            legend_y0 = 530
            legend_x1 = legend_x0 + content_width
            legend_y1 = legend_y0 + legend_height
            legend_area = (legend_x0, legend_y0, legend_x1, legend_y1)

            # Draw rounded rectangle
            self.draw_rounded_rectangle(draw, legend_area, fill="#2c3e50", radius=legend_radius)

            # --- Attacker and Defender Cost/Net ---
            team1_total_cost = sum(team1_gross_costs.values())
            team2_total_cost = sum(team2_gross_costs.values())
            team1_net_cost = costs['team1']['net']
            team2_net_cost = costs['team2']['net']

            team1_cost_text = f"Team 1 Cost: ${team1_total_cost:,.0f}"
            team1_net_text = f"Team 1 Net: ${team1_net_cost:,.0f}"
            team2_cost_text = f"Team 2 Cost: ${team2_total_cost:,.0f}"
            team2_net_text = f"Team 2 Net: ${team2_net_cost:,.0f}"

            # Position text within the rounded rectangle
            text_y_start = legend_y0 + legend_padding
            text_x_padding = 40
            
            draw.text((legend_x0 + text_x_padding, text_y_start), team1_cost_text, font=label_font, fill="#ecf0f1")
            draw.text((legend_x0 + text_x_padding, text_y_start + 30), team1_net_text, font=label_font, fill="#ecf0f1")
            
            def_text_x = legend_x1 - text_x_padding - draw.textlength(team2_cost_text, font=label_font)
            draw.text((def_text_x, text_y_start), team2_cost_text, font=label_font, fill="#ecf0f1")
            def_net_text_x = legend_x1 - text_x_padding - draw.textlength(team2_net_text, font=label_font)
            draw.text((def_net_text_x, text_y_start + 30), team2_net_text, font=label_font, fill="#ecf0f1")

            # --- Horizontal Color Legend (Centered) ---
            legend_y = legend_y0 + 80
            box_size = 20
            
            # Calculate total width of the color legend to center it
            total_legend_width = 0
            legend_items = list(cost_categories.items())
            item_spacing = 30
            for category, color in legend_items:
                total_legend_width += box_size + 10 + draw.textlength(category, font=label_font) + item_spacing

            legend_x_start = legend_x0 + (content_width - total_legend_width) / 2 + 15

            # Draw the centered color legend
            current_x = legend_x_start
            for category, color in legend_items:
                # Draw color box
                draw.rectangle([current_x, legend_y, current_x + box_size, legend_y + box_size], fill=color, outline="#ecf0f1", width=1)
                
                # Draw text
                text_x = current_x + box_size + 10
                draw.text((text_x, legend_y), category, fill="#ecf0f1", font=label_font)
                
                # Move to the next item
                current_x = text_x + draw.textlength(category, font=label_font) + item_spacing

            # --- Save to Buffer ---
            img_buffer = io.BytesIO()
            img.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            return img_buffer


        except Exception as e:
            logging.error(f"Error generating war cost graph: {e}", exc_info=True)
            return None

class WarCostView(discord.ui.View):
    """A view for paginating war cost analysis."""
    
    def __init__(self, embeds: dict, graph_file: Optional[discord.File] = None, war_report_file: Optional[discord.File] = None):
        super().__init__(timeout=300)
        self.embeds = embeds
        self.current_page_name = 'summary'
        self.message = None
        
        # Cache the image data instead of the Discord file
        self._graph_image_data = None
        if graph_file and hasattr(graph_file, 'fp') and hasattr(graph_file.fp, 'getvalue'):
            # Store the image data for later recreation
            self._graph_image_data = graph_file.fp.getvalue()
        
        # Cache the war report data
        self._war_report_data = None
        if war_report_file and hasattr(war_report_file, 'fp') and hasattr(war_report_file.fp, 'getvalue'):
            # Store the PDF data for later recreation
            self._war_report_data = war_report_file.fp.getvalue()

        # If there is no war report file, remove the breakdown button
        if not self._war_report_data:
            self.remove_item(self.breakdown_button)

        self.update_buttons()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            await self.message.edit(view=self)
    
    def update_buttons(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                # Button labels are title-cased, so we match
                item.disabled = (item.label.lower() == self.current_page_name)

    async def show_page(self, interaction: discord.Interaction, page_name: str):
        if self.current_page_name != page_name:
            self.current_page_name = page_name
            self.update_buttons()
            
            attachments = []
            embed = self.embeds[page_name]
            
            if page_name == 'summary':
                if self._graph_image_data:
                    # Recreate the Discord file from cached image data
                    import io
                    graph_buffer = io.BytesIO(self._graph_image_data)
                    graph_file = discord.File(graph_buffer, filename="war_cost_graph.png")
                    attachments.append(graph_file)

            await interaction.response.edit_message(embed=embed, view=self, attachments=attachments)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Summary", style=discord.ButtonStyle.secondary, emoji=get_animated_partial("bars"))
    async def summary_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show_page(interaction, 'summary')

    @discord.ui.button(label="Military", style=discord.ButtonStyle.primary, emoji=get_animated_partial("kill"))
    async def military_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show_page(interaction, 'military')

    @discord.ui.button(label="Destruction", style=discord.ButtonStyle.danger, emoji=get_animated_partial("bombq"))
    async def destruction_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show_page(interaction, 'destruction')

    @discord.ui.button(label="Loot", style=discord.ButtonStyle.success, emoji=get_animated_partial("Mimic"))
    async def loot_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show_page(interaction, 'loot')

    @discord.ui.button(label="Breakdown PDF", style=discord.ButtonStyle.secondary, emoji=get_animated_partial("pdf"))
    async def breakdown_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._war_report_data:
            # Recreate the Discord file from cached PDF data
            import io
            war_report_buffer = io.BytesIO(self._war_report_data)
            war_report_file = discord.File(war_report_buffer, filename=f"war_report_{uuid.uuid4()}.pdf")
            await interaction.response.send_message(file=war_report_file, ephemeral=True)
        else:
            await interaction.response.send_message("No breakdown available.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Wars(bot))