
import discord
from discord.ext import commands
from discord import app_commands
from typing import Literal, Optional, List

import random

from Systems.Functions.emoji import get_partial, mention, CATEGORIES
from Systems.Functions.ai_brain import get_ai_choice

class RPSGame(discord.ui.View):
    def __init__(self, player1: discord.Member, player2: Optional[discord.Member], rounds: int, theme: str, ai_opponent: bool = False):
        super().__init__(timeout=300)
        self.player1 = player1
        self.player2 = player2
        self.rounds = rounds
        self.theme = theme
        self.current_round = 0
        self.score = {player1.id: 0, (player2.id if player2 else None): 0}
        self.player1_choice = None
        self.player2_choice = None
        self.message = None
        self.ai_opponent = ai_opponent
        self.last_player1_choice = None
        self.player1_choice_history: List[str] = []

        if self.player2 is None and not self.ai_opponent:
            self.add_item(JoinButton())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.ai_opponent:
            return interaction.user == self.player1
        if self.player2 is None:
            return True # Allow join button interaction
        return interaction.user == self.player1 or interaction.user == self.player2

    def get_emoji(self, name: str):
        return get_partial(name, animated=False)

    async def start_game(self):
        self.clear_items()
        if self.theme == "Traditional":
            self.add_item(RPSButton("rock_1", self.get_emoji("rock_1"), "Rock"))
            self.add_item(RPSButton("paper", self.get_emoji("paper"), "Paper"))
            self.add_item(RPSButton("scissor", self.get_emoji("scissor"), "Scissors"))
        elif self.theme == "Fantasy":
            self.add_item(RPSButton("knights", self.get_emoji("knights"), "Knights"))
            self.add_item(RPSButton("archer", self.get_emoji("archer"), "Archer"))
            self.add_item(RPSButton("necromancer", self.get_emoji("necromancer"), "Necromancer"))
        else: # War
            self.add_item(RPSButton("tank", self.get_emoji("tank"), "Tank"))
            self.add_item(RPSButton("jet", self.get_emoji("jet"), "Jet"))
            self.add_item(RPSButton("ship", self.get_emoji("ship"), "Ship"))
        
        embed = self.create_embed()
        await self.message.edit(embed=embed, view=self)

    def create_embed(self, round_end_message: str = ""):
        rps_emoji = self.get_emoji("rps")
        embed = discord.Embed(title=f"{rps_emoji} Rock Paper Scissors", color=discord.Color.blurple())
        player2_display_name = "AI Bot" if self.ai_opponent else (self.player2.display_name if self.player2 else 'Waiting...')
        player2_mention = "AI Bot" if self.ai_opponent else (self.player2.mention if self.player2 else 'Waiting...')
        embed.add_field(name="Players", value=f"{self.player1.mention} vs {player2_mention}", inline=False)
        embed.add_field(name="Game Info", value=f"First to {self.rounds} wins! | Round: {self.current_round}", inline=False)
        embed.add_field(name="Score", value=f"{self.player1.display_name}: {self.score[self.player1.id]}\n{player2_display_name}: {self.score.get(self.player2.id if self.player2 else None, 0)}", inline=False)
        if round_end_message:
            embed.add_field(name="Round Result", value=round_end_message, inline=False)
        return embed

    async def handle_choice(self, interaction: discord.Interaction, choice: str, display_label: str):
        if interaction.user == self.player1:
            self.player1_choice = choice
            self.player1_choice_history.append(choice)
        elif interaction.user == self.player2:
            self.player2_choice = choice
        else:
            await interaction.response.send_message("You are not part of this game.", ephemeral=True)
            return

        await interaction.response.defer()

        if self.ai_opponent and interaction.user == self.player1:
            self.player2_choice = get_ai_choice(self.theme, player_choice_history=self.player1_choice_history)

        if self.player1_choice and self.player2_choice:
            self.last_player1_choice = self.player1_choice
            await self.end_round()

    async def end_round(self):
        self.current_round += 1
        winner = self.get_winner()
        round_end_message = ""

        p1_emoji = self.get_emoji(self.player1_choice)
        p2_emoji = self.get_emoji(self.player2_choice)
        
        player1_choice_display = self.player1_choice.replace('_', ' ').title()
        player2_choice_display = self.player2_choice.replace('_', ' ').title()

        if winner is None:
            round_end_message = f"It's a tie! Both chose {player1_choice_display} {p1_emoji}."
        elif winner == self.player1:
            self.score[self.player1.id] += 1
            round_end_message = f"{self.player1.mention} wins! {p1_emoji} beats {p2_emoji}."
        else:
            self.score[self.player2.id] += 1
            round_end_message = f"{self.player2.mention} wins! {p2_emoji} beats {p1_emoji}."

        self.player1_choice = None
        self.player2_choice = None
        
        embed = self.create_embed(round_end_message)

        p1_score = self.score[self.player1.id]
        p2_score = self.score.get(self.player2.id if self.player2 else None, 0)
        
        if p1_score >= self.rounds or p2_score >= self.rounds:
            game_winner = self.player1 if p1_score >= self.rounds else self.player2
            player2_display_name = "AI Bot" if self.ai_opponent else (self.player2.display_name if self.player2 else 'Waiting...')
            winner_name = self.player1.display_name if game_winner == self.player1 else player2_display_name
            
            embed.color = discord.Color.gold()
            embed.description = f"**{winner_name} has won the game!**"
            
            self.clear_items()
            self.add_item(PlayAgainButton())
            self.add_item(EndGameButton())
            await self.message.edit(embed=embed, view=self)
        else:
            await self.message.edit(embed=embed, view=self)


    def reset_for_new_game(self, reset_scores: bool = True):
        self.current_round = 0
        self.player1_choice = None
        self.player2_choice = None
        self.last_player1_choice = None
        self.player1_choice_history.clear()
        if reset_scores:
            for player_id in self.score:
                self.score[player_id] = 0

    def get_winner(self):
        if self.player1_choice == self.player2_choice:
            return None

        if self.theme == "Traditional":
            winning_combinations = {
                "rock_1": "scissor",
                "paper": "rock_1",
                "scissor": "paper"
            }
        elif self.theme == "Fantasy":
            winning_combinations = {
                "knights": "archer",
                "archer": "necromancer",
                "necromancer": "knights"
            }
        else: # War
            winning_combinations = {
                "tank": "ship",
                "jet": "tank",
                "ship": "jet"
            }

        if winning_combinations[self.player1_choice] == self.player2_choice:
            return self.player1
        else:
            return self.player2


class RPSButton(discord.ui.Button):
    def __init__(self, choice: str, emoji: discord.PartialEmoji, display_label: str):
        super().__init__(style=discord.ButtonStyle.secondary, label=display_label, emoji=emoji)
        self.choice = choice

    async def callback(self, interaction: discord.Interaction):
        await self.view.handle_choice(interaction, self.choice, self.label)

class JoinButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.success, label="Join Game")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.view.player2 = interaction.user
        self.view.score[self.view.player2.id] = 0
        await self.view.start_game()
        
class PlayAgainButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="Play Again")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.view.reset_for_new_game(reset_scores=False)
        await self.view.start_game()

class EndGameButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.danger, label="End Game")

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Game Over", description=f"Final Score:\n{self.view.player1.display_name}: {self.view.score[self.view.player1.id]}\n{self.view.player2.display_name}: {self.view.score[self.view.player2.id]}", color=discord.Color.red())
        await interaction.response.edit_message(embed=embed, view=None)
        self.view.stop()


class Fun(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="rps", description="Play a game of Rock Paper Scissors")
    @app_commands.describe(
        rival="Mention a user to challenge them to a game.",
        rounds="Choose the number of rounds (1, 3, or 5).",
        theme="Choose the theme of the game.",
        ai_opponent="Set to True to play against the bot."
    )
    async def rps(self, interaction: discord.Interaction, rival: Optional[discord.Member], rounds: Literal[1, 3, 5] = 1, theme: Literal["Traditional", "Fantasy", "War"] = "Traditional", ai_opponent: bool = False):
        if rival and rival.bot:
            await interaction.response.send_message("You can't play against a bot!", ephemeral=True)
            return
            
        if rival == interaction.user:
            await interaction.response.send_message("You can't play against a bot unless you explicitly use the `ai_opponent` argument!", ephemeral=True)
            return
            
        if ai_opponent:
            rival = self.bot.user

        game = RPSGame(interaction.user, rival, rounds, theme, ai_opponent=ai_opponent)
        
        rps_emoji = get_partial("rps")

        if rival:
            if ai_opponent:
                embed = discord.Embed(title=f"{rps_emoji} Rock Paper Scissors Challenge!", description=f"{interaction.user.mention} is playing against the AI for {rounds} rounds!", color=discord.Color.gold())
            else:
                embed = discord.Embed(title=f"{rps_emoji} Rock Paper Scissors Challenge!", description=f"{interaction.user.mention} has challenged {rival.mention} to a game of Rock Paper Scissors for {rounds} rounds!", color=discord.Color.gold())
            await interaction.response.send_message(embed=embed, view=game)
        game.message = await interaction.original_response()
        if rival:
            await game.start_game()

        else:
            embed = discord.Embed(title=f"{rps_emoji} Rock Paper Scissors", description="A game of Rock Paper Scissors has started! Click the button to join.", color=discord.Color.green())
            await interaction.response.send_message(embed=embed, view=game)
            game.message = await interaction.original_response()

    @commands.hybrid_command(name="dice", description="Roll some dice.")
    @app_commands.describe(
        dice_type="The type of dice to roll (D6 or D20).",
        amount="The amount of dice to roll (1-5).",
        color="The color of the dice (only for D6)."
    )
    async def dice(self, ctx: commands.Context, dice_type: Literal['D6', 'D20'], amount: Literal[1, 2, 3, 4, 5], color: Optional[Literal['Red', 'Orange', 'Blue', 'Yellow', 'Pink', 'Green', 'Purple']] = 'Red'):
        if dice_type == 'D20' and color != 'Red':
            await ctx.send("Color can only be selected for D6 dice.", ephemeral=True)
            return

        rolls = []
        for _ in range(amount):
            if dice_type == 'D6':
                roll = random.randint(1, 6)
                emoji_name = f"{color}{roll}"
                rolls.append(mention(emoji_name))
            else: # D20
                roll = random.randint(1, 20)
                if roll == 10:
                    emoji_name = "D010"
                else:
                    emoji_name = f"D{roll:02d}"
                rolls.append(mention(emoji_name))
        
        await ctx.send(f"{ctx.author.mention} rolled:\n# {' '.join(rolls)}")

    @commands.hybrid_command(name="card", description="Draw some cards.")
    @app_commands.describe(
        count="The number of cards to draw (1-5)."
    )
    async def card(self, ctx: commands.Context, count: Literal[1, 2, 3, 4, 5]):
        all_card_emojis = (
            CATEGORIES["Hearts"] +
            CATEGORIES["Diamonds"] +
            CATEGORIES["Clubs"] +
            CATEGORIES["Spades"] +
            CATEGORIES["Jokers"]
        )
        
        drawn_cards = random.sample(all_card_emojis, k=count)
        card_mentions = [mention(card_name) for card_name in drawn_cards]

        await ctx.send(f"{ctx.author.mention} drew:\n# {' '.join(card_mentions)}")

async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))
