"""
Spy Logic Module for Politics & War

Implements espionage operation calculations including:
- Odds calculation with safety levels and war policy modifiers
- Operation success/failure detection
- Casualty calculations
- Operation-specific effects
"""

import random
from typing import Dict, Optional, Tuple, List
from enum import Enum
from dataclasses import dataclass
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


class SafetyLevel(Enum):
    """Safety levels for espionage operations."""
    QUICK_AND_DIRTY = 1
    NORMAL_PRECAUTIONS = 2
    EXTREMELY_COVERT = 3


class EspionageOperation(Enum):
    """Types of espionage operations."""
    GATHER_INTELLIGENCE = "gather_intelligence"
    ASSASSINATE_SPIES = "assassinate_spies"
    TERRORIZE_CIVILIANS = "terrorize_civilians"
    SABOTAGE_SOLDIERS = "sabotage_soldiers"
    SABOTAGE_TANKS = "sabotage_tanks"
    SABOTAGE_AIRCRAFT = "sabotage_aircraft"
    SABOTAGE_SHIPS = "sabotage_ships"
    SABOTAGE_MISSILES = "sabotage_missiles"
    SABOTAGE_NUCLEAR_WEAPONS = "sabotage_nuclear_weapons"


@dataclass
class NationData:
    """Data structure for nation information relevant to espionage."""
    nation_id: int
    nation_name: str
    spies: int
    soldiers: int
    tanks: int
    aircraft: int
    ships: int
    missiles: int
    nukes: int
    war_policy: Optional[str] = None
    spy_satellite: bool = False
    cities: Optional[List[Dict]] = None
    money: float = 0.0
    resources: Dict[str, float] = None

    def __post_init__(self):
        if self.resources is None:
            self.resources = {}


@dataclass
class EspionageResult:
    """Result of an espionage operation."""
    operation: EspionageOperation
    success: bool
    detected: bool
    odds: float
    attacker_spies_lost: int = 0
    defender_spies_killed: int = 0
    infrastructure_destroyed: float = 0.0
    soldiers_killed: int = 0
    tanks_destroyed: int = 0
    aircraft_destroyed: int = 0
    ships_destroyed: int = 0
    missiles_destroyed: int = 0
    nukes_destroyed: int = 0
    intelligence_gathered: Optional[Dict] = None
    error_message: Optional[str] = None


