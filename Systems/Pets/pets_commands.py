from __future__ import annotations

from typing import Dict, Any, Tuple, Optional, Literal

import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
import random
import re
import json
import os

from enum import Enum, auto

from Systems.Functions.user_data_manager import user_data_manager
from .PetGames.quests import locations, QuestView, file_manager, generate_or_load_quest
from Systems.Pets.Logic.pet_brain import LootCalculator
from Systems.Functions import emoji as emoji_mod
from Systems.Pets.Logic.pet_badge import generate_pet_badge

from .pets_system import (
    PetSystem, 
    send_level_up_embed, 
    send_level_down_embed, 
    KillConfirmView,
    create_pet_shop_embed,
    create_delete_warning_embed,
    PetShopView,
    PetStatusView,
    LootMarketView,
    InventoryPaginatedView
)
from .PetGames.battle_system import UnifiedBattleView
from .PetGames.pvp_system import PvPBattleView, BattleMode
from .PetGames.tournament import Tournament, TournamentSize, TournamentView
from .PetGames.races import RaceSession
from .PetGames.craps import CrapsSession
from .PetGames.holdem import HoldemSession
from .PetGames.blackjack import BlackjackSession
from .PetGames.slots import SlotMachineView, compute_total_xp

logger = logging.getLogger(__name__)

class LobbyState(Enum):
    WAITING = auto()
    STARTING = auto()
    IN_PROGRESS = auto()

class PvPLobbyView(discord.ui.View):
    
    def __init__(self, bot, creator: discord.Member, battle_mode: str, max_players: int = 2):
        super().__init__(timeout=None)
        self.bot = bot
        self.creator = creator
        self.battle_mode = battle_mode
        self.max_players = max_players
        self.state = LobbyState.WAITING
        self.players: List[discord.Member] = [creator]
        self.message: Optional[discord.Message] = None
        self.start_task: Optional[asyncio.Task] = None
        self.update_buttons()
    
    def update_buttons(self):
        self.clear_items()
        join_button = discord.ui.Button(style=discord.ButtonStyle.primary, label="Join", custom_id="join")
        join_button.callback = self.join_callback
        self.add_item(join_button)
        leave_button = discord.ui.Button(style=discord.ButtonStyle.secondary, label="Leave", custom_id="leave")
        leave_button.callback = self.leave_callback
        self.add_item(leave_button)
        if len(self.players) >= 2:
            start_button = discord.ui.Button(style=discord.ButtonStyle.green, label="Start Battle", custom_id="start")
            start_button.callback = self.start_callback
            self.add_item(start_button)
    
    def get_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"⚔️ {self.battle_mode.upper()} PvP Lobby",
            description=f"**Battle Type:** {self.battle_mode.upper()}\n"
            f"**Players:** {len(self.players)}/{self.max_players}\n"
            f"**Status:** {self.state.name.replace('_', ' ').title()}",
            color=discord.Color.blue()
        )
        player_list = "\n".join(
            f"{i+1}. {member.mention} {'👑' if member == self.creator else ''}"
            for i, member in enumerate(self.players)
        )
        embed.add_field(name="Players", value=player_list or "No players yet", inline=False)
        if self.state == LobbyState.WAITING:
            instructions = (
                "• Click **Join** to enter the battle\n"
                "• Click **Leave** to exit the lobby\n"
                "• Creator can click **Start Battle** when ready"
            )
            embed.add_field(name="How to Play", value=instructions, inline=False)
        embed.set_footer(text=f"Created by {self.creator.display_name}")
        return embed
    
    async def join_callback(self, interaction: discord.Interaction):
        if interaction.user in self.players:
            await interaction.response.send_message("You're already in the lobby!", ephemeral=True)
            return
        if len(self.players) >= self.max_players:
            await interaction.response.send_message("This lobby is full!", ephemeral=True)
            return
        self.players.append(interaction.user)
        await self.update_lobby(interaction)
        await interaction.response.send_message("You've joined the lobby!", ephemeral=True)
        if len(self.players) >= self.max_players and not self.start_task:
            try:
                for member in self.players:
                    await member.send(f"⚔️ PvP FFA is full! Battle begins in 5 minutes.")
            except Exception:
                pass
            self.state = LobbyState.STARTING
            self.start_task = asyncio.create_task(self._auto_start_after_delay(300))
    
    async def leave_callback(self, interaction: discord.Interaction):
        if interaction.user not in self.players:
            await interaction.response.send_message("You're not in this lobby!", ephemeral=True)
            return
        if interaction.user == self.creator:
            await interaction.response.send_message(
                "You're the lobby creator! Use /pvp cancel to close the lobby.",
                ephemeral=True
            )
            return
        self.players.remove(interaction.user)
        await self.update_lobby(interaction)
        await interaction.response.send_message("You've left the lobby.", ephemeral=True)
    
    async def start_callback(self, interaction: discord.Interaction):
        if interaction.user != self.creator:
            await interaction.response.send_message("Only the lobby creator can start the battle!", ephemeral=True)
            return
        if len(self.players) < 2:
            await interaction.response.send_message("You need at least 2 players to start!", ephemeral=True)
            return
        self.state = LobbyState.STARTING
        await self.update_lobby(interaction)
        await interaction.response.defer()
        await self.start_battle()
    
    async def update_lobby(self, interaction: discord.Interaction):
        self.update_buttons()
        try:
            await interaction.message.edit(embed=self.get_embed(), view=self)
        except Exception as e:
            logger.error(f"Error updating lobby: {e}")
    
    async def update_lobby_by_interaction(self, interaction: discord.Interaction):
        self.update_buttons()
        try:
            await self.message.edit(embed=self.get_embed(), view=self)
        except Exception as e:
            logger.error(f"Error updating lobby: {e}")
    
    async def start_battle(self):
        self.state = LobbyState.IN_PROGRESS
        if self.start_task:
            try:
                self.start_task.cancel()
            except:
                pass
        try:
            pvp_cog = self.bot.get_cog("PetCommandsCog")
            if not pvp_cog:
                logger.error("PetCommandsCog not found!")
                return
            channel = self.message.channel if self.message else None
            if not channel:
                logger.error("Lobby message channel not available for starting battle")
                return
            if len(self.players) == 2:
                await pvp_cog.start_1v1_battle(channel, self.players[0], self.players[1])
            elif len(self.players) > 2:
                await pvp_cog.start_ffa_battle(channel, self.players)
            else:
                logger.error(f"Not enough players to start battle: {len(self.players)}")
        except Exception as e:
            logger.error(f"Error starting battle: {e}", exc_info=True)
        await self.cleanup()
    
    async def _auto_start_after_delay(self, seconds: int):
        try:
            await asyncio.sleep(seconds)
            if self.state == LobbyState.STARTING:
                await self.start_battle()
        except Exception as e:
            logger.error(f"Error in auto start: {e}")
    
    async def cleanup(self):
        for item in self.children:
            if hasattr(item, 'disabled'):
                item.disabled = True
        try:
            if self.message:
                embed = self.get_embed()
                embed.title = f"⚔️ {self.battle_mode.upper()} PvP Lobby (Closed)"
                embed.color = discord.Color.dark_gray()
                await self.message.edit(embed=embed, view=self)
        except Exception as e:
            logger.error(f"Error cleaning up lobby: {e}")

