import discord
import random
import asyncio
import logging
from typing import List, Dict, Tuple, Optional

from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.pet_brain import LootCalculator

logger = logging.getLogger(__name__)
from Systems.Functions import emoji as emoji_mod

VERY_EASY_EMOJIS = emoji_mod.category_mentions("Pet Type")
EASY_EMOJIS = emoji_mod.category_mentions("Slots")
MEDIUM_EMOJIS = emoji_mod.category_mentions("Stats")
HARD_EMOJIS = emoji_mod.category_mentions("Elements")
VERY_HARD_EMOJIS = emoji_mod.category_mentions("Pets")

# Payout ratios (net winnings multiplier on bet)
PAYOUTS: Dict[str, Dict[str, float]] = {
    "very_easy": {"three": 8.0, "two": 0.5},
    "easy": {"three": 15.0, "two": 7.0/9.0},
    "medium": {"three": 35.0, "two": 4.0/3.0},
    "hard": {"three": 168.0, "two": 3.33},
    "very_hard": {"three": 1061.0, "two": 33.0/67.0},
    "insanity": {"three_both": 2500000000.0, "two_both": 220000.0, "combination": 215000.0},
}

def get_emojis_for_difficulty(difficulty: str) -> List[str]:
    d = str(difficulty).lower()
    if d == "very_easy":
        return VERY_EASY_EMOJIS
    if d == "easy":
        return EASY_EMOJIS
    if d == "medium":
        return MEDIUM_EMOJIS
    if d == "hard":
        return HARD_EMOJIS
    return VERY_HARD_EMOJIS

def compute_total_xp(pet: Dict) -> int:
    lvl = int(pet.get("level", 1))
    rem = int(pet.get("experience", 0))
    return int(LootCalculator.get_total_experience_for_level(lvl)) + int(rem)


