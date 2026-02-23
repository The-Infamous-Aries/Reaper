import discord
from discord.ext import commands
from discord import app_commands, ui, ButtonStyle, Embed, File
import random
import logging
from typing import Dict, List, Any, Tuple, Optional, cast
import os
import math
import time
from io import BytesIO
import asyncio
import functools
from datetime import datetime
from pathlib import Path
from Systems.Functions.optimal_file_manager import OptimalFileManager
from Systems.Pets.Logic.pet_brain import DamageCalculator, LootCalculator
from Systems.Pets.pets_system import add_experience
from Systems.Functions import emoji as emoji_mod

# Alias for emoji helper to ensure correct usage
get_pet_emoji = LootCalculator.get_pet_emoji
from Systems.Pets.PetGames.game_map import GameMap

Image: Optional[Any] = None
ImageDraw: Optional[Any] = None
ImageFont: Optional[Any] = None
PIL_AVAILABLE: bool = False

try:
    from PIL import Image as PILImage, ImageDraw as PILImageDraw, ImageFont as PILImageFont
    Image = PILImage
    ImageDraw = PILImageDraw
    ImageFont = PILImageFont
    PIL_AVAILABLE = True
except ImportError:
    pass

UserDataManager: Optional[Any] = None

try:
    from Systems.Functions.user_data_manager import UserDataManager as _UserDataManager
    UserDataManager = _UserDataManager
except ImportError:
    pass

logger = logging.getLogger("reaper.pet_survivor_series")
DISCORD_CHAR_LIMIT = 2000

# Data paths (relative to Systems directory)
_SYSTEMS_DIR = str(Path(__file__).resolve().parents[2])
# Champions path relative to OptimalFileManager logic dir logic
_CHAMPIONS_FILE = "champions"
_GAME_STATES_DIR = os.path.join(_SYSTEMS_DIR, 'Data', 'GameStates')

def get_file_manager() -> OptimalFileManager:
    if UserDataManager is not None:
        try:
            return UserDataManager().file_manager
        except Exception:
            pass
    return OptimalFileManager()

async def _send_long_message(channel, text: str):
    limit = DISCORD_CHAR_LIMIT
    if len(text) <= limit:
        await channel.send(text)
        return
    lines = text.split("\n")
    parts: List[str] = []
    buf = ""
    for line in lines:
        add = ("\n" + line) if buf else line
        if len(buf) + len(add) <= limit:
            buf += add
        else:
            if buf:
                parts.append(buf)
            if len(line) <= limit:
                buf = line
            else:
                i = 0
                while i < len(line):
                    parts.append(line[i:i+limit])
                    i += limit
                buf = ""
    if buf:
        parts.append(buf)
    for p in parts:
        await channel.send(p)

class DataPools:
    def __init__(self):
        self.locations: Dict[str, List[str]] = {}
        self.placeholders: Dict[str, Any] = {}
        self.actions_dir_map: Dict[str, Any] = {}
        self.elims_dir_map: Dict[str, Any] = {}
        self.deadly_by_type: Dict[str, Any] = {}

    def reload(self):
        fm = get_file_manager()
        fm.preload_logic()
        
        self.actions_dir_map = fm.get_hg_pool("actions")
        self.elims_dir_map = fm.get_hg_pool("eliminations")
        self.locations = fm.get_hg_pool("locations_flat")
        self.deadly_by_type = fm.get_hg_pool("deadly_by_type")
        self.placeholders = fm.get_hg_pool("placeholders")

    async def reload_async(self):
        await asyncio.to_thread(self.reload)

    def _strip_style_prefix(self, style: str, name: str) -> str:
        key = style.replace('_', ' ').lower()
        lower = name.lower()
        if lower.startswith(key + ' '):
            return name[len(key) + 1:]
        return name

    def random_deadly_item(self, pet_type: str) -> Optional[Dict[str, Any]]:
        key = (pet_type or "").strip().lower()
        if key == "air": key = "flying"
        if key == "water": key = "swimming"
        
        if key not in {"flying", "land", "swimming"}:
            return None
        pack = self.deadly_by_type.get(key, {})
        items = pack.get("deadly", [])
        if not isinstance(items, list) or not items:
            return None
        return random.choice(items)
    
    def random_action_for_type(self, pet_type: str) -> Optional[Dict[str, Any]]:
        key = (pet_type or "").strip().lower()
        if key == "air": key = "flying"
        if key == "water": key = "swimming"
        
        pack = self.actions_dir_map.get(f"{key}_actions", {})
        acts = pack.get("actions", [])
        if not isinstance(acts, list) or not acts:
            return None
        return random.choice(acts)
    
    def random_action_any(self) -> Optional[Dict[str, Any]]:
        for k, pack in self.actions_dir_map.items():
            arr = pack.get("actions", [])
            if isinstance(arr, list) and arr:
                return random.choice(arr)
        return None
    
    def random_elimination_for_element(self, element: str, group_size: int) -> Optional[Dict[str, Any]]:
        ekey = (element or "basic").strip().lower()
        pack = self.elims_dir_map.get(f"{ekey}_eliminations", {})
        scenarios = pack.get("scenarios", {})
        key_map = {2: "duo", 3: "trio", 4: "quad", 5: "quint", 6: "sext"}
        skey = key_map.get(max(2, min(6, int(group_size))))
        if not skey:
            return None
        arr = scenarios.get(skey, [])
        if not isinstance(arr, list) or not arr:
            return None
        return random.choice(arr)

    def random_location_with_style(self) -> Tuple[str, str]:
        """Return (style_key, location_name). Falls back to generic when empty."""
        if not self.locations:
            return ("basic", "Open Field")
        style = random.choice(list(self.locations.keys()))
        pool = self.locations.get(style, [])
        loc = random.choice(pool) if pool else ("Iacon Plaza")
        return (style, self._strip_style_prefix(style, loc))

    def random_location_for_style(self, style: str) -> str:
        pool = self.locations.get(style, [])
        if not pool:
            return "Open Field"
        name = random.choice(pool)
        return self._strip_style_prefix(style, name)

def _format_a_open(names: List[str]) -> str:
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{', '.join(names[:-1])}, and {names[-1]}"


