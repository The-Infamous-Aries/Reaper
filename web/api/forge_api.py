"""
Forge / Reforge API
===================
POST /api/pets/reforge

Rules:
- User picks ONE item to reforge.  The item can be plain (reforge_level 0) or
  already reforged (reforge_level N).  Either way they need ≥5 copies of that
  exact stack (same name + type + reforge_level).
  Excluded types: Potion, Key, Chest.
- User picks THREE sacrifice items (any non-Potion/Key/Chest item from inventory,
  each must have ≥1 copy).
- User picks 1–6 stats (ATT DEF DEX INT HAP ENE) to distribute new points to.
- The reforge item's total stat points (sum of all bonuses) are multiplied by 5
  and distributed evenly across the chosen stats (remainder goes to the first stat).
- The 5 copies of the reforge item are consumed.
- The 3 sacrifice items are consumed (1 copy each).
- A new "reforged" item is created with:
    - Same name, emoji_file, rarity, type as the original
    - New bonuses = distributed points
    - reforge_level = source reforge_level + 1
    - reforged = True flag
- The new item is added to inventory.

Progression example:
  5× plain Jlum (Lv.0)  → 1× Jlum Lv.1
  5× Jlum Lv.1          → 1× Jlum Lv.2
  5× Jlum Lv.2          → 1× Jlum Lv.3
  … and so on.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.event_bus import EventQueue
from Systems.Pets.Logic.pet_components import AnimationComponent
from web.api.pets.gpp_helpers import _invalidate_stats_cache

logger = logging.getLogger("forge_api")
router = APIRouter()

# Item types that cannot be used in the forge at all
_EXCLUDED_TYPES = {"Potion", "Key", "Chest"}

# All valid stat keys
_VALID_STATS = ["ATT", "DEF", "DEX", "INT", "HAP", "ENE"]


def _consolidate(inventory: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge duplicate stacks into single entries.

    Reforged items are kept separate from plain items, and different reforge
    levels are kept separate from each other.  The key is therefore:
        (name, type, reforged_flag, reforge_level)
    so that e.g. 3× plain "Jlum" and 1× reforged Lv.1 "Jlum" remain two
    distinct stacks rather than being collapsed into one.
    """
    merged: Dict[tuple, Dict[str, Any]] = {}
    for item in inventory:
        reforged = bool(item.get("reforged", False))
        rl = int(item.get("reforge_level", 0)) if reforged else 0
        key = (item.get("name", ""), item.get("type", ""), reforged, rl)
        if key in merged:
            merged[key]["count"] = merged[key].get("count", 1) + item.get("count", 1)
        else:
            merged[key] = dict(item)
            merged[key]["count"] = item.get("count", 1)
    return list(merged.values())


def _get_item_total_stat_points(item: Dict[str, Any]) -> int:
    """Sum all stat bonus values on an item."""
    bonuses = item.get("bonuses") or {}
    return sum(int(v) for v in bonuses.values() if isinstance(v, (int, float)))


def _distribute_points(total: int, stats: List[str]) -> Dict[str, int]:
    """Distribute `total` points evenly across `stats`. Remainder goes to first stat."""
    if not stats:
        return {}
    per_stat = total // len(stats)
    remainder = total % len(stats)
    result = {s: per_stat for s in stats}
    result[stats[0]] += remainder
    return result


def _get_canonical_item(name: str, item_type: str) -> Optional[Dict[str, Any]]:
    """Look up the canonical item definition from equipment.json."""
    try:
        from Systems.Functions.user_data_manager import user_data_manager as _udm
        eq_data = _udm.file_manager.get_data("equipment")
        type_section_map = {
            "Material": "Materials", "Gem": "Gems", "Monster": "Monsters",
            "Hat": "Hats", "Ring": "Rings", "Helmet": "Helmets",
            "Armor": "Armor", "Boots": "Boots", "Shield": "Shields",
            "Dagger": "Daggers", "Katana": "Katanas", "Sword": "Swords",
            "Axe": "Axes", "Hammer": "Hammers", "Bow": "Bows",
        }
        section = type_section_map.get(item_type, item_type + "s")
        for item in eq_data.get(section, []):
            if item.get("name", "").lower() == name.lower():
                return item
    except Exception:
        pass
    return None


