"""
Advanced Tournament System for Discord Pet Battles
Supports tournament sizes of 4, 8, 16, 32, 64 players
Features:
- DM invitation system with 30-minute response time
- NPC tournament participants
- 30-minute breaks between rounds
- Multiple simultaneous battles
- Proper battle skills and abilities
- Stats saving
- Web interface integration
"""

import discord
from discord.ext import commands
import asyncio
import random
import math
import logging
import json
from typing import List, Dict, Optional, Tuple, Union, Set, Any, TypedDict, cast
from enum import Enum
from datetime import datetime, timedelta
import uuid

from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.pets_system import add_experience, send_level_up_embed
from Systems.Pets.Logic.pet_brain import DamageCalculator, LootCalculator, StatsCalculator, NPCBrain
from Systems.Functions import emoji as emoji_mod
from Systems.Pets.PetGames.tournament import TournamentBattleView, TournamentMatch

logger = logging.getLogger('advanced_tournament')

class TournamentStatus(Enum):
    REGISTRATION = "registration"
    INVITATION = "invitation"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class TournamentSize(Enum):
    SMALL = 4
    MEDIUM = 8
    LARGE = 16
    X_LARGE = 32
    XX_LARGE = 64

class ParticipantType(Enum):
    PLAYER = "player"
    NPC = "npc"

class Participant:
    """Represents a tournament participant (either player or NPC)"""
    
    def __init__(self, participant_type: ParticipantType, 
                 user: Optional[discord.Member] = None,
                 npc_name: str = "", npc_data: Optional[Dict] = None):
        self.id = str(uuid.uuid4())
        self.type = participant_type
        self.user = user
        self.npc_name = npc_name
        self.npc_data = npc_data or {}
        self.accepted = False
        self.invitation_sent_at = None
        self.invitation_message_id = None
        
    @property
    def name(self) -> str:
        if self.type == ParticipantType.PLAYER and self.user:
            return self.user.display_name
        return self.npc_name
    
    @property
    def mention(self) -> str:
        if self.type == ParticipantType.PLAYER and self.user:
            return self.user.mention
        return f"🤖 {self.npc_name}"
    
    @property
    def is_player(self) -> bool:
        return self.type == ParticipantType.PLAYER
    
    def accept_invitation(self):
        self.accepted = True
    
    def decline_invitation(self):
        self.accepted = False
    
    def is_invitation_expired(self, timeout_minutes: int = 30) -> bool:
        if not self.invitation_sent_at:
            return False
        elapsed = datetime.now() - self.invitation_sent_at
        return elapsed.total_seconds() > (timeout_minutes * 60)

