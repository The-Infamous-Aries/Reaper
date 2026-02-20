
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

# --- Constants ---
DATA_DIR = os.getenv('DATA_DIR', os.path.join(os.path.dirname(__file__)))
STATE_FILE = os.path.join(DATA_DIR, 'zombie_state.json')
UPDATE_INTERVAL_HOURS = 2  # Set to 2 hours for a more deliberate pace, reducing API calls.
INVENTORY_LIMIT = 5
ZOMBIE_THUMBNAIL_URL = "https://t4.ftcdn.net/jpg/06/04/24/25/360_F_604242595_aOXbhCveYiqzeEvq1IVWAC5N5YdGlQOK.jpg"

# Ensure data directory exists
if not os.path.exists(DATA_DIR):
    try:
        os.makedirs(DATA_DIR)
    except Exception as e:
        logging.getLogger("ZombieSurvival").error(f"Failed to create DATA_DIR: {e}")

SURVIVOR_DEFAULTS = {
    "health": 100,
    "stamina": 100,
    "morale": 75,
    "inventory": [],
    "status": "Normal"  # Normal, Injured, Exhausted, Deceased
}

class ZombieSurvival(commands.Cog):
    """An epic, ongoing, AI-driven zombie survival simulation."""
    def __init__(self, bot):
        self.bot = bot
        self.state = {}
        self.bot.loop.create_task(self.initialize())
        self.game_loop.start()

    async def initialize(self):
        """Loads the game state when the cog is initialized."""
        self.state = await self.load_state_async()

    def cog_unload(self):
        """Cleanly stops the game loop when the cog is unloaded."""
        self.game_loop.cancel()

    async def load_state_async(self) -> Dict:
        """Asynchronously loads the game state from a JSON file."""
        if os.path.exists(STATE_FILE):
            try:
                # Use asyncio.to_thread for non-blocking file I/O
                def _read():
                    with open(STATE_FILE, 'r') as f:
                        return json.load(f)
                return await asyncio.to_thread(_read)
            except (json.JSONDecodeError, IOError) as e:
                logging.getLogger("ZombieSurvival").error(f"Error loading zombie state: {e}")
        return self.get_default_state()

    def get_default_state(self):
        """Returns a clean, default state for the game."""
        return {
            "active": False, "history": [], "current_event": "The outbreak has just begun...",
            "choices": [], "votes": {}, "voters": [], "last_update": 0,
            "channel_id": None, "message_id": None, "round": 0,
            "survivors": {}, "world_state": {}
        }

    async def save_state_async(self):
        """Asynchronously saves the current game state to a JSON file."""
        try:
            def _write():
                # Create a copy to avoid issues during serialization
                state_to_save = self.state.copy()
                with open(STATE_FILE, 'w') as f:
                    json.dump(state_to_save, f, indent=4)
            await asyncio.to_thread(_write)
        except IOError as e:
            logging.getLogger("ZombieSurvival").error(f"Error saving zombie state: {e}")

    async def generate_content(self, context_prompt: str) -> Optional[Dict]:
        """Generates story content using the Gemini API."""
        if not GEMINI_API_KEY:
            logging.getLogger("ZombieSurvival").error("Gemini API key is missing.")
            return None

        system_instruction = (
            "You are a Zombie Survival Game Master for a Discord game. Your tone is dark, gritty, realistic, and intense, like 'The Last of Us' or 'The Walking Dead'. "
            "You will describe suspenseful situations in a zombie apocalypse. Your output must be a single, raw JSON object without any markdown. "
            "The story must be continuous and reflect the history and survivor statuses provided. "
            "The 'event_text' should be a detailed, atmospheric description of the new situation. The choices should be distinct and meaningful. "
            "The outcomes must describe the direct consequences of the action. Morale and Stamina should influence the narrative outcomes. Low morale might cause mistakes, high morale might lead to heroic actions."
            "JSON STRUCTURE: "
            "{ "
            "  'event_text': 'A detailed, atmospheric description of the current situation.', "
            "  'choices': ['Actionable Choice 1', 'Actionable Choice 2', 'Actionable Choice 3', 'Actionable Choice 4', 'Actionable Choice 5'], "
            "  'world_impact': { "
            "    'success_outcome': 'A descriptive paragraph of what happens on SUCCESS.', "
            "    'failure_outcome': 'A descriptive paragraph of what happens on FAILURE.', "
            "    'stat_changes': { 'user_id_1': {'health': -10, 'morale': 5}, 'user_id_2': {'stamina': -15} }, "
            "    'new_items': ['Bandage', 'Canned Food'] "
            "  } "
            "}"
        )

        full_prompt = f"{system_instruction}\n\n{context_prompt}"

        try:
            timeout = aiohttp.ClientTimeout(total=120)  # Increased timeout for longer generation
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GEMINI_API_KEY}"
                headers = {"Content-Type": "application/json"}
                payload = {"contents": [{"parts": [{"text": full_prompt}]}], "generationConfig": {"responseMimeType": "application/json"}}
                
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        try:
                            content_text = data["candidates"][0]["content"]["parts"][0]["text"]
                            return json.loads(content_text)
                        except (KeyError, IndexError, json.JSONDecodeError) as e:
                            logging.getLogger("ZombieSurvival").error(f"Gemini parsing error: {e}\nRaw content: {data}")
                            return None
                    else:
                        logging.getLogger("ZombieSurvival").error(f"Gemini API error: {resp.status}\n{await resp.text()}")
                        return None
        except Exception as e:
            logging.getLogger("ZombieSurvival").error(f"Generate content error: {e}")
            return None

    @tasks.loop(hours=UPDATE_INTERVAL_HOURS)
    async def game_loop(self):
        """The main game loop that triggers round resolution."""
        if not self.state.get("active") or not self.state.get("channel_id"):
            return

        await self.bot.wait_until_ready()
        
        last_update = self.state.get("last_update", 0)
        # Ensure the interval has truly passed
        if datetime.now().timestamp() - last_update >= (UPDATE_INTERVAL_HOURS * 3600):
            await self.resolve_round()

    @game_loop.before_loop
    async def before_game_loop(self):
        await self.bot.wait_until_ready()

    async def resolve_round(self):
        """Resolves the current round by tallying votes and generating the next event."""
        channel = self.bot.get_channel(self.state.get("channel_id"))
        if not channel:
            self.state["active"] = False  # Stop the game if channel is gone
            return

        votes = self.state.get("votes", {})
        choices = self.state.get("choices", [])
        total_votes = sum(votes.values())
        
        # Determine winning choice
        if not choices:
            winning_choice_text = "The survivors were indecisive, and chaos took over."
            success_chance = 0
            is_success = False
        elif total_votes == 0:
            winning_choice_index = random.randint(0, len(choices) - 1)
            winning_choice_text = choices[winning_choice_index]
            success_chance = 40  # Inaction is risky
            is_success = random.uniform(0, 100) <= success_chance
        else:
            max_votes = max(votes.values())
            candidates = [int(k) for k, v in votes.items() if v == max_votes]
            winning_choice_index = random.choice(candidates)
            winning_choice_text = choices[winning_choice_index]
            # Success is influenced by consensus and a bit of luck
            success_chance = min(95, (max_votes / total_votes) * 70 + 25)
            is_success = random.uniform(0, 100) <= success_chance

        world_impact = self.state.get("world_impact", {})
        outcome_details = world_impact.get("success_outcome" if is_success else "failure_outcome", "The world is indifferent to their struggle.")

        # Build outcome text
        outcome_text = (
            f"**Action:** {winning_choice_text} *(Success Chance: {success_chance:.1f}%)* -> **{'SUCCESS' if is_success else 'FAILURE'}**\n\n"
            f"*{outcome_details}*"
        )
        
        # Apply stat changes and check for death
        death_report = ""
        if is_success: # Only apply changes on success for now, failure is narrative punishment.
            stat_changes = world_impact.get("stat_changes", {})
            for user_id, changes in stat_changes.items():
                survivor = self.state["survivors"].get(user_id)
                if survivor and survivor.get("status") != "Deceased":
                    for stat, value in changes.items():
                        survivor[stat] = max(0, min(100, survivor.get(stat, 0) + value))
        
        for user_id in list(self.state["survivors"].keys()):
            survivor = self.state["survivors"][user_id]
            if survivor.get("health", 0) <= 0 and survivor.get("status") != "Deceased":
                survivor["status"] = "Deceased"
                user = self.bot.get_user(int(user_id))
                death_report += f"\n💀 **{user.display_name if user else 'A survivor'} has succumbed to the apocalypse.**"
        
        if death_report:
            outcome_text += f"\n\n**GRIM NEWS:**{death_report}"

        # Add to history
        self.state["history"].append({"event": self.state.get("current_event", ""), "outcome_text": outcome_text})
        if len(self.state["history"]) > 5:  # Keep history concise
            self.state["history"] = self.state["history"][-5:]

        # --- Generate Next Event ---
        history_summary = "\n".join(f"- Round {i-len(h_item['history'])}: {h_item['outcome_text'][:100]}..." for i, h_item in enumerate(self.state["history"]))
        survivor_summary = "\n".join(
            f"- {self.bot.get_user(int(uid)).display_name if self.bot.get_user(int(uid)) else 'Survivor'}: H:{s['health']} M:{s['morale']} S:{s['stamina']} Status: {s['status']}"
            for uid, s in self.state["survivors"].items() if s.get("status") != "Deceased"
        )
        
        prompt = (
            f"STORY HISTORY (Recent Events):\n{history_summary}\n\n"
            f"LIVING SURVIVOR STATUSES:\n{survivor_summary}\n\n"
            f"IMMEDIATE PAST EVENT: {self.state.get('current_event', '')}\n"
            f"PAST EVENT OUTCOME: {outcome_text}\n\n"
            "INSTRUCTIONS: Based on the history and survivor statuses, generate the next event. Describe the direct consequences of the last outcome, then create a new dangerous situation. Provide 5 distinct, actionable choices."
        )
        
        new_content = await self.generate_content(prompt)
        if new_content and all(k in new_content for k in ["event_text", "choices", "world_impact"]):
            self.state.update({
                "current_event": new_content["event_text"], "choices": new_content["choices"],
                "world_impact": new_content.get("world_impact", {}), "votes": {}, "voters": [],
                "last_update": datetime.now().timestamp(), "round": self.state["round"] + 1
            })
            await self.save_state_async()
            await self.update_message(channel)
        else:
            await channel.send("⚠️ The AI Game Master seems to have momentarily lost its train of thought... The story will resume shortly.")

    async def update_message(self, channel):
        """Updates the main game message with the current state."""
        embed = discord.Embed(title="🧟 ZOMBIE SURVIVAL: The Echoes of the Fallen", description=f"**Round {self.state['round']}**\n\n{self.state['current_event']}", color=discord.Color.dark_red())
        embed.set_thumbnail(url=ZOMBIE_THUMBNAIL_URL)

        choices_text = "\n".join(f"**{i+1}.** {choice}" for i, choice in enumerate(self.state["choices"]))
        embed.add_field(name="What do you do?", value=choices_text or "No choices available.", inline=False)

        survivor_text = ""
        for user_id, survivor in sorted(self.state["survivors"].items(), key=lambda item: item[1]['status'] != 'Deceased'):
            user = self.bot.get_user(int(user_id))
            if user:
                if survivor["status"] == "Deceased":
                    survivor_text += f"💀 ~~{user.display_name}~~ (Deceased)\n"
                else:
                    survivor_text += f"**{user.display_name}** | H:{survivor['health']} S:{survivor['stamina']} M:{survivor['morale']}\n"
        if survivor_text:
            embed.add_field(name="Survivor Roster", value=survivor_text, inline=False)
        
        if self.state["history"]:
            embed.add_field(name="Last Round's Outcome", value=self.state["history"][-1]["outcome_text"], inline=False)
            
        next_update = datetime.fromtimestamp(self.state["last_update"]) + timedelta(hours=UPDATE_INTERVAL_HOURS)
        embed.set_footer(text=f"A new chapter unfolds soon... | Next update: {discord.utils.format_dt(next_update, 'R')}")
        
        view = ZombieView(self)
        try:
            msg = await channel.send(embed=embed, view=view)
            self.state["message_id"] = msg.id
            await self.save_state_async()
        except discord.HTTPException as e:
            logging.getLogger("ZombieSurvival").error(f"Failed to send message: {e}")

    @commands.hybrid_command(name="zombie_survival", description="Start or join the Zombie Survival game.")
    async def zombie_survival(self, ctx: commands.Context):
        """Starts the game or allows a new player to join."""
        is_new_game = not self.state.get("active")
        
        if is_new_game:
            self.state = self.get_default_state()
            self.state["active"] = True
            self.state["channel_id"] = ctx.channel.id
            self.state["survivors"][str(ctx.author.id)] = SURVIVOR_DEFAULTS.copy()
            await ctx.defer()
            prompt = "The zombie apocalypse has just begun. A small group of survivors, including the players, find themselves huddled together in a derelict convenience store as dusk falls. The sounds of the undead echo outside. Generate the first event and 5 choices for survival."
            new_content = await self.generate_content(prompt)
            if new_content:
                self.state.update({
                    "current_event": new_content["event_text"], "choices": new_content["choices"],
                    "world_impact": new_content.get("world_impact", {}), "last_update": datetime.now().timestamp(), "round": 1
                })
                await self.save_state_async()
                await self.update_message(ctx.channel)
            else:
                await ctx.send("The apocalypse failed to materialize (AI Error). Please try again later.", ephemeral=True)
        else:
            if str(ctx.author.id) not in self.state["survivors"]:
                self.state["survivors"][str(ctx.author.id)] = SURVIVOR_DEFAULTS.copy()
                await self.save_state_async()
                await ctx.send(f"A new face in the gloom. Welcome, {ctx.author.mention}. Try to stay alive.", ephemeral=True)
            else:
                 await ctx.send("You're already in the thick of it. Check the latest message to act.", ephemeral=True)
            # Resend the message to the current user
            await self.update_message(ctx.channel)


    @commands.hybrid_command(name="zstatus", description="Check your survivor status.")
    async def zstatus(self, ctx: commands.Context):
        """Privately shows your current status in the game."""
        if not self.state.get("active"):
            await ctx.send("The zombie apocalypse has not begun yet.", ephemeral=True)
            return

        survivor = self.state["survivors"].get(str(ctx.author.id))
        if not survivor:
            await ctx.send("You are not part of this survival story. Use `/zombie_survival` to join.", ephemeral=True)
            return
        
        if survivor.get("status") == "Deceased":
            await ctx.send("Your story has ended. You are among the fallen.", ephemeral=True)
            return

        embed = discord.Embed(title=f"{ctx.author.display_name}'s Condition", color=discord.Color.dark_green())
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.add_field(name="Health", value=f"{survivor['health']}/100", inline=True)
        embed.add_field(name="Stamina", value=f"{survivor['stamina']}/100", inline=True)
        embed.add_field(name="Morale", value=f"{survivor['morale']}/100", inline=True)
        inventory = ", ".join(survivor["inventory"]) if survivor["inventory"] else "Empty"
        embed.add_field(name="Inventory", value=inventory, inline=False)
        embed.set_footer(text=f"Status: {survivor['status']}")
        await ctx.send(embed=embed, ephemeral=True)

    @commands.command(name="force_zombie_update", hidden=True)
    @commands.is_owner()
    async def force_zombie_update(self, ctx):
        """Force the zombie game to update immediately."""
        await ctx.send("Forcing a new chapter in the story...", ephemeral=True)
        await self.resolve_round()

