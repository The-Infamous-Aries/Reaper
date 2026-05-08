"""
Battle Skills System
====================
325 unique battle skills across 13 elements (25 per element).
Skills are active abilities used in battle — one per other turn.

Skill effect types:
  instant_damage      — deals immediate bonus damage (multiplied by attacker ATK)
  dot                 — damage over time: applies N ticks of damage each subsequent turn
  shield              — absorbs incoming damage for N turns
  damage_reduction    — reduces all incoming damage by a % for N turns
  elemental_damage    — adds an elemental multiplier to the next attack
  heal                — restores HP to self
  charge_boost        — immediately adds charge levels
  stat_debuff         — reduces enemy ATK or DEF for N turns
  stat_buff           — increases own ATK or DEF for N turns
  lifesteal           — deals damage and heals self for a % of damage dealt
  stun                — enemy skips their action next turn (NPC: forced defend)
  cleanse             — removes all negative effects from self
  reflect             — reflects a % of incoming damage back to attacker for N turns

Data stored on pet:
  pet["battle_skills"]         list[str]  — skill IDs equipped (1 base + extras from ability)

Data stored on player_data (battle state, NOT persisted to pet):
  player_data["skill_cooldowns"] dict[int,int] — {slot_index: turns_remaining} per-slot cooldowns
  player_data["active_effects"]  list[dict]   — active DoT/shield/buff/debuff/reflect effects

Slot management:
  Base slots: 1
  Extra slots: purchased via ability tree (skill_slot_2, skill_slot_3, skill_slot_4)
  Max slots: 4

Skill selection:
  On first equip / reroll: draw 5 random skills from element pool, player picks 1 per slot
  Cross-element slot: draw 10 random skills from ALL OTHER elements, player picks 1

Cooldown rule:
  After using a skill, that slot's cooldown is set to 3.
  Each round start ALL slot cooldowns decrement by 1.
  A slot is usable when its cooldown == 0.
  Each slot tracks independently — using slot 0 does NOT lock slot 1.
  (Effectively: use slot on turn T, locked T+1 and T+2, ready again T+3)
"""

from __future__ import annotations
import random
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("battle_skills")

# ── All 13 elements ──────────────────────────────────────────────────────────
ALL_ELEMENTS: List[str] = [
    "basic", "fire", "water", "electric", "ice",
    "plant", "rock", "air", "magic", "holy",
    "necro", "psychic", "fighting",
]

SKILL_COOLDOWN_TURNS = 3  # turns locked after use (use T, locked T+1 and T+2, ready T+3)


# ── SKILL POOL ───────────────────────────────────────────────────────────────
# Each skill dict:
#   id          str   — unique key
#   name        str   — display name
#   element     str   — which element pool it belongs to
#   description str   — shown in UI
#   effect      dict  — machine-readable effect descriptor
#
# Effect keys:
#   type        str   — effect type (see module docstring)
#   value       float — primary magnitude
#   turns       int   — duration for DoT/shield/buff/debuff/reflect (omit for instant)
#   stat        str   — for stat_buff/debuff: "atk" or "def"
#   heal_pct    float — for lifesteal: fraction of damage healed
#   element     str   — for elemental_damage: which element bonus to apply

