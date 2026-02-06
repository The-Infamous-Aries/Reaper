import asyncio
import logging
import random
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any, Union

import discord
from discord.ext import commands
from discord import ui

from Systems.Functions.user_data_manager import user_data_manager
from Systems.Functions import emoji as emoji_mod
from Systems.Functions.optimal_file_manager import OptimalFileManager
from Systems.Pets.Logic.pet_brain import DamageCalculator, LootCalculator, StatsCalculator

ELEMENT_EFFECTIVENESS: Dict[str, Dict[str, float]] = DamageCalculator.ELEMENT_EFFECTIVENESS
CATEGORY_ADVANTAGES: Dict[str, Dict[str, float]] = DamageCalculator.CATEGORY_ADVANTAGES
ELEMENTS = list(ELEMENT_EFFECTIVENESS.keys())
CATEGORIES = list(CATEGORY_ADVANTAGES.keys())

file_manager = OptimalFileManager()

# Load base data
_BASE_DATA = file_manager.get_data("base")
ELEMENT_BASES: Dict[str, List[str]] = _BASE_DATA.get("element_bases", {})
CATEGORY_BASES: Dict[str, List[str]] = _BASE_DATA.get("category_bases", {})
SPECIES_NAME_PARTS: Dict[str, List[str]] = _BASE_DATA.get("pet_bases", {})

# Load info data
_INFO_DATA = file_manager.get_data("info")
if not _INFO_DATA:
    _INFO_DATA = {"Pets": {}}

PETS: Dict[str, Dict[str, int]] = {}
DESCRIPTIONS: Dict[str, str] = {}
PETS_COMBINED: Dict[str, Dict[str, Any]] = {}

for _species, _data in _INFO_DATA.get("Pets", {}).items():
    PETS[_species] = _data.get("Stats", {})
    DESCRIPTIONS[_species] = _data.get("Descriptions", "")
    PETS_COMBINED[_species] = {
        **PETS[_species],
        "specializations": _data.get("Spec", []),
        "description": DESCRIPTIONS[_species]
    }

logger = logging.getLogger('pets_system')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

LEVEL_THRESHOLDS = {}

async def add_experience(user_id: int, amount: int, source: str = "battle", equipment_stats: Optional[Dict[str, int]] = None) -> Tuple[bool, Optional[Dict[str, Any]]]:
    try:
        # Validate inputs
        if not isinstance(user_id, (int, str)):
            return False, None
        if not isinstance(amount, (int, float)):
            return False, None
        if not isinstance(source, str) or not source.strip():
            return False, None

        return await LootCalculator.apply_xp_change(int(user_id), int(amount), source)
    except Exception as e:
        logger.error(f"Error in add_experience: {e}")
        return False, None

async def send_level_down_embed(user_id: int, old_level: int, new_level: int, source: str = "mission", channel=None, lost_xp: int = 0) -> None:
    pet = await user_data_manager.get_pet_data_async(str(user_id))
    if not pet:
        return
    embed = await LootCalculator.create_level_down_embed(pet, old_level, new_level, source, lost_xp)
    try:
        if channel:
            await channel.send(embed=embed)
    except Exception:
        pass

async def send_level_up_embed(user_id: int, level_gains: Dict[str, Any], channel=None) -> None:
    pet = await user_data_manager.get_pet_data_async(str(user_id))
    if not pet:
        return
    
    old_level = level_gains.get('old_level', 1)
    new_level = level_gains.get('new_level', 1)
    source = level_gains.get('source', 'battle')
    
    embed = await LootCalculator.create_level_up_embed(pet, old_level, new_level, source)
    try:
        if channel:
            await channel.send(embed=embed)
    except Exception:
        pass