class ZombieView(discord.ui.View):
    def __init__(self, cog: ZombieSurvival):
        super().__init__(timeout=None)
        self.cog = cog
        # Dynamically add buttons based on choices
        for i, choice in enumerate(cog.state.get("choices", [])):
            self.add_item(VoteButton(i, choice))

class VoteButton(discord.ui.Button):
    def __init__(self, index: int, choice_text: str):
        # Shorten label if choice text is too long
        label = str(index + 1)
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=f"zombie_vote_{index}")
        self.choice_index = index

    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        
        # Check if player is a survivor
        if str(user_id) not in self.cog.state["survivors"] or self.cog.state["survivors"][str(user_id)].get("status") == "Deceased":
            await interaction.response.send_message("The dead do not have a say.", ephemeral=True)
            return

        if user_id in self.cog.state["voters"]:
            await interaction.response.send_message("You have already cast your vote for this round.", ephemeral=True)
            return

        self.cog.state["voters"].append(user_id)
        current_votes = self.cog.state["votes"].get(str(self.choice_index), 0)
        self.cog.state["votes"][str(self.choice_index)] = current_votes + 1
        await self.cog.save_state_async()
        
        await interaction.response.send_message(f"You voted for choice {self.label}. May it be the right one.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(ZombieSurvival(bot))