class GameSession:
    def __init__(self, participants: List[Any], pools: DataPools, official: bool = False):
        self.participants = participants.copy()
        self.pools = pools
        self.alive = participants.copy()
        self.assignment = {}
        self.locations: dict[str, Any] = {}
        self.elimination_locations: dict[str, Any] = {}
        self.elimination_round: dict[str, Any] = {}
        self.forms: dict[str, Any] = {}
        self.round_index = 0
        self.started = False
        self.official = official
        self.action_log: Dict[str, List[str]] = {}
        self.kill_log: Dict[str, List[Dict[str, Any]]] = {}
        self.round_markers: List[Dict[str, Any]] = []
        self.participant_names = {p: getattr(p, 'display_name', str(p)) for p in participants}
        self.state_path: Optional[str] = None
        self.game_id: Optional[str] = None
        self.guild_id: Optional[int] = None
        self.channel_id: Optional[int] = None
        self.creator_id: Optional[int] = None
        self.status: str = 'active'
        self.created_at: str = datetime.now().isoformat()
        self.rounds_history: List[Dict[str, Any]] = []
        
        self.map_size = (1200, 800)
        self.game_map = GameMap({}, self.map_size)
        for participant in self.participants:
            self.assignment[participant] = 'Neutral'
        self._initialize_locations()
        self._style_cycle = list(self.game_map.style_order)
        self._style_cursor = 0
        self._round_timeout_seconds = 300
        self._event_weights = {"action": 0.50, "elimination": 0.50}
        self.recent_action_failures: Dict[Any, List[bool]] = {}
        self.pet_cache: Dict[str, Dict[str, Any]] = {}
        self._pets_loaded = False
    
    async def preload_pets(self):
        """Asynchronously preload pet data for all participants to prevent blocking I/O."""
        if self._pets_loaded:
            return
        


        udm = UserDataManager()
        tasks = []
        user_ids = []
        
        for p in self.participants:
            uid = getattr(p, "id", None)
            if uid:
                user_ids.append(str(uid))
                tasks.append(udm.get_pet_data_async(str(uid)))
        
        if not tasks:
            self._pets_loaded = True
            return

        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for uid, result in zip(user_ids, results):
            if isinstance(result, dict):
                self.pet_cache[uid] = result
            else:
                self.pet_cache[uid] = {}
                
        self._pets_loaded = True



    def _species_emoji(self, participant: Any) -> str:
        try:
            uid = str(getattr(participant, "id", ""))
            pet = self.pet_cache.get(uid)
            
            # Fallback to sync load ONLY if not cached and cache wasn't loaded
            # This is a safety net, but ideally preload_pets() is called first
            if pet is None and not self._pets_loaded:
                if UserDataManager is not None:
                    udm = UserDataManager()
                    if udm:
                        pet = udm.get_pet_data(uid)
            
            species = (pet or {}).get("species") or (pet or {}).get("name") or ""
            return get_pet_emoji("Pets", species) or emoji_mod.mention('Pets') or "🐾"
        except Exception:
            return emoji_mod.mention('Pets') or "🐾"

    def to_dict(self) -> Dict[str, Any]:
        def ser(p: Any) -> Dict[str, Any]:
            return {"id": getattr(p, 'id', None), "name": getattr(p, 'display_name', str(p))}
        participants_ser = [ser(p) for p in self.participants]
        alive_idx = [self.participants.index(p) for p in self.alive]
        locs_list = [self.locations.get(p, {}) for p in self.participants]
        elim_loc_map = {str(self.participants.index(k)): v for k, v in self.elimination_locations.items()}
        elim_round_map = {str(self.participants.index(k)): v for k, v in self.elimination_round.items()}
        
        # Serialize action_log and kill_log with participant indices as keys
        action_log_ser = {str(self.participants.index(p)): actions for p, actions in self.action_log.items()}
        kill_log_ser = {str(self.participants.index(p)): kills for p, kills in self.kill_log.items()}
        
        # Serialize round_markers (convert participant objects to indices for serialization)
        round_markers_ser = []
        for marker in self.round_markers:
            marker_copy = marker.copy()
            # Convert participant objects to indices for serialization
            if 'side_a' in marker_copy:
                marker_copy['side_a'] = [str(self.participants.index(p)) for p in marker_copy['side_a']]
            if 'side_b' in marker_copy:
                marker_copy['side_b'] = [str(self.participants.index(p)) for p in marker_copy['side_b']]
            round_markers_ser.append(marker_copy)
        
        return {
            "participants": participants_ser,
            "alive": alive_idx,
            "locations": locs_list,
            "elimination_locations": elim_loc_map,
            "elimination_round": elim_round_map,
            "action_log": action_log_ser,
            "kill_log": kill_log_ser,
            "round_markers": round_markers_ser,
            "round_index": self.round_index,
            "official": self.official,
            "game_id": self.game_id,
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "creator_id": self.creator_id,
            "status": self.status,
            "created_at": self.created_at,
            "started": self.started,
            "rounds_history": self.rounds_history
        }

    @staticmethod
    def from_dict(data: Dict[str, Any], pools: DataPools) -> "GameSession":
        participants = [d.get("name") for d in data.get("participants", [])]
        gs = GameSession(participants, pools, official=data.get("official", False))
        gs.round_index = int(data.get("round_index", 0))
        gs.alive = [gs.participants[i] for i in data.get("alive", list(range(len(gs.participants))))]
        locs_list = data.get("locations", [])
        for i, p in enumerate(gs.participants):
            if i < len(locs_list):
                gs.locations[p] = locs_list[i]
        for k, v in data.get("elimination_locations", {}).items():
            idx = int(k)
            if 0 <= idx < len(gs.participants):
                gs.elimination_locations[gs.participants[idx]] = v
        for k, v in data.get("elimination_round", {}).items():
            idx = int(k)
            if 0 <= idx < len(gs.participants):
                gs.elimination_round[gs.participants[idx]] = v
        
        # Deserialize action_log and kill_log
        for k, actions in data.get("action_log", {}).items():
            idx = int(k)
            if 0 <= idx < len(gs.participants):
                gs.action_log[gs.participants[idx]] = actions
        
        for k, kills in data.get("kill_log", {}).items():
            idx = int(k)
            if 0 <= idx < len(gs.participants):
                if isinstance(kills, int):
                    # Convert legacy int count to list of dummy entries to allow appending
                    gs.kill_log[gs.participants[idx]] = [{'victim': 'Unknown', 'with': [], 'text': 'Legacy kill'}] * kills
                else:
                    gs.kill_log[gs.participants[idx]] = kills
        
        # Deserialize round_markers (convert participant indices back to objects)
        round_markers_ser = data.get("round_markers", [])
        gs.round_markers = []
        for marker_ser in round_markers_ser:
            marker = marker_ser.copy()
            # Convert participant indices back to objects
            if 'side_a' in marker:
                side_a_indices = marker['side_a']
                marker['side_a'] = [gs.participants[int(idx)] for idx in side_a_indices if 0 <= int(idx) < len(gs.participants)]
            if 'side_b' in marker:
                side_b_indices = marker['side_b']
                marker['side_b'] = [gs.participants[int(idx)] for idx in side_b_indices if 0 <= int(idx) < len(gs.participants)]
            gs.round_markers.append(marker)
        
        gs.game_id = data.get("game_id")
        gs.guild_id = data.get("guild_id")
        gs.channel_id = data.get("channel_id")
        gs.creator_id = data.get("creator_id")
        gs.status = data.get("status", 'active')
        gs.created_at = data.get("created_at", datetime.now().isoformat())
        gs.started = bool(data.get("started", False))
        rh = data.get("rounds_history", [])
        try:
            if isinstance(rh, list):
                gs.rounds_history = rh
        except Exception:
            gs.rounds_history = []
        return gs
    
    def _element_emoji(self, participant: Any) -> str:
        try:
            uid = str(getattr(participant, "id", ""))
            pet = self.pet_cache.get(uid)
            if pet is None and not self._pets_loaded:
                if UserDataManager is not None:
                    udm = UserDataManager()
                    if udm:
                        pet = udm.get_pet_data(uid)
            
            element = (pet or {}).get("element", "basic")
            return get_pet_emoji("Elements", element) or get_pet_emoji("Elements", "basic") or "⚖️"
        except Exception:
            return get_pet_emoji("Elements", "basic") or "⚖️"

    def get_event_emojis(self, side_a: List[Any], side_b: List[Any], is_elimination: bool = False, a_form: str = 'pet', b_form: str = 'pet') -> str:
        if not side_a:
            return ""
        a_tokens = [self._species_emoji(p) for p in side_a]
        b_tokens = [self._species_emoji(p) for p in side_b]
        if not side_b:
            return ''.join(a_tokens)
        if is_elimination:
            return f"{''.join(a_tokens)}💀{''.join(b_tokens)}"
        return f"{''.join(a_tokens)}{''.join(b_tokens)}"

    def get_participant_name(self, participant: Any) -> str:
        """Get the display name for a participant, whether it's a Discord user object or string."""
        return self.participant_names.get(participant, str(participant))

    def _initialize_locations(self):
        locs, forms = self.game_map.initialize_locations(self.participants, self.assignment, self.pools)
        self.locations = locs
        self.forms = forms
    
    def render_map(self) -> Optional[BytesIO]:
        try:
            total_participants = len(self.participants)
            alive_participants = len(self.alive)
            return self.game_map.render_map(self.round_markers, self.elimination_locations, self.elimination_round, self.round_index, self.locations, total_participants, alive_participants)
        except Exception as e:
            logger.error(f"Error rendering map: {e}")
            return None

    async def render_map_async(self) -> Optional[BytesIO]:
        return await asyncio.to_thread(self.render_map)

    async def _get_member_pet(self, participant: Any) -> Dict[str, Any]:
        try:
            uid = getattr(participant, "id", None)
            udm = None
            pet = None
            if UserDataManager is not None:
                udm = UserDataManager()
            if udm and uid:
                pet = await udm.get_pet_data_async(str(uid))
            category = (pet or {}).get("category", "land")
            element = (pet or {}).get("element", "basic")
            element2 = (pet or {}).get("element2")
            species = (pet or {}).get("species", (pet or {}).get("name", "Pet"))
            species_emoji = get_pet_emoji("Pets", species) or ""
            elem_emoji = get_pet_emoji("Elements", element) or emoji_mod.mention('Charge') or "⚡"
            if element2:
                e2_emoji = get_pet_emoji("Elements", element2)
                if e2_emoji:
                    elem_emoji = f"{elem_emoji}{e2_emoji}"
            cat_emoji = get_pet_emoji("Pet Type", category) or "🌿"
            return {"category": category, "element": element, "element2": element2, "species": species, "species_emoji": species_emoji, "element_emoji": elem_emoji, "category_emoji": cat_emoji, "pet": pet}
        except Exception:
            return {"category": "land", "element": "basic", "element2": None, "species": "Pet", "species_emoji": "", "element_emoji": get_pet_emoji("Elements", "basic") or "⚖️", "category_emoji": get_pet_emoji("Pet Type", "land") or "🌿", "pet": None}

    def _game_stat_average(self, stat: str) -> float:
        vals = []
        levels = []
        for p in self.alive:
            pet_info: dict[str, dict[str, Any] | None] = {"pet": None}
            try:
                uid = str(getattr(p, "id", ""))
                pet = self.pet_cache.get(uid)
                if pet is None and not self._pets_loaded:
                    if UserDataManager is not None:
                        udm = UserDataManager()
                        if udm:
                            pet = udm.get_pet_data(uid)
                pet_info["pet"] = pet
            except Exception:
                pet = None
                pet_info["pet"] = None
            v = 0
            lvl = 1
            if isinstance(pet, dict):
                try:
                    v = int(pet.get(stat, 0))
                    lvl = int(pet.get("level", 1))
                except Exception:
                    v = 0
                    lvl = 1
            vals.append(v)
            levels.append(lvl)
        if not vals:
            return 1.0
        avg_stat = sum(vals) / len(vals)
        total_levels = sum(levels) if levels else len(self.alive)
        pets_left = max(1, len(self.alive))
        return float(avg_stat) * float(total_levels) * float(pets_left)
    
    def _pet_stat_weight(self, pet: Dict[str, Any], stat: str) -> float:
        try:
            lvl = max(1, int(pet.get("level", 1)))
            s = max(0, int(pet.get(stat, 0)))
            roll = random.randint(1, 20)
            return float(s) * float(lvl) * float(roll)
        except Exception:
            return 0.0
    
    def _random_placeholder(self, key: str) -> str:
        try:
            src = self.pools.placeholders.get(key)
        except Exception:
            src = None
        if isinstance(src, list) and src:
            return str(random.choice(src))
        if isinstance(src, dict):
            for v in src.values():
                if isinstance(v, list) and v:
                    return str(random.choice(v))
        return ""
    
    def _apply_placeholders(self, text: str, names: Optional[List[str]] = None, place: Optional[str] = None) -> str:
        s = str(text or "")
        if names:
            for idx, nm in enumerate(names, start=1):
                s = s.replace(f"{{P{idx}}}", nm)
        if place:
            s = s.replace("{LOCATION}", place)
            s = s.replace("{LOCATION_PLACEHOLDER}", place)
        token_map = {
            "ATTACK": "attacks", "ATTACKS": "attacks",
            "DEFENSE": "defenses", "DEFENSES": "defenses",
            "ELIMINATION": "eliminations", "ELIMINATIONS": "eliminations",
            "SUCCESS": "successes", "SUCCESSES": "successes"
        }
        for token, key in token_map.items():
            while f"{{{token}}}" in s:
                rep = self._random_placeholder(key)
                s = s.replace(f"{{{token}}}", rep, 1)
        return s
    
    def _recent_fail_penalty(self, participant: Any) -> float:
        fails = [b for b in self.recent_action_failures.get(participant, []) if b]
        return min(0.15, 0.05 * len(fails))
    
    def _advantage_bonus(self, participant: Any, group_types: List[str], style_element: Optional[str] = None) -> float:
        pet_info = self.participant_names.get(participant)
        try:
            uid = str(getattr(participant, "id", ""))
            pet = self.pet_cache.get(uid)
            if pet is None and not self._pets_loaded:
                if UserDataManager is not None:
                    udm = UserDataManager()
                    if udm:
                        pet = udm.get_pet_data(uid)
            
            t = str((pet or {}).get("category", "")).lower()
            e = str((pet or {}).get("element", "")).lower()
        except Exception:
            t = ""
            e = ""
        bonus = 0.0
        penalty = 0.0
        try:
            for gt in group_types:
                if not gt: continue
                # Check if participant has advantage over group member
                if DamageCalculator.compute_type_bonus(t, gt) > 1.0:
                    bonus += 0.05
                # Check if group member has advantage over participant
                if DamageCalculator.compute_type_bonus(gt, t) > 1.0:
                    penalty += 0.05
        
            if style_element:
                se = style_element.lower()
                # Check if participant element has advantage over location element
                if DamageCalculator.compute_element_bonus(e, se) > 1.0:
                    bonus += 0.05
                # Check if location element has advantage over participant
                if DamageCalculator.compute_element_bonus(se, e) > 1.0:
                    penalty += 0.05
        except Exception:
            pass
        net = bonus - penalty
        if net > 0.0:
            net = min(net, 0.10)
        else:
            net = max(net, -0.10)
        return net

    def _pick_event_type(self) -> str:
        r = random.random()
        if r < self._event_weights["action"]:
            return "action"
        return "elimination"

    def _pick_location_name(self, element: str) -> str:
        if not element or not isinstance(element, str):
            return "Open Field"
        return f"{element.title()} Zone"

    def _build_action_embed(self, participant: Any, pet_info: Dict[str, Any]) -> Tuple[Embed, List[Dict[str, Any]]]:
        cat = pet_info["category"]
        elem = pet_info["element"]
        loc = self._pick_location_name(elem)
        prompt = f"{self.get_participant_name(participant)} explores the {loc} and prepares an action."
        title = f"{pet_info['species_emoji']} {pet_info['category_emoji']} {cat.title()} • {pet_info['element_emoji']} {elem.title()}"
        embed = Embed(title=title, description=prompt)
        embed.color = discord.Color.blurple()
        choices = [{"text": "Attack"}, {"text": "Defend"}, {"text": "Evade"}]
        return embed, choices

    # removed deadly events

    def _build_elim_embed(self, participant: Any, pet_info: Dict[str, Any]) -> Tuple[Embed, List[Dict[str, Any]]]:
        elem = pet_info["element"]
        p1 = self.get_participant_name(participant)
        p2 = "Opponent"
        prompt = f"A tense duel unfolds between {p1} and {p2} in the {self._pick_location_name(elem)}."
        title = f"🗡️ Duel • {pet_info['element_emoji']} {elem.title()}"
        embed = Embed(title=title, description=prompt)
        embed.color = discord.Color.orange()
        actions = [{"action": "ATT"}, {"action": "DEF"}]
        return embed, actions

    class ChoiceView(ui.View):
        def __init__(self, choices: List[Dict[str, Any]], timeout_sec: int = 300):
            super().__init__(timeout=timeout_sec)
            self.result: Optional[Dict[str, Any]] = None
            for ch in choices:
                label = ch.get("text") or ch.get("stat") or ch.get("action") or "Choose"
                style = ButtonStyle.secondary
                if ch.get("style") == "primary":
                    style = ButtonStyle.primary
                elif ch.get("style") == "danger":
                    style = ButtonStyle.danger

                btn: discord.ui.Button = ui.Button(label=str(label)[:80], style=style)
                btn.callback = functools.partial(self._dynamic_button_callback, ch=ch) # type: ignore
                self.add_item(btn)

    async def _dynamic_button_callback(self, interaction: discord.Interaction, ch: Dict[str, Any]):
        self.result = ch
        try:
            await interaction.response.defer()
        except Exception:
            pass
        cast(discord.ui.View, self).stop()

    async def on_timeout(self):
            if not self.result and self.children:
                for item in self.children:
                    if isinstance(item, ui.Button):
                        self.result = {"text": item.label}
                        break
            self.stop()

    async def _send_user_event(self, bot: commands.Bot, participant: Any) -> Tuple[str, Optional[str]]:
        pet_info = await self._get_member_pet(participant)
        etype = self._pick_event_type()
        if etype == "action":
            embed, choices = self._build_action_embed(participant, pet_info)
        else:
            embed, choices = self._build_elim_embed(participant, pet_info)
        user_obj = participant if hasattr(participant, "send") else None
        if not user_obj and hasattr(participant, "id") and bot:
            participant_id = getattr(participant, "id", None)
            if isinstance(participant_id, int):
                user_obj = bot.get_user(participant_id)
        if not user_obj:
            view = self.ChoiceView(choices, self._round_timeout_seconds)
            await view.on_timeout()
            choice = view.result
        else:
            try:
                dm = await user_obj.create_dm()
                view = self.ChoiceView(choices, self._round_timeout_seconds)
                msg = await dm.send(embed=embed, view=view)
                await view.wait()
                choice = view.result
                try:
                    await msg.edit(view=None)
                except Exception:
                    pass
            except Exception:
                view = self.ChoiceView(choices, self._round_timeout_seconds)
                await view.on_timeout()
                choice = view.result
        summary = None
        name = self.get_participant_name(participant)
        if choice is not None:
            if etype == "action":
                summary = f"{name} chose {choice.get('stat', choice.get('text', ''))}"
            elif etype == "elimination":
                act = (choice.get("action", "") or choice.get("text", "")).upper()
            if act == "ATT":
                summary = f"{name} launches an attack"
            elif act == "DEF":
                summary = f"{name} defends"
            else:
                summary = f"{name} makes a bold move"
            if random.random() < 0.5:
                return f"{name} is eliminated.", "elimination"
        return summary or f"{name} acted.", None

    async def _handle_deadly_event(self, bot, p, round_timeout) -> Dict[str, Any]:
        pet_info = await self._get_member_pet(p)
        cat = (pet_info.get("category") or "land").lower()
        
        deadly_item = self.pools.random_deadly_item(cat)
        if not deadly_item:
            return {'type': 'skipped', 'p': p}

        style = deadly_item.get("style", "basic")
        place = deadly_item.get("name", "Unknown")
        try:
            px, py = self.game_map.random_point_in_style(style)
        except Exception:
            px, py = (0, 0)
            
        loc_data = {'style': style, 'location': place, 'x': px, 'y': py}
        
        user_obj = p if hasattr(p, "send") else None
        if not user_obj and hasattr(p, "id") and bot:
            user_obj = bot.get_user(getattr(p, "id", None))
            
        choices_src = deadly_item.get("choices", [])
        choices = [{'text': c.get('text', c.get('stat', 'Choose')), 'stat': c.get('stat')} for c in choices_src]
        
        embed = Embed(
            title=f"☠️ Deadly • {place}",
            description=str(deadly_item.get("prompt", "")),
            color=discord.Color.red()
        )
        
        default_choice = {'text': choices[0]['text'] if choices else 'Choose', 'stat': choices[0].get('stat') if choices else None}
        choice = None

        if user_obj:
            try:
                dm = await user_obj.create_dm()
                view = self.ChoiceView(choices, round_timeout)
                msg = await dm.send(embed=embed, view=view)
                await view.wait()
                try:
                    await msg.edit(view=None)
                except Exception:
                    pass
                choice = view.result or default_choice
            except Exception:
                view = self.ChoiceView(choices, round_timeout)
                await view.on_timeout()
                choice = view.result or default_choice
        else:
            view = self.ChoiceView(choices, round_timeout)
            await view.on_timeout()
            choice = view.result or default_choice
            
        name = self.get_participant_name(p)
        stat = str(choice.get('stat') or '').upper() or 'INT'
        gavg = self._game_stat_average(stat)
        pet = (pet_info or {}).get('pet', {})
        weight = self._pet_stat_weight(pet, stat)
        success = weight > gavg
        
        res = {
            'type': 'deadly',
            'p': p,
            'died': not success,
            'text': '',
            'markers': [],
            'loc': loc_data
        }
        
        if not success:
            res['text'] = f"{name} {(self._random_placeholder('eliminations') or 'is eliminated')} at {place}."
            res['markers'].append({'x': px, 'y': py, 'pos': (px, py), 'style': style, 'is_elimination': True, 'emoji': emoji_mod.mention('Broken') or '💀', 'pattern': False})
        else:
            res['text'] = f"{name} {(self._random_placeholder('successes') or 'survives')} the deadly {place}."
            res['markers'].append({'x': px, 'y': py, 'pos': (px, py), 'style': style, 'is_elimination': False, 'emoji': self._species_emoji(p), 'pattern': False})
            
        return res

    async def _handle_action_event(self, bot, p, round_timeout) -> Dict[str, Any]:
        pet_info = await self._get_member_pet(p)
        cat = (pet_info.get("category") or "land").lower()
        
        act = self.pools.random_action_for_type(cat) or self.pools.random_action_for_type("land") or self.pools.random_action_any()
        if not act:
            return {'type': 'skipped', 'p': p}
            
        loc_style, loc_name = self.pools.random_location_with_style()
        try:
            px, py = self.game_map.random_point_in_style(loc_style)
        except Exception:
            px, py = (0, 0)
            
        loc_data = {'style': loc_style, 'location': loc_name, 'x': px, 'y': py}
        
        prompt = self._apply_placeholders(str(act.get("prompt", "")).replace("{Location}", loc_name), [self.get_participant_name(p)], loc_name)
        choices_src = act.get("choices", [])
        choices = [{'text': c.get('text', c.get('stat', 'Choose')), 'stat': c.get('stat'), 'success_text': c.get('success_text'), 'failure_text': c.get('failure_text')} for c in choices_src]
        
        user_obj = p if hasattr(p, "send") else None
        if not user_obj and hasattr(p, "id") and bot:
            user_obj = bot.get_user(getattr(p, "id", None))
            
        embed = Embed(
            title=f"📋 Action • {loc_name}",
            description=prompt,
            color=discord.Color.blurple()
        )
        
        default_choice = choices[0] if choices else {'text': 'Act', 'stat': 'INT'}
        choice = None
        
        if user_obj:
            try:
                dm = await user_obj.create_dm()
                view = self.ChoiceView(choices, round_timeout)
                msg = await dm.send(embed=embed, view=view)
                await view.wait()
                try:
                    await msg.edit(view=None)
                except Exception:
                    pass
                choice = view.result or default_choice
            except Exception:
                view = self.ChoiceView(choices, round_timeout)
                await view.on_timeout()
                choice = view.result or default_choice
        else:
            view = self.ChoiceView(choices, round_timeout)
            await view.on_timeout()
            choice = view.result or default_choice
            
        stat = str(choice.get('stat') or '').upper() or 'INT'
        gavg = self._game_stat_average(stat)
        pet = (pet_info or {}).get('pet', {})
        weight = self._pet_stat_weight(pet, stat)
        success = weight > gavg
        name = self.get_participant_name(p)
        
        res = {
            'type': 'action',
            'p': p,
            'success': success,
            'text': '',
            'markers': [],
            'loc': loc_data
        }
        
        if success:
            res['text'] = f"{name} succeeds: {self._apply_placeholders(choice.get('success_text') or choice.get('text') or '', [name], loc_name)}"
            res['markers'].append({'x': px, 'y': py, 'pos': (px, py), 'style': loc_style, 'is_elimination': False, 'emoji': self._species_emoji(p)})
        else:
            res['text'] = f"{name} fails: {self._apply_placeholders(choice.get('failure_text') or choice.get('text') or '', [name], loc_name)}"
            res['markers'].append({'x': px, 'y': py, 'pos': (px, py), 'style': loc_style, 'is_elimination': False, 'emoji': self._species_emoji(p)})
            
        return res

    async def _handle_elimination_event(self, bot, group, round_timeout) -> Dict[str, Any]:
        elems = []
        types = []
        for gp in group:
            info = await self._get_member_pet(gp)
            elems.append(str((info.get("element") or "basic")).lower())
            types.append(str((info.get("category") or "land")).lower())
            
        fallback_elem = elems[0] if elems else "basic"
        chosen_elem = max(set(elems), key=elems.count) if elems else fallback_elem
        scenario = self.pools.random_elimination_for_element(chosen_elem, len(group))
        
        if not scenario:
            return {'type': 'skipped', 'group': group}
            
        style = scenario.get("style", "basic")
        loc_name = self.pools.random_location_for_style(style)
        
        coords = []
        loc_updates = {}
        for gp in group:
            try:
                px, py = self.game_map.random_point_in_style(style)
            except Exception:
                px, py = (0, 0)
            loc_updates[gp] = {'style': style, 'location': loc_name, 'x': px, 'y': py}
            coords.append((px, py))
            
        prompt = str(scenario.get("prompt", ""))
        names = [self.get_participant_name(gp) for gp in group]
        for idx, nm in enumerate(names, start=1):
            prompt = prompt.replace(f"{{P{idx}}}", nm)
        prompt = prompt.replace("{LOCATION_PLACEHOLDER}", loc_name)
        prompt = self._apply_placeholders(prompt, names, loc_name)
        
        choices_cfg = [{'text': 'ATT', 'action': 'ATT'}, {'text': 'DEF', 'action': 'DEF'}]
        
        async def ask_player(gp):
            user_obj = gp if hasattr(gp, "send") else None
            if not user_obj and hasattr(gp, "id") and bot:
                user_obj = bot.get_user(getattr(gp, "id", None))
                
            embed = Embed(title=f"⚔️ Elimination • {loc_name}", description=prompt, color=discord.Color.orange())
            choice = None
            default = choices_cfg[random.randrange(len(choices_cfg))]
            
            if user_obj:
                try:
                    dm = await user_obj.create_dm()
                    view = self.ChoiceView(choices_cfg, round_timeout)
                    msg = await dm.send(embed=embed, view=view)
                    await view.wait()
                    try:
                        await msg.edit(view=None)
                    except Exception:
                        pass
                    choice = view.result or default
                except Exception:
                    view = self.ChoiceView(choices_cfg, round_timeout)
                    await view.on_timeout()
                    choice = view.result or default
            else:
                view = self.ChoiceView(choices_cfg, round_timeout)
                await view.on_timeout()
                choice = view.result or default
                
            val = str((choice.get('action') or choice.get('text') or 'ATT')).upper()
            return gp, val

        responses = await asyncio.gather(*[ask_player(gp) for gp in group])
        selections = dict(responses)
        
        defenders = [gp for gp in group if selections.get(gp) == 'DEF']
        attackers = [gp for gp in group if selections.get(gp) == 'ATT']
        all_defend = len(defenders) == len(group)
        all_attack = len(attackers) == len(group)
        
        res = {
            'type': 'elimination',
            'group': group,
            'died': [],
            'text_action': '',
            'text_elim': '',
            'markers': [],
            'kill_logs': [],
            'xp_awards': [],
            'loc_updates': loc_updates
        }
        
        gcx = sum(c[0] for c in coords) // max(1, len(coords))
        gcy = sum(c[1] for c in coords) // max(1, len(coords))
        
        if all_defend:
            def_phrase = self._random_placeholder('defenses') or 'defend'
            text = f"{_format_a_open([self.get_participant_name(x) for x in group])} {def_phrase} in {loc_name}; no eliminations."
            text = self._apply_placeholders(text, [self.get_participant_name(x) for x in group], loc_name)
            res['text_action'] = text
            for gp in group:
                loc = loc_updates[gp]
                res['markers'].append({'x': loc['x'], 'y': loc['y'], 'pos': (loc['x'], loc['y']), 'style': style, 'cluster': (gcx, gcy), 'is_elimination': False, 'emoji': self._species_emoji(gp), 'pattern': True})
        else:
            fallen_local = []
            for gp in group:
                sel = selections.get(gp)
                base_survive = 0.5
                if sel == 'DEF':
                    base_survive += 0.10
                penalty = self._recent_fail_penalty(gp)
                bonus = self._advantage_bonus(gp, types, style_element=style)
                group_defender_boost = 0.10 * len(defenders)
                survive_prob = max(0.0, min(1.0, base_survive + group_defender_boost - penalty + bonus))
                if all_attack:
                    survive_prob = max(0.0, min(1.0, 0.5 - penalty + bonus))
                if random.random() > survive_prob:
                    fallen_local.append(gp)
            
            res['died'] = fallen_local
            
            if fallen_local:
                 att_phrase = self._random_placeholder('attacks') or 'attack'
                 elim_phrase = self._random_placeholder('eliminations') or 'are eliminated'
                 text = f"{_format_a_open([self.get_participant_name(x) for x in attackers or group])} {att_phrase} in {loc_name}; {_format_a_open([self.get_participant_name(x) for x in fallen_local])} {elim_phrase}."
                 text = self._apply_placeholders(text, [self.get_participant_name(x) for x in group], loc_name)
                 res['text_elim'] = text
                 
                 for victim in fallen_local:
                    for killer in attackers:
                        res['kill_logs'].append({'killer': killer, 'victim': victim, 'with': [p for p in attackers if p != killer]})
                    for killer in attackers:
                        uid = getattr(killer, "id", None)
                        if uid:
                            res['xp_awards'].append((uid, len(fallen_local)))
            else:
                 succ_phrase = self._random_placeholder('successes') or 'prevail'
                 text = f"{_format_a_open([self.get_participant_name(x) for x in group])} {succ_phrase} in {loc_name}."
                 text = self._apply_placeholders(text, [self.get_participant_name(x) for x in group], loc_name)
                 res['text_action'] = text
                 
            for gp in group:
                loc = loc_updates[gp]
                if gp in fallen_local:
                    res['markers'].append({'x': loc['x'], 'y': loc['y'], 'pos': (loc['x'], loc['y']), 'style': style, 'cluster': (gcx, gcy), 'is_elimination': True, 'emoji': emoji_mod.mention('Broken') or '💀', 'pattern': True})
                else:
                    res['markers'].append({'x': loc['x'], 'y': loc['y'], 'pos': (loc['x'], loc['y']), 'style': style, 'cluster': (gcx, gcy), 'is_elimination': False, 'emoji': self._species_emoji(gp), 'pattern': True})
                    
        return res

    async def process_round_dm(self, bot: Optional[commands.Bot]) -> Dict[str, Any]:
        await self.preload_pets()
        self.round_index += 1
        round_actions: list[Any] = []
        round_eliminations: list[Any] = []
        self.round_markers = []
        
        deadly_candidates = []
        normal_candidates = []
        
        # 1. Decide candidates (sync)
        for p in list(self.alive):
            if random.random() < 0.10:
                deadly_candidates.append(p)
            else:
                normal_candidates.append(p)
                
        random.shuffle(normal_candidates)
        
        tasks = []
        
        # 2. Schedule Tasks
        for p in deadly_candidates:
            tasks.append(self._handle_deadly_event(bot, p, self._round_timeout_seconds))
            
        i = 0
        while i < len(normal_candidates):
            remaining = len(normal_candidates) - i
            is_action = random.random() < 0.5 or remaining < 2
            
            if is_action:
                p = normal_candidates[i]
                tasks.append(self._handle_action_event(bot, p, self._round_timeout_seconds))
                i += 1
            else:
                group_n = max(2, min(6, remaining))
                group = normal_candidates[i:i+group_n]
                tasks.append(self._handle_elimination_event(bot, group, self._round_timeout_seconds))
                i += group_n
                
        # 3. Execute Parallel
        results = await asyncio.gather(*tasks)
        
        # 4. Aggregate Results
        udm = None
        if UserDataManager is not None:
            udm = UserDataManager()
        
        for res in results:
            if res['type'] == 'skipped':
                # Should fallback to basic action? 
                # For now just skip logging, effectively they did nothing (Resting).
                # But they should have a marker?
                # The original code would just continue loop if act/scenario was missing.
                # So here, we do nothing.
                pass
                
            elif res['type'] == 'deadly':
                if res['died']:
                    p = res['p']
                    if p in self.alive:
                        self.alive.remove(p)
                    self.elimination_locations[p] = res.get('loc', {})
                    self.elimination_round[p] = self.round_index
                    round_eliminations.append(res['text'])
                    self.action_log.setdefault(p, []).append(res['text'])
                else:
                    p = res['p']
                    self.locations[p] = res.get('loc', {})
                    round_actions.append(res['text'])
                    self.action_log.setdefault(p, []).append(res['text'])
                self.round_markers.extend(res['markers'])
                    
            elif res['type'] == 'action':
                p = res['p']
                self.locations[p] = res.get('loc', {})
                round_actions.append(res['text'])
                self.action_log.setdefault(p, []).append(res['text'])
                if not res['success']:
                     self.recent_action_failures.setdefault(p, []).append(True)
                else:
                     self.recent_action_failures.setdefault(p, []).append(False)
                self.recent_action_failures[p] = self.recent_action_failures[p][-5:]
                self.round_markers.extend(res['markers'])
                
            elif res['type'] == 'elimination':
                for p, loc in res['loc_updates'].items():
                    self.locations[p] = loc
                    
                if res['text_action']:
                    round_actions.append(res['text_action'])
                    for p in res['group']:
                        self.action_log.setdefault(p, []).append(res['text_action'])
                        
                if res['text_elim']:
                    round_eliminations.append(res['text_elim'])
                    for p in res['group']:
                        self.action_log.setdefault(p, []).append(res['text_elim'])
                        
                for p in res['died']:
                    if p in self.alive:
                        self.alive.remove(p)
                    self.elimination_locations[p] = res['loc_updates'][p]
                    self.elimination_round[p] = self.round_index
                    
                for log in res['kill_logs']:
                    self.kill_log.setdefault(log['killer'], []).append({
                        'victim': log['victim'],
                        'with': log['with'],
                        'text': res['text_elim']
                    })
                    
                if udm:
                    async def _award_xp(u, c):
                        try:
                            pet = await udm.get_pet_data_async(str(u))
                            lvl = int((pet or {}).get("level", 1))
                            xp_award = LootCalculator.calculate_ss_xp(lvl, c)
                            if xp_award > 0:
                                await add_experience(int(u), xp_award, "ss", None)
                        except Exception:
                            pass
                    
                    xp_tasks = [_award_xp(uid, count) for uid, count in res['xp_awards']]
                    if xp_tasks:
                        await asyncio.gather(*xp_tasks)
                self.round_markers.extend(res['markers'])

        # Fill missing markers? 
        # All participants should have been processed unless 'skipped'.
        # 'skipped' means no random item found.
        # We should probably ensure everyone has a marker.
        present_positions = set()
        for m in self.round_markers:
            pos = m.get('pos')
            if isinstance(pos, (list, tuple)):
                present_positions.add((int(pos[0]), int(pos[1])))
                
        for p in self.alive:
            loc = self.locations.get(p, {})
            px = int(loc.get('x', 0))
            py = int(loc.get('y', 0))
            if (px, py) not in present_positions:
                self.round_markers.append({'x': px, 'y': py, 'pos': (px, py), 'style': loc.get('style', 'basic'), 'is_elimination': False, 'emoji': self._species_emoji(p), 'pattern': False})
                
        return {"round_index": self.round_index, "actions": round_actions, "eliminations": round_eliminations, "remaining": self.alive.copy(), "game_over": len(self.alive) <= 1}
   
    def process_round(self) -> Dict[str, Any]:
        """Process a single round of the game"""
        self.round_index += 1
        round_actions: list[Any] = []
        round_eliminations: list[Any] = []
        for p in self.alive:
            self.forms[p] = 'pet'
        self.round_markers = []
        


        try:
            if len(self.alive) >= 6 and random.random() < 0.05:
                cand = random.sample(self.alive, 6)
                side_a = [cand[0]]
                side_b = cand[1:]
                if self._style_cursor >= len(self._style_cycle):
                    random.shuffle(self._style_cycle)
                    self._style_cursor = 0
                loc_style = self._style_cycle[self._style_cursor]
                self._style_cursor += 1
                try:
                    loc_name = self.pools.random_location_for_style(loc_style)
                except Exception:
                    loc_name = 'Unknown'
                coords = []
                for participant in side_a + side_b:
                    self.locations[participant] = {'style': loc_style, 'location': loc_name, 'x': 0, 'y': 0}
                    px, py = self.game_map.random_point_in_style(loc_style)
                    self.locations[participant]['x'] = px
                    self.locations[participant]['y'] = py
                    coords.append((px, py))
                cx = sum(x for x, _ in coords) // len(coords)
                cy = sum(y for _, y in coords) // len(coords)
                self.round_markers.append({'x': cx, 'y': cy, 'pos': (cx, cy), 'style': loc_style, 'cluster': (cx, cy), 'is_elimination': True, 'emoji': '💥', 'kind': 'sacrifice'})
                for participant in side_a + side_b:
                    if participant in self.alive:
                        self.alive.remove(participant)
                        ex, ey = self.game_map.scatter_around((cx, cy), min_radius=12, max_radius=36)
                        self.locations[participant] = {'style': loc_style, 'location': loc_name, 'x': ex, 'y': ey}
                        self.elimination_locations[participant] = self.locations[participant].copy()
                        self.elimination_round[participant] = self.round_index
                        self.round_markers.append({'x': ex, 'y': ey, 'pos': (ex, ey), 'style': loc_style, 'cluster': (cx, cy), 'is_elimination': True, 'emoji': emoji_mod.mention('Broken') or '💀'})
                names_a = [self.get_participant_name(p) for p in side_a]
                names_b = [self.get_participant_name(p) for p in side_b]
                text = f"💥 Sacrifice eliminates {', '.join(names_a)} vs {', '.join(names_b)} in {loc_style.replace('_',' ').title()}. All six fall."
                round_eliminations.append(text)
                for participant in side_a + side_b:
                    self.action_log.setdefault(participant, []).append(text)
        except Exception:
            pass

        # removed predatron eliminations

        if len(self.alive) <= 1:
            return {
                'round_index': self.round_index,
                'actions': round_actions,
                'eliminations': round_eliminations,
                'remaining': self.alive.copy(),
                'game_over': True
            }

        unassigned = list(self.alive)
        random.shuffle(unassigned)
        round_mode = 'mixed'
        
        while unassigned:
            leader = unassigned[0]
            k = len(unassigned)
            if k == 2:
                side_a = [leader]
                side_b = [unassigned[1]]
                desired_a = 1
                desired_b = 1
            else:
                if k >= 2:
                    max_a = min(5, k - 1)
                    desired_a = random.randint(1, max_a)
                    max_b = min(5, k - desired_a)
                    desired_b = random.randint(1, max_b)
                    leftover = k - desired_a - desired_b
                    if leftover == 1 and k > 2:
                        if desired_b < min(5, k - desired_a):
                            desired_b += 1
                        elif desired_a < min(5, k - 1):
                            desired_a += 1
                        else:
                            desired_b = max(1, desired_b - 1)
                            desired_a = min(desired_a + 1, min(5, k - 1))
                else:
                    break
            
            if k != 2:
                side_a = [leader]
                available_pool = unassigned[1:]
                pool_copy = available_pool[:]
                random.shuffle(pool_copy)
                side_a.extend(pool_copy[:max(1, desired_a - 1)])

                remaining_pool = [p for p in unassigned if p not in side_a]
                if not remaining_pool and len(side_a) > 1:
                    moved = side_a.pop()
                    remaining_pool = [moved]
                desired_b = max(1, min(desired_b, len(remaining_pool)))
                random.shuffle(remaining_pool)
                side_b = remaining_pool[:min(desired_b, len(remaining_pool))]
            
            if round_mode == 'actions_only':
                is_elim = False
            elif round_mode == 'elims_only':
                is_elim = True
            else:
                psel = random.random()
                if psel < 0.30:
                    is_elim = False
                elif psel < 0.74:
                    is_elim = True
                else:
                    unassigned.append(unassigned.pop(0))
                    continue
            # Simplified narration without external templates
            if self._style_cursor >= len(self._style_cycle):
                random.shuffle(self._style_cycle)
                self._style_cursor = 0
            loc_style = self._style_cycle[self._style_cursor]
            self._style_cursor += 1
            try:
                loc_name = self.pools.random_location_for_style(loc_style)
            except Exception:
                loc_name = f"{loc_style.replace('_',' ').title()} Zone"
            names_a = [self.get_participant_name(p) for p in side_a]
            names_b = [self.get_participant_name(p) for p in side_b]
            if is_elim:
                text = f"{', '.join(names_a)} eliminate {', '.join(names_b)} in the {loc_name}."
            else:
                text = f"{', '.join(names_a)} and {', '.join(names_b)} clash in the {loc_name}."
            
            # Use participant-assigned locations for markers to ensure placement inside chosen terrain
            na = len(side_a)
            nb = len(side_b)
            coords_a: List[Tuple[int, int]] = []
            coords_b: List[Tuple[int, int]] = []
            def centroid(points: List[Tuple[int, int]]) -> Tuple[int, int]:
                if not points:
                    return self.game_map.random_point_in_style(loc_style)
                sx = sum(x for x, _ in points)
                sy = sum(y for _, y in points)
                return (int(sx / len(points)), int(sy / len(points)))
            for participant in side_a + side_b:
                self.locations[participant] = {
                    'style': loc_style,
                    'location': loc_name,
                    'x': 0,
                    'y': 0
                }
                px, py = self.game_map.random_point_in_style(loc_style)
                self.locations[participant]['x'] = px
                self.locations[participant]['y'] = py
            coords_a = [(int(self.locations.get(p, {}).get('x', 0)), int(self.locations.get(p, {}).get('y', 0))) for p in side_a]
            coords_b = [(int(self.locations.get(p, {}).get('x', 0)), int(self.locations.get(p, {}).get('y', 0))) for p in side_b]
            a_form = 'pet'
            b_form = 'pet'
            if not is_elim:
                event_cx, event_cy = centroid(coords_a + coords_b)
                shared_cluster_coords_a = (event_cx, event_cy)
                for idx, p in enumerate(side_a):
                    em = self._species_emoji(p)
                    px, py = coords_a[idx]
                    self.round_markers.append({'x': px, 'y': py, 'pos': (px, py), 'style': loc_style, 'cluster': shared_cluster_coords_a, 'is_elimination': False, 'emoji': em, 'side_a': side_a, 'side_b': side_b, 'owner_side': 'A'})
                shared_cluster_coords_b = (event_cx, event_cy)
                for idx, p in enumerate(side_b):
                    em = self._species_emoji(p)
                    px, py = coords_b[idx]
                    self.round_markers.append({'x': px, 'y': py, 'pos': (px, py), 'style': loc_style, 'cluster': shared_cluster_coords_b, 'is_elimination': False, 'emoji': em, 'side_a': side_a, 'side_b': side_b, 'owner_side': 'B'})
            else:
                event_cx, event_cy = centroid(coords_a + coords_b)
                shared_cluster_coords_a = (event_cx, event_cy)
                for idx, p in enumerate(side_a):
                    em = self._species_emoji(p)
                    px, py = coords_a[idx]
                    self.round_markers.append({'x': px, 'y': py, 'pos': (px, py), 'style': loc_style, 'cluster': shared_cluster_coords_a, 'is_elimination': False, 'emoji': em, 'side_a': side_a, 'side_b': side_b, 'owner_side': 'A'})
                shared_cluster_coords_b = (event_cx, event_cy)
                for idx, p in enumerate(side_b):
                    px, py = coords_b[idx]
                    self.round_markers.append({'x': px, 'y': py, 'pos': (px, py), 'style': loc_style, 'cluster': shared_cluster_coords_b, 'is_elimination': True, 'emoji': emoji_mod.mention('Broken') or '💀', 'side_a': side_a, 'side_b': side_b, 'owner_side': 'B'})

            

            if is_elim:
                elim_emojis = self.get_event_emojis(side_a, side_b, is_elimination=True, a_form=a_form, b_form=b_form)
                emoji_text = f"{elim_emojis} {text}"
                round_eliminations.append(emoji_text)
                for participant in side_a:
                    self.action_log.setdefault(participant, []).append(emoji_text)
                for participant in side_b:
                    self.action_log.setdefault(participant, []).append(emoji_text)
                for victim in side_b:
                    for killer in side_a:
                        self.kill_log.setdefault(killer, []).append({
                            'victim': victim,
                            'with': [p for p in side_a if p != killer],
                            'text': emoji_text
                        })
                for participant in side_b:
                    if participant in self.alive:
                        self.alive.remove(participant)
                        self.elimination_locations[participant] = self.locations[participant].copy()
                        self.elimination_round[participant] = self.round_index
            else:
                action_emojis = self.get_event_emojis(side_a, side_b, is_elimination=False, a_form=a_form, b_form=b_form)
                emoji_text = f"{action_emojis} {text}"
                round_actions.append(emoji_text)
                for participant in side_a:
                    self.action_log.setdefault(participant, []).append(emoji_text)
                for participant in side_b:
                    self.action_log.setdefault(participant, []).append(emoji_text)

            for participant in side_a + side_b:
                if participant in unassigned:
                    unassigned.remove(participant)

            if len(self.alive) == 0:
                break
        
        return {
            'round_index': self.round_index,
            'actions': round_actions,
            'eliminations': round_eliminations,
            'remaining': self.alive.copy(),
            'game_over': len(self.alive) <= 1
        }


