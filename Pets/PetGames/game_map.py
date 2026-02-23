import random
import math
import os
import json
from typing import Dict, List, Any, Tuple, Optional, cast, Union, TYPE_CHECKING
from io import BytesIO

if TYPE_CHECKING:
    # These imports are only for type checking purposes
    from PIL import Image as _ImageModule, ImageDraw as _ImageDrawModule, ImageFont as _ImageFontModule, ImageChops as _ImageChopsModule, ImageFilter as _ImageFilterModule
    Image = _ImageModule
    ImageDraw = _ImageDrawModule
    ImageFont = _ImageFontModule
    ImageChops = _ImageChopsModule
    ImageFilter = _ImageFilterModule
else:
    # At runtime, these will be None if PIL is not available
    Image: Any = None
    ImageDraw: Any = None
    ImageFont: Any = None
    ImageChops: Any = None
    ImageFilter: Any = None

PIL_AVAILABLE: bool

try:
    from PIL import Image as _Image, ImageDraw as _ImageDraw, ImageFont as _ImageFont, ImageChops as _ImageChops, ImageFilter as _ImageFilter
    Image = _Image
    ImageDraw = _ImageDraw
    ImageFont = _ImageFont
    ImageChops = _ImageChops
    ImageFilter = _ImageFilter
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class GameMap:
    _locations_data: Optional[Dict[str, Any]] = None

    @classmethod
    def load_static_data(cls):
        if cls._locations_data is not None:
            return
        try:
            base_dir = os.path.dirname(__file__)
            fp = os.path.join(base_dir, 'Locations', 'locations_base.json')
            with open(fp, 'r', encoding='utf-8') as f:
                cls._locations_data = json.load(f)
        except Exception:
            cls._locations_data = {}

    def __init__(self, color_palette: Dict[str, Tuple[int, int, int]], map_size: Tuple[int, int] = (1200, 800)):
        self.color_palette = color_palette
        self.style_order = [
            'water', 'basic', 'fire', 'electric', 'ice',
            'plant', 'rock', 'air', 'magic', 'holy', 'necro',
            'fighting', 'psychic'
        ]
        self.style_bg_colors = {
            'water': (120, 220, 200),
            'basic': (150, 150, 160),
            'fire': (128, 0, 32),
            'electric': (204, 173, 25),
            'ice': (245, 245, 250),
            'plant': (34, 139, 34),
            'rock': (195, 176, 145),
            'air': (135, 206, 235),
            'magic': (181, 126, 220),
            'holy': (212, 175, 55),
            'necro': (110, 110, 120),
            'fighting': (139, 0, 0),
            'psychic': (148, 0, 211)
        }
        
        if GameMap._locations_data is None:
            GameMap.load_static_data()
            
        data = GameMap._locations_data or {}
        self.style_categories = data.get('conventions', {}).get('style_categories', {})
        
        if not self.style_categories:
            self.style_categories = {
                'basic': 'Neutral Grounds',
                'fire': 'Emberlands',
                'water': 'Tideways',
                'electric': 'Stormfields',
                'ice': 'Frostreach',
                'plant': 'Verdant Wilds',
                'rock': 'Stone Marches',
                'air': 'Skylands',
                'magic': 'Arcane Vale',
                'holy': 'Sanctified Plains',
                'necro': 'Shadow Wastes',
                'fighting': 'Battlegrounds',
                'psychic': 'Mindscapes'
            }
        self.map_size = map_size
        self.map_margin = 40
        self.border_inset = 20
        self.style_zones = self._compute_style_zones()
        self.style_patches = self._compute_style_patches()
        w, h = self.map_size
        self.globe_rect = (self.map_margin, self.map_margin, w - self.map_margin, h - self.map_margin)
        self._emoji_cache: Dict[Tuple[str, int], Optional[Image.Image]] = {}
        self._emoji_font_cache: Dict[int, Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]] = {}

    def _compute_style_zones(self) -> Dict[str, Tuple[int, int, int, int]]:
        width, height = self.map_size
        margin = self.map_margin
        cx = width // 2
        cy = height // 2
        band = int(min(width, height) * 0.18)
        zones: Dict[str, Tuple[int, int, int, int]] = {}
        zones['basic'] = (margin, margin, cx - band // 2, height - margin)
        zones['fire'] = (cx + band // 2, margin, width - margin, height - margin)
        zones['air'] = (margin, margin, width - margin, cy - band // 2)
        zones['water'] = (margin, cy + band // 2, width - margin, height - margin)
        zones['magic'] = (cx - band // 2, cy - band // 2, cx + band // 2, cy + band // 2)
        zones['electric'] = (margin, margin, width - margin, height - margin)
        zones['ice'] = (margin, margin, width - margin, height - margin)
        zones['plant'] = (margin, margin, width - margin, height - margin)
        zones['rock'] = (margin, margin, width - margin, height - margin)
        zones['holy'] = (margin, margin, width - margin, height - margin)
        zones['necro'] = (margin, margin, width - margin, height - margin)
        zones['fighting'] = (margin, margin, width - margin, height - margin)
        zones['psychic'] = (margin, margin, width - margin, height - margin)
        return zones

    def _organic_blob(self, cx, cy, rx, ry, points=10, spread=8, rng=None):
        if rng is None:
            rng = random
        poly = []
        for i in range(points):
            ang = 2 * math.pi * i / points
            radx = rx + rng.randint(-spread, spread)
            rady = ry + rng.randint(-spread, spread)
            x = int(cx + math.cos(ang) * radx)
            y = int(cy + math.sin(ang) * rady)
            poly.append((x, y))
        return poly

    def _compute_style_patches(self, seed: Optional[int] = None) -> Dict[str, List[List[Tuple[int, int]]]]:
        w, h = self.map_size
        rng = random.Random(seed) if seed is not None else random
        patches: Dict[str, List[List[Tuple[int, int]]]] = {}

        def rand_in_rect(rect: Tuple[int, int, int, int]) -> Tuple[int, int]:
            x0, y0, x1, y1 = rect
            return rng.randint(x0 + 20, x1 - 20), rng.randint(y0 + 20, y1 - 20)

        counts = {
            'water': rng.randint(16, 22),
            'basic': rng.randint(18, 26),
            'fire': rng.randint(12, 18),
            'electric': rng.randint(12, 18),
            'ice': rng.randint(14, 20),
            'plant': rng.randint(14, 20),
            'rock': rng.randint(14, 22),
            'air': rng.randint(12, 18),
            'magic': rng.randint(14, 20),
            'holy': rng.randint(12, 18),
            'necro': rng.randint(12, 18),
            'fighting': rng.randint(12, 18),
            'psychic': rng.randint(12, 18)
        }

        for style in self.style_order:
            rect = self.style_zones.get(style, (self.map_margin, self.map_margin, w - self.map_margin, h - self.map_margin))
            arr: List[List[Tuple[int, int]]] = []
            for _ in range(counts[style]):
                px, py = rand_in_rect(rect)
                size_w = rng.uniform(w * 0.035, w * 0.085)
                size_h = rng.uniform(h * 0.028, h * 0.072)
                pts = rng.randint(10, 20)
                spread = rng.randint(6, 16)
                arr.append(self._organic_blob(px, py, size_w, size_h, points=pts, spread=spread, rng=rng))
            patches[style] = arr

        return patches

    def _ellipse_mask(self) -> Image.Image:
        key = (self.map_size, self.globe_rect)
        if getattr(self, '_ellipse_mask_cache_key', None) == key:
            cached = getattr(self, '_ellipse_mask_cache_img', None)
            if cached is not None:
                return cached
        m = Image.new('L', self.map_size, 0)
        d = ImageDraw.Draw(m)
        d.rectangle(self.globe_rect, fill=255)
        self._ellipse_mask_cache_key = key
        self._ellipse_mask_cache_img = m
        return m

    def _globe_params(self) -> Tuple[float, float, float, float]:
        x0, y0, x1, y1 = self.globe_rect
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        rx = (x1 - x0) / 2.0
        ry = (y1 - y0) / 2.0
        return cx, cy, rx, ry

    def _inside_globe_point(self, x: int, y: int, margin: float = 0.0) -> bool:
        x0, y0, x1, y1 = self.globe_rect
        rx = (x1 - x0) / 2.0
        ry = (y1 - y0) / 2.0
        mx = int(rx * margin)
        my = int(ry * margin)
        return (x0 + mx) <= x <= (x1 - mx) and (y0 + my) <= y <= (y1 - my)


    def _fractalize_polygon(self, poly: List[Tuple[int, int]], iters: int = 3, disp_factor: float = 0.2, rng: Any = None) -> List[Tuple[int, int]]:
        if rng is None:
            rng = random
        for _ in range(iters):
            new_poly = []
            n = len(poly)
            for i in range(n):
                x1, y1 = poly[i]
                x2, y2 = poly[(i + 1) % n]
                midx = (x1 + x2) / 2
                midy = (y1 + y2) / 2
                dx = x2 - x1
                dy = y2 - y1
                length = math.sqrt(dx**2 + dy**2)
                if length == 0:
                    offset = 0
                else:
                    offset = rng.uniform(-disp_factor, disp_factor) * length
                    perp_dx = -dy / length
                    perp_dy = dx / length
                newx = midx + offset * perp_dx
                newy = midy + offset * perp_dy
                new_poly.append((x1, y1))
                new_poly.append((int(newx), int(newy)))
            poly = new_poly
        return poly

    def _rotate_polygon(self, poly: List[Tuple[int, int]], angle: float, cx: float, cy: float) -> List[Tuple[int, int]]:
        ca = math.cos(angle)
        sa = math.sin(angle)
        return [
            (
                int(cx + ca * (x - cx) - sa * (y - cy)),
                int(cy + sa * (x - cx) + ca * (y - cy))
            )
            for x, y in poly
        ]

    def _scale_polygon(self, poly: List[Tuple[int, int]], factor: float) -> List[Tuple[int, int]]:
        if not poly:
            return poly
        cx = sum(x for x, _ in poly) / len(poly)
        cy = sum(y for _, y in poly) / len(poly)
        out: List[Tuple[int, int]] = []
        for x, y in poly:
            dx = x - cx
            dy = y - cy
            out.append((int(cx + dx * factor), int(cy + dy * factor)))
        return out


    def _generate_continents(self, seed: Optional[int] = None, styles_required: Optional[List[str]] = None) -> Dict[str, List[List[Tuple[int, int]]]]:
        w, h = self.map_size
        rng = random.Random(seed) if seed is not None else random
        land_styles = [s for s in self.style_order if s != 'water']
        if styles_required:
            styles_required = [s for s in styles_required if s in land_styles]
        target_styles = styles_required if styles_required else land_styles
        x0, y0, x1, y1 = self.globe_rect
        gx, gy, grx, gry = self._globe_params()
        polys: List[List[Tuple[int, int]]] = []
        num_continents = max(len(target_styles), rng.randint(len(target_styles), len(target_styles) + 3))
        for _ in range(num_continents):
            cx = rng.randint(int(gx - grx * 0.9), int(gx + grx * 0.9))
            cy = rng.randint(int(gy - gry * 0.9), int(gy + gry * 0.9))
            rx = w * rng.uniform(0.08, 0.35)
            ry = h * rng.uniform(0.08, 0.35)
            poly = self._organic_blob(cx, cy, rx, ry, points=rng.randint(12, 24), spread=rng.randint(20, 40), rng=rng)
            poly = self._fractalize_polygon(poly, iters=2, disp_factor=0.2, rng=rng)
            # Calculate centroid for rotation
            cent_x = sum(x for x, _ in poly) / len(poly)
            cent_y = sum(y for _, y in poly) / len(poly)
            angle = rng.uniform(0, 2 * math.pi)
            poly = self._rotate_polygon(poly, angle, cent_x, cent_y)
            scale = rng.uniform(0.8, 1.3)
            poly = self._scale_polygon(poly, scale)
            poly = self._chaikin_smooth(poly, iters=3)
            polys.append(poly)
        for _ in range(24):
            changed = False
            for i in range(len(polys)):
                for j in range(i + 1, len(polys)):
                    if self._polygons_overlap(polys[i], polys[j]):
                        cxi, cyi = self._poly_centroid(polys[i])
                        cxj, cyj = self._poly_centroid(polys[j])
                        vx = cxi - cxj
                        vy = cyi - cyj
                        mag = max(1.0, (vx * vx + vy * vy) ** 0.5)
                        push = max(10.0, min(60.0, mag * 0.25))
                        dx = (vx / mag) * push
                        dy = (vy / mag) * push
                        polys[i] = self._displace_polygon(polys[i], dx, dy)
                        polys[j] = self._displace_polygon(polys[j], -dx, -dy)
                        changed = True
            if not changed:
                break
        for _ in range(8):
            any_overlap = False
            for i in range(len(polys)):
                for j in range(i + 1, len(polys)):
                    if self._polygons_overlap(polys[i], polys[j]):
                        any_overlap = True
                        cxi, cyi = self._poly_centroid(polys[i])
                        cxj, cyj = self._poly_centroid(polys[j])
                        vx = cxi - cxj
                        vy = cyi - cyj
                        mag = max(1.0, (vx * vx + vy * vy) ** 0.5)
                        dx = (vx / mag) * 8.0
                        dy = (vy / mag) * 8.0
                        polys[i] = self._displace_polygon(polys[i], dx, dy)
                        polys[j] = self._displace_polygon(polys[j], -dx, -dy)
            if not any_overlap:
                break
        land: Dict[str, List[List[Tuple[int, int]]]] = {s: [] for s in land_styles}
        while len(polys) < len(target_styles):
            cx = int(gx + rng.uniform(-grx * 0.9, grx * 0.9))
            cy = int(gy + rng.uniform(-gry * 0.9, gry * 0.9))
            rx = w * rng.uniform(0.08, 0.35)
            ry = h * rng.uniform(0.08, 0.35)
            p = self._organic_blob(cx, cy, rx, ry, points=rng.randint(12, 24), spread=rng.randint(20, 40), rng=rng)
            p = self._fractalize_polygon(p, iters=2, disp_factor=0.2, rng=rng)
            cent_x = sum(x for x, _ in p) / len(p)
            cent_y = sum(y for _, y in p) / len(p)
            angle = rng.uniform(0, 2 * math.pi)
            p = self._rotate_polygon(p, angle, cent_x, cent_y)
            scale = rng.uniform(0.8, 1.3)
            p = self._scale_polygon(p, scale)
            p = self._chaikin_smooth(p, iters=3)
            polys.append(p)
        rng.shuffle(polys)
        for i, poly in enumerate(polys[:len(target_styles)]):
            style = target_styles[i]
            land[style].append(poly)
        patches: Dict[str, List[List[Tuple[int, int]]]] = {s: land.get(s, []) for s in self.style_order}
        return patches

    def _point_in_polygon(self, x: int, y: int, poly: List[Tuple[int, int]]) -> bool:
        inside = False
        j = len(poly) - 1
        for i in range(len(poly)):
            xi, yi = poly[i]
            xj, yj = poly[j]
            if ((yi > y) != (yj > y)):
                x_intersect = (xj - xi) * (y - yi) / ((yj - yi) if (yj - yi) != 0 else 1e-9) + xi
                if x < x_intersect:
                    inside = not inside
            j = i
        return inside

    def random_point_in_style(self, style: str, max_tries: int = 80) -> Tuple[int, int]:
        polys = self.style_patches.get(style, [])
        if polys:
            for _ in range(max_tries):
                poly = random.choice(polys)
                xs = [p[0] for p in poly]
                ys = [p[1] for p in poly]
                minx = min(xs)
                maxx = max(xs)
                miny = min(ys)
                maxy = max(ys)
                x = random.randint(minx, maxx)
                y = random.randint(miny, maxy)
                if self._point_in_polygon(x, y, poly) and self._inside_globe_point(x, y):
                    return x, y
        # Fallback if no point found: sample a random land polygon
        land_styles = [s for s in self.style_order if s != 'water']
        for _ in range(max_tries):
            sty = random.choice(land_styles)
            polys = self.style_patches.get(sty, [])
            if not polys:
                continue
            poly = random.choice(polys)
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            minx = min(xs)
            maxx = max(xs)
            miny = min(ys)
            maxy = max(ys)
            x = random.randint(minx, maxx)
            y = random.randint(miny, maxy)
            if self._point_in_polygon(x, y, poly):
                return x, y
        cx, cy, _, _ = self._globe_params()
        return int(cx), int(cy)

    def scatter_around(self, center: Tuple[int, int], min_radius: int = 80, max_radius: int = 160) -> Tuple[int, int]:
        cx, cy = center
        for _ in range(60):
            ang = random.uniform(0.0, 2.0 * math.pi)
            rad = random.uniform(float(min_radius), float(max_radius))
            x = int(cx + rad * math.cos(ang))
            y = int(cy + rad * math.sin(ang))
            if self._inside_globe_point(x, y, margin=0.01):
                return x, y
        return int(cx), int(cy)

    def _polygons_overlap(self, poly1: List[Tuple[int, int]], poly2: List[Tuple[int, int]]) -> bool:
        if not poly1 or not poly2:
            return False
        xs1 = [p[0] for p in poly1]
        ys1 = [p[1] for p in poly1]
        xs2 = [p[0] for p in poly2]
        ys2 = [p[1] for p in poly2]
        minx1, maxx1 = min(xs1), max(xs1)
        miny1, maxy1 = min(ys1), max(ys1)
        minx2, maxx2 = min(xs2), max(xs2)
        miny2, maxy2 = min(ys2), max(ys2)
        if maxx1 < minx2 or maxx2 < minx1 or maxy1 < miny2 or maxy2 < miny1:
            return False
        def segs(poly: List[Tuple[int, int]]):
            n = len(poly)
            return [(poly[i], poly[(i + 1) % n]) for i in range(n)]
        def ccw(a, b, c):
            return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])
        def intersect(p1, p2, q1, q2):
            return ccw(p1, q1, q2) != ccw(p2, q1, q2) and ccw(p1, p2, q1) != ccw(p1, p2, q2)
        for e1 in segs(poly1):
            for e2 in segs(poly2):
                if intersect(e1[0], e1[1], e2[0], e2[1]):
                    return True
        for x, y in poly1:
            if self._point_in_polygon(x, y, poly2):
                return True
        for x, y in poly2:
            if self._point_in_polygon(x, y, poly1):
                return True
        return False

    def _poly_centroid(self, poly: List[Tuple[int, int]]) -> Tuple[float, float]:
        # Placeholder: assume defined
        cx = sum(x for x, _ in poly) / len(poly)
        cy = sum(y for _, y in poly) / len(poly)
        return cx, cy

    def _displace_polygon(self, poly: List[Tuple[int, int]], dx: float, dy: float) -> List[Tuple[int, int]]:
        # Placeholder: assume defined
        return [(int(x + dx), int(y + dy)) for x, y in poly]

    def _expand_polygon(self, poly: List[Tuple[int, int]], pad: int) -> List[Tuple[int, int]]:
        if not poly:
            return poly
        xs = [x for x, _ in poly]
        ys = [y for _, y in poly]
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span = max(1, max(max_x - min_x, max_y - min_y))
        scale = 1.0 + (float(pad) / float(span))
        out: List[Tuple[int, int]] = []
        for x, y in poly:
            nx = int(cx + (x - cx) * scale)
            ny = int(cy + (y - cy) * scale)
            out.append((nx, ny))
        return out

    def _lighten_color(self, col: Tuple[int, int, int], t: float) -> Tuple[int, int, int, int]:
        r = min(255, int(col[0] + (255 - col[0]) * t))
        g = min(255, int(col[1] + (255 - col[1]) * t))
        b = min(255, int(col[2] + (255 - col[2]) * t))
        return (r, g, b, 255)

    def _chaikin_smooth(self, pts: List[Tuple[int, int]], iters: int = 1) -> List[Tuple[int, int]]:
        # Placeholder for Chaikin smoothing algorithm
        for _ in range(iters):
            new_pts = []
            n = len(pts)
            for i in range(n):
                p0 = pts[i]
                p1 = pts[(i + 1) % n]
                q = (int(0.75 * p0[0] + 0.25 * p1[0]), int(0.75 * p0[1] + 0.25 * p1[1]))
                r = (int(0.25 * p0[0] + 0.75 * p1[0]), int(0.25 * p0[1] + 0.75 * p1[1]))
                new_pts.append(q)
                new_pts.append(r)
            pts = new_pts
        return pts

    def _render_terrain_base(self) -> Image.Image:
        img = Image.new('RGBA', self.map_size, (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        sea_color = self.style_bg_colors['water']
        base_col = (max(0,int(sea_color[0]*0.85)), max(0,int(sea_color[1]*0.85)), max(0,int(sea_color[2]*0.85)), 255)
        d.rectangle(self.globe_rect, fill=base_col)
        waves = Image.new('RGBA', self.map_size, (0,0,0,0))
        wd = ImageDraw.Draw(waves)
        x0, y0, x1, y1 = self.globe_rect
        dark = (max(0,int(sea_color[0]*0.6)), max(0,int(sea_color[1]*0.6)), max(0,int(sea_color[2]*0.6)), 100)
        bands = max(18, int((y1 - y0) // 24))
        for i in range(bands):
            yy = y0 + int((i + 0.5) * (y1 - y0) / bands)
            amp = max(3, int(0.02 * (y1 - y0))) + random.randint(-1, 2)
            freq = 0.02 + random.random() * 0.02
            phase = random.random() * 2 * math.pi
            step_x = 8
            pts: List[Tuple[int,int]] = []
            for x in range(x0, x1 + 1, step_x):
                y = yy + int(amp * math.sin((x - x0) * freq + phase))
                pts.append((x, y))
            wd.line(pts, fill=dark, width=3)
        if ImageFilter:
            waves = waves.filter(ImageFilter.GaussianBlur(1))
        rect_mask = Image.new('L', self.map_size, 0)
        md = ImageDraw.Draw(rect_mask)
        md.rectangle(self.globe_rect, fill=255)
        if ImageChops:
            wave_alpha = waves.split()[-1]
            wmask = ImageChops.multiply(wave_alpha, rect_mask)
        else:
            wmask = waves.split()[-1]
        img.paste(waves, (0,0), wmask)
        return img

    def _get_emoji_font(self, size: int) -> Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]:
        f = self._emoji_font_cache.get(size)
        if f:
            return f
        env_fp = os.getenv("ALLSPARK_EMOJI_FONT", "").strip()
        candidates: List[str] = []
        if env_fp:
            candidates.append(env_fp)
        candidates.extend([
            'C\\Windows\\Fonts\\seguiemj.ttf',
            'C\\Windows\\Fonts\\segoeui.ttf',
            'arial.ttf'
        ])
        for fp in candidates:
            try:
                f = ImageFont.truetype(fp, size)
                self._emoji_font_cache[size] = f
                return f
            except Exception:
                continue
        f = ImageFont.load_default()
        self._emoji_font_cache[size] = f
        return f

    def _emoji_stamp(self, em: str, size: int, font: Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]) -> Image.Image:
        bb = font.getbbox(em)
        w = int(max(8, bb[2] - bb[0]))
        h = int(max(8, bb[3] - bb[1]))
        stamp = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(stamp)
        try:
            d.text((0, 0), em, font=font, embedded_color=True)
        except Exception:
            d.text((0, 0), em, font=font, fill=(240, 240, 240, 255))
        return stamp

    def assign_locations(self, participants: List[Any], assignment: Dict[Any, str], pools: Any) -> Tuple[Dict[Any, Dict[str, Any]], Dict[Any, str]]:
        teams_map: Dict[str, List[Any]] = {}
        for p in participants:
            f = assignment.get(p, 'Neutral')
            teams_map.setdefault(f, []).append(p)
        non_neutral_teams = [f for f in teams_map.keys() if f != 'Neutral']
        land_styles = [s for s in self.style_order if s != 'water']
        cluster_styles: Dict[str, str] = {}
        if len(non_neutral_teams) <= len(land_styles):
            for i, f in enumerate(non_neutral_teams):
                cluster_styles[f] = land_styles[i]
        else:
            for i, f in enumerate(non_neutral_teams):
                cluster_styles[f] = land_styles[i % len(land_styles)]
        zone_center_slots: Dict[str, List[Tuple[int, int]]] = {}
        for style, rect in self.style_zones.items():
            x0, y0, x1, y1 = rect
            w = x1 - x0
            h = y1 - y0
            cx1 = x0 + w // 4
            cx2 = x0 + w // 2
            cx3 = x0 + (3 * w) // 4
            cy1 = y0 + h // 4
            cy2 = y0 + h // 2
            cy3 = y0 + (3 * h) // 4
            zone_center_slots[style] = [(cx1, cy1), (cx3, cy1), (cx1, cy3), (cx3, cy3), (cx2, cy2)]
        cluster_centers: Dict[str, Tuple[int, int]] = {}
        for f in non_neutral_teams:
            style = cluster_styles[f]
            slots = zone_center_slots.get(style, [])
            if slots:
                center = slots.pop(0)
                zone_center_slots[style] = slots
                cluster_centers[f] = center
            else:
                rect = self.style_zones[style]
                if rect:
                    x0, y0, x1, y1 = rect
                    center = (random.randint(x0 + 40, x1 - 40), random.randint(y0 + 40, y1 - 40))
                    cluster_centers[f] = center
        locations: Dict[Any, Dict[str, Any]] = {}
        forms: Dict[Any, str] = {}
        for f, members in teams_map.items():
            if f == 'Neutral':
                for p in members:
                    style, location = pools.random_location_with_style()
                    if style == 'water':
                        ok = False
                        for _ in range(12):
                            s, loc = pools.random_location_with_style()
                            if s != 'water':
                                style, location = s, loc
                                ok = True
                                break
                        if not ok:
                            style = random.choice([s for s in self.style_order if s != 'water'])
                            try:
                                location = pools.random_location_for_style(style)
                            except Exception:
                                location = 'Unknown'
                    locations[p] = {'style': style, 'location': location, 'x': 0, 'y': 0}
                    px, py = self.random_point_in_style(style)
                    locations[p]['x'] = px
                    locations[p]['y'] = py
                    forms[p] = 'pet'
            else:
                style = cluster_styles.get(f, random.choice(self.style_order))
                for p in members:
                    if style in self.style_zones:
                        px, py = self.random_point_in_style(style)
                        loc_name = pools.random_location_for_style(style)
                        locations[p] = {'style': style, 'location': loc_name, 'x': px, 'y': py}
                        forms[p] = 'pet'
                    else:
                        style, location = pools.random_location_with_style()
                        if style == 'water':
                            ok = False
                            for _ in range(12):
                                s, loc = pools.random_location_with_style()
                                if s != 'water':
                                    style, location = s, loc
                                    ok = True
                                    break
                            if not ok:
                                style = random.choice([s for s in self.style_order if s != 'water'])
                                try:
                                    location = pools.random_location_for_style(style)
                                except Exception:
                                    location = 'Unknown'
                        locations[p] = {'style': style, 'location': location, 'x': 0, 'y': 0}
                        if style in self.style_zones:
                            px, py = self.random_point_in_style(style)
                            locations[p]['x'] = px
                            locations[p]['y'] = py
                        forms[p] = 'pet'
        return locations, forms

    def initialize_locations(self, participants: List[Any], assignment: Dict[Any, str], pools: Any) -> Tuple[Dict[Any, Dict[str, Any]], Dict[Any, str]]:
        return self.assign_locations(participants, assignment, pools)

    def _calculate_dynamic_icon_size(self, total_participants: int, alive_participants: int, base_size: int = 20) -> int:
        return max(12, int(base_size * (2/3)))

    def render_map(self, round_markers: List[Dict[str, Any]], elimination_locations: Dict[Any, Dict[str, int]], elimination_round: Dict[Any, int], round_index: int, locations: Optional[Dict[Any, Dict[str, Any]]] = None, total_participants: int = 0, alive_participants: int = 0) -> Optional[BytesIO]:
        if not PIL_AVAILABLE:
            return None
        w, h = self.map_size
        px_per_cm = int(96 / 2.54)
        left_gap = self.map_margin
        right_gap = self.map_margin
        top_gap = self.map_margin
        bottom_gap = self.map_margin
        self.globe_rect = (left_gap, top_gap, w - right_gap, h - bottom_gap)
        img = self._render_terrain_base()
        d = ImageDraw.Draw(img)
        land_styles = [s for s in self.style_order if s != 'water']
        used_styles = set()
        for p, info in (locations or {}).items():
            s = info.get('style')
            if isinstance(s, str):
                used_styles.add(s)
        for m in (round_markers or []):
            s = m.get('style')
            if isinstance(s, str):
                used_styles.add(s)
        styles_required = list(set(land_styles) | used_styles)
        self.style_patches = self._generate_continents(seed=round_index or None, styles_required=styles_required)
        land = Image.new('RGBA', self.map_size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(land)
        for biome in self.style_order:
            if biome == 'water':
                continue
            for poly in self.style_patches.get(biome, []):
                col = self.style_bg_colors[biome]
                mask = Image.new('L', self.map_size, 0)
                md = ImageDraw.Draw(mask)
                md.polygon(poly, fill=255)
                base_col = self._lighten_color(col, 0.35)
                fill_layer = Image.new('RGBA', self.map_size, base_col)
                land.paste(fill_layer, (0, 0), mask)

                cx = sum(x for x, _ in poly) // max(1, len(poly))
                cy = sum(y for _, y in poly) // max(1, len(poly))
                xs = [x for x, _ in poly]
                ys = [y for _, y in poly]
                grad_mask = Image.new('L', self.map_size, 0)
                gdraw = ImageDraw.Draw(grad_mask)
                steps = 8
                gdraw.polygon(poly, fill=28)
                shrink_total = max(12, int(0.12 * max(max(xs) - min(xs), max(ys) - min(ys))))
                for i in range(1, steps + 1):
                    off = int(shrink_total * i / steps)
                    inner_i = self._expand_polygon(poly, -off)
                    a = int(28 + 12 * i)
                    gdraw.polygon(inner_i, fill=a)
                if ImageChops:
                    grad_mask = ImageChops.multiply(grad_mask, mask)
                elev_level = {
                    'necro': 1,
                    'magic': 2, 'ice': 2, 'fire': 2, 'psychic': 2,
                    'water': 3, 'basic': 3, 'plant': 3,
                    'air': 4, 'rock': 4, 'electric': 4, 'fighting': 4,
                    'holy': 5
                }
                lvl = elev_level.get(biome, 3)
                if lvl == 1:
                    center_col = (max(0,int(col[0]*0.60)), max(0,int(col[1]*0.60)), max(0,int(col[2]*0.60)), 255)
                elif lvl == 2:
                    center_col = (max(0,int(col[0]*0.85)), max(0,int(col[1]*0.85)), max(0,int(col[2]*0.85)), 255)
                elif lvl == 3:
                    center_col = (col[0], col[1], col[2], 255)
                elif lvl == 4:
                    center_col = (min(255,int(col[0]*1.18)), min(255,int(col[1]*1.18)), min(255,int(col[2]*1.18)), 255)
                else:
                    center_col = (min(255,int(col[0]*1.30)), min(255,int(col[1]*1.30)), min(255,int(col[2]*1.30)), 255)
                center_layer = Image.new('RGBA', self.map_size, center_col)
                land.paste(center_layer, (0, 0), grad_mask)

                ring_steps = 6
                ring_band = max(8, int(0.08 * max(max(xs) - min(xs), max(ys) - min(ys))))
                for ri in range(ring_steps):
                    inner_prev = self._expand_polygon(poly, -int((ring_band * ri) / ring_steps))
                    inner_now = self._expand_polygon(poly, -int((ring_band * (ri + 1)) / ring_steps))
                    ring_mask = Image.new('L', self.map_size, 0)
                    rmd = ImageDraw.Draw(ring_mask)
                    rmd.polygon(inner_prev, fill=180 - ri * 22)
                    rmd.polygon(inner_now, fill=0)
                    if ImageFilter:
                        ring_mask = ring_mask.filter(ImageFilter.GaussianBlur(1))
                    if lvl == 1:
                        ring_col = (max(0,int(col[0]*0.55)), max(0,int(col[1]*0.55)), max(0,int(col[2]*0.55)), 255)
                    elif lvl == 2:
                        ring_col = (max(0,int(col[0]*0.90)), max(0,int(col[1]*0.90)), max(0,int(col[2]*0.90)), 255)
                    elif lvl == 3:
                        ring_col = (col[0], col[1], col[2], 255)
                    elif lvl == 4:
                        ring_col = (min(255,int(col[0]*1.18)), min(255,int(col[1]*1.18)), min(255,int(col[2]*1.18)), 255)
                    else:
                        ring_col = (min(255,int(col[0]*1.35)), min(255,int(col[1]*1.35)), min(255,int(col[2]*1.35)), 255)
                    ring_layer = Image.new('RGBA', self.map_size, ring_col)
                    land.paste(ring_layer, (0,0), ring_mask)

                j = [(x + random.randint(-1, 1), y + random.randint(-1, 1)) for x, y in poly]
                jp = j + [j[0]]
                for i in range(len(jp) - 1):
                    ld.line([jp[i], jp[i + 1]], fill=(0, 0, 0, 220), width=3)
                
                # Add additional solid boundary outline for more definition
                for offset in [-1, 0, 1]:
                    offset_poly = [(x + offset, y + offset) for x, y in poly]
                    offset_j = [(x + random.randint(-1, 1), y + random.randint(-1, 1)) for x, y in offset_poly]
                    offset_jp = offset_j + [offset_j[0]]
                    for i in range(len(offset_jp) - 1):
                        ld.line([offset_jp[i], offset_jp[i + 1]], fill=(0, 0, 0, 160), width=2)
                ocean = self.style_bg_colors['water']
                outer_poly = self._expand_polygon(poly, 8)
                outer_mask = Image.new('L', self.map_size, 0)
                od = ImageDraw.Draw(outer_mask)
                od.polygon(outer_poly, fill=160)
                od.polygon(poly, fill=0)
                if ImageFilter:
                    outer_mask = outer_mask.filter(ImageFilter.GaussianBlur(4))
                shadow_color = (max(0,int(ocean[0]*0.7)), max(0,int(ocean[1]*0.7)), max(0,int(ocean[2]*0.7)), 255)
                shadow_layer = Image.new('RGBA', self.map_size, shadow_color)
                land.paste(shadow_layer, (0, 0), outer_mask)

                inner_poly = self._expand_polygon(poly, -6)
                inner_mask = Image.new('L', self.map_size, 0)
                idraw = ImageDraw.Draw(inner_mask)
                idraw.polygon(poly, fill=200 if lvl >= 4 else 170)
                idraw.polygon(inner_poly, fill=0)
                if ImageFilter:
                    inner_mask = inner_mask.filter(ImageFilter.GaussianBlur(2))
                if lvl in (4, 5):
                    inner_light_col = (
                        min(255,int(col[0]*(1.16 if lvl == 4 else 1.28))),
                        min(255,int(col[1]*(1.16 if lvl == 4 else 1.28))),
                        min(255,int(col[2]*(1.16 if lvl == 4 else 1.28))),
                        255
                    )
                    inner_light = Image.new('RGBA', self.map_size, inner_light_col)
                    land.paste(inner_light, (0,0), inner_mask)
                elif lvl in (1, 2):
                    inner_shadow = Image.new('RGBA', self.map_size, (0,0,0,255))
                    land.paste(inner_shadow, (0,0), inner_mask)
                else:
                    pass

        if ImageChops:
            alpha = land.split()[3]
            mask = ImageChops.multiply(alpha, self._ellipse_mask())
            img.paste(land, (0, 0), mask)
        else:
            img.paste(land, (0, 0), self._ellipse_mask())
        bx0, by0, bx1, by1 = self.globe_rect
        d.rectangle((bx0, by0, bx1, by1), outline=(60, 80, 100, 230), width=3)

        inner_left = left_gap
        inner_top = top_gap
        inner_right = w - right_gap
        inner_bottom = h - bottom_gap
        margin = self.map_margin
        size = 7
        placed: List[Tuple[int, int, int, int]] = []
        group_boxes: List[Tuple[int, int, int, int]] = []
        group_centers: List[Tuple[int, int]] = []
        emoji_font = self._get_emoji_font(size)
        pattern_markers: List[Dict[str, Any]] = [m for m in (round_markers or []) if m.get('pattern') is True]
        static_markers: List[Dict[str, Any]] = [m for m in (round_markers or []) if not m.get('pattern')]
        # First, place static markers at their given coordinates
        for m in static_markers:
            em = m.get('emoji', '⚪')
            m_style = m.get('style')
            stamp = self._emoji_stamp(em, size, emoji_font)
            ew, eh = stamp.size
            px = int(m.get('x', 0))
            py = int(m.get('y', 0))
            px = max(inner_left + ew // 2, min(px, inner_right - ew // 2))
            py = max(inner_top + eh // 2, min(py, inner_bottom - eh // 2))
            bb = (px - ew // 2, py - eh // 2, px + ew // 2, py + eh // 2)
            tries_place = 0
            while any(not (bb[2] < ox0 or bb[0] > ox1 or bb[3] < oy0 or bb[1] > oy1) for (ox0, oy0, ox1, oy1) in placed) and tries_place < 12:
                px += random.randint(-3, 3)
                py += random.randint(-3, 3)
                px = max(inner_left + ew // 2, min(px, inner_right - ew // 2))
                py = max(inner_top + eh // 2, min(py, inner_bottom - eh // 2))
                bb = (px - ew // 2, py - eh // 2, px + ew // 2, py + eh // 2)
                tries_place += 1
            img.paste(stamp, (px - ew // 2, py - eh // 2), stamp)
            placed.append(bb)
        # Build pattern groups by explicit cluster only
        groups: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
        for marker in pattern_markers:
            cl = marker.get('cluster')
            if isinstance(cl, (list, tuple)) and len(cl) == 2:
                key = (int(cl[0]), int(cl[1]))
            else:
                key = (int(marker.get('x', 0)), int(marker.get('y', 0)))
            groups.setdefault(key, []).append(marker)
        def radial_positions(center_x: int, center_y: int, count: int, radius: int) -> List[Tuple[int, int]]:
            if count == 1:
                return [(center_x, center_y)]
            ang_step = 2 * math.pi / count
            return [(int(center_x + radius * math.cos(i * ang_step)), int(center_y + radius * math.sin(i * ang_step))) for i in range(count)]
        
        def geometric_pattern_positions(center_x: int, center_y: int, count: int, radius: int, pattern_type: str = "same_side") -> List[Tuple[int, int]]:
            """Generate geometric patterns for emoji positioning."""
            if count == 1:
                return [(center_x, center_y)]
            elif count == 2:
                # Two users: place close together, slightly offset
                return [(center_x - radius//2, center_y), (center_x + radius//2, center_y)]
            elif count == 3:
                # Three users: triangle formation
                if pattern_type == "opposing_inverted":
                    # Inverted triangle for opposing side
                    return [
                        (center_x, center_y - radius),  # Top point
                        (center_x - radius, center_y + radius//2),  # Bottom left
                        (center_x + radius, center_y + radius//2)   # Bottom right
                    ]
                else:
                    # Regular triangle
                    return [
                        (center_x - radius, center_y + radius//2),  # Bottom left
                        (center_x + radius, center_y + radius//2),  # Bottom right
                        (center_x, center_y - radius)   # Top point
                    ]
            elif count == 4:
                # Four users: square formation
                if pattern_type == "opposing_overlapping":
                    # Overlapping squares (rotated 45 degrees)
                    offset = radius // 2
                    return [
                        (center_x - offset, center_y - offset),  # Top-left
                        (center_x + offset, center_y - offset),  # Top-right
                        (center_x - offset, center_y + offset),  # Bottom-left
                        (center_x + offset, center_y + offset)   # Bottom-right
                    ]
                else:
                    # Regular square
                    offset = radius // 2
                    return [
                        (center_x - offset, center_y - offset),  # Top-left
                        (center_x + offset, center_y - offset),  # Top-right
                        (center_x - offset, center_y + offset),  # Bottom-left
                        (center_x + offset, center_y + offset)   # Bottom-right
                    ]
            elif count == 5:
                # Five users: 5-point star formation
                if pattern_type == "opposing_combined":
                    # Combined 10-point star (two 5-point stars interleaved)
                    positions = []
                    for i in range(10):
                        angle = 2 * math.pi * i / 10
                        if i % 2 == 0:  # Outer points
                            r = radius
                        else:  # Inner points (slightly smaller)
                            r = int(radius * 0.6)
                        positions.append((int(center_x + r * math.cos(angle)), int(center_y + r * math.sin(angle))))
                    return positions
                else:
                    # Regular 5-point star
                    positions = []
                    for i in range(5):
                        angle = 2 * math.pi * i / 5 - math.pi / 2  # Start from top
                        positions.append((int(center_x + radius * math.cos(angle)), int(center_y + radius * math.sin(angle))))
                    return positions
            else:
                # Default to radial for larger groups
                return radial_positions(center_x, center_y, count, radius)
        for (cx, cy), markers in groups.items():
            tokens: List[str] = []
            for m in markers:
                tokens.append(m.get('emoji', '⚪'))
            # Calculate dynamic icon size based on participant count
            base_icon_size = max(24, min(w, h) // 24)
            icon_size = self._calculate_dynamic_icon_size(total_participants, alive_participants, base_icon_size)
            emoji_font = self._get_emoji_font(icon_size)
            
            # Separate markers by sides for opposing patterns
            side_a_markers = []
            side_b_markers = []
            neutral_markers = []
            
            for m in markers:
                owner = m.get('owner_side')
                if owner == 'A':
                    side_a_markers.append(m)
                elif owner == 'B':
                    side_b_markers.append(m)
                else:
                    neutral_markers.append(m)
            
            # Determine if this is an opposing sides event
            has_opposing_sides = len(side_a_markers) > 0 and len(side_b_markers) > 0
            
            if has_opposing_sides:
                side_a_count = len(side_a_markers)
                side_b_count = len(side_b_markers)
                px_per_cm = int(96/2.54)
                r_inner = max(int(px_per_cm * 0.8), 18)
                r_outer = r_inner + max(int(px_per_cm * 0.6), 18)
                smaller_is_a = side_a_count <= side_b_count
                all_elimination = all(m.get('is_elimination') for m in markers)
                def square(cx0, cy0, r):
                    o = r
                    return [(cx0 - o, cy0 - o), (cx0 + o, cy0 - o), (cx0 + o, cy0 + o), (cx0 - o, cy0 + o)]
                def triangle(cx0, cy0, r):
                    return [(cx0 - r, cy0 + r//2), (cx0 + r, cy0 + r//2), (cx0, cy0 - r)]
                def triangle_inverted(cx0, cy0, r):
                    return [(cx0, cy0 + r), (cx0 - r, cy0 - r//2), (cx0 + r, cy0 - r//2)]
                def star5(cx0, cy0, r, offset: float = 0.0):
                    pts = []
                    for i in range(5):
                        ang = 2 * math.pi * i / 5 - math.pi/2 + offset
                        pts.append((int(cx0 + r * math.cos(ang)), int(cy0 + r * math.sin(ang))))
                    return pts
                def star10(cx0, cy0, r):
                    pts = []
                    for i in range(10):
                        ang = 2 * math.pi * i / 10 - math.pi/2
                        rr = r if i % 2 == 0 else int(r * 0.6)
                        pts.append((int(cx0 + rr * math.cos(ang)), int(cy0 + rr * math.sin(ang))))
                    return pts
                if side_a_count == 1 and side_b_count == 1:
                    gap_px = max(int(px_per_cm * 0.6), 10)
                    positions = [(cx - gap_px//2, cy), (cx + gap_px//2, cy)]
                elif {side_a_count, side_b_count} == {1, 2}:
                    center_side_is_a = smaller_is_a
                    center_pos = [(cx, cy)]
                    ring = [(cx - r_inner, cy), (cx + r_inner, cy)]
                    positions = (center_pos + ring) if center_side_is_a else (ring + center_pos)
                elif {side_a_count, side_b_count} == {1, 3}:
                    center_side_is_a = smaller_is_a
                    center_pos = [(cx, cy)]
                    ring = triangle(cx, cy, r_inner)
                    positions = (center_pos + ring) if center_side_is_a else (ring + center_pos)
                elif {side_a_count, side_b_count} == {1, 4}:
                    center_side_is_a = smaller_is_a
                    center_pos = [(cx, cy)]
                    ring = square(cx, cy, r_inner)
                    positions = (center_pos + ring) if center_side_is_a else (ring + center_pos)
                elif {side_a_count, side_b_count} == {1, 5}:
                    center_side_is_a = smaller_is_a
                    center_pos = [(cx, cy)]
                    ring = star5(cx, cy, r_inner)
                    positions = (center_pos + ring) if center_side_is_a else (ring + center_pos)
                elif side_a_count == 2 and side_b_count == 2:
                    if all_elimination:
                        offset = max(8, r_inner // 2)
                        positions = [
                            (cx - offset, cy - offset),
                            (cx + offset, cy - offset),
                            (cx - offset, cy + offset),
                            (cx + offset, cy + offset)
                        ]
                    else:
                        a_pos = [(cx - r_inner, cy - r_inner//1), (cx - r_inner, cy + r_inner//1)]
                        b_pos = [(cx + r_inner, cy - r_inner//1), (cx + r_inner, cy + r_inner//1)]
                        positions = a_pos + b_pos
                elif {side_a_count, side_b_count} == {2, 3}:
                    center_is_a = smaller_is_a
                    center_two = [(cx - r_inner//2, cy), (cx + r_inner//2, cy)]
                    ring = triangle(cx, cy, r_outer)
                    positions = (center_two + ring) if center_is_a else (ring + center_two)
                elif {side_a_count, side_b_count} == {2, 4}:
                    center_is_a = smaller_is_a
                    center_two = [(cx - r_inner//2, cy), (cx + r_inner//2, cy)]
                    ring = square(cx, cy, r_outer)
                    positions = (center_two + ring) if center_is_a else (ring + center_two)
                elif {side_a_count, side_b_count} == {2, 5}:
                    center_is_a = smaller_is_a
                    center_two = [(cx - r_inner//2, cy), (cx + r_inner//2, cy)]
                    ring = star5(cx, cy, r_outer)
                    positions = (center_two + ring) if center_is_a else (ring + center_two)
                elif side_a_count == 3 and side_b_count == 3:
                    a_pos = triangle(cx, cy, r_inner)
                    b_pos = triangle_inverted(cx, cy, r_inner)
                    positions = a_pos + b_pos
                elif {side_a_count, side_b_count} == {3, 4}:
                    tri_is_a = smaller_is_a
                    center_tri = triangle(cx, cy, r_inner)
                    ring_sq = square(cx, cy, r_outer)
                    positions = (center_tri + ring_sq) if tri_is_a else (ring_sq + center_tri)
                elif {side_a_count, side_b_count} == {3, 5}:
                    tri_is_a = smaller_is_a
                    center_tri = triangle(cx, cy, r_inner)
                    ring_star = star5(cx, cy, r_outer)
                    positions = (center_tri + ring_star) if tri_is_a else (ring_star + center_tri)
                elif side_a_count == 4 and side_b_count == 4:
                    a_pos = square(cx, cy, r_inner)
                    ang = math.pi/4
                    r = r_inner
                    b_pos = [(int(cx + r*math.cos(ang)), int(cy - r*math.sin(ang))),
                             (int(cx + r*math.cos(3*ang)), int(cy - r*math.sin(3*ang))),
                             (int(cx + r*math.cos(5*ang)), int(cy - r*math.sin(5*ang))),
                             (int(cx + r*math.cos(7*ang)), int(cy - r*math.sin(7*ang)))]
                    positions = a_pos + b_pos
                elif side_a_count == 4 and side_b_count == 5 or side_a_count == 5 and side_b_count == 4:
                    sq_is_a = smaller_is_a
                    center_sq = square(cx, cy, r_inner)
                    ring_star = star5(cx, cy, r_outer)
                    positions = (center_sq + ring_star) if sq_is_a else (ring_star + center_sq)
                elif side_a_count == 5 and side_b_count == 5:
                    if all_elimination:
                        positions = star10(cx, cy, r_inner)
                    else:
                        a_pos = star5(cx, cy, r_inner, 0.0)
                        b_raw = star5(cx, cy, r_inner, 0.0)
                        b_pos = [(int(2*cx - x), y) for (x, y) in b_raw]
                        positions = a_pos + b_pos
                else:
                    center_is_a = smaller_is_a
                    inner = radial_positions(cx, cy, min(side_a_count, side_b_count), r_inner)
                    outer = radial_positions(cx, cy, max(side_a_count, side_b_count), r_outer)
                    positions = (inner + outer) if center_is_a else (outer + inner)
            else:
                total_count = len(tokens)
                px_per_cm = int(96/2.54)
                has_keeper = any((m.get('kind') == 'keeper') or (m.get('emoji') == '👽') for m in markers)
                if has_keeper and total_count >= 2:
                    r = max(18, int(px_per_cm * 1.0))
                    ring = radial_positions(cx, cy, total_count - 1, r)
                    positions = [(0, 0)] * total_count
                    keeper_index = None
                    for i, m in enumerate(markers):
                        if (m.get('kind') == 'keeper') or (m.get('emoji') == '👽'):
                            keeper_index = i
                            break
                    if keeper_index is None:
                        keeper_index = 0
                    positions[keeper_index] = (cx, cy)
                    ri = 0
                    for i, m in enumerate(markers):
                        if i == keeper_index:
                            continue
                        positions[i] = ring[ri]
                        ri += 1
                else:
                    if total_count == 2:
                        two_cm = int(px_per_cm * 2.0)
                        positions = geometric_pattern_positions(cx, cy, total_count, two_cm, "same_side")
                    elif total_count == 3:
                        base_r = int(px_per_cm * 0.85)
                        positions = geometric_pattern_positions(cx, cy, total_count, base_r, "same_side")
                    elif total_count == 4:
                        base_r = int(px_per_cm * 0.85)
                        positions = geometric_pattern_positions(cx, cy, total_count, base_r, "same_side")
                    elif total_count == 5:
                        base_r = int(px_per_cm * 0.85)
                        positions = geometric_pattern_positions(cx, cy, total_count, base_r, "same_side")
                    else:
                        tight_r = max(16, int(px_per_cm * 0.8))
                        positions = radial_positions(cx, cy, total_count, tight_r)

            group_style_counts: Dict[str, int] = {}
            for m in markers:
                s = m.get('style')
                if isinstance(s, str):
                    group_style_counts[s] = group_style_counts.get(s, 0) + 1
            if group_style_counts:
                group_style = max(group_style_counts.items(), key=lambda kv: kv[1])[0]
                if group_style != 'water':
                    polys = self.style_patches.get(group_style, [])
                    target_poly_group = None
                    for poly in polys:
                        if self._point_in_polygon(cx, cy, poly):
                            target_poly_group = poly
                            break
                    if target_poly_group is None and polys:
                        best: Optional[Tuple[float, float, float]] = None
                        for poly in polys:
                            pxs = [p[0] for p in poly]
                            pys = [p[1] for p in poly]
                            cxx = sum(pxs) / len(pxs)
                            cyy = sum(pys) / len(pys)
                            dist = (cxx - cx) ** 2 + (cyy - cy) ** 2
                            if best is None or dist < best[0]:
                                best = (dist, cxx, cyy)
                        if best is not None:
                            new_cx, new_cy = int(best[1]), int(best[2])
                            dx = new_cx - cx
                            dy = new_cy - cy
                            cx, cy = new_cx, new_cy
                            positions = [(px + dx, py + dy) for (px, py) in positions]
            
                # Dynamic spacing: tighter packing for larger groups
                group_size = len(tokens)
                px_per_cm = int(96/2.54)
                min_spacing = int(px_per_cm * 0.5)
                if group_size <= 5:
                    min_spacing = int(px_per_cm * 0.6)
                elif group_size <= 10:
                    min_spacing = int(px_per_cm * 0.5)
                else:
                    min_spacing = int(px_per_cm * 0.4)
            adjusted_positions = []
            for i, (px, py) in enumerate(positions):
                if i == 0:
                    adjusted_positions.append((px, py))
                else:
                    # Find position that maintains minimum spacing
                    best_pos = (px, py)
                    min_distance = float('inf')
                    
                    # Try small adjustments around the target position
                    for dx in range(-20, 21, 5):
                        for dy in range(-20, 21, 5):
                            test_pos = (px + dx, py + dy)
                            # Check distance to all previously placed positions
                            valid = True
                            for prev_pos in adjusted_positions:
                                dist = ((test_pos[0] - prev_pos[0])**2 + (test_pos[1] - prev_pos[1])**2)**0.5
                                if dist < min_spacing:
                                    valid = False
                                    break
                            
                            if valid:
                                # Also check distance to original position to minimize movement
                                orig_dist = ((test_pos[0] - px)**2 + (test_pos[1] - py)**2)**0.5
                                if orig_dist < min_distance:
                                    best_pos = test_pos
                                    min_distance = orig_dist
                    
                    adjusted_positions.append(best_pos)
            
            positions = adjusted_positions
            pxcm = int(96/2.54)
            gx = sum(p[0] for p in positions) // max(1, len(positions))
            gy = sum(p[1] for p in positions) // max(1, len(positions))
            gb = (min(p[0] for p in positions) - icon_size,
                  min(p[1] for p in positions) - icon_size,
                  max(p[0] for p in positions) + icon_size,
                  max(p[1] for p in positions) + icon_size)
            tries_group = 0
            while any(not (gb[2] < ox0 or gb[0] > ox1 or gb[3] < oy0 or gb[1] > oy1) for (ox0, oy0, ox1, oy1) in group_boxes) and tries_group < 24:
                # push away from the nearest group's center
                best = None
                for (ox0, oy0, ox1, oy1), (ocx, ocy) in zip(group_boxes, group_centers):
                    if not (gb[2] < ox0 or gb[0] > ox1 or gb[3] < oy0 or gb[1] > oy1):
                        dx = gx - ocx
                        dy = gy - ocy
                        dist2 = dx*dx + dy*dy
                        if best is None or dist2 < best[0]:
                            best = (dist2, dx, dy)
                if best is None:
                    break
                _, dx, dy = best
                step = max(12, int(pxcm * 0.8))
                if dx == 0 and dy == 0:
                    dx, dy = step, 0
                mag = max(1, int((dx*dx + dy*dy) ** 0.5))
                sx = int(step * dx / mag)
                sy = int(step * dy / mag)
                cx += sx
                cy += sy
                positions = [(px + sx, py + sy) for (px, py) in positions]
                gx = sum(p[0] for p in positions) // max(1, len(positions))
                gy = sum(p[1] for p in positions) // max(1, len(positions))
                gb = (min(p[0] for p in positions) - icon_size,
                      min(p[1] for p in positions) - icon_size,
                      max(p[0] for p in positions) + icon_size,
                      max(p[1] for p in positions) + icon_size)
                tries_group += 1
            group_boxes.append(gb)
            group_centers.append((gx, gy))
            # helper: inside globe check
            def _inside_globe(x: int, y: int) -> bool:
                x0, y0, x1, y1 = self.globe_rect
                return x0 <= x <= x1 and y0 <= y <= y1
            def _bb_inside_globe(bb: Tuple[int, int, int, int]) -> bool:
                x0, y0, x1, y1 = self.globe_rect
                bx0, by0, bx1, by1 = bb
                return bx0 >= x0 and by0 >= y0 and bx1 <= x1 and by1 <= y1
            for i, m in enumerate(markers):
                em = tokens[i]
                m_style = m.get('style')
                target_poly = None
                if isinstance(m_style, str):
                    # Prefer a polygon of this style that contains the cluster center
                    for poly in self.style_patches.get(m_style, []):
                        if self._point_in_polygon(cx, cy, poly):
                            target_poly = poly
                            break
                    if target_poly is None:
                        polys = self.style_patches.get(m_style, [])
                        if polys:
                            # choose nearest by centroid
                            nearest_poly_info: Optional[Tuple[float, List[Tuple[int, int]]]] = None
                            for poly in polys:
                                pxs = [p[0] for p in poly]
                                pys = [p[1] for p in poly]
                                cxx = sum(pxs) / len(pxs)
                                cyy = sum(pys) / len(pys)
                                dist = (cxx - cx) ** 2 + (cyy - cy) ** 2
                                if nearest_poly_info is None or dist < nearest_poly_info[0]:
                                    nearest_poly_info = (dist, poly)
                            if nearest_poly_info:
                                target_poly = nearest_poly_info[1]
                stamp = self._emoji_stamp(em, icon_size, emoji_font)
                if stamp is not None:
                    ew, eh = stamp.size
                else:
                    temp = self._emoji_stamp(em, icon_size, emoji_font)
                    ew, eh = temp.size
                px, py = positions[i]
                px = max(inner_left + ew // 2, min(px, inner_right - ew // 2))
                py = max(inner_top + eh // 2, min(py, inner_bottom - eh // 2))
                tries = 0
                while tries < 24:
                    bb = (px - ew // 2, py - eh // 2, px + ew // 2, py + eh // 2)
                    conflict = False
                    for ox0, oy0, ox1, oy1 in placed:
                        if not (bb[2] < ox0 or bb[0] > ox1 or bb[3] < oy0 or bb[1] > oy1):
                            conflict = True
                            break
                    if not _bb_inside_globe(bb):
                        x0, y0, x1, y1 = self.globe_rect
                        cxg = (x0 + x1) // 2
                        cyg = (y0 + y1) // 2
                        dx = cxg - px
                        dy = cyg - py
                        px += int(dx * 0.25)
                        py += int(dy * 0.25)
                        px = max(inner_left + ew // 2, min(px, inner_right - ew // 2))
                        py = max(inner_top + eh // 2, min(py, inner_bottom - eh // 2))
                    if target_poly is not None and not self._point_in_polygon(px, py, target_poly):
                        dx = cx - px
                        dy = cy - py
                        px += int(dx * 0.25)
                        py += int(dy * 0.25)
                        px = max(inner_left + ew // 2, min(px, inner_right - ew // 2))
                        py = max(inner_top + eh // 2, min(py, inner_bottom - eh // 2))
                    if not conflict:
                        break
                    px += random.randint(-4, 4)
                    py += random.randint(-4, 4)
                    px = max(inner_left + ew // 2, min(px, inner_right - ew // 2))
                    py = max(inner_top + eh // 2, min(py, inner_bottom - eh // 2))
                    tries += 1
                if stamp is not None:
                    img.paste(stamp, (px - ew // 2, py - eh // 2), stamp)
                else:
                    stamp = self._emoji_stamp(em, icon_size, emoji_font)
                    img.paste(stamp, (px - ew // 2, py - eh // 2), stamp)
                placed.append((px - ew // 2, py - eh // 2, px + ew // 2, py + eh // 2))
        # Skulls are now added as clustered markers within round_markers; no separate pasting here.
        buf = BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return buf

    def _apply_parchment_overlay(self, img: Image.Image) -> None:
        """Apply a parchment-style overlay to the image for champion images."""
        if not PIL_AVAILABLE or img is None:
            return
        
        try:
            # Create a parchment-like overlay with warm tones
            overlay = Image.new('RGBA', img.size, (235, 223, 200, 255))
            
            # Add some texture with noise
            for _ in range(1000):
                x = random.randint(0, img.width - 1)
                y = random.randint(0, img.height - 1)
                alpha = random.randint(5, 15)
                overlay.putpixel((x, y), (230, 218, 195, alpha))
            
            # Apply the overlay
            img.paste(overlay, (0, 0), overlay)
        except Exception:
            # If anything goes wrong, just return the original image
            pass
