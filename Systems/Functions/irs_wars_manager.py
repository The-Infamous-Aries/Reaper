#!/usr/bin/env python3

import asyncio
import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional
import json

# Allow running directly as a script from the repo root:
#   python Systems/Functions/irs_wars_manager.py <cmd>
# or as a module:
#   python -m Systems.Functions.irs_wars_manager <cmd>
_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from Systems.Functions.irs_wars_db import IRSWarsDB
from Systems.PnW.Util.query import create_v3_query_instance
from Systems.Functions.config import PANDW_API_V3_KEY

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
from Systems.Functions.db_paths import IRS_WARS_DB
DATABASE_DIR  = IRS_WARS_DB.parent
DATABASE_FILE = IRS_WARS_DB
CACHE_WARS_DIR = Path("c:/Users/codyr/DiscordBots/Reaper/Systems/.cache/wars")
ALLIANCE_ID = 14225  # Nights Watch alliance ID


def _chunked(values: list[int], size: int) -> list[list[int]]:
    return [values[i:i + size] for i in range(0, len(values), size)]


def _parse_war_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.fromisoformat(str(value).replace(" ", "T"))
        except ValueError:
            return None


def _load_cached_watch_wars(start_date: datetime, end_date: datetime) -> list[dict]:
    if not CACHE_WARS_DIR.exists():
        return []

    cached_wars: dict[int, dict] = {}
    for path in CACHE_WARS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        if not isinstance(data, list):
            continue

        for war in data:
            if not isinstance(war, dict):
                continue
            if str(war.get("att_alliance_id")) != str(ALLIANCE_ID) and str(war.get("def_alliance_id")) != str(ALLIANCE_ID):
                continue

            war_date = _parse_war_datetime(war.get("date"))
            if not war_date or war_date < start_date or war_date > end_date:
                continue

            war_id = war.get("id")
            if war_id is None:
                continue

            try:
                cached_wars[int(war_id)] = war
            except (TypeError, ValueError):
                continue

    return list(cached_wars.values())


async def _backfill_war_fields_from_cached_wars(
    db: IRSWarsDB,
    start_date: datetime,
    end_date: datetime,
) -> int:
    """Backfill war-level fields from cached war payloads into the local DB."""
    cached_wars = _load_cached_watch_wars(start_date, end_date)
    updated_wars = 0

    for war in cached_wars:
        if any(
            war.get(field) is not None
            for field in (
                "att_infra_destroyed_value",
                "def_infra_destroyed_value",
                "att_infra_destroyed",
                "def_infra_destroyed",
            )
        ):
            if await db.save_war(war):
                updated_wars += 1

    return updated_wars


async def _backfill_attack_fields_from_cached_wars(
    db: IRSWarsDB,
    start_date: datetime,
    end_date: datetime,
) -> int:
    """Backfill attack-level fields from cached war payloads into the local DB."""
    cached_wars = _load_cached_watch_wars(start_date, end_date)
    updated_attacks = 0

    for war in cached_wars:
        for attack in war.get("attacks", []) or []:
            if not any(
                attack.get(field) is not None
                for field in (
                    "infra_destroyed", "infra_destroyed_value",
                    "att_missiles_lost", "def_missiles_lost", "att_nukes_lost", "def_nukes_lost",
                    "money_looted", "coal_looted", "oil_looted", "uranium_looted", "iron_looted",
                    "bauxite_looted", "lead_looted", "gasoline_looted", "munitions_looted",
                    "steel_looted", "aluminum_looted", "food_looted",
                )
            ):
                continue
            if await db.save_war_attack(attack):
                updated_attacks += 1

    return updated_attacks

def ensure_database_directory():
    """Ensure the database directory exists."""
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)

async def init_database():
    """Initialize the database."""
    try:
        ensure_database_directory()
        db = IRSWarsDB(str(DATABASE_FILE))
        logger.info(f"Database initialized successfully at {DATABASE_FILE}")
        
        # Get stats to verify it's working
        stats = await db.get_database_stats()
        logger.info(f"Database stats: {stats}")
        
        return True
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        return False

