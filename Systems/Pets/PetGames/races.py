import discord
from discord.ext import commands
import asyncio
import random
import logging
from typing import Any, Dict, List, Optional, Tuple, cast

from Systems.Functions.user_data_manager import user_data_manager
from Systems.Functions import emoji as emoji_mod
from Systems.Pets.Logic.pet_brain import LootCalculator

def _pet_speed(pet: Dict) -> float:
    dex = float(pet.get("DEX", 0))
    ene = float(pet.get("ENE", 0))
    hap = float(pet.get("HAP", 0))
    
    rand_dex = random.uniform(0.5, 1.5)
    rand_ene = random.uniform(0.5, 1.5)
    rand_hap = random.uniform(0.5, 1.5)
    
    speed = (dex * rand_dex) * (ene * rand_ene) * (hap * rand_hap) / 3.0
    return speed

async def _deduct_xp(user: discord.Member, amount: int, pet_data: Optional[Dict] = None) -> bool:
    pet: Optional[Dict[str, Any]]
    if pet_data:
        pet = pet_data
    else:
        pet = await user_data_manager.get_pet_data_async(str(user.id), user.display_name)
    
    if not pet:
        return False
    
    # Check balance
    lvl = int(pet.get("level", 1))
    current_xp = int(pet.get("experience", 0))
    base_xp = LootCalculator.get_total_experience_for_level(lvl)
    total = base_xp + current_xp
    
    if amount < 0 or amount > total:
        return False
        
    # Apply deduction via LootCalculator
    await LootCalculator.apply_xp_change(user.id, -amount, source="race_bet")
    return True

async def _add_xp(user: discord.Member, amount: int) -> bool:
    await LootCalculator.apply_xp_change(user.id, amount, source="race_win")
    return True

def _species_emoji(species: str) -> str:
    m = emoji_mod.mention(species)
    return m or species

def _random_species_mention() -> Tuple[str, str]:
    names = emoji_mod.CATEGORIES.get("Pets", [])
    if not names:
        return "Unknown", "🐾"
    name = random.choice(names)
    return name, emoji_mod.mention(name) or name

class BetModal(discord.ui.Modal, title="Enter Bet"):
    bet_input: discord.ui.TextInput = discord.ui.TextInput(label="Bet XP", placeholder="Enter XP", min_length=1, max_length=8)

    def __init__(self, parent_view: 'RaceSession', pet: Dict, interaction_user: discord.Member):
        super().__init__()
        self.parent_view = parent_view
        self.pet = pet
        self.interaction_user = interaction_user
        self.add_item(self.bet_input)

    async def on_submit(self, inter: discord.Interaction):
        try:
            amt = int(str(self.bet_input.value or "0").strip())
        except Exception:
            await inter.response.send_message("Invalid bet.", ephemeral=True)
            return
        ok = await _deduct_xp(self.interaction_user, amt, pet_data=self.pet)
        if not ok:
            await inter.response.send_message("Bet exceeds available XP.", ephemeral=True)
            return
        self.parent_view.bets[self.interaction_user.id] = amt
        if self.parent_view.message:
            await self.parent_view.message.edit(embed=self.parent_view._lobby_embed(), view=self.parent_view)
        await inter.response.send_message("Bet placed.", ephemeral=True)

