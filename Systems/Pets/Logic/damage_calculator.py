from __future__ import annotations
import random
import logging
from typing import Dict, Any, Tuple, List, Optional
from Systems.Functions.user_data_manager import user_data_manager
from Systems.Functions import emoji as emoji_mod

logger = logging.getLogger('pet_brain')

class DamageCalculator:
    _ACTION_LABELS_DATA: Optional[Dict[str, Any]] = None

    # Base charge cap — abilities can raise this via charge_limit_bonus
    BASE_MAX_CHARGE_MULTIPLIER = 5.0
    MAX_CHARGE_MULTIPLIER = 5.0          # kept for back-compat; use get_max_charge() at runtime
    VULNERABILITY_WHEN_CHARGING = 1.25

    @staticmethod
    def _load_action_labels():
        if DamageCalculator._ACTION_LABELS_DATA is None:
            try:
                DamageCalculator._ACTION_LABELS_DATA = user_data_manager.file_manager.get_data("action_labels")
            except Exception as e:
                logger.error(f"Failed to load action_labels.json via OptimalFileManager: {e}")
                DamageCalculator._ACTION_LABELS_DATA = {}

    @staticmethod
    def get_max_charge(pet_data: Optional[Dict[str, Any]] = None) -> float:
        """
        Return the effective max charge multiplier for a pet.
        Base is 5.0; each level of ene_charge_mastery adds +1.
        """
        base = DamageCalculator.BASE_MAX_CHARGE_MULTIPLIER
        if not pet_data:
            return base
        try:
            from Systems.Pets.Logic.ability_tree import get_ability_effect
            bonus = get_ability_effect(pet_data, "charge_limit_bonus")
            return base + float(bonus)
        except Exception:
            return base

    @staticmethod
    def calculate_roll_multiplier(roll: int, base_stat: int) -> Tuple[int, str]:
        try:
            roll = max(1, min(20, int(roll)))
        except Exception:
            roll = 1
        try:
            base_stat = max(0, int(base_stat))
        except Exception:
            base_stat = 0
        return int(base_stat * roll), "high_mult"

    @staticmethod
    def get_pet_action_name(species: str, action_type: str) -> str:
        """Retrieves the themed battle action name for a pet species."""
        try:
            info_data = user_data_manager.file_manager.get_data("info")
            if not info_data: 
                return action_type.title()
            
            pet_data = info_data.get("Pets", {}).get(species, {})
            actions = pet_data.get("Actions", {})
            
            # Map action_type (lowercase) to JSON keys (Title Case)
            # "defend" maps to "Defense"
            key_map = {
                "attack": "Attack",
                "defend": "Defense",
                "defense": "Defense",
                "charge": "Charge"
            }
            
            json_key = key_map.get(action_type.lower(), "Attack")
            return actions.get(json_key, action_type.title())
        except Exception:
            return action_type.title()

    @staticmethod
    def calculate_battle_action(
        attacker_attack: int,
        target_defense: int,
        charge_multiplier: float = 1.0,
        target_charge_multiplier: float = 1.0,
        action_type: str = "attack",
        attacker_action_type: str = "attack",
        target_action_type: str = "defend",
        attacker_type: Optional[str] = None,
        attacker_element: Optional[str] = None,
        attacker_element2: Optional[str] = None,
        defender_type: Optional[str] = None,
        defender_element: Optional[str] = None,
        defender_element2: Optional[str] = None,
        attacker_species: Optional[str] = None,
        defender_species: Optional[str] = None,
        attacker_pet_data: Optional[Dict[str, Any]] = None,
        defender_pet_data: Optional[Dict[str, Any]] = None,
        use_scaling: bool = True,
        attacker_user_id: Optional[str] = None,
        defender_user_id: Optional[str] = None,
        # Current HP for low-health ability check (optional)
        defender_current_hp: Optional[int] = None,
        defender_max_hp: Optional[int] = None,
        battle_type: str = "npc",
    ) -> Dict[str, Any]:
        # ── Sanitise inputs ───────────────────────────────────────────────────
        try:
            attacker_attack = max(0, int(attacker_attack)) if attacker_attack is not None else 10
            target_defense = max(0, int(target_defense)) if target_defense is not None else 5
            attacker_max_charge = DamageCalculator.get_max_charge(attacker_pet_data)
            defender_max_charge = DamageCalculator.get_max_charge(defender_pet_data)
            charge_multiplier = max(1.0, min(attacker_max_charge, float(charge_multiplier))) if charge_multiplier is not None else 1.0
            target_charge_multiplier = max(1.0, min(defender_max_charge, float(target_charge_multiplier))) if target_charge_multiplier is not None else 1.0
            action_type = str(action_type) if action_type is not None else "attack"
            attacker_action_type = str(attacker_action_type or "attack").lower()
            target_action_type = str(target_action_type or "defend").lower()
        except (ValueError, TypeError):
            attacker_attack = 10
            target_defense = 5
            charge_multiplier = 1.0
            target_charge_multiplier = 1.0
            action_type = "attack"
            attacker_action_type = "attack"
            target_action_type = "defend"

        if attacker_action_type not in ("attack", "defend", "charge"):
            attacker_action_type = "attack"
        if target_action_type not in ("attack", "defend", "charge"):
            target_action_type = "defend"

        # ── Custom user formulas (override base attack/defense stats) ─────────
        custom_formulas_applied = False
        if attacker_user_id and attacker_pet_data:
            try:
                from Systems.Pets.Logic.user_battle_settings import UserBattleSettings
                user_formula = UserBattleSettings.get_user_formula(attacker_user_id)
                if not user_formula.use_original_scaling:
                    attacker_attack = UserBattleSettings.calculate_custom_attack(attacker_pet_data, user_formula)
                    custom_formulas_applied = True
            except ImportError:
                pass

        if defender_user_id and defender_pet_data and target_action_type == "defend":
            try:
                from Systems.Pets.Logic.user_battle_settings import UserBattleSettings
                user_formula = UserBattleSettings.get_user_formula(defender_user_id)
                if not user_formula.use_original_scaling:
                    target_defense = UserBattleSettings.calculate_custom_defense(defender_pet_data, user_formula)
                    custom_formulas_applied = True
            except ImportError:
                pass

        # ── Battle scaling for high-level combat (skip if custom formulas used) ─
        scaling_applied = False
        if use_scaling and not custom_formulas_applied and attacker_pet_data and defender_pet_data:
            try:
                from Systems.Pets.Logic.battle_scaling import should_use_battle_scaling, BattleScaler
                attacker_level = int(attacker_pet_data.get('level', 1))
                defender_level = int(defender_pet_data.get('level', 1))
                if should_use_battle_scaling(attacker_level, defender_level):
                    attacker_attack = BattleScaler.calculate_scaled_damage(
                        attacker_attack, attacker_level,
                        attacker_pet_data.get('equipment_multiplier', 1.0)
                    )
                    # Defense is scaled as damage (same logarithmic curve keeps ratios sane)
                    target_defense = BattleScaler.calculate_scaled_damage(
                        target_defense, defender_level,
                        defender_pet_data.get('equipment_multiplier', 1.0)
                    )
                    scaling_applied = True
            except ImportError:
                pass

        # ── Ability: battle_damage_mult (ATT branch) ──────────────────────────
        # Applied to the raw attack stat before the roll so the multiplier
        # scales with charge and type/element bonuses naturally.
        if attacker_pet_data and attacker_action_type == "attack":
            try:
                from Systems.Pets.Logic.ability_tree import get_ability_effect
                dmg_mult = get_ability_effect(attacker_pet_data, "battle_damage_mult", battle_type=battle_type)
                if dmg_mult != 1.0:
                    attacker_attack = int(attacker_attack * dmg_mult)
            except Exception:
                pass

        # ── Ability: battle_defense_mult (DEF branch) ─────────────────────────
        if defender_pet_data and target_action_type == "defend":
            try:
                from Systems.Pets.Logic.ability_tree import get_ability_effect
                def_mult = get_ability_effect(defender_pet_data, "battle_defense_mult", battle_type=battle_type)
                if def_mult != 1.0:
                    target_defense = int(target_defense * def_mult)
            except Exception:
                pass

        # ── Resolve action display names ──────────────────────────────────────
        attacker_action_name = (
            DamageCalculator.get_pet_action_name(attacker_species, attacker_action_type)
            if attacker_species else attacker_action_type.title()
        )
        target_action_name = (
            DamageCalculator.get_pet_action_name(defender_species, target_action_type)
            if defender_species else target_action_type.title()
        )

        # ── Roll attack ───────────────────────────────────────────────────────
        attack_roll = random.randint(1, 20)
        attack_value, attack_result = DamageCalculator.calculate_roll_multiplier(attack_roll, attacker_attack)
        final_attack = int(attack_value * charge_multiplier)

        # Type + element advantage on attack
        type_bonus = DamageCalculator.compute_type_bonus(attacker_type, defender_type, attacker_pet_data)
        element_bonus = DamageCalculator.compute_element_bonus(
            attacker_element, defender_element, attacker_element2, defender_element2, attacker_pet_data
        )
        atk_bonus_mult = type_bonus * element_bonus
        final_attack = int(final_attack * atk_bonus_mult)

        # ── Roll defense (only when defender is defending) ────────────────────
        def_bonus_mult = 1.0
        if target_action_type == "defend":
            defense_roll = random.randint(1, 20)
            defense_value, defense_result = DamageCalculator.calculate_roll_multiplier(defense_roll, target_defense)
            final_defense = int(defense_value * target_charge_multiplier)

            def_type_bonus = DamageCalculator.compute_type_bonus(defender_type, attacker_type, defender_pet_data)
            def_element_bonus = DamageCalculator.compute_element_bonus(
                defender_element, attacker_element, defender_element2, attacker_element2, defender_pet_data
            )
            def_bonus_mult = def_type_bonus * def_element_bonus
            final_defense = int(final_defense * def_bonus_mult)
        else:
            defense_roll = None
            defense_result = "none"
            final_defense = 0

        # ── Damage resolution ─────────────────────────────────────────────────
        is_critical = False
        critical_multiplier = 1.0

        if attacker_action_type == "charge":
            # Charging turn — no damage dealt
            final_damage = 0
            parry_damage = 0
        else:
            # Critical hit check (attack actions only)
            if attacker_action_type == "attack" and attacker_pet_data:
                try:
                    from Systems.Pets.Logic.ability_tree import get_critical_hit_chance, get_critical_hit_multiplier
                    crit_chance = get_critical_hit_chance(attacker_pet_data)
                    if crit_chance > 0 and random.random() < crit_chance:
                        is_critical = True
                        critical_multiplier = get_critical_hit_multiplier(attacker_pet_data)
                except Exception:
                    pass

            if target_action_type == "defend":
                if final_attack > final_defense:
                    base_damage = max(1, final_attack - final_defense)
                    final_damage = int(base_damage * critical_multiplier) if is_critical else base_damage
                    parry_damage = 0
                elif final_attack == final_defense:
                    final_damage = 0
                    parry_damage = 0
                else:
                    final_damage = 0
                    parry_damage = max(1, final_defense - final_attack)

            elif target_action_type == "charge":
                # Attacker hits a charging defender — vulnerability applies
                vulnerability_multiplier = DamageCalculator.VULNERABILITY_WHEN_CHARGING
                if defender_pet_data:
                    try:
                        from Systems.Pets.Logic.ability_tree import get_charge_vulnerability_reduction
                        vulnerability_multiplier = get_charge_vulnerability_reduction(defender_pet_data)
                    except Exception:
                        pass
                vulnerable_damage = int(max(0, final_attack) * vulnerability_multiplier)
                final_damage = int(vulnerable_damage * critical_multiplier) if is_critical else vulnerable_damage
                parry_damage = 0

            else:
                # Defender is attacking too — no defense roll, full damage
                base_damage = max(1, final_attack)
                final_damage = int(base_damage * critical_multiplier) if is_critical else base_damage
                parry_damage = 0

        # ── Ability: low_health_damage_reduction (DEF branch — Last Stand) ────
        # Applied after all other damage math when we know the defender's HP.
        if final_damage > 0 and defender_pet_data and defender_current_hp is not None and defender_max_hp:
            try:
                hp_pct = defender_current_hp / max(1, defender_max_hp)
                if hp_pct < 0.25:
                    from Systems.Pets.Logic.ability_tree import get_low_health_damage_reduction
                    reduction = get_low_health_damage_reduction(defender_pet_data)
                    if reduction > 0:
                        final_damage = max(1, int(final_damage * (1.0 - reduction)))
            except Exception:
                pass

        return {
            'final_damage': final_damage,
            'parry_damage': parry_damage,
            'attack_roll': attack_roll,
            'defense_roll': defense_roll,
            'attack_result': attack_result,
            'defense_result': defense_result,
            'final_attack': final_attack,
            'final_defense': final_defense,
            'charge_used': charge_multiplier > 1.0 or target_charge_multiplier > 1.0,
            'attacker_action_type': attacker_action_type,
            'target_action_type': target_action_type,
            'type_element_bonus_mult_attack': atk_bonus_mult,
            'type_element_bonus_mult_defense': def_bonus_mult,
            'attacker_action_name': attacker_action_name,
            'target_action_name': target_action_name,
            'is_critical': is_critical,
            'critical_multiplier': critical_multiplier,
            'scaling_applied': scaling_applied,
            'custom_formulas_applied': custom_formulas_applied,
            'battle_type': battle_type,
        }

    @staticmethod
    def calculate_monster_vs_players(
        monster_attack: int,
        player_defenses: Dict[str, Any],
        monster_charge_multiplier: float = 1.0,
        monster_type: Optional[str] = None,
        monster_element: Optional[str] = None,
        monster_pet_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        try:
            monster_attack = max(0, int(monster_attack)) if monster_attack is not None else 10
            monster_max_charge = DamageCalculator.get_max_charge(monster_pet_data)
            monster_charge_multiplier = max(1.0, min(monster_max_charge, float(monster_charge_multiplier))) if monster_charge_multiplier is not None else 1.0
            if not isinstance(player_defenses, dict):
                player_defenses = {}
        except (ValueError, TypeError):
            monster_attack = 10
            monster_charge_multiplier = 1.0
            player_defenses = {}
        results = {}

        for player_id, defense_info in player_defenses.items():
            player_defense = defense_info.get('defense', 0)
            player_charge_multiplier = defense_info.get('charge_multiplier', 1.0)
            player_action = str(defense_info.get('action', '') or '').lower()
            if not player_action:
                if defense_info.get('defending', False):
                    player_action = 'defend'
                elif defense_info.get('charging', False):
                    player_action = 'charge'
                else:
                    player_action = 'attack'

            battle_result = DamageCalculator.calculate_battle_action(
                attacker_attack=monster_attack,
                target_defense=player_defense,
                charge_multiplier=monster_charge_multiplier,
                target_charge_multiplier=player_charge_multiplier,
                action_type="monster_attack",
                attacker_action_type="attack",
                target_action_type=player_action,
                attacker_type=monster_type,
                attacker_element=monster_element,
                attacker_element2=None,
                defender_type=defense_info.get('type'),
                defender_element=defense_info.get('element'),
                defender_element2=defense_info.get('element2'),
                defender_species=defense_info.get('species'),
                attacker_pet_data=monster_pet_data,
                defender_pet_data=defense_info.get('pet_data'),
                defender_user_id=defense_info.get('user_id'),
                defender_current_hp=defense_info.get('current_hp'),
                defender_max_hp=defense_info.get('max_hp'),
                battle_type="npc",
            )

            results[player_id] = {
                'final_damage': battle_result['final_damage'],
                'parry_damage': battle_result['parry_damage'],
                'attack_roll': battle_result['attack_roll'],
                'defense_roll': battle_result['defense_roll'],
                'attack_result': battle_result['attack_result'],
                'defense_result': battle_result['defense_result'],
                'final_attack': battle_result['final_attack'],
                'final_defense': battle_result['final_defense'],
                'charge_used': battle_result['charge_used'],
                'target_action_type': battle_result['target_action_type'],
                'attacker_action_name': battle_result.get('attacker_action_name'),
                'target_action_name': battle_result.get('target_action_name'),
                'is_critical': battle_result.get('is_critical', False),
            }

        return results

    @staticmethod
    def get_charge_progression(pet_data: Optional[Dict[str, Any]] = None) -> list:
        """Return the charge progression steps up to this pet's max charge."""
        max_charge = DamageCalculator.get_max_charge(pet_data)
        steps = [1.0, 2.0, 3.0, 4.0, 5.0]
        # Extend if charge_limit_bonus raised the cap beyond 5
        extra = int(max_charge - 5.0)
        for i in range(extra):
            steps.append(6.0 + i)
        return [s for s in steps if s <= max_charge]

    @staticmethod
    def get_next_charge_multiplier(current_multiplier: float, pet_data: Optional[Dict[str, Any]] = None) -> float:
        try:
            current_multiplier = float(current_multiplier) if current_multiplier is not None else 1.0
            max_charge = DamageCalculator.get_max_charge(pet_data)
            current_multiplier = max(1.0, min(max_charge, current_multiplier))
        except (ValueError, TypeError):
            current_multiplier = 1.0
            max_charge = DamageCalculator.BASE_MAX_CHARGE_MULTIPLIER

        progression = DamageCalculator.get_charge_progression(pet_data)
        try:
            current_index = progression.index(current_multiplier)
            if current_index < len(progression) - 1:
                return progression[current_index + 1]
            else:
                return max_charge
        except ValueError:
            return progression[1] if len(progression) > 1 else max_charge

    @staticmethod
    def calculate_pet_health(
        hap: int,
        ene: int,
        level: int = 1,
        att: int = 0,
        deff: int = 0,
        intel: int = 0,
        dex: int = 0,
        pet_data: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Calculate Max Health using the balanced formula:
        (Stat Average + (HAP * ENE)) * 10

        Applies battle_health_bonus from HAP/ENE ability branches on top.
        pet_data is optional — pass it to include ability bonuses.
        """
        try:
            hap_i = max(0, int(hap))
            ene_i = max(0, int(ene))

            stats = [hap_i, ene_i]
            if att:   stats.append(int(att))
            if deff:  stats.append(int(deff))
            if intel: stats.append(int(intel))
            if dex:   stats.append(int(dex))

            avg_stat = sum(stats) / len(stats)
            health_stat = hap_i * ene_i
            base_health = int((avg_stat + health_stat) * 10)

            # Apply battle_health_bonus from abilities (hap_battle_health + ene_battle_stamina)
            if pet_data:
                try:
                    from Systems.Pets.Logic.ability_tree import get_ability_effect
                    health_bonus = get_ability_effect(pet_data, "battle_health_bonus")
                    if health_bonus > 0:
                        base_health = int(base_health * (1.0 + health_bonus))
                except Exception:
                    pass

            return max(1, base_health)

        except Exception:
            return 100

    ELEMENT_EFFECTIVENESS: Dict[str, Dict[str, float]] = {
        "basic": {
            "basic": 0.90, "fire": 0.90, "water": 0.90, "electric": 0.90, "ice": 0.90,
            "plant": 0.90, "rock": 0.90, "air": 0.90, "magic": 0.90, "holy": 0.90,
            "necro": 0.90, "psychic": 0.90, "fighting": 0.90
        },
        "fire": {"ice": 1.10, "plant": 1.10, "necro": 1.10},
        "electric": {"water": 1.10, "plant": 1.10, "fighting": 1.10},
        "air": {"rock": 1.10, "fighting": 1.10, "electric": 1.10},
        "ice": {"air": 1.10, "electric": 1.10, "water": 1.10},
        "water": {"fire": 1.10, "rock": 1.10, "air": 1.10},
        "plant": {"water": 1.10, "air": 1.10, "psychic": 1.10},
        "rock": {"electric": 1.10, "fire": 1.10, "ice": 1.10},
        "fighting": {"ice": 1.10, "psychic": 1.10, "holy": 1.10},
        "psychic": {"holy": 1.10, "necro": 1.10, "magic": 1.10},
        "magic": {"psychic": 1.10, "fighting": 1.10, "fire": 1.10},
        "holy": {"necro": 1.10, "magic": 1.10, "rock": 1.10},
        "necro": {"holy": 1.10, "magic": 1.10, "plant": 1.10},
    }

    CATEGORY_ADVANTAGES: Dict[str, Dict[str, float]] = {
        "flying": {"land": 1.15},
        "land": {"swimming": 1.15},
        "swimming": {"flying": 1.15},
    }

    @staticmethod
    def get_action_labels(pet_type: str, pet_element: str, species: Optional[str] = None, custom_labels: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Return action labels. Prefers custom saved labels, then species-specific actions from info.json, falls back to type/element defaults.
        
        The returned dict always uses 'defend' as the key (matching the action string used in battle logic).
        custom_labels may use either 'defend' or 'defense' as the key â€” both are handled.
        """
        DamageCalculator._load_action_labels() # Ensure labels are loaded
        if not DamageCalculator._ACTION_LABELS_DATA: # Fallback if loading failed
            return {"attack": "Attack", "defend": "Defend", "charge": "Charge"}

        # Try to get species-specific actions first
        if species:
            try:
                atk = DamageCalculator.get_pet_action_name(species, "attack")
                dfd = DamageCalculator.get_pet_action_name(species, "defense")
                chg = DamageCalculator.get_pet_action_name(species, "charge")

                result = {
                    "attack": atk,
                    "defend": dfd,
                    "charge": chg
                }
            except Exception:
                t = str(pet_type or "basic").lower()
                e = str(pet_element or "basic").lower()
                type_map = DamageCalculator._ACTION_LABELS_DATA.get(t, DamageCalculator._ACTION_LABELS_DATA["land"])
                entry = type_map.get(e, type_map["basic"])
                result = {"attack": entry["attack"], "defend": entry["defend"], "charge": entry["charge"]}
        else:
            t = str(pet_type or "basic").lower()
            e = str(pet_element or "basic").lower()
            type_map = DamageCalculator._ACTION_LABELS_DATA.get(t, DamageCalculator._ACTION_LABELS_DATA["land"])
            entry = type_map.get(e, type_map["basic"])
            result = {"attack": entry["attack"], "defend": entry["defend"], "charge": entry["charge"]}

        # Overlay custom labels â€” stored under "defense" (or legacy "defend"), returned under "defend"
        if custom_labels:
            if custom_labels.get("attack"):
                result["attack"] = custom_labels["attack"]
            if custom_labels.get("defense") or custom_labels.get("defend"):
                result["defend"] = custom_labels.get("defense") or custom_labels.get("defend")
            if custom_labels.get("charge"):
                result["charge"] = custom_labels["charge"]

        return result
    
    @staticmethod
    def compute_type_bonus(attacker_type: Optional[str], defender_type: Optional[str], attacker_pet_data: Optional[Dict[str, Any]] = None) -> float:
        try:
            a_t = str(attacker_type or "").lower()
            d_t = str(defender_type or "").lower()
            base = DamageCalculator.CATEGORY_ADVANTAGES.get(a_t, {}).get(d_t, 1.0)
            if base > 1.0 and attacker_pet_data:
                try:
                    from Systems.Pets.Logic.ability_tree import get_advantage_mastery_bonus
                    bonus = get_advantage_mastery_bonus(attacker_pet_data, "type")
                    if bonus > 0:
                        base = round(base + bonus, 4)
                except Exception:
                    pass
            return base
        except Exception:
            return 1.0

    @staticmethod
    def compute_element_bonus(attacker_element: Optional[str], defender_element: Optional[str], attacker_element2: Optional[str] = None, defender_element2: Optional[str] = None, attacker_pet_data: Optional[Dict[str, Any]] = None) -> float:
        """
        Calculates element effectiveness multiplier.
        Supports dual elements by averaging the modifiers.
        Applies element advantage mastery bonus (flat +0.1 per point) when the
        averaged result is above 1.0.
        """
        try:
            # Helper to get bonus for one pair
            def get_pair_bonus(a, d):
                if not a or not d: return 1.0
                return DamageCalculator.ELEMENT_EFFECTIVENESS.get(str(a).lower(), {}).get(str(d).lower(), 1.0)

            # Collect all combinations
            attackers = [attacker_element]
            if attacker_element2 and str(attacker_element2).lower() not in ("basic", "none", ""):
                attackers.append(attacker_element2)
            
            defenders = [defender_element]
            if defender_element2 and str(defender_element2).lower() not in ("basic", "none", ""):
                defenders.append(defender_element2)

            bonuses = []
            for a in attackers:
                for d in defenders:
                    bonuses.append(get_pair_bonus(a, d))
            
            if not bonuses:
                return 1.0

            result = sum(bonuses) / len(bonuses)

            if result > 1.0 and attacker_pet_data:
                try:
                    from Systems.Pets.Logic.ability_tree import get_advantage_mastery_bonus
                    bonus = get_advantage_mastery_bonus(attacker_pet_data, "element")
                    if bonus > 0:
                        result = round(result + bonus, 4)
                except Exception:
                    pass

            return result
        except Exception:
            return 1.0