async def _query_wars_from_api(
    query_instance,
    start_date: datetime,
    end_date: datetime,
) -> dict[int, dict]:
    """
    Query PnW GraphQL API for all NW wars with attacks inline.
    150 wars per page to keep payload manageable while still getting attacks.
    """
    war_fields = (
        "id date end_date reason war_type ground_control air_superiority naval_blockade "
        "winner_id turns_left att_id def_id att_alliance_id att_alliance_position "
        "def_alliance_id def_alliance_position att_points def_points att_peace def_peace "
        "att_resistance def_resistance att_fortify def_fortify att_gas_used def_gas_used "
        "att_mun_used def_mun_used att_infra_destroyed def_infra_destroyed "
        "att_infra_destroyed_value def_infra_destroyed_value "
        "att_soldiers_lost def_soldiers_lost att_tanks_lost def_tanks_lost "
        "att_aircraft_lost def_aircraft_lost att_ships_lost def_ships_lost "
        "att_missiles_used def_missiles_used att_nukes_used def_nukes_used "
        "attacker { id nation_name leader_name alliance { name } } defender { id nation_name leader_name alliance { name } }"
    )
    attack_fields = (
        "id date att_id def_id type war_id "
        "city_id success victor attcas1 defcas1 attcas2 defcas2 "
        "city_infra_before infra_destroyed infra_destroyed_value "
        "money_stolen money_destroyed military_salvage_aluminum military_salvage_steel "
        "att_missiles_lost def_missiles_lost att_nukes_lost def_nukes_lost "
        "improvements_destroyed resistance_lost loot_info "
        "money_looted coal_looted oil_looted uranium_looted iron_looted "
        "bauxite_looted lead_looted gasoline_looted munitions_looted "
        "steel_looted aluminum_looted food_looted"
    )

    after_str = start_date.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    before_str = end_date.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    unique_wars: dict[int, dict] = {}
    page = 1
    page_size = 50  # smaller pages = smaller payloads = fewer timeouts
    logger.info(f"Querying PnW GraphQL API for alliance {ALLIANCE_ID} wars ({after_str} → {before_str})...")

    while True:
        query = f"""
        query {{
          wars(
            alliance_id: [{ALLIANCE_ID}],
            active: false,
            after: "{after_str}",
            before: "{before_str}",
            page: {page},
            first: {page_size}
          ) {{
            paginatorInfo {{ hasMorePages currentPage lastPage total }}
            data {{
              {war_fields}
              attacks {{ {attack_fields} }}
            }}
          }}
        }}
        """
        page_retries = 0
        max_page_retries = 3
        wars_data = None
        paginator = {}
        while page_retries < max_page_retries:
            try:
                raw = await query_instance._make_graphql_request(query)
                wars_page = ((raw or {}).get("wars") or {})
                wars_data = wars_page.get("data") or []
                paginator = wars_page.get("paginatorInfo") or {}
                break
            except Exception as e:
                page_retries += 1
                logger.error(f"Page {page} failed (attempt {page_retries}/{max_page_retries}): {e}")
                if page_retries >= max_page_retries:
                    logger.error(f"Giving up on page {page} after {max_page_retries} attempts.")
                    break
                await asyncio.sleep(2 ** page_retries)

        if wars_data is None:
            logger.error(f"Aborting — page {page} failed after all retries. Partial data returned.")
            break

        if not wars_data:
            logger.info(f"No wars on page {page}, stopping.")
            break

        for war in wars_data:
            war_id = war.get("id")
            if war_id is not None:
                unique_wars[int(war_id)] = war

        total = paginator.get("total", "?")
        last_page = paginator.get("lastPage", "?")
        attack_count = sum(len(w.get("attacks") or []) for w in wars_data)
        logger.info(
            f"Page {page}/{last_page} — {len(wars_data)} wars, {attack_count} attacks. "
            f"Running total: {len(unique_wars)} wars (API total: {total})"
        )

        if not paginator.get("hasMorePages"):
            break

        page += 1
        await asyncio.sleep(0.5)

    return unique_wars