class AdvancedTournament:
    """Advanced tournament system with invitation system, NPCs, and round scheduling"""
    
    def __init__(self, bot, organizer: discord.Member, size: TournamentSize, channel: discord.TextChannel):
        self.bot = bot
        self.organizer = organizer
        self.size = size
        self.channel = channel
        self.id = str(uuid.uuid4())
        self.status = TournamentStatus.REGISTRATION
        self.participants: Dict[str, Participant] = {}
        self.matches: Dict[str, TournamentMatch] = {}
        self.current_round = 1
        self.max_rounds = int(math.log2(size.value))
        self.registration_deadline = datetime.now() + timedelta(minutes=10)
        self.bracket_message = None
        self.round_timer_task = None
        self.invitation_timeout_minutes = 30
        self.round_break_minutes = 30
        
        # Add organizer as first participant
        self.add_participant(ParticipantType.PLAYER, organizer)
    
    def add_participant(self, participant_type: ParticipantType, 
                       user: Optional[discord.Member] = None,
                       npc_name: str = "", npc_data: Optional[Dict] = None) -> bool:
        """Add a participant to the tournament"""
        if self.status not in [TournamentStatus.REGISTRATION, TournamentStatus.INVITATION]:
            return False
            
        if len(self.participants) >= self.size.value:
            return False
        
        participant = Participant(participant_type, user, npc_name, npc_data)
        
        # For players, check if they already exist
        if participant_type == ParticipantType.PLAYER and user:
            for existing in self.participants.values():
                if existing.type == ParticipantType.PLAYER and existing.user == user:
                    return False
        
        self.participants[participant.id] = participant
        return True
    
    def remove_participant(self, participant_id: str) -> bool:
        """Remove a participant from the tournament"""
        if self.status not in [TournamentStatus.REGISTRATION, TournamentStatus.INVITATION]:
            return False
            
        if participant_id in self.participants:
            del self.participants[participant_id]
            return True
        return False
    
    async def send_invitations(self, guild: discord.Guild) -> Dict[str, bool]:
        """Send DM invitations to all player participants"""
        if self.status != TournamentStatus.REGISTRATION:
            raise ValueError("Cannot send invitations - tournament not in registration phase")
        
        invitations_sent = {}
        
        for participant_id, participant in self.participants.items():
            if participant.type == ParticipantType.PLAYER and participant.user:
                try:
                    # Send DM invitation
                    embed = discord.Embed(
                        title="🏆 Tournament Invitation",
                        description=f"You've been invited to join a pet tournament!",
                        color=discord.Color.gold()
                    )
                    
                    embed.add_field(
                        name="Tournament Details",
                        value=f"• Size: {self.size.value} players\n• Organizer: {self.organizer.display_name}\n• Channel: {self.channel.mention}\n• Response Time: 30 minutes",
                        inline=False
                    )
                    
                    embed.add_field(
                        name="How to Accept",
                        value=f"React with ✅ to accept or ❌ to decline. You have 30 minutes to respond.",
                        inline=False
                    )
                    
                    view = TournamentInvitationView(self, participant_id)
                    message = await participant.user.send(embed=embed, view=view)
                    
                    participant.invitation_sent_at = datetime.now()
                    participant.invitation_message_id = message.id
                    invitations_sent[participant_id] = True
                    
                except discord.Forbidden:
                    logger.warning(f"Cannot send DM to {participant.user.display_name}")
                    invitations_sent[participant_id] = False
                except Exception as e:
                    logger.error(f"Error sending invitation to {participant.user.display_name}: {e}")
                    invitations_sent[participant_id] = False
        
        if any(invitations_sent.values()):
            self.status = TournamentStatus.INVITATION
        
        return invitations_sent
    
    async def generate_npc_participants(self, count: int):
        """Generate NPC participants to fill the tournament"""
        if self.status != TournamentStatus.REGISTRATION:
            return
            
        available_npc_names = [
            "BattleBot Alpha", "Cyber Claw", "Metal Mutant", "Digital Drake",
            "Circuit Serpent", "Robo Raptor", "AI Avalanche", "Neo Nemean",
            "Quantum Quetzal", "Synthetic Sphinx", "Mecha Manticore",
            "Android Basilisk", "Programmed Phoenix", "Binary Beast",
            "Algorithmic Ape", "Code Chimera", "Data Dragon", "Logic Leviathan"
        ]
        
        npc_templates = [
            {"level": 10, "species": "Dragon", "element": "Fire"},
            {"level": 12, "species": "Wolf", "element": "Earth"},
            {"level": 8, "species": "Phoenix", "element": "Fire"},
            {"level": 15, "species": "Kraken", "element": "Water"},
            {"level": 11, "species": "Griffin", "element": "Air"},
            {"level": 13, "species": "Basilisk", "element": "Poison"},
            {"level": 9, "species": "Unicorn", "element": "Light"},
            {"level": 14, "species": "Golem", "element": "Earth"}
        ]
        
        random.shuffle(available_npc_names)
        random.shuffle(npc_templates)
        
        npcs_to_add = min(count, len(available_npc_names), self.size.value - len(self.participants))
        
        for i in range(npcs_to_add):
            npc_name = available_npc_names[i]
            npc_data = npc_templates[i % len(npc_templates)]
            self.add_participant(ParticipantType.NPC, npc_name=npc_name, npc_data=npc_data)
    
    def get_accepted_participants(self) -> List[Participant]:
        """Get list of participants who have accepted invitations"""
        if self.status == TournamentStatus.REGISTRATION:
            # In registration phase, all participants are considered accepted
            return list(self.participants.values())
        
        accepted = []
        for participant in self.participants.values():
            if participant.type == ParticipantType.NPC:
                accepted.append(participant)  # NPCs auto-accept
            elif participant.accepted:
                accepted.append(participant)
        
        return accepted
    
    def can_start(self) -> bool:
        """Check if tournament can start"""
        accepted = self.get_accepted_participants()
        return (len(accepted) == self.size.value and 
                self.status in [TournamentStatus.REGISTRATION, TournamentStatus.INVITATION])
    
    def generate_bracket(self):
        """Generate the tournament bracket with accepted participants"""
        if not self.can_start():
            raise ValueError("Cannot generate bracket - tournament not ready")
        
        # Get accepted participants
        accepted_participants = self.get_accepted_participants()
        
        # Shuffle for random seeding
        random.shuffle(accepted_participants)
        
        # Generate first round matches
        self.matches.clear()
        match_count = 0
        
        for i in range(0, len(accepted_participants), 2):
            match_id = f"R{self.current_round}M{match_count + 1}"
            
            # Get participants for this match
            p1 = accepted_participants[i]
            p2 = accepted_participants[i + 1] if i + 1 < len(accepted_participants) else None
            
            # Convert to TournamentMatch format
            player1 = p1.user if p1.is_player else None
            player2 = p2.user if p2 and p2.is_player else None
            
            match = TournamentMatch(
                match_id=match_id,
                round_num=self.current_round,
                player1=player1,
                player2=player2
            )
            
            # Store NPC data if applicable
            if not p1.is_player:
                match.npc1 = p1
            if p2 and not p2.is_player:
                match.npc2 = p2
            
            self.matches[match_id] = match
            match_count += 1
        
        self.status = TournamentStatus.IN_PROGRESS
    
    async def start_round(self):
        """Start the current round of matches"""
        current_matches = self.get_current_matches()
        
        if not current_matches:
            return
        
        # Send round start announcement
        embed = discord.Embed(
            title=f"⚔️ Tournament Round {self.current_round} Starting!",
            description=f"Round {self.current_round} of {self.max_rounds} begins now!\n\n**Matches this round:**",
            color=discord.Color.blue()
        )
        
        for match in current_matches:
            p1_name = match.player1.display_name if match.player1 else match.npc1.name
            p2_name = match.player2.display_name if match.player2 else match.npc2.name if hasattr(match, 'npc2') else "BYE"
            embed.add_field(
                name=f"Match {match.match_id}",
                value=f"{p1_name} vs {p2_name}",
                inline=False
            )
        
        embed.set_footer(text=f"Next round in {self.round_break_minutes} minutes")
        await self.channel.send(embed=embed)
        
        # Start all matches
        for match in current_matches:
            if match.is_ready():
                await self.start_match(match)
    
    async def start_match(self, match: TournamentMatch):
        """Start a tournament match"""
        try:
            # Handle NPC matches
            if hasattr(match, 'npc1') and match.npc1:
                # NPC vs Player or NPC vs NPC
                if match.player2 and not hasattr(match, 'npc2'):
                    # Player vs NPC
                    await self.start_npc_battle(match)
                elif hasattr(match, 'npc2') and match.npc2:
                    # NPC vs NPC - simulate
                    await self.simulate_npc_battle(match)
            elif match.player1 and match.player2:
                # Player vs Player
                battle_view = TournamentBattleView(self.bot, match.player1, match.player2, match, self)
                match.battle_view = battle_view
            else:
                # Bye - player advances automatically
                if match.player1:
                    match.set_winner(match.player1)
                elif hasattr(match, 'npc1') and match.npc1:
                    match.set_winner(match.npc1)
                
        except Exception as e:
            logger.error(f"Error starting tournament match {match.match_id}: {e}")
    
    async def start_npc_battle(self, match: TournamentMatch):
        """Start a battle between a player and NPC"""
        from Systems.Pets.PetGames.battle_system import UnifiedBattleView
        
        # Create NPC battle
        npc_data = match.npc1.npc_data
        player = match.player2
        
        # Convert NPC data to monster format
        monster_data = {
            "name": match.npc1.name,
            "species": npc_data.get("species", "Dragon"),
            "element": npc_data.get("element", "Fire"),
            "level": npc_data.get("level", 10),
            "health": 100 + (npc_data.get("level", 10) * 10),
            "attack": 10 + (npc_data.get("level", 10) * 2),
            "defense": 5 + (npc_data.get("level", 10) * 1)
        }
        
        # Create battle view
        battle_view = UnifiedBattleView(
            ctx=None,  # We'll need to handle this differently
            battle_type="solo",
            monster=monster_data,
            selected_enemy_type=npc_data.get("species", "Dragon").lower(),
            selected_rarity="common",
            wild_encounter=False,
            is_boss_battle=False
        )
        
        # TODO: Integrate with existing battle system
        # This is a placeholder - need to integrate with existing battle system
    
    async def simulate_npc_battle(self, match: TournamentMatch):
        """Simulate a battle between two NPCs"""
        npc1 = match.npc1
        npc2 = match.npc2
        
        # Simple simulation based on NPC levels
        npc1_power = npc1.npc_data.get("level", 10)
        npc2_power = npc2.npc_data.get("level", 10)
        
        # Add some randomness
        npc1_roll = random.uniform(0.8, 1.2) * npc1_power
        npc2_roll = random.uniform(0.8, 1.2) * npc2_power
        
        if npc1_roll > npc2_roll:
            match.set_winner(npc1)
            winner_name = npc1.name
        else:
            match.set_winner(npc2)
            winner_name = npc2.name
        
        # Send result
        embed = discord.Embed(
            title=f"🤖 NPC Battle Complete - {match.match_id}",
            description=f"**{npc1.name}** vs **{npc2.name}**\n\n🏆 **Winner: {winner_name}**",
            color=discord.Color.blue()
        )
        await self.channel.send(embed=embed)
        
        # Progress tournament
        await self.handle_match_completion(match)
    
    async def schedule_next_round(self):
        """Schedule the next round after the break period"""
        if self.current_round >= self.max_rounds:
            self.status = TournamentStatus.COMPLETED
            return
        
        # Send round break announcement
        embed = discord.Embed(
            title=f"⏳ Tournament Round {self.current_round} Complete",
            description=f"Round {self.current_round} has finished!\n\nNext round begins in {self.round_break_minutes} minutes.",
            color=discord.Color.orange()
        )
        
        # Show current bracket
        embed.add_field(
            name="Current Bracket",
            value=self.get_bracket_display(),
            inline=False
        )
        
        await self.channel.send(embed=embed)
        
        # Schedule next round
        self.round_timer_task = asyncio.create_task(self._round_timer())
    
    async def _round_timer(self):
        """Timer for round breaks"""
        await asyncio.sleep(self.round_break_minutes * 60)
        
        # Advance to next round
        self.advance_round()
        
        # Start next round
        await self.start_round()
    
    def advance_round(self):
        """Advance to the next round of the tournament"""
        if self.current_round >= self.max_rounds:
            self.status = TournamentStatus.COMPLETED
            return
        
        # Get winners from current round
        current_round_matches = [m for m in self.matches.values() if m.round_num == self.current_round]
        winners = []
        
        for match in current_round_matches:
            if match.completed and match.winner:
                winners.append(match.winner)
        
        if len(winners) < len(current_round_matches):
            raise ValueError("Not all matches in current round are completed")
        
        # Create next round matches
        self.current_round += 1
        match_count = 0
        
        for i in range(0, len(winners), 2):
            match_id = f"R{self.current_round}M{match_count + 1}"
            
            # Determine participants
            p1 = winners[i]
            p2 = winners[i + 1] if i + 1 < len(winners) else None
            
            match = TournamentMatch(
                match_id=match_id,
                round_num=self.current_round,
                player1=p1 if isinstance(p1, discord.Member) else None,
                player2=p2 if p2 and isinstance(p2, discord.Member) else None
            )
            
            # Handle NPC winners
            if not isinstance(p1, discord.Member):
                match.npc1 = p1
            if p2 and not isinstance(p2, discord.Member):
                match.npc2 = p2
            
            self.matches[match_id] = match
            match_count += 1
        
        # Check if tournament is complete
        if self.current_round > self.max_rounds:
            self.status = TournamentStatus.COMPLETED
    
    def get_current_matches(self) -> List[TournamentMatch]:
        """Get matches for the current round"""
        return [m for m in self.matches.values() if m.round_num == self.current_round and not m.completed]
    
    def get_champion(self):
        """Get the tournament champion"""
        if self.status != TournamentStatus.COMPLETED:
            return None
        
        final_matches = [m for m in self.matches.values() if m.round_num == self.max_rounds]
        if final_matches and final_matches[0].completed:
            return final_matches[0].winner
        return None
    
    def get_bracket_display(self) -> str:
        """Generate a compact text representation of the tournament bracket"""
        if not self.matches:
            return "No bracket generated yet."
        
        bracket_text = f"🏆 **{self.size.value}P Tournament** | Round {self.current_round}/{self.max_rounds}\n\n"
        
        # Only show current round and completed rounds to save space
        for round_num in range(1, self.current_round + 1):
            round_matches = [m for m in self.matches.values() if m.round_num == round_num]
            if not round_matches:
                continue
                
            # Compact round headers
            if round_num == self.max_rounds:
                bracket_text += f"🏆 **FINAL**\n"
            elif round_num == self.max_rounds - 1:
                bracket_text += f"🥉 **SEMIS**\n"
            else:
                bracket_text += f"⚔️ **R{round_num}**\n"
            
            for match in round_matches:
                p1_name = ""
                p2_name = ""
                
                if match.player1:
                    p1_name = match.player1.display_name[:12]
                elif hasattr(match, 'npc1'):
                    p1_name = f"🤖{match.npc1.name[:10]}"
                
                if match.player2:
                    p2_name = match.player2.display_name[:12]
                elif hasattr(match, 'npc2'):
                    p2_name = f"🤖{match.npc2.name[:10]}"
                elif not match.player2 and not hasattr(match, 'npc2'):
                    p2_name = "BYE"
                
                if match.completed:
                    winner_name = ""
                    if match.winner:
                        if isinstance(match.winner, discord.Member):
                            winner_name = match.winner.display_name[:12]
                        else:
                            winner_name = f"🤖{match.winner.name[:10]}"
                    
                    bracket_text += f"✅ **{winner_name}** advances\n"
                else:
                    if p2_name:
                        bracket_text += f"🔴 {p1_name} vs {p2_name}\n"
                    else:
                        bracket_text += f"🎯 {p1_name} (Bye)\n"
        
        if self.status == TournamentStatus.COMPLETED:
            champion = self.get_champion()
            if champion:
                if isinstance(champion, discord.Member):
                    champ_name = champion.display_name
                else:
                    champ_name = champion.name
                bracket_text += f"\n🎉 **CHAMPION: {champ_name}** 🎉"
        
        return bracket_text
    
    async def handle_match_completion(self, completed_match: TournamentMatch):
        """Handle completion of a tournament match"""
        try:
            # Check if all matches in current round are complete
            current_round_matches = [m for m in self.matches.values() if m.round_num == self.current_round]
            all_complete = all(m.completed for m in current_round_matches)
            
            # Send updated bracket
            embed = discord.Embed(
                title="🏆 Tournament Bracket Updated",
                description=self.get_bracket_display(),
                color=discord.Color.gold()
            )
            await self.channel.send(embed=embed)
            
            if all_complete:
                if self.current_round >= self.max_rounds:
                    # Tournament is complete
                    self.status = TournamentStatus.COMPLETED
                    champion = self.get_champion()
                    
                    # Give rewards to champion
                    if champion and isinstance(champion, discord.Member):
                        try:
                            tournament_bonus_xp = 2000 * self.max_rounds  # Scale with tournament size
                            leveled_up, details = await add_experience(champion.id, tournament_bonus_xp, "tournament", None)
                            if leveled_up and details is not None:
                                await send_level_up_embed(champion.id, details, self.channel)
                        except Exception as e:
                            logger.error(f"Error applying tournament champion XP: {e}")
                    
                    champion_name = ""
                    if champion:
                        if isinstance(champion, discord.Member):
                            champion_name = champion.display_name
                        else:
                            champion_name = champion.name
                    
                    embed = discord.Embed(
                        title="🎉 TOURNAMENT COMPLETE! 🎉",
                        description=f"**🏆 CHAMPION: {champion_name}** 🏆\n\n{self.get_bracket_display()}",
                        color=discord.Color.gold()
                    )
                    
                    if isinstance(champion, discord.Member):
                        embed.add_field(
                            name="🎁 Champion Rewards",
                            value=f"• {2000 * self.max_rounds} Bonus XP\n• Tournament Glory\n• Bragging Rights",
                            inline=False
                        )
                    
                    await self.channel.send(embed=embed)
                else:
                    # Schedule next round
                    await self.schedule_next_round()
            
        except Exception as e:
            logger.error(f"Error handling match completion: {e}")
            await self.channel.send("❌ Error processing tournament match completion.")

