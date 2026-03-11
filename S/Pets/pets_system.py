import asyncio
import logging
import random
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Union, cast, TYPE_CHECKING
from collections import Counter

if TYPE_CHECKING:
    from discord.types.interactions import SelectMessageComponentInteractionData


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

LEVEL_THRESHOLDS: Dict[int, int] = {}

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
    pet = cast(Dict[str, Any], pet)
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

    def get_element_style(self, element: str, element2: Optional[str] = None) -> Tuple[int, str]:
        """Get element-specific styling. Supports dual elements."""
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
        
        c1 = color_map.get(str(element).lower(), 0x808080)
        
        # Check for valid second element
        if element2 and str(element2).lower() not in ('basic', 'none', '') and str(element2).lower() != str(element).lower():
            c2 = color_map.get(str(element2).lower(), 0x808080)
            
            # Blend colors
            r1, g1, b1 = (c1 >> 16) & 0xFF, (c1 >> 8) & 0xFF, c1 & 0xFF
            r2, g2, b2 = (c2 >> 16) & 0xFF, (c2 >> 8) & 0xFF, c2 & 0xFF
            
            r = (r1 + r2) // 2
            g = (g1 + g2) // 2
            b = (b1 + b2) // 2
            
            final_color = (r << 16) | (g << 8) | b
        else:
            final_color = c1
            
        return final_color, LootCalculator.get_pet_emoji("Elements", str(element)) or ""
        
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

    async def create_pet(self, user_id: int, category: str, species: str, element: Optional[str] = None, element2: Optional[str] = None) -> Optional[Dict[str, Any]]:
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
        
        computed_health = DamageCalculator.calculate_pet_health(hap, ene, 1, att, deff, intel, dex)

        # Name generation
        pet_name = self._generate_pet_name(species_key, chosen_element, category_key, chosen_element2)

        pet_data = {
            "name": pet_name,
            "category": category_key,
            "species": species_key,
            "emoji_name": species_key,
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

    async def process_adoption(self, user_id: int, user_name: str, category: str, species_input: str, element1: str, element2: str, custom_name: Optional[str] = None) -> Dict[str, Any]:
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
            pet_data = await self.create_pet(user_id, cat, chosen_species, e1, e2)
            if not pet_data:
                return {"success": False, "message": "❌ Failed to create pet."}
            if custom_name:
                pet_data["name"] = custom_name
                await user_data_manager.save_pet_data(str(user_id), custom_name, pet_data)
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
                + (f" • {LootCalculator.get_pet_emoji('Elements', str(pet_data.get('element2') or ''))} {str(pet_data.get('element2')).title()}" if pet_data.get('element2') else "")
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
            description="",
            color=discord.Color.gold()
        )
        
        for idx in range(start, end):
            name = species_list[idx]
            data = PETS_COMBINED.get(name, {})
            em = emoji_mod.mention(name) or ""
            stats = f"{emoji_mod.mention('Stat') or ''} Stats: ATT {data.get('ATT',0)} | DEF {data.get('DEF',0)} | INT {data.get('INT',0)} | DEX {data.get('DEX',0)} | HAP {data.get('HAP',0)} | ENE {data.get('ENE',0)}"
            desc = str(data.get('description', '') or '')
            embed.add_field(name=f"{idx+1}. {em} {name}", value=f"{stats}\n{desc}", inline=False)
            
        return embed

    async def create_pet_status_embed(self, user_id: int, pet_data: Optional[Dict[str, Any]] = None) -> discord.Embed:
        """Create the main pet status embed"""
        if not pet_data:
            pet_data = await self.get_user_pet(user_id)

        if not pet_data:
            return discord.Embed(title="Error", description="Pet not found!", color=discord.Color.red())

        pet: Dict[str, Any] = pet_data # Explicitly narrow the type
        
        element = str(pet.get('element', 'unknown')).lower()
        category = str(pet.get('category', 'unknown')).lower()
        e2 = str(pet.get('element2') or "").lower()
        embed_color, _ = self.get_element_style(element, e2)
        
        species_emoji = LootCalculator.get_pet_emoji("Pets", pet.get('species', ''))
        
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
        
        embed.add_field(name=f"{emoji_mod.mention('Stat') or ''} Stats", value=f"{att_e} {fmt_stat('ATT')} {totals['ATT']} | {def_e} {fmt_stat('DEF')} {totals['DEF']}\n{int_e} {fmt_stat('INT')} {totals['INT']} | {dex_e} {fmt_stat('DEX')} {totals['DEX']}\n{hap_e} {fmt_stat('HAP')} {totals['HAP']} | {ene_e} {fmt_stat('ENE')} {totals['ENE']}", inline=False)
        
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
        unfilled_char = LootCalculator.get_pet_emoji("Pet Helpers", "XP") or ""
        bar = filled_bar + unfilled_char * (10 - filled_length)
        
        embed.add_field(name="📊 Level Progress", value=f"**Level {pet['level']}** - {bar} {pet['experience']}/{threshold} XP", inline=False)

        equipment = pet.get('equipment', {})
        seat_emoji = LootCalculator.get_pet_emoji("Pet Helpers", "Seat") or "⚪"

        # Helper to get item emoji or seat emoji
        def get_item_or_seat_emoji(item_list, index, item_type):
            if item_list and len(item_list) > index and item_list[index]:
                item_name = item_list[index].get('name', '')
                return LootCalculator.get_pet_emoji(item_type, item_name) or seat_emoji
            return seat_emoji
        
        # Get equipped items, ensuring lists for multi-slot types
        equipped_monsters = equipment.get('Monsters', [])
        if not isinstance(equipped_monsters, list): equipped_monsters = [equipped_monsters] if equipped_monsters else []
        
        equipped_gems = equipment.get('Gems', [])
        if not isinstance(equipped_gems, list): equipped_gems = [equipped_gems] if equipped_gems else []
        
        equipped_materials = equipment.get('Material', [])
        if not isinstance(equipped_materials, list): equipped_materials = [equipped_materials] if equipped_materials else []

        equipped_hat = equipment.get('Hat')

        # Construct the equipment string in the desired order: {Monster}{Gem}{Material}{Hat}{Material}{Gem}{Monster}
        m1_emoji = get_item_or_seat_emoji(equipped_monsters, 0, "Pet Equipment")
        g1_emoji = get_item_or_seat_emoji(equipped_gems, 0, "Pet Equipment")
        mat1_emoji = get_item_or_seat_emoji(equipped_materials, 0, "Pet Equipment")
        hat_emoji = LootCalculator.get_pet_emoji("Pet Equipment", equipped_hat.get('name', '')) if equipped_hat else seat_emoji
        mat2_emoji = get_item_or_seat_emoji(equipped_materials, 1, "Pet Equipment") # Second material slot
        g2_emoji = get_item_or_seat_emoji(equipped_gems, 1, "Pet Equipment") # Second gem slot
        m2_emoji = get_item_or_seat_emoji(equipped_monsters, 1, "Pet Equipment") # Second monster slot

        equipment_display = f"{m1_emoji}{g1_emoji}{mat1_emoji}{hat_emoji}{mat2_emoji}{g2_emoji}{m2_emoji}"
        embed.add_field(name="Equipment", value=equipment_display, inline=False)

        return embed

    async def create_inventory_embed(self, user_id: int, pet_data: Optional[Dict[str, Any]] = None) -> discord.Embed:
        """Create inventory embed with categorized items"""
        if not pet_data:
            pet_data = await self.get_user_pet(user_id)
        
        pet = pet_data
        if not pet:
            return discord.Embed(title="❌ No Pet Found", description="You don't have a pet yet!", color=discord.Color.red())

        element = str(pet.get('element', 'basic')).lower()
        e2 = str(pet.get('element2') or "").lower()
        embed_color, _ = self.get_element_style(element, e2)
        
        inv_emoji = LootCalculator.get_pet_emoji("Pet Helpers", "Inventory") or ""
        embed = discord.Embed(
            title=f"{inv_emoji} {pet['name']}'s Inventory".strip(),
            description=f"**Level {pet['level']}** {pet.get('species', 'Pet')} • {pet.get('category', '').title()}",
            color=discord.Color(embed_color)
        )
        
        inventory = pet.get('inventory', [])
        
        # Group items
        item_counts, item_data = LootCalculator.group_inventory_items(inventory)

        # Build fields
        emoji_map = {"Material": "", "Gem": "", "Monster": "", "Potion": "", "Hat": "", "Key": "", "Chest": ""}
        
        for cat in ["Hat", "Potion", "Material", "Gem", "Monster", "Key", "Chest"]:
            if cat in item_counts and item_counts[cat]:
                lines = []
                for name, count in Counter(item_counts[cat]).most_common():
                    item = item_data[cat][name]
                    
                    # Search for a matching emoji in emoji.py
                    em = emoji_mod.mention(name) or ""
                    stats = LootCalculator._format_item_stats(item)
                    
                    line = f"{em} **{name}**{stats}"
                    if count > 1:
                        line += f" x{count}"
                    lines.append(line)
                
                cat_em = emoji_mod.mention(cat) or ""
                embed.add_field(name=f"{cat_em} {cat}s".strip(), value="\n".join(lines), inline=False)
            
        if not inventory:
            embed.description = (embed.description or "") + "\n\n*Inventory is empty!*"
            
        return embed

    async def create_pet_breakdown_embed(self, user_id: int, pet_data: Optional[Dict[str, Any]] = None) -> discord.Embed:
        # This function creates a detailed breakdown embed for the pet's stats and XP sources.
        """Detailed stats breakdown"""
        if not pet_data:
            pet_data = await self.get_user_pet(user_id)

        if not pet_data:
            return discord.Embed(title="Error", description="Pet not found!", color=discord.Color.red())

        pet: Dict[str, Any] = pet_data # Explicitly narrow the type
        totals = StatsCalculator.calculate_pet_stats(pet)
        
        embed = discord.Embed(
            title=f"📊 Stats Breakdown - {pet['name']}",
            description="",
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

        xp_breakdown_str = ""
        xp_sources_found = False
        for key, value in pet.items():
            if key.endswith("_xp_earned") and value != 0:
                source_name = key.replace("_xp_earned", "").replace("_", " ").title()
                sign = "+" if value >= 0 else ""
                xp_breakdown_str += f"{source_name}: {sign}{value} XP\n"
                xp_sources_found = True

        if xp_sources_found:
            embed.add_field(name="📊 XP Breakdown", value=xp_breakdown_str.strip(), inline=False)

        return embed

    async def create_pet_casino_embed(self, user_id: int, pet_data: Optional[Dict[str, Any]] = None) -> discord.Embed:
        """Casino stats embed"""
        if not pet_data:
            pet_data = await self.get_user_pet(user_id)

        if not pet_data:
            return discord.Embed(title="Error", description="Pet not found!", color=discord.Color.red())
            
        stats = pet_data.get("gambling_stats", {}) # Changed from "casino_stats" to "gambling_stats" based on user_data_manager.py
        
        embed = discord.Embed(
            title=f"🎰 Casino Stats - {pet_data['name']}",
            color=discord.Color.gold()
        )
        
        # Helper function to format game stats
        def format_game_stats(game_name: str, game_stats: Dict[str, Any]) -> str:
            # Attempt to get new keys first
            wins = game_stats.get("wins", 0)
            losses = game_stats.get("losses", 0)
            pushes = game_stats.get("pushes", 0)
            total_played = game_stats.get("total_played", 0)
            total_won = game_stats.get("total_won", 0)
            total_lost = game_stats.get("total_lost", 0)
            net_xp = game_stats.get("net_xp", 0)

            # Fallback to old keys if new keys are not present
            if total_played == 0: # If new format not found, try old format
                if game_name == "Slots":
                    total_played = game_stats.get("total_games_played", 0)
                    total_won = game_stats.get("xp_won_total", 0)
                    total_lost = game_stats.get("xp_lost_total", 0)
                    # Wins/losses for slots are not directly stored as counts in old format, infer from XP
                    if total_won > 0: wins = 1 # At least one win
                    if total_lost > 0: losses = 1 # At least one loss
                    net_xp = total_won - total_lost
                elif game_name == "Blackjack":
                    total_played = game_stats.get("rounds_played", 0)
                    wins = game_stats.get("rounds_won", 0)
                    losses = game_stats.get("rounds_lost", 0)
                    total_won = game_stats.get("xp_won_total", 0)
                    total_lost = game_stats.get("xp_lost_total", 0)
                    net_xp = total_won - total_lost
                elif game_name in ["Hold'em", "Craps"]:
                    total_played = game_stats.get("games_played", 0)
                    wins = game_stats.get("games_won", 0)
                    losses = game_stats.get("games_lost", 0)
                    total_won = game_stats.get("xp_won_total", 0)
                    total_lost = game_stats.get("xp_lost_total", 0)
                    net_xp = total_won - total_lost
                elif game_name == "Races":
                    total_played = game_stats.get("races_played", 0)
                    wins = game_stats.get("races_won", 0)
                    losses = game_stats.get("races_lost", 0)
                    total_won = game_stats.get("xp_won_total", 0)
                    total_lost = game_stats.get("xp_lost_total", 0)
                    net_xp = total_won - total_lost

            if total_played == 0:
                return "No games played."
            
            return (
                f"Played: {total_played} | Wins: {wins} | Losses: {losses} | Pushes: {pushes}\n"
                f"Won: {total_won:,} | Lost: {total_lost:,} | Net XP: {net_xp:+}"
            )

        # Games to display and their corresponding keys in gambling_stats
        games_to_display = {
            "Slots": "slots",
            "Blackjack": "blackjack",
            "Hold'em": "holdem",
            "Craps": "craps",
            "Races": "races"
        }

        for display_name, stat_key in games_to_display.items():
            game_stats = stats.get(stat_key, {})
            embed.add_field(name=display_name, value=format_game_stats(display_name, game_stats), inline=False)
        
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
            
            # Tiered Key Loot Logic
            looted_keys = LootCalculator.get_key_loot(difficulty, bypass_chance=True)
            
            if looted_keys:
                for k_data in looted_keys:
                    added, msg = await LootCalculator.add_item_to_inventory(user_id, k_data, pet)
                    if added and msg:
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
            
        success = await user_data_manager.update_pet_name(str(user_id), pet["id"], new_name)
        if success:
            return True, f"Pet renamed to {new_name}!"
        else:
            return False, "Failed to rename pet."
        return True, f"Pet renamed to {new_name}!"

    async def rename_action(self, user_id: int, action: str, label: str) -> Tuple[bool, str]:
        pet = await self.get_user_pet(user_id)
        if not pet:
            return False, "No pet found."

        if action not in ["attack", "defend", "charge"]:
            return False, "Invalid action to rename."

        if "action_labels" not in pet:
            pet["action_labels"] = {"attack": None, "defend": None, "charge": None}

        pet["action_labels"][action] = label
        await user_data_manager.save_pet_data(str(user_id), pet.get("name"), pet)
        return True, f"Pet's {action} action has been renamed to {label}!"


class PetShopView(discord.ui.View):
    def __init__(self, bot, user, pet_system):
        super().__init__(timeout=180)
        self.bot = bot
        self.user = user
        self.pet_system = pet_system
        self.page = 0
        self.per_page = 10
        self.message = None

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="◀️", row=0)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            embed = self.pet_system.create_pet_list_embed(self.page, self.per_page)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Adopt", style=discord.ButtonStyle.success, emoji="🐾", row=0)
    async def adopt_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This is not your session!", ephemeral=True)
            return
            
        # Get species on current page
        species_list = list(PETS_COMBINED.keys())
        start = self.page * self.per_page
        end = min(len(species_list), start + self.per_page)
        page_species = species_list[start:end]
        
        # Create a select menu for these species
        options = [
            discord.SelectOption(
                label=s, 
                value=s, 
                emoji=LootCalculator.get_pet_emoji("Pets", s) or "🐾"
            ) for s in page_species
        ]
        
        select: discord.ui.Select = discord.ui.Select(placeholder="Select which pet to adopt...", options=options)
        
        async def select_callback(inter: discord.Interaction):
            if inter.user.id != self.user.id:
                await inter.response.send_message("This is not your session!", ephemeral=True)
                return
            chosen = cast(SelectMessageComponentInteractionData, inter.data)['values'][0]
            config_view = AdoptionConfigView(self.bot, self.user, self.pet_system, chosen)
            config_view.update_selects()
            await inter.response.edit_message(content=None, embed=config_view.create_config_embed(), view=config_view)
            
        select.callback = select_callback # type: ignore
        
        # Show the select menu
        view = discord.ui.View(timeout=60)
        view.add_item(select)
        
        # Add a back button
        back_btn: discord.ui.Button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        async def cancel_callback(inter: discord.Interaction):
            if inter.user.id != self.user.id:
                await inter.response.send_message("This is not your session!", ephemeral=True)
                return
            await inter.response.edit_message(content=None, embed=self.pet_system.create_pet_list_embed(self.page, self.per_page), view=self)
        back_btn.callback = cancel_callback # type: ignore
        view.add_item(back_btn)
        
        await interaction.response.edit_message(content="**Which pet would you like to adopt?**", embed=None, view=view)

    @discord.ui.button(label="Forward", style=discord.ButtonStyle.secondary, emoji="▶️", row=0)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        total = len(PETS_COMBINED)
        if (self.page + 1) * self.per_page < total:
            self.page += 1
            embed = self.pet_system.create_pet_list_embed(self.page, self.per_page)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()


