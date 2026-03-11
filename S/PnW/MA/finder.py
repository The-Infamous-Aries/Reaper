import discord
from discord.ext import commands
from typing import List, Dict, Optional, Any, Callable
from datetime import datetime, timezone, timedelta
import math

# --- Embed Creation Functions ---

def _create_bounties_embed(bounties_data: List[Dict[str, Any]], bounty_type: str, price_range: str, current_page: int, total_pages: int) -> discord.Embed:
    """Creates a rich embed to display bounty information."""
    price_map = {
        "1-4.9": "$1M+",
        "5-9.9": "$5M+",
        "10-19.9": "$10M+",
        "20-49.9": "$20M+",
        "50+": "$50M+",
        "any": "Any"
    }

    embed = discord.Embed(
        title=f"🎯 {bounty_type.title()} Bounties Found",
        description=f"Displaying bounties in the **{price_map.get(price_range, 'N/A')}** range.",
        color=discord.Color.dark_red(),
        timestamp=datetime.utcnow()
    )

    if not bounties_data:
        embed.description = "No bounties found for this page."
        return embed

    for bounty in bounties_data:
        nation_name = bounty.get('nation', {}).get('nation_name', 'N/A')
        nation_id = bounty.get('nation', {}).get('id')
        if not nation_id:
            nation_id = bounty.get('nation_id')
        nation_link = f"[{nation_name}](https://politicsandwar.com/nation/id={nation_id})" if nation_id else nation_name
        last_active_str = bounty.get('nation', {}).get('last_active')
        last_active_display = 'Unknown'
        if last_active_str:
            try:
                last_active_dt = datetime.fromisoformat(last_active_str.replace('Z', '+00:00'))
                last_active_display = f'<t:{int(last_active_dt.timestamp())}:R>'
            except (ValueError, TypeError):
                pass

        embed.add_field(
            name=f"💰 ${bounty.get('amount', 0):,}",
            value=f"**Holder:** {nation_link}\n**Score:** {bounty.get('nation', {}).get('score', 0):,}\n**Last Active:** {last_active_display}",
            inline=False
        )

    if total_pages > 1:
        embed.set_footer(text=f"Page {current_page} of {total_pages} • Data from P&W API")
    else:
        embed.set_footer(text="Data from Politics & War API")

    return embed

def _create_treasures_embed(treasures_data: List[Dict[str, Any]], current_page: int, total_pages: int) -> discord.Embed:
    """Creates a rich embed to display treasure information."""
    embed = discord.Embed(
        title="💎 Treasures Found",
        description=f"Found {len(treasures_data)} treasures.",
        color=discord.Color.gold(),
        timestamp=datetime.utcnow()
    )
    
    if not treasures_data:
        embed.description = "No treasures found for this page."
        return embed

    for treasure in treasures_data:
        nation_name = treasure.get('nation', {}).get('nation_name', 'N/A')
        nation_id = treasure.get('nation', {}).get('id')
        if not nation_id:
            nation_id = treasure.get('nation_id')
        nation_link = f"[{nation_name}](https://politicsandwar.com/nation/id={nation_id})" if nation_id else nation_name

        spawn_date_str = treasure.get('spawn_date', 'N/A')
        try:
            spawn_date = datetime.fromisoformat(spawn_date_str)
            spawn_display = f'<t:{int(spawn_date.timestamp())}:R>'
        except (ValueError, TypeError):
            spawn_display = 'N/A'

        field_value = (
            f"**Bonus:** +{treasure.get('bonus', 0)}%\n"
            f"**Spawned:** {spawn_display}\n"
            f"**Holder:** {nation_link}\n"
            f"**Score:** {treasure.get('nation', {}).get('score', 0):,}"
        )

        embed.add_field(
            name=f"{treasure.get('name', 'Unknown Treasure')} ({treasure.get('color', 'N/A')})",
            value=field_value,
            inline=True
        )

    if total_pages > 1:
        embed.set_footer(text=f"Page {current_page} of {total_pages} • Data from P&W API")
    else:
        embed.set_footer(text="Data from Politics & War API")
        
    return embed