class SpyCalculator:
    """Calculator for espionage operations."""

    # Operation-specific odds modifiers
    OPERATION_MODIFIERS = {
        EspionageOperation.GATHER_INTELLIGENCE: 1.0,
        EspionageOperation.ASSASSINATE_SPIES: 1.5,
        EspionageOperation.TERRORIZE_CIVILIANS: 1.0,
        EspionageOperation.SABOTAGE_SOLDIERS: 1.0,
        EspionageOperation.SABOTAGE_TANKS: 1.5,
        EspionageOperation.SABOTAGE_AIRCRAFT: 2.0,
        EspionageOperation.SABOTAGE_SHIPS: 3.0,
        EspionageOperation.SABOTAGE_MISSILES: 4.0,
        EspionageOperation.SABOTAGE_NUCLEAR_WEAPONS: 5.0,
    }

    @staticmethod
    def calculate_base_odds(
        attacker_spies: int,
        defender_spies: int,
        safety_level: SafetyLevel
    ) -> float:
        """
        Calculate base odds for espionage operation.

        Formula: Safety Level * 25 + (Your Spies * 100 / ((Enemy Spies * 3) + 1))

        Args:
            attacker_spies: Number of attacking spies
            defender_spies: Number of defending spies
            safety_level: Safety level of the operation (1-3)

        Returns:
            Base odds as a float
        """
        base = safety_level.value * 25
        spy_ratio = (attacker_spies * 100) / ((defender_spies * 3) + 1)
        return base + spy_ratio

    @staticmethod
    def apply_operation_modifier(
        base_odds: float,
        operation: EspionageOperation
    ) -> float:
        """
        Apply operation-specific modifier to odds.

        Args:
            base_odds: Base odds before modifier
            operation: Type of espionage operation

        Returns:
            Modified odds
        """
        modifier = SpyCalculator.OPERATION_MODIFIERS.get(operation, 1.0)
        return base_odds / modifier

    @staticmethod
    def apply_war_policy_modifiers(
        odds: float,
        attacker_war_policy: Optional[str],
        defender_war_policy: Optional[str]
    ) -> float:
        """
        Apply war policy modifiers to odds.

        - Defender has Tactician: odds * 1.15
        - Defender has Arcane: odds * 0.85
        - Attacker has Covert: odds * 1.15

        Args:
            odds: Current odds
            attacker_war_policy: Attacker's war policy
            defender_war_policy: Defender's war policy

        Returns:
            Modified odds
        """
        modified_odds = odds

        # Defender modifiers
        if defender_war_policy:
            if defender_war_policy.lower() == "tactician":
                modified_odds *= 1.15
            elif defender_war_policy.lower() == "arcane":
                modified_odds *= 0.85

        # Attacker modifiers
        if attacker_war_policy and attacker_war_policy.lower() == "covert":
            modified_odds *= 1.15

        return modified_odds

    @staticmethod
    def calculate_final_odds(
        attacker_spies: int,
        defender_spies: int,
        safety_level: SafetyLevel,
        operation: EspionageOperation,
        attacker_war_policy: Optional[str] = None,
        defender_war_policy: Optional[str] = None
    ) -> float:
        """
        Calculate final odds for an espionage operation.

        Args:
            attacker_spies: Number of attacking spies
            defender_spies: Number of defending spies
            safety_level: Safety level of the operation
            operation: Type of espionage operation
            attacker_war_policy: Attacker's war policy
            defender_war_policy: Defender's war policy

        Returns:
            Final odds (capped at 100)
        """
        base_odds = SpyCalculator.calculate_base_odds(
            attacker_spies, defender_spies, safety_level
        )
        modified_odds = SpyCalculator.apply_operation_modifier(base_odds, operation)
        final_odds = SpyCalculator.apply_war_policy_modifiers(
            modified_odds, attacker_war_policy, defender_war_policy
        )

        return min(final_odds, 100.0)

    @staticmethod
    def roll_success(odds: float) -> bool:
        """
        Roll for operation success.

        Roll 1-100, if <= odds then successful.

        Args:
            odds: Final odds (0-100)

        Returns:
            True if operation succeeds, False otherwise
        """
        roll = random.uniform(1, 100)
        return roll <= odds

    @staticmethod
    def roll_detection(odds: float) -> bool:
        """
        Roll for detection.

        Roll 1-102, if <= odds then undetected (not caught).

        Args:
            odds: Final odds (0-100)

        Returns:
            True if undetected, False if detected
        """
        roll = random.uniform(1, 102)
        return roll <= odds

    @staticmethod
    def calculate_attacker_casualties(
        attacking_spies: int,
        odds: float,
        detected: bool
    ) -> int:
        """
        Calculate attacker spy casualties.

        If caught (detected): min(((1 / odds) * 8) * attacking_spies, attacking_spies)

        Args:
            attacking_spies: Number of attacking spies
            odds: Final odds
            detected: Whether the operation was detected

        Returns:
            Number of attacker spies lost
        """
        if not detected:
            return 0

        if odds <= 0:
            return attacking_spies

        casualties = ((1 / odds) * 8) * attacking_spies
        return min(int(casualties), attacking_spies)

    @staticmethod
    def calculate_espionage_range_min(nation_score: float) -> float:
        """
        Calculate minimum score for espionage range.

        Formula: Min Score = Nation Score * 0.40

        Args:
            nation_score: Nation's score

        Returns:
            Minimum score in espionage range
        """
        return nation_score * 0.40

    @staticmethod
    def calculate_espionage_range_max(nation_score: float) -> float:
        """
        Calculate maximum score for espionage range.

        Formula: Max Score = Nation Score * 2.50

        Args:
            nation_score: Nation's score

        Returns:
            Maximum score in espionage range
        """
        return nation_score * 2.50

    @staticmethod
    def calculate_nation_score_from_min(min_score: float) -> float:
        """
        Calculate nation score from minimum espionage range score.

        Formula: Nation Score = Min Score / 0.40

        Args:
            min_score: Minimum score in espionage range

        Returns:
            Nation's score
        """
        return min_score / 0.40

    @staticmethod
    def calculate_nation_score_from_max(max_score: float) -> float:
        """
        Calculate nation score from maximum espionage range score.

        Formula: Nation Score = Max Score / 2.50

        Args:
            max_score: Maximum score in espionage range

        Returns:
            Nation's score
        """
        return max_score / 2.50

    @staticmethod
    def get_espionage_range(nation_score: float) -> Tuple[float, float]:
        """
        Get full espionage range for a nation.

        Args:
            nation_score: Nation's score

        Returns:
            Tuple of (min_score, max_score)
        """
        return (
            SpyCalculator.calculate_espionage_range_min(nation_score),
            SpyCalculator.calculate_espionage_range_max(nation_score)
        )

    @staticmethod
    def can_espionage_target(attacker_score: float, target_score: float) -> bool:
        """
        Check if attacker can espionage target based on score ranges.

        Args:
            attacker_score: Attacker's nation score
            target_score: Target's nation score

        Returns:
            True if target is within attacker's espionage range
        """
        min_score = SpyCalculator.calculate_espionage_range_min(attacker_score)
        max_score = SpyCalculator.calculate_espionage_range_max(attacker_score)
        return min_score <= target_score <= max_score


