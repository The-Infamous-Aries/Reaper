import sys
import os

# Add project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
import io
import matplotlib.pyplot as plt
import math
import random
from typing import Optional

from Systems.PnW.Util.war_calc import UNIT_COSTS, get_resource_prices, calculate_unit_cost
from Systems.Functions.emoji import get_partial, mention
from Systems.Functions.db_paths import GLOBAL_NATIONS_DB
from Systems.PnW.Util.query import create_v3_query_instance, V3GraphQuery
from Systems.PnW.Util.rev_correct import calculate_population_effects, get_city_age_from_game_data

# --- 1. INFRASTRUCTURE COST FORMULA (from costs.py) ---

def infra_price(amount: float) -> float:
    """Calculates the price of 1 unit of infra at a specific level."""
    return ((abs(amount - 10) ** 2.2) / 710.0) + 300.0

def calc_infra_value(starting_amount: float, ending_amount: float) -> float:
    """Calculates total cost to buy infrastructure from starting_amount to ending_amount."""
    start = round(float(starting_amount), 2)
    end = round(float(ending_amount), 2)
    diff = end - start

    if diff <= 0: return 0.0
    if diff > 20000: return float('inf') # Safety break

    total_cost = 0.0
    current_infra = start

    while current_infra < end:
        remaining_diff = end - current_infra
        chunk_size = 0
        if remaining_diff >= 100:
            chunk_size = 100.0
        else:
            chunk_size = remaining_diff
        
        cost_for_chunk = infra_price(current_infra) * chunk_size
        total_cost += cost_for_chunk
        current_infra += chunk_size
        
    return total_cost

# --- 2. WEAPON DAMAGE FORMULAS (Updated) ---

def get_weapon_damage(infra: float, weapon_type: str, pop_density: float = 60.0, damage_type: str = 'average') -> float:
    """Calculates weapon damage using actual PnW formulas.
    
    Missile: min(RANDOMBETWEEN(300, max(350, pop_density*3)), (0.3*infra)+100, infra)
    Nuke:    min(RANDOMBETWEEN(1700, max(2000, pop_density*13.5)), (0.8*infra)+150, infra)
    
    pop_density scales the upper bound of the random roll range.
    damage_type selects min/max/average of the actual roll range.
    """
    if weapon_type == "missile":
        roll_min = 300
        roll_max = max(350, pop_density * 3)
        city_infra_limit = (infra * 0.3) + 100
    else:  # nuke
        roll_min = 1700
        roll_max = max(2000, pop_density * 13.5)
        city_infra_limit = (infra * 0.8) + 150

    if damage_type == 'min':
        roll = roll_min
    elif damage_type == 'max':
        roll = roll_max
    else:  # average
        roll = (roll_min + roll_max) / 2

    return min(roll, city_infra_limit, infra)

# --- 3. THE SEARCH LOGIC (SOLVER) ---

def find_required_infra(target_damage_value: float, weapon_type: str, pop_density: float, damage_type: str) -> float:
    """Uses Binary Search to find the infra level needed for a target dollar damage."""
    low = 0
    high = 30000  # Increased high limit for safety
    
    for _ in range(40):  # 40 iterations for high precision
        mid = (low + high) / 2
        if mid <= 0:
            low = 0
            continue
            
        dmg_amount = get_weapon_damage(mid, weapon_type, pop_density, damage_type)
        if dmg_amount <= 0:
            low = mid # If no damage, need more infra
            continue
            
        actual_value = calc_infra_value(mid - dmg_amount, mid)
        
        if actual_value < target_damage_value:
            low = mid
        else:
            high = mid
            
    return round(low, 2)

# --- 4. DISCORD COG INTEGRATION ---

