# 💀 ReaperBot

> A self-hosted Discord bot and data collection service for Politics & War — featuring a complete pet RPG, war intelligence tools, real-time data synchronization, and a full browser-based web interface. Everything runs on your own machine. No cloud hosting. No subscriptions. All data stays local.

---

## Quick Start

```bash
# Start the Discord bot + web server
python reaper.py

# Start the data collection service (separate process)
python harvester.py
```

Both services are configured through a single file: `Systems/Functions/.env`

The bot self-installs its Python venv and Node.js dependencies on first run. The only hard requirements are **Python 3.12+** and **Node.js**.

---

## Documentation

---

### 💀 [REAPER.md](REAPER.md) — Reaper Discord Bot

The main Discord bot (`python reaper.py`). Connects to Discord, loads all command cogs, starts the embedded web server on port 8080, and runs background tasks for beige alerts and user sync.

**What it covers:**

- Full configuration reference for `Systems/Functions/.env` — every variable, what it does, and what's required
- Startup sequence — venv self-relaunch, dependency check, cog loading order, command sync, web server startup, Cloudflare tunnel
- Complete command reference organized by department:
  - **EA** (Economic Affairs) — `/turn_bonuses`, `/game_info`, `/game_resources`, `/stocks`, `/history`, `/revenue`, `/rev_optimizer`, `/rss_alert_set/remove/list`
  - **FA** (Foreign Affairs) — `/treaties`, `/treaty_universe`
  - **IA** (Internal Affairs) — `/alliance`, `/audit`, `/show`, `/costs`, `/snipe_guide`, `/war_guide`
  - **MA** (Military Affairs) — `/wars`, `/wars_cost_bd`, `/wars_net_bd`, `/war`, `/compare_wars`, `/rankings`, `/raids`, `/destroy`, `/bounty`, `/treasures`, `/treasure_trades`, `/offshore`, `/units`, `/weapon_eff`, `/spy_chance`
  - **Other** — `/baseball`, `/activity`, `/theme emoji *`, loot message listener
  - **Tickets** — `/info`, `/verify`, `/delete_ticket`, `/resort_members`, `/ticket_role`
  - **Astrology** — `/tarot`, `/zodiac`
  - **Fun** — `/rps`, `/dice`, `/card`, `/range`, `/tictactoe`, `/roast`, `/compliment`, `/random`, `/walktru`, `/zombie_survival`, `/zombie_character`
  - **Admin** — `/shutdown`, `/usage`, `/servers`, `/leadership`, `/webpage`
- Background tasks: two-stage beige notification loop (early-exit drain, ~2h warning, ~15min final), periodic Discord user sync
- Database structure for all local SQLite files
- Full Python and Node.js dependency list

---

### 🚜 [HARVESTER.md](HARVESTER.md) — PnWHarvester Data Collection Service

The standalone data collection daemon (`python harvester.py`). Runs independently of the Discord bot and keeps all local databases current via live WebSocket subscriptions to the PnW API v3. Reaper is read-only against these databases.

**What it covers:**

- Complete startup sequence and venv self-relaunch guard
- GPP (Good Parallel Programming) core infrastructure:
  - **LockManager** — one lock per DB file, deadlock-safe acquisition order
  - **DatabasePool** — 5–10 connection pool per DB with health checking
  - **WriteQueue** — buffered writes with deduplication and priority levels
  - **NationCache** — bulk in-memory cache of all ~40k nations and cities
  - **SharedWebSocketManager** — circuit breaker, exponential backoff, event buffering
  - **ActivityTracker** — per-subscription stall detection driving auto-restarts
- All nine components with their subscriptions and behavior:
  - **NationComponent** — `nation/update|create`, `city/update|create`, `account/update`, `alliance/update|create`; spending detection, beige early-exit detection
  - **WarComponent** — `war/create|update`, `warattack/create`; dual-write strategy (all wars → GlobalWars.db, Darkstar wars → IRSWars.db), loot back-calculation
  - **BankrecComponent** — `bankrec/create`; nation loot vs. alliance loot vs. normal transfer classification
  - **TradeComponent** — `trade/update` (completed trades only); holdings update + news generation
  - **TreatyComponent** — `treaty/create|update|delete`; 24-hour silence tolerance
  - **RevenueComponent** — runs every 2 hours aligned to PnW turn boundaries; full city-build revenue engine
  - **TimedQueriesComponent** — runs every 15 minutes; resource prices, game data, radiation, completed trades
  - **BeigeAlertComponent** — manages `alerts.db` and the early-exit queue
  - **NewsComponent** — writes to WeeklyNews, MonthlyNews, and YearlyNews DBs simultaneously
