"""
Admin Cog - Houses the administrative commands for the bot.
"""

import discord
from discord.ext import commands
from discord import app_commands
from typing import List

from Systems.Functions.config import ARIES_USER_ID, ADMIN_USER_ID
from Systems.Functions.utils import cleanup_service_ports
from Systems.info import UsagePaginatorView


PAGE_LABELS = {
    "nations":     "The Flame (Nations)",
    "watch":       "War Stats",
    "leaderboard": "Leaderboards",
    "raids":       "Raid Finder",
}

# Shown in the autocomplete dropdown
_PAGE_CHOICES = [
    ("All Pages",              "all"),
    ("The Flame (Nations)",    "nations"),
    ("War Stats",              "watch"),
    ("Leaderboards",           "leaderboard"),
    ("Raid Finder",            "raids"),
]


async def _pages_autocomplete(
    interaction: discord.Interaction, current: str
) -> List[app_commands.Choice[str]]:
    """
    Autocomplete for the pages argument.
    Supports comma-separated multi-select: already-chosen values are filtered
    out so the user keeps seeing only what they haven't picked yet.
    """
    # Split on comma — everything before the last comma is already chosen
    parts = current.split(",")
    already = {p.strip().lower() for p in parts[:-1] if p.strip()}
    typing  = parts[-1].strip().lower()

    choices = []
    for label, value in _PAGE_CHOICES:
        # Skip values already in the list (except 'all' which resets everything)
        if value != "all" and value in already:
            continue
        if value == "all" and already:
            continue  # 'all' only makes sense as the sole selection
        if typing and typing not in label.lower() and typing not in value.lower():
            continue

        # Build the full string the argument will become when this choice is picked
        if already:
            display_val = ", ".join(sorted(already)) + ", " + value
        else:
            display_val = value

        choices.append(app_commands.Choice(name=label, value=display_val))
        if len(choices) == 25:
            break

    return choices


