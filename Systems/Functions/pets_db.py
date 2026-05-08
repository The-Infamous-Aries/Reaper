import json
import asyncio
from pathlib import Path
from typing import Any, Dict, Optional, List
import logging
import aiosqlite
from Systems.Functions import database_manager
from Systems.Functions.db_paths import PETS_DB, PETS_DB_STR

logger = logging.getLogger(__name__)


def _total_xp(pet: dict) -> int:
    """Return a pet's total cumulative XP across all levels."""
    lvl = int(pet.get("level", 1))
    rem = int(pet.get("experience", 0))
    n = lvl - 1
    cumulative = int(200 * (1 - 1.03 ** n) / (1 - 1.03)) if lvl > 1 else 0
    return cumulative + rem


def _enrich_item(name: str, item_type: str, rarity: str, count: int) -> Dict[str, Any]:
    """
    Build a full item dict by merging the minimal fields with the canonical
    equipment.json definition (which includes use_effect, emoji_file, etc.).
    Falls back to a minimal dict if the item isn't found in equipment data.
    """
    base: Dict[str, Any] = {"name": name, "type": item_type, "rarity": rarity, "count": count}
    try:
        from Systems.Functions.user_data_manager import user_data_manager
        eq_data = user_data_manager.file_manager.get_data("equipment")
        type_section_map = {
            "Potion": "Potions", "Material": "Materials", "Gem": "Gems",
            "Monster": "Monsters", "Hat": "Hats",
        }
        section = type_section_map.get(item_type, item_type + "s")
        for item in eq_data.get(section, []):
            if item.get("name") == name:
                merged = dict(item)          # full canonical data
                merged["count"] = count      # override with actual count
                return merged
    except Exception:
        pass
    return base