class GameSetupView(ui.View):
    def __init__(self, game_session: GameSession):
        super().__init__(timeout=None)
        self.game_session = game_session
        self.message: Optional[discord.Message] = None

    @ui.button(label="Start Game", style=ButtonStyle.green, emoji=emoji_mod.get_partial('Series'), custom_id="survivor:start")
    async def start_game(self, interaction: discord.Interaction, button: ui.Button):
        if self.game_session.creator_id and interaction.user.id != self.game_session.creator_id:
            await interaction.response.send_message("Only the game creator can start the game!", ephemeral=True)
            return

        self.game_session.started = True
        await interaction.response.send_message(f"{emoji_mod.mention('Pets') or '🐾'} **Pet Survivor Series Started!** {emoji_mod.mention('Pets') or '🐾'}", ephemeral=False)

        for item in self.children:
            cast(discord.ui.Button, item).disabled = True
        if self.message:
                     await self.message.edit(view=self)

        control_view = RoundControlView(self.game_session, cast(commands.Bot, interaction.client))
        interaction.client.add_view(control_view)
        if interaction.channel and isinstance(interaction.channel, discord.abc.Messageable):
            await control_view.send_round(cast(discord.abc.Messageable, interaction.channel))
        else:
            logging.warning(f"Could not send round: interaction.channel is not messageable or is None. Type: {type(interaction.channel)}")

    @ui.button(label="Cancel Game", style=ButtonStyle.red, emoji=emoji_mod.get_partial('No'), custom_id="survivor:cancel")
    async def cancel_game(self, interaction: discord.Interaction, button: ui.Button):
        if self.game_session.creator_id and interaction.user.id != self.game_session.creator_id:
            await interaction.response.send_message("Only the game creator can cancel the game!", ephemeral=True)
            return

        await interaction.response.send_message(f"{emoji_mod.mention('No') or '❌'} **Game Cancelled** {emoji_mod.mention('No') or '❌'}", ephemeral=False)

        for item in self.children:
            cast(discord.ui.Button, item).disabled = True
        if self.message:
            await self.message.edit(view=self)
        self.stop()

