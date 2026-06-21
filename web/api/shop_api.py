"""
Shop API — 5 rotating NPC shops selling all item types.

Schedule:
  Keys      — always open; prices reset at UTC midnight daily
  Potions   — open even UTC hours (0,2,4,…); rotate every hour
  Rings     — open odd  UTC hours (1,3,5,…); rotate every hour
  Equipment — open when hour%4 in {0,1};     rotate every 2 hours
  Weapons   — open when hour%4 in {2,3};     rotate every 2 hours

Key pricing (per user, resets at UTC midnight):
  base_cost × (1.0 + purchases_so_far × 0.5)
  1st buy → ×1.0 | 2nd → ×1.5 | 3rd → ×2.0 | 4th → ×2.5 …

All other item pricing (Dungeon Merchant formula ×2):
  cost = rarity_base × FLOOR_PROXY × slot_factor × SHOP_MULTIPLIER

Currency: Pet XP
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.loot_calculator import LootCalculator
import json, os, hashlib, time, logging
import aiosqlite
from typing import Any, Dict, List, Optional

logger = logging.getLogger("shop_api")
router = APIRouter()

# ── Constants ──────────────────────────────────────────────────────────────────

MERCHANT_RARITY_PRICES: Dict[str, int] = {
    "Common": 100, "Uncommon": 500, "Rare": 1000,
    "Epic": 2500,  "Mythic": 5000,  "Special": 3000,
}
FLOOR_PROXY     = 25
SHOP_MULTIPLIER = 2

EQUIP_JSON_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "../../Systems/Pets/Logic/equipment.json")
)

# PetShop.db — persists key purchase counts so they survive page refresh + bot restart
SHOP_DB_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "../../Databases/Pets/PetShop.db")
)

# Key Emporium items — keys + chests (slots 0-6)
# Chest1-3 base cost matches Key1-3; Chest4 base cost = Key1+Key2+Key3 sum
_SHOP_ITEMS: List[Dict] = [
    {"name": "Key1",   "emoji_file": "Key1.png",   "type": "Key",   "rarity": "Uncommon", "tier_mult": 1},
    {"name": "Key2",   "emoji_file": "Key2.png",   "type": "Key",   "rarity": "Rare",     "tier_mult": 2},
    {"name": "Key3",   "emoji_file": "Key3.png",   "type": "Key",   "rarity": "Epic",     "tier_mult": 3},
    {"name": "Chest1", "emoji_file": "chest1.png", "type": "Chest", "rarity": "Common",   "tier_mult": 1},
    {"name": "Chest2", "emoji_file": "chest2.png", "type": "Chest", "rarity": "Uncommon", "tier_mult": 2},
    {"name": "Chest3", "emoji_file": "chest3.png", "type": "Chest", "rarity": "Rare",     "tier_mult": 3},
    {"name": "Chest4", "emoji_file": "chest4.png", "type": "Chest", "rarity": "Epic",     "tier_mult": 0},
]
_KEY_DEFS   = _SHOP_ITEMS[:3]   # backward compat
_CHEST_DEFS = _SHOP_ITEMS[3:]  # chest-only list
# Chest → matching key index for price parity (Chest1-3 match Key1-3)
_CHEST_KEY_MAP: Dict[str, int] = {"Chest1": 0, "Chest2": 1, "Chest3": 2}
# Shared purchase group: Key1↔Chest1, Key2↔Chest2, Key3↔Chest3. Chest4 is independent.
_KEY_PURCHASE_GROUP: Dict[str, str] = {
    "Key1": "Key1", "Chest1": "Key1",
    "Key2": "Key2", "Chest2": "Key2",
    "Key3": "Key3", "Chest3": "Key3",
    "Chest4": "Chest4",
}

# ── PetShop DB — persistent key purchase tracking ─────────────────────────────
# Survives page refresh AND bot/server restart.
# Table: key_purchases (uid TEXT, day_epoch INTEGER, key_name TEXT, count INTEGER)

_shop_db_ready = False


async def _ensure_shop_db() -> None:
    """Create PetShop.db and its table on first use (idempotent)."""
    global _shop_db_ready
    if _shop_db_ready:
        return
    async with aiosqlite.connect(SHOP_DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS key_purchases (
                uid       TEXT    NOT NULL,
                day_epoch INTEGER NOT NULL,
                key_name  TEXT    NOT NULL,
                count     INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (uid, day_epoch, key_name)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS shop_purchases (
                uid      TEXT    NOT NULL,
                epoch    INTEGER NOT NULL,
                shop_id  TEXT    NOT NULL,
                slot     INTEGER NOT NULL,
                count    INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (uid, epoch, shop_id, slot)
            )
        """)
        # Migrate old rows without count column
        try:
            await db.execute("ALTER TABLE shop_purchases ADD COLUMN count INTEGER NOT NULL DEFAULT 1")
        except Exception:
            pass  # column already exists
        await db.commit()
    _shop_db_ready = True


