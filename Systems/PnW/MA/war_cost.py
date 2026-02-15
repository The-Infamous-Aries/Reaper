import discord
from discord import app_commands
from discord.ext import commands

import re
import logging
import asyncio
from typing import Any, Dict, List, Optional, Tuple, Set
from io import BytesIO

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config import HOME_ALLIANCE_ID

from Systems.PnW.Util.query import create_query_instance
from Systems.Functions import emoji as emoji_mod

UserDataManager = None

 

# Optional image generation support (same pattern as compare.py)
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except Exception:
    Image = None
    ImageDraw = None
    ImageFont = None
    PIL_AVAILABLE = False


class WarsCostCog(commands.Cog):
    """Provides a /wars slash command to summarize war costs between two parties (Attackers vs Defenders)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.query_instance = None
        try:
            if create_query_instance:
                self.query_instance = create_query_instance(logger=self.logger)
        except Exception as e:
            self.logger.warning(f"war_cost.py: Failed to init query instance: {e}")
        # In-memory payload cache (1 hour TTL)
        self._payload_cache: Dict[str, Any] = {}
        self._payload_expiry: Dict[str, float] = {}
        self._payload_ttl_seconds: float = 3600.0
        # No external icon URLs; we will use server custom emojis if available
        self._resource_emojis = {}

    # ---------------------------
    # Utilities
    # ---------------------------
    def _build_emoji_map_for_guild(self, guild: Optional[discord.Guild]) -> Dict[str, str]:
        return emoji_mod.resource_codes_for(getattr(guild, "id", None)) if guild else {}
    @staticmethod
    def _parse_alliance_identifier(text: str) -> Tuple[Optional[int], Optional[str]]:
        """Parse user input for alliance ID from numeric string or PnW link.
        Returns (alliance_id, resolved_name_if_known).
        """
        if not text:
            return (None, None)
        s = (text or '').strip()

        # Link formats: https://politicsandwar.com/alliance/id=12345 or id=12345
        m = re.search(r"id\s*=\s*(\d+)", s)
        if m:
            try:
                return (int(m.group(1)), None)
            except Exception:
                pass

        # Pure numeric
        if s.isdigit():
            try:
                return (int(s), None)
            except Exception:
                pass

        # No local bloc mapping; rely on API resolution

        return (None, s)

    async def _resolve_alliance_id_from_api(self, name_or_acr: str) -> Tuple[Optional[int], Optional[str]]:
        """Resolve alliance id by name or acronym via query system."""
        try:
            q = self.query_instance
            if not q:
                return (None, None)
            item = await q.resolve_alliance(name_or_acr)
            if item:
                try:
                    aid = int(item.get('id')) if item.get('id') else None
                except Exception:
                    aid = None
                nm = item.get('name') or name_or_acr
                return (aid, nm)
            return (None, None)
        except Exception as e:
            try:
                self.logger.warning(f"_resolve_alliance_id_from_api: failed to resolve '{name_or_acr}': {e}")
            except Exception:
                pass
            return (None, None)

    async def _resolve_targets(self, text: str) -> List[Tuple[Optional[int], Optional[str]]]:
        """Resolve a comma-separated list of alliance identifiers to IDs via parsing, batched API lookups, and fallbacks."""
        out: List[Tuple[Optional[int], Optional[str]]] = []
        if not text:
            return out
        parts = [p.strip() for p in str(text).split(',') if p.strip()]
        to_batch: List[str] = []

        # First pass: numeric/link/known mapping
        for part in parts:
            aid, name = self._parse_alliance_identifier(part)
            if isinstance(aid, int) and aid > 0:
                out.append((aid, name or f"Alliance {aid}"))
            else:
                to_batch.append(name or part)

        # Second pass: batched alliances(name: ...) query
        batched: Dict[str, Optional[Dict[str, Any]]] = {}
        if to_batch and getattr(self, 'query_instance', None):
            try:
                batched = await self.query_instance.resolve_alliance_names_batched(to_batch)
            except Exception as e:
                try:
                    self.logger.warning(f"_resolve_targets: batched resolve failed: {e}")
                except Exception:
                    pass
                batched = {}

        # Final pass: use batched results, fallback per-item resolution
        for name in to_batch:
            item = (batched or {}).get(name)
            if item and item.get('id'):
                try:
                    rid = int(item.get('id'))
                except Exception:
                    rid = None
                if isinstance(rid, int) and rid > 0:
                    rname = item.get('name') or name
                    out.append((rid, rname))
                    continue

            ra_id, ra_name = await self._resolve_alliance_id_from_api(name)
            if isinstance(ra_id, int) and ra_id > 0:
                out.append((ra_id, ra_name or name))
            else:
                out.append((None, name))

        return out

    def _abbr(self, name: str) -> str:
        """Derive a short abbreviation for an alliance name."""
        KNOWN = {"Death Before Dishonor": "DB4D", "DB4D": "DB4D"}
        if not name:
            return "ALL"
        if name in KNOWN:
            return KNOWN[name]
        parts = re.split(r"[^A-Za-z0-9]+", name)
        initials = ''.join([p[0] for p in parts if p])[:3]
        if initials:
            return initials.upper()
        return name[:3].upper()

    async def target_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        try:
            raw = (current or '')
            parts = [p.strip() for p in raw.split(',')]
            token = parts[-1] if parts else ''
            prefix = ''
            if len(parts) > 1:
                prefix = ', '.join([p for p in parts[:-1] if p])
                if prefix:
                    prefix += ', '

            choices: List[app_commands.Choice[str]] = []

            # Numeric or link on the current token: suggest parsed ID
            aid, _ = self._parse_alliance_identifier(token)
            if isinstance(aid, int) and aid > 0:
                full_val = f"{prefix}{aid}" if prefix else str(aid)
                choices.append(app_commands.Choice(name=f"Alliance ID {aid}", value=full_val))

            # REST-backed alliance search by token
            try:
                q = getattr(self, 'query_instance', None)
                if q:
                    results = await q.search_alliances(token, max_results=max(0, 25 - len(choices)))
                    for a in results or []:
                        rid = str(a.get('id') or '')
                        name = (a.get('name') or '').strip()
                        acr = (a.get('acronym') or '').strip()
                        disp = (f"{name} ({acr})" if (name and acr) else (name or rid)).strip()
                        if rid:
                            full_val = f"{prefix}{rid}" if prefix else rid
                            choices.append(app_commands.Choice(name=disp[:100], value=full_val))
                        if len(choices) >= 25:
                            break
            except Exception:
                pass

            return choices[:25]
        except Exception:
            return []

    # ---------------------------
    # Core aggregation utilities
    # ---------------------------
    def _aggregate_war_costs_by_party_sync(self, wars: List[Dict[str, Any]], home_ids: Set[int], away_ids: Set[int]) -> Dict[str, float]:
        """Aggregate numeric cost fields across wars, attributing to Home/Away parties.

        Home/Away are explicit party sets (attackers vs defenders input), not initial war sides.
        Returns keys like 'home_gas_used', 'away_gas_used', etc. Missing fields default to 0.
        """
        fields = [
            'gas_used', 'mun_used', 'alum_used', 'steel_used',
            'infra_destroyed', 'infra_destroyed_value', 'money_looted',
            'soldiers_lost', 'tanks_lost', 'aircraft_lost', 'ships_lost',
            'missiles_lost', 'nukes_lost',
            'gas_looted', 'mun_looted', 'alum_looted', 'steel_looted', 'food_looted',
            'coal_looted', 'oil_looted', 'uran_looted', 'iron_looted', 'baux_looted', 'lead_looted'
        ]
        totals: Dict[str, float] = {}
        for prefix in ('home', 'away'):
            for f in fields:
                totals[f"{prefix}_{f}"] = 0.0

        for w in wars or []:
            attacks = w.get('attacks') or []
            use_attacks = isinstance(attacks, list) and len(attacks) > 0

            try:
                war_att_id = int(w.get('att_id') or w.get('attid') or 0)
            except Exception:
                war_att_id = 0
            try:
                war_def_id = int(w.get('def_id') or w.get('defid') or 0)
            except Exception:
                war_def_id = 0
            try:
                war_att_alliance_id = int(w.get('att_alliance_id') or (w.get('attacker') or {}).get('alliance_id') or 0)
            except Exception:
                war_att_alliance_id = 0
            try:
                war_def_alliance_id = int(w.get('def_alliance_id') or (w.get('defender') or {}).get('alliance_id') or 0)
            except Exception:
                war_def_alliance_id = 0

            if use_attacks:
                for a in attacks:
                    try:
                        atk_id = int(a.get('att_id') or a.get('attid') or 0)
                    except Exception:
                        atk_id = 0
                    if atk_id and war_att_id and atk_id == war_att_id:
                        atk_alliance = war_att_alliance_id
                        def_alliance = war_def_alliance_id
                    elif atk_id and war_def_id and atk_id == war_def_id:
                        atk_alliance = war_def_alliance_id
                        def_alliance = war_att_alliance_id
                    else:
                        atk_alliance = war_att_alliance_id
                        def_alliance = war_def_alliance_id
                    atk_party = 'home' if atk_alliance in home_ids else ('away' if atk_alliance in away_ids else None)
                    def_party = 'home' if def_alliance in home_ids else ('away' if def_alliance in away_ids else None)
                    att_gas = float(a.get('att_gas_used', 0) or 0)
                    def_gas = float(a.get('def_gas_used', 0) or 0)
                    att_mun = float(a.get('att_mun_used', 0) or 0)
                    def_mun = float(a.get('def_mun_used', 0) or 0)
                    infra_lvl = float((a.get('infra_destroyed') if a.get('infra_destroyed') is not None else a.get('infradestroyed')) or 0)
                    infra_val = float(a.get('infra_destroyed_value', 0) or 0)
                    money_loot = float(
                        (a.get('money_stolen') if a.get('money_stolen') is not None else a.get('moneystolen'))
                        or a.get('money_looted') or 0
                    )
                    att_soldiers_lost = float(a.get('att_soldiers_lost', 0) or 0)
                    def_soldiers_lost = float(a.get('def_soldiers_lost', 0) or 0)
                    att_tanks_lost = float(a.get('att_tanks_lost', 0) or 0)
                    def_tanks_lost = float(a.get('def_tanks_lost', 0) or 0)
                    att_aircraft_lost = float(a.get('att_aircraft_lost', 0) or 0)
                    def_aircraft_lost = float(a.get('def_aircraft_lost', 0) or 0)
                    att_ships_lost = float(a.get('att_ships_lost', 0) or 0)
                    def_ships_lost = float(a.get('def_ships_lost', 0) or 0)
                    att_missiles_lost = float(a.get('att_missiles_lost', 0) or 0)
                    def_missiles_lost = float(a.get('def_missiles_lost', 0) or 0)
                    att_nukes_lost = float(a.get('att_nukes_lost', 0) or 0)
                    def_nukes_lost = float(a.get('def_nukes_lost', 0) or 0)
                    loot_gas = float(a.get('gasoline_looted', 0) or 0)
                    loot_mun = float(a.get('munitions_looted', 0) or 0)
                    loot_alum = float(a.get('aluminum_looted', 0) or 0)
                    loot_steel = float(a.get('steel_looted', 0) or 0)
                    loot_food = float(a.get('food_looted', 0) or 0)
                    loot_coal = float(a.get('coal_looted', 0) or 0)
                    loot_oil = float(a.get('oil_looted', 0) or 0)
                    loot_uran = float(a.get('uranium_looted', 0) or 0)
                    loot_iron = float(a.get('iron_looted', 0) or 0)
                    loot_baux = float(a.get('bauxite_looted', 0) or 0)
                    loot_lead = float(a.get('lead_looted', 0) or 0)
                    if atk_party:
                        totals[f"{atk_party}_gas_used"] += att_gas
                        totals[f"{atk_party}_mun_used"] += att_mun
                        totals[f"{atk_party}_money_looted"] += money_loot
                        totals[f"{atk_party}_gas_looted"] += loot_gas
                        totals[f"{atk_party}_mun_looted"] += loot_mun
                        totals[f"{atk_party}_alum_looted"] += loot_alum
                        totals[f"{atk_party}_steel_looted"] += loot_steel
                        totals[f"{atk_party}_food_looted"] += loot_food
                        totals[f"{atk_party}_coal_looted"] += loot_coal
                        totals[f"{atk_party}_oil_looted"] += loot_oil
                        totals[f"{atk_party}_uran_looted"] += loot_uran
                        totals[f"{atk_party}_iron_looted"] += loot_iron
                        totals[f"{atk_party}_baux_looted"] += loot_baux
                        totals[f"{atk_party}_lead_looted"] += loot_lead
                        totals[f"{atk_party}_soldiers_lost"] += att_soldiers_lost
                        totals[f"{atk_party}_tanks_lost"] += att_tanks_lost
                        totals[f"{atk_party}_aircraft_lost"] += att_aircraft_lost
                        totals[f"{atk_party}_ships_lost"] += att_ships_lost
                        totals[f"{atk_party}_missiles_lost"] += att_missiles_lost
                        totals[f"{atk_party}_nukes_lost"] += att_nukes_lost
                    if def_party:
                        totals[f"{def_party}_gas_used"] += def_gas
                        totals[f"{def_party}_mun_used"] += def_mun
                        totals[f"{def_party}_infra_destroyed"] += infra_lvl
                        totals[f"{def_party}_infra_destroyed_value"] += infra_val
                        totals[f"{def_party}_soldiers_lost"] += def_soldiers_lost
                        totals[f"{def_party}_tanks_lost"] += def_tanks_lost
                        totals[f"{def_party}_aircraft_lost"] += def_aircraft_lost
                        totals[f"{def_party}_ships_lost"] += def_ships_lost
                        totals[f"{def_party}_missiles_lost"] += def_missiles_lost
                        totals[f"{def_party}_nukes_lost"] += def_nukes_lost
            else:
                pass

        totals['war_count'] = float(len(wars or []))
        return totals

    async def aggregate_war_costs_by_party(self, wars: List[Dict[str, Any]], home_ids: Set[int], away_ids: Set[int]) -> Dict[str, float]:
        """Async wrapper for aggregating war costs."""
        return await asyncio.to_thread(self._aggregate_war_costs_by_party_sync, wars, home_ids, away_ids)


    def _format_columns(self, left_hdr: str, right_hdr: str, rows: List[Tuple[str, str, str]], fixed_widths: Optional[Tuple[int, int, int]] = None, include_header: bool = True) -> str:
        """Format aligned three columns: Stat | Home | Away, without code blocks.
        Uses consistent column widths across categories when provided via fixed_widths.
        Set include_header=False to omit the header line.
        """
        # Use figure spaces to preserve visual alignment in Discord's proportional font.
        FIGURE_SPACE = "\u2007"  # same width as digits in many fonts
        NBSP = "\u00A0"
        def _fix_spaces(s: str) -> str:
            try:
                # Replace normal spaces with figure spaces to keep alignment tight for numbers
                return (s or "").replace(" ", FIGURE_SPACE)
            except Exception:
                return s
        # Compute widths
        if fixed_widths and isinstance(fixed_widths, tuple) and len(fixed_widths) == 3:
            label_width, left_width, right_width = fixed_widths
        else:
            labels = [lbl for (lbl, _, _) in rows] + ["Stat"]
            lefts = [lv for (_, lv, _) in rows] + [left_hdr]
            rights = [rv for (_, _, rv) in rows] + [right_hdr]

            label_width = max(len(x) for x in labels) if labels else 4
            left_width = max(len(x) for x in lefts) if lefts else 6
            right_width = max(len(x) for x in rights) if rights else 6

            # Caps aligned with compare.py philosophy for mobile friendliness
            label_width = max(6, min(label_width, 10))
            left_width = max(8, min(left_width, 14))
            right_width = max(8, min(right_width, 14))

        sep = " | "
        out: List[str] = []
        header = f"{'Stat':<{label_width}}{sep}{left_hdr:>{left_width}}{sep}{right_hdr:>{right_width}}"
        if include_header:
            out.append(_fix_spaces(header))
        for label, left, right in rows:
            line = f"{label:<{label_width}}{sep}{left:>{left_width}}{sep}{right:>{right_width}}"
            out.append(_fix_spaces(line))
        return "\n".join(out)

    def _make_labeled_columns_block(self, label_header: str, left_header: str, right_header: str, rows: List[Tuple[str, str, str]]) -> str:
        """Render a three-column monospaced block: Label | Left | Right with fixed widths.
        Optimized for mobile with capped widths to reduce wrapping.
        rows: list of (label, left_value, right_value)
        """
        # Compute widths based on actual content
        label_width = max([len(label_header)] + [len(lbl) for lbl, _, _ in rows])
        left_width = max([len(left_header)] + [len(val) for _, val, _ in rows])
        right_width = max([len(right_header)] + [len(val) for _, _, val in rows])

        # Tighter caps to reduce horizontal spacing
        label_width = max(4, min(label_width, 8))
        left_width = max(6, min(left_width, 10))
        right_width = max(6, min(right_width, 10))

        lines: List[str] = []
        sep = "│"  # single thin separator to save space
        lines.append(f"{label_header.ljust(label_width)}{sep}{left_header.rjust(left_width)}{sep}{right_header.rjust(right_width)}")
        for label, left, right in rows:
            lines.append(f"{label.ljust(label_width)}{sep}{left.rjust(left_width)}{sep}{right.rjust(right_width)}")
        return "```" + "\n".join(lines) + "```"

    def _make_unit_columns_block(self, label_header: str, left_header: str, right_header: str, rows: List[Tuple[str, str, str]]) -> str:
        """Render a three-column monospaced block for unit rows with fixed column widths.
        Ensures every line is evenly spaced regardless of number of digits.
        """
        label_width = max(3, len(label_header))
        left_width = max(10, len(left_header))
        right_width = max(10, len(right_header))

        lines: List[str] = []
        lines.append(f"{label_header.ljust(label_width)} | {left_header.rjust(left_width)} | {right_header.rjust(right_width)}")
        for label, left, right in rows:
            lbl = (label + " ") if label else label
            lines.append(f"{lbl.ljust(label_width)} | {left.rjust(left_width)} | {right.rjust(right_width)}")
        return "```" + "\n".join(lines) + "```"

    async def _get_price_map(self) -> Dict[str, float]:
        """Fetch average prices for key resources used in wars."""
        price_map: Dict[str, float] = {}
        try:
            if not self.query_instance:
                return price_map
            vals = await self.query_instance.get_trade_resource_values()
            for item in vals or []:
                r = (item.get('resource') or '').upper()
                try:
                    price_map[r] = float(item.get('average_price') or 0)
                except Exception:
                    price_map[r] = 0.0
        except Exception:
            pass
        return price_map

    def _fmt_money_short(self, x: float) -> str:
        """Format large monetary values into short form using two decimals (e.g., 2.00M, 4.56B)."""
        try:
            val = abs(float(x or 0))
        except Exception:
            val = 0.0
        try:
            if val >= 1_000_000_000_000:
                return f"{val / 1_000_000_000_000:.2f}T"
            if val >= 1_000_000_000:
                return f"{val / 1_000_000_000:.2f}B"
            if val >= 1_000_000:
                return f"{val / 1_000_000:.2f}M"
            if val >= 1_000:
                return f"{val / 1_000:.2f}K"
            # Small values: show integer with commas
            return f"{int(round(val)):,}"
        except Exception:
            return "0"

    # ---------------------------
    # Chart generation helpers (PIL)
    # ---------------------------
    def _get_font(self, size: int = 16) -> Optional[Any]:
        if not PIL_AVAILABLE:
            return None
        try:
            return ImageFont.truetype("C:\\Windows\\Fonts\\seguiemj.ttf", size)
        except Exception:
            try:
                return ImageFont.truetype("C:\\Windows\\Fonts\\segoeui.ttf", size)
            except Exception:
                try:
                    return ImageFont.truetype("arial.ttf", size)
                except Exception:
                    return ImageFont.load_default()

    def _generate_war_cost_pies(self, home_vals: List[float], away_vals: List[float], categories: List[str]) -> Optional[Tuple[BytesIO, str]]:
        """Generate a side-by-side pie chart image for Home and Away.

        home_vals/away_vals: monetary totals per category in the order of `categories`.
        Returns (BytesIO, filename) or None if unavailable.
        """
        if not categories:
            return None
        # If PIL is unavailable, return a tiny placeholder PNG to ensure an image is always attached
        if not PIL_AVAILABLE:
            try:
                import base64
                # 1x1 transparent PNG
                b64 = (
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO3xYxUAAAAASUVORK5CYII="
                )
                bio = BytesIO(base64.b64decode(b64))
                bio.seek(0)
                return (bio, "chart_war_cost_pies.png")
            except Exception:
                return None
        # Pad values if lengths mismatch
        if len(home_vals) != len(categories):
            home_vals = list(home_vals) + [0.0] * (len(categories) - len(home_vals))
        if len(away_vals) != len(categories):
            away_vals = list(away_vals) + [0.0] * (len(categories) - len(away_vals))
        try:
            # Image dimensions and layout
            width = 900
            height = 420
            pad = 20
            title_h = 40
            # Minimal footer height since there is no legend; keep space for totals only
            line_step = 22
            legend_h = 48
            pie_area_h = height - title_h - legend_h - (pad * 2)
            pie_diameter = min(260, pie_area_h)
            # Space pies slightly further apart horizontally
            home_center = (int(width * 0.24), title_h + pad + pie_area_h // 2)
            away_center = (int(width * 0.76), title_h + pad + pie_area_h // 2)
            radius = pie_diameter // 2

            # Colors per category (consistent palette)
            palette = {
                "Resource": (46, 134, 222),   # Blue (legacy alias)
                "Consumption": (46, 134, 222),   # Blue
                "Units": (230, 126, 34),      # Orange
                "Infra": (142, 68, 173),      # Purple
                "Loot": (39, 174, 96),        # Green
            }
            # Build ordered colors list aligned to categories
            colors = [palette.get(cat, (200, 200, 200)) for cat in categories]

            img = Image.new("RGB", (width, height), (26, 26, 26))
            draw = ImageDraw.Draw(img)
            font_title = self._get_font(20)
            font_small = self._get_font(14)
            font_label = self._get_font(16)

            # Titles
            draw.text((pad, 10), "War Cost Breakdown", fill=(255, 255, 255), font=font_title)
            draw.text((home_center[0] - 30, title_h), "Home", fill=(220, 220, 220), font=font_label)
            draw.text((away_center[0] - 28, title_h), "Away", fill=(220, 220, 220), font=font_label)

            # Money formatting used by labels and legend
            def _fmt_money(x: float) -> str:
                try:
                    return f"${int(float(x or 0)):,}"
                except Exception:
                    return "$0"

            def _draw_pie(center: Tuple[int, int], vals: List[float]):
                total = sum([abs(float(v or 0)) for v in vals])
                bbox = [center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius]
                start_angle = 0.0
                if total <= 0:
                    # Draw a faint circle to indicate empty
                    draw.ellipse(bbox, outline=(90, 90, 90), width=2)
                    return
                for idx, v in enumerate(vals):
                    val = abs(float(v or 0))
                    frac = (val / total) if total > 0 else 0
                    end_angle = start_angle + 360.0 * frac
                    draw.pieslice(bbox, start=start_angle, end=end_angle, fill=colors[idx])
                    start_angle = end_angle

            # Draw both pies
            _draw_pie(home_center, home_vals)
            _draw_pie(away_center, away_vals)

            # Slice labels drawn INSIDE each slice: value only (short form)
            def _draw_slice_labels(center: Tuple[int, int], vals: List[float]):
                total = sum([abs(float(v or 0)) for v in vals])
                if total <= 0:
                    return
                import math
                start_angle = 0.0
                for idx, v in enumerate(vals):
                    val = abs(float(v or 0))
                    frac = (val / total) if total > 0 else 0
                    # Skip extremely small slices to avoid clutter
                    if frac <= 0.03:
                        continue
                    mid_angle = start_angle + (360.0 * frac) / 2.0
                    # Convert angle to radians
                    ang = math.radians(mid_angle)
                    # Label anchor inside the slice
                    label_r = int(radius * 0.60)
                    x1 = center[0] + int(label_r * math.cos(ang))
                    y1 = center[1] + int(label_r * math.sin(ang))
                    # Prepare single-line label: short value only
                    val_txt = self._fmt_money_short(val)
                    try:
                        bbox1 = draw.textbbox((0, 0), val_txt, font=font_small)
                        tw1 = bbox1[2] - bbox1[0]
                        th1 = bbox1[3] - bbox1[1]
                    except Exception:
                        tw1, th1 = 40, 12
                    tx1 = x1 - tw1 // 2
                    ty1 = y1 - th1 // 2
                    draw.text((tx1, ty1), val_txt, fill=(250, 250, 250), font=font_small)
                    start_angle += 360.0 * frac

            # Draw value labels next to each slice
            _draw_slice_labels(home_center, home_vals)
            _draw_slice_labels(away_center, away_vals)

            # No legend; draw outside labels for each slice with percentage under the category
            legend_y = height - legend_h + 12
            # Compute title bounding boxes to avoid overlapping
            try:
                home_title_bbox = draw.textbbox((home_center[0] - 30, title_h), "Home", font=font_label)
                away_title_bbox = draw.textbbox((away_center[0] - 28, title_h), "Away", font=font_label)
            except Exception:
                home_title_bbox = (home_center[0] - 50, title_h - 10, home_center[0] + 50, title_h + 10)
                away_title_bbox = (away_center[0] - 50, title_h - 10, away_center[0] + 50, title_h + 10)

            def _rects_intersect(a, b):
                return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])

            def _draw_outside_labels(center: Tuple[int, int], vals: List[float], title_bbox: Tuple[int, int, int, int]):
                total = sum([abs(float(v or 0)) for v in vals])
                if total <= 0:
                    return
                import math
                placed: List[Tuple[int, int, int, int]] = []
                start_angle = 0.0
                for idx, v in enumerate(vals):
                    val = abs(float(v or 0))
                    frac = (val / total) if total > 0 else 0
                    if frac <= 0.03:
                        start_angle += 360.0 * frac
                        continue
                    mid_angle = start_angle + (360.0 * frac) / 2.0
                    ang = math.radians(mid_angle)
                    # Initial label anchor outside the pie
                    label_r = radius + 24
                    x1 = center[0] + int(label_r * math.cos(ang))
                    y1 = center[1] + int(label_r * math.sin(ang))
                    # Two-line label: category name and percentage
                    name_txt = categories[idx]
                    pct_txt = f"{int(round(100.0 * frac))}%"
                    try:
                        bbox1 = draw.textbbox((0, 0), name_txt, font=font_small)
                        tw1 = bbox1[2] - bbox1[0]
                        th1 = bbox1[3] - bbox1[1]
                    except Exception:
                        tw1, th1 = 40, 12
                    try:
                        bbox2 = draw.textbbox((0, 0), pct_txt, font=font_small)
                        tw2 = bbox2[2] - bbox2[0]
                        th2 = bbox2[3] - bbox2[1]
                    except Exception:
                        tw2, th2 = 24, 12
                    block_w = max(tw1, tw2)
                    block_h = th1 + th2 + 2
                    # Position left or right of anchor based on angle sign
                    side_right = (math.cos(ang) >= 0)
                    if side_right:
                        tx = x1 + 6
                    else:
                        tx = x1 - block_w - 6
                    ty = y1 - block_h // 2
                    # Avoid overlaps with prior labels and title bbox by nudging vertically
                    max_iter = 30
                    step = 12
                    rect = (tx, ty, tx + block_w, ty + block_h)
                    def _overlaps_any(r):
                        if _rects_intersect(r, title_bbox):
                            return True
                        for pr in placed:
                            if _rects_intersect(r, pr):
                                return True
                        return False
                    i = 0
                    direction = -1
                    while _overlaps_any(rect) and i < max_iter:
                        ty += direction * step
                        rect = (tx, ty, tx + block_w, ty + block_h)
                        direction *= -1
                        i += 1
                    # Clamp within image bounds
                    ty = max(8, min(ty, height - block_h - legend_h - 8))
                    rect = (tx, ty, tx + block_w, ty + block_h)
                    # No connector line as requested; only draw text labels
                    # Draw the text
                    draw.text((tx, ty), name_txt, fill=(230, 230, 230), font=font_small)
                    draw.text((tx, ty + th1 + 2), pct_txt, fill=(210, 210, 210), font=font_small)
                    placed.append(rect)
                    start_angle += 360.0 * frac

            # Draw outside labels with percentages and connector lines
            _draw_outside_labels(home_center, home_vals, home_title_bbox)
            _draw_outside_labels(away_center, away_vals, away_title_bbox)

            # Totals under pies (short form)
            home_total = sum([abs(float(v or 0)) for v in home_vals])
            away_total = sum([abs(float(v or 0)) for v in away_vals])
            totals_y = height - legend_h + 8
            # Display clear totals under each pie
            draw.text((home_center[0] - 170, totals_y), f"Total war cost: {_fmt_money(home_total)}", fill=(255, 255, 255), font=font_label)
            draw.text((away_center[0] - 170, totals_y), f"Total war cost: {_fmt_money(away_total)}", fill=(255, 255, 255), font=font_label)

            bio = BytesIO()
            img.save(bio, format="PNG")
            bio.seek(0)
            return (bio, "chart_war_cost_pies.png")
        except Exception:
            return None

    async def generate_war_cost_pies(self, home_vals: List[float], away_vals: List[float], categories: List[str]) -> Optional[Tuple[BytesIO, str]]:
        """Async wrapper for pie chart generation."""
        return await asyncio.to_thread(self._generate_war_cost_pies, home_vals, away_vals, categories)

    async def _build_wars_embed(self, attackers_name: str, defenders_name: str, wars_between: List[Dict[str, Any]], home_ids: List[int], away_ids: List[int], guild: Optional[discord.Guild]) -> Tuple[discord.Embed, List[discord.File]]:
        agg = await self.aggregate_war_costs_by_party(wars_between, set(int(x) for x in (home_ids or [])), set(int(x) for x in (away_ids or [])))
        emoji_map = self._build_emoji_map_for_guild(guild)
        files: List[discord.File] = []

        # Fetch average prices
        prices = await self._get_price_map()
        p_gas = float(prices.get('GASOLINE', 0) or 0)
        p_mun = float(prices.get('MUNITIONS', 0) or 0)
        p_alum = float(prices.get('ALUMINUM', 0) or 0)
        p_steel = float(prices.get('STEEL', 0) or 0)
        p_uran = float(prices.get('URANIUM', 0) or 0)
        p_food = float(prices.get('FOOD', 0) or 0)
        p_coal = float(prices.get('COAL', 0) or 0)
        p_oil = float(prices.get('OIL', 0) or 0)
        p_iron = float(prices.get('IRON', 0) or 0)
        p_baux = float(prices.get('BAUXITE', 0) or 0)
        p_lead = float(prices.get('LEAD', 0) or 0)

        # Unit losses per side
        home_soldiers = float(agg.get('home_soldiers_lost', 0) or 0)
        home_tanks = float(agg.get('home_tanks_lost', 0) or 0)
        home_planes = float(agg.get('home_aircraft_lost', 0) or 0)
        home_ships = float(agg.get('home_ships_lost', 0) or 0)
        home_missiles = float(agg.get('home_missiles_lost', 0) or 0)
        home_nukes = float(agg.get('home_nukes_lost', 0) or 0)

        away_soldiers = float(agg.get('away_soldiers_lost', 0) or 0)
        away_tanks = float(agg.get('away_tanks_lost', 0) or 0)
        away_planes = float(agg.get('away_aircraft_lost', 0) or 0)
        away_ships = float(agg.get('away_ships_lost', 0) or 0)
        away_missiles = float(agg.get('away_missiles_lost', 0) or 0)
        away_nukes = float(agg.get('away_nukes_lost', 0) or 0)

        # Separate consumption (only gasoline and munitions used) from unit resources
        home_gas_cons = float(agg.get('home_gas_used', 0) or 0)
        away_gas_cons = float(agg.get('away_gas_used', 0) or 0)

        home_mun_cons = float(agg.get('home_mun_used', 0) or 0)
        away_mun_cons = float(agg.get('away_mun_used', 0) or 0)

        # Resources attributable to units (aluminum, steel, uranium), include both aggregated usage and per-unit derived amounts
        home_alum_units = float(agg.get('home_alum_used', 0) or 0) + (home_planes * 10.0) + (home_missiles * 150.0) + (home_nukes * 1000.0)
        away_alum_units = float(agg.get('away_alum_used', 0) or 0) + (away_planes * 10.0) + (away_missiles * 150.0) + (away_nukes * 1000.0)

        home_steel_units = float(agg.get('home_steel_used', 0) or 0) + (home_tanks * 0.5) + (home_ships * 30.0)
        away_steel_units = float(agg.get('away_steel_used', 0) or 0) + (away_tanks * 0.5) + (away_ships * 30.0)

        home_uran_units = (home_nukes * 500.0) + float(agg.get('home_uran_used', 0) or 0)
        away_uran_units = (away_nukes * 500.0) + float(agg.get('away_uran_used', 0) or 0)

        # Monetary value from consumption
        att_cons_val = (home_gas_cons * p_gas) + (home_mun_cons * p_mun)
        def_cons_val = (away_gas_cons * p_gas) + (away_mun_cons * p_mun)

        # Monetary value from unit losses (fixed per-unit costs)
        att_units_val = (
            home_soldiers * 5.0 +
            home_tanks * 60.0 +
            home_planes * 4000.0 +
            home_ships * 50000.0 +
            home_missiles * 150000.0 +
            home_nukes * 1750000.0
        )
        def_units_val = (
            away_soldiers * 5.0 +
            away_tanks * 60.0 +
            away_planes * 4000.0 +
            away_ships * 50000.0 +
            away_missiles * 150000.0 +
            away_nukes * 1750000.0
        )

        # Monetary value from unit resources (aluminum, steel, uranium)
        att_unit_res_val = (
            home_alum_units * p_alum +
            home_steel_units * p_steel +
            home_uran_units * p_uran
        )
        def_unit_res_val = (
            away_alum_units * p_alum +
            away_steel_units * p_steel +
            away_uran_units * p_uran
        )

        # Looted resources and money (credit)
        home_gas_loot = float(agg.get('home_gas_looted', 0) or 0)
        home_mun_loot = float(agg.get('home_mun_looted', 0) or 0)
        home_alum_loot = float(agg.get('home_alum_looted', 0) or 0)
        home_steel_loot = float(agg.get('home_steel_looted', 0) or 0)
        home_food_loot = float(agg.get('home_food_looted', 0) or 0)
        home_coal_loot = float(agg.get('home_coal_looted', 0) or 0)
        home_oil_loot = float(agg.get('home_oil_looted', 0) or 0)
        home_uran_loot = float(agg.get('home_uran_looted', 0) or 0)
        home_iron_loot = float(agg.get('home_iron_looted', 0) or 0)
        home_baux_loot = float(agg.get('home_baux_looted', 0) or 0)
        home_lead_loot = float(agg.get('home_lead_looted', 0) or 0)
        home_money_loot = float(agg.get('home_money_looted', 0) or 0)

        away_gas_loot = float(agg.get('away_gas_looted', 0) or 0)
        away_mun_loot = float(agg.get('away_mun_looted', 0) or 0)
        away_alum_loot = float(agg.get('away_alum_looted', 0) or 0)
        away_steel_loot = float(agg.get('away_steel_looted', 0) or 0)
        away_food_loot = float(agg.get('away_food_looted', 0) or 0)
        away_coal_loot = float(agg.get('away_coal_looted', 0) or 0)
        away_oil_loot = float(agg.get('away_oil_looted', 0) or 0)
        away_uran_loot = float(agg.get('away_uran_looted', 0) or 0)
        away_iron_loot = float(agg.get('away_iron_looted', 0) or 0)
        away_baux_loot = float(agg.get('away_baux_looted', 0) or 0)
        away_lead_loot = float(agg.get('away_lead_looted', 0) or 0)
        away_money_loot = float(agg.get('away_money_looted', 0) or 0)

        att_loot_val = (
            home_gas_loot * p_gas + home_mun_loot * p_mun + home_alum_loot * p_alum + home_steel_loot * p_steel +
            home_food_loot * p_food + home_coal_loot * p_coal + home_oil_loot * p_oil + home_uran_loot * p_uran +
            home_iron_loot * p_iron + home_baux_loot * p_baux + home_lead_loot * p_lead + home_money_loot
        )
        def_loot_val = (
            away_gas_loot * p_gas + away_mun_loot * p_mun + away_alum_loot * p_alum + away_steel_loot * p_steel +
            away_food_loot * p_food + away_coal_loot * p_coal + away_oil_loot * p_oil + away_uran_loot * p_uran +
            away_iron_loot * p_iron + away_baux_loot * p_baux + away_lead_loot * p_lead + away_money_loot
        )

        # Units total includes unit purchase costs plus resources for units
        att_units_total_val = att_units_val + att_unit_res_val
        def_units_total_val = def_units_val + def_unit_res_val

        # Combined monetary value (Consumption + Units Total + Infra + Loot Loss)
        # Treat loot as a loss to the party it was stolen from: add opponent's loot value
        att_comb_val = (
            att_cons_val + att_units_total_val +
            float(agg.get('home_infra_destroyed_value', 0) or 0) +
            def_loot_val
        )
        def_comb_val = (
            def_cons_val + def_units_total_val +
            float(agg.get('away_infra_destroyed_value', 0) or 0) +
            att_loot_val
        )

        embed = discord.Embed(color=discord.Color.blurple())
        # Header should only show total wars between selected parties; time window appended later
        embed.description = f"Across {int(agg.get('war_count', 0))} wars between selected parties"
        # Short title without emojis: collapse to counts to avoid long titles
        home_count = len(set(int(x) for x in (home_ids or [])))
        away_count = len(set(int(x) for x in (away_ids or [])))
        base = f"War Cost: {home_count} vs {away_count} alliances"
        name = base[:256]
        try:
            embed.set_author(name=name)
        except Exception:
            embed.title = name

        # Parties: show Home vs Away labels and alliance counts inferred from wars
        home_alliance_ids: Set[int] = set(int(x) for x in (home_ids or []))
        away_alliance_ids: Set[int] = set(int(x) for x in (away_ids or []))
        parties_value = (
            f"Home: {attackers_name or 'Home'}\n"
            f"Away: {defenders_name or 'Away'}"
        )
        embed.add_field(name="Parties", value=parties_value, inline=False)

        # Removed War Types section to streamline embed and reduce clutter

        # War Status: Home victory/defeat (ended wars), plus Peace/Active/Expired
        home_victory = 0
        home_defeat = 0
        peace_count = 0
        active_count = 0
        expired_count = 0

        for w in wars_between or []:
            # Determine active vs ended and peace/expired
            end_raw = w.get('end_date') or None
            att_peace = bool(w.get('att_peace') or w.get('attpeace') or False)
            def_peace = bool(w.get('def_peace') or w.get('defpeace') or False)
            if not end_raw:
                active_count += 1
            else:
                if att_peace or def_peace:
                    peace_count += 1
                else:
                    expired_count += 1

            # Winner side only counted for ended wars with a known winner
            try:
                winner_id = int(w.get('winner_id') or 0)
            except Exception:
                winner_id = 0
            if winner_id:
                # Attacker/Defender nation and alliance IDs
                try:
                    war_att_nation_id = int(w.get('att_id') or w.get('attid') or (w.get('attacker') or {}).get('id') or 0)
                except Exception:
                    war_att_nation_id = 0
                try:
                    war_def_nation_id = int(w.get('def_id') or w.get('defid') or (w.get('defender') or {}).get('id') or 0)
                except Exception:
                    war_def_nation_id = 0
                try:
                    war_att_alliance_id = int(w.get('att_alliance_id') or (w.get('attacker') or {}).get('alliance_id') or 0)
                except Exception:
                    war_att_alliance_id = 0
                try:
                    war_def_alliance_id = int(w.get('def_alliance_id') or (w.get('defender') or {}).get('alliance_id') or 0)
                except Exception:
                    war_def_alliance_id = 0

                winner_alliance_id = 0
                if winner_id and war_att_nation_id and winner_id == war_att_nation_id:
                    winner_alliance_id = war_att_alliance_id
                elif winner_id and war_def_nation_id and winner_id == war_def_nation_id:
                    winner_alliance_id = war_def_alliance_id

                if winner_alliance_id:
                    if winner_alliance_id in home_alliance_ids:
                        home_victory += 1
                    elif winner_alliance_id in away_alliance_ids:
                        home_defeat += 1

        # Group status by state so it sums to the total, and separate ended outcomes
        ended_count = peace_count + expired_count
        wins_count = home_victory + home_defeat
        no_winner = expired_count

        state_lines = [
            f"🔋 Active: {active_count}",
            f"🪫 Ended: {ended_count}",
            f"⚔️ Total: {int(agg.get('war_count', 0))}",
        ]
        embed.add_field(name="War Status", value="\n".join(state_lines), inline=False)

        # War Types: count by war_type across all wars in scope, display with emojis
        type_counts: Dict[str, int] = {}
        for w in wars_between or []:
            t_raw = w.get('war_type') or w.get('wartype')
            t = str(t_raw).strip().upper() if t_raw is not None else ''
            if not t:
                t = 'UNKNOWN'
            type_counts[t] = type_counts.get(t, 0) + 1

        # Display in preferred order with custom emojis
        ordered_types = ["RAID", "ATTRITION", "ORDINARY"]
        type_emojis = {
            "RAID": "🏴‍☠️",
            "ATTRITION": "💣",
            "ORDINARY": "🛡️",
        }
        display_types = [t for t in ordered_types if t in type_counts] + [k for k in type_counts.keys() if k not in ordered_types]
        type_lines = []
        for t in display_types:
            emj = type_emojis.get(t, "")
            lbl = t.title()
            cnt = int(type_counts.get(t, 0) or 0)
            # Show emoji + label + count
            type_lines.append(f"{emj} {lbl}: {cnt}")
        if type_lines:
            embed.add_field(name="War Types", value="\n".join(type_lines), inline=False)

        outcome_lines = [
            f"🎖️ Home Victory: {home_victory}",
            f"💀 Home Defeat: {home_defeat}",
            f"🕊️ Peace: {peace_count}",
            f"❌ No Winner: {no_winner}",
        ]
        embed.add_field(name="Ended Outcomes", value="\n".join(outcome_lines), inline=False)

        # Infra values
        home_infra_levels = int(agg.get('home_infra_destroyed', 0) or 0)
        away_infra_levels = int(agg.get('away_infra_destroyed', 0) or 0)
        home_infra_val = float(agg.get('home_infra_destroyed_value', 0) or 0)
        away_infra_val = float(agg.get('away_infra_destroyed_value', 0) or 0)

        # Note: Using per-category fields below with universal spacing via _format_columns

        # Helper to build resource label using server custom emojis when available
        def rlbl(key: str, fallback: str) -> str:
            try:
                k = (key or '').upper()
                emj = (emoji_map or {}).get(k)
                if emj:
                    return f"{emj} {fallback}"
            except Exception:
                pass
            return fallback

        # Pretty formatter for resource quantities: integers without decimals, fractional with one decimal
        def fmt_qty(q: float) -> str:
            try:
                qf = float(q or 0)
            except Exception:
                qf = 0.0
            if abs(qf - round(qf)) < 1e-9:
                return f"{int(round(qf)):,}"
            return f"{qf:,.1f}"


        loot_present = (
            (home_gas_loot + home_mun_loot + home_alum_loot + home_steel_loot + home_food_loot + home_coal_loot + home_oil_loot + home_uran_loot + home_iron_loot + home_baux_loot + home_lead_loot + home_money_loot) > 0 or
            (away_gas_loot + away_mun_loot + away_alum_loot + away_steel_loot + away_food_loot + away_coal_loot + away_oil_loot + away_uran_loot + away_iron_loot + away_baux_loot + away_lead_loot + away_money_loot) > 0
        )

        # Global uniform widths across all categories
        fixed_widths: Optional[Tuple[int, int, int]] = None

        # Add a single compact three-column block per category (Stat|Home|Away)
        def _add_category_columns(label: str, rows_list: List[Tuple[str, str, str]]) -> None:
            # Chunk rows to respect embed field value limits
            max_len = 980
            chunks: List[List[Tuple[str, str, str]]] = []
            cur: List[Tuple[str, str, str]] = []
            cur_len = 0
            for (st, hv, av) in rows_list:
                nl = 1
                # Predict length increase conservatively
                inc = len(st) + len(hv) + len(av) + nl + 4  # include separators
                if cur_len + inc > max_len:
                    if cur:
                        chunks.append(cur)
                    cur = [(st, hv, av)]
                    cur_len = inc
                else:
                    cur.append((st, hv, av))
                    cur_len += inc
            if cur:
                chunks.append(cur)

            for i, ch in enumerate(chunks, start=1):
                suf = f" ({i})" if len(chunks) > 1 else ""
                block = self._format_columns("Home", "Away", ch, fixed_widths, include_header=False)
                # Add a leading blank line for visual spacing between categories
                embed.add_field(name=f"{label}{suf}", value=("\n" + block), inline=False)

        # Infra
        infra_rows = [
            ("🏗️ Levels", f"`{home_infra_levels:,}`", f"`{away_infra_levels:,}`"),
            ("💸 Value", f"`$${int(home_infra_val):,}`", f"`$${int(away_infra_val):,}`"),
        ]
        # Consumption
        cons_rows = [
            (f"{rlbl('GASOLINE','Gasoline')}", f"`{fmt_qty(home_gas_cons)}`", f"`{fmt_qty(away_gas_cons)}`"),
            (f"{rlbl('MUNITIONS','Munitions')}", f"`{fmt_qty(home_mun_cons)}`", f"`{fmt_qty(away_mun_cons)}`"),
        ]
        # Units
        units_rows = [
            ("🪖 Soldiers", f"`{int(home_soldiers):,}`", f"`{int(away_soldiers):,}`"),
            ("🚙 Tanks", f"`{int(home_tanks):,}`", f"`{int(away_tanks):,}`"),
            ("🛩️ Aircraft", f"`{int(home_planes):,}`", f"`{int(away_planes):,}`"),
            ("⚓ Ships", f"`{int(home_ships):,}`", f"`{int(away_ships):,}`"),
            ("🎯 Missiles", f"`{int(home_missiles):,}`", f"`{int(away_missiles):,}`"),
            ("☢️ Nukes", f"`{int(home_nukes):,}`", f"`{int(away_nukes):,}`"),
        ]
        # Loot Loss
        loot_rows: List[Tuple[str, str, str]] = []
        if loot_present:
            loot_rows = [
                (f"{rlbl('GASOLINE','Gasoline')}", f"`{fmt_qty(away_gas_loot)}`", f"`{fmt_qty(home_gas_loot)}`"),
                (f"{rlbl('MUNITIONS','Munitions')}", f"`{fmt_qty(away_mun_loot)}`", f"`{fmt_qty(home_mun_loot)}`"),
                (f"{rlbl('ALUMINUM','Aluminum')}", f"`{fmt_qty(away_alum_loot)}`", f"`{fmt_qty(home_alum_loot)}`"),
                (f"{rlbl('STEEL','Steel')}", f"`{fmt_qty(away_steel_loot)}`", f"`{fmt_qty(home_steel_loot)}`"),
                (f"{rlbl('FOOD','Food')}", f"`{fmt_qty(away_food_loot)}`", f"`{fmt_qty(home_food_loot)}`"),
                (f"{rlbl('COAL','Coal')}", f"`{fmt_qty(away_coal_loot)}`", f"`{fmt_qty(home_coal_loot)}`"),
                (f"{rlbl('OIL','Oil')}", f"`{fmt_qty(away_oil_loot)}`", f"`{fmt_qty(home_oil_loot)}`"),
                (f"{rlbl('URANIUM','Uranium')}", f"`{fmt_qty(away_uran_loot)}`", f"`{fmt_qty(home_uran_loot)}`"),
                (f"{rlbl('IRON','Iron')}", f"`{fmt_qty(away_iron_loot)}`", f"`{fmt_qty(home_iron_loot)}`"),
                (f"{rlbl('BAUXITE','Bauxite')}", f"`{fmt_qty(away_baux_loot)}`", f"`{fmt_qty(home_baux_loot)}`"),
                (f"{rlbl('LEAD','Lead')}", f"`{fmt_qty(away_lead_loot)}`", f"`{fmt_qty(home_lead_loot)}`"),
                ("💰 Money", f"`$${int(away_money_loot):,}`", f"`$${int(home_money_loot):,}`"),
            ]

        # Totals (short-form values to ensure one-line fit)
        totals_rows = [
            ("🧰 Consumption", f"`{self._fmt_money_short(att_cons_val)}`", f"`{self._fmt_money_short(def_cons_val)}`"),
            ("⚰️ Units", f"`{self._fmt_money_short(att_units_total_val)}`", f"`{self._fmt_money_short(def_units_total_val)}`"),
            ("🏗️ Infra", f"`{self._fmt_money_short(home_infra_val)}`", f"`{self._fmt_money_short(away_infra_val)}`"),
            ("💎 Looted", f"`{self._fmt_money_short(def_loot_val)}`", f"`{self._fmt_money_short(att_loot_val)}`"),
            ("🧮 Combined", f"`{self._fmt_money_short(att_comb_val)}`", f"`{self._fmt_money_short(def_comb_val)}`"),
        ]
        # Compute global fixed widths once using all rows
        try:
            all_rows: List[Tuple[str, str, str]] = []
            all_rows.extend([("🏗️ Levels", f"`{home_infra_levels:,}`", f"`{away_infra_levels:,}`")])
            all_rows.extend([("💸 Value", f"`{int(home_infra_val):,}`", f"`{int(away_infra_val):,}`")])
            all_rows.extend(cons_rows)
            all_rows.extend(units_rows)
            if loot_rows:
                all_rows.extend(loot_rows)
            all_rows.extend(totals_rows)

            # Calculate maxima and apply compare-like caps
            label_max = max([len(lbl) for lbl, _, _ in all_rows] + [len("Stat")]) if all_rows else 6
            left_max = max([len(lv) for _, lv, _ in all_rows] + [len("Home")]) if all_rows else 8
            right_max = max([len(rv) for _, _, rv in all_rows] + [len("Away")]) if all_rows else 8
            fixed_widths = (
                max(6, min(label_max, 10)),
                max(8, min(left_max, 14)),
                max(8, min(right_max, 14)),
            )
        except Exception:
            fixed_widths = None

        # Do not add the column header line; categories will align without it

        # Now add categories using uniform widths
        _add_category_columns("Infra", infra_rows)
        _add_category_columns("Consumption", cons_rows)
        _add_category_columns("Units", units_rows)
        if loot_rows:
            _add_category_columns("Loot Loss", loot_rows)
        _add_category_columns("Totals", totals_rows)

        # Generate and attach side-by-side pies with updated categories
        categories = ["Consumption", "Units", "Infra", "Loot"]
        # Use loot losses for pies to reflect cost contributions
        home_vals = [att_cons_val, att_units_total_val, float(agg.get('home_infra_destroyed_value', 0) or 0), def_loot_val]
        away_vals = [def_cons_val, def_units_total_val, float(agg.get('away_infra_destroyed_value', 0) or 0), att_loot_val]
        try:
            pie = await self.generate_war_cost_pies(home_vals, away_vals, categories)
            if pie:
                bio, fname = pie
                f = discord.File(bio, filename=fname)
                files.append(f)
        except Exception:
            pass

        embed.set_footer(text="Values use current market averages for resources")

        # Attach the pie image as the final step to ensure it appears at the bottom
        try:
            if files:
                embed.set_image(url=f"attachment://{files[-1].filename}")
        except Exception:
            pass

        return embed, files

    # ---------------------------
    # Slash Command: /wars
    # ---------------------------
    @app_commands.describe(
        home="Alliance names or IDs/links for Home party (comma-separated)",
        away="Alliance names or IDs/links for Away party (comma-separated)",
        time="Time window to include wars, e.g. 6h, 3d, 2w, 2m"
    )
    @app_commands.autocomplete(home=target_autocomplete, away=target_autocomplete)
    @app_commands.command(name="wars", description="Show War Cost between Home and Away parties")
    async def wars(self, interaction: discord.Interaction, home: str, away: str, time: Optional[str] = None):
        try:
            await interaction.response.defer(thinking=True)

            # Resolve Home party
            parsed_attackers = await self._resolve_targets(home)
            attackers_valid = [(aid, name) for aid, name in parsed_attackers if isinstance(aid, int) and aid > 0]
            if not attackers_valid:
                await interaction.followup.send("❌ Could not resolve any alliance for Home party.")
                return
            attackers_ids: List[int] = [int(aid) for aid, _ in attackers_valid]
            # Build a readable attackers label without listing numeric IDs
            attackers_name = " + ".join([nm or "Alliance" for aid, nm in attackers_valid])

            # Resolve Away party
            parsed_def = await self._resolve_targets(away)
            defenders_valid = [(aid, name) for aid, name in parsed_def if isinstance(aid, int) and aid > 0]
            if not defenders_valid:
                await interaction.followup.send("❌ Could not resolve any alliances for Away party. Provide IDs, links, or known names.")
                return
            defenders_ids = [int(aid) for aid, _ in defenders_valid]
            defenders_name = " + ".join([nm or "Alliance" for aid, nm in defenders_valid])

            # Fetch wars for attackers side and defenders side, then filter to wars between the two groups
            q = self.query_instance
            if not q:
                await interaction.followup.send("❌ Query system unavailable.")
                return

            # Parse time window argument (e.g., 6h, 3d, 2w, 2m)
            def _parse_time_limit_arg(arg: Optional[str]) -> Tuple[Optional[str], Optional[__import__('datetime').datetime]]:
                if not arg:
                    return None, None
                s = str(arg).strip().lower()
                m = __import__('re').match(r"^(\d+)\s*([hdwm])$", s)
                if not m:
                    return None, None
                qty = int(m.group(1))
                unit = m.group(2)
                from datetime import datetime, timedelta, timezone
                # Use timezone-aware UTC to avoid naive/aware comparison errors
                now = datetime.now(timezone.utc)
                if unit == 'h':
                    delta = timedelta(hours=qty)
                elif unit == 'd':
                    delta = timedelta(days=qty)
                elif unit == 'w':
                    delta = timedelta(weeks=qty)
                elif unit == 'm':
                    # Approximate a month as 30 days
                    delta = timedelta(days=qty * 30)
                else:
                    return None, None
                cutoff = now - delta
                label = f"{qty}{unit}"
                return label, cutoff

            time_label, cutoff_dt = _parse_time_limit_arg(time)

            # Helpers to parse date and filter wars by time
            from datetime import datetime as _dt
            def _parse_date_safe(s: Any) -> Optional[_dt]:
                if not s:
                    return None
                try:
                    v = str(s).strip()
                    # Normalize Z suffix to ISO offset
                    if v.endswith('Z'):
                        v = v[:-1] + '+00:00'
                    parsed: Optional[_dt] = None
                    try:
                        parsed = _dt.fromisoformat(v)
                    except Exception:
                        parsed = None
                    if parsed is None:
                        # Common fallback formats, including optional timezone offset
                        for fmt in ("%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                            try:
                                parsed = _dt.strptime(v, fmt)
                                if parsed:
                                    break
                            except Exception:
                                continue
                    if parsed is None:
                        return None
                    # Normalize to timezone-aware UTC for safe comparisons
                    try:
                        from datetime import timezone as _tz
                        if parsed.tzinfo is None:
                            parsed = parsed.replace(tzinfo=_tz.utc)
                        else:
                            parsed = parsed.astimezone(_tz.utc)
                        return parsed
                    except Exception:
                        # If normalization fails, return parsed as-is
                        return parsed
                except Exception:
                    return None

            def _war_in_window(w: Dict[str, Any]) -> bool:
                if not cutoff_dt:
                    return True
                # Prefer attack dates when present
                attacks = w.get('attacks') or []
                for a in attacks or []:
                    ad = _parse_date_safe(a.get('date'))
                    if ad and ad >= cutoff_dt:
                        return True
                # Fallback to war start/end dates
                for k in ('date', 'end_date'):
                    d = _parse_date_safe(w.get(k))
                    if d and d >= cutoff_dt:
                        return True
                return False

            wars_between = await q.get_wars_between_parties(
                home_alliance_ids=attackers_ids,
                away_alliance_ids=defenders_ids,
                cutoff_dt=cutoff_dt,
                limit=None,
                force_refresh=True,
            )
            # Derive deterministic parties key to load unified cached payload
            try:
                norm_home_ids = sorted({int(x) for x in (attackers_ids or []) if int(x) > 0})
                norm_away_ids = sorted({int(x) for x in (defenders_ids or []) if int(x) > 0})
                home_party_id = "-".join([str(a) for a in norm_home_ids]) or "none"
                away_party_id = "-".join([str(b) for b in norm_away_ids]) or "none"
                parties_key = f"war_parties_{home_party_id}_vs_{away_party_id}"
            except Exception:
                parties_key = None

            # Load saved parties payload and prefer its complete data
            payload_wars: List[Dict[str, Any]] = wars_between
            payload_home_ids: List[int] = attackers_ids
            payload_away_ids: List[int] = defenders_ids
            payload_created: Optional[str] = None
            payload_total: Optional[int] = None
            try:
                if parties_key:
                    exp = self._payload_expiry.get(parties_key, 0.0)
                    if exp > time.monotonic():
                        payload = self._payload_cache.get(parties_key, {})
                        if isinstance(payload, dict):
                            maybe_wars = payload.get('wars')
                            if isinstance(maybe_wars, list) and maybe_wars:
                                payload_wars = maybe_wars
                            try:
                                h_items = payload.get('home_alliances') or []
                                a_items = payload.get('away_alliances') or []
                                h_ids = [int((it or {}).get('id') or 0) for it in h_items]
                                a_ids = [int((it or {}).get('id') or 0) for it in a_items]
                                payload_home_ids = [i for i in h_ids if i > 0] or payload_home_ids
                                payload_away_ids = [j for j in a_ids if j > 0] or payload_away_ids
                            except Exception:
                                pass
                            payload_created = payload.get('created_at') or None
                            try:
                                tv = payload.get('total_wars')
                                payload_total = int(tv) if tv is not None else None
                            except Exception:
                                payload_total = None
            except Exception as e:
                self.logger.debug(f"war_cost.py: failed to load parties payload for {parties_key}: {e}")

            # Persist side-specific Home/Away wars payloads with deterministic keys and auto-delete scheduling
            try:
                home_wars_key = f"war_party_home_{home_party_id}_wars" if 'home_party_id' in locals() else "war_party_home_wars"
                away_wars_key = f"war_party_away_{away_party_id}_wars" if 'away_party_id' in locals() else "war_party_away_wars"
                cutoff_iso = None
                try:
                    if cutoff_dt:
                        cutoff_iso = cutoff_dt.isoformat()
                except Exception:
                    cutoff_iso = None
                now_iso = None
                try:
                    from datetime import datetime, timezone
                    now_iso = datetime.now(timezone.utc).isoformat()
                except Exception:
                    now_iso = None
                home_payload = {
                    'role': 'party_wars',
                    'side': 'home',
                    'alliances': [{'id': int(i)} for i in (payload_home_ids or []) if isinstance(i, int) and i > 0],
                    'wars': list(payload_wars or []),
                    'total_wars': len(payload_wars or []),
                    'created_at': now_iso,
                    'cutoff': cutoff_iso,
                }
                away_payload = {
                    'role': 'party_wars',
                    'side': 'away',
                    'alliances': [{'id': int(j)} for j in (payload_away_ids or []) if isinstance(j, int) and j > 0],
                    'wars': list(payload_wars or []),
                    'total_wars': len(payload_wars or []),
                    'created_at': now_iso,
                    'cutoff': cutoff_iso,
                }
                self._payload_cache[home_wars_key] = home_payload
                self._payload_expiry[home_wars_key] = time.monotonic() + self._payload_ttl_seconds
                self._payload_cache[away_wars_key] = away_payload
                self._payload_expiry[away_wars_key] = time.monotonic() + self._payload_ttl_seconds
            except Exception as e:
                # Do not block embed generation on persistence errors
                try:
                    self.logger.debug(f"war_cost.py: error persisting party wars payloads: {e}")
                except Exception:
                    pass

            # Build and send embed (and optional image files) using cached payload
            embed, files = await self._build_wars_embed(
                attackers_name,
                defenders_name,
                payload_wars,
                payload_home_ids,
                payload_away_ids,
                interaction.guild,
            )
            if time_label:
                try:
                    # Append time window to the single header sentence cleanly
                    embed.description = f"{embed.description} in the last {time_label}."
                except Exception:
                    pass
            else:
                try:
                    # If no time window was provided, terminate the sentence with a period
                    embed.description = f"{embed.description}."
                except Exception:
                    pass
            # Append payload metadata when available
            try:
                extra_bits: List[str] = []
                if isinstance(payload_total, int):
                    extra_bits.append(f"wars={payload_total}")
                if payload_created:
                    extra_bits.append(f"saved={payload_created}")
                if extra_bits:
                    foot = embed.footer.text or ""
                    sep = " | " if foot else ""
                    embed.set_footer(text=f"{foot}{sep}{' '.join(extra_bits)}")
            except Exception:
                pass
            await interaction.followup.send(embed=embed, files=files)
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ Error fetching wars: {e}")
            except Exception:
                pass


async def setup(bot: commands.Bot):
    # Add the cog
    try:
        await bot.add_cog(WarsCostCog(bot))
    except Exception as e:
        logging.getLogger(__name__).warning(f"war_cost.py setup: failed to add cog: {e}")

    # Ensure slash command is registered in the tree
    try:
        existing = [cmd for cmd in bot.tree.get_commands() if getattr(cmd, 'name', '') == 'wars']
        if not existing:
            cog = bot.get_cog('WarsCostCog')
            if cog:
                for maybe_cmd in getattr(cog, '__cog_app_commands__', []):
                    try:
                        if isinstance(maybe_cmd, app_commands.Command) and maybe_cmd.name == 'wars':
                            bot.tree.add_command(maybe_cmd)
                            break
                    except Exception:
                        continue
    except Exception as e:
        logging.getLogger(__name__).warning(f"war_cost.py setup: command registration/sync issue: {e}")
