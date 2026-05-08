import discord
from discord.ext import commands
import random
import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any, cast

logger = logging.getLogger(__name__)

from Systems.Functions import emoji as emoji_mod
from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.pet_brain import LootCalculator
from Systems.Functions.ai_gambling import get_holdem_bot_action, get_hand_rank

RANKS = ["1","2","3","4","5","6","7","8","9","10","J","Q","K"]
SUITS = ["H","D","C","S"]

def _mention(code: str) -> str:
    m = emoji_mod.mention(code)
    return m or code

class MockMember:
    def __init__(self, uid: int, name: str):
        self.id = uid
        self.display_name = name
        self.mention = f"@{name}"
        self.bot = True

    async def send(self, content):
        pass

RANKS = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]
SUITS = ["H","D","C","S"]

class PlayerState:
    def __init__(self, user: Any, is_bot: bool = False):
        self.user = user
        self.hole: List[str] = []
        self.folded = False
        self.round_bets: Dict[str, int] = {"predeal": 0, "preflop": 0, "flop": 0, "turn": 0, "river": 0}
        self.left_table = False
        self.is_bot = is_bot
        self.win_streak = 0
        self.bankroll: int = 0

    def total_bet(self) -> int:
        return sum(int(v or 0) for v in self.round_bets.values())

