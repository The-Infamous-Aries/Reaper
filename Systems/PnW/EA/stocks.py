import discord
from discord import app_commands, ui
from discord.ext import commands
import time
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Optional, Tuple
import io
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import asyncio
import Systems.Functions.database_manager as db_manager
import Systems.Functions.emoji as emoji_mod

def _prepare_dataframe(raw_data: List[Tuple[int, str, float]]) -> pd.DataFrame:
    """Converts raw price data into a prepared pandas DataFrame."""
    if not raw_data:
        return pd.DataFrame()
    
    df = pd.DataFrame(raw_data, columns=['timestamp', 'resource', 'price'])
    df['date'] = pd.to_datetime(df['timestamp'], unit='s')
    df = df.drop_duplicates(subset=['date', 'resource'], keep='last').sort_values('date')
    return df

def _render_graph_process(price_data, title, single_resource, scale, width, height, start_ts=None, end_ts=None):
    """
    Generates a graph image from price data in a separate process.
    """
    import pandas as pd
    import plotly.graph_objects as go
    import plotly.io as pio
    from plotly import colors
    from itertools import cycle
    from datetime import datetime

    pio.templates.default = "reaper_dark"
    
    if not isinstance(price_data, pd.DataFrame):
        df = _prepare_dataframe(price_data)
    else:
        df = price_data
    df = df.set_index('date')

    fig = go.Figure()
    color_cycle = cycle(colors.qualitative.Plotly)
    
    if single_resource:
        groups = [(df['resource'].iloc[0], df)] if not df.empty else []
    else:
        fig.update_layout(legend_title_text='Toggle Resources')
        groups = df.groupby('resource')

    for resource_name, res_df in groups:
        resource_name_upper = resource_name.upper()
        color = RESOURCE_COLORS.get(resource_name_upper, next(color_cycle))

        if len(res_df) > 1:
            fig.add_trace(go.Scatter(
                x=res_df.index, y=res_df['price'], mode='lines', 
                name=resource_name_upper.title(), line=dict(color=color, width=2),
                connectgaps=False
            ))
    
    fig.update_layout(
        title=title, xaxis_title='Date', yaxis_title='Price (PPU)', 
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), 
        height=height, width=width, uirevision='true', hovermode='x unified'
    )

    if start_ts and end_ts:
        fig.update_xaxes(range=[datetime.fromtimestamp(start_ts), datetime.fromtimestamp(end_ts)])
    
    return pio.to_image(fig, format='png', scale=scale, engine='kaleido')


# --- Constants ---
RESOURCE_COLORS = {
    "FOOD": "#2ecc71", "COAL": "#34495e", "OIL": "#f39c12", "URANIUM": "#27ae60",
    "LEAD": "#e74c3c", "IRON": "#8e44ad", "BAUXITE": "#e67e22", "GASOLINE": "#f1c40f",
    "MUNITIONS": "#c0392b", "STEEL": "#9b59b6", "ALUMINUM": "#d35400", "CREDIT": "#3498db"
}
RESOURCES = [
    "FOOD", "COAL", "OIL", "URANIUM", "LEAD", "IRON", "BAUXITE",
    "GASOLINE", "MUNITIONS", "STEEL", "ALUMINUM", "CREDIT"
]
RAW_RESOURCES = {"COAL": "blue", "OIL": "goldenrod", "LEAD": "red", "URANIUM": "green", "IRON": "purple", "BAUXITE": "orange"}
MAN_RESOURCES = {"GASOLINE": "goldenrod", "MUNITIONS": "red", "STEEL": "purple", "ALUMINUM": "orange"}
FOOD_RESOURCES = {"FOOD": "green"}
CREDIT_RESOURCES = {"CREDIT": "blue"}

# --- Plotly Setup ---
pio.templates["reaper_dark"] = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor='#2f3136',
        plot_bgcolor='#2f3136',
        font=dict(color='#ffffff'),
        title_font=dict(size=24, color='#ffffff'),
        xaxis=dict(gridcolor='#44474c', linecolor='#44474c'),
        yaxis=dict(gridcolor='#44474c', linecolor='#44474c'),
        legend=dict(bgcolor='#2f3136', bordercolor='#44474c')
    )
)
pio.templates.default = "reaper_dark"


