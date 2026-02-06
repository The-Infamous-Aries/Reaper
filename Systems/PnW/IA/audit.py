import discord
from discord.ext import commands
from discord import app_commands
from typing import List, Dict, Any, Optional, Callable, Literal
from datetime import datetime, timezone, timedelta
import logging
import os
import sys
import asyncio
import math

try:
    _project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    _local_packages = os.path.join(_project_root, 'local_packages')
    if os.path.isdir(_local_packages) and _local_packages not in sys.path:
        sys.path.insert(0, _local_packages)
    # Prevent user site-packages precedence over vendored copies
    os.environ.setdefault('PYTHONNOUSERSITE', '1')
except Exception as _vend_err:
    logging.getLogger('AuditManager').warning(f"Vendored path setup failed: {_vend_err}")

try:
    import aiohttp  # type: ignore
    import io  # type: ignore
    from PIL import Image, ImageOps, ImageDraw, ImageFont  # type: ignore
except Exception:
    aiohttp = None
    io = None
    Image = None
    ImageOps = None
    ImageDraw = None
    ImageFont = None

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from Systems.Functions import emoji as emoji_mod

def _nation_link(n: Dict[str, Any]) -> str:
    """Return markdown link to a nation's PnW page."""
    nid = n.get('nation_id') or n.get('id') or n.get('nationid')
    name = (n.get('nation_name') or n.get('name') or 'Unknown').strip()
    try:
        nid_str = str(int(nid)) if nid is not None else ''
    except Exception:
        nid_str = str(nid) if nid is not None else ''
    url = f"https://politicsandwar.com/nation/id={nid_str}" if nid_str else "https://politicsandwar.com/nation/"
    return f"[{name}]({url})"


def _measure_text(font: Any, text: str) -> tuple[int, int]:
    try:
        if Image is None or ImageDraw is None or font is None:
            return (max(1, len(text)), 1)
        img = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        try:
            box = d.textbbox((0, 0), text, font=font)
            return (int(box[2] - box[0]), int(box[3] - box[1]))
        except Exception:
            try:
                w = d.textlength(text, font=font) if hasattr(d, "textlength") else (len(text) * 8)
                if hasattr(font, "getmetrics"):
                    a, b = font.getmetrics()
                    h = int(a + b)
                else:
                    h = 12
                return (int(w), int(h))
            except Exception:
                return (len(text) * 8, 12)
    except Exception:
        return (len(text) * 8, 12)


def _days_inactive(n: Dict[str, Any]) -> Optional[int]:
    """Compute days since last_active from a nation dict."""
    s = n.get('last_active')
    if not s:
        return None
    try:
        # Normalize common formats; handle 'Z' and missing timezone
        if isinstance(s, str):
            last = s.strip()
            if last.endswith('Z'):
                last = last.replace('Z', '+00:00')
            # If there's no timezone part, assume UTC
            if '+' not in last and last.count(':') >= 2:
                last += '+00:00'
            dt = datetime.fromisoformat(last)
        else:
            dt = s
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - dt).days
    except Exception:
        return None


