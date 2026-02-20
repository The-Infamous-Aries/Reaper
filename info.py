import discord
from discord.ext import commands
from discord import app_commands
from discord import ui
import json
from pathlib import Path
from datetime import datetime
import asyncio
from Systems.Functions import emoji as emoji_mod
from Systems.Functions.emoji import EMOJI_IDS
from Systems.PnW.pnwhopper import build_nation_mini_embed, build_alliance_mini_embed
from Systems.PnW.Util.query import PNWAPIQuery

async def read_json_async(path):
    if not path.exists():
        return None
    def _read():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return await asyncio.to_thread(_read)

async def write_json_async(path, data):
    def _write():
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    await asyncio.to_thread(_write)

SERVER_ID = 1445703450263420938
INFO_CHANNEL_ID = 1445703670057537700
TICKET_CATEGORY_ID = 1448558021855936592
CATEGORY_MEMBER_APPROVED = 1448558098888265778
CATEGORY_DIPLOMAT_APPROVED = 1448558162054615091

class TicketConfirmView(discord.ui.View):
    def __init__(self, data, ticket_type, channel):
        super().__init__(timeout=None)
        self.data = data
        self.ticket_type = ticket_type
        self.channel = channel
    
    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Data is already saved upon creation
        await interaction.response.send_message("✅ Ticket confirmed.", ephemeral=True)
        
        # Disable buttons
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        
    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, emoji=emoji_mod.get_partial('Warning') or "❌")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"{emoji_mod.mention('Warning') or '❌'} Ticket denied. Deleting channel in 5 seconds...", ephemeral=True)
        # Disable buttons to prevent re-clicking
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        
        # Remove from DB
        path = Path(__file__).parent / "Data" / "tickets.json"
        if path.exists():
            try:
                content = await read_json_async(path)
                if content:
                    tickets = content.get("tickets", [])
                    tickets = [t for t in tickets if t.get("channel_id") != self.channel.id]
                    content["tickets"] = tickets
                    
                    await write_json_async(path, content)
            except Exception:
                pass
        
        await asyncio.sleep(5)
        try:
            await self.channel.delete()
        except Exception:
            pass