async def sync_missing(lookback_days: int = 1):
    """
    Sync only the wars/attacks we don't already have.

    Finds the latest war date in the DB and syncs from there to now.
    Falls back to the last `lookback_days` days if the DB is empty.

    Already-complete wars (end_date set) in the sync window are skipped so
    we never re-write settled data and can't accidentally corrupt it.
    """
    try:
        ensure_database_directory()
        db = IRSWarsDB(str(DATABASE_FILE))

        bounds = await db.get_alliance_war_date_bounds(ALLIANCE_ID)
        now = datetime.now(timezone.utc)

        if bounds and bounds.get("max_date"):
            # Start from the latest date we have (inclusive, so we catch any
            # wars that were still in-progress when we last synced)
            latest = datetime.fromisoformat(bounds["max_date"]).replace(tzinfo=timezone.utc)
            # Step back 1 hour to catch any wars that were mid-save last time
            since = latest - timedelta(hours=1)
            logger.info(f"DB latest war date: {bounds['max_date']} — syncing from {since.strftime('%Y-%m-%d %H:%M')} UTC to now")
        else:
            since = now - timedelta(days=lookback_days)
            logger.info(f"DB is empty — syncing last {lookback_days} day(s)")

        # Fetch from API
        query_instance = create_v3_query_instance(api_key=PANDW_API_V3_KEY, logger=logger)
        unique_wars = await _query_wars_from_api(query_instance, since, now)

        if not unique_wars:
            logger.info("sync_missing: no wars returned from API for the window.")
            return True

        # Skip wars that are already fully settled in the DB to avoid re-writing
        # completed data (the main source of accidental corruption).
        completed_ids = await db.get_completed_war_ids_in_range(ALLIANCE_ID, since)
        skipped = 0
        wars_synced = 0
        attacks_synced = 0

        for war in sorted(unique_wars.values(), key=lambda w: w.get("date") or ""):
            war_id = war.get("id")

            # Only save wars that actually involve NW
            if (str(war.get("att_alliance_id")) != str(ALLIANCE_ID)
                    and str(war.get("def_alliance_id")) != str(ALLIANCE_ID)):
                skipped += 1
                logger.debug(
                    f"sync_missing: skipping non-NW war {war_id} "
                    f"(att_alliance={war.get('att_alliance_id')}, "
                    f"def_alliance={war.get('def_alliance_id')})"
                )
                continue

            if war_id is not None and int(war_id) in completed_ids:
                skipped += 1
                logger.debug(f"sync_missing: skipping already-complete war {war_id}")
                continue

            if await db.save_war(war):
                wars_synced += 1

            for attack in war.get("attacks") or []:
                if attack.get("attacker_id") is None and attack.get("att_id") is not None:
                    attack["attacker_id"] = attack["att_id"]
                if attack.get("defender_id") is None and attack.get("def_id") is not None:
                    attack["defender_id"] = attack["def_id"]
                if await db.save_war_attack(attack):
                    attacks_synced += 1

        logger.info(
            f"sync_missing complete: {wars_synced} wars and {attacks_synced} attacks saved "
            f"({skipped} non-NW/already-complete wars skipped)."
        )
        return True
    except Exception as e:
        logger.error(f"Error in sync_missing: {e}", exc_info=True)
        return False