class RaceSession(discord.ui.View):
    def __init__(self, bot: commands.Bot, owner: discord.Member, simulation: bool, difficulty: Optional[str], mode_betting: bool, bet_amount: Optional[int]):
        super().__init__(timeout=900)
        self.bot = bot
        self.owner = owner
        self.simulation = simulation
        self.difficulty = (difficulty or "").lower()
        self.mode_betting = mode_betting
        self.initial_bet = int(bet_amount or 0)
        self.message: Optional[discord.Message] = None
        self.running = False
        self.finished = False
        self.cashed_out = False
        self.tracks: Dict[int, List[str]] = {}
        self.progress: Dict[int, int] = {}
        self.accum: Dict[int, float] = {}
        self.species_emo: Dict[int, str] = {}
        self.pets: Dict[int, Dict] = {}
        self.bets: Dict[int, int] = {}
        self.participants: List[int] = []
        self.win_streak = 0
        self.pending_xp = 0
        self.pending_keys: List[str] = []
        self.winner_id: Optional[int] = None
        self.finish_order: List[int] = []
        self.finish_times: Dict[int, int] = {}
        self.loop_count = 0
        self.max_segments = 10
        self.segment_threshold = 5.0
        self.task: Optional[asyncio.Task] = None

        # --- Buttons ---
        self.join_button_item = discord.ui.Button(label="Join", style=discord.ButtonStyle.success)
        self.join_button_item.callback = self.join_button
        
        self.start_button_item = discord.ui.Button(label="Start", style=discord.ButtonStyle.primary)
        self.start_button_item.callback = self.start_button

        self.leave_button_item = discord.ui.Button(label="Leave", style=discord.ButtonStyle.danger)
        self.leave_button_item.callback = self.leave_button

        self.continue_button_item = discord.ui.Button(label="Continue", style=discord.ButtonStyle.success, row=1)
        self.continue_button_item.callback = self.continue_button

        self.cash_out_button_item = discord.ui.Button(label="Cash Out", style=discord.ButtonStyle.primary, row=1)
        self.cash_out_button_item.callback = self.cash_out_button

        self.play_again_button_item = discord.ui.Button(label="Play Again", style=discord.ButtonStyle.secondary, row=1)
        self.play_again_button_item.callback = self.play_again_button

        self._init_session()
        self._update_view()

    def _update_view(self):
        self.clear_items()
        if not self.running and not self.finished:  # Lobby state
            if not self.simulation:
                self.add_item(self.join_button_item)
                self.add_item(self.start_button_item)
                self.add_item(self.leave_button_item)
        elif self.finished:
            if self.cashed_out:
                self.add_item(self.play_again_button_item)
            elif self.winner_id == self.owner.id:  # Win state
                self.add_item(self.continue_button_item)
                self.add_item(self.cash_out_button_item)
            else:  # Loss state
                self.add_item(self.play_again_button_item)

    def _init_session(self):
        self.participants = [self.owner.id]
        track_char = emoji_mod.mention('BlackSquare') or "➖"
        self.tracks[self.owner.id] = [track_char] * self.max_segments
        self.progress[self.owner.id] = 0
        self.accum[self.owner.id] = 0.0

    async def _load_user_pet(self, user: discord.Member) -> Optional[Dict]:
        pet = await user_data_manager.get_pet_data_async(str(user.id), user.display_name)
        return pet

    async def _setup_competitors(self) -> bool:
        if self.simulation:
            pet = await self._load_user_pet(self.owner)
            if not pet:
                return False
            species = str(pet.get("species", "Cat"))
            self.species_emo[self.owner.id] = _species_emoji(species)
            self.pets[self.owner.id] = pet
            if self.mode_betting and self.initial_bet > 0:
                if self.win_streak == 0:  # Only deduct XP for the first race in a streak
                    ok = await _deduct_xp(self.owner, self.initial_bet)
                    if not ok:
                        return False
                    self.bets[self.owner.id] = self.initial_bet
            
            diff_mults = {"apprentice": 0.8, "journeyman": 1.0, "senior": 1.2}
            diff_mult = diff_mults.get(self.difficulty, 1.0)
            track_char = emoji_mod.mention('BlackSquare') or "➖"
            for _ in range(3):
                name, em = _random_species_mention()
                bot_id = random.randint(10_000_000, 99_999_999)
                self.participants.append(bot_id)
                self.tracks[bot_id] = [track_char] * self.max_segments
                self.progress[bot_id] = 0
                self.accum[bot_id] = 0.0
                self.species_emo[bot_id] = em
                pd = {
                    "DEX": max(1, int(float(self.pets[self.owner.id].get("DEX", 0)) * diff_mult + random.uniform(-2, 2))),
                    "ENE": max(1, int(float(self.pets[self.owner.id].get("ENE", 0)) * diff_mult + random.uniform(-2, 2))),
                    "HAP": max(1, int(float(self.pets[self.owner.id].get("HAP", 0)) * diff_mult + random.uniform(-2, 2))),
                    "species": name,
                }
                self.pets[bot_id] = pd
            return True
        else:
            pet = await self._load_user_pet(self.owner)
            if not pet:
                return False
            species = str(pet.get("species", "Cat"))
            self.species_emo[self.owner.id] = _species_emoji(species)
            self.pets[self.owner.id] = pet
            if self.mode_betting and self.initial_bet > 0:
                ok = await _deduct_xp(self.owner, self.initial_bet)
                if not ok:
                    return False
                self.bets[self.owner.id] = self.initial_bet
            return True

    def _calculate_average_pet_level(self) -> float:
        total_level = 0
        num_pets = 0
        for pet_data in self.pets.values():
            total_level += int(pet_data.get("level", 1))
            num_pets += 1
        return total_level / num_pets if num_pets > 0 else 1.0

    def _lobby_embed(self) -> discord.Embed:
        e = discord.Embed(title="Race Lobby", color=discord.Color.blurple(), timestamp=discord.utils.utcnow())
        lines: List[str] = []
        for uid in self.participants:
            u = self.bot.get_user(uid)
            if u:
                lines.append(f"{u.mention}")
        e.description = "\n".join(lines) if lines else "Waiting for racers"
        return e

    def _race_embed(self) -> discord.Embed:
        e = discord.Embed(title="Race", color=discord.Color.green(), timestamp=discord.utils.utcnow())
        track_char = emoji_mod.mention('BlackSquare') or "➖"
        start_char = emoji_mod.mention('start') or "▶️"
        finish_char = emoji_mod.mention('finish') or "🏁"
        for uid in self.participants:
            em = self.species_emo.get(uid) or "🐾"
            prog = int(self.progress.get(uid, 0))
            pos = min(prog, self.max_segments - 1)
            left = track_char * pos
            right = track_char * (self.max_segments - 1 - pos)
            track = f"{start_char}{left}{em}{right}{finish_char}"
            user_obj = self.bot.get_user(uid)
            name = "Bot" if not user_obj else user_obj.display_name
            pet = self.pets.get(uid, {})
            dex = float(pet.get("DEX", 0))
            ene = float(pet.get("ENE", 0))
            hap = float(pet.get("HAP", 0))
            
            # Calculate a 'base speed' for display using the average of the random range (1.5)
            base_speed = (dex * 1.5) * (ene * 1.5) * (hap * 1.5) / 3.0
            total = int(base_speed)
            e.add_field(name=f"{name}- {total}", value=f"{em} {track}", inline=False)
        return e



    async def start_race(self):
        if not self.simulation:
            self._update_view()
            if self.message:
                await self.message.edit(view=self)

        avg_level = self._calculate_average_pet_level()
        
        diff_mult = 1.0
        if self.difficulty == "journeyman":
            diff_mult = 1.5
        elif self.difficulty != "apprentice":
            diff_mult = 2.0
            
        self.segment_threshold = (25.0 * avg_level) * diff_mult

        self.running = True
        self.finished = False
        async def loop():
            while self.running and not self.finished:
                await asyncio.sleep(1)
                self.loop_count += 1
                for uid in self.participants:
                    if uid in self.finish_order:
                        continue
                    pet = self.pets.get(uid, {})
                    spd = _pet_speed(pet)
                    self.accum[uid] = self.accum.get(uid, 0.0) + spd
                    while self.accum[uid] >= self.segment_threshold and self.progress[uid] < self.max_segments:
                        self.accum[uid] -= self.segment_threshold
                        self.progress[uid] += 1
                    if self.progress[uid] >= self.max_segments:
                        if uid not in self.finish_order:
                            self.finish_order.append(uid)
                            self.finish_times[uid] = self.loop_count
                        if len(self.finish_order) == len(self.participants):
                            self.finished = True
                            break
                if self.message:
                    try:
                        await self.message.edit(embed=self._race_embed(), view=self)
                    except Exception as e:
                        logging.error(f"Error editing race message: {e}")
            if self.finished:
                await self._settle_bets()
        self.task = asyncio.create_task(loop())

    async def _handle_player_io(self, uid: int, change: int, bet: int, win: bool) -> Optional[str]:
        user = self.bot.get_user(uid)
        name = user.display_name if user else "Unknown"

        async def _do_stats():
            try:
                await user_data_manager.update_pet_gambling_stats(
                    str(uid),
                    "races",
                    change,
                    bet_amount=bet
                )
            except Exception:
                pass

        await _do_stats()
        return None

    async def _settle_bets(self):
        self.running = False
        if not self.finish_order:
            return

        self.winner_id = self.finish_order[0]
        
        if self.winner_id == self.owner.id:
            self.win_streak += 1
            
            payout_mults = {"apprentice": 1.25, "journeyman": 2.0, "senior": 3.0}
            payout_mult = payout_mults.get(self.difficulty, 1.0)
            
            streak_mult = 1
            if self.win_streak >= 9:
                streak_mult = 8
            elif self.win_streak >= 6:
                streak_mult = 4
            elif self.win_streak >= 3:
                streak_mult = 2
            
            win_amount = int(self.initial_bet * payout_mult * streak_mult)
            self.pending_xp += win_amount
            
            keys_to_add = []
            if self.win_streak >= 9:
                keys_to_add.extend(["Key1", "Key2", "Key3"])
            elif self.win_streak >= 6:
                keys_to_add.append("Key3")
            elif self.win_streak >= 3:
                keys_to_add.append("Key2")
            else:
                keys_to_add.append("Key1")
            self.pending_keys.extend(keys_to_add)

            self.update_view_for_win()
        else:
            self.win_streak = 0
            self.pending_xp = 0
            self.pending_keys = []
            await self._handle_player_io(self.owner.id, -self.initial_bet, self.initial_bet, False)
            self.update_view_for_loss()

    def update_view_for_win(self):
        self._update_view()
        if self.message:
            asyncio.create_task(self.message.edit(embed=self._win_embed(), view=self))

    def update_view_for_loss(self):
        self._update_view()
        if self.message:
            asyncio.create_task(self.message.edit(embed=self._loss_embed(), view=self))

    def _win_embed(self) -> discord.Embed:
        e = discord.Embed(title="You Won!", color=discord.Color.green(), timestamp=discord.utils.utcnow())
        e.description = f"Your win streak is now {self.win_streak}."
        e.add_field(name="Pending Winnings", value=f"XP: {self.pending_xp:,}\nKeys: {', '.join(self.pending_keys)}", inline=False)
        e.add_field(name="Next Race", value="You can either continue to the next race or cash out your winnings.", inline=False)
        return e

    def _loss_embed(self) -> discord.Embed:
        e = discord.Embed(title="You Lost!", color=discord.Color.red(), timestamp=discord.utils.utcnow())
        e.description = f"You lost your bet of {self.initial_bet:,} XP and your streak has been reset."
        return e

    async def continue_button(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self._reset_race_state()
        await self.start_race()

    async def cash_out_button(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        # Add XP
        await _add_xp(self.owner, self.pending_xp)
        
        # Add Keys
        pet_data = await self._load_user_pet(self.owner)
        if pet_data:
            for key_name in self.pending_keys:
                await LootCalculator.add_item_to_inventory(self.owner.id, {"name": key_name, "type": "Key"}, pet_data)

        await self._handle_player_io(self.owner.id, self.pending_xp, self.initial_bet, True)

        embed = discord.Embed(title="Cashed Out!", color=discord.Color.gold(), timestamp=discord.utils.utcnow())
        embed.description = f"You have cashed out your winnings of {self.pending_xp:,} XP and the following keys: {', '.join(self.pending_keys)}"
        
        self.win_streak = 0
        self.pending_xp = 0
        self.pending_keys = []
        self.cashed_out = True
        
        self._update_view()
        if self.message:
            await self.message.edit(embed=embed, view=self)

    async def play_again_button(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self._reset_race_state()
        await self.start_race()

    def _reset_race_state(self):
        self.finished = False
        self.cashed_out = False
        self.winner_id = None
        self.finish_order = []
        self.finish_times = {}
        self.loop_count = 0
        self.participants = [self.owner.id]
        for uid in self.participants:
            self.tracks[uid] = [emoji_mod.mention('BlackSquare') or "➖"] * self.max_segments
            self.progress[uid] = 0
            self.accum[uid] = 0.0

    async def on_timeout(self):
        self.running = False

    async def join_button(self, interaction: discord.Interaction):
        if self.simulation:
            await interaction.response.send_message("Simulation mode does not accept joins.", ephemeral=True)
            return
        if self.running:
            await interaction.response.send_message("Race already started.", ephemeral=True)
            return
        if interaction.user.id in self.participants:
            await interaction.response.send_message("You have already joined.", ephemeral=True)
            return
        if len(self.participants) >= 4:
            await interaction.response.send_message("Lobby is full.", ephemeral=True)
            return
        pet = await self._load_user_pet(cast(discord.Member, interaction.user))
        if not pet:
            await interaction.response.send_message("You need a pet.", ephemeral=True)
            return
        species = str(pet.get("species", "Cat"))
        self.participants.append(interaction.user.id)
        self.tracks[interaction.user.id] = ["➖"] * self.max_segments
        self.progress[interaction.user.id] = 0
        self.accum[interaction.user.id] = 0.0
        self.species_emo[interaction.user.id] = _species_emoji(species)
        self.pets[interaction.user.id] = pet
        if self.mode_betting:
            modal = BetModal(self, pet, cast(discord.Member, interaction.user))
            await interaction.response.send_modal(modal)
        else:
            if self.message:
                await self.message.edit(embed=self._lobby_embed(), view=self)
            await interaction.response.send_message("Joined.", ephemeral=True)

    async def start_button(self, interaction: discord.Interaction):
        if self.running:
            await interaction.response.send_message("Race already started.", ephemeral=True)
            return
        if not self.simulation:
            if len(self.participants) < 2:
                await interaction.response.send_message("Need at least 2 racers.", ephemeral=True)
                return
        await interaction.response.defer()
        if self.message:
            await self.message.edit(embed=self._race_embed(), view=self)
        await self.start_race()

    async def leave_button(self, interaction: discord.Interaction):
        if self.running:
            await interaction.response.send_message("Race in progress.", ephemeral=True)
            return
        if interaction.user.id not in self.participants:
            await interaction.response.send_message("You are not in this lobby.", ephemeral=True)
            return
        if interaction.user.id == self.owner.id:
            await interaction.response.send_message("The owner cannot leave the lobby.", ephemeral=True)
            return

        self.participants.remove(interaction.user.id)
        self.tracks.pop(interaction.user.id, None)
        self.progress.pop(interaction.user.id, None)
        self.accum.pop(interaction.user.id, None)
        self.species_emo.pop(interaction.user.id, None)
        self.pets.pop(interaction.user.id, None)
        bet = self.bets.pop(interaction.user.id, 0)
        if bet > 0:
            await _add_xp(cast(discord.Member, interaction.user), bet)

        if self.message:
            await self.message.edit(embed=self._lobby_embed(), view=self)
        await interaction.response.send_message("You have left the lobby.", ephemeral=True)
