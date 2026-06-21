"""
Dungeon Crawl System - Turn-based roguelite dungeon crawler
Solo or co-op (2-4 players) with procedurally generated dungeons
"""
import discord
import random
import asyncio
import logging
import json
import os
import aiosqlite
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from Systems.Functions.user_data_manager import user_data_manager
from Systems.Functions import emoji as emoji_mod
from Systems.Pets.Logic.pet_brain import DamageCalculator, NPCBrain, LootCalculator, StatsCalculator

logger = logging.getLogger('dungeon_crawl')

# Dungeon configuration
ROOMS_PER_FLOOR = 10
MAX_PARTY_SIZE = 4
BOSS_ROOM = 9    # Room 9 is always the boss
REWARD_ROOM = 10  # Room 10 is always a guaranteed chest reward

# Event types
EVENT_MONSTER = "monster"
EVENT_CHEST = "chest"   # Legacy alias (kept for backward compat)
EVENT_CHEST1 = "chest1"
EVENT_CHEST2 = "chest2"
EVENT_CHEST3 = "chest3"
EVENT_CHEST4 = "chest4"
EVENT_TRAP = "trap"
EVENT_SHRINE = "shrine"
EVENT_BOSS = "boss"

# NEW event types for quest merge
EVENT_MONSTER_ENCOUNTER = "monster_encounter"
EVENT_STORY_SEGMENT = "story_segment"
EVENT_PUZZLE = "puzzle"
EVENT_MERCHANT = "merchant"
EVENT_CHEST_MIMIC = "chest_mimic"
EVENT_FLOOR_LOOT = "floor_loot"

# Dungeon types for AI generation (MATCHING PLAY/QUEST LOCATIONS)
DUNGEON_TYPES = [
    "Camp", "Bonfire", "Beach", "Forest", "Hot Air Balloon", "Cruiseship",
    "Mountain", "Gym", "Graveyard", "Festival", "Glacier", "Pyramids"
]

# Dungeon type → primary element mapping (FOR THEMING ONLY - NO BONUSES)
DUNGEON_TYPE_ELEMENT = {
    "Camp": "basic",
    "Bonfire": "fire",
    "Beach": "water",
    "Forest": "plant",
    "Hot Air Balloon": "air",
    "Cruiseship": "water",
    "Mountain": "rock",
    "Gym": "fighting",
    "Graveyard": "necro",
    "Festival": "magic",
    "Glacier": "ice",
    "Pyramids": "electric"
}

# XP formula room type plugs
XP_PLUGS = {
    'boss': 500,
    'monster_encounter': 250,
    'story_segment': 250,
    'puzzle': 250,
    'trap': 100,
    'shrine': 50,
    'merchant': 25,
    'floor_loot': 25,
    'chest': 25,
    'chest1': 25,
    'chest2': 25,
    'chest3': 25,
    'chest4': 25
}

# Merchant rarity pricing
MERCHANT_RARITY_PRICES = {
    'Common': 100,
    'Uncommon': 500,
    'Rare': 1000,
    'Epic': 2500,
    'Mythic': 5000,
    'Special': 3000  # For Keys and Chests
}

# Chest event types mapped to their CHEST_TYPES index
CHEST_EVENT_MAP = {
    EVENT_CHEST1: 0,
    EVENT_CHEST2: 1,
    EVENT_CHEST3: 2,
    EVENT_CHEST4: 3,
    EVENT_CHEST:  0,  # legacy fallback → Chest 1
}

# Cache equipment data (loaded once at module level)
_EQUIPMENT_DATA = None

def _load_equipment_data():
    """Load equipment data once and cache it"""
    global _EQUIPMENT_DATA
    if _EQUIPMENT_DATA is None:
        equipment_path = os.path.join(os.path.dirname(__file__), '..', 'Logic', 'equipment.json')
        with open(equipment_path, 'r') as f:
            _EQUIPMENT_DATA = json.load(f)
    return _EQUIPMENT_DATA

# ---------------------------------------------------------------------------
# Emoji helpers — returns a static web path for use in the dungeon webpage.
# Element/type keys map to /static/Emojis/Pets/Deco/{Key}.png
# ---------------------------------------------------------------------------
_ELEMENT_TYPE_KEYS = {
    "Fire", "Water", "Electric", "Ice", "Plant", "Rock", "Air",
    "Magic", "Holy", "Necro", "Psychic", "Fighting", "Basic",
    "Flying", "Land", "Swimming",
}

def _e(key: str) -> str:
    """Return a static image path for the given element/type key.
    Used as the 'emoji' field on traps and shrines sent to the web UI."""
    if key in _ELEMENT_TYPE_KEYS:
        return f"/static/Emojis/Pets/Deco/{key}.png"
    return key  # fallback: just the key name

# ---------------------------------------------------------------------------
# Generic (non-elemental, non-type) trap effects — 50 entries
# These apply to ALL party members regardless of element/type.
# ---------------------------------------------------------------------------
TRAP_EFFECTS_GENERIC = [
    # ── Attack reductions ────────────────────────────────────────────────────
    {"name": "Weakening Gas",        "effect": "att_reduction", "value": 0.10, "duration": 5,  "emoji": "💨",  "target_filter": None},
    {"name": "Cursed Shackles",      "effect": "att_reduction", "value": 0.15, "duration": 4,  "emoji": "⛓️",  "target_filter": None},
    {"name": "Sapping Miasma",       "effect": "att_reduction", "value": 0.12, "duration": 5,  "emoji": "🌫️", "target_filter": None},
    {"name": "Enervating Spores",    "effect": "att_reduction", "value": 0.20, "duration": 3,  "emoji": "🍄",  "target_filter": None},
    {"name": "Leaden Weights",       "effect": "att_reduction", "value": 0.18, "duration": 4,  "emoji": "🏋️", "target_filter": None},
    {"name": "Withering Hex",        "effect": "att_reduction", "value": 0.25, "duration": 2,  "emoji": "🔮",  "target_filter": None},
    {"name": "Rusted Blades",        "effect": "att_reduction", "value": 0.15, "duration": 5,  "emoji": "🗡️", "target_filter": None},
    {"name": "Numbing Fog",          "effect": "att_reduction", "value": 0.10, "duration": 6,  "emoji": "☁️",  "target_filter": None},

    # ── Defense reductions ───────────────────────────────────────────────────
    {"name": "Draining Vortex",      "effect": "def_reduction", "value": 0.10, "duration": 5,  "emoji": "🌀",  "target_filter": None},
    {"name": "Crumbling Runes",      "effect": "def_reduction", "value": 0.15, "duration": 4,  "emoji": "📜",  "target_filter": None},
    {"name": "Corrosive Ooze",       "effect": "def_reduction", "value": 0.20, "duration": 3,  "emoji": "🧪",  "target_filter": None},
    {"name": "Brittle Curse",        "effect": "def_reduction", "value": 0.12, "duration": 5,  "emoji": "💀",  "target_filter": None},
    {"name": "Shattering Glyph",     "effect": "def_reduction", "value": 0.25, "duration": 2,  "emoji": "💠",  "target_filter": None},
    {"name": "Acid Puddle",          "effect": "def_reduction", "value": 0.18, "duration": 4,  "emoji": "☣️",  "target_filter": None},

    # ── Dexterity reductions ─────────────────────────────────────────────────
    {"name": "Slowing Mud",          "effect": "dex_reduction", "value": 0.15, "duration": 4,  "emoji": "🌊",  "target_filter": None},
    {"name": "Tar Pit",              "effect": "dex_reduction", "value": 0.20, "duration": 4,  "emoji": "🕳️", "target_filter": None},
    {"name": "Binding Vines",        "effect": "dex_reduction", "value": 0.15, "duration": 5,  "emoji": "🌿",  "target_filter": None},
    {"name": "Gravity Well",         "effect": "dex_reduction", "value": 0.25, "duration": 3,  "emoji": "⚫",  "target_filter": None},
    {"name": "Sticky Web",           "effect": "dex_reduction", "value": 0.18, "duration": 4,  "emoji": "🕸️", "target_filter": None},
    {"name": "Quicksand Trap",       "effect": "dex_reduction", "value": 0.20, "duration": 3,  "emoji": "🏜️", "target_filter": None},
    {"name": "Frozen Joints",        "effect": "dex_reduction", "value": 0.15, "duration": 5,  "emoji": "🧊",  "target_filter": None},

    # ── Intelligence reductions ──────────────────────────────────────────────
    {"name": "Confusion Mist",       "effect": "int_reduction", "value": 0.10, "duration": 5,  "emoji": "😵‍💫", "target_filter": None},
    {"name": "Madness Rune",         "effect": "int_reduction", "value": 0.20, "duration": 3,  "emoji": "👿",  "target_filter": None},
    {"name": "Disorienting Gas",     "effect": "int_reduction", "value": 0.15, "duration": 4,  "emoji": "💭",  "target_filter": None},
    {"name": "Memory Leech",         "effect": "int_reduction", "value": 0.25, "duration": 2,  "emoji": "🧠",  "target_filter": None},
    {"name": "Scrambling Sigil",     "effect": "int_reduction", "value": 0.12, "duration": 5,  "emoji": "🔣",  "target_filter": None},
    {"name": "Dullness Curse",       "effect": "int_reduction", "value": 0.18, "duration": 4,  "emoji": "😵",  "target_filter": None},

    # ── Health effects ───────────────────────────────────────────────────────
    {"name": "Poison Dart",          "effect": "health_half",   "value": 0.50, "duration": 10, "emoji": "🎯",  "target_filter": None},
    {"name": "Plague Vent",          "effect": "health_half",   "value": 0.40, "duration": 8,  "emoji": "☠️",  "target_filter": None},
    {"name": "Wasting Curse",        "effect": "health_half",   "value": 0.30, "duration": 6,  "emoji": "💔",  "target_filter": None},
    {"name": "Necrotic Spores",      "effect": "health_half",   "value": 0.35, "duration": 7,  "emoji": "🍄",  "target_filter": None},
    {"name": "Vampiric Rune",        "effect": "health_half",   "value": 0.45, "duration": 9,  "emoji": "🩸",  "target_filter": None},

    # ── No-defend effects ────────────────────────────────────────────────────
    {"name": "Cursed Runes",         "effect": "no_defend",     "value": 1,    "duration": 1,  "emoji": "📜",  "target_filter": None},
    {"name": "Paralysis Glyph",      "effect": "no_defend",     "value": 1,    "duration": 2,  "emoji": "⚡",  "target_filter": None},
    {"name": "Petrification Trap",   "effect": "no_defend",     "value": 1,    "duration": 1,  "emoji": "🗿",  "target_filter": None},
    {"name": "Stun Rune",            "effect": "no_defend",     "value": 1,    "duration": 2,  "emoji": "💫",  "target_filter": None},
    {"name": "Binding Seal",         "effect": "no_defend",     "value": 1,    "duration": 1,  "emoji": "🔒",  "target_filter": None},

    # ── Multi-stat combos (stacked via two entries sharing a room — single entry, moderate values) ──
    {"name": "Exhaustion Trap",      "effect": "att_reduction", "value": 0.12, "duration": 6,  "emoji": "😩",  "target_filter": None},
    {"name": "Despair Sigil",        "effect": "def_reduction", "value": 0.12, "duration": 6,  "emoji": "😰",  "target_filter": None},
    {"name": "Lethargy Mist",        "effect": "dex_reduction", "value": 0.12, "duration": 6,  "emoji": "💤",  "target_filter": None},
    {"name": "Fog of Doubt",         "effect": "int_reduction", "value": 0.12, "duration": 6,  "emoji": "🌁",  "target_filter": None},
    {"name": "Crushing Dread",       "effect": "att_reduction", "value": 0.20, "duration": 4,  "emoji": "😱",  "target_filter": None},
    {"name": "Hollow Curse",         "effect": "def_reduction", "value": 0.20, "duration": 4,  "emoji": "👻",  "target_filter": None},
    {"name": "Leech Pit",            "effect": "health_half",   "value": 0.25, "duration": 5,  "emoji": "🩸",  "target_filter": None},
    {"name": "Miasma Vent",          "effect": "dex_reduction", "value": 0.22, "duration": 4,  "emoji": "💨",  "target_filter": None},
    {"name": "Sorrow Rune",          "effect": "int_reduction", "value": 0.22, "duration": 4,  "emoji": "😢",  "target_filter": None},
    {"name": "Doom Glyph",           "effect": "att_reduction", "value": 0.30, "duration": 2,  "emoji": "💀",  "target_filter": None},
    {"name": "Shatter Seal",         "effect": "def_reduction", "value": 0.30, "duration": 2,  "emoji": "🔨",  "target_filter": None},
    {"name": "Void Snare",           "effect": "no_defend",     "value": 1,    "duration": 3,  "emoji": "🕳️", "target_filter": None},
    {"name": "Despair Aura",         "effect": "dex_reduction", "value": 0.30, "duration": 2,  "emoji": "🌑",  "target_filter": None},
]

