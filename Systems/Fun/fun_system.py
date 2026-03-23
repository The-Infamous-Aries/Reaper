import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
import logging
from typing import Optional

from Systems.Functions import emoji as emoji_mod

logger = logging.getLogger("reaper.fun_system")

FALLBACK_EMOJIS = {
    "Pirate": "",
    "Poop": "",
    "Future": "",
    "Retro": "",
    "Full": "",
    "Empty": "",
    "Plug": "",
    "Socket": "",
    "Open": "",
    "Closed": "",
    "Day": "",
    "Night": "",
    "Hot": "",
    "Cold": ""
}

COIN_TYPES = {
    "Raider": {"Heads": "Pirate", "Tails": "Poop"},
    "Time": {"Heads": "Future", "Tails": "Retro"},
    "Battery": {"Heads": "Full", "Tails": "Empty"},
    "Electric": {"Heads": "Plug", "Tails": "Socket"},
    "Business": {"Heads": "Open", "Tails": "Closed"},
    "Sky": {"Heads": "Day", "Tails": "Night"},
    "Tempature": {"Heads": "Hot", "Tails": "Cold"}
}

def get_coin_emoji(name: str) -> str:
    """Get emoji from emoji system or fallback."""
    # Try to get from emoji system
    em = emoji_mod.mention(name)
    if em:
        return em

    # Try fallback
    return FALLBACK_EMOJIS.get(name, "❓")

BOT_EMOJIS = ["✅", "❌", "🌟", "🔥", "✨", "🚀", "🧠", "💡", "🌈", "💫", "⭐", "🍀", "💯", "🔱", "🔔", "💡", "💎", "🔮", "💰", "🎲", "🎯", "⚡", "🔥", "🌊", "🌳", "🌷", "🍂", "⛄", "🌸", "🍄", "🍎", "🍊", "🍋", "🍉", "🍇", "🍓", "🍒", "🍑", "🍍", "🥝", "🍅", "🍆", "🥑", "🥦", "🥔", "🥕", "🌽", "🌶️", "🥒", "🥬", "🧅", "🧄", "🌰", "🥜", "🍞", "🥐", "🥖", "🥨", "🥯", "🧇", "🧀", "🥚", "🍳", "🧈", "🥓", "🥩", "🍗", "🍖", "🌭", "🍔", "🍟", "🍕", "🥪", "🥙", "🧆", "🌮", "🌯", "🥗", "🍲", "🥘", "🍝", "🍜", "🍣", "🍱", "🍛", "🍚", "🥟", "🍤", "🍥", "🥮", "🍢", "🍡", "🍧", "🍦", "🥧", "🍰", "🍮", "🍬", "🍭", "🍫", "🍿", "🍩", "🍪", "🌰", "🥜", "🍯", "🥛", "🍼", "☕", "🍵", "🧃", "🥤", "🍶", "🍾", "🍷", "🍸", "🍹", "🍺", "🍻", "🥂", "🧊", "🥄", "🍴", "🍽️", "🥣", "🥡", "🥢", "🧂"]

class JoinModal(discord.ui.Modal, title="Join Tic Tac Toe"):
    emoji = discord.ui.TextInput(label="Your Emoji (for your marks)", placeholder="e.g. ⭕", required=True, max_length=8)

    def __init__(self, cog, game_id):
        super().__init__()
        self.cog = cog
        self.game_id = game_id

    async def on_submit(self, interaction: discord.Interaction):
        emoji = self.emoji.value.strip()
        try:
            pe = discord.PartialEmoji.from_str(emoji)
        except Exception:
            await interaction.response.send_message("❌ Invalid emoji! Please try again.", ephemeral=True)
            return
        if getattr(pe, "id", None):
            await interaction.response.send_message("❌ Custom server emojis are not allowed. Use a standard emoji.", ephemeral=True)
            return
        game = self.cog.active_games.get(self.game_id)
        if game is None:
            await interaction.response.send_message("❌ Game no longer exists!", ephemeral=True)
            return
        if game.player2_id is not None:
            await interaction.response.send_message("❌ Game already joined!", ephemeral=True)
            return
        game.player2_id = interaction.user.id
        game.player2_emoji = emoji
        game.current_player = 1
        embed = game.get_embed()
        view = game.get_view(self.cog)
        for child in view.children:
            child.disabled = False
        view.join_button.disabled = True
        await interaction.response.edit_message(embed=embed, view=view)
        await game.update_message(embed, view)

