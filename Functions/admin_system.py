import discord
from discord.ext import commands
from discord import app_commands
import os
import psutil
import asyncio
from datetime import datetime, timezone
import sys
import logging
from typing import Optional, Dict, List
import time
from config import (
    ARIES_USER_ID,
)

from Systems.Functions.user_data_manager import user_data_manager

class BotLogger:
    """Logging system for bot activities"""
    def __init__(self, log_file=None):
        pass
    
    def add_log(self, user_id, username, command, details=""):
        """Add a log entry using UserDataManager"""
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "username": username,
            "command": command,
            "details": details
        }
        asyncio.create_task(user_data_manager.add_bot_log(log_entry))
    
    async def get_logs_async(self, user_id=None, limit=50):
        """Get logs with optional user filter using UserDataManager"""
        logs = await user_data_manager.get_bot_logs(user_id, limit)
        total_count = await user_data_manager.get_bot_log_count(user_id)
        return logs, total_count
    
    async def clear_logs_async(self, count=None):
        """Clear logs with optional count limit using UserDataManager"""
        return await user_data_manager.clear_bot_logs(count)

class ConfirmClearView(discord.ui.View):
    def __init__(self, cog, user_id):
        super().__init__(timeout=30)
        self.cog = cog
        self.user_id = user_id
    
    @discord.ui.button(label="Clear All Logs", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This confirmation is not for you.", ephemeral=True)
            return
        
        try:
            from Systems.Functions.user_data_manager import user_data_manager
            await user_data_manager.clear_bot_logs(None)
            embed = discord.Embed(
                title="✅ Logs Cleared",
                description=f"Successfully cleared logs.",
                color=0x00ff00,
                timestamp=discord.utils.utcnow()
            )
            await interaction.response.edit_message(embed=embed, view=None)
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Failed to clear logs: {str(e)}",
                color=0xff0000
            )
            await interaction.response.edit_message(embed=embed, view=None)
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This confirmation is not for you.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="❌ Cancelled",
            description="Log clearing cancelled.",
            color=0x808080,
            timestamp=discord.utils.utcnow()
        )
        await interaction.response.edit_message(embed=embed, view=None)
    
    async def on_timeout(self):
        """Handle timeout by disabling the view"""
        try:
            for item in self.children:
                item.disabled = True
        except Exception:
            pass

class DataClearView(discord.ui.View):
    """Data clearing interface for admin - now supports user file deletion"""
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog
        self.selected_users = []
        self.clear_mode = "user_files" 
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.users_dir = os.path.join(base_dir, "Systems", "Users")

    @discord.ui.select(
        placeholder="Select users to delete their data files...",
        min_values=1,
        max_values=5,
        options=[] 
    )
    async def select_users(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_users = [int(user_id) for user_id in select.values]
        
        if self.selected_users:
            user_mentions = []
            for user_id in self.selected_users:
                try:
                    user = await interaction.guild.fetch_member(user_id)
                    user_mentions.append(f"• {user.mention} ({user.display_name})")
                except:
                    user_mentions.append(f"• <@{user_id}> (User not found)")
            
            user_list = '\n'.join(user_mentions)
            description = f"**Selected users to delete data files:**\n{user_list}\n\n⚠️ **Warning:** This will permanently delete ALL user data files!"
        else:
            description = "No users selected. Choose users from the dropdown above.\n\n⚠️ **Warning:** This will permanently delete ALL user data files!"
        
        embed = discord.Embed(
            title="🗑️ Admin User Data Clear",
            description=description,
            color=0xff0000
        )
        
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🗑️ Delete User Data Files", style=discord.ButtonStyle.danger)
    async def delete_user_data(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_users:
            await interaction.response.send_message("❌ No users selected to delete!", ephemeral=True)
            return
        
        try:
            deleted_files = []
            failed_deletions = []
            
            for user_id in self.selected_users:
                try:
                    file_path = os.path.join(self.users_dir, f"{user_id}.json")
                    
                    if await asyncio.to_thread(os.path.exists, file_path):
                        await asyncio.to_thread(os.remove, file_path)

                        try:
                            user = await interaction.guild.fetch_member(user_id)
                            user_info = f"{user.mention} ({user.display_name})"
                        except:
                            user_info = f"<@{user_id}> (User not found)"
                        
                        deleted_files.append(user_info)
                        self.cog.logger.add_log(
                            interaction.user.id, 
                            str(interaction.user), 
                            "admin_clear", 
                            f"Deleted user data file for {user_id}"
                        )
                    else:
                        failed_deletions.append(f"<@{user_id}> (No data file)")
                
                except Exception as e:
                    failed_deletions.append(f"<@{user_id}> (Error: {str(e)})")

            embed = discord.Embed(
                title="✅ User Data Deletion Complete",
                color=0x00ff00 if deleted_files else 0xff0000,
                timestamp=discord.utils.utcnow()
            )
            
            if deleted_files:
                embed.add_field(
                    name="✅ Successfully Deleted",
                    value="\n".join(deleted_files),
                    inline=False
                )
            
            if failed_deletions:
                embed.add_field(
                    name="❌ Failed/Skipped",
                    value="\n".join(failed_deletions),
                    inline=False
                )
            
            await interaction.response.edit_message(embed=embed, view=None)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error Deleting User Data",
                description=f"An error occurred: {str(e)}",
                color=0xff0000
            )
            await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="❌ Operation Cancelled",
            description="User data deletion has been cancelled.",
            color=0x808080
        )
        await interaction.response.edit_message(embed=embed, view=None)

