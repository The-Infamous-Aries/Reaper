from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
import asyncio
import random
import logging
from typing import Dict, List, Optional, Any

from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.pet_brain import LootCalculator
from Systems.Pets.PetGames.blackjack import BlackjackSession
from Systems.Pets.PetGames.holdem import HoldemSession
from Systems.Pets.PetGames.craps import CrapsSession
from Systems.Pets.PetGames.slots import SlotMachineView, get_emojis_for_difficulty, PAYOUTS
from Systems.Pets.PetGames.races import RaceSession

logger = logging.getLogger(__name__)

casino_api = APIRouter()

# ── Per-user locks ────────────────────────────────────────────────────────────
_user_locks: Dict[str, asyncio.Lock] = {}

def _get_user_lock(user_id: str) -> asyncio.Lock:
    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()
    return _user_locks[user_id]

def compute_total_xp(pet_data: dict) -> int:
    """Total XP = cumulative XP to reach current level + current level's remaining XP."""
    lvl = int(pet_data.get("level", 1))
    rem = int(pet_data.get("experience", 0))
    return int(LootCalculator.get_total_experience_for_level(lvl)) + rem

# Emoji categories for slots
# Matches Discord emoji.py CATEGORIES — keys map to static file paths
EMOJI_CATEGORIES = {
    'Pet Type':  ['Flying', 'Land', 'Swimming'],
    'Slots':     ['soldier', 'tank', 'jet', 'ship', 'knights', 'necromancer'],
    'Stats':     ['ATT', 'DEF', 'DEX', 'INT', 'HAP', 'ENE'],
    'Elements':  ['Air', 'Basic', 'Electric', 'Fire', 'Holy', 'Ice', 'Magic', 'Necro', 'Plant', 'Rock', 'Water', 'Psychic', 'Fighting'],
    'Pets': [
        'Alligator','Ant','Anteater','Axolotl','Badger','Bat','Beaver','Bee','Beetle','Bison','BlueTang','Camel','Cardinal','Cat','Centipede','Cheetah','Chicken','Clownfish','Cow','Crab','Crow','Deer','Dog','Dolphin','Duck','Eagle','Elephant','Emu','Firefly','Fox','Frog','Giraffe','Goat','Goose','Gorilla','Grizzly','Hamster','Hedgehog','Hippo','Horse','Hummingbird','Iguana','Jaguar','Jellyfish','Kangaroo','Kiwi','Koala','Ladybug','Lemur','Leopard','Lion','Llama','Mantis','Monkey','Mouse','Octopus','Orangutan','Orca','Ostrich','Otter','Owl','Panda','Parrot','Peacock','Pelican','Penguin','Pig','Pigeon','Platypus','PolarBear','Pufferfish','Rabbit','Raccoon','Ram','Rat','RedPanda','Reindeer','Rhino','Salmon','Scorpion','Seahorse','Seal','Shark','Sheep','Shrimp','Skunk','Sloth','Snail','Snake','Spider','Squirrel','Starfish','Stingray','SugarGlider','Tiger','Toucan','Turkey','Turtle','Walrus','Whale','Wolf','Yak','Zebra'
    ]
}

# RPS folder has: knights, necromancer, archer, tank, jet, ship, soldier (via Military)
_RPS_NAMES = {'knights', 'necromancer', 'archer', 'rps', 'rock_1', 'paper', 'scissor'}
_MILITARY_NAMES = {'soldier', 'tank', 'jet', 'ship', 'spy', 'missile', 'bomb', 'fortification', 'strategy', 'wars', 'raid', 'attrition', 'draw', 'lose', 'win', 'peace', 'peace_1'}

def get_emoji_file_path(emoji_name: str) -> str:
    """Return the correct static file path for an emoji."""
    if emoji_name in _RPS_NAMES:
        return f"/static/Emojis/RPS/{emoji_name}.png"
    if emoji_name in _MILITARY_NAMES:
        return f"/static/Emojis/Military/{emoji_name}.png"
    # Check Pets folder (exact case match)
    pets = EMOJI_CATEGORIES['Pets']
    if emoji_name in pets:
        return f"/static/Emojis/Pets/{emoji_name}.png"
    # Everything else lives in Pets/Deco (Pet Type, Stats, Elements)
    return f"/static/Emojis/Pets/Deco/{emoji_name}.png"

