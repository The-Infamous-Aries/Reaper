"""
Spy Command Module for Politics & War

Provides commands for espionage operations and calculations.
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
import sqlite3
from typing import Optional, Dict, Any, List, Tuple

from Systems.PnW.Util.spy_calc import (
    SpyCalculator,
    EspionageOperation,
    SafetyLevel,
    NationData,
    EspionageOperationExecutor
)

logger = logging.getLogger(__name__)

# Database path
DB_PATH = "Databases/PnW/GlobalNations.db"


# ── Module-level autocomplete functions ───────────────────────────────────────
# Must be defined at module level so @app_commands.autocomplete can bind them

async def _spy_attacker_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> List[app_commands.Choice[str]]:
    """Autocomplete for the spy command's attacker parameter."""
    try:
        from Systems.Functions.autocomplete_utils import nation_autocomplete
        return await nation_autocomplete(current, nw_only=False, limit=25)
    except Exception as e:
        logger.error(f"spy attacker autocomplete error: {e}")
        return []


async def _spy_defender_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> List[app_commands.Choice[str]]:
    """Autocomplete for the spy command's defender parameter."""
    try:
        from Systems.Functions.autocomplete_utils import nation_autocomplete
        return await nation_autocomplete(current, nw_only=False, limit=25)
    except Exception as e:
        logger.error(f"spy defender autocomplete error: {e}")
        return []


