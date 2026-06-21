from __future__ import annotations

import json
import logging
import hashlib
import os
import random
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from Systems.Functions.db_paths import GLOBAL_NATIONS_DB as AUTOCOMPLETE_GLOBAL_NATIONS_DB

logger = logging.getLogger("Reaper.WouldYouRatherAPI")
router = APIRouter()

ROOT_DIR = Path(__file__).resolve().parents[2]
DB_PATH = str(ROOT_DIR / "Databases" / "fun.db")
_DB_READY = False
DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "would_you_rather"
POOL_FILES = {
    "weirdness": DATA_DIR / "weirdness.json",
    "moral": DATA_DIR / "moral.json",
}
_POOL_CACHE: Dict[str, List[Dict[str, Any]]] = {}
_ALLIANCE_CACHE: List[str] = []

PNW_WAR_TYPES = (
    "ordinary war",
    "attrition war",
    "raid war",
)

PNW_SPY_TYPES = (
    "Soldiers",
    "Tanks",
    "Aircraft",
    "Ships",
    "Missiles",
    "Nukes",
)

PNW_CONTROL_TYPES = (
    "Ground Control",
    "Air Superiority",
    "Blockade",
)

PNW_TREATY_TYPES = (
    "MDP",
    "MDoAP",
    "ODP",
    "ODoAP",
    "Protectorate",
    "NAP",
    "PIAT",
    "Extension",
)

PNW_ACTION_TEMPLATES = (
    "nuke {alliance}",
    "missile {alliance}",
    "spy {alliance}",
    "raid {alliance}",
    "counter {alliance}",
    "declare {war_type} on {alliance}",
    "blockade {alliance}",
    "airstrike {alliance}",
    "ground attack {alliance}",
    "naval attack {alliance}",
    "loot bank of {alliance}",
    "raid offshore of{alliance}",
    "beige cycle {alliance}",
    "target high-infra nations in {alliance}",
    "target low-infra nations in {alliance}",
    "target low-military nations in {alliance}",
    "target high-military nations in {alliance}",
    "spy {spy_type} from {alliance}",
    "break {control_type} from {alliance}",
    "force peace with {alliance}",
    "sign {treaty_article} {treaty_type} treaty with {alliance}",
    "break {treaty_article} {treaty_type} treaty with {alliance}",
    "upgrade {treaty_article} {treaty_type} treaty with {alliance}",
    "honor {treaty_article} {treaty_type} treaty call from {alliance}",
    "cancel {treaty_article} {treaty_type} treaty with {alliance}",
    "protect {alliance} from counters",
    "bankroll rebuild grants for {alliance}",
    "move offshore resources away from {alliance}",
    "join a coalition wave against {alliance}",
    "lead peace talks with {alliance}",
    "deny peace to {alliance}",
    "post raid targets from {alliance}",
    "assign counters against {alliance}",
    "focus net damage on {alliance}",
    "focus loot raids on {alliance}",
    "watch war stats for {alliance}",
    "pressure treaty partners of {alliance}",
)

