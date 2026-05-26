import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import logging
import re
import sqlite3
from typing import Optional, Dict, Any, List

from ..Util.query import V3GraphQuery
from ..Util.war_brain import WarBrain, WarSimulation
from ..Util.war_calc import UNIT_COSTS
from Systems.Functions.emoji import mention, SOLDIER_EMOJI, TANK_EMOJI, JET_EMOJI, SHIP_EMOJI, MISSILE_EMOJI, BOMB_EMOJI, resource_emoji
from Systems.PnW.Other.loot import Loot

# Database path
DB_PATH = "Databases/PnW/GlobalNations.db"

def get_nation_from_db(identifier: str) -> Optional[Dict[str, Any]]:
    """Fetch nation data from GlobalNations.db by name, leader, or ID."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Try by ID first
        if identifier.isdigit():
            cursor.execute("""
                SELECT id, nation_name, leader_name, score, soldiers, tanks, aircraft, ships, missiles, nukes,
                       money, food, coal, oil, uranium, lead, iron, bauxite, gasoline, munitions, steel, aluminum
                FROM nations WHERE id = ?
            """, (identifier,))
        else:
            # Try by name or leader
            cursor.execute("""
                SELECT id, nation_name, leader_name, score, soldiers, tanks, aircraft, ships, missiles, nukes,
                       money, food, coal, oil, uranium, lead, iron, bauxite, gasoline, munitions, steel, aluminum
                FROM nations WHERE nation_name LIKE ? OR leader_name LIKE ?
            """, (f"%{identifier}%", f"%{identifier}%"))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        # Fetch cities for this nation
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name, infrastructure, land
            FROM cities WHERE nation_id = ?
        """, (row[0],))
        cities_rows = cursor.fetchall()
        conn.close()
        
        # Structure the nation data
        cities = {}
        for city_row in cities_rows:
            cities[city_row[0]] = {
                'infrastructure': city_row[1],
                'land': city_row[2],
                'population': 0  # Not available in DB
            }
        
        return {
            'nation_id': row[0],
            'name': row[1],
            'leader_name': row[2],
            'score': row[3],
            'soldiers': row[4],
            'tanks': row[5],
            'aircraft': row[6],
            'ships': row[7],
            'missiles': row[8],
            'nukes': row[9],
            'money': row[10],
            'food': row[11],
            'coal': row[12],
            'oil': row[13],
            'uranium': row[14],
            'lead': row[15],
            'iron': row[16],
            'bauxite': row[17],
            'gasoline': row[18],
            'munitions': row[19],
            'steel': row[20],
            'aluminum': row[21],
            'cities': cities,
            'infrastructure': sum(c['infrastructure'] for c in cities.values())
        }
    except Exception as e:
        logging.error(f"Error fetching nation from DB: {e}")
        return None

