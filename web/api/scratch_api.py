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
from Systems.Pets.Logic.event_bus import EventQueue
from Systems.Pets.Logic.pet_components import AnimationComponent
from web.api.pets.gpp_helpers import _invalidate_stats_cache, _compute_total_xp, _get_user_lock

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Emoji pools ───────────────────────────────────────────────────────────────

def _ep(name: str) -> str:
    """Return the static image path for an emoji name."""
    _HATS = {
        "boater","aviator","ushanka","bearskin","turban","bowler","beret","nursing","gat",
        "peaked","stovepipe","capotain","keffiyeh","mortarboard","fool","safety","pith",
        "toque","rice","beanie","santa","ballcap","fez","service","tricorne","mitre",
        "sombrero","fedora","sorcerer","cattleman",
        "knights","necromancer","tank","jet","ship","rps","rock_1","paper","scissor",
    }
    _GEMS = {
        "EmberHeart","MintGaze","EmeraldSoul","ForestEye","SolarSphere","SkySpire",
        "ZephyrShard","AzureApex","MagmaDiamond","PrismaticFlux","FrostShard","EmberCube",
        "JadeSlab","FluxDiamond","MoonQuartz","FuryRose","SolarCore","VoidSpark",
        "GildedPrism","OceanTear",
    }
    _MATERIALS = {
        "Dirt","Sand","Leaf","Stone","Bone","Fabric","Leather","Glass","Wood","Brick",
        "Gold","Steel","plutonium","Smart","Laser",
    }
    _MONSTERS = {
        "Dwep","Krep","Bood","Lozd","Yoa","Nad","Ztuk","Gufi","Rowr","Jle","Zlik","Sili",
        "Qizi","Pir","Wirm","Dodl","Dwim","Zhy","Felr","Drak","Bliz","Smuj","Dvod","Neri",
        "Fwit","Plat","Mok","Jlum","Itle",
    }
    _POTIONS = {
        "basic_potion","fire_potion","water_potion","electric_potion","ice_potion",
        "air_potion","rock_potion","plant_potion","magic_potion","holy_potion",
        "necro_potion","psychic_potion","fighting_potion","mega_potion",
        "greater_health_potion","health_potion","lesser_health_potion","xp_potion",
        "lesser_xp_potion","luck_potion","att_potion","def_potion","dex_potion",
        "int_potion","hap_potion","ene_potion","s1_potion","s2_potion","s3_potion",
    }
    # Keys/Chests stay in Equipment root
    _EQUIPMENT_ROOT = {"Key1","Key2","Key3","chest1","chest2","chest3","chest4"}

    if name in _HATS:
        return f"/static/Emojis/Pets/Equipment/Hats/{name}.png"
    if name in _GEMS:
        return f"/static/Emojis/Pets/Equipment/Gems/{name}.png"
    if name in _MATERIALS:
        return f"/static/Emojis/Pets/Equipment/Materials/{name}.png"
    if name in _MONSTERS:
        return f"/static/Emojis/Pets/Equipment/Monsters/{name}.png"
    if name in _POTIONS:
        return f"/static/Emojis/Pets/Equipment/Potions/{name}.png"
    if name in _EQUIPMENT_ROOT:
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

    # Equipment set-based items (Card 6 & 7): "Wood Boots" -> Boots/Boots_Wood.png
    _equip_suffixes = {
        "Boots":   ("Boots",   "Boots"),
        "Helmet":  ("Helmets", "Helmet"),
        "Armor":   ("Armor",   "Armor"),
        "Shield":  ("Shield",  "Shield"),
        "Dagger":  ("Dagger",  "Dagger"),
        "Sword":   ("Sword",   "Sword"),
        "Katana":  ("Katana",  "Katana"),
        "Axe":     ("Axe",     "Axe"),
        "Hammer":  ("Hammers", "Hammer"),
        "Bow":     ("Bows",    "Bow"),
    }
    for suffix, (directory, prefix) in _equip_suffixes.items():
        if name.endswith(" " + suffix):
            if name == "Elven Katana":
                return "/static/Emojis/Pets/Equipment/Katana/Elven_Katana.png"
            set_part = name[:-(len(suffix) + 1)].replace(" ", "")
            return f"/static/Emojis/Pets/Equipment/{directory}/{prefix}_{set_part}.png"

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
    """For a 1×3 row: return 3 if all match, 2 if exactly two match, else 0.
    Matching is by exact symbol name."""
    counts: Dict[str, int] = {}
    for s in symbols:
        counts[s] = counts.get(s, 0) + 1
    best = max(counts.values())
    if best == 3:
        return 3
    if best == 2:
        return 2
    return 0


