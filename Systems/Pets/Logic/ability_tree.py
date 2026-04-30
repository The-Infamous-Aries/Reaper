"""
Endgame Ability & Stat Mastery Tree — Backend Logic
===================================================
Defines all abilities, stat mastery rules, and helper functions for
reading/writing ability tree data on a pet.

**ENDGAME FEATURE**: Ability points must be purchased by spending 500 levels each.
This is designed for high-level pets who want to trade levels for permanent bonuses.

Data stored on the pet object:
  pet["ability_points"]        int  — unspent points available to allocate (purchased with levels)
  pet["stat_mastery"]          dict — {stat: points_spent}  (endless, each +0.1x multiplier)
  pet["advantage_mastery"]     dict — {key: points_spent}   (endless, each +0.1 flat bonus)
  pet["abilities"]             dict — {ability_id: level}   — ability levels (1-5)

Ability Point Economy:
  - Cost: 500 levels per ability point
  - No automatic awarding (removed from level-up rewards)
  - Permanent trade: levels → ability points (cannot be reversed)

Stat Mastery multiplier formula:
  multiplier = 1.0 + (points_spent * 0.1)
  First point → 1.1x, second → 1.2x, tenth → 2.0x, etc.

Advantage Mastery bonus formula (type and element):
  bonus = points_spent * 0.1
  Applied as a flat addition to the base advantage multiplier (only when advantage > 1.0).
  Keys: "type" (category triangle), "element" (element effectiveness).
  First point → +0.1 on top of base (e.g. 1.15 → 1.25), tenth → +1.0 (e.g. 1.15 → 2.15).

Multi-Level Abilities (1-5 levels each):
  - Each ability can be upgraded 5 times (costs 1 point per upgrade)
  - Effects scale linearly: base + (per_level * (level - 1))
  - Example: 5% base + 5% per level = 5%, 10%, 15%, 20%, 25% at levels 1-5
  - **REQUIREMENT**: Must have at least 1 point in corresponding stat mastery
  - **NO PREREQUISITES**: Can unlock abilities in any order within a branch

Ability Tree layout (6 branches by stat theme):
  ATT branch → battle damage + aggressive survivor tactics + critical hits (6 abilities)
  DEF branch → battle defense + defensive survivor tactics + charge protection (6 abilities)  
  INT branch → XP multipliers for all 8 activities (8 abilities)
  DEX branch → speed boost + casino loss reduction (12 abilities)
  HAP branch → battle health + casino win bonuses (12 abilities)
  ENE branch → battle health + charge limit + speed + charge mastery (5 abilities)

Total: 49 abilities × 5 levels = 245 ability points maximum
At 500 levels per point = 122,500 levels for full completion

**Progression Flow:**
1. Purchase ability points with levels (500 each)
2. Spend 1 ability point on stat mastery to unlock a branch
3. Spend remaining points on any abilities in unlocked branches (any order)
4. Continue investing in stat mastery for permanent multipliers
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

# ── Stat keys ────────────────────────────────────────────────────────────────
STATS = ["ATT", "DEF", "INT", "DEX", "HAP", "ENE"]

# ── Advantage Mastery keys ────────────────────────────────────────────────────
ADVANTAGE_MASTERY_KEYS = ["type", "element"]

# ── Ability definitions ───────────────────────────────────────────────────────
# Each ability:
#   id          str   — unique key stored in pet["abilities"] as {id: level}
#   name        str   — display name
#   stat        str   — which stat branch it belongs to
#   max_level   int   — maximum level (1-5)
#   cost        int   — ability points to unlock/upgrade each level
#   description str   — shown in UI (use {level} and {value} placeholders)
#   effect      dict  — machine-readable effect descriptor used by game systems
#
# Effect types:
#   battle_damage_mult   — multiplies outgoing battle damage by `value` (per battle type)
#   battle_defense_mult  — multiplies incoming damage reduction by `value` (per battle type)
#   survive_score_mult   — multiplies survivor series score contribution by `value`
#   xp_multiplier        — multiplies XP gained from a source by `value`
#   speed_multiplier     — multiplies race speed by `value`
#   casino_xp_loss_reduction — reduces XP lost in casino games by `value` fraction
#   casino_xp_gain_mult  — multiplies XP gained in casino games by `value`
#   battle_health_bonus  — adds `value` percentage to battle health
#   charge_limit_bonus   — adds `value` to maximum charge limit
#   critical_hit_chance  — adds `value` chance for critical hits (0.0-1.0)
#   critical_hit_multiplier — multiplies critical hit damage by `value`
#   charge_vulnerability_reduction — reduces charge vulnerability multiplier by `value`
#   low_health_damage_reduction — reduces damage taken when below 25% health by `value` fraction
#   starting_charge_bonus — adds `value` charge levels at battle start
#   overcharged_bonus    — additional starting charge bonus (requires prerequisites)

ABILITIES: List[Dict[str, Any]] = [

    # ── ATT Branch: Damage + Aggressive Survivor Tactics ────────────────────
    {
        "id": "att_npc_damage",
        "name": "NPC Crusher",
        "stat": "ATT",
        "max_level": 5,
        "cost": 1,
        "description": "Devastate NPC opponents. +{value}% damage in NPC battles.",
        "effect": {"type": "battle_damage_mult", "battle_type": "npc", "base": 1.05, "per_level": 0.05},
    },
    {
        "id": "att_pvp_damage",
        "name": "PvP Dominator",
        "stat": "ATT",
        "max_level": 5,
        "cost": 1,
        "description": "Crush other players. +{value}% damage in PvP battles.",
        "effect": {"type": "battle_damage_mult", "battle_type": "pvp", "base": 1.05, "per_level": 0.05},
    },
    {
        "id": "att_boss_damage",
        "name": "Boss Slayer",
        "stat": "ATT",
        "max_level": 5,
        "cost": 1,
        "description": "Strike down mighty bosses. +{value}% damage in Boss battles.",
        "effect": {"type": "battle_damage_mult", "battle_type": "boss", "base": 1.05, "per_level": 0.05},
    },
    {
        "id": "att_survive_aggression",
        "name": "Aggressive Survivor",
        "stat": "ATT",
        "max_level": 5,
        "cost": 1,
        "description": "Aggressive tactics in survival. x{value} survivor series score multiplier.",
        "effect": {"type": "survive_score_mult", "base": 1.1, "per_level": 0.1},
    },
    {
        "id": "att_critical_chance",
        "name": "Critical Strike",
        "stat": "ATT",
        "max_level": 5,
        "cost": 1,
        "description": "Deadly precision strikes. {value}% chance for critical hits.",
        "effect": {"type": "critical_hit_chance", "base": 0.05, "per_level": 0.05},
    },
    {
        "id": "att_critical_multiplier",
        "name": "Critical Mastery",
        "stat": "ATT",
        "max_level": 5,
        "cost": 1,
        "description": "Enhanced critical damage. Critical hits deal x{value} damage.",
        "effect": {"type": "critical_hit_multiplier", "base": 1.40, "per_level": 0.15},
    },

    # ── DEF Branch: Defense + Defensive Survivor Tactics ────────────────────
    {
        "id": "def_npc_defense",
        "name": "NPC Guardian",
        "stat": "DEF",
        "max_level": 5,
        "cost": 1,
        "description": "Withstand NPC attacks. -{value}% damage taken in NPC battles.",
        "effect": {"type": "battle_defense_mult", "battle_type": "npc", "base": 1.05, "per_level": 0.05},
    },
    {
        "id": "def_pvp_defense",
        "name": "PvP Fortress",
        "stat": "DEF",
        "max_level": 5,
        "cost": 1,
        "description": "Defend against players. -{value}% damage taken in PvP battles.",
        "effect": {"type": "battle_defense_mult", "battle_type": "pvp", "base": 1.05, "per_level": 0.05},
    },
    {
        "id": "def_boss_defense",
        "name": "Boss Tank",
        "stat": "DEF",
        "max_level": 5,
        "cost": 1,
        "description": "Endure boss attacks. -{value}% damage taken in Boss battles.",
        "effect": {"type": "battle_defense_mult", "battle_type": "boss", "base": 1.05, "per_level": 0.05},
    },
    {
        "id": "def_survive_endurance",
        "name": "Defensive Survivor",
        "stat": "DEF",
        "max_level": 5,
        "cost": 1,
        "description": "Defensive endurance in survival. x{value} survivor series score multiplier.",
        "effect": {"type": "survive_score_mult", "base": 1.1, "per_level": 0.1},
    },
    {
        "id": "def_charge_protection",
        "name": "Charge Guard",
        "stat": "DEF",
        "max_level": 5,
        "cost": 1,
        "description": "Reduce vulnerability when charging. -{value}% extra damage taken while charging.",
        "effect": {"type": "charge_vulnerability_reduction", "base": 0.05, "per_level": 0.05},
    },
    {
        "id": "def_last_stand",
        "name": "Last Stand",
        "stat": "DEF",
        "max_level": 5,
        "cost": 1,
        "description": "Defiant when near death. -{value}% damage taken when below 25% health.",
        "effect": {"type": "low_health_damage_reduction", "base": 0.05, "per_level": 0.05},
    },

    # ── INT Branch: XP Multipliers for All Activities ───────────────────────
    {
        "id": "int_train_xp",
        "name": "Training Scholar",
        "stat": "INT",
        "max_level": 5,
        "cost": 1,
        "description": "Sharp mind sharpens training. On success: +{value} bonus to stat gained. On failure: blocks {value} from being lost.",
        "effect": {"type": "train_bonus", "base": 1, "per_level": 1},
    },
    {
        "id": "int_mission_xp",
        "name": "Mission Expert",
        "stat": "INT",
        "max_level": 5,
        "cost": 1,
        "description": "Master mission tactics. +{value}% XP from missions.",
        "effect": {"type": "xp_multiplier", "source": ["mission"], "base": 1.05, "per_level": 0.05},
    },
    {
        "id": "int_play_xp",
        "name": "Playful Learner",
        "stat": "INT",
        "max_level": 5,
        "cost": 1,
        "description": "Learn through play. +{value}% XP from play activities.",
        "effect": {"type": "xp_multiplier", "source": ["play"], "base": 1.05, "per_level": 0.05},
    },
    {
        "id": "int_quest_xp",
        "name": "Quest Master",
        "stat": "INT",
        "max_level": 5,
        "cost": 1,
        "description": "Excel at quests. +{value}% XP from quests.",
        "effect": {"type": "xp_multiplier", "source": ["quest"], "base": 1.05, "per_level": 0.05},
    },
    {
        "id": "int_survive_xp",
        "name": "Survival Wisdom",
        "stat": "INT",
        "max_level": 5,
        "cost": 1,
        "description": "Learn from survival. +{value}% XP from survivor series.",
        "effect": {"type": "xp_multiplier", "source": ["survive"], "base": 1.05, "per_level": 0.05},
    },
    {
        "id": "int_npc_battle_xp",
        "name": "NPC Combat Study",
        "stat": "INT",
        "max_level": 5,
        "cost": 1,
        "description": "Study NPC combat patterns. +{value}% XP from NPC battles.",
        "effect": {"type": "xp_multiplier", "source": ["npc_battle"], "base": 1.05, "per_level": 0.05},
    },
    {
        "id": "int_pvp_battle_xp",
        "name": "PvP Combat Analysis",
        "stat": "INT",
        "max_level": 5,
        "cost": 1,
        "description": "Analyze PvP strategies. +{value}% XP from PvP battles.",
        "effect": {"type": "xp_multiplier", "source": ["pvp_battle"], "base": 1.05, "per_level": 0.05},
    },
    {
        "id": "int_boss_battle_xp",
        "name": "Boss Combat Mastery",
        "stat": "INT",
        "max_level": 5,
        "cost": 1,
        "description": "Master boss mechanics. +{value}% XP from Boss battles.",
        "effect": {"type": "xp_multiplier", "source": ["boss_battle"], "base": 1.05, "per_level": 0.05},
    },

    # ── DEX Branch: Speed + Casino Loss Reduction ───────────────────────────
    {
        "id": "dex_speed_boost",
        "name": "Swift Runner",
        "stat": "DEX",
        "max_level": 5,
        "cost": 1,
        "description": "Incredible speed in races. x{value} speed multiplier.",
        "effect": {"type": "speed_multiplier", "base": 1.1, "per_level": 0.1},
    },
    {
        "id": "dex_slots_loss_reduction",
        "name": "Slots Resilience",
        "stat": "DEX",
        "max_level": 5,
        "cost": 1,
        "description": "Quick reflexes reduce slots losses. -{value}% XP lost on slots losses.",
        "effect": {"type": "casino_xp_loss_reduction", "game": "slots", "base": 0.05, "per_level": 0.05},
    },
    {
        "id": "dex_blackjack_loss_reduction",
        "name": "Blackjack Reflexes",
        "stat": "DEX",
        "max_level": 5,
        "cost": 1,
        "description": "Quick thinking reduces blackjack losses. -{value}% XP lost on blackjack losses.",
        "effect": {"type": "casino_xp_loss_reduction", "game": "blackjack", "base": 0.05, "per_level": 0.05},
    },
    {
        "id": "dex_holdem_loss_reduction",
        "name": "Hold'em Instincts",
        "stat": "DEX",
        "max_level": 5,
        "cost": 1,
        "description": "Sharp instincts reduce hold'em losses. -{value}% XP lost on hold'em losses.",
        "effect": {"type": "casino_xp_loss_reduction", "game": "holdem", "base": 0.05, "per_level": 0.05},
    },
    {
        "id": "dex_craps_loss_reduction",
        "name": "Craps Timing",
        "stat": "DEX",
        "max_level": 5,
        "cost": 1,
        "description": "Perfect timing reduces craps losses. -{value}% XP lost on craps losses.",
        "effect": {"type": "casino_xp_loss_reduction", "game": "craps", "base": 0.05, "per_level": 0.05},
    },
    {
        "id": "dex_wheel_loss_reduction",
        "name": "Wheel Agility",
        "stat": "DEX",
        "max_level": 5,
        "cost": 1,
        "description": "Agile reactions reduce wheel losses. -{value}% XP lost on wheel losses.",
        "effect": {"type": "casino_xp_loss_reduction", "game": "wheel_of_pets", "base": 0.05, "per_level": 0.05},
    },
    {
        "id": "dex_keno_loss_reduction",
        "name": "Keno Precision",
        "stat": "DEX",
        "max_level": 5,
        "cost": 1,
        "description": "Precise number picking reduces keno losses. -{value}% XP lost on keno losses.",
        "effect": {"type": "casino_xp_loss_reduction", "game": "keno", "base": 0.05, "per_level": 0.05},
    },
    {
        "id": "dex_scratch_loss_reduction",
        "name": "Scratch Intuition",
        "stat": "DEX",
        "max_level": 5,
        "cost": 1,
        "description": "Intuitive scratching reduces scratch card losses. -{value}% XP lost on scratch card losses.",
        "effect": {"type": "casino_xp_loss_reduction", "game": "scratch_cards", "base": 0.05, "per_level": 0.05},
    },
    {
        "id": "dex_powerball_loss_reduction",
        "name": "Powerball Insight",
        "stat": "DEX",
        "max_level": 5,
        "cost": 1,
        "description": "Strategic number selection reduces powerball losses. -{value}% XP lost on powerball tickets.",
        "effect": {"type": "casino_xp_loss_reduction", "game": "powerball", "base": 0.05, "per_level": 0.05},
    },
    {
        "id": "dex_races_loss_reduction",
        "name": "Racing Strategy",
        "stat": "DEX",
        "max_level": 5,
        "cost": 1,
        "description": "Smart betting reduces race losses. -{value}% XP lost on race bets.",
        "effect": {"type": "casino_xp_loss_reduction", "game": "races", "base": 0.05, "per_level": 0.05},
    },
    {
        "id": "dex_coinflip_loss_reduction",
        "name": "Coin Sense",
        "stat": "DEX",
        "max_level": 5,
        "cost": 1,
        "description": "Sharp instincts reduce coinflip losses. -{value}% XP lost on coinflip bets.",
        "effect": {"type": "casino_xp_loss_reduction", "game": "coinflip", "base": 0.05, "per_level": 0.05},
    },
    {
        "id": "dex_rps_loss_reduction",
        "name": "RPS Prediction",
        "stat": "DEX",
        "max_level": 5,
        "cost": 1,
        "description": "Predictive skills reduce rock-paper-scissors losses. -{value}% XP lost on RPS bets.",
        "effect": {"type": "casino_xp_loss_reduction", "game": "rps", "base": 0.05, "per_level": 0.05},
    },

    # ── HAP Branch: Battle Health + Casino Win Bonuses ──────────────────────
    {
        "id": "hap_battle_health",
        "name": "Joyful Vitality",
        "stat": "HAP",
        "max_level": 5,
        "cost": 1,
        "description": "Happiness boosts health. +{value}% battle health.",
        "effect": {"type": "battle_health_bonus", "base": 0.05, "per_level": 0.05},
    },
    {
        "id": "hap_slots_win_bonus",
        "name": "Lucky Slots",
        "stat": "HAP",
        "max_level": 5,
        "cost": 1,
        "description": "Happy fortune in slots. +{value}% XP from slots wins.",
        "effect": {"type": "casino_xp_gain_mult", "game": "slots", "base": 1.05, "per_level": 0.05},
    },
    {
        "id": "hap_blackjack_win_bonus",
        "name": "Blackjack Bliss",
        "stat": "HAP",
        "max_level": 5,
        "cost": 1,
        "description": "Happy cards bring fortune. +{value}% XP from blackjack wins.",
        "effect": {"type": "casino_xp_gain_mult", "game": "blackjack", "base": 1.05, "per_level": 0.05},
    },
    {
        "id": "hap_holdem_win_bonus",
        "name": "Hold'em Joy",
        "stat": "HAP",
        "max_level": 5,
        "cost": 1,
        "description": "Joyful poker brings rewards. +{value}% XP from hold'em wins.",
        "effect": {"type": "casino_xp_gain_mult", "game": "holdem", "base": 1.05, "per_level": 0.05},
    },
    {
        "id": "hap_craps_win_bonus",
        "name": "Craps Celebration",
        "stat": "HAP",
        "max_level": 5,
        "cost": 1,
        "description": "Celebrate craps victories. +{value}% XP from craps wins.",
        "effect": {"type": "casino_xp_gain_mult", "game": "craps", "base": 1.05, "per_level": 0.05},
    },
    {
        "id": "hap_wheel_win_bonus",
        "name": "Wheel of Joy",
        "stat": "HAP",
        "max_level": 5,
        "cost": 1,
        "description": "Joyful spins bring rewards. +{value}% XP from wheel wins.",
        "effect": {"type": "casino_xp_gain_mult", "game": "wheel_of_pets", "base": 1.05, "per_level": 0.05},
    },
    {
        "id": "hap_keno_win_bonus",
        "name": "Keno Celebration",
        "stat": "HAP",
        "max_level": 5,
        "cost": 1,
        "description": "Celebrate keno victories. +{value}% XP from keno wins.",
        "effect": {"type": "casino_xp_gain_mult", "game": "keno", "base": 1.05, "per_level": 0.05},
    },
    {
        "id": "hap_scratch_win_bonus",
        "name": "Scratch Euphoria",
        "stat": "HAP",
        "max_level": 5,
        "cost": 1,
        "description": "Euphoric scratch wins. +{value}% XP from scratch card wins.",
        "effect": {"type": "casino_xp_gain_mult", "game": "scratch_cards", "base": 1.05, "per_level": 0.05},
    },
    {
        "id": "hap_powerball_win_bonus",
        "name": "Powerball Ecstasy",
        "stat": "HAP",
        "max_level": 5,
        "cost": 1,
        "description": "Ecstatic powerball wins. +{value}% XP from powerball wins.",
        "effect": {"type": "casino_xp_gain_mult", "game": "powerball", "base": 1.05, "per_level": 0.05},
    },
    {
        "id": "hap_races_win_bonus",
        "name": "Victory Lap",
        "stat": "HAP",
        "max_level": 5,
        "cost": 1,
        "description": "Celebrate race victories. +{value}% XP from race wins.",
        "effect": {"type": "casino_xp_gain_mult", "game": "races", "base": 1.05, "per_level": 0.05},
    },
    {
        "id": "hap_coinflip_win_bonus",
        "name": "Coin Luck",
        "stat": "HAP",
        "max_level": 5,
        "cost": 1,
        "description": "Lucky coin flips. +{value}% XP from coinflip wins.",
        "effect": {"type": "casino_xp_gain_mult", "game": "coinflip", "base": 1.05, "per_level": 0.05},
    },
    {
        "id": "hap_rps_win_bonus",
        "name": "RPS Triumph",
        "stat": "HAP",
        "max_level": 5,
        "cost": 1,
        "description": "Triumphant RPS victories. +{value}% XP from RPS wins.",
        "effect": {"type": "casino_xp_gain_mult", "game": "rps", "base": 1.05, "per_level": 0.05},
    },

    # ── ENE Branch: Battle Health + Charge Limit + Speed ────────────────────
    {
        "id": "ene_battle_stamina",
        "name": "Battle Stamina",
        "stat": "ENE",
        "max_level": 5,
        "cost": 1,
        "description": "Energy fuels endurance. +{value}% battle health.",
        "effect": {"type": "battle_health_bonus", "base": 0.05, "per_level": 0.05},
    },
    {
        "id": "ene_charge_mastery",
        "name": "Charge Mastery",
        "stat": "ENE",
        "max_level": 5,
        "cost": 1,
        "description": "Master energy control. +{value} maximum charge limit.",
        "effect": {"type": "charge_limit_bonus", "base": 1, "per_level": 1},
    },
    {
        "id": "ene_speed_burst",
        "name": "Energy Burst",
        "stat": "ENE",
        "max_level": 5,
        "cost": 1,
        "description": "Channel energy into speed. x{value} speed multiplier.",
        "effect": {"type": "speed_multiplier", "base": 1.1, "per_level": 0.1},
    },
    {
        "id": "ene_charged_start",
        "name": "Charged",
        "stat": "ENE",
        "max_level": 5,
        "cost": 1,
        "description": "Start battles energized. Begin with +{value} charge levels.",
        "effect": {"type": "starting_charge_bonus", "base": 1, "per_level": 1},
    },
    {
        "id": "ene_overcharged",
        "name": "Overcharged",
        "stat": "ENE",
        "max_level": 5,
        "cost": 1,
        "description": "Ultimate energy mastery. Additional +{value} starting charge (requires Charged maxed + Charge Mastery).",
        "effect": {"type": "overcharged_bonus", "base": 1, "per_level": 1},
        "requires_abilities": ["ene_charged_start", "ene_charge_mastery"],
        "requires_max_level": True,
    },
]

# Quick lookup by id
ABILITY_BY_ID: Dict[str, Dict[str, Any]] = {a["id"]: a for a in ABILITIES}

# Abilities grouped by stat branch
ABILITIES_BY_STAT: Dict[str, List[Dict[str, Any]]] = {s: [] for s in STATS}
for _ab in ABILITIES:
    ABILITIES_BY_STAT[_ab["stat"]].append(_ab)


# ── Stat Mastery helpers ──────────────────────────────────────────────────────

def get_stat_mastery_multiplier(pet: Dict[str, Any], stat: str) -> float:
    """
    Returns the stat mastery multiplier for a given stat.
    1.0 base + 0.1 per point spent.
    """
    mastery = pet.get("stat_mastery") or {}
    stat_data = mastery.get(stat, 0)
    
    # Handle both old format (just numbers) and new format (dict with points)
    if isinstance(stat_data, dict):
        points = int(stat_data.get("points", 0))
    else:
        points = int(stat_data)
    
    return round(1.0 + points * 0.1, 10)


def get_all_mastery_multipliers(pet: Dict[str, Any]) -> Dict[str, float]:
    return {s: get_stat_mastery_multiplier(pet, s) for s in STATS}


# ── Advantage Mastery helpers ─────────────────────────────────────────────────

def get_advantage_mastery_bonus(pet: Dict[str, Any], key: str) -> float:
    """
    Returns the flat bonus added to an advantage multiplier when the pet has
    the advantage (base > 1.0).  Formula: points_spent * 0.1.
    key is one of ADVANTAGE_MASTERY_KEYS: "type" or "element".
    """
    mastery = pet.get("advantage_mastery") or {}
    points = int(mastery.get(key, 0))
    return round(points * 0.1, 10)


def spend_advantage_mastery(pet: Dict[str, Any], key: str, points: int = 1) -> Tuple[bool, str]:
    """
    Spend `points` ability points on advantage mastery for `key`.
    Returns (success, message).
    """
    if key not in ADVANTAGE_MASTERY_KEYS:
        return False, f"Unknown advantage mastery key: {key}. Valid keys: {ADVANTAGE_MASTERY_KEYS}"
    available = get_available_points(pet)
    if available < points:
        return False, f"Not enough ability points. Have {available}, need {points}."

    if "advantage_mastery" not in pet or pet["advantage_mastery"] is None:
        pet["advantage_mastery"] = {k: 0 for k in ADVANTAGE_MASTERY_KEYS}
    pet["advantage_mastery"][key] = int(pet["advantage_mastery"].get(key, 0)) + points
    pet["ability_points"] = available - points

    new_bonus = get_advantage_mastery_bonus(pet, key)
    label = "Type" if key == "type" else "Element"
    return True, f"Spent {points} point(s) on {label} Advantage mastery. Bonus: +{new_bonus:.1f} to advantage multiplier"


# ── Ability helpers ───────────────────────────────────────────────────────────

def has_ability(pet: Dict[str, Any], ability_id: str) -> bool:
    """Check if pet has unlocked an ability (any level)."""
    abilities = pet.get("abilities") or {}
    return ability_id in abilities and abilities[ability_id] > 0


def get_ability_level(pet: Dict[str, Any], ability_id: str) -> int:
    """Get the current level of an ability (0 if not unlocked)."""
    abilities = pet.get("abilities") or {}
    return int(abilities.get(ability_id, 0))


def get_ability_effect_value(ability: Dict[str, Any], level: int) -> float:
    """Calculate the effect value for an ability at a given level."""
    effect = ability.get("effect", {})
    base = effect.get("base", 1.0)
    per_level = effect.get("per_level", 0.0)
    return base + (per_level * (level - 1))


def get_ability_effect(pet: Dict[str, Any], effect_type: str, source: Optional[str] = None, battle_type: Optional[str] = None, game: Optional[str] = None) -> float:
    """
    Accumulates all active ability effects of a given type.
    For multiplier effects returns the combined multiplier (multiplicative).
    For additive effects returns the sum.
    """
    # Effect types that are multiplicative (start at 1.0, multiply together)
    MULTIPLICATIVE_TYPES = {
        "battle_damage_mult", "battle_defense_mult", "survive_score_mult",
        "xp_multiplier", "speed_multiplier", "casino_xp_gain_mult",
        "critical_hit_multiplier",
    }
    is_multiplicative = (
        effect_type.endswith("_mult") or
        effect_type.endswith("_multiplier") or
        effect_type in MULTIPLICATIVE_TYPES
    )
    abilities = pet.get("abilities") or {}
    result = 1.0 if is_multiplicative else 0.0

    for ab in ABILITIES:
        ab_id = ab["id"]
        level = abilities.get(ab_id, 0)
        if level <= 0:
            continue
            
        eff = ab.get("effect", {})
        if eff.get("type") != effect_type:
            continue

        # Source filtering for xp_multiplier
        if effect_type == "xp_multiplier" and source is not None:
            ab_sources = eff.get("source", [])
            if source not in ab_sources:
                continue

        # Battle type filtering
        if battle_type is not None and eff.get("battle_type") != battle_type:
            continue
            
        # Casino game filtering
        if game is not None and eff.get("game") != game:
            continue

        val = get_ability_effect_value(ab, level)
        if is_multiplicative:
            result *= val
        else:
            result += val

    return result


def get_critical_hit_chance(pet: Dict[str, Any]) -> float:
    """Get the pet's critical hit chance (0.0-1.0)."""
    return get_ability_effect(pet, "critical_hit_chance")


