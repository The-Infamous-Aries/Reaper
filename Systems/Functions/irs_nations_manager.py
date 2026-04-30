"""
NW Nations Manager — manages Nights Watch nation data.

Public API (imported by reaper.py):
    sync_nations()          — full alliance member snapshot (run on startup)
    start_nations_subscription() — start live nation/update WebSocket listener
"""

import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from Systems.Functions.irs_nations_db import IRSNationsDB
from Systems.PnW.Util.query import create_v3_query_instance
from Systems.Functions.config import PANDW_API_V3_KEY

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

from Systems.Functions.db_paths import IRS_NATIONS_DB
DATABASE_DIR  = IRS_NATIONS_DB.parent
DATABASE_FILE = IRS_NATIONS_DB
ALLIANCE_ID   = 14225

# ── Safe nation fields (no baseball_team — causes PnW API internal server error) ──
_NATION_FIELDS = (
    "id alliance_position nation_name leader_name continent color flag discord discord_id "
    "war_policy domestic_policy social_policy government_type economic_policy update_tz "
    "vacation_mode_turns beige_turns tax_id num_cities score population "
    "gross_national_income gross_domestic_product espionage_available date last_active "
    "turns_since_last_city turns_since_last_project soldiers tanks aircraft ships missiles nukes spies "
    "money coal oil uranium iron bauxite lead gasoline munitions steel aluminum food "
    "wars_won wars_lost offensive_wars_count defensive_wars_count "
    "alliance_id alliance_seniority "
    "activity_center advanced_engineering_corps advanced_pirate_economy arable_land_agency "
    "arms_stockpile bauxite_works bureau_of_domestic_affairs center_for_civil_engineering "
    "clinical_research_center emergency_gasoline_reserve fallout_shelter "
    "government_support_agency green_technologies guiding_satellite "
    "central_intelligence_agency international_trade_center iron_dome iron_works "
    "moon_landing mars_landing mass_irrigation military_doctrine military_research_center "
    "military_salvage missile_launch_pad nuclear_launch_facility nuclear_research_facility "
    "pirate_economy propaganda_bureau recycling_initiative research_and_development_center "
    "space_program specialized_police_training_program spy_satellite surveillance_network "
    "telecommunications_satellite uranium_enrichment_program vital_defense_system "
    "military_research { ground_capacity air_capacity naval_capacity ground_cost air_cost naval_cost } "
    "alliance { id name } "
    "cities { id name date infrastructure land powered "
    "coal_power oil_power nuclear_power wind_power "
    "coal_mine oil_well uranium_mine lead_mine iron_mine bauxite_mine "
    "oil_refinery aluminum_refinery steel_mill munitions_factory factory farm "
    "police_station hospital recycling_center subway "
    "supermarket bank shopping_mall stadium barracks hangar drydock }"
)


def _ensure_database_directory():
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)


async def _fetch_alliance_nations(query_instance) -> list:
    """
    Fetch all Nights Watch member nations directly via GraphQL using safe field set.
    Bypasses query.get_alliance_nations() to avoid the baseball_team field that
    causes PnW API internal server errors.
    """
    nations: list = []
    page = 1
    while True:
        gql = f"""
        query {{
          nations(alliance_id: {ALLIANCE_ID}, first: 500, page: {page}) {{
            paginatorInfo {{ hasMorePages currentPage lastPage }}
            data {{ {_NATION_FIELDS} }}
          }}
        }}
        """
        try:
            raw = await query_instance._make_graphql_request(gql, timeout=60)
            block = (raw or {}).get("nations") or {}
            items = block.get("data") or []
            if not items:
                break
            nations.extend(items)
            if not block.get("paginatorInfo", {}).get("hasMorePages"):
                break
            page += 1
        except Exception as e:
            logger.error(f"_fetch_alliance_nations page {page} failed: {e}", exc_info=True)
            break
    return nations


# ── Full sync ─────────────────────────────────────────────────────────────────