def _count_matches_1x3_typed(symbols: List[str]) -> Tuple[int, Optional[str]]:
    """For Card 5: match by TYPE GROUP (any 2+ items of the same type count).
    Returns (match_count, matched_type_or_None).
    3 = all three same type, 2 = exactly two same type, 0 = no match."""
    type_counts: Dict[str, int] = {}
    for s in symbols:
        t = _CARD5_TYPE.get(s)
        if t:
            type_counts[t] = type_counts.get(t, 0) + 1
    if not type_counts:
        return 0, None
    best_type = max(type_counts, key=lambda k: type_counts[k])
    best = type_counts[best_type]
    if best >= 3:
        return 3, best_type
    if best == 2:
        return 2, best_type
    return 0, None


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


def _score_all_lines_3x3(grid: List[str], typed: bool = False) -> Tuple[int, List[Tuple[List[str], Optional[str]]], List[Tuple[List[str], Optional[str]]]]:
    """
    Score ALL 8 lines independently.
    If typed=True (Card 5), matching is by item TYPE GROUP instead of exact symbol.
    Returns (best_match_count, three_match_lines, two_match_lines).
    Each entry in three/two_match_lines is (line_symbols, matched_type_or_None).
    """
    lines = _lines_3x3(grid)
    three_lines: List[Tuple[List[str], Optional[str]]] = []
    two_lines:   List[Tuple[List[str], Optional[str]]] = []
    for line in lines:
        if typed:
            m, matched_type = _count_matches_1x3_typed(line)
        else:
            m = _count_matches_1x3(line)
            matched_type = None
        if m == 3:
            three_lines.append((line, matched_type))
        elif m == 2:
            two_lines.append((line, matched_type))
    best = 3 if three_lines else (2 if two_lines else 0)
    return best, three_lines, two_lines


def _best_match_3x3(grid: List[str]) -> Tuple[int, List[List[str]]]:
    """
    Legacy helper — returns (best_match_count, winning_lines_at_best_tier).
    """
    best, three_lines, two_lines = _score_all_lines_3x3(grid)
    if three_lines:
        return 3, [ln for ln, _ in three_lines]
    if two_lines:
        return 2, [ln for ln, _ in two_lines]
    return 0, []


# ── Card 5 bonus: same-type group matches ────────────────────────────────────