class WeaponEfficiency(commands.Cog):
    """Cog for weapon efficiency analysis and chart generation using actual resource prices."""
    
    def __init__(self, bot):
        self.bot = bot

    def generate_efficiency_chart_cog(self, nuke_cost, missile_cost,
                                       user_infra: Optional[float] = None,
                                       user_pop_density: Optional[float] = None,
                                       missile_marker: Optional[dict] = None,
                                       nuke_marker: Optional[dict] = None):
        """Generate weapon efficiency chart for the Discord command."""
        multipliers = range(1, 21)
        # min band = low pop density (hardest to deal damage), max band = high pop density (easiest)
        scenarios = {
            'min': {'pop_density': 10.0,  'damage_type': 'min'},
            'max': {'pop_density': 150.0, 'damage_type': 'max'},
        }
        
        data = {wt: {key: [] for key in scenarios} for wt in ['nuke', 'missile']}

        for m in multipliers:
            for wt, cost in [('nuke', nuke_cost), ('missile', missile_cost)]:
                target_value = m * cost
                for key, sc in scenarios.items():
                    infra = find_required_infra(target_value, wt, sc['pop_density'], sc['damage_type'])
                    data[wt][key].append(infra)

        plt.figure(figsize=(14, 8))
        plt.style.use('seaborn-v0_8-darkgrid')

        colors = {'nuke': {'min': '#ff4444', 'max': '#aa0000'}, 
                  'missile': {'min': '#4488ff', 'max': '#0033aa'}}
        markers = {'nuke': 'o', 'missile': 's'}
        linestyles = {'min': ':', 'max': '--'}

        for wt in ['nuke', 'missile']:
            for key, sc in scenarios.items():
                label = f"{wt.title()} {'Low Density' if key == 'min' else 'High Density'}"
                plt.plot(multipliers, data[wt][key], marker=markers[wt], color=colors[wt][key],
                         label=label, linewidth=2, linestyle=linestyles[key])

        plt.title("Weapon Economic Efficiency: Target Infrastructure Required\n(Damage Range Analysis)", 
                 fontsize=16, fontweight='bold')
        plt.xlabel("Damage Multiplier (x Weapon Cost)", fontsize=12)
        plt.ylabel("Required Initial Infrastructure", fontsize=12)
        plt.xticks(multipliers)
        plt.grid(True, alpha=0.3)

        # Helper function to get the angle of the line at a specific point
        def get_angle(x_data, y_data, index, ax):
            if index == 0:
                # Forward difference for the first point
                p1 = ax.transData.transform((x_data[index], y_data[index]))
                p2 = ax.transData.transform((x_data[index + 1], y_data[index + 1]))
            elif index == len(x_data) - 1:
                # Backward difference for the last point
                p1 = ax.transData.transform((x_data[index - 1], y_data[index - 1]))
                p2 = ax.transData.transform((x_data[index], y_data[index]))
            else:
                # Central difference for other points
                p1 = ax.transData.transform((x_data[index - 1], y_data[index - 1]))
                p2 = ax.transData.transform((x_data[index + 1], y_data[index + 1]))
            
            angle_rad = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
            return math.degrees(angle_rad)

        ax = plt.gca()
        key_indices = [4, 9, 14, 19]

        for i in key_indices:
            # --- Nuke Annotations ---
            nuke_max_infra = data['nuke']['max'][i]
            nuke_max_damage = get_weapon_damage(nuke_max_infra, 'nuke', scenarios['max']['pop_density'], 'max')
            nuke_max_value = calc_infra_value(nuke_max_infra - nuke_max_damage, nuke_max_infra)
            angle_n_max = get_angle(multipliers, data['nuke']['max'], i, ax)
            plt.annotate(f"{int(nuke_max_infra)} infra - ${nuke_max_value:,.0f}", (multipliers[i], nuke_max_infra), 
                         textcoords="offset points", xytext=(0, -5), ha='center', va='top',
                         rotation=angle_n_max, color='#aa0000', fontsize=8, fontweight='bold')

            nuke_min_infra = data['nuke']['min'][i]
            nuke_min_damage = get_weapon_damage(nuke_min_infra, 'nuke', scenarios['min']['pop_density'], 'min')
            nuke_min_value = calc_infra_value(nuke_min_infra - nuke_min_damage, nuke_min_infra)
            angle_n_min = get_angle(multipliers, data['nuke']['min'], i, ax)
            plt.annotate(f"{int(nuke_min_infra)} infra - ${nuke_min_value:,.0f}", (multipliers[i], nuke_min_infra), 
                         textcoords="offset points", xytext=(0, 5), ha='center', va='bottom',
                         rotation=angle_n_min, color='#ff4444', fontsize=8, fontweight='bold')

            # --- Missile Annotations ---
            missile_max_infra = data['missile']['max'][i]
            missile_max_damage = get_weapon_damage(missile_max_infra, 'missile', scenarios['max']['pop_density'], 'max')
            missile_max_value = calc_infra_value(missile_max_infra - missile_max_damage, missile_max_infra)
            angle_m_max = get_angle(multipliers, data['missile']['max'], i, ax)
            plt.annotate(f"{int(missile_max_infra)} infra - ${missile_max_value:,.0f}", (multipliers[i], missile_max_infra), 
                         textcoords="offset points", xytext=(0, -5), ha='center', va='top',
                         rotation=angle_m_max, color='#0033aa', fontsize=8, fontweight='bold')

            missile_min_infra = data['missile']['min'][i]
            missile_min_damage = get_weapon_damage(missile_min_infra, 'missile', scenarios['min']['pop_density'], 'min')
            missile_min_value = calc_infra_value(missile_min_infra - missile_min_damage, missile_min_infra)
            angle_m_min = get_angle(multipliers, data['missile']['min'], i, ax)
            plt.annotate(f"{int(missile_min_infra)} infra - ${missile_min_value:,.0f}", (multipliers[i], missile_min_infra), 
                         textcoords="offset points", xytext=(0, 5), ha='center', va='bottom',
                         rotation=angle_m_min, color='#4488ff', fontsize=8, fontweight='bold')

        if user_infra:
            # Theory mode — single city, green markers (use max roll for best-case placement)
            _theory_pd = user_pop_density if user_pop_density is not None else scenarios['max']['pop_density']
            user_nuke_max_dmg = get_weapon_damage(user_infra, 'nuke', _theory_pd, 'max')
            user_nuke_max_val = calc_infra_value(user_infra - user_nuke_max_dmg, user_infra)
            user_nuke_mult = user_nuke_max_val / nuke_cost

            user_missile_max_dmg = get_weapon_damage(user_infra, 'missile', _theory_pd, 'max')
            user_missile_max_val = calc_infra_value(user_infra - user_missile_max_dmg, user_infra)
            user_missile_mult = user_missile_max_val / missile_cost

            plt.scatter(user_nuke_mult, user_infra, color='#00ff00', s=150, zorder=5, label='Your City (Nuke)', ec='black')
            plt.scatter(user_missile_mult, user_infra, color='#00ff00', s=150, zorder=5, marker='X', label='Your City (Missile)', ec='black')

        # Targeted mode — separate missile (bright orange) and nuke (bright green) markers
        if missile_marker:
            m_infra = missile_marker['infra']
            m_pd    = missile_marker.get('pop_density', scenarios['max']['pop_density'])
            m_dmg   = get_weapon_damage(m_infra, 'missile', m_pd, 'max')
            m_val   = calc_infra_value(m_infra - m_dmg, m_infra)
            m_mult  = m_val / missile_cost if missile_cost else 0
            city_name = missile_marker.get('city', {}).get('name', 'Missile Target')
            plt.scatter(m_mult, m_infra, color='#FF6600', s=220, zorder=6,
                        marker='X', ec='black', linewidths=1.5,
                        label=f'🚀 {city_name} (Missile)')
            plt.annotate(f"🚀 {city_name}\n{m_infra:,.0f} infra",
                         (m_mult, m_infra), textcoords="offset points",
                         xytext=(10, 6), fontsize=8, color='#FF6600', fontweight='bold',
                         bbox=dict(boxstyle='round,pad=0.2', fc='white', alpha=0.7))

        if nuke_marker:
            n_infra = nuke_marker['infra']
            n_pd    = nuke_marker.get('pop_density', scenarios['max']['pop_density'])
            n_dmg   = get_weapon_damage(n_infra, 'nuke', n_pd, 'max')
            n_val   = calc_infra_value(n_infra - n_dmg, n_infra)
            n_mult  = n_val / nuke_cost if nuke_cost else 0
            city_name = nuke_marker.get('city', {}).get('name', 'Nuke Target')
            plt.scatter(n_mult, n_infra, color='#00FF44', s=220, zorder=6,
                        marker='o', ec='black', linewidths=1.5,
                        label=f'☢️ {city_name} (Nuke)')
            plt.annotate(f"☢️ {city_name}\n{n_infra:,.0f} infra",
                         (n_mult, n_infra), textcoords="offset points",
                         xytext=(10, -12), fontsize=8, color='#00AA33', fontweight='bold',
                         bbox=dict(boxstyle='round,pad=0.2', fc='white', alpha=0.7))

        plt.legend(loc='upper left', fontsize=9, ncol=2)
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        return buf

    @app_commands.command(name="weapon_eff", description="Weapon efficiency analysis — Theory mode or Targeted strike analysis")
    @app_commands.describe(
        mode="Theory: manual infra/pop inputs. Targeted: find best city to strike on a nation or alliance.",
        target_type="(Targeted only) Nation or Alliance",
        target="(Targeted only) Nation/Alliance name or ID",
        infra_level="(Theory only) Total infrastructure of the target city",
        land="(Theory only) Total land of the target city",
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Theory", value="theory"),
            app_commands.Choice(name="Targeted", value="targeted"),
        ],
        target_type=[
            app_commands.Choice(name="Nation", value="nation"),
            app_commands.Choice(name="Alliance", value="alliance"),
        ],
    )
    async def weapon_efficiency_command(
        self,
        interaction: discord.Interaction,
        mode: str,
        target_type: Optional[str] = None,
        target: Optional[str] = None,
        infra_level: Optional[float] = None,
        land: Optional[float] = None,
    ):
        """Weapon efficiency — Theory or Targeted mode."""
        try:
            await interaction.response.defer()

            # Fetch prices (needed for both modes)
            resource_prices = await get_resource_prices()
            if not resource_prices or 'sell' not in resource_prices:
                await interaction.followup.send("❌ Unable to fetch current resource prices.", ephemeral=True)
                return
            nuke_cost = calculate_unit_cost('nukes', resource_prices['sell'])
            missile_cost = calculate_unit_cost('missiles', resource_prices['sell'])
            if nuke_cost <= 0 or missile_cost <= 0:
                await interaction.followup.send("❌ Invalid weapon costs calculated.", ephemeral=True)
                return

            # ── THEORY MODE ──────────────────────────────────────────────────────────
            if mode == "theory":
                if (infra_level is not None and land is None) or \
                   (infra_level is None and land is not None):
                    await interaction.followup.send(
                        "❌ Provide both `infra_level` and `land`, or neither.", ephemeral=True)
                    return

                # Derive pop density from infra + land using the wiki formula
                theory_pop_density: Optional[float] = None
                if infra_level is not None and land is not None:
                    theory_city = {'infrastructure': infra_level, 'land': land}
                    _, theory_pop_density = self._city_population_and_density(theory_city)

                chart_buffer = self.generate_efficiency_chart_cog(nuke_cost, missile_cost, infra_level, theory_pop_density)
                file = discord.File(chart_buffer, filename="weapon_efficiency_chart.png")

                if infra_level is not None and theory_pop_density is not None:
                    embed = discord.Embed(
                        title=f"{mention('war') or '⚔️'} Theory — Specific City",
                        description=f"**{infra_level:,.0f} infra** / **{land:,.0f} land** → **{theory_pop_density:,.1f} pop density**",
                        color=discord.Color.blue()
                    )
                    embed = self._add_city_weapon_fields(embed, infra_level, theory_pop_density, missile_cost, nuke_cost)
                    embed.set_footer(text="🟢 Your city is marked on the chart! Circle (Nuke) and X (Missile).")
                else:
                    embed = discord.Embed(
                        title=f"{mention('wars') or '⚔️'} Theory — General Efficiency",
                        description="Economic efficiency thresholds at average pop density (60).",
                        color=discord.Color.red()
                    )
                    infr_nuke_1x = find_required_infra(nuke_cost, 'nuke', 60, 'average')
                    infra_missile_1x = find_required_infra(missile_cost, 'missile', 60, 'average')
                    embed.add_field(
                        name="🚫 DON'T USE (Inefficient Zone)",
                        value=f"Below these levels you lose money.\n**Nuke:** `{infr_nuke_1x:,.0f}` infra\n**Missile:** `{infra_missile_1x:,.0f}` infra",
                        inline=False
                    )
                    infr_nuke_5x = find_required_infra(nuke_cost * 5, 'nuke', 60, 'average')
                    infra_missile_5x = find_required_infra(missile_cost * 5, 'missile', 60, 'average')
                    embed.add_field(
                        name="✅ OPTIMAL USE (5× Zone)",
                        value=f"Damage valued at **5×** weapon cost.\n**Nuke:** `{infr_nuke_5x:,.0f}` infra\n**Missile:** `{infra_missile_5x:,.0f}` infra",
                        inline=False
                    )

                embed.set_footer(text=f"Live Costs | Nuke: ${nuke_cost:,.0f}, Missile: ${missile_cost:,.0f} • {discord.utils.format_dt(discord.utils.utcnow(), 'R')}")
                embed.set_image(url="attachment://weapon_efficiency_chart.png")
                await interaction.followup.send(embed=embed, file=file)
                return

            # ── TARGETED MODE ─────────────────────────────────────────────────────────
            if not target_type or not target:
                await interaction.followup.send("❌ Targeted mode requires `target_type` and `target`.", ephemeral=True)
                return

            if target_type == "nation":
                # Prefer local DBs, fall back to API
                nation_data = await self._resolve_nation(target)
                if not nation_data:
                    await interaction.followup.send(f"❌ Nation `{target}` not found.", ephemeral=True)
                    return

                embed, best_missile, best_nuke = await self._targeted_nation_embed(nation_data, missile_cost, nuke_cost)
                chart_buffer = self.generate_efficiency_chart_cog(
                    nuke_cost, missile_cost,
                    missile_marker=best_missile,
                    nuke_marker=best_nuke
                )
                file = discord.File(chart_buffer, filename="weapon_efficiency_chart.png")
                embed.set_image(url="attachment://weapon_efficiency_chart.png")
                embed.set_footer(text=f"Live Costs | Nuke: ${nuke_cost:,.0f}, Missile: ${missile_cost:,.0f} • {discord.utils.format_dt(discord.utils.utcnow(), 'R')}")
                await interaction.followup.send(embed=embed, file=file)

            else:  # alliance
                alliance_info, nations = await self._resolve_alliance_nations(target)
                if not alliance_info:
                    await interaction.followup.send(f"❌ Alliance `{target}` not found.", ephemeral=True)
                    return
                if not nations:
                    await interaction.followup.send(f"❌ No nations found in alliance `{alliance_info.get('name', target)}`.", ephemeral=True)
                    return
                alliance_name = alliance_info.get('name', target)

                embed, best_missile, best_nuke = await self._targeted_alliance_embed(nations, alliance_name, missile_cost, nuke_cost)
                chart_buffer = self.generate_efficiency_chart_cog(
                    nuke_cost, missile_cost,
                    missile_marker=best_missile,
                    nuke_marker=best_nuke
                )
                file = discord.File(chart_buffer, filename="weapon_efficiency_chart.png")
                embed.set_image(url="attachment://weapon_efficiency_chart.png")
                embed.set_footer(text=f"Live Costs | Nuke: ${nuke_cost:,.0f}, Missile: ${missile_cost:,.0f} • {discord.utils.format_dt(discord.utils.utcnow(), 'R')}")
                await interaction.followup.send(embed=embed, file=file)

        except Exception as e:
            logging.error(f"Error in weapon_efficiency_command: {e}", exc_info=True)
            try:
                await interaction.followup.send(f"❌ An error occurred: {e}", ephemeral=True)
            except Exception:
                pass

    # ── HELPERS ──────────────────────────────────────────────────────────────────

    async def _resolve_nation(self, target: str) -> Optional[dict]:
        """Resolve a nation with cities from GlobalNations.db (single source of truth), falling back to API."""
        if GLOBAL_NATIONS_DB.exists():
            try:
                from PnWHarvester.db.global_nations_db import GlobalNationsDB
                gdb = GlobalNationsDB(str(GLOBAL_NATIONS_DB))
                nation = (await gdb.get_nation(int(target))
                          if target.isdigit()
                          else await gdb.get_nation_by_name(target))
                if nation:
                    nation['cities'] = await gdb.get_cities_for_nation(int(nation['id']))
                    if nation['cities']:
                        return nation
            except Exception as e:
                logging.debug(f"GlobalNationsDB lookup failed for '{target}': {e}")

        query = create_v3_query_instance()
        return (await query.get_nation_by_id(target)
                if target.isdigit()
                else await query.get_nation_by_name(target))

    async def _resolve_alliance_nations(self, target: str) -> tuple[Optional[dict], list]:
        """Resolve alliance nations with cities from local DBs, falling back to API."""
        if GLOBAL_NATIONS_DB.exists():
            try:
                from PnWHarvester.db.global_nations_db import GlobalNationsDB
                gdb = GlobalNationsDB(str(GLOBAL_NATIONS_DB))
                alliance_id_int = None
                alliance_name   = target
                if target.isdigit():
                    alliance_id_int = int(target)
                else:
                    alliances = await gdb.get_distinct_alliances(target)
                    for a in alliances:
                        if (a.get('alliance_name') or '').lower() == target.lower():
                            alliance_id_int = a['alliance_id']
                            alliance_name   = a.get('alliance_name') or target
                            break
                    if not alliance_id_int and alliances:
                        alliance_id_int = alliances[0]['alliance_id']
                        alliance_name   = alliances[0].get('alliance_name') or target

                if alliance_id_int:
                    nations = await gdb.get_nations_by_alliance(alliance_id_int)
                    if nations:
                        for nation in nations:
                            nation['cities'] = await gdb.get_cities_for_nation(int(nation['id']))
                        nations = [n for n in nations if n.get('cities')]
                        if nations:
                            return {'id': str(alliance_id_int), 'name': alliance_name}, nations
            except Exception as e:
                logging.debug(f"GlobalNationsDB alliance lookup failed for '{target}': {e}")

        query = create_v3_query_instance()
        resolved = await query.resolve_alliance(target)
        if not resolved or not resolved.get('id'):
            return None, []
        nations = await query.get_alliance_nations(str(resolved['id']), force_refresh=True) or []
        return resolved, nations

    def _city_population_and_density(self, city: dict) -> tuple[float, float]:
        """Calculate actual population and displayed population density per wiki formulas.

        Delegates to the canonical calculate_population_effects from rev_correct.
        Disease uses Base Pop Density (base_pop / land) per wiki.
        Displayed density = actual_pop / land.

        Returns:
            (actual_population, displayed_pop_density)
        """
        infra = city.get('infrastructure', 0) or 0
        land  = max(city.get('land', 0) or 0, 1)  # avoid div/0
        base_pop = infra * 100

        # --- Commerce (capped) ---
        powered = city.get('powered', True)
        commerce = 0.0
        if powered:
            commerce += city.get('subway', 0) * 8
            commerce += city.get('supermarket', 0) * 4
            commerce += city.get('bank', 0) * 6
            commerce += city.get('shopping_mall', 0) * 8
            commerce += city.get('stadium', 0) * 10
        commerce = min(commerce, 100)

        # --- Pollution ---
        pollution = 0.0
        if powered:
            pollution += city.get('police_station', 0)
            pollution += city.get('hospital', 0) * 4
            pollution -= city.get('recycling_center', 0) * 70
            pollution -= city.get('subway', 0) * 45
            pollution += city.get('shopping_mall', 0) * 2
            pollution += city.get('stadium', 0) * 5
        pollution = max(pollution, 0)

        police_stations = city.get('police_station', 0) if powered else 0
        hospitals       = city.get('hospital', 0)       if powered else 0

        # --- Default modifiers (no national projects assumed for bare city) ---
        modifiers = {'pol_cri_red': 2.5, 'hos_dis_red': 2.5}
        if city.get('clinical_research_center'):
            modifiers['hos_dis_red'] = 3.5
        if city.get('specialized_police_training_program'):
            modifiers['pol_cri_red'] = 3.5

        # Ensure city has 'infrastructure' and 'land' keys for calculate_population_effects
        city_for_calc = dict(city)
        city_for_calc['infrastructure'] = infra
        city_for_calc['land'] = land

        # --- Canonical population calculation from rev_correct ---
        pop_result = calculate_population_effects(
            city_for_calc, modifiers, base_pop, commerce, police_stations, hospitals, pollution
        )
        actual_pop = float(pop_result['population'])

        # --- Displayed density = actual pop / land ---
        displayed_density = actual_pop / land
        return actual_pop, max(displayed_density, 1.0)

    def _pop_density(self, city: dict) -> float:
        """Return displayed population density (actual pop / land) per wiki formula."""
        _, density = self._city_population_and_density(city)
        return density

    def _impact_chance(self, nation: dict, weapon: str) -> float:
        """Return hit probability (0–1) accounting for Iron Dome / VDS."""
        if weapon == "missile":
            return 0.70 if nation.get('iron_dome') else 1.0
        else:  # nuke
            return 0.75 if nation.get('vital_defense_system') else 1.0

    def _city_score(self, city: dict, nation: dict, weapon: str, weapon_cost: float) -> dict:
        """Score a single city for a given weapon — returns dict with all relevant stats."""
        infra = city.get('infrastructure', 0) or 0
        actual_pop, pd = self._city_population_and_density(city)
        hit_chance = self._impact_chance(nation, weapon)

        avg_dmg = get_weapon_damage(infra, weapon, pd, 'average')
        min_dmg = get_weapon_damage(infra, weapon, pd, 'min')
        max_dmg = get_weapon_damage(infra, weapon, pd, 'max')

        avg_val = calc_infra_value(infra - avg_dmg, infra)
        min_val = calc_infra_value(infra - min_dmg, infra)
        max_val = calc_infra_value(infra - max_dmg, infra)

        # Expected value = damage value × hit chance
        expected_val = avg_val * hit_chance

        return {
            'city': city,
            'infra': infra,
            'pop_density': pd,
            'actual_pop': actual_pop,
            'hit_chance': hit_chance,
            'avg_dmg': avg_dmg, 'min_dmg': min_dmg, 'max_dmg': max_dmg,
            'avg_val': avg_val, 'min_val': min_val, 'max_val': max_val,
            'expected_val': expected_val,
            'avg_mult': avg_val / weapon_cost if weapon_cost else 0,
            'max_mult': max_val / weapon_cost if weapon_cost else 0,
        }

    def _best_city(self, nation: dict, weapon: str, weapon_cost: float) -> Optional[dict]:
        """Find the best city to strike with a given weapon."""
        cities = nation.get('cities', [])
        if not cities:
            return None
        scored = [self._city_score(c, nation, weapon, weapon_cost) for c in cities]
        return max(scored, key=lambda s: s['expected_val'])

    def _add_city_weapon_fields(self, embed: discord.Embed, infra: float, pd: float,
                                 missile_cost: float, nuke_cost: float,
                                 missile_chance: float = 1.0, nuke_chance: float = 1.0) -> discord.Embed:
        """Add missile + nuke damage fields to an embed for a specific city."""
        for weapon, cost, chance, label in [
            ("missile", missile_cost, missile_chance, mention('missile') or "🚀 Missile"),
            ("nuke",    nuke_cost,    nuke_chance,    mention('bomb') or "☢️ Nuke"),
        ]:
            min_dmg = get_weapon_damage(infra, weapon, pd, 'min')
            max_dmg = get_weapon_damage(infra, weapon, pd, 'max')
            min_val = calc_infra_value(infra - min_dmg, infra)
            max_val = calc_infra_value(infra - max_dmg, infra)
            chance_str = f"{chance*100:.0f}% hit chance" if chance < 1.0 else "100% hit chance"
            # Show whether pop density is boosting the roll ceiling above the base cap
            if weapon == "missile":
                pd_threshold = 350 / 3  # ~116.7 — above this pd*3 > 350
                roll_ceil = max(350, pd * 3)
            else:
                pd_threshold = 2000 / 13.5  # ~148.1 — above this pd*13.5 > 2000
                roll_ceil = max(2000, pd * 13.5)
            if pd > pd_threshold:
                density_note = f"🔴 Density boosting roll ceil to `{roll_ceil:,.0f}`"
            else:
                density_note = f"⚪ Density below threshold (need `>{pd_threshold:,.0f}` to boost)"
            embed.add_field(
                name=f"{label} — ${cost:,.0f} ({chance_str})",
                value=(
                    f"**Min:** `{min_dmg:,.0f}` infra → `${min_val:,.0f}` ({min_val/cost:.1f}×)\n"
                    f"**Max:** `{max_dmg:,.0f}` infra → `${max_val:,.0f}` ({max_val/cost:.1f}×)\n"
                    f"**Expected:** `${min_val*chance:,.0f}` – `${max_val*chance:,.0f}`\n"
                    f"{density_note}"
                ),
                inline=False
            )
        return embed

    async def _targeted_nation_embed(self, nation: dict, missile_cost: float, nuke_cost: float) -> tuple[discord.Embed, Optional[dict], Optional[dict]]:
        """Build embed for targeted nation analysis."""
        nation_name = nation.get('nation_name', 'Unknown')
        nation_id = nation.get('id', '')
        has_iron_dome = bool(nation.get('iron_dome'))
        has_vds = bool(nation.get('vital_defense_system'))
        missile_chance = 0.70 if has_iron_dome else 1.0
        nuke_chance = 0.75 if has_vds else 1.0

        best_missile = self._best_city(nation, "missile", missile_cost)
        best_nuke = self._best_city(nation, "nuke", nuke_cost)

        embed = discord.Embed(
            title=f"🎯 Targeted Strike — {nation_name}",
            url=f"https://politicsandwar.com/nation/id={nation_id}",
            color=discord.Color.red()
        )

        # Defenses
        defense_lines = []
        if has_iron_dome:
            defense_lines.append("🛡️ **Iron Dome** — Missiles: 70% hit chance (-30%)")
        if has_vds:
            defense_lines.append("🛡️ **Vital Defense System** — Nukes: 75% hit chance (-25%)")
        if not defense_lines:
            defense_lines.append("✅ No missile/nuke defenses detected")
        embed.add_field(name="🔰 Defenses", value="\n".join(defense_lines), inline=False)

        # Best missile city
        if best_missile:
            c = best_missile['city']
            embed.add_field(
                name=f"{mention('missile') or '🚀'} Best Missile Target — {c.get('name', 'Unknown City')}",
                value=(
                    f"**Infra:** {best_missile['infra']:,.0f} | **Pop:** {best_missile['actual_pop']:,.0f} | **Pop Density:** {best_missile['pop_density']:,.1f}\n"
                    f"**Min Dmg:** {best_missile['min_dmg']:,.0f} infra → ${best_missile['min_val']:,.0f} ({best_missile['min_val']/missile_cost:.1f}×)\n"
                    f"**Max Dmg:** {best_missile['max_dmg']:,.0f} infra → ${best_missile['max_val']:,.0f} ({best_missile['max_val']/missile_cost:.1f}×)\n"
                    f"**Hit Chance:** {missile_chance*100:.0f}% | **Expected Value:** ${best_missile['expected_val']:,.0f}"
                ),
                inline=False
            )

        # Best nuke city
        if best_nuke:
            c = best_nuke['city']
            same_city = best_missile and c.get('id') == best_missile['city'].get('id')
            city_label = f"{c.get('name', 'Unknown City')}" + (" *(same city)*" if same_city else "")
            embed.add_field(
                name=f"{mention('bomb') or '☢️'} Best Nuke Target — {city_label}",
                value=(
                    f"**Infra:** {best_nuke['infra']:,.0f} | **Pop:** {best_nuke['actual_pop']:,.0f} | **Pop Density:** {best_nuke['pop_density']:,.1f}\n"
                    f"**Min Dmg:** {best_nuke['min_dmg']:,.0f} infra → ${best_nuke['min_val']:,.0f} ({best_nuke['min_val']/nuke_cost:.1f}×)\n"
                    f"**Max Dmg:** {best_nuke['max_dmg']:,.0f} infra → ${best_nuke['max_val']:,.0f} ({best_nuke['max_val']/nuke_cost:.1f}×)\n"
                    f"**Hit Chance:** {nuke_chance*100:.0f}% | **Expected Value:** ${best_nuke['expected_val']:,.0f}"
                ),
                inline=False
            )

        return embed, best_missile, best_nuke

    async def _targeted_alliance_embed(self, nations: list, alliance_name: str,
                                        missile_cost: float, nuke_cost: float) -> tuple[discord.Embed, Optional[dict], Optional[dict]]:
        """Find the best nation+city combo across an entire alliance for each weapon."""
        best_missile_score = None
        best_missile_nation = None
        best_nuke_score = None
        best_nuke_nation = None

        for nation in nations:
            if not nation.get('cities'):
                continue
            ms = self._best_city(nation, "missile", missile_cost)
            if ms and (best_missile_score is None or ms['expected_val'] > best_missile_score['expected_val']):
                best_missile_score = ms
                best_missile_nation = nation

            ns = self._best_city(nation, "nuke", nuke_cost)
            if ns and (best_nuke_score is None or ns['expected_val'] > best_nuke_score['expected_val']):
                best_nuke_score = ns
                best_nuke_nation = nation

        embed = discord.Embed(
            title=f"🎯 Alliance Strike Analysis — {alliance_name}",
            description=f"Best targets across **{len(nations)}** nations.",
            color=discord.Color.dark_red()
        )

        if best_missile_score and best_missile_nation:
            n = best_missile_nation
            c = best_missile_score['city']
            has_id = bool(n.get('iron_dome'))
            chance = 0.70 if has_id else 1.0
            embed.add_field(
                name=f"{mention('missile') or '🚀'} Best Missile Target",
                value=(
                    f"**Nation:** [{n.get('nation_name','?')}](https://politicsandwar.com/nation/id={n.get('id','')})\n"
                    f"**City:** {c.get('name','?')} | **Infra:** {best_missile_score['infra']:,.0f} | **Pop:** {best_missile_score['actual_pop']:,.0f} | **Density:** {best_missile_score['pop_density']:,.1f}\n"
                    f"{'🛡️ Iron Dome — ' if has_id else ''}**Hit Chance:** {chance*100:.0f}%\n"
                    f"**Min:** {best_missile_score['min_dmg']:,.0f} infra → ${best_missile_score['min_val']:,.0f} ({best_missile_score['min_val']/missile_cost:.1f}×)\n"
                    f"**Max:** {best_missile_score['max_dmg']:,.0f} infra → ${best_missile_score['max_val']:,.0f} ({best_missile_score['max_val']/missile_cost:.1f}×)\n"
                    f"**Expected Value:** ${best_missile_score['expected_val']:,.0f}"
                ),
                inline=False
            )

        if best_nuke_score and best_nuke_nation:
            n = best_nuke_nation
            c = best_nuke_score['city']
            has_vds = bool(n.get('vital_defense_system'))
            chance = 0.75 if has_vds else 1.0
            embed.add_field(
                name=f"{mention('bomb') or '☢️'} Best Nuke Target",
                value=(
                    f"**Nation:** [{n.get('nation_name','?')}](https://politicsandwar.com/nation/id={n.get('id','')})\n"
                    f"**City:** {c.get('name','?')} | **Infra:** {best_nuke_score['infra']:,.0f} | **Pop:** {best_nuke_score['actual_pop']:,.0f} | **Density:** {best_nuke_score['pop_density']:,.1f}\n"
                    f"{'🛡️ VDS — ' if has_vds else ''}**Hit Chance:** {chance*100:.0f}%\n"
                    f"**Min:** {best_nuke_score['min_dmg']:,.0f} infra → ${best_nuke_score['min_val']:,.0f} ({best_nuke_score['min_val']/nuke_cost:.1f}×)\n"
                    f"**Max:** {best_nuke_score['max_dmg']:,.0f} infra → ${best_nuke_score['max_val']:,.0f} ({best_nuke_score['max_val']/nuke_cost:.1f}×)\n"
                    f"**Expected Value:** ${best_nuke_score['expected_val']:,.0f}"
                ),
                inline=False
            )

        return embed, best_missile_score, best_nuke_score