# ---------------------------------------------------------------------------
# Elemental trap effects
# Each trap is themed around ONE element and targets the elements it has
# advantage over (from ELEMENT_EFFECTIVENESS).  Pets of those target elements
# receive the FULL debuff; all other pets receive a 50 % splash debuff.
#
# Advantage table (attacker → strong against):
#   fire     → ice, plant, necro
#   water    → fire, rock, air
#   electric → water, plant, fighting
#   ice      → air, electric, water
#   plant    → water, air, psychic
#   rock     → electric, fire, ice
#   air      → rock, fighting, electric
#   magic    → psychic, fighting, fire
#   holy     → necro, magic, rock
#   necro    → holy, magic, plant
#   psychic  → holy, necro, magic
#   fighting → ice, psychic, holy
#   basic    → (no advantage — not used as a trap element)
# ---------------------------------------------------------------------------
TRAP_EFFECTS_ELEMENTAL = [
    # ── Fire traps (targets Ice, Plant, Necro) ──────────────────────────────
    {"name": "Scorching Embers",  "effect": "att_reduction", "value": 0.15, "duration": 4,
     "emoji_key": "Fire",
     "target_filter": {"mode": "element", "values": ["ice", "plant", "necro"]}},
    {"name": "Lava Pit",          "effect": "health_half",   "value": 0.40, "duration": 6,
     "emoji_key": "Fire",
     "target_filter": {"mode": "element", "values": ["ice", "plant", "necro"]}},
    {"name": "Flame Rune",        "effect": "def_reduction", "value": 0.15, "duration": 4,
     "emoji_key": "Fire",
     "target_filter": {"mode": "element", "values": ["ice", "plant", "necro"]}},

    # ── Water traps (targets Fire, Rock, Air) ───────────────────────────────
    {"name": "Tidal Surge",       "effect": "dex_reduction", "value": 0.20, "duration": 4,
     "emoji_key": "Water",
     "target_filter": {"mode": "element", "values": ["fire", "rock", "air"]}},
    {"name": "Drowning Pool",     "effect": "health_half",   "value": 0.40, "duration": 6,
     "emoji_key": "Water",
     "target_filter": {"mode": "element", "values": ["fire", "rock", "air"]}},
    {"name": "Rust Flood",        "effect": "att_reduction", "value": 0.15, "duration": 4,
     "emoji_key": "Water",
     "target_filter": {"mode": "element", "values": ["fire", "rock", "air"]}},

    # ── Electric traps (targets Water, Plant, Fighting) ─────────────────────
    {"name": "Static Cage",       "effect": "no_defend",     "value": 1,    "duration": 2,
     "emoji_key": "Electric",
     "target_filter": {"mode": "element", "values": ["water", "plant", "fighting"]}},
    {"name": "Shock Coil",        "effect": "att_reduction", "value": 0.15, "duration": 4,
     "emoji_key": "Electric",
     "target_filter": {"mode": "element", "values": ["water", "plant", "fighting"]}},
    {"name": "Overload Rune",     "effect": "int_reduction", "value": 0.15, "duration": 4,
     "emoji_key": "Electric",
     "target_filter": {"mode": "element", "values": ["water", "plant", "fighting"]}},

    # ── Ice traps (targets Air, Electric, Water) ────────────────────────────
    {"name": "Frost Snare",       "effect": "dex_reduction", "value": 0.20, "duration": 5,
     "emoji_key": "Ice",
     "target_filter": {"mode": "element", "values": ["air", "electric", "water"]}},
    {"name": "Blizzard Glyph",    "effect": "att_reduction", "value": 0.15, "duration": 4,
     "emoji_key": "Ice",
     "target_filter": {"mode": "element", "values": ["air", "electric", "water"]}},
    {"name": "Frozen Floor",      "effect": "def_reduction", "value": 0.15, "duration": 4,
     "emoji_key": "Ice",
     "target_filter": {"mode": "element", "values": ["air", "electric", "water"]}},

    # ── Plant traps (targets Water, Air, Psychic) ───────────────────────────
    {"name": "Entangling Vines",  "effect": "dex_reduction", "value": 0.20, "duration": 5,
     "emoji_key": "Plant",
     "target_filter": {"mode": "element", "values": ["water", "air", "psychic"]}},
    {"name": "Spore Cloud",       "effect": "int_reduction", "value": 0.15, "duration": 4,
     "emoji_key": "Plant",
     "target_filter": {"mode": "element", "values": ["water", "air", "psychic"]}},
    {"name": "Thorn Pit",         "effect": "health_half",   "value": 0.35, "duration": 6,
     "emoji_key": "Plant",
     "target_filter": {"mode": "element", "values": ["water", "air", "psychic"]}},

    # ── Rock traps (targets Electric, Fire, Ice) ────────────────────────────
    {"name": "Boulder Crush",     "effect": "def_reduction", "value": 0.20, "duration": 4,
     "emoji_key": "Rock",
     "target_filter": {"mode": "element", "values": ["electric", "fire", "ice"]}},
    {"name": "Gravel Pit",        "effect": "dex_reduction", "value": 0.15, "duration": 4,
     "emoji_key": "Rock",
     "target_filter": {"mode": "element", "values": ["electric", "fire", "ice"]}},
    {"name": "Stone Seal",        "effect": "no_defend",     "value": 1,    "duration": 2,
     "emoji_key": "Rock",
     "target_filter": {"mode": "element", "values": ["electric", "fire", "ice"]}},

    # ── Air traps (targets Rock, Fighting, Electric) ────────────────────────
    {"name": "Cyclone Vortex",    "effect": "att_reduction", "value": 0.15, "duration": 4,
     "emoji_key": "Air",
     "target_filter": {"mode": "element", "values": ["rock", "fighting", "electric"]}},
    {"name": "Gale Snare",        "effect": "dex_reduction", "value": 0.20, "duration": 4,
     "emoji_key": "Air",
     "target_filter": {"mode": "element", "values": ["rock", "fighting", "electric"]}},
    {"name": "Vacuum Rune",       "effect": "def_reduction", "value": 0.15, "duration": 4,
     "emoji_key": "Air",
     "target_filter": {"mode": "element", "values": ["rock", "fighting", "electric"]}},

    # ── Magic traps (targets Psychic, Fighting, Fire) ───────────────────────
    {"name": "Arcane Hex",        "effect": "int_reduction", "value": 0.20, "duration": 5,
     "emoji_key": "Magic",
     "target_filter": {"mode": "element", "values": ["psychic", "fighting", "fire"]}},
    {"name": "Mana Drain",        "effect": "att_reduction", "value": 0.15, "duration": 4,
     "emoji_key": "Magic",
     "target_filter": {"mode": "element", "values": ["psychic", "fighting", "fire"]}},
    {"name": "Spell Trap",        "effect": "no_defend",     "value": 1,    "duration": 2,
     "emoji_key": "Magic",
     "target_filter": {"mode": "element", "values": ["psychic", "fighting", "fire"]}},

    # ── Holy traps (targets Necro, Magic, Rock) ─────────────────────────────
    {"name": "Radiant Seal",      "effect": "att_reduction", "value": 0.15, "duration": 4,
     "emoji_key": "Holy",
     "target_filter": {"mode": "element", "values": ["necro", "magic", "rock"]}},
    {"name": "Purge Rune",        "effect": "def_reduction", "value": 0.15, "duration": 4,
     "emoji_key": "Holy",
     "target_filter": {"mode": "element", "values": ["necro", "magic", "rock"]}},
    {"name": "Smite Trap",        "effect": "health_half",   "value": 0.35, "duration": 6,
     "emoji_key": "Holy",
     "target_filter": {"mode": "element", "values": ["necro", "magic", "rock"]}},

    # ── Necro traps (targets Holy, Magic, Plant) ────────────────────────────
    {"name": "Soul Drain",        "effect": "health_half",   "value": 0.40, "duration": 6,
     "emoji_key": "Necro",
     "target_filter": {"mode": "element", "values": ["holy", "magic", "plant"]}},
    {"name": "Curse Glyph",       "effect": "att_reduction", "value": 0.15, "duration": 4,
     "emoji_key": "Necro",
     "target_filter": {"mode": "element", "values": ["holy", "magic", "plant"]}},
    {"name": "Decay Trap",        "effect": "def_reduction", "value": 0.15, "duration": 4,
     "emoji_key": "Necro",
     "target_filter": {"mode": "element", "values": ["holy", "magic", "plant"]}},

    # ── Psychic traps (targets Holy, Necro, Magic) ──────────────────────────
    {"name": "Mind Shatter",      "effect": "int_reduction", "value": 0.20, "duration": 5,
     "emoji_key": "Psychic",
     "target_filter": {"mode": "element", "values": ["holy", "necro", "magic"]}},
    {"name": "Illusion Snare",    "effect": "no_defend",     "value": 1,    "duration": 2,
     "emoji_key": "Psychic",
     "target_filter": {"mode": "element", "values": ["holy", "necro", "magic"]}},
    {"name": "Psionic Rune",      "effect": "att_reduction", "value": 0.15, "duration": 4,
     "emoji_key": "Psychic",
     "target_filter": {"mode": "element", "values": ["holy", "necro", "magic"]}},

    # ── Fighting traps (targets Ice, Psychic, Holy) ─────────────────────────
    {"name": "Iron Cage",         "effect": "dex_reduction", "value": 0.20, "duration": 4,
     "emoji_key": "Fighting",
     "target_filter": {"mode": "element", "values": ["ice", "psychic", "holy"]}},
    {"name": "Brawler's Pit",     "effect": "def_reduction", "value": 0.15, "duration": 4,
     "emoji_key": "Fighting",
     "target_filter": {"mode": "element", "values": ["ice", "psychic", "holy"]}},
    {"name": "Fury Rune",         "effect": "att_reduction", "value": 0.15, "duration": 4,
     "emoji_key": "Fighting",
     "target_filter": {"mode": "element", "values": ["ice", "psychic", "holy"]}},
]

# ---------------------------------------------------------------------------
# Type trap effects
# Type triangle: Flying > Land > Swimming > Flying
# Each trap targets the type it has advantage over.
# ---------------------------------------------------------------------------
TRAP_EFFECTS_TYPE = [
    # Flying traps Land pets
    {"name": "Aerial Dive Trap",  "effect": "att_reduction", "value": 0.15, "duration": 4,
     "emoji_key": "Flying",
     "target_filter": {"mode": "type", "values": ["land"]}},
    {"name": "Wind Snare",        "effect": "dex_reduction", "value": 0.20, "duration": 4,
     "emoji_key": "Flying",
     "target_filter": {"mode": "type", "values": ["land"]}},
    {"name": "Sky Ambush",        "effect": "def_reduction", "value": 0.15, "duration": 4,
     "emoji_key": "Flying",
     "target_filter": {"mode": "type", "values": ["land"]}},

    # Land traps Swimming pets
    {"name": "Mudslide Trap",     "effect": "dex_reduction", "value": 0.20, "duration": 4,
     "emoji_key": "Land",
     "target_filter": {"mode": "type", "values": ["swimming"]}},
    {"name": "Earthen Cage",      "effect": "def_reduction", "value": 0.15, "duration": 4,
     "emoji_key": "Land",
     "target_filter": {"mode": "type", "values": ["swimming"]}},
    {"name": "Terrain Ambush",    "effect": "att_reduction", "value": 0.15, "duration": 4,
     "emoji_key": "Land",
     "target_filter": {"mode": "type", "values": ["swimming"]}},

    # Swimming traps Flying pets
    {"name": "Undertow Snare",    "effect": "att_reduction", "value": 0.15, "duration": 4,
     "emoji_key": "Swimming",
     "target_filter": {"mode": "type", "values": ["flying"]}},
    {"name": "Whirlpool Trap",    "effect": "dex_reduction", "value": 0.20, "duration": 4,
     "emoji_key": "Swimming",
     "target_filter": {"mode": "type", "values": ["flying"]}},
    {"name": "Depth Ambush",      "effect": "def_reduction", "value": 0.15, "duration": 4,
     "emoji_key": "Swimming",
     "target_filter": {"mode": "type", "values": ["flying"]}},
]

# ---------------------------------------------------------------------------
# Generic shrine effects — 50 entries, apply to ALL party members
# ---------------------------------------------------------------------------
SHRINE_EFFECTS_GENERIC = [
    # ── Attack boosts ────────────────────────────────────────────────────────
    {"name": "Shrine of Strength",      "effect": "att_boost",    "value": 0.15, "duration": 5,  "emoji": "⚔️",  "target_filter": None},
    {"name": "Shrine of Fury",          "effect": "att_boost",    "value": 0.20, "duration": 4,  "emoji": "🔥",  "target_filter": None},
    {"name": "Shrine of the Warlord",   "effect": "att_boost",    "value": 0.25, "duration": 3,  "emoji": "🗡️", "target_filter": None},
    {"name": "Shrine of Valor",         "effect": "att_boost",    "value": 0.12, "duration": 6,  "emoji": "🏆",  "target_filter": None},
    {"name": "Shrine of the Berserker", "effect": "att_boost",    "value": 0.30, "duration": 2,  "emoji": "😤",  "target_filter": None},
    {"name": "Shrine of Conquest",      "effect": "att_boost",    "value": 0.18, "duration": 5,  "emoji": "👑",  "target_filter": None},
    {"name": "Shrine of the Blade",     "effect": "att_boost",    "value": 0.22, "duration": 4,  "emoji": "🗡️", "target_filter": None},
    {"name": "Shrine of Carnage",       "effect": "att_boost",    "value": 0.35, "duration": 2,  "emoji": "💥",  "target_filter": None},

    # ── Defense boosts ───────────────────────────────────────────────────────
    {"name": "Shrine of Protection",    "effect": "def_boost",    "value": 0.15, "duration": 5,  "emoji": "🛡️", "target_filter": None},
    {"name": "Shrine of the Bulwark",   "effect": "def_boost",    "value": 0.20, "duration": 4,  "emoji": "🏰",  "target_filter": None},
    {"name": "Shrine of Iron Will",     "effect": "def_boost",    "value": 0.25, "duration": 3,  "emoji": "⚙️",  "target_filter": None},
    {"name": "Shrine of the Sentinel",  "effect": "def_boost",    "value": 0.12, "duration": 6,  "emoji": "🗼",  "target_filter": None},
    {"name": "Shrine of Endurance",     "effect": "def_boost",    "value": 0.18, "duration": 5,  "emoji": "🪨",  "target_filter": None},
    {"name": "Shrine of the Fortress",  "effect": "def_boost",    "value": 0.30, "duration": 2,  "emoji": "🏯",  "target_filter": None},
    {"name": "Shrine of Resilience",    "effect": "def_boost",    "value": 0.22, "duration": 4,  "emoji": "💪",  "target_filter": None},

    # ── Dexterity boosts ─────────────────────────────────────────────────────
    {"name": "Shrine of Agility",       "effect": "dex_boost",    "value": 0.15, "duration": 5,  "emoji": "💨",  "target_filter": None},
    {"name": "Shrine of the Swift",     "effect": "dex_boost",    "value": 0.20, "duration": 4,  "emoji": "⚡",  "target_filter": None},
    {"name": "Shrine of Haste",         "effect": "dex_boost",    "value": 0.25, "duration": 3,  "emoji": "🏃",  "target_filter": None},
    {"name": "Shrine of the Wind",      "effect": "dex_boost",    "value": 0.12, "duration": 6,  "emoji": "🌬️", "target_filter": None},
    {"name": "Shrine of Reflexes",      "effect": "dex_boost",    "value": 0.18, "duration": 5,  "emoji": "🎯",  "target_filter": None},
    {"name": "Shrine of the Phantom",   "effect": "dex_boost",    "value": 0.30, "duration": 2,  "emoji": "👻",  "target_filter": None},
    {"name": "Shrine of Evasion",       "effect": "dex_boost",    "value": 0.22, "duration": 4,  "emoji": "🌀",  "target_filter": None},

    # ── Intelligence boosts ──────────────────────────────────────────────────
    {"name": "Shrine of Wisdom",        "effect": "int_boost",    "value": 0.15, "duration": 5,  "emoji": "📖",  "target_filter": None},
    {"name": "Shrine of the Sage",      "effect": "int_boost",    "value": 0.20, "duration": 4,  "emoji": "🧙",  "target_filter": None},
    {"name": "Shrine of Insight",       "effect": "int_boost",    "value": 0.25, "duration": 3,  "emoji": "🔮",  "target_filter": None},
    {"name": "Shrine of the Scholar",   "effect": "int_boost",    "value": 0.12, "duration": 6,  "emoji": "📚",  "target_filter": None},
    {"name": "Shrine of Clarity",       "effect": "int_boost",    "value": 0.18, "duration": 5,  "emoji": "💡",  "target_filter": None},
    {"name": "Shrine of the Oracle",    "effect": "int_boost",    "value": 0.30, "duration": 2,  "emoji": "🌟",  "target_filter": None},
    {"name": "Shrine of Foresight",     "effect": "int_boost",    "value": 0.22, "duration": 4,  "emoji": "🔭",  "target_filter": None},

    # ── Health boosts ────────────────────────────────────────────────────────
    {"name": "Shrine of Vitality",      "effect": "health_boost", "value": 0.25, "duration": 10, "emoji": "❤️",  "target_filter": None},
    {"name": "Shrine of Renewal",       "effect": "health_boost", "value": 0.20, "duration": 8,  "emoji": "💚",  "target_filter": None},
    {"name": "Shrine of the Healer",    "effect": "health_boost", "value": 0.30, "duration": 6,  "emoji": "⚕️",  "target_filter": None},
    {"name": "Shrine of Restoration",   "effect": "health_boost", "value": 0.15, "duration": 10, "emoji": "🌿",  "target_filter": None},
    {"name": "Shrine of Mending",       "effect": "health_boost", "value": 0.35, "duration": 5,  "emoji": "🩹",  "target_filter": None},
    {"name": "Shrine of the Phoenix",   "effect": "health_boost", "value": 0.40, "duration": 4,  "emoji": "🦅",  "target_filter": None},
    {"name": "Shrine of Regeneration",  "effect": "health_boost", "value": 0.25, "duration": 7,  "emoji": "🌱",  "target_filter": None},

    # ── Charge boosts ────────────────────────────────────────────────────────
    {"name": "Shrine of Fortune",       "effect": "charge_boost", "value": 0.5,  "duration": 3,  "emoji": "✨",  "target_filter": None},
    {"name": "Shrine of the Catalyst",  "effect": "charge_boost", "value": 1.0,  "duration": 2,  "emoji": "⚗️",  "target_filter": None},
    {"name": "Shrine of Momentum",      "effect": "charge_boost", "value": 0.75, "duration": 3,  "emoji": "🌊",  "target_filter": None},
    {"name": "Shrine of the Surge",     "effect": "charge_boost", "value": 1.5,  "duration": 1,  "emoji": "⚡",  "target_filter": None},
    {"name": "Shrine of Readiness",     "effect": "charge_boost", "value": 0.5,  "duration": 4,  "emoji": "🎯",  "target_filter": None},

    # ── Thematic mixed-flavour (still single effect, varied stats) ───────────
    {"name": "Shrine of the Dungeon",   "effect": "def_boost",    "value": 0.15, "duration": 6,  "emoji": "🏚️", "target_filter": None},
    {"name": "Shrine of the Fallen",    "effect": "att_boost",    "value": 0.15, "duration": 6,  "emoji": "⚰️",  "target_filter": None},
    {"name": "Shrine of Shadows",       "effect": "dex_boost",    "value": 0.15, "duration": 6,  "emoji": "🌑",  "target_filter": None},
    {"name": "Shrine of the Ancients",  "effect": "int_boost",    "value": 0.15, "duration": 6,  "emoji": "🗿",  "target_filter": None},
    {"name": "Shrine of Perseverance",  "effect": "health_boost", "value": 0.20, "duration": 8,  "emoji": "🌄",  "target_filter": None},
    {"name": "Shrine of the Wanderer",  "effect": "dex_boost",    "value": 0.18, "duration": 5,  "emoji": "🧭",  "target_filter": None},
    {"name": "Shrine of Sacrifice",     "effect": "att_boost",    "value": 0.40, "duration": 2,  "emoji": "🩸",  "target_filter": None},
    {"name": "Shrine of the Colossus",  "effect": "def_boost",    "value": 0.35, "duration": 2,  "emoji": "🗽",  "target_filter": None},
    {"name": "Shrine of Cunning",       "effect": "int_boost",    "value": 0.35, "duration": 2,  "emoji": "🦊",  "target_filter": None},
]