def _card5_type_bonus(three_lines: List[Tuple[List[str], Optional[str]]]) -> Optional[str]:
    """
    If two or more 3-match lines share the same item type group, return that group name.
    Works with the typed line tuples from _score_all_lines_3x3(typed=True).
    """
    if not three_lines:
        return None
    type_counts: Dict[str, int] = {}
    for _line, matched_type in three_lines:
        if matched_type:
            type_counts[matched_type] = type_counts.get(matched_type, 0) + 1
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
    """Pet Emojis — 3×3 grid, all 8 lines. Each winning line pays independently.
    2-match line → x10 per line, 3-match line → x25 per line.
    Matching is by exact pet species."""
    grid = [random.choice(CARD4_POOL) for _ in range(9)]
    best, three_tuples, two_tuples = _score_all_lines_3x3(grid, typed=False)

    three_lines = [ln for ln, _ in three_tuples]
    two_lines   = [ln for ln, _ in two_tuples]
    three_count = len(three_lines)
    two_count   = len(two_lines)

    mult     = three_count * 25.0 + two_count * 10.0
    winnings = int(bet * mult)

    if three_count and two_count:
        result = (f"{three_count}×3-match + {two_count}×2-match! "
                  f"{three_count}×25 + {two_count}×10 = {mult:.0f}× XP!")
    elif three_count > 1:
        result = f"{three_count} lines of 3 Pets! {three_count}×25 = {mult:.0f}× XP!"
    elif three_count == 1:
        result = "3 Pets in a line! 25× XP!"
    elif two_count > 1:
        result = f"{two_count} lines of 2 Pets! {two_count}×10 = {mult:.0f}× XP!"
    elif two_count == 1:
        result = "2 Pets in a line! 10× XP!"
    else:
        result = "No match. Better luck next time!"

    all_win_lines = three_lines + two_lines
    all_lines = _lines_3x3(grid)
    win_line_indices = []
    for wl in all_win_lines:
        for i, al in enumerate(all_lines):
            if al == wl and i not in win_line_indices:
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
        "win_line_symbols": all_win_lines,
        "three_line_count": three_count,
        "two_line_count": two_count,
    }


