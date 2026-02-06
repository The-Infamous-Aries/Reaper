import discord
from discord import app_commands
from discord.ext import commands

import re
import logging
from typing import Any, Dict, List, Optional, Tuple
from io import BytesIO
import asyncio
import time

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config import PANDW_API_KEY
import aiohttp

from Systems.PnW.Util.calc import AllianceCalculator

from Systems.PnW.Util.query import create_query_instance

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except Exception:
    Image = None
    ImageDraw = None
    ImageFont = None
    PIL_AVAILABLE = False


class CompareCog(commands.Cog):
    """Provides a /compare slash command to compare alliances (DB4D defaults as Home)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.db4d_id = '14635'
        self.query_instance = None
        self._nations_cache: Dict[int, Dict[str, Any]] = {}
        self._cache_ttl_seconds = 3600
        self.calculator = AllianceCalculator()
        try:
            if create_query_instance:
                # Use default API key and this cog's logger
                self.query_instance = create_query_instance(logger=self.logger)
        except Exception as e:
            self.logger.warning(f"compare.py: Failed to init query instance: {e}")

    @staticmethod
    def _normalize_ids(value: Any) -> List[int]:
        """Normalize a config-provided ID or list of IDs to a list of ints.

        Accepts int, str, list/tuple of ints/strs, or comma-separated str.
        Returns a deduplicated list of positive ints.
        """
        ids: List[int] = []
        try:
            if value is None:
                return ids
            # If already a list/tuple, iterate
            if isinstance(value, (list, tuple)):
                for v in value:
                    try:
                        s = str(v).strip()
                        if s.isdigit():
                            ids.append(int(s))
                    except Exception:
                        continue
            else:
                s = str(value).strip()
                # Support comma-separated strings
                parts = [p.strip() for p in s.split(',')] if (',' in s) else [s]
                for p in parts:
                    if p.isdigit():
                        ids.append(int(p))
            # Deduplicate and filter invalid
            ids = sorted({i for i in ids if isinstance(i, int) and i > 0})
            return ids
        except Exception:
            return ids

    # ---------------------------
    # Utilities
    # ---------------------------
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

        # No local name map; fall back to external resolution

        # Unknown name; return the raw string for external resolution
        return (None, s)

    async def _resolve_alliance_id_from_api(self, name_or_acr: str) -> Tuple[Optional[int], Optional[str]]:
        """Resolve an alliance ID by exact name or acronym using the PnW GraphQL API.
        Returns (id, resolved_name) or (None, None) if not found.
        """
        try:
            # Prefer centralized resolver if available
            if self.query_instance:
                try:
                    result = await self.query_instance.resolve_alliance(name_or_acr)
                    if result and result.get('id'):
                        try:
                            return (int(result.get('id')), result.get('name') or name_or_acr)
                        except Exception:
                            return (None, result.get('name') or name_or_acr)
                except Exception:
                    pass

            q_name = (name_or_acr or '').strip()
            if not q_name:
                return (None, None)

            base_url = "https://api.politicsandwar.com/graphql"
            url = f"{base_url}?api_key={PANDW_API_KEY}"
            headers = {"Content-Type": "application/json"}

            # Try exact name match first
            query_name = (
                "query { alliances(name: \"" + q_name.replace("\"", "\\\"") + "\") { data { id name acronym } } }"
            )
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json={'query': query_name}, headers=headers, timeout=20) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            block = (data.get('data') or {}).get('alliances') or {}
                            items = block.get('data') or []
                            if items:
                                item = items[0]
                                aid = int(item.get('id')) if item.get('id') else None
                                nm = item.get('name') or q_name
                                if aid:
                                    return (aid, nm)
            except Exception:
                pass

            # Not found
            return (None, None)
        except Exception as e:
            try:
                self.logger.warning(f"_resolve_alliance_id_from_api: failed to resolve '{name_or_acr}': {e}")
            except Exception:
                pass
            return (None, None)

    async def _resolve_targets(self, text: str) -> List[Tuple[Optional[int], Optional[str]]]:
        """Resolve a comma-separated list of alliance identifiers to IDs via parsing and API lookups."""
        out: List[Tuple[Optional[int], Optional[str]]] = []
        if not text:
            return out
        parts = [p.strip() for p in str(text).split(',') if p.strip()]
        for part in parts:
            aid, name = self._parse_alliance_identifier(part)
            if isinstance(aid, int) and aid > 0:
                out.append((aid, name or f"Alliance {aid}"))
                continue
            # Attempt API resolution by name/acronym
            ra_id, ra_name = await self._resolve_alliance_id_from_api(name or part)
            if isinstance(ra_id, int) and ra_id > 0:
                out.append((ra_id, ra_name or name or part))
            else:
                out.append((None, name or part))
        return out

    def _parse_multiple_targets(self, text: str) -> List[Tuple[Optional[int], Optional[str]]]:
        """Parse comma-separated alliance identifiers into a list of (id, resolved_name)."""
        results: List[Tuple[Optional[int], Optional[str]]] = []
        if not text:
            return results
        parts = [p.strip() for p in str(text).split(',') if p.strip()]
        for part in parts:
            aid, name = self._parse_alliance_identifier(part)
            results.append((aid, name))
        return results

    async def _get_alliance_nations(self, alliance_id: int, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Fetch nations for an alliance using 1-hour TTL cache; fallback to AllianceManager cog."""
        try:
            now = time.time()
            cached = self._nations_cache.get(int(alliance_id))
            if cached and not force_refresh and (now - (cached.get('ts') or 0) < self._cache_ttl_seconds):
                return cached.get('nations') or []
            nations: List[Dict[str, Any]] = []
            if self.query_instance:
                fetch_fresh = force_refresh or (cached is None) or (now - (cached.get('ts') or 0) >= self._cache_ttl_seconds)
                nations = await self.query_instance.get_alliance_nations(str(alliance_id), bot=self.bot, force_refresh=fetch_fresh) or []
                self._nations_cache[int(alliance_id)] = {'ts': now, 'nations': nations}
                return nations
            # Fallback to AllianceManager cog
            alliance_cog = self.bot.get_cog('AllianceManager')
            if alliance_cog and hasattr(alliance_cog, 'get_alliance_nations'):
                nations_raw = await alliance_cog.get_alliance_nations(str(alliance_id), force_refresh=force_refresh) or []
                self._nations_cache[int(alliance_id)] = {'ts': now, 'nations': nations_raw}
                return nations_raw
        except Exception as e:
            self.logger.warning(f"_get_alliance_nations: error for {alliance_id}: {e}")
        return []

    async def _get_nations_batched_cached(self, ids: List[int], side_label: str) -> Dict[int, List[Dict[str, Any]]]:
        """Fetch nations for multiple alliance IDs, using 1-hour TTL cache and batched API when needed."""
        now = time.time()
        out: Dict[int, List[Dict[str, Any]]] = {}
        to_fetch: List[int] = []
        for aid in ids or []:
            cached = self._nations_cache.get(int(aid))
            if cached and (now - (cached.get('ts') or 0) < self._cache_ttl_seconds):
                out[int(aid)] = cached.get('nations') or []
            else:
                to_fetch.append(int(aid))
        if to_fetch and self.query_instance and hasattr(self.query_instance, 'get_alliances_nations_batched'):
            try:
                fetched = await self.query_instance.get_alliances_nations_batched(
                    to_fetch, side_label=side_label, bot=self.bot, force_refresh=True
                ) or {}
                for aid in to_fetch:
                    nations = fetched.get(int(aid)) or []
                    self._nations_cache[int(aid)] = {'ts': now, 'nations': nations}
                    out[int(aid)] = nations
            except Exception as e:
                self.logger.warning(f"_get_nations_batched_cached: batched fetch failed: {e}")
                for aid in to_fetch:
                    out[int(aid)] = await self._get_alliance_nations(int(aid), force_refresh=True)
        return out

    def _get_active_nations(self, nations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter nations to return only active ones (not in VM, not Applicant)."""
        active = []
        for n in nations:
            vm_turns = int(n.get('vacation_mode_turns', 0) or 0)
            position = str(n.get('alliance_position', '') or '').upper()
            if vm_turns == 0 and position != 'APPLICANT':
                active.append(n)
        return active

    async def _compute_stats(self, nations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute alliance statistics using AllianceCalculator, filtering to active nations."""
        active = self._get_active_nations(nations or [])
        try:
            return await self.calculator.calculate_alliance_statistics(active)
        except Exception as e:
            self.logger.warning(f"_compute_stats: failed: {e}")
            return {
                'total_nations': len(active),
                'total_score': 0,
                'total_cities': 0,
                'avg_score': 0,
                'avg_cities': 0,
                'total_military': {
                    'soldiers': 0, 'tanks': 0, 'aircraft': 0, 'ships': 0, 'missiles': 0, 'nukes': 0
                }
            }

    async def _compute_full_mill(self, nations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute full military data (current, daily, max, days) for active nations."""
        try:
            active = self._get_active_nations(nations or [])
            return await self.calculator.calculate_full_mill_data(active)
        except Exception as e:
            self.logger.warning(f"_compute_full_mill: failed: {e}")
            return {
                'daily_soldiers': 0,
                'daily_tanks': 0,
                'daily_aircraft': 0,
                'daily_ships': 0,
                'daily_missiles': 0,
                'daily_nukes': 0,
                'current_soldiers': 0,
                'current_tanks': 0,
                'current_aircraft': 0,
                'current_ships': 0,
                'current_missiles': 0,
                'current_nukes': 0,
            }

    def _format_city_buckets(self, buckets: List[Tuple[str, int]]) -> str:
        """Format city bucket counts into a readable multiline string."""
        return "\n".join([f"{label}: {count}" for label, count in buckets])

    def _format_military_inline(self, stats: Dict[str, Any]) -> str:
        """Format military totals using the same emojis as alliance.py."""
        tm = stats.get('total_military', {}) or {}
        return (
            f"🪖: {tm.get('soldiers', 0):,}\n"
            f"🚙: {tm.get('tanks', 0):,}\n"
            f"🛩️: {tm.get('aircraft', 0):,}\n"
            f"⚓: {tm.get('ships', 0):,}\n"
            f"🚀: {tm.get('missiles', 0):,}\n"
            f"☢️: {tm.get('nukes', 0):,}"
        )

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

    def _make_labeled_columns_block(self, label_header: str, left_header: str, right_header: str, rows: List[Tuple[str, str, str]]) -> str:
        """Render a three-column monospaced block: Label | Left | Right with fixed widths.
        Optimized for mobile: narrower max widths to reduce line wrapping.
        rows: list of (label, left_value, right_value)
        """
        # Compute widths based on actual content
        label_width = max([len(label_header)] + [len(lbl) for lbl, _, _ in rows])
        left_width = max([len(left_header)] + [len(val) for _, val, _ in rows])
        right_width = max([len(right_header)] + [len(val) for _, _, val in rows])

        # Mobile-friendly caps to keep total line length reasonable
        label_width = max(6, min(label_width, 10))
        left_width = max(8, min(left_width, 14))
        right_width = max(8, min(right_width, 14))

        # Build lines
        lines = []
        lines.append(
            f"{label_header.ljust(label_width)} | {left_header.rjust(left_width)} | {right_header.rjust(right_width)}"
        )
        for label, left, right in rows:
            lines.append(
                f"{label.ljust(label_width)} | {left.rjust(left_width)} | {right.rjust(right_width)}"
            )
        return "```" + "\n".join(lines) + "```"

    def _make_unit_columns_block(self, label_header: str, left_header: str, right_header: str, rows: List[Tuple[str, str, str]]) -> str:
        """Render a compact three-column monospaced block for unit rows.
        Matches spacing style of other labeled column fields (Totals/Cities).
        """
        # Compute widths based on content, then cap to keep layout tight
        label_width = max([len(label_header)] + [len(lbl or "") for lbl, _, _ in rows])
        left_width = max([len(left_header)] + [len(val or "") for _, val, _ in rows])
        right_width = max([len(right_header)] + [len(val or "") for _, _, val in rows])

        # Use same caps philosophy as _make_labeled_columns_block for consistency
        label_width = max(4, min(label_width, 8))
        left_width = max(8, min(left_width, 12))
        right_width = max(8, min(right_width, 12))

        lines: List[str] = []
        lines.append(
            f"{label_header.ljust(label_width)} | {left_header.rjust(left_width)} | {right_header.rjust(right_width)}"
        )
        for label, left, right in rows:
            lbl = (label + " ") if label else label
            lines.append(
                f"{(lbl or '').ljust(label_width)} | {left.rjust(left_width)} | {right.rjust(right_width)}"
            )
        return "```" + "\n".join(lines) + "```"

    def _make_comparison_embed(
        self,
        target_name: str,
        target_stats: Dict[str, Any],
        target_buckets: List[Tuple[str, int]],
        against_name: str,
        against_stats: Dict[str, Any],
        against_buckets: List[Tuple[str, int]],
        target_mill: Dict[str, Any],
        against_mill: Dict[str, Any],
        left_hdr: Optional[str] = None,
        right_hdr: Optional[str] = None,
        parties_home: Optional[List[str]] = None,
        parties_away: Optional[List[str]] = None
    ) -> discord.Embed:
        """Create a comparison embed with three categories:
        1) Totals (Total Nations and Score)
        2) City Distribution (by city count ranges)
        3) Military Comparison (per unit with emojis)
        4) Daily Purchases (per unit with emojis)
        """
        embed = discord.Embed(
            title="Alliance Comparison",
            description=f"Comparing {target_name} vs {against_name}",
            color=discord.Color.blurple()
        )

        # Headers (override if provided); use Home/Away by default
        left_hdr = left_hdr or "Home"
        right_hdr = right_hdr or "Away"

        # Optional Parties field listed first when multiple alliances exist on either side
        if (parties_home or []) or (parties_away or []):
            home_list = parties_home or []
            away_list = parties_away or []
            if len(home_list) > 1 or len(away_list) > 1:
                parties_value = (
                    f"Home: {', '.join(home_list) if home_list else '—'}\n"
                    f"Away: {', '.join(away_list) if away_list else '—'}"
                )
                embed.add_field(name="🏛️ Parties", value=parties_value, inline=False)

        # 1) Totals: show in one category (field) with labeled columns
        # Format score without decimals
        t_score = float(target_stats.get('total_score', 0) or 0)
        a_score = float(against_stats.get('total_score', 0) or 0)
        totals_rows = [
            ("Nations", f"{target_stats.get('total_nations', 0):,}", f"{against_stats.get('total_nations', 0):,}"),
            ("Score", f"{t_score:,.0f}", f"{a_score:,.0f}")
        ]
        totals_block = self._make_labeled_columns_block("Stat", left_hdr, right_hdr, totals_rows)
        embed.add_field(name="📊 Totals", value=totals_block, inline=False)

        # 2) City Distribution: break down totals by city count ranges
        city_rows = []
        # buckets aligned by label order
        for (label_t, count_t), (label_a, count_a) in zip(target_buckets, against_buckets):
            # Include only ranges where at least one alliance has 1 or more
            if (count_t or 0) > 0 or (count_a or 0) > 0:
                city_rows.append((label_t, f"{count_t}", f"{count_a}"))
        city_block = self._make_labeled_columns_block("Cities", left_hdr, right_hdr, city_rows)
        embed.add_field(name="🏙️ City Distribution", value=city_block, inline=False)

        # 3) Military Comparison: use same emojis as alliance.py
        tm_a = target_stats.get('total_military', {}) or {}
        tm_b = against_stats.get('total_military', {}) or {}
        mil_rows = [
            ("🪖", f"{tm_a.get('soldiers', 0):,}", f"{tm_b.get('soldiers', 0):,}"),
            ("🚙", f"{tm_a.get('tanks', 0):,}", f"{tm_b.get('tanks', 0):,}"),
            ("🛩️", f"{tm_a.get('aircraft', 0):,}", f"{tm_b.get('aircraft', 0):,}"),
            ("⚓", f"{tm_a.get('ships', 0):,}", f"{tm_b.get('ships', 0):,}"),
            ("🚀", f"{tm_a.get('missiles', 0):,}", f"{tm_b.get('missiles', 0):,}"),
            ("☢️", f"{tm_a.get('nukes', 0):,}", f"{tm_b.get('nukes', 0):,}")
        ]
        mil_block = self._make_unit_columns_block("Unit", left_hdr, right_hdr, mil_rows)
        embed.add_field(name="⚔️ Current Military", value=mil_block, inline=False)

        # 4) Daily Purchases: show daily purchase capacity per unit
        dm_a = target_mill or {}
        dm_b = against_mill or {}
        daily_rows = [
            ("🪖", f"{int(dm_a.get('daily_soldiers', 0)):,}", f"{int(dm_b.get('daily_soldiers', 0)):,}"),
            ("🚙", f"{int(dm_a.get('daily_tanks', 0)):,}", f"{int(dm_b.get('daily_tanks', 0)):,}"),
            ("🛩️", f"{int(dm_a.get('daily_aircraft', 0)):,}", f"{int(dm_b.get('daily_aircraft', 0)):,}"),
            ("⚓", f"{int(dm_a.get('daily_ships', 0)):,}", f"{int(dm_b.get('daily_ships', 0)):,}"),
            ("🚀", f"{int(dm_a.get('daily_missiles', 0)):,}", f"{int(dm_b.get('daily_missiles', 0)):,}"),
            ("☢️", f"{int(dm_a.get('daily_nukes', 0)):,}", f"{int(dm_b.get('daily_nukes', 0)):,}")
        ]
        daily_block = self._make_unit_columns_block("Daily", left_hdr, right_hdr, daily_rows)
        embed.add_field(name="🔁 Daily Purchases", value=daily_block, inline=False)

        embed.set_footer(text="Use /compare to refresh | Data excludes VM & applicants")
        return embed

    # ---------------------------
    # Chart generation (PIL)
    # ---------------------------
    def _get_font(self, size: int = 16) -> Optional[Any]:
        if not PIL_AVAILABLE:
            return None
        # Try to load emoji-capable font on Windows
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

    def _generate_bar_chart(self, title: str, labels: List[str], a_counts: List[int], b_counts: List[int], a_name: str, b_name: str) -> Optional[Tuple[BytesIO, str]]:
        if not PIL_AVAILABLE or not labels:
            return None
        try:
            # Dimensions - increased spacing to prevent overlapping
            width = 900
            bar_h = 16  # Slightly smaller bars
            gap = 6     # Increased gap between bars
            row_h = bar_h * 2 + gap + 20  # More space for each row
            top_pad = 50
            left_pad = 140
            right_pad = 40
            bottom_pad = 40
            height = top_pad + bottom_pad + max(1, len(labels)) * row_h

            img = Image.new("RGB", (width, height), (26, 26, 26))
            draw = ImageDraw.Draw(img)
            font_title = self._get_font(20)
            font_label = self._get_font(16)
            font_small = self._get_font(14)

            # Title
            draw.text((left_pad, 15), title, fill=(255, 255, 255), font=font_title)
            # Legend
            draw.rectangle([width - 320, 12, width - 310, 22], fill=(46, 134, 222))
            draw.text((width - 305, 10), f"{a_name}", fill=(220, 220, 220), font=font_small)
            draw.rectangle([width - 200, 12, width - 190, 22], fill=(230, 126, 34))
            draw.text((width - 185, 10), f"{b_name}", fill=(220, 220, 220), font=font_small)

            max_val = max([0] + a_counts + b_counts)
            usable_w = width - left_pad - right_pad
            scale = (usable_w - 60) / max_val if max_val > 0 else 1.0

            # Draw bars with proper spacing
            for idx, lbl in enumerate(labels):
                y = top_pad + idx * row_h
                a_val = int(a_counts[idx] or 0)
                b_val = int(b_counts[idx] or 0)
                # Label
                draw.text((10, y + 2), lbl, fill=(220, 220, 220), font=font_label)
                # Bars
                a_w = int(a_val * scale)
                b_w = int(b_val * scale)
                # A bar (top)
                draw.rectangle([left_pad, y, left_pad + a_w, y + bar_h], fill=(46, 134, 222))
                # B bar (bottom with gap)
                draw.rectangle([left_pad, y + bar_h + gap, left_pad + b_w, y + bar_h + gap + bar_h], fill=(230, 126, 34))
                # Values
                draw.text((left_pad + a_w + 6, y), f"{a_val}", fill=(200, 200, 200), font=font_small)
                draw.text((left_pad + b_w + 6, y + bar_h + gap), f"{b_val}", fill=(200, 200, 200), font=font_small)

            # Output
            bio = BytesIO()
            img.save(bio, format="PNG")
            bio.seek(0)
            return bio, f"chart_{re.sub(r'[^a-z0-9]+', '_', title.lower())}.png"
        except Exception:
            return None

    def _generate_city_chart(self, city_rows: List[Tuple[str, str, str]], a_name: str, b_name: str, include_title: bool = True, include_legend: bool = True) -> Optional[Tuple[BytesIO, str]]:
        # Vertical bar chart: ranges along X-axis, counts as vertical bars
        if not PIL_AVAILABLE or not city_rows:
            return None
        try:
            labels = [r[0] for r in city_rows]
            a_counts = [int(r[1]) for r in city_rows]
            b_counts = [int(r[2]) for r in city_rows]

            # Dimensions
            width = 900
            # Adjust top padding depending on whether title/legend are included
            top_pad = 60 if (include_title or include_legend) else 24
            left_pad = 70
            right_pad = 40
            bottom_pad = 90  # space for horizontal labels
            height = 460

            img = Image.new("RGB", (width, height), (26, 26, 26))
            draw = ImageDraw.Draw(img)
            font_title = self._get_font(20)
            font_axis = self._get_font(14)
            font_small = self._get_font(14)

            # Title
            if include_title:
                draw.text((left_pad, 15), "City Distribution", fill=(255, 255, 255), font=font_title)
            # Legend
            if include_legend:
                draw.rectangle([width - 320, 12, width - 310, 22], fill=(46, 134, 222))
                draw.text((width - 305, 10), f"{a_name}", fill=(220, 220, 220), font=font_small)
                draw.rectangle([width - 200, 12, width - 190, 22], fill=(231, 76, 60))
                draw.text((width - 185, 10), f"{b_name}", fill=(220, 220, 220), font=font_small)

            # Scaling
            max_val = max([0] + a_counts + b_counts)
            usable_h = height - top_pad - bottom_pad
            scale = usable_h / max_val if max_val > 0 else 1.0

            # X-axis layout
            usable_w = width - left_pad - right_pad
            n = max(1, len(labels))
            step = int(usable_w / n)
            bar_w = max(10, min(22, step // 3))
            x0 = left_pad
            y_base = height - bottom_pad

            # Axis line
            draw.line([left_pad, y_base, width - right_pad, y_base], fill=(200, 200, 200), width=1)

            for i, lbl in enumerate(labels):
                cx = x0 + i * step + step // 2
                # A and B bar x positions (side-by-side)
                ax = cx - bar_w - 2
                bx = cx + 2
                # Heights
                a_h = int((a_counts[i] or 0) * scale)
                b_h = int((b_counts[i] or 0) * scale)
                # Bars
                if a_h > 0:
                    draw.rectangle([ax, y_base - a_h, ax + bar_w, y_base], fill=(46, 134, 222))
                if b_h > 0:
                    draw.rectangle([bx, y_base - b_h, bx + bar_w, y_base], fill=(231, 76, 60))
                # Values above bars
                if a_h > 0:
                    a_txt = f"{a_counts[i]}"
                    atw = int(draw.textlength(a_txt, font=font_small))
                    draw.text((ax + (bar_w - atw) // 2, max(top_pad + 4, y_base - a_h - 16)), a_txt, fill=(220, 220, 220), font=font_small)
                if b_h > 0:
                    b_txt = f"{b_counts[i]}"
                    btw = int(draw.textlength(b_txt, font=font_small))
                    draw.text((bx + (bar_w - btw) // 2, max(top_pad + 4, y_base - b_h - 16)), b_txt, fill=(220, 220, 220), font=font_small)
                # X-axis labels (city ranges), horizontally along the axis
                l_tw = int(draw.textlength(lbl, font=font_axis))
                draw.text((cx - l_tw // 2, y_base + 8), lbl, fill=(220, 220, 220), font=font_axis)

            # Output
            bio = BytesIO()
            img.save(bio, format="PNG")
            bio.seek(0)
            return bio, "chart_city_distribution.png"
        except Exception:
            return None

    def _generate_military_chart(self, mill_a: Dict[str, Any], mill_b: Dict[str, Any], a_name: str, b_name: str, include_title: bool = True, include_legend: bool = True) -> Optional[Tuple[BytesIO, str]]:
        # Render vertical grouped bars per unit (4 bars per unit):
        # [Home Current, Away Current, Home Daily, Away Daily]
        # Bars for a unit are tightly grouped; gap between units.
        if not PIL_AVAILABLE:
            return None
        try:
            # Show six unit types with word labels (emojis not reliable in images)
            labels = ["Soldiers", "Tanks", "Aircraft", "Ships", "Missiles", "Nukes"]
            a_daily = [
                int(mill_a.get('daily_soldiers', 0) or 0),
                int(mill_a.get('daily_tanks', 0) or 0),
                int(mill_a.get('daily_aircraft', 0) or 0),
                int(mill_a.get('daily_ships', 0) or 0),
                int(mill_a.get('daily_missiles', 0) or 0),
                int(mill_a.get('daily_nukes', 0) or 0),
            ]
            b_daily = [
                int(mill_b.get('daily_soldiers', 0) or 0),
                int(mill_b.get('daily_tanks', 0) or 0),
                int(mill_b.get('daily_aircraft', 0) or 0),
                int(mill_b.get('daily_ships', 0) or 0),
                int(mill_b.get('daily_missiles', 0) or 0),
                int(mill_b.get('daily_nukes', 0) or 0),
            ]
            a_current = [
                int(mill_a.get('current_soldiers', 0) or 0),
                int(mill_a.get('current_tanks', 0) or 0),
                int(mill_a.get('current_aircraft', 0) or 0),
                int(mill_a.get('current_ships', 0) or 0),
                int(mill_a.get('current_missiles', 0) or 0),
                int(mill_a.get('current_nukes', 0) or 0),
            ]
            b_current = [
                int(mill_b.get('current_soldiers', 0) or 0),
                int(mill_b.get('current_tanks', 0) or 0),
                int(mill_b.get('current_aircraft', 0) or 0),
                int(mill_b.get('current_ships', 0) or 0),
                int(mill_b.get('current_missiles', 0) or 0),
                int(mill_b.get('current_nukes', 0) or 0),
            ]
            a_max = [
                int(mill_a.get('max_soldiers', 0) or 0),
                int(mill_a.get('max_tanks', 0) or 0),
                int(mill_a.get('max_aircraft', 0) or 0),
                int(mill_a.get('max_ships', 0) or 0),
                int(mill_a.get('max_missiles', 0) or 0),
                int(mill_a.get('max_nukes', 0) or 0),
            ]
            b_max = [
                int(mill_b.get('max_soldiers', 0) or 0),
                int(mill_b.get('max_tanks', 0) or 0),
                int(mill_b.get('max_aircraft', 0) or 0),
                int(mill_b.get('max_ships', 0) or 0),
                int(mill_b.get('max_missiles', 0) or 0),
                int(mill_b.get('max_nukes', 0) or 0),
            ]

            # Dimensions (vertical layout similar to city chart)
            width = 900
            # Adjust top padding depending on whether title/legend are included
            top_pad = 60 if (include_title or include_legend) else 24
            left_pad = 70
            right_pad = 40
            bottom_pad = 120  # space for unit labels under grouped bars
            height = 520

            img = Image.new("RGB", (width, height), (26, 26, 26))
            draw = ImageDraw.Draw(img)
            font_title = self._get_font(20)
            font_axis = self._get_font(14)
            font_small = self._get_font(12)
            font_bar = self._get_font(12)

            # Colors: Blue for Home (A), Red for Away (B)
            A_COLOR = (46, 134, 222)
            B_COLOR = (231, 76, 60)
            WHITE = (255, 255, 255)
            GREY = (220, 220, 220)

            # Title
            if include_title:
                draw.text((left_pad, 15), "Units: Current & Daily", fill=WHITE, font=font_title)
            # Legend
            if include_legend:
                draw.rectangle([width - 320, 12, width - 310, 22], fill=A_COLOR)
                draw.text((width - 305, 10), f"{a_name}", fill=GREY, font=font_small)
                draw.rectangle([width - 200, 12, width - 190, 22], fill=B_COLOR)
                draw.text((width - 185, 10), f"{b_name}", fill=GREY, font=font_small)

            # Scaling height per cluster dynamically
            usable_h = height - top_pad - bottom_pad

            # X-axis layout: grouped bars per unit
            usable_w = width - left_pad - right_pad
            group_count = max(1, len(labels))
            step = int(usable_w / group_count)
            # Bars tight within group; small gap between bars, larger gap between groups
            bar_w = 22
            bar_gap = 4
            group_gap = max(16, step - (bar_w * 4 + bar_gap * 3))
            x0 = left_pad
            y_base = height - bottom_pad

            # Axis line
            draw.line([left_pad, y_base, width - right_pad, y_base], fill=(200, 200, 200), width=1)

            # Helper to paste vertical text onto bars
            def paste_vertical_text(text: str, rect: Tuple[int, int, int, int], color: Tuple[int, int, int], font: ImageFont.FreeTypeFont):
                bx1, by1, bx2, by2 = rect
                bar_h = by2 - by1
                # Create text image
                tw = int(draw.textlength(text, font=font))
                th = font.getbbox(text)[3] - font.getbbox(text)[1]
                tx_img = Image.new("RGBA", (tw + 4, th + 4), (0, 0, 0, 0))
                tx_draw = ImageDraw.Draw(tx_img)
                tx_draw.text((2, 2), text, fill=color + (255,), font=font)
                rot = tx_img.rotate(90, expand=True)
                # Center on bar; if bar too short, place just above the bar
                cx = (bx1 + bx2) // 2
                cy = (by1 + by2) // 2
                px = int(cx - rot.width / 2)
                py = int(cy - rot.height / 2)
                if bar_h < rot.height + 4:
                    py = by1 - rot.height - 2
                    py = max(py, top_pad + 2)
                img.paste(rot, (px, py), rot)

            for i, lbl in enumerate(labels):
                # Values
                a_c = int(mill_a.get('current_' + lbl.lower(), 0) or 0)
                b_c = int(mill_b.get('current_' + lbl.lower(), 0) or 0)
                a_d = int(mill_a.get('daily_' + lbl.lower(), 0) or 0)
                b_d = int(mill_b.get('daily_' + lbl.lower(), 0) or 0)

                # Scale all four bars to the unit group's maximum
                g_max = max(a_c, b_c, a_d, b_d, 1)
                scale = usable_h / g_max if g_max > 0 else 1.0

                # Group center and left start
                gx = x0 + i * step + step // 2
                group_w = bar_w * 4 + bar_gap * 3
                gl = gx - group_w // 2

                # Bar x positions within the group (tight together)
                ax_cur_l = gl
                bx_cur_l = gl + bar_w + bar_gap
                ax_day_l = gl + (bar_w + bar_gap) * 2
                bx_day_l = gl + (bar_w + bar_gap) * 3

                # Bar heights
                a_ch = int(a_c * scale)
                b_ch = int(b_c * scale)
                a_dh = int(a_d * scale)
                b_dh = int(b_d * scale)

                # Draw bars
                rects = []
                # Home Current
                rects.append((ax_cur_l, y_base - a_ch, ax_cur_l + bar_w, y_base, A_COLOR, f"Cur {a_c:,}"))
                # Away Current
                rects.append((bx_cur_l, y_base - b_ch, bx_cur_l + bar_w, y_base, B_COLOR, f"Cur {b_c:,}"))
                # Home Daily
                rects.append((ax_day_l, y_base - a_dh, ax_day_l + bar_w, y_base, A_COLOR, f"Day {a_d:,}"))
                # Away Daily
                rects.append((bx_day_l, y_base - b_dh, bx_day_l + bar_w, y_base, B_COLOR, f"Day {b_d:,}"))

                for (x1, y1, x2, y2, color, text) in rects:
                    if y2 - y1 > 0:
                        draw.rectangle([x1, y1, x2, y2], fill=color)
                        paste_vertical_text(text, (x1, y1, x2, y2), GREY, font_bar)

                # Unit label shown once centered under the 4 bars
                unit_tw = int(draw.textlength(lbl, font=font_axis))
                draw.text((gx - unit_tw // 2, y_base + 10), lbl, fill=GREY, font=font_axis)

            bio = BytesIO()
            img.save(bio, format="PNG")
            bio.seek(0)
            return bio, f"chart_military_tug_of_war.png"
        except Exception:
            return None

    def _combine_charts_sync(self, bio_city: BytesIO, bio_mil: BytesIO) -> Optional[BytesIO]:
        """Combine city and military charts into one image vertically (Sync)."""
        if not PIL_AVAILABLE:
            return None
        try:
            img_city = Image.open(bio_city).convert("RGB")
            img_mil = Image.open(bio_mil).convert("RGB")
            # Add a unified header area with single title & legend
            header_h = 48
            combined_w = max(img_city.width, img_mil.width)
            combined_h = header_h + img_city.height + img_mil.height + 16
            combined = Image.new("RGB", (combined_w, combined_h), (26, 26, 26))
            draw_c = ImageDraw.Draw(combined)
            font_title = self._get_font(20)
            font_small = self._get_font(14)

            # Unified title and legend (Home/Away colors)
            draw_c.text((16, 12), "City Distribution & Military Comparison", fill=(255, 255, 255), font=font_title)
            A_COLOR = (46, 134, 222)
            B_COLOR = (231, 76, 60)
            # Legend on the right
            draw_c.rectangle([combined_w - 300, 14, combined_w - 290, 24], fill=A_COLOR)
            draw_c.text((combined_w - 285, 12), "Home", fill=(220, 220, 220), font=font_small)
            draw_c.rectangle([combined_w - 200, 14, combined_w - 190, 24], fill=B_COLOR)
            draw_c.text((combined_w - 185, 12), "Away", fill=(220, 220, 220), font=font_small)

            # Paste city below header, then military below with spacing
            combined.paste(img_city, (0, header_h))
            combined.paste(img_mil, (0, header_h + img_city.height + 16))
            # Save combined
            bio_combined = BytesIO()
            combined.save(bio_combined, format="PNG")
            bio_combined.seek(0)
            return bio_combined
        except Exception:
            return None

    # ---------------------------
    # Autocomplete for target alliance
    # ---------------------------
    async def target_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        try:
            cur = (current or '').strip()
            if not cur:
                # Offer DB4D default when empty
                return [app_commands.Choice(name="Death Before Dishonor (DB4D)", value=self.db4d_id)]

            choices: List[app_commands.Choice[str]] = []

            # Numeric or link: suggest parsed ID
            aid, _ = self._parse_alliance_identifier(cur)
            if isinstance(aid, int):
                choices.append(app_commands.Choice(name=f"Alliance ID {aid}", value=str(aid)))

            # Suggest DB4D by name/acronym if typed
            cur_lower = cur.lower()
            if ("db4d" in cur_lower) or ("death before dishonor".startswith(cur_lower)):
                choices.append(app_commands.Choice(name="Death Before Dishonor (DB4D)", value="Death Before Dishonor"))

            return choices[:25]
        except Exception:
            return []

    # ---------------------------
    # Slash Command: /compare
    # ---------------------------
    @app_commands.describe(
        home="Alliance names or IDs/links for Home (comma-separated). Defaults to DB4D.",
        away="Alliance names or IDs/links for Away (comma-separated)"
    )
    @app_commands.command(name="compare", description="Compare Home vs Away parties")
    async def compare(self, interaction: discord.Interaction, home: Optional[str], away: str):
        try:
            await interaction.response.defer(thinking=True)
            # Resolve Home alliances
            if not home or not str(home).strip():
                parsed_home = [(int(self.db4d_id), "Death Before Dishonor")]
            else:
                parsed_home = await self._resolve_targets(home)
            valid_home = [(aid, name) for aid, name in parsed_home if isinstance(aid, int) and aid > 0]
            if not valid_home:
                await interaction.followup.send("❌ Could not resolve any Home alliances. Provide IDs, links, or known names, or leave blank to default to DB4D.")
                return

            # Resolve Away alliances
            parsed_away = await self._resolve_targets(away)
            valid_away = [(aid, name) for aid, name in parsed_away if isinstance(aid, int) and aid > 0]
            if not valid_away:
                await interaction.followup.send("❌ Could not resolve any Away alliances. Provide IDs, links, or known names.")
                return

            # Fetch nations for Home via single batched query
            home_names_list: List[str] = [name or f"Alliance {aid}" for aid, name in valid_home]
            home_ids: List[int] = [int(aid) for aid, _ in valid_home]
            home_batched: Dict[int, List[Dict[str, Any]]] = await self._get_nations_batched_cached(home_ids, side_label='home')

            # Aggregate and dedupe from batched result
            home_map: Dict[int, Dict[str, Any]] = {}
            for aid in home_ids:
                for n in home_batched.get(aid, []) or []:
                    try:
                        nid = int(n.get('id') or 0)
                    except Exception:
                        nid = None
                    if nid and nid not in home_map:
                        home_map[nid] = n
            home_nations = list(home_map.values())
            
            if not home_nations:
                await interaction.followup.send("❌ No nation data found for Home alliances.")
                return

            # Fetch nations for Away via single batched query
            away_names_list: List[str] = [name or f"Alliance {aid}" for aid, name in valid_away]
            away_ids: List[int] = [int(aid) for aid, _ in valid_away]
            away_batched: Dict[int, List[Dict[str, Any]]] = await self._get_nations_batched_cached(away_ids, side_label='away')

            away_map: Dict[int, Dict[str, Any]] = {}
            for aid in away_ids:
                for n in away_batched.get(aid, []) or []:
                    try:
                        nid = int(n.get('id') or 0)
                    except Exception:
                        nid = None
                    if nid and nid not in away_map:
                        away_map[nid] = n
            away_nations = list(away_map.values())

            if not away_nations:
                await interaction.followup.send("❌ No nation data found for Away alliances.")
                return

            # Compute stats and full military data for Home/Away
            home_stats = await self._compute_stats(home_nations)
            away_stats = await self._compute_stats(away_nations)
            home_mill = await self._compute_full_mill(home_nations)
            away_mill = await self._compute_full_mill(away_nations)

            # Compute buckets
            home_buckets = await self.calculator.bucket_city_counts(home_nations)
            away_buckets = await self.calculator.bucket_city_counts(away_nations)

            # Persistence of aggregated Home/Away parties is handled by batched query (war_party_home/away)

            # Build Parties lists for embed
            home_list: List[str] = home_names_list
            away_list: List[str] = away_names_list

            # Build embed using Home/Away labels and data mapping
            embed = self._make_comparison_embed(
                "Home",
                home_stats,
                home_buckets,
                "Away",
                away_stats,
                away_buckets,
                home_mill,
                away_mill,
                left_hdr="Home",
                right_hdr="Away",
                parties_home=home_list,
                parties_away=away_list,
            )

            # Generate charts and attach as files
            files = []
            try:
                # Prepare city_rows consistent with filtered view
                # Use Home/Away buckets for chart generation
                # buckets already computed above
                city_rows = []
                for (label_t, count_t), (label_a, count_a) in zip(home_buckets, away_buckets):
                    if (count_t or 0) > 0 or (count_a or 0) > 0:
                        city_rows.append((label_t, f"{count_t}", f"{count_a}"))

                # Generate charts content-only (no titles/legends) when both are present
                city_chart = None
                if city_rows:
                    city_chart = await asyncio.to_thread(
                        self._generate_city_chart, 
                        city_rows, 
                        "Home", 
                        "Away", 
                        include_title=False, 
                        include_legend=False
                    )

                mil_chart = await asyncio.to_thread(
                    self._generate_military_chart, 
                    home_mill, 
                    away_mill, 
                    "Home", 
                    "Away", 
                    include_title=False, 
                    include_legend=False
                )

                # If both charts exist, combine them into one stacked image and attach to the single embed
                if city_chart and mil_chart and PIL_AVAILABLE:
                    bio_city, fname_city = city_chart
                    bio_mil, fname_mil = mil_chart
                    try:
                        bio_combined = await asyncio.to_thread(self._combine_charts_sync, bio_city, bio_mil)
                        if bio_combined:
                            fname_combined = "chart_compare_city_military.png"
                            files.append(discord.File(bio_combined, filename=fname_combined))
                            embed.set_image(url=f"attachment://{fname_combined}")
                        else:
                            raise Exception("Combination returned None")
                    except Exception:
                        # Fallback to attaching separately if combination fails
                        files.append(discord.File(bio_city, filename=fname_city))
                        embed.set_image(url=f"attachment://{fname_city}")
                        files.append(discord.File(bio_mil, filename=fname_mil))
                else:
                    # Attach whichever chart(s) exist, preferring city first and then military
                    if city_chart:
                        bio_city, fname_city = city_chart
                        files.append(discord.File(bio_city, filename=fname_city))
                        embed.set_image(url=f"attachment://{fname_city}")
                    if mil_chart:
                        bio_mil, fname_mil = mil_chart
                        files.append(discord.File(bio_mil, filename=fname_mil))
            except Exception:
                pass

            await interaction.followup.send(embed=embed, files=files)
        except Exception as e:
            self.logger.error(f"/compare failed: {e}")
            try:
                await interaction.followup.send(f"❌ Compare failed: {str(e)}")
            except Exception:
                pass


async def setup(bot: commands.Bot):
    # Add the cog
    try:
        await bot.add_cog(CompareCog(bot))
    except Exception as e:
        logging.getLogger(__name__).warning(f"compare.py setup: failed to add cog: {e}")

    # Ensure slash command is registered in the tree
    try:
        # Avoid duplicates; register if not present
        existing = [cmd for cmd in bot.tree.get_commands() if getattr(cmd, 'name', '') == 'compare']
        if not existing:
            cog = bot.get_cog('CompareCog')
            if cog:
                # Prefer the cog's collected app commands for reliable registration
                for maybe_cmd in getattr(cog, '__cog_app_commands__', []):
                    try:
                        if isinstance(maybe_cmd, app_commands.Command) and maybe_cmd.name == 'compare':
                            bot.tree.add_command(maybe_cmd)
                            break
                    except Exception:
                        continue
        # Global sync is handled centrally; avoid redundant per-cog sync
    except Exception as e:
        logging.getLogger(__name__).warning(f"compare.py setup: command registration/sync issue: {e}")