class AdoptionConfigView(discord.ui.View):
    def __init__(self, bot, user, pet_system, species):
        super().__init__(timeout=300)
        self.bot = bot
        self.user = user
        self.pet_system = pet_system
        self.species = species
        self.category = "land"
        self.element1 = "fire"
        self.element2 = "basic"
        self.message = None

    def create_config_embed(self):
        element_color, _ = self.pet_system.get_element_style(self.element1, self.element2)
        
        species_emoji = LootCalculator.get_pet_emoji("Pets", self.species) or ""
        type_emoji = LootCalculator.get_pet_emoji("Pet Type", self.category) or ""
        e1_emoji = LootCalculator.get_pet_emoji("Elements", self.element1) or ""
        e2_emoji = LootCalculator.get_pet_emoji("Elements", self.element2) if self.element2 != "basic" else ""

        embed = discord.Embed(
            title=f"🐾 Adoption: {species_emoji} {self.species}",
            description=f"Configure your new friend's attributes.\n\n"
                        f"**Current Build:**\n"
                        f"{type_emoji} Type: {self.category.title()}\n"
                        f"{e1_emoji} Element 1: {self.element1.title()}\n"
                        + (f"{e2_emoji} Element 2: {self.element2.title()}" if self.element2 != "basic" else "Element 2: None"),
            color=element_color
        )
        
        # Add base stats for the species
        base_stats = PETS_COMBINED.get(self.species, {})
        stats_str = (
            f"⚔️ ATT: {base_stats.get('ATT', 0)} | 🛡️ DEF: {base_stats.get('DEF', 0)}\n"
            f"🧠 INT: {base_stats.get('INT', 0)} | 💨 DEX: {base_stats.get('DEX', 0)}\n"
            f"❤️ HAP: {base_stats.get('HAP', 0)} | ⚡ ENE: {base_stats.get('ENE', 0)}"
        )
        embed.add_field(name="Base Stats", value=stats_str, inline=False)
        
        embed.set_footer(text="Select attributes below then click 'Finalize' to name your pet!")
        return embed

    def update_selects(self):
        self.clear_items()
        
        # 1. Type (Category) Dropdown
        cat_options = [
            discord.SelectOption(label=c.title(), value=c, emoji=LootCalculator.get_pet_emoji("Pet Type", c), default=(c == self.category)) 
            for c in CATEGORIES[:25]
        ]
        cat_select = discord.ui.Select(placeholder="Select Type (Category)", options=cat_options, row=0)
        cat_select.callback = self.select_category
        self.add_item(cat_select)
        
        # 2. Element 1 Dropdown
        e1_options = [
            discord.SelectOption(label=e.title(), value=e, emoji=LootCalculator.get_pet_emoji("Elements", e), default=(e == self.element1)) 
            for e in ELEMENTS[:25]
        ]
        e1_select = discord.ui.Select(placeholder="Select Element 1", options=e1_options, row=1)
        e1_select.callback = self.select_element1
        self.add_item(e1_select)
        
        # 3. Element 2 Dropdown (Conditional)
        if self.element1 != "basic":
            # Filter elements to exclude basic and element1
            e2_choices = [e for e in ELEMENTS if e != "basic" and e != self.element1]
            e2_options = [discord.SelectOption(label="None", value="basic", default=(self.element2 == "basic"))]
            e2_options += [
                discord.SelectOption(label=e.title(), value=e, emoji=LootCalculator.get_pet_emoji("Elements", e), default=(e == self.element2)) 
                for e in e2_choices[:24]
            ]
            e2_select = discord.ui.Select(placeholder="Select Element 2 (Optional)", options=e2_options, row=2)
            e2_select.callback = self.select_element2
            self.add_item(e2_select)
            
        # Finalize Button
        finalize_btn = discord.ui.Button(label="Finalize & Name", style=discord.ButtonStyle.success, emoji="📝", row=3)
        finalize_btn.callback = self.finalize_adoption
        self.add_item(finalize_btn)
        
        # Cancel/Back Button
        cancel_btn = discord.ui.Button(label="Back to Shop", style=discord.ButtonStyle.secondary, row=3)
        cancel_btn.callback = self.back_to_shop
        self.add_item(cancel_btn)

    async def select_category(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This is not your session!", ephemeral=True)
            return
        data: SelectMenuInteractionData = interaction.data # type: ignore
        self.category = data['values'][0]
        self.update_selects()
        await interaction.response.edit_message(embed=self.create_config_embed(), view=self)

    async def select_element1(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This is not your session!", ephemeral=True)
            return
        data: SelectMenuInteractionData = interaction.data # type: ignore
        self.element1 = data['values'][0]
        # Reset element2 if element1 is basic
        if self.element1 == "basic":
            self.element2 = "basic"
        # If element2 is same as new element1, reset it
        if self.element2 == self.element1:
            self.element2 = "basic"
            
        self.update_selects()
        await interaction.response.edit_message(embed=self.create_config_embed(), view=self)

    async def select_element2(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This is not your session!", ephemeral=True)
            return
        data: SelectMenuInteractionData = interaction.data # type: ignore
        self.element2 = data['values'][0]
        self.update_selects()
        await interaction.response.edit_message(embed=self.create_config_embed(), view=self)

    async def finalize_adoption(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This is not your session!", ephemeral=True)
            return
        await interaction.response.send_modal(AdoptionModal(self))

    async def back_to_shop(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This is not your session!", ephemeral=True)
            return
        shop_view = PetShopView(self.bot, self.user, self.pet_system)
        embed = self.pet_system.create_pet_list_embed(0, shop_view.per_page)
        await interaction.response.edit_message(content=None, embed=embed, view=shop_view)


class AdoptionModal(discord.ui.Modal, title="Name Your New Pet"):
    pet_name: discord.ui.TextInput = discord.ui.TextInput(
        label="Pet Name",
        placeholder="Enter a nickname for your pet...",
        min_length=1,
        max_length=32,
        required=True
    )

    def __init__(self, config_view):
        super().__init__()
        self.config_view = config_view

    async def on_submit(self, interaction: discord.Interaction):
        # Process the adoption
        res = await self.config_view.pet_system.process_adoption(
            interaction.user.id,
            interaction.user.display_name,
            self.config_view.category,
            self.config_view.species,
            self.config_view.element1,
            self.config_view.element2,
            custom_name=self.pet_name.value
        )
        
        if res['success']:
            # Success embed is returned from process_adoption
            embed = res['embed']
            embed.title = f"🎉 Adoption Complete!"
            embed.set_footer(text=f"Welcome home, {self.pet_name.value}!")
            await interaction.response.edit_message(content=None, embed=embed, view=None)
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
        super().__init__(style=discord.ButtonStyle.primary, label="Refresh", emoji="🔄", custom_id="refresh_status")
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view: 'PetStatusView' = cast('PetStatusView', self.view)
        view.pet_data = None  
        view.showing_breakdown = False
        view.showing_casino = False
        view.showing_inventory = False
        view.pet_data = await view.pet_system.get_user_pet(view.user_id, force_refresh=True)
        
        embed = await view.create_main_embed()
        await interaction.edit_original_response(embed=embed, view=view)

class BreakdownButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="Stats Breakdown", emoji="📊", custom_id="show_breakdown")
    
    async def callback(self, interaction: discord.Interaction):
        view: PetStatusView = cast(PetStatusView, self.view)
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
        super().__init__(style=discord.ButtonStyle.secondary, label="Casino Stats", emoji="🎰", custom_id="show_casino")
    
    async def callback(self, interaction: discord.Interaction):
        view: PetStatusView = cast(PetStatusView, self.view)
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
        super().__init__(style=discord.ButtonStyle.secondary, label="Inventory", emoji="🎒", custom_id="show_inventory")
    
    async def callback(self, interaction: discord.Interaction):
        view: PetStatusView = cast(PetStatusView, self.view)
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

    @discord.ui.button(label="Yes, Kill Pet", style=discord.ButtonStyle.danger, emoji="💀")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return

        await user_data_manager.save_pet_data(str(self.ctx.author.id), f"User_{self.ctx.author.id}", {})
        await interaction.response.send_message("💀 Your pet has been killed. R.I.P.", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="🛡️")
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

class InventoryPaginatedView(discord.ui.View):
    def __init__(self, pet_system, user_id, pet_data):
        super().__init__(timeout=180)
        self.pet_system = pet_system
        self.user_id = user_id
        self.pet_data = pet_data
        self.page = 0
        self.items_per_page = 15
        
        # Prepare data
        self.inventory = pet_data.get('inventory', [])
        item_counts, item_data = LootCalculator.group_inventory_items(self.inventory)
        
        # Flatten for pagination but keep headers
        self.lines = []
        emoji_map = {"Material": "🪵", "Gem": "💎", "Monster": "👹", "Potion": "🧪", "Hat": "🧢", "Key": "🗝️", "Chest": "📦"}
        
        # Order: Hat -> Potion -> Material -> Gem -> Monster -> Key -> Chest
        for cat in ["Hat", "Potion", "Material", "Gem", "Monster", "Key", "Chest"]:
            if cat in item_counts and item_counts[cat]:
                cat_em = emoji_mod.mention(cat) or ""
                self.lines.append(f"**{cat_em} {cat}s**".strip())
                for name, count in item_counts[cat].most_common():
                    item = item_data[cat][name]
                    
                    # Try to get emoji from emoji module using name
                    em = emoji_mod.mention(name) or ""
                        
                    stats = LootCalculator._format_item_stats(item)
                    
                    line = f"{em} **{name}**{stats}"
                    if count > 1:
                        line += f" x{count}"
                    self.lines.append(line)
                self.lines.append("") # Spacer
        
        # Remove trailing spacer
        if self.lines and self.lines[-1] == "":
            self.lines.pop()
            
        if not self.lines:
            self.lines = ["*Inventory is empty!*"]

    def get_embed(self):
        start = self.page * self.items_per_page
        end = start + self.items_per_page
        current_lines = self.lines[start:end]
        
        pet = self.pet_data
        element = str(pet.get('element', 'basic')).lower()
        embed_color, _ = self.pet_system.get_element_style(element, pet.get('element2'))
        inv_emoji = LootCalculator.get_pet_emoji("Pet Helpers", "Inventory") or ""
        
        total_pages = max(1, (len(self.lines) + self.items_per_page - 1) // self.items_per_page)
        
        embed = discord.Embed(
            title=f"{inv_emoji} {pet['name']}'s Inventory".strip(),
            description=f"**Level {pet['level']}** {pet.get('species', 'Pet')} • {pet.get('category', '').title()}\n\n" + "\n".join(current_lines),
            color=discord.Color(embed_color)
        )
        embed.set_footer(text=f"Page {self.page + 1}/{total_pages}")
        return embed

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
             await interaction.response.defer()

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        total_pages = max(1, (len(self.lines) + self.items_per_page - 1) // self.items_per_page)
        if self.page < total_pages - 1:
            self.page += 1
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
             await interaction.response.defer()

class LootMarketView(discord.ui.View):
    def __init__(self, user_id: int, pet_data: Dict[str, Any]):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.pet_data = pet_data
        
        # State
        self.selected_chest: str = ""  # "chest1", "chest2", "chest3", "chest4"
        self.selected_amount = 1
        self.selected_type: str = ""   # "Material", "Gem", "Monster", "Potion", "Hat"
        
        # Inventory Cache
        self.inventory = pet_data.get("inventory", [])
        self.keys = {"Key1": 0, "Key2": 0, "Key3": 0}
        
        # Count keys
        for item in self.inventory:
            if item.get("type") == "Key":
                self.keys[item.get("name")] = item.get("count", 1)

        # Components
        self.chest_select: discord.ui.Select = discord.ui.Select(
            placeholder="Select a Chest...",
            options=[
                discord.SelectOption(label="Chest 1 (1 Item)", value="chest1", description="Cost: 1x Key1", emoji=emoji_mod.mention('chest1')),
                discord.SelectOption(label="Chest 2 (2 Items)", value="chest2", description="Cost: 1x Key2", emoji=emoji_mod.mention('chest2')),
                discord.SelectOption(label="Chest 3 (3 Items)", value="chest3", description="Cost: 1x Key3", emoji=emoji_mod.mention('chest3')),
                discord.SelectOption(label="Chest 4 (1 Selected + 3 Random Items)", value="chest4", description="Cost: 1x Key1, 1x Key2, 1x Key3", emoji=emoji_mod.mention('chest4')),
            ],
            row=0
        )
        self.chest_select.callback = self.on_chest_select # type: ignore
        self.add_item(self.chest_select)
        
        self.amount_select: discord.ui.Select = discord.ui.Select(
            placeholder="Select Amount...",
            options=[discord.SelectOption(label="1", value="1")],
            disabled=True,
            row=1
        )
        self.amount_select.callback = self.on_amount_select # type: ignore
        self.add_item(self.amount_select)
        
        self.type_select: discord.ui.Select = discord.ui.Select(
            placeholder="Select Loot Type (Chest 4 Only)...",
            options=[
                discord.SelectOption(label="Material", value="Material", emoji="🪵"),
                discord.SelectOption(label="Gem", value="Gem", emoji="💎"),
                discord.SelectOption(label="Monster", value="Monster", emoji="👹"),
                discord.SelectOption(label="Potion", value="Potion", emoji="🧪"),
                discord.SelectOption(label="Hat", value="Hat", emoji="🧢"),
            ],
            disabled=True,
            row=2
        )
        self.type_select.callback = self.on_type_select # type: ignore
        self.add_item(self.type_select)
        
        self.open_btn: discord.ui.Button = discord.ui.Button(label="Open Chest", style=discord.ButtonStyle.green, disabled=True, row=3)
        self.open_btn.callback = self.on_open # type: ignore
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
                cast(discord.ui.Button, self.open_btn).label = "Need Keys!"
            else:
                cast(discord.ui.Button, self.open_btn).label = "Select Options"

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
        if self.selected_chest is None:
            await interaction.followup.send("Please select a chest first.", ephemeral=True)
            return
        msgs = await LootCalculator.open_chest(
            self.user_id, 
            cast(str, self.selected_chest), 
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
        self.pet_data = pet if pet is not None else {}
        self.inventory = self.pet_data.get("inventory", [])
        self.keys = {"Key1": 0, "Key2": 0, "Key3": 0}
        for item in self.inventory:
            if item.get("type") == "Key":
                self.keys[item.get("name")] = item.get("count", 1)
                
        self.update_view_state()
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        await interaction.edit_original_response(view=self)
