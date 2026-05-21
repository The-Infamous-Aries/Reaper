"""
GPP State Pattern — Pet Activity State Machine
===============================================
Represents each pet activity as a proper State object instead of scattered
if/elif chains.  Each state knows:

  - What it does when entered  (on_enter)
  - What it does each "tick"   (update) — for future real-time use
  - What it does when exited   (on_exit)
  - Which transitions are valid

The PetStateMachine holds the current state and enforces valid transitions.

States:
    IdleState        — pet is available for any action
    TrainingState    — pet is training a stat
    MissionState     — pet is on a mission
    PlayingState     — pet is playing at a location
    QuestState       — pet is on a quest
    BattleState      — pet is in a battle
    DungeonState     — pet is in a dungeon
    ColosseumState   — pet is in the colosseum

Usage:
    from Systems.Pets.Logic.pet_state_machine import PetStateMachine

    sm = PetStateMachine(pet)
    sm.transition_to("training")   # raises if invalid
    sm.current_state_name          # "training"
    sm.can_transition_to("mission") # False — already busy
    sm.transition_to("idle")       # back to idle after action completes
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Set

logger = logging.getLogger("pet_state_machine")


# ─────────────────────────────────────────────────────────────────────────────
# Base State
# ─────────────────────────────────────────────────────────────────────────────

class PetState:
    """Abstract base for all pet activity states."""

    name: str = "base"

    # States that this state can transition TO
    valid_transitions: Set[str] = set()

    def on_enter(self, pet: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> None:
        """Called when the state machine enters this state."""
        pet["activity_state"] = self.name

    def on_exit(self, pet: Dict[str, Any]) -> None:
        """Called when the state machine leaves this state."""
        pass

    def update(self, pet: Dict[str, Any], delta_ms: float = 0.0) -> None:
        """
        Called each game-loop tick (future real-time use).
        delta_ms = milliseconds since last tick.
        """
        pass

    def __repr__(self) -> str:
        return f"<PetState:{self.name}>"


# ─────────────────────────────────────────────────────────────────────────────
# Concrete States
# ─────────────────────────────────────────────────────────────────────────────

class IdleState(PetState):
    name = "idle"
    valid_transitions = {"training", "on_mission", "playing", "on_quest", "in_battle", "in_dungeon", "in_colosseum"}

    def on_enter(self, pet: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> None:
        super().on_enter(pet, context)
        # Clear any stale activity context
        pet.pop("activity_context", None)


class TrainingState(PetState):
    name = "training"
    valid_transitions = {"idle"}

    def on_enter(self, pet: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> None:
        super().on_enter(pet, context)
        if context:
            pet["activity_context"] = {
                "stat":       context.get("stat"),
                "difficulty": context.get("difficulty"),
            }

    def on_exit(self, pet: Dict[str, Any]) -> None:
        pet.pop("activity_context", None)


class MissionState(PetState):
    name = "on_mission"
    valid_transitions = {"idle"}

    def on_enter(self, pet: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> None:
        super().on_enter(pet, context)
        if context:
            pet["activity_context"] = {
                "difficulty": context.get("difficulty"),
                "gamble_xp":  context.get("gamble_xp", 0),
            }

    def on_exit(self, pet: Dict[str, Any]) -> None:
        pet.pop("activity_context", None)


class PlayingState(PetState):
    name = "playing"
    valid_transitions = {"idle", "in_battle"}

    def on_enter(self, pet: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> None:
        super().on_enter(pet, context)
        if context:
            pet["activity_context"] = {
                "location": context.get("location"),
            }

    def on_exit(self, pet: Dict[str, Any]) -> None:
        pet.pop("activity_context", None)


class QuestState(PetState):
    name = "on_quest"
    valid_transitions = {"idle", "in_battle"}

    def on_enter(self, pet: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> None:
        super().on_enter(pet, context)
        if context:
            pet["activity_context"] = {
                "location":   context.get("location"),
                "difficulty": context.get("difficulty"),
                "stage_idx":  0,
            }

    def on_exit(self, pet: Dict[str, Any]) -> None:
        pet.pop("activity_context", None)


class BattleState(PetState):
    name = "in_battle"
    valid_transitions = {"idle", "on_quest", "playing"}

    def on_enter(self, pet: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> None:
        super().on_enter(pet, context)
        if context:
            pet["activity_context"] = {
                "battle_type": context.get("battle_type", "npc"),
                "difficulty":  context.get("difficulty", "easy"),
                "turn":        0,
            }

    def on_exit(self, pet: Dict[str, Any]) -> None:
        pet.pop("activity_context", None)


class DungeonState(PetState):
    name = "in_dungeon"
    valid_transitions = {"idle"}

    def on_enter(self, pet: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> None:
        super().on_enter(pet, context)
        if context:
            pet["activity_context"] = {
                "floor": context.get("floor", 1),
            }

    def on_exit(self, pet: Dict[str, Any]) -> None:
        pet.pop("activity_context", None)


class ColosseumState(PetState):
    name = "in_colosseum"
    valid_transitions = {"idle"}

    def on_enter(self, pet: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> None:
        super().on_enter(pet, context)

    def on_exit(self, pet: Dict[str, Any]) -> None:
        pet.pop("activity_context", None)


# ─────────────────────────────────────────────────────────────────────────────
# State registry
# ─────────────────────────────────────────────────────────────────────────────

_STATE_REGISTRY: Dict[str, PetState] = {
    "idle":          IdleState(),
    "training":      TrainingState(),
    "on_mission":    MissionState(),
    "playing":       PlayingState(),
    "on_quest":      QuestState(),
    "in_battle":     BattleState(),
    "in_dungeon":    DungeonState(),
    "in_colosseum":  ColosseumState(),
}


def get_state(name: str) -> PetState:
    state = _STATE_REGISTRY.get(name)
    if state is None:
        raise ValueError(f"Unknown state '{name}'. Valid: {list(_STATE_REGISTRY)}")
    return state


# ─────────────────────────────────────────────────────────────────────────────
# PetStateMachine
# ─────────────────────────────────────────────────────────────────────────────

class PetStateMachine:
    """
    Manages the current activity state for a single pet.

    The machine is lightweight and stateless between requests — it reads
    and writes directly to the pet dict.  Instantiate it per-request:

        sm = PetStateMachine(pet)
        sm.transition_to("training", context={"stat": "ATT", "difficulty": "Easy"})
        # ... do training logic ...
        sm.transition_to("idle")
    """

    def __init__(self, pet: Dict[str, Any]) -> None:
        self._pet = pet
        # Ensure the pet has a valid state
        current = pet.get("activity_state", "idle")
        if current not in _STATE_REGISTRY:
            pet["activity_state"] = "idle"

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def current_state_name(self) -> str:
        return self._pet.get("activity_state", "idle")

    @property
    def current_state(self) -> PetState:
        return get_state(self.current_state_name)

    @property
    def is_idle(self) -> bool:
        return self.current_state_name == "idle"

    @property
    def is_busy(self) -> bool:
        return not self.is_idle

    # ── Transitions ───────────────────────────────────────────────────────────

    def can_transition_to(self, target: str) -> bool:
        """Return True if the current state allows transitioning to *target*."""
        if target not in _STATE_REGISTRY:
            return False
        return target in self.current_state.valid_transitions

    def transition_to(
        self,
        target: str,
        context: Optional[Dict[str, Any]] = None,
        force: bool = False,
    ) -> None:
        """
        Transition to *target* state.

        Raises ValueError if the transition is invalid unless *force=True*.
        *context* is passed to the new state's on_enter method.
        """
        if not force and not self.can_transition_to(target):
            raise ValueError(
                f"Cannot transition from '{self.current_state_name}' to '{target}'. "
                f"Valid transitions: {self.current_state.valid_transitions}"
            )
        old_state = self.current_state
        new_state = get_state(target)

        old_state.on_exit(self._pet)
        new_state.on_enter(self._pet, context)

        logger.debug(
            "Pet %s: %s → %s",
            self._pet.get("name", "?"),
            old_state.name,
            new_state.name,
        )

    def reset_to_idle(self) -> None:
        """Force-reset to idle regardless of current state."""
        self.transition_to("idle", force=True)

    # ── Convenience guards ────────────────────────────────────────────────────

    def assert_idle(self, action_name: str = "this action") -> None:
        """Raise ValueError if the pet is not idle."""
        if not self.is_idle:
            raise ValueError(
                f"Cannot perform {action_name}: pet is currently '{self.current_state_name}'."
            )

    def update(self, delta_ms: float = 0.0) -> None:
        """Tick the current state (for future real-time use)."""
        self.current_state.update(self._pet, delta_ms)

    def __repr__(self) -> str:
        return f"<PetStateMachine pet={self._pet.get('name','?')} state={self.current_state_name}>"
