import base64
import io
import json
import logging
import os
import re
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import aiohttp
import discord
from PIL import Image, ImageDraw, ImageFilter

logger = logging.getLogger(__name__)

SD_API_BASES = [
    base.rstrip("/")
    for base in os.getenv("REAPER_SD_API_BASES", "http://127.0.0.1:7861,http://127.0.0.1:7860").split(",")
    if base.strip()
]
BADGE_SIZE = int(os.getenv("REAPER_BADGE_SIZE", "512"))
FINAL_SIZE = 512

BADGE_DIR = Path(__file__).resolve().parents[2] / "Data" / "Badges"

_PROMPT_JSON_PATH = Path(__file__).resolve().parent / "pet_prompts.json"
with open(_PROMPT_JSON_PATH, "r", encoding="utf-8") as _f:
    _PROMPT_DATA = json.load(_f)

_SPECIES_PROMPTS: Dict[str, str] = _PROMPT_DATA.get("pet_prompts", {})
_TYPE_PROMPTS: Dict[str, str] = _PROMPT_DATA.get("type_prompts", {})
_ELEMENT_PROMPTS: Dict[str, str] = _PROMPT_DATA.get("element_prompts", {})




def _clean_token(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[_-]+", " ", text)
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _title_token(value: Any) -> str:
    text = _clean_token(value)
    return text.title() if text else ""


def _norm_key(value: Any) -> str:
    return _clean_token(value).lower()


def _first_present(data: Dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def pet_traits(pet_data: Dict[str, Any]) -> Tuple[str, str, str, Optional[str]]:
    species = _first_present(pet_data, ("species", "emoji_name", "pet", "pet_name"))
    pet_type = _first_present(pet_data, ("type", "category", "pet_type"))
    element1 = _first_present(pet_data, ("element", "element1", "primary_element"))
    element2 = _first_present(pet_data, ("element2", "secondary_element", "second_element"))

    if not pet_type:
        pet_type = "basic"
    if not element1:
        element1 = "basic"

    e1_norm = _norm_key(element1)
    e2_norm = _norm_key(element2)
    if e2_norm and e2_norm == e1_norm:
        element2 = ""

    return (
        _title_token(species),
        _title_token(pet_type),
        _title_token(element1),
        _title_token(element2) if element2 else None,
    )


def _get_pet_description(species: str) -> str:
    key = _norm_key(species)
    for json_key, desc in _SPECIES_PROMPTS.items():
        if _norm_key(json_key) == key:
            return desc
    return f"clear recognizable {species}"


def _get_type_description(pet_type: str) -> str:
    key = _norm_key(pet_type)
    for json_key, desc in _TYPE_PROMPTS.items():
        if _norm_key(json_key) == key:
            return desc
    return "terrestrial"


def _get_element_description(element: str) -> str:
    key = _norm_key(element)
    for json_key, desc in _ELEMENT_PROMPTS.items():
        if _norm_key(json_key) == key:
            return desc
    return element


def _build_negative_prompt(species: str) -> str:
    return ""


def _build_prompt_from_parts(species: str, pet_type: str, element1: str, element2: Optional[str]) -> str:
    type_desc = _get_type_description(pet_type)
    elem1_desc = _get_element_description(element1)
    parts = [f"cartoon portrait of a {species}", type_desc, elem1_desc]
    if element2:
        elem2_desc = _get_element_description(element2)
        parts.append(elem2_desc)
    parts.append("solid background")
    return ", ".join(parts)


def build_pet_prompt(pet_data: Dict[str, Any]) -> Tuple[str, str]:
    species, pet_type, element1, element2 = pet_traits(pet_data)
    if not species:
        raise ValueError("Pet data is missing species/emoji_name")

    prompt = _build_prompt_from_parts(species, pet_type, element1, element2)
    return prompt, ""


def build_pet_prompt_identity(pet_data: Dict[str, Any]) -> str:
    species, pet_type, element1, element2 = pet_traits(pet_data)
    elements = ", ".join([element1] + ([element2] if element2 else []))
    return f"Pet: {species}\nType: {pet_type}\nElement(s): {elements}"


def build_pet_prompt_with_user_text(
    pet_data: Dict[str, Any],
    user_prompt: str = "",
) -> Tuple[str, str]:
    species, pet_type, element1, element2 = pet_traits(pet_data)
    if not species:
        raise ValueError("Pet data is missing species/emoji_name")

    if user_prompt:
        return user_prompt, ""

    prompt = _build_prompt_from_parts(species, pet_type, element1, element2)
    return prompt, ""


async def _request_txt2img(prompt: str, negative_prompt: str) -> Image.Image:
    payload = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": BADGE_SIZE,
        "height": BADGE_SIZE,
        "steps": int(os.getenv("REAPER_BADGE_STEPS", "28")),
        "cfg_scale": float(os.getenv("REAPER_BADGE_CFG", "8")),
        "batch_size": 1,
        "n_iter": 1,
        "sampler_name": os.getenv("REAPER_BADGE_SAMPLER", "DPM++ 2M Karras"),
        "restore_faces": False,
        "send_images": True,
        "save_images": False,
        "override_settings": {
            "sd_vae": "Automatic",
            "CLIP_stop_at_last_layers": int(os.getenv("REAPER_BADGE_CLIP_SKIP", "2")),
        },
    }

    timeout = aiohttp.ClientTimeout(total=900)
    errors: List[str] = []
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for api_base in SD_API_BASES:
            try:
                async with session.post(f"{api_base}/sdapi/v1/txt2img", json=payload) as response:
                    if response.status != 200:
                        body = await response.text()
                        errors.append(f"{api_base} returned {response.status}: {body[:500]}")
                        continue
                    data = await response.json()
                    break
            except Exception as exc:
                errors.append(f"{api_base} failed: {exc}")
        else:
            raise RuntimeError("Stable Diffusion API request failed. " + " | ".join(errors))

    images = data.get("images") or []
    if not images:
        raise RuntimeError("Stable Diffusion API returned no images")

    image_data = images[0].split(",", 1)[-1]
    raw = base64.b64decode(image_data)
    return Image.open(io.BytesIO(raw)).convert("RGBA")


def _color_distance(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])