class RoundControlView(ui.View):
    def __init__(self, game_session: GameSession, bot: Optional[commands.Bot] = None):
        super().__init__(timeout=None)
        self.game_session = game_session
        self.bot = bot
        self.message: Optional[discord.Message] = None

    @ui.button(label="Next Round", style=ButtonStyle.primary, emoji=emoji_mod.get_partial('Hit'), custom_id="survivor:next")
    async def next_round(self, interaction: discord.Interaction, button: ui.Button):
        if self.game_session.creator_id and interaction.user.id != self.game_session.creator_id:
            await interaction.response.send_message("Only the game creator can advance rounds!", ephemeral=True)
            return
        
        # Defer immediately to prevent timeout
        try:
            await interaction.response.defer()
        except discord.errors.NotFound:
            # Interaction already expired, can't do anything
            return
        
        # Process the round logic
        try:
            if interaction.channel and isinstance(interaction.channel, discord.abc.Messageable):
                messageable_channel = cast(discord.abc.Messageable, interaction.channel)
                if len(self.game_session.alive) <= 1:
                    await self._end_game(messageable_channel)
                    return
                await self.send_round(messageable_channel)
                if self.message:
                    await self.message.edit(view=self)
        except Exception as e:
            # If anything goes wrong, try to send an error message
            try:
                if interaction.channel and isinstance(interaction.channel, discord.abc.Messageable):
                    await cast(discord.abc.Messageable, interaction.channel).send(f"Error advancing round: {str(e)}")
                else:
                    logging.warning(f"Could not send error message: interaction.channel is not messageable or is None. Type: {type(interaction.channel)}")
            except:
                pass

    @ui.button(label="End Games", style=ButtonStyle.red, emoji=emoji_mod.get_partial('No'), custom_id="survivor:end")
    async def end_games(self, interaction: discord.Interaction, button: ui.Button):
        if self.game_session.creator_id and interaction.user.id != self.game_session.creator_id:
            await interaction.response.send_message("Only the game creator can end the game!", ephemeral=True)
            return
        
        # Defer immediately to prevent timeout
        try:
            await interaction.response.defer()
        except discord.errors.NotFound:
            # Interaction already expired, can't do anything
            return
        
        # Process the end game logic
        try:
            if interaction.channel and isinstance(interaction.channel, discord.abc.Messageable):
                await self._end_game(cast(discord.abc.Messageable, interaction.channel))
            else:
                logging.warning(f"Could not end game: interaction.channel is not messageable or is None. Type: {type(interaction.channel)}")
        except Exception as e:
            # If anything goes wrong, try to send an error message
            try:
                if interaction.channel and isinstance(interaction.channel, discord.TextChannel):
                    await cast(discord.TextChannel, interaction.channel).send(f"Error ending game: {str(e)}")
            except:
                pass

    async def _end_game(self, channel: discord.abc.Messageable):
        if len(self.game_session.alive) == 1:
            winner = self.game_session.alive[0]
            if winner is None:
                await channel.send("⚠️ **Error: Invalid winner data**")
                return
            
            winner_name = self.game_session.get_participant_name(winner)
            if not winner_name:
                winner_name = "Unknown Champion"
            
            buf = await self._generate_champion_image(winner)
            if buf:
                await channel.send(f"{emoji_mod.mention('Champ') or '🏆'} **CHAMPION DETERMINED!**\n**{winner_name}** wins the Pet Survivor Series!", file=File(buf, filename="champion_journey.png"))
            else:
                await channel.send(f"{emoji_mod.mention('Champ') or '🏆'} **CHAMPION DETERMINED!**\n**{winner_name}** wins the Pet Survivor Series!")
            kills_by_user: Dict[str, int] = {}
            for u in self.game_session.participants:
                if u is not None:
                    kill_log_entry = self.game_session.kill_log.get(u, [])
                    if isinstance(kill_log_entry, list):
                        c = len(kill_log_entry)
                        if c > 0:
                            kills_by_user[u] = c
                    elif isinstance(kill_log_entry, int):
                        kills_by_user[u] = kill_log_entry
            
            user_rank = sorted(kills_by_user.items(), key=lambda kv: (-kv[1] if isinstance(kv[1], (int, float)) else 0, self.game_session.get_participant_name(kv[0]) if kv[0] is not None else ""))
            try:
                udm = None
                if UserDataManager is not None:
                    udm = UserDataManager()
                if udm:
                    for participant in self.game_session.participants:
                        if participant is None:
                            continue
                        pid = getattr(participant, "id", None)
                        if not pid:
                            continue
                        
                        # Get pet data for level (needed for XP calc)
                        pet = await udm.get_pet_data_async(str(pid))
                        if pet is None:
                            continue
                            
                        game_kills = int(kills_by_user.get(participant, 0))
                        w_lvl = int(pet.get("level", 1))
                        
                        win_xp = 0
                        is_winner = (winner and participant == winner)
                        
                        if is_winner:
                            win_xp = int((250 if self.game_session.official else 100) * w_lvl)
                            await udm.update_pet_battle_stats(
                                str(pid),
                                "survivor_series",
                                wins=1,
                                xp_earned=win_xp,
                                eliminations=game_kills,
                                most_eliminations=game_kills
                            )
                        else:
                            await udm.update_pet_battle_stats(
                                str(pid),
                                "survivor_series",
                                losses=1,
                                eliminations=game_kills,
                                most_eliminations=game_kills
                            )
                        
                        if win_xp > 0:
                            try:
                                await add_experience(int(pid), win_xp, "ss", None)
                            except Exception:
                                pass

            except Exception:
                pass
            try:
                if self.game_session.official:
                    data: list[Any] = []
                    fm = get_file_manager()
                    try:
                        raw_data = fm.get_logic_data(_CHAMPIONS_FILE)
                        if isinstance(raw_data, list):
                            data = raw_data
                        else:
                            data = []
                    except Exception:
                        data = []
                    n = len(data) + 1
                    if 10 <= n % 100 <= 13:
                        ord_str = f"{n}th"
                    else:
                        suf = ['th','st','nd','rd','th','th','th','th','th','th'][n % 10]
                        ord_str = f"{n}{suf}"
                    uid = getattr(winner, 'id', None)
                    elim_total = kills_by_user.get(winner, 0)
                    record = {
                        "User": {"id": uid, "name": winner_name},
                        "Winner of Game": ord_str,
                        "Eliminations": elim_total,
                        "Date": datetime.now().isoformat()
                    }
                    data.append(record)
                    try:
                        await fm.save_logic_data_async(_CHAMPIONS_FILE, data)
                    except Exception as e:
                        logger.error(f"Failed to save champion record: {e}")
            except Exception as e:
                logger.error(f"Failed to record champion: {e}")
            try:
                self.game_session.status = 'completed'
                if self.game_session.state_path:
                    os.makedirs(os.path.dirname(self.game_session.state_path), exist_ok=True)
                    fm = get_file_manager()
                    await fm.save_async(Path(self.game_session.state_path), self.game_session.to_dict())
            except Exception:
                pass
            def medal(i: int) -> str:
                return (emoji_mod.mention('Rank1') or '') if i == 0 else (emoji_mod.mention('Rank2') or '') if i == 1 else (emoji_mod.mention('Rank3') or '') if i == 2 else ''
            if user_rank:
                lines = []
                for i, (user_obj, count) in enumerate(user_rank):
                    m = medal(i)
                    prefix = f"{m} " if m else ""
                    user_name = self.game_session.get_participant_name(user_obj)
                    lines.append(f"{prefix}**{user_name}**: {count}")
                await _send_long_message(channel, "**⚔️ User Total Eliminations**\n" + "\n".join(lines))
            else:
                await _send_long_message(channel, "**⚔️ User Total Eliminations**\nNone")
        else:
            await channel.send("⚡ **Game ended by host**")
        for item in self.children:
            cast(discord.ui.Button, item).disabled = True
        if self.message:
            await self.message.edit(view=self)
        self.stop()

    async def send_round(self, channel: discord.abc.Messageable):
        result = await self.game_session.process_round_dm(self.bot)
        try:
            if not self.game_session.state_path:
                guild = getattr(channel, 'guild', None)
                gid = guild.id if guild else 0
                cid = getattr(channel, 'id', 0)
                self.game_session.guild_id = gid
                self.game_session.channel_id = cid
                if not self.game_session.game_id:
                    self.game_session.game_id = f"{gid}-{cid}-{int(time.time())}"
                os.makedirs(_GAME_STATES_DIR, exist_ok=True)
                self.game_session.state_path = os.path.join(_GAME_STATES_DIR, f"{self.game_session.game_id}.json")
            try:
                round_snapshot = {
                    "round_index": result.get("round_index"),
                    "actions": result.get("actions", []),
                    "eliminations": result.get("eliminations", []),
                    "remaining_count": len(result.get("remaining", [])),
                    "remaining_ids": [
                        getattr(p, "id", None) if hasattr(p, "id") else None
                        for p in result.get("remaining", [])
                    ]
                }
                self.game_session.rounds_history.append(round_snapshot)
            except Exception:
                pass
            fm = get_file_manager()
            await fm.save_async(Path(self.game_session.state_path), self.game_session.to_dict())
        except Exception:
            pass
        buf = await self.game_session.render_map_async()
        header = f"**⚡ ROUND {result['round_index']} RESULTS ⚡**\n*Participants remaining: {len(result['remaining'])}*"
        await channel.send(header)
        if result['actions']:
            actions_text = "**📋 ACTIONS:**\n" + "\n".join(f"•  {a}" for a in result['actions'])
            await _send_long_message(channel, actions_text)
        if result['eliminations']:
            elim_text = "**⚔️ ELIMINATIONS:**\n" + "\n".join(f"•  {e}" for e in result['eliminations'])
            await _send_long_message(channel, elim_text)
            fallen = [self.game_session.get_participant_name(p) for p, rnd in self.game_session.elimination_round.items() if rnd == result['round_index']]
            if fallen:
                fallen_text = "**🪦 Fallen:**\n" + ", ".join(f"**{name}**" for name in fallen)
                await _send_long_message(channel, fallen_text)
        if result['remaining']:
            names = []
            for p in result['remaining']:
                name = self.game_session.get_participant_name(p)
                pet_em = self.game_session._species_emoji(p)
                elem_em = self.game_session._element_emoji(p)
                names.append(f"{pet_em} {elem_em} {name}")
            remaining_text = "**🐾 REMAINING PETS:**\n" + ", ".join(f"**{n}**" for n in names)
            await _send_long_message(channel, remaining_text)
        if buf:
            self.message = await channel.send(file=File(buf, filename=f"pet_survivor_round_{result['round_index']}.png"), view=self)
        else:
            self.message = await channel.send("Use the controls below to continue.", view=self)
        if result['game_over']:
            await self._end_game(channel)


    @staticmethod
    def _render_champion_image_sync(winner_name: str, eliminations: int, avatar_bytes: Optional[bytes], info: Dict[str, Any]) -> Optional[BytesIO]:
        if not PIL_AVAILABLE or Image is None or ImageDraw is None or ImageFont is None:
            return None
        try:
            base_w = 1000
            base_h = 800
            img = Image.new('RGBA', (base_w, base_h), (232, 216, 176, 255))
            d = ImageDraw.Draw(img)
            border_col = (120, 100, 70, 255)
            d.rectangle((20, 20, base_w - 20, base_h - 20), outline=border_col, width=8)
            for i in range(6):
                shade = max(0, 180 - i * 8)
                d.rectangle((28 + i, 28 + i, base_w - 28 - i, base_h - 28 - i), outline=(shade, shade - 12, shade - 40, 90), width=1)
            font = ImageFont.load_default()
            title = "Wanted: Pet Survivor Series Champion"
            tb = d.textbbox((0, 0), title, font=font)
            tx = (base_w - (tb[2] - tb[0])) // 2
            d.text((tx, 40), title, fill=(60, 35, 20, 255), font=font)

            avatar = None
            if avatar_bytes:
                try:
                    avatar = Image.open(BytesIO(avatar_bytes)).convert('RGBA')
                except Exception:
                    avatar = None
            
            if avatar is None:
                avatar = Image.new('RGBA', (350, 350), (170, 150, 120, 255))
            
            av_size = 340
            avatar = avatar.resize((av_size, av_size))
            mask = Image.new('L', (av_size, av_size), 0)
            mdraw = ImageDraw.Draw(mask)
            mdraw.ellipse([0, 0, av_size, av_size], fill=255)
            ax = base_w // 2 - av_size // 2
            ay = 160
            img.paste(avatar, (ax, ay), mask)
            
            category = str(info.get("category", "land")).lower()
            element = str(info.get("element", "basic")).lower()
            circle_r = av_size // 2
            cx = ax + circle_r
            cy = ay + circle_r
            
            if category == "air" and element == "fire":
                left_angles = [210, 230, 250, 270]
                right_angles = [290, 310, 330, 350]
                colors = [(160, 40, 20, 200), (200, 80, 20, 200), (240, 120, 30, 200)]
                for idx, a in enumerate(left_angles):
                    r = math.radians(a)
                    bx = cx + (circle_r + 20 + idx * 8) * math.cos(r)
                    by = cy + (circle_r + 20 + idx * 8) * math.sin(r)
                    tx1 = bx - 40
                    ty1 = by - 30
                    tx2 = bx - 10
                    ty2 = by + 25
                    c = colors[min(idx, len(colors) - 1)]
                    d.polygon([(bx, by), (tx1, ty1), (tx2, ty2)], fill=c)
                for idx, a in enumerate(right_angles):
                    r = math.radians(a)
                    bx = cx + (circle_r + 20 + idx * 8) * math.cos(r)
                    by = cy + (circle_r + 20 + idx * 8) * math.sin(r)
                    tx1 = bx + 40
                    ty1 = by - 30
                    tx2 = bx + 10
                    ty2 = by + 25
                    c = colors[min(idx, len(colors) - 1)]
                    d.polygon([(bx, by), (tx1, ty1), (tx2, ty2)], fill=c)
            elif category == "water" and element == "electric":
                fin_colors = [(210, 180, 60, 220), (230, 200, 80, 200)]
                for side in [-1, 1]:
                    for i in range(3):
                        angle = 270 + side * (20 + i * 12)
                        r = math.radians(angle)
                        bx = cx + (circle_r + 18 + i * 6) * math.cos(r)
                        by = cy + (circle_r + 18 + i * 6) * math.sin(r)
                        tipx = bx + side * (45 + i * 10)
                        tipy = by - (20 + i * 5)
                        rootx = bx + side * (15 + i * 8)
                        rooty = by + (20 + i * 5)
                        c = fin_colors[min(i, len(fin_colors) - 1)]
                        d.polygon([(bx, by), (tipx, tipy), (rootx, rooty)], fill=c)
                    zig = [(cx + side * 20, cy - circle_r - 10), (cx + side * 40, cy - circle_r - 30), (cx + side * 60, cy - circle_r - 10)]
                    d.line(zig, fill=(255, 220, 40, 180), width=3)
            else:
                leaf_col = (60, 120, 60, 180)
                for i in range(10):
                    ang = 240 + i * 12
                    r = math.radians(ang)
                    bx = int(cx + (circle_r + 16) * math.cos(r))
                    by = int(cy + (circle_r + 16) * math.sin(r))
                    tx = int(cx + (circle_r + 44) * math.cos(r))
                    ty = int(cy + (circle_r + 44) * math.sin(r))
                    sx = int(cx + (circle_r + 28) * math.cos(r + 0.12))
                    sy = int(cy + (circle_r + 28) * math.sin(r + 0.12))
                    d.polygon([(tx, ty), (sx, sy), (bx, by)], fill=leaf_col)
                for i in range(10):
                    ang = 300 + i * 12
                    r = math.radians(ang)
                    bx = int(cx + (circle_r + 16) * math.cos(r))
                    by = int(cy + (circle_r + 16) * math.sin(r))
                    tx = int(cx + (circle_r + 44) * math.cos(r))
                    ty = int(cy + (circle_r + 44) * math.sin(r))
                    sx = int(cx + (circle_r + 28) * math.cos(r - 0.12))
                    sy = int(cy + (circle_r + 28) * math.sin(r - 0.12))
                    d.polygon([(tx, ty), (sx, sy), (bx, by)], fill=leaf_col)

            name_b = d.textbbox((0, 0), winner_name, font=font)
            nx = (base_w - (name_b[2] - name_b[0])) // 2
            ny = ay + av_size + 40
            d.text((nx, ny), winner_name, fill=(55, 35, 20, 255), font=font)

            species_emoji = info.get("species_emoji", "")
            element_emoji = info.get("element_emoji", "")
            category_emoji = info.get("category_emoji", "")
            pet = info.get("pet") or {}
            pet_name = str(pet.get("name") or "").strip() or winner_name
            em_line = f"{species_emoji} {element_emoji} {category_emoji} {pet_name}".strip()
            eb = d.textbbox((0, 0), em_line, font=font)
            ex = (base_w - (eb[2] - eb[0])) // 2
            ey = ny + 30
            d.text((ex, ey), em_line, fill=(70, 45, 25, 255), font=font)

            elim_text = f"Eliminations: {eliminations}"
            eb2 = d.textbbox((0, 0), elim_text, font=font)
            ex2 = (base_w - (eb2[2] - eb2[0])) // 2
            ey2 = ey + 28
            d.text((ex2, ey2), elim_text, fill=(90, 60, 35, 255), font=font)

            buf = BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)
            return buf
        except Exception as e:
            logger.error(f"Champion image sync error: {e}")
            return None

    async def _generate_champion_image(self, winner: str) -> Optional[BytesIO]:
        if not PIL_AVAILABLE:
            return None
        try:
            kills_entry = self.game_session.kill_log.get(winner, [])
            eliminations = 0
            if isinstance(kills_entry, list):
                eliminations = len(kills_entry)
            elif isinstance(kills_entry, int):
                eliminations = kills_entry

            winner_name = self.game_session.get_participant_name(winner)

            avatar_bytes = None
            guild = None
            if self.game_session.guild_id and hasattr(self, 'bot') and self.bot:
                guild = self.bot.get_guild(self.game_session.guild_id)
            if guild and hasattr(winner, 'id'):
                m = guild.get_member(winner.id)
                if m:
                    try:
                        avatar_bytes = await m.display_avatar.read()
                    except Exception:
                        avatar_bytes = None
            
            info = await self.game_session._get_member_pet(winner)
            
            return await asyncio.to_thread(
                self._render_champion_image_sync,
                winner_name,
                eliminations,
                avatar_bytes,
                info
            )
        except Exception as e:
            logger.error(f"Champion image error: {e}")
            return None

