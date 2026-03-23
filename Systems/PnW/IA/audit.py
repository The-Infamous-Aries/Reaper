import discord
from discord.ext import commands
from discord import app_commands
from typing import List, Dict, Any, Optional, Callable, Literal
from discord.ui import Button, View
from datetime import datetime, timezone
import logging
import os
import sys

from Systems.Functions import emoji as emoji_mod

def _nation_link(n: Dict[str, Any]) -> str:
    """Return markdown link to a nation's PnW page."""
    nid = n.get('nation_id') or n.get('id') or n.get('nationid')
    name = (n.get('nation_name') or n.get('name') or 'Unknown').strip()
    try:
        nid_str = str(int(nid)) if nid is not None else ''
    except Exception:
        nid_str = str(nid) if nid is not None else ''
    url = f"https://politicsandwar.com/nation/id={nid_str}" if nid_str else "https://politicsandwar.com/nation/"
    return f"[{name}]({url})"

class AuditManager(commands.Cog):
    """Cog to audit alliance nations and surface issues in an embed."""

    def __init__(self, bot: commands.Bot, query_instance, calc_instance):
        self.bot = bot
        self.logger = logging.getLogger(self.__class__.__name__)
        self.query_instance = query_instance
        self.calc_instance = calc_instance
        self.default_alliance_id: Optional[int] = None
        self.default_alliance_name: Optional[str] = None

    # Dynamic autocomplete for mmr_mode: only suggest when view=="mmr"
    async def _mmr_mode_autocomplete(self, interaction: discord.Interaction, current: str):
        try:
            view_sel = getattr(interaction.namespace, 'view', None)
        except Exception:
            view_sel = None
        if view_sel == 'mmr':
            base = [
                app_commands.Choice(name="Basic", value="basic"),
                app_commands.Choice(name="Max", value="max"),
            ]
            cur = (current or "").lower()
            if cur:
                return [c for c in base if (cur in c.name.lower()) or (cur in c.value)]
            return base
        # When not in MMR view, no suggestions (keeps UI clean)
        return []

    async def _get_alliance_nations(self, alliance_id: int, force_refresh: bool = True) -> List[Dict[str, Any]]:
        """Use query instance to fetch nations."""
        try:
            nations_raw = await self.query_instance.get_alliance_nations(str(alliance_id), force_refresh=force_refresh)
            if isinstance(nations_raw, dict):
                return nations_raw.get('nations', []) or []
            return nations_raw or []
        except Exception as e:
            self.logger.error(f"Error fetching alliance nations for {alliance_id}: {e}")
            return []

    async def _get_combined_nations(self, center_id: int) -> List[Dict[str, Any]]:
        """Fetch nations for the specified alliance."""
        cy = await self._get_alliance_nations(center_id, force_refresh=True)
        # AllianceManager returns nations for the specific alliance; no extra filter needed.
        return cy or []

    def _filter_active_members(self, nations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Exclude applicants and vacation mode for resource checks."""
        active = []
        for n in nations:
            pos = (n.get('alliance_position', '') or '').strip().upper()
            if pos == 'APPLICANT':
                continue
            vm = int(n.get('vacation_mode_turns', 0) or 0)
            if vm > 0:
                continue
            active.append(n)
        return active

    async def _build_multi_field_values(self, items: List[Dict[str, Any]], with_days: bool = False, suffix_builder: Optional[Callable[[Dict[str, Any]], Optional[str]]] = None) -> List[str]:
        """Build multiple field values to show all nations, splitting across fields when needed.

        Returns a list of strings, each under 1024 characters, to display all nations
        across multiple embed fields if necessary.
        """
        try:
            if not items:
                return ["None"]

            links: List[str] = []
            for n in items:
                nid = n.get('nation_id') or n.get('id') or n.get('nationid')
                name = (n.get('nation_name') or n.get('name') or 'Unknown').strip()
                if not nid:
                    continue
                link = f"[{name}](https://politicsandwar.com/nation/id={nid})"
                if with_days:
                    d = await self.calc_instance.calculate_days_inactive(n.get('last_active'))
                    if isinstance(d, int):
                        link = f"{link} ({d}d)"
                if suffix_builder is not None:
                    try:
                        suffix = suffix_builder(n)
                        if suffix:
                            link = f"{link} {suffix}"
                    except Exception:
                        pass
                links.append(link)

            links.sort(key=lambda x: x.lower())

            if not links:
                return ["None"]

            field_values = []
            current_value = ""

            for link in links:
                add = ("\n" if current_value else "") + link
                if len(current_value) + len(add) > 1024:
                    if current_value:
                        field_values.append(current_value)
                    current_value = link
                else:
                    current_value += add

            if current_value:
                field_values.append(current_value)

            return field_values if field_values else ["None"]

        except Exception:
            safe = [(_nation_link(n)) for n in items]
            text = "\n".join(safe)
            if len(text) <= 1024:
                return [text] if text else ["None"]

            chunks = []
            while text:
                if len(text) <= 1024:
                    chunks.append(text)
                    break
                split_pos = text.rfind('\n', 0, 1024)
                if split_pos == -1:
                    split_pos = 1024
                chunks.append(text[:split_pos])
                text = text[split_pos:].lstrip('\n')

            return chunks if chunks else ["None"]

    async def _add_category_fields(self, embed: discord.Embed, category_name: str, emoji: str, items: List[Dict[str, Any]], with_days: bool = False, suffix_builder: Optional[Callable[[Dict[str, Any]], Optional[str]]] = None, count_only: Optional[int] = None):
        """Add one or more fields for a category, splitting across multiple fields if needed."""
        if count_only is not None:
            embed.add_field(name=f"{emoji} {category_name}", value=f"Total: {count_only}", inline=False)
            return

        field_values = await self._build_multi_field_values(items, with_days=with_days, suffix_builder=suffix_builder)

        for i, value in enumerate(field_values):
            if len(field_values) == 1:
                field_name = f"{emoji} {category_name} ({len(items)})"
            else:
                field_name = f"{emoji} {category_name} ({len(items)}) - Part {i + 1}"

            embed.add_field(name=field_name, value=value, inline=False)

    def _chunk_lines(self, lines: List[str], max_len: int = 1024) -> List[str]:
        """Split a list of lines into chunks under Discord's field length limit."""
        chunks: List[str] = []
        current = ""
        for line in lines:
            add = ("\n" if current else "") + line
            if len(current) + len(add) > max_len:
                if current:
                    chunks.append(current)
                current = line
            else:
                current += add
        if current:
            chunks.append(current)
        return chunks or ["None"]

    async def _audit_mmr_sync(self, active_members: List[Dict[str, Any]], mmr_mode: str) -> discord.Embed:
        if (mmr_mode or "basic") == "max":
            thresh = {"barracks": 5.0, "factory": 5.0, "air": 5.0, "drydock": 3.0}
            title = f"{emoji_mod.mention('max') or '⚙️'} MMR Build Audit — Max"
            note = "Shows ALL nations below 5/5/5/3 per-city average."
        else:
            thresh = {"barracks": 0.0, "factory": 2.0, "air": 5.0, "drydock": 1.0}
            title = f"{emoji_mod.mention('min') or '⚙️'} MMR Build Audit — Basic"
            note = "Shows nations below minimum 0/2/5/1 per-city average (more is fine)."
        EPSILON = 0.05

        def compute_mmr_avgs(n: Dict[str, Any]) -> Dict[str, float]:
            cities = n.get("cities") or []
            num = len(cities) if isinstance(cities, list) else (n.get("num_cities") or 0)
            if not num:
                return {"barracks": 0.0, "factory": 0.0, "air": 0.0, "drydock": 0.0, "num": 0,
                        "b_total": 0, "f_total": 0, "a_total": 0, "d_total": 0}
            b = f = a = d = 0
            for c in cities or []:
                if not isinstance(c, dict):
                    continue
                b += c.get("barracks", 0) or 0
                f += c.get("factory", 0) or 0
                a += (c.get("airforcebase", 0) or c.get("hangar", 0) or 0)
                d += c.get("drydock", 0) or 0
            return {
                "barracks": b / float(num),
                "factory": f / float(num),
                "air": a / float(num),
                "drydock": d / float(num),
                "num": float(num),
                "b_total": int(b),
                "f_total": int(f),
                "a_total": int(a),
                "d_total": int(d),
            }

        def _normalize_avgs(avg: Dict[str, float]) -> Dict[str, float]:
            return {
                "barracks": round(float(avg.get("barracks", 0.0) or 0.0), 1),
                "factory": round(float(avg.get("factory", 0.0) or 0.0), 1),
                "air": round(float(avg.get("air", 0.0) or 0.0), 1),
                "drydock": round(float(avg.get("drydock", 0.0) or 0.0), 1),
                "num": float(avg.get("num", 0.0) or 0.0),
            }

        def below_threshold(avg: Dict[str, float]) -> bool:
            navg = _normalize_avgs(avg)
            def is_below(key: str) -> bool:
                t = float(thresh.get(key, 0.0) or 0.0)
                a = float(navg.get(key, 0.0) or 0.0)
                if t <= 0:
                    return False
                return (a + EPSILON) < t
            return any(is_below(k) for k in ("barracks", "factory", "air", "drydock"))

        def compute_percent_off(avg: Dict[str, float], thr: Dict[str, float]) -> float:
            keys = ("barracks", "factory", "air", "drydock")
            total_thr = sum(v for k, v in thr.items() if k in keys and v > 0)
            if total_thr <= 0:
                return 0.0
            navg = _normalize_avgs(avg)
            deficit_sum = 0.0
            for k in keys:
                t = float(thr.get(k, 0.0) or 0.0)
                a = float(navg.get(k, 0.0) or 0.0)
                if t > 0 and (a + EPSILON) < t:
                    deficit_sum += (t - a)
            return max(0.0, min(100.0, (deficit_sum / total_thr) * 100.0))

        bucket_50_plus: List[Dict[str, Any]] = []
        bucket_25_49: List[Dict[str, Any]] = []
        bucket_10_24: List[Dict[str, Any]] = []
        bucket_0_9: List[Dict[str, Any]] = []

        for n in active_members:
            avg = compute_mmr_avgs(n)
            if avg["num"] <= 0:
                continue
            if below_threshold(avg):
                perc = compute_percent_off(avg, thresh)
                mmr_str = f"{avg['barracks']:.1f}/{avg['factory']:.1f}/{avg['air']:.1f}/{avg['drydock']:.1f}"
                try:
                    num_cities = int(round(float(avg.get("num", 0) or 0)))
                except Exception:
                    num_cities = 0
                totals_map = {
                    "barracks": int(round((thresh.get("barracks", 0) or 0) * num_cities)),
                    "factory": int(round((thresh.get("factory", 0) or 0) * num_cities)),
                    "air": int(round((thresh.get("air", 0) or 0) * num_cities)),
                    "drydock": int(round((thresh.get("drydock", 0) or 0) * num_cities)),
                }
                current_totals = {
                    "barracks": int(avg.get("b_total", 0) or 0),
                    "factory": int(avg.get("f_total", 0) or 0),
                    "air": int(avg.get("a_total", 0) or 0),
                    "drydock": int(avg.get("d_total", 0) or 0),
                }
                navg = {
                    "barracks": round(float(avg.get("barracks", 0.0) or 0.0), 1),
                    "factory": round(float(avg.get("factory", 0.0) or 0.0), 1),
                    "air": round(float(avg.get("air", 0.0) or 0.0), 1),
                    "drydock": round(float(avg.get("drydock", 0.0) or 0.0), 1),
                }
                below_keys = []
                for k in ("barracks", "factory", "air", "drydock"):
                    tval = float(thresh.get(k, 0.0) or 0.0)
                    aval = float(navg.get(k, 0.0) or 0.0)
                    if tval > 0 and (aval + EPSILON) < tval:
                        below_keys.append(k)
                enriched = dict(n)
                enriched["__mmr_avg"] = avg
                enriched["__mmr_percent_off"] = perc
                enriched["__mmr_str"] = mmr_str
                enriched["__mmr_totals"] = totals_map
                enriched["__mmr_current_totals"] = current_totals
                enriched["__mmr_below_keys"] = below_keys
                if perc >= 50.0:
                    bucket_50_plus.append(enriched)
                elif perc >= 25.0:
                    bucket_25_49.append(enriched)
                elif perc >= 10.0:
                    bucket_10_24.append(enriched)
                else:
                    bucket_0_9.append(enriched)

        embed = discord.Embed(
            title=title,
            description=note,
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        def suffix_builder(nation: Dict[str, Any]) -> Optional[str]:
            try:
                totals = nation.get("__mmr_totals", {}) or {}
                current = nation.get("__mmr_current_totals", {}) or {}
                avg = nation.get("__mmr_avg", {}) or {}
                mode_label = "Max" if (mmr_mode or "basic") == "max" else "Basic"
                mmr_s = str(nation.get("__mmr_str", ""))
                navg = {
                    "barracks": round(float(avg.get("barracks", 0.0) or 0.0), 1),
                    "factory": round(float(avg.get("factory", 0.0) or 0.0), 1),
                    "air": round(float(avg.get("air", 0.0) or 0.0), 1),
                    "drydock": round(float(avg.get("drydock", 0.0) or 0.0), 1),
                }
                def need_for(key: str) -> int:
                    t = float(thresh.get(key, 0.0) or 0.0)
                    a = float(navg.get(key, 0.0) or 0.0)
                    if t <= 0:
                        return 0
                    if (a + EPSILON) >= t:
                        return 0
                    required_total = int(round(t * float(avg.get("num", 0.0) or 0.0)))
                    current_total = int(current.get(key, 0) or 0)
                    return max(0, required_total - current_total)

                need_b = need_for("barracks")
                need_f = need_for("factory")
                need_a = need_for("air")
                need_d = need_for("drydock")
                needed_str = f"{need_b}/{need_f}/{need_a}/{need_d}"
                return f" - {mmr_s}\n   * Target {mode_label}: {needed_str}"
            except Exception:
                return None

        total_offenders = (
            len(bucket_50_plus) + len(bucket_25_49) + len(bucket_10_24) + len(bucket_0_9)
        )

        base_embed = discord.Embed(
            title=title,
            description=note,
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )

        if total_offenders == 0:
            no_offenders_embed = base_embed.copy()
            no_offenders_embed.add_field(name="Members Below Threshold", value="✅ All members meet the threshold.", inline=False)
            no_offenders_embed.set_footer(text=f"Active members checked: {len(active_members)} • Offenders: 0")
            return {"All Clear": no_offenders_embed}

        categories = {
            "50%+ off": (bucket_50_plus, emoji_mod.mention("warnr") or "🟥"),
            "25–49% off": (bucket_25_49, emoji_mod.mention("warno") or "🟧"),
            "10–24% off": (bucket_10_24, emoji_mod.mention("warny") or "🟨"),
            "0–9% off": (bucket_0_9, emoji_mod.mention("warng") or "🟩"),
        }

        # Attempt to build a single summary embed
        full_summary_embed = base_embed.copy()
        full_summary_embed.title = f"{emoji_mod.mention('summary') or '📜'} MMR Audit Summary"
        full_summary_embed.description = f"A complete list of all {total_offenders} offenders."
        full_summary_embed.set_footer(text=f"Active members checked: {len(active_members)} • Total Offenders: {total_offenders}")

        total_len = len(full_summary_embed.title) + len(full_summary_embed.description or '')
        field_count = 0
        summary_fields_data = []

        for name, (bucket, emoji) in categories.items():
            if bucket:
                field_values = await self._build_multi_field_values(bucket, suffix_builder=suffix_builder)
                for i, value in enumerate(field_values):
                    field_name = f"{emoji} {name} ({len(bucket)})"
                    if len(field_values) > 1:
                        field_name += f" - Part {i + 1}"
                    
                    summary_fields_data.append({'name': field_name, 'value': value, 'inline': False})
                    total_len += len(field_name) + len(value)
                    field_count += 1
        
        # Discord limits: 6000 total chars, 25 fields.
        if total_len < 5800 and field_count <= 25:
            for field in summary_fields_data:
                full_summary_embed.add_field(**field)
            return {"Summary": full_summary_embed}

        # If too long, create paginated view
        category_embeds: Dict[str, discord.Embed] = {}
        
        # Create a summary page with counts
        summary_counts_embed = base_embed.copy()
        summary_counts_embed.title = f"{emoji_mod.mention('summary') or '📜'} MMR Audit Summary"
        summary_counts_embed.description = "Too many offenders to display at once. Use buttons to navigate categories."
        summary_counts_embed.set_footer(text=f"Active members checked: {len(active_members)} • Total Offenders: {total_offenders}")
        for name, (bucket, emoji) in categories.items():
            if bucket:
                summary_counts_embed.add_field(name=f"{emoji} {name}", value=f"Total: {len(bucket)}", inline=False)
        category_embeds["Summary"] = summary_counts_embed

        # Create individual category pages, paginating within a category if needed
        for name, (bucket, emoji) in categories.items():
            if not bucket:
                continue

            field_values = await self._build_multi_field_values(bucket, suffix_builder=suffix_builder)
            
            # Split field_values into chunks of up to 25, as one embed can't have more.
            fields_per_embed = 25
            value_chunks = [field_values[i:i + fields_per_embed] for i in range(0, len(field_values), fields_per_embed)]

            if not value_chunks:
                continue

            for i, chunk in enumerate(value_chunks):
                page_embed = base_embed.copy()
                page_name = name
                if len(value_chunks) > 1:
                    page_name = f"{name} (Page {i + 1}/{len(value_chunks)})"
                
                page_embed.set_footer(text=f"Active members checked: {len(active_members)} • Offenders in category: {len(bucket)}")
                
                # Add fields to this page's embed
                for j, value in enumerate(chunk):
                    part_num = i * fields_per_embed + j + 1
                    if len(field_values) == 1:
                        field_name = f"{emoji} {name} ({len(bucket)})"
                    else:
                        field_name = f"{emoji} {name} ({len(bucket)}) - Part {part_num}"
                    
                    page_embed.add_field(name=field_name, value=value, inline=False)
                
                category_embeds[page_name] = page_embed

        return category_embeds

    @app_commands.describe(
        view="Select what to display: Food & Uranium, Inactives, Color, or MMR Build",
        mmr_mode="If MMR Build is selected, choose Basic or Max"
    )
    @app_commands.choices(view=[
        app_commands.Choice(name="Food & Uranium", value="resources"),
        app_commands.Choice(name="Inactives", value="inactives"),
        app_commands.Choice(name="Color", value="color"),
        app_commands.Choice(name="MMR Build", value="mmr"),
    ])
    @app_commands.autocomplete(mmr_mode=_mmr_mode_autocomplete)
    @app_commands.describe(alliance="Alliance name or ID")
    @commands.hybrid_command(name="audit", description="Audit alliance issues")  # type: ignore
    async def audit_command(self, ctx: commands.Context, view: Literal["resources", "inactives", "color", "mmr"], alliance: Optional[str] = None, mmr_mode: Optional[Literal["basic", "max"]] = "basic"):

        """Generate an "Audit Issues" embed listing issue categories as nation links."""
        try:
            try:
                if hasattr(ctx, 'interaction') and ctx.interaction and not ctx.interaction.response.is_done():
                    await ctx.interaction.response.defer()
            except Exception:
                pass

            center_id: Optional[int] = None
            center_name: Optional[str] = None
            center_color: Optional[str] = None
            try:
                alliance_cog = self.bot.get_cog('AllianceManager')
                if alliance_cog and hasattr(alliance_cog, 'query_system') and alliance_cog.query_system:
                    arg = (alliance or "").strip()
                    if arg:
                        resolved = await alliance_cog.query_system.resolve_alliance(arg)
                        try:
                            if resolved and isinstance(resolved, dict) and resolved.get('id'):
                                center_id = int(str(resolved.get('id')))
                                center_name = (resolved.get('name') or '').strip() or None
                                center_color = (resolved.get('color') or '').strip().lower() or None
                            elif arg.isdigit():
                                center_id = int(arg)
                            else:
                                center_id = None
                        except Exception:
                            center_id = None

                        if not center_id or int(center_id) <= 0:
                            msg = "❌ Could not resolve alliance. Enter a valid name or ID."
                            if hasattr(ctx, 'interaction') and ctx.interaction:
                                await ctx.interaction.followup.send(msg)
                            else:
                                await ctx.reply(msg)
                            return
                    else:
                        if self.default_alliance_id:
                            center_id = int(self.default_alliance_id)
                            center_name = self.default_alliance_name
                        else:
                            center_id = None
                            center_name = None
                else:
                    # Fallback if AllianceManager is not loaded
                    if self.default_alliance_id:
                        center_id = int(self.default_alliance_id)
                        center_name = self.default_alliance_name
                    else:
                        center_id = None
                        center_name = None
            except Exception as qerr:
                self.logger.error(f"Error resolving alliance for audit: {qerr}")
                if self.default_alliance_id:
                    center_id = int(self.default_alliance_id)
                    center_name = self.default_alliance_name
                else:
                    center_id = None
                    center_name = None

            if not center_id:
                msg = "❌ No default alliance configured. Please specify an alliance name or ID."
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.interaction.followup.send(msg)
                else:
                    await ctx.reply(msg)
                return

            nations = await self._get_combined_nations(center_id)
            if not nations:
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.interaction.followup.send("❌ No alliance data found for the specified alliance.")
                else:
                    await ctx.reply("❌ No alliance data found for the specified alliance.")
                return

            active_members = self._filter_active_members(nations)

            # New: MMR Build audit
            if view == "mmr":
                try:
                    category_embeds = await self._audit_mmr_sync(active_members, mmr_mode or "basic")

                    # If only one embed, send it without a view (no buttons).
                    # This handles the full summary view and the 'All Clear' case.
                    if len(category_embeds) == 1:
                        single_embed = list(category_embeds.values())[0]
                        if hasattr(ctx, 'interaction') and ctx.interaction:
                            await ctx.interaction.followup.send(embed=single_embed)
                        else:
                            await ctx.reply(embed=single_embed)
                        return

                    # Determine the initial category to display
                    initial_category = "Summary"

                    initial_embed = category_embeds.get(initial_category)
                    if not initial_embed: # Fallback
                        initial_embed = list(category_embeds.values())[0]

                    # Create the pagination view
                    mmr_view = MMRPaginationView(embeds=category_embeds, initial_category=initial_category)

                    if hasattr(ctx, 'interaction') and ctx.interaction:
                        sent_message = await ctx.interaction.followup.send(embed=initial_embed, view=mmr_view)
                    else:
                        sent_message = await ctx.reply(embed=initial_embed, view=mmr_view)

                    mmr_view.message = sent_message # Store the message for later editing

                    return
                except Exception as mmr_err:
                    self.logger.error(f"MMR audit error: {mmr_err}")
                    embed = discord.Embed(
                        title="❌ MMR Audit Error",
                        description=f"An error occurred during MMR calculation: {mmr_err}",
                        color=discord.Color.red()
                    )
                    if hasattr(ctx, 'interaction') and ctx.interaction:
                        await ctx.interaction.followup.send(embed=embed)
                    else:
                        await ctx.reply(embed=embed)
                    return
            food_lt_10k = [n for n in active_members if 0 < (n.get('food', 0) or 0) < 50000]
            uran_lt_500 = [n for n in active_members if 0 < (n.get('uranium', 0) or 0) < 1000]
            food_zero = [n for n in active_members if (n.get('food', 0) or 0) == 0]
            uran_zero = [n for n in active_members if (n.get('uranium', 0) or 0) == 0]
            alliance_color: Optional[str] = None
            if center_id:
                resolved_alliance_details = await self.query_instance.resolve_alliance(center_id)
                if resolved_alliance_details:
                    alliance_color = (resolved_alliance_details.get('color') or '').strip().upper()

            beige = [n for n in active_members if (n.get('color', '') or '').strip().upper() == 'BEIGE']
            grey = [n for n in active_members if (n.get('color', '') or '').strip().upper() in ('GREY', 'GRAY')]

            correct_color_members: List[Dict[str, Any]] = []
            wrong_color_members: List[Dict[str, Any]] = []

            if alliance_color:
                correct_color_members = [n for n in active_members if (n.get('color', '') or '').strip().upper() == alliance_color]
                # Wrong color members are those not matching alliance_color, and also not Beige or Grey
                wrong_color_members = [
                    n for n in active_members
                    if (n.get('color', '') or '').strip().upper() not in (alliance_color, 'BEIGE', 'GREY', 'GRAY')
                ]
            else:
                # Fallback if alliance color cannot be determined
                wrong_color_members = [n for n in active_members if (n.get('color', '') or '').strip().upper() not in ('LIME', 'GREY', 'GRAY', 'BEIGE')]


            inactive_7_to_13: List[Dict[str, Any]] = []
            inactive_14_to_23: List[Dict[str, Any]] = []
            inactive_24_plus: List[Dict[str, Any]] = []
            for n in active_members:
                d = await self.calc_instance.calculate_days_inactive(n.get('last_active'))
                if isinstance(d, int):
                    if 7 <= d <= 13:
                        inactive_7_to_13.append(n)
                    elif 14 <= d <= 23:
                        inactive_14_to_23.append(n)
                    elif d >= 24:
                        inactive_24_plus.append(n)

            audit_title = f"🧮 {center_name or 'Alliance'} Audit Issues"
            audit_description = f"Irregularities in the {center_name or 'selected'} alliance."
            embed = discord.Embed(
                title=audit_title,
                description=audit_description,
                color=discord.Color.orange()
            )

            view_key = view

            if view_key == "resources":
                await self._add_category_fields(
                    embed,
                    "Food < 50,000",
                    emoji_mod.mention('food_1') or "🍞",
                    food_lt_10k,
                    suffix_builder=lambda n: f"- {int(n.get('food', 0)):,}"
                )
                await self._add_category_fields(
                    embed,
                    "Uranium < 1,000",
                    emoji_mod.mention('uranium_1') or "☢️",
                    uran_lt_500,
                    suffix_builder=lambda n: f"- {int(n.get('uranium', 0)):,}"
                )
                await self._add_category_fields(embed, "Food = 0", "🚫", food_zero)
                await self._add_category_fields(embed, "Uranium = 0", "🚫", uran_zero)
            elif view_key == "inactives":
                await self._add_category_fields(embed, "Inactive 7-13 days", "⏲️", inactive_7_to_13, with_days=True)
                await self._add_category_fields(embed, "Inactive 14-23 days", "⚠️", inactive_14_to_23, with_days=True)
                await self._add_category_fields(embed, "Inactive 24+ days", "🛑", inactive_24_plus, with_days=True)
            elif view_key == "color":
                await self._add_category_fields(embed, "Beige", "🩼", beige)
                await self._add_category_fields(embed, "Grey", "⚪", grey)
                if alliance_color:
                    await self._add_category_fields(embed, f"Correct Color ({alliance_color})", "✅", [], count_only=len(correct_color_members))
                    await self._add_category_fields(embed, "Wrong Color", "🎨", wrong_color_members)
                else:
                    embed.add_field(name="Color Audit", value="❌ Could not determine alliance color. Showing default 'Wrong Color' audit.", inline=False)
                    await self._add_category_fields(embed, "Wrong Color (Default)", "🎨", wrong_color_members)


            embed.set_footer(text=f"Generated at {datetime.now().strftime('%H:%M:%S')} | Excludes APPLICANTS and Vacation Mode")

            if hasattr(ctx, 'interaction') and ctx.interaction:
                await ctx.interaction.followup.send(embed=embed)
            else:
                await ctx.reply(embed=embed)
        except Exception as e:
            self.logger.error(f"/audit error: {e}")
            try:
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.interaction.followup.send(f"❌ An error occurred: {str(e)}")
                else:
                    await ctx.reply(f"❌ An error occurred: {str(e)}")
            except Exception:
                pass

class MMRPaginationView(discord.ui.View):

    def __init__(self, embeds: Dict[str, discord.Embed], initial_category: str, timeout: Optional[float] = 180.0):
        super().__init__(timeout=timeout)
        self.embeds = embeds
        self.current_category = initial_category
        self.message = None  # To store the message this view is attached to

        # Add buttons for each category
        for category_name in self.embeds.keys():
            self.add_item(self._create_button(category_name))

    def _create_button(self, category_name: str) -> discord.ui.Button:
        button = discord.ui.Button(label=category_name, custom_id=f"mmr_category_{category_name}")
        button.callback = self.create_callback(category_name)
        return button

    def create_callback(self, category_name: str):
        async def callback(interaction: discord.Interaction):
            # Only the user who invoked the command can interact
            if interaction.user.id != self.message.interaction.user.id:
                await interaction.response.send_message("This is not your audit!", ephemeral=True)
                return

            self.current_category = category_name
            await interaction.response.edit_message(embed=self.embeds[category_name], view=self)
        return callback

    async def on_timeout(self):
        if self.message:
            await self.message.edit(view=None) # Remove buttons on timeout

async def setup(bot: commands.Bot):
    logging.getLogger(__name__).info("Attempting to load AuditManager cog.")
    alliance_cog = bot.get_cog('AllianceManager')
    if alliance_cog:
        query_instance = getattr(alliance_cog, 'query_system', None)
        calc_instance = getattr(alliance_cog, 'calc_system', None)
        if query_instance and calc_instance:
            audit = AuditManager(bot, query_instance, calc_instance)
            await bot.add_cog(audit)