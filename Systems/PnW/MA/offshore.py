import discord
from discord.ext import commands
from discord import app_commands
import logging
import sqlite3
from typing import Optional, List, Dict, Tuple, Set
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from Systems.PnW.Util.query import create_v3_query_instance
from Systems.PnW.Util.war_calc import get_resource_prices
from Systems.Functions.emoji import resource_emoji
from Systems.Functions.db_paths import BANKRECS_DB_STR, IRS_WARS_DB_STR

logger = logging.getLogger("Reaper.MA.Offshore")

RESOURCES = ["money", "coal", "oil", "uranium", "iron", "bauxite", "lead",
             "gasoline", "munitions", "steel", "aluminum", "food"]

# sender_type / receiver_type values
TYPE_NATION   = 1
TYPE_ALLIANCE = 2

MAX_DAYS = 14  # hard cap — users can go up to 14 days, default is 7

# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_time_arg(time_str: str) -> int:
    """
    Parse a human time string into a number of days.
    Supports: 2d, 3w  (days, weeks only — max 14 days)
    Returns days as int. Defaults to 7 on invalid input.
    """
    import re
    if not time_str:
        return 7
    m = re.fullmatch(r"(\d+)\s*([dw])", time_str.strip().lower())
    if not m:
        try:
            return min(MAX_DAYS, max(1, int(time_str)))
        except ValueError:
            return 7
    amount, unit = int(m.group(1)), m.group(2)
    days = {"d": amount, "w": amount * 7}[unit]
    return min(MAX_DAYS, max(1, days))


