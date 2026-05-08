"""
Wheel of Pets — Casino game for the Pet System.

A fully animated wheel with all 103 pet species. Players bet XP on which
pet will land. If the winning pet matches the player's own pet species,
the payout is doubled (2x multiplier).

Payout structure (flat odds, all pets equal rarity):
  - Win:          bet * 103 * 0.95  (5% house edge)
  - Own-pet win:  bet * 103 * 0.95 * 2
  - Loss:         -bet

Animation: 8-frame spinning sequence showing a scrolling strip of pet
emojis + names, slowing down each frame, then a final reveal with a
pointer indicator.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Dict, List, Optional, Tuple

import discord

from Systems.Functions import emoji as emoji_mod
from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.pet_brain import LootCalculator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# All 103 pet species (must match info.json keys exactly)
# ---------------------------------------------------------------------------
ALL_PETS: List[str] = [
    "Alligator", "Ant", "Anteater", "Badger", "Bat", "Beaver", "Bee",
    "Beetle", "Bison", "BlueTang", "Camel", "Cardinal", "Cat", "Cheetah",
    "Chicken", "Clownfish", "Cow", "Crab", "Crow", "Deer", "Dog",
    "Dolphin", "Duck", "Eagle", "Elephant", "Emu", "Fox", "Frog",
    "Giraffe", "Goat", "Goose", "Gorilla", "Grizzly", "Hamster",
    "Hedgehog", "Hippo", "Horse", "Hummingbird", "Iguana", "Jaguar",
    "Jellyfish", "Kangaroo", "Kiwi", "Koala", "Ladybug", "Lemur",
    "Leopard", "Lion", "Llama", "Mantis", "Monkey", "Mouse", "Octopus",
    "Orangutan", "Orca", "Ostrich", "Otter", "Panda", "Parrot", "Peacock",
    "Pelican", "Penguin", "Pig", "Pigeon", "Platypus", "PolarBear",
    "Pufferfish", "Rabbit", "Raccoon", "Ram", "Rat", "RedPanda",
    "Reindeer", "Rhino", "Salmon", "Scorpion", "Seahorse", "Seal",
    "Shark", "Sheep", "Shrimp", "Skunk", "Sloth", "Snail", "Snake",
    "Spider", "Squirrel", "Starfish", "Stingray", "SugarGlider", "Tiger",
    "Toucan", "Turkey", "Turtle", "Walrus", "Whale", "Wolf", "Yak",
    "Zebra", "Owl", "Axolotl", "Centipede", "Firefly",
]

# House edge: 5 %
_HOUSE_EDGE = 0.95
# Base multiplier = number of pets on the wheel
_BASE_MULT = len(ALL_PETS)  # 103
# Own-pet bonus multiplier
_OWN_PET_MULT = 2.0

# Number of animation frames before the final reveal
_SPIN_FRAMES = 8
# Seconds between each animation frame (starts fast, slows down)
_FRAME_DELAYS = [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3]

# Width of the visible "window" on the wheel (number of pets shown)
_WINDOW_SIZE = 7   # odd number so the centre slot is the pointer


def _pet_emoji(species: str) -> str:
    """Return the Discord emoji mention for a pet species, or a paw fallback."""
    m = emoji_mod.mention(species)
    return m if m else "🐾"


def _wheel_window(centre_index: int, pets: List[str]) -> List[str]:
    """
    Return a list of _WINDOW_SIZE pet names centred on centre_index,
    wrapping around the wheel.
    """
    half = _WINDOW_SIZE // 2
    n = len(pets)
    return [pets[(centre_index - half + i) % n] for i in range(_WINDOW_SIZE)]


def _render_window(window: List[str], pointer_pos: int = _WINDOW_SIZE // 2) -> str:
    """
    Render the wheel window as a single embed field value.
    The centre slot (pointer_pos) gets a ▶ marker.
    Each slot shows: emoji  Name
    """
    lines: List[str] = []
    for i, species in enumerate(window):
        em = _pet_emoji(species)
        if i == pointer_pos:
            lines.append(f"**▶  {em}  {species}  ◀**")
        else:
            lines.append(f"　　{em}  {species}")
    return "\n".join(lines)


def _compute_total_xp(pet: Dict[str, Any]) -> int:
    lvl = int(pet.get("level", 1))
    rem = int(pet.get("experience", 0))
    return int(LootCalculator.get_total_experience_for_level(lvl)) + rem


# ---------------------------------------------------------------------------
# Bet modal
# ---------------------------------------------------------------------------
class WheelBetModal(discord.ui.Modal, title="🎡 Wheel of Pets — Place Your Bet"):
    bet_input: discord.ui.TextInput = discord.ui.TextInput(
        label="XP Bet Amount",
        placeholder="Enter XP to bet (e.g. 500)",
        required=True,
        min_length=1,
        max_length=10,
        style=discord.TextStyle.short,
    )

    def __init__(self, view: "WheelOfPetsView"):
        super().__init__()
        self.wheel_view = view
        self.add_item(self.bet_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            bet = int(str(self.bet_input.value).strip())
        except ValueError:
            await interaction.response.send_message(
                f"{emoji_mod.mention('Deny') or '❌'} Bet must be a whole number.",
                ephemeral=True,
            )
            return

        if bet <= 0:
            await interaction.response.send_message(
                f"{emoji_mod.mention('Deny') or '❌'} Bet must be greater than 0.",
                ephemeral=True,
            )
            return

        # Validate XP balance
        pet = await user_data_manager.get_pet_data_async(str(interaction.user.id))
        if not pet:
            await interaction.response.send_message(
                f"{emoji_mod.mention('Deny') or '❌'} You need a pet to play. Use `/pet_shop` first.",
                ephemeral=True,
            )
            return

        total_xp = _compute_total_xp(pet)
        if bet > total_xp:
            await interaction.response.send_message(
                f"{emoji_mod.mention('Deny') or '❌'} You only have **{total_xp:,}** XP. "
                f"You cannot bet **{bet:,}** XP.",
                ephemeral=True,
            )
            return

        # Hand off to the view
        await interaction.response.defer()
        await self.wheel_view.run_spin(interaction, bet)


# ---------------------------------------------------------------------------
# Pet selection dropdown (25 pets per select due to Discord limit)
# ---------------------------------------------------------------------------
class PetSelectView(discord.ui.View):
    """
    Lets the player pick which pet they want to bet on.
    Because Discord limits selects to 25 options, we paginate across
    multiple selects shown one at a time via a page button.
    """

    PAGE_SIZE = 25

    def __init__(self, parent: "WheelOfPetsView"):
        super().__init__(timeout=120)
        self.parent = parent
        self.page = 0
        self.total_pages = (len(ALL_PETS) + self.PAGE_SIZE - 1) // self.PAGE_SIZE
        self._build_page()

    def _build_page(self) -> None:
        self.clear_items()
        start = self.page * self.PAGE_SIZE
        end = min(start + self.PAGE_SIZE, len(ALL_PETS))
        page_pets = ALL_PETS[start:end]

        options = []
        for species in page_pets:
            em_str = emoji_mod.mention(species)
            # Discord option emoji must be a PartialEmoji or str unicode emoji
            partial = emoji_mod.get_partial(species)
            opt = discord.SelectOption(
                label=species,
                value=species,
                description=f"Bet on {species}",
                emoji=partial,
            )
            options.append(opt)

        select = discord.ui.Select(
            placeholder=f"Choose a pet to bet on (page {self.page + 1}/{self.total_pages})",
            options=options,
            min_values=1,
            max_values=1,
        )
        select.callback = self._on_select
        self.add_item(select)

        # Prev / Next page buttons
        if self.total_pages > 1:
            if self.page > 0:
                prev_btn = discord.ui.Button(
                    label="◀ Prev",
                    style=discord.ButtonStyle.secondary,
                    row=1,
                )
                prev_btn.callback = self._prev_page
                self.add_item(prev_btn)

            if self.page < self.total_pages - 1:
                next_btn = discord.ui.Button(
                    label="Next ▶",
                    style=discord.ButtonStyle.secondary,
                    row=1,
                )
                next_btn.callback = self._next_page
                self.add_item(next_btn)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.parent.user.id:
            await interaction.response.send_message("This isn't your wheel!", ephemeral=True)
            return
        chosen = interaction.data["values"][0]  # type: ignore[index]
        self.parent.chosen_pet = chosen
        # Now ask for the bet amount
        modal = WheelBetModal(self.parent)
        await interaction.response.send_modal(modal)

    async def _prev_page(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.parent.user.id:
            await interaction.response.send_message("This isn't your wheel!", ephemeral=True)
            return
        self.page -= 1
        self._build_page()
        await interaction.response.edit_message(
            embed=self.parent._selection_embed(), view=self
        )

    async def _next_page(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.parent.user.id:
            await interaction.response.send_message("This isn't your wheel!", ephemeral=True)
            return
        self.page += 1
        self._build_page()
        await interaction.response.edit_message(
            embed=self.parent._selection_embed(), view=self
        )


# ---------------------------------------------------------------------------
# Main Wheel of Pets view
# ---------------------------------------------------------------------------
class WheelOfPetsView(discord.ui.View):
    """
    Persistent view that lives on the message for the entire session.
    The player can keep spinning without dismissing the message.
    """

    def __init__(self, bot: Any, user: discord.Member):
        super().__init__(timeout=600)
        self.bot = bot
        self.user = user
        self.message: Optional[discord.Message] = None
        self.chosen_pet: Optional[str] = None
        self.spinning = False

        # Session stats
        self.session_spins = 0
        self.session_net_xp = 0

    # ------------------------------------------------------------------
    # Embeds
    # ------------------------------------------------------------------

    def _lobby_embed(self) -> discord.Embed:
        casino_em = emoji_mod.mention("Casino") or "🎡"
        embed = discord.Embed(
            title=f"{casino_em}  Wheel of Pets  {casino_em}",
            description=(
                "**How to play:**\n"
                "1. Press **🎡 Spin the Wheel** to choose a pet and place your XP bet.\n"
                "2. The wheel spins through all **103 pets** and lands on one.\n"
                "3. If it lands on your chosen pet — you win!\n\n"
                "**Payouts:**\n"
                f"🏆 Win  →  `bet × {_BASE_MULT} × {_HOUSE_EDGE}` XP\n"
                f"⭐ Win on **your own pet**  →  `bet × {_BASE_MULT} × {_HOUSE_EDGE} × {int(_OWN_PET_MULT)}` XP\n"
                f"💸 Loss  →  `-bet` XP\n\n"
                "*All {total} pets have equal odds.*".format(total=len(ALL_PETS))
            ),
            color=discord.Color.gold(),
        )
        embed.set_footer(
            text=f"Session: {self.session_spins} spin(s) | Net XP: {self.session_net_xp:+,}"
        )
        return embed

    def _selection_embed(self) -> discord.Embed:
        casino_em = emoji_mod.mention("Casino") or "🎡"
        embed = discord.Embed(
            title=f"{casino_em}  Wheel of Pets — Choose Your Pet  {casino_em}",
            description=(
                "Select the pet you want to bet on from the dropdown below.\n"
                "Then enter your XP bet in the popup.\n\n"
                f"*{len(ALL_PETS)} pets on the wheel — all equal odds.*"
            ),
            color=discord.Color.blurple(),
        )
        return embed

    def _spinning_embed(
        self,
        frame: int,
        window: List[str],
        bet: int,
        chosen: str,
        own_pet: str,
    ) -> discord.Embed:
        casino_em = emoji_mod.mention("Casino") or "🎡"
        chosen_em = _pet_emoji(chosen)
        own_em = _pet_emoji(own_pet)

        # Progress bar: filled squares for frames elapsed
        filled = emoji_mod.mention("Approve") or "🟩"
        empty = emoji_mod.mention("Pending") or "⬜"
        bar = filled * frame + empty * (_SPIN_FRAMES - frame)

        # Slow-down label
        speed_labels = [
            "🌪️ Blazing fast!", "🌪️ Very fast!", "⚡ Fast!", "⚡ Speeding up…",
            "🐇 Slowing down…", "🐢 Almost there…", "🔮 Finalising…", "✨ Revealing…",
        ]
        speed = speed_labels[min(frame, len(speed_labels) - 1)]

        embed = discord.Embed(
            title=f"{casino_em}  Wheel of Pets — Spinning!  {casino_em}",
            color=discord.Color.orange(),
        )
        embed.add_field(
            name="🎡 The Wheel",
            value=_render_window(window),
            inline=False,
        )
        embed.add_field(name="🎯 Your Bet", value=f"{chosen_em} **{chosen}**  •  **{bet:,}** XP", inline=True)
        embed.add_field(name="🐾 Your Pet", value=f"{own_em} **{own_pet}**", inline=True)
        embed.add_field(name=f"Frame {frame}/{_SPIN_FRAMES}", value=f"{bar}\n{speed}", inline=False)
        embed.set_footer(text=f"Session: {self.session_spins} spin(s) | Net XP: {self.session_net_xp:+,}")
        return embed

    def _result_embed(
        self,
        winner: str,
        bet: int,
        chosen: str,
        own_pet: str,
        xp_delta: int,
        new_total_xp: int,
        level_change: Optional[Tuple[int, int]],
        loot_messages: List[str],
        window: List[str],
    ) -> discord.Embed:
        casino_em = emoji_mod.mention("Casino") or "🎡"
        winner_em = _pet_emoji(winner)
        chosen_em = _pet_emoji(chosen)
        own_em = _pet_emoji(own_pet)

        won = winner == chosen
        own_pet_bonus = won and (winner == own_pet)

        if own_pet_bonus:
            color = discord.Color.gold()
            title = f"{casino_em}  ⭐ OWN PET JACKPOT! ⭐  {casino_em}"
        elif won:
            color = discord.Color.green()
            title = f"{casino_em}  🏆 YOU WIN!  {casino_em}"
        else:
            color = discord.Color.red()
            title = f"{casino_em}  💸 Better luck next time…  {casino_em}"

        embed = discord.Embed(title=title, color=color)

        # Final wheel window (centred on winner)
        embed.add_field(
            name="🎡 Final Position",
            value=_render_window(window),
            inline=False,
        )

        embed.add_field(
            name="🎯 Landed On",
            value=f"{winner_em} **{winner}**",
            inline=True,
        )
        embed.add_field(
            name="🎰 Your Bet",
            value=f"{chosen_em} **{chosen}**  •  **{bet:,}** XP",
            inline=True,
        )
        embed.add_field(
            name="🐾 Your Pet",
            value=f"{own_em} **{own_pet}**",
            inline=True,
        )

        if won:
            bonus_note = "  *(2× own-pet bonus!)*" if own_pet_bonus else ""
            embed.add_field(
                name="🏆 XP Won",
                value=f"**+{xp_delta:,}** XP{bonus_note}",
                inline=True,
            )
        else:
            embed.add_field(
                name="💸 XP Lost",
                value=f"**{xp_delta:,}** XP",
                inline=True,
            )

        embed.add_field(
            name="🧮 New Total XP",
            value=f"**{new_total_xp:,}** XP",
            inline=True,
        )

        if level_change:
            old_lvl, new_lvl = level_change
            if new_lvl > old_lvl:
                embed.add_field(
                    name="🎉 Level Up!",
                    value=f"**{old_lvl}** ➡️ **{new_lvl}**",
                    inline=False,
                )
            elif new_lvl < old_lvl:
                embed.add_field(
                    name="📉 Level Down",
                    value=f"**{old_lvl}** ➡️ **{new_lvl}**",
                    inline=False,
                )

        for msg in loot_messages:
            embed.add_field(name="💎 Loot Found", value=msg, inline=False)

        embed.set_footer(
            text=f"Session: {self.session_spins} spin(s) | Net XP: {self.session_net_xp:+,}"
        )
        return embed

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------

    @discord.ui.button(
        label="🎡 Spin the Wheel",
        style=discord.ButtonStyle.success,
        row=0,
    )
    async def spin_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "This isn't your wheel! Start your own with `/wheel`.", ephemeral=True
            )
            return
        if self.spinning:
            await interaction.response.send_message(
                "The wheel is already spinning!", ephemeral=True
            )
            return

        # Check pet exists
        pet = await user_data_manager.get_pet_data_async(str(self.user.id))
        if not pet:
            await interaction.response.send_message(
                f"{emoji_mod.mention('Deny') or '❌'} You need a pet to play. Use `/pet_shop` first.",
                ephemeral=True,
            )
            return

        # Show pet selection
        sel_view = PetSelectView(self)
        await interaction.response.edit_message(
            embed=self._selection_embed(), view=sel_view
        )

    # ------------------------------------------------------------------
    # Core spin logic
    # ------------------------------------------------------------------

    async def run_spin(
        self, interaction: discord.Interaction, bet: int
    ) -> None:
        """
        Called after the player has chosen a pet and confirmed their bet.
        Runs the full animation then settles the result.
        """
        self.spinning = True

        # Restore the main view on the message (removes the pet-select view)
        # We disable the spin button during animation
        self.spin_button.disabled = True
        if self.message:
            await self.message.edit(view=self)

        # Determine the winning pet (pre-determined before animation)
        winner_index = random.randint(0, len(ALL_PETS) - 1)
        winner = ALL_PETS[winner_index]

        # Load own pet species
        pet = await user_data_manager.get_pet_data_async(str(self.user.id))
        own_pet = str(pet.get("species", "Cat")) if pet else "Cat"
        chosen = self.chosen_pet or "Cat"

        # ── Animation ──────────────────────────────────────────────────
        # We animate a "virtual" position that starts far away from the
        # winner and decelerates toward it.
        n = len(ALL_PETS)

        # Start position: a random offset several full rotations before winner
        full_rotations = random.randint(3, 5)
        start_offset = full_rotations * n + random.randint(10, n - 10)
        start_index = (winner_index - start_offset) % n

        # Distribute the travel across frames with easing (more steps early)
        # Total steps to travel = start_offset
        total_steps = start_offset
        # Allocate steps per frame using a decelerating distribution
        raw_weights = [_SPIN_FRAMES - i for i in range(_SPIN_FRAMES)]
        weight_sum = sum(raw_weights)
        steps_per_frame = [
            max(1, round(total_steps * w / weight_sum)) for w in raw_weights
        ]
        # Correct rounding drift so we land exactly on winner_index
        cumulative = sum(steps_per_frame)
        diff = total_steps - cumulative
        steps_per_frame[-1] = max(1, steps_per_frame[-1] + diff)

        current_index = start_index
        for frame_num, (steps, delay) in enumerate(
            zip(steps_per_frame, _FRAME_DELAYS), start=1
        ):
            current_index = (current_index + steps) % n
            window = _wheel_window(current_index, ALL_PETS)
            embed = self._spinning_embed(frame_num, window, bet, chosen, own_pet)
            try:
                if self.message:
                    await self.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass
            await asyncio.sleep(delay)

        # Final position must be exactly winner_index
        final_window = _wheel_window(winner_index, ALL_PETS)

        # ── Settle ─────────────────────────────────────────────────────
        won = winner == chosen
        own_pet_bonus = won and (winner == own_pet)

        if won:
            raw_win = int(bet * _BASE_MULT * _HOUSE_EDGE)
            if own_pet_bonus:
                raw_win = int(raw_win * _OWN_PET_MULT)
            xp_delta = raw_win
        else:
            xp_delta = -bet

        # Apply XP change
        level_change: Optional[Tuple[int, int]] = None
        new_total_xp = 0
        loot_messages: List[str] = []

        try:
            old_level = int(pet.get("level", 1)) if pet else 1

            xp_result = await LootCalculator.apply_xp_change(
                self.user.id, xp_delta,
                source="wheel_of_pets_win" if won else "wheel_of_pets_bet",
            )

            if isinstance(xp_result, tuple) and xp_result[0] and xp_result[1]:
                result_data = xp_result[1]
                new_total_xp = result_data.get("new_total_xp", 0)
                new_level = result_data.get("new_level", old_level)
                if new_level != old_level:
                    level_change = (old_level, new_level)
            else:
                # Fallback: reload pet to get current XP
                refreshed = await user_data_manager.get_pet_data_async(str(self.user.id))
                if refreshed:
                    new_total_xp = _compute_total_xp(refreshed)

            # Award loot on wins
            if won and pet:
                loot_messages = await LootCalculator.award_gambling_loot(
                    self.user.id, pet
                )

            # Update gambling stats
            await user_data_manager.update_pet_gambling_stats(
                str(self.user.id),
                "wheel_of_pets",
                xp_delta,
                bet_amount=bet,
                extra_data={
                    "games_by_type": {"wheel_of_pets": 1},
                    "own_pet_jackpots": 1 if own_pet_bonus else 0,
                },
            )

        except Exception as exc:
            logger.error(f"WheelOfPets settle error for {self.user.id}: {exc}", exc_info=True)

        # Update session stats
        self.session_spins += 1
        self.session_net_xp += xp_delta

        # ── Result embed ───────────────────────────────────────────────
        result_embed = self._result_embed(
            winner=winner,
            bet=bet,
            chosen=chosen,
            own_pet=own_pet,
            xp_delta=xp_delta,
            new_total_xp=new_total_xp,
            level_change=level_change,
            loot_messages=loot_messages,
            window=final_window,
        )

        # Re-enable spin button so the player can go again
        self.spinning = False
        self.chosen_pet = None
        self.spin_button.disabled = False

        if self.message:
            await self.message.edit(embed=result_embed, view=self)

    # ------------------------------------------------------------------
    # Timeout
    # ------------------------------------------------------------------

    async def on_timeout(self) -> None:
        self.spinning = False
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True  # type: ignore[attr-defined]
        if self.message:
            try:
                timeout_embed = discord.Embed(
                    title="⏰ Wheel of Pets — Session Ended",
                    description=(
                        f"Session timed out after inactivity.\n\n"
                        f"**Spins this session:** {self.session_spins}\n"
                        f"**Net XP:** {self.session_net_xp:+,}"
                    ),
                    color=discord.Color.dark_gray(),
                )
                await self.message.edit(embed=timeout_embed, view=self)
            except Exception:
                pass
