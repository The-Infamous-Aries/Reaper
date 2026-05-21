"""
GPP Component Pattern — Pet System
====================================
Breaks pet logic into reusable, composable components instead of one
monolithic class.  Each component owns a single concern:

  StatsComponent      — stat calculation, equipment bonuses, mastery
  AnimationComponent  — produces animation metadata for the frontend
  StateComponent      — tracks what the pet is currently doing
  InventoryComponent  — inventory queries and mutations
  CombatComponent     — combat stat derivation and action-label lookup

Components are stateless helpers that operate on a pet dict.
They do NOT persist data — callers are responsible for saving.

Usage:
    from Systems.Pets.Logic.pet_components import (
        StatsComponent, AnimationComponent, StateComponent,
        InventoryComponent, CombatComponent
    )

    stats  = StatsComponent.get_totals(pet)
    anim   = AnimationComponent.for_train(stat, success, delta)
    state  = StateComponent.get(pet)
    StateComponent.set(pet, "training")
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# StatsComponent
# ─────────────────────────────────────────────────────────────────────────────

class StatsComponent:
    """Read-only stat queries on a pet dict."""

    STAT_KEYS = ("ATT", "DEF", "INT", "DEX", "HAP", "ENE")

    @staticmethod
    def get_base(pet: Dict[str, Any]) -> Dict[str, int]:
        """Return the six raw base stats (no equipment, no mastery)."""
        return {k: int(pet.get(k, 0)) for k in StatsComponent.STAT_KEYS}

    @staticmethod
    def get_totals(pet: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return fully-computed stats including equipment bonuses, mastery
        multipliers, and derived combat values.
        Delegates to the existing StatsCalculator to avoid duplication.
        """
        from Systems.Pets.Logic.pet_brain import StatsCalculator
        return StatsCalculator.calculate_pet_stats(pet)

    @staticmethod
    def get_equipment_multiplier(pet: Dict[str, Any]) -> float:
        """Return the XP/stat equipment multiplier for this pet."""
        from Systems.Pets.Logic.pet_brain import StatsCalculator
        return StatsCalculator.get_equipment_xp_multiplier(pet)

    @staticmethod
    def get_specializations(pet: Dict[str, Any]) -> List[str]:
        """Return the list of specialised stat keys for this pet."""
        return list(pet.get("specializations") or pet.get("Spec") or [])

    @staticmethod
    def is_specialised(pet: Dict[str, Any], stat: str) -> bool:
        return stat in StatsComponent.get_specializations(pet)

    @staticmethod
    def stat_delta_description(stat: str, old_val: int, new_val: int) -> str:
        """Human-readable description of a stat change."""
        delta = new_val - old_val
        sign  = "+" if delta >= 0 else ""
        return f"{stat}: {old_val} → {new_val} ({sign}{delta})"


# ─────────────────────────────────────────────────────────────────────────────
# AnimationComponent
# ─────────────────────────────────────────────────────────────────────────────