class TicTacToeButton(discord.ui.Button):
    def __init__(self, x: int, y: int):
        super().__init__(label=" ", style=discord.ButtonStyle.secondary, row=y)
        self.x = x
        self.y = y

    async def callback(self, interaction: discord.Interaction):
        game = getattr(self.view, 'game', None)
        if game is None:
            await interaction.response.defer()
            return
        if game.current_player == 0 and interaction.user.id != game.player1_id:
            await interaction.response.send_message("❌ It's not your turn!", ephemeral=True)
            return
        elif game.current_player == 1 and interaction.user.id != game.player2_id:
            await interaction.response.send_message("❌ It's not your turn!", ephemeral=True)
            return
        board = game.board
        if board[self.y][self.x] != 0:
            await interaction.response.defer()
            return
        mark = -1 if game.current_player == 0 else 1
        board[self.y][self.x] = mark
        emoji = game.player1_emoji if mark == -1 else game.player2_emoji
        self.emoji = emoji
        self.style = discord.ButtonStyle.danger if mark == -1 else discord.ButtonStyle.success
        self.disabled = True
        winner = game.check_winner()
        if winner or game.is_tie():
            game.round_scores[0 if winner == -1 else 1 if winner == 1 else 2] += 1
            if game.check_series_over():
                embed = discord.Embed(title="🎉 Series Over!", color=0x00ff00)
                if game.round_scores[0] > game.round_scores[1]:
                    embed.description = f"{game.player1_mention} wins the series {game.round_scores[0]}-{game.round_scores[1]}!"
                elif game.round_scores[1] > game.round_scores[0]:
                    embed.description = f"{game.player2_mention} wins the series {game.round_scores[1]}-{game.round_scores[0]}!"
                else:
                    embed.description = f"Tie series {game.round_scores[0]}-{game.round_scores[1]}!"
                for child in self.view.children:
                    child.disabled = True
                if hasattr(self.view, 'cog') and self.view.cog:
                    self.view.cog.active_games.pop(game.game_id, None)
            else:
                await game.next_round()
                embed = game.get_embed()
            view = self.view
        else:
            game.current_player = 1 - game.current_player
            embed = game.get_embed()
        await interaction.response.edit_message(embed=embed, view=view)
        await game.update_message(embed, view)

class TicTacToeView(discord.ui.View):
    def __init__(self, cog, game):
        super().__init__(timeout=None)
        self.cog = cog
        self.game = game
        self.game_id = game.game_id
        self.add_items()
        self.join_button = discord.ui.Button(label="Join Game", style=discord.ButtonStyle.green)
        self.join_button.callback = self.join_callback
        self.add_item(self.join_button)

    async def join_callback(self, interaction: discord.Interaction):
        game = self.game
        if game.player2_id is not None:
            await interaction.response.send_message("❌ Already joined!", ephemeral=True)
            return
        await interaction.response.send_modal(JoinModal(self.cog, self.game_id))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return True

    def add_items(self):
        for item in list(self.children):
            if isinstance(item, discord.ui.Button) and item.row is not None:
                self.remove_item(item)
        for x in range(3):
            for y in range(3):
                btn = TicTacToeButton(x, y)
                self.add_item(btn)