def _since_dt(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _since_str(days: int) -> str:
    return _since_dt(days).strftime("%Y-%m-%d %H:%M:%S")


# ── War-loot filter ───────────────────────────────────────────────────────────

def _build_war_loot_filter(since: str) -> Set[Tuple[int, int]]:
    """
    Query IRSWars.db for all wars that were active/started within the time window
    and return a set of (attacker_nation_id, defender_alliance_id) pairs.

    Any bankrec where receiver_id == attacker_nation_id AND sender_id == defender_alliance_id
    (sender_type=2, receiver_type=1) is war bank loot and must be excluded.

    We also include the reverse: (defender_nation_id, attacker_alliance_id) for cases
    where the defender wins and loots the attacker's alliance bank.
    """
    war_loot_pairs: Set[Tuple[int, int]] = set()
    try:
        with sqlite3.connect(IRS_WARS_DB_STR) as conn:
            conn.row_factory = sqlite3.Row
            # Wars that started or ended within the window, or were still active
            rows = conn.execute(
                """
                SELECT att_id, def_id, att_alliance_id, def_alliance_id
                FROM wars
                WHERE date >= ? OR end_date >= ? OR end_date IS NULL
                """,
                (since, since),
            ).fetchall()
            for row in rows:
                att_id          = row["att_id"]
                def_id          = row["def_id"]
                att_alliance_id = row["att_alliance_id"]
                def_alliance_id = row["def_alliance_id"]
                # Attacker loots defender's alliance bank
                if att_id and def_alliance_id:
                    war_loot_pairs.add((int(att_id), int(def_alliance_id)))
                # Defender loots attacker's alliance bank (less common but possible)
                if def_id and att_alliance_id:
                    war_loot_pairs.add((int(def_id), int(att_alliance_id)))
    except Exception as e:
        logger.warning(f"Could not load war loot filter from IRSWars.db: {e}")

    logger.info(f"War loot filter: {len(war_loot_pairs)} (nation, alliance) pairs loaded")
    return war_loot_pairs


def _is_war_loot(rec: dict, war_loot_pairs: Set[Tuple[int, int]]) -> bool:
    """
    Return True if this bankrec looks like war bank loot and should be excluded.

    Two detection methods (either is sufficient):
      1. note field contains war-loot keywords (e.g. "Looted from war")
      2. (receiver_id, sender_id) matches a known (attacker, looted_alliance) war pair
         where sender_type=2 (alliance) and receiver_type=1 (nation)
    """
    note = (rec.get("note") or "").lower()
    if "looted from war" in note or "war loot" in note or "war #" in note:
        return True

    sender_type   = int(rec.get("sender_type")   or 0)
    receiver_type = int(rec.get("receiver_type") or 0)
    sender_id     = int(rec.get("sender_id")     or 0)
    receiver_id   = int(rec.get("receiver_id")   or 0)

    if sender_type == TYPE_ALLIANCE and receiver_type == TYPE_NATION:
        if (receiver_id, sender_id) in war_loot_pairs:
            return True

    return False


# ── Local DB queries ──────────────────────────────────────────────────────────

def _fetch_member_bankrecs_local(
    nation_ids: List[int],
    alliance_id: int,
    since: str,
    war_loot_pairs: Set[Tuple[int, int]],
) -> List[dict]:
    """
    Query bankrecs.db directly for all records involving the member nations
    within the time window, then filter:
      - Keep only records where a member received from an external source
        OR sent to an external destination (for net tracking)
      - Exclude internal alliance bank transfers (own alliance bank → member)
      - Exclude war loot bankrecs
    """
    if not nation_ids:
        return []

    nation_set = set(nation_ids)
    results: List[dict] = []
    seen: Set[int] = set()

    try:
        with sqlite3.connect(BANKRECS_DB_STR) as conn:
            conn.row_factory = sqlite3.Row
            placeholders = ",".join("?" * len(nation_ids))

            rows = conn.execute(
                f"""
                SELECT * FROM bankrecs
                WHERE (
                    (receiver_id IN ({placeholders}) AND receiver_type = 1)
                 OR (sender_id   IN ({placeholders}) AND sender_type   = 1)
                )
                AND date >= ?
                ORDER BY date DESC
                """,
                list(nation_ids) + list(nation_ids) + [since],
            ).fetchall()

        for row in rows:
            rec = dict(row)
            rec_id = rec.get("id")
            if rec_id in seen:
                continue
            seen.add(rec_id)

            sender_id     = int(rec.get("sender_id")   or 0)
            sender_type   = int(rec.get("sender_type")  or 0)
            receiver_id   = int(rec.get("receiver_id")  or 0)
            receiver_type = int(rec.get("receiver_type") or 0)

            # ── Filter: exclude war loot ──────────────────────────────────────
            if _is_war_loot(rec, war_loot_pairs):
                logger.debug(
                    f"Skipping war loot bankrec id={rec_id} "
                    f"sender={sender_id}(type={sender_type}) → "
                    f"receiver={receiver_id}(type={receiver_type})"
                )
                continue

            # ── RECEIVE path: external → member ──────────────────────────────
            if receiver_type == TYPE_NATION and receiver_id in nation_set:
                # Skip: own alliance bank paying out to member (normal withdrawal)
                if sender_type == TYPE_ALLIANCE and sender_id == alliance_id:
                    continue
                # Skip: member-to-member transfer
                if sender_type == TYPE_NATION and sender_id in nation_set:
                    continue
                results.append(rec)
                continue

            # ── SEND path: member → external ─────────────────────────────────
            if sender_type == TYPE_NATION and sender_id in nation_set:
                # Skip: member depositing into own alliance bank
                if receiver_type == TYPE_ALLIANCE and receiver_id == alliance_id:
                    continue
                # Skip: member-to-member transfer
                if receiver_type == TYPE_NATION and receiver_id in nation_set:
                    continue
                results.append(rec)

    except Exception as e:
        logger.error(f"Error querying bankrecs.db: {e}", exc_info=True)

    return results


# ── Alliance name resolution ──────────────────────────────────────────────────

async def resolve_alliance_names(query_instance, alliance_ids: List[int]) -> Dict[int, str]:
    """Batch resolve alliance IDs to names via the PnW API."""
    if not alliance_ids:
        return {}
    try:
        blocks = " ".join(
            f'a{aid}: alliances(id: [{aid}], first: 1) {{ data {{ id name acronym }} }}'
            for aid in alliance_ids
        )
        data   = await query_instance._make_graphql_request(f"query {{ {blocks} }}")
        result = {}
        for aid in alliance_ids:
            items = (data.get(f"a{aid}") or {}).get("data") or []
            result[aid] = items[0].get("name") or items[0].get("acronym") or str(aid) if items else str(aid)
        return result
    except Exception as e:
        logger.error(f"Error resolving alliance names: {e}")
        return {aid: str(aid) for aid in alliance_ids}


async def fetch_alliance_nation_ids(query_instance, alliance_id: int) -> Tuple[List[int], Dict[int, str]]:
    """Fetch all current nation IDs in an alliance via the PnW API."""
    gql = f"""
    query {{
      nations(alliance_id: [{alliance_id}], first: 500) {{
        paginatorInfo {{ hasMorePages }}
        data {{ id nation_name }}
      }}
    }}
    """
    try:
        data    = await query_instance._make_graphql_request(gql)
        nations = (data.get("nations") or {}).get("data") or []
        return [int(n["id"]) for n in nations], {int(n["id"]): n.get("nation_name", "") for n in nations}
    except Exception as e:
        logger.error(f"Error fetching nation IDs for alliance {alliance_id}: {e}")
        return [], {}


# ── Value helpers ─────────────────────────────────────────────────────────────

def _rec_value(rec: dict, prices: dict) -> float:
    """Total $ value of all resources in a bankrec at best sell prices."""
    total = float(rec.get("money") or 0)
    sell  = prices.get("sell", {})
    for rss in RESOURCES:
        if rss == "money":
            continue
        total += float(rec.get(rss) or 0) * sell.get(rss, 0)
    return total


def _add_rec(balance: Dict[str, float], rec: dict, sign: float) -> None:
    for rss in RESOURCES:
        balance[rss] += float(rec.get(rss) or 0) * sign


def _format_balance(balance: Dict[str, float], prices: dict) -> Tuple[List[str], float]:
    lines, total = [], 0.0
    sell = prices.get("sell", {})
    for rss in RESOURCES:
        amt = balance.get(rss, 0)
        if abs(amt) < 0.01:
            continue
        val   = amt if rss == "money" else amt * sell.get(rss, 0)
        emoji = "💵" if rss == "money" else (resource_emoji(rss) or rss.title())
        total += val
        sign  = "+" if amt >= 0 else ""
        lines.append(f"{emoji} {sign}{amt:,.0f} (${val:,.0f})")
    return lines, total


# ── View ──────────────────────────────────────────────────────────────────────

class OffshoreView(discord.ui.View):
    def __init__(self, embeds: List[discord.Embed]):
        super().__init__(timeout=300)
        self.embeds  = embeds
        self.page    = 0
        self.message: Optional[discord.Message] = None
        self._sync_buttons()

    def _sync_buttons(self):
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = self.page >= len(self.embeds) - 1

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.page], view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = min(len(self.embeds) - 1, self.page + 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.page], view=self)