class TicketModal(ui.Modal, title="Enter Nation Details"):
    nation_input = ui.TextInput(label="Nation Name or ID", placeholder="e.g. 12345 or MyNation", required=True)

    def __init__(self, ticket_type):
        super().__init__()
        self.ticket_type = ticket_type
        self.api = PNWAPIQuery()

    async def _fetch_nation(self, query_input):
        # Try ID first
        if query_input.isdigit():
            query = f"""
            query {{
                nations(id: {query_input}, first: 1) {{
                    data {{ {self.api._nation_fields()} }}
                }}
            }}
            """
        else:
            safe_name = query_input.replace('"', '\\"')
            query = f"""
            query {{
                nations(nation_name: "{safe_name}", first: 1) {{
                    data {{ {self.api._nation_fields()} }}
                }}
            }}
            """
        
        data = await self.api._request_with_retries(query)
        nations = data.get("data", {}).get("nations", {}).get("data", [])
        if nations:
            return self.api._normalize_nation(nations[0])
        return None

    async def _fetch_alliance(self, alliance_id):
        if not alliance_id:
            return None
        # We need score and count of nations.
        query = f"""
        query {{
            alliances(id: {alliance_id}) {{
                data {{
                    id
                    name
                    score
                    nations {{ paginatorInfo {{ total }} }}
                }}
            }}
        }}
        """
        data = await self.api._request_with_retries(query)
        alliances = data.get("data", {}).get("alliances", {}).get("data", [])
        if alliances:
            return alliances[0]
        return None

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        inp = self.nation_input.value.strip()
        
        try:
            nation = await self._fetch_nation(inp)
            if not nation:
                await interaction.followup.send(f"❌ Could not find nation: {inp}", ephemeral=True)
                return

            # Prepare stats for Nation Embed
            cities = nation.get("cities", [])
            powered_cities = sum(1 for c in cities if c.get("powered"))
            total_infra = sum(float(c.get("infrastructure", 0)) for c in cities)
            num_cities = int(nation.get("num_cities", 0))
            avg_city_infra = total_infra / num_cities if num_cities > 0 else 0
            
            # Helper for project/city status (simplified)
            def get_turns_status(turns):
                if turns is None: return "Unknown"
                return f"{turns} turns ago"
            
            # Create Channel
            guild = interaction.guild
            category = guild.get_channel(TICKET_CATEGORY_ID)
            if not category:
                await interaction.followup.send("❌ Ticket category not found.", ephemeral=True)
                return

            channel_name = f"{nation.get('nation_name')}{nation.get('id')}".lower().replace(" ", "-")
            # Sanitize channel name
            channel_name = "".join(c for c in channel_name if c.isalnum() or c == "-")
            
            channel = await guild.create_text_channel(name=channel_name, category=category)
            
            # Data to save
            save_data = {
                "discord_id": interaction.user.id,
                "discord_name": interaction.user.name,
                "nation_name": nation.get("nation_name"),
                "nation_id": nation.get("id"),
                "type": self.ticket_type,
                "channel_id": channel.id,
                "status": "pending",
                "created_at": datetime.now().isoformat()
            }
            
            if self.ticket_type == "membership":
                embed = await build_nation_mini_embed(
                    nation=nation,
                    vacation_turns=int(nation.get("vacation_mode_turns", 0)),
                    beige_turns=int(nation.get("beige_turns", 0)),
                    discord_info=nation.get("discord", "Unknown"),
                    last_active=nation.get("last_active", "Unknown"),
                    project_status=get_turns_status(nation.get("turns_since_last_project")),
                    city_status=get_turns_status(nation.get("turns_since_last_city")),
                    cities=cities,
                    powered_cities=powered_cities,
                    infra_tier="Unknown", # Logic not provided, default to Unknown
                    total_infra=total_infra,
                    avg_city_infra=avg_city_infra
                )
            
            elif self.ticket_type == "diplomat":
                alliance_id = nation.get("alliance_id")
                if not alliance_id or str(alliance_id) == "0":
                    await channel.delete()
                    await interaction.followup.send("❌ Your nation is not in an alliance.", ephemeral=True)
                    return
                
                alliance = await self._fetch_alliance(alliance_id)
                if not alliance:
                    await channel.delete()
                    await interaction.followup.send("❌ Could not fetch alliance data.", ephemeral=True)
                    return
                
                # Construct data for builder
                nations_count = alliance.get("nations", {}).get("paginatorInfo", {}).get("total", 0)
                full_mill_data = {
                    "active_nations": 0, # Requires full fetch
                    "total_cities": 0,
                    "total_score": alliance.get("score", 0)
                }
                
                embed = await build_alliance_mini_embed(full_mill_data, nations_count)
                
                # Update save data with alliance ID
                save_data["alliance_id"] = alliance_id

            # Save data immediately
            path = Path(__file__).parent / "Data" / "tickets.json"
            try:
                if path.exists():
                    content = await read_json_async(path)
                else:
                    content = {"tickets": []}
                    path.parent.mkdir(parents=True, exist_ok=True)
                
                content.setdefault("tickets", []).append(save_data)
                
                await write_json_async(path, content)
            except Exception as e:
                # If save fails, we should probably delete the channel and warn
                await channel.delete()
                await interaction.followup.send(f"❌ Failed to save ticket data: {e}", ephemeral=True)
                return

            view = TicketConfirmView(save_data, self.ticket_type, channel)
            await channel.send(f"{interaction.user.mention} Ticket created.", embed=embed, view=view)
            
            await interaction.followup.send(f"✅ Ticket created: {channel.mention}", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Error creating ticket: {e}", ephemeral=True)
            # Cleanup if channel was created? 
            # It's hard to know if 'channel' exists here easily without scope, 
            # but usually error happens before creation or during fetch.

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Create Application", style=discord.ButtonStyle.success, custom_id="ticket_membership", emoji=discord.PartialEmoji(name="Member", id=EMOJI_IDS.get("Member")))
    async def membership(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketModal("membership"))
    
    @discord.ui.button(label="Create Embassy", style=discord.ButtonStyle.primary, custom_id="ticket_diplomat", emoji=discord.PartialEmoji(name="Diplomat", id=EMOJI_IDS.get("Diplomat")))
    async def diplomat(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketModal("diplomat"))

class InfoSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="information", description="Send the information embed to the info channel")
    @commands.has_permissions(administrator=True)
    async def information(self, ctx):
        if ctx.guild.id != SERVER_ID:
            await ctx.send("❌ This command is only for the main server.", ephemeral=True)
            return

        target_channel = ctx.guild.get_channel(INFO_CHANNEL_ID)
        if not target_channel:
            await ctx.send(f"❌ Target channel {INFO_CHANNEL_ID} not found.", ephemeral=True)
            return

        # Build Leadership String
        leadership_text = (
            f"**Leadership**\n"
            f"1ic {emoji_mod.mention('1ic')} - "
            f"2ic {emoji_mod.mention('2ic')} - "
            f"The Reapers\n"
            f"IA (Internal Affairs) {emoji_mod.mention('IA')} - "
            f"MA (Military Affairs) {emoji_mod.mention('MA')} - "
            f"FA (Foreign Affairs) {emoji_mod.mention('FA')} - "
            f"EA (Economic Affairs) {emoji_mod.mention('EA')} - "
            f"JA (Judicial Affairs) {emoji_mod.mention('JA')} - "
            f"TA (Technical Affairs) {emoji_mod.mention('TA')}"
        )

        rules_text = (
            "**Server Rules**\n"
            "1. No Harrassment of any kind (Racial, Religious, Sexual or any not mentioned, Zero Tolerance)\n"
            "2. No Explicit Content (Swearing & Cussing will be allowed as we honor free speech but no sexual or harrassment pictures or videos allowed, Zero Tolerance)\n"
            "3. No Spamming of things we dont like (You will be warned 1-2 times depending on what your spamming but after that your gone)"
        )
        
        tickets_text = (
            "**Member Applications & Embassy Tickets**\n"
            f"- Member Applications will be made for alliance leadership review/communication with applicant upon selection of the {emoji_mod.mention('Member')}.\n"
            f"- Embassy Tickets will be made for Alliances upon selection of the {emoji_mod.mention('Diplomat')}.\n"
            f"If your alliance already has a Embassy please message and/or DM {emoji_mod.mention('1ic')}{emoji_mod.mention('2ic')}{emoji_mod.mention('FA')} for proper Alliance Diplomat role."
        )

        embed = discord.Embed(
            title="Alliance Information",
            description=f"{leadership_text}\n\n{rules_text}\n\n{tickets_text}",
            color=discord.Color.gold()
        )

        await target_channel.send(embed=embed, view=TicketView())
        await ctx.send("✅ Information embed sent.", ephemeral=True)

    @commands.hybrid_command(name="approve", description="Approve a ticket and move it to the appropriate category")
    @commands.has_permissions(administrator=True)
    async def approve(self, ctx):
        path = Path(__file__).parent / "Data" / "tickets.json"
        if not path.exists():
            await ctx.send("❌ No tickets data found.", ephemeral=True)
            return
            
        try:
            data = await read_json_async(path)
            if not data:
                await ctx.send("❌ Failed to read ticket data.", ephemeral=True)
                return

            tickets = data.get("tickets", [])
            ticket = next((t for t in tickets if t.get("channel_id") == ctx.channel.id), None)
            
            if not ticket:
                await ctx.send("❌ This channel is not a registered ticket.", ephemeral=True)
                return
            
            ticket_type = ticket.get("type")
            target_category_id = None
            
            if ticket_type == "membership":
                target_category_id = CATEGORY_MEMBER_APPROVED
            elif ticket_type == "diplomat":
                target_category_id = CATEGORY_DIPLOMAT_APPROVED
            
            if not target_category_id:
                await ctx.send(f"❌ Unknown ticket type: {ticket_type}", ephemeral=True)
                return
            
            category = ctx.guild.get_channel(target_category_id)
            if not category:
                await ctx.send(f"❌ Target category {target_category_id} not found.", ephemeral=True)
                return
                
            await ctx.channel.edit(category=category)
            
            # Update ticket status in DB
            ticket["status"] = "approved"
            ticket["approved_at"] = datetime.now().isoformat()
            ticket["approved_by"] = ctx.author.id
            
            await write_json_async(path, data)
                
            await ctx.send(f"✅ Ticket approved and moved to {category.name}.", ephemeral=True)
            
        except Exception as e:
            await ctx.send(f"❌ Error approving ticket: {e}", ephemeral=True)

    @commands.hybrid_command(name="deny", description="Deny a ticket, delete the channel and remove data")
    @commands.has_permissions(administrator=True)
    async def deny(self, ctx):
        path = Path(__file__).parent / "Data" / "tickets.json"
        if not path.exists():
            await ctx.send("❌ No tickets data found. Deleting channel...", ephemeral=True)
            await asyncio.sleep(2)
            await ctx.channel.delete()
            return
            
        try:
            data = await read_json_async(path)
            if not data:
                data = {"tickets": []}

            tickets = data.get("tickets", [])
            initial_count = len(tickets)
            
            # Filter out the current ticket
            tickets = [t for t in tickets if t.get("channel_id") != ctx.channel.id]
            
            if len(tickets) == initial_count:
                # Ticket not in DB
                await ctx.send("⚠️ This channel is not in the ticket database. Deleting anyway...", ephemeral=True)
            else:
                # Save updated list
                data["tickets"] = tickets
                await write_json_async(path, data)
                await ctx.send("✅ Ticket denied and data removed. Deleting channel in 5 seconds...", ephemeral=True)
            
            await asyncio.sleep(5)
            await ctx.channel.delete()
            
        except Exception as e:
            await ctx.send(f"❌ Error denying ticket: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(InfoSystem(bot))
    bot.add_view(TicketView())
