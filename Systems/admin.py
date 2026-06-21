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

INVITE_URL = (
    "https://discord.com/oauth2/authorize"
    "?client_id=1345073131550801984"
    "&permissions=380373429328"
    "&integration_type=0"
    "&scope=bot+applications.commands"
)


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

    @commands.hybrid_command(name="invite", description="Get the link to invite The Reaper to a server.")
    async def invite(self, ctx: commands.Context):
        """Returns the bot invite link. Only usable by Aries."""
        if ctx.author.id != ARIES_USER_ID:
            await ctx.send("You do not have permission to use this command.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Invite The Reaper",
            description=f"[Click here to add The Reaper to your server]({INVITE_URL})",
            color=discord.Color.dark_red(),
        )
        embed.set_thumbnail(url="attachment://keeper.png")
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="servers", description="Lists all servers the bot is in.")
    @commands.is_owner()
    async def servers(self, ctx: commands.Context):
        """Lists all servers the bot is currently in."""
        if ctx.author.id != ARIES_USER_ID:
            await ctx.send("You do not have permission to use this command.", ephemeral=True)
            return

        guilds = self.bot.guilds
        guild_count = len(guilds)

        if guild_count == 0:
            await ctx.send("The bot is not in any servers.", ephemeral=True)
            return

        # Paginate if there are many servers (Discord embed field limit is 25)
        pages: list[discord.Embed] = []
        chunk_size = 20
        guild_list = list(guilds)

        for i in range(0, guild_count, chunk_size):
            chunk = guild_list[i : i + chunk_size]
            page_num = i // chunk_size + 1
            total_pages = (guild_count + chunk_size - 1) // chunk_size
            embed = discord.Embed(
                title=f"Bot Server List ({guild_count} servers) — Page {page_num}/{total_pages}",
                color=discord.Color.blue(),
            )
            for guild in chunk:
                embed.add_field(
                    name=guild.name,
                    value=f"ID: `{guild.id}`\nMembers: {guild.member_count:,}",
                    inline=False,
                )
            pages.append(embed)

        # Send all pages (ephemeral, so no interactive pagination needed)
        for page in pages:
            await ctx.send(embed=page, ephemeral=True)

    async def _server_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete that supports comma-separated multi-select.

        Discord passes the entire field value as `current`. We split on the last
        comma so already-chosen IDs are preserved and only the newest token is
        used for filtering. Each suggestion's value includes the already-chosen
        prefix so selecting it appends rather than replaces.
        """
        guilds = self.bot.guilds

        # Split into already-committed tokens and the fragment being typed now
        if "," in current:
            prefix_part, fragment = current.rsplit(",", 1)
            prefix = prefix_part.strip() + ", "
        else:
            prefix = ""
            fragment = current

        fragment = fragment.strip().lower()

        # Collect IDs that have already been selected so we can skip them
        already_selected: set[str] = set()
        if prefix:
            for tok in prefix.split(","):
                tok = tok.strip()
                if tok:
                    already_selected.add(tok)

        choices: list[app_commands.Choice[str]] = []
        for guild in guilds:
            gid = str(guild.id)
            if gid in already_selected:
                continue  # Don't offer servers already in the list

            # Filter by the current fragment (name or ID)
            if fragment and fragment not in guild.name.lower() and fragment not in gid:
                continue

            label = f"{guild.name} ({guild.id})"
            # The value includes everything already typed so selecting appends
            value = f"{prefix}{gid}"

            # Discord caps Choice name at 100 chars and value at 100 chars
            if len(value) > 100:
                continue

            choices.append(app_commands.Choice(name=label[:100], value=value))

        return choices[:25]

    @commands.hybrid_command(name="leave_server", description="Force the bot to leave one or more servers. (Aries only)")
    @app_commands.describe(server_ids="Server ID(s) to leave — comma-separated for multiple, e.g. 123, 456, 789")
    @app_commands.autocomplete(server_ids=_server_autocomplete)
    async def leave_server(self, ctx: commands.Context, server_ids: str):
        """Leave one or more servers by ID. Only usable by Aries."""
        if ctx.author.id != ARIES_USER_ID:
            await ctx.send("You do not have permission to use this command.", ephemeral=True)
            return

        # Defer immediately — leaving servers can exceed Discord's 3-second window
        await ctx.defer(ephemeral=True)

        # Parse comma-separated IDs
        raw_ids = [s.strip() for s in server_ids.split(",") if s.strip()]
        if not raw_ids:
            await ctx.followup.send("❌ No server IDs provided.", ephemeral=True)
            return

        results: list[str] = []
        for raw in raw_ids:
            try:
                guild_id = int(raw)
            except ValueError:
                results.append(f"❌ `{raw}` — not a valid server ID")
                continue

            guild = self.bot.get_guild(guild_id)
            if guild is None:
                results.append(f"❌ `{guild_id}` — bot is not in this server")
                continue

            guild_name = guild.name
            try:
                await guild.leave()
                results.append(f"✅ Left **{guild_name}** (`{guild_id}`)")
                self.bot.logger.info(f"Left server '{guild_name}' ({guild_id}) on Aries request.")
            except discord.HTTPException as e:
                results.append(f"❌ Failed to leave **{guild_name}** (`{guild_id}`): {e}")

        embed = discord.Embed(
            title=f"Leave Server — {len(raw_ids)} requested",
            description="\n".join(results),
            color=discord.Color.green() if all(r.startswith("✅") for r in results) else discord.Color.orange(),
        )
        await ctx.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    """Add the Admin cog to the bot."""
    await bot.add_cog(Admin(bot))
