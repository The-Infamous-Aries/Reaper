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
    def _calculate_equipment_bonuses(pet_data: Dict[str, Any]) -> Dict[str, int]:
        """
        Calculate raw equipment bonuses with set/pair/hat-spec multipliers.

        Multiplier rules — the global multiplier is determined first, then
        applied to the TOTAL sum of all equipped item bonuses:
          - No pairs, no full set          → 1×  (+ level bonus)
          - Any duplicate pair             → 2×  (+ level bonus) on entire pool
          - Full set (mat pair + gem pair
            + mon pair + hat equipped)     → 3×  (+ level bonus) on entire pool
          - Full set + both hat bonus stats
            match pet specs                → 4×  (+ level bonus) on entire pool
          - Every 50 levels                → +1 added to the final multiplier
            (so level 100 full-set+both = 6×, etc.)

        All item bonuses are summed raw first, then the single final_mult is
        applied to the whole pool — so a 6× multiplier hits every point from
        every equipped item equally.
        """
        equipment = pet_data.get('equipment') or {}
        if not equipment:
            return {k: 0 for k in ['ATT', 'DEF', 'INT', 'DEX', 'HAP', 'ENE']}

        level = int(pet_data.get('level', 1))
        try:
            specs = [s.upper() for s in LootCalculator._get_pet_specs(pet_data)]
        except Exception:
            specs = []
        level_bonus = level // 50  # +1 per 50 levels

        # ── Collect typed items ───────────────────────────────────────────────
        items = []  # list of (type_key, item_dict)
        mat = equipment.get('Material')
        if isinstance(mat, list):
            for m in mat:
                if isinstance(m, dict) and m.get('name'): items.append(('Material', m))
        elif isinstance(mat, dict) and mat.get('name'):
            items.append(('Material', mat))
        gems = equipment.get('Gems', [])
        if isinstance(gems, list):
            for g in gems:
                if isinstance(g, dict) and g.get('name'): items.append(('Gem', g))
        elif isinstance(gems, dict) and gems.get('name'):
            items.append(('Gem', gems))
        mons = equipment.get('Monsters', [])
        if isinstance(mons, list):
            for m in mons:
                if isinstance(m, dict) and m.get('name'): items.append(('Monster', m))
        elif isinstance(mons, dict) and mons.get('name'):
            items.append(('Monster', mons))
        hat = equipment.get('Hat')
        # Hat may be stored as a list (from _manage_equipment_slot) or a plain dict (legacy)
        if isinstance(hat, list):
            hat = hat[0] if hat else None
        hat_equipped = hat and isinstance(hat, dict) and hat.get('name')
        if hat_equipped:
            items.append(('Hat', hat))

        # ── Count duplicates ──────────────────────────────────────────────────
        mat_counts: Dict[str, int] = {}
        gem_counts: Dict[str, int] = {}
        mon_counts: Dict[str, int] = {}
        for type_key, item in items:
            name = (item.get('name') or '').lower()
            if not name: continue
            if type_key == 'Material':
                mat_counts[name] = mat_counts.get(name, 0) + 1
            elif type_key == 'Gem':
                gem_counts[name] = gem_counts.get(name, 0) + 1
            elif type_key == 'Monster':
                mon_counts[name] = mon_counts.get(name, 0) + 1

        has_mat_pair = any(v >= 2 for v in mat_counts.values())
        has_gem_pair = any(v >= 2 for v in gem_counts.values())
        has_mon_pair = any(v >= 2 for v in mon_counts.values())

        # ── Hat spec matching ─────────────────────────────────────────────────
        hat_spec_matches = 0
        if hat_equipped and specs:
            hat_bonus_stats = [s.upper() for s in (hat.get('bonuses') or {}).keys()]
            hat_spec_matches = sum(1 for s in hat_bonus_stats if s in specs)

        # ── Determine global set multiplier ───────────────────────────────────
        full_set = has_mat_pair and has_gem_pair and has_mon_pair and hat_equipped

        if full_set:
            if hat_spec_matches >= 2:
                set_mult = 4
            else:
                set_mult = 3
        elif has_mat_pair or has_gem_pair or has_mon_pair:
            set_mult = 2
        else:
            set_mult = 1

        # Add level bonus on top of the set multiplier
        final_mult = set_mult + level_bonus

        # ── Accumulate raw bonuses (sum all equipped item values first) ──────
        raw_bonuses = {k: 0 for k in ['ATT', 'DEF', 'INT', 'DEX', 'HAP', 'ENE']}
        for type_key, item in items:
            bonuses = item.get('bonuses', {})
            for stat, val in bonuses.items():
                if stat not in raw_bonuses: continue
                try:
                    raw_bonuses[stat] += int(val)
                except (TypeError, ValueError):
                    continue

        # ── Apply the global multiplier to the total equipment bonus pool ────
        equipment_bonuses = {
            stat: raw_bonuses[stat] * final_mult
            for stat in raw_bonuses
        }

        return equipment_bonuses

    @staticmethod
    def get_equipment_xp_multiplier(pet_data: Dict[str, Any]) -> float:
        """
        Return the XP multiplier derived from the pet's equipment and level.

        Uses the same rules as _calculate_equipment_bonuses:
          - No equipment                          → 1.0×
          - Any pair (no full set)                → 2.0× + level_bonus
          - Full set (mat pair + gem pair
            + mon pair + hat)                     → 3.0× + level_bonus
          - Full set + both hat stats match specs → 4.0× + level_bonus
          - Level bonus: +1 per 50 levels
        """
        equipment = pet_data.get('equipment') or {}
        level = int(pet_data.get('level', 1))
        level_bonus = level // 50

        if not equipment:
            return 1.0 + level_bonus

        try:
            specs = [s.upper() for s in LootCalculator._get_pet_specs(pet_data)]
        except Exception:
            specs = []

        mat = equipment.get('Material')
        mat_names: list = []
        if isinstance(mat, list):
            mat_names = [(m.get('name') or '').lower() for m in mat if isinstance(m, dict) and m.get('name')]
        elif isinstance(mat, dict) and mat.get('name'):
            mat_names = [(mat.get('name') or '').lower()]

        gems = equipment.get('Gems', [])
        gem_names: list = []
        if isinstance(gems, list):
            gem_names = [(g.get('name') or '').lower() for g in gems if isinstance(g, dict) and g.get('name')]
        elif isinstance(gems, dict) and gems.get('name'):
            gem_names = [(gems.get('name') or '').lower()]

        mons = equipment.get('Monsters', [])
        mon_names: list = []
        if isinstance(mons, list):
            mon_names = [(m.get('name') or '').lower() for m in mons if isinstance(m, dict) and m.get('name')]
        elif isinstance(mons, dict) and mons.get('name'):
            mon_names = [(mons.get('name') or '').lower()]

        hat = equipment.get('Hat')
        if isinstance(hat, list):
            hat = hat[0] if hat else None
        hat_equipped = hat and isinstance(hat, dict) and hat.get('name')

        has_mat_pair = len(mat_names) >= 2 and len(set(mat_names)) == 1
        has_gem_pair = len(gem_names) >= 2 and len(set(gem_names)) == 1
        has_mon_pair = len(mon_names) >= 2 and len(set(mon_names)) == 1

        full_set = has_mat_pair and has_gem_pair and has_mon_pair and hat_equipped

        if full_set:
            hat_spec_matches = 0
            if specs and hat_equipped:
                hat_bonus_stats = [s.upper() for s in (hat.get('bonuses') or {}).keys()]
                hat_spec_matches = sum(1 for s in hat_bonus_stats if s in specs)
            set_mult = 4 if hat_spec_matches >= 2 else 3
        elif has_mat_pair or has_gem_pair or has_mon_pair:
            set_mult = 2
        else:
            set_mult = 1

        return float(set_mult + level_bonus)

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
        Applies battle_health_bonus from abilities on top.
        """
        total_stats = sum(v for k, v in stats.items() if k in ('ATT', 'DEF', 'INT', 'DEX', 'HAP', 'ENE'))
        leveled_avg = total_stats / 6
        hap = stats.get('HAP', 0)
        ene = stats.get('ENE', 0)
        health_stat = hap * ene
        base_health = int((leveled_avg + health_stat) * 10)

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
          3. Original formula: (stat_avg + HAP*ENE) * 10 × ability bonus

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
