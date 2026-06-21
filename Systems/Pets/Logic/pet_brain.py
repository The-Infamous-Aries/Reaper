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

# ---------------------------------------------------------------------------
# Re-export stripped classes so all existing imports still work
# ---------------------------------------------------------------------------
from Systems.Pets.Logic.loot_calculator import LootCalculator
from Systems.Pets.Logic.damage_calculator import DamageCalculator
from Systems.Pets.Logic.npc_brain import NPCBrain


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
    def _get_equipment_state(pet_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract equipment state (filled slots, set match, ring sub-bonuses, full set).
        Shared by _calculate_equipment_bonuses and get_equipment_xp_multiplier.

        Returns:
            {
                "main_filled": int,
                "matching_set": bool,
                "ring_sub_bonus": int,
                "full_set": bool,
                "level_bonus": int,
                "all_items": List[Dict]  # All equipment items for bonus accumulation
            }
        """
        equipment = pet_data.get('equipment') or {}
        level = int(pet_data.get('level', 1))
        level_bonus = level // 50  # +1 per 50 levels

        # ── Helper: get item from slot (handles list or dict) ─────────────────
        def _get_single(slot_key: str) -> Optional[Dict]:
            v = equipment.get(slot_key)
            if isinstance(v, list): v = v[0] if v else None
            return v if isinstance(v, dict) and v.get('name') else None

        def _get_list(slot_key: str) -> List[Dict]:
            v = equipment.get(slot_key, [])
            if isinstance(v, dict): v = [v] if v.get('name') else []
            return [i for i in v if isinstance(i, dict) and i.get('name')]

        # ── Collect main slots ────────────────────────────────────────────────
        helmet  = _get_single('Helmet')
        armor   = _get_single('Armor')
        boots   = _get_single('Boots')
        ring    = _get_single('Ring')
        shield  = _get_single('Shield')
        weapon  = _get_single('Weapon')

        main_slots = [helmet, armor, boots, ring, shield, weapon]
        main_filled = [s for s in main_slots if s is not None]

        # ── Collect ring sub-slots ────────────────────────────────────────────
        material = _get_single('Material')
        monsters = _get_list('Monsters')   # up to 2
        gems     = _get_list('Gems')       # up to 2

        # ── Determine set match ───────────────────────────────────────────────
        def _set_tag(item: Optional[Dict]) -> Optional[str]:
            if not item: return None
            # Reforged items may not have the set tag stored; fall back to canonical
            tag = item.get('set') or None
            if not tag:
                try:
                    canonical = user_data_manager.file_manager.get_equipment_item(item.get('name', ''))
                    tag = (canonical.get('set') if canonical else None) or None
                except Exception:
                    pass
            return tag

        # Set bonus: Helmet + Armor + Boots + Shield + Weapon only (Ring excluded)
        set_slots = [helmet, armor, boots, shield, weapon]
        set_slots_filled = [s for s in set_slots if s is not None]
        main_set_tags = [_set_tag(s) for s in set_slots_filled if _set_tag(s)]
        matching_set = (
            len(set_slots_filled) == 5 and
            len(main_set_tags) == 5 and
            len(set(main_set_tags)) == 1
        )

        # ── Ring sub-slot bonuses ─────────────────────────────────────────────
        mon_names = [(m.get('name') or '').lower() for m in monsters]
        gem_names = [(g.get('name') or '').lower() for g in gems]
        matching_monsters = len(mon_names) == 2 and mon_names[0] == mon_names[1]
        matching_gems     = len(gem_names) == 2 and gem_names[0] == gem_names[1]
        has_material      = material is not None

        ring_sub_bonus = (1 if matching_monsters else 0) + \
                         (1 if matching_gems else 0) + \
                         (1 if has_material else 0)

        # ── Full set check ────────────────────────────────────────────────────
        full_set = (
            matching_set and
            ring is not None and
            has_material and
            matching_monsters and
            matching_gems
        )

        # Collect all items for bonus accumulation
        all_items = main_filled + ([material] if material else []) + monsters + gems

        return {
            "main_filled": len(main_filled),
            "matching_set": matching_set,
            "ring_sub_bonus": ring_sub_bonus,
            "full_set": full_set,
            "level_bonus": level_bonus,
            "all_items": all_items,
        }

    @staticmethod
    def _calculate_equipment_bonuses(pet_data: Dict[str, Any]) -> Dict[str, int]:
        """
        New equipment system:
          Main slots: Helmet, Armor, Boots, Ring, Shield, Weapon (1 each)
          Ring sub-slots: Material (1), Monsters (2), Gems (2)

        Multiplier rules (per slot):
          - Each main slot filled:          +1 to level_mult
          - Matching set (all 6 share set): +3 bonus
          - Ring sub-slots:
              +1 if matching monsters (both same name)
              +1 if matching gems (both same name)
              +1 if material equipped
          - Every 50 levels:                +1 to level_mult
          - Full set (all 6 main + all ring sub-slots filled + matching ring items):
              ALL bonuses DOUBLED after level multiplier

        Each item's bonuses are multiplied by its own per-item multiplier
        (level_mult), then the full-set doubling is applied on top.
        """
        equipment = pet_data.get('equipment') or {}
        if not equipment:
            return {k: 0 for k in ['ATT', 'DEF', 'INT', 'DEX', 'HAP', 'ENE']}

        # ── Use shared equipment state calculation ────────────────────────────
        state = StatsCalculator._get_equipment_state(pet_data)

        STATS = ['ATT', 'DEF', 'INT', 'DEX', 'HAP', 'ENE']
        raw_bonuses = {k: 0 for k in STATS}

        # ── Accumulate raw bonuses from all items ───────────────────────────────
        for item in state['all_items']:
            for stat, val in (item.get('bonuses') or {}).items():
                if stat in raw_bonuses:
                    try: raw_bonuses[stat] += int(val)
                    except (TypeError, ValueError): pass

        # ── Per-item level multiplier ─────────────────────────────────────────
        # Base = slots filled + set bonus + ring sub bonus + level bonus
        slots_filled_bonus = state['main_filled']  # +1 per filled main slot
        set_bonus = 3 if state['matching_set'] else 0
        base_mult = slots_filled_bonus + set_bonus + state['ring_sub_bonus'] + state['level_bonus']
        if base_mult < 1:
            base_mult = 1

        # ── Apply multiplier ──────────────────────────────────────────────────
        result = {stat: raw_bonuses[stat] * base_mult for stat in STATS}

        # ── Full set doubling (applied after level multiplier) ────────────────
        if state['full_set']:
            result = {stat: result[stat] * 2 for stat in STATS}

        return result

    @staticmethod
    def get_equipment_xp_multiplier(pet_data: Dict[str, Any]) -> float:
        """
        XP multiplier from equipment — mirrors _calculate_equipment_bonuses rules.

        Base = slots_filled + set_bonus(3) + ring_sub_bonus + level_bonus
        Full set (all 6 matching + all ring sub-slots): doubled.
        """
        equipment = pet_data.get('equipment') or {}
        level = int(pet_data.get('level', 1))
        level_bonus = level // 50

        if not equipment:
            return 1.0 + level_bonus

        # ── Use shared equipment state calculation ────────────────────────────
        state = StatsCalculator._get_equipment_state(pet_data)

        slots_filled_bonus = state['main_filled']
        set_bonus = 3 if state['matching_set'] else 0
        base_mult = float(slots_filled_bonus + set_bonus + state['ring_sub_bonus'] + state['level_bonus'])
        if base_mult < 1.0:
            base_mult = 1.0

        return base_mult * 2.0 if state['full_set'] else base_mult

    @staticmethod
    def _build_effective_stats(pet_data: Dict[str, Any]) -> Dict[str, int]:
        """
        Internal helper: base stats + equipment bonuses + stat mastery multipliers.
        Does NOT recurse into calculate_max_health — safe to call from anywhere.
        """
        stats = {
            'ATT': int(pet_data.get('ATT') or 0),
            'DEF': int(pet_data.get('DEF') or 0),
            'INT': int(pet_data.get('INT') or 0),
            'DEX': int(pet_data.get('DEX') or 0),
            'HAP': int(pet_data.get('HAP') or 0),
            'ENE': int(pet_data.get('ENE') or 0),
        }

        bonuses = StatsCalculator._calculate_equipment_bonuses(pet_data)
        for stat in stats:
            stats[stat] += bonuses.get(stat, 0)

        try:
            from Systems.Pets.Logic.ability_tree import get_all_mastery_multipliers
            multipliers = get_all_mastery_multipliers(pet_data)
            for stat in stats:
                if stat in multipliers:
                    stats[stat] = int(stats[stat] * multipliers[stat])
        except Exception:
            pass

        return stats

    @staticmethod
    def calculate_pet_stats(pet_data: Dict[str, Any]) -> Dict[str, int]:
        """
        Calculate total stats including base stats, equipment bonuses, and stat mastery
        multipliers. Returns a dict with base stats (ATT, DEF, etc.) and computed
        combat stats (attack, defense, max_health).
        """
        stats = StatsCalculator._build_effective_stats(pet_data)

        stats['attack'] = StatsCalculator.calculate_computed_attack(stats['ATT'], stats['DEX'])
        stats['defense'] = StatsCalculator.calculate_computed_defense(stats['DEF'], stats['INT'])
        # Compute max_health from the already-resolved stats to avoid re-entering
        # the full pipeline (which would cause infinite recursion via
        # calculate_max_health → calculate_pet_stats → calculate_max_health).
        stats['max_health'] = StatsCalculator._compute_health_from_stats(stats, pet_data)

        return stats

    @staticmethod
    def _compute_health_from_stats(
        stats: Dict[str, int],
        pet_data: Dict[str, Any],
    ) -> int:
        """
        Compute raw health from an already-resolved stats dict (no re-entry).
        Formula: (HAP + ENE) * (equip_mult * 4)
        Applies battle_health_bonus from abilities on top.
        """
        hap = stats.get('HAP', 0)
        ene = stats.get('ENE', 0)
        equip_mult = StatsCalculator.get_equipment_xp_multiplier(pet_data)
        base_health = int((hap + ene) * (equip_mult * 4))

        # Apply battle_health_bonus from hap_battle_health + ene_battle_stamina
        try:
            from Systems.Pets.Logic.ability_tree import get_ability_effect
            health_bonus = get_ability_effect(pet_data, "battle_health_bonus")
            if health_bonus > 0:
                base_health = int(base_health * (1.0 + health_bonus))
        except Exception:
            pass

        return max(1, base_health)

    @staticmethod
    def calculate_max_health(pet_data: Dict[str, Any], user_id: Optional[str] = None) -> int:
        """
        Calculate max health for a pet.

        Priority order:
          1. User's custom formula (if user_id provided and formula is active)
          2. Battle scaling (logarithmic, for high-level pets)
          3. Original formula: (HAP + ENE) * (equip_mult * 4) × ability bonus

        All paths apply battle_health_bonus from abilities.
        """
        level = int(pet_data.get('level', 1))

        # ── 1. Custom user formula ────────────────────────────────────────────
        if user_id:
            try:
                from Systems.Pets.Logic.user_battle_settings import UserBattleSettings
                user_formula = UserBattleSettings.get_user_formula(user_id)
                if not user_formula.use_original_scaling:
                    # calculate_custom_health calls calculate_pet_stats which calls
                    # _compute_health_from_stats — no recursion back here.
                    return UserBattleSettings.calculate_custom_health(pet_data, user_formula)
            except Exception:
                pass

        # ── Resolve effective stats once (shared by paths 2 & 3) ─────────────
        stats = StatsCalculator._build_effective_stats(pet_data)

        # ── 2. Battle scaling (high-level logarithmic) ────────────────────────
        try:
            from Systems.Pets.Logic.battle_scaling import should_use_battle_scaling, BattleScaler
            if should_use_battle_scaling(level, level):
                equipment_mult = StatsCalculator.get_equipment_xp_multiplier(pet_data)
                # BattleScaler applies mastery internally via mastery_multipliers kwarg,
                # but we've already applied mastery in _build_effective_stats, so pass
                # empty dict to avoid double-application.
                scaled = BattleScaler.calculate_scaled_health(
                    stats, level, equipment_mult, {}
                )
                # Apply battle_health_bonus on top of scaled result
                try:
                    from Systems.Pets.Logic.ability_tree import get_ability_effect
                    health_bonus = get_ability_effect(pet_data, "battle_health_bonus")
                    if health_bonus > 0:
                        scaled = int(scaled * (1.0 + health_bonus))
                except Exception:
                    pass
                return max(1, scaled)
        except Exception:
            pass

        # ── 3. Original formula ───────────────────────────────────────────────
        return StatsCalculator._compute_health_from_stats(stats, pet_data)