MORAL_TERMS = (
    "truth", "lie", "harm", "hurt", "help", "save", "forgive", "apologize", "moral", "safest", "bravest", "justice",
    "mercy", "promise", "blame", "rule", "corruption", "feelings", "sacrifice",
    "betrayal", "dignity", "fair", "unfair", "reputation", "silent", "consequences",
    "trust", "privacy", "secret", "mistake", "law", "honest", "family", "stability",
    "support", "loyalty", "compassion", "punishment", "fear", "good", "scarce", "aid", "disaster", "resources", "suffering",
    "reward", "effort", "results", "failed", "cheating", "scholarship", "loss", "consent", "autonomy", "responsibility",
    "community", "safety", "unsafe", "safer", "kindness", "accountability", "forgiveness", "need",
    "deserve", "protect", "risk", "money", "cash", "bill", "urgent", "power", "weak", "vulnerable", "equal",
    "bias", "disability", "access", "respect", "harmful", "innocent", "guilty", "public", "private", "duty",
    "care", "fairness", "freedom", "guilt", "second chance", "medicine", "patient",
    "triage", "medical", "victim", "whistleblower", "charity", "donor", "confidential",
    "transparent", "transparency", "repair", "restitution", "credit", "debt",
)
PNW_TERMS = (
    "infra", "commerce", "project", "projects", "loot", "beige", "air superiority",
    "ground control", "air control", "spy", "spies", "nuke", "nukes", "missile",
    "missiles", "warchest", "bloc", "global", "declare", "counter", "resistance",
    "damage",
    "score", "munitions", "gasoline", "steel", "aluminum", "food", "coal", "oil",
    "uranium", "credits", "city", "cities", "raid", "raider", "alliance war",
    "war", "military", "airstrikes", "ground attacks", "tanks", "aircraft", "bank",
    "rebuild", "rebuilds", "resources", "resource prices", "peace", "conventional",
    "barracks", "soldier", "soldiers", "factory", "factories", "tank", "ship", "ships",
    "naval", "nation", "nations", "land", "improvement", "improvements", "slots",
    "power", "wind", "nuclear", "lead", "iron", "bauxite", "cash", "pollution",
    "recycling", "manufacturing", "turn", "turns", "day", "week", "revenue", "income",
    "upkeep", "consumption", "attack", "attacks", "planes", "dogfight", "dogfights",
    "enemy", "hangar", "drydock", "attrition", "raids", "counters", "defensive slots",
    "offensive slots", "map", "maps", "target", "targets", "timing", "fortify", "market", "tax", "color bonus",
    "immense triumph", "moderate success", "pyrrhic victory", "victory",
    "treaty", "treaties", "defense pact", "defense pacts", "fa", "protectorate",
    "mdp", "odp", "applicant", "applicants", "inactive", "vacation mode",
    "alliance", "alliance comparison", "full mill", "full military", "treaty universe",
    "news", "news feed", "watch dashboard", "war stats", "goals", "build plan",
    "color", "population", "recruitment", "diplomatic", "policy", "opponent", "opponents",
    "unit kills", "member activity", "resource security",
)

QUESTION_TYPES: Dict[str, Dict[str, str]] = {
    "weirdness": {
        "label": "Insanity",
        "tone": "absurd, playful, strange, and safe for Discord",
    },
    "moral": {
        "label": "Crossroads",
        "tone": "legitimate ethical tradeoffs with no obvious perfect answer",
    },
    "pnw": {
        "label": "PnW Choas",
        "tone": "real Politics & War strategy choices using actual game concepts",
    },
}


class WouldYouRatherVote(BaseModel):
    question_id: str = Field(..., min_length=3, max_length=140)
    choice_index: int = Field(..., ge=0, le=1)


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:30] or "question"


def _theme_valid(qtype: str, question: str, choice_a: str, choice_b: str) -> bool:
    text = f"{question} {choice_a} {choice_b}".lower()
    if qtype == "moral":
        return any(term in text for term in MORAL_TERMS)
    if qtype == "pnw":
        matched_terms = {term for term in PNW_TERMS if term in text}
        return bool(matched_terms)
    return True


def _load_alliance_names() -> List[str]:
    global _ALLIANCE_CACHE
    if _ALLIANCE_CACHE:
        return _ALLIANCE_CACHE

    try:
        with sqlite3.connect(AUTOCOMPLETE_GLOBAL_NATIONS_DB) as con:
            rows = con.execute(
                """
                SELECT alliance_id, alliance_name, COUNT(*) AS member_count
                FROM nations
                WHERE alliance_id IS NOT NULL
                  AND alliance_id != 0
                  AND nation_name IS NOT NULL
                  AND nation_name != ''
                GROUP BY alliance_id
                ORDER BY member_count DESC
                """
            ).fetchall()
        names = [str(row[1]).strip() for row in rows if row[1] is not None and str(row[1]).strip()]
    except Exception as e:
        logger.warning(f"Could not load PnW alliances from autocomplete source {AUTOCOMPLETE_GLOBAL_NATIONS_DB}: {e}")
        names = []

    _ALLIANCE_CACHE = names or [
        "Rose",
        "Singularity",
        "The Knights Radiant",
        "Eclipse",
        "The Syndicate",
        "Guardian",
        "The Fighting Pacifists",
        "Grumpy Old Bastards",
    ]
    return _ALLIANCE_CACHE


def _load_treaty_types() -> List[str]:
    return list(PNW_TREATY_TYPES)


def _article_for(value: str) -> str:
    word = value.strip()
    if not word:
        return "a"
    first = word[0].lower()
    if first in "aeiou":
        return "an"
    if first.upper() in {"A", "E", "F", "H", "I", "L", "M", "N", "O", "R", "S", "X"}:
        return "an"
    return "a"