async def sync_wars(days: int = 30, since: Optional[datetime] = None, until: Optional[datetime] = None):
    """
    Pull IRS wars directly from the PnW GraphQL API and save them to the DB.

    The PnW wars endpoint does NOT support date filtering — we fetch all pages
    for the alliance and filter by date in Python.

    Window resolution:
      --since / --until  → explicit date range
      --days             → last N days from now (default 30)
    """
    try:
        ensure_database_directory()
        db = IRSWarsDB(str(DATABASE_FILE))

        now = datetime.now(timezone.utc)
        start_date = since if since else (now - timedelta(days=days))
        end_date = until if until else now

        logger.info(
            f"Syncing NW wars from {start_date.strftime('%Y-%m-%d')} "
            f"to {end_date.strftime('%Y-%m-%d')} via GraphQL API"
        )

        query_instance = create_v3_query_instance(api_key=PANDW_API_V3_KEY, logger=logger)

        unique_wars = await _query_wars_from_api(query_instance, start_date, end_date)

        if not unique_wars:
            logger.error("No wars returned from the API for the requested window.")
            return False

        wars_synced = 0
        attacks_synced = 0
        wars_skipped = 0

        for war in sorted(unique_wars.values(), key=lambda w: w.get("date") or ""):
            # Only save wars that actually involve NW
            if (str(war.get("att_alliance_id")) != str(ALLIANCE_ID)
                    and str(war.get("def_alliance_id")) != str(ALLIANCE_ID)):
                wars_skipped += 1
                logger.debug(
                    f"sync_wars: skipping non-NW war {war.get('id')} "
                    f"(att_alliance={war.get('att_alliance_id')}, "
                    f"def_alliance={war.get('def_alliance_id')})"
                )
                continue

            if await db.save_war(war):
                wars_synced += 1
            else:
                logger.warning(f"Failed to save war {war.get('id')}")

            for attack in war.get("attacks") or []:
                # Map att_id/def_id → attacker_id/defender_id for DB compatibility
                if attack.get("attacker_id") is None and attack.get("att_id") is not None:
                    attack["attacker_id"] = attack["att_id"]
                if attack.get("defender_id") is None and attack.get("def_id") is not None:
                    attack["defender_id"] = attack["def_id"]
                if await db.save_war_attack(attack):
                    attacks_synced += 1
                else:
                    logger.warning(f"Failed to save attack {attack.get('id')} for war {war.get('id')}")

        logger.info(
            f"Sync complete: {wars_synced} wars and {attacks_synced} attacks saved to DB "
            f"({wars_skipped} non-NW wars skipped)."
        )
        return True
    except Exception as e:
        logger.error(f"Error syncing wars: {e}", exc_info=True)
        return False

async def start_subscription():
    """Subscriptions are now handled by PnWHarvester. This is a no-op kept for CLI compatibility."""
    logger.info("start_subscription: subscriptions are managed by PnWHarvester — nothing to do")

async def process_subscription_attacks():
    """Process subscription war attacks - now integrated directly into main tables."""
    try:
        ensure_database_directory()
        db = IRSWarsDB(str(DATABASE_FILE))
        
        logger.info("Subscription attacks are now processed directly into main war_attacks table")
        logger.info("No separate processing needed - all subscription data flows directly to main tables")
        
        # Show current stats
        stats = await db.get_database_stats()
        logger.info(f"Current database stats: {stats['wars']} wars, {stats['war_attacks']} total attacks")
        
        return True
    except Exception as e:
        logger.error(f"Error processing subscription attacks: {e}")
        return False

async def backfill_attack_fields(days: int = 30):
    """Backfill war-level infra and attack-level infra, loot, and missile/nuke loss fields from cached NW wars."""
    try:
        ensure_database_directory()
        db = IRSWarsDB(str(DATABASE_FILE))
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        end_date = datetime.now(timezone.utc)
        updated_wars = await _backfill_war_fields_from_cached_wars(db, start_date, end_date)
        updated = await _backfill_attack_fields_from_cached_wars(db, start_date, end_date)
        logger.info(f"Backfilled war-level infra fields for {updated_wars} cached wars")
        logger.info(f"Backfilled attack-level infra, loot, and missile/nuke fields for {updated} cached attacks")
        return True
    except Exception as e:
        logger.error(f"Error backfilling attack fields: {e}", exc_info=True)
        return False

