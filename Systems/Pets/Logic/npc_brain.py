from __future__ import annotations
import random
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger('pet_brain')


def _get_ability_effect(pet_data: Optional[Dict[str, Any]], effect_type: str, **kwargs) -> float:
    """Safe wrapper around ability_tree.get_ability_effect — returns 0.0 on any failure."""
    if not pet_data:
        return 0.0
    try:
        from Systems.Pets.Logic.ability_tree import get_ability_effect
        return get_ability_effect(pet_data, effect_type, **kwargs)
    except Exception:
        return 0.0


def _get_max_charge(pet_data: Optional[Dict[str, Any]]) -> float:
    """Return the effective max charge multiplier for a pet (base 5 + charge_limit_bonus)."""
    try:
        from Systems.Pets.Logic.damage_calculator import DamageCalculator
        return DamageCalculator.get_max_charge(pet_data)
    except Exception:
        return 5.0


class NPCBrain:
    def decide_action(
        self,
        monster_state: Dict[str, Any],
        players_state: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        # ── Read monster state ────────────────────────────────────────────────
        hp = max(0, int(monster_state.get("hp", 0)))
        max_hp = max(1, int(monster_state.get("max_hp", 1)))
        charge_mult = float(monster_state.get("charge_multiplier", 1.0))
        last_action = monster_state.get("last_action")
        seed = monster_state.get("seed")
        prev_hp = monster_state.get("prev_hp")
        attack_stat = float(monster_state.get("attack_stat", 1.0))
        defense_stat = float(monster_state.get("defense_stat", 1.0))

        # Monster's own pet_data (optional — enables ability-aware decisions)
        monster_pet_data: Optional[Dict[str, Any]] = monster_state.get("pet_data")

        if seed is not None:
            try:
                random.seed(int(seed))
            except Exception:
                pass

        # ── Monster ability modifiers ─────────────────────────────────────────
        # Effective charge cap (ene_charge_mastery raises this above 5)
        monster_max_charge = _get_max_charge(monster_pet_data)
        charge_mult = max(1.0, min(monster_max_charge, charge_mult))

        # Starting charge bonus — if the monster started with pre-built charge,
        # treat the current charge_mult as already elevated for decision purposes.
        # (The actual starting charge is applied by the battle system before the
        # first call here, so charge_mult already reflects it — no extra math needed.)

        # Critical hit chance — aggressive monsters with high crit should attack more
        monster_crit_chance = _get_ability_effect(monster_pet_data, "critical_hit_chance")

        # Damage/defense ability multipliers — refine the attack_bias calculation
        # battle_damage_mult and battle_defense_mult are already baked into the
        # attack_stat / defense_stat values passed in monster_state by the battle
        # system, so we only need them here if the caller didn't pre-apply them.
        # We read them as a tiebreak signal rather than re-applying.
        monster_dmg_mult = _get_ability_effect(monster_pet_data, "battle_damage_mult", battle_type="npc")
        monster_def_mult = _get_ability_effect(monster_pet_data, "battle_defense_mult", battle_type="npc")

        # ── HP percentages ────────────────────────────────────────────────────
        m_pct = (hp / max_hp) * 100.0
        loss_rate = 0.0
        if prev_hp is not None:
            try:
                prev_hp_i = max(0, int(prev_hp))
                loss_rate = max(0.0, (prev_hp_i - hp) / max_hp)
            except Exception:
                loss_rate = 0.0

        # ── Player state analysis ─────────────────────────────────────────────
        alive_players = [
            p for p in players_state
            if p.get("alive", False) and p.get("hp", 0) > 0
        ]
        n_alive = len(alive_players)
        total_players = len(players_state)
        eliminations = max(0, total_players - n_alive)

        if n_alive == 0:
            return {"action": "defend", "rationale": "No opponents alive", "strategy": "spread"}

        player_pcts = [
            max(0.0, min(100.0, (p.get("hp", 0) / max(1, p.get("max_hp", 1))) * 100.0))
            for p in alive_players
        ]
        avg_player_pct = sum(player_pcts) / len(player_pcts)
        weakest_pct = min(player_pcts)
        strongest_pct = max(player_pcts)
        any_player_critical = weakest_pct <= 10.0
        any_player_finisher_range = weakest_pct <= 25.0
        players_charging = [p for p in alive_players if p.get("charging", False)]
        charging_count = len(players_charging)
        many_players = n_alive >= 3

        # ── Per-player ability awareness ──────────────────────────────────────
        # Identify the weakest player and check if they have Last Stand
        # (low_health_damage_reduction). If so, finishing them is harder —
        # reduce the "focus_weakest" aggression bonus.
        weakest_player = min(alive_players, key=lambda p: p.get("hp", 0) / max(1, p.get("max_hp", 1)))
        weakest_pet_data: Optional[Dict[str, Any]] = weakest_player.get("pet_data")
        weakest_last_stand = _get_ability_effect(weakest_pet_data, "low_health_damage_reduction")

        # Check if any charging player has charge_vulnerability_reduction (Charge Guard).
        # If so, hitting them while charging is less rewarding — reduce attack bias.
        charging_guard_total = sum(
            _get_ability_effect(p.get("pet_data"), "charge_vulnerability_reduction")
            for p in players_charging
        )
        # Normalise: 0.0 = no guard, 1.0 = full guard across all charging players
        charging_guard_factor = min(1.0, charging_guard_total / max(1, charging_count)) if charging_count else 0.0

        # ── HP stage ──────────────────────────────────────────────────────────
        if hp == max_hp:
            stage = "full"
        elif m_pct >= 75.0:
            stage = "three_quarters"
        elif m_pct >= 50.0:
            stage = "half"
        elif m_pct >= 25.0:
            stage = "quarter"
        elif m_pct >= 10.0:
            stage = "ten_percent"
        else:
            stage = "critical"

        # ── Base action weights ───────────────────────────────────────────────
        weights: Dict[str, float] = {"attack": 0.0, "defend": 0.0, "charge": 0.0}
        strategy = "spread"

        if stage == "full":
            weights["attack"] = 6
            weights["defend"] = 1
            weights["charge"] = 3 if many_players else 2
        elif stage == "three_quarters":
            weights["attack"] = 6
            weights["defend"] = 2
            weights["charge"] = 3 if many_players else 2
        elif stage == "half":
            weights["attack"] = 5
            weights["defend"] = 3
            weights["charge"] = 2
        elif stage == "quarter":
            weights["attack"] = 5
            weights["defend"] = 5
            charge_base = 2
            charge_decay = int(max(0, (50.0 - m_pct) / 12.0))
            weights["charge"] = max(0, charge_base - charge_decay)
            if loss_rate >= 0.20:
                weights["charge"] = max(0, weights["charge"] - 2)
                weights["defend"] += 1
        elif stage == "ten_percent":
            weights["attack"] = 4
            weights["defend"] = 6
            weights["charge"] = 0
        else:  # critical
            weights["attack"] = 2
            weights["defend"] = 7
            weights["charge"] = 0

        # ── Player count adjustments ──────────────────────────────────────────
        if n_alive == 1:
            weights["attack"] += 2
            if weights["defend"] > 0:
                weights["defend"] -= 1
        elif n_alive == 2:
            weights["attack"] += 1
        elif n_alive == 4:
            if stage in ("full", "three_quarters", "half"):
                weights["charge"] += 1

        # ── Finisher / pressure adjustments ──────────────────────────────────
        if any_player_finisher_range:
            # Reduce aggression bonus if the weakest player has Last Stand
            finisher_bonus = max(0.0, 2.0 - weakest_last_stand * 4.0)
            weights["attack"] += finisher_bonus
            strategy = "focus_weakest"
        elif avg_player_pct < 50.0 and not many_players:
            weights["attack"] += 1

        pressure_advantage = m_pct - avg_player_pct
        if pressure_advantage >= 15:
            weights["attack"] += 2
            if stage in ("full", "three_quarters") and many_players:
                weights["charge"] += 1
        elif pressure_advantage <= -15:
            weights["defend"] += 2
            weights["charge"] = max(0, weights["charge"] - 1)

        # ── Charge safety check ───────────────────────────────────────────────
        safe_to_charge = (
            stage in ("full", "three_quarters", "half") and
            avg_player_pct >= 50.0 and
            not any_player_critical and
            charging_count == 0
        )

        # Attack/defense stat bias (base)
        max_stat = max(1.0, max(attack_stat, defense_stat))
        attack_bias = (attack_stat - defense_stat) / max_stat

        # Refine attack_bias with ability multipliers if the caller didn't
        # pre-apply them into attack_stat / defense_stat.
        # monster_dmg_mult / monster_def_mult are additive offsets from 1.0.
        ability_bias_offset = (monster_dmg_mult - 1.0) - (monster_def_mult - 1.0)
        attack_bias = max(-1.0, min(1.0, attack_bias + ability_bias_offset * 0.5))

        # Boost attack weight for monsters with high crit chance
        if monster_crit_chance > 0:
            weights["attack"] += monster_crit_chance * 6.0  # e.g. 25% crit → +1.5

        if not safe_to_charge:
            suppress = 1 if attack_bias < -0.1 else 2
            weights["charge"] = max(0, weights["charge"] - suppress)

        # ── Charge release logic ──────────────────────────────────────────────
        # Use the monster's actual max charge cap (not hardcoded 5.0)
        charge_release_threshold = monster_max_charge * 0.6  # release at 60% of cap
        if charge_mult >= charge_release_threshold:
            weights["attack"] += 2
            weights["charge"] = max(0, weights["charge"] - 2)
            if many_players and m_pct >= 50.0 and not any_player_finisher_range:
                strategy = "focus_strongest"

        # ── Charging players ──────────────────────────────────────────────────
        if charging_count >= 2 and m_pct <= 50.0:
            weights["defend"] += 2
            weights["charge"] = 0
        elif charging_count == 1 and stage in ("full", "three_quarters", "half"):
            # Reduce attack bonus if the charging player has Charge Guard
            attack_bonus = max(0.0, 1.0 - charging_guard_factor)
            weights["attack"] += attack_bonus
            strategy = "focus_strongest" if strongest_pct >= 60.0 else strategy

        # ── Last-action momentum ──────────────────────────────────────────────
        if last_action == "charge":
            weights["attack"] += 2
            if stage in ("quarter", "critical"):
                weights["defend"] += 1
            weights["charge"] = max(0, weights["charge"] - 2)
        elif last_action == "defend":
            weights["attack"] += 1
        elif last_action == "attack" and stage in ("quarter", "ten_percent", "critical"):
            weights["defend"] += 1

        if eliminations >= 1 and m_pct >= 25.0:
            weights["attack"] += 1

        # ── Stat-profile bias ─────────────────────────────────────────────────
        bias_scale = 2 if m_pct <= 50.0 else 1
        if attack_bias > 0.1:
            weights["attack"] += 1 + int(round(abs(attack_bias) * 4)) * bias_scale
        elif attack_bias < -0.1:
            weights["defend"] += 1 + int(round(abs(attack_bias) * 4)) * bias_scale
            if charge_mult < charge_release_threshold and stage in ("full", "three_quarters", "half"):
                weights["charge"] += 1 + int(round(abs(attack_bias) * 2))

        if m_pct >= 50.0 and abs(attack_bias) < 0.1 and charge_mult < (monster_max_charge * 0.8):
            weights["charge"] += 1

        # ── Near-death: no charging, pure fight-or-flight ─────────────────────
        if m_pct <= 15.0:
            weights["charge"] = 0
            if attack_bias > 0:
                weights["attack"] += 2
            elif attack_bias < 0:
                weights["defend"] += 2

        # ── Risk factor (adds noise) ──────────────────────────────────────────
        base_risk = {
            "full": 0.7,
            "three_quarters": 0.65,
            "half": 0.55,
            "quarter": 0.4,
            "ten_percent": 0.3,
            "critical": 0.25,
        }[stage]
        adv_factor = max(-0.2, min(0.2, pressure_advantage / 100.0))
        risk = max(0.05, min(0.95, base_risk + adv_factor + (random.random() - 0.5) * 0.1))

        noisy: Dict[str, float] = {}
        for k, w in weights.items():
            if k == "charge" and m_pct <= 15.0:
                noisy[k] = 0.0
            else:
                noisy[k] = max(0.0, w + risk * random.uniform(0, 1.0))

        # ── Action selection ──────────────────────────────────────────────────
        top = max(noisy.values())
        candidates = [k for k, v in noisy.items() if abs(v - top) < 0.75]
        if len(candidates) == 1:
            action = candidates[0]
        else:
            if attack_bias < -0.1:
                tiebreak_order = ("charge", "defend", "attack")
            elif attack_bias > 0.1:
                tiebreak_order = ("attack", "charge", "defend")
            else:
                tiebreak_order = ("attack", "defend", "charge")
            for pref in tiebreak_order:
                if pref in candidates:
                    action = pref
                    break
            else:
                total_noisy = sum(noisy.values())
                if total_noisy > 0:
                    action = random.choices(list(noisy.keys()), weights=list(noisy.values()))[0]
                else:
                    action = random.choice(["attack", "defend", "charge"])

        # ── Final strategy override ───────────────────────────────────────────
        if any_player_finisher_range:
            strategy = "focus_weakest"
        elif charging_count >= 1 and m_pct >= 50.0 and not any_player_finisher_range:
            strategy = "focus_strongest"
        elif many_players and stage in ("full", "three_quarters") and action == "attack":
            strategy = "spread"

        rationale = (
            f"stage={stage}, n_alive={n_alive}, avg_player_pct={avg_player_pct:.0f}, "
            f"weakest_pct={weakest_pct:.0f}, strongest_pct={strongest_pct:.0f}, "
            f"charge_mult=x{charge_mult:.1f}/{monster_max_charge:.0f}, "
            f"charging_count={charging_count}, risk={risk:.2f}, "
            f"att={attack_stat:.1f}, def={defense_stat:.1f}, "
            f"crit={monster_crit_chance:.2f}, last_stand={weakest_last_stand:.2f}, "
            f"charge_guard={charging_guard_factor:.2f}"
        )

        return {"action": action, "rationale": rationale, "strategy": strategy}
