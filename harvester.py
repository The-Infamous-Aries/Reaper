"""
PnWHarvester — standalone asyncio service (no Discord).

Starts three WebSocket subscriptions and keeps them running forever:
  1. GlobalNationsSubscription — all nations → GlobalNations.db; NW → IRSNations.db
  2. GlobalWarsSubscription    — NW wars → IRSWars.db; win attacks → holdings.db
  3. BankrecsSubscription      — all bank records → bankrecs.db + holdings.db

One-time population of GlobalNations.db and bankrecs.db is done separately via:
    python scripts/populate_dbs.py --all

NW wars backfill (IRSWars.db) is still available here:
    python harvester.py --sync-nw-wars [--nw-wars-days N]
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

# ── Path setup ────────────────────────────────────────────────────────────────
# Harvester now lives in DiscordBots/Reaper/ (root directory)
# Reaper's Systems/ is in the same directory
_harvester_dir = Path(__file__).resolve().parent
_reaper_root   = _harvester_dir  # Now the same directory
if str(_reaper_root) not in sys.path:
    sys.path.insert(0, str(_reaper_root))

# Add PnWHarvester to path for imports
_pnw_harvester_dir = _reaper_root / "PnWHarvester"
if str(_pnw_harvester_dir) not in sys.path:
    sys.path.insert(0, str(_pnw_harvester_dir))

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(_harvester_dir / "harvester.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("harvester")

# ── DB paths ──────────────────────────────────────────────────────────────────
DB_DIR = _reaper_root / "Databases"
DB_DIR.mkdir(parents=True, exist_ok=True)

EP_NATIONS_DB    = str(DB_DIR / "PnW" / "GlobalNations.db")  # merged into GlobalNations.db
EP_WARS_DB       = str(DB_DIR / "PnW" / "IRSWars.db")
GLOBAL_NATIONS_DB = str(DB_DIR / "PnW" / "GlobalNations.db")
BANKRECS_DB      = str(DB_DIR / "PnW" / "bankrecs.db")
HOLDINGS_DB      = str(DB_DIR / "PnW" / "holdings.db")

NW_ALLIANCE_ID  = 14225
IRS_ALLIANCE_ID = NW_ALLIANCE_ID   # backward-compat alias
EP_ALLIANCE_ID  = NW_ALLIANCE_ID   # backward-compat alias

# ── GraphQL field sets ────────────────────────────────────────────────────────
_WAR_FIELDS = (
    "id date end_date reason war_type ground_control air_superiority naval_blockade "
    "winner_id turns_left att_id def_id att_alliance_id att_alliance_position "
    "def_alliance_id def_alliance_position att_points def_points att_peace def_peace "
    "att_resistance def_resistance att_fortify def_fortify att_gas_used def_gas_used "
    "att_mun_used def_mun_used att_infra_destroyed def_infra_destroyed "
    "att_infra_destroyed_value def_infra_destroyed_value "
    "att_soldiers_lost def_soldiers_lost att_tanks_lost def_tanks_lost "
    "att_aircraft_lost def_aircraft_lost att_ships_lost def_ships_lost "
    "att_missiles_used def_missiles_used att_nukes_used def_nukes_used "
    "attacker { id nation_name leader_name war_policy advanced_pirate_economy alliance { name } } "
    "defender { id nation_name leader_name war_policy alliance { name } }"
)
_ATTACK_FIELDS = (
    "id date att_id def_id type war_id "
    "city_id success victor attcas1 defcas1 attcas2 defcas2 "
    "city_infra_before infra_destroyed infra_destroyed_value "
    "money_stolen money_destroyed military_salvage_aluminum military_salvage_steel "
    "att_aircraft_lost def_aircraft_lost att_ships_lost def_ships_lost "
    "att_missiles_lost def_missiles_lost att_nukes_lost def_nukes_lost "
    "att_mun_used def_mun_used att_gas_used def_gas_used "
    "improvements_destroyed resistance_lost loot_info "
    "money_looted coal_looted oil_looted uranium_looted iron_looted "
    "bauxite_looted lead_looted gasoline_looted munitions_looted "
    "steel_looted aluminum_looted food_looted"
)
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


async def _sync_nw_wars(
    query_instance,
    nw_wars_db,
    since: "datetime",
    until: "datetime",
) -> dict:
    """
    Fetch Nights Watch wars for [since, until] and upsert into IRSWars.db.
    Returns {"wars_saved": int, "attacks_saved": int}.
    All saves are upserts — existing rows are updated only where the incoming
    value is non-null, so no data is ever overwritten with NULL.
    """
    after_str  = since.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    before_str = until.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"NW wars sync: {after_str} → {before_str}")

    unique_wars: dict[int, dict] = {}

    async def _fetch_pages(active_filter: bool | None):
        """Paginate one pass (ended or active) and merge into unique_wars."""
        page = 1
        page_size = 50
        active_clause = "" if active_filter is None else f"active: {'true' if active_filter else 'false'},"
        label = "active" if active_filter is True else ("ended" if active_filter is False else "all")
        while True:
            query = f"""
            query {{
              wars(
                alliance_id: [{EP_ALLIANCE_ID}],
                {active_clause}
                after: "{after_str}",
                before: "{before_str}",
                page: {page},
                first: {page_size}
              ) {{
                paginatorInfo {{ hasMorePages currentPage lastPage total }}
                data {{
                  {_WAR_FIELDS}
                  attacks {{ {_ATTACK_FIELDS} }}
                }}
              }}
            }}
            """
            retries = 0
            wars_data = None
            paginator = {}
            while retries < 3:
                try:
                    raw = await query_instance._make_graphql_request(query, timeout=60)
                    wars_page = (raw or {}).get("wars") or {}
                    wars_data = wars_page.get("data") or []
                    paginator = wars_page.get("paginatorInfo") or {}
                    break
                except Exception as e:
                    retries += 1
                    logger.error(f"NW wars [{label}] page {page} attempt {retries}/3: {e}")
                    if retries >= 3:
                        break
                    await asyncio.sleep(2 ** retries)

            if wars_data is None:
                logger.error(f"NW wars sync [{label}]: aborting at page {page} after retries")
                break
            if not wars_data:
                break

            for war in wars_data:
                wid = war.get("id")
                if wid is not None:
                    unique_wars[int(wid)] = war

            logger.info(
                f"NW wars [{label}] page {page}/{paginator.get('lastPage', '?')} — "
                f"{len(wars_data)} wars, {len(unique_wars)} unique so far"
            )
            if not paginator.get("hasMorePages"):
                break
            page += 1
            await asyncio.sleep(0.5)

    # Fetch ended wars first, then active — active pass wins on conflict (fresher state)
    await _fetch_pages(False)
    await _fetch_pages(True)

    wars_saved = 0
    attacks_saved = 0
    for war in sorted(unique_wars.values(), key=lambda w: w.get("date") or ""):
        # Only NW wars — API filter should guarantee this but double-check
        if (str(war.get("att_alliance_id")) != str(NW_ALLIANCE_ID)
                and str(war.get("def_alliance_id")) != str(NW_ALLIANCE_ID)):
            continue
        if await nw_wars_db.save_war(war):
            wars_saved += 1
        for attack in war.get("attacks") or []:
            if attack.get("attacker_id") is None and attack.get("att_id") is not None:
                attack["attacker_id"] = attack["att_id"]
            if attack.get("defender_id") is None and attack.get("def_id") is not None:
                attack["defender_id"] = attack["def_id"]
            if await nw_wars_db.save_war_attack(attack):
                attacks_saved += 1

    logger.info(f"NW wars sync complete: {wars_saved} wars, {attacks_saved} attacks upserted")
    return {"wars_saved": wars_saved, "attacks_saved": attacks_saved}


async def _sync_global_nations(query_instance, global_nations_db) -> dict:
    """
    Fetch ALL nations in the game (paginated) and upsert into GlobalNations.db.
    Excludes baseball_team (causes PnW API internal server error) and wars/bankrecs
    (too large for a full-game sync — those come from subscriptions).
    Returns {"nations_saved": int}.
    """
    _GLOBAL_NATION_FIELDS = (
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
        "alliance { id name } "
        "cities { id name date infrastructure land powered "
        "coal_power oil_power nuclear_power wind_power "
        "coal_mine oil_well uranium_mine lead_mine iron_mine bauxite_mine "
        "oil_refinery aluminum_refinery steel_mill munitions_factory factory farm "
        "police_station hospital recycling_center subway "
        "supermarket bank shopping_mall stadium barracks hangar drydock }"
    )

    logger.info("Global nations sync: fetching all nations (no wars/bankrecs)...")
    nations_saved = 0
    page = 1
    page_size = 100

    while True:
        query = f"""
        query {{
          nations(first: {page_size}, page: {page}, vmode: false) {{
            paginatorInfo {{ hasMorePages currentPage lastPage total }}
            data {{ {_GLOBAL_NATION_FIELDS} }}
          }}
        }}
        """
        retries = 0
        nations_data = None
        paginator = {}
        while retries < 3:
            try:
                raw = await query_instance._make_graphql_request(query, timeout=90)
                nations_page = (raw or {}).get("nations") or {}
                nations_data = nations_page.get("data") or []
                paginator = nations_page.get("paginatorInfo") or {}
                break
            except Exception as e:
                retries += 1
                logger.error(f"Global nations page {page} attempt {retries}/3: {e}")
                if retries >= 3:
                    break
                await asyncio.sleep(2 ** retries)

        if nations_data is None:
            logger.error(f"Global nations sync: aborting at page {page} after retries")
            break
        if not nations_data:
            break

        for nation in nations_data:
            alliance_obj = nation.get("alliance") or {}
            if isinstance(alliance_obj, dict):
                if not nation.get("alliance_id") and alliance_obj.get("id"):
                    nation["alliance_id"] = alliance_obj["id"]
                if not nation.get("alliance_name"):
                    nation["alliance_name"] = alliance_obj.get("name")

        # Use bulk upsert — writes all fields including money/resources as initial seed
        saved, _ = await global_nations_db.bulk_upsert_nations_and_cities(nations_data)
        nations_saved += saved

        logger.info(
            f"Global nations page {page}/{paginator.get('lastPage', '?')} — "
            f"{len(nations_data)} nations, total saved: {nations_saved}"
        )
        if not paginator.get("hasMorePages"):
            break
        page += 1
        await asyncio.sleep(0.3)

    logger.info(f"Global nations sync complete: {nations_saved} nations upserted")
    return {"nations_saved": nations_saved}


async def _backfill_bankrecs(query_instance, bankrecs_db, days: int = 14) -> dict:
    """
    Backfill bankrecs.db with ALL bank records from the last N days.
    Returns {"records_saved": int}.
    """
    until_dt = datetime.now(timezone.utc)
    since_dt = until_dt - timedelta(days=days)
    after_str  = since_dt.strftime("%Y-%m-%d %H:%M:%S")
    before_str = until_dt.strftime("%Y-%m-%d %H:%M:%S")

    logger.info(f"Bankrecs backfill: fetching all records {after_str} → {before_str}")

    _BANKREC_FIELDS = (
        "id date sender_id sender_type receiver_id receiver_type "
        "banker_id note tax_id "
        "money coal oil uranium iron bauxite lead "
        "gasoline munitions steel aluminum food"
    )

    records_saved = 0
    page = 1
    page_size = 100

    while True:
        query = f"""
        query {{
          bankrecs(
            after: "{after_str}",
            before: "{before_str}",
            page: {page},
            first: {page_size},
            orderBy: [{{ column: DATE, order: DESC }}]
          ) {{
            paginatorInfo {{ hasMorePages currentPage lastPage total }}
            data {{ {_BANKREC_FIELDS} }}
          }}
        }}
        """
        retries = 0
        recs_data = None
        paginator = {}
        while retries < 3:
            try:
                raw = await query_instance._make_graphql_request(query, timeout=60)
                recs_page = (raw or {}).get("bankrecs") or {}
                recs_data = recs_page.get("data") or []
                paginator = recs_page.get("paginatorInfo") or {}
                break
            except Exception as e:
                retries += 1
                logger.error(f"Bankrecs backfill page {page} attempt {retries}/3: {e}")
                if retries >= 3:
                    break
                await asyncio.sleep(2 ** retries)

        if recs_data is None:
            logger.error(f"Bankrecs backfill: aborting at page {page} after retries")
            break
        if not recs_data:
            break

        saved = await bankrecs_db.save_bankrecs_bulk(recs_data)
        records_saved += saved

        logger.info(
            f"Bankrecs backfill page {page}/{paginator.get('lastPage', '?')} — "
            f"{len(recs_data)} fetched, {saved} new, total saved: {records_saved}"
        )
        if not paginator.get("hasMorePages"):
            break
        page += 1
        await asyncio.sleep(0.5)

    logger.info(f"Bankrecs backfill complete: {records_saved} records saved")
    return {"records_saved": records_saved}


async def main(
    sync_ep_wars_backfill: bool = False,
    ep_wars_days: int = 7,
    ep_wars_since: Optional[datetime] = None,
    ep_wars_until: Optional[datetime] = None,
    skip_ep_nations_sync: bool = False,
    force_ep_nations_sync: bool = False,
):
    # ── Suppress pnwkit internal task noise ───────────────────────────────────
    # pnwkit spawns asyncio tasks for ping_pong / handle_socket_close that raise
    # various network errors when the PnW API drops the connection or DNS fails.
    # These are expected disconnects — our run_forever() wrappers handle the actual
    # restart.  Without this handler Python logs "Task exception was never retrieved"
    # for every disconnect, which is noisy and misleading.
    _PNWKIT_NOISE_TYPES = (
        "pnwkit.errors.NoReconnect",
        "aiohttp.client_exceptions.ServerDisconnectedError",
        "aiohttp.client_exceptions.ClientConnectorError",  # DNS failure during reconnect
        "aiohttp.client_exceptions.ClientOSError",
        "aiohttp.client_exceptions.ClientConnectionError",
    )
    _PNWKIT_NOISE_MSGS = (
        "getaddrinfo failed",
        "Cannot connect to host",
        "Connection reset by peer",
        "The network connection was aborted",
    )

    def _pnwkit_exception_handler(loop, context):
        exc = context.get("exception")
        if exc is not None:
            exc_type = f"{type(exc).__module__}.{type(exc).__qualname__}"
            exc_msg  = str(exc)
            if exc_type in _PNWKIT_NOISE_TYPES:
                logger.debug(f"pnwkit internal disconnect (suppressed): {exc}")
                return
            # Also suppress by message for subclasses we might not enumerate
            if any(m in exc_msg for m in _PNWKIT_NOISE_MSGS):
                logger.debug(f"pnwkit network error (suppressed): {exc}")
                return
        # Fall back to default handler for everything else
        loop.default_exception_handler(context)

    asyncio.get_event_loop().set_exception_handler(_pnwkit_exception_handler)

    # ── Imports ───────────────────────────────────────────────────────────────
    from PnWHarvester.subscriptions.nations_subscription  import GlobalNationsSubscription
    from PnWHarvester.subscriptions.wars_subscription     import GlobalWarsSubscription
    from PnWHarvester.subscriptions.bankrecs_subscription import BankrecsSubscription
    from PnWHarvester.subscriptions.turn_revenue_loop     import TurnRevenueLoop

    from Systems.Functions.irs_wars_db         import IRSWarsDB
    from Systems.Functions.irs_nations_manager import sync_nations
    from Systems.PnW.Util.query                import create_v3_query_instance

    import os
    from dotenv import load_dotenv
    load_dotenv(_reaper_root / "Systems" / "Functions" / ".env")
    api_key = os.getenv("PANDW_API_V3_KEY")
    if not api_key:
        logger.error("PANDW_API_V3_KEY not found in Systems/Functions/.env — aborting")
        return

    # ── Init DBs ──────────────────────────────────────────────────────────────
    logger.info("Initialising databases...")
    from PnWHarvester.db.global_nations_db import GlobalNationsDB
    from PnWHarvester.db.holdings_db       import HoldingsDB
    from PnWHarvester.db.bankrecs_db       import BankrecsDB

    # Single nations DB — GlobalNations.db holds ALL nations (NW and non-NW).
    # IRSNationsDB is an alias for GlobalNationsDB; no separate file is needed.
    global_nations_db = GlobalNationsDB(GLOBAL_NATIONS_DB)
    ep_wars_db        = IRSWarsDB(EP_WARS_DB)
    holdings_db       = HoldingsDB(HOLDINGS_DB)
    bankrecs_db       = BankrecsDB(BANKRECS_DB)

    query_instance = create_v3_query_instance(api_key=api_key, logger=logger)

    # ── Optional: NW nations sync on startup ──────────────────────────────────
    if not skip_ep_nations_sync:
        if force_ep_nations_sync:
            logger.info("Starting NW nations sync (FORCE)...")
            nations_result = await sync_nations(force=True)
        else:
            logger.info("Starting NW nations sync...")
            nations_result = await sync_nations(force=False)
        logger.info(f"NW nations sync: {nations_result}")
    else:
        logger.info("NW nations sync skipped")

    # ── Optional: NW wars backfill on startup ─────────────────────────────────
    if sync_ep_wars_backfill:
        if ep_wars_since and ep_wars_until:
            since_dt = ep_wars_since
            until_dt = ep_wars_until
        elif ep_wars_since:
            since_dt = ep_wars_since
            until_dt = datetime.now(timezone.utc)
        else:
            until_dt = datetime.now(timezone.utc)
            since_dt = until_dt - timedelta(days=ep_wars_days)

        logger.info("Starting NW wars backfill...")
        wars_result = await _sync_nw_wars(query_instance, ep_wars_db, since_dt, until_dt)
        logger.info(f"NW wars backfill: {wars_result}")
    else:
        logger.info("NW wars backfill skipped (pass --sync-nw-wars to enable)")

    # ── Start subscriptions ───────────────────────────────────────────────────
    query_instance = create_v3_query_instance(api_key=api_key, logger=logger)

    nations_sub = GlobalNationsSubscription(
        global_db=global_nations_db,
        api_key=api_key,
        holdings_db=holdings_db,
    )
    
    # Verify alliance data integrity on startup
    logger.info("Verifying alliance data integrity...")
    try:
        integrity_stats = await nations_sub.verify_alliance_data_integrity()
        logger.info(f"Alliance data integrity check complete: {integrity_stats}")
    except Exception as e:
        logger.error(f"Alliance data integrity check failed: {e}")
    
    wars_sub = GlobalWarsSubscription(
        global_db=None,
        nw_db=ep_wars_db,
        query_instance=query_instance,
        api_key=api_key,
        holdings_db=holdings_db,
        nw_nations_db=None,
        global_nations_db=global_nations_db,
    )
    bankrecs_sub = BankrecsSubscription(
        api_key=api_key,
        holdings_db=holdings_db,
        bankrecs_db=bankrecs_db,
    )

    turn_revenue_loop = TurnRevenueLoop(
        holdings_db=holdings_db,
        global_db=global_nations_db,
        query_instance=query_instance,
    )

    logger.info("Starting subscriptions (nations, wars, bankrecs) + turn revenue loop...")

    # ── Shutdown coordination ─────────────────────────────────────────────────
    # A single Event that any signal handler sets to request a clean shutdown.
    # All _run_* wrappers watch it so they can exit their restart loops gracefully
    # instead of being hard-cancelled mid-write.
    _shutdown = asyncio.Event()

    def _request_shutdown(signame: str):
        if not _shutdown.is_set():
            logger.info(f"Shutdown requested ({signame}) — draining in-flight writes…")
            _shutdown.set()

    # Register both SIGINT (Ctrl-C) and SIGTERM (systemd / kill) on Unix.
    import signal as _signal
    loop = asyncio.get_event_loop()
    for _sig in (getattr(_signal, "SIGINT", None), getattr(_signal, "SIGTERM", None)):
        if _sig is not None:
            try:
                loop.add_signal_handler(_sig, _request_shutdown, _sig.name)
            except (NotImplementedError, RuntimeError):
                # Windows doesn't support add_signal_handler for all signals
                pass

    async def _run_nations():
        while not _shutdown.is_set():
            try:
                await nations_sub.run_forever()
            except asyncio.CancelledError:
                break
            except Exception as e:
                if _shutdown.is_set():
                    break
                logger.error(f"Nations subscription crashed: {e} — restarting in 30s", exc_info=True)
                try:
                    await asyncio.wait_for(_shutdown.wait(), timeout=30)
                except asyncio.TimeoutError:
                    pass
        await nations_sub.stop()
        logger.info("Nations subscription shut down cleanly")

    async def _run_wars():
        while not _shutdown.is_set():
            try:
                await wars_sub.run_forever()
            except asyncio.CancelledError:
                break
            except Exception as e:
                if _shutdown.is_set():
                    break
                logger.error(f"Wars subscription crashed: {e} — restarting in 30s", exc_info=True)
                try:
                    await asyncio.wait_for(_shutdown.wait(), timeout=30)
                except asyncio.TimeoutError:
                    pass
        await wars_sub.stop()
        logger.info("Wars subscription shut down cleanly")

    async def _run_bankrecs():
        while not _shutdown.is_set():
            try:
                await bankrecs_sub.run_forever()
            except asyncio.CancelledError:
                break
            except Exception as e:
                if _shutdown.is_set():
                    break
                logger.error(f"Bankrecs subscription crashed: {e} — restarting in 30s", exc_info=True)
                try:
                    await asyncio.wait_for(_shutdown.wait(), timeout=30)
                except asyncio.TimeoutError:
                    pass
        await bankrecs_sub.stop()
        logger.info("Bankrecs subscription shut down cleanly")

    async def _run_turn_revenue():
        await turn_revenue_loop.start()
        try:
            await _shutdown.wait()
        except asyncio.CancelledError:
            pass
        finally:
            await turn_revenue_loop.stop()
            logger.info("Turn revenue loop shut down cleanly")

    async def _run_checkpoint():
        """Checkpoint all WAL files every 5 minutes to keep them small."""
        while not _shutdown.is_set():
            try:
                await asyncio.wait_for(_shutdown.wait(), timeout=300)
            except asyncio.TimeoutError:
                pass
            if _shutdown.is_set():
                break
            try:
                global_nations_db.checkpoint()
            except Exception as e:
                logger.warning(f"Checkpoint loop error: {e}")
            try:
                from PnWHarvester.db.news_db import get_news_db as _get_news_db
                _get_news_db().checkpoint()
            except Exception as e:
                logger.warning(f"News DB checkpoint error: {e}")
        logger.info("Checkpoint loop shut down cleanly")

    async def _shutdown_watcher():
        """Wait for shutdown signal, then cancel all subscription tasks."""
        await _shutdown.wait()
        logger.info("Shutdown signal received — stopping all subscriptions…")
        # Signal all subscriptions to stop their restart loops
        nations_sub.running  = False
        wars_sub.running     = False
        bankrecs_sub.running = False
        # Give in-flight asyncio.create_task() DB writes a moment to complete
        # before the event loop is torn down. 3 seconds is enough for any
        # pending SQLite write (they're all sub-100ms).
        await asyncio.sleep(3)
        # Cancel all top-level tasks so gather() returns
        for t in asyncio.all_tasks():
            if t is not asyncio.current_task():
                t.cancel()

    # Run everything concurrently. _shutdown_watcher cancels the others on signal.
    await asyncio.gather(
        asyncio.create_task(_run_nations(),      name="nations"),
        asyncio.create_task(_run_wars(),         name="wars"),
        asyncio.create_task(_run_bankrecs(),     name="bankrecs"),
        asyncio.create_task(_run_turn_revenue(), name="turn_revenue"),
        asyncio.create_task(_run_checkpoint(),   name="checkpoint"),
        asyncio.create_task(_shutdown_watcher(), name="shutdown_watcher"),
        return_exceptions=True,
    )

    # ── Final WAL checkpoint on clean exit ────────────────────────────────────
    logger.info("Performing final WAL checkpoint on all databases…")
    for _db, _name in [
        (global_nations_db, "GlobalNations.db"),
        (holdings_db,       "holdings.db (GlobalNations.db WAL)"),
    ]:
        try:
            _db.checkpoint()
            logger.info(f"  ✓ {_name} checkpointed")
        except Exception as e:
            logger.warning(f"  ✗ {_name} checkpoint failed: {e}")
    try:
        from PnWHarvester.db.news_db import get_news_db as _get_news_db
        _get_news_db().checkpoint()
        logger.info("  ✓ news DBs checkpointed")
    except Exception as e:
        logger.warning(f"  ✗ news DB checkpoint failed: {e}")
    logger.info("Harvester shut down cleanly.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PnW Harvester — Nights Watch subscription service")

    # ── NW wars backfill ──────────────────────────────────────────────────────
    parser.add_argument("--sync-nw-wars", action="store_true",
                        help="Backfill NW wars on startup (off by default)")
    parser.add_argument("--nw-wars-days", type=int, default=7,
                        help="Days of NW wars to backfill (default: 7)")
    parser.add_argument("--nw-wars-since", type=str, default=None,
                        help="NW wars backfill start date YYYY-MM-DD")
    parser.add_argument("--nw-wars-until", type=str, default=None,
                        help="NW wars backfill end date YYYY-MM-DD (default: today)")

    # ── NW nations sync ───────────────────────────────────────────────────────
    parser.add_argument("--skip-nw-nations-sync", action="store_true",
                        help="Skip the NW nations sync on startup")
    parser.add_argument("--force-nw-nations-sync", action="store_true",
                        help="Force full repopulation of NW nations")

    # backward-compat aliases
    parser.add_argument("--sync-irs-wars",          action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--irs-wars-days",           type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--irs-wars-since",          type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--irs-wars-until",          type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--skip-irs-nations-sync",   action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--force-irs-nations-sync",  action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--sync-ep-wars",            action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--ep-wars-days",            type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--ep-wars-since",           type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--ep-wars-until",           type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--skip-ep-nations-sync",    action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--force-ep-nations-sync",   action="store_true", help=argparse.SUPPRESS)

    args = parser.parse_args()

    sync_wars  = args.sync_nw_wars or args.sync_irs_wars or args.sync_ep_wars
    wars_days  = args.nw_wars_days
    if wars_days is None:
        wars_days = args.irs_wars_days if args.irs_wars_days is not None else (args.ep_wars_days if args.ep_wars_days is not None else 7)
    wars_since = args.nw_wars_since or args.irs_wars_since or args.ep_wars_since
    wars_until = args.nw_wars_until or args.irs_wars_until or args.ep_wars_until
    skip_sync  = args.skip_nw_nations_sync or args.skip_irs_nations_sync or args.skip_ep_nations_sync
    force_sync = args.force_nw_nations_sync or args.force_irs_nations_sync or args.force_ep_nations_sync

    nw_wars_since_dt = (
        datetime.fromisoformat(wars_since).replace(tzinfo=timezone.utc)
        if wars_since else None
    )
    nw_wars_until_dt = (
        datetime.fromisoformat(wars_until).replace(tzinfo=timezone.utc)
        if wars_until else None
    )

    try:
        asyncio.run(main(
            sync_ep_wars_backfill=sync_wars,
            ep_wars_days=wars_days,
            ep_wars_since=nw_wars_since_dt,
            ep_wars_until=nw_wars_until_dt,
            skip_ep_nations_sync=skip_sync,
            force_ep_nations_sync=force_sync,
        ))
    except KeyboardInterrupt:
        # SIGINT on Windows (no add_signal_handler) — asyncio.run() already
        # cancelled all tasks; just suppress the traceback.
        logger.info("Harvester stopped by user (KeyboardInterrupt)")
    except Exception as e:
        logger.error(f"Harvester exited with error: {e}", exc_info=True)
        sys.exit(1)