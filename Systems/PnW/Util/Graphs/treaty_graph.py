import plotly.graph_objects as go
import networkx as nx
import math
import json
from typing import List, Dict, Any
from collections import defaultdict

COLOR_HEX_MAP = {
    "white": "#FFFFFF", "grey": "#808080", "black": "#000000",
    "gold": "#FFD700", "pink": "#FFC0CB", "brown": "#A52A2A",
    "mint": "#98FF98", "green": "#00FF00", "aqua": "#00FFFF",
    "lavender": "#E6E6FA", "lime": "#00FF00", "maroon": "#800000",
    "olive": "#808000", "yellow": "#FFFF00", "turquoise": "#40E0D0",
    "red": "#FF0000", "purple": "#800080", "orange": "#FFA500",
    "blue": "#0000FF", "beige": "#DDDDDD"
}

import os
from datetime import datetime

class TreatyGraph:
    def __init__(self, web_dir=None):
        # Allow custom web directory via parameter or environment variable
        if web_dir:
            self.web_dir = web_dir
        else:
            # Check environment variable first, then fall back to relative path
            env_web_dir = os.environ.get('TREATY_GRAPH_WEB_DIR')
            if env_web_dir:
                self.web_dir = env_web_dir
            else:
                # Default relative path for portability, goes up 4 levels to the project root
                self.web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..', 'web', 'Universes')
        
        # Ensure the directory exists
        os.makedirs(self.web_dir, exist_ok=True)

    def _get_alliance_color(self, color_name: str) -> str:
        """
        Get hex color for alliance color name, with fallback for any color.
        """
        if not color_name:
            return '#888888'
        
        # First try the predefined color map
        if color_name.lower() in COLOR_HEX_MAP:
            return COLOR_HEX_MAP[color_name.lower()]
        
        # If it's already a hex color (starts with #), validate and return it
        if color_name.startswith('#'):
            try:
                # Validate hex color format
                hex_color = color_name.lstrip('#')
                if len(hex_color) == 3:
                    # Convert shorthand hex (#RGB) to full hex (#RRGGBB)
                    hex_color = ''.join([c*2 for c in hex_color])
                elif len(hex_color) != 6:
                    raise ValueError("Invalid hex color length")
                
                # Test if it's valid hex
                int(hex_color, 16)
                return f'#{hex_color}'
            except (ValueError, IndexError):
                return '#888888'
        
        # For any other color name, generate a consistent hash-based color
        # This ensures the same color name always gets the same color
        import hashlib
        color_hash = hashlib.md5(color_name.lower().encode()).hexdigest()
        return f'#{color_hash[:6]}'

    def _get_contrast_color(self, hex_color: str) -> str:
        """
        Returns black or white text color based on the brightness of the background color.
        Uses the WCAG luminance formula for optimal contrast.
        """
        # Remove # if present
        hex_color = hex_color.lstrip('#')
        
        # Convert to RGB
        try:
            r = int(hex_color[0:2], 16) / 255.0
            g = int(hex_color[2:4], 16) / 255.0
            b = int(hex_color[4:6], 16) / 255.0
        except (ValueError, IndexError):
            # Fallback for invalid hex colors - return white for dark gray fallback
            return '#ffffff'
        
        # Calculate relative luminance using WCAG formula
        def adjust_channel(channel):
            if channel <= 0.03928:
                return channel / 12.92
            else:
                return pow((channel + 0.055) / 1.055, 2.4)
        
        r_adj = adjust_channel(r)
        g_adj = adjust_channel(g)
        b_adj = adjust_channel(b)
        
        luminance = 0.2126 * r_adj + 0.7152 * g_adj + 0.0722 * b_adj
        
        # Return white for dark backgrounds, black for light backgrounds
        # Using WCAG AA standard threshold for optimal readability
        # This ensures 4.5:1 contrast ratio for normal text
        return '#ffffff' if luminance < 0.45 else '#000000'

    def _get_treaty_width(self, treaty_type: str) -> int:
        """
        Returns the line width for a treaty type based on its significance.
        """
        treaty_styles = {
            'Protectorate': 4,
            'Extension': 4,
            'MDoAP': 3,
            'MDP': 3,
            'ODoAP': 2,
            'ODP': 2,
            'PIAT': 1,
            'NAP': 1,
        }
        return treaty_styles.get(treaty_type, 1)

    def _create_enhanced_layout(self, G: nx.Graph, blocs: Dict[str, List[List[int]]] = None) -> Dict[int, tuple]:
        """
        Creates an enhanced 3D layout with proper bloc spacing while maintaining connections.
        """
        # Build bloc mapping
        alliance_bloc_map = {}
        bloc_centers = {}
        if blocs and 'combined' in blocs:
            for bloc_idx, bloc in enumerate(blocs['combined']):
                # Calculate bloc center based on alliance scores
                bloc_score = sum(G.nodes[alliance_id].get('score', 0) for alliance_id in bloc if G.has_node(alliance_id))
                bloc_centers[bloc_idx] = bloc_score
                for alliance_id in bloc:
                    alliance_bloc_map[alliance_id] = bloc_idx
        
        # Create initial layout
        pos = nx.spring_layout(G, dim=3, seed=42, k=3.0, iterations=100)
        
        # Apply bloc-based positioning
        if bloc_centers:
            # Sort blocs by total score for hierarchical positioning
            sorted_blocs = sorted(bloc_centers.items(), key=lambda x: x[1], reverse=True)
            
            # Position blocs in a circle/spiral pattern with large spacing
            bloc_positions = {}
            num_blocs = len(sorted_blocs)
            for i, (bloc_idx, _) in enumerate(sorted_blocs):
                # Use spiral positioning for better 3D distribution
                angle = (2 * math.pi * i) / num_blocs
                height = (i - num_blocs/2) * 15  # Vertical spacing
                radius = 50 + (i * 10)  # Increasing radius for larger blocs
                
                bloc_positions[bloc_idx] = (
                    radius * math.cos(angle),
                    radius * math.sin(angle),
                    height
                )
            
            # Position alliances within their blocs
            final_positions = {}
            for node in G.nodes():
                node_id = node
                if node_id in alliance_bloc_map:
                    bloc_idx = alliance_bloc_map[node_id]
                    bloc_center = bloc_positions[bloc_idx]
                    
                    # Position alliances within bloc in small cluster
                    score = G.nodes[node_id].get('score', 1)
                    local_angle = hash(str(node_id)) % 360  # Consistent random angle
                    local_radius = 5 + math.log10(max(1, score)) * 2
                    local_height = (hash(str(node_id)) % 10 - 5) * 0.5
                    
                    final_positions[node_id] = (
                        bloc_center[0] + local_radius * math.cos(math.radians(local_angle)),
                        bloc_center[1] + local_radius * math.sin(math.radians(local_angle)),
                        bloc_center[2] + local_height
                    )
                else:
                    # Unaligned alliances - position them between blocs
                    unaligned_angle = hash(str(node_id)) % 360
                    unaligned_radius = 80 + (hash(str(node_id)) % 20)
                    unaligned_height = (hash(str(node_id)) % 20 - 10) * 3
                    
                    final_positions[node_id] = (
                        unaligned_radius * math.cos(math.radians(unaligned_angle)),
                        unaligned_radius * math.sin(math.radians(unaligned_angle)),
                        unaligned_height
                    )
            
            return final_positions
        
        return pos

    def find_blocs(self, treaties: List[Dict[str, Any]]) -> Dict[str, List[List[int]]]:
        """
        Finds blocs where 3+ alliances all share MDP/MDoAP/ODP/ODoAP treaties with each other.
        Returns a dictionary with bloc types as keys and lists of alliance ID lists as values.
        """
        # Filter treaties to only include the 4 main treaty types for bloc formation
        bloc_treaty_types = {'MDP', 'MDoAP', 'ODP', 'ODoAP'}
        
        # Create adjacency dictionary for alliances
        alliance_treaties = defaultdict(lambda: defaultdict(set))
        alliance_scores = {}
        
        for treaty in treaties:
            a1_id = treaty.get('alliance1_id')
            a2_id = treaty.get('alliance2_id')
            treaty_type = treaty.get('treaty_type')
            
            if a1_id and a2_id and treaty_type in bloc_treaty_types:
                alliance_treaties[a1_id][treaty_type].add(a2_id)
                alliance_treaties[a2_id][treaty_type].add(a1_id)
                
                # Store alliance scores
                alliance1_data = treaty.get('alliance1') or {}
                alliance2_data = treaty.get('alliance2') or {}
                alliance_scores[a1_id] = alliance1_data.get('score', 0)
                alliance_scores[a2_id] = alliance2_data.get('score', 0)
        
        # Find blocs by treaty type first
        treaty_type_blocs = {
            'MDP': [],
            'MDoAP': [],
            'ODP': [],
            'ODoAP': []
        }
        
        # Find cliques for each treaty type
        for treaty_type in bloc_treaty_types:
            # Create graph for this treaty type
            G = nx.Graph()
            for alliance_id, treaties in alliance_treaties.items():
                if treaty_type in treaties:
                    G.add_node(alliance_id)
                    for other_alliance in treaties[treaty_type]:
                        if other_alliance in alliance_treaties and treaty_type in alliance_treaties[other_alliance]:
                            # Both alliances have this treaty type with each other
                            if alliance_id in alliance_treaties[other_alliance][treaty_type]:
                                G.add_edge(alliance_id, other_alliance)
            
            # Find cliques of size 3 or more
            cliques = list(nx.find_cliques(G))
            for clique in cliques:
                if len(clique) >= 3:
                    # Sort by score (descending) for consistent ordering
                    sorted_clique = sorted(clique, key=lambda x: alliance_scores.get(x, 0), reverse=True)
                    treaty_type_blocs[treaty_type].append(sorted_clique)
        
        # Find combined blocs (any of the 4 treaty types)
        # Create graph where edges exist if alliances share ANY of the 4 treaty types
        combined_G = nx.Graph()
        for alliance_id in alliance_treaties:
            combined_G.add_node(alliance_id)
            
        for a1_id in alliance_treaties:
            for a2_id in alliance_treaties:
                if a1_id == a2_id:  # Skip self-loops
                    continue
                    
                # Check if they share ANY of the 4 treaty types
                shared_treaties = False
                for treaty_type in bloc_treaty_types:
                    if (treaty_type in alliance_treaties[a1_id] and 
                        a2_id in alliance_treaties[a1_id][treaty_type] and
                        treaty_type in alliance_treaties[a2_id] and 
                        a1_id in alliance_treaties[a2_id][treaty_type]):
                        shared_treaties = True
                        break
                
                if shared_treaties:
                    combined_G.add_edge(a1_id, a2_id)
        
        # Find cliques in the combined graph
        combined_blocs = []
        combined_cliques = list(nx.find_cliques(combined_G))
        for clique in combined_cliques:
            if len(clique) >= 3:
                # Sort by score (descending) for consistent ordering
                sorted_clique = sorted(clique, key=lambda x: alliance_scores.get(x, 0), reverse=True)
                combined_blocs.append(sorted_clique)
        
        # Add protectorates and extensions to blocs
        protectorate_treaties = {'Protectorate', 'Extension'}
        protectorate_mapping = defaultdict(list)
        
        # Map protectorates to their protectors and ensure all alliance scores are captured
        print("DEBUG: Starting protectorate mapping")
        for treaty in treaties:
            if not isinstance(treaty, dict):
                continue
            a1_id = treaty.get('alliance1_id')
            a2_id = treaty.get('alliance2_id')
            
            if a1_id and a2_id:
                # Store alliance scores for all alliances (including protectorates)
                alliance1_data = treaty.get('alliance1') or {}
                alliance2_data = treaty.get('alliance2') or {}
                alliance_scores[a1_id] = alliance1_data.get('score', 0)
                alliance_scores[a2_id] = alliance2_data.get('score', 0)

        for treaty in treaties:
            if not isinstance(treaty, dict):
                continue
            a1_id = treaty.get('alliance1_id')
            a2_id = treaty.get('alliance2_id')
            treaty_type = treaty.get('treaty_type')
            
            if a1_id and a2_id and treaty_type in protectorate_treaties:
                print(f"DEBUG: Found protectorate treaty: {a1_id} <-> {a2_id}")
                # Determine which is protector and which is protectorate based on score
                a1_score = alliance_scores.get(a1_id, 0)
                a2_score = alliance_scores.get(a2_id, 0)
                
                if a1_score >= a2_score:
                    # a1 is protector, a2 is protectorate
                    protectorate_mapping[a2_id].append((a1_id, a1_score))
                    print(f"DEBUG: Mapped protectorate {a2_id} -> protector {a1_id}")
                else:
                    # a2 is protector, a1 is protectorate
                    protectorate_mapping[a1_id].append((a2_id, a2_score))
                    print(f"DEBUG: Mapped protectorate {a1_id} -> protector {a2_id}")
        
        # Add protectorates to blocs based on biggest alliance they share protectorate with
        final_blocs = {
            'by_treaty_type': treaty_type_blocs,
            'combined': combined_blocs,
            'with_protectorates': {}
        }
        
        # Add protectorates to combined blocs
        for bloc in combined_blocs:
            bloc_set = set(bloc)
            enhanced_bloc = list(bloc)  # Start with original bloc
            
            # Find protectorates that should be added to this bloc
            for protectorate_id, protectors in protectorate_mapping.items():
                if protectorate_id in bloc_set:  # Skip if protectorate is already in bloc
                    continue
                    
                # Find the biggest protector that's in this bloc
                best_protector = None
                best_score = 0
                for protector_id, protector_score in protectors:
                    if protector_id in bloc_set and protector_score > best_score:
                        best_protector = protector_id
                        best_score = protector_score
                
                if best_protector:
                    enhanced_bloc.append(protectorate_id)
            
            # Sort enhanced bloc by score
            enhanced_bloc = sorted(enhanced_bloc, key=lambda x: alliance_scores.get(x, 0), reverse=True)
            # Use a sorted tuple as key for consistent ordering
            bloc_key = tuple(sorted(bloc))
            final_blocs['with_protectorates'][bloc_key] = enhanced_bloc
        
        return final_blocs

    def build_treaty_graph(self, treaties: List[Dict[str, Any]]) -> nx.Graph:
        """
        Builds a networkx graph from the list of treaties.
        Edges are styled based on treaty type to show their significance.
        """
        G = nx.Graph()

        # Define treaty hierarchy for edge styling (width)
        treaty_styles = {
            'Protectorate': {'width': 4},  # Thickest
            'Extension': {'width': 4},
            'MDoAP': {'width': 3},
            'MDP': {'width': 3},
            'ODoAP': {'width': 2},
            'ODP': {'width': 2},
        }
        # A broader set of treaties for visualization
        visualized_treaty_types = set(treaty_styles.keys())

        for treaty in treaties:
            a1_id = treaty.get('alliance1_id')
            a2_id = treaty.get('alliance2_id')
            
            if a1_id and a2_id:
                # Add nodes for all alliances
                alliance1_data = treaty.get('alliance1') or {}
                alliance2_data = treaty.get('alliance2') or {}
                a1_name = alliance1_data.get('name', str(a1_id))
                a2_name = alliance2_data.get('name', str(a2_id))
                a1_score = alliance1_data.get('score', 0)
                a2_score = alliance2_data.get('score', 0)
                a1_color = self._get_alliance_color(alliance1_data.get('color') or '')
                a2_color = self._get_alliance_color(alliance2_data.get('color') or '')
                a1_flag = alliance1_data.get('flag')
                a2_flag = alliance2_data.get('flag')

                if not G.has_node(a1_id):
                    G.add_node(a1_id, name=a1_name, score=a1_score, color=a1_color, flag=a1_flag)
                if not G.has_node(a2_id):
                    G.add_node(a2_id, name=a2_name, score=a2_score, color=a2_color, flag=a2_flag)

                # Add styled edges for visualized treaties
                treaty_type = treaty.get('treaty_type')
                if treaty_type in visualized_treaty_types:
                    style = treaty_styles[treaty_type]
                    # Use alliance1's color for the edge
                    edge_color = a1_color
                    
                    # If an edge already exists, update it only if the new treaty is of higher importance (thicker width)
                    if G.has_edge(a1_id, a2_id):
                        if style['width'] > G[a1_id][a2_id].get('width', 0):
                            G[a1_id][a2_id].update(color=edge_color, width=style['width'])
                    else:
                        G.add_edge(a1_id, a2_id, color=edge_color, width=style['width'])
        nodes_to_remove = [node for node, data in G.nodes(data=True) if data.get('score', 0) == 0]
        G.remove_nodes_from(nodes_to_remove)
        return G

    def create_focused_map(self, focused_data: Dict[str, Any]) -> str:
        """
        Creates a focused 2D interactive treaty map centered on one alliance.
        Layer 0 = center (largest), Layer 1 = direct partners, Layer 2 = partners-of-partners (smaller, for lines only).
        Uses alliance flags as node images via Plotly scatter with image overlays.
        """
        center_id = focused_data['center_id']
        layer1 = focused_data['layer1']
        layer2 = focused_data['layer2']
        treaties = focused_data['treaties']
        alliance_info = focused_data['alliance_info']

        TREATY_TYPES = {'Protectorate', 'Extension', 'MDP', 'MDoAP', 'ODP', 'ODoAP'}
        TREATY_COLORS = {
            'MDoAP': '#e74c3c', 'MDP': '#e67e22',
            'ODoAP': '#3498db', 'ODP': '#2ecc71',
            'Protectorate': '#9b59b6', 'Extension': '#9b59b6',
        }
        TREATY_WIDTHS = {'MDoAP': 4, 'MDP': 4, 'ODoAP': 2, 'ODP': 2, 'Protectorate': 3, 'Extension': 3}

        # Build set of all nodes to show
        all_node_ids = {center_id} | layer1 | layer2

        # Build adjacency from treaties (only between nodes we're showing)
        edges: Dict[tuple, Dict] = {}  # (a, b) -> {type, color, width}
        for t in treaties:
            tt = t.get('treaty_type')
            if tt not in TREATY_TYPES:
                continue
            a1 = t.get('alliance1_id')
            a2 = t.get('alliance2_id')
            if not a1 or not a2:
                continue
            a1, a2 = int(a1), int(a2)
            if a1 not in all_node_ids or a2 not in all_node_ids:
                continue
            key = (min(a1, a2), max(a1, a2))
            w = TREATY_WIDTHS.get(tt, 1)
            if key not in edges or w > edges[key]['width']:
                edges[key] = {'type': tt, 'color': TREATY_COLORS.get(tt, '#aaaaaa'), 'width': w}

        # Build networkx graph for layout
        G = nx.Graph()
        for nid in all_node_ids:
            G.add_node(nid)
        for (a, b) in edges:
            G.add_edge(a, b)

        # Force-directed layout, seed for reproducibility
        pos = nx.spring_layout(G, seed=42, k=2.5, iterations=120)

        # Node sizing by layer
        def node_size(nid):
            if nid == center_id: return 40
            if nid in layer1: return 28
            return 16

        def node_opacity(nid):
            if nid in layer2: return 0.55
            return 1.0

        # Build edge traces grouped by treaty type for legend
        edge_traces = []
        legend_added = set()
        for (a, b), edata in edges.items():
            x0, y0 = pos[a]
            x1, y1 = pos[b]
            tt = edata['type']
            show_legend = tt not in legend_added
            if show_legend:
                legend_added.add(tt)
            edge_traces.append(go.Scatter(
                x=[x0, x1, None], y=[y0, y1, None],
                mode='lines',
                line=dict(color=edata['color'], width=edata['width']),
                hoverinfo='none',
                name=tt,
                legendgroup=tt,
                showlegend=show_legend,
            ))

        # Build node traces — one per layer for sizing
        def _node_hover(nid):
            info = alliance_info.get(nid, {})
            name = info.get('name', str(nid))
            score = info.get('score', 0)
            layer = 'Center' if nid == center_id else ('Partner' if nid in layer1 else 'Extended')
            partner_treaties = []
            for t in treaties:
                a1, a2 = t.get('alliance1_id'), t.get('alliance2_id')
                if not a1 or not a2: continue
                a1, a2 = int(a1), int(a2)
                if a1 == nid or a2 == nid:
                    other = a2 if a1 == nid else a1
                    other_name = alliance_info.get(other, {}).get('name', str(other))
                    tt = t.get('treaty_type', '')
                    if tt in TREATY_TYPES:
                        partner_treaties.append(f"{other_name} ({tt})")
            treaty_lines = '<br>'.join(sorted(partner_treaties)[:20])
            return f"<b>{name}</b><br>Score: {score:,.0f}<br>Layer: {layer}<br><br>{treaty_lines}"

        for layer_ids, size, opacity, layer_name in [
            ({center_id}, 40, 1.0, 'Center'),
            (layer1, 28, 1.0, 'Partners'),
            (layer2, 16, 0.55, 'Extended'),
        ]:
            nodes_in_layer = [nid for nid in layer_ids if nid in pos]
            if not nodes_in_layer:
                continue
            xs = [pos[n][0] for n in nodes_in_layer]
            ys = [pos[n][1] for n in nodes_in_layer]
            colors = [self._get_alliance_color(alliance_info.get(n, {}).get('color', '')) for n in nodes_in_layer]
            names = [alliance_info.get(n, {}).get('name', str(n)) for n in nodes_in_layer]
            hovers = [_node_hover(n) for n in nodes_in_layer]
            flags = [alliance_info.get(n, {}).get('flag', '') for n in nodes_in_layer]
            edge_traces.append(go.Scatter(
                x=xs, y=ys,
                mode='markers+text',
                marker=dict(size=size, color=colors, opacity=opacity,
                            line=dict(width=2, color='#ffffff')),
                text=names,
                textposition='top center',
                textfont=dict(size=9 if layer_name == 'Extended' else 11, color='#ffffff'),
                hovertext=hovers,
                hoverinfo='text',
                name=layer_name,
                customdata=[[n, alliance_info.get(n, {}).get('flag', '')] for n in nodes_in_layer],
            ))

        # Build flag images for Plotly layout.images (layer0 + layer1 only)
        images = []
        for nid in ([center_id] + list(layer1)):
            if nid not in pos:
                continue
            flag = alliance_info.get(nid, {}).get('flag', '')
            if not flag:
                continue
            x, y = pos[nid]
            sz = 0.06 if nid == center_id else 0.04
            images.append(dict(
                source=flag,
                xref='x', yref='y',
                x=x, y=y,
                sizex=sz, sizey=sz,
                xanchor='center', yanchor='middle',
                layer='above',
            ))

        center_name = alliance_info.get(center_id, {}).get('name', str(center_id))

        # Build node metadata for JS flag overlay (flags via JS, not Plotly images which don't scale)
        node_meta = {}
        for layer_ids, layer_num in [({center_id}, 0), (layer1, 1), (layer2, 2)]:
            for nid in layer_ids:
                if nid not in pos:
                    continue
                info = alliance_info.get(nid, {})
                node_meta[str(nid)] = {
                    'flag': info.get('flag', ''),
                    'name': info.get('name', str(nid)),
                    'layer': layer_num,
                }

        fig = go.Figure(data=edge_traces)
        fig.update_layout(
            title=f'Treaty Universe — {center_name}',
            showlegend=True,
            legend=dict(x=1.01, y=1, bgcolor='rgba(0,0,0,0.5)', font=dict(color='white')),
            hovermode='closest',
            paper_bgcolor='#0f0f0f',
            plot_bgcolor='#0f0f0f',
            font=dict(color='white'),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            margin=dict(l=10, r=150, t=50, b=10),
            autosize=True,
        )

        base_html = fig.to_html(full_html=True, config={'responsive': True, 'scrollZoom': True})

        flag_data_json = json.dumps(node_meta)
        pos_json = json.dumps({str(k): [float(v[0]), float(v[1])] for k, v in pos.items()})

        inject = f"""
<style>
html, body {{ margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; background: #0f0f0f; }}
.plotly-graph-div {{ width: 100% !important; height: 100vh !important; }}
.flag-overlay {{ position: absolute; pointer-events: none; border-radius: 50%; border: 2px solid rgba(255,255,255,0.7); overflow: hidden; transform: translate(-50%, -50%); box-shadow: 0 0 6px rgba(0,0,0,0.8); }}
.flag-overlay img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
#flag-container {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; overflow: hidden; }}
</style>
<div id="flag-container"></div>
<script>
(function() {{
  const flagData = {flag_data_json};
  const posData = {pos_json};
  const FLAG_SIZES = [34, 22, 0];

  function placeFlagOverlays() {{
    const gd = document.querySelector('.plotly-graph-div');
    if (!gd || !gd._fullLayout) {{ setTimeout(placeFlagOverlays, 300); return; }}
    const container = document.getElementById('flag-container');
    container.innerHTML = '';
    const layout = gd._fullLayout;
    const xaxis = layout.xaxis, yaxis = layout.yaxis;
    const dragLayer = gd.querySelector('.nsewdrag');
    if (!dragLayer) {{ setTimeout(placeFlagOverlays, 300); return; }}
    const rect = dragLayer.getBoundingClientRect();
    const gdRect = gd.getBoundingClientRect();
    const offsetX = rect.left - gdRect.left;
    const offsetY = rect.top - gdRect.top;

    for (const [nid, meta] of Object.entries(flagData)) {{
      const sz = FLAG_SIZES[meta.layer];
      if (!sz || !meta.flag) continue;
      const xy = posData[nid];
      if (!xy) continue;
      const px = xaxis.l2p(xy[0]) + offsetX;
      const py = yaxis.l2p(xy[1]) + offsetY;
      const div = document.createElement('div');
      div.className = 'flag-overlay';
      div.style.width = sz + 'px';
      div.style.height = sz + 'px';
      div.style.left = px + 'px';
      div.style.top = py + 'px';
      const img = document.createElement('img');
      img.src = meta.flag;
      img.alt = meta.name;
      img.onerror = () => div.remove();
      div.appendChild(img);
      container.appendChild(div);
    }}
  }}

  document.addEventListener('DOMContentLoaded', () => setTimeout(placeFlagOverlays, 600));
  window.addEventListener('resize', () => setTimeout(placeFlagOverlays, 150));
  document.addEventListener('DOMContentLoaded', () => {{
    const gd = document.querySelector('.plotly-graph-div');
    if (gd) {{
      gd.on('plotly_relayout', () => setTimeout(placeFlagOverlays, 80));
      gd.on('plotly_afterplot', () => setTimeout(placeFlagOverlays, 150));
    }}
  }});
}})();
</script>"""

        return base_html.replace('</body>', inject + '\n</body>')

    def create_interactive_map(self, G: nx.Graph, all_treaties: List[Dict[str, Any]], blocs: Dict[str, List[List[int]]] = None):
        """
        Creates an interactive 3D treaty map using Plotly with a summary of blocs.
        """
        if not G.nodes:
            print("Graph is empty, cannot generate map.")
            return ""

        # Build alliance data with bloc information
        alliance_bloc_map = {}
        if blocs and 'combined' in blocs:
            for bloc_idx, bloc in enumerate(blocs['combined']):
                for alliance_id in bloc:
                    alliance_bloc_map[alliance_id] = bloc_idx

        # Sort alliances by score and bloc
        sorted_alliances = sorted(G.nodes(data=True), key=lambda x: (alliance_bloc_map.get(x[0], float('inf')), -x[1].get('score', 0)))

        # Create alliance toggle HTML
        summary_html = "<h2>Alliances</h2><input type=\"checkbox\" id=\"toggle-all\" checked> <label for=\"toggle-all\">Toggle All</label><ul>"
        for node_id, data in sorted_alliances:
            alliance_name = data.get('name', str(node_id))
            score = data.get('score', 0)
            bloc_info = f" (Bloc {alliance_bloc_map[node_id] + 1})" if node_id in alliance_bloc_map else ""
            sanitized_alliance_name = alliance_name.replace(" ", "-").replace("'", "")
            summary_html += f'<li><input type=\"checkbox\" class=\"alliance-toggle\" id=\"alliance-toggle-{sanitized_alliance_name}\" data-alliance-id=\"{node_id}\" data-bloc-id=\"{alliance_bloc_map.get(node_id, -1)}\" checked> <label for=\"alliance-toggle-{sanitized_alliance_name}\">{alliance_name} ({score:,.0f}){bloc_info}</label></li>'
        summary_html += "</ul>"
        
        # Add bloc toggle HTML
        if blocs and 'combined' in blocs and blocs['combined']:
            summary_html += "<h2>Blocs</h2><input type=\"checkbox\" id=\"toggle-all-blocs\" checked> <label for=\"toggle-all-blocs\">Toggle All Blocs</label><ul>"
            for i, bloc in enumerate(blocs['combined'], 1):
                bloc_names = []
                total_score = 0
                for alliance_id in bloc:
                    if G.has_node(alliance_id):
                        alliance_name = G.nodes[alliance_id].get('name', str(alliance_id))
                        score = G.nodes[alliance_id].get('score', 0)
                        bloc_names.append(f"{alliance_name} ({score:,.0f})")
                        total_score += score
                summary_html += f'<li><input type=\"checkbox\" class=\"bloc-toggle\" id=\"bloc-toggle-{i}\" data-bloc-id=\"{i-1}\" checked> <label for=\"bloc-toggle-{i}\">Bloc {i} (Score: {total_score:,.0f})</label></li>'
            summary_html += "</ul>"

        # Create enhanced layout with proper bloc spacing
        pos = self._create_enhanced_layout(G, blocs)

        # Build treaty data with proper coloring
        edge_traces = []
        all_treaty_data = []
        
        # Create a mapping of edges to their treaty data for proper coloring
        edge_treaty_map = {}
        for treaty in all_treaties:
            a1_id = treaty.get('alliance1_id')
            a2_id = treaty.get('alliance2_id')
            if a1_id and a2_id and G.has_edge(a1_id, a2_id):
                # Store treaty data for this edge, using alliance1 as the color source
                alliance1_data = treaty.get('alliance1', {})
                color = self._get_alliance_color(alliance1_data.get('color') or '')
                treaty_type = treaty.get('treaty_type', 'Unknown')
                
                # Use alliance1's color for the edge
                edge_key = tuple(sorted([a1_id, a2_id]))
                if edge_key not in edge_treaty_map:
                    edge_treaty_map[edge_key] = {
                        'color': color,
                        'width': self._get_treaty_width(treaty_type),
                        'alliance1_id': a1_id
                    }
                else:
                    # If multiple treaties, use the most significant one's color
                    existing_width = edge_treaty_map[edge_key]['width']
                    new_width = self._get_treaty_width(treaty_type)
                    if new_width > existing_width:
                        edge_treaty_map[edge_key] = {
                            'color': color,
                            'width': new_width,
                            'alliance1_id': a1_id
                        }
        
        for edge in G.edges(data=True):
            x0, y0, z0 = pos[edge[0]]
            x1, y1, z1 = pos[edge[1]]
            edge_data = edge[2]
            
            # Get the proper color from alliance1
            edge_key = tuple(sorted([edge[0], edge[1]]))
            if edge_key in edge_treaty_map:
                treaty_info = edge_treaty_map[edge_key]
                alliance1_color = treaty_info['color']
                width = treaty_info['width']
            else:
                # Fallback to existing edge data
                alliance1_color = edge_data.get('color', '#cccccc')
                width = edge_data.get('width', 1)
            
            edge_style = {'color': alliance1_color, 'width': width}
            all_treaty_data.append({'source': edge[0], 'target': edge[1], 'color': alliance1_color})

            trace = go.Scatter3d(
                x=[x0, x1, None], y=[y0, y1, None], z=[z0, z1, None],
                mode='lines',
                line=edge_style,
                hoverinfo='none',
                visible=True
            )
            edge_traces.append(trace)

        # Build enhanced node data with bloc information
        all_node_data = []
        for node in G.nodes():
            x, y, z = pos[node]
            alliance_id = node
            alliance_data = G.nodes[node]
            alliance_name = alliance_data.get('name', str(node))
            alliance_url = f'https://politicsandwar.com/alliance/id/{alliance_id}'
            score = alliance_data.get('score', 0)
            color = self._get_alliance_color(alliance_data.get('color') or '')
            flag_url = alliance_data.get('flag')
            size = 20 + math.log10(max(1, score)) * 5
            bloc_id = alliance_bloc_map.get(alliance_id, -1)
            
            # Get alliance acronym
            acronym = ''.join(word[0] for word in alliance_name.split() if word).upper()[:3]
            
            # Get treaties for this alliance
            alliance_treaties = []
            bloc_name = f"Bloc {bloc_id + 1}" if bloc_id >= 0 else "Unaligned"
            
            for treaty in all_treaties:
                if treaty.get('alliance1_id') == alliance_id:
                    other_alliance_id = treaty.get('alliance2_id')
                    if G.has_node(other_alliance_id):
                        other_alliance_data = G.nodes[other_alliance_id]
                        other_alliance_name = other_alliance_data.get('name', str(other_alliance_id))
                        treaty_type = treaty.get('treaty_type', 'Unknown')
                        alliance_treaties.append(f"{other_alliance_name} - {treaty_type}")
                elif treaty.get('alliance2_id') == alliance_id:
                    other_alliance_id = treaty.get('alliance1_id')
                    if G.has_node(other_alliance_id):
                        other_alliance_data = G.nodes[other_alliance_id]
                        other_alliance_name = other_alliance_data.get('name', str(other_alliance_id))
                        treaty_type = treaty.get('treaty_type', 'Unknown')
                        alliance_treaties.append(f"{other_alliance_name} - {treaty_type}")

            # Create enhanced hover text with flag image and dynamic colors
            flag_html = ''
            if flag_url:
                flag_html = f'<div class="alliance-flag"><img src="{flag_url}" alt="{alliance_name} flag" onerror="this.style.display=\'none\'"></div>'
            
            treaties_html = ''
            if alliance_treaties:
                treaty_items = ''.join(f'<li>{t}</li>' for t in sorted(alliance_treaties))
                treaties_html = f'<div class="treaty-list"><b>Treaties</b><ul>{treaty_items}</ul></div>'

            # Calculate contrast color for text readability
            text_color = self._get_contrast_color(color)
            
            hover_text = f'''
<div class="hover-content" style="background-color: {color}; color: {text_color}; border: 2px solid {color};">
    {flag_html}
    <a href="{alliance_url}" target="_blank" style="color: {text_color};">{alliance_name}</a>
    <div class="alliance-acronym" style="background-color: rgba(255,255,255,0.2); color: {text_color};">{acronym}</div>
    <div class="alliance-score" style="color: {text_color};">{score:,.0f}</div>
    <div class="alliance-bloc" style="background-color: rgba(255,255,255,0.15); color: {text_color};">{bloc_name}</div>
    {treaties_html}
</div>'''

            all_node_data.append({
                'id': node,
                'x': x, 'y': y, 'z': z,
                'text': hover_text,
                'color': color,
                'size': size,
                'name': alliance_name,
                'bloc_id': bloc_id,
                'flag_url': flag_url
            })
        
        # Create node trace
        node_x = [n['x'] for n in all_node_data]
        node_y = [n['y'] for n in all_node_data]
        node_z = [n['z'] for n in all_node_data]
        node_text = [n['text'] for n in all_node_data]
        node_colors = [n['color'] for n in all_node_data]
        node_sizes = [n['size'] for n in all_node_data]

        node_trace = go.Scatter3d(
            x=node_x, y=node_y, z=node_z, mode='markers', hoverinfo='none', text=node_text,
            marker=dict(
                size=node_sizes,
                color=node_colors,
                line=dict(width=2, color='#333333'),
            ),
            customdata=[[n['id'], n['flag_url']] for n in all_node_data],
            uid='node_trace'
        )

        # Create figure
        fig = go.Figure(data=edge_traces + [node_trace],
                        layout=go.Layout(title='<br>PnW Treaty-verse', showlegend=False, hovermode='closest',
                                         clickmode='event',
                                         margin=dict(b=20,l=5,r=5,t=40),
                                         height=1200, # Taller graph
                                         annotations=[dict(showarrow=False, text="Treaty Map", xref="paper", yref="paper", x=0.005, y=0.95)],
                                         scene=dict(xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                                                  yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                                                  zaxis=dict(showgrid=False, zeroline=False, showticklabels=False))))
        
        # Check if a file for the current day already exists
        today_str = datetime.now().strftime("%m-%d-%Y")
        html_filename = f"universe_{today_str}.html"
        html_filepath = os.path.join(self.web_dir, html_filename)

        if os.path.exists(html_filepath):
            return html_filename

        # Enhanced JavaScript for proper toggle functionality
        js_code = """<script>
    document.addEventListener('DOMContentLoaded', function() {
        const allNodes = %s;
        const allTreaties = %s;
        const plotContainer = document.getElementById('plot');
        const graphDiv = plotContainer.querySelector('.plotly-graph-div');
        const pinnedCards = new Map();
        let hoverTimeout;

        const pinnedContainer = document.createElement('div');
        pinnedContainer.className = 'pinned-cards-container';
        plotContainer.appendChild(pinnedContainer);

        let temporaryHoverCard = document.createElement('div');
        temporaryHoverCard.className = 'custom-hover-card';
        plotContainer.appendChild(temporaryHoverCard);

        function updateGraph() {
            const checkedAllianceIds = new Set(Array.from(document.querySelectorAll('.alliance-toggle:checked')).map(cb => parseInt(cb.dataset.allianceId, 10)));
            const checkedBlocIds = new Set(Array.from(document.querySelectorAll('.bloc-toggle:checked')).map(cb => parseInt(cb.dataset.blocId, 10)));
            
            // Filter nodes based on both alliance and bloc toggles
            let nodesToShow = allNodes.filter(node => {
                const allianceChecked = checkedAllianceIds.has(node.id);
                const blocChecked = node.bloc_id === -1 || checkedBlocIds.has(node.bloc_id);
                return allianceChecked && blocChecked;
            });
            
            const nodesToShowIds = new Set(nodesToShow.map(n => n.id));

            // Update node trace
            const node_trace = graphDiv.data[graphDiv.data.length - 1];
            node_trace.x = nodesToShow.map(n => n.x);
            node_trace.y = nodesToShow.map(n => n.y);
            node_trace.z = nodesToShow.map(n => n.z);
            node_trace.text = nodesToShow.map(n => n.text);
            node_trace.marker.color = nodesToShow.map(n => n.color);
            node_trace.marker.size = nodesToShow.map(n => n.size);
            node_trace.customdata = nodesToShow.map(n => [n.id, n.flag_url]);

            // Update edge visibility
            const edgesToShow = allTreaties.filter(edge => nodesToShowIds.has(edge.source) && nodesToShowIds.has(edge.target));

            for (let i = 0; i < allTreaties.length; i++) {
                const edge = allTreaties[i];
                const trace = graphDiv.data[i];
                const shouldShow = edgesToShow.some(e => e.source === edge.source && e.target === edge.target);
                trace.visible = shouldShow;
            }
            
            Plotly.react(graphDiv, graphDiv.data, graphDiv.layout);
        }

        // Toggle all alliances
        document.getElementById('toggle-all').addEventListener('change', function() {
            document.querySelectorAll('.alliance-toggle').forEach(toggle => {
                toggle.checked = this.checked;
            });
            updateGraph();
        });

        // Toggle all blocs
        document.getElementById('toggle-all-blocs').addEventListener('change', function() {
            document.querySelectorAll('.bloc-toggle').forEach(toggle => {
                toggle.checked = this.checked;
            });
            updateGraph();
        });

        // Individual alliance toggles
        document.querySelectorAll('.alliance-toggle').forEach(toggle => {
            toggle.addEventListener('change', () => {
                const allToggles = document.querySelectorAll('.alliance-toggle');
                const allChecked = Array.from(allToggles).every(t => t.checked);
                document.getElementById('toggle-all').checked = allChecked;
                updateGraph();
            });
        });

        // Individual bloc toggles
        document.querySelectorAll('.bloc-toggle').forEach(toggle => {
            toggle.addEventListener('change', () => {
                const allBlocToggles = document.querySelectorAll('.bloc-toggle');
                const allChecked = Array.from(allBlocToggles).every(t => t.checked);
                document.getElementById('toggle-all-blocs').checked = allChecked;
                updateGraph();
            });
        });

        // Enhanced hover functionality
        graphDiv.on('plotly_hover', function(data) {
            const point = data.points[0];
            if (!point) return;
            const allianceId = point.customdata[0];
            if (pinnedCards.has(allianceId)) return;

            clearTimeout(hoverTimeout);
            temporaryHoverCard.innerHTML = point.text;
            
            const rect = plotContainer.getBoundingClientRect();
            let x = data.event.clientX - rect.left;
            let y = data.event.clientY - rect.top;
            
            const cardWidth = 320;
            const cardHeight = temporaryHoverCard.getBoundingClientRect().height || 250;

            if (x + cardWidth > rect.width) x -= (cardWidth + 20);
            if (y + cardHeight > rect.height) y -= (cardHeight + 20);

            temporaryHoverCard.style.left = `${x + 10}px`;
            temporaryHoverCard.style.top = `${y + 10}px`;
            temporaryHoverCard.style.display = 'block';
        });

        graphDiv.on('plotly_unhover', function(data) {
             hoverTimeout = setTimeout(() => {
                temporaryHoverCard.style.display = 'none';
            }, 200);
        });

        temporaryHoverCard.addEventListener('mouseenter', () => clearTimeout(hoverTimeout));
        temporaryHoverCard.addEventListener('mouseleave', () => temporaryHoverCard.style.display = 'none');

        // Enhanced click functionality for persistent hover cards
        graphDiv.on('plotly_click', function(data) {
            if (data.points.length === 0) return;
            const point = data.points[0];
            const allianceId = point.customdata[0];

            temporaryHoverCard.style.display = 'none';

            if (pinnedCards.has(allianceId)) {
                const card = pinnedCards.get(allianceId);
                card.element.remove();
                pinnedCards.delete(allianceId);
                return;
            }

            const cardElement = document.createElement('div');
            cardElement.className = 'custom-hover-card pinned';
            cardElement.style.display = 'block';
            
            const closeButton = document.createElement('button');
            closeButton.className = 'close-btn';
            closeButton.innerHTML = '&times;';
            closeButton.onclick = function() {
                cardElement.remove();
                pinnedCards.delete(allianceId);
            };

            const parsedHTML = new DOMParser().parseFromString(point.text, 'text/html');
            const contentNode = parsedHTML.body.firstChild;

            cardElement.appendChild(closeButton);
            if (contentNode) {
                cardElement.appendChild(contentNode);
            }
            
            pinnedContainer.appendChild(cardElement);

            const rect = plotContainer.getBoundingClientRect();
            let x = data.event.clientX - rect.left;
            let y = data.event.clientY - rect.top;

            const cardWidth = 320;
            const cardHeight = cardElement.getBoundingClientRect().height || 250;

            if (x + cardWidth > rect.width) x -= (cardWidth + 20);
            if (y + cardHeight > rect.height) y -= (cardHeight + 20);
            
            cardElement.style.left = `${x + 10}px`;
            cardElement.style.top = `${y + 10}px`;

            pinnedCards.set(allianceId, { element: cardElement, data: point });

            // Make card draggable
            let isDragging = false, dragStartX, dragStartY, cardStartX, cardStartY;
            cardElement.onmousedown = function(e) {
                if (e.target.tagName === 'A' || e.target.tagName === 'BUTTON' || e.target.closest('a, button')) return;
                isDragging = true;
                dragStartX = e.clientX;
                dragStartY = e.clientY;
                const cardRect = cardElement.getBoundingClientRect();
                const containerRect = pinnedContainer.getBoundingClientRect();
                cardStartX = cardRect.left - containerRect.left;
                cardStartY = cardRect.top - containerRect.top;
                cardElement.style.cursor = 'grabbing';
                e.preventDefault();
            };
            document.onmousemove = function(e) {
                if (!isDragging) return;
                const dx = e.clientX - dragStartX;
                const dy = e.clientY - dragStartY;
                cardElement.style.left = `${cardStartX + dx}px`;
                cardElement.style.top = `${cardStartY + dy}px`;
            };
            document.onmouseup = function() {
                if (isDragging) {
                    isDragging = false;
                    cardElement.style.cursor = 'grab';
                }
            };
        });

        updateGraph();
    });
</script>""" % (json.dumps(all_node_data), json.dumps(all_treaty_data))

        final_html = f'''
        <html>
            <head>
                <meta charset=\"utf-8\" />
                <title>Interactive Treaty Universe</title>
                <script src=\"https://cdn.plot.ly/plotly-latest.min.js\"></script>
                <style>
                    body {{ font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, \"Helvetica Neue\", Arial, sans-serif; margin: 0; background-color: #f8f9fa; }}
                    #container {{ display: flex; flex-direction: row; height: 100vh; }}
                    #sidebar {{ width: 30%; height: 100%; overflow-y: auto; background-color: #fff; border-right: 1px solid #dee2e6; box-shadow: 0 0 10px rgba(0,0,0,0.05); }}
                    #plot {{ width: 70%; height: 100%; position: relative; }}
                    .bloc-summary {{ padding: 20px; }}
                    h1, h2, h3 {{ color: #343a40; }}
                    h1 {{ text-align: center; border-bottom: 1px solid #dee2e6; padding-bottom: 15px; margin-top: 0;}}
                    h3 {{ border-bottom: 1px solid #eee; padding-bottom: 5px; }}
                    ul {{ list-style-type: none; padding-left: 0; }}
                    li {{ background-color: #f1f3f5; margin-bottom: 5px; padding: 8px; border-radius: 4px; }}
                    input[type=\"checkbox\"] {{ margin-right: 8px; }}
                    
                    .custom-hover-card {{
                        position: absolute;
                        background: transparent; /* Changed for dynamic coloring */
                        padding: 0; /* Padding moved to hover-content */
                        border-radius: 8px;
                        box-shadow: 0 8px 25px rgba(0,0,0,0.15);
                        width: 320px;
                        font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, \"Helvetica Neue\", Arial, sans-serif;
                        font-size: 14px;
                        z-index: 1000;
                        display: none;
                        pointer-events: all;
                    }}
                    .custom-hover-card.pinned {{
                        cursor: grab;
                        display: block !important;
                    }}
                    .pinned-cards-container {{
                        position: absolute;
                        top: 0;
                        left: 0;
                        width: 100%;
                        height: 100%;
                        pointer-events: none;
                        z-index: 999;
                    }}
                    .pinned-cards-container > .custom-hover-card {{
                        pointer-events: all;
                    }}

                    .custom-hover-card .close-btn {{
                        position: absolute;
                        top: 8px;
                        right: 12px;
                        background: rgba(0,0,0,0.2);
                        border: none;
                        font-size: 18px;
                        font-weight: bold;
                        color: inherit; /* Inherit from dynamic text color */
                        cursor: pointer;
                        padding: 0;
                        width: 24px;
                        height: 24px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        border-radius: 50%;
                        transition: background-color 0.2s, opacity 0.2s;
                        z-index: 10;
                    }}
                    .custom-hover-card .close-btn:hover {{ 
                        background: rgba(0,0,0,0.3);
                        opacity: 0.8;
                    }}

                    .hover-content {{
                        text-align: center;
                        line-height: 1.4;
                        padding: 15px;
                        border-radius: 8px;
                        box-shadow: 0 8px 25px rgba(0,0,0,0.15);
                        border: 2px solid;
                        position: relative;
                    }}
                    .hover-content a {{
                        font-weight: bold;
                        font-size: 16px;
                        text-decoration: none;
                        display: inline-block;
                        margin-bottom: 10px;
                        padding: 4px 8px;
                        border-radius: 4px;
                        transition: background-color 0.2s, opacity 0.2s;
                        background-color: rgba(255,255,255,0.1);
                    }}
                    .hover-content a:hover {{ 
                        text-decoration: underline;
                        background-color: rgba(255,255,255,0.2);
                    }}
                    .hover-content .alliance-acronym {{
                        font-weight: bold;
                        font-size: 15px;
                        padding: 4px 8px;
                        border-radius: 4px;
                        display: inline-block;
                        margin: 5px 0;
                        background-color: rgba(255,255,255,0.15);
                    }}
                    .hover-content .alliance-score {{
                        font-size: 14px;
                        font-weight: 600;
                        margin: 5px 0;
                    }}
                    .hover-content .alliance-bloc {{
                        font-size: 13px;
                        font-weight: 500;
                        margin: 5px 0;
                        padding: 3px 6px;
                        border-radius: 3px;
                        display: inline-block;
                        background-color: rgba(255,255,255,0.1);
                    }}
                    .hover-content .alliance-flag {{
                        margin-bottom: 10px;
                        text-align: center;
                    }}
                    .hover-content .alliance-flag img {{
                        max-width: 80px;
                        max-height: 50px;
                        border: 1px solid #ddd;
                        border-radius: 4px;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                        object-fit: contain;
                        background-color: #f8f9fa;
                    }}
                    .hover-content .treaty-list {{
                        margin-top: 12px;
                        padding-top: 12px;
                        border-top: 1px solid rgba(255,255,255,0.3);
                        text-align: left;
                    }}
                    .hover-content .treaty-list b {{
                        display: block;
                        text-align: center;
                        margin-bottom: 8px;
                        font-size: 13px;
                        text-transform: uppercase;
                        letter-spacing: 0.5px;
                        opacity: 0.9;
                    }}
                    .hover-content .treaty-list ul {{
                        margin: 0;
                        padding-left: 20px;
                        list-style-type: circle;
                    }}
                    .hover-content .treaty-list li {{
                        margin-bottom: 6px;
                        background-color: transparent;
                        padding: 2px 0;
                        font-size: 13px;
                        line-height: 1.3;
                        opacity: 0.85;
                    }}
                    .hover-content .treaty-list li:hover {{
                        opacity: 1;
                        background-color: rgba(255,255,255,0.1);
                        border-radius: 3px;
                        padding-left: 4px;
                        margin-left: -4px;
                    }}
                </style>
            </head>
            <body>
                <div id=\"container\">
                    <div id=\"sidebar\">
                        <div class=\"bloc-summary\">
                            {summary_html}
                        </div>
                    </div>
                    <div id=\"plot\">
                        {plot_div}
                    </div>
                </div>
                {js_code}
            </body>
        </html>
        '''
        # Save the HTML file
        with open(html_filepath, "w", encoding="utf-8") as f:
            f.write(final_html)

        return html_filename