# ---------------------------------------------------------------------------
# Elemental shrine effects
# Each shrine blesses 2-3 thematically related elements.
# ONLY pets whose primary element matches receive the buff.
# ---------------------------------------------------------------------------
SHRINE_EFFECTS_ELEMENTAL = [
    # ── Inferno Shrine (Fire + Necro) ────────────────────────────────────────
    {"name": "Inferno Shrine",       "effect": "att_boost",    "value": 0.20, "duration": 5,
     "emoji_key": "Fire",
     "target_filter": {"mode": "element", "values": ["fire", "necro"]}},
    {"name": "Pyre Shrine",          "effect": "health_boost", "value": 0.25, "duration": 6,
     "emoji_key": "Fire",
     "target_filter": {"mode": "element", "values": ["fire", "necro"]}},
    {"name": "Ember Shrine",         "effect": "charge_boost", "value": 0.5,  "duration": 3,
     "emoji_key": "Fire",
     "target_filter": {"mode": "element", "values": ["fire", "necro"]}},

    # ── Tidal Shrine (Water + Ice) ───────────────────────────────────────────
    {"name": "Tidal Shrine",         "effect": "def_boost",    "value": 0.20, "duration": 5,
     "emoji_key": "Water",
     "target_filter": {"mode": "element", "values": ["water", "ice"]}},
    {"name": "Glacier Shrine",       "effect": "att_boost",    "value": 0.20, "duration": 5,
     "emoji_key": "Ice",
     "target_filter": {"mode": "element", "values": ["water", "ice"]}},
    {"name": "Frost Shrine",         "effect": "dex_boost",    "value": 0.20, "duration": 5,
     "emoji_key": "Ice",
     "target_filter": {"mode": "element", "values": ["water", "ice"]}},

    # ── Storm Shrine (Electric + Air) ────────────────────────────────────────
    {"name": "Storm Shrine",         "effect": "att_boost",    "value": 0.20, "duration": 5,
     "emoji_key": "Electric",
     "target_filter": {"mode": "element", "values": ["electric", "air"]}},
    {"name": "Tempest Shrine",       "effect": "dex_boost",    "value": 0.20, "duration": 5,
     "emoji_key": "Air",
     "target_filter": {"mode": "element", "values": ["electric", "air"]}},
    {"name": "Gale Shrine",          "effect": "charge_boost", "value": 0.5,  "duration": 3,
     "emoji_key": "Air",
     "target_filter": {"mode": "element", "values": ["electric", "air"]}},

    # ── Nature Shrine (Plant + Rock) ─────────────────────────────────────────
    {"name": "Nature Shrine",        "effect": "health_boost", "value": 0.30, "duration": 6,
     "emoji_key": "Plant",
     "target_filter": {"mode": "element", "values": ["plant", "rock"]}},
    {"name": "Overgrowth Shrine",    "effect": "def_boost",    "value": 0.20, "duration": 5,
     "emoji_key": "Plant",
     "target_filter": {"mode": "element", "values": ["plant", "rock"]}},
    {"name": "Stone Shrine",         "effect": "att_boost",    "value": 0.20, "duration": 5,
     "emoji_key": "Rock",
     "target_filter": {"mode": "element", "values": ["plant", "rock"]}},

    # ── Celestial Shrine (Holy + Magic + Psychic) ────────────────────────────
    {"name": "Celestial Shrine",     "effect": "att_boost",    "value": 0.20, "duration": 5,
     "emoji_key": "Holy",
     "target_filter": {"mode": "element", "values": ["holy", "magic", "psychic"]}},
    {"name": "Arcane Shrine",        "effect": "int_boost",    "value": 0.20, "duration": 5,
     "emoji_key": "Magic",
     "target_filter": {"mode": "element", "values": ["holy", "magic", "psychic"]}},
    {"name": "Oracle Shrine",        "effect": "charge_boost", "value": 0.5,  "duration": 3,
     "emoji_key": "Psychic",
     "target_filter": {"mode": "element", "values": ["holy", "magic", "psychic"]}},

    # ── Shadow Shrine (Necro + Fighting) ─────────────────────────────────────
    {"name": "Shadow Shrine",        "effect": "att_boost",    "value": 0.20, "duration": 5,
     "emoji_key": "Necro",
     "target_filter": {"mode": "element", "values": ["necro", "fighting"]}},
    {"name": "Bone Shrine",          "effect": "def_boost",    "value": 0.20, "duration": 5,
     "emoji_key": "Necro",
     "target_filter": {"mode": "element", "values": ["necro", "fighting"]}},
    {"name": "Warrior Shrine",       "effect": "dex_boost",    "value": 0.20, "duration": 5,
     "emoji_key": "Fighting",
     "target_filter": {"mode": "element", "values": ["necro", "fighting"]}},
]

# ---------------------------------------------------------------------------
# Type shrine effects
# Each shrine blesses ONE type (Flying / Land / Swimming).
# ONLY pets whose category matches receive the buff.
# ---------------------------------------------------------------------------
SHRINE_EFFECTS_TYPE = [
    # Flying shrines
    {"name": "Skyward Shrine",    "effect": "att_boost",    "value": 0.20, "duration": 5,
     "emoji_key": "Flying",
     "target_filter": {"mode": "type", "values": ["flying"]}},
    {"name": "Aerie Shrine",      "effect": "dex_boost",    "value": 0.20, "duration": 5,
     "emoji_key": "Flying",
     "target_filter": {"mode": "type", "values": ["flying"]}},
    {"name": "Feather Shrine",    "effect": "charge_boost", "value": 0.5,  "duration": 3,
     "emoji_key": "Flying",
     "target_filter": {"mode": "type", "values": ["flying"]}},

    # Land shrines
    {"name": "Earthen Shrine",    "effect": "def_boost",    "value": 0.20, "duration": 5,
     "emoji_key": "Land",
     "target_filter": {"mode": "type", "values": ["land"]}},
    {"name": "Bedrock Shrine",    "effect": "health_boost", "value": 0.30, "duration": 6,
     "emoji_key": "Land",
     "target_filter": {"mode": "type", "values": ["land"]}},
    {"name": "Terrain Shrine",    "effect": "att_boost",    "value": 0.20, "duration": 5,
     "emoji_key": "Land",
     "target_filter": {"mode": "type", "values": ["land"]}},

    # Swimming shrines
    {"name": "Abyssal Shrine",    "effect": "def_boost",    "value": 0.20, "duration": 5,
     "emoji_key": "Swimming",
     "target_filter": {"mode": "type", "values": ["swimming"]}},
    {"name": "Current Shrine",    "effect": "dex_boost",    "value": 0.20, "duration": 5,
     "emoji_key": "Swimming",
     "target_filter": {"mode": "type", "values": ["swimming"]}},
    {"name": "Tide Shrine",       "effect": "health_boost", "value": 0.30, "duration": 6,
     "emoji_key": "Swimming",
     "target_filter": {"mode": "type", "values": ["swimming"]}},
]

# ---------------------------------------------------------------------------
# Flat lists used by _generate_floor (backward-compat names kept)
# ---------------------------------------------------------------------------
# Resolve emoji_key → Discord mention string at module load time




# Chest types (matching Loot Market)
CHEST_TYPES = [
    {"name": "Chest 1", "emoji": "chest1", "rarity_pool": ["Common", "Uncommon"], "count": 1},
    {"name": "Chest 2", "emoji": "chest2", "rarity_pool": ["Rare"], "count": 1},
    {"name": "Chest 3", "emoji": "chest3", "rarity_pool": ["Epic"], "count": 1},
    {"name": "Chest 4", "emoji": "chest4", "rarity_pool": ["Uncommon", "Rare", "Epic", "Mythic"], "count": 2},
]


class DungeonCrawl:
    """Main dungeon crawl manager"""
    
    def __init__(self, party_leader_id: int, db_path: str = "Databases/Pets/dungeon.db"):
        self.party_leader_id = party_leader_id
        self.db_path = db_path
        self.dungeon_id = None
        self.party_members = []
        self.current_floor = 1
        self.current_room = 1
        self.dungeon_state = {}
        self.party_buffs = {}  # {user_id: [buff_dict, ...]}
        self.rooms_cleared = 0
        self.ready_users = set()  # Track users ready to continue
        self.dungeon_type = "Camp"  # Default dungeon type
        
    async def initialize_database(self):
        """Create dungeon tables if they don't exist"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS dungeons (
                    dungeon_id TEXT PRIMARY KEY,
                    party_leader_id TEXT NOT NULL,
                    party_members TEXT NOT NULL,
                    current_floor INTEGER DEFAULT 1,
                    current_room INTEGER DEFAULT 1,
                    dungeon_state TEXT,
                    party_buffs TEXT,
                    ready_users TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed INTEGER DEFAULT 0
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS dungeon_progress (
                    dungeon_id TEXT NOT NULL,
                    floor INTEGER NOT NULL,
                    room INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    event_data TEXT,
                    completed INTEGER DEFAULT 0,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (dungeon_id, floor, room)
                )
            ''')
            
            # NEW: Add dungeon_type column
            try:
                await db.execute("ALTER TABLE dungeons ADD COLUMN dungeon_type TEXT DEFAULT 'Crypt'")
            except aiosqlite.OperationalError:
                pass  # Column already exists
            
            # NEW: Add event_history column
            try:
                await db.execute("ALTER TABLE dungeons ADD COLUMN event_history TEXT DEFAULT '[]'")
            except aiosqlite.OperationalError:
                pass
            
            # NEW: Create story cooldowns table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS dungeon_story_cooldowns (
                    dungeon_id TEXT NOT NULL,
                    room_key TEXT NOT NULL,
                    fail_until REAL NOT NULL,
                    PRIMARY KEY (dungeon_id, room_key)
                )
            ''')
            
            await db.commit()
    
    def calculate_xp_reward(self, pet: Dict, room_type: str, room_number: int) -> int:
        """
        Calculate XP reward using universal formula:
        (pet_level / equipment_multiplier) * floor_number * room_number * room_type_plug
        """
        pet_level = pet.get('level', 1)
        equipment_multiplier = pet.get('equipment_multiplier', 1.0)
        
        # Get XP plug for room type
        xp_plug = XP_PLUGS.get(room_type, 25)
        
        # Calculate XP
        xp_reward = int((pet_level / equipment_multiplier) * self.current_floor * room_number * xp_plug)
        
        return max(10, xp_reward)  # Minimum 10 XP

    def check_element_advantage(self, pet_element: str, target_element: str) -> bool:
        """Check if pet element has advantage over target element.

        ELEMENT_EFFECTIVENESS maps {attacker_elem: {defender_elem: multiplier}}.
        An advantage exists when the multiplier for the target element is > 1.0.
        """
        attacker_elem = pet_element.lower()
        defender_elem = target_element.lower()
        elem_row = DamageCalculator.ELEMENT_EFFECTIVENESS.get(attacker_elem, {})
        return elem_row.get(defender_elem, 1.0) > 1.0

    def check_type_advantage(self, pet_type: str, target_type: str) -> bool:
        """Check if pet type has advantage over target type"""
        type_map = {
            'flying': ['land'],
            'land': ['swimming'],
            'swimming': ['flying']
        }
        return target_type.lower() in type_map.get(pet_type.lower(), [])

    def add_event_to_history(self, room_num: int, event_type: str, summary: str, chest_emoji: str = None):
        """Add event to dungeon history (keep last 5)
        
        Args:
            room_num: Room number
            event_type: Type of event
            summary: Text summary
            chest_emoji: Optional chest emoji for chest events
        """
        if 'event_history' not in self.dungeon_state:
            self.dungeon_state['event_history'] = []
        
        # Store as structured data instead of just a string
        event_data = {
            "room": room_num,
            "floor": self.current_floor,
            "event_type": event_type,
            "summary": summary
        }
        
        # Add chest_emoji if provided (for chest events)
        if chest_emoji:
            event_data["chest_emoji"] = chest_emoji
        
        self.dungeon_state['event_history'].append(event_data)
        
        # Keep only last 5 events
        if len(self.dungeon_state['event_history']) > 5:
            self.dungeon_state['event_history'] = self.dungeon_state['event_history'][-5:]
    
    def _generate_story_segment_sync(self, floor_num: int, room_num: int, dungeon_type: str) -> Dict:
        """Generate AI story segment for dungeon (synchronous)"""
        # Get recent event history for context
        event_history = self.dungeon_state.get('event_history', [])
        recent_events = event_history[-3:] if len(event_history) >= 3 else event_history
        
        dungeon_descriptions = {
            "Camp": "wilderness campsite with tents, campfires, forest creatures, outdoor survival, trail paths",
            "Bonfire": "crackling flames, gathering circles, nighttime warmth, storytelling, ember glow",
            "Beach": "sandy shores, ocean waves, tropical creatures, seashells, palm trees, coastal breeze",
            "Forest": "dense woodland, towering trees, wildlife, moss-covered paths, dappled sunlight",
            "Hot Air Balloon": "floating high above, cloud islands, wind currents, aerial views, basket adventures",
            "Cruiseship": "ship decks, ocean voyage, luxurious rooms, nautical adventures, sea horizon",
            "Mountain": "rocky peaks, cliff faces, thin air, alpine challenges, mountain creatures, snow caps",
            "Gym": "training equipment, workout challenges, strength tests, fitness obstacles, athletic trials",
            "Graveyard": "weathered tombstones, ancient crypts, misty pathways, memorial stones, solemn silence",
            "Festival": "colorful tents, carnival games, festive music, celebration atmosphere, joyful crowds",
            "Glacier": "frozen expanse, ice formations, frigid winds, crevasses, crystalline beauty",
            "Pyramids": "ancient stone corridors, hieroglyphs, desert sand, hidden chambers, pharaoh's legacy"
        }
        
        theme = dungeon_descriptions.get(dungeon_type, "mysterious dungeon passages")
        recent_context = " Recent events: " + ", ".join(recent_events) if recent_events else ""
        
        prompt = f"""
