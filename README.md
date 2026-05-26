# ReaperBot

A self-hosted Discord bot and data collection service for Politics & War, featuring a complete pet RPG system, war intelligence tools, and real-time data synchronization.

---

## Documentation

For comprehensive technical documentation on the two main systems:

- **[REAPER.md](REAPER.md)** — Complete documentation for the Reaper Discord bot, including architecture, component breakdown, command reference, and development guidelines.
- **[HARVESTER.md](HARVESTER.md)** — Complete documentation for the PnWHarvester data collection service, including GPP architecture, component breakdown, database schema, configuration, and performance characteristics.
- **[WEBSITE.md](WEBSITE.md)** — Complete documentation for the web interface, including page reference, API documentation, authentication, deployment, and configuration.

---

## Quick Start

**Reaper Bot**

```bash
python reaper.py
```

**PnWHarvester**

```bash
python harvester.py
```

Both services are configured via `Systems/Functions/.env`. See the documentation files above for detailed configuration options.

---

## Overview

**ReaperBot** is a self-hosted Discord bot that provides:
- A complete digital pet RPG with stats, combat, PvP, tournaments, casino games, and a full browser-based interface
- Deep Politics & War integration with real-time nation/war tracking, revenue calculators, war intelligence dashboards, raid finders, treaty maps, alliance comparisons, beige alerts, and global news/leaderboards
- A structured support ticket system with category routing and staff assignment
- Automatic message translation, daily horoscopes, tarot readings, and entertainment commands

**PnWHarvester** is a standalone asyncio service that:
- Subscribes to PnW API v3 WebSocket events for real-time data collection
- Stores data locally in SQLite databases (GlobalNationsDB, IRSWarsDB, HoldingsDB, etc.)
- Generates narrative news events for wars, trades, and bank transfers
- Processes turn revenue and manages beige alerts
- Uses a GPP (Good Parallel Programming) architecture with unified locking, connection pooling, and write buffering

Both services run entirely on your own machine — no cloud hosting, no third-party bot service, no subscription. All data stays local.

---

## License

See [LICENSE.txt](LICENSE.txt) for details.
