import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta, timezone
import asyncio

from Systems.Functions.emoji import mention, resource_emoji, military_codes
from Systems.Functions.irs_wars_db import IRSWarsDB
from Systems.Functions.db_paths import NW_WARS_DB_STR as NW_DB_PATH
from Systems.PnW.Util.war_calc import get_resource_prices, calculate_unit_cost

# ── Constants ─────────────────────────────────────────────────────────────────
NW_ALLIANCE_ID = 10259
NW_ALLIANCE_NAME = "Darkstar"

RANKING_TYPES = [
    app_commands.Choice(name="War Cost", value="war_cost"),
    app_commands.Choice(name="War Net", value="war_net"),
    app_commands.Choice(name="Damages", value="damages"),
    app_commands.Choice(name="Bomb Cost", value="bomb_cost"),
    app_commands.Choice(name="Loot", value="loot"),
    app_commands.Choice(name="Soldiers Lost", value="soldiers_lost"),
    app_commands.Choice(name="Soldiers Killed", value="soldiers_killed"),
    app_commands.Choice(name="Tanks Lost", value="tanks_lost"),
    app_commands.Choice(name="Tanks Killed", value="tanks_killed"),
    app_commands.Choice(name="Aircraft Lost", value="aircraft_lost"),
    app_commands.Choice(name="Aircraft Killed", value="aircraft_killed"),
    app_commands.Choice(name="Ships Lost", value="ships_lost"),
    app_commands.Choice(name="Ships Killed", value="ships_killed"),
    app_commands.Choice(name="Peace", value="peace"),
    app_commands.Choice(name="Wins", value="wins"),
    app_commands.Choice(name="Losses", value="losses"),
]

TIME_CHOICES = [
    app_commands.Choice(name="1 Day", value="1d"),
    app_commands.Choice(name="3 Days", value="3d"),
    app_commands.Choice(name="1 Week", value="1w"),
    app_commands.Choice(name="2 Weeks", value="2w"),
    app_commands.Choice(name="1 Month", value="1m"),
    app_commands.Choice(name="3 Months", value="3m"),
    app_commands.Choice(name="6 Months", value="6m"),
    app_commands.Choice(name="1 Year", value="1y"),
    app_commands.Choice(name="All Time", value="all"),
    app_commands.Choice(name="Custom (e.g., 2d, 1w)", value="custom")
]

