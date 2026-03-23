
import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional
import asyncio
from datetime import datetime, timedelta
import math

from Systems.PnW.Util.war_calc import UNIT_COSTS, get_resource_prices
from Systems.Functions.emoji import get_partial, get_animated_partial, resource_emoji, military_codes, mention
from Systems.PnW.pnwhopper import emoji_mod


class ResourcePriceCache:
    """Cache resource prices for 30 minutes to reduce API calls."""
    
    def __init__(self):
        self.cache = {}
        self.cache_duration = 1800  # 30 minutes in seconds
        self.last_fetch = None
        self.prices = {"sell": {}, "buy": {}}
    
    async def get_cached_prices(self) -> dict:
        """Get prices from cache or fetch new ones if expired."""
        if self._is_cache_valid():
            return self.prices
        
        # Fetch fresh prices
        try:
            fresh_prices = await get_resource_prices()
            if not fresh_prices or not isinstance(fresh_prices, dict):
                logging.warning("Invalid price data received, using cached prices")
                return self.prices
            
            # Validate price data structure
            if 'sell' not in fresh_prices:
                logging.warning("Missing 'sell' key in price data, using cached prices")
                return self.prices
                
            self.prices = fresh_prices
            self.last_fetch = datetime.now()
            return fresh_prices
            
        except asyncio.TimeoutError:
            logging.error("Timeout while fetching resource prices")
            return self.prices
        except ConnectionError as e:
            logging.error(f"Connection error while fetching resource prices: {e}")
            return self.prices
        except Exception as e:
            logging.error(f"Unexpected error fetching resource prices: {e}")
            return self.prices  # Return cached even if expired
    
    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid (30 minutes)."""
        if not self.last_fetch:
            return False
        return (datetime.now() - self.last_fetch).seconds < self.cache_duration
    
    def get_cache_age(self) -> str:
        """Get human-readable cache age."""
        if not self.last_fetch:
            return "Unknown"
        
        age_seconds = (datetime.now() - self.last_fetch).seconds
        if age_seconds < 60:
            return f"{age_seconds}s"
        elif age_seconds < 3600:
            return f"{age_seconds // 60}m"
        else:
            return f"{age_seconds // 3600}h"

import re

def _get_easter_egg(units):
    """Return a string for an easter egg if the units match a specific combination."""
    
    num_unit_types = sum(1 for v in units.values() if v > 0)

    # ONLY 6 missiles
    if num_unit_types == 1 and units.get("missiles") == 6:
        missile_emoji = str(get_partial('missile') or '🚀')
        return f"{missile_emoji * 6} Good Luck! .. If you miss twice {missile_emoji * 2} your 🤬"

    # ONLY 4 nukes
    if num_unit_types == 1 and units.get("nukes") == 4:
        bomb_emoji = str(get_partial('bomb') or '💣')
        boom_emoji = str(get_animated_partial('boom') or '💥')
        return f"🏠🏚️👻{bomb_emoji}{boom_emoji}{bomb_emoji}👻🏚️🏠"

    # ONLY 1 ship and ANY amount of Soldiers
    if num_unit_types == 2 and units.get("ships") == 1 and units.get("soldiers", 0) > 0:
        scallywag_emoji = get_partial('scallywag') or ''
        mimic_emoji = get_animated_partial('mimic') or ''
        parrot_emoji = '🦜'
        return f"🏴‍☠️{scallywag_emoji}{parrot_emoji} Take it all, Give **NOTHING** back! {mimic_emoji}"

    # EXACTLY of 15,000 soldiers, 1,250 tanks, 75 aircraft and 15 ships
    soldiers = units.get("soldiers", 0)
    tanks = units.get("tanks", 0)
    aircraft = units.get("aircraft", 0)
    ships = units.get("ships", 0)
    
    is_max_mmr = (
        soldiers > 0 and tanks > 0 and aircraft > 0 and ships > 0 and
        num_unit_types == 4
    )

    if is_max_mmr:
        base_soldiers = 15000
        base_tanks = 1250
        base_aircraft = 75
        base_ships = 15

        if (soldiers % base_soldiers == 0 and
            tanks % base_tanks == 0 and
            aircraft % base_aircraft == 0 and
            ships % base_ships == 0):

            ratio = soldiers / base_soldiers
            if (tanks / base_tanks == ratio and
                aircraft / base_aircraft == ratio and
                ships / base_ships == ratio):
                
                city_count = int(ratio)
                soldier_emoji = military_codes().get("soldiers", "🪖")
                tank_emoji = military_codes().get("tanks", "⚔️")
                jet_emoji = military_codes().get("aircraft", "✈️")
                ship_emoji = military_codes().get("ships", "🚢")
                
                return f"Let me guess; **c{city_count}** running a **5/5/5/3** {soldier_emoji}{tank_emoji}{jet_emoji}{ship_emoji}"

    # ONLY 1 missile or nuke
    if num_unit_types == 1:
        wavecash_emoji = get_animated_partial('wavecash') or '💸'
        if units.get("missiles") == 1:
            missile_emoji = get_partial('missile') or '🚀'
            return f"{wavecash_emoji} Looking up the cost to 1 Missile {missile_emoji}? .. Live a little, let that thing fly!"
        if units.get("nukes") == 1:
            bomb_emoji = get_partial('bomb') or '💣'
            return f"{wavecash_emoji} Looking up the cost to 1 Nuke {bomb_emoji}? .. Live a little, let that thing fly!"

    return None

class UnitInputModal(discord.ui.Modal):
    """Modal for inputting all unit quantities in a single field."""

    def __init__(self, current_units, parent_view):
        super().__init__(title="Set All Unit Quantities")
        self.parent_view = parent_view
        self.current_units = current_units

        default_value = ", ".join([f"{unit_type}:{amount}" for unit_type, amount in current_units.items() if amount > 0])
        
        self.units_input = discord.ui.TextInput(
            label="Enter Units Below:",
            placeholder=f"soldiers:10, tanks=15, aircraft-20, ships;25, missiles~30, nukes`35",
            style=discord.TextStyle.paragraph,
            default=default_value,
            required=False,
        )
        self.add_item(self.units_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Parse the single input field and update all units."""
        try:
            new_units = self.current_units.copy()
            
            for unit in new_units:
                new_units[unit] = 0

            input_str = self.units_input.value.strip()
            
            if not input_str:
                self.parent_view.units = new_units
                await self.parent_view.update_display(interaction)
                return

            unit_pattern = re.compile(r"(\w+)\s*[-=:;~`\"]\s*([\d,]+[km]?)", re.IGNORECASE)
            
            matches = unit_pattern.findall(input_str)

            unit_map = {
                "soldier": "soldiers", "soldiers": "soldiers",
                "tank": "tanks", "tanks": "tanks",
                "plane": "aircraft", "planes": "aircraft", "aircraft": "aircraft",
                "ship": "ships", "ships": "ships",
                "missile": "missiles", "missiles": "missiles",
                "nuke": "nukes", "nukes": "nukes"
            }

            for unit_type_str, amount_str in matches:
                unit_type = unit_map.get(unit_type_str.lower().rstrip('s'))
                if not unit_type:
                    continue

                amount_str = amount_str.lower()
                multiplier = 1
                if 'k' in amount_str:
                    multiplier = 1000
                    amount_str = amount_str.replace('k', '')
                elif 'm' in amount_str:
                    multiplier = 1000000
                    amount_str = amount_str.replace('m', '')
                
                amount_str = amount_str.replace(',', '')

                try:
                    value = int(float(amount_str) * multiplier)
                    new_units[unit_type] = max(0, value)
                except (ValueError, TypeError):
                    continue
            
            self.parent_view.units = new_units
            await self.parent_view.update_display(interaction)

        except Exception as e:
            logging.error(f"Error parsing unit input: {e}")
            await interaction.followup.send("❌ Failed to parse unit input. Please check the format and try again.", ephemeral=True)