SKILL_POOL: List[Dict[str, Any]] = [

    # ════════════════════════════════════════════════════════════════════════
    # BASIC  (25 skills — balanced, no elemental theme, jack-of-all-trades)
    # ════════════════════════════════════════════════════════════════════════
    {
        "id": "basic_001", "name": "Power Strike", "element": "basic",
        "description": "A focused strike dealing 40% bonus damage.",
        "effect": {"type": "instant_damage", "value": 0.40},
    },
    {
        "id": "basic_002", "name": "Iron Guard", "element": "basic",
        "description": "Raise a sturdy guard, reducing incoming damage by 25% for 2 turns.",
        "effect": {"type": "damage_reduction", "value": 0.25, "turns": 2},
    },
    {
        "id": "basic_003", "name": "Steady Resolve", "element": "basic",
        "description": "Heal 12% of max HP.",
        "effect": {"type": "heal", "value": 0.12},
    },
    {
        "id": "basic_004", "name": "Adrenaline Rush", "element": "basic",
        "description": "Boost ATK by 30% for 3 turns.",
        "effect": {"type": "stat_buff", "stat": "atk", "value": 0.30, "turns": 3},
    },
    {
        "id": "basic_005", "name": "Fortify", "element": "basic",
        "description": "Boost DEF by 30% for 3 turns.",
        "effect": {"type": "stat_buff", "stat": "def", "value": 0.30, "turns": 3},
    },
    {
        "id": "basic_006", "name": "Rend", "element": "basic",
        "description": "Slash the enemy, reducing their ATK by 20% for 2 turns.",
        "effect": {"type": "stat_debuff", "stat": "atk", "value": 0.20, "turns": 2},
    },
    {
        "id": "basic_007", "name": "Hamstring", "element": "basic",
        "description": "Cripple the enemy, reducing their DEF by 20% for 2 turns.",
        "effect": {"type": "stat_debuff", "stat": "def", "value": 0.20, "turns": 2},
    },
    {
        "id": "basic_008", "name": "Bulwark", "element": "basic",
        "description": "Erect a shield absorbing 35% of max HP in damage for 2 turns.",
        "effect": {"type": "shield", "value": 0.35, "turns": 2},
    },
    {
        "id": "basic_009", "name": "Drain Strike", "element": "basic",
        "description": "Deal 30% bonus damage and heal for 40% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.30, "heal_pct": 0.40},
    },
    {
        "id": "basic_010", "name": "Overpower", "element": "basic",
        "description": "Stun the enemy, forcing them to skip their next action.",
        "effect": {"type": "stun", "turns": 1},
    },
    {
        "id": "basic_011", "name": "Cleanse", "element": "basic",
        "description": "Remove all negative effects currently on yourself.",
        "effect": {"type": "cleanse"},
    },
    {
        "id": "basic_012", "name": "Mirror Stance", "element": "basic",
        "description": "Reflect 30% of incoming damage back to the attacker for 2 turns.",
        "effect": {"type": "reflect", "value": 0.30, "turns": 2},
    },
    {
        "id": "basic_013", "name": "Quick Charge", "element": "basic",
        "description": "Instantly gain +2 charge levels.",
        "effect": {"type": "charge_boost", "value": 2},
    },
    {
        "id": "basic_014", "name": "Wound", "element": "basic",
        "description": "Inflict a bleeding wound dealing 8% ATK damage per turn for 3 turns.",
        "effect": {"type": "dot", "value": 0.08, "turns": 3},
    },
    {
        "id": "basic_015", "name": "Rallying Cry", "element": "basic",
        "description": "Boost ATK by 20% and DEF by 20% for 2 turns.",
        "effect": {"type": "stat_buff", "stat": "atk", "value": 0.20, "turns": 2,
                   "secondary": {"type": "stat_buff", "stat": "def", "value": 0.20, "turns": 2}},
    },
    {
        "id": "basic_016", "name": "Crushing Blow", "element": "basic",
        "description": "A devastating strike dealing 60% bonus damage.",
        "effect": {"type": "instant_damage", "value": 0.60},
    },
    {
        "id": "basic_017", "name": "Endure", "element": "basic",
        "description": "Reduce incoming damage by 40% for 1 turn.",
        "effect": {"type": "damage_reduction", "value": 0.40, "turns": 1},
    },
    {
        "id": "basic_018", "name": "Second Wind", "element": "basic",
        "description": "Heal 20% of max HP.",
        "effect": {"type": "heal", "value": 0.20},
    },
    {
        "id": "basic_019", "name": "Expose Weakness", "element": "basic",
        "description": "Reduce enemy DEF by 35% for 2 turns.",
        "effect": {"type": "stat_debuff", "stat": "def", "value": 0.35, "turns": 2},
    },
    {
        "id": "basic_020", "name": "Tenacity", "element": "basic",
        "description": "Boost DEF by 50% for 2 turns.",
        "effect": {"type": "stat_buff", "stat": "def", "value": 0.50, "turns": 2},
    },
    {
        "id": "basic_021", "name": "Bleed Out", "element": "basic",
        "description": "Inflict deep wounds dealing 12% ATK damage per turn for 4 turns.",
        "effect": {"type": "dot", "value": 0.12, "turns": 4},
    },
    {
        "id": "basic_022", "name": "Absorb", "element": "basic",
        "description": "Shield absorbing 50% of max HP in damage for 1 turn.",
        "effect": {"type": "shield", "value": 0.50, "turns": 1},
    },
    {
        "id": "basic_023", "name": "Vampiric Strike", "element": "basic",
        "description": "Deal 50% bonus damage and heal for 60% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.50, "heal_pct": 0.60},
    },
    {
        "id": "basic_024", "name": "Daze", "element": "basic",
        "description": "Reduce enemy ATK by 30% for 3 turns.",
        "effect": {"type": "stat_debuff", "stat": "atk", "value": 0.30, "turns": 3},
    },
    {
        "id": "basic_025", "name": "Full Counter", "element": "basic",
        "description": "Reflect 50% of incoming damage back to the attacker for 1 turn.",
        "effect": {"type": "reflect", "value": 0.50, "turns": 1},
    },

    # ════════════════════════════════════════════════════════════════════════
    # FIRE  (25 skills — burn DoTs, explosive bursts, heat shields, ignition)
    # ════════════════════════════════════════════════════════════════════════
    {
        "id": "fire_001", "name": "Ember Burst", "element": "fire",
        "description": "Hurl a burst of embers dealing 35% bonus fire damage.",
        "effect": {"type": "instant_damage", "value": 0.35, "element": "fire"},
    },
    {
        "id": "fire_002", "name": "Ignite", "element": "fire",
        "description": "Set the enemy ablaze, dealing 10% ATK fire damage per turn for 3 turns.",
        "effect": {"type": "dot", "value": 0.10, "turns": 3, "element": "fire"},
    },
    {
        "id": "fire_003", "name": "Inferno", "element": "fire",
        "description": "Unleash a roaring inferno dealing 65% bonus fire damage.",
        "effect": {"type": "instant_damage", "value": 0.65, "element": "fire"},
    },
    {
        "id": "fire_004", "name": "Scorched Earth", "element": "fire",
        "description": "Burn the ground beneath the enemy, dealing 8% ATK fire damage per turn for 4 turns.",
        "effect": {"type": "dot", "value": 0.08, "turns": 4, "element": "fire"},
    },
    {
        "id": "fire_005", "name": "Heat Shield", "element": "fire",
        "description": "Surround yourself in flames, absorbing 40% of max HP in damage for 2 turns.",
        "effect": {"type": "shield", "value": 0.40, "turns": 2},
    },
    {
        "id": "fire_006", "name": "Flame Cloak", "element": "fire",
        "description": "Reflect 35% of incoming damage as fire damage for 2 turns.",
        "effect": {"type": "reflect", "value": 0.35, "turns": 2, "element": "fire"},
    },
    {
        "id": "fire_007", "name": "Wildfire", "element": "fire",
        "description": "Reduce enemy DEF by 25% for 3 turns (melted by heat).",
        "effect": {"type": "stat_debuff", "stat": "def", "value": 0.25, "turns": 3},
    },
    {
        "id": "fire_008", "name": "Blazing Fury", "element": "fire",
        "description": "Boost ATK by 40% for 2 turns, fueled by rage.",
        "effect": {"type": "stat_buff", "stat": "atk", "value": 0.40, "turns": 2},
    },
    {
        "id": "fire_009", "name": "Phoenix Drain", "element": "fire",
        "description": "Deal 40% bonus fire damage and heal 50% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.40, "heal_pct": 0.50, "element": "fire"},
    },
    {
        "id": "fire_010", "name": "Flashfire", "element": "fire",
        "description": "Blind the enemy with a flash of fire, stunning them for 1 turn.",
        "effect": {"type": "stun", "turns": 1},
    },
    {
        "id": "fire_011", "name": "Cauterize", "element": "fire",
        "description": "Burn away wounds, healing 15% of max HP.",
        "effect": {"type": "heal", "value": 0.15},
    },
    {
        "id": "fire_012", "name": "Magma Core", "element": "fire",
        "description": "Reduce incoming damage by 30% for 2 turns (hardened lava skin).",
        "effect": {"type": "damage_reduction", "value": 0.30, "turns": 2},
    },
    {
        "id": "fire_013", "name": "Combustion", "element": "fire",
        "description": "Instantly gain +2 charge levels as internal fire ignites.",
        "effect": {"type": "charge_boost", "value": 2},
    },
    {
        "id": "fire_014", "name": "Searing Brand", "element": "fire",
        "description": "Brand the enemy, reducing their ATK by 25% for 3 turns.",
        "effect": {"type": "stat_debuff", "stat": "atk", "value": 0.25, "turns": 3},
    },
    {
        "id": "fire_015", "name": "Purifying Flame", "element": "fire",
        "description": "Burn away all negative effects on yourself.",
        "effect": {"type": "cleanse"},
    },
    {
        "id": "fire_016", "name": "Eruption", "element": "fire",
        "description": "Volcanic eruption dealing 55% bonus fire damage.",
        "effect": {"type": "instant_damage", "value": 0.55, "element": "fire"},
    },
    {
        "id": "fire_017", "name": "Napalm", "element": "fire",
        "description": "Coat the enemy in sticky fire, dealing 15% ATK fire damage per turn for 3 turns.",
        "effect": {"type": "dot", "value": 0.15, "turns": 3, "element": "fire"},
    },
    {
        "id": "fire_018", "name": "Firestorm", "element": "fire",
        "description": "Boost ATK by 25% and reduce enemy DEF by 20% for 2 turns.",
        "effect": {"type": "stat_buff", "stat": "atk", "value": 0.25, "turns": 2,
                   "secondary": {"type": "stat_debuff", "stat": "def", "value": 0.20, "turns": 2}},
    },
    {
        "id": "fire_019", "name": "Molten Shield", "element": "fire",
        "description": "Shield absorbing 55% of max HP in damage for 1 turn.",
        "effect": {"type": "shield", "value": 0.55, "turns": 1},
    },
    {
        "id": "fire_020", "name": "Backdraft", "element": "fire",
        "description": "Reflect 50% of incoming damage as fire for 1 turn.",
        "effect": {"type": "reflect", "value": 0.50, "turns": 1, "element": "fire"},
    },
    {
        "id": "fire_021", "name": "Smoldering Aura", "element": "fire",
        "description": "Boost DEF by 35% for 3 turns (heat haze deflects blows).",
        "effect": {"type": "stat_buff", "stat": "def", "value": 0.35, "turns": 3},
    },
    {
        "id": "fire_022", "name": "Lava Surge", "element": "fire",
        "description": "Deal 45% bonus fire damage and apply 6% ATK fire DoT for 2 turns.",
        "effect": {"type": "instant_damage", "value": 0.45, "element": "fire",
                   "secondary": {"type": "dot", "value": 0.06, "turns": 2, "element": "fire"}},
    },
    {
        "id": "fire_023", "name": "Flame Vortex", "element": "fire",
        "description": "Reduce enemy ATK by 35% for 2 turns (disoriented by spinning fire).",
        "effect": {"type": "stat_debuff", "stat": "atk", "value": 0.35, "turns": 2},
    },
    {
        "id": "fire_024", "name": "Solar Flare", "element": "fire",
        "description": "Heal 25% of max HP using solar fire energy.",
        "effect": {"type": "heal", "value": 0.25},
    },
    {
        "id": "fire_025", "name": "Cinder Drain", "element": "fire",
        "description": "Deal 55% bonus fire damage and heal 70% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.55, "heal_pct": 0.70, "element": "fire"},
    },

    # ════════════════════════════════════════════════════════════════════════
    # WATER  (25 skills — tidal surges, healing currents, ice-cold debuffs)
    # ════════════════════════════════════════════════════════════════════════
    {
        "id": "water_001", "name": "Tidal Strike", "element": "water",
        "description": "Crash a wave dealing 35% bonus water damage.",
        "effect": {"type": "instant_damage", "value": 0.35, "element": "water"},
    },
    {
        "id": "water_002", "name": "Whirlpool", "element": "water",
        "description": "Trap the enemy in a whirlpool, dealing 9% ATK water damage per turn for 3 turns.",
        "effect": {"type": "dot", "value": 0.09, "turns": 3, "element": "water"},
    },
    {
        "id": "water_003", "name": "Healing Spring", "element": "water",
        "description": "Draw from a healing spring, restoring 18% of max HP.",
        "effect": {"type": "heal", "value": 0.18},
    },
    {
        "id": "water_004", "name": "Aqua Shield", "element": "water",
        "description": "A flowing water barrier absorbing 40% of max HP in damage for 2 turns.",
        "effect": {"type": "shield", "value": 0.40, "turns": 2},
    },
    {
        "id": "water_005", "name": "Riptide", "element": "water",
        "description": "Powerful current dealing 55% bonus water damage.",
        "effect": {"type": "instant_damage", "value": 0.55, "element": "water"},
    },
    {
        "id": "water_006", "name": "Undertow", "element": "water",
        "description": "Drag the enemy under, reducing their ATK by 25% for 3 turns.",
        "effect": {"type": "stat_debuff", "stat": "atk", "value": 0.25, "turns": 3},
    },
    {
        "id": "water_007", "name": "Fluid Form", "element": "water",
        "description": "Become fluid, reducing incoming damage by 30% for 2 turns.",
        "effect": {"type": "damage_reduction", "value": 0.30, "turns": 2},
    },
    {
        "id": "water_008", "name": "Surge", "element": "water",
        "description": "Boost ATK by 35% for 2 turns (riding the wave).",
        "effect": {"type": "stat_buff", "stat": "atk", "value": 0.35, "turns": 2},
    },
    {
        "id": "water_009", "name": "Leech Current", "element": "water",
        "description": "Deal 40% bonus water damage and heal 45% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.40, "heal_pct": 0.45, "element": "water"},
    },
    {
        "id": "water_010", "name": "Tsunami", "element": "water",
        "description": "Massive wave dealing 70% bonus water damage.",
        "effect": {"type": "instant_damage", "value": 0.70, "element": "water"},
    },
    {
        "id": "water_011", "name": "Drowning Grip", "element": "water",
        "description": "Hold the enemy underwater, stunning them for 1 turn.",
        "effect": {"type": "stun", "turns": 1},
    },
    {
        "id": "water_012", "name": "Cleansing Rain", "element": "water",
        "description": "Purifying rain removes all negative effects.",
        "effect": {"type": "cleanse"},
    },
    {
        "id": "water_013", "name": "Tidal Charge", "element": "water",
        "description": "Ride the tide, instantly gaining +2 charge levels.",
        "effect": {"type": "charge_boost", "value": 2},
    },
    {
        "id": "water_014", "name": "Erode", "element": "water",
        "description": "Slowly erode enemy DEF by 30% for 3 turns.",
        "effect": {"type": "stat_debuff", "stat": "def", "value": 0.30, "turns": 3},
    },
    {
        "id": "water_015", "name": "Torrent", "element": "water",
        "description": "Relentless torrent dealing 10% ATK water damage per turn for 4 turns.",
        "effect": {"type": "dot", "value": 0.10, "turns": 4, "element": "water"},
    },
    {
        "id": "water_016", "name": "Bubble Barrier", "element": "water",
        "description": "Reflect 30% of incoming damage as water for 2 turns.",
        "effect": {"type": "reflect", "value": 0.30, "turns": 2, "element": "water"},
    },
    {
        "id": "water_017", "name": "Deep Current", "element": "water",
        "description": "Boost DEF by 35% for 3 turns (deep water pressure).",
        "effect": {"type": "stat_buff", "stat": "def", "value": 0.35, "turns": 3},
    },
    {
        "id": "water_018", "name": "Hydro Pump", "element": "water",
        "description": "High-pressure blast dealing 50% bonus water damage.",
        "effect": {"type": "instant_damage", "value": 0.50, "element": "water"},
    },
    {
        "id": "water_019", "name": "Mist Veil", "element": "water",
        "description": "Reduce incoming damage by 45% for 1 turn (hidden in mist).",
        "effect": {"type": "damage_reduction", "value": 0.45, "turns": 1},
    },
    {
        "id": "water_020", "name": "Siphon Stream", "element": "water",
        "description": "Deal 55% bonus water damage and heal 65% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.55, "heal_pct": 0.65, "element": "water"},
    },
    {
        "id": "water_021", "name": "Flood", "element": "water",
        "description": "Flood the field, dealing 12% ATK water damage per turn for 3 turns.",
        "effect": {"type": "dot", "value": 0.12, "turns": 3, "element": "water"},
    },
    {
        "id": "water_022", "name": "Tidal Surge", "element": "water",
        "description": "Deal 45% bonus water damage and reduce enemy ATK by 20% for 2 turns.",
        "effect": {"type": "instant_damage", "value": 0.45, "element": "water",
                   "secondary": {"type": "stat_debuff", "stat": "atk", "value": 0.20, "turns": 2}},
    },
    {
        "id": "water_023", "name": "Ocean Mend", "element": "water",
        "description": "Restore 28% of max HP from the ocean's healing power.",
        "effect": {"type": "heal", "value": 0.28},
    },
    {
        "id": "water_024", "name": "Maelstrom", "element": "water",
        "description": "Reduce enemy ATK by 35% for 2 turns (disoriented by spinning water).",
        "effect": {"type": "stat_debuff", "stat": "atk", "value": 0.35, "turns": 2},
    },
    {
        "id": "water_025", "name": "Tidal Wall", "element": "water",
        "description": "Shield absorbing 55% of max HP in damage for 1 turn.",
        "effect": {"type": "shield", "value": 0.55, "turns": 1},
    },

    # ════════════════════════════════════════════════════════════════════════
    # ELECTRIC  (25 skills — lightning strikes, paralysis, charge boosts)
    # ════════════════════════════════════════════════════════════════════════
    {
        "id": "electric_001", "name": "Spark", "element": "electric",
        "description": "A quick spark dealing 30% bonus electric damage.",
        "effect": {"type": "instant_damage", "value": 0.30, "element": "electric"},
    },
    {
        "id": "electric_002", "name": "Thunderbolt", "element": "electric",
        "description": "A powerful bolt dealing 60% bonus electric damage.",
        "effect": {"type": "instant_damage", "value": 0.60, "element": "electric"},
    },
    {
        "id": "electric_003", "name": "Static Field", "element": "electric",
        "description": "Surround yourself in static, dealing 9% ATK electric damage per turn for 3 turns.",
        "effect": {"type": "dot", "value": 0.09, "turns": 3, "element": "electric"},
    },
    {
        "id": "electric_004", "name": "Paralysis Shock", "element": "electric",
        "description": "Shock the enemy, stunning them for 1 turn.",
        "effect": {"type": "stun", "turns": 1},
    },
    {
        "id": "electric_005", "name": "Overload", "element": "electric",
        "description": "Instantly gain +3 charge levels from electrical surge.",
        "effect": {"type": "charge_boost", "value": 3},
    },
    {
        "id": "electric_006", "name": "Voltage Spike", "element": "electric",
        "description": "Boost ATK by 45% for 2 turns (supercharged).",
        "effect": {"type": "stat_buff", "stat": "atk", "value": 0.45, "turns": 2},
    },
    {
        "id": "electric_007", "name": "Grounding Field", "element": "electric",
        "description": "Reduce incoming damage by 30% for 2 turns (grounded).",
        "effect": {"type": "damage_reduction", "value": 0.30, "turns": 2},
    },
    {
        "id": "electric_008", "name": "Chain Lightning", "element": "electric",
        "description": "Deal 45% bonus electric damage and apply 7% ATK electric DoT for 2 turns.",
        "effect": {"type": "instant_damage", "value": 0.45, "element": "electric",
                   "secondary": {"type": "dot", "value": 0.07, "turns": 2, "element": "electric"}},
    },
    {
        "id": "electric_009", "name": "Discharge", "element": "electric",
        "description": "Reduce enemy ATK by 30% for 3 turns (circuits fried).",
        "effect": {"type": "stat_debuff", "stat": "atk", "value": 0.30, "turns": 3},
    },
    {
        "id": "electric_010", "name": "Faraday Shield", "element": "electric",
        "description": "Electromagnetic shield absorbing 45% of max HP in damage for 2 turns.",
        "effect": {"type": "shield", "value": 0.45, "turns": 2},
    },
    {
        "id": "electric_011", "name": "Arc Reflect", "element": "electric",
        "description": "Reflect 35% of incoming damage as electric for 2 turns.",
        "effect": {"type": "reflect", "value": 0.35, "turns": 2, "element": "electric"},
    },
    {
        "id": "electric_012", "name": "Galvanize", "element": "electric",
        "description": "Boost DEF by 30% for 3 turns (hardened by electricity).",
        "effect": {"type": "stat_buff", "stat": "def", "value": 0.30, "turns": 3},
    },
    {
        "id": "electric_013", "name": "Zap Drain", "element": "electric",
        "description": "Deal 40% bonus electric damage and heal 45% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.40, "heal_pct": 0.45, "element": "electric"},
    },
    {
        "id": "electric_014", "name": "Defibrillate", "element": "electric",
        "description": "Shock yourself back to health, restoring 20% of max HP.",
        "effect": {"type": "heal", "value": 0.20},
    },
    {
        "id": "electric_015", "name": "Static Purge", "element": "electric",
        "description": "Discharge all negative effects from your body.",
        "effect": {"type": "cleanse"},
    },
    {
        "id": "electric_016", "name": "Ball Lightning", "element": "electric",
        "description": "Floating orb dealing 11% ATK electric damage per turn for 4 turns.",
        "effect": {"type": "dot", "value": 0.11, "turns": 4, "element": "electric"},
    },
    {
        "id": "electric_017", "name": "Plasma Burst", "element": "electric",
        "description": "Superheated plasma dealing 70% bonus electric damage.",
        "effect": {"type": "instant_damage", "value": 0.70, "element": "electric"},
    },
    {
        "id": "electric_018", "name": "Short Circuit", "element": "electric",
        "description": "Reduce enemy DEF by 35% for 2 turns (armor shorted out).",
        "effect": {"type": "stat_debuff", "stat": "def", "value": 0.35, "turns": 2},
    },
    {
        "id": "electric_019", "name": "Magnetic Pulse", "element": "electric",
        "description": "Reduce incoming damage by 40% for 1 turn (magnetic deflection).",
        "effect": {"type": "damage_reduction", "value": 0.40, "turns": 1},
    },
    {
        "id": "electric_020", "name": "Surge Drain", "element": "electric",
        "description": "Deal 55% bonus electric damage and heal 60% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.55, "heal_pct": 0.60, "element": "electric"},
    },
    {
        "id": "electric_021", "name": "Ionic Boost", "element": "electric",
        "description": "Instantly gain +2 charge levels from ionic energy.",
        "effect": {"type": "charge_boost", "value": 2},
    },
    {
        "id": "electric_022", "name": "Thunder Clap", "element": "electric",
        "description": "Deafening clap reducing enemy ATK by 40% for 2 turns.",
        "effect": {"type": "stat_debuff", "stat": "atk", "value": 0.40, "turns": 2},
    },
    {
        "id": "electric_023", "name": "Capacitor Shield", "element": "electric",
        "description": "Shield absorbing 50% of max HP in damage for 1 turn.",
        "effect": {"type": "shield", "value": 0.50, "turns": 1},
    },
    {
        "id": "electric_024", "name": "Amp Up", "element": "electric",
        "description": "Boost ATK by 25% and DEF by 25% for 2 turns.",
        "effect": {"type": "stat_buff", "stat": "atk", "value": 0.25, "turns": 2,
                   "secondary": {"type": "stat_buff", "stat": "def", "value": 0.25, "turns": 2}},
    },
    {
        "id": "electric_025", "name": "Lightning Rod", "element": "electric",
        "description": "Reflect 50% of incoming damage as electric for 1 turn.",
        "effect": {"type": "reflect", "value": 0.50, "turns": 1, "element": "electric"},
    },

    # ════════════════════════════════════════════════════════════════════════
    # ICE  (25 skills — freeze, slow, brittle armor, glacial shields)
    # ════════════════════════════════════════════════════════════════════════
    {
        "id": "ice_001", "name": "Ice Shard", "element": "ice",
        "description": "Hurl a razor-sharp shard dealing 35% bonus ice damage.",
        "effect": {"type": "instant_damage", "value": 0.35, "element": "ice"},
    },
    {
        "id": "ice_002", "name": "Blizzard", "element": "ice",
        "description": "Raging blizzard dealing 60% bonus ice damage.",
        "effect": {"type": "instant_damage", "value": 0.60, "element": "ice"},
    },
    {
        "id": "ice_003", "name": "Frostbite", "element": "ice",
        "description": "Inflict frostbite dealing 9% ATK ice damage per turn for 3 turns.",
        "effect": {"type": "dot", "value": 0.09, "turns": 3, "element": "ice"},
    },
    {
        "id": "ice_004", "name": "Deep Freeze", "element": "ice",
        "description": "Freeze the enemy solid, stunning them for 1 turn.",
        "effect": {"type": "stun", "turns": 1},
    },
    {
        "id": "ice_005", "name": "Glacial Wall", "element": "ice",
        "description": "Raise a wall of ice absorbing 45% of max HP in damage for 2 turns.",
        "effect": {"type": "shield", "value": 0.45, "turns": 2},
    },
    {
        "id": "ice_006", "name": "Brittle Armor", "element": "ice",
        "description": "Freeze enemy armor, reducing their DEF by 35% for 3 turns.",
        "effect": {"type": "stat_debuff", "stat": "def", "value": 0.35, "turns": 3},
    },
    {
        "id": "ice_007", "name": "Permafrost", "element": "ice",
        "description": "Reduce incoming damage by 35% for 2 turns (frozen skin).",
        "effect": {"type": "damage_reduction", "value": 0.35, "turns": 2},
    },
    {
        "id": "ice_008", "name": "Cryo Boost", "element": "ice",
        "description": "Instantly gain +2 charge levels from cryo energy.",
        "effect": {"type": "charge_boost", "value": 2},
    },
    {
        "id": "ice_009", "name": "Frozen Drain", "element": "ice",
        "description": "Deal 40% bonus ice damage and heal 45% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.40, "heal_pct": 0.45, "element": "ice"},
    },
    {
        "id": "ice_010", "name": "Sleet Storm", "element": "ice",
        "description": "Reduce enemy ATK by 30% for 3 turns (slowed by cold).",
        "effect": {"type": "stat_debuff", "stat": "atk", "value": 0.30, "turns": 3},
    },
    {
        "id": "ice_011", "name": "Cryo Reflect", "element": "ice",
        "description": "Reflect 35% of incoming damage as ice for 2 turns.",
        "effect": {"type": "reflect", "value": 0.35, "turns": 2, "element": "ice"},
    },
    {
        "id": "ice_012", "name": "Frost Mend", "element": "ice",
        "description": "Crystalline healing restoring 16% of max HP.",
        "effect": {"type": "heal", "value": 0.16},
    },
    {
        "id": "ice_013", "name": "Absolute Zero", "element": "ice",
        "description": "Devastating cold dealing 70% bonus ice damage.",
        "effect": {"type": "instant_damage", "value": 0.70, "element": "ice"},
    },
    {
        "id": "ice_014", "name": "Icicle Barrage", "element": "ice",
        "description": "Barrage of icicles dealing 11% ATK ice damage per turn for 4 turns.",
        "effect": {"type": "dot", "value": 0.11, "turns": 4, "element": "ice"},
    },
    {
        "id": "ice_015", "name": "Thaw", "element": "ice",
        "description": "Melt away all negative effects on yourself.",
        "effect": {"type": "cleanse"},
    },
    {
        "id": "ice_016", "name": "Frost Armor", "element": "ice",
        "description": "Boost DEF by 40% for 3 turns (encased in ice).",
        "effect": {"type": "stat_buff", "stat": "def", "value": 0.40, "turns": 3},
    },
    {
        "id": "ice_017", "name": "Avalanche", "element": "ice",
        "description": "Deal 50% bonus ice damage and reduce enemy DEF by 20% for 2 turns.",
        "effect": {"type": "instant_damage", "value": 0.50, "element": "ice",
                   "secondary": {"type": "stat_debuff", "stat": "def", "value": 0.20, "turns": 2}},
    },
    {
        "id": "ice_018", "name": "Chill Aura", "element": "ice",
        "description": "Reduce enemy ATK by 40% for 2 turns (numbed by cold).",
        "effect": {"type": "stat_debuff", "stat": "atk", "value": 0.40, "turns": 2},
    },
    {
        "id": "ice_019", "name": "Ice Fortress", "element": "ice",
        "description": "Shield absorbing 60% of max HP in damage for 1 turn.",
        "effect": {"type": "shield", "value": 0.60, "turns": 1},
    },
    {
        "id": "ice_020", "name": "Glacial Drain", "element": "ice",
        "description": "Deal 55% bonus ice damage and heal 65% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.55, "heal_pct": 0.65, "element": "ice"},
    },
    {
        "id": "ice_021", "name": "Snowstorm", "element": "ice",
        "description": "Reduce incoming damage by 45% for 1 turn (blinded by snow).",
        "effect": {"type": "damage_reduction", "value": 0.45, "turns": 1},
    },
    {
        "id": "ice_022", "name": "Frozen Spike", "element": "ice",
        "description": "Boost ATK by 40% for 2 turns (sharpened by cold).",
        "effect": {"type": "stat_buff", "stat": "atk", "value": 0.40, "turns": 2},
    },
    {
        "id": "ice_023", "name": "Polar Vortex", "element": "ice",
        "description": "Relentless cold dealing 14% ATK ice damage per turn for 3 turns.",
        "effect": {"type": "dot", "value": 0.14, "turns": 3, "element": "ice"},
    },
    {
        "id": "ice_024", "name": "Mirror Ice", "element": "ice",
        "description": "Reflect 50% of incoming damage as ice for 1 turn.",
        "effect": {"type": "reflect", "value": 0.50, "turns": 1, "element": "ice"},
    },
    {
        "id": "ice_025", "name": "Cryo Heal", "element": "ice",
        "description": "Restore 26% of max HP from cryo regeneration.",
        "effect": {"type": "heal", "value": 0.26},
    },

    # ════════════════════════════════════════════════════════════════════════
    # PLANT  (25 skills — vines, spores, regeneration, nature's wrath)
    # ════════════════════════════════════════════════════════════════════════
    {
        "id": "plant_001", "name": "Vine Whip", "element": "plant",
        "description": "Lash with thorny vines dealing 35% bonus plant damage.",
        "effect": {"type": "instant_damage", "value": 0.35, "element": "plant"},
    },
    {
        "id": "plant_002", "name": "Spore Cloud", "element": "plant",
        "description": "Release toxic spores dealing 9% ATK plant damage per turn for 3 turns.",
        "effect": {"type": "dot", "value": 0.09, "turns": 3, "element": "plant"},
    },
    {
        "id": "plant_003", "name": "Photosynthesis", "element": "plant",
        "description": "Absorb sunlight, restoring 20% of max HP.",
        "effect": {"type": "heal", "value": 0.20},
    },
    {
        "id": "plant_004", "name": "Thorn Barrier", "element": "plant",
        "description": "Thorny barrier absorbing 40% of max HP in damage for 2 turns.",
        "effect": {"type": "shield", "value": 0.40, "turns": 2},
    },
    {
        "id": "plant_005", "name": "Entangle", "element": "plant",
        "description": "Wrap the enemy in vines, stunning them for 1 turn.",
        "effect": {"type": "stun", "turns": 1},
    },
    {
        "id": "plant_006", "name": "Overgrowth", "element": "plant",
        "description": "Explosive growth dealing 60% bonus plant damage.",
        "effect": {"type": "instant_damage", "value": 0.60, "element": "plant"},
    },
    {
        "id": "plant_007", "name": "Root Drain", "element": "plant",
        "description": "Deal 40% bonus plant damage and heal 50% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.40, "heal_pct": 0.50, "element": "plant"},
    },
    {
        "id": "plant_008", "name": "Bark Skin", "element": "plant",
        "description": "Harden your skin like bark, reducing incoming damage by 35% for 2 turns.",
        "effect": {"type": "damage_reduction", "value": 0.35, "turns": 2},
    },
    {
        "id": "plant_009", "name": "Wilt", "element": "plant",
        "description": "Drain enemy vitality, reducing their ATK by 30% for 3 turns.",
        "effect": {"type": "stat_debuff", "stat": "atk", "value": 0.30, "turns": 3},
    },
    {
        "id": "plant_010", "name": "Verdant Boost", "element": "plant",
        "description": "Instantly gain +2 charge levels from nature's energy.",
        "effect": {"type": "charge_boost", "value": 2},
    },
    {
        "id": "plant_011", "name": "Thorn Reflect", "element": "plant",
        "description": "Reflect 35% of incoming damage as plant for 2 turns.",
        "effect": {"type": "reflect", "value": 0.35, "turns": 2, "element": "plant"},
    },
    {
        "id": "plant_012", "name": "Regrowth", "element": "plant",
        "description": "Regenerate 10% ATK plant healing per turn for 3 turns (heal DoT).",
        "effect": {"type": "dot", "value": -0.10, "turns": 3, "element": "plant"},
    },
    {
        "id": "plant_013", "name": "Noxious Spores", "element": "plant",
        "description": "Reduce enemy DEF by 30% for 3 turns (corroded by spores).",
        "effect": {"type": "stat_debuff", "stat": "def", "value": 0.30, "turns": 3},
    },
    {
        "id": "plant_014", "name": "Nature's Wrath", "element": "plant",
        "description": "Unleash nature's fury dealing 70% bonus plant damage.",
        "effect": {"type": "instant_damage", "value": 0.70, "element": "plant"},
    },
    {
        "id": "plant_015", "name": "Purify", "element": "plant",
        "description": "Nature cleanses all negative effects from yourself.",
        "effect": {"type": "cleanse"},
    },
    {
        "id": "plant_016", "name": "Canopy Shield", "element": "plant",
        "description": "Dense canopy absorbing 55% of max HP in damage for 1 turn.",
        "effect": {"type": "shield", "value": 0.55, "turns": 1},
    },
    {
        "id": "plant_017", "name": "Bloom", "element": "plant",
        "description": "Boost ATK by 35% for 2 turns (blooming power).",
        "effect": {"type": "stat_buff", "stat": "atk", "value": 0.35, "turns": 2},
    },
    {
        "id": "plant_018", "name": "Ancient Grove", "element": "plant",
        "description": "Boost DEF by 40% for 3 turns (ancient tree resilience).",
        "effect": {"type": "stat_buff", "stat": "def", "value": 0.40, "turns": 3},
    },
    {
        "id": "plant_019", "name": "Poison Ivy", "element": "plant",
        "description": "Coat the enemy in poison ivy, dealing 13% ATK plant damage per turn for 4 turns.",
        "effect": {"type": "dot", "value": 0.13, "turns": 4, "element": "plant"},
    },
    {
        "id": "plant_020", "name": "Sap Drain", "element": "plant",
        "description": "Deal 55% bonus plant damage and heal 65% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.55, "heal_pct": 0.65, "element": "plant"},
    },
    {
        "id": "plant_021", "name": "Leaf Storm", "element": "plant",
        "description": "Reduce incoming damage by 40% for 1 turn (deflected by leaves).",
        "effect": {"type": "damage_reduction", "value": 0.40, "turns": 1},
    },
    {
        "id": "plant_022", "name": "Seed Bomb", "element": "plant",
        "description": "Deal 45% bonus plant damage and apply 7% ATK plant DoT for 2 turns.",
        "effect": {"type": "instant_damage", "value": 0.45, "element": "plant",
                   "secondary": {"type": "dot", "value": 0.07, "turns": 2, "element": "plant"}},
    },
    {
        "id": "plant_023", "name": "Thorned Reflect", "element": "plant",
        "description": "Reflect 50% of incoming damage as plant for 1 turn.",
        "effect": {"type": "reflect", "value": 0.50, "turns": 1, "element": "plant"},
    },
    {
        "id": "plant_024", "name": "Verdant Heal", "element": "plant",
        "description": "Restore 28% of max HP from verdant energy.",
        "effect": {"type": "heal", "value": 0.28},
    },
    {
        "id": "plant_025", "name": "Mycelium Network", "element": "plant",
        "description": "Reduce enemy ATK by 40% for 2 turns (sapped by fungal network).",
        "effect": {"type": "stat_debuff", "stat": "atk", "value": 0.40, "turns": 2},
    },

    # ════════════════════════════════════════════════════════════════════════
    # ROCK  (25 skills — earth shatter, stone armor, seismic tremors)
    # ════════════════════════════════════════════════════════════════════════
    {
        "id": "rock_001", "name": "Boulder Toss", "element": "rock",
        "description": "Hurl a massive boulder dealing 40% bonus rock damage.",
        "effect": {"type": "instant_damage", "value": 0.40, "element": "rock"},
    },
    {
        "id": "rock_002", "name": "Earthquake", "element": "rock",
        "description": "Seismic tremor dealing 65% bonus rock damage.",
        "effect": {"type": "instant_damage", "value": 0.65, "element": "rock"},
    },
    {
        "id": "rock_003", "name": "Rockslide", "element": "rock",
        "description": "Continuous rockslide dealing 10% ATK rock damage per turn for 3 turns.",
        "effect": {"type": "dot", "value": 0.10, "turns": 3, "element": "rock"},
    },
    {
        "id": "rock_004", "name": "Stone Skin", "element": "rock",
        "description": "Harden your skin to stone, reducing incoming damage by 40% for 2 turns.",
        "effect": {"type": "damage_reduction", "value": 0.40, "turns": 2},
    },
    {
        "id": "rock_005", "name": "Granite Shield", "element": "rock",
        "description": "Granite barrier absorbing 50% of max HP in damage for 2 turns.",
        "effect": {"type": "shield", "value": 0.50, "turns": 2},
    },
    {
        "id": "rock_006", "name": "Tremor", "element": "rock",
        "description": "Knock the enemy off balance, stunning them for 1 turn.",
        "effect": {"type": "stun", "turns": 1},
    },
    {
        "id": "rock_007", "name": "Erode Armor", "element": "rock",
        "description": "Grind down enemy DEF by 35% for 3 turns.",
        "effect": {"type": "stat_debuff", "stat": "def", "value": 0.35, "turns": 3},
    },
    {
        "id": "rock_008", "name": "Tectonic Boost", "element": "rock",
        "description": "Boost DEF by 45% for 3 turns (immovable as a mountain).",
        "effect": {"type": "stat_buff", "stat": "def", "value": 0.45, "turns": 3},
    },
    {
        "id": "rock_009", "name": "Seismic Drain", "element": "rock",
        "description": "Deal 40% bonus rock damage and heal 45% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.40, "heal_pct": 0.45, "element": "rock"},
    },
    {
        "id": "rock_010", "name": "Stone Reflect", "element": "rock",
        "description": "Reflect 35% of incoming damage as rock for 2 turns.",
        "effect": {"type": "reflect", "value": 0.35, "turns": 2, "element": "rock"},
    },
    {
        "id": "rock_011", "name": "Mineral Mend", "element": "rock",
        "description": "Absorb minerals from the earth, restoring 18% of max HP.",
        "effect": {"type": "heal", "value": 0.18},
    },
    {
        "id": "rock_012", "name": "Petrify", "element": "rock",
        "description": "Reduce enemy ATK by 30% for 3 turns (turned to stone).",
        "effect": {"type": "stat_debuff", "stat": "atk", "value": 0.30, "turns": 3},
    },
    {
        "id": "rock_013", "name": "Tectonic Charge", "element": "rock",
        "description": "Instantly gain +2 charge levels from tectonic energy.",
        "effect": {"type": "charge_boost", "value": 2},
    },
    {
        "id": "rock_014", "name": "Gravel Storm", "element": "rock",
        "description": "Reduce incoming damage by 35% for 2 turns (gravel deflects blows).",
        "effect": {"type": "damage_reduction", "value": 0.35, "turns": 2},
    },
    {
        "id": "rock_015", "name": "Purge Dust", "element": "rock",
        "description": "Shake off all negative effects like dust from stone.",
        "effect": {"type": "cleanse"},
    },
    {
        "id": "rock_016", "name": "Magma Fist", "element": "rock",
        "description": "Boost ATK by 40% for 2 turns (fists of molten rock).",
        "effect": {"type": "stat_buff", "stat": "atk", "value": 0.40, "turns": 2},
    },
    {
        "id": "rock_017", "name": "Stalactite Rain", "element": "rock",
        "description": "Falling stalactites dealing 12% ATK rock damage per turn for 4 turns.",
        "effect": {"type": "dot", "value": 0.12, "turns": 4, "element": "rock"},
    },
    {
        "id": "rock_018", "name": "Obsidian Blade", "element": "rock",
        "description": "Razor-sharp obsidian dealing 55% bonus rock damage.",
        "effect": {"type": "instant_damage", "value": 0.55, "element": "rock"},
    },
    {
        "id": "rock_019", "name": "Bedrock Fortress", "element": "rock",
        "description": "Shield absorbing 60% of max HP in damage for 1 turn.",
        "effect": {"type": "shield", "value": 0.60, "turns": 1},
    },
    {
        "id": "rock_020", "name": "Quake Drain", "element": "rock",
        "description": "Deal 55% bonus rock damage and heal 65% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.55, "heal_pct": 0.65, "element": "rock"},
    },
    {
        "id": "rock_021", "name": "Shatter", "element": "rock",
        "description": "Deal 45% bonus rock damage and reduce enemy DEF by 25% for 2 turns.",
        "effect": {"type": "instant_damage", "value": 0.45, "element": "rock",
                   "secondary": {"type": "stat_debuff", "stat": "def", "value": 0.25, "turns": 2}},
    },
    {
        "id": "rock_022", "name": "Landslide", "element": "rock",
        "description": "Reduce enemy ATK by 40% for 2 turns (buried under rubble).",
        "effect": {"type": "stat_debuff", "stat": "atk", "value": 0.40, "turns": 2},
    },
    {
        "id": "rock_023", "name": "Crystal Reflect", "element": "rock",
        "description": "Reflect 50% of incoming damage as rock for 1 turn.",
        "effect": {"type": "reflect", "value": 0.50, "turns": 1, "element": "rock"},
    },
    {
        "id": "rock_024", "name": "Geode Heal", "element": "rock",
        "description": "Crack open a healing geode, restoring 26% of max HP.",
        "effect": {"type": "heal", "value": 0.26},
    },
    {
        "id": "rock_025", "name": "Mountain Stance", "element": "rock",
        "description": "Reduce incoming damage by 50% for 1 turn (immovable as a mountain).",
        "effect": {"type": "damage_reduction", "value": 0.50, "turns": 1},
    },

    # ════════════════════════════════════════════════════════════════════════
    # AIR  (25 skills — wind slashes, evasion, gust debuffs, cyclones)
    # ════════════════════════════════════════════════════════════════════════
    {
        "id": "air_001", "name": "Wind Slash", "element": "air",
        "description": "A razor wind slash dealing 35% bonus air damage.",
        "effect": {"type": "instant_damage", "value": 0.35, "element": "air"},
    },
    {
        "id": "air_002", "name": "Cyclone", "element": "air",
        "description": "Spinning cyclone dealing 60% bonus air damage.",
        "effect": {"type": "instant_damage", "value": 0.60, "element": "air"},
    },
    {
        "id": "air_003", "name": "Gust Barrage", "element": "air",
        "description": "Relentless gusts dealing 9% ATK air damage per turn for 3 turns.",
        "effect": {"type": "dot", "value": 0.09, "turns": 3, "element": "air"},
    },
    {
        "id": "air_004", "name": "Updraft", "element": "air",
        "description": "Instantly gain +3 charge levels riding an updraft.",
        "effect": {"type": "charge_boost", "value": 3},
    },
    {
        "id": "air_005", "name": "Wind Wall", "element": "air",
        "description": "Barrier of compressed air absorbing 40% of max HP in damage for 2 turns.",
        "effect": {"type": "shield", "value": 0.40, "turns": 2},
    },
    {
        "id": "air_006", "name": "Evasive Gust", "element": "air",
        "description": "Reduce incoming damage by 40% for 2 turns (dodge with wind).",
        "effect": {"type": "damage_reduction", "value": 0.40, "turns": 2},
    },
    {
        "id": "air_007", "name": "Tailwind", "element": "air",
        "description": "Boost ATK by 35% for 2 turns (wind at your back).",
        "effect": {"type": "stat_buff", "stat": "atk", "value": 0.35, "turns": 2},
    },
    {
        "id": "air_008", "name": "Headwind", "element": "air",
        "description": "Reduce enemy ATK by 30% for 3 turns (fighting against the wind).",
        "effect": {"type": "stat_debuff", "stat": "atk", "value": 0.30, "turns": 3},
    },
    {
        "id": "air_009", "name": "Vortex Drain", "element": "air",
        "description": "Deal 40% bonus air damage and heal 45% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.40, "heal_pct": 0.45, "element": "air"},
    },
    {
        "id": "air_010", "name": "Whirlwind", "element": "air",
        "description": "Spin the enemy in a whirlwind, stunning them for 1 turn.",
        "effect": {"type": "stun", "turns": 1},
    },
    {
        "id": "air_011", "name": "Clear Skies", "element": "air",
        "description": "Fresh air clears all negative effects from yourself.",
        "effect": {"type": "cleanse"},
    },
    {
        "id": "air_012", "name": "Gale Reflect", "element": "air",
        "description": "Reflect 35% of incoming damage as air for 2 turns.",
        "effect": {"type": "reflect", "value": 0.35, "turns": 2, "element": "air"},
    },
    {
        "id": "air_013", "name": "Breath of Life", "element": "air",
        "description": "Breathe in healing air, restoring 18% of max HP.",
        "effect": {"type": "heal", "value": 0.18},
    },
    {
        "id": "air_014", "name": "Tornado", "element": "air",
        "description": "Devastating tornado dealing 70% bonus air damage.",
        "effect": {"type": "instant_damage", "value": 0.70, "element": "air"},
    },
    {
        "id": "air_015", "name": "Shear Wind", "element": "air",
        "description": "Reduce enemy DEF by 35% for 3 turns (armor stripped by wind).",
        "effect": {"type": "stat_debuff", "stat": "def", "value": 0.35, "turns": 3},
    },
    {
        "id": "air_016", "name": "Jet Stream", "element": "air",
        "description": "Boost DEF by 35% for 3 turns (riding the jet stream).",
        "effect": {"type": "stat_buff", "stat": "def", "value": 0.35, "turns": 3},
    },
    {
        "id": "air_017", "name": "Tempest", "element": "air",
        "description": "Raging tempest dealing 11% ATK air damage per turn for 4 turns.",
        "effect": {"type": "dot", "value": 0.11, "turns": 4, "element": "air"},
    },
    {
        "id": "air_018", "name": "Vacuum Burst", "element": "air",
        "description": "Reduce incoming damage by 45% for 1 turn (vacuum absorbs impact).",
        "effect": {"type": "damage_reduction", "value": 0.45, "turns": 1},
    },
    {
        "id": "air_019", "name": "Gale Drain", "element": "air",
        "description": "Deal 55% bonus air damage and heal 65% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.55, "heal_pct": 0.65, "element": "air"},
    },
    {
        "id": "air_020", "name": "Pressure Wave", "element": "air",
        "description": "Deal 45% bonus air damage and reduce enemy ATK by 20% for 2 turns.",
        "effect": {"type": "instant_damage", "value": 0.45, "element": "air",
                   "secondary": {"type": "stat_debuff", "stat": "atk", "value": 0.20, "turns": 2}},
    },
    {
        "id": "air_021", "name": "Sonic Boom", "element": "air",
        "description": "Shield absorbing 55% of max HP in damage for 1 turn.",
        "effect": {"type": "shield", "value": 0.55, "turns": 1},
    },
    {
        "id": "air_022", "name": "Wind Reflect", "element": "air",
        "description": "Reflect 50% of incoming damage as air for 1 turn.",
        "effect": {"type": "reflect", "value": 0.50, "turns": 1, "element": "air"},
    },
    {
        "id": "air_023", "name": "Zephyr Heal", "element": "air",
        "description": "Gentle zephyr restoring 26% of max HP.",
        "effect": {"type": "heal", "value": 0.26},
    },
    {
        "id": "air_024", "name": "Boost Charge", "element": "air",
        "description": "Instantly gain +2 charge levels from wind energy.",
        "effect": {"type": "charge_boost", "value": 2},
    },
    {
        "id": "air_025", "name": "Maelstrom Aura", "element": "air",
        "description": "Boost ATK by 25% and DEF by 25% for 2 turns (eye of the storm).",
        "effect": {"type": "stat_buff", "stat": "atk", "value": 0.25, "turns": 2,
                   "secondary": {"type": "stat_buff", "stat": "def", "value": 0.25, "turns": 2}},
    },

    # ════════════════════════════════════════════════════════════════════════
    # MAGIC  (25 skills — arcane blasts, mana shields, spell curses)
    # ════════════════════════════════════════════════════════════════════════
    {
        "id": "magic_001", "name": "Arcane Bolt", "element": "magic",
        "description": "A focused arcane bolt dealing 35% bonus magic damage.",
        "effect": {"type": "instant_damage", "value": 0.35, "element": "magic"},
    },
    {
        "id": "magic_002", "name": "Mana Surge", "element": "magic",
        "description": "Overwhelming surge dealing 65% bonus magic damage.",
        "effect": {"type": "instant_damage", "value": 0.65, "element": "magic"},
    },
    {
        "id": "magic_003", "name": "Arcane Burn", "element": "magic",
        "description": "Arcane fire dealing 10% ATK magic damage per turn for 3 turns.",
        "effect": {"type": "dot", "value": 0.10, "turns": 3, "element": "magic"},
    },
    {
        "id": "magic_004", "name": "Mana Shield", "element": "magic",
        "description": "Mana barrier absorbing 45% of max HP in damage for 2 turns.",
        "effect": {"type": "shield", "value": 0.45, "turns": 2},
    },
    {
        "id": "magic_005", "name": "Hex", "element": "magic",
        "description": "Curse the enemy, reducing their ATK by 30% for 3 turns.",
        "effect": {"type": "stat_debuff", "stat": "atk", "value": 0.30, "turns": 3},
    },
    {
        "id": "magic_006", "name": "Weaken", "element": "magic",
        "description": "Weaken enemy armor, reducing their DEF by 30% for 3 turns.",
        "effect": {"type": "stat_debuff", "stat": "def", "value": 0.30, "turns": 3},
    },
    {
        "id": "magic_007", "name": "Arcane Boost", "element": "magic",
        "description": "Boost ATK by 40% for 2 turns (arcane empowerment).",
        "effect": {"type": "stat_buff", "stat": "atk", "value": 0.40, "turns": 2},
    },
    {
        "id": "magic_008", "name": "Spell Ward", "element": "magic",
        "description": "Reduce incoming damage by 35% for 2 turns (warded).",
        "effect": {"type": "damage_reduction", "value": 0.35, "turns": 2},
    },
    {
        "id": "magic_009", "name": "Drain Magic", "element": "magic",
        "description": "Deal 40% bonus magic damage and heal 50% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.40, "heal_pct": 0.50, "element": "magic"},
    },
    {
        "id": "magic_010", "name": "Time Stop", "element": "magic",
        "description": "Freeze time around the enemy, stunning them for 1 turn.",
        "effect": {"type": "stun", "turns": 1},
    },
    {
        "id": "magic_011", "name": "Dispel", "element": "magic",
        "description": "Dispel all negative effects from yourself.",
        "effect": {"type": "cleanse"},
    },
    {
        "id": "magic_012", "name": "Arcane Reflect", "element": "magic",
        "description": "Reflect 35% of incoming damage as magic for 2 turns.",
        "effect": {"type": "reflect", "value": 0.35, "turns": 2, "element": "magic"},
    },
    {
        "id": "magic_013", "name": "Mana Infusion", "element": "magic",
        "description": "Infuse yourself with mana, restoring 20% of max HP.",
        "effect": {"type": "heal", "value": 0.20},
    },
    {
        "id": "magic_014", "name": "Arcane Charge", "element": "magic",
        "description": "Instantly gain +2 charge levels from arcane energy.",
        "effect": {"type": "charge_boost", "value": 2},
    },
    {
        "id": "magic_015", "name": "Spell Barrage", "element": "magic",
        "description": "Rapid spells dealing 12% ATK magic damage per turn for 4 turns.",
        "effect": {"type": "dot", "value": 0.12, "turns": 4, "element": "magic"},
    },
    {
        "id": "magic_016", "name": "Arcane Fortress", "element": "magic",
        "description": "Boost DEF by 40% for 3 turns (arcane fortification).",
        "effect": {"type": "stat_buff", "stat": "def", "value": 0.40, "turns": 3},
    },
    {
        "id": "magic_017", "name": "Void Blast", "element": "magic",
        "description": "Void energy dealing 70% bonus magic damage.",
        "effect": {"type": "instant_damage", "value": 0.70, "element": "magic"},
    },
    {
        "id": "magic_018", "name": "Mana Siphon", "element": "magic",
        "description": "Deal 55% bonus magic damage and heal 65% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.55, "heal_pct": 0.65, "element": "magic"},
    },
    {
        "id": "magic_019", "name": "Arcane Veil", "element": "magic",
        "description": "Reduce incoming damage by 45% for 1 turn (arcane veil).",
        "effect": {"type": "damage_reduction", "value": 0.45, "turns": 1},
    },
    {
        "id": "magic_020", "name": "Spell Mirror", "element": "magic",
        "description": "Reflect 50% of incoming damage as magic for 1 turn.",
        "effect": {"type": "reflect", "value": 0.50, "turns": 1, "element": "magic"},
    },
    {
        "id": "magic_021", "name": "Arcane Torrent", "element": "magic",
        "description": "Shield absorbing 55% of max HP in damage for 1 turn.",
        "effect": {"type": "shield", "value": 0.55, "turns": 1},
    },
    {
        "id": "magic_022", "name": "Curse of Weakness", "element": "magic",
        "description": "Reduce enemy ATK by 40% for 2 turns (cursed).",
        "effect": {"type": "stat_debuff", "stat": "atk", "value": 0.40, "turns": 2},
    },
    {
        "id": "magic_023", "name": "Arcane Surge", "element": "magic",
        "description": "Deal 45% bonus magic damage and apply 8% ATK magic DoT for 2 turns.",
        "effect": {"type": "instant_damage", "value": 0.45, "element": "magic",
                   "secondary": {"type": "dot", "value": 0.08, "turns": 2, "element": "magic"}},
    },
    {
        "id": "magic_024", "name": "Mana Restore", "element": "magic",
        "description": "Restore 28% of max HP from mana regeneration.",
        "effect": {"type": "heal", "value": 0.28},
    },
    {
        "id": "magic_025", "name": "Arcane Empowerment", "element": "magic",
        "description": "Boost ATK by 25% and DEF by 25% for 2 turns.",
        "effect": {"type": "stat_buff", "stat": "atk", "value": 0.25, "turns": 2,
                   "secondary": {"type": "stat_buff", "stat": "def", "value": 0.25, "turns": 2}},
    },

    # ════════════════════════════════════════════════════════════════════════
    # HOLY  (25 skills — divine light, sacred shields, smite, purification)
    # ════════════════════════════════════════════════════════════════════════
    {
        "id": "holy_001", "name": "Smite", "element": "holy",
        "description": "Divine smite dealing 40% bonus holy damage.",
        "effect": {"type": "instant_damage", "value": 0.40, "element": "holy"},
    },
    {
        "id": "holy_002", "name": "Holy Nova", "element": "holy",
        "description": "Radiant explosion dealing 65% bonus holy damage.",
        "effect": {"type": "instant_damage", "value": 0.65, "element": "holy"},
    },
    {
        "id": "holy_003", "name": "Sacred Flame", "element": "holy",
        "description": "Holy fire dealing 10% ATK holy damage per turn for 3 turns.",
        "effect": {"type": "dot", "value": 0.10, "turns": 3, "element": "holy"},
    },
    {
        "id": "holy_004", "name": "Divine Shield", "element": "holy",
        "description": "Sacred barrier absorbing 50% of max HP in damage for 2 turns.",
        "effect": {"type": "shield", "value": 0.50, "turns": 2},
    },
    {
        "id": "holy_005", "name": "Lay on Hands", "element": "holy",
        "description": "Divine healing restoring 25% of max HP.",
        "effect": {"type": "heal", "value": 0.25},
    },
    {
        "id": "holy_006", "name": "Consecrate", "element": "holy",
        "description": "Reduce incoming damage by 40% for 2 turns (consecrated ground).",
        "effect": {"type": "damage_reduction", "value": 0.40, "turns": 2},
    },
    {
        "id": "holy_007", "name": "Judgment", "element": "holy",
        "description": "Reduce enemy ATK by 35% for 3 turns (judged unworthy).",
        "effect": {"type": "stat_debuff", "stat": "atk", "value": 0.35, "turns": 3},
    },
    {
        "id": "holy_008", "name": "Exorcise", "element": "holy",
        "description": "Stun the enemy for 1 turn (banished by holy light).",
        "effect": {"type": "stun", "turns": 1},
    },
    {
        "id": "holy_009", "name": "Purify", "element": "holy",
        "description": "Remove all negative effects with holy light.",
        "effect": {"type": "cleanse"},
    },
    {
        "id": "holy_010", "name": "Holy Drain", "element": "holy",
        "description": "Deal 40% bonus holy damage and heal 55% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.40, "heal_pct": 0.55, "element": "holy"},
    },
    {
        "id": "holy_011", "name": "Radiant Reflect", "element": "holy",
        "description": "Reflect 35% of incoming damage as holy for 2 turns.",
        "effect": {"type": "reflect", "value": 0.35, "turns": 2, "element": "holy"},
    },
    {
        "id": "holy_012", "name": "Divine Charge", "element": "holy",
        "description": "Instantly gain +2 charge levels from divine energy.",
        "effect": {"type": "charge_boost", "value": 2},
    },
    {
        "id": "holy_013", "name": "Blessed Armor", "element": "holy",
        "description": "Boost DEF by 45% for 3 turns (blessed by the divine).",
        "effect": {"type": "stat_buff", "stat": "def", "value": 0.45, "turns": 3},
    },
    {
        "id": "holy_014", "name": "Wrath of Heaven", "element": "holy",
        "description": "Heavenly wrath dealing 70% bonus holy damage.",
        "effect": {"type": "instant_damage", "value": 0.70, "element": "holy"},
    },
    {
        "id": "holy_015", "name": "Searing Light", "element": "holy",
        "description": "Blinding light dealing 12% ATK holy damage per turn for 4 turns.",
        "effect": {"type": "dot", "value": 0.12, "turns": 4, "element": "holy"},
    },
    {
        "id": "holy_016", "name": "Holy Fervor", "element": "holy",
        "description": "Boost ATK by 40% for 2 turns (holy fervor).",
        "effect": {"type": "stat_buff", "stat": "atk", "value": 0.40, "turns": 2},
    },
    {
        "id": "holy_017", "name": "Reduce Armor", "element": "holy",
        "description": "Reduce enemy DEF by 35% for 3 turns (armor weakened by holy light).",
        "effect": {"type": "stat_debuff", "stat": "def", "value": 0.35, "turns": 3},
    },
    {
        "id": "holy_018", "name": "Aegis", "element": "holy",
        "description": "Reduce incoming damage by 50% for 1 turn (divine aegis).",
        "effect": {"type": "damage_reduction", "value": 0.50, "turns": 1},
    },
    {
        "id": "holy_019", "name": "Holy Siphon", "element": "holy",
        "description": "Deal 55% bonus holy damage and heal 65% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.55, "heal_pct": 0.65, "element": "holy"},
    },
    {
        "id": "holy_020", "name": "Light Mirror", "element": "holy",
        "description": "Reflect 50% of incoming damage as holy for 1 turn.",
        "effect": {"type": "reflect", "value": 0.50, "turns": 1, "element": "holy"},
    },
    {
        "id": "holy_021", "name": "Celestial Shield", "element": "holy",
        "description": "Shield absorbing 60% of max HP in damage for 1 turn.",
        "effect": {"type": "shield", "value": 0.60, "turns": 1},
    },
    {
        "id": "holy_022", "name": "Restoration", "element": "holy",
        "description": "Restore 30% of max HP through divine restoration.",
        "effect": {"type": "heal", "value": 0.30},
    },
    {
        "id": "holy_023", "name": "Holy Surge", "element": "holy",
        "description": "Deal 45% bonus holy damage and apply 8% ATK holy DoT for 2 turns.",
        "effect": {"type": "instant_damage", "value": 0.45, "element": "holy",
                   "secondary": {"type": "dot", "value": 0.08, "turns": 2, "element": "holy"}},
    },
    {
        "id": "holy_024", "name": "Sanctify", "element": "holy",
        "description": "Boost ATK by 25% and DEF by 25% for 2 turns (sanctified).",
        "effect": {"type": "stat_buff", "stat": "atk", "value": 0.25, "turns": 2,
                   "secondary": {"type": "stat_buff", "stat": "def", "value": 0.25, "turns": 2}},
    },
    {
        "id": "holy_025", "name": "Crusader Strike", "element": "holy",
        "description": "Reduce enemy ATK by 40% for 2 turns (crushed by holy might).",
        "effect": {"type": "stat_debuff", "stat": "atk", "value": 0.40, "turns": 2},
    },

    # ════════════════════════════════════════════════════════════════════════
    # NECRO  (25 skills — death drain, bone shields, curses, undead power)
    # ════════════════════════════════════════════════════════════════════════
    {
        "id": "necro_001", "name": "Death Touch", "element": "necro",
        "description": "A touch of death dealing 35% bonus necro damage.",
        "effect": {"type": "instant_damage", "value": 0.35, "element": "necro"},
    },
    {
        "id": "necro_002", "name": "Soul Rend", "element": "necro",
        "description": "Tear the enemy's soul dealing 60% bonus necro damage.",
        "effect": {"type": "instant_damage", "value": 0.60, "element": "necro"},
    },
    {
        "id": "necro_003", "name": "Wither", "element": "necro",
        "description": "Wither the enemy, dealing 10% ATK necro damage per turn for 3 turns.",
        "effect": {"type": "dot", "value": 0.10, "turns": 3, "element": "necro"},
    },
    {
        "id": "necro_004", "name": "Bone Shield", "element": "necro",
        "description": "Bone barrier absorbing 45% of max HP in damage for 2 turns.",
        "effect": {"type": "shield", "value": 0.45, "turns": 2},
    },
    {
        "id": "necro_005", "name": "Life Drain", "element": "necro",
        "description": "Deal 40% bonus necro damage and heal 55% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.40, "heal_pct": 0.55, "element": "necro"},
    },
    {
        "id": "necro_006", "name": "Curse of Decay", "element": "necro",
        "description": "Reduce enemy DEF by 35% for 3 turns (decaying armor).",
        "effect": {"type": "stat_debuff", "stat": "def", "value": 0.35, "turns": 3},
    },
    {
        "id": "necro_007", "name": "Death Grip", "element": "necro",
        "description": "Grip the enemy with death, stunning them for 1 turn.",
        "effect": {"type": "stun", "turns": 1},
    },
    {
        "id": "necro_008", "name": "Undying Will", "element": "necro",
        "description": "Reduce incoming damage by 35% for 2 turns (undead resilience).",
        "effect": {"type": "damage_reduction", "value": 0.35, "turns": 2},
    },
    {
        "id": "necro_009", "name": "Dark Pact", "element": "necro",
        "description": "Boost ATK by 45% for 2 turns (pact with darkness).",
        "effect": {"type": "stat_buff", "stat": "atk", "value": 0.45, "turns": 2},
    },
    {
        "id": "necro_010", "name": "Necrotic Reflect", "element": "necro",
        "description": "Reflect 35% of incoming damage as necro for 2 turns.",
        "effect": {"type": "reflect", "value": 0.35, "turns": 2, "element": "necro"},
    },
    {
        "id": "necro_011", "name": "Soul Harvest", "element": "necro",
        "description": "Harvest souls, restoring 20% of max HP.",
        "effect": {"type": "heal", "value": 0.20},
    },
    {
        "id": "necro_012", "name": "Void Cleanse", "element": "necro",
        "description": "Void energy purges all negative effects.",
        "effect": {"type": "cleanse"},
    },
    {
        "id": "necro_013", "name": "Death Charge", "element": "necro",
        "description": "Instantly gain +2 charge levels from death energy.",
        "effect": {"type": "charge_boost", "value": 2},
    },
    {
        "id": "necro_014", "name": "Plague", "element": "necro",
        "description": "Inflict plague dealing 13% ATK necro damage per turn for 4 turns.",
        "effect": {"type": "dot", "value": 0.13, "turns": 4, "element": "necro"},
    },
    {
        "id": "necro_015", "name": "Lich Form", "element": "necro",
        "description": "Boost DEF by 40% for 3 turns (lich's undead form).",
        "effect": {"type": "stat_buff", "stat": "def", "value": 0.40, "turns": 3},
    },
    {
        "id": "necro_016", "name": "Enervate", "element": "necro",
        "description": "Reduce enemy ATK by 35% for 3 turns (drained of life force).",
        "effect": {"type": "stat_debuff", "stat": "atk", "value": 0.35, "turns": 3},
    },
    {
        "id": "necro_017", "name": "Death Coil", "element": "necro",
        "description": "Coil of death energy dealing 70% bonus necro damage.",
        "effect": {"type": "instant_damage", "value": 0.70, "element": "necro"},
    },
    {
        "id": "necro_018", "name": "Necrotic Siphon", "element": "necro",
        "description": "Deal 55% bonus necro damage and heal 65% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.55, "heal_pct": 0.65, "element": "necro"},
    },
    {
        "id": "necro_019", "name": "Shadow Veil", "element": "necro",
        "description": "Reduce incoming damage by 45% for 1 turn (shadow veil).",
        "effect": {"type": "damage_reduction", "value": 0.45, "turns": 1},
    },
    {
        "id": "necro_020", "name": "Death Mirror", "element": "necro",
        "description": "Reflect 50% of incoming damage as necro for 1 turn.",
        "effect": {"type": "reflect", "value": 0.50, "turns": 1, "element": "necro"},
    },
    {
        "id": "necro_021", "name": "Crypt Shield", "element": "necro",
        "description": "Shield absorbing 55% of max HP in damage for 1 turn.",
        "effect": {"type": "shield", "value": 0.55, "turns": 1},
    },
    {
        "id": "necro_022", "name": "Grave Mend", "element": "necro",
        "description": "Restore 28% of max HP from grave energy.",
        "effect": {"type": "heal", "value": 0.28},
    },
    {
        "id": "necro_023", "name": "Bone Surge", "element": "necro",
        "description": "Deal 45% bonus necro damage and apply 8% ATK necro DoT for 2 turns.",
        "effect": {"type": "instant_damage", "value": 0.45, "element": "necro",
                   "secondary": {"type": "dot", "value": 0.08, "turns": 2, "element": "necro"}},
    },
    {
        "id": "necro_024", "name": "Undead Might", "element": "necro",
        "description": "Boost ATK by 25% and DEF by 25% for 2 turns (undead power).",
        "effect": {"type": "stat_buff", "stat": "atk", "value": 0.25, "turns": 2,
                   "secondary": {"type": "stat_buff", "stat": "def", "value": 0.25, "turns": 2}},
    },
    {
        "id": "necro_025", "name": "Corpse Explosion", "element": "necro",
        "description": "Reduce enemy ATK by 40% for 2 turns (horrified by explosion).",
        "effect": {"type": "stat_debuff", "stat": "atk", "value": 0.40, "turns": 2},
    },

    # ════════════════════════════════════════════════════════════════════════
    # PSYCHIC  (25 skills — mind blasts, confusion, mental shields, foresight)
    # ════════════════════════════════════════════════════════════════════════
    {
        "id": "psychic_001", "name": "Mind Blast", "element": "psychic",
        "description": "A focused mind blast dealing 35% bonus psychic damage.",
        "effect": {"type": "instant_damage", "value": 0.35, "element": "psychic"},
    },
    {
        "id": "psychic_002", "name": "Psychic Crush", "element": "psychic",
        "description": "Crush the enemy's mind dealing 60% bonus psychic damage.",
        "effect": {"type": "instant_damage", "value": 0.60, "element": "psychic"},
    },
    {
        "id": "psychic_003", "name": "Mental Torment", "element": "psychic",
        "description": "Torment the enemy's mind, dealing 10% ATK psychic damage per turn for 3 turns.",
        "effect": {"type": "dot", "value": 0.10, "turns": 3, "element": "psychic"},
    },
    {
        "id": "psychic_004", "name": "Confusion", "element": "psychic",
        "description": "Confuse the enemy, reducing their ATK by 35% for 3 turns.",
        "effect": {"type": "stat_debuff", "stat": "atk", "value": 0.35, "turns": 3},
    },
    {
        "id": "psychic_005", "name": "Psychic Shield", "element": "psychic",
        "description": "Mental barrier absorbing 45% of max HP in damage for 2 turns.",
        "effect": {"type": "shield", "value": 0.45, "turns": 2},
    },
    {
        "id": "psychic_006", "name": "Dominate", "element": "psychic",
        "description": "Dominate the enemy's mind, stunning them for 1 turn.",
        "effect": {"type": "stun", "turns": 1},
    },
    {
        "id": "psychic_007", "name": "Foresight", "element": "psychic",
        "description": "Reduce incoming damage by 40% for 2 turns (predicted the attack).",
        "effect": {"type": "damage_reduction", "value": 0.40, "turns": 2},
    },
    {
        "id": "psychic_008", "name": "Telekinetic Boost", "element": "psychic",
        "description": "Boost ATK by 40% for 2 turns (telekinetic power).",
        "effect": {"type": "stat_buff", "stat": "atk", "value": 0.40, "turns": 2},
    },
    {
        "id": "psychic_009", "name": "Mind Drain", "element": "psychic",
        "description": "Deal 40% bonus psychic damage and heal 50% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.40, "heal_pct": 0.50, "element": "psychic"},
    },
    {
        "id": "psychic_010", "name": "Mental Clarity", "element": "psychic",
        "description": "Clear your mind of all negative effects.",
        "effect": {"type": "cleanse"},
    },
    {
        "id": "psychic_011", "name": "Psi Reflect", "element": "psychic",
        "description": "Reflect 35% of incoming damage as psychic for 2 turns.",
        "effect": {"type": "reflect", "value": 0.35, "turns": 2, "element": "psychic"},
    },
    {
        "id": "psychic_012", "name": "Meditate", "element": "psychic",
        "description": "Deep meditation restoring 20% of max HP.",
        "effect": {"type": "heal", "value": 0.20},
    },
    {
        "id": "psychic_013", "name": "Psi Charge", "element": "psychic",
        "description": "Instantly gain +2 charge levels from psychic energy.",
        "effect": {"type": "charge_boost", "value": 2},
    },
    {
        "id": "psychic_014", "name": "Psychic Storm", "element": "psychic",
        "description": "Mental storm dealing 70% bonus psychic damage.",
        "effect": {"type": "instant_damage", "value": 0.70, "element": "psychic"},
    },
    {
        "id": "psychic_015", "name": "Nightmare", "element": "psychic",
        "description": "Inflict nightmares dealing 12% ATK psychic damage per turn for 4 turns.",
        "effect": {"type": "dot", "value": 0.12, "turns": 4, "element": "psychic"},
    },
    {
        "id": "psychic_016", "name": "Iron Will", "element": "psychic",
        "description": "Boost DEF by 40% for 3 turns (iron will).",
        "effect": {"type": "stat_buff", "stat": "def", "value": 0.40, "turns": 3},
    },
    {
        "id": "psychic_017", "name": "Shatter Mind", "element": "psychic",
        "description": "Reduce enemy DEF by 35% for 3 turns (shattered concentration).",
        "effect": {"type": "stat_debuff", "stat": "def", "value": 0.35, "turns": 3},
    },
    {
        "id": "psychic_018", "name": "Psi Siphon", "element": "psychic",
        "description": "Deal 55% bonus psychic damage and heal 65% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.55, "heal_pct": 0.65, "element": "psychic"},
    },
    {
        "id": "psychic_019", "name": "Mind Fortress", "element": "psychic",
        "description": "Reduce incoming damage by 45% for 1 turn (mental fortress).",
        "effect": {"type": "damage_reduction", "value": 0.45, "turns": 1},
    },
    {
        "id": "psychic_020", "name": "Psi Mirror", "element": "psychic",
        "description": "Reflect 50% of incoming damage as psychic for 1 turn.",
        "effect": {"type": "reflect", "value": 0.50, "turns": 1, "element": "psychic"},
    },
    {
        "id": "psychic_021", "name": "Thought Barrier", "element": "psychic",
        "description": "Shield absorbing 55% of max HP in damage for 1 turn.",
        "effect": {"type": "shield", "value": 0.55, "turns": 1},
    },
    {
        "id": "psychic_022", "name": "Psi Restore", "element": "psychic",
        "description": "Restore 28% of max HP through psychic regeneration.",
        "effect": {"type": "heal", "value": 0.28},
    },
    {
        "id": "psychic_023", "name": "Psychic Surge", "element": "psychic",
        "description": "Deal 45% bonus psychic damage and apply 8% ATK psychic DoT for 2 turns.",
        "effect": {"type": "instant_damage", "value": 0.45, "element": "psychic",
                   "secondary": {"type": "dot", "value": 0.08, "turns": 2, "element": "psychic"}},
    },
    {
        "id": "psychic_024", "name": "Psi Empowerment", "element": "psychic",
        "description": "Boost ATK by 25% and DEF by 25% for 2 turns.",
        "effect": {"type": "stat_buff", "stat": "atk", "value": 0.25, "turns": 2,
                   "secondary": {"type": "stat_buff", "stat": "def", "value": 0.25, "turns": 2}},
    },
    {
        "id": "psychic_025", "name": "Psychic Crush", "element": "psychic",
        "description": "Reduce enemy ATK by 40% for 2 turns (crushed by psychic force).",
        "effect": {"type": "stat_debuff", "stat": "atk", "value": 0.40, "turns": 2},
    },

    # ════════════════════════════════════════════════════════════════════════
    # FIGHTING  (25 skills — martial arts, combo strikes, iron body)
    # ════════════════════════════════════════════════════════════════════════
    {
        "id": "fighting_001", "name": "Jab", "element": "fighting",
        "description": "A quick jab dealing 30% bonus fighting damage.",
        "effect": {"type": "instant_damage", "value": 0.30, "element": "fighting"},
    },
    {
        "id": "fighting_002", "name": "Haymaker", "element": "fighting",
        "description": "A massive haymaker dealing 65% bonus fighting damage.",
        "effect": {"type": "instant_damage", "value": 0.65, "element": "fighting"},
    },
    {
        "id": "fighting_003", "name": "Combo Strike", "element": "fighting",
        "description": "Rapid combo dealing 9% ATK fighting damage per turn for 3 turns.",
        "effect": {"type": "dot", "value": 0.09, "turns": 3, "element": "fighting"},
    },
    {
        "id": "fighting_004", "name": "Iron Body", "element": "fighting",
        "description": "Harden your body, reducing incoming damage by 40% for 2 turns.",
        "effect": {"type": "damage_reduction", "value": 0.40, "turns": 2},
    },
    {
        "id": "fighting_005", "name": "Guard Stance", "element": "fighting",
        "description": "Fighting guard absorbing 45% of max HP in damage for 2 turns.",
        "effect": {"type": "shield", "value": 0.45, "turns": 2},
    },
    {
        "id": "fighting_006", "name": "Knockout Blow", "element": "fighting",
        "description": "Knock the enemy out, stunning them for 1 turn.",
        "effect": {"type": "stun", "turns": 1},
    },
    {
        "id": "fighting_007", "name": "Adrenaline", "element": "fighting",
        "description": "Boost ATK by 45% for 2 turns (adrenaline surge).",
        "effect": {"type": "stat_buff", "stat": "atk", "value": 0.45, "turns": 2},
    },
    {
        "id": "fighting_008", "name": "Disarm", "element": "fighting",
        "description": "Disarm the enemy, reducing their ATK by 35% for 3 turns.",
        "effect": {"type": "stat_debuff", "stat": "atk", "value": 0.35, "turns": 3},
    },
    {
        "id": "fighting_009", "name": "Drain Punch", "element": "fighting",
        "description": "Deal 40% bonus fighting damage and heal 50% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.40, "heal_pct": 0.50, "element": "fighting"},
    },
    {
        "id": "fighting_010", "name": "Counter Stance", "element": "fighting",
        "description": "Reflect 35% of incoming damage as fighting for 2 turns.",
        "effect": {"type": "reflect", "value": 0.35, "turns": 2, "element": "fighting"},
    },
    {
        "id": "fighting_011", "name": "Second Wind", "element": "fighting",
        "description": "Catch your breath, restoring 18% of max HP.",
        "effect": {"type": "heal", "value": 0.18},
    },
    {
        "id": "fighting_012", "name": "Focus", "element": "fighting",
        "description": "Clear your mind of all negative effects.",
        "effect": {"type": "cleanse"},
    },
    {
        "id": "fighting_013", "name": "Battle Rush", "element": "fighting",
        "description": "Instantly gain +2 charge levels from battle rush.",
        "effect": {"type": "charge_boost", "value": 2},
    },
    {
        "id": "fighting_014", "name": "Armor Break", "element": "fighting",
        "description": "Reduce enemy DEF by 40% for 3 turns (armor broken).",
        "effect": {"type": "stat_debuff", "stat": "def", "value": 0.40, "turns": 3},
    },
    {
        "id": "fighting_015", "name": "Fortify Stance", "element": "fighting",
        "description": "Boost DEF by 40% for 3 turns (fortified stance).",
        "effect": {"type": "stat_buff", "stat": "def", "value": 0.40, "turns": 3},
    },
    {
        "id": "fighting_016", "name": "Flurry", "element": "fighting",
        "description": "Flurry of blows dealing 12% ATK fighting damage per turn for 4 turns.",
        "effect": {"type": "dot", "value": 0.12, "turns": 4, "element": "fighting"},
    },
    {
        "id": "fighting_017", "name": "Berserker Rage", "element": "fighting",
        "description": "Unleash berserker rage dealing 70% bonus fighting damage.",
        "effect": {"type": "instant_damage", "value": 0.70, "element": "fighting"},
    },
    {
        "id": "fighting_018", "name": "Turtle Shell", "element": "fighting",
        "description": "Reduce incoming damage by 50% for 1 turn (turtle shell defense).",
        "effect": {"type": "damage_reduction", "value": 0.50, "turns": 1},
    },
    {
        "id": "fighting_019", "name": "Leech Punch", "element": "fighting",
        "description": "Deal 55% bonus fighting damage and heal 65% of damage dealt.",
        "effect": {"type": "lifesteal", "value": 0.55, "heal_pct": 0.65, "element": "fighting"},
    },
    {
        "id": "fighting_020", "name": "Parry Stance", "element": "fighting",
        "description": "Reflect 50% of incoming damage as fighting for 1 turn.",
        "effect": {"type": "reflect", "value": 0.50, "turns": 1, "element": "fighting"},
    },
    {
        "id": "fighting_021", "name": "Iron Fortress", "element": "fighting",
        "description": "Shield absorbing 55% of max HP in damage for 1 turn.",
        "effect": {"type": "shield", "value": 0.55, "turns": 1},
    },
    {
        "id": "fighting_022", "name": "Recovery", "element": "fighting",
        "description": "Recover 26% of max HP through fighting spirit.",
        "effect": {"type": "heal", "value": 0.26},
    },
    {
        "id": "fighting_023", "name": "Power Combo", "element": "fighting",
        "description": "Deal 45% bonus fighting damage and apply 8% ATK fighting DoT for 2 turns.",
        "effect": {"type": "instant_damage", "value": 0.45, "element": "fighting",
                   "secondary": {"type": "dot", "value": 0.08, "turns": 2, "element": "fighting"}},
    },
    {
        "id": "fighting_024", "name": "Battle Hardened", "element": "fighting",
        "description": "Boost ATK by 25% and DEF by 25% for 2 turns.",
        "effect": {"type": "stat_buff", "stat": "atk", "value": 0.25, "turns": 2,
                   "secondary": {"type": "stat_buff", "stat": "def", "value": 0.25, "turns": 2}},
    },
    {
        "id": "fighting_025", "name": "Intimidate", "element": "fighting",
        "description": "Reduce enemy ATK by 40% for 2 turns (intimidated).",
        "effect": {"type": "stat_debuff", "stat": "atk", "value": 0.40, "turns": 2},
    },
]  # end SKILL_POOL