- Complete database schema for all PnW databases (GlobalNations, GlobalWars, IRSWars, bankrecs, holdings, Treaties, news)
- Command-line flags: `--sync-nw-wars`, `--nw-wars-days`, `--nw-wars-since/until`, `--skip/force-nw-nations-sync`
- Health monitoring, WAL checkpointing, performance characteristics, and troubleshooting guide

---

### 💻 [WEBSITE.md](WEBSITE.md) — Web Interface

The browser-based interface embedded inside the Discord bot process. Accessible at your configured domain (default `https://reaper.qzz.io`) or locally at `http://localhost:8080`. Most PnW analytics pages are public; pet system pages require Discord login.

**What it covers:**

- Architecture: FastAPI + Uvicorn, Vanilla JS SPA, SQLite shared with bot, Discord OAuth2, WebSocket and SSE for real-time features
- Full page reference:
  - **Pets** — adoption flow, My Pet, pet roster, bazaar, ability tree, arena (NPC/PvP/4-player boss), colosseum, dungeon, Survivor Series, tasks, pet stock market, game info
  - **Casino** — lobby (12 live rooms), slots, blackjack, Texas Hold'em, craps, races, mini-games, powerball, wheel, scratch cards, keno, leaderboard, library
  - **PnW Analytics** — Watch war dashboard, nations search, revenue calculator, revenue optimizer, cost calculator, alliance comparison, full-mill rankings, raids, weapons, treaty universe globe, news feed, personal nation dashboard (goals, build plan, war stats, snapshot)
  - **Utility** — homepage, astrology, commands, documentation browser, settings, contact, privacy, terms, cache management
- Complete REST API reference for all ~45 API modules organized by category
- Static asset structure, i18n/locale system, caching strategy
- Deployment guide: local dev, Cloudflare Tunnel setup, CDN cache purging
- Full environment variable and configuration reference

---

### 📄 [LICENSE.txt](LICENSE.txt) — License & Attributions

MIT License covering all three systems (Reaper Bot, PnWHarvester, Web Interface). Also includes:

- Third-party Python and Node.js dependency attributions with their respective licenses
- External service integrations (Discord, Politics & War API, Groq, Google Translate, Cloudflare, Giphy, Pixabay)
- Data and privacy statement — all data is stored locally, no data transmitted beyond listed API integrations, no real money involved in any feature
- Contact information

---

## Project Structure

```
Reaper/
├── reaper.py               Discord bot entry point
├── harvester.py            PnWHarvester entry point
├── requirements.txt        Python dependencies
├── package.json            Node.js dependencies
├── Systems/
│   ├── Functions/
│   │   └── .env            All configuration (API keys, tokens, settings)
│   ├── PnW/                Discord PnW command cogs (EA/FA/IA/MA/Other)
│   ├── Pets/               Pet system logic and Discord commands
│   ├── Astrology/          Tarot and zodiac systems
│   ├── Fun/                Entertainment commands
│   ├── Tickets/            Ticket system
│   └── PnWCasino/          Casino Discord cog
├── PnWHarvester/
│   ├── components/         Subscription + background loop components
│   ├── core/               GPP infrastructure (locks, pools, queues, cache)
│   ├── db/                 Database handler classes
│   └── subscriptions/      News generation helpers
├── web/
│   ├── dashboard.html      SPA entry point
│   ├── Pages/              All HTML pages
│   ├── api/                FastAPI route modules (~45 files)
│   ├── js/                 Per-page JavaScript
│   ├── css/                Per-page stylesheets
│   ├── static/             Images, emojis, user backgrounds
│   └── docs/               Markdown documentation (served by /api/documentation/)
└── Databases/
    ├── Pets/               Pet system SQLite databases
    └── PnW/                PnW data SQLite databases (maintained by harvester)
```

---

## Key Facts

| | Reaper Bot | PnWHarvester |
|:---|:---|:---|
| Entry point | `python reaper.py` | `python harvester.py` |
| Purpose | Discord commands + web server | Live data collection |
| Port | 8080 (web) | — |
| Writes to PnW DBs? | ❌ Read-only | ✅ Yes |
| Requires Discord token? | ✅ Yes | ❌ No |
| Requires PnW API key? | Optional (some commands) | ✅ Yes |
| Can run without the other? | ✅ Yes (degraded data) | ✅ Yes |

Both processes share the same `Databases/` directory. Run them in separate terminals simultaneously for full functionality.
