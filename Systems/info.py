import discord  
from discord.ext import commands  
from discord import app_commands  
import json  
from pathlib import Path  
from datetime import datetime  
import asyncio  
from typing import List, Optional
import os
from Systems.Functions import emoji as emoji_mod  
from Systems.Functions.utils import get_web_public_url  
from Systems.Functions.user_data_manager import user_data_manager

class UsagePaginatorView(discord.ui.View):
    def __init__(self, bot: commands.Bot, admin_user_id: int):
        super().__init__(timeout=300)  # 5 minute timeout
        self.bot = bot
        self.admin_user_id = admin_user_id
        self.current_page = 0
        self.current_view = "servers"  # servers, users, or installed
        self.servers = []
        self.users = []
        self.installed_users = []
        self.message = None
        
        self._setup_buttons()
        
    async def _init_data(self):
        await self._load_data()

    def _setup_buttons(self):
        """Setup the control buttons for the view."""
        # Navigation buttons
        self.first_page = discord.ui.Button(label="<<", style=discord.ButtonStyle.grey, row=1)
        self.prev_page = discord.ui.Button(label="<", style=discord.ButtonStyle.grey, row=1)
        self.next_page = discord.ui.Button(label=">", style=discord.ButtonStyle.grey, row=1)
        self.last_page = discord.ui.Button(label=">>", style=discord.ButtonStyle.grey, row=1)
        
        # View switcher
        self.view_select = discord.ui.Select(
            placeholder="Switch View",
            options=[
                discord.SelectOption(label="Servers", value="servers", emoji="🏠"),
                discord.SelectOption(label="Users with Data", value="users", emoji="👤"),
                discord.SelectOption(label="Installed Users", value="installed", emoji="📱")
            ],
            row=0
        )
        
        # Action buttons
        self.remove_button = discord.ui.Button(label="Remove Selected", style=discord.ButtonStyle.red, row=2)
        self.refresh_button = discord.ui.Button(label="Refresh", style=discord.ButtonStyle.green, row=2)
        self.close_button = discord.ui.Button(label="Close", style=discord.ButtonStyle.blurple, row=2)
        
        # Add callbacks
        self.first_page.callback = self.first_page_callback
        self.prev_page.callback = self.prev_page_callback
        self.next_page.callback = self.next_page_callback
        self.last_page.callback = self.last_page_callback
        self.view_select.callback = self.view_select_callback
        self.remove_button.callback = self.remove_callback
        self.refresh_button.callback = self.refresh_callback
        self.close_button.callback = self.close_callback
        
        # Add items to view
        self.add_item(self.view_select)
        self.add_item(self.first_page)
        self.add_item(self.prev_page)
        self.add_item(self.next_page)
        self.add_item(self.last_page)
        self.add_item(self.remove_button)
        self.add_item(self.refresh_button)
        self.add_item(self.close_button)

    async def _load_data(self):
        """Load servers and users data."""
        try:
            # Load servers
            self.servers = []
            for guild in self.bot.guilds:
                self.servers.append({
                    'id': guild.id,
                    'name': guild.name,
                    'member_count': guild.member_count,
                    'owner': str(guild.owner) if guild.owner else "Unknown",
                    'created_at': guild.created_at,
                    'joined_at': guild.me.joined_at
                })
            
            # Sort servers by member count (descending)
            self.servers.sort(key=lambda x: x['member_count'], reverse=True)
            
            # Load users from data files
            self.users = []
            data_dir = os.path.join(os.getcwd(), "Systems", "Data", "Users")
            if os.path.exists(data_dir):
                for filename in os.listdir(data_dir):
                    if filename.endswith('.json'):
                        user_id = filename[:-5]  # Remove .json
                        try:
                            user_id_int = int(user_id)
                            user = self.bot.get_user(user_id_int)
                            
                            # Get user data file info
                            file_path = os.path.join(data_dir, filename)
                            file_stats = os.stat(file_path)
                            
                            self.users.append({
                                'id': user_id_int,
                                'name': str(user) if user else f"Unknown User ({user_id})",
                                'avatar_url': str(user.avatar.url) if user and user.avatar else None,
                                'created_at': user.created_at if user else None,
                                'data_file': filename,
                                'last_modified': datetime.fromtimestamp(file_stats.st_mtime),
                                'file_size': file_stats.st_size
                            })
                        except (ValueError, FileNotFoundError):
                            continue
            
            # Sort users by last modified (descending)
            self.users.sort(key=lambda x: x['last_modified'], reverse=True)
            
            # Load installed users from tracking
            self.installed_users = []
            try:
                installed_data = await user_data_manager.get_installed_users()
                for user_id_str, user_data in installed_data.items():
                    try:
                        user_id_int = int(user_id_str)
                        user = self.bot.get_user(user_id_int)
                        
                        self.installed_users.append({
                            'id': user_id_int,
                            'name': user_data.get('username', str(user) if user else f"Unknown User ({user_id_str})"),
                            'avatar_url': str(user.avatar.url) if user and user.avatar else None,
                            'created_at': user.created_at if user else None,
                            'first_seen': datetime.fromisoformat(user_data.get('first_seen', datetime.utcnow().isoformat())),
                            'last_seen': datetime.fromisoformat(user_data.get('last_seen', datetime.utcnow().isoformat())),
                            'source': user_data.get('source', 'unknown')
                        })
                    except (ValueError, KeyError):
                        continue
                
                # Sort installed users by last seen (descending)
                self.installed_users.sort(key=lambda x: x['last_seen'], reverse=True)
                
            except Exception as e:
                print(f"Error loading installed users: {e}")
            
        except Exception as e:
            print(f"Error loading usage data: {e}")

    def get_current_data(self):
        """Get the current data based on the active view."""
        if self.current_view == "servers":
            return self.servers
        elif self.current_view == "users":
            return self.users
        else:  # installed
            return self.installed_users

    def get_total_pages(self):
        """Get total number of pages for current view."""
        data = self.get_current_data()
        return max(1, (len(data) + 9) // 10)  # 10 items per page

    def get_embed(self):
        """Generate the embed for current page and view."""
        data = self.get_current_data()
        total_pages = self.get_total_pages()
        
        # Add summary statistics at the top
        summary = f"📊 **Total:** {len(self.servers)} servers, {len(self.users)} users with data, {len(self.installed_users)} installed users"
        
        if self.current_view == "servers":
            embed = discord.Embed(
                title="🤖 Bot Server Usage",
                description=f"{summary}\n\nShowing {len(self.servers)} servers across {total_pages} pages",
                color=discord.Color.blue()
            )
            
            start_idx = self.current_page * 10
            end_idx = min(start_idx + 10, len(data))
            
            for i, server in enumerate(data[start_idx:end_idx], start=start_idx + 1):
                embed.add_field(
                    name=f"{i}. {server['name']}",
                    value=(
                        f"**ID:** `{server['id']}`\n"
                        f"**Members:** {server['member_count']:,}\n"
                        f"**Owner:** {server['owner']}\n"
                        f"**Created:** {server['created_at'].strftime('%Y-%m-%d')}\n"
                        f"**Joined:** {server['joined_at'].strftime('%Y-%m-%d')}"
                    ),
                    inline=False
                )
        
        elif self.current_view == "users":
            embed = discord.Embed(
                title="👥 Bot User Data",
                description=f"{summary}\n\nShowing {len(self.users)} users with data files across {total_pages} pages",
                color=discord.Color.green()
            )
            
            start_idx = self.current_page * 10
            end_idx = min(start_idx + 10, len(data))
            
            for i, user in enumerate(data[start_idx:end_idx], start=start_idx + 1):
                created_str = user['created_at'].strftime('%Y-%m-%d') if user['created_at'] else "Unknown"
                embed.add_field(
                    name=f"{i}. {user['name']}",
                    value=(
                        f"**ID:** `{user['id']}`\n"
                        f"**Created:** {created_str}\n"
                        f"**Last Modified:** {user['last_modified'].strftime('%Y-%m-%d %H:%M')}\n"
                        f"**File Size:** {user['file_size']:,} bytes"
                    ),
                    inline=False
                )
        
        else:  # installed users view
            embed = discord.Embed(
                title="📱 Bot Installed Users",
                description=f"{summary}\n\nShowing {len(self.installed_users)} users who have installed the bot across {total_pages} pages",
                color=discord.Color.purple()
            )
            
            start_idx = self.current_page * 10
            end_idx = min(start_idx + 10, len(data))
            
            for i, user in enumerate(data[start_idx:end_idx], start=start_idx + 1):
                created_str = user['created_at'].strftime('%Y-%m-%d') if user['created_at'] else "Unknown"
                first_seen_str = user['first_seen'].strftime('%Y-%m-%d %H:%M') if user['first_seen'] else "Unknown"
                last_seen_str = user['last_seen'].strftime('%Y-%m-%d %H:%M') if user['last_seen'] else "Unknown"
                
                embed.add_field(
                    name=f"{i}. {user['name']}",
                    value=(
                        f"**ID:** `{user['id']}`\n"
                        f"**Created:** {created_str}\n"
                        f"**First Seen:** {first_seen_str}\n"
                        f"**Last Seen:** {last_seen_str}\n"
                        f"**Source:** {user['source']}"
                    ),
                    inline=False
                )
        
        embed.set_footer(text=f"Page {self.current_page + 1} of {total_pages}")
        embed.timestamp = datetime.now()
        
        return embed

    async def update_message(self):
        """Update the message with current embed and button states."""
        if not self.message:
            return
        
        embed = self.get_embed()
        
        # Update button states
        total_pages = self.get_total_pages()
        self.first_page.disabled = self.current_page == 0
        self.prev_page.disabled = self.current_page == 0
        self.next_page.disabled = self.current_page >= total_pages - 1
        self.last_page.disabled = self.current_page >= total_pages - 1
        
        # Remove button is only enabled when we have items
        self.remove_button.disabled = len(self.get_current_data()) == 0
        
        await self.message.edit(embed=embed, view=self)

    # Callback methods
    async def first_page_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.admin_user_id:
            await interaction.response.send_message("You don't have permission to use this.", ephemeral=True)
            return
        
        self.current_page = 0
        await self.update_message()
        await interaction.response.defer()

    async def prev_page_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.admin_user_id:
            await interaction.response.send_message("You don't have permission to use this.", ephemeral=True)
            return
        
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_message()
        await interaction.response.defer()

    async def next_page_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.admin_user_id:
            await interaction.response.send_message("You don't have permission to use this.", ephemeral=True)
            return
        
        if self.current_page < self.get_total_pages() - 1:
            self.current_page += 1
            await self.update_message()
        await interaction.response.defer()

    async def last_page_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.admin_user_id:
            await interaction.response.send_message("You don't have permission to use this.", ephemeral=True)
            return
        
        self.current_page = self.get_total_pages() - 1
        await self.update_message()
        await interaction.response.defer()

    async def view_select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.admin_user_id:
            await interaction.response.send_message("You don't have permission to use this.", ephemeral=True)
            return
        
        self.current_view = self.view_select.values[0]
        self.current_page = 0
        await self.update_message()
        await interaction.response.defer()

    async def remove_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.admin_user_id:
            await interaction.response.send_message("You don't have permission to use this.", ephemeral=True)
            return
        
        # Create removal confirmation view
        data = self.get_current_data()
        if not data:
            await interaction.response.send_message("No items to remove.", ephemeral=True)
            return
        
        start_idx = self.current_page * 10
        current_items = data[start_idx:start_idx + 10]
        
        if not current_items:
            await interaction.response.send_message("No items on this page.", ephemeral=True)
            return
        
        # Create selection menu for items to remove
        options = []
        for i, item in enumerate(current_items):
            if self.current_view == "servers":
                label = f"{item['name']} ({item['member_count']} members)"
                value = f"server_{item['id']}"
            elif self.current_view == "users":
                label = f"{item['name']} (ID: {item['id']})"
                value = f"user_{item['id']}"
            else:  # installed users
                label = f"{item['name']} (ID: {item['id']})"
                value = f"installed_{item['id']}"
            
            options.append(discord.SelectOption(label=label[:100], value=value))  # Discord limit is 100
        
        select_menu = discord.ui.Select(
            placeholder=f"Select {self.current_view} to remove",
            options=options,
            max_values=len(options)
        )
        
        confirm_button = discord.ui.Button(label="Confirm Removal", style=discord.ButtonStyle.red)
        cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.grey)
        
        removal_view = discord.ui.View()
        removal_view.add_item(select_menu)
        removal_view.add_item(confirm_button)
        removal_view.add_item(cancel_button)
        
        async def confirm_removal(interaction: discord.Interaction):
            if interaction.user.id != self.admin_user_id:
                await interaction.response.send_message("You don't have permission to use this.", ephemeral=True)
                return
            
            if not select_menu.values:
                await interaction.response.send_message("Please select items to remove.", ephemeral=True)
                return
            
            removed_count = 0
            errors = []
            
            for value in select_menu.values:
                try:
                    item_type, item_id = value.split('_', 1)
                    item_id = int(item_id)
                    
                    if item_type == "server":
                        # Leave server
                        guild = self.bot.get_guild(item_id)
                        if guild:
                            await guild.leave()
                            removed_count += 1
                        else:
                            errors.append(f"Server {item_id} not found")
                    
                    elif item_type == "user":
                        # Delete user data file
                        data_file = os.path.join(os.getcwd(), "Systems", "Data", "Users", f"{item_id}.json")
                        if os.path.exists(data_file):
                            os.remove(data_file)
                            removed_count += 1
                        else:
                            errors.append(f"User data file for {item_id} not found")
                    
                    elif item_type == "installed":
                        # Remove from installed users tracking
                        try:
                            installed_data = await user_data_manager.get_installed_users()
                            if str(item_id) in installed_data:
                                # Load current data and remove the user
                                from Systems.Functions.optimal_file_manager import OptimalFileManager
                                file_manager = OptimalFileManager()
                                full_data = await file_manager.load_async(
                                    user_data_manager.installed_users_path,
                                    {"installed_users": {}, "last_updated": datetime.utcnow().isoformat()}
                                )
                                if str(item_id) in full_data["installed_users"]:
                                    del full_data["installed_users"][str(item_id)]
                                    await file_manager.save_async(
                                        user_data_manager.installed_users_path,
                                        full_data
                                    )
                                    removed_count += 1
                            else:
                                errors.append(f"Installed user {item_id} not found in tracking")
                        except Exception as e:
                            errors.append(f"Error removing installed user {item_id}: {str(e)}")
                
                except (ValueError, OSError) as e:
                    errors.append(f"Error removing {value}: {str(e)}")
            
            # Refresh data
            self._load_data()
            
            # Send result message
            result_msg = f"Successfully removed {removed_count} items."
            if errors:
                result_msg += f"\nErrors: {', '.join(errors)}"
            
            await interaction.response.send_message(result_msg, ephemeral=True)
            
            # Update main view
            await self.update_message()
        
        async def cancel_removal(interaction: discord.Interaction):
            if interaction.user.id != self.admin_user_id:
                await interaction.response.send_message("You don't have permission to use this.", ephemeral=True)
                return
            
            await interaction.response.send_message("Removal cancelled.", ephemeral=True)
        
        confirm_button.callback = confirm_removal
        cancel_button.callback = cancel_removal
        
        await interaction.response.send_message(
            "**⚠️ WARNING: This action cannot be undone!**\n\n"
            f"Select the {self.current_view} you want to remove:",
            view=removal_view,
            ephemeral=True
        )

    async def refresh_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.admin_user_id:
            await interaction.response.send_message("You don't have permission to use this.", ephemeral=True)
            return
        
        await interaction.response.send_message("Refreshing data...", ephemeral=True)
        self._load_data()
        await self.update_message()

    async def close_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.admin_user_id:
            await interaction.response.send_message("You don't have permission to use this.", ephemeral=True)
            return
        
        await interaction.response.send_message("Closing usage viewer...", ephemeral=True)
        await self.message.delete()
        self.stop()

    async def on_timeout(self):
        """Called when the view times out."""
        if self.message:
            try:
                await self.message.edit(view=None)
            except:
                pass

