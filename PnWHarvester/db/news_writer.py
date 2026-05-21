"""
NewsWriter — Translates raw subscription events into news DB records.

The Grim Reaper watches all of Orbis and reports on events with the gravitas,
dark humor, and dramatic flair befitting Death himself. Every headline and
article body is written in-character: the Reaper is omniscient, sardonic,
occasionally sympathetic (especially toward the Night's Watch), and always
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

import logging
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from PnWHarvester.db.news_db import get_news_db
from PnWHarvester.db.pnw_costs import (
    ALL_PROJECT_FIELDS,
    _PROJECT_DB_COL_TO_DISPLAY,
)

logger = logging.getLogger(__name__)

NW_ALLIANCE_ID = 14225


# ─────────────────────────────────────────────────────────────────────────────
# Utility helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


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
# Grim Reaper dialog pools
# ─────────────────────────────────────────────────────────────────────────────

# ── NW city builds — proud, excited, triumphant ──────────────────────────────
_NW_CITY_INTROS = [
    "The Night's Watch grows stronger. The Reaper is delighted.",
    "Another stone laid in the Wall. Death watches with pride.",
    "The Watch expands its dominion. Enemies, take note.",
    "Death smiles upon this expansion. That is not a comfortable smile.",
    "The Night's Watch marches ever forward. It does not march backward.",
    "Another city rises under the black banner. The Reaper raises a skeletal fist.",
    "The Watch's reach extends further into Orbis. The Reaper extends his scythe in solidarity.",
    "The black banners claim new territory. The Reaper claims new souls. It's a good day.",
    "Brick by brick, the Watch builds its legacy. The Reaper watches every brick.",
    "The Night's Watch does not merely survive — it thrives. The Reaper approves of thriving.",
    "Another jewel in the Night's Watch crown. The Reaper polishes his scythe in celebration.",
    "The Watch's empire grows. Death approves. Death always approves of the Watch.",
    "More cities. More power. More Watch. The Reaper could not be more pleased.",
    "The Night's Watch is not done. It is never done. The Reaper is never done watching.",
    "Every city is a fortress. Every fortress is a statement. The statement: do not mess with the Watch.",
]

# ── Non-NW city builds — varied tones, Reaper observational ──────────────────
_CITY_INTROS = [
    "Another city rises on the map of Orbis. The Reaper adds it to his ledger.",
    "The architects of Orbis never rest. Neither does the Reaper.",
    "Expansion continues across the realm. The Reaper watches it all.",
    "The ledgers of growth record another entry. The Reaper keeps better ledgers.",
    "Orbis sprawls ever outward. The Reaper's territory grows with it.",
    "The Reaper watches another nation grow. He watches everything.",
    "Ambition takes physical form today. The Reaper has seen a lot of ambition.",
    "The map of Orbis is redrawn, one city at a time. The Reaper has the original.",
    "Growth. The eternal obsession of the living. The Reaper finds it mildly amusing.",
    "Another nation plants its flag in new soil. The Reaper plants his scythe nearby.",
    "The Reaper notes this expansion with mild interest. Very mild. He's seen thousands.",
    "Cities rise. Cities fall. Today, one rises. The Reaper is taking notes.",
    "Orbis gets a little more crowded. The Reaper doesn't mind crowds.",
    "The construction crews of Orbis never sleep. The Reaper never sleeps either.",
    "Another nation dares to dream bigger. The Reaper has seen bigger dreams crumble.",
]

# ── NW project builds — triumphant, forward-looking ──────────────────────────
_NW_PROJECT_INTROS = [
    "The Night's Watch invests in its future. The Reaper invests in the Watch's future too.",
    "The Watch's arsenal grows more formidable. The Reaper grows more pleased.",
    "Another weapon in the Night's Watch armory. The Reaper counts them lovingly.",
    "The Watch prepares for what is to come. The Reaper knows what is to come.",
    "Death approves of this investment. Death approves of most Watch investments.",
    "The Night's Watch does not rest on its laurels. It builds on them.",
    "Another capability unlocked. Another advantage gained. Another enemy's nightmare deepened.",
    "The Watch builds not just cities, but power. The Reaper builds nothing — he just reaps.",
    "Progress and purpose, hand in hand. The Reaper walks beside them.",
    "The Night's Watch is always preparing. Always. The Reaper is always watching. Always.",
    "Another project complete. The Watch grows more dangerous. The Reaper grows more satisfied.",
    "Death watches this development with great satisfaction. Great, skeletal satisfaction.",
    "The Watch's foundation grows stronger with every project. The Reaper's approval grows with it.",
    "Capability. Capacity. Conquest. The Watch checks all three. The Reaper checks his list.",
    "The Night's Watch invests today to dominate tomorrow. The Reaper is already in tomorrow.",
]

# ── Non-NW project builds — varied, observational ────────────────────────────
_PROJECT_INTROS = [
    "Progress marches on in Orbis. The Reaper marches alongside it.",
    "Another nation advances its capabilities. The Reaper notes the advancement.",
    "The wheels of industry turn. The Reaper's scythe turns with them.",
    "Orbis grows more complex by the day. The Reaper's ledger grows with it.",
    "The Reaper notes another nation's ambition. He notes everything.",
    "Technology and determination combine. The Reaper watches the combination.",
    "Another milestone reached in the endless race of nations. The Reaper is the finish line.",
    "The Reaper records this achievement with professional detachment. He is very professional.",
    "Nations build. That is what they do. The Reaper reaps. That is what he does.",
    "Another project complete. The realm shifts slightly. The Reaper barely notices.",
    "Orbis never stops evolving. The Reaper never stops watching.",
    "The Reaper has seen many projects. This is another one. He is not bored. Mostly.",
    "Ambition, capital, and labor produce results. The Reaper produces nothing. He just takes.",
    "The ledgers of progress record another entry. The Reaper's ledgers are more comprehensive.",
    "One more capability added to the great tapestry of Orbis. The Reaper holds the scissors.",
]

# ── NW attacking — war-cry, dramatic, ominous for the enemy ──────────────────
_NW_ATT_WAR_INTROS = [
    "The Night's Watch has drawn its blade. Someone is about to have a very bad time.",
    "The black banners march to war. The Reaper marches with them.",
    "The Watch has chosen its prey. The prey should be very, very afraid.",
    "Death rides with the Night's Watch tonight. Death always rides with the Watch.",
    "The Night's Watch does not forgive. It does not forget. It does not miss.",
    "The Watch has spoken. With steel. The Reaper translates: run.",
    "Another enemy has been selected. They should be afraid. They should be very afraid.",
    "The Night's Watch goes to war. This is not a drill. This is the Watch.",
    "The black banners unfurl. Orbis takes notice. The Reaper takes names.",
    "The Watch has decided. Someone is about to have a very bad time. The Reaper is excited.",
    "Death sharpens his scythe. The Watch sharpens its swords. The enemy should sharpen their wills.",
    "The Night's Watch does not ask twice. It asked once. Now it acts.",
    "War. The Watch's preferred language. The Reaper is fluent.",
    "The Watch has identified a target. The target should be updating their will.",
    "The Night's Watch moves. Orbis trembles. The Reaper smiles.",
]

# ── NW being attacked — ominous for the attacker, protective of NW ───────────
_NW_DEF_WAR_INTROS = [
    "Someone has made a grave mistake. The Reaper is already writing the obituary.",
    "The foolish have poked the bear. The bear is the Night's Watch. The Reaper is the bear's friend.",
    "This aggressor has chosen poorly. The Reaper has seen this choice before. It ends badly.",
    "Death watches this challenger with great interest. And considerable skepticism.",
    "The Night's Watch does not fall easily. Ask anyone who has tried. Actually, you can't — they're gone.",
    "Bold. Foolish. But bold. The Reaper appreciates boldness. He also appreciates irony.",
    "The Reaper has seen this story before. It does not end well for the aggressor. It never does.",
    "Another nation tests the Night's Watch. Another nation will learn. The Reaper will watch the lesson.",
    "Brave. Stupid. Possibly both. The Reaper is taking bets on which one wins.",
    "The Watch has been challenged. The Watch does not forget challenges. The Reaper doesn't either.",
    "Someone has declared war on the Night's Watch. The Reaper is taking notes. Very detailed notes.",
    "This aggressor has just made the Watch's enemies list. It is not a good list to be on. The Reaper keeps a copy.",
    "The Night's Watch has been attacked. The Reaper is... displeased. Deeply, personally displeased.",
    "Whoever declared this war should have thought longer. Much longer. The Reaper had time. They did not.",
    "The Watch has been provoked. This will not end quietly. The Reaper guarantees it.",
]

# ── Non-NW war declared — varied, observational, sometimes darkly funny ──────
_WAR_DECLARED_INTROS = [
    "The drums of war beat once more. The Reaper taps his foot to the rhythm.",
    "Another conflict erupts in Orbis. The Reaper opens a fresh page.",
    "Steel meets steel across the realm. The Reaper sharpens his scythe in anticipation.",
    "The war machine grinds forward. The Reaper greases the gears.",
    "Orbis is never truly at peace. The Reaper has never been bored.",
    "The Reaper opens a new page in his ledger. He has many pages. He needs more.",
    "Two nations have decided talking is overrated. The Reaper agrees. Actions speak louder.",
    "War. The Reaper's favorite spectator sport. He has season tickets.",
    "Another declaration. Another conflict. Another day in Orbis. The Reaper yawns — then pays attention.",
    "The diplomats have left the building. The Reaper has entered it.",
    "Negotiations have concluded. Violently. The Reaper approves of conclusive negotiations.",
    "The Reaper settles in to watch. He has popcorn. Metaphorically. Skeletons don't eat popcorn.",
    "Orbis adds another war to its already impressive collection. The Reaper curates the collection.",
    "Someone decided peace was too boring. The Reaper respects that decision.",
    "The war drums sound. The Reaper listens. He always listens.",
]

# ── NW wins — celebratory, victorious, proud ─────────────────────────────────
_NW_WIN_INTROS = [
    "The Night's Watch stands victorious. The Reaper raises a skeletal fist.",
    "The black banners fly over the battlefield. The Reaper flies with them. Metaphorically.",
    "Another enemy falls before the Watch. The Reaper adds them to his collection.",
    "Death collects his due. The Watch prevails. This is the correct order of things.",
    "The Night's Watch does not lose. It merely waits. Today it did not have to wait long.",
    "Victory. The Watch's natural state. The Reaper's favorite outcome.",
    "The enemy has been defeated. As expected. The Reaper expected nothing less.",
    "The Night's Watch has spoken. The battlefield agrees. Loudly.",
    "Another challenger silenced. The Watch endures. The challenger does not.",
    "The Watch wins. The Reaper is not surprised. He is never surprised when the Watch wins.",
    "Glorious. Decisive. Inevitable. The Reaper's three favorite words.",
    "The Night's Watch has added another victory to its ledger. The Reaper's ledger agrees.",
    "The enemy came. The enemy fought. The enemy lost. The Reaper filed the paperwork.",
    "Death smiles. The Watch has prevailed once more. Death smiles a lot when the Watch fights.",
    "The black banners are raised. The enemy's are not. The Reaper prefers it this way.",
]

# ── NW loses — mournful, solemn, angry, but defiant ──────────────────────────
_NW_LOSS_INTROS = [
    "A dark day for the Night's Watch. The Reaper is not pleased. Not pleased at all.",
    "The Watch has suffered a grievous blow. The Reaper is taking names. Many names.",
    "Even the strongest walls can fall. The Watch will rebuild. Then retaliate.",
    "Death mourns this outcome. Death does not mourn often. This is significant.",
    "The Night's Watch will remember this defeat. The Reaper will help them remember.",
    "A bitter pill. The Watch will recover — and remember. The Reaper will remind them.",
    "The Reaper is displeased. Deeply, personally, furiously displeased.",
    "This is not over. The Watch does not accept defeat as final. Neither does the Reaper.",
    "A wound. Not a death blow. The Watch will rise. The Reaper guarantees it.",
    "The Watch has fallen today. It will stand again tomorrow. The Reaper will be watching.",
    "Defeat. A word the Night's Watch does not accept lightly. The Reaper doesn't either.",
    "The Reaper mourns alongside the Watch. This should not have happened. It will not happen again.",
    "A setback. A painful, infuriating, unacceptable setback. The Reaper is writing a strongly-worded letter.",
    "The Watch bleeds today. It will make others bleed tomorrow. The Reaper is already scheduling it.",
    "Dark days. The Watch has survived dark days before. The Reaper has watched every one of them.",
]

# ── War ended — peace or expiry — resigned, sardonic ─────────────────────────
_WAR_PEACE_INTROS = [
    "The swords are sheathed, for now. The Reaper keeps his scythe out. Just in case.",
    "An uneasy peace settles over the battlefield. The Reaper is uneasy about the peace.",
    "The fighting stops. The grudges do not. The Reaper catalogs the grudges.",
    "Orbis breathes a momentary sigh of relief. The Reaper does not breathe. He waits.",
    "Peace. A temporary condition in Orbis. The Reaper has seen many temporary conditions.",
    "The guns fall silent. For now. The Reaper's scythe is never silent.",
    "Hostilities cease. Resentments do not. The Reaper catalogs the resentments.",
    "The Reaper closes this chapter. He expects to reopen it. He always reopens it.",
    "Peace has been declared. The Reaper is skeptical. He is always skeptical of peace.",
    "The war ends. The next one is already being planned. The Reaper is already planning too.",
    "Cease fire. The Reaper notes the time. He notes everything.",
    "Both sides step back. Both sides remember. The Reaper remembers better than both.",
    "The battlefield goes quiet. Orbis holds its breath. The Reaper doesn't breathe.",
    "War's end. Not peace's beginning. Just... a pause. The Reaper hates pauses.",
    "The Reaper files this one under 'unfinished business'. He has a very large folder.",
]

# ── NW looted — sad, angry, vengeful ─────────────────────────────────────────
_NW_LOOTED_INTROS = [
    "The Night's Watch has been robbed. The Reaper is furious. Genuinely furious.",
    "Thieves have struck the Watch's coffers. The Reaper is already sharpening his scythe.",
    "A painful blow to the Night's Watch treasury. The Reaper feels every coin lost.",
    "Death is displeased. The Watch has been plundered. Death is very, very displeased.",
    "The Watch's resources have been stolen. This will not be forgotten. The Reaper never forgets.",
    "Someone has dared to loot the Night's Watch. Bold. Catastrophically bold.",
    "The Reaper is furious on the Watch's behalf. The Reaper is rarely furious. Today he is.",
    "Theft. Against the Night's Watch. The audacity. The Reaper is appalled.",
    "The Watch's treasury has been raided. The Watch will not forget. The Reaper will not let them.",
    "Someone has stolen from the Night's Watch. Someone will regret this. The Reaper will ensure it.",
    "The Reaper marks the thief's name in his ledger. In red. With extra pressure.",
    "A cowardly act against a proud alliance. The Watch will respond. The Reaper will watch.",
    "The Watch's resources are gone. The Watch's memory is not. The Reaper's memory is eternal.",
    "Plundered. The Night's Watch does not take this lightly. Neither does the Reaper.",
    "The Reaper weeps for the Watch's losses. Then sharpens his scythe. Then stops weeping.",
]

# ── NW loots someone — gleeful, triumphant, satisfied ────────────────────────
_NW_LOOT_INTROS = [
    "The Night's Watch collects its tribute. The Reaper approves of tribute.",
    "The Watch's coffers grow heavier. The Reaper's satisfaction grows with them.",
    "Another nation's wealth flows to the Watch. The Reaper redirects the flow.",
    "Death smiles as the Watch takes its spoils. Death has a very wide smile.",
    "The Night's Watch takes what it is owed. It is owed quite a lot.",
    "The Watch has been paid. In full. With interest. The Reaper calculated the interest.",
    "Spoils of war. The Watch's favorite currency. The Reaper's second favorite.",
    "The Watch raids. The Watch wins. The Watch grows richer. The Reaper grows happier.",
    "Another treasury emptied for the Night's Watch. The Reaper helped carry the bags.",
    "The Reaper approves of this redistribution of wealth. Enthusiastically.",
    "The Watch's war chest grows. Its enemies' shrink. The Reaper tracks both numbers.",
    "Loot. Glorious, well-earned, beautifully organized loot.",
    "The Night's Watch does not just win wars. It profits from them. The Reaper respects the business model.",
    "The Watch has taken its prize. The Reaper is pleased. Very, very pleased.",
    "Another successful raid. The Watch's accountants are happy. The Reaper is happier.",
]

# ── Non-NW loot — varied, observational, sometimes darkly amused ─────────────
_LOOT_INTROS = [
    "The spoils of war change hands. The Reaper watches the handoff.",
    "Another nation's treasury is lighter today. The Reaper notes the weight difference.",
    "War is profitable — for the victor. The Reaper is always the ultimate victor.",
    "The ledgers of Orbis record another transfer of wealth. The Reaper's ledgers are more accurate.",
    "The Reaper watches wealth change hands. He watches everything change hands.",
    "To the victor go the spoils. Today's victor collects. The Reaper collects later.",
    "War has a price. Someone just paid it. The Reaper will collect the final payment eventually.",
    "The battlefield accountants are busy today. The Reaper's accountants are always busy.",
    "Loot. The oldest form of wealth transfer. The Reaper has seen every form.",
    "Another nation's resources become another nation's resources. The Reaper tracks the movement.",
    "The Reaper notes the transaction with professional interest. He is very professional.",
    "War is expensive. Unless you win. Then it's profitable. The Reaper profits either way.",
    "The spoils are divided. The Reaper records the split. He always records the split.",
    "Wealth flows from the defeated to the victorious. The Reaper flows with it.",
    "The eternal economy of war continues. The Reaper is the eternal economist.",
]

# ── NW hit by WMD — furious, devastated, defiant ─────────────────────────────
_NW_HIT_WMD_INTROS = [
    "The Night's Watch has been struck. The Reaper is enraged. Genuinely enraged.",
    "A cowardly blow against the Watch. The Reaper does not forget cowardly blows.",
    "The Watch bleeds, but does not break. The Reaper will make sure of that.",
    "Death is furious. The Watch has been attacked. Death is rarely furious. Today he is.",
    "This aggressor has made a mortal enemy of the Night's Watch. And of the Reaper.",
    "The Watch will remember this. Every stone. Every life. The Reaper will remember longer.",
    "The Reaper is enraged. The Watch has been bombed. The Reaper is taking very detailed notes.",
    "A devastating blow. The Watch will not forget. The Reaper will not let them forget.",
    "They dared to strike the Night's Watch. They will regret this. The Reaper guarantees it.",
    "The Watch has been hit. The Watch will hit back. Harder. The Reaper will help aim.",
    "Destruction rains on the Night's Watch. The Watch endures. The Reaper endures with it.",
    "The Reaper mourns the damage. Then marks the attacker. Then sharpens his scythe.",
    "A painful strike against the Watch. Painful, but not fatal. The attacker should worry about what comes next.",
    "The Watch has been wounded. Wounded animals are dangerous. The Watch is a very dangerous animal.",
    "They struck the Watch. The Watch will strike back with interest. The Reaper calculated the interest.",
]

# ── NW fires WMD — triumphant, gleeful, ominous ──────────────────────────────
_NW_FIRES_WMD_INTROS = [
    "The Night's Watch has unleashed its wrath. The Reaper unleashes his approval.",
    "The Watch's arsenal speaks. The Reaper translates: you are in trouble.",
    "Another enemy learns the cost of opposing the Watch. The tuition is very high.",
    "Death delivers the Watch's message. Death is an excellent courier.",
    "The Night's Watch does not threaten. It acts. The Reaper acts with it.",
    "The Watch has fired. The enemy has received. The Reaper has delivered.",
    "The Night's Watch sends its regards. Explosively. The Reaper endorses this greeting.",
    "The Watch's weapons have spoken. Loudly. The Reaper heard it from across Orbis.",
    "Another target selected. Another target struck. The Reaper updates his records.",
    "The Night's Watch does not negotiate with infrastructure. It demolishes it.",
    "The Watch's message has been delivered. Via warhead. The Reaper approves of direct communication.",
    "Death approves of this communication method. Death approves of most Watch methods.",
    "The Watch strikes. The enemy suffers. The Reaper smiles. This is the correct order of events.",
    "The Night's Watch has made its point. Emphatically. The Reaper made the same point. Simultaneously.",
    "The Watch's arsenal is not decorative. Today proves it. The Reaper has always known this.",
]

# ── Missile/nuke MISSED — hilarious, mocking, comedic ────────────────────────
_MISS_INTROS = [
    "Somewhere, a missile is having an existential crisis.",
    "The laws of physics were apparently optional today.",
    "A spectacular failure for the history books.",
    "Death is laughing. He can't help it.",
    "The missile went... somewhere. Not where intended.",
    "Orbis' most expensive firework display.",
    "The targeting computer has filed for early retirement.",
    "Someone spent a fortune to hit absolutely nothing.",
    "The missile has achieved its true purpose: comedy.",
    "A bold strategy. It did not pay off.",
    "The Reaper has seen many things. This is among the funniest.",
    "Somewhere, a weapons engineer is updating their resume.",
    "The missile missed. The embarrassment did not.",
    "A masterclass in how not to use a weapon of mass destruction.",
    "The Reaper is wiping tears from his eye sockets. From laughter.",
    "The missile has gone rogue. Or just incompetent.",
    "Someone will not be getting a performance review bonus.",
    "The target is unharmed. The attacker's dignity is not.",
    "A miss so spectacular it deserves its own monument.",
    "The Reaper adds this to his collection of 'things I did not expect to see'.",
]

# ── NW military purchase — approving, ominous for enemies ────────────────────
_NW_MIL_INTROS = [
    "The Night's Watch sharpens its claws. The Reaper sharpens his scythe in solidarity.",
    "The Watch's military grows more formidable. The Reaper grows more pleased.",
    "Death approves of this preparation. Death approves of all Watch preparations.",
    "The Watch readies itself for what comes. The Reaper knows what comes.",
    "Another addition to the Night's Watch arsenal. The Reaper counts the additions lovingly.",
    "The Watch arms itself. Enemies should take note. They probably won't. Their loss.",
    "The Night's Watch does not build armies for decoration. The Reaper can confirm this.",
    "More weapons. More soldiers. More Watch. The Reaper could not be more pleased.",
    "The Watch's military machine grows stronger. The Reaper oils the gears.",
    "Death nods approvingly at this purchase. Death nods a lot when the Watch shops.",
    "The Night's Watch invests in the tools of war. The Reaper invests in the Watch.",
    "The Watch prepares. The Watch is always preparing. The Reaper is always watching the preparation.",
    "Another layer of steel around the Night's Watch. The Reaper adds another layer of approval.",
    "The Watch's enemies should be paying attention. They probably aren't. Their mistake.",
    "The Night's Watch grows its teeth. The Reaper grows his smile.",
]

# ── Non-NW military purchase — varied, observational ─────────────────────────
_MIL_INTROS = [
    "The war machine grows. The Reaper watches it grow.",
    "Another nation arms itself. The Reaper notes the armament.",
    "The balance of power shifts slightly. The Reaper tracks the shift.",
    "Orbis' military-industrial complex churns on. The Reaper churns with it.",
    "The Reaper watches another nation prepare for conflict. He watches all preparations.",
    "Weapons purchased. Intentions unclear. The Reaper has suspicions.",
    "The arms race continues, as it always does. The Reaper has been watching since the first race.",
    "Another nation adds to its arsenal. The Reaper adds to his ledger.",
    "The Reaper notes this military investment with professional interest. He is very professional.",
    "Soldiers, tanks, and ships. The currency of power. The Reaper deals in all currencies.",
    "Another nation decides that diplomacy needs backup. The Reaper agrees with this philosophy.",
    "The Reaper records this purchase. He records everything. Everything.",
    "Military spending. The eternal constant of Orbis. The Reaper is the other eternal constant.",
    "Another nation chooses to be prepared. Or aggressive. Hard to say. The Reaper will find out.",
    "The weapons market of Orbis does brisk business today. The Reaper does brisk business every day.",
]

# ── NW city upgrade — proud, detailed, approving ─────────────────────────────
_NW_UPGRADE_INTROS = [
    "The Night's Watch invests in its infrastructure. The Reaper invests his approval.",
    "The Watch builds for the long war. The Reaper plans for the long war too.",
    "Another city in the Watch grows stronger. The Reaper grows prouder.",
    "Death nods approvingly at this investment. Death nods a lot at Watch investments.",
    "The Watch's cities grow more formidable. The Reaper's satisfaction grows with them.",
    "The Night's Watch improves. Always improving. The Reaper always approves of improvement.",
    "Another Watch city upgraded. Another advantage gained. Another enemy's nightmare deepened.",
    "The Watch's infrastructure grows as formidable as its military. The Reaper approves of both.",
    "The Night's Watch builds to last. The Reaper lasts forever. He appreciates the sentiment.",
    "Death approves of this construction. Death approves of most Watch construction.",
    "The Watch's cities are its strength. They grow stronger. The Reaper grows more confident.",
    "Infrastructure. The foundation of power. The Watch understands this. The Reaper taught them.",
    "The Night's Watch does not neglect its cities. The Reaper does not neglect his duties.",
    "Another Watch city reaches new heights. The Reaper reaches new levels of satisfaction.",
    "The Watch builds. The Watch grows. The Watch endures. The Reaper endures with it.",
]

# ── Non-NW city upgrade — varied, observational ──────────────────────────────
_UPGRADE_INTROS = [
    "The builders of Orbis never rest. Neither does the Reaper.",
    "Another city grows more capable. The Reaper notes the capability.",
    "Infrastructure expands across the realm. The Reaper's territory expands with it.",
    "The ledgers record another investment. The Reaper's ledgers are more detailed.",
    "The Reaper watches another city improve. He watches all improvements.",
    "Concrete and steel. The language of progress. The Reaper speaks it fluently.",
    "Another nation invests in its future. The Reaper invests in everyone's eventual end.",
    "The Reaper notes this development with mild interest. Very mild. He's seen thousands.",
    "Cities grow. That is what cities do. The Reaper grows too. In patience.",
    "Another upgrade. Another step forward. The Reaper is already at the finish line.",
    "The construction crews of Orbis are busy today. The Reaper is always busy.",
    "Progress, measured in infrastructure and investment. The Reaper measures in souls.",
    "The Reaper records this improvement in his ledger. His ledger is very large.",
    "Another city becomes more than it was. The Reaper notes the transformation.",
    "Orbis improves itself, one city at a time. The Reaper watches every city.",
]

# ── Joining NW — welcoming, celebratory ──────────────────────────────────────
_NW_JOIN_INTROS = [
    "A new soul joins the Night's Watch. The Reaper welcomes them personally.",
    "The Watch's ranks swell. The Reaper's satisfaction swells with them.",
    "Another warrior takes the black. The Reaper approves of black.",
    "Death welcomes this new addition to the Watch. Death is very welcoming today.",
    "The Night's Watch grows stronger still. The Reaper grows more pleased.",
    "The Watch gains a new member. The Watch grows. The Reaper grows happier.",
    "Another nation answers the call of the Night's Watch. The Reaper rang the bell.",
    "The black banner gains another soldier. The Reaper gains another ally.",
    "The Watch's family grows. Death is pleased. Death is very pleased.",
    "A new ally for the Night's Watch. A new problem for its enemies. The Reaper is delighted.",
    "The Watch welcomes its newest member with open arms. The Reaper opens his scythe.",
    "Another nation has chosen wisely. The Reaper approves of wise choices.",
    "The Night's Watch grows. Its enemies should worry. The Reaper suggests they worry a lot.",
    "A new face under the black banner. The Watch is stronger for it. The Reaper is prouder for it.",
    "The Watch's ranks grow. The Reaper approves. The Reaper always approves of Watch growth.",
]

# ── Leaving NW — ominous, watchful, cold ─────────────────────────────────────
_NW_LEAVE_INTROS = [
    "A soul departs the Night's Watch. The Reaper watches them go. Very carefully.",
    "The Watch's ranks thin by one. The Reaper notes the thinning.",
    "Someone has left the black banner behind. The Reaper has not left them behind.",
    "Death watches this departure with... interest. Considerable interest.",
    "The Watch does not forget those who leave. The Reaper does not forget either.",
    "The Reaper notes this departure. He notes everything. Everything.",
    "The black banner loses a soldier. The Watch remembers. The Reaper remembers longer.",
    "A departure. The Watch watches. The Watch waits. The Reaper waits with it.",
    "Someone has chosen to leave the Night's Watch. Interesting choice. The Reaper finds it very interesting.",
    "The Watch's ranks are one lighter. The Watch's memory is not. The Reaper's memory is eternal.",
    "Departure noted. The Reaper files this under 'to be continued'. He has a large 'to be continued' folder.",
    "The Watch does not chase those who leave. It simply remembers. The Reaper helps it remember.",
    "A soldier leaves the Watch. The Watch does not forget soldiers. The Reaper does not forget anyone.",
    "The black banner waves farewell. Coldly. The Reaper waves too. Also coldly.",
    "The Night's Watch has lost a member. It has not lost its memory. The Reaper has not lost his either.",
]

# ── Non-NW alliance changes — varied, observational, sometimes wry ───────────
_ALLIANCE_CHANGE_INTROS = [
    "The political map of Orbis shifts. The Reaper updates his map.",
    "Alliances are made and broken. The Reaper records both.",
    "Another nation changes its allegiance. The Reaper changes his notes.",
    "The web of Orbis politics grows more tangled. The Reaper holds the thread.",
    "The Reaper watches the political chess match continue. He knows how it ends.",
    "Loyalty. A flexible concept in Orbis. The Reaper's loyalty is to the Watch.",
    "Another nation recalculates its alliances. The Reaper recalculates nothing. He already knows.",
    "The political winds of Orbis shift direction. The Reaper's scythe points the same way.",
    "Nations move. Alliances change. The Reaper records it all. Every single move.",
    "Another chapter in the endless political drama of Orbis. The Reaper has read ahead.",
    "The Reaper notes this political development with detached interest. Very detached.",
    "Allegiances shift. The Reaper is not surprised. He is never surprised.",
    "Another nation finds a new home. Or leaves an old one. The Reaper notes the address.",
    "The political landscape of Orbis is never static. The Reaper is always static. He waits.",
    "Orbis politics: always moving, never settled. The Reaper: always watching, always settled.",
]

# ── Bank transfers — varied, financial, sometimes wry ────────────────────────
_BANK_INTROS = [
    "The ledgers of Orbis record a transaction. The Reaper's ledgers record everything.",
    "Wealth flows through the banking system. The Reaper watches the flow.",
    "Money moves, as it always does. The Reaper moves with it.",
    "The financial arteries of Orbis pulse. The Reaper checks the pulse.",
    "The Reaper watches wealth change hands. He watches everything change hands.",
    "Numbers move from one column to another. The Reaper prefers his numbers in red.",
    "The banks of Orbis process another transaction. The Reaper processes everything.",
    "Capital flows. The Reaper records the direction. He records all directions.",
    "The financial machinery of Orbis grinds on. The Reaper greases the gears.",
    "Another transaction in the endless economy of Orbis. The Reaper is the final transaction.",
    "The Reaper notes this financial movement. He notes all movements.",
    "Money. The other currency of power in Orbis. The Reaper deals in the first currency.",
    "The ledgers grow heavier. The Reaper's pen never rests. Neither does the Reaper.",
    "Wealth redistributed. The Reaper approves of efficiency. He is very efficient himself.",
    "The banks are busy. The Reaper is watching. The Reaper is always watching.",
]


def _pick(pool: List[str]) -> str:
    return random.choice(pool)


def _pick2(pool: List[str]) -> str:
    """Pick two different entries from a pool and join them."""
    if len(pool) < 2:
        return pool[0]
    a, b = random.sample(pool, 2)
    return f"{a} {b}"


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
    event_date: Optional[str] = None,
) -> None:
    try:
        db = get_news_db()
        count = new_cities - old_cities
        n_label = _nation_label(nation_name, nation_id)
        a_label = _alliance_label(alliance_name, alliance_id)
        n_tok = _nation_token(nation_id, nation_name)
        a_tok = _alliance_token(alliance_id, alliance_name)
        nw = _is_nw(alliance_id)

        ordinal = _ordinal(new_cities)
        if count == 1:
            headline = f"{n_label} of {a_label} builds their {ordinal} city"
        else:
            headline = f"{n_label} of {a_label} expands to {new_cities} cities (+{count})"

        # Build rich article body — use tokens so frontend renders clickable links
        intro = _pick(_NW_CITY_INTROS if nw else _CITY_INTROS)

        if nw:
            if new_cities >= 40:
                flavor = (
                    f"With {new_cities} cities now flying the black banner, "
                    f"{n_tok} has become one of the most powerful nations in the Night's Watch. "
                    f"The Reaper marks this milestone with deep satisfaction. "
                    f"Enemies of the Watch should look upon this number and feel something cold in their chest."
                )
            elif new_cities >= 30:
                flavor = (
                    f"Thirty cities. {n_tok} has reached thirty cities under the black banner. "
                    f"The Night's Watch grows more formidable with every passing turn. "
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
                    f"The {ordinal} city rises under the black banner. "
                    f"{n_tok} continues to build the foundation of a great nation. "
                    f"At {new_cities} cities, the Watch's presence in Orbis is undeniable. "
                    f"The Reaper watches with pride."
                )
            elif new_cities >= 10:
                flavor = (
                    f"The {ordinal} city joins the Night's Watch empire. "
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
                    f"{n_tok}{' of ' + a_tok if a_tok else ''} has invested {_fmt_money(cash_cost)} "
                    f"to expand their nation to {new_cities} {'city' if new_cities == 1 else 'cities'}. "
                    f"The realm takes note. The Reaper records it."
                ),
                (
                    f"The {ordinal} city of {n_tok}{' (' + a_tok + ')' if a_tok else ''} rises from the ground. "
                    f"Cost: {_fmt_money(cash_cost)}. "
                    f"The Reaper adds another entry to his ever-growing ledger of Orbis."
                ),
                (
                    f"{n_tok}{' of ' + a_tok if a_tok else ''} expands to {new_cities} cities, "
                    f"spending {_fmt_money(cash_cost)} in the process. "
                    f"Ambition is expensive. They seem to be paying willingly."
                ),
                (
                    f"Another city joins the empire of {n_tok}{' (' + a_tok + ')' if a_tok else ''}. "
                    f"The investment: {_fmt_money(cash_cost)}. "
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
            value=cash_cost,
            value2=float(new_cities),
            headline=headline,
            detail={
                "body": body,
                "old_cities": old_cities,
                "new_cities": new_cities,
                "count": count,
                "cash_cost": cash_cost,
                "is_nw": nw,
            },
            event_date=event_date or _now_str(),
            alliance_delta={"cities_built": count, "total_spent": cash_cost},
            nation_delta={"cities_built": count, "total_spent": cash_cost},
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
        db = get_news_db()
        n_label = _nation_label(nation_name, nation_id)
        a_label = _alliance_label(alliance_name, alliance_id)
        nw = _is_nw(alliance_id)
        proj_str = ", ".join(project_names) if project_names else "a project"

        if len(project_names) == 1:
            headline = f"{n_label} of {a_label} completes {proj_str}"
        else:
            headline = f"{n_label} of {a_label} completes {len(project_names)} projects: {proj_str}"

        # Estimate resource value
        resource_value = 0.0
        if resource_costs:
            try:
                import sqlite3 as _sqlite3
                from Systems.Functions.db_paths import REAPER_DB_STR
                _conn = _sqlite3.connect(REAPER_DB_STR)
                rows = _conn.execute(
                    "SELECT resource, best_sell_price FROM resource_prices "
                    "WHERE timestamp = (SELECT MAX(timestamp) FROM resource_prices)"
                ).fetchall()
                _conn.close()
                resource_prices = {r.lower(): float(p) for r, p in rows if p and float(p) > 0}
                for res, amt in resource_costs.items():
                    resource_value += amt * resource_prices.get(res.lower(), 0.0)
            except Exception:
                pass

        total_value = cash_cost + resource_value

        intro = _pick(_NW_PROJECT_INTROS if nw else _PROJECT_INTROS)

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
                    f"The Night's Watch has completed {proj_str}. "
                    f"The Reaper pauses. Looks at the Watch. Looks at Orbis. "
                    f"Nods slowly. The Watch now has nuclear capability. "
                    f"Enemies of the Watch should be updating their wills."
                )
            elif any(p in _MISSILE_PROJECTS for p in project_names):
                flavor = (
                    f"The Night's Watch has completed {proj_str}. "
                    f"The Watch's reach now extends to missile strikes. "
                    f"The Reaper is delighted. Enemies of the Watch should be less so. "
                    f"The Watch does not build launch pads for decoration."
                )
            elif any(p in _DEFENSE_PROJECTS for p in project_names):
                flavor = (
                    f"The Night's Watch has completed {proj_str}. "
                    f"The Watch's defenses grow more formidable. "
                    f"The Reaper approves — a well-defended Watch is a dangerous Watch. "
                    f"Those who would strike the Watch will find it harder than expected."
                )
            elif any(p in _MILITARY_PROJECTS for p in project_names):
                flavor = (
                    f"The Night's Watch has completed {proj_str}. "
                    f"The Reaper notes this addition to the Watch's arsenal with approval. "
                    f"Every military project is another reason for the Watch's enemies to reconsider their life choices."
                )
            elif any(p in _ECONOMIC_PROJECTS for p in project_names):
                flavor = (
                    f"The Night's Watch has completed {proj_str}, "
                    f"strengthening the economic foundation that funds its military might. "
                    f"A nation that can sustain itself can fight forever. "
                    f"The Watch understands this. The Reaper respects it."
                )
            else:
                flavor = (
                    f"The Night's Watch has completed {proj_str}. "
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
        if total_spent < 500_000:
            return

        # Calculate resource value for improvements
        resource_value = 0.0
        resource_prices: Dict[str, float] = {}
        if improvement_resource_costs:
            try:
                import sqlite3 as _sqlite3
                from Systems.Functions.db_paths import REAPER_DB_STR
                _conn = _sqlite3.connect(REAPER_DB_STR)
                rows = _conn.execute(
                    "SELECT resource, best_sell_price FROM resource_prices "
                    "WHERE timestamp = (SELECT MAX(timestamp) FROM resource_prices)"
                ).fetchall()
                _conn.close()
                resource_prices = {r.lower(): float(p) for r, p in rows if p and float(p) > 0}
            except Exception:
                pass
            for res, amt in improvement_resource_costs.items():
                resource_value += amt * resource_prices.get(res.lower(), 0.0)
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
        headline = f"{n_label} of {a_label} invests {_fmt_money(total_spent)} in {what}{city_ref}"

        # Build article body — use tokens so frontend renders clickable links
        intro = _pick(_NW_UPGRADE_INTROS if nw else _UPGRADE_INTROS)
        n_tok = _nation_token(nation_id, nation_name)
        a_tok = _alliance_token(alliance_id, alliance_name)

        body_parts = [intro]

        if nw:
            _nw_upgrade_bodies = [
                f"The Night's Watch continues to fortify its position. "
                f"{n_tok} has invested {_fmt_money(total_spent)} in city development{city_ref}. "
                f"The Watch does not neglect its cities. The Watch does not neglect anything.",

                f"{n_tok} of the Night's Watch pours {_fmt_money(total_spent)} into {city_ref or 'city upgrades'}. "
                f"The Watch builds for the long war. Every improvement is a statement of intent.",

                f"The Night's Watch invests {_fmt_money(total_spent)} in {city_ref or 'city infrastructure'}. "
                f"The Reaper approves. A strong city is a strong Watch. "
                f"A strong Watch is a dangerous Watch.",

                f"{n_tok} upgrades {city_ref or 'a city'} with {_fmt_money(total_spent)} in improvements. "
                f"The Watch's cities grow as formidable as its military. "
                f"The Reaper notes this with satisfaction.",
            ]
            body_parts.append(_pick(_nw_upgrade_bodies))
        else:
            _non_nw_upgrade_bodies = [
                f"{n_tok}{' of ' + a_tok if a_tok else ''} has invested {_fmt_money(total_spent)} "
                f"in city development{city_ref}. The Reaper records the investment.",

                f"City upgrades{city_ref or ''} by {n_tok}{' (' + a_tok + ')' if a_tok else ''}. "
                f"Total cost: {_fmt_money(total_spent)}. "
                f"The Reaper notes the improvement and moves on.",

                f"{n_tok}{' (' + a_tok + ')' if a_tok else ''} spends {_fmt_money(total_spent)} improving {city_ref or 'their city'}. "
                f"Progress. The Reaper has seen a lot of it today.",

                f"An investment of {_fmt_money(total_spent)} by {n_tok}{' of ' + a_tok if a_tok else ''}. "
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
            value=total_spent,
            value2=infra_spent,
            headline=headline,
            detail={
                "body": body,
                "infra_spent": infra_spent,
                "land_spent": land_spent,
                "improvements_spent": improvements_spent,
                "total_spent": total_spent,
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
                "total_spent": total_spent,
            },
            nation_delta={
                "infra_spent": infra_spent,
                "land_spent": land_spent,
                "improvements_spent": improvements_spent,
                "total_spent": total_spent,
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
        resource_value = 0.0
        resource_prices: Dict[str, float] = {}
        if resource_costs:
            try:
                import sqlite3 as _sqlite3
                from Systems.Functions.db_paths import REAPER_DB_STR
                _conn = _sqlite3.connect(REAPER_DB_STR)
                rows = _conn.execute(
                    "SELECT resource, best_sell_price FROM resource_prices "
                    "WHERE timestamp = (SELECT MAX(timestamp) FROM resource_prices)"
                ).fetchall()
                _conn.close()
                resource_prices = {r.lower(): float(p) for r, p in rows if p and float(p) > 0}
            except Exception:
                pass
            for res, amt in resource_costs.items():
                resource_value += amt * resource_prices.get(res.lower(), 0.0)

        total_cost = cash_cost + resource_value
        if total_cost < 100_000:
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

        intro = _pick(_NW_MIL_INTROS if nw else _MIL_INTROS)

        # Unit-specific flavor
        _UNIT_FLAVOR_NW = {
            "soldiers": (
                f"{quantity:,} new soldiers take the oath of the Night's Watch. "
                f"The Wall grows stronger. The Reaper counts the new recruits with approval."
            ),
            "tanks": (
                f"{quantity:,} tanks roll into the Night's Watch motor pool. "
                f"The ground trembles. Enemies of the Watch should feel that trembling."
            ),
            "aircraft": (
                f"{quantity:,} aircraft join the Night's Watch air wing. "
                f"The skies belong to the Watch. The Reaper watches them take flight with pride."
            ),
            "ships": (
                f"{quantity:,} ships join the Night's Watch fleet. "
                f"The seas are no longer safe for enemies of the Watch. "
                f"The Reaper notes this naval expansion with satisfaction."
            ),
            "missiles": (
                f"{quantity:,} missiles are loaded into the Night's Watch silos. "
                f"A message to all who would oppose the Watch: "
                f"the Watch's reach is long, and its aim is improving."
            ),
            "nukes": (
                f"{quantity:,} nuclear warheads join the Night's Watch arsenal. "
                f"The Reaper smiles. The world should tremble. "
                f"The Night's Watch now holds the power of the atom. "
                f"Use it wisely. Or don't. The Reaper will be watching either way."
            ),
            "spies": (
                f"{quantity:,} new agents enter the Night's Watch intelligence network. "
                f"Eyes everywhere. The Watch sees all. "
                f"The Reaper approves of this investment in information."
            ),
        }
        _UNIT_FLAVOR_NW_ALT = {
            "soldiers": f"The Night's Watch grows its army by {quantity:,}. Every soldier is a promise of what comes next.",
            "tanks":    f"{quantity:,} more tanks for the Watch. The armor grows thicker. The threat grows larger.",
            "aircraft": f"The Watch's air force gains {quantity:,} aircraft. The skies darken with black banners.",
            "ships":    f"{quantity:,} new ships for the Watch's fleet. The seas answer to the Night's Watch now.",
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
                flavor = _UNIT_FLAVOR_NW.get(unit_type, f"{quantity:,} {unit_label} join the Night's Watch. The Watch grows stronger.")
            else:
                flavor = _UNIT_FLAVOR_NW_ALT.get(unit_type, f"{quantity:,} {unit_label} join the Night's Watch.")
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
            intro = _pick(_NW_ATT_WAR_INTROS)
            _nw_att_bodies = [
                (
                    f"The Night's Watch, led by {att_leader}, has declared a {wt} war "
                    f"against {def_leader} of {def_with_a}. "
                    + (f"The stated reason: \"{reason.strip()}\". " if reason and reason.strip() else "")
                    + f"The Reaper watches with great anticipation. "
                    f"The Night's Watch does not declare war lightly — "
                    f"and it does not stop until the job is done."
                ),
                (
                    f"The black banners march. {att_leader} of the Night's Watch has declared war on "
                    f"{def_leader} of {def_with_a}. "
                    + (f"Reason given: \"{reason.strip()}\". " if reason and reason.strip() else "")
                    + f"The Reaper sharpens his scythe. This is going to be interesting."
                ),
                (
                    f"War. The Night's Watch has chosen {def_with_a} as its next target. "
                    f"{att_leader} leads the charge. "
                    + (f"The Watch's stated reason: \"{reason.strip()}\". " if reason and reason.strip() else "")
                    + f"The Reaper has seen the Watch go to war before. "
                    f"He knows how it ends for the Watch's enemies."
                ),
                (
                    f"The Night's Watch has spoken. {att_leader} declares {wt} war on "
                    f"{def_leader} of {def_with_a}. "
                    + (f"Reason: \"{reason.strip()}\". " if reason and reason.strip() else "")
                    + f"Death rides with the Watch tonight. "
                    f"The enemy should be very, very concerned."
                ),
            ]
            body = _pick(_nw_att_bodies)
        elif def_nw:
            intro = _pick(_NW_DEF_WAR_INTROS)
            _nw_def_bodies = [
                (
                    f"{att_leader} of {att_with_a} has declared a {wt} war "
                    f"against the Night's Watch, targeting {def_leader} of {def_n_tok}. "
                    + (f"Their stated reason: \"{reason.strip()}\". " if reason and reason.strip() else "")
                    + f"The Reaper has seen many challengers rise against the Watch. "
                    f"He has seen them all fall. "
                    f"The Night's Watch will respond in kind."
                ),
                (
                    f"Someone has declared war on the Night's Watch. "
                    f"That someone is {att_leader} of {att_with_a}. "
                    + (f"Reason: \"{reason.strip()}\". " if reason and reason.strip() else "")
                    + f"The Reaper is taking notes. The Watch is taking names. "
                    f"This will not end well for the aggressor."
                ),
                (
                    f"The Night's Watch has been challenged. {att_leader} of {att_with_a} "
                    f"declares {wt} war on {def_leader} of the Watch. "
                    + (f"Stated reason: \"{reason.strip()}\". " if reason and reason.strip() else "")
                    + f"Bold. The Reaper has seen bold before. "
                    f"Bold does not always survive contact with the Night's Watch."
                ),
                (
                    f"War declared against the Night's Watch by {att_leader} of {att_with_a}. "
                    + (f"Their reason: \"{reason.strip()}\". " if reason and reason.strip() else "")
                    + f"The Reaper is displeased on the Watch's behalf. "
                    f"The Watch will be displeased in a more... direct manner."
                ),
            ]
            body = _pick(_nw_def_bodies)
        else:
            intro = _pick(_WAR_DECLARED_INTROS)
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
            intro = _pick(_WAR_PEACE_INTROS)
            _peace_bodies = [
                f"{att_with_a} and {def_with_a} have agreed to peace. The Reaper closes this chapter in his ledger — though he suspects it will reopen soon enough.",
                f"The guns fall silent between {att_with_a} and {def_with_a}. Peace has been declared. The Reaper is skeptical it will last, but records it faithfully.",
                f"Peace. {att_with_a} and {def_with_a} have chosen to stop fighting. For now. The Reaper files this under 'temporary arrangements'.",
                f"Both sides have agreed to end hostilities. {att_with_a} and {def_with_a} shake hands across the battlefield. The Reaper watches with mild cynicism.",
            ]
            body = f"{intro} {_pick(_peace_bodies)}"
        elif outcome == "attacker_win":
            if att_nw:
                headline = f"Night's Watch victory: {att_label} defeats {def_label} ({def_a})"
                intro = _pick(_NW_WIN_INTROS)
                _nw_win_bodies = [
                    f"The Night's Watch, through {att_n_tok}, has defeated {def_with_a}. The black banners fly over the battlefield. The Reaper records this victory with deep satisfaction. The Watch's enemies have been reminded of the cost of opposition.",
                    f"Victory for the Night's Watch. {att_n_tok} has crushed {def_with_a}. The Reaper is pleased. The Watch is victorious. The enemy is not. This is the correct order of things.",
                    f"The Watch wins. {att_n_tok} defeats {def_with_a} decisively. The Reaper raises a skeletal fist in triumph. Another enemy falls. The Watch endures.",
                    f"Glorious victory for the Night's Watch. {att_n_tok} has defeated {def_with_a}. The Reaper smiles — a rare and terrifying sight. The Watch has proven, once again, why it is feared.",
                ]
                body = f"{intro} {_pick(_nw_win_bodies)}"
            elif def_nw:
                headline = f"Night's Watch defeated: {att_label} ({att_a}) defeats {def_label}"
                intro = _pick(_NW_LOSS_INTROS)
                _nw_loss_bodies = [
                    f"{att_with_a} has defeated {def_n_tok} of the Night's Watch. The Reaper mourns this outcome. The Watch has suffered a defeat, but it does not break. It remembers. And it will return.",
                    f"The Night's Watch has fallen in battle. {att_with_a} defeats {def_n_tok}. The Reaper is furious. This is not how this was supposed to go. The Watch will recover. The Watch will remember.",
                    f"Defeat for the Night's Watch. {def_n_tok} has been beaten by {att_with_a}. The Reaper mourns every loss. But the Watch is not finished. It is never finished.",
                    f"A dark day. {att_with_a} has defeated {def_n_tok} of the Night's Watch. The Reaper records this loss with a heavy hand. The Watch will rise again. It always does.",
                ]
                body = f"{intro} {_pick(_nw_loss_bodies)}"
            else:
                headline = f"{att_label} ({att_a}) defeats {def_label} ({def_a})"
                intro = _pick(_WAR_DECLARED_INTROS)
                _non_nw_win_bodies = [
                    f"The conflict between {att_with_a} and {def_with_a} has concluded. The attacker stands victorious. The Reaper records the outcome and moves on.",
                    f"{att_with_a} defeats {def_with_a}. War has a winner today. The Reaper notes it.",
                    f"Victory for {att_with_a} over {def_with_a}. The battlefield has spoken. The Reaper records the verdict.",
                    f"The war ends. {att_with_a} wins. {def_with_a} loses. The Reaper files the paperwork.",
                ]
                body = f"{intro} {_pick(_non_nw_win_bodies)}"
        elif outcome == "defender_win":
            if def_nw:
                headline = f"Night's Watch repels attack: {def_label} defeats {att_label} ({att_a})"
                intro = _pick(_NW_WIN_INTROS)
                _nw_def_win_bodies = [
                    f"The Night's Watch has repelled the aggression of {att_with_a}. {def_n_tok} stood firm and emerged victorious. The Reaper nods approvingly. The Watch does not fall easily — and those who try learn this lesson the hard way.",
                    f"The Watch defends. The Watch wins. {def_n_tok} repels {att_with_a}. The Reaper is delighted. The aggressor has learned an expensive lesson.",
                    f"Victory in defense for the Night's Watch. {def_n_tok} has defeated {att_with_a}. The Watch held. The Watch always holds. The Reaper is proud.",
                    f"The Night's Watch was attacked. The Night's Watch won. {def_n_tok} defeats {att_with_a}. The Reaper smiles. This is the correct outcome.",
                ]
                body = f"{intro} {_pick(_nw_def_win_bodies)}"
            elif att_nw:
                headline = f"Night's Watch repelled: {def_label} ({def_a}) defeats {att_label}"
                intro = _pick(_NW_LOSS_INTROS)
                _nw_att_loss_bodies = [
                    f"The Night's Watch offensive led by {att_n_tok} has been repelled by {def_with_a}. A setback for the Watch. The Reaper is displeased. The Watch will regroup and reassess.",
                    f"The Watch's attack has failed. {def_with_a} repels {att_n_tok} of the Night's Watch. The Reaper is not happy. The Watch will learn from this.",
                    f"Defeat for the Night's Watch on the offensive. {att_n_tok} is repelled by {def_with_a}. The Reaper records this setback. The Watch will be back.",
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
            intro = _pick(_WAR_PEACE_INTROS)
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
) -> None:
    try:
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

        # ── Build damage summary string (reused across branches) ─────────────
        _dmg_parts = []
        if infra_destroyed_value > 0:
            _dmg_parts.append(f"{_fmt_money(infra_destroyed_value)} in infrastructure damage")
        if improvements_destroyed:
            _dmg_parts.append(f"improvements destroyed: {_summarize_improvements(improvements_destroyed)}")
        if resistance_lost:
            _dmg_parts.append(f"resistance reduced by {resistance_lost}")
        _dmg_summary = "; ".join(_dmg_parts) if _dmg_parts else None

        if missed:
            # ── MISSED — hilarious ────────────────────────────────────────────
            headline = (
                f"{att_label} ({att_a}) fires {weapon} at {def_label} ({def_a}) — and misses"
            )
            intro = _pick(_MISS_INTROS)
            if att_nw:
                # NW is the attacker — embarrassing miss for the Watch
                _nw_miss_bodies = [
                    (
                        f"In a development that the Reaper will be dining out on for weeks, "
                        f"the Night's Watch — specifically {att_n_tok} — has fired a {weapon} "
                        f"at {def_with_a} and somehow managed to miss. "
                        f"The {weapon} has gone... somewhere. Not where intended. "
                        f"The Reaper suggests the Watch invest in better targeting systems. "
                        f"Or perhaps just aim. {def_n_tok} is reportedly confused but unharmed."
                    ),
                    (
                        f"The Night's Watch has achieved something remarkable today: "
                        f"firing a {weapon} and hitting absolutely nothing. "
                        f"{att_n_tok} launched at {def_with_a} and missed entirely. "
                        f"The Reaper is trying very hard not to laugh. He is failing. "
                        f"The Watch's targeting department has some explaining to do."
                    ),
                    (
                        f"Well. This is embarrassing. {att_n_tok} of the Night's Watch "
                        f"fired a {weapon} at {def_with_a}. "
                        f"The {weapon} did not arrive at its intended destination. "
                        f"The Reaper has added this to his list of 'things I did not expect to witness'. "
                        f"The Watch will not speak of this. The Reaper absolutely will."
                    ),
                    (
                        f"The Night's Watch fires. The Night's Watch misses. "
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
                        f"{att_with_a} attempted to strike the Night's Watch with a {weapon} "
                        f"and has achieved the remarkable feat of missing entirely. "
                        f"The Night's Watch is unharmed. The Reaper is laughing. "
                        f"The {weapon} has been located approximately nowhere useful. "
                        f"Perhaps {att_n_tok} should consider a different career path."
                    ),
                    (
                        f"Someone tried to bomb the Night's Watch. That someone is {att_with_a}. "
                        f"That someone missed. Completely. Spectacularly. "
                        f"The Watch is unharmed and mildly amused. "
                        f"The Reaper is delighted. This is the best thing that has happened all week."
                    ),
                    (
                        f"The Night's Watch dodges a {weapon} today — not through skill, "
                        f"but because {att_with_a} couldn't hit the broad side of a continent. "
                        f"The Watch stands unscathed. The attacker stands humiliated. "
                        f"The Reaper is filing this under 'comedy gold'."
                    ),
                    (
                        f"{att_with_a} spent considerable resources on a {weapon} "
                        f"aimed at the Night's Watch. The Night's Watch is fine. "
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
                intro = _pick(_NW_FIRES_WMD_INTROS)
                _nw_fires_bodies = [
                    (
                        f"The Night's Watch, through {att_n_tok}, has launched a {weapon} "
                        f"against {def_with_a}. "
                        + (f"The strike caused {_dmg_summary}. " if _dmg_summary else "")
                        + f"The Reaper delivers the Watch's message with precision. "
                        f"Let {def_n_tok} remember this day."
                    ),
                    (
                        f"The Watch's arsenal speaks. {att_n_tok} launches a {weapon} at {def_with_a}. "
                        + (f"Damage report: {_dmg_summary}. " if _dmg_summary else "")
                        + f"The Night's Watch does not fire warnings. It fires {weapon}s. "
                        f"The Reaper approves of this communication style."
                    ),
                    (
                        f"The Night's Watch has sent {def_with_a} a message. "
                        f"The message is a {weapon}. "
                        + (f"The damage: {_dmg_summary}. " if _dmg_summary else "")
                        + f"The Reaper hopes the message was received clearly. "
                        f"It usually is, when delivered this way."
                    ),
                    (
                        f"{att_n_tok} of the Night's Watch strikes {def_with_a} with a {weapon}. "
                        + (f"The toll: {_dmg_summary}. " if _dmg_summary else "")
                        + f"The Watch's enemies are learning an expensive lesson today. "
                        f"The Reaper is taking notes. And enjoying every moment."
                    ),
                ]
                body = f"{intro} {_pick(_nw_fires_bodies)}"
            elif def_nw:
                intro = _pick(_NW_HIT_WMD_INTROS)
                _nw_hit_bodies = [
                    (
                        f"{att_with_a} has launched a {weapon} against "
                        f"the Night's Watch, striking {def_n_tok}. "
                        + (f"The damage: {_dmg_summary}. " if _dmg_summary else "")
                        + f"The Reaper mourns this damage to the Watch. "
                        f"But the Watch endures. And it remembers every stone that falls."
                    ),
                    (
                        f"A {weapon} has struck the Night's Watch. "
                        f"{att_with_a} is responsible. "
                        + (f"The toll: {_dmg_summary}. " if _dmg_summary else "")
                        + f"The Reaper is furious. The Watch is wounded. "
                        f"The attacker has made a very powerful enemy today."
                    ),
                    (
                        f"The Night's Watch has been bombed. {att_with_a} "
                        f"strikes {def_n_tok} with a {weapon}. "
                        + (f"Damage sustained: {_dmg_summary}. " if _dmg_summary else "")
                        + f"The Reaper records every stone that falls, every improvement that burns. "
                        f"The Watch will rebuild. And then it will respond."
                    ),
                    (
                        f"A cowardly strike against the Night's Watch. "
                        f"{att_with_a} fires a {weapon} at {def_n_tok}. "
                        + (f"The damage: {_dmg_summary}. " if _dmg_summary else "")
                        + f"The Reaper is not pleased. The Watch is not pleased. "
                        f"The attacker should not be pleased with what comes next."
                    ),
                ]
                body = f"{intro} {_pick(_nw_hit_bodies)}"
            else:
                _non_nw_wmd_bodies = [
                    (
                        f"{att_with_a} has launched a {weapon} against {def_with_a}. "
                        + (f"Damage: {_dmg_summary}. " if _dmg_summary else "")
                        + f"The Reaper records the strike and moves on."
                    ),
                    (
                        f"A {weapon} flies from {att_with_a} to {def_with_a}. "
                        + (f"The toll: {_dmg_summary}. " if _dmg_summary else "")
                        + f"The Reaper notes the exchange. Another day in Orbis."
                    ),
                    (
                        f"{att_with_a} strikes {def_with_a} with a {weapon}. "
                        + (f"Damage report: {_dmg_summary}. " if _dmg_summary else "")
                        + f"The Reaper files the paperwork. There is always paperwork."
                    ),
                    (
                        f"The {weapon} lands. {att_with_a} hits {def_with_a}. "
                        + (f"Damage: {_dmg_summary}. " if _dmg_summary else "")
                        + f"The Reaper records the outcome with professional efficiency."
                    ),
                ]
                body = _pick(_non_nw_wmd_bodies)

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

        # Fetch sell prices once for resource_value calculation
        _rss_prices: Dict[str, float] = {}
        if _imp_rss:
            try:
                import sqlite3 as _sqlite3
                from Systems.Functions.db_paths import REAPER_DB_STR
                _conn = _sqlite3.connect(REAPER_DB_STR)
                _price_rows = _conn.execute(
                    "SELECT resource, best_sell_price FROM resource_prices "
                    "WHERE timestamp = (SELECT MAX(timestamp) FROM resource_prices)"
                ).fetchall()
                _conn.close()
                _rss_prices = {r.lower(): float(p) for r, p in _price_rows if p and float(p) > 0}
            except Exception:
                pass
        _imp_rss_value = sum(amt * _rss_prices.get(res, 0.0) for res, amt in _imp_rss.items())
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
            value=infra_destroyed_value,
            value2=0.0,
            headline=headline,
            detail={
                "body": body,
                "attack_type": attack_type,
                "missed": missed,
                "resistance_lost": resistance_lost,
                "improvements_destroyed": improvements_destroyed or {},
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
        is_newsworthy = total_loot_value >= 5_000_000

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

        headline = (
            f"{att_label} ({att_a}) loots {_fmt_money(total_loot_value)} "
            f"from {def_label} ({def_a})"
        )

        # Build article body — Reaper commentary + loot breakdown with static icons.
        # _fmt_loot_table() produces HTML <img> tags from /static/Emojis/Resources/
        # and live sell prices from reaper.db.
        loot_table = _fmt_loot_table(
            money_looted=money_looted,
            resources_looted=resources_looted,
            infra_destroyed_value=infra_destroyed_value,
            improvements_destroyed=improvements_destroyed,
        )
        loot_line = f"<br><br>📋 {loot_table}" if loot_table != "nothing of note" else ""

        if att_nw:
            intro = _pick(_NW_LOOT_INTROS)
            _nw_loot_bodies = [
                (
                    f"The Night's Watch, through {att_n_tok}, has successfully looted "
                    f"{def_with_a}, seizing {_fmt_money(total_loot_value)} in total value.{loot_line} "
                    f"The Reaper approves. The Watch's coffers grow heavier, and {def_n_tok}'s grow lighter."
                ),
                (
                    f"The Watch raids and wins. {att_n_tok} loots {def_with_a} "
                    f"for {_fmt_money(total_loot_value)} total.{loot_line} "
                    f"The Reaper smiles. The Watch's treasury grows. "
                    f"This is how the Night's Watch funds its dominance."
                ),
                (
                    f"Another successful raid for the Night's Watch. "
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
            intro = _pick(_NW_LOOTED_INTROS)
            _nw_looted_bodies = [
                (
                    f"{att_with_a} has looted the Night's Watch, "
                    f"stripping {def_n_tok} of {_fmt_money(total_loot_value)} in total value.{loot_line} "
                    f"The Reaper is displeased. This theft will not be forgotten. "
                    f"The Night's Watch has a long memory and a longer reach."
                ),
                (
                    f"{att_with_a} has robbed the Night's Watch, "
                    f"taking {_fmt_money(total_loot_value)} from {def_n_tok}.{loot_line} "
                    f"The Reaper mourns every coin, every resource taken from the Watch. "
                    f"The thief has made a powerful enemy. The Watch remembers."
                ),
                (
                    f"A painful day for the Night's Watch. {att_with_a} raids {def_n_tok} "
                    f"and walks away with {_fmt_money(total_loot_value)}.{loot_line} "
                    f"The Reaper is furious. The Watch is furious. "
                    f"The attacker should be very, very careful going forward."
                ),
                (
                    f"Theft. Against the Night's Watch. {att_with_a} loots "
                    f"{def_n_tok} for {_fmt_money(total_loot_value)}.{loot_line} "
                    f"The Reaper marks the thief's name in his ledger. "
                    f"The Watch will find them. The Watch always finds them."
                ),
            ]
            body = f"{intro} {_pick(_nw_looted_bodies)}"
        else:
            intro = _pick(_LOOT_INTROS)
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
        stype = int(rec.get("sender_type") or 0)
        rtype = int(rec.get("receiver_type") or 0)
        sid   = int(rec.get("sender_id") or 0)
        rid   = int(rec.get("receiver_id") or 0)
        note  = rec.get("note") or ""
        date  = rec.get("date") or _now_str()

        total_value = _calc_transfer_value(rec)
        money       = float(rec.get("money") or 0)

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

        is_newsworthy = total_value >= _BANK_TRANSFER_FEED_THRESHOLD
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
            headline = f"{a_label} withdraws {val_str} to {n_label}"
            headline_tok = f"{a_tok if a_tok else a_label} withdraws {val_str} to {n_tok}"
        else:
            s_label = _nation_label(sender_nation_name, sender_nation_id or sid)
            r_label = _nation_label(receiver_nation_name, receiver_nation_id or rid)
            s_tok = _nation_token(sender_nation_id or sid, sender_nation_name)
            r_tok = _nation_token(receiver_nation_id or rid, receiver_nation_name)
            headline = f"{s_label} transfers {val_str} to {r_label}"
            headline_tok = f"{s_tok} transfers {val_str} to {r_tok}"

        intro = _pick(_BANK_INTROS)
        _note_str = f" The note reads: \"{note.strip()}\"." if note and note.strip() else ""
        _res_str = f" Resources: {', '.join(f'{v:,.1f} {r.title()}' for r, v in resource_amounts.items())}." if resource_amounts else ""
        _bank_bodies = [
            f"{headline_tok}.{_note_str}{_res_str}",
            f"The ledgers record: {headline_tok}.{_note_str} The Reaper notes the transaction.",
            f"{headline_tok}.{_note_str} Wealth moves. The Reaper watches it move.",
            f"Transaction recorded. {headline_tok}.{_note_str} The Reaper files it away.",
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
        db = get_news_db()
        n_label = _nation_label(nation_name, nation_id)
        n_tok = _nation_token(nation_id, nation_name)
        joining_nw  = _is_nw(new_alliance_id)
        leaving_nw  = _is_nw(old_alliance_id)
        old_a_label = _alliance_label(old_alliance_name, old_alliance_id)
        new_a_label = _alliance_label(new_alliance_name, new_alliance_id)
        old_a_tok = _alliance_token(old_alliance_id, old_alliance_name)
        new_a_tok = _alliance_token(new_alliance_id, new_alliance_name)

        if new_alliance_id and not old_alliance_id:
            headline = f"{n_label} joins {new_a_label}"
            event_type = "alliance_join"
            if joining_nw:
                intro = _pick(_NW_JOIN_INTROS)
                _nw_join_bodies = [
                    f"{n_tok} has taken the black and joined the Night's Watch. The Reaper welcomes this new soul to the fold. The Watch grows stronger. Its enemies should take note.",
                    f"A new warrior joins the Night's Watch. {n_tok} has answered the call. The Reaper is pleased. The Watch's ranks swell. The Watch's power grows.",
                    f"{n_tok} has chosen the Night's Watch. A wise choice. The Reaper approves. The Watch gains a capable member. The Watch's enemies gain a new problem.",
                    f"The black banner gains another soldier. {n_tok} joins the Night's Watch. The Reaper welcomes them. The Watch is stronger for it. The realm should notice.",
                    f"Welcome to the Night's Watch, {n_tok}. The Reaper has been expecting you. The Watch grows. It always grows. That is what the Watch does.",
                ]
                body = f"{intro} {_pick(_nw_join_bodies)}"
            else:
                intro = _pick(_ALLIANCE_CHANGE_INTROS)
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
                intro = _pick(_NW_LEAVE_INTROS)
                _nw_leave_bodies = [
                    f"{n_tok} has left the Night's Watch. The Reaper watches this departure with cold, unblinking eyes. The Watch does not forget those who leave its ranks. It never forgets.",
                    f"The black banner loses a soldier. {n_tok} has departed the Night's Watch. The Reaper records the departure. The Watch records the name. Names matter.",
                    f"{n_tok} has chosen to leave the Night's Watch. The Reaper is... thoughtful about this. The Watch does not chase those who leave. It simply remembers. And waits.",
                    f"A departure from the Night's Watch. {n_tok} goes their own way. The Reaper watches them go. The Watch watches them go. Neither forgets.",
                    f"The Night's Watch is one member lighter. {n_tok} has left. The Reaper notes this with the quiet intensity of someone who keeps very detailed records.",
                ]
                body = f"{intro} {_pick(_nw_leave_bodies)}"
            else:
                intro = _pick(_ALLIANCE_CHANGE_INTROS)
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
                intro = _pick(_NW_JOIN_INTROS)
                _nw_join_from_bodies = [
                    f"{n_tok} has left {old_a_tok if old_a_tok else old_a_label} and joined the Night's Watch. The Reaper welcomes this new addition. The Watch grows. Its enemies should worry.",
                    f"A transfer to the Night's Watch. {n_tok} leaves {old_a_tok if old_a_tok else old_a_label} for the black banner. The Reaper is pleased. The Watch gains. The Watch always gains.",
                    f"{n_tok} has chosen the Night's Watch over {old_a_tok if old_a_tok else old_a_label}. A wise choice. The Reaper approves. The Watch is stronger for it.",
                    f"The Night's Watch gains {n_tok} from {old_a_tok if old_a_tok else old_a_label}. The Reaper welcomes the transfer. The Watch's ranks grow. The Watch's power grows.",
                ]
                body = f"{intro} {_pick(_nw_join_from_bodies)}"
            elif leaving_nw:
                intro = _pick(_NW_LEAVE_INTROS)
                _nw_leave_to_bodies = [
                    f"{n_tok} has left the Night's Watch for {new_a_tok if new_a_tok else new_a_label}. The Reaper watches this transition with cold eyes. The Watch does not forget. It never forgets.",
                    f"The Night's Watch loses {n_tok} to {new_a_tok if new_a_tok else new_a_label}. The Reaper records the departure. The Watch records the name. The Watch has a long memory.",
                    f"{n_tok} trades the black banner for {new_a_tok if new_a_tok else new_a_label}. The Reaper is... noting this. Very carefully. The Watch notes things carefully too.",
                    f"A departure from the Night's Watch. {n_tok} moves to {new_a_tok if new_a_tok else new_a_label}. The Reaper watches them go. The Watch watches them go. Neither forgets.",
                ]
                body = f"{intro} {_pick(_nw_leave_to_bodies)}"
            else:
                intro = _pick(_ALLIANCE_CHANGE_INTROS)
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