class LiveUnitCalculatorView(discord.ui.View):
    """Interactive view for live unit cost calculations."""
    
    def __init__(self, initial_units=None, price_cache=None):
        super().__init__(timeout=1800)  # 30 minute timeout for live calculator
        self.units = initial_units or {"soldiers": 0, "tanks": 0, "aircraft": 0, "ships": 0, "missiles": 0, "nukes": 0}
        self.price_cache = price_cache or ResourcePriceCache()
        self.message = None
    
    async def create_initial_embed(self) -> discord.Embed:
        """Create the initial embed with current calculations."""
        try:
            return await self.create_embed()
        except Exception as e:
            logging.error(f"Error creating initial embed: {e}")
            # Return a basic error embed
            error_embed = discord.Embed(
                title="❌ Calculator Error",
                description="Failed to initialize calculator. Please try again.",
                color=discord.Color.red()
            )
            return error_embed
    
    async def create_embed(self) -> discord.Embed:
        """Create embed with current unit calculations."""
        try:
            # Get cached prices with error handling
            resource_prices = await self.price_cache.get_cached_prices()
            
            # Validate price data
            if not resource_prices or not isinstance(resource_prices, dict):
                logging.warning("Invalid resource prices data")
                resource_prices = {"sell": {}}
            
            # Ensure sell prices exist
            if 'sell' not in resource_prices:
                resource_prices['sell'] = {}
            
            # Calculate costs using existing logic
            unit_breakdown = []
            resource_totals = {}
            money_total = 0
            total_units = sum(self.units.values())
            unit_total_costs = {}
            
            # Get military emoji mappings with error handling
            try:
                military_emoji_map = military_codes()
                if not military_emoji_map:
                    military_emoji_map = {}  # Use empty dict if function fails
            except Exception as e:
                logging.error(f"Error getting military emoji mappings: {e}")
                military_emoji_map = {}
            
            units_config = [
                ("soldiers", self.units["soldiers"], military_emoji_map.get("soldiers", "🪖")),
                ("tanks", self.units["tanks"], military_emoji_map.get("tanks", "⚔️")),
                ("aircraft", self.units["aircraft"], military_emoji_map.get("aircraft", "✈️")),
                ("ships", self.units["ships"], military_emoji_map.get("ships", "🚢")),
                ("missiles", self.units["missiles"], military_emoji_map.get("missiles", "🚀")),
                ("nukes", self.units["nukes"], military_emoji_map.get("nukes", "☢️"))
            ]
            
            for unit_type, quantity, emoji in units_config:
                if quantity <= 0:
                    continue
                    
                # Validate unit costs data
                if unit_type not in UNIT_COSTS:
                    logging.warning(f"Missing unit costs for {unit_type}")
                    continue
                    
                unit_costs = UNIT_COSTS[unit_type]
                if not isinstance(unit_costs, dict):
                    logging.warning(f"Invalid unit costs data for {unit_type}")
                    continue
                
                unit_money_cost = unit_costs.get("cash", 0) * quantity
                money_total += unit_money_cost

                unit_resource_cost = 0
                # Calculate resource costs
                for resource, amount_per_unit in unit_costs.items():
                    if resource == "cash":
                        continue
                    
                    if not isinstance(amount_per_unit, (int, float)) or amount_per_unit <= 0:
                        continue
                        
                    total_resource_needed = amount_per_unit * quantity
                    if total_resource_needed > 0:
                        resource_price = resource_prices.get('sell', {}).get(resource, 0)
                        if not isinstance(resource_price, (int, float)) or resource_price < 0:
                            resource_price = 0
                            
                        resource_cost = total_resource_needed * resource_price
                        unit_resource_cost += resource_cost
                        
                        if resource not in resource_totals:
                            resource_totals[resource] = {"amount": 0, "cost": 0}
                        resource_totals[resource]["amount"] += total_resource_needed
                        resource_totals[resource]["cost"] += resource_cost

                unit_total_costs[unit_type] = unit_money_cost + unit_resource_cost
                
                # Add unit breakdown
                unit_breakdown.append(f"**{quantity:,}** *{unit_type.title()}* {emoji}\n* **${unit_money_cost:,.0f}**")
            
            # Calculate totals
            total_resource_cost = sum(r["cost"] for r in resource_totals.values())
            grand_total = money_total + total_resource_cost
            
            # Determine embed color
            embed_color = discord.Color.blue()  # Default color
            if unit_total_costs:
                most_expensive_unit = max(unit_total_costs, key=unit_total_costs.get)

                UNIT_COLORS = {
                    "soldiers": discord.Color.gold(),
                    "tanks": discord.Color.light_grey(),
                    "aircraft": discord.Color.from_rgb(135, 206, 235),  # Sky Blue
                    "ships": discord.Color.dark_blue(),
                    "missiles": discord.Color.red(),
                    "nukes": discord.Color.from_rgb(50, 205, 50),  # Lime Green
                }
                embed_color = UNIT_COLORS.get(most_expensive_unit, discord.Color.blue())

            # Build the embed
            embed = discord.Embed(
                title=f"{mention('costs') or '💰'} Live Military Units Calculator",
                description=f"Calculator with 30-min cached prices - {total_units:,} total units",
                color=embed_color
            )
            
            # Add unit breakdown field
            if unit_breakdown:
                embed.add_field(
                    name=f"{mention('general') or '📋'} Unit Breakdown",
                    value="\n".join(unit_breakdown) if unit_breakdown else "No units selected",
                    inline=False
                )
            
            # Add total resources field if any resources are needed
            if resource_totals:
                resource_summary = []
                for resource, data in resource_totals.items():
                    try:
                        resource_emoji_icon = resource_emoji(resource) or "📦"
                        resource_price = resource_prices.get('sell', {}).get(resource, 0)
                        resource_summary.append(
                            f"**{data['amount']:,.1f}** *{resource.title()}* {resource_emoji_icon}\n* **${resource_price:,.2f}** ppu = **${data['cost']:,.0f}**"
                        )
                    except Exception as e:
                        logging.error(f"Error processing resource {resource}: {e}")
                        continue
                
                if resource_summary:
                    resource_summary.append(f"\n**Resources Total: ${total_resource_cost:,.0f}**")
                    
                    embed.add_field(
                        name=f"{mention('inventory') or '📦'} Total Resources",
                        value="\n".join(resource_summary),
                        inline=False
                    )
            
            # Add total costs field
            total_costs_text = ""
            total_costs_text += f"*Money Total:* **${money_total:,.0f}**"
            if resource_totals:
                total_costs_text += f"\n*Resources Total:* **${total_resource_cost:,.0f}**"
            total_costs_text += f"\n*Grand Total:* **${grand_total:,.0f}**"
            
            # Add easter egg if applicable
            easter_egg = _get_easter_egg(self.units)
            if easter_egg:
                total_costs_text += f"\n\n{easter_egg}"
            
            embed.add_field(
                name=f"{mention('total') or '💰'} Total Costs",
                value=total_costs_text,
                inline=False
            )
            
            # Add cache information
            try:
                cache_age = self.price_cache.get_cache_age()
                embed.set_footer(
                    text=f"Prices cached {cache_age} ago • Use 'Set Unit Quantities' to update"
                )
            except Exception as e:
                logging.error(f"Error getting cache age: {e}")
                embed.set_footer(text="Use 'Set Unit Quantities' to update")
            
            return embed
            
        except Exception as e:
            logging.error(f"Critical error creating embed: {e}")
            # Return a basic error embed
            error_embed = discord.Embed(
                title="❌ Calculator Error",
                description="An error occurred while calculating unit costs. Please try again.",
                color=discord.Color.red()
            )
            return error_embed
    
    async def update_display(self, interaction: discord.Interaction):
        """Update the embed with current calculations."""
        try:
            embed = await self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)
                
        except discord.HTTPException as e:
            logging.error(f"Discord HTTP error updating display: {e}")
            await interaction.followup.send("❌ Failed to update display. Please try again.", ephemeral=True)
        except discord.NotFound:
            logging.error("Message not found when updating display")
            await interaction.followup.send("❌ The message was not found. The calculator may have expired.", ephemeral=True)
        except discord.Forbidden:
            logging.error("Permission error updating display")
            await interaction.followup.send("❌ Permission error. I may not have permission to edit this message.", ephemeral=True)
        except Exception as e:
            logging.error(f"Unexpected error updating display: {e}")
            await interaction.followup.send("❌ An error occurred updating the display.", ephemeral=True)
    
    @discord.ui.button(label="Recalculate", emoji=get_partial("calculator") or '🔄', style=discord.ButtonStyle.primary, row=0)
    async def recalculate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open modal for unit input."""
        try:
            modal = UnitInputModal(self.units, self)
            await interaction.response.send_modal(modal)
        except Exception as e:
            logging.error(f"Unexpected error sending unit input modal: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Failed to open unit input modal. Please try again.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Failed to open unit input modal. Please try again.", ephemeral=True)
    
    @discord.ui.button(label="Close", emoji="❌", style=discord.ButtonStyle.danger, row=0)
    async def close_calculator_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Close the calculator but preserve the final calculations."""
        try:
            # Create final embed without buttons
            embed = await self.create_embed()
            embed.title = f"{mention('costs') or '💰'} Military Units Calculation - Final"
            embed.description = "Calculator closed - Final calculation preserved"
            embed.color = discord.Color.green()
            
            # Remove all buttons by editing with view=None
            await interaction.response.edit_message(embed=embed, view=None)
            
            # Stop the view to prevent further interactions
            self.stop()
            
        except discord.HTTPException as e:
            logging.error(f"Discord HTTP error closing calculator: {e}")
            await interaction.followup.send("❌ Failed to close calculator. Please try again.", ephemeral=True)
        except discord.NotFound:
            logging.error("Message not found when closing calculator")
            await interaction.followup.send("❌ The message was not found. The calculator may have expired.", ephemeral=True)
        except discord.Forbidden:
            logging.error("Permission error closing calculator")
            await interaction.followup.send("❌ Permission error. I may not have permission to edit this message.", ephemeral=True)
        except Exception as e:
            logging.error(f"Unexpected error closing calculator: {e}")
            await interaction.followup.send("❌ Error closing calculator.", ephemeral=True)