class SlotMachineView(discord.ui.View):
    """Interactive slot machine view with spinning animation (Pet XP gambling)."""
    
    def __init__(self, bot, user: discord.Member, difficulty: str, xp_bet: int, mode: str = "betting"):
        super().__init__(timeout=300)
        self.bot = bot
        self.user = user
        self.difficulty = difficulty
        self.bet = int(xp_bet)
        self.slot_emojis = get_emojis_for_difficulty(difficulty)
        self.message = None
        self.game_finished = False
        self.starting_total_xp = 0
        self.fun_mode = str(mode).lower() == "fun"
    
    async def on_timeout(self):
        """Handle view timeout."""
        for item in self.children:
            item.disabled = True
        if self.message and not self.game_finished:
            try:
                timeout_embed = discord.Embed(
                    title="⏰ Slots Timed Out",
                    description="The Pet XP slots view has been reset due to inactivity.",
                    color=discord.Color.orange()
                )
                await self.message.edit(embed=timeout_embed, view=self)
            except:
                pass
    
    @discord.ui.button(label="SPIN", style=discord.ButtonStyle.success, emoji=emoji_mod.get_partial('Casino'))
    async def spin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle spin button click."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(f"{emoji_mod.mention('Deny')} This isn't your slot machine!", ephemeral=True)
            return
        
        button.disabled = True
        await interaction.response.edit_message(view=self)
        await self.perform_spin(interaction)
    
    async def perform_spin(self, interaction: discord.Interaction):
        """Perform the slot machine spin animation with 6 random reels (Pet XP)."""
        # Ensure message reference is properly set
        if not self.message:
            self.message = await interaction.original_response()
        
        # Load current total XP
        pet = await user_data_manager.get_pet_data_async(str(self.user.id), self.user.display_name)
        if not pet:
            await interaction.followup.send(f"{emoji_mod.mention('Deny')} You need a pet to play slots. Use `/pet_shop` first.", ephemeral=True)
            return
        self.starting_total_xp = compute_total_xp(pet)
            
        casino_emoji = emoji_mod.mention('Casino') or "🎰"
        embed = discord.Embed(
            title=f"{casino_emoji} PET XP SLOTS - {self.difficulty.upper()} {casino_emoji}",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow()
        )
        
        embed.set_author(
            name=f"{self.user.display_name} is spinning!",
            icon_url=self.user.display_avatar.url
        )
        
        # 6-stage spinning animation with 1.5-second intervals
        animation_stages = [
            f"**{casino_emoji} STAGE 1: Spinning... {casino_emoji}**",
            "**⚡ STAGE 2: Reels turning! ⚡**",
            "**🎯 STAGE 3: Building momentum... 🎯**",
            "**🐢 STAGE 4: Slowing down... 🐢**",
            "**🔮 STAGE 5: Finalizing... 🔮**",
            "**🌟 STAGE 6: Revealing result! 🌟**"
        ]
        
        is_insanity = self.difficulty.lower() == "insanity"
        element_symbol = ""
        species_symbol = ""
        element_reel_set: List[str] = []
        species_reel_set: List[str] = []
        if is_insanity:
            element = str(pet.get("element", "fire")).lower()
            species = str(pet.get("species", "Cat"))
            element_symbol = emoji_mod.mention(element) or "⚡️"
            species_symbol = emoji_mod.mention(species) or "🐈"
            element_reel_set = emoji_mod.category_mentions("Elements")
            species_reel_set = emoji_mod.category_mentions("Pets")
        
        for stage_num, status in enumerate(animation_stages):
            try:
                embed.clear_fields()
                if self.fun_mode:
                    embed.add_field(name="📈 Mode", value="**Fun (no XP change)**", inline=True)
                else:
                    embed.add_field(name="📈 XP Bet", value=f"**{self.bet}** XP", inline=True)
                embed.add_field(name="🧮 Total XP", value=f"**{self.starting_total_xp}** XP", inline=True)
                embed.add_field(name="🎲 Animation", value=f"**Stage {stage_num + 1}/6**", inline=True)
                
                casino_emoji = emoji_mod.mention('Casino') or "🎰"
                if is_insanity:
                    current_slots_elements = [random.choice(element_reel_set) for _ in range(3)]
                    current_slots_species = [random.choice(species_reel_set) for _ in range(3)]
                    elements_display = f"{casino_emoji}  {current_slots_elements[0]}  {current_slots_elements[1]}  {current_slots_elements[2]}  {casino_emoji}"
                    species_display = f"{casino_emoji}  {current_slots_species[0]}  {current_slots_species[1]}  {current_slots_species[2]}  {casino_emoji}"
                    embed.add_field(name="🔮 Emoji Reel", value=elements_display, inline=False)
                    embed.add_field(name="🐾 Pets Reel", value=species_display, inline=False)
                    embed.add_field(name="🧮 Your Match Targets", value=f"Element {element_symbol} • Pet {species_symbol}", inline=False)
                else:
                    current_slots = [random.choice(self.slot_emojis) for _ in range(3)]
                    slots_display = f"{casino_emoji}  {current_slots[0]}  {current_slots[1]}  {current_slots[2]}  {casino_emoji}"
                    embed.add_field(name="🎰 SLOT REELS", value=slots_display, inline=False)
                
                embed.add_field(name=f"{casino_emoji} Status", value=status, inline=False)
                
                progress_bar = (emoji_mod.mention('Approve') or "🟩") * (stage_num + 1) + (emoji_mod.mention('Pending') or "⬜") * (6 - stage_num - 1)
                elapsed_time = (stage_num + 1) * 1.5
                embed.set_footer(text=f"Stage {stage_num + 1}/6 • {elapsed_time:.1f}s", icon_url=self.bot.user.display_avatar.url)
                
                await self.message.edit(embed=embed, view=self)
                await asyncio.sleep(1.5)
            except discord.HTTPException as e:
                if e.status == 429:
                    await asyncio.sleep(0.1)
                    continue
                else:
                    break
            except Exception:
                break
        
        await asyncio.sleep(0.5)
        if is_insanity:
            await self.show_results_insanity(element_reel_set, species_reel_set, element_symbol, species_symbol)
        else:
            await self.show_results(self.slot_emojis)
    
    async def show_results(self, slot_emojis: List[str]):
        """Show the final results of the slot machine spin with bigger emojis and apply Pet XP changes."""
        final_slots = [random.choice(slot_emojis) for _ in range(3)]
        
        casino_emoji = emoji_mod.mention('Casino') or "🎰"
        # Make final reels appear much bigger
        slots_display = f"{casino_emoji}  {final_slots[0]}  {final_slots[1]}  {final_slots[2]}  {casino_emoji}"
        
        # Check win conditions
        all_match = len(set(final_slots)) == 1
        two_match = len(set(final_slots)) == 2
        
        # Calculate XP winnings using payout ratios
        winnings = 0
        payouts = PAYOUTS.get(self.difficulty.lower(), PAYOUTS.get("very_easy", {"three": 0.0, "two": 0.0}))
        if all_match:
            winnings = int(self.bet * payouts["three"])
        elif two_match:
            winnings = int(self.bet * payouts["two"])
        
        # Create result embed with bigger emoji presentation
        embed = discord.Embed(
            title=f"{casino_emoji} PET XP SLOTS - {self.difficulty.upper()} {casino_emoji}",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow()
        )
        
        embed.set_author(
            name=f"{self.user.display_name}'s Results",
            icon_url=self.user.display_avatar.url
        )
        
        if self.fun_mode:
            embed.add_field(name="📈 Mode", value="**Fun (no XP change)**", inline=True)
        else:
            embed.add_field(name="📈 XP Bet", value=f"**{self.bet}** XP", inline=True)
        embed.add_field(name="🧮 FINAL REELS", value=slots_display, inline=False)
        if winnings > 0:
            embed.add_field(name="🏆 XP Won", value=f"**{winnings}** XP", inline=True)
            embed.add_field(name="✨ Result", value=f"**{'JACKPOT!' if all_match else 'WIN!'}**", inline=False)
        else:
            if not self.fun_mode:
                embed.add_field(name="💸 Lost", value=f"**{self.bet}** XP", inline=True)
            embed.add_field(name="😢 Result", value="**Better luck next time!**", inline=False)
        
        # Update game state
        self.game_finished = True
        
        # Apply XP delta to pet and update slot stats
        try:
            # Prepare parallel tasks
            tasks = []
            xp_delta = 0
            winnings_val = 0

            if not self.fun_mode:
                xp_delta = winnings if winnings > 0 else -self.bet
                winnings_val = xp_delta
                
                # Task 1: XP Change
                tasks.append(LootCalculator.apply_xp_change(self.user.id, xp_delta, source="slots"))
                
                # Task 2: Loot
                if winnings > 0:
                    tasks.append(LootCalculator.award_gambling_loot(self.user.id, None, self.difficulty))
                else:
                    tasks.append(asyncio.sleep(0))
            else:
                tasks.append(asyncio.sleep(0))
                tasks.append(asyncio.sleep(0))

            # Task 3: Stats
            try:
                extra = {}
                key = self.difficulty.lower()
                extra["games_by_difficulty"] = {key: 1}
                
                if not self.fun_mode:
                    if winnings > 0:
                        extra["xp_won_by_difficulty"] = {key: winnings}
                        if all_match:
                            extra["three_matches_won"] = 1
                        elif two_match:
                            extra["two_matches_won"] = 1
                
                tasks.append(user_data_manager.update_pet_gambling_stats(
                    str(self.user.id),
                    "slots",
                    winnings_val,
                    bet_amount=self.bet if not self.fun_mode else 0,
                    extra_data=extra
                ))
            except Exception as e:
                print(f"Error preparing slot stats: {e}")
                tasks.append(asyncio.sleep(0))

            # Execute all I/O in parallel
            results = await asyncio.gather(*tasks)
            
            xp_res = results[0]
            loot_res = results[1]
            # stats_res = results[2] (not needed)

            if not self.fun_mode and isinstance(xp_res, tuple) and xp_res[0]:
                result = xp_res[1]
                new_total = result.get("new_total_xp", 0)
                embed.add_field(name="🧮 New Total XP", value=f"**{new_total}** XP", inline=True)
                
                if result.get("new_level", 0) > result.get("old_level", 0):
                    embed.add_field(name="🎉 Level Up!", value=f"{result['old_level']} ➡️ {result['new_level']}", inline=False)
            
            if loot_res and isinstance(loot_res, list):
                for msg in loot_res:
                    embed.add_field(name="💎 Loot Found", value=msg, inline=False)
                    
        except Exception as e:
            print(f"Error applying XP change or saving slot stats: {e}")
        
        # Show play again button
        play_again_view = PlayAgainView(self.bot, self.user, self.difficulty)
        await self.message.edit(embed=embed, view=play_again_view)
    
    async def show_results_insanity(self, element_reel_set: List[str], species_reel_set: List[str], element_symbol: str, species_symbol: str):
        """Show final results for Insanity difficulty with dual reels and pet-matched payouts."""
        emoji_slots = [random.choice(element_reel_set) for _ in range(3)]
        pet_slots = [random.choice(species_reel_set) for _ in range(3)]
        
        casino_emoji = emoji_mod.mention('Casino') or "🎰"
        elements_display = f"{casino_emoji}  {emoji_slots[0]}  {emoji_slots[1]}  {emoji_slots[2]}  {casino_emoji}"
        species_display = f"{casino_emoji}  {pet_slots[0]}  {pet_slots[1]}  {pet_slots[2]}  {casino_emoji}"
        
        element_matches = sum(1 for s in emoji_slots if s == element_symbol)
        species_matches = sum(1 for s in pet_slots if s == species_symbol)
        
        winnings = 0
        result_text = "Better luck next time!"
        payouts = PAYOUTS.get("insanity", {})
        if element_matches == 3 and species_matches == 3:
            winnings = int(self.bet * float(payouts.get("three_both", 0.0)))
            result_text = "INSANITY JACKPOT!"
        elif (element_matches == 3 and species_matches == 2) or (element_matches == 2 and species_matches == 3):
            winnings = int(self.bet * float(payouts.get("combination", 0.0)))
            result_text = "MEGA WIN!"
        elif element_matches == 2 and species_matches == 2:
            winnings = int(self.bet * float(payouts.get("two_both", 0.0)))
            result_text = "DUAL WIN!"
        
        embed = discord.Embed(
            title=f"{casino_emoji} PET XP SLOTS - {self.difficulty.upper()} {casino_emoji}",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=f"{self.user.display_name}'s Results", icon_url=self.user.display_avatar.url)
        if self.fun_mode:
            embed.add_field(name="📈 Mode", value="**Fun (no XP change)**", inline=True)
        else:
            embed.add_field(name="📈 XP Bet", value=f"**{self.bet}** XP", inline=True)
        embed.add_field(name="🔮 Emoji Reel", value=elements_display, inline=False)
        embed.add_field(name="🐾 Pets Reel", value=species_display, inline=False)
        embed.add_field(name="🎯 Your Match Targets", value=f"Element {element_symbol} • Pet {species_symbol}", inline=False)
        
        if winnings > 0:
            embed.add_field(name="🏆 XP Won", value=f"**{winnings}** XP", inline=True)
            embed.add_field(name="✨ Result", value=f"**{result_text}**", inline=False)
        else:
            if not self.fun_mode:
                embed.add_field(name="💸 Lost", value=f"**{self.bet}** XP", inline=True)
            embed.add_field(name="😢 Result", value=f"**{result_text}**", inline=False)
        
        self.game_finished = True
        
        try:
            xp_delta = winnings if winnings > 0 else -self.bet
            
            # Prepare stats update
            extra = {}
            extra["games_by_difficulty"] = {"insanity": 1}
            winnings_val = 0
            if not self.fun_mode:
                winnings_val = xp_delta
                if winnings > 0:
                    extra["xp_won_by_difficulty"] = {"insanity": winnings}
                    if element_matches == 3 and species_matches == 3:
                        extra["insanity_jackpot_won"] = 1

            # Prepare parallel tasks
            tasks = []
            
            # 1. Update Gambling Stats
            tasks.append(user_data_manager.update_pet_gambling_stats(
                str(self.user.id),
                "slots",
                winnings_val,
                bet_amount=self.bet if not self.fun_mode else 0,
                extra_data=extra
            ))
            
            # 2. XP Change
            if not self.fun_mode:
                tasks.append(LootCalculator.apply_xp_change(self.user.id, xp_delta, source="slots"))
            else:
                tasks.append(asyncio.sleep(0))
                
            # 3. Loot
            if not self.fun_mode and winnings > 0:
                tasks.append(LootCalculator.award_gambling_loot(self.user.id, None, self.difficulty))
            else:
                tasks.append(asyncio.sleep(0))
                
            # Execute
            results = await asyncio.gather(*tasks)
            
            # xp_res = results[1]
            xp_res = results[1]
            loot_res = results[2]
            
            if not self.fun_mode and isinstance(xp_res, tuple) and xp_res[0]:
                result = xp_res[1]
                new_total = result.get("new_total_xp", 0)
                embed.add_field(name="🧮 New Total XP", value=f"**{new_total}** XP", inline=True)
                if result.get("new_level", 0) > result.get("old_level", 0):
                    level_up_emoji = emoji_mod.mention('LevelUp') or "🎉"
                    embed.add_field(name=f"{level_up_emoji} Level Up!", value=f"{result['old_level']} ➡️ {result['new_level']}", inline=False)
                    
            if loot_res and isinstance(loot_res, list):
                for msg in loot_res:
                    embed.add_field(name="💎 Loot Found", value=msg, inline=False)
                    
        except Exception as e:
            print(f"Error in slots insanity I/O: {e}")
        
        play_again_view = PlayAgainView(self.bot, self.user, self.difficulty)
        await self.message.edit(embed=embed, view=play_again_view)