class Rankings(commands.Cog):
    """Rankings command for P&W war statistics."""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)

    def _parse_time_to_datetime(self, time_str: str) -> Optional[datetime]:
        """Parse time string to datetime object.
        
        Supports formats like:
        - 'all' or None for all time
        - 'Nd' for N days (e.g., '2d', '7d')
        - 'Nw' for N weeks (e.g., '1w', '2w')
        - 'Nm' for N months (e.g., '1m', '6m')
        - 'Ny' for N years (e.g., '1y', '2y')
        """
        if not time_str or time_str == "all":
            return None
        
        now = datetime.now(timezone.utc)
        time_str = time_str.strip().lower()
        
        # Parse the time string (e.g., "2d", "1w", "6m", "1y")
        import re
        match = re.match(r'^(\d+)([dwmy])$', time_str)
        if not match:
            return None
        
        value = int(match.group(1))
        unit = match.group(2)
        
        if unit == 'd':
            return now - timedelta(days=value)
        elif unit == 'w':
            return now - timedelta(weeks=value)
        elif unit == 'm':
            return now - timedelta(days=value * 30)
        elif unit == 'y':
            return now - timedelta(days=value * 365)
        
        return None

    async def _calculate_nation_stats(self, wars: List[Dict[str, Any]], resource_prices: Dict[str, Any], 
                                    ranking_type: str, enemy_alliance_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """Calculate statistics for each nation based on ranking type."""
        nation_stats = {}

        # Always bulk-fetch attacks — needed for bomb counts (war-level missile/nuke
        # columns are always 0 in the DB; real data lives in attack rows).
        war_ids = [war['id'] for war in wars]
        db = IRSWarsDB(NW_DB_PATH)
        attacks_by_war = await db.get_attacks_for_wars(war_ids)

        for war in wars:
            att_id = war.get('att_id')
            def_id = war.get('def_id')
            att_alliance_id = war.get('att_alliance_id')
            def_alliance_id = war.get('def_alliance_id')
            
            # Determine if this is a relevant war based on enemy filter
            is_relevant_war = False
            nw_nation_id = None
            
            if att_alliance_id == NW_ALLIANCE_ID:
                if not enemy_alliance_ids or def_alliance_id in enemy_alliance_ids:
                    is_relevant_war = True
                    nw_nation_id = att_id
            elif def_alliance_id == NW_ALLIANCE_ID:
                if not enemy_alliance_ids or att_alliance_id in enemy_alliance_ids:
                    is_relevant_war = True
                    nw_nation_id = def_id
            
            if not is_relevant_war or not nw_nation_id:
                continue
            
            if nw_nation_id not in nation_stats:
                nation_stats[nw_nation_id] = {
                    'nation_name': war.get('att_nation_name') if att_id == nw_nation_id else war.get('def_nation_name'),
                    'war_cost': 0, 'war_net': 0, 'damages': 0, 'bomb_cost': 0, 'loot': 0,
                    'wars_count': 0,
                    'soldiers_lost': 0, 'soldiers_killed': 0,
                    'tanks_lost': 0,    'tanks_killed': 0,
                    'aircraft_lost': 0, 'aircraft_killed': 0,
                    'ships_lost': 0,    'ships_killed': 0,
                    'wins': 0, 'losses': 0, 'peace': 0,
                }
            
            stats = nation_stats[nw_nation_id]
            # Keep the first non-None name we encounter
            if not stats['nation_name']:
                stats['nation_name'] = (
                    war.get('att_nation_name') if att_id == nw_nation_id else war.get('def_nation_name')
                )
            stats['wars_count'] += 1
            war_attacks = attacks_by_war.get(war['id'], [])

            if att_id == nw_nation_id:
                self._add_attacker_stats(stats, war, war_attacks, resource_prices)
                self._add_attacker_loot(stats, war, war_attacks, resource_prices)
            else:
                self._add_defender_stats(stats, war, war_attacks, resource_prices)
                self._add_defender_loot(stats, war, war_attacks, resource_prices)

            # ── Unit counts (always from war-level columns) ───────────────────
            if att_id == nw_nation_id:
                stats['soldiers_lost']   += war.get('att_soldiers_lost',  0) or 0
                stats['tanks_lost']      += war.get('att_tanks_lost',     0) or 0
                stats['aircraft_lost']   += war.get('att_aircraft_lost',  0) or 0
                stats['ships_lost']      += war.get('att_ships_lost',     0) or 0
                stats['soldiers_killed'] += war.get('def_soldiers_lost',  0) or 0
                stats['tanks_killed']    += war.get('def_tanks_lost',     0) or 0
                stats['aircraft_killed'] += war.get('def_aircraft_lost',  0) or 0
                stats['ships_killed']    += war.get('def_ships_lost',     0) or 0
            else:
                stats['soldiers_lost']   += war.get('def_soldiers_lost',  0) or 0
                stats['tanks_lost']      += war.get('def_tanks_lost',     0) or 0
                stats['aircraft_lost']   += war.get('def_aircraft_lost',  0) or 0
                stats['ships_lost']      += war.get('def_ships_lost',     0) or 0
                stats['soldiers_killed'] += war.get('att_soldiers_lost',  0) or 0
                stats['tanks_killed']    += war.get('att_tanks_lost',     0) or 0
                stats['aircraft_killed'] += war.get('att_aircraft_lost',  0) or 0
                stats['ships_killed']    += war.get('att_ships_lost',     0) or 0

            # ── Win / loss / peace ────────────────────────────────────────────
            winner_id = war.get('winner_id')
            att_peace = war.get('att_peace')
            def_peace = war.get('def_peace')
            is_peace = (
                (not winner_id or str(winner_id) == '0')
                and att_peace == 1 and def_peace == 1
            )
            if is_peace:
                stats['peace'] += 1
            elif winner_id and str(winner_id) != '0':
                if str(winner_id) == str(nw_nation_id):
                    stats['wins'] += 1
                else:
                    stats['losses'] += 1

        # ── Backfill missing nation names from GlobalNations.db ───────────────
        missing_ids = [nid for nid, s in nation_stats.items() if not s['nation_name']]
        if missing_ids:
            try:
                from PnWHarvester.db.global_nations_db import GlobalNationsDB
                from Systems.Functions.db_paths import GLOBAL_NATIONS_DB as _GNDB
                gdb = GlobalNationsDB(str(_GNDB))
                nw_nations = await gdb.get_nations_by_alliance(NW_ALLIANCE_ID)
                name_map = {n['nation_id']: n['nation_name'] for n in nw_nations if n.get('nation_id') and n.get('nation_name')}
                for nid in missing_ids:
                    if nid in name_map:
                        nation_stats[nid]['nation_name'] = name_map[nid]
            except Exception as e:
                self.logger.warning(f"Could not backfill nation names: {e}")
        
        return nation_stats

    def _add_attacker_stats(self, stats: Dict[str, Any], war: Dict[str, Any], attacks: List[Dict[str, Any]], resource_prices: Dict[str, Any]):
        """Add statistics for when NW nation is the attacker."""
        sell_prices = resource_prices.get('sell', {})
        
        att_soldiers_lost = war.get('att_soldiers_lost', 0) or 0
        att_tanks_lost = war.get('att_tanks_lost', 0) or 0
        att_aircraft_lost = war.get('att_aircraft_lost', 0) or 0
        att_ships_lost = war.get('att_ships_lost', 0) or 0
        att_infra_destroyed_value = war.get('att_infra_destroyed_value', 0) or 0

        # Count missiles/nukes from attack rows (war-level columns are always 0)
        att_missiles_used = sum(
            1 for a in attacks
            if str(a.get('type', '')).upper() in ('MISSILE', 'MISSILEFAIL')
            and a.get('attacker_id') == war.get('att_id')
        )
        att_nukes_used = sum(
            1 for a in attacks
            if str(a.get('type', '')).upper() in ('NUKE', 'NUKEFAIL')
            and a.get('attacker_id') == war.get('att_id')
        )
        
        buy_prices = resource_prices.get('buy', {})
        unit_cost = (
            att_soldiers_lost * calculate_unit_cost('soldiers', buy_prices)
            + att_tanks_lost    * calculate_unit_cost('tanks',    buy_prices)
            + att_aircraft_lost * calculate_unit_cost('aircraft', buy_prices)
            + att_ships_lost    * calculate_unit_cost('ships',    buy_prices)
        )

        bomb_cost = (
            att_missiles_used * calculate_unit_cost('missiles', buy_prices)
            + att_nukes_used  * calculate_unit_cost('nukes',    buy_prices)
        )

        total_cost = unit_cost + bomb_cost + att_infra_destroyed_value

        def_infra_destroyed_value = war.get('def_infra_destroyed_value', 0) or 0
        def_soldiers_lost = war.get('def_soldiers_lost', 0) or 0
        def_tanks_lost = war.get('def_tanks_lost', 0) or 0
        def_aircraft_lost = war.get('def_aircraft_lost', 0) or 0
        def_ships_lost = war.get('def_ships_lost', 0) or 0

        damages = (
            def_infra_destroyed_value
            + def_soldiers_lost * calculate_unit_cost('soldiers', buy_prices)
            + def_tanks_lost    * calculate_unit_cost('tanks',    buy_prices)
            + def_aircraft_lost * calculate_unit_cost('aircraft', buy_prices)
            + def_ships_lost    * calculate_unit_cost('ships',    buy_prices)
        )
        
        war_net = damages - total_cost
        
        stats['war_cost'] += total_cost
        stats['war_net'] += war_net
        stats['damages'] += damages
        stats['bomb_cost'] += bomb_cost

    def _add_attacker_loot(self, stats: Dict[str, Any], war: Dict[str, Any], 
                          attacks: List[Dict[str, Any]], resource_prices: Dict[str, Any]):
        """Calculate loot for when NW nation is the attacker."""
        sell_prices = resource_prices.get('sell', {})
        att_id = war.get('att_id')
        
        loot_gained = 0
        loot_lost = 0
        
        for attack in attacks:
            if attack.get('attacker_id') == att_id:
                # NW nation attacked - calculate loot gained
                loot_gained += self._calculate_attack_loot_value(attack, sell_prices)
            elif attack.get('defender_id') == att_id:
                # NW nation was attacked - calculate loot lost
                loot_lost += self._calculate_attack_loot_value(attack, sell_prices)
        
        net_loot = loot_gained - loot_lost
        stats['loot'] += net_loot

    def _add_defender_stats(self, stats: Dict[str, Any], war: Dict[str, Any], attacks: List[Dict[str, Any]], resource_prices: Dict[str, Any]):
        """Add statistics for when NW nation is the defender."""
        sell_prices = resource_prices.get('sell', {})
        
        def_soldiers_lost = war.get('def_soldiers_lost', 0) or 0
        def_tanks_lost = war.get('def_tanks_lost', 0) or 0
        def_aircraft_lost = war.get('def_aircraft_lost', 0) or 0
        def_ships_lost = war.get('def_ships_lost', 0) or 0
        def_infra_destroyed_value = war.get('def_infra_destroyed_value', 0) or 0

        # Count missiles/nukes from attack rows (war-level columns are always 0)
        def_missiles_used = sum(
            1 for a in attacks
            if str(a.get('type', '')).upper() in ('MISSILE', 'MISSILEFAIL')
            and a.get('attacker_id') == war.get('def_id')
        )
        def_nukes_used = sum(
            1 for a in attacks
            if str(a.get('type', '')).upper() in ('NUKE', 'NUKEFAIL')
            and a.get('attacker_id') == war.get('def_id')
        )
        
        buy_prices = resource_prices.get('buy', {})
        unit_cost = (
            def_soldiers_lost * calculate_unit_cost('soldiers', buy_prices)
            + def_tanks_lost    * calculate_unit_cost('tanks',    buy_prices)
            + def_aircraft_lost * calculate_unit_cost('aircraft', buy_prices)
            + def_ships_lost    * calculate_unit_cost('ships',    buy_prices)
        )

        bomb_cost = (
            def_missiles_used * calculate_unit_cost('missiles', buy_prices)
            + def_nukes_used  * calculate_unit_cost('nukes',    buy_prices)
        )

        total_cost = unit_cost + bomb_cost + def_infra_destroyed_value

        att_infra_destroyed_value = war.get('att_infra_destroyed_value', 0) or 0
        att_soldiers_lost = war.get('att_soldiers_lost', 0) or 0
        att_tanks_lost = war.get('att_tanks_lost', 0) or 0
        att_aircraft_lost = war.get('att_aircraft_lost', 0) or 0
        att_ships_lost = war.get('att_ships_lost', 0) or 0

        damages = (
            att_infra_destroyed_value
            + att_soldiers_lost * calculate_unit_cost('soldiers', buy_prices)
            + att_tanks_lost    * calculate_unit_cost('tanks',    buy_prices)
            + att_aircraft_lost * calculate_unit_cost('aircraft', buy_prices)
            + att_ships_lost    * calculate_unit_cost('ships',    buy_prices)
        )
        
        war_net = damages - total_cost
        
        stats['war_cost'] += total_cost
        stats['war_net'] += war_net
        stats['damages'] += damages
        stats['bomb_cost'] += bomb_cost

    def _add_defender_loot(self, stats: Dict[str, Any], war: Dict[str, Any], 
                          attacks: List[Dict[str, Any]], resource_prices: Dict[str, Any]):
        """Calculate loot for when NW nation is the defender."""
        sell_prices = resource_prices.get('sell', {})
        def_id = war.get('def_id')
        
        loot_gained = 0
        loot_lost = 0
        
        for attack in attacks:
            if attack.get('attacker_id') == def_id:
                # NW nation attacked - calculate loot gained
                loot_gained += self._calculate_attack_loot_value(attack, sell_prices)
            elif attack.get('defender_id') == def_id:
                # NW nation was attacked - calculate loot lost
                loot_lost += self._calculate_attack_loot_value(attack, sell_prices)
        
        net_loot = loot_gained - loot_lost
        stats['loot'] += net_loot

    def _calculate_attack_loot_value(self, attack: Dict[str, Any], sell_prices: Dict[str, Any]) -> float:
        """Calculate the total value of loot from an attack."""
        loot_value = 0
        
        # Money looted
        money_looted = attack.get('money_looted', 0) or 0
        loot_value += money_looted
        
        # Resource loot
        resources = ['coal', 'oil', 'uranium', 'iron', 'bauxite', 'lead', 
                    'gasoline', 'munitions', 'steel', 'aluminum', 'food']
        
        for resource in resources:
            amount = attack.get(f'{resource}_looted', 0) or 0
            price = sell_prices.get(resource, 0)
            loot_value += amount * price
        
        return loot_value

    def _create_rankings_embed(self, nation_stats: Dict[int, Dict[str, Any]], ranking_type: str, 
                             time_str: str) -> discord.Embed:
        """Create the rankings embed."""
        # Sort nations by the selected ranking type
        sorted_nations = sorted(
            nation_stats.items(),
            key=lambda x: x[1][ranking_type],
            reverse=True
        )[:25]  # Top 25
        
        # Create embed
        type_names = {
            'war_cost':        'War Cost',
            'war_net':         'War Net',
            'damages':         'Damages',
            'bomb_cost':       'Bomb Cost',
            'loot':            'Loot',
            'soldiers_lost':   'Soldiers Lost',
            'soldiers_killed': 'Soldiers Killed',
            'tanks_lost':      'Tanks Lost',
            'tanks_killed':    'Tanks Killed',
            'aircraft_lost':   'Aircraft Lost',
            'aircraft_killed': 'Aircraft Killed',
            'ships_lost':      'Ships Lost',
            'ships_killed':    'Ships Killed',
            'peace':           'Peace',
            'wins':            'Wins',
            'losses':          'Losses',
        }

        type_emojis = {
            'war_cost':        '💸',
            'war_net':         '📊',
            'damages':         '💥',
            'bomb_cost':       '🚀',
            'loot':            '💰',
            'soldiers_lost':   '🪖',
            'soldiers_killed': '⚔️',
            'tanks_lost':      '🛡️',
            'tanks_killed':    '💣',
            'aircraft_lost':   '✈️',
            'aircraft_killed': '🎯',
            'ships_lost':      '⚓',
            'ships_killed':    '🌊',
            'peace':           '🕊️',
            'wins':            '🏆',
            'losses':          '💀',
        }

        # Types that display as dollar amounts vs raw counts
        DOLLAR_TYPES = {'war_cost', 'war_net', 'damages', 'bomb_cost', 'loot'}
        
        ranking_name = type_names.get(ranking_type, ranking_type)
        emoji = type_emojis.get(ranking_type, '📈')
        
        time_display = "All Time" if time_str == "all" else time_str.upper()
        
        embed = discord.Embed(
            title=f"{emoji} Top 25 Nations by {ranking_name}",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        
        if not sorted_nations:
            embed.description = f"**Time Range:** {time_display}"
            embed.add_field(
                name="No Data",
                value="No war data found for the specified criteria.",
                inline=False
            )
            return embed
        
        # Create ranking list
        ranking_lines = []
        for i, (nation_id, stats) in enumerate(sorted_nations, 1):
            nation_name = stats['nation_name'] or f"Nation #{nation_id}"
            value = stats[ranking_type]
            
            # Create masked nation link
            nation_link = f"[{nation_name}](https://politicsandwar.com/nation/id={nation_id})"
            
            # Format value based on type
            if ranking_type in DOLLAR_TYPES:
                value_str = f"${value:,.0f}"
            else:
                value_str = f"{value:,}"
            
            # Add rank emoji for top 3
            rank_emoji = ""
            if i == 1:
                rank_emoji = "🥇 "
            elif i == 2:
                rank_emoji = "🥈 "
            elif i == 3:
                rank_emoji = "🥉 "
            
            ranking_lines.append(f"{rank_emoji}**{i}.** {nation_link} — {value_str}")
        
        # Put all rankings in the embed description to avoid field char limits
        # (description supports up to 4096 chars, plenty for 25 entries)
        rankings_text = "\n".join(ranking_lines)
        embed.description = (
            f"**Time Range:** {time_display}\n\n"
            + rankings_text
        )
        
        return embed

    @app_commands.command(name="rankings", description="Show top 25 nations ranked by war statistics")
    @app_commands.describe(
        ranking_type="What to rank nations by (War Cost, War Net, Damages, Bomb Cost, or Loot)",
        time="How far back to look (e.g., 2d, 1w, 1m, 1y, or all - defaults to All Time)",
    )
    @app_commands.choices(ranking_type=RANKING_TYPES)
    async def rankings(
        self,
        interaction: discord.Interaction,
        ranking_type: str,
        time: Optional[str] = "all",
    ):
        """Show top 25 nations ranked by war statistics."""
        await interaction.response.defer()
        
        try:
            # Parse parameters
            after_datetime = self._parse_time_to_datetime(time or "all")
            enemy_alliance_ids: List[int] = []
            
            # Get resource prices
            resource_prices = await get_resource_prices()
            if not resource_prices:
                resource_prices = {"sell": {}, "buy": {}}
            
            # Get wars from database
            db = IRSWarsDB(NW_DB_PATH)
            start_date = after_datetime.date() if after_datetime else None
            end_date = datetime.now(timezone.utc).date()
            
            # Get wars where NW is attacker or defender
            att_wars = await db.get_wars_by_alliance_in_range(
                NW_ALLIANCE_ID, role='attacker', start_date=start_date, end_date=end_date
            )
            def_wars = await db.get_wars_by_alliance_in_range(
                NW_ALLIANCE_ID, role='defender', start_date=start_date, end_date=end_date
            )
            
            # Combine and deduplicate wars
            seen_ids = set()
            all_wars = []
            for war in att_wars + def_wars:
                if war['id'] not in seen_ids:
                    seen_ids.add(war['id'])
                    all_wars.append(war)
            
            # Calculate nation statistics
            nation_stats = await self._calculate_nation_stats(
                all_wars, resource_prices, ranking_type, enemy_alliance_ids
            )
            
            # Create and send embed
            embed = self._create_rankings_embed(nation_stats, ranking_type, time or "all")
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            self.logger.error(f"Error in rankings command: {e}", exc_info=True)
            error_embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while generating rankings. Please try again.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed)

async def setup(bot):
    await bot.add_cog(Rankings(bot))