class TournamentInvitationView(discord.ui.View):
    """View for tournament invitation DMs"""
    
    def __init__(self, tournament: AdvancedTournament, participant_id: str):
        super().__init__(timeout=1800)  # 30 minute timeout
        self.tournament = tournament
        self.participant_id = participant_id
    
    @discord.ui.button(label="Accept ✅", style=discord.ButtonStyle.success)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        participant = self.tournament.participants.get(self.participant_id)
        if not participant or participant.type != ParticipantType.PLAYER:
            await interaction.response.send_message("Invalid invitation.", ephemeral=True)
            return
        
        if participant.user != interaction.user:
            await interaction.response.send_message("This invitation is not for you.", ephemeral=True)
            return
        
        participant.accept_invitation()
        
        # Update tournament channel
        embed = discord.Embed(
            title="✅ Tournament Invitation Accepted",
            description=f"{participant.mention} has accepted the tournament invitation!",
            color=discord.Color.green()
        )
        
        accepted_count = len([p for p in self.tournament.participants.values() 
                             if p.accepted or p.type == ParticipantType.NPC])
        embed.add_field(
            name="Status",
            value=f"{accepted_count}/{self.tournament.size.value} participants accepted",
            inline=False
        )
        
        await self.tournament.channel.send(embed=embed)
        
        await interaction.response.edit_message(
            content="✅ You have accepted the tournament invitation!",
            embed=None,
            view=None
        )
        
        # Check if tournament can start
        if self.tournament.can_start():
            await self.tournament.channel.send(
                f"🎉 Tournament is now full! Use `/tournament start` to begin the tournament."
            )
    
    @discord.ui.button(label="Decline ❌", style=discord.ButtonStyle.danger)
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        participant = self.tournament.participants.get(self.participant_id)
        if not participant or participant.type != ParticipantType.PLAYER:
            await interaction.response.send_message("Invalid invitation.", ephemeral=True)
            return
        
        if participant.user != interaction.user:
            await interaction.response.send_message("This invitation is not for you.", ephemeral=True)
            return
        
        participant.decline_invitation()
        
        # Update tournament channel
        embed = discord.Embed(
            title="❌ Tournament Invitation Declined",
            description=f"{participant.mention} has declined the tournament invitation.",
            color=discord.Color.red()
        )
        
        await self.tournament.channel.send(embed=embed)
        
        await interaction.response.edit_message(
            content="❌ You have declined the tournament invitation.",
            embed=None,
            view=None
        )