# SLOTS ENDPOINTS
@casino_api.get('/casino/xp')
async def get_casino_xp(request: Request):
    """Return the current user's total XP and pet info for the casino."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))
    pet_data = await user_data_manager.get_pet_data_async(user_id)
    if not pet_data:
        return JSONResponse(content={"has_pet": False, "total_xp": 0})
    total_xp = compute_total_xp(pet_data)
    return JSONResponse(content={
        "has_pet": True,
        "total_xp": total_xp,
        "level": pet_data.get("level", 1),
        "experience": pet_data.get("experience", 0),
        "name": pet_data.get("name", ""),
        "species": pet_data.get("species", ""),
        "element": pet_data.get("element", "basic"),
    })

@casino_api.get('/casino/slots/odds')
def get_slots_odds():
    """Return odds information for all slot themes"""
    odds_info = {
        "Very Easy": {"total_emojis": 3, "three_match_odds": "1 in 9", "two_match_odds": "1 in 3"},
        "Easy": {"total_emojis": 4, "three_match_odds": "1 in 16", "two_match_odds": "1 in 4"},
        "Medium": {"total_emojis": 6, "three_match_odds": "1 in 36", "two_match_odds": "1 in 6"},
        "Hard": {"total_emojis": 13, "three_match_odds": "1 in 169", "two_match_odds": "1 in 13"},
        "Very Hard": {"total_emojis": 95, "three_match_odds": "1 in 9,025", "two_match_odds": "1 in 95"},
        "Insanity": {"total_emojis": "100+", "three_match_odds": "1 in 10,000+", "two_match_odds": "1 in 100+"},
    }
    return JSONResponse(content=odds_info)

@casino_api.get('/casino/slots/emojis/{theme}')
def get_slots_emojis(theme: str):
    """Return emojis for a given theme"""
    theme_map = {
        'Very Easy': 'Pet Type',
        'Easy': 'Slots',
        'Medium': 'Stats',
        'Hard': 'Elements',
        'Very Hard': 'Pets',
        'Insanity': ['Pets', 'Pet Type', 'Slots', 'Stats', 'Elements']
    }

    emoji_category = theme_map.get(theme)
    emojis = []

    if isinstance(emoji_category, list):
        for category in emoji_category:
            emojis.extend(EMOJI_CATEGORIES.get(category, []))
    elif emoji_category:
        emojis = EMOJI_CATEGORIES.get(emoji_category, [])

    if not emojis:
        return JSONResponse(content={'error': f'No emojis found for theme {theme}'}, status_code=400)

    response_emojis = [
        {'name': e, 'path': get_emoji_file_path(e)} for e in emojis
    ]

    return JSONResponse(content={'emojis': response_emojis})

@casino_api.post('/casino/slots/spin')
async def spin_slots(request: Request):
    """Spin slots with XP betting"""
    try:
        data = await request.json()
        # Use session user — don't trust client-supplied user_id
        session_user = request.session.get("discord_user")
        if not session_user:
            return JSONResponse(content={"error": "Not logged in"}, status_code=401)
        user_id = str(session_user.get("id"))

        theme = data.get('theme')
        bet_amount = int(data.get('bet_amount', 0))
        fun_mode = data.get('fun_mode', False)

        async with _get_user_lock(user_id):
            return await _spin_slots_inner(request, user_id, theme, bet_amount, fun_mode)

    except Exception as e:
        logger.error(f"Error in slots spin: {e}")
        return JSONResponse(content={'error': 'Spin failed'}, status_code=500)


async def _spin_slots_inner(request: Request, user_id: str, theme: str, bet_amount: int, fun_mode: bool):
    # Get user pet data
    pet_data = await user_data_manager.get_pet_data_async(user_id)
    if not pet_data:
        return JSONResponse(content={'error': 'No pet found'}, status_code=404)

    # Check XP balance if not fun mode
    if not fun_mode:
        total_xp = compute_total_xp(pet_data)
        if bet_amount > total_xp:
            return JSONResponse(content={'error': 'Insufficient XP'}, status_code=400)
        # Deduct bet amount
        await LootCalculator.apply_xp_change(int(user_id), -bet_amount, source="slots_bet")

    # Get emojis for theme
    theme_map = {
        'Very Easy': 'Pet Type',
        'Easy': 'Slots',
        'Medium': 'Stats',
        'Hard': 'Elements',
        'Very Hard': 'Pets',
        'Insanity': ['Pets', 'Pet Type', 'Slots', 'Stats', 'Elements']
    }

    emoji_category = theme_map.get(theme)
    emojis = []

    if isinstance(emoji_category, list):
        for category in emoji_category:
            emojis.extend(EMOJI_CATEGORIES.get(category, []))
    elif emoji_category:
        emojis = EMOJI_CATEGORIES.get(emoji_category, [])

    if not emojis:
        return JSONResponse(content={'error': f'No emojis found for theme {theme}'}, status_code=400)

    # Handle Insanity mode (targeted reels)
    if theme == 'Insanity':
        # Get pet's attributes
        species = str(pet_data.get("species", "Cat"))
        pet_type = str(pet_data.get("category", "land")).lower()
        element1 = str(pet_data.get("element", "basic")).lower()
        element2_raw = str(pet_data.get("element2", "") or "").lower()
        element2 = element2_raw if element2_raw and element2_raw != "basic" else None

        # Determine reel count: 3 if single-element, 4 if dual-element
        has_dual_element = element2 is not None
        reel_count = 4 if has_dual_element else 3

        # Build emoji pools for each reel
        all_species = EMOJI_CATEGORIES.get('Pets', [])
        all_types = EMOJI_CATEGORIES.get('Pet Type', [])
        all_elements = EMOJI_CATEGORIES.get('Elements', [])

        # Spin each reel
        reel_results = []
        reel_results.append(random.choice(all_species))  # Reel 1: Species
        reel_results.append(random.choice(all_types))    # Reel 2: Type
        reel_results.append(random.choice(all_elements)) # Reel 3: Element 1
        if has_dual_element:
            reel_results.append(random.choice(all_elements))  # Reel 4: Element 2

        # Check if ALL reels match their requirements
        species_match = reel_results[0].lower() == species.lower()
        type_match = reel_results[1].lower() == pet_type
        element1_match = reel_results[2].lower() == element1
        element2_match = reel_results[3].lower() == element2 if has_dual_element else True

        all_requirements_met = species_match and type_match and element1_match and element2_match

        # Calculate payout based on odds
        # Odds: (1/num_species) × (1/num_types) × (1/num_elements) × (1/num_elements if dual)
        num_species = len(all_species)
        num_types = len(all_types)
        num_elements = len(all_elements)

        if has_dual_element:
            # 4 reels: 1/species × 1/type × 1/element × 1/element
            odds_denominator = num_species * num_types * num_elements * num_elements
        else:
            # 3 reels: 1/species × 1/type × 1/element
            odds_denominator = num_species * num_types * num_elements

        # Payout = odds × 0.8 (80% RTP for fairness)
        payout_multiplier = int(odds_denominator * 0.8)

        winnings = 0
        result_text = "Better luck next time!"

        if all_requirements_met:
            winnings = int(bet_amount * payout_multiplier)
            result_text = f"🎰 INSANITY JACKPOT! All {reel_count} reels matched!"

        if not fun_mode and winnings > 0:
            await LootCalculator.apply_xp_change(int(user_id), winnings, source="slots_win")
        if not fun_mode:
            net = winnings - bet_amount
            await user_data_manager.update_pet_gambling_stats(user_id, "slots", net, bet_amount=bet_amount)

        # Task tracking — play_slots
        try:
            from web.api.tasks_api import record_action as _task_record
            await _task_record(user_id, "play_slots")
        except Exception:
            pass

        return JSONResponse(content={
            'reels': [{'name': r, 'path': get_emoji_file_path(r)} for r in reel_results],
            'result_text': result_text,
            'winnings': winnings if not fun_mode else 0,
            'insanity_mode': True,
            'reel_count': reel_count,
            'requirements': {
                'species': species,
                'type': pet_type,
                'element1': element1,
                'element2': element2,
            },
            'matches': {
                'species': species_match,
                'type': type_match,
                'element1': element1_match,
                'element2': element2_match if has_dual_element else None,
            },
            'payout_multiplier': payout_multiplier,
        })
    else:
        # Regular slots
        reels_result = [random.choice(emojis) for _ in range(3)]

        all_match = len(set(reels_result)) == 1
        two_match = len(set(reels_result)) == 2

        winnings = 0
        payouts = PAYOUTS.get(theme.lower().replace(' ', '_'), PAYOUTS.get("very_easy", {"three": 0.0, "two": 0.0}))

        if all_match:
            winnings = int(bet_amount * payouts["three"])
            result_text = 'JACKPOT! 3 in a row!'
        elif two_match:
            winnings = int(bet_amount * payouts["two"])
            result_text = 'WIN! 2 in a row!'
        else:
            winnings = 0
            result_text = 'Better luck next time!'

        if not fun_mode and winnings > 0:
            await LootCalculator.apply_xp_change(int(user_id), winnings, source="slots_win")
        if not fun_mode:
            net = winnings - bet_amount
            await user_data_manager.update_pet_gambling_stats(user_id, "slots", net, bet_amount=bet_amount)

        # Task tracking — play_slots
        try:
            from web.api.tasks_api import record_action as _task_record
            await _task_record(user_id, "play_slots")
        except Exception:
            pass

        return JSONResponse(content={
            'reels': [{'name': r, 'path': get_emoji_file_path(r)} for r in reels_result],
            'result_text': result_text,
            'winnings': winnings if not fun_mode else 0,
            'insanity_mode': False
        })

# ── KENO ENDPOINTS ───────────────────────────────────────────────────────────

# Keno pools (same source as slots)
KENO_TYPES    = ['Flying', 'Land', 'Swimming']
KENO_ELEMENTS = ['Air', 'Basic', 'Electric', 'Fire', 'Holy', 'Ice', 'Magic', 'Necro', 'Plant', 'Rock', 'Water', 'Psychic', 'Fighting']
KENO_PETS     = EMOJI_CATEGORIES['Pets']  # 103 pets

# ── Payout tables (matching keno.js) ─────────────────────────────────────
# Pet draw: pick 10, bot draws 20 from 103
# Multipliers on bet for each match count (0-10)
_PET_PAYOUTS = {
    0: 0, 1: 0, 2: 0, 3: 0,
    4: 1.5,
    5: 3.5,
    6: 10,
    7: 35,
    8: 150,
    9: 800,
    10: 5000,
}

# Element draw: pick 3, bot draws 3 from 13
# Multiplier applied on top of base payout
_ELEMENT_MULTIPLIERS = {0: 1, 1: 1, 2: 2.5, 3: 8}

# Type draw: pick 1, bot draws 1 from 3
# MEGA multiplier stacked on top of element multiplier
_TYPE_MULTIPLIER = 5


@casino_api.get('/casino/keno/emojis')
def get_keno_emojis():
    """Return all emoji pools for Mega Keno."""
    return JSONResponse(content={
        'types':    [{'name': n, 'path': get_emoji_file_path(n)} for n in KENO_TYPES],
        'elements': [{'name': n, 'path': get_emoji_file_path(n)} for n in KENO_ELEMENTS],
        'pets':     [{'name': n, 'path': get_emoji_file_path(n)} for n in KENO_PETS],
    })


@casino_api.post('/casino/keno/play')
async def play_keno(request: Request):
    """Play a round of Mega Keno."""
    try:
        data = await request.json()
        session_user = request.session.get("discord_user")
        if not session_user:
            return JSONResponse(content={"error": "Not logged in"}, status_code=401)
        user_id = str(session_user.get("id"))

        bet_amount      = int(data.get('bet_amount', 0))
        fun_mode        = bool(data.get('fun_mode', False))
        picked_type     = str(data.get('picked_type', ''))
        picked_elements = list(data.get('picked_elements', []))
        picked_pets     = list(data.get('picked_pets', []))

        # Validate picks
        if picked_type not in KENO_TYPES:
            return JSONResponse(content={"error": "Invalid type selection"}, status_code=400)
        if len(picked_elements) != 3 or not all(e in KENO_ELEMENTS for e in picked_elements):
            return JSONResponse(content={"error": "Must pick exactly 3 valid elements"}, status_code=400)
        if len(picked_pets) != 10 or not all(p in KENO_PETS for p in picked_pets):
            return JSONResponse(content={"error": "Must pick exactly 10 valid pets"}, status_code=400)

        async with _get_user_lock(user_id):
            return await _play_keno_inner(user_id, bet_amount, fun_mode,
                                          picked_type, picked_elements, picked_pets)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"Keno play error: {e}\nFull traceback:\n{tb}")
        return JSONResponse(content={"error": "Keno play failed", "detail": str(e)}, status_code=500)


async def _play_keno_inner(user_id: str, bet_amount: int, fun_mode: bool,
                            picked_type: str, picked_elements: list, picked_pets: list):
    pet_data = await user_data_manager.get_pet_data_async(user_id)
    if not pet_data:
        return JSONResponse(content={"error": "No pet found"}, status_code=404)

    if not fun_mode:
        if bet_amount < 10:
            return JSONResponse(content={"error": "Minimum bet is 10 XP"}, status_code=400)
        total_xp = compute_total_xp(pet_data)
        if bet_amount > total_xp:
            return JSONResponse(content={"error": "Insufficient XP"}, status_code=400)
        await LootCalculator.apply_xp_change(int(user_id), -bet_amount, source="keno_bet")

    # ── Phase 1: Pet draw — bot picks 20 from 103 ─────────────────────────
    drawn_pets_names = random.sample(KENO_PETS, 20)
    drawn_pets       = [{'name': n, 'path': get_emoji_file_path(n)} for n in drawn_pets_names]
    pet_hits         = [n for n in picked_pets if n in drawn_pets_names]
    pet_matches      = len(pet_hits)

    base_mult   = _PET_PAYOUTS.get(pet_matches, 0)
    base_payout = int(bet_amount * base_mult) if not fun_mode else 0

    # ── Phase 2: Element draw — triggered if 4+ pet matches ──────────────
    element_draw_triggered = pet_matches >= 4
    drawn_elements   = []
    element_hits     = []
    element_matches  = 0
    element_multiplier = 1

    if element_draw_triggered:
        drawn_elem_names = random.sample(KENO_ELEMENTS, 3)
        drawn_elements   = [{'name': n, 'path': get_emoji_file_path(n)} for n in drawn_elem_names]
        element_hits     = [n for n in picked_elements if n in drawn_elem_names]
        element_matches  = len(element_hits)
        element_multiplier = _ELEMENT_MULTIPLIERS.get(element_matches, 1)

    # ── Phase 3: Type draw — triggered if 2+ element matches ─────────────
    type_draw_triggered = element_draw_triggered and element_matches >= 2
    drawn_type     = None
    type_hit       = False
    type_multiplier = 1

    if type_draw_triggered:
        drawn_type_name = random.choice(KENO_TYPES)
        drawn_type      = {'name': drawn_type_name, 'path': get_emoji_file_path(drawn_type_name)}
        type_hit        = drawn_type_name == picked_type
        type_multiplier = _TYPE_MULTIPLIER if type_hit else 1

    # ── Final payout calculation ──────────────────────────────────────────
    # Stacked: base × element_mult × type_mult
    total_multiplier = element_multiplier * type_multiplier
    total_winnings   = int(base_payout * total_multiplier) if not fun_mode else 0

    if not fun_mode and total_winnings > 0:
        # Apply ability tree effects
        modified_winnings = total_winnings
        try:
            pet_data = await user_data_manager.get_pet_data_async(user_id)
            if pet_data:
                from Systems.Pets.Logic.ability_tree import get_ability_effect
                # Apply casino win bonus
                win_mult = get_ability_effect(pet_data, "casino_xp_gain_mult", game="keno")
                if win_mult != 1.0:
                    modified_winnings = int(total_winnings * win_mult)
        except Exception:
            pass
        
        await LootCalculator.apply_xp_change(int(user_id), modified_winnings, source="keno_win")
    elif not fun_mode:
        # Apply loss reduction for losses
        try:
            pet_data = await user_data_manager.get_pet_data_async(user_id)
            if pet_data:
                from Systems.Pets.Logic.ability_tree import get_ability_effect
                loss_reduction = get_ability_effect(pet_data, "casino_xp_loss_reduction", game="keno")
                if loss_reduction > 0:
                    refund = int(bet_amount * loss_reduction)
                    if refund > 0:
                        await LootCalculator.apply_xp_change(int(user_id), refund, source="keno_loss_reduction")
        except Exception:
            pass

    if not fun_mode:
        net = total_winnings - bet_amount
        await user_data_manager.update_pet_gambling_stats(user_id, "keno", net, bet_amount=bet_amount)

    # ── Task tracking ─────────────────────────────────────────────────────
    try:
        from web.api.tasks_api import record_action as _task_record
        await _task_record(user_id, "play_keno")
    except Exception:
        pass

    return JSONResponse(content={
        # Pet draw
        'drawn_pets':    drawn_pets,
        'pet_hits':      pet_hits,
        'pet_matches':   pet_matches,
        'base_payout':   base_payout,
        # Element draw
        'element_draw_triggered': element_draw_triggered,
        'drawn_elements':   drawn_elements,
        'element_hits':     element_hits,
        'element_matches':  element_matches,
        'element_multiplier': element_multiplier,
        # Type draw
        'type_draw_triggered': type_draw_triggered,
        'drawn_type':     drawn_type,
        'type_hit':       type_hit,
        'type_multiplier': type_multiplier,
        # Final
        'total_winnings': total_winnings,
        'fun_mode':       fun_mode,
    })


# ── WHEEL OF PETS ENDPOINTS ──────────────────────────────────────────────────

# ── WHEEL MODES DATA ──────────────────────────────────────────────────────────

# All 103 pet species — must match info.json keys exactly
WHEEL_PETS: List[str] = [
    'Alligator','Ant','Anteater','Axolotl','Badger','Bat','Beaver','Bee','Beetle','Bison',
    'BlueTang','Camel','Cardinal','Cat','Centipede','Cheetah','Chicken','Clownfish','Cow',
    'Crab','Crow','Deer','Dog','Dolphin','Duck','Eagle','Elephant','Emu','Firefly','Fox',
    'Frog','Giraffe','Goat','Goose','Gorilla','Grizzly','Hamster','Hedgehog','Hippo',
    'Horse','Hummingbird','Iguana','Jaguar','Jellyfish','Kangaroo','Kiwi','Koala',
    'Ladybug','Lemur','Leopard','Lion','Llama','Mantis','Monkey','Mouse','Octopus',
    'Orangutan','Orca','Ostrich','Otter','Owl','Panda','Parrot','Peacock','Pelican',
    'Penguin','Pig','Pigeon','Platypus','PolarBear','Pufferfish','Rabbit','Raccoon',
    'Ram','Rat','RedPanda','Reindeer','Rhino','Salmon','Scorpion','Seahorse','Seal',
    'Shark','Sheep','Shrimp','Skunk','Sloth','Snail','Snake','Spider','Squirrel',
    'Starfish','Stingray','SugarGlider','Tiger','Toucan','Turkey','Turtle','Walrus',
    'Whale','Wolf','Yak','Zebra',
]

# Monsters - From equipment.json
WHEEL_MONSTERS: List[str] = [
    'Wirm','Dodl','Dwim','Zhy','Felr','Drak','Bliz','Smuj','Dvod','Neri',
    'Fwit','Plat','Mok','Jlum','Itle','Dwep','Krep','Bood','Lozd','Yoa',
    'Nad','Ztuk','Gufi','Rowr','Jle','Zlik','Sili','Pir','Qizi'
]

# Materials - From equipment.json
WHEEL_MATERIALS: List[str] = [
    'Dirt','Leaf','Sand','Bone','Fabric','Leather','Glass','Stone','Wood',
    'Brick','Gold','Steel','Laser','Plutonium','Smart'
]

# Gems - From equipment.json
WHEEL_GEMS: List[str] = [
    'EmberHeart','MintGaze','EmeraldSoul','ForestEye','SolarSphere','SkySpire',
    'ZephyrShard','AzureApex','MagmaDiamond','PrismaticFlux','FrostShard','EmberCube',
    'JadeSlab','FluxDiamond','MoonQuartz','FuryRose','SolarCore','VoidSpark',
    'GildedPrism','OceanTear'
]

# Hats - From equipment.json
WHEEL_HATS: List[str] = [
    'Boater','Aviator','Ushanka','Bearskin','Turban','Bowler','Beret','Nursing Cap',
    'Gat','Peaked Cap','Stovepipe','Capotain','Keffiyeh','Mortarboard','Fool\'s Cap',
    'Safety Helmet','Pith Helmet','Toque','Rice Hat','Beanie','Santa Hat','Ballcap',
    'Fez','Service Cap','Tricorne','Mitre','Sombrero','Fedora','Sorcerer Hat','Cattleman'
]

# Potions - From equipment.json
WHEEL_POTIONS: List[str] = [
    'ATT Potion','DEF Potion','DEX Potion','ENE Potion','HAP Potion','INT Potion',
    'Air Potion','Basic Potion','Electric Potion','Fighting Potion','Fire Potion',
    'Holy Potion','Ice Potion','Magic Potion','Necro Potion','Plant Potion',
    'Psychic Potion','Rock Potion','Water Potion','S1 Potion','S2 Potion','S3 Potion',
    'Luck Potion','Mega Potion','Greater Health Potion','Health Potion',
    'Lesser Health Potion','XP Potion','Lesser XP Potion'
]

# Equipment filename mappings for items that have different display names vs filenames
EQUIPMENT_FILENAME_MAP = {
    'Nursing Cap': 'nursing',
    'Peaked Cap': 'peaked',
    'Fool\'s Cap': 'fool',
    'Safety Helmet': 'safety',
    'Pith Helmet': 'pith',
    'Rice Hat': 'rice',
    'Santa Hat': 'santa',
    'Service Cap': 'service',
    'Sorcerer Hat': 'sorcerer',
    'ATT Potion': 'att_potion',
    'DEF Potion': 'def_potion',
    'DEX Potion': 'dex_potion',
    'ENE Potion': 'ene_potion',
    'HAP Potion': 'hap_potion',
    'INT Potion': 'int_potion',
    'Air Potion': 'air_potion',
    'Basic Potion': 'basic_potion',
    'Electric Potion': 'electric_potion',
    'Fighting Potion': 'fighting_potion',
    'Fire Potion': 'fire_potion',
    'Holy Potion': 'holy_potion',
    'Ice Potion': 'ice_potion',
    'Magic Potion': 'magic_potion',
    'Necro Potion': 'necro_potion',
    'Plant Potion': 'plant_potion',
    'Psychic Potion': 'psychic_potion',
    'Rock Potion': 'rock_potion',
    'Water Potion': 'water_potion',
    'S1 Potion': 's1_potion',
    'S2 Potion': 's2_potion',
    'S3 Potion': 's3_potion',
    'Luck Potion': 'luck_potion',
    'Mega Potion': 'mega_potion',
    'Greater Health Potion': 'greater_health_potion',
    'Health Potion': 'health_potion',
    'Lesser Health Potion': 'lesser_health_potion',
    'XP Potion': 'xp_potion',
    'Lesser XP Potion': 'lesser_xp_potion'
}

# Elements - From Deco folder
WHEEL_ELEMENTS: List[str] = [
    'Air','Basic','Electric','Fighting','Fire','Holy','Ice',
    'Magic','Necro','Plant','Psychic','Rock','Water'
]

# Stats - From Deco folder  
WHEEL_STATS: List[str] = [
    'ATT','DEF','DEX','ENE','HAP','INT'
]

# Units - Military units (using available PnW military emojis)
WHEEL_UNITS: List[str] = [
    'Soldier','Tank','Jet','Ship','Missile','Bomb','Spy'
]

# Resources - PnW Resources (using available PnW resource emojis)
WHEEL_RESOURCES: List[str] = [
    'Aluminum','Bauxite','Coal','Credit','Food','Gasoline','Iron','Lead','Munitions','Oil','Steel','Uranium'
]

# Mode configuration
WHEEL_MODES = {
    'pets': {
        'items': WHEEL_PETS,
        'path_template': '/static/Emojis/Pets/{}.png',
        'title': 'Wheel of Pets',
        'subtitle': 'Click a segment · Place your bet · Spin to win',
        'description': '103 pets · equal odds · 5% house edge'
    },
    'monsters': {
        'items': WHEEL_MONSTERS,
        'path_template': '/static/Emojis/Pets/Equipment/{}.png',
        'title': 'Wheel of Monsters',
        'subtitle': 'Summon your creature · Place your bet · Spin to win',
        'description': f'{len(WHEEL_MONSTERS)} monsters · equal odds · 5% house edge'
    },
    'materials': {
        'items': WHEEL_MATERIALS,
        'path_template': '/static/Emojis/Pets/Equipment/{}.png',
        'title': 'Wheel of Materials',
        'subtitle': 'Choose your material · Place your bet · Spin to win',
        'description': f'{len(WHEEL_MATERIALS)} materials · equal odds · 5% house edge'
    },
    'gems': {
        'items': WHEEL_GEMS,
        'path_template': '/static/Emojis/Pets/Equipment/{}.png',
        'title': 'Wheel of Gems',
        'subtitle': 'Select your gem · Place your bet · Spin to win',
        'description': f'{len(WHEEL_GEMS)} gems · equal odds · 5% house edge'
    },
    'hats': {
        'items': WHEEL_HATS,
        'path_template': '/static/Emojis/Pets/Equipment/{}.png',
        'title': 'Wheel of Hats',
        'subtitle': 'Pick your headwear · Place your bet · Spin to win',
        'description': f'{len(WHEEL_HATS)} hats · equal odds · 5% house edge'
    },
    'potions': {
        'items': WHEEL_POTIONS,
        'path_template': '/static/Emojis/Pets/Equipment/{}.png',
        'title': 'Wheel of Potions',
        'subtitle': 'Brew your fortune · Place your bet · Spin to win',
        'description': f'{len(WHEEL_POTIONS)} potions · equal odds · 5% house edge'
    },
    'elements': {
        'items': WHEEL_ELEMENTS,
        'path_template': '/static/Emojis/Pets/Deco/{}.png',
        'title': 'Wheel of Elements',
        'subtitle': 'Harness the elements · Place your bet · Spin to win',
        'description': f'{len(WHEEL_ELEMENTS)} elements · equal odds · 5% house edge'
    },
    'stats': {
        'items': WHEEL_STATS,
        'path_template': '/static/Emojis/Pets/Deco/{}.png',
        'title': 'Wheel of Stats',
        'subtitle': 'Boost your attributes · Place your bet · Spin to win',
        'description': f'{len(WHEEL_STATS)} stats · equal odds · 5% house edge'
    },
    'units': {
        'items': WHEEL_UNITS,
        'path_template': '/static/Emojis/Military/{}.png',
        'title': 'Wheel of Units',
        'subtitle': 'Deploy your forces · Place your bet · Spin to win',
        'description': f'{len(WHEEL_UNITS)} units · equal odds · 5% house edge'
    },
    'resources': {
        'items': WHEEL_RESOURCES,
        'path_template': '/static/Emojis/Resources/{}.png',
        'title': 'Wheel of Resources',
        'subtitle': 'Trade resources · Place your bet · Spin to win',
        'description': f'{len(WHEEL_RESOURCES)} resources · equal odds · 5% house edge'
    }
}

# Unicode emoji mappings for modes that use emoji: paths
EMOJI_MAPPINGS = {
    # Monsters
    'Dragon': '🐉', 'Phoenix': '🔥', 'Unicorn': '🦄', 'Griffin': '🦅', 'Kraken': '🐙', 'Hydra': '🐍',
    'Basilisk': '🐍', 'Chimera': '🦁', 'Sphinx': '🗿', 'Minotaur': '🐂', 'Centaur': '🏹', 'Pegasus': '🐴',
    'Banshee': '👻', 'Vampire': '🧛', 'Werewolf': '🐺', 'Zombie': '🧟', 'Ghost': '👻', 'Demon': '😈',
    'Angel': '😇', 'Fairy': '🧚', 'Goblin': '👺', 'Orc': '👹', 'Troll': '👹', 'Giant': '🗿',
    'Cyclops': '👁️', 'Medusa': '🐍', 'Harpy': '🦅', 'Siren': '🧜', 'Djinn': '🧞', 'Elemental': '🌪️',
    'Golem': '🗿', 'Lich': '💀', 'Necromancer': '🧙', 'Wizard': '🧙', 'Witch': '🧙', 'Warlock': '🧙',
    'Paladin': '⚔️', 'Knight': '🛡️', 'Rogue': '🗡️', 'Archer': '🏹', 'Barbarian': '🪓', 'Monk': '🥋',
    'Druid': '🌿', 'Ranger': '🏹', 'Bard': '🎵', 'Cleric': '✨', 'Sorcerer': '🔮', 'Artificer': '🔧',
    'Fighter': '⚔️', 'Beastmaster': '🐺', 'Summoner': '🔮', 'Enchanter': '✨', 'Illusionist': '🎭',
    'Diviner': '🔮', 'Transmuter': '⚗️', 'Evoker': '⚡', 'Abjurer': '🛡️', 'Conjurer': '🌟',
    
    # Materials
    'Wood': '🪵', 'Stone': '🪨', 'Iron': '⚙️', 'Gold': '🥇', 'Silver': '🥈', 'Copper': '🟤',
    'Bronze': '🟫', 'Steel': '⚙️', 'Platinum': '⚪', 'Diamond': '💎', 'Ruby': '🔴', 'Emerald': '🟢',
    'Sapphire': '🔵', 'Amethyst': '🟣', 'Topaz': '🟡', 'Opal': '⚪', 'Pearl': '🤍', 'Jade': '🟢',
    'Obsidian': '⚫', 'Quartz': '⚪', 'Crystal': '💎', 'Glass': '🪟', 'Clay': '🟫', 'Sand': '🟨',
    'Marble': '⚪', 'Granite': '🪨', 'Limestone': '🤍', 'Slate': '⬛', 'Brick': '🧱', 'Concrete': '🏗️',
    'Leather': '🟫', 'Cloth': '🧵', 'Silk': '🕸️', 'Cotton': '☁️', 'Wool': '🐑', 'Linen': '🤍',
    'Hemp': '🌿', 'Rope': '🪢', 'Chain': '⛓️', 'Wire': '🔗', 'Plastic': '🟡', 'Rubber': '⚫',
    'Paper': '📄', 'Cardboard': '📦', 'Foam': '☁️', 'Resin': '🟡', 'Wax': '🕯️', 'Oil': '🛢️',
    'Tar': '⚫', 'Pitch': '⚫',
    
    # Gems
    'Garnet': '🔴', 'Peridot': '🟢', 'Aquamarine': '🔵', 'Citrine': '🟡', 'Tourmaline': '🌈',
    'Moonstone': '🌙', 'Sunstone': '☀️', 'Labradorite': '🌈', 'Onyx': '⚫', 'Agate': '🟫',
    'Jasper': '🟫', 'Carnelian': '🟠', 'Bloodstone': '🔴', 'Hematite': '⚫', 'Malachite': '🟢',
    'Turquoise': '🔵', 'Lapis': '🔵', 'Sodalite': '🔵', 'Fluorite': '🟣', 'Calcite': '⚪',
    'Pyrite': '🟡', 'Quartz': '⚪', 'Rose Quartz': '🩷', 'Smoky Quartz': '🟫', 'Clear Quartz': '⚪',
    'Aventurine': '🟢', 'Tiger Eye': '🟡', 'Volcanic Glass': '⚫', 'Amber': '🟡', 'Coral': '🪸',
    'Jet': '⚫', 'Ivory': '🤍',
    
    # Hats
    'Crown': '👑', 'Tiara': '👑', 'Helmet': '⛑️', 'Cap': '🧢', 'Beanie': '🧢', 'Beret': '🎩',
    'Fedora': '🎩', 'Sombrero': '👒', 'Cowboy Hat': '🤠', 'Top Hat': '🎩', 'Bowler Hat': '🎩',
    'Baseball Cap': '🧢', 'Trucker Hat': '🧢', 'Snapback': '🧢', 'Bucket Hat': '👒', 'Sun Hat': '👒',
    'Visor': '🧢', 'Headband': '🎽', 'Bandana': '🎽', 'Turban': '👳', 'Fez': '🎩', 'Tam': '🧢',
    'Cloche': '👒', 'Pillbox': '👒', 'Boater': '👒', 'Panama': '👒', 'Pork Pie': '🎩',
    'Trilby': '🎩', 'Homburg': '🎩', 'Deerstalker': '🎩', 'Ushanka': '🧢', 'Balaclava': '🎿',
    'Ski Mask': '🎿', 'Hard Hat': '⛑️', 'Chef Hat': '👨‍🍳', 'Nurse Cap': '👩‍⚕️', 'Graduation Cap': '🎓',
    'Wizard Hat': '🧙', 'Witch Hat': '🧙‍♀️', 'Santa Hat': '🎅', 'Party Hat': '🎉', 'Jester Hat': '🃏',
    'Viking Helmet': '⚔️',
    
    # Elements
    'Fire': '🔥', 'Water': '💧', 'Earth': '🌍', 'Air': '💨', 'Lightning': '⚡', 'Ice': '🧊',
    'Light': '💡', 'Dark': '🌑', 'Metal': '⚙️', 'Wood': '🌳', 'Spirit': '👻', 'Void': '🕳️',
    'Plasma': '⚡', 'Energy': '⚡', 'Gravity': '🌌', 'Time': '⏰', 'Space': '🌌', 'Mind': '🧠',
    'Soul': '👻', 'Life': '🌱', 'Death': '💀', 'Chaos': '🌪️', 'Order': '⚖️', 'Nature': '🌿',
    'Magic': '✨', 'Divine': '✨', 'Infernal': '🔥', 'Celestial': '⭐', 'Abyssal': '🕳️', 'Primal': '🌋',
    'Arcane': '🔮', 'Holy': '✨', 'Shadow': '🌑', 'Frost': '❄️', 'Storm': '⛈️', 'Earthquake': '🌍',
    'Tsunami': '🌊', 'Volcano': '🌋', 'Hurricane': '🌪️', 'Blizzard': '❄️'
}

_WHEEL_HOUSE_EDGE = 0.95   # 5 % house edge
_WHEEL_OWN_PET_MULT = 2.0  # 2× bonus if winner == your pet species


@casino_api.get('/casino/wheel/pets')
def get_wheel_pets():
    """Return the full list of pets on the wheel with their image paths. (Legacy endpoint)"""
    return JSONResponse(content={
        'pets': [{'name': p, 'path': f'/static/Emojis/Pets/{p}.png'} for p in WHEEL_PETS],
        'count': len(WHEEL_PETS),
        'house_edge': _WHEEL_HOUSE_EDGE,
        'own_pet_mult': _WHEEL_OWN_PET_MULT,
    })


@casino_api.get('/casino/wheel/modes')
def get_wheel_modes():
    """Return all available wheel modes and their configurations."""
    return JSONResponse(content={
        'modes': {
            mode_id: {
                'title': config['title'],
                'subtitle': config['subtitle'],
                'description': config['description'],
                'count': len(config['items'])
            }
            for mode_id, config in WHEEL_MODES.items()
        }
    })


@casino_api.get('/casino/wheel/items/{mode}')
def get_wheel_items(mode: str):
    """Return the items for a specific wheel mode."""
    if mode not in WHEEL_MODES:
        return JSONResponse(content={"error": "Invalid mode"}, status_code=400)
    
    config = WHEEL_MODES[mode]
    items = []
    
    for item in config['items']:
        if config['path_template'].startswith('emoji:'):
            # Use Unicode emoji
            emoji = EMOJI_MAPPINGS.get(item, '❓')
            path = f'emoji:{emoji}'
        elif 'Equipment' in config['path_template']:
            # Use equipment emoji with filename mapping
            filename = EQUIPMENT_FILENAME_MAP.get(item, item)
            path = config['path_template'].format(filename)
        else:
            # Use image file with lowercase name
            path = config['path_template'].format(item.lower())
        
        items.append({'name': item, 'path': path})
    
    return JSONResponse(content={
        'mode': mode,
        'title': config['title'],
        'subtitle': config['subtitle'],
        'description': config['description'],
        'items': items,
        'count': len(items),
        'house_edge': _WHEEL_HOUSE_EDGE,
        'own_pet_mult': _WHEEL_OWN_PET_MULT,
    })


@casino_api.post('/casino/wheel/spin')
async def spin_wheel(request: Request):
    """Spin the Wheel. Body: {bet_amount, chosen_item, mode, fun_mode}."""
    try:
        data = await request.json()
        session_user = request.session.get("discord_user")
        if not session_user:
            return JSONResponse(content={"error": "Not logged in"}, status_code=401)
        user_id = str(session_user.get("id"))

        bet_amount   = int(data.get('bet_amount', 0))
        chosen_item  = str(data.get('chosen_item', data.get('chosen_pet', '')))  # Support both old and new param names
        mode         = str(data.get('mode', 'pets'))
        fun_mode     = bool(data.get('fun_mode', False))

        if mode not in WHEEL_MODES:
            return JSONResponse(content={"error": "Invalid mode"}, status_code=400)
        
        mode_config = WHEEL_MODES[mode]
        if chosen_item not in mode_config['items']:
            return JSONResponse(content={"error": "Invalid item selection"}, status_code=400)

        async with _get_user_lock(user_id):
            return await _spin_wheel_inner(user_id, bet_amount, chosen_item, mode, fun_mode)

    except Exception as e:
        logger.error(f"Wheel spin error: {e}", exc_info=True)
        return JSONResponse(content={"error": "Spin failed"}, status_code=500)


async def _spin_wheel_inner(user_id: str, bet_amount: int, chosen_item: str, mode: str, fun_mode: bool):
    pet_data = await user_data_manager.get_pet_data_async(user_id)
    if not pet_data:
        return JSONResponse(content={"error": "No pet found"}, status_code=404)

    if not fun_mode:
        if bet_amount < 10:
            return JSONResponse(content={"error": "Minimum bet is 10 XP"}, status_code=400)
        total_xp = compute_total_xp(pet_data)
        if bet_amount > total_xp:
            return JSONResponse(content={"error": "Insufficient XP"}, status_code=400)
        await LootCalculator.apply_xp_change(int(user_id), -bet_amount, source="wheel_bet")

    # Determine winner
    mode_config = WHEEL_MODES[mode]
    winner = random.choice(mode_config['items'])
    winner_index = mode_config['items'].index(winner)

    # Get winner path
    if mode_config['path_template'].startswith('emoji:'):
        winner_path = f'emoji:{EMOJI_MAPPINGS.get(winner, "❓")}'
    elif 'Equipment' in mode_config['path_template']:
        filename = EQUIPMENT_FILENAME_MAP.get(winner, winner)
        winner_path = mode_config['path_template'].format(filename)
    else:
        winner_path = mode_config['path_template'].format(winner.lower())

    # For pets mode, check own pet bonus
    own_species = str(pet_data.get("species", "Cat"))
    won = winner == chosen_item
    own_pet_bonus = won and (mode == 'pets' and winner == own_species)

    winnings = 0
    if won:
        base_win = int(bet_amount * len(mode_config['items']) * _WHEEL_HOUSE_EDGE)
        winnings = int(base_win * _WHEEL_OWN_PET_MULT) if own_pet_bonus else base_win

    if not fun_mode and winnings > 0:
        # Apply ability tree effects
        modified_winnings = winnings
        try:
            pet_data = await user_data_manager.get_pet_data_async(user_id)
            if pet_data:
                from Systems.Pets.Logic.ability_tree import get_ability_effect
                # Apply casino win bonus
                win_mult = get_ability_effect(pet_data, "casino_xp_gain_mult", game="wheel_of_pets")
                if win_mult != 1.0:
                    modified_winnings = int(winnings * win_mult)
        except Exception:
            pass
        
        await LootCalculator.apply_xp_change(int(user_id), modified_winnings, source="wheel_win")
    elif not fun_mode:
        # Apply loss reduction for losses
        try:
            pet_data = await user_data_manager.get_pet_data_async(user_id)
            if pet_data:
                from Systems.Pets.Logic.ability_tree import get_ability_effect
                loss_reduction = get_ability_effect(pet_data, "casino_xp_loss_reduction", game="wheel_of_pets")
                if loss_reduction > 0:
                    refund = int(bet_amount * loss_reduction)
                    if refund > 0:
                        await LootCalculator.apply_xp_change(int(user_id), refund, source="wheel_loss_reduction")
        except Exception:
            pass

    if not fun_mode:
        net = winnings - bet_amount
        await user_data_manager.update_pet_gambling_stats(
            user_id, f"wheel_of_{mode}", net, bet_amount=bet_amount,
            extra_data={"own_pet_jackpots": 1 if own_pet_bonus else 0}
        )

    if won and own_pet_bonus:
        result_text = f"⭐ OWN PET JACKPOT! {winner} landed — 2× bonus!"
    elif won:
        result_text = f"🏆 YOU WIN! {winner} landed!"
    else:
        result_text = f"💸 {winner} landed. Better luck next time!"

    return JSONResponse(content={
        'winner':        winner,
        'winner_index':  winner_index,
        'winner_path':   winner_path,
        'chosen_item':   chosen_item,
        'own_species':   own_species,
        'won':           won,
        'own_pet_bonus': own_pet_bonus,
        'winnings':      winnings if not fun_mode else 0,
        'result_text':   result_text,
        'fun_mode':      fun_mode,
        'mode':          mode,
    })


# BLACKJACK ENDPOINTS
@casino_api.post('/casino/blackjack/create')
async def create_blackjack_game(request: Request):
    """Create a new blackjack game session"""
    try:
        data = await request.json()
        user_id = data.get('user_id')
        betting_mode = data.get('betting_mode', True)
        buy_in = int(data.get('buy_in', 50))
        
        if not user_id:
            return JSONResponse(content={'error': 'User ID required'}, status_code=400)
        
        # Validate user has enough XP if betting
        if betting_mode:
            pet_data = await user_data_manager.get_pet_data_async(user_id)
            if not pet_data:
                return JSONResponse(content={'error': 'No pet found'}, status_code=404)
            
            total_xp = compute_total_xp(pet_data)
            if buy_in > total_xp:
                return JSONResponse(content={'error': 'Insufficient XP'}, status_code=400)
        
        # Create mock member object for blackjack session
        class MockMember:
            def __init__(self, uid: str):
                self.id = int(uid)
                self.display_name = f"Player_{uid}"
                self.mention = f"<@{uid}>"
        
        mock_member = MockMember(user_id)
        
        # For web-based blackjack, we'll return game state instead of creating Discord session
        return JSONResponse(content={
            'game_id': f"bj_{user_id}_{random.randint(1000, 9999)}",
            'betting_mode': betting_mode,
            'buy_in': buy_in,
            'status': 'created'
        })
        
    except Exception as e:
        logger.error(f"Error creating blackjack game: {e}")
        return JSONResponse(content={'error': 'Failed to create game'}, status_code=500)

# HOLDEM ENDPOINTS  
@casino_api.post('/casino/holdem/create')
async def create_holdem_game(request: Request):
    """Create a new Texas Hold'em game session"""
    try:
        data = await request.json()
        user_id = data.get('user_id')
        
        return JSONResponse(content={
            'game_id': f"holdem_{user_id}_{random.randint(1000, 9999)}",
            'status': 'created'
        })
        
    except Exception as e:
        logger.error(f"Error creating holdem game: {e}")
        return JSONResponse(content={'error': 'Failed to create game'}, status_code=500)