async def backfill_24h():
    """
    Recover all missing wars and attacks from the last 24 hours.

    Fetches every IRS war (and its inline attacks) from the PnW GraphQL
    API for the window [now-24h, now], then upserts each record into the DB.
    Already-present rows are updated (never overwritten with NULL), so this is
    safe to run while the subscription is live.

    Reports new vs already-present counts so you can see exactly what was missing.
    """
    try:
        ensure_database_directory()
        db = IRSWarsDB(str(DATABASE_FILE))
        query_instance = create_v3_query_instance(api_key=PANDW_API_V3_KEY, logger=logger)

        now = datetime.now(timezone.utc)
        since = now - timedelta(hours=24)

        logger.info(
            f"backfill_24h: fetching all NW wars from "
            f"{since.strftime('%Y-%m-%d %H:%M')} UTC to {now.strftime('%Y-%m-%d %H:%M')} UTC"
        )

        unique_wars = await _query_wars_from_api(query_instance, since, now)

        if not unique_wars:
            logger.warning("backfill_24h: API returned no wars for the last 24 hours.")
            return False

        wars_new = 0
        wars_updated = 0
        attacks_new = 0
        attacks_updated = 0

        for war in sorted(unique_wars.values(), key=lambda w: w.get("date") or ""):
            war_id = war.get("id")

            existing_war = await db.get_war(int(war_id)) if war_id else None
            await db.save_war(war)
            if existing_war:
                wars_updated += 1
            else:
                wars_new += 1
                logger.info(
                    f"backfill_24h: new war {war_id} "
                    f"(att_alliance={war.get('att_alliance_id')}, "
                    f"def_alliance={war.get('def_alliance_id')}, "
                    f"date={war.get('date')})"
                )

            # Fetch existing attack IDs once per war (avoids O(n²) queries)
            existing_attack_ids: set = set()
            if war_id:
                existing_attacks_in_db = await db.get_war_attacks(int(war_id))
                existing_attack_ids = {a.get("id") for a in existing_attacks_in_db}

            for attack in war.get("attacks") or []:
                # Normalise att_id/def_id → attacker_id/defender_id for DB
                if attack.get("attacker_id") is None and attack.get("att_id") is not None:
                    attack["attacker_id"] = attack["att_id"]
                if attack.get("defender_id") is None and attack.get("def_id") is not None:
                    attack["defender_id"] = attack["def_id"]

                attack_id = attack.get("id")
                await db.save_war_attack(attack)
                if attack_id in existing_attack_ids:
                    attacks_updated += 1
                else:
                    attacks_new += 1
                    logger.debug(
                        f"backfill_24h: new attack {attack_id} for war {war_id} "
                        f"(type={attack.get('type')})"
                    )

        logger.info(
            f"backfill_24h complete: "
            f"{wars_new} new wars, {wars_updated} wars updated, "
            f"{attacks_new} new attacks, {attacks_updated} attacks updated."
        )
        if wars_new == 0 and attacks_new == 0:
            logger.info("backfill_24h: DB was already up to date — nothing missing.")
        return True

    except Exception as e:
        logger.error(f"backfill_24h failed: {e}", exc_info=True)
        return False


async def cleanup_database(days: int = 90):
    """Clean up old subscription data."""
    try:
        ensure_database_directory()
        db = IRSWarsDB(str(DATABASE_FILE))
        
        logger.info(f"Cleaning up subscription data older than {days} days")
        
        # For now, we'll just log that this would clean up old data
        logger.info("Cleanup functionality would be implemented here")
        
        return True
    except Exception as e:
        logger.error(f"Error cleaning up database: {e}")
        return False

async def show_stats():
    """Show database statistics."""
    try:
        ensure_database_directory()
        db = IRSWarsDB(str(DATABASE_FILE))
        
        stats = await db.get_database_stats()
        
        print("\n=== NW Wars Database Statistics ===")
        print(f"Total Wars: {stats['wars']}")
        print(f"Total War Attacks: {stats['war_attacks']}")
        print(f"Total Subscription Attacks: {stats['subscription_attacks']}")
        print(f"Unprocessed Subscription Attacks: {stats['unprocessed_attacks']}")
        print("=====================================\n")
        
        return True
    except Exception as e:
        logger.error(f"Error showing stats: {e}")
        return False

