import discord
from discord.ext import commands
import random
import asyncio
from typing import Dict, List, Optional, Tuple, Any

from Systems.Functions import emoji as emoji_mod
from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.pet_brain import LootCalculator

RANKS = ["1","2","3","4","5","6","7","8","9","10","J","Q","K"]
SUITS = ["H","D","C","S"]

def _mention(code: str) -> str:
    m = emoji_mod.mention(code)
    return m or code

def _card_codes() -> List[str]:
    out: List[str] = []
    for s in SUITS:
        for r in RANKS:
            out.append(f"{s}{r}")
    return out

def _rank_value(r: str) -> int:
    if r == "1":
        return 14
    if r == "J":
        return 11
    if r == "Q":
        return 12
    if r == "K":
        return 13
    try:
        return int(r)
    except Exception:
        return 0

def _hand_rank(hole: List[str], community: List[str]) -> Tuple[int, List[int]]:
    cards = hole + community
    ranks = [_rank_value(c[1:]) for c in cards]
    suits = [c[0] for c in cards]
    counts: Dict[int,int] = {}
    for v in ranks:
        counts[v] = counts.get(v, 0) + 1
    sorted_ranks = sorted(ranks, reverse=True)
    is_flush = False
    for s in SUITS:
        if sum(1 for c in suits if c == s) >= 5:
            is_flush = True
            break
    uniq = sorted(set(ranks))
    straights: List[int] = []
    if 14 in uniq:
        uniq.append(1)
    uniq_sorted = sorted(uniq)
    streak = 1
    last = None
    best_st = 0
    for v in uniq_sorted:
        if last is None:
            streak = 1
        else:
            if v == last + 1:
                streak += 1
            else:
                streak = 1
        last = v
        if streak >= 5:
            best_st = v
    is_straight = best_st > 0
    four = [v for v,c in counts.items() if c == 4]
    trips = [v for v,c in counts.items() if c == 3]
    pairs = [v for v,c in counts.items() if c == 2]
    if is_flush and is_straight:
        return 8, [best_st]
    if len(four) >= 1:
        kicker = max([v for v in ranks if v != four[0]])
        return 7, [max(four), kicker]
    if len(trips) >= 1 and len(pairs) >= 1:
        return 6, [max(trips), max(pairs)]
    if is_flush:
        top5 = sorted_ranks[:5]
        return 5, top5
    if is_straight:
        return 4, [best_st]
    if len(trips) >= 1:
        kickers = [v for v in sorted_ranks if v != max(trips)]
        return 3, [max(trips)] + kickers[:2]
    if len(pairs) >= 2:
        top2 = sorted(pairs, reverse=True)[:2]
        kicker = max([v for v in sorted_ranks if v not in top2])
        return 2, top2 + [kicker]
    if len(pairs) == 1:
        pairv = pairs[0]
        kickers = [v for v in sorted_ranks if v != pairv][:3]
        return 1, [pairv] + kickers
    return 0, sorted_ranks[:5]

class MockMember:
    def __init__(self, uid: int, name: str):
        self.id = uid
        self.display_name = name
        self.mention = f"@{name}"
        self.bot = True

    async def send(self, content):
        pass

class PlayerState:
    def __init__(self, user: Any, bankroll: int, is_bot: bool = False):
        self.user = user
        self.bankroll = bankroll
        self.hole: List[str] = []
        self.folded = False
        self.round_bets: Dict[str, int] = {"predeal": 0, "preflop": 0, "flop": 0, "turn": 0, "river": 0}
        self.left_table = False
        self.is_bot = is_bot
        self.win_streak = 0

    def total_bet(self) -> int:
        return sum(int(v or 0) for v in self.round_bets.values())

