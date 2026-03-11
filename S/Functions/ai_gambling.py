import random
from typing import List, Tuple, Dict

# --- Hold'em Helper Functions ---

RANKS = ["1","2","3","4","5","6","7","8","9","10","J","Q","K"]
SUITS = ["H","D","C","S"]

def _rank_value(r: str) -> int:
    if r == "1":
        return 14
    if r == "J":
        return 11
    if r == "Q":
        return 12
    if r == "K":
        return 13
    try:
        return int(r)
    except Exception:
        return 0

def get_hand_rank(hole: List[str], community: List[str]) -> Tuple[int, List[int]]:
    cards = hole + community
    ranks = [_rank_value(c[1:]) for c in cards]
    suits = [c[0] for c in cards]
    counts: Dict[int,int] = {}
    for v in ranks:
        counts[v] = counts.get(v, 0) + 1
    sorted_ranks = sorted(ranks, reverse=True)
    is_flush = False
    for s in SUITS:
        if sum(1 for c in suits if c == s) >= 5:
            is_flush = True
            break
    uniq = sorted(set(ranks))
    straights: List[int] = []
    if 14 in uniq:
        uniq.append(1)
    uniq_sorted = sorted(uniq)
    streak = 1
    last = None
    best_st = 0
    for v in uniq_sorted:
        if last is None:
            streak = 1
        else:
            if v == last + 1:
                streak += 1
            else:
                streak = 1
        last = v
        if streak >= 5:
            best_st = v
    is_straight = best_st > 0
    four = [v for v,c in counts.items() if c == 4]
    trips = [v for v,c in counts.items() if c == 3]
    pairs = [v for v,c in counts.items() if c == 2]
    if is_flush and is_straight:
        return 8, [best_st]
    if len(four) >= 1:
        kicker = max([v for v in ranks if v != four[0]])
        return 7, [max(four), kicker]
    if len(trips) >= 1 and len(pairs) >= 1:
        return 6, [max(trips), max(pairs)]
    if is_flush:
        top5 = sorted_ranks[:5]
        return 5, top5
    if is_straight:
        return 4, [best_st]
    if len(trips) >= 1:
        kickers = [v for v in sorted_ranks if v != max(trips)]
        return 3, [max(trips)] + kickers[:2]
    if len(pairs) >= 2:
        top2 = sorted(pairs, reverse=True)[:2]
        kicker = max([v for v in sorted_ranks if v not in top2])
        return 2, top2 + [kicker]
    if len(pairs) == 1:
        pairv = pairs[0]
        kickers = [v for v in sorted_ranks if v != pairv][:3]
        return 1, [pairv] + kickers
    return 0, sorted_ranks[:5]

def get_holdem_bot_action(player_hand: List[str], community_cards: List[str], to_call: int, pot: int, round_stage: str, can_check: bool) -> Tuple[str, int]:
    """
    Determines the bot's action in a game of Texas Hold'em with more advanced logic.
    """
    rank, values = get_hand_rank(player_hand, community_cards)
    hand_strength = rank + max(values) / 14.0  # Simple strength score

    # Bluffing
    if random.random() < 0.1:  # 10% chance to bluff
        if can_check:
            return "bet", int(pot * 0.5)  # Bluff bet half the pot
        else:
            return "raise", to_call + int(pot * 0.5)

    if round_stage == "preflop":
        # More selective pre-flop based on hand quality
        if hand_strength > 1.5:  # Good starting hand (pair, high cards)
            if can_check:
                return "bet", 50
            else:
                return "raise", to_call * 2
        elif hand_strength > 1.0 and to_call < 50: # Decent hand, call small raises
            return "call", to_call
        else:
            if can_check:
                return "check", 0
            return "fold", 0

    else:  # Flop, Turn, River
        pot_odds = to_call / (pot + to_call) if to_call > 0 else 0

        # Strong hand
        if hand_strength > 3:
            return "raise", to_call + int(pot * 0.75)
        # Decent hand
        elif hand_strength > 2:
            if pot_odds < 0.3: # Good pot odds
                return "call", to_call
            else:
                if can_check:
                    return "check", 0
                return "fold", 0
        # Weak hand
        else:
            if can_check:
                return "check", 0
            if to_call == 0:
                return "check", 0
            return "fold", 0

# --- Blackjack Helper Functions ---

def _value_of(code: str) -> int:
    r = code[1:]
    if r == "J" or r == "Q" or r == "K":
        return 10
    if r == "1":
        return 11
    try:
        return int(r)
    except Exception:
        return 0

def _hand_value(cards: List[str]) -> Tuple[int, bool]:
    total = 0
    aces = 0
    for c in cards:
        v = _value_of(c)
        if c[1:] == "1":
            aces += 1
        total += v
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    soft = aces > 0 and total <= 21
    return total, soft

def get_blackjack_bot_action(player_hand: List[str], dealer_card: str, can_double: bool) -> str:
    """
    Determines the bot's action in a game of Blackjack based on a more advanced strategy.
    Includes logic for doubling down and occasional "bluffs" (deviations from basic strategy).
    """
    player_value, player_is_soft = _hand_value(player_hand)
    dealer_value = _value_of(dealer_card)

    # Occasional bluff (10% chance to deviate)
    if random.random() < 0.1:
        return "hit" if player_value < 19 else "stand"

    # Doubling down logic
    if can_double:
        if player_value == 11:
            return "double"
        if player_value == 10 and dealer_value <= 9:
            return "double"
        if player_value == 9 and dealer_value >= 3 and dealer_value <= 6:
            return "double"

    if player_is_soft:
        if player_value >= 19:
            return "stand"
        if player_value == 18 and dealer_value <= 8:
            return "stand"
        return "hit"

    if player_value >= 17:
        return "stand"
    if player_value <= 11:
        return "hit"
    if player_value == 12:
        if dealer_value >= 4 and dealer_value <= 6:
            return "stand"
        return "hit"
    if player_value >= 13 and player_value <= 16:
        if dealer_value <= 6:
            return "stand"
        return "hit"

    return "hit" # Fallback
