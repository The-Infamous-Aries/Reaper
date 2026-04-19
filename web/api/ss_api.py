"""
Pet Survivor Series — Web API
Handles lobby, game lifecycle, round processing, SSE live feed, and persistence.
All round/narrative logic lives in ss_brain.py.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import random
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.requests import Request

from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.pet_brain import LootCalculator
from Systems.Functions.ss_db import ss_db
from web.api import ss_brain as _brain

logger = logging.getLogger(__name__)
router = APIRouter()

# ── In-memory game state ──────────────────────────────────────────────────────
_ss_game: Optional[Dict[str, Any]] = None
_ss_lock = asyncio.Lock()
_sse_subscribers: List[asyncio.Queue] = []

# ── Persistence helpers ───────────────────────────────────────────────────────

async def _save_state():
    """Persist active game to ss_db. Call while holding _ss_lock."""
    try:
        await ss_db.save_active(_ss_game)
        if _ss_game:
            await ss_db.upsert_game(_ss_game)
    except Exception as e:
        logger.error(f"SS save_state error: {e}")


async def _load_state():
    """Load persisted game state on startup. Resumes lobby/countdown/running games."""
    global _ss_game, _round_task
    try:
        await ss_db.ensure_ready()
        game = await ss_db.load_active()
        if not game:
            return
        status = game.get("status", "none")
        if status in ("none", "finished"):
            return

        # Restore all active states: lobby, countdown, running
        _ss_game = game
        _patch_participant_multipliers(_ss_game)

        # Ensure map fields exist for restored games (backward compat with old saves)
        if "map_positions" not in _ss_game or not _ss_game["map_positions"]:
            if _ss_game.get("participants") and status in ("running", "countdown"):
                _init_map_positions(_ss_game)
                logger.info("SS _load_state: map_positions missing — re-initialized from participant list")
        if "map_events" not in _ss_game:
            _ss_game["map_events"] = []
        if "map_seed" not in _ss_game:
            _ss_game["map_seed"] = random.randint(1000, 9999)

        logger.info(f"SS state restored: status={status}, participants={len(game.get('participants', []))}")

        if status == "countdown":
            remaining = int(game.get("countdown_end", 0)) - int(time.time())
            asyncio.create_task(_resume_countdown(max(0, remaining)))
        elif status == "running":
            # Resume the round schedule.
            # If next_round_at is in the past, fire immediately (set to now so loop fires right away).
            now = int(time.time())
            nra = _ss_game.get("next_round_at", 0)
            if not nra or nra < now:
                _ss_game["next_round_at"] = now  # fire immediately on loop start
                logger.info(f"SS _load_state: next_round_at was overdue by {now - nra}s — firing immediately")
            if _round_task is None or _round_task.done():
                _round_task = asyncio.create_task(_round_loop())
                logger.info("SS _load_state: round loop resumed")

    except Exception as e:
        logger.error(f"SS load_state error: {e}")


async def _resume_countdown(remaining_secs: float):
    global _ss_game, _round_task
    if remaining_secs > 0:
        await asyncio.sleep(remaining_secs)
    async with _ss_lock:
        if _ss_game is None or _ss_game.get("status") != "countdown":
            return
        _ss_game["status"] = "running"
        _ss_game["start_time"] = datetime.now().isoformat()
        _ss_game["round_index"] = 0
        _ss_game["next_round_at"] = int(time.time())  # fire round 1 immediately
        _init_map_positions(_ss_game)
        await _load_rel_map(_ss_game)
        await _add_feed(f"⚔️ The Survivor Series has begun! {len(_ss_game['participants'])} enter the arena.", "system")
        await _save_state()
        await _broadcast("game_started", {
            "participants": _ss_game["participants"],
            "alive_ids": list(_ss_game["alive_ids"]),
            "next_round_at": _ss_game["next_round_at"],
        })
    _round_task = asyncio.create_task(_round_loop())


async def _resume_running():
    """Bot came back online mid-game — resume the round loop without firing a bonus round."""
    global _round_task
    async with _ss_lock:
        if _ss_game is None or _ss_game.get("status") != "running":
            return
        # Ensure map fields are present (backward compat)
        if not _ss_game.get("map_positions"):
            _init_map_positions(_ss_game)
        if "map_events" not in _ss_game:
            _ss_game["map_events"] = []
    if _round_task is None or _round_task.done():
        _round_task = asyncio.create_task(_round_loop())


# ── Helpers ───────────────────────────────────────────────────────────────────

def _new_game() -> Dict[str, Any]:
    return {
        "game_id": f"web-ss-{int(time.time())}",
        "status": "lobby",
        "participants": [],
        "alive_ids": [],
        "eliminated": [],
        "rounds": [],
        "winner": None,
        "round_index": 0,
        "start_time": None,
        "countdown_end": None,
        "created_at": datetime.now().isoformat(),
        "started_by": None,
        "feed": [],
        "map_positions": {},
        "map_events": [],
        "map_seed": random.randint(1000, 9999),
    }


async def _add_feed(text: str, ftype: str = "system"):
    """Append a feed item to the active game state and persist it."""
    if _ss_game is None:
        return
    item = {"text": text, "type": ftype, "ts": int(time.time() * 1000)}
    _ss_game.setdefault("feed", []).append(item)
    # Keep last 500 items in memory
    if len(_ss_game["feed"]) > 500:
        _ss_game["feed"] = _ss_game["feed"][-500:]
    # Persist to ss_db feed table
    try:
        await ss_db.add_feed_event(
            _ss_game["game_id"],
            _ss_game.get("round_index", 0),
            ftype,
            text
        )
    except Exception as e:
        logger.debug(f"feed persist error: {e}")


async def _broadcast(event: str, data: Any):
    """Push an SSE event to all connected clients."""
    msg = {"event": event, "data": data, "ts": int(time.time() * 1000)}
    dead = []
    for q in _sse_subscribers:
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        try:
            _sse_subscribers.remove(q)
        except ValueError:
            pass


async def _dm_user(user_id: str, title: str, body: str) -> None:
    """Send a plain Discord DM to one user. Silently no-ops if bot unavailable."""
    try:
        from Systems.Functions.web_server import get_bot_instance
        bot = get_bot_instance()
        if not bot:
            return
        import discord
        uid_int = int(user_id)
        user = bot.get_user(uid_int) or await bot.fetch_user(uid_int)
        if not user:
            return
        embed = discord.Embed(title=title, description=body, color=0xFFD700)
        await user.send(embed=embed)
    except Exception as e:
        logger.debug(f"SS DM to {user_id} failed: {e}")


def _compute_pet_multiplier(pet: Dict[str, Any]) -> int:
    """
    Mirrors StatsCalculator._calculate_equipment_bonuses multiplier exactly:
      - level_bonus = level // 50  (always applies regardless of equipment)
      - set_mult: 1 (no full set), 3 (full set), 4 (full set + both hat specs match)
      - final = set_mult + level_bonus  (minimum 1)

    Note: pairs (2× per-item) don't change the global set_mult — only a full set does.
    A full set requires: mat pair + gem pair + mon pair + hat equipped.
    """
    level      = max(1, int(pet.get("level", 1)))
    level_bonus = level // 50

    equipment = pet.get("equipment") or {}
    if not equipment:
        return max(1, 1 + level_bonus)

    # ── Collect items exactly as pet_brain does ───────────────────────────────
    mat_counts: Dict[str, int] = {}
    gem_counts: Dict[str, int] = {}
    mon_counts: Dict[str, int] = {}

    mat = equipment.get("Material")
    if isinstance(mat, list):
        for m in mat:
            if isinstance(m, dict) and m.get("name"):
                n = m["name"].lower()
                mat_counts[n] = mat_counts.get(n, 0) + 1
    elif isinstance(mat, dict) and mat.get("name"):
        mat_counts[mat["name"].lower()] = 1

    gems = equipment.get("Gems", [])
    if isinstance(gems, list):
        for g in gems:
            if isinstance(g, dict) and g.get("name"):
                n = g["name"].lower()
                gem_counts[n] = gem_counts.get(n, 0) + 1
    elif isinstance(gems, dict) and gems.get("name"):
        gem_counts[gems["name"].lower()] = 1

    mons = equipment.get("Monsters", [])
    if isinstance(mons, list):
        for m in mons:
            if isinstance(m, dict) and m.get("name"):
                n = m["name"].lower()
                mon_counts[n] = mon_counts.get(n, 0) + 1
    elif isinstance(mons, dict) and mons.get("name"):
        mon_counts[mons["name"].lower()] = 1

    hat = equipment.get("Hat")
    if isinstance(hat, list):
        hat = hat[0] if hat else None
    hat_equipped = isinstance(hat, dict) and bool(hat.get("name"))

    has_mat_pair = any(v >= 2 for v in mat_counts.values())
    has_gem_pair = any(v >= 2 for v in gem_counts.values())
    has_mon_pair = any(v >= 2 for v in mon_counts.values())
    full_set     = has_mat_pair and has_gem_pair and has_mon_pair and hat_equipped

    if full_set:
        # Mirror LootCalculator._get_pet_specs exactly:
        # field is "specializations" first, then "specs" fallback
        raw_specs = pet.get("specializations") or pet.get("specs") or []
        specs = [s.upper() for s in raw_specs] if isinstance(raw_specs, list) else []
        hat_bonus_stats = [s.upper() for s in (hat.get("bonuses") or {}).keys()]
        hat_spec_matches = sum(1 for s in hat_bonus_stats if s in specs)
        set_mult = 4 if hat_spec_matches >= 2 else 3
    else:
        set_mult = 1

    return max(1, set_mult + level_bonus)


def _patch_participant_multipliers(game: Dict[str, Any]) -> None:
    """
    Back-fill the 'multiplier' field on any participant that's missing it.
    Called whenever a game is loaded from DB so old saves work correctly.
    NPCs already have their multiplier baked in at creation time.
    Real players need it recomputed from their stored pet data snapshot —
    we can't async-fetch here, so we derive it from whatever equipment data
    is already embedded in the participant record (none for real players in
    old saves, so we fall back to level-only calculation).
    """
    for p in game.get("participants", []):
        if "multiplier" not in p or p["multiplier"] is None:
            level      = max(1, int(p.get("level", 1)))
            level_bonus = level // 50
            # No equipment data in participant record — use level-only multiplier.
            # Real players will get the full value next time they join a fresh game.
            p["multiplier"] = max(1, 1 + level_bonus)


async def _build_participant_record(user_id: int, username: str) -> Dict[str, Any]:
    """Load pet data and build a participant record including the equipment multiplier."""
    pet = await user_data_manager.get_pet_data_async(str(user_id))
    multiplier = _compute_pet_multiplier(pet) if pet else 1

    # Build Discord avatar URL from stored hash (set by discord_auth on login)
    avatar_hash = (pet or {}).get("discord_avatar", "")
    if avatar_hash:
        avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.webp?size=64"
    else:
        try:
            bucket = (int(user_id) >> 22) % 5
        except (ValueError, TypeError):
            bucket = 0
        avatar_url = f"https://cdn.discordapp.com/embed/avatars/{bucket}.png"

    return {
        "user_id":       str(user_id),
        "username":      username,
        "avatar_url":    avatar_url,
        "pet_name":      (pet or {}).get("name", username),
        "species":       (pet or {}).get("species", "Cat"),
        "element":       (pet or {}).get("element", "basic"),
        "element2":      (pet or {}).get("element2", ""),
        "category":      (pet or {}).get("category", "land"),
        "level":         int((pet or {}).get("level", 1)),
        "multiplier":    multiplier,
        "has_pet":       pet is not None,
        # Custom battle action labels saved via /pets/rename
        # Keys: "attack", "defense", "charge"  (lowercase, matching pet_brain lookup)
        "action_labels": (pet or {}).get("action_labels", {}),
    }


# ── NPC generation ────────────────────────────────────────────────────────────

_NPC_NAMES = [
    # Nature / elements (24)
    "Shadow", "Blaze", "Frost", "Storm", "Ember", "Tide", "Gale", "Vex",
    "Rune", "Dusk", "Ash", "Cinder", "Mire", "Flux", "Zeal", "Grim",
    "Nox", "Sable", "Haze", "Wrath", "Lore", "Bane", "Crest", "Void",
    # Celestial (28)
    "Nova", "Comet", "Solstice", "Eclipse", "Nebula", "Quasar", "Pulsar",
    "Zenith", "Nadir", "Equinox", "Solaris", "Lunara", "Astra", "Vega",
    "Rigel", "Altair", "Sirius", "Lyra", "Orion", "Cygnus", "Draco",
    "Perseus", "Andromeda", "Cassidy", "Polaris", "Arcturus", "Capella", "Castor",
    # Mythic / arcane (30)
    "Zephyr", "Tempest", "Inferno", "Glacier", "Torrent", "Quake",
    "Mirage", "Specter", "Phantom", "Wraith", "Revenant", "Banshee",
    "Golem", "Titan", "Colossus", "Leviathan", "Behemoth", "Chimera",
    "Griffin", "Basilisk", "Hydra", "Manticore", "Wyvern", "Kraken",
    "Fenrir", "Cerberus", "Medusa", "Cyclops", "Sphinx", "Minotaur",
    # Elemental forces (18)
    "Magma", "Tundra", "Cyclone", "Tsunami", "Avalanche", "Tremor",
    "Surge", "Gust", "Blizzard", "Thunderclap",
    "Wildfire", "Monsoon", "Drought", "Permafrost", "Sandstorm", "Hailstorm",
    "Flare", "Squall",
    # Precious / minerals (20)
    "Obsidian", "Onyx", "Garnet", "Topaz", "Jasper", "Opal", "Amber",
    "Cobalt", "Crimson", "Indigo", "Scarlet", "Ivory", "Ebony", "Slate",
    "Flint", "Quartz", "Pyrite", "Basalt", "Granite", "Marble",
    # Predators / fierce animals (20)
    "Fang", "Talon", "Claw", "Maw", "Venom", "Sting", "Barb", "Spike",
    "Thorn", "Blade", "Edge", "Pierce", "Slash", "Rend", "Crush",
    "Pounce", "Lunge", "Strike", "Snap", "Gnash",
    # Speed / motion (15)
    "Dash", "Bolt", "Rush", "Streak", "Blitz", "Dart", "Zip",
    "Flicker", "Flash", "Glide", "Soar", "Dive", "Swoop", "Skid", "Hurtle",
    # Dark / shadow (19)
    "Dread", "Gloom", "Murk", "Shade", "Shroud", "Veil", "Umbra",
    "Penumbra", "Abyss", "Chasm", "Rift", "Null", "Cipher",
    "Ruin", "Decay", "Blight", "Plague", "Curse", "Pall",
    # Light / holy (20)
    "Dawn", "Twilight", "Radiance", "Gleam", "Glint", "Shimmer",
    "Luster", "Aureate", "Gilded", "Halo", "Nimbus", "Beacon",
    "Solace", "Seraph", "Cherub", "Paladin", "Valor", "Virtue", "Lumis", "Ardent",
    # Unique / exotic (20)
    "Axiom", "Paradox", "Enigma", "Riddle", "Oracle", "Omen", "Portent",
    "Augur", "Seer", "Prophet", "Sage", "Mystic", "Shaman", "Druid",
    "Warlock", "Sorcerer", "Conjurer", "Invoker", "Hexblade", "Arcanist",
    # Short punchy names (17)
    "Rex", "Max", "Ace", "Jet", "Kai", "Zax", "Rox", "Dex", "Tex",
    "Brix", "Crux", "Lynx", "Pyx", "Styx", "Vyx", "Wyx", "Jax",
    # Nature spirits (21)
    "Briar", "Fern", "Moss", "Reed", "Sedge", "Thistle", "Nettle", "Bracken",
    "Hazel", "Rowan", "Alder", "Birch", "Cedar", "Elm", "Hawthorn",
    "Juniper", "Laurel", "Maple", "Willow", "Yew", "Sorrel",
    # Ocean / water (19)
    "Coral", "Reef", "Kelp", "Brine", "Foam", "Spray", "Swell",
    "Eddy", "Current", "Undertow", "Maelstrom", "Whirlpool",
    "Trench", "Shoal", "Lagoon", "Atoll", "Geyser", "Cascade", "Riptide",
    # Warriors / titles (20)
    "Aegis", "Bastion", "Rampart", "Bulwark", "Vanguard",
    "Sentinel", "Warden", "Champion", "Crusader", "Marauder", "Raider",
    "Berserker", "Duelist", "Gladiator", "Lancer", "Ranger", "Scout",
    "Stalker", "Hunter", "Reaver",
    # Arcane concepts (15)
    "Nexus", "Vertex", "Apex", "Prism", "Vortex", "Helix",
    "Matrix", "Vector", "Scalar", "Tensor", "Fractal", "Entropy",
    "Sigil", "Glyph", "Relic",
]
# Deduplicate while preserving order
_NPC_NAMES = list(dict.fromkeys(_NPC_NAMES))
_ELEMENTS = ["fire", "water", "electric", "ice", "plant", "rock", "air", "magic", "holy", "necro", "psychic", "fighting", "basic"]
_CATEGORIES = ["land", "flying", "swimming"]
# Use real pet species from info.json if available, else fallback list
_NPC_SPECIES_FALLBACK = [
    "Wolf", "Fox", "Eagle", "Tiger", "Shark", "Panther", "Hawk",
    "Viper", "Bear", "Lynx", "Raven", "Cobra", "Falcon", "Jaguar", "Orca",
]

def _get_npc_species_pool() -> List[str]:
    # ss_brain already has info.json loaded — reuse it
    pets = list(_brain._PET_ACTIONS.keys())
    return pets if pets else _NPC_SPECIES_FALLBACK

_NPC_SPECIES_POOL: Optional[List[str]] = None
_NPC_NAMES_SHUFFLED: Optional[List[str]] = None  # Shuffled once per game for uniqueness

def _make_npc(idx: int) -> Dict[str, Any]:
    global _NPC_SPECIES_POOL, _NPC_NAMES_SHUFFLED
    if _NPC_SPECIES_POOL is None:
        _NPC_SPECIES_POOL = _get_npc_species_pool()
    # Shuffle names once per game to ensure uniqueness
    if _NPC_NAMES_SHUFFLED is None:
        _NPC_NAMES_SHUFFLED = list(_NPC_NAMES)
        random.shuffle(_NPC_NAMES_SHUFFLED)
    # Use idx directly (no modulo) — we have 300+ names now
    name = _NPC_NAMES_SHUFFLED[idx] if idx < len(_NPC_NAMES_SHUFFLED) else f"NPC_{idx}"
    species = random.choice(_NPC_SPECIES_POOL)
    # NPC levels span a wide range so Survive Scores are varied and meaningful
    level = random.randint(1, 5000)

    # Simulate realistic equipment multiplier:
    #   level_bonus = level // 50
    #   set_mult: weighted toward lower values (most pets don't have full sets)
    level_bonus = level // 50
    roll = random.random()
    if roll < 0.40:
        set_mult = 1   # no set / singles only
    elif roll < 0.65:
        set_mult = 2   # has a pair
    elif roll < 0.85:
        set_mult = 3   # full set
    else:
        set_mult = 4   # full set + both hat specs match
    multiplier = max(1, set_mult + level_bonus)

    return {
        "user_id": f"npc_{idx}",
        "username": f"NPC {name}",
        "avatar_url": "",
        "pet_name": name,
        "species": species,
        "element": random.choice(_ELEMENTS),
        "element2": random.choice([""] + _ELEMENTS[:6]),
        "category": random.choice(_CATEGORIES),
        "level": level,
        "multiplier": multiplier,
        "has_pet": True,
        "is_npc": True,
    }



def _process_round_logic(game: Dict[str, Any]) -> Dict[str, Any]:
    """Delegate fully to ss_brain.process_round."""
    return _brain.process_round(game)


# ── Map state helpers ─────────────────────────────────────────────────────────

def _zone_rects(W: int = 1600, H: int = 1066, M: int = 0) -> Dict[str, tuple]:
    """
    Zone rectangles matching the JS frontend MAP_ZONES exactly.
    Layout (4 rows × 4 cols, basic occupies 2×2 center):

      Row 0: ice | holy | air | psychic
      Row 1: plant | [basic 2×2] | rock
      Row 2: magic | [basic 2×2] | fighting
      Row 3: water | necro | electric | fire
    """
    c1 = 0
    c2 = round(W * 0.25)
    c3 = round(W * 0.50)
    c4 = round(W * 0.75)
    c5 = W
    r1 = 0
    r2 = round(H * 0.25)
    r3 = round(H * 0.50)
    r4 = round(H * 0.75)
    r5 = H
    return {
        # Row 0 — sky/light themes
        "ice":      (c1, r1, c2, r2),
        "holy":     (c2, r1, c3, r2),
        "air":      (c3, r1, c4, r2),
        "psychic":  (c4, r1, c5, r2),
        # Row 1 — left/right flanks, basic center
        "plant":    (c1, r2, c2, r3),
        "basic":    (c2, r2, c4, r4),   # 2×2 center block
        "rock":     (c4, r2, c5, r3),
        # Row 2 — left/right flanks, basic center continues
        "magic":    (c1, r3, c2, r4),
        "fighting": (c4, r3, c5, r4),
        # Row 3 — ground/dark themes
        "water":    (c1, r4, c2, r5),
        "necro":    (c2, r4, c3, r5),
        "electric": (c3, r4, c4, r5),
        "fire":     (c4, r4, c5, r5),
    }


def _zone_random_point(style: str, W: int = 1600, H: int = 1066, M: int = 0) -> tuple:
    rects = _zone_rects(W, H, M)
    x0, y0, x1, y1 = rects.get(style, rects["basic"])
    pad = 30
    return (random.randint(x0 + pad, max(x0 + pad + 1, x1 - pad)),
            random.randint(y0 + pad, max(y0 + pad + 1, y1 - pad)))


def _zone_cluster_points(style: str, count: int, W: int = 1600, H: int = 1066) -> List[tuple]:
    """
    Return `count` (x, y) points clustered near a random spot inside the zone.
    Used for elimination events so combatants appear next to each other on the map.
    Spread is ±40px so they're visually adjacent but not stacked.
    """
    rects = _zone_rects(W, H)
    x0, y0, x1, y1 = rects.get(style, rects["basic"])
    pad = 60
    cx = random.randint(x0 + pad, max(x0 + pad + 1, x1 - pad))
    cy = random.randint(y0 + pad, max(y0 + pad + 1, y1 - pad))
    spread = 40
    points = []
    for i in range(count):
        angle = (2 * 3.14159 * i) / max(count, 1)
        import math
        r = spread * (0.5 + 0.5 * (i % 2))
        px = int(cx + r * math.cos(angle))
        py = int(cy + r * math.sin(angle))
        # Clamp inside zone
        px = max(x0 + 20, min(x1 - 20, px))
        py = max(y0 + 20, min(y1 - 20, py))
        points.append((px, py))
    return points


_ELEM_HOME: Dict[str, str] = {
    "fire": "fire", "water": "water", "electric": "electric", "ice": "ice",
    "plant": "plant", "rock": "rock", "air": "air", "magic": "magic",
    "holy": "holy", "necro": "necro", "psychic": "psychic",
    "fighting": "fighting", "basic": "basic",
}


def _init_map_positions(game: Dict[str, Any]) -> None:
    """Start ALL pets in the basic (neutral) zone. Resets seed and all positions."""
    positions = {}
    for p in game["participants"]:
        uid = p["user_id"]
        x, y = _zone_random_point("basic")
        positions[uid] = {"x": x, "y": y, "style": "basic", "location": ""}
    game["map_positions"] = positions
    game["map_events"] = []
    game["map_seed"] = random.randint(1000, 9999)


def _add_participant_map_position(game: Dict[str, Any], participant: Dict[str, Any]) -> None:
    """Add a single participant's starting position without disturbing existing positions or seed.
    Used when a player joins the lobby so their marker appears immediately on the map.
    All pets start in the basic (neutral) zone.
    """
    # Ensure the map is bootstrapped (seed + events) even if this is the first player
    if "map_seed" not in game:
        game["map_seed"] = random.randint(1000, 9999)
    if "map_events" not in game:
        game["map_events"] = []
    positions = game.setdefault("map_positions", {})
    uid = participant["user_id"]
    if uid not in positions:
        x, y = _zone_random_point("basic")
        positions[uid] = {"x": x, "y": y, "style": "basic", "location": ""}


def _update_map_for_round(game: Dict[str, Any], round_result: Dict[str, Any]) -> None:
    """
    Move each pet to their round zone; record elimination events.
    Combatants in an elimination are clustered at the same spot inside the
    event zone so they appear visually adjacent on the map.
    """
    W, H = 1600, 1066
    if "map_positions" not in game or not game["map_positions"]:
        _init_map_positions(game)
    if "map_events" not in game:
        game["map_events"] = []

    positions = game["map_positions"]
    events    = game.get("map_events", [])
    rnd       = game["round_index"]
    p_map     = {p["user_id"]: p for p in game["participants"]}
    pet_locs  = round_result.get("pet_locations", {})

    # Ensure every participant has a position entry
    for p in game["participants"]:
        uid = p["user_id"]
        if uid not in positions:
            elem = (p.get("element") or "basic").lower()
            x, y = _zone_random_point(elem)
            positions[uid] = {"x": x, "y": y, "style": elem, "location": ""}

    # ── Build elimination clusters: all pets in the same elim event share a spot ──
    # Map uid -> (x, y) for pets involved in an elimination this round
    elim_cluster_pos: Dict[str, tuple] = {}
    # Group eliminations by their zone (pet_locs zone of the eliminated pet)
    # Each elimination event involves the eliminated pet + their killer(s)
    elim_this_round = [e for e in game["eliminated"] if e.get("round") == rnd]
    for elim in elim_this_round:
        uid = elim["user_id"]
        killer_uids = elim.get("eliminated_by_uids") or []
        zone = pet_locs.get(uid) or pet_locs.get(killer_uids[0] if killer_uids else uid, "basic")
        # All participants in this fight share a cluster
        all_combatants = [uid] + [k for k in killer_uids if k not in elim_cluster_pos]
        all_combatants = [u for u in all_combatants if u not in elim_cluster_pos]
        if all_combatants:
            pts = _zone_cluster_points(zone, len(all_combatants))
            for i, u in enumerate(all_combatants):
                elim_cluster_pos[u] = pts[i]

    # ── Move alive pets to their destination zone ─────────────────────────────
    for uid in game["alive_ids"]:
        if uid not in positions:
            continue
        if uid in elim_cluster_pos:
            # Winner of an elimination — place at cluster spot
            x, y = elim_cluster_pos[uid]
            zone = pet_locs.get(uid, positions[uid].get("style", "basic"))
            positions[uid].update({"x": x, "y": y, "style": zone})
        else:
            zone = pet_locs.get(uid, positions[uid].get("style", "basic"))
            x, y = _zone_random_point(zone)
            positions[uid].update({"x": x, "y": y, "style": zone})

    # ── Record elimination events with clustered positions ────────────────────
    existing = {(e["user_id"], e["round"]) for e in events if e.get("type") == "elimination"}
    for elim in elim_this_round:
        uid = elim["user_id"]
        if (uid, rnd) not in existing:
            # Use cluster position if available, else last known position
            if uid in elim_cluster_pos:
                ex, ey = elim_cluster_pos[uid]
            else:
                pos = positions.get(uid, {"x": W // 2, "y": H // 2})
                ex, ey = pos["x"], pos["y"]
            zone = pet_locs.get(uid, p_map.get(uid, {}).get("element", "basic"))
            events.append({
                "round":    rnd,
                "type":     "elimination",
                "x":        ex,
                "y":        ey,
                "style":    zone,
                "user_id":  uid,
                "pet_name": elim.get("pet_name", ""),
                "text":     elim.get("text", ""),
            })
            # Also update the eliminated pet's stored position to the cluster spot
            if uid in positions:
                positions[uid].update({"x": ex, "y": ey, "style": zone})

    game["map_events"] = events[-200:]


@router.get("/ss/map")
async def ss_map(request: Request):
    """Return map rendering data: terrain seed, participant positions, events.
    Live level/multiplier are fetched fresh for real players so the map always
    reflects current pet data, not the stale join-time snapshot.
    """
    async with _ss_lock:
        if _ss_game is None:
            return JSONResponse({"status": "none"})
        # Ensure every participant has a position entry.
        # For lobby state, use _add_participant_map_position so the seed is
        # preserved and existing markers don't jump.  Only fall back to a full
        # _init_map_positions if there are no positions at all yet.
        positions = _ss_game.get("map_positions") or {}
        missing = [p for p in _ss_game.get("participants", []) if p["user_id"] not in positions]
        if missing:
            if not positions:
                # First time — full init (sets seed + all positions)
                _init_map_positions(_ss_game)
            else:
                # Incremental — add only the missing participants
                for p in missing:
                    _add_participant_map_position(_ss_game, p)
        # Snapshot what we need — release lock before doing async I/O
        participants_snapshot = list(_ss_game.get("participants", []))
        response_data = {
            "status": _ss_game["status"],
            "map_seed": _ss_game.get("map_seed", 42),
            "map_size": [1600, 1066],
            "positions": _ss_game.get("map_positions", {}),
            "events": _ss_game.get("map_events", []),
            "alive_ids": _ss_game.get("alive_ids", []),
            "round_index": _ss_game.get("round_index", 0),
            "eliminated": _ss_game.get("eliminated", []),
            "rounds": _ss_game.get("rounds", []),
            "rel_map": _ss_game.get("_rel_map", {}),
            "next_round_at": _ss_game.get("next_round_at", 0),
            "charge_stacks": _ss_game.get("_charge_stacks", {}),
        }

    # ── Refresh level + multiplier for real players (outside lock) ────────────
    real_uids = [
        p["user_id"] for p in participants_snapshot
        if not p.get("is_npc") and not str(p["user_id"]).startswith("npc_")
    ]
    # Try to get bot instance for Discord cache fallback (same as Pet Connector / world_api)
    try:
        from Systems.Functions.web_server import get_bot_instance as _get_bot
        _bot = _get_bot()
    except Exception:
        _bot = None

    live_data: Dict[str, Dict[str, Any]] = {}
    for uid in real_uids:
        try:
            pet = await user_data_manager.get_pet_data_async(str(uid))
            if pet:
                # Build fresh avatar URL — prefer pet-stored hash, then bot cache, then default
                # (mirrors the logic in world_api and Pet Connector page)
                avatar_hash = (
                    pet.get("discord_avatar") or
                    pet.get("avatar_hash") or
                    ""
                )
                if _bot and not avatar_hash:
                    try:
                        discord_user = _bot.get_user(int(uid))
                        if discord_user and discord_user.avatar:
                            avatar_hash = discord_user.avatar.key
                    except Exception:
                        pass

                if avatar_hash:
                    fresh_avatar_url = f"https://cdn.discordapp.com/avatars/{uid}/{avatar_hash}.webp?size=64"
                else:
                    try:
                        bucket = (int(uid) >> 22) % 5
                    except (ValueError, TypeError):
                        bucket = 0
                    fresh_avatar_url = f"https://cdn.discordapp.com/embed/avatars/{bucket}.png"

                live_data[str(uid)] = {
                    "level":          int(pet.get("level", 1)),
                    "multiplier":     _compute_pet_multiplier(pet),
                    "specializations": pet.get("specializations") or pet.get("specs") or [],
                    "avatar_url":     fresh_avatar_url,
                }
        except Exception:
            pass

    # Merge live data into participant copies (don't mutate the game state)
    merged_participants = []
    for p in participants_snapshot:
        uid = str(p["user_id"])
        if uid in live_data:
            p = dict(p)  # shallow copy — don't touch game state
            p["level"]          = live_data[uid]["level"]
            p["multiplier"]     = live_data[uid]["multiplier"]
            p["specializations"] = live_data[uid]["specializations"]
            p["avatar_url"]     = live_data[uid]["avatar_url"]
        merged_participants.append(p)

    response_data["participants"] = merged_participants
    return JSONResponse(response_data)



_round_task: Optional[asyncio.Task] = None


async def _round_loop():
    """Fires rounds on schedule. On resume, fires immediately if overdue."""
    global _ss_game
    while True:
        # Calculate how long to sleep until next_round_at
        async with _ss_lock:
            if _ss_game is None or _ss_game["status"] != "running":
                break
            nra = _ss_game.get("next_round_at", 0)
            now = int(time.time())
            sleep_secs = max(0, nra - now)

        if sleep_secs > 0:
            await asyncio.sleep(sleep_secs)

        async with _ss_lock:
            if _ss_game is None or _ss_game["status"] != "running":
                break
            await _fire_round()


async def _fire_round():
    """Process one round and broadcast results. Must be called under _ss_lock."""
    global _ss_game, _round_task
    if _ss_game is None:
        return

    _ss_game["round_index"] = _ss_game.get("round_index", 0) + 1
    result = _process_round_logic(_ss_game)

    # Build participant lookup for use throughout this function
    p_map = {p["user_id"]: p for p in _ss_game.get("participants", [])}

    round_snapshot = {
        "round_index": _ss_game["round_index"],
        "actions": result["actions"],
        "eliminations": result["eliminations"],
        "remaining_count": len(_ss_game["alive_ids"]),
        "eliminated_this_round": [
            {
                "user_id":       e.get("user_id", ""),
                "pet_name":      e.get("pet_name", ""),
                "species":       e.get("species", "Cat"),
                "eliminated_by": e.get("eliminated_by", "Unknown"),
                "is_npc":        e.get("is_npc", False),
            }
            for e in _ss_game["eliminated"]
            if e.get("round") == _ss_game["round_index"]
        ],
        "timestamp": datetime.now().isoformat(),
    }
    _ss_game["rounds"].append(round_snapshot)

    # Persist round to ss_db and add feed items
    asyncio.create_task(ss_db.save_round(_ss_game["game_id"], round_snapshot))
    await _add_feed(f"━━━ Round {_ss_game['round_index']} ━━━", "system")

    # Add detailed round logs — actions first, then eliminations
    for a in result["actions"]:
        await _add_feed(a, "action")
    for e in result["eliminations"]:
        await _add_feed(e, "elim")

    # Summary line
    elim_count = len(result["newly_eliminated"])
    remain_count = len(_ss_game["alive_ids"])
    if elim_count > 0:
        await _add_feed(f"💀 {elim_count} eliminated this round. {remain_count} remain.", "system")
    else:
        await _add_feed(f"🐾 {remain_count} pets remain.", "system")

    # Update map positions
    _update_map_for_round(_ss_game, result)

    # Set next_round_at for the upcoming round (before broadcast so frontend gets fresh timer)
    if not result["game_over"]:
        _ss_game["next_round_at"] = int(time.time()) + 900

    # DM eliminated real users
    for uid in result["newly_eliminated"]:
        p = p_map.get(uid, {})
        if p.get("is_npc") or str(uid).startswith("npc_"):
            continue
        elim_entry = next((e for e in _ss_game["eliminated"] if e.get("user_id") == uid), {})
        # Collect all kills this player made so far in the game
        kills_so_far = []
        for e in _ss_game.get("eliminated", []):
            if uid in (e.get("eliminated_by_uids") or []):
                kills_so_far.append({
                    "pet_name": e.get("pet_name") or e.get("username", "Unknown"),
                    "round":    e.get("round", "?"),
                    "text":     e.get("text", ""),
                })
        asyncio.create_task(_dm_eliminated(
            uid,
            p.get("pet_name") or p.get("username", "Your pet"),
            _ss_game["round_index"],
            elim_entry.get("text", "Your pet was eliminated."),
            kills_so_far,
        ))

    # ── Task tracking: ss_rounds (+1 per real player still alive) ────────────
    # ── Task tracking: ss_eliminate (credit killers for this round) ──────────
    try:
        from web.api.tasks_api import tasks_db as _tdb, _check_and_deliver_daily_goal
        # Credit 1 round survived to every real player still alive
        for uid in list(_ss_game.get("alive_ids", [])):
            if not str(uid).startswith("npc_"):
                async def _do_rounds(u=str(uid)):
                    slots = await _tdb.update_progress_by(u, "ss_rounds", 1)
                    await _check_and_deliver_daily_goal(u, slots)
                asyncio.create_task(_do_rounds())
        # Credit kills to real killers this round
        kill_credits: Dict[str, int] = {}
        for e in _ss_game.get("eliminated", []):
            if e.get("round") != _ss_game["round_index"]:
                continue
            for killer_uid in (e.get("eliminated_by_uids") or []):
                if killer_uid and not str(killer_uid).startswith("npc_"):
                    kill_credits[str(killer_uid)] = kill_credits.get(str(killer_uid), 0) + 1
        for killer_uid, count in kill_credits.items():
            async def _do_elim(u=killer_uid, c=count):
                slots = await _tdb.update_progress_by(u, "ss_eliminate", c)
                await _check_and_deliver_daily_goal(u, slots)
            asyncio.create_task(_do_elim())
    except Exception as _te:
        logger.debug(f"SS task tracking error: {_te}")

    await _broadcast("round", {
        "round": round_snapshot,
        "alive_ids": list(_ss_game["alive_ids"]),
        "eliminated": _ss_game["eliminated"],
        "game_over": result["game_over"],
        "next_round_at": _ss_game.get("next_round_at"),
        "elim_count": elim_count,
        "remain_count": remain_count,
    })

    if result["game_over"]:
        _ss_game["status"] = "finished"
        _ss_game["finished_at"] = datetime.now().isoformat()
        winner_id = _ss_game["alive_ids"][0] if _ss_game["alive_ids"] else None
        winner = p_map.get(winner_id, {}) if winner_id else None
        _ss_game["winner"] = winner

        # ── Build per-player kill counts from elimination log ─────────────────
        kill_counts: Dict[str, int] = {}
        kill_victims: Dict[str, List[str]] = {}  # uid -> list of pet names they killed
        for e in _ss_game.get("eliminated", []):
            # Credit all winners (eliminated_by_uids), fall back to single uid
            killer_uids = e.get("eliminated_by_uids") or (
                [e["eliminated_by_uid"]] if e.get("eliminated_by_uid") else []
            )
            for killer_uid in killer_uids:
                if killer_uid and not killer_uid.startswith("npc_"):
                    kill_counts[killer_uid] = kill_counts.get(killer_uid, 0) + 1
                    kill_victims.setdefault(killer_uid, []).append(
                        e.get("pet_name") or e.get("username", "Unknown")
                    )

        # ── Build per-player rounds survived ─────────────────────────────────
        total_rounds = _ss_game["round_index"]
        rounds_survived: Dict[str, int] = {}
        for p in _ss_game.get("participants", []):
            uid = p.get("user_id", "")
            if p.get("is_npc") or uid.startswith("npc_"):
                continue
            if uid in _ss_game.get("alive_ids", []):
                rounds_survived[uid] = total_rounds  # winner survived all rounds
            else:
                elim_entry = next((e for e in _ss_game.get("eliminated", []) if e.get("user_id") == uid), {})
                rounds_survived[uid] = elim_entry.get("round", 1) - 1  # survived until the round they died

        # ── Award XP to ALL real players (rounds survived + kills) ───────────
        XP_PER_ROUND = 10
        XP_PER_KILL  = 25
        XP_WIN_BONUS = 200
        total_xp_awarded: Dict[str, int] = {}

        for p in _ss_game.get("participants", []):
            uid = p.get("user_id", "")
            if p.get("is_npc") or uid.startswith("npc_"):
                continue
            try:
                pet = await user_data_manager.get_pet_data_async(uid)
                lvl = int((pet or {}).get("level", 1))
                survived = rounds_survived.get(uid, 0)
                kills    = kill_counts.get(uid, 0)
                xp = (survived * XP_PER_ROUND + kills * XP_PER_KILL) * max(1, lvl // 5 + 1)
                if uid == winner_id:
                    xp += XP_WIN_BONUS * max(1, lvl // 5 + 1)
                if xp > 0:
                    await LootCalculator.apply_xp_change(int(uid), xp, "ss_participation")
                    total_xp_awarded[uid] = xp
            except Exception as e:
                logger.error(f"SS XP award error for {uid}: {e}")

        winner_name_feed = (winner.get("pet_name") or winner.get("username", "Unknown")) if winner else "Unknown"
        await _add_feed(f"🏆 {winner_name_feed} wins the Survivor Series!", "system")
        await _broadcast("game_over", {
            "winner": winner,
            "eliminated": _ss_game["eliminated"],
            "total_rounds": _ss_game["round_index"],
        })

        # ── Persist final game state + per-pet stats ──────────────────────────
        game_id = _ss_game["game_id"]
        eliminated = _ss_game.get("eliminated", [])
        alive_ids  = list(_ss_game.get("alive_ids", []))
        participants = _ss_game.get("participants", [])

        # kill_counts already built above — capture for closure
        _kill_counts_snap = dict(kill_counts)

        async def _persist_game_end():
            try:
                await ss_db.upsert_game(_ss_game)
                await ss_db.save_participants(game_id, participants, eliminated, alive_ids, _kill_counts_snap)
                total = len(participants)
                for p in participants:
                    uid = p.get("user_id", "")
                    if p.get("is_npc") or uid.startswith("npc_"):
                        continue
                    is_winner = (uid == winner_id)
                    placement = 1 if is_winner else (
                        next((i + len(alive_ids) + 1 for i, e in enumerate(reversed(eliminated))
                              if e.get("user_id") == uid), total)
                    )
                    await ss_db.update_pet_stats(uid, is_winner, _kill_counts_snap.get(uid, 0), placement)
            except Exception as e:
                logger.error(f"SS persist_game_end error: {e}")

        asyncio.create_task(_persist_game_end())
        await _save_state()

        if _round_task and not _round_task.done():
            _round_task.cancel()
    else:
        await _save_state()


# ── Countdown task ────────────────────────────────────────────────────────────

async def _load_rel_map(game: Dict[str, Any]) -> None:
    """
    Load all real-player relationships into game["_rel_map"].
    NPCs have no relationships (they roam freely).
    Called once when the game transitions to running.
    """
    from Systems.Functions.pets_db import pets_db
    rel_map: Dict[str, Dict[str, str]] = {}
    real_uids = [
        p["user_id"] for p in game.get("participants", [])
        if not p.get("is_npc") and not str(p["user_id"]).startswith("npc_")
    ]
    for uid in real_uids:
        try:
            rels = await pets_db.get_user_relationships(uid)
            if rels:
                rel_map[uid] = rels
        except Exception as e:
            logger.debug(f"SS rel_map load error for {uid}: {e}")
    game["_rel_map"] = rel_map
    logger.info(f"SS _rel_map loaded: {len(rel_map)} players with relationships")


async def _dm_game_start(game: Dict[str, Any]) -> None:
    """DM every real player when the game begins: NPC count + real-player roster with Survive Scores."""
    from web.api import ss_brain as _brain

    parts     = game.get("participants", [])
    real      = [p for p in parts if not p.get("is_npc") and not str(p.get("user_id","")).startswith("npc_")]
    npcs      = [p for p in parts if p.get("is_npc") or str(p.get("user_id","")).startswith("npc_")]
    total     = len(parts)

    # Build the real-player roster lines
    roster_lines = []
    for p in real:
        score = _brain.survive_score(p)
        roster_lines.append(
            f"**{p.get('pet_name') or p.get('username', '?')}** "
            f"({p.get('username', '?')}) — "
            f"Lv.{p.get('level', 1)} ×{p.get('multiplier', 1)} — "
            f"Survive: **{score:.2f}**"
        )

    roster_block = "\n".join(roster_lines) if roster_lines else "No real players found."

    body = (
        f"**{total} pets** have entered the arena "
        f"({len(real)} players + **{len(npcs)} NPCs**).\n\n"
        f"**Real Competitors:**\n{roster_block}\n\n"
        f"Rounds fire every 15 minutes after Round 1. Watch the live feed on the Survive page."
    )

    for p in real:
        asyncio.create_task(_dm_user(
            str(p["user_id"]),
            "⚔️ Pet Survivor Series — Fight Begins!",
            body,
        ))


async def _dm_eliminated(uid: str, pet_name: str, round_num: int,
                          elim_text: str, kills_this_game: List[Dict[str, Any]]) -> None:
    """DM a real player when their pet is eliminated."""
    kill_section = ""
    if kills_this_game:
        lines = [f"• {k['pet_name']} (Round {k['round']}): {k['text']}" for k in kills_this_game]
        kill_section = f"\n\n**Your eliminations this game ({len(kills_this_game)}):**\n" + "\n".join(lines)

    body = (
        f"**Round {round_num}**\n\n"
        f"{elim_text}"
        f"{kill_section}\n\n"
        f"*Watch the rest of the game live on the Survive page.*"
    )
    asyncio.create_task(_dm_user(uid, f"💀 {pet_name} Was Eliminated", body))


async def _countdown_then_start():
    """Wait 15 minutes after start signal, then begin the game."""
    global _ss_game, _round_task
    await asyncio.sleep(900)
    async with _ss_lock:
        if _ss_game is None or _ss_game["status"] != "countdown":
            return
        _ss_game["status"] = "running"
        _ss_game["start_time"] = datetime.now().isoformat()
        _ss_game["round_index"] = 0
        _ss_game["next_round_at"] = int(time.time())  # fire round 1 immediately

        # NPCs were already added at start time — no auto-padding here
        # Initialise map positions now that the full roster is known
        _init_map_positions(_ss_game)
        await _load_rel_map(_ss_game)

        await _broadcast("game_started", {
            "participants": _ss_game["participants"],
            "alive_ids": _ss_game["alive_ids"],
            "next_round_at": _ss_game["next_round_at"],
        })
        await _save_state()

    # ── DM all real players: game start roster ────────────────────────────────
    asyncio.create_task(_dm_game_start(_ss_game))

    _round_task = asyncio.create_task(_round_loop())


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/ss/state")
async def ss_state(request: Request):
    """Return full current game state, falling back to DB if in-memory state is not yet loaded."""
    global _ss_game, _round_task
    async with _ss_lock:
        if _ss_game is None:
            # Race condition guard: _load_state runs as a task on startup and may not
            # have completed yet when the first page load hits this endpoint.
            try:
                game = await ss_db.load_active()
                if game and game.get("status") not in ("none", "finished", None):
                    _ss_game = game
                    _patch_participant_multipliers(_ss_game)
                    if not _ss_game.get("map_positions") and _ss_game.get("participants"):
                        _init_map_positions(_ss_game)
                    _ss_game.setdefault("map_events", [])
                    _ss_game.setdefault("map_seed", random.randint(1000, 9999))
                    logger.info(f"SS state lazy-loaded from DB: status={game.get('status')}, participants={len(game.get('participants', []))}")
                    if game.get("status") == "running":
                        now = int(time.time())
                        nra = _ss_game.get("next_round_at", 0)
                        if not nra or nra < now:
                            _ss_game["next_round_at"] = now  # fire immediately
                        if _round_task is None or _round_task.done():
                            _round_task = asyncio.create_task(_round_loop())
                    elif game.get("status") == "countdown":
                        remaining = int(game.get("countdown_end", 0)) - int(time.time())
                        asyncio.create_task(_resume_countdown(max(0, remaining)))
            except Exception as e:
                logger.error(f"SS state lazy-load error: {e}")

        # Self-heal: if game is running but round loop died, restart it
        if (_ss_game and _ss_game.get("status") == "running"
                and (_round_task is None or _round_task.done())):
            now = int(time.time())
            nra = _ss_game.get("next_round_at", 0)
            if not nra or nra < now:
                _ss_game["next_round_at"] = now
            _round_task = asyncio.create_task(_round_loop())
            logger.warning("SS ss_state: round loop was dead — restarted")

        if _ss_game is None:
            return JSONResponse({"status": "none"})
        return JSONResponse(_ss_game)


@router.post("/ss/join")
async def ss_join(request: Request):
    """Join the current lobby (or create one if none exists)."""
    global _ss_game
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)

    user_id = str(user["id"])
    username = user.get("username", "Unknown")

    async with _ss_lock:
        # Lazy-load from DB if in-memory state is missing (race condition on startup)
        if _ss_game is None:
            try:
                game = await ss_db.load_active()
                if game and game.get("status") not in ("none", "finished", None):
                    _ss_game = game
                    _patch_participant_multipliers(_ss_game)
                    logger.info(f"SS join lazy-loaded from DB: status={game.get('status')}, participants={len(game.get('participants', []))}")
            except Exception as e:
                logger.error(f"SS join lazy-load error: {e}")

        if _ss_game is None:
            _ss_game = _new_game()

        if _ss_game["status"] not in ("lobby",):
            return JSONResponse({"error": "Game already in progress or finished"}, status_code=400)

        # Check already joined
        if any(p["user_id"] == user_id for p in _ss_game["participants"]):
            return JSONResponse({"error": "Already joined", "game": _ss_game})

        # Check has pet
        pet = await user_data_manager.get_pet_data_async(user_id)
        if not pet:
            return JSONResponse({"error": "You need a pet to join the Survivor Series"}, status_code=400)

        participant = await _build_participant_record(int(user_id), username)
        _ss_game["participants"].append(participant)
        _ss_game["alive_ids"].append(user_id)

        # Add this participant's map position immediately so their marker
        # appears on the lobby map without disturbing existing players' positions.
        _add_participant_map_position(_ss_game, participant)

        await _add_feed(f"🐾 {participant['pet_name']} ({username}) joined the lobby!", "system")
        await _broadcast("player_joined", {"participant": participant, "total": len(_ss_game["participants"])})
        await _save_state()

    # Task tracking — ss_join (once per game, like boss)
    try:
        from web.api.tasks_api import record_action as _task_record
        await _task_record(user_id, "ss_join")
    except Exception:
        pass

    return JSONResponse({"ok": True, "game": _ss_game})


@router.post("/ss/start")
async def ss_start(request: Request):
    """
    Any joined user can start the game if 2+ real users are in the lobby.
    Body: { npc_count: int }  — 0 to 100, capped so total participants ≤ 100.
    Generates NPCs immediately (visible in lobby), sends DMs, begins 1-hour countdown.
    """
    global _ss_game
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)

    user_id = str(user["id"])

    try:
        body = await request.json()
        npc_count = int(body.get("npc_count", 0))
    except Exception:
        npc_count = 0

    async with _ss_lock:
        if _ss_game is None or _ss_game["status"] != "lobby":
            return JSONResponse({"error": "No lobby to start"}, status_code=400)

        real_users = [p for p in _ss_game["participants"] if not p.get("is_npc")]
        if len(real_users) < 2:
            return JSONResponse({"error": "Need at least 2 players to start"}, status_code=400)

        if not any(p["user_id"] == user_id for p in real_users):
            return JSONResponse({"error": "You must be in the lobby to start"}, status_code=403)

        # Clamp NPC count: total must not exceed 100
        max_npcs = max(0, 100 - len(_ss_game["participants"]))
        npc_count = max(0, min(npc_count, max_npcs))

        # Generate NPCs now so they appear in the lobby immediately
        # Reset the shuffled name list so each game gets a fresh unique set
        global _NPC_NAMES_SHUFFLED
        _NPC_NAMES_SHUFFLED = None
        existing_npc_ids = {p["user_id"] for p in _ss_game["participants"] if p.get("is_npc")}
        npc_idx = len(existing_npc_ids)
        for i in range(npc_count):
            npc = _make_npc(npc_idx + i)
            _ss_game["participants"].append(npc)
            _ss_game["alive_ids"].append(npc["user_id"])
            # Add map position immediately so NPCs appear on the map right away
            _add_participant_map_position(_ss_game, npc)

        _ss_game["status"] = "countdown"
        _ss_game["started_by"] = user_id
        _ss_game["countdown_end"] = int(time.time()) + 900

        participant_ids = [p["user_id"] for p in real_users]
        participant_names = [p["pet_name"] for p in _ss_game["participants"]]
        total_count = len(_ss_game["participants"])

        await _add_feed(f"🚀 Game starting in 15 minutes! {total_count} participants ({npc_count} NPCs). Round 1 fires immediately when the countdown ends. DMs sent.", "system")
        await _broadcast("countdown_started", {
            "countdown_end": _ss_game["countdown_end"],
            "started_by": user_id,
            "participants": _ss_game["participants"],
            "alive_ids": list(_ss_game["alive_ids"]),
            "npc_count": npc_count,
        })
        await _save_state()

    # Start countdown task
    asyncio.create_task(_countdown_then_start())

    return JSONResponse({"ok": True, "countdown_end": _ss_game["countdown_end"], "total": total_count, "npc_count": npc_count})


@router.post("/ss/leave")
async def ss_leave(request: Request):
    """Leave is disabled — joining is permanent."""
    return JSONResponse({"error": "You cannot leave once you have joined. There is no undo."}, status_code=403)


# ── In-memory last-game snapshot (shown in lobby until next game starts) ──────
_ss_last_game: Optional[Dict[str, Any]] = None


@router.post("/ss/admin/kick_round")
async def ss_admin_kick_round(request: Request):
    """Admin: immediately kick the round loop if it's stuck or overdue."""
    global _ss_game, _round_task
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)

    async with _ss_lock:
        if _ss_game is None or _ss_game.get("status") != "running":
            return JSONResponse({"error": "No running game"}, status_code=400)
        # Set next_round_at to now so the loop fires immediately
        _ss_game["next_round_at"] = int(time.time())
        await _save_state()

    # Restart the round loop if it died
    if _round_task is None or _round_task.done():
        _round_task = asyncio.create_task(_round_loop())
        return JSONResponse({"ok": True, "action": "loop_restarted_and_round_queued"})
    return JSONResponse({"ok": True, "action": "next_round_at_set_to_now"})


