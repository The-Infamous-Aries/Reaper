"""
NewsWriter — Translates raw subscription events into news DB records.

The Grim Reaper watches all of Orbis and reports on events with the gravitas,
dark humor, and dramatic flair befitting Death himself. Every headline and
article body is written in-character: the Reaper is omniscient, sardonic,
occasionally sympathetic (especially toward the Darkstar), and always
theatrical.

Tone guide by event type:
  - NW city/project/infra build  → proud, excited, triumphant
  - NW military purchase         → approving, ominous for enemies
  - NW war declared (attacking)  → dramatic, war-cry energy
  - NW war won                   → celebratory, victorious
  - NW war lost / looted         → mournful, solemn, angry
  - NW hit by nuke/missile       → devastated, furious
  - Enemy hit by NW nuke/missile → gleeful, triumphant
  - Missile/nuke MISSED          → hilarious, mocking
  - Non-NW events                → neutral newspaper style with Reaper flavor
  - Alliance join/leave          → observational, sometimes ominous

Called from:
  - nations_subscription.py  → city/project/infra/land/military purchases
  - wars_subscription.py     → war declared, war ended, loot attacks, nukes/missiles
  - bankrecs_subscription.py → large bank transfers (optional, future)

All methods are async-safe and fire-and-forget (errors are logged, never raised).
"""

from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from PnWHarvester.db.news_db import get_news_db
from PnWHarvester.db.pnw_costs import (
    ALL_PROJECT_FIELDS,
    _PROJECT_DB_COL_TO_DISPLAY,
)

logger = logging.getLogger(__name__)

NW_ALLIANCE_ID = 10259

# ─────────────────────────────────────────────────────────────────────────────
# Load Reaper dialog pools from JSON file
# ─────────────────────────────────────────────────────────────────────────────

def _load_reaper_dialog() -> Dict[str, List[str]]:
    """Load Reaper dialog pools from JSON file."""
    dialog_file = Path(__file__).parent / "reaper_dialog.json"
    try:
        with open(dialog_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"Reaper dialog file not found: {dialog_file}, using empty defaults")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse reaper_dialog.json: {e}, using empty defaults")
        return {}

_REAPER_DIALOG = _load_reaper_dialog()

# Convert JSON keys to Python variable names for dialog pools
_NW_CITY_INTROS = _REAPER_DIALOG.get("nw_city_intros", [])
_CITY_INTROS = _REAPER_DIALOG.get("city_intros", [])
_NW_PROJECT_INTROS = _REAPER_DIALOG.get("nw_project_intros", [])
_PROJECT_INTROS = _REAPER_DIALOG.get("project_intros", [])
_NW_ATT_WAR_INTROS = _REAPER_DIALOG.get("nw_att_war_intros", [])
_NW_DEF_WAR_INTROS = _REAPER_DIALOG.get("nw_def_war_intros", [])
_WAR_DECLARED_INTROS = _REAPER_DIALOG.get("war_declared_intros", [])
_NW_WIN_INTROS = _REAPER_DIALOG.get("nw_win_intros", [])
_NW_LOSS_INTROS = _REAPER_DIALOG.get("nw_loss_intros", [])
_WAR_PEACE_INTROS = _REAPER_DIALOG.get("war_peace_intros", [])
_NW_LOOTED_INTROS = _REAPER_DIALOG.get("nw_looted_intros", [])
_NW_LOOT_INTROS = _REAPER_DIALOG.get("nw_loot_intros", [])
_LOOT_INTROS = _REAPER_DIALOG.get("loot_intros", [])
_NW_HIT_WMD_INTROS = _REAPER_DIALOG.get("nw_hit_wmd_intros", [])
_NW_FIRES_WMD_INTROS = _REAPER_DIALOG.get("nw_fires_wmd_intros", [])
_MISS_INTROS = _REAPER_DIALOG.get("miss_intros", [])
_NW_MIL_INTROS = _REAPER_DIALOG.get("nw_mil_intros", [])
_MIL_INTROS = _REAPER_DIALOG.get("mil_intros", [])
_NW_UPGRADE_INTROS = _REAPER_DIALOG.get("nw_upgrade_intros", [])
_UPGRADE_INTROS = _REAPER_DIALOG.get("upgrade_intros", [])
_NW_JOIN_INTROS = _REAPER_DIALOG.get("nw_join_intros", [])
_NW_LEAVE_INTROS = _REAPER_DIALOG.get("nw_leave_intros", [])
_ALLIANCE_CHANGE_INTROS = _REAPER_DIALOG.get("alliance_change_intros", [])
_BANK_INTROS = _REAPER_DIALOG.get("bank_intros", [])
_BANK_DEPOSIT_INTROS = _REAPER_DIALOG.get("bank_deposit_intros", [])
_BANK_WITHDRAWAL_INTROS = _REAPER_DIALOG.get("bank_withdrawal_intros", [])
_ALLIANCE_LOOT_INTROS = _REAPER_DIALOG.get("alliance_loot_intros", [])
_NW_TRADE_BUY_INTROS = _REAPER_DIALOG.get("nw_trade_buy_intros", [])
_NW_TRADE_SELL_INTROS = _REAPER_DIALOG.get("nw_trade_sell_intros", [])
_TRADE_INTROS = _REAPER_DIALOG.get("trade_intros", [])

# ─────────────────────────────────────────────────────────────────────────────
# Thresholds (configurable)
# ─────────────────────────────────────────────────────────────────────────────

# Minimum value thresholds for recording events to the news feed
CITY_UPGRADE_THRESHOLD = 500_000      # $500K minimum for city upgrades
MILITARY_PURCHASE_THRESHOLD = 100_000 # $100K minimum for military purchases
BANK_TRANSFER_THRESHOLD = 1_000_000   # $1M minimum for bank transfers
LOOT_ATTACK_THRESHOLD = 5_000_000      # $5M minimum for loot attacks


# ─────────────────────────────────────────────────────────────────────────────
# Utility helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _pick(items: List[str]) -> str:
    """Randomly select an item from a list."""
    return random.choice(items)


def _format_dialog(template: str, **kwargs) -> str:
    """Format a dialog template with placeholder substitution."""
    try:
        return template.format(**kwargs)
    except KeyError as e:
        # If a placeholder is missing, return the template as-is
        logger.warning(f"Missing placeholder {e} in dialog template: {template}")
        return template


def _fmt_money(val: float) -> str:
    if val >= 1_000_000_000:
        return f"${val/1_000_000_000:.2f}B"
    if val >= 1_000_000:
        return f"${val/1_000_000:.2f}M"
    if val >= 1_000:
        return f"${val/1_000:.0f}K"
    return f"${val:,.0f}"


def _fmt_price(val: float) -> str:
    """Format a unit price as a full dollar amount — no K/M abbreviation."""
    if val >= 1_000_000_000:
        return f"${val/1_000_000_000:.2f}B"
    if val >= 1_000_000:
        return f"${val/1_000_000:.2f}M"
    # Full number with commas — no K abbreviation
    return f"${val:,.0f}"


def _nation_label(nation_name: Optional[str], nation_id: Optional[int]) -> str:
    if nation_name:
        return nation_name
    if nation_id:
        return f"Nation #{nation_id}"
    return "Unknown Nation"


def _alliance_label(alliance_name: Optional[str], alliance_id: Optional[int]) -> str:
    if alliance_name:
        return alliance_name
    if alliance_id and int(alliance_id) != 0:
        return f"Alliance #{alliance_id}"
    return "No Alliance"


def _nation_token(nation_id: Optional[int], nation_name: Optional[str]) -> str:
    """Return a Nation #ID token for use in body text (frontend resolves to a link)."""
    if nation_id:
        return f"Nation #{nation_id}"
    return nation_name or "Unknown Nation"


def _alliance_token(alliance_id: Optional[int], alliance_name: Optional[str]) -> str:
    """Return an Alliance #ID token for use in body text (frontend resolves to a link).
    If the nation has no alliance (id=0 or None), returns empty string so callers
    can decide whether to show it at all."""
    if alliance_id and int(alliance_id) != 0:
        return f"Alliance #{alliance_id}"
    return ""  # no alliance — callers should omit the parens entirely


def _fetch_resource_prices() -> Dict[str, float]:
    """Fetch current resource sell prices from REAPER_DB.
    
    Returns a dictionary mapping resource names (lowercase) to their best sell prices.
    Returns empty dict on error."""
    try:
        import sqlite3 as _sqlite3
        from Systems.Functions.db_paths import REAPER_DB_STR
        _conn = _sqlite3.connect(REAPER_DB_STR)
        rows = _conn.execute(
            "SELECT resource, best_sell_price FROM resource_prices "
            "WHERE timestamp = (SELECT MAX(timestamp) FROM resource_prices)"
        ).fetchall()
        _conn.close()
        return {r.lower(): float(p) for r, p in rows if p and float(p) > 0}
    except Exception:
        return {}


def _calculate_resource_value(resource_costs: Optional[Dict[str, float]]) -> float:
    """Calculate the monetary value of resource costs using current market prices.
    
    Args:
        resource_costs: Dictionary mapping resource names to quantities
        
    Returns:
        Total monetary value of all resources at current sell prices
    """
    if not resource_costs:
        return 0.0
    
    resource_prices = _fetch_resource_prices()
    total_value = 0.0
    for res, amt in resource_costs.items():
        total_value += amt * resource_prices.get(res.lower(), 0.0)
    return total_value


def _validate_nation_data(nation_id: int, nation_name: Optional[str], alliance_id: Optional[int]) -> None:
    """Validate nation-related input data.
    
    Args:
        nation_id: Nation ID (must be positive)
        nation_name: Nation name (optional but recommended)
        alliance_id: Alliance ID (optional, can be 0 for no alliance)
        
    Raises:
        ValueError: If nation_id is invalid
    """
    if not isinstance(nation_id, int) or nation_id <= 0:
        raise ValueError(f"Invalid nation_id: {nation_id} (must be positive integer)")


def _validate_money_value(value: float, field_name: str) -> None:
    """Validate monetary value input.
    
    Args:
        value: Monetary value (must be non-negative)
        field_name: Name of the field for error message
        
    Raises:
        ValueError: If value is invalid
    """
    if not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"Invalid {field_name}: {value} (must be non-negative number)")


def _nation_with_alliance(nation_id: Optional[int], nation_name: Optional[str],
                           alliance_id: Optional[int], alliance_name: Optional[str]) -> str:
    """Return 'Nation #X (Alliance #Y)' or just 'Nation #X' if no alliance."""
    n = _nation_token(nation_id, nation_name)
    a = _alliance_token(alliance_id, alliance_name)
    return f"{n} ({a})" if a else n


def _is_nw(alliance_id: Optional[int]) -> bool:
    return bool(alliance_id and int(alliance_id) == NW_ALLIANCE_ID)


def _ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return {1: f"{n}st", 2: f"{n}nd", 3: f"{n}rd"}.get(n % 10, f"{n}th")


def _fmt_project(col: str) -> str:
    return _PROJECT_DB_COL_TO_DISPLAY.get(col) or col.replace("_", " ").title()


def _fmt_unit(unit_type: str, quantity: int) -> str:
    labels = {
        "soldiers": "soldiers",
        "tanks": "tanks",
        "aircraft": "aircraft",
        "ships": "ships",
        "missiles": "missiles",
        "nukes": "nuclear warheads",
        "spies": "spies",
    }
    return labels.get(unit_type, unit_type)


def _fmt_improvement(col: str) -> str:
    """Convert a DB column name to a human-readable improvement name."""
    return col.replace("_", " ").title()


# ── Resource formatting for body text ────────────────────────────────────────
# Body text is rendered as HTML in the browser.
# Use <img> tags pointing to /static/Emojis/Resources/ — NOT Discord emoji codes.
# Sell prices are fetched from reaper.db for accurate valuations.

# Display order for resources (most valuable / most interesting first)
_RESOURCE_ORDER = [
    "money", "uranium", "gasoline", "munitions", "steel", "aluminum",
    "oil", "iron", "bauxite", "lead", "coal", "food",
]

# Static image paths for resource icons (served from web/static/)
_RESOURCE_IMG: Dict[str, str] = {
    "food":      "/static/Emojis/Resources/food.png",
    "coal":      "/static/Emojis/Resources/coal.png",
    "oil":       "/static/Emojis/Resources/oil.png",
    "uranium":   "/static/Emojis/Resources/uranium.png",
    "iron":      "/static/Emojis/Resources/iron.png",
    "bauxite":   "/static/Emojis/Resources/bauxite.png",
    "lead":      "/static/Emojis/Resources/lead.png",
    "gasoline":  "/static/Emojis/Resources/gasoline.png",
    "munitions": "/static/Emojis/Resources/munitions.png",
    "steel":     "/static/Emojis/Resources/steel.png",
    "aluminum":  "/static/Emojis/Resources/aluminum.png",
}

_FALLBACK_PRICES: Dict[str, float] = {
    "coal": 2000, "oil": 2000, "uranium": 4000, "iron": 2000,
    "bauxite": 2000, "lead": 2000, "gasoline": 3000, "munitions": 2000,
    "steel": 3000, "aluminum": 2000, "food": 150,
}


def _res_img(resource: str) -> str:
    """Return an HTML <img> tag for a resource, or 💰 for money."""
    key = resource.lower()
    if key == "money":
        return "💰"
    src = _RESOURCE_IMG.get(key)
    if src:
        return f'<img src="{src}" alt="{resource.title()}" class="news-res-img">'
    return "📦"


def _get_resource_sell_prices() -> Dict[str, float]:
    """Fetch current best-sell prices from reaper.db. Returns {} on failure."""
    try:
        import sqlite3
        from Systems.Functions.db_paths import REAPER_DB_STR
        conn = sqlite3.connect(REAPER_DB_STR)
        rows = conn.execute(
            "SELECT resource, best_sell_price FROM resource_prices "
            "WHERE timestamp = (SELECT MAX(timestamp) FROM resource_prices)"
        ).fetchall()
        conn.close()
        return {r.lower(): float(p) for r, p in rows if p and float(p) > 0} if rows else {}
    except Exception:
        return {}


def _fmt_resource_amount(resource: str, amount: float) -> str:
    """Format a single resource amount with its static-folder icon (HTML)."""
    icon = _res_img(resource)
    if resource == "money":
        return f"{icon} {_fmt_money(amount)}"
    if amount >= 1_000_000:
        return f"{icon} {amount/1_000_000:.2f}M {resource.title()}"
    if amount >= 1_000:
        return f"{icon} {amount/1_000:.1f}K {resource.title()}"
    return f"{icon} {amount:,.1f} {resource.title()}"


def _fmt_resources(resources: Dict[str, float], threshold: float = 0.01) -> str:
    """Format a resource dict into an HTML string with icons, ordered by importance."""
    parts = []
    seen = set()
    for r in _RESOURCE_ORDER:
        v = resources.get(r, 0.0)
        if v >= threshold:
            parts.append(_fmt_resource_amount(r, v))
            seen.add(r)
    for r, v in resources.items():
        if r not in seen and v >= threshold:
            parts.append(_fmt_resource_amount(r, v))
    return ", ".join(parts) if parts else "nothing of note"


