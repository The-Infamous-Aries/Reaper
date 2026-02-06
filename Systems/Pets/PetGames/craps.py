import discord
from discord.ext import commands
import random
import asyncio
from typing import Dict, List, Optional, Tuple
from enum import Enum
from dataclasses import dataclass

from Systems.Functions import emoji as emoji_mod
from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.pet_brain import LootCalculator

DICE_COLORS = ["Red", "Orange", "Blue", "Yellow", "Pink", "Green", "Purple"]

def _dice_emoji(value: int, color: Optional[str] = None) -> str:
    selected_color = color
    if color == "Random":
        selected_color = random.choice(DICE_COLORS)
        
    if selected_color:
        name = f"{selected_color}{value}"
        m = emoji_mod.mention(name)
        if m:
            return m
            
    if 1 <= value <= 6:
        code = f"D0{value}"
        m = emoji_mod.mention(code)
        return m or f"[{value}]"
    return f"[{value}]"

class BetType(Enum):
    PASS_LINE = "Pass Line"
    DONT_PASS = "Don't Pass"
    FIELD = "Field"
    PLACE_4 = "Place 4"
    PLACE_5 = "Place 5"
    PLACE_6 = "Place 6"
    PLACE_8 = "Place 8"
    PLACE_9 = "Place 9"
    PLACE_10 = "Place 10"
    ANY_7 = "Any 7"
    HARD_4 = "Hard 4"
    HARD_6 = "Hard 6"
    HARD_8 = "Hard 8"
    HARD_10 = "Hard 10"

@dataclass
class Bet:
    bet_type: BetType
    amount: int
    
    def __str__(self):
        return f"{self.bet_type.value}: {self.amount}"

class PlayerState:
    def __init__(self, user: discord.Member, bankroll: int, mode_betting: bool, dice_color: Optional[str] = None):
        self.user = user
        self.bankroll = bankroll
        self.mode_betting = mode_betting
        self.bets: List[Bet] = []
        self.left_game = False
        self.buy_in = bankroll
        self.dice_color = dice_color
        self.win_streak = 0
        
    @property
    def total_bet_amount(self) -> int:
        return sum(b.amount for b in self.bets)

class BetSelect(discord.ui.Select):
    def __init__(self, parent_view: 'BettingView'):
        options = [
            discord.SelectOption(label="Pass Line", description="Win on 7/11 (Come Out) or Point. Lose on 2/3/12 or 7 (Point)."),
            discord.SelectOption(label="Don't Pass", description="Opposite of Pass Line."),
            discord.SelectOption(label="Field", description="One Roll. Win on 2,3,4,9,10,11,12."),
            discord.SelectOption(label="Place 4", description="Win if 4 rolled before 7."),
            discord.SelectOption(label="Place 5", description="Win if 5 rolled before 7."),
            discord.SelectOption(label="Place 6", description="Win if 6 rolled before 7."),
            discord.SelectOption(label="Place 8", description="Win if 8 rolled before 7."),
            discord.SelectOption(label="Place 9", description="Win if 9 rolled before 7."),
            discord.SelectOption(label="Place 10", description="Win if 10 rolled before 7."),
            discord.SelectOption(label="Any 7", description="One Roll. Win on 7."),
            discord.SelectOption(label="Hard 4", description="Win on 2+2 before 7 or Easy 4."),
            discord.SelectOption(label="Hard 6", description="Win on 3+3 before 7 or Easy 6."),
            discord.SelectOption(label="Hard 8", description="Win on 4+4 before 7 or Easy 8."),
            discord.SelectOption(label="Hard 10", description="Win on 5+5 before 7 or Easy 10."),
        ]
        super().__init__(placeholder="Select Bet Type", min_values=1, max_values=1, options=options)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        bet_type_str = self.values[0]
        # Map string label to BetType
        bet_type_map = {b.value: b for b in BetType}
        selected_type = bet_type_map[bet_type_str]
        
        # Open Modal
        modal = discord.ui.Modal(title=f"Bet on {bet_type_str}")
        amount_input = discord.ui.TextInput(label="Amount", placeholder="Enter amount", min_length=1, max_length=9)
        modal.add_item(amount_input)
        
        async def on_submit(inter: discord.Interaction):
            try:
                amount = int(amount_input.value)
                if amount <= 0:
                    await inter.response.send_message("Amount must be positive.", ephemeral=True)
                    return
                
                ps = self.parent_view.main_view.players.get(inter.user.id)
                if not ps:
                    await inter.response.send_message("You are not in the game.", ephemeral=True)
                    return
                
                if ps.mode_betting and amount > ps.bankroll:
                    await inter.response.send_message(f"Insufficient funds. Bankroll: {ps.bankroll}", ephemeral=True)
                    return
                
                if ps.mode_betting:
                    ps.bankroll -= amount
                
                ps.bets.append(Bet(selected_type, amount))
                await inter.response.send_message(f"Placed {amount} on {bet_type_str}.", ephemeral=True)
                await self.parent_view.main_view.update_table()
                
            except ValueError:
                await inter.response.send_message("Invalid number.", ephemeral=True)
        
        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