class AdvancedTournamentView(discord.ui.View):
    """Main tournament view for Discord channel"""
    
    def __init__(self, tournament: AdvancedTournament):
        super().__init__(timeout=None)
        self.tournament = tournament
    
    @discord.ui.button(label="Join Tournament", style=discord.ButtonStyle.success, emoji="🎯")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.tournament.status != TournamentStatus.REGISTRATION:
            await interaction.response.send_message("❌ Tournament registration is closed.", ephemeral=True)
            return
        
        # Check if user has a pet
        try:
            pet_data = await user_data_manager.get_pet_data_async(str(interaction.user.id))
            if not pet_data:
                await interaction.response.send_message(
                    "❌ You need a pet to join tournaments! Use `/pet_shop` to get started.",
                    ephemeral=True
                )
                return
        except Exception as e:
            logger.error(f"Error checking pet data: {e}")
            await interaction.response.send_message("❌ Error checking your pet status.", ephemeral=True)
            return
        
        # Add participant
        added = self.tournament.add_participant(ParticipantType.PLAYER, interaction.user)
        if not added:
            await interaction.response.send_message("❌ Cannot join tournament (already joined or tournament full).", ephemeral=True)
            return
        
        await interaction.response.send_message(
            f"✅ You have joined the tournament! {len(self.tournament.participants)}/{self.tournament.size.value} participants.",
            ephemeral=True
        )
        
        # Update tournament message
        await self.update_tournament_message(interaction)
    
    @discord.ui.button(label="Invite Players", style=discord.ButtonStyle.primary, emoji="📨")
    async def invite_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.tournament.status != TournamentStatus.REGISTRATION:
            await interaction.response.send_message("❌ Cannot send invitations now.", ephemeral=True)
            return
        
        if interaction.user != self.tournament.organizer:
            await interaction.response.send_message("❌ Only the tournament organizer can send invitations.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Send invitations
        sent = await self.tournament.send_invitations(interaction.guild)
        success_count = sum(1 for s in sent.values() if s)
        
        await interaction.followup.send(
            f"📨 Sent {success_count} tournament invitation(s). Participants have 30 minutes to respond.",
            ephemeral=True
        )
    
    @discord.ui.button(label="Add NPCs", style=discord.ButtonStyle.secondary, emoji="🤖")
    async def add_npcs_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.tournament.status != TournamentStatus.REGISTRATION:
            await interaction.response.send_message("❌ Cannot add NPCs now.", ephemeral=True)
            return
        
        if interaction.user != self.tournament.organizer:
            await interaction.response.send_message("❌ Only the tournament organizer can add NPCs.", ephemeral=True)
            return
        
        # Calculate how many NPCs to add
        current_count = len(self.tournament.participants)
        slots_remaining = self.tournament.size.value - current_count
        
        if slots_remaining <= 0:
            await interaction.response.send_message("❌ Tournament is already full.", ephemeral=True)
            return
        
        # Add NPCs
        await self.tournament.generate_npc_participants(slots_remaining)
        
        await interaction.response.send_message(
            f"🤖 Added {min(slots_remaining, slots_remaining)} NPC participants.",
            ephemeral=True
        )
        
        # Update tournament message
        await self.update_tournament_message(interaction)
    
    @discord.ui.button(label="Start Tournament", style=discord.ButtonStyle.danger, emoji="⚔️")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.tournament.organizer:
            await interaction.response.send_message("❌ Only the tournament organizer can start the tournament.", ephemeral=True)
            return
        
        if not self.tournament.can_start():
            await interaction.response.send_message(
                f"❌ Tournament needs {self.tournament.size.value} participants to start. "
                f"Current: {len(self.tournament.get_accepted_participants())}/{self.tournament.size.value}",
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        
        # Generate bracket and start tournament
        self.tournament.generate_bracket()
        
        # Send tournament start announcement
        embed = discord.Embed(
            title="🏆 Tournament Starting!",
            description=f"**{self.tournament.size.value} Player Tournament**\n\n"
                       f"Organizer: {self.tournament.organizer.mention}\n"
                       f"Rounds: {self.tournament.max_rounds}\n"
                       f"Round breaks: {self.tournament.round_break_minutes} minutes\n\n"
                       f"{self.tournament.get_bracket_display()}",
            color=discord.Color.gold()
        )
        
        await interaction.followup.send(embed=embed)
        
        # Start first round
        await self.tournament.start_round()
    
    async def update_tournament_message(self, interaction: discord.Interaction):
        """Update the tournament message with current status"""
        embed = self.create_tournament_embed()
        
        try:
            await interaction.message.edit(embed=embed, view=self)
        except:
            pass  # Message might not be available
    
    def create_tournament_embed(self) -> discord.Embed:
        """Create tournament status embed"""
        embed = discord.Embed(
            title=f"🏆 {self.tournament.size.value} Player Tournament",
            description=f"Organized by {self.tournament.organizer.mention}",
            color=discord.Color.gold()
        )
        
        # Participant list
        players = []
        npcs = []
        
        for participant in self.tournament.participants.values():
            if participant.type == ParticipantType.PLAYER:
                status = "✅" if participant.accepted else "⏳"
                players.append(f"{status} {participant.mention}")
            else:
                npcs.append(f"🤖 {participant.name}")
        
        participants_text = "\n".join(players) if players else "No players yet"
        npcs_text = "\n".join(npcs) if npcs else "No NPCs"
        
        embed.add_field(
            name=f"Players ({len(players)}/{self.tournament.size.value})",
            value=participants_text[:1024],
            inline=False
        )
        
        if npcs:
            embed.add_field(
                name=f"NPCs ({len(npcs)})",
                value=npcs_text[:1024],
                inline=False
            )
        
        # Status info
        status_info = []
        status_info.append(f"**Status:** {self.tournament.status.value.upper()}")
        status_info.append(f"**Round breaks:** {self.tournament.round_break_minutes} minutes")
        status_info.append(f"**Invitation timeout:** {self.tournament.invitation_timeout_minutes} minutes")
        
        if self.tournament.status == TournamentStatus.INVITATION:
            pending = len([p for p in self.tournament.participants.values() 
                          if p.type == ParticipantType.PLAYER and not p.accepted])
            status_info.append(f"**Pending responses:** {pending}")
        
        embed.add_field(
            name="Tournament Info",
            value="\n".join(status_info),
            inline=False
        )
        
        embed.set_footer(text=f"Tournament ID: {self.tournament.id}")
        return embed