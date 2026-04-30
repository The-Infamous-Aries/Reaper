import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import logging
import re
from typing import Optional, Dict, Any, List

from ..Util.query import V3GraphQuery
from ..Util.war_brain import WarBrain, WarSimulation
from ..Util.war_calc import UNIT_COSTS
from Systems.Functions.emoji import mention, SOLDIER_EMOJI, TANK_EMOJI, JET_EMOJI, SHIP_EMOJI, MISSILE_EMOJI, BOMB_EMOJI, resource_emoji
from Systems.PnW.Other.loot import Loot

class SpyOpModal(discord.ui.Modal, title='Spy Operation Report'):
    report = discord.ui.TextInput(
        label='Paste your spy report here',
        style=discord.TextStyle.paragraph,
        placeholder='Your spies discovered that USER has the following resources available for looting: ...',
        required=True
    )

    def __init__(self, cog: 'WarSimCog', attacker_id: str, defender_id: str, war_type: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.attacker_id = attacker_id
        self.defender_id = defender_id
        self.war_type = war_type

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        
        try:
            your_nation_data, target_nation_data, trade_prices_data = await asyncio.gather(
                self.cog._get_nation(self.attacker_id),
                self.cog._get_nation(self.defender_id),
                self.cog.api.get_trade_resource_values()
            )
            self.cog.logger.info(f"Full API response for attacker \"{self.attacker_id}\": {your_nation_data}")

            if not your_nation_data or not target_nation_data:
                await interaction.followup.send("Could not find one or both nations. Please check the names/IDs.", ephemeral=True)
                return

            market_prices = {price['resource'].lower(): float(price['best_sell_offer']['price']) 
                             for price in trade_prices_data if price.get('best_sell_offer')}

            your_nation = self.cog._structure_nation_data(your_nation_data)
            target_nation = self.cog._structure_nation_data(target_nation_data)
            
            spy_data = self.cog._extract_intelligence_data(self.report.value)
            if not spy_data:
                await interaction.followup.send("Could not parse spy report. Please make sure it's in the correct format.", ephemeral=True)
                return

            await self.cog._run_and_present_simulation(interaction, your_nation, target_nation, market_prices, self.war_type, spy_data)

        except Exception as e:
            self.cog.logger.error(f"Error in modal submission: {e}", exc_info=True)
            await interaction.followup.send("An unexpected error occurred while processing your request.", ephemeral=True)

class WarSimPaginator(discord.ui.View):
    def __init__(self, embeds: List[discord.Embed]):
        super().__init__(timeout=300)
        self.embeds = embeds
        self.current_page = 0
        self._update_buttons()

    def _update_buttons(self):
        self.children[0].disabled = self.current_page == 0
        self.children[1].disabled = self.current_page >= len(self.embeds) - 1

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.grey)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.grey)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

class WarSimCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.war_brain = WarBrain()
        self.api = V3GraphQuery()
        self.logger = logging.getLogger(__name__)
        # Get the loot cog for intelligence data extraction
        self.loot_cog = None

    async def cog_load(self):
        """Get reference to the loot cog (loaded by PnW system hopper)."""
        # Don't get the reference here - get it on-demand when needed
        # This allows the Loot cog to be loaded later and still be usable
        self.loot_cog = None

    async def _get_nation(self, identifier: str) -> Optional[dict]:
        if not identifier: return None
        if identifier.isdigit(): return await self.api.get_nation_by_id(identifier)
        
        nation = await self.api.get_nation_by_name(identifier)
        if nation: return nation
        return await self.api.get_nation_by_leader(identifier)

    @app_commands.command(name="war", description="Simulates a full war between two nations.")
    @app_commands.describe(
        attacker="Your nation name, leader, or ID",
        defender="The target nation name, leader, or ID",
        war_type="The type of war to simulate",
        include_spy_op="Whether to include a spy report for more accurate loot calculation"
    )
    @app_commands.choices(war_type=[
        app_commands.Choice(name="Ordinary", value="ordinary"),
        app_commands.Choice(name="Attrition", value="attrition"),
        app_commands.Choice(name="Raid", value="raid"),
    ])
    async def war(self, interaction: discord.Interaction, attacker: str, defender: str, war_type: app_commands.Choice[str], include_spy_op: bool):
        if include_spy_op:
            modal = SpyOpModal(self, attacker, defender, war_type.value)
            await interaction.response.send_modal(modal)
            return

        await interaction.response.defer(thinking=True, ephemeral=False)

        try:
            your_nation_data, target_nation_data, trade_prices_data = await asyncio.gather(
                self._get_nation(attacker),
                self._get_nation(defender),
                self.api.get_trade_resource_values()
            )

            if not your_nation_data or not target_nation_data:
                await interaction.followup.send("Could not find one or both nations. Please check the names/IDs.", ephemeral=False)
                return

            market_prices = {price['resource'].lower(): float(price['best_sell_offer']['price']) 
                             for price in trade_prices_data if price.get('best_sell_offer')}

        except Exception as e:
            self.logger.error(f"Error in war command pre-flight: {e}", exc_info=True)
            await interaction.followup.send("An error occurred while fetching nation data. Please try again.", ephemeral=False)
            return
        
        your_nation = self._structure_nation_data(your_nation_data)
        target_nation = self._structure_nation_data(target_nation_data)

        await self._run_and_present_simulation(interaction, your_nation, target_nation, market_prices, war_type.value)

    def _extract_intelligence_data(self, content: str) -> Optional[Dict[str, float]]:
        """Extract intelligence data using the Loot cog's implementation."""
        # Get Loot cog reference on-demand if not already cached
        if self.loot_cog is None:
            self.loot_cog = self.bot.get_cog('Loot')
            if self.loot_cog:
                self.logger.info("Loot cog found and cached for intelligence extraction")
        
        if not self.loot_cog:
            self.logger.warning("Loot cog not available, falling back to basic extraction")
            return self._basic_extract_intelligence_data(content)
        
        try:
            # Use the Loot cog's extraction method
            return self.loot_cog._extract_intelligence_data(content)
        except Exception as e:
            self.logger.error(f"Error using Loot cog extraction: {e}, falling back to basic")
            return self._basic_extract_intelligence_data(content)
    
    def _basic_extract_intelligence_data(self, content: str) -> Optional[Dict[str, float]]:
        """Basic fallback implementation for intelligence data extraction."""
        try:
            intel_data = {}
            content_lower = content.lower()
            # Manually find and parse money
            money_match = re.search(r'has\s\$([0-9,]+(?:\.[0-9]{2})?)', content_lower)
            if money_match:
                intel_data['money'] = float(money_match.group(1).replace(',', ''))

            # Manually find and parse resources
            for res in ['food', 'coal', 'oil', 'uranium', 'lead', 'iron', 'bauxite', 'gasoline', 'munitions', 'steel', 'aluminum']:
                match = re.search(r'([\d,]+\.?\d*)\s+' + re.escape(res) + r'\b', content_lower)
                if match:
                    intel_data[res] = float(match.group(1).replace(',', ''))
            return intel_data if intel_data else None
        except Exception as e:
            self.logger.error(f"Error extracting intelligence data: {e}", exc_info=True)
            return None
    
    def _structure_nation_data(self, nation_data: dict) -> dict:
        if not nation_data: return {}
        cities_data = {city.get('name', 'Unknown'): city for city in nation_data.get('cities', [])}
        nation_data['cities'] = cities_data
        nation_data['infrastructure'] = sum(c.get('infrastructure', 0) for c in cities_data.values())
        return nation_data

    async def _run_and_present_simulation(self, interaction: discord.Interaction, attacker: dict, defender: dict, market_prices: dict, war_type: str, spy_data: Optional[dict] = None):
        try:
            simulation = self.war_brain.simulate_full_war(attacker, defender, market_prices, war_type, spy_data)
        except Exception as e:
            self.logger.error(f"Error during full war simulation: {e}", exc_info=True)
            await interaction.followup.send(f"An unexpected error occurred during simulation: {e}", ephemeral=False)
            return

        if simulation.winner == 'error':
            await interaction.followup.send("The simulation encountered an error and could not complete.", ephemeral=False)
            return

        summary_embed = self._create_summary_embed(simulation)
        turn_embeds = self._create_turn_embeds(simulation)
        all_embeds = [summary_embed] + turn_embeds

        view = WarSimPaginator(all_embeds)
        await interaction.followup.send(embed=all_embeds[0], view=view)

    def _get_unit_emoji(self, unit_type: str) -> str:
        """Get the emoji for a given unit type."""
        if unit_type == 'soldiers':
            return SOLDIER_EMOJI
        elif unit_type == 'tanks':
            return TANK_EMOJI
        elif unit_type == 'aircraft':
            return JET_EMOJI
        elif unit_type == 'ships':
            return SHIP_EMOJI
        elif unit_type == 'missiles':
            return MISSILE_EMOJI
        elif unit_type == 'nukes':
            return BOMB_EMOJI
        else:
            return mention(unit_type)

    def _create_summary_embed(self, sim: WarSimulation) -> discord.Embed:
        color = discord.Color.dark_red() if sim.winner == 'attacker' else discord.Color.dark_blue()
        if sim.winner == 'ongoing': color = discord.Color.gold()

        # Get nation names safely, handling both 'name' and 'nation_name' keys
        attacker_name = sim.attacker_nation.get('name') or sim.attacker_nation.get('nation_name', 'Unknown')
        defender_name = sim.defender_nation.get('name') or sim.defender_nation.get('nation_name', 'Unknown')

        embed = discord.Embed(
            title=f"War Summary: {attacker_name} vs. {defender_name}",
            description=f"**Winner: {sim.winner.title()} in {sim.total_turns} turns** ({sim.war_type.title()} War)",
            color=color
        )

        embed.add_field(name="Attacker Resistance", value=f"{sim.initial_attacker_resistance:.1f} → **{sim.final_attacker_resistance:.1f}**", inline=True)
        embed.add_field(name="Defender Resistance", value=f"{sim.initial_defender_resistance:.1f} → **{sim.final_defender_resistance:.1f}**", inline=True)
        
        if sim.total_infra_destroyed > 0:
            total_infra_cost = sum(turn.infra_damage_cost for turn in sim.turn_results)
            embed.add_field(name="Total Infra Destroyed", value=f"{sim.total_infra_destroyed:,.0f} (${total_infra_cost:,.0f})", inline=True)

        if sim.winner == 'attacker':
            if sim.total_consumption:
                cons_str_parts = []
                for k, v in sim.total_consumption.items():
                    if v > 0:
                        emoji = resource_emoji(k) or ''
                        cons_str_parts.append(f"{emoji} {int(v):,} {k.title()}")
                if cons_str_parts:
                    embed.add_field(name="Resources Lost", value='\n'.join(cons_str_parts), inline=True)

            if sim.total_loot:
                loot_str_parts = []
                for k, v in sim.total_loot.items():
                    if v > 0:
                        name = k.title()
                        emoji = resource_emoji(k)
                        if k == 'money':
                            name = 'Cash'
                            emoji = resource_emoji('credit')
                        emoji = emoji or ''
                        loot_str_parts.append(f"{emoji} {int(v):,} {name}")
                if loot_str_parts:
                    embed.add_field(name="Resources Looted", value='\n'.join(loot_str_parts), inline=True)
        
        # Attacker Casualties
        attacker_cas_str = "\n".join([f"{self._get_unit_emoji(k)} {int(v):,} {k.title()}" for k, v in sim.total_attacker_casualties.items() if v > 0])
        attacker_cas_cost = sum(v * UNIT_COSTS.get(k, {}).get('cash', 0) for k, v in sim.total_attacker_casualties.items())
        embed.add_field(name="Attacker Casualties", value=f"{attacker_cas_str}\n**Total Cost: ${attacker_cas_cost:,.0f}**" if attacker_cas_str else "None", inline=True)

        # Defender Casualties
        defender_cas_str = "\n".join([f"{self._get_unit_emoji(k)} {int(v):,} {k.title()}" for k, v in sim.total_defender_casualties.items() if v > 0])
        defender_cas_cost = sum(v * UNIT_COSTS.get(k, {}).get('cash', 0) for k, v in sim.total_defender_casualties.items())
        embed.add_field(name="Defender Casualties", value=f"{defender_cas_str}\n**Total Cost: ${defender_cas_cost:,.0f}**" if defender_cas_str else "None", inline=True)

        embed.set_footer(text="Page 1 of {} | War Summary".format(len(sim.turn_results) + 1))
        return embed

    def _create_turn_embeds(self, sim: WarSimulation) -> List[discord.Embed]:
        embeds = []
        for i, turn in enumerate(sim.turn_results):
            # Get nation names safely, handling both 'name' and 'nation_name' keys
            attacker_name = sim.attacker_nation.get('name') or sim.attacker_nation.get('nation_name', 'Unknown')
            defender_name = sim.defender_nation.get('name') or sim.defender_nation.get('nation_name', 'Unknown')
            actor_name = attacker_name if turn.attacker_side == 'attacker' else defender_name
            embed = discord.Embed(title=f"Turn {turn.turn}: {actor_name} attacks!", color=discord.Color.dark_grey())
            
            embed.add_field(name="Attack Type", value=turn.attack_type.title(), inline=True)
            embed.add_field(name="Attacker Resistance", value=f"`{turn.attacker_resistance:.2f}`", inline=True)
            embed.add_field(name="Defender Resistance", value=f"`{turn.defender_resistance:.2f}`", inline=True)
            embed.add_field(name="Attacker MAPs", value=f"`{turn.attacker_maps}`", inline=True)
            embed.add_field(name="Defender MAPs", value=f"`{turn.defender_maps}`", inline=True)

            if turn.infra_damage > 0:
                embed.add_field(name="Infra Damage", value=f"{turn.infra_damage:,.0f} (${turn.infra_damage_cost:,.0f})", inline=True)

            if turn.consumption:
                cons_str = "\n".join([f"{resource_emoji(k)} {int(v):,} {k.title()}" for k, v in turn.consumption.items() if v > 0])
                if cons_str: embed.add_field(name="Consumption", value=cons_str, inline=True)
            
            if turn.attacker_casualties:
                cas_str = "\n".join([f"{self._get_unit_emoji(k)} {int(v):,} {k.title()}" for k, v in turn.attacker_casualties.items() if v > 0])
                if cas_str: embed.add_field(name="Attacker Casualties", value=cas_str, inline=True)

            if turn.defender_casualties:
                cas_str = "\n".join([f"{self._get_unit_emoji(k)} {int(v):,} {k.title()}" for k, v in turn.defender_casualties.items() if v > 0])
                if cas_str: embed.add_field(name="Defender Casualties", value=cas_str, inline=True)

            if turn.purchases and turn.purchases.get('units'):
                purchase_str = "\n".join([f"{self._get_unit_emoji(k)} {int(v):,}" for k, v in turn.purchases['units'].items() if v > 0])
                cost_parts = []
                for k, v in turn.purchases['cost'].items():
                    if v > 0:
                        emoji = resource_emoji('credit') if k == 'money' else resource_emoji(k)
                        emoji = emoji or ''
                        cost_parts.append(f"{emoji} {int(v):,}")
                cost_str = "\n".join(cost_parts)
                embed.add_field(name="Purchases", value=f"**Units**:\n{purchase_str}\n**Cost**:\n{cost_str}", inline=True)

            status_text = (
                f"Attacker: GC: {mention(turn.attacker_ground_control)}, AS: {mention(turn.attacker_air_superiority)}, Blockade: {mention(turn.attacker_blockade)}\n"
                f"Defender: GC: {mention(turn.defender_ground_control)}, AS: {mention(turn.defender_air_superiority)}, Blockade: {mention(turn.defender_blockade)}"
            )
            embed.add_field(name="War Statuses", value=status_text, inline=False)
            embed.set_footer(text=f"Page {i + 2} of {len(sim.turn_results) + 1} | Turn {turn.turn}")
            embeds.append(embed)
        return embeds

async def setup(bot):
    await bot.add_cog(WarSimCog(bot))
