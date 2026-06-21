"""
Centralised DB path constants for all Reaper databases.

Import from here instead of hardcoding paths in individual files:

    from Systems.Functions.db_paths import GLOBAL_NATIONS_DB, IRS_WARS_DB
    from Systems.Functions.db_paths import PETS_DB, REAPER_DB, TASKS_DB

IRSNations.db has been merged into GlobalNations.db.
All IRS_NATIONS_DB / EP_NATIONS_DB / NW_NATIONS_DB aliases now point to
GlobalNations.db so existing code continues to work without changes.
"""

from pathlib import Path

# ── Root ──────────────────────────────────────────────────────────────────────
_REAPER_ROOT = Path("c:/Users/codyr/DiscordBots/Reaper")
_DB_ROOT     = _REAPER_ROOT / "Databases"
_PNW_DIR     = _DB_ROOT / "PnW"
_PETS_DIR    = _DB_ROOT / "Pets"

# ── PnW DBs (Databases/PnW/) ──────────────────────────────────────────────────
GLOBAL_NATIONS_DB          = _PNW_DIR / "GlobalNations.db"          # single nations DB — all nations
NATIONS_SNAPSHOT_DB        = _PNW_DIR / "NationsSnapshot.db"        # live API snapshot for deletion diffing
NATIONS_SNAPSHOT_DB_STR    = str(NATIONS_SNAPSHOT_DB)
GLOBAL_WARS_DB    = _PNW_DIR / "GlobalWars.db"      # game-wide wars DB
IRS_WARS_DB       = _PNW_DIR / "IRSWars.db"
BANKRECS_DB       = _PNW_DIR / "bankrecs.db"
HOLDINGS_DB       = _PNW_DIR / "holdings.db"
TREATIES_DB       = _PNW_DIR / "Treaties.db"
VERIFIED_DB       = _PNW_DIR / "Verified.db"

# All NW/IRS/EP nation DB aliases point to GlobalNations.db (merged)
IRS_NATIONS_DB = GLOBAL_NATIONS_DB
EP_NATIONS_DB  = GLOBAL_NATIONS_DB
NW_NATIONS_DB  = GLOBAL_NATIONS_DB

EP_WARS_DB = IRS_WARS_DB
NW_WARS_DB = IRS_WARS_DB

GLOBAL_NATIONS_DB_STR = str(GLOBAL_NATIONS_DB)
GLOBAL_WARS_DB_STR    = str(GLOBAL_WARS_DB)
IRS_NATIONS_DB_STR    = GLOBAL_NATIONS_DB_STR   # alias → same file
IRS_WARS_DB_STR       = str(IRS_WARS_DB)
BANKRECS_DB_STR       = str(BANKRECS_DB)
HOLDINGS_DB_STR       = str(HOLDINGS_DB)
TREATIES_DB_STR       = str(TREATIES_DB)
VERIFIED_DB_STR       = str(VERIFIED_DB)

# Backward-compat string aliases
EP_NATIONS_DB_STR = GLOBAL_NATIONS_DB_STR
EP_WARS_DB_STR    = IRS_WARS_DB_STR
NW_NATIONS_DB_STR = GLOBAL_NATIONS_DB_STR
NW_WARS_DB_STR    = IRS_WARS_DB_STR

MY_NATIONS_DB     = _DB_ROOT / "MyNations.db"
MY_NATIONS_DB_STR = str(MY_NATIONS_DB)

# ── Pets DBs (Databases/Pets/) ────────────────────────────────────────────────
PETS_DB        = _PETS_DIR / "pets.db"
TASKS_DB       = _PETS_DIR / "Tasks.db"
POWERBALL_DB   = _PETS_DIR / "powerball.db"
SURVIVOR_DB    = _PETS_DIR / "survivorseries.db"
ABSORB_DB      = _PETS_DIR / "absorb.db"
COLOSSEUM_DB   = _PETS_DIR / "colosseum.db"

PETS_DB_STR        = str(PETS_DB)
TASKS_DB_STR       = str(TASKS_DB)
POWERBALL_DB_STR   = str(POWERBALL_DB)
SURVIVOR_DB_STR    = str(SURVIVOR_DB)
ABSORB_DB_STR      = str(ABSORB_DB)
COLOSSEUM_DB_STR   = str(COLOSSEUM_DB)

# ── Root DBs (Databases/) ─────────────────────────────────────────────────────
REAPER_DB  = _DB_ROOT / "reaper.db"
ALERTS_DB  = _DB_ROOT / "alerts.db"
ZOMBIE_DB  = _DB_ROOT / "zombie.db"
ACCESS_DB  = _DB_ROOT / "access.db"

REAPER_DB_STR  = str(REAPER_DB)
ALERTS_DB_STR  = str(ALERTS_DB)
ZOMBIE_DB_STR  = str(ZOMBIE_DB)
ACCESS_DB_STR  = str(ACCESS_DB)

# ── Tracking DB (Databases/PnW/) ──────────────────────────────────────────────
TRACKING_DB     = _PNW_DIR / "Tracking.db"
TRACKING_DB_STR = str(TRACKING_DB)

# ── Tickets DB (Databases/) ───────────────────────────────────────────────────
TICKETS_DB     = _DB_ROOT / "Tickets.db"
TICKETS_DB_STR = str(TICKETS_DB)

# Ensure subdirectories exist on import
_PNW_DIR.mkdir(parents=True, exist_ok=True)
_PETS_DIR.mkdir(parents=True, exist_ok=True)

# Alliance ID constant (used by DB helpers)
NW_ALLIANCE_ID = 10259
