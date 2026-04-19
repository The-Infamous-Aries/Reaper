"""
SS Brain — Pet Survivor Series round logic.

Scoring:
  Survive Score     = level / multiplier / 10   (movement / perception)
  Elimination Score = Survive Score × 1.2^adv × 0.8^|disadv|  (combat)
  Win probability   = sigmoid-clamped ratio of elimination scores (5–95%)
                      with a small upset window so upsets are rare but real.

Movement (SS Brain):
  Priority order per pet each round:
    1. Enemies      → always chase, ignore all other logic
    2. Best Friends → stay in same zone while field > 10%
    3. Dominant pets hunt — move toward weakest stranger in range
    4. Flee         → score-gap-weighted flee from stronger strangers;
                      boldness (kills × 0.15, cap 0.75) reduces flee chance
    5. Foes         → roam preferred zones freely, no flee
    6. Friends      → avoid their zones while field > 25%
    7. Default      → element-preferred zones, weighted by element affinity
    8. Arena pressure → as rounds accumulate with no eliminations, pets are
                        forced into a shrinking pool of "hot zones" to guarantee
                        encounters happen.

Encounter chance per zone:
  Base 65% (2 pets) → 85% (3+).
  Enemies in same zone: always encounter.
  Foes in same zone: 90% encounter.
  Friends in same zone: 40% encounter.
  BFs in same zone: 20% encounter.
  Dominant pet (score > 1.5× opponent): +15% encounter chance.
  Arena pressure (stale rounds): encounter chance floors raised further.

Deal-making:
  After _DEAL_ROUND_THRESHOLD rounds with no eliminations, pets that are
  strangers or foes may form a temporary truce (deal) to gang up on a
  common threat. Deals are stored in game["_deals"] and last
  _DEAL_DURATION rounds. During a deal, the two pets act as "friends"
  for movement and encounter purposes, but the deal can break at any time
  if one of them is the last two standing.

Combat resolution:
  True per-matchup elimination scores computed for each side.
  Group combat: average score of each side vs representative opponent.
  Win probability clamped 5–95%; close scores produce real tension.
  Upset multiplier: if loser's score > 0.85× winner's, upset chance +5%.

Narrative:
  Solo lines reflect actual behaviour: hunting, fleeing, guarding BF,
  circling foe, avoiding friend, or neutral patrol — with score-gap
  commentary, kill-streak flavour, and late-game pressure lines.
  Elimination lines: winner's attack action, loser's defend action,
  element advantage line, type advantage line, relationship close,
  score-gap commentary, and kill-count flavour all woven together.
"""
from __future__ import annotations

import json
import os
import random
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Arena pressure + deal-making constants
# ---------------------------------------------------------------------------

# After this many consecutive rounds with no eliminations, the arena starts
# forcing pets into fewer zones (pressure) and pets start making deals.
_PRESSURE_START_ROUND = 3   # pressure begins after 3 quiet rounds
_DEAL_ROUND_THRESHOLD = 4   # deals start forming after 4 quiet rounds
_DEAL_DURATION        = 3   # a deal lasts up to 3 rounds
_DEAL_CHANCE          = 0.55  # 55% chance a stranger/foe pair forms a deal each quiet round

# ── New feature constants ─────────────────────────────────────────────────────
_RAMPAGE_THRESHOLD    = 3    # kills needed to enter rampage state
_ZONE_TENURE_BONUS    = 0.12 # +12% combat score per round holding a zone (cap 2 rounds = +24%)
_ZONE_TENURE_CAP      = 2    # max rounds of tenure bonus
_INJURY_PENALTY       = 0.20 # wounded pets fight at -20% score
_LAST_STAND_BONUS     = 0.25 # bottom-10% pets get +25% score ("nothing to lose")
_BETRAYAL_FIGHT_CHANCE = 0.40 # 40% chance expired deal partners fight immediately

# ── Psychological breakdown constants ─────────────────────────────────────────
_BREAKDOWN_FRIEND_KILL = 2    # breakdown points for killing a friend
_BREAKDOWN_BF_KILL     = 4    # breakdown points for killing a best friend
_BREAKDOWN_BF_DEATH    = 3    # breakdown points when your BF dies
_BREAKDOWN_THRESHOLD   = 5    # points needed to trigger breakdown state
_BREAKDOWN_DURATION    = 3    # rounds breakdown lasts
_BREAKDOWN_AGGRO_BOOST = 0.30 # +30% encounter chance when broken down
_BREAKDOWN_FLEE_REDUCE = 0.40 # -40% flee chance when broken down (reckless)

# ── Environmental event constants ─────────────────────────────────────────────
_ENV_EVENT_CHANCE      = 0.25 # 25% chance per round after round 3
_ENV_EVENT_START_ROUND = 3    # environmental events start after round 3
_ENV_DAMAGE_CHANCE     = 0.60 # 60% chance pets in affected zone take damage
_ENV_FORCE_MOVE_CHANCE = 0.80 # 80% chance pets are forced to evacuate

# How many "hot zones" are available under pressure (shrinks as stale rounds grow)
def _pressure_zone_count(stale_rounds: int, total_zones: int = 13) -> int:
    """Return how many zones are available under arena pressure."""
    if stale_rounds < _PRESSURE_START_ROUND:
        return total_zones
    # Shrink by 2 zones per stale round beyond threshold, floor at 3
    reduction = (stale_rounds - _PRESSURE_START_ROUND + 1) * 2
    return max(3, total_zones - reduction)

# ---------------------------------------------------------------------------
# Data loading — action labels + locations (loaded once at import)
# ---------------------------------------------------------------------------

