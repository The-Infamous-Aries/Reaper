import os
import random
import json
import logging
import discord
from typing import Dict, Any, Tuple, List, Optional, Union, cast
from datetime import datetime
from Systems.Functions.user_data_manager import user_data_manager
from Systems.Functions import emoji as emoji_mod

logger = logging.getLogger('pet_brain')

class LootCalculator:

    @staticmethod
    def group_inventory_items(inventory: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, int]], Dict[str, Dict[str, Any]]]:
        """
        Group inventory items by category and name.
        Returns (item_counts, item_data)
        """
        from collections import Counter
        item_counts: Dict[str, Dict[str, int]] = {} # type -> name -> count
        item_data: Dict[str, Dict[str, Any]] = {} # type -> name -> item_obj
        
        for item in inventory:
            itype = item.get('type', 'Material') # Default to Material if unknown
            name = item.get('name', 'Unknown')
            count = item.get('count', 1)
            
            # Map type to our categories
            cat_key = itype
            if "Gem" in itype: cat_key = "Gem"
            elif "Monster" in itype: cat_key = "Monster"
            elif "Material" in itype: cat_key = "Material"
            elif "Potion" in itype: cat_key = "Potion"
            elif "Hat" in itype: cat_key = "Hat"
            elif "Key" in itype: cat_key = "Key"
            elif "Chest" in itype: cat_key = "Chest"
            else: cat_key = itype # Fallback
            
            if cat_key not in item_counts: item_counts[cat_key] = Counter()
            if cat_key not in item_data: item_data[cat_key] = {}
            
            item_counts[cat_key][name] += count
            if name not in item_data[cat_key]:
                item_data[cat_key][name] = item

        return item_counts, item_data



    @staticmethod
    def _get_item_from_inventory(pet: Dict[str, Any], item_name: str, item_type: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves an item from the pet's inventory.
        Does NOT remove it.
        """
        inventory = pet.get("inventory", [])
        for item in inventory:
            if item.get("name") == item_name and item.get("type") == item_type:
                return item
        return None

    @staticmethod
    def _remove_item_from_inventory(pet: Dict[str, Any], item: Dict[str, Any], count: int = 1) -> Tuple[bool, str]:
        """
        Removes an item (or a specified count of it) from the pet's inventory.
        Updates the pet's inventory in place.
        """
        inventory = pet.get("inventory", [])
        item_name = item.get("name")
        item_type = item.get("type")

        # Find the item in the inventory
        found_item = None
        for i, inv_item in enumerate(inventory):
            if inv_item.get("name") == item_name and inv_item.get("type") == item_type:
                found_item = inv_item
                break

        if not found_item:
            return False, f"{item_name} not found in inventory."

        current_count = found_item.get("count", 1)
        if current_count < count:
            return False, f"Not enough {item_name} to remove. Have {current_count}, need {count}."

        if current_count == count:
            # Remove the item entirely
            inventory.remove(found_item)
        else:
            # Decrement count
            found_item["count"] = current_count - count
        
        pet["inventory"] = inventory # Update pet's inventory in place
        return True, f"Removed {count} x {item_name} from inventory."




    # --- EMOJI HELPERS ---
    @staticmethod
    def get_pet_emoji(category: str, key: Union[str, int]) -> str:
        target_key = str(key)
        cat_map = {
            "Elements": "Elements",
            "Category": "Pet Type",
            "Pet Type": "Pet Type",
            "Pets": "Pets",
            "Species": "Pets",
            "Stats": "Stats",
            "Pet Level": "Pet Level",
            "Pet Helpers": "Pet Helpers",
            "Material": "Materials",
            "Hat": "Hats",
            "Gem": "Gems",
            "Monster": "Monsters"
        }
        real_category = cat_map.get(category, category)

        if real_category == "Pet Level":
            try:
                lvl = int(key)
            except Exception:
                lvl = 1
            if lvl > 500:
                 target_key = "P26"
            else:
                bucket = ((max(1, lvl) - 1) // 20) + 1
                bucket = min(bucket, 25)
                target_key = f"P{bucket}"

        target_lower = target_key.lower()
        if real_category in emoji_mod.CATEGORIES:
            for name in emoji_mod.CATEGORIES[real_category]:
                if name.lower() == target_lower:
                    return emoji_mod.mention(name) or ""

        return emoji_mod.mention(target_key) or ""

    @staticmethod
    def get_pet_stat_emojis() -> Dict[str, str]:
        stats = ["ATT", "DEF", "INT", "DEX", "HAP", "ENE"]
        return {s: LootCalculator.get_pet_emoji("Stats", s) or "" for s in stats}

    @staticmethod
    def get_pet_source_emojis() -> Dict[str, str]:
        return {
            "battle": LootCalculator.get_pet_emoji("Pet Helpers", "ring") or "",
            "train": LootCalculator.get_pet_emoji("Pet Helpers", "Train") or "",
            "training": LootCalculator.get_pet_emoji("Pet Helpers", "Train") or "",
            "mission": LootCalculator.get_pet_emoji("Pet Helpers", "Mission") or "",
            "quest": LootCalculator.get_pet_emoji("Pet Helpers", "Quest") or "",
            "search": LootCalculator.get_pet_emoji("Pet Helpers", "Search") or "",
            "levelup": LootCalculator.get_pet_emoji("Pet Helpers", "LevelUp") or "",
            "downgrade": LootCalculator.get_pet_emoji("Pet Helpers", "Downgrade") or "",
            "xp": LootCalculator.get_pet_emoji("Pet Helpers", "XP") or "",
            "npc": LootCalculator.get_pet_emoji("Pet Helpers", "NPC") or "",
            "pvp": LootCalculator.get_pet_emoji("Pet Helpers", "PvP") or "",
            "series": LootCalculator.get_pet_emoji("Pet Helpers", "Series") or "",
            "tournament": LootCalculator.get_pet_emoji("Pet Helpers", "Tournament") or "",
            "gamble": LootCalculator.get_pet_emoji("Gambling", "Casino") or ""
        }

    # --- XP LOGIC ---
    @staticmethod
    def get_level_experience(level: int) -> int:
        """
        Calculate XP needed to pass current level (reach level+1).
        Level 1 needs 200 XP to reach Level 2.
        Then 3% exponential growth.
        Formula: 200 * (1.03 ^ (level - 1))
        """
        if level < 1: level = 1
        return int(200 * (1.03 ** (level - 1)))

    @staticmethod
    def get_total_experience_for_level(level: int) -> int:
        """
        Calculate total cumulative XP required to reach a specific level from level 1.
        Sum of get_level_experience for all levels below target level.
        Geometric Series Sum: 200 * (1 - 1.03^(level-1)) / (1 - 1.03)
        """
        if level <= 1: return 0

        n = level - 1
        return int(200 * (1 - 1.03**n) / (1 - 1.03))

    @staticmethod
    def get_next_level_xp(level: int) -> int:
        """XP needed to finish current level"""
        return LootCalculator.get_level_experience(level)

    @staticmethod
    def recompute_level_from_total_xp(pet_data: dict, total_xp: int) -> Tuple[int, int, int]:
        level = 1
        while True:
            needed = LootCalculator.get_total_experience_for_level(level + 1)
            if total_xp < needed:
                break
            level += 1
        
        current_level_base = LootCalculator.get_total_experience_for_level(level)
        xp_into_level = total_xp - current_level_base
        
        return total_xp, level, xp_into_level

    # --- XP GAIN CALCULATIONS ---
    @staticmethod
    def calculate_xp_gain(winner_level: int, loser_level: int) -> int:
        """PvP / Battle XP Calculation based on level difference"""
        diff = loser_level - winner_level
        base_xp = 50
        
        if diff >= 5: multiplier = 1.5
        elif diff >= 2: multiplier = 1.2
        elif diff >= -2: multiplier = 1.0
        elif diff >= -5: multiplier = 0.8
        else: multiplier = 0.5
            
        return int(base_xp * multiplier)

    @staticmethod
    def calculate_pve_xp_gain(level: int, difficulty: str = "normal", source: str = "battle") -> int:
        """PvE / Mission XP Calculation"""
        base_xp = 50
        if level <= 50: base_xp = 25
        elif level <= 100: base_xp = 35
        elif level <= 200: base_xp = 50
        elif level <= 300: base_xp = 75
        elif level <= 400: base_xp = 100
        else: base_xp = 150
        
        difficulty_multipliers = {"easy": 0.7, "normal": 1.0, "average": 1.0, "medium": 1.0, "hard": 1.5, "extreme": 2.0}
        multiplier = difficulty_multipliers.get(difficulty.lower(), 1.0)
        source_bonuses = {"battle": 1.0, "mission": 1.2, "train": 0.8, "quest": 1.5, "pvp": 1.3}
        source_multiplier = source_bonuses.get(source.lower(), 1.0)
        variation = random.uniform(0.8, 1.2)
        final_xp = int(base_xp * multiplier * source_multiplier * variation)
        return max(1, final_xp)

    @staticmethod
    def calculate_mission_xp(level: int, difficulty: str = "easy") -> int:
        """Calculate mission XP based on level and difficulty"""
        return LootCalculator.calculate_pve_xp_gain(level, difficulty, "mission")

    @staticmethod
    def calculate_training_xp(level: int, difficulty: str = "easy") -> int:
        """Calculate training XP based on level and difficulty"""
        return LootCalculator.calculate_pve_xp_gain(level, difficulty, "training")

    @staticmethod
    def get_mission_success_chance(difficulty: str) -> float:
        """Get mission success chance based on difficulty"""
        diff = difficulty.lower()
        if diff == "easy": return 0.90
        if diff == "medium": return 0.70
        if diff == "hard": return 0.50
        if diff == "insane": return 0.30
        if diff == "extreme": return 0.30
        return 0.90

    @staticmethod
    def get_mission_gamble_multiplier(difficulty: str) -> float:
        """Get mission gamble multiplier based on difficulty"""
        diff = difficulty.lower()
        if diff == "easy": return 1.5
        if diff == "medium": return 2.0
        if diff == "hard": return 3.0
        if diff == "insane": return 5.0
        return 1.5

    @staticmethod
    def calculate_pvp_xp(damage_dealt: int, damage_taken: int, is_winner: bool) -> int:
        """Calculate PvP XP based on damage dealt and taken"""
        if is_winner:
            return max(0, int(damage_dealt / 10 + damage_taken / 5))
        else:
            return max(0, int(damage_dealt / 15 + damage_taken / 10))

    @staticmethod
    def calculate_ss_xp(level: int, kills: int) -> int:
        """Calculate Survivor Series XP based on level and kills"""
        return max(0, int(50 * level * kills))

    @staticmethod
    def calculate_play_loot(pet_element: str, pet_element2: str, place_specials: Dict[str, Any]) -> Tuple[int, List[str]]:
        xp_multiplier = 1
        keys_to_award_names = ["Key1"]

        if pet_element == "basic":
            xp_multiplier = 1
            keys_to_award_names = ["Key1", "Key2", "Key3"]
        else:
            matched_elements_in_specials = []
            if pet_element in place_specials:
                matched_elements_in_specials.append(pet_element)
            if pet_element2 and pet_element2 in place_specials:
                matched_elements_in_specials.append(pet_element2)

            if len(matched_elements_in_specials) == 2:
                xp_multiplier = 3
                keys_to_award_names = ["Key3"]
            elif len(matched_elements_in_specials) == 1:
                xp_multiplier = 2
                keys_to_award_names = ["Key2"]
            else:
                xp_multiplier = 1
                keys_to_award_names = ["Key1"]

        return xp_multiplier, keys_to_award_names

    @staticmethod
    def get_play_outcome_message(
        pet_element: str,
        pet_element2: str,
        outcome_data: Dict[str, Any],
        chosen_place: str,
        pet_name: str,
        pet_emoji: str,
        place_emoji: str,
        element1_emoji: str,
        element2_emoji: str
    ) -> str:
        place_specials = outcome_data.get("Special", {})
        final_outcome_message = ""

        if pet_element == "basic":
            basic_outcomes = outcome_data.get("Basic", ["Your basic pet had a simple but fun time at the {place}!"])
            final_outcome_message = random.choice(basic_outcomes).format(place=chosen_place)
        else:
            matched_elements_in_specials = []
            if pet_element in place_specials:
                matched_elements_in_specials.append(pet_element)
            if pet_element2 and pet_element2 in place_specials:
                matched_elements_in_specials.append(pet_element2)

            if len(matched_elements_in_specials) == 2:
                element1_outcome_msg = random.choice(place_specials[matched_elements_in_specials[0]])
                element2_outcome_msg = random.choice(place_specials[matched_elements_in_specials[1]])
                final_outcome_message = f"You and {pet_emoji} **{pet_name}** played at {place_emoji} **{chosen_place}**, {pet_name} {element1_emoji} {element1_outcome_msg.format(place=chosen_place)} & {element2_emoji} {element2_outcome_msg.format(place=chosen_place)}"
            else:
                # Use the helper for the first element
                msg1 = LootCalculator._get_element_message(pet_element.capitalize(), outcome_data, chosen_place)
                
                if pet_element2:
                    # Use the helper for the second element if it exists
                    msg2 = LootCalculator._get_element_message(pet_element2.capitalize(), outcome_data, chosen_place)
                    final_outcome_message = f"You and {pet_emoji} **{pet_name}** played at {place_emoji} **{chosen_place}**, {pet_name} {element1_emoji} {msg1.format(place=chosen_place)} & {element2_emoji} {msg2.format(place=chosen_place)}"
                else:
                    # Single element pet
                    final_outcome_message = f"You and {pet_emoji} **{pet_name}** played at {place_emoji} **{chosen_place}**, {pet_name} {element1_emoji} {msg1.format(place=chosen_place)}"
        return final_outcome_message

    @staticmethod
    def _get_element_message(element: str, outcome_data: Dict[str, Any], chosen_place: str) -> str:
        if element in outcome_data.get("Special", {}):
            return random.choice(outcome_data["Special"][element])
        elif element in outcome_data.get("Regular", {}):
            return random.choice(outcome_data["Regular"][element])
        else:
            return random.choice(outcome_data.get("Basic", ["Your basic pet had a simple but fun time at the {place}!"]))

    # --- EMBEDS ---
    @staticmethod
    def _format_stat_block(pet: Dict[str, Any]) -> str:
        stats_emojis = LootCalculator.get_pet_stat_emojis()
        stats = {
            'ATT': pet.get('ATT', 0),
            'DEF': pet.get('DEF', 0),
            'INT': pet.get('INT', 0),
            'DEX': pet.get('DEX', 0),
            'HAP': pet.get('HAP', 0),
            'ENE': pet.get('ENE', 0)
        }
        return " | ".join([f"{stats_emojis.get(k, '')} **{k}**: {v}" for k, v in stats.items()])

    @staticmethod
    async def create_level_up_embed(pet_data: dict, old_level: int, new_level: int, source: str = "battle") -> discord.Embed:
        name = pet_data.get('name', 'Pet')
        src_emojis = LootCalculator.get_pet_source_emojis()
        src_emoji = src_emojis.get(source, "")
        
        embed = discord.Embed(
            title=f"{src_emoji} LEVEL UP! {src_emoji}".strip(),
            description=f"**{name}** has reached **Level {new_level}**!",
            color=0xFFD700
        )
        
        levels_gained = new_level - old_level
        if levels_gained > 1:
            embed.description = f"**{name}** has gained {levels_gained} levels, reaching **Level {new_level}**!"
            embed.add_field(name="Level Progress", value=f"Level {old_level} ➡️ Level {new_level} (x{levels_gained})", inline=False)
        else:
            embed.add_field(name="Level Progress", value=f"Level {old_level} ➡️ Level {new_level}", inline=False)
        
        stats = LootCalculator._format_stat_block(pet_data)
        embed.add_field(name="Current Stats", value=stats, inline=False)
        
        if source == "battle": embed.set_footer(text="Growing stronger through combat!")
        elif source == "mission": embed.set_footer(text="Experience gained from missions!")
        elif source == "play": embed.set_footer(text="Gaining experience through playful activities!")
        else: embed.set_footer(text="New power unlocked!")
            
        return embed

    @staticmethod
    async def create_level_down_embed(pet_data: dict, old_level: int, new_level: int, source: str = "mission", lost_xp: int = 0) -> discord.Embed:
        name = pet_data.get('name', 'Pet')
        src_emojis = LootCalculator.get_pet_source_emojis()
        src_emoji = src_emojis.get(source, "")

        embed = discord.Embed(
            title=f"{src_emoji} LEVEL DOWN {src_emoji}".strip(),
            description=f"**{name}** has fallen to **Level {new_level}**...",
            color=0xFF0000
        )
        
        embed.add_field(name="Level Change", value=f"Level {old_level} ➡️ Level {new_level}", inline=False)

        if lost_xp > 0:
            embed.add_field(name="XP Lost", value=f"-{lost_xp:,} XP", inline=False)
            
        stats = LootCalculator._format_stat_block(pet_data)
        embed.add_field(name="Current Stats", value=stats, inline=False)
        
        if source == "mission": embed.set_footer(text="The mission was too dangerous...")
        elif source == "gamble": embed.set_footer(text="Fortune was not on your side...")
            
        return embed

    # --- LOOT LOGIC ---
    @staticmethod
    def _get_equipment_data() -> Dict[str, Any]:
        try:
            return user_data_manager.file_manager.get_data("equipment")
        except Exception as e:
            logger.error(f"Failed to load equipment data via OptimalFileManager: {e}")
            return {}

    @staticmethod
    def _format_item_stats(item: Dict[str, Any]) -> str:
        stats = []
        
        # 1. Equipment Bonuses
        bonuses = item.get("bonuses", {})
        if bonuses:
            for k, v in bonuses.items():
                stats.append(f"{k}: {v}")
        
        # 2. Potion Effects
        effect = item.get("use_effect")
        if effect:
            etype = effect.get("type")
            if etype == "elemental_boost":
                e = effect.get("element", "Unknown")
                v_s = effect.get("value_single", 5)
                v_d = effect.get("value_dual", 3)
                stats.append(f"Boosts {e} (Single: +{v_s}, Dual: +{v_d})")
            elif etype == "attribute_boost":
                attr = effect.get("attribute", "Stats")
                val = effect.get("value", 3)
                stats.append(f"+{val} {attr}")
            elif etype == "random_boost":
                cnt = effect.get("count", 2)
                val = effect.get("value", 1)
                stats.append(f"+{val} to {cnt} Random Stats")
            elif etype == "luck_boost":
                mn = effect.get("min", 1)
                mx = effect.get("max", 5)
                stats.append(f"+{mn}-{mx} All Stats")
            elif etype == "mega_boost":
                val = effect.get("value", 10)
                stats.append(f"+{val} All Stats")
            elif etype == "health_boost":
                val = effect.get("value", 5)
                attrs = effect.get("attributes", ["HAP", "ENE"])
                stats.append(f"+{val} {', '.join(attrs)}")
            elif etype == "xp_boost":
                mul = effect.get("multiplier", 50)
                stats.append(f"Grants {mul}x Level XP")
        
        if not stats:
            return ""
            
        return f" ({', '.join(stats)})"

    @staticmethod
    def _get_pet_specs(pet_data: Dict[str, Any]) -> List[str]:
        """Helper to safely get pet specializations"""
        specs = pet_data.get("specializations", [])
        if not specs:
            specs = pet_data.get("specs", [])
        return specs if isinstance(specs, list) else []

    @staticmethod
    async def add_item_to_inventory(user_id: int, item: Dict[str, Any], pet_data: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        """
        Adds item to inventory respecting limits.
        Returns (added_bool, message).
        Limits:
        - Potions: 16 per individual potion
        - Everything else: 5 per individual item
        Fallback: Current Level * 100 XP.
        """
        try:
            if not pet_data:
                pet_data = await user_data_manager.get_pet_data_async(str(user_id))
            if not pet_data:
                return False, ""
            assert pet_data is not None # Ensure pet_data is not None for mypy

            inventory = pet_data.get("inventory", [])
            # Ensure inventory is clean/consolidated first
            inventory = user_data_manager._consolidate_inventory(inventory)
            
            item_type = item.get("type", "Unknown")
            item_name = item.get("name", "Unknown")
            
            # Determine limit based on type
            limit = 5 # Default limit for individual items
            if item_type == "Potion":
                limit = 16
            elif item_type == "Key":
                limit = 99
                
            # Find existing item
            existing_item = None
            for inv_item in inventory:
                if inv_item.get("name") == item_name and inv_item.get("type") == item_type:
                    existing_item = inv_item
                    break
            
            current_count = existing_item.get("count", 0) if existing_item else 0
            count_to_add = item.get("count", 1)
            
            available_space = max(0, limit - current_count)
            amount_added = 0
            xp_gain = 0
            
            # 1. Fill available space
            if available_space > 0:
                amount_added = min(count_to_add, available_space)
                if existing_item:
                    existing_item["count"] = current_count + amount_added
                else:
                    item_instance = item.copy()
                    item_instance["acquired_at"] = datetime.utcnow().isoformat()
                    item_instance["count"] = amount_added
                    inventory.append(item_instance)
            
            # 2. Convert excess to XP
            excess = count_to_add - amount_added
            if excess > 0:
                level = int(pet_data.get("level", 1))
                xp_gain = level * 100 * excess
                
                # Use centralized XP change logic
                _, change_data = await LootCalculator.apply_xp_change(user_id, xp_gain, "excess_item_conversion")
                
                # The above call saves the data, so we don't need to save again here.
                # However, we need to ensure the local pet_data reflects the changes if we continue using it.
                if change_data:
                    pet_data["level"] = change_data["new_level"]
                    pet_data["experience"] = pet_data.get("experience", 0) # apply_xp_change updated the DB, but we should update our local ref if needed
            
            # We don't need to call save_pet_data again if XP was added, as apply_xp_change handles it.
            # But if NO xp was added (amount_added > 0 but excess == 0), we DO need to save the inventory.
            if excess <= 0:
                pet_data["inventory"] = inventory
                await user_data_manager.save_pet_data(str(user_id), pet_data.get("name", "Pet"), pet_data)
            
            emoji = LootCalculator.get_pet_emoji(item_type, item_name)
            stats_str = LootCalculator._format_item_stats(item)
            
            msg = ""
            if amount_added > 0:
                msg += f"\n🎁 Looted {emoji} **{item_name}** x{amount_added}{stats_str}!"
            if excess > 0:
                msg += f"\n⚠️ Max capacity ({limit}) reached! {excess} converted to {xp_gain} XP."
                
            return True, msg
            
        except Exception as e:
            logger.error(f"Failed to add item to inventory: {e}")
            return False, ""

    @staticmethod
    async def use_potion(user_id: int, potion_name: str) -> Tuple[bool, str]:
        """
        Uses a potion from inventory and applies its permanent effects.
        """
        try:
            pet = await user_data_manager.get_pet_data_async(str(user_id))
            if not pet:
                return False, "You don't have a pet!"
            assert pet is not None # mypy: pet is now Dict[str, Any]
            
            inventory = pet.get("inventory", [])
            # Consolidate inventory
            inventory = user_data_manager.UserDataManager._consolidate_inventory(inventory)
            
            # Find potion
            potion_idx = -1
            potion_item = None
            for i, item in enumerate(inventory):
                if item.get("name") == potion_name and item.get("type") == "Potion":
                    potion_idx = i
                    potion_item = item
                    break
            
            if potion_idx == -1 or potion_item is None:
                return False, f"You don't have any {potion_name}!"
            
            effect = potion_item.get("use_effect")
            if not effect:
                # Fallback: Try to find in equipment.json
                eq_data = LootCalculator._get_equipment_data()
                potions = eq_data.get("Potions", [])
                for p in potions:
                    if p["name"] == potion_name:
                        effect = p.get("use_effect")
                        break
            
            if not effect:
                return False, "This potion has no effect!"

            # Apply Logic
            stats = ["ATT", "DEF", "INT", "DEX", "HAP", "ENE"]
            changes = []
            
            etype = effect.get("type")
            
            if etype == "elemental_boost":
                req_element = effect.get("element")
                pet_elements = [pet.get("element")]
                if pet.get("element2"): pet_elements.append(pet.get("element2"))
                
                # Check match (case insensitive)
                matches = [e for e in pet_elements if str(e).lower() == str(req_element).lower()]
                if not matches:
                    return False, f"Only {req_element} pets can use this potion!"
                
                is_dual = bool(pet.get("element2"))
                
                if is_dual:
                    # 4 stats by 3
                    targets = random.sample(stats, 4)
                    val = effect.get("value_dual", 3)
                else:
                    # 3 stats by 5
                    targets = random.sample(stats, 3)
                    val = effect.get("value_single", 5)
                
                for stat in targets:
                    pet[stat] = int(pet.get(stat, 0)) + val
                    changes.append(f"+{val} {stat}")

            elif etype == "attribute_boost":
                target = effect.get("attribute")
                val = effect.get("value", 3)
                if target in stats:
                    pet[target] = int(pet.get(target, 0)) + val
                    changes.append(f"+{val} {target}")
            
            elif etype == "random_boost":
                count = effect.get("count", 2)
                val = effect.get("value", 1)
                targets = random.sample(stats, min(count, len(stats)))
                for stat in targets:
                    pet[stat] = int(pet.get(stat, 0)) + val
                    changes.append(f"+{val} {stat}")
            
            elif etype == "luck_boost":
                min_v = effect.get("min", 1)
                max_v = effect.get("max", 5)
                for stat in stats:
                    roll = random.randint(min_v, max_v)
                    pet[stat] = int(pet.get(stat, 0)) + roll
                    changes.append(f"+{roll} {stat}")

            elif etype == "mega_boost":
                val = effect.get("value", 10)
                for stat in stats:
                    pet[stat] = int(pet.get(stat, 0)) + val
                    changes.append(f"+{val} {stat}")

            elif etype == "health_boost":
                val = effect.get("value", 5)
                target_stats = effect.get("attributes", ["HAP", "ENE"])
                for stat in target_stats:
                    if stat in stats:
                        pet[stat] = int(pet.get(stat, 0)) + val
                        changes.append(f"+{val} {stat}")

            elif etype == "xp_boost":
                multiplier = effect.get("multiplier", 50)
                try:
                    level = int(pet.get("level", 1))
                    xp_gain = multiplier * level
                    
                    # Use centralized XP change logic
                    leveled_up, change_data = await LootCalculator.apply_xp_change(user_id, xp_gain, "potion_boost")
                    
                    changes.append(f"+{xp_gain} XP")
                    if leveled_up and change_data:
                         new_level = change_data.get("new_level")
                         changes.append(f"**LEVEL UP!** {level} -> {new_level}")
                         # apply_xp_change already handled stat gains and saving
                         for k, v in change_data.get("gains", {}).items():
                             if v > 0:
                                 changes.append(f"+{v} {k}")

                except Exception as e:
                    logger.error(f"Error calculating XP boost: {e}")
                    changes.append("Error adding XP")
            
            else:
                return False, "Unknown potion effect."

            # Remove potion (decrement count)
            count = potion_item.get("count", 1)
            if count > 1:
                potion_item["count"] = count - 1
            else:
                inventory.pop(potion_idx)
                
            pet["inventory"] = inventory
            
            await user_data_manager.save_pet_data(str(user_id), pet.get("name", "Pet"), pet)
            
            return True, f"🧪 Used **{potion_name}**! Gains: {', '.join(changes)}"
            
        except Exception as e:
            logger.error(f"Error using potion: {e}")
            return False, "An error occurred while using the potion."

    @staticmethod
    def get_material_loot_item(difficulty: str = "normal", level: int = 1, bypass_chance: bool = False) -> Optional[Dict[str, Any]]:
        # Check 1: Rare chance to find ANY material at all
        # "Materials being pulled at all is Rare" -> Let's say 20% base chance, scaling slightly with difficulty?
        # Or fixed 20%? User said "is Rare", usually means ~20-25%.
        material_chance = 0.20
        diff = difficulty.lower()
        if diff == "medium": material_chance = 0.25
        elif diff == "hard": material_chance = 0.30
        
        if not bypass_chance and random.random() > material_chance:
            return None
            
        # Check 2: Rarity Roll for the specific material
        # Common: 45%, Uncommon: 25%, Rare: 15%, Epic: 10%, Mythic: 5%
        roll = random.random()
        target_rarity = "Common"
        
        # Cumulative probabilities
        if roll > 0.95: target_rarity = "Mythic"      # Top 5%
        elif roll > 0.85: target_rarity = "Epic"      # Next 10% (85-95)
        elif roll > 0.70: target_rarity = "Rare"      # Next 15% (70-85)
        elif roll > 0.45: target_rarity = "Uncommon"  # Next 25% (45-70)
        else: target_rarity = "Common"                # Bottom 45%
        
        data = LootCalculator._get_equipment_data()
        materials = data.get("Materials", [])
        if not materials:
            return None
            
        # Filter by target rarity
        potential_items = [m for m in materials if m.get("rarity") == target_rarity]
        
        # Fallback if no items of that rarity exist (shouldn't happen with correct json)
        if not potential_items:
            # Fallback to lower rarities
            if target_rarity == "Mythic": potential_items = [m for m in materials if m.get("rarity") == "Epic"]
            if not potential_items and target_rarity in ["Mythic", "Epic"]: potential_items = [m for m in materials if m.get("rarity") == "Rare"]
            if not potential_items: potential_items = [m for m in materials if m.get("rarity") == "Common"]
            
        if not potential_items:
            return random.choice(materials) # Absolute fallback
            
        return random.choice(potential_items)



    @staticmethod
    def get_gem_loot_item(difficulty: str = "normal", bypass_chance: bool = False) -> Optional[Dict[str, Any]]:
        # Chance: 25% Normal, 35% Medium, 50% Hard
        chance = 0.25
        diff = difficulty.lower()
        if diff == "medium": chance = 0.35
        elif diff == "hard": chance = 0.50
        elif diff in ["very_hard", "insanity", "extreme"]: chance = 0.65
        
        if not bypass_chance and random.random() > chance:
            return None
            
        data = LootCalculator._get_equipment_data()
        gems = data.get("Gems", [])
        if not gems:
            return None
            
        # Rarity weights: Common 45%, Uncommon 25%, Rare 15%, Epic 10%, Mythic 5%
        weighted_items = []
        weights = []
        for item in gems:
            rarity = item.get("rarity", "Common")
            w = 45
            if rarity == "Uncommon": w = 25
            elif rarity == "Rare": w = 15
            elif rarity == "Epic": w = 10
            elif rarity == "Mythic": w = 5
            weighted_items.append(item)
            weights.append(w)
            
        if not weighted_items:
            return random.choice(gems)
            
        return random.choices(weighted_items, weights=weights, k=1)[0]



    @staticmethod
    async def process_gem_loot(user_id: int, pet_data: Dict[str, Any], difficulty: str = "normal") -> str:
        """Wrapper that gets a gem and adds it to inventory"""
        gem = LootCalculator.get_gem_loot_item(difficulty)
        if not gem:
            return ""
            
        added, msg = await LootCalculator.add_item_to_inventory(user_id, gem, pet_data)
        return msg

    @staticmethod
    async def award_gambling_loot(user_id: int, pet_data: Dict[str, Any], difficulty: str = "normal", win_streak: int = 0, source: str = "gamble") -> List[str]:
        """
        Awards loot for gambling wins.
        - Keys: 
            - If Slots: Chance based on difficulty
            - If other: Chance based on Win Streak (3+, 5+)
        Returns list of messages.
        """
        messages: List[str] = []
        
        # Key Loot (ONLY Loot for Gambling now)
        items_to_add: List[Dict[str, Any]] = []
        diff = difficulty.lower()
        
        if source == "slots":
            # Slots: Difficulty based
            key_chance = 0.0
            if diff == "medium": key_chance = 0.05
            elif diff == "hard": key_chance = 0.10
            elif diff in ["very_hard", "insanity", "extreme"]: key_chance = 0.20
            
            if key_chance > 0 and random.random() < key_chance:
                k = LootCalculator.get_key_loot(difficulty)
                if k: items_to_add.extend(k)
        else:
            # Table Games: Deterministic Streak Logic
            if win_streak == 1:
                items_to_add.append({"name": "Key1", "type": "Key", "rarity": "Common"})
            elif win_streak == 2:
                items_to_add.extend([{"name": "Key1", "type": "Key", "rarity": "Common"}] * 2)
            elif win_streak == 3:
                items_to_add.append({"name": "Key2", "type": "Key", "rarity": "Uncommon"})
            elif win_streak == 4:
                items_to_add.extend([{"name": "Key2", "type": "Key", "rarity": "Uncommon"}] * 2)
            elif win_streak == 5:
                items_to_add.append({"name": "Key3", "type": "Key", "rarity": "Rare"})
            elif win_streak == 6:
                items_to_add.extend([{"name": "Key3", "type": "Key", "rarity": "Rare"}] * 2)
            elif win_streak >= 7:
                messages.append("🔥 **7+ WIN STREAK! JACKPOT!** 🔥")
                items_to_add.extend([{"name": "Key1", "type": "Key", "rarity": "Common"}] * 3)
                items_to_add.extend([{"name": "Key2", "type": "Key", "rarity": "Uncommon"}] * 3)
                items_to_add.extend([{"name": "Key3", "type": "Key", "rarity": "Rare"}] * 3)
            
        for item in items_to_add:
            added, msg = await LootCalculator.add_item_to_inventory(user_id, item, pet_data)
            if msg: messages.append(msg)

        return messages



    @staticmethod
    def _return_item_to_inventory(inventory: List[Dict[str, Any]], item: Dict[str, Any], pet_data: Dict[str, Any], user_id: int) -> Tuple[bool, str]:
        """
        Helper to return an item to inventory, handling stacking, limits, and XP conversion.
        """
        if not item: return False, ""
        
        item_type = item.get("type", "Material")
        item_name = item.get("name", "Unknown")
        limit = 5
        if item_type == "Potion": limit = 16
        elif item_type == "Key": limit = 99
        
        # Find existing item
        existing_item = None
        for inv_item in inventory:
            if inv_item.get("name") == item_name and inv_item.get("type") == item_type:
                existing_item = inv_item
                break
        
        current_count = existing_item.get("count", 0) if existing_item else 0
        
        # Check limit
        if current_count >= limit:
            # Convert to XP
            level = int(pet_data.get("level", 1))
            xp_gain = level * 100
            
            current_xp = int(pet_data.get("experience", 0))
            total_xp_for_level = LootCalculator.get_total_experience_for_level(level)
            current_total_xp = total_xp_for_level + current_xp
            new_total_xp = current_total_xp + xp_gain
            
            _, new_level, new_xp = LootCalculator.recompute_level_from_total_xp(pet_data, new_total_xp)
            
            pet_data["level"] = new_level
            pet_data["experience"] = new_xp
            
            return True, f"⚠️ Limit reached for {item_name}! Converted to {xp_gain} XP."
            
        else:
            # Add to inventory
            if existing_item:
                existing_item["count"] = current_count + 1
            else:
                new_item = item.copy()
                new_item["count"] = 1
                inventory.append(new_item)
            return True, ""

    @staticmethod
    def _manage_equipment_slot(pet: Dict, slot_name: str, item_obj: Dict, max_slots: int) -> Optional[Dict]:
        """
        Manages adding an item to an equipment slot that supports multiple items.
        Returns the item that was replaced (if any), which needs to be unequipped.
        """
        equipped_items = pet["equipment"].get(slot_name, [])
        if not isinstance(equipped_items, list):
            # If it's a single item (legacy data), convert to list
            equipped_items = [equipped_items] if equipped_items else []

        unequipped_item = None
        if len(equipped_items) >= max_slots:
            # If max slots reached, replace the oldest item (first in list)
            unequipped_item = equipped_items.pop(0)
            
        equipped_items.append(item_obj)
        pet["equipment"][slot_name] = equipped_items
        return unequipped_item

    @staticmethod
    async def equip_items(user_id: str, username: str, material_name: Optional[str] = None, gem_names: Optional[str] = None, monster_names: Optional[str] = None, hat_name: Optional[str] = None) -> Tuple[bool, str]:
        """Equip items to the user's pet, handling inventory moves and limits."""
        try:
            pet = await user_data_manager.get_pet_data_async(str(user_id))
            if not pet:
                return False, "You don't have a pet!"
            
            inventory = pet.get('inventory', [])
            # Consolidate inventory
            inventory = user_data_manager.UserDataManager._consolidate_inventory(inventory)
            
            equipment = pet.setdefault('equipment', {})
            # Ensure multi-slot equipment types are initialized as lists
            equipment.setdefault("Material", [])
            equipment.setdefault("Gems", [])
            equipment.setdefault("Monsters", [])
            
            msg_parts = []
            


            # 1. Material
            if material_name:
                item_obj = LootCalculator._get_item_from_inventory(pet, material_name, "Material")
                if not item_obj:
                    msg_parts.append(f"❌ Material **{material_name}** not found in inventory.")
                else:
                    unequipped_material = LootCalculator._manage_equipment_slot(pet, "Material", item_obj, max_slots=2)
                    if unequipped_material:
                        success, msg = LootCalculator._return_item_to_inventory(inventory, unequipped_material, pet, int(user_id))
                        if not success:
                            return False, f"Failed to return material {unequipped_material.get('name')} to inventory: {msg}"
                        msg_parts.append(f"📦 Unequipped old Material: **{unequipped_material['name']}**")
                    success, msg = LootCalculator._remove_item_from_inventory(pet, item_obj)
                    if not success:
                        return False, f"Failed to remove material {item_obj.get('name')} from inventory: {msg}"
                    
                    equipped_materials = pet["equipment"].get("Material", [])
                    material_names_list = [m['name'] for m in equipped_materials]
                    emoji = emoji_mod.mention('material') or "🧵"
                    msg_parts.append(f"{emoji} Equipped Material(s): **{', '.join(material_names_list)}**")

            # 2. Hat
            if hat_name:
                item_obj = LootCalculator._get_item_from_inventory(pet, hat_name, "Hat")
                if not item_obj:
                    msg_parts.append(f"❌ Hat **{hat_name}** not found in inventory.")
                else:
                    unequipped_hat = LootCalculator._manage_equipment_slot(pet, "Hat", item_obj, max_slots=1)
                    if unequipped_hat:
                        success, msg = LootCalculator._return_item_to_inventory(inventory, unequipped_hat, pet, int(user_id))
                        if not success:
                            return False, f"Failed to return hat {unequipped_hat.get('name')} to inventory: {msg}"
                        msg_parts.append(f"📦 Unequipped old Hat: **{unequipped_hat['name']}**")
                    success, msg = LootCalculator._remove_item_from_inventory(pet, item_obj)
                    if not success:
                        return False, f"Failed to remove hat {item_obj.get('name')} from inventory: {msg}"
                    emoji = LootCalculator.get_pet_emoji("Hats", hat_name) or "🧢"
                    msg_parts.append(f"{emoji} Equipped **{hat_name}**")

            # 3. Gems
            if gem_names:
                names = [n.strip() for n in gem_names.split(',') if n.strip()][:2] # Limit to 2
                missing_gems = []
                for gem_name in names:
                    item_obj = LootCalculator._get_item_from_inventory(pet, gem_name, "Gem")
                    if not item_obj:
                        missing_gems.append(gem_name)
                    else:
                        unequipped_gem = LootCalculator._manage_equipment_slot(pet, "Gems", item_obj, max_slots=2)
                        if unequipped_gem:
                            success, msg = LootCalculator._return_item_to_inventory(inventory, unequipped_gem, pet, int(user_id))
                            if not success:
                                return False, f"Failed to return gem {unequipped_gem.get('name')} to inventory: {msg}"
                            msg_parts.append(f"📦 Unequipped old Gem: **{unequipped_gem['name']}**")
                        success, msg = LootCalculator._remove_item_from_inventory(pet, item_obj)
                        if not success:
                            return False, f"Failed to remove gem {item_obj.get('name')} from inventory: {msg}"
                
                equipped_gems = pet["equipment"].get("Gems", [])
                if equipped_gems:
                    gem_names_list = [g['name'] for g in equipped_gems]
                    emoji = emoji_mod.mention('gem') or "💎"
                    msg_parts.append(f"{emoji} Equipped Gem(s): **{', '.join(gem_names_list)}**")
                if missing_gems:
                    msg_parts.append(f"❌ Missing Gem(s): {', '.join(missing_gems)}")

            # 4. Monsters
            if monster_names:
                names = [n.strip() for n in monster_names.split(',') if n.strip()][:2] # Limit to 2
                missing_monsters = []
                for monster_name in names:
                    item_obj = LootCalculator._get_item_from_inventory(pet, monster_name, "Monster")
                    if not item_obj:
                        missing_monsters.append(monster_name)
                    else:
                        unequipped_monster = LootCalculator._manage_equipment_slot(pet, "Monsters", item_obj, max_slots=2)
                        if unequipped_monster:
                            success, msg = LootCalculator._return_item_to_inventory(inventory, unequipped_monster, pet, int(user_id))
                            if not success:
                                return False, f"Failed to return monster {unequipped_monster.get('name')} to inventory: {msg}"
                            msg_parts.append(f"📦 Unequipped old Monster: **{unequipped_monster['name']}**")
                        success, msg = LootCalculator._remove_item_from_inventory(pet, item_obj)
                        if not success:
                            return False, f"Failed to remove monster {item_obj.get('name')} from inventory: {msg}"
                
                equipped_monsters = pet["equipment"].get("Monsters", [])
                if equipped_monsters:
                    monster_names_list = [m['name'] for m in equipped_monsters]
                    emoji = emoji_mod.mention('monster') or "👹"
                    msg_parts.append(f"{emoji} Equipped Monster(s): **{', '.join(monster_names_list)}**")
                if missing_monsters:
                    msg_parts.append(f"❌ Missing Monster(s): {', '.join(missing_monsters)}")
            
            if not msg_parts:
                return False, "No changes made."

            pet['inventory'] = inventory
            pet['equipment'] = equipment
            
            await user_data_manager.save_pet_data(str(user_id), pet.get("name", "Pet"), pet)
            
            return True, "\n".join(msg_parts)
        except Exception as e:
            logger.error(f"Error in equip_items: {e}")
            return False, f"An error occurred: {e}"

    @staticmethod
    async def unequip_items(user_id: str, slot_type: str) -> Tuple[bool, str]:
        """
        Unequip items from a specific slot (Material, Gems, Monsters).
        Moves them back to inventory.
        """
        try:
            pet = await user_data_manager.get_pet_data_async(str(user_id))
            if not pet:
                return False, "You don't have a pet!"
            
            inventory = pet.get('inventory', [])
            # Consolidate inventory
            inventory = user_data_manager.UserDataManager._consolidate_inventory(inventory)
            
            equipment = pet.get('equipment', {})
            # Ensure multi-slot equipment types are initialized as lists
            equipment.setdefault("Material", [])
            equipment.setdefault("Gems", [])
            equipment.setdefault("Monsters", [])
            
            slot = slot_type.capitalize()
            if slot not in ["Material", "Gems", "Monsters", "Hat"]:
                return False, "Invalid slot type. Choose Material, Gems, Monsters, or Hat."
            
            items_removed = []
            xp_msgs = []

            if slot == "Material":
                item = equipment.get("Material")
                if item:
                    _, msg = LootCalculator._return_item_to_inventory(inventory, item, pet, int(user_id))
                    if msg: xp_msgs.append(msg)
                    del equipment["Material"]
                    items_removed.append(item.get("name", "Unknown Material"))

            elif slot == "Hat":
                item = equipment.get("Hat")
                if item:
                    _, msg = LootCalculator._return_item_to_inventory(inventory, item, pet, int(user_id))
                    if msg: xp_msgs.append(msg)
                    del equipment["Hat"]
                    items_removed.append(item.get("name", "Unknown Hat"))
            
            elif slot == "Gems":
                items = equipment.get("Gems", [])
                if items:
                    # Ensure it's a list for iteration, even if it was a single dict (legacy)
                    items_list = items if isinstance(items, list) else [items]
                    for item_obj in items_list:
                        _, msg = LootCalculator._return_item_to_inventory(inventory, item_obj, pet, int(user_id))
                        if msg: xp_msgs.append(msg)
                        items_removed.append(item_obj.get("name", "Unknown Gem"))
                    equipment["Gems"] = [] # Clear the slot

            elif slot == "Monsters":
                items = equipment.get("Monsters", [])
                if items:
                    # Ensure it's a list for iteration, even if it was a single dict (legacy)
                    items_list = items if isinstance(items, list) else [items]
                    for item_obj in items_list:
                        _, msg = LootCalculator._return_item_to_inventory(inventory, item_obj, pet, int(user_id))
                        if msg: xp_msgs.append(msg)
                        items_removed.append(item_obj.get("name", "Unknown Monster"))
                    equipment["Monsters"] = [] # Clear the slot
            
            if not items_removed:
                return False, f"No items found in {slot} slot."
            
            pet['inventory'] = inventory
            pet['equipment'] = equipment
            
            await user_data_manager.save_pet_data(str(user_id), pet.get("name", "Pet"), pet)
            
            result_msg = f"Unequipped: **{', '.join(items_removed)}**"
            if xp_msgs:
                result_msg += "\n" + "\n".join(xp_msgs)
            return True, result_msg
            
        except Exception as e:
            logger.error(f"Error in unequip_items: {e}")
            return False, f"An error occurred: {e}"


    @staticmethod
    def get_monster_loot_item(difficulty: str = "medium", bypass_chance: bool = False) -> Optional[Dict[str, Any]]:
        # Medium: 20%, Hard: 33% (No Easy)
        chance = 0.0
        if difficulty.lower() == "medium": chance = 0.20
        elif difficulty.lower() == "hard": chance = 0.33
        
        if not bypass_chance and random.random() > chance:
            return None
            
        data = LootCalculator._get_equipment_data()
        monsters = data.get("Monsters", [])
        if not monsters:
            return None

        # Rarity weights: Common 45%, Uncommon 25%, Rare 15%, Epic 10%, Mythic 5%
        weighted_monsters = []
        weights = []
        
        for m in monsters:
            rarity = m.get("rarity", "Common")
            w = 45
            if rarity == "Uncommon": w = 25
            elif rarity == "Rare": w = 15
            elif rarity == "Epic": w = 10
            elif rarity == "Mythic": w = 5
            
            weighted_monsters.append(m)
            weights.append(w)
            
        if not weighted_monsters:
            return random.choice(monsters)
            
        return random.choices(weighted_monsters, weights=weights, k=1)[0]

    @staticmethod
    def get_potion_loot(difficulty: str = "normal", bypass_chance: bool = False) -> Optional[Dict[str, Any]]:
        # Chance: 15% Easy, 25% Medium, 35% Hard
        chance = 0.15
        diff = difficulty.lower()
        if diff == "medium": chance = 0.25
        elif diff == "hard": chance = 0.35
        
        if not bypass_chance and random.random() > chance:
            return None
            
        data = LootCalculator._get_equipment_data()
        potions = data.get("Potions", [])
        if not potions:
            return None

        # Rarity weights: Common 45%, Uncommon 25%, Rare 15%, Epic 10%, Mythic 5%
        weighted_potions = []
        weights = []
        
        for p in potions:
            rarity = p.get("rarity", "Common")
            w = 45
            if rarity == "Uncommon": w = 25
            elif rarity == "Rare": w = 15
            elif rarity == "Epic": w = 10
            elif rarity == "Mythic": w = 5
            
            weighted_potions.append(p)
            weights.append(w)
            
        if not weighted_potions:
            return random.choice(potions)
            
        return random.choices(weighted_potions, weights=weights, k=1)[0]

    @staticmethod
    def get_hat_loot_item(difficulty: str = "normal", bypass_chance: bool = False) -> Optional[Dict[str, Any]]:
        # Chance: 10% Easy, 20% Medium, 30% Hard
        chance = 0.10
        diff = difficulty.lower()
        if diff == "medium": chance = 0.20
        elif diff == "hard": chance = 0.30
        
        if not bypass_chance and random.random() > chance:
            return None
            
        data = LootCalculator._get_equipment_data()
        hats = data.get("Hats", [])
        if not hats:
            return None

        # Rarity weights: Common 45%, Uncommon 25%, Rare 15%, Epic 10%, Mythic 5%
        weighted_hats = []
        weights = []
        
        for h in hats:
            rarity = h.get("rarity", "Common")
            w = 45
            if rarity == "Uncommon": w = 25
            elif rarity == "Rare": w = 15
            elif rarity == "Epic": w = 10
            elif rarity == "Mythic": w = 5
            
            weighted_hats.append(h)
            weights.append(w)
            
        if not weighted_hats:
            return random.choice(hats)
            
        return random.choices(weighted_hats, weights=weights, k=1)[0]

    @staticmethod
    def get_key_loot(difficulty: str = "normal", bypass_chance: bool = False) -> List[Dict[str, Any]]:
        """
        Calculates key loot based on difficulty.
        Easy: 33% Key1
        Average: 50% Key1, 33% Key2
        Hard: 75% Key1, 50% Key2, 33% Key3
        """
        diff = difficulty.lower()
        looted_keys = []
        
        # Helper to roll for a key
        def roll_key(name, chance):
            if random.random() < chance:
                looted_keys.append({
                    "name": name,
                    "type": "Key",
                    "rarity": "Rare",
                    "emoji_id": name
                })

        if diff == "easy":
            roll_key("Key1", 0.33)
        elif diff in ["average", "medium", "normal"]:
            roll_key("Key1", 0.50)
            roll_key("Key2", 0.33)
        elif diff == "hard":
            roll_key("Key1", 0.75)
            roll_key("Key2", 0.50)
            roll_key("Key3", 0.33)
            
        return looted_keys

    @staticmethod
    def get_chest_loot(difficulty: str = "normal") -> Optional[Dict[str, Any]]:
        # Very rare drop: 2% Easy, 5% Medium, 8% Hard
        chance = 0.02
        diff = difficulty.lower()
        if diff == "medium": chance = 0.05
        elif diff == "hard": chance = 0.08
        
        if random.random() > chance:
            return None
            
        chests = ["chest1", "chest2", "chest3", "chest4"]
        name = random.choices(chests, weights=[50, 30, 15, 5], k=1)[0]
        
        return {
            "name": name,
            "type": "Chest",
            "rarity": "Epic",
            "emoji_id": name
        }

    @staticmethod
    async def open_chest(user_id: int, chest_type: str, amount: int, selected_type: Optional[str] = None) -> List[str]:
        """
        Opens a chest, deducts keys, and awards loot.
        chest_type: "chest1", "chest2", "chest3", "chest4"
        amount: Number of chests to open
        selected_type: For Chest 4 (Material, Gem, Monster, Potion, Hat)
        """
        messages: List[str] = []
        try:
            pet_data = await user_data_manager.get_pet_data_async(str(user_id))
            if not pet_data:
                return ["You don't have a pet!"]
            
            inventory = pet_data.get("inventory", [])
            # Ensure consolidated
            inventory = user_data_manager.UserDataManager._consolidate_inventory(inventory)
            
            # Determine Cost
            cost = {}
            if chest_type == "chest1":
                cost = {"Key1": 1 * amount}
            elif chest_type == "chest2":
                cost = {"Key2": 1 * amount}
            elif chest_type == "chest3":
                cost = {"Key3": 1 * amount}
            elif chest_type == "chest4":
                cost = {"Key1": 1 * amount, "Key2": 1 * amount, "Key3": 1 * amount}
            else:
                return ["Invalid Chest Type"]
                
            # Check Affordability
            inventory_counts = {}
            for item in inventory:
                if item.get("type") == "Key":
                    inventory_counts[item.get("name")] = item.get("count", 1)
            
            for key_name, required_amount in cost.items():
                if inventory_counts.get(key_name, 0) < required_amount:
                    return [f"Not enough {key_name}! Need {required_amount}, have {inventory_counts.get(key_name, 0)}."]
            
            # Deduct Keys
            for key_name, required_amount in cost.items():
                for item in inventory:
                    if item.get("name") == key_name and item.get("type") == "Key":
                        item["count"] = item.get("count", 1) - required_amount
            
            # Remove 0 count items
            inventory = [i for i in inventory if i.get("count", 1) > 0]
            pet_data["inventory"] = inventory
            
            # Generate Loot
            items_to_add = []
            
            # Helper to get random item
            def get_random_item():
                loot_func = random.choice([
                    LootCalculator.get_material_loot_item,
                    LootCalculator.get_gem_loot_item,
                    LootCalculator.get_monster_loot_item,
                    LootCalculator.get_potion_loot,
                    LootCalculator.get_hat_loot_item
                ])
                return loot_func(bypass_chance=True)

            for _ in range(amount):
                if chest_type == "chest1":
                    # 1 random item
                    item = get_random_item()
                    if item: items_to_add.append(item)
                    
                elif chest_type == "chest2":
                    # 2 random items
                    for _ in range(2):
                        item = get_random_item()
                        if item: items_to_add.append(item)
                        
                elif chest_type == "chest3":
                    # 3 random items
                    for _ in range(3):
                        item = get_random_item()
                        if item: items_to_add.append(item)
                        
                elif chest_type == "chest4":
                    # 1 selected + 3 random
                    # Selected
                    sel_item = None
                    if selected_type == "Material": sel_item = LootCalculator.get_material_loot_item(bypass_chance=True)
                    elif selected_type == "Gem": sel_item = LootCalculator.get_gem_loot_item(bypass_chance=True)
                    elif selected_type == "Monster": sel_item = LootCalculator.get_monster_loot_item(bypass_chance=True)
                    elif selected_type == "Potion": sel_item = LootCalculator.get_potion_loot(bypass_chance=True)
                    elif selected_type == "Hat": sel_item = LootCalculator.get_hat_loot_item(bypass_chance=True)
                    
                    if sel_item: items_to_add.append(sel_item)
                    
                    # 3 Random
                    for _ in range(3):
                        item = get_random_item()
                        if item: items_to_add.append(item)
            
            # Bulk Add Items
            final_messages = []
            
            for item in items_to_add:
                i_type = item.get("type")
                i_name = item.get("name")
                
                limit = 5
                if i_type == "Potion": limit = 16
                elif i_type == "Key": limit = 99
                
                # Find in current inventory
                existing = next((i for i in inventory if i.get("name") == i_name and i.get("type") == i_type), None)
                
                curr_count = existing.get("count", 0) if existing else 0
                add_count = item.get("count", 1)
                
                if curr_count + add_count > limit:
                     # Calculate space available
                     available = max(0, limit - curr_count)
                     excess = add_count - available
                     
                     # Add what we can
                     if available > 0:
                         if existing:
                             existing["count"] = curr_count + available
                         else:
                             new_item = item.copy()
                             new_item["count"] = available
                             new_item["acquired_at"] = datetime.utcnow().isoformat()
                             inventory.append(new_item)
                         
                         emoji = LootCalculator.get_pet_emoji(i_type, i_name)
                         stats = LootCalculator._format_item_stats(item)
                         final_messages.append(f"🎁 {emoji} **{i_name}** x{available}{stats}")

                     # Convert excess to XP
                     if excess > 0:
                         lvl = int(pet_data.get("level", 1))
                         xp_gain = lvl * 100 * excess
                         
                         # Add XP
                         curr_xp = int(pet_data.get("experience", 0))
                         base = LootCalculator.get_total_experience_for_level(lvl)
                         new_total = base + curr_xp + xp_gain
                         _, new_lvl, new_xp = LootCalculator.recompute_level_from_total_xp(pet_data, new_total)
                         
                         pet_data["level"] = new_lvl
                         pet_data["experience"] = new_xp
                         final_messages.append(f"⚠️ Limit reached for {i_name}! {excess} items converted to {xp_gain} XP.")
                else:
                    if existing:
                        existing["count"] = curr_count + add_count
                    else:
                        new_item = item.copy()
                        new_item["count"] = add_count
                        new_item["acquired_at"] = datetime.utcnow().isoformat()
                        inventory.append(new_item)
                    
                    emoji = LootCalculator.get_pet_emoji(i_type, i_name)
                    stats = LootCalculator._format_item_stats(item)
                    final_messages.append(f"🎁 {emoji} **{i_name}**{stats}")

            pet_data["inventory"] = inventory
            await user_data_manager.save_pet_data(str(user_id), pet_data.get("name", "Pet"), pet_data)
            
            return final_messages

        except Exception as e:
            logger.error(f"Error opening chest: {e}")
            return [f"Error: {e}"]

    @staticmethod
    def calculate_level_up_stats(pet_data: Dict[str, Any], old_level: int, new_level: int) -> Dict[str, int]:
        """Calculates and applies stat gains for level up"""
        levels_gained = new_level - old_level
        if levels_gained <= 0: return {}

        points_per_level = 5 # Standard 5 points per level
        total_points = levels_gained * points_per_level
        
        stats = ["ATT", "DEF", "INT", "DEX", "HAP", "ENE"]
        gains = {s: 0 for s in stats}
        
        # Weighted random distribution based on existing stats (higher stats get more likely upgrades)
        # Or simple random distribution
        for _ in range(total_points):
            stat = random.choice(stats)
            pet_data[stat] = int(pet_data.get(stat, 0)) + 1
            gains[stat] += 1
            
        return gains

    @staticmethod
    async def apply_xp_change(user_id: int, xp_amount: int, source: str = "unknown") -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Centralized XP Application Logic.
        Applies XP, handles level ups/downs, updates stats, and saves data.
        Returns (has_level_changed, change_data)
        """
        try:
            pet_data = await user_data_manager.get_pet_data_async(str(user_id))
            if not pet_data:
                return False, None

            current_xp = int(pet_data.get("experience", 0))
            level = int(pet_data.get("level", 1))
            old_level = level
            
            total_xp_for_level = LootCalculator.get_total_experience_for_level(level)
            current_total_xp = total_xp_for_level + current_xp
            new_total_xp = max(0, current_total_xp + xp_amount)
            
            _, new_level, new_xp = LootCalculator.recompute_level_from_total_xp(pet_data, new_total_xp)
            
            pet_data["level"] = new_level
            pet_data["experience"] = new_xp
            
            # Track Source XP
            if "xp_sources" not in pet_data:
                pet_data["xp_sources"] = {}
            
            current_source_xp = pet_data["xp_sources"].get(source, 0)
            pet_data["xp_sources"][source] = current_source_xp + int(xp_amount)
            logger.info(f"Updated xp_sources for pet {pet_data.get('name')}: {pet_data['xp_sources']}")

            # Update total_xp_earned only for positive gains
            if xp_amount > 0:
                pet_data["total_xp_earned"] = int(pet_data.get("total_xp_earned", 0)) + int(xp_amount)

            change_data = {
                "old_level": old_level,
                "new_level": new_level,
                "xp_added": xp_amount,
                "source": source,
                "new_total_xp": new_total_xp,
                "gains": {}
            }
            
            has_changed = new_level != old_level
            
            if has_changed:
                if new_level > old_level:
                    # Level Up
                    gains = LootCalculator.calculate_level_up_stats(pet_data, old_level, new_level)
                    change_data["gains"] = gains
                elif new_level < old_level:
                    # Level Down
                    change_data["lost_xp"] = xp_amount
                    # No stat reduction on level down to keep it simple
            
            await user_data_manager.save_pet_data(str(user_id), pet_data.get("name", "Pet"), pet_data)
            return has_changed, change_data if has_changed else None
            
        except Exception as e:
            logger.error(f"Error applying XP change: {e}")
            return False, None



    @staticmethod
    async def calculate_loot(
        user_id: int, 
        pet_data: Dict[str, Any], 
        source: str = "battle", 
        difficulty: str = "normal", 
        winner_level: int = 1,
        loser_level: int = 1,
        is_winner: bool = True
    ) -> Dict[str, Any]:
        """
        Unified loot calculation for all sources.
        Returns a dictionary with results:
        {
            "xp_gained": int,
            "items_gained": List[Dict], # List of item dicts
            "messages": List[str], # Messages for each gain
            "leveled_up": bool,
            "level_up_embed": Optional[discord.Embed]
        }
        """
        result: Dict[str, Any] = {
            "xp_gained": 0,
            "items_gained": [], # mypy: List[Dict[str, Any]]
            "messages": [], # mypy: List[str]
            "leveled_up": False,
            "level_up_embed": None
        }
        
        # 1. Calculate XP
        xp_amount = 0
        if source == "pvp":
            if is_winner:
                xp_amount = LootCalculator.calculate_xp_gain(winner_level, loser_level)
            else:
                xp_amount = max(10, int(LootCalculator.calculate_xp_gain(loser_level, winner_level) * 0.2))
        else:
            # PvE
            level = int(pet_data.get("level", 1))
            if source == "mission":
                xp_amount = LootCalculator.calculate_mission_xp(level, difficulty)
            elif source == "training":
                xp_amount = LootCalculator.calculate_training_xp(level, difficulty)
            else:
                xp_amount = LootCalculator.calculate_pve_xp_gain(level, difficulty, source)
            
            if not is_winner:
                xp_amount = int(xp_amount * 0.1) # 10% XP for failure
            
        result["xp_gained"] = xp_amount
        
        # 2. Apply XP
        has_level_changed, change_data = await LootCalculator.apply_xp_change(user_id, xp_amount, source)
        
        if has_level_changed and change_data:
            new_lvl = change_data.get("new_level", 1)
            old_lvl = change_data.get("old_level", 1)
            
            # Update local pet_data to reflect changes
            pet_data["level"] = new_lvl
            pet_data["experience"] = int(pet_data.get("experience", 0)) # Actually apply_xp_change saved it, but we might need to reload or just trust it. 
            # Ideally apply_xp_change should return the updated pet_data or we should reload it if we need perfectly synced state, 
            # but for loot display, we just need the new level.
            
            if new_lvl > old_lvl:
                result["leveled_up"] = True
                result["messages"].append(f"📈 Gained **{xp_amount} XP** and Leveled Up to **{new_lvl}**!")
                result["level_up_embed"] = await LootCalculator.create_level_up_embed(pet_data, old_lvl, new_lvl, source)
            else:
                result["leveled_down"] = True
                result["messages"].append(f"📉 Lost XP... dropped to Level **{new_lvl}**.")
                result["level_down_embed"] = await LootCalculator.create_level_down_embed(pet_data, old_lvl, new_lvl, source, change_data.get("lost_xp", 0))
        else:
            result["messages"].append(f"📈 Gained **{xp_amount} XP**")

        # 3. Loot Items (Only if winner)
        if is_winner:
            # Use updated award_loot_items that returns items and messages
            # Note: We pass new_lvl just in case loot depends on it
            loot_result = await LootCalculator.award_loot_items(
                user_id=user_id,
                pet_data=pet_data,
                difficulty=difficulty,
                level=pet_data.get("level", 1),
                source=source
            )
            result["items_gained"].extend(loot_result["items_gained"])
            result["messages"].extend(loot_result["messages"])
        
        return result

    @staticmethod
    async def award_loot_items(user_id: int, pet_data: Dict[str, Any], difficulty: str = "normal", level: int = 1, source: str = "battle") -> Dict[str, Any]:
        """
        Awards all potential loot items based on difficulty and source.
        Returns dict with "items_gained" (list) and "messages" (list).
        Missions only award keys.
        """
        result: Dict[str, Any] = {"items_gained": [], "messages": []}
        items_to_add = []
        
        key_loot = LootCalculator.get_key_loot(difficulty)
        if key_loot:
            if isinstance(key_loot, list):
                items_to_add.extend(key_loot)
            else:
                items_to_add.append(key_loot)
        
        # Add collected items
        for item in items_to_add:
            added, msg = await LootCalculator.add_item_to_inventory(user_id, item, pet_data)
            if msg:
                result["messages"].append(msg)
            if added:
                result["items_gained"].append(item)
                
        return result


class StatsCalculator:
    """
    Handles all Pet Stat calculation logic including:
    - Equipment Stat Calculation (with bonuses and level multipliers)
    - Health Calculation (NPC, PvP, Tournament)
    """

    @staticmethod
    def calculate_computed_attack(att: int, dex: int) -> int:
        return int(att + dex)

    @staticmethod
    def calculate_computed_defense(deff: int, intel: int) -> int:
        return int(deff + intel)

    @staticmethod
    def _calculate_equipment_bonuses(pet_data: Dict[str, Any]) -> Dict[str, int]:
        """Internal helper to calculate raw equipment bonuses including Spec bonuses and Level Milestones"""
        equipment = pet_data.get('equipment') or {}
        if not equipment:
            return {k: 0 for k in ['ATT', 'DEF', 'INT', 'DEX', 'HAP', 'ENE']}
            
        level = int(pet_data.get('level', 1))
        specs = LootCalculator._get_pet_specs(pet_data)
        level_mult = 1 + (level // 50)
        
        items = []
        mat = equipment.get('Material')
        if mat and isinstance(mat, dict): items.append(('Material', mat))
        hat = equipment.get('Hat')
        if hat and isinstance(hat, dict): items.append(('Hat', hat))
        
        gems = equipment.get('Gems', [])
        if isinstance(gems, list):
            for g in gems: 
                if isinstance(g, dict): items.append(('Gem', g))
        elif isinstance(gems, dict):
            items.append(('Gem', gems))
            
        mons = equipment.get('Monsters', [])
        if isinstance(mons, list):
            for m in mons: 
                if isinstance(m, dict): items.append(('Monster', m))
        elif isinstance(mons, dict):
            items.append(('Monster', mons))
            
        mat_counts: Dict[str, int] = {} # Added for Material duplicates
        gem_counts: Dict[str, int] = {}
        mon_counts: Dict[str, int] = {}
        for type_key, item in items:
            name = item.get('name')
            if not name: continue
            if type_key == 'Material': # Added Material to duplicate check
                mat_counts[name] = mat_counts.get(name, 0) + 1
            elif type_key == 'Gem':
                gem_counts[name] = gem_counts.get(name, 0) + 1
            elif type_key == 'Monster':
                mon_counts[name] = mon_counts.get(name, 0) + 1
                
        equipment_bonuses = {k: 0 for k in ['ATT', 'DEF', 'INT', 'DEX', 'HAP', 'ENE']}
        for type_key, item in items:
            bonuses = item.get('bonuses', {})
            name = item.get('name')
            is_duplicate_pair = False
            if type_key == 'Material' and name and mat_counts.get(name, 0) >= 2: # Added Material
                is_duplicate_pair = True
            elif type_key == 'Gem' and name and gem_counts.get(name, 0) >= 2:
                is_duplicate_pair = True
            elif type_key == 'Monster' and name and mon_counts.get(name, 0) >= 2:
                is_duplicate_pair = True
                
            for stat, val in bonuses.items():
                if stat not in equipment_bonuses: continue
                try:
                    val = int(val)
                except:
                    continue
                
                mult = 1
                if is_duplicate_pair: # Removed "and stat in specs"
                    mult = 2 # Changed from 3 to 2 for double bonus
                
                equipment_bonuses[stat] += val * mult
        
        # Apply Level Milestone Bonus
        for stat in equipment_bonuses:
            equipment_bonuses[stat] *= level_mult
            
        return equipment_bonuses

    @staticmethod
    def calculate_pet_stats(pet_data: Dict[str, Any]) -> Dict[str, int]:
        """
        Calculate total stats including base stats and equipment bonuses.
        Returns a dict with base stats (ATT, DEF, etc.) and computed stats (attack, defense, max_health).
        """
        # Base stats
        stats = {
            'ATT': int(pet_data.get('ATT') or 0),
            'DEF': int(pet_data.get('DEF') or 0),
            'INT': int(pet_data.get('INT') or 0),
            'DEX': int(pet_data.get('DEX') or 0),
            'HAP': int(pet_data.get('HAP') or 0),
            'ENE': int(pet_data.get('ENE') or 0)
        }
        
        # Add equipment bonuses
        bonuses = StatsCalculator._calculate_equipment_bonuses(pet_data)
        for stat in stats:
            stats[stat] += bonuses.get(stat, 0)
            
        # Add computed combat stats
        stats['attack'] = StatsCalculator.calculate_computed_attack(stats['ATT'], stats['DEX'])
        stats['defense'] = StatsCalculator.calculate_computed_defense(stats['DEF'], stats['INT'])
        stats['max_health'] = StatsCalculator.calculate_max_health(pet_data)
        
        return stats

    @staticmethod
    def calculate_max_health(pet_data: Dict[str, Any]) -> int:
        """
        Calculate max health based on total stats (Base + Equipment).
        Formula: Leveled Stat Average (ATT+DEF+DEX+INT+HAP+ENE)/6 + Health Stat (HAP*ENE) * Health Bar (10)
        """
        # We need the stats AFTER equipment bonuses, but without derived stats to avoid recursion
        stats = {
            'ATT': int(pet_data.get('ATT') or 0),
            'DEF': int(pet_data.get('DEF') or 0),
            'INT': int(pet_data.get('INT') or 0),
            'DEX': int(pet_data.get('DEX') or 0),
            'HAP': int(pet_data.get('HAP') or 0),
            'ENE': int(pet_data.get('ENE') or 0)
        }
        
        # Add equipment bonuses
        bonuses = StatsCalculator._calculate_equipment_bonuses(pet_data)
        for stat in stats:
            stats[stat] += bonuses.get(stat, 0)
        
        # Leveled Stat Average
        total_stats = sum(stats.values())
        leveled_avg = total_stats / 6
        
        # Health Stat
        hap = stats.get('HAP', 0)
        ene = stats.get('ENE', 0)
        health_stat = hap * ene
        
        # Final Formula
        return int((leveled_avg + health_stat) * 10)


class DamageCalculator:
    _ACTION_LABELS_DATA: Optional[Dict[str, Any]] = None

    @staticmethod
    def _load_action_labels():
        if DamageCalculator._ACTION_LABELS_DATA is None:
            try:
                DamageCalculator._ACTION_LABELS_DATA = user_data_manager.file_manager.get_data("action_labels")
            except Exception as e:
                logger.error(f"Failed to load action_labels.json via OptimalFileManager: {e}")
                DamageCalculator._ACTION_LABELS_DATA = {}

    MAX_CHARGE_MULTIPLIER = 16.0
    VULNERABILITY_WHEN_CHARGING = 1.25

    @staticmethod
    def calculate_roll_multiplier(roll: int, base_stat: int) -> Tuple[int, str]:
        try:
            roll = max(1, min(20, int(roll)))
        except Exception:
            roll = 1
        try:
            base_stat = max(0, int(base_stat))
        except Exception:
            base_stat = 0
        return int(base_stat * roll), "high_mult"

    @staticmethod
    def get_pet_action_name(species: str, action_type: str) -> str:
        """Retrieves the themed battle action name for a pet species."""
        try:
            info_data = user_data_manager.file_manager.get_data("info")
            if not info_data: 
                return action_type.title()
            
            pet_data = info_data.get("Pets", {}).get(species, {})
            actions = pet_data.get("Actions", {})
            
            # Map action_type (lowercase) to JSON keys (Title Case)
            # "defend" maps to "Defense"
            key_map = {
                "attack": "Attack",
                "defend": "Defense",
                "defense": "Defense",
                "charge": "Charge"
            }
            
            json_key = key_map.get(action_type.lower(), "Attack")
            return actions.get(json_key, action_type.title())
        except Exception:
            return action_type.title()

    @staticmethod
    def calculate_battle_action(
        attacker_attack: int,
        target_defense: int,
        charge_multiplier: float = 1.0,
        target_charge_multiplier: float = 1.0,
        action_type: str = "attack",
        attacker_action_type: str = "attack",
        target_action_type: str = "defend",
        attacker_type: Optional[str] = None,
        attacker_element: Optional[str] = None,
        attacker_element2: Optional[str] = None,
        defender_type: Optional[str] = None,
        defender_element: Optional[str] = None,
        defender_element2: Optional[str] = None,
        attacker_species: Optional[str] = None,
        defender_species: Optional[str] = None
    ) -> Dict[str, Any]:
        try:
            attacker_attack = max(0, int(attacker_attack)) if attacker_attack is not None else 10
            target_defense = max(0, int(target_defense)) if target_defense is not None else 5
            charge_multiplier = max(1.0, min(16.0, float(charge_multiplier))) if charge_multiplier is not None else 1.0
            target_charge_multiplier = max(1.0, min(16.0, float(target_charge_multiplier))) if target_charge_multiplier is not None else 1.0
            action_type = str(action_type) if action_type is not None else "attack"
            attacker_action_type = (str(attacker_action_type or "attack").lower())
            target_action_type = (str(target_action_type or "defend").lower())
        except (ValueError, TypeError):
            attacker_attack = 10
            target_defense = 5
            charge_multiplier = 1.0
            target_charge_multiplier = 1.0
            action_type = "attack"
            attacker_action_type = "attack"
            target_action_type = "defend"

        if attacker_action_type not in ("attack", "defend", "charge"):
            attacker_action_type = "attack"
        if target_action_type not in ("attack", "defend", "charge"):
            target_action_type = "defend"

        # Resolve action names
        attacker_action_name = DamageCalculator.get_pet_action_name(attacker_species, attacker_action_type) if attacker_species else attacker_action_type.title()
        target_action_name = DamageCalculator.get_pet_action_name(defender_species, target_action_type) if defender_species else target_action_type.title()

        attack_roll = random.randint(1, 20)
        attack_value, attack_result = DamageCalculator.calculate_roll_multiplier(attack_roll, attacker_attack)

        final_attack = int(attack_value * charge_multiplier)

        # Advantage Calculation: TypeModifier * ElementModifier
        type_bonus = DamageCalculator.compute_type_bonus(attacker_type, defender_type)
        element_bonus = DamageCalculator.compute_element_bonus(attacker_element, defender_element, attacker_element2, defender_element2)
        atk_bonus_mult = type_bonus * element_bonus
        final_attack = int(final_attack * atk_bonus_mult)

        # Target defense only applies if defending this round
        if target_action_type == "defend":
            defense_roll = random.randint(1, 20)
            defense_value, defense_result = DamageCalculator.calculate_roll_multiplier(defense_roll, target_defense)
            final_defense = int(defense_value * target_charge_multiplier)
            
            # Advantage Calculation for Defense
            def_type_bonus = DamageCalculator.compute_type_bonus(defender_type, attacker_type)
            def_element_bonus = DamageCalculator.compute_element_bonus(defender_element, attacker_element, defender_element2, attacker_element2)
            def_bonus_mult = def_type_bonus * def_element_bonus
            final_defense = int(final_defense * def_bonus_mult)
        else:
            defense_roll = None
            defense_result = "none"
            final_defense = 0

        if attacker_action_type == "charge":
            final_damage = 0
            parry_damage = 0
        else:
            if target_action_type == "defend":
                if final_attack > final_defense:
                    final_damage = max(1, final_attack - final_defense)
                    parry_damage = 0
                elif final_attack == final_defense:
                    final_damage = 0
                    parry_damage = 0
                else:
                    final_damage = 0
                    parry_damage = max(1, final_defense - final_attack)
            elif target_action_type == "charge":
                base_damage = final_attack
                final_damage = int(max(0, base_damage) * DamageCalculator.VULNERABILITY_WHEN_CHARGING)
                parry_damage = 0
            else:
                final_damage = max(1, final_attack)
                parry_damage = 0

        return {
            'final_damage': final_damage,
            'parry_damage': parry_damage,
            'attack_roll': attack_roll,
            'defense_roll': defense_roll,
            'attack_result': attack_result,
            'defense_result': defense_result,
            'final_attack': final_attack,
            'final_defense': final_defense,
            'charge_used': charge_multiplier > 1.0 or target_charge_multiplier > 1.0,
            'attacker_action_type': attacker_action_type,
            'target_action_type': target_action_type,
            'type_element_bonus_mult_attack': atk_bonus_mult if 'atk_bonus_mult' in locals() else 1.0,
            'type_element_bonus_mult_defense': def_bonus_mult if 'def_bonus_mult' in locals() else 1.0,
            'attacker_action_name': attacker_action_name,
            'target_action_name': target_action_name
        }

    @staticmethod
    def calculate_monster_vs_players(
        monster_attack: int,
        player_defenses: Dict[str, Any],
        monster_charge_multiplier: float = 1.0,
        monster_type: Optional[str] = None,
        monster_element: Optional[str] = None
    ) -> Dict[str, Any]:
        try:
            monster_attack = max(0, int(monster_attack)) if monster_attack is not None else 10
            monster_charge_multiplier = max(1.0, min(16.0, float(monster_charge_multiplier))) if monster_charge_multiplier is not None else 1.0
            if not isinstance(player_defenses, dict):
                player_defenses = {}
        except (ValueError, TypeError):
            monster_attack = 10
            monster_charge_multiplier = 1.0
            player_defenses = {}
        results = {}

        for player_id, defense_info in player_defenses.items():
            player_defense = defense_info.get('defense', 0)
            player_charge_multiplier = defense_info.get('charge_multiplier', 1.0)
            player_action = str(defense_info.get('action', '') or '').lower()
            if not player_action:
                if defense_info.get('defending', False):
                    player_action = 'defend'
                elif defense_info.get('charging', False):
                    player_action = 'charge'
                else:
                    player_action = 'attack'

            battle_result = DamageCalculator.calculate_battle_action(
                attacker_attack=monster_attack,
                target_defense=player_defense,
                charge_multiplier=monster_charge_multiplier,
                target_charge_multiplier=player_charge_multiplier,
                action_type="monster_attack",
                attacker_action_type="attack",
                target_action_type=player_action,
                attacker_type=monster_type,
                attacker_element=monster_element,
                attacker_element2=None, # Monsters usually only have one element
                defender_type=defense_info.get('type'),
                defender_element=defense_info.get('element'),
                defender_element2=defense_info.get('element2'),
                defender_species=defense_info.get('species')
            )

            results[player_id] = {
                'final_damage': battle_result['final_damage'],
                'parry_damage': battle_result['parry_damage'],
                'attack_roll': battle_result['attack_roll'],
                'defense_roll': battle_result['defense_roll'],
                'attack_result': battle_result['attack_result'],
                'defense_result': battle_result['defense_result'],
                'final_attack': battle_result['final_attack'],
                'final_defense': battle_result['final_defense'],
                'charge_used': battle_result['charge_used'],
                'target_action_type': battle_result['target_action_type'],
                'attacker_action_name': battle_result.get('attacker_action_name'),
                'target_action_name': battle_result.get('target_action_name')
            }

        return results

    @staticmethod
    def get_charge_progression() -> list:
        return [1.0, 2.0, 4.0, 8.0, 16.0]

    @staticmethod
    def get_next_charge_multiplier(current_multiplier: float) -> float:
        try:
            current_multiplier = float(current_multiplier) if current_multiplier is not None else 1.0
            current_multiplier = max(1.0, min(16.0, current_multiplier))
        except (ValueError, TypeError):
            current_multiplier = 1.0

        progression = DamageCalculator.get_charge_progression()
        try:
            current_index = progression.index(current_multiplier)
            if current_index < len(progression) - 1:
                return progression[current_index + 1]
            else:
                return DamageCalculator.MAX_CHARGE_MULTIPLIER
        except ValueError:
            return progression[1]

    @staticmethod
    def calculate_pet_health(hap: int, ene: int, level: int = 1, att: int = 0, deff: int = 0, intel: int = 0, dex: int = 0) -> int:
        """
        Calculate Max Health using the balanced formula:
        (Leveled Stat Average + (HAP * ENE)) * 10
        
        If other stats (ATT, DEF, etc.) are not provided, estimates average based on HAP/ENE.
        """
        try:
            hap_i = max(0, int(hap))
            ene_i = max(0, int(ene))
            # Level is no longer a direct multiplier, but kept for signature compatibility
            
            # Calculate average stat
            stats = [hap_i, ene_i]
            if att: stats.append(int(att))
            if deff: stats.append(int(deff))
            if intel: stats.append(int(intel))
            if dex: stats.append(int(dex))
            
            avg_stat = sum(stats) / len(stats)
            
            health_stat = hap_i * ene_i
            
            return int((avg_stat + health_stat) * 10)
            
        except Exception:
            return 100 # Fallback safety

    ELEMENT_EFFECTIVENESS: Dict[str, Dict[str, float]] = {
        "basic": {
            "basic": 0.90, "fire": 0.90, "water": 0.90, "electric": 0.90, "ice": 0.90,
            "plant": 0.90, "rock": 0.90, "air": 0.90, "magic": 0.90, "holy": 0.90,
            "necro": 0.90, "psychic": 0.90, "fighting": 0.90
        },
        "fire": {"ice": 1.10, "plant": 1.10, "necro": 1.10},
        "electric": {"water": 1.10, "plant": 1.10, "fighting": 1.10},
        "air": {"rock": 1.10, "fighting": 1.10, "electric": 1.10},
        "ice": {"air": 1.10, "electric": 1.10, "water": 1.10},
        "water": {"fire": 1.10, "rock": 1.10, "air": 1.10},
        "plant": {"water": 1.10, "air": 1.10, "psychic": 1.10},
        "rock": {"electric": 1.10, "fire": 1.10, "ice": 1.10},
        "fighting": {"ice": 1.10, "psychic": 1.10, "holy": 1.10},
        "psychic": {"holy": 1.10, "necro": 1.10, "magic": 1.10},
        "magic": {"psychic": 1.10, "fighting": 1.10, "fire": 1.10},
        "holy": {"necro": 1.10, "magic": 1.10, "rock": 1.10},
        "necro": {"holy": 1.10, "magic": 1.10, "plant": 1.10},
    }

    CATEGORY_ADVANTAGES: Dict[str, Dict[str, float]] = {
        "flying": {"land": 1.15},
        "land": {"swimming": 1.15},
        "swimming": {"flying": 1.15},
    }

    @staticmethod
    def get_action_labels(pet_type: str, pet_element: str, species: Optional[str] = None) -> Dict[str, str]:
        """Return action labels. Prefers species-specific actions from info.json, falls back to type/element defaults."""
        DamageCalculator._load_action_labels() # Ensure labels are loaded
        if not DamageCalculator._ACTION_LABELS_DATA: # Fallback if loading failed
            return {"attack": "Attack", "defend": "Defend", "charge": "Charge"}

        # Try to get species-specific actions first
        if species:
            try:
                # Use the helper method to check if we have valid custom actions
                # We check one action to verify existence; get_pet_action_name handles the lookup safely
                atk = DamageCalculator.get_pet_action_name(species, "attack")
                dfd = DamageCalculator.get_pet_action_name(species, "defense")
                chg = DamageCalculator.get_pet_action_name(species, "charge")

                return {
                    "attack": atk,
                    "defend": dfd,
                    "charge": chg
                }
            except Exception:
                pass # Fall back to legacy system on error

        t = str(pet_type or "basic").lower()
        e = str(pet_element or "basic").lower()

        type_map = DamageCalculator._ACTION_LABELS_DATA.get(t, DamageCalculator._ACTION_LABELS_DATA["land"])
        entry = type_map.get(e, type_map["basic"])
        return {"attack": entry["attack"], "defend": entry["defend"], "charge": entry["charge"]}
    
    @staticmethod
    def compute_type_bonus(attacker_type: Optional[str], defender_type: Optional[str]) -> float:
        try:
            a_t = str(attacker_type or "").lower()
            d_t = str(defender_type or "").lower()
            return DamageCalculator.CATEGORY_ADVANTAGES.get(a_t, {}).get(d_t, 1.0)
        except Exception:
            return 1.0

    @staticmethod
    def compute_element_bonus(attacker_element: Optional[str], defender_element: Optional[str], attacker_element2: Optional[str] = None, defender_element2: Optional[str] = None) -> float:
        """
        Calculates element effectiveness multiplier. 
        Supports dual elements by averaging the modifiers.
        """
        try:
            # Helper to get bonus for one pair
            def get_pair_bonus(a, d):
                if not a or not d: return 1.0
                return DamageCalculator.ELEMENT_EFFECTIVENESS.get(str(a).lower(), {}).get(str(d).lower(), 1.0)

            # Collect all combinations
            attackers = [attacker_element]
            if attacker_element2 and str(attacker_element2).lower() not in ("basic", "none", ""):
                attackers.append(attacker_element2)
            
            defenders = [defender_element]
            if defender_element2 and str(defender_element2).lower() not in ("basic", "none", ""):
                defenders.append(defender_element2)

            bonuses = []
            for a in attackers:
                for d in defenders:
                    bonuses.append(get_pair_bonus(a, d))
            
            if not bonuses:
                return 1.0
                
            return sum(bonuses) / len(bonuses)
        except Exception:
            return 1.0

class NPCBrain:
    def decide_action(self, monster_state: Dict[str, Any], players_state: List[Dict[str, Any]]) -> Dict[str, Any]:
        hp = max(0, int(monster_state.get("hp", 0)))
        max_hp = max(1, int(monster_state.get("max_hp", 1)))
        charge_mult = float(monster_state.get("charge_multiplier", 1.0))
        last_action = monster_state.get("last_action")
        defending = bool(monster_state.get("defending", False))
        seed = monster_state.get("seed")
        prev_hp = monster_state.get("prev_hp")
        attack_stat = float(monster_state.get("attack_stat", 1.0))
        defense_stat = float(monster_state.get("defense_stat", 1.0))

        if seed is not None:
            try:
                random.seed(int(seed))
            except Exception:
                pass

        m_pct = (hp / max_hp) * 100.0
        loss_rate = 0.0
        if prev_hp is not None:
            try:
                prev_hp_i = max(0, int(prev_hp))
                loss_rate = max(0.0, (prev_hp_i - hp) / max_hp)
            except Exception:
                loss_rate = 0.0

        alive_players = [p for p in players_state if p.get("alive", False) and p.get("hp", 0) > 0]
        n_alive = len(alive_players)
        total_players = len(players_state)
        eliminations = max(0, total_players - n_alive)

        if n_alive == 0:
            return {"action": "defend", "rationale": "No opponents alive", "strategy": "spread"}

        player_pcts = [max(0.0, min(100.0, (p.get("hp", 0) / max(1, p.get("max_hp", 1))) * 100.0)) for p in alive_players]
        avg_player_pct = sum(player_pcts) / len(player_pcts)
        weakest_pct = min(player_pcts)
        strongest_pct = max(player_pcts)
        any_player_critical = weakest_pct <= 10.0
        any_player_finisher_range = weakest_pct <= 25.0
        players_charging = [p for p in alive_players if p.get("charging", False)]
        charging_count = len(players_charging)
        many_players = n_alive >= 3

        if hp == max_hp:
            stage = "full"
        elif m_pct >= 75.0:
            stage = "three_quarters"
        elif m_pct >= 50.0:
            stage = "half"
        elif m_pct >= 25.0:
            stage = "quarter"
        elif m_pct >= 10.0:
            stage = "ten_percent"
        else:
            stage = "critical"

        weights = {"attack": 0, "defend": 0, "charge": 0}
        strategy = "spread"

        if stage == "full":
            weights["attack"] = 6
            weights["defend"] = 1
            weights["charge"] = 3 if many_players else 2
        elif stage == "three_quarters":
            weights["attack"] = 6
            weights["defend"] = 2
            weights["charge"] = 3 if many_players else 2
        elif stage == "half":
            weights["attack"] = 5
            weights["defend"] = 3
            weights["charge"] = 2
        elif stage == "quarter":
            weights["attack"] = 5
            weights["defend"] = 5
            charge_base = 2
            charge_decay = int(max(0, (50.0 - m_pct) / 12.0))
            weights["charge"] = max(0, charge_base - charge_decay)
            if loss_rate >= 0.20:
                weights["charge"] = max(0, weights["charge"] - 2)
                weights["defend"] += 1
        elif stage == "ten_percent":
            weights["attack"] = 4
            weights["defend"] = 6
            weights["charge"] = 0
        else:
            weights["attack"] = 2
            weights["defend"] = 7
            weights["charge"] = 0

        if n_alive == 1:
            weights["attack"] += 2
            if weights["defend"] > 0:
                weights["defend"] -= 1
        elif n_alive == 2:
            weights["attack"] += 1
        elif n_alive == 4:
            if stage in ("full", "three_quarters", "half"):
                weights["charge"] += 1

        if any_player_finisher_range:
            weights["attack"] += 2
            strategy = "focus_weakest"
        elif avg_player_pct < 50.0 and not many_players:
            weights["attack"] += 1

        pressure_advantage = m_pct - avg_player_pct
        if pressure_advantage >= 15:
            weights["attack"] += 2
            if stage in ("full", "three_quarters") and many_players:
                weights["charge"] += 1
        elif pressure_advantage <= -15:
            weights["defend"] += 2
            weights["charge"] = max(0, weights["charge"] - 1)

        safe_to_charge = (
            stage in ("full", "three_quarters", "half") and
            avg_player_pct >= 50.0 and
            not any_player_critical and
            charging_count == 0
        )
        if not safe_to_charge:
            weights["charge"] = max(0, weights["charge"] - 2)

        if charge_mult >= 4.0:
            weights["attack"] += 2
            weights["charge"] = max(0, weights["charge"] - 2)
            if many_players and m_pct >= 50.0 and not any_player_finisher_range:
                strategy = "focus_strongest"

        if charging_count >= 2 and m_pct <= 50.0:
            weights["defend"] += 2
            weights["charge"] = 0
        elif charging_count == 1 and stage in ("full", "three_quarters", "half"):
            weights["attack"] += 1
            strategy = "focus_strongest" if strongest_pct >= 60.0 else strategy

        if last_action == "charge":
            weights["attack"] += 2
            if stage in ("quarter", "critical"):
                weights["defend"] += 1
            weights["charge"] = max(0, weights["charge"] - 2)
        elif last_action == "defend":
            weights["attack"] += 1
        elif last_action == "attack" and stage in ("quarter", "ten_percent", "critical"):
            weights["defend"] += 1

        if eliminations >= 1 and m_pct >= 25.0:
            weights["attack"] += 1

        bias_den = max(1.0, attack_stat + defense_stat)
        attack_bias = (attack_stat - defense_stat) / bias_den
        bias_scale = 2 if m_pct <= 50.0 else 1
        if attack_bias > 0:
            weights["attack"] += 1 + int(round(abs(attack_bias) * 3)) * bias_scale
        elif attack_bias < 0:
            weights["defend"] += 1 + int(round(abs(attack_bias) * 3)) * bias_scale

        if m_pct >= 50.0 and abs(attack_bias) < 0.15 and charge_mult < 4.0:
            weights["charge"] += 1

        if m_pct <= 15.0:
            weights["charge"] = 0
            if attack_bias > 0:
                weights["attack"] += 2
            elif attack_bias < 0:
                weights["defend"] += 2

        base_risk = {
            "full": 0.7,
            "three_quarters": 0.65,
            "half": 0.55,
            "quarter": 0.4,
            "ten_percent": 0.3,
            "critical": 0.25,
        }[stage]
        adv_factor = max(-0.2, min(0.2, pressure_advantage / 100.0))
        risk = max(0.05, min(0.95, base_risk + adv_factor + (random.random() - 0.5) * 0.1))

        noisy: Dict[str, float] = {}
        for k, w in weights.items():
            if k == "charge" and m_pct <= 15.0:
                noisy[k] = 0.0
            else:
                noisy[k] = max(0.0, w + risk * random.uniform(0, 1.0))

        top = max(noisy.values())
        candidates = [k for k, v in noisy.items() if abs(v - top) < 0.75]
        if len(candidates) == 1:
            action = candidates[0]
        else:
            for pref in ("attack", "defend", "charge"):
                if pref in candidates:
                    action = pref
                    break
            else:
                action = random.choices(list(noisy.keys()), weights=list(noisy.values()))[0]

        if any_player_finisher_range:
            strategy = "focus_weakest"
        elif charging_count >= 1 and m_pct >= 50.0 and not any_player_finisher_range:
            strategy = "focus_strongest"
        elif many_players and stage in ("full", "three_quarters") and action == "attack":
            strategy = "spread"

        rationale = (
            f"stage={stage}, n_alive={n_alive}, avg_player_pct={avg_player_pct:.0f}, "
            f"weakest_pct={weakest_pct:.0f}, strongest_pct={strongest_pct:.0f}, "
            f"charge_mult=x{charge_mult:.1f}, charging_count={charging_count}, risk={risk:.2f}, "
            f"att={attack_stat:.1f}, def={defense_stat:.1f}"
        )

        return {"action": action, "rationale": rationale, "strategy": strategy}