class Units(commands.Cog):
    """Cog for P&W unit cost calculations."""

    def __init__(self, bot, query_system=None, calc_system=None):
        self.bot = bot
        self.query_system = query_system
        self.calc_system = calc_system

    @app_commands.command(name="units", description="Calculate the total cost of military units")
    @app_commands.describe(
        soldiers="Number of Soldiers",
        tanks="Number of Tanks", 
        aircraft="Number of Aircraft",
        ships="Number of Ships",
        missiles="Number of Missiles",
        nukes="Number of Nukes",
        live_mode="Use interactive live calculator (default: true)"
    )
    async def units_command(
        self,
        interaction: discord.Interaction,
        soldiers: Optional[int] = 0,
        tanks: Optional[int] = 0,
        aircraft: Optional[int] = 0,
        ships: Optional[int] = 0,
        missiles: Optional[int] = 0,
        nukes: Optional[int] = 0,
        live_mode: Optional[bool] = True
    ):
        """Calculate total cost of military units with current resource prices."""
        
        # Validate input parameters
        try:
            # Ensure all values are non-negative integers
            soldiers = max(0, int(soldiers) if soldiers is not None else 0)
            tanks = max(0, int(tanks) if tanks is not None else 0)
            aircraft = max(0, int(aircraft) if aircraft is not None else 0)
            ships = max(0, int(ships) if ships is not None else 0)
            missiles = max(0, int(missiles) if missiles is not None else 0)
            nukes = max(0, int(nukes) if nukes is not None else 0)
        except (ValueError, TypeError) as e:
            logging.error(f"Invalid input parameters: {e}")
            await interaction.response.send_message("❌ Invalid input parameters. Please provide valid numbers.", ephemeral=True)
            return
        
        # If live_mode is True, launch the interactive calculator
        if live_mode:
            try:
                initial_units = {
                    "soldiers": soldiers, "tanks": tanks, "aircraft": aircraft, 
                    "ships": ships, "missiles": missiles, "nukes": nukes
                }

                # Defer response to show a loading state
                await interaction.response.defer()

                # Create the view and initial embed
                view = LiveUnitCalculatorView(initial_units=initial_units)
                embed = await view.create_initial_embed()
                
                # Send the message and store it in the view
                message = await interaction.followup.send(embed=embed, view=view)
                view.message = message
                return  # Exit after launching live mode

            except discord.HTTPException as e:
                logging.error(f"Discord HTTP error in live calculator: {e}")
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Failed to create live calculator.", ephemeral=True)
                else:
                    await interaction.followup.send("❌ Failed to create live calculator.", ephemeral=True)
                return
            except Exception as e:
                logging.error(f"Unexpected error in live calculator: {e}")
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ An error occurred creating the live calculator.", ephemeral=True)
                else:
                    await interaction.followup.send("❌ An error occurred creating the live calculator.", ephemeral=True)
                return

        # Fallback to static calculation if live_mode is False
        try:
            await interaction.response.defer()
        except discord.HTTPException as e:
            logging.error(f"Discord defer error: {e}")
            await interaction.response.send_message("❌ Failed to process command. Please try again.", ephemeral=True)
            return
            
        total_units = soldiers + tanks + aircraft + ships + missiles + nukes
        if total_units == 0:
            # If no units are provided in static mode, guide the user
            await interaction.followup.send(
                "❌ Please specify units for calculation or use `live_mode:True` for the interactive calculator."
            )
            return

        try:
            # Get current resource prices with error handling
            resource_prices_data = await get_resource_prices()
            if not resource_prices_data or not isinstance(resource_prices_data, dict):
                logging.warning("Invalid resource prices data received")
                await interaction.followup.send("❌ Unable to fetch current resource prices. Please try again later.")
                return
            
            resource_prices = resource_prices_data.get('sell', {})
            if not isinstance(resource_prices, dict):
                logging.warning("Invalid sell prices data")
                resource_prices = {}
            
            # Calculate costs
            unit_breakdown = []
            resource_totals = {}
            money_total = 0
            unit_total_costs = {}
            
            # Get military emoji mappings with error handling
            try:
                military_emoji_map = military_codes()
                if not military_emoji_map:
                    logging.warning("Empty military emoji mappings")
                    military_emoji_map = {}
            except Exception as e:
                logging.error(f"Error getting military emoji mappings: {e}")
                military_emoji_map = {}
            
            units_config = [
                ("soldiers", soldiers, military_emoji_map.get("soldiers", "🪖")),
                ("tanks", tanks, military_emoji_map.get("tanks", "⚔️")),
                ("aircraft", aircraft, military_emoji_map.get("aircraft", "✈️")),
                ("ships", ships, military_emoji_map.get("ships", "🚢")),
                ("missiles", missiles, military_emoji_map.get("missiles", "🚀")),
                ("nukes", nukes, military_emoji_map.get("nukes", "☢️"))
            ]
            
            for unit_type, quantity, emoji in units_config:
                if quantity <= 0:
                    continue
                
                # Validate unit costs data
                if unit_type not in UNIT_COSTS:
                    logging.warning(f"Missing unit costs for {unit_type}")
                    continue
                
                unit_costs = UNIT_COSTS[unit_type]
                if not isinstance(unit_costs, dict):
                    logging.warning(f"Invalid unit costs data for {unit_type}")
                    continue
                
                # Get cash cost with validation
                cash_cost = unit_costs.get("cash", 0)
                if not isinstance(cash_cost, (int, float)) or cash_cost < 0:
                    logging.warning(f"Invalid cash cost for {unit_type}: {cash_cost}")
                    cash_cost = 0
                
                unit_money_cost = cash_cost * quantity
                money_total += unit_money_cost

                unit_resource_cost = 0
                # Calculate resource costs for this unit type
                for resource, amount_per_unit in unit_costs.items():
                    if resource == "cash":
                        continue
                    
                    # Validate resource amount
                    if not isinstance(amount_per_unit, (int, float)) or amount_per_unit <= 0:
                        continue
                    
                    total_resource_needed = amount_per_unit * quantity
                    if total_resource_needed > 0:
                        resource_price = resource_prices.get(resource, 0)
                        if not isinstance(resource_price, (int, float)) or resource_price < 0:
                            resource_price = 0
                        
                        resource_cost = total_resource_needed * resource_price
                        unit_resource_cost += resource_cost
                        
                        # Add to resource totals
                        if resource not in resource_totals:
                            resource_totals[resource] = {"amount": 0, "cost": 0}
                        resource_totals[resource]["amount"] += total_resource_needed
                        resource_totals[resource]["cost"] += resource_cost
                
                unit_total_costs[unit_type] = unit_money_cost + unit_resource_cost
                
                # Add unit breakdown
                unit_breakdown.append(f"**{quantity:,}** *{unit_type.title()}* {emoji}\n* **${unit_money_cost:,.0f}**")
            
            # Calculate totals with validation
            try:
                total_resource_cost = sum(r["cost"] for r in resource_totals.values())
                grand_total = money_total + total_resource_cost
            except Exception as e:
                logging.error(f"Error calculating totals: {e}")
                total_resource_cost = 0
                grand_total = money_total
            
            # Build the embed with error handling
            try:
                # Determine embed color
                embed_color = discord.Color.blue()  # Default color
                if unit_total_costs:
                    most_expensive_unit = max(unit_total_costs, key=unit_total_costs.get)

                    UNIT_COLORS = {
                        "soldiers": discord.Color.gold(),
                        "tanks": discord.Color.light_grey(),
                        "aircraft": discord.Color.from_rgb(135, 206, 235),  # Sky Blue
                        "ships": discord.Color.dark_blue(),
                        "missiles": discord.Color.red(),
                        "nukes": discord.Color.from_rgb(50, 205, 50),  # Lime Green
                    }
                    embed_color = UNIT_COLORS.get(most_expensive_unit, discord.Color.blue())

                embed = discord.Embed(
                    title=f"{mention('costs') or '💰'} Military Units Cost Calculator",
                    description=f"Cost breakdown for {total_units:,} total units",
                    color=embed_color
                )
                
                # Add unit breakdown field
                embed.add_field(
                    name=f"{mention('general') or '📋'} Unit Breakdown",
                    value="\n".join(unit_breakdown) if unit_breakdown else "No units selected",
                    inline=False
                )
                
                # Add total resources field if any resources are needed
                if resource_totals:
                    resource_summary = []
                    for resource, data in resource_totals.items():
                        try:
                            resource_emoji_icon = resource_emoji(resource) or "📦"
                            resource_price = resource_prices.get(resource, 0)
                            resource_summary.append(
                                f"**{data['amount']:,.1f}** *{resource.title()}* {resource_emoji_icon}\n* **${resource_price:,.2f}** ppu = **${data['cost']:,.0f}**"
                            )
                        except Exception as e:
                            logging.error(f"Error processing resource {resource}: {e}")
                            continue
                    
                    if resource_summary:
                        resource_summary.append(f"\n**Resources Total: ${total_resource_cost:,.0f}**")
                        
                        embed.add_field(
                            name=f"{mention('inventory') or '📦'} Total Resources",
                            value="\n".join(resource_summary),
                            inline=False
                        )
                
                # Add total costs field
                total_costs_text = ""
                total_costs_text += f"*Money Total:* **${money_total:,.0f}**"
                if resource_totals:
                    total_costs_text += f"\n*Resources Total:* **${total_resource_cost:,.0f}**"
                total_costs_text += f"\n*Grand Total:* **${grand_total:,.0f}**"
                
                # Add easter egg if applicable
                units = {
                    "soldiers": soldiers, "tanks": tanks, "aircraft": aircraft, 
                    "ships": ships, "missiles": missiles, "nukes": nukes
                }
                easter_egg = _get_easter_egg(units)
                if easter_egg:
                    total_costs_text += f"\n\n{easter_egg}"
                
                embed.add_field(
                    name=f"{mention('total') or '💰'} Total Costs",
                    value=total_costs_text,
                    inline=False
                )
                
                embed.set_footer(text="Prices based on current market best sell prices")
                
                await interaction.followup.send(embed=embed)
                
            except discord.HTTPException as e:
                logging.error(f"Discord HTTP error sending embed: {e}")
                await interaction.followup.send("❌ Failed to send calculation results. Please try again.", ephemeral=True)
            except Exception as e:
                logging.error(f"Error building embed: {e}")
                await interaction.followup.send("❌ An error occurred while creating the results display.", ephemeral=True)
                
        except asyncio.TimeoutError:
            logging.error("Timeout while fetching resource prices")
            await interaction.followup.send("❌ Request timed out while fetching resource prices. Please try again.", ephemeral=True)
        except ConnectionError as e:
            logging.error(f"Connection error while fetching resource prices: {e}")
            await interaction.followup.send("❌ Connection error while fetching resource prices. Please try again later.", ephemeral=True)
        except discord.HTTPException as e:
            logging.error(f"Discord HTTP error in units command: {e}")
            await interaction.followup.send("❌ Discord error occurred. Please try again.", ephemeral=True)
        except Exception as e:
            logging.error(f"Unexpected error in units command: {e}")
            await interaction.followup.send(f"❌ An error occurred while calculating unit costs: {str(e)}", ephemeral=True)

async def setup(bot):
    """Add the Units cog to the bot."""
    await bot.add_cog(Units(bot))
