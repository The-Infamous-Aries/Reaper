"""
Colosseum API - Passive hourly battle league.
Users join the Colosseum and every hour their pet automatically battles a random
opponent (another user pet or NPC). XP is awarded regardless of outcome.
Pending rewards accumulate in the DB until the user claims them.

XP Formulas:
  Win:  floor((level / equip_mult) * level * 250)
  Loss: floor((level / equip_mult) * 100)
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import random
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite
from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse

from Systems.Functions.db_paths import COLOSSEUM_DB_STR
from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.event_bus import EventQueue
from Systems.Pets.Logic.pet_components import AnimationComponent
from web.api.pets.gpp_helpers import _invalidate_stats_cache

logger = logging.getLogger("colosseum_api")
router = APIRouter()

# ── Pet badge helpers ─────────────────────────────────────────────────────────
COLO_PROJECT_ROOT = Path(__file__).resolve().parents[2]
COLO_BADGE_STATIC_ROOT = COLO_PROJECT_ROOT / "web" / "static" / "pet_badges"

def _colo_selected_badge_url(user_id: str) -> str:
    safe_user_id = re.sub(r"[^0-9A-Za-z_-]", "", str(user_id))
    selected = COLO_BADGE_STATIC_ROOT / safe_user_id / "selected.png"
    if not selected.exists():
        return ""
    return f"/static/pet_badges/{safe_user_id}/selected.png?v={int(selected.stat().st_mtime)}"

# ── Constants ─────────────────────────────────────────────────────────────────
BATTLE_INTERVAL_SECS = 3600   # 1 hour between rounds
MAX_LOG_ENTRIES      = 50     # round log entries kept in DB
NPC_CHANCE           = 0.35   # 35% chance of NPC opponent when no other user available

# ── DB helpers ────────────────────────────────────────────────────────────────
async def _ensure_db() -> None:
    """Create Colosseum tables if they do not exist."""
    async with aiosqlite.connect(COLOSSEUM_DB_STR) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS members (
                user_id         TEXT PRIMARY KEY,
                username        TEXT NOT NULL DEFAULT '',
                pet_name        TEXT NOT NULL DEFAULT '',
                pet_species     TEXT NOT NULL DEFAULT '',
                pet_element     TEXT NOT NULL DEFAULT 'basic',
                pet_element2    TEXT NOT NULL DEFAULT '',
                pet_type        TEXT NOT NULL DEFAULT 'land',
                pet_level       INTEGER NOT NULL DEFAULT 1,
                joined_at       REAL NOT NULL DEFAULT 0,
                last_battle     REAL NOT NULL DEFAULT 0,
                wins            INTEGER NOT NULL DEFAULT 0,
                losses          INTEGER NOT NULL DEFAULT 0,
                rounds          INTEGER NOT NULL DEFAULT 0,
                pending_xp      INTEGER NOT NULL DEFAULT 0,
                pending_keys    TEXT NOT NULL DEFAULT '[]',
                pending_potions TEXT NOT NULL DEFAULT '[]',
                avatar          TEXT NOT NULL DEFAULT ''
            )
        """)
        # Migrate: add pending_potions column if it doesn't exist yet
        try:
            await db.execute("ALTER TABLE members ADD COLUMN pending_potions TEXT NOT NULL DEFAULT '[]'")
        except Exception:
            pass  # Column already exists
        await db.execute("""
            CREATE TABLE IF NOT EXISTS round_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                round_num   INTEGER NOT NULL DEFAULT 0,
                ts          REAL NOT NULL DEFAULT 0,
                user_a_id   TEXT NOT NULL DEFAULT '',
                user_a_name TEXT NOT NULL DEFAULT '',
                user_b_id   TEXT NOT NULL DEFAULT '',
                user_b_name TEXT NOT NULL DEFAULT '',
                winner_id   TEXT NOT NULL DEFAULT '',
                winner_name TEXT NOT NULL DEFAULT '',
                xp_a        INTEGER NOT NULL DEFAULT 0,
                xp_b        INTEGER NOT NULL DEFAULT 0,
                summary     TEXT NOT NULL DEFAULT '',
                is_npc      INTEGER NOT NULL DEFAULT 0,
                winner_key  TEXT NOT NULL DEFAULT ''
            )
        """)
        # Migrate: add winner_key column if it doesn't exist yet
        try:
            await db.execute("ALTER TABLE round_log ADD COLUMN winner_key TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass  # Column already exists
        await db.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_members_last_battle ON members(last_battle)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_log_ts ON round_log(ts DESC)")
        await db.commit()


async def _get_meta(key: str, default: str = "") -> str:
    async with aiosqlite.connect(COLOSSEUM_DB_STR) as db:
        async with db.execute("SELECT value FROM meta WHERE key=?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else default


async def _set_meta(key: str, value: str) -> None:
    async with aiosqlite.connect(COLOSSEUM_DB_STR) as db:
        await db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (key, value))
        await db.commit()


async def _get_member(user_id: str) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(COLOSSEUM_DB_STR) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM members WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def _upsert_member(user_id: str, data: Dict[str, Any]) -> None:
    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    updates = ", ".join(f"{k}=excluded.{k}" for k in data if k != "user_id")
    sql = f"INSERT INTO members({cols}) VALUES({placeholders}) ON CONFLICT(user_id) DO UPDATE SET {updates}"
    async with aiosqlite.connect(COLOSSEUM_DB_STR) as db:
        await db.execute(sql, list(data.values()))
        await db.commit()


async def _get_all_members() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(COLOSSEUM_DB_STR) as db:
        db.row_factory = aiosqlite.Row
        # Only return members who are currently active (joined_at > 0)
        async with db.execute(
            "SELECT * FROM members WHERE joined_at > 0 ORDER BY wins DESC, rounds DESC"
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def _get_recent_log(limit: int = 20) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(COLOSSEUM_DB_STR) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM round_log ORDER BY ts DESC LIMIT ?", (limit,)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def _append_log(entry: Dict[str, Any]) -> None:
    async with aiosqlite.connect(COLOSSEUM_DB_STR) as db:
        await db.execute("""
            INSERT INTO round_log(round_num,ts,user_a_id,user_a_name,user_b_id,user_b_name,
                                  winner_id,winner_name,xp_a,xp_b,summary,is_npc,winner_key)
            VALUES(:round_num,:ts,:user_a_id,:user_a_name,:user_b_id,:user_b_name,
                   :winner_id,:winner_name,:xp_a,:xp_b,:summary,:is_npc,:winner_key)
        """, entry)
        # Prune old entries
        await db.execute(f"""
            DELETE FROM round_log WHERE id NOT IN (
                SELECT id FROM round_log ORDER BY ts DESC LIMIT {MAX_LOG_ENTRIES}
            )
        """)
        await db.commit()



# ── XP formula ────────────────────────────────────────────────────────────────
def _calc_xp(pet_level: int, equip_mult: float, won: bool) -> int:
    """
    Win:  floor((level / equip_mult) * level * 250)
    Loss: floor((level / equip_mult) * 100)
    equip_mult is clamped to [1, 8] so it never zeroes out XP.
    """
    em = max(1.0, min(8.0, float(equip_mult)))
    if won:
        return max(1, math.floor((pet_level / em) * pet_level * 250))
    return max(1, math.floor((pet_level / em) * 100))


def _get_equip_mult(pet: Dict[str, Any]) -> float:
    """
    Return the equipment set multiplier for a pet (1-4 base + level bonus).
    Mirrors the JS calcEquipBonuses logic from mypet.js.
    """
    try:
        from Systems.Pets.Logic.pet_brain import StatsCalculator
        stats = StatsCalculator.calculate_pet_stats(pet)
        # equip_mult is embedded in computed stats as 'equip_multiplier'
        return float(stats.get("equip_multiplier", 1.0))
    except Exception:
        return 1.0


def _pick_random_key() -> str:
    """Pick one random key (Key1/Key2/Key3) with equal probability."""
    return random.choice(["Key1", "Key2", "Key3"])


def _pick_random_potion() -> Optional[Dict[str, Any]]:
    """Pick one random potion using the LootCalculator weighted rarity system."""
    try:
        from Systems.Pets.Logic.loot_calculator import LootCalculator
        return LootCalculator.get_potion_loot(difficulty="normal", bypass_chance=True)
    except Exception:
        return None


async def _sync_colosseum_stats_to_pet(user_id: str, member: Dict[str, Any]) -> None:
    """
    Write the colosseum DB's authoritative wins/losses/rounds totals into the
    pet's battle_stats.colosseum dict.  Called after every battle and on claim
    so the pets DB is always consistent with the colosseum DB.

    xp_earned in battle_stats is the running total of XP earned across all
    colosseum battles (claimed + pending).  We only ever increase it — never
    decrease — so claiming doesn't wipe the historical record.
    """
    try:
        async with user_data_manager._get_user_lock(user_id):
            pet = await user_data_manager._get_pet_data_no_lock(user_id)
            if not pet:
                return
            stats = pet.setdefault("battle_stats", {})
            col   = stats.setdefault("colosseum", {})

            # Authoritative totals from colosseum DB
            col["wins"]   = int(member.get("wins",   0))
            col["losses"] = int(member.get("losses", 0))
            col["rounds"] = int(member.get("rounds", 0))

            # xp_earned = total XP ever earned in colosseum (claimed + still pending).
            # We derive this from xp_sources["colosseum"] (already-claimed XP applied
            # by apply_xp_change) + pending_xp (not yet claimed).
            already_claimed_xp = int(pet.get("xp_sources", {}).get("colosseum", 0))
            pending_xp         = int(member.get("pending_xp", 0))
            col["xp_earned"]   = already_claimed_xp + pending_xp

            await user_data_manager._save_pet_data_no_lock(user_id, pet)
    except Exception as e:
        logger.warning("[Colosseum] _sync_colosseum_stats_to_pet failed for %s: %s", user_id, e)



async def _simulate_colosseum_battle(
    pet_a: Dict[str, Any],
    pet_b: Dict[str, Any],
    user_a_id: str,
    user_b_id: str,
    is_npc: bool = False,
) -> Dict[str, Any]:
    """
    Fully simulate a battle between two pets using the real DamageCalculator,
    NPCBrain, type/element advantages, abilities, and charge mechanics.
    Returns a result dict with winner, loser, xp for each side, and a log.
    """
    import random as _rng
    from Systems.Pets.Logic.pet_brain import StatsCalculator, DamageCalculator, NPCBrain

    def _build_fighter(pet: Dict[str, Any]) -> Dict[str, Any]:
        s = StatsCalculator.calculate_pet_stats(pet)
        return {
            "atk":   int(s.get("attack",     10)),
            "def":   int(s.get("defense",     5)),
            "hp":    int(s.get("max_health", 500)),
            "type":  str(pet.get("category", "land")).lower(),
            "elem":  str(pet.get("element",  "basic")).lower(),
            "elem2": str(pet.get("element2", "") or "").lower() or None,
            "spec":  str(pet.get("species",  "")),
            "name":  str(pet.get("name",     "Unknown")),
            "level": int(pet.get("level",    1)),
            "charge": 1.0,
            "last_action": None,
            "pet_data": pet,
        }

    fa = _build_fighter(pet_a)
    fb = _build_fighter(pet_b)
    hp_a, hp_b = fa["hp"], fb["hp"]
    npc_brain = NPCBrain()
    log_lines: List[str] = []
    MAX_TURNS = 35

    # Get action labels for both pets
    labels_a = DamageCalculator.get_action_labels(
        fa["type"], fa["elem"], fa["spec"],
        custom_labels=pet_a.get("action_labels", {})
    )
    labels_b = DamageCalculator.get_action_labels(
        fb["type"], fb["elem"], fb["spec"],
        custom_labels=pet_b.get("action_labels", {})
    )

    for turn_num in range(1, MAX_TURNS + 1):
        if hp_a <= 0 or hp_b <= 0:
            break

        # ── Decide actions ────────────────────────────────────────────────────
        # Pet A uses NPCBrain for realistic decision-making
        state_a = {
            "hp": hp_a, "max_hp": fa["hp"], "prev_hp": hp_a,
            "charge_multiplier": fa["charge"], "last_action": fa["last_action"],
            "attack_stat": float(fa["atk"]), "defense_stat": float(fa["def"]),
            "seed": turn_num * 7 + hash(user_a_id) % 100,
            "pet_data": fa["pet_data"],
        }
        state_b = {
            "hp": hp_b, "max_hp": fb["hp"], "prev_hp": hp_b,
            "charge_multiplier": fb["charge"], "last_action": fb["last_action"],
            "attack_stat": float(fb["atk"]), "defense_stat": float(fb["def"]),
            "seed": turn_num * 13 + hash(user_b_id) % 100,
            "pet_data": fb["pet_data"],
        }
        players_for_a = [{"alive": hp_b > 0, "hp": hp_b, "max_hp": fb["hp"],
                          "charging": fb["charge"] > 1.0}]
        players_for_b = [{"alive": hp_a > 0, "hp": hp_a, "max_hp": fa["hp"],
                          "charging": fa["charge"] > 1.0}]

        act_a = npc_brain.decide_action(state_a, players_for_a).get("action", "attack")
        act_b = npc_brain.decide_action(state_b, players_for_b).get("action", "attack")

        # ── Charge accumulation ───────────────────────────────────────────────
        if act_a == "charge":
            fa["charge"] = DamageCalculator.get_next_charge_multiplier(fa["charge"], fa["pet_data"])
        if act_b == "charge":
            fb["charge"] = DamageCalculator.get_next_charge_multiplier(fb["charge"], fb["pet_data"])

        # ── Damage calculation ────────────────────────────────────────────────
        r_a = DamageCalculator.calculate_battle_action(
            attacker_attack=fa["atk"], target_defense=fb["def"],
            charge_multiplier=fa["charge"] if act_a in ("attack", "defend") else 1.0,
            target_charge_multiplier=fb["charge"] if act_b == "defend" else 1.0,
            attacker_action_type=act_a, target_action_type=act_b,
            attacker_type=fa["type"], attacker_element=fa["elem"],
            attacker_element2=fa["elem2"],
            defender_type=fb["type"], defender_element=fb["elem"],
            defender_element2=fb["elem2"],
            attacker_species=fa["spec"],
        )
        r_b = DamageCalculator.calculate_battle_action(
            attacker_attack=fb["atk"], target_defense=fa["def"],
            charge_multiplier=fb["charge"] if act_b in ("attack", "defend") else 1.0,
            target_charge_multiplier=fa["charge"] if act_a == "defend" else 1.0,
            attacker_action_type=act_b, target_action_type=act_a,
            attacker_type=fb["type"], attacker_element=fb["elem"],
            attacker_element2=fb["elem2"],
            defender_type=fa["type"], defender_element=fa["elem"],
            defender_element2=fa["elem2"],
            attacker_species=fb["spec"],
        )

        dmg_a = r_a["final_damage"]   # A deals to B
        dmg_b = r_b["final_damage"]   # B deals to A
        par_a = r_a["parry_damage"]   # A parries back at B (when A defends)
        par_b = r_b["parry_damage"]   # B parries back at A (when B defends)

        hp_b = max(0, hp_b - dmg_a - par_b)
        hp_a = max(0, hp_a - dmg_b - par_a)

        # Reset charge after use
        if act_a in ("attack", "defend"):
            fa["charge"] = 1.0
        if act_b in ("attack", "defend"):
            fb["charge"] = 1.0
        fa["last_action"] = act_a
        fb["last_action"] = act_b

        # ── Build log line ────────────────────────────────────────────────────
        label_a = labels_a.get(act_a, act_a.title())
        label_b = labels_b.get(act_b, act_b.title())
        mult_a  = r_a.get("type_element_bonus_mult_attack", 1.0)
        mult_b  = r_b.get("type_element_bonus_mult_attack", 1.0)
        eff_a   = " 🔥" if mult_a > 1.05 else (" 💨" if mult_a < 0.95 else "")
        eff_b   = " 🔥" if mult_b > 1.05 else (" 💨" if mult_b < 0.95 else "")

        if act_a == "charge":
            log_lines.append(f"T{turn_num}: ⚡ {fa['name']} charges (x{fa['charge']:.0f})")
        elif act_a == "defend":
            if par_a > 0:
                log_lines.append(f"T{turn_num}: 🛡️ {fa['name']} parries {par_a} back!")
            else:
                log_lines.append(f"T{turn_num}: 🛡️ {fa['name']} defends")
        else:
            if dmg_a > 0:
                log_lines.append(f"T{turn_num}: ⚔️ {fa['name']} {label_a} → {dmg_a} dmg{eff_a}")
            else:
                log_lines.append(f"T{turn_num}: ⚔️ {fa['name']} {label_a} → blocked")

        if act_b == "charge":
            log_lines.append(f"T{turn_num}: ⚡ {fb['name']} charges (x{fb['charge']:.0f})")
        elif act_b == "defend":
            if par_b > 0:
                log_lines.append(f"T{turn_num}: 🛡️ {fb['name']} parries {par_b} back!")
            else:
                log_lines.append(f"T{turn_num}: 🛡️ {fb['name']} defends")
        else:
            if dmg_b > 0:
                log_lines.append(f"T{turn_num}: ⚔️ {fb['name']} {label_b} → {dmg_b} dmg{eff_b}")
            else:
                log_lines.append(f"T{turn_num}: ⚔️ {fb['name']} {label_b} → blocked")

        if hp_a <= 0 or hp_b <= 0:
            break

    # ── Determine winner ──────────────────────────────────────────────────────
    a_won = hp_a > 0 or (hp_a == 0 and hp_b == 0 and _rng.random() < 0.5)
    winner_id   = user_a_id if a_won else user_b_id
    loser_id    = user_b_id if a_won else user_a_id
    winner_name = fa["name"] if a_won else fb["name"]
    loser_name  = fb["name"] if a_won else fa["name"]

    # ── XP calculation ────────────────────────────────────────────────────────
    em_a = _get_equip_mult(pet_a)
    em_b = _get_equip_mult(pet_b)
    xp_a = _calc_xp(fa["level"], em_a, a_won)
    xp_b = _calc_xp(fb["level"], em_b, not a_won)

    log_lines.append(f"🏆 {winner_name} wins! | {fa['name']} +{xp_a} XP | {fb['name']} +{xp_b} XP")

    return {
        "winner_id":   winner_id,
        "loser_id":    loser_id,
        "winner_name": winner_name,
        "loser_name":  loser_name,
        "xp_a":        xp_a,
        "xp_b":        xp_b,
        "a_won":       a_won,
        "log":         log_lines,
        "is_npc":      is_npc,
        "turns":       len([l for l in log_lines if l.startswith("T")]),
    }



# ── NPC pet generator ─────────────────────────────────────────────────────────
def _generate_npc_pet(opponent_level: int) -> Dict[str, Any]:
    """Generate a balanced NPC pet to fight against."""
    from Systems.Pets.Logic.pet_brain import DamageCalculator
    from Systems.Functions.optimal_file_manager import OptimalFileManager

    all_elements = list(DamageCalculator.ELEMENT_EFFECTIVENESS.keys())
    all_types    = list(DamageCalculator.CATEGORY_ADVANTAGES.keys())
    elem  = random.choice(all_elements)
    ptype = random.choice(all_types)

    try:
        info = OptimalFileManager().get_data("info")
        species_list = list(info.get("Pets", {}).keys())
        species = random.choice(species_list) if species_list else "Wolf"
        base_stats = info["Pets"][species].get("Stats", {})
    except Exception:
        species = "Wolf"
        base_stats = {"ATT": 12, "DEF": 10, "INT": 8, "DEX": 10, "HAP": 10, "ENE": 10}

    # Scale stats to opponent level
    scale = max(0.5, min(3.0, opponent_level / 10.0))
    scaled = {k: max(5, int(v * scale)) for k, v in base_stats.items()}

    try:
        base = OptimalFileManager().get_data("base")
        adj  = random.choice(base.get("element_bases", {}).get(elem, ["Ancient"]))
        noun = random.choice(base.get("category_bases", {}).get(ptype, ["Guardian"]))
        name = f"{adj} {noun}"
    except Exception:
        name = f"{elem.title()} {species}"

    return {
        "name":      name,
        "species":   species,
        "category":  ptype,
        "element":   elem,
        "element2":  "",
        "level":     opponent_level,
        "action_labels": {},
        **scaled,
    }


# ── Hourly battle loop ────────────────────────────────────────────────────────
_round_counter: int = 0
_loop_task: Optional[asyncio.Task] = None


async def _run_hourly_battles() -> None:
    """
    Background task: every BATTLE_INTERVAL_SECS seconds, pair up all active
    Colosseum members and simulate their battles, accumulating pending rewards.
    """
    global _round_counter
    await _ensure_db()
    # Restore round counter from DB
    try:
        _round_counter = int(await _get_meta("round_counter", "0"))
    except Exception:
        _round_counter = 0

    while True:
        # Sleep until next battle time
        try:
            last_str = await _get_meta("last_battle_ts", "0")
            last_ts  = float(last_str)
        except Exception:
            last_ts = 0.0

        now = time.time()
        elapsed = now - last_ts
        wait = max(0.0, BATTLE_INTERVAL_SECS - elapsed)
        if wait > 0:
            logger.info(f"[Colosseum] Next round in {wait:.0f}s")
            await asyncio.sleep(wait)

        await _run_one_round()


async def _run_one_round() -> None:
    """Run one full round of Colosseum battles for all active members."""
    global _round_counter
    _round_counter += 1
    now = time.time()
    await _set_meta("last_battle_ts", str(now))
    await _set_meta("round_counter",  str(_round_counter))

    members = await _get_all_members()
    if not members:
        logger.info("[Colosseum] Round %d: no members, skipping", _round_counter)
        return

    logger.info("[Colosseum] Round %d: %d members", _round_counter, len(members))

    # Shuffle for random pairing
    random.shuffle(members)
    paired: set = set()

    for member in members:
        uid = member["user_id"]
        if uid in paired:
            continue

        # Find a random opponent not yet paired
        candidates = [m for m in members if m["user_id"] != uid and m["user_id"] not in paired]

        use_npc = not candidates or random.random() < NPC_CHANCE
        if use_npc:
            opponent_level = member["pet_level"]
            npc_pet = _generate_npc_pet(opponent_level)
            npc_uid = f"npc_{uid}_{_round_counter}"
            await _battle_member_vs_npc(member, npc_pet, npc_uid, now)
        else:
            opponent = random.choice(candidates)
            paired.add(uid)
            paired.add(opponent["user_id"])
            await _battle_two_members(member, opponent, now)


async def _battle_member_vs_npc(
    member: Dict[str, Any],
    npc_pet: Dict[str, Any],
    npc_uid: str,
    now: float,
) -> None:
    """Simulate a member vs NPC battle and store pending rewards."""
    pet = await user_data_manager.get_pet_data_async(member["user_id"])
    if not pet:
        return

    try:
        result = await _simulate_colosseum_battle(
            pet_a=pet,
            pet_b=npc_pet,
            user_a_id=member["user_id"],
            user_b_id=npc_uid,
            is_npc=True,
        )
    except Exception as e:
        logger.error("[Colosseum] NPC battle error for %s: %s", member["user_id"], e, exc_info=True)
        return

    a_won = result["a_won"]
    xp_a  = result["xp_a"]

    # Accumulate pending XP
    new_pending = member["pending_xp"] + xp_a
    new_wins    = member["wins"]   + (1 if a_won else 0)
    new_losses  = member["losses"] + (0 if a_won else 1)
    new_rounds  = member["rounds"] + 1

    # Award keys based on win milestones: every 2 wins = Key1, every 5 wins = Key2, every 10 wins = Key3
    existing_keys    = json.loads(member.get("pending_keys",    "[]") or "[]")
    existing_potions = json.loads(member.get("pending_potions", "[]") or "[]")
    awarded_key = ""
    if a_won:
        awarded_keys = []
        # Check milestone rewards (cumulative on milestone wins)
        if new_wins % 10 == 0:  # Every 10 wins: Key1 + Key2 + Key3
            awarded_keys = ["Key1", "Key2", "Key3"]
        elif new_wins % 5 == 0:  # Every 5 wins (not divisible by 10): Key1 + Key2
            awarded_keys = ["Key1", "Key2"]
        elif new_wins % 2 == 0:  # Every 2 wins (not divisible by 5): Key1
            awarded_keys = ["Key1"]
        
        for key in awarded_keys:
            existing_keys.append(key)
        awarded_key = ", ".join(awarded_keys) if awarded_keys else ""

    await _upsert_member(member["user_id"], {
        "user_id":          member["user_id"],
        "pending_xp":       new_pending,
        "pending_keys":     json.dumps(existing_keys),
        "pending_potions":  json.dumps(existing_potions),
        "wins":             new_wins,
        "losses":           new_losses,
        "rounds":           new_rounds,
        "last_battle":      now,
    })

    # Sync authoritative colosseum totals → pets DB so mypets page is always current
    await _sync_colosseum_stats_to_pet(member["user_id"], {
        "wins":       new_wins,
        "losses":     new_losses,
        "rounds":     new_rounds,
        "pending_xp": new_pending,
    })

    # Refresh member data for log
    await _append_log({
        "round_num":   _round_counter,
        "ts":          now,
        "user_a_id":   member["user_id"],
        "user_a_name": member["pet_name"],
        "user_b_id":   npc_uid,
        "user_b_name": npc_pet["name"],
        "winner_id":   result["winner_id"],
        "winner_name": result["winner_name"],
        "xp_a":        xp_a,
        "xp_b":        0,
        "summary":     result["log"][-1] if result["log"] else "",
        "is_npc":      1,
        "winner_key":  awarded_key,
    })

    # NOTE: Do NOT call broadcast_unified here — colosseum rounds are independent
    # of arena rooms and broadcasting would interrupt active NPC/PvP/Boss battles
    # for all connected clients. The colosseum.js frontend polls /api/colosseum/state
    # on its own 15-second interval instead.


async def _battle_two_members(
    member_a: Dict[str, Any],
    member_b: Dict[str, Any],
    now: float,
) -> None:
    """Simulate a battle between two Colosseum members and store pending rewards."""
    pet_a = await user_data_manager.get_pet_data_async(member_a["user_id"])
    pet_b = await user_data_manager.get_pet_data_async(member_b["user_id"])
    if not pet_a or not pet_b:
        return

    try:
        result = await _simulate_colosseum_battle(
            pet_a=pet_a,
            pet_b=pet_b,
            user_a_id=member_a["user_id"],
            user_b_id=member_b["user_id"],
            is_npc=False,
        )
    except Exception as e:
        logger.error("[Colosseum] PvP battle error: %s", e, exc_info=True)
        return

    a_won = result["a_won"]
    xp_a  = result["xp_a"]
    xp_b  = result["xp_b"]

    # Compute new totals for both members FIRST (before awarding keys)
    new_wins_a   = member_a["wins"]   + (1 if a_won else 0)
    new_losses_a = member_a["losses"] + (0 if a_won else 1)
    new_rounds_a = member_a["rounds"] + 1
    new_xp_a     = member_a["pending_xp"] + xp_a

    new_wins_b   = member_b["wins"]   + (0 if a_won else 1)
    new_losses_b = member_b["losses"] + (1 if a_won else 0)
    new_rounds_b = member_b["rounds"] + 1
    new_xp_b     = member_b["pending_xp"] + xp_b

    # PvP rewards: winner gets 2 potions + milestone keys; loser gets 1 potion
    keys_a    = json.loads(member_a.get("pending_keys",    "[]") or "[]")
    keys_b    = json.loads(member_b.get("pending_keys",    "[]") or "[]")
    potions_a = json.loads(member_a.get("pending_potions", "[]") or "[]")
    potions_b = json.loads(member_b.get("pending_potions", "[]") or "[]")

    winner_key = ""
    if a_won:
        # A wins: 2 potions + milestone keys
        awarded_keys = []
        # Check milestone rewards (cumulative on milestone wins)
        if new_wins_a % 10 == 0:  # Every 10 wins: Key1 + Key2 + Key3
            awarded_keys = ["Key1", "Key2", "Key3"]
        elif new_wins_a % 5 == 0:  # Every 5 wins (not divisible by 10): Key1 + Key2
            awarded_keys = ["Key1", "Key2"]
        elif new_wins_a % 2 == 0:  # Every 2 wins (not divisible by 5): Key1
            awarded_keys = ["Key1"]
        
        for key in awarded_keys:
            keys_a.append(key)
        winner_key = ", ".join(awarded_keys) if awarded_keys else ""
        
        for _ in range(2):
            p = _pick_random_potion()
            if p:
                potions_a.append(p.get("name") or p.get("emoji_file", "basic_potion"))
        # B loses: 1 potion
        p = _pick_random_potion()
        if p:
            potions_b.append(p.get("name") or p.get("emoji_file", "basic_potion"))
    else:
        # B wins: 2 potions + milestone keys
        awarded_keys = []
        # Check milestone rewards (cumulative on milestone wins)
        if new_wins_b % 10 == 0:  # Every 10 wins: Key1 + Key2 + Key3
            awarded_keys = ["Key1", "Key2", "Key3"]
        elif new_wins_b % 5 == 0:  # Every 5 wins (not divisible by 10): Key1 + Key2
            awarded_keys = ["Key1", "Key2"]
        elif new_wins_b % 2 == 0:  # Every 2 wins (not divisible by 5): Key1
            awarded_keys = ["Key1"]
        
        for key in awarded_keys:
            keys_b.append(key)
        winner_key = ", ".join(awarded_keys) if awarded_keys else ""
        
        for _ in range(2):
            p = _pick_random_potion()
            if p:
                potions_b.append(p.get("name") or p.get("emoji_file", "basic_potion"))
        # A loses: 1 potion
        p = _pick_random_potion()
        if p:
            potions_a.append(p.get("name") or p.get("emoji_file", "basic_potion"))

    # Update member A
    await _upsert_member(member_a["user_id"], {
        "user_id":          member_a["user_id"],
        "pending_xp":       new_xp_a,
        "pending_keys":     json.dumps(keys_a),
        "pending_potions":  json.dumps(potions_a),
        "wins":             new_wins_a,
        "losses":           new_losses_a,
        "rounds":           new_rounds_a,
        "last_battle":      now,
    })
    # Update member B
    await _upsert_member(member_b["user_id"], {
        "user_id":          member_b["user_id"],
        "pending_xp":       new_xp_b,
        "pending_keys":     json.dumps(keys_b),
        "pending_potions":  json.dumps(potions_b),
        "wins":             new_wins_b,
        "losses":           new_losses_b,
        "rounds":           new_rounds_b,
        "last_battle":      now,
    })

    # Sync authoritative colosseum totals → pets DB for both members
    await _sync_colosseum_stats_to_pet(member_a["user_id"], {
        "wins": new_wins_a, "losses": new_losses_a,
        "rounds": new_rounds_a, "pending_xp": new_xp_a,
    })
    await _sync_colosseum_stats_to_pet(member_b["user_id"], {
        "wins": new_wins_b, "losses": new_losses_b,
        "rounds": new_rounds_b, "pending_xp": new_xp_b,
    })

    await _append_log({
        "round_num":   _round_counter,
        "ts":          now,
        "user_a_id":   member_a["user_id"],
        "user_a_name": member_a["pet_name"],
        "user_b_id":   member_b["user_id"],
        "user_b_name": member_b["pet_name"],
        "winner_id":   result["winner_id"],
        "winner_name": result["winner_name"],
        "xp_a":        xp_a,
        "xp_b":        xp_b,
        "summary":     result["log"][-1] if result["log"] else "",
        "is_npc":      0,
        "winner_key":  winner_key,
    })

    # NOTE: Do NOT call broadcast_unified — same reason as _battle_member_vs_npc.



# ── REST endpoints ────────────────────────────────────────────────────────────

@router.post("/colosseum/join")
async def colosseum_join(request: Request) -> JSONResponse:
    """Join the Colosseum. Registers the user's pet as an active participant."""
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    user_id = str(user["id"])
    pet = await user_data_manager.get_pet_data_async(user_id)
    if not pet:
        raise HTTPException(status_code=400, detail="You need a pet to join the Colosseum")

    await _ensure_db()

    from Systems.Functions.discord_utils import get_discord_avatar_url
    avatar_url = get_discord_avatar_url(user_id, user.get("avatar") or "", size=64)

    # Check if user has existing colosseum stats (rejoining)
    existing_member = await _get_member(user_id)
    
    # Preserve all-time stats if rejoining, otherwise start fresh
    member_data = {
        "user_id":          user_id,
        "username":         user.get("username", "Unknown"),
        "pet_name":         pet.get("name", "Unknown"),
        "pet_species":      pet.get("species", ""),
        "pet_element":      pet.get("element", "basic"),
        "pet_element2":     pet.get("element2", "") or "",
        "pet_type":         pet.get("category", "land"),
        "pet_level":        int(pet.get("level", 1)),
        "joined_at":        time.time(),
        "avatar":           avatar_url,
    }
    
    # If rejoining, preserve wins/losses/rounds from previous sessions
    if existing_member:
        member_data["wins"]   = existing_member.get("wins", 0)
        member_data["losses"] = existing_member.get("losses", 0)
        member_data["rounds"] = existing_member.get("rounds", 0)
        # Note: pending rewards are intentionally NOT preserved (they were lost on leave)
    
    await _upsert_member(user_id, member_data)

    # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
    queue = EventQueue()
    queue.push("colosseum_join", {"user_id": user_id, "pet_name": pet.get("name", "Unknown")})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("colosseum_join", 400)

    # Task tracking — colosseum (fires each time the user joins/rejoins)
    try:
        from web.api.tasks_api import record_action as _task_record
        await _task_record(user_id, "colosseum")
    except Exception:
        pass

    logger.info("[Colosseum] %s joined", user_id)
    return JSONResponse({"success": True, "message": "You have entered the Colosseum!", "animation": animation})


@router.post("/colosseum/leave")
async def colosseum_leave(request: Request) -> JSONResponse:
    """
    Leave the Colosseum. Pending rewards are forfeited, but all-time stats
    (wins/losses/rounds) are preserved in the DB for when the user rejoins.
    """
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    user_id = str(user["id"])
    await _ensure_db()

    # Instead of deleting, we mark as inactive by clearing pending rewards
    # and setting last_battle to 0 (so they won't be matched in battles)
    member = await _get_member(user_id)
    if member:
        await _upsert_member(user_id, {
            "user_id":          user_id,
            "pending_xp":       0,
            "pending_keys":     "[]",
            "pending_potions":  "[]",
            "last_battle":      0,  # Mark as inactive
            "joined_at":        0,  # Mark as not currently joined
        })

    # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
    queue = EventQueue()
    queue.push("colosseum_leave", {"user_id": user_id})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("colosseum_leave", 300)

    return JSONResponse({"success": True, "message": "You have left the Colosseum.", "animation": animation})


@router.get("/colosseum/state")
async def colosseum_state(request: Request) -> JSONResponse:
    """
    Return full Colosseum state:
    - members list (all active participants with stats)
    - recent round log
    - current user's membership + pending rewards
    - next battle countdown
    - lifetime colosseum stats from the pet's battle_stats (always available)
    """
    user = request.session.get("discord_user")
    user_id = str(user["id"]) if user else None

    await _ensure_db()

    members  = await _get_all_members()
    log      = await _get_recent_log(25)
    my_data  = None
    lifetime = None

    if user_id:
        my_data = await _get_member(user_id)
        if my_data:
            my_data["badge_url"] = _colo_selected_badge_url(user_id) or None
        # Always fetch lifetime stats from pets DB so they show even after leaving
        try:
            pet = await user_data_manager.get_pet_data_async(user_id)
            if pet:
                col = pet.get("battle_stats", {}).get("colosseum", {})
                lifetime = {
                    "wins":       int(col.get("wins",       0)),
                    "losses":     int(col.get("losses",     0)),
                    "rounds":     int(col.get("rounds",     0)),
                    "xp_earned":  int(col.get("xp_earned",  0)),
                }
        except Exception:
            pass

    # Enrich each member with badge_url
    for m in members:
        m["badge_url"] = _colo_selected_badge_url(m["user_id"]) or None

    # Next battle countdown
    try:
        last_ts = float(await _get_meta("last_battle_ts", "0"))
    except Exception:
        last_ts = 0.0
    next_battle_in = max(0, int(BATTLE_INTERVAL_SECS - (time.time() - last_ts)))

    round_num = int(await _get_meta("round_counter", "0"))

    return JSONResponse({
        "members":        members,
        "log":            log,
        "my_data":        my_data,
        "lifetime":       lifetime,
        "next_battle_in": next_battle_in,
        "round_num":      round_num,
        "member_count":   len(members),
    })


@router.post("/colosseum/claim")
async def colosseum_claim(request: Request) -> JSONResponse:
    """
    Claim all pending Colosseum rewards (XP + keys) and apply them to the pet.
    Moves pending_xp from colosseum.db into the pet's actual XP via LootCalculator.
    """
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    user_id = str(user["id"])
    await _ensure_db()

    member = await _get_member(user_id)
    if not member:
        raise HTTPException(status_code=400, detail="You are not in the Colosseum")

    pending_xp      = int(member.get("pending_xp", 0))
    pending_keys    = json.loads(member.get("pending_keys",    "[]") or "[]")
    pending_potions = json.loads(member.get("pending_potions", "[]") or "[]")

    if pending_xp == 0 and not pending_keys and not pending_potions:
        return JSONResponse({"success": True, "message": "No rewards to claim yet.", "xp_claimed": 0})

    # ── Apply XP to pet via LootCalculator (handles level-ups, xp_sources, etc.)
    level_change = None
    if pending_xp > 0:
        from Systems.Pets.Logic.loot_calculator import LootCalculator
        _, level_change = await LootCalculator.apply_xp_change(int(user_id), pending_xp, "colosseum")

    # ── Apply keys + potions to pet inventory ─────────────────────────────────
    keys_claimed    = []
    potions_claimed = []
    if pending_keys or pending_potions:
        pet = await user_data_manager.get_pet_data_async(user_id)
        if pet:
            inventory = pet.get("inventory", [])

            for key_name in pending_keys:
                existing = next((i for i in inventory if i.get("name") == key_name), None)
                if existing:
                    existing["count"] = min(99, existing.get("count", 0) + 1)
                else:
                    inventory.append({"name": key_name, "type": "Key", "rarity": "Rare", "count": 1})
                keys_claimed.append(key_name)

            for potion_name in pending_potions:
                existing = next((i for i in inventory if i.get("name") == potion_name), None)
                if existing:
                    existing["count"] = min(99, existing.get("count", 0) + 1)
                else:
                    inventory.append({"name": potion_name, "type": "Potion", "rarity": "Common", "count": 1})
                potions_claimed.append(potion_name)

            pet["inventory"] = inventory
            await user_data_manager.save_pet_data(user_id, pet)

    # ── Clear pending rewards in colosseum DB ─────────────────────────────────
    await _upsert_member(user_id, {
        "user_id":          user_id,
        "pending_xp":       0,
        "pending_keys":     "[]",
        "pending_potions":  "[]",
    })

    # ── Sync authoritative colosseum totals → pets DB (pending_xp now 0) ─────
    # Re-fetch member to get the latest wins/losses/rounds after clearing pending
    fresh_member = await _get_member(user_id)
    if fresh_member:
        await _sync_colosseum_stats_to_pet(user_id, fresh_member)

    msg_parts = []
    if pending_xp > 0:
        msg_parts.append(f"+{pending_xp:,} XP")
    if keys_claimed:
        msg_parts.append(", ".join(keys_claimed))
    if potions_claimed:
        msg_parts.append(", ".join(potions_claimed))

    # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
    queue = EventQueue()
    queue.push("colosseum_claim", {"user_id": user_id, "xp_claimed": pending_xp, "keys_claimed": len(keys_claimed), "potions_claimed": len(potions_claimed)})
    await queue.flush()

    # Build items list for animation
    items = []
    if pending_xp > 0:
        items.append({"name": f"{pending_xp} XP", "rarity": "Common"})
    for key in keys_claimed:
        items.append({"name": key, "rarity": "Uncommon"})
    for potion in potions_claimed:
        items.append({"name": potion, "rarity": "Rare"})
    animation = AnimationComponent.for_loot(items)

    return JSONResponse({
        "success":         True,
        "message":         "Rewards claimed: " + " | ".join(msg_parts) if msg_parts else "Claimed!",
        "animation": animation,
        "xp_claimed":      pending_xp,
        "keys_claimed":    keys_claimed,
        "potions_claimed": potions_claimed,
        "level_change":    level_change,
    })


@router.post("/colosseum/sync_pet")
async def colosseum_sync_pet(request: Request) -> JSONResponse:
    """
    Sync the user's current pet stats into the Colosseum member record.
    Also syncs colosseum DB totals back into the pet's battle_stats.
    Call this after equipping items or levelling up.
    """
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    user_id = str(user["id"])
    await _ensure_db()

    member = await _get_member(user_id)
    if not member:
        raise HTTPException(status_code=400, detail="You are not in the Colosseum")

    pet = await user_data_manager.get_pet_data_async(user_id)
    if not pet:
        raise HTTPException(status_code=400, detail="No pet found")

    # Update colosseum member record with latest pet info
    await _upsert_member(user_id, {
        "user_id":      user_id,
        "pet_name":     pet.get("name", "Unknown"),
        "pet_species":  pet.get("species", ""),
        "pet_element":  pet.get("element", "basic"),
        "pet_element2": pet.get("element2", "") or "",
        "pet_type":     pet.get("category", "land"),
        "pet_level":    int(pet.get("level", 1)),
    })

    # Also sync colosseum totals → pets DB
    await _sync_colosseum_stats_to_pet(user_id, member)

    # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
    queue = EventQueue()
    queue.push("colosseum_sync_pet", {"user_id": user_id})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("stats_synced", 300)

    return JSONResponse({"success": True, "animation": animation})


@router.post("/colosseum/sync_stats")
async def colosseum_sync_stats(request: Request) -> JSONResponse:
    """
    Authoritative one-way sync: reads this user's colosseum DB record and
    writes the wins/losses/rounds/xp_earned totals into their pet's
    battle_stats.colosseum in the pets DB.

    Safe to call at any time — idempotent.  Useful for backfilling after
    a server restart or if the pets DB drifted out of sync.
    """
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    user_id = str(user["id"])
    await _ensure_db()

    member = await _get_member(user_id)
    if not member:
        return JSONResponse({"success": False, "message": "Not in Colosseum"})

    await _sync_colosseum_stats_to_pet(user_id, member)

    # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
    queue = EventQueue()
    queue.push("colosseum_sync_stats", {"user_id": user_id})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("stats_synced", 300)

    return JSONResponse({
        "success": True,
        "synced": {
            "wins":    member.get("wins",   0),
            "losses":  member.get("losses", 0),
            "rounds":  member.get("rounds", 0),
        },
        "animation": animation
    })


# ── Startup helper ────────────────────────────────────────────────────────────
async def start_colosseum_loop() -> None:
    """Start the hourly battle loop. Called from web_server startup_event."""
    global _loop_task
    await _ensure_db()

    # On every startup, sync all existing colosseum members → pets DB so the
    # pets DB is never stale after a server restart.
    try:
        members = await _get_all_members()
        for m in members:
            await _sync_colosseum_stats_to_pet(m["user_id"], m)
        if members:
            logger.info("[Colosseum] Startup sync: pushed stats for %d member(s) to pets DB", len(members))
    except Exception as e:
        logger.warning("[Colosseum] Startup sync failed: %s", e)

    if _loop_task is None or _loop_task.done():
        _loop_task = asyncio.create_task(_run_hourly_battles())
        logger.info("[Colosseum] Hourly battle loop started")