def get_nation_from_db(identifier: str) -> Optional[Dict[str, Any]]:
    """
    Fetch nation data from GlobalNations.db by name, leader, or ID.

    Includes all relevant fields for espionage calculations:
    - spies, war_policy, spy_satellite
    - soldiers, tanks, aircraft, ships, missiles, nukes
    - projects (spy_satellite, etc.)
    - score (for espionage range)

    Args:
        identifier: Nation name, leader name, or ID

    Returns:
        Dictionary with nation data or None if not found
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Try by ID first
        if identifier.isdigit():
            cursor.execute("""
                SELECT
                    id, nation_name, leader_name, score,
                    spies, soldiers, tanks, aircraft, ships, missiles, nukes,
                    war_policy, spy_satellite,
                    iron_dome, vital_defense_system, missile_launch_pad,
                    nuclear_research_facility, nuclear_launch_facility,
                    propaganda_bureau, military_research_center, space_program,
                    surveillance_network, guiding_satellite,
                    telecommunications_satellite, central_intelligence_agency,
                    fallout_shelter, military_doctrine, military_salvage,
                    pirate_economy, advanced_pirate_economy, arms_stockpile,
                    bauxite_works, iron_works, emergency_gasoline_reserve,
                    uranium_enrichment_program, green_technologies,
                    recycling_initiative, mass_irrigation, arable_land_agency,
                    international_trade_center, clinical_research_center,
                    specialized_police_training_program, bureau_of_domestic_affairs,
                    government_support_agency, center_for_civil_engineering,
                    advanced_engineering_corps, activity_center,
                    research_and_development_center, moon_landing, mars_landing,
                    money, coal, oil, uranium, iron, bauxite, lead,
                    gasoline, munitions, steel, aluminum, food
                FROM nations WHERE id = ?
            """, (identifier,))
        else:
            # Try by name or leader
            cursor.execute("""
                SELECT
                    id, nation_name, leader_name, score,
                    spies, soldiers, tanks, aircraft, ships, missiles, nukes,
                    war_policy, spy_satellite,
                    iron_dome, vital_defense_system, missile_launch_pad,
                    nuclear_research_facility, nuclear_launch_facility,
                    propaganda_bureau, military_research_center, space_program,
                    surveillance_network, guiding_satellite,
                    telecommunications_satellite, central_intelligence_agency,
                    fallout_shelter, military_doctrine, military_salvage,
                    pirate_economy, advanced_pirate_economy, arms_stockpile,
                    bauxite_works, iron_works, emergency_gasoline_reserve,
                    uranium_enrichment_program, green_technologies,
                    recycling_initiative, mass_irrigation, arable_land_agency,
                    international_trade_center, clinical_research_center,
                    specialized_police_training_program, bureau_of_domestic_affairs,
                    government_support_agency, center_for_civil_engineering,
                    advanced_engineering_corps, activity_center,
                    research_and_development_center, moon_landing, mars_landing,
                    money, coal, oil, uranium, iron, bauxite, lead,
                    gasoline, munitions, steel, aluminum, food
                FROM nations WHERE nation_name LIKE ? OR leader_name LIKE ?
            """, (f"%{identifier}%", f"%{identifier}%"))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        # Structure the nation data
        return {
            'nation_id': row[0],
            'nation_name': row[1],
            'leader_name': row[2],
            'score': row[3],
            'spies': row[4] or 0,
            'soldiers': row[5] or 0,
            'tanks': row[6] or 0,
            'aircraft': row[7] or 0,
            'ships': row[8] or 0,
            'missiles': row[9] or 0,
            'nukes': row[10] or 0,
            'war_policy': row[11],
            'spy_satellite': bool(row[12]),
            # Projects
            'iron_dome': bool(row[13]),
            'vital_defense_system': bool(row[14]),
            'missile_launch_pad': bool(row[15]),
            'nuclear_research_facility': bool(row[16]),
            'nuclear_launch_facility': bool(row[17]),
            'propaganda_bureau': bool(row[18]),
            'military_research_center': bool(row[19]),
            'space_program': bool(row[20]),
            'surveillance_network': bool(row[21]),
            'guiding_satellite': bool(row[22]),
            'telecommunications_satellite': bool(row[23]),
            'central_intelligence_agency': bool(row[24]),
            'fallout_shelter': bool(row[25]),
            'military_doctrine': bool(row[26]),
            'military_salvage': bool(row[27]),
            'pirate_economy': bool(row[28]),
            'advanced_pirate_economy': bool(row[29]),
            'arms_stockpile': bool(row[30]),
            'bauxite_works': bool(row[31]),
            'iron_works': bool(row[32]),
            'emergency_gasoline_reserve': bool(row[33]),
            'uranium_enrichment_program': bool(row[34]),
            'green_technologies': bool(row[35]),
            'recycling_initiative': bool(row[36]),
            'mass_irrigation': bool(row[37]),
            'arable_land_agency': bool(row[38]),
            'international_trade_center': bool(row[39]),
            'clinical_research_center': bool(row[40]),
            'specialized_police_training_program': bool(row[41]),
            'bureau_of_domestic_affairs': bool(row[42]),
            'government_support_agency': bool(row[43]),
            'center_for_civil_engineering': bool(row[44]),
            'advanced_engineering_corps': bool(row[45]),
            'activity_center': bool(row[46]),
            'research_and_development_center': bool(row[47]),
            'moon_landing': bool(row[48]),
            'mars_landing': bool(row[49]),
            # Resources
            'money': row[50] or 0.0,
            'coal': row[51] or 0.0,
            'oil': row[52] or 0.0,
            'uranium': row[53] or 0.0,
            'iron': row[54] or 0.0,
            'bauxite': row[55] or 0.0,
            'lead': row[56] or 0.0,
            'gasoline': row[57] or 0.0,
            'munitions': row[58] or 0.0,
            'steel': row[59] or 0.0,
            'aluminum': row[60] or 0.0,
            'food': row[61] or 0.0,
        }
    except Exception as e:
        logger.error(f"Error fetching nation from DB: {e}")
        return None


def find_optimal_spies_safety(
    attacker_spies: int,
    defender_spies: int,
    operation: EspionageOperation,
    attacker_war_policy: Optional[str],
    defender_war_policy: Optional[str],
    target_odds: float = 95.0,
    max_spies_override: Optional[int] = None
) -> Tuple[int, SafetyLevel, float]:
    """
    Find the optimal combination of spies and safety level to achieve target odds.

    Strategy:
    1. Try with safety level 1 (Quick and Dirty) first - cheapest
    2. Only increase safety level if needed to reach target odds
    3. Find minimum spies needed for each safety level
    4. Return the combination with lowest total "cost" (spies + safety level)

    Args:
        attacker_spies: Maximum available spies
        defender_spies: Defender's spy count
        operation: Type of espionage operation
        attacker_war_policy: Attacker's war policy
        defender_war_policy: Defender's war policy
        target_odds: Desired odds (default 95%)
        max_spies_override: Override max spies to check

    Returns:
        Tuple of (spies_needed, safety_level, actual_odds)
    """
    max_spies = max_spies_override if max_spies_override else attacker_spies

    # Try each safety level from cheapest to most expensive
    for safety_level in [SafetyLevel.QUICK_AND_DIRTY, SafetyLevel.NORMAL_PRECAUTIONS, SafetyLevel.EXTREMELY_COVERT]:
        # Binary search for minimum spies to achieve target odds
        low, high = 0, max_spies
        optimal_spies = max_spies

        while low <= high:
            mid = (low + high) // 2
            odds = SpyCalculator.calculate_final_odds(
                mid, defender_spies, safety_level,
                operation, attacker_war_policy, defender_war_policy
            )

            if odds >= target_odds:
                optimal_spies = mid
                high = mid - 1
            else:
                low = mid + 1

        actual_odds = SpyCalculator.calculate_final_odds(
            optimal_spies, defender_spies, safety_level,
            operation, attacker_war_policy, defender_war_policy
        )

        # If we can achieve target odds with this safety level, return it
        if actual_odds >= target_odds:
            return optimal_spies, safety_level, actual_odds

    # If we can't reach target odds even with max spies and highest safety level
    # Return the best we found (max spies, highest safety level)
    best_odds = SpyCalculator.calculate_final_odds(
        max_spies, defender_spies, SafetyLevel.EXTREMELY_COVERT,
        operation, attacker_war_policy, defender_war_policy
    )
    return max_spies, SafetyLevel.EXTREMELY_COVERT, best_odds


def _strip_emoji(value: str) -> str:
    """Strip emoji prefix from autocomplete values."""
    if not value:
        return value
    parts = value.split(" ", 1)
    if len(parts) == 2 and len(parts[0]) <= 2:
        return parts[1].strip()
    return value.strip()


def _nation_link(name: str, nation_id: int) -> str:
    """Create a clickable nation link."""
    return f"[{name}](https://politicsandwar.com/nation/id={nation_id})"


def _nation_link_masked(leader: str, nation: str, nation_id: int) -> str:
    """Create a masked nation link showing 'Leader of Nation'."""
    return f"[{leader} of {nation}](https://politicsandwar.com/nation/id={nation_id})"


# Espionage operation choices for dropdown
ESPIONAGE_TYPE_CHOICES = [
    app_commands.Choice(name="Gather Intelligence", value="gather_intelligence"),
    app_commands.Choice(name="Assassinate Spies", value="assassinate_spies"),
    app_commands.Choice(name="Terrorize Civilians", value="terrorize_civilians"),
    app_commands.Choice(name="Sabotage Soldiers", value="sabotage_soldiers"),
    app_commands.Choice(name="Sabotage Tanks", value="sabotage_tanks"),
    app_commands.Choice(name="Sabotage Aircraft", value="sabotage_aircraft"),
    app_commands.Choice(name="Sabotage Ships", value="sabotage_ships"),
    app_commands.Choice(name="Sabotage Missiles", value="sabotage_missiles"),
    app_commands.Choice(name="Sabotage Nuclear Weapons", value="sabotage_nuclear_weapons"),
]

# Desired outcome choices for dropdown
DESIRED_OUTCOME_CHOICES = [
    app_commands.Choice(name="Least Cost & Best Odds", value="least_cost"),
    app_commands.Choice(name="Most Destruction", value="most_destruction"),
]


class SpyCog(commands.Cog):
    """Cog for espionage commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="spy_chance",
        description="Calculate espionage operation odds and optimal spy allocation"
    )
    @app_commands.describe(
        attacker="Attacker nation (use autocomplete)",
        defender="Defender nation (use autocomplete)",
        espionage_type="Type of espionage operation",
        desired_outcome="Optimization strategy"
    )
    @app_commands.choices(espionage_type=ESPIONAGE_TYPE_CHOICES, desired_outcome=DESIRED_OUTCOME_CHOICES)
    @app_commands.autocomplete(attacker=_spy_attacker_autocomplete, defender=_spy_defender_autocomplete)
    async def spy_chance(
        self,
        interaction: discord.Interaction,
        attacker: str,
        defender: str,
        espionage_type: str,
        desired_outcome: str = "least_cost"
    ):
        """Calculate espionage operation odds and optimal spy allocation."""
        await interaction.response.defer()

        # Strip emoji prefixes from autocomplete values
        attacker_clean = _strip_emoji(attacker)
        defender_clean = _strip_emoji(defender)

        # Fetch nation data
        attacker_data = get_nation_from_db(attacker_clean)
        defender_data = get_nation_from_db(defender_clean)

        if not attacker_data:
            await interaction.followup.send(f"Attacker nation '{attacker_clean}' not found.", ephemeral=True)
            return

        if not defender_data:
            await interaction.followup.send(f"Defender nation '{defender_clean}' not found.", ephemeral=True)
            return

        # Convert string to EspionageOperation enum
        operation_map = {
            "gather_intelligence": EspionageOperation.GATHER_INTELLIGENCE,
            "assassinate_spies": EspionageOperation.ASSASSINATE_SPIES,
            "terrorize_civilians": EspionageOperation.TERRORIZE_CIVILIANS,
            "sabotage_soldiers": EspionageOperation.SABOTAGE_SOLDIERS,
            "sabotage_tanks": EspionageOperation.SABOTAGE_TANKS,
            "sabotage_aircraft": EspionageOperation.SABOTAGE_AIRCRAFT,
            "sabotage_ships": EspionageOperation.SABOTAGE_SHIPS,
            "sabotage_missiles": EspionageOperation.SABOTAGE_MISSILES,
            "sabotage_nuclear_weapons": EspionageOperation.SABOTAGE_NUCLEAR_WEAPONS,
        }

        operation = operation_map.get(espionage_type)
        if not operation:
            await interaction.followup.send(f"Unknown espionage type: {espionage_type}", ephemeral=True)
            return

        # Check espionage range
        can_target = SpyCalculator.can_espionage_target(
            attacker_data['score'],
            defender_data['score']
        )

        # Calculate espionage range
        min_range = SpyCalculator.calculate_espionage_range_min(attacker_data['score'])
        max_range = SpyCalculator.calculate_espionage_range_max(attacker_data['score'])

        # If out of range, show error embed
        if not can_target:
            embed = discord.Embed(
                title=f"❌ Out of Espionage Range",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )

            embed.add_field(
                name="🎯 Defender",
                value=_nation_link_masked(
                    defender_data['leader_name'],
                    defender_data['nation_name'],
                    defender_data['nation_id']
                ),
                inline=False
            )

            embed.add_field(
                name="📏 Espionage Range",
                value=f"**Your Range:** {min_range:,.0f} - {max_range:,.0f}\n"
                      f"**Defender Score:** {defender_data['score']:,.0f}",
                inline=False
            )

            embed.add_field(
                name="🔍 Defender Spies",
                value=f"{defender_data['spies']:,}",
                inline=True
            )

            def_policy = defender_data['war_policy'] or "None"
            embed.add_field(
                name="⚔️ War Policy",
                value=def_policy.title(),
                inline=True
            )

            def_sat = "✅" if defender_data['spy_satellite'] else "❌"
            embed.add_field(
                name="🛰️ Spy Satellite",
                value=def_sat,
                inline=True
            )

            embed.set_footer(text="Data from GlobalNations.db")
            await interaction.followup.send(embed=embed)
            return

        # Find optimal spies and safety level based on desired outcome
        if desired_outcome == "least_cost":
            # Least Cost & Best Odds: target 99% or highest possible
            spies_needed, safety_level, actual_odds = find_optimal_spies_safety(
                attacker_data['spies'],
                defender_data['spies'],
                operation,
                attacker_data['war_policy'],
                defender_data['war_policy'],
                99.0
            )
        else:
            # Most Destruction: use minimum spies for high odds if possible,
            # otherwise use all spies to maximize chances
            target_odds = 95.0

            # Try to find minimum spies for 95% odds
            spies_needed, safety_level, actual_odds = find_optimal_spies_safety(
                attacker_data['spies'],
                defender_data['spies'],
                operation,
                attacker_data['war_policy'],
                defender_data['war_policy'],
                target_odds
            )

            # If we can't reach 95% even with all spies, use all spies
            if actual_odds < 95.0:
                spies_needed = attacker_data['spies']
                # Find best safety level with all spies
                best_odds = 0
                best_safety = SafetyLevel.QUICK_AND_DIRTY
                for sl in [SafetyLevel.QUICK_AND_DIRTY, SafetyLevel.NORMAL_PRECAUTIONS, SafetyLevel.EXTREMELY_COVERT]:
                    odds = SpyCalculator.calculate_final_odds(
                        attacker_data['spies'],
                        defender_data['spies'],
                        sl,
                        operation,
                        attacker_data['war_policy'],
                        defender_data['war_policy']
                    )
                    if odds > best_odds:
                        best_odds = odds
                        best_safety = sl
                safety_level = best_safety
                actual_odds = best_odds

        # Safety level display names
        safety_names = {
            SafetyLevel.QUICK_AND_DIRTY: "Quick and Dirty (1)",
            SafetyLevel.NORMAL_PRECAUTIONS: "Normal Precautions (2)",
            SafetyLevel.EXTREMELY_COVERT: "Extremely Covert (3)",
        }

        # Operation display names
        operation_names = {
            EspionageOperation.GATHER_INTELLIGENCE: "Gather Intelligence",
            EspionageOperation.ASSASSINATE_SPIES: "Assassinate Spies",
            EspionageOperation.TERRORIZE_CIVILIANS: "Terrorize Civilians",
            EspionageOperation.SABOTAGE_SOLDIERS: "Sabotage Soldiers",
            EspionageOperation.SABOTAGE_TANKS: "Sabotage Tanks",
            EspionageOperation.SABOTAGE_AIRCRAFT: "Sabotage Aircraft",
            EspionageOperation.SABOTAGE_SHIPS: "Sabotage Ships",
            EspionageOperation.SABOTAGE_MISSILES: "Sabotage Missiles",
            EspionageOperation.SABOTAGE_NUCLEAR_WEAPONS: "Sabotage Nuclear Weapons",
        }

        # Create embed
        embed = discord.Embed(
            title=f"🕵️ Espionage Odds: {operation_names[operation]}",
            color=discord.Color.dark_purple(),
            timestamp=discord.utils.utcnow()
        )

        # Nations section with masked links
        embed.add_field(
            name="🎯 Nations",
            value=f"**Attacker:** {_nation_link_masked(attacker_data['leader_name'], attacker_data['nation_name'], attacker_data['nation_id'])}\n"
                  f"**Defender:** {_nation_link_masked(defender_data['leader_name'], defender_data['nation_name'], defender_data['nation_id'])}",
            inline=False
        )

        # Spy information
        embed.add_field(
            name="🔍 Spy Count",
            value=f"**Attacker Spies:** {attacker_data['spies']:,}\n"
                  f"**Defender Spies:** {defender_data['spies']:,}",
            inline=True
        )

        # War policies
        att_policy = attacker_data['war_policy'] or "None"
        def_policy = defender_data['war_policy'] or "None"
        embed.add_field(
            name="⚔️ War Policies",
            value=f"**Attacker:** {att_policy.title()}\n"
                  f"**Defender:** {def_policy.title()}",
            inline=True
        )

        # Projects
        att_sat = "✅" if attacker_data['spy_satellite'] else "❌"
        def_sat = "✅" if defender_data['spy_satellite'] else "❌"
        embed.add_field(
            name="🛰️ Spy Satellite",
            value=f"**Attacker:** {att_sat}\n"
                  f"**Defender:** {def_sat}",
            inline=True
        )

        # Optimal strategy section
        if desired_outcome == "least_cost":
            if spies_needed > attacker_data['spies']:
                embed.add_field(
                    name="⚠️ Insufficient Spies",
                    value=f"You have {attacker_data['spies']:,} spies but need {spies_needed:,} spies "
                          f"to reach 99% odds.\n"
                          f"Showing best possible odds with available spies.",
                    inline=False
                )

                # Recalculate with available spies
                best_odds = SpyCalculator.calculate_final_odds(
                    attacker_data['spies'],
                    defender_data['spies'],
                    SafetyLevel.EXTREMELY_COVERT,
                    operation,
                    attacker_data['war_policy'],
                    defender_data['war_policy']
                )
                actual_odds = best_odds
                spies_needed = attacker_data['spies']
                safety_level = SafetyLevel.EXTREMELY_COVERT

            embed.add_field(
                name="💡 Least Cost Strategy",
                value=f"**Spies Needed:** {spies_needed:,}\n"
                      f"**Safety Level:** {safety_names[safety_level]}\n"
                      f"**Actual Odds:** {actual_odds:.1f}%",
                inline=False
            )
        else:
            # Most Destruction mode
            embed.add_field(
                name="💥 Most Destruction Strategy",
                value=f"**Spies Needed:** {spies_needed:,}\n"
                      f"**Safety Level:** {safety_names[safety_level]}\n"
                      f"**Success Odds:** {actual_odds:.1f}%",
                inline=False
            )

            # Simulate operation to show potential destruction
            # Only for operations that can cause damage
            damage_operations = [
                EspionageOperation.ASSASSINATE_SPIES,
                EspionageOperation.TERRORIZE_CIVILIANS,
                EspionageOperation.SABOTAGE_SOLDIERS,
                EspionageOperation.SABOTAGE_TANKS,
                EspionageOperation.SABOTAGE_AIRCRAFT,
                EspionageOperation.SABOTAGE_SHIPS,
                EspionageOperation.SABOTAGE_MISSILES,
                EspionageOperation.SABOTAGE_NUCLEAR_WEAPONS,
            ]

            if operation in damage_operations:
                try:
                    conn = sqlite3.connect(DB_PATH)
                    executor = EspionageOperationExecutor(conn)

                    # Create NationData objects
                    attacker_nation = NationData(
                        nation_id=attacker_data['nation_id'],
                        nation_name=attacker_data['nation_name'],
                        spies=spies_needed,
                        soldiers=attacker_data['soldiers'],
                        tanks=attacker_data['tanks'],
                        aircraft=attacker_data['aircraft'],
                        ships=attacker_data['ships'],
                        missiles=attacker_data['missiles'],
                        nukes=attacker_data['nukes'],
                        war_policy=attacker_data['war_policy'],
                        spy_satellite=attacker_data['spy_satellite']
                    )

                    defender_nation = NationData(
                        nation_id=defender_data['nation_id'],
                        nation_name=defender_data['nation_name'],
                        spies=defender_data['spies'],
                        soldiers=defender_data['soldiers'],
                        tanks=defender_data['tanks'],
                        aircraft=defender_data['aircraft'],
                        ships=defender_data['ships'],
                        missiles=defender_data['missiles'],
                        nukes=defender_data['nukes'],
                        war_policy=defender_data['war_policy'],
                        spy_satellite=defender_data['spy_satellite']
                    )

                    # Execute the operation simulation
                    result = None
                    if operation == EspionageOperation.ASSASSINATE_SPIES:
                        result = executor.execute_assassinate_spies(attacker_nation, defender_nation, safety_level)
                    elif operation == EspionageOperation.TERRORIZE_CIVILIANS:
                        result = executor.execute_terrorize_civilians(attacker_nation, defender_nation, safety_level)
                    elif operation == EspionageOperation.SABOTAGE_SOLDIERS:
                        result = executor.execute_sabotage_soldiers(attacker_nation, defender_nation, safety_level)
                    elif operation == EspionageOperation.SABOTAGE_TANKS:
                        result = executor.execute_sabotage_tanks(attacker_nation, defender_nation, safety_level)
                    elif operation == EspionageOperation.SABOTAGE_AIRCRAFT:
                        result = executor.execute_sabotage_aircraft(attacker_nation, defender_nation, safety_level)
                    elif operation == EspionageOperation.SABOTAGE_SHIPS:
                        result = executor.execute_sabotage_ships(attacker_nation, defender_nation, safety_level)
                    elif operation == EspionageOperation.SABOTAGE_MISSILES:
                        result = executor.execute_sabotage_missiles(attacker_nation, defender_nation, safety_level)
                    elif operation == EspionageOperation.SABOTAGE_NUCLEAR_WEAPONS:
                        result = executor.execute_sabotage_nuclear_weapons(attacker_nation, defender_nation, safety_level)

                    conn.close()

                    # Display potential damage
                    if result:
                        damage_info = []
                        if result.defender_spies_killed > 0:
                            damage_info.append(f"**Spies Killed:** {result.defender_spies_killed:,}")
                        if result.infrastructure_destroyed > 0:
                            damage_info.append(f"**Infrastructure Destroyed:** {result.infrastructure_destroyed:.1f}")
                        if result.soldiers_killed > 0:
                            damage_info.append(f"**Soldiers Killed:** {result.soldiers_killed:,}")
                        if result.tanks_destroyed > 0:
                            damage_info.append(f"**Tanks Destroyed:** {result.tanks_destroyed:,}")
                        if result.aircraft_destroyed > 0:
                            damage_info.append(f"**Aircraft Destroyed:** {result.aircraft_destroyed:,}")
                        if result.ships_destroyed > 0:
                            damage_info.append(f"**Ships Destroyed:** {result.ships_destroyed:,}")
                        if result.missiles_destroyed > 0:
                            damage_info.append(f"**Missiles Destroyed:** {result.missiles_destroyed:,}")
                        if result.nukes_destroyed > 0:
                            damage_info.append(f"**Nukes Destroyed:** {result.nukes_destroyed:,}")

                        if damage_info:
                            embed.add_field(
                                name="💣 Potential Damage",
                                value="\n".join(damage_info),
                                inline=False
                            )
                        elif result.error_message:
                            embed.add_field(
                                name="⚠️ Operation Status",
                                value=result.error_message,
                                inline=False
                            )
                except Exception as e:
                    logger.error(f"Error simulating operation: {e}")

        # Additional info for specific operations
        if operation == EspionageOperation.SABOTAGE_MISSILES and defender_data['missiles'] == 0:
            embed.add_field(
                name="⚠️ Warning",
                value="Defender has 0 missiles. This operation will automatically fail.",
                inline=False
            )
        elif operation == EspionageOperation.SABOTAGE_NUCLEAR_WEAPONS and defender_data['nukes'] == 0:
            embed.add_field(
                name="⚠️ Warning",
                value="Defender has 0 nuclear weapons. This operation will automatically fail.",
                inline=False
            )

        embed.set_footer(text="Data from GlobalNations.db")

        await interaction.followup.send(embed=embed)