class EspionageOperationExecutor:
    """Executor for espionage operations."""

    def __init__(self, db_connection):
        """
        Initialize the executor with a database connection.

        Args:
            db_connection: Database connection to GlobalNationsDB
        """
        self.db = db_connection

    def get_nation_data(self, nation_id: int) -> Optional[NationData]:
        """
        Retrieve nation data from database.

        Args:
            nation_id: Nation ID to retrieve

        Returns:
            NationData object or None if not found
        """
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT 
                    id, nation_name, spies, soldiers, tanks, aircraft, ships,
                    missiles, nukes, war_policy, spy_satellite, money,
                    coal, oil, uranium, iron, bauxite, lead, gasoline,
                    munitions, steel, aluminum, food
                FROM nations
                WHERE id = ?
            """, (nation_id,))
            
            row = cursor.fetchone()
            if not row:
                return None

            # Get city data for infrastructure operations
            cursor.execute("""
                SELECT id, name, infrastructure
                FROM cities
                WHERE nation_id = ?
                ORDER BY infrastructure DESC
            """, (nation_id,))
            cities = [{"id": r[0], "name": r[1], "infrastructure": r[2]} for r in cursor.fetchall()]

            resources = {
                "coal": row[12] or 0.0,
                "oil": row[13] or 0.0,
                "uranium": row[14] or 0.0,
                "iron": row[15] or 0.0,
                "bauxite": row[16] or 0.0,
                "lead": row[17] or 0.0,
                "gasoline": row[18] or 0.0,
                "munitions": row[19] or 0.0,
                "steel": row[20] or 0.0,
                "aluminum": row[21] or 0.0,
                "food": row[22] or 0.0,
            }

            return NationData(
                nation_id=row[0],
                nation_name=row[1],
                spies=row[2] or 0,
                soldiers=row[3] or 0,
                tanks=row[4] or 0,
                aircraft=row[5] or 0,
                ships=row[6] or 0,
                missiles=row[7] or 0,
                nukes=row[8] or 0,
                war_policy=row[9],
                spy_satellite=bool(row[10]),
                cities=cities,
                money=row[11] or 0.0,
                resources=resources
            )
        except Exception as e:
            logger.error(f"Error retrieving nation data for {nation_id}: {e}")
            return None

    def check_missile_nuke_eligibility(
        self,
        defender: NationData,
        operation: EspionageOperation
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if defender is eligible for missile/nuke sabotage.

        - Mission automatically fails if defender has 0 missiles/nukes
        - Cannot destroy if it's the defender's only missile/nuke and built within last daychange

        Args:
            defender: Defender nation data
            operation: Operation type

        Returns:
            Tuple of (is_eligible, error_message)
        """
        if operation == EspionageOperation.SABOTAGE_MISSILES:
            if defender.missiles == 0:
                return False, "Defender has 0 missiles"
            # Note: Cannot check "built within last daychange" without additional data
            # This would require tracking missile acquisition times
        elif operation == EspionageOperation.SABOTAGE_NUCLEAR_WEAPONS:
            if defender.nukes == 0:
                return False, "Defender has 0 nuclear weapons"
            # Note: Cannot check "built within last daychange" without additional data

        return True, None

    def execute_gather_intelligence(
        self,
        attacker: NationData,
        defender: NationData,
        safety_level: SafetyLevel
    ) -> EspionageResult:
        """
        Execute Gather Intelligence operation.

        Reveals enemy spies, money, and resources.

        Args:
            attacker: Attacker nation data
            defender: Defender nation data
            safety_level: Safety level of operation

        Returns:
            EspionageResult with operation outcome
        """
        odds = SpyCalculator.calculate_final_odds(
            attacker.spies, defender.spies, safety_level,
            EspionageOperation.GATHER_INTELLIGENCE,
            attacker.war_policy, defender.war_policy
        )

        success = SpyCalculator.roll_success(odds)
        detected = not SpyCalculator.roll_detection(odds)
        attacker_spies_lost = SpyCalculator.calculate_attacker_casualties(
            attacker.spies, odds, detected
        )

        intelligence = None
        if success:
            intelligence = {
                "spies": defender.spies,
                "money": defender.money,
                "resources": defender.resources.copy(),
            }

        return EspionageResult(
            operation=EspionageOperation.GATHER_INTELLIGENCE,
            success=success,
            detected=detected,
            odds=odds,
            attacker_spies_lost=attacker_spies_lost,
            intelligence_gathered=intelligence
        )

    def execute_assassinate_spies(
        self,
        attacker: NationData,
        defender: NationData,
        safety_level: SafetyLevel
    ) -> EspionageResult:
        """
        Execute Assassinate Spies operation.

        Kills enemy spies. Formula:
        Random value between 85% and 105% of [Attacking Spies - (Defending Spies * 0.4)] * 0.5
        Max cap: (Defending Spies * 0.25) + 4
        Spy satellite makes value * 1.5

        Args:
            attacker: Attacker nation data
            defender: Defender nation data
            safety_level: Safety level of operation

        Returns:
            EspionageResult with operation outcome
        """
        odds = SpyCalculator.calculate_final_odds(
            attacker.spies, defender.spies, safety_level,
            EspionageOperation.ASSASSINATE_SPIES,
            attacker.war_policy, defender.war_policy
        )

        success = SpyCalculator.roll_success(odds)
        detected = not SpyCalculator.roll_detection(odds)
        attacker_spies_lost = SpyCalculator.calculate_attacker_casualties(
            attacker.spies, odds, detected
        )

        defender_spies_killed = 0
        if success:
            base_value = (attacker.spies - (defender.spies * 0.4)) * 0.5
            if base_value > 0:
                random_multiplier = random.uniform(0.85, 1.05)
                kills = base_value * random_multiplier
                max_cap = (defender.spies * 0.25) + 4
                kills = min(kills, max_cap)

                # Spy satellite multiplier
                if defender.spy_satellite:
                    kills *= 1.5

                # Cap at actual defender spy count (can't kill more than they have)
                defender_spies_killed = min(int(kills), defender.spies)

        return EspionageResult(
            operation=EspionageOperation.ASSASSINATE_SPIES,
            success=success,
            detected=detected,
            odds=odds,
            attacker_spies_lost=attacker_spies_lost,
            defender_spies_killed=defender_spies_killed
        )

    def execute_terrorize_civilians(
        self,
        attacker: NationData,
        defender: NationData,
        safety_level: SafetyLevel
    ) -> EspionageResult:
        """
        Execute Terrorize Civilians operation.

        Destroys infrastructure in target's highest infrastructure city.
        Max (60 spies vs 0 spies): 34.5 infrastructure
        Spy satellite makes value * 1.5

        Args:
            attacker: Attacker nation data
            defender: Defender nation data
            safety_level: Safety level of operation

        Returns:
            EspionageResult with operation outcome
        """
        odds = SpyCalculator.calculate_final_odds(
            attacker.spies, defender.spies, safety_level,
            EspionageOperation.TERRORIZE_CIVILIANS,
            attacker.war_policy, defender.war_policy
        )

        success = SpyCalculator.roll_success(odds)
        detected = not SpyCalculator.roll_detection(odds)
        attacker_spies_lost = SpyCalculator.calculate_attacker_casualties(
            attacker.spies, odds, detected
        )

        infra_destroyed = 0.0
        if success and defender.cities:
            # Calculate infrastructure destruction based on spy ratio
            # Max is 34.5 with 60 spies vs 0 spies
            spy_ratio = min(attacker.spies / 60.0, 1.0)
            base_destruction = 34.5 * spy_ratio

            # Spy satellite multiplier
            if defender.spy_satellite:
                base_destruction *= 1.5

            infra_destroyed = base_destruction

        return EspionageResult(
            operation=EspionageOperation.TERRORIZE_CIVILIANS,
            success=success,
            detected=detected,
            odds=odds,
            attacker_spies_lost=attacker_spies_lost,
            infrastructure_destroyed=infra_destroyed
        )

    def execute_sabotage_soldiers(
        self,
        attacker: NationData,
        defender: NationData,
        safety_level: SafetyLevel
    ) -> EspionageResult:
        """
        Execute Sabotage Soldiers operation.

        Kills 1-5% of target's total soldiers.
        Spy satellite makes value * 1.5

        Args:
            attacker: Attacker nation data
            defender: Defender nation data
            safety_level: Safety level of operation

        Returns:
            EspionageResult with operation outcome
        """
        odds = SpyCalculator.calculate_final_odds(
            attacker.spies, defender.spies, safety_level,
            EspionageOperation.SABOTAGE_SOLDIERS,
            attacker.war_policy, defender.war_policy
        )

        success = SpyCalculator.roll_success(odds)
        detected = not SpyCalculator.roll_detection(odds)
        attacker_spies_lost = SpyCalculator.calculate_attacker_casualties(
            attacker.spies, odds, detected
        )

        soldiers_killed = 0
        if success and defender.soldiers > 0:
            percentage = random.uniform(0.01, 0.05)
            kills = int(defender.soldiers * percentage)

            # Spy satellite multiplier
            if defender.spy_satellite:
                kills = int(kills * 1.5)

            # Cap at actual defender soldier count
            soldiers_killed = min(kills, defender.soldiers)

        return EspionageResult(
            operation=EspionageOperation.SABOTAGE_SOLDIERS,
            success=success,
            detected=detected,
            odds=odds,
            attacker_spies_lost=attacker_spies_lost,
            soldiers_killed=soldiers_killed
        )

    def execute_sabotage_tanks(
        self,
        attacker: NationData,
        defender: NationData,
        safety_level: SafetyLevel
    ) -> EspionageResult:
        """
        Execute Sabotage Tanks operation.

        Destroys 1-5% of target's total tanks.
        Spy satellite makes value * 1.5

        Args:
            attacker: Attacker nation data
            defender: Defender nation data
            safety_level: Safety level of operation

        Returns:
            EspionageResult with operation outcome
        """
        odds = SpyCalculator.calculate_final_odds(
            attacker.spies, defender.spies, safety_level,
            EspionageOperation.SABOTAGE_TANKS,
            attacker.war_policy, defender.war_policy
        )

        success = SpyCalculator.roll_success(odds)
        detected = not SpyCalculator.roll_detection(odds)
        attacker_spies_lost = SpyCalculator.calculate_attacker_casualties(
            attacker.spies, odds, detected
        )

        tanks_destroyed = 0
        if success and defender.tanks > 0:
            percentage = random.uniform(0.01, 0.05)
            destroyed = int(defender.tanks * percentage)

            # Spy satellite multiplier
            if defender.spy_satellite:
                destroyed = int(destroyed * 1.5)

            # Cap at actual defender tank count
            tanks_destroyed = min(destroyed, defender.tanks)

        return EspionageResult(
            operation=EspionageOperation.SABOTAGE_TANKS,
            success=success,
            detected=detected,
            odds=odds,
            attacker_spies_lost=attacker_spies_lost,
            tanks_destroyed=tanks_destroyed
        )

    def execute_sabotage_aircraft(
        self,
        attacker: NationData,
        defender: NationData,
        safety_level: SafetyLevel
    ) -> EspionageResult:
        """
        Execute Sabotage Aircraft operation.

        Destroys 1-5% of target's total aircraft.
        Spy satellite makes value * 1.5

        Args:
            attacker: Attacker nation data
            defender: Defender nation data
            safety_level: Safety level of operation

        Returns:
            EspionageResult with operation outcome
        """
        odds = SpyCalculator.calculate_final_odds(
            attacker.spies, defender.spies, safety_level,
            EspionageOperation.SABOTAGE_AIRCRAFT,
            attacker.war_policy, defender.war_policy
        )

        success = SpyCalculator.roll_success(odds)
        detected = not SpyCalculator.roll_detection(odds)
        attacker_spies_lost = SpyCalculator.calculate_attacker_casualties(
            attacker.spies, odds, detected
        )

        aircraft_destroyed = 0
        if success and defender.aircraft > 0:
            percentage = random.uniform(0.01, 0.05)
            destroyed = int(defender.aircraft * percentage)

            # Spy satellite multiplier
            if defender.spy_satellite:
                destroyed = int(destroyed * 1.5)

            # Cap at actual defender aircraft count
            aircraft_destroyed = min(destroyed, defender.aircraft)

        return EspionageResult(
            operation=EspionageOperation.SABOTAGE_AIRCRAFT,
            success=success,
            detected=detected,
            odds=odds,
            attacker_spies_lost=attacker_spies_lost,
            aircraft_destroyed=aircraft_destroyed
        )

    def execute_sabotage_ships(
        self,
        attacker: NationData,
        defender: NationData,
        safety_level: SafetyLevel
    ) -> EspionageResult:
        """
        Execute Sabotage Ships operation.

        Destroys 1-5% of target's total ships.
        Spy satellite makes value * 1.5

        Args:
            attacker: Attacker nation data
            defender: Defender nation data
            safety_level: Safety level of operation

        Returns:
            EspionageResult with operation outcome
        """
        odds = SpyCalculator.calculate_final_odds(
            attacker.spies, defender.spies, safety_level,
            EspionageOperation.SABOTAGE_SHIPS,
            attacker.war_policy, defender.war_policy
        )

        success = SpyCalculator.roll_success(odds)
        detected = not SpyCalculator.roll_detection(odds)
        attacker_spies_lost = SpyCalculator.calculate_attacker_casualties(
            attacker.spies, odds, detected
        )

        ships_destroyed = 0
        if success and defender.ships > 0:
            percentage = random.uniform(0.01, 0.05)
            destroyed = int(defender.ships * percentage)

            # Spy satellite multiplier
            if defender.spy_satellite:
                destroyed = int(destroyed * 1.5)

            # Cap at actual defender ship count
            ships_destroyed = min(destroyed, defender.ships)

        return EspionageResult(
            operation=EspionageOperation.SABOTAGE_SHIPS,
            success=success,
            detected=detected,
            odds=odds,
            attacker_spies_lost=attacker_spies_lost,
            ships_destroyed=ships_destroyed
        )

    def execute_sabotage_missiles(
        self,
        attacker: NationData,
        defender: NationData,
        safety_level: SafetyLevel
    ) -> EspionageResult:
        """
        Execute Sabotage Missiles operation.

        Destroys 1 missile with 25% chance to destroy an additional missile.
        Spy satellite makes value * 1.5 (applies to the chance or count?)

        Args:
            attacker: Attacker nation data
            defender: Defender nation data
            safety_level: Safety level of operation

        Returns:
            EspionageResult with operation outcome
        """
        # Check eligibility
        eligible, error_msg = self.check_missile_nuke_eligibility(
            defender, EspionageOperation.SABOTAGE_MISSILES
        )

        if not eligible:
            return EspionageResult(
                operation=EspionageOperation.SABOTAGE_MISSILES,
                success=False,
                detected=False,
                odds=0.0,
                error_message=error_msg
            )

        odds = SpyCalculator.calculate_final_odds(
            attacker.spies, defender.spies, safety_level,
            EspionageOperation.SABOTAGE_MISSILES,
            attacker.war_policy, defender.war_policy
        )

        success = SpyCalculator.roll_success(odds)
        detected = not SpyCalculator.roll_detection(odds)
        attacker_spies_lost = SpyCalculator.calculate_attacker_casualties(
            attacker.spies, odds, detected
        )

        missiles_destroyed = 0
        if success:
            missiles_destroyed = 1

            # 25% chance for additional missile
            if random.random() < 0.25:
                missiles_destroyed += 1

            # Cap at available missiles
            missiles_destroyed = min(missiles_destroyed, defender.missiles)

        return EspionageResult(
            operation=EspionageOperation.SABOTAGE_MISSILES,
            success=success,
            detected=detected,
            odds=odds,
            attacker_spies_lost=attacker_spies_lost,
            missiles_destroyed=missiles_destroyed
        )

    def execute_sabotage_nuclear_weapons(
        self,
        attacker: NationData,
        defender: NationData,
        safety_level: SafetyLevel
    ) -> EspionageResult:
        """
        Execute Sabotage Nuclear Weapons operation.

        Destroys 1 nuclear weapon.
        Spy satellite makes value * 1.5 (applies to the chance or count?)

        Args:
            attacker: Attacker nation data
            defender: Defender nation data
            safety_level: Safety level of operation

        Returns:
            EspionageResult with operation outcome
        """
        # Check eligibility
        eligible, error_msg = self.check_missile_nuke_eligibility(
            defender, EspionageOperation.SABOTAGE_NUCLEAR_WEAPONS
        )

        if not eligible:
            return EspionageResult(
                operation=EspionageOperation.SABOTAGE_NUCLEAR_WEAPONS,
                success=False,
                detected=False,
                odds=0.0,
                error_message=error_msg
            )

        odds = SpyCalculator.calculate_final_odds(
            attacker.spies, defender.spies, safety_level,
            EspionageOperation.SABOTAGE_NUCLEAR_WEAPONS,
            attacker.war_policy, defender.war_policy
        )

        success = SpyCalculator.roll_success(odds)
        detected = not SpyCalculator.roll_detection(odds)
        attacker_spies_lost = SpyCalculator.calculate_attacker_casualties(
            attacker.spies, odds, detected
        )

        nukes_destroyed = 0
        if success:
            nukes_destroyed = 1
            # Cap at available nukes
            nukes_destroyed = min(nukes_destroyed, defender.nukes)

        return EspionageResult(
            operation=EspionageOperation.SABOTAGE_NUCLEAR_WEAPONS,
            success=success,
            detected=detected,
            odds=odds,
            attacker_spies_lost=attacker_spies_lost,
            nukes_destroyed=nukes_destroyed
        )

    def execute_operation(
        self,
        attacker_nation_id: int,
        defender_nation_id: int,
        operation: EspionageOperation,
        safety_level: SafetyLevel,
        attacker_spies_override: Optional[int] = None
    ) -> EspionageResult:
        """
        Execute an espionage operation.

        Args:
            attacker_nation_id: ID of attacking nation
            defender_nation_id: ID of defending nation
            operation: Type of espionage operation
            safety_level: Safety level of operation
            attacker_spies_override: Override attacker spy count (for simulations)

        Returns:
            EspionageResult with operation outcome
        """
        attacker = self.get_nation_data(attacker_nation_id)
        defender = self.get_nation_data(defender_nation_id)

        if not attacker:
            return EspionageResult(
                operation=operation,
                success=False,
                detected=False,
                odds=0.0,
                error_message=f"Attacker nation {attacker_nation_id} not found"
            )

        if not defender:
            return EspionageResult(
                operation=operation,
                success=False,
                detected=False,
                odds=0.0,
                error_message=f"Defender nation {defender_nation_id} not found"
            )

        # Override attacker spies if specified (for simulations)
        if attacker_spies_override is not None:
            attacker.spies = attacker_spies_override

        # Dispatch to appropriate operation handler
        operation_handlers = {
            EspionageOperation.GATHER_INTELLIGENCE: self.execute_gather_intelligence,
            EspionageOperation.ASSASSINATE_SPIES: self.execute_assassinate_spies,
            EspionageOperation.TERRORIZE_CIVILIANS: self.execute_terrorize_civilians,
            EspionageOperation.SABOTAGE_SOLDIERS: self.execute_sabotage_soldiers,
            EspionageOperation.SABOTAGE_TANKS: self.execute_sabotage_tanks,
            EspionageOperation.SABOTAGE_AIRCRAFT: self.execute_sabotage_aircraft,
            EspionageOperation.SABOTAGE_SHIPS: self.execute_sabotage_ships,
            EspionageOperation.SABOTAGE_MISSILES: self.execute_sabotage_missiles,
            EspionageOperation.SABOTAGE_NUCLEAR_WEAPONS: self.execute_sabotage_nuclear_weapons,
        }

        handler = operation_handlers.get(operation)
        if not handler:
            return EspionageResult(
                operation=operation,
                success=False,
                detected=False,
                odds=0.0,
                error_message=f"Unknown operation: {operation}"
            )

        return handler(attacker, defender, safety_level)