def _scratch_card5(bet: int) -> Dict[str, Any]:
    """
    ALL Equipment & Item Emojis — 3×3 grid, all 8 lines scored independently.

    Each line can win by:
      • Exact symbol match (harder)  — 2 same = 10×, 3 same = 25× per line
      • Same type group  (easier)    — 2 same type = 4×, 3 same type = 8× per line
        (type match only fires when the line has NO exact-symbol match)

    All winning lines stack. Type-bonus still applies when 2+ exact-3-match lines
    share the same item type group (×3 on those lines).
    """
    grid = [random.choice(CARD5_POOL) for _ in range(9)]
    all_lines_syms = _lines_3x3(grid)

    # Per-line scoring
    # line_results: list of dicts per line index
    exact_three: List[Tuple[int, List[str], Optional[str]]] = []  # (line_idx, syms, type)
    exact_two:   List[Tuple[int, List[str], Optional[str]]] = []
    type_three:  List[Tuple[int, List[str], str]]            = []
    type_two:    List[Tuple[int, List[str], str]]            = []

    for li, line in enumerate(all_lines_syms):
        # Try exact match first
        exact_m = _count_matches_1x3(line)
        if exact_m == 3:
            exact_three.append((li, line, None))
            continue
        if exact_m == 2:
            exact_two.append((li, line, None))
            continue
        # No exact match — try type match
        type_m, matched_type = _count_matches_1x3_typed(line)
        if type_m == 3 and matched_type:
            type_three.append((li, line, matched_type))
        elif type_m == 2 and matched_type:
            type_two.append((li, line, matched_type))

    # Type bonus: 2+ exact-3-match lines sharing the same type group → ×3 on those lines
    bonus_group: Optional[str] = None
    if len(exact_three) >= 2:
        type_counts: Dict[str, int] = {}
        for _li, line, _ in exact_three:
            # All 3 symbols are the same exact item, so they share one type
            t = _CARD5_TYPE.get(line[0])
            if t:
                type_counts[t] = type_counts.get(t, 0) + 1
        for t, cnt in type_counts.items():
            if cnt >= 2:
                bonus_group = t
                break

    bonus_mult = 3.0 if bonus_group else 1.0

    # Calculate total multiplier
    # Exact 3-match lines: 25× each (×3 if bonus_group applies to that line)
    exact_three_pay = 0.0
    for _li, line, _ in exact_three:
        line_mult = 25.0
        if bonus_group and _CARD5_TYPE.get(line[0]) == bonus_group:
            line_mult *= bonus_mult
        exact_three_pay += line_mult

    exact_two_pay = len(exact_two) * 10.0
    type_three_pay = len(type_three) * 8.0
    type_two_pay   = len(type_two)   * 4.0
    mult = exact_three_pay + exact_two_pay + type_three_pay + type_two_pay
    winnings = int(bet * mult)

    # Collect all winning line indices for frontend highlighting
    win_line_indices = (
        [li for li, _, _ in exact_three] +
        [li for li, _, _ in exact_two]   +
        [li for li, _, _ in type_three]  +
        [li for li, _, _ in type_two]
    )
    all_win_line_syms = (
        [line for _, line, _ in exact_three] +
        [line for _, line, _ in exact_two]   +
        [line for _, line, _ in type_three]  +
        [line for _, line, _ in type_two]
    )

    # Counts for message + frontend badge
    e3 = len(exact_three)
    e2 = len(exact_two)
    t3 = len(type_three)
    t2 = len(type_two)
    total_wins = e3 + e2 + t3 + t2

    # Build result message
    if total_wins == 0:
        result = "No match. Better luck next time!"
    elif bonus_group:
        result = (f"DOUBLE {bonus_group} 3-match BONUS! "
                  f"{e3}×25×{bonus_mult:.0f}"
                  + (f" + {e2}×10" if e2 else "")
                  + (f" + {t3}×8" if t3 else "")
                  + (f" + {t2}×4" if t2 else "")
                  + f" = {mult:.0f}× XP!")
    else:
        parts = []
        if e3: parts.append(f"{e3}×exact-3 ({e3*25:.0f}×)")
        if e2: parts.append(f"{e2}×exact-2 ({e2*10:.0f}×)")
        if t3: parts.append(f"{t3}×type-3 ({t3*8:.0f}×)")
        if t2: parts.append(f"{t2}×type-2 ({t2*4:.0f}×)")
        result = " + ".join(parts) + f" = {mult:.0f}× XP!" if parts else "No match."

    best = 3 if (e3 or t3) else (2 if (e2 or t2) else 0)

    return {
        "symbols":          [{"name": s, "path": _ep(s)} for s in grid],
        "grid_type":        "3x3",
        "match":            best,
        "multiplier":       mult,
        "winnings":         winnings,
        "result":           result,
        "win_lines":        win_line_indices,
        "win_line_symbols": all_win_line_syms,
        "bonus_group":      bonus_group,
        "bonus_mult":       bonus_mult,
        # Breakdown counts for frontend badge
        "exact_three_count": e3,
        "exact_two_count":   e2,
        "type_three_count":  t3,
        "type_two_count":    t2,
        "three_line_count":  e3 + t3,   # total 3-match lines (exact + type)
        "two_line_count":    e2 + t2,   # total 2-match lines (exact + type)
        "symbol_types":      {s: _CARD5_TYPE.get(s, "Unknown") for s in grid},
    }


# ── Set-based equipment helpers (Card 6 & 7) ────────────────────────────────

_SETS = ["Wood", "Rusty Iron", "Stone", "Iron", "Nature", "Elven", "Steel",
         "Crystal", "Volcanic", "Advanced", "SciFi"]

def _eq_name(set_name: str, equip_type: str) -> str:
    """Generate display name for an equipment item by set + type.
    e.g. ("Wood", "Boots") -> "Wood Boots"
         ("Nature", "Bow") -> "Natural Bow"
    """
    if set_name == "Nature" and equip_type in ("Bow", "Dagger"):
        return f"Natural {equip_type}"
    return f"{set_name} {equip_type}"


def _get_set(name: str) -> str:
    """Extract the material set from an equipment display name.
    "Wood Boots" -> "Wood", "Rusty Iron Boots" -> "Rusty Iron"
    """
    for t in ("Helmet", "Armor", "Boots", "Shield",
              "Dagger", "Sword", "Katana", "Axe", "Hammer", "Bow"):
        if name.endswith(" " + t):
            return name[:-(len(t) + 1)]
    return name


