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

# Create a mapping of all emojis to their subdirectories
ALL_EMOJIS = {}
for category, emojis in EMOJI_CATEGORIES.items():
    if category == 'Pets':
        for emoji in emojis:
            ALL_EMOJIS[emoji] = 'Pets'
    elif category == 'Units':
        for emoji in emojis:
            ALL_EMOJIS[emoji] = 'Military'
    elif category == 'RPS':
        for emoji in emojis:
            ALL_EMOJIS[emoji] = 'RPS'
    elif category == 'Equipment':
        for emoji in emojis:
            ALL_EMOJIS[emoji] = 'Pets/Equipment'
    else:  # Default to Pets/Deco
        for emoji in emojis:
            ALL_EMOJIS[emoji] = 'Pets/Deco'

def get_emoji_file_path(emoji_name):
    """Return the correct file path for an emoji based on its category"""
    subdirectory = ALL_EMOJIS.get(emoji_name, 'Pets/Deco')  # Default to Deco
    return f"/static/Emojis/{subdirectory}/{emoji_name}.png"

@fun_slots_api.get('/api/fun/slots-odds')
def get_slots_odds():
    """Return odds information for all themes"""
    return JSONResponse(content=ODDS_INFO)