class AuditManager(commands.Cog):
    """Cog to audit alliance nations and surface issues in an embed."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger(self.__class__.__name__)
        self.db4d_id = '14635'
        # Track the last posted treaties message per channel to edit instead of posting new
        self.treaties_message_map: Dict[int, int] = {}

    # Dynamic autocomplete for mmr_mode: only suggest when view=="mmr"
    async def _mmr_mode_autocomplete(self, interaction: discord.Interaction, current: str):
        try:
            view_sel = getattr(interaction.namespace, 'view', None)
        except Exception:
            view_sel = None
        if view_sel == 'mmr':
            base = [
                app_commands.Choice(name="Basic", value="basic"),
                app_commands.Choice(name="Max", value="max"),
            ]
            cur = (current or "").lower()
            if cur:
                return [c for c in base if (cur in c.name.lower()) or (cur in c.value)]
            return base
        # When not in MMR view, no suggestions (keeps UI clean)
        return []

    # Autocomplete for treaties command alliance argument
    async def _treaties_alliance_autocomplete(self, interaction: discord.Interaction, current: str):
        try:
            cur = (current or "").strip().lower()
            choices: List[app_commands.Choice[str]] = []

            # Numeric ID direct entry
            if cur.isdigit():
                choices.append(app_commands.Choice(name=f"Alliance ID {current}", value=current))

            # Suggest home alliance explicitly
            if not cur:
                try:
                    choices.append(app_commands.Choice(name="Death Before Dishonor (DB4D)", value=str(int(self.db4d_id))))
                except Exception:
                    choices.append(app_commands.Choice(name="Death Before Dishonor (DB4D)", value=str(self.db4d_id)))

            # No external bloc suggestions

            # Limit to 25
            return choices[:25]
        except Exception:
            return []

    async def _fetch_flag_image(self, url: str) -> Optional["Image.Image"]:
        """Download an image from URL and return a PIL Image, or None on failure.
        This is safe to call even if Pillow/aiohttp are unavailable; it will return None.
        """
        try:
            if not url:
                return None
            if aiohttp is None or Image is None or io is None:
                # Dependencies not available; skip image processing
                return None
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.read()
            bio = io.BytesIO(data)
            img = Image.open(bio)
            return img
        except Exception:
            return None

    def _normalize_treaty_type(self, ttype: str) -> str:
        """Normalize various treaty type labels/abbreviations to canonical keys.
        Returns one of: 'MDP', 'MDoAP', 'ODP', 'ODoAP', 'Protectorate', 'NAP', 'PIAT', 'Extension'.
        """
        s = (ttype or '').strip().lower()
        s_compact = s.replace(' ', '').replace('-', '')
        # Direct abbreviation hits
        if s_compact in {"mdp"} or s.startswith("mutual defense"):
            return "MDP"
        if s_compact in {"mdoap"} or s.startswith("mutual defense/optional aggression") or s_compact in {"mutualdefenseoptionalaggression"}:
            return "MDoAP"
        if s_compact in {"odp"} or s.startswith("optional defense"):
            return "ODP"
        if s_compact in {"odoap"} or s.startswith("optional defense/optional aggression") or s_compact in {"optionaldefenseoptionalaggression"}:
            return "ODoAP"
        if s_compact in {"protectorate", "prot"}:
            return "Protectorate"
        if s_compact in {"nap"} or s.startswith("non-aggression") or s.startswith("no aggression"):
            return "NAP"
        if s_compact in {"piat"} or s.startswith("peace, intelligence and aid"):
            return "PIAT"
        if s_compact in {"extension", "ext"} or s.startswith("extension"):
            return "Extension"
        # Fallback to original for unknown types
        return ttype.strip() or ""

    def _resize_flag_image(self, img: "Image.Image", size: tuple[int, int] = (24, 24)) -> Optional["Image.Image"]:
        """Resize the given PIL image to size, maintaining aspect ratio and adding padding if needed."""
        try:
            if Image is None or ImageOps is None:
                return None
            # Convert to RGBA for consistent output
            if img.mode not in ("RGBA", "LA"):
                img = img.convert("RGBA")
            # Fit into target box, maintain aspect
            resized = ImageOps.contain(img, size)
            # Pad to exact size
            out = Image.new("RGBA", size, (0, 0, 0, 0))
            ox = (size[0] - resized.width) // 2
            oy = (size[1] - resized.height) // 2
            # Use resized as mask to preserve transparency
            out.paste(resized, (ox, oy), resized)
            return out
        except Exception:
            return None

    def _generate_category_image_sync(self, rows_data: List[tuple[Optional["Image.Image"], str]], title: str, row_height: int) -> Optional[discord.File]:
        """Synchronous part of category image generation."""
        try:
            if Image is None or ImageDraw is None or ImageFont is None:
                return None
            font = ImageFont.load_default()
            
            # Process rows with resizing
            processed_rows = []
            for img, text in rows_data:
                resized_img = None
                if img is not None:
                    resized_img = self._resize_flag_image(img, (24, 24))
                processed_rows.append((resized_img, text))
            
            # Determine image width by measuring text
            max_text_w = 0
            for _, text in processed_rows:
                w, _ = _measure_text(font, text)
                if w > max_text_w:
                    max_text_w = w
            
            # Image width: padding + flag(24) + gap + text + padding
            padding = 8
            gap = 8
            width = padding + 24 + gap + max_text_w + padding
            # Title height
            title_h = _measure_text(font, title)[1] + padding
            # Total height: title + rows * row_height + padding
            height = title_h + len(processed_rows) * row_height + padding
            
            # Create canvas
            canvas = Image.new("RGBA", (max(width, 200), max(height, 50)), (255, 255, 255, 0))
            draw = ImageDraw.Draw(canvas)
            
            # Draw title
            draw.text((padding, padding // 2), title, fill=(255, 255, 255, 255), font=font)
            
            # Draw rows
            y = title_h
            for img, text in processed_rows:
                # Flag
                if img is not None:
                    canvas.paste(img, (padding, y + (row_height - img.height) // 2), img)
                # Text
                draw.text((padding + 24 + gap, y + (row_height - _measure_text(font, text)[1]) // 2), text, fill=(255, 255, 255, 255), font=font)
                y += row_height

            # Save to buffer as PNG
            if io is None:
                return None
            buf = io.BytesIO()
            canvas.save(buf, format='PNG')
            buf.seek(0)
            
            # Filename based on title
            safe_name = ''.join(c for c in title if c.isalnum()).lower() or "category"
            return discord.File(buf, filename=f"treaties_{safe_name}.png")
        except Exception:
            return None

    def _generate_treaty_web_image_sync(self, 
                                      immediate_items: List[Dict[str, Any]], 
                                      m_items: List[Dict[str, Any]], 
                                      o_items: List[Dict[str, Any]], 
                                      peace_items: List[Dict[str, Any]],
                                      cy_raw_img: Optional["Image.Image"],
                                      center_size: int = 80) -> Optional[discord.File]:
        """Synchronous part of treaty web image generation."""
        try:
            if Image is None or ImageDraw is None or ImageFont is None:
                return None
                
            # Resize logic helper
            def process_items(items: List[Dict[str, Any]], size: int) -> List[Dict[str, Any]]:
                out = []
                for item in items:
                    raw = item.get('img_raw')
                    resized = None
                    if raw:
                        resized = self._resize_flag_image(raw, (size, size))
                    else:
                        ph = Image.new("RGBA", (size, size), (40, 40, 40, 200))
                        d = ImageDraw.Draw(ph)
                        text = (item.get('acr') or item.get('name') or "?")
                        text = (text[:3] or "?").upper()
                        try:
                            try:
                                box = d.textbbox((0, 0), text)
                                tw, th = int(box[2] - box[0]), int(box[3] - box[1])
                            except Exception:
                                tw, th = (len(text) * 8, 12)
                            d.text(((size - tw) // 2, (size - th) // 2), text, fill=(255, 255, 255, 220))
                        except Exception:
                            d.text((size // 4, size // 3), text, fill=(255, 255, 255, 220))
                        resized = ph
                    
                    new_item = dict(item)
                    new_item['img'] = resized
                    # Remove raw image to save memory/avoid confusion, though not strictly necessary
                    if 'img_raw' in new_item:
                        del new_item['img_raw']
                    out.append(new_item)
                return out

            # Process all groups
            immediate_placed = process_items(immediate_items, 56)
            m_placed = process_items(m_items, 58)
            o_placed = process_items(o_items, 58)
            peace_placed = process_items(peace_items, 58)

            cy_img = None
            if cy_raw_img:
                cy_img = self._resize_flag_image(cy_raw_img, (center_size, center_size))

            # Helper functions for layout
            used_angles: List[float] = []

            def _norm_angle(a: float) -> float:
                while a < 0:
                    a += 2 * math.pi
                while a >= 2 * math.pi:
                    a -= 2 * math.pi
                return a

            def _angle_diff(a: float, b: float) -> float:
                d = abs(a - b)
                while d > math.pi:
                    d = abs(d - 2 * math.pi)
                return d

            def assign_angles(items: List[Dict[str, Any]], offset: float = 0.0) -> None:
                n = len(items)
                if n <= 0:
                    return
                step = (2 * math.pi) / n
                jitter = math.pi / 180 * 5
                min_gap = math.pi / 180 * 14
                for i, it in enumerate(items):
                    a = _norm_angle(offset + step * i)
                    tries = 0
                    while any(_angle_diff(a, ua) < min_gap for ua in used_angles) and tries < 360:
                        a = _norm_angle(a + jitter)
                        tries += 1
                    used_angles.append(a)
                    it['angle'] = a

            def half_size(items: List[Dict[str, Any]]) -> int:
                try:
                    return max(((it.get('img').width or 0) // 2) for it in items) if items else 0
                except Exception:
                    return 0

            # Layout constants
            BASE_RADIUS = 160
            RING_GAP = 80
            IMMEDIATE_RADIUS = BASE_RADIUS
            M_RADIUS = BASE_RADIUS + 2 * RING_GAP
            O_RADIUS = BASE_RADIUS + 3 * RING_GAP
            PEACE_RADIUS = BASE_RADIUS + 4 * RING_GAP
            
            MARGIN = 28
            max_extent = max([
                IMMEDIATE_RADIUS + half_size(immediate_placed),
                M_RADIUS         + half_size(m_placed),
                O_RADIUS         + half_size(o_placed),
                PEACE_RADIUS     + half_size(peace_placed),
            ])
            CANVAS_SIZE = max(800, int(2 * (max_extent + MARGIN)))
            CENTER_X, CENTER_Y = CANVAS_SIZE // 2, CANVAS_SIZE // 2

            def place_circle(items: List[Dict[str, Any]], radius: int) -> List[Dict[str, Any]]:
                n = len(items)
                placed: List[Dict[str, Any]] = []
                if n == 0:
                    return placed
                for i, it in enumerate(items):
                    angle = it.get('angle') if it.get('angle') is not None else (2 * math.pi * i / n)
                    img_obj = it.get('img')
                    img_width = img_obj.width if img_obj else 48
                    img_height = img_obj.height if img_obj else 48
                    x = CENTER_X + int(radius * math.cos(angle)) - img_width // 2
                    y = CENTER_Y + int(radius * math.sin(angle)) - img_height // 2
                    it['pos'] = (x, y)
                    it['angle'] = angle
                    placed.append(it)
                return placed

            assign_angles(immediate_placed)
            assign_angles(m_placed)
            assign_angles(o_placed)
            assign_angles(peace_placed)

            immediate_final = place_circle(immediate_placed, IMMEDIATE_RADIUS)
            m_final = place_circle(m_placed, M_RADIUS)
            o_final = place_circle(o_placed, O_RADIUS)
            peace_final = place_circle(peace_placed, PEACE_RADIUS)

            # Draw
            canvas = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
            draw = ImageDraw.Draw(canvas)
            cy_center = (CENTER_X, CENTER_Y)
            
            COLOR_MAP: Dict[str, tuple] = {
                'Protectorate': (50, 205, 50, 200),
                'Extension':    (50, 205, 50, 200),
                'MDoAP':        (255, 255, 0, 200),
                'MDP':          (255, 255, 0, 200),
                'ODoAP':        (255, 165, 0, 200),
                'ODP':          (255, 165, 0, 200),
                'PIAT':         (0, 122, 255, 200),
                'NAP':          (0, 122, 255, 200),
            }

            def pick_line_color(line_type: Optional[str]) -> tuple:
                return COLOR_MAP.get(line_type or '', (255, 255, 255, 180))

            LINE_WIDTH = 2
            for it in immediate_final + m_final + o_final + peace_final:
                img_obj = it.get('img')
                pos = it.get('pos') or (CENTER_X, CENTER_Y)
                cx = pos[0] + (img_obj.width // 2 if img_obj else 0)
                cy = pos[1] + (img_obj.height // 2 if img_obj else 0)
                draw.line([cy_center, (cx, cy)], fill=pick_line_color(it.get('line_type')), width=LINE_WIDTH)

            def draw_ring(radius: int, color_key: str):
                col = COLOR_MAP.get(color_key, (255, 255, 255, 160))
                bbox = [CENTER_X - radius, CENTER_Y - radius, CENTER_X + radius, CENTER_Y + radius]
                draw.ellipse(bbox, outline=col, width=2)

            draw_ring(IMMEDIATE_RADIUS, 'Protectorate')
            draw_ring(M_RADIUS, 'MDP')
            draw_ring(O_RADIUS, 'ODP')
            draw_ring(PEACE_RADIUS, 'PIAT')

            for it in immediate_final:
                if it.get('img') is not None:
                    canvas.paste(it['img'], it['pos'], it['img'])
            for it in m_final:
                if it.get('img') is not None:
                    canvas.paste(it['img'], it['pos'], it['img'])
            for it in o_final:
                if it.get('img') is not None:
                    canvas.paste(it['img'], it['pos'], it['img'])
            for it in peace_final:
                if it.get('img') is not None:
                    canvas.paste(it['img'], it['pos'], it['img'])

            if cy_img is not None:
                canvas.paste(cy_img, (CENTER_X - center_size // 2, CENTER_Y - center_size // 2), cy_img)

            if io is None:
                return None
            buf = io.BytesIO()
            canvas.save(buf, format='PNG')
            buf.seek(0)
            return discord.File(buf, filename="treaty_web.png")
            
        except Exception:
            return None

    async def _compose_treaty_web_image(self, treaties: List[Dict[str, Any]], center_alliance_id: Optional[int] = None) -> Optional[discord.File]:
        if Image is None or ImageDraw is None or io is None:
            return None

        cy_flag_url: Optional[str] = None
        partners: List[Dict[str, Any]] = []
        partner_types: Dict[int, set] = {}

        try:
            center_id = int(center_alliance_id if center_alliance_id is not None else int(self.db4d_id))
        except Exception:
            center_id = int(self.db4d_id)

        for t in treaties or []:
            a1 = t.get('alliance1') or {}
            a2 = t.get('alliance2') or {}
            a1_id = int(str(a1.get('id') or t.get('alliance1_id') or 0)) if (a1.get('id') or t.get('alliance1_id')) else 0
            a2_id = int(str(a2.get('id') or t.get('alliance2_id') or 0)) if (a2.get('id') or t.get('alliance2_id')) else 0
            ttype = self._normalize_treaty_type(t.get('treaty_type') or '')

            if a1_id == center_id:
                if not cy_flag_url:
                    cy_flag_url = (a1.get('flag') or '').strip()
                other = a2
                other_id = a2_id
            elif a2_id == center_id:
                if not cy_flag_url:
                    cy_flag_url = (a2.get('flag') or '').strip()
                other = a1
                other_id = a1_id
            else:
                continue

            if other_id and other_id != center_id:
                partners.append({
                    'id': other_id,
                    'name': (other.get('name') or 'Unknown').strip(),
                    'acr': (other.get('acronym') or '').strip(),
                    'flag_url': (other.get('flag') or '').strip(),
                })
                if ttype:
                    partner_types.setdefault(other_id, set()).add(ttype)

        seen = set()
        immediate_partners: List[Dict[str, Any]] = []
        m_partners: List[Dict[str, Any]] = []
        o_partners: List[Dict[str, Any]] = []
        peace_partners: List[Dict[str, Any]] = []

        for p in partners:
            pid = int(p.get('id') or 0)
            if not pid or pid in seen:
                continue
            seen.add(pid)
            types = partner_types.get(pid) or set()
            if ('Protectorate' in types) or ('Extension' in types):
                immediate_partners.append(p)
            elif ('MDoAP' in types) or ('MDP' in types):
                m_partners.append(p)
            elif ('ODoAP' in types) or ('ODP' in types):
                o_partners.append(p)
            elif ('PIAT' in types) or ('NAP' in types):
                peace_partners.append(p)

        cy_img = await self._fetch_flag_image(cy_flag_url or '')

        async def fetch_raw_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            tasks = [self._fetch_flag_image(p.get('flag_url') or '') for p in items]
            raws = await asyncio.gather(*tasks) if tasks else []
            out: List[Dict[str, Any]] = []
            for i, raw in enumerate(raws):
                item = dict(items[i])
                item['img_raw'] = raw
                out.append(item)
            return out

        immediate_items = await fetch_raw_items([
            dict(p, line_type=('Protectorate' if ('Protectorate' in (partner_types.get(int(p.get('id') or 0)) or set())) else 'Extension'))
            for p in immediate_partners
        ])
        m_items = await fetch_raw_items([
            dict(p, line_type=('MDoAP' if ('MDoAP' in (partner_types.get(int(p.get('id') or 0)) or set())) else 'MDP'))
            for p in m_partners
        ])
        o_items = await fetch_raw_items([
            dict(p, line_type=('ODoAP' if ('ODoAP' in (partner_types.get(int(p.get('id') or 0)) or set())) else 'ODP'))
            for p in o_partners
        ])
        peace_items = await fetch_raw_items([
            dict(p, line_type=('PIAT' if ('PIAT' in (partner_types.get(int(p.get('id') or 0)) or set())) else 'NAP'))
            for p in peace_partners
        ])

        return await asyncio.to_thread(
            self._generate_treaty_web_image_sync,
            immediate_items,
            m_items,
            o_items,
            peace_items,
            cy_img,
            80  # CENTER_SIZE
        )


    async def _compose_category_image(self, items: List[Dict[str, Any]], title: str, alliance_id: int, row_height: int = 28) -> Optional[discord.File]:
        """Compose a simple image for a category."""
        try:
            # Gather all data first
            tasks = []
            texts = []
            for t in items:
                a1 = t.get('alliance1') or {}
                a2 = t.get('alliance2') or {}
                a1_id = int(str(a1.get('id') or t.get('alliance1_id') or 0)) if (a1.get('id') or t.get('alliance1_id')) else 0
                other = a2 if a1_id == int(alliance_id) else a1
                name = (other.get('name') or 'Unknown').strip()
                acr = (other.get('acronym') or '').strip()
                text = f"{name} ({acr})" if acr else name
                flag_url = (other.get('flag') or '').strip()
                
                tasks.append(self._fetch_flag_image(flag_url))
                texts.append(text)
            
            imgs = await asyncio.gather(*tasks) if tasks else []
            
            rows_data = list(zip(imgs, texts))
            
            return await asyncio.to_thread(self._generate_category_image_sync, rows_data, title, row_height)
        except Exception as e:
            self.logger.error(f"Error in _compose_category_image: {e}")
            return None

    async def _get_alliance_nations(self, alliance_id: int, force_refresh: bool = True) -> List[Dict[str, Any]]:
        """Use AllianceManager cog if available to fetch nations; otherwise return empty list."""
        try:
            alliance_cog = self.bot.get_cog('AllianceManager')
            if alliance_cog and hasattr(alliance_cog, 'get_alliance_nations'):
                # AllianceManager signature supports (alliance_id, force_refresh=True)
                nations_raw = await alliance_cog.get_alliance_nations(str(alliance_id), force_refresh=force_refresh)
                # Support both list and dict payloads
                if isinstance(nations_raw, dict):
                    nations_list = nations_raw.get('nations', []) or []
                else:
                    nations_list = nations_raw or []
                return nations_list
        except Exception as e:
            self.logger.error(f"Error fetching alliance nations for {alliance_id}: {e}")
        return []

    async def _get_combined_nations(self) -> List[Dict[str, Any]]:
        """Fetch nations from DB4D only."""
        cy = await self._get_alliance_nations(self.db4d_id, force_refresh=True)
        # AllianceManager returns nations for the specific alliance; no extra filter needed.
        return cy or []

    def _filter_active_members(self, nations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Exclude applicants and vacation mode for resource checks."""
        active = []
        for n in nations:
            pos = (n.get('alliance_position', '') or '').strip().upper()
            if pos == 'APPLICANT':
                continue
            vm = int(n.get('vacation_mode_turns', 0) or 0)
            if vm > 0:
                continue
            active.append(n)
        return active

    def _format_treaties_chunks_sync(self, treaties: List[Dict[str, Any]]) -> List[str]:
        """Format treaties into plain-text chunks under 2000 chars, grouped by type.
        - Shows all treaties
        - Suppresses link embeds via angle-bracketed URLs
        - No counts in headers, no repeated treaty type per item
        """
        # Default center to DB4D for plain-text output
        try:
            center_id = int(self.db4d_id)
        except Exception:
            center_id = 0
        categories = [
            ("Protectorate", emoji_mod.mention("Prot") or "Prot", "Protectorate"),
            ("Extension", emoji_mod.mention("Prot") or "Prot", "Extension"),
            ("MDoAP", emoji_mod.mention("MLevel") or "MLevel", "Mutual Defense / Optional Aggression (MDoAP)"),
            ("MDP", emoji_mod.mention("MLevel") or "MLevel", "Mutual Defense (MDP)"),
            ("ODoAP", emoji_mod.mention("OLevel") or "OLevel", "Optional Defense / Optional Aggression (ODoAP)"),
            ("ODP", emoji_mod.mention("OLevel") or "OLevel", "Optional Defense (ODP)"),
            ("PIAT", emoji_mod.mention("Peace") or "Peace", "Peace, Intelligence and Aid (PIAT)"),
            ("NAP", emoji_mod.mention("Peace") or "Peace", "Non-Aggression Pact (NAP)"),
        ]

        by_type: Dict[str, List[Dict[str, Any]]] = {}
        for t in treaties or []:
            ttype = self._normalize_treaty_type(t.get('treaty_type') or '')
            if not ttype:
                continue
            by_type.setdefault(ttype, []).append(t)

        # If no treaties, return a single message
        if not by_type:
            return ["No treaties found."]

        messages: List[str] = []
        current = ""
        max_len = 1900

        def add_line(line: str):
            nonlocal current, messages
            add = ("\n" if current else "") + line
            if len(current) + len(add) > max_len:
                if current:
                    messages.append(current)
                current = line
            else:
                current += add

        # Render categories
        for ttype, emoji, display in categories:
            items = by_type.get(ttype) or []
            filtered = items
            if not filtered:
                continue
            add_line(f"{emoji} {display}")
            for t in filtered:
                a1 = t.get('alliance1') or {}
                a2 = t.get('alliance2') or {}
                a1_id = int(str(a1.get('id') or t.get('alliance1_id') or 0)) if (a1.get('id') or t.get('alliance1_id')) else 0
                a2_id = int(str(a2.get('id') or t.get('alliance2_id') or 0)) if (a2.get('id') or t.get('alliance2_id')) else 0
                other = a2 if a1_id == center_id else a1
                other_name = (other.get('name') or 'Unknown').strip()
                other_acr = (other.get('acronym') or '').strip()
                other_disp = f"{other_name} ({other_acr})" if other_acr else other_name
                other_id = a2_id if a1_id == center_id else a1_id
                pnw_url = f"https://politicsandwar.com/alliance/id={other_id}" if other_id else ""
                if pnw_url:
                    add_line(f"  - [{other_disp}](<{pnw_url}>)")
                else:
                    add_line(f"  - {other_disp}")
            add_line("")


        if current:
            messages.append(current)
        return messages

    def _format_treaties_embed_sync(self, treaties: List[Dict[str, Any]], center_alliance_id: Optional[int] = None, center_name: Optional[str] = None) -> discord.Embed:
        """Format treaties into a rich Discord embed with proper categories and emojis.
        Uses regular URLs (not angle-bracketed) since embeds don't auto-expand links in embed fields.
        """
        # Determine center id and title
        try:
            center_id = int(center_alliance_id if center_alliance_id is not None else int(self.db4d_id))
        except Exception:
            center_id = int(self.db4d_id)

        title = "💀 DB4D Treaties 📜" if center_id == int(self.db4d_id) else f"{(center_name or 'Alliance').strip()} Treaties 📜"

        embed = discord.Embed(
            title=title,
            color=0x00ff00,  # Green color
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text="Last updated")

        # Attempt to set the embed image to DB4D's flag from treaty data
        try:
            cy_flag_url: Optional[str] = None
            for t in treaties or []:
                a1 = t.get('alliance1') or {}
                a2 = t.get('alliance2') or {}
                a1_id = int(str(a1.get('id') or t.get('alliance1_id') or 0)) if (a1.get('id') or t.get('alliance1_id')) else 0
                a2_id = int(str(a2.get('id') or t.get('alliance2_id') or 0)) if (a2.get('id') or t.get('alliance2_id')) else 0
                source = a1 if a1_id == center_id else (a2 if a2_id == center_id else None)
                if source:
                    flag_url = (source.get('flag') or '').strip()
                    if flag_url:
                        cy_flag_url = flag_url
                        break
            if cy_flag_url and len(cy_flag_url) < 1000:
                embed.set_image(url=cy_flag_url)
        except Exception:
            # Best-effort only; continue without image on failure
            pass

        # Build alliance-centric map of treaty types
        partners: Dict[int, Dict[str, Any]] = {}
        for t in treaties or []:
            a1 = t.get('alliance1') or {}
            a2 = t.get('alliance2') or {}
            a1_id = int(str(a1.get('id') or t.get('alliance1_id') or 0)) if (a1.get('id') or t.get('alliance1_id')) else 0
            a2_id = int(str(a2.get('id') or t.get('alliance2_id') or 0)) if (a2.get('id') or t.get('alliance2_id')) else 0
            other_id = a2_id if a1_id == center_id else a1_id
            other = a2 if a1_id == center_id else a1
            if other_id == 0:
                continue
            ttype = self._normalize_treaty_type(t.get('treaty_type') or '')
            info = partners.setdefault(other_id, {
                'id': other_id,
                'name': (other.get('name') or 'Unknown').strip(),
                'acr': (other.get('acronym') or '').strip(),
                'types': set(),
            })
            if ttype:
                info['types'].add(ttype)

        # Determine display category per alliance (matches rings)
        def pick_category(aid: int, types: set) -> Optional[str]:
            if ('Protectorate' in types) or ('Extension' in types):
                return 'Immediate'
            if ('MDoAP' in types) or ('MDP' in types):
                return 'M Level'
            if ('ODoAP' in types) or ('ODP' in types):
                return 'O Level'
            if ('PIAT' in types) or ('NAP' in types):
                return 'Peace'
            return None

        grouped: Dict[str, List[Dict[str, Any]]] = {k: [] for k in ['Immediate', 'M Level', 'O Level', 'Peace']}
        for aid, info in partners.items():
            cat = pick_category(aid, info.get('types') or set())
            if cat:
                grouped[cat].append(info)

        # Build formatted lines per category
        def build_lines(items: List[Dict[str, Any]]) -> List[str]:
            lines: List[str] = []
            for it in sorted(items, key=lambda x: (x.get('acr') or x.get('name') or '').lower()):
                disp = f"{it['name']}" + (f" {it['acr']}" if it.get('acr') else "")
                url = f"https://politicsandwar.com/alliance/id={it['id']}"
                lines.append(f"* [{disp}]({url})")
                for ttype in sorted(it.get('types') or []):
                    lines.append(f"  * {ttype}")
            return lines

        # Add fields in required order with emojis
        cat_emojis = {
            'Immediate': f"{emoji_mod.mention('Prot') or 'Prot'} Protection & Extensions",
            'M Level': f"{emoji_mod.mention('MLevel') or 'MLevel'} MDoAP & MDP",
            'O Level': f"{emoji_mod.mention('OLevel') or 'OLevel'} ODoAP & ODP",
            'Peace': f"{emoji_mod.mention('Peace') or 'Peace'} PIAT & NAP",
        }
        for cat in ['Immediate', 'M Level', 'O Level', 'Peace']:
            items = grouped.get(cat) or []
            if not items:
                continue
            lines = build_lines(items)
            # Chunk by 1024
            chunks: List[str] = []
            cur = ""
            for line in lines:
                add = ("\n" if cur else "") + line
                if len(cur) + len(add) > 1024:
                    if cur:
                        chunks.append(cur)
                    cur = line
                else:
                    cur += add
            if cur:
                chunks.append(cur)
            for i, chunk in enumerate(chunks):
                base = cat_emojis.get(cat, cat)
                name = f"{base} ({len(items)})" if i == 0 else f"{base} (cont.)"
                embed.add_field(name=name, value=chunk, inline=False)

        # If no treaties found, add a field indicating this
        if not embed.fields:
            embed.add_field(name="📭 No Treaties", value="No treaties found.", inline=False)

        return embed

    def _build_multi_field_values(self, items: List[Dict[str, Any]], with_days: bool = False, suffix_builder: Optional[Callable[[Dict[str, Any]], Optional[str]]] = None) -> List[str]:
        """Build multiple field values to show all nations, splitting across fields when needed.
        
        Returns a list of strings, each under 1024 characters, to display all nations
        across multiple embed fields if necessary.
        """
        try:
            if not items:
                return ["None"]

            links: List[str] = []
            for n in items:
                nid = n.get('nation_id') or n.get('id') or n.get('nationid')
                name = (n.get('nation_name') or n.get('name') or 'Unknown').strip()
                if not nid:
                    continue
                link = f"[{name}](https://politicsandwar.com/nation/id={nid})"
                if with_days:
                    d = _days_inactive(n)
                    if isinstance(d, int):
                        link = f"{link} ({d}d)"
                if suffix_builder is not None:
                    try:
                        suffix = suffix_builder(n)
                        if suffix:
                            link = f"{link} {suffix}"
                    except Exception:
                        pass
                links.append(link)

            links.sort(key=lambda x: x.lower())

            if not links:
                return ["None"]

            field_values = []
            current_value = ""
            
            for link in links:
                add = ("\n" if current_value else "") + link
                if len(current_value) + len(add) > 1024:
                    if current_value:
                        field_values.append(current_value)
                    current_value = link
                else:
                    current_value += add

            if current_value:
                field_values.append(current_value)
            
            return field_values if field_values else ["None"]
            
        except Exception:
            safe = [(_nation_link(n)) for n in items]
            text = "\n".join(safe)
            if len(text) <= 1024:
                return [text] if text else ["None"]
            
            chunks = []
            while text:
                if len(text) <= 1024:
                    chunks.append(text)
                    break
                split_pos = text.rfind('\n', 0, 1024)
                if split_pos == -1:
                    split_pos = 1024
                chunks.append(text[:split_pos])
                text = text[split_pos:].lstrip('\n')
            
            return chunks if chunks else ["None"]

    def _add_category_fields(self, embed: discord.Embed, category_name: str, emoji: str, items: List[Dict[str, Any]], with_days: bool = False, suffix_builder: Optional[Callable[[Dict[str, Any]], Optional[str]]] = None):
        """Add one or more fields for a category, splitting across multiple fields if needed."""
        field_values = self._build_multi_field_values(items, with_days=with_days, suffix_builder=suffix_builder)
        
        for i, value in enumerate(field_values):
            if len(field_values) == 1:
                field_name = f"{emoji} {category_name} ({len(items)})"
            else:
                field_name = f"{emoji} {category_name} ({len(items)}) - Part {i + 1}"
            
            embed.add_field(name=field_name, value=value, inline=False)

    def _chunk_lines(self, lines: List[str], max_len: int = 1024) -> List[str]:
        """Split a list of lines into chunks under Discord's field length limit."""
        chunks: List[str] = []
        current = ""
        for line in lines:
            add = ("\n" if current else "") + line
            if len(current) + len(add) > max_len:
                if current:
                    chunks.append(current)
                current = line
            else:
                current += add
        if current:
            chunks.append(current)
        return chunks or ["None"]

    def _format_treaty_line(self, t: Dict[str, Any], alliance_id: int) -> str:
        """Format a single treaty line with an angle-bracketed raw URL to suppress embeds."""
        try:
            a1 = t.get('alliance1') or {}
            a2 = t.get('alliance2') or {}
            a1_id = int(str(a1.get('id') or t.get('alliance1_id') or 0)) if (a1.get('id') or t.get('alliance1_id')) else 0
            a2_id = int(str(a2.get('id') or t.get('alliance2_id') or 0)) if (a2.get('id') or t.get('alliance2_id')) else 0
            other = a2 if a1_id == int(alliance_id) else a1
            other_name = (other.get('name') or 'Unknown').strip()
            other_acr = (other.get('acronym') or '').strip()
            other_disp = f"{other_name} ({other_acr})" if other_acr else other_name
            other_id = a2_id if a1_id == int(alliance_id) else a1_id
            name_link = f"[{other_disp}](<https://politicsandwar.com/alliance/id={other_id}>)" if other_id else other_disp

            return name_link
        except Exception:
            return str(t)

    def _audit_mmr_sync(self, active_members: List[Dict[str, Any]], mmr_mode: str) -> discord.Embed:
        if (mmr_mode or "basic") == "max":
            thresh = {"barracks": 5.0, "factory": 5.0, "air": 5.0, "drydock": 3.0}
            title = "⚙️ MMR Build Audit — Max"
            note = "Shows ALL nations below 5/5/5/3 per-city average."
        else:
            thresh = {"barracks": 0.0, "factory": 2.0, "air": 5.0, "drydock": 1.0}
            title = "⚙️ MMR Build Audit — Basic"
            note = "Shows nations below minimum 0/2/5/1 per-city average (more is fine)."
        EPSILON = 0.05

        def compute_mmr_avgs(n: Dict[str, Any]) -> Dict[str, float]:
            cities = n.get("cities") or []
            num = len(cities) if isinstance(cities, list) else (n.get("num_cities") or 0)
            if not num:
                return {"barracks": 0.0, "factory": 0.0, "air": 0.0, "drydock": 0.0, "num": 0,
                        "b_total": 0, "f_total": 0, "a_total": 0, "d_total": 0}
            b = f = a = d = 0
            for c in cities or []:
                if not isinstance(c, dict):
                    continue
                b += c.get("barracks", 0) or 0
                f += c.get("factory", 0) or 0
                a += (c.get("airforcebase", 0) or c.get("hangar", 0) or 0)
                d += c.get("drydock", 0) or 0
            return {
                "barracks": b / float(num),
                "factory": f / float(num),
                "air": a / float(num),
                "drydock": d / float(num),
                "num": float(num),
                "b_total": int(b),
                "f_total": int(f),
                "a_total": int(a),
                "d_total": int(d),
            }

        def _normalize_avgs(avg: Dict[str, float]) -> Dict[str, float]:
            return {
                "barracks": round(float(avg.get("barracks", 0.0) or 0.0), 1),
                "factory": round(float(avg.get("factory", 0.0) or 0.0), 1),
                "air": round(float(avg.get("air", 0.0) or 0.0), 1),
                "drydock": round(float(avg.get("drydock", 0.0) or 0.0), 1),
                "num": float(avg.get("num", 0.0) or 0.0),
            }

        def below_threshold(avg: Dict[str, float]) -> bool:
            navg = _normalize_avgs(avg)
            def is_below(key: str) -> bool:
                t = float(thresh.get(key, 0.0) or 0.0)
                a = float(navg.get(key, 0.0) or 0.0)
                if t <= 0:
                    return False
                return (a + EPSILON) < t
            return any(is_below(k) for k in ("barracks", "factory", "air", "drydock"))

        def compute_percent_off(avg: Dict[str, float], thr: Dict[str, float]) -> float:
            keys = ("barracks", "factory", "air", "drydock")
            total_thr = sum(v for k, v in thr.items() if k in keys and v > 0)
            if total_thr <= 0:
                return 0.0
            navg = _normalize_avgs(avg)
            deficit_sum = 0.0
            for k in keys:
                t = float(thr.get(k, 0.0) or 0.0)
                a = float(navg.get(k, 0.0) or 0.0)
                if t > 0 and (a + EPSILON) < t:
                    deficit_sum += (t - a)
            return max(0.0, min(100.0, (deficit_sum / total_thr) * 100.0))

        bucket_50_plus: List[Dict[str, Any]] = []  
        bucket_25_49: List[Dict[str, Any]] = []   
        bucket_10_24: List[Dict[str, Any]] = []   
        bucket_0_9: List[Dict[str, Any]] = []    

        for n in active_members:
            avg = compute_mmr_avgs(n)
            if avg["num"] <= 0:
                continue
            if below_threshold(avg):
                perc = compute_percent_off(avg, thresh)
                mmr_str = f"{avg['barracks']:.1f}/{avg['factory']:.1f}/{avg['air']:.1f}/{avg['drydock']:.1f}"
                try:
                    num_cities = int(round(float(avg.get("num", 0) or 0)))
                except Exception:
                    num_cities = 0
                totals_map = {
                    "barracks": int(round((thresh.get("barracks", 0) or 0) * num_cities)),
                    "factory": int(round((thresh.get("factory", 0) or 0) * num_cities)),
                    "air": int(round((thresh.get("air", 0) or 0) * num_cities)),
                    "drydock": int(round((thresh.get("drydock", 0) or 0) * num_cities)),
                }
                current_totals = {
                    "barracks": int(avg.get("b_total", 0) or 0),
                    "factory": int(avg.get("f_total", 0) or 0),
                    "air": int(avg.get("a_total", 0) or 0),
                    "drydock": int(avg.get("d_total", 0) or 0),
                }
                navg = {
                    "barracks": round(float(avg.get("barracks", 0.0) or 0.0), 1),
                    "factory": round(float(avg.get("factory", 0.0) or 0.0), 1),
                    "air": round(float(avg.get("air", 0.0) or 0.0), 1),
                    "drydock": round(float(avg.get("drydock", 0.0) or 0.0), 1),
                }
                below_keys = []
                for k in ("barracks", "factory", "air", "drydock"):
                    tval = float(thresh.get(k, 0.0) or 0.0)
                    aval = float(navg.get(k, 0.0) or 0.0)
                    if tval > 0 and (aval + EPSILON) < tval:
                        below_keys.append(k)
                enriched = dict(n)
                enriched["__mmr_avg"] = avg
                enriched["__mmr_percent_off"] = perc
                enriched["__mmr_str"] = mmr_str
                enriched["__mmr_totals"] = totals_map
                enriched["__mmr_current_totals"] = current_totals
                enriched["__mmr_below_keys"] = below_keys
                if perc >= 50.0:
                    bucket_50_plus.append(enriched)
                elif perc >= 25.0:
                    bucket_25_49.append(enriched)
                elif perc >= 10.0:
                    bucket_10_24.append(enriched)
                else:
                    bucket_0_9.append(enriched)

        embed = discord.Embed(
            title=title,
            description=note,
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        def suffix_builder(nation: Dict[str, Any]) -> Optional[str]:
            try:
                totals = nation.get("__mmr_totals", {}) or {}
                current = nation.get("__mmr_current_totals", {}) or {}
                avg = nation.get("__mmr_avg", {}) or {}
                mode_label = "Max" if (mmr_mode or "basic") == "max" else "Basic"
                mmr_s = str(nation.get("__mmr_str", ""))
                navg = {
                    "barracks": round(float(avg.get("barracks", 0.0) or 0.0), 1),
                    "factory": round(float(avg.get("factory", 0.0) or 0.0), 1),
                    "air": round(float(avg.get("air", 0.0) or 0.0), 1),
                    "drydock": round(float(avg.get("drydock", 0.0) or 0.0), 1),
                }
                def need_for(key: str) -> int:
                    t = float(thresh.get(key, 0.0) or 0.0)
                    a = float(navg.get(key, 0.0) or 0.0)
                    if t <= 0:
                        return 0
                    if (a + EPSILON) >= t:
                        return 0
                    required_total = int(round(t * float(avg.get("num", 0.0) or 0.0)))
                    current_total = int(current.get(key, 0) or 0)
                    return max(0, required_total - current_total)

                need_b = need_for("barracks")
                need_f = need_for("factory")
                need_a = need_for("air")
                need_d = need_for("drydock")
                needed_str = f"{need_b}/{need_f}/{need_a}/{need_d}"
                return f" - {mmr_s}\n   * Target {mode_label}: {needed_str}"
            except Exception:
                return None

        total_offenders = (
            len(bucket_50_plus) + len(bucket_25_49) + len(bucket_10_24) + len(bucket_0_9)
        )

        if total_offenders == 0:
            embed.add_field(name="Members Below Threshold", value="✅ All members meet the threshold.", inline=False)
        else:
            # Use emojis to signal severity
            self._add_category_fields(embed, "50%+ off", "🟥", bucket_50_plus, suffix_builder=suffix_builder)
            self._add_category_fields(embed, "25–49% off", "🟧", bucket_25_49, suffix_builder=suffix_builder)
            self._add_category_fields(embed, "10–24% off", "🟨", bucket_10_24, suffix_builder=suffix_builder)
            self._add_category_fields(embed, "0–9% off", "🟩", bucket_0_9, suffix_builder=suffix_builder)

        embed.set_footer(text=f"Active members checked: {len(active_members)} • Offenders: {total_offenders}")
        return embed

    @app_commands.describe(
        view="Select what to display: Food & Uranium, Inactives, Color, or MMR Build",
        mmr_mode="If MMR Build is selected, choose Basic or Max"
    )
    @app_commands.choices(view=[
        app_commands.Choice(name="Food & Uranium", value="resources"),
        app_commands.Choice(name="Inactives", value="inactives"),
        app_commands.Choice(name="Color", value="color"),
        app_commands.Choice(name="MMR Build", value="mmr"),
    ])
    @app_commands.autocomplete(mmr_mode=_mmr_mode_autocomplete)
    @commands.hybrid_command(name="audit", description="Audit alliance issues for DB4D")
    async def audit_command(self, ctx: commands.Context, view: Literal["resources", "inactives", "color", "mmr"], mmr_mode: Optional[Literal["basic", "max"]] = "basic"):

        """Generate an "Audit Issues" embed listing issue categories as nation links."""
        try:
            try:
                if hasattr(ctx, 'interaction') and ctx.interaction and not ctx.interaction.response.is_done():
                    await ctx.interaction.response.defer()
            except Exception:
                pass

            try:
                alliance_cog = self.bot.get_cog('AllianceManager')
                if alliance_cog and hasattr(alliance_cog, 'query_system') and getattr(alliance_cog, 'query_system', None):
                    await alliance_cog.query_system.get_alliance_nations(
                        str(self.db4d_id),
                        bot=self.bot,
                        force_refresh=True
                    )
                elif alliance_cog and hasattr(alliance_cog, 'get_alliance_nations'):
                    await alliance_cog.get_alliance_nations(str(self.db4d_id), force_refresh=True)
            except Exception as e:
                self.logger.warning(f"Pre-refresh before /audit failed: {e}")

            nations = await self._get_combined_nations()
            if not nations:
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.interaction.followup.send("❌ No alliance data found for DB4D.")
                else:
                    await ctx.reply("❌ No alliance data found for DB4D.")
                return

            active_members = self._filter_active_members(nations)

            # New: MMR Build audit
            if view == "mmr":
                try:
                    embed = await asyncio.to_thread(self._audit_mmr_sync, active_members, mmr_mode)
                    
                    if hasattr(ctx, 'interaction') and ctx.interaction:
                        await ctx.interaction.followup.send(embed=embed)
                    else:
                        await ctx.reply(embed=embed)
                    return
                except Exception as mmr_err:
                    self.logger.error(f"MMR audit error: {mmr_err}")
                    embed = discord.Embed(
                        title="❌ MMR Audit Error",
                        description=f"An error occurred during MMR calculation: {mmr_err}",
                        color=discord.Color.red()
                    )
                    if hasattr(ctx, 'interaction') and ctx.interaction:
                        await ctx.interaction.followup.send(embed=embed)
                    else:
                        await ctx.reply(embed=embed)
                    return
            food_lt_10k = [n for n in active_members if 0 < (n.get('food', 0) or 0) < 50000]
            uran_lt_500 = [n for n in active_members if 0 < (n.get('uranium', 0) or 0) < 1000]
            food_zero = [n for n in active_members if (n.get('food', 0) or 0) == 0]
            uran_zero = [n for n in active_members if (n.get('uranium', 0) or 0) == 0]
            beige = [n for n in active_members if (n.get('color', '') or '').strip().upper() == 'BEIGE']
            grey = [n for n in active_members if (n.get('color', '') or '').strip().upper() in ('GREY', 'GRAY')]
            wrong_color = [
                n for n in active_members
                if (n.get('color', '') or '').strip().upper() not in ('LIME', 'GREY', 'GRAY', 'BEIGE')
            ]

            inactive_7_to_13: List[Dict[str, Any]] = []
            inactive_14_to_23: List[Dict[str, Any]] = []
            inactive_24_plus: List[Dict[str, Any]] = []
            for n in active_members:
                d = _days_inactive(n)
                if isinstance(d, int):
                    if 7 <= d <= 13:
                        inactive_7_to_13.append(n)
                    elif 14 <= d <= 23:
                        inactive_14_to_23.append(n)
                    elif d >= 24:
                        inactive_24_plus.append(n)

            embed = discord.Embed(
                title="🧮 Audit Issues",
                description="Irregularities in the DB4D alliance.",
                color=discord.Color.orange()
            )

            view_key = view

            if view_key == "resources":
                self._add_category_fields(
                    embed,
                    "Food < 50,000",
                    "🍞",
                    food_lt_10k,
                    suffix_builder=lambda n: f"- {int(n.get('food', 0)):,}"
                )
                self._add_category_fields(
                    embed,
                    "Uranium < 1,000",
                    "☢️",
                    uran_lt_500,
                    suffix_builder=lambda n: f"- {int(n.get('uranium', 0)):,}"
                )
                self._add_category_fields(embed, "Food = 0", "🚫", food_zero)
                self._add_category_fields(embed, "Uranium = 0", "🚫", uran_zero)
            elif view_key == "inactives":
                self._add_category_fields(embed, "Inactive 7-13 days", "⏲️", inactive_7_to_13, with_days=True)
                self._add_category_fields(embed, "Inactive 14-23 days", "⚠️", inactive_14_to_23, with_days=True)
                self._add_category_fields(embed, "Inactive 24+ days", "🛑", inactive_24_plus, with_days=True)
            elif view_key == "color":
                self._add_category_fields(embed, "Beige", "🩼", beige)
                self._add_category_fields(embed, "Grey", "⚪", grey)
                self._add_category_fields(embed, "Wrong Color", "🎨", wrong_color)

            embed.set_footer(text=f"Generated at {datetime.now().strftime('%H:%M:%S')} | Excludes APPLICANTS and Vacation Mode")

            if hasattr(ctx, 'interaction') and ctx.interaction:
                await ctx.interaction.followup.send(embed=embed)
            else:
                await ctx.reply(embed=embed)
        except Exception as e:
            self.logger.error(f"/audit error: {e}")
            try:
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.interaction.followup.send(f"❌ An error occurred: {str(e)}")
                else:
                    await ctx.reply(f"❌ An error occurred: {str(e)}")
            except Exception:
                pass

    @commands.hybrid_command(name="treaties", description="Show treaties and treaty web for any alliance")
    @app_commands.describe(alliance="Alliance name or ID (optional)")
    async def treaties_command(self, ctx: commands.Context, alliance: Optional[str] = None):
        """Query alliance treaties and display them in a rich embed."""
        try:
            try:
                if hasattr(ctx, 'interaction') and ctx.interaction and not ctx.interaction.response.is_done():
                    await ctx.interaction.response.send_message("🔄 Refreshing treaties…", ephemeral=True, delete_after=1)
            except Exception:
                pass

            treaties: List[Dict[str, Any]] = []
            center_id: Optional[int] = None
            center_name: Optional[str] = None
            try:
                alliance_cog = self.bot.get_cog('AllianceManager')
                if alliance_cog and hasattr(alliance_cog, 'query_system') and alliance_cog.query_system:
                    arg = (alliance or "").strip()
                    if arg:
                        resolved = await alliance_cog.query_system.resolve_alliance(arg)
                        try:
                            if resolved and isinstance(resolved, dict) and resolved.get('id'):
                                center_id = int(str(resolved.get('id')))
                                center_name = (resolved.get('name') or '').strip() or None
                            elif arg.isdigit():
                                center_id = int(arg)
                            else:
                                center_id = None
                        except Exception:
                            center_id = None

                        if not center_id or int(center_id) <= 0:
                            msg = "❌ Could not resolve alliance. Enter a valid name or ID."
                            if hasattr(ctx, 'interaction') and ctx.interaction:
                                await ctx.interaction.followup.send(msg)
                            else:
                                await ctx.reply(msg)
                            return
                    else:
                        try:
                            center_id = int(self.db4d_id)
                        except Exception:
                            center_id = self.db4d_id
                        center_name = "Death Before Dishonor"

                    res = await alliance_cog.query_system.get_alliance_treaties(str(center_id), force_refresh=True)
                    treaties = res or []
                else:
                    treaties = []
            except Exception as qerr:
                self.logger.error(f"Error querying treaties: {qerr}")

            treaty_file = await self._compose_treaty_web_image(treaties, center_alliance_id=center_id or 0)
            embed = await asyncio.to_thread(self._format_treaties_embed_sync, treaties, center_id or 0, center_name)
            files: List[discord.File] = []
            if treaty_file:
                embed.set_image(url=f"attachment://{treaty_file.filename}")
                files = [treaty_file]

            view = None
            if center_id and int(center_id) == int(self.db4d_id):
                view = TreatiesRefreshView(self, center_id)

            try:
                channel_id = getattr(getattr(ctx, 'channel', None), 'id', None)
                has_new_file = bool(files)
                edited = False
                if channel_id and channel_id in self.treaties_message_map:
                    try:
                        last_msg_id = self.treaties_message_map[channel_id]
                        last_msg = await ctx.channel.fetch_message(last_msg_id)
                        if not has_new_file:
                            await last_msg.edit(embed=embed, view=view, attachments=list(last_msg.attachments))
                            edited = True
                        else:
                            edited = False
                    except Exception:
                        edited = False
                if not edited:
                    sent = await ctx.send(embed=embed, view=view, files=files if files else [])
                    try:
                        if channel_id:
                            self.treaties_message_map[channel_id] = sent.id
                    except Exception:
                        pass

                try:
                    if hasattr(ctx, 'interaction') and ctx.interaction:
                        try:
                            await ctx.interaction.delete_original_response()
                        except Exception:
                            try:
                                await ctx.interaction.edit_original_response(content="", embed=None, view=None, attachments=[])
                            except Exception:
                                pass
                except Exception:
                    pass
            except Exception as send_error:
                self.logger.error(f"Error sending treaties embed: {send_error}")
                fallback_embed = discord.Embed(
                    title="❌ Error Loading Treaties",
                    description="An error occurred while loading treaty information.",
                    color=0xff0000
                )
                try:
                    if hasattr(ctx, 'interaction') and ctx.interaction:
                        await ctx.interaction.edit_original_response(embed=fallback_embed)
                    else:
                        await ctx.send(embed=fallback_embed)
                except Exception:
                    pass

        except Exception as e:
            self.logger.error(f"/treaties error: {e}")
            try:
                error_embed = discord.Embed(
                    title="❌ An error occurred",
                    description=str(e),
                    color=0xff0000
                )
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    try:
                        await ctx.interaction.edit_original_response(content="", embed=None, view=None, attachments=[])
                    except Exception:
                        pass
                    await ctx.interaction.followup.send(embed=error_embed)
                else:
                    await ctx.reply(embed=error_embed)
            except Exception:
                pass

class TreatiesRefreshView(discord.ui.View):
    def __init__(self, cog: AuditManager, alliance_id: int, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.alliance_id = alliance_id

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.primary, custom_id="treaties_refresh")
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
        except Exception:
            pass
        try:
            treaties: List[Dict[str, Any]] = []
            try:
                alliance_cog = self.cog.bot.get_cog('AllianceManager')
                if alliance_cog and hasattr(alliance_cog, 'query_system') and alliance_cog.query_system:
                    res = await alliance_cog.query_system.get_alliance_treaties(str(self.alliance_id), force_refresh=True)
                    treaties = res or []
            except Exception as qerr:
                self.cog.logger.error(f"Refresh treaties query error: {qerr}")

            treaty_file = await self.cog._compose_treaty_web_image(treaties, center_alliance_id=int(self.alliance_id))
            embed = self.cog._format_treaties_embed(treaties, center_alliance_id=int(self.alliance_id))
            files: List[discord.File] = []
            if treaty_file:
                embed.set_image(url=f"attachment://{treaty_file.filename}")
                files = [treaty_file]

            new_view = TreatiesRefreshView(self.cog, int(self.alliance_id), timeout=None)
            try:
                try:
                    await interaction.message.delete()
                except Exception as del_err:
                    self.cog.logger.error(f"TreatiesRefreshView: delete failed: {del_err}")
                new_msg = await interaction.channel.send(embed=embed, view=new_view, files=files if files else [])
                try:
                    self.cog.treaties_message_map[getattr(interaction.channel, 'id', 0)] = getattr(new_msg, 'id', 0)
                except Exception:
                    pass
            except Exception:
                try:
                    await interaction.message.edit(embed=embed, view=new_view)
                except Exception:
                    try:
                        await interaction.edit_original_response(embed=embed, view=new_view)
                    except Exception:
                        pass
        except Exception as e:
            try:
                error_embed = discord.Embed(
                    title="❌ Refresh Failed",
                    description=f"Error: {str(e)}",
                    color=0xFF0000
                )
                await interaction.followup.send(embed=error_embed, ephemeral=True)
            except Exception:
                pass

async def setup(bot: commands.Bot):
    audit = AuditManager(bot)
    await bot.add_cog(audit)
    try:
        bot.add_view(TreatiesRefreshView(audit, audit.db4d_id, timeout=None))
    except Exception:
        pass