Generate a dungeon story segment for a {dungeon_type} dungeon, floor {floor_num}, room {room_num}.

DUNGEON THEMING: {theme}
{recent_context}

Create a single meaningful story moment with:
1. A 2-3 sentence narrative scene themed to {dungeon_type}
2. THREE choices for the player, each using different pet stats:
   - Choice 1: A physical/forceful approach (uses ATT + DEF)
   - Choice 2: A skillful/clever approach (uses DEX + INT)  
   - Choice 3: An enduring/patient approach (uses ENE + HAP)
3. Brief descriptions of what success and failure look like

REQUIREMENTS:
- Reference the {dungeon_type} setting specifically
- Choices must make thematic sense for the scene
- difficulty_modifier between 0.8 and 1.4

Return ONLY valid JSON:
{{
  "scene": "Scene description here",
  "choices": {{
    "1": "Physical approach description",
    "2": "Skillful approach description", 
    "3": "Enduring approach description"
  }},
  "difficulty_modifier": 1.0,
  "success_flavor": "What happens when you succeed",
  "fail_flavor": "What happens when you fail"
}}
"""
        
        try:
            # Use the same AI function as quests
            from Systems.Functions.local_ai import chat_complete_json_sync
            result = chat_complete_json_sync(prompt)
            return result
        except Exception as e:
            # Fallback to generic story segment
            return {
                "scene": f"You encounter a mysterious passage in the {dungeon_type}. The way forward is unclear.",
                "choices": {
                    "1": "Force your way through with strength",
                    "2": "Find a clever path around the obstacle",
                    "3": "Wait patiently for the right moment"
                },
                "difficulty_modifier": 1.0,
                "success_flavor": "You successfully navigate the passage.",
                "fail_flavor": "The passage proves too challenging."
            }
    
    def _generate_puzzle_room_sync(self, floor_num: int, dungeon_type: str) -> Dict:
        """Generate puzzle room from templates"""
        puzzle_templates = {
            "Crypt": [
                {"desc": "A pressure plate puzzle - stepping stones must be crossed in the correct order.", "hints": "Ancient runes mark the safe path."},
                {"desc": "A lock with three spinning rings - find the symbol sequence.", "hints": "The symbols match those on nearby sarcophagi."},
                {"desc": "An ancient scale balanced with gem-weights - add the correct weight.", "hints": "The inscription mentions 'balance of the dead'."},
                {"desc": "A sarcophagus sealed with riddle runes.", "hints": "The answer is the number of bones in the room."},
                {"desc": "A contraption that opens when three levers are pulled in sequence.", "hints": "The sequence is carved into the floor."},
                {"desc": "A mural depicting a ritual - mime the posture to unlock the passage.", "hints": "The posture shows reverence to the dead."}
            ],
            "Volcanic Depths": [
                {"desc": "Lava flows block the path - redirect them using ancient channels.", "hints": "The channels form a pattern of fire runes."},
                {"desc": "Heat-sensitive crystals must be cooled in the right order.", "hints": "Start from the hottest and work down."},
                {"desc": "A flame gate that opens only when the correct torch sequence is lit.", "hints": "The pattern follows the rising sun."},
                {"desc": "Pressure vents must be sealed to stop the lava flow.", "hints": "Seal them from smallest to largest."},
                {"desc": "A bridge of unstable volcanic rock - find the safe path.", "hints": "The darker stones are more stable."},
                {"desc": "Molten metal must be poured into the correct mold.", "hints": "The mold shape matches a nearby demon statue."}
            ],
            "Frozen Cavern": [
                {"desc": "Ice pillars must be melted in sequence to open the path.", "hints": "Melt them in the order they froze."},
                {"desc": "A frozen lock requires the right combination of heat sources.", "hints": "Too much heat will crack the mechanism."},
                {"desc": "Slippery ice paths - find the route that doesn't lead to a fall.", "hints": "Follow the path with the most snow coverage."},
                {"desc": "Icicles hang precariously - disturb them in the right order to create a bridge.", "hints": "Start from the thickest icicles."},
                {"desc": "A snow drift blocks the way - dig through at the right spot.", "hints": "The wind patterns show the weakest point."},
                {"desc": "Frozen mirrors must reflect light to unlock the gate.", "hints": "The beam must hit all mirrors in sequence."}
            ],
            "Arcane Tower": [
                {"desc": "Magical runes must be activated in the correct sequence.", "hints": "The sequence follows the elements: fire, water, earth, air."},
                {"desc": "Floating platforms move in patterns - time your jumps correctly.", "hints": "The platforms follow a mathematical sequence."},
                {"desc": "Books on shelves form a riddle - arrange them in the right order.", "hints": "Chronological order by author's birth year."},
                {"desc": "A spell circle requires the correct components placed in order.", "hints": "Start with the base element, build up to complex."},
                {"desc": "Enchanted doors respond only to specific magical gestures.", "hints": "The gestures are drawn on nearby scrolls."},
                {"desc": "A constellation puzzle - connect the stars in the right order.", "hints": "Follow the mythological hero's journey."}
            ],
            "Haunted Forest": [
                {"desc": "Twisted roots form a maze - find the path through.", "hints": "The healthy roots lead to safety."},
                {"desc": "Fairy lights flicker in patterns - follow the right sequence.", "hints": "The lights move in the direction of the wind."},
                {"desc": "Ancient trees whisper riddles - answer correctly to pass.", "hints": "The answer is always something found in nature."},
                {"desc": "Mushroom circles block the way - step only on the safe ones.", "hints": "Avoid the glowing mushrooms."},
                {"desc": "A cursed tree must be appeased with the right offering.", "hints": "The tree craves water, not blood."},
                {"desc": "Animal tracks lead in multiple directions - follow the right trail.", "hints": "Follow the prints that go uphill."}
            ],
            "Sky Fortress": [
                {"desc": "Wind currents must be redirected to activate mechanisms.", "hints": "Use the metal vanes to redirect the flow."},
                {"desc": "Cloud bridges appear only when lightning strikes correctly.", "hints": "The timing follows the thunder count."},
                {"desc": "Aerial platforms must be balanced with weights.", "hints": "Equal weight on both sides creates stability."},
                {"desc": "A wind chime puzzle - ring them in harmonic sequence.", "hints": "Follow musical scale: do, re, mi."},
                {"desc": "Floating debris must be arranged to create a path.", "hints": "Stack from largest to smallest for stability."},
                {"desc": "Thunder pylons must be activated in the right order.", "hints": "Follow the electrical current flow."}
            ],
            "Sunken Temple": [
                {"desc": "Water channels must be opened in sequence to drain rooms.", "hints": "Start with the highest channel first."},
                {"desc": "Coral formations hide the correct path - break the right ones.", "hints": "The dead coral is safe to break."},
                {"desc": "Ancient murals show a diving ritual - perform it correctly.", "hints": "Hold your breath at the right moment."},
                {"desc": "Underwater levers must be pulled in a specific order.", "hints": "The barnacles show which were pulled recently."},
                {"desc": "Bioluminescent algae lights the way - follow the right glow.", "hints": "The brightest path is safest."},
                {"desc": "A tidal lock opens only at the right water level.", "hints": "Wait for the tide to reach the middle mark."}
            ],
            "Shadow Realm": [
                {"desc": "Mirrors reflect false paths - identify the real exit.", "hints": "Your reflection behaves differently in the real mirror."},
                {"desc": "Shadows shift and change - follow your own shadow to safety.", "hints": "Your shadow never lies, even here."},
                {"desc": "Illusion layers must be dispelled in order.", "hints": "Dispel from outermost to innermost."},
                {"desc": "A dimensional rift shows multiple futures - choose the right timeline.", "hints": "The future where you survive shows you resting."},
                {"desc": "Void cracks threaten to swallow you - step only on solid ground.", "hints": "Test each step before committing weight."},
                {"desc": "Psychic echoes give false directions - trust your instincts.", "hints": "The quietest path is the true one."}
            ],
            "Holy Sanctum": [
                {"desc": "Sacred altars must be blessed in the order of virtues.", "hints": "Faith, Hope, Charity - the traditional order."},
                {"desc": "Divine light beams must converge on the central altar.", "hints": "Use the prisms to redirect light."},
                {"desc": "Ancient hymns provide clues - sing them in the right order.", "hints": "Start with the morning prayer."},
                {"desc": "Angelic statues must face the correct directions.", "hints": "All should face the rising sun."},
                {"desc": "Holy water must be poured in the correct basin.", "hints": "Pour from highest to lowest elevation."},
                {"desc": "Celestial symbols align only at certain times - wait for the right moment.", "hints": "When three symbols align, proceed."}
            ],
            "Gladiator Pit": [
                {"desc": "Weapon racks must be arranged by combat style.", "hints": "Group by weapon weight and reach."},
                {"desc": "Training dummies reveal the correct attack combination.", "hints": "Strike high, low, then middle."},
                {"desc": "Arena gates open only when the crowd is satisfied.", "hints": "Perform a display of strength."},
                {"desc": "Combat statues show fighting stances - replicate them in order.", "hints": "Follow the progression from novice to master."},
                {"desc": "Blood-stained sand marks the victors' path.", "hints": "Follow the trail with the most dried blood."},
                {"desc": "Champion's banners hang in order of victory - arrange them correctly.", "hints": "Chronological order by date on the banners."}
            ],
            "Crystal Labyrinth": [
                {"desc": "Gem veins pulse with energy - follow the right vein to the exit.", "hints": "The brightest vein leads forward."},
                {"desc": "Crystal formations must be struck in harmonic sequence.", "hints": "Match the tone to the entrance crystal."},
                {"desc": "Stone guardians activate when approached - find the safe path.", "hints": "The guardians with closed eyes are dormant."},
                {"desc": "Glittering walls create illusions - find the real passage.", "hints": "Run your hand along the wall; illusions have no texture."},
                {"desc": "Precious minerals form a pattern - identify the correct sequence.", "hints": "Follow the mineral hardness scale."},
                {"desc": "Underground streams flow to the exit - but which one?", "hints": "The clearest water flows from the purest source."}
            ],
            "Storm Wastes": [
                {"desc": "Electrical conduits must be connected in the right order.", "hints": "Follow the direction of current flow."},
                {"desc": "Floating debris creates a path, but only briefly.", "hints": "Jump when the lightning illuminates the next platform."},
                {"desc": "Storm crystals overload if touched wrong - disable them safely.", "hints": "Drain the largest crystal first."},
                {"desc": "Chaos energy swirls create illusions - find the real path.", "hints": "The path that flickers least is most real."},
                {"desc": "Energy pylons must be activated in sequence to stabilize the area.", "hints": "Create a circuit from north to south."},
                {"desc": "Lightning strikes in patterns - predict the safe zones.", "hints": "Lightning never strikes the same spot twice in a row."}
            ]
        }
        
        templates = puzzle_templates.get(dungeon_type, puzzle_templates["Crypt"])
        puzzle = random.choice(templates)
        
        return {
            "description": puzzle["desc"],
            "hints": puzzle["hints"],
            "choices": {
                "1": "Use brute force and strength to solve it",
                "2": "Apply careful observation and logic",
                "3": "Wait patiently and let the pattern reveal itself"
            },
            "difficulty_modifier": 0.8 + (floor_num - 1) * 0.1  # Gets harder each floor
        }
    
    def _generate_merchant_items_sync(self, floor_num: int) -> List[Dict]:
        """Generate 5 random items for merchant"""
        equipment_data = _load_equipment_data()
        merchant_items = []
        
        for _ in range(5):
            category = random.choice(['Monster', 'Gem', 'Material', 'Potion', 'Hat', 'Key', 'Chest', 'Special'])
            
            if category == 'Monster':
                # Random monster equipment
                monsters = equipment_data.get('Monsters', [])
                if monsters:
                    monster = random.choice(monsters)
                    item = {
                        "type": "Monster",
                        "name": monster["name"],
                        "emoji_file": monster.get("emoji_file", f"Monsters/{monster['name']}.png"),
                        "rarity": monster.get("rarity", "Uncommon"),
                        "element": monster.get("element", "Basic"),
                        "category": monster.get("category", "Land")
                    }
                else:
                    continue
            
            elif category in ['Gem', 'Material']:
                # Random gem or material
                items = equipment_data.get(category + 's', [])
                if items:
                    selected = random.choice(items)
                    item = {
                        "type": category,
                        "name": selected["name"],
                        "emoji_file": selected.get("emoji_file", f"{category}s/{selected['name']}.png"),
                        "rarity": selected.get("rarity", "Common")
                    }
                else:
                    continue
            
            elif category == 'Potion':
                # Random potion
                potions = equipment_data.get('Potions', [])
                if potions:
                    potion = random.choice(potions)
                    item = {
                        "type": "Potion",
                        "name": potion["name"],
                        "emoji_file": potion.get("emoji_file", f"Potions/{potion['name']}.png"),
                        "rarity": potion.get("rarity", "Common"),
                        "effect": potion.get("effect", "heal")
                    }
                else:
                    continue
            
            elif category == 'Hat':
                # Random hat
                hats = equipment_data.get('Hats', [])
                if hats:
                    hat = random.choice(hats)
                    item = {
                        "type": "Hat",
                        "name": hat["name"],
                        "emoji_file": hat.get("emoji_file", f"Hats/{hat['name']}.png"),
                        "rarity": hat.get("rarity", "Uncommon")
                    }
                else:
                    continue
            
            elif category == 'Key':
                # Random key
                key_type = random.choice(['Key1', 'Key2', 'Key3'])
                item = {
                    "type": "Key",
                    "name": key_type,
                    "emoji_file": f"{key_type}.png",
                    "rarity": "Special",
                    "count": 1
                }
            
            elif category == 'Chest':
                # Random chest
                chest_type = random.choice(['Chest 1', 'Chest 2', 'Chest 3', 'Chest 4'])
                item = {
                    "type": "Chest",
                    "name": chest_type,
                    "emoji_file": f"Chests/{chest_type.replace(' ', '')}.png",
                    "rarity": "Special",
                    "count": 1
                }
            
            else:
                # Skip if no valid category
                continue
            
            # Calculate price using merchant formula
            rarity = item.get("rarity", "Common")
            base_price = MERCHANT_RARITY_PRICES.get(rarity, 100)
            
            # Formula: (pet_level / equipment_mult) * rarity_mult * random(25,100)
            # We don't have pet level here, so we use floor as proxy
            level_proxy = floor_num * 5  # Rough estimate
            random_mult = random.randint(25, 100)
            item["cost"] = int((level_proxy / 1.0) * base_price * random_mult)
            
            merchant_items.append(item)
        
        return merchant_items
    
    def _generate_boss_lore_sync(self, floor_num: int, dungeon_type: str) -> str:
        """Generate AI boss lore/title for the floor boss"""
        # Get recent event history for context
        event_history = self.dungeon_state.get('event_history', [])
        recent_events = event_history[-3:] if len(event_history) >= 3 else event_history
        
        dungeon_descriptions = {
            "Crypt": "undead necromancer, ancient burial chambers, dark magic",
            "Volcanic Depths": "fire demon lord, molten lava, volcanic fury",
            "Frozen Cavern": "ice titan, frost magic, eternal winter",
            "Arcane Tower": "archmage, powerful spells, arcane mastery",
            "Haunted Forest": "ancient treant lord, nature spirits, fae magic",
            "Sky Fortress": "storm elemental, thunder and lightning, aerial combat",
            "Sunken Temple": "sea leviathan, ancient civilization, water magic",
            "Shadow Realm": "void entity, dimensional rifts, psychic terror",
            "Holy Sanctum": "celestial guardian, divine light, sacred trials",
            "Gladiator Pit": "champion warrior, battle mastery, combat glory",
            "Crystal Labyrinth": "stone golem lord, gem magic, earth power",
            "Storm Wastes": "chaos elemental, energetic anomalies, storm fury"
        }
        
        theme = dungeon_descriptions.get(dungeon_type, "powerful guardian")
        recent_context = " The adventurer has survived: " + ", ".join(recent_events) if recent_events else ""
        
        prompt = f"""