def _load_json(rel_path: str) -> Any:
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    full = os.path.join(base, rel_path)
    try:
        with open(full, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


_ACTION_LABELS: Dict[str, Any] = _load_json("Systems/Pets/Logic/action_labels.json")
_LOCATIONS_BASE: Dict[str, Any] = _load_json("Systems/Pets/Logic/Locations/locations_base.json")
_INFO: Dict[str, Any] = _load_json("Systems/Pets/Logic/info.json")

# Flat locations dict: style -> [name, ...]
_LOCATIONS: Dict[str, List[str]] = _LOCATIONS_BASE.get("locations", {})

# Pet species action lookup: species -> {Attack, Defense, Charge}
_PET_ACTIONS: Dict[str, Dict[str, str]] = {
    k: v.get("Actions", {})
    for k, v in _INFO.get("Pets", {}).items()
}

# Pet species stats lookup: species -> {ATT, DEF, ...}
_PET_STATS: Dict[str, Dict[str, int]] = {
    k: v.get("Stats", {})
    for k, v in _INFO.get("Pets", {}).items()
}


def _location_for_zone(zone: str) -> str:
    pool = _LOCATIONS.get(zone) or _LOCATIONS.get("basic") or ["Open Field"]
    return random.choice(pool)


def _get_action_label(cat: str, elem: str, elem2: str, action: str) -> str:
    """
    Look up action label from action_labels.json.
    Tries dual-element key first, then single element, then basic.
    action: 'attack' | 'defend' | 'charge'
    """
    c = _norm_cat(cat)
    e1 = (elem or "basic").lower()
    e2 = (elem2 or "").lower()
    cat_block = _ACTION_LABELS.get(c, _ACTION_LABELS.get("land", {}))

    # Try dual-element keys (both orderings)
    if e2 and e2 != "basic":
        for key in (f"{e1}_{e2}", f"{e2}_{e1}"):
            if key in cat_block:
                return cat_block[key].get(action, action.title())

    # Single element
    if e1 in cat_block:
        return cat_block[e1].get(action, action.title())

    # Basic fallback
    return cat_block.get("basic", {}).get(action, action.title())


def _pet_action_name(info: Dict, action: str) -> str:
    """
    Return the named action for a pet.
    Priority:
      1. Custom saved action labels on the participant record (action_labels field)
      2. Real pets: species actions from info.json
      3. Fallback: action_labels.json by element/category
    action: 'attack' | 'defend' | 'charge'
    """
    # 1. Custom labels saved via /pets/rename  (keys: "attack", "defense", "charge")
    custom = info.get("action_labels") or {}
    # The rename endpoint saves "defense" for the defend action
    lookup_key = "defense" if action == "defend" else action
    if custom.get(lookup_key):
        return custom[lookup_key]

    # 2. Species actions from info.json
    species = info.get("species", "")
    if species and species in _PET_ACTIONS:
        key_map = {"attack": "Attack", "defend": "Defense", "charge": "Charge"}
        val = _PET_ACTIONS[species].get(key_map.get(action, action.title()), "")
        if val:
            return val

    # 3. action_labels.json fallback
    return _get_action_label(
        info.get("category", "land"),
        info.get("element", "basic"),
        info.get("element2", ""),
        action,
    )


def _preferred_action(info: Dict) -> str:
    """
    Return 'attack' if ATT >= DEF for this pet, else 'defend'.
    Uses species stats from info.json; falls back to 'attack'.
    """
    species = info.get("species", "")
    stats = _PET_STATS.get(species, {})
    att = stats.get("ATT", 10)
    def_ = stats.get("DEF", 10)
    return "attack" if att >= def_ else "defend"


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

ELEM_STRONG: Dict[str, List[str]] = {
    "fire":     ["ice", "plant", "necro"],
    "water":    ["fire", "rock", "air"],
    "electric": ["water", "plant", "fighting"],
    "ice":      ["air", "electric", "water"],
    "plant":    ["water", "air", "psychic"],
    "rock":     ["electric", "fire", "ice"],
    "air":      ["rock", "fighting", "electric"],
    "magic":    ["psychic", "fighting", "fire"],
    "holy":     ["necro", "magic", "rock"],
    "necro":    ["holy", "magic", "plant"],
    "psychic":  ["holy", "necro", "magic"],
    "fighting": ["ice", "psychic", "holy"],
}

_TYPE_STRONG: Dict[str, str] = {
    "flying": "land", "land": "swimming", "swimming": "flying",
}


def _norm_cat(cat: str) -> str:
    c = (cat or "land").lower()
    if c in ("air", "flying"):     return "flying"
    if c in ("water", "swimming"): return "swimming"
    return "land"


def survive_score(info: Dict) -> float:
    level      = max(1, int(info.get("level", 1)))
    multiplier = max(1, int(info.get("multiplier", 1)))
    return level / multiplier / 10


def charge_multiplier(charge_stacks: int) -> float:
    """
    Charge multiplier for a pet that has avoided combat for N consecutive rounds.
    0 stacks = 1.0×, 1 = 1.15×, 2 = 1.30×, 3 = 1.45×, 4 = 1.60×,
    5 = 1.75×, 6 = 1.90×, 7 = 2.05×, 8+ = 2.20× (cap).
    Stronger bonus than before so charged pets are genuinely threatening.
    """
    return 1.0 + min(charge_stacks, 8) * 0.15


def count_advantages(attacker: Dict, defender: Dict) -> int:
    """
    Net advantage count across all matchup axes:
      1. Type triangle  (flying > land > swimming > flying)
      2. Primary element vs primary element
      3. Attacker element2 vs defender primary
      4. Attacker primary vs defender element2
      5. Attacker element2 vs defender element2
    +1 per advantage axis, -1 per disadvantage axis.
    """
    cat_a = _norm_cat(attacker.get("category", "land"))
    cat_b = _norm_cat(defender.get("category", "land"))
    ea    = (attacker.get("element")  or "basic").lower()
    ea2   = (attacker.get("element2") or "").lower()
    eb    = (defender.get("element")  or "basic").lower()
    eb2   = (defender.get("element2") or "").lower()

    adv = 0

    # 1. Type triangle
    if _TYPE_STRONG.get(cat_a) == cat_b:   adv += 1
    elif _TYPE_STRONG.get(cat_b) == cat_a: adv -= 1

    # 2. Primary vs primary
    if eb  in ELEM_STRONG.get(ea,  []): adv += 1
    elif ea in ELEM_STRONG.get(eb,  []): adv -= 1

    # 3. Attacker element2 vs defender primary
    if ea2:
        if eb  in ELEM_STRONG.get(ea2, []): adv += 1
        elif ea2 in ELEM_STRONG.get(eb, []): adv -= 1

    # 4. Attacker primary vs defender element2
    if eb2:
        if eb2 in ELEM_STRONG.get(ea,  []): adv += 1
        elif ea in ELEM_STRONG.get(eb2, []): adv -= 1

    # 5. Attacker element2 vs defender element2
    if ea2 and eb2:
        if eb2 in ELEM_STRONG.get(ea2, []): adv += 1
        elif ea2 in ELEM_STRONG.get(eb2, []): adv -= 1

    return adv


def elimination_score(
    info: Dict,
    opponent: Dict,
    attacker_charge: int = 0,
    zone_tenure_rounds: int = 0,
    is_wounded: bool = False,
    is_last_stand: bool = False,
    is_in_home_zone: bool = False,
    opponent_in_home_zone: bool = False,
) -> float:
    """
    Combat score for info attacking opponent.
    Factors: element/type advantages, charge, zone tenure, injury, last stand.

    Zone tenure: +12% per round held (cap 2 rounds = +24%) when fighting in own zone.
    Opponent in attacker's zone: -8% (challenger disadvantage).
    Wounded: -20% score for one round after barely surviving.
    Last stand: +25% score when in bottom 10% of field.
    """
    base    = survive_score(info)
    net_adv = count_advantages(info, opponent)
    if net_adv >= 0:
        score = base * (1.2 ** net_adv)
    else:
        score = base * (0.8 ** abs(net_adv))
    score *= charge_multiplier(attacker_charge)

    # Zone tenure bonus — fighting in your own held zone
    if zone_tenure_rounds > 0 and is_in_home_zone:
        tenure_bonus = 1.0 + min(zone_tenure_rounds, _ZONE_TENURE_CAP) * _ZONE_TENURE_BONUS
        score *= tenure_bonus

    # Challenger disadvantage — entering someone else's held zone
    if opponent_in_home_zone and zone_tenure_rounds == 0:
        score *= (1.0 - _ZONE_TENURE_BONUS)

    # Injury penalty
    if is_wounded:
        score *= (1.0 - _INJURY_PENALTY)

    # Last stand bonus
    if is_last_stand:
        score *= (1.0 + _LAST_STAND_BONUS)

    return score


def elim_win_prob(uid_a: str, uid_b: str, p_map: Dict,
                  charge_a: int = 0, charge_b: int = 0,
                  zone_tenure_a: int = 0, zone_tenure_b: int = 0,
                  wounded_a: bool = False, wounded_b: bool = False,
                  last_stand_a: bool = False, last_stand_b: bool = False,
                  fight_zone: str = "",
                  zone_tenure_map: Dict = None) -> float:
    """
    Win probability for uid_a vs uid_b.
    Uses ratio of elimination scores (with all modifiers), clamped 5–95%.
    """
    ia = p_map.get(uid_a, {})
    ib = p_map.get(uid_b, {})
    ztm = zone_tenure_map or {}

    # Determine if each pet is fighting in their held zone
    a_home = ztm.get(uid_a, {}).get("zone", "") == fight_zone if fight_zone else False
    b_home = ztm.get(uid_b, {}).get("zone", "") == fight_zone if fight_zone else False
    a_tenure = ztm.get(uid_a, {}).get("rounds", 0) if a_home else 0
    b_tenure = ztm.get(uid_b, {}).get("rounds", 0) if b_home else 0

    sa = elimination_score(ia, ib, attacker_charge=charge_a,
                           zone_tenure_rounds=a_tenure, is_wounded=wounded_a,
                           is_last_stand=last_stand_a,
                           is_in_home_zone=a_home, opponent_in_home_zone=b_home)
    sb = elimination_score(ib, ia, attacker_charge=charge_b,
                           zone_tenure_rounds=b_tenure, is_wounded=wounded_b,
                           is_last_stand=last_stand_b,
                           is_in_home_zone=b_home, opponent_in_home_zone=a_home)
    total = sa + sb
    if total <= 0:
        return 0.5
    raw = sa / total
    ratio = sa / max(sb, 1e-9)
    if 0.90 <= ratio <= 1.10:
        raw = 0.5 + (raw - 0.5) * 0.80
    elif ratio >= 2.0 or ratio <= 0.5:
        raw = 0.5 + (raw - 0.5) * 1.15
    return max(0.05, min(0.95, raw))


def _group_combat_odds(side_a: List[str], side_b: List[str], p_map: Dict,
                       charge_stacks: Dict[str, int] = None,
                       wounded_set: set = None,
                       last_stand_set: set = None,
                       zone_tenure_map: Dict = None,
                       fight_zone: str = "") -> float:
    """Win probability for side_a vs side_b, including all modifiers."""
    if not side_a or not side_b:
        return 0.5
    if charge_stacks is None:
        charge_stacks = {}
    wounded_set    = wounded_set    or set()
    last_stand_set = last_stand_set or set()
    ztm            = zone_tenure_map or {}

    rep_a = max(side_a, key=lambda u: survive_score(p_map.get(u, {})))
    rep_b = max(side_b, key=lambda u: survive_score(p_map.get(u, {})))

    def _escore(u: str, rep_opp: str, side_opp_rep: str) -> float:
        a_home = ztm.get(u, {}).get("zone", "") == fight_zone if fight_zone else False
        o_home = ztm.get(side_opp_rep, {}).get("zone", "") == fight_zone if fight_zone else False
        tenure = ztm.get(u, {}).get("rounds", 0) if a_home else 0
        return elimination_score(
            p_map.get(u, {}), p_map.get(rep_opp, {}),
            attacker_charge=charge_stacks.get(u, 0),
            zone_tenure_rounds=tenure,
            is_wounded=(u in wounded_set),
            is_last_stand=(u in last_stand_set),
            is_in_home_zone=a_home,
            opponent_in_home_zone=o_home,
        )

    sa = sum(_escore(u, rep_b, rep_a) for u in side_a) / len(side_a)
    sb = sum(_escore(u, rep_a, rep_b) for u in side_b) / len(side_b)
    total = sa + sb
    if total <= 0:
        return 0.5
    raw = sa / total
    ratio = sa / max(sb, 1e-9)
    if 0.90 <= ratio <= 1.10:
        raw = 0.5 + (raw - 0.5) * 0.80
    elif ratio >= 2.0 or ratio <= 0.5:
        raw = 0.5 + (raw - 0.5) * 1.15
    return max(0.05, min(0.95, raw))


# ---------------------------------------------------------------------------
# Zone constants — must match JS frontend MAP_ZONES exactly
# ---------------------------------------------------------------------------
#
# Map layout (1600×1066, 4 rows × 4 cols, basic = 2×2 center):
#
#   Col:    0%      25%     50%     75%    100%
#   Row 0:  ice   | holy  | air   | psychic
#   Row 1:  plant | [basic 2×2 center] | rock
#   Row 2:  magic | [basic 2×2 center] | fighting
#   Row 3:  water | necro  | electric | fire
#
# basic occupies the full center (cols 25–75%, rows 25–75%) — it is the
# neutral hub that all pets can pass through.

ALL_ZONES: List[str] = [
    "basic", "fire", "water", "electric", "ice", "plant",
    "rock", "air", "magic", "holy", "necro", "fighting", "psychic",
]

# Zones that are physically adjacent to each zone on the map.
# Used for movement: pets prefer to move to adjacent zones rather than
# teleporting across the map, and the brain uses this for realistic pathing.
ZONE_ADJACENCY: Dict[str, List[str]] = {
    # Row 0 (top)
    "ice":      ["holy", "plant", "basic"],
    "holy":     ["ice", "air", "plant", "basic"],
    "air":      ["holy", "psychic", "basic", "rock"],
    "psychic":  ["air", "basic", "rock"],
    # Left/right flanks (rows 1–2)
    "plant":    ["ice", "holy", "basic", "magic", "water"],
    "rock":     ["air", "psychic", "basic", "fighting", "fire"],
    "magic":    ["plant", "basic", "water"],
    "fighting": ["rock", "basic", "fire"],
    # Row 3 (bottom)
    "water":    ["magic", "plant", "basic", "necro"],
    "necro":    ["water", "basic", "electric"],
    "electric": ["necro", "basic", "fire"],
    "fire":     ["electric", "fighting", "rock", "basic"],
    # Basic — center hub, adjacent to everything on its border
    "basic":    ["ice", "holy", "air", "psychic",
                 "plant", "rock", "magic", "fighting",
                 "water", "necro", "electric", "fire"],
}

# Element-preferred zones: primary home zone first, then adjacent zones the
# pet naturally gravitates toward. basic is intentionally NOT in most lists
# so pets don't default to the center — they use it as a transit hub only.
_ELEM_PREFERRED: Dict[str, List[str]] = {
    "fire":     ["fire", "fighting", "electric", "rock"],
    "water":    ["water", "magic", "necro", "plant"],
    "electric": ["electric", "necro", "air", "fighting"],
    "ice":      ["ice", "holy", "air", "plant"],
    "plant":    ["plant", "magic", "water", "ice"],
    "rock":     ["rock", "fighting", "fire", "psychic"],
    "air":      ["air", "holy", "psychic", "ice"],
    "magic":    ["magic", "plant", "water", "necro"],
    "holy":     ["holy", "ice", "air", "plant"],
    "necro":    ["necro", "magic", "water", "electric"],
    "psychic":  ["psychic", "air", "rock", "holy"],
    "fighting": ["fighting", "rock", "fire", "electric"],
    "basic":    ["basic", "holy", "plant", "air"],  # basic pets are comfortable anywhere
}

# Zones where each element has a combat advantage (element strong vs zone's theme).
# Pets with advantages in a zone are more likely to hunt there.
_ELEM_ADVANTAGE_ZONES: Dict[str, List[str]] = {
    "fire":     ["plant", "ice", "necro"],
    "water":    ["fire", "rock", "electric"],
    "electric": ["water", "plant", "fighting"],
    "ice":      ["air", "electric", "water"],
    "plant":    ["water", "magic", "psychic"],
    "rock":     ["electric", "fire", "ice"],
    "air":      ["rock", "fighting", "electric"],
    "magic":    ["psychic", "fighting", "fire"],
    "holy":     ["necro", "magic", "rock"],
    "necro":    ["holy", "magic", "plant"],
    "psychic":  ["holy", "necro", "magic"],
    "fighting": ["ice", "psychic", "holy"],
    "basic":    [],
}

# ---------------------------------------------------------------------------
# Psychological breakdown helpers
# ---------------------------------------------------------------------------

def _update_breakdown_points(game: Dict, uid: str, points: int, reason: str = "") -> bool:
    """
    Add breakdown points to a pet. Returns True if they hit the breakdown threshold.
    Breakdown is triggered by traumatic events: killing friends/BFs, losing BFs.
    """
    breakdown_map = game.setdefault("_breakdown_points", {})
    breakdown_map[uid] = breakdown_map.get(uid, 0) + points
    
    if breakdown_map[uid] >= _BREAKDOWN_THRESHOLD:
        # Trigger breakdown state
        breakdown_state = game.setdefault("_breakdown_state", {})
        current_round = game.get("round_index", 0)
        breakdown_state[uid] = {
            "triggered_round": current_round,
            "expires_round": current_round + _BREAKDOWN_DURATION,
            "reason": reason,
        }
        # Reset points after breakdown triggers
        breakdown_map[uid] = 0
        return True
    return False


def _process_breakdown_triggers(game: Dict, eliminated_uid: str, killer_uids: List[str], 
                                rel_map: Dict, p_map: Dict) -> List[str]:
    """
    Process psychological breakdown triggers when someone is eliminated.
    Returns list of breakdown trigger narratives.
    """
    narratives = []
    
    # Check if any killers just killed a friend or BF
    for killer_uid in killer_uids:
        if is_best_friend(rel_map, killer_uid, eliminated_uid):
            reason = f"killed their best friend {_pname(p_map.get(eliminated_uid, {}))}"
            if _update_breakdown_points(game, killer_uid, _BREAKDOWN_BF_KILL, reason):
                killer_name = _pname(p_map.get(killer_uid, {}))
                line = random.choice(_BREAKDOWN_TRIGGER_LINES).replace("{name}", killer_name)
                narratives.append(line)
        elif is_friend(rel_map, killer_uid, eliminated_uid):
            reason = f"killed their friend {_pname(p_map.get(eliminated_uid, {}))}"
            if _update_breakdown_points(game, killer_uid, _BREAKDOWN_FRIEND_KILL, reason):
                killer_name = _pname(p_map.get(killer_uid, {}))
                line = random.choice(_BREAKDOWN_TRIGGER_LINES).replace("{name}", killer_name)
                narratives.append(line)
    
    # Check if any surviving BFs are traumatized by the death
    alive = game.get("alive_ids", [])
    for survivor_uid in alive:
        if survivor_uid != eliminated_uid and is_best_friend(rel_map, survivor_uid, eliminated_uid):
            reason = f"watched their best friend {_pname(p_map.get(eliminated_uid, {}))} die"
            if _update_breakdown_points(game, survivor_uid, _BREAKDOWN_BF_DEATH, reason):
                survivor_name = _pname(p_map.get(survivor_uid, {}))
                line = random.choice(_BREAKDOWN_TRIGGER_LINES).replace("{name}", survivor_name)
                narratives.append(line)
    
    return narratives


def _expire_breakdowns(game: Dict, current_round: int) -> List[str]:
    """Remove expired breakdown states. Returns recovery narratives."""
    breakdown_state = game.get("_breakdown_state", {})
    expired_uids = []
    narratives = []
    
    for uid, state in breakdown_state.items():
        if state.get("expires_round", 0) <= current_round:
            expired_uids.append(uid)
    
    for uid in expired_uids:
        del breakdown_state[uid]
        # Optional: add recovery narrative
        # p_map_ref = game.get("_p_map_cache", {})
        # name = _pname(p_map_ref.get(uid, {}))
        # narratives.append(f"💚 {name} slowly regains their composure — the breakdown is passing.")
    
    return narratives


def _is_broken_down(game: Dict, uid: str) -> bool:
    """Check if a pet is currently in breakdown state."""
    breakdown_state = game.get("_breakdown_state", {})
    return uid in breakdown_state


# ---------------------------------------------------------------------------
# Environmental event helpers
# ---------------------------------------------------------------------------

def _trigger_environmental_event(game: Dict, current_round: int, alive: List[str], 
                                 p_map: Dict) -> List[str]:
    """
    Trigger random environmental disasters in zones.
    Returns list of event narratives.
    """
    if current_round < _ENV_EVENT_START_ROUND:
        return []
    
    if random.random() > _ENV_EVENT_CHANCE:
        return []
    
    # Choose a random zone for the environmental event
    affected_zone = random.choice(ALL_ZONES)
    
    # Get zone display name
    zone_name_map = {
        "fire":"Emberlands","water":"Tideways","electric":"Stormfields",
        "ice":"Frostreach","plant":"Verdant Wilds","rock":"Stone Marches",
        "air":"Skylands","magic":"Arcane Vale","holy":"Sanctified Plains",
        "necro":"Shadow Wastes","fighting":"Battlegrounds","psychic":"Mindscapes",
        "basic":"Neutral Grounds",
    }
    zone_display = zone_name_map.get(affected_zone, affected_zone.title())
    
    # Get pets currently in the affected zone
    cur_positions = {
        uid: ((game.get("map_positions") or {}).get(uid) or {}).get("style", "basic")
        for uid in alive
    }
    pets_in_zone = [uid for uid in alive if cur_positions.get(uid) == affected_zone]
    
    narratives = []
    
    # Main event announcement
    event_lines = _ENV_EVENT_LINES.get(affected_zone, _ENV_EVENT_LINES["basic"])
    event_line = random.choice(event_lines).replace("{zone_name}", zone_display)
    narratives.append(event_line)
    
    # Add atmospheric buildup (50% chance)
    if random.random() < 0.50:
        buildup_lines = [
            f"⚠️ Warning signs appeared moments before the disaster struck the {zone_display}!",
            f"🌡️ The air grew ominous in the {zone_display} just before chaos erupted!",
            f"📡 Arena sensors detected the incoming threat to the {zone_display}!",
            f"🎭 The gamemakers smile as their trap activates in the {zone_display}!",
        ]
        narratives.insert(-1, random.choice(buildup_lines))
    
    if not pets_in_zone:
        narratives.append(f"🍀 The {zone_display} is empty — no one is caught in the disaster.")
        return narratives
    
    # Track environmental damage for this round
    env_damaged = game.setdefault("_env_damaged", set())
    env_evacuated = game.setdefault("_env_evacuated", {})
    
    # Process each pet in the affected zone
    for uid in pets_in_zone:
        pet_name = _pname(p_map.get(uid, {}))
        
        # Damage chance
        if random.random() < _ENV_DAMAGE_CHANCE:
            env_damaged.add(uid)
            damage_line = random.choice(_ENV_DAMAGE_LINES).replace("{name}", pet_name)
            narratives.append(damage_line)
        
        # Forced evacuation chance
        if random.random() < _ENV_FORCE_MOVE_CHANCE:
            # Force pet to move to an adjacent zone next round
            adjacent_zones = ZONE_ADJACENCY.get(affected_zone, [])
            if adjacent_zones:
                new_zone = random.choice(adjacent_zones)
                env_evacuated[uid] = new_zone
                evac_line = random.choice(_ENV_EVACUATION_LINES).replace("{name}", pet_name)
                narratives.append(evac_line)
        else:
            # Pet stays and endures
            survivor_line = random.choice(_ENV_SURVIVOR_LINES).replace("{name}", pet_name)
            narratives.append(survivor_line)
    
    return narratives


def _apply_environmental_effects(game: Dict, uid: str, scores: Dict[str, float]) -> float:
    """
    Apply environmental damage effects to combat scores.
    Pets damaged by environmental events fight at reduced effectiveness.
    """
    env_damaged = game.get("_env_damaged", set())
    if uid in env_damaged:
        # Environmental damage reduces combat effectiveness by 15%
        return scores.get(uid, 1.0) * 0.85
    return scores.get(uid, 1.0)


def _is_environmentally_damaged(game: Dict, uid: str) -> bool:
    """Check if a pet is currently environmentally damaged."""
    env_damaged = game.get("_env_damaged", set())
    return uid in env_damaged


def _handle_environmental_evacuation(game: Dict, uid: str, chosen_zone: str) -> str:
    """
    Override zone choice if pet was forced to evacuate by environmental event.
    """
    env_evacuated = game.get("_env_evacuated", {})
    if uid in env_evacuated:
        forced_zone = env_evacuated[uid]
        # Remove from evacuation list after applying
        del env_evacuated[uid]
        return forced_zone
    return chosen_zone


def _generate_round_summary(game: Dict, round_num: int, eliminated: List[str], 
                           remaining: int, env_events: List[str], 
                           breakdown_events: List[str]) -> Dict[str, Any]:
    """
    Generate an enhanced round summary with statistics and highlights.
    """
    p_map = game.get("_p_map_cache", {})
    
    # Basic stats
    eliminations_count = len(eliminated)
    total_start = game.get("_total_start", remaining + eliminations_count)
    elimination_rate = (eliminations_count / max(1, total_start)) * 100
    
    # Special events count
    env_event_count = len([e for e in env_events if not e.startswith("🍀")])
    breakdown_count = len(breakdown_events)
    
    # Generate summary text
    summary_parts = []
    
    # Elimination summary
    if eliminations_count == 0:
        summary_parts.append("🛡️ No eliminations this round — the tension builds!")
    elif eliminations_count == 1:
        summary_parts.append(f"💀 1 pet eliminated ({elimination_rate:.1f}% of the field)")
    else:
        summary_parts.append(f"💀 {eliminations_count} pets eliminated ({elimination_rate:.1f}% of the field)")
    
    # Environmental events
    if env_event_count > 0:
        summary_parts.append(f"🌪️ {env_event_count} environmental disaster{'s' if env_event_count != 1 else ''} struck!")
    
    # Psychological breakdowns
    if breakdown_count > 0:
        summary_parts.append(f"💔 {breakdown_count} pet{'s' if breakdown_count != 1 else ''} suffered psychological breakdown!")
    
    # Remaining pets
    if remaining <= 5:
        summary_parts.append(f"⚠️ Only {remaining} pets remain — the end is near!")
    elif remaining <= 10:
        summary_parts.append(f"🔥 {remaining} pets still fighting — the field is thinning!")
    else:
        summary_parts.append(f"📊 {remaining} pets remain in the arena")
    
    # Special round milestones
    if round_num == 1:
        summary_parts.append("🚀 Opening bloodbath complete!")
    elif round_num % 5 == 0:
        summary_parts.append(f"🏁 Round {round_num} milestone reached!")
    
    return {
        "round": round_num,
        "eliminated_count": eliminations_count,
        "remaining_count": remaining,
        "elimination_rate": round(elimination_rate, 1),
        "environmental_events": env_event_count,
        "psychological_breaks": breakdown_count,
        "summary_text": " • ".join(summary_parts),
        "is_milestone": round_num % 5 == 0 or remaining <= 5,
    }


# ---------------------------------------------------------------------------
# Relationship helpers
# ---------------------------------------------------------------------------

def _rel(rel_map: Dict, uid_a: str, uid_b: str) -> Optional[str]:
    return rel_map.get(uid_a, {}).get(uid_b)


def _either_rel(rel_map: Dict, a: str, b: str) -> Optional[str]:
    return _rel(rel_map, a, b) or _rel(rel_map, b, a)


def is_best_friend(rel_map: Dict, a: str, b: str) -> bool:
    return _rel(rel_map, a, b) == "best_friend" or _rel(rel_map, b, a) == "best_friend"


def is_friend(rel_map: Dict, a: str, b: str) -> bool:
    return _either_rel(rel_map, a, b) == "friend"


def is_foe(rel_map: Dict, a: str, b: str) -> bool:
    return _either_rel(rel_map, a, b) == "foe"


def is_enemy(rel_map: Dict, a: str, b: str) -> bool:
    return _rel(rel_map, a, b) == "enemy" or _rel(rel_map, b, a) == "enemy"


# ---------------------------------------------------------------------------
# Deal helpers — temporary in-game truces between strangers/foes
# ---------------------------------------------------------------------------

def _get_deals(game: Dict) -> Dict[str, Any]:
    """Return the active deals dict from game state, creating it if absent."""
    return game.setdefault("_deals", {})


def _deal_key(uid_a: str, uid_b: str) -> str:
    """Canonical key for a deal between two pets (order-independent)."""
    return "|".join(sorted([uid_a, uid_b]))


def has_deal(game: Dict, uid_a: str, uid_b: str) -> bool:
    """Return True if uid_a and uid_b have an active deal that is in effect this round.
    FIX #11: deals formed this round don't take effect until next round."""
    deals = _get_deals(game)
    key = _deal_key(uid_a, uid_b)
    if key not in deals:
        return False
    # New deals formed this round are not yet in effect
    if deals[key].get("_new_this_round"):
        return False
    return True


def _deal_partner(game: Dict, uid: str, alive: List[str]) -> Optional[str]:
    """Return uid's current deal partner if they have one and it's still alive."""
    deals = _get_deals(game)
    for key, info in deals.items():
        parts = key.split("|")
        if uid in parts:
            partner = parts[0] if parts[1] == uid else parts[1]
            if partner in alive:
                return partner
    return None


def _form_deals(
    game: Dict,
    alive: List[str],
    p_map: Dict,
    rel_map: Dict,
    scores: Dict[str, float],
    stale_rounds: int,
    current_round: int,
) -> List[str]:
    """
    Try to form new deals between stranger/foe pairs.
    Returns a list of narrative strings for new deals formed.
    Called when stale_rounds >= _DEAL_ROUND_THRESHOLD.
    """
    deals = _get_deals(game)
    narratives: List[str] = []

    # Find all stranger/foe pairs that don't already have a deal
    candidates: List[Tuple[str, str]] = []
    for i, uid_a in enumerate(alive):
        for uid_b in alive[i + 1:]:
            if is_enemy(rel_map, uid_a, uid_b):
                continue  # enemies never deal
            if is_best_friend(rel_map, uid_a, uid_b):
                continue  # BFs don't need deals
            if has_deal(game, uid_a, uid_b):
                continue  # already have a deal
            # Strangers and foes are eligible
            candidates.append((uid_a, uid_b))

    random.shuffle(candidates)

    # Form deals — scale how many by how stale things are
    max_new_deals = max(1, stale_rounds - _DEAL_ROUND_THRESHOLD + 1)
    formed = 0
    for uid_a, uid_b in candidates:
        if formed >= max_new_deals:
            break
        if random.random() < _DEAL_CHANCE:
            key = _deal_key(uid_a, uid_b)
            deals[key] = {
                "formed_round": current_round,
                "expires_round": current_round + _DEAL_DURATION,
                "uid_a": uid_a,
                "uid_b": uid_b,
            }
            name_a = _pname(p_map.get(uid_a, {}))
            name_b = _pname(p_map.get(uid_b, {}))
            line = random.choice(_DEAL_FORM_LINES).replace("{A}", name_a).replace("{B}", name_b)
            narratives.append(line)
            formed += 1

    return narratives


def _expire_deals(game: Dict, current_round: int, alive: List[str]) -> Tuple[List[str], List[Tuple[str, str]]]:
    """
    Remove deals that have expired or whose participants are dead.
    Also clears the _new_this_round flag so deals formed last round are now active.
    Returns (narrative_strings, betrayal_pairs).
    betrayal_pairs: list of (uid_a, uid_b) where both are alive and the deal
    expired naturally — 40% chance each pair becomes a betrayal fight.
    """
    deals = _get_deals(game)
    expired_keys = []
    narratives: List[str] = []
    betrayal_pairs: List[Tuple[str, str]] = []

    for key, info in deals.items():
        # Clear new-this-round flag — deal is now active
        info.pop("_new_this_round", None)

        uid_a = info.get("uid_a", "")
        uid_b = info.get("uid_b", "")
        if (info.get("expires_round", 0) <= current_round
                or uid_a not in alive
                or uid_b not in alive):
            expired_keys.append(key)
            # Only narrate/betray if both are still alive and deal ran its course
            if uid_a in alive and uid_b in alive and info.get("expires_round", 0) <= current_round:
                if random.random() < _BETRAYAL_FIGHT_CHANCE:
                    # Betrayal — they fight immediately; narrative set at fight time
                    betrayal_pairs.append((uid_a, uid_b))
                else:
                    p_map_ref = game.get("_p_map_cache", {})
                    name_a = p_map_ref.get(uid_a, {}).get("pet_name") or uid_a
                    name_b = p_map_ref.get(uid_b, {}).get("pet_name") or uid_b
                    narratives.append(
                        random.choice(_DEAL_BREAK_LINES)
                        .replace("{A}", name_a)
                        .replace("{B}", name_b)
                    )

    for key in expired_keys:
        deals.pop(key, None)

    return narratives, betrayal_pairs


def _effective_rel(game: Dict, rel_map: Dict, uid_a: str, uid_b: str) -> Optional[str]:
    """
    Return the effective relationship between two pets, accounting for active deals.
    A deal makes strangers/foes act as 'friend' for movement/encounter purposes.
    """
    base = _either_rel(rel_map, uid_a, uid_b)
    if base in ("best_friend", "enemy"):
        return base  # deals can't override these
    if has_deal(game, uid_a, uid_b):
        return "friend"  # deal = temporary friendship
    return base


# ---------------------------------------------------------------------------
# Narrative helpers
# ---------------------------------------------------------------------------

def _pname(info: Dict) -> str:
    return info.get("pet_name") or info.get("username") or "Unknown"


def _fmt_names(names: List[str]) -> str:
    if not names:       return "Unknown"
    if len(names) == 1: return names[0]
    if len(names) == 2: return f"{names[0]} and {names[1]}"
    return f"{', '.join(names[:-1])}, and {names[-1]}"


# ── Solo action context lines ─────────────────────────────────────────────────
_SEEK_LINES = [
    "is hunting down {target} across the arena",
    "has locked onto {target} and refuses to let them escape",
    "is tracking {target} through the terrain, closing fast",
    "pushes hard toward {target}'s position — this is personal",
    "has {target} in their sights and won't stop until it's done",
    "cuts through the zone, eyes fixed on {target}",
]
_SEEK_ENEMY_LINES = [
    "is hunting down their sworn enemy {target} — old grudges die hard",
    "has been waiting for this — {target} is finally in range",
    "charges toward {target} with everything they have — this rivalry ends today",
    "locks onto {target} with cold focus — no hesitation, no mercy",
]
_FLEE_LINES = [
    "keeps distance from the stronger competition, biding their time",
    "slips away before anyone can corner them",
    "reads the field and retreats to safer ground",
    "moves carefully, avoiding the heaviest threats",
    "scouts the edges, staying out of trouble for now",
    "pulls back — the odds aren't right yet",
]
_FLEE_DOMINANT_LINES = [
    "is outmatched here and knows it — survival first",
    "retreats from a clearly superior opponent, living to fight another round",
    "wisely avoids a fight they can't win right now",
    "backs off — the score gap is too wide to ignore",
]
_HUNT_DOMINANT_LINES = [
    "dominates the zone, daring anyone to challenge them",
    "patrols the area with authority — no one is safe nearby",
    "is the apex predator here and everyone knows it",
    "moves through the zone unchallenged, looking for the next target",
    "controls this part of the arena completely",
]
_BF_LINES = [
    "stays close to {bf}, watching each other's backs",
    "moves in step with {bf}, neither willing to split up",
    "and {bf} hold their ground together — strength in numbers",
    "keeps {bf} in sight as they navigate the arena side by side",
    "refuses to leave {bf}'s side — they came in together",
]
_BF_ENDGAME_LINES = [
    "and {bf} are the last ones standing together — the arena grows quiet",
    "stays shoulder to shoulder with {bf} as the field thins out",
    "and {bf} exchange a look — they both know what's coming",
]
_FRIEND_AVOID_LINES = [
    "steers clear of {friend} for now — no reason to fight yet",
    "spots {friend} nearby but lets them pass without incident",
    "and {friend} exchange a glance and go their separate ways",
    "gives {friend} space — there's no need to force this",
    "sees {friend} across the zone and deliberately takes a different path",
]
_FOE_LINES = [
    "prowls the same ground as {foe}, tension rising between them",
    "and {foe} circle each other warily — neither ready to commit",
    "keeps {foe} in their peripheral vision, waiting for the right moment",
    "and {foe} share the zone in uneasy silence",
]
_NEUTRAL_LINES = [
    "moves through the terrain, staying alert",
    "scouts the area and finds no immediate threats",
    "holds position and waits for the right moment",
    "presses forward, reading the field carefully",
    "navigates the zone with quiet confidence",
    "keeps moving, conserving energy for what's ahead",
    "surveys the arena from a strong position",
]
_LATE_GAME_LINES = [
    "feels the pressure as the field shrinks — every move counts now",
    "knows the end is near and tightens their focus",
    "can feel the arena closing in — time to make a move",
    "is one of the last ones standing and plays it carefully",
]
_KILL_STREAK_LINES = [
    "On a roll with {kills} eliminations and still going strong.",
    "Carrying the momentum of {kills} victories into this round.",
    "{kills} kills so far — the arena is running out of challengers.",
]

# ── Arena pressure lines (stale rounds, no eliminations) ─────────────────────
_PRESSURE_LINES = [
    "The arena walls close in — nowhere left to hide.",
    "The dead zones are shrinking. Everyone is being pushed together.",
    "The arena forces the survivors into tighter ground.",
    "There's no more room to run — the arena demands blood.",
    "The safe zones are gone. Every path leads to a fight now.",
]

# ── Deal-making lines ─────────────────────────────────────────────────────────
_DEAL_FORM_LINES = [
    "🤝 {A} and {B} exchange a tense nod — a temporary truce. Neither trusts the other, but the arena demands it.",
    "🤝 {A} approaches {B} cautiously. Words are exchanged. A deal is struck — for now.",
    "🤝 {B} signals to {A}: not yet. They have bigger problems. The truce holds — until it doesn't.",
    "🤝 {A} and {B} agree to hold off — there are stronger targets to deal with first.",
    "🤝 An uneasy alliance forms between {A} and {B}. The arena watches.",
]
_DEAL_ACTIVE_LINES = [
    "moves alongside {partner} — the deal still holds, for now",
    "keeps {partner} close — the truce is uneasy but useful",
    "and {partner} watch each other's backs, neither fully trusting the other",
    "holds to the deal with {partner} — there are bigger threats to handle first",
]
_DEAL_BREAK_LINES = [
    "💔 The deal between {A} and {B} expires — they're on their own again.",
    "💔 {A} and {B}'s truce has run its course. The alliance is over.",
    "💔 The temporary alliance between {A} and {B} dissolves. Back to survival.",
]

# ── Charge build-up lines (pet not in combat this round) ─────────────────────
_CHARGE_LINES = [
    "building power in the shadows — something is coming",
    "holds back and lets the energy build — not yet",
    "conserves strength, waiting for the perfect moment to strike",
    "channels focus inward — the charge is growing",
    "stays out of the fray, accumulating force",
    "bides their time — every round of patience adds to the blow",
]
_CHARGE_LINES_HIGH = [  # 3+ stacks
    "radiates barely-contained energy — the charge is almost ready",
    "is coiled like a spring — one more round and they'll be unstoppable",
    "the air around them crackles — the charge is at its peak",
    "holds a devastating amount of stored power — the arena should be afraid",
    "has been building this for rounds — whoever they hit next won't survive it",
    "moves with quiet menace — the charge is fully loaded",
]

# ── Rampage lines (3+ kill streak) ───────────────────────────────────────────
_RAMPAGE_SOLO_LINES = [
    "is on a rampage — {kills} eliminations and showing no signs of stopping",
    "tears through the arena on a {kills}-kill streak — the crowd is terrified",
    "has gone feral — {kills} down and hunting for more",
    "moves like a force of nature — {kills} eliminations and still hungry",
    "is unstoppable right now — {kills} kills and the arena knows it",
]
_RAMPAGE_HUNT_LINES = [
    "locks onto {target} — the rampage continues",
    "sets their sights on {target} — {kills} kills isn't enough",
    "charges toward {target} — nothing is stopping this streak",
]
_FLEE_RAMPAGE_LINES = [
    "gives ground to {rampager} — {kills} kills is not a fight to take right now",
    "reads the room and avoids {rampager} — that streak speaks for itself",
    "backs off from {rampager} — surviving is the priority",
    "steers well clear of {rampager} — {kills} eliminations and still going",
]
_HUNT_RAMPAGE_LINES = [
    "moves to intercept {rampager} — someone has to stop that streak",
    "targets {rampager} directly — {kills} kills and they need to be stopped",
    "steps up to challenge {rampager} — the arena needs a hero right now",
]

# ── Enhanced action context lines ────────────────────────────────────────────
_ENHANCED_CONTEXT_LINES = [
    # Weather/atmosphere
    "The arena air grows thick with tension as {name} {action}",
    "Under the watchful eyes of the crowd, {name} {action}",
    "As shadows lengthen across the arena, {name} {action}",
    "The silence is broken only by {name} as they {action}",
    
    # Emotional state
    "With grim determination, {name} {action}",
    "Fighting back fear, {name} {action}",
    "Adrenaline coursing through their veins, {name} {action}",
    "Heart pounding, {name} {action}",
    
    # Strategic thinking
    "Calculating their next move, {name} {action}",
    "Reading the field carefully, {name} {action}",
    "With tactical precision, {name} {action}",
    "Weighing their options, {name} {action}",
]

# ── Zone-specific atmospheric lines ───────────────────────────────────────────
_ZONE_ATMOSPHERE = {
    "fire": [
        "Heat shimmers rise from the scorched ground as {name} {action}",
        "Embers drift through the air while {name} {action}",
        "The acrid smell of smoke fills the air as {name} {action}",
    ],
    "water": [
        "Mist rises from the waterways as {name} {action}",
        "The sound of rushing water echoes while {name} {action}",
        "Droplets glisten in the light as {name} {action}",
    ],
    "ice": [
        "Frost crunches underfoot as {name} {action}",
        "Their breath forms clouds in the frigid air as {name} {action}",
        "Ice crystals catch the light while {name} {action}",
    ],
    "plant": [
        "Vines rustle in the breeze as {name} {action}",
        "The scent of wild growth fills the air while {name} {action}",
        "Leaves whisper secrets as {name} {action}",
    ],
    "necro": [
        "Shadows seem to move on their own as {name} {action}",
        "An unnatural chill fills the air while {name} {action}",
        "The very ground seems to pulse with dark energy as {name} {action}",
    ],
    "holy": [
        "Golden light bathes the area as {name} {action}",
        "A sense of peace contrasts with the danger as {name} {action}",
        "Sacred energy hums in the air while {name} {action}",
    ],
    "psychic": [
        "Reality seems to bend at the edges as {name} {action}",
        "Thoughts feel heavier in this place as {name} {action}",
        "The air itself seems to think while {name} {action}",
    ],
    "basic": [
        "In the neutral grounds, {name} {action}",
        "At the heart of the arena, {name} {action}",
        "Where all paths converge, {name} {action}",
    ],
}
_ZONE_HOLD_LINES = [
    "holds {zone}, daring anyone to challenge them",
    "has claimed {zone} — this is their ground now",
    "patrols {zone} with authority — no one enters unchallenged",
    "owns {zone} and everyone in the arena knows it",
    "stands firm in {zone} — they've made it their fortress",
]
_ZONE_CHALLENGER_LINES = [
    "enters {zone} — {holder} won't give it up without a fight",
    "pushes into {zone}, challenging {holder}'s claim",
    "steps into {holder}'s territory in {zone}",
]

# ── Injury lines ──────────────────────────────────────────────────────────────
_WOUNDED_SOLO_LINES = [
    "is wounded and moving carefully — one more hit could end it",
    "limps through the zone, trying to stay out of sight",
    "is hurt but still standing — survival instinct kicks in",
    "fights through the pain, looking for somewhere safe to recover",
    "is in bad shape after that last fight — every step is a risk",
]
_WOUNDED_ELIM_OPENER = [
    "{W} finds {L} wounded and doesn't hesitate at {LOC}",
    "{W} hunts down the injured {L} at {LOC} — no mercy",
    "{L} couldn't recover in time — {W} closes in at {LOC}",
    "{W} smells blood and finishes the job at {LOC}",
]

# ── Last stand lines ──────────────────────────────────────────────────────────
_LAST_STAND_SOLO_LINES = [
    "has nothing left to lose — and that makes them dangerous",
    "is the weakest one left standing, but they're not going quietly",
    "digs deep — the underdog isn't done yet",
    "refuses to go out without a fight — last stand energy",
    "is cornered and desperate — the most dangerous kind of opponent",
]
_LAST_STAND_ELIM_UPSET = [
    "{W} pulls off the impossible — the last stand paid off",
    "Nobody counted on {W} — the underdog just rewrote the script",
    "{W} had nothing to lose and everything to gain — and they took it",
    "The arena goes silent as {W} defies every expectation",
]

# ── Betrayal lines ────────────────────────────────────────────────────────────
_BETRAYAL_LINES = [
    "💔 The deal between {A} and {B} collapses — and {A} immediately turns on {B}!",
    "💔 {A} and {B}'s truce ends — and {A} wastes no time making a move!",
    "💔 The alliance is over. {A} decides to settle things with {B} right now.",
    "💔 {B} barely has time to react — {A} breaks the deal and attacks immediately!",
    "💔 The moment the deal expires, {A} turns on {B}. Trust was always a luxury.",
]

# ── Psychological breakdown lines ─────────────────────────────────────────────
_BREAKDOWN_TRIGGER_LINES = [
    "💀 {name} stares at their hands, shaking. The weight of what they've done is crushing them.",
    "😵 {name} breaks down completely — the arena has pushed them past their breaking point.",
    "💔 {name} collapses to their knees. The guilt and horror finally overwhelm them.",
    "🌪️ {name} snaps. Their eyes go wild — they're not thinking clearly anymore.",
    "😱 {name} screams at the sky. The psychological pressure has shattered their mind.",
    "💀 {name} laughs hysterically, then starts sobbing. They've lost all control.",
]
_BREAKDOWN_SOLO_LINES = [
    "moves erratically, muttering to themselves — the breakdown is complete",
    "stumbles through the zone, eyes unfocused and mind shattered",
    "acts without thinking, driven by pure instinct and trauma",
    "has lost all strategy — they're running on raw emotion now",
    "fights back tears while moving recklessly through the terrain",
    "can't stop shaking — the psychological damage is written all over them",
    "talks to people who aren't there, completely detached from reality",
]
_BREAKDOWN_HUNT_LINES = [
    "charges toward {target} with wild, unfocused rage — no strategy, just fury",
    "locks onto {target} with broken, desperate eyes — this isn't tactical anymore",
    "stumbles toward {target}, driven by something darker than strategy",
    "moves on {target} with the reckless abandon of someone who's lost everything",
]
_BREAKDOWN_ENCOUNTER_BOOST_LINES = [
    "{name} doesn't care about the odds anymore — they're beyond fear",
    "{name} throws caution to the wind — psychological breakdown makes them reckless",
    "The mental break has made {name} unpredictable and dangerous",
]

# ── Environmental event lines ─────────────────────────────────────────────────
_ENV_EVENT_LINES = {
    "fire": [
        "🔥 WILDFIRE ERUPTS! The {zone_name} is consumed by raging flames!",
        "🌋 VOLCANIC ACTIVITY! Lava flows through the {zone_name}!",
        "🔥 INFERNO! The {zone_name} becomes a blazing death trap!",
        "🌋 MAGMA SURGE! The ground splits open in the {zone_name}!",
    ],
    "water": [
        "🌊 FLASH FLOOD! Torrential waters surge through the {zone_name}!",
        "🌊 TSUNAMI WARNING! Massive waves crash into the {zone_name}!",
        "⛈️ STORM SURGE! The {zone_name} is swallowed by rushing water!",
        "🌊 TIDAL WAVE! The {zone_name} disappears under the flood!",
    ],
    "electric": [
        "⚡ LIGHTNING STORM! Electric death rains down on the {zone_name}!",
        "⚡ POWER SURGE! The {zone_name} crackles with deadly electricity!",
        "🌩️ THUNDERSTORM! Lightning strikes repeatedly in the {zone_name}!",
        "⚡ ELECTRIC FIELD! The air in the {zone_name} becomes charged with death!",
    ],
    "ice": [
        "❄️ BLIZZARD! The {zone_name} is buried under a deadly ice storm!",
        "🧊 FLASH FREEZE! The {zone_name} becomes a frozen wasteland!",
        "❄️ ICE AGE! Killing cold engulfs the {zone_name}!",
        "🌨️ ARCTIC BLAST! The {zone_name} is locked in deadly ice!",
    ],
    "plant": [
        "🌿 TOXIC BLOOM! Poisonous spores fill the air in the {zone_name}!",
        "🌱 CARNIVOROUS GROWTH! Killer vines overrun the {zone_name}!",
        "🍄 FUNGAL OUTBREAK! Deadly mushrooms sprout throughout the {zone_name}!",
        "🌿 NATURE'S WRATH! The {zone_name} turns against all living things!",
    ],
    "rock": [
        "🪨 EARTHQUAKE! The ground splits and crumbles in the {zone_name}!",
        "⛰️ ROCKSLIDE! Boulders rain down on the {zone_name}!",
        "🪨 STONE STORM! The {zone_name} is pelted with deadly debris!",
        "⛰️ AVALANCHE! The {zone_name} is buried under crushing stone!",
    ],
    "air": [
        "🌪️ TORNADO! A deadly twister tears through the {zone_name}!",
        "💨 HURRICANE! Killing winds ravage the {zone_name}!",
        "🌪️ CYCLONE! The {zone_name} is caught in a spiral of destruction!",
        "💨 WIND SHEAR! The {zone_name} is torn apart by violent gusts!",
    ],
    "magic": [
        "✨ ARCANE STORM! Wild magic tears reality apart in the {zone_name}!",
        "🔮 MANA SURGE! Unstable energy erupts throughout the {zone_name}!",
        "✨ SPELL CHAOS! The {zone_name} becomes a maelstrom of raw magic!",
        "🔮 REALITY BREAK! The laws of nature collapse in the {zone_name}!",
    ],
    "holy": [
        "☀️ DIVINE WRATH! Sacred fire purges the {zone_name}!",
        "⚡ JUDGMENT! Holy lightning strikes down in the {zone_name}!",
        "☀️ PURIFICATION! Blinding light scours the {zone_name}!",
        "⚡ CELESTIAL FURY! The heavens unleash their anger on the {zone_name}!",
    ],
    "necro": [
        "💀 DEATH WAVE! Necrotic energy sweeps through the {zone_name}!",
        "👻 SOUL STORM! The {zone_name} is haunted by vengeful spirits!",
        "💀 UNDEAD RISING! The ground in the {zone_name} vomits up the dead!",
        "👻 SHADOW PLAGUE! Darkness consumes all life in the {zone_name}!",
    ],
    "psychic": [
        "🧠 MIND STORM! Psychic energy shatters sanity in the {zone_name}!",
        "👁️ MENTAL BREAK! The {zone_name} becomes a nightmare of broken minds!",
        "🧠 TELEPATHIC CHAOS! Thoughts become weapons in the {zone_name}!",
        "👁️ PSYCHIC SCREAM! The {zone_name} echoes with mental anguish!",
    ],
    "fighting": [
        "👊 BATTLE FRENZY! The {zone_name} erupts in mindless violence!",
        "⚔️ WEAPON STORM! Blades and fists rain from the sky in the {zone_name}!",
        "👊 RAGE FIELD! Uncontrollable fury fills the {zone_name}!",
        "⚔️ COMBAT ZONE! The {zone_name} becomes a whirlwind of deadly combat!",
    ],
    "basic": [
        "🌪️ ARENA SHIFT! The Neutral Grounds are torn apart by unknown forces!",
        "⚡ GAMEMAKER INTERVENTION! The {zone_name} becomes a death trap!",
        "🔥 CHAOS ERUPTS! The {zone_name} is consumed by elemental fury!",
        "💀 ARENA HAZARD! The {zone_name} turns deadly without warning!",
    ],
}

_ENV_DAMAGE_LINES = [
    "{name} is caught in the environmental disaster and badly injured!",
    "{name} barely escapes the hazard but takes serious damage!",
    "{name} is wounded by the environmental chaos!",
    "{name} suffers injuries from the arena's deadly trap!",
]

_ENV_EVACUATION_LINES = [
    "{name} flees the disaster zone, forced to abandon their position!",
    "{name} evacuates immediately — staying would mean certain death!",
    "{name} is driven out by the environmental hazard!",
    "{name} retreats to safety as the zone becomes uninhabitable!",
]

_ENV_SURVIVOR_LINES = [
    "{name} weathers the environmental disaster and holds their ground!",
    "{name} endures the hazard through sheer determination!",
    "{name} survives the chaos and remains in position!",
    "{name} toughs it out despite the environmental threat!",
]

# ── Elimination openers ───────────────────────────────────────────────────────
_ELIM_OPENERS_1V1 = [
    "{W} corners {L} at {LOC}",
    "{W} catches {L} off guard at {LOC}",
    "{W} closes the gap on {L} at {LOC}",
    "{W} drives {L} into a dead end at {LOC}",
    "{W} strikes first at {LOC}, catching {L} flat-footed",
    "{W} hunts {L} down at {LOC}",
    "{W} and {L} clash at {LOC} — only one walks away",
    "{W} cuts off {L}'s escape route at {LOC}",
    "{W} finds {L} exposed at {LOC} and doesn't hesitate",
]

# ── Enhanced elimination openers ─────────────────────────────────────────────
_ELIM_OPENERS_ENHANCED = [
    "💀 The arena holds its breath as {W} and {L} face off at {LOC}",
    "⚔️ Destiny calls as {W} confronts {L} in the {LOC}",
    "🎯 The crowd roars as {W} closes in on {L} at {LOC}",
    "💥 The moment of truth arrives — {W} versus {L} at {LOC}",
    "🌪️ Chaos erupts as {W} engages {L} in deadly combat at {LOC}",
    "⚡ Lightning-fast, {W} strikes at {L} in the {LOC}",
    "🔥 The arena ignites with violence as {W} battles {L} at {LOC}",
    "🎭 The final act begins as {W} faces {L} at {LOC}",
]

# ── Crowd reaction lines ──────────────────────────────────────────────────────
_CROWD_REACTIONS = [
    "The crowd erupts in cheers!",
    "Spectators gasp in shock!",
    "The arena falls silent in awe!",
    "Wild applause echoes through the stands!",
    "The audience is on their feet!",
    "Stunned silence grips the crowd!",
    "Roars of approval shake the arena!",
]

# ── Victory celebration lines ─────────────────────────────────────────────────
_VICTORY_CELEBRATIONS = [
    "{W} raises their weapon in triumph!",
    "{W} stands victorious over their fallen opponent!",
    "{W} lets out a primal roar of victory!",
    "{W} surveys the arena with cold satisfaction!",
    "{W} doesn't even look back as they walk away!",
    "{W} pauses to catch their breath, victorious but weary!",
]
_ELIM_OPENERS_DOMINANT = [
    "{W} overwhelms {L} at {LOC} — the score gap was never close",
    "{W} dismantles {L} at {LOC} with clinical precision",
    "{W} makes short work of {L} at {LOC} — no contest",
    "{W} runs down {L} at {LOC} — the outcome was never in doubt",
]
_ELIM_OPENERS_UPSET = [
    "{W} shocks {L} at {LOC} in a stunning upset",
    "{W} pulls off the impossible at {LOC}, taking down {L}",
    "Against all odds, {W} defeats {L} at {LOC}",
    "{L} was the favourite at {LOC} — {W} didn't care",
]
_ELIM_OPENERS_ENEMY = [
    "{W} finally catches {L} at {LOC} — this grudge match was a long time coming",
    "The rivalry between {W} and {L} reaches its end at {LOC}",
    "{W} hunted {L} across the entire arena — it ends at {LOC}",
]
_ELIM_OPENERS_GROUP = [
    "{W} surround {L} at {LOC}",
    "{W} cut off {L}'s escape at {LOC}",
    "{W} coordinate a strike on {L} at {LOC}",
    "{W} overwhelm {L} at {LOC}",
    "{W} close in on {L} from multiple angles at {LOC}",
]

# ── Parry lines (loser is a defender type — they tried to block) ──────────────
_PARRY_FAIL = [
    "tries to parry with {defend_action} but the force breaks through",
    "raises {defend_action} — not enough to stop it",
    "attempts {defend_action} but is overwhelmed",
    "braces with {defend_action}, yet the blow lands clean",
    "scrambles into {defend_action} too late",
    "throws up {defend_action} but the strike punches right through",
    "reaches for {defend_action} — {winner} was already past it",
]
_PARRY_SUCCESS_THEN_BREAK = [
    "deflects the first blow with {defend_action} — but {winner} reads the recovery and strikes again",
    "holds firm with {defend_action}, absorbing the hit — {winner} shifts angle and breaks through on the follow-up",
    "executes {defend_action} cleanly, turning the first strike aside — {winner} doesn't let up and finds the gap",
    "uses {defend_action} to weather the opening — {winner} presses the advantage before {loser} can reset",
    "blocks with {defend_action} — a solid parry — but {winner} chains a second strike before {loser} can recover",
    "catches the attack on {defend_action} — {winner} feints, resets, and lands the decisive blow",
    "weathers the first exchange with {defend_action} — {winner} adjusts and finds the opening on the second",
]

# FIX #12: separate template for losers who are attackers (not defenders).
# These don't call an attack move a "parry".
_ATTACK_COUNTER_FAIL = [
    "fires back with {attack_action} — {winner} reads it and counters clean",
    "launches {attack_action} but {winner} sidesteps and answers with the decisive blow",
    "commits to {attack_action} — {winner} was waiting for exactly that opening",
    "swings {attack_action} wide — {winner} doesn't miss the gap",
    "pushes forward with {attack_action} but {winner} has already closed the angle",
    "throws {attack_action} with everything left — {winner} absorbs it and ends the fight",
    "goes for {attack_action} one last time — {winner} turns it aside and strikes back",
]

# ── Relationship closing lines ────────────────────────────────────────────────
_REL_ENEMY_CLOSE = [
    "Their long rivalry finally ends here.",
    "The grudge match is over — only one walks away.",
    "Old scores are settled at last.",
    "This was always going to happen. The arena just chose the time.",
]
_REL_BF_CLOSE = [
    "Even the closest bonds break in the arena.",
    "Best friends, but only one can win.",
    "The hardest fight of all — and neither will forget it.",
    "They both knew this moment might come. It didn't make it easier.",
]
_REL_FRIEND_CLOSE = [
    "Neither wanted this, but the arena demanded it.",
    "Friends until the end — almost.",
    "They tried to avoid each other. The arena had other plans.",
]
_REL_FOE_CLOSE = [
    "Rivals clash, and only one remains.",
    "The rivalry reaches its conclusion.",
    "They've been circling each other all game. Now it's settled.",
]

# ── Score-gap commentary ──────────────────────────────────────────────────────
_SCORE_DOMINANT_LINES = [
    "The score gap told the whole story.",
    "There was never any doubt — the numbers don't lie.",
    "{W} was simply in a different league.",
    "The gap in power was too wide to overcome.",
]
_SCORE_CLOSE_LINES = [
    "It was razor-thin — either could have won.",
    "The scores were nearly identical. A different day, a different result.",
    "This one could have gone either way.",
    "The closest fight of the round.",
]
_SCORE_UPSET_LINES = [
    "Nobody saw that coming.",
    "The underdog pulled through when it mattered most.",
    "{W} defied the odds completely.",
    "The arena had other plans — {L} was the favourite and still fell.",
]

# ── Kill-count flavour ────────────────────────────────────────────────────────
_WINNER_KILL_LINES = [
    "{W} adds another name to their list.",
    "Another elimination for {W} — they're not done yet.",
    "That's {kills} for {W}. The arena is running out of challengers.",
]
_LOSER_KILL_LINES = [
    "{L} fought well — {kills} elimination{s} before the end.",
    "Not a bad run for {L} — {kills} down before going out.",
]

# ── Type + element advantage lines ───────────────────────────────────────────
_TYPE_ADV_LINES: Dict[str, Dict[str, str]] = {
    "flying":   {"land":     "{W}'s aerial advantage leaves {L} with no answer from the ground"},
    "land":     {"swimming": "{W}'s ground dominance overwhelms {L}'s water-based footing"},
    "swimming": {"flying":   "{W}'s fluid movement grounds {L}'s aerial assault"},
}
_ELEM_ADV_LINES: Dict[str, str] = {
    "fire":     "{W}'s fire scorches through {L}'s defences",
    "water":    "{W}'s water overwhelms {L}'s footing",
    "electric": "{W}'s electricity short-circuits {L}'s guard",
    "ice":      "{W}'s ice locks {L} in place",
    "plant":    "{W}'s vines tighten around {L}",
    "rock":     "{W}'s stone-hard force crushes {L}'s stance",
    "air":      "{W}'s gust sweeps {L} off their feet",
    "magic":    "{W}'s arcane energy overwhelms {L}",
    "holy":     "{W}'s sacred light blinds {L}",
    "necro":    "{W}'s shadow energy drains {L}",
    "psychic":  "{W}'s mental pressure shatters {L}'s focus",
    "fighting": "{W}'s raw power batters through {L}'s guard",
    "basic":    "{W} outmanoeuvres {L} with superior technique",
}


def _score_gap_label(winner_score: float, loser_score: float) -> str:
    # FIX #5: threshold now matches elim_win_prob dominant amplifier (≥2.0)
    # so "dominant" narrative only fires when the odds were actually lopsided.
    if loser_score <= 0:
        return "dominant"
    ratio = winner_score / loser_score
    if ratio >= 2.0:
        return "dominant"
    if ratio <= 1.10:
        return "close"
    return "normal"


def _build_solo_action(
    uid: str,
    info: Dict,
    zone: str,
    alive: List[str],
    p_map: Dict,
    rel_map: Dict,
    scores: Dict,
    kill_counts: Dict,
    pct_alive: float,
    charge_stacks: int = 0,
    game: Dict = None,
    # FIX #7: pass the zone the pet is actually moving to so seek lines
    # only fire when the pet is genuinely heading toward their target.
    dest_zone: str = None,
) -> str:
    """
    Build a single-pet action line reflecting actual behaviour.
    Uses the Charge action name when the pet is building up power (charge_stacks > 0),
    otherwise uses their preferred action (attack or defend).
    dest_zone: the zone chosen by choose_zone for this pet this round.
    """
    name     = _pname(info)
    loc      = _location_for_zone(zone)

    # Action name: use Charge when building stacks, preferred otherwise
    if charge_stacks > 0:
        act_name = _pet_action_name(info, "charge")
    else:
        pref     = _preferred_action(info)
        act_name = _pet_action_name(info, pref)

    enemies = [u for u in alive if u != uid and is_enemy(rel_map, uid, u)]
    bfs     = [u for u in alive if u != uid and is_best_friend(rel_map, uid, u)]
    foes    = [u for u in alive if u != uid and is_foe(rel_map, uid, u)]
    friends = [u for u in alive if u != uid and is_friend(rel_map, uid, u)]

    my_score     = scores.get(uid, 1.0)
    all_scores   = [scores.get(u, 1.0) for u in alive if u != uid]
    median_score = sorted(all_scores)[len(all_scores) // 2] if all_scores else my_score
    stronger     = [u for u in alive if u != uid and scores.get(u, 1.0) > my_score * 1.15]
    is_dominant  = my_score > median_score * 1.5 and not stronger
    kills        = kill_counts.get(uid, 0)
    boldness     = min(0.75, kills * 0.15)
    is_late_game = pct_alive <= 0.25

    # Check for active deal partner
    deal_partner_uid = _deal_partner(game, uid, alive) if game is not None else None

    # Pull new state from game
    wounded_set    = set((game.get("_wounded") or {}).keys()) if game else set()
    rampage_map    = (game.get("_rampage") or {})             if game else {}
    last_stand_set = set(game.get("_last_stand") or [])       if game else set()
    zone_tenure    = (game.get("_zone_tenure") or {})         if game else {}
    is_wounded     = uid in wounded_set
    is_last_stand  = uid in last_stand_set
    is_broken_down = _is_broken_down(game, uid) if game else False
    zone_name_map  = {
        "fire":"Emberlands","water":"Tideways","electric":"Stormfields",
        "ice":"Frostreach","plant":"Verdant Wilds","rock":"Stone Marches",
        "air":"Skylands","magic":"Arcane Vale","holy":"Sanctified Plains",
        "necro":"Shadow Wastes","fighting":"Battlegrounds","psychic":"Mindscapes",
        "basic":"Neutral Grounds",
    }

    context = ""

    # FIX #8: charge narrative only fires when stacks > 0 AND the pet has
    # been in the game long enough to have deliberately avoided combat.
    current_round = (game.get("round_index", 0) if game else 0)
    charge_is_meaningful = charge_stacks > 0 and not (current_round <= 1 and charge_stacks == 1)

    # Wounded pets get injury narrative first
    if is_wounded:
        context = random.choice(_WOUNDED_SOLO_LINES)
    # Broken down pets get psychological breakdown narrative
    elif is_broken_down:
        # Check if they're hunting someone while broken down
        if enemies:
            enemy_zones = {p_map.get(e, {}).get("_cur_zone", "") for e in enemies}
            heading_toward_enemy = (
                dest_zone is None
                or dest_zone in enemy_zones
                or any(
                    dest_zone in ZONE_ADJACENCY.get(ez, [])
                    for ez in enemy_zones if ez
                )
            )
            if heading_toward_enemy:
                target = random.choice(enemies)
                target_name = _pname(p_map.get(target, {}))
                context = random.choice(_BREAKDOWN_HUNT_LINES).replace("{target}", target_name)
            else:
                context = random.choice(_BREAKDOWN_SOLO_LINES)
        else:
            context = random.choice(_BREAKDOWN_SOLO_LINES)
    # Last-stand pets get their own narrative
    elif is_last_stand:
        context = random.choice(_LAST_STAND_SOLO_LINES)
    # Rampage narrative
    elif kills >= _RAMPAGE_THRESHOLD:
        rampager_target = None
        if dest_zone:
            for other in alive:
                if other != uid and p_map.get(other, {}).get("_cur_zone") == dest_zone:
                    rampager_target = other
                    break
        if rampager_target:
            tname = _pname(p_map.get(rampager_target, {}))
            context = (random.choice(_RAMPAGE_HUNT_LINES)
                       .replace("{target}", tname)
                       .replace("{kills}", str(kills)))
        else:
            context = (random.choice(_RAMPAGE_SOLO_LINES)
                       .replace("{kills}", str(kills)))
    # Zone control narrative — pet has held this zone 2+ rounds
    elif zone_tenure.get(uid, {}).get("zone") == zone and zone_tenure.get(uid, {}).get("rounds", 0) >= 2:
        zone_display = zone_name_map.get(zone, zone.title())
        context = random.choice(_ZONE_HOLD_LINES).replace("{zone}", zone_display)
    elif charge_is_meaningful and charge_stacks >= 3:
        context = random.choice(_CHARGE_LINES_HIGH)
    elif charge_is_meaningful and charge_stacks > 0:
        context = random.choice(_CHARGE_LINES)
    elif enemies:
        # FIX #7: only use "hunting" seek lines when actually moving toward the enemy.
        enemy_zones = {p_map.get(e, {}).get("_cur_zone", "") for e in enemies}
        heading_toward_enemy = (
            dest_zone is None
            or dest_zone in enemy_zones
            or any(
                dest_zone in ZONE_ADJACENCY.get(ez, [])
                for ez in enemy_zones if ez
            )
        )
        if heading_toward_enemy:
            target = random.choice(enemies)
            target_name = _pname(p_map.get(target, {}))
            context = random.choice(_SEEK_ENEMY_LINES).replace("{target}", target_name)
        else:
            target = random.choice(enemies)
            target_name = _pname(p_map.get(target, {}))
            context = random.choice(_SEEK_LINES).replace("{target}", target_name)
    elif bfs and pct_alive > 0.10:
        bf_name = _pname(p_map.get(random.choice(bfs), {}))
        pool = _BF_ENDGAME_LINES if is_late_game else _BF_LINES
        context = random.choice(pool).replace("{bf}", bf_name)
    elif deal_partner_uid:
        partner_name = _pname(p_map.get(deal_partner_uid, {}))
        context = random.choice(_DEAL_ACTIVE_LINES).replace("{partner}", partner_name)
    elif is_dominant:
        # Check if hunting a rampager
        rampagers_nearby = [u for u in alive if u != uid
                            and kill_counts.get(u, 0) >= _RAMPAGE_THRESHOLD]
        if rampagers_nearby:
            rname = _pname(p_map.get(rampagers_nearby[0], {}))
            context = (random.choice(_HUNT_RAMPAGE_LINES)
                       .replace("{rampager}", rname)
                       .replace("{kills}", str(kill_counts.get(rampagers_nearby[0], 0))))
        else:
            context = random.choice(_HUNT_DOMINANT_LINES)
    elif stronger:
        # Check if fleeing a rampager specifically
        rampager_threats = [u for u in stronger if kill_counts.get(u, 0) >= _RAMPAGE_THRESHOLD]
        if rampager_threats and random.random() < max(0.10, 0.35 - boldness):
            rname = _pname(p_map.get(rampager_threats[0], {}))
            context = (random.choice(_FLEE_RAMPAGE_LINES)
                       .replace("{rampager}", rname)
                       .replace("{kills}", str(kill_counts.get(rampager_threats[0], 0))))
        elif random.random() < max(0.10, 0.35 - boldness):
            gap = max(scores.get(u, 1.0) for u in stronger) / max(my_score, 0.01)
            context = random.choice(_FLEE_DOMINANT_LINES if gap >= 2.0 else _FLEE_LINES)
        else:
            context = random.choice(_NEUTRAL_LINES)
    elif foes:
        foe_name = _pname(p_map.get(random.choice(foes), {}))
        context = random.choice(_FOE_LINES).replace("{foe}", foe_name)
    elif friends and pct_alive > 0.25:
        friend_name = _pname(p_map.get(random.choice(friends), {}))
        context = random.choice(_FRIEND_AVOID_LINES).replace("{friend}", friend_name)
    elif is_late_game:
        context = random.choice(_LATE_GAME_LINES)
    else:
        context = random.choice(_NEUTRAL_LINES)

    if not context:
        context = random.choice(_NEUTRAL_LINES)

    # Charge level suffix
    charge_suffix = ""
    if charge_is_meaningful and charge_stacks > 0:
        mult = charge_multiplier(charge_stacks)
        charge_suffix = f" [Charge ×{mult:.1f}]"

    base_line = f"📋 {name} uses {act_name} at {loc} — {context}.{charge_suffix}"
    
    # Add atmospheric enhancement (20% chance)
    if random.random() < 0.20:
        zone_atmo = _ZONE_ATMOSPHERE.get(zone, _ZONE_ATMOSPHERE["basic"])
        if zone_atmo:
            atmo_line = random.choice(zone_atmo).replace("{name}", name).replace("{action}", f"uses {act_name}")
            base_line = f"📋 {atmo_line}.{charge_suffix}"
    
    # Add kill streak flavor
    if kills >= 2 and random.random() < 0.40:
        base_line += " " + random.choice(_KILL_STREAK_LINES).replace("{kills}", str(kills))
    
    return base_line


def _build_elim_text(
    winners: List[str],
    losers: List[str],
    p_map: Dict,
    rel_map: Dict,
    zone: str,
    scores: Dict = None,
    kill_counts: Dict = None,
    win_prob: float = 0.5,
    winner_charge: int = 0,
    loser_charge: int = 0,
    loser_was_wounded: bool = False,
    winner_is_last_stand: bool = False,
    loser_is_last_stand: bool = False,
    winner_zone_tenure: int = 0,
    charge_stacks: Dict = None,
) -> str:
    """
    Full elimination narrative with correct action selection.
    Now also reflects wounded, last-stand, zone-control, and rampage states.
    """
    if scores is None:
        scores = {}
    if kill_counts is None:
        kill_counts = {}

    loc    = _location_for_zone(zone)
    w_info = p_map.get(winners[0], {})
    l_info = p_map.get(losers[0], {})
    wname  = _pname(w_info)
    lname  = _pname(l_info)

    # ── Correct action selection based on species stats ───────────────────────
    w_species = w_info.get("species", "")
    l_species = l_info.get("species", "")
    w_stats   = _PET_STATS.get(w_species, {})
    l_stats   = _PET_STATS.get(l_species, {})

    winner_is_defender = w_stats.get("DEF", 10) > w_stats.get("ATT", 10)
    loser_is_defender  = l_stats.get("DEF", 10) > l_stats.get("ATT", 10)

    # Winner: if they had a charge, they release it (charge action name); else preferred
    if winner_charge > 0:
        w_action = _pet_action_name(w_info, "charge")
    elif winner_is_defender:
        w_action = _pet_action_name(w_info, "defend")
    else:
        w_action = _pet_action_name(w_info, "attack")

    # Loser: defenders use defend (parry attempt), attackers use attack
    if loser_is_defender:
        l_action = _pet_action_name(l_info, "defend")
    else:
        l_action = _pet_action_name(l_info, "attack")

    w_score   = scores.get(winners[0], survive_score(w_info))
    l_score   = scores.get(losers[0],  survive_score(l_info))
    gap_label = _score_gap_label(w_score, l_score)

    # ── Parry flavour ─────────────────────────────────────────────────────────
    if loser_is_defender:
        parry_line = (
            random.choice(_PARRY_SUCCESS_THEN_BREAK)
            .replace("{defend_action}", l_action)
            .replace("{winner}", wname)
            .replace("{loser}", lname)
        )
    else:
        # FIX #12: loser was attacking, not defending — use attack-counter templates
        # that don't call their attack move a "parry".
        parry_line = (
            random.choice(_ATTACK_COUNTER_FAIL)
            .replace("{attack_action}", l_action)
            .replace("{winner}", wname)
        )

    # ── Charge release flavour ────────────────────────────────────────────────
    charge_line = ""
    if winner_charge > 0:
        mult = charge_multiplier(winner_charge)
        charge_line = f" {wname} releases {winner_charge} round{'s' if winner_charge != 1 else ''} of stored power (×{mult:.1f})."

    # ── Opener ────────────────────────────────────────────────────────────────
    is_1v1 = len(winners) == 1 and len(losers) == 1
    if is_1v1:
        a0, b0 = winners[0], losers[0]
        if is_enemy(rel_map, a0, b0):
            pool = _ELIM_OPENERS_ENEMY
        elif loser_was_wounded:
            pool = _WOUNDED_ELIM_OPENER
        elif winner_is_last_stand:
            pool = _LAST_STAND_ELIM_UPSET
        elif gap_label == "dominant":
            pool = _ELIM_OPENERS_DOMINANT
        elif gap_label == "close" and win_prob < 0.45:
            pool = _ELIM_OPENERS_UPSET
        else:
            pool = _ELIM_OPENERS_1V1
        opener = (
            random.choice(pool)
            .replace("{W}", wname).replace("{L}", lname).replace("{LOC}", loc)
        )
    else:
        w_str = _fmt_names([_pname(p_map.get(u, {})) for u in winners])
        l_str = _fmt_names([_pname(p_map.get(u, {})) for u in losers])
        opener = (
            random.choice(_ELIM_OPENERS_GROUP)
            .replace("{W}", w_str).replace("{L}", l_str).replace("{LOC}", loc)
        )

    # ── Element advantage — check primary AND element2 of winner ─────────────
    # FIX #6: was only checking winner's primary element; now checks element2 too.
    w_elem   = (w_info.get("element")  or "basic").lower()
    w_elem2  = (w_info.get("element2") or "").lower()
    l_elem   = (l_info.get("element")  or "basic").lower()
    adv_line = ""
    # Primary element advantage
    if l_elem in ELEM_STRONG.get(w_elem, []):
        tmpl = _ELEM_ADV_LINES.get(w_elem, "")
        if tmpl:
            adv_line = " " + tmpl.replace("{W}", wname).replace("{L}", lname) + "."
    # Secondary element advantage (only if primary didn't already fire)
    elif w_elem2 and l_elem in ELEM_STRONG.get(w_elem2, []):
        tmpl = _ELEM_ADV_LINES.get(w_elem2, "")
        if tmpl:
            adv_line = " " + tmpl.replace("{W}", wname).replace("{L}", lname) + "."

    # ── Type advantage ────────────────────────────────────────────────────────
    w_cat     = _norm_cat(w_info.get("category", "land"))
    l_cat     = _norm_cat(l_info.get("category", "land"))
    type_line = ""
    if _TYPE_STRONG.get(w_cat) == l_cat:
        tmpl = (_TYPE_ADV_LINES.get(w_cat) or {}).get(l_cat, "")
        if tmpl:
            type_line = " " + tmpl.replace("{W}", wname).replace("{L}", lname) + "."

    # ── Relationship close ────────────────────────────────────────────────────
    rel_close = ""
    if is_1v1:
        a0, b0 = winners[0], losers[0]
        if is_enemy(rel_map, a0, b0):
            rel_close = " " + random.choice(_REL_ENEMY_CLOSE)
        elif is_best_friend(rel_map, a0, b0):
            rel_close = " " + random.choice(_REL_BF_CLOSE)
        elif is_friend(rel_map, a0, b0):
            rel_close = " " + random.choice(_REL_FRIEND_CLOSE)
        elif is_foe(rel_map, a0, b0):
            rel_close = " " + random.choice(_REL_FOE_CLOSE)

    # ── Score-gap commentary ──────────────────────────────────────────────────
    score_comment = ""
    if gap_label == "dominant":
        score_comment = " " + random.choice(_SCORE_DOMINANT_LINES).replace("{W}", wname).replace("{L}", lname)
    elif gap_label == "close" and win_prob >= 0.45:
        score_comment = " " + random.choice(_SCORE_CLOSE_LINES).replace("{W}", wname).replace("{L}", lname)
    elif gap_label == "close" and win_prob < 0.45:
        score_comment = " " + random.choice(_SCORE_UPSET_LINES).replace("{W}", wname).replace("{L}", lname)

    # ── Kill-count flavour ────────────────────────────────────────────────────
    w_kills   = kill_counts.get(winners[0], 0)
    l_kills   = kill_counts.get(losers[0], 0)
    kill_line = ""
    if w_kills >= 2 and random.random() < 0.50:
        kill_line += " " + (
            random.choice(_WINNER_KILL_LINES)
            .replace("{W}", wname)
            .replace("{kills}", str(w_kills + 1))
        )
    if l_kills >= 1 and random.random() < 0.50:
        s = "s" if l_kills != 1 else ""
        kill_line += " " + (
            random.choice(_LOSER_KILL_LINES)
            .replace("{L}", lname)
            .replace("{kills}", str(l_kills))
            .replace("{s}", s)
        )

    loser_names  = _fmt_names([_pname(p_map.get(u, {})) for u in losers])
    winner_names = _fmt_names([_pname(p_map.get(u, {})) for u in winners])
    were = "were" if len(losers) > 1 else "was"

    # FIX #13: group fights get a proper multi-combatant narrative instead of
    # reading like a 1v1 with a footnote. Build a combined action line for
    # all winners when it's a group fight.
    if not is_1v1:
        all_w_actions = []
        for wu in winners:
            wi2 = p_map.get(wu, {})
            wc2 = (charge_stacks or {}).get(wu, 0)
            if wc2 > 0:
                all_w_actions.append(f"{_pname(wi2)} ({_pet_action_name(wi2, 'charge')})")
            else:
                pref2 = _preferred_action(wi2)
                all_w_actions.append(f"{_pname(wi2)} ({_pet_action_name(wi2, pref2)})")
        combined_attack = " and ".join(all_w_actions) if len(all_w_actions) <= 2 else (
            ", ".join(all_w_actions[:-1]) + ", and " + all_w_actions[-1]
        )
        combat_line = f"{combined_attack} — {lname} {parry_line}."
    else:
        combat_line = f"{wname} strikes with {w_action} — {lname} {parry_line}."

    # Zone control suffix
    zone_name_map = {
        "fire":"Emberlands","water":"Tideways","electric":"Stormfields",
        "ice":"Frostreach","plant":"Verdant Wilds","rock":"Stone Marches",
        "air":"Skylands","magic":"Arcane Vale","holy":"Sanctified Plains",
        "necro":"Shadow Wastes","fighting":"Battlegrounds","psychic":"Mindscapes",
        "basic":"Neutral Grounds",
    }
    zone_suffix = ""
    if winner_zone_tenure >= 2:
        zname = zone_name_map.get(zone, zone.title())
        zone_suffix = f" {wname} defends their hold on {zname}."

    # Rampage suffix
    w_kills_now = (kill_counts or {}).get(winners[0], 0) + 1  # +1 for this kill
    rampage_suffix = ""
    if w_kills_now >= _RAMPAGE_THRESHOLD and random.random() < 0.60:
        rampage_suffix = f" 🔥 {wname} is on a rampage — {w_kills_now} eliminations!"
    
    # Crowd reaction (30% chance for dramatic moments)
    crowd_reaction = ""
    if (gap_label == "upset" or winner_is_last_stand or w_kills_now >= _RAMPAGE_THRESHOLD) and random.random() < 0.30:
        crowd_reaction = " " + random.choice(_CROWD_REACTIONS)
    
    # Victory celebration (25% chance)
    victory_celebration = ""
    if random.random() < 0.25:
        victory_celebration = " " + random.choice(_VICTORY_CELEBRATIONS).replace("{W}", wname)

    return (
        f"⚔️ {opener}.{charge_line} "
        f"{combat_line}"
        f"{adv_line}{type_line}{rel_close}{score_comment}{kill_line}"
        f"{zone_suffix}{rampage_suffix}{crowd_reaction}{victory_celebration} "
        f"💀 {loser_names} {were} eliminated by {winner_names}."
    )


# ---------------------------------------------------------------------------
# Zone choice (SS Brain movement)
# ---------------------------------------------------------------------------

def choose_zone(
    uid: str,
    alive: List[str],
    p_map: Dict,
    rel_map: Dict,
    cur_positions: Dict[str, str],
    scores: Dict[str, float],
    kill_counts: Dict[str, int],
    pct_alive: float,
    game: Dict = None,
    stale_rounds: int = 0,
) -> str:
    """
    Decide which zone this pet moves to this round.

    Movement is terrain-aware:
    - Pets strongly prefer their element's home zone and adjacent zones.
    - Pets with element advantages in a zone are drawn toward it.
    - basic is a neutral transit hub — all pets tolerate it, but none
      prefer it exclusively. Pets pass through it to reach their targets.
    - Under arena pressure, pets are funneled into fewer zones.

    Priority:
      1. Enemies      → chase into their zone (step via adjacency)
      2. Best Friends → stay in same zone while field > 10%
      3. Dominant pets hunt → move toward weakest stranger's zone
      4. Flee         → move away from stronger threats (pressure reduces flee)
      5. Deal partner → move toward deal partner's zone
      6. Advantage hunting → move toward a zone where this pet has advantages
      7. Foes         → roam preferred zones freely (not basic)
      8. Friends      → avoid their zones while field > 25%
      9. Arena pressure → forced into shrinking hot-zone pool
     10. Default      → element-preferred zones (never basic-only)
    """
    info      = p_map.get(uid, {})
    elem      = (info.get("element") or "basic").lower()
    my_zone   = cur_positions.get(uid, "basic")
    my_score  = scores.get(uid, 1.0)
    kills     = kill_counts.get(uid, 0)
    boldness  = min(0.75, kills * 0.15)
    preferred = list(dict.fromkeys(_ELEM_PREFERRED.get(elem) or ["basic"]))
    if not preferred:
        preferred = ["basic"]
    adv_zones = _ELEM_ADVANTAGE_ZONES.get(elem, [])
    adjacent  = ZONE_ADJACENCY.get(my_zone, ALL_ZONES)

    all_scores   = [scores.get(u, 1.0) for u in alive if u != uid]
    median_score = sorted(all_scores)[len(all_scores) // 2] if all_scores else my_score
    is_dominant  = my_score > median_score * 1.5

    # Pull new state dicts from game (safe defaults if not yet initialised)
    wounded_set    = set(game.get("_wounded", {}).keys())    if game else set()
    rampage_map    = game.get("_rampage", {})                if game else {}
    last_stand_set = set(game.get("_last_stand", []))        if game else set()
    zone_tenure    = game.get("_zone_tenure", {})            if game else {}

    is_wounded    = uid in wounded_set
    is_rampage    = kills >= _RAMPAGE_THRESHOLD
    is_last_stand = uid in last_stand_set

    def _zone_of(other: str) -> str:
        oz = cur_positions.get(other)
        if oz:
            return oz
        adj_preferred = [z for z in preferred if z in adjacent]
        return random.choice(adj_preferred if adj_preferred else preferred)

    def _step_toward(target_zone: str) -> str:
        """Move one step toward target_zone using adjacency."""
        if target_zone == my_zone or target_zone in adjacent:
            return target_zone
        # Route through basic (central hub) if it bridges the gap
        if "basic" in adjacent and target_zone in ZONE_ADJACENCY.get("basic", []):
            return "basic"
        # Pick any adjacent zone that neighbours the target
        target_adj = set(ZONE_ADJACENCY.get(target_zone, []))
        bridge = [z for z in adjacent if z in target_adj]
        if bridge:
            return random.choice(bridge)
        return target_zone

    # 0. WOUNDED — injured pets flee first, before any other logic.
    # They need to survive this round; fighting is secondary.
    if is_wounded:
        safe_zones = sorted(ALL_ZONES, key=lambda z: sum(
            1 for o in alive if o != uid and cur_positions.get(o) == z
        ))
        safe_half = safe_zones[:max(1, len(safe_zones) // 2)]
        preferred_safe = [z for z in safe_half if z in preferred and z != "basic"]
        if not preferred_safe:
            preferred_safe = [z for z in safe_half if z in preferred]
        return random.choice(preferred_safe if preferred_safe else safe_half)

    # 1. Chase enemies — step toward their zone
    enemies = [u for u in alive if u != uid and is_enemy(rel_map, uid, u)]
    if enemies:
        return _step_toward(_zone_of(random.choice(enemies)))

    # 2. Stay near best friends (while field > 10%)
    bfs = [u for u in alive if u != uid and is_best_friend(rel_map, uid, u)]
    if bfs and pct_alive > 0.10:
        return _step_toward(_zone_of(random.choice(bfs)))

    # 3. Dominant pets hunt — weakest stranger first, then anyone.
    # Also: strong pets hunt rampagers to stop their streak.
    if is_dominant:
        # If there's a rampager, strong pets prioritise stopping them
        rampagers = [u for u in alive if u != uid
                     and kill_counts.get(u, 0) >= _RAMPAGE_THRESHOLD
                     and scores.get(u, 1.0) <= my_score * 1.5]
        if rampagers:
            target = max(rampagers, key=lambda u: kill_counts.get(u, 0))
            return _step_toward(_zone_of(target))
        strangers = [
            u for u in alive if u != uid
            and not is_enemy(rel_map, uid, u)
            and not is_best_friend(rel_map, uid, u)
            and not is_friend(rel_map, uid, u)
            and (game is None or not has_deal(game, uid, u))
        ]
        if strangers:
            weakest = min(strangers, key=lambda u: scores.get(u, 1.0))
            return _step_toward(_zone_of(weakest))
        remaining_targets = [u for u in alive if u != uid]
        if remaining_targets:
            weakest = min(remaining_targets, key=lambda u: scores.get(u, 1.0))
            return _step_toward(_zone_of(weakest))

    # 4. Score-based flee from stronger strangers.
    # Also: weaker pets flee rampagers more aggressively.
    flee_reduction = min(0.40, stale_rounds * 0.08) if stale_rounds >= _PRESSURE_START_ROUND else 0.0
    zone_threat: Dict[str, float] = {}
    for other in alive:
        if other == uid:
            continue
        r = _effective_rel(game, rel_map, uid, other) if game is not None else _either_rel(rel_map, uid, other)
        if r in ("enemy", "foe"):
            continue
        if r == "friend" and pct_alive > 0.15:
            continue
        other_score = scores.get(other, 1.0)
        if other_score <= my_score * 1.30:
            continue
        threat = (other_score - my_score) / max(my_score, 0.01)
        # Rampagers are extra threatening — weaker pets flee them harder
        if kill_counts.get(other, 0) >= _RAMPAGE_THRESHOLD and other_score > my_score:
            threat *= 1.5
        oz = cur_positions.get(other, "basic")
        zone_threat[oz] = zone_threat.get(oz, 0.0) + threat

    flee_prob = max(0.0, 0.35 - boldness - flee_reduction) if not is_dominant else 0.0
    # Last-stand pets never flee — they have nothing to lose
    if is_last_stand:
        flee_prob = 0.0
    # Broken down pets are reckless — reduced flee chance
    if is_broken_down:
        flee_prob = max(0.0, flee_prob - _BREAKDOWN_FLEE_REDUCE)
    if zone_threat and random.random() < flee_prob:
        safe_zones = sorted(ALL_ZONES, key=lambda z: zone_threat.get(z, 0.0))
        safe_half  = safe_zones[: max(1, len(safe_zones) // 2)]
        preferred_safe = [z for z in safe_half if z in preferred and z != "basic"]
        if not preferred_safe:
            preferred_safe = [z for z in safe_half if z in preferred]
        return random.choice(preferred_safe if preferred_safe else safe_half)

    # 4b. Last-stand pets hunt the weakest target — they need a kill to survive.
    if is_last_stand:
        targets = [u for u in alive if u != uid]
        if targets:
            weakest = min(targets, key=lambda u: scores.get(u, 1.0))
            return _step_toward(_zone_of(weakest))

    # 5. Move toward deal partner's zone
    if game is not None:
        deal_partner_uid = _deal_partner(game, uid, alive)
        if deal_partner_uid:
            return _step_toward(_zone_of(deal_partner_uid))

    # 6. Advantage hunting — move toward a zone where this element has advantages.
    # More aggressive when field is large (lots of targets in those zones).
    if adv_zones:
        adv_hunt_chance = 0.55 if pct_alive > 0.50 else 0.45
        if random.random() < adv_hunt_chance:
            adj_adv = [z for z in adv_zones if z in adjacent]
            if adj_adv:
                return random.choice(adj_adv)
            if adv_zones:
                return _step_toward(random.choice(adv_zones))

    # 7. Foes — actively circle toward each other's zone (95% encounter when they
    # meet, so moving toward them is correct behaviour — they want that fight).
    # FIX #15: was picking a random preferred zone, ignoring foe positions entirely.
    foes = [u for u in alive if u != uid and is_foe(rel_map, uid, u)]
    if foes:
        # 65% chance to move toward a foe's zone, 35% to roam preferred zones
        if random.random() < 0.65:
            return _step_toward(_zone_of(random.choice(foes)))
        non_basic_preferred = [z for z in preferred if z != "basic"]
        return random.choice(non_basic_preferred if non_basic_preferred else preferred)

    # 8. Friends — avoid their zones while field > 25%
    friends = [u for u in alive if u != uid and is_friend(rel_map, uid, u)]
    if friends and pct_alive > 0.25:
        friend_zones = {cur_positions.get(f, "basic") for f in friends}
        non_friend = [z for z in ALL_ZONES if z not in friend_zones and z != "basic"]
        pool = [z for z in preferred if z in non_friend] or non_friend or ALL_ZONES
        return random.choice(pool)

    # 9. Arena pressure — force into shrinking hot-zone pool
    if stale_rounds >= _PRESSURE_START_ROUND:
        n_zones = _pressure_zone_count(stale_rounds)
        zone_pop: Dict[str, int] = {}
        for other in alive:
            if other != uid:
                z = cur_positions.get(other, "basic")
                zone_pop[z] = zone_pop.get(z, 0) + 1
        hot_zones = sorted(ALL_ZONES, key=lambda z: zone_pop.get(z, 0), reverse=True)[:n_zones]
        hot_preferred = [z for z in hot_zones if z in preferred and z != "basic"]
        if not hot_preferred:
            hot_preferred = [z for z in hot_zones if z != "basic"]
        pool = hot_preferred if hot_preferred else hot_zones
        return random.choice(pool)

    # 10. Default — element-preferred zones, weighted toward top preference.
    # Exclude basic unless the pet's element IS basic, to prevent center clustering.
    if elem != "basic":
        non_basic = [z for z in preferred if z != "basic"]
        if non_basic:
            weights = [max(1, len(non_basic) - i) for i in range(len(non_basic))]
            return random.choices(non_basic, weights=weights, k=1)[0]

    weights = [max(1, len(preferred) - i) for i in range(len(preferred))]
    chosen_zone = random.choices(preferred, weights=weights, k=1)[0]
    
    # Environmental evacuation override — forced movement due to disasters
    return _handle_environmental_evacuation(game, uid, chosen_zone)


# ---------------------------------------------------------------------------
# Encounter pairing rules
# ---------------------------------------------------------------------------

def _allowed_group_size(uid_a: str, uid_b: str, rel_map: Dict) -> int:
    """
    Max group size for an encounter between uid_a and uid_b.
    Strangers/enemies/foes: 1v1 only.
    Friends: up to 2 per side.
    Best Friends: up to 4 per side.
    """
    if is_best_friend(rel_map, uid_a, uid_b):
        return 4
    if is_friend(rel_map, uid_a, uid_b):
        return 2
    return 1


def _can_form_group(uids: List[str], rel_map: Dict, max_size: int) -> bool:
    """All pairs in uids must share the same relationship tier."""
    if len(uids) <= 1:
        return True
    for i in range(len(uids)):
        for j in range(i + 1, len(uids)):
            if not (is_best_friend(rel_map, uids[i], uids[j]) or
                    is_friend(rel_map, uids[i], uids[j])):
                return False
    return True


def _build_encounter(
    available: List[str],
    rel_map: Dict,
    game: Dict = None,
) -> Optional[Tuple[List[str], List[str]]]:
    """
    Try to form a valid encounter from available pets.
    Returns (side_a, side_b) or None if no valid pairing found.

    Rules:
      - 1v1 always valid.
      - 2v1 or 2v2 only if both pets on the larger side are Friends, BFs, or deal partners.
      - 3v1 / 3v2 / 4-way only if all on each side are BFs.
      - Deal partners are placed on the same side (they fight together).
    """
    if len(available) < 2:
        return None

    def _allied(uid_a: str, uid_b: str) -> bool:
        """True if two pets should fight on the same side."""
        if is_best_friend(rel_map, uid_a, uid_b):
            return True
        if is_friend(rel_map, uid_a, uid_b):
            return True
        if game is not None and has_deal(game, uid_a, uid_b):
            return True
        return False

    a0, b0 = available[0], available[1]
    max_g = _allowed_group_size(a0, b0, rel_map)

    if max_g == 1 or len(available) == 2:
        return ([a0], [b0])

    # FIX #3: build side_a first, then side_b from pets NOT already on side_a.
    # The old code used available[1:] for both passes, so b0 could end up on
    # both sides when a0 and b0 are allied.
    side_a = [a0]
    for u in available[1:]:
        if len(side_a) >= max_g:
            break
        if all(_allied(u, s) for s in side_a):
            side_a.append(u)

    # Side B: only from pets not already claimed by side_a
    side_b_pool = [u for u in available if u not in side_a]
    if not side_b_pool:
        return ([a0], [b0])

    side_b = [side_b_pool[0]]
    for u in side_b_pool[1:]:
        if len(side_b) >= max_g:
            break
        if all(_allied(u, s) for s in side_b):
            side_b.append(u)

    # Final safety: no overlap
    if set(side_a) & set(side_b):
        return ([a0], [b0])

    return (side_a, side_b)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def process_round(game: Dict[str, Any]) -> Dict[str, Any]:
    """
    Full round processor. Called by ss_api._process_round_logic().
    Mutates game["alive_ids"] and game["eliminated"] in place.
    Returns the round result dict.
    """
    alive = list(dict.fromkeys(game["alive_ids"]))

    if "_total_start" not in game:
        game["_total_start"] = len(alive)
    total_start = game["_total_start"]

    if len(alive) <= 1:
        return {"actions": [], "eliminations": [], "newly_eliminated": [],
                "game_over": True, "pet_locations": {}}

    p_map     = {p["user_id"]: p for p in game["participants"]}
    pct_alive = len(alive) / max(1, total_start)
    rel_map: Dict[str, Dict[str, str]] = game.setdefault("_rel_map", {})

    # Cache p_map for use in deal expiry narratives
    game["_p_map_cache"] = p_map

    # ── Stale-round tracking (rounds with no eliminations) ────────────────────
    stale_rounds: int = game.setdefault("_stale_rounds", 0)
    current_round: int = game.get("round_index", 0)

    # Kill counts → boldness (built from history; updated mid-round below)
    kill_counts: Dict[str, int] = {}
    for e in game.get("eliminated", []):
        for kuid in (e.get("eliminated_by_uids") or []):
            kill_counts[kuid] = kill_counts.get(kuid, 0) + 1

    # Survive scores (movement perception only)
    scores: Dict[str, float] = {uid: survive_score(p_map.get(uid, {})) for uid in alive}

    # ── Charge stacks — incremented each round a pet doesn't fight, reset on combat ──
    charge_stacks: Dict[str, int] = game.setdefault("_charge_stacks", {})
    for uid in alive:
        if uid not in charge_stacks:
            charge_stacks[uid] = 0

    # ── New feature state ─────────────────────────────────────────────────────
    # _wounded:     uid → rounds_remaining (1 = wounded this round only)
    # _zone_tenure: uid → {"zone": str, "rounds": int}
    # _rampage:     uid → kill_streak (mirrors kill_counts but tracked separately)
    # _last_stand:  set of uids currently in bottom 10% of scores
    wounded_map:  Dict[str, int] = game.setdefault("_wounded", {})
    zone_tenure:  Dict[str, Any] = game.setdefault("_zone_tenure", {})

    # Tick down wounded state — remove pets whose wound has healed
    healed = [uid for uid, rounds in wounded_map.items() if rounds <= 0]
    for uid in healed:
        del wounded_map[uid]
    for uid in list(wounded_map):
        wounded_map[uid] -= 1

    # Compute last-stand set: bottom 10% of alive scores (min 1 pet)
    sorted_scores = sorted(alive, key=lambda u: scores.get(u, 1.0))
    last_stand_count = max(1, int(len(alive) * 0.10))
    last_stand_set: set = set(sorted_scores[:last_stand_count])
    game["_last_stand"] = list(last_stand_set)

    wounded_set = set(wounded_map.keys())

    # ── Track group-elimination history for guaranteed BF shared victory ─────
    bf_group_elims_raw: List[List[str]] = game.setdefault("_bf_group_elims", [])
    bf_group_elims: List[frozenset] = [frozenset(g) for g in bf_group_elims_raw]

    # ── Expire old deals ──────────────────────────────────────────────────────
    deal_expire_narratives, betrayal_pairs = _expire_deals(game, current_round, alive)

    # ── Form new deals if stale ───────────────────────────────────────────────
    deal_form_narratives: List[str] = []
    if stale_rounds >= _DEAL_ROUND_THRESHOLD and len(alive) > 2:
        deal_form_narratives = _form_deals(
            game, alive, p_map, rel_map, scores, stale_rounds, current_round
        )
        # FIX #11: tag deals formed THIS round so encounter logic treats them as
        # strangers this round — the deal takes effect from next round onward.
        deals = _get_deals(game)
        for key, info in deals.items():
            if info.get("formed_round") == current_round:
                info["_new_this_round"] = True

    # ── Environmental events ──────────────────────────────────────────────────
    environmental_narratives = _trigger_environmental_event(game, current_round, alive, p_map)
    
    # ── Expire psychological breakdowns ───────────────────────────────────────
    breakdown_recovery_narratives = _expire_breakdowns(game, current_round)

    # ── Best-Friend shared victory check ─────────────────────────────────────
    if 2 <= len(alive) <= 4:
        all_bf = all(
            is_best_friend(rel_map, alive[i], alive[j])
            for i in range(len(alive))
            for j in range(i + 1, len(alive))
        )
        if all_bf:
            # FIX #10: if one BF has significantly more kills than the others,
            # they've earned a solo win — shared victory only makes sense when
            # the BFs contributed roughly equally.
            bf_kills = {u: kill_counts.get(u, 0) for u in alive}
            max_kills = max(bf_kills.values()) if bf_kills else 0
            min_kills = min(bf_kills.values()) if bf_kills else 0
            kill_gap_too_large = (max_kills - min_kills) >= 3 and max_kills >= 3
            if not kill_gap_too_large:
                alive_set = frozenset(alive)
                had_group_elim = any(alive_set <= g for g in bf_group_elims)
                shared_chance = 1.0 if had_group_elim else {2: 0.60, 3: 0.40, 4: 0.25}.get(len(alive), 0.20)
                if random.random() < shared_chance:
                    names = [_pname(p_map.get(u, {})) for u in alive]
                    names_str = _fmt_names(names)
                    text = (
                        f"🤝 {names_str} — the last Best Friends standing — look at each other "
                        f"and lower their guard. They accept shared victory together. "
                        f"🏆 All {len(alive)} champions!"
                    )
                    return {
                        "actions":          [text],
                        "eliminations":     [],
                        "newly_eliminated": [],
                        "game_over":        True,
                        "shared_victory":   list(alive),
                        "pet_locations":    {u: "final_duel" for u in alive},
                    }

    # ── Final duel (2 remain, no shared victory triggered) ───────────────────
    if len(alive) == 2:
        uid_a, uid_b = alive[0], alive[1]
        win_p   = elim_win_prob(uid_a, uid_b, p_map,
                                charge_a=charge_stacks.get(uid_a, 0),
                                charge_b=charge_stacks.get(uid_b, 0),
                                wounded_a=(uid_a in wounded_set) or _is_environmentally_damaged(game, uid_a),
                                wounded_b=(uid_b in wounded_set) or _is_environmentally_damaged(game, uid_b),
                                last_stand_a=(uid_a in last_stand_set),
                                last_stand_b=(uid_b in last_stand_set),
                                fight_zone="basic",
                                zone_tenure_map=zone_tenure)
        a_wins  = random.random() < win_p
        winner_id, loser_id = (uid_a, uid_b) if a_wins else (uid_b, uid_a)
        wi = p_map.get(winner_id, {})
        li = p_map.get(loser_id, {})
        wname = _pname(wi)
        lname = _pname(li)

        elim_text = _build_elim_text(
            [winner_id], [loser_id], p_map, rel_map, "basic",
            scores=scores, kill_counts=kill_counts,
            win_prob=win_p if a_wins else 1.0 - win_p,
            winner_charge=charge_stacks.get(winner_id, 0),
            loser_charge=charge_stacks.get(loser_id, 0),
        )
        elim_text = elim_text.replace("⚔️", "⚔️ Final duel!", 1)

        charge_stacks[winner_id] = 0
        charge_stacks[loser_id]  = 0

        if loser_id in game["alive_ids"]:
            game["alive_ids"].remove(loser_id)
        game["eliminated"].append({
            "user_id":            loser_id,
            "username":           li.get("username", loser_id),
            "pet_name":           lname,
            "species":            li.get("species", "Cat"),
            "round":              game.get("round_index", 0),
            "text":               elim_text,
            "is_npc":             li.get("is_npc", False),
            "eliminated_by":      wname,
            "eliminated_by_uid":  winner_id,
            "eliminated_by_uids": [winner_id],
        })
        return {
            "actions":          [],
            "eliminations":     [elim_text],
            "newly_eliminated": [loser_id],
            "game_over":        True,
            "pet_locations":    {uid_a: "final_duel", uid_b: "final_duel"},
        }

    # ── ROUND 1 CHAOS — Opening Bloodbath ────────────────────────────────────
    # All pets start in the basic zone. Round 1 is pure chaos: 10–50% of the
    # field is eliminated as everyone collides in the neutral grounds.
    # All factors (scores, elements, relationships, charge) are fully applied —
    # we just guarantee a high encounter rate and a large elimination count.
    if current_round == 1 and not game.get("_opening_chaos_done"):
        game["_opening_chaos_done"] = True

        # Target: eliminate 10–50% of the field, weighted toward the lower end
        # so the result feels dramatic but not instantly game-ending.
        target_elim_frac = random.uniform(0.10, 0.50)
        target_elim_count = max(1, int(round(len(alive) * target_elim_frac)))

        _OPENING_LINES = [
            "⚔️ The gates open — every pet charges into the Neutral Grounds at once!",
            "💥 The starting horn sounds and the arena erupts into immediate chaos!",
            "🔥 No time to breathe — the opening clash begins in the Neutral Grounds!",
            "⚡ The crowd roars as all contestants collide in the center of the arena!",
            "🌪️ Pandemonium! Every pet scrambles for position in the opening frenzy!",
            "💀 The Neutral Grounds run red — the opening bloodbath has begun!",
            "🏟️ The arena shakes as the full field crashes together in Round 1!",
        ]

        chaos_actions: List[str] = [random.choice(_OPENING_LINES)]
        chaos_elims:   List[str] = []
        chaos_newly:   List[str] = []
        chaos_locs:    Dict[str, str] = {uid: "basic" for uid in alive}
        chaos_used:    set = set()

        # Shuffle and pair up pets for combat — keep going until we hit the target
        shuffled = list(alive)
        random.shuffle(shuffled)

        for i in range(0, len(shuffled) - 1, 2):
            if len(chaos_newly) >= target_elim_count:
                break
            uid_a = shuffled[i]
            uid_b = shuffled[i + 1]
            if uid_a in chaos_used or uid_b in chaos_used:
                continue
            if uid_a not in game["alive_ids"] or uid_b not in game["alive_ids"]:
                continue

            # Fully-weighted combat resolution
            win_p  = elim_win_prob(uid_a, uid_b, p_map,
                                   charge_a=charge_stacks.get(uid_a, 0),
                                   charge_b=charge_stacks.get(uid_b, 0),
                                   wounded_a=(uid_a in wounded_set) or _is_environmentally_damaged(game, uid_a),
                                   wounded_b=(uid_b in wounded_set) or _is_environmentally_damaged(game, uid_b),
                                   last_stand_a=(uid_a in last_stand_set),
                                   last_stand_b=(uid_b in last_stand_set),
                                   fight_zone="basic",
                                   zone_tenure_map=zone_tenure)
            a_wins = random.random() < win_p
            winner_id, loser_id = (uid_a, uid_b) if a_wins else (uid_b, uid_a)
            actual_win_p = win_p if a_wins else (1.0 - win_p)

            elim_text = _build_elim_text(
                [winner_id], [loser_id], p_map, rel_map, "basic",
                scores=scores, kill_counts=kill_counts, win_prob=actual_win_p,
                winner_charge=charge_stacks.get(winner_id, 0),
                loser_charge=charge_stacks.get(loser_id, 0),
            )
            chaos_elims.append(elim_text)

            charge_stacks[winner_id] = 0
            charge_stacks[loser_id]  = 0
            chaos_used.add(uid_a)
            chaos_used.add(uid_b)

            if loser_id in game["alive_ids"]:
                game["alive_ids"].remove(loser_id)
                chaos_newly.append(loser_id)
                info        = p_map.get(loser_id, {})
                killer_info = p_map.get(winner_id, {})
                game["eliminated"].append({
                    "user_id":            loser_id,
                    "username":           info.get("username", loser_id),
                    "pet_name":           _pname(info),
                    "species":            info.get("species", "Cat"),
                    "round":              current_round,
                    "text":               elim_text,
                    "is_npc":             info.get("is_npc", False),
                    "eliminated_by":      _pname(killer_info),
                    "eliminated_by_uid":  winner_id,
                    "eliminated_by_uids": [winner_id],
                })
                
                # Process psychological breakdown triggers for opening chaos elimination
                breakdown_narratives = _process_breakdown_triggers(
                    game, loser_id, [winner_id], rel_map, p_map
                )
                chaos_actions.extend(breakdown_narratives)

            if len(game["alive_ids"]) <= 1:
                break

        # Pets not drawn into combat get a solo chaos action
        for uid in alive:
            if uid in chaos_used or uid not in game["alive_ids"]:
                continue
            info = p_map.get(uid, {})
            charge_stacks[uid] = min(8, charge_stacks.get(uid, 0) + 1)
            chaos_actions.append(_build_solo_action(
                uid, info, "basic", list(game["alive_ids"]), p_map, rel_map,
                scores, kill_counts, pct_alive,
                charge_stacks=charge_stacks.get(uid, 0),
                game=game,
            ))

        # Reset stale counter — opening round always has eliminations
        game["_stale_rounds"] = 0

        return {
            "actions":          chaos_actions,
            "eliminations":     chaos_elims,
            "newly_eliminated": chaos_newly,
            "game_over":        len(game["alive_ids"]) <= 1,
            "pet_locations":    chaos_locs,
        }

    # ── Zone assignment ───────────────────────────────────────────────────────
    cur_positions: Dict[str, str] = {
        uid: ((game.get("map_positions") or {}).get(uid) or {}).get("style", "basic")
        for uid in alive
    }

    pet_dest: Dict[str, str] = {}
    for uid in alive:
        pet_dest[uid] = choose_zone(
            uid, alive, p_map, rel_map, cur_positions,
            scores, kill_counts, pct_alive,
            game=game, stale_rounds=stale_rounds,
        )

    # Store each pet's destination zone on their p_map entry so _build_solo_action
    # can check whether they're actually heading toward an enemy (FIX #7).
    for uid, dest in pet_dest.items():
        if uid in p_map:
            p_map[uid]["_cur_zone"] = dest

    # ── Update zone tenure ────────────────────────────────────────────────────
    # A pet that stays in the same zone as last round increments their tenure.
    # Moving to a new zone resets it to 1.
    for uid in alive:
        dest = pet_dest.get(uid, "basic")
        prev = zone_tenure.get(uid, {})
        if prev.get("zone") == dest:
            zone_tenure[uid] = {"zone": dest, "rounds": min(prev.get("rounds", 1) + 1, _ZONE_TENURE_CAP + 1)}
        else:
            zone_tenure[uid] = {"zone": dest, "rounds": 1}
    # Clean up dead pets from tenure map
    for uid in list(zone_tenure.keys()):
        if uid not in alive:
            del zone_tenure[uid]

    zone_groups: Dict[str, List[str]] = {}
    for uid, zone in pet_dest.items():
        zone_groups.setdefault(zone, []).append(uid)

    actions:          List[str] = []
    eliminations:     List[str] = []
    newly_eliminated: List[str] = []
    pet_locations:    Dict[str, str] = dict(pet_dest)
    used:             set = set()

    # Prepend deal/pressure narratives as actions
    if stale_rounds >= _PRESSURE_START_ROUND:
        actions.append(random.choice(_PRESSURE_LINES))
    actions.extend(deal_expire_narratives)
    actions.extend(deal_form_narratives)
    actions.extend(environmental_narratives)
    actions.extend(breakdown_recovery_narratives)

    # ── Betrayal fights — expired deal partners who immediately turn on each other ──
    betrayal_used: set = set()
    for uid_a, uid_b in betrayal_pairs:
        if uid_a not in game["alive_ids"] or uid_b not in game["alive_ids"]:
            continue
        if uid_a in betrayal_used or uid_b in betrayal_used:
            continue
        p_map_ref = game.get("_p_map_cache", {})
        name_a = _pname(p_map_ref.get(uid_a, {}))
        name_b = _pname(p_map_ref.get(uid_b, {}))
        betrayal_narrative = (random.choice(_BETRAYAL_LINES)
                              .replace("{A}", name_a).replace("{B}", name_b))
        actions.append(betrayal_narrative)

        win_p  = elim_win_prob(uid_a, uid_b, p_map,
                               charge_a=charge_stacks.get(uid_a, 0),
                               charge_b=charge_stacks.get(uid_b, 0),
                               wounded_a=(uid_a in wounded_set) or _is_environmentally_damaged(game, uid_a),
                               wounded_b=(uid_b in wounded_set) or _is_environmentally_damaged(game, uid_b),
                               last_stand_a=(uid_a in last_stand_set),
                               last_stand_b=(uid_b in last_stand_set),
                               fight_zone=pet_dest.get(uid_a, "basic"),
                               zone_tenure_map=zone_tenure)
        a_wins = random.random() < win_p
        winner_id, loser_id = (uid_a, uid_b) if a_wins else (uid_b, uid_a)
        actual_win_p = win_p if a_wins else (1.0 - win_p)

        elim_text = _build_elim_text(
            [winner_id], [loser_id], p_map, rel_map,
            pet_dest.get(uid_a, "basic"),
            scores=scores, kill_counts=kill_counts, win_prob=actual_win_p,
            winner_charge=charge_stacks.get(winner_id, 0),
            loser_charge=charge_stacks.get(loser_id, 0),
            loser_was_wounded=(loser_id in wounded_set),
            winner_is_last_stand=(winner_id in last_stand_set),
            winner_zone_tenure=zone_tenure.get(winner_id, {}).get("rounds", 0),
            charge_stacks=charge_stacks,
        )
        eliminations.append(elim_text)
        charge_stacks[winner_id] = 0
        charge_stacks[loser_id]  = 0
        betrayal_used.add(uid_a)
        betrayal_used.add(uid_b)
        used.add(uid_a)
        used.add(uid_b)

        if loser_id in game["alive_ids"]:
            game["alive_ids"].remove(loser_id)
            newly_eliminated.append(loser_id)
            info        = p_map.get(loser_id, {})
            killer_info = p_map.get(winner_id, {})
            game["eliminated"].append({
                "user_id":            loser_id,
                "username":           info.get("username", loser_id),
                "pet_name":           _pname(info),
                "species":            info.get("species", "Cat"),
                "round":              current_round,
                "text":               elim_text,
                "is_npc":             info.get("is_npc", False),
                "eliminated_by":      _pname(killer_info),
                "eliminated_by_uid":  winner_id,
                "eliminated_by_uids": [winner_id],
            })
            kill_counts[winner_id] = kill_counts.get(winner_id, 0) + 1
            # Mark winner as wounded if they barely won
            if actual_win_p < 0.30:
                wounded_map[winner_id] = 1
            
            # Process psychological breakdown triggers for betrayal elimination
            breakdown_narratives = _process_breakdown_triggers(
                game, loser_id, [winner_id], rel_map, p_map
            )
            actions.extend(breakdown_narratives)

        if len(game["alive_ids"]) <= 1:
            break

    # ── Encounter chance boost under pressure ─────────────────────────────────
    # Base encounter chances are raised when stale rounds accumulate
    pressure_boost = min(0.30, stale_rounds * 0.06) if stale_rounds >= _PRESSURE_START_ROUND else 0.0

    for zone, zone_pets in zone_groups.items():
        available = [u for u in zone_pets if u not in used and u in game["alive_ids"]]
        random.shuffle(available)

        while available:
            if len(available) == 1:
                uid = available.pop()
                if uid not in used:
                    used.add(uid)
                    info = p_map.get(uid, {})
                    current_alive = list(game["alive_ids"])
                    # FIX #14: compute live pct_alive so late-game lines fire correctly
                    live_pct = len(current_alive) / max(1, total_start)
                    charge_stacks[uid] = min(8, charge_stacks.get(uid, 0) + 1)
                    actions.append(_build_solo_action(
                        uid, info, zone, current_alive, p_map, rel_map,
                        scores, kill_counts, live_pct,
                        charge_stacks=charge_stacks.get(uid, 0),
                        game=game,
                        dest_zone=pet_dest.get(uid),
                    ))
                break

            # ── Relationship-aware encounter chance ───────────────────────────
            uid0, uid1 = available[0], available[1]
            # Use effective relationship (accounts for deals)
            eff_rel = _effective_rel(game, rel_map, uid0, uid1)
            if is_enemy(rel_map, uid0, uid1):
                enc_chance = 1.00
            elif _either_rel(rel_map, uid0, uid1) == "foe":
                enc_chance = min(1.0, 0.95 + pressure_boost)
            elif is_best_friend(rel_map, uid0, uid1):
                enc_chance = min(0.55, 0.25 + pressure_boost)
            elif eff_rel == "friend":
                # Includes deal partners — they cooperate, not fight
                enc_chance = min(0.60, 0.45 + pressure_boost)
            elif len(available) >= 3:
                enc_chance = min(1.0, 0.92 + pressure_boost)
            else:
                # Base stranger 1v1: scale up as field shrinks so late-game is
                # more decisive. Early game (pct_alive > 0.5): 75%.
                # Mid game (0.25–0.5): 82%. Late game (<0.25): 90%.
                # FIX #14: use live count, not stale pct_alive from round start
                live_pct_enc = len(game["alive_ids"]) / max(1, total_start)
                base_enc = 0.75 + (1.0 - live_pct_enc) * 0.20
                enc_chance = min(1.0, base_enc + pressure_boost)

            # FIX #9: dominant pet vs clearly weaker opponent = 100% encounter.
            # A dominant predator that moved to hunt someone doesn't let them walk away.
            s0, s1 = scores.get(uid0, 1.0), scores.get(uid1, 1.0)
            if s0 > s1 * 1.5 or s1 > s0 * 1.5:
                enc_chance = 1.00

            # Last-stand pets always encounter — nothing to lose
            if uid0 in last_stand_set or uid1 in last_stand_set:
                enc_chance = 1.00
            
            # Broken down pets are more aggressive — increased encounter chance
            if _is_broken_down(game, uid0) or _is_broken_down(game, uid1):
                enc_chance = min(1.0, enc_chance + _BREAKDOWN_AGGRO_BOOST)

            if random.random() >= enc_chance:
                uid = available.pop(0)
                used.add(uid)
                info = p_map.get(uid, {})
                current_alive = list(game["alive_ids"])
                live_pct = len(current_alive) / max(1, total_start)
                charge_stacks[uid] = min(8, charge_stacks.get(uid, 0) + 1)
                actions.append(_build_solo_action(
                    uid, info, zone, current_alive, p_map, rel_map,
                    scores, kill_counts, live_pct,
                    charge_stacks=charge_stacks.get(uid, 0),
                    game=game,
                    dest_zone=pet_dest.get(uid),
                ))
                continue

            # Build a valid encounter
            enc = _build_encounter(available, rel_map, game=game)
            if enc is None:
                uid = available.pop(0)
                used.add(uid)
                info = p_map.get(uid, {})
                current_alive = list(game["alive_ids"])
                live_pct = len(current_alive) / max(1, total_start)
                charge_stacks[uid] = min(8, charge_stacks.get(uid, 0) + 1)
                actions.append(_build_solo_action(
                    uid, info, zone, current_alive, p_map, rel_map,
                    scores, kill_counts, live_pct,
                    charge_stacks=charge_stacks.get(uid, 0),
                    game=game,
                    dest_zone=pet_dest.get(uid),
                ))
                continue

            side_a, side_b = enc
            for u in side_a + side_b:
                if u in available:
                    available.remove(u)
            used.update(side_a)
            used.update(side_b)

            # Record BF group elimination if applicable
            all_enc = side_a + side_b
            if len(all_enc) >= 3 and all(
                is_best_friend(rel_map, all_enc[i], all_enc[j])
                for i in range(len(all_enc))
                for j in range(i + 1, len(all_enc))
            ):
                group_list = list(all_enc)
                bf_group_elims.append(frozenset(group_list))
                bf_group_elims_raw.append(group_list)

            # Resolve combat
            env_damaged = game.get("_env_damaged", set())
            combined_wounded = wounded_set | env_damaged
            win_p  = _group_combat_odds(side_a, side_b, p_map,
                                        charge_stacks=charge_stacks,
                                        wounded_set=combined_wounded,
                                        last_stand_set=last_stand_set,
                                        zone_tenure_map=zone_tenure,
                                        fight_zone=zone)
            a_wins = random.random() < win_p
            winners = side_a if a_wins else side_b
            losers  = side_b if a_wins else side_a
            actual_win_p = win_p if a_wins else (1.0 - win_p)

            rep_winner = max(winners, key=lambda u: survive_score(p_map.get(u, {})))
            rep_loser  = max(losers,  key=lambda u: survive_score(p_map.get(u, {})))

            elim_text = _build_elim_text(
                winners, losers, p_map, rel_map, zone,
                scores=scores, kill_counts=kill_counts, win_prob=actual_win_p,
                winner_charge=charge_stacks.get(rep_winner, 0),
                loser_charge=charge_stacks.get(rep_loser, 0),
                loser_was_wounded=(rep_loser in wounded_set),
                winner_is_last_stand=(rep_winner in last_stand_set),
                winner_zone_tenure=zone_tenure.get(rep_winner, {}).get("rounds", 0),
                charge_stacks=charge_stacks,
            )
            eliminations.append(elim_text)

            for u in side_a + side_b:
                charge_stacks[u] = 0
                # Mark winner as wounded if they barely survived
            if actual_win_p < 0.30:
                wounded_map[rep_winner] = 1

            for uid in losers:
                if uid in game["alive_ids"]:
                    game["alive_ids"].remove(uid)
                    newly_eliminated.append(uid)
                    info        = p_map.get(uid, {})
                    killer_info = p_map.get(winners[0], {}) if winners else {}
                    game["eliminated"].append({
                        "user_id":            uid,
                        "username":           info.get("username", uid),
                        "pet_name":           _pname(info),
                        "species":            info.get("species", "Cat"),
                        "round":              game["round_index"],
                        "text":               elim_text,
                        "is_npc":             info.get("is_npc", False),
                        "eliminated_by":      _pname(killer_info),
                        "eliminated_by_uid":  winners[0] if winners else "",
                        "eliminated_by_uids": list(winners),
                    })
                    # FIX #4: update kill_counts mid-round so subsequent fights
                    # in the same round reflect accurate kill streaks.
                    for w in winners:
                        kill_counts[w] = kill_counts.get(w, 0) + 1
                    
                    # Process psychological breakdown triggers for this elimination
                    for uid in losers:
                        breakdown_narratives = _process_breakdown_triggers(
                            game, uid, list(winners), rel_map, p_map
                        )
                        actions.extend(breakdown_narratives)

            if len(game["alive_ids"]) <= 1:
                break

        if len(game["alive_ids"]) <= 1:
            break

    # ── Update stale-round counter ────────────────────────────────────────────
    if newly_eliminated:
        game["_stale_rounds"] = 0  # reset on any elimination
    else:
        game["_stale_rounds"] = stale_rounds + 1
    
    # ── Clean up environmental effects ────────────────────────────────────────
    # Environmental damage lasts only one round
    if "_env_damaged" in game:
        game["_env_damaged"].clear()
    if "_env_evacuated" in game:
        game["_env_evacuated"].clear()
    
    # ── Generate enhanced round summary ───────────────────────────────────────
    round_summary = _generate_round_summary(
        game, current_round, newly_eliminated, len(alive), 
        environmental_narratives, breakdown_recovery_narratives
    )

    return {
        "actions":          actions,
        "eliminations":     eliminations,
        "newly_eliminated": newly_eliminated,
        "game_over":        len(game["alive_ids"]) <= 1,
        "pet_locations":    pet_locations,
        "round_summary":    round_summary,  # Enhanced summary for live feed
    }