def _format_pnw_action(template: str, alliance: str, rng: random.Random) -> str:
    treaty_type = rng.choice(_load_treaty_types())
    return template.format(
        alliance=alliance,
        war_type=rng.choice(PNW_WAR_TYPES),
        spy_type=rng.choice(PNW_SPY_TYPES),
        control_type=rng.choice(PNW_CONTROL_TYPES),
        treaty_type=treaty_type,
        treaty_article=_article_for(treaty_type),
    )


def _make_pnw_daily_question(day: str) -> Dict[str, Any]:
    rng = random.Random(f"wyr:pnw-daily-action:{day}")
    alliances = _load_alliance_names()
    alliance_a, alliance_b = rng.sample(alliances, 2) if len(alliances) >= 2 else (alliances[0], alliances[0])
    template_a, template_b = rng.sample(PNW_ACTION_TEMPLATES, 2)
    choice_a = _format_pnw_action(template_a, alliance_a, rng)
    choice_b = _format_pnw_action(template_b, alliance_b, rng)
    question = f"Would you rather {choice_a}, or {choice_b}?"
    return _make_question(day, "pnw", question, choice_a, choice_b)


async def _ensure_db() -> None:
    global _DB_READY
    if _DB_READY:
        return

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=MEMORY")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS wyr_daily_sets (
                day TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS wyr_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day TEXT NOT NULL,
                question_id TEXT NOT NULL,
                user_key TEXT NOT NULL,
                voter_name TEXT NOT NULL DEFAULT 'Anonymous Visitor',
                choice_index INTEGER NOT NULL,
                voted_at TEXT NOT NULL,
                UNIQUE(day, question_id, user_key)
            )
        """)
        try:
            await db.execute("ALTER TABLE wyr_votes ADD COLUMN voter_name TEXT NOT NULL DEFAULT 'Anonymous Visitor'")
        except Exception:
            pass
        await db.commit()
    _DB_READY = True


def _make_question(day: str, qtype: str, question: str, choice_a: str, choice_b: str) -> Dict[str, Any]:
    return {
        "id": f"{day}-{qtype}-{_slug(question)}",
        "type": qtype,
        "label": QUESTION_TYPES[qtype]["label"],
        "question": question.strip(),
        "choices": [
            {"index": 0, "text": choice_a.strip()},
            {"index": 1, "text": choice_b.strip()},
        ],
    }


def _load_pool(qtype: str) -> List[Dict[str, Any]]:
    if qtype in _POOL_CACHE:
        return _POOL_CACHE[qtype]

    path = POOL_FILES[qtype]
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Could not load Would You Rather pool {path}: {e}", exc_info=True)
        raw = []

    valid: List[Dict[str, Any]] = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question", "")).strip()
        choices = item.get("choices")
        if not isinstance(choices, list) or len(choices) != 2:
            continue
        choice_a_raw = choices[0].get("text") if isinstance(choices[0], dict) else choices[0]
        choice_b_raw = choices[1].get("text") if isinstance(choices[1], dict) else choices[1]
        choice_a = str(choice_a_raw).strip()
        choice_b = str(choice_b_raw).strip()
        question_lower = question.lower()
        if not question.startswith("Would you rather ") or not question.endswith("?"):
            continue
        if choice_a.lower() not in question_lower or choice_b.lower() not in question_lower:
            continue
        if choice_a.lower() == choice_b.lower():
            continue
        if not _theme_valid(qtype, question, choice_a, choice_b):
            continue
        if question_lower in seen:
            continue
        seen.add(question_lower)
        valid.append({"question": question, "choices": [choice_a, choice_b]})

    if len(valid) < 500:
        logger.warning(f"Would You Rather pool '{qtype}' has only {len(valid)} valid entries; expected at least 500.")

    _POOL_CACHE[qtype] = valid
    return valid


def _fallback_daily(day: str) -> List[Dict[str, Any]]:
    rng = random.Random(f"wyr:{day}")
    questions = []
    for qtype in ("weirdness", "moral"):
        pool = _load_pool(qtype)
        if not pool:
            raise RuntimeError(f"Would You Rather pool '{qtype}' is empty or invalid.")
        item = rng.choice(pool)
        questions.append(_make_question(day, qtype, item["question"], item["choices"][0], item["choices"][1]))
    questions.append(_make_pnw_daily_question(day))
    return questions


def _validate_questions(day: str, raw: Optional[dict]) -> Optional[List[Dict[str, Any]]]:
    if not raw or not isinstance(raw.get("questions"), list):
        return None

    by_type: Dict[str, Dict[str, Any]] = {}
    for item in raw["questions"]:
        if not isinstance(item, dict):
            continue
        qtype = str(item.get("type", "")).strip().lower()
        if qtype not in QUESTION_TYPES or qtype in by_type:
            continue
        question = str(item.get("question", "")).strip()
        choices = item.get("choices")
        if not question.endswith("?"):
            question += "?"
        if not isinstance(choices, list) or len(choices) != 2:
            continue
        choice_a_raw = choices[0].get("text") if isinstance(choices[0], dict) else choices[0]
        choice_b_raw = choices[1].get("text") if isinstance(choices[1], dict) else choices[1]
        choice_a = str(choice_a_raw).strip()
        choice_b = str(choice_b_raw).strip()
        if len(question) < 24 or len(choice_a) < 3 or len(choice_b) < 3 or choice_a.lower() == choice_b.lower():
            continue
        if choice_a.lower() not in question.lower() or choice_b.lower() not in question.lower():
            continue
        if not _theme_valid(qtype, question, choice_a, choice_b):
            continue
        by_type[qtype] = _make_question(day, qtype, question, choice_a, choice_b)

    if set(by_type) != set(QUESTION_TYPES):
        return None
    return [by_type["weirdness"], by_type["moral"], by_type["pnw"]]


async def _load_daily(day: str) -> Optional[Dict[str, Any]]:
    await _ensure_db()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=MEMORY")
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT payload, source, created_at FROM wyr_daily_sets WHERE day=?", (day,)) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        questions = json.loads(row["payload"])
        if row["source"] != "json":
            logger.warning(f"Rejecting old Would You Rather source '{row['source']}' for {day}")
            return None
        validated_questions = _validate_questions(day, {"questions": questions})
        if not validated_questions:
            logger.warning(f"Rejecting invalid cached Would You Rather set for {day}")
            return None
        return {
            "day": day,
            "source": row["source"],
            "created_at": row["created_at"],
            "questions": validated_questions,
        }


async def _save_daily(day: str, questions: List[Dict[str, Any]], source: str) -> Dict[str, Any]:
    created_at = datetime.now(timezone.utc).isoformat()
    await _ensure_db()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=MEMORY")
        await db.execute(
            "INSERT OR REPLACE INTO wyr_daily_sets(day, payload, source, created_at) VALUES (?, ?, ?, ?)",
            (day, json.dumps(questions), source, created_at),
        )
        await db.commit()
    return {"day": day, "source": source, "created_at": created_at, "questions": questions}


async def _get_or_create_daily(day: str) -> Dict[str, Any]:
    existing = await _load_daily(day)
    if existing:
        return existing

    return await _save_daily(day, _fallback_daily(day), "json")


def get_wyr_type_choices() -> List[Dict[str, str]]:
    return [{"name": meta["label"], "value": qtype} for qtype, meta in QUESTION_TYPES.items()]


async def get_daily_wyr_state(user_key: str, day: Optional[str] = None) -> Dict[str, Any]:
    current_day = day or _utc_today()
    daily = await _get_or_create_daily(current_day)
    votes = await _vote_summary(current_day, daily["questions"], user_key)
    return {
        "day": daily["day"],
        "source": daily["source"],
        "created_at": daily["created_at"],
        "questions": daily["questions"],
        "votes": votes,
    }


async def get_daily_wyr_question(qtype: str, user_key: str, day: Optional[str] = None) -> Dict[str, Any]:
    state = await get_daily_wyr_state(user_key, day)
    question = next((q for q in state["questions"] if q.get("type") == qtype), None)
    if not question:
        raise ValueError(f"Unknown Would You Rather type: {qtype}")
    return {"day": state["day"], "question": question, "votes": state["votes"].get(question["id"])}


async def vote_daily_wyr(
    question_id: str,
    choice_index: int,
    user_key: str,
    voter_name: str,
    day: Optional[str] = None,
) -> Dict[str, Any]:
    current_day = day or _utc_today()
    daily = await _get_or_create_daily(current_day)
    question_by_id = {q["id"]: q for q in daily["questions"]}
    question = question_by_id.get(question_id)
    if not question:
        raise ValueError("Invalid daily question.")
    if choice_index not in (0, 1):
        raise ValueError("Invalid choice.")

    now = datetime.now(timezone.utc).isoformat()
    await _ensure_db()
    is_new_answer = False
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=MEMORY")
        async with db.execute(
            "SELECT 1 FROM wyr_votes WHERE day=? AND question_id=? AND user_key=?",
            (current_day, question_id, user_key),
        ) as cur:
            is_new_answer = await cur.fetchone() is None
        await db.execute(
            """
            INSERT INTO wyr_votes(day, question_id, user_key, voter_name, choice_index, voted_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(day, question_id, user_key)
            DO UPDATE SET voter_name=excluded.voter_name, choice_index=excluded.choice_index, voted_at=excluded.voted_at
            """,
            (current_day, question_id, user_key, voter_name[:80], choice_index, now),
        )
        await db.commit()

    if is_new_answer and user_key.startswith("discord:"):
        user_id = user_key.split(":", 1)[1]
        action = {
            "weirdness": "wyr_weirdness",
            "moral": "wyr_moral",
            "pnw": "wyr_pnw",
        }.get(question.get("type"))
        if user_id and action:
            try:
                from web.api.tasks_api import record_action
                await record_action(user_id, action)
            except Exception as e:
                logger.debug(f"Would You Rather task progress failed for {user_id}/{action}: {e}")

    votes = await _vote_summary(current_day, daily["questions"], user_key)
    return {"day": current_day, "question": question, "votes": votes}


def _user_identity(request: Request) -> tuple[str, str]:
    user = request.session.get("discord_user")
    if user and user.get("id"):
        display_name = (
            user.get("global_name")
            or user.get("username")
            or user.get("name")
            or f"Discord User {user['id']}"
        )
        return f"discord:{user['id']}", str(display_name)[:80]
    forwarded_for = request.headers.get("x-forwarded-for", "")
    user_agent = request.headers.get("user-agent", "")
    client_host = request.client.host if request.client else ""
    fingerprint = hashlib.sha256(f"{forwarded_for}|{client_host}|{user_agent}".encode("utf-8")).hexdigest()[:24]
    return f"anon:{fingerprint}", "Anonymous Visitor"


async def _vote_summary(day: str, questions: List[Dict[str, Any]], user_key: str) -> Dict[str, Any]:
    await _ensure_db()
    question_ids = [q["id"] for q in questions]
    counts = {qid: [0, 0] for qid in question_ids}
    user_votes: Dict[str, int] = {}
    voter_rows: Dict[str, List[Dict[str, Any]]] = {qid: [] for qid in question_ids}

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=MEMORY")
        async with db.execute(
            "SELECT question_id, choice_index, COUNT(*) FROM wyr_votes WHERE day=? GROUP BY question_id, choice_index",
            (day,),
        ) as cur:
            async for question_id, choice_index, total in cur:
                if question_id in counts and choice_index in (0, 1):
                    counts[question_id][choice_index] = total

        async with db.execute(
            "SELECT question_id, choice_index FROM wyr_votes WHERE day=? AND user_key=?",
            (day, user_key),
        ) as cur:
            async for question_id, choice_index in cur:
                user_votes[question_id] = choice_index

        async with db.execute(
            "SELECT question_id, choice_index, voter_name FROM wyr_votes WHERE day=? ORDER BY voted_at ASC",
            (day,),
        ) as cur:
            async for question_id, choice_index, voter_name in cur:
                if question_id in voter_rows and choice_index in (0, 1):
                    voter_rows[question_id].append({
                        "choice_index": choice_index,
                        "name": voter_name or "Anonymous Visitor",
                    })

    summary: Dict[str, Any] = {}
    for question_id, pair in counts.items():
        total = pair[0] + pair[1]
        user_choice = user_votes.get(question_id)
        summary[question_id] = {
            "counts": pair,
            "total": total,
            "percents": [
                round((pair[0] / total) * 100, 1) if total else 0,
                round((pair[1] / total) * 100, 1) if total else 0,
            ],
            "user_choice": user_choice,
            "voters": voter_rows[question_id] if user_choice is not None else [],
        }
    return summary


@router.get("/would-you-rather/daily")
async def get_daily_would_you_rather(request: Request):
    user_key, _ = _user_identity(request)
    return JSONResponse(await get_daily_wyr_state(user_key))


@router.post("/would-you-rather/vote")
async def vote_would_you_rather(request: Request, vote: WouldYouRatherVote):
    user_key, voter_name = _user_identity(request)
    try:
        result = await vote_daily_wyr(vote.question_id, vote.choice_index, user_key, voter_name)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"day": result["day"], "votes": result["votes"]})