class BettingView(discord.ui.View):
    def __init__(self, session: 'HoldemSession', player: PlayerState, call_amount: int):
        super().__init__(timeout=60)
        self.session = session
        self.player = player
        self.call_amount = call_amount
        self._setup_buttons()

    def _setup_buttons(self):
        self.clear_items()
        
        # Bet/Raise Button
        bet_emoji = emoji_mod.get_partial('Casino')
        bet_btn = discord.ui.Button(label="Bet/Raise", style=discord.ButtonStyle.success, emoji=bet_emoji)
        bet_btn.callback = self.btn_bet_callback
        self.add_item(bet_btn)

        # Call/Check Button
        call_emoji = emoji_mod.get_partial('Hit')
        if self.call_amount == 0:
            label = "Check"
            style = discord.ButtonStyle.secondary
        else:
            label = f"Call ({self.call_amount})"
            style = discord.ButtonStyle.primary
        
        call_btn = discord.ui.Button(label=label, style=style, emoji=call_emoji)
        call_btn.callback = self.btn_call_callback
        self.add_item(call_btn)

        # Fold Button
        fold_emoji = emoji_mod.get_partial('No')
        fold_btn = discord.ui.Button(label="Fold", style=discord.ButtonStyle.danger, emoji=fold_emoji)
        fold_btn.callback = self.btn_fold_callback
        self.add_item(fold_btn)

    async def btn_bet_callback(self, interaction: discord.Interaction):
        modal = discord.ui.Modal(title="Bet Amount")
        # Determine min raise
        min_raise = 50
        if self.call_amount > 0:
            min_raise = self.call_amount * 2
            
        bet_input = discord.ui.TextInput(
            label="Amount", 
            placeholder=f"Min {min_raise}, Max {self.player.bankroll}", 
            min_length=1, 
            max_length=7
        )
        modal.add_item(bet_input)
        
        async def on_submit(inter: discord.Interaction):
            try:
                amt = int(bet_input.value)
                if amt > self.player.bankroll:
                    await inter.response.send_message("Insufficient funds.", ephemeral=True)
                    return
                current_stage_bet = self.player.round_bets.get(self.session.round_stage, 0)
                total_to_put_in = amt
                if amt < self.call_amount:
                     await inter.response.send_message(f"Must at least call {self.call_amount}.", ephemeral=True)
                     return
                     
                await self.session.process_bet(self.player, amt, inter)
            except ValueError:
                await inter.response.send_message("Invalid number.", ephemeral=True)
                
        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

    async def btn_call_callback(self, interaction: discord.Interaction):
        if self.call_amount > self.player.bankroll:
             await self.session.process_bet(self.player, self.player.bankroll, interaction)
        else:
             await self.session.process_bet(self.player, self.call_amount, interaction)

    async def btn_fold_callback(self, interaction: discord.Interaction):
        await self.session.process_fold(self.player, interaction)