class LeaveServerView(discord.ui.View):
    def __init__(self, cog, author_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.author_id = author_id
        self.selected_guild_id: Optional[int] = None

        options: List[discord.SelectOption] = []
        for g in sorted(self.cog.bot.guilds, key=lambda x: (getattr(x, 'member_count', 0) or 0), reverse=True):
            label = f"{g.name} ({getattr(g, 'member_count', 0) or 0})"
            options.append(discord.SelectOption(label=label, value=str(g.id)))

        self.server_select = discord.ui.Select(placeholder="Select a server to leave…", min_values=1, max_values=1, options=options)
        self.server_select.callback = self._on_select
        self.add_item(self.server_select)

        leave_btn = discord.ui.Button(label="Leave Server", style=discord.ButtonStyle.danger, emoji="🚪")
        leave_btn.callback = self._on_leave
        self.add_item(leave_btn)

        close_btn = discord.ui.Button(label="Close", style=discord.ButtonStyle.secondary, emoji="❌")
        close_btn.callback = self._on_close
        self.add_item(close_btn)

    async def _on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Not authorized for this action.", ephemeral=True)
            return
        try:
            value = self.server_select.values[0]
            self.selected_guild_id = int(value)
            guild = self.cog.bot.get_guild(self.selected_guild_id)
            if guild:
                await interaction.response.send_message(f"Selected: {guild.name}", ephemeral=True)
            else:
                await interaction.response.send_message("Selected server not found.", ephemeral=True)
        except Exception:
            await interaction.response.send_message("Failed to select server.", ephemeral=True)

    async def _on_leave(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Not authorized for this action.", ephemeral=True)
            return
        if not self.selected_guild_id:
            await interaction.response.send_message("❌ Select a server first.", ephemeral=True)
            return
        guild = self.cog.bot.get_guild(self.selected_guild_id)
        if not guild:
            await interaction.response.send_message("❌ Server not found.", ephemeral=True)
            return
        try:
            name = guild.name
            count = getattr(guild, 'member_count', 0) or 0
            await guild.leave()
            embed = discord.Embed(
                title="✅ Left Server",
                description=f"Left `{name}` ({count} users).",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error leaving server: {str(e)}", ephemeral=True)

    async def _on_close(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Not authorized for this action.", ephemeral=True)
            return
        for item in self.children:
            item.disabled = True
        embed = discord.Embed(
            title="❌ Closed",
            description="Operation closed.",
            color=discord.Color.dark_gray(),
            timestamp=discord.utils.utcnow()
        )
        await interaction.response.edit_message(embed=embed, view=self)

class AdminSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()
        self.logger = BotLogger()
        self.command_stats = {}
        self.active_users = set()
        self.error_count = 0
        self.command_usage_history = []

    @commands.hybrid_command(name='horoscopes', description="[ADMIN ONLY] Start/Stop daily horoscope broadcast")
    @app_commands.describe(action="Start or Stop the daily broadcast")
    @app_commands.choices(action=[
        app_commands.Choice(name="Start", value="Start"),
        app_commands.Choice(name="Stop", value="Stop")
    ])
    async def horoscopes(self, ctx: commands.Context, action: str):
        """Control the daily horoscope broadcast"""
        if ctx.author.id != ARIES_USER_ID:
            await ctx.send("❌ This command is restricted to the bot administrator.", ephemeral=True)
            return

        cog = self.bot.get_cog("AstrologyCog")
        if not cog:
            await ctx.send("❌ Astrology system not found.", ephemeral=True)
            return

        if action == "Start":
            cog.start_broadcast()
            await ctx.send("✅ Daily horoscope broadcast scheduled for 12:00 PM UTC.")
        else:
            cog.stop_broadcast()
            await ctx.send("🛑 Daily horoscope broadcast stopped.")

    @commands.hybrid_command(name='admin_clear', description="[ADMIN ONLY] Clear user data files")
    async def admin_clear(self, ctx):
        if ctx.author.id != ARIES_USER_ID:
            await ctx.send("❌ This command is restricted to the bot administrator.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🗑️ Admin User Data Clear",
            description="Select users to delete their data files from the dropdown below.\n\n⚠️ **Warning:** This will permanently delete ALL user data files!",
            color=0x0099ff
        )
        
        view = DataClearView(self)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name='leave', description='Leave a server the bot is in')
    async def leave(self, ctx: commands.Context):
        if ctx.author.id != ARIES_USER_ID:
            await ctx.send("❌ This command is restricted to the bot administrator.", ephemeral=True)
            return

        guilds = list(self.bot.guilds)
        if not guilds:
            await ctx.send("Bot is not in any servers.")
            return

        lines = []
        for g in sorted(guilds, key=lambda x: (getattr(g, 'member_count', 0) or 0), reverse=True):
            count = getattr(g, 'member_count', 0) or 0
            lines.append(f"• {g.name} — {count} users")
        description = "\n".join(lines[:25])

        embed = discord.Embed(title="🏠 Servers", description=description, color=0x0099ff, timestamp=discord.utils.utcnow())

        view = LeaveServerView(self, ctx.author.id)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name='analytics', description="[ADMIN ONLY] Display comprehensive command usage analytics")
    async def analytics(self, ctx):
        """Display detailed command usage analytics and statistics"""
        if ctx.author.id != ARIES_USER_ID:
            await ctx.send("❌ This command is restricted to the bot administrator.", ephemeral=True)
            return
        
        self.logger.add_log(ctx.author.id, str(ctx.author), "analytics", "Command analytics accessed")
        
        embed = discord.Embed(title="📊 Bot Command Analytics", description="Analytics simplified", color=0x00ff99, timestamp=discord.utils.utcnow())
        uptime_hours = (time.time() - self.start_time) / 3600
        embed.add_field(name="Uptime (hours)", value=f"{uptime_hours:.1f}", inline=True)
        embed.add_field(name="Guilds", value=str(len(self.bot.guilds)), inline=True)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='logs', description="[ADMIN ONLY] View bot logs")
    async def logs(self, ctx, user: discord.Member = None):
        """View bot activity logs"""
        if ctx.author.id != ARIES_USER_ID:
            await ctx.send("❌ This command is restricted to the bot administrator.", ephemeral=True)
            return
        
        user_id = user.id if user else None
        logs = await user_data_manager.get_bot_logs(user_id, 50)
        total_count = await user_data_manager.get_bot_log_count(user_id)
        
        if not logs:
            if user:
                await ctx.send(f"📝 No logs found for {user.mention}.")
            else:
                await ctx.send("📝 No logs found.")
            return
        
        if user:
            title = f"📝 Recent Logs for {user.display_name}"
            description = f"Showing last {len(logs)} of {total_count} total logs for this user"
        else:
            title = "📝 Recent Bot Logs"
            description = f"Showing last {len(logs)} of {total_count} total logs"
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=0x0099ff,
            timestamp=discord.utils.utcnow()
        )
        
        log_text = ""
        for log in logs[-10:]: 
            timestamp = datetime.fromisoformat(log['timestamp']).strftime('%m/%d %H:%M')
            log_text += f"`{timestamp}` **{log['username']}** used `{log['command']}`\n"
            if log.get('details'):
                log_text += f"  └ {log['details']}\n"
        
        if log_text:
            embed.add_field(name="Recent Activity", value=log_text, inline=False)
        
        if len(logs) > 10:
            embed.add_field(
                name="Note", 
                value=f"Only showing last 10 entries in embed. Total retrieved: {len(logs)}", 
                inline=False
            )
        
        embed.set_footer(text=f"Total logs in system: {total_count}")
        
        await ctx.send(embed=embed)
        
    @commands.hybrid_command(name='logs_clear', description="[ADMIN ONLY] Clear bot logs")
    async def logs_clear(self, ctx, count: int = None):
        """Clear bot activity logs"""
        if ctx.author.id != ARIES_USER_ID:
            await ctx.send("❌ This command is restricted to the bot administrator.", ephemeral=True)
            return
        
        if count is not None and count <= 0:
            await ctx.send("❌ Count must be a positive number or omitted to clear all logs.")
            return
        
        if count is None:
            view = ConfirmClearView(self, ctx.author.id)
            embed = discord.Embed(
                title="⚠️ Confirm Log Clear",
                description="Are you sure you want to clear **ALL** bot activity logs? This action cannot be undone.",
                color=0xff8800,
                timestamp=discord.utils.utcnow()
            )
            await ctx.send(embed=embed, view=view)
            return
        
        await user_data_manager.clear_bot_logs(count)
        await ctx.send(f"🗑️ Logs cleared.")

    @commands.hybrid_command(name='uptime', description="[ADMIN ONLY] Check bot uptime and performance")
    async def uptime(self, ctx):
        """Check bot uptime and system performance"""
        if ctx.author.id != ARIES_USER_ID:
            await ctx.send("❌ This command is restricted to the bot administrator.", ephemeral=True)
            return
        
        uptime_seconds = (discord.utils.utcnow() - self.bot.user.created_at).total_seconds()
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        
        def get_stats():
            return psutil.virtual_memory(), psutil.cpu_percent(interval=1)
            
        memory, cpu_percent = await asyncio.to_thread(get_stats)
        
        embed = discord.Embed(
            title="⏱️ Bot Uptime & Performance",
            color=0x00ff00,
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(
            name="🕐 Uptime",
            value=f"{days}d {hours}h {minutes}m",
            inline=True
        )
        
        embed.add_field(
            name="💾 Memory Usage",
            value=f"{memory.percent:.1f}%",
            inline=True
        )
        
        embed.add_field(
            name="⚡ CPU Usage",
            value=f"{cpu_percent:.1f}%",
            inline=True
        )       
        embed.set_footer(text="Bot performance metrics")       
        await ctx.send(embed=embed) 
        self.logger.add_log(ctx.author.id, str(ctx.author), "uptime", "Uptime check performed")

    @commands.hybrid_command(name='clear_debug_log', description="[ADMIN ONLY] Clear the bot debug log file")
    async def clear_debug_log(self, ctx):
        """Clear the bot_debug.log file while the bot is running"""
        if ctx.author.id != ARIES_USER_ID:
            await ctx.send("❌ This command is restricted to the bot administrator.", ephemeral=True)
            return
        
        try:
            log_path = "bot_debug.log"
            if os.path.exists(log_path):
                def truncate_log():
                    with open(log_path, 'w') as f:
                        f.write("")
                
                await asyncio.to_thread(truncate_log)
                
                embed = discord.Embed(
                    title="✅ Debug Log Cleared",
                    description="Successfully cleared bot_debug.log file",
                    color=0x00ff00,
                    timestamp=discord.utils.utcnow()
                )
                embed.add_field(
                    name="📁 File",
                    value=f"`{log_path}`",
                    inline=True
                )
                embed.add_field(
                    name="👤 Cleared by",
                    value=ctx.author.mention,
                    inline=True
                )
                
                await ctx.send(embed=embed)
            else:
                await ctx.send("❌ Debug log file not found.")
                
        except Exception as e:
            await ctx.send(f"❌ Error clearing debug log: {str(e)}")

    @commands.hybrid_command(name='sync_commands', description="[ADMIN ONLY] Force sync all slash commands")
    async def sync_commands(self, ctx):
        """Force sync all slash commands to Discord"""
        if ctx.author.id != ADMIN_USER_ID:
            await ctx.send("❌ This command is restricted to the bot administrator.", ephemeral=True)
            return
        
        try:
            embed = discord.Embed(
                title="🔄 Syncing Commands",
                description="Syncing all slash commands to Discord...",
                color=0x0099ff,
                timestamp=discord.utils.utcnow()
            )
            await ctx.send(embed=embed)
            synced = await self.bot.tree.sync()
            command_list = [f"`/{cmd.name}`" for cmd in synced]
            commands_text = "\n".join(command_list) if command_list else "No commands synced"
            
            success_embed = discord.Embed(
                title="✅ Commands Synced Successfully",
                description=f"Successfully synced **{len(synced)}** slash commands.",
                color=0x00ff00,
                timestamp=discord.utils.utcnow()
            )
            
            if command_list:
                success_embed.add_field(
                    name="📋 Synced Commands",
                    value=commands_text[:1024],
                    inline=False
                )
            
            await ctx.send(embed=success_embed)
            self.logger.add_log(ctx.author.id, str(ctx.author), "sync_commands", f"Synced {len(synced)} commands")
            
        except Exception as e:
            error_embed = discord.Embed(
                title="❌ Sync Failed",
                description=f"Failed to sync commands: {str(e)}",
                color=0xff0000,
                timestamp=discord.utils.utcnow()
            )
            await ctx.send(embed=error_embed)
            self.logger.add_log(ctx.author.id, str(ctx.author), "sync_commands_error", str(e))

    @commands.hybrid_command(name='debug', hidden=True, description="[ADMIN ONLY] Display detailed debug information")
    async def debug_info(self, ctx: commands.Context):
        """Display detailed debug information"""
        if ctx.author.id != ADMIN_USER_ID:
            await ctx.send("❌ This command is restricted to the bot administrator.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🔍 Reaper Debug Information",
            description="Detailed system and error information",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(
            name="📊 Module Status",
            value=f"✅ Loaded: {len(self.bot.loaded_modules)}\n"
                  f"❌ Failed: {len(self.bot.failed_modules)}\n"
                  f"📋 Errors: {len(self.bot.error_log)}",
            inline=True
        )
        
        embed.add_field(
            name="🐍 System Info",
            value=f"Python: {sys.version.split()[0]}\n"
                  f"Discord.py: {discord.__version__}\n"
                  f"Uptime: {datetime.now() - self.bot.startup_time}",
            inline=True
        )
        
        if self.bot.failed_modules:
            failed_list = "\n".join([f"• {mod}: {err[:50]}..." for mod, err in self.bot.failed_modules[:5]])
            embed.add_field(
                name="❌ Failed Modules",
                value=failed_list or "None",
                inline=False
            )
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='test_error', hidden=True, description="[ADMIN ONLY] Test error handling system")
    async def test_error(self, ctx: commands.Context):
        """Test error handling system"""
        if ctx.author.id != ADMIN_USER_ID:
            await ctx.send("❌ This command is restricted to the bot administrator.", ephemeral=True)
            return

        try:
            # Intentionally cause an error
            result = 1 / 0
        except Exception as e:
            self.logger.add_log(ctx.author.id, str(ctx.author), "test_error", "Test error triggered by owner")
            logging.getLogger("AdminSystem").error("Test error triggered by owner")
            await ctx.send(f"✅ Error handling system working! Check logs for details.")

async def setup(bot):
    """Setup function to add the AdminSystem cog"""
    await bot.add_cog(AdminSystem(bot))
    print("Admin system loaded successfully")

def setup_legacy(bot):
    """Legacy setup function for backward compatibility"""
    bot.add_cog(AdminSystem(bot))
    print("Admin system loaded (legacy)")

__all__ = ['setup', 'setup_legacy', 'AdminSystem']
