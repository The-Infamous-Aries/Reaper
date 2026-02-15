import discord
from discord.ext import commands, tasks
import aiohttp
import json
import os
import random
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from config import GEMINI_API_KEY
import logging

# Constants
DATA_DIR = os.getenv('DATA_DIR')
if DATA_DIR:
    if not os.path.exists(DATA_DIR):
        try:
            os.makedirs(DATA_DIR)
        except Exception as e:
            logging.getLogger("ZombieSurvival").error(f"Failed to create DATA_DIR: {e}")
    STATE_FILE = os.path.join(DATA_DIR, 'zombie_state.json')
else:
    STATE_FILE = os.path.join(os.path.dirname(__file__), 'zombie_state.json')

UPDATE_INTERVAL_HOURS = 2

class ZombieSurvival(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.state = {}
        self.bot.loop.create_task(self.initialize())
        self.game_loop.start()

    async def initialize(self):
        self.state = await self.load_state_async()

    def cog_unload(self):
        self.game_loop.cancel()

    async def load_state_async(self) -> Dict:
        if os.path.exists(STATE_FILE):
            try:
                def _read():
                    with open(STATE_FILE, 'r') as f:
                        return json.load(f)
                return await asyncio.to_thread(_read)
            except Exception as e:
                print(f"Error loading zombie state: {e}")
        return {
            "active": False,
            "history": [], # List of objects
            "current_event": "The outbreak has just begun...",
            "choices": [],
            "votes": {},
            "voters": [],
            "last_update": 0,
            "channel_id": None,
            "message_id": None,
            "round": 0
        }

    async def save_state_async(self):
        try:
            def _write():
                with open(STATE_FILE, 'w') as f:
                    json.dump(self.state, f, indent=4)
            await asyncio.to_thread(_write)
        except Exception as e:
            print(f"Error saving zombie state: {e}")

    async def generate_content(self, context_prompt: str):
        if not GEMINI_API_KEY:
            print("Gemini API key missing")
            return None

        system_instruction = (
            "You are a Zombie Survival Game Master. "
            "You are running a continual interactive story where users vote on choices. "
            "TONE: Dark, gritty, realistic, intense. NO jokes, NO slang, NO roasting. "
            "Output strictly in JSON format with keys: 'event_text' (the story description) and 'choices' (a list of exactly 5 distinct actionable choices). "
            "Do not include markdown formatting like ```json. Just the raw JSON."
        )

        full_prompt = f"{system_instruction}\n\n{context_prompt}"

        try:
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GEMINI_API_KEY}"
                headers = {
                    "Content-Type": "application/json",
                }
                payload = {
                    "contents": [{
                        "parts": [{"text": full_prompt}]
                    }],
                    "generationConfig": {
                        "responseMimeType": "application/json"
                    }
                }
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        try:
                            content_text = data["candidates"][0]["content"]["parts"][0]["text"]
                            # Clean up potential markdown
                            if content_text.startswith("```json"):
                                content_text = content_text[7:]
                            if content_text.startswith("```"):
                                content_text = content_text[3:]
                            if content_text.endswith("```"):
                                content_text = content_text[:-3]
                            
                            return json.loads(content_text)
                        except (KeyError, IndexError, json.JSONDecodeError) as e:
                            print(f"Gemini parsing error: {e}")
                            print(f"Raw content: {data}")
                            return None
                    else:
                        print(f"Gemini API error: {resp.status}")
                        print(await resp.text())
                        return None
        except Exception as e:
            print(f"Gen content error: {e}")
            return None

    @tasks.loop(hours=UPDATE_INTERVAL_HOURS)
    async def game_loop(self):
        if not self.state:
            return
            
        if not self.state.get("active") or not self.state.get("channel_id"):
            return

        await self.bot.wait_until_ready()

        last_update = self.state.get("last_update", 0)
        # Check if 2 hours have passed
        if datetime.now().timestamp() - last_update < (UPDATE_INTERVAL_HOURS * 3600 - 60):
            return

        await self.resolve_round()

    @game_loop.before_loop
    async def before_game_loop(self):
        await self.bot.wait_until_ready()

    async def resolve_round(self):
        channel_id = self.state.get("channel_id")
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        votes = self.state.get("votes", {})
        choices = self.state.get("choices", [])
        
        total_votes = sum(votes.values())
        
        if not choices:
            winning_choice_index = -1
            winning_choice_text = "None"
            success_chance = 100
            is_success = True
        else:
            if total_votes == 0:
                winning_choice_index = random.randint(0, 4)
                winning_choice_text = choices[winning_choice_index]
                success_chance = 50 
            else:
                max_votes = max(votes.values())
                candidates = [int(k) for k, v in votes.items() if v == max_votes]
                if not candidates:
                     winning_choice_index = random.randint(0, 4)
                else:
                    winning_choice_index = random.choice(candidates)
                
                winning_choice_text = choices[winning_choice_index]
                success_chance = (max_votes / total_votes) * 100

            roll = random.uniform(0, 100)
            is_success = roll <= success_chance

        prev_event = self.state.get("current_event", "")
        
        outcome_text = f"Survivors chose: **{winning_choice_text}**\n"
        outcome_text += f"Votes: {votes.get(str(winning_choice_index), 0)}/{total_votes} ({success_chance:.1f}% chance)\n"
        outcome_text += f"Outcome: {'SUCCESS ✅' if is_success else 'FAILURE ❌'}"
        
        # Add to history
        self.state["history"].append({
            "event": prev_event,
            "choice": winning_choice_text,
            "success": is_success,
            "outcome_text": outcome_text
        })
        
        # History Management: Sliding Window
        # We keep the LAST 8 events for context.
        if len(self.state["history"]) > 8:
            self.state["history"] = self.state["history"][-8:]

        # Construct History Summary for Prompt
        # We want to be efficient with tokens but maintain context.
        # Format: "Round X: [Choice] -> [Outcome]"
        
        history_summary = ""
        for i, h in enumerate(self.state["history"]):
            short_event = h['event'][:50] + "..." if len(h['event']) > 50 else h['event']
            history_summary += f"Round -{len(self.state['history'])-i}: Event: {short_event} | Choice: {h['choice']} | Result: {'Success' if h['success'] else 'Failure'}\n"

        prompt = (
            f"STORY HISTORY (Last {len(self.state['history'])} rounds):\n{history_summary}\n\n"
            f"IMMEDIATE PAST:\n"
            f"Last Event: {prev_event}\n"
            f"Action Taken: {winning_choice_text}\n"
            f"Result: {'Success' if is_success else 'Failure'}. (Chance was {success_chance:.1f}%)\n\n"
            "INSTRUCTIONS:\n"
            "1. Describe the immediate outcome of the action based on the result (Success/Failure).\n"
            "2. Then, present the NEXT dangerous situation or event that naturally follows.\n"
            "3. Provide 5 distinct choices for what to do next.\n"
            "4. Maintain a consistent, serious zombie apocalypse theme."
        )
        
        new_content = await self.generate_content(prompt)
        
        if new_content:
            self.state["current_event"] = new_content["event_text"]
            self.state["choices"] = new_content["choices"]
            self.state["votes"] = {}
            self.state["voters"] = []
            self.state["last_update"] = datetime.now().timestamp()
            self.state["round"] += 1
            await self.save_state_async()
            
            await self.update_message(channel)
        else:
            await channel.send("⚠️ The AI Game Master is currently offline. The survivors are in limbo...")

    async def update_message(self, channel):
        embed = discord.Embed(
            title="🧟 ZOMBIE SURVIVAL - LIVE",
            description=self.state["current_event"],
            color=discord.Color.dark_red()
        )
        
        # Add Choices
        choices_text = ""
        for i, choice in enumerate(self.state["choices"]):
            choices_text += f"**{i+1}.** {choice}\n"
        
        embed.add_field(name="Current Choices", value=choices_text, inline=False)
        
        # Add History/Status
        last_history = self.state["history"][-1] if self.state["history"] else None
        if last_history:
            embed.add_field(name="Last Round Result", value=last_history["outcome_text"], inline=False)
            
        next_update = datetime.fromtimestamp(self.state["last_update"]) + timedelta(hours=UPDATE_INTERVAL_HOURS)
        embed.set_footer(text=f"Round {self.state['round']} | Next Update: {discord.utils.format_dt(next_update, 'R')}")
        
        view = ZombieView(self)
        
        # Delete old message if possible to keep channel clean, or just send new one
        msg = await channel.send(embed=embed, view=view)
        self.state["message_id"] = msg.id
        await self.save_state_async()

    @commands.hybrid_command(name="zombie_survival", description="Start or view the Zombie Survival game")
    async def zombie_survival(self, ctx: commands.Context):
        if not self.state:
             self.state = await self.load_state_async()

        if self.state.get("active") and self.state.get("channel_id") == ctx.channel.id:
            # Resend current state
            channel = ctx.channel
            await self.update_message(channel)
            await ctx.send("Resynced game state.", ephemeral=True)
        else:
            # Start new game
            self.state["active"] = True
            self.state["channel_id"] = ctx.channel.id
            self.state["history"] = []
            self.state["round"] = 1
            
            await ctx.defer()
            
            # Initial Generation
            prompt = "Start a new zombie apocalypse story. The survivors have just gathered. Describe the initial situation and 5 choices."
            new_content = await self.generate_content(prompt)
            
            if new_content:
                self.state["current_event"] = new_content["event_text"]
                self.state["choices"] = new_content["choices"]
                self.state["votes"] = {}
                self.state["voters"] = []
                self.state["last_update"] = datetime.now().timestamp()
                await self.save_state_async()
                await self.update_message(ctx.channel)
                # await ctx.send("Game Started!", ephemeral=True) # update_message sends the embed
            else:
                await ctx.send("Failed to start game (AI Error).")
    
    @commands.command(name="force_zombie_update", hidden=True)
    @commands.is_owner()
    async def force_zombie_update(self, ctx):
        """Force the zombie game to update immediately."""
        await ctx.send("Forcing update...")
        await self.resolve_round()