class PetsDatabase:
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, db_path: str = None):
        if hasattr(self, '_initialized') and self._initialized:
            return
            
        self._initialized = True
        from Systems.Functions.db_paths import PETS_DB_STR
        self.db_path = db_path or PETS_DB_STR
        self._legacy_db_path = PETS_DB
        self._lock = asyncio.Lock()
        self._db_initialized = False
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
    
    async def _ensure_initialized(self):
        """Ensure database is initialized (thread-safe, no double-init)"""
        if self._db_initialized:
            return
        async with self._lock:
            # Double-check after acquiring the lock
            if not self._db_initialized:
                await self._initialize_db()
                self._db_initialized = True

    async def _initialize_db(self):
        """Create the tables if they don't exist. Called only while self._lock is held."""
        async with aiosqlite.connect(self.db_path) as db:
            # Create pets table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS pets (
                    user_id TEXT PRIMARY KEY,
                    pet_data TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            await db.execute('''
                CREATE TRIGGER IF NOT EXISTS trg_pets_updated_at
                AFTER UPDATE ON pets
                FOR EACH ROW
                BEGIN
                    UPDATE pets SET updated_at = CURRENT_TIMESTAMP WHERE user_id = OLD.user_id;
                END;
            ''')
            
            # Create users table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            await db.execute('''
                CREATE TRIGGER IF NOT EXISTS trg_users_updated_at
                AFTER UPDATE ON users
                FOR EACH ROW
                BEGIN
                    UPDATE users SET last_updated = CURRENT_TIMESTAMP WHERE user_id = OLD.user_id;
                END;
            ''')

            # Create user_relationships table for Friend/Foe system
            await db.execute('''
                CREATE TABLE IF NOT EXISTS user_relationships (
                    user_id TEXT NOT NULL,
                    target_user_id TEXT NOT NULL,
                    relationship_type TEXT NOT NULL CHECK (relationship_type IN ('best_friend', 'friend', 'foe', 'enemy')),
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, target_user_id)
                )
            ''')
            await db.execute('''
                CREATE TRIGGER IF NOT EXISTS trg_user_relationships_updated_at
                AFTER UPDATE ON user_relationships
                FOR EACH ROW
                BEGIN
                    UPDATE user_relationships SET updated_at = CURRENT_TIMESTAMP 
                    WHERE user_id = OLD.user_id AND target_user_id = OLD.target_user_id;
                END;
            ''')

            # Create indexes for better performance
            await db.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON pets(user_id)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_relationships_user_id ON user_relationships(user_id)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_relationships_target_user_id ON user_relationships(target_user_id)')
            
            # Migration: Handle existing databases that might have 'updated_at' column in users table
            # Check if 'updated_at' column exists and migrate to 'last_updated'
            try:
                cursor = await db.execute("PRAGMA table_info(users)")
                columns = await cursor.fetchall()
                column_names = [col[1] for col in columns]
                
                if 'updated_at' in column_names and 'last_updated' not in column_names:
                    # Rename updated_at to last_updated
                    await db.execute('ALTER TABLE users RENAME COLUMN updated_at TO last_updated')
                    logger.info("Migrated users.updated_at column to users.last_updated")
                elif 'updated_at' in column_names and 'last_updated' in column_names:
                    # Both columns exist, copy data and drop updated_at
                    await db.execute('UPDATE users SET last_updated = updated_at WHERE last_updated IS NULL')
                    await db.execute('ALTER TABLE users DROP COLUMN updated_at')
                    logger.info("Merged users.updated_at data into users.last_updated and dropped old column")
            except Exception as e:
                logger.debug(f"Column migration check completed (this is normal): {e}")
            
            await db.commit()
            logger.info("Pets database initialized successfully")

    
    async def save_pet_data(self, user_id: str, pet_data: Dict[str, Any]) -> bool:
        """Save pet data to database"""
        try:
            await self._ensure_initialized()
            async with self._lock:
                async with aiosqlite.connect(self.db_path) as db:
                    # Convert pet data to JSON string
                    pet_json = json.dumps(pet_data, default=str)
                    
                    await db.execute('''
                        INSERT OR REPLACE INTO pets (user_id, pet_data)
                        VALUES (?, ?)
                    ''', (str(user_id), pet_json))
                    
                    await db.commit()
                    logger.debug(f"Pet data saved for user {user_id}")
                    return True
                    
        except Exception as e:
            logger.error(f"Error saving pet data for user {user_id}: {e}")
            return False
    
    async def get_pet_data(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get pet data from database"""
        try:
            await self._ensure_initialized()
            async with self._lock:
                async with aiosqlite.connect(self.db_path) as db:
                    async with db.execute('''
                        SELECT pet_data FROM pets WHERE user_id = ?
                    ''', (str(user_id),)) as cursor:
                        row = await cursor.fetchone()
                        
                        if row:
                            pet_json = row[0]
                            pet_data = json.loads(pet_json)
                            logger.debug(f"Pet data retrieved for user {user_id}")
                            return pet_data
                        else:
                            logger.debug(f"No pet data found for user {user_id}")
                            return None
                            
        except Exception as e:
            logger.error(f"Error retrieving pet data for user {user_id}: {e}")
            return None
    
    async def delete_pet_data(self, user_id: str) -> bool:
        """Delete pet data from database"""
        try:
            await self._ensure_initialized()
            async with self._lock:
                async with aiosqlite.connect(self.db_path) as db:
                    cursor = await db.execute('''
                        DELETE FROM pets WHERE user_id = ?
                    ''', (str(user_id),))
                    
                    await db.commit()
                    
                    if cursor.rowcount > 0:
                        logger.debug(f"Pet data deleted for user {user_id}")
                        return True
                    else:
                        logger.debug(f"No pet data found to delete for user {user_id}")
                        return False
                        
        except Exception as e:
            logger.error(f"Error deleting pet data for user {user_id}: {e}")
            return False
    
    async def get_all_pet_data(self) -> Dict[str, Dict[str, Any]]:
        """Get all pet data from database"""
        try:
            await self._ensure_initialized()
            async with self._lock:
                async with aiosqlite.connect(self.db_path) as db:
                    async with db.execute('''
                        SELECT user_id, pet_data FROM pets
                    ''') as cursor:
                        rows = await cursor.fetchall()
                        
                        all_pets = {}
                        for row in rows:
                            user_id, pet_json = row
                            pet_data = json.loads(pet_json)
                            all_pets[user_id] = pet_data
                        
                        logger.debug(f"Retrieved {len(all_pets)} pet records from database")
                        return all_pets
                        
        except Exception as e:
            logger.error(f"Error retrieving all pet data: {e}")
            return {}
    
    async def batch_save_pet_data(self, pet_data_dict: Dict[str, Dict[str, Any]]) -> bool:
        """Batch save multiple pet data entries"""
        try:
            await self._ensure_initialized()
            async with self._lock:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute('BEGIN TRANSACTION')
                    
                    for user_id, pet_data in pet_data_dict.items():
                        pet_json = json.dumps(pet_data, default=str)
                        await db.execute('''
                            INSERT OR REPLACE INTO pets (user_id, pet_data)
                        VALUES (?, ?)
                    ''', (str(user_id), pet_json))
                    
                    await db.commit()
                    logger.debug(f"Batch saved {len(pet_data_dict)} pet records")
                    return True
                    
        except Exception as e:
            logger.error(f"Error batch saving pet data: {e}")
            return False
    
    async def get_user_ids_with_pets(self) -> List[str]:
        """Get list of user IDs that have pet data"""
        try:
            await self._ensure_initialized()
            async with self._lock:
                async with aiosqlite.connect(self.db_path) as db:
                    async with db.execute('''
                        SELECT user_id FROM pets
                    ''') as cursor:
                        rows = await cursor.fetchall()
                        user_ids = [row[0] for row in rows]
                        logger.debug(f"Found {len(user_ids)} users with pet data")
                        return user_ids
                        
        except Exception as e:
            logger.error(f"Error retrieving user IDs with pets: {e}")
            return []
    
    async def migrate_json_to_db(self, json_pet_data: Dict[str, Dict[str, Any]]) -> bool:
        """Migrate existing JSON pet data to database"""
        try:
            success = await self.batch_save_pet_data(json_pet_data)
            if success:
                logger.info(f"Successfully migrated {len(json_pet_data)} pet records to database")
            return success
            
        except Exception as e:
            logger.error(f"Error migrating pet data to database: {e}")
            return False
    
    async def close(self):
        """Close database connections"""
        logger.info("Pets database closed")

    # --- User Profile Methods ---

    async def save_user_profile(self, user_id: str, username: str) -> bool:
        """Saves a user's profile to the users table."""
        try:
            await self._ensure_initialized()
            async with self._lock:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute('''
                        INSERT OR REPLACE INTO users (user_id, username)
                        VALUES (?, ?)
                    ''', (user_id, username))
                    await db.commit()
                    return True
        except Exception as e:
            logger.error(f"Error saving user profile for {user_id}: {e}")
            return False

    async def get_user_relationship(self, user_id: str, target_user_id: str) -> Optional[str]:
        """Get the relationship type between two users"""
        await self._ensure_initialized()
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT relationship_type FROM user_relationships WHERE user_id = ? AND target_user_id = ?",
                    (user_id, target_user_id)
                ) as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row else None
        except Exception as e:
            logger.error(f"Error getting user relationship: {e}")
            return None

    async def set_user_relationship(self, user_id: str, target_user_id: str, relationship_type: str) -> bool:
        """Set the relationship type between two users"""
        if relationship_type not in ['best_friend', 'friend', 'foe', 'enemy']:
            return False
        if user_id == target_user_id:
            return False
            
        await self._ensure_initialized()
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """INSERT OR REPLACE INTO user_relationships 
                       (user_id, target_user_id, relationship_type) 
                       VALUES (?, ?, ?)""",
                    (user_id, target_user_id, relationship_type)
                )
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error setting user relationship: {e}")
            return False

    async def get_user_relationships(self, user_id: str) -> Dict[str, str]:
        """Get all relationships for a user"""
        await self._ensure_initialized()
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT target_user_id, relationship_type FROM user_relationships WHERE user_id = ?",
                    (user_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    return {row[0]: row[1] for row in rows}
        except Exception as e:
            logger.error(f"Error getting user relationships: {e}")
            return {}

    async def get_mutual_relationship(self, user_id: str, target_user_id: str) -> tuple[Optional[str], Optional[str]]:
        """Get mutual relationship between two users (user->target, target->user)"""
        await self._ensure_initialized()
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    """SELECT 
                        (SELECT relationship_type FROM user_relationships WHERE user_id = ? AND target_user_id = ?) as user_to_target,
                        (SELECT relationship_type FROM user_relationships WHERE user_id = ? AND target_user_id = ?) as target_to_user
                    """,
                    (user_id, target_user_id, target_user_id, user_id)
                ) as cursor:
                    row = await cursor.fetchone()
                    return (row[0], row[1]) if row else (None, None)
        except Exception as e:
            logger.error(f"Error getting mutual relationship: {e}")
            return (None, None)

    async def remove_user_relationship(self, user_id: str, target_user_id: str) -> bool:
        """Remove relationship between two users"""
        await self._ensure_initialized()
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "DELETE FROM user_relationships WHERE user_id = ? AND target_user_id = ?",
                    (user_id, target_user_id)
                )
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error removing user relationship: {e}")
            return False
        """Gets a user's profile from the users table."""
        try:
            await self._ensure_initialized()
            async with self._lock:
                async with aiosqlite.connect(self.db_path) as db:
                    async with db.execute("SELECT user_id, username, created_at, last_updated FROM users WHERE user_id = ?", (user_id,)) as cursor:
                        row = await cursor.fetchone()
                        if row:
                            return {"user_id": row[0], "username": row[1], "created_at": row[2], "last_updated": row[3]}
                        return None
        except Exception as e:
            logger.error(f"Error getting user profile for {user_id}: {e}")
            return None

    # --- Bazaar Methods ---

    async def _ensure_bazaar_table(self, db: aiosqlite.Connection):
        """Create bazaar table if it doesn't exist (idempotent)."""
        await db.execute('''
            CREATE TABLE IF NOT EXISTS bazaar (
                listing_id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id TEXT NOT NULL,
                seller_name TEXT NOT NULL,
                seller_pet_name TEXT,
                seller_pet_emoji TEXT,
                item_name TEXT NOT NULL,
                item_type TEXT NOT NULL,
                item_rarity TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                price_type TEXT NOT NULL,
                xp_price INTEGER,
                trade_item_name TEXT,
                trade_item_quantity INTEGER,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                buyer_id TEXT,
                buyer_name TEXT
            )
        ''')
        # Add new columns to existing tables if they don't exist yet
        for col, typedef in [("seller_pet_name", "TEXT"), ("seller_pet_emoji", "TEXT")]:
            try:
                await db.execute(f"ALTER TABLE bazaar ADD COLUMN {col} {typedef}")
            except Exception:
                pass  # Column already exists
        await db.execute('CREATE INDEX IF NOT EXISTS idx_bazaar_status ON bazaar(status)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_bazaar_seller ON bazaar(seller_id)')
        await db.commit()

    async def bazaar_post_listing(
        self,
        seller_id: str,
        seller_name: str,
        seller_pet_name: Optional[str],
        seller_pet_emoji: Optional[str],
        item_name: str,
        item_type: str,
        item_rarity: str,
        quantity: int,
        price_type: str,          # "xp" or "trade"
        xp_price: Optional[int],
        trade_item_name: Optional[str],
        trade_item_quantity: Optional[int],
        pet_data: Dict[str, Any],
    ) -> Optional[int]:
        """
        Atomically remove item from seller's inventory and create a bazaar listing.
        Returns the new listing_id on success, None on failure.
        """
        try:
            await self._ensure_initialized()
            async with self._lock:
                async with aiosqlite.connect(self.db_path) as db:
                    await self._ensure_bazaar_table(db)

                    # --- Deduct item from inventory ---
                    inventory: List[Dict[str, Any]] = pet_data.get("inventory", [])
                    item_idx = next(
                        (i for i, it in enumerate(inventory)
                         if it["name"].lower() == item_name.lower()),
                        None,
                    )
                    if item_idx is None:
                        logger.warning(f"bazaar_post_listing: item '{item_name}' not in inventory for {seller_id}")
                        return None
                    if inventory[item_idx].get("count", 1) < quantity:
                        logger.warning(f"bazaar_post_listing: not enough '{item_name}' for {seller_id}")
                        return None

                    inventory[item_idx]["count"] -= quantity
                    if inventory[item_idx]["count"] <= 0:
                        inventory.pop(item_idx)

                    pet_data["inventory"] = inventory
                    pet_json = json.dumps(pet_data, default=str)
                    await db.execute(
                        "INSERT OR REPLACE INTO pets (user_id, pet_data) VALUES (?, ?)",
                        (str(seller_id), pet_json),
                    )

                    # --- Insert listing ---
                    cursor = await db.execute(
                        '''INSERT INTO bazaar
                           (seller_id, seller_name, seller_pet_name, seller_pet_emoji,
                            item_name, item_type, item_rarity,
                            quantity, price_type, xp_price, trade_item_name, trade_item_quantity)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                        (
                            str(seller_id), seller_name, seller_pet_name, seller_pet_emoji,
                            item_name, item_type, item_rarity,
                            quantity, price_type, xp_price, trade_item_name, trade_item_quantity,
                        ),
                    )
                    await db.commit()
                    return cursor.lastrowid
        except Exception as e:
            logger.error(f"bazaar_post_listing error: {e}", exc_info=True)
            return None

    async def bazaar_get_active_listings(self) -> List[Dict[str, Any]]:
        """Return all active listings ordered newest-first."""
        try:
            await self._ensure_initialized()
            async with self._lock:
                async with aiosqlite.connect(self.db_path) as db:
                    await self._ensure_bazaar_table(db)
                    db.row_factory = aiosqlite.Row
                    async with db.execute(
                        "SELECT * FROM bazaar WHERE status='active' ORDER BY created_at DESC"
                    ) as cursor:
                        rows = await cursor.fetchall()
                        return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"bazaar_get_active_listings error: {e}", exc_info=True)
            return []

    async def bazaar_buy_listing(
        self,
        listing_id: int,
        buyer_id: str,
        buyer_name: str,
        buyer_pet: Dict[str, Any],
        seller_pet: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Atomically complete a purchase:
        - XP sale  : deduct XP from buyer, add XP to seller, give item to buyer
        - Trade    : remove trade item from buyer, give it to seller, give listed item to buyer
        Returns {"ok": True} or {"ok": False, "error": "..."}
        """
        try:
            await self._ensure_initialized()
            async with self._lock:
                async with aiosqlite.connect(self.db_path) as db:
                    await self._ensure_bazaar_table(db)
                    db.row_factory = aiosqlite.Row

                    # Fetch listing
                    async with db.execute(
                        "SELECT * FROM bazaar WHERE listing_id=? AND status='active'",
                        (listing_id,),
                    ) as cur:
                        row = await cur.fetchone()
                    if not row:
                        return {"ok": False, "error": "Listing not found or already sold"}

                    listing = dict(row)
                    if str(listing["seller_id"]) == str(buyer_id):
                        return {"ok": False, "error": "You can't buy your own listing"}

                    # Fetch fresh pet data for both parties inside the lock
                    async with db.execute(
                        "SELECT pet_data FROM pets WHERE user_id=?", (str(buyer_id),)
                    ) as cur2:
                        buyer_row = await cur2.fetchone()
                    buyer_pet = json.loads(buyer_row["pet_data"]) if buyer_row else buyer_pet

                    async with db.execute(
                        "SELECT pet_data FROM pets WHERE user_id=?", (str(listing["seller_id"]),)
                    ) as cur3:
                        seller_row = await cur3.fetchone()
                    seller_pet = json.loads(seller_row["pet_data"]) if seller_row else seller_pet

                    price_type = listing["price_type"]
                    item_name  = listing["item_name"]
                    item_type  = listing["item_type"]
                    item_rarity = listing["item_rarity"]
                    quantity   = listing["quantity"]

                    # Initialize XP tracking variables (used after lock release)
                    _xp_buyer_deduct = None
                    _xp_seller_add   = None
                    _seller_id_for_xp = None

                    if price_type == "xp":
                        xp_cost = listing["xp_price"]
                        buyer_total_xp = _total_xp(buyer_pet)
                        if buyer_total_xp < xp_cost:
                            return {"ok": False, "error": f"Not enough XP (need {xp_cost:,}, have {buyer_total_xp:,})"}
                        # Deduct XP from buyer and add to seller via the centralized
                        # XP system so level-up/down, stat changes, and ability
                        # multipliers are all applied correctly.
                        # We must release the DB lock before calling apply_xp_change
                        # (which acquires its own lock via user_data_manager), so we
                        # do the inventory/listing work first, then apply XP outside
                        # the lock below.  Flag it here so the post-lock block runs.
                        _xp_buyer_deduct = xp_cost
                        _xp_seller_add   = xp_cost
                        _seller_id_for_xp = str(listing["seller_id"])

                    elif price_type == "trade":
                        trade_name = listing["trade_item_name"]
                        trade_qty  = listing["trade_item_quantity"] or 1
                        buyer_inv  = buyer_pet.get("inventory", [])
                        tidx = next(
                            (i for i, it in enumerate(buyer_inv)
                             if isinstance(it, dict) and it.get("name", "").lower() == trade_name.lower()),
                            None,
                        )
                        if tidx is None or buyer_inv[tidx].get("count", 1) < trade_qty:
                            return {"ok": False, "error": f"You don't have {trade_qty}x {trade_name}"}
                        # Remove trade item from buyer
                        buyer_inv[tidx]["count"] -= trade_qty
                        if buyer_inv[tidx]["count"] <= 0:
                            buyer_inv.pop(tidx)
                        buyer_pet["inventory"] = buyer_inv
                        # Give trade item to seller
                        seller_inv = seller_pet.get("inventory", [])
                        sidx = next(
                            (i for i, it in enumerate(seller_inv)
                             if isinstance(it, dict) and it.get("name", "").lower() == trade_name.lower()),
                            None,
                        )
                        if sidx is not None:
                            seller_inv[sidx]["count"] = seller_inv[sidx].get("count", 1) + trade_qty
                        else:
                            trade_item_meta = next(
                                (it for it in buyer_inv if isinstance(it, dict) and it.get("name", "").lower() == trade_name.lower()), {}
                            )
                            seller_inv.append(_enrich_item(
                                trade_name,
                                trade_item_meta.get("type", "Material"),
                                trade_item_meta.get("rarity", "Common"),
                                trade_qty,
                            ))
                        seller_pet["inventory"] = seller_inv
                    else:
                        return {"ok": False, "error": "Unknown price type"}

                    # Give listed item to buyer
                    buyer_inv2 = buyer_pet.get("inventory", [])
                    bidx = next(
                        (i for i, it in enumerate(buyer_inv2)
                         if isinstance(it, dict) and it.get("name", "").lower() == item_name.lower()),
                        None,
                    )
                    if bidx is not None:
                        buyer_inv2[bidx]["count"] = buyer_inv2[bidx].get("count", 1) + quantity
                    else:
                        buyer_inv2.append(_enrich_item(item_name, item_type, item_rarity, quantity))
                    buyer_pet["inventory"] = buyer_inv2

                    # Persist both pets — inventory only; XP/level will be
                    # updated by apply_xp_change after the lock is released.
                    await db.execute(
                        "INSERT OR REPLACE INTO pets (user_id, pet_data) VALUES (?, ?)",
                        (str(buyer_id), json.dumps(buyer_pet, default=str)),
                    )
                    await db.execute(
                        "INSERT OR REPLACE INTO pets (user_id, pet_data) VALUES (?, ?)",
                        (str(listing["seller_id"]), json.dumps(seller_pet, default=str)),
                    )

                    # Mark listing sold
                    from datetime import datetime as _dt
                    await db.execute(
                        """UPDATE bazaar SET status='sold', buyer_id=?, buyer_name=?,
                           completed_at=? WHERE listing_id=?""",
                        (str(buyer_id), buyer_name, _dt.utcnow().isoformat(), listing_id),
                    )
                    await db.commit()

            # ── Apply XP changes outside the DB lock ──────────────────────────
            # apply_xp_change acquires user_data_manager's per-user lock, so it
            # must not be called while self._lock is held (deadlock risk).
            if _xp_buyer_deduct is not None:
                try:
                    from Systems.Pets.Logic.pet_brain import LootCalculator
                    await LootCalculator.apply_xp_change(
                        int(buyer_id), -_xp_buyer_deduct, source="bazaar_purchase"
                    )
                    await LootCalculator.apply_xp_change(
                        int(_seller_id_for_xp), _xp_seller_add, source="bazaar_sale"
                    )
                except Exception as _xp_err:
                    logger.error(f"bazaar_buy_listing: XP apply failed: {_xp_err}", exc_info=True)
                    # XP failure is non-fatal — item transfer already committed.

            return {"ok": True}
        except Exception as e:
            logger.error(f"bazaar_buy_listing error: {e}", exc_info=True)
            return {"ok": False, "error": "Internal server error"}

    async def bazaar_cancel_listing(
        self,
        listing_id: int,
        seller_id: str,
        seller_pet: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Return item to seller's inventory and mark listing cancelled."""
        try:
            await self._ensure_initialized()
            async with self._lock:
                async with aiosqlite.connect(self.db_path) as db:
                    await self._ensure_bazaar_table(db)
                    db.row_factory = aiosqlite.Row

                    async with db.execute(
                        "SELECT * FROM bazaar WHERE listing_id=? AND status='active'",
                        (listing_id,),
                    ) as cur:
                        row = await cur.fetchone()
                    if not row:
                        return {"ok": False, "error": "Listing not found or already closed"}
                    listing = dict(row)
                    if str(listing["seller_id"]) != str(seller_id):
                        return {"ok": False, "error": "Not your listing"}

                    # Fetch the freshest pet data inside the lock to avoid stale reads
                    async with db.execute(
                        "SELECT pet_data FROM pets WHERE user_id=?", (str(seller_id),)
                    ) as cur2:
                        pet_row = await cur2.fetchone()
                    fresh_pet = json.loads(pet_row["pet_data"]) if pet_row else seller_pet

                    # Return item to inventory
                    inv = fresh_pet.get("inventory", [])
                    item_name_lower = listing["item_name"].lower()
                    idx = next(
                        (i for i, it in enumerate(inv)
                         if isinstance(it, dict) and it.get("name", "").lower() == item_name_lower),
                        None,
                    )
                    if idx is not None:
                        inv[idx]["count"] = inv[idx].get("count", 1) + listing["quantity"]
                    else:
                        inv.append(_enrich_item(
                            listing["item_name"],
                            listing["item_type"],
                            listing["item_rarity"],
                            listing["quantity"],
                        ))
                    fresh_pet["inventory"] = inv

                    await db.execute(
                        "INSERT OR REPLACE INTO pets (user_id, pet_data) VALUES (?, ?)",
                        (str(seller_id), json.dumps(fresh_pet, default=str)),
                    )
                    from datetime import datetime as _dt
                    await db.execute(
                        "UPDATE bazaar SET status='cancelled', completed_at=? WHERE listing_id=?",
                        (_dt.utcnow().isoformat(), listing_id),
                    )
                    await db.commit()
                    return {"ok": True}
        except Exception as e:
            logger.error(f"bazaar_cancel_listing error: {e}", exc_info=True)
            return {"ok": False, "error": "Internal server error"}


# Global instance
pets_db = PetsDatabase()