Generate an epic boss name/title for floor {floor_num} of a {dungeon_type} dungeon.

DUNGEON THEME: {theme}
{recent_context}

Create a memorable boss title that includes:
1. A fearsome name
2. An intimidating title or epithet
3. A reference to their role as guardian of floor {floor_num}

Format: "[Name] [Epithet], [Guardian Role]"

Examples:
- "Archlich Vorruk the Hollow, Warden of the Third Crypt"
- "Ignar the Unquenched, First Flame of the Depths"
- "Frostlord Kyrax, Guardian of the Fifth Frozen Hall"

Return ONLY the boss title, nothing else.
"""
        
        try:
            # Use AI to generate boss lore
            from Systems.Functions.local_ai import chat_complete_json_sync
            result = chat_complete_json_sync(prompt)
            
            # Handle both string and dict responses
            if isinstance(result, dict):
                boss_lore = result.get('title', result.get('name', f"Guardian of Floor {floor_num}"))
            else:
                boss_lore = str(result).strip()
            
            return boss_lore
        except Exception as e:
            # Fallback to generic boss title
            boss_titles = {
                "Crypt": f"Archlich of the {self._ordinal(floor_num)} Crypt",
                "Volcanic Depths": f"Flame Lord of the {self._ordinal(floor_num)} Depths",
                "Frozen Cavern": f"Frostlord of the {self._ordinal(floor_num)} Cavern",
                "Arcane Tower": f"Archmage of the {self._ordinal(floor_num)} Tower",
                "Haunted Forest": f"Ancient Treant of the {self._ordinal(floor_num)} Grove",
                "Sky Fortress": f"Storm Elemental of the {self._ordinal(floor_num)} Sky",
                "Sunken Temple": f"Sea Leviathan of the {self._ordinal(floor_num)} Temple",
                "Shadow Realm": f"Void Entity of the {self._ordinal(floor_num)} Realm",
                "Holy Sanctum": f"Celestial Guardian of the {self._ordinal(floor_num)} Sanctum",
                "Gladiator Pit": f"Grand Champion of the {self._ordinal(floor_num)} Arena",
                "Crystal Labyrinth": f"Stone Colossus of the {self._ordinal(floor_num)} Labyrinth",
                "Storm Wastes": f"Chaos Lord of the {self._ordinal(floor_num)} Wastes"
            }
            return boss_titles.get(dungeon_type, f"Guardian of Floor {floor_num}")
    
    def _ordinal(self, n: int) -> str:
        """Convert number to ordinal (1st, 2nd, 3rd, etc.)"""
        if 10 <= n % 100 <= 20:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
        return f"{n}{suffix}"
            
    async def create_dungeon(self, party_members: List[int], dungeon_type: str = "Crypt") -> str:
        """Create a new dungeon instance"""
        await self.initialize_database()
        
        if len(party_members) > MAX_PARTY_SIZE:
            raise ValueError(f"Party size cannot exceed {MAX_PARTY_SIZE} members")
        
        if dungeon_type not in DUNGEON_TYPES:
            dungeon_type = "Camp"  # Default fallback
            
        self.dungeon_id = f"dungeon_{self.party_leader_id}_{int(datetime.now().timestamp())}"
        self.party_members = party_members
        self.dungeon_type = dungeon_type
        self.dungeon_state = self._generate_floor(1)
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO dungeons (dungeon_id, party_leader_id, party_members, dungeon_state, party_buffs, ready_users, dungeon_type, event_history)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                self.dungeon_id,
                str(self.party_leader_id),
                json.dumps([str(m) for m in party_members]),
                json.dumps(self.dungeon_state),
                json.dumps({}),
                json.dumps([]),
                dungeon_type,
                json.dumps([])
            ))
            await db.commit()
            
        logger.info(f"Created {dungeon_type} dungeon {self.dungeon_id} with {len(party_members)} members")
        return self.dungeon_id
        
    async def load_dungeon(self, dungeon_id: str) -> bool:
        """Load existing dungeon state"""
        await self.initialize_database()
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('''
                SELECT party_leader_id, party_members, current_floor, current_room, 
                       dungeon_state, party_buffs, ready_users, completed, dungeon_type, event_history
                FROM dungeons WHERE dungeon_id = ?
            ''', (dungeon_id,)) as cursor:
                row = await cursor.fetchone()
                
                if not row:
                    return False
                    
                self.dungeon_id = dungeon_id
                self.party_leader_id = int(row[0])
                self.party_members = json.loads(row[1])
                self.current_floor = row[2]
                self.current_room = row[3]
                self.dungeon_state = json.loads(row[4]) if row[4] else {}
                self.party_buffs = json.loads(row[5]) if row[5] else {}
                self.ready_users = set(json.loads(row[6])) if row[6] else set()
                self.dungeon_type = row[8] if row[8] else "Crypt"
                
                # Load event history into dungeon_state
                if row[9]:
                    self.dungeon_state['event_history'] = json.loads(row[9])
                
                if row[7]:  # completed
                    logger.info(f"Dungeon {dungeon_id} is already completed")
                    return False
                    
        logger.info(f"Loaded {self.dungeon_type} dungeon {dungeon_id} at floor {self.current_floor}, room {self.current_room}")
        return True
        
    async def save_dungeon(self):
        """Save current dungeon state"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE dungeons 
                SET current_floor = ?, current_room = ?, dungeon_state = ?, 
                    party_buffs = ?, ready_users = ?, dungeon_type = ?, event_history = ?, updated_at = CURRENT_TIMESTAMP
                WHERE dungeon_id = ?
            ''', (
                self.current_floor,
                self.current_room,
                json.dumps(self.dungeon_state),
                json.dumps(self.party_buffs),
                json.dumps(list(self.ready_users)),
                getattr(self, 'dungeon_type', 'Crypt'),
                json.dumps(self.dungeon_state.get('event_history', [])),
                self.dungeon_id
            ))
            await db.commit()
            
    def _generate_floor(self, floor_number: int) -> Dict:
        """Generate a floor with 10 rooms.

        Rooms 1-8: weighted random events with new distribution
            24.0% Monster Encounter (new)
            20.0% Story Segment (new AI-generated)
            12.0% Puzzle (new)
            10.0% Trap
            10.0% Chest/Mimic (50/50 whether real or mimic)
             8.0% Shrine
             6.0% Merchant (new)
             3.5% Chest 1 (Common/Uncommon, always real)
             2.5% Chest 2 (Rare, always real)
             2.0% Chest 3 (Epic, always real)
             2.0% Chest 4 (Mythic mix, always real)
        Room 9:  always Boss with AI-generated lore
        Room 10: always Floor Loot (scaled chest reward)
        """
        floor_data = {"floor": floor_number, "rooms": []}

        # NEW weighted pool for rooms 1-8
        _event_pool = [
            EVENT_MONSTER_ENCOUNTER,  # 24%
            EVENT_STORY_SEGMENT,      # 20%
            EVENT_PUZZLE,             # 12%
            EVENT_TRAP,               # 10%
            EVENT_CHEST_MIMIC,        # 10%
            EVENT_SHRINE,             # 8%
            EVENT_MERCHANT,           # 6%
            EVENT_CHEST1,             # 3.5%
            EVENT_CHEST2,             # 2.5%
            EVENT_CHEST3,             # 2.0%
            EVENT_CHEST4,             # 2.0%
        ]
        _event_weights = [24.0, 20.0, 12.0, 10.0, 10.0, 8.0, 6.0, 3.5, 2.5, 2.0, 2.0]

        for room_num in range(1, ROOMS_PER_FLOOR + 1):
            if room_num == BOSS_ROOM:
                # Room 9 is always the boss with AI-generated lore
                dungeon_type = getattr(self, 'dungeon_type', 'Crypt')
                boss_lore = self._generate_boss_lore_sync(floor_number, dungeon_type)
                
                room_data = {
                    "room": room_num,
                    "event_type": EVENT_BOSS,
                    "completed": False,
                    "boss_lore": boss_lore
                }
            elif room_num == REWARD_ROOM:
                # Room 10 is always Floor Loot (scaled chest reward based on floor)
                # Floor 1: Chest 1, Floor 2-3: Chest 2, Floor 4-6: Chest 3, Floor 7+: Chest 4 x2
                if floor_number == 1:
                    chest_event = EVENT_CHEST1
                    count = 1
                elif floor_number <= 3:
                    chest_event = EVENT_CHEST2
                    count = 1
                elif floor_number <= 6:
                    chest_event = EVENT_CHEST3
                    count = 1
                else:
                    chest_event = EVENT_CHEST4
                    count = 2
                
                chest_type = CHEST_TYPES[CHEST_EVENT_MAP[chest_event]]
                room_data = {
                    "room": room_num,
                    "event_type": EVENT_FLOOR_LOOT,
                    "completed": False,
                    "chest_type": chest_type["name"],
                    "chest_emoji": chest_type["emoji"],
                    "chest_rarity_pool": chest_type["rarity_pool"],
                    "chest_count": count,
                }
            else:
                # Rooms 1-8: weighted random event
                event_type = random.choices(_event_pool, weights=_event_weights, k=1)[0]

                room_data = {
                    "room": room_num,
                    "event_type": event_type,
                    "completed": False
                }

                # Pre-generate event data so it doesn't change on each load
                if event_type == EVENT_MONSTER_ENCOUNTER:
                    # Generate monster encounter with persistent monster selection
                    # We can't call async generate_monster() here, so we pre-select the monster
                    # and store enough data to regenerate it consistently
                    equipment_data = _load_equipment_data()
                    monsters = equipment_data.get('Monsters', [])
                    if not monsters:
                        monsters = [{"name": "Wirm", "emoji_file": "Monsters/Wirm.png", "category": "Land", "element": "Basic"}]
                    monster_template = random.choice(monsters)
                    
                    room_data["monster_template"] = {
                        "name": monster_template["name"],
                        "emoji_file": monster_template.get("emoji_file", f"Monsters/{monster_template['name']}.png"),
                        "category": monster_template.get("category", "Land"),
                        "element": monster_template.get("element", "Basic"),
                    }
                    # Monster stats will be calculated when first entering the room (based on party stats)
                    
                elif event_type == EVENT_STORY_SEGMENT:
                    # Generate AI story segment with 3 choices
                    dungeon_type = getattr(self, 'dungeon_type', 'Crypt')
                    story_segment = self._generate_story_segment_sync(floor_number, room_num, dungeon_type)
                    room_data["story_segment"] = story_segment
                    room_data["story_attempts"] = 0
                    
                elif event_type == EVENT_PUZZLE:
                    # Generate puzzle from templates
                    dungeon_type = getattr(self, 'dungeon_type', 'Crypt')
                    puzzle_data = self._generate_puzzle_room_sync(floor_number, dungeon_type)
                    room_data["puzzle_data"] = puzzle_data
                    
                elif event_type == EVENT_MERCHANT:
                    # Generate 5 random items for sale
                    merchant_items = self._generate_merchant_items_sync(floor_number)
                    room_data["merchant_items"] = merchant_items
                    
                elif event_type == EVENT_CHEST_MIMIC:
                    # 50/50 whether it's a mimic or real chest
                    is_mimic = random.random() < 0.5
                    room_data["is_mimic"] = is_mimic
                    
                    # ALWAYS use a random chest emoji (1-4) to disguise mimics as real chests
                    chest_tier = random.randint(0, 3)  # Random chest 1-4
                    chest_type = CHEST_TYPES[chest_tier]
                    room_data["chest_type"] = chest_type["name"]
                    room_data["chest_emoji"] = chest_type["emoji"]
                    room_data["chest_rarity_pool"] = chest_type["rarity_pool"]
                    room_data["chest_count"] = chest_type["count"]
                    
                elif event_type in CHEST_EVENT_MAP:
                    # Regular guaranteed chests (always real, not mimics)
                    chest_type = CHEST_TYPES[CHEST_EVENT_MAP[event_type]]
                    room_data["chest_type"] = chest_type["name"]
                    room_data["chest_emoji"] = chest_type["emoji"]
                    room_data["chest_rarity_pool"] = chest_type["rarity_pool"]
                    room_data["chest_count"] = chest_type["count"]
                    
                elif event_type == EVENT_TRAP:
                    # 50/50 chance: generic pool vs elemental+type pool
                    _trap_pool = (TRAP_EFFECTS_GENERIC if random.random() < 0.5
                                  else TRAP_EFFECTS_ELEMENTAL + TRAP_EFFECTS_TYPE)
                    trap = random.choice(_trap_pool)
                    if "emoji_key" in trap:
                        trap["emoji"] = _e(trap["emoji_key"])
                    room_data["trap_data"] = trap
                    
                elif event_type == EVENT_SHRINE:
                    # 50/50 chance: generic pool vs elemental+type pool
                    _shrine_pool = (SHRINE_EFFECTS_GENERIC if random.random() < 0.5
                                    else SHRINE_EFFECTS_ELEMENTAL + SHRINE_EFFECTS_TYPE)
                    shrine = random.choice(_shrine_pool)
                    if "emoji_key" in shrine:
                        shrine["emoji"] = _e(shrine["emoji_key"])
                    room_data["shrine_data"] = shrine

            floor_data["rooms"].append(room_data)

        return floor_data
        
    def get_current_room_data(self) -> Optional[Dict]:
        """Get data for current room"""
        if not self.dungeon_state or "rooms" not in self.dungeon_state:
            return None
            
        for room in self.dungeon_state["rooms"]:
            if room["room"] == self.current_room:
                return room
                
        return None
        
    async def get_party_average_stats(self) -> Dict[str, float]:
        """Calculate average party stats for scaling.
        
        Returns dungeon-scaled stats where health is capped to give
        ~15-20 turns of combat (health ≈ 15 × attack).
        """
        total_att = 0
        total_def = 0
        total_health = 0
        count = 0

        for user_id in self.party_members:
            pet = await user_data_manager.get_pet_data_async(str(user_id))
            if pet:
                stats = StatsCalculator.calculate_pet_stats(pet)
                p_atk = int(stats.get('attack',  stats['ATT'] + stats['DEX']))
                p_def = int(stats.get('defense', stats['DEF'] + stats['INT']))
                # Dungeon health: cap at 20× attack so battles last ~15-20 turns.
                # This prevents the 3-billion HP problem on high-level pets.
                dungeon_hp = min(int(stats.get('max_health', 500)), p_atk * 20)
                dungeon_hp = max(500, dungeon_hp)  # floor of 500
                total_att    += p_atk
                total_def    += p_def
                total_health += dungeon_hp
                count += 1

        if count == 0:
            return {"att": 10, "def": 5, "health": 500}

        return {
            "att":    total_att    / count,
            "def":    total_def    / count,
            "health": total_health / count,
        }
        
    async def generate_monster(self, is_boss: bool = False) -> Dict:
        """Generate NPC monster for battle"""
        avg_stats = await self.get_party_average_stats()
        
        # Calculate difficulty multiplier based on floor and room
        base_multiplier = 0.10 + (self.current_floor - 1) * 0.05 + (self.current_room - 1) * 0.02
        party_size_bonus = (len(self.party_members) - 1) * 0.05
        base_multiplier += party_size_bonus
        
        if is_boss:
            base_multiplier = 0.15 + (self.current_floor - 1) * 0.08 + party_size_bonus
            
        equipment_data = _load_equipment_data()
            
        if is_boss:
            # Bosses use actual pet species from info.json
            try:
                info_path = os.path.join(os.path.dirname(__file__), '..', 'Logic', 'info.json')
                with open(info_path, 'r') as f:
                    info_data = json.load(f)
                all_species = list(info_data.get('Pets', {}).keys())
            except Exception:
                all_species = []
            
            if all_species:
                species = random.choice(all_species)
                # Get element/category from info.json if available
                pet_info = info_data.get('Pets', {}).get(species, {})
                monster_name = f"Boss {species}"
                monster_template = {
                    'name': species,
                    'species': species,
                    'emoji_file': None,          # bosses use Pets/ folder
                    'category': pet_info.get('category', random.choice(["Land", "Air", "Water", "Fighting", "Psychic"])),
                    'element': pet_info.get('element', random.choice(["Fire", "Ice", "Electric", "Plant", "Water", "Rock", "Air", "Magic", "Holy", "Necro", "Psychic", "Fighting", "Basic"])),
                }
            else:
                species = 'Wolf'
                monster_name = 'Boss Wolf'
                monster_template = {'name': 'Wolf', 'species': 'Wolf', 'emoji_file': None, 'category': 'Land', 'element': 'Basic'}
        else:
            # Regular monsters use monster equipment items
            monsters = equipment_data.get('Monsters', [])
            if not monsters:
                monsters = [{"name": "Wirm", "emoji_file": "Monsters/Wirm.png", "category": "Land", "element": "Basic"}]
            monster_template = random.choice(monsters)
            monster_name = monster_template['name']
            monster_template['species'] = None  # monsters don't have a pet species
        
        # Generate stats based on party average
        monster_att    = max(5,  int(avg_stats["att"]    * base_multiplier * random.uniform(0.9, 1.1)))
        monster_def    = max(3,  int(avg_stats["def"]    * base_multiplier * random.uniform(0.9, 1.1)))
        monster_health = max(50, int(avg_stats["health"] * base_multiplier * random.uniform(0.95, 1.15)))
        
        types    = ["Land", "Air", "Water", "Fighting", "Psychic", "Magic"]
        elements = ["Basic", "Fire", "Ice", "Electric", "Plant", "Water", "Rock", "Air", "Fighting", "Psychic", "Magic", "Holy", "Necro"]
        
        monster_type    = monster_template.get('category', random.choice(types))
        monster_element = monster_template.get('element',  random.choice(elements))
        
        # emoji_file: monsters use Equipment/Monsters/ folder, bosses use Pets folder
        emoji_file = monster_template.get('emoji_file')
        if not emoji_file and not is_boss:
            emoji_file = 'Monsters/' + monster_template['name'].replace(' ', '') + '.png'
        
        return {
            "name":           monster_name,
            "equipment_name": monster_template["name"],   # for loot drop
            "species":        monster_template.get('species'),  # pet species for boss image
            "emoji_file":     emoji_file,                 # filename in Equipment/ (monsters only)
            "attack":         monster_att,
            "defense":        monster_def,
            "health":         monster_health,
            "max_health":     monster_health,
            "type":           monster_type,
            "element":        monster_element,
            "is_boss":        is_boss,
            "level":          self.current_floor
        }
        
    async def generate_chest_loot(self, chest_type: Dict, user_id: int) -> List[Dict]:
        """Generate individual loot for a user from a chest"""
        equipment_data = _load_equipment_data()
            
        loot = []
        rarity_pool = chest_type["rarity_pool"]
        count = chest_type["count"]
        
        # Collect all items matching rarity (Hats excluded from dungeon loot)
        available_items = []
        for category in ["Materials", "Gems", "Monsters", "Potions"]:
            items = equipment_data.get(category, [])
            for item in items:
                if item.get("rarity") in rarity_pool:
                    item_copy = item.copy()
                    item_copy["type"] = category.rstrip('s')  # Remove plural
                    available_items.append(item_copy)
                    
        # Select random items
        for _ in range(count):
            if available_items:
                selected = random.choice(available_items)
                loot.append({
                    "name": selected["name"],
                    "type": selected["type"],
                    "rarity": selected["rarity"],
                    "emoji_id": selected.get("emoji_id"),
                    "count": 1
                })
                
        return loot
        
    def apply_trap_effect(self, trap: Dict):
        """Apply trap effect to party members.

        If the trap has a target_filter, pets whose element/type matches the
        filter receive the FULL debuff.  All other pets receive a 50 % splash
        debuff (half value, same duration) — they still get hurt, just less.
        Generic traps (target_filter=None) hit everyone at full strength.
        """
        import asyncio

        effect_name = trap["name"]
        effect_type = trap["effect"]
        value       = trap["value"]
        duration    = trap["duration"]
        emoji       = trap.get("emoji", "🪤")
        tf          = trap.get("target_filter")  # None → generic

        for user_id in self.party_members:
            user_id_str = str(user_id)
            if user_id_str not in self.party_buffs:
                self.party_buffs[user_id_str] = []

            # Determine effective value based on target filter
            effective_value = value
            if tf is not None:
                pet_matches = asyncio.get_event_loop().run_until_complete(
                    self._pet_matches_filter(user_id_str, tf)
                ) if not asyncio.get_event_loop().is_running() else False
                # Async-safe: we store the filter on the buff and resolve lazily
                # For now apply full value; the filter is stored for display.
                # (Actual selective application is handled in apply_trap_effect_async)
                effective_value = value  # will be corrected in async path

            self.party_buffs[user_id_str].append({
                "name":            effect_name,
                "effect":          effect_type,
                "value":           effective_value,
                "duration":        duration,
                "rooms_remaining": duration,
                "type":            "debuff",
                "emoji":           emoji,
                "target_filter":   tf,   # kept for display/info
            })

    async def apply_trap_effect_async(self, trap: Dict):
        """Async version of apply_trap_effect — correctly resolves pet element/type."""
        effect_name = trap["name"]
        effect_type = trap["effect"]
        value       = trap["value"]
        duration    = trap["duration"]
        emoji       = trap.get("emoji", "🪤")
        tf          = trap.get("target_filter")

        for user_id in self.party_members:
            user_id_str = str(user_id)
            if user_id_str not in self.party_buffs:
                self.party_buffs[user_id_str] = []

            if tf is not None:
                matches = await self._pet_matches_filter(user_id_str, tf)
                effective_value = value if matches else value * 0.5
            else:
                effective_value = value

            self.party_buffs[user_id_str].append({
                "name":            effect_name,
                "effect":          effect_type,
                "value":           effective_value,
                "duration":        duration,
                "rooms_remaining": duration,
                "type":            "debuff",
                "emoji":           emoji,
                "target_filter":   tf,
            })

    def apply_shrine_effect(self, shrine: Dict):
        """Apply shrine effect to party members.

        If the shrine has a target_filter, ONLY pets whose element/type matches
        receive the buff.  Non-matching pets get nothing.
        Generic shrines (target_filter=None) bless everyone.
        """
        effect_name = shrine["name"]
        effect_type = shrine["effect"]
        value       = shrine["value"]
        duration    = shrine["duration"]
        emoji       = shrine.get("emoji", "⛩️")
        tf          = shrine.get("target_filter")

        for user_id in self.party_members:
            user_id_str = str(user_id)
            if user_id_str not in self.party_buffs:
                self.party_buffs[user_id_str] = []

            # Generic shrines always apply; elemental/type shrines stored with
            # filter — async path resolves correctly.
            self.party_buffs[user_id_str].append({
                "name":            effect_name,
                "effect":          effect_type,
                "value":           value,
                "duration":        duration,
                "rooms_remaining": duration,
                "type":            "buff",
                "emoji":           emoji,
                "target_filter":   tf,
            })

    async def apply_shrine_effect_async(self, shrine: Dict):
        """Async version of apply_shrine_effect — correctly resolves pet element/type."""
        effect_name = shrine["name"]
        effect_type = shrine["effect"]
        value       = shrine["value"]
        duration    = shrine["duration"]
        emoji       = shrine.get("emoji", "⛩️")
        tf          = shrine.get("target_filter")

        for user_id in self.party_members:
            user_id_str = str(user_id)
            if user_id_str not in self.party_buffs:
                self.party_buffs[user_id_str] = []

            if tf is not None:
                matches = await self._pet_matches_filter(user_id_str, tf)
                if not matches:
                    continue  # shrine only blesses matching pets

            self.party_buffs[user_id_str].append({
                "name":            effect_name,
                "effect":          effect_type,
                "value":           value,
                "duration":        duration,
                "rooms_remaining": duration,
                "type":            "buff",
                "emoji":           emoji,
                "target_filter":   tf,
            })

    async def _pet_matches_filter(self, user_id_str: str, tf: Dict) -> bool:
        """Return True if the user's pet matches the given target_filter."""
        pet = await user_data_manager.get_pet_data_async(user_id_str)
        if not pet:
            return False
        mode   = tf.get("mode", "element")
        values = [v.lower() for v in tf.get("values", [])]
        if mode == "element":
            elem = str(pet.get("element", "basic")).lower()
            return elem in values
        elif mode == "type":
            cat = str(pet.get("category", "land")).lower()
            # Normalise aliases
            if cat in ("air",):      cat = "flying"
            if cat in ("water",):    cat = "swimming"
            return cat in values
        return False
            
    def decrement_buff_durations(self):
        """Decrease buff/debuff durations after room completion"""
        for user_id in list(self.party_buffs.keys()):
            buffs = self.party_buffs[user_id]
            # Decrement and filter expired buffs
            active_buffs = []
            for buff in buffs:
                buff["rooms_remaining"] -= 1
                if buff["rooms_remaining"] > 0:
                    active_buffs.append(buff)
            self.party_buffs[user_id] = active_buffs
            
    def get_active_buffs(self, user_id: int) -> List[Dict]:
        """Get active buffs/debuffs for a user"""
        return self.party_buffs.get(str(user_id), [])
        
    def mark_user_ready(self, user_id: int) -> bool:
        """Mark a user as ready. Returns True if all users are ready."""
        self.ready_users.add(str(user_id))
        return len(self.ready_users) >= len(self.party_members)
    
    def clear_ready_users(self):
        """Clear all ready users (after room completion)"""
        self.ready_users.clear()
    
    async def handle_monster_encounter_action(self, user_id: int, action: str) -> Dict:
        """Handle Fight/Scare/Flee choice for monster encounters
        
        Returns: {
            "success": bool,
            "action": str,
            "result": str,
            "forced_battle": bool,
            "xp_reward": int,
            "loot": list,
            "cooldown_until": float or None
        }
        """
        room_data = self.get_current_room_data()
        if not room_data or room_data["event_type"] != EVENT_MONSTER_ENCOUNTER:
            return {"success": False, "result": "Not a monster encounter room"}
        
        # Get pet data
        pet = await user_data_manager.get_pet_data_async(str(user_id))
        if not pet:
            return {"success": False, "result": "Pet not found"}
        
        stats = StatsCalculator.calculate_pet_stats(pet)
        pet_element = pet.get('element', 'Basic').lower()
        pet_type = pet.get('category', 'Land').lower()
        
        # Get monster template from room data
        monster_template = room_data.get("monster_template", {})
        monster_element = monster_template.get("element", "Basic").lower()
        monster_type = monster_template.get("category", "Land").lower()
        
        if action == "fight":
            # Fight always leads to battle
            return {
                "success": True,
                "action": "fight",
                "result": "You engage the monster in battle!",
                "forced_battle": True,
                "xp_reward": 0,  # XP awarded after battle victory
                "loot": [],
                "cooldown_until": None
            }
        
        elif action == "scare":
            # Scare formula: (ATT + DEX) / 2 * bonuses / floor_penalty
            pet_scare_power = (stats["ATT"] + stats["DEX"]) / 2
            
            # Element advantage bonus
            element_bonus = 1.15 if self.check_element_advantage(pet_element, monster_element) else 1.0
            
            # Type advantage bonus
            type_bonus = 1.10 if self.check_type_advantage(pet_type, monster_type) else 1.0
            
            # Floor penalty
            floor_penalty = 1.0 + (self.current_floor - 1) * 0.03
            
            # Required threshold
            scare_required = 15 * floor_penalty
            
            # Success rate (5-85%)
            scare_rate = max(5, min(85, int((pet_scare_power * element_bonus * type_bonus / scare_required) * 60)))
            
            # Roll
            roll = random.randint(1, 100)
            success = roll <= scare_rate
            
            if success:
                # Success: Monster flees, half XP, no loot
                xp_reward = self.calculate_xp_reward(pet, EVENT_MONSTER_ENCOUNTER, self.current_room) // 2
                
                return {
                    "success": True,
                    "action": "scare",
                    "result": f"Your intimidating presence frightens the monster away! (Roll: {roll}/{scare_rate})",
                    "forced_battle": False,
                    "xp_reward": xp_reward,
                    "loot": [],
                    "cooldown_until": None
                }
            else:
                # Failure: Forced battle
                return {
                    "success": False,
                    "action": "scare",
                    "result": f"The monster is not intimidated and attacks! (Roll: {roll}/{scare_rate})",
                    "forced_battle": True,
                    "xp_reward": 0,
                    "loot": [],
                    "cooldown_until": None
                }
        
        elif action == "flee":
            # Flee formula: (DEX + INT) / 2 * bonuses / floor_penalty
            pet_flee_power = (stats["DEX"] + stats["INT"]) / 2
            
            # Mobility bonus for swimming/flying
            mobility_bonus = 1.15 if pet_type in ("swimming", "flying") else 1.0
            
            # Element bonus for air/psychic
            element_bonus = 1.10 if pet_element in ("air", "psychic") else 1.0
            
            # Floor penalty
            floor_penalty = 1.0 + (self.current_floor - 1) * 0.04
            
            # Required threshold
            flee_required = 12 * floor_penalty
            
            # Success rate (5-80%)
            flee_rate = max(5, min(80, int((pet_flee_power * mobility_bonus * element_bonus / flee_required) * 60)))
            
            # Roll
            roll = random.randint(1, 100)
            success = roll <= flee_rate
            
            if success:
                # Success: Escape, no XP, no loot
                return {
                    "success": True,
                    "action": "flee",
                    "result": f"You successfully escape from the monster! (Roll: {roll}/{flee_rate})",
                    "forced_battle": False,
                    "xp_reward": 0,
                    "loot": [],
                    "cooldown_until": None
                }
            else:
                # Failure: Forced battle
                return {
                    "success": False,
                    "action": "flee",
                    "result": f"The monster catches you! (Roll: {roll}/{flee_rate})",
                    "forced_battle": True,
                    "xp_reward": 0,
                    "loot": [],
                    "cooldown_until": None
                }
        
        return {"success": False, "result": "Invalid action"}
    
    async def handle_story_segment_choice(self, user_id: int, choice: int) -> Dict:
        """Handle story segment skill check
        
        Returns: {
            "success": bool,
            "result": str,
            "xp_reward": int,
            "loot": list,
            "cooldown_until": float or None
        }
        """
        room_data = self.get_current_room_data()
        if not room_data or room_data["event_type"] != EVENT_STORY_SEGMENT:
            return {"success": False, "result": "Not a story segment room"}
        
        story_segment = room_data.get("story_segment", {})
        if not story_segment:
            return {"success": False, "result": "Story segment not generated"}
        
        # Get pet data
        pet = await user_data_manager.get_pet_data_async(str(user_id))
        if not pet:
            return {"success": False, "result": "Pet not found"}
        
        stats = StatsCalculator.calculate_pet_stats(pet)
        
        # Determine stats based on choice
        if choice == 1:
            # Physical: ATT + DEF
            pet_skill = (stats["ATT"] + stats["DEF"]) / 2
        elif choice == 2:
            # Skillful: DEX + INT
            pet_skill = (stats["DEX"] + stats["INT"]) / 2
        elif choice == 3:
            # Endurance: ENE + HAP
            pet_skill = (stats["ENE"] + stats["HAP"]) / 2
        else:
            return {"success": False, "result": "Invalid choice"}
        
        # Difficulty calculation
        difficulty_multiplier = 1.0 + (self.current_floor - 1) * 0.04
        stage_mod = story_segment.get("difficulty_modifier", 1.0)
        required = 10 * difficulty_multiplier * stage_mod
        
        # Success rate (5-90%)
        success_rate = max(5, min(90, int((pet_skill / max(1, required)) * 50)))
        
        # Roll
        roll = random.randint(1, 100)
        success = roll <= success_rate
        
        if success:
            # Success: XP + small loot chance
            xp_reward = self.calculate_xp_reward(pet, EVENT_STORY_SEGMENT, self.current_room)
            
            # 20% chance for 1 random item
            loot = []
            if random.random() < 0.20:
                # Floor-based chest tier
                if self.current_floor <= 1:
                    chest_tier = 0
                elif self.current_floor <= 3:
                    chest_tier = 1
                else:
                    chest_tier = 2
                chest_loot = await self.generate_chest_loot(CHEST_TYPES[chest_tier], user_id)
                if chest_loot:
                    loot = [chest_loot[0]]  # Just 1 item
            
            success_flavor = story_segment.get("success_flavor", "You successfully overcome the challenge!")
            
            return {
                "success": True,
                "result": f"{success_flavor} (Roll: {roll}/{success_rate})",
                "xp_reward": xp_reward,
                "loot": loot,
                "cooldown_until": None
            }
        else:
            # Failure: 1-hour cooldown
            import time
            cooldown_until = time.time() + 3600  # 1 hour
            
            fail_flavor = story_segment.get("fail_flavor", "You fail to overcome the challenge.")
            
            # Store cooldown in database
            async with aiosqlite.connect(self.db_path) as db:
                room_key = f"{self.current_floor}_{self.current_room}"
                await db.execute('''
                    INSERT OR REPLACE INTO dungeon_story_cooldowns (dungeon_id, room_key, fail_until)
                    VALUES (?, ?, ?)
                ''', (self.dungeon_id, room_key, cooldown_until))
                await db.commit()
            
            return {
                "success": False,
                "result": f"{fail_flavor} You need time to regroup. (Roll: {roll}/{success_rate})",
                "xp_reward": 0,
                "loot": [],
                "cooldown_until": cooldown_until
            }
    
    async def handle_puzzle_attempt(self, user_id: int, choice: int) -> Dict:
        """Handle puzzle room skill check"""
        room_data = self.get_current_room_data()
        if not room_data or room_data["event_type"] != EVENT_PUZZLE:
            return {"success": False, "result": "Not a puzzle room"}
        
        puzzle_data = room_data.get("puzzle_data", {})
        if not puzzle_data:
            return {"success": False, "result": "Puzzle not generated"}
        
        # Get pet data
        pet = await user_data_manager.get_pet_data_async(str(user_id))
        if not pet:
            return {"success": False, "result": "Pet not found"}
        
        stats = StatsCalculator.calculate_pet_stats(pet)
        
        # Determine stats based on choice (same as story segments)
        if choice == 1:
            pet_skill = (stats["ATT"] + stats["DEF"]) / 2
        elif choice == 2:
            pet_skill = (stats["DEX"] + stats["INT"]) / 2
        elif choice == 3:
            pet_skill = (stats["ENE"] + stats["HAP"]) / 2
        else:
            return {"success": False, "result": "Invalid choice"}
        
        # Difficulty calculation
        difficulty_multiplier = 1.0 + (self.current_floor - 1) * 0.04
        puzzle_mod = puzzle_data.get("difficulty_modifier", 1.0)
        required = 10 * difficulty_multiplier * puzzle_mod
        
        # Success rate (5-90%)
        success_rate = max(5, min(90, int((pet_skill / max(1, required)) * 50)))
        
        # Roll
        roll = random.randint(1, 100)
        success = roll <= success_rate
        
        if success:
            # Success: XP + guaranteed item
            xp_reward = self.calculate_xp_reward(pet, EVENT_PUZZLE, self.current_room)
            
            # Floor-based chest tier
            if self.current_floor <= 1:
                chest_tier = 0
            elif self.current_floor <= 3:
                chest_tier = 1
            else:
                chest_tier = 2
            
            loot = await self.generate_chest_loot(CHEST_TYPES[chest_tier], user_id)
            
            return {
                "success": True,
                "result": f"You solved the puzzle! (Roll: {roll}/{success_rate})",
                "xp_reward": xp_reward,
                "loot": loot,
                "cooldown_until": None
            }
        else:
            # Failure: 1-hour cooldown
            import time
            cooldown_until = time.time() + 3600
            
            return {
                "success": False,
                "result": f"The puzzle stumps you. (Roll: {roll}/{success_rate})",
                "xp_reward": 0,
                "loot": [],
                "cooldown_until": cooldown_until
            }
    
    async def handle_merchant_purchase(self, user_id: int, item_index: int) -> Dict:
        """Handle merchant item purchase"""
        room_data = self.get_current_room_data()
        if not room_data or room_data["event_type"] != EVENT_MERCHANT:
            return {"success": False, "result": "Not a merchant room"}
        
        merchant_items = room_data.get("merchant_items", [])
        if not merchant_items or item_index < 0 or item_index >= len(merchant_items):
            return {"success": False, "result": "Invalid item"}
        
        item = merchant_items[item_index]
        cost = item.get("cost", 0)
        
        # Get pet data
        pet = await user_data_manager.get_pet_data_async(str(user_id))
        if not pet:
            return {"success": False, "result": "Pet not found"}
        
        current_xp = pet.get('xp', 0)
        
        if current_xp < cost:
            return {
                "success": False,
                "result": f"Insufficient XP! Need {cost:,}, have {current_xp:,}"
            }
        
        # Deduct XP
        new_xp = current_xp - cost
        await user_data_manager.update_pet_data_async(str(user_id), {'xp': new_xp})
        
        # Add item to inventory
        await LootCalculator.add_item_to_inventory(user_id, item)
        
        # Award bonus XP
        bonus_xp = self.calculate_xp_reward(pet, EVENT_MERCHANT, self.current_room)
        await LootCalculator.apply_xp_change(user_id, bonus_xp)
        
        # Remove item from merchant stock
        merchant_items.pop(item_index)
        room_data["merchant_items"] = merchant_items
        
        return {
            "success": True,
            "result": f"Purchased {item['name']} for {cost:,} XP!",
            "item": item,
            "new_xp_balance": new_xp + bonus_xp,
            "bonus_xp": bonus_xp
        }
    
    async def handle_chest_mimic_approach(self, user_id: int, approach: int) -> Dict:
        """Handle chest/mimic approach choice
        
        Returns: {
            "success": bool,
            "is_mimic": bool,
            "result": str,
            "forced_battle": bool (if mimic),
            "xp_reward": int,
            "loot": list,
            "cooldown_until": float or None
        }
        """
        room_data = self.get_current_room_data()
        if not room_data or room_data["event_type"] != EVENT_CHEST_MIMIC:
            return {"success": False, "result": "Not a chest/mimic room"}
        
        is_mimic = room_data.get("is_mimic", False)
        
        # Get pet data
        pet = await user_data_manager.get_pet_data_async(str(user_id))
        if not pet:
            return {"success": False, "result": "Pet not found"}
        
        stats = StatsCalculator.calculate_pet_stats(pet)
        
        # Determine stats based on approach
        if approach == 1:
            # Force Open: ATT + DEF
            pet_skill = (stats["ATT"] + stats["DEF"]) / 2
            bonus = 1.20 if is_mimic else 1.0  # +20% vs mimics
        elif approach == 2:
            # Examine: DEX + INT
            pet_skill = (stats["DEX"] + stats["INT"]) / 2
            bonus = 1.10 if is_mimic else 1.20  # +10% mimic detection, +20% chest opening
        elif approach == 3:
            # Wait: ENE + HAP
            pet_skill = (stats["ENE"] + stats["HAP"]) / 2
            bonus = 1.0  # Lowest bonus
        else:
            return {"success": False, "result": "Invalid approach"}
        
        # Difficulty calculation
        floor_difficulty = 1.0 + (self.current_floor - 1) * 0.05
        
        if is_mimic:
            # Mimic fight check
            mimic_defense = 8 * floor_difficulty
            skill_rate = max(5, min(90, int((pet_skill * bonus / mimic_defense) * 60)))
        else:
            # Real chest skill check
            required = 10 * floor_difficulty
            skill_rate = max(5, min(90, int((pet_skill * bonus / required) * 60)))
        
        # Roll
        roll = random.randint(1, 100)
        success = roll <= skill_rate
        
        if is_mimic:
            if approach == 3 and success:
                # Wait + Success = Mimic retreats without battle
                xp_reward = self.calculate_xp_reward(pet, EVENT_MONSTER_ENCOUNTER, self.current_room)
                return {
                    "success": True,
                    "is_mimic": True,
                    "result": f"Your patience reveals the mimic, which retreats! (Roll: {roll}/{skill_rate})",
                    "forced_battle": False,
                    "xp_reward": xp_reward,
                    "loot": [],
                    "cooldown_until": None
                }
            else:
                # Battle triggered (success = surprise advantage, failure = ambush)
                return {
                    "success": success,
                    "is_mimic": True,
                    "result": "It's a mimic!" if success else "The mimic ambushes you!",
                    "forced_battle": True,
                    "surprise_advantage": success,  # For battle system
                    "xp_reward": 0,
                    "loot": [],
                    "cooldown_until": None
                }
        else:
            # Real chest
            if success:
                # Success: Loot (double if approach 2)
                chest_tier = 0 if self.current_floor <= 1 else 1 if self.current_floor <= 3 else 2
                loot = await self.generate_chest_loot(CHEST_TYPES[chest_tier], user_id)
                
                if approach == 2:
                    # Double loot for skillful opening
                    loot = loot + await self.generate_chest_loot(CHEST_TYPES[chest_tier], user_id)
                
                xp_reward = self.calculate_xp_reward(pet, "chest", self.current_room)
                
                return {
                    "success": True,
                    "is_mimic": False,
                    "result": f"You successfully open the chest! (Roll: {roll}/{skill_rate})",
                    "forced_battle": False,
                    "xp_reward": xp_reward,
                    "loot": loot,
                    "cooldown_until": None
                }
            else:
                # Failure: 1 item from lower tier + cooldown
                import time
                cooldown_until = time.time() + 3600
                
                lower_tier = max(0, (0 if self.current_floor <= 1 else 1 if self.current_floor <= 3 else 2) - 1)
                loot = await self.generate_chest_loot(CHEST_TYPES[lower_tier], user_id)
                if loot:
                    loot = [loot[0]]  # Just 1 item
                
                return {
                    "success": False,
                    "is_mimic": False,
                    "result": f"You struggle with the lock. (Roll: {roll}/{skill_rate})",
                    "forced_battle": False,
                    "xp_reward": 0,
                    "loot": loot,
                    "cooldown_until": cooldown_until
                }
    
    async def handle_trap_choice(self, user_id: int, choice: str) -> Dict:
        """Handle trap escape attempt or acceptance
        
        Args:
            choice: "attempt" or "accept"
        
        Returns: {
            "success": bool,
            "result": str,
            "trap_applied": bool,
            "xp_reward": int,
            "cooldown_until": float or None
        }
        """
        room_data = self.get_current_room_data()
        if not room_data or room_data["event_type"] != EVENT_TRAP:
            return {"success": False, "result": "Not a trap room"}
        
        trap_data = room_data.get("trap_data", {})
        if not trap_data:
            return {"success": False, "result": "Trap not found"}
        
        # Get pet data
        pet = await user_data_manager.get_pet_data_async(str(user_id))
        if not pet:
            return {"success": False, "result": "Pet not found"}
        
        if choice == "accept":
            # Accept trap: Apply at full value, award XP
            await self.apply_trap_effect_async(trap_data)
            xp_reward = self.calculate_xp_reward(pet, EVENT_TRAP, self.current_room)
            
            return {
                "success": True,
                "result": f"You brace yourself and trigger the {trap_data['name']}.",
                "trap_applied": True,
                "xp_reward": xp_reward,
                "cooldown_until": None
            }
        
        elif choice == "attempt":
            # Attempt escape
            stats = StatsCalculator.calculate_pet_stats(pet)
            trap_effect = trap_data.get("effect", "att_reduction")
            
            # Determine counter-stat based on trap type
            if trap_effect == "att_reduction":
                counter_stat = (stats["DEF"] + stats["INT"]) / 2
            elif trap_effect == "def_reduction":
                counter_stat = (stats["ATT"] + stats["HAP"]) / 2
            elif trap_effect == "dex_reduction":
                counter_stat = (stats["DEX"] + stats["ENE"]) / 2
            elif trap_effect == "int_reduction":
                counter_stat = (stats["INT"] + stats["HAP"]) / 2
            elif trap_effect == "health_half":
                counter_stat = (stats["ENE"] + stats["DEF"]) / 2
            elif trap_effect == "no_defend":
                counter_stat = (stats["DEX"] + stats["INT"]) / 2
            else:
                counter_stat = (stats["DEF"] + stats["INT"]) / 2  # Default
            
            # Escape formula
            floor_penalty = 1.0 + (self.current_floor - 1) * 0.03
            trap_value = trap_data.get("value", 0.10)
            trap_difficulty = trap_value * 20 * floor_penalty
            
            escape_rate = max(10, min(75, int((counter_stat / max(1, trap_difficulty)) * 50)))
            
            # Roll
            roll = random.randint(1, 100)
            success = roll <= escape_rate
            
            if success:
                # Escape success: No trap, award XP
                xp_reward = self.calculate_xp_reward(pet, EVENT_TRAP, self.current_room)
                
                return {
                    "success": True,
                    "result": f"You successfully avoid the {trap_data['name']}! (Roll: {roll}/{escape_rate})",
                    "trap_applied": False,
                    "xp_reward": xp_reward,
                    "cooldown_until": None
                }
            else:
                # Escape failure: Trap at FULL value + cooldown
                import time
                cooldown_until = time.time() + 3600
                
                await self.apply_trap_effect_async(trap_data)
                
                return {
                    "success": False,
                    "result": f"You fail to escape the {trap_data['name']}! (Roll: {roll}/{escape_rate})",
                    "trap_applied": True,
                    "xp_reward": 0,
                    "cooldown_until": cooldown_until
                }
        
        return {"success": False, "result": "Invalid choice"}
    
    async def check_room_cooldown(self) -> Dict:
        """Check if current room has an active cooldown
        
        Returns: {
            "on_cooldown": bool,
            "cooldown_until": float or None,
            "time_remaining": int (seconds)
        }
        """
        import time
        
        room_key = f"{self.current_floor}_{self.current_room}"
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('''
                SELECT fail_until FROM dungeon_story_cooldowns
                WHERE dungeon_id = ? AND room_key = ?
            ''', (self.dungeon_id, room_key)) as cursor:
                row = await cursor.fetchone()
                
                if row:
                    cooldown_until = row[0]
                    current_time = time.time()
                    
                    if current_time < cooldown_until:
                        return {
                            "on_cooldown": True,
                            "cooldown_until": cooldown_until,
                            "time_remaining": int(cooldown_until - current_time)
                        }
                    else:
                        # Cooldown expired, clean up
                        await db.execute('''
                            DELETE FROM dungeon_story_cooldowns
                            WHERE dungeon_id = ? AND room_key = ?
                        ''', (self.dungeon_id, room_key))
                        await db.commit()
        
        return {
            "on_cooldown": False,
            "cooldown_until": None,
            "time_remaining": 0
        }
    
    async def set_floor_cooldown(self) -> float:
        """Set 1-hour cooldown after completing floor 10
        
        Returns: cooldown_until timestamp
        """
        import time
        cooldown_until = time.time() + 3600  # 1 hour
        
        # Store in dungeon_state
        if 'floor_cooldown_until' not in self.dungeon_state:
            self.dungeon_state['floor_cooldown_until'] = {}
        
        self.dungeon_state['floor_cooldown_until'][str(self.current_floor)] = cooldown_until
        await self.save_dungeon()
        
        return cooldown_until
    
    async def check_floor_cooldown(self) -> Dict:
        """Check if there's an active floor cooldown
        
        Returns: {
            "on_cooldown": bool,
            "cooldown_until": float or None,
            "time_remaining": int (seconds)
        }
        """
        import time
        
        floor_cooldowns = self.dungeon_state.get('floor_cooldown_until', {})
        cooldown_until = floor_cooldowns.get(str(self.current_floor))
        
        if cooldown_until:
            current_time = time.time()
            
            if current_time < cooldown_until:
                return {
                    "on_cooldown": True,
                    "cooldown_until": cooldown_until,
                    "time_remaining": int(cooldown_until - current_time)
                }
            else:
                # Cooldown expired, clean up
                del floor_cooldowns[str(self.current_floor)]
                self.dungeon_state['floor_cooldown_until'] = floor_cooldowns
                await self.save_dungeon()
        
        return {
            "on_cooldown": False,
            "cooldown_until": None,
            "time_remaining": 0
        }
    
    async def advance_to_next_floor(self) -> Dict:
        """Advance to the next floor (only after completing room 10 and cooldown expired)
        
        Returns: {
            "success": bool,
            "result": str,
            "new_floor": int or None
        }
        """
        # Check if on floor loot room (room 10)
        if self.current_room != REWARD_ROOM:
            return {
                "success": False,
                "result": f"Must complete room 10 before advancing (currently on room {self.current_room})"
            }
        
        # Check floor cooldown
        cooldown_status = await self.check_floor_cooldown()
        if cooldown_status["on_cooldown"]:
            minutes = cooldown_status["time_remaining"] // 60
            seconds = cooldown_status["time_remaining"] % 60
            return {
                "success": False,
                "result": f"Floor cooldown active. {minutes}m {seconds}s remaining before you can advance."
            }
        
        # Advance to next floor
        self.current_floor += 1
        self.current_room = 1
        self.dungeon_state = self._generate_floor(self.current_floor)
        await self.save_dungeon()
        
        return {
            "success": True,
            "result": f"Advanced to floor {self.current_floor}!",
            "new_floor": self.current_floor
        }
    
    async def complete_room(self):
        """Mark current room as complete and advance"""
        room_data = self.get_current_room_data()
        if room_data:
            room_data["completed"] = True
            
            # Add event to history with chest_emoji if it's a chest event
            event_type = room_data.get("event_type", "unknown")
            event_summary = f"{event_type.replace('_', ' ').title()}"
            chest_emoji = room_data.get("chest_emoji")  # Get chest_emoji if present
            
            self.add_event_to_history(self.current_room, event_type, event_summary, chest_emoji)
            
            # CRITICAL FIX: Set floor cooldown when completing room 10
            if self.current_room == REWARD_ROOM and event_type == EVENT_FLOOR_LOOT:
                await self.set_floor_cooldown()
            
        # Decrement buff durations
        self.decrement_buff_durations()
        
        # Clear ready users for next room
        self.clear_ready_users()
        
        # Save progress
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR REPLACE INTO dungeon_progress 
                (dungeon_id, floor, room, event_type, completed)
                VALUES (?, ?, ?, ?, 1)
            ''', (
                self.dungeon_id,
                self.current_floor,
                self.current_room,
                room_data["event_type"] if room_data else "unknown"
            ))
            await db.commit()
            
        # Check if completing room 10 (floor loot)
        if self.current_room == REWARD_ROOM:
            # Set 1-hour floor cooldown before advancing
            await self.set_floor_cooldown()
            logger.info(f"Floor {self.current_floor} complete. 1-hour cooldown set before advancing to floor {self.current_floor + 1}")
            # DON'T auto-advance - user must explicitly advance after cooldown
        elif self.current_room >= ROOMS_PER_FLOOR:
            # This shouldn't happen with room 10 being REWARD_ROOM, but safety check
            self.current_floor += 1
            self.current_room = 1
            self.dungeon_state = self._generate_floor(self.current_floor)
            logger.info(f"Advanced to floor {self.current_floor}")
        else:
            # Advance to next room
            self.current_room += 1
            logger.info(f"Advanced to room {self.current_room}")
            
        await self.save_dungeon()
        
    async def get_dungeon_summary(self) -> Dict:
        """Get summary of dungeon progress"""
        return {
            "dungeon_id": self.dungeon_id,
            "party_leader": self.party_leader_id,
            "party_size": len(self.party_members),
            "current_floor": self.current_floor,
            "current_room": self.current_room,
            "total_rooms_cleared": (self.current_floor - 1) * ROOMS_PER_FLOOR + (self.current_room - 1)
        }


