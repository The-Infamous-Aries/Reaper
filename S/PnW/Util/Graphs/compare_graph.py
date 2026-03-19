import json
import plotly.graph_objects as go
import plotly.express as px


def create_interactive_comparison_page(home_individual_stats, away_individual_stats):
    """Creates an interactive comparison page with a bar chart and toggles for each side."""

    stat_keys = {
        "Soldiers": "soldiers",
        "Tanks": "tanks",
        "Aircraft": "aircraft",
        "Ships": "ships",
        "Missiles": "missiles",
        "Nukes": "nukes",
    }

    def get_color(score, max_score, color_scale):
        if max_score == 0:
            return color_scale[0]
        ratio = score / max_score
        index = int(ratio * (len(color_scale) - 1))
        return color_scale[index]

    home_scores = [ind['stats'].get('total_score', 0) for ind in home_individual_stats]
    away_scores = [ind['stats'].get('total_score', 0) for ind in away_individual_stats]
    max_home_score = max(home_scores) if home_scores else 0
    max_away_score = max(away_scores) if away_scores else 0

    home_color_scale = px.colors.sequential.Blues
    away_color_scale = px.colors.sequential.Oranges

    fig = go.Figure()

    # --- Military Data Calculation ---
    military_traces = []
    military_x_labels = []
    military_x_positions = []
    mil_pos = 0

    home_military_totals = {f"{unit}_{t}": sum(ind['stats'].get('daily_military', {}).get(f"{t}_{stat_keys[unit]}", 0) for ind in home_individual_stats) for unit in stat_keys for t in ['current', 'daily']}
    away_military_totals = {f"{unit}_{t}": sum(ind['stats'].get('daily_military', {}).get(f"{t}_{stat_keys[unit]}", 0) for ind in away_individual_stats) for unit in stat_keys for t in ['current', 'daily']}

    for unit in stat_keys:
        military_x_labels.append(unit)
        military_x_positions.append(mil_pos + 2.5)
        for type in ['current', 'daily']:
            max_val = max(home_military_totals.get(f"{unit}_{type}", 0), away_military_totals.get(f"{unit}_{type}", 0), 1)
            
            for ind in home_individual_stats:
                val = ind['stats'].get('daily_military', {}).get(f"{type}_{stat_keys[unit]}", 0)
                percent_of_max = (val / max_val) * 100
                side_total = home_military_totals.get(f"{unit}_{type}", 1)
                percent_of_side = (val / side_total) * 100 if side_total > 0 else 0
                hovertemplate = (
                    f"<b>{unit.capitalize()} ({type.capitalize()})</b><br><br>"
                    "<b>Alliance:</b> %{data.name}<br>"
                    "<b>Count:</b> %{customdata[0]:,.0f}<br>"
                    "<b>Contribution:</b> %{customdata[1]:.1f}%<br>"
                    "<i>Click to see all contributions</i>"
                    "<extra></extra>"
                )
                military_traces.append(go.Bar(
                    x=[mil_pos + 1],
                    y=[percent_of_max],
                    name=ind['name'],
                    marker_color=get_color(ind['stats'].get('total_score', 0), max_home_score, home_color_scale),
                    legendgroup=ind['name'],
                    showlegend=False,
                    customdata=[[val, percent_of_side]],
                    hovertemplate=hovertemplate
                ))

            for ind in away_individual_stats:
                val = ind['stats'].get('daily_military', {}).get(f"{type}_{stat_keys[unit]}", 0)
                percent_of_max = (val / max_val) * 100
                side_total = away_military_totals.get(f"{unit}_{type}", 1)
                percent_of_side = (val / side_total) * 100 if side_total > 0 else 0
                hovertemplate = (
                    f"<b>{unit.capitalize()} ({type.capitalize()})</b><br><br>"
                    "<b>Alliance:</b> %{data.name}<br>"
                    "<b>Count:</b> %{customdata[0]:,.0f}<br>"
                    "<b>Contribution:</b> %{customdata[1]:.1f}%<br>"
                    "<i>Click to see all contributions</i>"
                    "<extra></extra>"
                )
                military_traces.append(go.Bar(
                    x=[mil_pos + 2],
                    y=[percent_of_max],
                    name=ind['name'],
                    marker_color=get_color(ind['stats'].get('total_score', 0), max_away_score, away_color_scale),
                    legendgroup=ind['name'],
                    showlegend=False,
                    customdata=[[val, percent_of_side]],
                    hovertemplate=hovertemplate
                ))
            mil_pos += 3
        mil_pos += 1

    # --- Nations (City Counts) Data Calculation ---
    nation_traces = []
    all_city_counts = set()
    for ind in home_individual_stats + away_individual_stats:
        all_city_counts.update(ind['stats'].get('city_counts', {}).keys())
    
    nation_x_labels = sorted(list(all_city_counts))
    nation_x_positions = [i * 3 + 1.5 for i in range(len(nation_x_labels))]

    home_city_totals = {count: sum(ind['stats'].get('city_counts', {}).get(count, 0) for ind in home_individual_stats) for count in nation_x_labels}
    away_city_totals = {count: sum(ind['stats'].get('city_counts', {}).get(count, 0) for ind in away_individual_stats) for count in nation_x_labels}

    # Create line traces for nations instead of bars
    home_line_data = []
    away_line_data = []
    
    for count in nation_x_labels:
        home_total = home_city_totals.get(count, 0)
        away_total = away_city_totals.get(count, 0)
        home_line_data.append(home_total)
        away_line_data.append(away_total)

    # Add line traces for home side
    nation_traces.append(go.Scatter(
        x=nation_x_labels,
        y=home_line_data,
        name='Home',
        line=dict(color='blue', width=3),
        mode='lines+markers',
        marker=dict(size=8),
        visible=False,
        customdata=[[home_total] for home_total in home_line_data],
        hovertemplate='<b>City Count: %{x}</b><br><b>Home Total:</b> %{customdata[0]:,.0f}<extra></extra>'
    ))

    # Add line traces for away side
    nation_traces.append(go.Scatter(
        x=nation_x_labels,
        y=away_line_data,
        name='Away',
        line=dict(color='orange', width=3),
        mode='lines+markers',
        marker=dict(size=8),
        visible=False,
        customdata=[[away_total] for away_total in away_line_data],
        hovertemplate='<b>City Count: %{x}</b><br><b>Away Total:</b> %{customdata[0]:,.0f}<extra></extra>'
    ))

    fig.add_traces(military_traces + nation_traces)

    military_annotations = []
    for i, unit in enumerate(stat_keys):
        military_annotations.append(dict(x=i*4 + 1.5, y=-0.08, xref='x', yref='paper', text="Current", showarrow=False, font=dict(size=10)))
        military_annotations.append(dict(x=i*4 + 2.5, y=-0.12, xref='x', yref='paper', text="Home", showarrow=False, font=dict(size=8)))
        military_annotations.append(dict(x=i*4 + 3.5, y=-0.12, xref='x', yref='paper', text="Away", showarrow=False, font=dict(size=8)))
        military_annotations.append(dict(x=i*4 + 4.5, y=-0.08, xref='x', yref='paper', text="Daily", showarrow=False, font=dict(size=10)))
        military_annotations.append(dict(x=i*4 + 5.5, y=-0.12, xref='x', yref='paper', text="Home", showarrow=False, font=dict(size=8)))
        military_annotations.append(dict(x=i*4 + 6.5, y=-0.12, xref='x', yref='paper', text="Away", showarrow=False, font=dict(size=8)))

    nations_annotations = []
    for i, count in enumerate(nation_x_labels):
        nations_annotations.append(dict(x=count, y=-0.08, xref='x', yref='paper', text=str(count), showarrow=False, font=dict(size=10)))

    fig.update_layout(
        barmode='stack',
        title='Comparison',
        xaxis=dict(
            tickvals=military_x_positions,
            ticktext=[l.capitalize() for l in military_x_labels],
            title=" ",
        ),
        yaxis=dict(
            title="Percentage of Max",
            range=[0, 101]
        ),
        legend_title="Alliances",
        hoverlabel=dict(align="left"),
        updatemenus=[
            dict(
                type="buttons",
                direction="right",
                x=0.5,
                xanchor="center",
                y=1.2,
                yanchor="top",
                showactive=True,
                buttons=[
                    dict(
                        label="Military",
                        method="update",
                        args=[
                            {"visible": [True] * len(military_traces) + [False] * len(nation_traces)},
                            {"xaxis.tickvals": military_x_positions, "xaxis.ticktext": [l.capitalize() for l in military_x_labels], "annotations": military_annotations}
                        ],
                        args2=[],
                        execute=True
                    ),
                    dict(
                        label="Nations",
                        method="update",
                        args=[
                            {"visible": [False] * len(military_traces) + [True] * len(nation_traces)},
                            {"xaxis.tickvals": nation_x_positions, "xaxis.ticktext": nation_x_labels, "annotations": nations_annotations}
                        ],
                        args2=[],
                        execute=True
                    ),
                ]
            )
        ],
        annotations=military_annotations
    )

    figure_json = fig.to_json()

    plot_div = fig.to_html(full_html=False, include_plotlyjs=False)

    sidebar_html = "<h2>Alliances</h2>"

    sidebar_html += '<h3><input type="checkbox" class="side-toggle" id="side-toggle-home" data-side="home" checked> <label for="side-toggle-home">Home</label></h3>'
    sidebar_html += '<div id="home-alliances">'
    for ind in home_individual_stats:
        sanitized_name = ind['name'].replace(" ", "-").replace("'", "")
        score = ind['stats'].get('total_score', 0)
        nations = ind['stats'].get('total_nations', 0)
        alliance_name = ind['name']
        sidebar_html += f'<div><input type="checkbox" class="alliance-toggle home-alliance" id="alliance-toggle-{sanitized_name}" data-alliance-name="{alliance_name}" data-side="home" checked> <label for="alliance-toggle-{sanitized_name}">{alliance_name}</label><br><small>Score: {score:,.0f}, Nations: {nations}</small></div>'
    sidebar_html += '</div>'

    sidebar_html += '<h3><input type="checkbox" class="side-toggle" id="side-toggle-away" data-side="away" checked> <label for="side-toggle-away">Away</label></h3>'
    sidebar_html += '<div id="away-alliances">'
    for ind in away_individual_stats:
        sanitized_name = ind['name'].replace(" ", "-").replace("'", "")
        score = ind['stats'].get('total_score', 0)
        nations = ind['stats'].get('total_nations', 0)
        alliance_name = ind['name']
        sidebar_html += f'<div><input type="checkbox" class="alliance-toggle away-alliance" id="alliance-toggle-{sanitized_name}" data-alliance-name="{alliance_name}" data-side="away" checked> <label for="alliance-toggle-{sanitized_name}">{alliance_name}</label><br><small>Score: {score:,.0f}, Nations: {nations}</small></div>'
    sidebar_html += '</div>'


    js_code = f"""<script>
    document.addEventListener('DOMContentLoaded', function() {{
        const plotDiv = document.getElementById('plot');
        const initialFigure = {figure_json};
        const military_traces_indices = Array.from({{length: {len(military_traces)}}}, (_, i) => i);
        const nation_traces_indices = Array.from({{length: {len(nation_traces)}}}, (_, i) => i + {len(military_traces)};

        let current_view = 'military';
        let active_hover_boxes = new Map(); // Store active hover boxes

        function update_plot() {{
            const alliance_visibility = {{}};
            document.querySelectorAll('.alliance-toggle').forEach(toggle => {{
                alliance_visibility[toggle.dataset.allianceName] = toggle.checked;
            }});

            const traces_to_show_indices = current_view === 'military' ? military_traces_indices : nation_traces_indices;

            const visibility_update = initialFigure.data.map((trace, index) => {{
                if (traces_to_show_indices.includes(index)) {{
                    if (current_view === 'military') {{
                        return alliance_visibility[trace.name];
                    }} else {{
                        // For nations view, show lines based on side toggle
                        const side = trace.name === 'Home' ? 'home' : 'away';
                        const side_toggle = document.getElementById(`side-toggle-${{side}}`);
                        return side_toggle ? side_toggle.checked : true;
                    }}
                }} else {{
                    return false;
                }}
            }});

            Plotly.restyle(plotDiv, {{ 'visible': visibility_update }});
        }}

        // Handle military bar clicks for persistent hover
        plotDiv.on('plotly_click', function(data) {{
            if (current_view === 'military') {{
                const point = data.points[0];
                const trace_name = point.data.name;
                const x_value = point.x;
                
                // Create unique key for this hover box
                const key = `${{trace_name}}_${{x_value}}`;
                
                if (active_hover_boxes.has(key)) {{
                    // Remove existing hover box
                    const existing_box = active_hover_boxes.get(key);
                    existing_box.remove();
                    active_hover_boxes.delete(key);
                }} else {{
                    // Create persistent hover box with all alliance contributions
                    const unit_type = point.data.hovertemplate.match(/<b>(.+?) \(/)[1];
                    const current_type = point.data.hovertemplate.match(/\((.+?)\)/)[1];
                    
                    // Get all alliances for this unit and type
                    const home_alliances = {json.dumps(home_individual_stats)};
                    const away_alliances = {json.dumps(away_individual_stats)};
                    
                    let breakdown_html = `<strong>${{unit_type}} (${{current_type}})</strong><br><br>`;
                    breakdown_html += `<strong>Home Side:</strong><br>`;
                    
                    home_alliances.forEach(alliance => {{
                        if (alliance.stats.daily_military && alliance.stats.daily_military[`${{current_type.toLowerCase()}}_${stat_keys[unit_type.toLowerCase()]}]) {{
                            const count = alliance.stats.daily_military[`${{current_type.toLowerCase()}}_${stat_keys[unit_type.toLowerCase()]}`];
                            breakdown_html += `${{alliance.name}}: ${{count:,.0f}}<br>`;
                        }}
                    }});
                    
                    breakdown_html += `<br><strong>Away Side:</strong><br>`;
                    away_alliances.forEach(alliance => {{
                        if (alliance.stats.daily_military && alliance.stats.daily_military[`${{current_type.toLowerCase()}}_${stat_keys[unit_type.toLowerCase()]}]) {{
                            const count = alliance.stats.daily_military[`${{current_type.toLowerCase()}}_${stat_keys[unit_type.toLowerCase()]}`];
                            breakdown_html += `${{alliance.name}}: ${{count:,.0f}}<br>`;
                        }}
                    }});
                    
                    const hover_box = document.createElement('div');
                    hover_box.className = 'persistent-hover-box';
                    hover_box.innerHTML = `
                        <div style="background: white; border: 1px solid #ccc; padding: 10px; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.2); position: absolute; z-index: 1000; max-width: 300px;">
                            ${{breakdown_html}}
                            <button onclick="this.parentElement.parentElement.remove(); active_hover_boxes.delete('${{key}}');" style="float: right; background: #f44336; color: white; border: none; padding: 2px 6px; border-radius: 3px; cursor: pointer;">×</button>
                            <div style="clear: both;"></div>
                        </div>
                    `;
                    
                    // Position near click point
                    const plot_rect = plotDiv.getBoundingClientRect();
                    hover_box.style.left = (data.event.clientX - plot_rect.left + 10) + 'px';
                    hover_box.style.top = (data.event.clientY - plot_rect.top - 10) + 'px';
                    
                    plotDiv.appendChild(hover_box);
                    active_hover_boxes.set(key, hover_box);
                }}
            }}
        }});

        // Handle nations line clicks for persistent hover
        plotDiv.on('plotly_click', function(data) {{
            if (current_view === 'nations') {{
                const point = data.points[0];
                const side = point.data.name;
                const city_count = point.x;
                const total = point.customdata[0];
                
                const key = `${{side}}_${{city_count}}`;
                
                if (active_hover_boxes.has(key)) {{
                    const existing_box = active_hover_boxes.get(key);
                    existing_box.remove();
                    active_hover_boxes.delete(key);
                }} else {{
                    // Get breakdown for this side and city count
                    const side_data = side === 'Home' ? {json.dumps(home_individual_stats)} : {json.dumps(away_individual_stats)};
                    let breakdown_html = `<strong>${{side}} Side - City Count: ${{city_count}}</strong><br><strong>Total: ${{total:,.0f}}</strong><br><br>`;
                    
                    side_data.forEach(alliance => {{
                        if (alliance.stats.city_counts && alliance.stats.city_counts[city_count]) {{
                            breakdown_html += `<strong>${{alliance.name}}:</strong> ${{alliance.stats.city_counts[city_count]:,.0f}}<br>`;
                        }}
                    }});
                    
                    const hover_box = document.createElement('div');
                    hover_box.className = 'persistent-hover-box';
                    hover_box.innerHTML = `
                        <div style="background: white; border: 1px solid #ccc; padding: 10px; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.2); position: absolute; z-index: 1000;">
                            ${{breakdown_html}}
                            <button onclick="this.parentElement.parentElement.remove(); active_hover_boxes.delete('${{key}}');" style="float: right; background: #f44336; color: white; border: none; padding: 2px 6px; border-radius: 3px; cursor: pointer;">×</button>
                        </div>
                    `;
                    
                    const plot_rect = plotDiv.getBoundingClientRect();
                    hover_box.style.left = (data.event.clientX - plot_rect.left + 10) + 'px';
                    hover_box.style.top = (data.event.clientY - plot_rect.top - 10) + 'px';
                    
                    plotDiv.appendChild(hover_box);
                    active_hover_boxes.set(key, hover_box);
                }}
            }}
        }});

        document.querySelectorAll('.alliance-toggle').forEach(toggle => {{
            toggle.addEventListener('change', update_plot);
        }});

        document.querySelectorAll('.side-toggle').forEach(toggle => {{
            toggle.addEventListener('change', function() {{
                const side = this.dataset.side;
                const is_checked = this.checked;
                document.querySelectorAll(`.alliance-toggle[data-side='${{side}}']`).forEach(allianceToggle => {{
                    allianceToggle.checked = is_checked;
                }});
                update_plot();
            }});
        }});
        
        // Handle view switching buttons
        const updatemenu_buttons = document.querySelectorAll('button[data-view]');
        updatemenu_buttons.forEach(btn => {{
            btn.addEventListener('click', function() {{
                current_view = this.getAttribute('data-view');
                update_plot();
                
                // Clear active hover boxes when switching views
                active_hover_boxes.forEach(box => box.remove());
                active_hover_boxes.clear();
                
                // Update layout based on view
                if (current_view === 'military') {{
                    Plotly.relayout(plotDiv, {{ 
                        'xaxis.tickvals': {json.dumps(military_x_positions)},
                        'xaxis.ticktext': {json.dumps([l.capitalize() for l in military_x_labels])},
                        'annotations': {json.dumps(military_annotations)}
                    }});
                }} else {{
                    Plotly.relayout(plotDiv, {{
                        'xaxis.tickvals': {json.dumps(nation_x_positions)},
                        'xaxis.ticktext': {json.dumps(nation_x_labels)},
                        'annotations': {json.dumps(nations_annotations)}
                    }});
                }}
            }});
        }});
        
        Plotly.newPlot(plotDiv, initialFigure.data, initialFigure.layout);
        update_plot(); // Initial plot draw
    }});
    </script>"""

    final_html = f'''
    <html>
        <head>
            <meta charset="utf-8" />
            <title>Interactive Alliance Comparison</title>
            <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin: 0; background-color: #f8f9fa; }}
                #container {{ display: flex; flex-direction: row; height: 100vh; }}
                #sidebar {{ width: 25%; height: 100%; overflow-y: auto; background-color: #fff; border-right: 1px solid #dee2e6; box-shadow: 0 0 10px rgba(0,0,0,0.05); padding: 20px; }}
                #plot {{ width: 75%; height: 100%; position: relative; }}
                h2, h3 {{ color: #343a40; }}
                h3 {{ border-bottom: 1px solid #eee; padding-bottom: 5px; }}
                input[type="checkbox"] {{ margin-right: 8px; }}
                .plotly .hovertext {{ text-align: left !important; }}
                #home-alliances div, #away-alliances div {{ margin-left: 20px; margin-bottom: 10px; }}
                .persistent-hover-box {{ position: absolute; pointer-events: none; }}
                .persistent-hover-box button {{ pointer-events: auto; }}
                .updatemenu-button {{ cursor: pointer; }}
            </style>
        </head>
        <body>
            <div id="container">
                <div id="sidebar">
                    {sidebar_html}
                </div>
                <div id="plot">
                    {plot_div}
                </div>
            </div>
            {js_code}
        </body>
    </html>
    '''
    return final_html