# --- UI Elements ---
class DateRangeModal(ui.Modal, title='Select Date Range'):
    start_date_input = ui.TextInput(label='Start Date (YYYY-MM-DD)', placeholder='e.g., 2023-01-01', required=True)
    end_date_input = ui.TextInput(label='End Date (YYYY-MM-DD)', placeholder='e.g., 2023-12-31', required=True)

    def __init__(self, cog_instance: 'ResourceStocks'):
        super().__init__()
        self.cog = cog_instance

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            start_date_str = self.start_date_input.value
            end_date_str = self.end_date_input.value
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)

            if start_date >= end_date:
                await interaction.followup.send("Start date must be before the end date.", ephemeral=True)
                return

            start_ts = int(start_date.timestamp())
            end_ts = int(end_date.timestamp())

            raw_data = await db_manager.get_resource_prices_for_range(start_ts, end_ts)
            if not raw_data:
                await interaction.followup.send("No data found for the selected date range.", ephemeral=True)
                return
            
            df = _prepare_dataframe(raw_data)
            prices_data = self.cog._optimize_price_data(df, max_points=1200)
            
            embed = discord.Embed(title="Historical Market Data", color=discord.Color.blue())
            graph_file = await self.cog._create_graph(prices_data, f"Market History: {start_date_str} to {end_date_str}")
            
            if graph_file:
                embed.set_image(url=f"attachment://{graph_file.filename}")
                await interaction.followup.send(embed=embed, file=graph_file, ephemeral=True)
            else:
                footer_text = self.cog._get_graph_failure_reason()
                embed.description = "Could not generate graph."
                embed.set_footer(text=footer_text)
                await interaction.followup.send(embed=embed, ephemeral=True)

        except ValueError:
            await interaction.followup.send("Invalid date format. Please use YYYY-MM-DD.", ephemeral=True)
        except Exception as e:
            self.cog.logger.error(f"Error in DateRangeModal: {e}", exc_info=True)
            await interaction.followup.send("An error occurred while processing your request.", ephemeral=True)

async def resource_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=resource, value=resource)
        for resource in RESOURCES if current.lower() in resource.lower()
    ][:25]