@router.get("/pets/forge/eligible-items")
async def get_eligible_items(request: Request):
    """
    Return inventory items eligible for reforging (≥5 copies, not Potion/Key/Chest)
    and items eligible as sacrifices (≥1 copy, not Potion/Key/Chest).
    """
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    try:
        pet = await user_data_manager.get_pet_data_async(user_id)
        if not pet:
            return JSONResponse(content={"error": "No pet found"}, status_code=404)

        inventory = _consolidate(pet.get("inventory", []))

        reforge_candidates = []
        sacrifice_candidates = []

        for item in inventory:
            itype = item.get("type", "")
            if itype in _EXCLUDED_TYPES:
                continue
            count = item.get("count", 1)
            # Enrich with canonical data (bonuses, emoji_file, rarity)
            canonical = _get_canonical_item(item.get("name", ""), itype)
            enriched = {
                "name": item.get("name", ""),
                "type": itype,
                "rarity": item.get("rarity") or (canonical.get("rarity") if canonical else "Common"),
                "count": count,
                "bonuses": item.get("bonuses") or (canonical.get("bonuses") if canonical else {}),
                "emoji_file": item.get("emoji_file") or (canonical.get("emoji_file") if canonical else ""),
                "reforge_level": item.get("reforge_level", 0),
                "reforged": item.get("reforged", False),
            }
            # Any stack with ≥5 copies can be reforged (plain OR already-reforged)
            if count >= 5:
                reforge_candidates.append(enriched)
            if count >= 1:
                sacrifice_candidates.append(enriched)

        return JSONResponse(content={
            "reforge_candidates": reforge_candidates,
            "sacrifice_candidates": sacrifice_candidates,
        })

    except Exception as e:
        logger.error(f"get_eligible_items error: {e}", exc_info=True)
        return JSONResponse(content={"error": str(e)}, status_code=500)


