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
import hashlib


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
    
    def generate_interactive_breakdown(self, nation_breakdown: Dict[int, Any], alliance_name: str, resource_prices: dict, as_html: bool = False) -> str:
        """Generates an interactive sunburst chart for war breakdown with cost types as primary slices."""

        cost_types = ["Units", "Consumption", "Infrastructure", "Improvements", "Net Loot"]
        
        # Data for sunburst
        ids = ["Total"]
        labels = ["Total War Costs"]
        parents = [""]
        values = [0] # Will be calculated later
        customdata = [""]
        
        # Intermediate data storage
        cost_type_totals = {cost_type: 0 for cost_type in cost_types}
        nation_costs_by_type = {cost_type: [] for cost_type in cost_types}

        # Process each nation
        sorted_nations = sorted(nation_breakdown.values(), key=lambda x: x['gross_cost'], reverse=True)
        for costs in sorted_nations:
            nation_name = costs['name']
            
            # Calculate net loot (negative means gain, positive means loss)
            loot_gained = costs.get('loot_received', 0) + costs.get('resource_loot_value', 0)
            loot_lost = costs.get('loot_lost', 0) + costs.get('resource_loot_lost_value', 0)
            net_loot = loot_lost - loot_gained  # Positive = net loss, Negative = net gain
            
            cost_components = {
                "Units": costs['soldiers_lost'] * 5 + costs['tanks_lost'] * (60 + 0.5 * resource_prices['buy'].get('steel', 0)) + costs['aircraft_lost'] * (4000 + 10 * resource_prices['buy'].get('aluminum', 0)) + costs['ships_lost'] * (50000 + 30 * resource_prices['buy'].get('steel', 0)) + costs['missiles_lost'] * (150000 + 100 * resource_prices['buy'].get('gasoline', 0) + 100 * resource_prices['buy'].get('munitions', 0) + 150 * resource_prices['buy'].get('aluminum', 0)) + costs['nukes_lost'] * (1750000 + 500 * resource_prices['buy'].get('uranium', 0) + 500 * resource_prices['buy'].get('gasoline', 0) + 1000 * resource_prices['buy'].get('aluminum', 0)),
                "Consumption": costs['consumption_cost'],
                "Infrastructure": costs['infra_destroyed_value'],
                "Improvements": costs['improvements_cost'],
                "Net Loot": net_loot,
            }

            for cost_type, value in cost_components.items():
                if value > 0:
                    cost_type_totals[cost_type] += value
                    nation_costs_by_type[cost_type].append({'name': nation_name, 'cost': value})

        # Calculate adjusted total cost (subtract net loot gains)
        total_war_cost = sum(cost_type_totals.values())
        net_loot_adjustment = 0
        if "Net Loot" in cost_type_totals and cost_type_totals["Net Loot"] < 0:
            net_loot_adjustment = abs(cost_type_totals["Net Loot"])
            total_war_cost -= net_loot_adjustment
        
        values[0] = total_war_cost
        customdata[0] = f"Total War Cost: ${total_war_cost:,.0f}"
        if net_loot_adjustment > 0:
            customdata[0] += f"<br>(Net loot gains reduced total by ${net_loot_adjustment:,.0f})"

        for cost_type, total_cost in cost_type_totals.items():
            if total_cost != 0:  # Allow negative values for Net Loot
                ids.append(cost_type)
                if cost_type == "Net Loot" and total_cost < 0:
                    labels.append("Net Loot Gain")
                else:
                    labels.append(cost_type)
                parents.append("Total")
                values.append(abs(total_cost))  # Use absolute value for sizing
                
                # Create hover text for the cost type slice
                sorted_nations = sorted(nation_costs_by_type[cost_type], key=lambda x: x['cost'], reverse=True)
                display_name = "Net Loot Gain" if cost_type == "Net Loot" and total_cost < 0 else cost_type
                hover_text = f"<b>{display_name} - Top Nations:</b><br>"
                for nation in sorted_nations:
                    if cost_type == "Net Loot" and nation['cost'] < 0:
                        hover_text += f"{nation['name']}: <span style='color: #2ecc71'>${abs(nation['cost']):,.0f} gain</span><br>"
                    else:
                        hover_text += f"{nation['name']}: ${nation['cost']:,.0f}<br>"
                customdata.append(hover_text)
                
                # Add nations as children of the cost type
                for nation in sorted_nations:
                    nation_id = f"{cost_type}-{nation['name']}"
                    ids.append(nation_id)
                    labels.append(nation['name'])
                    parents.append(cost_type)
                    values.append(abs(nation['cost']))  # Use absolute value for sizing
                    if cost_type == "Net Loot" and nation['cost'] < 0:
                        customdata.append(f"<b>{nation['name']}</b><br>{cost_type} Gain: ${abs(nation['cost']):,.0f}")
                    else:
                        customdata.append(f"<b>{nation['name']}</b><br>{cost_type} Cost: ${nation['cost']:,.0f}")

        # Create the sunburst figure
        fig = go.Figure(go.Sunburst(
            ids=ids,
            labels=labels,
            parents=parents,
            values=values,
            branchvalues="total",
            hovertemplate="<b>%{label}</b><br>Value: $%{value:,.0f}<br><br>%{customdata}<extra></extra>",
            customdata=customdata,
            maxdepth=2 # Show cost types initially
        ))

        fig.update_layout(
            title_text=f"Interactive War Breakdown for {alliance_name}",
            height=1200, # Taller graph
            paper_bgcolor="rgba(48,51,57,255)",
            font={"color": "white"},
        )
        
        # Generate HTML content
        html_content = pio.to_html(fig, full_html=True)
        
        # Save to file for web access in Wars directory
        from datetime import datetime
        
        # Generate filename with proper naming convention: warbd_{alliancename}_{mm/dd/yyyy format timestamp}.html
        timestamp = datetime.now().strftime("%m-%d-%Y")
        alliance_clean = "".join(c for c in alliance_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        alliance_clean = alliance_clean.replace(' ', '_')
        html_filename = f"warbd_{alliance_clean}_{timestamp}.html"
        
        # Create Wars directory if it doesn't exist
        wars_dir = os.path.join(self.web_dir, 'Wars')
        os.makedirs(wars_dir, exist_ok=True)
        
        # Write HTML file to Wars directory
        html_file_path = os.path.join(wars_dir, html_filename)
        with open(html_file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return html_filename


# Create a singleton instance for easy import
war_graph_generator = WarGraphGenerator()