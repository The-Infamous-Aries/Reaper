import asyncio
import json
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, cast, TypedDict
import logging

logger = logging.getLogger(__name__)

class InventoryItem(TypedDict):
    name: str
    type: str
    rarity: str
    count: int
from datetime import datetime

from Systems.Functions.optimal_file_manager import OptimalFileManager


class UserDataManager:
    _instance: Optional["UserDataManager"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True
        self.file_manager = OptimalFileManager(max_cache_size=2000, ttl_seconds=600)
        self.users_path = self.file_manager.users_path
        self.json_path = self.file_manager.json_path
        self.bot_logs_path = self.json_path / "bot_logs.json"
        self._user_cache: Dict[str, Dict[str, Any]] = {}
        self._user_locks: Dict[str, asyncio.Lock] = {}
        self._dirty_users: Dict[str, bool] = {}
        self._bot_logs_lock = asyncio.Lock()
        self._json_locks: Dict[str, asyncio.Lock] = {}
        self._shutdown = asyncio.Event()
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self._flush_task = loop.create_task(self._flush_loop())
            else:
                self._flush_task = None
        except RuntimeError:
            self._flush_task = None

    def _user_lock(self, user_id: str) -> asyncio.Lock:
        k = str(user_id)
        if k not in self._user_locks:
            self._user_locks[k] = asyncio.Lock()
        return self._user_locks[k]

    def _get_json_lock(self, key: str) -> asyncio.Lock:
        k = str(key)
        if k not in self._json_locks:
            self._json_locks[k] = asyncio.Lock()
        return self._json_locks[k]

    def _user_file(self, user_id: str) -> Path:
        return self.file_manager.get_user_file_path(str(user_id))

    def _default_user(self, user_id: str, username: Optional[str]) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat()
        return {
            "user_id": str(user_id),
            "username": username or "Unknown",
            "created_at": now,
            "last_updated": now,
            "pets": {"pet_data": None},
        }

    async def _flush_loop(self):
        while not self._shutdown.is_set():
            await asyncio.sleep(2)
            to_flush = [uid for uid, dirty in list(self._dirty_users.items()) if dirty]
            
            if not to_flush:
                continue

            # Batch flush with semaphore to limit file descriptors
            # Although python handles this well, limiting to 50 concurrent writes is safe
            sem = asyncio.Semaphore(50)
            
            async def protected_flush(uid):
                async with sem:
                    try:
                        await self._flush_user(uid)
                    except Exception as e:
                        logger.error(f"Error flushing user {uid}: {e}")

            # Gather all flushes in parallel
            await asyncio.gather(*(protected_flush(uid) for uid in to_flush))

    async def _flush_user_internal(self, user_id: str):
        logger.debug(f"Flushing user data internally for user_id: {user_id}")
        # Internal flush that assumes lock is ALREADY held
        data = self._user_cache.get(str(user_id))
        if not data:
            logger.debug(f"No data found in cache for user_id: {user_id}. Removing from dirty users.")
            self._dirty_users.pop(str(user_id), None)
            return
        path = self._user_file(user_id)
        logger.debug(f"Saving user data for user_id: {user_id} to path: {path}")
        saved_successfully = await self.file_manager.save_async(path, data)
        if not saved_successfully:
            logger.error(f"Failed to save user data for user_id: {user_id} to path: {path}. Keeping user marked as dirty.")
            # Do NOT mark as clean, so it will be re-attempted
        else:
            self._dirty_users[str(user_id)] = False
            self._user_cache[str(user_id)] = data # Ensure cache is updated with the data that was just saved
            logger.debug(f"Successfully flushed and marked user_id: {user_id} as clean.")

    async def _flush_user(self, user_id: str):
        async with self._user_lock(user_id):
            await self._flush_user_internal(str(user_id))

    def _process_loaded_data(self, loaded: Dict[str, Any], uid: str) -> Dict[str, Any]:
        if "pets" not in loaded:
            loaded["pets"] = {}

        migrated = False
        
        # 1. Migrate Games to Pet Gambling Stats
        if "games" in loaded and loaded["games"]:
            games = loaded["games"]
            pet_data = loaded.get("pets", {}).get("pet_data")
            if pet_data:
                pet_data = self._migrate_pet(pet_data)
                g_stats = pet_data["gambling_stats"]
                
                mapping = {
                    "slot_machine": "slots",
                    "blackjack": "blackjack",
                    "holdem": "holdem",
                    "craps": "craps",
                    "races": "races"
                }
                
                keys_to_remove = []
                for old_key, new_key in mapping.items():
                    if old_key in games:
                        if g_stats[new_key].get("total_games_played", 0) == 0 and \
                           g_stats[new_key].get("rounds_played", 0) == 0 and \
                           g_stats[new_key].get("games_played", 0) == 0 and \
                           g_stats[new_key].get("races_played", 0) == 0:
                               g_stats[new_key] = games[old_key]
                        
                        keys_to_remove.append(old_key)
                
                for k in keys_to_remove:
                    del games[k]
                    
                loaded["pets"]["pet_data"] = pet_data
                migrated = True

            if not games:
                del loaded["games"]
                migrated = True
        
        # 2. Ensure Pet Data is Migrated
        if loaded.get("pets", {}).get("pet_data"):
             pet_data = loaded["pets"]["pet_data"]
             new_pet_data = self._migrate_pet(pet_data)
             if new_pet_data != pet_data:
                 loaded["pets"]["pet_data"] = new_pet_data
                 migrated = True

        if migrated:
            self._dirty_users[uid] = True
        else:
            self._dirty_users[uid] = False
            
        return loaded

    async def _get_user_data_internal(self, user_id: str, username: Optional[str] = None) -> Dict[str, Any]:
        uid = str(user_id)
        data = self._user_cache.get(uid)
        if data:
            if username and data.get("username") != username:
                data["username"] = username
                data["last_updated"] = datetime.utcnow().isoformat()
                self._dirty_users[uid] = True
            return data
            
        path = self._user_file(uid)
        loaded = await self.file_manager.load_async(path, self._default_user(uid, username))
        loaded = self._process_loaded_data(loaded, uid)
        self._user_cache[uid] = loaded
        return loaded

    def get_user_data_sync(self, user_id: str, username: Optional[str] = None) -> Dict[str, Any]:
        uid = str(user_id)
        data = self._user_cache.get(uid)
        if data:
            if username and data.get("username") != username:
                data["username"] = username
                data["last_updated"] = datetime.utcnow().isoformat()
                self._dirty_users[uid] = True
            return data
            
        path = self._user_file(uid)
        loaded = self.file_manager.load(path, self._default_user(uid, username))
        loaded = self._process_loaded_data(loaded, uid)
        self._user_cache[uid] = loaded
        return loaded

    async def get_user_data(self, user_id: str, username: Optional[str] = None) -> Dict[str, Any]:
        async with self._user_lock(user_id):
            return await self._get_user_data_internal(user_id, username)

    async def save_user_data(self, user_id: str, username: str, data: Dict[str, Any]) -> bool:
        async with self._user_lock(user_id):
            uid = str(user_id)
            data["last_updated"] = datetime.utcnow().isoformat()
            if username:
                data["username"] = username
            self._user_cache[uid] = data
            self._dirty_users[uid] = True
            await self._flush_user_internal(uid)
            return True

    async def update_user_data(self, user_id: str, updates: Dict[str, Any], username: Optional[str] = None) -> bool:
        async with self._user_lock(user_id):
            base = await self._get_user_data_internal(user_id, username)
            def merge(dst: Dict[str, Any], src: Dict[str, Any]):
                for k, v in src.items():
                    if isinstance(v, dict) and isinstance(dst.get(k), dict):
                        merge(dst[k], v)
                    else:
                        dst[k] = v
            merge(base, updates or {})
            base["last_updated"] = datetime.utcnow().isoformat()
            self._user_cache[str(user_id)] = base
            self._dirty_users[str(user_id)] = True
            await self._flush_user_internal(str(user_id))
            return True

    def get_pet_data(self, user_id: str, username: Optional[str] = None) -> Optional[Dict[str, Any]]:
        data = self.get_user_data_sync(user_id, username)
        return data.get("pets", {}).get("pet_data")

    async def get_pet_data_async(self, user_id: str, username: Optional[str] = None) -> Optional[Dict[str, Any]]:
        async with self._user_lock(user_id):
            data = await self._get_user_data_internal(user_id, username)
            return data.get("pets", {}).get("pet_data")

    async def save_pet_data(self, user_id: str, username_or_pet: Optional[Union[str, Dict[str, Any]]], pet_data: Optional[Dict[str, Any]] = None) -> bool:
        if isinstance(username_or_pet, dict) and pet_data is None:
            username = None
            pet = self._migrate_pet(username_or_pet)
        else:
            username = username_or_pet if isinstance(username_or_pet, str) else None
            pet = self._migrate_pet(pet_data or {})
            
        async with self._user_lock(user_id):
            data = await self._get_user_data_internal(user_id, username)
            data.setdefault("pets", {})
            data["pets"]["pet_data"] = pet
            if not data.get("active_pet"):
                data["active_pet"] = "pet"
            data["last_updated"] = datetime.utcnow().isoformat()
            self._user_cache[str(user_id)] = data
            self._dirty_users[str(user_id)] = True
            await self._flush_user_internal(str(user_id))
            return True

    async def update_pet_battle_stats(self, user_id: str, mode: str, **kwargs) -> bool:
        """
        Updates specific battle stats for a pet.
        mode: "npc", "pvp", "tournament", "survivor_series"
        kwargs: key-value pairs of stats to increment or update.
                For 'most_eliminations' or 'highest_*', it updates if the new value is higher.
                For other numeric stats (wins, losses, xp, damage), it increments.
        """
        async with self._user_lock(user_id):
            data = await self._get_user_data_internal(user_id)
            if not data:
                return False
            
            # Ensure pet data exists
            if "pets" not in data:
                data["pets"] = {}
            if "pet_data" not in data["pets"] or not data["pets"]["pet_data"]:
                # If no pet data, we can't update battle stats
                return False
                
            pet = data["pets"]["pet_data"]
            
            # Ensure battle_stats structure
            stats = pet.setdefault("battle_stats", {})
            mode_stats = stats.setdefault(mode, {})
            
            username = data.get("username", "Unknown")
            
            for key, value in kwargs.items():
                if key.startswith("most_") or key.startswith("highest_"):
                    current = int(mode_stats.get(key, 0))
                    if int(value) > current:
                        mode_stats[key] = int(value)
                else:
                    # Increment standard stats
                    current = int(mode_stats.get(key, 0))
                    mode_stats[key] = current + int(value)
            
            # Mark as dirty and trigger save/flush
            data["last_updated"] = datetime.utcnow().isoformat()
            self._user_cache[str(user_id)] = data
            self._dirty_users[str(user_id)] = True
            await self._flush_user_internal(str(user_id))
            return True

    async def update_pet_gambling_stats(self, user_id: str, game_type: str, winnings: int, bet_amount: int = 0, extra_data: Optional[Dict[str, Any]] = None) -> bool:
        """
        Updates gambling stats for a pet.
        game_type: "blackjack", "craps", "holdem", "races", "slots"
        winnings: Net XP change (positive for win, negative for loss)
        bet_amount: Amount bet (for highest_bet tracking)
        extra_data: Game-specific stats (e.g. difficulty for slots)
        """
        async with self._user_lock(user_id):
            data = await self._get_user_data_internal(user_id)
            if not data:
                return False

            if "pets" not in data:
                data["pets"] = {}
            if "pet_data" not in data["pets"] or not data["pets"]["pet_data"]:
                return False

            pet = data["pets"]["pet_data"]
            game_stats = gambling_stats.setdefault(game_type, {
                "wins": 0,
                "losses": 0,
                "pushes": 0,
                "total_played": 0,
                "total_won": 0, # Total amount won
                "total_lost": 0, # Total amount lost
                "net_xp": 0 # Net XP change
            })

            # Update standard stats
            game_stats["total_played"] += 1
            game_stats["net_xp"] += winnings

            if winnings > 0:
                game_stats["wins"] += 1
                game_stats["total_won"] += winnings
            elif winnings < 0:
                game_stats["losses"] += 1
                game_stats["total_lost"] += abs(winnings)
            # For pushes, we'll handle it in extra_data if provided

            # Game-specific updates
            if game_type == "races":
                # No specific extra stats for races beyond standard
                pass
            elif game_type == "slots":
                # No specific extra stats for slots beyond standard
                pass
            elif game_type == "blackjack":
                if extra_data and extra_data.get("is_push"): # Assuming extra_data can indicate a push
                    game_stats["pushes"] += 1
            elif game_type == "holdem":
                # No specific extra stats for holdem beyond standard
                pass
            elif game_type == "craps":
                # No specific extra stats for craps beyond standard
                pass

            # Apply any extra data provided (e.g., highest bet, specific game outcomes)
            if extra_data:
                for key, value in extra_data.items():
                    if key == "highest_bet": # Example of an extra stat
                        game_stats[key] = max(game_stats.get(key, 0), value)
                    elif key == "is_push" and game_type != "blackjack": # Handle pushes for other games if applicable
                        game_stats["pushes"] += 1
                    # Add other extra_data handling as needed

            # Mark as dirty and trigger save/flush
            data["last_updated"] = datetime.utcnow().isoformat()
            self._user_cache[str(user_id)] = data
            self._dirty_users[str(user_id)] = True
            await self._flush_user_internal(str(user_id))
            return True


    async def delete_pet_data(self, user_id: str, username: Optional[str] = None) -> bool:
        async with self._user_lock(user_id):
            data = await self._get_user_data_internal(user_id, username)
            changed = False
            pets = data.get("pets", {})
            if "pet_data" in pets:
                del pets["pet_data"]
                changed = True
            ap = data.get("active_pet")
            if isinstance(ap, str) and ap in pets:
                try:
                    del pets[ap]
                except Exception:
                    pass
                data["active_pet"] = None
                changed = True
                
            if changed:
                data["pets"] = pets
                self._user_cache[str(user_id)] = data
                self._dirty_users[str(user_id)] = True
                await self._flush_user_internal(str(user_id))
                return True
            return False

    async def set_pet_action_label(self, user_id: str, pet_id: str, action: str, label: str) -> bool:
        async with self._user_lock(user_id):
            data = await self._get_user_data_internal(user_id)
            if not data or "pets" not in data or "pet_data" not in data["pets"]:
                return False

            pet = data["pets"]["pet_data"]
            if pet.get("id") != pet_id: # Assuming pet_id is the unique identifier for the active pet
                return False

            if "action_labels" not in pet:
                pet["action_labels"] = {"attack": None, "defend": None, "charge": None} # Initialize if not present

            pet["action_labels"][action] = label if label else None # Set label for specific action
            data["pets"]["pet_data"] = pet

            data["last_updated"] = datetime.utcnow().isoformat()
            self._user_cache[str(user_id)] = data
            self._dirty_users[str(user_id)] = True
            await self._flush_user_internal(str(user_id))
            return True

    async def update_pet_name(self, user_id: str, pet_id: str, new_name: str) -> bool:
        async with self._user_lock(user_id):
            data = await self._get_user_dat-internal(user_id)
            if not data or "pets" not in data or "pet_data" not in data["pets"]:
                return False

            pet = data["pets"]["pet_data"]
            if pet.get("id") != pet_id: # Assuming pet_id is the unique identifier for the active pet
                return False

            pet["name"] = new_name
            data["pets"]["pet_data"] = pet

            data["last_updated"] = datetime.utcnow().isoformat()
            self._user_cache[str(user_id)] = data
            self._dirty_users[str(user_id)] = True
            await self._flush_user_internal(str(user_id))
            return True

    def _get_level_experience(self, level: int) -> int:
        """
        Calculate XP needed to pass current level (reach level+1).
        Level 1 needs 200 XP to reach Level 2.
        Then 3% exponential growth.
        Formula: 200 * (1.03 ^ (level - 1))
        """
        if level < 1: level = 1
        return int(200 * (1.03 ** (level - 1)))

    async def add_pet_experience(self, user_id: str, amount: int, source: str = "battle") -> Tuple[bool, Optional[Dict[str, Any]]]:
        async with self._user_lock(user_id):
            data = await self._get_user_data_internal(user_id)
            if not data or "pets" not in data or "pet_data" not in data["pets"]:
                return False, None
            
            pet = data["pets"]["pet_data"]
            
            # Ensure basic stats exist via migrate
            pet = self._migrate_pet(pet)
            data["pets"]["pet_data"] = pet

            old_level = int(pet["level"])
            current_exp = int(pet["experience"])
            new_exp = current_exp + int(amount)
            pet["experience"] = new_exp
            
            # --- DEBUG LOGGING ---
            logger.debug(f"add_pet_experience: User {user_id}, Amount {amount}, Source {source}")
            logger.debug(f"Initial: Level {old_level}, Current XP {current_exp}, New XP {new_exp}")
            # --- END DEBUG LOGGING ---

            # Track Source XP
            xp_key = f"{source}_xp_earned"
            pet[xp_key] = int(pet.get(xp_key, 0)) + int(amount)
            pet["total_xp_earned"] = int(pet.get("total_xp_earned", 0)) + int(amount)

            gains = {"ATT": 0, "DEF": 0, "INT": 0, "DEX": 0, "HAP": 0, "ENE": 0}
            
            # Level Up Logic
            if amount >= 0:
                while True:
                    exp_needed = self._get_level_experience(pet["level"])
                    # --- DEBUG LOGGING ---
                    logger.debug(f"Level Up Check: Pet Level {pet['level']}, XP Needed {exp_needed}, Current New XP {new_exp}")
                    # --- END DEBUG LOGGING ---
                    if new_exp < exp_needed:
                        break
                    new_exp -= exp_needed
                    pet["level"] += 1
                    pet["experience"] = new_exp
                    
                    # Stat gains
                    points_per_category = 1 + ((pet["level"] - 1) // 10)
                    
                    # Physical
                    for _ in range(points_per_category):
                        if random.choice([True, False]):
                            pet["ATT"] = int(pet.get("ATT", 0)) + 1
                            gains["ATT"] += 1
                        else:
                            pet["DEF"] = int(pet.get("DEF", 0)) + 1
                            gains["DEF"] += 1
                    
                    # Mental
                    for _ in range(points_per_category):
                        if random.choice([True, False]):
                            pet["INT"] = int(pet.get("INT", 0)) + 1
                            gains["INT"] += 1
                        else:
                            pet["DEX"] = int(pet.get("DEX", 0)) + 1
                            gains["DEX"] += 1
                    
                    # Vitals
                    for _ in range(points_per_category):
                        if random.choice([True, False]):
                            pet["HAP"] = int(pet.get("HAP", 0)) + 1
                            gains["HAP"] += 1
                        else:
                            pet["ENE"] = int(pet.get("ENE", 0)) + 1
                            gains["ENE"] += 1
            else:
                # Level Down Logic (Handle negative XP)
                # Calculate total XP first to handle multi-level drops
                total_xp = 0
                for lvl in range(1, pet["level"]):
            
                    data["last_updated"] = datetime.utcnow().isoformat()
                    self._user_cache[str(user_id)] = data
                    self._dirty_users[str(user_id)] = True
                    await self._flush_user_internal(str(user_id))
                    return True, pet
                total_xp += self._get_level_experience(lvl)
                total_xp += current_exp
                
                # Subtract loss (amount is negative)
                new_total = max(0, total_xp + amount)
                
                # Recompute level
                new_level = 1
                remainder = new_total
                while True:
                    needed = self._get_level_experience(new_level)
                    if remainder < needed:
                        break
                    remainder -= needed
                    new_level += 1
                
                pet["level"] = new_level
                pet["experience"] = remainder
                # We don't reduce stats on level down to avoid complex rollback logic
                # Just level and XP adjustment

            data["last_updated"] = datetime.utcnow().isoformat()
            self._user_cache[str(user_id)] = data
            self._dirty_users[str(user_id)] = True
            await self._flush_user_internal(str(user_id))

            if pet["level"] > old_level:
                level_gains = {
                    "old_level": old_level,
                    "new_level": pet["level"],
                    "ATT": gains["ATT"],
                    "DEF": gains["DEF"],
                    "INT": gains["INT"],
                    "DEX": gains["DEX"],
                    "HAP": gains["HAP"],
                    "ENE": gains["ENE"],
                    "source": source
                }
                return True, level_gains
            elif pet["level"] < old_level:
                 level_loss = {
                    "old_level": old_level,
                    "new_level": pet["level"],
                    "source": source,
                    "lost_xp": abs(amount)
                 }
                 return True, level_loss
            
            return True, None

    @staticmethod
    def _consolidate_inventory(inventory: List[Any]) -> List[InventoryItem]:
        """
        Consolidates inventory items into stacks.
        Handles legacy string items and dicts without counts.
        """
        consolidated: List[InventoryItem] = []
        seen: Dict[Any, int] = {}  # key -> index in consolidated

        for item in inventory:
            # 1. Normalize item to dict
            item_dict: InventoryItem
            if isinstance(item, str):
                item_dict = {"name": item, "type": "Material", "rarity": "Common", "count": 1}
            elif isinstance(item, dict):
                item_dict = cast(InventoryItem, item.copy())
                if "count" not in item_dict:
                    item_dict["count"] = 1
            else:
                continue # Skip invalid items

            # 2. Generate Key
            name = item_dict.get("name", "Unknown")
            itype = item_dict.get("type", "Material")
            rarity = item_dict.get("rarity", "Common")
            
            # Simple key based on identity
            key = f"{name}|{itype}|{rarity}"
            
            # 3. Merge or Add
            if key in seen:
                idx = seen[key]
                consolidated[idx]["count"] += item_dict["count"]
            else:
                consolidated.append(item_dict)
                seen[key] = len(consolidated) - 1
        
        return consolidated

    async def update_pet_data(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """
        Generic update for pet data fields (name, species, etc).
        For stats/xp, use add_pet_experience.
        """
        async with self._user_lock(user_id):
            data = await self._get_user_data_internal(user_id)
            if not data or "pets" not in data or "pet_data" not in data["pets"]:
                return False
            
            pet = data["pets"]["pet_data"]
            for k, v in updates.items():
                pet[k] = v
            
            data["last_updated"] = datetime.utcnow().isoformat()
            self._user_cache[str(user_id)] = data
            self._dirty_users[str(user_id)] = True
            await self._flush_user_internal(str(user_id))
            return True, {"level_up": old_level < pet["level"], "new_level": pet["level"], "gains": gains}
        
    async def increment_pet_stats(self, user_id: str, stats_to_increment: Dict[str, int]) -> bool:
        async with self._user_lock(user_id):
            data = await self._get_user_data_internal(user_id)
            if not data or "pets" not in data or "pet_data" not in data["pets"]:
                return False
            
            pet = data["pets"]["pet_data"]
            
            for stat, value in stats_to_increment.items():
                pet[stat] = pet.get(stat, 0) + value

            data["last_updated"] = datetime.utcnow().isoformat()
            self._user_cache[str(user_id)] = data
            self._dirty_users[str(user_id)] = True
            await self._flush_user_internal(str(user_id))
            return True

    def _migrate_pet(self, pet: Dict[str, Any]) -> Dict[str, Any]:
        pet = dict(pet or {})
        
        # 1. Inventory Migration & Consolidation
        raw_inv = pet.get("inventory", [])
        if not isinstance(raw_inv, list):
            raw_inv = []
        
        pet["inventory"] = self._consolidate_inventory(raw_inv)
            
        pet.setdefault("equipment", {})
        if not isinstance(pet["equipment"], dict):
            pet["equipment"] = {}
            
        # Ensure equipment structure
        equip = pet["equipment"]
        
        # Ensure List Slots (Gems, Monsters)
        for list_slot in ["Gems", "Monsters"]:
            if list_slot in equip:
                val = equip[list_slot]
                if isinstance(val, dict):
                    equip[list_slot] = [val]
                elif not isinstance(val, list):
                    equip[list_slot] = []
            else:
                # Optional: leave it missing or init? 
                # Old code inited if missing, but it was messy.
                # Let's clean it up if it's junk, but don't force empty list if None.
                pass
        
        # Ensure Dict Slots (Material, Hat, Potion)
        for dict_slot in ["Material", "Hat", "Potion"]:
            if dict_slot in equip:
                val = equip[dict_slot]
                if isinstance(val, list):
                    if val:
                        equip[dict_slot] = val[0]
                    else:
                        del equip[dict_slot]
                elif not isinstance(val, dict):
                     del equip[dict_slot]

            
        pet.setdefault("ATT", pet.pop("attack", 0))
        pet.setdefault("DEF", pet.pop("defense", 0))
        pet.setdefault("INT", pet.pop("intelligence", 0))
        pet.setdefault("DEX", pet.pop("dexterity", 0))
        pet.setdefault("HAP", pet.pop("max_happiness", pet.pop("happiness", 0)))
        pet.setdefault("ENE", pet.pop("max_energy", pet.pop("energy", 0)))
        pet.setdefault("level", 1)
        if "xp" in pet: pet.setdefault("experience", pet.pop("xp"))
        pet.setdefault("experience", 0)
        pet.setdefault("element2", None)

        # Core Identity
        pet.setdefault("category", "land")
        pet.setdefault("element", "fire")
        pet.setdefault("species", pet.get("name", "Pet"))

        # Mission & Training Stats
        for source in ["mission", "battle", "training", "ss"]:
            xp_key = f"{source}_xp_earned"
            pet.setdefault(xp_key, 0)
            
        pet.setdefault("total_xp_earned", 0)
        pet.setdefault("missions_completed", 0)
        pet.setdefault("missions_failed", 0)

        # Action Labels
        action_labels = pet.setdefault("action_labels", {})
        action_labels.setdefault("attack", None)
        action_labels.setdefault("defend", None)
        action_labels.setdefault("charge", None)

        pet.setdefault("mission_xp_gambled_total", 0)
        pet.setdefault("mission_xp_gambled_won", 0)
        pet.setdefault("mission_xp_gambled_lost", 0)
        pet.setdefault("mission_gambles_success", 0)
        pet.setdefault("mission_gambles_failed", 0)
        pet.setdefault("training_completed", 0)
        pet.setdefault("training_failed", 0)
        pet.setdefault("play_attempts", 0)
        pet.setdefault("xp_sources", {})

        battle_stats = pet.setdefault("battle_stats", {})
        
        def move_stat(target_dict, target_key, source_key):
            if source_key in pet:
                target_dict.setdefault(target_key, int(pet.pop(source_key, 0)))
            else:
                target_dict.setdefault(target_key, 0)

        npc = battle_stats.setdefault("npc", {})
        move_stat(npc, "wins", "npc_battles_won")
        move_stat(npc, "losses", "npc_battles_lost")
        move_stat(npc, "xp_earned", "npc_battle_xp_earned")

        pvp = battle_stats.setdefault("pvp", {})
        move_stat(pvp, "wins", "pvp_battles_won")
        move_stat(pvp, "losses", "pvp_battles_lost")
        move_stat(pvp, "xp_earned", "pvp_battle_xp_earned")
        move_stat(pvp, "eliminations", "users_eliminated")

        tourn = battle_stats.setdefault("tournament", {})
        move_stat(tourn, "wins", "tournament_matches_won")
        move_stat(tourn, "losses", "tournament_matches_lost")
        move_stat(tourn, "xp_earned", "tournament_xp_earned")
        
        ss = battle_stats.setdefault("survivor_series", {})
        move_stat(ss, "wins", "ss_wins")
        move_stat(ss, "losses", "ss_losses")
        move_stat(ss, "eliminations", "ss_total_eliminations")
        move_stat(ss, "most_eliminations", "ss_most_eliminations")
        move_stat(ss, "xp_earned", "ss_xp_earned")
        
        legacy_keys = [
            "battles_won", "battles_lost", "maintenance", "max_maintenance", 
            "search_xp_earned", "charge_xp_earned", "play_xp_earned", "repair_xp_earned",
            "daily_xp_earned", "quest_xp_earned", "combiner_battle_xp_earned",
            "combiner_pvp_victory_xp_earned", "combiner_pvp_defeat_xp_earned",
            "mega_fight_xp_earned", "rpg_event_xp_earned",
            "slots_summary", "blackjack_summary", "holdem_summary", "craps_summary", "races_summary"
        ]
        for k in legacy_keys:
            pet.pop(k, None)

        gambling_stats = pet.setdefault("gambling_stats", {})
        
        gambling_stats.setdefault("slots", {
            "total_games_played": 0, "xp_won_total": 0, "xp_lost_total": 0,
            "highest_xp_win": 0, "highest_xp_bet": 0, 
            "games_by_difficulty": {"easy": 0, "medium": 0, "hard": 0, "insanity": 0}
        })
        gambling_stats.setdefault("blackjack", {
            "rounds_played": 0, "rounds_won": 0, "rounds_lost": 0,
            "xp_won_total": 0, "xp_lost_total": 0, "highest_xp_win": 0, "highest_xp_bet": 0
        })
        gambling_stats.setdefault("holdem", {
            "games_played": 0, "games_won": 0, "games_lost": 0,
            "xp_won_total": 0, "xp_lost_total": 0, "highest_xp_win": 0, "highest_xp_bet": 0
        })
        gambling_stats.setdefault("craps", {
            "games_played": 0, "games_won": 0, "games_lost": 0,
            "xp_won_total": 0, "xp_lost_total": 0, "highest_xp_win": 0, "highest_xp_bet": 0
        })
        gambling_stats.setdefault("races", {
            "races_played": 0, "races_won": 0, "races_lost": 0,
            "xp_won_total": 0, "xp_lost_total": 0, "highest_xp_win": 0, "highest_xp_bet": 0
        })

        return pet

    async def batch_load_user_data(self, user_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        results: Dict[str, Dict[str, Any]] = {}
        tasks = [self.get_user_data(str(uid)) for uid in user_ids]
        outs = await asyncio.gather(*tasks, return_exceptions=True)
        for i, uid in enumerate(user_ids):
            res = outs[i]
            if not isinstance(res, Exception):
                results[str(uid)] = cast(Dict[str, Any], res)
        return results

    async def update_shooting_range_stats(self, user_id: str, session_data: Dict[str, Any]) -> bool:
        async with self._user_lock(user_id):
            data = await self._get_user_data_internal(user_id)
            if not data:
                return False

            hits = int(session_data.get("hits", 0))
            total_shots = int(session_data.get("total_shots", 0))
            rounds = session_data.get("rounds", 5)

            games = data.setdefault("games", {})
            stats = games.setdefault("shooting_range", {
                "sessions_played": 0, "total_hits": 0, "total_shots": 0,
                "best_records": {
                    "5": {"accuracy": 0.0, "hits": 0},
                    "15": {"accuracy": 0.0, "hits": 0},
                    "25": {"accuracy": 0.0, "hits": 0},
                    "50": {"accuracy": 0.0, "hits": 0},
                    "100": {"accuracy": 0.0, "hits": 0}
                },
                "attempts_by_round": {"5": 0, "15": 0, "25": 0, "50": 0, "100": 0}
            })
            stats["sessions_played"] += 1
            stats["total_hits"] += hits
            stats["total_shots"] += total_shots
            acc = (hits / max(1, total_shots)) * 100.0
            rk = str(rounds)
            best = stats["best_records"].get(rk, {"accuracy": 0.0, "hits": 0})
            if acc > best["accuracy"] or (acc == best["accuracy"] and hits > best["hits"]):
                stats["best_records"][rk] = {"accuracy": acc, "hits": hits}
            stats["attempts_by_round"][rk] = int(stats["attempts_by_round"].get(rk, 0)) + 1
            
            data["last_updated"] = datetime.utcnow().isoformat()
            self._user_cache[str(user_id)] = data
            self._dirty_users[str(user_id)] = True
            await self._flush_user_internal(str(user_id))
            return True

    async def get_shooting_range_stats(self, user_id: str) -> Dict[str, Any]:
        d = await self.get_user_data(str(user_id))
        games = d.setdefault("games", {})
        stats = games.setdefault("shooting_range", {
            "sessions_played": 0, "total_hits": 0, "total_shots": 0,
            "best_records": {
                "5": {"accuracy": 0.0, "hits": 0},
                "15": {"accuracy": 0.0, "hits": 0},
                "25": {"accuracy": 0.0, "hits": 0},
                "50": {"accuracy": 0.0, "hits": 0},
                "100": {"accuracy": 0.0, "hits": 0}
            },
            "attempts_by_round": {"5": 0, "15": 0, "25": 0, "50": 0, "100": 0}
        })
        self._user_cache[str(user_id)] = d
        self._dirty_users[str(user_id)] = True
        return stats

    async def get_json_data(self, key: str, default_data: Any = None) -> Any:
        async with self._get_json_lock(key):
            k = str(key)
            if k.startswith("walktru_"):
                mapping = {
                    "horror": "Horror.json",
                    "ganster": "Ganster.json",
                    "knight": "Knight.json",
                    "robot": "Robot.json",
                    "western": "Western.json",
                    "wizard": "Wizard.json",
                }
                name = k.replace("walktru_", "", 1)
                fname = mapping.get(name)
                if fname:
                    path = self.file_manager.walk_tru_dir / fname
                    data = await self.file_manager.load_async(path, default_data if default_data is not None else {})
                    return data if data is not None else (default_data if default_data is not None else {})
            path = self.json_path / f"{k}.json"
            data = await self.file_manager.load_async(path, default_data if default_data is not None else {})
            return data if data is not None else (default_data if default_data is not None else {})

    async def save_json_data(self, key: str, data: Any) -> bool:
        async with self._get_json_lock(key):
            path = self.json_path / f"{str(key)}.json"
            return await self.file_manager.save_async(path, data)

    async def load_json_data(self, key: str) -> Any:
        async with self._get_json_lock(key):
            k = str(key)
            if k.startswith("walktru_"):
                mapping = {
                    "horror": "Horror.json",
                    "ganster": "Ganster.json",
                    "knight": "Knight.json",
                    "robot": "Robot.json",
                    "western": "Western.json",
                    "wizard": "Wizard.json",
                }
                name = k.replace("walktru_", "", 1)
                fname = mapping.get(name)
                if fname:
                    path = self.file_manager.walk_tru_dir / fname
                    return await self.file_manager.load_async(path, {})
            path = self.json_path / f"{k}.json"
            return await self.file_manager.load_async(path, {})

    async def get_bot_logs(self, user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        async with self._bot_logs_lock:
            logs = await self.file_manager.load_async(self.bot_logs_path, {"logs": []})
        entries = logs.get("logs", [])
        if user_id:
            entries = [e for e in entries if str(e.get("user_id")) == str(user_id)]
        return entries[-int(limit or 50):]

    async def get_bot_log_count(self, user_id: Optional[str] = None) -> int:
        async with self._bot_logs_lock:
            logs = await self.file_manager.load_async(self.bot_logs_path, {"logs": []})
        entries = logs.get("logs", [])
        if user_id:
            entries = [e for e in entries if str(e.get("user_id")) == str(user_id)]
        return len(entries)

    async def add_bot_log(self, entry: Dict[str, Any]) -> bool:
        async with self._bot_logs_lock:
            logs = await self.file_manager.load_async(self.bot_logs_path, {"logs": []})
            entries = logs.get("logs", [])
            entries.append(entry)
            # Limit logs to prevent infinite growth (e.g., keep last 5000)
            if len(entries) > 5000:
                entries = entries[-5000:]
            logs["logs"] = entries
            return await self.file_manager.save_async(self.bot_logs_path, logs)

    async def clear_bot_logs(self, count: Optional[int] = None) -> int:
        async with self._bot_logs_lock:
            logs = await self.file_manager.load_async(self.bot_logs_path, {"logs": []})
            entries = logs.get("logs", [])
            if count is None or int(count) >= len(entries):
                cleared = len(entries)
                logs["logs"] = []
                await self.file_manager.save_async(self.bot_logs_path, logs)
                return cleared
            cleared = int(count)
            logs["logs"] = entries[:-cleared]
            await self.file_manager.save_async(self.bot_logs_path, logs)
            return cleared

    async def get_user_theme_data(self, user_id: str, username: Optional[str] = None) -> Dict[str, Any]:
        d = await self.get_user_data(str(user_id), username)
        theme = d.setdefault("theme", {})
        self._user_cache[str(user_id)] = d
        self._dirty_users[str(user_id)] = True
        return theme

    async def save_theme_system_data(self, user_id: str, theme_data: Dict[str, Any]) -> bool:
        async with self._user_lock(user_id):
            data = await self._get_user_data_internal(user_id)
            data["theme_system"] = theme_data
            self._user_cache[str(user_id)] = data
            self._dirty_users[str(user_id)] = True
            await self._flush_user_internal(str(user_id))
            return True

    async def shutdown(self):
        self._shutdown.set()
        if getattr(self, "_flush_task", None):
            try:
                await asyncio.sleep(0.05)
            except Exception:
                pass
        for uid in list(self._dirty_users.keys()):
            try:
                await self._flush_user(uid)
            except Exception:
                pass


user_data_manager = UserDataManager()
