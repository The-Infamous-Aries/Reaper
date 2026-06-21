from __future__ import annotations
import math
import random
import logging
import discord
from typing import Dict, Any, Tuple, List, Optional, Union
from datetime import datetime
from Systems.Functions.user_data_manager import user_data_manager
from Systems.Functions import emoji as emoji_mod

logger = logging.getLogger('pet_brain')


def _get_ability_effect(pet_data: Optional[Dict[str, Any]], effect_type: str, **kwargs) -> float:
    """Safe wrapper — returns 0.0 (additive identity) or 1.0 (multiplicative identity) on failure."""
    if not pet_data:
        return 0.0
    try:
        from Systems.Pets.Logic.ability_tree import get_ability_effect
        return get_ability_effect(pet_data, effect_type, **kwargs)
    except Exception:
        return 0.0

class LootCalculator:

    @staticmethod
    def _stats_calculator():
        """Lazy import to avoid circular dependency."""
        from Systems.Pets.Logic.pet_brain import StatsCalculator
        return StatsCalculator

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
    def _get_item_from_inventory(pet: Dict[str, Any], item_name: str, item_type: str,
                                  reforged: Optional[bool] = None,
                                  reforge_level: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieves an item from the pet's inventory using the full identity key.
        Does NOT remove it.

        When `reforged` is None, matches by name+type only (backward-compatible).
        When `reforged` is True/False, also matches reforged flag and (if provided) reforge_level.
        """
        inventory = pet.get("inventory", [])
        for item in inventory:
            if item.get("name") == item_name and item.get("type") == item_type:
                if reforged is not None:
                    item_ref = bool(item.get("reforged", False))
                    if item_ref != reforged:
                        continue
                    if reforge_level is not None:
                        item_rl = int(item.get("reforge_level", 0))
                        if item_rl != reforge_level:
                            continue
                return item
        return None

    @staticmethod
    def _remove_item_from_inventory(pet: Dict[str, Any], item: Dict[str, Any], count: int = 1) -> Tuple[bool, str]:
        """
        Removes an item (or a specified count of it) from the pet's inventory.
        Updates the pet's inventory in place.

        Matching uses the same identity key as _consolidate_inventory:
            (name, type, rarity, reforged, reforge_level)
        so that plain and reforged stacks are never confused.
        """
        inventory = pet.get("inventory", [])
        item_name    = item.get("name")
        item_type    = item.get("type")
        item_rarity  = item.get("rarity", "Common")
        item_reforged = bool(item.get("reforged", False))
        item_rl      = int(item.get("reforge_level", 0)) if item_reforged else 0

        # Find the exact stack using the full identity key
        found_item = None
        for inv_item in inventory:
            if (inv_item.get("name") == item_name
                    and inv_item.get("type") == item_type
                    and inv_item.get("rarity", "Common") == item_rarity
                    and bool(inv_item.get("reforged", False)) == item_reforged
                    and (int(inv_item.get("reforge_level", 0)) if item_reforged else 0) == item_rl):
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
            "Monster": "Monsters",
            "Potion": "Potions"
        }
        real_category = cat_map.get(category, category)

        if real_category == "Pet Level":
            try:
                lvl = int(key)
            except Exception:
                lvl = 1
            if lvl > 500:
                target_key = "P26"  # P26 is the "beyond" emoji, used for all levels above 500
            else:
                bucket = ((max(1, lvl) - 1) // 20) + 1
                bucket = min(bucket, 25)  # P1–P25 cover levels 1–500; P26 is beyond
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

        At extreme levels (1.03^n overflows float), returns 10^18 as a sentinel
        so XP arithmetic still works without hard-capping the level.
        """
        if level <= 1: return 0

        n = level - 1
        try:
            result = 200 * (1 - 1.03**n) / (1 - 1.03)
            # Check for inf/nan (happens around level ~24000+)
            if not math.isfinite(result):
                return 10 ** 18
            return int(result)
        except (OverflowError, ValueError):
            return 10 ** 18

    @staticmethod
    def get_next_level_xp(level: int) -> int:
        """XP needed to finish current level"""
        return LootCalculator.get_level_experience(level)

    @staticmethod
    def recompute_level_from_total_xp(pet_data: dict, total_xp: int) -> Tuple[int, int, int]:
        """
        Compute level from total XP using optimized O(log n) algorithm.
        No level cap — levels grow forever. At extreme XP values where the
        geometric formula overflows, the level is estimated from the overflow
        sentinel (10^18) so progression never hard-stops.
        """
        if total_xp <= 0:
            return 0, 1, 0
        
        # Use closed-form logarithmic solution as starting estimate
        # Formula: total_xp = 200 * (1 - 1.03^n) / (1 - 1.03) where n = level - 1
        # Solving for n: n = log(1 + total_xp * 0.03 / 200) / log(1.03)
        try:
            inner = 1.0 + float(total_xp) * 0.03 / 200.0
            if inner <= 1.0:
                return total_xp, 1, total_xp
            n = math.log(inner) / math.log(1.03)
            level = max(1, int(n) + 1)
        except (ValueError, OverflowError):
            # Fallback for extreme XP values — estimate level from sentinel
            level = 1

        # Fine-tune: walk down if we overshot
        while level > 1:
            needed = LootCalculator.get_total_experience_for_level(level)
            if total_xp >= needed:
                break
            level -= 1

        # Walk up if we undershot (rare but be safe)
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
    def calculate_play_loot(pet_element: str, pet_element2: str, place_specials: Dict[str, Any], level: int = 1) -> Tuple[int, List[str]]:
        import random as _random
        keys_to_award_names = []
        base_xp = max(1, level) * 5  # XP = 5 × level, as shown in UI
        all_keys = ["Key1", "Key2", "Key3"]

        def _bonus_keys(extra_chance: float) -> List[str]:
            """Roll for 1 or 2 bonus keys at the given chance."""
            if _random.random() < extra_chance:
                return _random.sample(all_keys, k=_random.randint(1, 2))
            return []

        if pet_element == "basic":
            xp_gained = _random.randint(base_xp, base_xp + 5)
            # 75% chance for 1 random key
            if _random.random() < 0.75:
                keys_to_award_names = [_random.choice(all_keys)]
        else:
            matched_elements_in_specials = []
            lower_case_place_specials_keys = {k.lower() for k in place_specials.keys()}

            if pet_element in lower_case_place_specials_keys:
                matched_elements_in_specials.append(pet_element)
            if pet_element2 and pet_element2 in lower_case_place_specials_keys:
                matched_elements_in_specials.append(pet_element2)

            if len(matched_elements_in_specials) == 2:
                # Both elements match — 3x XP, guaranteed 1 key + 50% chance for 1-2 more
                xp_gained = _random.randint(base_xp * 3, base_xp * 3 + 5)
                base_key = [_random.choice(all_keys)]
                bonus = _bonus_keys(0.50)
                keys_to_award_names = list(dict.fromkeys(base_key + bonus))  # deduplicate, preserve order
            elif len(matched_elements_in_specials) == 1:
                # One element matches — 2x XP, guaranteed 1 key + 25% chance for 1-2 more
                xp_gained = _random.randint(base_xp * 2, base_xp * 2 + 5)
                base_key = [_random.choice(all_keys)]
                bonus = _bonus_keys(0.25)
                keys_to_award_names = list(dict.fromkeys(base_key + bonus))
            else:
                # No match — 1x XP, 75% chance for 1 random key
                xp_gained = _random.randint(base_xp, base_xp + 5)
                if _random.random() < 0.75:
                    keys_to_award_names = [_random.choice(all_keys)]

        return xp_gained, keys_to_award_names

    @staticmethod
    def calculate_boss_loot(level: int) -> Tuple[int, List[Dict[str, Any]]]:
        """
        Calculate loot for defeating a boss.
        - 5x normal 'play' XP
        - 1 of each key type
        """
        # 5x normal 'play' XP
        xp_gain = LootCalculator.calculate_pve_xp_gain(level, "hard", "play") * 5

        # 1 of each key type
        keys = [
            {"name": "Key1", "type": "Key", "rarity": "Common"},
            {"name": "Key2", "type": "Key", "rarity": "Uncommon"},
            {"name": "Key3", "type": "Key", "rarity": "Rare"},
        ]

        return xp_gain, keys

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
                title=f"{emoji_mod.mention('LevelUp')} LEVEL UP! {emoji_mod.mention('LevelUp')}".strip(),
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
        elif source == "quest": embed.set_footer(text="Victory in the quest!")
        elif source in ("npc_battle", "pvp_battle", "boss_battle"): embed.set_footer(text="Growing stronger through combat!")
        elif source == "pet_stock": embed.set_footer(text="Profits from the pet stock market!")
        else: embed.set_footer(text="New power unlocked!")
            
        return embed

    @staticmethod
    async def create_level_down_embed(pet_data: dict, old_level: int, new_level: int, source: str = "mission", lost_xp: int = 0, losses: Optional[Dict[str, int]] = None) -> discord.Embed:
        name = pet_data.get('name', 'Pet')
        src_emojis = LootCalculator.get_pet_source_emojis()
        src_emoji = src_emojis.get(source, "")

        embed = discord.Embed(
                title=f"{emoji_mod.mention('Downgrade')} LEVEL DOWN {emoji_mod.mention('Downgrade')}".strip(),
                description=f"**{name}** has fallen to **Level {new_level}**...",
                color=0xFF0000
            )
        
        embed.add_field(name="Level Change", value=f"Level {old_level} ➡️ Level {new_level}", inline=False)

        if lost_xp > 0:
            embed.add_field(name="XP Lost", value=f"-{lost_xp:,} XP", inline=False)

        # Show which stats were reduced by the level-down
        if losses and any(v > 0 for v in losses.values()):
            loss_lines = " | ".join(f"-{v} {s}" for s, v in losses.items() if v > 0)
            total_lost = sum(losses.values())
            embed.add_field(
                name=f"Stats Lost ({total_lost} pts from {old_level - new_level} levels)",
                value=loss_lines,
                inline=False
            )
            
        stats = LootCalculator._format_stat_block(pet_data)
        embed.add_field(name="Current Stats", value=stats, inline=False)
        
        if source == "mission": embed.set_footer(text="The mission was too dangerous...")
        elif source == "mission_fail": embed.set_footer(text="The mission was too dangerous...")
        elif source == "gamble": embed.set_footer(text="Fortune was not on your side...")
        elif source == "pet_stock": embed.set_footer(text="The market turned against you...")
        else: embed.set_footer(text="A costly defeat...")
            
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
        All item types stack to 99.
        Fallback: Current Level * 100 XP if stack is full.
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

            # Always enforce canonical rarity from equipment.json so the stored
            # rarity can never diverge from the source-of-truth definition.
            # Keys and Chests are not in equipment.json so we skip them.
            if item_type not in ("Key", "Chest"):
                canonical = user_data_manager.file_manager.get_equipment_item(item_name)
                if canonical and canonical.get("rarity"):
                    item = {**item, "rarity": canonical["rarity"]}
            
            # Determine limit based on type — all items stack to 99
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
            
            # We need to save the inventory if items were added.
            # apply_xp_change saves XP/level but NOT the inventory, so we always
            # save here when amount_added > 0 to ensure keys/items persist.
            if amount_added > 0:
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
            inventory = user_data_manager._consolidate_inventory(inventory)
            
            # Find potion — match by display name first, then fall back to
            # emoji_file stem (e.g. "mega_potion") for legacy inventory entries.
            potion_idx = -1
            potion_item = None
            canonical_potion: Optional[Dict[str, Any]] = None

            # Build a lookup from equipment.json so we can normalise legacy names
            try:
                eq_data = LootCalculator._get_equipment_data()
                all_potions = eq_data.get("Potions", [])
            except Exception as _e:
                logger.error(f"use_potion: failed to load equipment data: {_e}")
                all_potions = []

            # Build emoji_file-stem → canonical potion map for legacy matching
            _stem_to_potion: Dict[str, Dict[str, Any]] = {}
            for _p in all_potions:
                _ef = _p.get("emoji_file", "")
                # Strip subfolder prefix and extension to get bare stem (e.g. "Potions/mega_potion.png" → "mega_potion")
                _stem = _ef.split("/")[-1].replace(".png", "").replace(".jpg", "").lower() if _ef else ""
                if _stem:
                    _stem_to_potion[_stem] = _p

            for i, item in enumerate(inventory):
                if item.get("type") != "Potion":
                    continue
                item_name_stored = item.get("name", "")
                # Exact display-name match
                if item_name_stored == potion_name:
                    potion_idx = i
                    potion_item = item
                    break
                # Legacy: stored name is the emoji_file stem (e.g. "mega_potion")
                # and the user is requesting by display name (e.g. "Mega Potion")
                _canon = _stem_to_potion.get(item_name_stored.lower())
                if _canon and _canon.get("name") == potion_name:
                    potion_idx = i
                    potion_item = item
                    canonical_potion = _canon
                    break

            if potion_idx == -1 or potion_item is None:
                return False, f"You don't have any {potion_name}!"

            effect = potion_item.get("use_effect")
            if not effect:
                # Fallback 1: canonical potion already resolved via legacy stem match
                if canonical_potion:
                    effect = canonical_potion.get("use_effect")
                    # Also fix the stored name so future uses work without the fallback
                    potion_item["name"] = canonical_potion["name"]
                    potion_item["rarity"] = canonical_potion.get("rarity", potion_item.get("rarity", "Common"))

            if not effect:
                # Fallback 2: item stored without use_effect (e.g. purchased via bazaar).
                # Look up the canonical definition from equipment.json by display name.
                try:
                    for p in all_potions:
                        if p["name"] == potion_name:
                            effect = p.get("use_effect")
                            break
                    if not effect:
                        logger.warning(f"use_potion: no use_effect found for '{potion_name}' in equipment.json (potions count={len(all_potions)})")
                except Exception as _e:
                    logger.error(f"use_potion: equipment.json fallback failed: {_e}")

            if not effect:
                return False, "This potion has no effect!"

            # Apply Logic
            stats = ["ATT", "DEF", "INT", "DEX", "HAP", "ENE"]
            changes = []

            # Get equipment multiplier so potion effects scale with the pet's gear
            equip_mult = int(LootCalculator._stats_calculator().get_equipment_xp_multiplier(pet))
            equip_mult = max(1, equip_mult)
            
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
                    val = effect.get("value_dual", 3) * equip_mult
                else:
                    # 3 stats by 5
                    targets = random.sample(stats, 3)
                    val = effect.get("value_single", 5) * equip_mult
                
                for stat in targets:
                    pet[stat] = int(pet.get(stat, 0)) + val
                    changes.append(f"+{val} {stat}")

            elif etype == "attribute_boost":
                target = effect.get("attribute")
                val = effect.get("value", 3) * equip_mult
                if target in stats:
                    pet[target] = int(pet.get(target, 0)) + val
                    changes.append(f"+{val} {target}")
            
            elif etype == "random_boost":
                count = effect.get("count", 2)
                val = effect.get("value", 1) * equip_mult
                targets = random.sample(stats, min(count, len(stats)))
                for stat in targets:
                    pet[stat] = int(pet.get(stat, 0)) + val
                    changes.append(f"+{val} {stat}")
            
            elif etype == "luck_boost":
                min_v = effect.get("min", 1)
                max_v = effect.get("max", 5)
                for stat in stats:
                    roll = random.randint(min_v, max_v) * equip_mult
                    pet[stat] = int(pet.get(stat, 0)) + roll
                    changes.append(f"+{roll} {stat}")

            elif etype == "mega_boost":
                val = effect.get("value", 10) * equip_mult
                for stat in stats:
                    pet[stat] = int(pet.get(stat, 0)) + val
                    changes.append(f"+{val} {stat}")

            elif etype == "health_boost":
                val = effect.get("value", 5) * equip_mult
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

                    # Remove potion BEFORE apply_xp_change so the reload below
                    # doesn't re-add it back when we overwrite inventory.
                    count = potion_item.get("count", 1)
                    if count > 1:
                        potion_item["count"] = count - 1
                    else:
                        inventory.pop(potion_idx)
                    pet["inventory"] = inventory
                    await user_data_manager.save_pet_data(str(user_id), pet.get("name", "Pet"), pet)

                    # Now apply XP on the freshly-saved data
                    leveled_up, change_data = await LootCalculator.apply_xp_change(user_id, xp_gain, "potion_boost")

                    # Reload pet so the final save below doesn't clobber the XP
                    pet = await user_data_manager.get_pet_data_async(str(user_id))
                    # Mark inventory already saved so the block below is a no-op
                    potion_idx = -1

                    changes.append(f"+{xp_gain} XP")
                    if leveled_up and change_data:
                        new_level = change_data.get("new_level")
                        changes.append(f"LEVEL UP! {level} -> {new_level}")
                        for k, v in change_data.get("gains", {}).items():
                            if v > 0:
                                changes.append(f"+{v} {k}")

                except Exception as e:
                    logger.error(f"Error calculating XP boost: {e}")
                    changes.append("Error adding XP")
            
            else:
                return False, "Unknown potion effect."

            # Remove potion (decrement count) — skipped for xp_boost (already handled above)
            if potion_idx != -1 and potion_item is not None:
                count = potion_item.get("count", 1)
                if count > 1:
                    potion_item["count"] = count - 1
                else:
                    inventory.pop(potion_idx)

                pet["inventory"] = inventory
                await user_data_manager.save_pet_data(str(user_id), pet.get("name", "Pet"), pet)
            
            potion_emoji = emoji_mod.mention(potion_name) or "🧪"
            return True, f"{potion_emoji} Used **{potion_name}**! Gains: {', '.join(changes)}"
            
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

        Matching uses the same identity key as _consolidate_inventory so that reforged
        items and plain items are never merged into the wrong stack:
            (name, type, rarity, reforged, reforge_level)
        """
        if not item: return False, ""
        
        item_type    = item.get("type", "Material")
        item_name    = item.get("name", "Unknown")
        item_rarity  = item.get("rarity", "Common")
        item_reforged = bool(item.get("reforged", False))
        item_rl      = int(item.get("reforge_level", 0)) if item_reforged else 0
        limit = 99  # all items stack to 99
        
        # Find existing stack using the same key as _consolidate_inventory
        existing_item = None
        for inv_item in inventory:
            if (inv_item.get("name") == item_name
                    and inv_item.get("type") == item_type
                    and inv_item.get("rarity", "Common") == item_rarity
                    and bool(inv_item.get("reforged", False)) == item_reforged
                    and (int(inv_item.get("reforge_level", 0)) if item_reforged else 0) == item_rl):
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
            # Add to inventory — always return exactly 1 unit (equipment slots hold 1)
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
    async def equip_items(user_id: str, username: str,
                          material_names: Optional[str] = None,
                          gem_names: Optional[str] = None,
                          monster_names: Optional[str] = None,
                          helmet_name: Optional[str] = None,
                          armor_name: Optional[str] = None,
                          boots_name: Optional[str] = None,
                          ring_name: Optional[str] = None,
                          shield_name: Optional[str] = None,
                          weapon_name: Optional[str] = None,
                          reforged: bool = False,
                          reforge_level: int = 0) -> Tuple[bool, str]:
        """Equip items to the user's pet.

        Single slots (1 each): Helmet, Armor, Boots, Ring, Shield, Weapon
        Multi slots (up to 2 each): Gems, Monsters
        Single sub-slot: Material

        For ALL slots the invariant is:
          1. Snapshot the incoming item.
          2. Remove it from inventory FIRST.
          3. Swap it into the equipment slot (returning any displaced item to inventory).
        This prevents double-counting when the old and new items share the same name/type.
        """
        try:
            pet = await user_data_manager.get_pet_data_async(str(user_id))
            if not pet:
                return False, "You don't have a pet!"

            inventory = user_data_manager._consolidate_inventory(pet.get('inventory', []))
            # Keep pet['inventory'] pointing at the same list so that
            # _remove_item_from_inventory (which reads pet['inventory']) and
            # _return_item_to_inventory (which receives `inventory`) both
            # operate on the exact same object — preventing phantom duplicates.
            pet['inventory'] = inventory

            equipment = pet.setdefault('equipment', {})
            equipment.setdefault("Gems", [])
            equipment.setdefault("Monsters", [])

            msg_parts = []

            # ── Helper: equip a single-slot item ─────────────────────────────
            def _equip_single(slot_key: str, item_type: str, name: str) -> None:
                item_obj = LootCalculator._get_item_from_inventory(
                    pet, name, item_type,
                    reforged=reforged if reforged else None,
                    reforge_level=reforge_level if reforged else None
                )
                if not item_obj:
                    msg_parts.append(f"❌ **{name}** not found in inventory.")
                    return

                # Snapshot BEFORE touching inventory to avoid reference mutation.
                # Force count=1: equipment slots hold exactly one unit of an item.
                item_snapshot = {k: v for k, v in item_obj.items()}
                item_snapshot["count"] = 1

                # Remove new item from inventory FIRST — prevents double-counting when
                # old and new items share the same name/type
                ok, rmsg = LootCalculator._remove_item_from_inventory(pet, item_obj)
                if not ok:
                    msg_parts.append(f"❌ Could not remove **{name}** from inventory: {rmsg}")
                    return

                # Return old equipped item to inventory (safe — new item already removed)
                old = equipment.get(slot_key)
                if isinstance(old, list):
                    old = old[0] if old else None
                if isinstance(old, dict) and old.get('name'):
                    _, xmsg = LootCalculator._return_item_to_inventory(inventory, old, pet, int(user_id))
                    if xmsg:
                        msg_parts.append(xmsg)
                    msg_parts.append(f"📦 Unequipped old {slot_key}: **{old['name']}**")

                equipment[slot_key] = item_snapshot
                msg_parts.append(f"✅ Equipped **{name}** → {slot_key}")

            # ── Helper: equip a multi-slot item (Gems / Monsters) ────────────
            def _equip_multi(slot_key: str, item_type: str, name: str, max_slots: int) -> None:
                item_obj = LootCalculator._get_item_from_inventory(
                    pet, name, item_type,
                    reforged=reforged if reforged else None,
                    reforge_level=reforge_level if reforged else None
                )
                if not item_obj:
                    msg_parts.append(f"❌ **{name}** not found in inventory.")
                    return

                item_snapshot = {k: v for k, v in item_obj.items()}
                item_snapshot["count"] = 1  # equipment slots hold exactly one unit

                # Remove new item from inventory FIRST
                ok, rmsg = LootCalculator._remove_item_from_inventory(pet, item_obj)
                if not ok:
                    msg_parts.append(f"❌ Could not remove **{name}** from inventory: {rmsg}")
                    return

                # Add to slot, displacing oldest if full
                displaced = LootCalculator._manage_equipment_slot(pet, slot_key, item_snapshot, max_slots=max_slots)
                if displaced and isinstance(displaced, dict) and displaced.get('name'):
                    _, xmsg = LootCalculator._return_item_to_inventory(inventory, displaced, pet, int(user_id))
                    if xmsg:
                        msg_parts.append(xmsg)
                    msg_parts.append(f"📦 Unequipped old {slot_key[:-1] if slot_key.endswith('s') else slot_key}: **{displaced['name']}**")

            # ── Single-slot main gear ─────────────────────────────────────────
            if helmet_name:
                _equip_single('Helmet', 'Helmet', helmet_name)
            if armor_name:
                _equip_single('Armor', 'Armor', armor_name)
            if boots_name:
                _equip_single('Boots', 'Boots', boots_name)
            if ring_name:
                _equip_single('Ring', 'Ring', ring_name)
            if shield_name:
                _equip_single('Shield', 'Shield', shield_name)

            # ── Weapon (any weapon sub-type) ──────────────────────────────────
            if weapon_name:
                weapon_types = ['Dagger', 'Katana', 'Sword', 'Axe', 'Hammer', 'Bow']
                item_obj = None
                for wtype in weapon_types:
                    item_obj = LootCalculator._get_item_from_inventory(
                        pet, weapon_name, wtype,
                        reforged=reforged if reforged else None,
                        reforge_level=reforge_level if reforged else None
                    )
                    if item_obj:
                        break
                if not item_obj:
                    msg_parts.append(f"❌ Weapon **{weapon_name}** not found in inventory.")
                else:
                    weapon_snapshot = {k: v for k, v in item_obj.items()}
                    weapon_snapshot["count"] = 1  # equipment slots hold exactly one unit
                    ok, rmsg = LootCalculator._remove_item_from_inventory(pet, item_obj)
                    if not ok:
                        msg_parts.append(f"❌ Could not remove **{weapon_name}**: {rmsg}")
                    else:
                        old = equipment.get('Weapon')
                        if isinstance(old, list):
                            old = old[0] if old else None
                        if isinstance(old, dict) and old.get('name'):
                            _, xmsg = LootCalculator._return_item_to_inventory(inventory, old, pet, int(user_id))
                            if xmsg:
                                msg_parts.append(xmsg)
                            msg_parts.append(f"📦 Unequipped old Weapon: **{old['name']}**")
                        equipment['Weapon'] = weapon_snapshot
                        msg_parts.append(f"✅ Equipped **{weapon_name}** → Weapon")

            # ── Material (single slot) ────────────────────────────────────────
            if material_names:
                name = material_names.strip().split(',')[0].strip()
                _equip_single('Material', 'Material', name)

            # ── Gems (up to 2) ────────────────────────────────────────────────
            if gem_names:
                names = [n.strip() for n in gem_names.split(',') if n.strip()][:2]
                for gem_name in names:
                    _equip_multi('Gems', 'Gem', gem_name, max_slots=2)
                equipped_gems = [g['name'] for g in equipment.get('Gems', []) if isinstance(g, dict)]
                if equipped_gems:
                    msg_parts.append(f"✅ Equipped Gem(s): **{', '.join(equipped_gems)}**")

            # ── Monsters (up to 2) ────────────────────────────────────────────
            if monster_names:
                names = [n.strip() for n in monster_names.split(',') if n.strip()][:2]
                for mon_name in names:
                    _equip_multi('Monsters', 'Monster', mon_name, max_slots=2)
                equipped_mons = [m['name'] for m in equipment.get('Monsters', []) if isinstance(m, dict)]
                if equipped_mons:
                    msg_parts.append(f"✅ Equipped Monster(s): **{', '.join(equipped_mons)}**")

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
        Unequip items from a slot. Valid slots:
          Main: Helmet, Armor, Boots, Ring, Shield, Weapon
          Ring sub: Material, Gems, Monsters
          Legacy: Hat
        Unequipping Ring also clears Material, Gems, Monsters.
        """
        try:
            pet = await user_data_manager.get_pet_data_async(str(user_id))
            if not pet:
                return False, "You don't have a pet!"

            inventory = pet.get('inventory', [])
            inventory = user_data_manager._consolidate_inventory(inventory)
            equipment = pet.get('equipment', {})
            equipment.setdefault("Gems", [])
            equipment.setdefault("Monsters", [])

            SINGLE_SLOTS = {'Helmet', 'Armor', 'Boots', 'Ring', 'Shield', 'Weapon', 'Hat', 'Material'}
            LIST_SLOTS   = {'Gems', 'Monsters'}
            valid = SINGLE_SLOTS | LIST_SLOTS
            slot = slot_type.strip()
            # Normalise capitalisation
            slot_map = {s.lower(): s for s in valid}
            slot = slot_map.get(slot.lower(), slot)

            if slot not in valid:
                return False, f"Invalid slot '{slot}'. Valid: {', '.join(sorted(valid))}"

            items_removed = []
            xp_msgs = []

            def _unequip_single(key: str) -> None:
                item = equipment.get(key)
                if isinstance(item, list): item = item[0] if item else None
                if isinstance(item, dict) and item.get('name'):
                    _, msg = LootCalculator._return_item_to_inventory(inventory, item, pet, int(user_id))
                    if msg: xp_msgs.append(msg)
                    items_removed.append(item.get('name', key))
                    equipment.pop(key, None)

            def _unequip_list(key: str) -> None:
                items = equipment.get(key, [])
                if isinstance(items, dict): items = [items] if items.get('name') else []
                for item in items:
                    if isinstance(item, dict) and item.get('name'):
                        _, msg = LootCalculator._return_item_to_inventory(inventory, item, pet, int(user_id))
                        if msg: xp_msgs.append(msg)
                        items_removed.append(item.get('name', key))
                equipment[key] = []

            if slot in SINGLE_SLOTS:
                _unequip_single(slot)
                # Unequipping Ring also clears sub-slots
                if slot == 'Ring':
                    _unequip_single('Material')
                    _unequip_list('Gems')
                    _unequip_list('Monsters')
            else:
                _unequip_list(slot)

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
    def get_item_by_rarity(allowed_rarities: list, item_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Returns a random item filtered to the given rarity list.
        item_type: singular item type string (e.g. "Material", "Gem", "Ring", "Helmet", "Sword") or None for any.
        """
        data = LootCalculator._get_equipment_data()
        # Map singular type → JSON section key
        type_map = {
            "Material": "Materials",
            "Gem": "Gems",
            "Monster": "Monsters",
            "Potion": "Potions",
            "Hat": "Hats",
            "Ring": "Rings",
            "Helmet": "Helmets",
            "Armor": "Armor",
            "Boots": "Boots",
            "Shield": "Shields",
            "Dagger": "Daggers",
            "Katana": "Katanas",
            "Sword": "Swords",
            "Axe": "Axes",
            "Hammer": "Hammers",
            "Bow": "Bows",
        }
        if item_type:
            section = type_map.get(item_type, item_type + "s")
            pool = data.get(section, [])
        else:
            pool = []
            for section in ["Materials", "Gems", "Monsters", "Potions",
                            "Rings", "Helmets", "Armor", "Boots", "Shields",
                            "Daggers", "Katanas", "Swords", "Axes", "Hammers", "Bows"]:
                pool.extend(data.get(section, []))

        filtered = [i for i in pool if i.get("rarity") in allowed_rarities]
        # No silent fallback — if nothing matches the requested rarity, return None
        # so callers can handle it properly rather than getting wrong-rarity items.
        return random.choice(filtered) if filtered else None

    @staticmethod
    def get_key_loot(difficulty: str = "normal", bypass_chance: bool = False) -> List[Dict[str, Any]]:
        """
        Calculates key loot based on difficulty.
        All keys are equal — each has a ~75% independent chance to drop.
        Difficulty scales the base roll chance:
          Easy:   50% per key
          Normal: 65% per key
          Hard:   75% per key
        """
        diff = difficulty.lower()
        looted_keys = []

        if diff == "easy":
            chance = 0.50
        elif diff == "hard":
            chance = 0.75
        else:  # normal / average / medium
            chance = 0.65

        for key_name in ("Key1", "Key2", "Key3"):
            if random.random() < chance:
                looted_keys.append({
                    "name": key_name,
                    "type": "Key",
                    "rarity": "Rare",
                    "emoji_id": key_name
                })

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
    async def open_chest(user_id: int, chest_type: str, amount: int, selected_type: Optional[str] = None) -> tuple:
        """
        Opens a chest, deducts keys, and awards loot.
        chest_type: "chest1", "chest2", "chest3", "chest4"
        amount: Number of chests to open
        selected_type: For Chest 4 (Material, Gem, Monster, Potion,
                       Ring, Helmet, Armor, Boots, Shield,
                       Dagger, Katana, Sword, Axe, Hammer, Bow)
                       Hats are NOT available via the Loot Market.

        Chest loot tiers:
          chest1 → 1 Common or Uncommon item (no Hats)
          chest2 → 1 Rare item (no Hats)
          chest3 → 1 Epic item (no Hats)
          chest4 → 1 selected-type item (Common–Mythic) + 1 random item (Common–Mythic, no Hats)

        Returns (messages: List[str], awarded_items: List[Dict])
        """
        messages: List[str] = []
        awarded_items: List[dict] = []
        try:
            pet_data = await user_data_manager.get_pet_data_async(str(user_id))
            if not pet_data:
                return (["You don't have a pet!"], [])
            
            inventory = pet_data.get("inventory", [])
            # Ensure consolidated
            inventory = user_data_manager._consolidate_inventory(inventory)
            
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
                return (["Invalid Chest Type"], [])
                
            # Check Affordability
            inventory_counts = {}
            for item in inventory:
                if item.get("type") == "Key":
                    inventory_counts[item.get("name")] = item.get("count", 1)
            
            for key_name, required_amount in cost.items():
                if inventory_counts.get(key_name, 0) < required_amount:
                    return ([f"Not enough {key_name}! Need {required_amount}, have {inventory_counts.get(key_name, 0)}."], [])
            
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

            for _ in range(amount):
                if chest_type == "chest1":
                    item = LootCalculator.get_item_by_rarity(["Common", "Uncommon"])
                    if item: items_to_add.append(item)

                elif chest_type == "chest2":
                    item = LootCalculator.get_item_by_rarity(["Rare"])
                    if item: items_to_add.append(item)

                elif chest_type == "chest3":
                    item = LootCalculator.get_item_by_rarity(["Epic"])
                    if item: items_to_add.append(item)

                elif chest_type == "chest4":
                    # Guaranteed selected-type item: any rarity Common–Mythic
                    sel_item = LootCalculator.get_item_by_rarity(
                        ["Common", "Uncommon", "Rare", "Epic", "Mythic"],
                        item_type=selected_type
                    )
                    if sel_item: items_to_add.append(sel_item)
                    # Bonus random item: any rarity Common–Mythic, no Hats
                    bonus = LootCalculator.get_item_by_rarity(["Common", "Uncommon", "Rare", "Epic", "Mythic"])
                    if bonus: items_to_add.append(bonus)
            
            # Add items to inventory
            final_messages = []
            
            for item in items_to_add:
                i_type = item.get("type")
                i_name = item.get("name")
                
                limit = 99  # all items stack to 99
                
                existing = next((i for i in inventory if i.get("name") == i_name and i.get("type") == i_type), None)
                
                curr_count = existing.get("count", 0) if existing else 0
                add_count = item.get("count", 1)
                
                if curr_count + add_count > limit:
                     available = max(0, limit - curr_count)
                     excess = add_count - available
                     
                     if available > 0:
                         if existing:
                             existing["count"] = curr_count + available
                         else:
                             new_item = item.copy()
                             new_item["count"] = available
                             new_item["acquired_at"] = datetime.utcnow().isoformat()
                             inventory.append(new_item)
                         
                         awarded_item = item.copy()
                         awarded_item["count"] = available
                         awarded_items.append(awarded_item)
                         emoji = LootCalculator.get_pet_emoji(i_type, i_name)
                         stats = LootCalculator._format_item_stats(item)
                         final_messages.append(f"🎁 {emoji} **{i_name}** x{available}{stats}")

                     if excess > 0:
                         lvl = int(pet_data.get("level", 1))
                         xp_gain = lvl * 100 * excess
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
                    
                    awarded_item = item.copy()
                    awarded_item["count"] = add_count
                    awarded_items.append(awarded_item)
                    emoji = LootCalculator.get_pet_emoji(i_type, i_name)
                    stats = LootCalculator._format_item_stats(item)
                    final_messages.append(f"🎁 {emoji} **{i_name}** x{add_count}{stats}")

            pet_data["inventory"] = inventory
            await user_data_manager.save_pet_data(str(user_id), pet_data.get("name", "Pet"), pet_data)
            
            return (final_messages, awarded_items)

        except Exception as e:
            logger.error(f"Error opening chest: {e}")
            return ([f"Error: {e}"], [])

    @staticmethod
    def calculate_level_up_stats(pet_data: Dict[str, Any], old_level: int, new_level: int) -> Dict[str, int]:
        """
        Calculates and applies stat gains for level up.

        Formula: 3 × (1 + (level-1)//10) points per level gained.
          - Level   1-10:  3 pts/level
          - Level  11-20:  6 pts/level
          - Level  51-60: 18 pts/level
          - Level 100+:   30+ pts/level
        Matches add_pet_experience so both paths are consistent.
        """
        levels_gained = new_level - old_level
        if levels_gained <= 0:
            return {}

        # Total points = sum of scaling formula across each level gained
        total_points = sum(
            3 * (1 + ((lvl - 1) // 10))
            for lvl in range(old_level + 1, new_level + 1)
        )

        stats = ["ATT", "DEF", "INT", "DEX", "HAP", "ENE"]
        gains = {s: 0 for s in stats}

        # For large totals use fast batched distribution to avoid hanging
        BATCH_THRESHOLD = 5000

        if total_points <= BATCH_THRESHOLD:
            for _ in range(total_points):
                stat = random.choice(stats)
                pet_data[stat] = int(pet_data.get(stat, 0)) + 1
                gains[stat] += 1
        else:
            remaining = total_points
            for i, stat in enumerate(stats):
                if i == len(stats) - 1:
                    alloc = remaining
                else:
                    remaining_stats = len(stats) - i
                    mean = remaining / remaining_stats
                    variance = max(1, int(mean * 0.10))
                    alloc = max(0, min(remaining, int(mean) + random.randint(-variance, variance)))
                gains[stat] = alloc
                pet_data[stat] = int(pet_data.get(stat, 0)) + alloc
                remaining -= alloc
                if remaining <= 0:
                    break

        return gains

    @staticmethod
    def calculate_level_down_stats(pet_data: Dict[str, Any], old_level: int, new_level: int) -> Dict[str, int]:
        """
        Removes stat points when a pet levels down.

        Mirrors calculate_level_up_stats exactly: removes 3 × (1+(level-1)//10)
        per level lost so the total stat budget stays honest.
        Stats are floored at 1.
        Returns {stat: points_removed}.
        """
        levels_lost = old_level - new_level
        if levels_lost <= 0:
            return {}

        total_to_remove = sum(
            3 * (1 + ((lvl - 1) // 10))
            for lvl in range(new_level + 1, old_level + 1)
        )

        stats = ["ATT", "DEF", "INT", "DEX", "HAP", "ENE"]
        losses = {s: 0 for s in stats}

        BATCH_THRESHOLD = 5000

        if total_to_remove <= BATCH_THRESHOLD:
            remaining = total_to_remove
            attempts = 0
            max_attempts = total_to_remove * 10
            while remaining > 0 and attempts < max_attempts:
                attempts += 1
                stat = random.choice(stats)
                current = int(pet_data.get(stat, 1))
                if current > 1:
                    pet_data[stat] = current - 1
                    losses[stat] += 1
                    remaining -= 1
        else:
            remaining = total_to_remove
            for i, stat in enumerate(stats):
                if i == len(stats) - 1:
                    alloc = remaining
                else:
                    remaining_stats = len(stats) - i
                    mean = remaining / remaining_stats
                    variance = max(1, int(mean * 0.10))
                    alloc = max(0, min(remaining, int(mean) + random.randint(-variance, variance)))
                current = int(pet_data.get(stat, 1))
                actual_remove = min(alloc, max(0, current - 1))
                pet_data[stat] = current - actual_remove
                losses[stat] = actual_remove
                remaining -= alloc
                if remaining <= 0:
                    break

        return losses

    @staticmethod
    async def apply_xp_change(user_id: int, xp_amount: int, source: str = "unknown") -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Centralized XP Application Logic.
        Applies XP, handles level ups/downs, updates stats, and saves data.
        Returns (has_level_changed, change_data)

        Handles:
        - Massive XP gains (casino wins, race streaks) without hanging
        - Massive XP losses (mission gambles) without crashing
        - Level/XP desync (recomputes from total XP, not from stored level)
        - MAX_LEVEL cap (10,000)
        """
        MAX_LEVEL = 10000
        # Cap a single XP change to prevent integer overflow in DB / display.
        # 10^15 XP in one shot is already astronomical; anything beyond is a bug.
        XP_CHANGE_CAP = 10 ** 15

        try:
            pet_data = await user_data_manager.get_pet_data_async(str(user_id))
            if not pet_data:
                return False, None

            # --- Sanitise inputs ---
            try:
                xp_amount = int(xp_amount)
            except (TypeError, ValueError):
                xp_amount = 0

            # Clamp the change to prevent overflow
            xp_amount = max(-XP_CHANGE_CAP, min(XP_CHANGE_CAP, xp_amount))

            # --- Reconstruct true total XP from stored level + experience ---
            # We always recompute from (level_base + experience) so that any
            # prior desync between level and experience is corrected here.
            try:
                stored_level = max(1, int(pet_data.get("level", 1)))
                stored_xp   = max(0, int(pet_data.get("experience", 0)))
            except (TypeError, ValueError):
                stored_level = 1
                stored_xp   = 0

            # --- Apply ability XP multiplier (only for positive gains) ---
            if xp_amount > 0:
                try:
                    from Systems.Pets.Logic.ability_tree import get_ability_effect
                    # Normalize source string to what the ability tree expects.
                    # Sources not in this map are passed through as-is (e.g. "npc_battle",
                    # "pvp_battle", "boss_battle", "mission", "play", "quest", "survive").
                    _XP_SOURCE_NORMALIZE = {
                        "training":         "train",
                        "ss_participation": "survive",
                        "ss_win":           "survive",
                        "pvp":              "pvp_battle",
                        "npc":              "npc_battle",
                        "boss":             "boss_battle",
                        "battle":           "npc_battle",   # generic battle → npc_battle
                    }
                    normalized_source = _XP_SOURCE_NORMALIZE.get(source, source)
                    xp_mult = get_ability_effect(pet_data, "xp_multiplier", source=normalized_source)
                    if xp_mult != 1.0:
                        xp_amount = int(xp_amount * xp_mult)
                        xp_amount = max(-XP_CHANGE_CAP, min(XP_CHANGE_CAP, xp_amount))
                except Exception:
                    pass  # ability tree import failure is non-fatal

            # --- Apply casino win bonus (only for positive gains from casino wins) ---
            if xp_amount > 0:
                try:
                    from Systems.Pets.Logic.ability_tree import get_ability_effect
                    # Map win source strings to the game name the ability tree expects.
                    # All casino win sources are handled here centrally — do NOT apply
                    # casino_xp_gain_mult locally in the game files to avoid double-application.
                    _WIN_SOURCE_TO_GAME = {
                        "slots_win":          "slots",
                        "blackjack_win":      "blackjack",
                        "holdem_win":         "holdem",
                        "holdem_cashout":     "holdem",
                        "craps_win":          "craps",
                        "wheel_of_pets_win":  "wheel_of_pets",
                        "race_win":           "races",
                        "scratch_win":        "scratch_cards",
                        "powerball_win":      "powerball",
                        "coinflip_win":       "coinflip",
                        "rps_win":            "rps",
                        "rps_pvp_win":        "rps",
                        "keno_win":           "keno",
                    }
                    game_name = _WIN_SOURCE_TO_GAME.get(source)
                    if game_name:
                        win_mult = get_ability_effect(pet_data, "casino_xp_gain_mult", game=game_name)
                        if win_mult != 1.0:
                            xp_amount = int(xp_amount * win_mult)
                            xp_amount = max(-XP_CHANGE_CAP, min(XP_CHANGE_CAP, xp_amount))
                except Exception:
                    pass  # ability tree import failure is non-fatal

            # --- Apply casino XP loss reduction (only for negative losses) ---
            if xp_amount < 0:
                try:
                    from Systems.Pets.Logic.ability_tree import get_ability_effect
                    # Map bet/loss source strings to the game name the ability tree expects.
                    # All casino loss sources are handled here centrally — do NOT apply
                    # casino_xp_loss_reduction locally in the game files to avoid double-application.
                    # NOTE: craps uses a separate refund pattern (craps_loss_reduction source)
                    # so craps_bet is intentionally NOT listed here — the bet deduction is the
                    # full amount (goes to pot), and the refund is issued separately.
                    _LOSS_SOURCE_TO_GAME = {
                        "slots_bet":          "slots",
                        "blackjack_bet":      "blackjack",
                        "blackjack_loss":     "blackjack",
                        "blackjack_double":   "blackjack",
                        "blackjack_split":    "blackjack",
                        "holdem_buyin":       "holdem",
                        "holdem_rebuy":       "holdem",
                        "wheel_of_pets_bet":  "wheel_of_pets",
                        "scratch_bet":        "scratch_cards",
                        "powerball_ticket":   "powerball",
                        "race_bet":           "races",
                        "race_loss":          "races",
                        "coinflip_bet":       "coinflip",
                        "rps_bet":            "rps",
                        "keno_bet":           "keno",
                    }
                    game_name = _LOSS_SOURCE_TO_GAME.get(source)  # None if not a casino loss
                    if game_name:
                        xp_loss_reduction = get_ability_effect(pet_data, "casino_xp_loss_reduction", game=game_name)
                        if xp_loss_reduction > 0:
                            xp_amount = int(xp_amount * (1.0 - xp_loss_reduction))
                            xp_amount = max(-XP_CHANGE_CAP, min(XP_CHANGE_CAP, xp_amount))
                except Exception:
                    pass  # ability tree import failure is non-fatal

            total_xp_for_stored_level = LootCalculator.get_total_experience_for_level(stored_level)
            current_total_xp = total_xp_for_stored_level + stored_xp

            # Apply the change, floor at 0
            new_total_xp = max(0, current_total_xp + xp_amount)

            # Recompute level (O(log n), capped at MAX_LEVEL)
            _, new_level, new_xp = LootCalculator.recompute_level_from_total_xp(pet_data, new_total_xp)
            new_level = min(new_level, MAX_LEVEL)

            old_level = stored_level

            pet_data["level"]      = new_level
            pet_data["experience"] = new_xp

            # --- Track XP source ---
            if "xp_sources" not in pet_data:
                pet_data["xp_sources"] = {}
            current_source_xp = pet_data["xp_sources"].get(source, 0)
            try:
                current_source_xp = int(current_source_xp)
            except (TypeError, ValueError):
                current_source_xp = 0
            pet_data["xp_sources"][source] = current_source_xp + xp_amount
            logger.info(f"Updated xp_sources for pet {pet_data.get('name')}: source={source} delta={xp_amount}")

            # Update total_xp_earned only for positive gains
            if xp_amount > 0:
                try:
                    prev = int(pet_data.get("total_xp_earned", 0))
                except (TypeError, ValueError):
                    prev = 0
                pet_data["total_xp_earned"] = prev + xp_amount

            change_data: Dict[str, Any] = {
                "old_level":    old_level,
                "new_level":    new_level,
                "xp_added":     xp_amount,
                "source":       source,
                "new_total_xp": new_total_xp,
                "gains":        {}
            }

            has_changed = new_level != old_level

            if has_changed:
                if new_level > old_level:
                    # Level Up — apply stat gains (fast-path for large jumps)
                    gains = LootCalculator.calculate_level_up_stats(pet_data, old_level, new_level)
                    change_data["gains"] = gains
                    
                    # NOTE: Ability points are NOT auto-awarded. They must be purchased with levels.
                    change_data["ability_points_gained"] = 0
                    
                elif new_level < old_level:
                    # Level Down — remove the stat points that were earned from
                    # those levels (5 pts/level, randomly redistributed so the
                    # total removed matches exactly but the per-stat split varies).
                    losses = LootCalculator.calculate_level_down_stats(pet_data, old_level, new_level)
                    change_data["lost_xp"] = xp_amount
                    change_data["losses"] = losses

            await user_data_manager.save_pet_data(str(user_id), pet_data.get("name", "Pet"), pet_data)
            return has_changed, change_data if has_changed else None

        except Exception as e:
            logger.error(f"Error applying XP change for user {user_id}: {e}", exc_info=True)
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
        if source == "pvp" or source == "pvp_battle":
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
                result["level_change"] = {
                    "old_level": old_lvl,
                    "new_level": new_lvl,
                    "gains": change_data.get("gains", {}),
                }
                result["messages"].append(f"📈 Gained **{xp_amount} XP** and Leveled Up to **{new_lvl}**!")
                result["level_up_embed"] = await LootCalculator.create_level_up_embed(pet_data, old_lvl, new_lvl, source)
            else:
                result["leveled_down"] = True
                result["level_change"] = {
                    "old_level": old_lvl,
                    "new_level": new_lvl,
                    "losses": change_data.get("losses", {}),
                }
                result["messages"].append(f"📉 Lost XP... dropped to Level **{new_lvl}**.")
                result["level_down_embed"] = await LootCalculator.create_level_down_embed(pet_data, old_lvl, new_lvl, source, change_data.get("lost_xp", 0), change_data.get("losses"))
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
        items_to_add: List[Dict[str, Any]] = []

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

   
    @staticmethod
    def generate_hostile_pet(player_pet: dict, difficulty: str) -> dict:
        """
        Generates a hostile pet (boss) for quests.
        The boss has high HP but lower ATT and DEF than the player's pet.
        """
        difficulty_multipliers = {
            "Apprentice": 0.8,
            "Journeyman": 1.0,
            "Senior": 1.2
        }
        multiplier = difficulty_multipliers.get(difficulty, 1.0)

        player_stats = LootCalculator._stats_calculator().calculate_pet_stats(player_pet)

        # Boss has high health, so we boost HAP and ENE
        boss_hap = int(player_stats.get('HAP', 10) * 1.5 * multiplier)
        boss_ene = int(player_stats.get('ENE', 10) * 1.5 * multiplier)

        # Boss has lower attack and defense
        boss_att = int(player_stats.get('ATT', 10) * 0.8 * multiplier)
        boss_def = int(player_stats.get('DEF', 10) * 0.8 * multiplier)
        
        # Other stats can be based on player's stats
        boss_int = int(player_stats.get('INT', 10) * multiplier)
        boss_dex = int(player_stats.get('DEX', 10) * multiplier)

        # Generate a random species and name
        try:
            base_data = user_data_manager.file_manager.get_data("base")
            elements = list(base_data.get("element_bases", {"basic": ["Basic"]}).keys())
            categories = list(base_data.get("category_bases", {"land": ["Creature"]}).keys())
            
            boss_element = random.choice(elements)
            boss_category = random.choice(categories)

            element_adjective = random.choice(base_data["element_bases"].get(boss_element, ["Mysterious"]))
            category_noun = random.choice(base_data["category_bases"].get(boss_category, ["Creature"]))

            boss_species = f"{element_adjective} {category_noun}"
            boss_name = f"Wild {boss_species}"
        except Exception:
            boss_species = "Hostile Pet"
            boss_name = "Hostile Pet"
            boss_element = "basic"
            boss_category = "land"

        boss_pet = {
            "species": boss_species,
            "name": boss_name,
            "level": player_pet.get("level", 1),
            "ATT": boss_att,
            "DEF": boss_def,
            "INT": boss_int,
            "DEX": boss_dex,
            "HAP": boss_hap,
            "ENE": boss_ene,
            "max_health": LootCalculator._stats_calculator().calculate_max_health({
                "ATT": boss_att, "DEF": boss_def, "INT": boss_int, "DEX": boss_dex,
                "HAP": boss_hap, "ENE": boss_ene, "level": player_pet.get("level", 1)
            }),
            "hp": LootCalculator._stats_calculator().calculate_max_health({
                "ATT": boss_att, "DEF": boss_def, "INT": boss_int, "DEX": boss_dex,
                "HAP": boss_hap, "ENE": boss_ene, "level": player_pet.get("level", 1)
            }),
            "equipment": {},
            "element": boss_element,
            "category": boss_category,
        }
        return boss_pet

