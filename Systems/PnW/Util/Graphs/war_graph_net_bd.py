#!/usr/bin/env python3
"""
Interactive War Net Breakdown Graph Generator

This module contains all the logic for generating interactive sunburst charts
for war net breakdown visualization with enemy nation relationships in Politics & War Discord bot.
"""

import plotly.graph_objects as go
import plotly.io as pio
import os
import random
from typing import Dict, Any, List, Optional
from datetime import datetime
import hashlib


class WarNetBreakdownGraphGenerator:
    """Generates interactive war net breakdown graphs with enemy relationships using Plotly."""
    
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
    
    def generate_interactive_net_breakdown(self, nation_breakdown: Dict[int, Any], alliance_name: str, 
                                         resource_prices: dict, enemy_relationships: Dict[int, Dict[int, Dict[str, Any]]], 
                                         as_html: bool = False) -> str:
        """Generates an interactive sunburst chart for war net breakdown with enemy nation details."""

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
        enemy_damage_by_nation = {}  # Track enemy relationships per nation

        # Process each nation and their enemy relationships
        sorted_nations = sorted(nation_breakdown.values(), key=lambda x: x.get('net_damage', 0), reverse=True)
        for costs in sorted_nations:
            nation_name = costs['name']
            nation_id = costs.get('nation_id', 0)
            
            # Calculate net cost using the same logic as war_calc.py
            # Units cost calculation
            units_cost = (
                costs['soldiers_lost'] * 5 +
                costs['tanks_lost'] * (60 + 0.5 * resource_prices['buy'].get('steel', 0)) +
                costs['aircraft_lost'] * (4000 + 10 * resource_prices['buy'].get('aluminum', 0)) +
                costs['ships_lost'] * (50000 + 30 * resource_prices['buy'].get('steel', 0)) +
                costs['missiles_lost'] * (150000 + 100 * resource_prices['buy'].get('gasoline', 0) + 100 * resource_prices['buy'].get('munitions', 0) + 150 * resource_prices['buy'].get('aluminum', 0)) +
                costs['nukes_lost'] * (1750000 + 500 * resource_prices['buy'].get('uranium', 0) + 500 * resource_prices['buy'].get('gasoline', 0) + 1000 * resource_prices['buy'].get('aluminum', 0))
            )
            
            # Consumption cost
            consumption_cost = costs['consumption_cost']
            
            # Infrastructure cost
            infra_cost = costs['infra_destroyed_value']
            
            # Improvements cost
            improvements_cost = costs['improvements_cost']
            
            # Net loot calculation (loot_lost - loot_gained = net loss)
            loot_gained = costs.get('loot_received', 0) + costs.get('resource_loot_value', 0)
            loot_lost = costs.get('loot_lost', 0) + costs.get('resource_loot_lost_value', 0)
            net_loot = loot_lost - loot_gained  # Positive = net loss, Negative = net gain
            
            # Money destroyed is already included in gross cost calculation
            money_destroyed = costs.get('money_destroyed', 0)
            
            cost_components = {
                "Units": units_cost,
                "Consumption": consumption_cost,
                "Infrastructure": infra_cost,
                "Improvements": improvements_cost,
                "Net Loot": net_loot,
            }

            # Track enemy relationships for this nation
            if nation_id in enemy_relationships:
                enemy_damage_by_nation[nation_name] = {}
                for enemy_id, enemy_data in enemy_relationships[nation_id].items():
                    enemy_name = enemy_data.get('name', f'Enemy {enemy_id}')
                    enemy_net_damage = enemy_data.get('net_damage', 0)
                    if enemy_net_damage != 0:  # Only track significant relationships
                        enemy_damage_by_nation[nation_name][enemy_name] = enemy_net_damage

            for cost_type, value in cost_components.items():
                if value != 0:  # Allow negative values for Net Loot
                    cost_type_totals[cost_type] += value
                    nation_costs_by_type[cost_type].append({
                        'name': nation_name, 
                        'cost': value,
                        'nation_id': nation_id
                    })

        # Calculate total war cost (this represents the net damage)
        # Use the same logic as war_calc.py: gross cost minus gains
        total_war_cost = sum(cost_type_totals.values())
        
        values[0] = abs(total_war_cost)
        customdata[0] = f"Total War Net Cost: ${abs(total_war_cost):,.0f}"
        if total_war_cost < 0:
            customdata[0] += f"<br>(Net gain of ${abs(total_war_cost):,.0f})"
        elif total_war_cost > 0:
            customdata[0] += f"<br>(Net loss of ${total_war_cost:,.0f})"

        # Build the sunburst structure with enemy relationships
        for cost_type, total_cost in cost_type_totals.items():
            if total_cost != 0:  # Allow negative values for Net Loot
                cost_type_id = f"cost_type_{cost_type}"
                ids.append(cost_type_id)
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
                    nation_name = nation['name']
                    nation_id = nation['nation_id']
                    nation_cost = nation['cost']
                    
                    nation_id_str = f"{cost_type_id}_{nation_name}"
                    ids.append(nation_id_str)
                    labels.append(nation_name)
                    parents.append(cost_type_id)
                    values.append(abs(nation_cost))  # Use absolute value for sizing
                    
                    # Create detailed hover text with enemy relationships
                    nation_hover = f"<b>{nation_name}</b><br>{display_name} Cost: ${abs(nation_cost):,.0f}"
                    
                    # Add enemy relationships if available
                    if nation_name in enemy_damage_by_nation and enemy_damage_by_nation[nation_name]:
                        nation_hover += f"<br><br><b>Enemy Relationships:</b><br>"
                        # Sort enemies by damage amount
                        sorted_enemies = sorted(enemy_damage_by_nation[nation_name].items(), 
                                              key=lambda x: abs(x[1]), reverse=True)
                        for enemy_name, enemy_damage in sorted_enemies[:5]:  # Show top 5 enemies
                            if enemy_damage > 0:
                                nation_hover += f"vs {enemy_name}: <span style='color: #e74c3c'>${enemy_damage:,.0f} damage dealt</span><br>"
                            elif enemy_damage < 0:
                                nation_hover += f"vs {enemy_name}: <span style='color: #2ecc71'>${abs(enemy_damage):,.0f} damage received</span><br>"
                    
                    if cost_type == "Net Loot" and nation_cost < 0:
                        customdata.append(f"<b>{nation_name}</b><br>{cost_type} Gain: ${abs(nation_cost):,.0f}")
                    else:
                        customdata.append(nation_hover)

        # Create the sunburst figure
        fig = go.Figure(go.Sunburst(
            ids=ids,
            labels=labels,
            parents=parents,
            values=values,
            branchvalues="total",
            hovertemplate="<b>%{label}</b><br>Value: $%{value:,.0f}<br><br>%{customdata}<extra></extra>",
            customdata=customdata,
            maxdepth=3  # Allow deeper exploration to see enemy relationships
        ))

        fig.update_layout(
            title_text=f"Interactive War Net Breakdown for {alliance_name}",
            height=None,
            autosize=True,
            paper_bgcolor="rgba(48,51,57,255)",
            font={"color": "white"},
        )
        
        # Generate HTML content - inject full-height CSS so it fills the iframe
        raw_html = pio.to_html(fig, full_html=True, config={"responsive": True})
        html_content = raw_html.replace(
            '<head>',
            '<head><style>html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:#303339;} .plotly-graph-div{width:100%!important;height:100vh!important;}</style>'
        )
        
        # Save to file for web access in Wars directory
        timestamp = datetime.now().strftime("%m-%d-%Y")
        alliance_clean = "".join(c for c in alliance_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        alliance_clean = alliance_clean.replace(' ', '_')
        html_filename = f"warnetbd_{alliance_clean}_{timestamp}.html"
        
        # Create Wars directory if it doesn't exist
        wars_dir = os.path.join(self.web_dir, 'Wars')
        os.makedirs(wars_dir, exist_ok=True)
        
        # Write HTML file to Wars directory
        html_file_path = os.path.join(wars_dir, html_filename)
        with open(html_file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return html_content


# Create a singleton instance for easy import
war_net_breakdown_graph_generator = WarNetBreakdownGraphGenerator()