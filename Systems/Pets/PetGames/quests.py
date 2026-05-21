
import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from typing import Literal
import random
import asyncio
import re

from Systems.Functions import user_data_manager
from Systems.Functions import emoji as emoji_manager
from Systems.Functions.optimal_file_manager import OptimalFileManager
from Systems.Pets.Logic.pet_brain import LootCalculator, StatsCalculator
# Import the battle system to initiate battles
from Systems.Pets.PetGames.battle_system import UnifiedBattleView
from Systems.Functions.local_ai import chat_complete_json_sync

file_manager = OptimalFileManager()

difficulties = ["Apprentice", "Journeyman", "Senior"]
locations = ["Camp", "Bonfire", "Beach", "Forest", "Hot Air Balloon", "Cruiseship", "Mountain", "Gym", "Graveyard", "Festival", "Glacier", "Pyramids"]

# --- Local AI Quest Generation ---
def _generate_quest_from_groq(location, difficulty):
    """Generates a quest using local AI (Ollama → Groq fallback)."""

    # Location-specific theming hints
    location_themes = {
        "Camp": "wilderness survival, campfires, tents, outdoor cooking, nature sounds",
        "Bonfire": "crackling flames, gathering warmth, storytelling, sparks flying, cozy atmosphere",
        "Beach": "ocean waves, sandy shores, seashells, tide pools, salty breeze, driftwood",
        "Forest": "towering trees, rustling leaves, woodland creatures, moss-covered paths, filtered sunlight",
        "Hot Air Balloon": "soaring heights, panoramic views, gentle winds, floating clouds, basket creaking",
        "Cruiseship": "ocean voyage, deck activities, nautical themes, sea spray, ship's horn",
        "Mountain": "rocky peaks, thin air, steep climbs, mountain goats, echoing calls, snow caps",
        "Gym": "exercise equipment, training routines, physical challenges, sweat, determination",
        "Graveyard": "ancient tombstones, misty atmosphere, eerie silence, weathered monuments, shadows",
        "Festival": "colorful decorations, music, crowds, celebration, food stalls, joyful chaos",
        "Glacier": "ice formations, freezing winds, slippery surfaces, crystal formations, arctic wildlife",
        "Pyramids": "ancient stones, desert heat, mysterious passages, hieroglyphs, sand dunes"
    }

    theme_elements = location_themes.get(location, "mysterious environment, unknown challenges")

    prompt = f"""
    Create a cohesive 5-stage pet quest for a {difficulty} level pet exploring the {location}.
    
    LOCATION THEMING: Incorporate these elements throughout: {theme_elements}
    Make every stage description immersive and specific to {location}. Use vivid, location-appropriate imagery.
    
    STORY FLOW: Create a narrative where each stage builds naturally to the next:
    1. "Entering Location" - Arrival and first impressions
    2. "Looking Around" - Exploration and discovery  
    3. "Avoiding Hostile Pets" - First encounter with danger
    4. "Locating a FREE to open Loot Chest" - Finding treasure
    5. "Exiting Location" - Departure with rewards

    CHOICE DESIGN: Each choice must use stats that make thematic sense for the action:
    - Physical actions (climbing, fighting, breaking) → ATT/DEF
    - Skillful actions (dodging, sneaking, precision) → DEX/INT  
    - Endurance actions (persisting, staying calm, maintaining energy) → ENE/HAP

    SPECIFIC REQUIREMENTS:
    - **Stage 3: Avoiding Hostile Pets**: Create TWO versions:
      * "scare_off" sub_type: Use %%HOSTILE_PET%% placeholder, focus on intimidation
      * "evade" sub_type: Use %%HOSTILE_PET%% placeholder, focus on escape
    - **Stage 4: Locating a FREE to open Loot Chest**: Create TWO versions:
      * "mimic" sub_type: Describe a chest that seems suspicious but don't explicitly say "mimic". Use subtle hints like "the chest seems to shift slightly", "something feels off about this chest", "the chest's lock looks unusually organic"
      * "real_chest" sub_type: Normal chest with "double_loot_choice" (1, 2, or 3)
    - **All stages**: Include "difficulty_modifier" between 0.8-1.5

    Return ONLY valid JSON with this structure:
    {{
      "stages": [
        {{
          "stage_name": "Entering Location",
          "event": "[Vivid {location}-themed arrival description]",
          "difficulty_modifier": 1.0,
          "choices": {{
            "1": "[Physical approach using ATT/DEF]",
            "2": "[Skillful approach using DEX/INT]", 
            "3": "[Endurance approach using ENE/HAP]"
          }}
        }},
        {{
          "stage_name": "Looking Around",
          "event": "[Detailed {location} exploration scene]",
          "difficulty_modifier": 1.0,
          "choices": {{
            "1": "[Physical exploration using ATT/DEF]",
            "2": "[Careful investigation using DEX/INT]",
            "3": "[Patient observation using ENE/HAP]"
          }}
        }},
        {{
          "stage_name": "Avoiding Hostile Pets",
          "sub_type": "scare_off",
          "event": "A %%HOSTILE_PET%% blocks your path through the {location}! It looks aggressive and territorial.",
          "difficulty_modifier": 1.2,
          "choices": {{
            "1": "[Intimidating display using ATT/DEF]",
            "2": "[Clever misdirection using DEX/INT]",
            "3": "[Persistent confidence using ENE/HAP]"
          }}
        }},
        {{
          "stage_name": "Avoiding Hostile Pets", 
          "sub_type": "evade",
          "event": "The %%HOSTILE_PET%% charges at you across the {location}! You need to escape quickly!",
          "difficulty_modifier": 1.2,
          "choices": {{
            "1": "[Forceful escape using ATT/DEF]",
            "2": "[Agile evasion using DEX/INT]",
            "3": "[Enduring retreat using ENE/HAP]"
          }}
        }},
        {{
          "stage_name": "Locating a FREE to open Loot Chest",
          "sub_type": "mimic",
          "event": "[{location}-themed scene with suspicious chest - use subtle hints, no direct mimic mention]",
          "difficulty_modifier": 1.3,
          "choices": {{
            "1": "[Direct forceful approach using ATT/DEF - best for mimics]",
            "2": "[Careful examination using DEX/INT]",
            "3": "[Cautious patience using ENE/HAP]"
          }}
        }},
        {{
          "stage_name": "Locating a FREE to open Loot Chest",
          "sub_type": "real_chest", 
          "event": "[{location}-themed scene with genuine treasure chest]",
          "difficulty_modifier": 1.3,
          "double_loot_choice": 2,
          "choices": {{
            "1": "[Forceful opening using ATT/DEF]",
            "2": "[Skillful unlocking using DEX/INT - double loot choice]",
            "3": "[Patient searching using ENE/HAP]"
          }}
        }},
        {{
          "stage_name": "Exiting Location",
          "event": "[{location}-themed departure with sense of accomplishment]",
          "difficulty_modifier": 1.0,
          "choices": {{
            "1": "[Strong departure using ATT/DEF]",
            "2": "[Graceful exit using DEX/INT]",
            "3": "[Energetic celebration using ENE/HAP]"
          }}
        }}
      ]
    }}
    """

    try:
        result = chat_complete_json_sync(
            messages=[{"role": "user", "content": prompt}],
            system="You are a creative quest designer for a pet adventure game. Return only valid JSON.",
            temperature=0.8,
            max_tokens=1500,
        )
        return result
    except Exception as e:
        print(f"An unexpected error occurred while generating quest from local AI: {e}")
        return None