def _today_epoch() -> int:
    return int(time.time()) // 86400


def _seconds_until_utc_midnight() -> int:
    return 86400 - (int(time.time()) % 86400)


async def _get_key_purchases(uid: str) -> Dict[str, int]:
    """Return today's purchase counts for uid from PetShop.db."""
    await _ensure_shop_db()
    today = _today_epoch()
    async with aiosqlite.connect(SHOP_DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        # Prune stale days for this user while we're here (fire-and-forget)
        await db.execute(
            "DELETE FROM key_purchases WHERE uid = ? AND day_epoch != ?",
            (uid, today),
        )
        async with db.execute(
            "SELECT key_name, count FROM key_purchases WHERE uid = ? AND day_epoch = ?",
            (uid, today),
        ) as cur:
            rows = await cur.fetchall()
        await db.commit()
    return {row[0]: row[1] for row in rows}


async def _increment_key_purchase(uid: str, key_name: str) -> int:
    """Increment purchase count for uid+key_name today. Returns new count."""
    await _ensure_shop_db()
    today = _today_epoch()
    async with aiosqlite.connect(SHOP_DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute(
            """
            INSERT INTO key_purchases (uid, day_epoch, key_name, count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(uid, day_epoch, key_name)
            DO UPDATE SET count = count + 1
            """,
            (uid, today, key_name),
        )
        async with db.execute(
            "SELECT count FROM key_purchases WHERE uid = ? AND day_epoch = ? AND key_name = ?",
            (uid, today, key_name),
        ) as cur:
            row = await cur.fetchone()
        await db.commit()
    return row[0] if row else 1


def _key_multiplier(purchases_so_far: int) -> float:
    """1.0 + n×0.5  (first buy ×1.0, second ×1.5, …)"""
    return 1.0 + purchases_so_far * 0.5


def _non_key_multiplier(purchases_so_far: int) -> float:
    """×1, ×10, ×20, ×30, ×40, ×50 — adds ×10 per purchase up to 5."""
    if purchases_so_far == 0:
        return 1.0
    return 10.0 * purchases_so_far


# ── Non-key shop purchase persistence ──────────────────────────────────────────

def _shop_epoch(shop_id: str) -> int:
    if shop_id == "keys":
        return _day_epoch()
    if shop_id in ("potions", "rings"):
        return _hour_epoch()
    return _2h_epoch()  # equipment, weapons


async def _get_shop_purchases(uid: str) -> Dict[str, Dict[int, int]]:
    """Return dict of {shop_id: {slot: count}} for current epoch."""
    await _ensure_shop_db()
    async with aiosqlite.connect(SHOP_DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        # Prune stale records for each shop (epoch changed = new stock)
        for sid in ("potions", "rings", "equipment", "weapons"):
            ep = _shop_epoch(sid)
            await db.execute(
                "DELETE FROM shop_purchases WHERE uid = ? AND shop_id = ? AND epoch != ?",
                (uid, sid, ep),
            )
        async with db.execute(
            "SELECT shop_id, slot, count FROM shop_purchases WHERE uid = ?",
            (uid,),
        ) as cur:
            rows = await cur.fetchall()
        await db.commit()
    result: Dict[str, Dict[int, int]] = {}
    for shop_id, slot, count in rows:
        result.setdefault(shop_id, {})[slot] = count
    return result


async def _mark_shop_purchase(uid: str, shop_id: str, slot: int) -> int:
    """Increment purchase count for uid+shop+slot this epoch. Returns new count (capped at 5)."""
    await _ensure_shop_db()
    epoch = _shop_epoch(shop_id)
    async with aiosqlite.connect(SHOP_DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute(
            """
            INSERT INTO shop_purchases (uid, epoch, shop_id, slot, count)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(uid, epoch, shop_id, slot)
            DO UPDATE SET count = MIN(count + 1, 5)
            """,
            (uid, epoch, shop_id, slot),
        )
        async with db.execute(
            "SELECT count FROM shop_purchases WHERE uid = ? AND epoch = ? AND shop_id = ? AND slot = ?",
            (uid, epoch, shop_id, slot),
        ) as cur:
            row = await cur.fetchone()
        await db.commit()
    return row[0] if row else 1


# ── Equipment data ─────────────────────────────────────────────────────────────

_equip_data: Optional[Dict[str, Any]] = None

def _load_equip() -> Dict[str, Any]:
    global _equip_data
    if _equip_data is None:
        with open(EQUIP_JSON_PATH, encoding="utf-8") as f:
            _equip_data = json.load(f)
    return _equip_data


# ── Seeding helpers ────────────────────────────────────────────────────────────

def _seed_int(s: str) -> int:
    return int(hashlib.sha256(s.encode()).hexdigest(), 16)

def _seeded_choices(pool: list, k: int, seed: str) -> list:
    result, used, i = [], set(), 0
    while len(result) < k and len(result) < len(pool):
        idx = _seed_int(f"{seed}:pick:{i}") % len(pool)
        if idx not in used:
            used.add(idx); result.append(pool[idx])
        i += 1
    return result

def _slot_factor(seed: str) -> int:
    return 25 + (_seed_int(seed) % 76)


# ── Time helpers ───────────────────────────────────────────────────────────────

def _utc_hour()    -> int: return int(time.gmtime().tm_hour)
def _day_epoch()   -> int: return int(time.time()) // 86400
def _hour_epoch()  -> int: return int(time.time()) // 3600
def _2h_epoch()    -> int: return int(time.time()) // 7200
def _secs_to_next_hour() -> int: return 3600 - (int(time.time()) % 3600)
def _secs_to_next_2h()   -> int: return 7200 - (int(time.time()) % 7200)


# ── Price helpers ──────────────────────────────────────────────────────────────

def _item_price(rarity: str, seed: str) -> int:
    return int(FLOOR_PROXY * MERCHANT_RARITY_PRICES.get(rarity, 100) * _slot_factor(seed) * SHOP_MULTIPLIER)

def _key_base_price(kd: Dict) -> int:
    seed   = f"keys:day:{_day_epoch()}:slot:{kd['name']}"
    return int(FLOOR_PROXY * MERCHANT_RARITY_PRICES.get(kd["rarity"], 500)
               * _slot_factor(seed) * SHOP_MULTIPLIER * kd["tier_mult"])


def _item_base_price(item: Dict) -> int:
    """Return the base (pre-scaling) price for any Key Emporium item."""
    if item["tier_mult"] == 0:  # Chest4 — sum of all 3 key base prices
        return (_key_base_price(_SHOP_ITEMS[0])
                + _key_base_price(_SHOP_ITEMS[1])
                + _key_base_price(_SHOP_ITEMS[2]))
    # Chest1-3: price matches corresponding key (same cost to buy chest or key)
    key_idx = _CHEST_KEY_MAP.get(item["name"])
    if key_idx is not None:
        return _key_base_price(_SHOP_ITEMS[key_idx])
    return _key_base_price(item)


# ── Item builders ──────────────────────────────────────────────────────────────

def _build_key_shop_items(uid: Optional[str] = None, today_purchases: Optional[Dict[str, int]] = None) -> List[Dict]:
    """Build all Key Emporium items (keys + chests). today_purchases from DB."""
    if today_purchases is None:
        today_purchases = {}
    items = []
    for i, item_def in enumerate(_SHOP_ITEMS):
        group_name = _KEY_PURCHASE_GROUP[item_def["name"]]
        bought     = today_purchases.get(group_name, 0)
        base_price = _item_base_price(item_def)
        cost_now   = int(base_price * _key_multiplier(bought))
        cost_next  = int(base_price * _key_multiplier(bought + 1))
        items.append({
            "name":            item_def["name"],
            "emoji_file":      item_def["emoji_file"],
            "type":            item_def["type"],
            "rarity":          item_def["rarity"],
            "slot":            i,
            "base_cost":       base_price,
            "cost":            cost_now,
            "next_cost":       cost_next,
            "purchases_today": bought,
            "multiplier":      f"×{_key_multiplier(bought):.1f}",
        })
    return items


def _pick_5(pool: List[Dict], category: str, epoch: int) -> List[Dict]:
    seed_base = f"{category}:{epoch}"
    return [
        {**item, "cost": _item_price(item.get("rarity","Common"), f"{seed_base}:slot:{i}"), "slot": i}
        for i, item in enumerate(_seeded_choices(pool, 5, seed_base))
    ]

def _build_potion_items()    -> List[Dict]:
    return _pick_5(_load_equip().get("Potions", []), "potions", _hour_epoch())

def _build_ring_items()      -> List[Dict]:
    e = _load_equip()
    return _pick_5(e.get("Rings",[]) + e.get("Monsters",[]) + e.get("Gems",[]) + e.get("Materials",[]),
                   "rings", _hour_epoch())

def _build_equipment_items() -> List[Dict]:
    e = _load_equip()
    return _pick_5(e.get("Boots",[]) + e.get("Armor",[]) + e.get("Helmets",[]) + e.get("Shields",[]),
                   "equipment", _2h_epoch())

def _build_weapon_items()    -> List[Dict]:
    e = _load_equip()
    return _pick_5(e.get("Swords",[]) + e.get("Daggers",[]) + e.get("Katanas",[])
                   + e.get("Axes",[]) + e.get("Hammers",[]) + e.get("Bows",[]),
                   "weapons", _2h_epoch())


# ── Shop state ─────────────────────────────────────────────────────────────────

def _shop_states() -> Dict[str, Dict]:
    h  = _utc_hour()
    h4 = h % 4
    return {
        "keys":      {"open": True,          "countdown": _seconds_until_utc_midnight(), "cycle": "daily"},
        "potions":   {"open": h % 2 == 0,    "countdown": _secs_to_next_hour(),          "cycle": "1h"},
        "rings":     {"open": h % 2 == 1,    "countdown": _secs_to_next_hour(),          "cycle": "1h"},
        "equipment": {"open": h4 in (0, 1),  "countdown": _secs_to_next_2h(),            "cycle": "2h"},
        "weapons":   {"open": h4 in (2, 3),  "countdown": _secs_to_next_2h(),            "cycle": "2h"},
    }


# ── Shopkeeper skull ───────────────────────────────────────────────────────────

def _shopkeeper_skull(shop: str) -> Optional[int]:
    if shop == "keys":
        return (_seed_int(f"skull:keys:day:{_day_epoch()}") % 16) + 1
    epoch = _hour_epoch() if shop in ("potions", "rings") else _2h_epoch()
    return (_seed_int(f"skull:{shop}:epoch:{epoch}") % 16) + 1


# ── Full shop builder ──────────────────────────────────────────────────────────

def _build_all_shops(uid: Optional[str] = None, today_purchases: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    states = _shop_states()

    def _shop(name: str, label: str, item_fn, icon: str, desc: str) -> Dict:
        is_open = states[name]["open"]
        return {
            "id": name, "label": label, "icon": icon, "desc": desc,
            "skull": _shopkeeper_skull(name) if (is_open or name == "keys") else None,
            "state": states[name],
            "items": item_fn() if (is_open or name == "keys") else [],
        }

    return {
        "keys": {
            "id": "keys", "label": "The Ferryman's Toll", "icon": "🗝️",
            "desc": "Keys to unlock dungeon chests. Prices reset at UTC midnight.",
            "skull": _shopkeeper_skull("keys"),
            "state": states["keys"],
            "items": _build_key_shop_items(uid, today_purchases),
        },
        "potions":   _shop("potions",   "Wraith's Wort",  _build_potion_items,    "🧪", "Magical brews to boost your pet's power."),
        "rings":     _shop("rings",     "Crypt Curios", _build_ring_items,    "💍", "Rings, monsters, gems, and rare materials."),
        "equipment": _shop("equipment", "Hollow Outfitter",    _build_equipment_items, "🛡️", "Armor, boots, helmets, and shields."),
        "weapons":   _shop("weapons",   "Grim Arsenal",     _build_weapon_items,    "⚔️", "Every blade, bow, and blunt instrument imaginable."),
    }


# ── Auth ───────────────────────────────────────────────────────────────────────

def _auth(request: Request):
    user = request.session.get("discord_user")
    if not user:
        return None, None, JSONResponse({"error": "Not logged in"}, status_code=401)
    uid = user.get("id")
    if not uid:
        return None, None, JSONResponse({"error": "No user ID"}, status_code=401)
    return uid, user.get("username", "Unknown"), None


# ── GET /api/shop/state ────────────────────────────────────────────────────────

@router.get("/shop/state")
async def shop_state(request: Request):
    uid, _, err = _auth(request)
    if err:
        return err

    today_purchases = await _get_key_purchases(uid) if uid else {}
    shop_purchases  = await _get_shop_purchases(uid) if uid else {}
    shops    = _build_all_shops(uid, today_purchases)
    pet_data = await user_data_manager.get_pet_data_async(uid)

    spendable_xp = pet_level = 0
    pet_name = None
    pet_xp_into_level = pet_xp_for_next = 0
    inventory_counts: Dict[str, int] = {}
    pet_level = 1

    if pet_data:
        lvl = int(pet_data.get("level", 1))
        exp = int(pet_data.get("experience", 0))
        spendable_xp      = LootCalculator.get_total_experience_for_level(lvl) + exp
        pet_level         = lvl
        pet_name          = pet_data.get("name", "Your Pet")
        pet_xp_into_level = exp
        pet_xp_for_next   = LootCalculator.get_next_level_xp(lvl)
        for item in pet_data.get("inventory", []):
            n = item.get("name", "")
            inventory_counts[n] = inventory_counts.get(n, 0) + int(item.get("count", 1))

    for sid, shop in shops.items():
        for item in shop.get("items", []):
            item["owned"] = inventory_counts.get(item["name"], 0)
        if sid == "keys":
            continue  # keys/chests already have prices computed in _build_key_shop_items
        slot_counts = shop_purchases.get(sid, {})
        for item in shop.get("items", []):
            bought    = slot_counts.get(item["slot"], 0)
            base_cost = item.get("cost", 0)
            item["base_cost"]       = base_cost
            item["cost"]            = int(base_cost * _non_key_multiplier(bought))
            item["next_cost"]       = int(base_cost * _non_key_multiplier(bought + 1))
            item["purchases_today"] = bought
            item["multiplier"]      = f"×{_non_key_multiplier(bought):.0f}"
            item["purchased"]       = bought >= 5

    return JSONResponse({
        "shops": shops,
        "pet": {
            "name":          pet_name,
            "level":         pet_level,
            "spendable_xp":  spendable_xp,
            "xp_into_level": pet_xp_into_level,
            "xp_for_next":   pet_xp_for_next,
        },
    })


# ── POST /api/shop/buy ─────────────────────────────────────────────────────────

@router.post("/shop/buy")
async def shop_buy(request: Request):
    uid, _, err = _auth(request)
    if err:
        return err

    body    = await request.json()
    shop_id = body.get("shop_id", "")
    slot    = int(body.get("slot", -1))

    if shop_id not in ("keys", "potions", "rings", "equipment", "weapons"):
        return JSONResponse({"error": "Invalid shop"}, status_code=400)
    if slot < 0:
        return JSONResponse({"error": "Invalid slot"}, status_code=400)

    # ── Key Emporium: keys + chests, per-user escalating price ────────────────
    if shop_id == "keys":
        if slot >= len(_SHOP_ITEMS):
            return JSONResponse({"error": "Invalid item slot"}, status_code=400)

        item_def        = _SHOP_ITEMS[slot]
        group_name      = _KEY_PURCHASE_GROUP[item_def["name"]]
        today_purchases = await _get_key_purchases(uid)
        bought_so_far   = today_purchases.get(group_name, 0)
        base_price      = _item_base_price(item_def)
        cost            = int(base_price * _key_multiplier(bought_so_far))

        pet_data = await user_data_manager.get_pet_data_async(uid)
        if not pet_data:
            return JSONResponse({"error": "You need a pet to shop here"}, status_code=400)

        lvl      = int(pet_data.get("level", 1))
        exp      = int(pet_data.get("experience", 0))
        total_xp = LootCalculator.get_total_experience_for_level(lvl) + exp

        if total_xp < cost:
            return JSONResponse({"error": f"Not enough XP. Need {cost:,} but you have {total_xp:,}."}, status_code=400)

        new_total                = total_xp - cost
        _, new_level, new_xp_rem = LootCalculator.recompute_level_from_total_xp(pet_data, new_total)
        pet_data["level"]        = new_level
        pet_data["experience"]   = new_xp_rem

        _add_to_inventory(pet_data, {
            "name": item_def["name"], "type": item_def["type"],
            "rarity": item_def["rarity"], "emoji_file": item_def["emoji_file"], "count": 1,
        })

        await user_data_manager.save_pet_data(uid, pet_data)
        _try_invalidate_cache(pet_data)

        # Persist purchase count to DB AFTER save succeeds (shared group)
        new_bought  = await _increment_key_purchase(uid, group_name)
        next_cost   = int(base_price * _key_multiplier(new_bought))
        new_total_xp = LootCalculator.get_total_experience_for_level(new_level) + new_xp_rem

        return JSONResponse({
            "ok":               True,
            "item_name":        item_def["name"],
            "cost":             cost,
            "next_cost":        next_cost,
            "next_multiplier":  f"×{_key_multiplier(new_bought):.1f}",
            "purchases_today":  new_bought,
            "new_spendable_xp": new_total_xp,
            "new_level":        new_level,
            "new_xp_into_level": new_xp_rem,
            "new_xp_for_next":  LootCalculator.get_next_level_xp(new_level),
        })

    # ── Other shops (scaling price: ×1, ×10, ×20, ×30, ×30, max 5) ──────────
    today_purchases = await _get_key_purchases(uid)
    shops = _build_all_shops(uid, today_purchases)
    shop  = shops.get(shop_id, {})

    if not shop.get("state", {}).get("open", False):
        return JSONResponse({"error": "This shop is currently closed"}, status_code=400)

    item = next((i for i in shop.get("items", []) if i.get("slot") == slot), None)
    if not item:
        return JSONResponse({"error": "Item not found in shop"}, status_code=400)

    # Compute scaled cost from DB purchase count
    shop_purchases_data = await _get_shop_purchases(uid)
    slot_counts  = shop_purchases_data.get(shop_id, {})
    bought_sofar = slot_counts.get(slot, 0)

    if bought_sofar >= 5:
        return JSONResponse({"error": "This item is sold out"}, status_code=400)

    base_cost = item.get("cost", 0)
    cost      = int(base_cost * _non_key_multiplier(bought_sofar))

    pet_data = await user_data_manager.get_pet_data_async(uid)
    if not pet_data:
        return JSONResponse({"error": "You need a pet to shop here"}, status_code=400)

    lvl      = int(pet_data.get("level", 1))
    exp      = int(pet_data.get("experience", 0))
    total_xp = LootCalculator.get_total_experience_for_level(lvl) + exp

    if total_xp < cost:
        return JSONResponse({"error": f"Not enough XP. Need {cost:,} but you have {total_xp:,}."}, status_code=400)

    new_total                = total_xp - cost
    _, new_level, new_xp_rem = LootCalculator.recompute_level_from_total_xp(pet_data, new_total)
    pet_data["level"]        = new_level
    pet_data["experience"]   = new_xp_rem

    new_item = {
        "name":       item["name"],
        "type":       item.get("type", "Material"),
        "rarity":     item.get("rarity", "Common"),
        "emoji_file": item.get("emoji_file", ""),
        "count":      1,
    }
    for field in ("effect", "bonuses", "set", "element", "category"):
        if field in item:
            new_item[field] = item[field]

    _add_to_inventory(pet_data, new_item)
    await user_data_manager.save_pet_data(uid, pet_data)
    _try_invalidate_cache(pet_data)

    # Persist purchase (increments count in DB)
    new_bought = await _mark_shop_purchase(uid, shop_id, slot)

    new_total_after = LootCalculator.get_total_experience_for_level(new_level) + new_xp_rem
    return JSONResponse({
        "ok":               True,
        "item_name":        item["name"],
        "cost":             cost,
        "base_cost":        base_cost,
        "next_cost":        int(base_cost * _non_key_multiplier(new_bought)),
        "next_multiplier":  f"×{_non_key_multiplier(new_bought):.0f}",
        "purchases_today":  new_bought,
        "new_spendable_xp": new_total_after,
        "new_level":        new_level,
        "new_xp_into_level": new_xp_rem,
        "new_xp_for_next":  LootCalculator.get_next_level_xp(new_level),
    })


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _add_to_inventory(pet_data: Dict, new_item: Dict) -> None:
    inventory = pet_data.get("inventory", [])
    for inv in inventory:
        if (inv.get("name")   == new_item["name"]
                and inv.get("type")   == new_item["type"]
                and inv.get("rarity") == new_item["rarity"]
                and not inv.get("reforged", False)):
            inv["count"] = inv.get("count", 1) + 1
            pet_data["inventory"] = inventory
            return
    inventory.append(new_item)
    pet_data["inventory"] = inventory


def _try_invalidate_cache(pet_data: Dict) -> None:
    try:
        from web.api.pets.gpp_helpers import _invalidate_stats_cache
        _invalidate_stats_cache(pet_data)
    except Exception:
        pass
