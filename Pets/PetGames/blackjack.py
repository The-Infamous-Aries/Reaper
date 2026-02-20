import discord
from discord.ext import commands
import random
import asyncio
from functools import partial
from typing import Awaitable, Any, Callable, cast, Coroutine, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass

from Systems.Functions import emoji as emoji_mod
from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.pet_brain import LootCalculator
from Systems.Functions.ai_gambling import get_blackjack_bot_action, _hand_value

def _value_of(code: str) -> int:
    r = code[1:]
    if r == "J" or r == "Q" or r == "K":
        return 10
    if r == "1":
        return 11
    try:
        return int(r)
    except Exception:
        return 0

def _card_codes() -> List[str]:
    ranks = ["1","2","3","4","5","6","7","8","9","10","J","Q","K"]
    suits = ["H","D","C","S"]
    out: List[str] = []
    for s in suits:
        for r in ranks:
            out.append(f"{s}{r}")
    return out

def _mention(code: str) -> str:
    m = emoji_mod.mention(code)
    return m or code



@dataclass
class BotMember:
    id: int
    display_name: str
    mention: str

    def __hash__(self):
        return hash(self.id)
    
    def __eq__(self, other):
        return isinstance(other, BotMember) and self.id == other.id

class PlayerState:
    def __init__(self, user: Union[discord.Member, BotMember], mode_betting: bool):
        self.user = user
        self.mode_betting = mode_betting
        self.hands: List[List[str]] = [[]]
        self.bets: List[int] = [0]
        self.active_hand_index = 0
        self.standing_hands: List[bool] = [False]
        self.busted_hands: List[bool] = [False]
        self.blackjacks: List[bool] = [False]
        self.left_game = False

        self.loot_message = ""
        self.win_streak = 0

    def can_split(self) -> bool:
        h = self.hands[self.active_hand_index]
        if len(h) != 2:
            return False
        if h[0][1:] != h[1][1:]:
            return False
        if len(self.hands) >= 4:
            return False

        return True

    def can_double(self) -> bool:
        if not self.mode_betting:
            return False
        h = self.hands[self.active_hand_index]
        return len(h) == 2

    def is_all_done(self) -> bool:
        for i in range(len(self.hands)):
            if not self.standing_hands[i] and not self.busted_hands[i]:
                return False
        return True