class TicTacToeGame:
    X = -1
    O = 1
    TIE = 0

    def __init__(self, creator_id, creator_emoji, rounds, interaction, npc=False, difficulty="novice", bot_emoji=None):
        self.player1_id = creator_id
        self.player1_emoji = creator_emoji
        self.player1_mention = f"<@{creator_id}>"
        self.player2_id = None
        self.player2_emoji = bot_emoji if npc else None
        self.player2_mention = "🤖 Bot" if npc else None
        self.npc = npc
        self.difficulty = difficulty
        self.rounds = rounds
        self.wins_needed = (rounds + 1) // 2
        self.round_scores = [0, 0]
        self.current_round = 0
        self.board = [[0] * 3 for _ in range(3)]
        self.current_player = 0
        self.message = None
        self.interaction = interaction
        self.game_id = interaction.id

    def get_embed(self):
        board_str = ""
        empty_emoji = emoji_mod.mention("Pending") or "⚪"
        for row in self.board:
            board_str += " | ".join([self.player1_emoji if c == self.X else self.player2_emoji if c == self.O else empty_emoji for c in row]) + "\n"
        embed = discord.Embed(title=f"Tic Tac Toe - Round {self.current_round + 1}/{self.rounds} | Series: {self.round_scores[0]}-{self.round_scores[1]}", color=0x00ff00)
        embed.add_field(name="Board", value=f"```{board_str}```", inline=False)
        if self.player2_id is not None or self.npc:
            turn_emoji = self.player1_emoji if self.current_player == 0 else self.player2_emoji
            turn_player = self.player1_mention if self.current_player == 0 else self.player2_mention
            embed.set_footer(text=f"{turn_emoji} {turn_player}'s Turn")
        else:
            embed.description = "Waiting for opponent to join..."
        return embed

    async def next_round(self):
        self.current_round += 1
        self.board = [[0] * 3 for _ in range(3)]
        self.current_player = 0

    def check_winner(self):
        for across in self.board:
            value = sum(across)
            if value == 3:
                return self.O
            elif value == -3:
                return self.X
        for line in range(3):
            value = self.board[0][line] + self.board[1][line] + self.board[2][line]
            if value == 3:
                return self.O
            elif value == -3:
                return self.X
        diag1 = self.board[0][2] + self.board[1][1] + self.board[2][0]
        diag2 = self.board[0][0] + self.board[1][1] + self.board[2][2]
        if diag1 == 3 or diag2 == 3:
            return self.O
        elif diag1 == -3 or diag2 == -3:
            return self.X
        return None

    def is_tie(self):
        return all(cell != 0 for row in self.board for cell in row)

    def check_series_over(self):
        return self.round_scores[0] >= self.wins_needed or self.round_scores[1] >= self.wins_needed

    def _minimax(self, board, depth, is_maximizing):
        winner = self.check_winner()
        if winner == self.O:
            return 10 - depth
        if winner == self.X:
            return depth - 10
        if self.is_tie():
            return 0
        if is_maximizing:
            best_score = -float('inf')
            for i in range(3):
                for j in range(3):
                    if board[i][j] == 0:
                        board[i][j] = self.O
                        score = self._minimax(board, depth + 1, False)
                        board[i][j] = 0
                        best_score = max(score, best_score)
            return best_score
        else:
            best_score = float('inf')
            for i in range(3):
                for j in range(3):
                    if board[i][j] == 0:
                        board[i][j] = self.X
                        score = self._minimax(board, depth + 1, True)
                        board[i][j] = 0
                        best_score = min(score, best_score)
            return best_score

    async def bot_move(self):
        if self.npc and self.current_player == 1:
            empty = [(i, j) for i in range(3) for j in range(3) if self.board[i][j] == 0]
            if empty:
                if self.difficulty == "novice":
                    y, x = random.choice(empty)
                elif self.difficulty == "competent":
                    move = None
                    for i, j in empty:
                        self.board[i][j] = self.O
                        if self.check_winner() == self.O:
                            move = (i, j)
                            self.board[i][j] = 0
                            break
                        self.board[i][j] = 0
                    if move is None:
                        for i, j in empty:
                            self.board[i][j] = self.X
                            if self.check_winner() == self.X:
                                move = (i, j)
                                self.board[i][j] = 0
                                break
                            self.board[i][j] = 0
                    if move is None:
                        y, x = random.choice(empty)
                    else:
                        y, x = move
                else:
                    best_score = -float('inf')
                    best_move = None
                    for i in range(3):
                        for j in range(3):
                            if self.board[i][j] == 0:
                                self.board[i][j] = self.O
                                score = self._minimax(self.board, 0, False)
                                self.board[i][j] = 0
                                if score > best_score:
                                    best_score = score
                                    best_move = (i, j)
                    y, x = best_move if best_move else random.choice(empty)
                self.board[y][x] = self.O
                await self.update_message(self.get_embed(), self.get_view(self._cog))
                if not self.check_winner() and not self.is_tie():
                    self.current_player = 0

    def get_view(self, cog):
        self._cog = cog
        view = TicTacToeView(cog, self)
        if self.player2_id or self.npc:
            for item in list(view.children):
                if isinstance(item, discord.ui.Button) and item == view.join_button:
                    item.disabled = True
        return view

    async def update_message(self, embed, view):
        if self.message:
            await self.message.edit(embed=embed, view=view)

