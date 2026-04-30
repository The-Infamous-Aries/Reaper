import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import logging

import Systems.Functions.emoji as emoji_mod
from Systems.Functions.db_paths import ALERTS_DB_STR as ALERTS_DB

logger = logging.getLogger(__name__)

VALID_RESOURCES = [
    "food", "coal", "oil", "uranium", "lead", "iron",
    "bauxite", "gasoline", "munitions", "steel", "aluminum", "credit"
]

# Embed colours keyed by direction
ALERT_COLORS = {
    "above": 0x2ecc71,  # green — price rose to your target
    "below": 0xe74c3c,  # red   — price fell to your target
}


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _setup_alerts_table():
    """
    Creates or migrates the rss_alerts table.
    Old schema had: user_id, resource, alert_type, threshold
    New schema has: user_id, resource, price_type, direction, threshold
    We drop and recreate if the old schema is detected.
    """
    async with aiosqlite.connect(ALERTS_DB) as conn:
        # Check if table exists and has the new columns already
        cur = await conn.execute("PRAGMA table_info(rss_alerts)")
        cols = {row[1] for row in await cur.fetchall()}

        if cols and 'price_type' not in cols:
            # Old schema detected — drop and recreate (old alerts are incompatible)
            logger.info("Migrating rss_alerts table to new schema (dropping old alerts).")
            await conn.execute("DROP TABLE rss_alerts")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rss_alerts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    TEXT    NOT NULL,
                resource   TEXT    NOT NULL,
                price_type TEXT    NOT NULL CHECK(price_type IN ('buy','sell')),
                direction  TEXT    NOT NULL CHECK(direction  IN ('above','below')),
                threshold  REAL    NOT NULL,
                UNIQUE(user_id, resource, price_type, direction)
            )
        """)
        await conn.commit()


async def _upsert_alert(user_id: str, resource: str, price_type: str,
                        direction: str, threshold: float):
    async with aiosqlite.connect(ALERTS_DB) as conn:
        await conn.execute("""
            INSERT INTO rss_alerts (user_id, resource, price_type, direction, threshold)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, resource, price_type, direction)
            DO UPDATE SET threshold = excluded.threshold
        """, (user_id, resource, price_type, direction, threshold))
        await conn.commit()


async def _remove_alert(user_id: str, resource: str,
                        price_type: str, direction: str) -> bool:
    async with aiosqlite.connect(ALERTS_DB) as conn:
        cur = await conn.execute(
            "DELETE FROM rss_alerts WHERE user_id=? AND resource=? AND price_type=? AND direction=?",
            (user_id, resource, price_type, direction)
        )
        await conn.commit()
        return cur.rowcount > 0


async def _delete_alert_by_id(alert_id: int):
    async with aiosqlite.connect(ALERTS_DB) as conn:
        await conn.execute("DELETE FROM rss_alerts WHERE id=?", (alert_id,))
        await conn.commit()


async def _get_user_alerts(user_id: str):
    async with aiosqlite.connect(ALERTS_DB) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT resource, price_type, direction, threshold
               FROM rss_alerts WHERE user_id=?
               ORDER BY resource, price_type, direction""",
            (user_id,)
        )
        return await cur.fetchall()


async def _get_all_alerts():
    async with aiosqlite.connect(ALERTS_DB) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT id, user_id, resource, price_type, direction, threshold FROM rss_alerts"
        )
        return await cur.fetchall()


# ---------------------------------------------------------------------------
# Alert checker — called by TimedQueries after saving resource data
# ---------------------------------------------------------------------------

async def check_price_alerts(bot: commands.Bot, resource_data: dict):
    """
    Called after each timed resource save. Fires and deletes triggered alerts.

    resource_data keys per resource: 'best_sell', 'best_buy', 'avg'

    Trigger logic:
      price_type='buy',  direction='above' → fires when best_buy  >= threshold
      price_type='buy',  direction='below' → fires when best_buy  <= threshold
      price_type='sell', direction='above' → fires when best_sell >= threshold
      price_type='sell', direction='below' → fires when best_sell <= threshold
    """
    alerts = await _get_all_alerts()
    if not alerts:
        return

    for alert in alerts:
        resource   = alert["resource"]
        price_type = alert["price_type"]
        direction  = alert["direction"]
        threshold  = alert["threshold"]
        user_id    = alert["user_id"]
        alert_id   = alert["id"]

        prices = resource_data.get(resource)
        if not prices:
            continue

        price_key = "best_buy" if price_type == "buy" else "best_sell"
        current = prices.get(price_key, 0)
        if current <= 0:
            continue

        triggered = (current >= threshold) if direction == "above" else (current <= threshold)
        if not triggered:
            continue

        try:
            user = await bot.fetch_user(int(user_id))
            if user:
                await user.send(embed=_build_alert_embed(
                    resource, price_type, direction, threshold, current
                ))
        except discord.Forbidden:
            logger.warning(f"Cannot DM user {user_id} ({resource} {price_type} {direction}).")
        except Exception as e:
            logger.error(f"Alert send failed for {user_id}: {e}", exc_info=True)
        finally:
            await _delete_alert_by_id(alert_id)