def _scratch_card6(bet: int) -> Dict[str, Any]:
    """
    Defense Scratchoff — 1×4 row: Helmet, Armor, Boots, Shield.
    Match by set (material). 3+ match: 4×, 4 match: 20×.
    """
    types = ["Helmet", "Armor", "Boots", "Shield"]

    target = random.choice(_SETS)

    # Determine how many slots match the target set
    roll = random.random()
    if roll < 0.03:
        # All 4 match
        symbols = [_eq_name(target, t) for t in types]
        best_count = 4
    elif roll < 0.18:
        # Exactly 3 match
        match_idx = random.sample(range(4), 3)
        symbols = []
        for i, t in enumerate(types):
            if i in match_idx:
                symbols.append(_eq_name(target, t))
            else:
                other = random.choice([s for s in _SETS if s != target])
                symbols.append(_eq_name(other, t))
        best_count = 3
    else:
        # 0-2 match — no payout.  Generate with low odds of accidental 3+
        symbols = []
        for t in types:
            if random.random() < 0.15:
                symbols.append(_eq_name(target, t))
            else:
                other = random.choice([s for s in _SETS if s != target])
                symbols.append(_eq_name(other, t))
        # Count actual matches
        set_counts: Dict[str, int] = {}
        for s in symbols:
            ss = _get_set(s)
            set_counts[ss] = set_counts.get(ss, 0) + 1
        best_count = max(set_counts.values())

    # Shuffle so matching items are spaced
    random.shuffle(symbols)

    # Re-count after shuffle
    set_counts: Dict[str, int] = {}
    for s in symbols:
        ss = _get_set(s)
        set_counts[ss] = set_counts.get(ss, 0) + 1
    best_set = max(set_counts, key=lambda k: set_counts[k])
    best_count = set_counts[best_set]

    if best_count >= 4:
        mult = 20.0
        result = "FULL DEFENSE SET! All 4 armor pieces match! 20× XP!"
    elif best_count >= 3:
        mult = 4.0
        result = f"Partial set! {best_count} of 4 matching — 4× XP!"
    else:
        mult = 0.0
        result = "No matching set. Better luck next time!"

    winnings = int(bet * mult)
    win_indices = [i for i, s in enumerate(symbols) if _get_set(s) == best_set] if best_count >= 3 else []

    return {
        "symbols":     [{"name": s, "path": _ep(s)} for s in symbols],
        "grid_type":   "1x4",
        "match":       best_count,
        "multiplier":  mult,
        "winnings":    winnings,
        "result":      result,
        "win_lines":   [win_indices] if win_indices else [],
        "match_set":   best_set if best_count >= 3 else None,
    }