@router.post("/ss/reset")
async def ss_reset(request: Request):
    """Admin: reset the game entirely."""
    global _ss_game, _round_task, _ss_last_game
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)

    async with _ss_lock:
        if _round_task and not _round_task.done():
            _round_task.cancel()
        # Preserve finished game as last_game before clearing
        if _ss_game and _ss_game.get("status") == "finished":
            _ss_last_game = {
                "winner":       _ss_game.get("winner"),
                "participants": _ss_game.get("participants", []),
                "eliminated":   _ss_game.get("eliminated", []),
                "rounds":       _ss_game.get("rounds", []),
                "round_index":  _ss_game.get("round_index", 0),
                "finished_at":  _ss_game.get("finished_at"),
            }
        _ss_game = None
        await _broadcast("reset", {"last_game": _ss_last_game})
        await _save_state()

    return JSONResponse({"ok": True})


@router.get("/ss/last_game")
async def ss_last_game_endpoint(request: Request):
    """Return the last finished game snapshot for the lobby log."""
    if _ss_last_game:
        return JSONResponse(_ss_last_game)
    # Try to load from DB
    try:
        game = await ss_db.load_last_finished()
        if game:
            return JSONResponse({
                "winner":       game.get("winner"),
                "participants": game.get("participants", []),
                "eliminated":   game.get("eliminated", []),
                "rounds":       game.get("rounds", []),
                "round_index":  game.get("round_index", 0),
                "finished_at":  game.get("finished_at"),
            })
    except Exception:
        pass
    return JSONResponse({"none": True})