class PlayAgainView(discord.ui.View):
    """View for playing slots again with difficulty selection."""
    
    def __init__(self, bot, user: discord.Member, difficulty: str):
        super().__init__(timeout=180)
        self.bot = bot
        self.user = user
        self.difficulty = difficulty
        self.message = None
    
    @discord.ui.button(label="Play Again", style=discord.ButtonStyle.success, emoji=emoji_mod.get_partial('Casino'))
    async def play_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle play again button for Pet XP slots."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(f"{emoji_mod.mention('Deny')} This isn't your game!", ephemeral=True)
            return
        
        # Create difficulty select menu
        difficulty_select = discord.ui.Select(
            placeholder="Choose Difficulty",
            options=[
                discord.SelectOption(label="Very Easy", description="Pet Type Style", emoji="🟩"),
                discord.SelectOption(label="Easy", description="Gambling (Slots) Style", emoji="🟢"),
                discord.SelectOption(label="Medium", description="Stats Style", emoji="🟡"),
                discord.SelectOption(label="Hard", description="Elements Style", emoji="🟠"),
                discord.SelectOption(label="Very Hard", description="Pets Style", emoji="🔴"),
                discord.SelectOption(label="Insanity", description="Dual Reels: Elements + Pets (pet-matched wins)", emoji="🟣"),
            ]
        )
        
        async def difficulty_callback(interaction: discord.Interaction):
            difficulty = difficulty_select.values[0].lower()
            
            # Defer the interaction to prevent timeout
            await interaction.response.defer()
            
            # Pet XP betting modal
            modal = discord.ui.Modal(title="Place Your XP Bet")
            bet_input = discord.ui.TextInput(
                label="Bet XP",
                placeholder="Enter XP (10-100000, must be ≤ your total XP)",
                min_length=1,
                max_length=6
            )
            modal.add_item(bet_input)
            
            async def modal_callback(interaction: discord.Interaction):
                try:
                    bet = int(str(bet_input.value or "0").strip())
                except Exception:
                    await interaction.followup.send("❌ Bet must be a number.", ephemeral=True)
                    return
                pet = await user_data_manager.get_pet_data_async(str(self.user.id), self.user.display_name)
                if not pet:
                    await interaction.followup.send("❌ You need a pet to play slots. Use `/pet_shop` first.", ephemeral=True)
                    return
                total_xp = compute_total_xp(pet)
                if bet < 10 or bet > 100000 or bet > total_xp:
                    await interaction.followup.send(f"❌ Bet must be between 10 and 100000 XP and ≤ your total XP ({total_xp}).", ephemeral=True)
                    return
                view = SlotMachineView(self.bot, self.user, difficulty, bet, mode="betting")
                embed = discord.Embed(
                    title=f"🎰 PET XP SLOTS - {difficulty.upper()} 🎰",
                    description="Press 🎰 SPIN to start the animation and reveal your result.",
                    color=discord.Color.gold()
                )
                embed.add_field(name="📈 XP Bet", value=f"**{bet}** XP", inline=True)
                await self.message.edit(embed=embed, view=view)
            modal.on_submit = modal_callback
            await interaction.followup.send_modal(modal)
        
        difficulty_select.callback = difficulty_callback
        self.add_item(difficulty_select)
        
        try:
            await interaction.followup.send("🎛️ Select a difficulty and place your XP bet.", ephemeral=True)
        except Exception:
            pass
    
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass
