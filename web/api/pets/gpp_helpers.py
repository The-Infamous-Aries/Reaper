"""
GPP Pattern Helpers for Pet API Endpoints
=========================================
Helper functions to consistently apply GPP patterns across pet endpoints.
These helpers reduce code duplication and ensure consistent implementation
of cache invalidation, event queuing, and animation metadata generation.
"""

from typing import Dict, Any, Optional
from Systems.Pets.Logic.pet_components import AnimationComponent
from Systems.Pets.Logic.event_bus import EventQueue


# ── Cache invalidation helper (Object Pool pattern) ───────────────────────────
def _invalidate_stats_cache(pet: dict) -> None:
    """Invalidate the stats cache for a pet after data mutation."""
    if pet and "name" in pet:
        from Systems.Pets.Logic.pet_object_pool import stats_cache
        pet_name = pet.get("name")
        if pet_name:
            stats_cache.invalidate(pet_name)


# ── XP calculation helper ────────────────────────────────────────────────────────
def _compute_total_xp(pet: dict) -> int:
    """Calculate total XP (cumulative level XP + current level's remaining XP)."""
    from Systems.Pets.Logic.pet_brain import LootCalculator
    lvl = int(pet.get("level", 1))
    exp = int(pet.get("experience", 0))
    return int(LootCalculator.get_total_experience_for_level(lvl)) + exp


# ── User lock helper ───────────────────────────────────────────────────────────────
_user_locks: Dict[str, Any] = {}

def _get_user_lock(user_id: str) -> Any:
    """Get or create a per-user asyncio lock for preventing race conditions."""
    import asyncio
    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()
    return _user_locks[user_id]


async def apply_gpp_pattern(
    pet: Optional[Dict[str, Any]] = None,
    invalidate_cache: bool = False,
    event_name: Optional[str] = None,
    event_data: Optional[Dict[str, Any]] = None,
    animation_effect: str = "ui_update",
    animation_duration_ms: int = 500,
    animation_extra_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Apply GPP patterns consistently: cache invalidation, event queue, and animation.
    
    Args:
        pet: Pet data dict (required if invalidate_cache=True)
        invalidate_cache: Whether to invalidate the stats cache
        event_name: Event name to push (if None, no event is emitted)
        event_data: Event data to push with the event
        animation_effect: Animation effect name
        animation_duration_ms: Animation duration in milliseconds
        animation_extra_data: Optional additional data for animation payload
        
    Returns:
        Animation metadata dict
        
    Example:
        animation = await apply_gpp_pattern(
            pet=pet,
            invalidate_cache=True,
            event_name="item_equipped",
            event_data={"user_id": user_id, "item_name": item_name},
            animation_effect="equip_flash",
            animation_duration_ms=500
        )
    """
    # Cache invalidation
    if invalidate_cache and pet is not None:
        _invalidate_stats_cache(pet)
    
    # Event queue
    if event_name is not None:
        queue = EventQueue()
        queue.push(event_name, event_data or {})
        await queue.flush()
    
    # Animation
    return AnimationComponent.for_ui_update(
        animation_effect,
        animation_duration_ms,
        animation_extra_data
    )


async def apply_gpp_readonly(
    event_name: str,
    event_data: Dict[str, Any],
    animation_effect: str = "ui_update",
    animation_duration_ms: int = 500,
    animation_extra_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Apply GPP patterns for read-only endpoints (no cache invalidation).
    
    Args:
        event_name: Event name to push
        event_data: Event data to push with the event
        animation_effect: Animation effect name
        animation_duration_ms: Animation duration in milliseconds
        animation_extra_data: Optional additional data for animation payload
        
    Returns:
        Animation metadata dict
        
    Example:
        animation = await apply_gpp_readonly(
            event_name="skill_draw",
            event_data={"user_id": user_id, "count": 5},
            animation_effect="skill_draw",
            animation_duration_ms=600
        )
    """
    return await apply_gpp_pattern(
        pet=None,
        invalidate_cache=False,
        event_name=event_name,
        event_data=event_data,
        animation_effect=animation_effect,
        animation_duration_ms=animation_duration_ms,
        animation_extra_data=animation_extra_data
    )
