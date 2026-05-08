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
# Emoji mention helpers (static IDs from EMOJI_IDS — no bot needed at import)
# ---------------------------------------------------------------------------
def _e(key: str) -> str:
    """Return a Discord custom-emoji mention string for the given EMOJI_IDS key."""
    from Systems.Functions.emoji import EMOJI_IDS
    eid = EMOJI_IDS.get(key)
    if eid:
        return f"<:{key}:{eid}>"
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
def _resolve_emoji(entry: Dict) -> Dict:
    """Return a copy of entry with 'emoji' set from 'emoji_key' if present."""
    entry = dict(entry)
    key = entry.pop("emoji_key", None)
    if key and "emoji" not in entry:
        entry["emoji"] = _e(key)
    return entry

TRAP_EFFECTS = (
    [_resolve_emoji(t) for t in TRAP_EFFECTS_GENERIC]
    + [_resolve_emoji(t) for t in TRAP_EFFECTS_ELEMENTAL]
    + [_resolve_emoji(t) for t in TRAP_EFFECTS_TYPE]
)

SHRINE_EFFECTS = (
    [_resolve_emoji(s) for s in SHRINE_EFFECTS_GENERIC]
    + [_resolve_emoji(s) for s in SHRINE_EFFECTS_ELEMENTAL]
    + [_resolve_emoji(s) for s in SHRINE_EFFECTS_TYPE]
)

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
            await db.commit()
            
    async def create_dungeon(self, party_members: List[int]) -> str:
        """Create a new dungeon instance"""
        await self.initialize_database()
        
        if len(party_members) > MAX_PARTY_SIZE:
            raise ValueError(f"Party size cannot exceed {MAX_PARTY_SIZE} members")
            
        self.dungeon_id = f"dungeon_{self.party_leader_id}_{int(datetime.now().timestamp())}"
        self.party_members = party_members
        self.dungeon_state = self._generate_floor(1)
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO dungeons (dungeon_id, party_leader_id, party_members, dungeon_state, party_buffs, ready_users)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                self.dungeon_id,
                str(self.party_leader_id),
                json.dumps([str(m) for m in party_members]),
                json.dumps(self.dungeon_state),
                json.dumps({}),
                json.dumps([])
            ))
            await db.commit()
            
        logger.info(f"Created dungeon {self.dungeon_id} with {len(party_members)} members")
        return self.dungeon_id
        
    async def load_dungeon(self, dungeon_id: str) -> bool:
        """Load existing dungeon state"""
        await self.initialize_database()
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('''
                SELECT party_leader_id, party_members, current_floor, current_room, 
                       dungeon_state, party_buffs, ready_users, completed
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
                
                if row[7]:  # completed
                    logger.info(f"Dungeon {dungeon_id} is already completed")
                    return False
                    
        logger.info(f"Loaded dungeon {dungeon_id} at floor {self.current_floor}, room {self.current_room}")
        return True
        
    async def save_dungeon(self):
        """Save current dungeon state"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE dungeons 
                SET current_floor = ?, current_room = ?, dungeon_state = ?, 
                    party_buffs = ?, ready_users = ?, updated_at = CURRENT_TIMESTAMP
                WHERE dungeon_id = ?
            ''', (
                self.current_floor,
                self.current_room,
                json.dumps(self.dungeon_state),
                json.dumps(self.party_buffs),
                json.dumps(list(self.ready_users)),
                self.dungeon_id
            ))
            await db.commit()
            
    def _generate_floor(self, floor_number: int) -> Dict:
        """Generate a floor with 10 rooms.

        Rooms 1-8: weighted random events
            75.0% Monster
            10.0% Shrine
            10.0% Trap
             2.0% Chest 1  (Common/Uncommon)
             1.5% Chest 2  (Rare)
             1.0% Chest 3  (Epic)
             0.5% Chest 4  (Mythic mix)
        Room 9:  always Boss
        Room 10: always a random Chest (Chest 1-4, equal chance)
        """
        floor_data = {"floor": floor_number, "rooms": []}

        # Weighted pool for rooms 1-8 (weights sum to 100)
        _event_pool = [
            EVENT_MONSTER,
            EVENT_SHRINE,
            EVENT_TRAP,
            EVENT_CHEST1,
            EVENT_CHEST2,
            EVENT_CHEST3,
            EVENT_CHEST4,
        ]
        _event_weights = [75.0, 10.0, 10.0, 2.0, 1.5, 1.0, 0.5]

        for room_num in range(1, ROOMS_PER_FLOOR + 1):
            if room_num == BOSS_ROOM:
                # Room 9 is always the boss
                room_data = {
                    "room": room_num,
                    "event_type": EVENT_BOSS,
                    "completed": False
                }
            elif room_num == REWARD_ROOM:
                # Room 10 is always a guaranteed chest (random tier, equal weight)
                chest_event = random.choice([EVENT_CHEST1, EVENT_CHEST2, EVENT_CHEST3, EVENT_CHEST4])
                chest_type = CHEST_TYPES[CHEST_EVENT_MAP[chest_event]]
                room_data = {
                    "room": room_num,
                    "event_type": chest_event,
                    "completed": False,
                    "chest_type": chest_type["name"],
                    "chest_emoji": chest_type["emoji"],
                    "chest_rarity_pool": chest_type["rarity_pool"],
                    "chest_count": chest_type["count"],
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
                if event_type in CHEST_EVENT_MAP:
                    chest_type = CHEST_TYPES[CHEST_EVENT_MAP[event_type]]
                    room_data["chest_type"] = chest_type["name"]
                    room_data["chest_emoji"] = chest_type["emoji"]
                    room_data["chest_rarity_pool"] = chest_type["rarity_pool"]
                    room_data["chest_count"] = chest_type["count"]
                elif event_type == EVENT_TRAP:
                    # 50/50 chance: generic pool vs elemental+type pool
                    # This ensures dungeon feels varied regardless of party composition
                    _trap_pool = (TRAP_EFFECTS_GENERIC if random.random() < 0.5
                                  else TRAP_EFFECTS_ELEMENTAL + TRAP_EFFECTS_TYPE)
                    trap = _resolve_emoji(random.choice(_trap_pool))
                    room_data["trap_data"] = trap
                elif event_type == EVENT_SHRINE:
                    # 50/50 chance: generic pool vs elemental+type pool
                    _shrine_pool = (SHRINE_EFFECTS_GENERIC if random.random() < 0.5
                                    else SHRINE_EFFECTS_ELEMENTAL + SHRINE_EFFECTS_TYPE)
                    shrine = _resolve_emoji(random.choice(_shrine_pool))
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
                monsters = [{"name": "Wirm", "emoji_file": "Wirm.png", "category": "Land", "element": "Basic"}]
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
        
        # emoji_file: monsters use Equipment folder, bosses use Pets folder
        emoji_file = monster_template.get('emoji_file')
        if not emoji_file and not is_boss:
            emoji_file = monster_template['name'].replace(' ', '') + '.png'
        
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
        
        # Collect all items matching rarity
        available_items = []
        for category in ["Materials", "Gems", "Monsters", "Hats", "Potions"]:
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
    
    async def complete_room(self):
        """Mark current room as complete and advance"""
        room_data = self.get_current_room_data()
        if room_data:
            room_data["completed"] = True
            
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
            
        # Advance to next room or floor
        if self.current_room >= ROOMS_PER_FLOOR:
            self.current_floor += 1
            self.current_room = 1
            self.dungeon_state = self._generate_floor(self.current_floor)
            logger.info(f"Advanced to floor {self.current_floor}")
        else:
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
            current_att = modified_pet.get("attack", 10)
            modified_pet["attack"] = int(current_att * (1 - value))
            
        elif effect_type == "att_boost":
            current_att = modified_pet.get("attack", 10)
            modified_pet["attack"] = int(current_att * (1 + value))
            
        elif effect_type == "def_reduction":
            current_def = modified_pet.get("defense", 5)
            modified_pet["defense"] = int(current_def * (1 - value))
            
        elif effect_type == "def_boost":
            current_def = modified_pet.get("defense", 5)
            modified_pet["defense"] = int(current_def * (1 + value))
            
        elif effect_type == "dex_reduction":
            # DEX affects computed attack
            if "equipment" in modified_pet:
                # Reduce DEX bonus from equipment
                pass  # Handled by StatsCalculator
                
        elif effect_type == "dex_boost":
            # DEX affects computed attack
            if "equipment" in modified_pet:
                # Increase DEX bonus from equipment
                pass  # Handled by StatsCalculator
                
        elif effect_type == "int_reduction":
            # INT affects computed defense
            pass  # Handled by StatsCalculator
            
        elif effect_type == "int_boost":
            # INT affects computed defense
            pass  # Handled by StatsCalculator
            
        elif effect_type == "health_half":
            current_health = modified_pet.get("health", 100)
            modified_pet["health"] = int(current_health * value)
            
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
