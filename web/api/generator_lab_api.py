# Standard Library Imports
import logging
import random
import re
from typing import Any, Dict, List, Optional

# Third-Party Imports
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("Reaper.GeneratorLabAPI")
router = APIRouter()


class GeneratorLabRequest(BaseModel):
    category: str = Field(..., min_length=1, max_length=40)
    description: str = Field("", max_length=1200)
    count: int = Field(6, ge=1, le=12)


CATEGORY_CONFIG: Dict[str, Dict[str, Any]] = {
    "discord_username": {
        "label": "Discord Username",
        "prompt": "Generate Discord usernames. Keep them memorable, readable, and community-safe. Avoid discriminator numbers unless they add style.",
        "fallback_type": "names",
    },
    "pnw_nation_name": {
        "label": "PnW Nation Name",
        "prompt": "Generate Politics & War nation names. Make them sound like plausible countries, city-states, republics, kingdoms, or empires.",
        "fallback_type": "nations",
    },
    "pnw_leader_name": {
        "label": "PnW Leader Name",
        "prompt": "Generate Politics & War leader names. Make them suitable for rulers, diplomats, generals, presidents, monarchs, or ministers.",
        "fallback_type": "leaders",
    },
    "pets": {
        "label": "Pets",
        "prompt": "Generate pet concepts. Each result must include a pet name, attack name, defend name, and charge name.",
        "fallback_type": "pets",
    },
    "villain_name": {
        "label": "Villain Name",
        "prompt": "Generate villain names with dramatic flair. Keep them usable in games, roleplay, and Discord.",
        "fallback_type": "villains",
    },
    "hero_name": {
        "label": "Hero Name",
        "prompt": "Generate hero names with bold, memorable energy. Keep them usable in games, roleplay, and Discord.",
        "fallback_type": "heroes",
    },
    "compliment": {
        "label": "Compliment",
        "prompt": "Generate compliments. They should feel specific, warm, witty, and not generic.",
        "fallback_type": "compliments",
    },
    "roast": {
        "label": "Roast",
        "prompt": "Generate playful roasts. Keep them non-hateful, non-threatening, and suitable for a Discord bot.",
        "fallback_type": "roasts",
    },
    "fake_news_headline": {
        "label": "Fake News Headline",
        "prompt": "Generate fictional parody news headlines. They must be clearly fake, funny, and not presented as real news.",
        "fallback_type": "headlines",
    },
}


ADJECTIVES = [
    "Ashen", "Crimson", "Velvet", "Iron", "Neon", "Midnight", "Solar", "Frost",
    "Arcane", "Lucky", "Storm", "Obsidian", "Golden", "Quiet", "Wicked", "Nova",
]
NOUNS = [
    "Oracle", "Cipher", "Reaper", "Echo", "Vanguard", "Crown", "Signal", "Forge",
    "Comet", "Phantom", "Ledger", "Spark", "Citadel", "Warden", "Pulse", "Beacon",
]
PLACES = [
    "Asterfall", "Northreach", "Veloria", "Cindervale", "Ironhaven", "Moonspire",
    "Ravenmark", "Solmora", "Duskwick", "Ebonreach", "Starford", "Halcyra",
]
TITLES = [
    "Chancellor", "Archon", "Marshal", "Sovereign", "Director", "Minister",
    "Commander", "Consul", "Warden", "High Steward", "Prime Envoy", "Regent",
]


def _clean_description(description: str) -> str:
    cleaned = re.sub(r"\s+", " ", description or "").strip()
    return cleaned[:1200]


