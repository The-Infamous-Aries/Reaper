"""
Scratch Card API — 5 card types, XP-based betting, fully random outcomes.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.pet_brain import LootCalculator

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Per-user locks ────────────────────────────────────────────────────────────
_user_locks: Dict[str, asyncio.Lock] = {}

def _get_user_lock(user_id: str) -> asyncio.Lock:
    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()
    return _user_locks[user_id]


def _compute_total_xp(pet_data: dict) -> int:
    lvl = int(pet_data.get("level", 1))
    rem = int(pet_data.get("experience", 0))
    return int(LootCalculator.get_total_experience_for_level(lvl)) + rem


# ── Emoji pools ───────────────────────────────────────────────────────────────

def _ep(name: str) -> str:
    """Return the static image path for an emoji name."""
    # Equipment folder (hats, gems, materials, monsters, potions, keys, chests)
    _EQUIPMENT = {
        # Hats
        "boater","aviator","ushanka","bearskin","turban","bowler","beret","nursing","gat",
        "peaked","stovepipe","capotain","keffiyeh","mortarboard","fool","safety","pith",
        "toque","rice","beanie","santa","ballcap","fez","service","tricorne","mitre",
        "sombrero","fedora","sorcerer","cattleman",
        # Gems
        "EmberHeart","MintGaze","EmeraldSoul","ForestEye","SolarSphere","SkySpire",
        "ZephyrShard","AzureApex","MagmaDiamond","PrismaticFlux","FrostShard","EmberCube",
        "JadeSlab","FluxDiamond","MoonQuartz","FuryRose","SolarCore","VoidSpark",
        "GildedPrism","OceanTear",
        # Materials
        "Dirt","Sand","Leaf","Stone","Bone","Fabric","Leather","Glass","Wood","Brick",
        "Gold","Steel","plutonium","Smart","Laser",
        # Monsters
        "Dwep","Krep","Bood","Lozd","Yoa","Nad","Ztuk","Gufi","Rowr","Jle","Zlik","Sili",
        "Qizi","Pir","Wirm","Dodl","Dwim","Zhy","Felr","Drak","Bliz","Smuj","Dvod","Neri",
        "Fwit","Plat","Mok","Jlum","Itle",
        # Potions
        "basic_potion","fire_potion","water_potion","electric_potion","ice_potion",
        "air_potion","rock_potion","plant_potion","magic_potion","holy_potion",
        "necro_potion","psychic_potion","fighting_potion","mega_potion",
        "greater_health_potion","health_potion","lesser_health_potion","xp_potion",
        "lesser_xp_potion","luck_potion","att_potion","def_potion","dex_potion",
        "int_potion","hap_potion","ene_potion","s1_potion","s2_potion","s3_potion",
        # Keys/Chests
        "Key1","Key2","Key3","chest1","chest2","chest3","chest4",
        # RPS/Military in Equipment
        "knights","necromancer","tank","jet","ship","rps","rock_1","paper","scissor",
    }
    if name in _EQUIPMENT:
        return f"/static/Emojis/Pets/Equipment/{name}.png"
    # Pets
    _PETS = {
        "Alligator","Ant","Anteater","Axolotl","Badger","Bat","Beaver","Bee","Beetle",
        "Bison","BlueTang","Camel","Cardinal","Cat","Centipede","Cheetah","Chicken",
        "Clownfish","Cow","Crab","Crow","Deer","Dog","Dolphin","Duck","Eagle","Elephant",
        "Emu","Firefly","Fox","Frog","Giraffe","Goat","Goose","Gorilla","Grizzly",
        "Hamster","Hedgehog","Hippo","Horse","Hummingbird","Iguana","Jaguar","Jellyfish",
        "Kangaroo","Kiwi","Koala","Ladybug","Lemur","Leopard","Lion","Llama","Mantis",
        "Monkey","Mouse","Octopus","Orangutan","Orca","Ostrich","Otter","Owl","Panda",
        "Parrot","Peacock","Pelican","Penguin","Pig","Pigeon","Platypus","PolarBear",
        "Pufferfish","Rabbit","Raccoon","Ram","Rat","RedPanda","Reindeer","Rhino",
        "Salmon","Scorpion","Seahorse","Seal","Shark","Sheep","Shrimp","Skunk","Sloth",
        "Snail","Snake","Spider","Squirrel","Starfish","Stingray","SugarGlider","Tiger",
        "Toucan","Turkey","Turtle","Walrus","Whale","Wolf","Yak","Zebra",
    }
    if name in _PETS:
        return f"/static/Emojis/Pets/{name}.png"
    # Military
    _MILITARY = {"soldier","missile","bomb","spy","fortification","peace_1","strategy","wars"}
    if name in _MILITARY:
        return f"/static/Emojis/Military/{name}.png"
    # Deco (elements, stats, types)
    return f"/static/Emojis/Pets/Deco/{name}.png"


# ── Card definitions ──────────────────────────────────────────────────────────

# Card 1 — Type Emojis (3 symbols, 1×3 row)
CARD1_POOL = ["Flying", "Land", "Swimming"]

# Card 2 — Unit Emojis (3 symbols, 1×3 row)
CARD2_POOL = ["soldier", "tank", "jet", "ship", "missile", "bomb"]

# Card 3 — Element Emojis (3 symbols, 1×3 row)
CARD3_POOL = ["Air", "Basic", "Electric", "Fire", "Holy", "Ice", "Magic", "Necro",
              "Plant", "Rock", "Water", "Psychic", "Fighting"]

# Card 4 — Pet Emojis (3×3 grid, works all ways)
CARD4_POOL = [
    "Alligator","Ant","Anteater","Axolotl","Badger","Bat","Beaver","Bee","Beetle","Bison",
    "BlueTang","Camel","Cardinal","Cat","Centipede","Cheetah","Chicken","Clownfish","Cow",
    "Crab","Crow","Deer","Dog","Dolphin","Duck","Eagle","Elephant","Emu","Firefly","Fox",
    "Frog","Giraffe","Goat","Goose","Gorilla","Grizzly","Hamster","Hedgehog","Hippo",
    "Horse","Hummingbird","Iguana","Jaguar","Jellyfish","Kangaroo","Kiwi","Koala",
    "Ladybug","Lemur","Leopard","Lion","Llama","Mantis","Monkey","Mouse","Octopus",
    "Orangutan","Orca","Ostrich","Otter","Owl","Panda","Parrot","Peacock","Pelican",
    "Penguin","Pig","Pigeon","Platypus","PolarBear","Pufferfish","Rabbit","Raccoon",
    "Ram","Rat","RedPanda","Reindeer","Rhino","Salmon","Scorpion","Seahorse","Seal",
    "Shark","Sheep","Shrimp","Skunk","Sloth","Snail","Snake","Spider","Squirrel",
    "Starfish","Stingray","SugarGlider","Tiger","Toucan","Turkey","Turtle","Walrus",
    "Whale","Wolf","Yak","Zebra",
]

# Card 5 — ALL Equipment & Item Emojis (3×3 grid, works all ways + type-group bonus)
CARD5_MONSTERS  = ["Dwep","Krep","Bood","Lozd","Yoa","Nad","Ztuk","Gufi","Rowr","Jle",
                   "Zlik","Sili","Qizi","Pir","Wirm","Dodl","Dwim","Zhy","Felr","Drak",
                   "Bliz","Smuj","Dvod","Neri","Fwit","Plat","Mok","Jlum","Itle"]
CARD5_MATERIALS = ["Dirt","Sand","Leaf","Stone","Bone","Fabric","Leather","Glass","Wood",
                   "Brick","Gold","Steel","plutonium","Smart","Laser"]
CARD5_GEMS      = ["EmberHeart","MintGaze","EmeraldSoul","ForestEye","SolarSphere",
                   "SkySpire","ZephyrShard","AzureApex","MagmaDiamond","PrismaticFlux",
                   "FrostShard","EmberCube","JadeSlab","FluxDiamond","MoonQuartz",
                   "FuryRose","SolarCore","VoidSpark","GildedPrism","OceanTear"]
CARD5_HATS      = ["boater","aviator","ushanka","bearskin","turban","bowler","beret",
                   "nursing","gat","peaked","stovepipe","capotain","keffiyeh","mortarboard",
                   "fool","safety","pith","toque","rice","beanie","santa","ballcap","fez",
                   "service","tricorne","mitre","sombrero","fedora","sorcerer","cattleman"]
CARD5_POTIONS   = ["basic_potion","fire_potion","water_potion","electric_potion",
                   "ice_potion","air_potion","rock_potion","plant_potion","magic_potion",
                   "holy_potion","necro_potion","psychic_potion","fighting_potion",
                   "mega_potion","greater_health_potion","health_potion",
                   "lesser_health_potion","xp_potion","lesser_xp_potion","luck_potion",
                   "att_potion","def_potion","dex_potion","int_potion","hap_potion",
                   "ene_potion","s1_potion","s2_potion","s3_potion"]

CARD5_POOL = CARD5_MONSTERS + CARD5_MATERIALS + CARD5_GEMS + CARD5_HATS + CARD5_POTIONS

# Map each item to its type group for Card 5 bonus
_CARD5_TYPE: Dict[str, str] = {}
for _n in CARD5_MONSTERS:  _CARD5_TYPE[_n] = "Monsters"
for _n in CARD5_MATERIALS: _CARD5_TYPE[_n] = "Materials"
for _n in CARD5_GEMS:      _CARD5_TYPE[_n] = "Gems"
for _n in CARD5_HATS:      _CARD5_TYPE[_n] = "Hats"
for _n in CARD5_POTIONS:   _CARD5_TYPE[_n] = "Potions"


# ── Win-line helpers ──────────────────────────────────────────────────────────

def _count_matches_1x3(symbols: List[str]) -> int:
    """For a 1×3 row: return 3 if all match, 2 if exactly two match, else 0."""
    counts: Dict[str, int] = {}
    for s in symbols:
        counts[s] = counts.get(s, 0) + 1
    best = max(counts.values())
    if best == 3:
        return 3
    if best == 2:
        return 2
    return 0


def _lines_3x3(grid: List[str]) -> List[List[str]]:
    """Return all 8 win-lines for a 3×3 grid (rows, cols, diagonals)."""
    g = grid  # flat list, row-major
    return [
        [g[0], g[1], g[2]],  # row 0
        [g[3], g[4], g[5]],  # row 1
        [g[6], g[7], g[8]],  # row 2
        [g[0], g[3], g[6]],  # col 0
        [g[1], g[4], g[7]],  # col 1
        [g[2], g[5], g[8]],  # col 2
        [g[0], g[4], g[8]],  # diag TL→BR
        [g[2], g[4], g[6]],  # diag TR→BL
    ]


def _best_match_3x3(grid: List[str]) -> Tuple[int, List[List[str]]]:
    """
    Return (best_match_count, winning_lines) for a 3×3 grid.
    best_match_count = 3 if any line has 3 identical, 2 if any line has 2 identical, else 0.
    winning_lines = list of lines that achieved best_match_count.
    """
    lines = _lines_3x3(grid)
    three_lines = []
    two_lines = []
    for line in lines:
        m = _count_matches_1x3(line)
        if m == 3:
            three_lines.append(line)
        elif m == 2:
            two_lines.append(line)
    if three_lines:
        return 3, three_lines
    if two_lines:
        return 2, two_lines
    return 0, []


# ── Card 5 bonus: same-type group matches ────────────────────────────────────

def _card5_type_bonus(grid: List[str], winning_lines: List[List[str]]) -> Optional[str]:
    """
    If two or more winning lines (3-match) share the same item type group,
    return that group name. Otherwise None.
    """
    if not winning_lines:
        return None
    # Only consider 3-match lines for the bonus
    three_lines = [ln for ln in winning_lines if len(set(ln)) == 1]
    if len(three_lines) < 2:
        return None
    # Check if any two 3-match lines share the same type group
    type_counts: Dict[str, int] = {}
    for line in three_lines:
        sym = line[0]
        t = _CARD5_TYPE.get(sym)
        if t:
            type_counts[t] = type_counts.get(t, 0) + 1
    for t, cnt in type_counts.items():
        if cnt >= 2:
            return t
    return None


# ── Scratch logic ─────────────────────────────────────────────────────────────

def _scratch_card1(bet: int) -> Dict[str, Any]:
    """Type Emojis — 1×3 row. 2-match → x1.2, 3-match → x2."""
    # Weighted draw: make 3-match rare (~1/9 natural, keep it natural)
    symbols = [random.choice(CARD1_POOL) for _ in range(3)]
    m = _count_matches_1x3(symbols)
    if m == 3:
        mult = 2.0
        result = "3 in a row! 2× XP!"
    elif m == 2:
        mult = 1.2
        result = "2 in a row! 1.2× XP back!"
    else:
        mult = 0.0
        result = "No match. Better luck next time!"
    winnings = int(bet * mult)
    return {
        "symbols": [{"name": s, "path": _ep(s)} for s in symbols],
        "grid_type": "1x3",
        "match": m,
        "multiplier": mult,
        "winnings": winnings,
        "result": result,
        "win_lines": [[0, 1, 2]] if m > 0 else [],
    }


def _scratch_card2(bet: int) -> Dict[str, Any]:
    """Unit Emojis — 1×3 row. 2-match → x1.5, 3-match → x5."""
    symbols = [random.choice(CARD2_POOL) for _ in range(3)]
    m = _count_matches_1x3(symbols)
    if m == 3:
        mult = 5.0
        result = "3 Units matched! 5× XP!"
    elif m == 2:
        mult = 1.5
        result = "2 Units matched! 1.5× XP!"
    else:
        mult = 0.0
        result = "No match. Better luck next time!"
    winnings = int(bet * mult)
    return {
        "symbols": [{"name": s, "path": _ep(s)} for s in symbols],
        "grid_type": "1x3",
        "match": m,
        "multiplier": mult,
        "winnings": winnings,
        "result": result,
        "win_lines": [[0, 1, 2]] if m > 0 else [],
    }


def _scratch_card3(bet: int) -> Dict[str, Any]:
    """Element Emojis — 1×3 row. 2-match → x2.5, 3-match → x7.5."""
    symbols = [random.choice(CARD3_POOL) for _ in range(3)]
    m = _count_matches_1x3(symbols)
    if m == 3:
        mult = 7.5
        result = "3 Elements matched! 7.5× XP!"
    elif m == 2:
        mult = 2.5
        result = "2 Elements matched! 2.5× XP!"
    else:
        mult = 0.0
        result = "No match. Better luck next time!"
    winnings = int(bet * mult)
    return {
        "symbols": [{"name": s, "path": _ep(s)} for s in symbols],
        "grid_type": "1x3",
        "match": m,
        "multiplier": mult,
        "winnings": winnings,
        "result": result,
        "win_lines": [[0, 1, 2]] if m > 0 else [],
    }


def _scratch_card4(bet: int) -> Dict[str, Any]:
    """Pet Emojis — 3×3 grid, all 8 lines. 2-match → x10, 3-match → x25."""
    grid = [random.choice(CARD4_POOL) for _ in range(9)]
    best, win_lines = _best_match_3x3(grid)
    if best == 3:
        mult = 25.0
        result = "3 Pets in a line! 25× XP!"
    elif best == 2:
        mult = 10.0
        result = "2 Pets in a line! 10× XP!"
    else:
        mult = 0.0
        result = "No match. Better luck next time!"
    winnings = int(bet * mult)
    # Convert win_lines (list of symbol lists) to index lists for the frontend
    all_lines = _lines_3x3(grid)
    win_line_indices = []
    for wl in win_lines:
        for i, al in enumerate(all_lines):
            if al == wl:
                win_line_indices.append(i)
                break
    return {
        "symbols": [{"name": s, "path": _ep(s)} for s in grid],
        "grid_type": "3x3",
        "match": best,
        "multiplier": mult,
        "winnings": winnings,
        "result": result,
        "win_lines": win_line_indices,
        "win_line_symbols": win_lines,
    }


def _scratch_card5(bet: int) -> Dict[str, Any]:
    """
    ALL Equipment & Item Emojis — 3×3 grid, all 8 lines.
    2-match → x10, 3-match → x25.
    BONUS: if two 3-match lines share the same item type group → extra multiplier.
    """
    grid = [random.choice(CARD5_POOL) for _ in range(9)]
    best, win_lines = _best_match_3x3(grid)

    # Determine bonus
    bonus_group = None
    bonus_mult = 1.0
    if best == 3:
        bonus_group = _card5_type_bonus(grid, win_lines)
        if bonus_group:
            bonus_mult = 3.0  # triple the payout for same-type double 3-match

    if best == 3:
        base_mult = 25.0
        if bonus_group:
            mult = base_mult * bonus_mult
            result = f"DOUBLE {bonus_group} 3-match! {mult:.0f}× XP BONUS!"
        else:
            mult = base_mult
            result = "3 Items in a line! 25× XP!"
    elif best == 2:
        mult = 10.0
        result = "2 Items in a line! 10× XP!"
    else:
        mult = 0.0
        result = "No match. Better luck next time!"

    winnings = int(bet * mult)
    all_lines = _lines_3x3(grid)
    win_line_indices = []
    for wl in win_lines:
        for i, al in enumerate(all_lines):
            if al == wl:
                win_line_indices.append(i)
                break

    return {
        "symbols": [{"name": s, "path": _ep(s)} for s in grid],
        "grid_type": "3x3",
        "match": best,
        "multiplier": mult,
        "winnings": winnings,
        "result": result,
        "win_lines": win_line_indices,
        "win_line_symbols": win_lines,
        "bonus_group": bonus_group,
        "bonus_mult": bonus_mult,
        "symbol_types": {s: _CARD5_TYPE.get(s, "Unknown") for s in grid},
    }


_CARD_FUNCS = {
    1: _scratch_card1,
    2: _scratch_card2,
    3: _scratch_card3,
    4: _scratch_card4,
    5: _scratch_card5,
}

CARD_INFO = {
    1: {
        "name": "Type Scratch",
        "icon": "🌊",
        "desc": "3 Pet Types — 2 match: 1.2× · 3 match: 2×",
        "pool_size": len(CARD1_POOL),
        "grid": "1×3",
        "two_mult": 1.2,
        "three_mult": 2.0,
    },
    2: {
        "name": "Unit Scratch",
        "icon": "⚔️",
        "desc": "6 Military Units — 2 match: 1.5× · 3 match: 5×",
        "pool_size": len(CARD2_POOL),
        "grid": "1×3",
        "two_mult": 1.5,
        "three_mult": 5.0,
    },
    3: {
        "name": "Element Scratch",
        "icon": "🔥",
        "desc": "13 Elements — 2 match: 2.5× · 3 match: 7.5×",
        "pool_size": len(CARD3_POOL),
        "grid": "1×3",
        "two_mult": 2.5,
        "three_mult": 7.5,
    },
    4: {
        "name": "Pet Scratch",
        "icon": "🐾",
        "desc": "103 Pets — 3×3 all-ways · 2 match: 10× · 3 match: 25×",
        "pool_size": len(CARD4_POOL),
        "grid": "3×3",
        "two_mult": 10.0,
        "three_mult": 25.0,
    },
    5: {
        "name": "Item Scratch",
        "icon": "🎒",
        "desc": "All Items — 3×3 all-ways · 2 match: 10× · 3 match: 25× · Same-type double: 75×",
        "pool_size": len(CARD5_POOL),
        "grid": "3×3",
        "two_mult": 10.0,
        "three_mult": 25.0,
        "bonus_mult": 75.0,
    },
}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/casino/scratch/info")
def get_scratch_info():
    """Return card definitions and payout info."""
    return JSONResponse(content={"cards": CARD_INFO})


@router.post("/casino/scratch/play")
async def play_scratch(request: Request):
    """Scratch a card. Body: {card_type: 1-5, bet_amount: int, fun_mode: bool}"""
    try:
        data = await request.json()
        session_user = request.session.get("discord_user")
        if not session_user:
            return JSONResponse(content={"error": "Not logged in"}, status_code=401)
        user_id = str(session_user.get("id"))

        card_type = int(data.get("card_type", 1))
        bet_amount = int(data.get("bet_amount", 0))
        fun_mode = bool(data.get("fun_mode", False))

        if card_type not in range(1, 6):
            return JSONResponse(content={"error": "Invalid card type (1-5)"}, status_code=400)

        async with _get_user_lock(user_id):
            return await _play_scratch_inner(user_id, card_type, bet_amount, fun_mode)

    except Exception as e:
        logger.error(f"Scratch play error: {e}", exc_info=True)
        return JSONResponse(content={"error": "Scratch play failed"}, status_code=500)


async def _play_scratch_inner(user_id: str, card_type: int, bet_amount: int, fun_mode: bool):
    pet_data = await user_data_manager.get_pet_data_async(user_id)
    if not pet_data:
        return JSONResponse(content={"error": "No pet found"}, status_code=404)

    if not fun_mode:
        if bet_amount < 10:
            return JSONResponse(content={"error": "Minimum bet is 10 XP"}, status_code=400)
        total_xp = _compute_total_xp(pet_data)
        if bet_amount > total_xp:
            return JSONResponse(content={"error": "Insufficient XP"}, status_code=400)
        await LootCalculator.apply_xp_change(int(user_id), -bet_amount, source="scratch_bet")

    # Generate the card result
    card_fn = _CARD_FUNCS[card_type]
    result = card_fn(bet_amount if not fun_mode else 1000)

    winnings = result["winnings"] if not fun_mode else 0

    if not fun_mode and winnings > 0:
        await LootCalculator.apply_xp_change(int(user_id), winnings, source="scratch_win")

    if not fun_mode:
        net = winnings - bet_amount
        await user_data_manager.update_pet_gambling_stats(
            user_id, "scratch_cards", net, bet_amount=bet_amount
        )

    # Task tracking
    try:
        from web.api.tasks_api import record_action as _task_record
        await _task_record(user_id, "scratch_card")
    except Exception:
        pass

    result["fun_mode"] = fun_mode
    result["card_type"] = card_type
    if fun_mode:
        result["winnings"] = 0
    return JSONResponse(content=result)
