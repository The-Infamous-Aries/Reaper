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
        self.tracks: Dict[int, List[str]] = {}
        self.progress: Dict[int, int] = {}
        self.accum: Dict[int, float] = {}
        self.species_emo: Dict[int, str] = {}
        self.pets: Dict[int, Dict] = {}
        self.bets: Dict[int, int] = {}
        self.participants: List[int] = []
        self.win_streaks: Dict[int, int] = {}
        self.winner_id: Optional[int] = None
        self.finish_order: List[int] = []
        self.finish_times: Dict[int, int] = {}
        self.loop_count = 0
        self.max_segments = 10
        self.segment_threshold = 5.0
        self.task: Optional[asyncio.Task] = None
        self._init_session()

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
                ok = await _deduct_xp(self.owner, self.initial_bet)
                if not ok:
                    return False
                self.bets[self.owner.id] = self.initial_bet
            diff_mult = 0.8 if self.difficulty == "apprentice" else (1.0 if self.difficulty == "journeyman" else 1.2)
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

    def _results_embed(self, win_amount: int, loot_messages: List[str]) -> discord.Embed:
        e = discord.Embed(title="Race Results", color=discord.Color.gold(), timestamp=discord.utils.utcnow())
        
        rankings = []
        rank_emojis = {
            0: emoji_mod.mention("1A") or "1st",
            1: emoji_mod.mention("2A") or "2nd",
            2: emoji_mod.mention("3A") or "3rd",
        }
        for i, user_id in enumerate(self.finish_order):
            user = self.bot.get_user(user_id)
            if user:
                time = self.finish_times.get(user_id, 0)
                rank_emoji = rank_emojis.get(i, f"#{i+1}")
                rankings.append(f"{rank_emoji} {user.mention} - {time}s")
        
        e.description = "\n".join(rankings)

        for uid in self.participants:
            user = self.bot.get_user(uid)
            if not user:
                continue

            bet_amount = self.bets.get(uid, 0)
            result_text = ""

            if uid == self.winner_id:
                result_text = f"Won: {win_amount:,} XP"
            else:
                result_text = f"Lost: {bet_amount:,} XP"

            e.add_field(name=user.display_name, value=result_text, inline=True)

        if loot_messages:
            e.add_field(name="💎 Loot Found", value="\n".join(loot_messages), inline=False)

        return e

    async def start_race(self):
        if not await self._setup_competitors():
            logging.error("Failed to set up competitors.")
            return

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
        io_tasks = []
        loot_messages: List[str] = []

        if self.simulation:
            if self.winner_id == self.owner.id:
                key_name = None
                if self.difficulty == "apprentice":
                    key_name = "Key1"
                elif self.difficulty == "journeyman":
                    key_name = "Key2"
                else:
                    key_name = "Key3"

                if key_name:
                    key_item = {"name": key_name, "type": "Key"}
                    pet_data = await user_data_manager.get_pet_data_async(str(self.owner.id))
                    if pet_data:
                        added, msg = await LootCalculator.add_item_to_inventory(self.owner.id, key_item, pet_data)
                        if msg:
                            loot_messages.append(msg)

            if self.mode_betting:
                mult = 2 if self.difficulty == "apprentice" else (5 if self.difficulty == "journeyman" else 10)
                win_amount = self.initial_bet * mult
                if self.winner_id == self.owner.id:
                    self.win_streaks[self.owner.id] = self.win_streaks.get(self.owner.id, 0) + 1
                    await _add_xp(self.owner, win_amount)
                    io_tasks.append(self._handle_player_io(self.owner.id, int(win_amount), int(self.initial_bet or 0), True))
                else:
                    self.win_streaks[self.owner.id] = 0
                    io_tasks.append(self._handle_player_io(self.owner.id, -int(self.initial_bet or 0), int(self.initial_bet or 0), False))
        else:
            placements = {0: "Key3", 1: "Key2", 2: "Key1"}
            for i, user_id in enumerate(self.finish_order):
                if i in placements:
                    key_name = placements[i]
                    key_item = {"name": key_name, "type": "Key"}
                    pet_data = await user_data_manager.get_pet_data_async(str(user_id))
                    user = self.bot.get_user(user_id)
                    if pet_data and user:
                        added, msg = await LootCalculator.add_item_to_inventory(user_id, key_item, pet_data)
                        if msg:
                            loot_messages.append(f"{user.mention}:{msg}")

            if self.mode_betting:
                pot = sum(self.bets.values())
                winner_user = self.bot.get_user(self.winner_id)
                if winner_user:
                    for pid in self.participants:
                        if pid == self.winner_id:
                            self.win_streaks[pid] = self.win_streaks.get(pid, 0) + 1
                        else:
                            self.win_streaks[pid] = 0

                    await _add_xp(winner_user, pot)
                    max_bet = max(self.bets.values()) if self.bets else 0
                    io_tasks.append(self._handle_player_io(self.winner_id, int(pot), max_bet, True))

                for pid in self.participants:
                    if pid != self.winner_id:
                        u = self.bot.get_user(pid)
                        if u:
                            bet_amt = int(self.bets.get(pid, 0) or 0)
                            io_tasks.append(self._handle_player_io(pid, -bet_amt, bet_amt, False))
        
        # Run I/O in parallel
        if io_tasks:
            await asyncio.gather(*io_tasks)

        # Show "Play Again" / Reset option
        if self.message:
            win_amount = 0
            if self.simulation:
                mult = 2 if self.difficulty == "apprentice" else (5 if self.difficulty == "journeyman" else 10)
                win_amount = self.initial_bet * mult
            else:
                win_amount = sum(self.bets.values())
            
            results_embed = self._results_embed(win_amount, loot_messages)
            await self.message.channel.send(embed=results_embed)

    @discord.ui.button(label="Play Again", style=discord.ButtonStyle.secondary, row=1)
    async def play_again_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.running:
            await interaction.response.send_message("Race in progress.", ephemeral=True)
            return
        if not self.finished:
            await interaction.response.send_message("Finish the current race first.", ephemeral=True)
            return
        
        # Reset Logic
        self.finished = False
        self.winner_id = None
        self.bets = {}
        for uid in self.participants:
            self.tracks[uid] = ["➖"] * self.max_segments
            self.progress[uid] = 0
            self.accum[uid] = 0.0
        
        await interaction.response.defer()
        if self.message:
            await self.message.edit(embed=self._lobby_embed(), view=self)


    async def on_timeout(self):
        self.running = False

    @discord.ui.button(label="Join", style=discord.ButtonStyle.success)
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
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

    @discord.ui.button(label="Start", style=discord.ButtonStyle.primary)
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
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