class HoldemSession(discord.ui.View):
    def __init__(self, bot: commands.Bot, channel_id: int, solo: bool, buy_in: int, host: discord.Member, bots: int = 0):
        super().__init__(timeout=900)
        self.bot = bot
        self.channel_id = channel_id
        self.solo = solo
        self.host = host
        self.buy_in_amt = buy_in
        self.players: Dict[int, PlayerState] = {}
        self.community: List[str] = []
        self.deck: List[str] = []
        self.message: Optional[discord.Message] = None
        self.table_open = not solo
        self.round_stage = "idle"
        self.current_order: List[int] = []
        self.turn_index = 0
        self.last_aggressor = -1 
        self.highest_bet = 0      
        self.buy_in_applied: Dict[int, int] = {}
        self._init_deck()
        self._setup_session_buttons()
        asyncio.create_task(self._apply_buy_in(host, buy_in))
        self.players[host.id] = PlayerState(host, buy_in)
        
        for i in range(bots):
            bid = -100 - i
            bname = f"Bot {i+1}"
            buser = MockMember(bid, bname)
            self.players[bid] = PlayerState(buser, buy_in, is_bot=True)

    async def _apply_buy_in(self, user: discord.Member, amount: int) -> None:
        await LootCalculator.apply_xp_change(user.id, -amount, source="holdem_buyin")
        self.buy_in_applied[user.id] = amount

    def _init_deck(self) -> None:
        self.deck = _card_codes() * 1
        random.shuffle(self.deck)

    def _draw(self) -> str:
        if not self.deck:
            self._init_deck()
        return self.deck.pop()

    def _build_table_embed(self) -> discord.Embed:
        casino_emoji = emoji_mod.mention('Casino') or "🎰"
        e = discord.Embed(title=f"{casino_emoji} Texas Hold'em {casino_emoji}", color=discord.Color.dark_red(), timestamp=discord.utils.utcnow())
        
        # Community
        if self.community:
            comm = " ".join([_mention(c) for c in self.community])
        else:
            cb = emoji_mod.mention("CardBack") or "[?]"
            comm = " ".join([cb] * 5)
        e.add_field(name="Community Cards", value=comm, inline=False)
        
        pot = sum(p.total_bet() for p in self.players.values())

        lines: List[str] = []
        cb = emoji_mod.mention("CardBack") or "[?]"
        
        for uid in self.current_order if self.current_order else self.players.keys():
            p = self.players.get(uid)
            if not p or p.left_table:
                continue
            
            status = ""
            if p.folded:
                status = f" ({emoji_mod.mention('No')} Folded)"
            elif self.round_stage != "idle" and self.round_stage != "finished":
                if self.current_order and self.current_order[self.turn_index] == uid:
                    thinking_emoji = emoji_mod.mention('Thinking') or "🟢"
                    status = f" {thinking_emoji} **Thinking...**"
            
            cards_display = ""
            if not p.folded and self.round_stage not in ["idle", "finished"]:
                cards_display = f" {cb}{cb}"
            
            lines.append(f"{p.user.display_name}{cards_display} • Bank {p.bankroll} • Bet {p.total_bet()}{status}")

        if lines:
            e.add_field(name="Players", value="\n".join(lines), inline=False)
            
        stage_display = self.round_stage.title()
        if self.round_stage == "predeal": stage_display = "Shuffling"
        
        e.set_footer(text=f"Stage: {stage_display} • Pot {pot} XP")
        return e

    async def update_message(self, interaction: Optional[discord.Interaction] = None):
        embed = self._build_table_embed()
        
        self.clear_items()
        if self.round_stage == "idle":
            self.add_item(self.btn_join_ref)
            self.add_item(self.btn_start_ref)
            self.add_item(self.btn_leave_ref)
        elif self.round_stage == "finished":
            self.add_item(self.btn_join_ref)
            self.add_item(self.btn_start_ref)
            self.add_item(self.btn_leave_ref)
        else:
            self.add_item(self.btn_show_hand_ref)
            
        if interaction and not interaction.response.is_done():
            await interaction.response.edit_message(embed=embed, view=self)
        elif self.message:
            await self.message.edit(embed=embed, view=self)

    async def start_hand(self, interaction: Optional[discord.Interaction]) -> None:
        self.community = []
        self.deck = []
        self._init_deck()
        for ps in self.players.values():
            ps.hole = []
            ps.folded = False
            ps.round_bets = {"predeal": 0, "preflop": 0, "flop": 0, "turn": 0, "river": 0}

        self.current_order = [uid for uid, ps in self.players.items() if not ps.left_table and ps.bankroll > 0]
        if len(self.current_order) < 2:
            if interaction:
                await interaction.response.send_message("Not enough players.", ephemeral=True)
            return

        random.shuffle(self.current_order)
        self.round_stage = "preflop"
        self.highest_bet = 0
        
        for uid in self.current_order:
            self.players[uid].hole = [self._draw(), self._draw()]
        
        self.turn_index = 0
        self.last_aggressor = 0 # Index
        
        await self.update_message(interaction)
        await self.next_turn()

    async def next_turn(self):
        active = [uid for uid in self.current_order if not self.players[uid].folded]
        if len(active) == 1:
            await self.end_hand(active)
            return
      
        current_uid = self.current_order[self.turn_index]
        player = self.players[current_uid]       
        needs_to_call = self.highest_bet - player.round_bets.get(self.round_stage, 0)
        
        if self.turn_index == self.last_aggressor and needs_to_call == 0:
            await self.advance_phase()
            return
            
        if player.folded or player.bankroll == 0:
            self.turn_index = (self.turn_index + 1) % len(self.current_order)
            not_all_in = [uid for uid in active if self.players[uid].bankroll > 0]
            if not not_all_in:
                 await self.advance_phase()
                 return
            
            await asyncio.sleep(0.5) 
            await self.next_turn()
            return

        await self.update_message()
        
        if player.is_bot:
            await asyncio.sleep(1.5) # Thinking time
            await self.ai_turn(player)
        else:
            pass

    async def ai_turn(self, player: PlayerState):
        current_bet = player.round_bets.get(self.round_stage, 0)
        to_call = self.highest_bet - current_bet
        
        rank, values = _hand_rank(player.hole, self.community)
        
        action = "fold"
        amt = 0
        
        # Logic
        if self.round_stage == "preflop":
            if rank >= 1 or max(values) >= 12: # Pair or Q+
                if to_call == 0: action = "check"
                else: action = "call"
                
                # Random raise
                if rank >= 1 and random.random() < 0.4:
                    action = "raise"
                    amt = to_call + 50
            else:
                if to_call == 0: action = "check"
                elif to_call <= 50 and random.random() < 0.3: action = "call"
                else: action = "fold"
        else:
            # Post flop
            if rank >= 2: # Two pair or better
                action = "raise"
                amt = to_call + 100
            elif rank == 1: # Pair
                if to_call < 200: action = "call"
                else: action = "fold"
            else:
                if to_call == 0: action = "check"
                else: action = "fold"
                
        # Execute
        if action == "fold":
            await self.process_fold(player, None)
        elif action in ["check", "call"]:
            await self.process_bet(player, to_call, None)
        elif action == "raise":
            if amt > player.bankroll: amt = player.bankroll
            await self.process_bet(player, amt, None)

    async def process_bet(self, player: PlayerState, amount: int, interaction: Optional[discord.Interaction]):
        if amount > player.bankroll:
            amount = player.bankroll
        
        player.bankroll -= amount
        current_round_bet = player.round_bets.get(self.round_stage, 0)
        player.round_bets[self.round_stage] = current_round_bet + amount
        
        new_total = player.round_bets[self.round_stage]
        if new_total > self.highest_bet:
            self.highest_bet = new_total
            self.last_aggressor = self.current_order.index(player.user.id if not player.is_bot else player.user.id)
            
        msg = f"{player.user.display_name} bets/calls {amount}."
        if interaction:
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            pass
            
        self.turn_index = (self.turn_index + 1) % len(self.current_order)
        await self.next_turn()

    async def process_fold(self, player: PlayerState, interaction: Optional[discord.Interaction]):
        player.folded = True
        msg = f"{player.user.display_name} folds."
        if interaction:
            await interaction.response.send_message(msg, ephemeral=True)
            
        self.turn_index = (self.turn_index + 1) % len(self.current_order)
        await self.next_turn()

    async def advance_phase(self):
        self.turn_index = 0
        self.last_aggressor = 0
        self.highest_bet = 0
        
        if self.round_stage == "preflop":
            self.round_stage = "flop"
            self._draw() # Burn
            self.community.extend([self._draw(), self._draw(), self._draw()])
        elif self.round_stage == "flop":
            self.round_stage = "turn"
            self._draw()
            self.community.append(self._draw())
        elif self.round_stage == "turn":
            self.round_stage = "river"
            self._draw()
            self.community.append(self._draw())
        elif self.round_stage == "river":
            active = [uid for uid in self.current_order if not self.players[uid].folded]
            await self.end_hand(active)
            return
            
        await self.update_message()
        await self.next_turn()

    async def _handle_player_io(self, uid: int, amount: int, won: bool, highest_bet: int) -> Optional[str]:
        ps = self.players.get(uid)
        
        async def _do_loot():
            if won and ps:
                pet_data = await user_data_manager.get_pet_data_async(str(uid), ps.user.display_name)
                if pet_data:
                    loot = await LootCalculator.award_gambling_loot(uid, pet_data, difficulty="normal", win_streak=ps.win_streak, source="holdem")
                    if loot:
                        return f"{ps.user.display_name}: {', '.join(loot)}"
            return None

        async def _do_stats():
            try:
                await user_data_manager.update_pet_gambling_stats(
                    str(uid),
                    "holdem",
                    amount,
                    bet_amount=highest_bet
                )
            except Exception:
                pass

        results = await asyncio.gather(_do_loot(), _do_stats())
        return results[0]

    async def end_hand(self, winners_pool: List[int]):
        # Showdown
        self.round_stage = "finished"
        
        results: List[Tuple[int, Tuple[int, List[int]]]] = []
        for uid in winners_pool:
            ps = self.players.get(uid)
            rk = _hand_rank(ps.hole, self.community)
            results.append((uid, rk))
            
        results.sort(key=lambda x: (x[1][0], x[1][1]), reverse=True)
        
        winners: List[int] = []
        if results:
            top = results[0][1]
            for uid, rk in results:
                if rk == top:
                    winners.append(uid)
                    
        pot = sum(p.total_bet() for p in self.players.values())
        share = pot // max(1, len(winners))
        
        win_text = []
        loot_text = []
        
        io_tasks = []

        for uid in winners:
            self.players[uid].bankroll += share
            win_text.append(self.players[uid].user.display_name)
            self.players[uid].win_streak += 1
            
            if not self.players[uid].is_bot:
                highest_bet = 0
                ps = self.players.get(uid)
                if ps:
                    for v in ps.round_bets.values():
                        if v > highest_bet: highest_bet = v
                
                io_tasks.append(self._handle_player_io(uid, share, True, highest_bet))
                
        for uid in self.current_order:
            if uid not in winners:
                self.players[uid].win_streak = 0
                if not self.players[uid].is_bot:
                    lost = self.players[uid].total_bet()
                    
                    highest_bet = 0
                    ps = self.players.get(uid)
                    if ps:
                        for v in ps.round_bets.values():
                            if v > highest_bet: highest_bet = v
                    
                    io_tasks.append(self._handle_player_io(uid, -lost, False, highest_bet))

        if io_tasks:
            results = await asyncio.gather(*io_tasks)
            for r in results:
                if r:
                    loot_text.append(r)

        embed = self._build_table_embed()
        embed.add_field(name="Winners", value=f"{', '.join(win_text)} won {share} XP!", inline=False)
        if loot_text:
            embed.add_field(name="Loot Found", value="\n".join(loot_text), inline=False)
        
        hand_lines = []
        for uid in winners_pool:
            p = self.players[uid]
            h_str = f"{_mention(p.hole[0])} {_mention(p.hole[1])}"
            hand_lines.append(f"{p.user.display_name}: {h_str}")
        embed.add_field(name="Showdown", value="\n".join(hand_lines), inline=False)
        
        if self.message:
            await self.message.edit(embed=embed, view=self)

    async def update_stats(self, uid: int, amount: int, won: bool):
        try:
            ps = self.players.get(uid)
            highest_bet = 0
            if ps:
                for v in ps.round_bets.values():
                    if v > highest_bet: highest_bet = v

            await user_data_manager.update_pet_gambling_stats(
                str(uid),
                "holdem",
                amount,
                bet_amount=highest_bet
            )
        except Exception:
            pass

    async def _cash_out(self, user: Any, amount: int) -> None:
        if isinstance(user, MockMember): return
        await LootCalculator.apply_xp_change(user.id, amount, source="holdem_cashout")

    @discord.ui.button(label="Join", style=discord.ButtonStyle.success, custom_id="holdem_join")
    async def btn_join(self, interaction: discord.Interaction, button: discord.ui.Button):
        # ... (implementation will be updated in _setup_session_buttons)
        pass

    @discord.ui.button(label="Start", style=discord.ButtonStyle.success, custom_id="holdem_start")
    async def btn_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.secondary, custom_id="holdem_leave")
    async def btn_leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="Show Hand", style=discord.ButtonStyle.primary, custom_id="holdem_show", row=1)
    async def btn_show_hand(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass
    
    def _setup_session_buttons(self):
        self.clear_items()
        
        # Join Button
        join_emoji = emoji_mod.get_partial('Plus')
        self.btn_join_ref = discord.ui.Button(label="Join", style=discord.ButtonStyle.success, emoji=join_emoji)
        self.btn_join_ref.callback = self.btn_join_callback
        
        # Start Button
        start_emoji = emoji_mod.get_partial('Yes')
        self.btn_start_ref = discord.ui.Button(label="Start", style=discord.ButtonStyle.success, emoji=start_emoji)
        self.btn_start_ref.callback = self.btn_start_callback
        
        # Leave Button
        leave_emoji = emoji_mod.get_partial('No')
        self.btn_leave_ref = discord.ui.Button(label="Leave", style=discord.ButtonStyle.secondary, emoji=leave_emoji)
        self.btn_leave_ref.callback = self.btn_leave_callback
        
        # Show Hand Button
        show_emoji = emoji_mod.get_partial('Search')
        self.btn_show_hand_ref = discord.ui.Button(label="Show Hand", style=discord.ButtonStyle.primary, emoji=show_emoji, row=1)
        self.btn_show_hand_ref.callback = self.btn_show_hand_callback

    async def btn_join_callback(self, interaction: discord.Interaction):
        if self.solo:
            await interaction.response.send_message("Solo game.", ephemeral=True)
            return
        if not self.table_open:
            await interaction.response.send_message("Table closed.", ephemeral=True)
            return
        if interaction.user.id in self.players and not self.players[interaction.user.id].left_table:
            await interaction.response.send_message("Already joined.", ephemeral=True)
            return
            
        modal = discord.ui.Modal(title="Buy In")
        amount_input = discord.ui.TextInput(label="Buy In XP", placeholder="Enter XP", min_length=1, max_length=7)
        modal.add_item(amount_input)
        async def on_submit(inter: discord.Interaction):
            try:
                amt = int(str(amount_input.value or "0").strip())
            except Exception:
                await inter.response.send_message("Invalid number.", ephemeral=True)
                return
            
            pet = await user_data_manager.get_pet_data_async(str(interaction.user.id), interaction.user.display_name)
            if not pet:
                await inter.response.send_message("No pet.", ephemeral=True)
                return
            lvl = int(pet.get("level", 1))
            total = int(pet.get("experience", 0)) + int(LootCalculator.get_total_experience_for_level(lvl))
            if amt <= 0 or amt > total:
                await inter.response.send_message(f"Buy in exceeds total XP ({total}).", ephemeral=True)
                return
                
            await self._apply_buy_in(interaction.user, amt)
            self.players[interaction.user.id] = PlayerState(interaction.user, amt)
            await self.update_message()
            await inter.response.send_message(f"Joined with {amt} XP.", ephemeral=True)
        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

    async def btn_start_callback(self, interaction: discord.Interaction):
        if self.round_stage != "idle" and self.round_stage != "finished":
            await interaction.response.send_message("Game in progress.", ephemeral=True)
            return
        await self.start_hand(interaction)

    async def btn_leave_callback(self, interaction: discord.Interaction):
        ps = self.players.get(interaction.user.id)
        if not ps:
            await interaction.response.send_message("Not in game.", ephemeral=True)
            return
        await self._cash_out(interaction.user, ps.bankroll)
        ps.left_table = True
        await interaction.response.send_message("Left table. XP cashed out.", ephemeral=True)
        await self.update_message()

    async def btn_show_hand_callback(self, interaction: discord.Interaction):
        ps = self.players.get(interaction.user.id)
        if not ps or ps.left_table:
            await interaction.response.send_message("You are not in the game.", ephemeral=True)
            return
        
        cards = " ".join([_mention(c) for c in ps.hole])
        msg = f"**Your Hand:** {cards}\n"

        is_turn = False
        if self.round_stage not in ["idle", "finished"] and not ps.folded:
            if self.current_order and self.current_order[self.turn_index] == interaction.user.id:
                is_turn = True
        
        if is_turn:
            current_bet = ps.round_bets.get(self.round_stage, 0)
            to_call = self.highest_bet - current_bet
            msg += f"\nIt is your turn! To Call: {to_call} XP."
            view = BettingView(self, ps, to_call)
            await interaction.response.send_message(msg, view=view, ephemeral=True)
        else:
            msg += "\n(Waiting for your turn...)"
            await interaction.response.send_message(msg, ephemeral=True)
    
    async def on_timeout(self):
        for ps in list(self.players.values()):
            if not ps.left_table and not ps.is_bot:
                try:
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

    def _setup_buttons(self):
        self.btn_map = {}
        for child in self.children:
            if hasattr(child, "custom_id"):
                self.btn_map[child.custom_id] = child
        
        self.btn_join_ref = self.btn_map.get("holdem_join")
        self.btn_start_ref = self.btn_map.get("holdem_start")
        self.btn_leave_ref = self.btn_map.get("holdem_leave")
        self.btn_show_hand_ref = self.btn_map.get("holdem_show")