class Admin(commands.Cog):
    """Administrative commands for bot management."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="shutdown", description="Securely shuts down the bot.")
    @commands.is_owner()
    async def shutdown(self, ctx: commands.Context):
        """Securely shuts down the bot, can only be used by the bot owner."""
        if ctx.author.id != ARIES_USER_ID:
            await ctx.send("You do not have permission to use this command.", ephemeral=True)
            return

        await ctx.send("Shutting down...", ephemeral=True)
        self.bot.logger.info(f"Shutdown command initiated by {ctx.author} (ID: {ctx.author.id})")
        cleanup_service_ports()
        await self.bot.close()

    @commands.hybrid_command(name="usage", description="Shows bot usage statistics and allows for management.")
    @commands.is_owner()
    async def usage(self, ctx: commands.Context):
        """Shows bot usage and allows for server/user management."""
        if ctx.author.id != ADMIN_USER_ID:
            await ctx.send("You do not have permission to use this command.", ephemeral=True)
            return

        try:
            view = UsagePaginatorView(self.bot, ADMIN_USER_ID)
            await view._init_data()
            embed = view.get_embed()
            message = await ctx.send(embed=embed, view=view, ephemeral=True)
            view.message = message
        except Exception as e:
            await ctx.send(f"Error loading usage view: {e}", ephemeral=True)

    @app_commands.command(
        name="they_shall_pass",
        description="Grant or revoke a user's access to restricted dashboard pages.",
    )
    @app_commands.describe(
        user="The Discord member to grant or revoke access for",
        action="Grant or revoke access",
        pages="Which pages — pick from the dropdown, add more by typing a comma then selecting again",
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Grant",  value="grant"),
        app_commands.Choice(name="Revoke", value="revoke"),
    ])
    @app_commands.autocomplete(pages=_pages_autocomplete)
    async def they_shall_pass(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        action: app_commands.Choice[str],
        pages: str = "all",
    ):
        """Grant or revoke per-page dashboard access. Aries only."""
        if interaction.user.id != ARIES_USER_ID:
            await interaction.response.send_message(
                "You do not have permission to use this command.", ephemeral=True
            )
            return

        from Systems.Functions.page_access import (
            grant_access, revoke_access, get_allowed_pages, ALL_PAGES,
        )

        # ── Parse pages ───────────────────────────────────────────────────────
        raw_parts = {p.strip().lower() for p in pages.split(",") if p.strip()}

        if not raw_parts or "all" in raw_parts:
            target_pages = set(ALL_PAGES)
        else:
            invalid = raw_parts - set(ALL_PAGES)
            if invalid:
                await interaction.response.send_message(
                    f"❌ Unknown page(s): `{'`, `'.join(sorted(invalid))}`. "
                    f"Valid: `{'`, `'.join(sorted(ALL_PAGES))}`",
                    ephemeral=True,
                )
                return
            target_pages = raw_parts

        page_names = ", ".join(
            f"**{PAGE_LABELS.get(p, p)}**" for p in sorted(target_pages)
        )

        # ── Execute ───────────────────────────────────────────────────────────
        if action.value == "grant":
            success = await grant_access(user.id, interaction.user.id, target_pages)
            if not success:
                await interaction.response.send_message(
                    f"❌ Failed to grant access to {user.mention}.", ephemeral=True
                )
                return

            confirm = discord.Embed(
                title="✅ Access Granted",
                description=f"**{user.display_name}** can now view: {page_names}",
                color=discord.Color.green(),
            )
            confirm.set_thumbnail(url=user.display_avatar.url)
            await interaction.response.send_message(embed=confirm, ephemeral=True)

            now_has = await get_allowed_pages(user.id)
            all_labels = ", ".join(
                f"**{PAGE_LABELS.get(p, p)}**" for p in sorted(now_has)
            ) or "none"
            public = discord.Embed(
                title="🔥 You Shall Pass",
                description=(
                    f"{user.mention}, your dashboard access has been updated.\n\n"
                    f"**Newly granted:** {page_names}\n"
                    f"**All pages you can now access:** {all_labels}\n\n"
                    f"Sign in with Discord at [reaper.qzz.io](https://reaper.qzz.io) to access them."
                ),
                color=discord.Color.gold(),
            )
            public.set_footer(text=f"Access granted by {interaction.user.display_name}")
            await interaction.followup.send(embed=public)

        else:  # revoke
            success = await revoke_access(user.id, target_pages)
            if not success:
                await interaction.response.send_message(
                    f"❌ Failed to revoke access for {user.mention}.", ephemeral=True
                )
                return

            remaining = await get_allowed_pages(user.id)
            remaining_str = (
                ", ".join(f"**{PAGE_LABELS.get(p, p)}**" for p in sorted(remaining))
                if remaining else "**none**"
            )
            confirm = discord.Embed(
                title="🚫 Access Revoked",
                description=(
                    f"**{user.display_name}** can no longer view: {page_names}\n"
                    f"Remaining access: {remaining_str}"
                ),
                color=discord.Color.red(),
            )
            confirm.set_thumbnail(url=user.display_avatar.url)
            await interaction.response.send_message(embed=confirm, ephemeral=True)

    @app_commands.command(
        name="who_passes",
        description="List all users who have access to restricted dashboard pages.",
    )
    async def who_passes(self, interaction: discord.Interaction):
        """Lists every user currently granted access. Aries only."""
        if interaction.user.id != ARIES_USER_ID:
            await interaction.response.send_message(
                "You do not have permission to use this command.", ephemeral=True
            )
            return

        from Systems.Functions.page_access import list_access
        from collections import defaultdict

        rows = await list_access()
        if not rows:
            await interaction.response.send_message(
                "No users have been granted access yet.", ephemeral=True
            )
            return

        # Group rows by user
        by_user: dict[str, dict] = defaultdict(
            lambda: {"pages": [], "granted_by": "", "granted_at": ""}
        )
        for r in rows:
            by_user[r["user_id"]]["pages"].append(r["page"])
            by_user[r["user_id"]]["granted_by"] = r["granted_by"]
            by_user[r["user_id"]]["granted_at"] = r["granted_at"]

        lines = []
        for uid, info in by_user.items():
            page_list = ", ".join(
                f"`{PAGE_LABELS.get(p, p)}`" for p in sorted(info["pages"])
            )
            lines.append(
                f"• <@{uid}> — {page_list}\n"
                f"  granted by <@{info['granted_by']}> on {info['granted_at'][:10]}"
            )

        embed = discord.Embed(
            title="🔐 Who Shall Pass",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )
        embed.set_footer(text=f"{len(by_user)} user(s) with access")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    """Add the Admin cog to the bot."""
    await bot.add_cog(Admin(bot))