@router.post("/pets/reforge")
async def reforge_item(request: Request):
    """
    Perform a reforge.

    Body:
    {
        "reforge_item": {"name": "Steel", "type": "Material"},
        "sacrifice_items": [
            {"name": "Gold", "type": "Material"},
            {"name": "Wirm", "type": "Monster"},
            {"name": "Ember Heart", "type": "Gem"}
        ],
        "target_stats": ["ATT", "DEF", "DEX"]
    }
    """
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(content={"error": "Invalid JSON body"}, status_code=400)

    reforge_spec = body.get("reforge_item")
    sacrifice_specs = body.get("sacrifice_items", [])
    target_stats = body.get("target_stats", [])

    # ── Validate inputs ───────────────────────────────────────────────────────
    if not reforge_spec or not isinstance(reforge_spec, dict):
        return JSONResponse(content={"error": "reforge_item is required"}, status_code=400)

    if len(sacrifice_specs) != 3:
        return JSONResponse(content={"error": "Exactly 3 sacrifice items are required"}, status_code=400)

    if not target_stats or not isinstance(target_stats, list):
        return JSONResponse(content={"error": "target_stats is required"}, status_code=400)

    target_stats = [s.upper() for s in target_stats]
    invalid_stats = [s for s in target_stats if s not in _VALID_STATS]
    if invalid_stats:
        return JSONResponse(content={"error": f"Invalid stats: {invalid_stats}"}, status_code=400)

    if len(target_stats) < 1 or len(target_stats) > 6:
        return JSONResponse(content={"error": "Choose 1–6 stats"}, status_code=400)

    # Deduplicate target stats while preserving order
    seen = set()
    deduped_stats = []
    for s in target_stats:
        if s not in seen:
            seen.add(s)
            deduped_stats.append(s)
    target_stats = deduped_stats

    reforge_name = reforge_spec.get("name", "").strip()
    reforge_type = reforge_spec.get("type", "").strip()
    # The client sends the exact reforge_level of the stack being consumed so we
    # can distinguish plain (level 0) from already-reforged (level N) copies.
    reforge_source_level = int(reforge_spec.get("reforge_level", 0))
    reforge_source_is_reforged = bool(reforge_spec.get("reforged", False)) or reforge_source_level > 0

    if not reforge_name or not reforge_type:
        return JSONResponse(content={"error": "reforge_item must have name and type"}, status_code=400)

    if reforge_type in _EXCLUDED_TYPES:
        return JSONResponse(content={"error": f"Cannot reforge {reforge_type} items"}, status_code=400)

    for sac in sacrifice_specs:
        if not isinstance(sac, dict) or not sac.get("name") or not sac.get("type"):
            return JSONResponse(content={"error": "Each sacrifice item must have name and type"}, status_code=400)
        if sac.get("type") in _EXCLUDED_TYPES:
            return JSONResponse(content={"error": f"Cannot sacrifice {sac.get('type')} items"}, status_code=400)

    # ── Load pet and inventory ────────────────────────────────────────────────
    try:
        pet = await user_data_manager.get_pet_data_async(user_id)
        if not pet:
            return JSONResponse(content={"error": "No pet found"}, status_code=404)

        inventory = _consolidate(pet.get("inventory", []))

        # ── Find the reforge item stack ───────────────────────────────────────
        # Match by name + type + exact reforge_level so plain and reforged stacks
        # are never confused with each other.
        reforge_idx = next(
            (i for i, it in enumerate(inventory)
             if it.get("name", "").lower() == reforge_name.lower()
             and it.get("type", "") == reforge_type
             and int(it.get("reforge_level", 0)) == reforge_source_level
             and bool(it.get("reforged", False)) == reforge_source_is_reforged),
            None
        )
        if reforge_idx is None:
            level_desc = f"Lv.{reforge_source_level}" if reforge_source_is_reforged else "plain"
            return JSONResponse(
                content={"error": f"'{reforge_name}' ({level_desc}) not found in inventory"},
                status_code=400
            )

        reforge_stack = inventory[reforge_idx]
        if reforge_stack.get("count", 1) < 5:
            level_desc = f"Lv.{reforge_source_level}" if reforge_source_is_reforged else "plain"
            return JSONResponse(
                content={"error": f"Need 5× '{reforge_name}' ({level_desc}) — have {reforge_stack.get('count', 1)}"},
                status_code=400
            )

        # ── Validate sacrifices (track counts needed per item) ────────────────
        # Build a working copy of counts keyed by (lowercased name, type, reforged, reforge_level)
        # matching the _consolidate key so each distinct stack is tracked separately.
        working_counts: Dict[tuple, int] = {
            (it.get("name", "").lower(), it.get("type", ""),
             bool(it.get("reforged", False)), int(it.get("reforge_level", 0)) if it.get("reforged") else 0
            ): it.get("count", 1)
            for it in inventory
        }

        # Deduct 5 from the reforge item stack (keyed by exact level)
        rf_actual_key = (reforge_name.lower(), reforge_type, reforge_source_is_reforged, reforge_source_level)
        if rf_actual_key not in working_counts:
            level_desc = f"Lv.{reforge_source_level}" if reforge_source_is_reforged else "plain"
            return JSONResponse(content={"error": f"'{reforge_name}' ({level_desc}) not found"}, status_code=400)
        working_counts[rf_actual_key] -= 5

        # Validate and deduct each sacrifice — sacrifices can be plain or reforged;
        # prefer the plain stack first, fall back to any matching stack.
        for sac in sacrifice_specs:
            sac_name = sac.get("name", "").strip()
            sac_type = sac.get("type", "").strip()
            # Try plain stack first, then any reforged stack
            sac_key = next(
                (k for k in working_counts
                 if k[0] == sac_name.lower() and k[1] == sac_type and working_counts[k] >= 1),
                None
            )
            if sac_key is None:
                return JSONResponse(
                    content={"error": f"Sacrifice item '{sac_name}' not found in inventory"},
                    status_code=400
                )
            if working_counts[sac_key] < 1:
                return JSONResponse(
                    content={"error": f"Not enough copies of '{sac_name}' for sacrifice"},
                    status_code=400
                )
            working_counts[sac_key] -= 1

        # ── Calculate new stats ───────────────────────────────────────────────
        # For plain items: use canonical bonuses as the base.
        # For already-reforged items: use the item's current bonuses (the redistributed ones).
        canonical = _get_canonical_item(reforge_name, reforge_type)
        if reforge_source_is_reforged:
            # Use the reforged item's actual current bonuses as the base
            base_bonuses = reforge_stack.get("bonuses") or (canonical.get("bonuses") if canonical else {})
        else:
            # Plain item — use canonical bonuses
            base_bonuses = (canonical.get("bonuses") if canonical else {}) or reforge_stack.get("bonuses") or {}

        total_points = _get_item_total_stat_points({"bonuses": base_bonuses})
        if total_points <= 0:
            total_points = len(target_stats)

        new_total = total_points * 5
        new_bonuses = _distribute_points(new_total, target_stats)

        # ── Build the new reforged item ───────────────────────────────────────
        new_reforge_level = reforge_source_level + 1

        emoji_file = reforge_stack.get("emoji_file") or (canonical.get("emoji_file") if canonical else "")
        rarity = reforge_stack.get("rarity") or (canonical.get("rarity") if canonical else "Common")
        # Preserve set tag from canonical item or existing reforged item so set bonuses still apply
        set_tag = reforge_stack.get("set") or (canonical.get("set") if canonical else None)

        new_item: Dict[str, Any] = {
            "name": reforge_name,
            "type": reforge_type,
            "rarity": rarity,
            "emoji_file": emoji_file,
            "bonuses": new_bonuses,
            "reforged": True,
            "reforge_level": new_reforge_level,
            "count": 1,
        }
        if set_tag:
            new_item["set"] = set_tag

        # ── Apply inventory changes ───────────────────────────────────────────
        # Deduct 5 from the source reforge stack (matched by exact level)
        reforge_stack["count"] -= 5
        if reforge_stack["count"] <= 0:
            inventory.pop(reforge_idx)

        # Deduct 1 from each sacrifice — prefer plain (non-reforged) stack first
        for sac in sacrifice_specs:
            sac_name = sac.get("name", "").strip()
            sac_type = sac.get("type", "").strip()
            # Try plain stack first, then any reforged stack
            target_i = next(
                (i for i, it in enumerate(inventory)
                 if it.get("name", "").lower() == sac_name.lower()
                 and it.get("type", "") == sac_type
                 and not it.get("reforged", False)
                 and it.get("count", 1) >= 1),
                None
            )
            if target_i is None:
                target_i = next(
                    (i for i, it in enumerate(inventory)
                     if it.get("name", "").lower() == sac_name.lower()
                     and it.get("type", "") == sac_type
                     and it.get("count", 1) >= 1),
                    None
                )
            if target_i is not None:
                inventory[target_i]["count"] = inventory[target_i].get("count", 1) - 1
                if inventory[target_i]["count"] <= 0:
                    inventory.pop(target_i)

        # Add the new reforged item (stack with existing reforged copy if same name+type+reforge_level)
        existing_reforged = next(
            (it for it in inventory
             if it.get("name", "").lower() == reforge_name.lower()
             and it.get("type", "") == reforge_type
             and it.get("reforged") is True
             and it.get("reforge_level", 0) == new_reforge_level),
            None
        )
        if existing_reforged:
            existing_reforged["count"] = existing_reforged.get("count", 1) + 1
            # Update bonuses to the latest reforge (they should be the same if same level)
            existing_reforged["bonuses"] = new_bonuses
            # Ensure set tag is preserved (may have been missing from older reforged stacks)
            if set_tag:
                existing_reforged["set"] = set_tag
        else:
            inventory.append(new_item)

        pet["inventory"] = inventory
        await user_data_manager.save_pet_data(user_id, pet.get("name", "Pet"), pet)

        # ── GPP: Cache invalidation after pet data mutation ──────────────────────────
        _invalidate_stats_cache(pet)

        # Re-fetch enriched pet
        from web.api.pets_api import _enrich_pet
        refreshed = _enrich_pet(await user_data_manager.get_pet_data_async(user_id))

        logger.info(
            f"Reforge: user={user_id} item={reforge_name}({reforge_type}) "
            f"source_level={reforge_source_level} -> reforge_level={new_reforge_level} "
            f"stats={target_stats} total_points={new_total} bonuses={new_bonuses}"
        )

        # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
        queue = EventQueue()
        queue.push("forge_reforge", {"user_id": user_id, "item_name": reforge_name, "reforge_level": new_reforge_level})
        await queue.flush()

        animation = AnimationComponent.for_ui_update("reforge_complete", 600)

        return JSONResponse(content={
            "success": True,
            "reforged_item": new_item,
            "new_bonuses": new_bonuses,
            "total_points": new_total,
            "reforge_level": new_reforge_level,
            "pet": refreshed,
            "animation": animation
        })

    except Exception as e:
        logger.error(f"reforge_item error: {e}", exc_info=True)
        return JSONResponse(content={"error": str(e)}, status_code=500)
