"""
Centralised DB path constants for all Reaper databases.

Import from here instead of hardcoding paths in individual files:

    from Systems.Functions.db_paths import IRS_NATIONS_DB, IRS_WARS_DB, GLOBAL_NATIONS_DB
    from Systems.Functions.db_paths import PETS_DB, REAPER_DB, TASKS_DB

Note: GLOBAL_WARS_DB removed to avoid API issues - only NW wars are saved
"""

from pathlib import Path

# ── Root ──────────────────────────────────────────────────────────────────────
_REAPER_ROOT = Path("c:/Users/codyr/DiscordBots/Reaper")
_DB_ROOT     = _REAPER_ROOT / "Databases"
_PNW_DIR     = _DB_ROOT / "PnW"
_PETS_DIR    = _DB_ROOT / "Pets"

# ── PnW DBs (Databases/PnW/) ──────────────────────────────────────────────────
IRS_NATIONS_DB    = _PNW_DIR / "IRSNations.db"
IRS_WARS_DB       = _PNW_DIR / "IRSWars.db"
GLOBAL_NATIONS_DB = _PNW_DIR / "GlobalNations.db"
LOOT_DB           = _PNW_DIR / "loot.db"
BANKRECS_DB       = _PNW_DIR / "bankrecs.db"
HOLDINGS_DB       = _PNW_DIR / "holdings.db"
# GLOBAL_WARS_DB removed to avoid API issues - only NW wars are saved

# Aliases for backward compatibility
EP_NATIONS_DB     = IRS_NATIONS_DB
EP_WARS_DB        = IRS_WARS_DB
NW_NATIONS_DB     = IRS_NATIONS_DB
NW_WARS_DB        = IRS_WARS_DB

IRS_NATIONS_DB_STR    = str(IRS_NATIONS_DB)
IRS_WARS_DB_STR       = str(IRS_WARS_DB)
GLOBAL_NATIONS_DB_STR = str(GLOBAL_NATIONS_DB)
LOOT_DB_STR           = str(LOOT_DB)
BANKRECS_DB_STR       = str(BANKRECS_DB)
HOLDINGS_DB_STR       = str(HOLDINGS_DB)

# Aliases for backward compatibility
EP_NATIONS_DB_STR = IRS_NATIONS_DB_STR
EP_WARS_DB_STR    = IRS_WARS_DB_STR
NW_NATIONS_DB_STR = IRS_NATIONS_DB_STR
NW_WARS_DB_STR    = IRS_WARS_DB_STR
# GLOBAL_WARS_DB_STR removed

# ── Pets DBs (Databases/Pets/) ────────────────────────────────────────────────
PETS_DB      = _PETS_DIR / "pets.db"
TASKS_DB     = _PETS_DIR / "Tasks.db"
POWERBALL_DB = _PETS_DIR / "powerball.db"
SURVIVOR_DB  = _PETS_DIR / "survivorseries.db"

PETS_DB_STR      = str(PETS_DB)
TASKS_DB_STR     = str(TASKS_DB)
POWERBALL_DB_STR = str(POWERBALL_DB)
SURVIVOR_DB_STR  = str(SURVIVOR_DB)

# ── Root DBs (Databases/) ─────────────────────────────────────────────────────
REAPER_DB  = _DB_ROOT / "reaper.db"
ALERTS_DB  = _DB_ROOT / "alerts.db"
ZOMBIE_DB  = _DB_ROOT / "zombie.db"
ACCESS_DB  = _DB_ROOT / "access.db"

REAPER_DB_STR  = str(REAPER_DB)
ALERTS_DB_STR  = str(ALERTS_DB)
ZOMBIE_DB_STR  = str(ZOMBIE_DB)
ACCESS_DB_STR  = str(ACCESS_DB)

# ── Tickets DB (Databases/) ───────────────────────────────────────────────────
TICKETS_DB     = _DB_ROOT / "Tickets.db"
TICKETS_DB_STR = str(TICKETS_DB)

# Ensure subdirectories exist on import
_PNW_DIR.mkdir(parents=True, exist_ok=True)
_PETS_DIR.mkdir(parents=True, exist_ok=True)

