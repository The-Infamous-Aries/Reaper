import discord
import random
import asyncio
import logging
import json
import os
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from Systems.Functions.user_data_manager import user_data_manager
from Systems.Functions import emoji as emoji_mod
from Systems.Pets.Logic.pet_brain import DamageCalculator, NPCBrain, LootCalculator, StatsCalculator

logger = logging.getLogger('battle_system')

MONSTER_EMOJIS: dict[str, str] = {}
RARITY_EMOJIS: dict[str, str] = {}

class UnifiedBattleView(discord.ui.View):
    BASE_DATA: dict[str, Any] = {}
    """Main battle view for handling all battle types"""

    def __init__(self, ctx, battle_type="solo", participants=None, monster=None, 
                 selected_enemy_type=None, selected_rarity=None, wild_encounter=False, is_boss_battle=False):
        super().__init__(timeout=300)
        # Load base.json data
        if not UnifiedBattleView.BASE_DATA: # Load only once
            base_json_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Logic', 'base.json'))
            try:
                with open(base_json_path, 'r') as f:
                    UnifiedBattleView.BASE_DATA = json.load(f)
                logger.info("Loaded base.json successfully.")
            except FileNotFoundError:
                logger.error(f"base.json not found at {base_json_path}")
            except json.JSONDecodeError:
                logger.error(f"Error decoding JSON from {base_json_path}")
        self.ctx = ctx
        self.battle_type = battle_type
        self.selected_enemy_type = None
        self.selected_rarity = None
        self.difficulty = "easy"
        self.message = None
        self.participants = participants or []
        self.monster = monster
        self.wild_encounter = wild_encounter
        self.is_boss_battle = is_boss_battle
        self.player_data = {}
        self.monster_hp = 0
        self.max_monster_hp = 0
        self.monster_charge_multiplier = 1.0
        self.monster_defending = False
        self.current_turn_index = 0
        self.turn_count = 0
        self.battle_started = False
        self.battle_over = False
        self.battle_log = []
        self.player_actions = {}
        self.waiting_for_actions = False
        self.round_actions = {}
        self.spectator_embed = None
        self.spectator_message = None  
        self.rewards = {}
        self.ephemeral_messages = {}  # Store ephemeral message references for reuse
        self.battle_complete = asyncio.Future()

        # Damage tracking for final summary
        self.total_damage_dealt = {}
        self.total_damage_received = {}
        self.total_monster_damage_dealt = 0
        self.total_monster_damage_received = 0

        # Round history for battle log
        self.round_history = []
        # Defending players set for PvP
        self.defending_players = set()
        # Monster action tracking
        self.monster_last_action = None
        self.monster_last_action_info = {}
        self.prev_monster_hp = 0
        # Action timeout task
        self._action_timeout_task: Optional[asyncio.Task] = None

        # Initialize damage calculator
        self.damage_calculator = DamageCalculator()
        # Initialize NPC brain for monster AI decisions
        self.npc_brain = NPCBrain()
 
    @classmethod
    async def create_async(cls, ctx, battle_type="solo", participants=None, 
                           monster=None, selected_enemy_type=None, selected_rarity=None, 
                           interaction=None, wild_encounter=False, is_boss_battle=False, forced_species=None):
        """Async factory method to create battle with loaded data"""
        view = cls(ctx, "solo", participants, monster, None, None, wild_encounter=wild_encounter, is_boss_battle=is_boss_battle)
        view.interaction = interaction
        
        # Load participants with batch operations
        user_ids = []
        user_ids = [str(ctx.author.id)]
        
        # Batch load user data
        user_data_batch = await user_data_manager.batch_load_user_data(user_ids)
        
        # Create participants list
        view.participants = []
        for i, user_id in enumerate(user_ids):
            user = ctx.author if user_id == str(ctx.author.id) else (participants[i][0] if participants else ctx.author)
            user_data = user_data_batch.get(user_id, {})
            pet = user_data.get('pets', {}).get('pet_data') or {
                'name': 'Default Pet', 'attack': 10, 'defense': 5, 'energy': 100,
                'maintenance': 0, 'happiness': 0, 'level': 1
            }
            view.participants.append((user, pet))
        
        # Generate enemy based on player's pet and difficulty
        try:
            first_pet = view.participants[0][1] if view.participants else None
        except Exception:
            first_pet = None
        # Call the new method to handle enemy generation and HP initialization
        if not is_boss_battle:
            await view.regenerate_enemy_for_difficulty(forced_species=forced_species)
            
        view.initialize_battle_data()
        await view._send_or_update_action_messages() # Send initial action buttons
        return view

    def _generate_enemy_for_pet(self, pet: Dict[str, Any], difficulty: str, forced_species: Optional[str] = None) -> Dict[str, Any]:
        """Create opponent scaled to the player's pet stats and difficulty"""
        try:
            diff = str(difficulty or 'easy').lower()
            pet_stats = StatsCalculator.calculate_pet_stats(pet) if pet else None
            atk_base = int(pet_stats['attack']) if pet_stats else 10
            def_base = int(pet_stats['defense']) if pet_stats else 5
            hp_base = int(pet_stats['max_health']) if pet_stats else 500
        except Exception:
            diff = 'easy'
            atk_base, def_base, hp_base = 10, 5, 500
        scale_map = {
            'easy': (0.7, 0.7, 0.85),
            'average': (1.1, 1.1, 1.1),
            'hard': (1.5, 1.5, 1.35)
        }
        s_atk, s_def, s_hp = scale_map.get(diff, scale_map['easy'])
        atk = int(atk_base * s_atk * random.uniform(0.9, 1.1))
        deff = int(def_base * s_def * random.uniform(0.9, 1.1))
        hp = int(hp_base * s_hp * random.uniform(0.95, 1.15))
        # Clamp attack to avoid one-shots
        if pet and hp_base > 0:
            cap = max(10, hp_base // 12)
            atk = min(atk, cap)



        if forced_species:
            enemy_type = 'basic'
            enemy_element = 'basic'
            generated_name = f"{forced_species.title()} ({diff.title()})"
        else:
            player_pet_type = str(pet.get('category', '')).lower() if pet else 'basic'
            player_pet_element = str(pet.get('element', '')).lower() if pet else 'basic'

            logger.debug(f"Player pet type: {player_pet_type}, element: {player_pet_element}, difficulty: {diff}")

            # Get all possible types and elements from DamageCalculator for easier filtering
            all_types = list(DamageCalculator.CATEGORY_ADVANTAGES.keys()) + [item for sublist in DamageCalculator.CATEGORY_ADVANTAGES.values() for item in sublist]
            all_elements = list(DamageCalculator.ELEMENT_EFFECTIVENESS.keys()) + [item for sublist in DamageCalculator.ELEMENT_EFFECTIVENESS.values() for item in sublist]
            ALL_ENEMY_TYPES = sorted(list(set(t for t in all_types if t))) # Ensure unique and remove empty strings
            ALL_ENEMY_ELEMENTS = sorted(list(set(e for e in all_elements if e))) # Ensure unique and remove empty strings

            if diff == 'easy':
                # Find enemy types/elements that are weak to player's pet
                # A type 't' is weak to player_pet_type if player_pet_type has advantage over 't'
                # Or, more simply, if 't' is in the values of CATEGORY_ADVANTAGES where player_pet_type is the key.
                # However, the original logic was: "enemy types/elements that are weak to player's pet"
                # And `TYPE_ADVANTAGES` was `Key is strong against values`.
                # So, if `player_pet_type` is strong against `t`, then `t` is weak to `player_pet_type`.
                # This means `t` is in the values of `DamageCalculator.CATEGORY_ADVANTAGES.get(player_pet_type, {})`.
                
                # Let's redefine based on the intent: find enemies that player has advantage over.
                possible_enemy_types = [
                    t for t in ALL_ENEMY_TYPES
                    if DamageCalculator.compute_type_bonus(player_pet_type, t) > 1.0
                ]
                possible_enemy_elements = [
                    e for e in ALL_ENEMY_ELEMENTS
                    if DamageCalculator.compute_element_bonus(player_pet_element, e) > 1.0
                ]
                
                logger.debug(f"Easy mode - possible enemy types (weak to player): {possible_enemy_types}")
                logger.debug(f"Easy mode - possible enemy elements (weak to player): {possible_enemy_elements}")
                if not possible_enemy_types:
                    possible_enemy_types = ALL_ENEMY_TYPES
                if not possible_enemy_elements:
                    possible_enemy_elements = ALL_ENEMY_ELEMENTS
            elif diff == 'hard':
                # Find enemy types/elements that are strong against player's pet
                # An enemy type 't' is strong against player_pet_type if 't' has advantage over player_pet_type.
                possible_enemy_types = [
                    t for t in ALL_ENEMY_TYPES
                    if DamageCalculator.compute_type_bonus(t, player_pet_type) > 1.0
                ]
                possible_enemy_elements = [
                    e for e in ALL_ENEMY_ELEMENTS
                    if DamageCalculator.compute_element_bonus(e, player_pet_element) > 1.0
                ]

                logger.debug(f"Hard mode - possible enemy types (strong against player): {possible_enemy_types}")
                logger.debug(f"Hard mode - possible enemy elements (strong against player): {possible_enemy_elements}")
                if not possible_enemy_types:
                    possible_enemy_types = ALL_ENEMY_TYPES
                if not possible_enemy_elements:
                    possible_enemy_elements = ALL_ENEMY_ELEMENTS
            else: # medium
                # Find neutral types/elements (neither strong nor weak against player)
                neutral_types = [
                    t for t in ALL_ENEMY_TYPES
                    if DamageCalculator.compute_type_bonus(player_pet_type, t) == 1.0 and \
                       DamageCalculator.compute_type_bonus(t, player_pet_type) == 1.0
                ]
                neutral_elements = [
                    e for e in ALL_ENEMY_ELEMENTS
                    if DamageCalculator.compute_element_bonus(player_pet_element, e) == 1.0 and \
                       DamageCalculator.compute_element_bonus(e, player_pet_element) == 1.0
                ]

                logger.debug(f"Medium mode - neutral enemy types: {neutral_types}")
                logger.debug(f"Medium mode - neutral enemy elements: {neutral_elements}")
                possible_enemy_types = neutral_types or ALL_ENEMY_TYPES
                possible_enemy_elements = neutral_elements or ALL_ENEMY_ELEMENTS
            
            enemy_type = random.choice(possible_enemy_types)
            enemy_element = random.choice(possible_enemy_elements)

            logger.debug(f"Generated enemy type: {enemy_type}, element: {enemy_element} for difficulty {diff}")

            # Generate a more descriptive name using base.json
            element_adjective_list = self.BASE_DATA.get('element_bases', {}).get(enemy_element, self.BASE_DATA.get('element_bases', {}).get('basic', ["Mysterious"]))
            category_noun_list = self.BASE_DATA.get('category_bases', {}).get(enemy_type, self.BASE_DATA.get('category_bases', {}).get('land', ["Creature"]))

            element_adjective = random.choice(element_adjective_list)
            category_noun = random.choice(category_noun_list)

            # Combine difficulty, element adjective, and category noun
            generated_name = f"{element_adjective} {category_noun} {diff.title()}"
        
        return {
            "name": generated_name,
            "health": hp,
            "attack": atk,
            "defense": deff,
            "type": enemy_type,
            "element": enemy_element
        }

    async def regenerate_enemy_for_difficulty(self, forced_species=None):
        """Regenerate the enemy based on current difficulty and player's pet"""
        first_pet = self.participants[0][1] if self.participants else None
        if first_pet:
            self.monster = self._generate_enemy_for_pet(first_pet, self.difficulty, forced_species=forced_species)
            if self.monster:
                self.monster_hp = self.monster['health']
                self.max_monster_hp = self.monster['health']
                logger.info(f"Regenerated monster for difficulty '{self.difficulty}': {self.monster['name']} with {self.monster_hp} HP.")
            else:
                logger.warning("Failed to regenerate monster for difficulty.")
        else:
            logger.warning("No participant pets found to regenerate enemy for difficulty.")

    async def get_monster_by_type_and_rarity(self, enemy_type: str, rarity: str) -> Dict[str, Any]:
        """Deprecated: now generates enemies by level; kept for compatibility"""
        dummy_pet = {'name': 'Dummy Pet', 'attack': 10, 'defense': 5, 'max_health': 500, 'category': 'basic', 'element': 'basic'}
        return self._generate_enemy_for_pet(dummy_pet, "easy")

    def _create_fallback_monster(self, enemy_type: str, rarity: str) -> Dict[str, Any]:
        dummy_pet = {'name': 'Dummy Pet', 'attack': 10, 'defense': 5, 'max_health': 500, 'category': 'basic', 'element': 'basic'}
        return self._generate_enemy_for_pet(dummy_pet, "easy")
  
    def initialize_battle_data(self):
        """Initialize battle data for all participants"""
        for user, pet in self.participants:
            if pet:
                # Use StatsCalculator for comprehensive stats (includes equipment)
                stats = StatsCalculator.calculate_pet_stats(pet)
                
                total_attack = stats['attack']
                total_defense = stats['defense']

                level = int(pet.get('level', 1))
                max_hp = StatsCalculator.calculate_max_health(pet)
                current_hp = int(pet.get('health', max_hp))
                
                # Apply ability tree charge bonuses
                starting_charge = 1.0
                max_charge_limit = 5.0  # Default max charge
                try:
                    from Systems.Pets.Logic.ability_tree import get_starting_charge_bonus, get_ability_effect
                    # Apply charge limit bonus FIRST so starting_charge can be clamped correctly
                    charge_limit_bonus = get_ability_effect(pet, "charge_limit_bonus")
                    if charge_limit_bonus > 0:
                        max_charge_limit = 5.0 + charge_limit_bonus

                    charge_bonus = get_starting_charge_bonus(pet)
                    if charge_bonus > 0:
                        starting_charge = min(max_charge_limit, 1.0 + charge_bonus)
                except Exception:
                    pass
                
                self.player_data[user.id] = {
                    'user': user,
                    'pet': pet,
                    'hp': current_hp,
                    'max_hp': max_hp,
                    'charge': starting_charge,
                    'charge_multiplier': starting_charge,
                    'max_charge_limit': max_charge_limit,
                    'charging': False,
                    'defending': False,
                    'alive': True,
                    'last_action': None,
                    'last_action_info': {},
                    'total_attack': total_attack,
                    'total_defense': total_defense,
                    'type': str(pet.get('category','')).lower(),
                    'element': str(pet.get('element','')).lower()
                }
                # Initialise battle skill state (cooldown, active effects, equipped snapshot)
                try:
                    from Systems.Pets.Logic.battle_skills import init_battle_skill_state
                    init_battle_skill_state(self.player_data[user.id])
                except Exception:
                    pass
                
                # Initialize damage tracking
                self.total_damage_dealt[user.id] = 0
                self.total_damage_received[user.id] = 0
                
        if self.monster:
            self.monster_hp = self.monster['health']
            self.max_monster_hp = self.monster['health']
            self.total_monster_damage_dealt = 0
            self.total_monster_damage_received = 0
            # Track previous monster HP for NPC brain decisions
            self.prev_monster_hp = self.monster_hp
            # Active skill effects on the monster (DoT, debuff, stun from player skills)
            self.monster_active_effects = []
  
    def create_hp_bar(self, current: int, max_hp: int, bar_type: str = "default", pet=None) -> str:
        """Create visual HP bar with element themes"""
        percentage = max(0, min(100, (current / max_hp) * 100))
        filled = int(percentage // 10)
        empty = 10 - filled       
        
        filled_bar = ""
        empty_char = emoji_mod.mention('BlackSquare') or '⬛'
        
        # If we have a pet/entity object with element data
        if pet and (bar_type == "pet" or bar_type == "enemy" or bar_type == "monster"):
            element = str(pet.get('element', 'basic')).lower()
            e2 = str(pet.get('secondary_element', '')).lower() if pet.get('secondary_element') else None
            
            e1_char = LootCalculator.get_pet_emoji("Elements", element) or '🟩'
            e2_char = LootCalculator.get_pet_emoji("Elements", e2) if e2 else None
            
            for i in range(filled):
                if e2_char:
                    filled_bar += e1_char if i % 2 == 0 else e2_char
                else:
                    filled_bar += e1_char
        elif bar_type == "enemy":
            # Fallback for enemy without object
            filled_char = emoji_mod.mention('YellowSquare') or '🟨'
            filled_bar = filled_char * filled
        else:
            filled_char, empty_char = "█", "░"      
            filled_bar = filled_char * filled
            
        bar = filled_bar + empty_char * empty
        return f"[{bar}] {current}/{max_hp} ({percentage:.0f}%)"
  
    def get_current_player(self):
        """Get current player's turn"""
        alive_players = [pid for pid, data in self.player_data.items() if data['alive']]
        if not alive_players:
            return None       
        current_id = alive_players[self.current_turn_index % len(alive_players)]
        return self.player_data[current_id]
 
    async def _send_or_update_action_messages(self):
        """Helper to send new or update existing ephemeral action messages"""
        if not hasattr(self, 'interaction') or not self.interaction:
            logger.warning("No interaction context available for sending/updating action messages.")
            return

        async def send_prompt_for_player(uid: int, pdata: dict):
            if not (pdata['alive'] and pdata['hp'] > 0):
                return
            try:
                action_view = EphemeralActionView(self, uid)

                # Create the action embed
                last_action = pdata.get('last_action')
                last_info = pdata.get('last_action_info', {})
                last_line = ""
                if last_action == 'attack':
                    tgt = last_info.get('target')
                    dmg = last_info.get('damage')
                    parry = last_info.get('parry_damage', 0)
                    extra = f" | Parry {parry}" if parry else ""
                    last_line = f"\nLast round: {emoji_mod.mention('Attack') or '⚔️'} Attack → {dmg} dmg{(' to ' + tgt) if tgt else ''}{extra}"
                elif last_action == 'defend':
                    eff = last_info.get('effectiveness')
                    parry_dealt = last_info.get('parry_damage_dealt', 0)
                    extra = f" | Parry dealt {parry_dealt}" if parry_dealt else ""
                    last_line = f"\nLast round: {emoji_mod.mention('Defend') or '🛡️'} Defend → {eff:.2f}x{extra}" if eff is not None else f"\nLast round: {emoji_mod.mention('Defend') or '🛡️'} Defend"
                elif last_action == 'charge':
                    mult = last_info.get('multiplier', pdata.get('charge_multiplier', 1.0))
                    last_line = f"\nLast round: {emoji_mod.mention('Charge') or '⚡'} Charge → x{mult}"
                elif last_action == 'skill':
                    sname = last_info.get('skill_name', '?')
                    last_line = f"\nLast round: ✨ {sname}"

                embed = discord.Embed(
                    title=f"{emoji_mod.mention('Attack') or '⚔️'} Battle Action Required",
                    description=f"**{pdata['pet']['name']}** - Round {self.turn_count + 1}{last_line}\nChoose your action:",
                    color=0x00ff00
                )

                if uid in self.ephemeral_messages and self.ephemeral_messages[uid]:
                    try:
                        await self.ephemeral_messages[uid].edit(embed=embed, view=action_view)
                    except discord.NotFound:
                        logger.debug(f"Ephemeral message for {uid} not found, sending new one.")
                        del self.ephemeral_messages[uid]
                        msg = await self.interaction.followup.send(embed=embed, view=action_view, ephemeral=True)
                        self.ephemeral_messages[uid] = msg
                    except Exception as e:
                        logger.error(f"Error editing ephemeral message for user {uid}: {e}")
                        try:
                            msg = await self.interaction.followup.send(embed=embed, view=action_view, ephemeral=True)
                            self.ephemeral_messages[uid] = msg
                        except Exception as e2:
                            logger.error(f"Fallback send also failed for user {uid}: {e2}")
                else:
                    msg = await self.interaction.followup.send(embed=embed, view=action_view, ephemeral=True)
                    self.ephemeral_messages[uid] = msg

            except Exception as e:
                logger.error(f"Error sending/updating action message to user {uid}: {e}")

        tasks = [send_prompt_for_player(uid, pdata) for uid, pdata in self.player_data.items()]
        if tasks:
            await asyncio.gather(*tasks)

    async def start_action_collection(self):
        """Start action collection - updates ephemeral action buttons for each player"""
        if self.battle_over:
            return

        self.waiting_for_actions = True
        self.player_actions.clear()

        # Cancel any previous timeout task
        if self._action_timeout_task and not self._action_timeout_task.done():
            self._action_timeout_task.cancel()

        # Update the main battle message without a resend button
        waiting_embed = self.build_spectator_embed("⏳ Waiting for players to choose actions...")
        try:
            await self.message.edit(embed=waiting_embed, view=None)
        except discord.NotFound:
            logger.warning("Main battle message not found during action collection")
        except discord.HTTPException as e:
            logger.error(f"Error updating main battle message: {e}")

        # Update ephemeral action messages to each alive player
        await self._send_or_update_action_messages()

        # Start a timeout so the battle never stalls if a player goes AFK
        self._action_timeout_task = asyncio.create_task(self._action_timeout())

        return True

    async def _action_timeout(self, timeout: int = 120):
        """Auto-submit 'attack' for any player who hasn't acted within timeout seconds."""
        await asyncio.sleep(timeout)
        if self.battle_over or not self.waiting_for_actions:
            return
        alive_players = [uid for uid, data in self.player_data.items() if data['alive'] and data['hp'] > 0]
        for uid in alive_players:
            if uid not in self.player_actions:
                logger.info(f"Action timeout: auto-submitting 'attack' for player {uid}")
                self.player_actions[uid] = {'action': 'attack', 'target': None, 'action_label': 'Attack (auto)'}
        # Trigger round processing
        await self.check_all_actions_submitted()
 
    async def check_all_actions_submitted(self):
        """Check if all players have submitted actions"""
        if not self.waiting_for_actions:
            return
        alive_players = [uid for uid, data in self.player_data.items() if data['alive'] and data['hp'] > 0]
        if len(self.player_actions) >= len(alive_players):
            self.waiting_for_actions = False

            # Cancel the timeout task since all actions are in
            if self._action_timeout_task and not self._action_timeout_task.done():
                self._action_timeout_task.cancel()

            # Mark any player with hp <= 0 as dead before processing
            for uid, data in self.player_data.items():
                if data['hp'] <= 0:
                    data['alive'] = False

            # Process the round
            if self.battle_type in ["solo"] and self.monster:
                monster_action = self.get_monster_action()
                await self.process_combat_round(monster_action)
            else:
                await self.process_round()

    async def process_combat_round(self, monster_action: str):
        """Process a complete combat round with all player actions and monster action using new roll-based system"""
        
        # Collect round summary lines to display in spectator embed
        action_lines = [f"{emoji_mod.mention('Attack') or '⚔️'} Round {self.turn_count + 1} Results"]
        self.monster_last_action = None

        # Initialize defense results storage
        self.defense_results = {}

        # ── Tick active skill effects (DoT, HoT, buff/debuff countdowns) ──────
        # IMPORTANT: check stun BEFORE tick so a stun with turns_left=1 fires
        # correctly — tick would decrement it to 0 and remove it before we see it.
        try:
            from Systems.Pets.Logic.battle_skills import tick_battle_effects, is_stunned, consume_stun
            for pid, pdata in self.player_data.items():
                if not pdata.get('alive'):
                    continue
                # 1. Check stun FIRST (before tick removes it)
                if is_stunned(pdata):
                    consume_stun(pdata)
                    self.player_actions[pid] = {'action': 'defend', 'target': None, 'action_label': 'Stunned!'}
                    action_lines.append(f"💫 {pdata['user'].display_name} is stunned and cannot act!")
                # 2. Tick effects (decrements turns_left, applies DoT/HoT, ticks cooldowns)
                net_delta, tick_lines = tick_battle_effects(pdata, pdata.get('total_attack', 10))
                if net_delta != 0:
                    pdata['hp'] = max(0, min(pdata['max_hp'], pdata['hp'] + net_delta))
                for line in tick_lines:
                    action_lines.append(line)
        except Exception as _e:
            logger.debug(f"Skill tick error: {_e}")

        # ── Tick monster active skill effects (DoT, debuff, stun from player skills) ──
        if self.monster_hp > 0 and hasattr(self, 'monster_active_effects') and self.monster_active_effects:
            try:
                from Systems.Pets.Logic.battle_skills import tick_battle_effects, is_stunned, consume_stun
                # Build a minimal proxy for tick (monster ATK used for any HoT scaling, irrelevant here)
                monster_tick_proxy = {
                    'active_effects': self.monster_active_effects,
                    'skill_cooldowns': {},
                    'skill_cooldown': 0,
                }
                # Check monster stun BEFORE tick
                if is_stunned(monster_tick_proxy):
                    consume_stun(monster_tick_proxy)
                    # Stunned monster is forced to defend this round
                    monster_action = "defend"
                    action_lines.append(f"💫 {self.monster['name']} is stunned and cannot act!")
                net_delta, tick_lines = tick_battle_effects(monster_tick_proxy, self.monster.get('attack', 10))
                self.monster_active_effects = monster_tick_proxy['active_effects']
                if net_delta != 0:
                    # Negative delta = damage to monster from DoT
                    self.monster_hp = max(0, self.monster_hp + net_delta)
                    self.total_monster_damage_received += max(0, -net_delta)
                for line in tick_lines:
                    action_lines.append(f"[Monster] {line}")
            except Exception as _me:
                logger.debug(f"Monster tick error: {_me}")

        # Process player actions
        for player_id, action_data in self.player_actions.items():
            if player_id not in self.player_data or not self.player_data[player_id]['alive']:
                continue
                
            action = action_data['action']
            player_data = self.player_data[player_id]
            player_name = player_data['user'].display_name
            
            if action == "attack":
                # Determine battle type for ability effects
                _battle_type = "boss" if self.is_boss_battle else "npc"
                # Apply active skill ATK buff/debuff multipliers
                _skill_atk_mult = 1.0
                try:
                    from Systems.Pets.Logic.battle_skills import get_atk_multiplier
                    _skill_atk_mult = get_atk_multiplier(player_data)
                except Exception:
                    pass
                # Use new roll-based attack system
                battle_result = DamageCalculator.calculate_battle_action(
                    attacker_attack=int(player_data['total_attack'] * _skill_atk_mult),
                    # Defense only applies if monster is defending this round
                    target_defense=self.monster['defense'] if getattr(self, 'monster_defending', False) else 0,
                    charge_multiplier=player_data.get('charge_multiplier', 1.0),
                    # Charge does not boost defense; keep at 1.0
                    target_charge_multiplier=1.0,
                    action_type="attack",
                    attacker_action_type="attack",
                    target_action_type=(
                        "defend" if getattr(self, 'monster_defending', False)
                        else ("charge" if monster_action == "charge" else "attack")
                    ),
                    attacker_type=str(player_data['pet'].get('category','')).lower(),
                    attacker_element=str(player_data['pet'].get('element','')).lower(),
                    attacker_element2=player_data['pet'].get('element2'),
                    defender_type=str(self.monster.get('type','')).lower(),
                    defender_element=str(self.monster.get('element','')).lower(),
                    attacker_pet_data=player_data['pet'],
                    attacker_user_id=str(player_data['user'].id),
                    battle_type=_battle_type,
                )

                # Use calculator's final damage (includes charging vulnerability when applicable)
                damage_to_monster = battle_result['final_damage']
                # Calculate roll multiplier for display
                roll_multiplier = self._get_roll_multiplier_from_result(battle_result['attack_result'], battle_result['attack_roll'])

                # Apply damage to monster
                self.monster_hp = max(0, self.monster_hp - damage_to_monster)
                self.total_damage_dealt[player_id] += damage_to_monster
                self.total_monster_damage_received += damage_to_monster

                # If monster was defending and out-defended the attack, reflect parry damage to the attacker
                if getattr(self, 'monster_defending', False) and battle_result.get('parry_damage', 0) > 0:
                    parry = battle_result['parry_damage']
                    player_data['hp'] = max(0, player_data['hp'] - parry)
                    self.total_damage_received[player_id] += parry
                    self.total_monster_damage_dealt += parry
                    self.battle_log.append(f"{emoji_mod.mention('Mirror') or '🪞'} {self.monster['name']} parries {player_name}, reflecting {parry} damage!")
                    action_lines.append(f"{emoji_mod.mention('Mirror') or '🪞'} {self.monster['name']} parries {player_name} for {parry}")
                
                # Add roll result to battle log
                if battle_result['attack_result'] == "miss":
                    self.battle_log.append(f"{emoji_mod.mention('Attack') or '⚔️'} {player_name} attacks but misses completely! (Roll: {battle_result['attack_roll']})")
                    action_lines.append(f"{emoji_mod.mention('Attack') or '⚔️'} {player_name} attacks but misses! (Roll: {battle_result['attack_roll']})")
                else:
                    charge_text = f" (Charged x{player_data.get('charge_multiplier', 1.0)}!)" if player_data.get('charge_multiplier', 1.0) > 1.0 else ""
                    critical_text = " **CRITICAL HIT!**" if battle_result.get('is_critical', False) else ""
                    self.battle_log.append(f"{emoji_mod.mention('Attack') or '⚔️'} {player_name} attacks for {battle_result['final_damage']} damage! (Roll: {battle_result['attack_roll']}, Result: {battle_result['attack_result']}){charge_text}{critical_text}")
                    action_lines.append(f"{emoji_mod.mention('Attack') or '⚔️'} {player_name} hits for {battle_result['final_damage']} damage (Roll: {battle_result['attack_roll']}, Result: {battle_result['attack_result']}){charge_text}{critical_text}")
                
                # Reset charge after attack
                player_data['charge_multiplier'] = 1.0
                if 'charge' in player_data:
                    player_data['charge'] = 1.0
                # Track last action
                player_data['last_action'] = 'attack'
                player_data['last_action_info'] = {
                    'type': 'attack',
                    'target': self.monster.get('name', 'Enemy'),
                    'damage': damage_to_monster,
                    'parry_damage': battle_result.get('parry_damage', 0),
                    'roll': battle_result.get('attack_roll'),
                    'multiplier': roll_multiplier,
                    'result': battle_result.get('attack_result'),
                    'action_label': self.player_actions.get(player_id, {}).get('action_label', 'Attack')
                }
                
            elif action == "defend":
                # Use new roll-based defend system
                target_id = action_data.get('target', player_id)
                _battle_type = "boss" if self.is_boss_battle else "npc"
                # Apply active skill DEF buff/debuff multipliers
                try:
                    from Systems.Pets.Logic.battle_skills import get_def_multiplier
                    _def_mult = get_def_multiplier(player_data)
                except Exception:
                    _def_mult = 1.0

                battle_result = DamageCalculator.calculate_battle_action(
                    attacker_attack=int(player_data['total_defense'] * _def_mult),
                    target_defense=0,  # Defense doesn't have an opposing stat
                    charge_multiplier=player_data.get('charge_multiplier', 1.0),
                    action_type="defend",
                    attacker_action_type="defend",
                    attacker_type=str(player_data['pet'].get('category','')).lower(),
                    attacker_element=str(player_data['pet'].get('element','')).lower(),
                    attacker_element2=player_data['pet'].get('element2'),
                    defender_type=str(self.monster.get('type','')).lower(),
                    defender_element=str(self.monster.get('element','')).lower(),
                    attacker_pet_data=player_data['pet'],
                    attacker_user_id=str(player_data['user'].id),
                    battle_type=_battle_type,
                )
                
                # Store defense information with roll result
                # Mark self-defense only
                self.defense_results[player_id] = battle_result
                # Mark defender state on player for this round
                player_data['defending'] = True
                
                # Add roll result to battle log
                target_name = self.player_data[target_id]['user'].display_name if target_id in self.player_data else "themselves"
                
                if battle_result['attack_result'] == "miss":
                    self.battle_log.append(f"{emoji_mod.mention('Defend') or '🛡️'} {player_name} tries to defend {target_name} but fails! (Roll: {battle_result['attack_roll']})")
                    action_lines.append(f"{emoji_mod.mention('Defend') or '🛡️'} {player_name} fails to defend {target_name} (Roll: {battle_result['attack_roll']})")
                else:
                    charge_text = f" (Charged x{player_data.get('charge_multiplier', 1.0)}!)" if player_data.get('charge_multiplier', 1.0) > 1.0 else ""
                    roll_multiplier = self._get_roll_multiplier_from_result(battle_result['attack_result'], battle_result['attack_roll'])
                    self.battle_log.append(f"{emoji_mod.mention('Defend') or '🛡️'} {player_name} defends {target_name} with {roll_multiplier:.2f}x effectiveness! (Roll: {battle_result['attack_roll']}){charge_text}")
                    action_lines.append(f"{emoji_mod.mention('Defend') or '🛡️'} {player_name} defends {target_name} ({roll_multiplier:.2f}x effectiveness, Roll: {battle_result['attack_roll']}){charge_text}")
                
                # Reset charge after defend
                player_data['charge_multiplier'] = 1.0
                if 'charge' in player_data:
                    player_data['charge'] = 1.0
                # Track last action
                player_data['last_action'] = 'defend'
                player_data['last_action_info'] = {
                    'type': 'defend',
                    'target': target_name,
                    'effectiveness': roll_multiplier if battle_result['attack_result'] != "miss" else 0.0,
                    'roll': battle_result.get('attack_roll'),
                    'result': battle_result.get('attack_result'),
                    'action_label': self.player_actions.get(player_id, {}).get('action_label', 'Defend')
                }
                
            elif action == "charge":
                # Use new charge progression system (2-4-8-16)
                current_multiplier = player_data.get('charge_multiplier', 1.0)
                if 'charge' in player_data:
                    current_multiplier = player_data['charge']
                
                # Pass pet so get_next_charge_multiplier respects charge_limit_bonus
                next_multiplier = DamageCalculator.get_next_charge_multiplier(current_multiplier, player_data.get('pet'))
                player_data['charge_multiplier'] = next_multiplier
                player_data['charge'] = next_multiplier  # Keep both for compatibility
                player_data['charging'] = True
                
                self.battle_log.append(f"{emoji_mod.mention('Charge') or '⚡'} {player_name} charges up! (Charge: x{next_multiplier})")
                action_lines.append(f"{emoji_mod.mention('Charge') or '⚡'} {player_name} charges up (x{next_multiplier})")
                # Track last action
                player_data['last_action'] = 'charge'
                player_data['last_action_info'] = {
                    'type': 'charge',
                    'multiplier': next_multiplier,
                    'action_label': self.player_actions.get(player_id, {}).get('action_label', 'Charge')
                }

            elif action == "skill":
                # ── Battle skill use ──────────────────────────────────────────
                skill_id = action_data.get('skill_id', '')
                try:
                    from Systems.Pets.Logic.battle_skills import apply_skill
                    # Monster is the target for NPC/boss battles.
                    # Use self.monster_active_effects so DoT/debuff/stun effects
                    # persist across rounds and get ticked correctly.
                    if not hasattr(self, 'monster_active_effects'):
                        self.monster_active_effects = []
                    monster_proxy = {
                        'element': str(self.monster.get('element', 'basic')).lower(),
                        'active_effects': self.monster_active_effects,
                        'max_hp': self.max_monster_hp,
                        'total_attack': self.monster.get('attack', 10),
                        'skill_cooldowns': {},
                        'skill_cooldown': 0,
                    }
                    _battle_type = "boss" if self.is_boss_battle else "npc"
                    slot_index = action_data.get('slot_index', 0)
                    skill_result = apply_skill(skill_id, player_data, monster_proxy, battle_type=_battle_type, slot_index=slot_index)
                    if skill_result['ok']:
                        # Apply HP deltas
                        if skill_result['hp_delta_user'] != 0:
                            player_data['hp'] = max(0, min(player_data['max_hp'],
                                                           player_data['hp'] + skill_result['hp_delta_user']))
                        if skill_result['hp_delta_target'] != 0:
                            self.monster_hp = max(0, self.monster_hp + skill_result['hp_delta_target'])
                            self.total_damage_dealt[player_id] += max(0, -skill_result['hp_delta_target'])
                            self.total_monster_damage_received += max(0, -skill_result['hp_delta_target'])
                        msg = skill_result['message']
                        self.battle_log.append(f"✨ {player_name} uses {skill_result['skill_name']}! {msg}")
                        action_lines.append(f"✨ {player_name}: {msg}")
                    else:
                        action_lines.append(f"❌ {player_name} skill failed: {skill_result['message']}")
                    player_data['last_action'] = 'skill'
                    player_data['last_action_info'] = {
                        'type': 'skill',
                        'skill_name': skill_result.get('skill_name', '?'),
                        'message': skill_result.get('message', ''),
                        'action_label': skill_result.get('skill_name', 'Skill'),
                    }
                except Exception as _se:
                    logger.error(f"Skill use error: {_se}")
                    action_lines.append(f"❌ {player_name} skill error.")
                
        # Process monster action
        if self.monster_hp > 0:
            if monster_action == "attack":
                # Prepare player defense data for the damage calculator
                player_defenses = {}
                for player_id, player_data in self.player_data.items():
                    if not player_data['alive']:
                        continue
                    
                    # Self-defense only, with active skill DEF buff/debuff multiplier
                    try:
                        from Systems.Pets.Logic.battle_skills import get_def_multiplier
                        _def_mult = get_def_multiplier(player_data)
                    except Exception:
                        _def_mult = 1.0
                    base_def = player_data.get('total_defense', 0) if player_data.get('defending') else 0
                    assigned_defense = int(base_def * _def_mult)
                    
                    player_defenses[player_id] = {
                        'defense': assigned_defense,
                        # Charge does not boost defense in new rules
                        'charge_multiplier': 1.0,
                        # Explicit player state for this round
                        'defending': assigned_defense > 0,
                        'charging': player_data.get('charging', False),
                        'action': ('defend' if assigned_defense > 0 else (
                            'charge' if player_data.get('charging', False) else 'attack'
                        )),
                        'type': str(player_data['pet'].get('category', '')).lower(),
                        'element': str(player_data['pet'].get('element', '')).lower(),
                        'element2': player_data['pet'].get('element2'),
                        'species': player_data['pet'].get('species'),
                        'pet_data': player_data['pet'],
                        'user_id': str(player_data['user'].id),
                        'current_hp': player_data['hp'],
                        'max_hp': player_data['max_hp'],
                    }
                
                # Calculate monster attack against all players
                _battle_type = "boss" if self.is_boss_battle else "npc"
                battle_results = DamageCalculator.calculate_monster_vs_players(
                    monster_attack=self.monster['attack'],
                    player_defenses=player_defenses,
                    monster_charge_multiplier=self.monster_charge_multiplier,
                    monster_type=str(self.monster.get('type','')).lower(),
                    monster_element=str(self.monster.get('element','')).lower(),
                    battle_type=_battle_type,
                )
                
                # Apply results to each player
                total_damage_to_players = 0
                total_parry_to_monster = 0
                per_target_summary = {}
                for player_id, battle_result in battle_results.items():
                    if player_id not in self.player_data or not self.player_data[player_id]['alive']:
                        continue
                        
                    player_data = self.player_data[player_id]
                    
                    # Use calculator's final damage (already accounts for charging vulnerability
                    # and Last Stand low-health reduction via defender_current_hp/max_hp in dict)
                    incoming_damage = battle_result['final_damage']

                    # ── Apply skill-based damage reduction, shields, and reflect ──
                    try:
                        from Systems.Pets.Logic.battle_skills import (
                            get_damage_reduction, absorb_damage_through_shield, get_reflect_value
                        )
                        # Damage reduction from active skill effects
                        skill_dr = get_damage_reduction(player_data)
                        if skill_dr > 0:
                            incoming_damage = max(1, int(incoming_damage * (1.0 - skill_dr)))
                        # Shield absorption
                        incoming_damage, _absorbed, shield_log = absorb_damage_through_shield(player_data, incoming_damage)
                        for sl in shield_log:
                            action_lines.append(sl)
                        # Reflect damage back to monster
                        reflect_frac = get_reflect_value(player_data)
                        if reflect_frac > 0 and incoming_damage > 0:
                            reflect_dmg = max(1, int(incoming_damage * reflect_frac))
                            self.monster_hp = max(0, self.monster_hp - reflect_dmg)
                            self.total_damage_dealt[player_id] += reflect_dmg
                            self.total_monster_damage_received += reflect_dmg
                            action_lines.append(f"🪞 {player_data['user'].display_name} reflects {reflect_dmg} damage!")
                    except Exception:
                        pass

                    # Apply damage to player
                    player_data['hp'] = max(0, player_data['hp'] - incoming_damage)
                    self.total_damage_received[player_id] += incoming_damage
                    self.total_monster_damage_dealt += incoming_damage
                    total_damage_to_players += incoming_damage
                    
                    # Apply parry damage to monster if defended
                    if battle_result['parry_damage'] > 0:
                        self.monster_hp = max(0, self.monster_hp - battle_result['parry_damage'])
                        # Credit parry damage to the defending player (self-defense only)
                        self.total_damage_dealt[player_id] += battle_result['parry_damage']
                        info = self.player_data[player_id].setdefault('last_action_info', {'type': 'defend'})
                        info['parry_damage_dealt'] = info.get('parry_damage_dealt', 0) + battle_result['parry_damage']
                        self.total_monster_damage_received += battle_result['parry_damage']
                        total_parry_to_monster += battle_result['parry_damage']
                    per_target_summary[player_id] = {
                        'damage': incoming_damage,
                        'parry_damage': battle_result.get('parry_damage', 0),
                        'roll': battle_result.get('attack_roll'),
                        'result': battle_result.get('attack_result'),
                        'defended': player_defenses.get(player_id, {}).get('defending', False)
                    }
                
                # Add monster action to battle log
                charge_text = f" (Charged x{self.monster_charge_multiplier}!)" if self.monster_charge_multiplier > 1.0 else ""
                self.battle_log.append(f"{emoji_mod.mention('Attack') or '⚔️'} The {self.monster['name']} attacks the party!{charge_text}")
                action_lines.append(f"{emoji_mod.mention('Attack') or '⚔️'} {self.monster['name']} attacks the party!{charge_text}")
                self.monster_last_action = 'attack'
                self.monster_last_action_info = {
                    'type': 'attack',
                    'total_damage': total_damage_to_players,
                    'total_parry_taken': total_parry_to_monster,
                    'per_target': per_target_summary
                }
                
                # Guard information removed (self-defense only)
                        
            elif monster_action == "defend":
                self.monster_defending = True
                self.battle_log.append(f"{emoji_mod.mention('Defend') or '🛡️'} The {self.monster['name']} takes a defensive stance!")
                action_lines.append(f"{emoji_mod.mention('Defend') or '🛡️'} {self.monster['name']} takes a defensive stance!")
                self.monster_last_action = 'defend'
                self.monster_last_action_info = { 'type': 'defend' }
                
            elif monster_action == "charge":
                # Use new charge progression for monster too
                self.monster_charge_multiplier = DamageCalculator.get_next_charge_multiplier(self.monster_charge_multiplier)
                self.battle_log.append(f"{emoji_mod.mention('Charge') or '⚡'} The {self.monster['name']} is powering up! (Charge: x{self.monster_charge_multiplier})")
                action_lines.append(f"{emoji_mod.mention('Charge') or '⚡'} {self.monster['name']} is charging (x{self.monster_charge_multiplier})")
                self.monster_last_action = 'charge'
                self.monster_last_action_info = { 'type': 'charge', 'multiplier': self.monster_charge_multiplier }
                
        # Clear player actions after processing
        self.player_actions.clear()
        
        # Reset states
        # Clear defense state tracking
        if hasattr(self, 'defense_results'):
            self.defense_results.clear()
            
        for player_data in self.player_data.values():
            player_data['charging'] = False
            player_data['defending'] = False
            
        # Reset monster defense state (charge persists until used in attack)
        self.monster_defending = False
        # Reset monster charge after attack (like players)
        if monster_action == "attack":
            self.monster_charge_multiplier = 1.0
        # Track previous monster HP for next NPCBrain decision
        self.prev_monster_hp = self.monster_hp
            
        # Increment turn counter after processing the round
        self.turn_count += 1

        # Build round summary for battle log
        round_summary = f"**Round {self.turn_count}**\n"
        for player_id, player in self.player_data.items():
            if not player['alive']:
                continue

            action_info = player.get('last_action_info', {})
            action_label = action_info.get('action_label', player.get('last_action'))
            
            if player.get('last_action') == 'attack':
                target_name = action_info.get('target')
                damage = action_info.get('damage', 0)
                round_summary += f"- {player['user'].display_name} used {action_label} on {target_name} dealing {damage} damage.\n"
            elif player.get('last_action') == 'defend':
                effectiveness = action_info.get('effectiveness', 0)
                round_summary += f"- {player['user'].display_name} used {action_label} with {effectiveness:.2f}x effectiveness.\n"
            elif player.get('last_action') == 'charge':
                charge_mult = action_info.get('multiplier', 0)
                round_summary += f"- {player['user'].display_name} used {action_label} and is now at {charge_mult}x charge.\n"

        monster_action_info = getattr(self, 'monster_last_action_info', {})
        if getattr(self, 'monster_last_action', None) == 'attack':
            total_damage = monster_action_info.get('total_damage', 0)
            round_summary += f"- {self.monster['name']} attacked the party, dealing {total_damage} total damage.\n"
        elif getattr(self, 'monster_last_action', None) == 'defend':
            round_summary += f"- {self.monster['name']} took a defensive stance.\n"
        elif getattr(self, 'monster_last_action', None) == 'charge':
            charge_mult = monster_action_info.get('multiplier', 0)
            round_summary += f"- {self.monster['name']} charged and is now at {charge_mult}x charge.\n"

        self.round_history.append(round_summary)

        
        await self.check_victory_conditions()        
        
        if not self.battle_over:
            # Show battle results with round completion message
            action_text = "\n".join(action_lines)
            spectator_embed = self.build_spectator_embed(action_text)
            try:
                await self.message.edit(embed=spectator_embed)
                await self.start_action_collection()
            except discord.NotFound:
                self.message = await self.ctx.channel.send(embed=spectator_embed)
                await self.start_action_collection()
        else:
            # Show final battle results with damage summary
            final_embed = self.build_final_battle_embed("")
            try:
                await self.message.edit(embed=final_embed, view=None)
            except discord.NotFound:
                self.message = await self.ctx.channel.send(embed=final_embed, view=None)

    async def process_round(self):
        """Process a single round for PvP battles using new roll-based system"""
        action_text = f"{emoji_mod.mention('Attack') or '⚔️'} **Round {self.turn_count + 1} Results**\n\n"
        
        # Process defend actions first to set up defense states
        for player_id, action_data in self.player_actions.items():
            if action_data['action'] == 'defend':
                player_data = self.player_data[player_id]
                player_name = player_data['user'].display_name
                
                # Use new roll-based defend system
                battle_result = DamageCalculator.calculate_battle_action(
                    attacker_attack=player_data['total_defense'],
                    target_defense=0,  # Defense doesn't have an opposing stat
                    charge_multiplier=player_data.get('charge_multiplier', 1.0),
                    action_type="defend",
                    attacker_action_type="defend",
                    attacker_species=player_data['pet'].get('species'),
                    attacker_pet_data=player_data['pet'],
                    attacker_user_id=str(player_data['user'].id),
                    battle_type="pvp",
                )
                
                # Store defense effectiveness for later use
                roll_multiplier = self._get_roll_multiplier_from_result(battle_result['attack_result'], battle_result['attack_roll'])
                player_data['defense_effectiveness'] = roll_multiplier if battle_result['attack_result'] != "miss" else 0.0
                player_data['defending'] = True  # Mark as defending for this round
                # Track last action for UI visibility until next pick
                player_data['last_action'] = 'defend'
                player_data['last_action_info'] = {
                    'type': 'defend',
                    'effectiveness': player_data['defense_effectiveness'],
                    'roll': battle_result.get('attack_roll'),
                    'result': battle_result.get('attack_result')
                }
                
                # Add roll result to action text
                if battle_result['attack_result'] == "miss":
                    action_text += f"{emoji_mod.mention('Defend') or '🛡️'} **{player_name}** tries to defend but fails! (Roll: {battle_result['attack_roll']})\n"
                else:
                    charge_text = f" (Charged x{player_data.get('charge_multiplier', 1.0)}!)" if player_data.get('charge_multiplier', 1.0) > 1.0 else ""
                    dverb = battle_result.get('attacker_action_name', 'Defend')
                    action_text += f"{emoji_mod.mention('Defend') or '🛡️'} **{player_name}** uses {dverb} with {roll_multiplier:.2f}x effectiveness! (Roll: {battle_result['attack_roll']}){charge_text}\n"
                
                # Reset charge after defend
                player_data['charge_multiplier'] = 1.0
                if 'charge' in player_data:
                    player_data['charge'] = 1.0
        
        # Process charge actions
        for player_id, action_data in self.player_actions.items():
            if action_data['action'] == 'charge':
                player_data = self.player_data[player_id]
                player_name = player_data['user'].display_name
                
                # Use new charge progression system (2-4-8-16)
                current_multiplier = player_data.get('charge_multiplier', 1.0)
                if 'charge' in player_data:
                    current_multiplier = player_data['charge']
                
                # Pass pet so get_next_charge_multiplier respects charge_limit_bonus
                next_multiplier = DamageCalculator.get_next_charge_multiplier(current_multiplier, player_data.get('pet'))
                player_data['charge_multiplier'] = next_multiplier
                player_data['charge'] = next_multiplier  # Keep both for compatibility
                # Track last action for UI visibility until next pick
                player_data['last_action'] = 'charge'
                player_data['last_action_info'] = {
                    'type': 'charge',
                    'multiplier': next_multiplier
                }
                
                labels = DamageCalculator.get_action_labels(
                    str(player_data['pet'].get('category','')).lower(),
                    str(player_data['pet'].get('element','')).lower(),
                    species=player_data['pet'].get('species'),
                    custom_labels=player_data['pet'].get('action_labels', {})
                )
                verb = labels.get('charge', 'Charging')
                action_text += f"{emoji_mod.mention('Charge') or '⚡'} **{player_name}** channels {verb}! (Charge: x{next_multiplier})\n"
        
        # Process attack actions
        for player_id, action_data in self.player_actions.items():
            if action_data['action'] == 'attack' and action_data['target']:
                attacker_data = self.player_data[player_id]
                defender_data = self.player_data[action_data['target']]
                
                if not attacker_data['alive'] or attacker_data['hp'] <= 0:
                    continue
                
                attacker_name = attacker_data['user'].display_name
                defender_name = defender_data['user'].display_name
                
                # Check if defender is defending
                defender_defending = defender_data.get('defending', False)
                
                # Use unified calculator with defend-only mitigation and built-in parry
                battle_result = DamageCalculator.calculate_battle_action(
                    attacker_attack=attacker_data['total_attack'],
                    target_defense=defender_data['total_defense'] if defender_defending else 0,
                    charge_multiplier=attacker_data.get('charge_multiplier', 1.0),
                    target_charge_multiplier=1.0,
                    action_type="attack",
                    attacker_action_type="attack",
                    target_action_type=(
                        'defend' if defender_defending else (
                            'charge' if defender_data.get('charging', False) else 'attack'
                        )
                    ),
                    attacker_type=str(attacker_data['pet'].get('category','')).lower(),
                    attacker_element=str(attacker_data['pet'].get('element','')).lower(),
                    defender_type=str(defender_data['pet'].get('category','')).lower(),
                    defender_element=str(defender_data['pet'].get('element','')).lower(),
                    attacker_species=attacker_data['pet'].get('species'),
                    defender_species=defender_data['pet'].get('species'),
                    attacker_pet_data=attacker_data['pet'],
                    defender_pet_data=defender_data['pet'],
                    attacker_user_id=str(attacker_data['user'].id),
                    defender_user_id=str(defender_data['user'].id),
                    defender_current_hp=defender_data['hp'],
                    defender_max_hp=defender_data['max_hp'],
                    battle_type="pvp",
                )
                
                final_damage = battle_result['final_damage']
                parry_damage = battle_result.get('parry_damage', 0)
                
                # Apply low health damage reduction to attacker if taking parry damage and below 25% health
                attacker_current_hp_percent = attacker_data['hp'] / attacker_data['max_hp']
                if attacker_current_hp_percent < 0.25 and parry_damage > 0:
                    try:
                        from Systems.Pets.Logic.ability_tree import get_low_health_damage_reduction
                        damage_reduction = get_low_health_damage_reduction(attacker_data['pet'])
                        if damage_reduction > 0:
                            parry_damage = int(parry_damage * (1.0 - damage_reduction))
                    except Exception:
                        pass
                
                # Apply damage
                if parry_damage > 0:
                    # Parry successful - reflect damage
                    attacker_data['hp'] = max(0, attacker_data['hp'] - parry_damage)
                    defender_data['hp'] = max(0, defender_data['hp'] - final_damage)
                    
                    # Track damage stats
                    self.total_damage_dealt[player_id] += final_damage
                    self.total_damage_received[action_data['target']] += final_damage
                    
                    # Track parry damage (defender deals damage to attacker)
                    self.total_damage_dealt[action_data['target']] += parry_damage
                    self.total_damage_received[player_id] += parry_damage
                    
                    roll_multiplier = self._get_roll_multiplier_from_result(battle_result['attack_result'], battle_result['attack_roll'])
                    action_text += f"{emoji_mod.mention('Attack') or '⚔️'} **{attacker_name}** attacks **{defender_name}**! (Roll: {battle_result['attack_roll']}, Multiplier: {roll_multiplier:.2f}x)\n"
                    action_text += f"{emoji_mod.mention('Defend') or '🛡️'} **{defender_name}** parries the attack!\n"
                    if final_damage > 0:
                        action_text += f"{emoji_mod.mention('Damage') or '💥'} {final_damage} damage dealt to {defender_name}\n"
                    action_text += f"{emoji_mod.mention('Charge') or '⚡'} {parry_damage} parry damage dealt to {attacker_name}\n"
                else:
                    # Normal attack or failed defense
                    defender_data['hp'] = max(0, defender_data['hp'] - final_damage)
                    
                    # Track damage stats
                    self.total_damage_dealt[player_id] += final_damage
                    self.total_damage_received[action_data['target']] += final_damage
                    
                    if battle_result['attack_result'] == "miss":
                        action_text += f"{emoji_mod.mention('Attack') or '⚔️'} **{attacker_name}** attacks **{defender_name}** but misses completely! (Roll: {battle_result['attack_roll']})\n"
                    else:
                        roll_multiplier = self._get_roll_multiplier_from_result(battle_result['attack_result'], battle_result['attack_roll'])
                        charge_text = f" (Charged x{attacker_data.get('charge_multiplier', 1.0)}!)" if attacker_data.get('charge_multiplier', 1.0) > 1.0 else ""
                        critical_text = " **CRITICAL HIT!**" if battle_result.get('is_critical', False) else ""
                        defend_text = f", reduced by defense" if defender_defending else ""
                        atk = battle_result.get('attacker_action_name', 'Attack')
                        action_text += f"{emoji_mod.mention('Attack') or '⚔️'} **{attacker_name}** uses {atk} on **{defender_name}**! (Roll: {battle_result['attack_roll']}, Multiplier: {roll_multiplier:.2f}x){charge_text}{critical_text}{defend_text} → {final_damage} damage dealt\n"
                
                # Track last action for UI visibility until next pick
                attacker_data['last_action'] = 'attack'
                attacker_data['last_action_info'] = {
                    'type': 'attack',
                    'target': defender_name,
                    'damage': final_damage,
                    'parry_damage': parry_damage,
                    'roll': battle_result.get('attack_roll'),
                    'multiplier': self._get_roll_multiplier_from_result(battle_result['attack_result'], battle_result['attack_roll']),
                    'result': battle_result.get('attack_result')
                }
                # If defender blocked/parried, annotate their last action info
                if defender_defending:
                    info = defender_data.setdefault('last_action_info', {'type': 'defend'})
                    info['blocked'] = True
                    if parry_damage > 0:
                        info['parry_damage_dealt'] = info.get('parry_damage_dealt', 0) + parry_damage
                # Reset charge after attack
                attacker_data['charge_multiplier'] = 1.0
                if 'charge' in attacker_data:
                    attacker_data['charge'] = 1.0
        
        # Reset states and increment turn
        self.defending_players.clear()
        self.player_actions.clear()  # Clear actions after processing
        for player_data in self.player_data.values():
            player_data['charging'] = False
            if 'defense_effectiveness' in player_data:
                del player_data['defense_effectiveness']
            # Reset defending flag at end of PvP round
            player_data['defending'] = False
        
        self.turn_count += 1
        
        # Check victory conditions
        await self.check_victory_conditions()
        
        if not self.battle_over:
            # Update spectator embed in channel
            spectator_embed = self.build_spectator_embed(action_text)
            try:
                await self.message.edit(embed=spectator_embed)
            except discord.NotFound:
                # Message was deleted, send new message instead
                self.message = await self.ctx.channel.send(embed=spectator_embed)
            
            # Start next action collection in channel for all players
            await self.start_action_collection()
        else:
            # Battle ended
            final_embed = self.build_final_battle_embed(action_text)
            try:
                await self.message.edit(embed=final_embed, view=None)
            except discord.NotFound:
                # Message was deleted, send new message instead
                self.message = await self.ctx.channel.send(embed=final_embed, view=None)
            
            # Send detailed battle log
            battle_log = self.generate_battle_log(action_text)
            for i, message in enumerate(battle_log):
                await asyncio.sleep(1)
                await self.ctx.channel.send(message)

    def build_battle_embed(self, action_text: str = "") -> discord.Embed:
        """Build battle embed"""
        
        # Handle battle over states
        if self.battle_over:
            return self.build_final_battle_embed(action_text)
            
        current_player = self.get_current_player()
        if not current_player:
            return discord.Embed(title="Battle Ended", color=0x808080)
        
        prefix = emoji_mod.mention('Attack') or "⚔️"
        try:
            if self.monster:
                prefix = emoji_mod.mention('NPC') or '🤖'
            else:
                bt = str(self.battle_type or '').lower()
                if bt == 'pvp':
                    prefix = emoji_mod.mention('PvP') or emoji_mod.mention('Attack') or '⚔️'
                elif bt == 'tournament':
                    prefix = emoji_mod.mention('Tournament') or '🏆'
        except Exception:
            prefix = emoji_mod.mention('Attack') or "⚔️"
        title = f"{prefix} {self.battle_type.title()} Battle"
        if self.monster:
            title = f"{prefix} Battle: {self.monster['name']}"
        
        embed = discord.Embed(
            title=title,
            description=f"Turn {self.turn_count + 1} - {current_player['user'].display_name}'s turn!",
            color=0x0099ff
        )
        
        # Show participant
        status_lines = []
        
        for player_id, data in self.player_data.items():
            if not data['alive']:
                continue
                
            user = data['user']
            pet = data['pet']
            hp_bar = self.create_hp_bar(data['hp'], data['max_hp'], "pet", pet)
            status_emojis = []

            if data['charging']:
                status_emojis.append(f"{emoji_mod.mention('Charge') or '⚡'}x{data['charge']:.1f}")
                
            status = " ".join(status_emojis) if status_emojis else (emoji_mod.mention('WhiteCircle') or "⚪")
            status_lines.append(f"{status} {user.display_name} - {pet['name']}\n{hp_bar}")
        
        embed.add_field(name=f"{emoji_mod.mention('Defend') or '🛡️'} Participants", value="\n".join(status_lines), inline=False)
        
        # Show monster if exists
        if self.monster:
            monster_hp_bar = self.create_hp_bar(self.monster_hp, self.max_monster_hp, "pet", self.monster)
            embed.add_field(
                name=f"{emoji_mod.mention('NPC') or '🤖'} {self.monster['name']}",
                value=monster_hp_bar,
                inline=False
            )
        
        if action_text:
            embed.add_field(name=f"{emoji_mod.mention('Charge') or '⚡'} Action", value=action_text[:200], inline=False)
        

        
        alive_count = sum(1 for data in self.player_data.values() if data['alive'])
        embed.set_footer(text=f"Turn {self.turn_count} | {alive_count} active fighters")
        
        return embed

    def build_spectator_embed(self, action_text: str = "") -> discord.Embed:
        """Build spectator embed for channel view (no buttons)"""
        
        # Handle battle over states
        if self.battle_over:
            return self.build_final_battle_embed(action_text)
            
        prefix = "⚔️"
        try:
            if self.monster:
                prefix = emoji_mod.mention('NPC') or '🤖'
            else:
                bt = str(self.battle_type or '').lower()
                if bt == 'pvp':
                    prefix = emoji_mod.mention('PvP') or '⚔️'
                elif bt == 'tournament':
                    prefix = emoji_mod.mention('Tournament') or '🏆'
        except Exception:
            prefix = "⚔️"
        title = f"{prefix} {self.battle_type.title()} Battle"
        if self.monster:
            title = f"{prefix} Battle: {self.monster['name']}"
        else:
            title = f"{prefix} PvP Battle"
        
        embed = discord.Embed(
            title=title,
            description=f"Round {self.turn_count + 1} - Live Battle Status",
            color=0x0099ff
        )
        
        # Show participants with detailed status
        status_lines = []
        for user_id, data in self.player_data.items():
            user = data['user']
            pet = data['pet']
            hp_bar = self.create_hp_bar(data['hp'], data['max_hp'], "pet", pet)
            charge_info = f" {emoji_mod.mention('Charge') or '⚡'}x{data['charge']:.1f}" if data['charge'] > 1.0 else ""
            charging_info = f" {emoji_mod.mention('Charge') or '🔋'}" if data['charging'] else ""
            defending_info = f" {emoji_mod.mention('Defend') or '🛡️'}" if data.get('defending') else ""
            last_action = data.get('last_action')
            last_info = data.get('last_action_info', {})
            action_label = last_info.get('action_label', last_action)
            if last_action == 'attack':
                tgt = last_info.get('target')
                dmg = last_info.get('damage')
                parry = last_info.get('parry_damage', 0)
                extra = f" | Parry {parry}" if parry else ""
                last_line = f"\nLast: {emoji_mod.mention('Attack') or '⚔️'} {action_label} → {dmg} dmg{(' to ' + tgt) if tgt else ''}{extra}"
            elif last_action == 'defend':
                eff = last_info.get('effectiveness')
                parry_dealt = last_info.get('parry_damage_dealt', 0)
                extra = f" | Parry dealt {parry_dealt}" if parry_dealt else ""
                last_line = f"\nLast: {emoji_mod.mention('Defend') or '🛡️'} {action_label} → {eff:.2f}x{extra}" if eff is not None else f"\nLast: {emoji_mod.mention('Defend') or '🛡️'} {action_label}"
            elif last_action == 'charge':
                mult = last_info.get('multiplier', data.get('charge', 1.0))
                last_line = f"\nLast: {emoji_mod.mention('Charge') or '⚡'} {action_label} → x{mult}"
            else:
                last_line = ""
            
            # Status indicators
            if not data['alive'] or data['hp'] <= 0:
                status = f"{emoji_mod.mention('Dead') or '💀'} Defeated"
            elif user_id in self.player_actions:
                status = f"{emoji_mod.mention('Check') or '✅'} Action Ready"
            elif data['hp'] > 0:
                status = f"{emoji_mod.mention('Loading') or '⏳'} Choosing Action"
            else:
                status = f"{emoji_mod.mention('GreenCircle') or '🟢'} Alive"
                
            status_lines.append(
                f"**{user.display_name}** - {pet['name']}\n"
                f"{hp_bar} {data['hp']}/{data['max_hp']} HP{charge_info}{charging_info}{defending_info}{last_line}\n"
                f"Status: {status}"
            )
        
        embed.add_field(
            name="🐾 Participants",
            value="\n".join(status_lines) if status_lines else "No participants",
            inline=False
        )
        
        # Show monster for PvE battles
        if self.monster and self.battle_type in ["solo"]:
            monster_hp_bar = self.create_hp_bar(self.monster_hp, self.max_monster_hp, "monster", self.monster)
            monster_charge_info = f" {emoji_mod.mention('Charge') or '⚡'}x{self.monster_charge_multiplier:.1f}" if self.monster_charge_multiplier > 1.0 else ""
            monster_defense_info = f" {emoji_mod.mention('Defend') or '🛡️'}" if self.monster_defending else ""
            # Enemy last action summary
            m_last = getattr(self, 'monster_last_action', None)
            m_info = getattr(self, 'monster_last_action_info', {})
            if m_last == 'attack':
                td = m_info.get('total_damage', 0)
                tp = m_info.get('total_parry_taken', 0)
                m_last_line = f"\nLast: {emoji_mod.mention('Attack') or '⚔️'} Attack → {td} total dmg" + (f" | Parried back {tp}" if tp else "")
            elif m_last == 'defend':
                m_last_line = f"\nLast: {emoji_mod.mention('Defend') or '🛡️'} Defend"
            elif m_last == 'charge':
                mult = m_info.get('multiplier', self.monster_charge_multiplier)
                m_last_line = f"\nLast: {emoji_mod.mention('Charge') or '⚡'} Charge → x{mult}"
            else:
                m_last_line = ""
            
            embed.add_field(
                name=f"{emoji_mod.mention('NPC') or '🤖'} {self.monster['name']}",
                value=f"{monster_hp_bar} {self.monster_hp}/{self.max_monster_hp} HP{monster_charge_info}{monster_defense_info}{m_last_line}",
                inline=False
            )
        
        if action_text:
            embed.add_field(name=f"{emoji_mod.mention('Charge') or '⚡'} Last Action", value=action_text, inline=False)
        
        # Action collection status
        if self.waiting_for_actions:
            alive_players = [uid for uid, data in self.player_data.items() if data['alive'] and data['hp'] > 0]
            ready_count = len(self.player_actions)
            total_count = len(alive_players)
            
            embed.add_field(
                name=f"{emoji_mod.mention('Loading') or '⏳'} Action Collection",
                value=f"{ready_count}/{total_count} players have chosen their actions",
                inline=False
            )
        
        embed.set_footer(text=f"Round {self.turn_count + 1} • Battle in progress")
        return embed

    def generate_battle_log(self, action_text: str = "") -> list[str]:
        """Generate simplified battle log messages"""
        messages = []
        
        # Determine victory/defeat
        if self.monster:
            if self.monster_hp <= 0:
                title = f"{emoji_mod.mention('Trophy') or '🎉'} VICTORY!"
                description = f"You defeated **{self.monster['name']}**!"
            else:
                title = f"{emoji_mod.mention('Dead') or '💀'} DEFEAT"
                description = f"You were defeated by **{self.monster['name']}**!"
        else:
            title = f"{emoji_mod.mention('Attack') or '⚔️'} BATTLE ENDED"
            description = "The battle has concluded"
        
        messages.append(f"**{title}**\n{description}")
        
        # Rewards
        if self.rewards:
            reward_lines = []
            if self.rewards['type'] == 'victory' and self.rewards['survivors']:
                for survivor in self.rewards['survivors']:
                    reward_lines.append(f"**{survivor['user'].display_name}** received rewards")
            
            if reward_lines:
                reward_msg = f"{emoji_mod.mention('Money') or '💰'} **Rewards**\n" + "\n".join(reward_lines)
                messages.append(reward_msg)
        
        return messages

    def build_final_battle_embed(self, action_text: str = "") -> discord.Embed:
        """Build final battle embed with total damage summary and loot"""
        # Determine victory/defeat
        if self.monster:
            if self.monster_hp <= 0:
                title = "🎉 VICTORY!"
                if self.is_boss_battle:
                    description = f"You have defeated the mighty **{self.monster['name']}**!"
                else:
                    description = f"You defeated **{self.monster['name']}**!"
                if self.wild_encounter:
                    description += "\n\n*This was a wild encounter. No loot or XP was awarded.*"
            else:
                title = "💀 DEFEAT"
                description = f"You were defeated by **{self.monster['name']}**!"
                if self.wild_encounter:
                    description += "\n\n*This was a wild encounter.*"
        else:
            title = "⚔️ BATTLE ENDED"
            description = "The battle has concluded"

        embed = discord.Embed(
            title=title,
            description=description,
            color=0x00ff00 if "VICTORY" in title else 0xff0000 if "DEFEAT" in title else 0x808080
        )
        
        # Add total damage summary
        if self.monster:
            monster_damage = f"**Monster ({self.monster['name']})**\n"
            monster_damage += f"• **Damage Dealt:** {self.total_monster_damage_dealt}\n"
            monster_damage += f"• **Damage Received:** {self.total_monster_damage_received}\n\n"
            monster_damage += "**Players**\n"
            
            player_damage = []
            for uid in self.player_data:
                player_name = self.player_data[uid]['user'].display_name
                dealt = self.total_damage_dealt[uid]
                received = self.total_damage_received[uid]
                player_damage.append(f"• **{player_name}:** {dealt} dealt, {received} received")
            
            monster_damage += "\n".join(player_damage)
            
            embed.add_field(
                name="📊 Total Damage Summary",
                value=monster_damage,
                inline=False
            )
        else:
            # PvP battle damage summary
            player_damage = []
            for uid in self.player_data:
                player_name = self.player_data[uid]['user'].display_name
                dealt = self.total_damage_dealt[uid]
                received = self.total_damage_received[uid]
                player_damage.append(f"• **{player_name}:** {dealt} dealt, {received} received")
            
            embed.add_field(
                name="📊 Total Damage Summary",
                value="**Players**\n" + "\n".join(player_damage),
                inline=False
            )
        
        # Add final standings and loot
        final_standings = []
        for user_id, data in self.player_data.items():
            status = "🟢 Alive" if data['hp'] > 0 else "🔴 Defeated"
            
            # Build standings text
            standings_text = f"Final HP: {data['hp']}/{data['max_hp']}"
            
            if 'loot_text' in data:
                standings_text += data['loot_text']
            
            final_standings.append(f"**{data['user'].display_name}** - {status}\n{standings_text}")
        
        if final_standings:
            embed.add_field(
                name="🏆 Final Standings & Rewards",
                value="\n\n".join(final_standings),
                inline=False
            )
        
        if action_text:
            embed.add_field(name="📜 Final Round", value=action_text[:1024], inline=False)

        if self.round_history:
            round_summary = "\n".join(self.round_history)
            embed.add_field(name="Round Breakdown", value=round_summary, inline=False)
        
        return embed

    def get_monster_action(self) -> str:
        """Determine monster's AI action using NPCBrain across health stages and party sizes"""
        if not self.monster:
            return "attack"

        # Build monster and players state for the brain
        monster_state = {
            'hp': self.monster_hp,
            'max_hp': self.max_monster_hp,
            'charge_multiplier': self.monster_charge_multiplier,
            'defending': getattr(self, 'monster_defending', False),
            'last_action': getattr(self, 'monster_last_action', None),
            'prev_hp': getattr(self, 'prev_monster_hp', None),
            'attack_stat': float(self.monster.get('attack', 1)),
            'defense_stat': float(self.monster.get('defense', 1))
        }

        players_state = []
        for uid, pdata in self.player_data.items():
            players_state.append({
                'hp': pdata.get('hp', 0),
                'max_hp': pdata.get('max_hp', 1),
                'alive': pdata.get('alive', False),
                'charging': pdata.get('charging', False)
            })

        decision = self.npc_brain.decide_action(monster_state, players_state)
        action = decision.get('action', 'attack')
        # Optionally log rationale for debugging
        try:
            rationale = decision.get('rationale')
            if rationale:
                logger.debug(f"NPCBrain decision: {action} ({rationale})")
        except Exception:
            pass

        return action

    async def check_victory_conditions(self):
        """Check if battle is over and handle rewards"""
        if self.battle_over:
            return

        # Sync alive flag with hp for all players
        for data in self.player_data.values():
            if data['hp'] <= 0:
                data['alive'] = False

        # Check for victory against monster
        if self.monster and self.monster_hp <= 0:
            self.battle_over = True
            await self.handle_victory()

        # Check for defeat against monster (all players dead)
        elif self.monster and not any(data['alive'] for data in self.player_data.values()):
            self.battle_over = True
            await self.handle_defeat()

        # PvP: only one player left alive
        elif not self.monster:
            alive_count = sum(1 for data in self.player_data.values() if data['alive'])
            if alive_count <= 1:
                self.battle_over = True
                await self.handle_victory()

    def _get_roll_multiplier_from_result(self, result_type: str, roll: int) -> float:
        """Convert attack result type to roll multiplier for display purposes"""
        if result_type == "miss":
            return 0.0
        elif result_type == "base":
            return 1.0
        elif result_type == "low_mult":
            return roll / 3.0
        elif result_type == "mid_mult":
            return (2 * roll) / 3.0
        elif result_type == "high_mult":
            return float(roll)
        else:
            return 1.0  # Fallback

    # Loot system removed

    async def handle_victory(self):
        """Handle battle victory and rewards using LootCalculator"""
        if hasattr(self, 'battle_complete') and not self.battle_complete.done():
            self.battle_complete.set_result(True)
        try:
            if self.wild_encounter:
                logger.info(f"Wild encounter victory for {[p[0].id for p in self.participants]}. No rewards.")
                for user_id, data in self.player_data.items():
                    if data['alive'] and data['hp'] > 0:
                        await user_data_manager.update_pet_battle_stats(
                            str(user_id),
                            "wild_encounter",
                            wins=1,
                            xp_earned=0,
                            damage_dealt=int(self.total_damage_dealt.get(user_id, 0)),
                            damage_taken=int(self.total_damage_received.get(user_id, 0))
                        )
                return

            if self.is_boss_battle:
                logger.info(f"Boss battle victory for {[p[0].id for p in self.participants]}.")
                for user_id, data in self.player_data.items():
                    if data['alive'] and data['hp'] > 0:
                        pet = data['pet']
                        xp_gain, items = LootCalculator.calculate_boss_loot(pet.get('level', 1))

                        # Apply XP
                        has_level_changed, change_data = await LootCalculator.apply_xp_change(user_id, xp_gain, "boss_battle")

                        # Add items
                        loot_messages = []
                        for item in items:
                            added, msg = await LootCalculator.add_item_to_inventory(user_id, item, pet)
                            if msg:
                                loot_messages.append(msg)

                        # Update battle stats
                        await user_data_manager.update_pet_battle_stats(
                            str(user_id),
                            "boss",
                            wins=1,
                            xp_earned=xp_gain,
                            damage_dealt=int(self.total_damage_dealt.get(user_id, 0)),
                            damage_taken=int(self.total_damage_received.get(user_id, 0))
                        )

                        # Store loot info for the final embed
                        data['loot_text'] = "\n" + "\n".join(loot_messages)
                        if has_level_changed and change_data:
                            if change_data.get("new_level", 0) > change_data.get("old_level", 0):
                                data['loot_text'] += f"\n↗️ Leveled up to {change_data.get('new_level')}!"

                return

            self.rewards = {'type': 'victory', 'survivors': []}
            
            for user_id, data in self.player_data.items():
                if data['alive'] and data['hp'] > 0:
                    pet = data['pet']
                    dealt = int(self.total_damage_dealt.get(user_id, 0))
                    taken = int(self.total_damage_received.get(user_id, 0))
                    
                    # Use unified LootCalculator
                    loot_result = await LootCalculator.calculate_loot(
                        user_id=int(user_id),
                        pet_data=pet,
                        source="npc_battle",
                        difficulty=self.difficulty,
                        winner_level=int(pet.get('level', 1)),
                        is_winner=True
                    )
                    
                    # Update Stats
                    await user_data_manager.update_pet_battle_stats(
                        str(user_id),
                        "npc",
                        wins=1,
                        xp_earned=loot_result['xp_gained'],
                        damage_dealt=dealt,
                        damage_taken=taken
                    )
                    
                    # Store info for final embed
                    loot_lines = loot_result['messages']
                    data['loot_text'] = "\n" + "\n".join(loot_lines)
                    
                    self.rewards['survivors'].append({
                        'user': data['user'], 
                        'reward': loot_result['xp_gained'], 
                        'pet_name': pet['name']
                    })
                    
                    # Send Level Up/Down Embeds if present
                    if loot_result.get('level_up_embed'):
                        try:
                            await self.ctx.channel.send(embed=loot_result['level_up_embed'])
                        except Exception as e:
                            logger.error(f"Error sending level up embed: {e}")
                    if loot_result.get('level_down_embed'):
                        try:
                            await self.ctx.channel.send(embed=loot_result['level_down_embed'])
                        except Exception as e:
                            logger.error(f"Error sending level down embed: {e}")
                        
        except Exception as e:
            logger.error(f"Error handling victory: {e}")

    async def handle_defeat(self):
        """Handle battle defeat using LootCalculator"""
        if hasattr(self, 'battle_complete') and not self.battle_complete.done():
            self.battle_complete.set_result(False)
        try:
            if self.wild_encounter:
                logger.info(f"Wild encounter defeat for {[p[0].id for p in self.participants]}.")
                for user_id, data in self.player_data.items():
                    await user_data_manager.update_pet_battle_stats(
                        str(user_id),
                        "wild_encounter",
                        losses=1,
                        xp_earned=0,
                        damage_dealt=int(self.total_damage_dealt.get(user_id, 0)),
                        damage_taken=int(self.total_damage_received.get(user_id, 0))
                    )
                return

            for user_id, data in self.player_data.items():
                pet = data['pet']
                dealt = int(self.total_damage_dealt.get(user_id, 0))
                taken = int(self.total_damage_received.get(user_id, 0))
                
                loot_result = await LootCalculator.calculate_loot(
                    user_id=int(user_id),
                    pet_data=pet,
                    source="npc_battle",
                    difficulty=self.difficulty,
                    winner_level=int(pet.get('level', 1)),
                    is_winner=False
                )
                
                await user_data_manager.update_pet_battle_stats(
                    str(user_id), 
                    "npc", 
                    losses=1, 
                    xp_earned=loot_result['xp_gained'],
                    damage_dealt=dealt,
                    damage_taken=taken
                )
                
                # Send Level Up/Down Embeds if present
                if loot_result.get('level_up_embed'):
                    try:
                        await self.ctx.channel.send(embed=loot_result['level_up_embed'])
                    except Exception as e:
                        logger.error(f"Error sending level up embed: {e}")
                if loot_result.get('level_down_embed'):
                    try:
                        await self.ctx.channel.send(embed=loot_result['level_down_embed'])
                    except Exception as e:
                        logger.error(f"Error sending level down embed: {e}")

        except Exception as e:
            logger.error(f"Error handling defeat: {e}")

class EphemeralActionView(discord.ui.View):
    """
    Ephemeral action view for individual players.

    Row 0: Attack | Defend | Charge  (always present)
    Row 1+: One button per equipped skill slot (1 always shown, up to 4 total).
            Each button shows the skill name and its per-slot cooldown status.
            Pressing a skill button immediately queues that skill as the full action
            and disables all buttons — skills count as the complete action for the round.

    Skill buttons are disabled (greyed out with cooldown shown) when that slot's cooldown > 0.
    """

    def __init__(self, battle_view: UnifiedBattleView, user_id: int):
        super().__init__(timeout=300)
        self.battle_view = battle_view
        self.user_id = user_id

        try:
            pdata = self.battle_view.player_data.get(user_id, {})
            pet = pdata.get('pet', {})
            ptype = str(pet.get('category', '')).lower()
            pelem = str(pet.get('element', '')).lower()
            custom_labels = pet.get('action_labels', {})

            default_labels = DamageCalculator.get_action_labels(ptype, pelem)
            labels = {
                'attack': custom_labels.get('attack') or default_labels.get('attack', 'Attack'),
                'defend': custom_labels.get('defense') or custom_labels.get('defend') or default_labels.get('defend', 'Defend'),
                'charge': custom_labels.get('charge') or default_labels.get('charge', 'Charge'),
            }

            # Row 0: core action buttons
            self.attack_button.label = labels['attack']
            self.attack_button.style = discord.ButtonStyle.danger
            atk_emoji_id = emoji_mod.id_for('Attack')
            if atk_emoji_id:
                self.attack_button.emoji = discord.PartialEmoji(name='Attack', id=atk_emoji_id)

            self.defend_button.label = labels['defend']
            self.defend_button.style = discord.ButtonStyle.primary
            def_emoji_id = emoji_mod.id_for('Defend')
            if def_emoji_id:
                self.defend_button.emoji = discord.PartialEmoji(name='Defend', id=def_emoji_id)

            current_charge = 1
            try:
                current_charge = int(pdata.get('charge_multiplier', 1))
            except Exception:
                current_charge = 1
            self.charge_button.label = f"{labels['charge']} x{current_charge}"
            self.charge_button.style = discord.ButtonStyle.success
            chg_emoji_id = emoji_mod.id_for('Charge')
            if chg_emoji_id:
                self.charge_button.emoji = discord.PartialEmoji(name='Charge', id=chg_emoji_id)

            # Row 1+: one button per equipped skill slot
            try:
                from Systems.Pets.Logic.battle_skills import SKILL_BY_ID, get_slot_cooldown
                equipped = pdata.get('equipped_skills', [])
                cooldowns = pdata.get('skill_cooldowns', {})

                for slot_idx, skill_id in enumerate(equipped):
                    sk = SKILL_BY_ID.get(skill_id)
                    if not sk:
                        continue
                    cd = cooldowns.get(slot_idx, 0)
                    ready = (cd == 0)
                    label = sk['name'][:20]
                    if not ready:
                        label = f"{label} ({cd}t)"
                    # Rows 1-4 for skill slots (Discord max 5 rows total)
                    btn_row = min(1 + slot_idx, 4)
                    btn = discord.ui.Button(
                        label=label,
                        style=discord.ButtonStyle.secondary,
                        emoji="✨" if ready else "⏳",
                        disabled=not ready,
                        row=btn_row,
                        custom_id=f"skill_{slot_idx}_{skill_id}",
                    )

                    def make_skill_callback(sidx: int, skid: str):
                        async def skill_callback(interaction: discord.Interaction):
                            await self.handle_skill_selection(interaction, sidx, skid)
                        return skill_callback

                    btn.callback = make_skill_callback(slot_idx, skill_id)
                    self.add_item(btn)
            except Exception as _se:
                logger.debug(f"Skill button build error: {_se}")

        except Exception:
            pass

    @discord.ui.button(style=discord.ButtonStyle.red, row=0)
    async def attack_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action_selection(interaction, "attack")

    @discord.ui.button(style=discord.ButtonStyle.blurple, row=0)
    async def defend_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action_selection(interaction, "defend")

    @discord.ui.button(style=discord.ButtonStyle.green, row=0)
    async def charge_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action_selection(interaction, "charge")

    async def handle_skill_selection(self, interaction: discord.Interaction, slot_index: int, skill_id: str):
        """Handle a skill button press — queues the skill as the player's full action for this round."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your action menu!", ephemeral=True, delete_after=3)
            return

        pdata = self.battle_view.player_data.get(self.user_id, {})

        # Re-check cooldown in case the button state was stale
        try:
            from Systems.Pets.Logic.battle_skills import can_use_skill, SKILL_BY_ID
            if not can_use_skill(pdata, slot_index):
                cd = pdata.get('skill_cooldowns', {}).get(slot_index, 0)
                await interaction.response.send_message(
                    f"That skill is on cooldown — {cd} turn(s) remaining.", ephemeral=True, delete_after=5
                )
                return
            sk = SKILL_BY_ID.get(skill_id)
            skill_name = sk['name'] if sk else skill_id
        except Exception:
            skill_name = skill_id

        # Queue skill as the full action — no other action can be taken this round
        self.battle_view.player_actions[self.user_id] = {
            'action': 'skill',
            'skill_id': skill_id,
            'slot_index': slot_index,
            'target': None,
            'action_label': f"Skill: {skill_name}",
        }

        # Disable ALL buttons — skill is the complete action for this round
        try:
            for item in self.children:
                if hasattr(item, 'disabled'):
                    item.disabled = True
            await interaction.response.edit_message(
                content=f"✨ **{skill_name}** queued!", view=self
            )
        except Exception as e:
            logger.debug(f"Error disabling skill buttons: {e}")
            try:
                await interaction.response.defer()
            except Exception:
                pass

        await self.battle_view.check_all_actions_submitted()

    async def handle_action_selection(self, interaction: discord.Interaction, action: str):
        """Handle attack/defend/charge selection."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your action menu!", ephemeral=True, delete_after=3)
            return

        button_label = ''
        if action == 'attack':
            button_label = self.attack_button.label or ""
        elif action == 'defend':
            button_label = self.defend_button.label or ""
        elif action == 'charge':
            button_label = self.charge_button.label or ""

        self.battle_view.player_actions[self.user_id] = {
            'action': action,
            'target': None,
            'action_label': button_label
        }
        # Disable ALL buttons — action is locked in for this round
        try:
            for item in self.children:
                if hasattr(item, 'disabled'):
                    item.disabled = True
            await interaction.response.edit_message(view=self)
        except Exception as e:
            logger.debug(f"Error editing ephemeral action message: {e}")

        await self.battle_view.check_all_actions_submitted()

class BattleSystem:
    """Battle system class for managing battles"""
    
    def __init__(self):
        self.active_battles = {}
        
    async def create_battle(self, ctx, battle_type: str, **kwargs) -> UnifiedBattleView:
        """Create a new battle"""
        # Handle PvE battles only (PvP removed)
        battle = await UnifiedBattleView.create_async(ctx, battle_type, **kwargs)
        self.active_battles[ctx.channel.id] = battle
        return battle
        
    def get_battle(self, channel_id: int) -> Optional[UnifiedBattleView]:
        """Get active battle for channel"""
        return self.active_battles.get(channel_id)
        
    def end_battle(self, channel_id: int):
        """End battle for channel"""
        self.active_battles.pop(channel_id, None)

# Global battle system instance
battle_system = BattleSystem()

# Export classes for use in other modules
__all__ = [
    'UnifiedBattleView',
    'BattleSystem',
    'battle_system'
]