def _build_alert_embed(resource: str, price_type: str, direction: str,
                       threshold: float, current: float) -> discord.Embed:
    emoji   = emoji_mod.resource_emoji(resource) or "📦"
    dir_str = "risen to/above" if direction == "above" else "dropped to/below"

    embed = discord.Embed(
        title=f"{emoji} {resource.title()} Price Alert",
        description=(
            f"The **best {price_type} price** for {emoji} **{resource.title()}** "
            f"has {dir_str} your threshold.\n\n"
            f"**Your threshold:** ${threshold:,.2f} ppu\n"
            f"**Current {price_type} price:** ${current:,.2f} ppu"
        ),
        color=ALERT_COLORS[direction],
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text="PnW Resource Alert • This alert has been removed after firing")
    return embed


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class RssAlerts(commands.Cog):
    """Resource price alert commands for Politics & War."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        await _setup_alerts_table()
        logger.info("RssAlerts cog loaded.")

    # --- autocompletes ---

    async def resource_autocomplete(self, interaction: discord.Interaction, current: str):
        return [
            app_commands.Choice(name=r.title(), value=r)
            for r in VALID_RESOURCES if current.lower() in r
        ]

    # --- /rss_alert_set ---

    @commands.hybrid_command(
        name="rss_alert_set",
        description="Set a price alert — choose resource, buy/sell price, direction, and PPU threshold."
    )
    @app_commands.describe(
        resource="The resource to watch",
        price_type="Which market price to watch: the best Buy price or the best Sell price",
        direction="Trigger when the price rises AT/ABOVE or drops AT/BELOW your threshold",
        threshold="The PPU value that triggers the alert"
    )
    @app_commands.autocomplete(resource=resource_autocomplete)
    @app_commands.choices(
        price_type=[
            app_commands.Choice(name="Buy price  (best buy offer)",  value="buy"),
            app_commands.Choice(name="Sell price (best sell offer)", value="sell"),
        ],
        direction=[
            app_commands.Choice(name="At / Above  ≥  (price rises to your PPU)", value="above"),
            app_commands.Choice(name="At / Below  ≤  (price drops to your PPU)", value="below"),
        ]
    )
    async def rss_alert_set(
        self,
        ctx: commands.Context,
        resource: str,
        price_type: str,
        direction: str,
        threshold: float
    ):
        if isinstance(ctx.interaction, discord.Interaction):
            await ctx.interaction.response.defer(ephemeral=True)

        resource = resource.lower()
        if resource not in VALID_RESOURCES:
            return await ctx.send(
                f"Unknown resource `{resource}`. Valid: {', '.join(VALID_RESOURCES)}",
                ephemeral=True
            )
        if threshold <= 0:
            return await ctx.send("Threshold must be greater than 0.", ephemeral=True)

        await _upsert_alert(str(ctx.author.id), resource, price_type, direction, threshold)

        emoji   = emoji_mod.resource_emoji(resource) or "📦"
        dir_str = "rises to/above" if direction == "above" else "drops to/below"
        comparator = "≥" if direction == "above" else "≤"

        embed = discord.Embed(
            title="✅ Alert Set",
            description=(
                f"You'll receive a DM when the **best {price_type} price** for "
                f"{emoji} **{resource.title()}** {dir_str} "
                f"**${threshold:,.2f} ppu** ({comparator} {threshold:,.2f}).\n\n"
                f"The alert fires once then is removed."
            ),
            color=0x3498db
        )
        await ctx.send(embed=embed, ephemeral=True)

    # --- /rss_alert_remove ---

    @commands.hybrid_command(
        name="rss_alert_remove",
        description="Remove a specific price alert before it fires."
    )
    @app_commands.describe(
        resource="The resource",
        price_type="Buy or Sell price alert",
        direction="Above or Below direction"
    )
    @app_commands.autocomplete(resource=resource_autocomplete)
    @app_commands.choices(
        price_type=[
            app_commands.Choice(name="Buy price",  value="buy"),
            app_commands.Choice(name="Sell price", value="sell"),
        ],
        direction=[
            app_commands.Choice(name="At / Above ≥", value="above"),
            app_commands.Choice(name="At / Below ≤", value="below"),
        ]
    )
    async def rss_alert_remove(
        self,
        ctx: commands.Context,
        resource: str,
        price_type: str,
        direction: str
    ):
        if isinstance(ctx.interaction, discord.Interaction):
            await ctx.interaction.response.defer(ephemeral=True)

        removed = await _remove_alert(
            str(ctx.author.id), resource.lower(), price_type, direction
        )
        comparator = "≥" if direction == "above" else "≤"
        if removed:
            await ctx.send(
                f"Removed your **{price_type} {comparator}** alert for **{resource.title()}**.",
                ephemeral=True
            )
        else:
            await ctx.send(
                f"No **{price_type} {comparator}** alert found for **{resource.title()}**.",
                ephemeral=True
            )

    # --- /rss_alert_list ---

    @commands.hybrid_command(
        name="rss_alert_list",
        description="List all your active resource price alerts."
    )
    async def rss_alert_list(self, ctx: commands.Context):
        if isinstance(ctx.interaction, discord.Interaction):
            await ctx.interaction.response.defer(ephemeral=True)

        alerts = await _get_user_alerts(str(ctx.author.id))
        if not alerts:
            return await ctx.send("You have no active resource price alerts.", ephemeral=True)

        lines = []
        for a in alerts:
            emoji      = emoji_mod.resource_emoji(a["resource"]) or "📦"
            comparator = "≥" if a["direction"] == "above" else "≤"
            lines.append(
                f"{emoji} **{a['resource'].title()}** — "
                f"best **{a['price_type']}** {comparator} **${a['threshold']:,.2f} ppu**"
            )

        embed = discord.Embed(
            title="📋 Your Resource Price Alerts",
            description="\n".join(lines),
            color=0x3498db
        )
        await ctx.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(RssAlerts(bot))