class PetSystem:
    """Main pet system class with optimized performance and resource management"""
    
    def __init__(self, bot):
        self.bot = bot
        self._data_loaded = asyncio.Event()
        self._load_task = None
        self._shutdown = False
        self._load_task = asyncio.create_task(self._preload_data())
        self._cooldowns = {}
        self.mission_data = self._load_mission_data()

    def _load_mission_data(self) -> Dict:
        try:
            data = file_manager.get_data("mission")
            if not data:
                logger.warning("Mission data returned empty from file_manager")
            return data
        except Exception as e:
            logger.error(f"Failed to load mission data: {e}")
            return {}

    def _is_command_on_cooldown(self, command: str, user_id: int) -> Tuple[bool, int]:
        now = datetime.utcnow()
        if command not in self._cooldowns:
            self._cooldowns[command] = {}
        
        # Cooldown durations in seconds
        durations = {
            'mission': 300,  # 5 minutes
            'train': 60,     # 1 minute
        }
        duration = durations.get(command, 0)
        
        if user_id in self._cooldowns[command]:
            last_time = self._cooldowns[command][user_id]
            elapsed = (now - last_time).total_seconds()
            if elapsed < duration:
                return True, int(duration - elapsed)

        return False, 0

    def set_command_cooldown(self, command: str, user_id: int):
        if command not in self._cooldowns:
            self._cooldowns[command] = {}
        self._cooldowns[command][user_id] = datetime.utcnow()

    def get_element_style(self, element: str) -> Tuple[int, str]:
        """Get element-specific styling"""
        color_map = {
            'basic': 0x808080,
            'fire': 0xFF4500,
            'water': 0x1E90FF,
            'electric': 0xFFD700,
            'ice': 0x87CEEB,
            'plant': 0x228B22,
            'rock': 0x8B4513,
            'air': 0xADD8E6,
            'magic': 0x4B0082,
            'holy': 0xEEE8AA,
            'necro': 0x800080,
            'psychic': 0x9932CC,
            'fighting': 0xCD5C5C,
        }
        return color_map.get(element, 0x808080), LootCalculator.get_pet_emoji("Elements", element) or '⚡'
        
    def _generate_pet_name(self, species_key: str, element1: str, category: str, element2: Optional[str] = None) -> str:
        parts = SPECIES_NAME_PARTS.get(species_key, [species_key])
        cat_bases = CATEGORY_BASES.get(str(category).lower(), [])
        elem1_bases = ELEMENT_BASES.get(str(element1).lower(), [])
        elem2_bases = ELEMENT_BASES.get(str(element2).lower(), []) if element2 else []
        cw = random.choice(cat_bases) if cat_bases else str(category).title()
        ew1 = random.choice(elem1_bases) if elem1_bases else str(element1).title()
        ew2 = random.choice(elem2_bases) if elem2_bases else None
        pw = random.choice(parts)
        if ew2:
            return f"{cw}{ew1}{ew2}{pw}"
        return f"{cw}{ew1}{pw}"

    async def _preload_data(self) -> None:
        try:
            self._data_loaded.set()
        except Exception:
            pass

    async def create_pet(self, user_id: int, category: str, species: str, element: Optional[str] = None, element2: Optional[str] = None) -> Dict[str, Any]:
        """Create a new pet using category/species base stats and element."""
        category_key = str(category).lower()
        species_name = species.strip()
        
        # Find species key case-insensitively
        species_key = None
        for k in PETS_COMBINED.keys():
            if k.lower() == species_name.lower():
                species_key = k
                break
        
        if not species_key:
            raise ValueError(f"Invalid species '{species}' for category '{category}'")
            
        base = PETS_COMBINED[species_key]
        
        # Determine elements
        # Primary element: use provided, or base default, or fire
        chosen_element = (element or base.get("element", "fire")).lower()
        if chosen_element not in ELEMENTS:
             # If provided element is invalid, fall back to base
             chosen_element = base.get("element", "fire").lower()
             
        # Secondary element: use provided if valid
        chosen_element2 = None
        if element2:
            e2 = str(element2).lower()
            if e2 in ELEMENTS and e2 != "basic" and e2 != chosen_element:
                chosen_element2 = e2

        # Base stats
        att = int(base["ATT"])
        deff = int(base["DEF"])
        ene = int(base["ENE"])
        hap = int(base["HAP"])
        intel = int(base["INT"])
        dex = int(base["DEX"])
        
        # Computed stats
        computed_attack = StatsCalculator.calculate_computed_attack(att, dex)
        computed_defense = StatsCalculator.calculate_computed_defense(deff, intel)
        
        computed_health = DamageCalculator.calculate_pet_health(hap, ene)

        # Name generation
        pet_name = self._generate_pet_name(species_key, chosen_element, category_key, chosen_element2)

        pet_data = {
            "name": pet_name,
            "category": category_key,
            "species": species_key,
            "element": chosen_element,
            "level": 1,
            "experience": 0,
            "ATT": att,
            "DEF": deff,
            "INT": intel,
            "DEX": dex,
            "HAP": hap,
            "ENE": ene,
            "attack": computed_attack,
            "defense": computed_defense,
            "max_health": computed_health,
            "health": computed_health,
            "created_at": datetime.utcnow().isoformat(),
            "specializations": base.get("specializations", []),
            "inventory": [],
            "equipment": {}
        }
        
        if chosen_element2:
            pet_data["element2"] = chosen_element2
            
        # Save via UDM - it handles migration and defaults
        await user_data_manager.save_pet_data(str(user_id), f"User_{user_id}", pet_data)
        
        # Return the full pet data (re-fetch to get defaults)
        return await user_data_manager.get_pet_data_async(str(user_id))
    


    async def get_user_pet(self, user_id: int, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """Get user's pet data, possibly cached"""
        # For now, we just fetch from UDM directly as it handles some caching/persistence
        # In a more advanced version, we could add a memory cache here
        return await user_data_manager.get_pet_data_async(str(user_id))

    async def process_adoption(self, user_id: int, user_name: str, category: str, species_input: str, element1: str, element2: str) -> Dict[str, Any]:
        """
        Process pet adoption: validate input, check existing, create pet.
        Returns a dict with 'success': bool, 'message': str, 'embed': Optional[discord.Embed]
        """
        cat = category or "land"
        e1 = element1 or "fire"
        e2 = element2 or "basic"
        raw = str(species_input).strip()
        all_species = list(PETS_COMBINED.keys())
        chosen_species = None
        
        if raw.isdigit():
            idx = max(1, min(int(raw), len(all_species)))
            chosen_species = all_species[idx - 1]
        else:
            for s in all_species:
                if s.lower() == raw.lower():
                    chosen_species = s
                    break
                    
        if not chosen_species:
            return {"success": False, "message": "❌ Invalid pet name or number."}

        existing = await self.get_user_pet(user_id)
        if existing:
            return {"success": False, "message": "👍 You already have a digital pet! Use `/pet` to check on them."}

        try:
            pet_data = await self.create_pet(user_id, cat, chosen_species, e1, (e2 if str(e1).lower() == "basic" else None))
        except Exception as e:
            logger.error(f"Adoption failed: {e}")
            return {"success": False, "message": "❌ Adoption failed. Please check your selections."}

        # Create success embed
        species_emoji = emoji_mod.mention(chosen_species) or ""
        embed = discord.Embed(
            title=f"{species_emoji} Adopted!",
            description=(
                f"You've adopted **{pet_data['name']}**\n"
                f"{LootCalculator.get_pet_emoji('Pet Type', pet_data['category'])} {pet_data['category'].title()} • "
                f"{LootCalculator.get_pet_emoji('Elements', pet_data['element'])} {pet_data['element'].title()}"
                + (f" • {LootCalculator.get_pet_emoji('Elements', e2)} {str(e2).title()}" if str(e1).lower() == "basic" else "")
                + f"\nLevel {pet_data['level']}"
            ),
            color=discord.Color.blurple()
        )
        return {"success": True, "message": "Adopted successfully!", "embed": embed}

    def create_pet_list_embed(self, page: int, per_page: int = 10) -> discord.Embed:
        """Create an embed listing available pets"""
        species_list = list(PETS_COMBINED.keys())
        total = len(species_list)
        start = page * per_page
        end = min(total, start + per_page)
        
        embed = discord.Embed(
            title=f"{emoji_mod.mention('PetShop') or '🛍️'} Pets ({start+1}-{end} of {total})",
            color=discord.Color.gold()
        )
        
        for idx in range(start, end):
            name = species_list[idx]
            data = PETS_COMBINED.get(name, {})
            em = emoji_mod.mention(name) or "🐾"
            stats = f"ATT {data.get('ATT',0)} | DEF {data.get('DEF',0)} | INT {data.get('INT',0)} | DEX {data.get('DEX',0)} | HAP {data.get('HAP',0)} | ENE {data.get('ENE',0)}"
            desc = str(data.get('description', '') or '')
            embed.add_field(name=f"{idx+1}. {em} {name}", value=f"{stats}\n{desc}", inline=False)
            
        return embed

    async def create_pet_status_embed(self, user_id: int, pet_data: Optional[Dict[str, Any]] = None) -> discord.Embed:
        """Create the main pet status embed"""
        if not pet_data:
            pet_data = await self.get_user_pet(user_id)
        
        pet = pet_data
        if not pet:
            return discord.Embed(title="Error", description="Pet not found!", color=discord.Color.red())
        
        element = str(pet.get('element', 'unknown')).lower()
        category = str(pet.get('category', 'unknown')).lower()
        embed_color, _ = self.get_element_style(element)
        
        species_emoji = LootCalculator.get_pet_emoji("Pets", pet.get('species', ''))
        e2 = str(pet.get('element2') or "").lower()
        
        type_emoji = LootCalculator.get_pet_emoji("Pet Type", category)
        el_emoji = LootCalculator.get_pet_emoji("Elements", element)
        e2_emoji = LootCalculator.get_pet_emoji("Elements", e2) if e2 else ""
        
        title_str = f"{type_emoji}{el_emoji}{e2_emoji}{species_emoji} {pet['name']} - Level {pet['level']}"
        
        desc_parts = [category.title(), element.title()]
        if e2:
            desc_parts.append(e2.title())
            
        embed = discord.Embed(
            title=title_str,
            description=" • ".join(desc_parts),
            color=embed_color
        )
        
        totals = StatsCalculator.calculate_pet_stats(pet)
        
        # Add fields
        created = datetime.fromisoformat(pet["created_at"])
        embed.add_field(name="🗓️ Created", value=created.strftime("%m/%d/%y at %I:%M %p"), inline=True)
        
        stats = LootCalculator.get_pet_stat_emojis()
        att_e, def_e, int_e, dex_e, hap_e, ene_e = stats['ATT'], stats['DEF'], stats['INT'], stats['DEX'], stats['HAP'], stats['ENE']
        
        # Get specs for bolding
        specs = LootCalculator._get_pet_specs(pet) or []
        def fmt_stat(name):
            return f"**{name}**" if name in specs else name
        
        embed.add_field(name="⚔️ Fighting", value=f"{att_e} {fmt_stat('ATT')} {totals['ATT']} | {def_e} {fmt_stat('DEF')} {totals['DEF']}", inline=True)
        embed.add_field(name="🧪 Usage", value=f"{int_e} {fmt_stat('INT')} {totals['INT']} | {dex_e} {fmt_stat('DEX')} {totals['DEX']}", inline=True)
        embed.add_field(name="❤️ Life", value=f"{hap_e} {fmt_stat('HAP')} {totals['HAP']} | {ene_e} {fmt_stat('ENE')} {totals['ENE']}", inline=True)
        
        threshold = LootCalculator.get_next_level_xp(pet['level'])
        progress = min(pet['experience'] / threshold, 1.0) if threshold > 0 else 0
        filled_length = int(10 * progress)
        
        # Element cycling for filled bar
        e1_char = LootCalculator.get_pet_emoji("Elements", element) or '⚡'
        e2_char = LootCalculator.get_pet_emoji("Elements", e2) if e2 else None
        
        filled_bar = ""
        for i in range(filled_length):
            if e2_char:
                filled_bar += e1_char if i % 2 == 0 else e2_char
            else:
                filled_bar += e1_char
                
        # XP emoji for unfilled bar
        unfilled_char = LootCalculator.get_pet_emoji("Pet Helpers", "XP") or '⚫'
        bar = filled_bar + unfilled_char * (10 - filled_length)
        
        embed.add_field(name="📊 Level Progress", value=f"**Level {pet['level']}** - {bar} {pet['experience']}/{threshold} XP", inline=False)

        equipment = pet.get('equipment', {})
        seat = LootCalculator.get_pet_emoji("Pet Helpers", "Seat") or "🔳"
        
        def get_equip_emoji(item):
            if not item or not isinstance(item, dict): return seat
            name = item.get('name')
            if not name: return seat
            return LootCalculator.get_pet_emoji("Pet Equipment", name) or seat

        gems = equipment.get('Gems', [])
        if isinstance(gems, dict): gems = [gems]
        elif not isinstance(gems, list): gems = []
        
        mons = equipment.get('Monsters', [])
        if isinstance(mons, dict): mons = [mons]
        elif not isinstance(mons, list): mons = []
        
        mat = equipment.get('Material')
        hat = equipment.get('Hat')

        g1 = gems[0] if len(gems) > 0 else None
        g2 = gems[1] if len(gems) > 1 else None
        m1 = mons[0] if len(mons) > 0 else None
        m2 = mons[1] if len(mons) > 1 else None
        
        hat_str = f"{get_equip_emoji(hat)}\n" if hat else ""
        collar_str = f"{get_equip_emoji(g1)}{get_equip_emoji(m1)}{get_equip_emoji(mat)}{get_equip_emoji(m2)}{get_equip_emoji(g2)}"
        embed.add_field(name="Equipment", value=f"{hat_str}{collar_str}", inline=False)

        return embed

    async def create_inventory_embed(self, user_id: int, pet_data: Optional[Dict[str, Any]] = None) -> discord.Embed:
        """Create inventory embed with categorized items"""
        if not pet_data:
            pet_data = await self.get_user_pet(user_id)
        
        pet = pet_data
        if not pet:
            return discord.Embed(title="❌ No Pet Found", description="You don't have a pet yet!", color=discord.Color.red())

        element = str(pet.get('element', 'basic')).lower()
        embed_color, _ = self.get_element_style(element)
        
        inv_emoji = LootCalculator.get_pet_emoji("Pet Helpers", "Inventory") or "🎒"
        embed = discord.Embed(
            title=f"{inv_emoji} {pet['name']}'s Inventory",
            description=f"**Level {pet['level']}** {pet.get('species', 'Pet')} • {pet.get('category', '').title()}",
            color=discord.Color(embed_color)
        )
        
        inventory = pet.get('inventory', [])
        
        # Group items
        item_counts, item_data = LootCalculator.group_inventory_items(inventory)

        # Build fields
        emoji_map = {"Material": "🪵", "Gem": "💎", "Monster": "👹", "Potion": "🧪", "Hat": "🧢", "Key": "🗝️", "Chest": "📦"}
        
        for cat in ["Hat", "Potion", "Material", "Gem", "Monster", "Key", "Chest"]:
            if cat not in item_counts or not item_counts[cat]:
                continue
                
            lines = []
            for name, count in item_counts[cat].most_common():
                item = item_data[cat][name]
                
                # Format: {Emoji} {Name} {Stats} {Count}
                em_id = item.get('emoji_id')
                em = emoji_mod.get(em_id) or emoji_map.get(cat, "❓")
                stats = LootCalculator._format_item_stats(item)
                
                line = f"{em} **{name}**{stats}"
                if count > 1:
                    line += f" x{count}"
                lines.append(line)
            
            embed.add_field(name=f"{emoji_map.get(cat, '❓')} {cat}s", value="\n".join(lines), inline=False)
            
        if not inventory:
            embed.description += "\n\n*Inventory is empty!*"
            
        return embed

    async def create_pet_breakdown_embed(self, user_id: int, pet_data: Optional[Dict[str, Any]] = None) -> discord.Embed:
        """Detailed stats breakdown"""
        if not pet_data:
            pet_data = await self.get_user_pet(user_id)
        
        pet = pet_data
        totals = StatsCalculator.calculate_pet_stats(pet)
        
        embed = discord.Embed(
            title=f"📊 Stats Breakdown - {pet['name']}",
            color=discord.Color.blue()
        )
        
        # Base stats
        base_stats = (
            f"ATT: {pet.get('ATT', 0)}\n"
            f"DEF: {pet.get('DEF', 0)}\n"
            f"INT: {pet.get('INT', 0)}\n"
            f"DEX: {pet.get('DEX', 0)}\n"
            f"HAP: {pet.get('HAP', 0)}\n"
            f"ENE: {pet.get('ENE', 0)}"
        )
        embed.add_field(name="Base Stats", value=base_stats, inline=True)
        
        # Equipment Bonuses
        equip_bonuses = StatsCalculator._calculate_equipment_bonuses(pet)
        equip_str = ""
        for stat, val in equip_bonuses.items():
            if val > 0:
                equip_str += f"{stat}: +{val}\n"
        
        if not equip_str:
            equip_str = "None"
            
        embed.add_field(name="Equipment Bonuses", value=equip_str, inline=True)
        
        # Computed
        comp_str = (
            f"Attack Power: {totals['attack']}\n"
            f"Defense Power: {totals['defense']}\n"
            f"Max Health: {totals['max_health']}"
        )
        embed.add_field(name="Combat Stats", value=comp_str, inline=False)
        
        return embed

    async def create_pet_casino_embed(self, user_id: int, pet_data: Optional[Dict[str, Any]] = None) -> discord.Embed:
        """Casino stats embed"""
        if not pet_data:
            pet_data = await self.get_user_pet(user_id)
            
        stats = pet_data.get("casino_stats", {})
        
        embed = discord.Embed(
            title=f"🎰 Casino Stats - {pet_data['name']}",
            color=discord.Color.gold()
        )
        
        slots = stats.get("slots", {})
        spins = slots.get("spins", 0)
        wins = slots.get("wins", 0)
        net = slots.get("net_xp", 0)
        
        embed.add_field(name="Slots", value=f"Spins: {spins}\nWins: {wins}\nNet XP: {net:+}", inline=False)
        
        return embed

    async def train_pet(self, user_id: int, difficulty: str) -> Tuple[bool, str]:
        """Train pet for XP"""
        pet = await self.get_user_pet(user_id)
        if not pet:
            return False, "You don't have a pet!"
            
        xp_gain = 50
        if difficulty == "Average": xp_gain = 100
        elif difficulty == "Hard": xp_gain = 200
        
        added, lvl_up = await add_experience(user_id, xp_gain, "training")
        
        msg = f"🏋️ Trained hard! Gained {xp_gain} XP."
        if lvl_up:
            await send_level_up_embed(user_id, lvl_up)
            msg += f"\n🎉 Level Up! Now level {lvl_up['new_level']}!"
            
        return True, msg

    async def perform_mission(self, user_id: int, difficulty: str, gamble_xp: Optional[int] = None) -> Dict[str, Any]:
        """Perform a mission"""
        pet = await self.get_user_pet(user_id)
        if not pet:
            return {"narrative": "You don't have a pet!", "level_up": None, "level_down": None}
            
        # Determine outcome
        success_chance = 0.7
        if difficulty == "Average": success_chance = 0.5
        elif difficulty == "Hard": success_chance = 0.3
        
        success = random.random() < success_chance
        
        xp_gain = 0
        lost_xp = 0
        
        if success:
            base_xp = 100
            if difficulty == "Average": base_xp = 250
            elif difficulty == "Hard": base_xp = 500
            
            xp_gain = base_xp
            if gamble_xp:
                xp_gain += gamble_xp  # Double the gamble (original + gain)
            
            narrative = f"✅ Mission Successful! Gained {xp_gain} XP."
            
            # Chance for loot
            loot_item = LootCalculator.get_material_loot_item(difficulty, pet['level'])
            if loot_item:
                added, msg = await LootCalculator.add_item_to_inventory(user_id, loot_item, pet)
                narrative += f"\n{msg}"
                
        else:
            narrative = "❌ Mission Failed."
            if gamble_xp:
                # Lost the gamble
                # Remove XP
                _, res = await LootCalculator.apply_xp_change(user_id, -gamble_xp, "mission_fail")
                if res and res.get("level_down"):
                     return {"narrative": narrative, "level_up": None, "level_down": res}
                narrative += f" Lost {gamble_xp} XP."

        level_up = None
        if xp_gain > 0:
            _, lvl_up = await add_experience(user_id, xp_gain, "mission")
            if lvl_up:
                level_up = lvl_up
                narrative += f"\n🎉 Level Up! Now level {lvl_up['new_level']}!"
        
        return {"narrative": narrative, "level_up": level_up, "level_down": None}

    async def rename_pet(self, user_id: int, new_name: str) -> Tuple[bool, str]:
        pet = await self.get_user_pet(user_id)
        if not pet:
            return False, "No pet found."
            
        pet["name"] = new_name
        await user_data_manager.save_pet_data(str(user_id), pet.get("name"), pet)
        return True, f"Pet renamed to {new_name}!"


class PetShopView(discord.ui.View):
    def __init__(self, bot, user, pet_system):
        super().__init__(timeout=180)
        self.bot = bot
        self.user = user
        self.pet_system = pet_system
        self.page = 0
        self.per_page = 10
        self.category = None
        self.element1 = None
        self.element2 = None
        self.species = None
        self.message = None

    @discord.ui.button(label="◀️ Prev", style=discord.ButtonStyle.secondary, row=4)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            embed = self.pet_system.create_pet_list_embed(self.page, self.per_page)
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.secondary, row=4)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        total = len(PETS_COMBINED)
        if (self.page + 1) * self.per_page < total:
            self.page += 1
            embed = self.pet_system.create_pet_list_embed(self.page, self.per_page)
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.select(placeholder="Select Category", options=[
        discord.SelectOption(label=c.title(), value=c) for c in CATEGORIES[:25]
    ], row=0)
    async def select_category(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.category = select.values[0]
        await interaction.response.defer()

    @discord.ui.select(placeholder="Select Element 1", options=[
        discord.SelectOption(label=e.title(), value=e) for e in ELEMENTS[:25]
    ], row=1)
    async def select_element1(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.element1 = select.values[0]
        await interaction.response.defer()

    @discord.ui.select(placeholder="Select Element 2 (Optional)", options=[
        discord.SelectOption(label="None", value="basic")
    ] + [
        discord.SelectOption(label=e.title(), value=e) for e in ELEMENTS[:24]
    ], row=2)
    async def select_element2(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.element2 = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="Adopt Selected", style=discord.ButtonStyle.success, row=3)
    async def adopt_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # We need species. For now, prompt user to type it?
        # Or add a species select. 
        # Since species list is huge, we'll ask them to type command or use a modal.
        # Let's use a Modal for Species name.
        await interaction.response.send_modal(AdoptionModal(self))


class AdoptionModal(discord.ui.Modal, title="Finalize Adoption"):
    species = discord.ui.TextInput(label="Species Name (from list)", placeholder="e.g. Dragon, Cat...")

    def __init__(self, view):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        res = await self.view.pet_system.process_adoption(
            interaction.user.id,
            interaction.user.display_name,
            self.view.category,
            self.species.value,
            self.view.element1,
            self.view.element2
        )
        
        if res['success']:
            await interaction.response.send_message(embed=res['embed'], ephemeral=True)
        else:
            await interaction.response.send_message(res['message'], ephemeral=True)


class PetStatusView(discord.ui.View):
    def __init__(self, user_id: int, pet_system: PetSystem, cog, pet_data=None):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.pet_system = pet_system
        self.cog = cog
        self.pet_data = pet_data
        self.message = None
        
        self.showing_breakdown = False
        self.showing_casino = False
        self.showing_inventory = False
        
        self.add_item(RefreshButton())
        self.add_item(BreakdownButton())
        self.add_item(InventoryButton())
        self.add_item(CasinoStatsButton())

    async def create_main_embed(self):
        return await self.pet_system.create_pet_status_embed(self.user_id, self.pet_data)
    
    async def create_breakdown_embed(self, user_id: str):
        """Create a detailed breakdown embed for the pet."""
        return await self.pet_system.create_pet_breakdown_embed(int(user_id), self.pet_data)

    async def create_casino_embed(self, user_id: str):
        return await self.pet_system.create_pet_casino_embed(int(user_id), self.pet_data)

class RefreshButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="🔄 Refresh", custom_id="refresh_status")
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view = self.view
        view.pet_data = None  
        view.showing_breakdown = False
        view.showing_casino = False
        view.showing_inventory = False
        view.pet_data = await view.pet_system.get_user_pet(view.user_id, force_refresh=True)
        
        embed = await view.create_main_embed()
        await interaction.edit_original_response(embed=embed, view=view)

class BreakdownButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="📊 Stats Breakdown", custom_id="show_breakdown")
    
    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.showing_breakdown = not view.showing_breakdown
        view.showing_casino = False
        view.showing_inventory = False
        await interaction.response.defer()
        
        if view.showing_breakdown:
            embed = await view.create_breakdown_embed(str(view.user_id))
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            embed = await view.create_main_embed()
            await interaction.edit_original_response(embed=embed, view=view)

class CasinoStatsButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="🎰 Casino Stats", custom_id="show_casino")
    
    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.showing_casino = not view.showing_casino
        view.showing_breakdown = False
        view.showing_inventory = False
        await interaction.response.defer()
        
        if view.showing_casino:
            embed = await view.create_casino_embed(str(view.user_id))
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            embed = await view.create_main_embed()
            await interaction.edit_original_response(embed=embed, view=view)

class InventoryButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="🎒 Inventory", custom_id="show_inventory")
    
    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.showing_inventory = not getattr(view, 'showing_inventory', False)
        view.showing_breakdown = False
        view.showing_casino = False
        
        await interaction.response.defer()
        
        if view.showing_inventory:
            embed = await view.pet_system.create_inventory_embed(view.user_id, view.pet_data)
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            embed = await view.create_main_embed()
            await interaction.edit_original_response(embed=embed, view=view)

class KillConfirmView(discord.ui.View):
    def __init__(self, pet_system, ctx, pet_data):
        super().__init__(timeout=60)
        self.pet_system = pet_system
        self.ctx = ctx
        self.pet_data = pet_data

    @discord.ui.button(label="Yes, Kill Pet", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return

        await user_data_manager.save_pet_data(str(self.ctx.author.id), f"User_{self.ctx.author.id}", {})
        await interaction.response.send_message("💀 Your pet has been killed. R.I.P.", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return
        await interaction.response.send_message("Crisis averted!", ephemeral=True)
        self.stop()

def create_pet_shop_embed():
    return discord.Embed(
        title="Welcome to the Pet Shop!",
        description="Adopt a new friend today! Use the controls below to browse and select.",
        color=discord.Color.green()
    )

def create_delete_warning_embed(pet, pet_system):
    return discord.Embed(
        title="⚠️ WARNING: PERMANENT ACTION",
        description=f"Are you sure you want to KILL **{pet['name']}**?\nThis action cannot be undone. All progress and items will be lost.",
        color=discord.Color.red()
    )

class LootMarketView(discord.ui.View):
    def __init__(self, user_id: int, pet_data: Dict[str, Any]):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.pet_data = pet_data
        
        # State
        self.selected_chest = None  # "chest1", "chest2", "chest3", "chest4"
        self.selected_amount = 1
        self.selected_type = None   # "Material", "Gem", "Monster", "Potion", "Hat"
        
        # Inventory Cache
        self.inventory = pet_data.get("inventory", [])
        self.keys = {"Key1": 0, "Key2": 0, "Key3": 0}
        
        # Count keys
        for item in self.inventory:
            if item.get("type") == "Key":
                self.keys[item.get("name")] = item.get("count", 1)

        # Components
        self.chest_select = discord.ui.Select(
            placeholder="Select a Chest...",
            options=[
                discord.SelectOption(label="Chest 1 (1 Item)", value="chest1", description="Cost: 1x Key1", emoji=emoji_mod.get('chest1') or '📦'),
                discord.SelectOption(label="Chest 2 (2 Items)", value="chest2", description="Cost: 1x Key2", emoji=emoji_mod.get('chest2') or '📦'),
                discord.SelectOption(label="Chest 3 (3 Items)", value="chest3", description="Cost: 1x Key3", emoji=emoji_mod.get('chest3') or '📦'),
                discord.SelectOption(label="Chest 4 (Selected + 3)", value="chest4", description="Cost: 1x All Keys", emoji=emoji_mod.get('chest4') or '📦'),
            ],
            row=0
        )
        self.chest_select.callback = self.on_chest_select
        self.add_item(self.chest_select)
        
        self.amount_select = discord.ui.Select(
            placeholder="Select Amount...",
            options=[discord.SelectOption(label="1", value="1")],
            disabled=True,
            row=1
        )
        self.amount_select.callback = self.on_amount_select
        self.add_item(self.amount_select)
        
        self.type_select = discord.ui.Select(
            placeholder="Select Loot Type (Chest 4 Only)...",
            options=[
                discord.SelectOption(label="Material", value="Material", emoji=emoji_mod.get('Material') or "🪵"),
                discord.SelectOption(label="Gem", value="Gem", emoji=emoji_mod.get('Gem') or "💎"),
                discord.SelectOption(label="Monster", value="Monster", emoji=emoji_mod.get('Monster') or "👹"),
                discord.SelectOption(label="Potion", value="Potion", emoji=emoji_mod.get('Potion') or "🧪"),
                discord.SelectOption(label="Hat", value="Hat", emoji=emoji_mod.get('Hat') or "🧢"),
            ],
            disabled=True,
            row=2
        )
        self.type_select.callback = self.on_type_select
        self.add_item(self.type_select)
        
        self.open_btn = discord.ui.Button(label="Open Chest", style=discord.ButtonStyle.green, disabled=True, row=3)
        self.open_btn.callback = self.on_open
        self.add_item(self.open_btn)

    def update_view_state(self):
        # Update Amount Select based on Chest
        if not self.selected_chest:
            self.amount_select.disabled = True
            self.type_select.disabled = True
            self.open_btn.disabled = True
            return

        # Calculate max affordable
        max_affordable = 0
        if self.selected_chest == "chest1":
            max_affordable = self.keys["Key1"]
        elif self.selected_chest == "chest2":
            max_affordable = self.keys["Key2"]
        elif self.selected_chest == "chest3":
            max_affordable = self.keys["Key3"]
        elif self.selected_chest == "chest4":
            max_affordable = min(self.keys["Key1"], self.keys["Key2"], self.keys["Key3"])
            
        # Update Amount Options
        options = []
        for amt in [1, 5, 10, 25]:
            if amt <= max_affordable:
                options.append(discord.SelectOption(label=str(amt), value=str(amt)))
        
        if not options:
            # Can't afford any
            self.amount_select.options = [discord.SelectOption(label="0 (Not enough keys)", value="0")]
            self.amount_select.disabled = True
            self.open_btn.disabled = True
        else:
            self.amount_select.options = options
            self.amount_select.disabled = False
            
            # Reset amount if not in new options
            if str(self.selected_amount) not in [o.value for o in options]:
                 self.selected_amount = int(options[0].value)

        # Update Type Select (Chest 4 only)
        if self.selected_chest == "chest4":
            self.type_select.disabled = False
        else:
            self.type_select.disabled = True
            self.selected_type = None

        # Update Button State
        can_open = True
        if max_affordable < self.selected_amount: can_open = False
        if self.selected_chest == "chest4" and not self.selected_type: can_open = False
        if max_affordable == 0: can_open = False
        
        self.open_btn.disabled = not can_open
        
        # Update Label
        if can_open:
            self.open_btn.label = f"Open {self.selected_amount} x {self.selected_chest.title()}"
        else:
            if max_affordable == 0:
                self.open_btn.label = "Need Keys!"
            else:
                self.open_btn.label = "Select Options"

    async def on_chest_select(self, interaction: discord.Interaction):
        self.selected_chest = self.chest_select.values[0]
        self.update_view_state()
        await interaction.response.edit_message(view=self)

    async def on_amount_select(self, interaction: discord.Interaction):
        self.selected_amount = int(self.amount_select.values[0])
        self.update_view_state()
        await interaction.response.edit_message(view=self)

    async def on_type_select(self, interaction: discord.Interaction):
        self.selected_type = self.type_select.values[0]
        self.update_view_state()
        await interaction.response.edit_message(view=self)

    async def on_open(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        # Call backend
        msgs = await LootCalculator.open_chest(
            self.user_id, 
            self.selected_chest, 
            self.selected_amount, 
            self.selected_type
        )
        
        # Format result
        res_str = "\n".join(msgs)
        if len(res_str) > 4000:
            res_str = res_str[:3900] + "\n... (truncated)"
            
        embed = discord.Embed(
            title="🎁 Chest Opened!",
            description=res_str,
            color=discord.Color.green()
        )
        
        # Update keys locally to prevent spamming without refresh
        # (Though backend handles it, UI should reflect it)
        # Re-fetching pet data is safer
        pet = await user_data_manager.get_pet_data_async(str(self.user_id))
        self.pet_data = pet
        self.inventory = pet.get("inventory", [])
        self.keys = {"Key1": 0, "Key2": 0, "Key3": 0}
        for item in self.inventory:
            if item.get("type") == "Key":
                self.keys[item.get("name")] = item.get("count", 1)
                
        self.update_view_state()
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        await interaction.edit_original_response(view=self)
