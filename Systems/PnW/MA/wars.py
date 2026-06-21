import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional, List, Union
from datetime import datetime, timedelta, timezone
import re
import io
import math
from PIL import Image, ImageDraw, ImageFont
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER

from Systems.Functions.emoji import resource_emoji, military_codes, improvement_emoji_map, mention, get_animated_partial, MISSILE_EMOJI, BOMB_EMOJI
from Systems.Functions.db_paths import NW_WARS_DB_STR as NW_DB_PATH, NW_NATIONS_DB_STR as NW_NATIONS_DB_PATH
from Systems.Functions.nation_emoji_store import get_nation_emoji, strip_emoji_prefix
from Systems.PnW.Util.war_calc import (
    get_resource_prices,
    calculate_war_costs,
    calculate_single_war_costs,
    calculate_improvement_cost,
    WAR_SUMMARY_THRESHOLD
)
import uuid

class Wars(commands.Cog):
    """Cog for P&W war-related commands."""

    def __init__(self, bot):
        self.bot = bot

    def _parse_time_to_utc_datetime(self, time_str: str) -> Optional[datetime]:
        """Parse time string like '1d', '3w' into a UTC datetime object."""
        if not time_str:
            return None
        
        match = re.match(r'(\d+)([dwm])', time_str.lower())
        if not match:
            return None
        
        amount, unit = int(match.group(1)), match.group(2)
        
        delta = timedelta()
        if unit == 'd':
            delta = timedelta(days=amount)
        elif unit == 'w':
            delta = timedelta(weeks=amount)
        elif unit == 'm':
            delta = timedelta(days=amount * 30)
        
        return datetime.now(timezone.utc) - delta

    def _parse_identifiers(self, identifiers_str: str) -> List[Union[int, str]]:
        """Parse comma-separated identifiers (IDs or names), stripping any leading emoji prefix."""
        if not identifiers_str:
            return []
        identifiers = []
        for item in identifiers_str.split(','):
            item = item.strip()
            # Strip leading emoji + space added by autocomplete (e.g. '⭐ Flim Flam Fugazies')
            if ' ' in item and not item.isdigit():
                parts = item.split(' ', 1)
                if len(parts[0]) <= 2:  # emoji is 1-2 chars
                    item = parts[1].strip()
            if item.isdigit():
                identifiers.append(int(item))
            else:
                identifiers.append(item)
        return identifiers

    def _normalize_wars(self, wars: list) -> list:
        """Inject nested attacker/defender dicts into flat DB rows so they
        match the structure expected by calculate_war_costs and _get_war_participants."""
        normalized = []
        for war in wars:
            w = dict(war)
            if 'attacker' not in w or w['attacker'] is None:
                att_name = w.get('att_nation_name') or (f"Nation #{w.get('att_id')}" if w.get('att_id') else 'Unknown')
                w['attacker'] = {
                    'nation_name': att_name,
                    'leader_name': w.get('att_leader_name', ''),
                    'alliance_name': w.get('att_alliance_name') or '',
                    'id': w.get('att_id'),
                    'alliance_id': w.get('att_alliance_id'),
                }
            if 'defender' not in w or w['defender'] is None:
                def_name = w.get('def_nation_name') or (f"Nation #{w.get('def_id')}" if w.get('def_id') else 'Unknown')
                w['defender'] = {
                    'nation_name': def_name,
                    'leader_name': w.get('def_leader_name', ''),
                    'alliance_name': w.get('def_alliance_name') or '',
                    'id': w.get('def_id'),
                    'alliance_id': w.get('def_alliance_id'),
                }
            normalized.append(w)
        return normalized

    async def _get_all_wars_from_db(self, after_datetime: Optional[datetime]) -> list:
        """Fetch ALL wars from IRSWars.db (no alliance filter), with attacks attached."""
        from Systems.Functions.irs_wars_db import IRSWarsDB
        db = IRSWarsDB(NW_DB_PATH)
        start_date = after_datetime.date() if after_datetime else None
        end_date = datetime.now(timezone.utc).date()
        all_wars = await db.get_all_wars_in_range(start_date=start_date, end_date=end_date)
        return await self._attach_attacks(db, self._normalize_wars(all_wars))

    async def _get_nation_wars_from_db(self, nation_ids: List[int], after_datetime: Optional[datetime]) -> list:
        """Fetch wars from IRSWars.db for specific nation IDs (attacker or defender), with attacks attached."""
        from Systems.Functions.irs_wars_db import IRSWarsDB
        db = IRSWarsDB(NW_DB_PATH)
        start_date = after_datetime.date() if after_datetime else None
        end_date = datetime.now(timezone.utc).date()
        all_wars = await db.get_all_wars_in_range(start_date=start_date, end_date=end_date)
        nation_id_set = {int(n) for n in nation_ids}
        seen_ids = set()
        combined = []
        for w in all_wars:
            if w['id'] not in seen_ids:
                att_id = w.get('att_id')
                def_id = w.get('def_id')
                if (att_id and int(att_id) in nation_id_set) or (def_id and int(def_id) in nation_id_set):
                    seen_ids.add(w['id'])
                    combined.append(w)
        return await self._attach_attacks(db, self._normalize_wars(combined))

    async def _attach_attacks(self, db, wars: list) -> list:
        """Bulk-fetch and attach war_attacks to each war dict so war_calc can
        process attack-level missile/nuke losses and loot fields."""
        if not wars:
            return wars
        war_ids = [w['id'] for w in wars]
        attacks_by_war = await db.get_attacks_for_wars(war_ids)
        for war in wars:
            attacks = attacks_by_war.get(war['id'], [])
            # Normalise field names and inject alliance IDs from the parent war
            # so war_calc can correctly bucket each attack to team1 or team2
            war_att_id = war.get('att_id')
            war_def_id = war.get('def_id')
            war_att_alliance_id = war.get('att_alliance_id')
            war_def_alliance_id = war.get('def_alliance_id')
            for a in attacks:
                # attacker_id → att_id
                if a.get('att_id') is None and a.get('attacker_id') is not None:
                    a['att_id'] = a['attacker_id']
                if a.get('def_id') is None and a.get('defender_id') is not None:
                    a['def_id'] = a['defender_id']
                # Inject att_alliance_id / def_alliance_id from the parent war
                # by matching the attack's nation IDs to the war's att_id/def_id
                if a.get('att_alliance_id') is None:
                    if a.get('att_id') == war_att_id:
                        a['att_alliance_id'] = war_att_alliance_id
                    elif a.get('att_id') == war_def_id:
                        a['att_alliance_id'] = war_def_alliance_id
                if a.get('def_alliance_id') is None:
                    if a.get('def_id') == war_def_id:
                        a['def_alliance_id'] = war_def_alliance_id
                    elif a.get('def_id') == war_att_id:
                        a['def_alliance_id'] = war_att_alliance_id
            war['attacks'] = attacks
        return wars

    def _extract_team2_from_wars(self, wars: list, team1_id_set: set, team1_type: str) -> tuple:
        """From a list of wars, derive the opponent IDs and type for Team2.
        Returns (team2_id_set, team2_type, team2_label).
        """
        opp_nation_ids = set()
        opp_alliance_ids = set()
        str_t1 = {str(i) for i in team1_id_set}

        for war in wars:
            att_id = str(war.get('att_id', ''))
            att_aa = str(war.get('att_alliance_id', ''))
            def_id = str(war.get('def_id', ''))
            def_aa = str(war.get('def_alliance_id', ''))

            # Determine which side is team1
            team1_is_att = att_id in str_t1 or att_aa in str_t1
            if team1_is_att:
                if def_aa and def_aa != '0' and def_aa != 'None':
                    opp_alliance_ids.add(int(def_aa))
                if def_id and def_id != '0' and def_id != 'None':
                    opp_nation_ids.add(int(def_id))
            else:
                if att_aa and att_aa != '0' and att_aa != 'None':
                    opp_alliance_ids.add(int(att_aa))
                if att_id and att_id != '0' and att_id != 'None':
                    opp_nation_ids.add(int(att_id))

        if team1_type == 'alliance':
            if opp_alliance_ids:
                return opp_alliance_ids, 'alliance', 'Opponents'
            return opp_nation_ids, 'nation', 'Opponents'
        else:
            if opp_nation_ids:
                return opp_nation_ids, 'nation', 'Opponents'
            return opp_alliance_ids, 'alliance', 'Opponents'

    # ── DB-only resolution helpers ────────────────────────────────────────────

    async def _resolve_nation_ids_from_db(self, identifiers: List[Union[int, str]]) -> List[int]:
        """Resolve nation names/IDs to IDs using GlobalNations.db — no API call."""
        try:
            from PnWHarvester.db.global_nations_db import GlobalNationsDB
            from Systems.Functions.db_paths import GLOBAL_NATIONS_DB as _GNDB
            db = GlobalNationsDB(str(_GNDB))
            resolved = []
            for ident in identifiers:
                ident_str = str(ident).strip()
                if ident_str.isdigit():
                    resolved.append(int(ident_str))
                else:
                    low = ident_str.lower()
                    nation = await db.get_nation_by_name(low)
                    if nation and nation.get('id'):
                        resolved.append(int(nation['id']))
            return resolved
        except Exception as e:
            logging.warning(f"_resolve_nation_ids_from_db failed: {e}")
            return []

    async def _resolve_team2_ids_from_db(
        self,
        identifiers: List[Union[int, str]],
        team2_type: str,
        nw_wars: list,
    ) -> List[int]:
        """Resolve team2 identifiers entirely from the wars DB — no API call.

        For nations: match att_nation_name / def_nation_name in the wars.
        For alliances: match att_alliance_id / def_alliance_id (autocomplete
                       already provides the numeric ID as the value).
        """
        resolved = []
        for ident in identifiers:
            ident_str = str(ident).strip()

            if team2_type == 'alliance':
                # Autocomplete sets value = str(alliance_id), so this is already an ID
                if ident_str.isdigit():
                    resolved.append(int(ident_str))
                else:
                    # Name typed manually — scan wars DB for matching alliance name
                    low = ident_str.lower()
                    for war in nw_wars:
                        for col_id, col_name in (
                            ('att_alliance_id', 'att_alliance_name'),
                            ('def_alliance_id', 'def_alliance_name'),
                        ):
                            aname = (war.get(col_name) or '').lower()
                            if aname and low in aname:
                                aid = war.get(col_id)
                                if aid and int(aid) not in resolved:
                                    resolved.append(int(aid))
                                break

            elif team2_type == 'nation':
                if ident_str.isdigit():
                    resolved.append(int(ident_str))
                else:
                    # Name — scan wars DB for matching nation name
                    low = ident_str.lower()
                    for war in nw_wars:
                        for col_id, col_name in (
                            ('att_id', 'att_nation_name'),
                            ('def_id', 'def_nation_name'),
                        ):
                            nname = (war.get(col_name) or '').lower()
                            if nname and low in nname:
                                nid = war.get(col_id)
                                if nid and int(nid) not in resolved:
                                    resolved.append(int(nid))
                                break

        return resolved

    # ── Autocomplete helpers ──────────────────────────────────────────────────

    async def _get_nations_for_autocomplete(self) -> list:
        """Load nations from GlobalNations.db for autocomplete."""
        try:
            from PnWHarvester.db.global_nations_db import GlobalNationsDB
            from Systems.Functions.db_paths import GLOBAL_NATIONS_DB as _GNDB
            db = GlobalNationsDB(str(_GNDB))
            return await db.get_all_nations()
        except Exception as e:
            logging.warning(f"wars autocomplete: could not load nations: {e}")
            return []

    async def team1_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for team1.
        Requires team1_type to be selected first — returns empty until it is.
        - team1_type == alliance → suggest alliances from the wars DB
        - team1_type == nation   → suggest nations from GlobalNations.db
        """
        try:
            team1_type = getattr(interaction.namespace, 'team1_type', None)

            if not team1_type:
                return []

            if team1_type == 'alliance':
                try:
                    from Systems.Functions.irs_wars_db import IRSWarsDB
                    db = IRSWarsDB(NW_DB_PATH)
                    rows = await db.get_all_distinct_alliances(current)
                    choices = []
                    for r in rows[:25]:
                        aid = str(r['alliance_id'])
                        name = r['alliance_name']
                        label = name if name else f"Alliance {aid}"
                        choices.append(app_commands.Choice(name=label, value=aid))
                    return choices
                except Exception as e:
                    logging.warning(f"team1 alliance autocomplete error: {e}")
                    return []

            if team1_type == 'nation':
                try:
                    from Systems.Functions.autocomplete_utils import nation_autocomplete
                    return await nation_autocomplete(current, nw_only=False, limit=25)
                except Exception as e:
                    logging.warning(f"team1 nation autocomplete error: {e}")
                    return []

            return []
        except Exception as e:
            logging.warning(f"team1_autocomplete error: {e}")
            return []

    async def team2_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for team2.
        Requires BOTH team2_type AND team1 to be filled first.
        - team2_type == alliance → suggest opponent alliances (by ID) from the wars DB
        - team2_type == nation   → suggest opponent nations from the wars DB
        Both are scoped to whoever is in team1 (NW alliance or a specific NW member nation).
        """
        try:
            from Systems.Functions.irs_wars_db import IRSWarsDB
            ns = interaction.namespace

            # Read from interaction.data options directly — more reliable than namespace
            # when the user hasn't tabbed away from a field yet
            options_map: dict = {}
            for opt in (interaction.data or {}).get('options', []):
                options_map[opt['name']] = opt.get('value')

            team1_type = options_map.get('team1_type') or getattr(ns, 'team1_type', None)
            team1_val  = (options_map.get('team1') or getattr(ns, 'team1', None) or '').strip()
            team2_type = options_map.get('team2_type') or getattr(ns, 'team2_type', None)

            # Strip any emoji prefix that may have been prepended by the autocomplete display
            # e.g. "🧌 Flim Flam Fugazies" → "Flim Flam Fugazies"
            if team1_val and not team1_val.isdigit():
                # Remove leading emoji + space if present (emoji is 1-2 chars + space)
                parts = team1_val.split(' ', 1)
                if len(parts) == 2 and len(parts[0]) <= 2:
                    team1_val = parts[1].strip()

            # Force user to pick both types and fill team1 first
            if not team2_type or not team1_val or not team1_type:
                return []

            db = IRSWarsDB(NW_DB_PATH)

            # ── Team1 is an alliance ───────────────────────────────
            if team1_type == 'alliance' and team1_val:
                # Resolve the alliance ID from the label/ID
                try:
                    alliance_id = int(team1_val) if team1_val.isdigit() else None
                except ValueError:
                    alliance_id = None

                if alliance_id:
                    if team2_type == 'nation':
                        names = await db.get_opponent_nation_names(alliance_id, current)
                        return [app_commands.Choice(name=n, value=n) for n in names[:25]]

                    if team2_type == 'alliance':
                        rows = await db.get_opponent_alliance_ids(alliance_id, current)
                        choices = []
                        for r in rows[:25]:
                            aid = str(r['alliance_id'])
                            name = r['alliance_name']
                            label = name if name else f"Alliance {aid}"
                            choices.append(app_commands.Choice(name=label, value=aid))
                        return choices

            # ── Team1 is a specific nation ─────────────────────────
            if team1_type == 'nation' and team1_val:
                try:
                    nation_id = int(team1_val) if team1_val.isdigit() else None
                except ValueError:
                    nation_id = None

                if not nation_id:
                    # Try to resolve by name from GlobalNations.db
                    try:
                        from PnWHarvester.db.global_nations_db import GlobalNationsDB
                        from Systems.Functions.db_paths import GLOBAL_NATIONS_DB as _GNDB
                        ndb = GlobalNationsDB(str(_GNDB))
                        nat = await ndb.get_nation_by_name(team1_val)
                        if nat and nat.get('id'):
                            nation_id = int(nat['id'])
                    except Exception:
                        pass

                if nation_id:
                    if team2_type == 'nation':
                        names = await db.get_opponent_nation_names_for_nation(nation_id, current)
                        return [app_commands.Choice(name=n, value=n) for n in names[:25]]

                    if team2_type == 'alliance':
                        rows = await db.get_opponent_alliance_ids_for_nation(nation_id, current)
                        choices = []
                        for r in rows[:25]:
                            aid = str(r['alliance_id'])
                            name = r['alliance_name']
                            label = name if name else f"Alliance {aid}"
                            choices.append(app_commands.Choice(name=label, value=aid))
                        return choices

            return []
        except Exception as e:
            logging.warning(f"team2_autocomplete error: {e}")
            return []

    # ── Command ───────────────────────────────────────────────────────────────

    @app_commands.command(name="wars", description="War-related commands for P&W")
    @app_commands.describe(
        team1_type="Type of Team 1 (Alliance or Nation)",
        team1="Comma-separated alliance/nation names or IDs for Team 1",
        time="Time range (e.g., '1d', '3w', '5m') for recent wars",
        team2="Optional: Comma-separated alliance/nation names or IDs for Team 2",
        team2_type="Optional: Type of Team 2 (Alliance or Nation)"
    )
    @app_commands.choices(
        team1_type=[
            app_commands.Choice(name="Alliance", value="alliance"),
            app_commands.Choice(name="Nation", value="nation"),
        ],
        team2_type=[
            app_commands.Choice(name="Alliance", value="alliance"),
            app_commands.Choice(name="Nation", value="nation"),
        ]
    )
    @app_commands.autocomplete(team1=team1_autocomplete, team2=team2_autocomplete)
    async def wars(self, interaction: discord.Interaction, team1_type: str, team1: str, time: Optional[str] = None, team2: Optional[str] = None, team2_type: Optional[str] = None):
        """Calculates the cost of a war for the given team1 and team2."""
        try:
            await interaction.response.defer(thinking=True)
        except discord.NotFound:
            logging.warning("Interaction expired before deferral. Command will not be processed.")
            return
        
        try:
            after_datetime = self._parse_time_to_utc_datetime(time)
            team1_ids = self._parse_identifiers(team1)

            if not team1_ids:
                await interaction.followup.send("❌ Please provide at least one Team 1 identifier.")
                return

            resource_prices = await get_resource_prices()

            # ── Resolve Team1 and fetch wars ───────────────────────
            all_wars_db = await self._get_all_wars_from_db(after_datetime)

            if team1_type == 'alliance':
                # For alliance, the identifier is the alliance ID from autocomplete
                resolved_team1_ids = [int(i) for i in team1_ids if str(i).isdigit()]
            else:
                # For nation, resolve IDs from GlobalNations.db
                resolved_team1_ids = await self._resolve_nation_ids_from_db(team1_ids)

            if not resolved_team1_ids:
                await interaction.followup.send("❌ Could not resolve Team 1. Please use a valid nation or alliance ID.")
                return

            team1_id_set = set(resolved_team1_ids)

            # ── Filter wars to those involving Team1 ──────────────────────────
            str_t1 = {str(i) for i in team1_id_set}
            filtered_wars = []
            for war in all_wars_db:
                if (str(war.get('att_id')) in str_t1 or
                    str(war.get('att_alliance_id')) in str_t1 or
                    str(war.get('def_id')) in str_t1 or
                    str(war.get('def_alliance_id')) in str_t1):
                    filtered_wars.append(war)

            if not filtered_wars:
                await interaction.followup.send("❌ No wars found for the specified criteria.")
                return

            # ── Resolve Team2 entirely from DB ────────────────────────────────
            resolved_team2_ids: List[int] = []
            effective_team2_type = team2_type

            if team2 and team2_type:
                team2_ids = self._parse_identifiers(team2)
                resolved_team2_ids = await self._resolve_team2_ids_from_db(
                    team2_ids, team2_type, filtered_wars
                )
            else:
                auto_t2_ids, auto_t2_type, _ = self._extract_team2_from_wars(
                    filtered_wars, team1_id_set, team1_type
                )
                resolved_team2_ids = list(auto_t2_ids)
                effective_team2_type = auto_t2_type

            all_wars = filtered_wars

            # ── When team2 is specified, narrow wars to those involving BOTH ────
            wars_data = list(all_wars)  # all already involve team1
            team2_id_set = set(resolved_team2_ids) if resolved_team2_ids else None

            if team2_id_set:
                wars_data = []
                for war in all_wars:
                    war_att_ids = {
                        int(war[key]) for key in ('att_id', 'att_alliance_id') if war.get(key)
                    }
                    war_def_ids = {
                        int(war[key]) for key in ('def_id', 'def_alliance_id') if war.get(key)
                    }
                    is_match = (
                        (not team1_id_set.isdisjoint(war_att_ids) and not team2_id_set.isdisjoint(war_def_ids)) or
                        (not team1_id_set.isdisjoint(war_def_ids) and not team2_id_set.isdisjoint(war_att_ids))
                    )
                    if is_match:
                        wars_data.append(war)

            if not wars_data:
                await interaction.followup.send("❌ No wars found for the specified criteria.")
                return

            has_team2 = bool(resolved_team2_ids)
            pov_ids = team1_id_set if not has_team2 else None
            final_team2_id_set = set(resolved_team2_ids) if resolved_team2_ids else None

            display_team2_type = effective_team2_type
            display_team2 = team2

            costs = await calculate_war_costs(wars_data, resource_prices, team1_id_set=team1_id_set, team2_id_set=final_team2_id_set)

            embeds = {}

            display_team1 = team1
            summary_embed = self._create_summary_embed(costs, wars_data, time, display_team1, pov_ids, team2=display_team2)
            embeds['summary'] = summary_embed

            # Category Embeds
            t2_label = display_team2 or ("Opponents" if pov_ids else "Team 2")
            embeds['military'] = self._create_category_embed("Military", costs, resource_prices, display_team1, t2_label)
            embeds['destruction'] = self._create_category_embed("Destruction", costs, resource_prices, display_team1, t2_label)
            embeds['loot'] = self._create_category_embed("Loot", costs, resource_prices, display_team1, t2_label)

            war_report_file = None
            if len(wars_data) > WAR_SUMMARY_THRESHOLD:
                war_report_file = await self._generate_war_report_file(
                    wars_data, resource_prices, pov_ids,
                    team1_type, display_team1,
                    display_team2_type, display_team2,
                    team1_id_set, final_team2_id_set,
                    after_datetime=after_datetime
                )
            else:
                for i, war in enumerate(wars_data):
                    team1_name, team2_name = self._get_war_participants(
                        war, team1_type, display_team1,
                        display_team2_type, display_team2, pov_ids
                    )
                    reason = war.get('reason', 'No reason provided.')
                    winner_id = war.get('winner_id')
                    winner_name = "Ongoing"
                    if winner_id:
                        if str(winner_id) == str(war.get('att_id')) or str(winner_id) == str(war.get('att_alliance_id')):
                            winner_name = team1_name
                        elif str(winner_id) == str(war.get('def_id')) or str(winner_id) == str(war.get('def_alliance_id')):
                            winner_name = team2_name
                        else:
                            winner_name = f"ID: {winner_id}"

                    summary_embed.add_field(
                        name=f"War #{i+1}: {team1_name} vs {team2_name}",
                        value=f"**Reason:** {reason}\n**Winner:** {winner_name}",
                        inline=False
                    )

            graph_file = None
            try:
                graph_image = await self._generate_war_cost_graph(costs, resource_prices)
                if graph_image:
                    graph_file = discord.File(graph_image, filename="war_cost_graph.png")
                    summary_embed.set_image(url="attachment://war_cost_graph.png")
            except Exception as e:
                logging.error(f"Error generating war cost graph: {e}", exc_info=True)

            files_to_send = []
            if graph_file:
                files_to_send.append(graph_file)
            
            view = WarCostView(embeds, graph_file=graph_file, war_report_file=war_report_file)
            
            await interaction.followup.send(embed=summary_embed, view=view, files=files_to_send)
            
            view.message = await interaction.original_response()
            
        except Exception as e:
            logging.error(f"Error in wars cost command: {e}", exc_info=True)
            await interaction.followup.send(f"❌ An error occurred while calculating war costs: {str(e)}")

    def _get_war_participants(self, war: dict, team1_type: str, team1: str, team2_type: Optional[str], team2: Optional[str], pov_ids: Optional[set]) -> tuple[str, str]:
        """
        Determine the names of the war participants.
        If pov_ids is provided, returns (pov_entity_name, opponent_name).
        Otherwise, returns (actual_attacker_name, actual_defender_name).
        """
        str_pov_ids = {str(i) for i in pov_ids} if pov_ids else None

        if str_pov_ids:
            pov_name = team1
            is_pov_actual_attacker = str(war.get('att_id')) in str_pov_ids or str(war.get('att_alliance_id')) in str_pov_ids
            
            if is_pov_actual_attacker:
                opponent_name = (war.get('defender') or {}).get('nation_name') or (war.get('defender') or {}).get('alliance_name') or "Unknown"
            else:
                opponent_name = (war.get('attacker') or {}).get('nation_name') or (war.get('attacker') or {}).get('alliance_name') or "Unknown"
            return pov_name, opponent_name

        team1_name = (war.get('attacker') or {}).get('nation_name') or team1
        if team1_type == 'alliance':
            team1_name = team1

        team2_name = "Unknown"
        if team2_type and team2:
            if team2_type == 'alliance':
                team2_name = team2
            else:
                team2_name = (war.get('defender') or {}).get('nation_name') or team2
        else:
            team2_name = (war.get('defender') or {}).get('nation_name') or (war.get('defender') or {}).get('alliance_name') or "Unknown"
        
        return team1_name, team2_name

    def _create_summary_embed(self, costs: dict, wars_data: List[dict], time: Optional[str], team1: str, pov_ids: Optional[set], team2: Optional[str] = None) -> discord.Embed:
        """Create the summary embed."""
        description = f"Summary of wars involving specified entities{f' in the last {time}' if time else ''}"
        if pov_ids:
            description = f"Summary of all wars for {team1}{f' in the last {time}' if time else ''}"

        summary_embed = discord.Embed(
            title="📊 War Cost Summary",
            description=description,
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )

        t2_label = "Opponents" if pov_ids else (team2 or "Team 2")
        overview_value = (
            f"⚔️ **{team1}**\n"
            f"* Costs- `${costs['team1']['gross']:,.0f}`\n"
            f"* Net- `${costs['team1']['net']:,.0f}`\n"
            f"🛡️ **{t2_label}**\n"
            f"* Costs- `${costs['team2']['gross']:,.0f}`\n"
            f"* Net- `${costs['team2']['net']:,.0f}`\n"
            f"Wars Analyzed: **{len(wars_data)}**\n"
            f"Time Range: **{time or 'All time'}**"
        )
        
        summary_embed.add_field(name="Overview", value=overview_value, inline=False)

        if len(wars_data) > WAR_SUMMARY_THRESHOLD:
            summary_embed.add_field(
                name="Detailed War Report",
                value="Click the 'Breakdown PDF' button for a detailed report.",
                inline=False
            )
        return summary_embed

    def _create_category_embed(self, category: str, costs: dict, resource_prices: dict, team1_name: str = "Team 1", team2_name: str = "Team 2") -> discord.Embed:
        """Create an embed for a specific cost category."""
        embed = discord.Embed(title=f"{category} Costs", color=discord.Color.blue(), timestamp=datetime.now(timezone.utc))
        
        team1_details = self._get_category_details("team1", category, costs, resource_prices)
        team2_details = self._get_category_details("team2", category, costs, resource_prices)

        embed.add_field(name=f"⚔️ {team1_name}", value=team1_details if team1_details else "No costs", inline=True)
        embed.add_field(name=f"🛡️ {team2_name}", value=team2_details if team2_details else "No costs", inline=True)

        return embed

    def _get_category_details(self, side: str, category: str, costs: dict, resource_prices: dict) -> str:
        """Get formatted details for a specific category and side."""
        details = []
        if category == "Military":
            military_emojis = military_codes()
            units = costs[side]["units"]
            # Conventional units in display order
            CONVENTIONAL = ["soldiers", "tanks", "aircraft", "ships"]
            # Bombs (missiles + nukes) shown separately
            BOMBS = ["missiles", "nukes"]

            conventional_lines = []
            for unit in CONVENTIONAL:
                if unit in units:
                    data = units[unit]
                    emoji = military_emojis.get(unit, '')
                    conventional_lines.append(f"{emoji} {data['lost']:,.0f} {unit.title()} — ${data['cost']:,.0f}")

            bomb_lines = []
            for unit in BOMBS:
                if unit in units:
                    data = units[unit]
                    emoji = MISSILE_EMOJI if unit == "missiles" else BOMB_EMOJI
                    label = "Missiles" if unit == "missiles" else "Nukes"
                    bomb_lines.append(f"{emoji} {data['lost']:,.0f} {label} — ${data['cost']:,.0f}")

            if conventional_lines:
                details.append("**Unit Losses:**")
                details.extend(conventional_lines)

            if bomb_lines:
                if details:
                    details.append("")
                details.append("**Bombs Used:**")
                details.extend(bomb_lines)

            if costs[side]["consumption"]["munitions"] > 0 or costs[side]["consumption"]["gasoline"] > 0:
                details.append("\n**Consumption:**")
                munitions_amount = costs[side]['consumption']['munitions']
                gasoline_amount = costs[side]['consumption']['gasoline']
                munitions_value = munitions_amount * resource_prices['buy'].get('munitions', 0)
                gasoline_value = gasoline_amount * resource_prices['buy'].get('gasoline', 0)
                munitions_emoji = resource_emoji('munitions') or '⛽'
                gasoline_emoji = resource_emoji('gasoline') or '⛽'
                details.append(f"{munitions_emoji}{munitions_amount:,.0f} = ${munitions_value:,.0f}\n{gasoline_emoji}{gasoline_amount:,.0f} = ${gasoline_value:,.0f}")
        elif category == "Destruction":
            if costs[side]['infra_lost_value'] > 0:
                details.append("**Infrastructure:**")
                infra_value = costs[side]['infra_lost_value']
                infra_levels = costs[side]['infra_lost_levels']
                details.append(f"🏗️ {infra_levels:,.0f} levels = ${infra_value:,.0f}")

            if costs[side].get('money_destroyed', 0) > 0:
                if details:
                    details.append("")
                details.append("**Money Destroyed:**")
                money_destroyed_value = costs[side]['money_destroyed']
                details.append(f"💸 ${money_destroyed_value:,.0f}")

            if costs[side]['improvements_lost'] > 0:
                if details:
                    details.append("")
                details.append("**Improvements:**")
                improvements_cost = costs[side]['improvements_lost']
                details.append(f"${improvements_cost:,.0f}")
                improvement_emojis = improvement_emoji_map()
                for name, count in sorted(costs[side]['improvements_destroyed'].items()):
                    emoji_name = improvement_emojis.get(name)
                    emoji = mention(emoji_name) if emoji_name else '🛠️'
                    details.append(f"{count} {name.replace('_', ' ').title()} {emoji}")
        elif category == "Loot":
            cash_gained = costs[side].get('loot_received', 0)
            resource_gained = costs[side].get('resource_loot', {})
            total_gained = cash_gained + sum(resource_gained.values())

            if total_gained > 0:
                details.append(f"**Gained: ${total_gained:,.0f}**")
                if cash_gained > 0:
                    details.append(f"  Cash: ${cash_gained:,.0f}")
                for resource, value in sorted(resource_gained.items(), key=lambda item: item[1], reverse=True):
                    price = resource_prices.get("sell", {}).get(resource, 1)
                    original_amount = value / price if price > 0 else 0
                    emoji = resource_emoji(resource) or ''
                    details.append(f"{emoji} {original_amount:,.0f}")
        
        return "\n".join(details)

    def _get_category_details_for_pdf(self, side: str, category: str, costs: dict, resource_prices: dict) -> str:
        """Get formatted details for a specific category and side, formatted for PDF output."""
        details = []
        if category == "Military":
            units = costs[side]["units"]
            CONVENTIONAL = ["soldiers", "tanks", "aircraft", "ships"]
            BOMBS = ["missiles", "nukes"]

            conventional_lines = []
            for unit in CONVENTIONAL:
                if unit in units:
                    data = units[unit]
                    conventional_lines.append(f"{data['lost']:,.0f} {unit.title()} - ${data['cost']:,.0f}")

            bomb_lines = []
            for unit in BOMBS:
                if unit in units:
                    data = units[unit]
                    label = "Missiles" if unit == "missiles" else "Nukes"
                    bomb_lines.append(f"{data['lost']:,.0f} {label} - ${data['cost']:,.0f}")

            if conventional_lines:
                details.append("<b>Unit Losses:</b>")
                details.extend(conventional_lines)

            if bomb_lines:
                details.append("<br/><b>Bombs Used:</b>")
                details.extend(bomb_lines)

            # Consumption is rendered separately with resource images in the PDF
        elif category == "Destruction":
            if costs[side]['infra_lost_value'] > 0:
                details.append("<b>Infrastructure:</b>")
                infra_value = costs[side]['infra_lost_value']
                infra_levels = costs[side]['infra_lost_levels']
                details.append(f"{infra_levels:,.0f} levels = ${infra_value:,.0f}")

            if costs[side].get('money_destroyed', 0) > 0:
                details.append("<br/><b>Money Destroyed:</b>")
                money_destroyed_value = costs[side]['money_destroyed']
                details.append(f"${money_destroyed_value:,.0f}")

            if costs[side]['improvements_lost'] > 0:
                details.append("<br/><b>Improvements:</b>")
                improvements_cost = costs[side]['improvements_lost']
                details.append(f"<b>Total: ${improvements_cost:,.0f}</b>")
                improvement_emojis = improvement_emoji_map()
                for name, count in sorted(costs[side]['improvements_destroyed'].items()):
                    cost_per_one = calculate_improvement_cost(name, resource_prices)
                    total_value = count * cost_per_one
                    emoji_name = improvement_emojis.get(name)
                    emoji_text = f" ({emoji_name})" if emoji_name else ""
                    details.append(f"{count} {name.replace('_', ' ').title()}{emoji_text} - ${total_value:,.0f}")
        elif category == "Loot":
            cash_gained = costs[side].get('loot_received', 0)
            resource_gained = costs[side].get('resource_loot', {})
            total_gained = cash_gained + sum(resource_gained.values())

            if total_gained > 0:
                details.append(f"<b>Gained: ${total_gained:,.0f}</b>")
                if cash_gained > 0:
                    details.append(f"<b>$</b> Cash: ${cash_gained:,.0f}")
                for resource, value in sorted(resource_gained.items(), key=lambda item: item[1], reverse=True):
                    price = resource_prices.get("sell", {}).get(resource, 1)
                    original_amount = value / price if price > 0 else 0
                    sell_price = resource_prices.get("sell", {}).get(resource, 0)
                    details.append(f"({resource.title()}) {original_amount:,.0f} @ ${sell_price:,.0f} = ${value:,.0f}")
        
        return "<br/>".join(details)

    @staticmethod
    def _load_resource_image(img_path: str, size: int):
        """Load a resource PNG, composite transparent areas onto white, return a ReportLab Image."""
        from reportlab.platypus import Image as RLImage
        from PIL import Image as PILImage
        import io as _io

        try:
            pil_img = PILImage.open(img_path).convert('RGBA')
            # Composite onto white so transparent pixels don't render black in PDF
            white = PILImage.new('RGBA', pil_img.size, (255, 255, 255, 255))
            white.paste(pil_img, mask=pil_img.split()[3])
            rgb = white.convert('RGB')
            buf = _io.BytesIO()
            rgb.save(buf, format='PNG')
            buf.seek(0)
            return RLImage(buf, width=size, height=size)
        except Exception:
            return None

    def _build_consumption_flowables(self, side: str, costs: dict, resource_prices: dict, body_style) -> list:
        """Build consumption rows as a ReportLab table with resource PNG icons."""
        from reportlab.platypus import Image as RLImage, Table as RLTable, TableStyle as RLTableStyle
        from reportlab.lib.styles import ParagraphStyle
        import os

        RESOURCE_IMG_DIR = os.path.join("web", "static", "Emojis", "Resources")
        IMG_SIZE = 14

        mun_amount  = costs[side]['consumption']['munitions']
        gas_amount  = costs[side]['consumption']['gasoline']

        if not mun_amount and not gas_amount:
            return []

        row_style = ParagraphStyle('ConRow', parent=body_style, fontSize=8)
        bold_style = ParagraphStyle('ConBold', parent=body_style, fontName='Helvetica-Bold', fontSize=8)

        rows = [[Paragraph('<b>Consumption:</b>', bold_style), '', '']]

        for resource, amount in [('munitions', mun_amount), ('gasoline', gas_amount)]:
            if not amount:
                continue
            buy_price = resource_prices['buy'].get(resource, 0)
            value = amount * buy_price

            img_path = os.path.join(RESOURCE_IMG_DIR, f"{resource}.png")
            if os.path.exists(img_path):
                icon = self._load_resource_image(img_path, IMG_SIZE) or Paragraph(resource.title()[:3], row_style)
            else:
                icon = Paragraph(resource.title()[:3], row_style)

            rows.append([
                icon,
                Paragraph(f"{amount:,.0f} @ ${buy_price:,.0f}", row_style),
                Paragraph(f"= ${value:,.0f}", row_style),
            ])

        tbl = RLTable(rows, colWidths=[18, None, 60], hAlign='LEFT')
        tbl.setStyle(RLTableStyle([
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING',   (0, 0), (-1, -1), 2),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 2),
            ('TOPPADDING',    (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ('SPAN',          (0, 0), (-1, 0)),  # header spans all cols
        ]))
        return [tbl]

    def _build_loot_flowables(self, side: str, costs: dict, resource_prices: dict, body_style) -> list:
        """Build loot section as a list of ReportLab flowables with resource PNG images."""
        from reportlab.platypus import Image as RLImage, Table as RLTable, TableStyle as RLTableStyle
        from reportlab.lib import colors as rl_colors
        import os

        RESOURCE_IMG_DIR = os.path.join("web", "static", "Emojis", "Resources")
        IMG_SIZE = 14  # points — small inline icon

        cash_gained = costs[side].get('loot_received', 0)
        resource_gained = costs[side].get('resource_loot', {})
        total_gained = cash_gained + sum(resource_gained.values())

        if not total_gained:
            return []

        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib import colors as rl_colors
        bold_style = ParagraphStyle('LootBold', parent=body_style, fontName='Helvetica-Bold', fontSize=8)
        row_style  = ParagraphStyle('LootRow',  parent=body_style, fontSize=8)

        rows = []

        # Total header
        rows.append([Paragraph(f"<b>Gained: ${total_gained:,.0f}</b>", bold_style), '', ''])

        # Cash row — use $ symbol styled in green
        if cash_gained > 0:
            cash_label = Paragraph('<font color="#27AE60"><b>$</b></font> Cash', row_style)
            rows.append([cash_label, Paragraph(f'${cash_gained:,.0f}', row_style), ''])

        # Resource rows sorted by value descending
        for resource, value in sorted(resource_gained.items(), key=lambda x: x[1], reverse=True):
            sell_price = resource_prices.get("sell", {}).get(resource, 0)
            amount = value / sell_price if sell_price > 0 else 0

            img_path = os.path.join(RESOURCE_IMG_DIR, f"{resource.lower()}.png")
            if os.path.exists(img_path):
                icon = self._load_resource_image(img_path, IMG_SIZE) or Paragraph(resource.title()[:3], row_style)
            else:
                icon = Paragraph(resource.title()[:3], row_style)

            amount_text = Paragraph(f"{amount:,.0f} @ ${sell_price:,.0f}", row_style)
            value_text  = Paragraph(f"= ${value:,.0f}", row_style)
            rows.append([icon, amount_text, value_text])

        tbl = RLTable(rows, colWidths=[18, None, 60], hAlign='LEFT')
        tbl.setStyle(RLTableStyle([
            ('VALIGN',   (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING',  (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING',   (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING',(0, 0), (-1, -1), 1),
            ('SPAN',     (0, 0), (-1, 0)),   # total header spans all cols
            ('SPAN',     (0, 1), (0, 1)) if cash_gained > 0 else ('NOP', (0,0),(0,0)),
        ]))
        return [tbl]

    async def _generate_war_report_file(self, wars_data: List[dict], resource_prices: dict, pov_ids: set, team1_type: str, team1: str, team2_type: Optional[str], team2: Optional[str], team1_id_set: set, team2_id_set: Optional[set] = None, after_datetime: Optional[datetime] = None) -> Optional[discord.File]:
        """Generate a PDF file with a detailed list of wars and their costs."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, rightMargin=inch/4, leftMargin=inch/4, topMargin=inch/2, bottomMargin=inch/2)
        
        styles = getSampleStyleSheet()
        title_style = styles['h1']
        title_style.alignment = TA_CENTER
        h2_style = styles['h2']
        body_style = styles['BodyText']
        link_style = ParagraphStyle(
            'NationLink',
            parent=body_style,
            textColor=colors.HexColor('#1155CC'),
        )
        
        story = [Paragraph("War Report", title_style), Spacer(1, 0.2*inch)]

        # ── Page 1: Full Alliance Breakdown ──────────────────────────────────
        overall_costs = await calculate_war_costs(wars_data, resource_prices, team1_id_set, team2_id_set)
        t1_name = team1 if team1 else "Team 1"
        t2_name = team2 if team2 else "Team 2"

        # Header row
        header_style = ParagraphStyle('ColHeader', parent=body_style,
                                      fontName='Helvetica-Bold', fontSize=11, alignment=TA_CENTER)
        sub_style    = ParagraphStyle('SubHead',   parent=body_style,
                                      fontName='Helvetica-Bold', fontSize=9)
        val_style    = ParagraphStyle('Val',       parent=body_style, fontSize=9)

        def _section(label: str) -> Paragraph:
            return Paragraph(f'<b>{label}</b>', sub_style)

        def _val(text: str) -> Paragraph:
            return Paragraph(text, val_style)

        # ── Overview totals (3 columns: label | team1 | team2) ───────────────
        col_w = doc.width / 3.0
        overview_rows = [
            [Paragraph('', header_style), Paragraph(t1_name, header_style), Paragraph(t2_name, header_style)],
            [_section('Wars Analysed'), _val(str(len(wars_data))), _val(str(len(wars_data)))],
            [_section('Gross Cost'),
             _val(f"${overall_costs['team1']['gross']:,.0f}"),
             _val(f"${overall_costs['team2']['gross']:,.0f}")],
            [_section('Net Cost'),
             _val(f"${overall_costs['team1']['net']:,.0f}"),
             _val(f"${overall_costs['team2']['net']:,.0f}")],
        ]
        ov_tbl = Table(overview_rows, colWidths=[col_w] * 3)
        ov_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0), colors.HexColor('#2C3E50')),
            ('TEXTCOLOR',     (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN',         (0, 1), (0, -1), 'LEFT'),
            ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('TOPPADDING',    (0, 0), (-1, 0), 10),
            ('BACKGROUND',    (0, 1), (-1, -1), colors.HexColor('#ECF0F1')),
            ('GRID',          (0, 0), (-1, -1), 0.5, colors.HexColor('#BDC3C7')),
        ]))
        story.append(ov_tbl)
        story.append(Spacer(1, 0.15*inch))

        # ── Side-by-side detail table ─────────────────────────────────────────
        # Build each section for both sides at the same time so rows always align.
        CONVENTIONAL = ['soldiers', 'tanks', 'aircraft', 'ships']
        BOMBS        = ['missiles', 'nukes']

        def _unit_cell(side: str) -> Paragraph:
            c = overall_costs[side]
            lines = []
            for u in CONVENTIONAL:
                if u in c['units']:
                    d = c['units'][u]
                    lines.append(f"{d['lost']:,.0f} {u.title()} — ${d['cost']:,.0f}")
            if lines:
                return Paragraph('<b>Unit Losses</b><br/>' + '<br/>'.join(lines), val_style)
            return None

        def _bomb_cell(side: str) -> Paragraph:
            c = overall_costs[side]
            lines = []
            for u in BOMBS:
                if u in c['units']:
                    d = c['units'][u]
                    label = 'Missiles' if u == 'missiles' else 'Nukes'
                    lines.append(f"{d['lost']:,.0f} {label} — ${d['cost']:,.0f}")
            if lines:
                return Paragraph('<b>Bombs Used</b><br/>' + '<br/>'.join(lines), val_style)
            return None

        def _con_cell(side: str):
            flows = self._build_consumption_flowables(side, overall_costs, resource_prices, body_style)
            return flows[0] if flows else None

        def _infra_cell(side: str) -> Paragraph:
            c = overall_costs[side]
            if c['infra_lost_value'] > 0:
                return Paragraph(f'<b>Infrastructure</b><br/>{c["infra_lost_levels"]:,.0f} levels = ${c["infra_lost_value"]:,.0f}', val_style)
            return None

        def _money_cell(side: str) -> Paragraph:
            c = overall_costs[side]
            if c.get('money_destroyed', 0) > 0:
                return Paragraph(f'<b>Money Destroyed</b><br/>${c["money_destroyed"]:,.0f}', val_style)
            return None

        def _imp_cell(side: str) -> Paragraph:
            c = overall_costs[side]
            if c['improvements_lost'] > 0:
                lines = [f"${c['improvements_lost']:,.0f} total"]
                for imp, cnt in sorted(c['improvements_destroyed'].items()):
                    lines.append(f"  {cnt}× {imp.replace('_',' ').title()}")
                return Paragraph('<b>Improvements</b><br/>' + '<br/>'.join(lines), val_style)
            return None

        def _loot_cell(side: str):
            flows = self._build_loot_flowables(side, overall_costs, resource_prices, body_style)
            return flows[0] if flows else None

        def _gross_net_cell(side: str) -> Paragraph:
            c = overall_costs[side]
            return Paragraph(f'<b>Gross:</b> ${c["gross"]:,.0f}<br/><b>Net:</b> ${c["net"]:,.0f}', val_style)

        empty = Paragraph('', val_style)

        # Each section: only include the row if at least one side has data
        sections = [
            (_unit_cell, True),   # always include units row
            (_bomb_cell, False),
            (_con_cell,  False),
            (_infra_cell, False),
            (_money_cell, False),
            (_imp_cell,  False),
            (_loot_cell, False),
            (_gross_net_cell, True),  # always include gross/net
        ]

        detail_data = [[Paragraph(t1_name, header_style), Paragraph(t2_name, header_style)]]
        for fn, always in sections:
            c1 = fn('team1')
            c2 = fn('team2')
            if always or c1 or c2:
                detail_data.append([c1 or empty, c2 or empty])

        detail_tbl = Table(detail_data, colWidths=[doc.width/2.0]*2)
        detail_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0), colors.HexColor('#2C3E50')),
            ('TEXTCOLOR',     (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN',         (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING',    (0, 0), (-1, 0), 8),
            ('VALIGN',        (0, 1), (-1, -1), 'TOP'),
            ('GRID',          (0, 0), (-1, -1), 0.5, colors.HexColor('#BDC3C7')),
            ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, colors.HexColor('#F8F9FA')]),
        ]))
        story.append(detail_tbl)
        story.append(Spacer(1, 0.15*inch))

        story.append(PageBreak())

        # Detailed war breakdowns
        for war in wars_data:
            war_id = war.get('id')
            att_nation_name = war.get('att_nation_name') or (war.get('attacker') or {}).get('nation_name') or (f"Nation #{war.get('att_id')}" if war.get('att_id') else 'Unknown')
            def_nation_name = war.get('def_nation_name') or (war.get('defender') or {}).get('nation_name') or (f"Nation #{war.get('def_id')}" if war.get('def_id') else 'Unknown')
            att_nation_id   = war.get('att_id')
            def_nation_id   = war.get('def_id')
            att_alliance_name = war.get('att_alliance_name') or (war.get('attacker') or {}).get('alliance_name') or ''
            def_alliance_name = war.get('def_alliance_name') or (war.get('defender') or {}).get('alliance_name') or ''

            # Build clickable nation links using ReportLab's <link href="..."> tag
            pnw_base = "https://politicsandwar.com/nation/id="
            if att_nation_id:
                att_link_text = f'<link href="{pnw_base}{att_nation_id}">{att_nation_name}</link>'
                if att_alliance_name:
                    att_link_text += f' ({att_alliance_name})'
                att_para = Paragraph(f'<b>Attacker:</b> {att_link_text}', link_style)
            else:
                att_para = Paragraph(f'<b>Attacker:</b> {att_nation_name}' + (f' ({att_alliance_name})' if att_alliance_name else ''), body_style)

            if def_nation_id:
                def_link_text = f'<link href="{pnw_base}{def_nation_id}">{def_nation_name}</link>'
                if def_alliance_name:
                    def_link_text += f' ({def_alliance_name})'
                def_para = Paragraph(f'<b>Defender:</b> {def_link_text}', link_style)
            else:
                def_para = Paragraph(f'<b>Defender:</b> {def_nation_name}' + (f' ({def_alliance_name})' if def_alliance_name else ''), body_style)

            story.append(Paragraph(f"War ID: {war_id}", h2_style))

            winner_id = war.get('winner_id')
            winner_name = "Ongoing"
            if winner_id:
                if str(winner_id) == str(att_nation_id):
                    winner_name = att_nation_name
                elif str(winner_id) == str(def_nation_id):
                    winner_name = def_nation_name
                else:
                    winner_name = f"ID: {winner_id}"

            war_info_data = [
                [att_para],
                [def_para],
                [Paragraph(f"<b>Reason:</b> {war.get('reason', 'N/A')}", body_style)],
                [Paragraph(f"<b>Winner:</b> {winner_name}", body_style)],
            ]
            war_info_table = Table(war_info_data, colWidths=[doc.width])
            war_info_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
            story.append(war_info_table)
            story.append(Spacer(1, 0.1*inch))

            # Column headers with clickable nation links
            pnw_base = "https://politicsandwar.com/nation/id="
            str_t1 = {str(i) for i in team1_id_set}
            att_is_team1 = str(war.get('att_alliance_id','')) in str_t1 or str(war.get('att_id','')) in str_t1

            def _nation_header(nation_name, nation_id, alliance_name):
                suffix = f' ({alliance_name})' if alliance_name else ''
                if nation_id:
                    return Paragraph(f'<link href="{pnw_base}{nation_id}">{nation_name}</link>{suffix}', link_style)
                return Paragraph(f'{nation_name}{suffix}', body_style)

            if att_is_team1:
                t1_header = _nation_header(att_nation_name, att_nation_id, att_alliance_name)
                t2_header = _nation_header(def_nation_name, def_nation_id, def_alliance_name)
            else:
                t1_header = _nation_header(def_nation_name, def_nation_id, def_alliance_name)
                t2_header = _nation_header(att_nation_name, att_nation_id, att_alliance_name)

            cost_data = [[t1_header, t2_header]]

            # Detailed Costs for this war
            single_war_costs = await calculate_single_war_costs(war, resource_prices, team1_id_set, team2_id_set)

            # Units — text for unit losses/bombs, image table for consumption
            from reportlab.platypus import KeepTogether

            def _build_military_cell(side):
                units_text = self._get_category_details_for_pdf(side, "Military", single_war_costs, resource_prices)
                con_flows = self._build_consumption_flowables(side, single_war_costs, resource_prices, body_style)
                parts = [Paragraph(units_text, body_style)] if units_text.strip() else []
                parts.extend(con_flows)
                return parts if parts else [Paragraph("No costs", body_style)]

            att_mil = _build_military_cell("team1")
            def_mil = _build_military_cell("team2")
            cost_data.append([att_mil, def_mil])
            
            # Destruction
            att_dest = self._get_category_details_for_pdf("team1", "Destruction", single_war_costs, resource_prices)
            def_dest = self._get_category_details_for_pdf("team2", "Destruction", single_war_costs, resource_prices)
            cost_data.append([Paragraph(att_dest, body_style), Paragraph(def_dest, body_style)])
            
            # Loot — use image flowables for resource icons
            att_loot_flows = self._build_loot_flowables("team1", single_war_costs, resource_prices, body_style)
            def_loot_flows = self._build_loot_flowables("team2", single_war_costs, resource_prices, body_style)
            att_loot_cell = att_loot_flows[0] if att_loot_flows else Paragraph("No loot", body_style)
            def_loot_cell = def_loot_flows[0] if def_loot_flows else Paragraph("No loot", body_style)
            cost_data.append([att_loot_cell, def_loot_cell])

            # Net
            att_gross = f"<b>Gross: ${single_war_costs['team1']['gross']:,.0f}</b>"
            def_gross = f"<b>Gross: ${single_war_costs['team2']['gross']:,.0f}</b>"
            att_net = f"<b>Net: ${single_war_costs['team1']['net']:,.0f}</b>"
            def_net = f"<b>Net: ${single_war_costs['team2']['net']:,.0f}</b>"
            cost_data.append([Paragraph(f"{att_gross}<br/>{att_net}", body_style), Paragraph(f"{def_gross}<br/>{def_net}", body_style)])

            cost_table = Table(cost_data, colWidths=[doc.width/2.0 - 5]*2, spaceAfter=20)
            cost_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.lightblue),
                ('TEXTCOLOR', (0,0), (-1,0), colors.black),
                ('ALIGN', (0,0), (-1,0), 'CENTER'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('GRID', (0,0), (-1,-1), 1, colors.black),
                ('VALIGN', (0,1), (-1,-1), 'TOP'),
            ]))
            story.append(cost_table)
            story.append(PageBreak())

        doc.build(story)
        buffer.seek(0)

        # Build a descriptive filename: team1_vs_team2_MM-DD-YY_to_MM-DD-YY.pdf
        def _safe(name: str) -> str:
            """Strip characters that are invalid in filenames."""
            import re as _re
            return _re.sub(r'[^\w\-]', '_', (name or 'Unknown').strip())[:40]

        now = datetime.now(timezone.utc)
        start_dt = after_datetime if after_datetime else now
        date_range = f"{start_dt.strftime('%m-%d-%y')}_to_{now.strftime('%m-%d-%y')}"
        t1_safe = _safe(team1)
        t2_safe = _safe(team2) if team2 else "All"
        filename = f"{t1_safe}_vs_{t2_safe}_{date_range}.pdf"

        return discord.File(buffer, filename=filename)

    def draw_rounded_rectangle(self, draw, xy, radius, fill=None, outline=None):
        x1, y1, x2, y2 = xy
        draw.rectangle(
            (x1 + radius, y1, x2 - radius, y2),
            fill=fill,
            outline=outline
        )
        draw.rectangle(
            (x1, y1 + radius, x2, y2 - radius),
            fill=fill,
            outline=outline
        )
        draw.pieslice(
            (x1, y1, x1 + radius * 2, y1 + radius * 2),
            180, 270, fill=fill, outline=outline
        )
        draw.pieslice(
            (x2 - radius * 2, y1, x2, y1 + radius * 2),
            270, 360, fill=fill, outline=outline
        )
        draw.pieslice(
            (x1, y2 - radius * 2, x1 + radius * 2, y2),
            90, 180, fill=fill, outline=outline
        )
        draw.pieslice(
            (x2 - radius * 2, y2 - radius * 2, x2, y2),
            0, 90, fill=fill, outline=outline
        )

    async def _generate_war_cost_graph(self, costs: dict, resource_prices: dict) -> io.BytesIO:
        """Generate pie charts for war costs with rich labels."""
        try:
            # --- Data Preparation ---
            cost_categories = {
                "Units": "#3498db", "Bombs": "#e74c3c", "Consumption": "#2ecc71", "Infrastructure": "#f1c40f",
                "Improvements": "#e67e22", "Loot Lost": "#9b59b6", "Money Destroyed": "#c0392b"
            }

            CONVENTIONAL = {"soldiers", "tanks", "aircraft", "ships"}
            BOMBS = {"missiles", "nukes"}

            def _split_units(side_costs):
                conventional = sum(d['cost'] for u, d in side_costs['units'].items() if u in CONVENTIONAL)
                bombs = sum(d['cost'] for u, d in side_costs['units'].items() if u in BOMBS)
                return conventional, bombs

            t1_conventional, t1_bombs = _split_units(costs['team1'])
            t2_conventional, t2_bombs = _split_units(costs['team2'])

            team1_gross_costs = {
                "Units": t1_conventional,
                "Bombs": t1_bombs,
                "Consumption": (costs['team1']['consumption']['munitions'] * resource_prices['buy'].get("munitions", 0) +
                                costs['team1']['consumption']['gasoline'] * resource_prices['buy'].get("gasoline", 0)),
                "Infrastructure": costs['team1']['infra_lost_value'],
                "Improvements": costs['team1']['improvements_lost'],
                "Loot Lost": costs['team1']['loot_lost'] + sum(costs['team1']['resource_loot_lost'].values()),
                "Money Destroyed": costs['team1'].get('money_destroyed', 0)
            }

            team2_gross_costs = {
                "Units": t2_conventional,
                "Bombs": t2_bombs,
                "Consumption": (costs['team2']['consumption']['munitions'] * resource_prices['buy'].get("munitions", 0) +
                                costs['team2']['consumption']['gasoline'] * resource_prices['buy'].get("gasoline", 0)),
                "Infrastructure": costs['team2']['infra_lost_value'],
                "Improvements": costs['team2']['improvements_lost'],
                "Loot Lost": costs['team2']['loot_lost'] + sum(costs['team2']['resource_loot_lost'].values()),
                "Money Destroyed": costs['team2'].get('money_destroyed', 0)
            }

            team1_gross_costs = {k: v for k, v in team1_gross_costs.items() if v > 0}
            team2_gross_costs = {k: v for k, v in team2_gross_costs.items() if v > 0}

            # --- Image Setup ---
            width, height = 1200, 700
            img = Image.new('RGBA', (width, height), (255, 255, 255, 0))  # Transparent background
            draw = ImageDraw.Draw(img)
            try:
                title_font = ImageFont.truetype("arialbd.ttf", 20)
                label_font = ImageFont.truetype("arial.ttf", 16)
                small_label_font = ImageFont.truetype("arial.ttf", 14)
            except IOError:
                title_font, label_font, small_label_font = [ImageFont.load_default()] * 3

            # --- Helper Function for Drawing Pie ---
            def draw_pie(pie_box, data, title, draw_obj, is_attacker=True):
                total_cost = sum(data.values())
                
                if not data:
                    draw_obj.ellipse(pie_box, fill='#dcdcdc', outline='#b0b0b0')
                    draw_obj.text((pie_box[0] + (pie_box[2]-pie_box[0])/2, pie_box[1] + (pie_box[3]-pie_box[1])/2), "No Costs", fill='black', font=label_font, anchor="mm")
                    return

                start_angle = -90
                for category, value in data.items():
                    angle = (value / total_cost) * 360 if total_cost > 0 else 0
                    end_angle = start_angle + angle

                    mid_angle_rad = math.radians((start_angle + end_angle) / 2)
                    cx, cy = (pie_box[0] + pie_box[2]) / 2, (pie_box[1] + pie_box[3]) / 2

                    # Explode small slices
                    explode_dist = 10 if angle < 15 else 0
                    offset_x = int(explode_dist * math.cos(mid_angle_rad))
                    offset_y = int(explode_dist * math.sin(mid_angle_rad))
                    exploded_box = [pie_box[0] + offset_x, pie_box[1] + offset_y, pie_box[2] + offset_x, pie_box[3] + offset_y]
                    draw_obj.pieslice(exploded_box, start_angle, end_angle, fill=cost_categories[category], outline='white', width=2)

                    start_angle = end_angle

            # --- Draw Charts ---
            draw_pie((50, 100, 450, 500), team1_gross_costs, "Team 1 Gross Costs", draw, is_attacker=True)
            draw_pie((750, 100, 1150, 500), team2_gross_costs, "Team 2 Gross Costs", draw, is_attacker=False)

            # --- Draw Tighter, Rounded Legend ---
            legend_padding = 20
            legend_radius = 15
            content_width = 1050  # Estimated content width
            legend_height = 120  # Estimated height
            
            # Center the legend area
            legend_x0 = (width - content_width) / 2
            legend_y0 = 530
            legend_x1 = legend_x0 + content_width
            legend_y1 = legend_y0 + legend_height
            legend_area = (legend_x0, legend_y0, legend_x1, legend_y1)

            # Draw rounded rectangle
            self.draw_rounded_rectangle(draw, legend_area, fill="#2c3e50", radius=legend_radius)

            # --- Attacker and Defender Cost/Net ---
            team1_total_cost = sum(team1_gross_costs.values())
            team2_total_cost = sum(team2_gross_costs.values())
            team1_net_cost = costs['team1']['net']
            team2_net_cost = costs['team2']['net']

            team1_cost_text = f"Team 1 Cost: ${team1_total_cost:,.0f}"
            team1_net_text = f"Team 1 Net: ${team1_net_cost:,.0f}"
            team2_cost_text = f"Team 2 Cost: ${team2_total_cost:,.0f}"
            team2_net_text = f"Team 2 Net: ${team2_net_cost:,.0f}"

            # Position text within the rounded rectangle
            text_y_start = legend_y0 + legend_padding
            text_x_padding = 40
            
            draw.text((legend_x0 + text_x_padding, text_y_start), team1_cost_text, font=label_font, fill="#ecf0f1")
            draw.text((legend_x0 + text_x_padding, text_y_start + 30), team1_net_text, font=label_font, fill="#ecf0f1")
            
            def_text_x = legend_x1 - text_x_padding - draw.textlength(team2_cost_text, font=label_font)
            draw.text((def_text_x, text_y_start), team2_cost_text, font=label_font, fill="#ecf0f1")
            def_net_text_x = legend_x1 - text_x_padding - draw.textlength(team2_net_text, font=label_font)
            draw.text((def_net_text_x, text_y_start + 30), team2_net_text, font=label_font, fill="#ecf0f1")

            # --- Horizontal Color Legend (Centered) ---
            legend_y = legend_y0 + 80
            box_size = 20
            
            # Calculate total width of the color legend to center it
            total_legend_width = 0
            legend_items = list(cost_categories.items())
            item_spacing = 30
            for category, color in legend_items:
                total_legend_width += box_size + 10 + draw.textlength(category, font=label_font) + item_spacing

            legend_x_start = legend_x0 + (content_width - total_legend_width) / 2 + 15

            # Draw the centered color legend
            current_x = legend_x_start
            for category, color in legend_items:
                # Draw color box
                draw.rectangle([current_x, legend_y, current_x + box_size, legend_y + box_size], fill=color, outline="#ecf0f1", width=1)
                
                # Draw text
                text_x = current_x + box_size + 10
                draw.text((text_x, legend_y), category, fill="#ecf0f1", font=label_font)
                
                # Move to the next item
                current_x = text_x + draw.textlength(category, font=label_font) + item_spacing

            # --- Save to Buffer ---
            img_buffer = io.BytesIO()
            img.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            return img_buffer


        except Exception as e:
            logging.error(f"Error generating war cost graph: {e}", exc_info=True)
            return None

class WarCostView(discord.ui.View):
    """A view for paginating war cost analysis."""
    
    def __init__(self, embeds: dict, graph_file: Optional[discord.File] = None, war_report_file: Optional[discord.File] = None):
        super().__init__(timeout=300)
        self.embeds = embeds
        self.current_page_name = 'summary'
        self.message = None
        
        self._graph_image_data = None
        if graph_file and hasattr(graph_file, 'fp') and hasattr(graph_file.fp, 'getvalue'):
            self._graph_image_data = graph_file.fp.getvalue()
        
        self._war_report_data = None
        self._war_report_filename = "war_report.pdf"
        if war_report_file and hasattr(war_report_file, 'fp') and hasattr(war_report_file.fp, 'getvalue'):
            self._war_report_data = war_report_file.fp.getvalue()
            self._war_report_filename = war_report_file.filename or "war_report.pdf"

        if not self._war_report_data:
            self.remove_item(self.breakdown_button)

        self.update_buttons()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            await self.message.edit(view=self)
    
    def update_buttons(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                # Button labels are title-cased, so we match
                item.disabled = (item.label.lower() == self.current_page_name)

    async def show_page(self, interaction: discord.Interaction, page_name: str):
        if self.current_page_name != page_name:
            self.current_page_name = page_name
            self.update_buttons()
            
            attachments = []
            embed = self.embeds[page_name]
            
            if page_name == 'summary':
                if self._graph_image_data:
                    # Recreate the Discord file from cached image data
                    import io
                    graph_buffer = io.BytesIO(self._graph_image_data)
                    graph_file = discord.File(graph_buffer, filename="war_cost_graph.png")
                    attachments.append(graph_file)

            await interaction.response.edit_message(embed=embed, view=self, attachments=attachments)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Summary", style=discord.ButtonStyle.secondary, emoji=get_animated_partial("bars"))
    async def summary_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show_page(interaction, 'summary')

    @discord.ui.button(label="Military", style=discord.ButtonStyle.primary, emoji=get_animated_partial("kill"))
    async def military_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show_page(interaction, 'military')

    @discord.ui.button(label="Destruction", style=discord.ButtonStyle.danger, emoji=get_animated_partial("bombq"))
    async def destruction_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show_page(interaction, 'destruction')

    @discord.ui.button(label="Loot", style=discord.ButtonStyle.success, emoji=get_animated_partial("Mimic"))
    async def loot_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show_page(interaction, 'loot')

    @discord.ui.button(label="Breakdown PDF", style=discord.ButtonStyle.secondary, emoji=get_animated_partial("pdf"))
    async def breakdown_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._war_report_data:
            import io
            war_report_buffer = io.BytesIO(self._war_report_data)
            war_report_file = discord.File(war_report_buffer, filename=self._war_report_filename)
            await interaction.response.send_message(file=war_report_file, ephemeral=True)
        else:
            await interaction.response.send_message("No breakdown available.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Wars(bot))
