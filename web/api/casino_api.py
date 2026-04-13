from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
import random
import asyncio
import logging
from typing import Dict, List, Optional, Any

from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.pet_brain import LootCalculator
from Systems.Pets.PetGames.blackjack import BlackjackSession
from Systems.Pets.PetGames.holdem import HoldemSession
from Systems.Pets.PetGames.craps import CrapsSession
from Systems.Pets.PetGames.slots import SlotMachineView, get_emojis_for_difficulty, compute_total_xp, PAYOUTS
from Systems.Pets.PetGames.races import RaceSession

logger = logging.getLogger(__name__)

casino_api = APIRouter()

# Emoji categories for slots
EMOJI_CATEGORIES = {
    'Pet Type': ['Flying', 'Land', 'Swimming'],
    'Units': ['soldier', 'tank', 'jet', 'ship', 'knights', 'necromancer', 'sorcerer'],
    'Stats': ['ATT', 'DEF', 'DEX', 'INT', 'HAP', 'ENE'],
    'Elements': ['Air', 'Basic', 'Electric', 'Fire', 'Holy', 'Ice', 'Magic', 'Necro', 'Plant', 'Rock', 'Water', 'Psychic', 'Fighting'],
    'Pets': [
        'Alligator','Ant','Anteater','Axolotl','Badger','Bat','Beaver','Bee','Beetle','Bison','BlueTang','Camel','Cardinal','Cat','Centipede','Cheetah','Chicken','Clownfish','Cow','Crab','Crow','Deer','Dog','Dolphin','Duck','Eagle','Elephant','Emu','Firefly','Fox','Frog','Giraffe','Goat','Goose','Gorilla','Grizzly','Hamster','Hedgehog','Hippo','Horse','Hummingbird','Iguana','Jaguar','Jellyfish','Kangaroo','Kiwi','Koala','Ladybug','Lemur','Leopard','Lion','Llama','Mantis','Monkey','Mouse','Octopus','Orangutan','Orca','Ostrich','Otter','Owl','Panda','Parrot','Peacock','Pelican','Penguin','Pig','Pigeon','Platypus','PolarBear','Pufferfish','Rabbit','Raccoon','Ram','Rat','RedPanda','Reindeer','Rhino','Salmon','Scorpion','Seahorse','Seal','Shark','Sheep','Shrimp','Skunk','Sloth','Snail','Snake','Spider','Squirrel','Starfish','Stingray','SugarGlider','Tiger','Toucan','Turkey','Turtle','Walrus','Whale','Wolf','Yak','Zebra'
    ]
}

def get_emoji_file_path(emoji_name):
    """Return the correct file path for an emoji based on its category"""
    for category, emojis in EMOJI_CATEGORIES.items():
        if emoji_name in emojis:
            if category == 'Pets':
                return f"/static/Emojis/Pets/{emoji_name}.png"
            elif category == 'Units':
                return f"/static/Emojis/Military/{emoji_name}.png"
            else:
                return f"/static/Emojis/Pets/Deco/{emoji_name}.png"
    return f"/static/Emojis/Pets/Deco/{emoji_name}.png"

@casino_api.get('/casino/user-xp/{user_id}')
async def get_user_xp(user_id: str):
    """Get user's current XP for betting"""
    try:
        pet_data = await user_data_manager.get_pet_data_async(user_id)
        if not pet_data:
            return JSONResponse(content={'error': 'No pet found'}, status_code=404)
        
        total_xp = compute_total_xp(pet_data)
        return JSONResponse(content={'total_xp': total_xp})
    except Exception as e:
        logger.error(f"Error getting user XP: {e}")
        return JSONResponse(content={'error': 'Failed to get XP'}, status_code=500)