class BlackjackSession(discord.ui.View):
    def __init__(self, bot: commands.Bot, channel_id: int, solo: bool, betting_mode: bool, buy_in: int, host: discord.Member, bot_count: int = 0):
        super().__init__(timeout=900)
        self.bot = bot
        self.channel_id = channel_id
        self.solo = solo
        self.betting_mode = betting_mode
        self.host = host
        self.players: Dict[int, PlayerState] = {}
        self.dealer_hand: List[str] = []
        self.deck: List[str] = []
        self.message: Optional[discord.Message] = None
        self.round_active = False
        self.waiting_for_bets = False
        self.current_player_order: List[int] = []
        self.turn_index = 0

        self.table_open = not solo
        self._init_deck()
        self.players[host.id] = PlayerState(host, betting_mode)
        
        # Add Bots
        for i in range(bot_count):
            bot_id = -(i + 1)
            bot_name = f"Bot {i+1}"
            bot_member = BotMember(bot_id, bot_name, bot_name)
            self.players[bot_id] = PlayerState(bot_member, betting_mode)

    def _init_deck(self) -> None:
        self.deck = _card_codes() * 4
        random.shuffle(self.deck)

    def _draw(self) -> str:
        if not self.deck:
            self._init_deck()
        return self.deck.pop()

    def _reset_round(self) -> None:
        self.dealer_hand = []
        for ps in self.players.values():
            ps.hands = [[]]
            ps.bets = [0]
            ps.active_hand_index = 0
            ps.standing_hands = [False]
            ps.busted_hands = [False]
            ps.blackjacks = [False]
        self.current_player_order = [uid for uid, ps in self.players.items() if not ps.left_game]
        random.shuffle(self.current_player_order)
        self.turn_index = 0
        self.round_active = True
        self.waiting_for_bets = self.betting_mode
        
        # Bot Bets
        if self.betting_mode:
            for uid, ps in self.players.items():
                if isinstance(ps.user, BotMember) and not ps.left_game:
                    ps.bets[0] = 10
    
    async def on_timeout(self):
        pass

    async def start_round(self, interaction: Optional[discord.Interaction]) -> None:
        self._reset_round()
        if self.waiting_for_bets:
            if interaction and not interaction.response.is_done():
                await interaction.response.edit_message(embed=await self._build_bets_embed(), view=self)
            elif self.message:
                await self.message.edit(embed=await self._build_bets_embed(), view=self)
            return
        await self._deal_initial(interaction)

    async def _build_bets_embed(self) -> discord.Embed:
        bj_emoji = emoji_mod.mention('Blackjack') or "♠️"
        e = discord.Embed(title=f"{bj_emoji} Blackjack Bets", color=discord.Color.blurple(), timestamp=discord.utils.utcnow())
        for uid in self.current_player_order:
            ps = self.players.get(uid)
            if not ps or ps.left_game:
                continue

            total_xp = 0
            if not isinstance(ps.user, BotMember):
                pet_data = await user_data_manager.get_pet_data_async(str(ps.user.id), ps.user.display_name)
                if pet_data:
                    lvl = int(pet_data.get("level", 1))
                    total_xp = int(pet_data.get("experience", 0)) + int(LootCalculator.get_total_experience_for_level(lvl))

            val_str = f"Total XP: {total_xp} • Bet {ps.bets[0]} XP"
            if ps.loot_message:
                val_str += f"\n{ps.loot_message}"
            e.add_field(name=ps.user.display_name, value=val_str, inline=False)
        e.set_footer(text="Submit bet or Leave. Round starts after all bets are placed.")
        return e

    def _current_player_id(self) -> Optional[int]:
        if self.turn_index < len(self.current_player_order):
            return self.current_player_order[self.turn_index]
        return None

    def _build_table_embed(self) -> discord.Embed:
        bj_emoji = emoji_mod.mention('Blackjack') or "♠️"
        e = discord.Embed(title=f"{bj_emoji} Blackjack", color=discord.Color.dark_green(), timestamp=discord.utils.utcnow())
        
        # Dealer Hand Logic
        dealer_cards_list = self.dealer_hand
        dealer_total, _ = _hand_value(dealer_cards_list)
        dealer_display = ""
        hide_hole = self.round_active and self.turn_index < len(self.current_player_order)
        
        if hide_hole and len(dealer_cards_list) >= 2:
            # Show first card, hide second
            first_card = _mention(dealer_cards_list[0])
            card_back = emoji_mod.mention("CardBack") or "🂠"
            dealer_display = f"{first_card} {card_back}"
            # Show value of first card only or just "?"
            v1 = _value_of(dealer_cards_list[0])
            e.add_field(name=f"Dealer- {v1} + ?", value=dealer_display, inline=False)
        else:
            dealer_display = " ".join([_mention(c) for c in dealer_cards_list])
            e.add_field(name=f"Dealer- {dealer_total}", value=dealer_display, inline=False)

        for uid in self.current_player_order:
            ps = self.players.get(uid)
            if not ps or ps.left_game:
                continue
            
            player_name = f"{ps.user.display_name}"
            if ps.left_game:
                player_name += " (Left)"
            
            # Only show total bet, not individual hands
            bet_value = f"Bet: {ps.bets[0]} XP" if self.betting_mode else ""
            e.add_field(name=player_name, value=bet_value, inline=False)
        return e

    async def _send_player_hand_ephemerally(self, interaction: discord.Interaction, player_state: PlayerState) -> None:
        if player_state.user.id != interaction.user.id:
            return # Only send ephemeral message to the player whose turn it is

        hand_info = []
        for i, hand in enumerate(player_state.hands):
            hand_value, _ = _hand_value(hand)
            hand_display = " ".join([_mention(card) for card in hand])
            bet_display = f"{player_state.bets[i]} XP" if self.betting_mode else ""
            hand_info.append(f"Hand {i+1}: {hand_display} ({hand_value}) {bet_display}")
        
        await interaction.followup.send(f"Your hands:\n" + "\n".join(hand_info), ephemeral=True)

    async def _deal_initial(self, interaction: Optional[discord.Interaction]) -> None:
        for _ in range(2):
            for uid in self.current_player_order:
                ps = self.players.get(uid)
                if ps and not ps.left_game:
                    ps.hands[0].append(self._draw())
            self.dealer_hand.append(self._draw())
        for uid in self.current_player_order:
            ps = self.players.get(uid)
            if ps:
                v, _ = _hand_value(ps.hands[0])
                ps.blackjacks[0] = v == 21 and len(ps.hands[0]) == 2
                if ps.blackjacks[0]:
                    ps.standing_hands[0] = True
        
        # Send initial player hands ephemerally
        if interaction:
            for uid, ps in self.players.items():
                if not isinstance(ps.user, BotMember) and not ps.left_game:
                    await self._send_player_hand_ephemerally(interaction, ps)

        # Build view with buttons using PartialEmoji
        self.clear_items()
        
        hit_emoji = emoji_mod.get_partial('Yes')
        stand_emoji = emoji_mod.get_partial('No')
        double_emoji = emoji_mod.get_partial('dub')
        split_emoji = emoji_mod.get_partial('split')
        leave_emoji = emoji_mod.get_partial('exit')
        
        hit_btn: discord.ui.Button = discord.ui.Button(label="Hit", style=discord.ButtonStyle.success, emoji=hit_emoji, custom_id="bj_hit")
        stand_btn: discord.ui.Button = discord.ui.Button(label="Stand", style=discord.ButtonStyle.secondary, emoji=stand_emoji, custom_id="bj_stand")
        double_btn: discord.ui.Button = discord.ui.Button(label="Double", style=discord.ButtonStyle.primary, emoji=double_emoji, custom_id="bj_double")
        split_btn: discord.ui.Button = discord.ui.Button(label="Split", style=discord.ButtonStyle.primary, emoji=split_emoji, custom_id="bj_split")
        leave_btn: discord.ui.Button = discord.ui.Button(label="Leave", style=discord.ButtonStyle.danger, emoji=leave_emoji, custom_id="bj_leave")
        
        hit_btn.callback = lambda i: self.handle_action(i, "hit")
        stand_btn.callback = lambda i: self.handle_action(i, "stand")
        double_btn.callback = lambda i: self.handle_action(i, "double")
        split_btn.callback = lambda i: self.handle_action(i, "split")
        leave_btn.callback = lambda i: self.handle_action(i, "leave")
        
        self.add_item(hit_btn)
        self.add_item(stand_btn)
        self.add_item(double_btn)
        self.add_item(split_btn)
        self.add_item(leave_btn)
        
        if interaction and not interaction.response.is_done():
            await interaction.response.edit_message(embed=self._build_table_embed(), view=self)
        elif self.message:
            await self.message.edit(embed=self._build_table_embed(), view=self)

        await self._advance_turn_or_hand(interaction)

    async def handle_action(self, interaction: discord.Interaction, action: str) -> None:
        uid = interaction.user.id
        current_uid = self._current_player_id()
        if action == "leave":
             await self.leave_table(interaction)
             return

        if uid != current_uid:
            await interaction.response.send_message(f"{emoji_mod.mention('Deny')} Not your turn.", ephemeral=True)
            return
        ps = self.players.get(uid)
        if not ps:
            await interaction.response.send_message(f"{emoji_mod.mention('Deny')} Player not found.", ephemeral=True)
            return
        if action == "hit":
            ps.hands[ps.active_hand_index].append(self._draw())
            v, _ = _hand_value(ps.hands[ps.active_hand_index])
            if v > 21:
                ps.busted_hands[ps.active_hand_index] = True
                await self._advance_turn_or_hand(interaction)
            else:
                await interaction.response.edit_message(embed=self._build_table_embed(), view=self)
        elif action == "stand":
            ps.standing_hands[ps.active_hand_index] = True
            await self._advance_turn_or_hand(interaction)
        elif action == "double":
            if not ps.can_double():
                await interaction.response.send_message("Cannot double.", ephemeral=True)
                return
            
            amt = ps.bets[ps.active_hand_index]

            pet_data = await user_data_manager.get_pet_data_async(str(interaction.user.id), interaction.user.display_name)
            if not pet_data:
                await interaction.response.send_message("No pet found.", ephemeral=True)
                return
            
            lvl = int(pet_data.get("level", 1))
            total_xp = int(pet_data.get("experience", 0)) + int(LootCalculator.get_total_experience_for_level(lvl))

            if amt > total_xp:
                await interaction.response.send_message("Insufficient XP to double down.", ephemeral=True)
                return

            await LootCalculator.apply_xp_change(interaction.user.id, -amt, source="blackjack_double")
            ps.bets[ps.active_hand_index] += amt
            ps.hands[ps.active_hand_index].append(self._draw())
            v, _ = _hand_value(ps.hands[ps.active_hand_index])
            if v > 21:
                ps.busted_hands[ps.active_hand_index] = True
            ps.standing_hands[ps.active_hand_index] = True
            await self._advance_turn_or_hand(interaction)
        elif action == "split":
            if not ps.can_split():
                await interaction.response.send_message("Cannot split.", ephemeral=True)
                return

            amt = ps.bets[ps.active_hand_index]
            if self.betting_mode:
                pet_data = await user_data_manager.get_pet_data_async(str(interaction.user.id), interaction.user.display_name)
                if not pet_data:
                    await interaction.response.send_message("No pet found.", ephemeral=True)
                    return
            
                lvl = int(pet_data.get("level", 1))
                total_xp = int(pet_data.get("experience", 0)) + int(LootCalculator.get_total_experience_for_level(lvl))

                if amt > total_xp:
                    await interaction.response.send_message("Insufficient XP to split.", ephemeral=True)
                    return
                
                await LootCalculator.apply_xp_change(interaction.user.id, -amt, source="blackjack_split")

            h = ps.hands[ps.active_hand_index]
            first = [h[0], self._draw()]
            second = [h[1], self._draw()]
            ps.hands[ps.active_hand_index] = first
            ps.hands.append(second)
            ps.bets.append(amt if self.betting_mode else 0)
            ps.standing_hands.append(False)
            ps.busted_hands.append(False)
            ps.blackjacks.append(False)
            await interaction.response.edit_message(embed=self._build_table_embed(), view=self)

    async def _on_hit(self, interaction: discord.Interaction):
        await self.handle_action(interaction, "hit")

    async def _on_stand(self, interaction: discord.Interaction):
        await self.handle_action(interaction, "stand")

    async def _on_double(self, interaction: discord.Interaction):
        await self.handle_action(interaction, "double")

    async def _on_split(self, interaction: discord.Interaction):
        await self.handle_action(interaction, "split")

    async def _on_leave(self, interaction: discord.Interaction):
        await self.handle_action(interaction, "leave")

    async def _play_bot_turn(self, ps: PlayerState) -> None:
        await asyncio.sleep(1)
        while ps.active_hand_index < len(ps.hands):
            if ps.blackjacks[ps.active_hand_index]:
                ps.standing_hands[ps.active_hand_index] = True
                ps.active_hand_index += 1
                continue

            while True:
                hand = ps.hands[ps.active_hand_index]
                val, _ = _hand_value(hand)
                if val >= 21:
                    if val > 21:
                        ps.busted_hands[ps.active_hand_index] = True
                    else:
                        ps.standing_hands[ps.active_hand_index] = True
                    break

                dealer_card = self.dealer_hand[0] if self.dealer_hand else None
                if not dealer_card:
                    ps.standing_hands[ps.active_hand_index] = True
                    break
                
                can_double = ps.can_double() and self.betting_mode
                action = get_blackjack_bot_action(hand, dealer_card, can_double)

                if action == "hit":
                    await asyncio.sleep(1.5)
                    hand.append(self._draw())
                    if self.message:
                        await self.message.edit(embed=self._build_table_embed(), view=self)
                elif action == "double":
                    amt = ps.bets[ps.active_hand_index]
                    ps.bets[ps.active_hand_index] += amt
                    hand.append(self._draw())
                    val, _ = _hand_value(hand)
                    if val > 21:
                        ps.busted_hands[ps.active_hand_index] = True
                    ps.standing_hands[ps.active_hand_index] = True
                    break
                else: # stand
                    ps.standing_hands[ps.active_hand_index] = True
                    break
            
            if not ps.busted_hands[ps.active_hand_index] and not ps.standing_hands[ps.active_hand_index]:
                ps.standing_hands[ps.active_hand_index] = True

            ps.active_hand_index += 1
        
        await self._advance_turn_or_hand(None)

    async def _advance_turn_or_hand(self, interaction: Optional[discord.Interaction]) -> None:
        uid = self._current_player_id()
        ps = self.players.get(uid) if uid is not None else None
        if ps:
            if ps.active_hand_index + 1 < len(ps.hands):
                ps.active_hand_index += 1
                if interaction and not interaction.response.is_done():
                    await interaction.response.edit_message(embed=self._build_table_embed(), view=self)
                elif self.message:
                    await self.message.edit(embed=self._build_table_embed(), view=self)
                return
        
        # Find next player
        while self.turn_index < len(self.current_player_order):
            cur = self.current_player_order[self.turn_index]
            cur_ps = self.players.get(cur)
            if cur_ps and not cur_ps.is_all_done():
                # Found active player
                if isinstance(cur_ps.user, BotMember):
                    # Update UI to show it's bot's turn
                    if interaction and not interaction.response.is_done():
                        await interaction.response.edit_message(embed=self._build_table_embed(), view=self)
                    elif self.message:
                        await self.message.edit(embed=self._build_table_embed(), view=self)
                    
                    # Start bot turn
                    asyncio.create_task(self._play_bot_turn(cur_ps))
                    return
                else:
                    # Human player found
                    break
            self.turn_index += 1
            
        if self.turn_index >= len(self.current_player_order):
            await self._dealer_play_and_settle(interaction)
        else:
            if interaction and not interaction.response.is_done():
                await interaction.response.edit_message(embed=self._build_table_embed(), view=self)
            elif self.message:
                await self.message.edit(embed=self._build_table_embed(), view=self)

    async def _dealer_play_and_settle(self, interaction: Optional[discord.Interaction]) -> None:
        while True:
            v, soft = _hand_value(self.dealer_hand)
            if v < 17 or (soft and v == 17):
                self.dealer_hand.append(self._draw())
                if self.message:
                    await self.message.edit(embed=self._build_table_embed(), view=self)
                await asyncio.sleep(1.5) # 1.5-2 second delay as requested
                continue
            break
        await self._settle_round()
        self.round_active = False
        self.table_open = False
        if self.betting_mode:
            for ps in self.players.values():
                if ps.left_game:
                    continue
                ps.bets = [0] + ps.bets[1:]
            self.waiting_for_bets = True
            
            # Bot Bets for next round
            for uid, ps in self.players.items():
                 if isinstance(ps.user, BotMember) and not ps.left_game:
                     ps.bets[0] = 10

            if interaction and not interaction.response.is_done():
                await interaction.response.edit_message(embed=await self._build_bets_embed(), view=self)
            elif self.message:
                await self.message.edit(embed=await self._build_bets_embed(), view=self)
        else:
            if interaction and not interaction.response.is_done():
                await interaction.response.edit_message(embed=self._build_table_embed(), view=self)
            elif self.message:
                await self.message.edit(embed=self._build_table_embed(), view=self)
        
        await asyncio.sleep(0.5)
        if self.betting_mode:
            if interaction and not interaction.response.is_done():
                 await interaction.followup.send("Place bets for next round or leave.", ephemeral=False)
            elif self.message and self.channel_id:
                 # Can't use followup easily without interaction, maybe send new message?
                 # Or just rely on embed update.
                 pass
        self.table_open = not self.solo

    async def _handle_player_io(self, uid: int, ps: PlayerState, total_change: int, max_bet: int) -> Optional[str]:
        async def _do_loot():
            if total_change > 0 and not isinstance(ps.user, BotMember):
                pet_data = await user_data_manager.get_pet_data_async(str(uid), ps.user.display_name)
                if pet_data:
                    return await LootCalculator.award_gambling_loot(uid, pet_data, win_streak=ps.win_streak)
            return None

        async def _do_stats():
            try:
                await user_data_manager.update_pet_gambling_stats(
                    str(uid),
                    "blackjack",
                    int(total_change),
                    bet_amount=int(max_bet or 0)
                )
            except Exception:
                pass

        results = await asyncio.gather(_do_loot(), _do_stats())
        loot = results[0]
        
        if loot:
            return "\n".join(loot)
        return None

    async def _settle_round(self) -> None:
        dealer_total, _ = _hand_value(self.dealer_hand)
        dealer_bust = dealer_total > 21
        dealer_bj = dealer_total == 21 and len(self.dealer_hand) == 2

        io_tasks: List[Awaitable[Any]] = []
        player_io_map = {} # uid -> index in io_tasks

        for uid in list(self.current_player_order):
            ps = self.players.get(uid)
            if not ps:
                continue
            total_change = 0
            max_bet_this_round = 0
            for i, hand in enumerate(ps.hands):
                bet = ps.bets[i]
                if bet > max_bet_this_round:
                    max_bet_this_round = bet
                hv, _ = _hand_value(hand)
                player_bj = ps.blackjacks[i]
                
                payout_mult = 0.0
                if dealer_bj:
                    if player_bj:
                        payout_mult = 1.0 # Push
                    else:
                        payout_mult = 0.0 # Lose
                else:
                    if player_bj:
                        payout_mult = 2.5 # Win 3:2 (return bet + 1.5 bet)
                    elif hv > 21:
                        payout_mult = 0.0 # Bust
                    elif dealer_bust:
                        payout_mult = 2.0 # Win
                    elif hv > dealer_total:
                        payout_mult = 2.0 # Win
                    elif hv == dealer_total:
                        payout_mult = 1.0 # Push
                    else:
                        payout_mult = 0.0 # Lose
                
                if self.betting_mode:
                    payout = int(bet * payout_mult)
                    change = payout - bet
                    total_change += change

                    if change != 0 and not isinstance(ps.user, BotMember):
                        await LootCalculator.apply_xp_change(uid, change, source="blackjack_round")

            if self.betting_mode:
                # Update Win Streak
                if total_change > 0:
                    ps.win_streak += 1
                elif total_change < 0:
                    ps.win_streak = 0
                

            
                # Bot stats are not saved
                if not isinstance(ps.user, BotMember):
                    if total_change != 0:
                        player_io_map[uid] = len(io_tasks)
                        io_tasks.append(self._handle_player_io(uid, ps, total_change, max_bet_this_round))
        
        # Run I/O in parallel
        if io_tasks:
            results = await asyncio.gather(*io_tasks)
            for uid, ps in self.players.items():
                if uid in player_io_map:
                    msg = results[player_io_map[uid]]
                    if msg:
                         ps.loot_message += "\n" + msg

    async def join_table(self, interaction: discord.Interaction) -> None:
        if self.solo:
            await interaction.response.send_message("Solo game.", ephemeral=True)
            return
        if interaction.user.id in self.players and not self.players[interaction.user.id].left_game:
            await interaction.response.send_message("Already joined.", ephemeral=True)
            return

        pet = await user_data_manager.get_pet_data_async(str(interaction.user.id), interaction.user.display_name)
        if not pet:
            await interaction.response.send_message("No pet.", ephemeral=True)
            return

        self.players[interaction.user.id] = PlayerState(cast(discord.Member, interaction.user), self.betting_mode)
        if interaction.response.is_done():
            await interaction.followup.send(f"{interaction.user.mention} joined.", ephemeral=False)
        else:
            await interaction.response.send_message(f"{interaction.user.mention} joined.", ephemeral=False)

    async def leave_table(self, interaction: discord.Interaction) -> None:
        ps = self.players.get(interaction.user.id)
        if not ps:
            await interaction.response.send_message("Not in game.", ephemeral=True)
            return
        ps.left_game = True
        await interaction.response.send_message("Left game.", ephemeral=True)



    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary, custom_id="bj_hit")
    async def btn_hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action(interaction, "hit")

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary, custom_id="bj_stand")
    async def btn_stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action(interaction, "stand")

    @discord.ui.button(label="Double Down", style=discord.ButtonStyle.success, custom_id="bj_double")
    async def btn_double(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action(interaction, "double")

    @discord.ui.button(label="Split", style=discord.ButtonStyle.danger, custom_id="bj_split")
    async def btn_split(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action(interaction, "split")

    @discord.ui.button(label="Join", style=discord.ButtonStyle.success, custom_id="bj_join")
    async def btn_join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.table_open:
            await interaction.response.send_message("Table closed.", ephemeral=True)
            return
        await self.join_table(interaction)

    @discord.ui.button(label="Bet", style=discord.ButtonStyle.primary, custom_id="bj_bet")
    async def btn_bet(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.betting_mode or not self.waiting_for_bets:
            await interaction.response.send_message("Betting not available.", ephemeral=True)
            return
        ps = self.players.get(interaction.user.id)
        if not ps or ps.left_game:
            await interaction.response.send_message("Not at table.", ephemeral=True)
            return

        pet_data = await user_data_manager.get_pet_data_async(str(interaction.user.id), interaction.user.display_name)
        if not pet_data:
            await interaction.response.send_message("No pet found.", ephemeral=True)
            return

        lvl = int(pet_data.get("level", 1))
        total_xp = int(pet_data.get("experience", 0)) + int(LootCalculator.get_total_experience_for_level(lvl))

        modal = discord.ui.Modal(title="Round Bet")
        bet_input: discord.ui.TextInput = discord.ui.TextInput(label="Bet XP", placeholder=f"Total XP: {total_xp}", min_length=1, max_length=7)
        modal.add_item(bet_input)
        async def on_submit(inter: discord.Interaction):
            try:
                b = int(str(bet_input.value or "0").strip())
            except Exception:
                await inter.response.send_message("Invalid bet.", ephemeral=True)
                return

            pet_data = await user_data_manager.get_pet_data_async(str(interaction.user.id), interaction.user.display_name)
            if not pet_data:
                await inter.response.send_message("No pet found.", ephemeral=True)
                return
            
            lvl = int(pet_data.get("level", 1))
            total_xp = int(pet_data.get("experience", 0)) + int(LootCalculator.get_total_experience_for_level(lvl))

            if b <= 0 or b > total_xp:
                await inter.response.send_message("Bet exceeds total XP.", ephemeral=True)
                return
            
            await LootCalculator.apply_xp_change(interaction.user.id, -b, source="blackjack_bet")
            ps.bets[0] = b

            all_set = True
            for uid in self.current_player_order:
                st = self.players.get(uid)
                if st and not st.left_game and (st.bets[0] or 0) <= 0:
                    all_set = False
                    break
            if self.message:
                await self.message.edit(embed=await self._build_bets_embed(), view=self)
            if all_set:
                self.waiting_for_bets = False
                if self.message:
                    await self._deal_initial(inter)
        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.secondary, custom_id="bj_leave")
    async def btn_leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.leave_table(interaction)
        if self.message:
            await self.message.edit(embed=self._build_table_embed(), view=self)
            