class AnimationComponent:
    """
    Produces animation metadata dicts that the frontend game loop consumes.

    Each dict has:
        type        str   — animation identifier
        duration_ms int   — how long the animation should play
        data        dict  — animation-specific payload
    """

    # ── Train ─────────────────────────────────────────────────────────────────

    @staticmethod
    def for_train(stat: str, success: bool, delta: int) -> Dict[str, Any]:
        return {
            "type":        "train_result",
            "duration_ms": 800,
            "data": {
                "stat":    stat,
                "success": success,
                "delta":   delta,
                # Particle colour per stat
                "color":   AnimationComponent._stat_color(stat),
                # Which particle effect to play
                "effect":  "sparkle_up" if success else "shake_down",
            },
        }

    # ── Mission ───────────────────────────────────────────────────────────────

    @staticmethod
    def for_mission(success: bool, xp: int, difficulty: str) -> Dict[str, Any]:
        return {
            "type":        "mission_result",
            "duration_ms": 1200,
            "data": {
                "success":    success,
                "xp":         xp,
                "difficulty": difficulty,
                "effect":     "xp_burst" if success else "fail_flash",
                "color":      "#2ecc71" if success else "#e74c3c",
            },
        }

    # ── Play ──────────────────────────────────────────────────────────────────

    @staticmethod
    def for_play(location: str, xp: int, element: str, element2: Optional[str] = None) -> Dict[str, Any]:
        return {
            "type":        "play_result",
            "duration_ms": 1000,
            "data": {
                "location":  location,
                "xp":        xp,
                "element":   element,
                "element2":  element2,
                "effect":    "float_up",
                "color":     AnimationComponent._element_color(element),
            },
        }

    # ── Level up / down ───────────────────────────────────────────────────────

    @staticmethod
    def for_level_up(old_level: int, new_level: int, gains: Dict[str, int]) -> Dict[str, Any]:
        return {
            "type":        "level_up",
            "duration_ms": 2000,
            "data": {
                "old_level": old_level,
                "new_level": new_level,
                "gains":     gains,
                "effect":    "level_burst",
                "color":     "#ffd700",
            },
        }

    @staticmethod
    def for_level_down(old_level: int, new_level: int, losses: Dict[str, int]) -> Dict[str, Any]:
        return {
            "type":        "level_down",
            "duration_ms": 1500,
            "data": {
                "old_level": old_level,
                "new_level": new_level,
                "losses":    losses,
                "effect":    "level_drop",
                "color":     "#e74c3c",
            },
        }

    # ── XP bar ────────────────────────────────────────────────────────────────

    @staticmethod
    def for_xp_change(old_xp: int, new_xp: int, max_xp: int) -> Dict[str, Any]:
        old_pct = min(old_xp / max(max_xp, 1), 1.0) * 100
        new_pct = min(new_xp / max(max_xp, 1), 1.0) * 100
        return {
            "type":        "xp_bar",
            "duration_ms": 600,
            "data": {
                "old_pct": round(old_pct, 2),
                "new_pct": round(new_pct, 2),
                "old_xp":  old_xp,
                "new_xp":  new_xp,
                "max_xp":  max_xp,
            },
        }

    # ── Loot ──────────────────────────────────────────────────────────────────

    @staticmethod
    def for_loot(items: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "type":        "loot_drop",
            "duration_ms": 1500,
            "data": {
                "items":  [{"name": i.get("name"), "rarity": i.get("rarity", "Common")} for i in items],
                "effect": "chest_open",
            },
        }

    # ── Battle ────────────────────────────────────────────────────────────────

    @staticmethod
    def for_battle_action(
        action: str,
        damage: int,
        is_player: bool,
        element_mult: float = 1.0,
    ) -> Dict[str, Any]:
        effect = "attack_hit"
        if action == "defend":
            effect = "shield_block"
        elif action == "charge":
            effect = "charge_glow"
        elif element_mult > 1.0:
            effect = "super_effective"
        elif element_mult < 1.0:
            effect = "not_effective"

        return {
            "type":        "battle_action",
            "duration_ms": 400,
            "data": {
                "action":       action,
                "damage":       damage,
                "is_player":    is_player,
                "element_mult": element_mult,
                "effect":       effect,
            },
        }

    # ── UI Update (generic) ───────────────────────────────────────────────────

    @staticmethod
    def for_ui_update(effect: str, duration_ms: int = 500, extra_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Generic UI update animation for simple feedback effects.
        Used for actions that don't have specific animation types.

        Args:
            effect: The effect name to play
            duration_ms: Animation duration in milliseconds
            extra_data: Optional additional data to include in the animation payload
        """
        data = {"effect": effect}
        if extra_data:
            data.update(extra_data)
        return {
            "type": "ui_update",
            "duration_ms": duration_ms,
            "data": data
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _stat_color(stat: str) -> str:
        return {
            "ATT": "#e74c3c",
            "DEF": "#3498db",
            "INT": "#9b59b6",
            "DEX": "#1abc9c",
            "HAP": "#f39c12",
            "ENE": "#2ecc71",
        }.get(stat, "#ffd700")

    @staticmethod
    def _element_color(element: str) -> str:
        return {
            "fire":     "#e74c3c",
            "water":    "#3498db",
            "electric": "#f1c40f",
            "ice":      "#a8d8ea",
            "plant":    "#2ecc71",
            "rock":     "#95a5a6",
            "air":      "#bdc3c7",
            "magic":    "#9b59b6",
            "holy":     "#f39c12",
            "necro":    "#8e44ad",
            "psychic":  "#e91e63",
            "fighting": "#e67e22",
        }.get((element or "basic").lower(), "#aaa")


# ─────────────────────────────────────────────────────────────────────────────
# StateComponent
# ─────────────────────────────────────────────────────────────────────────────

# Valid pet activity states
PET_STATES = frozenset({
    "idle",
    "training",
    "on_mission",
    "playing",
    "on_quest",
    "in_battle",
    "in_dungeon",
    "in_colosseum",
})

class StateComponent:
    """
    Tracks what the pet is currently doing.
    State is stored directly on the pet dict under "activity_state".
    """

    @staticmethod
    def get(pet: Dict[str, Any]) -> str:
        return pet.get("activity_state", "idle")

    @staticmethod
    def set(pet: Dict[str, Any], state: str) -> None:
        if state not in PET_STATES:
            raise ValueError(f"Unknown pet state '{state}'. Valid: {PET_STATES}")
        pet["activity_state"] = state

    @staticmethod
    def reset(pet: Dict[str, Any]) -> None:
        pet["activity_state"] = "idle"

    @staticmethod
    def is_busy(pet: Dict[str, Any]) -> bool:
        return StateComponent.get(pet) != "idle"

    @staticmethod
    def can_train(pet: Dict[str, Any]) -> bool:
        return StateComponent.get(pet) == "idle"

    @staticmethod
    def can_mission(pet: Dict[str, Any]) -> bool:
        return StateComponent.get(pet) == "idle"

    @staticmethod
    def can_play(pet: Dict[str, Any]) -> bool:
        return StateComponent.get(pet) == "idle"

    @staticmethod
    def can_battle(pet: Dict[str, Any]) -> bool:
        return StateComponent.get(pet) in ("idle", "playing")


# ─────────────────────────────────────────────────────────────────────────────
# InventoryComponent
# ─────────────────────────────────────────────────────────────────────────────

class InventoryComponent:
    """Read-only inventory queries on a pet dict."""

    @staticmethod
    def get_all(pet: Dict[str, Any]) -> List[Dict[str, Any]]:
        return list(pet.get("inventory") or [])

    @staticmethod
    def count(pet: Dict[str, Any], item_name: str) -> int:
        total = 0
        for item in InventoryComponent.get_all(pet):
            if item.get("name", "").lower() == item_name.lower():
                total += int(item.get("count", 1))
        return total

    @staticmethod
    def has(pet: Dict[str, Any], item_name: str, quantity: int = 1) -> bool:
        return InventoryComponent.count(pet, item_name) >= quantity

    @staticmethod
    def get_by_type(pet: Dict[str, Any], item_type: str) -> List[Dict[str, Any]]:
        return [
            i for i in InventoryComponent.get_all(pet)
            if i.get("type", "").lower() == item_type.lower()
        ]

    @staticmethod
    def get_keys(pet: Dict[str, Any]) -> Dict[str, int]:
        """Return {Key1: count, Key2: count, Key3: count}."""
        result = {"Key1": 0, "Key2": 0, "Key3": 0}
        for item in InventoryComponent.get_all(pet):
            if item.get("type") == "Key" and item.get("name") in result:
                result[item["name"]] += int(item.get("count", 1))
        return result

    @staticmethod
    def total_items(pet: Dict[str, Any]) -> int:
        return sum(int(i.get("count", 1)) for i in InventoryComponent.get_all(pet))

    @staticmethod
    def group_by_type(pet: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        groups: Dict[str, List] = {}
        for item in InventoryComponent.get_all(pet):
            t = item.get("type", "Other")
            groups.setdefault(t, []).append(item)
        return groups


# ─────────────────────────────────────────────────────────────────────────────
# CombatComponent
# ─────────────────────────────────────────────────────────────────────────────

class CombatComponent:
    """Derived combat values and action-label helpers."""

    @staticmethod
    def get_action_labels(pet: Dict[str, Any]) -> Dict[str, str]:
        """
        Return the three battle action labels for this pet, respecting
        custom labels set by the player.
        """
        from Systems.Pets.Logic.damage_calculator import DamageCalculator
        category = str(pet.get("category") or pet.get("type") or "land").lower()
        element  = str(pet.get("element") or "basic").lower()
        species  = str(pet.get("species") or "").strip()
        custom   = pet.get("action_labels") or {}
        return DamageCalculator.get_action_labels(category, element, species, custom_labels=custom)

    @staticmethod
    def get_attack(pet: Dict[str, Any]) -> int:
        return int(StatsComponent.get_totals(pet).get("attack", 0))

    @staticmethod
    def get_defense(pet: Dict[str, Any]) -> int:
        return int(StatsComponent.get_totals(pet).get("defense", 0))

    @staticmethod
    def get_max_health(pet: Dict[str, Any]) -> int:
        return int(StatsComponent.get_totals(pet).get("max_health", 1))

    @staticmethod
    def get_element_style(pet: Dict[str, Any]) -> Tuple[int, str]:
        """Return (embed_color_int, element_emoji) for this pet."""
        element  = str(pet.get("element") or "basic").lower()
        element2 = str(pet.get("element2") or "").lower()
        from Systems.Pets.Logic.loot_calculator import LootCalculator
        color_map = {
            "basic": 0x808080, "fire": 0xFF4500, "water": 0x1E90FF,
            "electric": 0xFFD700, "ice": 0x87CEEB, "plant": 0x228B22,
            "rock": 0x8B4513, "air": 0xADD8E6, "magic": 0x4B0082,
            "holy": 0xEEE8AA, "necro": 0x800080, "psychic": 0x9932CC,
            "fighting": 0xCD5C5C,
        }
        c1 = color_map.get(element, 0x808080)
        if element2 and element2 not in ("basic", "none", "") and element2 != element:
            c2 = color_map.get(element2, 0x808080)
            r = ((c1 >> 16) & 0xFF + (c2 >> 16) & 0xFF) // 2
            g = ((c1 >> 8)  & 0xFF + (c2 >> 8)  & 0xFF) // 2
            b = (c1 & 0xFF + c2 & 0xFF) // 2
            final_color = (r << 16) | (g << 8) | b
        else:
            final_color = c1
        emoji = LootCalculator.get_pet_emoji("Elements", element) or ""
        return final_color, emoji