class ResourceStocks(commands.Cog):
    def __init__(self, bot, query_instance, calc_instance):
        self.bot = bot
        self.logger = logging.getLogger("ResourceStocks")
        self.query = query_instance
        self.calc = calc_instance
        self.kaleido_installed = False

    async def cog_load(self):
        self.logger.info("Loading ResourceStocks Cog...")
        self._check_kaleido()
        if not hasattr(self.bot, 'process_executor'):
            from concurrent.futures import ProcessPoolExecutor
            self.bot.process_executor = ProcessPoolExecutor(max_workers=2)
        self.logger.info("ResourceStocks Cog loaded.")

    def cog_unload(self):
        if hasattr(self.bot, 'process_executor'):
            self.bot.process_executor.shutdown(wait=True)
            del self.bot.process_executor
        self.logger.info("ResourceStocks Cog unloaded.")

    def _check_kaleido(self):
        try:
            import kaleido
            self.kaleido_installed = True
        except ImportError:
            self.logger.warning("Kaleido package not found. Image generation will be disabled. Run `pip install kaleido`.")
            self.kaleido_installed = False

    def _get_graph_failure_reason(self) -> str:
        if not self.kaleido_installed:
            return "⚠️ Graph generation failed. The `kaleido` package is missing."
        return "📈 Graph could not be generated. Check logs for more details."

    def _optimize_price_data(self, price_data: pd.DataFrame, max_points: int = 1000) -> pd.DataFrame:
        if price_data.empty or len(price_data) <= max_points:
            return price_data
        from lttb import downsample
        optimized_data = []
        for resource_name, res_df in price_data.groupby('resource'):
            if len(res_df) > max_points:
                np_data = res_df.reset_index()[['date', 'price']].values
                np_data[:, 0] = res_df.index.astype(int) // 10**9
                downsampled_np = downsample(np_data, n_out=max_points)
                downsampled_df = pd.DataFrame(downsampled_np, columns=['timestamp', 'price'])
                downsampled_df['date'] = pd.to_datetime(downsampled_df['timestamp'], unit='s')
                downsampled_df['resource'] = resource_name
                optimized_data.append(downsampled_df.set_index('date'))
            else:
                optimized_data.append(res_df)
        return pd.concat(optimized_data)

    async def _create_graph(self, price_data: pd.DataFrame, title: str, single_resource: bool = False, start_ts: Optional[int] = None, end_ts: Optional[int] = None) -> Optional[discord.File]:
        if price_data.empty or len(price_data) < 2:
            return None
        try:
            loop = asyncio.get_event_loop()
            img_bytes = await loop.run_in_executor(
                self.bot.process_executor,
                _render_graph_process,
                price_data, title, single_resource, 1.0, 1200, 800, start_ts, end_ts
            )
            if img_bytes:
                return discord.File(io.BytesIO(img_bytes), filename="market_graph.png")
        except Exception as e:
            self.logger.error(f"Failed to create graph: {e}", exc_info=True)
        return None

    def _build_market_embed(self, current_prices: Dict[str, float], prev_prices: Dict[str, float], timestamp: int) -> discord.Embed:
        description = f"Last Updated: <t:{timestamp}:R>"
        embed = discord.Embed(title=f"{emoji_mod.mention('data') or '📈'} PnW Market Prices", description=description, color=discord.Color.gold())
        if not current_prices:
            embed.description += "\n\nMarket data not yet available. Please try again shortly."
            return embed

        resource_groups = [
            ["FOOD", "COAL", "OIL", "URANIUM"],      
            ["LEAD", "IRON", "BAUXITE", "GASOLINE"],  
            ["MUNITIONS", "STEEL", "ALUMINUM", "CREDIT"] 
        ]
        
        for group in resource_groups:
            field_values = []
            for res in group:
                price = current_prices.get(res, 0.0)
                prev = prev_prices.get(res, 0.0)
                value = "❌ No Data"
                if res in current_prices:
                    price_int = int(price)
                    price_str = f"${price_int:,}"
                    if prev > 0 and prev != price:
                        diff = price - prev
                        pct = (diff / prev) * 100
                        price_emoji = emoji_mod.mention('dollarup') if diff > 0 else emoji_mod.mention('dollardown')
                        pct_emoji = emoji_mod.mention('perup') if pct > 0 else emoji_mod.mention('perdown')
                        diff_int = int(diff)
                        change_str = f"{price_emoji or ('📈' if diff > 0 else '📉')} ${diff_int:+d}"
                        pct_str = f"{pct_emoji or ('📈' if pct > 0 else '📉')} {pct:+.1f}%"
                        value = f"{price_str} ({change_str}) {pct_str}"
                    else:
                        value = f"🆕 ${price_int:,}"
                
                emoji_key = emoji_mod.RESOURCE_EMOJI_NAMES.get(res)
                resource_emoji = emoji_mod.mention(emoji_key) if emoji_key else ''
                field_values.append(f"**{resource_emoji} {res.title()}**\n{value}")
            embed.add_field(name="\u200b", value="\n".join(field_values), inline=True)
            
        return embed

    @app_commands.command(name="stocks", description="Display P&W market prices and trends.")
    @app_commands.describe(graph_type="Choose the type of graph to display")
    @app_commands.choices(graph_type=[
        app_commands.Choice(name="All Resources", value="all"),
        app_commands.Choice(name="Raw Resources", value="raw"),
        app_commands.Choice(name="Manufactured Resources", value="man"),
        app_commands.Choice(name="Food", value="food"),
        app_commands.Choice(name="Credit", value="credit"),
    ])
    async def stocks(self, interaction: discord.Interaction, graph_type: str = 'all'):
        await interaction.response.defer()
        try:
            latest_prices = await db_manager.get_latest_resource_prices()
            if not latest_prices:
                await interaction.followup.send("Could not fetch latest market prices. Please try again later.", ephemeral=True)
                return

            raw_data = await db_manager.get_historical_resource_prices(days=30, min_entries=24)
            price_history = self._optimize_price_data(_prepare_dataframe(raw_data), max_points=600)
            comparison_prices = await db_manager.get_comparison_resource_prices(hours_ago=2)
            timestamp = int(datetime.now().timestamp())

            embed = self._build_market_embed(latest_prices, comparison_prices, timestamp)

            graph_data_map = {
                'raw': RAW_RESOURCES,
                'man': MAN_RESOURCES,
                'food': FOOD_RESOURCES,
                'credit': CREDIT_RESOURCES
            }
            if graph_type in graph_data_map:
                graph_data = price_history[price_history['resource'].isin(graph_data_map[graph_type])]
            else:
                graph_data = price_history

            graph_file = await self._create_graph(graph_data, f"{graph_type.title()} Resources Price Trend")
            if graph_file:
                embed.set_image(url=f"attachment://{graph_file.filename}")
                await interaction.followup.send(embed=embed, file=graph_file)
            else:
                embed.set_footer(text="📈 Not enough data for a 30-day trend graph yet.")
                await interaction.followup.send(embed=embed)

        except Exception as e:
            self.logger.error(f"Error in stocks command: {e}", exc_info=True)
            await interaction.followup.send("An error occurred while fetching stock data.", ephemeral=True)

    @app_commands.command(name="history", description="Show historical market data for a custom date range")
    async def history(self, interaction: discord.Interaction):
        min_ts, max_ts = await db_manager.get_all_time_resource_price_range()
        if not min_ts:
            await interaction.response.send_message("No historical data available yet.", ephemeral=True)
            return
        await interaction.response.send_modal(DateRangeModal(self))

async def setup(bot):
    if not (alliance_cog := bot.get_cog('AllianceManager')):
        return logging.error("Failed to add ResourceStocks cog: AllianceManager cog not found.")
    if not (query_instance := getattr(alliance_cog, 'query_system', None)) or not (calc_instance := getattr(alliance_cog, 'calc_system', None)):
        return logging.error("Failed to add ResourceStocks: Could not find query_system or calc_system in AllianceManager.")
    await bot.add_cog(ResourceStocks(bot, query_instance, calc_instance))