def get_critical_hit_multiplier(pet: Dict[str, Any]) -> float:
    """Get the pet's critical hit damage multiplier (base 1.25x + bonuses)."""
    base_multiplier = 1.25  # Base critical hit multiplier
    bonus_multiplier = get_ability_effect(pet, "critical_hit_multiplier")
    return base_multiplier + (bonus_multiplier - 1.0) if bonus_multiplier > 1.0 else base_multiplier


def get_charge_vulnerability_reduction(pet: Dict[str, Any]) -> float:
    """Get the pet's charge vulnerability multiplier (base 1.25x - reductions).
    Each level of Charge Guard reduces the extra 0.25x vulnerability by 0.05 per level.
    Returns the final vulnerability multiplier (minimum 1.0 = no extra damage).
    """
    base_vulnerability = 1.25
    reduction = get_ability_effect(pet, "charge_vulnerability_reduction")
    return max(1.0, base_vulnerability - reduction) if reduction > 0 else base_vulnerability


def get_low_health_damage_reduction(pet: Dict[str, Any]) -> float:
    """Get damage reduction when below 25% health."""
    return get_ability_effect(pet, "low_health_damage_reduction")


def get_starting_charge_bonus(pet: Dict[str, Any]) -> int:
    """Get total starting charge bonus from Charged + Overcharged abilities."""
    charged_bonus = int(get_ability_effect(pet, "starting_charge_bonus"))
    overcharged_bonus = int(get_ability_effect(pet, "overcharged_bonus"))
    return charged_bonus + overcharged_bonus