def _scratch_card7(bet: int) -> Dict[str, Any]:
    """
    Offense Scratchoff — 1×6 row: Dagger, Sword, Katana, Axe, Hammer, Bow.
    Match by set (material). 4-5 match: 6×, 6 match: 50×.
    """
    types = ["Dagger", "Sword", "Katana", "Axe", "Hammer", "Bow"]

    target = random.choice(_SETS)

    roll = random.random()
    if roll < 0.015:
        # All 6 match
        symbols = [_eq_name(target, t) for t in types]
        best_count = 6
    elif roll < 0.08:
        # 5 match
        match_idx = random.sample(range(6), 5)
        symbols = []
        for i, t in enumerate(types):
            if i in match_idx:
                symbols.append(_eq_name(target, t))
            else:
                other = random.choice([s for s in _SETS if s != target])
                symbols.append(_eq_name(other, t))
        best_count = 5
    elif roll < 0.22:
        # 4 match
        match_idx = random.sample(range(6), 4)
        symbols = []
        for i, t in enumerate(types):
            if i in match_idx:
                symbols.append(_eq_name(target, t))
            else:
                other = random.choice([s for s in _SETS if s != target])
                symbols.append(_eq_name(other, t))
        best_count = 4
    else:
        # 0-3 match
        symbols = []
        for t in types:
            if random.random() < 0.12:
                symbols.append(_eq_name(target, t))
            else:
                other = random.choice([s for s in _SETS if s != target])
                symbols.append(_eq_name(other, t))
        set_counts: Dict[str, int] = {}
        for s in symbols:
            ss = _get_set(s)
            set_counts[ss] = set_counts.get(ss, 0) + 1
        best_count = max(set_counts.values())

    # Shuffle
    random.shuffle(symbols)

    # Re-count
    set_counts: Dict[str, int] = {}
    for s in symbols:
        ss = _get_set(s)
        set_counts[ss] = set_counts.get(ss, 0) + 1
    best_set = max(set_counts, key=lambda k: set_counts[k])
    best_count = set_counts[best_set]

    if best_count >= 6:
        mult = 50.0
        result = "FULL WEAPON RACK! All 6 weapons match! 50× XP!"
    elif best_count >= 5:
        mult = 6.0
        result = f"Strong arsenal! {best_count} of 6 matching — 6× XP!"
    elif best_count >= 4:
        mult = 6.0
        result = f"Weapon set! {best_count} of 6 matching — 6× XP!"
    else:
        mult = 0.0
        result = "No matching weapon set. Better luck next time!"

    winnings = int(bet * mult)
    win_indices = [i for i, s in enumerate(symbols) if _get_set(s) == best_set] if best_count >= 4 else []

    return {
        "symbols":     [{"name": s, "path": _ep(s)} for s in symbols],
        "grid_type":   "1x6",
        "match":       best_count,
        "multiplier":  mult,
        "winnings":    winnings,
        "result":      result,
        "win_lines":   [win_indices] if win_indices else [],
        "match_set":   best_set if best_count >= 4 else None,
    }


_CARD_FUNCS = {
    1: _scratch_card1,
    2: _scratch_card2,
    3: _scratch_card3,
    4: _scratch_card4,
    5: _scratch_card5,
    6: _scratch_card6,
    7: _scratch_card7,
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
        "desc": "All Items — 3×3 all-ways · Exact 2: 10× · Exact 3: 25× · Type 2: 4× · Type 3: 8× · Same-type double: 75×",
        "pool_size": len(CARD5_POOL),
        "grid": "3×3",
        "two_mult": 10.0,
        "three_mult": 25.0,
        "type_two_mult": 4.0,
        "type_three_mult": 8.0,
        "bonus_mult": 75.0,
    },
    6: {
        "name": "Defense Scratch",
        "icon": "🛡️",
        "desc": "11 Armor Sets — Helmet, Armor, Boots, Shield · 3 match: 4× · 4 match: 20×",
        "pool_size": len(_SETS),
        "grid": "1×4",
        "four_mult": 20.0,
        "three_mult": 4.0,
    },
    7: {
        "name": "Offense Scratch",
        "icon": "⚔️",
        "desc": "11 Weapon Sets — 6 weapon types · 4+ match: 6× · 6 match: 50×",
        "pool_size": len(_SETS),
        "grid": "1×6",
        "six_mult": 50.0,
        "four_mult": 6.0,
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

        if card_type not in range(1, 8):
            return JSONResponse(content={"error": "Invalid card type (1-7)"}, status_code=400)

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

    # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
    queue = EventQueue()
    queue.push("scratch_play", {"user_id": user_id, "card_type": card_type, "winnings": result.get("winnings", 0)})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("scratch_reveal", 500, {"card_type": card_type, "winnings": result.get("winnings", 0)})

    result["fun_mode"] = fun_mode
    result["card_type"] = card_type
    if fun_mode:
        result["winnings"] = 0
    result["animation"] = animation
    return JSONResponse(content=result)
