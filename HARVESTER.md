# PnWHarvester

A standalone asyncio service for Politics & War (PnW) data collection, built with a GPP (Good Parallel Programming) architecture for high-performance real-time data synchronization.

## Overview

PnWHarvester is a data collection service that subscribes to PnW API v3 WebSocket events and stores data locally in SQLite databases. It operates independently of the Reaper Discord bot, focusing solely on data collection and storage.

### Key Features

- **Real-time WebSocket Subscriptions**: Subscribes to nation, city, war, attack, bank record, and trade events
- **GPP Architecture**: Unified locking, connection pooling, and write buffering for optimal performance
- **Dual-Write Strategy**: Writes all global data to GlobalWarsDB/GlobalNationsDB, and alliance-specific data to IRSWarsDB
- **News Generation**: Automatically generates narrative news events for wars, trades, and bank transfers
- **Turn Revenue Processing**: Calculates and applies turn revenue every 2 hours
- **Beige Alert Management**: Tracks beige status and generates early-exit notifications
- **Timed Queries**: Periodically fetches resource prices, game data, and completed trades
- **WAL Checkpointing**: Periodic checkpointing to keep WAL files small

## Configuration

### Environment Variables

Create a `.env` file in `Systems/Functions/` with the following:

```env
PANDW_API_V3_KEY=your_pnw_api_v3_key_here
```

### Command-Line Arguments

```bash
python harvester.py [--backfill-nations] [--backfill-wars]
```

- `--backfill-nations`: Backfill GlobalNations.db with all nations
- `--backfill-wars`: Backfill IRSWars.db with Darkstar wars (alliance ID 10259)

## Architecture

### GPP (Good Parallel Programming) Components

The Harvester uses a unified architecture for managing concurrent operations:

#### Core Infrastructure

- **LockManager** (`core/lock_manager.py`): Unified locking strategy for all databases
  - One lock per unique DB file path
  - Consistent lock acquisition order prevents deadlocks
  - Lock hierarchy: GlobalNations.db (1) > IRSWars.db (2) > bankrecs.db (3) > alerts.db (4) > news.db (5)
  - Lock timeout handling with retry logic

- **DatabasePool** (`core/database_pool.py`): Connection pooling for databases
  - 5-10 connections per database
  - Connection health checking
  - Automatic reconnection
  - Connection lifetime tracking (max 1 hour)

- **WriteQueue** (`core/write_queue.py`): Buffered write operations
  - Multiple flush policies (timeout, size, manual, hybrid)
  - Duplicate write merging (last writer wins)
  - Write priority handling (CRITICAL, HIGH, NORMAL, LOW)

- **GPPManager** (`core/gpp_manager.py`): Central orchestrator
  - Component lifecycle management (start/stop)
  - Health monitoring and status reporting
  - Graceful degradation on component failure

### Data Components

#### NationComponent (`components/nation_component.py`)

Handles nation and city event processing:

- **Subscriptions**: nation/create, nation/update, city/create, city/update, account/update
- **Sub-components**:
  - NationEventProcessor: Processes nation events
  - CityEventProcessor: Processes city events
  - AccountEventProcessor: Processes account events
  - SpendingDetector: Detects spending (cities, projects, military, upgrades)
  - BeigeEarlyExitDetector: Detects early beige exits
- **Databases**: GlobalNationsDB, HoldingsDB, beige_alerts_db
- **Features**:
  - Maintains in-memory set of Darkstar nations (alliance ID 10259)
  - Detects alliance changes and generates news
  - Detects spending events
  - Tracks beige early exits

#### WarComponent (`components/war_component.py`)

Handles war and attack event processing:

- **Subscriptions**: war/create, war/update, warattack/create
- **Sub-components**:
  - WarEventProcessor: Processes war events
  - AttackEventProcessor: Processes attack events
  - WarCacheManager: In-memory war cache for fast lookups
  - HoldingsUpdater: Updates HoldingsDB on ground-win attacks
  - WarNewsGenerator: Generates news events
  - BeigeManager: Manages beige state updates
  - WarStatsUpdater: Updates war statistics
- **Databases**: IRSWarsDB, GlobalWarsDB, HoldingsDB, GlobalNationsDB
- **Features**:
  - Dual-write strategy: All wars to GlobalWarsDB, Darkstar wars to IRSWarsDB
  - Enriches war data with policy and APE information from GlobalNationsDB
  - Tracks loot, war consumption, and combat losses
  - Generates news for war declarations, ends, WMD attacks, and loot
  - Updates war statistics (offensive/defensive slots, wins/losses)