def generate_or_load_quest(location, difficulty):
    """
    Tries to generate a fresh quest via local AI. Falls back to a pre-generated
    file if local AI is unavailable. Only saves a new file when generation succeeds
    AND fewer than 5 files already exist for this location+difficulty combo
    (prevents unbounded disk growth).
    """
    script_dir = os.path.dirname(os.path.realpath(__file__))
    quest_dir  = os.path.join(script_dir, '..', 'Logic', 'Quests')
    os.makedirs(quest_dir, exist_ok=True)

    # Try local AI first
    quest_data = _generate_quest_from_groq(location, difficulty)
    if quest_data and quest_data.get("stages"):
        # Only cache if we have fewer than 5 files for this combo
        existing = [f for f in os.listdir(quest_dir)
                    if f.startswith(f"{location}_{difficulty}_") and f.endswith('.json')]
        if len(existing) < 5:
            file_path = os.path.join(quest_dir, f"{location}_{difficulty}_{random.randint(1, 9999)}.json")
            try:
                with open(file_path, 'w') as f:
                    json.dump(quest_data, f, indent=4)
            except Exception:
                pass  # caching failure is non-fatal
        return quest_data

    # Fallback to pre-generated files
    pregen_files = [f for f in os.listdir(quest_dir)
                    if f.startswith(f"{location}_{difficulty}") and f.endswith('.json')]
    if pregen_files:
        try:
            with open(os.path.join(quest_dir, random.choice(pregen_files)), 'r') as f:
                return json.load(f)
        except Exception:
            pass

    return None

