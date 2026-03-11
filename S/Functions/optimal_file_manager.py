import json
import os
import threading
import logging
import time
from typing import Dict, Any, Optional, Union
from pathlib import Path

logger = logging.getLogger("OptimalFileManager")

import asyncio

class OptimalFileManager:
    """
    Optimized file manager for handling JSON data.
    
    Features:
    - specialized preloading for Systems/Pets/Logic (O(1) access).
    - General purpose load/save for other files (User data, etc.).
    - Backward compatible with UserDataManager.
    - Async support for non-blocking I/O.
    """
    def __init__(self, max_cache_size: int = 2000, ttl_seconds: int = 600):
        # Support for containerized environments (CasaOS/Docker) via DATA_DIR
        data_dir_env = os.getenv('DATA_DIR')
        if data_dir_env:
            self.base_data_dir = Path(data_dir_env).resolve()
        else:
            self.base_data_dir = Path(__file__).parent.parent.resolve() / "Data"

        # Paths
        self.base_systems_dir = Path(__file__).parent.parent.resolve()
        self.pets_logic_dir = self.base_systems_dir / "Pets" / "Logic"
        self.users_path = self.base_data_dir / "Users"
        self.json_path = self.base_data_dir
        self.walk_tru_dir = self.base_systems_dir / "Fun" / "Walk Tru"
        
        # Ensure directories
        self.ensure_directories()
        
        # Caches
        self._logic_cache: Dict[str, Any] = {}
        self._hg_optimized: Dict[str, Any] = {}
        # Optimized Lookups
        self._equipment_lookup: Dict[str, Any] = {}
        self._pet_info_lookup: Dict[str, Any] = {}
        self._base_name_lookup: Dict[str, str] = {}
        
        self._logic_lock = threading.RLock()
        
        # Fine-grained file locking to prevent read/write races
        # (e.g. Sync load vs Async save-thread)
        self._file_locks: Dict[str, threading.RLock] = {}
        self._locks_lock = threading.Lock()
        
        # Preload Logic Files immediately
        self.preload_logic()

    def _get_file_lock(self, path: Path) -> threading.RLock:
        key = str(path.resolve())
        with self._locks_lock:
            if key not in self._file_locks:
                self._file_locks[key] = threading.RLock()
            return self._file_locks[key]

    def ensure_directories(self):
        for d in [self.pets_logic_dir, self.users_path, self.json_path]:
            try:
                d.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

    def preload_logic(self):
        """
        Loads all JSON files from Systems/Pets/Logic into memory and builds optimized indexes.
        Verifies that all critical Hunger Games logic files are present.
        """
        required_hg_files = {
            "Actions": [
                "flying_actions", "land_actions", "swimming_actions"
            ],
            "Eliminations": [
                "air_eliminations", "basic_eliminations", "electric_eliminations", 
                "fighting_eliminations", "fire_eliminations", "holy_eliminations", 
                "ice_eliminations", "magic_eliminations", "necro_eliminations", 
                "plant_eliminations", "psychic_eliminations", "rock_eliminations", 
                "water_eliminations"
            ],
            "Locations": [
                "deadly_flying", "deadly_land", "deadly_swimming", "locations_base"
            ],
            "Placeholders": [
                "attacks", "defenses", "eliminations", "successes"
            ]
        }

        with self._logic_lock:
            self._logic_cache.clear()
            self._equipment_lookup.clear()
            self._pet_info_lookup.clear()
            self._base_name_lookup.clear()
            
            if not self.pets_logic_dir.exists():
                return
            
            loaded_count = 0
            # Load root JSONs
            for file_path in self.pets_logic_dir.glob("*.json"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        self._logic_cache[file_path.stem] = data
                        loaded_count += 1
                except Exception as e:
                    logger.error(f"Failed to load {file_path.name}: {e}")
            
            # Load SurvivorSeries subdirectories into hunger_games structure
            hg_data = {
                "actions": {},
                "eliminations": {},
                "locations": {},
                "placeholders": {}
            }
            
            subdirs = {
                "Actions": "actions", 
                "Eliminations": "eliminations", 
                "Locations": "locations", 
                "Placeholders": "placeholders"
            }
            
            for folder_name, key_name in subdirs.items():
                folder_path = self.pets_logic_dir / folder_name
                if folder_path.exists():
                    for file_path in folder_path.glob("*.json"):
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                                hg_data[key_name][file_path.stem] = data
                                loaded_count += 1
                        except Exception as e:
                            logger.error(f"Failed to load {folder_name}/{file_path.name}: {e}")

            # Verify required files
            missing_files = []
            for folder, expected_files in required_hg_files.items():
                key_name = subdirs.get(folder)
                if not key_name: 
                    continue
                    
                loaded_data = hg_data.get(key_name, {})
                for expected in expected_files:
                    if expected not in loaded_data:
                        missing_files.append(f"{folder}/{expected}.json")
            
            if missing_files:
                logger.warning(f"Missing required Hunger Games logic files: {', '.join(missing_files)}")
            else:
                logger.info("All required Hunger Games logic files verified and loaded.")
            
            self._logic_cache["hunger_games"] = hg_data
            
            # Build Optimized Indexes
            self._build_optimized_indexes()
            self._build_hg_indexes(hg_data)
            
            logger.info(f"OptimalFileManager preloaded {loaded_count} files from {self.pets_logic_dir}")

    def _build_hg_indexes(self, hg_data: Dict[str, Any]):
        """
        Builds optimized indexes for Hunger Games data.
        """
        # 1. Deadly Locations
        deadly = {}
        locs_raw = hg_data.get("locations", {})
        for k, v in locs_raw.items():
            if k.startswith("deadly_"):
                type_key = k.replace("deadly_", "")
                deadly[type_key] = v
        
        # 2. Flattened Locations (Style -> List[names])
        locs_flat = {}
        base_locs = locs_raw.get("locations_base", {}).get("locations", {})
        for style, names in base_locs.items():
            locs_flat[style] = names
            
        self._hg_optimized = {
            "deadly_by_type": deadly,
            "locations_flat": locs_flat,
            "actions": hg_data.get("actions", {}),
            "eliminations": hg_data.get("eliminations", {}),
            "placeholders": hg_data.get("placeholders", {})
        }

    def _build_optimized_indexes(self):
        """
        Constructs O(1) lookup tables for frequently accessed data from base, equipment, info, mission.
        """
        # 1. Equipment Lookup (Name -> Item Data)
        if "equipment" in self._logic_cache:
            eq_data = self._logic_cache["equipment"]
            # Categories: Gems, Monsters, Materials
            for category, items in eq_data.items():
                if isinstance(items, list):
                    type_name = category[:-1] if category.endswith('s') else category
                    for item in items:
                        name = item.get("name")
                        if name:
                            # Inject type if missing so we know what it is
                            if "type" not in item:
                                item["type"] = type_name
                            self._equipment_lookup[name] = item

        # 2. Pet Species Lookup (Species -> Data)
        if "info" in self._logic_cache:
            info_data = self._logic_cache["info"]
            self._pet_info_lookup = info_data.get("Pets", {})

        # 3. Base Name Lookup (Base Name -> Element)
        if "base" in self._logic_cache:
            base_data = self._logic_cache["base"]
            element_bases = base_data.get("element_bases", {})
            for element, bases in element_bases.items():
                for base_name in bases:
                    self._base_name_lookup[base_name] = element

    def get_equipment_item(self, name: str) -> Optional[Dict[str, Any]]:
        """O(1) lookup for any equipment item by name."""
        with self._logic_lock:
            return self._equipment_lookup.get(name)

    def get_pet_species_info(self, species: str) -> Optional[Dict[str, Any]]:
        """O(1) lookup for pet species base stats."""
        with self._logic_lock:
            return self._pet_info_lookup.get(species)

    def get_base_element(self, base_name: str) -> Optional[str]:
        """O(1) lookup to find which element a base name belongs to."""
        with self._logic_lock:
            return self._base_name_lookup.get(base_name)

    def get_mission_scenarios(self, difficulty: str = "easy", category: str = "land") -> list:
        """Fast access to mission scenarios."""
        with self._logic_lock:
            missions = self._logic_cache.get("mission", {})
            return missions.get("scenarios", {}).get(difficulty, {}).get(category, [])


    def load_all(self) -> Dict[str, Any]:
        """
        Returns the entire cached logic data.
        """
        with self._logic_lock:
            return self._logic_cache.copy()

    def get_data(self, filename: str) -> Any:
        """
        Retrieves data for a specific logic file (e.g. 'mission', 'base').
        Served from memory.
        """
        with self._logic_lock:
            return self._logic_cache.get(filename, {})

    def get_logic_data(self, filename: str) -> Any:
        """
        Alias for get_data to be more explicit about retrieving logic data.
        """
        return self.get_data(filename)

    def get_hg_pool(self, key: str) -> Dict[str, Any]:
        """
        Returns a specific Hunger Games optimized pool.
        Keys: 'actions', 'eliminations', 'locations_flat', 'deadly_by_type', 'placeholders'
        """
        with self._logic_lock:
            return self._hg_optimized.get(key, {})

    def save_logic_data(self, filename: str, data: Any) -> bool:
        """
        Saves data to a logic file in the Pets/Logic directory.
        """
        path = self.pets_logic_dir / f"{filename}.json"
        return self.save(path, data)

    def get_user_file_path(self, user_id: str) -> Path:
        return self.users_path / f"{user_id}.json"

    def load(self, path: Path, default: Any = None) -> Any:
        """
        Loads a JSON file from disk (on-demand).
        """
        # Check if it matches a logic file we already have
        if self.pets_logic_dir in path.parents or path.parent == self.pets_logic_dir:
            stem = path.stem
            with self._logic_lock:
                if stem in self._logic_cache:
                    return self._logic_cache[stem]

        # General load
        try:
            if not path.exists():
                return default if default is not None else {}
            
            with self._get_file_lock(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            return default if default is not None else {}

    def save(self, path: Path, data: Any) -> bool:
        """
        Saves data to disk.
        """
        # If it's a logic file, update cache too
        if self.pets_logic_dir in path.parents or path.parent == self.pets_logic_dir:
            with self._logic_lock:
                self._logic_cache[path.stem] = data

        try:
            # Ensure parent exists
            if not path.parent.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
            
            logger.debug(f"Attempting to acquire file lock for {path}")
            with self._get_file_lock(path):
                logger.debug(f"File lock acquired for {path}. Opening file for writing.")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                    f.flush() # Ensure data is written to OS buffer
                    os.fsync(f.fileno()) # Force OS to write buffer to disk
                logger.debug(f"Data written and synced to disk for {path}. Releasing file lock.")
            return True
        except Exception as e:
            logger.error(f"Failed to save {path}: {e}")
            return False

    async def load_async(self, path: Path, default: Any = None) -> Any:
        """
        Asynchronously loads a JSON file from disk.
        """
        return await asyncio.to_thread(self.load, path, default)

    async def save_async(self, path: Path, data: Any) -> bool:
        """
        Asynchronously saves data to disk.
        """
        return await asyncio.to_thread(self.save, path, data)

    async def save_logic_data_async(self, filename: str, data: Any) -> bool:
        """
        Asynchronously saves data to a logic file.
        """
        path = self.pets_logic_dir / f"{filename}.json"
        return await self.save_async(path, data)