async def clean_war(war_id: int) -> bool:
    """
    Delete a single war and all its attacks from the main DB by war ID.

    Safe to run while the bot is live — the subscription will re-add the war
    if it's still active and new attacks come in.  Use this to remove a
    specific war that has bad/duplicate data so you can let it re-sync cleanly.
    """
    try:
        ensure_database_directory()
        db = IRSWarsDB(str(DATABASE_FILE))

        # Confirm the war exists first
        existing = await db.get_war(war_id)
        if not existing:
            logger.warning(f"clean_war: war {war_id} not found in DB — nothing to delete.")
            return False

        result = await db.delete_war(war_id)
        logger.info(
            f"clean_war: deleted war {war_id} — "
            f"{result['wars_deleted']} war row, "
            f"{result['attacks_deleted']} attack rows, "
            f"{result['subscription_attacks_deleted']} subscription attack rows removed."
        )
        return result['wars_deleted'] > 0
    except Exception as e:
        logger.error(f"clean_war failed for war {war_id}: {e}", exc_info=True)
        return False


async def sync_wars_to_db(
    target_db_path: str,
    days: int = 30,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> bool:
    """
    Sync the last N days of NW wars to a *separate* target DB.

    This is the safe way to inspect or clean a corrupted main DB:
      1. Run this to populate a clean copy.
      2. Inspect / compare the clean copy against the main DB.
      3. Use clean-war to remove bad rows from the main DB, then re-sync them.

    The target DB is created fresh (or reused if it already exists) at
    `target_db_path`.  The main DB is never touched.
    """
    try:
        # Ensure target directory exists
        target_path = Path(target_db_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        db = IRSWarsDB(str(target_path))

        now = datetime.now(timezone.utc)
        start_date = since if since else (now - timedelta(days=days))
        end_date = until if until else now

        logger.info(
            f"sync_wars_to_db: syncing {start_date.strftime('%Y-%m-%d')} → "
            f"{end_date.strftime('%Y-%m-%d')} into {target_path}"
        )

        query_instance = create_v3_query_instance(api_key=PANDW_API_V3_KEY, logger=logger)
        unique_wars = await _query_wars_from_api(query_instance, start_date, end_date)

        if not unique_wars:
            logger.error("sync_wars_to_db: no wars returned from API.")
            return False

        wars_synced = 0
        attacks_synced = 0

        for war in sorted(unique_wars.values(), key=lambda w: w.get("date") or ""):
            if await db.save_war(war):
                wars_synced += 1

            for attack in war.get("attacks") or []:
                if attack.get("attacker_id") is None and attack.get("att_id") is not None:
                    attack["attacker_id"] = attack["att_id"]
                if attack.get("defender_id") is None and attack.get("def_id") is not None:
                    attack["defender_id"] = attack["def_id"]
                if await db.save_war_attack(attack):
                    attacks_synced += 1

        logger.info(
            f"sync_wars_to_db complete: {wars_synced} wars and {attacks_synced} attacks "
            f"written to {target_path}"
        )
        return True
    except Exception as e:
        logger.error(f"sync_wars_to_db failed: {e}", exc_info=True)
        return False


def main():
    parser = argparse.ArgumentParser(description="NW Wars Database Manager")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Init command
    init_parser = subparsers.add_parser('init', help='Initialize the database')
    
    # Sync-missing command
    sync_missing_parser = subparsers.add_parser('sync-missing', help='Sync only wars/attacks not yet in the DB (gap from latest DB date to now)')
    sync_missing_parser.add_argument('--lookback-days', type=int, default=1, help='Days to fall back if DB is empty (default: 1)')

    # Sync command
    sync_parser = subparsers.add_parser('sync', help='Sync wars data from API')
    sync_parser.add_argument('--days', type=int, default=30, help='Number of days back from now (or --until) to sync (default: 30)')
    sync_parser.add_argument('--since', type=str, default=None, help='Start date YYYY-MM-DD (overrides --days)')
    sync_parser.add_argument('--until', type=str, default=None, help='End date YYYY-MM-DD (default: today)')
    
    # Subscribe command
    sub_parser = subparsers.add_parser('subscribe', help='Start WebSocket subscription')
    
    # Process command
    process_parser = subparsers.add_parser('process', help='Process subscription attacks')

    # Backfill-24h command
    subparsers.add_parser('backfill-24h', help='Recover all missing wars and attacks from the last 24 hours')

    # Backfill command
    backfill_parser = subparsers.add_parser('backfill-attacks', help='Backfill attack-level loss fields from cached wars')
    backfill_parser.add_argument('--days', type=int, default=30, help='Number of days to backfill from cache (default: 30)')

    # Clean-war command — remove a single war (and its attacks) by ID
    clean_war_parser = subparsers.add_parser('clean-war', help='Delete a war and all its attacks from the DB by war ID')
    clean_war_parser.add_argument('war_id', type=int, help='War ID to delete')

    # Sync-to command — sync to a separate DB for inspection/cleaning
    sync_to_parser = subparsers.add_parser('sync-to', help='Sync wars to a separate DB file (safe copy for inspection/cleaning)')
    sync_to_parser.add_argument('target_db', type=str, help='Path to the target DB file (created if it does not exist)')
    sync_to_parser.add_argument('--days', type=int, default=30, help='Number of days back to sync (default: 30)')
    sync_to_parser.add_argument('--since', type=str, default=None, help='Start date YYYY-MM-DD (overrides --days)')
    sync_to_parser.add_argument('--until', type=str, default=None, help='End date YYYY-MM-DD (default: today)')

    # Cleanup command
    cleanup_parser = subparsers.add_parser('cleanup', help='Clean up old data')
    cleanup_parser.add_argument('--days', type=int, default=90, help='Keep data newer than this many days (default: 90)')
    
    # Stats command
    stats_parser = subparsers.add_parser('stats', help='Show database statistics')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Run the appropriate command
    try:
        if args.command == 'init':
            success = asyncio.run(init_database())
            return 0 if success else 1
        
        elif args.command == 'sync-missing':
            success = asyncio.run(sync_missing(args.lookback_days))
            return 0 if success else 1

        elif args.command == 'sync':
            since_dt = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc) if args.since else None
            until_dt = datetime.fromisoformat(args.until).replace(tzinfo=timezone.utc) if args.until else None
            success = asyncio.run(sync_wars(args.days, since=since_dt, until=until_dt))
            return 0 if success else 1
        
        elif args.command == 'subscribe':
            success = asyncio.run(start_subscription())
            return 0 if success else 1
        
        elif args.command == 'process':
            success = asyncio.run(process_subscription_attacks())
            return 0 if success else 1

        elif args.command == 'backfill-24h':
            success = asyncio.run(backfill_24h())
            return 0 if success else 1

        elif args.command == 'backfill-attacks':
            success = asyncio.run(backfill_attack_fields(args.days))
            return 0 if success else 1

        elif args.command == 'clean-war':
            success = asyncio.run(clean_war(args.war_id))
            return 0 if success else 1

        elif args.command == 'sync-to':
            since_dt = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc) if args.since else None
            until_dt = datetime.fromisoformat(args.until).replace(tzinfo=timezone.utc) if args.until else None
            success = asyncio.run(sync_wars_to_db(args.target_db, days=args.days, since=since_dt, until=until_dt))
            return 0 if success else 1

        elif args.command == 'cleanup':
            success = asyncio.run(cleanup_database(args.days))
            return 0 if success else 1
        
        elif args.command == 'stats':
            success = asyncio.run(show_stats())
            return 0 if success else 1
        
        else:
            parser.print_help()
            return 1
            
    except KeyboardInterrupt:
        logger.info("Operation interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
