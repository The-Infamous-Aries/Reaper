import discord
import random
import asyncio
import logging
import json
from typing import Dict, List, Optional, Set, Tuple, Any, Union, TypedDict, cast
from enum import Enum, auto
from collections import defaultdict
from Systems.Functions.user_data_manager import user_data_manager
from Systems.Functions.pets_db import pets_db
from Systems.Pets.pets_system import add_experience
from Systems.Pets.Logic.pet_brain import DamageCalculator, LootCalculator, StatsCalculator, NPCBrain
from Systems.Functions import emoji as emoji_mod

logger = logging.getLogger('pvp_system')

# ── Relationship System ────────────────────────────────────────────────────────
async def get_relationship_multipliers(user1_id: str, user2_id: str) -> Tuple[float, float]:
    """
    Get damage multipliers based on mutual relationship between two users.
    Returns (user1_damage_multiplier, user2_damage_multiplier)
    
    Relationship effects:
    - Best Friends: Cannot battle each other (should be blocked before this)
    - Friends: Both do 0.8x damage to each other
    - Foe: Both do 1.2x damage to each other  
    - Enemy: Both do 1.5x damage to each other
    - Neutral/Mixed: 1.0x damage (no effect)
    """
    try:
        user1_to_user2, user2_to_user1 = await pets_db.get_mutual_relationship(user1_id, user2_id)
        
        # If either user considers the other a best friend, they cannot battle
        if user1_to_user2 == 'best_friend' or user2_to_user1 == 'best_friend':
            return (0.0, 0.0)  # This should be caught earlier, but safety check
        
        # Determine effective relationship (both must agree for effect)
        effective_relationship = None
        if user1_to_user2 == user2_to_user1 and user1_to_user2 is not None:
            effective_relationship = user1_to_user2
        
        # Apply multipliers based on effective relationship
        if effective_relationship == 'friend':
            return (0.8, 0.8)  # Both do less damage
        elif effective_relationship == 'foe':
            return (1.2, 1.2)  # Both do more damage
        elif effective_relationship == 'enemy':
            return (1.5, 1.5)  # Both do much more damage
        else:
            return (1.0, 1.0)  # Neutral or mixed relationships
            
    except Exception as e:
        logger.error(f"Error getting relationship multipliers: {e}")
        return (1.0, 1.0)  # Default to neutral on error

async def can_battle_pvp(user1_id: str, user2_id: str) -> Tuple[bool, str]:
    """
    Check if two users can battle each other based on their relationship.
    Returns (can_battle, reason_if_not)
    """
    try:
        user1_to_user2, user2_to_user1 = await pets_db.get_mutual_relationship(user1_id, user2_id)
        
        # Best friends cannot battle each other
        if user1_to_user2 == 'best_friend' or user2_to_user1 == 'best_friend':
            return (False, "Best friends cannot battle each other!")
        
        return (True, "")
        
    except Exception as e:
        logger.error(f"Error checking battle eligibility: {e}")
        return (True, "")  # Default to allowing battle on error

async def get_boss_battle_multipliers(participants: List[str]) -> Dict[str, float]:
    """
    Get damage multipliers for boss battles based on relationships.
    
    Best Friends: +25% damage when fighting together
    Friends: +10% damage when fighting together  
    Foes: -15% damage when fighting together
    Enemies: Cannot participate in boss battles together
    """
    multipliers = {user_id: 1.0 for user_id in participants}
    
    try:
        # Check all pairs of participants
        for i, user1_id in enumerate(participants):
            for user2_id in participants[i+1:]:
                user1_to_user2, user2_to_user1 = await pets_db.get_mutual_relationship(user1_id, user2_id)
                
                # If anyone considers anyone else an enemy, block the battle
                if user1_to_user2 == 'enemy' or user2_to_user1 == 'enemy':
                    return {}  # Empty dict indicates battle blocked
                
                # Apply positive multipliers for mutual positive relationships
                effective_relationship = None
                if user1_to_user2 == user2_to_user1 and user1_to_user2 is not None:
                    effective_relationship = user1_to_user2
                
                if effective_relationship == 'best_friend':
                    multipliers[user1_id] = max(multipliers[user1_id], 1.25)
                    multipliers[user2_id] = max(multipliers[user2_id], 1.25)
                elif effective_relationship == 'friend':
                    multipliers[user1_id] = max(multipliers[user1_id], 1.10)
                    multipliers[user2_id] = max(multipliers[user2_id], 1.10)
                elif effective_relationship == 'foe':
                    multipliers[user1_id] = min(multipliers[user1_id], 0.85)
                    multipliers[user2_id] = min(multipliers[user2_id], 0.85)
        
        return multipliers
        
    except Exception as e:
        logger.error(f"Error getting boss battle multipliers: {e}")
        return {user_id: 1.0 for user_id in participants}  # Default to neutral on error

async def can_battle_boss_together(participants: List[str]) -> Tuple[bool, str]:
    """
    Check if users can participate in a boss battle together.
    Returns (can_battle, reason_if_not)
    """
    try:
        # Check all pairs for enemy relationships
        for i, user1_id in enumerate(participants):
            for user2_id in participants[i+1:]:
                user1_to_user2, user2_to_user1 = await pets_db.get_mutual_relationship(user1_id, user2_id)
                
                if user1_to_user2 == 'enemy' or user2_to_user1 == 'enemy':
                    return (False, "Enemies cannot fight boss battles together!")
        
        return (True, "")
        
    except Exception as e:
        logger.error(f"Error checking boss battle eligibility: {e}")
        return (True, "")  # Default to allowing battle on error

class PlayerInfoType(TypedDict, total=False):
    effective_multiplier: float
    charge_multiplier_used: float
    action_label: str
    protected_id: str
    parry_damage: int
    parry_taken: Optional[int]
    roll: Optional[int]
    result: str
    defense_effectiveness: Optional[float]
    charge_multiplier: float
    target_id: str
    damage: int

class PlayerDataType(TypedDict, total=False):
    user: discord.Member
    team_id: str
    hp: int
    max_hp: int
    attack: int
    defense: int

    charging: bool
    pet: Optional[Dict[str, Any]]
    alive: bool
    xp_earned: int
    damage_dealt: int
    damage_taken: int
    kills: int
    assists: int
    last_action: Optional[str]
    last_action_info: PlayerInfoType
    base_defense: int
    charge: Optional[float]

class BattleMode(Enum):
    ONE_VS_ONE = auto()
    FREE_FOR_ALL = auto()


def _pvp_effective_atk(player_data: dict) -> int:
    """Return the player's effective ATK including active skill stat_buff multipliers."""
    base = int(player_data.get('total_attack', player_data.get('attack', 10)))
    try:
        from Systems.Pets.Logic.battle_skills import get_atk_multiplier
        mult = get_atk_multiplier(player_data)
        return max(1, int(base * mult))
    except Exception:
        return base


def _pvp_effective_def(player_data: dict) -> int:
    """Return the player's effective DEF including active skill stat_buff multipliers."""
    base = int(player_data.get('total_defense', player_data.get('defense', 5)))
    try:
        from Systems.Pets.Logic.battle_skills import get_def_multiplier
        mult = get_def_multiplier(player_data)
        return max(1, int(base * mult))
    except Exception:
        return base