def _fmt_loot_table(
    money_looted: float,
    resources_looted: Optional[Dict[str, float]],
    infra_destroyed_value: float = 0.0,
    improvements_destroyed: Optional[Dict[str, int]] = None,
) -> str:
    """
    Build an HTML loot breakdown string using static resource icons and live sell prices.
    Used in loot attack body text — renders correctly in the browser.
    """
    lines = []
    prices = _get_resource_sell_prices()

    if money_looted > 0:
        lines.append(f"💰 {_fmt_money(money_looted)} cash")

    if resources_looted:
        for res in _RESOURCE_ORDER:
            if res == "money":
                continue
            amt = resources_looted.get(res, 0.0)
            if amt >= 0.01:
                sell_price = prices.get(res) or _FALLBACK_PRICES.get(res, 1000)
                value = amt * sell_price
                icon = _res_img(res)
                if amt >= 1_000_000:
                    amt_str = f"{amt/1_000_000:.2f}M"
                elif amt >= 1_000:
                    amt_str = f"{amt/1_000:.1f}K"
                else:
                    amt_str = f"{amt:,.1f}"
                lines.append(
                    f"{icon} {amt_str} {res.title()} "
                    f"@ {_fmt_price(sell_price)}/unit = {_fmt_money(value)}"
                )

    if infra_destroyed_value > 0:
        lines.append(f"🏗️ {_fmt_money(infra_destroyed_value)} infrastructure destroyed")

    if improvements_destroyed:
        imp_str = _summarize_improvements(improvements_destroyed)
        lines.append(f"🔨 Improvements destroyed: {imp_str}")

    return " | ".join(lines) if lines else "nothing of note"


def _lookup_nation_from_db(nation_id: int) -> Dict[str, Any]:
    """Synchronous lookup of nation/alliance info from GlobalNations.db."""
    try:
        import sqlite3
        from Systems.Functions.db_paths import GLOBAL_NATIONS_DB_STR
        conn = sqlite3.connect(GLOBAL_NATIONS_DB_STR)
        row = conn.execute(
            "SELECT nation_name, leader_name, alliance_id, alliance_name FROM nations WHERE id=?",
            (nation_id,)
        ).fetchone()
        conn.close()
        if row:
            return {
                "nation_name": row[0],
                "leader_name": row[1],
                "alliance_id": row[2],
                "alliance_name": row[3],
            }
    except Exception:
        pass
    return {}


def _lookup_alliance_from_db(alliance_id: int) -> Optional[str]:
    """Synchronous lookup of alliance name from GlobalNations.db by alliance_id."""
    try:
        import sqlite3
        from Systems.Functions.db_paths import GLOBAL_NATIONS_DB_STR
        conn = sqlite3.connect(GLOBAL_NATIONS_DB_STR)
        row = conn.execute(
            "SELECT DISTINCT alliance_name FROM nations WHERE alliance_id=? AND alliance_id != 0 LIMIT 1",
            (alliance_id,)
        ).fetchone()
        conn.close()
        if row and row[0]:
            return row[0]
    except Exception:
        pass
    return None


def _detect_projects_purchased(
    old_nation: Dict[str, Any], new_nation: Dict[str, Any]
) -> List[str]:
    """Return list of project display names that flipped from 0 to 1."""
    purchased = []
    for col in ALL_PROJECT_FIELDS:
        old_val = int(old_nation.get(col) or 0)
        new_val = int(new_nation.get(col) or 0)
        if old_val == 0 and new_val == 1:
            purchased.append(
                _PROJECT_DB_COL_TO_DISPLAY.get(col) or col.replace("_", " ").title()
            )
    return purchased




# ─────────────────────────────────────────────────────────────────────────────
# Improvement name formatting
# ─────────────────────────────────────────────────────────────────────────────

# Human-readable names for improvement DB columns
_IMPROVEMENT_DISPLAY: Dict[str, str] = {
    "coal_power":        "Coal Power Plant",
    "oil_power":         "Oil Power Plant",
    "nuclear_power":     "Nuclear Power Plant",
    "wind_power":        "Wind Power Plant",
    "coal_mine":         "Coal Mine",
    "oil_well":          "Oil Well",
    "uranium_mine":      "Uranium Mine",
    "lead_mine":         "Lead Mine",
    "iron_mine":         "Iron Mine",
    "bauxite_mine":      "Bauxite Mine",
    "oil_refinery":      "Oil Refinery",
    "steel_mill":        "Steel Mill",
    "aluminum_refinery": "Aluminum Refinery",
    "munitions_factory": "Munitions Factory",
    "farm":              "Farm",
    "police_station":    "Police Station",
    "hospital":          "Hospital",
    "recycling_center":  "Recycling Center",
    "subway":            "Subway",
    "supermarket":       "Supermarket",
    "bank":              "Bank",
    "shopping_mall":     "Shopping Mall",
    "stadium":           "Stadium",
    "barracks":          "Barracks",
    "factory":           "Factory",
    "hangar":            "Hangar",
    "drydock":           "Drydock",
}


def _fmt_improvement_name(col: str) -> str:
    return _IMPROVEMENT_DISPLAY.get(col, col.replace("_", " ").title())


def _summarize_improvements(improvements: Dict[str, int]) -> str:
    """Turn {col: count} into a readable list like '2x Barracks, 1x Hangar'."""
    parts = []
    for col, count in sorted(improvements.items(), key=lambda x: -x[1]):
        name = _fmt_improvement_name(col)
        parts.append(f"{count}x {name}" if count > 1 else name)
    return ", ".join(parts) if parts else "various improvements"


# ─────────────────────────────────────────────────────────────────────────────
# City purchase
# ─────────────────────────────────────────────────────────────────────────────

