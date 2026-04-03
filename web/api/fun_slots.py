from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import random

import os

fun_slots_api = APIRouter()

# Odds information for display
ODDS_INFO = {
    "Very Easy": {"total_emojis": 3, "three_match_odds": "1 in 9", "two_match_odds": "1 in 3"},
    "Easy": {"total_emojis": 4, "three_match_odds": "1 in 16", "two_match_odds": "1 in 4"},
    "Medium": {"total_emojis": 6, "three_match_odds": "1 in 36", "two_match_odds": "1 in 6"},
    "Hard": {"total_emojis": 13, "three_match_odds": "1 in 169", "two_match_odds": "1 in 13"},
    "Very Hard": {"total_emojis": 95, "three_match_odds": "1 in 9,025", "two_match_odds": "1 in 95"},
    "Insanity": {"total_emojis": "100+", "three_match_odds": "1 in 10,000+", "two_match_odds": "1 in 100+"},
}

# Define categories and their corresponding subdirectories
EMOJI_CATEGORIES = {
    'Pet Type': ['Flying', 'Land', 'Swimming'],
    'Units': ['soldier', 'tank', 'jet', 'ship', 'knights', 'necromancer', 'sorcerer'],
    'Stats': ['ATT', 'DEF', 'DEX', 'INT', 'HAP', 'ENE'],
    'Elements': ['Air', 'Basic', 'Electric', 'Fire', 'Holy', 'Ice', 'Magic', 'Necro', 'Plant', 'Rock', 'Water', 'Psychic', 'Fighting'],
    'Pets': [
        'Alligator','Ant','Anteater','Axolotl','Badger','Bat','Beaver','Bee','Beetle','Bison','BlueTang','Camel','Cardinal','Cat','Centipede','Cheetah','Chicken','Clownfish','Cow','Crab','Crow','Deer','Dog','Dolphin','Duck','Eagle','Elephant','Emu','Firefly','Fox','Frog','Giraffe','Goat','Goose','Gorilla','Grizzly','Hamster','Hedgehog','Hippo','Horse','Hummingbird','Iguana','Jaguar','Jellyfish','Kangaroo','Kiwi','Koala','Ladybug','Lemur','Leopard','Lion','Llama','Mantis','Monkey','Mouse','Octopus','Orangutan','Orca','Ostrich','Otter','Owl','Panda','Parrot','Peacock','Pelican','Penguin','Pig','Pigeon','Platypus','PolarBear','Pufferfish','Rabbit','Raccoon','Ram','Rat','RedPanda','Reindeer','Rhino','Salmon','Scorpion','Seahorse','Seal','Shark','Sheep','Shrimp','Skunk','Sloth','Snail','Snake','Spider','Squirrel','Starfish','Stingray','SugarGlider','Tiger','Toucan','Turkey','Turtle','Walrus','Whale','Wolf','Yak','Zebra'
    ],
    'RPS': ['paper', 'scissor', 'rock_1'],
    'Equipment': [
        'Bone', 'Brick', 'Dirt', 'EmberCube', 'EmberHeart', 'EmeraldSoul', 'Fabric', 'Glass', 'Gold', 
        'JadeSlab', 'Key1', 'Key2', 'Key3', 'Laser', 'Leaf', 'Leather', 'Plat', 'Sand', 'Steel', 
        'Stone', 'Wood', 'air_potion', 'att_potion', 'basic_potion', 'def_potion', 'dex_potion', 
        'electric_potion', 'ene_potion', 'fedora', 'fire_potion', 'greater_health_potion', 'hap_potion', 
        'health_potion', 'holy_potion', 'ice_potion', 'int_potion', 'lesser_health_potion', 
        'lesser_xp_potion', 'luck_potion', 'magic_potion', 'mega_potion', 'necro_potion', 
        'nursing', 'plant_potion', 'psychic_potion', 'rock_potion', 's1_potion', 's2_potion', 
        's3_potion', 'safety', 'santa', 'toque', 'water_potion', 'xp_potion'
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
            elif category == 'RPS':
                return f"/static/Emojis/RPS/{emoji_name}.png"
            elif category == 'Equipment':
                return f"/static/Emojis/Pets/Equipment/{emoji_name}.png"
            else:
                return f"/static/Emojis/Pets/Deco/{emoji_name}.png"
    return f"/static/Emojis/Pets/Deco/{emoji_name}.png" # Default

@fun_slots_api.get('/fun/slots-emojis/{theme}')
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


@fun_slots_api.get('/fun/slots-odds')
def get_slots_odds():
    """Return odds information for all themes"""
    return JSONResponse(content=ODDS_INFO)

@fun_slots_api.post('/fun/slots-spin')
async def spin_slots(request: Request):
    """Simulate a slots spin based on the selected theme"""
    data = await request.json()
    theme = data.get('theme')

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

    # Spin the reels
    reel1 = random.choice(emojis)
    reel2 = random.choice(emojis)
    reel3 = random.choice(emojis)

    reels_result = [reel1, reel2, reel3]

    # Check for wins
    if reel1 == reel2 == reel3:
        result_text = 'JACKPOT! 3 in a row!'
    elif reel1 == reel2 or reel1 == reel3 or reel2 == reel3:
        result_text = 'WIN! 2 in a row!'
    else:
        result_text = 'Better luck next time!'

    # Prepare response
    response_reels = [
        {'name': r, 'path': get_emoji_file_path(r)} for r in reels_result
    ]

    return JSONResponse(content={
        'reels': response_reels,
        'result_text': result_text
    })
