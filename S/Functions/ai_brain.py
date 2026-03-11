import random
from typing import Optional, List
from collections import Counter

def get_ai_choice(theme: str, player_choice_history: Optional[List[str]] = None) -> str:
    """
    Returns a strategic choice for the AI based on the game theme and player's choice history.
    The AI analyzes the player's move frequency and introduces randomness to avoid predictability.
    """
    winning_combinations = {
        "Traditional": {
            "rock_1": "scissor",
            "paper": "rock_1",
            "scissor": "paper"
        },
        "Fantasy": {
            "knights": "archer",
            "archer": "necromancer",
            "necromancer": "knights"
        },
        "War": {
            "tank": "ship",
            "jet": "tank",
            "ship": "jet"
        }
    }

    choices = {
        "Traditional": ["rock_1", "paper", "scissor"],
        "Fantasy": ["knights", "archer", "necromancer"],
        "War": ["tank", "jet", "ship"]
    }
    theme_choices = choices.get(theme)
    if not theme_choices:
        return ""

    # With a 33% chance, or if there is not enough history, make a random move to be less predictable.
    if not player_choice_history or len(player_choice_history) < 3 or random.random() < 0.33:
        return random.choice(theme_choices)

    # Analyze player's move frequency
    move_counts = Counter(player_choice_history)
    most_common_moves = move_counts.most_common()

    if not most_common_moves:
        return random.choice(theme_choices)

    # Find the most frequent move, handling ties by random choice
    max_count = most_common_moves[0][1]
    tied_most_common = [move for move, count in most_common_moves if count == max_count]
    predicted_player_move = random.choice(tied_most_common)

    # Counter the predicted move
    winning_moves = winning_combinations.get(theme, {})
    for ai_move, beats_move in winning_moves.items():
        if beats_move == predicted_player_move:
            return ai_move

    # Fallback to a random choice if no counter is found
    return random.choice(theme_choices)
