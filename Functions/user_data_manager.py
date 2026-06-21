import asyncio
import random
from pathlib import Path
import json
from typing import Any, Dict, List, Optional, Tuple, Union, cast, TypedDict
import logging
from Systems.Functions.pets_db import pets_db

logger = logging.getLogger(__name__)

class InventoryItem(TypedDict):
    name: str
    type: str
    rarity: str
    count: int
from datetime import datetime


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
        # All file-based caching and management is removed.
        self._legacy_users_dir = Path(r"c:\Users\codyr\DiscordBots\Reaper\Systems\Data\Users")
        self._user_locks: Dict[str, asyncio.Lock] = {}

        # Expose file_manager so pet_brain.py can call user_data_manager.file_manager.get_data(...)
        from Systems.Functions.optimal_file_manager import OptimalFileManager
        self.file_manager = OptimalFileManager()

    def _get_user_lock(self, user_id: str) -> asyncio.Lock:
        """Returns a lock for a given user ID."""
        k = str(user_id)
        if k not in self._user_locks:
            self._user_locks[k] = asyncio.Lock()
        return self._user_locks[k]

    async def _get_pet_data_no_lock(self, user_id: str, username: Optional[str] = None) -> Optional[Dict[str, Any]]:
        pet_data = await pets_db.get_pet_data(user_id)
        if pet_data is not None:
            return self._migrate_pet(pet_data)

        legacy_pet = await self._load_legacy_pet_data(user_id)
        if legacy_pet is not None:
            migrated_pet = self._migrate_pet(legacy_pet)
            await pets_db.save_pet_data(user_id, migrated_pet)
            if username:
                await pets_db.save_user_profile(user_id, username)
            logger.info(f"Migrated legacy pet data for user {user_id} into shared pets storage")
            return migrated_pet

        return None

    async def _save_pet_data_no_lock(self, user_id: str, pet_data: Dict[str, Any], username: Optional[str] = None) -> bool:
        pet = self._migrate_pet(pet_data or {})
        success = await pets_db.save_pet_data(user_id, pet)
        if success and username:
            await pets_db.save_user_profile(user_id, username)
        return success

    async def get_user_data(self, user_id: str, username: Optional[str] = None) -> Dict[str, Any]:
        """Gets all user data from the database and merges it."""
        async with self._get_user_lock(user_id):
            user_profile = await pets_db.get_user_profile(user_id)
            pet_data = await self._get_pet_data_no_lock(user_id, username)

            if not user_profile:
                # If no profile exists, create one
                await pets_db.save_user_profile(user_id, username or "Unknown")
                user_profile = await pets_db.get_user_profile(user_id)
            elif username and user_profile.get("username") != username:
                # If username has changed, update it
                await pets_db.save_user_profile(user_id, username)
                user_profile["username"] = username

            # Combine the data
            full_user_data = user_profile or {}
            full_user_data["pets"] = {"pet_data": self._migrate_pet(pet_data) if pet_data else None}
            
            return full_user_data

    async def save_user_data(self, user_id: str, username: str, data: Dict[str, Any]) -> bool:
        """Saves user profile and pet data to the database."""
        async with self._get_user_lock(user_id):
            # Extract pet data and save it
            if "pets" in data and "pet_data" in data["pets"]:
                pet_data = self._migrate_pet(data["pets"]["pet_data"])
                await self._save_pet_data_no_lock(user_id, pet_data, username)
            
            # Save user profile
            await pets_db.save_user_profile(user_id, username)
            return True

    async def update_user_data(self, user_id: str, updates: Dict[str, Any], username: Optional[str] = None) -> bool:
        """Updates user data by merging new data with existing data."""
        async with self._get_user_lock(user_id):
            # Fetch current data without re-acquiring the lock (avoids deadlock)
            user_profile = await pets_db.get_user_profile(user_id)
            pet_data = await self._get_pet_data_no_lock(user_id, username)

            if not user_profile:
                await pets_db.save_user_profile(user_id, username or "Unknown")
                user_profile = await pets_db.get_user_profile(user_id)
            elif username and user_profile.get("username") != username:
                await pets_db.save_user_profile(user_id, username)
                if user_profile:
                    user_profile["username"] = username

            current_data: Dict[str, Any] = user_profile or {}
            current_data["pets"] = {"pet_data": self._migrate_pet(pet_data) if pet_data else None}

            # Merge updates
            def merge(dst: Dict[str, Any], src: Dict[str, Any]) -> None:
                for k, v in src.items():
                    if isinstance(v, dict) and isinstance(dst.get(k), dict):
                        merge(dst[k], v)
                    else:
                        dst[k] = v
            merge(current_data, updates or {})

            # Save without re-acquiring the lock
            if "pets" in current_data and "pet_data" in current_data["pets"]:
                pet = self._migrate_pet(current_data["pets"]["pet_data"] or {})
                await self._save_pet_data_no_lock(user_id, pet, current_data.get("username"))

            await pets_db.save_user_profile(user_id, current_data.get("username") or username or "Unknown")
            return True

    async def get_pet_data_async(self, user_id: str, username: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Gets pet data exclusively from the database."""
        async with self._get_user_lock(user_id):
            return await self._get_pet_data_no_lock(user_id, username)

    async def _load_legacy_pet_data(self, user_id: str) -> Optional[Dict[str, Any]]:
        legacy_path = self._legacy_users_dir / f"{user_id}.json"
        if not legacy_path.exists():
            return None

        try:
            raw_data = json.loads(legacy_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to read legacy pet data for user {user_id}: {e}")
            return None

        if not isinstance(raw_data, dict):
            return None

        pets_section = raw_data.get("pets")
        if isinstance(pets_section, dict):
            direct_pet = pets_section.get("pet_data")
            if isinstance(direct_pet, dict) and direct_pet:
                return direct_pet

            active_pet_id = raw_data.get("active_pet") or pets_section.get("active_pet")
            if active_pet_id:
                active_pet = pets_section.get(str(active_pet_id))
                if isinstance(active_pet, dict) and active_pet:
                    return active_pet

            dict_pets = [value for value in pets_section.values() if isinstance(value, dict) and value]
            if len(dict_pets) == 1:
                return dict_pets[0]

        active_pet = raw_data.get("active_pet")
        if isinstance(active_pet, dict) and active_pet:
            return active_pet

        return None

    async def save_pet_data(self, user_id: str, username_or_pet: Optional[Union[str, Dict[str, Any]]], pet_data: Optional[Dict[str, Any]] = None) -> bool:
        """Saves pet data exclusively to the database."""
        async with self._get_user_lock(user_id):
            if isinstance(username_or_pet, dict) and pet_data is None:
                pet = self._migrate_pet(username_or_pet)
                username = None
            else:
                pet = self._migrate_pet(pet_data or {})
                username = cast(Optional[str], username_or_pet) if isinstance(username_or_pet, str) else None

            return await self._save_pet_data_no_lock(user_id, pet, username)

    async def update_pet_battle_stats(self, user_id: str, mode: str, **kwargs) -> bool:
        """
        Updates specific battle stats for a pet, fetching and saving exclusively from the database.
        """
        async with self._get_user_lock(user_id):
            pet = await self._get_pet_data_no_lock(user_id)
            if not pet:
                return False
            
            # Ensure battle_stats structure
            stats = pet.setdefault("battle_stats", {})
            mode_stats = stats.setdefault(mode, {})
            
            for key, value in kwargs.items():
                if key.startswith("most_") or key.startswith("highest_"):
                    current = int(mode_stats.get(key, 0))
                    if int(value) > current:
                        mode_stats[key] = int(value)
                else:
                    # Increment standard stats
                    current = int(mode_stats.get(key, 0))
                    mode_stats[key] = current + int(value)
            
            # Save the updated pet data to the database
            await self._save_pet_data_no_lock(user_id, pet)
            return True

    async def update_pet_gambling_stats(self, user_id: str, game_type: str, winnings: int, bet_amount: int = 0, extra_data: Optional[Dict[str, Any]] = None) -> bool:
        """
        Updates gambling stats for a pet, fetching and saving exclusively from the database.
        """
        async with self._get_user_lock(user_id):
            pet = await self._get_pet_data_no_lock(user_id)
            if not pet:
                return False
            
            # Ensure gambling_stats exists
            if "gambling_stats" not in pet:
                pet["gambling_stats"] = {}
            
            gambling_stats = pet["gambling_stats"]
            
            # Ensure game_type stats exist with correct structure
            if game_type not in gambling_stats:
                if game_type == "slots":
                    gambling_stats[game_type] = {
                        "total_games_played": 0,
                        "xp_won_total": 0,
                        "xp_lost_total": 0,
                        "highest_xp_win": 0,
                        "highest_xp_bet": 0,
                        "games_by_difficulty": {"easy": 0, "medium": 0, "hard": 0, "insanity": 0}
                    }
                elif game_type == "blackjack":
                    gambling_stats[game_type] = {
                        "rounds_played": 0,
                        "rounds_won": 0,
                        "rounds_lost": 0,
                        "pushes": 0,
                        "xp_won_total": 0,
                        "xp_lost_total": 0,
                        "highest_xp_win": 0,
                        "highest_xp_bet": 0
                    }
                elif game_type == "holdem":
                    gambling_stats[game_type] = {
                        "games_played": 0,
                        "games_won": 0,
                        "games_lost": 0,
                        "xp_won_total": 0,
                        "xp_lost_total": 0,
                        "highest_xp_win": 0,
                        "highest_xp_bet": 0
                    }
                elif game_type == "craps":
                    gambling_stats[game_type] = {
                        "games_played": 0,
                        "games_won": 0,
                        "games_lost": 0,
                        "xp_won_total": 0,
                        "xp_lost_total": 0,
                        "highest_xp_win": 0,
                        "highest_xp_bet": 0
                    }
                elif game_type == "races":
                    gambling_stats[game_type] = {
                        "races_played": 0,
                        "races_won": 0,
                        "races_lost": 0,
                        "xp_won_total": 0,
                        "xp_lost_total": 0,
                        "highest_xp_win": 0,
                        "highest_xp_bet": 0
                    }
                elif game_type == "coinflip":
                    gambling_stats[game_type] = {
                        "games_played": 0,
                        "games_won": 0,
                        "games_lost": 0,
                        "xp_won_total": 0,
                        "xp_lost_total": 0,
                        "highest_xp_win": 0,
                        "highest_xp_bet": 0
                    }
                elif game_type == "rps":
                    gambling_stats[game_type] = {
                        "games_played": 0,
                        "games_won": 0,
                        "games_lost": 0,
                        "games_tied": 0,
                        "xp_won_total": 0,
                        "xp_lost_total": 0,
                        "highest_xp_win": 0,
                        "highest_xp_bet": 0
                    }
                elif game_type == "wheel_of_pets":
                    gambling_stats[game_type] = {
                        "games_played": 0,
                        "games_won": 0,
                        "games_lost": 0,
                        "own_pet_jackpots": 0,
                        "xp_won_total": 0,
                        "xp_lost_total": 0,
                        "highest_xp_win": 0,
                        "highest_xp_bet": 0
                    }
                elif game_type == "keno":
                    gambling_stats[game_type] = {
                        "games_played": 0,
                        "games_won": 0,
                        "games_lost": 0,
                        "xp_won_total": 0,
                        "xp_lost_total": 0,
                        "highest_xp_win": 0,
                        "highest_xp_bet": 0
                    }
                elif game_type == "powerball":
                    gambling_stats[game_type] = {
                        "tickets_bought": 0,
                        "games_won": 0,
                        "xp_won_total": 0,
                        "xp_lost_total": 0,
                        "highest_xp_win": 0
                    }
                elif game_type == "scratch_cards":
                    gambling_stats[game_type] = {
                        "games_played": 0,
                        "games_won": 0,
                        "games_lost": 0,
                        "xp_won_total": 0,
                        "xp_lost_total": 0,
                        "highest_xp_win": 0,
                        "highest_xp_bet": 0
                    }
                else:
                    # Default structure for unknown game types
                    gambling_stats[game_type] = {
                        "wins": 0,
                        "losses": 0,
                        "pushes": 0,
                        "total_played": 0,
                        "total_won": 0,
                        "total_lost": 0,
                        "net_xp": 0
                    }
            
            game_stats = gambling_stats[game_type]
            
            # Update standard stats based on game type
            if game_type == "slots":
                game_stats["total_games_played"] += 1
                if winnings > 0:
                    game_stats["xp_won_total"] += winnings
                    if winnings > game_stats.get("highest_xp_win", 0):
                        game_stats["highest_xp_win"] = winnings
                else:
                    game_stats["xp_lost_total"] += abs(winnings)
                if bet_amount > game_stats.get("highest_xp_bet", 0):
                    game_stats["highest_xp_bet"] = bet_amount
            elif game_type == "blackjack":
                game_stats["rounds_played"] += 1
                if winnings > 0:
                    game_stats["xp_won_total"] += winnings
                    game_stats["rounds_won"] += 1
                    if winnings > game_stats.get("highest_xp_win", 0):
                        game_stats["highest_xp_win"] = winnings
                else:
                    game_stats["xp_lost_total"] += abs(winnings)
                    game_stats["rounds_lost"] += 1
                if bet_amount > game_stats.get("highest_xp_bet", 0):
                    game_stats["highest_xp_bet"] = bet_amount
            elif game_type == "holdem":
                game_stats["games_played"] += 1
                if winnings > 0:
                    game_stats["xp_won_total"] += winnings
                    game_stats["games_won"] += 1
                    if winnings > game_stats.get("highest_xp_win", 0):
                        game_stats["highest_xp_win"] = winnings
                else:
                    game_stats["xp_lost_total"] += abs(winnings)
                    game_stats["games_lost"] += 1
                if bet_amount > game_stats.get("highest_xp_bet", 0):
                    game_stats["highest_xp_bet"] = bet_amount
            elif game_type == "craps":
                game_stats["games_played"] += 1
                if winnings > 0:
                    game_stats["xp_won_total"] += winnings
                    game_stats["games_won"] += 1
                    if winnings > game_stats.get("highest_xp_win", 0):
                        game_stats["highest_xp_win"] = winnings
                else:
                    game_stats["xp_lost_total"] += abs(winnings)
                    game_stats["games_lost"] += 1
                if bet_amount > game_stats.get("highest_xp_bet", 0):
                    game_stats["highest_xp_bet"] = bet_amount
            elif game_type == "races":
                game_stats["races_played"] += 1
                if winnings > 0:
                    game_stats["xp_won_total"] += winnings
                    game_stats["races_won"] += 1
                    if winnings > game_stats.get("highest_xp_win", 0):
                        game_stats["highest_xp_win"] = winnings
                else:
                    game_stats["xp_lost_total"] += abs(winnings)
                    game_stats["races_lost"] += 1
                if bet_amount > game_stats.get("highest_xp_bet", 0):
                    game_stats["highest_xp_bet"] = bet_amount
            elif game_type in ("coinflip", "rps"):
                game_stats["games_played"] += 1
                if winnings > 0:
                    game_stats["xp_won_total"] += winnings
                    game_stats["games_won"] += 1
                    if winnings > game_stats.get("highest_xp_win", 0):
                        game_stats["highest_xp_win"] = winnings
                elif winnings < 0:
                    game_stats["xp_lost_total"] += abs(winnings)
                    game_stats["games_lost"] += 1
                elif game_type == "rps":
                    game_stats["games_tied"] = game_stats.get("games_tied", 0) + 1
                if bet_amount > game_stats.get("highest_xp_bet", 0):
                    game_stats["highest_xp_bet"] = bet_amount
            elif game_type in ("wheel_of_pets", "keno", "scratch_cards"):
                game_stats["games_played"] = game_stats.get("games_played", 0) + 1
                if winnings > 0:
                    game_stats["xp_won_total"] = game_stats.get("xp_won_total", 0) + winnings
                    game_stats["games_won"] = game_stats.get("games_won", 0) + 1
                    if winnings > game_stats.get("highest_xp_win", 0):
                        game_stats["highest_xp_win"] = winnings
                else:
                    game_stats["xp_lost_total"] = game_stats.get("xp_lost_total", 0) + abs(winnings)
                    game_stats["games_lost"] = game_stats.get("games_lost", 0) + 1
                if bet_amount > game_stats.get("highest_xp_bet", 0):
                    game_stats["highest_xp_bet"] = bet_amount
            elif game_type == "powerball":
                if bet_amount > 0:
                    # Ticket purchase
                    game_stats["tickets_bought"] = game_stats.get("tickets_bought", 0) + 1
                    game_stats["xp_lost_total"] += bet_amount
                if winnings > 0:
                    game_stats["games_won"] = game_stats.get("games_won", 0) + 1
                    game_stats["xp_won_total"] += winnings
                    if winnings > game_stats.get("highest_xp_win", 0):
                        game_stats["highest_xp_win"] = winnings
            else:
                # Default for unknown game types
                if "total_played" in game_stats:
                    game_stats["total_played"] += 1
                    if winnings > 0:
                        game_stats["wins"] += 1
                        game_stats["total_won"] += winnings
                    elif winnings < 0:
                        game_stats["losses"] += 1
                        game_stats["total_lost"] += abs(winnings)
                    if "net_xp" in game_stats:
                        game_stats["net_xp"] += winnings

            # Game-specific updates
            if game_type == "races":
                pass
            elif game_type == "slots":
                pass
            elif game_type == "blackjack":
                if extra_data and extra_data.get("is_push"):
                    game_stats["pushes"] = game_stats.get("pushes", 0) + 1
            elif game_type == "holdem":
                pass
            elif game_type == "craps":
                pass
            elif game_type == "wheel_of_pets":
                if extra_data and extra_data.get("own_pet_jackpots"):
                    game_stats["own_pet_jackpots"] = game_stats.get("own_pet_jackpots", 0) + int(extra_data["own_pet_jackpots"])

            # Apply any extra data provided
            if extra_data:
                for key, value in extra_data.items():
                    if key == "highest_bet":
                        game_stats[key] = max(game_stats.get(key, 0), value)
                    elif key == "is_push" and game_type != "blackjack":
                        game_stats["pushes"] = game_stats.get("pushes", 0) + 1

            # Save the updated pet data to the database
            await self._save_pet_data_no_lock(user_id, pet)
            return True


    async def delete_pet_data(self, user_id: str, username: Optional[str] = None) -> bool:
        """Deletes pet data exclusively from the database."""
        async with self._get_user_lock(user_id):
            return await pets_db.delete_pet_data(user_id)

    async def set_pet_action_label(self, user_id: str, pet_id: str, action: str, label: str) -> bool:
        async with self._get_user_lock(user_id):
            pet = await self._get_pet_data_no_lock(user_id)
            if not pet or pet.get("id") != pet_id:
                return False

            if "action_labels" not in pet:
                pet["action_labels"] = {"attack": None, "defense": None, "charge": None}

            # Normalize: always store defense under "defense" (not "defend")
            storage_key = "defense" if action in ("defend", "defense") else action
            pet["action_labels"][storage_key] = label if label else None

            return await self._save_pet_data_no_lock(user_id, pet)

    async def update_pet_name(self, user_id: str, pet_id: str, new_name: str) -> bool:
        async with self._get_user_lock(user_id):
            pet = await self._get_pet_data_no_lock(user_id)
            if not pet or pet.get("id") != pet_id:
                return False

            pet["name"] = new_name

            return await self._save_pet_data_no_lock(user_id, pet)

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
        """Adds experience to a pet. Delegates to the centralized XP system."""
        try:
            from Systems.Pets.Logic.pet_brain import LootCalculator
            return await LootCalculator.apply_xp_change(int(user_id), int(amount), source)
        except Exception as e:
            logger.error(f"add_pet_experience error for user {user_id}: {e}", exc_info=True)
            return False, None

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
            # Include reforge identity so reforged items don't merge with base items
            reforged = item_dict.get("reforged", False)
            reforge_level = item_dict.get("reforge_level", 0)
            
            # Simple key based on identity
            key = f"{name}|{itype}|{rarity}|{reforged}|{reforge_level}"
            
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
        Generic update for pet data fields, saving exclusively to the database.
        """
        async with self._get_user_lock(user_id):
            pet = await self._get_pet_data_no_lock(user_id)
            if not pet:
                return False

            for k, v in updates.items():
                pet[k] = v

            return await self._save_pet_data_no_lock(user_id, pet)
        
    async def increment_pet_stats(self, user_id: str, stats_to_increment: Dict[str, int]) -> bool:
        async with self._get_user_lock(user_id):
            pet = await self._get_pet_data_no_lock(user_id)
            if not pet:
                return False

            for stat, value in stats_to_increment.items():
                pet[stat] = pet.get(stat, 0) + value

            return await self._save_pet_data_no_lock(user_id, pet)

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

        # ── Backfill missing set tags on reforged items (inventory + equipment) ──
        # Reforged items created before the forge_api fix won't have a 'set' key.
        # We patch them here on load so set-matching works correctly going forward.
        try:
            def _backfill_set_tag(item: dict) -> None:
                if not isinstance(item, dict): return
                if not item.get('reforged'): return
                if item.get('set'): return  # already present, skip
                canonical = self.file_manager.get_equipment_item(item.get('name', ''))
                if canonical and canonical.get('set'):
                    item['set'] = canonical['set']

            for inv_item in pet.get('inventory', []):
                _backfill_set_tag(inv_item)

            for slot_val in equip.values():
                if isinstance(slot_val, dict):
                    _backfill_set_tag(slot_val)
                elif isinstance(slot_val, list):
                    for slot_item in slot_val:
                        _backfill_set_tag(slot_item)
        except Exception:
            pass  # Never break migration due to set-tag backfill

        # Ensure List Slots (Gems, Monsters, Material)
        for list_slot in ["Gems", "Monsters", "Material"]:
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
        
        # Ensure Dict Slots (Hat, Potion)
        for dict_slot in ["Hat", "Potion"]:
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
        action_labels.setdefault("defense", None)
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

        boss = battle_stats.setdefault("boss", {})
        move_stat(boss, "wins", "boss_wins")
        move_stat(boss, "losses", "boss_losses")

        wild = battle_stats.setdefault("wild_encounter", {})
        move_stat(wild, "wins", "wild_encounter_wins")
        move_stat(wild, "losses", "wild_encounter_losses")
        
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

user_data_manager = UserDataManager()