class SpyAnalyzer:
    """Analyzer for espionage operations and optimal spy calculations."""

    def __init__(self, db_connection):
        """
        Initialize the analyzer with a database connection.

        Args:
            db_connection: Database connection to GlobalNationsDB
        """
        self.db = db_connection
        self.executor = EspionageOperationExecutor(db_connection)

    def calculate_odds_for_nation(
        self,
        attacker_spies: int,
        defender_nation_id: int,
        operation: EspionageOperation,
        safety_level: SafetyLevel,
        attacker_war_policy: Optional[str] = None
    ) -> Optional[float]:
        """
        Calculate odds for an operation against a specific nation.

        Args:
            attacker_spies: Number of attacking spies
            defender_nation_id: ID of defending nation
            operation: Type of espionage operation
            safety_level: Safety level of operation
            attacker_war_policy: Attacker's war policy

        Returns:
            Final odds or None if nation not found
        """
        defender = self.executor.get_nation_data(defender_nation_id)
        if not defender:
            return None

        return SpyCalculator.calculate_final_odds(
            attacker_spies, defender.spies, safety_level,
            operation, attacker_war_policy, defender.war_policy
        )

    def find_optimal_spies_for_operation(
        self,
        defender_nation_id: int,
        operation: EspionageOperation,
        safety_level: SafetyLevel,
        target_odds: float = 95.0,
        attacker_war_policy: Optional[str] = None,
        max_spies: int = 100
    ) -> Optional[Dict]:
        """
        Find the minimum number of spies needed to achieve target odds.

        Args:
            defender_nation_id: ID of defending nation
            operation: Type of espionage operation
            safety_level: Safety level of operation
            target_odds: Desired odds (default 95%)
            attacker_war_policy: Attacker's war policy
            max_spies: Maximum spies to check

        Returns:
            Dictionary with optimal spies and actual odds, or None if nation not found
        """
        defender = self.executor.get_nation_data(defender_nation_id)
        if not defender:
            return None

        # Binary search for minimum spies to achieve target odds
        low, high = 0, max_spies
        optimal_spies = max_spies

        while low <= high:
            mid = (low + high) // 2
            odds = SpyCalculator.calculate_final_odds(
                mid, defender.spies, safety_level,
                operation, attacker_war_policy, defender.war_policy
            )

            if odds >= target_odds:
                optimal_spies = mid
                high = mid - 1
            else:
                low = mid + 1

        actual_odds = SpyCalculator.calculate_final_odds(
            optimal_spies, defender.spies, safety_level,
            operation, attacker_war_policy, defender.war_policy
        )

        return {
            "optimal_spies": optimal_spies,
            "actual_odds": actual_odds,
            "defender_spies": defender.spies,
            "defender_war_policy": defender.war_policy
        }

    def analyze_alliance_vs_alliance(
        self,
        attacker_alliance_id: int,
        defender_alliance_id: int,
        operation: EspionageOperation,
        safety_level: SafetyLevel,
        attacker_spies_per_nation: int = 50
    ) -> Dict:
        """
        Analyze espionage operations between two alliances.

        Args:
            attacker_alliance_id: ID of attacking alliance
            defender_alliance_id: ID of defending alliance
            operation: Type of espionage operation
            safety_level: Safety level of operation
            attacker_spies_per_nation: Spies to assume per attacking nation

        Returns:
            Dictionary with analysis results
        """
        cursor = self.db.cursor()

        # Get attacker nations
        cursor.execute("""
            SELECT id, nation_name, spies, war_policy
            FROM nations
            WHERE alliance_id = ? AND spies > 0
        """, (attacker_alliance_id,))
        attacker_nations = [
            {
                "id": row[0],
                "name": row[1],
                "spies": row[2],
                "war_policy": row[3]
            }
            for row in cursor.fetchall()
        ]

        # Get defender nations
        cursor.execute("""
            SELECT id, nation_name, spies, war_policy
            FROM nations
            WHERE alliance_id = ?
        """, (defender_alliance_id,))
        defender_nations = [
            {
                "id": row[0],
                "name": row[1],
                "spies": row[2],
                "war_policy": row[3]
            }
            for row in cursor.fetchall()
        ]

        results = []
        for attacker in attacker_nations:
            for defender in defender_nations:
                odds = SpyCalculator.calculate_final_odds(
                    attacker_spies_per_nation, defender["spies"], safety_level,
                    operation, attacker["war_policy"], defender["war_policy"]
                )

                results.append({
                    "attacker": attacker["name"],
                    "attacker_id": attacker["id"],
                    "defender": defender["name"],
                    "defender_id": defender["id"],
                    "odds": odds,
                    "attacker_spies": attacker_spies_per_nation,
                    "defender_spies": defender["spies"]
                })

        # Sort by odds descending
        results.sort(key=lambda x: x["odds"], reverse=True)

        return {
            "attacker_alliance_id": attacker_alliance_id,
            "defender_alliance_id": defender_alliance_id,
            "operation": operation.value,
            "safety_level": safety_level.value,
            "attacker_spies_per_nation": attacker_spies_per_nation,
            "total_matchups": len(results),
            "high_odds_matchups": len([r for r in results if r["odds"] >= 80]),
            "medium_odds_matchups": len([r for r in results if 50 <= r["odds"] < 80]),
            "low_odds_matchups": len([r for r in results if r["odds"] < 50]),
            "matchups": results
        }

    def get_nations_by_alliance(self, alliance_id: int) -> List[Dict]:
        """
        Get all nations in an alliance with relevant espionage data.

        Args:
            alliance_id: Alliance ID

        Returns:
            List of nation dictionaries
        """
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT 
                id, nation_name, spies, soldiers, tanks, aircraft, ships,
                missiles, nukes, war_policy, spy_satellite, score
            FROM nations
            WHERE alliance_id = ?
            ORDER BY spies DESC
        """, (alliance_id,))

        return [
            {
                "id": row[0],
                "name": row[1],
                "spies": row[2],
                "soldiers": row[3],
                "tanks": row[4],
                "aircraft": row[5],
                "ships": row[6],
                "missiles": row[7],
                "nukes": row[8],
                "war_policy": row[9],
                "spy_satellite": bool(row[10]),
                "score": row[11]
            }
            for row in cursor.fetchall()
        ]