# --- 5. UPDATED STANDALONE CHART GENERATION ---

async def generate_war_chart_async():
    """Updated standalone function to generate chart with live prices and min/max damage."""
    print("Fetching live resource prices...")
    resource_prices = await get_resource_prices()
    if not resource_prices or 'sell' not in resource_prices:
        print("Error: Could not fetch resource prices.")
        return

    nuke_cost = calculate_unit_cost('nukes', resource_prices['sell'])
    missile_cost = calculate_unit_cost('missiles', resource_prices['sell'])
    print(f"Live Costs | Nuke: ${nuke_cost:,.0f}, Missile: ${missile_cost:,.0f}")

    multipliers = range(1, 21)
    
    nuke_min_data = []
    nuke_max_data = []
    missile_min_data = []
    missile_max_data = []

    print("Calculating data points for min/max damage scenarios... please wait.")
    for m in multipliers:
        nuke_target_value = m * nuke_cost
        nuke_min_data.append(find_required_infra(nuke_target_value, "nuke", pop_density=10.0, damage_type='min'))
        nuke_max_data.append(find_required_infra(nuke_target_value, "nuke", pop_density=150.0, damage_type='max'))
        
        # Missile calculations
        missile_target_value = m * missile_cost
        missile_min_data.append(find_required_infra(missile_target_value, "missile", pop_density=10.0, damage_type='min'))
        missile_max_data.append(find_required_infra(missile_target_value, "missile", pop_density=150.0, damage_type='max'))

    plt.figure(figsize=(12, 7))
    plt.style.use('seaborn-v0_8-darkgrid')

    plt.plot(multipliers, nuke_min_data, marker='o', color='#ff9999', label=f'Nuke - Min Damage Taken', linestyle='--', linewidth=2)
    plt.plot(multipliers, nuke_max_data, marker='o', color='#d62728', label=f'Nuke - Max Damage Taken', linewidth=2)

    plt.plot(multipliers, missile_min_data, marker='s', color='#99ccff', label=f'Missile - Min Damage Taken', linestyle='--', linewidth=2)
    plt.plot(multipliers, missile_max_data, marker='s', color='#1f77b4', label=f'Missile - Max Damage Taken', linewidth=2)

    plt.title("Weapon Economic Efficiency: Required Infra vs. Damage Multiplier", fontsize=16, fontweight='bold')
    plt.xlabel("Damage Multiplier (x Weapon Cost)", fontsize=12)
    plt.ylabel("Required Initial Infrastructure", fontsize=12)
    plt.xticks(multipliers)
    plt.legend(loc='upper left', fontsize=12)
    plt.grid(True, which='both', linestyle='--', linewidth=0.5)
    
    # Helper function to get the angle of the line at a specific point
    def get_angle(x_data, y_data, index, ax):
        if index == 0:
            # Forward difference for the first point
            p1 = ax.transData.transform((x_data[index], y_data[index]))
            p2 = ax.transData.transform((x_data[index + 1], y_data[index + 1]))
        elif index == len(x_data) - 1:
            # Backward difference for the last point
            p1 = ax.transData.transform((x_data[index - 1], y_data[index - 1]))
            p2 = ax.transData.transform((x_data[index], y_data[index]))
        else:
            # Central difference for other points
            p1 = ax.transData.transform((x_data[index - 1], y_data[index - 1]))
            p2 = ax.transData.transform((x_data[index + 1], y_data[index + 1]))
        
        angle_rad = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
        return math.degrees(angle_rad)

    # Annotations for key points
    key_indices = [4, 9, 14, 19] # Corresponds to multipliers 5, 10, 15, 20
    ax = plt.gca() # Get current axes

    for i in key_indices:
        # --- Nuke Annotations ---
        nuke_max_infra = nuke_max_data[i]
        nuke_max_damage = get_weapon_damage(nuke_max_infra, 'nuke', 150, 'max')
        nuke_max_value = calc_infra_value(nuke_max_infra - nuke_max_damage, nuke_max_infra)
        angle_n_max = get_angle(multipliers, nuke_max_data, i, ax)
        plt.annotate(f"{int(nuke_max_infra)} - ${nuke_max_cost:,.0f}", (multipliers[i], nuke_max_infra), 
                     textcoords="offset points", xytext=(0, -5), ha='center', va='top',
                     rotation=angle_n_max, color='#d62728', fontsize=8, fontweight='bold')

        nuke_min_infra = nuke_min_data[i]
        nuke_min_damage = get_weapon_damage(nuke_min_infra, 'nuke', 10, 'min')
        nuke_min_value = calc_infra_value(nuke_min_infra - nuke_min_damage, nuke_min_infra)
        angle_n_min = get_angle(multipliers, nuke_min_data, i, ax)
        plt.annotate(f"{int(nuke_min_infra)} - ${nuke_min_cost:,.0f}", (multipliers[i], nuke_min_infra), 
                     textcoords="offset points", xytext=(0, 5), ha='center', va='bottom',
                     rotation=angle_n_min, color='#d62728', fontsize=8)

        # --- Missile Annotations ---
        missile_max_infra = missile_max_data[i]
        missile_max_damage = get_weapon_damage(missile_max_infra, 'missile', 150, 'max')
        missile_max_value = calc_infra_value(missile_max_infra - missile_max_damage, missile_max_infra)
        angle_m_max = get_angle(multipliers, missile_max_data, i, ax)
        plt.annotate(f"{int(missile_max_infra)} - ${missile_max_cost:,.0f}", (multipliers[i], missile_max_infra), 
                     textcoords="offset points", xytext=(0, -5), ha='center', va='top',
                     rotation=angle_m_max, color='#1f77b4', fontsize=8, fontweight='bold')

        missile_min_infra = missile_min_data[i]
        missile_min_damage = get_weapon_damage(missile_min_infra, 'missile', 10, 'min')
        missile_min_value = calc_infra_value(missile_min_infra - missile_min_damage, missile_min_infra)
        angle_m_min = get_angle(multipliers, missile_min_data, i, ax)
        plt.annotate(f"{int(missile_min_infra)} - ${missile_min_cost:,.0f}", (multipliers[i], missile_min_infra), 
                     textcoords="offset points", xytext=(0, 5), ha='center', va='bottom',
                     rotation=angle_m_min, color='#1f77b4', fontsize=8)

    plt.tight_layout()
    
    file_name = "weapon_eff_live.png"
    plt.savefig(file_name, dpi=300)
    print(f"Success! Chart saved as {file_name}")

async def setup(bot):
    """Add the WeaponEfficiency cog to the bot."""
    await bot.add_cog(WeaponEfficiency(bot))

if __name__ == "__main__":
    try:
        asyncio.run(generate_war_chart_async())
    except RuntimeError as e:
        print(f"Could not run async function directly: {e}")
        print("Please run this in an environment that supports top-level await or use an existing event loop.")