class PetSurvivorSeries(commands.Cog):
    """Pet Survivor Series with interactive maps and pet-based gameplay."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pools = DataPools()
        self.active_sessions: Dict[Tuple[int, int], Tuple[GameSession, str]] = {}
        # Offload initialization to avoid blocking startup
        self.bot.loop.create_task(self.initialize_cog())

    async def initialize_cog(self):
        try:
            await asyncio.to_thread(self.pools.reload)
            logger.info("✅ Pet Survivor data pools loaded successfully")
        except Exception as e:
            logger.error(f"❌ Failed to load Pet Survivor data pools: {e}")
        
        await self.restore_sessions()

    async def restore_sessions(self):
        try:
            os.makedirs(_GAME_STATES_DIR, exist_ok=True)
            paths = list(Path(_GAME_STATES_DIR).glob('*.json'))
            if not paths:
                return

            fm = get_file_manager()
            
            for path in paths:
                try:
                    # Offload file I/O
                    data = await asyncio.to_thread(fm.load, path)
                    
                    # Offload heavy object reconstruction (GameMap generation)
                    gs = await asyncio.to_thread(GameSession.from_dict, data, self.pools)
                    
                    if gs.status == 'active' and gs.guild_id is not None and gs.channel_id is not None:
                        self.active_sessions[(gs.guild_id, gs.channel_id)] = (gs, str(path))
                except Exception:
                    continue
            
            if self.active_sessions:
                logger.info("🔄 Restored active Pet Survivor sessions from game_states")
                for (gid, cid), (gs, path) in list(self.active_sessions.items()):
                    try:
                        v: discord.ui.View = RoundControlView(gs, self.bot) if gs.started else GameSetupView(gs)
                        cast(commands.Bot, self.bot).add_view(v)
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"Failed to restore sessions: {e}")

    @commands.hybrid_group(name="survivor")  # type: ignore[arg-type]
    async def survivor(self, ctx: commands.Context):
        """Base group for Pet Survivor Series commands."""
        pass

    @survivor.command(name="series")  # type: ignore[arg-type]
    @app_commands.describe(  # type: ignore[arg-type]
        warriors="Total number of participants (10-100)",
        users="Mention users to include in the games (separate with spaces)",
        bots="Toggle random bot inclusion (true/false)",
        roles="Mention roles to randomly select users from those roles",
        official="Record the champion to the hall of fame (true/false)"
    )
    async def series(self, ctx: commands.Context, warriors: int, users: str = "", bots: bool = False, roles: str = "", official: bool = False):
        """Start a new Pet Survivor Series session with interactive map and pet-based gameplay."""
        
        # Validate parameters
        if warriors < 10 or warriors > 100:
            return await ctx.send("❌ Warriors must be between 10 and 100.")
        
        try:
            if getattr(ctx, "defer", None):
                await ctx.defer()
        except Exception:
            pass
        try:
            await self.pools.reload_async()
        except Exception:
            try:
                self.pools.reload()
            except Exception:
                pass
        
        # Parse participants - collect Discord user objects
        participants: list[discord.User | discord.Member | str] = []
        
        # Add mentioned users
        if ctx.message and ctx.message.mentions:
            participants.extend([user for user in ctx.message.mentions])
        
        # Add users from the users parameter (split by spaces) - these are display names
        if users and ctx.guild:
            user_names = [name.strip() for name in users.split() if name.strip()]
            for user_name in user_names:
                member = discord.utils.find(lambda m: m.display_name == user_name or m.name == user_name, ctx.guild.members)
                if member:
                    participants.append(member)
        
        # Handle role mentions - randomly select users from mentioned roles
        if ctx.message and ctx.message.role_mentions:
            role_users = []
            for role in ctx.message.role_mentions:
                # Get members with this role who aren't already participants
                role_members = [member for member in role.members if member not in participants]
                role_users.extend(role_members)
            
            # Remove duplicates and shuffle
            role_users = list(set(role_users))
            random.shuffle(role_users)
            
            # Add role users to participants (respect warrior limit)
            needed = warriors - len(participants)
            if needed > 0:
                participants.extend(role_users[:needed])
        
        # Handle role names from parameter - find roles by name and select users
        elif roles:
            role_names = [name.strip() for name in roles.split() if name.strip()]
            role_users = []
            
            if ctx.guild: # Add this check
                for role_name in role_names:
                    # Find role by name in the guild
                    found_role = None
                    for guild_role in ctx.guild.roles:
                        if guild_role.name.lower() == role_name.lower():
                            found_role = guild_role
                            break
                    
                    if found_role:
                        # Get members with this role who aren't already participants
                        role_members = [member for member in found_role.members if member not in participants]
                        role_users.extend(role_members)
            
            # Remove duplicates and shuffle
            role_users = list(set(role_users))
            random.shuffle(role_users)
            
            # Add role users to participants (respect warrior limit)
            needed = warriors - len(participants)
            if needed > 0:
                participants.extend(role_users[:needed])
        
        # Fill remaining slots with server members if needed
        if len(participants) < warriors:
            remaining = warriors - len(participants)
            # Get random members from the server who aren't already participants
            if ctx.guild: # Add this check
                server_members = [member for member in ctx.guild.members if member not in participants]
                if server_members:
                    additional_members = random.sample(server_members, min(remaining, len(server_members)))
                    participants.extend(additional_members)
        
        # Include bots if requested
        if bots and len(participants) < warriors:
            remaining = warriors - len(participants)
            # Get bot members from the server who aren't already participants
            if ctx.guild: # Add this check
                bot_members = [member for member in ctx.guild.members if member.bot and member not in participants]
                if bot_members:
                    additional_bots = random.sample(bot_members, min(remaining, len(bot_members)))
                    participants.extend(additional_bots)
        
        # If still not enough, generate generic names for the remainder
        if len(participants) < warriors:
            remaining = warriors - len(participants)
            generated_names = [f"Warrior-{i+1}" for i in range(remaining)]
            participants.extend(generated_names)
        
        # Trim to exact warrior count
        participants = participants[:warriors]
        
        # Create game session
        game_session = await asyncio.to_thread(GameSession, participants, self.pools, official=official)
        await game_session.preload_pets()
        game_session.guild_id = ctx.guild.id if ctx.guild else 0
        game_session.channel_id = ctx.channel.id
        game_session.game_id = f"{game_session.guild_id}-{game_session.channel_id}-{int(time.time())}"
        os.makedirs(_GAME_STATES_DIR, exist_ok=True)
        game_session.state_path = os.path.join(_GAME_STATES_DIR, f"{game_session.game_id}.json")
        try:
            fm = get_file_manager()
            await fm.save_async(Path(game_session.state_path), game_session.to_dict())
            self.active_sessions[(game_session.guild_id, game_session.channel_id)] = (game_session, game_session.state_path)
        except Exception:
            pass

        total_tributes = len(participants)
        intro_text = f"**{total_tributes}** pets prepare to survive across diverse terrains."

        ord_text = ""
        if official:
            try:
                count = 0
                try:
                    fm = get_file_manager()
                    data = fm.get_logic_data(_CHAMPIONS_FILE)
                    if isinstance(data, list):
                        count = len(data)
                except Exception:
                    count = 0
                n = count + 1
                if 10 <= n % 100 <= 13:
                    ord_text = f"{n}th "
                else:
                    suf = ['th','st','nd','rd','th','th','th','th','th','th'][n % 10]
                    ord_text = f"{n}{suf} "
            except Exception:
                ord_text = ""
        prefix = f"The **{ord_text} Official Pet Survivor Series** will commence shortly.\n" if official else "The **Pet Survivor Series** will commence shortly.\n"
        embed = Embed(
            title=(f"{emoji_mod.mention('Series') or '🎲'} __{ord_text}__ OFFICIAL {emoji_mod.mention('Approved') or '🎟️'} PET SURVIVOR SERIES" if official else f"{emoji_mod.mention('Series') or '🎲'} PET SURVIVOR SERIES"),
            description=(
                f"{prefix} "
                f"{intro_text} await the chance to prove they are supreme."
            ),
            color=0xffd700,
            timestamp=datetime.now()
        )
        
        participant_names: List[str] = [game_session.get_participant_name(p) for p in participants]
        embed.add_field(name="🐾 Participants", value=f"{', '.join(participant_names[:20])}{'...' if len(participant_names) > 20 else ''}", inline=False)

        # Build initial round markers for starting positions (neutral scatter)
        game_session.round_markers = []
        for p in participants:
            # Get a string identifier for the participant
            if isinstance(p, (discord.User, discord.Member)):
                participant_key = str(p.id)
            else:  # p is already a string (for generated names)
                participant_key = p
            
            loc = game_session.locations.get(participant_key, {})
            emoji = game_session._species_emoji(p)
            game_session.round_markers.append({
                'x': loc.get('x', 0),
                'y': loc.get('y', 0),
                'style': loc.get('style', 'basic'),
                'is_elimination': False,
                'emoji': emoji
            })

        # Add 'Upon Completion' details after main description
        completion_text = (
            f"Winner receives **Prize Money** 💰 and is recorded in **History** 📜 as the {ord_text} **Champion** 🏆 of the Pet Survivor Series with eternal bragging rights!"
            if official else
            "Winner earns bragging rights as the champion of the Pet Survivor Series!"
        )
        embed.add_field(name="🏁 Upon Completion", value=completion_text, inline=False)

        # Map info and emoji legend field (placed right above the attached map)
        map_info = (
            "**Map** 🗺️ attached shows the *ever-changing* games terrain; users' starting positions are marked now and will update to show each round's results."
        )
        embed.add_field(name="🗺 Map", value=map_info, inline=False)

        buf = await game_session.render_map_async()
        file = None
        if buf:
            file = File(buf, filename="pet_survivor_setup.png")
            embed.set_image(url="attachment://pet_survivor_setup.png")
        
        embed.set_footer(text="Click Start Game to begin the Pet Survivor Series!")
        
        # Create view with buttons
        view = GameSetupView(game_session)
        
        # Send embed with buttons
        if file:
            message = await ctx.send(embed=embed, view=view, file=file)
        else:
            message = await ctx.send(embed=embed, view=view)
        view.message = message
        try:
            self.bot.add_view(view)
        except Exception:
            pass


    @survivor.command(name="champions")  # type: ignore[arg-type]
    async def champions(self, ctx: commands.Context):
        embeds: List[Embed] = []
        data: List[Any] = []
        try:
            fm = get_file_manager()
            try:
                data = fm.get_logic_data(_CHAMPIONS_FILE)
            except Exception:
                data = []

            if not isinstance(data, list):
                data = []
        except Exception:
            data = []
        if not data:
            return await ctx.send("No champions recorded yet.")
        for rec in data:
            user = rec.get("User", {})
            name = user.get("name") or "Unknown"
            uid = user.get("id")
            ordv = rec.get("Winner of Game")
            elim = rec.get("Eliminations")
            date = rec.get("Date")
            title = f"Pet Champion — {ordv}" if ordv else "Pet Champion"
            e = Embed(title=title, color=0xFFD700, timestamp=datetime.fromisoformat(date) if date else datetime.now())
            e.add_field(name="User", value=f"{name}{f' (ID: {uid})' if uid else ''}", inline=False)
            e.add_field(name="Eliminations", value=f"{elim if elim is not None else 0}", inline=True)
            e.add_field(name="Date", value=f"{date if date else datetime.now().isoformat()}", inline=False)
            embeds.append(e)
        class ChampionsView(ui.View):
            def __init__(self, pages: List[Embed]):
                super().__init__(timeout=300)
                self.pages = pages
                self.index = 0
                self.message: Optional[discord.Message] = None
            @ui.button(label="Previous", style=ButtonStyle.gray, emoji=emoji_mod.get_partial('Miss'))
            async def prev(self, interaction: discord.Interaction, button: ui.Button):
                self.index = (self.index - 1) % len(self.pages)
                await interaction.response.edit_message(embed=self.pages[self.index], view=self)
            @ui.button(label="Next", style=ButtonStyle.gray, emoji=emoji_mod.get_partial('Hit'))
            async def next(self, interaction: discord.Interaction, button: ui.Button):
                self.index = (self.index + 1) % len(self.pages)
                await interaction.response.edit_message(embed=self.pages[self.index], view=self)
            @ui.button(label="Close", style=ButtonStyle.red, emoji=emoji_mod.get_partial('No'))
            async def close(self, interaction: discord.Interaction, button: ui.Button):
                for item in self.children:
                    cast(discord.ui.Button, item).disabled = True
                await interaction.response.edit_message(view=self)
                self.stop()
        view = ChampionsView(embeds)
        msg = await ctx.send(embed=embeds[0], view=view)
        view.message = msg

async def setup(bot: commands.Bot):
    await bot.add_cog(PetSurvivorSeries(bot))
    logger.info("✅ Pet Survivor Series cog loaded successfully")