# ── Point management ──────────────────────────────────────────────────────────

ABILITY_POINT_COST = 500  # Levels required to purchase 1 ability point

def get_available_points(pet: Dict[str, Any]) -> int:
    return int(pet.get("ability_points") or 0)


def can_purchase_ability_point(pet: Dict[str, Any]) -> bool:
    """Check if pet has enough levels to purchase an ability point."""
    current_level = int(pet.get("level", 1))
    return current_level >= ABILITY_POINT_COST


def purchase_ability_point(pet: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Purchase 1 ability point by spending 500 levels.
    Returns (success, message).

    Correctly reduces level, XP, AND stats so that apply_xp_change cannot
    recompute the level back up from stale XP on the next call.
    """
    current_level = int(pet.get("level", 1))
    if current_level < ABILITY_POINT_COST:
        return False, f"Need {ABILITY_POINT_COST} levels to purchase an ability point. Current level: {current_level}"
    
    # Import here to avoid circular imports
    from Systems.Pets.Logic.pet_brain import LootCalculator
    
    new_level = current_level - ABILITY_POINT_COST

    # Reduce stats using the scaling formula: 3 × (1+(level-1)//10) per level.
    # calculate_level_down_stats now uses this formula, matching calculate_level_up_stats
    # and add_pet_experience — consistent across the entire codebase.
    stat_losses = LootCalculator.calculate_level_down_stats(pet, current_level, new_level)

    # Apply the level change AND reset XP to 0 within the new level.
    # This is critical: if experience is not updated, apply_xp_change will
    # recompute total_xp = xp_for(new_level) + old_experience, which is
    # enough XP to push the level back up to current_level — undoing the
    # level deduction while the stat reduction sticks.
    pet["level"] = new_level
    pet["experience"] = 0

    # Award ability point
    current_points = get_available_points(pet)
    pet["ability_points"] = current_points + 1
    
    # Format stat losses for message
    loss_summary = ", ".join([f"{stat}: -{amount}" for stat, amount in stat_losses.items() if amount > 0])
    stat_message = f" (Stats reduced: {loss_summary})" if loss_summary else ""
    
    return True, f"Purchased 1 ability point for {ABILITY_POINT_COST} levels! New level: {new_level}, Ability points: {current_points + 1}{stat_message}"


def initialize_ability_tree(pet: Dict[str, Any]) -> None:
    """
    Initialize ability tree data on an existing pet if not already present.
    Called automatically by get_tree_state if needed.
    
    NOTE: Ability points are NOT auto-awarded. They must be purchased with levels.
    """
    if "ability_points" not in pet or pet["ability_points"] is None:
        pet["ability_points"] = 0  # Start with 0 points - must be purchased
    
    if "stat_mastery" not in pet or pet["stat_mastery"] is None:
        pet["stat_mastery"] = {s: 0 for s in STATS}

    if "advantage_mastery" not in pet or pet["advantage_mastery"] is None:
        pet["advantage_mastery"] = {k: 0 for k in ADVANTAGE_MASTERY_KEYS}
    
    if "abilities" not in pet or pet["abilities"] is None:
        pet["abilities"] = {}


def spend_stat_mastery(pet: Dict[str, Any], stat: str, points: int = 1) -> Tuple[bool, str]:
    """
    Spend `points` ability points on stat mastery for `stat`.
    Returns (success, message).
    """
    if stat not in STATS:
        return False, f"Unknown stat: {stat}"
    available = get_available_points(pet)
    if available < points:
        return False, f"Not enough ability points. Have {available}, need {points}."

    if "stat_mastery" not in pet or pet["stat_mastery"] is None:
        pet["stat_mastery"] = {s: 0 for s in STATS}
    pet["stat_mastery"][stat] = int(pet["stat_mastery"].get(stat, 0)) + points
    pet["ability_points"] = available - points

    new_mult = get_stat_mastery_multiplier(pet, stat)
    return True, f"Spent {points} point(s) on {stat} mastery. New multiplier: {new_mult:.1f}x"


def unlock_ability(pet: Dict[str, Any], ability_id: str) -> Tuple[bool, str]:
    """
    Unlock or upgrade an ability for the pet.
    Requires 1 point in the corresponding stat mastery first.
    Returns (success, message).
    """
    ab = ABILITY_BY_ID.get(ability_id)
    if not ab:
        return False, f"Unknown ability: {ability_id}"

    # Check stat mastery requirement
    stat = ab["stat"]
    mastery = pet.get("stat_mastery") or {}
    stat_points = int(mastery.get(stat, 0))
    if stat_points < 1:
        return False, f"Requires at least 1 point in {stat} stat mastery first."

    # Check special ability requirements (for Overcharged)
    if ab.get("requires_abilities"):
        required_abilities = ab["requires_abilities"]
        requires_max = ab.get("requires_max_level", False)
        
        for req_ability_id in required_abilities:
            req_level = get_ability_level(pet, req_ability_id)
            if requires_max:
                req_ab = ABILITY_BY_ID.get(req_ability_id)
                max_level = req_ab["max_level"] if req_ab else 5
                if req_level < max_level:
                    req_name = req_ab["name"] if req_ab else req_ability_id
                    return False, f"Requires {req_name} to be maxed out first."
            elif req_level < 1:
                req_ab = ABILITY_BY_ID.get(req_ability_id)
                req_name = req_ab["name"] if req_ab else req_ability_id
                return False, f"Requires {req_name} to be unlocked first."

    current_level = get_ability_level(pet, ability_id)
    max_level = ab["max_level"]
    
    # Special handling for Overcharged - can't exceed Charge Mastery level
    if ability_id == "ene_overcharged":
        charge_mastery_level = get_ability_level(pet, "ene_charge_mastery")
        if current_level >= charge_mastery_level:
            return False, f"Overcharged cannot exceed Charge Mastery level ({charge_mastery_level})."
    
    if current_level >= max_level:
        return False, f"{ab['name']} is already at maximum level ({max_level})."

    cost = ab["cost"]
    available = get_available_points(pet)
    if available < cost:
        return False, f"Not enough ability points. Have {available}, need {cost}."

    if "abilities" not in pet or pet["abilities"] is None:
        pet["abilities"] = {}
    
    new_level = current_level + 1
    pet["abilities"][ability_id] = new_level
    pet["ability_points"] = available - cost

    # Calculate effect value for display
    effect_value = get_ability_effect_value(ab, new_level)
    
    # Format the effect value for display
    if ab["effect"]["type"].endswith("_mult") or ab["effect"]["type"].endswith("_multiplier"):
        if ab["effect"]["type"] == "battle_defense_mult":
            # Defense is shown as damage reduction percentage (boost above 1.0)
            boost_pct = int((effect_value - 1.0) * 100)
            formatted_value = f"{boost_pct}%"
        elif ab["effect"]["type"] == "battle_damage_mult":
            # Damage is shown as bonus percentage above 1.0
            bonus_pct = int((effect_value - 1.0) * 100)
            formatted_value = f"{bonus_pct}%"
        elif ab["effect"]["type"] == "xp_multiplier":
            # XP multiplier shown as bonus percentage above 1.0
            bonus_pct = int((effect_value - 1.0) * 100)
            formatted_value = f"{bonus_pct}%"
        elif ab["effect"]["type"] == "casino_xp_gain_mult":
            # Casino win bonus shown as bonus percentage above 1.0
            bonus_pct = int((effect_value - 1.0) * 100)
            formatted_value = f"{bonus_pct}%"
        else:
            formatted_value = f"{effect_value:.1f}"
    elif ab["effect"]["type"] in ["casino_xp_loss_reduction", "battle_health_bonus", "low_health_damage_reduction", "charge_vulnerability_reduction"]:
        # Show as percentage
        formatted_value = f"{int(effect_value * 100)}%"
    elif ab["effect"]["type"] in ["charge_limit_bonus", "starting_charge_bonus", "overcharged_bonus"]:
        # Show as flat number
        formatted_value = str(int(effect_value))
    elif ab["effect"]["type"] == "critical_hit_chance":
        # Show as percentage
        formatted_value = f"{int(effect_value * 100)}%"
    else:
        formatted_value = f"{effect_value:.1f}"

    action = "Upgraded" if current_level > 0 else "Unlocked"
    description = ab['description'].format(level=new_level, value=formatted_value)
    
    return True, f"{action} **{ab['name']}** to level {new_level}! {description}"


# ── Tree state serialiser (for API response) ─────────────────────────────────

def get_tree_state(pet: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns the full tree state for the frontend:
      - available_points
      - can_purchase_point (bool)
      - current_level
      - point_cost (500)
      - stat_mastery: {stat: {points, multiplier}}
      - abilities: {id: {current_level, max_level, can_upgrade, stat_mastery_met, requirements_met, ...ability_data}}
    """
    # Initialize ability tree data if not present
    initialize_ability_tree(pet)
    
    available = get_available_points(pet)
    current_level = int(pet.get("level", 1))
    can_purchase = can_purchase_ability_point(pet)
    
    mastery_state: Dict[str, Any] = {}
    for s in STATS:
        pts = int((pet.get("stat_mastery") or {}).get(s, 0))
        mastery_state[s] = {
            "points": pts,
            "multiplier": round(1.0 + pts * 0.1, 2),
        }

    adv_mastery_state: Dict[str, Any] = {}
    for k in ADVANTAGE_MASTERY_KEYS:
        pts = int((pet.get("advantage_mastery") or {}).get(k, 0))
        adv_mastery_state[k] = {
            "points": pts,
            "bonus": round(pts * 0.1, 2),
        }

    abilities_state: Dict[str, Any] = {}
    for ab in ABILITIES:
        ab_id = ab["id"]
        current_ab_level = get_ability_level(pet, ab_id)
        max_level = ab["max_level"]
        
        # Check stat mastery requirement
        stat = ab["stat"]
        stat_mastery_points = int((pet.get("stat_mastery") or {}).get(stat, 0))
        stat_mastery_met = stat_mastery_points >= 1
        
        # Check special ability requirements
        requirements_met = True
        requirement_text = ""
        if ab.get("requires_abilities"):
            required_abilities = ab["requires_abilities"]
            requires_max = ab.get("requires_max_level", False)
            
            for req_ability_id in required_abilities:
                req_level = get_ability_level(pet, req_ability_id)
                req_ab = ABILITY_BY_ID.get(req_ability_id)
                req_name = req_ab["name"] if req_ab else req_ability_id
                
                if requires_max:
                    req_max_level = req_ab["max_level"] if req_ab else 5
                    if req_level < req_max_level:
                        requirements_met = False
                        requirement_text = f"Requires {req_name} maxed"
                        break
                elif req_level < 1:
                    requirements_met = False
                    requirement_text = f"Requires {req_name}"
                    break
        
        # Special handling for Overcharged level cap
        effective_max_level = max_level
        if ab_id == "ene_overcharged":
            charge_mastery_level = get_ability_level(pet, "ene_charge_mastery")
            effective_max_level = min(max_level, charge_mastery_level)
        
        can_upgrade = (current_ab_level < effective_max_level) and stat_mastery_met and requirements_met and (available >= ab["cost"])
        
        # Calculate current effect value for display
        if current_ab_level > 0:
            effect_value = get_ability_effect_value(ab, current_ab_level)
        else:
            effect_value = get_ability_effect_value(ab, 1)  # Show level 1 preview
        
        # Format the effect value for display
        if ab["effect"]["type"].endswith("_mult") or ab["effect"]["type"].endswith("_multiplier"):
            if ab["effect"]["type"] == "battle_defense_mult":
                # Defense is shown as damage reduction percentage (boost above 1.0)
                boost_pct = int((effect_value - 1.0) * 100)
                formatted_value = f"{boost_pct}%"
            elif ab["effect"]["type"] == "battle_damage_mult":
                # Damage is shown as bonus percentage above 1.0
                bonus_pct = int((effect_value - 1.0) * 100)
                formatted_value = f"{bonus_pct}%"
            elif ab["effect"]["type"] == "xp_multiplier":
                # XP multiplier shown as bonus percentage above 1.0
                bonus_pct = int((effect_value - 1.0) * 100)
                formatted_value = f"{bonus_pct}%"
            elif ab["effect"]["type"] == "casino_xp_gain_mult":
                # Casino win bonus shown as bonus percentage above 1.0
                bonus_pct = int((effect_value - 1.0) * 100)
                formatted_value = f"{bonus_pct}%"
            else:
                formatted_value = f"{effect_value:.1f}"
        elif ab["effect"]["type"] in ["casino_xp_loss_reduction", "battle_health_bonus", "low_health_damage_reduction", "charge_vulnerability_reduction"]:
            # Show as percentage
            formatted_value = f"{int(effect_value * 100)}%"
        elif ab["effect"]["type"] in ["charge_limit_bonus", "starting_charge_bonus", "overcharged_bonus"]:
            # Show as flat number
            formatted_value = str(int(effect_value))
        elif ab["effect"]["type"] == "critical_hit_chance":
            # Show as percentage
            formatted_value = f"{int(effect_value * 100)}%"
        else:
            formatted_value = f"{effect_value:.1f}"
        
        abilities_state[ab_id] = {
            **ab,
            "current_level": current_ab_level,
            "effective_max_level": effective_max_level,
            "can_upgrade": can_upgrade,
            "stat_mastery_met": stat_mastery_met,
            "requirements_met": requirements_met,
            "requirement_text": requirement_text,
            "formatted_value": formatted_value,
        }

    return {
        "available_points": available,
        "can_purchase_point": can_purchase,
        "current_level": current_level,
        "point_cost": ABILITY_POINT_COST,
        "stat_mastery": mastery_state,
        "advantage_mastery": adv_mastery_state,
        "abilities": abilities_state,
    }
