import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone

from Systems.Functions.irs_wars_db import IRSWarsDB
from Systems.Functions.db_paths import NW_WARS_DB_STR as NW_DB_PATH
from Systems.Functions.nation_emoji_store import get_nation_emoji, strip_emoji_prefix
from Systems.PnW.Util.war_calc import get_resource_prices, calculate_unit_cost
from Systems.Functions.emoji import resource_emoji

NW_ALLIANCE_ID = 14225

TIME_CHOICES = [
    app_commands.Choice(name="1 Day",    value="1d"),
    app_commands.Choice(name="3 Days",   value="3d"),
    app_commands.Choice(name="1 Week",   value="1w"),
    app_commands.Choice(name="2 Weeks",  value="2w"),
    app_commands.Choice(name="1 Month",  value="1m"),
    app_commands.Choice(name="3 Months", value="3m"),
    app_commands.Choice(name="6 Months", value="6m"),
    app_commands.Choice(name="1 Year",   value="1y"),
    app_commands.Choice(name="All Time", value="all"),
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_time(time_str: str) -> Optional[datetime]:
    if not time_str or time_str == "all":
        return None
    now = datetime.now(timezone.utc)
    mapping = {
        "1d": timedelta(days=1),   "3d": timedelta(days=3),
        "1w": timedelta(weeks=1),  "2w": timedelta(weeks=2),
        "1m": timedelta(days=30),  "3m": timedelta(days=90),
        "6m": timedelta(days=180), "1y": timedelta(days=365),
    }
    delta = mapping.get(time_str)
    return now - delta if delta else None


def _strip_emoji(value: str) -> str:
    if not value:
        return value
    parts = value.split(" ", 1)
    if len(parts) == 2 and len(parts[0]) <= 2:
        return parts[1].strip()
    return value.strip()


def _link(name: str, nation_id: Any) -> str:
    if nation_id:
        return f"[{name}](https://politicsandwar.com/nation/id={nation_id})"
    return name


def _fmt(v: float) -> str:
    return f"${v:,.0f}"


def _winner(a: float, b: float, low_better: bool = False):
    if a == b:
        return "➡️", "➡️"
    if low_better:
        return ("✅", "❌") if a < b else ("❌", "✅")
    return ("✅", "❌") if a > b else ("❌", "✅")


# ── Stat accumulator ──────────────────────────────────────────────────────────

RESOURCES = [
    "coal", "oil", "uranium", "iron", "bauxite", "lead",
    "gasoline", "munitions", "steel", "aluminum", "food",
]


class NationWarStats:
    def __init__(self, nation_id: int, nation_name: str):
        self.nation_id   = nation_id
        self.nation_name = nation_name
        self.wars_count  = 0
        self.unit_cost   = 0.0
        self.infra_cost  = 0.0
        self.bomb_cost   = 0.0
        # own consumption (gas + mun used)
        self.consumption_cost = 0.0
        # own improvements destroyed value
        self.improvements_lost = 0.0

        # damage inflicted on enemies — matches watch page total_damages formula
        self.enemy_unit_dmg        = 0.0   # enemy unit costs
        self.enemy_infra_dmg       = 0.0   # enemy infra destroyed value
        self.enemy_consumption_dmg = 0.0   # enemy gas+mun consumed (buy price)
        self.enemy_improvements_dmg= 0.0   # enemy improvements destroyed value
        self.enemy_loot_lost       = 0.0   # cash + resources looted FROM enemy
        self.enemy_money_destroyed = 0.0   # money destroyed in enemy cities

        self.loot_gained = 0.0
        self.loot_lost   = 0.0
        self.missiles_used = 0
        self.nukes_used    = 0
        # per-resource net loot (gained - lost) for display
        self.resource_loot_net: Dict[str, float] = {r: 0.0 for r in RESOURCES}
        self.money_loot_net: float = 0.0

    @property
    def gross_cost(self) -> float:
        return self.unit_cost + self.infra_cost + self.bomb_cost + self.consumption_cost + self.improvements_lost

    @property
    def total_damage(self) -> float:
        """Matches watch page total_damages: all costs inflicted on the enemy."""
        return (
            self.enemy_unit_dmg
            + self.enemy_infra_dmg
            + self.enemy_consumption_dmg
            + self.enemy_improvements_dmg
            + self.enemy_loot_lost
            + self.enemy_money_destroyed
        )

    @property
    def net(self) -> float:
        return self.total_damage - self.gross_cost

    @property
    def net_loot(self) -> float:
        return self.loot_gained - self.loot_lost

    def add_war(self, war: Dict[str, Any], is_attacker: bool, prices: Dict[str, Any],
                attacks: Optional[List[Dict[str, Any]]] = None):
        self.wars_count += 1
        sell = prices.get("sell", {})
        buy  = prices.get("buy",  {})

        if is_attacker:
            sl = war.get("att_soldiers_lost", 0) or 0
            tl = war.get("att_tanks_lost",    0) or 0
            al = war.get("att_aircraft_lost", 0) or 0
            hl = war.get("att_ships_lost",    0) or 0
            iv = war.get("att_infra_destroyed_value", 0) or 0
            esl = war.get("def_soldiers_lost", 0) or 0
            etl = war.get("def_tanks_lost",    0) or 0
            eal = war.get("def_aircraft_lost", 0) or 0
            ehl = war.get("def_ships_lost",    0) or 0
            eiv = war.get("def_infra_destroyed_value", 0) or 0
            nation_id = war.get("att_id")
            enemy_id  = war.get("def_id")
        else:
            sl = war.get("def_soldiers_lost", 0) or 0
            tl = war.get("def_tanks_lost",    0) or 0
            al = war.get("def_aircraft_lost", 0) or 0
            hl = war.get("def_ships_lost",    0) or 0
            iv = war.get("def_infra_destroyed_value", 0) or 0
            esl = war.get("att_soldiers_lost", 0) or 0
            etl = war.get("att_tanks_lost",    0) or 0
            eal = war.get("att_aircraft_lost", 0) or 0
            ehl = war.get("att_ships_lost",    0) or 0
            eiv = war.get("att_infra_destroyed_value", 0) or 0
            nation_id = war.get("def_id")
            enemy_id  = war.get("att_id")

        atk_list = attacks or []

        # ── Missiles / nukes fired (attack rows, war-level cols are always 0) ──
        mu = sum(
            1 for a in atk_list
            if str(a.get("type", "")).upper() in ("MISSILE", "MISSILEFAIL")
            and a.get("attacker_id") == nation_id
        )
        nu = sum(
            1 for a in atk_list
            if str(a.get("type", "")).upper() in ("NUKE", "NUKEFAIL")
            and a.get("attacker_id") == nation_id
        )
        # enemy missiles/nukes fired at us
        emu = sum(
            1 for a in atk_list
            if str(a.get("type", "")).upper() in ("MISSILE", "MISSILEFAIL")
            and a.get("attacker_id") == enemy_id
        )
        enu = sum(
            1 for a in atk_list
            if str(a.get("type", "")).upper() in ("NUKE", "NUKEFAIL")
            and a.get("attacker_id") == enemy_id
        )

        # ── Own unit costs (use war_calc's calculate_unit_cost with BUY prices) ──
        self.unit_cost += (
            sl * calculate_unit_cost("soldiers", buy)
            + tl * calculate_unit_cost("tanks",    buy)
            + al * calculate_unit_cost("aircraft", buy)
            + hl * calculate_unit_cost("ships",    buy)
        )
        self.infra_cost += iv

        # Own bomb cost
        self.bomb_cost += mu * calculate_unit_cost("missiles", buy)
        self.bomb_cost += nu * calculate_unit_cost("nukes",    buy)
        self.missiles_used += mu
        self.nukes_used    += nu

        # Own consumption (gas + mun used in conventional attacks, sell price)
        own_gas = (war.get("att_gas_used", 0) or 0) if is_attacker else (war.get("def_gas_used", 0) or 0)
        own_mun = (war.get("att_mun_used", 0) or 0) if is_attacker else (war.get("def_mun_used", 0) or 0)
        self.consumption_cost += own_gas * sell.get("gasoline", 0) + own_mun * sell.get("munitions", 0)

        # ── Enemy unit costs (damage we dealt, BUY prices) ─────────────────
        self.enemy_unit_dmg += (
            esl * calculate_unit_cost("soldiers", buy)
            + etl * calculate_unit_cost("tanks",    buy)
            + eal * calculate_unit_cost("aircraft", buy)
            + ehl * calculate_unit_cost("ships",    buy)
            + emu * calculate_unit_cost("missiles", buy)
            + enu * calculate_unit_cost("nukes",    buy)
        )
        self.enemy_infra_dmg += eiv

        # Enemy consumption (gas + mun they used, buy price — matches war_calc)
        e_gas = (war.get("def_gas_used", 0) or 0) if is_attacker else (war.get("att_gas_used", 0) or 0)
        e_mun = (war.get("def_mun_used", 0) or 0) if is_attacker else (war.get("att_mun_used", 0) or 0)
        self.enemy_consumption_dmg += e_gas * buy.get("gasoline", 0) + e_mun * buy.get("munitions", 0)

        # Enemy money destroyed + loot lost (from attack rows)
        for a in atk_list:
            if a.get("defender_id") == enemy_id:
                self.enemy_money_destroyed += (a.get("money_destroyed", 0) or 0)
                # enemy loot lost = what we looted from them
                self.enemy_loot_lost += (a.get("money_looted", 0) or 0) + (a.get("money_stolen", 0) or 0)
                for r in RESOURCES:
                    amt = a.get(f"{r}_looted", 0) or 0
                    if amt:
                        self.enemy_loot_lost += amt * sell.get(r, 0)

    def add_attack_loot(self, attack: Dict[str, Any], prices: Dict[str, Any]):
        sell = prices.get("sell", {})
        is_att = (attack.get("attacker_id") == self.nation_id)
        sign = 1 if is_att else -1
        money = (attack.get("money_looted", 0) or 0)
        value = money
        self.money_loot_net += sign * money
        for r in RESOURCES:
            amt = (attack.get(f"{r}_looted", 0) or 0)
            value += amt * sell.get(r, 0)
            self.resource_loot_net[r] += sign * amt
        if is_att:
            self.loot_gained += value
        else:
            self.loot_lost += value


# ── Paginated view ────────────────────────────────────────────────────────────

class CompareView(discord.ui.View):
    PAGE_LABELS = ["📊 Summary", "⚔️ Nation 1", "⚔️ Nation 2"]

    def __init__(self, embeds: List[discord.Embed]):
        super().__init__(timeout=180)
        self.embeds = embeds
        self.page   = 0
        self._refresh()

    def _refresh(self):
        self.prev_btn.disabled = (self.page == 0)
        self.next_btn.disabled = (self.page == len(self.embeds) - 1)
        self.page_btn.label    = f"{self.PAGE_LABELS[self.page]}  ({self.page + 1}/{len(self.embeds)})"

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self._refresh()
        await interaction.response.edit_message(embed=self.embeds[self.page], view=self)

    @discord.ui.button(label="Page", style=discord.ButtonStyle.primary, disabled=True)
    async def page_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._refresh()
        await interaction.response.edit_message(embed=self.embeds[self.page], view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ── Embed builders ────────────────────────────────────────────────────────────

def _summary_embed(s1: NationWarStats, s2: NationWarStats,
                   n1_id: Any, n2_id: Any, time_label: str) -> discord.Embed:
    n1_link = _link(s1.nation_name, n1_id)
    n2_link = _link(s2.nation_name, n2_id)

    embed = discord.Embed(
        title="⚔️ War Performance Comparison",
        description=f"{n1_link}  vs  {n2_link}\n**Time Range:** {time_label}",
        color=discord.Color.gold(),
        timestamp=datetime.now(timezone.utc),
    )

    # Wars fought
    w1, w2 = _winner(s1.wars_count, s2.wars_count)
    embed.add_field(name="🗡️ Wars Fought",
        value=f"{w1} **{s1.nation_name}:** {s1.wars_count}\n{w2} **{s2.nation_name}:** {s2.wars_count}",
        inline=True)

    # Gross cost (lower = better)
    c1, c2 = _winner(s1.gross_cost, s2.gross_cost, low_better=True)
    embed.add_field(name="💸 Total Cost",
        value=f"{c1} **{s1.nation_name}:** {_fmt(s1.gross_cost)}\n{c2} **{s2.nation_name}:** {_fmt(s2.gross_cost)}",
        inline=True)

    embed.add_field(name="​", value="​", inline=True)

    # Damage dealt (higher = better)
    d1, d2 = _winner(s1.total_damage, s2.total_damage)
    embed.add_field(name="💥 Damage Dealt",
        value=f"{d1} **{s1.nation_name}:** {_fmt(s1.total_damage)}\n{d2} **{s2.nation_name}:** {_fmt(s2.total_damage)}",
        inline=True)

    # War net (higher = better)
    n1w, n2w = _winner(s1.net, s2.net)
    embed.add_field(name="📊 War Net",
        value=f"{n1w} **{s1.nation_name}:** {_fmt(s1.net)}\n{n2w} **{s2.nation_name}:** {_fmt(s2.net)}",
        inline=True)

    embed.add_field(name="​", value="​", inline=True)

    # Net loot (higher = better)
    l1, l2 = _winner(s1.net_loot, s2.net_loot)
    embed.add_field(name="💰 Net Loot",
        value=f"{l1} **{s1.nation_name}:** {_fmt(s1.net_loot)}\n{l2} **{s2.nation_name}:** {_fmt(s2.net_loot)}",
        inline=True)

    # Bomb cost (lower = better)
    b1, b2 = _winner(s1.bomb_cost, s2.bomb_cost, low_better=True)
    embed.add_field(name="🚀 Bomb Cost",
        value=f"{b1} **{s1.nation_name}:** {_fmt(s1.bomb_cost)}\n{b2} **{s2.nation_name}:** {_fmt(s2.bomb_cost)}",
        inline=True)

    embed.add_field(name="​", value="​", inline=True)

    # Verdict
    scores: Dict[str, int] = {s1.nation_name: 0, s2.nation_name: 0}
    for a, b, low in [
        (s1.gross_cost,   s2.gross_cost,   True),
        (s1.total_damage, s2.total_damage,  False),
        (s1.net,          s2.net,           False),
        (s1.net_loot,     s2.net_loot,      False),
        (s1.bomb_cost,    s2.bomb_cost,     True),
    ]:
        if a == b:
            continue
        winner = s1.nation_name if (a < b if low else a > b) else s2.nation_name
        scores[winner] += 1

    sc1, sc2 = scores[s1.nation_name], scores[s2.nation_name]
    if sc1 > sc2:
        verdict = f"🏆 **{s1.nation_name}** edges out overall ({sc1}-{sc2})"
    elif sc2 > sc1:
        verdict = f"🏆 **{s2.nation_name}** edges out overall ({sc2}-{sc1})"
    else:
        verdict = "🤝 **Dead even** across all categories"

    embed.add_field(name="🏅 Verdict", value=verdict, inline=False)
    embed.set_footer(text="Page 1/3 — use ▶ for nation breakdowns")
    return embed


def _nation_embed(s: NationWarStats, nation_id: Any,
                  page_num: int, time_label: str) -> discord.Embed:
    nation_link = _link(s.nation_name, nation_id)
    embed = discord.Embed(
        title=f"📋 {s.nation_name} — War Breakdown",
        description=f"{nation_link}\n**Time Range:** {time_label}  |  **Wars:** {s.wars_count}",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(name="💸 Costs",
        value=(
            f"Unit Losses:  `{_fmt(s.unit_cost)}`\n"
            f"Infra Lost:   `{_fmt(s.infra_cost)}`\n"
            f"Bombs Fired:  `{_fmt(s.bomb_cost)}`\n"
            f"Consumption:  `{_fmt(s.consumption_cost)}`\n"
            f"**Gross Cost: `{_fmt(s.gross_cost)}`**"
        ), inline=True)

    embed.add_field(name="💥 Damage Dealt",
        value=(
            f"Enemy Units:  `{_fmt(s.enemy_unit_dmg)}`\n"
            f"Enemy Infra:  `{_fmt(s.enemy_infra_dmg)}`\n"
            f"Enemy Consump:`{_fmt(s.enemy_consumption_dmg)}`\n"
            f"Loot Taken:   `{_fmt(s.enemy_loot_lost)}`\n"
            f"Money Destr:  `{_fmt(s.enemy_money_destroyed)}`\n"
            f"**Total Dmg:  `{_fmt(s.total_damage)}`**"
        ), inline=True)

    embed.add_field(name="​", value="​", inline=True)

    net_icon = "🟢" if s.net >= 0 else "🔴"
    embed.add_field(name="📊 Net Performance",
        value=(
            f"Damage:    `{_fmt(s.total_damage)}`\n"
            f"Cost:      `{_fmt(s.gross_cost)}`\n"
            f"{net_icon} **War Net: `{_fmt(s.net)}`**"
        ), inline=True)

    loot_icon = "🟢" if s.net_loot >= 0 else "🔴"
    # Build per-resource loot lines using resource_emoji
    loot_lines = []
    if s.money_loot_net != 0:
        sign = "+" if s.money_loot_net >= 0 else ""
        loot_lines.append(f"💵 {sign}{s.money_loot_net:,.0f}")
    for r in RESOURCES:
        amt = s.resource_loot_net.get(r, 0)
        if abs(amt) >= 1:
            emoji = resource_emoji(r) or r.title()
            sign = "+" if amt >= 0 else ""
            loot_lines.append(f"{emoji} {sign}{amt:,.0f}")
    loot_detail = "\n".join(loot_lines) if loot_lines else "No loot data"
    embed.add_field(name="💰 Loot",
        value=(
            f"Gained:    `{_fmt(s.loot_gained)}`\n"
            f"Lost:      `{_fmt(s.loot_lost)}`\n"
            f"{loot_icon} **Net Loot: `{_fmt(s.net_loot)}`**"
        ), inline=True)
    if loot_lines:
        embed.add_field(name="📦 Resource Loot (net)", value=loot_detail[:1024], inline=True)

    embed.add_field(name="​", value="​", inline=True)

    embed.add_field(name="🚀 Bombs Used",
        value=(
            f"Missiles: `{s.missiles_used:,}`\n"
            f"Nukes:    `{s.nukes_used:,}`\n"
            f"Cost:     `{_fmt(s.bomb_cost)}`"
        ), inline=True)

    embed.set_footer(text=f"Page {page_num}/3 — use ◀ ▶ to navigate")
    return embed


# ── Cog ───────────────────────────────────────────────────────────────────────

class CompareWars(commands.Cog):
    """Compare two Night\'s Watch nations\' war performance head-to-head."""

    def __init__(self, bot):
        self.bot    = bot
        self.logger = logging.getLogger(__name__)

    async def _get_nw_nations(self) -> List[Dict[str, Any]]:
        try:
            from PnWHarvester.db.global_nations_db import GlobalNationsDB
            from Systems.Functions.db_paths import GLOBAL_NATIONS_DB as _GNDB, NW_ALLIANCE_ID
            db = GlobalNationsDB(str(_GNDB))
            return await db.get_nations_by_alliance(NW_ALLIANCE_ID)
        except Exception as e:
            self.logger.warning(f"compare_wars: could not load NW nations: {e}")
            return []

    def _resolve(self, value: str, nations: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        clean = _strip_emoji(value)
        for n in nations:
            if clean.isdigit() and str(n.get("id")) == clean:
                return n
            if n.get("nation_name", "").lower() == clean.lower():
                return n
        for n in nations:
            if clean.lower() in n.get("nation_name", "").lower():
                return n
        return None

    async def _collect(self, nation_id: int, nation_name: str,
                       after: Optional[datetime], prices: Dict[str, Any]) -> NationWarStats:
        db = IRSWarsDB(NW_DB_PATH)
        start_date = after.date() if after else None
        end_date   = datetime.now(timezone.utc).date()

        att_wars = await db.get_wars_by_alliance_in_range(
            NW_ALLIANCE_ID, role="attacker", start_date=start_date, end_date=end_date)
        def_wars = await db.get_wars_by_alliance_in_range(
            NW_ALLIANCE_ID, role="defender", start_date=start_date, end_date=end_date)

        seen: set = set()
        nation_wars: List[Dict[str, Any]] = []
        for w in att_wars + def_wars:
            wid = w["id"]
            if wid in seen:
                continue
            if w.get("att_id") == nation_id or w.get("def_id") == nation_id:
                seen.add(wid)
                nation_wars.append(w)

        stats = NationWarStats(nation_id, nation_name)
        if not nation_wars:
            return stats

        war_ids = [w["id"] for w in nation_wars]
        attacks_by_war = await db.get_attacks_for_wars(war_ids)

        for war in nation_wars:
            is_att = (war.get("att_id") == nation_id)
            war_attacks = attacks_by_war.get(war["id"], [])
            stats.add_war(war, is_att, prices, attacks=war_attacks)
            for atk in war_attacks:
                a_id = atk.get("attacker_id")
                d_id = atk.get("defender_id")
                if a_id == nation_id or d_id == nation_id:
                    stats.add_attack_loot(atk, prices)

        return stats

    # ── Autocomplete ──────────────────────────────────────────────────────────

    async def nation1_autocomplete(self, interaction: discord.Interaction,
                                   current: str) -> List[app_commands.Choice[str]]:
        try:
            from Systems.Functions.autocomplete_utils import nation_autocomplete
            return await nation_autocomplete(current, nw_only=False, limit=25)
        except Exception as e:
            logger.error(f"Error in compare_wars nation1 autocomplete: {e}")
            return []

    async def nation2_autocomplete(self, interaction: discord.Interaction,
                                   current: str) -> List[app_commands.Choice[str]]:
        try:
            from Systems.Functions.autocomplete_utils import nation_autocomplete
            # Get nation1 value to exclude it from nation2 choices
            options_map: dict = {}
            for opt in (interaction.data or {}).get("options", []):
                options_map[opt["name"]] = opt.get("value", "")
            n1_clean = _strip_emoji(options_map.get("nation1", "")).lower()
            
            # Get all nations and filter out nation1
            all_choices = await nation_autocomplete(current, nw_only=False, limit=25)
            filtered_choices = []
            for choice in all_choices:
                if choice.value.lower() != n1_clean:
                    filtered_choices.append(choice)
            return filtered_choices
        except Exception as e:
            logger.error(f"Error in compare_wars nation2 autocomplete: {e}")
            return []

    # ── Command ───────────────────────────────────────────────────────────────

    @app_commands.command(
        name="compare_wars",
        description="Compare two Night\'s Watch nations\' war performance head-to-head",
    )
    @app_commands.describe(
        nation1="First NW nation to compare",
        nation2="Second NW nation to compare (cannot be the same as Nation 1)",
        time="How far back to look (defaults to All Time)",
    )
    @app_commands.choices(time=TIME_CHOICES)
    @app_commands.autocomplete(nation1=nation1_autocomplete, nation2=nation2_autocomplete)
    async def compare_wars(self, interaction: discord.Interaction,
                           nation1: str, nation2: str,
                           time: Optional[str] = "all"):
        await interaction.response.defer()
        try:
            nations = await self._get_nw_nations()
            n1_data = self._resolve(nation1, nations)
            n2_data = self._resolve(nation2, nations)

            def _not_found(val: str):
                return discord.Embed(
                    title="❌ Nation Not Found",
                    description=f"Could not find **{_strip_emoji(val)}** in the Night\'s Watch nations database.",
                    color=discord.Color.red(),
                )

            if not n1_data:
                await interaction.followup.send(embed=_not_found(nation1)); return
            if not n2_data:
                await interaction.followup.send(embed=_not_found(nation2)); return

            n1_id, n2_id = n1_data["id"], n2_data["id"]
            n1_name = n1_data.get("nation_name", f"Nation #{n1_id}")
            n2_name = n2_data.get("nation_name", f"Nation #{n2_id}")

            if n1_id == n2_id:
                await interaction.followup.send(embed=discord.Embed(
                    title="❌ Same Nation",
                    description="You cannot compare a nation against itself.",
                    color=discord.Color.red(),
                )); return

            after = _parse_time(time or "all")
            time_label = {
                "1d": "Last 1 Day",   "3d": "Last 3 Days",
                "1w": "Last 1 Week",  "2w": "Last 2 Weeks",
                "1m": "Last 1 Month", "3m": "Last 3 Months",
                "6m": "Last 6 Months","1y": "Last 1 Year",
                "all": "All Time",
            }.get(time or "all", "All Time")

            prices = await get_resource_prices() or {"sell": {}, "buy": {}}

            s1, s2 = await asyncio.gather(
                self._collect(n1_id, n1_name, after, prices),
                self._collect(n2_id, n2_name, after, prices),
            )

            embeds = [
                _summary_embed(s1, s2, n1_id, n2_id, time_label),
                _nation_embed(s1, n1_id, 2, time_label),
                _nation_embed(s2, n2_id, 3, time_label),
            ]
            view = CompareView(embeds)
            await interaction.followup.send(embed=embeds[0], view=view)

        except Exception as e:
            self.logger.error(f"compare_wars error: {e}", exc_info=True)
            await interaction.followup.send(embed=discord.Embed(
                title="❌ Error",
                description="Something went wrong generating the comparison. Please try again.",
                color=discord.Color.red(),
            ))


async def setup(bot):
    await bot.add_cog(CompareWars(bot))
