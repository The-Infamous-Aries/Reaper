#!/usr/bin/env python3
"""
Interactive War Graph Generator

This module contains all the logic for generating interactive pie charts
for war breakdown visualization in Politics & War Discord bot.
"""

import plotly.graph_objects as go
import plotly.io as pio
import os
import random
from typing import Dict, Any, List, Optional
from datetime import datetime


class WarGraphGenerator:
    """Generates interactive war breakdown graphs using Plotly."""
    
    def __init__(self):
        self.web_dir = None
        self.public_url = None
        self.port = 8000
        self._setup_web_directory()
    
    def _setup_web_directory(self):
        """Setup the web directory for HTML output."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, '..', '..', '..', '..'))
        self.web_dir = os.path.join(project_root, 'web')
        os.makedirs(self.web_dir, exist_ok=True)
    
    def set_public_url(self, public_url: str, port: int = 8000):
        """Set the public URL and port for the web server."""
        self.public_url = public_url
        self.port = port
    
    def generate_interactive_breakdown(self, nation_breakdown: Dict[int, Any], alliance_name: str, resource_prices: dict) -> str:
        """Generates an interactive sunburst chart for war breakdown with detailed tooltips and nation toggles."""
        
        # Store original nation data for toggle functionality
        self.original_nation_data = nation_breakdown.copy()
        self.resource_prices = resource_prices
        
        # Prepare data for the sunburst chart
        ids = ["Total"]
        labels = ["Total"]
        parents = [""]
        values = [sum(c['gross_cost'] for c in nation_breakdown.values())]
        customdata = [f"Total Gross Cost: ${values[0]:,.0f}"]
        
        # Generate 100+ distinct nation colors using HSL color space
        nation_colors = self._generate_nation_colors(120)
        
        # Sort nations by gross cost for consistent layout
        sorted_nations = sorted(nation_breakdown.values(), key=lambda x: x['gross_cost'], reverse=True)

        for nation_idx, costs in enumerate(sorted_nations):
            nation_name = costs['name']
            nation_gross_cost = costs['gross_cost']
            if nation_gross_cost <= 0:
                continue

            # Get nation color
            nation_color = nation_colors[nation_idx % len(nation_colors)]
            
            # Add nation to the chart
            ids.append(nation_name)
            labels.append(nation_name)
            parents.append("Total")
            values.append(nation_gross_cost)
            customdata.append(
                f"<b>Gross Cost:</b> ${costs['gross_cost']:,.0f}<br>" +
                f"<b>Gains:</b> ${costs['total_gains']:,.0f}<br>" +
                f"<b>Net Cost:</b> ${costs['net_cost']:,.0f}"
            )

            # Define cost components for this nation with detailed hover information
            cost_components = {
                "Units": {
                    'value': costs['soldiers_lost'] * (5) + 
                             costs['tanks_lost'] * (60 + (0.5 * resource_prices['buy'].get('steel', 0))) + 
                             costs['aircraft_lost'] * (4000 + (10 * resource_prices['buy'].get('aluminum', 0))) + 
                             costs['ships_lost'] * (50000 + (30 * resource_prices['buy'].get('steel', 0))) + 
                             costs['missiles_lost'] * (150000 + (100 * resource_prices['buy'].get('gasoline', 0)) + (100 * resource_prices['buy'].get('munitions', 0)) + (150 * resource_prices['buy'].get('aluminum', 0))) +
                             costs['nukes_lost'] * (1750000 + (500 * resource_prices['buy'].get('uranium', 0)) + (500 * resource_prices['buy'].get('gasoline', 0)) + (1000 * resource_prices['buy'].get('aluminum', 0))),
                    'details': self._generate_units_hover_details(costs, resource_prices)
                },
                "Consumption": {
                    'value': costs['consumption_cost'],
                    'details': self._generate_consumption_hover_details(costs, resource_prices)
                },
                "Infrastructure": {
                    'value': costs['infra_destroyed_value'],
                    'details': self._generate_infrastructure_hover_details(costs)
                },
                "Improvements": {
                    'value': costs['improvements_cost'],
                    'details': self._generate_improvements_hover_details(costs)
                },
                "Money Destroyed": {
                    'value': costs['money_destroyed'],
                    'details': f"💸 ${costs['money_destroyed']:,.0f} cash destroyed"
                },
                "Loot Lost": {
                    'value': costs['loot_lost'] + costs['resource_loot_lost_value'],
                    'details': self._generate_loot_lost_hover_details(costs)
                },
                "Loot Gained": {
                    'value': costs['loot_received'] + costs['resource_loot_value'],
                    'details': self._generate_loot_gained_hover_details(costs)
                }
            }

            # Add cost components to the chart with proper coloring
            for comp_name, comp_data in cost_components.items():
                if comp_data['value'] > 0:
                    comp_id = f"{nation_name}-{comp_name}"
                    ids.append(comp_id)
                    labels.append(comp_name)
                    parents.append(nation_name)
                    values.append(comp_data['value'])
                    customdata.append(comp_data['details'])

        # Create the sunburst figure with enhanced styling
        fig = go.Figure(go.Sunburst(
            ids=ids,
            labels=labels,
            parents=parents,
            values=values,
            branchvalues="total",
            hovertemplate="<b>%{label}</b><br>Value: %{value:$,.0f}<br><br>%{customdata}<extra></extra>",
            customdata=customdata,
            marker={
                "colors": self._generate_colors_for_sunburst(ids, labels, parents, nation_colors),
                "line": {"color": "white", "width": 2}
            },
            textfont={"color": "white", "size": 12}
        ))

        fig.update_layout(
            title_text=f"Interactive War Breakdown for {alliance_name}",
            margin=dict(t=80, l=0, r=0, b=0),
            paper_bgcolor="rgba(48,51,57,255)",
            font={"color": "white"}
        )

        # Generate HTML with nation toggle menu
        html_content = self._generate_html_with_toggles(fig, sorted_nations, alliance_name)
        
        filename = f"war_breakdown_{random.randint(1000, 9999)}.html"
        file_path = os.path.join(self.web_dir, filename)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return filename
    
    def _generate_nation_colors(self, count=100):
        """Generate 100+ distinct nation colors using HSL color space."""
        colors = []
        # Use golden angle for optimal color distribution
        golden_angle = 137.5
        
        for i in range(count):
            # Calculate hue using golden angle for maximum distinction
            hue = (i * golden_angle) % 360
            
            # Vary saturation and lightness to create more distinct colors
            saturation = 60 + (i % 4) * 10  # 60-90%
            lightness = 45 + (i % 3) * 10  # 45-65%
            
            # Convert HSL to RGB
            h = hue / 360
            s = saturation / 100
            l = lightness / 100
            
            # HSL to RGB conversion
            c = (1 - abs(2 * l - 1)) * s
            x = c * (1 - abs((h * 6) % 2 - 1))
            m = l - c / 2
            
            if h < 1/6:
                r, g, b = c, x, 0
            elif h < 2/6:
                r, g, b = x, c, 0
            elif h < 3/6:
                r, g, b = 0, c, x
            elif h < 4/6:
                r, g, b = 0, x, c
            elif h < 5/6:
                r, g, b = x, 0, c
            else:
                r, g, b = c, 0, x
            
            # Convert to hex
            r = int((r + m) * 255)
            g = int((g + m) * 255)
            b = int((b + m) * 255)
            
            hex_color = f"#{r:02X}{g:02X}{b:02X}"
            colors.append(hex_color)
        
        return colors
    
    def _generate_colors_for_sunburst(self, ids, labels, parents, nation_colors):
        """Generate colors for sunburst chart with dynamic shading."""
        colors = []
        nation_color_map = {}
        
        for i, parent in enumerate(parents):
            if not parent:
                colors.append("#2c3e50") # Center color
                continue
            
            nation_name = parent if '-' not in ids[i] else ids[i].split('-')[0]
            if nation_name not in nation_color_map:
                nation_color_map[nation_name] = nation_colors[len(nation_color_map) % len(nation_colors)]
            
            if '-' in ids[i] and labels[i] in ["Units", "Consumption", "Infrastructure", "Improvements", "Money Destroyed", "Loot Lost", "Loot Gained"]:
                # This is a cost type, generate dynamic shading
                base_color = nation_color_map[nation_name]
                shaded_color = self.get_cost_type_color(base_color, labels[i])
                colors.append(shaded_color)
            else:
                # This is a nation
                colors.append(nation_color_map[nation_name])
        return colors
    
    def get_cost_type_color(self, base_color, cost_type):
        """Generate cost type color by adjusting the base nation color."""
        # Convert hex to RGB
        base_color = base_color.lstrip('#')
        r = int(base_color[0:2], 16)
        g = int(base_color[2:4], 16)
        b = int(base_color[4:6], 16)
        
        # Convert RGB to HSL
        r_norm = r / 255
        g_norm = g / 255
        b_norm = b / 255
        
        max_val = max(r_norm, g_norm, b_norm)
        min_val = min(r_norm, g_norm, b_norm)
        l = (max_val + min_val) / 2
        
        if max_val == min_val:
            h = s = 0
        else:
            d = max_val - min_val
            s = d / (2 - max_val - min_val) if l > 0.5 else d / (max_val + min_val)
            
            if max_val == r_norm:
                h = (g_norm - b_norm) / d + (6 if g_norm < b_norm else 0)
            elif max_val == g_norm:
                h = (b_norm - r_norm) / d + 2
            else:
                h = (r_norm - g_norm) / d + 4
            h /= 6
        
        # Adjust lightness based on cost type
        if cost_type == "Units":
            l = max(0.2, l - 0.15)  # Darker
        elif cost_type == "Consumption":
            l = min(0.8, l + 0.1)   # Lighter
        elif cost_type == "Infrastructure":
            l = max(0.3, l - 0.1)   # Slightly darker
        elif cost_type == "Improvements":
            l = min(0.7, l + 0.05)  # Slightly lighter
        elif cost_type == "Money Destroyed":
            l = max(0.15, l - 0.2)  # Much darker
        elif cost_type == "Loot Lost":
            l = max(0.25, l - 0.12)  # Darker
        elif cost_type == "Loot Gained":
            l = min(0.85, l + 0.2)   # Much lighter (gains)
        
        # Convert back to RGB
        c = (1 - abs(2 * l - 1)) * s
        x = c * (1 - abs((h * 6) % 2 - 1))
        m = l - c / 2
        
        if h < 1/6:
            r_new, g_new, b_new = c, x, 0
        elif h < 2/6:
            r_new, g_new, b_new = x, c, 0
        elif h < 3/6:
            r_new, g_new, b_new = 0, c, x
        elif h < 4/6:
            r_new, g_new, b_new = 0, x, c
        elif h < 5/6:
            r_new, g_new, b_new = x, 0, c
        else:
            r_new, g_new, b_new = c, 0, x
        
        r_new = int((r_new + m) * 255)
        g_new = int((g_new + m) * 255)
        b_new = int((b_new + m) * 255)
        
        return f"#{r_new:02X}{g_new:02X}{b_new:02X}"
    
    def _generate_units_hover_details(self, costs: dict, resource_prices: dict) -> str:
        """Generate detailed hover information for units."""
        details = "<b>Unit Losses:</b><br>"
        unit_costs = {
            "soldiers": 5,
            "tanks": 60 + (0.5 * resource_prices['buy'].get('steel', 0)),
            "aircraft": 4000 + (10 * resource_prices['buy'].get('aluminum', 0)),
            "ships": 50000 + (30 * resource_prices['buy'].get('steel', 0)),
            "missiles": 150000 + (100 * resource_prices['buy'].get('gasoline', 0)) + (100 * resource_prices['buy'].get('munitions', 0)) + (150 * resource_prices['buy'].get('aluminum', 0)),
            "nukes": 1750000 + (500 * resource_prices['buy'].get('uranium', 0)) + (500 * resource_prices['buy'].get('gasoline', 0)) + (1000 * resource_prices['buy'].get('aluminum', 0)),
        }
        for unit, cost in unit_costs.items():
            lost_key = f'{unit}_lost'
            if costs.get(lost_key, 0) > 0:
                total_cost = costs[lost_key] * cost
                details += f"{costs[lost_key]:,} {unit.title()} - ${total_cost:,.0f}<br>"
        return details.strip("<br>")
    
    def _generate_consumption_hover_details(self, costs: dict, resource_prices: dict) -> str:
        """Generate detailed hover information for consumption."""
        details = "<b>Consumption Costs:</b><br>"
        gas_cost = costs['gas_used'] * resource_prices['buy'].get('gasoline', 0)
        mun_cost = costs['mun_used'] * resource_prices['buy'].get('munitions', 0)
        details += f"{costs['gas_used']:,} Gasoline - ${gas_cost:,.0f}<br>"
        details += f"{costs['mun_used']:,} Munitions - ${mun_cost:,.0f}<br>"
        return details.strip("<br>")
    
    def _generate_infrastructure_hover_details(self, costs: dict) -> str:
        """Generate detailed hover information for infrastructure."""
        return f"<b>Infrastructure Lost:</b><br>{costs['infra_destroyed']:,} levels - ${costs['infra_destroyed_value']:,.0f}"
    
    def _generate_improvements_hover_details(self, costs: dict) -> str:
        """Generate detailed hover information for improvements."""
        details = f"<b>Improvements Lost:</b><br>Total Cost: ${costs['improvements_cost']:,.0f}<br>"
        for imp, count in costs.get('improvements_destroyed', {}).items():
            details += f"{count} {imp.replace('_', ' ').title()}<br>"
        return details.strip("<br>")
    
    def _generate_loot_lost_hover_details(self, costs: dict) -> str:
        """Generate detailed hover information for loot lost."""
        details = f"<b>Loot Lost:</b><br>Total Cost: ${costs['loot_lost'] + costs['resource_loot_lost_value']:,.0f}<br>"
        details += f"Money Stolen/Destroyed: ${costs['loot_lost']:,.0f}<br>"
        details += f"Resources Lost: ${costs['resource_loot_lost_value']:,.0f}<br>"
        return details.strip("<br>")
    
    def _generate_loot_gained_hover_details(self, costs: dict) -> str:
        """Generate detailed hover information for loot gained."""
        details = f"<b>Loot Gained:</b><br>Total Gains: ${costs['loot_received'] + costs['resource_loot_value']:,.0f}<br>"
        details += f"Money Stolen: ${costs['loot_received']:,.0f}<br>"
        details += f"Resources Gained: ${costs['resource_loot_value']:,.0f}<br>"
        return details.strip("<br>")

    def _generate_html_with_toggles(self, fig, sorted_nations, alliance_name):
        """Generate HTML with nation toggle menu and interactive functionality."""
        # Get the Plotly chart HTML
        chart_html = pio.to_html(fig, include_plotlyjs=True, auto_open=False)
        
        # Create nation toggle data
        nation_toggle_data = []
        for nation in sorted_nations:
            if nation['gross_cost'] > 0:
                nation_toggle_data.append({
                    'name': nation['name'],
                    'total_cost': nation['gross_cost'],
                    'net_cost': nation['net_cost'],
                    'enabled': True
                })
        
        # HTML template with toggle menu
        html_template = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Interactive War Breakdown for {alliance_name}</title>
    <style>
        body {{
            margin: 0;
            padding: 0;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            color: white;
            min-height: 100vh;
        }}
        
        .container {{
            display: flex;
            height: 100vh;
            overflow: hidden;
        }}
        
        .sidebar {{
            width: 300px;
            background: rgba(48, 51, 57, 0.9);
            backdrop-filter: blur(10px);
            border-right: 1px solid rgba(255, 255, 255, 0.1);
            padding: 20px;
            overflow-y: auto;
            box-shadow: 2px 0 10px rgba(0, 0, 0, 0.3);
        }}
        
        .sidebar h2 {{
            margin: 0 0 20px 0;
            color: #ffffff;
            font-size: 1.4em;
            text-align: center;
            border-bottom: 2px solid #7289da;
            padding-bottom: 10px;
        }}
        
        .nation-toggle {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 15px;
            margin: 8px 0;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.2);
            transition: all 0.3s ease;
            cursor: pointer;
        }}
        
        .nation-toggle:hover {{
            background: rgba(255, 255, 255, 0.15);
            transform: translateX(5px);
        }}
        
        .nation-toggle.disabled {{
             opacity: 0.4;
             background: rgba(255, 255, 255, 0.05);
         }}
         
         .nation-toggle.expanded {{
             background: rgba(114, 137, 218, 0.3);
             border: 2px solid #7289da;
             transform: translateX(5px);
         }}
        
        .nation-info {{
            flex: 1;
            margin-right: 10px;
        }}
        
        .nation-name {{
            font-weight: 600;
            font-size: 0.95em;
            margin-bottom: 4px;
            color: #ffffff;
        }}
        
        .nation-costs {{
            font-size: 0.8em;
            color: #b9bbbe;
            line-height: 1.3;
        }}
        
        .toggle-switch {{
            position: relative;
            width: 50px;
            height: 24px;
            background: #7289da;
            border-radius: 12px;
            transition: background 0.3s ease;
            cursor: pointer;
            flex-shrink: 0;
        }}
        
        .toggle-switch.disabled {{
            background: #4f545c;
        }}
        
        .toggle-slider {{
            position: absolute;
            top: 2px;
            left: 2px;
            width: 20px;
            height: 20px;
            background: white;
            border-radius: 50%;
            transition: transform 0.3s ease;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
        }}
        
        .toggle-switch.disabled .toggle-slider {{
            transform: translateX(26px);
        }}
        
        .chart-container {{
            flex: 1;
            padding: 20px;
            display: flex;
            flex-direction: column;
        }}
        
        .controls {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding: 15px;
            background: rgba(48, 51, 57, 0.9);
            backdrop-filter: blur(10px);
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        
        .total-display {{
            font-size: 1.2em;
            font-weight: 600;
        }}
        
        .control-buttons {{
            display: flex;
            gap: 10px;
        }}
        
        .control-btn {{
            padding: 8px 16px;
            background: #7289da;
            border: none;
            border-radius: 6px;
            color: white;
            cursor: pointer;
            font-size: 0.9em;
            transition: background 0.3s ease;
        }}
        
        .control-btn:hover {{
             background: #5f73bc;
         }}
         
         .slice-hint {{
             position: absolute;
             top: 10px;
             right: 10px;
             background: rgba(0, 0, 0, 0.7);
             color: white;
             padding: 8px 12px;
             border-radius: 6px;
             font-size: 0.85em;
             opacity: 0;
             transition: opacity 0.3s ease;
             pointer-events: none;
         }}
         
         .slice-hint.show {{
             opacity: 1;
         }}
        
        #chart {{
            flex: 1;
            background: rgba(48, 51, 57, 0.9);
            backdrop-filter: blur(10px);
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            padding: 20px;
        }}
        
        .loading {{
            text-align: center;
            padding: 40px;
            color: #b9bbbe;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="sidebar">
            <h2>Nations Toggle</h2>
            <div id="nation-toggles">
                {self._generate_nation_toggles_html(nation_toggle_data)}
            </div>
        </div>
        <div class="chart-container">
            <div class="controls">
                <div class="total-display">
                    <div>Total Cost: <span id="total-cost">${sum(n['total_cost'] for n in nation_toggle_data):,.0f}</span></div>
                    <div>Net Cost: <span id="net-cost">${sum(n['net_cost'] for n in nation_toggle_data):,.0f}</span></div>
                </div>
                <div class="control-buttons">
                    <button class="control-btn" onclick="enableAllNations()">Enable All</button>
                    <button class="control-btn" onclick="disableAllNations()">Disable All</button>
                </div>
            </div>
            <div id="chart">
                 <div class="slice-hint" id="slice-hint">Click a nation slice to expand</div>
                 {chart_html}
             </div>
        </div>
    </div>

    <script>
        let originalData = {self._get_nation_data_json(nation_toggle_data)};
         let enabledNations = new Set(Object.keys(originalData));
         let chart = null;
         let expandedNation = null;
        
        // Wait for Plotly to load
         document.addEventListener('DOMContentLoaded', function() {{
             setTimeout(initializeChart, 100);
         }});
         
         function initializeChart() {{
             // Get the Plotly chart element
             const plotlyChart = document.querySelector('#chart .plotly-graph-div');
             if (plotlyChart && plotlyChart.data) {{
                 chart = plotlyChart;
                 
                 // Add click event listener for nation slices
                  chart.on('plotly_sunburstclick', function(eventData) {{
                     if (eventData.points && eventData.points[0]) {{
                          const clickedPoint = eventData.points[0];
                          const clickedId = clickedPoint.id;
                          const parent = clickedPoint.parent;
                          
                          // Only handle nation level clicks (direct children of "Total")
                          if (parent === "Total" && clickedId !== "Total") {{
                              toggleNationExpansion(clickedId);
                          }}
                      }}
                  }});
                  
                  // Add hover effects for nation slices
                  chart.on('plotly_hover', function(eventData) {{
                      if (eventData.points && eventData.points[0]) {{
                          const hoveredPoint = eventData.points[0];
                          const parent = hoveredPoint.parent;
                          
                          // Show hint when hovering over nation slices
                          if (parent === "Total" && hoveredPoint.id !== "Total") {{
                              document.getElementById('slice-hint').classList.add('show');
                          }}
                      }}
                  }});
                  
                  chart.on('plotly_unhover', function() {{
                      document.getElementById('slice-hint').classList.remove('show');
                  }});
                 
                 updateChart();
             }}
         }}
        
        function toggleNation(nationName) {{
             const toggle = document.querySelector(`[data-nation="${{nationName}}"]`);
             const switchElement = toggle.querySelector('.toggle-switch');
             
             if (enabledNations.has(nationName)) {{
                 enabledNations.delete(nationName);
                 toggle.classList.add('disabled');
                 switchElement.classList.add('disabled');
                 
                 // If this was the expanded nation, clear the expansion
                 if (expandedNation === nationName) {{
                     expandedNation = null;
                 }}
             }} else {{
                 enabledNations.add(nationName);
                 toggle.classList.remove('disabled');
                 switchElement.classList.remove('disabled');
             }}
             
             updateChart();
         }}
         
         function toggleNationExpansion(nationName) {{
             // If clicking the same expanded nation, collapse it
             if (expandedNation === nationName) {{
                 expandedNation = null;
             }} else {{
                 expandedNation = nationName;
             }}
             
             updateChart();
         }}
        
        function enableAllNations() {{
            enabledNations = new Set(Object.keys(originalData));
            document.querySelectorAll('.nation-toggle').forEach(toggle => {{
                toggle.classList.remove('disabled');
                toggle.querySelector('.toggle-switch').classList.remove('disabled');
            }});
            updateChart();
        }}
        
        function disableAllNations() {{
            enabledNations.clear();
            document.querySelectorAll('.nation-toggle').forEach(toggle => {{
                toggle.classList.add('disabled');
                toggle.querySelector('.toggle-switch').classList.add('disabled');
            }});
            updateChart();
        }}
        
        function updateChart() {{
             if (!chart || !chart.data) return;
             
             // Calculate new totals
             let totalCost = 0;
             let netCost = 0;
             
             enabledNations.forEach(nationName => {{
                 if (originalData[nationName]) {{
                     totalCost += originalData[nationName].total_cost;
                     netCost += originalData[nationName].net_cost;
                 }}
             }});
             
             // Update total displays
             document.getElementById('total-cost').textContent = `$${{totalCost.toLocaleString()}}`;
             document.getElementById('net-cost').textContent = `$${{netCost.toLocaleString()}}`;
             
             // Update sidebar nation indicators
             document.querySelectorAll('.nation-toggle').forEach(toggle => {{
                 const nationName = toggle.dataset.nation;
                 toggle.classList.remove('expanded');
                 
                 if (expandedNation === nationName) {{
                     toggle.classList.add('expanded');
                 }}
             }});
             
             // Filter chart data based on enabled nations
             if (chart.data && chart.data[0]) {{
                 const chartData = chart.data[0];
                 const filteredIds = [];
                 const filteredLabels = [];
                 const filteredParents = [];
                 const filteredValues = [];
                 const filteredCustomdata = [];
                 const filteredMarkers = {{ colors: [], line: chartData.marker.line }};
                 
                 // Keep the center "Total" node
                 filteredIds.push(chartData.ids[0]);
                 filteredLabels.push(chartData.labels[0]);
                 filteredParents.push(chartData.parents[0]);
                 filteredValues.push(totalCost);
                 filteredCustomdata.push(chartData.customdata[0]);
                 filteredMarkers.colors.push(chartData.marker.colors[0]);
                 
                 // Filter nations and their components
                 for (let i = 1; i < chartData.ids.length; i++) {{
                     const id = chartData.ids[i];
                     const parent = chartData.parents[i];
                     const originalColor = chartData.marker.colors[i];
                     
                     // Check if this is a nation node or its component
                     let shouldInclude = false;
                     let isExpandedNation = false;
                     
                     if (parent === "Total") {{
                         // This is a nation node
                         const nationName = id;
                         if (enabledNations.has(nationName)) {{
                             shouldInclude = true;
                             if (expandedNation === nationName) {{
                                 isExpandedNation = true;
                             }}
                         }}
                     }} else if (enabledNations.has(parent)) {{
                         // This is a component of an enabled nation
                         shouldInclude = true;
                         if (expandedNation === parent) {{
                             isExpandedNation = true;
                         }}
                     }}
                     
                     if (shouldInclude) {{
                         filteredIds.push(id);
                         filteredLabels.push(chartData.labels[i]);
                         filteredParents.push(parent);
                         
                         // Apply expansion effect
                         if (isExpandedNation) {{
                             // Make expanded nation/components more prominent
                             filteredValues.push(chartData.values[i] * 1.5); // Increase size by 50%
                             // Brighten the color for expanded items
                             filteredMarkers.colors.push(brightenColor(originalColor, 0.3));
                         }} else {{
                             filteredValues.push(chartData.values[i]);
                             filteredMarkers.colors.push(originalColor);
                         }}
                         
                         filteredCustomdata.push(chartData.customdata[i]);
                     }}
                 }}
                 
                 // Update the chart with filtered data
                 Plotly.react(chart, [{{
                     type: 'sunburst',
                     ids: filteredIds,
                     labels: filteredLabels,
                     parents: filteredParents,
                     values: filteredValues,
                     customdata: filteredCustomdata,
                     hovertemplate: chartData.hovertemplate,
                     marker: filteredMarkers,
                     textfont: chartData.textfont,
                     branchvalues: 'total',
                     // Add level settings to help with expansion visibility
                     level: expandedNation ? 'all' : undefined,
                     maxdepth: expandedNation ? 3 : undefined
                 }}], chart.layout);
             }}
             
             // Update title
             const visibleNations = enabledNations.size;
             const totalNations = Object.keys(originalData).length;
             const expansionText = expandedNation ? `<br><sub>Expanded: ${{expandedNation}}</sub>` : '';
             Plotly.relayout(chart, {{
                 title: {{
                     text: `Interactive War Breakdown for {alliance_name}<br><sub>${{visibleNations}} of ${{totalNations}} nations shown${{expansionText}}</sub>`
                 }}
             }});
         }}
        
        // Add click handlers to toggle switches
         document.addEventListener('click', function(e) {{
             if (e.target.closest('.toggle-switch')) {{
                 const nationToggle = e.target.closest('.nation-toggle');
                 const nationName = nationToggle.dataset.nation;
                 toggleNation(nationName);
             }}
         }});
         
         function brightenColor(hexColor, factor) {{
             // Convert hex to RGB
             hexColor = hexColor.replace('#', '');
             const r = parseInt(hexColor.substr(0, 2), 16);
             const g = parseInt(hexColor.substr(2, 2), 16);
             const b = parseInt(hexColor.substr(4, 2), 16);
             
             // Brighten each component
             const newR = Math.min(255, Math.round(r + (255 - r) * factor));
             const newG = Math.min(255, Math.round(g + (255 - g) * factor));
             const newB = Math.min(255, Math.round(b + (255 - b) * factor));
             
             // Convert back to hex
             return `#${{newR.toString(16).padStart(2, '0')}}${{newG.toString(16).padStart(2, '0')}}${{newB.toString(16).padStart(2, '0')}}`;
         }}
    </script>
</body>
</html>
        """
        
        return html_template
    
    def _generate_nation_toggles_html(self, nation_data):
        """Generate HTML for nation toggle buttons."""
        html = ""
        for nation in sorted(nation_data, key=lambda x: x['total_cost'], reverse=True):
            html += f"""
            <div class="nation-toggle" data-nation="{nation['name']}">
                <div class="nation-info">
                    <div class="nation-name">{nation['name']}</div>
                    <div class="nation-costs">
                        Total: ${nation['total_cost']:,.0f}<br>
                        Net: ${nation['net_cost']:,.0f}
                    </div>
                </div>
                <div class="toggle-switch">
                    <div class="toggle-slider"></div>
                </div>
            </div>
            """
        return html
    
    def _get_nation_data_json(self, nation_data):
        """Convert nation data to JSON for JavaScript."""
        import json
        data_dict = {}
        for nation in nation_data:
            data_dict[nation['name']] = {
                'total_cost': nation['total_cost'],
                'net_cost': nation['net_cost']
            }
        return json.dumps(data_dict)


# Create a singleton instance for easy import
war_graph_generator = WarGraphGenerator()