class InfoSystem(commands.Cog):  
    def __init__(self, bot):  
        self.bot = bot 

    @commands.hybrid_command(name="leadership", description="Send the Leadership embed to the current channel")
    async def leadership(self, ctx):
        # Build Leadership String
        leadership_text = (
            f"1ic {emoji_mod.mention('1ic')} - <@941869945967480842>\n"
            f"2ic {emoji_mod.mention('2ic')} - <@1357987963878903898> & <@1317311041209896960>\n"
            f"IA (Internal Affairs) {emoji_mod.mention('IA')} - <@1246226717841031331>\n"
            f"MA (Military Affairs) {emoji_mod.mention('MA')} -\n"
            f"FA (Foreign Affairs) {emoji_mod.mention('FA')} -\n"
            f"EA (Economic Affairs) {emoji_mod.mention('EA')} - <@250297961362227201>\n"
            f"JA (Judicial Affairs) {emoji_mod.mention('JA')} -\n"
            f"TA (Technical Affairs) {emoji_mod.mention('TA')} -"
        )

        embed = discord.Embed(
            title="Alliance Leadership",
            description=f"{leadership_text}",
            color=discord.Color.gold()
        )

        # Send embed to the current channel
        await ctx.send(embed=embed)
        await ctx.send("✅ Information embed sent.", ephemeral=True)

    @commands.hybrid_command(name="webpage", description="Get the link to the bot's web interface")
    async def webpage(self, ctx):
        """Sends the web interface URL as a masked link."""
        public_url = get_web_public_url()

        if public_url:
            await ctx.send(
                f"Click [HERE]({public_url}) for 😎 **Cool** 💀 **Reaper** 🤩 **Fun**",
                ephemeral=False
            )
        else:
            await ctx.send(
                "❌ Web interface is not currently accessible. Try: http://localhost:8080",
                ephemeral=False
            )

async def setup(bot):  
    await bot.add_cog(InfoSystem(bot))