# PnWHarvester

A standalone asyncio service for Politics & War (PnW) data collection. PnWHarvester subscribes to PnW API v3 WebSocket events, processes them through a GPP (Good Parallel Programming) component architecture, and stores the results in local SQLite databases shared with the Reaper Discord bot.

---

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
  - [Startup Sequence](#startup-sequence)
  - [GPP Core Infrastructure](#gpp-core-infrastructure)
  - [Components](#components)
  - [DB Layer](#db-layer)
  - [Subscriptions Layer](#subscriptions-layer)
- [Components Reference](#components-reference)
  - [NationComponent](#nationcomponent)
  - [WarComponent](#warcomponent)
  - [BankrecComponent](#bankreccomponent)
  - [TradeComponent](#tradecomponent)
  - [TreatyComponent](#treatycomponent)
  - [RevenueComponent](#revenuecomponent)
  - [TimedQueriesComponent](#timedqueriescomponent)
  - [BeigeAlertComponent](#beigecomponent)
  - [NewsComponent](#newscomponent)
- [Database Reference](#database-reference)
  - [GlobalNations.db](#globalnationsdb)
  - [GlobalWars.db](#globalwarsdb)
  - [IRSWars.db](#irswarsdb)
  - [bankrecs.db](#banecsdb)
  - [holdings.db](#holdingsdb)
  - [Treaties.db](#treatiesdb)
  - [WeeklyNews / MonthlyNews / YearlyNews DBs](#news-dbs)
  - [reaper.db](#reaperdb)
  - [alerts.db](#alertsdb)
  - [MyNations.db](#mynationsdb)
- [Command-Line Reference](#command-line-reference)
- [Configuration](#configuration)
- [Health Monitoring](#health-monitoring)
- [Performance Characteristics](#performance-characteristics)
- [Maintenance](#maintenance)
- [Troubleshooting](#troubleshooting)

---

## Overview

PnWHarvester is the data-collection backbone. It runs as a **completely standalone process** — no Discord connection, no bot — and feeds every database that the Reaper web interface and Discord bot read from.

Key traits:

- **Real-time WebSocket subscriptions** via `pnwkit` — nation, city, account, alliance, war, warattack, bankrec, trade, and treaty events all stream in live.
- **Dual-write strategy for wars** — every war in the game goes to `GlobalWars.db`; wars involving Darkstar (alliance 10259) also go to `IRSWars.db`.
- **Holdings tracking** — cash, resources, and military units for every tracked nation are maintained in real time by deducting purchases and crediting loot/revenue/bank transfers.
- **News generation** — all significant events are written simultaneously to three rolling news databases (weekly, monthly, yearly) with Reaper-flavoured narrative text.
- **Turn revenue processing** — every 2 hours the component calculates and applies turn revenue to all tracked nations.
- **Timed queries** — every 15 minutes the component fetches resource prices, game data (colors, radiation, game date), and recently completed trades.
- **Beige alert management** — beige alert state is kept in sync from live nation events, with early-exit detection and Discord DM notification queuing.
- **Treaty tracking** — all alliance treaty creation, updates, and cancellations are persisted.
- **WAL checkpointing** — every 5 minutes a background task checkpoints the WAL files to keep them small.

---

## Quick Start

### Prerequisites

- Python 3.11+ (the venv auto-re-launch guard at the top of `harvester.py` handles this)
- PnW API v3 key with WebSocket access

### Setup

```bash
# 1. The venv is already set up by install_venv.bat; just activate
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

# 2. Set your API key
#    Create or edit Systems/Functions/.env and add:
echo PANDW_API_V3_KEY=your_key_here >> Systems/Functions/.env

# 3. Run
python harvester.py
```

The harvester self-relaunches into the `.venv` Python if needed, so running `python harvester.py` from any Python is safe.

### Normal startup

```
2025-01-01 12:00:00 [harvester] INFO: Initialising databases...
2025-01-01 12:00:01 [harvester] INFO: Nation cache loaded: {'nations_count': 42000, ...}
2025-01-01 12:00:02 [harvester] INFO: Darkstar nations sync: {'nations_synced': 72}
2025-01-01 12:00:03 [harvester] INFO: GPP Manager started
2025-01-01 12:00:03 [nation_component] INFO: nation/update subscription active
2025-01-01 12:00:03 [war_component] INFO: warattack/create subscription active
...
```

Logs go to both stdout and `harvester.log`.

---

## Architecture

### Startup Sequence

```
harvester.py main()
  │
  ├─ Load .env (PANDW_API_V3_KEY)
  ├─ Init all DB instances
  │    GlobalNationsDB, GlobalWarsDB, IRSWarsDB, HoldingsDB,
  │    BankrecsDB, TreatiesDB, BeigeAlertDB, NewsDB
  │
  ├─ Load NationCache (bulk-load all nations + cities into RAM)
  ├─ sync_nations() — Darkstar nations sync on startup
  │
  ├─ (optional) --sync-nw-wars backfill
  │
  ├─ GPPManager.initialize()
  │    ├─ SharedWebSocketManager.initialize()
  │    ├─ Init DatabasePool for each DB
  │    ├─ Init WriteQueue for each DB
  │    └─ Instantiate all components:
  │         BeigeAlertComponent → NewsComponent → NationComponent
  │         WarComponent → BankrecComponent → TradeComponent
  │         TreatyComponent → RevenueComponent → TimedQueriesComponent
  │
  ├─ GPPManager.start()
  │    ├─ SharedWebSocketManager.start()
  │    └─ Launch each component:
  │         Subscription components → run_forever() tasks
  │         Background loop components → _run_loop() tasks
  │
  └─ Main watchdog loop
       ├─ Checkpoint task (every 5 min)
       ├─ Shutdown watcher
       └─ GPP health monitor (every 60 s)
```

### GPP Core Infrastructure

All four core infrastructure objects are **global singletons** (get via `get_lock_manager()`, `get_pool_manager()`, `get_queue_manager()`).

#### LockManager (`core/lock_manager.py`)

One `asyncio.Lock` per unique DB file path — prevents concurrent writes from multiple components to the same database.

Acquisition order (deadlock prevention):

| Priority | Database |
|:---:|:---|
| 1 | `GlobalNations.db` |
| 2 | `IRSWars.db` |
| 3 | `bankrecs.db` |
| 4 | `alerts.db` |
| 5 | `news.db` |

Unknown DBs default to priority 999. When multiple locks must be held simultaneously they are always acquired in priority order.

- Default timeout: **30 seconds**
- Per-lock stats: acquisitions, releases, timeouts, wait time, current holders

#### DatabasePool (`core/database_pool.py`)

Connection pool per DB file — avoids the overhead of opening a new `sqlite3.Connection` on every operation.

- Default pool size: **5 connections** per DB
- Maximum pool size: **10 connections** per DB
- Max connection age: **1 hour**
- Max idle time: **5 minutes**
- Health check interval: **60 seconds** (runs `SELECT 1`)
- Connections are configured with: `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=15000`, `wal_autocheckpoint=1000`

#### WriteQueue (`core/write_queue.py`)

Buffered write operations with deduplication. Each DB file gets its own queue.

- Flush policy: **HYBRID** (flush when size threshold OR timeout reached)
- Default flush timeout: **5 seconds**
- Default flush size: **100 operations**
- Max queue size: **1000 operations** (drops with WARNING if exceeded)
- Write priorities: `CRITICAL` (immediate flush), `HIGH`, `NORMAL`, `LOW`
- Deduplication: writes with the same key replace earlier queued writes (last-writer-wins)

In practice the harvester uses the DB directly (via `_run_sync` / `async with self._get_lock()`) rather than the write queue for most operations. The queue is available for future batching optimizations.

#### NationCache (`core/nation_cache.py`)

In-memory cache of the entire `nations` and `cities` tables from `GlobalNations.db`.

- Loaded once at startup: bulk `SELECT *` on both tables
- Refresh interval: **24 hours** (or explicit `force_refresh()`)
- Used by `RevenueComponent` to calculate per-nation turn revenue without individual DB reads
- Cache stats: `nations_count`, `cities_count`, `loaded`, `last_refresh`
- Individual nation invalidation available via `invalidate_nation(nation_id)`

#### SharedWebSocketManager (`core/websocket_manager.py`)

Centralized WebSocket connection manager built on top of `pnwkit.QueryKit`.

Reliability features:
- **Circuit breaker**: stops reconnection attempts after 5 consecutive failures; enters half-open state after 5-minute cooldown
- **Exponential backoff + jitter**: base 10s, max 5 minutes
- **EventBuffer**: buffers the last 1000 events for potential replay on reconnect
- **HealthProber**: probes connection health every 60 seconds
- **State machine**: `DISCONNECTED → CONNECTING → CONNECTED → RECONNECTING → CIRCUIT_OPEN`

Each component creates its own `QueryKit` instance and subscription loop rather than using the shared manager for event delivery (the shared manager's subscribe API exists for future consolidation). Components use `run_forever()` with their own reconnect logic.

#### ActivityTracker (`core/activity_tracker.py`)

Per-subscription health tracking used by the GPPManager to detect stalled subscriptions.

- Each subscription registers itself (e.g. `"nation/update"`, `"war/create"`)
- Records `last_message_at` and `message_count` on every received event
- `get_unhealthy_subscriptions()` returns subscriptions that have received at least one message and then gone silent for longer than `max_silence_seconds`
- Subscriptions that have never received any message are not flagged (normal for infrequent events like `treaty/create`)
- `max_silence_seconds` defaults to **120s** for subscription components; **3600s** for `TimedQueriesComponent`; **86400s** (24 hours) for `TreatyComponent`
- The GPPManager syncs the silence threshold from `HARVESTER_MAX_SILENCE` env var at each health check

---

### Components

All components live in `PnWHarvester/components/` and are managed by GPPManager. There are two lifecycle patterns:

**Subscription components** (`nation`, `war`, `bankrec`, `trade`, `treaty`) — launched via `run_forever()`:
```
run_forever()
  └─ start()          ← opens subscriptions, runs until disconnect/crash
       └─ asyncio.wait(tasks, FIRST_COMPLETED)
  ← on any exit, sleep + restart with exponential backoff
```

**Background loop components** (`revenue`, `timed_queries`) — launched via GPPManager calling `_run_loop()` directly, wrapped in `_run_background_loop()` for auto-restart.

**Helper components** (`beige`, `news`) — no background loop; called directly by other components.

---

## Components Reference

### NationComponent

**File:** `components/nation_component.py`

Subscribes to nation, city, account, and alliance events.

**Subscriptions:**

| Subscription | What triggers it |
|:---|:---|
| `nation/update` | Any nation stat change (military, beige, activity, alliance, etc.) |
| `nation/create` | New nation registered |
| `city/update` | City infrastructure, land, or improvement change |
| `city/create` | New city purchased |
| `account/update` | Player last_active or discord_id change |
| `alliance/update` | Alliance name or flag change |
| `alliance/create` | New alliance formed |

**Sub-components:**

- **NationEventProcessor** — Upserts nation to `GlobalNations.db`. On updates, strips resource/military columns (those are owned by `HoldingsDB`). Maintains in-memory set of Darkstar nation IDs (`_nw_nation_ids`) for fast membership checks. Detects alliance changes and fires `record_alliance_change` news.
- **CityEventProcessor** — Upserts city to `GlobalNations.db`. On `city/create`, increments `num_cities` on the parent nation row.
- **AccountEventProcessor** — Patches `last_active` and `discord_id` fields on the nation row.
- **SpendingDetector** — Triggered by both nation and city events. On `nation/update`: detects project purchases (using `turns_since_last_project` reset), military unit changes, deducts costs from `HoldingsDB`, fires news. On `city/update`: detects infra, land, and improvement purchases, deducts costs. On `city/create`: calculates and deducts city purchase cost.
- **BeigeEarlyExitDetector** — After processing `nation/update`, checks if the nation just left beige. If active alerts exist, enqueues early-exit notifications and deletes the alert rows.

**Databases written:** `GlobalNations.db` (via `GlobalNationsDB` and `HoldingsDB`)

**Notes:**
- Holdings columns (`money`, `coal`, `oil`, etc.) are **only written on INSERT** (first time a nation is seen) — on UPDATE these columns are excluded so `HoldingsDB` remains authoritative.
- War count columns (`wars_won`, `wars_lost`, `offensive_wars_count`, `defensive_wars_count`) are excluded from `nation/update` saves — `WarComponent` manages these via incremental deltas to prevent stale API snapshot values from overwriting real-time counts.

---

### WarComponent

**File:** `components/war_component.py`

Subscribes to war and attack events. Implements the **dual-write strategy**: every war/attack goes to `GlobalWars.db`; only Darkstar wars also go to `IRSWars.db`.

**Subscriptions:**

| Subscription | What triggers it |
|:---|:---|
| `war/create` | New war declared |
| `war/update` | War state change (peace offer, resistance change, end) |
| `warattack/create` | Any attack in any war |

**Sub-components:**

- **WarCacheManager** — In-memory dict of war context (IDs, alliance names, policies, APE flags) keyed by war ID. Used so attack events can look up their war without a DB round-trip. Max 5000 entries; evicts oldest on overflow.
- **WarEventProcessor** — Saves wars to `GlobalWars.db` and (if Darkstar) `IRSWars.db`. Enriches war data with `att_war_policy`, `def_war_policy`, `att_has_ape` from `GlobalNations.db` before saving. Generates war-declared news on `war/create`; generates war-ended news when `turns_left == 0` on `war/update`.
- **AttackEventProcessor** — Saves attacks to `GlobalWars.db` and (if Darkstar war) `IRSWars.db`. For `warattack/create` events where the war isn't in cache yet, queues the attack and retries after the next `war/create`. Routes to `HoldingsUpdater` for loot/consumption/losses and to `WarNewsGenerator` for WMD/loot news.
- **HoldingsUpdater** — Three operations triggered by attack events:
  - `update_holdings_for_attack` — On a ground-win attack: SET defender's holdings to back-calculated post-loot value (`remaining = looted × (1/loot_pct - 1)`), ADD loot to attacker. Loot percentage respects war type, Pirate policy (×1.4), APE project (×1.1), Turtle defense (×1.2), Moneybags defense (×0.6), defender APE (×0.9).
  - `update_war_consumption` — Deducts gasoline and munitions consumed per attack from the attacker's holdings.
  - `update_combat_losses` — Deducts unit losses from both attacker and defender holdings. Increments cumulative `*_kills` columns in `GlobalNations.db`.
- **WarNewsGenerator** — Generates war-declared, war-ended, loot attack, and WMD attack news via `news_writer`.

**Databases written:** `GlobalWars.db`, `IRSWars.db`, `GlobalNations.db` (unit kills, war counts), `HoldingsDB` (via `GlobalNations.db`)

---

### BankrecComponent

**File:** `components/bankrec_component.py`

**Subscription:** `bankrec/create`

Saves every bank record to `bankrecs.db`. Classifies records:

| sender_type | receiver_type | Note contains loot text | Classification |
|:---:|:---:|:---:|:---|
| 1 (nation) | 1 (nation) | ✓ | Nation loot — **skip holdings** (WarComponent owns this) |
| 2 (alliance) | 1 (nation) | ✓ | Alliance bank loot — add to winner only |
| 1 (nation) | 2 (alliance) | — | Deposit — deduct from nation |
| 2 (alliance) | 1 (nation) | — | Withdrawal — add to nation |
| 1 (nation) | 1 (nation) | — | Nation-to-nation transfer |

Generates news via `news_writer.record_bank_transfer` (for regular transfers) and `news_writer.record_loot_attack` (for alliance bank loot). Deduplication via a rolling `deque(maxlen=5000)` of processed IDs.

**Databases written:** `bankrecs.db`, `GlobalNations.db` (via `HoldingsDB`)

---

### TradeComponent

**File:** `components/trade_component.py`

**Subscription:** `trade/update` with filter `buy_or_sell=1` — only fires for **completed marketplace transactions** (actual buys/sells), not for posted trade offers.

Calls `holdings_db.apply_trade_completion()` to deduct money from buyer and resources from seller (or vice versa). Generates news via `TradeNewsGenerator`.

**Databases written:** `GlobalNations.db` (via `HoldingsDB`)

---

### TreatyComponent

**File:** `components/treaty_component.py`

**Subscriptions:** `treaty/create`, `treaty/update`, `treaty/delete`

- `treaty/create` → upsert to `Treaties.db` as active + generate treaty-signed news
- `treaty/update` → upsert to `Treaties.db` (type/URL changes, no news)
- `treaty/delete` → mark treaty inactive + generate treaty-cancelled news

ActivityTracker silence threshold: **24 hours** (treaties change infrequently; never triggers false stall restarts).

**Database written:** `Treaties.db`

---

### RevenueComponent

**File:** `components/revenue_component.py`

Background loop component. Fires once per PnW game turn (every 2 real hours at even UTC hours — 00:00, 02:00, 04:00, …). Waits until 30 seconds after the boundary to allow `nation/update` events to propagate before reading `beige_turns`.

**Loop behavior:**
1. Calculate seconds to next turn boundary; sleep until it.
2. Run `process_turn_revenue_batch()`.
3. Repeat from step 1.

**Revenue batch (`process_turn_revenue_batch`):**

Revenue application (runs if `HoldingsDB` is available):
1. Load all nation IDs with holdings from `GlobalNations.db`.
2. If `NationCache` is loaded, use it for fast access; otherwise bulk-load from DB.
3. For each nation, call `revenue_calc_sync()` from `Systems.PnW.Util.rev_correct` — the same calculation engine used by the web revenue page — with colors/radiation loaded once at `initialize()` time.
4. Bulk-apply all revenue deltas to `GlobalNations.db`.

Beige alert updates (runs for all nations with active alerts only):
1. Fetch all beige alert rows.
2. For each alerted nation, load the nation and call `BeigeAlertUpdater.update_beige_alerts()`.
3. If `beige_turns == 0`, delete the alert row; otherwise update turns and projected loot.

**Databases read/written:** `GlobalNations.db`, `IRSWars.db` (active war IDs), `alerts.db`

---

### TimedQueriesComponent

**File:** `components/timed_queries_component.py`

Background loop component. Fires every **15 minutes** (configurable via `interval_seconds`). 30-second startup delay to avoid API contention at boot.

**Each cycle (`_process_update`):**

1. **Game data** — `TimedQueriesProcessor.fetch_game_data()`:
   - Calls `query_instance.get_master_update_data()` (one GraphQL request for all master data).
   - Saves color bonuses to `reaper.db` via `database_manager.add_game_data("colors", ...)`.
   - Saves `game_date` and `city_average` to `reaper.db` via `add_game_info`.
   - Saves radiation levels (global + per-continent) to `reaper.db` via `add_radiation_data`.

2. **Resource prices** — `fetch_resource_prices()`:
   - Parses `tradeInfo.resources` from the master data.
   - Saves `best_sell`, `best_buy`, and `avg` price per resource to `reaper.db` via `add_resource_data`.
   - Tracks 12 resources: food, coal, oil, uranium, lead, iron, bauxite, gasoline, munitions, steel, aluminum, credit.

3. **Completed trades** — `fetch_completed_trades(minutes_back=15)`:
   - GraphQL query for recently accepted trades filtered by `date_accepted >= cutoff`.
   - Deduplicates via `_last_trade_id` watermark.
   - Calls `holdings_db.apply_trade()` per trade.
   - Calls `TradeNewsGenerator.generate_trade_completed_news()` per trade.

**Database written:** `reaper.db` (prices, game data, radiation), `GlobalNations.db` (via `HoldingsDB` for trade holdings)

---

### BeigeAlertComponent

**File:** `components/beige_alert_component.py`

Helper component (no background loop). Called by other components that need to read or write beige alert state. Wraps `Systems.Functions.beige_alerts_db` functions.

**Operations:**

- `create_alert(user_id, nation_id, nation_name, beige_turns, projected_loot)` — upsert
- `update_alert(alert_id, beige_turns, projected_loot)` — update turns and loot
- `delete_alert(alert_id)` — delete by ID
- `get_alerts_for_nation(nation_id)` — all alerts for a nation
- `get_all_alerts()` — all alerts in the system
- `enqueue_early_exit(user_id, nation_id, nation_name, projected_loot)` — add to notification queue
- `drain_queue()` — pop all queued early-exit notifications (consumed by Reaper bot)

**Database read/written:** `alerts.db`

---

### NewsComponent

**File:** `components/news_component.py`

Helper component (no background loop). Provides a clean async interface over `NewsDB`. Used by all components that generate news events.

Key method: `record_event(event_type, ...)` — delegates to `NewsDB.record_event()`, which writes simultaneously to `WeeklyNews.db`, `MonthlyNews.db`, and `YearlyNews{YYYY}.db`.

Also exposes `update_stats_only()` for incrementing alliance/nation counters without creating an event row.

---

## Database Reference

All databases live in `Databases/`.

### GlobalNations.db

**Path:** `Databases/PnW/GlobalNations.db`  
**Class:** `PnWHarvester/db/global_nations_db.py` → `GlobalNationsDB`

Stores every nation and city in the game. Also doubles as the holdings store (cash, resources, military units are columns on the `nations` table).

**Tables:**

`nations` — key columns:

| Column group | Columns |
|:---|:---|
| Identity | `id`, `nation_name`, `leader_name`, `continent`, `color`, `flag`, `discord`, `discord_id` |
| Alliance | `alliance_id`, `alliance_name`, `alliance_flag`, `alliance_position`, `alliance_seniority` |
| Stats | `num_cities`, `score`, `population`, `gross_national_income`, `gross_domestic_product` |
| Time | `date`, `last_active`, `turns_since_last_city`, `turns_since_last_project`, `vacation_mode_turns`, `beige_turns` |
| Military | `soldiers`, `tanks`, `aircraft`, `ships`, `missiles`, `nukes`, `spies` |
| War counts | `wars_won`, `wars_lost`, `offensive_wars_count`, `defensive_wars_count` |
| Unit kills | `soldier_kills`, `tank_kills`, `aircraft_kills`, `ship_kills`, `missile_kills`, `nuke_kills`, `spy_kills` |
| Resources | `money`, `coal`, `oil`, `uranium`, `iron`, `bauxite`, `lead`, `gasoline`, `munitions`, `steel`, `aluminum`, `food` |
| Holdings tracking | `confidence`, `last_loot_date`, `last_bankrec_date`, `last_revenue_date`, `last_event_date` |
| Projects (40+) | All PnW national project columns (boolean 0/1) |
| Military research | `military_research` (JSON) |

`confidence` values: `seeded` (initial from API), `tracked` (has received at least one live update), `fresh` (just reset from a loot event).

`cities` — improvement counts and infrastructure/land per city, foreign-keyed to `nations.id`.

**Indexes:** `alliance_id`, `alliance_name`, `nation_name`, `last_active`, `cities.nation_id`

**Important:** Resource/military columns on `nations` are owned by `HoldingsDB`. `NationComponent` only writes these on **INSERT** (initial seed). All subsequent updates go through `HoldingsDB` methods.

---

### GlobalWars.db

**Path:** `Databases/PnW/GlobalWars.db`  
**Class:** `PnWHarvester/db/global_wars_db.py` → `GlobalWarsDB`

All wars in the game (no alliance filter). Schema mirrors `IRSWars.db`.

**Tables:**

`wars` — complete war state including `is_active`, `end_reason`, `att_war_policy`, `def_war_policy`, `att_has_ape`.

`war_attacks` — every attack in every war with full loot and casualty breakdown.

`is_active` is computed from `turns_left`, `end_date`, `winner_id`, and peace flags on every upsert. Never overwrites non-null with NULL.

**Indexes:** `att_alliance_id`, `def_alliance_id`, `att_id`, `def_id`, `war_attacks.war_id`, `is_active`

---

### IRSWars.db

**Path:** `Databases/PnW/IRSWars.db`  
**Class:** `Systems/Functions/irs_wars_db.py` → `IRSWarsDB`

Identical schema to `GlobalWars.db` but contains **only Darkstar (alliance 10259) wars**. Used by the web Watch page, revenue calculations, and beige alert loot estimation.

---

### bankrecs.db

**Path:** `Databases/PnW/bankrecs.db`  
**Class:** `PnWHarvester/db/bankrecs_db.py` → `BankrecsDB`

Every bank record received from the `bankrec/create` subscription.

**Table:** `bankrecs` — `id`, `date`, `sender_id`, `sender_type`, `receiver_id`, `receiver_type`, `banker_id`, `note`, `money`, 11 resource columns, `tax_id`, `created_at`.

INSERT OR IGNORE — duplicates are silently skipped.

**Bulk backfill** available via `save_bankrecs_bulk(recs)`.

**Indexes:** `(sender_id, sender_type, date DESC)`, `(receiver_id, receiver_type, date DESC)`, `date DESC`, `banker_id`

---

### holdings.db

**Path:** `Databases/PnW/GlobalNations.db` (alias)

`HoldingsDB` (`PnWHarvester/db/holdings_db.py`) is an **adapter over `GlobalNations.db`** — it reads and writes the resource/military columns on the `nations` table. It does not have its own file.

Key methods:

| Method | What it does |
|:---|:---|
| `apply_loot_event(...)` | Back-calculates defender remaining holdings; adds loot to attacker |
| `apply_bankrec(rec)` | Deducts from sender (if nation), adds to receiver (if nation) |
| `apply_turn_revenue(nation_id, money_delta, resource_deltas, ...)` | Adds one turn of revenue |
| `apply_military_update(nation_id, old_mil, new_mil, ...)` | Updates unit counts, deducts purchase costs |
| `apply_war_consumption(nation_id, gasoline, munitions, ...)` | Deducts gas/muns consumed |
| `apply_combat_losses(attacker_id, defender_id, att_losses, def_losses, ...)` | Deducts units lost |
| `deduct_spending(nation_id, cash_cost, ...)` | Generic spending deduction |
| `get_holdings(nation_id)` | Returns holdings dict for one nation |
| `get_holdings_bulk(nation_ids)` | Bulk holdings fetch |

**Loot formula:**
```
loot_pct = base(war_type=0.10)
         × att_pirate_policy(×1.4)
         × att_ape(×1.1)
         × def_turtle_policy(×1.2)
         × def_moneybags_policy(×0.6)
         × def_ape(×0.9)

remaining = looted × (1/loot_pct - 1)
```

---

### Treaties.db

**Path:** `Databases/PnW/Treaties.db`  
**Class:** `PnWHarvester/db/treaties_db.py` → `TreatiesDB`

All active and historical alliance treaties.

**Table:** `treaties` — `id`, `date`, `treaty_type`, `treaty_url`, `turns_left`, `alliance1_id/name/flag`, `alliance2_id/name/flag`, `active` (1=live, 0=cancelled), `updated_at`.

Upsert logic: never overwrites non-null with NULL. `delete_treaty(id)` sets `active=0`.

**Indexes:** `alliance1_id`, `alliance2_id`, `active`, `treaty_type`

---

### News DBs

**Paths:** `Databases/PnW/WeeklyNews.db`, `MonthlyNews.db`, `WeeklyNews_prev.db`, `MonthlyNews_prev.db`, `YearlyNews{YYYY}.db`  
**Class:** `PnWHarvester/db/news_db.py` → `NewsDB`

Three rolling databases with identical schema. Every event is written to all three simultaneously.

**Period management:** At startup and every 60 seconds during writes:
- Weekly DB resets on Monday 00:00 UTC (old data copied to `WeeklyNews_prev.db` first)
- Monthly DB resets on the 1st of each month (old data copied to `MonthlyNews_prev.db`)
- Yearly DB never resets; a new file is created each calendar year

**Tables:**

`events` — event feed. Columns: `event_type`, `nation_id/name/flag`, `alliance_id/name/flag`, `sec_nation_id/name`, `sec_alliance_id/name` (secondary party), `value`, `value2`, `headline`, `detail` (HTML), `event_date`, `recorded_at`.

`alliance_stats` — running totals per alliance: cities_built, projects_bought, infra_spent, land_spent, improvements_spent, military_spent, wars_declared/won/lost/drawn, loot_gained/lost, infra_destroyed, nukes_used, missiles_used, bank_deposits/withdrawals, total_spent.

`nation_stats` — same counters at nation level plus `alliance_id` for grouping.

`meta` — `period_start` key tracks when this period began.

**Alliance name correctness:** At init and after every rollover, `NewsDB._refresh_alliance_names()` resolves all alliance IDs against `GlobalNations.db` to correct any stale names (PnW recycles alliance IDs).

**News narrative:** All article bodies are written by `PnWHarvester/db/news_writer.py` using dialog pools loaded from `PnWHarvester/db/Dialog/*.json`. Events involving Darkstar (alliance 10259) or The Keeper (nation 680891) get thematic Reaper-flavored text; other events get neutral newspaper style.

**Event types recorded:**

| Event type | Triggered by |
|:---|:---|
| `city_purchase` | `SpendingDetector` on city/create |
| `city_upgrade` | `SpendingDetector` on city/update (infra, land, improvements) |
| `project_purchase` | `SpendingDetector` on nation/update |
| `military_purchase` | `HoldingsDB.apply_military_update` |
| `alliance_change` | `NationEventProcessor` on nation/update |
| `war_declared` | `WarEventProcessor` on war/create |
| `war_ended` | `WarEventProcessor` on war/update (turns_left=0) |
| `loot_attack` | `WarNewsGenerator` on warattack/create (ground win) |
| `wmd_attack` | `WarNewsGenerator` on warattack/create (missile/nuke) |
| `bank_transfer` | `BankrecComponent` on bankrec/create |
| `trade_completed` | `TradeComponent` / `TimedQueriesComponent` |
| `treaty_signed` | `TreatyComponent` on treaty/create |
| `treaty_cancelled` | `TreatyComponent` on treaty/delete |

---

### reaper.db

**Path:** `Databases/reaper.db`  
**Managed by:** `Systems/Functions/database_manager.py` (not a PnWHarvester class)

Stores the timed-query outputs used by the web server and Discord bot:

- `resource_prices` — best sell/buy/avg per resource, timestamped
- `colors` — color bonuses per color, timestamped
- `game_info` — `game_date`, `city_average`, timestamped
- `radiation` — radiation levels per continent + global, timestamped
- `user_settings` — per-user web settings (theme, nation link, etc.)

---

### alerts.db

**Path:** `Databases/alerts.db`  
**Managed by:** `Systems/Functions/beige_alerts_db.py`

- `beige_alerts` — active beige alerts per user-nation pair: `user_id`, `nation_id`, `nation_name`, `beige_turns`, `projected_loot`
- `early_exit_queue` — early-exit notifications pending delivery by the Reaper bot

---

### MyNations.db

**Path:** `Databases/reaper.db` (the goals/plans tables live in `reaper.db`)  
**Class:** `PnWHarvester/db/my_nations_db.py` → `MyNationsDB`

Personal nation goals, build plans, and snapshots for the My Nation web page.

**Tables:**
- `nation_goals` — user-defined upgrade goals with `goal_type`, `target_value` (JSON), `estimated_cost`, `completed`, auto-completion tracking
- `nation_plans` — active build plan per nation with `plan_data` (JSON)
- `nation_snapshots` — point-in-time nation + cities snapshot for cost estimation

---

## Command-Line Reference

```
python harvester.py [options]
```

| Flag | Default | Description |
|:---|:---|:---|
| `--sync-nw-wars` | off | Backfill IRSWars.db with Darkstar wars on startup |
| `--nw-wars-days N` | `7` | Days of history to backfill (used with `--sync-nw-wars`) |
| `--nw-wars-since YYYY-MM-DD` | — | Explicit start date for backfill |
| `--nw-wars-until YYYY-MM-DD` | today | Explicit end date for backfill |
| `--skip-nw-nations-sync` | off | Skip the Darkstar nations sync on startup |
| `--force-nw-nations-sync` | off | Force full re-population of Darkstar nations from API |

**Backfill behavior:** The `--sync-nw-wars` backfill paginates in two passes — ended wars first, then active wars. Active-war data overwrites ended-war data for the same ID (fresher state wins). All saves are upserts.

**Old flag aliases:** `--sync-irs-wars`, `--sync-ep-wars`, `--irs-wars-*`, `--ep-wars-*`, `--skip/force-irs-nations-sync`, `--skip/force-ep-nations-sync` are all accepted as aliases (hidden from help).

---

## Configuration

### Environment Variables

All in `Systems/Functions/.env`:

| Variable | Required | Description |
|:---|:---:|:---|
| `PANDW_API_V3_KEY` | ✓ | PnW API v3 key with WebSocket access |
| `HARVESTER_MAX_SILENCE` | — | Seconds before a silent subscription is flagged unhealthy (default: `120`) |

### Alliance Configuration

Darkstar's alliance ID is **10259**, referenced as `NW_ALLIANCE_ID` / `IRS_ALLIANCE_ID` / `EP_ALLIANCE_ID` in:

- `harvester.py` (top-level constants)
- `components/nation_component.py` (`NW_ALLIANCE_ID = 10259`)
- `components/war_component.py` (`IRS_ALLIANCE_ID = 10259`)
- `components/treaty_component.py` (`NW_ALLIANCE_ID = 10259`)
- `subscriptions/war_news_components.py` (`NW_ALLIANCE_ID = 10259`)
- `db/news_writer.py` (`NW_ALLIANCE_ID = 10259`)

To track a different alliance, update all six locations.

---

## Health Monitoring

The GPPManager runs a health check loop every **30 seconds** (first check delayed 60 seconds after startup to allow subscriptions to receive initial messages).

**For each subscription component**, the health check:
1. Calls `get_component_stats()` to refresh stats.
2. Calls `activity_tracker.get_unhealthy_subscriptions()` — returns subscriptions that have received at least one message and then gone silent beyond `max_silence_seconds`.
3. If any subscription is stalled, marks the component `UNHEALTHY` and calls `_restart_component(name)`.

**Restart rate limiting:** Max 30 restarts per hour per component. If a component has been healthy for 5+ minutes since the last restart, the counter resets.

**Restart procedure:** Cancels the component's asyncio task and launches a new `run_forever()` / `_run_loop()` task.

**For background loop components** (`revenue`, `timed_queries`), the `ActivityTracker` silence threshold is not overridden by the manager — these components manage their own health internally.

**GPP health is logged every 60 seconds:**
```
GPP Health: 8/8 healthy, 8 running, 0 total errors, uptime 42.3m
```

**Full GPP stats on shutdown** (via `gpp_manager.get_stats()`): per-component health, error counts, uptime.

---

## Performance Characteristics

| Characteristic | Value |
|:---|:---|
| Connection pool size | 5–10 per DB |
| Connection max age | 1 hour |
| Connection health check | Every 60 s |
| WriteQueue flush timeout | 5 s |
| WriteQueue flush size | 100 ops |
| WriteQueue max size | 1000 ops |
| War cache size | 5000 wars in-memory |
| Processed ID dedup | 5000 entries (rolling deque) |
| NationCache refresh | 24 hours |
| WAL checkpoint | Every 5 minutes |
| Health check | Every 30 seconds |
| Turn revenue | Every 2 hours (aligned to game turns) |
| Timed queries | Every 15 minutes |
| Lock timeout | 30 seconds |
| Subscription silence timeout | 120 s (subscriptions), 3600 s (timed_queries), 86400 s (treaties) |
| Reconnect backoff | 10 s base, ×2 per retry, max 300 s, ±20% jitter |

---

## Maintenance

### WAL Checkpoint

Checkpoints run automatically every 5 minutes via `_run_checkpoint()` for `GlobalNations.db`, `IRSWars.db`, `bankrecs.db`, and all news DBs. A final checkpoint runs on clean shutdown.

To manually checkpoint:
```python
db.checkpoint()          # synchronous
await db.checkpoint_async()  # async
```

### Database Backup

```python
path = db.backup_database()                  # timestamped backup
path = db.backup_database("path/to/backup")  # explicit path
path = await db.backup_database_async()      # async version
```

Copies the `.db` file plus any `.db-wal` and `.db-shm` sidecar files.

### Database Verification

```python
result = db.verify_database()
# Returns: {path, exists, size_bytes, tables, integrity_check, wal_size_bytes, shm_size_bytes}
result = await db.verify_database_async()
```

### Bankrecs Cleanup

Old bank records can be pruned to save disk space:
```python
await bankrecs_db.cleanup_old_bankrecs(days=30)  # delete records older than 30 days
```

---

## Troubleshooting

### WebSocket disconnects / subscription restarts

These are normal. The PnW API drops WebSocket connections periodically. Every subscription component has `run_forever()` with exponential backoff. Check `harvester.log` for:
```
BankrecComponent disconnected (ServerDisconnectedError) — retry 1, restarting in 10.3s
```
This is expected behavior, not an error.

If a component is restarting repeatedly with short intervals, check:
1. API key validity and WebSocket permissions.
2. Network connectivity.
3. The `HARVESTER_MAX_SILENCE` setting — if set too low, legitimate quiet periods trigger restarts.

### Stalled subscription warning

```
WARNING: Component nation stalled: nation/update(145s > 120s) [threshold=120s]
```
The GPPManager detected no messages for over 2 minutes on a subscription. It will restart the component automatically. This can happen during game maintenance or very quiet turns.

### Database lock timeouts

```
WARNING: Lock acquisition timeout for GlobalNations.db after 30s
```
Multiple processes are accessing the same DB. Only run one harvester instance at a time. The bot (Reaper) is read-only from the harvester's databases, so it should not cause this.

### High memory usage

- `NationCache` holds all ~40,000+ nations + cities in memory. This is expected and intentional.
- `WarCacheManager` holds up to 5000 war contexts (small).
- Each subscription component has a `deque(maxlen=5000)` for processed-ID dedup (small).
- `EventBuffer` holds up to 1000 events for potential replay (small).

If memory is excessive, check if multiple harvester processes are running.

### "no such table: nations" in HoldingsDB

`HoldingsDB` always uses `GlobalNations.db` regardless of the `db_path` argument passed to it. If this error appears, `GlobalNations.db` itself may be missing or corrupt. Restore from backup or re-run the nations sync.

### News DB period rollover issues

If the weekly or monthly DB rolled over incorrectly (wrong `period_start`), manually delete the DB file and restart — `_ensure_dbs()` will recreate it with the correct period.

---

## Dependencies

From `PnWHarvester/requirements.txt`:

```
pnwkit
python-dotenv
aiosqlite
```

The full Reaper project dependencies (including `aiohttp`, `pydantic`, etc.) are in `requirements.txt` at the project root. The harvester's own requirements are minimal — `pnwkit` for WebSocket subscriptions, `python-dotenv` for `.env` loading, and `aiosqlite` for async DB operations in certain components.

System requirements:
- Python 3.11+
- SQLite 3.35+ (WAL mode, `TRUNCATE` checkpoint)