# CRAPS ENDPOINTS
@casino_api.post('/casino/craps/create')
async def create_craps_game(request: Request):
    """Create a new craps game session"""
    try:
        data = await request.json()
        user_id = data.get('user_id')
        betting_mode = data.get('betting_mode', True)
        
        return JSONResponse(content={
            'game_id': f"craps_{user_id}_{random.randint(1000, 9999)}",
            'betting_mode': betting_mode,
            'status': 'created'
        })
        
    except Exception as e:
        logger.error(f"Error creating craps game: {e}")
        return JSONResponse(content={'error': 'Failed to create game'}, status_code=500)

# RACES ENDPOINTS
@casino_api.post('/casino/races/create')
async def create_race_game(request: Request):
    """Create a new pet race session"""
    try:
        data = await request.json()
        user_id = data.get('user_id')
        difficulty = data.get('difficulty', 'apprentice')
        bet_amount = int(data.get('bet_amount', 50))
        
        if not user_id:
            return JSONResponse(content={'error': 'User ID required'}, status_code=400)
        
        # Validate user has pet and enough XP
        pet_data = await user_data_manager.get_pet_data_async(user_id)
        if not pet_data:
            return JSONResponse(content={'error': 'No pet found'}, status_code=404)
        
        total_xp = compute_total_xp(pet_data)
        if bet_amount > total_xp:
            return JSONResponse(content={'error': 'Insufficient XP'}, status_code=400)
        
        return JSONResponse(content={
            'game_id': f"race_{user_id}_{random.randint(1000, 9999)}",
            'difficulty': difficulty,
            'bet_amount': bet_amount,
            'status': 'created'
        })
        
    except Exception as e:
        logger.error(f"Error creating race game: {e}")
        return JSONResponse(content={'error': 'Failed to create game'}, status_code=500)
