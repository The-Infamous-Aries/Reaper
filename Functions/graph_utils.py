import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly import colors
from itertools import cycle
from datetime import datetime
from typing import List, Tuple, Optional
import io
import asyncio
import discord

def _prepare_dataframe(raw_data: List[Tuple[int, str, float]]) -> pd.DataFrame:
    """Converts raw price data into a prepared pandas DataFrame."""
    if not raw_data:
        return pd.DataFrame()
    
    df = pd.DataFrame(raw_data, columns=['timestamp', 'resource', 'price'])
    df['date'] = pd.to_datetime(df['timestamp'], unit='s')
    df = df.drop_duplicates(subset=['date', 'resource'], keep='last').sort_values('date')
    return df

def _render_graph_process(price_data, title, single_resource, with_indicators, scale, width, height, start_ts=None, end_ts=None):
    """
    Generates a graph image from price data in a separate process.
    Optimized version that focuses on rendering, not data processing.
    """
    import pandas as pd
    import plotly.graph_objects as go
    import plotly.io as pio
    from plotly import colors
    from itertools import cycle
    from datetime import datetime

    # --- Plotly Setup (re-defined for the separate process) ---
    pio.templates.default = "reaper_dark"
    
    # Fast data prep - assume data is already optimized
    if not isinstance(price_data, pd.DataFrame):
        df = _prepare_dataframe(price_data)
    else:
        df = price_data
    df = df.set_index('date')

    fig = go.Figure()
    color_cycle = cycle(colors.qualitative.Plotly)
    
    # Efficient plotting - data should already be optimized
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
    
    # Use faster image generation settings
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
RAW_RESOURCES = ["COAL", "OIL", "LEAD", "URANIUM", "IRON", "BAUXITE"]
MAN_RESOURCES = ["GASOLINE", "MUNITIONS", "STEEL", "ALUMINUM"]
FOOD_RESOURCES = ["FOOD"]
CREDIT_RESOURCES = ["CREDIT"]

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

async def create_stock_graph(
    bot,
    price_data: pd.DataFrame,
    title: str,
    single_resource: bool = False,
    with_indicators: bool = True,
    start_ts: Optional[int] = None,
    end_ts: Optional[int] = None
) -> Optional[bytes]:
    """Creates a historical price graph and returns it as bytes."""
    import time
    start_time = time.time()

    if price_data.empty:
        return None
    
    if isinstance(price_data, pd.DataFrame):
        resource_counts = price_data.groupby('resource').size()
        if not any(resource_counts >= 2):
            return None

    try:
        # Ensure the DataFrame has the correct columns and types
        price_data['timestamp'] = pd.to_datetime(price_data['timestamp'], unit='s')
        price_data['price'] = pd.to_numeric(price_data['price'])
        price_data = price_data.sort_values('timestamp')

        # Prepare data for the render function
        if isinstance(price_data, pd.DataFrame):
            # Convert DataFrame to list format for the process function
            data_list = []
            for _, row in price_data.iterrows():
                data_list.append([
                    int(row['timestamp'].timestamp()),
                    row['resource'],
                    float(row['price'])
                ])
            price_data = data_list

        # Use Plotly render function
        img_bytes = await asyncio.get_event_loop().run_in_executor(
            bot.process_executor,
            _render_graph_process,
            price_data,
            title,
            single_resource,
            with_indicators,
            1.0,  # scale
            1200,  # width
            800,    # height
            start_ts,
            end_ts
        )

        if img_bytes is None:
            return None

        return img_bytes

    except Exception as e:
        print(f"Failed to create graph '{title}': {e}")
        return None
