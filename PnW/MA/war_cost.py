import discord
from discord import app_commands
from discord.ext import commands

import time
import re
import logging
import asyncio
from typing import Any, Dict, List, Optional, Tuple, Set, TypedDict
from io import BytesIO
from datetime import datetime, timedelta

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config import HOME_ALLIANCE_ID

class UnitLossStats(TypedDict):
    soldiers: int
    tanks: int
    aircraft: int
    ships: int

class LootGainedStats(TypedDict):
    money: float
    food: float
    oil: float
    uranium: float
    steel: float
    aluminum: float
    lead: float
    bauxite: float
    iron: float
    coal: float
    gasoline: float

from Systems.PnW.Util.query import create_query_instance
from Systems.PnW.Util.calc import AllianceCalculator
from Systems.Functions import emoji as emoji_mod

UserDataManager: Optional[Any] = None

# Optional image generation support (same pattern as compare.py)
Image: Optional[Any] = None
ImageDraw: Optional[Any] = None
ImageFont: Optional[Any] = None
try:
    from PIL import Image as PILImage, ImageDraw as PILImageDraw, ImageFont as PILImageFont
    Image = PILImage
    ImageDraw = PILImageDraw
    ImageFont = PILImageFont
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False


class WarsCostCog(commands.Cog):
    """Provides a /wars slash command to summarize war costs between two parties (Attackers vs Defenders)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.query_instance = None
        self.calc_instance = AllianceCalculator()
        try:
            self.query_instance = create_query_instance(logger=self.logger)
        except Exception as e:
            self.logger.warning(f"war_cost.py: Failed to init query instance: {e}")

        # No external icon URLs; we will use server custom emojis if available
        self._resource_emojis: Dict[str, str] = {}

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
        m = re.search(r"id\\s*=\\s*(\\d+)", s)
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
                    aid = int(item.get('id') or 0)
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
        if to_batch and self.query_instance:
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
                    rid = int(item.get('id') or 0)
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



    def _format_columns(self, left_hdr: str, right_hdr: str, rows: List[Tuple[str, str, str]], fixed_widths: Optional[Tuple[int, int, int]] = None, include_header: bool = True) -> str:
        """Format aligned three columns: Stat | Home | Away, without code blocks.
        Uses consistent column widths across categories when provided via fixed_widths.
        Set include_header=False to omit the header line.
        """
        # Use figure spaces to preserve visual alignment in Discord's proportional font.
        FIGURE_SPACE = "\\u2007"  # same width as digits in many fonts
        NBSP = "\\u00A0"
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
        return "\\n".join(out)

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
        return "```" + "\\n".join(lines) + "```"

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
        return "```" + "\\n".join(lines) + "```"

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

    class WarStatsAggregate(TypedDict):
        units_lost: UnitLossStats
        wars_won: int
        total_infra_destroyed: float
        total_wars_participated: int
        resistance_total: int
        loot_gained: LootGainedStats
        resources_lost: Dict[str, float]
        infra_destroyed_value: float
        units_lost_value: float
        loot_lost_value: float
        total_money_lost: float

    class WarMonetaryStats(TypedDict):
        res_lost: float
        units_lost: float
        infra_lost: float
        loot_lost: float
        net: float
        total_lost: float
        loot_gained: float

    def _new_war_stats_aggregate(self) -> WarStatsAggregate:
        return {
            'units_lost': {
                'soldiers': 0,
                'tanks': 0,
                'aircraft': 0,
                'ships': 0,
            },
            'wars_won': 0,
            'total_infra_destroyed': 0.0,
            'total_wars_participated': 0,
            'resistance_total': 0,
            'loot_gained': {
                'money': 0.0,
                'food': 0.0,
                'oil': 0.0,
                'uranium': 0.0,
            },
            'resources_lost': {
                'food': 0.0,
                'oil': 0.0,
                'uranium': 0.0,
                'steel': 0.0,
                'aluminum': 0.0,
                'lead': 0.0,
                'bauxite': 0.0,
                'iron': 0.0,
                'coal': 0.0,
                'gasoline': 0.0,
            },
            'infra_destroyed_value': 0.0,
            'units_lost_value': 0.0,
            'loot_lost_value': 0.0,
            'total_money_lost': 0.0,
        }

    def _accumulate_war_stats(self, aggregate: WarStatsAggregate, war_data: Dict[str, Any], role: str) -> None:
        prefix = 'attacker_' if role == 'attacker' else 'defender_'

        # Accumulate units lost
        aggregate['units_lost']['soldiers'] += war_data.get(f'{prefix}soldiers_lost', 0)
        aggregate['units_lost']['tanks'] += war_data.get(f'{prefix}tanks_lost', 0)
        aggregate['units_lost']['aircraft'] += war_data.get(f'{prefix}aircraft_lost', 0)
        aggregate['units_lost']['ships'] += war_data.get(f'{prefix}ships_lost', 0)

        # Accumulate wars won (assuming 'won' is a boolean or 1/0)
        # This logic needs to be careful. 'wars_won' should only increment if the *current* party won.
        # The war_data usually has 'winner_id' or similar.
        # For now, I'll assume 'war_won' in war_data refers to the perspective of the 'role'.
        if war_data.get(f'{prefix}won', False): # This is a guess, need to verify PnW API structure
            aggregate['wars_won'] += 1

        # Accumulate total infrastructure destroyed
        aggregate['total_infra_destroyed'] += war_data.get(f'{prefix}infrastructure_destroyed', 0.0)

        # Accumulate total wars participated
        aggregate['total_wars_participated'] += 1 # Each call represents one war

        # Accumulate resistance total
        aggregate['resistance_total'] += war_data.get(f'{prefix}resistance_gained', 0) # Or 'resistance_lost' depending on context

        # Accumulate loot gained
        aggregate['loot_gained']['money'] += war_data.get(f'{prefix}money_gained', 0.0)
        aggregate['loot_gained']['food'] += war_data.get(f'{prefix}food_gained', 0.0)
        aggregate['loot_gained']['oil'] += war_data.get(f'{prefix}oil_gained', 0.0)
        aggregate['loot_gained']['uranium'] += war_data.get(f'{prefix}uranium_gained', 0.0)
        aggregate['loot_gained']['steel'] += war_data.get(f'{prefix}steel_gained', 0.0)
        aggregate['loot_gained']['aluminum'] += war_data.get(f'{prefix}aluminum_gained', 0.0)
        aggregate['loot_gained']['lead'] += war_data.get(f'{prefix}lead_gained', 0.0)
        aggregate['loot_gained']['bauxite'] += war_data.get(f'{prefix}bauxite_gained', 0.0)
        aggregate['loot_gained']['iron'] += war_data.get(f'{prefix}iron_gained', 0.0)
        aggregate['loot_gained']['coal'] += war_data.get(f'{prefix}coal_gained', 0.0)
        aggregate['loot_gained']['gasoline'] += war_data.get(f'{prefix}gasoline_gained', 0.0)

        # Accumulate resources lost (this will be more complex as it's a dict)
        # Assuming war_data has a 'resources_lost' dict
        for res, amount in war_data.get(f'{prefix}resources_lost', {}).items(): # This is a guess
            aggregate['resources_lost'][res] = aggregate['resources_lost'].get(res, 0.0) + amount

        # Also need to accumulate total_money_lost for the monetary calculation
        aggregate['total_money_lost'] += war_data.get(f'{prefix}money_lost', 0.0) # Another guess

    async def _war_stats_to_monetary(self, aggregate: WarStatsAggregate, price_map: Dict[str, float]) -> WarMonetaryStats:
        # Calculate unit values
        units_lost_value = (
            aggregate['units_lost']['soldiers'] * price_map.get('SOLDIER', 0.0) +
            aggregate['units_lost']['tanks'] * price_map.get('TANK', 0.0) +
            aggregate['units_lost']['aircraft'] * price_map.get('AIRCRAFT', 0.0) +
            aggregate['units_lost']['ships'] * price_map.get('SHIP', 0.0)
        )

        # Calculate infrastructure destroyed value (assuming a fixed value per infra or using a price map if available)
        # For now, let's assume a generic value or use a placeholder if not in price_map
        infra_destroyed_value = aggregate['total_infra_destroyed'] * price_map.get('INFRASTRUCTURE', 10000.0) # Placeholder

        # Calculate resources lost value
        res_lost_value = 0.0
        for res, amount in aggregate['resources_lost'].items():
            res_lost_value += amount * price_map.get(res.upper(), 0.0)

        # Calculate loot lost value (assuming this is the value of resources lost to the enemy)
        # This might be tricky. If 'loot_gained' is what *we* gained, then 'loot_lost' would be what *they* gained from us.
        # For now, let's assume 'loot_lost_value' is derived from 'resources_lost' and 'total_money_lost'
        loot_lost_value = aggregate['total_money_lost'] + res_lost_value # This needs clarification based on actual PnW data

        # Calculate loot gained value
        loot_gained_value = (
            aggregate['loot_gained']['money'] +
            aggregate['loot_gained']['food'] * price_map.get('FOOD', 0.0) +
            aggregate['loot_gained']['oil'] * price_map.get('OIL', 0.0) +
            aggregate['loot_gained']['uranium'] * price_map.get('URANIUM', 0.0)
        )

        total_lost = units_lost_value + infra_destroyed_value + res_lost_value + aggregate['total_money_lost'] # Assuming total_money_lost is separate from res_lost

        net = loot_gained_value - total_lost

        return {
            'res_lost': res_lost_value,
            'units_lost': units_lost_value,
            'infra_lost': infra_destroyed_value,
            'loot_lost': loot_lost_value, # This needs to be properly defined based on PnW data
            'net': net,
            'total_lost': total_lost,
            'loot_gained': loot_gained_value,
        }

    # ---------------------------
    # Chart generation helpers (PIL)
    # ---------------------------
    def _get_font(self, size: int = 16) -> Optional[Any]:
        if not PIL_AVAILABLE or ImageFont is None:
            return None
        try:
            return ImageFont.truetype("C:\\\\Windows\\\\Fonts\\\\seguiemj.ttf", size)
        except Exception:
            try:
                return ImageFont.truetype("C:\\\\Windows\\\\Fonts\\\\segoeui.ttf", size)
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
        if not PIL_AVAILABLE or Image is None or ImageDraw is None:
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
            legend_x_start = pad
            total_home_val = sum(home_vals)
            total_away_val = sum(away_vals)

            for i, cat in enumerate(categories):
                # Home side
                home_val = home_vals[i]
                home_pct = (home_val / total_home_val) * 100 if total_home_val > 0 else 0
                home_str = f"{self._fmt_money_short(home_val)} ({home_pct:.0f}%)"
                # Away side
                away_val = away_vals[i]
                away_pct = (away_val / total_away_val) * 100 if total_away_val > 0 else 0
                away_str = f"{self._fmt_money_short(away_val)} ({away_pct:.0f}%)"

                # Draw category color swatch
                swatch_y = legend_y + (i * line_step)
                draw.rectangle([legend_x_start, swatch_y, legend_x_start + 14, swatch_y + 14], fill=colors[i])

                # Draw text labels
                cat_x = legend_x_start + 20
                home_x = legend_x_start + 150
                away_x = legend_x_start + 300
                draw.text((cat_x, swatch_y - 2), cat, fill=(220, 220, 220), font=font_small)
                draw.text((home_x, swatch_y - 2), home_str, fill=(220, 220, 220), font=font_small)
                draw.text((away_x, swatch_y - 2), away_str, fill=(220, 220, 220), font=font_small)

            # Final totals
            total_y = height - 24
            draw.text((home_center[0] - 60, total_y), f"Total: {self._fmt_money_short(total_home_val)}", fill=(255, 255, 255), font=font_label)
            draw.text((away_center[0] - 60, total_y), f"Total: {self._fmt_money_short(total_away_val)}", fill=(255, 255, 255), font=font_label)

            bio = BytesIO()
            img.save(bio, "PNG")
            bio.seek(0)
            return (bio, "chart_war_cost_pies.png")
        except Exception as e:
            try:
                self.logger.error(f"Failed to generate war cost pie chart: {e}", exc_info=True)
            except Exception:
                pass
            return None

    # ---------------------------
    # Embed builder
    # ---------------------------
    async def _build_wars_embed(
        self,
        attackers_name: str,
        defenders_name: str,
        wars: List[Dict[str, Any]],
        home_ids: List[int],
        away_ids: List[int],
        guild: Optional[discord.Guild]
    ) -> Tuple[discord.Embed, List[discord.File]]:
        """Build the embed and chart for war costs."""
        files: List[discord.File] = []
        e = discord.Embed(title=f"War Costs: {attackers_name} vs {defenders_name}", color=discord.Color.dark_red())

        # Get emoji maps
        emj = self._build_emoji_map_for_guild(guild)
        mil_emj = emoji_mod.military_codes()

        # Aggregate stats
        home_stats = self._new_war_stats_aggregate()
        away_stats = self._new_war_stats_aggregate()

        for war in wars or []:
            try:
                att_id = int(war.get('attacker_alliance_id') or 0)
                def_id = int(war.get('defender_alliance_id') or 0)
            except Exception:
                continue

            # Determine if this war is Home->Away or Away->Home
            is_home_attacker = att_id in home_ids and def_id in away_ids
            is_away_attacker = att_id in away_ids and def_id in home_ids

            if is_home_attacker:
                self._accumulate_war_stats(home_stats, war, 'attacker')
                self._accumulate_war_stats(away_stats, war, 'defender')
            elif is_away_attacker:
                self._accumulate_war_stats(away_stats, war, 'attacker')
                self._accumulate_war_stats(home_stats, war, 'defender')

        # Fetch market prices for monetary conversion
        price_map = await self._get_price_map()

        # Convert aggregated stats to monetary values
        home_monetary = await self._war_stats_to_monetary(home_stats, price_map)
        away_monetary = await self._war_stats_to_monetary(away_stats, price_map)

        # Prepare data for chart generation
        chart_categories = ["Consumption", "Units", "Infra", "Loot"]
        home_chart_values = [
            home_monetary['res_lost'],
            home_monetary['units_lost'],
            home_monetary['infra_lost'],
            home_monetary['loot_lost']
        ]
        away_chart_values = [
            away_monetary['res_lost'],
            away_monetary['units_lost'],
            away_monetary['infra_lost'],
            away_monetary['loot_lost']
        ]

        # Generate and attach chart
        chart_result = self._generate_war_cost_pies(home_chart_values, away_chart_values, chart_categories)
        if chart_result:
            chart_bio, chart_filename = chart_result
            f = discord.File(chart_bio, filename=chart_filename)
            files.append(f)
            e.set_image(url=f"attachment://{chart_filename}")

        # Format for embed fields
        home_abbr = self._abbr(attackers_name)
        away_abbr = self._abbr(defenders_name)

        # -- Totals Field --
        total_rows = [
            ("Net Gain", self._fmt_money_short(home_monetary['net']), self._fmt_money_short(away_monetary['net'])),
            ("Total Lost", self._fmt_money_short(home_monetary['total_lost']), self._fmt_money_short(away_monetary['total_lost'])),
            ("Loot", self._fmt_money_short(home_monetary['loot_gained']), self._fmt_money_short(away_monetary['loot_gained'])),
        ]
        e.add_field(
            name=f"{mil_emj.get('War', '')} Totals",
            value=self._format_columns(home_abbr, away_abbr, total_rows, include_header=True),
            inline=False
        )

        # -- Losses Breakdown Field --
        losses_rows = [
            (f"{emj.get('STEEL', '')} Res", self._fmt_money_short(home_monetary['res_lost']), self._fmt_money_short(away_monetary['res_lost'])),
            (f"{mil_emj.get('Tank', '')} Units", self._fmt_money_short(home_monetary['units_lost']), self._fmt_money_short(away_monetary['units_lost'])),
            (f"{emj.get('ALUMINUM', '')} Infra", self._fmt_money_short(home_monetary['infra_lost']), self._fmt_money_short(away_monetary['infra_lost'])),
        ]
        e.add_field(
            name=f"{mil_emj.get('Grave', '')} Losses Breakdown",
            value=self._format_columns(home_abbr, away_abbr, losses_rows, include_header=True),
            inline=False
        )

        # -- Units Lost Field --
        units_rows = [
            (f"{mil_emj.get('Soldier', '')} Soldiers", f"{home_stats['units_lost']['soldiers']:,}", f"{away_stats['units_lost']['soldiers']:,}"),
            (f"{mil_emj.get('Tank', '')} Tanks", f"{home_stats['units_lost']['tanks']:,}", f"{away_stats['units_lost']['tanks']:,}"),
            (f"{mil_emj.get('Aircraft', '')} Aircraft", f"{home_stats['units_lost']['aircraft']:,}", f"{away_stats['units_lost']['aircraft']:,}"),
            (f"{mil_emj.get('Ship', '')} Ships", f"{home_stats['units_lost']['ships']:,}", f"{away_stats['units_lost']['ships']:,}"),
        ]
        e.add_field(
            name=f"{mil_emj.get('Casualty', '')} Units Lost",
            value=self._make_unit_columns_block("Unit", home_abbr, away_abbr, units_rows),
            inline=False
        )

        # -- War Stats Field --
        stats_rows = [
            ("Wars Won", f"{home_stats['wars_won']}", f"{away_stats['wars_won']}"),
            ("Wars Lost", f"{away_stats['wars_won']}", f"{home_stats['wars_won']}"), # Mirrored
            ("Avg Imp.", self._fmt_money_short(home_stats['total_infra_destroyed']), self._fmt_money_short(away_stats['total_infra_destroyed'])),
            ("Resistance", f"{home_stats['resistance_total']}", f"{away_stats['resistance_total']}"),
        ]
        e.add_field(
            name=f"{mil_emj.get('Medal', '')} War Stats",
            value=self._make_labeled_columns_block("Stat", home_abbr, away_abbr, stats_rows),
            inline=True
        )

        # -- Loot Stats Field --
        loot_rows = [
            (f"{emj.get('MONEY', '')} Money", self._fmt_money_short(home_stats['loot_gained']['money']), self._fmt_money_short(away_stats['loot_gained']['money'])),
            (f"{emj.get('FOOD', '')} Food", self._fmt_money_short(home_stats['loot_gained']['food']), self._fmt_money_short(away_stats['loot_gained']['food'])),
            (f"{emj.get('OIL', '')} Oil", self._fmt_money_short(home_stats['loot_gained']['oil']), self._fmt_money_short(away_stats['loot_gained']['oil'])),
            (f"{emj.get('URANIUM', '')} Uranium", self._fmt_money_short(home_stats['loot_gained']['uranium']), self._fmt_money_short(away_stats['loot_gained']['uranium'])),
        ]
        e.add_field(
            name=f"{mil_emj.get('Pirate', '')} Loot Stats",
            value=self._make_labeled_columns_block("Loot", home_abbr, away_abbr, loot_rows),
            inline=True
        )

        return e, files

    # ---------------------------
    # Command entry point
    # ---------------------------
    @app_commands.command(name="wars", description="Summarize war costs between two parties.")
    @app_commands.describe(
        attackers="Attacking alliance(s) (IDs or names, comma-separated)",
        defenders="Defending alliance(s) (IDs or names, comma-separated)",
        since="Look back how many days (e.g., 7d, 2w, 1m, 3M). Defaults to 1 month."
    )
    @app_commands.autocomplete(attackers=target_autocomplete, defenders=target_autocomplete)
    async def wars(
        self,
        interaction: discord.Interaction,
        attackers: str,
        defenders: str,
        since: Optional[str] = None
    ):
        """Handler for the /wars command."""
        await interaction.response.defer(thinking=True)
        q = self.query_instance
        if not q:
            await interaction.followup.send("The query service is not available. Please try again later.", ephemeral=True)
            return

        # Step 1: Parse time window
        try:
            cutoff_dt = self.calc_instance.parse_time_window(since or "", default_days=30)
        except ValueError as e:
            await interaction.followup.send(f":warning: Invalid time window: {e}", ephemeral=True)
            return

        # Step 2: Resolve alliance IDs
        attackers_resolved = await self._resolve_targets(attackers)
        defenders_resolved = await self._resolve_targets(defenders)

        attackers_ids = [aid for aid, _ in attackers_resolved if aid is not None]
        defenders_ids = [aid for aid, _ in defenders_resolved if aid is not None]

        if not attackers_ids or not defenders_ids:
            await interaction.followup.send("Could not resolve any valid alliances for both attackers and defenders.", ephemeral=True)
            return

        attackers_name = ", ".join([name for _, name in attackers_resolved if name]) or "Attackers"
        defenders_name = ", ".join([name for _, name in defenders_resolved if name]) or "Defenders"

        # Step 4: Fetch the war data
        wars_between = await q.get_wars_between_parties(
            home_alliance_ids=attackers_ids,
            away_alliance_ids=defenders_ids,
            cutoff_dt=cutoff_dt,
            limit=None,
            active_mode='inactive',
        )

        # Step 5: Build and send the embed
        embed, files = await self._build_wars_embed(
            attackers_name,
            defenders_name,
            wars_between,
            attackers_ids,
            defenders_ids,
            interaction.guild,
        )

        await interaction.followup.send(embed=embed, files=files)

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