async def sync_nations(force: bool = False) -> dict:
    """
    Pull all current Nights Watch member nations from the PnW API and upsert
    them (with cities) into the local DB.

    Args:
        force: If True, wipe the nations and cities tables first (full repopulate).
               If False (default), skip the sync entirely when the DB already has data.

    Returns dict with keys: nations_saved, cities_saved, total_nations, total_cities
    """
    try:
        _ensure_database_directory()
        db = IRSNationsDB(str(DATABASE_FILE))
        query = create_v3_query_instance(api_key=PANDW_API_V3_KEY, logger=logger)

        if force:
            logger.info("sync_nations(force=True): wiping nations and cities tables...")
            async with db._lock:
                import sqlite3 as _sqlite3
                with _sqlite3.connect(str(DATABASE_FILE)) as conn:
                    conn.execute("DELETE FROM cities")
                    conn.execute("DELETE FROM nations")
                    conn.commit()
            logger.info("Tables cleared — starting fresh repopulate")
        else:
            # Skip full sync if DB already has data — subscriptions keep it current
            stats = await db.get_stats()
            if stats["nations"] > 0:
                logger.info(
                    f"sync_nations: DB already has {stats['nations']} nations and "
                    f"{stats['cities']} cities — skipping full sync (use force=True to repopulate)"
                )
                return {
                    "nations_saved": 0,
                    "cities_saved":  0,
                    "total_nations": stats["nations"],
                    "total_cities":  stats["cities"],
                }

        logger.info(f"Syncing Nights Watch nations (alliance {ALLIANCE_ID})...")

        # Clean up any skeleton rows from previous patch-only subscription events
        await db.purge_skeleton_rows()

        nations = await _fetch_alliance_nations(query)

        if not nations:
            logger.warning("sync_nations: no nations returned from API")
            return {"nations_saved": 0, "cities_saved": 0, "total_nations": 0, "total_cities": 0}

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        nations_saved = 0
        cities_saved  = 0

        # Extract and save tax brackets from the first nation's alliance data
        brackets_saved = 0
        for nation in nations:
            alliance_data = nation.get("alliance") or {}
            if isinstance(alliance_data, dict):
                tax_brackets = alliance_data.get("tax_brackets") or []
                if tax_brackets:
                    brackets_saved = await db.save_tax_brackets(ALLIANCE_ID, tax_brackets)
                    logger.info(f"sync_nations: saved {brackets_saved} tax brackets for alliance {ALLIANCE_ID}")
                    break

        # Track which nation IDs are currently in the alliance
        current_ids = set()
        for nation in nations:
            nation["snapshot_at"] = now
            if await db.save_nation(nation):
                nations_saved += 1
            cities = nation.get("cities") or []
            if cities:
                cities_saved += await db.save_cities(int(nation["id"]), cities)
            current_ids.add(int(nation["id"]))

        # Remove nations that have left the alliance since last sync
        removed = await db.remove_departed_nations(current_ids)

        stats = await db.get_stats()
        logger.info(
            f"sync_nations complete: saved {nations_saved} nations, "
            f"{cities_saved} cities, removed {removed} departed. DB totals: {stats}"
        )
        return {
            "nations_saved": nations_saved,
            "cities_saved":  cities_saved,
            "total_nations": stats["nations"],
            "total_cities":  stats["cities"],
        }

    except Exception as e:
        logger.error(f"sync_nations error: {e}", exc_info=True)
        return {"nations_saved": 0, "cities_saved": 0, "total_nations": 0, "total_cities": 0}


# ── Subscription ──────────────────────────────────────────────────────────────

async def start_nations_subscription():
    """Subscriptions are now handled by PnWHarvester. This is a no-op kept for CLI compatibility."""
    logger.info("start_nations_subscription: subscriptions are managed by PnWHarvester — nothing to do")


# ── CLI entry point (mirrors wars_manager) ────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NW Nations Manager")
    sub = parser.add_subparsers(dest="cmd")
    sync_p = sub.add_parser("sync", help="Full sync of all member nations")
    sync_p.add_argument("--force", action="store_true", help="Wipe and repopulate the DB from scratch")
    sub.add_parser("subscribe", help="Start live subscription")
    args = parser.parse_args()

    if args.cmd == "sync":
        asyncio.run(sync_nations(force=args.force))
    elif args.cmd == "subscribe":
        asyncio.run(start_nations_subscription())
    else:
        parser.print_help()