# ── SSE live feed ─────────────────────────────────────────────────────────────

@router.get("/ss/events")
async def ss_events(request: Request):
    """Server-Sent Events stream for live game updates."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=64)
    _sse_subscribers.append(queue)

    async def event_generator():
        # Send current state immediately on connect.
        # If _ss_game is not yet loaded in memory, fall back to DB so the
        # client always gets the real state on first connect.
        global _ss_game, _round_task
        async with _ss_lock:
            init_state = _ss_game
            if init_state is None:
                try:
                    game = await ss_db.load_active()
                    if game and game.get("status") not in ("none", "finished", None):
                        _ss_game = game
                        _patch_participant_multipliers(_ss_game)
                        init_state = game
                        logger.info(f"SS SSE init lazy-loaded from DB: status={game.get('status')}")
                        # Resume tasks if needed
                        if game.get("status") == "running":
                            if _round_task is None or _round_task.done():
                                _round_task = asyncio.create_task(_round_loop())
                        elif game.get("status") == "countdown":
                            remaining = int(game.get("countdown_end", 0)) - int(time.time())
                            asyncio.create_task(_resume_countdown(max(0, remaining)))
                except Exception as _e:
                    logger.debug(f"SS SSE init lazy-load error: {_e}")
            state = init_state or {"status": "none"}
        yield f"data: {json.dumps({'event': 'init', 'data': state})}\n\n"

        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=25)
                    yield f"data: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            try:
                _sse_subscribers.remove(queue)
            except ValueError:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── History & stats endpoints ─────────────────────────────────────────────────

@router.get("/ss/history")
async def ss_history(request: Request):
    """Return list of past SS games (most recent first)."""
    games = await ss_db.get_game_history(limit=30)
    return JSONResponse({"games": games})


@router.get("/ss/history/{game_id}/rounds")
async def ss_game_rounds(game_id: str, request: Request):
    """Return all rounds for a specific game."""
    rounds = await ss_db.get_game_rounds(game_id)
    return JSONResponse({"game_id": game_id, "rounds": rounds})


@router.get("/ss/history/{game_id}/feed")
async def ss_game_feed(game_id: str, request: Request):
    """Return the live feed for a specific game."""
    feed = await ss_db.get_game_feed(game_id, limit=500)
    return JSONResponse({"game_id": game_id, "feed": feed})


@router.get("/ss/history/{game_id}/participants")
async def ss_game_participants(game_id: str, request: Request):
    """Return participants + placements for a specific game."""
    parts = await ss_db.get_game_participants(game_id)
    return JSONResponse({"game_id": game_id, "participants": parts})


@router.get("/ss/pet-stats")
async def ss_pet_stats(request: Request):
    """Return SS stats for the logged-in user's pet."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    stats = await ss_db.get_pet_stats(str(user["id"]))
    return JSONResponse(stats or {
        "games_played": 0, "games_won": 0, "total_kills": 0,
        "best_placement": None, "last_played_at": None, "last_won_at": None
    })