#### BankrecComponent (`components/bankrec_component.py`)

Handles bank record event processing:

- **Subscriptions**: bankrec/create
- **Sub-components**:
  - BankrecEventProcessor: Processes bank record events
- **Databases**: BankrecsDB, HoldingsDB
- **Features**:
  - Detects war-related bank records (nation loot, alliance bank loot)
  - Skips nation loot (handled by war subscription)
  - Processes alliance bank loot separately
  - Generates news for bank transfers and alliance loot

#### TradeComponent (`components/trade_component.py`)

Handles trade event processing:

- **Subscriptions**: trade/update with buy_or_sell=1 filter (completed trades only)
- **Sub-components**:
  - TradeEventProcessor: Processes trade events
- **Databases**: HoldingsDB
- **Features**:
  - Only processes completed marketplace transactions (not posted offers)
  - Updates holdings for buyer and seller
  - Generates news for completed trades

#### RevenueComponent (`components/revenue_component.py`)

Handles turn revenue processing:

- **Sub-components**:
  - RevenueProcessor: Calculates and applies turn revenue
  - BeigeAlertUpdater: Updates beige alerts
- **Databases**: GlobalNationsDB, IRSWarsDB, HoldingsDB, beige_alerts_db
- **Features**:
  - Processes turn revenue every 2 hours (configurable)
  - Calculates revenue based on GNI, tax rate, and city count
  - Updates beige alerts with projected loot

#### BeigeAlertComponent (`components/beige_alert_component.py`)

Handles beige alert management:

- **Sub-components**:
  - BeigeAlertManager: Manages beige alerts
  - EarlyExitQueueManager: Manages early-exit notification queue
- **Databases**: beige_alerts_db
- **Features**:
  - Create, update, delete beige alerts
  - Enqueue early-exit notifications
  - Drain notification queue for Discord bot processing

#### TimedQueriesComponent (`components/timed_queries_component.py`)

Handles periodic data fetching:

- **Sub-components**:
  - TimedQueriesProcessor: Processes timed query data
- **Databases**: HoldingsDB
- **Features**:
  - Fetches resource prices every 15 minutes
  - Fetches game data (colors, game_date, city_average, radiation)
  - Fetches completed trades every 15 minutes
  - Generates trade news

### News Generation

#### Trade News (`subscriptions/trade_news_components.py`)

- **TradeNewsGenerator**: Generates news for completed trades
  - Extracts buyer/seller information
  - Calculates price per unit
  - Records trade completion with resource breakdown

#### War News (`subscriptions/war_news_components.py`)

- **WarNewsGenerator**: Generates news for war events
  - War declarations with alliance information
  - War ends with winner/loser
  - WMD attacks (nuke, missile) with infrastructure damage
  - Loot attacks with resource breakdown
- **BeigeManager**: Manages beige state updates on war loss
- **WarStatsUpdater**: Updates war statistics (slots, wins/losses)

### Database Layer

#### BaseDB (`db/base_db.py`)

Unified database component for all PnW Harvester databases:

- **Features**:
  - Configurable async mode (thread_pool or aiosqlite)
  - Standardized WAL mode, synchronous, busy_timeout settings
  - Automatic schema migration support
  - Backup/verification capabilities
  - Checkpoint management for WAL files
  - Unified locking via LockManager

#### Database Files

Located in `Databases/PnW/`:

- **GlobalNations.db**: All nations globally
  - Tables: nations, cities
  - Updated by: NationComponent

- **IRSWars.db**: Darkstar wars (alliance ID 10259)
  - Tables: wars, war_attacks
  - Updated by: WarComponent

- **GlobalWars.db**: All wars globally
  - Tables: wars, war_attacks
  - Updated by: WarComponent

- **bankrecs.db**: Bank records
  - Tables: bankrecs
  - Updated by: BankrecComponent

- **holdings.db**: Nation holdings
  - Tables: holdings
  - Updated by: NationComponent, WarComponent, BankrecComponent, TradeComponent, RevenueComponent

- **alerts.db**: Beige alerts
  - Tables: beige_alerts, early_exit_queue
  - Updated by: BeigeAlertComponent, WarComponent