class ZombieView(discord.ui.View):
    def __init__(self, cog: ZombieSurvival):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="1", style=discord.ButtonStyle.primary, custom_id="zombie_1")
    async def vote_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_vote(interaction, 0)

    @discord.ui.button(label="2", style=discord.ButtonStyle.primary, custom_id="zombie_2")
    async def vote_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_vote(interaction, 1)

    @discord.ui.button(label="3", style=discord.ButtonStyle.primary, custom_id="zombie_3")
    async def vote_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_vote(interaction, 2)

    @discord.ui.button(label="4", style=discord.ButtonStyle.primary, custom_id="zombie_4")
    async def vote_4(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_vote(interaction, 3)

    @discord.ui.button(label="5", style=discord.ButtonStyle.primary, custom_id="zombie_5")
    async def vote_5(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_vote(interaction, 4)

    async def handle_vote(self, interaction: discord.Interaction, choice_idx: int):
        user_id = interaction.user.id
        if user_id in self.cog.state["voters"]:
            await interaction.response.send_message("You have already voted this round!", ephemeral=True)
            return

        # Record vote
        self.cog.state["voters"].append(user_id)
        current_votes = self.cog.state["votes"].get(str(choice_idx), 0)
        self.cog.state["votes"][str(choice_idx)] = current_votes + 1
        await self.cog.save_state_async()
        
        await interaction.response.send_message(f"Vote cast for Choice {choice_idx + 1}!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(ZombieSurvival(bot))