def _strip_hints(text):
    return re.sub(r'\s*\(.*?\)\s*', '', text).strip()


class QuestView(discord.ui.View):
    def __init__(self, bot, pet, quest_data, difficulty, user_id, location):
        super().__init__()
        self.bot = bot
        self.pet = pet
        self.quest_data = quest_data
        self.difficulty = difficulty
        self.user_id = user_id
        self.location = location
        self.current_stage_index = 0

        # Reorder stages based on the specified logic
        all_stages = quest_data.get('stages', [])
        ordered_stages = []

        # 1. Entering Location
        ordered_stages.append(next((s for s in all_stages if s['stage_name'] == 'Entering Location'), None))

        # 2. Avoid Hostile Pet 'scare_off'
        ordered_stages.append(next((s for s in all_stages if s['stage_name'] == 'Avoiding Hostile Pets' and s.get('sub_type') == 'scare_off'), None))

        # 3. Looking Around
        ordered_stages.append(next((s for s in all_stages if s['stage_name'] == 'Looking Around'), None))

        # 4. Locating a FREE to open Loot Chest (50/50 for mimic or real)
        loot_stages = [s for s in all_stages if s['stage_name'] == 'Locating a FREE to open Loot Chest']
        if loot_stages:
            ordered_stages.append(random.choice(loot_stages))

        # 5. Avoiding Hostile Pet 'evade'
        ordered_stages.append(next((s for s in all_stages if s['stage_name'] == 'Avoiding Hostile Pets' and s.get('sub_type') == 'evade'), None))

        # 6. Exiting Location
        ordered_stages.append(next((s for s in all_stages if s['stage_name'] == 'Exiting Location'), None))

        self.stages_data = [s for s in ordered_stages if s is not None]

        self.xp = 0
        self.loot = []
        self.message = None
        self.event_log = []

        # State for hostile pet encounters
        self.hostile_pet = None
        self.hostile_pet_defeated = False

    async def start_quest(self, interaction: discord.Interaction):
        self.interaction = interaction
        await self.next_stage(interaction) # Pass interaction to the first next_stage call

    async def next_stage(self, interaction: discord.Interaction = None):
        if self.message:
            try:
                await self.message.edit(view=None)
            except (discord.NotFound, discord.HTTPException):
                pass

        if self.current_stage_index >= len(self.stages_data):
            await self.end_quest(success=True)
            return

        self.current_event = self.stages_data[self.current_stage_index]
        stage_name = self.current_event["stage_name"]
        sub_type = self.current_event.get("sub_type")

        # Skip "evade" stage if the pet was already defeated
        if stage_name == "Avoiding Hostile Pets" and sub_type == "evade":
            if self.hostile_pet_defeated:
                self.current_stage_index += 1
                await self.next_stage()
                return

        # Generate the hostile pet early and replace the placeholder in the event text
        if stage_name == "Avoiding Hostile Pets":
            if self.hostile_pet is None:
                self.hostile_pet = LootCalculator.generate_hostile_pet(self.pet, self.difficulty)
            boss_name = f"{self.location} {self.hostile_pet['species']}"
            self.current_event['event'] = self.current_event['event'].replace('%%HOSTILE_PET%%', boss_name)

        location_emoji = emoji_manager.mention(self.location) or ""
        pet_emoji = emoji_manager.mention(self.pet.get("species")) or ""
        element1_emoji = emoji_manager.mention(self.pet.get("element")) or ""
        element2_emoji = emoji_manager.mention(self.pet.get("element2")) or ""

        embed = discord.Embed(
            title=f"Quest: {self.location} {location_emoji}{pet_emoji}{element1_emoji}{element2_emoji}",
            description=f"**{stage_name}**\n\n{_strip_hints(self.current_event['event'])}",
            color=discord.Color.green()
        )

        choices_text = []
        for i, choice_text in self.current_event["choices"].items():
            choices_text.append(f"**{i}.** {_strip_hints(choice_text)}")
        embed.description += "\n\n" + "\n".join(choices_text)

        self.clear_items()
        for i in self.current_event["choices"].keys():
            self.add_item(ChoiceButton(self, int(i), str(i)))

        # If interaction is provided, it's the first message
        if interaction:
            await interaction.response.send_message(embed=embed, view=self)
            self.message = await interaction.original_response()
        # Otherwise, edit the existing message
        elif self.message:
            await self.message.edit(embed=embed, view=self)

    async def show_progress_update(self, message, success=True):
        if not self.message:
            return

        embed = self.message.embeds[0]
        embed.description = message
        embed.color = discord.Color.green() if success else discord.Color.orange()

        # Title is already set in next_stage, no need to update it here unless it changes

        embed.clear_fields()

        await self.message.edit(embed=embed, view=None)
        await asyncio.sleep(random.randint(5, 7))

    async def handle_choice(self, choice_num):
        self.current_event = self.stages_data[self.current_stage_index]
        stage_name = self.current_event["stage_name"]

        stat_map = {
            1: ("ATT", "DEF"),
            2: ("DEX", "INT"),
            3: ("ENE", "HAP")
        }
        stat1, stat2 = stat_map[choice_num]

        # --- Generic Skill Check Calculation ---
        pet_skill = (self.pet.get(stat1, 0) + self.pet.get(stat2, 0)) / 2
        difficulty_multiplier = {"Apprentice": 0.8, "Journeyman": 1.0, "Senior": 1.2}
        stage_difficulty_mod = self.current_event.get('difficulty_modifier', 1.0)
        required_skill = 10 * difficulty_multiplier[self.difficulty] * stage_difficulty_mod
        
        # Base success rate formula
        success_rate = min(95, max(5, int((pet_skill / max(1, required_skill)) * 50))) # Clamp between 5% and 95%
        success = random.randint(1, 100) <= success_rate

        event_description = _strip_hints(self.current_event["event"])
        choice_description = _strip_hints(self.current_event["choices"][str(choice_num)])

        # --- Stage-Specific Logic ---

        # --- Stage 1: Entering Location (No Failure) ---
        if stage_name == "Entering Location":
            success = True
            success_rate = 100
            await self.show_progress_update("You enter the area and begin your quest.")

        # --- Stage 3 & 5: Avoiding Hostile Pets ---
        elif stage_name == "Avoiding Hostile Pets":
            sub_type = self.current_event.get("sub_type")

            # Pet is already generated and placeholder replaced in next_stage
            boss_name = f"{self.location} {self.hostile_pet['species']}"
            event_description = event_description.replace('%%HOSTILE_PET%%', boss_name)

            skill_influence = ((pet_skill - required_skill) / max(1, required_skill)) * 15

            if sub_type == "scare_off":
                base_rate = 65  # Higher success rate for scare_off as requested
            elif sub_type == "evade":
                base_rate = 50 # Lower success rate for evade
            else:
                base_rate = 40

            success_rate = min(95, max(5, base_rate + skill_influence))
            success = random.randint(1, 100) <= success_rate

            if sub_type == "scare_off":
                if success:
                    # Success means you proceed, but the pet is not defeated.
                    xp_gain = max(10, int(pet_skill * 1.5))
                    self.xp += xp_gain
                    await self.show_progress_update(f"Success! You scared off the {boss_name} for now... and gained {xp_gain} XP.")
                else:
                    # Failure means you must fight.
                    failure_message = f"You failed to scare off the {boss_name}! It attacks!"
                    await self.show_progress_update(failure_message, success=False)
                    
                    battle_won = await self.start_battle(self.hostile_pet)
                    if battle_won:
                        # Winning the battle defeats the pet, so the next encounter is skipped.
                        self.hostile_pet_defeated = True
                        await self.interaction.followup.send("You won the battle and proceed.")
                    else:
                        # Losing ends the quest.
                        await self.end_quest(success=False)
                        return  # End quest on loss

            elif sub_type == "evade":
                if success:
                    xp_gain = max(10, int(pet_skill * 1.5))
                    self.xp += xp_gain
                    await self.show_progress_update(f"Success! You evaded the {boss_name} and gained {xp_gain} XP.")
                else:
                    # Failure to evade also leads to a fight.
                    failure_message = f"You failed to evade the {boss_name}! It attacks!"
                    await self.show_progress_update(failure_message, success=False)

                    battle_won = await self.start_battle(self.hostile_pet)
                    if battle_won:
                        await self.interaction.followup.send("You won the battle and proceed.")
                    else:
                        await self.end_quest(success=False)
                        return # End quest on loss

        # --- Stage 4: Locating a FREE to open Loot Chest ---
        elif stage_name == "Locating a FREE to open Loot Chest":
            # More complex formula
            success_rate = min(95, max(5, int((pet_skill / max(1, required_skill)) * 60) + self.pet.get("LUCK", 0)))
            success = random.randint(1, 100) <= success_rate

            if not success:
                await self.show_progress_update("You fumbled and couldn't open the chest. No loot for you.")
            else:
                sub_type = self.current_event.get("sub_type")
                loot_multiplier = {"Apprentice": 1, "Journeyman": 2, "Senior": 3}
                base_loot_amount = random.randint(1, 3) * loot_multiplier[self.difficulty]
                loot_amount = 0
                chest_emoji = random.choice(emoji_manager.category_mentions("Loot"))
                update_message = ""

                if sub_type == "mimic":
                    if choice_num == 1: # ATT/DEF choice for fighting mimic
                        update_message = f"Your forceful approach revealed the chest's true nature - it was a disguised creature! You defeated it and claimed double loot! {emoji_manager.mention('mimic')}"
                        loot_amount = base_loot_amount * 2
                    else:
                        update_message = f"The chest suddenly snapped shut with rows of teeth! You barely escaped the creature's jaws but found no treasure. {emoji_manager.mention('mimic')}"
                else: # Not a mimic
                    double_loot_choice = self.current_event.get("double_loot_choice", -1)
                    if choice_num == double_loot_choice:
                        update_message = f"Your skillful approach paid off! You found a hidden compartment with double loot! {chest_emoji}"
                        loot_amount = base_loot_amount * 2
                    else:
                        update_message = f"You successfully opened the chest and found treasure inside! {chest_emoji}"
                        loot_amount = base_loot_amount
                
                if loot_amount > 0:
                    new_loot = self.generate_quest_loot(loot_amount)
                    if new_loot:
                        self.loot.extend(new_loot)
                        loot_details = [f'{item.get("count", 1)} {emoji_manager.mention(item.get("name")) or ""}{item.get("name")}' for item in new_loot]
                        update_message += f"\nYou found: {', '.join(loot_details)}!"
                    else:
                        update_message += "\nYou found nothing of value."

                await self.show_progress_update(update_message)

        # --- Exiting Location & Other Stages ---
        else:
            if success:
                xp_gain = max(10, int((pet_skill - required_skill) * 5))
                self.xp += xp_gain
                await self.show_progress_update(f"Success! You navigated the challenge and gained {xp_gain} XP.")
            else:
                # For now, failure in other stages just means no XP
                await self.show_progress_update("You struggled a bit but made it through.", success=False)


        # --- Log the event and move to the next stage ---
        self.event_log.append({
            "event": event_description,
            "choice": choice_description,
            "success": success,
            "success_rate": round(success_rate, 2)
        })

        self.current_stage_index += 1
        await self.next_stage()

    def generate_quest_loot(self, amount):
        """
        Generates a list of loot items for the quest, similar to opening a chest.
        """
        loot_items = []
        item_types = ["Material", "Gem", "Monster", "Potion", "Hat"]

        for _ in range(amount):
            loot_type = random.choice(item_types)
            item = None
            if loot_type == "Material":
                item = LootCalculator.get_material_loot_item(self.difficulty, bypass_chance=True)
            elif loot_type == "Gem":
                item = LootCalculator.get_gem_loot_item(self.difficulty, bypass_chance=True)
            elif loot_type == "Monster":
                item = LootCalculator.get_monster_loot_item(self.difficulty, bypass_chance=True)
            elif loot_type == "Potion":
                item = LootCalculator.get_potion_loot(self.difficulty, bypass_chance=True)
            
            if item:
                # Check if this item (by name and type) is already in loot_items
                found = False
                for existing_item in loot_items:
                    if existing_item['name'] == item['name'] and existing_item['type'] == item['type']:
                        existing_item['count'] = existing_item.get('count', 1) + 1
                        found = True
                        break
                if not found:
                    item['count'] = 1
                    loot_items.append(item)
        
        return loot_items

    async def start_battle(self, boss_pet: dict) -> bool:
        """Starts a battle against a boss pet and returns the result."""
        
        interaction = self.interaction

        # Create a mock context object with the required attributes
        class MockCtx:
            def __init__(self, interaction):
                self.author = interaction.user
                self.guild = interaction.guild
                self.channel = interaction.channel
                self.bot = interaction.client

        mock_ctx = MockCtx(interaction)

        battle_view = await UnifiedBattleView.create_async(
            ctx=mock_ctx,
            battle_type="solo",
            participants=[(interaction.user, self.pet)],
            monster=boss_pet,
            interaction=interaction,
            is_boss_battle=True
        )

        if not battle_view:
            await interaction.followup.send("There was an error initiating the battle.", ephemeral=True)
            return False

        battle_view.difficulty = self.difficulty
        
        embed = battle_view.build_spectator_embed(f"A wild {boss_pet.get('name', 'Boss')} appears!")
        
        message = await interaction.followup.send(embed=embed, view=battle_view)
        battle_view.message = message

        await battle_view.start_action_collection()

        result = await battle_view.battle_complete
        return result

    async def end_quest(self, success):
        if self.message:
            try:
                await self.message.edit(view=None)
            except (discord.NotFound, discord.HTTPException):
                pass
        self.clear_items()

        title = "Quest Complete!" if success else "Quest Failed!"
        color = discord.Color.gold() if success else discord.Color.red()
        embed = discord.Embed(title=title, color=color)

        total_success_rate = 0
        event_count = len(self.event_log)

        for i, event in enumerate(self.event_log):
            success_str = "Success" if event['success'] else "Failure"
            embed.add_field(
                name=f"Stage {i+1}: {event['event']}",
                value=f"**Choice:** {event['choice']}\n"
                      f"**Success Rate:** {event['success_rate']}%\n"
                      f"**Outcome:** {success_str}",
                inline=False
            )
            total_success_rate += event['success_rate']

        loot_str = ", ".join([f'{item.get("count", 1)} {emoji_manager.mention(item["name"]) or ""}{item["name"]}' for item in self.loot]) if self.loot else "None"

        # Compute level-scaled XP now so the embed shows the correct value
        if success and self.xp > 0:
            pet_level = self.pet.get("level", 1)
            level_multiplier = 1.0 + (pet_level - 1) * 0.1
            display_xp = int(self.xp * level_multiplier)
            xp_label = f"**Total XP:** {display_xp}" + (f" *(Lv.{pet_level} bonus)*" if pet_level > 1 else "")
        else:
            display_xp = self.xp
            xp_label = f"**Total XP:** {display_xp}"

        summary_value = xp_label + "\n"
        if success:
             summary_value += f"**Loot:** {loot_str}\n"
        elif self.current_stage_index >= 3 and self.loot:
            summary_value += f"**Loot Kept:** {loot_str}\n"
        else:
            summary_value += f"**Loot:** None\n"

        if event_count > 0:
            quest_success_rate = total_success_rate / event_count
            summary_value += f"**Final Quest Success Rate:** {quest_success_rate:.2f}%"
        
        if summary_value:
            embed.add_field(
                name="Quest Summary",
                value=summary_value,
                inline=False
            )

        if not self.event_log and not self.loot and self.xp == 0:
            embed.description = "The quest ended without any significant events."
            embed.clear_fields()

        if success:
            if display_xp > 0:
                await LootCalculator.apply_xp_change(int(self.user_id), display_xp, "quest")
            if self.loot:
                for item in self.loot:
                    await LootCalculator.add_item_to_inventory(self.user_id, item, self.pet)
        elif self.current_stage_index >= 3 and self.loot:
            for item in self.loot:
                await LootCalculator.add_item_to_inventory(self.user_id, item, self.pet)

        await self.interaction.followup.send(embed=embed)

class ChoiceButton(discord.ui.Button):
    def __init__(self, quest_view, choice_num, label):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.quest_view = quest_view
        self.choice_num = choice_num

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.view.clear_items()
        # We need to edit the original message to remove the buttons
        await interaction.message.edit(view=self.view)
        await self.quest_view.handle_choice(self.choice_num)