def get_all_nation_names() -> List[str]:
    """Get all nation names from GlobalNations.db for autocomplete."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT nation_name, leader_name FROM nations")
        rows = cursor.fetchall()
        conn.close()
        
        # Return both nation names and leader names
        names = []
        for row in rows:
            if row[0]:
                names.append(row[0])
            if row[1]:
                names.append(row[1])
        return names
    except Exception as e:
        logging.error(f"Error fetching nation names from DB: {e}")
        return []

async def nation_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    """Autocomplete for nation names from GlobalNations.db."""
    all_names = get_all_nation_names()
    filtered = [name for name in all_names if current.lower() in name.lower()]
    return [app_commands.Choice(name=name, value=name) for name in filtered[:25]]

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
        """Fetch nation data from GlobalNations.db."""
        if not identifier: return None
        return get_nation_from_db(identifier)

    @app_commands.command(name="war", description="Simulates a full war between two nations.")
    @app_commands.describe(
        attacker="Your nation name, leader, or ID",
        defender="The target nation name, leader, or ID",
        war_type="The type of war to simulate"
    )
    @app_commands.choices(war_type=[
        app_commands.Choice(name="Ordinary", value="ordinary"),
        app_commands.Choice(name="Attrition", value="attrition"),
        app_commands.Choice(name="Raid", value="raid"),
    ])
    @app_commands.autocomplete(attacker=nation_autocomplete, defender=nation_autocomplete)
    async def war(self, interaction: discord.Interaction, attacker: str, defender: str, war_type: app_commands.Choice[str]):
        await interaction.response.defer(thinking=True, ephemeral=False)

        try:
            your_nation_data, target_nation_data, trade_prices_data = await asyncio.gather(
                self._get_nation(attacker),
                self._get_nation(defender),
                self.api.get_trade_resource_values()
            )

            if not your_nation_data or not target_nation_data:
                await interaction.followup.send("Could not find one or both nations in the database. Please check the names/IDs.", ephemeral=False)
                return

            market_prices = {price['resource'].lower(): float(price['best_sell_offer']['price']) 
                             for price in trade_prices_data if price.get('best_sell_offer')}

        except Exception as e:
            self.logger.error(f"Error in war command pre-flight: {e}", exc_info=True)
            await interaction.followup.send("An error occurred while fetching nation data. Please try again.", ephemeral=False)
            return
        
        # Nation data from DB is already structured correctly
        await self._run_and_present_simulation(interaction, your_nation_data, target_nation_data, market_prices, war_type.value)

    async def _run_and_present_simulation(self, interaction: discord.Interaction, attacker: dict, defender: dict, market_prices: dict, war_type: str):
        try:
            simulation = self.war_brain.simulate_full_war(attacker, defender, market_prices, war_type)
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

        # Add total consumption to summary
        if sim.total_consumption:
            cons_str_parts = []
            for k, v in sim.total_consumption.items():
                if v > 0:
                    emoji = resource_emoji(k) or ''
                    cons_str_parts.append(f"{emoji} {v:.2f} {k.title()}")
            if cons_str_parts:
                embed.add_field(name="Total Consumption", value='\n'.join(cons_str_parts), inline=True)
        
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
        attacker_turns_active = []
        defender_turns_active = []
        
        for i, turn in enumerate(sim.turn_results):
            # Track which turns each side was active
            if turn.attacker_side == 'attacker' and turn.attack_type != 'pass':
                attacker_turns_active.append(turn.turn)
            elif turn.attacker_side == 'defender' and turn.attack_type != 'pass':
                defender_turns_active.append(turn.turn)
            
            # Get nation names safely, handling both 'name' and 'nation_name' keys
            attacker_name = sim.attacker_nation.get('name') or sim.attacker_nation.get('nation_name', 'Unknown')
            defender_name = sim.defender_nation.get('name') or sim.defender_nation.get('nation_name', 'Unknown')
            actor_name = attacker_name if turn.attacker_side == 'attacker' else defender_name
            
            embed = discord.Embed(title=f"Turn {turn.turn}: {actor_name} attacks!" if turn.attack_type != 'pass' else f"Turn {turn.turn}: {actor_name} does nothing", color=discord.Color.dark_grey())
            
            embed.add_field(name="Attack Type", value=turn.attack_type.title() if turn.attack_type != 'pass' else 'None', inline=True)
            embed.add_field(name="Attacker Resistance", value=f"`{turn.attacker_resistance:.2f}`", inline=True)
            embed.add_field(name="Defender Resistance", value=f"`{turn.defender_resistance:.2f}`", inline=True)
            embed.add_field(name="Attacker MAPs", value=f"`{turn.attacker_maps}`", inline=True)
            embed.add_field(name="Defender MAPs", value=f"`{turn.defender_maps}`", inline=True)

            if turn.infra_damage > 0:
                embed.add_field(name="Infra Damage", value=f"{turn.infra_damage:,.0f} (${turn.infra_damage_cost:,.0f})", inline=True)

            # Always show consumption, even if zero
            consumption_fields = []
            for resource in ['munitions', 'gasoline']:
                amount = turn.consumption.get(resource, 0)
                if amount > 0:
                    emoji = resource_emoji(resource) or ''
                    consumption_fields.append(f"{emoji} {amount:.2f} {resource.title()}")
            
            if consumption_fields:
                embed.add_field(name="Consumption Used", value='\n'.join(consumption_fields), inline=True)
            else:
                embed.add_field(name="Consumption Used", value="None", inline=True)
            
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
            
            # Add inactive turns information
            inactive_turns = []
            if turn.turn not in attacker_turns_active:
                inactive_turns.append(f"{attacker_name} was inactive")
            if turn.turn not in defender_turns_active:
                inactive_turns.append(f"{defender_name} was inactive")
            
            if inactive_turns:
                embed.add_field(name="Inactive Nations", value="\n".join(inactive_turns), inline=False)
            
            embed.set_footer(text=f"Page {i + 2} of {len(sim.turn_results) + 1} | Turn {turn.turn} of {sim.total_turns}")
            embeds.append(embed)
            
        return embeds

async def setup(bot):
    await bot.add_cog(WarSimCog(bot))