# ── Fast lookup structures ────────────────────────────────────────────────────
SKILL_BY_ID: Dict[str, Dict[str, Any]] = {s["id"]: s for s in SKILL_POOL}
SKILLS_BY_ELEMENT: Dict[str, List[Dict[str, Any]]] = {e: [] for e in ALL_ELEMENTS}
for _sk in SKILL_POOL:
    SKILLS_BY_ELEMENT[_sk["element"]].append(_sk)


# ── Slot management helpers ───────────────────────────────────────────────────

def get_max_skill_slots(pet: Dict[str, Any]) -> int:
    """Return total skill slots available (1 base + ability tree extras)."""
    base = 1
    abilities = pet.get("abilities") or {}
    extra = 0
    if abilities.get("skill_slot_2", 0) >= 1:
        extra += 1
    if abilities.get("skill_slot_3", 0) >= 1:
        extra += 1
    if abilities.get("skill_slot_4", 0) >= 1:
        extra += 1
    return base + extra


def get_equipped_skills(pet: Dict[str, Any]) -> List[str]:
    """Return list of equipped skill IDs (may be shorter than max slots)."""
    raw = pet.get("battle_skills") or []
    return [s for s in raw if s in SKILL_BY_ID]


def get_skill_objects(pet: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return full skill dicts for all equipped skills."""
    return [SKILL_BY_ID[sid] for sid in get_equipped_skills(pet) if sid in SKILL_BY_ID]


# ── Skill selection helpers ───────────────────────────────────────────────────

def draw_initial_skill_choices(element1: str, element2: Optional[str] = None, count: int = 5) -> List[Dict[str, Any]]:
    """
    Draw `count` random skills from the combined pool of element1 (and element2 if provided).
    Used during adoption so the player can pick their first battle skill.
    """
    e1 = str(element1).lower()
    e2 = str(element2).lower() if element2 else None

    pool = list(SKILLS_BY_ELEMENT.get(e1, SKILLS_BY_ELEMENT.get("basic", [])))
    if e2 and e2 != e1 and e2 in SKILLS_BY_ELEMENT:
        pool = pool + [s for s in SKILLS_BY_ELEMENT[e2] if s not in pool]

    if not pool:
        pool = SKILLS_BY_ELEMENT.get("basic", [])

    return random.sample(pool, min(count, len(pool)))


def draw_skill_choices(pet: Dict[str, Any], count: int = 5,
                       cross_element: bool = False) -> List[Dict[str, Any]]:
    """
    Draw `count` random skills for the player to choose from.

    cross_element=False  → draw from the pet's own element pool
    cross_element=True   → draw from ALL OTHER elements (10 skills)
    """
    element = str(pet.get("element", "basic")).lower()
    already_equipped = set(get_equipped_skills(pet))

    if cross_element:
        pool = [s for s in SKILL_POOL if s["element"] != element and s["id"] not in already_equipped]
        draw_count = 10
    else:
        pool = [s for s in SKILLS_BY_ELEMENT.get(element, SKILLS_BY_ELEMENT["basic"])
                if s["id"] not in already_equipped]
        draw_count = count

    if not pool:
        # Fallback: allow duplicates if pool is exhausted
        pool = SKILLS_BY_ELEMENT.get(element, SKILLS_BY_ELEMENT["basic"]) if not cross_element \
               else [s for s in SKILL_POOL if s["element"] != element]

    return random.sample(pool, min(draw_count, len(pool)))


def equip_skill(pet: Dict[str, Any], skill_id: str, slot_index: int) -> Tuple[bool, str]:
    """
    Equip a skill into a specific slot index (0-based).
    Returns (success, message).
    """
    if skill_id not in SKILL_BY_ID:
        return False, f"Unknown skill: {skill_id}"

    max_slots = get_max_skill_slots(pet)
    if slot_index >= max_slots:
        return False, f"Slot {slot_index + 1} is not unlocked (max {max_slots} slots)."

    skills = list(get_equipped_skills(pet))
    # Pad list to slot_index if needed
    while len(skills) <= slot_index:
        skills.append("")
    skills[slot_index] = skill_id
    # Strip trailing empty strings
    while skills and not skills[-1]:
        skills.pop()
    pet["battle_skills"] = skills

    skill = SKILL_BY_ID[skill_id]
    return True, f"Equipped **{skill['name']}** in slot {slot_index + 1}."


def reroll_all_skills(pet: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Clear all equipped skills and draw a fresh full pool from the pet's element.
    Returns the drawn choices (player must call equip_skill for each slot).
    """
    pet["battle_skills"] = []
    max_slots = get_max_skill_slots(pet)
    # Draw enough for all slots at once (5 per slot, deduplicated)
    element = str(pet.get("element", "basic")).lower()
    pool = list(SKILLS_BY_ELEMENT.get(element, SKILLS_BY_ELEMENT["basic"]))
    random.shuffle(pool)
    return pool  # Caller presents these; player picks one per slot


def draw_cross_element_choices(pet: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Draw 10 skills from elements OTHER than the pet's own element.
    Used for the cross-element slot ability.
    """
    return draw_skill_choices(pet, cross_element=True)


# ── Battle state helpers ──────────────────────────────────────────────────────

def init_battle_skill_state(player_data: Dict[str, Any]) -> None:
    """
    Initialise skill-related keys on a player_data dict at battle start.
    Call this inside initialize_battle_data() for each participant.

    Per-slot cooldowns: skill_cooldowns = {slot_index: turns_remaining}
    Each slot is independent — using slot 0 does NOT affect slot 1's cooldown.
    """
    # Snapshot equipped skills so mid-battle pet changes don't affect the fight
    equipped = get_equipped_skills(player_data.get("pet") or {})
    player_data.setdefault("equipped_skills", equipped)
    # Per-slot cooldown dict — one entry per equipped slot, all start at 0 (ready)
    if "skill_cooldowns" not in player_data:
        player_data["skill_cooldowns"] = {i: 0 for i in range(len(equipped))}
    player_data.setdefault("active_effects", [])
    # Legacy single-cooldown key — keep at 0 so old code doesn't break
    player_data["skill_cooldown"] = 0


def tick_battle_effects(player_data: Dict[str, Any], attacker_atk: int) -> Tuple[int, List[str]]:
    """
    Called at the START of each round for a player.
    Ticks down all active effects, applies DoT/HoT damage, and removes expired effects.

    Returns:
        net_hp_delta  int         — positive = heal, negative = damage
        log_lines     List[str]   — human-readable descriptions of what happened
    """
    net_delta = 0
    log_lines: List[str] = []
    remaining: List[Dict[str, Any]] = []

    for eff in player_data.get("active_effects", []):
        eff_type = eff.get("type")
        turns_left = eff.get("turns_left", 0)

        if eff_type == "dot":
            # Negative value = heal-over-time (plant regrowth)
            val = eff.get("value", 0.0)
            # Use atk_at_cast (caster's ATK when skill was used) if stored,
            # otherwise fall back to the passed-in attacker_atk
            effective_atk = eff.get("atk_at_cast", attacker_atk)
            dmg = int(effective_atk * abs(val))
            if val < 0:
                net_delta += dmg
                log_lines.append(f"🌿 Regrowth heals {dmg} HP")
            else:
                net_delta -= dmg
                elem = eff.get("element", "")
                elem_tag = f" ({elem})" if elem else ""
                log_lines.append(f"🔥 {eff.get('name', 'DoT')}{elem_tag} deals {dmg} damage")

        # Decrement turns
        new_turns = turns_left - 1
        if new_turns > 0:
            eff = dict(eff)
            eff["turns_left"] = new_turns
            remaining.append(eff)
        # else: effect expires, don't keep it

    player_data["active_effects"] = remaining

    # Decrement per-slot skill cooldowns
    cooldowns = player_data.get("skill_cooldowns", {})
    for slot_idx in list(cooldowns.keys()):
        if cooldowns[slot_idx] > 0:
            cooldowns[slot_idx] -= 1
    player_data["skill_cooldowns"] = cooldowns
    # Keep legacy key in sync (0 = at least one slot ready, for backwards compat)
    player_data["skill_cooldown"] = 0

    return net_delta, log_lines


def can_use_skill(player_data: Dict[str, Any], slot_index: int = 0) -> bool:
    """
    Return True if the given skill slot is off cooldown and ready to use.
    Each slot has its own independent 3-turn cooldown.
    """
    cooldowns = player_data.get("skill_cooldowns", {})
    return cooldowns.get(slot_index, 0) == 0


def get_slot_cooldown(player_data: Dict[str, Any], slot_index: int) -> int:
    """Return the remaining cooldown turns for a specific skill slot."""
    return player_data.get("skill_cooldowns", {}).get(slot_index, 0)


def get_atk_multiplier(player_data: Dict[str, Any]) -> float:
    """Return combined ATK multiplier from all active stat_buff/debuff effects."""
    mult = 1.0
    for eff in player_data.get("active_effects", []):
        if eff.get("type") in ("stat_buff", "stat_debuff") and eff.get("stat") == "atk":
            mult *= eff.get("multiplier", 1.0)
    return mult


def get_def_multiplier(player_data: Dict[str, Any]) -> float:
    """Return combined DEF multiplier from all active stat_buff/debuff effects."""
    mult = 1.0
    for eff in player_data.get("active_effects", []):
        if eff.get("type") in ("stat_buff", "stat_debuff") and eff.get("stat") == "def":
            mult *= eff.get("multiplier", 1.0)
    return mult


def get_damage_reduction(player_data: Dict[str, Any]) -> float:
    """Return total incoming damage reduction fraction (0.0–1.0) from active effects."""
    total = 0.0
    for eff in player_data.get("active_effects", []):
        if eff.get("type") == "damage_reduction":
            total += eff.get("value", 0.0)
    return min(total, 0.90)  # cap at 90% reduction


def get_shield_hp(player_data: Dict[str, Any]) -> int:
    """Return total remaining shield HP from all active shield effects."""
    total = 0
    for eff in player_data.get("active_effects", []):
        if eff.get("type") == "shield":
            total += eff.get("shield_hp", 0)
    return total


def absorb_damage_through_shield(player_data: Dict[str, Any], incoming: int) -> Tuple[int, int, List[str]]:
    """
    Pass incoming damage through any active shields first.
    Returns (damage_after_shield, shield_absorbed, log_lines).
    Modifies player_data["active_effects"] in place.
    """
    remaining_dmg = incoming
    absorbed = 0
    log_lines: List[str] = []
    new_effects: List[Dict[str, Any]] = []

    for eff in player_data.get("active_effects", []):
        if eff.get("type") == "shield" and remaining_dmg > 0:
            shield_hp = eff.get("shield_hp", 0)
            if shield_hp > 0:
                taken = min(shield_hp, remaining_dmg)
                shield_hp -= taken
                remaining_dmg -= taken
                absorbed += taken
                eff = dict(eff)
                eff["shield_hp"] = shield_hp
                if shield_hp > 0:
                    new_effects.append(eff)
                    log_lines.append(f"🛡️ Shield absorbs {taken} damage ({shield_hp} remaining)")
                else:
                    log_lines.append(f"🛡️ Shield absorbs {taken} damage and shatters!")
            else:
                new_effects.append(eff)
        else:
            new_effects.append(eff)

    player_data["active_effects"] = new_effects
    return remaining_dmg, absorbed, log_lines


def get_reflect_value(player_data: Dict[str, Any]) -> float:
    """Return total reflect fraction from all active reflect effects."""
    total = 0.0
    for eff in player_data.get("active_effects", []):
        if eff.get("type") == "reflect":
            total += eff.get("value", 0.0)
    return min(total, 0.90)


def is_stunned(player_data: Dict[str, Any]) -> bool:
    """Return True if the player has an active stun effect."""
    return any(eff.get("type") == "stun" for eff in player_data.get("active_effects", []))


def consume_stun(player_data: Dict[str, Any]) -> None:
    """Remove one stun effect (consumed when the stun turn fires)."""
    effects = player_data.get("active_effects", [])
    for i, eff in enumerate(effects):
        if eff.get("type") == "stun":
            effects.pop(i)
            break
    player_data["active_effects"] = effects


# ── Core skill application engine ─────────────────────────────────────────────

def apply_skill(
    skill_id: str,
    user_data: Dict[str, Any],
    target_data: Optional[Dict[str, Any]],
    battle_type: str = "npc",
    slot_index: int = 0,
) -> Dict[str, Any]:
    """
    Apply a battle skill and return a result dict.

    Parameters
    ----------
    skill_id    : ID of the skill being used
    user_data   : player_data dict for the skill user (modified in place)
    target_data : player_data dict for the target (modified in place, may be None for self-only skills)
    battle_type : "npc", "boss", or "pvp"

    Returns
    -------
    {
        "ok":           bool,
        "message":      str,          # human-readable summary line
        "hp_delta_user":   int,       # HP change on user  (positive=heal, negative=damage)
        "hp_delta_target": int,       # HP change on target (positive=heal, negative=damage)
        "skill_name":   str,
        "skill_id":     str,
        "effects_applied": list[str], # names of effects added
    }
    """
    skill = SKILL_BY_ID.get(skill_id)
    if not skill:
        return {"ok": False, "message": f"Unknown skill: {skill_id}", "hp_delta_user": 0, "hp_delta_target": 0,
                "skill_name": "?", "skill_id": skill_id, "effects_applied": []}

    if not can_use_skill(user_data, slot_index):
        cd = get_slot_cooldown(user_data, slot_index)
        return {"ok": False, "message": f"Skill on cooldown ({cd} turn(s) remaining).",
                "hp_delta_user": 0, "hp_delta_target": 0,
                "skill_name": skill["name"], "skill_id": skill_id, "effects_applied": []}

    effect = skill["effect"]
    skill_name = skill["name"]
    hp_delta_user = 0
    hp_delta_target = 0
    effects_applied: List[str] = []
    message_parts: List[str] = []

    # Helper: get attacker ATK stat for scaling
    user_atk = user_data.get("total_attack", user_data.get("attack", 10))

    def _apply_single_effect(eff: Dict[str, Any], is_secondary: bool = False) -> None:
        nonlocal hp_delta_user, hp_delta_target
        etype = eff.get("type")
        val = float(eff.get("value", 0.0))
        turns = int(eff.get("turns", 0))
        elem = eff.get("element", "")

        if etype == "instant_damage":
            # Compute elemental bonus if skill has an element
            elem_bonus = 1.0
            if elem and target_data:
                try:
                    from Systems.Pets.Logic.damage_calculator import DamageCalculator
                    elem_bonus = DamageCalculator.compute_element_bonus(
                        elem,
                        str(target_data.get("element", "basic")).lower()
                    )
                except Exception:
                    pass
            raw_dmg = int(user_atk * val * elem_bonus)
            # Apply target damage reduction
            if target_data:
                dr = get_damage_reduction(target_data)
                raw_dmg = max(1, int(raw_dmg * (1.0 - dr)))
                # Pass through shield
                raw_dmg, absorbed, shield_log = absorb_damage_through_shield(target_data, raw_dmg)
                for sl in shield_log:
                    message_parts.append(sl)
            hp_delta_target -= raw_dmg
            elem_tag = f" ({elem})" if elem else ""
            message_parts.append(f"💥 {skill_name}{elem_tag} deals **{raw_dmg}** damage")

        elif etype == "dot":
            if val < 0:
                # Heal-over-time (plant regrowth)
                user_data.setdefault("active_effects", []).append({
                    "type": "dot", "value": val, "turns_left": turns,
                    "name": skill_name, "element": elem,
                    "atk_at_cast": user_atk,  # scale heal off caster's ATK
                })
                effects_applied.append(f"HoT ({turns}t)")
                message_parts.append(f"🌿 {skill_name}: heals {int(user_atk * abs(val))}/turn for {turns} turns")
            else:
                if target_data is not None:
                    target_data.setdefault("active_effects", []).append({
                        "type": "dot", "value": val, "turns_left": turns,
                        "name": skill_name, "element": elem,
                        "atk_at_cast": user_atk,  # scale damage off caster's ATK, not victim's
                    })
                    effects_applied.append(f"DoT ({turns}t)")
                    elem_tag = f" ({elem})" if elem else ""


        elif etype == "shield":
            shield_hp = int(user_data.get("max_hp", 500) * val)
            user_data.setdefault("active_effects", []).append({
                "type": "shield", "shield_hp": shield_hp, "turns_left": turns,
                "name": skill_name,
            })
            effects_applied.append(f"Shield ({shield_hp} HP, {turns}t)")
            message_parts.append(f"🛡️ {skill_name}: shield absorbs up to {shield_hp} damage for {turns} turns")

        elif etype == "damage_reduction":
            user_data.setdefault("active_effects", []).append({
                "type": "damage_reduction", "value": val, "turns_left": turns,
                "name": skill_name,
            })
            effects_applied.append(f"DR {int(val*100)}% ({turns}t)")
            message_parts.append(f"🔰 {skill_name}: -{int(val*100)}% incoming damage for {turns} turns")

        elif etype == "heal":
            heal_amt = int(user_data.get("max_hp", 500) * val)
            hp_delta_user += heal_amt
            message_parts.append(f"💚 {skill_name} heals **{heal_amt}** HP")

        elif etype == "charge_boost":
            boost = int(val)
            current = float(user_data.get("charge_multiplier", 1.0))
            max_charge = float(user_data.get("max_charge_limit", 5.0))
            new_charge = min(max_charge, current + boost)
            user_data["charge_multiplier"] = new_charge
            user_data["charge"] = new_charge
            message_parts.append(f"⚡ {skill_name}: charge → x{new_charge:.0f}")

        elif etype == "stat_buff":
            stat = eff.get("stat", "atk")
            multiplier = 1.0 + val
            user_data.setdefault("active_effects", []).append({
                "type": "stat_buff", "stat": stat, "multiplier": multiplier,
                "turns_left": turns, "name": skill_name,
            })
            effects_applied.append(f"+{int(val*100)}% {stat.upper()} ({turns}t)")
            message_parts.append(f"📈 {skill_name}: +{int(val*100)}% {stat.upper()} for {turns} turns")

        elif etype == "stat_debuff":
            stat = eff.get("stat", "atk")
            multiplier = 1.0 - val
            if target_data is not None:
                target_data.setdefault("active_effects", []).append({
                    "type": "stat_debuff", "stat": stat, "multiplier": multiplier,
                    "turns_left": turns, "name": skill_name,
                })
                effects_applied.append(f"-{int(val*100)}% enemy {stat.upper()} ({turns}t)")
                message_parts.append(f"📉 {skill_name}: -{int(val*100)}% enemy {stat.upper()} for {turns} turns")

        elif etype == "lifesteal":
            elem_bonus = 1.0
            if elem and target_data:
                try:
                    from Systems.Pets.Logic.damage_calculator import DamageCalculator
                    elem_bonus = DamageCalculator.compute_element_bonus(
                        elem,
                        str(target_data.get("element", "basic")).lower()
                    )
                except Exception:
                    pass
            raw_dmg = int(user_atk * val * elem_bonus)
            if target_data:
                dr = get_damage_reduction(target_data)
                raw_dmg = max(1, int(raw_dmg * (1.0 - dr)))
                raw_dmg, absorbed, shield_log = absorb_damage_through_shield(target_data, raw_dmg)
                for sl in shield_log:
                    message_parts.append(sl)
            heal_pct = float(eff.get("heal_pct", 0.40))
            heal_amt = int(raw_dmg * heal_pct)
            hp_delta_target -= raw_dmg
            hp_delta_user += heal_amt
            elem_tag = f" ({elem})" if elem else ""
            message_parts.append(
                f"🩸 {skill_name}{elem_tag}: deals **{raw_dmg}** damage, heals **{heal_amt}** HP"
            )

        elif etype == "stun":
            if target_data is not None:
                target_data.setdefault("active_effects", []).append({
                    "type": "stun", "turns_left": turns, "name": skill_name,
                })
                effects_applied.append("Stun (1t)")
                message_parts.append(f"💫 {skill_name}: enemy stunned for {turns} turn(s)!")

        elif etype == "cleanse":
            before = len(user_data.get("active_effects", []))
            user_data["active_effects"] = [
                e for e in user_data.get("active_effects", [])
                if e.get("type") not in ("dot", "stat_debuff", "stun")
            ]
            removed = before - len(user_data.get("active_effects", []))
            message_parts.append(f"✨ {skill_name}: removed {removed} negative effect(s)")

        elif etype == "reflect":
            user_data.setdefault("active_effects", []).append({
                "type": "reflect", "value": val, "turns_left": turns,
                "name": skill_name, "element": elem,
            })
            effects_applied.append(f"Reflect {int(val*100)}% ({turns}t)")
            message_parts.append(f"🪞 {skill_name}: reflects {int(val*100)}% damage for {turns} turns")

    # Apply primary effect
    _apply_single_effect(effect)

    # Apply secondary effect if present
    secondary = effect.get("secondary")
    if secondary:
        _apply_single_effect(secondary, is_secondary=True)

    # Set per-slot cooldown for this specific slot
    if "skill_cooldowns" not in user_data:
        user_data["skill_cooldowns"] = {}
    user_data["skill_cooldowns"][slot_index] = SKILL_COOLDOWN_TURNS
    # Keep legacy key in sync
    user_data["skill_cooldown"] = SKILL_COOLDOWN_TURNS

    return {
        "ok": True,
        "message": " | ".join(message_parts) if message_parts else f"{skill_name} used!",
        "hp_delta_user": hp_delta_user,
        "hp_delta_target": hp_delta_target,
        "skill_name": skill_name,
        "skill_id": skill_id,
        "effects_applied": effects_applied,
    }


# ── Ability tree integration stubs ────────────────────────────────────────────
# These are the ability IDs that must be added to ability_tree.py ABILITIES list.
# They are referenced here for documentation; the actual dicts live in ability_tree.py.

SKILL_SLOT_ABILITY_IDS = ["skill_slot_2", "skill_slot_3", "skill_slot_4"]
SKILL_REROLL_ABILITY_ID = "skill_reroll_all"
SKILL_CROSS_ELEMENT_ABILITY_ID = "skill_cross_element"


# ── Serialisation helpers (for API / web) ─────────────────────────────────────

def get_skill_state(pet: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return the full skill state for the frontend / API.
    """
    equipped = get_equipped_skills(pet)
    max_slots = get_max_skill_slots(pet)
    element = str(pet.get("element", "basic")).lower()

    slots = []
    for i in range(max_slots):
        if i < len(equipped) and equipped[i]:
            sk = SKILL_BY_ID.get(equipped[i])
            slots.append({
                "slot": i,
                "skill_id": equipped[i],
                "skill": sk,
                "filled": True,
            })
        else:
            slots.append({"slot": i, "skill_id": None, "skill": None, "filled": False})

    return {
        "element": element,
        "max_slots": max_slots,
        "slots": slots,
        "pool_size": len(SKILLS_BY_ELEMENT.get(element, [])),
    }