class BettingView(discord.ui.View):
    def __init__(self, session: 'HoldemSession', player: PlayerState, call_amount: int):
        super().__init__(timeout=60)
        self.session = session
        self.player = player
        self.call_amount = call_amount



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
        try:
            class BetModal(discord.ui.Modal, title="Bet Amount"):
                def __init__(self, session: 'HoldemSession', player: PlayerState, call_amount: int, min_raise: int, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.session = session
                    self.player = player
                    self.call_amount = call_amount
                    
                    self.bet_input: discord.ui.TextInput = discord.ui.TextInput(
                        label="Amount", 
                        placeholder=f"Min {min_raise}", 
                        min_length=1, 
                        max_length=7
                    )
                    self.add_item(self.bet_input)

                async def on_submit(self, inter: discord.Interaction):
                    try:
                        amt = int(self.bet_input.value)
                        if amt < self.call_amount:
                            await inter.response.send_message(f"Must at least call {self.call_amount}.", ephemeral=True)
                            return
                            
                        await self.session.process_bet(self.player, amt, inter)
                    except ValueError:
                        await inter.response.send_message("Invalid number.", ephemeral=True)
                    except Exception as e:
                        logger.error(f"Error in BetModal.on_submit: {e}")
                        await inter.response.send_message(f"An unexpected error occurred while processing your bet: {e}", ephemeral=True)
            
            # Determine min raise
            min_raise = 50
            if self.call_amount > 0:
                min_raise = self.call_amount * 2
                
            modal = BetModal(self.session, self.player, self.call_amount, min_raise)
            await interaction.response.send_modal(modal)
        except Exception as e:
            logger.error(f"Error in btn_bet_callback: {e}")
            await interaction.response.send_message(f"An unexpected error occurred while initiating bet: {e}", ephemeral=True)

    async def btn_call_callback(self, interaction: discord.Interaction):
        try:
            await self.session.process_bet(self.player, self.call_amount, interaction)
        except Exception as e:
            logger.error(f"Error in btn_call_callback: {e}")
            await interaction.response.send_message(f"An unexpected error occurred while processing your call: {e}", ephemeral=True)

    async def btn_fold_callback(self, interaction: discord.Interaction):
        try:
            await self.session.process_fold(self.player, interaction)
        except Exception as e:
            logger.error(f"Error in btn_fold_callback: {e}")
            await interaction.response.send_message(f"An unexpected error occurred while processing your fold: {e}", ephemeral=True)

class HoldemSession(discord.ui.View):
    def __init__(self, bot: commands.Bot, channel_id: int, solo: bool, host: discord.Member, bots: int = 0, buy_in: int = 500, fun_mode: bool = False):
        super().__init__(timeout=900)
        logger.debug(f"HoldemSession initialized for channel {channel_id} by {host.display_name} (Solo: {solo}, Bots: {bots})")
        self.bot = bot
        self.channel_id = channel_id
        self.solo = solo
        self.host = host
        self.buy_in_amt: int = max(100, buy_in)
        self.fun_mode: bool = fun_mode
        self.players: dict[int, PlayerState] = {}
        self.table_open: bool = True


        # Define buttons for game management
        self._init_deck()
        self.round_stage: str = "idle"  # "idle", "betting", "flop", "turn", "river", "finished"
        self.bet_amount: int = 0
        self.pot: int = 0
        self.community_cards: list[str] = []
        self.current_order: list[int] = []  # Order of players for betting rounds
        self.turn_index: int = 0  # Index of the current player whose turn it is
        self.last_bet: int = 0
        self.last_better: int | None = None
        self.bots_to_add = bots

        self.community: List[str] = []
        self.message: Optional[discord.Message] = None
        self._setup_buttons() # Call setup to populate button references

    def _card_codes(self) -> list[str]:
        out: list[str] = []
        for s in SUITS:
            for r in RANKS:
                out.append(f"{s}{r}")
        return out

    def _init_deck(self) -> None:
        self.deck = self._card_codes() * 4
        random.shuffle(self.deck)

    def _draw(self) -> str:
        if not self.deck:
            self._init_deck()
        return self.deck.pop()


    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item):
        logger.error(f"HoldemSession on_error caught an exception in {getattr(item, 'custom_id', 'unknown')}: {error}", exc_info=True)
        if interaction.response.is_done():
            await interaction.followup.send(f"An unexpected error occurred: {error}", ephemeral=True)
        else:
            await interaction.response.send_message(f"An unexpected error occurred: {error}", ephemeral=True)




    async def send_initial_message(self, ctx: commands.Context):        # Have the host join the game implicitly
        try:
            success, message = await self._join_player(self.host)
            if not success:
                # Handle error if host can't join for some reason (e.g., insufficient funds)
                await ctx.send(f"Error: {message}")
                return
            
            # Add bots to the game
            try:
                for i in range(self.bots_to_add):
                    bid = -100 - (i + 1) # Ensure unique negative IDs for bots
                    bname = f"Bot {i+1}"
                    buser = MockMember(bid, bname)
                    self.players[bid] = PlayerState(buser, is_bot=True)
            except Exception as e:
                logger.error(f"Error adding bot to the game: {e}")
                await ctx.send(f"An unexpected error occurred while adding bots: {e}")
                return

            # Send the initial message with the embed and view
            embed = self._build_table_embed()
            self.message = await ctx.send(embed=embed, view=self)
            
            await self.update_message() # Update the message to reflect bots (and host if applicable)
        except Exception as e:
            logger.error(f"Error in send_initial_message: {e}")
            await ctx.send(f"An unexpected error occurred while setting up the game: {e}")

    async def btn_join_action(self, interaction: discord.Interaction):
        logger.debug(f"btn_join_callback triggered by {interaction.user.display_name} (ID: {interaction.user.id})")
        await interaction.response.defer(ephemeral=True)
        try:
            user_id = interaction.user.id
            user_display_name = interaction.user.display_name

            logger.debug(f"Attempting to join player {user_display_name} (ID: {user_id}) to game session {self.host.id}")
            success, message = await self._join_player(cast(discord.Member, interaction.user))
            
            if success:
                logger.debug(f"Player {user_display_name} (ID: {user_id}) successfully joined. Message: {message}")
                await interaction.followup.send(message, ephemeral=False)
                await self.update_message()  # Update the public message to reflect the new player
            else:
                logger.debug(f"Player {user_display_name} (ID: {user_id}) failed to join. Message: {message}")
                await interaction.followup.send(message, ephemeral=True)
        except Exception as e:
            logger.error(f"Error in btn_join_callback: {e}")
            await interaction.followup.send(f"An unexpected error occurred while joining the game: {e}", ephemeral=True)

    async def btn_start_action(self, interaction: discord.Interaction):
        logger.debug(f"btn_start_callback triggered by {interaction.user.display_name} (ID: {interaction.user.id})")
        await interaction.response.defer(ephemeral=True)

        # 1. Check if the interaction user is the host
        if interaction.user.id != self.host.id:
            logger.debug(f"User {interaction.user.display_name} (ID: {interaction.user.id}) tried to start game but is not host (Host ID: {self.host.id}).")
            await interaction.followup.send("Only the host can start the game.", ephemeral=True)
            return

        # 2. Check if there are enough players
        # Filter out bots from the count for this check if desired, or count all.
        # Assuming for now 'players' includes host and any joined users, plus initial bots.
        # The game requires at least 2 non-folded players to start a hand.
        # For starting the game, let's check for at least 2 human players (or 1 human + 1 bot)
        # The start_hand function itself has a check for len(self.current_order) < 2
        # So we can rely on that or add a more specific check here.
        active_players = [p for p in self.players.values() if not p.is_bot and not p.left_table]
        total_players = len(active_players) + len([p for p in self.players.values() if p.is_bot and not p.left_table])
        if total_players < 2:
            logger.debug(f"Not enough players to start game. Current players: {total_players}")
            await interaction.followup.send("Need at least 2 players (including bots) to start the game.", ephemeral=True)
            return
        
        # 3. Prevent starting if game is already in progress
        if self.round_stage != "idle":
            logger.debug(f"Game start failed: Game already in progress (Stage: {self.round_stage}).")
            await interaction.followup.send("The game has already started or is in progress.", ephemeral=True)
            return

        # 4. If solo, this button shouldn't be available (handled by update_message, but good to double check)
        if self.solo:
            await interaction.followup.send("This is a solo game, it starts automatically.", ephemeral=True)
            return

        # 5. Call start_hand
        try:
            await interaction.followup.send("Starting the game...", ephemeral=False)
            await self.start_hand(interaction)
        except Exception as e:
            logger.error(f"Error in btn_start_callback: {e}")
            await interaction.followup.send(f"An unexpected error occurred while trying to start the game: {e}", ephemeral=True)

    async def btn_leave_action(self, interaction: discord.Interaction):
        logger.debug(f"btn_leave_callback triggered by {interaction.user.display_name} (ID: {interaction.user.id})")
        try:
            await interaction.response.defer(ephemeral=True)

            user_id = interaction.user.id
            user_display_name = interaction.user.display_name

            # 1. Check if the player is in the game
            if user_id not in self.players:
                await interaction.followup.send("You are not in this game.", ephemeral=True)
                return

            player_state = self.players[user_id]

            # 2. Prevent leaving if the game is in progress and player has active bets or cards
            if self.round_stage != "idle" and self.round_stage != "finished":
                # If a player leaves during an active round, they forfeit their current bets and cards
                # and are marked as left_table. Their bankroll remains as is.
                player_state.left_table = True
                player_state.folded = True # Automatically fold if leaving during a round
                await interaction.followup.send(f"You have left the table. Any current bets are forfeited.", ephemeral=True)
                # Need to update turn if it was this player's turn
                if self.current_order and self.current_order[self.turn_index] == user_id:
                    self.turn_index = (self.turn_index + 1) % len(self.current_order)
                    await self.next_turn() # Advance the turn
                
            else: # Game is idle or finished
                await interaction.followup.send("You have left the game.", ephemeral=True)
                
                del self.players[user_id]
                # If the host leaves, end the session or pass host to another player
                if user_id == self.host.id:
                    await interaction.followup.send("The host has left, ending the game session.", ephemeral=False)
                    # This will stop the view and end the game
                    self.stop()
                    return

            await self.update_message() # Update the public message
        except Exception as e:
            logger.error(f"Error in btn_leave_callback: {e}")
            await interaction.followup.send(f"An unexpected error occurred while leaving the game: {e}", ephemeral=True)

    async def btn_show_hand_action(self, interaction: discord.Interaction):
        logger.debug(f"btn_show_hand_callback triggered by {interaction.user.display_name} (ID: {interaction.user.id})")
        try:
            await interaction.response.defer(ephemeral=True)

            user_id = interaction.user.id

            # 1. Check if the player is in the game
            if user_id not in self.players:
                await interaction.followup.send("You are not currently in this game.", ephemeral=True)
                return

            player_state = self.players[user_id]

            # 2. Check if it's an active round (i.e., not idle or finished)
            if self.round_stage == "idle" or self.round_stage == "finished":
                await interaction.followup.send("You can only show your hand during an active round.", ephemeral=True)
                return

            # 3. Check if the player has hole cards
            if not player_state.hole:
                await interaction.followup.send("You don't have any cards yet.", ephemeral=True)
                return
            
            # 4. Display the player's hand
            hand_display = " ".join([_mention(c) for c in player_state.hole])
            await interaction.followup.send(f"Your hand: {hand_display}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in btn_show_hand_callback: {e}")
            await interaction.followup.send(f"An unexpected error occurred while showing your hand: {e}", ephemeral=True)

    async def _join_player(self, user: discord.Member) -> tuple[bool, str]:
        """
        Helper method to handle the logic of a player joining the game.
        Returns a tuple: (success: bool, message: str)
        """
        user_id = user.id
        user_display_name = user.display_name

        if self.round_stage != "idle":
            return False, "You can only join before the game starts."

        if user_id in self.players:
            return False, "You are already in this game."

        # Deduct buy-in XP for real players
        if not self.fun_mode:
            pet = await user_data_manager.get_pet_data_async(str(user_id), user_display_name)
            if not pet:
                return False, "You need a pet to play."
            lvl = int(pet.get("level", 1))
            total_xp = int(LootCalculator.get_total_experience_for_level(lvl)) + int(pet.get("experience", 0))
            if total_xp < self.buy_in_amt:
                return False, f"Not enough XP. Need {self.buy_in_amt:,}, have {total_xp:,}."
            await LootCalculator.apply_xp_change(user_id, -self.buy_in_amt, source="holdem_buyin")

        player_state = PlayerState(user)
        player_state.bankroll = self.buy_in_amt
        self.players[user_id] = player_state

        return True, f"{user_display_name} has joined the game!"



    async def process_bet(self, player: PlayerState, amount: int, interaction: Optional[discord.Interaction]):
        user_display_name = player.user.display_name
        current_player_bet = player.round_bets.get(self.round_stage, 0)
        bet_increase = amount - current_player_bet

        if bet_increase < 0:
            if interaction:
                await interaction.followup.send("You cannot decrease your bet.", ephemeral=True)
            return

        if player.bankroll < bet_increase:
            if interaction:
                await interaction.followup.send("Insufficient funds for this bet.", ephemeral=True)
            return

        # Deduct from player bankroll
        player.bankroll -= bet_increase
        player.round_bets[self.round_stage] = amount
        self.pot += bet_increase # Add to the pot immediately

        if amount > self.last_bet: # It's a raise
            self.last_bet = amount
            self.last_better = player.user.id
            if interaction:
                await interaction.followup.send(f"{user_display_name} raised to {amount}.", ephemeral=False)
        elif amount == self.last_bet: # It's a call
            if interaction:
                await interaction.followup.send(f"{user_display_name} called {amount}.", ephemeral=False)
        else: # It's a check (amount == 0 and last_bet == 0)
            if interaction:
                await interaction.followup.send(f"{user_display_name} checked.", ephemeral=False)

        await self.update_message()

    async def process_fold(self, player: PlayerState, interaction: Optional[discord.Interaction]):
        player.folded = True
        if interaction:
            await interaction.followup.send(f"{player.user.display_name} folded.", ephemeral=False)
        else:
            # For bots, just log or send a general message to the channel
            await cast(discord.TextChannel, await self.bot.fetch_channel(self.channel_id)).send(f"{player.user.display_name} folded.")
        await self.update_message()

    async def _deal_community_cards(self, count: int):
        for _ in range(count):
            self.community.append(self._draw())
        await self.update_message()

    async def _determine_winner(self):
        """
        Determines the winner(s) of the hand, distributes the pot, and announces the results.
        """
        self.round_stage = "finished" # End the game round
        await self.update_message() # Update embed to show all cards

        active_players = [p for p in self.players.values() if not p.folded and not p.left_table]

        if len(active_players) == 1: # If only one player left, they win the pot
            winner = active_players[0]
            await self.channel.send(f"{winner.user.mention} wins the pot of {self.pot} XP by default!")
            await LootCalculator.apply_xp_change(winner.user.id, self.pot, source="holdem_win")
            self.pot = 0
            await self._reset_hand()
            return
        
        # Evaluate hands for all active players
        best_hand_rank = (-1, [])
        winners = []

        for player in active_players:
            hand_rank = self._hand_rank(player.hole, self.community)
            if hand_rank > best_hand_rank:
                best_hand_rank = hand_rank
                winners = [player]
            elif hand_rank == best_hand_rank:
                winners.append(player)

        # Announce winner(s)
        if winners:
            winner_mentions = ", ".join([w.user.mention for w in winners])
            winning_hand_display = self._hand_rank_to_string(best_hand_rank[0]) # Need a helper for this
            
            if len(winners) == 1:
                await self.channel.send(f"{winner_mentions} wins the pot of {self.pot} XP with a {winning_hand_display}!")
            else:
                await self.channel.send(f"It's a split pot! {winner_mentions} share the pot of {self.pot} XP with a {winning_hand_display}!")
            
            pot_per_winner = self.pot // len(winners)
            for winner in winners:
                await LootCalculator.apply_xp_change(winner.user.id, pot_per_winner, source="holdem_win")

        self.pot = 0 # Pot is distributed
        await self._reset_hand()

    def _hand_rank_to_string(self, rank: int) -> str:
        ranks_map = {
            0: "High Card",
            1: "One Pair",
            2: "Two Pair",
            3: "Three of a Kind",
            4: "Straight",
            5: "Flush",
            6: "Full House",
            7: "Four of a Kind",
            8: "Straight Flush"
        }
        return ranks_map.get(rank, "Unknown Hand")

    async def _reset_hand(self):
        self.deck = self._card_codes() * 1 # Reinitialize and shuffle deck
        random.shuffle(self.deck)
        self.community = []
        self.pot = 0
        self.bet_amount = 0
        self.last_bet = 0
        self.last_better = None
        self.current_order = []
        self.turn_index = 0
        for player_id in self.players:
            player = self.players[player_id]
            player.hole = []
            player.folded = False
            player.round_bets = {"predeal": 0, "preflop": 0, "flop": 0, "turn": 0, "river": 0}

    async def _deal_hole_cards(self):
        active_players = [p for p in self.players.values() if not p.left_table]
        for _ in range(2): # Deal two cards
            for player in active_players:
                if not player.folded: # Only deal to players who haven't folded
                    player.hole.append(self._draw())
    
    async def _send_hole_cards_ephemerally(self):
        for player in self.players.values():
            if not player.is_bot and not player.folded and not player.left_table:
                hand_display = " ".join([self._mention(c) for c in player.hole])
                try:
                    await player.user.send(f"Your hand: {hand_display}")
                except discord.Forbidden:
                    # Bot cannot send messages to this user
                    pass

    async def start_hand(self, interaction: discord.Interaction):
        try:
            if self.round_stage != "idle":
                await interaction.followup.send("A hand is already in progress.", ephemeral=True)
                return

            active_players = [p for p in self.players.values() if not p.left_table]
            if len(active_players) < 2:
                await interaction.followup.send("Not enough players to start a hand (minimum 2).", ephemeral=True)
                return

            await self._reset_hand()
            self.round_stage = "preflop"
            
            # Establish player order for this hand
            self.current_order = [p.user.id for p in active_players]
            random.shuffle(self.current_order) # Randomize starting player

            await self._deal_hole_cards()
            await self._send_hole_cards_ephemerally()

            await self.update_message() # Update public message with card backs
            await self._start_betting_round() # Start the pre-flop betting round
        except Exception as e:
            logger.error(f"Error in start_hand: {e}")
            await interaction.followup.send(f"An unexpected error occurred while starting the hand: {e}", ephemeral=True)

    async def _start_betting_round(self):
        try:
            """
            Manages a single betting round.
            """
            self.last_bet = 0  # Reset last bet for the new round
            self.last_better = None # Reset last better
            self.turn_index = 0 # Start from the first player in order
            current_stage_players = [p_id for p_id in self.current_order if not self.players[p_id].folded and not self.players[p_id].left_table]

            if len(current_stage_players) <= 1: # If only one player left, no betting needed
                await self._advance_round()
                return

            # Loop until betting round is complete
            while True:
                current_player_id = self.current_order[self.turn_index]
                player_state = self.players[current_player_id]

                if player_state.folded or player_state.left_table:
                    self.turn_index = (self.turn_index + 1) % len(self.current_order)
                    continue

                # Determine call amount
                current_player_bet_in_stage = player_state.round_bets.get(self.round_stage, 0)
                call_amount = max(0, self.last_bet - current_player_bet_in_stage)

                if player_state.is_bot:
                    # Implement basic bot logic here
                    await asyncio.sleep(2) # Simulate bot thinking
                    if call_amount == 0: # Bot can check or bet
                        if random.random() < 0.5: # 50% chance to check
                            await self.process_bet(player_state, 0, None) # Check
                        else:
                            bet_amount = random.randint(50, 200) # Small bet
                            await self.process_bet(player_state, bet_amount, None)
                    elif random.random() < 0.6: # 60% chance to call
                        await self.process_bet(player_state, call_amount, None)
                    elif random.random() < 0.8: # 20% chance to raise
                        raise_amount = random.randint(call_amount + 1, call_amount + self.buy_in_amt) # Raise a bit
                        await self.process_bet(player_state, raise_amount, None)
                    else: # 20% chance to fold
                        await self.process_fold(player_state, None)
                else:
                    # Human player's turn
                    betting_view = BettingView(self, player_state, call_amount)
                    try:
                        await self.message.edit(embed=self._build_table_embed(), view=betting_view) # Update message with betting view
                        await betting_view.wait() # Wait for player action
                    except asyncio.TimeoutError:
                        player_state.folded = True
                        await self.channel.send(f"{player_state.user.display_name} timed out and folded.")

                # Check if betting round is complete
                active_in_round = [p for p in self.players.values() if not p.folded and not p.left_table]
                if len(active_in_round) <= 1: # All but one folded
                    break

                # Check if all active players have matched the highest bet
                all_matched = True
                for p in active_in_round:
                    if p.user.id == self.last_better: # The last better doesn't need to act again
                        continue
                    if p.round_bets.get(self.round_stage, 0) < self.last_bet:
                        all_matched = False
                        break
                
                if all_matched and self.last_better is not None: # All matched and someone actually bet
                    break
                elif all_matched and self.last_better is None: # Everyone checked
                    break
                
                self.turn_index = (self.turn_index + 1) % len(self.current_order)
                await self.update_message()

            await self._advance_round()
        except Exception as e:
            logger.error(f"Error in _start_betting_round: {e}")
            if self.message:
                await self.message.channel.send(f"An unexpected error occurred during the betting round: {e}")

    async def _advance_round(self):
        try:
            """
            Advances the game to the next stage (flop, turn, river, or showdown).
            """
            if self.round_stage == "preflop":
                self.round_stage = "flop"
                # Deal flop cards
                await self._deal_community_cards(3)
            elif self.round_stage == "flop":
                self.round_stage = "turn"
                # Deal turn card
                await self._deal_community_cards(1)
            elif self.round_stage == "turn":
                self.round_stage = "river"
                # Deal river card
                await self._deal_community_cards(1)
            elif self.round_stage == "river":
                self.round_stage = "showdown"
                await self._determine_winner()
                return
            
            # Update the pot with all bets from the previous round
            for player_id in self.current_order:
                player = self.players[player_id]
                if not player.folded and not player.left_table:
                    self.pot += player.round_bets.get(self.round_stage, 0)
                    player.round_bets[self.round_stage] = 0 # Reset for next betting round

            await self.update_message()
            # Start a new betting round if there's more than one active player
            active_players = [p for p in self.players.values() if not p.folded and not p.left_table]
            if len(active_players) > 1:
                await self._start_betting_round()
            else:
                await self._determine_winner() # If only one player left, they win
        except Exception as e:
            logger.error(f"Error in _advance_round: {e}")
            if self.message:
                await self.message.channel.send(f"An unexpected error occurred while advancing the round: {e}")


    def _build_table_embed(self) -> discord.Embed:
        casino_emoji = emoji_mod.mention('Casino') or "🎰"
        e = discord.Embed(title=f"{casino_emoji} Texas Hold'em {casino_emoji}", color=discord.Color.dark_red(), timestamp=discord.utils.utcnow())
        
        # Community Cards
        community_display = []
        cb = emoji_mod.mention("CardBack") or "[?]"
        if self.round_stage == "preflop":
            community_display = [cb] * 5
        elif self.round_stage == "flop":
            community_display = [_mention(c) for c in self.community] + ([cb] * 2)
        elif self.round_stage == "turn":
            community_display = [_mention(c) for c in self.community] + ([cb] * 1)
        else: # river or showdown/finished
            community_display = [_mention(c) for c in self.community]
        
        e.add_field(name="Community Cards", value=" ".join(community_display), inline=False)
        e.add_field(name="Pot", value=f"{self.pot} XP", inline=True)
        e.add_field(name="Current Bet", value=f"{self.last_bet} XP", inline=True)

        # Player Information
        players_info = []
        for p_id in self.current_order: # Iterate in current turn order
            player = self.players[p_id]
            status = ""
            if player.folded:
                status = "(Folded)"
            elif player.left_table:
                status = "(Left)"
            
            player_line = f"{player.user.display_name} {status}"
            if self.round_stage != "idle" and self.current_order and self.current_order[self.turn_index] == p_id:
                player_line = f"**>** {player_line} **<**" # Indicate current player's turn
            
            players_info.append(player_line)
        
        if players_info:
            e.add_field(name="Players", value="\n".join(players_info), inline=False)

            
        stage_display = self.round_stage.title()
        if self.round_stage == "predeal": stage_display = "Shuffling"
        
        e.set_footer(text=f"Stage: {stage_display} • Pot {self.pot} XP")
        return e

    async def update_message(self, interaction: Optional[discord.Interaction] = None):
        embed = self._build_table_embed()
        
        self.clear_items() # Clear all current buttons
        
        if self.round_stage == "idle":
            self.add_item(self.btn_join_ref)
            if not self.solo:
                self.add_item(self.btn_start_ref)
            self.add_item(self.btn_leave_ref)
        else: # Game in progress
            self.add_item(self.btn_leave_ref)
            self.add_item(self.btn_show_hand_ref)

        if self.message:
            try:
                # If an interaction was provided and hasn't been responded to yet, use it
                if interaction and not interaction.response.is_done():
                    await interaction.response.edit_message(embed=embed, view=self)
                # If interaction was provided and already responded (e.g., deferred), use followup
                elif interaction and interaction.response.is_done():
                    await interaction.followup.edit_message(message_id=self.message.id, embed=embed, view=self)
                # Otherwise, just edit the message directly
                else:
                    await self.message.edit(embed=embed, view=self)
            except discord.NotFound:
                logger.debug("Message not found, could not update.")
            except Exception as e:
                logger.error(f"Error updating message: {e}")



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
            
        if player.folded:
            self.turn_index = (self.turn_index + 1) % len(self.current_order)
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
        can_check = to_call == 0

        action, amount = get_holdem_bot_action(player.hole, self.community, to_call, self.pot, self.round_stage, can_check)

        if action == "fold":
            await self.process_fold(player, None)
        elif action == "check":
            await self.process_bet(player, 0, None)
        elif action == "call":
            await self.process_bet(player, to_call, None)
        elif action == "bet":
            await self.process_bet(player, amount, None)
        elif action == "raise":
            await self.process_bet(player, amount, None)





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
                    loot = await LootCalculator.award_gambling_loot(uid, pet_data, win_streak=ps.win_streak)
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
            if ps is None:
                continue
            rk = get_hand_rank(ps.hole, self.community)
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
            win_text.append(self.players[uid].user.display_name)
            self.players[uid].win_streak += 1
            
            if not self.players[uid].is_bot:
                # Award XP to winner — ability effects (win bonus) applied centrally
                # in LootCalculator.apply_xp_change via source="holdem_win".
                if not self.fun_mode and share > 0:
                    await LootCalculator.apply_xp_change(uid, share, source="holdem_win")

                highest_bet = 0
                ps = self.players.get(uid)
                if ps:
                    for v in ps.round_bets.values():
                        if v > highest_bet: highest_bet = v
                
                io_tasks.append(self._handle_player_io(uid, share, True, highest_bet))
                
        for uid in self.current_order:
            if uid not in winners:
                self.players[uid].win_streak = 0

        if io_tasks:
            io_results = await asyncio.gather(*io_tasks)
            for r in io_results:
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



    @discord.ui.button(label="Join", style=discord.ButtonStyle.success, custom_id="holdem_join")
    async def btn_join(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.btn_join_action(interaction)

    @discord.ui.button(label="Start", style=discord.ButtonStyle.success, custom_id="holdem_start")
    async def btn_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.btn_start_action(interaction)

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.secondary, custom_id="holdem_leave")
    async def btn_leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.btn_leave_action(interaction)

    @discord.ui.button(label="Show Hand", style=discord.ButtonStyle.secondary, custom_id="holdem_show")
    async def btn_show_hand(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.btn_show_hand_action(interaction)

    @discord.ui.button(label="Cash Out", style=discord.ButtonStyle.primary, custom_id="holdem_cashout", row=1)
    async def btn_cashout(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.btn_cashout_action(interaction)





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
            
        success, message = await self._join_player(cast(discord.Member, interaction.user))
        if success:
            await self.update_message()
            await interaction.response.send_message(message, ephemeral=False)
        else:
            await interaction.response.send_message(message, ephemeral=True)

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
        ps.left_table = True
        await interaction.response.send_message("Left table.", ephemeral=True)
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
        if self.message:
            try:
                embed = self.message.embeds[0]
                embed.set_footer(text="Game timed out.")
                for item in self.children:
                    item.disabled = True
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass

    async def btn_cashout_action(self, interaction: discord.Interaction):
        """Cash out — return remaining bankroll XP to the player and end their session."""
        try:
            await interaction.response.defer(ephemeral=True)
            uid = interaction.user.id
            ps = self.players.get(uid)
            if not ps:
                await interaction.followup.send("You are not in this game.", ephemeral=True)
                return
            if self.round_stage not in ("idle", "finished"):
                await interaction.followup.send("You can only cash out between hands.", ephemeral=True)
                return

            # Return remaining bankroll to the player
            remaining = ps.bankroll
            if not self.fun_mode and remaining > 0:
                await LootCalculator.apply_xp_change(uid, remaining, source="holdem_cashout")

            net = remaining - self.buy_in_amt
            if not self.fun_mode:
                await user_data_manager.update_pet_gambling_stats(
                    str(uid), "holdem", net, bet_amount=self.buy_in_amt
                )

            ps.left_table = True
            sign = "+" if net >= 0 else ""
            await interaction.followup.send(
                f"Cashed out **{remaining:,} XP** ({sign}{net:,} net). Thanks for playing!",
                ephemeral=True
            )
            await self.update_message()
        except Exception as e:
            logger.error(f"Error in btn_cashout_action: {e}")
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

    def _setup_buttons(self):
        self.btn_map = {}
        for child in self.children:
            if hasattr(child, "custom_id"):
                self.btn_map[child.custom_id] = child
        
        self.btn_join_ref = self.btn_map.get("holdem_join")
        self.btn_start_ref = self.btn_map.get("holdem_start")
        self.btn_leave_ref = self.btn_map.get("holdem_leave")
        self.btn_show_hand_ref = self.btn_map.get("holdem_show")
        self.btn_cashout_ref = self.btn_map.get("holdem_cashout")