# ── Cog ───────────────────────────────────────────────────────────────────────

class Offshore(commands.Cog):
    def __init__(self, bot):
        self.bot            = bot
        self.query_instance = create_v3_query_instance()

    @app_commands.command(name="offshore", description="Find members receiving funds from an external offshore bank")
    @app_commands.describe(
        alliance="Alliance name or ID to investigate",
        time="How far back to look — e.g. 7d, 2w (default 7d, max 14d)",
    )
    async def offshore(self, interaction: discord.Interaction, alliance: str, time: str = "7d"):
        try:
            await interaction.response.defer(thinking=True)
        except discord.NotFound:
            return

        try:
            days = min(_parse_time_arg(time), MAX_DAYS)

            # ── Resolve alliance ──────────────────────────────────────────────
            resolved = await self.query_instance.resolve_entities(
                [int(alliance) if alliance.isdigit() else alliance], "alliance"
            )
            if not resolved:
                await interaction.followup.send("❌ Could not resolve that alliance.")
                return
            alliance_id   = resolved[0]
            alliance_name = alliance
            try:
                info = await self.query_instance.resolve_alliance(alliance_id)
                if info:
                    alliance_name = info.get("name") or info.get("acronym") or alliance
            except Exception:
                pass

            await interaction.followup.send(
                f"🔍 Scanning **{alliance_name}** member bank records for the last **{days}d** "
                f"(war loot excluded)…"
            )

            prices = await get_resource_prices()
            since  = _since_str(days)

            # ── Step 1: get all current member nation IDs ─────────────────────
            result = await fetch_alliance_nation_ids(self.query_instance, alliance_id)
            nation_ids, nation_name_map = result
            if not nation_ids:
                await interaction.followup.send("❌ No members found for this alliance.")
                return

            nation_set = set(nation_ids)

            # ── Step 2: build war-loot filter from IRSWars.db ─────────────────
            # This gives us (attacker_nation_id, looted_alliance_id) pairs so we
            # can drop any bankrec that is actually war bank loot, not an offshore.
            war_loot_pairs = _build_war_loot_filter(since)

            # ── Step 3: query bankrecs.db locally ────────────────────────────
            all_member_recs = _fetch_member_bankrecs_local(
                nation_ids, alliance_id, since, war_loot_pairs
            )

            if not all_member_recs:
                await interaction.followup.send(
                    "❌ No external bank records found for members in this time window "
                    "(after filtering war loot)."
                )
                return

            # ── Step 4: per-member net tracking ──────────────────────────────
            nation_net: Dict[int, Dict[str, float]] = defaultdict(lambda: {r: 0.0 for r in RESOURCES})
            nation_info: Dict[int, str]             = dict(nation_name_map)
            # nation_sources[nation_id][source_alliance_id] = total $ value received
            nation_sources: Dict[int, Dict[int, float]] = defaultdict(lambda: defaultdict(float))
            source_names: Dict[int, str]                = {}
            needs_name_resolve: Set[int]                = set()

            for rec in all_member_recs:
                sender_id     = int(rec.get("sender_id")   or 0)
                sender_type   = int(rec.get("sender_type")  or 0)
                receiver_id   = int(rec.get("receiver_id")  or 0)
                receiver_type = int(rec.get("receiver_type") or 0)

                # ── RECEIVE: external → member ────────────────────────────────
                if receiver_type == TYPE_NATION and receiver_id in nation_set:
                    val = _rec_value(rec, prices)
                    _add_rec(nation_net[receiver_id], rec, +1.0)

                    # Identify the source alliance
                    if sender_type == TYPE_ALLIANCE:
                        src_id = sender_id
                        needs_name_resolve.add(src_id)
                    else:
                        # Nation sender — use their alliance affiliation if we have it
                        # (bankrecs.db doesn't store nested alliance objects, so we
                        #  can only track by sender nation id here; we'll group by
                        #  sender_id as a proxy and resolve later if needed)
                        src_id = None  # nation-to-nation external; no alliance to attribute

                    if src_id and src_id != alliance_id:
                        nation_sources[receiver_id][src_id] += val

                # ── SEND: member → external ───────────────────────────────────
                elif sender_type == TYPE_NATION and sender_id in nation_set:
                    _add_rec(nation_net[sender_id], rec, -1.0)

            # Resolve any alliance names we don't have yet
            if needs_name_resolve:
                resolved_names = await resolve_alliance_names(
                    self.query_instance, list(needs_name_resolve)
                )
                source_names.update(resolved_names)

            # ── Step 5: compute per-member net value and rank ─────────────────
            sell = prices.get("sell", {})
            member_results = []
            for nid, net_bal in nation_net.items():
                net_val = sum(
                    net_bal.get(r, 0) * (1.0 if r == "money" else sell.get(r, 0))
                    for r in RESOURCES
                )
                if net_val <= 0:
                    continue
                top_src_id   = max(nation_sources[nid], key=nation_sources[nid].get, default=None)
                top_src_name = source_names.get(top_src_id, f"Alliance #{top_src_id}") if top_src_id else "Unknown"
                member_results.append((nid, net_val, net_bal, top_src_id, top_src_name))

            member_results.sort(key=lambda x: x[1], reverse=True)

            # ── Step 6: aggregate source alliances ────────────────────────────
            source_totals: Dict[int, float] = defaultdict(float)
            for nid, _, _, src_id, _ in member_results:
                if src_id:
                    source_totals[src_id] += sum(nation_sources[nid].values())

            top_sources = sorted(source_totals.items(), key=lambda x: x[1], reverse=True)[:3]

            if not member_results:
                await interaction.followup.send(
                    "✅ No members found with a net positive external receive balance "
                    "(war loot excluded)."
                )
                return

            # ── Step 7: build embeds ──────────────────────────────────────────
            date_str     = f"Last {days} day{'s' if days != 1 else ''}"
            medals       = ["🥇", "🥈", "🥉"]
            PER_PAGE     = 10
            pages_needed = max(1, -(-len(member_results) // PER_PAGE))
            total_pages  = 1 + pages_needed

            overview = discord.Embed(
                title=f"🏦 Offshore Receiver Scan — {alliance_name}",
                description=(
                    f"**{date_str}** • {len(member_results)} member(s) received external funds\n"
                    f"Net = received from external sources − sent back. "
                    f"Own alliance bank and **war loot excluded**."
                ),
                color=discord.Color.gold(),
                timestamp=datetime.now(timezone.utc),
            )

            if top_sources:
                src_lines = []
                for rank, (src_id, total_val) in enumerate(top_sources):
                    sname = source_names.get(src_id, f"Alliance #{src_id}")
                    src_lines.append(
                        f"{medals[rank]} **{sname}** — `${total_val:,.0f}` sent to members"
                    )
                overview.add_field(
                    name="🎯 Top Suspected Offshore Sources",
                    value="\n".join(src_lines),
                    inline=False,
                )

            top5_lines = []
            for nid, net_val, _, _, src_name in member_results[:5]:
                nname = nation_info.get(nid, str(nid))
                top5_lines.append(
                    f"🧑 [{nname}](https://politicsandwar.com/nation/id={nid}) — "
                    f"net `${net_val:,.0f}` (top source: **{src_name}**)"
                )
            overview.add_field(
                name="👥 Top Members by Net Received",
                value="\n".join(top5_lines),
                inline=False,
            )
            overview.set_footer(text=f"Page 1/{total_pages} • Offshore Finder")

            member_pages = []
            for page_idx in range(pages_needed):
                chunk = member_results[page_idx * PER_PAGE:(page_idx + 1) * PER_PAGE]
                embed = discord.Embed(
                    title=f"📋 Member Net Balances — {alliance_name} (pg {page_idx + 1}/{pages_needed})",
                    description=f"Net = received from external − sent to external in last {days}d. War loot excluded.",
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc),
                )
                for nid, net_val, net_bal, _, src_name in chunk:
                    nname     = nation_info.get(nid, str(nid))
                    bal_lines, _ = _format_balance(net_bal, prices)
                    field_val = (
                        ("\n".join(bal_lines[:5]) + ("\n…" if len(bal_lines) > 5 else ""))
                        if bal_lines else "No resources"
                    ) + f"\n↩️ Top source: **{src_name}**"
                    embed.add_field(
                        name=f"🧑 {nname} — net ${net_val:,.0f}",
                        value=field_val,
                        inline=False,
                    )
                embed.set_footer(text=f"Page {page_idx + 2}/{total_pages} • Offshore Finder")
                member_pages.append(embed)

            all_embeds = [overview] + member_pages
            view       = OffshoreView(all_embeds)
            msg        = await interaction.followup.send(embed=overview, view=view)
            view.message = msg

        except Exception as e:
            logger.error(f"Error in /offshore: {e}", exc_info=True)
            await interaction.followup.send(f"❌ An error occurred: {str(e)}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Offshore(bot))