class PetCommandsCog(commands.Cog):
    """Cog for pet-related commands"""
    
    def __init__(self, bot: commands.Bot, pet_system: PetSystem):
        self.bot = bot
        self.pet_system = pet_system
        self.active_battles = {} 
        self.pending_challenges = {}  
        self.craps_sessions = {}
        self.holdem_sessions = {}
        self.blackjack_sessions = {}

    @staticmethod
    def get_emoji_by_name(emoji_name: str) -> str:
        emoji_id = emoji_mod.EMOJI_IDS.get(emoji_name)
        if emoji_id:
            return f"<:{emoji_name}:{emoji_id}>"
        return emoji_name # Fallback to plain text if not found

    @commands.hybrid_command(name='slots', description='Play Pet XP Slots')
    @app_commands.describe(
        difficulty="Choose slot difficulty",
        mode="Betting changes XP; Fun does not",
        bet_amount="Required if mode is Betting (10-100000)"
    )
    @app_commands.choices(difficulty=[
        app_commands.Choice(name="Very Easy", value="very_easy"),
        app_commands.Choice(name="Easy", value="easy"),
        app_commands.Choice(name="Medium", value="medium"),
        app_commands.Choice(name="Hard", value="hard"),
        app_commands.Choice(name="Very Hard", value="very_hard"),
        app_commands.Choice(name="Insanity", value="insanity"),
    ])
    @app_commands.choices(mode=[
        app_commands.Choice(name="Betting", value="betting"),
        app_commands.Choice(name="Fun", value="fun"),
    ])
    async def slots(self: "PetCommandsCog", ctx: commands.Context[commands.Bot], difficulty: str, mode: str = "betting", bet_amount: Optional[int] = None) -> None:
        try:
            pet = await user_data_manager.get_pet_data_async(str(ctx.author.id), ctx.author.display_name)
            if not pet:
                await ctx.send("❌ You need a pet to play slots. Use `/pet_shop` first.")
                return
            
            if mode.lower() == "betting":
                if bet_amount is None:
                    await ctx.send("❌ Betting mode requires a bet amount (10-100000).")
                    return
                try:
                    bet = int(bet_amount)
                except Exception:
                    await ctx.send("❌ Bet amount must be a number.")
                    return
                if bet < 10 or bet > 100000:
                    await ctx.send("❌ Bet must be between 10 and 100000 XP!")
                    return
                total_xp = compute_total_xp(pet)
                if bet > total_xp:
                    await ctx.send(f"❌ Bet exceeds your total XP ({total_xp}).")
                    return
                view = SlotMachineView(self.bot, ctx.author, difficulty.lower(), bet, mode="betting")
                embed = discord.Embed(
                    title=f"🎰 PET XP SLOTS - {difficulty.upper()} 🎰",
                    description="Press 🎰 SPIN to start the animation and reveal your result.",
                    color=discord.Color.gold()
                )
                embed.add_field(name="📈 XP Bet", value=f"**{bet}** XP", inline=True)
                await ctx.send(embed=embed, view=view)
            else:
                view = SlotMachineView(self.bot, ctx.author, difficulty.lower(), 0, mode="fun")
                embed = discord.Embed(
                    title=f"🎰 PET XP SLOTS - {difficulty.upper()} 🎰",
                    description="Press 🎰 SPIN to start the animation and reveal your result.",
                    color=discord.Color.gold()
                )
                embed.add_field(name="📈 Mode", value="**Fun (no XP change)**", inline=True)
                await ctx.send(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Error in slots command: {e}")
            await ctx.send("❌ Failed to start slots.")

    @app_commands.command(name="play", description="Let your pet play in various locations!")
    @app_commands.describe(
        place="Choose a place for your pet to play"
    )
    @app_commands.choices(place=[
        app_commands.Choice(name=location, value=location) for location in locations
    ])
    async def play(self, interaction: discord.Interaction, place: app_commands.Choice[str]):
        user_id_str = str(interaction.user.id)
        pet_data = await self.pet_system.get_user_pet(interaction.user.id)

        if not pet_data:
            await interaction.response.send_message("You don't have a pet yet! Use `/pet adopt` to get one.", ephemeral=True)
            return

        # 5% chance for a boss encounter
        if random.random() < 0.05:
            boss_encountered = await self.pet_system.handle_boss_encounter(interaction, place.value)
            if boss_encountered:
                return  # Stop normal play logic if a boss appears

        # --- Capture old pet level BEFORE XP is awarded ---
        old_pet_level = pet_data.get("level", 1)

        pet_element = pet_data.get("element", "basic").lower()
        pet_element2 = pet_data.get("element2", "").lower()
        chosen_place = place.value

        # Get emojis
        pet_emoji = self.get_emoji_by_name(pet_data.get("emoji_name", pet_data["species"])) # Assuming a default emoji name
        place_emoji = self.get_emoji_by_name(self.pet_system.locations_data.get("locations", {}).get(chosen_place, {}).get("emoji_name", "place_default"))
        element1_emoji = self.get_emoji_by_name(pet_element.capitalize())
        element2_emoji = self.get_emoji_by_name(pet_element2.capitalize()) if pet_element2 else ""
        outcome_data = self.pet_system.locations_data.get("locations", {}).get(chosen_place, {})
        place_specials = outcome_data.get("Special", {})
        outcome_messages_list = []

        xp_multiplier, keys_to_award_names = LootCalculator.calculate_play_loot(pet_element, pet_element2, place_specials)

        final_outcome_message = LootCalculator.get_play_outcome_message(
            pet_element,
            pet_element2,
            outcome_data,
            chosen_place,
            pet_data['name'],
            pet_emoji,
            place_emoji,
            element1_emoji,
            element2_emoji
        )

        pet_level = old_pet_level  # Use captured pre-XP level for XP calculation
        base_xp = 5 * pet_level  # Use robust XP formula!
        xp_gained = base_xp * xp_multiplier

        # Increment play attempts
        await user_data_manager.increment_pet_stats(user_id_str, {"play_attempts": 1})

        keys_awarded_emojis = []
        for key_name in keys_to_award_names:
            key_item = {"name": key_name, "type": "Key", "count": 1}
            await LootCalculator.add_item_to_inventory(interaction.user.id, key_item, pet_data)
            keys_awarded_emojis.append(self.get_emoji_by_name(key_name))

        # Award XP
        success, _ = await user_data_manager.add_pet_experience(interaction.user.id, xp_gained, "play")

        # RELOAD pet data after XP change to get correct new stats!
        pet_data = await user_data_manager.get_pet_data_async(str(interaction.user.id), interaction.user.display_name)
        new_pet_level = pet_data.get("level", 1)

        response_message = f"{final_outcome_message}\n\nYour pet gained {xp_gained} XP and received {', '.join(keys_awarded_emojis)}!"
        await interaction.response.send_message(response_message)

        # Level up embed
        if new_pet_level > old_pet_level:
            level_up_embed = await LootCalculator.create_level_up_embed(pet_data, old_pet_level, new_pet_level, "play")
            await interaction.followup.send(embed=level_up_embed)
        # Level down embed (optional)
        elif new_pet_level < old_pet_level:
            level_down_embed = await LootCalculator.create_level_down_embed(pet_data, old_pet_level, new_pet_level, "play", abs(xp_gained))
            await interaction.followup.send(embed=level_down_embed)

    @commands.hybrid_command(name='equip', description='Equip items to your pet (Material, Gems, Monsters, Hat)')
    @app_commands.describe(
        material="Select material(s) to equip (up to 2, separated by comma)",
        gems="Select gems to equip (up to 2, separated by comma)",
        monsters="Select monsters to equip (up to 2, separated by comma)",
        hat="Select a hat to equip"
    )
    async def equip(self, ctx: commands.Context, material: Optional[str] = None, gems: Optional[str] = None, monsters: Optional[str] = None, hat: Optional[str] = None):
        if not material and not gems and not monsters and not hat:
            await ctx.send("⚠️ You must provide at least one item to equip!", ephemeral=True)
            return

        success, msg = await LootCalculator.equip_items(str(ctx.author.id), ctx.author.name, material, gems, monsters, hat)
        
        embed = discord.Embed(
            title="🎒 Equipment Updated",
            description=msg,
            color=discord.Color.green() if success else discord.Color.red()
        )
        await ctx.send(embed=embed)

    @equip.autocomplete('material')
    async def equip_material_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        user_id = interaction.user.id
        pet = await self.pet_system.get_user_pet(user_id)
        if not pet: return []
        inventory = pet.get('inventory', [])
        
        choices = []
        materials = sorted(list(set([i['name'] for i in inventory if 'Material' in i.get('type', 'Material')])))
        
        if "," in current:
            first_part, second_part = current.rsplit(',', 1)
            first_part = first_part.strip()
            second_part = second_part.strip()
            
            for name in materials:
                if second_part.lower() in name.lower():
                    val = f"{first_part}, {name}"
                    choices.append(app_commands.Choice(name=val, value=val))
        else:
            for name in materials:
                if current.lower() in name.lower():
                    choices.append(app_commands.Choice(name=name, value=name))
        return choices[:25]


    @equip.autocomplete('hat')
    async def equip_hat_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        user_id = interaction.user.id
        pet = await self.pet_system.get_user_pet(user_id)
        if not pet: return []
        inventory = pet.get('inventory', [])
        
        choices = []
        hats = sorted(list(set([i['name'] for i in inventory if 'Hat' in i.get('type', 'Hat')])))
        
        for name in hats:
            if current.lower() in name.lower():
                choices.append(app_commands.Choice(name=name, value=name))
        return choices[:25]

    @equip.autocomplete('gems')
    async def equip_gems_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        user_id = interaction.user.id
        pet = await self.pet_system.get_user_pet(user_id)
        if not pet: return []
        inventory = pet.get('inventory', [])
        
        gems = sorted(list(set([i['name'] for i in inventory if 'Gem' in i.get('type', '')])))
        choices = []
        
        if "," in current:
            # Second gem suggestion
            first_part, second_part = current.rsplit(',', 1)
            first_part = first_part.strip()
            second_part = second_part.strip()
            
            for name in gems:
                if second_part.lower() in name.lower():
                    val = f"{first_part}, {name}"
                    choices.append(app_commands.Choice(name=val, value=val))
        else:
            # First gem suggestion
            for name in gems:
                if current.lower() in name.lower():
                    choices.append(app_commands.Choice(name=name, value=name))
                    
        return choices[:25]

    @equip.autocomplete('monsters')
    async def equip_monsters_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        user_id = interaction.user.id
        pet = await self.pet_system.get_user_pet(user_id)
        if not pet: return []
        inventory = pet.get('inventory', [])
        
        monsters = sorted(list(set([i['name'] for i in inventory if 'Monster' in i.get('type', '')])))
        choices = []
        
        if "," in current:
            first_part, second_part = current.rsplit(',', 1)
            first_part = first_part.strip()
            second_part = second_part.strip()
            
            for name in monsters:
                if second_part.lower() in name.lower():
                    val = f"{first_part}, {name}"
                    choices.append(app_commands.Choice(name=val, value=val))
        else:
            for name in monsters:
                if current.lower() in name.lower():
                    choices.append(app_commands.Choice(name=name, value=name))
                    
        return choices[:25]

    @commands.hybrid_command(name='unequip', description='Unequip items from your pet (Material, Gems, Monsters)')
    @app_commands.describe(slot="Select the slot to unequip")
    @app_commands.choices(slot=[
        app_commands.Choice(name="Material", value="Material"),
        app_commands.Choice(name="Gems", value="Gems"),
        app_commands.Choice(name="Monsters", value="Monsters"),
        app_commands.Choice(name="Hat", value="Hat")
    ])
    async def unequip(self, ctx: commands.Context, slot: str):
        success, msg = await LootCalculator.unequip_items(str(ctx.author.id), slot)
        
        embed = discord.Embed(
            title="🎒 Equipment Updated",
            description=msg,
            color=discord.Color.green() if success else discord.Color.red()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='use', description='Use a consumable item (Potion)')
    @app_commands.describe(item="Select potion(s) to use (up to 5, separated by comma)")
    async def use(self, ctx: commands.Context, item: str):
        potion_names = [p.strip() for p in item.split(',') if p.strip()]
        
        if not potion_names:
            await ctx.send("Please specify at least one potion to use.", ephemeral=True)
            return

        if len(potion_names) > 5:
            await ctx.send("You can use a maximum of 5 potions at once.", ephemeral=True)
            return

        results = []
        all_success = True
        for potion_name in potion_names:
            success, msg = await LootCalculator.use_potion(ctx.author.id, potion_name)
            if success:
                results.append(f"{msg}") # msg already contains the potion emoji
            else:
                results.append(f"❌ **{potion_name}**: {msg}")
            if not success:
                all_success = False
        
        title = "🧪 Potions Used" if all_success else "⚠️ Potions Used (with errors)"
        color = discord.Color.green() if all_success else discord.Color.orange()

        embed = discord.Embed(
            title=title,
            description="\n".join(results),
            color=color
        )
        await ctx.send(embed=embed)

    @use.autocomplete('item')
    async def use_item_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        user_id = interaction.user.id
        pet = await self.pet_system.get_user_pet(user_id)
        if not pet: return []
        inventory = pet.get('inventory', [])
        
        # Filter for Potions
        potions = sorted(list(set([i['name'] for i in inventory if i.get('type') == 'Potion'])))
        
        choices = []
        for name in potions:
            if current.lower() in name.lower():
                choices.append(app_commands.Choice(name=name, value=name))
        return choices[:25]

    @commands.hybrid_group(name="loot", description="Loot related commands")
    async def loot(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
             await ctx.send("Use /loot market", ephemeral=True)

    @loot.command(name="market", description="Open the Loot Market to open chests")
    async def loot_market(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        pet = await self.pet_system.get_user_pet(ctx.author.id)
        if not pet:
            await ctx.send("❌ You need a pet to access the Loot Market! Use `/pet_shop` to adopt one.", ephemeral=True)
            return
        
        view = LootMarketView(ctx.author.id, pet)
        
        embed = discord.Embed(
            title=f"{emoji_mod.mention('market') or '🗝️'} Loot Market",
            description="Welcome to the Loot Market! Spend your keys to open chests.\n\n"
                        "**Chest Tiers:**\n"
                        f"{emoji_mod.mention('chest1') or '📦'} **Chest 1:** Costs 1 {emoji_mod.mention('Key1') or 'Key1'} -> 1 Random Item\n"
                        f"{emoji_mod.mention('chest2') or '📦'} **Chest 2:** Costs 1 {emoji_mod.mention('Key2') or 'Key2'} -> 2 Random Items\n"
                        f"{emoji_mod.mention('chest3') or '📦'} **Chest 3:** Costs 1 {emoji_mod.mention('Key3') or 'Key3'} -> 3 Random Items\n"
                        f"{emoji_mod.mention('chest4') or '📦'} **Chest 4:** Costs 1 of Each Key -> 1 Selected + 3 Random Items",
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed, view=view, ephemeral=True)

    @commands.hybrid_command(name='pet_shop', description='Visit the Pet Shop to adopt a pet')
    async def pet_shop(self: "PetCommandsCog", ctx: commands.Context):
        view = PetShopView(self.bot, ctx.author, self.pet_system)
        embed = self.pet_system.create_pet_list_embed(0, view.per_page)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @commands.hybrid_command(name='pet', description='View your digital pet\'s status')
    async def pet_status(self: "PetCommandsCog", ctx: commands.Context):
        await ctx.defer(ephemeral=False)
        
        try:
            pet = await self.pet_system.get_user_pet(ctx.author.id, force_refresh=True)
            if not pet:
                await ctx.send("🚷 You don't have a pet yet! Use `/pet_shop` to adopt one.")
                return

            badge_file = await generate_pet_badge(pet, ctx.author.id)

            if "level" not in pet:
                pet["level"] = 1
            if "experience" not in pet:
                pet["experience"] = 0

            view = PetStatusView(ctx.author.id, self.pet_system, self, pet_data=pet)
            embed = await view.create_main_embed()

            if badge_file:
                embed.set_thumbnail(url=f"attachment://{badge_file.filename}")
                message = await ctx.send(embed=embed, view=view, file=badge_file)
            else:
                message = await ctx.send(embed=embed, view=view)
            
            view.message = message
            
        except Exception as e:
            logger.error(f"Error in pet_status_command: {e}")
            try:
                await ctx.send("❌ An error occurred while loading your pet. Please try again in a moment.")
            except:
                pass

    @commands.hybrid_command(name='pet_badge', description='Generate a badge for your pet')
    async def pet_badge(self: "PetCommandsCog", ctx: commands.Context):
        await ctx.defer(ephemeral=False)
        
        try:
            pet = await self.pet_system.get_user_pet(ctx.author.id, force_refresh=True)
            if not pet:
                await ctx.send("🚷 You don't have a pet yet! Use `/pet_shop` to adopt one.")
                return

            badge_file = await generate_pet_badge(pet, ctx.author.id)

            if badge_file:
                embed = discord.Embed(title=f"{pet['name']}'s Badge", color=discord.Color.gold())
                embed.set_thumbnail(url=f"attachment://{badge_file.filename}")
                await ctx.send(embed=embed, file=badge_file)
            else:
                await ctx.send("❌ Could not generate a badge for your pet.")

        except Exception as e:
            logger.error(f"Error in pet_badge_command: {e}")
            try:
                await ctx.send("❌ An error occurred while generating your pet badge. Please try again in a moment.")
            except:
                pass

    @commands.hybrid_command(name='inventory', description='View your pet\'s inventory')
    async def inventory(self: "PetCommandsCog", ctx: commands.Context):
        """View your pet's inventory"""
        pet = await self.pet_system.get_user_pet(ctx.author.id)
        if not pet:
            await ctx.send("❌ You need a pet to view inventory! Use `/pet_shop` to adopt one.")
            return
            
        view = InventoryPaginatedView(self.pet_system, ctx.author.id, pet)
        await ctx.send(embed=view.get_embed(), view=view)

    @commands.hybrid_command(name='train', description='Train your pet to gain experience')
    @app_commands.describe(difficulty="Choose training difficulty")
    @app_commands.choices(difficulty=[
        app_commands.Choice(name="Easy", value="Easy"),
        app_commands.Choice(name="Average", value="Average"),
        app_commands.Choice(name="Hard", value="Hard"),
    ])
    async def train(self: "PetCommandsCog", ctx: commands.Context, difficulty: str = "Easy"):
        on_cd, remaining = self.pet_system._is_command_on_cooldown('train', ctx.author.id)
        if on_cd:
            await ctx.send(f"⏳ Training is on cooldown for {remaining}s")
            return
            
        self.pet_system.set_command_cooldown('train', ctx.author.id)
        success, message = await self.pet_system.train_pet(ctx, difficulty)
        if message:
            await ctx.send(message)

    @commands.hybrid_group(name='rename', description='Rename your pet or its actions')
    async def rename(self: "PetCommandsCog", ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("Invalid rename command. Use `/rename pet`, `/rename attack`, `/rename defend`, or `/rename charge`.", ephemeral=True)

    @rename.command(name="pet", description="Rename your pet")
    @app_commands.describe(new_name="The new name for your pet")
    async def rename_pet_subcommand(self: "PetCommandsCog", ctx: commands.Context, new_name: str):
        success, message = await self.pet_system.rename_pet(ctx.author.id, new_name)
        await ctx.send(message)

    @rename.command(name="attack", description="Rename your pet's attack action")
    @app_commands.describe(label="The new label for the attack action")
    async def rename_attack(self: "PetCommandsCog", ctx: commands.Context, label: str):
        success, message = await self.pet_system.rename_action(ctx.author.id, "attack", label)
        await ctx.send(message)

    @rename.command(name="defend", description="Rename your pet's defend action")
    @app_commands.describe(label="The new label for the defend action")
    async def rename_defend(self: "PetCommandsCog", ctx: commands.Context, label: str):
        success, message = await self.pet_system.rename_action(ctx.author.id, "defend", label)
        await ctx.send(message)

    @rename.command(name="charge", description="Rename your pet's charge action")
    @app_commands.describe(label="The new label for the charge action")
    async def rename_charge(self: "PetCommandsCog", ctx: commands.Context, label: str):
        success, message = await self.pet_system.rename_action(ctx.author.id, "charge", label)
        await ctx.send(message)
    
    @commands.hybrid_command(name='kill', description='Permanently delete your digital pet')
    async def kill_pet(self: "PetCommandsCog", ctx: commands.Context):
        pet = await self.pet_system.get_user_pet(ctx.author.id)
        if not pet:
            await ctx.send("🚷 You don't have a pet to delete!")
            return
        
        embed = create_delete_warning_embed(pet, self.pet_system)
        view = KillConfirmView(self.pet_system, ctx, pet)
        await ctx.send(embed=embed, view=view)
    
    @commands.hybrid_command(name='mission', description='Send your pet on a mission to gain experience')
    @app_commands.describe(difficulty="Choose mission difficulty", gamble_xp="Optional XP to gamble")
    @app_commands.choices(difficulty=[
        app_commands.Choice(name="Easy", value="Easy"),
        app_commands.Choice(name="Average", value="Average"),
        app_commands.Choice(name="Hard", value="Hard"),
    ])
    async def mission(self: "PetCommandsCog", ctx: commands.Context, difficulty: str = "Easy", gamble_xp: Optional[int] = None):
        on_cd, remaining = self.pet_system._is_command_on_cooldown('mission', ctx.author.id)
        if on_cd:
            await ctx.send(f"⏳ Mission is on cooldown for {remaining // 60}m {remaining % 60}s")
            return
            
        result = await self.pet_system.perform_mission(ctx, difficulty, gamble_xp)
        
        if result["narrative"]:
            await ctx.send(result["narrative"])
            
        if result["level_up"]:
            asyncio.create_task(send_level_up_embed(ctx.author.id, result["level_up"], ctx.channel))
            
        if result["level_down"]:
            res = result["level_down"]
            asyncio.create_task(send_level_down_embed(
                ctx.author.id, 
                res.get("old_level", 0), 
                res.get("new_level", 0), 
                "mission", 
                ctx.channel, 
                res.get("lost_xp", 0)
            ))

    @commands.hybrid_command(name="battle", description="Start a solo battle against a monster")
    @app_commands.describe(difficulty="Choose battle difficulty: Easy, Medium, or Hard")
    @app_commands.choices(difficulty=[
        app_commands.Choice(name="Easy", value="easy"),
        app_commands.Choice(name="Average", value="average"),
        app_commands.Choice(name="Hard", value="hard"),
    ])
    async def battle(self: "PetCommandsCog", ctx: commands.Context, difficulty: Optional[str] = "easy"):
        """Start a solo battle immediately with the chosen difficulty"""
        try:
            pet = await self.pet_system.get_user_pet(ctx.author.id)
            if not pet:
                await ctx.send("❌ You need a pet to battle! Use `/pet_shop` to get started.")
                return

            battle_view = await UnifiedBattleView.create_async(ctx, battle_type="solo", interaction=ctx.interaction)
            battle_view.difficulty = difficulty
            await battle_view.regenerate_enemy_for_difficulty()
            battle_view.battle_started = True
            embed = battle_view.build_battle_embed("⚔️ Battle Started! Check the channel for actions!")
            battle_view.message = await ctx.send(embed=embed)
            await battle_view.start_action_collection()
            
        except Exception as e:
            logger.error(f"Error in battle command: {e}")
            await ctx.send("❌ Error starting battle. Please try again.")

    @app_commands.command(name="pvp", description="Start a PvP free-for-all lobby")
    @app_commands.describe(max="Max other users (1-9) allowed to join")
    @app_commands.choices(max=[app_commands.Choice(name=str(i), value=str(i)) for i in range(1, 10)])
    async def pvp(self: "PetCommandsCog", interaction: discord.Interaction, max: str):
        """Start a PvP FFA lobby where players can join (no timeout)"""
        try:
            if not await self.pet_system.get_user_pet(interaction.user.id):
                return await interaction.response.send_message(
                    "❌ You need a pet to start PvP lobbies! Use `/pet_shop` to get started.",
                    ephemeral=True
                )

            if str(interaction.user.id) in self.active_battles:
                return await interaction.response.send_message(
                    "You're already in a battle!", 
                    ephemeral=True
                )
            
            if not isinstance(interaction.user, discord.Member):
                return await interaction.response.send_message(
                    "❌ This command can only be used in a guild channel.",
                    ephemeral=True
                )
            member: discord.Member = interaction.user
            
            lobby_view = PvPLobbyView(self.bot, member, "ffa", 1 + int(max))
            await interaction.response.send_message(embed=lobby_view.get_embed(), view=lobby_view)
            lobby_view.message = await interaction.original_response()
            
        except Exception as e:
            logger.error(f"Error in pvp command: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Error creating lobby.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Error creating lobby.", ephemeral=True)
    
    async def start_1v1_battle(self, channel, player1: discord.Member, player2: discord.Member):
        """Start a 1v1 battle"""
        battle_view = PvPBattleView(channel, [player1, player2], BattleMode.ONE_VS_ONE)
        self.active_battles[str(player1.id)] = battle_view
        self.active_battles[str(player2.id)] = battle_view
    
    async def start_ffa_battle(self, channel, players: list):
        """Start a free-for-all battle"""
        battle_view = PvPBattleView(channel, players, BattleMode.FREE_FOR_ALL)
        for p in players:
            self.active_battles[str(p.id)] = battle_view

    @commands.hybrid_command(name="race", description="Race pets in simulation or lobby mode")
    @app_commands.describe(
        simulation="True to race bots; False for lobby with users",
        difficulty="Shown when simulation is True",
        mode="Betting changes XP; Fun does not",
        bet="Bet XP if Betting mode"
    )
    @app_commands.choices(difficulty=[
        app_commands.Choice(name="Apprentice", value="apprentice"),
        app_commands.Choice(name="Journeyman", value="journeyman"),
        app_commands.Choice(name="Senior", value="senior"),
    ])
    @app_commands.choices(mode=[
        app_commands.Choice(name="Betting", value="betting"),
        app_commands.Choice(name="Fun", value="fun"),
    ])
    async def race(self, ctx: commands.Context, simulation: bool = True, difficulty: Optional[str] = None, mode: str = "betting", bet: Optional[int] = None):
        mode_betting = str(mode).lower() == "betting"
        if simulation and not difficulty:
            await ctx.send("Select a difficulty for simulation.", ephemeral=True)
            return
        if mode_betting and bet is None:
            await ctx.send("Bet XP is required for Betting mode.", ephemeral=True)
            return
        
        member = ctx.author
        if not isinstance(member, discord.Member):
            await ctx.send("Could not get member information. Please try again in a guild channel.", ephemeral=True)
            return

        session = RaceSession(self.bot, member, simulation, difficulty, mode_betting, bet)
        ok = await session._setup_competitors()
        if not ok:
            await ctx.send("Unable to start race. Ensure you have a pet and enough XP.", ephemeral=True)
            return
        embed = session._lobby_embed() if not simulation else session._race_embed()
        view = session
        msg = await ctx.send(embed=embed, view=view)
        session.message = msg
        if simulation:
            await session.start_race()

    @commands.hybrid_command(name="craps", description="Play Craps with Pet XP betting")
    @app_commands.describe(
        solo="If true, only you play",
        mode="Choose Betting or Fun",
        buy_in="Buy in XP for Betting mode",
        color="Choose Dice Color"
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="Betting", value="betting"),
        app_commands.Choice(name="Fun", value="fun"),
    ])
    @app_commands.choices(color=[
        app_commands.Choice(name="Random", value="Random"),
        app_commands.Choice(name="Red", value="Red"),
        app_commands.Choice(name="Orange", value="Orange"),
        app_commands.Choice(name="Blue", value="Blue"),
        app_commands.Choice(name="Yellow", value="Yellow"),
        app_commands.Choice(name="Pink", value="Pink"),
        app_commands.Choice(name="Green", value="Green"),
        app_commands.Choice(name="Purple", value="Purple"),
    ])
    async def craps(self, ctx: commands.Context, solo: Optional[bool] = False, mode: str = "betting", buy_in: Optional[int] = None, color: Optional[str] = None):
        betting_mode = str(mode).lower() == "betting"
        if betting_mode:
            if buy_in is None or int(buy_in) <= 0:
                await ctx.send("Buy in XP is required for Betting mode.")
                return
        if ctx.channel is None:
            await ctx.send("Run in a channel.")
            return
        ch_id = ctx.channel.id
        if ch_id in self.craps_sessions:

            await ctx.send("A Craps game is already running in this channel.")
            return
            
        member = ctx.author
        if not isinstance(member, discord.Member):
            await ctx.send("Could not get member information. Please try again in a guild channel.", ephemeral=True)
            return
            
        session = CrapsSession(self.bot, ch_id, bool(solo), betting_mode, int(buy_in or 0), member, host_dice_color=color)
        self.craps_sessions[ch_id] = session
        embed: discord.Embed = await session._build_embed()
        msg = await ctx.send(embed=embed, view=session)
        session.message = msg

    @commands.hybrid_command(name="holdem", description="Play Texas Hold'em with Pet XP betting")
    @app_commands.describe(
        solo="If true, only you play",
        buy_in="Buy in XP for bankroll",
        bots="Number of AI bots (0-3)"
    )
    @app_commands.choices(bots=[
        app_commands.Choice(name="0", value=0),
        app_commands.Choice(name="1", value=1),
        app_commands.Choice(name="2", value=2),
        app_commands.Choice(name="3", value=3),
    ])
    async def holdem(self, ctx: commands.Context, solo: Optional[bool] = False, buy_in: Optional[int] = None, bots: int = 0):
        if buy_in is None or int(buy_in) <= 0:
            await ctx.send("Buy in XP is required.")
            return
        if ctx.channel is None:
            await ctx.send("Run in a channel.")
            return
        if ctx.guild is None:
            await ctx.send("This command can only be used in a guild channel.")
            return
        member = ctx.author
        if not isinstance(member, discord.Member):
            await ctx.send("Could not get member information. Please try again in a guild channel.")
            return
        ch_id = ctx.channel.id
        if ch_id in self.holdem_sessions:
            await ctx.send("A Hold'em game is already running in this channel.")
            return
            
        session = HoldemSession(self.bot, ch_id, bool(solo), member, bots=bots)
        self.holdem_sessions[ch_id] = session
        
        embed = session._build_table_embed()
        msg = await ctx.send(embed=embed, view=session)
        session.message = msg
        if ctx.interaction:
            await session.start_hand(ctx.interaction)
        else:
            await ctx.send("This command must be used as a slash command to start the game.", ephemeral=True)

    @commands.hybrid_command(name="blackjack", description="Play Blackjack with Pet XP betting or for fun")
    @app_commands.describe(
        solo="If true, only you play",
        mode="Choose Betting or Fun",
        buy_in="Buy in XP for Betting mode",
        bots="Number of AI players (0-3)"
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="Betting", value="betting"),
        app_commands.Choice(name="Fun", value="fun"),
    ])
    @app_commands.choices(bots=[
        app_commands.Choice(name="None", value=0),
        app_commands.Choice(name="1 Bot", value=1),
        app_commands.Choice(name="2 Bots", value=2),
        app_commands.Choice(name="3 Bots", value=3),
    ])
    async def blackjack(self, ctx: commands.Context, solo: Optional[bool] = False, mode: str = "betting", buy_in: Optional[int] = None, bots: int = 0):
        betting_mode = str(mode).lower() == "betting"
        if betting_mode:
            if buy_in is None or int(buy_in) <= 0:
                await ctx.send("Buy in XP is required for Betting mode.")
                return
        if ctx.channel is None:
            await ctx.send("Run in a channel.")
            return
        if ctx.guild is None:
            await ctx.send("This command can only be used in a guild channel.")
            return
        member = ctx.author
        if not isinstance(member, discord.Member):
            await ctx.send("Could not get member information. Please try again in a guild channel.")
            return
        ch_id = ctx.channel.id
        if ch_id in self.blackjack_sessions:
            await ctx.send("A blackjack game is already running in this channel.")
            return
        session = BlackjackSession(self.bot, ch_id, bool(solo), betting_mode, int(buy_in or 0), member, bot_count=bots)
        self.blackjack_sessions[ch_id] = session
        embed = session._build_table_embed()
        msg = await ctx.send(embed=embed, view=session)
        session.message = msg
        await session.start_round(getattr(ctx, "interaction", None))
    
    @app_commands.command(name="quest", description="Embark on a quest with your pet!")
    @app_commands.describe(location="The location of the quest", difficulty="The difficulty of the quest")
    @app_commands.choices(location=[app_commands.Choice(name=loc, value=loc) for loc in locations])
    async def quest(self, ctx: discord.Interaction, location: str, difficulty: Literal["Apprentice", "Journeyman", "Senior"]):
        pet = await user_data_manager.get_pet_data_async(str(ctx.user.id), ctx.user.display_name)

        if not pet:
            await ctx.response.send_message("You don't have a pet to go on a quest with!", ephemeral=True)
            return

        quest_data = generate_or_load_quest(location, difficulty)
        if not quest_data or 'stages' not in quest_data or not quest_data['stages']:
            await ctx.response.send_message("Could not generate or load a quest. Please try again later.", ephemeral=True)
            return

        view = QuestView(self.bot, pet, quest_data, difficulty, str(ctx.user.id), location)
        await view.start_quest(ctx)  # Pass the interaction context directly

    async def tournament_size_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for tournament size selection"""
        sizes = [
            ("4 Players (2 rounds)", "4"),
            ("8 Players (3 rounds)", "8"),
            ("16 Players (4 rounds)", "16")
        ]
        return [
            app_commands.Choice(name=name, value=value)
            for name, value in sizes
            if current.lower() in name.lower()
        ][:25]
    
    @app_commands.command(name="tournament", description="Create a pet tournament bracket")
    @app_commands.describe(
        size="Tournament size (4, 8, or 16 players)",
        participants="Optional: Mention specific users to invite (if none, auto-fills with eligible users)"
    )
    @app_commands.autocomplete(size=tournament_size_autocomplete)
    async def tournament(self, interaction: discord.Interaction, size: str, participants: Optional[str] = None):
        """Create a tournament with the specified size and optional participant mentions"""
        # Validate size
        if size not in ["4", "8", "16"]:
            return await interaction.response.send_message(
                "❌ Invalid tournament size! Please choose 4, 8, or 16 players.",
                ephemeral=True
            )
        
        try:
            # Check if user has a pet
            if not await self.pet_system.get_user_pet(interaction.user.id):
                return await interaction.response.send_message(
                    "❌ You need a pet to create tournaments! Use `/pet_shop` to get started.",
                    ephemeral=True
                )
            
            # Ensure interaction.user is a Member
            if not isinstance(interaction.user, discord.Member):
                return await interaction.response.send_message(
                    "❌ This command can only be used in a guild channel.",
                    ephemeral=True
                )
            creator_member: discord.Member = interaction.user

            # Ensure interaction.channel is a TextChannel
            if not isinstance(interaction.channel, discord.TextChannel):
                return await interaction.response.send_message(
                    "❌ Tournaments can only be created in text channels.",
                    ephemeral=True
                )
            channel: discord.TextChannel = interaction.channel

            tournament_size = TournamentSize(int(size))
            tournament = Tournament(self.bot, creator_member, tournament_size, channel)
            
            # Parse mentioned participants if provided
            mentioned_users = []
            if participants:
                if interaction.guild is None:
                    return await interaction.response.send_message(
                        "❌ Cannot mention participants outside of a guild.",
                        ephemeral=True
                    )
                user_ids = re.findall(r'<@!?(\d+)>', participants)
                for user_id in user_ids:
                    member = interaction.guild.get_member(int(user_id))
                    if member and not member.bot:
                        mentioned_users.append(member)
            
            # Add mentioned users to tournament
            added_users = []
            for user in mentioned_users:
                # Check if user has a pet
                if await self.pet_system.get_user_pet(user.id):
                    if tournament.add_participant(user):
                        added_users.append(user)
            
            # Add the organizer if not already added
            if creator_member not in tournament.participants:
                tournament.add_participant(creator_member)
                added_users.append(creator_member)
            
            # Create tournament view and send message
            view = TournamentView(tournament)
            embed = view.create_tournament_embed()
            
            if added_users:
                mention_text = ", ".join([user.mention for user in added_users])
                embed.add_field(
                    name="Pre-registered Participants",
                    value=mention_text,
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Error in tournament command: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An error occurred while creating the tournament. Please try again.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ An error occurred while creating the tournament. Please try again.",
                    ephemeral=True
                )

async def setup(bot: commands.Bot):
    pet_system = PetSystem(bot)
    await bot.add_cog(PetCommandsCog(bot, pet_system))