def _corner_background_color(image: Image.Image) -> Tuple[int, int, int]:
    rgb = image.convert("RGB")
    width, height = rgb.size
    sample_points = [
        (0, 0),
        (width - 1, 0),
        (0, height - 1),
        (width - 1, height - 1),
        (width // 2, 0),
        (width // 2, height - 1),
        (0, height // 2),
        (width - 1, height // 2),
    ]
    colors = [rgb.getpixel(point) for point in sample_points]
    colors.sort(key=lambda color: colors.count(color), reverse=True)
    return colors[0]


def _background_mask(image: Image.Image) -> Image.Image:
    rgb = image.convert("RGB")
    width, height = rgb.size
    bg = _corner_background_color(image)
    tolerance = int(os.getenv("REAPER_BADGE_BG_TOLERANCE", "42"))
    visited = bytearray(width * height)
    mask = Image.new("L", (width, height), 0)
    mask_pixels = mask.load()
    queue: deque[Tuple[int, int]] = deque()

    for x in range(width):
        queue.append((x, 0))
        queue.append((x, height - 1))
    for y in range(1, height - 1):
        queue.append((0, y))
        queue.append((width - 1, y))

    while queue:
        x, y = queue.popleft()
        if x < 0 or y < 0 or x >= width or y >= height:
            continue
        idx = y * width + x
        if visited[idx]:
            continue
        visited[idx] = 1

        pixel = rgb.getpixel((x, y))
        if _color_distance(pixel, bg) > tolerance:
            continue

        mask_pixels[x, y] = 255
        queue.append((x + 1, y))
        queue.append((x - 1, y))
        queue.append((x, y + 1))
        queue.append((x, y - 1))

    return mask.filter(ImageFilter.GaussianBlur(radius=0.8))


def _solid_subject_mask(bg_mask: Image.Image) -> Image.Image:
    width, height = bg_mask.size
    preliminary = Image.eval(bg_mask, lambda value: 0 if value > 127 else 255)
    padded = Image.new("L", (width + 2, height + 2), 0)
    padded.paste(preliminary, (1, 1))
    for seed in ((0, 0), (width + 1, 0), (0, height + 1), (width + 1, height + 1)):
        ImageDraw.floodfill(padded, seed, 128)

    subject = Image.new("L", (width, height), 0)
    subject_pixels = subject.load()
    padded_pixels = padded.load()
    for y in range(height):
        for x in range(width):
            if padded_pixels[x + 1, y + 1] != 128:
                subject_pixels[x, y] = 255
    return subject


def make_background_transparent(image: Image.Image) -> Image.Image:
    image = image.convert("RGBA")
    bg_mask = _background_mask(image)
    subject_mask = _solid_subject_mask(bg_mask)
    alpha = subject_mask.filter(ImageFilter.GaussianBlur(radius=0.6))
    result = image.copy()
    result.putalpha(alpha)

    bbox = alpha.getbbox()
    if bbox:
        pad = 28
        left = max(0, bbox[0] - pad)
        top = max(0, bbox[1] - pad)
        right = min(result.width, bbox[2] + pad)
        bottom = min(result.height, bbox[3] + pad)
        result = result.crop((left, top, right, bottom))

    result.thumbnail((FINAL_SIZE, FINAL_SIZE), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (FINAL_SIZE, FINAL_SIZE), (0, 0, 0, 0))
    x = (FINAL_SIZE - result.width) // 2
    y = (FINAL_SIZE - result.height) // 2
    canvas.alpha_composite(result, (x, y))
    return canvas


async def generate_pet_badge_image(
    pet_data: Dict[str, Any],
    user_id: int,
    user_prompt: str = "",
) -> Tuple[Image.Image, str]:
    species, pet_type, element1, element2 = pet_traits(pet_data)
    prompt, negative = build_pet_prompt_with_user_text(pet_data, user_prompt)
    logger.info(
        "Generating pet image for user %s: species=%s type=%s element=%s element2=%s prompt=%s",
        user_id,
        species,
        pet_type,
        element1,
        element2,
        prompt[:500],
    )
    generated = await _request_txt2img(prompt, negative)
    transparent = make_background_transparent(generated)
    filename = f"pet_{user_id}_{int(time.time())}.png"
    return transparent, filename


async def generate_pet_badge(pet_data: Dict[str, Any], user_id: int) -> Optional[discord.File]:
    try:
        image, filename = await generate_pet_badge_image(pet_data, user_id)

        BADGE_DIR.mkdir(parents=True, exist_ok=True)
        image.save(BADGE_DIR / f"{user_id}_badge.png", format="PNG")

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        return discord.File(fp=buffer, filename=filename)
    except Exception as exc:
        logger.error("Failed to generate AI pet image for user %s: %s", user_id, exc, exc_info=True)
        return None