def _create_treasure_trades_embed(trades_data: List[Dict[str, Any]], current_page: int, total_pages: int) -> discord.Embed:
    """Creates a rich embed to display treasure trade information."""
    embed = discord.Embed(
        title="📉 Recently Canceled Treasure Trades",
        description="Showing trades that were rejected or canceled by the seller.",
        color=discord.Color.orange(),
        timestamp=datetime.utcnow()
    )

    if not trades_data:
        embed.description = "No canceled treasure trades found for this page."
        return embed

    for trade in trades_data:
        receiver_name = trade.get('receiver', {}).get('nation_name', 'N/A')
        receiver_id = trade.get('receiver', {}).get('id')
        if not receiver_id:
            receiver_id = trade.get('receiver_id')
        
        holder_link = f"[{receiver_name}](https://politicsandwar.com/nation/id={receiver_id})" if receiver_id else receiver_name
        
        canceled_date_str = trade.get('accept_date') or trade.get('offer_date')
        canceled_display = 'Unknown'
        if canceled_date_str:
            try:
                canceled_dt = datetime.fromisoformat(canceled_date_str.replace('Z', '+00:00'))
                canceled_display = f'<t:{int(canceled_dt.timestamp())}:R>'
            except (ValueError, TypeError):
                pass

        field_value = (
            f"**Trade Amount:** ${trade.get('money', 0):,}\n"
            f"**Treasure Holder:** {holder_link}\n"
            f"**Trade Canceled:** {canceled_display}"
        )

        embed.add_field(
            name=f"Treasure: {trade.get('treasure', 'Unknown')}",
            value=field_value,
            inline=False
        )

    if total_pages > 1:
        embed.set_footer(text=f"Page {current_page} of {total_pages} • Data from P&W API")
    else:
        embed.set_footer(text="Data from Politics & War API")
        
    return embed


# --- Pagination View ---
class PaginationView(discord.ui.View):
    def __init__(self, all_items: List[Dict[str, Any]], embed_creator: Callable, per_page: int = 10, **kwargs):
        super().__init__(timeout=180)
        self.all_items = all_items
        self.embed_creator = embed_creator
        self.per_page = per_page
        self.current_page = 1
        self.total_pages = math.ceil(len(self.all_items) / self.per_page)
        self.embed_kwargs = kwargs
        self.update_buttons()

    def update_buttons(self):
        self.prev_button.disabled = self.current_page == 1
        self.next_button.disabled = self.current_page == self.total_pages

    async def get_page_embed(self) -> discord.Embed:
        start_index = (self.current_page - 1) * self.per_page
        end_index = start_index + self.per_page
        page_items = self.all_items[start_index:end_index]
        return self.embed_creator(page_items, current_page=self.current_page, total_pages=self.total_pages, **self.embed_kwargs)

    async def update_interaction(self, interaction: discord.Interaction):
        self.update_buttons()
        embed = await self.get_page_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.grey)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 1:
            self.current_page -= 1
            await self.update_interaction(interaction)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Next", style=discord.ButtonStyle.grey)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages:
            self.current_page += 1
            await self.update_interaction(interaction)
        else:
            await interaction.response.defer()