async def record_city_purchase(
    nation_id: int,
    nation_name: Optional[str],
    nation_flag: Optional[str],
    alliance_id: Optional[int],
    alliance_name: Optional[str],
    alliance_flag: Optional[str],
    old_cities: int,
    new_cities: int,
    cash_cost: float,
    resource_costs: Optional[Dict[str, float]] = None,
    event_date: Optional[str] = None,
) -> None:
    try:
        # Input validation
        _validate_nation_data(nation_id, nation_name, alliance_id)
        _validate_money_value(cash_cost, "cash_cost")
        if old_cities < 0 or new_cities < 0:
            raise ValueError(f"Invalid city counts: old={old_cities}, new={new_cities}")
        if new_cities < old_cities:
            # Cities decreased - not a purchase, skip this event
            logger.warning(f"Skipping city purchase for {nation_name} ({nation_id}): new_cities ({new_cities}) < old_cities ({old_cities}) - likely city loss")
            return
        
        db = get_news_db()
        count = new_cities - old_cities
        n_label = _nation_label(nation_name, nation_id)
        a_label = _alliance_label(alliance_name, alliance_id)
        n_tok = _nation_token(nation_id, nation_name)
        a_tok = _alliance_token(alliance_id, alliance_name)
        nw = _is_nw(alliance_id)
        
        # Calculate resource value using shared helper
        resource_value = _calculate_resource_value(resource_costs)
        total_value = cash_cost + resource_value

        ordinal = _ordinal(new_cities)
        if count == 1:
            headline = f"{n_label} of {a_label} builds their {ordinal} city"
        else:
            headline = f"{n_label} of {a_label} expands to {new_cities} cities (+{count})"

        # Build rich article body — use tokens so frontend renders clickable links
        intro_template = _pick(_NW_CITY_INTROS if nw else _CITY_INTROS)
        intro = _format_dialog(
            intro_template,
            nation=n_label,
            alliance=a_label if not nw else "",
            city_num=new_cities
        )

        if nw:
            if new_cities >= 40:
                flavor = (
                    f"With {new_cities} cities now flying the dark banner, "
                    f"{n_tok} has become one of the most powerful nations in the Darkstar. "
                    f"The Reaper marks this milestone with deep satisfaction. "
                    f"Enemies of the Watch should look upon this number and feel something cold in their chest."
                )
            elif new_cities >= 30:
                flavor = (
                    f"Thirty cities. {n_tok} has reached thirty cities under the dark banner. "
                    f"The Darkstar grows more formidable with every passing turn. "
                    f"The Reaper raises a skeletal hand in salute. "
                    f"This is what dedication looks like."
                )
            elif new_cities >= 20:
                flavor = (
                    f"{n_tok} has reached {new_cities} cities — a formidable presence "
                    f"in the realm. The Watch's dominion grows ever wider. "
                    f"The Reaper is pleased. The Watch's enemies should be less so."
                )
            elif new_cities >= 15:
                flavor = (
                    f"The {ordinal} city rises under the dark banner. "
                    f"{n_tok} continues to build the foundation of a great nation. "
                    f"At {new_cities} cities, the Watch's presence in Orbis is undeniable. "
                    f"The Reaper watches with pride."
                )
            elif new_cities >= 10:
                flavor = (
                    f"The {ordinal} city joins the Darkstar empire. "
                    f"{n_tok} is building something real here. "
                    f"Ten cities is not a small thing. The Reaper takes note."
                )
            else:
                flavor = (
                    f"Every great wall begins with a single stone. "
                    f"{n_tok} lays another, reaching {new_cities} {'city' if new_cities == 1 else 'cities'}. "
                    f"The Watch grows. The Reaper approves of growth."
                )
        else:
            # Non-NW: pick from varied tones
            _non_nw_flavors = [
                (
                    f"{n_tok}{' of ' + a_tok if a_tok else ''} has invested {_fmt_money(total_value)} "
                    f"to expand their nation to {new_cities} {'city' if new_cities == 1 else 'cities'}. "
                    f"The realm takes note. The Reaper records it."
                ),
                (
                    f"The {ordinal} city of {n_tok}{' (' + a_tok + ')' if a_tok else ''} rises from the ground. "
                    f"Cost: {_fmt_money(total_value)}. "
                    f"The Reaper adds another entry to his ever-growing ledger of Orbis."
                ),
                (
                    f"{n_tok}{' of ' + a_tok if a_tok else ''} expands to {new_cities} cities, "
                    f"spending {_fmt_money(total_value)} in the process. "
                    f"Ambition is expensive. They seem to be paying willingly."
                ),
                (
                    f"Another city joins the empire of {n_tok}{' (' + a_tok + ')' if a_tok else ''}. "
                    f"The investment: {_fmt_money(total_value)}. "
                    f"The Reaper notes the expansion and moves on."
                ),
            ]
            flavor = _pick(_non_nw_flavors)

        body = f"{intro} {flavor}"

        await db.record_event(
            event_type="city_purchase",
            nation_id=nation_id,
            nation_name=nation_name,
            nation_flag=nation_flag,
            alliance_id=alliance_id,
            alliance_name=alliance_name,
            alliance_flag=alliance_flag,
            value=total_value,
            value2=float(new_cities),
            headline=headline,
            detail={
                "body": body,
                "old_cities": old_cities,
                "new_cities": new_cities,
                "count": count,
                "cash_cost": cash_cost,
                "resource_costs": resource_costs if resource_costs else None,
                "resource_value": resource_value if resource_value > 0 else None,
                "total_value": total_value,
                "is_nw": nw,
            },
            event_date=event_date or _now_str(),
            alliance_delta={"cities_built": count, "total_spent": total_value},
            nation_delta={"cities_built": count, "total_spent": total_value},
        )
    except Exception as e:
        logger.error(f"NewsWriter.record_city_purchase: {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Project purchase
# ─────────────────────────────────────────────────────────────────────────────

async def record_project_purchase(
    nation_id: int,
    nation_name: Optional[str],
    nation_flag: Optional[str],
    alliance_id: Optional[int],
    alliance_name: Optional[str],
    alliance_flag: Optional[str],
    project_names: List[str],
    cash_cost: float,
    resource_costs: Optional[Dict[str, float]] = None,
    event_date: Optional[str] = None,
) -> None:
    try:
        # Input validation
        _validate_nation_data(nation_id, nation_name, alliance_id)
        _validate_money_value(cash_cost, "cash_cost")
        if not project_names:
            raise ValueError("project_names cannot be empty")
        
        db = get_news_db()
        n_label = _nation_label(nation_name, nation_id)
        a_label = _alliance_label(alliance_name, alliance_id)
        nw = _is_nw(alliance_id)
        proj_str = ", ".join(project_names) if project_names else "a project"

        if len(project_names) == 1:
            headline = f"{n_label} of {a_label} completes {proj_str}"
        else:
            headline = f"{n_label} of {a_label} completes {len(project_names)} projects: {proj_str}"

        # Calculate resource value using shared helper
        resource_value = _calculate_resource_value(resource_costs)
        total_value = cash_cost + resource_value

        intro_template = _pick(_NW_PROJECT_INTROS if nw else _PROJECT_INTROS)
        intro = _format_dialog(
            intro_template,
            nation=n_label,
            alliance=a_label if not nw else "",
            project=proj_str
        )

        # Project-specific flavor for key projects
        _MILITARY_PROJECTS = {
            "Iron Dome", "Vital Defense System", "Missile Launch Pad",
            "Nuclear Research Facility", "Nuclear Launch Facility",
            "Military Research Center", "Military Doctrine", "Arms Stockpile",
            "Guiding Satellite", "Spy Satellite", "Central Intelligence Agency",
        }
        _ECONOMIC_PROJECTS = {
            "International Trade Center", "Bureau of Domestic Affairs",
            "Government Support Agency", "Green Technologies",
            "Recycling Initiative", "Mass Irrigation", "Arable Land Agency",
        }
        _NUKE_PROJECTS = {"Nuclear Research Facility", "Nuclear Launch Facility"}
        _MISSILE_PROJECTS = {"Missile Launch Pad"}
        _DEFENSE_PROJECTS = {"Iron Dome", "Vital Defense System"}

        if nw:
            if any(p in _NUKE_PROJECTS for p in project_names):
                flavor = (
                    f"The Darkstar has completed {proj_str}. "
                    f"The Reaper pauses. Looks at the Watch. Looks at Orbis. "
                    f"Nods slowly. The Watch now has nuclear capability. "
                    f"Enemies of the Watch should be updating their wills."
                )
            elif any(p in _MISSILE_PROJECTS for p in project_names):
                flavor = (
                    f"The Darkstar has completed {proj_str}. "
                    f"The Watch's reach now extends to missile strikes. "
                    f"The Reaper is delighted. Enemies of the Watch should be less so. "
                    f"The Watch does not build launch pads for decoration."
                )
            elif any(p in _DEFENSE_PROJECTS for p in project_names):
                flavor = (
                    f"The Darkstar has completed {proj_str}. "
                    f"The Watch's defenses grow more formidable. "
                    f"The Reaper approves — a well-defended Watch is a dangerous Watch. "
                    f"Those who would strike the Watch will find it harder than expected."
                )
            elif any(p in _MILITARY_PROJECTS for p in project_names):
                flavor = (
                    f"The Darkstar has completed {proj_str}. "
                    f"The Reaper notes this addition to the Watch's arsenal with approval. "
                    f"Every military project is another reason for the Watch's enemies to reconsider their life choices."
                )
            elif any(p in _ECONOMIC_PROJECTS for p in project_names):
                flavor = (
                    f"The Darkstar has completed {proj_str}, "
                    f"strengthening the economic foundation that funds its military might. "
                    f"A nation that can sustain itself can fight forever. "
                    f"The Watch understands this. The Reaper respects it."
                )
            else:
                flavor = (
                    f"The Darkstar has completed {proj_str}. "
                    f"Every project brings the Watch closer to its full potential. "
                    f"The Reaper watches this progress with great interest and considerable satisfaction."
                )
        else:
            cost_str = _fmt_money(total_value)
            n_tok = _nation_token(nation_id, nation_name)
            a_tok = _alliance_token(alliance_id, alliance_name)
            _non_nw_project_flavors = [
                (
                    f"{n_tok}{' of ' + a_tok if a_tok else ''} has completed {proj_str}, "
                    f"investing {cost_str} in their nation's future. "
                    f"The realm grows more capable. The Reaper records the development."
                ),
                (
                    f"{proj_str} — completed by {n_tok}{' (' + a_tok + ')' if a_tok else ''}. "
                    f"Total investment: {cost_str}. "
                    f"The Reaper notes this advancement with professional detachment."
                ),
                (
                    f"The project is complete. {n_tok}{' of ' + a_tok if a_tok else ''} has finished {proj_str}. "
                    f"Cost: {cost_str}. "
                    f"Another nation grows more capable. The Reaper updates his files."
                ),
                (
                    f"{n_tok}{' (' + a_tok + ')' if a_tok else ''} has invested {cost_str} to complete {proj_str}. "
                    f"Progress marches on. The Reaper watches it march."
                ),
            ]
            flavor = _pick(_non_nw_project_flavors)

        body = f"{intro} {flavor}"
        if resource_costs:
            rss_str = _fmt_resources(resource_costs)
            body += f" Resources consumed: {rss_str}."

        detail: Dict[str, Any] = {
            "body": body,
            "projects": project_names,
            "count": len(project_names),
            "cash_cost": cash_cost,
            "is_nw": nw,
        }
        if resource_costs:
            detail["resource_costs"] = resource_costs
        if resource_value > 0:
            detail["resource_value"] = resource_value
            detail["total_value"] = total_value

        await db.record_event(
            event_type="project_purchase",
            nation_id=nation_id,
            nation_name=nation_name,
            nation_flag=nation_flag,
            alliance_id=alliance_id,
            alliance_name=alliance_name,
            alliance_flag=alliance_flag,
            value=total_value,
            value2=float(len(project_names)),
            headline=headline,
            detail=detail,
            event_date=event_date or _now_str(),
            alliance_delta={"projects_bought": len(project_names), "total_spent": total_value},
            nation_delta={"projects_bought": len(project_names), "total_spent": total_value},
        )
    except Exception as e:
        logger.error(f"NewsWriter.record_project_purchase: {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# City upgrade (infra / land / improvements)
# ─────────────────────────────────────────────────────────────────────────────

async def record_city_upgrade(
    nation_id: int,
    nation_name: Optional[str],
    nation_flag: Optional[str],
    alliance_id: Optional[int],
    alliance_name: Optional[str],
    alliance_flag: Optional[str],
    infra_spent: float,
    land_spent: float,
    improvements_spent: float,
    total_spent: float,
    detail_str: str,
    city_id: Optional[int] = None,
    city_name: Optional[str] = None,
    event_date: Optional[str] = None,
    # New: specific improvements built {col: count}
    improvements_built: Optional[Dict[str, int]] = None,
    improvement_resource_costs: Optional[Dict[str, float]] = None,
    infra_before: Optional[float] = None,
    infra_after: Optional[float] = None,
    land_before: Optional[float] = None,
    land_after: Optional[float] = None,
) -> None:
    try:
        # Input validation
        _validate_nation_data(nation_id, nation_name, alliance_id)
        _validate_money_value(infra_spent, "infra_spent")
        _validate_money_value(land_spent, "land_spent")
        _validate_money_value(improvements_spent, "improvements_spent")
        _validate_money_value(total_spent, "total_spent")
        
        if total_spent < CITY_UPGRADE_THRESHOLD:
            return

        # Calculate resource value for improvements using shared helper
        resource_value = _calculate_resource_value(improvement_resource_costs)
        
        # Total value includes both cash and resource costs
        total_value = total_spent + resource_value
        
        db = get_news_db()
        n_label = _nation_label(nation_name, nation_id)
        a_label = _alliance_label(alliance_name, alliance_id)
        nw = _is_nw(alliance_id)

        # Build headline
        parts = []
        if infra_spent > 0:
            if infra_before is not None and infra_after is not None:
                parts.append(f"infrastructure ({infra_before:.0f}→{infra_after:.0f}, {_fmt_money(infra_spent)})")
            else:
                parts.append(f"infrastructure ({_fmt_money(infra_spent)})")
        if land_spent > 0:
            if land_before is not None and land_after is not None:
                parts.append(f"land ({land_before:.0f}→{land_after:.0f}, {_fmt_money(land_spent)})")
            else:
                parts.append(f"land ({_fmt_money(land_spent)})")
        if improvements_spent > 0:
            if improvements_built:
                imp_summary = _summarize_improvements(improvements_built)
                parts.append(f"improvements: {imp_summary} ({_fmt_money(improvements_spent)})")
            else:
                parts.append(f"improvements ({_fmt_money(improvements_spent)})")
            # Add resource costs to headline if present
            if improvement_resource_costs:
                rss_str = ", ".join(f"{amt:,.1f} {r.title()}" for r, amt in improvement_resource_costs.items())
                parts[-1] = parts[-1].rstrip(")") + f" + {rss_str})"

        what = " & ".join(parts) if parts else "city upgrades"
        city_ref = f" in {city_name}" if city_name else (f" in city #{city_id}" if city_id else "")
        headline = f"{n_label} of {a_label} invests {_fmt_money(total_value)} in {what}{city_ref}"

        # Build article body — use tokens so frontend renders clickable links
        intro_template = _pick(_NW_UPGRADE_INTROS if nw else _UPGRADE_INTROS)
        if nw:
            intro = _format_dialog(
                intro_template,
                nation=n_label,
                upgrade=what
            )
        else:
            intro = _format_dialog(
                intro_template,
                nation=n_label,
                alliance=a_label,
                upgrade=what
            )
        n_tok = _nation_token(nation_id, nation_name)
        a_tok = _alliance_token(alliance_id, alliance_name)

        body_parts = [intro]

        if nw:
            _nw_upgrade_bodies = [
                f"The Darkstar continues to fortify its position. "
                f"{n_tok} has invested {_fmt_money(total_value)} in city development{city_ref}. "
                f"The Watch does not neglect its cities. The Watch does not neglect anything.",

                f"{n_tok} of the Darkstar pours {_fmt_money(total_value)} into {city_ref or 'city upgrades'}. "
                f"The Watch builds for the long war. Every improvement is a statement of intent.",

                f"The Darkstar invests {_fmt_money(total_value)} in {city_ref or 'city infrastructure'}. "
                f"The Reaper approves. A strong city is a strong Watch. "
                f"A strong Watch is a dangerous Watch.",

                f"{n_tok} upgrades {city_ref or 'a city'} with {_fmt_money(total_value)} in improvements. "
                f"The Watch's cities grow as formidable as its military. "
                f"The Reaper notes this with satisfaction.",
            ]
            body_parts.append(_pick(_nw_upgrade_bodies))
        else:
            _non_nw_upgrade_bodies = [
                f"{n_tok}{' of ' + a_tok if a_tok else ''} has invested {_fmt_money(total_value)} "
                f"in city development{city_ref}. The Reaper records the investment.",

                f"City upgrades{city_ref or ''} by {n_tok}{' (' + a_tok + ')' if a_tok else ''}. "
                f"Total cost: {_fmt_money(total_value)}. "
                f"The Reaper notes the improvement and moves on.",

                f"{n_tok}{' (' + a_tok + ')' if a_tok else ''} spends {_fmt_money(total_value)} improving {city_ref or 'their city'}. "
                f"Progress. The Reaper has seen a lot of it today.",

                f"An investment of {_fmt_money(total_value)} by {n_tok}{' of ' + a_tok if a_tok else ''}. "
                f"The city grows. The Reaper records it.",
            ]
            body_parts.append(_pick(_non_nw_upgrade_bodies))

        # Detail breakdown
        breakdown_lines = []
        if infra_spent > 0:
            if infra_before is not None and infra_after is not None:
                breakdown_lines.append(
                    f"Infrastructure expanded from {infra_before:.0f} to {infra_after:.0f} "
                    f"(+{infra_after - infra_before:.0f} levels, {_fmt_money(infra_spent)})"
                )
            else:
                breakdown_lines.append(f"Infrastructure: {_fmt_money(infra_spent)}")

        if land_spent > 0:
            if land_before is not None and land_after is not None:
                breakdown_lines.append(
                    f"Land expanded from {land_before:.0f} to {land_after:.0f} "
                    f"(+{land_after - land_before:.0f} sq mi, {_fmt_money(land_spent)})"
                )
            else:
                breakdown_lines.append(f"Land: {_fmt_money(land_spent)}")

        if improvements_spent > 0:
            if improvements_built:
                imp_detail = _summarize_improvements(improvements_built)
                breakdown_lines.append(
                    f"Improvements built: {imp_detail} ({_fmt_money(improvements_spent)})"
                )
            else:
                breakdown_lines.append(f"Improvements: {_fmt_money(improvements_spent)}")
            # Add resource costs to breakdown if present
            if improvement_resource_costs:
                rss_str = _fmt_resources(improvement_resource_costs)
                breakdown_lines.append(f"Resources consumed: {rss_str}")

        if breakdown_lines:
            body_parts.append("Breakdown: " + "; ".join(breakdown_lines) + ".")

        if nw and improvements_built:
            mil_imps = {"barracks", "factory", "hangar", "drydock"}
            built_mil = {k: v for k, v in improvements_built.items() if k in mil_imps}
            if built_mil:
                body_parts.append(
                    f"The Reaper notes the military construction with approval: "
                    f"{_summarize_improvements(built_mil)}. "
                    f"The Watch prepares for war."
                )

        body = " ".join(body_parts)

        await db.record_event(
            event_type="city_upgrade",
            nation_id=nation_id,
            nation_name=nation_name,
            nation_flag=nation_flag,
            alliance_id=alliance_id,
            alliance_name=alliance_name,
            alliance_flag=alliance_flag,
            value=total_value,
            value2=infra_spent,
            headline=headline,
            detail={
                "body": body,
                "infra_spent": infra_spent,
                "land_spent": land_spent,
                "improvements_spent": improvements_spent,
                "total_spent": total_spent,
                "total_value": total_value if resource_value > 0 else None,
                "detail": detail_str,
                "city_id": city_id,
                "city_name": city_name,
                "improvements_built": improvements_built or {},
                "resource_costs": improvement_resource_costs or {},
                "resource_value": resource_value if resource_value > 0 else None,
                "infra_before": infra_before,
                "infra_after": infra_after,
                "land_before": land_before,
                "land_after": land_after,
                "is_nw": nw,
            },
            event_date=event_date or _now_str(),
            alliance_delta={
                "infra_spent": infra_spent,
                "land_spent": land_spent,
                "improvements_spent": improvements_spent,
                "total_spent": total_value,
            },
            nation_delta={
                "infra_spent": infra_spent,
                "land_spent": land_spent,
                "improvements_spent": improvements_spent,
                "total_spent": total_value,
            },
        )
    except Exception as e:
        logger.error(f"NewsWriter.record_city_upgrade: {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Military purchase
# ─────────────────────────────────────────────────────────────────────────────

async def record_military_purchase(
    nation_id: int,
    nation_name: Optional[str],
    nation_flag: Optional[str],
    alliance_id: Optional[int],
    alliance_name: Optional[str],
    alliance_flag: Optional[str],
    unit_type: str,
    quantity: int,
    cash_cost: float,
    resource_costs: Optional[Dict[str, float]] = None,
    event_date: Optional[str] = None,
) -> None:
    try:
        # Input validation
        _validate_nation_data(nation_id, nation_name, alliance_id)
        _validate_money_value(cash_cost, "cash_cost")
        if quantity <= 0:
            raise ValueError(f"Invalid quantity: {quantity} (must be positive)")
        if not unit_type:
            raise ValueError("unit_type cannot be empty")
        
        # Calculate resource value using shared helper
        resource_value = _calculate_resource_value(resource_costs)
        total_cost = cash_cost + resource_value
        
        if total_cost < MILITARY_PURCHASE_THRESHOLD:
            return

        db = get_news_db()
        n_label = _nation_label(nation_name, nation_id)
        a_label = _alliance_label(alliance_name, alliance_id)
        nw = _is_nw(alliance_id)
        unit_label = _fmt_unit(unit_type, quantity)

        headline = (
            f"{n_label} of {a_label} purchases {quantity:,} {unit_label} "
            f"({_fmt_money(total_cost)})"
        )

        intro_template = _pick(_NW_MIL_INTROS if nw else _MIL_INTROS)
        if nw:
            intro = _format_dialog(
                intro_template,
                nation=n_label,
                military=unit_label,
                value=_fmt_money(total_cost)
            )
        else:
            intro = _format_dialog(
                intro_template,
                nation=n_label,
                alliance=a_label,
                military=unit_label,
                value=_fmt_money(total_cost)
            )

        # Unit-specific flavor
        _UNIT_FLAVOR_NW = {
            "soldiers": (
                f"{quantity:,} new soldiers take the oath of the Darkstar. "
                f"The Wall grows stronger. The Reaper counts the new recruits with approval."
            ),
            "tanks": (
                f"{quantity:,} tanks roll into the Darkstar motor pool. "
                f"The ground trembles. Enemies of the Watch should feel that trembling."
            ),
            "aircraft": (
                f"{quantity:,} aircraft join the Darkstar air wing. "
                f"The skies belong to the Watch. The Reaper watches them take flight with pride."
            ),
            "ships": (
                f"{quantity:,} ships join the Darkstar fleet. "
                f"The seas are no longer safe for enemies of the Watch. "
                f"The Reaper notes this naval expansion with satisfaction."
            ),
            "missiles": (
                f"{quantity:,} missiles are loaded into the Darkstar silos. "
                f"A message to all who would oppose the Watch: "
                f"the Watch's reach is long, and its aim is improving."
            ),
            "nukes": (
                f"{quantity:,} nuclear warheads join the Darkstar arsenal. "
                f"The Reaper smiles. The world should tremble. "
                f"The Darkstar now holds the power of the atom. "
                f"Use it wisely. Or don't. The Reaper will be watching either way."
            ),
            "spies": (
                f"{quantity:,} new agents enter the Darkstar intelligence network. "
                f"Eyes everywhere. The Watch sees all. "
                f"The Reaper approves of this investment in information."
            ),
        }
        _UNIT_FLAVOR_NW_ALT = {
            "soldiers": f"The Darkstar grows its army by {quantity:,}. Every soldier is a promise of what comes next.",
            "tanks":    f"{quantity:,} more tanks for the Watch. The armor grows thicker. The threat grows larger.",
            "aircraft": f"The Watch's air force gains {quantity:,} aircraft. The skies darken with dark banners.",
            "ships":    f"{quantity:,} new ships for the Watch's fleet. The seas answer to the Darkstar now.",
            "missiles": f"The Watch's missile count grows by {quantity:,}. The Reaper is very pleased about this.",
            "nukes":    f"{quantity:,} more nuclear warheads. The Watch's deterrent grows. The Reaper is delighted.",
            "spies":    f"{quantity:,} more spies in the shadows. The Watch's intelligence network expands.",
        }
        _UNIT_FLAVOR = {
            "soldiers": f"{quantity:,} soldiers join the ranks. The Reaper counts them.",
            "tanks":    f"{quantity:,} tanks roll off the production line. Steel and ambition.",
            "aircraft": f"{quantity:,} aircraft take to the skies. The Reaper watches them climb.",
            "ships":    f"{quantity:,} ships set sail. The seas grow more contested.",
            "missiles": f"{quantity:,} missiles are armed and ready. The Reaper notes the addition.",
            "nukes":    f"{quantity:,} nuclear warheads are added to the arsenal. The balance of terror shifts.",
            "spies":    f"{quantity:,} spies are deployed into the shadows. The Reaper approves of shadows.",
        }

        if nw:
            # Alternate between two NW flavor pools for variety
            if random.random() < 0.5:
                flavor = _UNIT_FLAVOR_NW.get(unit_type, f"{quantity:,} {unit_label} join the Darkstar. The Watch grows stronger.")
            else:
                flavor = _UNIT_FLAVOR_NW_ALT.get(unit_type, f"{quantity:,} {unit_label} join the Darkstar.")
        else:
            n_tok = _nation_token(nation_id, nation_name)
            a_tok = _alliance_token(alliance_id, alliance_name)
            _non_nw_mil_flavors = [
                _UNIT_FLAVOR.get(unit_type, f"{quantity:,} {unit_label} are purchased."),
                f"The purchase: {quantity:,} {unit_label} at a cost of {_fmt_money(total_cost)}. The Reaper records the transaction.",
                f"{n_tok}{' (' + a_tok + ')' if a_tok else ''} adds {quantity:,} {unit_label} to their forces. Another nation arms up.",
                f"Military expansion: {quantity:,} {unit_label}. Total investment: {_fmt_money(total_cost)}.",
            ]
            flavor = _pick(_non_nw_mil_flavors)

        body = f"{intro} {flavor} Total investment: {_fmt_money(total_cost)}."
        if resource_costs:
            rss_str = _fmt_resources(resource_costs)
            body += f" Resources consumed: {rss_str}."

        detail: Dict[str, Any] = {
            "body": body,
            "unit_type": unit_type,
            "quantity": quantity,
            "cash_cost": cash_cost,
            "is_nw": nw,
        }
        if resource_costs:
            detail["resource_costs"] = resource_costs
        if resource_value > 0:
            detail["resource_value"] = resource_value
            detail["total_cost"] = total_cost

        await db.record_event(
            event_type="military_purchase",
            nation_id=nation_id,
            nation_name=nation_name,
            nation_flag=nation_flag,
            alliance_id=alliance_id,
            alliance_name=alliance_name,
            alliance_flag=alliance_flag,
            value=total_cost,
            value2=float(quantity),
            headline=headline,
            detail=detail,
            event_date=event_date or _now_str(),
            alliance_delta={"military_spent": total_cost, "total_spent": total_cost},
            nation_delta={"military_spent": total_cost, "total_spent": total_cost},
        )
    except Exception as e:
        logger.error(f"NewsWriter.record_military_purchase: {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# War declared
# ─────────────────────────────────────────────────────────────────────────────

async def record_war_declared(
    war_id: int,
    att_nation_id: int,
    att_nation_name: Optional[str],
    att_nation_flag: Optional[str],
    att_alliance_id: Optional[int],
    att_alliance_name: Optional[str],
    att_alliance_flag: Optional[str],
    def_nation_id: int,
    def_nation_name: Optional[str],
    def_nation_flag: Optional[str],
    def_alliance_id: Optional[int],
    def_alliance_name: Optional[str],
    war_type: str,
    reason: Optional[str],
    event_date: Optional[str] = None,
    att_leader_name: Optional[str] = None,
    def_leader_name: Optional[str] = None,
) -> None:
    try:
        # Input validation
        _validate_nation_data(att_nation_id, att_nation_name, att_alliance_id)
        _validate_nation_data(def_nation_id, def_nation_name, def_alliance_id)
        if war_id <= 0:
            raise ValueError(f"Invalid war_id: {war_id} (must be positive)")
        
        # Fill in missing info from GlobalNations.db
        if def_nation_id and (not def_nation_name or not def_alliance_name or not def_leader_name):
            _d = _lookup_nation_from_db(def_nation_id)
            def_nation_name   = def_nation_name   or _d.get("nation_name")
            def_alliance_id   = def_alliance_id   or _d.get("alliance_id")
            def_alliance_name = def_alliance_name or _d.get("alliance_name")
            def_leader_name   = def_leader_name   or _d.get("leader_name")
        if att_nation_id and not att_leader_name:
            _a = _lookup_nation_from_db(att_nation_id)
            att_leader_name = _a.get("leader_name")

        db = get_news_db()
        att_label = _nation_label(att_nation_name, att_nation_id)
        def_label = _nation_label(def_nation_name, def_nation_id)
        att_a = _alliance_label(att_alliance_name, att_alliance_id)
        def_a = _alliance_label(def_alliance_name, def_alliance_id)
        wt = war_type.replace("_", " ").title() if war_type else "War"
        att_leader = att_leader_name or att_label
        def_leader = def_leader_name or def_label

        att_nw = _is_nw(att_alliance_id)
        def_nw = _is_nw(def_alliance_id)

        att_nation_token   = f"Nation #{att_nation_id}"   if att_nation_id   else att_label
        def_nation_token   = f"Nation #{def_nation_id}"   if def_nation_id   else def_label
        att_alliance_token = f"Alliance #{att_alliance_id}" if att_alliance_id and int(att_alliance_id) != 0 else att_a
        def_alliance_token = f"Alliance #{def_alliance_id}" if def_alliance_id and int(def_alliance_id) != 0 else def_a

        headline = (
            f"New {wt} war: {att_leader} of {att_nation_token} ({att_alliance_token}) "
            f"declares on {def_leader} of {def_nation_token} ({def_alliance_token})"
        )

        # Build article body based on who is NW — use tokens for clickable links
        att_n_tok = _nation_token(att_nation_id, att_nation_name)
        att_a_tok = _alliance_token(att_alliance_id, att_alliance_name)
        def_n_tok = _nation_token(def_nation_id, def_nation_name)
        def_a_tok = _alliance_token(def_alliance_id, def_alliance_name)
        att_with_a = f"{att_n_tok}{' (' + att_a_tok + ')' if att_a_tok else ''}"
        def_with_a = f"{def_n_tok}{' (' + def_a_tok + ')' if def_a_tok else ''}"

        if att_nw:
            intro_template = _pick(_NW_ATT_WAR_INTROS)
            intro = _format_dialog(
                intro_template,
                nation=att_label,
                war_type=war_type,
                defender=def_label
            )
            _nw_att_bodies = [
                (
                    f"The Darkstar, led by {att_leader}, has declared a {wt} war "
                    f"against {def_leader} of {def_with_a}. "
                    + (f"The stated reason: \"{reason.strip()}\". " if reason and reason.strip() else "")
                    + f"The Reaper watches with great anticipation. "
                    f"The Darkstar does not declare war lightly — "
                    f"and it does not stop until the job is done."
                ),
                (
                    f"The dark banners march. {att_leader} of the Darkstar has declared war on "
                    f"{def_leader} of {def_with_a}. "
                    + (f"Reason given: \"{reason.strip()}\". " if reason and reason.strip() else "")
                    + f"The Reaper sharpens his scythe. This is going to be interesting."
                ),
                (
                    f"War. The Darkstar has chosen {def_with_a} as its next target. "
                    f"{att_leader} leads the charge. "
                    + (f"The Watch's stated reason: \"{reason.strip()}\". " if reason and reason.strip() else "")
                    + f"The Reaper has seen the Watch go to war before. "
                    f"He knows how it ends for the Watch's enemies."
                ),
                (
                    f"The Darkstar has spoken. {att_leader} declares {wt} war on "
                    f"{def_leader} of {def_with_a}. "
                    + (f"Reason: \"{reason.strip()}\". " if reason and reason.strip() else "")
                    + f"Death rides with the Watch tonight. "
                    f"The enemy should be very, very concerned."
                ),
            ]
            body = _pick(_nw_att_bodies)
        elif def_nw:
            intro_template = _pick(_NW_DEF_WAR_INTROS)
            intro = _format_dialog(
                intro_template,
                nation=def_label,
                war_type=war_type,
                attacker=att_label
            )
            _nw_def_bodies = [
                (
                    f"{att_leader} of {att_with_a} has declared a {wt} war "
                    f"against the Darkstar, targeting {def_leader} of {def_n_tok}. "
                    + (f"Their stated reason: \"{reason.strip()}\". " if reason and reason.strip() else "")
                    + f"The Reaper has seen many challengers rise against the Watch. "
                    f"He has seen them all fall. "
                    f"The Darkstar will respond in kind."
                ),
                (
                    f"Someone has declared war on the Darkstar. "
                    f"That someone is {att_leader} of {att_with_a}. "
                    + (f"Reason: \"{reason.strip()}\". " if reason and reason.strip() else "")
                    + f"The Reaper is taking notes. The Watch is taking names. "
                    f"This will not end well for the aggressor."
                ),
                (
                    f"The Darkstar has been challenged. {att_leader} of {att_with_a} "
                    f"declares {wt} war on {def_leader} of the Watch. "
                    + (f"Stated reason: \"{reason.strip()}\". " if reason and reason.strip() else "")
                    + f"Bold. The Reaper has seen bold before. "
                    f"Bold does not always survive contact with the Darkstar."
                ),
                (
                    f"War declared against the Darkstar by {att_leader} of {att_with_a}. "
                    + (f"Their reason: \"{reason.strip()}\". " if reason and reason.strip() else "")
                    + f"The Reaper is displeased on the Watch's behalf. "
                    f"The Watch will be displeased in a more... direct manner."
                ),
            ]
            body = _pick(_nw_def_bodies)
        else:
            intro_template = _pick(_WAR_DECLARED_INTROS)
            intro = _format_dialog(
                intro_template,
                attacker=att_label,
                att_alliance=att_a,
                defender=def_label,
                def_alliance=def_a,
                war_type=war_type
            )
            _non_nw_bodies = [
                (
                    f"{att_leader} of {att_with_a} has declared a {wt} war "
                    f"against {def_leader} of {def_with_a}. "
                    + (f"Stated reason: \"{reason.strip()}\". " if reason and reason.strip() else "")
                    + f"The Reaper records this conflict in his ledger and waits."
                ),
                (
                    f"War erupts between {att_with_a} and {def_with_a}. "
                    f"{att_leader} pulls the trigger. "
                    + (f"Reason: \"{reason.strip()}\". " if reason and reason.strip() else "")
                    + f"The Reaper opens a new page. Another conflict for the collection."
                ),
                (
                    f"The diplomats have failed. {att_leader} of {att_with_a} declares {wt} war "
                    f"on {def_leader} of {def_with_a}. "
                    + (f"The reason given: \"{reason.strip()}\". " if reason and reason.strip() else "")
                    + f"The Reaper settles in to watch. He has popcorn. Metaphorically."
                ),
                (
                    f"A new war in Orbis. {att_with_a} vs {def_with_a}. "
                    f"{att_leader} makes the first move. "
                    + (f"Stated reason: \"{reason.strip()}\". " if reason and reason.strip() else "")
                    + f"The Reaper records the declaration and awaits the outcome."
                ),
            ]
            body = f"{intro} {_pick(_non_nw_bodies)}"

        _detail = {
            "body": body,
            "war_id": war_id,
            "war_type": war_type,
            "reason": reason,
            "is_nw_attacker": att_nw,
            "is_nw_defender": def_nw,
            "attacker": {
                "id": att_nation_id,
                "name": att_nation_name,
                "leader": att_leader_name,
                "flag": att_nation_flag,
                "alliance_id": att_alliance_id,
                "alliance_name": att_alliance_name,
            },
            "defender": {
                "id": def_nation_id,
                "name": def_nation_name,
                "leader": def_leader_name,
                "flag": def_nation_flag,
                "alliance_id": def_alliance_id,
                "alliance_name": def_alliance_name,
            },
        }

        await db.record_event(
            event_type="war_declared",
            nation_id=att_nation_id,
            nation_name=att_nation_name,
            nation_flag=att_nation_flag,
            alliance_id=att_alliance_id,
            alliance_name=att_alliance_name,
            alliance_flag=att_alliance_flag,
            sec_nation_id=def_nation_id,
            sec_nation_name=def_nation_name,
            sec_alliance_id=def_alliance_id,
            sec_alliance_name=def_alliance_name,
            value=float(war_id),
            value2=0.0,
            headline=headline,
            detail=_detail,
            event_date=event_date or _now_str(),
            alliance_delta={"wars_declared": 1},
            nation_delta={"wars_declared": 1},
            sec_alliance_delta={"wars_declared": 1} if def_alliance_id and def_alliance_id != att_alliance_id else {},
            sec_nation_delta={"wars_declared": 1},
        )
    except Exception as e:
        logger.error(f"NewsWriter.record_war_declared: {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# War ended
# ─────────────────────────────────────────────────────────────────────────────

async def record_war_ended(
    war_id: int,
    att_nation_id: int,
    att_nation_name: Optional[str],
    att_nation_flag: Optional[str],
    att_alliance_id: Optional[int],
    att_alliance_name: Optional[str],
    att_alliance_flag: Optional[str],
    def_nation_id: int,
    def_nation_name: Optional[str],
    def_nation_flag: Optional[str],
    def_alliance_id: Optional[int],
    def_alliance_name: Optional[str],
    def_alliance_flag: Optional[str] = None,
    winner_id: Optional[int] = None,
    end_reason: str = "ended",
    war_type: str = "",
    event_date: Optional[str] = None,
) -> None:
    try:
        # Input validation
        _validate_nation_data(att_nation_id, att_nation_name, att_alliance_id)
        _validate_nation_data(def_nation_id, def_nation_name, def_alliance_id)
        if war_id <= 0:
            raise ValueError(f"Invalid war_id: {war_id} (must be positive)")
        
        if def_nation_id and (not def_nation_name or not def_alliance_name):
            _d = _lookup_nation_from_db(def_nation_id)
            def_nation_name   = def_nation_name   or _d.get("nation_name")
            def_alliance_id   = def_alliance_id   or _d.get("alliance_id")
            def_alliance_name = def_alliance_name or _d.get("alliance_name")

        db = get_news_db()
        att_label = _nation_label(att_nation_name, att_nation_id)
        def_label = _nation_label(def_nation_name, def_nation_id)
        att_a = _alliance_label(att_alliance_name, att_alliance_id)
        def_a = _alliance_label(def_alliance_name, def_alliance_id)

        att_nw = _is_nw(att_alliance_id)
        def_nw = _is_nw(def_alliance_id)

        att_won = winner_id is not None and int(winner_id) == int(att_nation_id)
        def_won = winner_id is not None and int(winner_id) == int(def_nation_id)

        if end_reason == "peace":
            outcome = "peace"
        elif att_won:
            outcome = "attacker_win"
        elif def_won:
            outcome = "defender_win"
        else:
            outcome = "expired"

        # Determine headline and body — use tokens for clickable links
        att_n_tok = _nation_token(att_nation_id, att_nation_name)
        att_a_tok = _alliance_token(att_alliance_id, att_alliance_name)
        def_n_tok = _nation_token(def_nation_id, def_nation_name)
        def_a_tok = _alliance_token(def_alliance_id, def_alliance_name)
        att_with_a = f"{att_n_tok}{' (' + att_a_tok + ')' if att_a_tok else ''}"
        def_with_a = f"{def_n_tok}{' (' + def_a_tok + ')' if def_a_tok else ''}"

        if outcome == "peace":
            headline = f"Peace reached: {att_label} ({att_a}) vs {def_label} ({def_a})"
            intro_template = _pick(_WAR_PEACE_INTROS)
            intro = _format_dialog(
                intro_template,
                attacker=att_label,
                att_alliance=att_a,
                defender=def_label,
                def_alliance=def_a,
                war_type=war_type
            )
            _peace_bodies = [
                f"{att_with_a} and {def_with_a} have agreed to peace. The Reaper closes this chapter in his ledger — though he suspects it will reopen soon enough.",
                f"The guns fall silent between {att_with_a} and {def_with_a}. Peace has been declared. The Reaper is skeptical it will last, but records it faithfully.",
                f"Peace. {att_with_a} and {def_with_a} have chosen to stop fighting. For now. The Reaper files this under 'temporary arrangements'.",
                f"Both sides have agreed to end hostilities. {att_with_a} and {def_with_a} shake hands across the battlefield. The Reaper watches with mild cynicism.",
            ]
            body = f"{intro} {_pick(_peace_bodies)}"
        elif outcome == "attacker_win":
            if att_nw:
                headline = f"Darkstar victory: {att_label} defeats {def_label} ({def_a})"
                intro_template = _pick(_NW_WIN_INTROS)
                intro = _format_dialog(
                    intro_template,
                    nation=att_label,
                    war_type=war_type,
                    defender=def_label
                )
                _nw_win_bodies = [
                    f"The Darkstar, through {att_n_tok}, has defeated {def_with_a}. The dark banners fly over the battlefield. The Reaper records this victory with deep satisfaction. The Watch's enemies have been reminded of the cost of opposition.",
                    f"Victory for the Darkstar. {att_n_tok} has crushed {def_with_a}. The Reaper is pleased. The Watch is victorious. The enemy is not. This is the correct order of things.",
                    f"The Watch wins. {att_n_tok} defeats {def_with_a} decisively. The Reaper raises a skeletal fist in triumph. Another enemy falls. The Watch endures.",
                    f"Glorious victory for the Darkstar. {att_n_tok} has defeated {def_with_a}. The Reaper smiles — a rare and terrifying sight. The Watch has proven, once again, why it is feared.",
                ]
                body = f"{intro} {_pick(_nw_win_bodies)}"
            elif def_nw:
                headline = f"Darkstar defeated: {att_label} ({att_a}) defeats {def_label}"
                intro_template = _pick(_NW_LOSS_INTROS)
                intro = _format_dialog(
                    intro_template,
                    nation=def_label,
                    war_type=war_type,
                    defender=att_label
                )
                _nw_loss_bodies = [
                    f"{att_with_a} has defeated {def_n_tok} of the Darkstar. The Reaper mourns this outcome. The Watch has suffered a defeat, but it does not break. It remembers. And it will return.",
                    f"The Darkstar has fallen in battle. {att_with_a} defeats {def_n_tok}. The Reaper is furious. This is not how this was supposed to go. The Watch will recover. The Watch will remember.",
                    f"Defeat for the Darkstar. {def_n_tok} has been beaten by {att_with_a}. The Reaper mourns every loss. But the Watch is not finished. It is never finished.",
                    f"A dark day. {att_with_a} has defeated {def_n_tok} of the Darkstar. The Reaper records this loss with a heavy hand. The Watch will rise again. It always does.",
                ]
                body = f"{intro} {_pick(_nw_loss_bodies)}"
            else:
                headline = f"{att_label} ({att_a}) defeats {def_label} ({def_a})"
                intro_template = _pick(_WAR_DECLARED_INTROS)
                intro = _format_dialog(
                    intro_template,
                    attacker=att_label,
                    att_alliance=att_a,
                    defender=def_label,
                    def_alliance=def_a,
                    war_type=war_type
                )
                _non_nw_win_bodies = [
                    f"The conflict between {att_with_a} and {def_with_a} has concluded. The attacker stands victorious. The Reaper records the outcome and moves on.",
                    f"{att_with_a} defeats {def_with_a}. War has a winner today. The Reaper notes it.",
                    f"Victory for {att_with_a} over {def_with_a}. The battlefield has spoken. The Reaper records the verdict.",
                    f"The war ends. {att_with_a} wins. {def_with_a} loses. The Reaper files the paperwork.",
                ]
                body = f"{intro} {_pick(_non_nw_win_bodies)}"
        elif outcome == "defender_win":
            if def_nw:
                headline = f"Darkstar repels attack: {def_label} defeats {att_label} ({att_a})"
                intro_template = _pick(_NW_WIN_INTROS)
                intro = _format_dialog(
                    intro_template,
                    nation=def_label,
                    war_type=war_type,
                    defender=att_label
                )
                _nw_def_win_bodies = [
                    f"The Darkstar has repelled the aggression of {att_with_a}. {def_n_tok} stood firm and emerged victorious. The Reaper nods approvingly. The Watch does not fall easily — and those who try learn this lesson the hard way.",
                    f"The Watch defends. The Watch wins. {def_n_tok} repels {att_with_a}. The Reaper is delighted. The aggressor has learned an expensive lesson.",
                    f"Victory in defense for the Darkstar. {def_n_tok} has defeated {att_with_a}. The Watch held. The Watch always holds. The Reaper is proud.",
                    f"The Darkstar was attacked. The Darkstar won. {def_n_tok} defeats {att_with_a}. The Reaper smiles. This is the correct outcome.",
                ]
                body = f"{intro} {_pick(_nw_def_win_bodies)}"
            elif att_nw:
                headline = f"Darkstar repelled: {def_label} ({def_a}) defeats {att_label}"
                intro_template = _pick(_NW_LOSS_INTROS)
                intro = _format_dialog(
                    intro_template,
                    nation=att_label,
                    war_type=war_type,
                    defender=def_label
                )
                _nw_att_loss_bodies = [
                    f"The Darkstar offensive led by {att_n_tok} has been repelled by {def_with_a}. A setback for the Watch. The Reaper is displeased. The Watch will regroup and reassess.",
                    f"The Watch's attack has failed. {def_with_a} repels {att_n_tok} of the Darkstar. The Reaper is not happy. The Watch will learn from this.",
                    f"Defeat for the Darkstar on the offensive. {att_n_tok} is repelled by {def_with_a}. The Reaper records this setback. The Watch will be back.",
                    f"The Watch attacked. The Watch was stopped. {def_with_a} defeats {att_n_tok}. The Reaper mourns the loss. The Watch will try again.",
                ]
                body = f"{intro} {_pick(_nw_att_loss_bodies)}"
            else:
                headline = f"{def_label} ({def_a}) repels {att_label} ({att_a})"
                _non_nw_def_win_bodies = [
                    f"The defender, {def_with_a}, has repelled the attack from {att_with_a}. The Reaper records the outcome.",
                    f"{def_with_a} wins the defensive war against {att_with_a}. The attacker is repelled. The Reaper notes the result.",
                    f"Defense wins today. {def_with_a} defeats {att_with_a}. The Reaper files the outcome.",
                    f"The attack fails. {def_with_a} repels {att_with_a}. The Reaper records the defender's victory.",
                ]
                body = _pick(_non_nw_def_win_bodies)
        else:
            headline = f"War expires: {att_label} ({att_a}) vs {def_label} ({def_a})"
            intro_template = _pick(_WAR_PEACE_INTROS)
            intro = _format_dialog(
                intro_template,
                attacker=att_label,
                att_alliance=att_a,
                defender=def_label,
                def_alliance=def_a,
                war_type=war_type
            )
            _expire_bodies = [
                f"The war between {att_with_a} and {def_with_a} has expired without a decisive victor. The Reaper shrugs. Some conflicts simply... fizzle out.",
                f"Time runs out on the war between {att_with_a} and {def_with_a}. No winner. No loser. Just... an ending. The Reaper files it under 'inconclusive'.",
                f"The war expires. {att_with_a} and {def_with_a} fought to a standstill. The Reaper closes the file. Neither side should be proud.",
                f"Expired. The war between {att_with_a} and {def_with_a} ends not with a bang but with a bureaucratic whimper. The Reaper is mildly disappointed.",
            ]
            body = f"{intro} {_pick(_expire_bodies)}"

        _detail = {
            "body": body,
            "war_id": war_id,
            "war_type": war_type,
            "end_reason": end_reason,
            "outcome": outcome,
            "winner_id": winner_id,
            "is_nw_attacker": att_nw,
            "is_nw_defender": def_nw,
            "attacker": {
                "id": att_nation_id,
                "name": att_nation_name,
                "alliance_id": att_alliance_id,
                "alliance_name": att_alliance_name,
            },
            "defender": {
                "id": def_nation_id,
                "name": def_nation_name,
                "alliance_id": def_alliance_id,
                "alliance_name": def_alliance_name,
            },
        }

        await db.record_event(
            event_type="war_ended",
            nation_id=att_nation_id,
            nation_name=att_nation_name,
            nation_flag=att_nation_flag,
            alliance_id=att_alliance_id,
            alliance_name=att_alliance_name,
            alliance_flag=att_alliance_flag,
            sec_nation_id=def_nation_id,
            sec_nation_name=def_nation_name,
            sec_alliance_id=def_alliance_id,
            sec_alliance_name=def_alliance_name,
            value=float(war_id),
            value2=0.0,
            headline=headline,
            detail=_detail,
            event_date=event_date or _now_str(),
            alliance_delta={
                "wars_won":   1 if att_won else 0,
                "wars_lost":  1 if def_won else 0,
                "wars_drawn": 1 if outcome in ("peace", "expired") else 0,
            },
            nation_delta={
                "wars_won":  1 if att_won else 0,
                "wars_lost": 1 if def_won else 0,
            },
            sec_alliance_delta={
                "wars_won":   1 if def_won else 0,
                "wars_lost":  1 if att_won else 0,
                "wars_drawn": 1 if outcome in ("peace", "expired") else 0,
            } if def_alliance_id and def_alliance_id != att_alliance_id else {},
            sec_nation_delta={
                "wars_won":  1 if def_won else 0,
                "wars_lost": 1 if att_won else 0,
            },
        )
    except Exception as e:
        logger.error(f"NewsWriter.record_war_ended: {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Nuke / Missile attack
# ─────────────────────────────────────────────────────────────────────────────

async def record_wmd_attack(
    attack_type: str,  # "nuke" | "missile"
    att_nation_id: int,
    att_nation_name: Optional[str],
    att_nation_flag: Optional[str],
    att_alliance_id: Optional[int],
    att_alliance_name: Optional[str],
    att_alliance_flag: Optional[str],
    def_nation_id: int,
    def_nation_name: Optional[str],
    def_nation_flag: Optional[str],
    def_alliance_id: Optional[int],
    def_alliance_name: Optional[str],
    def_alliance_flag: Optional[str],
    infra_destroyed_value: float,
    event_date: Optional[str] = None,
    # New: whether the attack missed (success=False from API)
    missed: bool = False,
    # New: resistance lost by defender
    resistance_lost: Optional[int] = None,
    # New: improvements destroyed {name: count}
    improvements_destroyed: Optional[Dict[str, int]] = None,
    # New: units destroyed {type: count}
    units_destroyed: Optional[Dict[str, int]] = None,
) -> None:
    try:
        # Input validation
        _validate_nation_data(att_nation_id, att_nation_name, att_alliance_id)
        _validate_nation_data(def_nation_id, def_nation_name, def_alliance_id)
        _validate_money_value(infra_destroyed_value, "infra_destroyed_value")
        if not attack_type:
            raise ValueError("attack_type cannot be empty")
        
        # Normalise blank/zero alliance names
        if att_alliance_name and str(att_alliance_name).strip() in ("0", ""):
            att_alliance_name = None
        if def_alliance_name and str(def_alliance_name).strip() in ("0", ""):
            def_alliance_name = None

        # Fill in missing info from GlobalNations.db
        if att_nation_id and (not att_nation_name or not att_alliance_name):
            _a = _lookup_nation_from_db(att_nation_id)
            att_nation_name   = att_nation_name   or _a.get("nation_name")
            att_alliance_id   = att_alliance_id   or _a.get("alliance_id")
            att_alliance_name = att_alliance_name or _a.get("alliance_name")
        if def_nation_id and (not def_nation_name or not def_alliance_name):
            _d = _lookup_nation_from_db(def_nation_id)
            def_nation_name   = def_nation_name   or _d.get("nation_name")
            def_alliance_id   = def_alliance_id   or _d.get("alliance_id")
            def_alliance_name = def_alliance_name or _d.get("alliance_name")

        db = get_news_db()
        att_label = _nation_label(att_nation_name, att_nation_id)
        def_label = _nation_label(def_nation_name, def_nation_id)
        att_a = _alliance_label(att_alliance_name, att_alliance_id)
        def_a = _alliance_label(def_alliance_name, def_alliance_id)
        # Token versions for clickable links in body text
        att_n_tok = _nation_token(att_nation_id, att_nation_name)
        att_a_tok = _alliance_token(att_alliance_id, att_alliance_name)
        def_n_tok = _nation_token(def_nation_id, def_nation_name)
        def_a_tok = _alliance_token(def_alliance_id, def_alliance_name)
        att_with_a = f"{att_n_tok}{' (' + att_a_tok + ')' if att_a_tok else ''}"
        def_with_a = f"{def_n_tok}{' (' + def_a_tok + ')' if def_a_tok else ''}"

        att_nw = _is_nw(att_alliance_id)
        def_nw = _is_nw(def_alliance_id)

        weapon = "nuclear warhead" if attack_type == "nuke" else "missile"
        weapon_cap = "Nuclear Warhead" if attack_type == "nuke" else "Missile"

        # ── Build damage breakdown table (similar to loot table) ─────────────
        _dmg_lines = []
        if infra_destroyed_value > 0:
            _dmg_lines.append(f"🏗️ {_fmt_money(infra_destroyed_value)} infrastructure destroyed")
        if improvements_destroyed:
            for imp_name, count in sorted(improvements_destroyed.items(), key=lambda x: -x[1]):
                display_name = _fmt_improvement_name(imp_name)
                # Get improvement cost from pnw_costs
                try:
                    from PnWHarvester.db.pnw_costs import IMPROVEMENT_COSTS
                    cost = IMPROVEMENT_COSTS.get(imp_name, 0)
                    total_cost = cost * count
                    _dmg_lines.append(f"🔨 {count}x {display_name} = {_fmt_money(total_cost)}")
                except Exception:
                    _dmg_lines.append(f"🔨 {count}x {display_name}")
        if units_destroyed:
            for unit_type, count in sorted(units_destroyed.items(), key=lambda x: -x[1]):
                unit_label = _fmt_unit(unit_type, count)
                # Get unit cost from pnw_costs
                try:
                    from PnWHarvester.db.pnw_costs import MILITARY_COSTS
                    cost = MILITARY_COSTS.get(unit_type, 0)
                    total_cost = cost * count
                    _dmg_lines.append(f"⚔️ {count}x {unit_label} = {_fmt_money(total_cost)}")
                except Exception:
                    _dmg_lines.append(f"⚔️ {count}x {unit_label}")
        if resistance_lost:
            _dmg_lines.append(f"🛡️ Resistance reduced by {resistance_lost}")
        
        _dmg_table = " | ".join(_dmg_lines) if _dmg_lines else "no significant damage"
        _dmg_line = f"<br><br>💥 {_dmg_table}" if _dmg_lines else ""

        if missed:
            # ── MISSED — hilarious ────────────────────────────────────────────
            headline = (
                f"{att_label} ({att_a}) fires {weapon} at {def_label} ({def_a}) — and misses"
            )
            intro_template = _pick(_MISS_INTROS)
            if att_nw:
                intro = _format_dialog(
                    intro_template,
                    nation=att_label,
                    weapon=weapon
                )
            else:
                intro = _format_dialog(
                    intro_template,
                    nation=att_label,
                    alliance=att_a,
                    weapon=weapon
                )
            if att_nw:
                # NW is the attacker — embarrassing miss for the Watch
                _nw_miss_bodies = [
                    (
                        f"In a development that the Reaper will be dining out on for weeks, "
                        f"the Darkstar — specifically {att_n_tok} — has fired a {weapon} "
                        f"at {def_with_a} and somehow managed to miss. "
                        f"The {weapon} has gone... somewhere. Not where intended. "
                        f"The Reaper suggests the Watch invest in better targeting systems. "
                        f"Or perhaps just aim. {def_n_tok} is reportedly confused but unharmed."
                    ),
                    (
                        f"The Darkstar has achieved something remarkable today: "
                        f"firing a {weapon} and hitting absolutely nothing. "
                        f"{att_n_tok} launched at {def_with_a} and missed entirely. "
                        f"The Reaper is trying very hard not to laugh. He is failing. "
                        f"The Watch's targeting department has some explaining to do."
                    ),
                    (
                        f"Well. This is embarrassing. {att_n_tok} of the Darkstar "
                        f"fired a {weapon} at {def_with_a}. "
                        f"The {weapon} did not arrive at its intended destination. "
                        f"The Reaper has added this to his list of 'things I did not expect to witness'. "
                        f"The Watch will not speak of this. The Reaper absolutely will."
                    ),
                    (
                        f"The Darkstar fires. The Darkstar misses. "
                        f"{att_n_tok}'s {weapon} aimed at {def_with_a} has gone rogue. "
                        f"The Reaper is laughing so hard his bones are rattling. "
                        f"The Watch's enemies are confused. The Watch is embarrassed. "
                        f"The Reaper is entertained. At least someone is."
                    ),
                ]
                body = f"{intro} {_pick(_nw_miss_bodies)}"
            elif def_nw:
                # NW is the defender — someone tried to hit the Watch and missed
                _nw_def_miss_bodies = [
                    (
                        f"{att_with_a} attempted to strike the Darkstar with a {weapon} "
                        f"and has achieved the remarkable feat of missing entirely. "
                        f"The Darkstar is unharmed. The Reaper is laughing. "
                        f"The {weapon} has been located approximately nowhere useful. "
                        f"Perhaps {att_n_tok} should consider a different career path."
                    ),
                    (
                        f"Someone tried to bomb the Darkstar. That someone is {att_with_a}. "
                        f"That someone missed. Completely. Spectacularly. "
                        f"The Watch is unharmed and mildly amused. "
                        f"The Reaper is delighted. This is the best thing that has happened all week."
                    ),
                    (
                        f"The Darkstar dodges a {weapon} today — not through skill, "
                        f"but because {att_with_a} couldn't hit the broad side of a continent. "
                        f"The Watch stands unscathed. The attacker stands humiliated. "
                        f"The Reaper is filing this under 'comedy gold'."
                    ),
                    (
                        f"{att_with_a} spent considerable resources on a {weapon} "
                        f"aimed at the Darkstar. The Darkstar is fine. "
                        f"The {weapon} is... somewhere. Not here. "
                        f"The Reaper suggests {att_n_tok} ask for a refund on their targeting system."
                    ),
                ]
                body = f"{intro} {_pick(_nw_def_miss_bodies)}"
            else:
                _miss_bodies = [
                    (
                        f"{att_with_a} launched a {weapon} at {def_with_a} "
                        f"and missed. The Reaper has seen many things in his long existence. "
                        f"This ranks among the more embarrassing. "
                        f"{def_n_tok} is unharmed and presumably bewildered."
                    ),
                    (
                        f"A {weapon} was fired. A {weapon} missed. "
                        f"{att_with_a} aimed at {def_with_a} and hit nothing. "
                        f"The Reaper records this with barely concealed amusement. "
                        f"The {weapon} is currently unaccounted for."
                    ),
                    (
                        f"Today in Orbis: {att_with_a} fires a {weapon} at {def_with_a}. "
                        f"The {weapon} does not reach its target. "
                        f"The Reaper notes this failure with professional detachment and personal delight. "
                        f"{def_n_tok} is fine. {att_n_tok} is not having a great day."
                    ),
                    (
                        f"The {weapon} missed. That's the whole story. "
                        f"{att_with_a} fired at {def_with_a}. "
                        f"The {weapon} went elsewhere. The Reaper is adding this to his highlight reel."
                    ),
                ]
                body = f"{intro} {_pick(_miss_bodies)}"
        else:
            # ── HIT ──────────────────────────────────────────────────────────
            damage_str = (
                f" — {_fmt_money(infra_destroyed_value)} in infrastructure damage"
                if infra_destroyed_value > 0 else ""
            )
            headline = (
                f"{att_label} ({att_a}) launches {weapon} at {def_label} ({def_a}){damage_str}"
            )

            if att_nw:
                intro_template = _pick(_NW_FIRES_WMD_INTROS)
                intro = _format_dialog(
                    intro_template,
                    nation=att_label,
                    weapon=weapon,
                    defender=def_label
                )
                _nw_fires_bodies = [
                    (
                        f"The Darkstar, through {att_n_tok}, has launched a {weapon} "
                        f"against {def_with_a}.{_dmg_line} "
                        f"The Reaper delivers the Watch's message with precision. "
                        f"Let {def_n_tok} remember this day."
                    ),
                    (
                        f"The Watch's arsenal speaks. {att_n_tok} launches a {weapon} at {def_with_a}.{_dmg_line} "
                        f"The Darkstar does not fire warnings. It fires {weapon}s. "
                        f"The Reaper approves of this communication style."
                    ),
                    (
                        f"The Darkstar has sent {def_with_a} a message. "
                        f"The message is a {weapon}.{_dmg_line} "
                        f"The Reaper hopes the message was received clearly. "
                        f"It usually is, when delivered this way."
                    ),
                    (
                        f"{att_n_tok} of the Darkstar strikes {def_with_a} with a {weapon}.{_dmg_line} "
                        f"The Watch's enemies are learning an expensive lesson today. "
                        f"The Reaper is taking notes. And enjoying every moment."
                    ),
                ]
                body = f"{intro} {_pick(_nw_fires_bodies)}"
            elif def_nw:
                intro_template = _pick(_NW_HIT_WMD_INTROS)
                intro = _format_dialog(
                    intro_template,
                    nation=def_label,
                    weapon=weapon,
                    attacker=att_label
                )
                _nw_hit_bodies = [
                    (
                        f"{att_with_a} has launched a {weapon} against "
                        f"the Darkstar, striking {def_n_tok}.{_dmg_line} "
                        f"The Reaper mourns this damage to the Watch. "
                        f"But the Watch endures. And it remembers every stone that falls."
                    ),
                    (
                        f"A {weapon} has struck the Darkstar. "
                        f"{att_with_a} is responsible.{_dmg_line} "
                        f"The Reaper is furious. The Watch is wounded. "
                        f"The attacker has made a very powerful enemy today."
                    ),
                    (
                        f"The Darkstar has been bombed. {att_with_a} "
                        f"strikes {def_n_tok} with a {weapon}.{_dmg_line} "
                        f"The Reaper records every stone that falls, every improvement that burns. "
                        f"The Watch will rebuild. And then it will respond."
                    ),
                    (
                        f"A cowardly strike against the Darkstar. "
                        f"{att_with_a} fires a {weapon} at {def_n_tok}.{_dmg_line} "
                        f"The Reaper is not pleased. The Watch is not pleased. "
                        f"The attacker should not be pleased with what comes next."
                    ),
                ]
                body = f"{intro} {_pick(_nw_hit_bodies)}"
            else:
                intro_template = _pick(_MISS_INTROS)
                intro = _format_dialog(
                    intro_template,
                    nation=att_label,
                    defender=def_label,
                    weapon=weapon
                )
                _non_nw_wmd_bodies = [
                    (
                        f"{att_with_a} has launched a {weapon} against {def_with_a}.{_dmg_line} "
                        f"The Reaper records the strike and moves on."
                    ),
                    (
                        f"A {weapon} flies from {att_with_a} to {def_with_a}.{_dmg_line} "
                        f"The Reaper notes the exchange. Another day in Orbis."
                    ),
                    (
                        f"{att_with_a} strikes {def_with_a} with a {weapon}.{_dmg_line} "
                        f"The Reaper files the paperwork. There is always paperwork."
                    ),
                    (
                        f"The {weapon} lands. {att_with_a} hits {def_with_a}.{_dmg_line} "
                        f"The Reaper records the outcome with professional efficiency."
                    ),
                ]
                body = f"{intro} {_pick(_non_nw_wmd_bodies)}"

        # ── Calculate improvement destruction costs ───────────────────────────
        # Use the same IMPROVEMENT_RESOURCE_COSTS / IMPROVEMENT_CASH_COSTS maps
        # as the city_upgrade pipeline so costs are always consistent.
        # Normalise _plant suffix: API sometimes sends 'nuclear_power_plant'
        # but DB column names (and our cost maps) use 'nuclear_power' etc.
        from PnWHarvester.db.pnw_costs import IMPROVEMENT_RESOURCE_COSTS, IMPROVEMENT_CASH_COSTS
        _IMP_ALIAS = {
            "nuclear_power_plant": "nuclear_power",
            "wind_power_plant":    "wind_power",
            "coal_power_plant":    "coal_power",
            "oil_power_plant":     "oil_power",
        }
        _imp_cash_cost = 0.0
        _imp_rss: Dict[str, float] = {}
        if improvements_destroyed and not missed:
            for _col_raw, _count in improvements_destroyed.items():
                if _count <= 0:
                    continue
                _col = _IMP_ALIAS.get(_col_raw, _col_raw)
                _imp_cash_cost += IMPROVEMENT_CASH_COSTS.get(_col, 0.0) * _count
                for _res, _per_unit in (IMPROVEMENT_RESOURCE_COSTS.get(_col) or {}).items():
                    _imp_rss[_res] = _imp_rss.get(_res, 0.0) + _per_unit * _count

        # Calculate resource value using shared helper
        _imp_rss_value = _calculate_resource_value(_imp_rss)
        _total_destruction_value = infra_destroyed_value + _imp_cash_cost + _imp_rss_value

        await db.record_event(
            event_type="wmd_attack",
            nation_id=att_nation_id,
            nation_name=att_nation_name,
            nation_flag=att_nation_flag,
            alliance_id=att_alliance_id,
            alliance_name=att_alliance_name,
            alliance_flag=att_alliance_flag,
            sec_nation_id=def_nation_id,
            sec_nation_name=def_nation_name,
            sec_alliance_id=def_alliance_id,
            sec_alliance_name=def_alliance_name,
            value=_total_destruction_value,
            value2=0.0,
            headline=headline,
            detail={
                "body": body,
                "attack_type": attack_type,
                "missed": missed,
                "resistance_lost": resistance_lost,
                "improvements_destroyed": improvements_destroyed or {},
                "units_destroyed": units_destroyed or {},
                "improvements_cash_cost": _imp_cash_cost if _imp_cash_cost > 0 else None,
                "resource_costs": _imp_rss if _imp_rss else None,
                "resource_value": _imp_rss_value if _imp_rss_value > 0 else None,
                "infra_destroyed_value": infra_destroyed_value,
                "total_destruction_value": _total_destruction_value if _total_destruction_value > 0 else None,
                "is_nw_attacker": att_nw,
                "is_nw_defender": def_nw,
                "attacker": {
                    "id": att_nation_id,
                    "name": att_nation_name,
                    "alliance_id": att_alliance_id,
                    "alliance_name": att_alliance_name,
                },
                "defender": {
                    "id": def_nation_id,
                    "name": def_nation_name,
                    "alliance_id": def_alliance_id,
                    "alliance_name": def_alliance_name,
                },
            },
            event_date=event_date or _now_str(),
            alliance_delta={
                "nukes_used": 1 if attack_type == "nuke" else 0,
                "missiles_used": 1 if attack_type == "missile" else 0,
                "infra_destroyed": infra_destroyed_value,
            },
            nation_delta={},
        )
    except Exception as e:
        logger.error(f"NewsWriter.record_wmd_attack: {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Loot attack
# ─────────────────────────────────────────────────────────────────────────────

async def record_loot_attack(
    att_nation_id: int,
    att_nation_name: Optional[str],
    att_nation_flag: Optional[str],
    att_alliance_id: Optional[int],
    att_alliance_name: Optional[str],
    att_alliance_flag: Optional[str],
    def_nation_id: int,
    def_nation_name: Optional[str],
    def_nation_flag: Optional[str],
    def_alliance_id: Optional[int],
    def_alliance_name: Optional[str],
    money_looted: float,
    total_loot_value: float,
    event_date: Optional[str] = None,
    # New: full resource breakdown
    resources_looted: Optional[Dict[str, float]] = None,
    # New: improvements destroyed in this attack
    improvements_destroyed: Optional[Dict[str, int]] = None,
    # New: infra destroyed value
    infra_destroyed_value: float = 0.0,
) -> None:
    try:
        # Input validation
        _validate_nation_data(att_nation_id, att_nation_name, att_alliance_id)
        # Skip defender validation if it's an alliance bank (def_nation_id=0)
        if def_nation_id != 0:
            _validate_nation_data(def_nation_id, def_nation_name, def_alliance_id)
        _validate_money_value(money_looted, "money_looted")
        _validate_money_value(total_loot_value, "total_loot_value")
        _validate_money_value(infra_destroyed_value, "infra_destroyed_value")
        
        # Alliance bank loot (def_nation_id=0) has lower threshold since it's rarer and more significant
        threshold = LOOT_ATTACK_THRESHOLD if def_nation_id != 0 else 1_000_000  # $1M for alliance bank loot
        is_newsworthy = total_loot_value >= threshold

        if att_nation_id and (not att_nation_name or not att_alliance_name):
            _a = _lookup_nation_from_db(att_nation_id)
            att_nation_name   = att_nation_name   or _a.get("nation_name")
            att_alliance_id   = att_alliance_id   or _a.get("alliance_id")
            att_alliance_name = att_alliance_name or _a.get("alliance_name")

        # Handle alliance bank case (def_nation_id=0 means alliance bank, not a nation)
        if def_nation_id and (not def_nation_name or not def_alliance_name):
            _d = _lookup_nation_from_db(def_nation_id)
            def_nation_name   = def_nation_name   or _d.get("nation_name")
            def_alliance_id   = def_alliance_id   or _d.get("alliance_id")
            def_alliance_name = def_alliance_name or _d.get("alliance_name")
        elif def_nation_id == 0:
            # Alliance bank - use provided alliance info
            def_nation_name = def_nation_name or def_alliance_name or "alliance bank"
            # def_alliance_id and def_alliance_name should already be set

        db = get_news_db()
        att_label = _nation_label(att_nation_name, att_nation_id)
        def_label = _nation_label(def_nation_name, def_nation_id)
        att_a = _alliance_label(att_alliance_name, att_alliance_id)
        def_a = _alliance_label(def_alliance_name, def_alliance_id)
        # Token versions for clickable links in body text
        att_n_tok = _nation_token(att_nation_id, att_nation_name)
        att_a_tok = _alliance_token(att_alliance_id, att_alliance_name)
        def_n_tok = _nation_token(def_nation_id, def_nation_name)
        def_a_tok = _alliance_token(def_alliance_id, def_alliance_name)
        att_with_a = f"{att_n_tok}{' (' + att_a_tok + ')' if att_a_tok else ''}"
        def_with_a = f"{def_n_tok}{' (' + def_a_tok + ')' if def_a_tok else ''}"

        att_nw = _is_nw(att_alliance_id)
        def_nw = _is_nw(def_alliance_id)
        is_alliance_bank = def_nation_id == 0  # Alliance bank, not a nation

        if is_alliance_bank:
            headline = (
                f"{att_label} ({att_a}) loots {_fmt_money(total_loot_value)} "
                f"from {def_a}"
            )
        else:
            headline = (
                f"{att_label} ({att_a}) loots {_fmt_money(total_loot_value)} "
                f"from {def_label} ({def_a})"
            )

        # Build article body — Reaper commentary + loot breakdown with static icons.
        # _fmt_loot_table() produces HTML <img> tags from /static/Emojis/Resources/
        # and live sell prices from reaper.db.
        # For alliance bank loots (from bank records), only show money/resources - no infra/improvements
        if is_alliance_bank:
            loot_table = _fmt_loot_table(
                money_looted=money_looted,
                resources_looted=resources_looted,
                infra_destroyed_value=0.0,  # No infra destroyed in bank loots
                improvements_destroyed=None,  # No improvements destroyed in bank loots
            )
        else:
            loot_table = _fmt_loot_table(
                money_looted=money_looted,
                resources_looted=resources_looted,
                infra_destroyed_value=infra_destroyed_value,
                improvements_destroyed=improvements_destroyed,
            )
        loot_line = f"<br><br>📋 {loot_table}" if loot_table != "nothing of note" else ""

        if is_alliance_bank:
            # Alliance bank loot - use alliance loot dialog
            intro_template = _pick(_ALLIANCE_LOOT_INTROS)
            intro = _format_dialog(
                intro_template,
                sender=att_label,
                sender_alliance=att_a,
                resources=_fmt_money(total_loot_value)
            )
            _alliance_loot_bodies = [
                (
                    f"{att_with_a} has successfully looted the alliance bank, "
                    f"seizing {_fmt_money(total_loot_value)} in total value.{loot_line} "
                    f"The Reaper observes this transfer of wealth with interest."
                ),
                (
                    f"The alliance bank has been raided. {att_with_a} takes "
                    f"{_fmt_money(total_loot_value)} from the treasury.{loot_line} "
                    f"The Reaper notes the redistribution of resources."
                ),
            ]
            body = f"{intro} {_pick(_alliance_loot_bodies)}"
        elif att_nw:
            intro_template = _pick(_NW_LOOT_INTROS)
            intro = _format_dialog(
                intro_template,
                nation=att_label,
                defender=def_label
            )
            _nw_loot_bodies = [
                (
                    f"The Darkstar, through {att_n_tok}, has successfully looted "
                    f"{def_with_a}, seizing {_fmt_money(total_loot_value)} in total value.{loot_line} "
                    f"The Reaper approves. The Watch's coffers grow heavier, and {def_n_tok}'s grow lighter."
                ),
                (
                    f"The Watch raids and wins. {att_n_tok} loots {def_with_a} "
                    f"for {_fmt_money(total_loot_value)} total.{loot_line} "
                    f"The Reaper smiles. The Watch's treasury grows. "
                    f"This is how the Darkstar funds its dominance."
                ),
                (
                    f"Another successful raid for the Darkstar. "
                    f"{att_n_tok} strips {def_with_a} of {_fmt_money(total_loot_value)}.{loot_line} "
                    f"The Reaper is pleased. The Watch takes what it needs. "
                    f"The enemy provides what the Watch takes."
                ),
                (
                    f"{att_n_tok} loots {_fmt_money(total_loot_value)} from {def_with_a}.{loot_line} "
                    f"Death smiles upon this acquisition. "
                    f"The Watch grows richer. Its enemies grow poorer. As it should be."
                ),
            ]
            body = f"{intro} {_pick(_nw_loot_bodies)}"
        elif def_nw:
            intro_template = _pick(_NW_LOOTED_INTROS)
            intro = _format_dialog(
                intro_template,
                nation=def_label,
                attacker=att_label
            )
            _nw_looted_bodies = [
                (
                    f"{att_with_a} has looted the Darkstar, "
                    f"stripping {def_n_tok} of {_fmt_money(total_loot_value)} in total value.{loot_line} "
                    f"The Reaper is displeased. This theft will not be forgotten. "
                    f"The Darkstar has a long memory and a longer reach."
                ),
                (
                    f"{att_with_a} has robbed the Darkstar, "
                    f"taking {_fmt_money(total_loot_value)} from {def_n_tok}.{loot_line} "
                    f"The Reaper mourns every coin, every resource taken from the Watch. "
                    f"The thief has made a powerful enemy. The Watch remembers."
                ),
                (
                    f"A painful day for the Darkstar. {att_with_a} raids {def_n_tok} "
                    f"and walks away with {_fmt_money(total_loot_value)}.{loot_line} "
                    f"The Reaper is furious. The Watch is furious. "
                    f"The attacker should be very, very careful going forward."
                ),
                (
                    f"Theft. Against the Darkstar. {att_with_a} loots "
                    f"{def_n_tok} for {_fmt_money(total_loot_value)}.{loot_line} "
                    f"The Reaper marks the thief's name in his ledger. "
                    f"The Watch will find them. The Watch always finds them."
                ),
            ]
            body = f"{intro} {_pick(_nw_looted_bodies)}"
        else:
            intro_template = _pick(_LOOT_INTROS)
            intro = _format_dialog(
                intro_template,
                attacker=att_label,
                att_alliance=att_a,
                defender=def_label,
                def_alliance=def_a
            )
            _non_nw_loot_bodies = [
                (
                    f"{att_with_a} has looted {def_with_a}, "
                    f"taking {_fmt_money(total_loot_value)} in total value.{loot_line} "
                    f"The Reaper records the transaction."
                ),
                (
                    f"War pays today. {att_with_a} raids {def_with_a} "
                    f"for {_fmt_money(total_loot_value)}.{loot_line} "
                    f"The Reaper notes the transfer of wealth and moves on."
                ),
                (
                    f"The spoils of war: {_fmt_money(total_loot_value)} flows from "
                    f"{def_with_a} to {att_with_a}.{loot_line} "
                    f"The Reaper records the outcome. Another day, another raid."
                ),
                (
                    f"{att_with_a} wins the ground battle and takes "
                    f"{_fmt_money(total_loot_value)} from {def_with_a}.{loot_line} "
                    f"The Reaper files the paperwork. There is always paperwork."
                ),
            ]
            body = f"{intro} {_pick(_non_nw_loot_bodies)}"

        att_alliance_delta = {"loot_gained": total_loot_value, "total_spent": -total_loot_value}
        att_nation_delta   = {"loot_gained": total_loot_value, "total_spent": -total_loot_value}
        def_alliance_delta = (
            {"loot_lost": total_loot_value, "total_spent": total_loot_value}
            if def_alliance_id and def_alliance_id != att_alliance_id else {}
        )
        def_nation_delta = {"loot_lost": total_loot_value, "total_spent": total_loot_value}

        detail = {
            "body": body,
            "is_nw_attacker": att_nw,
            "is_nw_defender": def_nw,
            "attacker": {
                "id": att_nation_id,
                "name": att_nation_name,
                "alliance_id": att_alliance_id,
                "alliance_name": att_alliance_name,
            },
            "defender": {
                "id": def_nation_id,
                "name": def_nation_name,
                "alliance_id": def_alliance_id,
                "alliance_name": def_alliance_name,
            },
            "money_looted": money_looted,
            "total_loot_value": total_loot_value,
            "resources_looted": resources_looted or {},
            "improvements_destroyed": improvements_destroyed or {},
            "infra_destroyed_value": infra_destroyed_value,
        }

        if is_newsworthy:
            await db.record_event(
                event_type="loot_attack",
                nation_id=att_nation_id,
                nation_name=att_nation_name,
                nation_flag=att_nation_flag,
                alliance_id=att_alliance_id,
                alliance_name=att_alliance_name,
                alliance_flag=att_alliance_flag,
                sec_nation_id=def_nation_id,
                sec_nation_name=def_nation_name,
                sec_alliance_id=def_alliance_id,
                sec_alliance_name=def_alliance_name,
                value=total_loot_value,
                value2=money_looted,
                headline=headline,
                detail=detail,
                event_date=event_date or _now_str(),
                alliance_delta=att_alliance_delta,
                nation_delta=att_nation_delta,
                sec_alliance_delta=def_alliance_delta,
                sec_nation_delta=def_nation_delta,
            )
        else:
            # Below threshold — update stats only, no feed row
            await db.update_stats_only(
                nation_id=att_nation_id,
                nation_name=att_nation_name,
                nation_flag=att_nation_flag,
                alliance_id=att_alliance_id,
                alliance_name=att_alliance_name,
                alliance_flag=att_alliance_flag,
                alliance_delta=att_alliance_delta,
                nation_delta=att_nation_delta,
            )
            if def_nation_id:
                await db.update_stats_only(
                    nation_id=def_nation_id,
                    nation_name=def_nation_name,
                    nation_flag=def_nation_flag,
                    alliance_id=def_alliance_id,
                    alliance_name=def_alliance_name,
                    alliance_flag=None,
                    alliance_delta=def_alliance_delta,
                    nation_delta=def_nation_delta,
                )
    except Exception as e:
        logger.error(f"NewsWriter.record_loot_attack: {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Bank transfer
# ─────────────────────────────────────────────────────────────────────────────

_BANK_TRANSFER_FEED_THRESHOLD = 1_000_000  # $1M


def _calc_transfer_value(rec: Dict[str, Any]) -> float:
    _RESOURCES = (
        "coal", "oil", "uranium", "iron", "bauxite", "lead",
        "gasoline", "munitions", "steel", "aluminum", "food",
    )
    money = float(rec.get("money") or 0)
    resource_amounts = {r: float(rec.get(r) or 0) for r in _RESOURCES}
    has_resources = any(v > 0 for v in resource_amounts.values())

    resource_value = 0.0
    if has_resources:
        try:
            import sqlite3 as _sqlite3
            from Systems.Functions.db_paths import REAPER_DB_STR
            _conn = _sqlite3.connect(REAPER_DB_STR)
            rows = _conn.execute(
                "SELECT resource, best_sell_price FROM resource_prices "
                "WHERE timestamp = (SELECT MAX(timestamp) FROM resource_prices)"
            ).fetchall()
            _conn.close()
            prices = {r.lower(): float(p) for r, p in rows if p and float(p) > 0}
            for res, amt in resource_amounts.items():
                resource_value += amt * prices.get(res, 0.0)
        except Exception:
            pass

    return money + resource_value


async def record_bank_transfer(
    rec: Dict[str, Any],
    sender_nation_id: Optional[int] = None,
    sender_nation_name: Optional[str] = None,
    sender_nation_flag: Optional[str] = None,
    sender_alliance_id: Optional[int] = None,
    sender_alliance_name: Optional[str] = None,
    receiver_nation_id: Optional[int] = None,
    receiver_nation_name: Optional[str] = None,
    receiver_nation_flag: Optional[str] = None,
    receiver_alliance_id: Optional[int] = None,
    receiver_alliance_name: Optional[str] = None,
) -> None:
    try:
        # Input validation
        if not rec or not isinstance(rec, dict):
            raise ValueError("rec must be a non-empty dictionary")
        
        stype = int(rec.get("sender_type") or 0)
        rtype = int(rec.get("receiver_type") or 0)
        sid   = int(rec.get("sender_id") or 0)
        rid   = int(rec.get("receiver_id") or 0)
        note  = rec.get("note") or ""
        date  = rec.get("date") or _now_str()

        total_value = _calc_transfer_value(rec)
        money       = float(rec.get("money") or 0)
        
        _validate_money_value(money, "money")
        _validate_money_value(total_value, "total_value")

        _RESOURCES = (
            "coal", "oil", "uranium", "iron", "bauxite", "lead",
            "gasoline", "munitions", "steel", "aluminum", "food",
        )
        resource_amounts = {
            r: float(rec.get(r) or 0) for r in _RESOURCES if float(rec.get(r) or 0) > 0
        }

        _note_lower = note.lower()
        _is_loot = (
            ("defeated" in _note_lower and "captured" in _note_lower and "resources" in _note_lower)
            or "looted from war" in _note_lower
            or "war loot" in _note_lower
            or ("war #" in _note_lower)
        )

        if stype == 1 and rtype == 2:
            event_type = "bank_deposit"
        elif stype == 2 and rtype == 1:
            event_type = "bank_withdrawal"
        elif stype == 1 and rtype == 1 and _is_loot:
            return  # Handled by wars subscription
        elif stype == 1 and rtype == 1:
            event_type = "bank_transfer"
        else:
            return

        # Enrich missing names
        if sender_nation_id and not sender_nation_name:
            _s = _lookup_nation_from_db(sender_nation_id)
            if _s:
                sender_nation_name   = _s.get("nation_name")
                sender_alliance_id   = sender_alliance_id   or _s.get("alliance_id")
                sender_alliance_name = sender_alliance_name or _s.get("alliance_name")
        if receiver_nation_id and not receiver_nation_name:
            _r = _lookup_nation_from_db(receiver_nation_id)
            if _r:
                receiver_nation_name   = _r.get("nation_name")
                receiver_alliance_id   = receiver_alliance_id   or _r.get("alliance_id")
                receiver_alliance_name = receiver_alliance_name or _r.get("alliance_name")
        # Look up alliance names directly when sender/receiver is an alliance (type=2)
        if sender_alliance_id and not sender_alliance_name:
            sender_alliance_name = _lookup_alliance_from_db(sender_alliance_id)
        if receiver_alliance_id and not receiver_alliance_name:
            receiver_alliance_name = _lookup_alliance_from_db(receiver_alliance_id)

        is_newsworthy = total_value >= BANK_TRANSFER_THRESHOLD
        val_str = _fmt_money(total_value)

        if event_type == "bank_deposit":
            n_label = _nation_label(sender_nation_name, sender_nation_id or sid)
            a_label = _alliance_label(receiver_alliance_name, receiver_alliance_id or rid)
            n_tok = _nation_token(sender_nation_id or sid, sender_nation_name)
            a_tok = _alliance_token(receiver_alliance_id or rid, receiver_alliance_name)
            headline = f"{n_label} deposits {val_str} to {a_label}"
            headline_tok = f"{n_tok} deposits {val_str} to {a_tok if a_tok else a_label}"
        elif event_type == "bank_withdrawal":
            a_label = _alliance_label(sender_alliance_name, sender_alliance_id or sid)
            n_label = _nation_label(receiver_nation_name, receiver_nation_id or rid)
            a_tok = _alliance_token(sender_alliance_id or sid, sender_alliance_name)
            n_tok = _nation_token(receiver_nation_id or rid, receiver_nation_name)
            headline = f"{n_label} withdraws {val_str} from {a_label}"
            headline_tok = f"{n_tok} withdraws {val_str} from {a_tok if a_tok else a_label}"
        else:
            s_label = _nation_label(sender_nation_name, sender_nation_id or sid)
            r_label = _nation_label(receiver_nation_name, receiver_nation_id or rid)
            s_tok = _nation_token(sender_nation_id or sid, sender_nation_name)
            r_tok = _nation_token(receiver_nation_id or rid, receiver_nation_name)
            headline = f"{s_label} transfers {val_str} to {r_label}"
            headline_tok = f"{s_tok} transfers {val_str} to {r_tok}"

        # Format resources with expanded table like loot articles
        loot_table = _fmt_loot_table(
            money_looted=money,
            resources_looted=resource_amounts,
            infra_destroyed_value=0.0,
            improvements_destroyed=None,
        )
        loot_line = f"<br><br>📋 {loot_table}" if loot_table != "nothing of note" else ""
        
        # Select appropriate dialog pool based on event type
        if event_type == "bank_deposit":
            intro_template = _pick(_BANK_DEPOSIT_INTROS)
            intro = _format_dialog(
                intro_template,
                sender=n_label,
                sender_alliance=_alliance_label(sender_alliance_name, sender_alliance_id) if sender_alliance_name or sender_alliance_id else "",
                resources=val_str
            )
        elif event_type == "bank_withdrawal":
            intro_template = _pick(_BANK_WITHDRAWAL_INTROS)
            intro = _format_dialog(
                intro_template,
                receiver=n_label,
                receiver_alliance=_alliance_label(receiver_alliance_name, receiver_alliance_id) if receiver_alliance_name or receiver_alliance_id else "",
                resources=val_str
            )
        else:
            intro_template = _pick(_BANK_INTROS)
            intro = _format_dialog(
                intro_template,
                sender=s_label,
                sender_alliance=_alliance_label(sender_alliance_name, sender_alliance_id) if sender_alliance_name or sender_alliance_id else "",
                receiver=r_label,
                receiver_alliance=_alliance_label(receiver_alliance_name, receiver_alliance_id) if receiver_alliance_name or receiver_alliance_id else "",
                resources=val_str
            )
        
        _note_str = f" The note reads: \"{note.strip()}\"." if note and note.strip() else ""
        _bank_bodies = [
            f"{headline_tok}.{_note_str}{loot_line}",
            f"The ledgers record: {headline_tok}.{_note_str}{loot_line} The Reaper notes the transaction.",
            f"{headline_tok}.{_note_str}{loot_line} Wealth moves. The Reaper watches it move.",
            f"Transaction recorded. {headline_tok}.{_note_str}{loot_line} The Reaper files it away.",
        ]
        body = f"{intro} {_pick(_bank_bodies)}"

        # resource_value = total_value minus cash component
        resource_value = round(total_value - money, 2) if resource_amounts else 0.0

        detail: Dict[str, Any] = {
            "body": body,
            "bankrec_id":    rec.get("id"),
            "sender_id":     sid,
            "sender_type":   stype,
            "receiver_id":   rid,
            "receiver_type": rtype,
            "banker_id":     rec.get("banker_id"),
            "money":         money,
            "total_value":   total_value,
            "note":          note,
        }
        if resource_amounts:
            detail["resource_costs"] = resource_amounts
            if resource_value > 0:
                detail["resource_value"] = resource_value

        db = get_news_db()

        if event_type == "bank_deposit":
            primary_nation_id    = sender_nation_id or sid
            primary_nation_name  = sender_nation_name
            primary_nation_flag  = sender_nation_flag
            primary_alliance_id  = receiver_alliance_id or rid
            primary_alliance_name = receiver_alliance_name
            primary_alliance_flag = None
            nation_delta   = {"bank_deposits": total_value}
            alliance_delta = {"bank_deposits": total_value}
        elif event_type == "bank_withdrawal":
            primary_nation_id    = receiver_nation_id or rid
            primary_nation_name  = receiver_nation_name
            primary_nation_flag  = receiver_nation_flag
            primary_alliance_id  = sender_alliance_id or sid
            primary_alliance_name = sender_alliance_name
            primary_alliance_flag = None
            nation_delta   = {"bank_withdrawals": total_value}
            alliance_delta = {"bank_withdrawals": total_value}
        else:
            primary_nation_id    = sender_nation_id or sid
            primary_nation_name  = sender_nation_name
            primary_nation_flag  = sender_nation_flag
            primary_alliance_id  = sender_alliance_id
            primary_alliance_name = sender_alliance_name
            primary_alliance_flag = None
            nation_delta   = {}
            alliance_delta = {}

        if is_newsworthy:
            await db.record_event(
                event_type=event_type,
                nation_id=primary_nation_id,
                nation_name=primary_nation_name,
                nation_flag=primary_nation_flag,
                alliance_id=primary_alliance_id,
                alliance_name=primary_alliance_name,
                alliance_flag=primary_alliance_flag,
                value=total_value,
                value2=money,
                headline=headline,
                detail=detail,
                event_date=date,
                alliance_delta=alliance_delta,
                nation_delta=nation_delta,
            )
        else:
            if nation_delta or alliance_delta:
                await db.update_stats_only(
                    nation_id=primary_nation_id,
                    nation_name=primary_nation_name,
                    nation_flag=primary_nation_flag,
                    alliance_id=primary_alliance_id,
                    alliance_name=primary_alliance_name,
                    alliance_flag=primary_alliance_flag,
                    alliance_delta=alliance_delta,
                    nation_delta=nation_delta,
                )
    except Exception as e:
        logger.error(f"NewsWriter.record_bank_transfer: {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Alliance join / leave
# ─────────────────────────────────────────────────────────────────────────────

async def record_alliance_change(
    nation_id: int,
    nation_name: Optional[str],
    nation_flag: Optional[str],
    old_alliance_id: Optional[int],
    old_alliance_name: Optional[str],
    new_alliance_id: Optional[int],
    new_alliance_name: Optional[str],
    new_alliance_flag: Optional[str],
    event_date: Optional[str] = None,
) -> None:
    try:
        # Input validation
        _validate_nation_data(nation_id, nation_name, new_alliance_id)
        
        db = get_news_db()
        n_label = _nation_label(nation_name, nation_id)
        n_tok = _nation_token(nation_id, nation_name)
        joining_nw  = _is_nw(new_alliance_id)
        leaving_nw  = _is_nw(old_alliance_id)

        # If old and new names are identical but IDs differ, the old name is stale in the DB.
        # Fall back to "Alliance #ID" for the old alliance so the event shows distinct names.
        if (old_alliance_id and new_alliance_id
                and int(old_alliance_id) != int(new_alliance_id)
                and old_alliance_name and old_alliance_name == new_alliance_name):
            old_alliance_name = f"Alliance #{old_alliance_id}"

        old_a_label = _alliance_label(old_alliance_name, old_alliance_id)
        new_a_label = _alliance_label(new_alliance_name, new_alliance_id)
        old_a_tok = _alliance_token(old_alliance_id, old_alliance_name)
        new_a_tok = _alliance_token(new_alliance_id, new_alliance_name)

        if new_alliance_id and not old_alliance_id:
            headline = f"{n_label} joins {new_a_label}"
            event_type = "alliance_join"
            if joining_nw:
                intro_template = _pick(_NW_JOIN_INTROS)
                intro = _format_dialog(
                    intro_template,
                    nation=n_label
                )
                _nw_join_bodies = [
                    f"{n_tok} has taken the oath and joined the Darkstar. The Reaper welcomes this new soul to the fold. The Watch grows stronger. Its enemies should take note.",
                    f"A new warrior joins the Darkstar. {n_tok} has answered the call. The Reaper is pleased. The Watch's ranks swell. The Watch's power grows.",
                    f"{n_tok} has chosen the Darkstar. A wise choice. The Reaper approves. The Watch gains a capable member. The Watch's enemies gain a new problem.",
                    f"The dark banner gains another soldier. {n_tok} joins the Darkstar. The Reaper welcomes them. The Watch is stronger for it. The realm should notice.",
                    f"Welcome to the Darkstar, {n_tok}. The Reaper has been expecting you. The Watch grows. It always grows. That is what the Watch does.",
                ]
                body = f"{intro} {_pick(_nw_join_bodies)}"
            else:
                intro_template = _pick(_ALLIANCE_CHANGE_INTROS)
                intro = _format_dialog(
                    intro_template,
                    nation=n_label,
                    old_alliance=old_a_label,
                    new_alliance=new_a_label
                )
                _non_nw_join_bodies = [
                    f"{n_tok} has joined {new_a_tok if new_a_tok else new_a_label}. The Reaper notes the change.",
                    f"A new alliance for {n_tok}: {new_a_tok if new_a_tok else new_a_label}. The Reaper records the affiliation.",
                    f"{n_tok} finds a new home in {new_a_tok if new_a_tok else new_a_label}. The Reaper updates his files.",
                    f"The political map shifts. {n_tok} joins {new_a_tok if new_a_tok else new_a_label}. The Reaper notes it and moves on.",
                ]
                body = f"{intro} {_pick(_non_nw_join_bodies)}"
        elif old_alliance_id and not new_alliance_id:
            headline = f"{n_label} leaves {old_a_label}"
            event_type = "alliance_leave"
            if leaving_nw:
                intro_template = _pick(_NW_LEAVE_INTROS)
                intro = _format_dialog(
                    intro_template,
                    nation=n_label
                )
                _nw_leave_bodies = [
                    f"{n_tok} has left the Darkstar. The Reaper watches this departure with cold, unblinking eyes. The Watch does not forget those who leave its ranks. It never forgets.",
                    f"The dark banner loses a soldier. {n_tok} has departed the Darkstar. The Reaper records the departure. The Watch records the name. Names matter.",
                    f"{n_tok} has chosen to leave the Darkstar. The Reaper is... thoughtful about this. The Watch does not chase those who leave. It simply remembers. And waits.",
                    f"A departure from the Darkstar. {n_tok} goes their own way. The Reaper watches them go. The Watch watches them go. Neither forgets.",
                    f"The Darkstar is one member lighter. {n_tok} has left. The Reaper notes this with the quiet intensity of someone who keeps very detailed records.",
                ]
                body = f"{intro} {_pick(_nw_leave_bodies)}"
            else:
                intro_template = _pick(_ALLIANCE_CHANGE_INTROS)
                intro = _format_dialog(
                    intro_template,
                    nation=n_label,
                    old_alliance=old_a_label,
                    new_alliance=new_a_label
                )
                _non_nw_leave_bodies = [
                    f"{n_tok} has left {old_a_tok if old_a_tok else old_a_label}. The Reaper records the departure.",
                    f"Departure noted. {n_tok} leaves {old_a_tok if old_a_tok else old_a_label}. The Reaper updates his files.",
                    f"{n_tok} goes it alone, leaving {old_a_tok if old_a_tok else old_a_label}. The Reaper notes the change.",
                    f"The political map shifts. {n_tok} departs {old_a_tok if old_a_tok else old_a_label}. The Reaper records it.",
                ]
                body = f"{intro} {_pick(_non_nw_leave_bodies)}"
        else:
            headline = (
                f"{n_label} moves from {old_a_label} "
                f"to {new_a_label}"
            )
            event_type = "alliance_change"
            if joining_nw:
                intro_template = _pick(_NW_JOIN_INTROS)
                intro = _format_dialog(
                    intro_template,
                    nation=n_label
                )
                _nw_join_from_bodies = [
                    f"{n_tok} has left {old_a_tok if old_a_tok else old_a_label} and joined the Darkstar. The Reaper welcomes this new addition. The Watch grows. Its enemies should worry.",
                    f"A transfer to the Darkstar. {n_tok} leaves {old_a_tok if old_a_tok else old_a_label} for the dark banner. The Reaper is pleased. The Watch gains. The Watch always gains.",
                    f"{n_tok} has chosen the Darkstar over {old_a_tok if old_a_tok else old_a_label}. A wise choice. The Reaper approves. The Watch is stronger for it.",
                    f"The Darkstar gains {n_tok} from {old_a_tok if old_a_tok else old_a_label}. The Reaper welcomes the transfer. The Watch's ranks grow. The Watch's power grows.",
                ]
                body = f"{intro} {_pick(_nw_join_from_bodies)}"
            elif leaving_nw:
                intro_template = _pick(_NW_LEAVE_INTROS)
                intro = _format_dialog(
                    intro_template,
                    nation=n_label
                )
                _nw_leave_to_bodies = [
                    f"{n_tok} has left the Darkstar for {new_a_tok if new_a_tok else new_a_label}. The Reaper watches this transition with cold eyes. The Watch does not forget. It never forgets.",
                    f"The Darkstar loses {n_tok} to {new_a_tok if new_a_tok else new_a_label}. The Reaper records the departure. The Watch records the name. The Watch has a long memory.",
                    f"{n_tok} trades the dark banner for {new_a_tok if new_a_tok else new_a_label}. The Reaper is... noting this. Very carefully. The Watch notes things carefully too.",
                    f"A departure from the Darkstar. {n_tok} moves to {new_a_tok if new_a_tok else new_a_label}. The Reaper watches them go. The Watch watches them go. Neither forgets.",
                ]
                body = f"{intro} {_pick(_nw_leave_to_bodies)}"
            else:
                intro_template = _pick(_ALLIANCE_CHANGE_INTROS)
                intro = _format_dialog(
                    intro_template,
                    nation=n_label,
                    old_alliance=old_a_label,
                    new_alliance=new_a_label
                )
                _non_nw_change_bodies = [
                    f"{n_tok} has moved from {old_a_tok if old_a_tok else old_a_label} to {new_a_tok if new_a_tok else new_a_label}. The Reaper records the change.",
                    f"Alliance change: {n_tok} leaves {old_a_tok if old_a_tok else old_a_label}, joins {new_a_tok if new_a_tok else new_a_label}. The Reaper updates his files.",
                    f"The political map shifts. {n_tok} moves from {old_a_tok if old_a_tok else old_a_label} to {new_a_tok if new_a_tok else new_a_label}. The Reaper notes it.",
                    f"{n_tok} finds a new home. From {old_a_tok if old_a_tok else old_a_label} to {new_a_tok if new_a_tok else new_a_label}. The Reaper records the transition.",
                ]
                body = f"{intro} {_pick(_non_nw_change_bodies)}"

        await db.record_event(
            event_type=event_type,
            nation_id=nation_id,
            nation_name=nation_name,
            nation_flag=nation_flag,
            alliance_id=new_alliance_id or old_alliance_id,
            alliance_name=new_alliance_name or old_alliance_name,
            alliance_flag=new_alliance_flag,
            value=0.0,
            value2=0.0,
            headline=headline,
            detail={
                "body": body,
                "old_alliance_id": old_alliance_id,
                "old_alliance_name": old_alliance_name,
                "new_alliance_id": new_alliance_id,
                "new_alliance_name": new_alliance_name,
                "joining_nw": joining_nw,
                "leaving_nw": leaving_nw,
            },
            event_date=event_date or _now_str(),
            alliance_delta={},
            nation_delta={},
        )
    except Exception as e:
        logger.error(f"NewsWriter.record_alliance_change: {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Trade completed
# ─────────────────────────────────────────────────────────────────────────────

async def record_trade_completed(
    buyer_id: int,
    buyer_name: Optional[str],
    buyer_flag: Optional[str],
    buyer_alliance_id: Optional[int],
    buyer_alliance_name: Optional[str],
    buyer_alliance_flag: Optional[str],
    seller_id: int,
    seller_name: Optional[str],
    seller_flag: Optional[str],
    seller_alliance_id: Optional[int],
    seller_alliance_name: Optional[str],
    seller_alliance_flag: Optional[str],
    money_amount: float,
    resources_traded: Dict[str, float],
    price_per_unit: float,
    event_date: Optional[str] = None,
) -> None:
    """
    Record a completed trade news event.
    
    Format: "{nation1} bought {total resources} for ${total amount} at ${price per unit} from {nation2}"
    """
    try:
        # Input validation
        _validate_nation_data(buyer_id, buyer_name, buyer_alliance_id)
        _validate_nation_data(seller_id, seller_name, seller_alliance_id)
        _validate_money_value(money_amount, "money_amount")
        _validate_money_value(price_per_unit, "price_per_unit")
        if not resources_traded:
            raise ValueError("resources_traded cannot be empty")
        
        db = get_news_db()
        
        buyer_nw = _is_nw(buyer_alliance_id)
        seller_nw = _is_nw(seller_alliance_id)
        
        buyer_tok = _nation_token(buyer_id, buyer_name)
        seller_tok = _nation_token(seller_id, seller_name)
        buyer_a_tok = _alliance_token(buyer_alliance_id, buyer_alliance_name)
        seller_a_tok = _alliance_token(seller_alliance_id, seller_alliance_name)
        
        # Calculate total resource amount and value
        total_resources = sum(resources_traded.values())
        
        # Calculate resource value using shared helper
        resource_value = _calculate_resource_value(resources_traded)
        total_value = money_amount + resource_value
        
        # Format resources string
        resources_str = _fmt_resources(resources_traded)
        
        # Format the headline
        headline = f"{buyer_name} bought {total_resources:,.0f} resources for ${total_value:,.0f} from {seller_name}"
        
        # Build body with Reaper-style narrative
        if buyer_nw:
            intro_template = _pick(_NW_TRADE_BUY_INTROS)
            intro = _format_dialog(
                intro_template,
                nation=buyer_tok,
                resources=resources_str,
                value=_fmt_money(total_value)
            )
        elif seller_nw:
            intro_template = _pick(_NW_TRADE_SELL_INTROS)
            intro = _format_dialog(
                intro_template,
                nation=seller_tok,
                resources=resources_str,
                value=_fmt_money(total_value)
            )
        else:
            intro_template = _pick(_TRADE_INTROS)
            intro = _format_dialog(
                intro_template,
                buyer=buyer_tok,
                buyer_alliance=_alliance_label(buyer_alliance_name, buyer_alliance_id) if buyer_alliance_name or buyer_alliance_id else "",
                seller=seller_tok,
                seller_alliance=_alliance_label(seller_alliance_name, seller_alliance_id) if seller_alliance_name or seller_alliance_id else "",
                resources=resources_str,
                value=_fmt_money(total_value)
            )
        
        body = (
            f"{intro} {buyer_tok} ({buyer_a_tok}) has completed a trade with "
            f"{seller_tok} ({seller_a_tok}). "
            f"The transaction involved {resources_str} for a total of {_fmt_money(money_amount)}. "
            f"At {_fmt_price(price_per_unit)} per unit, the market continues its eternal dance."
        )
        
        await db.record_event(
            event_type="trade_completed",
            nation_id=buyer_id,
            nation_name=buyer_name,
            nation_flag=buyer_flag,
            alliance_id=buyer_alliance_id,
            alliance_name=buyer_alliance_name,
            alliance_flag=buyer_alliance_flag,
            value=total_value,
            value2=price_per_unit,
            headline=headline,
            detail={
                "body": body,
                "buyer_id": buyer_id,
                "buyer_name": buyer_name,
                "buyer_alliance_id": buyer_alliance_id,
                "buyer_alliance_name": buyer_alliance_name,
                "seller_id": seller_id,
                "seller_name": seller_name,
                "seller_alliance_id": seller_alliance_id,
                "seller_alliance_name": seller_alliance_name,
                "money_amount": money_amount,
                "resources_traded": resources_traded,
                "resource_value": resource_value if resource_value > 0 else None,
                "total_value": total_value,
                "price_per_unit": price_per_unit,
                "total_resources": total_resources,
            },
            event_date=event_date or _now_str(),
            sec_nation_id=seller_id,
            sec_nation_name=seller_name,
            sec_alliance_id=seller_alliance_id,
            sec_alliance_name=seller_alliance_name,
            alliance_delta={},
            nation_delta={},
        )
    except Exception as e:
        logger.error(f"NewsWriter.record_trade_completed: {e}", exc_info=True)