class DungeonCrawlView(discord.ui.View):
    """Discord UI for dungeon crawl"""
    
    def __init__(self, dungeon: DungeonCrawl, bot):
        super().__init__(timeout=None)
        self.dungeon = dungeon
        self.bot = bot
        self.ready_users = set()
        self.user_loot = {}  # {user_id: [items]}
        
    async def create_room_embed(self) -> discord.Embed:
        """Create embed for current room"""
        room_data = self.dungeon.get_current_room_data()
        
        if not room_data:
            return discord.Embed(
                title="❌ Error",
                description="Could not load room data",
                color=discord.Color.red()
            )
            
        event_type = room_data["event_type"]
        
        # Event type emojis
        event_emojis = {
            EVENT_MONSTER: "⚔️",
            EVENT_CHEST:   "📦",
            EVENT_CHEST1:  "📦",
            EVENT_CHEST2:  "🎁",
            EVENT_CHEST3:  "💎",
            EVENT_CHEST4:  "✨",
            EVENT_TRAP:    "🪤",
            EVENT_SHRINE:  "⛩️",
            EVENT_BOSS:    "👹"
        }
        
        embed = discord.Embed(
            title=f"{event_emojis.get(event_type, '❓')} Floor {self.dungeon.current_floor} - Room {self.dungeon.current_room}",
            color=discord.Color.blue()
        )
        
        # Event description
        if event_type == EVENT_MONSTER:
            embed.description = "A wild monster blocks your path!"
        elif event_type == EVENT_BOSS:
            embed.description = "**BOSS ROOM!** A powerful enemy awaits!"
        elif event_type == EVENT_CHEST1 or event_type == EVENT_CHEST:
            embed.description = "You found a **Chest 1**! Common/Uncommon loot awaits."
        elif event_type == EVENT_CHEST2:
            embed.description = "You found a **Chest 2**! Rare loot awaits."
        elif event_type == EVENT_CHEST3:
            embed.description = "You found a **Chest 3**! Epic loot awaits."
        elif event_type == EVENT_CHEST4:
            embed.description = "You found a **Chest 4**! Mythic-tier loot awaits!"
        elif event_type == EVENT_TRAP:
            trap_data = room_data.get("trap_data", {})
            trap_name = trap_data.get("name", "a trap")
            trap_emoji = trap_data.get("emoji", "🪤")
            tf = trap_data.get("target_filter")
            if tf:
                targets = ", ".join(v.title() for v in tf.get("values", []))
                mode = tf.get("mode", "element").title()
                embed.description = (
                    f"{trap_emoji} **{trap_name}** springs from the shadows!\n"
                    f"⚠️ This trap is especially dangerous to **{mode}**: {targets} pets."
                )
            else:
                embed.description = f"{trap_emoji} **{trap_name}** springs from the shadows! ⚠️ All party members are affected."
        elif event_type == EVENT_SHRINE:
            shrine_data = room_data.get("shrine_data", {})
            shrine_name = shrine_data.get("name", "a shrine")
            shrine_emoji = shrine_data.get("emoji", "⛩️")
            tf = shrine_data.get("target_filter")
            if tf:
                targets = ", ".join(v.title() for v in tf.get("values", []))
                mode = tf.get("mode", "element").title()
                embed.description = (
                    f"{shrine_emoji} **{shrine_name}** glows with ancient power!\n"
                    f"✨ This shrine blesses **{mode}**: {targets} pets."
                )
            else:
                embed.description = f"{shrine_emoji} **{shrine_name}** glows with ancient power! ✨ All party members are blessed."
            
        # Party status
        party_status = []
        for user_id in self.dungeon.party_members:
            user = self.bot.get_user(int(user_id))
            if user:
                ready_icon = "✅" if user_id in self.ready_users else "⏳"
                party_status.append(f"{ready_icon} {user.display_name}")
                
        embed.add_field(
            name="Party Status",
            value="\n".join(party_status) if party_status else "No party members",
            inline=False
        )
        
        # Active buffs/debuffs
        buff_summary = []
        for user_id in self.dungeon.party_members:
            buffs = self.dungeon.get_active_buffs(int(user_id))
            if buffs:
                user = self.bot.get_user(int(user_id))
                user_name = user.display_name if user else f"User {user_id}"
                for buff in buffs:
                    buff_summary.append(
                        f"{buff['emoji']} {user_name}: {buff['name']} ({buff['rooms_remaining']} rooms)"
                    )
                    
        if buff_summary:
            embed.add_field(
                name="Active Effects",
                value="\n".join(buff_summary[:10]),  # Limit to 10
                inline=False
            )
            
        embed.set_footer(text=f"Dungeon ID: {self.dungeon.dungeon_id}")
        
        return embed
        
    @discord.ui.button(label="Continue", style=discord.ButtonStyle.green, custom_id="dungeon_continue")
    async def continue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Mark user as ready to continue"""
        user_id = str(interaction.user.id)
        
        if user_id not in [str(m) for m in self.dungeon.party_members]:
            await interaction.response.send_message("You are not in this dungeon party!", ephemeral=True)
            return
            
        if user_id in self.ready_users:
            await interaction.response.send_message("You are already ready!", ephemeral=True)
            return
            
        self.ready_users.add(user_id)
        
        # Check if all party members are ready
        if len(self.ready_users) >= len(self.dungeon.party_members):
            await self.dungeon.complete_room()
            self.ready_users.clear()
            
            # Update to next room
            embed = await self.create_room_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            # Update embed to show ready status
            embed = await self.create_room_embed()
            await interaction.response.edit_message(embed=embed, view=self)



def apply_dungeon_buffs_to_pet(pet_data: Dict, buffs: List[Dict]) -> Dict:
    """Apply dungeon buffs/debuffs to pet stats for battle"""
    modified_pet = pet_data.copy()
    
    for buff in buffs:
        effect_type = buff["effect"]
        value = buff["value"]
        
        if effect_type == "att_reduction":
            current_att = modified_pet.get("ATT", modified_pet.get("attack", 10))
            modified_pet["ATT"] = max(1, int(current_att * (1 - value)))
            
        elif effect_type == "att_boost":
            current_att = modified_pet.get("ATT", modified_pet.get("attack", 10))
            modified_pet["ATT"] = int(current_att * (1 + value))
            
        elif effect_type == "def_reduction":
            current_def = modified_pet.get("DEF", modified_pet.get("defense", 5))
            modified_pet["DEF"] = max(1, int(current_def * (1 - value)))
            
        elif effect_type == "def_boost":
            current_def = modified_pet.get("DEF", modified_pet.get("defense", 5))
            modified_pet["DEF"] = int(current_def * (1 + value))
            
        elif effect_type == "dex_reduction":
            current_dex = modified_pet.get("DEX", 5)
            modified_pet["DEX"] = max(1, int(current_dex * (1 - value)))
                
        elif effect_type == "dex_boost":
            current_dex = modified_pet.get("DEX", 5)
            modified_pet["DEX"] = int(current_dex * (1 + value))
                
        elif effect_type == "int_reduction":
            current_int = modified_pet.get("INT", 5)
            modified_pet["INT"] = max(1, int(current_int * (1 - value)))
            
        elif effect_type == "int_boost":
            current_int = modified_pet.get("INT", 5)
            modified_pet["INT"] = int(current_int * (1 + value))
            
        elif effect_type == "health_half":
            current_health = modified_pet.get("health", 100)
            modified_pet["health"] = max(1, int(current_health * (1 - value)))
            
        elif effect_type == "health_boost":
            current_health = modified_pet.get("health", 100)
            max_health = modified_pet.get("max_health", 100)
            boosted = int(current_health * (1 + value))
            modified_pet["health"] = min(boosted, max_health)
            
        elif effect_type == "no_defend":
            # This needs to be handled in battle system
            modified_pet["_dungeon_no_defend"] = True
            
        elif effect_type == "charge_boost":
            # This needs to be handled in battle system
            modified_pet["_dungeon_charge_boost"] = value
            
    return modified_pet


def get_buff_summary(buffs: List[Dict]) -> str:
    """Get a summary string of active buffs"""
    if not buffs:
        return "No active effects"
        
    summary = []
    for buff in buffs:
        emoji = buff.get("emoji", "")
        name = buff.get("name", "Unknown")
        rooms = buff.get("rooms_remaining", 0)
        summary.append(f"{emoji} {name} ({rooms} rooms)")
        
    return "\n".join(summary)