- **News DBs**: News events
  - Tables: news (weekly, monthly, yearly)
  - Updated by: NewsComponent

## Dependencies

### Python Dependencies

From `PnWHarvester/requirements.txt`:

```
pnwkit
python-dotenv
aiosqlite
```

### System Dependencies

- Python 3.8+
- SQLite 3

## Running the Harvester

### Setup

1. Create a Python virtual environment:
```bash
python -m venv venv
```

2. Activate the virtual environment:
```bash
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r PnWHarvester/requirements.txt
```

4. Configure environment variables:
```bash
# Create Systems/Functions/.env
echo "PANDW_API_V3_KEY=your_key_here" > Systems/Functions/.env
```

### Start the Harvester

```bash
python harvester.py
```

### Backfill Data

```bash
# Backfill all nations
python harvester.py --backfill-nations

# Backfill Darkstar wars
python harvester.py --backfill-wars
```

## Logging

Logs are written to `harvester.log` with the following format:

```
[timestamp] [level] [module] message
```

Log levels:
- DEBUG: Detailed information for debugging
- INFO: General informational messages
- WARNING: Warning messages for potential issues
- ERROR: Error messages for failures

## Performance Characteristics

### Connection Pooling

- 5-10 connections per database
- Connection health checking every 60 seconds
- Max connection age: 1 hour
- Max idle time: 5 minutes

### Write Buffering

- Default flush timeout: 5 seconds
- Default flush size: 100 operations
- Max queue size: 1000 operations
- Critical writes flush immediately

### Lock Hierarchy

Locks are acquired in the following order to prevent deadlocks:

1. GlobalNations.db (priority 1)
2. IRSWars.db (priority 2)
3. bankrecs.db (priority 3)
4. alerts.db (priority 4)
5. news.db (priority 5)

### Subscription Auto-Restart

All subscription components use `run_forever()` with automatic restart on disconnect:

- Exponential backoff with jitter (10s to 5 minutes max)
- WebSocket connection health monitoring
- Graceful shutdown on cancellation

## Maintenance

### WAL Checkpointing

The Harvester runs periodic WAL checkpointing every 5 minutes to keep WAL files small. This is done synchronously while locks are not held to avoid blocking.

### Database Backups

Use the BaseDB backup methods:

```python
# Synchronous backup
db.backup_database()

# Asynchronous backup
await db.backup_database_async()
```

### Database Verification

Use the BaseDB verification methods:

```python
# Synchronous verification
result = db.verify_database()

# Asynchronous verification
result = await db.verify_database_async()
```

## Troubleshooting

### WebSocket Disconnections

If WebSocket connections disconnect frequently:

1. Check your PnW API v3 key is valid
2. Check network connectivity
3. Review logs for specific error messages
4. The Harvester will automatically restart with exponential backoff

### Database Lock Contention

If you see lock timeout errors:

1. Check if multiple processes are accessing the same database
2. Review the lock hierarchy in LockManager
3. Consider increasing lock timeout (default: 30 seconds)
4. Check for long-running transactions

### High Memory Usage

If memory usage is high:

1. Check connection pool sizes (default: 5-10 per DB)
2. Review queue sizes in WriteQueue
3. Check war cache size (default: 5000 wars)
4. Review processed ID caches (default: 5000 entries)

## Alliance Configuration

The Harvester is configured for Darkstar (alliance ID 10259):

- **NationComponent**: Tracks Darkstar nations in-memory set
- **WarComponent**: Dual-writes Darkstar wars to IRSWarsDB
- **NW_ALLIANCE_ID**: 10259 (defined in multiple components)

To change the alliance:

1. Update `NW_ALLIANCE_ID` in `nation_component.py`
2. Update `IRS_ALLIANCE_ID` in `war_component.py`
3. Update `NW_ALLIANCE_ID` in `harvester.py`
4. Update alliance references in web components (if applicable)

## Integration with Reaper Bot

The Harvester operates independently but provides data for the Reaper Discord bot:

- **HoldingsDB**: Used by Reaper for nation resource tracking
- **IRSWarsDB**: Used by Reaper for war monitoring
- **GlobalNationsDB**: Used by Reaper for nation lookups
- **alerts.db**: Used by Reaper for beige alert notifications
- **News DBs**: Used by Reaper for news display

The Reaper bot reads from these databases but does not write to them, ensuring clean separation of concerns.