class PvPBattleView(discord.ui.View):
    """View for PvP battles between players"""
    
    _cached_team_names = None
    
    def __init__(self, ctx, participants: Union[List[discord.Member], Dict[str, List[discord.Member]]], 
                 battle_mode: BattleMode = BattleMode.ONE_VS_ONE, team_names: Optional[Dict[str, str]] = None, 
                 npc_player_ids: Optional[List[str]] = None):
        """
        Initialize a PvP battle view
        
        Args:
            ctx: The command context
            participants: Either a list of members (for FFA) or a dict with 'team_a' and 'team_b' keys
            battle_mode: The type of battle (1v1 or FFA)
            team_names: Optional dict mapping team IDs to team names (from lobby)
        """
        super().__init__(timeout=None)
        self.ctx = ctx
        self.battle_mode = battle_mode
        self.action_messages: Dict[str, discord.Message] = {}  # Store ephemeral action messages for cleanup
        self.npc_player_ids = set(npc_player_ids) if npc_player_ids else set()
        
        # Initialize participants based on battle mode (1v1 or FFA only)
        if battle_mode == BattleMode.FREE_FOR_ALL:
            self.teams = {str(i): [member] for i, member in enumerate(cast(List[discord.Member], participants)[:10])}
            self.team_names = {str(i): f"Player {i+1}" for i in range(len(self.teams))}
        else:
            # ONE_VS_ONE: expect list of two members
            p = participants if isinstance(participants, list) else list(participants.values())[0]
            self.teams = {"a": [p[0]], "b": [p[1]]}
            self.team_names = {"a": "Challenger A", "b": "Challenger B"}
        
        # Initialize player data
        self.players: Dict[str, PlayerDataType] = {}
        self.team_assignments = {}
        self.join_order_ids = []
        
        for team_id, members in self.teams.items():
            for member in members:
                member_id = str(member.id)
                self.join_order_ids.append(member_id)
                self.players[member_id] = {
                    'user': member,
                    'team_id': team_id,
                    'hp': 100, 'max_hp': 100,
                    'attack': 10, 'defense': 5,
                    'charge': 1.0, 'charging': False,
                    'pet': None, 'alive': True,
                    'xp_earned': 0, 'damage_dealt': 0,
                    'damage_taken': 0, 'kills': 0, 'assists': 0,
                    # Last action tracking for UI parity with battle_system
                    'last_action': None,
                    'last_action_info': {}
                }
                self.team_assignments[member_id] = team_id
        
        # Team visuals removed for simplified PvP (FFA/1v1)
        
        # Initialize battle state
        self.message = None
        self.turn_count = 0
        self.battle_over = False
        self.battle_log: List[str] = []
        self.defending_players: Set[str] = set()
        self.guard_relationships: Dict[str, str] = {}
        self.player_actions: Dict[str, Dict[str, Any]] = {}
        self.waiting_for_actions = False
        self.death_log: List[str] = []
        self.turn_order: List[str] = []
        self.npc_brain = NPCBrain()
        self.round_history: List[Dict[str, Any]] = []
        
        # Start battle initialization
        asyncio.create_task(self.initialize_battle_data())

    def _get_roll_multiplier_from_result(self, result_type: str, roll: int) -> float:
        """Convert attack/defense result type to roll multiplier for display purposes
        Mirrored from battle_system.py for UI consistency."""
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
            return 1.0
    
    # Team helpers removed (FFA/1v1 only)
    
    async def initialize_battle_data(self):
        """Initialize pet data for all participants"""
        try:
            # Check relationships before starting battle
            player_ids = list(self.players.keys())
            
            # For 1v1 battles, check if players can battle each other
            if self.battle_mode == BattleMode.ONE_VS_ONE and len(player_ids) == 2:
                can_battle, reason = await can_battle_pvp(player_ids[0], player_ids[1])
                if not can_battle:
                    if self.message:
                        error_emoji = emoji_mod.mention('No') or "❌"
                        await self.message.edit(content=f"{error_emoji} {reason}", view=None)
                    return
            
            # For FFA battles, check all pairs (though best friends can still participate in FFA)
            elif self.battle_mode == BattleMode.FREE_FOR_ALL:
                blocked_pairs = []
                for i, player1_id in enumerate(player_ids):
                    for player2_id in player_ids[i+1:]:
                        can_battle, reason = await can_battle_pvp(player1_id, player2_id)
                        if not can_battle:
                            # In FFA, we just note the relationship but don't block the battle
                            # Best friends will just do 0 damage to each other
                            blocked_pairs.append((player1_id, player2_id))
                
                if blocked_pairs:
                    # Add a note about relationship effects
                    relationship_note = "⚠️ Some players have relationship restrictions that will affect damage."
                    if hasattr(self, 'battle_log'):
                        self.battle_log.append(relationship_note)
            
            tasks = []
            for player_id, player in self.players.items():
                tasks.append(self._load_pet_data(player_id, player))
            
            # Wait for all pet data to load
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Set up turn order to follow lobby join order
            self.turn_order = [self.players[pid] for pid in self.join_order_ids if self.players.get(pid, {}).get('alive')]
            
            await self.start_battle()
        except Exception as e:
            logger.error(f"Battle init error: {e}", exc_info=True)
            if self.message:
                error_emoji = emoji_mod.mention('No') or "❌"
                await self.message.edit(content=f"{error_emoji} Error: {str(e)}", view=None)

    async def _load_pet_data(self, player_id: str, player_data: dict):
        """Load pet data for a single player"""
        try:
            username = player_data.get('user', {}).display_name if player_data.get('user') else None
            user_data = await user_data_manager.get_user_data(str(player_id), username)
            if user_data and 'active_pet' in user_data and user_data['active_pet']:
                pet = user_data['pets'][str(user_data['active_pet'])]
                
                # Use StatsCalculator for comprehensive stats (includes equipment)
                stats = StatsCalculator.calculate_pet_stats(pet)
                att = stats['ATT']
                dex = stats['DEX']
                deff = stats['DEF']
                intel = stats['INT']
                hap = stats['HAP']
                ene = stats['ENE']
                
                base_attack = pet.get('attack', att * dex if att and dex else 10)
                base_defense = pet.get('defense', deff * intel if deff and intel else 5)
                
                level = int(pet.get('level', 1))
                max_hp = pet.get('max_health', StatsCalculator.calculate_max_health(pet))
                current_hp = int(pet.get('health', max_hp))
                
                total_attack = base_attack
                total_defense = base_defense
                
                player_data.update({
                    'pet': pet,
                    'hp': current_hp,
                    'max_hp': max_hp,
                    'attack': total_attack,
                    'defense': total_defense,
                    'type': str(pet.get('category','')).lower(),
                    'element': str(pet.get('element','')).lower(),
                    'element2': str(pet.get('element2','')).lower() if pet.get('element2') else None
                })
                # Initialise battle skill state
                try:
                    from Systems.Pets.Logic.battle_skills import init_battle_skill_state
                    init_battle_skill_state(player_data)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Error loading pet data for {player_id}: {e}")
    
    async def _process_pvp_skill(self, player_id: str, action_data: dict):
        """Apply a battle skill in PvP context."""
        skill_id = action_data.get('skill_id', '')
        pdata = self.players.get(player_id)
        if not pdata:
            return
        try:
            from Systems.Pets.Logic.battle_skills import apply_skill, get_atk_multiplier
            # In PvP, target is the first alive enemy
            target_data = None
            my_team = self.team_assignments.get(player_id)
            for pid, pd in self.players.items():
                if pid != player_id and pd.get('alive') and self.team_assignments.get(pid) != my_team:
                    target_data = pd
                    break
            slot_index = action_data.get('slot_index', 0)
            skill_result = apply_skill(skill_id, pdata, target_data, battle_type="pvp", slot_index=slot_index)
            if skill_result['ok']:
                if skill_result['hp_delta_user'] != 0:
                    pdata['hp'] = max(0, min(pdata['max_hp'], pdata['hp'] + skill_result['hp_delta_user']))
                if skill_result['hp_delta_target'] != 0 and target_data:
                    target_data['hp'] = max(0, min(target_data['max_hp'],
                                                   target_data['hp'] + skill_result['hp_delta_target']))
                self.battle_log.append(f"✨ {pdata['user'].display_name}: {skill_result['message']}")
            pdata['last_action'] = 'skill'
            pdata['last_action_info'] = {
                'type': 'skill',
                'skill_name': skill_result.get('skill_name', '?'),
                'message': skill_result.get('message', ''),
            }
        except Exception as e:
            logger.error(f"PvP skill error: {e}")

    async def start_battle(self):
        battle_emoji = emoji_mod.mention('Casino') or "⚔️"
        embed = self.build_battle_embed(f"{battle_emoji} Battle starting!")
        self.message = await self.ctx.send(embed=embed)
        await self.start_turn()
    
    async def start_turn(self):
        """Start a new turn in the battle"""
        self.turn_count += 1
        self.waiting_for_actions = True
        self.player_actions = {}
        self.defending_players = set()
        self.guard_relationships = {}
        
        # Reset charge for players who didn't use it
        for player_id, player in self.players.items():
            if player['alive'] and player_id not in self.player_actions:
                player['charge'] = 1.0
        
        # Notify players about the new round
        refresh_emoji = emoji_mod.mention('Refresh') or "🔄"
        embed = self.build_battle_embed(f"{refresh_emoji} Round {self.turn_count} - Select your actions!")
        await self.message.edit(embed=embed)
        
        # Start action collection
        await self.start_action_collection()
    
    async def start_action_collection(self):
        """Start collecting actions from all alive players"""
        self.waiting_for_actions = True
        
        tasks = []

        # Helper to handle sending/editing for a single player
        async def send_player_prompt(player_id, player, is_ffa):
            if not player['alive']:
                return

            # Check if this player is an NPC
            if player_id in self.npc_player_ids:
                # Construct monster_state for the NPCBrain
                # Use pet data for type and element
                pet_data = player.get('pet', {})
                npc_state = {
                    'name': player['user'].display_name,
                    'health': player['hp'],
                    'max_health': player['max_hp'],
                    'attack': player['attack'],
                    'defense': player['defense'],
                    'charge_multiplier': player['charge'],
                    'type': str(pet_data.get('category', '')).lower(),
                    'element': str(pet_data.get('element', '')).lower(),
                    'species': pet_data.get('species'),
                    # Assuming 'is_defending' or similar will be handled in process_combat_interactions
                    'is_defending': False
                }

                # Construct players_state (other alive players)
                players_state = []
                for pid, pdata in self.players.items():
                    if pid != player_id and pdata['alive']:
                        other_pet_data = pdata.get('pet', {})
                        players_state.append({
                            'id': pid,
                            'name': pdata['user'].display_name,
                            'health': pdata['hp'],
                            'max_health': pdata['max_hp'],
                            'attack': pdata['attack'],
                            'defense': pdata['defense'],
                            'charge_multiplier': pdata['charge'],
                            'type': str(other_pet_data.get('category', '')).lower(),
                            'element': str(other_pet_data.get('element', '')).lower(),
                            'species': other_pet_data.get('species'),
                            'is_defending': pdata.get('defending', False)
                        })

                # NPC decides action
                decision = self.npc_brain.decide_action(npc_state, players_state)
                npc_action = decision.get('action')
                npc_target_id = decision.get('target_id')

                # Store NPC's action
                self.player_actions[player_id] = {
                    'action': npc_action,
                    'target': npc_target_id
                }
                logger.info(f"NPC {player['user'].display_name} decided to {npc_action} against {npc_target_id or 'no one'}.")
                return # Skip sending ephemeral message for NPC

            try:
                enemies = {}
                if is_ffa:
                     # For FFA, enemies are all other alive players
                    enemies = {
                        pid: p for pid, p in self.players.items() 
                        if p['alive'] and pid != player_id
                    }
                else:
                    # 1v1 logic (find enemies in other teams)
                    my_team = self.team_assignments.get(player_id)
                    enemies = {
                        pid: p for pid, p in self.players.items() 
                        if pid != player_id and p['alive'] and self.team_assignments.get(pid) != my_team
                    }

                view = PvPActionView(self, player_id, enemies, is_ffa=is_ffa)
                
                battle_emoji = emoji_mod.mention('Casino') or "⚔️"
                desc = f"{player['user'].mention} it\'s your turn to act! (FFA)" if is_ffa else f"{player['user'].mention} it\'s your turn to act!"
                embed = discord.Embed(
                    title=f"{battle_emoji} PvP Battle Action Required",
                    description=desc,
                    color=0x00ff00
                )

                # Show this player's last action details
                pdata = self.players.get(player_id, {})
                la = pdata.get('last_action')
                info = pdata.get('last_action_info', {})
                if la:
                    if la == 'attack':
                        tgt = cast(PlayerDataType, self.players.get(cast(str, info.get('target_id', '')))).get('user', None)
                        tgt_name = tgt.display_name if tgt else 'Unknown'
                        dmg = info.get('damage')
                        roll = info.get('roll')
                        res = info.get('result')
                        eff = info.get('effective_multiplier')
                        cm = info.get('charge_multiplier_used')
                        atk_emoji = emoji_mod.mention('Attack') or "⚔️"
                        text = f"{atk_emoji} You attacked {tgt_name} for {dmg} • roll {roll} {res} x{eff:.1f}"
                        if cm and cm != 1.0:
                            text += f" • {emoji_mod.mention('Charge') or '⚡'}x{cm:.1f}"
                        embed.add_field(name="Last Action", value=text, inline=False)
                    elif la == 'defend':
                        prot = cast(PlayerDataType, self.players.get(cast(str, info.get('protected_id', '')))).get('user', None)
                        prot_name = prot.display_name if prot else ('yourself' if info.get('protected_id') == player_id else 'Unknown')
                        parry = info.get('parry_damage', 0)
                        roll = info.get('roll')
                        res = info.get('result')
                        eff = info.get('defense_effectiveness')
                        eff_text = f" x{eff:.1f}" if isinstance(eff, (int, float)) else ""
                        def_emoji = emoji_mod.mention('Defend') or "🛡️"
                        text = f"{def_emoji} You defended {prot_name} • parry {parry} • roll {roll} {res}{eff_text}"
                        embed.add_field(name="Last Action", value=text, inline=False)
                    elif la == 'charge':
                        cm = info.get('charge_multiplier')
                        charge_emoji = emoji_mod.mention('Charge') or "⚡"
                        text = f"{charge_emoji} You charged to x{cm:.1f}"
                        embed.add_field(name="Last Action", value=text, inline=False)

                # Check if we have an existing ephemeral message for this user
                if player_id in self.action_messages:
                    try:
                        # Try to edit the existing message
                        await self.action_messages[player_id].edit(embed=embed, view=view)
                        return
                    except discord.NotFound:
                        # Message was deleted, remove from cache and create new one
                        del self.action_messages[player_id]
                    except Exception as e:
                        logger.debug(f"Error editing existing ephemeral message for user {player_id}: {e}")
                        # Fall through to create new message

                # Send new ephemeral message and store reference
                # PvP uses ctx.send (not interaction followup) because it might be started from a command
                # But to be truly ephemeral/non-spammy, we try to use the stored message or a new one
                msg = await self.ctx.send(
                    embed=embed,
                    view=view,
                    delete_after=60,
                    ephemeral=True
                )
                self.action_messages[player_id] = msg
            except Exception as e:
                logger.error(f"Error sending action view to {player_id}: {e}")
                # Fallback to DM if ephemeral message fails
                try:
                    await player['user'].send("Failed to send action buttons in channel. Please enable DMs from server members.")
                    await player['user'].send("⚔️ Your turn to act!", view=view)
                except Exception:
                    pass

        # For FFA, everyone is an enemy
        if self.battle_mode == BattleMode.FREE_FOR_ALL:
            for player_id, player in self.players.items():
                tasks.append(send_player_prompt(player_id, player, True))
        else:
            # 1v1
            for team_id, members in self.teams.items():
                for member in members:
                    member_id = str(member.id)
                    if self.players.get(member_id, {}).get('alive'):
                        tasks.append(send_player_prompt(member_id, self.players[member_id], False))
        
        if tasks:
            await asyncio.gather(*tasks)
        
        embed = self.build_battle_embed("⚔️ Players are choosing actions...")
        await self.message.edit(embed=embed)
        asyncio.create_task(self.check_all_actions_ready())
    
    async def check_all_actions_ready(self):
        """Check if all players have submitted their actions"""
        alive_players = [p_id for p_id, p in self.players.items() if p['alive']]
        if all(p_id in self.player_actions for p_id in alive_players):
            self.waiting_for_actions = False
            
            # Show selected actions summary
            action_summary = []
            for player_id, action_data in self.player_actions.items():
                player = self.players[player_id]
                target = self.players.get(action_data.get('target', ''), {})
                action_text = f"{player['user'].display_name} "
                
                if action_data['action'] == 'attack':
                    action_text += f"attacks {target.get('user', 'Unknown').display_name if target else 'nothing'}"
                elif action_data['action'] == 'defend':
                    target_name = target.get('user', 'themselves').display_name if target else 'themselves'
                    target_name = target_name if target_name != player['user'].display_name else 'themselves'
                    action_text += f"defends {target_name}"
                elif action_data['action'] == 'charge':
                    action_text += "charges up a powerful attack"
                
                action_summary.append(action_text)
            
            # Update battle message with actions summary
            embed = self.build_battle_embed("🎬 Processing round actions...")
            summary = "\n".join(f"• {action}" for action in action_summary)
            embed.add_field(name="Selected Actions", value=summary, inline=False)
            await self.message.edit(embed=embed)
            
            # Small delay to let players see the actions
            await asyncio.sleep(2)
            
            # Process the turn
            await self.process_turn()
    
    async def process_turn(self):
        """Process all actions for the current turn with new mechanics"""
        alive_players = [p_id for p_id, p in self.players.items() if p['alive']]

        # ── Tick active skill effects for all alive players ───────────────────
        # Check stun BEFORE tick so a stun with turns_left=1 fires correctly.
        # tick_battle_effects decrements turns_left and removes expired effects,
        # so checking after tick would miss a stun on its last turn.
        skill_tick_lines: list = []
        try:
            from Systems.Pets.Logic.battle_skills import tick_battle_effects, is_stunned, consume_stun
            for pid in alive_players:
                pdata = self.players[pid]
                # 1. Check and consume stun FIRST
                if is_stunned(pdata):
                    consume_stun(pdata)
                    self.player_actions[pid] = {'action': 'defend', 'target': None, 'action_label': 'Stunned!'}
                    self.battle_log.append(f"💫 {pdata['user'].display_name} is stunned and cannot act!")
                # 2. Tick effects (decrements turns, applies DoT/HoT, ticks cooldowns)
                net_delta, tick_lines = tick_battle_effects(pdata, pdata.get('attack', 10))
                if net_delta != 0:
                    pdata['hp'] = max(0, min(pdata['max_hp'], pdata['hp'] + net_delta))
                skill_tick_lines.extend(tick_lines)
        except Exception:
            pass

        # Group actions by type for simultaneous processing
        attackers = []
        defenders = []
        chargers = []
        skillers = []

        for player_id in alive_players:
            if player_id in self.player_actions and self.players[player_id]['alive']:
                action_data = self.player_actions[player_id]
                action = action_data['action']

                if action == 'attack':
                    attackers.append((player_id, action_data))
                elif action == 'defend':
                    defenders.append((player_id, action_data))
                elif action == 'charge':
                    chargers.append((player_id, action_data))
                elif action == 'skill':
                    skillers.append((player_id, action_data))

        # Order actions by lobby join order to respect turn cycle
        def _order_key(pid):
            try:
                return self.join_order_ids.index(pid)
            except ValueError:
                return len(self.join_order_ids)
        attackers.sort(key=lambda x: _order_key(x[0]))
        defenders.sort(key=lambda x: _order_key(x[0]))
        chargers.sort(key=lambda x: _order_key(x[0]))
        skillers.sort(key=lambda x: _order_key(x[0]))

        # Process skills (self-targeted or enemy-targeted)
        for player_id, action_data in skillers:
            await self._process_pvp_skill(player_id, action_data)

        # Process charges first (they just increase multipliers)
        for player_id, action_data in chargers:
            await self.process_charge(player_id)

        # Process attacks and defenses simultaneously
        await self.process_combat_interactions(attackers, defenders)

        # Check for battle end conditions
        if self.check_battle_end():
            await self.end_battle()
        else:
            # Small delay before starting next round
            await asyncio.sleep(2)
            # Start next turn
            await self.start_turn()
        
        # Clean up dead players from turn order
        self.turn_order = [p for p in self.turn_order if p['alive']]

        # Build round summary for battle log
        round_summary = f"**Round {self.turn_count}**\n"
        for player_id, player in self.players.items():
            if not player['alive']:
                continue

            action_info = player.get('last_action_info', {})
            action_label = action_info.get('action_label', player.get('last_action'))
            
            if player.get('last_action') == 'attack':
                target_id = action_info.get('target_id')
                target = self.players.get(target_id)
                damage = action_info.get('damage', 0)
                if target:
                    round_summary += f"- {player['user'].display_name} used {action_label} on {target['user'].display_name} dealing {damage} damage.\n"
            elif player.get('last_action') == 'defend':
                parry_damage = action_info.get('parry_damage', 0)
                round_summary += f"- {player['user'].display_name} used {action_label} and parried {parry_damage} damage.\n"
            elif player.get('last_action') == 'charge':
                charge_mult = action_info.get('charge_multiplier', 0)
                round_summary += f"- {player['user'].display_name} used {action_label} and is now at {charge_mult}x charge.\n"

        self.round_history.append(round_summary)
    
    async def process_charge(self, player_id: str):
        """Process a charge action using the new progression system"""
        player = self.players[player_id]
        current_charge = player.get('charge', 1.0)
        new_charge = DamageCalculator.get_next_charge_multiplier(cast(float, current_charge))
        player['charge'] = new_charge
        # Track last action for UI
        player['last_action'] = 'charge'
        player['last_action_info'] = {
            'charge_multiplier': new_charge,
            'action_label': self.player_actions.get(player_id, {}).get('action_label', 'Charge')
        }

        self.battle_log.append(
            f"⚡ {player['user'].display_name} charges up! "
            f"(Power: {new_charge:.0f}x)"
        )
    
    async def process_combat_interactions(self, attackers, defenders):
        """Process combat interactions based on the new mechanics"""
        # Create a map of who is defending whom
        defending_map = {}
        for defender_id, action_data in defenders:
            target_id = action_data.get('target', defender_id)
            defending_map[target_id] = defender_id
        
        # Create a map of who is attacking whom
        attacking_map = {}
        for attacker_id, action_data in attackers:
            target_id = action_data.get('target')
            if not target_id or target_id not in self.players or not self.players[target_id]['alive']:
                # Find a valid target
                alive_targets = [p_id for p_id, p in self.players.items() 
                               if p['alive'] and p_id != attacker_id]
                if alive_targets:
                    target_id = random.choice(alive_targets)
                    action_data['target'] = target_id
                else:
                    continue
            attacking_map[attacker_id] = target_id
        
        # Handle mutual attacks (both attacking each other)
        processed_pairs = set()
        for attacker_id, target_id in attacking_map.items():
            if target_id in attacking_map and attacking_map[target_id] == attacker_id:
                # Mutual attack - both take full damage
                pair = tuple(sorted([attacker_id, target_id]))
                if pair not in processed_pairs:
                    processed_pairs.add(pair)
                    await self.process_mutual_attack(attacker_id, target_id)
        
        # Process remaining attacks
        for attacker_id, action_data in attackers:
            target_id = action_data.get('target')
            if not target_id:
                continue
                
            # Skip if this was already processed as a mutual attack
            pair = tuple(sorted([attacker_id, target_id]))
            if pair in processed_pairs:
                continue
            
            # Check if target is being defended
            defender_id = defending_map.get(target_id)
            if defender_id and defender_id in self.players and self.players[defender_id]['alive']:
                # Attack vs Defense - use parry mechanics
                await self.process_attack_vs_defense(attacker_id, target_id, defender_id)
            else:
                # Attack vs no defense - full damage
                await self.process_undefended_attack(attacker_id, target_id)
    
    async def process_attack_vs_defense(self, attacker_id: str, target_id: str, defender_id: str):
        """Process attack vs defense with parry mechanics"""
        attacker = self.players[attacker_id]
        target = self.players[target_id]
        defender = self.players[defender_id]
        
        # Get relationship multiplier for PvP damage
        relationship_mult_attacker, relationship_mult_target = await get_relationship_multipliers(attacker_id, target_id)
        
        # Use new damage calculator
        result = DamageCalculator.calculate_battle_action(
            attacker_attack=_pvp_effective_atk(attacker),
            target_defense=_pvp_effective_def(defender),
            charge_multiplier=cast(float, attacker.get('charge', 1.0)),
            target_charge_multiplier=1.0,
            action_type="attack",
            attacker_type=str(attacker.get('type','')).lower(),
            attacker_element=str(attacker.get('element','')).lower(),
            attacker_element2=cast(Optional[str], attacker.get('element2')),
            defender_type=str(defender.get('type','')).lower(),
            defender_element=str(defender.get('element','')).lower(),
            defender_element2=cast(Optional[str], defender.get('element2')),
            attacker_species=cast(Optional[str], cast(Dict[str, Any], attacker.get('pet', {})).get('species')),
            defender_species=cast(Optional[str], cast(Dict[str, Any], defender.get('pet', {})).get('species'))
        )
        
        # Apply damage and parry
        damage_to_target = result['final_damage']
        # Apply relationship multiplier to damage
        damage_to_target = int(damage_to_target * relationship_mult_attacker)
        
        # Apply 25% extra incoming damage if target is charging
        if target.get('charging', False) and damage_to_target > 0:
            damage_to_target = int(damage_to_target * 1.25)
        parry_damage = result['parry_damage']
        
        # Apply skill-based damage reduction, shields, and reflect on target
        reflect_dmg_to_attacker = 0
        try:
            from Systems.Pets.Logic.battle_skills import (
                get_damage_reduction, absorb_damage_through_shield, get_reflect_value
            )
            if damage_to_target > 0:
                skill_dr = get_damage_reduction(target)
                if skill_dr > 0:
                    damage_to_target = max(1, int(damage_to_target * (1.0 - skill_dr)))
                damage_to_target, _absorbed, _shield_log = absorb_damage_through_shield(target, damage_to_target)
                reflect_frac = get_reflect_value(target)
                if reflect_frac > 0 and damage_to_target > 0:
                    reflect_dmg_to_attacker = max(1, int(damage_to_target * reflect_frac))
        except Exception:
            pass

        # Apply damage to target
        if damage_to_target > 0:
            target['hp'] = max(0, target['hp'] - damage_to_target)
            attacker['damage_dealt'] = attacker.get('damage_dealt', 0) + damage_to_target
            target['damage_taken'] = target.get('damage_taken', 0) + damage_to_target

        # Apply reflect damage to attacker
        if reflect_dmg_to_attacker > 0:
            attacker['hp'] = max(0, attacker['hp'] - reflect_dmg_to_attacker)
            target['damage_dealt'] = target.get('damage_dealt', 0) + reflect_dmg_to_attacker
            attacker['damage_taken'] = attacker.get('damage_taken', 0) + reflect_dmg_to_attacker
            self.battle_log.append(f"🪞 {target['user'].display_name} reflects {reflect_dmg_to_attacker} damage!")

        # Apply parry damage to attacker
        if parry_damage > 0:
            attacker['hp'] = max(0, attacker['hp'] - parry_damage)
            defender['damage_dealt'] = defender.get('damage_dealt', 0) + parry_damage
            attacker['damage_taken'] = attacker.get('damage_taken', 0) + parry_damage

        # Reset charge multipliers after use
        attacker['charge'] = 1.0
        defender['charge'] = 1.0

        # Track last actions for UI parity
        attacker_effective = self._get_roll_multiplier_from_result(result.get('attack_result', 'base'), result.get('attack_roll', 0))
        defender_effective = 0.0
        if result.get('attack_result') != 'miss':
            defender_effective = self._get_roll_multiplier_from_result(result.get('defense_result', 'base'), result.get('defense_roll', 0))
        attacker['last_action'] = 'attack'
        attacker['last_action_info'] = {
            'target_id': target_id,
            'damage': damage_to_target,
            'parry_taken': parry_damage,
            'roll': result.get('attack_roll', 0),
            'result': result.get('attack_result', 'base'),
            'effective_multiplier': attacker_effective,
            'charge_multiplier_used': cast(float, attacker.get('charge', 1.0)),
            'action_label': self.player_actions.get(attacker_id, {}).get('action_label', 'Attack')
        }
        defender['last_action'] = 'defend'
        defender['last_action_info'] = {
            'protected_id': target_id,
            'parry_damage': parry_damage,
            'roll': result.get('defense_roll', 0),
            'result': result.get('defense_result', 'base'),
            'defense_effectiveness': defender_effective,
            'action_label': self.player_actions.get(defender_id, {}).get('action_label', 'Defend')
        }
        
        # Add to battle log
        atk_name = result.get('attacker_action_name', 'Attack')
        def_name = result.get('target_action_name', 'Defend')
        self.battle_log.append(
            f"{emoji_mod.mention('Attack') or '⚔️'} {attacker['user'].display_name} uses {atk_name} on {target['user'].display_name} "
            f"(Roll: {result['attack_roll']}, {result['attack_result']}) "
            f"{emoji_mod.mention('Defend') or '🛡️'} {defender['user'].display_name} uses {def_name} "
            f"(Roll: {result['defense_roll']}, {result['defense_result']})"
        )
        
        if damage_to_target > 0:
            self.battle_log.append(f"{emoji_mod.mention('Damage') or '💥'} {target['user'].display_name} takes {damage_to_target} damage!")
        
        if parry_damage > 0:
            self.battle_log.append(f"{emoji_mod.mention('Refresh') or '🔄'} {attacker['user'].display_name} takes {parry_damage} parry damage!")
        
        # Check for defeats and award XP
        await self.check_defeat_and_award_xp(target_id, attacker_id)
        await self.check_defeat_and_award_xp(attacker_id, defender_id)
    
    async def process_undefended_attack(self, attacker_id: str, target_id: str):
        """Process attack with no defense - full damage"""
        attacker = self.players[attacker_id]
        target = self.players[target_id]
        
        # Use new damage calculator with no defense
        result = DamageCalculator.calculate_battle_action(
            attacker_attack=_pvp_effective_atk(attacker),
            target_defense=0,
            charge_multiplier=cast(float, attacker.get('charge', 1.0)),
            target_charge_multiplier=1.0,
            action_type="attack",
            attacker_type=str(attacker.get('type','')).lower(),
            attacker_element=str(attacker.get('element','')).lower(),
            attacker_element2=cast(Optional[str], attacker.get('element2')),
            defender_type=str(target.get('type','')).lower(),
            defender_element=str(target.get('element','')).lower(),
            defender_element2=cast(Optional[str], target.get('element2')),
            attacker_species=cast(Optional[str], cast(Dict[str, Any], attacker.get('pet', {})).get('species')),
            defender_species=cast(Optional[str], cast(Dict[str, Any], target.get('pet', {})).get('species'))
        )
        
        # Apply full damage, with charging vulnerability if target is charging
        damage = result['final_damage']
        if target.get('charging', False) and damage > 0:
            damage = int(damage * 1.25)

        # Apply skill-based damage reduction, shields, and reflect on target
        reflect_dmg_to_attacker = 0
        try:
            from Systems.Pets.Logic.battle_skills import (
                get_damage_reduction, absorb_damage_through_shield, get_reflect_value
            )
            skill_dr = get_damage_reduction(target)
            if skill_dr > 0:
                damage = max(1, int(damage * (1.0 - skill_dr)))
            damage, _absorbed, _shield_log = absorb_damage_through_shield(target, damage)
            reflect_frac = get_reflect_value(target)
            if reflect_frac > 0 and damage > 0:
                reflect_dmg_to_attacker = max(1, int(damage * reflect_frac))
        except Exception:
            pass

        target['hp'] = max(0, target['hp'] - damage)
        attacker['damage_dealt'] = attacker.get('damage_dealt', 0) + damage
        target['damage_taken'] = target.get('damage_taken', 0) + damage

        # Apply reflect damage to attacker
        if reflect_dmg_to_attacker > 0:
            attacker['hp'] = max(0, attacker['hp'] - reflect_dmg_to_attacker)
            target['damage_dealt'] = target.get('damage_dealt', 0) + reflect_dmg_to_attacker
            attacker['damage_taken'] = attacker.get('damage_taken', 0) + reflect_dmg_to_attacker
            self.battle_log.append(f"🪞 {target['user'].display_name} reflects {reflect_dmg_to_attacker} damage!")

        # No persistent stat depletion

        # Reset charge multiplier after use
        attacker['charge'] = 1.0

        # Track last action for UI parity
        effective = self._get_roll_multiplier_from_result(result.get('attack_result', 'base'), result.get('attack_roll', 0))
        attacker['last_action'] = 'attack'
        attacker['last_action_info'] = {
            'target_id': target_id,
            'damage': damage,
            'roll': result.get('attack_roll', 0),
            'result': result.get('attack_result', 'base'),
            'effective_multiplier': effective,
            'charge_multiplier_used': cast(float, attacker.get('charge', 1.0)),
            'action_label': self.player_actions.get(attacker_id, {}).get('action_label', 'Attack')
        }
        
        # Add to battle log
        atk_name = result.get('attacker_action_name', 'Attack')
        self.battle_log.append(
            f"{emoji_mod.mention('Attack') or '⚔️'} {attacker['user'].display_name} uses {atk_name} on {target['user'].display_name} "
            f"(Roll: {result['attack_roll']}, {result['attack_result']}) "
            f"{emoji_mod.mention('Damage') or '💥'} {damage} damage! (No defense)"
        )
        
        # Check for defeat and award XP
        await self.check_defeat_and_award_xp(target_id, attacker_id)
    
    async def process_mutual_attack(self, player1_id: str, player2_id: str):
        """Process mutual attacks where both players attack each other simultaneously"""
        player1 = self.players[player1_id]
        player2 = self.players[player2_id]
        
        # Get relationship multipliers for both players
        relationship_mult_p1, relationship_mult_p2 = await get_relationship_multipliers(player1_id, player2_id)
        
        # Calculate damage for player1 attacking player2
        result1 = DamageCalculator.calculate_battle_action(
            attacker_attack=_pvp_effective_atk(player1),
            target_defense=0,
            charge_multiplier=float(cast(Any, player1.get('charge', 1.0))),
            target_charge_multiplier=1.0,
            action_type="attack",
            attacker_type=str(player1.get('type','')).lower(),
            attacker_element=str(player1.get('element','')).lower(),
            attacker_element2=cast(Optional[str], player1.get('element2')),
            defender_type=str(player2.get('type','')).lower(),
            defender_element=str(player2.get('element','')).lower(),
            defender_element2=cast(Optional[str], player2.get('element2')),
            attacker_species=cast(Optional[str], cast(Dict[str, Any], player1.get('pet', {})).get('species')),
            defender_species=cast(Optional[str], cast(Dict[str, Any], player2.get('pet', {})).get('species'))
        )
        
        # Calculate damage for player2 attacking player1
        result2 = DamageCalculator.calculate_battle_action(
            attacker_attack=_pvp_effective_atk(player2),
            target_defense=0,
            charge_multiplier=float(cast(Any, player2.get('charge', 1.0))),
            target_charge_multiplier=1.0,
            action_type="attack",
            attacker_type=str(player2.get('type','')).lower(),
            attacker_element=str(player2.get('element','')).lower(),
            attacker_element2=cast(Optional[str], player2.get('element2')),
            defender_type=str(player1.get('type','')).lower(),
            defender_element=str(player1.get('element','')).lower(),
            defender_element2=cast(Optional[str], player1.get('element2')),
            attacker_species=cast(Optional[str], cast(Dict[str, Any], player2.get('pet', {})).get('species')),
            defender_species=cast(Optional[str], cast(Dict[str, Any], player1.get('pet', {})).get('species'))
        )
        
        # Apply damage simultaneously
        damage1 = result1['final_damage']
        damage2 = result2['final_damage']
        
        # Apply relationship multipliers
        damage1 = int(damage1 * relationship_mult_p1)
        damage2 = int(damage2 * relationship_mult_p2)
        
        # Apply 25% vulnerability if the targets are charging
        if player2.get('charging', False) and damage1 > 0:
            damage1 = int(damage1 * 1.25)
        if player1.get('charging', False) and damage2 > 0:
            damage2 = int(damage2 * 1.25)
        
        # Apply skill-based damage reduction, shields, and reflect on both players
        reflect1_to_p1 = 0  # player2 reflects back to player1
        reflect2_to_p2 = 0  # player1 reflects back to player2
        try:
            from Systems.Pets.Logic.battle_skills import (
                get_damage_reduction, absorb_damage_through_shield, get_reflect_value
            )
            # damage1 hits player2
            if damage1 > 0:
                dr2 = get_damage_reduction(player2)
                if dr2 > 0:
                    damage1 = max(1, int(damage1 * (1.0 - dr2)))
                damage1, _a, _sl = absorb_damage_through_shield(player2, damage1)
                rf2 = get_reflect_value(player2)
                if rf2 > 0 and damage1 > 0:
                    reflect1_to_p1 = max(1, int(damage1 * rf2))
            # damage2 hits player1
            if damage2 > 0:
                dr1 = get_damage_reduction(player1)
                if dr1 > 0:
                    damage2 = max(1, int(damage2 * (1.0 - dr1)))
                damage2, _a, _sl = absorb_damage_through_shield(player1, damage2)
                rf1 = get_reflect_value(player1)
                if rf1 > 0 and damage2 > 0:
                    reflect2_to_p2 = max(1, int(damage2 * rf1))
        except Exception:
            pass

        player2['hp'] = max(0, player2['hp'] - damage1)
        player1['hp'] = max(0, player1['hp'] - damage2)

        # Apply reflect damage
        if reflect1_to_p1 > 0:
            player1['hp'] = max(0, player1['hp'] - reflect1_to_p1)
            player2['damage_dealt'] = player2.get('damage_dealt', 0) + reflect1_to_p1
            player1['damage_taken'] = player1.get('damage_taken', 0) + reflect1_to_p1
            self.battle_log.append(f"🪞 {player2['user'].display_name} reflects {reflect1_to_p1} damage!")
        if reflect2_to_p2 > 0:
            player2['hp'] = max(0, player2['hp'] - reflect2_to_p2)
            player1['damage_dealt'] = player1.get('damage_dealt', 0) + reflect2_to_p2
            player2['damage_taken'] = player2.get('damage_taken', 0) + reflect2_to_p2
            self.battle_log.append(f"🪞 {player1['user'].display_name} reflects {reflect2_to_p2} damage!")

        # Update damage stats
        player1['damage_dealt'] = player1.get('damage_dealt', 0) + damage1
        player2['damage_taken'] = player2.get('damage_taken', 0) + damage1
        player2['damage_dealt'] = player2.get('damage_dealt', 0) + damage2
        player1['damage_taken'] = player1.get('damage_taken', 0) + damage2

        # No persistent stat depletion

        # Reset charge multipliers after use
        player1['charge'] = 1.0
        player2['charge'] = 1.0

        # Track last actions for UI
        eff1 = self._get_roll_multiplier_from_result(result1.get('attack_result', 'base'), result1.get('attack_roll', 0))
        eff2 = self._get_roll_multiplier_from_result(result2.get('attack_result', 'base'), result2.get('attack_roll', 0))
        player1['last_action'] = 'attack'
        player1['last_action_info'] = {
            'target_id': player2_id,
            'damage': damage1,
            'roll': result1.get('attack_roll', 0),
            'result': result1.get('attack_result', 'base'),
            'effective_multiplier': eff1,
            'charge_multiplier_used': cast(float, player1.get('charge', 1.0)),
            'action_label': self.player_actions.get(player1_id, {}).get('action_label', 'Attack')
        }
        player2['last_action'] = 'attack'
        player2['last_action_info'] = {
            'target_id': player1_id,
            'damage': damage2,
            'roll': result2.get('attack_roll', 0),
            'result': result2.get('attack_result', 'base'),
            'effective_multiplier': eff2,
            'charge_multiplier_used': cast(float, player2.get('charge', 1.0)),
            'action_label': self.player_actions.get(player2_id, {}).get('action_label', 'Attack')
        }
        
        # Add to battle log
        a1 = result1.get('attacker_action_name', 'Attack')
        a2 = result2.get('attacker_action_name', 'Attack')
        self.battle_log.append(
            f"{emoji_mod.mention('Attack') or '⚔️'}{emoji_mod.mention('Damage') or '💥'} MUTUAL STRIKES! {player1['user'].display_name} uses {a1} and {player2['user'].display_name} uses {a2} simultaneously!"
        )
        self.battle_log.append(
            f"{emoji_mod.mention('Attack') or '⚔️'} {player1['user'].display_name} deals {damage1} damage "
            f"(Roll: {result1['attack_roll']}, {result1['attack_result']})"
        )
        self.battle_log.append(
            f"{emoji_mod.mention('Attack') or '⚔️'} {player2['user'].display_name} deals {damage2} damage "
            f"(Roll: {result2['attack_roll']}, {result2['attack_result']})"
        )
        
        # Check for defeats and award XP
        await self.check_defeat_and_award_xp(player2_id, player1_id)
        await self.check_defeat_and_award_xp(player1_id, player2_id)
    
    async def check_defeat_and_award_xp(self, victim_id: str, killer_id: str):
        """Check if a player is defeated and award XP to the killer"""
        if victim_id not in self.players or killer_id not in self.players:
            return
            
        victim = self.players[victim_id]
        killer = self.players[killer_id]
        
        if victim['hp'] <= 0 and victim['alive']:
            victim['alive'] = False
            self.battle_log.append(f"{emoji_mod.mention('Skull') or '💀'} {victim['user'].display_name} has been defeated!")
            
            # Award XP and track kills using new formula
            killer_dealt = int(killer.get('damage_dealt', 0))
            killer_taken = int(killer.get('damage_taken', 0))
            victim_dealt = int(victim.get('damage_dealt', 0))
            victim_taken = int(victim.get('damage_taken', 0))
            
            killer['kills'] = killer.get('kills', 0) + 1
            
            # Track elimination count on killer's pet
            try:
                await user_data_manager.update_pet_battle_stats(
                    str(killer['user'].id),
                    "pvp",
                    eliminations=1,
                    damage_dealt=0,
                )
            except Exception:
                pass
            
            # Check for level up
            if killer['xp_earned'] >= int(cast(Any, killer.get('xp_to_next_level', 100))):
                pet = killer.get('pet', {})
                old_level = cast(Dict[str, Any], pet).get('level', 1)
                leveled_up, level_up_details = await add_experience(killer['user'].id, killer['xp_earned'], "pvp_battle", equipment_stats=None)
                if leveled_up and level_up_details and pet:
                    new_level = level_up_details.get('new_level', old_level)
                    level_up_embed = await LootCalculator.create_level_up_embed(pet, old_level, new_level, "pvp")
                    await self.ctx.send(embed=level_up_embed)
    
    # Removed persistent stat depletion utilities
     
    async def process_defend(self, defender_id: str, target_id: str):
        """Process a defend action with enhanced mechanics
        
        Args:
            defender_id: ID of the player defending
            target_id: ID of the player being defended (can be self)
        """
        if defender_id not in self.players or not self.players[defender_id]['alive']:
            return  # Skip if defender is invalid
            
        defender = self.players[defender_id]
        
        # If target is invalid, default to self-defense
        if target_id not in self.players or not self.players[target_id]['alive']:
            target_id = defender_id
            
        target = self.players[target_id]
        
        # Set up guard relationship (can defend others or self)
        self.guard_relationships[defender_id] = target_id
        
        # Store base defense if not already stored
        if 'base_defense' not in defender:
            defender['base_defense'] = defender['defense']
            
        # Add to defending players set for this turn (double defense)
        self.defending_players.add(defender_id)

        # Track last action for UI
        defender['last_action'] = 'defend'
        defender['last_action_info'] = {
            'protected_id': target_id,
            'parry_damage': 0,
            'roll': None,
            'result': 'base',
            'defense_effectiveness': None
        }
        
        # Add to battle log
        if target_id == defender_id:
            self.battle_log.append(
                f"🛡️ {defender['user'].display_name} takes a defensive stance! "
                f"(Defense DOUBLED for this turn!)"
            )
        else:
            self.battle_log.append(
                f"🛡️ {defender['user'].display_name} prepares to defend {target['user'].display_name}! "
                f"(Defense DOUBLED for this turn!)"
            )
    
    def check_battle_end(self) -> bool:
        """Check if the battle should end based on the battle mode"""
        if self.battle_over:
            return True
            
        # End when only one player remains alive (applies to both FFA and 1v1)
        alive_players = [p for p in self.players.values() if p['alive']]
        if len(alive_players) <= 1:
            self.battle_over = True
            return True
                
        return False
    
    async def end_battle(self):
        """Handle battle conclusion and distribute rewards"""
        # Determine winner (FFA: last alive; 1v1: alive participant)
        alive_players = [p for p in self.players.values() if p['alive']]
        winner = alive_players[0] if alive_players else None
        if winner:
            self.battle_log.append(f"{emoji_mod.mention('Trophy') or '🏆'} {winner['user'].mention} is the last one standing!")
        
        # Calculate XP per player
        xp_rewards = {}
        for member_id, player in self.players.items():
            if not player.get('pet'):
                continue
            dealt = int(player.get('damage_dealt', 0))
            taken = int(player.get('damage_taken', 0))
            
            # Determine if winner
            is_winner = (winner and member_id == str(winner['user'].id))
            
            xp = LootCalculator.calculate_pvp_xp(dealt, taken, is_winner=is_winner)
            player['xp_earned'] = xp
            xp_rewards[member_id] = xp
        
        # Apply XP and rewards to pets
        level_ups = []
        for member_id, xp in xp_rewards.items():
            try:
                player = self.players.get(member_id)
                if not player:
                    continue
                    
                is_winner = (winner and member_id == str(winner['user'].id))
                
                # Update stats via UDM
                await user_data_manager.update_pet_battle_stats(
                    str(member_id),
                    "pvp",
                    wins=1 if is_winner else 0,
                    losses=1 if not is_winner else 0,
                    xp_earned=xp,
                    damage_dealt=int(player.get('damage_dealt', 0)),
                    damage_taken=int(player.get('damage_taken', 0))
                )
                
                # Then award XP and check for level up
                pet = player.get('pet', {})
                old_level = pet.get('level', 1)
                
                
                leveled_up, level_up_details = await add_experience(str(member_id), xp, "pvp_battle", equipment_stats=None)
                
                if leveled_up and level_up_details:
                    new_level = level_up_details.get('new_level', old_level)
                    level_ups.append((member_id, pet, old_level, new_level, level_up_details))
                
            except Exception as e:
                logger.error(f"Error updating pet data for {member_id}: {e}")
        
        # Build result embed
        embed = self.build_battle_embed("🏆 Battle Over!")
        
        # Add XP rewards
        xp_text = []
        for member_id, player in self.players.items():
            if player.get('xp_earned', 0) > 0:
                xp_text.append(
                    f"{player['user'].mention}: "
                    f"{player['xp_earned']} XP "
                    f"({player.get('kills',0)} kills, {player.get('assists',0)} assists, "
                    f"{player.get('damage_dealt',0)} damage)"
                )
        
        if xp_text:
            embed.add_field(
                name="XP Rewards",
                value="\n".join(xp_text),
                inline=False
            )
        
        # Send level up embeds
        if level_ups:
            for member_id, pet, old_level, new_level, level_up_details in level_ups:
                player = self.get_player(member_id)
                if player and level_up_details:
                    try:
                        old_lvl = level_up_details.get('old_level', old_level)
                        new_lvl = level_up_details.get('new_level', new_level)
                        source = level_up_details.get('source', 'pvp')
                        
                        level_up_embed = await LootCalculator.create_level_up_embed(pet, old_lvl, new_lvl, source)
                        await self.ctx.send(embed=level_up_embed)
                    except Exception as e:
                        logger.error(f"Error sending level up embed: {e}")
                        # Fallback to simple text
                        embed.add_field(
                            name="Level Up!",
                            value=f"🎉 {player['user'].mention}'s {pet['name']} leveled up from {old_level} to {new_level}!",
                            inline=False
                        )
        
        if winner:
            awarded_items = await LootCalculator.award_loot_items(
                winner['user'].id,
                winner['pet'],
                source='pvp',
                difficulty=winner['pet']['level']
            )
            if awarded_items:
                loot_str = ", ".join([f"{item['quantity']} {item['item_id'].replace('_', ' ').title()}" for item in awarded_items])
                embed.add_field(name="Winner's Loot", value=loot_str, inline=False)

        if self.round_history:
            round_summary = "\n".join(self.round_history)
            embed.add_field(name="Round Breakdown", value=round_summary, inline=False)

        # Disable all buttons and update message
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        
        await self.message.edit(embed=embed, view=self)
    
    def get_player(self, player_id: str) -> Optional[PlayerDataType]:
        return self.players.get(player_id)
    
    def build_battle_embed(self, title: str) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            color=discord.Color.blue(),
            description="\n".join(self.battle_log[-5:]) if self.battle_log else "Battle starting..."
        )
        lines = []
        for member_id, data in self.players.items():
            if not data['alive']:
                lines.append(f"{emoji_mod.mention('Skull') or '💀'} ~~{data['user'].display_name}~~")
                continue
            hp_pct = (data['hp'] / data['max_hp']) * 100
            
            pet = data.get('pet', {})
            hp_bar = self._get_hp_bar(hp_pct, pet)
            
            status = []
            if data.get('charging'):
                status.append(f"{emoji_mod.mention('Charge') or '⚡'}x{data.get('charge',1.0):.1f}")
            defender_count = 1 if member_id in self.defending_players else 0
            if defender_count > 0:
                status.append(f"{emoji_mod.mention('Defend') or '🛡️'}×{defender_count}")
            line = f"{emoji_mod.mention('Health') or '❤️'} {hp_bar} {data['hp']}/{data['max_hp']} {data['user'].display_name}"
            if status:
                line += f" [{' '.join(status)}]"
            la = data.get('last_action')
            info = data.get('last_action_info', {})
            if la == 'attack':
                tgt = cast(PlayerDataType, self.players.get(cast(str, info.get('target_id', '')), {})).get('user', None)
                tgt_name = tgt.display_name if tgt else 'Unknown'
                dmg = info.get('damage')
                roll = info.get('roll')
                res = info.get('result')
                eff = info.get('effective_multiplier')
                cm = info.get('charge_multiplier_used')
                action_label = info.get('action_label', 'Attack')
                line += f" \n   ⚔️ Last: {action_label} {dmg} dmg → {tgt_name} • roll {roll} {res} x{eff:.1f}"
                if cm and cm != 1.0:
                    line += f" • ⚡x{cm:.1f}"
            elif la == 'defend':
                prot = cast(PlayerDataType, self.players.get(cast(str, info.get('protected_id', '')), {})).get('user', None)
                prot_name = prot.display_name if prot else ('self' if info.get('protected_id') == member_id else 'Unknown')
                parry = info.get('parry_damage', 0)
                roll = info.get('roll')
                res = info.get('result')
                eff = info.get('defense_effectiveness')
                eff_text = f" x{eff:.1f}" if isinstance(eff, (int, float)) else ""
                action_label = info.get('action_label', 'Defend')
                line += f" \n   🛡️ Last: {action_label} {prot_name} • parry {parry} • roll {roll} {res}{eff_text}"
            elif la == 'charge':
                cm = info.get('charge_multiplier')
                action_label = info.get('action_label', 'Charge')
                line += f" \n   ⚡ Last: {action_label} to x{cm:.1f}"
            lines.append(line)
        embed.add_field(name="Participants", value="\n".join(lines) if lines else "No players", inline=False)
        embed.set_footer(text=f"Turn {self.turn_count}")
        return embed
    
    @staticmethod
    def _get_hp_bar(percentage: float, pet: Optional[dict] = None, length: int = 10) -> str:
        # Element cycling for filled bar
        element = str(pet.get('element', 'basic')).lower() if pet else 'basic'
        e2 = str(pet.get('secondary_element', '')).lower() if pet and pet.get('secondary_element') else None
        
        e1_char = LootCalculator.get_pet_emoji("Elements", element) or '█'
        e2_char = LootCalculator.get_pet_emoji("Elements", e2) if e2 else None
        
        filled_length = int(round(length * percentage / 100))
        # Ensure filled_length is within bounds [0, length]
        filled_length = max(0, min(length, filled_length))
        
        filled_bar = ""
        for i in range(filled_length):
            if e2_char:
                filled_bar += e1_char if i % 2 == 0 else e2_char
            else:
                filled_bar += e1_char
                
        empty_char = '⬛'
        
        return f"{filled_bar}{empty_char * (length - filled_length)}"