class BettingView(discord.ui.View):
    def __init__(self, main_view: 'CrapsSession'):
        super().__init__(timeout=60)
        self.main_view = main_view
        self.add_item(BetSelect(self))

class CrapsSession(discord.ui.View):
    def __init__(self, bot: commands.Bot, channel_id: int, solo: bool, betting_mode: bool, buy_in: int, host: discord.Member, host_dice_color: Optional[str] = None):
        super().__init__(timeout=900)
        self.bot = bot
        self.channel_id = channel_id
        self.solo = solo
        self.betting_mode = betting_mode
        self.host = host
        self.shooter = host
        self.players: Dict[int, PlayerState] = {}
        self.message: Optional[discord.Message] = None
        self.table_open = not solo
        
        # Game State
        self.point: Optional[int] = None
        self.last_roll: Tuple[int, int] = (0, 0)
        self.last_roll_colors: Tuple[Optional[str], Optional[str]] = (None, None)
        self.last_result_text = "Place your bets for the Come Out roll!"
        self.phase = "come_out"  # come_out, point
        
        self.buy_ins: Dict[int, int] = {}
        
        initial_bankroll = buy_in if betting_mode else 0
        if betting_mode:
            asyncio.create_task(self._apply_buy_in(host, initial_bankroll))
        self.players[host.id] = PlayerState(host, initial_bankroll, betting_mode, dice_color=host_dice_color)

    async def _apply_buy_in(self, user: discord.Member, amount: int) -> None:
        await LootCalculator.apply_xp_change(user.id, -amount, source="craps_buyin")
        self.buy_ins[user.id] = amount

    async def _cash_out(self, user: discord.Member, amount: int) -> None:
        await LootCalculator.apply_xp_change(user.id, amount, source="craps_cashout")

    async def on_timeout(self):
        if self.betting_mode:
            for ps in list(self.players.values()):
                if not ps.left_game:
                    try:
                        # Refund all active bets
                        refund = sum(b.amount for b in ps.bets)
                        ps.bankroll += refund
                        await self._cash_out(ps.user, ps.bankroll)
                    except Exception:
                        pass
        if self.message:
            try:
                embed = self.message.embeds[0]
                embed.set_footer(text="Game timed out.")
                for item in self.children:
                    item.disabled = True
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass

    async def join_table(self, interaction: discord.Interaction, buy_in: Optional[int]) -> None:
        if self.solo:
            await interaction.response.send_message("Solo game.", ephemeral=True)
            return
        if interaction.user.id in self.players and not self.players[interaction.user.id].left_game:
            await interaction.response.send_message("Already joined.", ephemeral=True)
            return
        bankroll = 0
        if self.betting_mode:
            if not isinstance(buy_in, int) or buy_in <= 0:
                await interaction.response.send_message("Invalid buy in.", ephemeral=True)
                return
            pet = await user_data_manager.get_pet_data_async(str(interaction.user.id), interaction.user.display_name)
            if not pet:
                await interaction.response.send_message("No pet.", ephemeral=True)
                return
            lvl = int(pet.get("level", 1))
            total = int(pet.get("experience", 0)) + int(LootCalculator.get_total_experience_for_level(lvl))
            if buy_in > total:
                await interaction.response.send_message(f"Buy in exceeds total XP ({total}).", ephemeral=True)
                return
            await self._apply_buy_in(interaction.user, buy_in)
            bankroll = buy_in
        self.players[interaction.user.id] = PlayerState(interaction.user, bankroll, self.betting_mode, dice_color=None)
        if interaction.response.is_done():
            await interaction.followup.send(f"{interaction.user.mention} joined.", ephemeral=False)
        else:
            await interaction.response.send_message(f"{interaction.user.mention} joined.", ephemeral=False)
        await self.update_table(interaction)

    async def leave_table(self, interaction: discord.Interaction) -> None:
        ps = self.players.get(interaction.user.id)
        if not ps:
            await interaction.response.send_message("Not in game.", ephemeral=True)
            return
        if self.betting_mode:
            # Refund all active bets
            refund = sum(b.amount for b in ps.bets)
            ps.bankroll += refund
            ps.bets.clear()
            await self._cash_out(interaction.user, ps.bankroll)
        ps.left_game = True
        
        if interaction.user.id == self.shooter.id:
            active = [p for p in self.players.values() if not p.left_game]
            if active:
                self.shooter = active[0].user
                self.last_result_text += f"\nNew Shooter: {self.shooter.display_name}"
            else:
                self.last_result_text += "\nNo players left."
                
        await interaction.response.send_message("Left game.", ephemeral=True)
        await self.update_table(interaction)

    def _build_embed(self) -> discord.Embed:
        color = discord.Color.green() if self.point is None else discord.Color.gold()
        title = "🎲 Craps Table"
        if self.betting_mode:
            title += " (Betting XP)"
        else:
            title += " (Fun Mode)"
            
        embed = discord.Embed(title=title, color=color, timestamp=discord.utils.utcnow())
        
        # Game Status
        d1, d2 = self.last_roll
        total = d1 + d2
        
        c1, c2 = self.last_roll_colors
        # If total > 0 but colors are None (e.g. legacy or restart), fallback to shooter's pref
        if total > 0 and c1 is None:
             shooter_color = self.players[self.shooter.id].dice_color if self.shooter.id in self.players else None
             if shooter_color == "Random":
                 # Generate now (might shift on refresh, but better than nothing)
                 c1 = random.choice(DICE_COLORS)
                 c2 = random.choice(DICE_COLORS)
             else:
                 c1 = shooter_color
                 c2 = shooter_color
        
        roll_str = f"{_dice_emoji(d1, c1)} {_dice_emoji(d2, c2)} ({total})" if total > 0 else "Waiting for roll..."
        
        phase_str = "Come Out Roll" if self.point is None else f"Point Phase (Point: {self.point})"
        
        status_lines = [
            f"**Shooter:** {self.shooter.mention}",
            f"**Phase:** {phase_str}",
            f"**Last Roll:** {roll_str}",
            f"**Result:** {self.last_result_text}"
        ]
        embed.add_field(name="Table Status", value="\n".join(status_lines), inline=False)
        
        # Players
        player_lines = []
        for uid, ps in self.players.items():
            if ps.left_game:
                continue
            line = f"{ps.user.display_name}"
            if self.betting_mode:
                line += f" • Bank: **{ps.bankroll}** XP"
            
            if ps.bets:
                # Summarize bets
                bet_summary = ", ".join([f"{b.bet_type.value}({b.amount})" for b in ps.bets[:3]])
                if len(ps.bets) > 3:
                    bet_summary += f", +{len(ps.bets)-3} more"
                line += f"\n   └ Bets: {bet_summary}"
            else:
                line += "\n   └ No active bets"
                
            player_lines.append(line)
            
        if player_lines:
            embed.add_field(name="Players", value="\n".join(player_lines), inline=False)
        else:
            embed.add_field(name="Players", value="No active players.", inline=False)
            
        embed.set_footer(text=f"Pass: Win 7/11 (Come Out) or Point. Field: 2,3,4,9,10,11,12.")
        return embed

    async def update_table(self, interaction: Optional[discord.Interaction] = None):
        embed = self._build_embed()
        if interaction and not interaction.response.is_done():
            await interaction.response.edit_message(embed=embed, view=self)
        elif self.message:
            await self.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Place Bet", style=discord.ButtonStyle.primary, custom_id="craps_bet_menu")
    async def btn_bet_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        ps = self.players.get(interaction.user.id)
        if not ps or ps.left_game:
            await interaction.response.send_message("Join the table first.", ephemeral=True)
            return
        
        view = BettingView(self)
        await interaction.response.send_message("Select a bet type:", view=view, ephemeral=True)

    @discord.ui.button(label="Clear Bets", style=discord.ButtonStyle.danger, custom_id="craps_clear_bets")
    async def btn_clear_bets(self, interaction: discord.Interaction, button: discord.ui.Button):
        ps = self.players.get(interaction.user.id)
        if not ps or ps.left_game:
            await interaction.response.send_message("Not in game.", ephemeral=True)
            return
        
        refund = sum(b.amount for b in ps.bets)
        ps.bets.clear()
        if self.betting_mode:
            ps.bankroll += refund
        
        await interaction.response.send_message(f"Cleared all bets. Refunded {refund} XP.", ephemeral=True)
        await self.update_table()

    @discord.ui.button(label="Roll Dice", style=discord.ButtonStyle.success, custom_id="craps_roll", emoji="🎲")
    async def btn_roll(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.shooter.id:
            await interaction.response.send_message(f"Only the shooter ({self.shooter.display_name}) can roll!", ephemeral=True)
            return
            
        d1 = random.randint(1, 6)
        d2 = random.randint(1, 6)
        total = d1 + d2
        self.last_roll = (d1, d2)
        
        # Determine Colors
        shooter_color = self.players[self.shooter.id].dice_color if self.shooter.id in self.players else None
        if shooter_color == "Random":
            self.last_roll_colors = (random.choice(DICE_COLORS), random.choice(DICE_COLORS))
        else:
            self.last_roll_colors = (shooter_color, shooter_color)
        
        result_text_parts = []
        
        # Game Phase Logic
        if self.point is None: # Come Out
            if total in (7, 11):
                result_text_parts.append(f"Natural {total}! Pass Line Wins!")
                # Evaluate Bets
                await self._resolve_bets(total, "come_out_win")
            elif total in (2, 3, 12):
                result_text_parts.append(f"Craps {total}! Pass Line Loses!")
                await self._resolve_bets(total, "come_out_loss")
            else:
                self.point = total
                result_text_parts.append(f"Point is {total}.")
                await self._resolve_bets(total, "point_established")
        else: # Point Phase
            if total == self.point:
                result_text_parts.append(f"Hit Point {total}! Pass Line Wins!")
                self.point = None # Reset
                await self._resolve_bets(total, "point_win")
            elif total == 7:
                result_text_parts.append("Seven Out! Pass Line Loses!")
                self.point = None # Reset
                await self._resolve_bets(total, "seven_out")
            else:
                result_text_parts.append(f"Rolled {total}. Point is {self.point}.")
                await self._resolve_bets(total, "point_continue")

        self.last_result_text = " ".join(result_text_parts)
        
        # Check Shooter Rotation (Seven Out)
        if "Seven Out" in self.last_result_text:
             active = [p for p in self.players.values() if not p.left_game]
             if active:
                 try:
                     idx = [p.user.id for p in active].index(self.shooter.id)
                     next_idx = (idx + 1) % len(active)
                     self.shooter = active[next_idx].user
                     self.last_result_text += f"\nNew Shooter: {self.shooter.display_name}"
                 except ValueError:
                     self.shooter = active[0].user

        await self.update_table(interaction)

    async def _handle_player_io(self, uid: int, ps: PlayerState, won_total: int, lost_total: int, max_bet: int) -> Optional[str]:
        async def _do_loot():
            if won_total > 0:
                pet = await user_data_manager.get_pet_data_async(str(uid), ps.user.display_name)
                if pet:
                    loot = await LootCalculator.award_gambling_loot(uid, pet, difficulty="normal", win_streak=ps.win_streak, source="craps")
                    if loot:
                        return f"\n💎 {ps.user.display_name}: {', '.join(loot)}"
            return None

        async def _do_stats():
            if won_total > 0 or lost_total > 0:
                winnings = won_total - lost_total
                try:
                    await user_data_manager.update_pet_gambling_stats(
                        str(uid),
                        "craps",
                        winnings,
                        bet_amount=max_bet
                    )
                except Exception:
                    pass

        results = await asyncio.gather(_do_loot(), _do_stats())
        return results[0]

    async def _resolve_bets(self, roll: int, event: str) -> List[str]:
        # Events: come_out_win, come_out_loss, point_established, point_win, point_continue, seven_out
        
        d1, d2 = self.last_roll
        is_hard = d1 == d2
        
        # Standard Rules: Place Bets and Hardways are OFF during Come Out roll
        is_come_out = self.point is None
        
        loot_messages = []
        io_tasks = []

        for uid, ps in self.players.items():
            if ps.left_game: continue
            
            new_bets = []
            won_total = 0
            lost_total = 0
            max_bet = 0
            
            for bet in ps.bets:
                max_bet = max(max_bet, bet.amount)
                win = False
                loss = False
                stay_up = False # If true, bet remains on table after winning (Place/Hardways)
                payout_ratio = 1.0 # Profit multiplier (1.0 means 1:1 payout)
                
                # --- Pass Line ---
                if bet.bet_type == BetType.PASS_LINE:
                    if event == "come_out_win": win = True
                    elif event == "come_out_loss": loss = True
                    elif event == "point_win": win = True
                    elif event == "seven_out": loss = True
                    
                # --- Don't Pass ---
                elif bet.bet_type == BetType.DONT_PASS:
                    if event == "come_out_win": loss = True
                    elif event == "come_out_loss": 
                        if roll == 12: pass # Push
                        else: win = True
                    elif event == "point_win": loss = True
                    elif event == "seven_out": win = True
                    
                # --- Field (Always Working) ---
                elif bet.bet_type == BetType.FIELD:
                    if roll in (3, 4, 9, 10, 11):
                        win = True
                    elif roll in (2, 12):
                        win = True
                        payout_ratio = 2.0
                    else:
                        loss = True
                        
                # --- Place Bets (OFF on Come Out) ---
                elif bet.bet_type in (BetType.PLACE_4, BetType.PLACE_5, BetType.PLACE_6, BetType.PLACE_8, BetType.PLACE_9, BetType.PLACE_10):
                    if not is_come_out:
                        target = int(bet.bet_type.value.split(" ")[1])
                        if roll == target:
                            win = True
                            stay_up = True
                            if target in (4, 10): payout_ratio = 9/5
                            elif target in (5, 9): payout_ratio = 7/5
                            elif target in (6, 8): payout_ratio = 7/6
                        elif roll == 7:
                            loss = True

                # --- Any 7 (Always Working) ---
                elif bet.bet_type == BetType.ANY_7:
                    if roll == 7: win = True; payout_ratio = 4.0
                    else: loss = True
                    
                # --- Hardways (OFF on Come Out) ---
                elif bet.bet_type in (BetType.HARD_4, BetType.HARD_6, BetType.HARD_8, BetType.HARD_10):
                    if not is_come_out:
                        target = int(bet.bet_type.value.split(" ")[1])
                        if roll == target and is_hard:
                            win = True
                            stay_up = True
                            if target in (6, 8): payout_ratio = 9.0
                            elif target in (4, 10): payout_ratio = 7.0
                        elif roll == 7 or (roll == target and not is_hard):
                            loss = True
                    
                # --- Resolution ---
                if win:
                    profit = int(bet.amount * payout_ratio)
                    # If staying up, we only pay profit. If not, we pay profit + principal (return bet).
                    payout = profit if stay_up else (bet.amount + profit)
                    
                    if self.betting_mode:
                        ps.bankroll += payout
                    won_total += profit
                    
                    if stay_up:
                        new_bets.append(bet)
                elif loss:
                    lost_total += bet.amount
                else:
                    new_bets.append(bet) # Keep bet (Push, or not resolved yet)
                    
            ps.bets = new_bets
            
            # Save Stats and Loot (Queue for async gather)
            if self.betting_mode:
                # Update Win Streak
                if won_total > 0:
                    ps.win_streak += 1
                elif lost_total > 0 and won_total == 0:
                    ps.win_streak = 0
                
                if won_total > 0 or lost_total > 0:
                    io_tasks.append(self._handle_player_io(uid, ps, won_total, lost_total, max_bet))

        # Execute all I/O in parallel
        if io_tasks:
            results = await asyncio.gather(*io_tasks)
            for r in results:
                if r:
                    loot_messages.append(r)

        return loot_messages

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.danger, custom_id="craps_leave")
    async def btn_leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.leave_table(interaction)

    @discord.ui.button(label="Join", style=discord.ButtonStyle.secondary, custom_id="craps_join")
    async def btn_join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.table_open:
            await interaction.response.send_message("Table closed.", ephemeral=True)
            return
        
        if not self.betting_mode:
            await self.join_table(interaction, None)
        else:
            modal = discord.ui.Modal(title="Buy In")
            amount_input = discord.ui.TextInput(label="Buy In XP", placeholder="Enter XP", min_length=1, max_length=7)
            modal.add_item(amount_input)
            async def on_submit(inter: discord.Interaction):
                try:
                    amt = int(str(amount_input.value or "0").strip())
                    if amt <= 0:
                        await inter.response.send_message("Invalid amount.", ephemeral=True)
                        return
                    await self.join_table(inter, amt)
                except Exception:
                    await inter.response.send_message("Invalid number.", ephemeral=True)
            modal.on_submit = on_submit
            await interaction.response.send_modal(modal)