class ShootingView(discord.ui.View):
    def __init__(self, target_position, user_id):
        super().__init__(timeout=1.2)  # 1.2 second timeout to match sleep timing
        self.target_position = target_position
        self.user_id = user_id
        self.user_clicked = False
        self.hit = False

        # Create 5 buttons using custom server emojis for Miss/Hit
        hit_id = emoji_mod.id_for("Hit")
        miss_id = emoji_mod.id_for("Miss")
        hit_pe = discord.PartialEmoji(name="Hit", id=hit_id) if hit_id else None
        miss_pe = discord.PartialEmoji(name="Miss", id=miss_id) if miss_id else None

        for i in range(5):
            if i == target_position:
                # Target button (hit)
                button = discord.ui.Button(
                    style=discord.ButtonStyle.danger,
                    emoji=hit_pe,
                    custom_id=f'target_{i}'
                )
                button.callback = self.create_callback(i, True)
            else:
                # Miss button
                button = discord.ui.Button(
                    style=discord.ButtonStyle.danger,
                    emoji=miss_pe,
                    custom_id=f'miss_{i}'
                )
                button.callback = self.create_callback(i, False)

            self.add_item(button)

    def create_callback(self, position, is_hit):
        async def button_callback(interaction: discord.Interaction):
            # Only allow the original user to click
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ This isn't your shooting session!", ephemeral=True)
                return

            # Only allow one click
            if self.user_clicked:
                await interaction.response.send_message("❌ You already shot!", ephemeral=True)
                return

            self.user_clicked = True
            self.hit = is_hit

            # Disable all buttons
            for item in self.children:
                item.disabled = True

            # Update the message
            if is_hit:
                embed = discord.Embed(
                    title="🎯 HIT!",
                    description="Perfect shot! 🔥",
                    color=0x00ff00
                )
            else:
                embed = discord.Embed(
                    title="❌ MISS!",
                    description="Better luck next time!",
                    color=0xff0000
                )

            await interaction.response.edit_message(embed=embed, view=self)

        return button_callback

    async def on_timeout(self):
        # Disable all buttons when timeout occurs
        for item in self.children:
            item.disabled = True

class RangeStatsView(discord.ui.View):
    def __init__(self, user, stats, cog):
        super().__init__(timeout=300)
        self.user = user
        self.stats = stats
        self.cog = cog

    def create_stats_embed(self):
        """Create the personal stats embed"""
        overall_accuracy = (self.stats['total_hits'] / self.stats['total_shots'] * 100) if self.stats['total_shots'] > 0 else 0

        embed = discord.Embed(
            title=f"🎯 {self.user.display_name}'s Training Records",
            color=discord.Color.dark_gray()
        )

        embed.add_field(
            name="📊 Overall Performance",
            value=f"**Sessions Played:** {self.stats['sessions_played']}\n**Total Hits:** {self.stats['total_hits']}/{self.stats['total_shots']}\n**Overall Accuracy:** {overall_accuracy:.1f}%",
            inline=False
        )

        # Show all round types in descending order
        rounds_data = ""
        for rounds in ['100', '50', '25', '15', '5']:
            if rounds in self.stats['best_records']:
                record = self.stats['best_records'][rounds]
                accuracy = record['accuracy']
                hits = record['hits']
            else:
                accuracy = 0.0
                hits = 0

            play_count = self.stats.get('attempts_by_round', {}).get(rounds, 0)

            rounds_data += f"**{rounds} rounds:** {accuracy:.1f}% ({hits}/{rounds}) - Played: {play_count}x\n"

        if rounds_data:
            embed.add_field(
                name="🏆 Round Performance",
                value=rounds_data,
                inline=False
            )

        embed.set_footer(text="Keep training to improve your scores!")
        return embed

class FunSystemCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}  # For Tic Tac Toe games
        self.shooting_active = {} # user_id -> boolean

    async def update_shooting_stats(self, user_id, hits, total_shots, rounds):
        """Update shooting statistics for a user using UserDataManager"""
        try:
            user = self.bot.get_user(user_id)
            username = user.name if user else str(user_id)

            # Use the bot's user_data_manager instance directly
            updated_stats = await self.bot.user_data_manager.update_shooting_range_stats(
                str(user_id), username, hits, total_shots, rounds
            )
            return updated_stats
        except Exception as e:
            logger.error(f"Error updating shooting stats for {user_id}: {e}")
            return {}

    @commands.hybrid_command(name='range', description='Start Sniper Training')
    @app_commands.describe(rounds="Number of rounds for the training session (5, 15, 25, 50, 100)")
    async def shooting_range(self, ctx, rounds: int = 10):
        """
        Start sniper training!
        Usage: /range [rounds]
        Available rounds: 5, 15, 25, 50, 100
        """
        # Validate rounds
        valid_rounds = [5, 15, 25, 50, 100]
        if rounds not in valid_rounds:
            embed = discord.Embed(
                title="🎯 Sniper Training - Invalid Selection",
                description=f"Please select from available rounds: {', '.join(map(str, valid_rounds))}",
                color=0xff0000
            )
            await ctx.send(embed=embed, ephemeral=True)
            return

        # Check if user already has an active game
        if ctx.author.id in self.active_games:
            embed = discord.Embed(
                title="🎯 Training Already in Progress",
                description="You already have an active sniper training session!",
                color=0xff9900
            )
            await ctx.send(embed=embed, ephemeral=True)
            return

        # Mark user as having an active game
        self.active_games[ctx.author.id] = True

        try:
            await self._run_shooting_range(ctx, rounds)
        finally:
            # Clean up active game tracking
            if ctx.author.id in self.active_games:
                del self.active_games[ctx.author.id]

    @shooting_range.autocomplete('rounds')
    async def rounds_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete for rounds parameter"""
        valid_rounds = [5, 15, 25, 50, 100]
        choices = []

        for r in valid_rounds:
            rounds_str = str(r)
            if current.lower() in rounds_str.lower():
                choices.append(app_commands.Choice(name=f"{r} rounds", value=r))

        return choices[:25]

    @shooting_range.error
    async def shooting_range_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            embed = discord.Embed(
                title="🎯 Invalid Input",
                description="Please enter a valid number of rounds (5, 15, 25, 50, or 100)",
                color=0xff0000
            )
            await ctx.send(embed=embed, ephemeral=True)
        else:
            # Clean up active game on error
            if ctx.author.id in self.active_games:
                del self.active_games[ctx.author.id]
            logger.error(f"Error in shooting_range: {error}")
            raise error

    async def _run_shooting_range(self, ctx, rounds):
        hits = 0
        total_shots = 0

        # Initial setup message
        setup_embed = discord.Embed(
            title="💀 Sniper Training Initializing...",
            description=f"**Operative:** {ctx.author.mention}\n**Mission:** {rounds} rounds of precision target practice\n**Objective:** Click the 🎯 target button!",
            color=discord.Color.dark_gray()
        )
        setup_embed.add_field(
            name="📋 Instructions",
            value="• Target appears briefly — react fast\n• Click the correct 🎯 button to score a hit\n• Miss buttons: 🔴 (red circles)\n• Hits: 🎯 (target)\n• Train your sniping reaction time and precision",
            inline=False
        )
        setup_msg = await ctx.send(embed=setup_embed)

        # Let the setup message stay visible for 5 seconds
        await asyncio.sleep(5)

        # Countdown
        for i in range(3, 0, -1):
            countdown_embed = discord.Embed(
                title=f"🎯 Training starts in {i}...",
                description="Shoulder your rifle. Steady your breath.",
                color=discord.Color.dark_red()
            )
            await setup_msg.edit(embed=countdown_embed)
            await asyncio.sleep(1)

        # Delete setup message
        try:
            await setup_msg.delete()
        except discord.NotFound:
            pass

        for round_num in range(1, rounds + 1):
            # Randomly select target position (0-4)
            target_position = random.randint(0, 4)

            # Create and send target message with buttons
            target_embed = discord.Embed(
                title=f"🎯 Round {round_num}/{rounds}",
                description="**FIRE!** Acquire and engage the target.",
                color=discord.Color.dark_gold()
            )

            # Create view with buttons
            view = ShootingView(target_position, ctx.author.id)
            target_msg = await ctx.send(embed=target_embed, view=view)

            # Wait for user interaction or timeout (1.2 seconds to match view timeout + 0.2s)
            await asyncio.sleep(1.2)

            # Check if user clicked and if it was a hit
            if view.user_clicked and view.hit:
                hits += 1

            total_shots += 1

            # Brief pause before next round
            await asyncio.sleep(0.5)

            # Delete the target message
            try:
                await target_msg.delete()
            except discord.NotFound:
                pass

        accuracy = (hits / total_shots * 100) if total_shots > 0 else 0

        # Update stats
        updated_stats = await self.update_shooting_stats(ctx.author.id, hits, total_shots, rounds)

        # Ensure we have valid stats data
        if not updated_stats or 'best_records' not in updated_stats:
            updated_stats = {
                'sessions_played': 0,
                'total_hits': 0,
                'total_shots': 0,
                'best_records': {
                    '5': {'accuracy': 0, 'hits': 0},
                    '15': {'accuracy': 0, 'hits': 0},
                    '25': {'accuracy': 0, 'hits': 0},
                    '50': {'accuracy': 0, 'hits': 0},
                    '100': {'accuracy': 0, 'hits': 0}
                },
                'round_attempts': {}
            }

        await self._display_results(ctx, hits, total_shots, accuracy, rounds, updated_stats)

    async def _display_results(self, ctx, hits, total_shots, accuracy, rounds, user_stats):
        # Rank mapping: only 80%+ is positive; below 80% is negative with worsening titles
        if accuracy == 100:
            rank = "💀 **Deliverer of Death**"
            rank_color = discord.Color.gold()
            rank_desc = "Perfect execution. Every shot lethal."
        elif accuracy >= 95:
            rank = "🎯 **Deadshot**"
            rank_color = discord.Color.dark_gold()
            rank_desc = "Unerring precision under pressure."
        elif accuracy >= 90:
            rank = "🦅 **Marksman Elite**"
            rank_color = discord.Color.teal()
            rank_desc = "High-competence target acquisition."
        elif accuracy >= 85:
            rank = "🥶 **Cold Precision**"
            rank_color = discord.Color.dark_gray()
            rank_desc = "Controlled, disciplined shooting."
        elif accuracy >= 80:
            rank = "🏅 **Qualified Marksman**"
            rank_color = discord.Color.green()
            rank_desc = "Positive performance. Maintain standards."
        elif accuracy >= 70:
            rank = "⚠️ **Stray Shooter**"
            rank_color = discord.Color.dark_orange()
            rank_desc = "Too many misses. Tighten your grouping."
        elif accuracy >= 60:
            rank = "🚫 **Liability**"
            rank_color = discord.Color.red()
            rank_desc = "Misses jeopardize operations. Retrain immediately."
        elif accuracy >= 50:
            rank = "🧱 **Spray-and-Pray**"
            rank_color = discord.Color.dark_red()
            rank_desc = "Undisciplined fire. Focus, breathe, and reset."
        elif accuracy >= 40:
            rank = "🤣 **Target's Laughing**"
            rank_color = discord.Color.dark_red()
            rank_desc = "Poor performance. Back to fundamentals."
        elif accuracy >= 30:
            rank = "🤕 **Friendly Fire Risk**"
            rank_color = discord.Color.dark_red()
            rank_desc = "Dangerously inaccurate. Halt live drills."
        elif accuracy >= 20:
            rank = "🤡 **Can't Hit Static**"
            rank_color = discord.Color.dark_red()
            rank_desc = "Inadequate. Dry-fire and zeroing required."
        else:
            rank = "🦯 **Blindfolded Intern**"
            rank_color = discord.Color.dark_red()
            rank_desc = "Catastrophic aim. Restart training program."

        # Check if this is a new personal best
        rounds_key = str(rounds)
        is_new_best = False
        if rounds_key in user_stats['best_records']:
            best_record = user_stats['best_records'][rounds_key]
            # Simple check: if current run matches the stored best (which was just updated), it's a "new" best (or equal)
            # A more robust check would require previous state, but this suffices for feedback
            if accuracy == best_record['accuracy'] and hits == best_record['hits']:
                # Could be a tie, but we'll celebrate it
                is_new_best = True

        # Create results embed
        results_embed = discord.Embed(
            title="🎯 Sniper Training Results" + (" 🆕 NEW PERSONAL BEST!" if is_new_best else ""),
            color=rank_color
        )

        results_embed.add_field(
            name="📊 Performance Stats",
            value=f"**Hits:** {hits}/{total_shots}\n**Accuracy:** {accuracy:.1f}%\n**Rounds Completed:** {rounds}",
            inline=True
        )

        results_embed.add_field(
            name="🏅 Rank Achieved",
            value=f"{rank}\n*{rank_desc}*",
            inline=True
        )

        # Show personal best for this round count
        if rounds_key in user_stats['best_records']:
            best_record = user_stats['best_records'][rounds_key]
            results_embed.add_field(
                name=f"🏆 Personal Best ({rounds} rounds)",
                value=f"**Accuracy:** {best_record['accuracy']:.1f}%\n**Hits:** {best_record['hits']}/{rounds}",
                inline=True
            )

        # Add accuracy bar
        bar_length = 20
        filled_length = int(bar_length * accuracy // 100)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)

        results_embed.add_field(
            name="📈 Accuracy Meter",
            value=f"`{bar}` {accuracy:.1f}%",
            inline=False
        )

        # Add overall stats
        overall_accuracy = (user_stats['total_hits'] / user_stats['total_shots'] * 100) if user_stats['total_shots'] > 0 else 0
        results_embed.add_field(
            name="📈 Overall Stats",
            value=f"**Sessions:** {user_stats['sessions_played']}\n**Total Hits:** {user_stats['total_hits']}/{user_stats['total_shots']}\n**Overall Accuracy:** {overall_accuracy:.1f}%",
            inline=False
        )

        results_embed.set_footer(text=f"{rank} | {ctx.author.display_name} | Use /range [rounds] to train again")

        await ctx.send(embed=results_embed)

    @commands.hybrid_command(name='rangestats', description='View shooting range statistics')
    async def range_stats(self, ctx, user: discord.Member = None):
        """View shooting range statistics"""
        target_user = user or ctx.author
        stats = await self.bot.user_data_manager.get_shooting_range_stats(str(target_user.id))

        # Ensure we have valid stats data
        if not stats or 'best_records' not in stats:
            stats = {
                'sessions_played': 0,
                'total_hits': 0,
                'total_shots': 0,
                'best_records': {
                    '5': {'accuracy': 0, 'hits': 0},
                    '15': {'accuracy': 0, 'hits': 0},
                    '25': {'accuracy': 0, 'hits': 0},
                    '50': {'accuracy': 0, 'hits': 0},
                    '100': {'accuracy': 0, 'hits': 0}
                },
                'round_attempts': {}
            }

        # Create view with pagination (though currently only one page)
        view = RangeStatsView(target_user, stats, self)
        embed = view.create_stats_embed()

        await ctx.send(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_ready(self):
        """Initialize story map manager when bot is ready"""
        from .walktru import StoryMapManager

        # Initialize story map manager on the bot instance
        if not hasattr(self.bot, 'story_map_manager'):
            self.bot.story_map_manager = StoryMapManager(self.bot)
            logger.info("StoryMapManager initialized")

    @commands.hybrid_command(name='walktru', description='Start an interactive adventure')
    async def walktru(self, ctx):
        """Start an interactive adventure experience"""
        try:
            from .walktru import StoryMapManager, WalktruView

            # Ensure manager is initialized
            if not hasattr(self.bot, 'story_map_manager'):
                self.bot.story_map_manager = StoryMapManager(self.bot)

            story_maps = await self.bot.story_map_manager.load_story_maps_lazy()

            if not story_maps:
                embed = discord.Embed(
                    title="❌ Adventure System Error",
                    description="Unable to load adventure data. Please try again later.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed, ephemeral=True)
                return

            view = WalktruView(story_maps, ctx.author.id, self.bot.story_map_manager)

            embed = discord.Embed(
                title="🎭 Choose Your Adventure",
                description="Select an adventure from the dropdown menu below to begin your interactive story experience!",
                color=discord.Color.purple()
            )
            # Add some flavor emojis if available
            flavor_emojis = [
                emoji_mod.mention("Haunted") or "👻",
                emoji_mod.mention("Mafia") or "🔫",
                emoji_mod.mention("Knight") or "🗡️",
                emoji_mod.mention("Wizard") or "🧙‍♂️",
                emoji_mod.mention("Robot") or "🤖",
                emoji_mod.mention("Western") or "🤠"
            ]
            embed.add_field(name="Available Genres", value=" ".join(flavor_emojis), inline=False)

            await ctx.send(embed=embed, view=view)

        except Exception as e:
            logger.error(f"Error in walktru command: {e}")
            await ctx.send("An error occurred while starting the adventure system.", ephemeral=True)

    @app_commands.command(name="coin", description="Flip a coin with custom styles")
    @app_commands.describe(
        coin_type="Choose the style of the coin",
        call_side="Call Heads or Tails"
    )
    @app_commands.choices(coin_type=[
        app_commands.Choice(name="Raider (Pirate- Heads & Poop- Tails)", value="Raider"),
        app_commands.Choice(name="Time (Future- Heads & Retro- Tails)", value="Time"),
        app_commands.Choice(name="Battery (Full- Heads & Empty- Tails)", value="Battery"),
        app_commands.Choice(name="Electric (Plug- Heads & Socket- Tails)", value="Electric"),
        app_commands.Choice(name="Business (Open- Heads & Closed- Tails)", value="Business"),
        app_commands.Choice(name="Sky (Day- Heads & Night- Tails)", value="Sky"),
        app_commands.Choice(name="Tempature (Hot- Heads & Cold- Tails)", value="Tempature")
    ])
    @app_commands.choices(call_side=[
        app_commands.Choice(name="Heads", value="Heads"),
        app_commands.Choice(name="Tails", value="Tails")
    ])
    async def coin(self, interaction: discord.Interaction, coin_type: str, call_side: str):
        # Determine the emojis
        config = COIN_TYPES.get(coin_type)
        if not config:
            await interaction.response.send_message("Invalid coin type.", ephemeral=True)
            return

        heads_key = config["Heads"]
        tails_key = config["Tails"]

        heads_emoji = get_coin_emoji(heads_key)
        tails_emoji = get_coin_emoji(tails_key)

        # User's choice emoji
        user_choice_emoji = heads_emoji if call_side == "Heads" else tails_emoji

        # --- Page 1: Show choices ---
        embed = discord.Embed(
            title="Coin Flip",
            description=f"**{interaction.user.display_name}** picked **{call_side}** {user_choice_emoji}",
            color=discord.Color.gold()
        )
        embed.add_field(name="Heads", value=heads_emoji, inline=True)
        embed.add_field(name="Tails", value=tails_emoji, inline=True)

        await interaction.response.send_message(embed=embed)

        await asyncio.sleep(7)

        # --- Page 2: Tossing ---
        embed.description = "The coin is being tossed..."
        embed.clear_fields()
        await interaction.edit_original_response(embed=embed)

        await asyncio.sleep(1.5)

        # --- Page 3: Random side in air ---
        # Pick a random side to show "in air"
        air_side_1 = random.choice(["Heads", "Tails"])
        air_emoji_1 = heads_emoji if air_side_1 == "Heads" else tails_emoji

        embed.description = f"The coin is still in the air...\n{air_emoji_1}"
        await interaction.edit_original_response(embed=embed)

        await asyncio.sleep(1.5)

        # --- Page 4: Other side in air ---
        air_side_2 = "Tails" if air_side_1 == "Heads" else "Heads"
        air_emoji_2 = heads_emoji if air_side_2 == "Heads" else tails_emoji

        embed.description = f"The coin is still in the air...\n{air_emoji_2}"
        await interaction.edit_original_response(embed=embed)

        await asyncio.sleep(1.5)

        # --- Page 5: Landing ---
        embed.description = "The coin is landing..."
        await interaction.edit_original_response(embed=embed)

        await asyncio.sleep(1.5)

        # --- Page 6: Result ---
        result_side = random.choice(["Heads", "Tails"])
        result_emoji = heads_emoji if result_side == "Heads" else tails_emoji

        won = (result_side == call_side)
        outcome_text = "Won" if won else "Lost"
        color = discord.Color.green() if won else discord.Color.red()

        embed.title = f"Coin Flip Result: {result_side}"
        embed.description = f"{result_emoji}\n\n**{interaction.user.display_name} {outcome_text} the coin toss!**"
        embed.color = color

        await interaction.edit_original_response(embed=embed)

    @app_commands.command(name="tictactoe", description="Play Tic Tac Toe!")
    @app_commands.describe(emoji="Your emoji for marks", npc="Play against bot?", rounds="Number of rounds", difficulty="Bot difficulty")
    @app_commands.choices(rounds=[
        app_commands.Choice(name="1 (single)", value=1),
        app_commands.Choice(name="3 (first to 2)", value=3),
        app_commands.Choice(name="5 (first to 3)", value=5),
        app_commands.Choice(name="7 (first to 4)", value=7),
        app_commands.Choice(name="9 (first to 5)", value=9)
    ], difficulty=[
        app_commands.Choice(name="Novice", value="novice"),
        app_commands.Choice(name="Competent", value="competent"),
        app_commands.Choice(name="Expert", value="expert")
    ])
    async def tictactoe(self, interaction: discord.Interaction, emoji: str, npc: bool = False, rounds: int = 1, difficulty: str = "novice"):
        try:
            pe = discord.PartialEmoji.from_str(emoji)
        except Exception:
            await interaction.response.send_message("❌ Invalid emoji!", ephemeral=True)
            return
        if getattr(pe, "id", None):
            await interaction.response.send_message("❌ Custom server emojis are not allowed. Use a standard emoji.", ephemeral=True)
            return
        bot_emoji_choices = [e for e in BOT_EMOJIS if e != emoji]
        bot_emoji = random.choice(bot_emoji_choices) if npc else None
        game = TicTacToeGame(interaction.user.id, emoji, rounds, interaction, npc, difficulty, bot_emoji)
        self.active_games[game.game_id] = game
        embed = game.get_embed()
        view = game.get_view(self)
        game.message = await interaction.response.send_message(embed=embed, view=view)
        if npc:
            game.player2_id = 0
            game.current_player = 0
            if random.choice([True, False]):
                await asyncio.sleep(1)
                game.current_player = 1
                await game.bot_move()

async def setup(bot):
    await bot.add_cog(FunSystemCommands(bot))