# SLOTS ENDPOINTS
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
        'Easy': 'Units',
        'Medium': 'Stats',
        'Hard': 'Elements',
        'Very Hard': 'Pets',
        'Insanity': ['Pets', 'Pet Type', 'Units', 'Stats', 'Elements']
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
        user_id = data.get('user_id')
        theme = data.get('theme')
        bet_amount = int(data.get('bet_amount', 0))
        fun_mode = data.get('fun_mode', False)
        
        if not user_id:
            return JSONResponse(content={'error': 'User ID required'}, status_code=400)
        
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
            'Easy': 'Units', 
            'Medium': 'Stats',
            'Hard': 'Elements',
            'Very Hard': 'Pets',
            'Insanity': ['Pets', 'Pet Type', 'Units', 'Stats', 'Elements']
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

        # Handle Insanity mode (dual reels)
        if theme == 'Insanity':
            element = str(pet_data.get("element", "fire")).lower()
            species = str(pet_data.get("species", "Cat"))
            
            element_emojis = EMOJI_CATEGORIES.get('Elements', [])
            species_emojis = EMOJI_CATEGORIES.get('Pets', [])
            
            # Spin both reels
            emoji_slots = [random.choice(element_emojis) for _ in range(3)]
            pet_slots = [random.choice(species_emojis) for _ in range(3)]
            
            element_matches = sum(1 for s in emoji_slots if s.lower() == element)
            species_matches = sum(1 for s in pet_slots if s == species)
            
            # Calculate winnings
            winnings = 0
            result_text = "Better luck next time!"
            payouts = PAYOUTS.get("insanity", {})
            
            if element_matches == 3 and species_matches == 3:
                winnings = int(bet_amount * float(payouts.get("three_both", 0.0)))
                result_text = "INSANITY JACKPOT!"
            elif (element_matches == 3 and species_matches == 2) or (element_matches == 2 and species_matches == 3):
                winnings = int(bet_amount * float(payouts.get("combination", 0.0)))
                result_text = "MEGA WIN!"
            elif element_matches == 2 and species_matches == 2:
                winnings = int(bet_amount * float(payouts.get("two_both", 0.0)))
                result_text = "DUAL WIN!"
            
            # Apply winnings
            if not fun_mode and winnings > 0:
                await LootCalculator.apply_xp_change(int(user_id), winnings, source="slots_win")
            
            return JSONResponse(content={
                'emoji_reels': [{'name': e, 'path': get_emoji_file_path(e)} for e in emoji_slots],
                'pet_reels': [{'name': p, 'path': get_emoji_file_path(p)} for p in pet_slots],
                'result_text': result_text,
                'winnings': winnings if not fun_mode else 0,
                'element_target': element,
                'species_target': species,
                'insanity_mode': True
            })
        else:
            # Regular slots
            reel1 = random.choice(emojis)
            reel2 = random.choice(emojis)
            reel3 = random.choice(emojis)
            
            reels_result = [reel1, reel2, reel3]
            
            # Check for wins
            all_match = len(set(reels_result)) == 1
            two_match = len(set(reels_result)) == 2
            
            # Calculate winnings
            winnings = 0
            payouts = PAYOUTS.get(theme.lower().replace(' ', '_'), PAYOUTS.get("very_easy", {"three": 0.0, "two": 0.0}))
            
            if all_match:
                winnings = int(bet_amount * payouts["three"])
                result_text = 'JACKPOT! 3 in a row!'
            elif two_match:
                winnings = int(bet_amount * payouts["two"])
                result_text = 'WIN! 2 in a row!'
            else:
                result_text = 'Better luck next time!'
            
            # Apply winnings
            if not fun_mode and winnings > 0:
                await LootCalculator.apply_xp_change(int(user_id), winnings, source="slots_win")
            
            response_reels = [
                {'name': r, 'path': get_emoji_file_path(r)} for r in reels_result
            ]
            
            return JSONResponse(content={
                'reels': response_reels,
                'result_text': result_text,
                'winnings': winnings if not fun_mode else 0,
                'insanity_mode': False
            })
            
    except Exception as e:
        logger.error(f"Error in slots spin: {e}")
        return JSONResponse(content={'error': 'Spin failed'}, status_code=500)

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