class PvPActionView(discord.ui.View):
    """View for players to select actions in PvP battles"""
    
    def __init__(self, battle_view, player_id: str, enemies: Dict[str, dict], 
                 is_ffa: bool = False):
        """
        Initialize the action view
        
        Args:
            battle_view: The parent PvPBattleView
            player_id: ID of the current player
            enemies: Dict of enemy players (id -> player data)
            is_ffa: Whether this is a free-for-all battle
            is_team_battle: Whether this is a team battle
            allies: Dict of ally players (id -> player data) for team battles
        """
        super().__init__(timeout=60)
        self.battle_view = battle_view
        self.player_id = player_id
        self.enemies = enemies
        self.is_ffa = is_ffa
        self.allies: Dict[str, PlayerDataType] = {}
        self.message = None  # Store the message for cleanup
        self.add_buttons()
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the intended player can interact with these buttons"""
        if str(interaction.user.id) != self.player_id:
            await interaction.response.send_message("These action buttons aren't for you!", ephemeral=True)
            return False
        return True
    
    def add_buttons(self):
        # Attack button with target selection
        attack_options = []
        
        if self.is_ffa:
            # In FFA, show all other players as potential targets
                attack_options = [
                    discord.SelectOption(
                        label=f"{enemy['user'].display_name} (HP: {enemy['hp']}/{enemy['max_hp']})",
                        value=member_id,
                    emoji=emoji_mod.get_partial('Attack')
                    )
                    for member_id, enemy in self.enemies.items()
                    if enemy.get('alive', False)
                ]
        
        # Only add attack select if there are valid targets
        if attack_options:
            # Theme attack placeholder per player's pet type
            try:
                pdata = self.battle_view.players.get(self.player_id, {})
                pet = pdata.get('pet', {})
                ptype = str(pet.get('category','')).lower()
                pelem = str(pet.get('element','')).lower()
                labels = DamageCalculator.get_action_labels(ptype, pelem, species=pet.get('species'), custom_labels=pet.get('action_labels', {}))
                t_name = (ptype or 'unknown').title()
                attack_ph = f"{emoji_mod.mention('Attack') or '⚔️'} {labels.get('attack','Attack')} • {t_name} (select target)"
            except Exception:
                attack_ph = "⚔️ Select target to attack"
            attack_select = discord.ui.Select(
                placeholder=attack_ph,
                options=attack_options,
                min_values=1,
                max_values=1
            )
            attack_select.callback = self.attack_callback
            self.add_item(attack_select)
        
        # Defend button with target selection
        defend_options = [discord.SelectOption(label="Yourself", value="self", emoji=emoji_mod.get_partial('Defend'))]
        
        # Theme defend placeholder per player's pet type
        try:
            pdata = self.battle_view.players.get(self.player_id, {})
            pet = pdata.get('pet', {})
            ptype = str(pet.get('category','')).lower()
            pelem = str(pet.get('element','')).lower()
            labels = DamageCalculator.get_action_labels(ptype, pelem, species=pet.get('species'), custom_labels=pet.get('action_labels', {}))
            t_name = (ptype or 'unknown').title()
            defend_ph = f"{emoji_mod.mention('Defend') or '🛡️'} {labels.get('defend','Defend')} • {t_name} (self only)"
        except Exception:
            defend_ph = "🛡️ Select who to defend"
        defend_select = discord.ui.Select(
            placeholder=defend_ph,
            options=defend_options,
            min_values=1,
            max_values=1
        )
        defend_select.callback = self.defend_callback
        self.add_item(defend_select)

        surrender_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary, 
            label="Surrender", 
            emoji=emoji_mod.get_partial('No'),
            row=0
        )
        surrender_button.callback = self.surrender_callback
        self.add_item(surrender_button)

        # Charge button
        # Theme charge button per player's pet element and set per-combo verbs
        try:
            pdata = self.battle_view.players.get(self.player_id, {})
            pet = pdata.get('pet', {})
            pelem = str(pet.get('element','')).lower()
            ptype = str(pet.get('category','')).lower()
            labels = DamageCalculator.get_action_labels(ptype, pelem, species=pet.get('species'), custom_labels=pet.get('action_labels', {}))
            current_charge = int(pdata.get('charge', 1))
            charge_label = f"{labels.get('charge','Charge')} x{current_charge}"
        except Exception:
            charge_label = "Charge"
        charge_button = discord.ui.Button(
            style=discord.ButtonStyle.success,
            label=charge_label,
            emoji=emoji_mod.get_partial('Charge'),
            custom_id="charge",
            row=1
        )
        charge_button.callback = self.charge_callback
        self.add_item(charge_button)
    
    async def attack_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        interaction_data = cast(dict, interaction.data)
        target_id = interaction_data['values'][0]
        
        # Clean up the action message immediately
        if self.message:
            try:
                await self.message.delete()
            except:
                pass
        
        # Handle single target selection
        if target_id not in self.enemies or not self.enemies[target_id].get('alive', False):
            await interaction.followup.send("Invalid target selected!", ephemeral=True)
            return
        target_name = self.enemies[target_id]['user'].display_name
        
        # Apply charge multiplier if charging
        player_data = self.battle_view.players.get(self.player_id, {})
        charge_multiplier = player_data.get('charge', 1.0)

        pet = player_data.get('pet', {})
        labels = DamageCalculator.get_action_labels(str(pet.get('category','')).lower(), str(pet.get('element','')).lower(), species=pet.get('species'), custom_labels=pet.get('action_labels', {}))
        action_label = labels.get('attack', 'Attack')
        
        # Clear charge after attacking
        if player_data.get('charging', False):
            player_data['charging'] = False
            charge_text = f" (charged x{charge_multiplier:.1f} damage!)"
        else:
            charge_text = ""
        
        self.battle_view.player_actions[self.player_id] = {
            'action': 'attack',
            'target': target_id,
            'charge_multiplier': charge_multiplier,
            'action_label': action_label
        }
        
        # No confirmation message - action is recorded silently
        await self.battle_view.check_turn_completion()
    
    async def defend_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        interaction_data = cast(dict, interaction.data)
        target_id = interaction_data['values'][0]
        
        # Clean up the action message immediately
        if self.message:
            try:
                await self.message.delete()
            except:
                pass
        
        if target_id == "self":
            target_id = self.player_id
            target_name = "yourself"
        else:
            await interaction.followup.send("You can only defend yourself in this mode.", ephemeral=True)
            return
        
        player_data = self.battle_view.players.get(self.player_id, {})
        pet = player_data.get('pet', {})
        labels = DamageCalculator.get_action_labels(str(pet.get('category','')).lower(), str(pet.get('element','')).lower(), species=pet.get('species'), custom_labels=pet.get('action_labels', {}))
        action_label = labels.get('defend', 'Defend')
        
        # Set up defense state
        self.battle_view.player_actions[self.player_id] = {
            'action': 'defend',
            'target': target_id,
            'counter_attack': True,
            'action_label': action_label
        }
        
        self.battle_view.guard_relationships[self.player_id] = target_id
        
        # No confirmation message - action is recorded silently
        await self.battle_view.check_turn_completion()

    async def on_timeout(self):
        # Default to attack a random target if player doesn't choose
        if self.player_id not in self.battle_view.player_actions:
            alive_enemies = [mid for mid, e in self.enemies.items() if e['alive']]
            if alive_enemies:
                target_id = random.choice(alive_enemies)
                self.battle_view.player_actions[self.player_id] = {
                    'action': 'attack',
                    'target': target_id
                }
                await self.battle_view.check_all_actions_ready()
    
    async def surrender_callback(self, interaction: discord.Interaction):
        """Handle surrender button click"""
        if str(interaction.user.id) != self.player_id:
            return await interaction.response.send_message("This isn't your battle!", ephemeral=True)
            
        # Clean up the action message
        if self.message:
            try:
                await self.message.delete()
            except:
                pass
        
        # Mark player as defeated
        player_data = self.battle_view.players.get(self.player_id)
        if not player_data:
            return await interaction.response.send_message("You're not in this battle!", ephemeral=True)
        
        # Set player as defeated
        player_data['alive'] = False
        player_data['hp'] = 0
        
        # Add to battle log
        self.battle_view.battle_log.append(f"{emoji_mod.mention('No') or '🏳️'} {interaction.user.display_name} has surrendered!")
        
        # Disable all buttons
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        
        # Update the message
        await interaction.response.edit_message(view=self)
        
        # Check if battle should end
        if self.battle_view.check_battle_end():
            await self.battle_view.end_battle()
        else:
            await self.battle_view.update_battle_embed()

    async def charge_callback(self, interaction: discord.Interaction):
        """Handle charge button click"""
        if str(interaction.user.id) != self.player_id:
            return await interaction.response.send_message("This isn't your battle!", ephemeral=True)
            
        # Clean up the action message immediately
        if self.message:
            try:
                await self.message.delete()
            except:
                pass
        
        player_data = self.battle_view.players.get(self.player_id)
        if not player_data:
            return await interaction.response.send_message("You're not in this battle!", ephemeral=True)
        
        # Set charging state using proper progression system
        player_data['charging'] = True
        current_charge = player_data.get('charge', 1.0)
        new_charge = DamageCalculator.get_next_charge_multiplier(current_charge)
        player_data['charge'] = new_charge
        
        # Add to battle log
        try:
            pet = self.battle_view.players[self.player_id].get('pet', {})
            labels = DamageCalculator.get_action_labels(str(pet.get('category','')).lower(), str(pet.get('element','')).lower(), species=pet.get('species'), custom_labels=pet.get('action_labels', {}))
            cverb = labels.get('charge', 'Charge')
        except Exception:
            cverb = "Charge"
        self.battle_view.battle_log.append(f"{emoji_mod.mention('Charge') or '⚡'} {interaction.user.display_name} channels {cverb}! (Charge: x{new_charge})")
        
        # Disable charge button after use
        for item in self.children:
            if isinstance(item, discord.ui.Button) and getattr(item, 'custom_id', None) == 'charge':
                item.disabled = True
                break
        
        # Update the message
        await interaction.response.edit_message(view=self)
        
        # Mark action as complete
        self.battle_view.player_actions[self.player_id] = {
            'action': 'charge',
            'target': self.player_id,
            'action_label': cverb
        }
        
        await self.battle_view.check_turn_completion()