class Finder(commands.Cog):
    """Cog for finding treasures and bounties in Politics & War."""

    def __init__(self, bot: commands.Bot, query_instance):
        self.bot = bot
        self.query = query_instance

    async def _fetch_all_bounties(self, min_amount: Optional[float] = None) -> List[Dict[str, Any]]:
        """Fetches all bounties from all pages for a given filter."""
        all_bounties = []
        current_page = 1
        while True:
            try:
                paginator = await self.query.get_bounties(min_amount=min_amount, first=50, page=current_page)
                if not paginator or not paginator.get('data'):
                    break
                
                all_bounties.extend(paginator['data'])
                
                if not paginator.get('paginatorInfo', {}).get('hasMorePages'):
                    break
                current_page += 1
            except Exception: # Broad exception to prevent getting stuck in a loop
                break
        return all_bounties

    @commands.hybrid_command(name="treasures", description="Find all available treasures.")
    @discord.app_commands.describe(
        sort="How to sort the treasures.",
        active="Filter by nation inactivity.",
        score="Your nation score to filter by war range"
    )
    @discord.app_commands.choices(
        sort=[
            discord.app_commands.Choice(name="Spawn Date (Newest First)", value="spawn_new"),
            discord.app_commands.Choice(name="Spawn Date (Oldest First)", value="spawn_old"),
            discord.app_commands.Choice(name="Bonus (High to Low)", value="bonus_desc"),
            discord.app_commands.Choice(name="Bonus (Low to High)", value="bonus_asc"),
            discord.app_commands.Choice(name="Activity (Most Recent First)", value="active_new"),
            discord.app_commands.Choice(name="Activity (Least Recent First)", value="active_old"),
        ],
        active=[
            discord.app_commands.Choice(name="Any", value="any"),
            discord.app_commands.Choice(name="7+ Days Inactive", value="7"),
            discord.app_commands.Choice(name="14+ Days Inactive", value="14"),
            discord.app_commands.Choice(name="28+ Days Inactive", value="28"),
        ]
    )
    async def treasures(self, ctx: commands.Context, sort: str = "spawn_new", active: str = "any", score: Optional[float] = None):
        """Find and display all available treasures in the game, with sorting and pagination."""
        await ctx.defer()

        # Use user's score if provided
        user_score = score

        try:
            treasures_data = await self.query.get_treasures()
            if not treasures_data:
                await ctx.send("Could not retrieve treasure data or no treasures are currently available.", ephemeral=True)
                return

            # --- Filtering ---
            filtered_treasures = [t for t in treasures_data if t.get('nation', {}).get('vacation_mode_turns', 0) == 0]

            # Filter by war range if score parameter provided
            if user_score:
                min_war_score = user_score * 0.75  # -25%
                max_war_score = user_score * 2.5   # +150%
                filtered_treasures = [t for t in filtered_treasures if min_war_score <= (t.get('nation', {}).get('score', 0) or 0) <= max_war_score]

            # Filter by activity if specified
            if active != "any":
                try:
                    days_inactive = int(active)
                    now = datetime.now(timezone.utc)
                    inactive_threshold = now - timedelta(days=days_inactive)
                    
                    def is_inactive(treasure):
                        last_active_str = treasure.get('nation', {}).get('last_active')
                        if not last_active_str: return False
                        try:
                            last_active_dt = datetime.fromisoformat(last_active_str.replace('Z', '+00:00'))
                            return last_active_dt < inactive_threshold
                        except (ValueError, TypeError): return False
                    
                    filtered_treasures = [t for t in filtered_treasures if is_inactive(t)]
                except ValueError: pass
            def get_last_active(treasure):
                last_active_str = treasure.get('nation', {}).get('last_active')
                if not last_active_str: return datetime.min.replace(tzinfo=timezone.utc)
                try:
                    return datetime.fromisoformat(last_active_str.replace('Z', '+00:00'))
                except (ValueError, TypeError): return datetime.min.replace(tzinfo=timezone.utc)

            if sort == "bonus_desc":
                treasures_data.sort(key=lambda t: t.get('bonus', 0), reverse=True)
            elif sort == "bonus_asc":
                treasures_data.sort(key=lambda t: t.get('bonus', 0))
            elif sort == "active_new":
                treasures_data.sort(key=get_last_active, reverse=True)
            elif sort == "active_old":
                treasures_data.sort(key=get_last_active)
            else: # spawn_new (default)
                treasures_data.sort(key=lambda t: datetime.fromisoformat(t.get('spawn_date', '')), reverse=True)

            # --- Pagination ---
            if not filtered_treasures:
                if user_score:
                    await ctx.send(f"No treasures found within your war range ({user_score * 0.75:,.0f} - {user_score * 2.5:,.0f} score).", ephemeral=True)
                else:
                    await ctx.send("No treasures found with the specified criteria.", ephemeral=True)
                return

            view = PaginationView(filtered_treasures, _create_treasures_embed, per_page=9)
            initial_embed = await view.get_page_embed()
            await ctx.send(embed=initial_embed, view=view)

        except Exception as e:
            await ctx.send(f"An error occurred: {e}", ephemeral=True)

    @commands.hybrid_command(name="treasure_trades", description="Find recent treasure trades that were canceled or rejected.")
    async def treasure_trades(self, ctx: commands.Context):
        """Find and display recent treasure trades that were canceled or rejected."""
        await ctx.defer()

        try:
            all_trades = await self.query.get_treasure_trades()
            if not all_trades:
                await ctx.send("Could not retrieve treasure trade data or no recent trades are available.", ephemeral=True)
                return

            filtered_trades = [
                t for t in all_trades 
                if t.get('buying') and (t.get('rejected') or t.get('seller_cancelled'))
            ]

            if not filtered_trades:
                await ctx.send("No recently canceled or rejected treasure trades found.", ephemeral=True)
                return

            def get_cancel_date(trade):
                date_str = trade.get('accept_date') or trade.get('offer_date')
                if not date_str: return datetime.min.replace(tzinfo=timezone.utc)
                try:
                    return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                except (ValueError, TypeError): return datetime.min.replace(tzinfo=timezone.utc)

            filtered_trades.sort(key=get_cancel_date, reverse=True)

            view = PaginationView(filtered_trades, _create_treasure_trades_embed, per_page=5)
            initial_embed = await view.get_page_embed()
            await ctx.send(embed=initial_embed, view=view)

        except Exception as e:
            await ctx.send(f"An error occurred: {e}", ephemeral=True)
 
    @commands.hybrid_command(name="bounty", description="Find active bounties.")
    @discord.app_commands.describe(
        bounty_type="The type of bounty to search for.",
        price="The price range of the bounty.",
        active="Filter by nation inactivity.",
        sort="How to sort the bounties.",
        score="Your nation score to filter by war range"
    )
    @discord.app_commands.choices(
        bounty_type=[
            discord.app_commands.Choice(name="Any", value="ANY"),
            discord.app_commands.Choice(name="Ordinary", value="ORDINARY"),
            discord.app_commands.Choice(name="Attrition", value="ATTRITION"),
            discord.app_commands.Choice(name="Raid", value="RAID"),
            discord.app_commands.Choice(name="Nuclear", value="NUCLEAR"),
        ],
        price=[
            discord.app_commands.Choice(name="Any", value="any"),
            discord.app_commands.Choice(name=">$1M", value="1-4.9"),
            discord.app_commands.Choice(name=">$5M", value="5-9.9"),
            discord.app_commands.Choice(name=">$10M", value="10-19.9"),
            discord.app_commands.Choice(name=">$20M", value="20-49.9"),
            discord.app_commands.Choice(name=">$50M", value="50+"),
        ],
        active=[
            discord.app_commands.Choice(name="Any", value="any"),
            discord.app_commands.Choice(name="7+ Days Inactive", value="7"),
            discord.app_commands.Choice(name="14+ Days Inactive", value="14"),
            discord.app_commands.Choice(name="28+ Days Inactive", value="28"),
        ],
        sort=[
            discord.app_commands.Choice(name="Price (High to Low)", value="price_desc"),
            discord.app_commands.Choice(name="Price (Low to High)", value="price_asc"),
            discord.app_commands.Choice(name="Activity (Most Recent First)", value="active_new"),
            discord.app_commands.Choice(name="Activity (Least Recent First)", value="active_old"),
        ]
    )
    async def bounty(self, ctx: commands.Context, bounty_type: str = "ANY", price: str = "any", active: str = "any", sort: str = "price_desc", score: Optional[float] = None):
        """Find and display active bounties based on specified criteria."""
        await ctx.defer()

        price_map = {
            "1-4.9": 1000000, "5-9.9": 5000000, "10-19.9": 10000000,
            "20-49.9": 20000000, "50+": 50000000
        }
        min_amount = price_map.get(price, 0)

        # Use user's score if provided
        user_score = score

        try:
            all_bounties_raw = await self._fetch_all_bounties(min_amount=min_amount)
            if not all_bounties_raw:
                await ctx.send("Could not retrieve bounty data or no bounties match the criteria.", ephemeral=True)
                return

            # --- Filtering ---
            filtered_bounties = [b for b in all_bounties_raw if b.get('nation', {}).get('vacation_mode_turns', 0) == 0]

            # Filter by war range if score parameter provided
            if user_score:
                min_war_score = user_score * 0.75  # -25%
                max_war_score = user_score * 2.5   # +150%
                filtered_bounties = [b for b in filtered_bounties if min_war_score <= (b.get('nation', {}).get('score', 0) or 0) <= max_war_score]

            if bounty_type.upper() != "ANY":
                filtered_bounties = [b for b in filtered_bounties if b.get('type', '').upper() == bounty_type.upper()]

            if active != "any":
                try:
                    days_inactive = int(active)
                    now = datetime.now(timezone.utc)
                    inactive_threshold = now - timedelta(days=days_inactive)
                    
                    def is_inactive(bounty):
                        last_active_str = bounty.get('nation', {}).get('last_active')
                        if not last_active_str: return False
                        try:
                            last_active_dt = datetime.fromisoformat(last_active_str.replace('Z', '+00:00'))
                            return last_active_dt < inactive_threshold
                        except (ValueError, TypeError): return False
                    
                    filtered_bounties = [b for b in filtered_bounties if is_inactive(b)]
                except ValueError: pass

            # --- Sorting ---
            def get_last_active(bounty):
                last_active_str = bounty.get('nation', {}).get('last_active')
                if not last_active_str: return datetime.min.replace(tzinfo=timezone.utc)
                try:
                    return datetime.fromisoformat(last_active_str.replace('Z', '+00:00'))
                except (ValueError, TypeError): return datetime.min.replace(tzinfo=timezone.utc)

            if sort == "price_asc":
                filtered_bounties.sort(key=lambda b: b.get('amount', 0))
            elif sort == "active_new":
                filtered_bounties.sort(key=get_last_active, reverse=True)
            elif sort == "active_old":
                filtered_bounties.sort(key=get_last_active)
            else: # price_desc (default)
                filtered_bounties.sort(key=lambda b: b.get('amount', 0), reverse=True)

            if not filtered_bounties:
                if user_score:
                    await ctx.send(f"No bounties found within your war range ({user_score * 0.75:,.0f} - {user_score * 2.5:,.0f} score).", ephemeral=True)
                else:
                    await ctx.send(f"No bounties found with the specified criteria.", ephemeral=True)
                return

            # --- Pagination ---
            view = PaginationView(
                filtered_bounties, 
                _create_bounties_embed, 
                per_page=5, 
                bounty_type=bounty_type, 
                price_range=price
            )
            initial_embed = await view.get_page_embed()
            await ctx.send(embed=initial_embed, view=view)

        except Exception as e:
            await ctx.send(f"An error occurred: {e}", ephemeral=True)