def _dedupe(items: List[Any]) -> List[Any]:
    seen = set()
    unique = []
    for item in items:
        key = repr(item).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _description_words(description: str) -> List[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", description)
    return [word[:18] for word in words[:8]]


def _fallback_names(description: str, count: int) -> List[str]:
    hints = _description_words(description)
    pool = hints or NOUNS
    items = []
    for _ in range(count * 2):
        left = random.choice(ADJECTIVES + pool)
        right = random.choice(NOUNS + pool)
        style = random.choice([
            f"{left}{right}",
            f"{left}_{right}",
            f"{right}{random.randint(7, 999)}",
            f"{left}.{right}",
        ])
        items.append(style)
    return _dedupe(items)[:count]


def _fallback_nations(description: str, count: int) -> List[str]:
    hints = _description_words(description)
    cores = hints or PLACES
    forms = ["Republic of {0}", "{0} Dominion", "Kingdom of {0}", "{0} Federation", "Free State of {0}", "{0} Union"]
    return _dedupe([random.choice(forms).format(random.choice(cores + PLACES)) for _ in range(count * 2)])[:count]


def _fallback_leaders(description: str, count: int) -> List[str]:
    surnames = _description_words(description) or PLACES
    firsts = ["Kael", "Mira", "Dorian", "Selene", "Voss", "Ari", "Cassian", "Nyra", "Rowan", "Thane"]
    return _dedupe([f"{random.choice(TITLES)} {random.choice(firsts)} {random.choice(surnames)}" for _ in range(count * 2)])[:count]


def _fallback_pets(description: str, count: int) -> List[Dict[str, str]]:
    hints = _description_words(description)
    bases = hints or ["Ember", "Bolt", "Shade", "Mochi", "Rook", "Nova", "Pip", "Rune"]
    attacks = ["Meteor Chomp", "Static Swipe", "Moonbite", "Cinder Claw", "Echo Pounce", "Starfang"]
    defends = ["Shell Ward", "Velvet Guard", "Iron Curl", "Mist Screen", "Lucky Brace", "Aegis Nap"]
    charges = ["Comet Rush", "Thunder Zoom", "Reaper Sprint", "Solar Dash", "Chaos Scoot", "Nova Burst"]
    pets = []
    for _ in range(count * 2):
        base = random.choice(bases)
        pets.append({
            "pet_name": f"{base} {random.choice(['Paws', 'Whisk', 'Fang', 'Bean', 'Spark', 'Shade'])}",
            "attack_name": random.choice(attacks),
            "defend_name": random.choice(defends),
            "charge_name": random.choice(charges),
        })
    return _dedupe(pets)[:count]


def _fallback_villains(description: str, count: int) -> List[str]:
    hints = _description_words(description)
    cores = hints or NOUNS
    patterns = ["The {0} Tyrant", "Lord {0}", "{0} the Unmade", "Doctor {0}", "The Crimson {0}", "{0} Prime"]
    return _dedupe([random.choice(patterns).format(random.choice(cores + NOUNS)) for _ in range(count * 2)])[:count]


def _fallback_heroes(description: str, count: int) -> List[str]:
    hints = _description_words(description)
    cores = hints or NOUNS
    patterns = ["Captain {0}", "The {0} Sentinel", "{0}heart", "Solar {0}", "{0} Ranger", "The Iron {0}"]
    return _dedupe([random.choice(patterns).format(random.choice(cores + NOUNS)) for _ in range(count * 2)])[:count]


def _fallback_compliments(description: str, count: int) -> List[str]:
    subject = description.strip() or "you"
    templates = [
        "{0} has the kind of presence that makes a room feel more sorted out.",
        "{0} brings rare main-character competence without making a whole speech about it.",
        "{0} has excellent taste and suspiciously good timing.",
        "{0} makes difficult things look much less dramatic than they are.",
        "{0} is carrying an unreasonable amount of charm for one person.",
        "{0} has the energy of someone who reads the patch notes and still has fun.",
    ]
    return [template.format(subject[:80]) for template in templates[:count]]


def _fallback_roasts(description: str, count: int) -> List[str]:
    subject = description.strip() or "you"
    templates = [
        "{0} has the confidence of a loading screen at 99 percent.",
        "{0} plans like the calendar is optional DLC.",
        "{0} could lose a staring contest with a progress bar.",
        "{0} brings tutorial energy to ranked decisions.",
        "{0} is proof that vibes can pass inspection even when the paperwork cannot.",
        "{0} has a strategy, but it appears to be in beta.",
    ]
    return [template.format(subject[:80]) for template in templates[:count]]


def _fallback_headlines(description: str, count: int) -> List[str]:
    hints = _description_words(description)
    subject = " ".join(hints[:3]) if hints else "Local Discord Server"
    templates = [
        "{0} Declares Victory After Successfully Finding the Settings Menu",
        "Experts Confirm {0} Was Load-Bearing the Entire Time",
        "{0} Accidentally Invents New Meta While Looking for Snacks",
        "Council Shocked as {0} Makes One Reasonable Decision Before Midnight",
        "{0} Announces Bold Plan to Rename Everything Until It Works",
        "Breaking: {0} Seen Touching Grass, Sources Remain Skeptical",
    ]
    return [template.format(subject) for template in templates[:count]]


FALLBACKS = {
    "names": _fallback_names,
    "nations": _fallback_nations,
    "leaders": _fallback_leaders,
    "pets": _fallback_pets,
    "villains": _fallback_villains,
    "heroes": _fallback_heroes,
    "compliments": _fallback_compliments,
    "roasts": _fallback_roasts,
    "headlines": _fallback_headlines,
}


def _fallback_generate(category_key: str, description: str, count: int) -> List[Any]:
    config = CATEGORY_CONFIG[category_key]
    fallback = FALLBACKS[config["fallback_type"]]
    return fallback(description, count)


def _normalize_ai_items(category_key: str, data: Optional[dict], count: int) -> Optional[List[Any]]:
    if not data:
        return None

    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        return None

    items: List[Any] = []
    if category_key == "pets":
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            pet = {
                "pet_name": str(item.get("pet_name") or item.get("name") or "").strip(),
                "attack_name": str(item.get("attack_name") or item.get("attack") or "").strip(),
                "defend_name": str(item.get("defend_name") or item.get("defend") or "").strip(),
                "charge_name": str(item.get("charge_name") or item.get("charge") or "").strip(),
            }
            if all(pet.values()):
                items.append(pet)
    else:
        for item in raw_items:
            if isinstance(item, str) and item.strip():
                items.append(item.strip())
            elif isinstance(item, dict):
                text = str(item.get("text") or item.get("name") or item.get("headline") or "").strip()
                if text:
                    items.append(text)

    return _dedupe(items)[:count] or None


async def _ai_generate(category_key: str, description: str, count: int) -> Optional[List[Any]]:
    config = CATEGORY_CONFIG[category_key]
    try:
        from Systems.Functions.local_ai import chat_complete_json
    except Exception as e:
        logger.warning(f"Generator Lab AI import failed: {e}")
        return None

    if category_key == "pets":
        schema = (
            '{"items":[{"pet_name":"Name","attack_name":"Attack Move",'
            '"defend_name":"Defend Move","charge_name":"Charge Move"}]}'
        )
    else:
        schema = '{"items":["Result 1","Result 2"]}'

    prompt = (
        f"Category: {config['label']}\n"
        f"User description: {description or 'No extra description provided.'}\n"
        f"Count: {count}\n\n"
        f"{config['prompt']}\n"
        "Return only JSON matching this schema exactly:\n"
        f"{schema}"
    )

    try:
        data = await chat_complete_json(
            messages=[{"role": "user", "content": prompt}],
            system=(
                "You are Reaper's Random Generator Lab. Generate concise, original, "
                "Discord-safe results. Do not include slurs, targeted harassment, threats, "
                "real breaking-news claims, or markdown."
            ),
            temperature=0.9,
            max_tokens=700,
        )
    except Exception as e:
        logger.warning(f"Generator Lab AI request failed: {e}", exc_info=True)
        return None

    return _normalize_ai_items(category_key, data, count)


@router.get("/generator-lab/categories")
async def get_generator_categories():
    return JSONResponse(content={
        "categories": [
            {"key": key, "label": value["label"]}
            for key, value in CATEGORY_CONFIG.items()
        ]
    })


@router.post("/generator-lab/generate")
async def generate_lab_items(http_request: Request, request: GeneratorLabRequest):
    category_key = request.category.strip().lower()
    if category_key not in CATEGORY_CONFIG:
        return JSONResponse(
            content={"error": "Invalid generator category."},
            status_code=400,
        )

    description = _clean_description(request.description)
    ai_items = await _ai_generate(category_key, description, request.count)
    source = "ai" if ai_items else "fallback"
    items = ai_items or _fallback_generate(category_key, description, request.count)

    user = http_request.session.get("discord_user")
    user_id = str(user.get("id", "")) if user else ""
    if user_id:
        try:
            from web.api.tasks_api import record_action
            await record_action(user_id, "generator_lab")
        except Exception as e:
            logger.debug(f"Generator Lab task progress failed for {user_id}: {e}")

    return JSONResponse(content={
        "category": category_key,
        "label": CATEGORY_CONFIG[category_key]["label"],
        "description": description,
        "source": source,
        "items": items,
    })
