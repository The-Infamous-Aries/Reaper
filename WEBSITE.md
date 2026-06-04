# ReaperBot Web Interface

> A comprehensive browser-based interface for the Pets RPG system and Politics & War analytics tools, running as an embedded FastAPI server within the Discord bot.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Authentication](#authentication)
- [Pages Reference](#pages-reference)
  - [Dashboard](#dashboard)
  - [Pets Pages](#pets-pages)
  - [Casino Pages](#casino-pages)
  - [PnW Analytics Pages](#pnw-analytics-pages)
  - [Utility Pages](#utility-pages)
- [API Reference](#api-reference)
  - [Authentication APIs](#authentication-apis)
  - [Pets APIs](#pets-apis)
  - [Casino APIs](#casino-apis)
  - [PnW APIs](#pnw-apis)
  - [Utility APIs](#utility-apis)
- [Static Assets](#static-assets)
- [Deployment](#deployment)
- [Configuration](#configuration)

---

## Overview

The ReaperBot web interface is a full-featured browser application that runs as a FastAPI server embedded directly within the Discord bot process. It serves two primary systems:

- **Pets System** — A complete digital pet RPG with stats, combat, PvP, tournaments, casino games, and social features
- **PnW Analytics** — Politics & War intelligence tools including war tracking, revenue calculators, raid finders, treaty maps, and global news

The web server starts automatically when the bot launches (`python reaper.py`) and shares the same local SQLite databases as the Discord bot. There is no separate web server to manage, no Docker container required, and no database server to configure.

Key features:

- Single-page application architecture with dynamic page loading
- Discord OAuth2 authentication for personal data access
- Real-time WebSocket updates for live battle systems
- Server-Sent Events (SSE) for Survivor Series live feed
- Responsive design for desktop and mobile
- Cloudflare tunnel support for public access
- CDN caching for static assets

---

## Architecture

### Server Stack

- **Backend:** FastAPI (Python)
- **Frontend:** Vanilla JavaScript with HTML5
- **CSS Framework:** Bootstrap 5 (local)
- **Animation:** GSAP (local)
- **Database:** SQLite (shared with Discord bot)
- **Authentication:** Discord OAuth2
- **Real-time:** WebSocket for arena/casino, SSE for Survivor Series
- **Tunneling:** Cloudflare Tunnel (optional)

### Entry Points

- **Public URL:** Configured via `CUSTOM_DOMAIN` (default: `https://reaper.qzz.io`)
- **Local URL:** `http://localhost:8080`
- **Dashboard:** `web/dashboard.html` — Main SPA entry point

### Request Flow

1. User accesses the web interface
2. FastAPI serves static HTML/JS/CSS files
3. Client-side JavaScript makes API calls to backend endpoints
4. Backend queries SQLite databases or PnW API as needed
5. Responses are returned as JSON
6. Client updates UI dynamically

### Database Access

The web server reads from the same SQLite databases used by the Discord bot:

| Database | Purpose |
|:---|:---|
| `Databases/Pets/pets.db` | Pet system data (stats, inventory, XP) |
| `Databases/Pets/absorb.db` | PnW war absorb tracking |
| `Databases/Pets/colosseum.db` | Colosseum passive battle league |
| `Databases/Pets/dungeon.db` | Dungeon crawl state |
| `Databases/Pets/survivorseries.db` | Survivor Series game state |
| `Databases/Pets/powerball.db` | Powerball lottery |
| `Databases/Pets/Tasks.db` | Daily/weekly tasks |
| `Databases/PnW/GlobalNations.db` | Nation tracking |
| `Databases/PnW/IRSWars.db` | War records |
| `Databases/PnW/Treaties.db` | Alliance treaties |
| `Databases/PnW/GlobalWars.db` | Global war history |
| `Databases/PnW/holdings.db` | Nation resource holdings |
| `Databases/alerts.db` | User alerts |
| `Databases/reaper.db` | Bot settings and my-nations data |
| `Databases/sessions.db` | Web session storage |

Write operations go through API endpoints that validate user permissions and data integrity.

---

## Authentication

### Discord OAuth2

Access to personal pet data and alert management requires Discord OAuth2 authentication. The login flow:

1. User clicks "Login with Discord" button
2. Redirected to Discord's official authorization page
3. User authorizes the bot with `identify`, `email`, and `guilds` scopes
4. Discord redirects back with authorization code
5. Server exchanges code for access token
6. Session is stored server-side with user ID and access token
7. Access tokens are automatically refreshed in the background

### Session Management

- Sessions are stored server-side in `Databases/sessions.db`
- Access tokens refresh automatically before expiration
- User profile data syncs on login and periodically
- No passwords are stored; authentication is entirely delegated to Discord
- Sessions persist across page refreshes

### Public vs Private Pages

- **Public pages:** Most PnW analytics pages (watch, nations, revenue, comparison, raids, weapons, news, treaty universe, full mill) are accessible without login
- **Private pages:** Pet system pages, alert management, my-nation dashboard, and personal data require authentication

---

## Pages Reference

### Dashboard

**File:** `web/dashboard.html`

The main single-page application entry point. Features:

- Bot avatar and name display
- Live bot stats (servers, users, nations, pets) from `GET /api/stats`
- Recent activity feed via `GET /api/activity/recent`
- Sidebar navigation between all sections with customizable menu layout
- Dynamic page loading without full page refreshes
- Responsive design for desktop and mobile
- User authentication status indicator
- Theme customization (colors, custom background image)
- Language/locale selection

---

### Pets Pages

#### Onboarding

**Files:** `web/Pages/what_are_pets.html`, `web/Pages/petconnector.html`

New user onboarding for the pet system:

- **what_are_pets.html** — Introduction to the pet system: species, categories, elements, and gameplay overview
- **petconnector.html** — Pet creation wizard: species selection, category choice, element combination, custom name input

Validation enforced:
- Name checked for safe characters
- Duplicate pets per user prevented
- Species/category/element combinations validated server-side

#### Pet Management

**File:** `web/Pages/mypet.html`

Displays the user's pet with full stat sheet:

- Computed stats (ATT, DEF, INT, DEX, HAP, ENE)
- XP bar and current level
- Inventory items and equipped gear
- Battle action labels (Attack, Defense, Charge)
- Rename pet functionality
- Custom battle action name configuration
- Colosseum stats, dungeon records, Survivor Series records
- PnW war absorb section (link nation, absorb wins/unit kills as XP)

**File:** `web/Pages/pets.html`

Global pet roster for game entry and social browsing:

- All registered pets in the system
- Search and filter functionality
- Pet profiles with basic stats
- Social viewing of other players' pets and their relationship status

**File:** `web/Pages/bazaar.html`

In-world marketplace for pet items and equipment:

- Item listings with prices
- Search and filter by category
- Purchase functionality requiring sufficient XP
- User inventory display

**File:** `web/Pages/ability_tree.html` (`web/css/ability_tree.css`, `web/js/ability_tree.js`)

Interactive skill tree for pet abilities:

- Stat mastery point spending
- Ability unlocking
- Prerequisite visualization
- Skill tree navigation with zoom/pan

#### Activities

**File:** `web/Pages/arena.html`

Live multi-room combat arena with WebSocket broadcast:

- 12 live rooms; states: empty, npc_battle, pvp_waiting, pvp_battle, boss_waiting, boss_battle
- NPC battle with Easy/Average/Hard difficulty
- PvP matchmaking (join a room another player is waiting in)
- 4-player Co-op Boss battle with relationship multipliers
- Spectator view with live battle log
- Relationship system (ally, rival, neutral, enemy) affects boss battle damage

**File:** `web/Pages/colosseum.html`

Passive hourly battle league:

- Enroll your pet; battles run automatically every hour
- Opponents are matched from the current member pool (35% NPC chance if no player available)
- Pending XP, keys, and potions accumulate until claimed
- Key milestone rewards: every 2 wins = Key1, every 5 = Key1+Key2, every 10 = Key1+Key2+Key3
- PvP battles also award potions (2 for winner, 1 for loser)
- Historical round log

**File:** `web/Pages/dungeon.html`

Multi-floor dungeon crawl with party support:

- Create a dungeon solo or with party members
- 10 rooms per floor, multiple floors
- Room events: monster battles, boss battles, chests (4 tiers), traps, shrines
- Party-wide buffs/debuffs from traps and shrines
- Battle system with action skills, charge mechanics, and elemental advantages
- Persistent dungeon state across sessions

**File:** `web/Pages/survive.html`

Survivor Series — real-time battle royale:

- Lobby system with NPC fill (configurable NPC count)
- Countdown and auto-start
- Interactive elemental map (13 zones: fire, water, electric, ice, plant, rock, air, magic, holy, necro, psychic, fighting, basic)
- Per-round narrative events with elemental interactions
- Live feed via Server-Sent Events (SSE)
- Relationship multipliers affect combat outcomes
- Pet ability bonuses (survive_score_mult, stat mastery, advantage mastery, charge abilities)
- Historical game archive and pet-specific stats

**File:** `web/Pages/tasks.html`

Daily and weekly task system:

- Tasks auto-generated for all pet owners
- Completion tracked from bot and web actions
- DM notification preferences (on/off)
- Daily goal reward claiming

**File:** `web/Pages/pet_stock.html`

Simulated resource stock market:

- Hourly price updates
- Buy/sell functionality
- Portfolio tracking
- Market price history

**File:** `web/Pages/game_info.html`

Reference page for live game data:

- Current PnW resource prices
- Color bonuses
- Game state (turn, date, radiation)

---

### Casino Pages

**File:** `web/Pages/casino_lobby.html`

Casino lobby with live room state:

- 12 live game rooms with real-time WebSocket updates
- Room status (active, waiting, full)
- Player counts and seat availability indicators

**File:** `web/Pages/casino.html`

Solo slot machine:

- Multiple difficulty tiers
- Animated reels
- XP wagering
- Payout multipliers

**File:** `web/Pages/blackjack.html`

Multiplayer blackjack:

- Up to 6 players per table
- Standard blackjack rules
- Double-down and split support
- AI opponents for empty seats

**File:** `web/Pages/holdem.html`

Texas Hold'em poker:

- Up to 6 players
- AI opponents fill empty seats
- Full poker hand evaluation
- Full betting rounds (pre-flop, flop, turn, river)

**File:** `web/Pages/craps.html`

Dice game with side-betting:

- One active roller
- Observer side-bets
- Dice pass functionality
- Real-time updates

**File:** `web/Pages/races.html`

Pet racing:

- Up to 4 pets per race
- Observer betting
- Race animations
- Payout calculations

**File:** `web/Pages/minigames.html`

Collection of head-to-head mini-games:

- Various short-form games
- Direct player vs player
- Quick rounds

**File:** `web/Pages/powerball.html`

Lottery system:

- XP ticket purchases
- Jackpot system
- Draw history
- Winner announcements

**File:** `web/Pages/wheel.html`

Spin-the-wheel game:

- Variable XP prizes
- Spin animations
- Prize tiers

**File:** `web/Pages/scratch.html`

Instant-win scratch cards:

- Multiple card types
- Instant reveal
- Prize tiers

**File:** `web/Pages/keno.html`

Number-pick lottery:

- Number selection
- Draw results
- Payout calculations

**File:** `web/Pages/leaderboard.html`

Global rankings:

- Multiple categories (level, XP, battle wins, casino earnings, colosseum, SS)
- Privacy controls per user (show/hide from leaderboard)
- Leaderboard pagination and player search

**File:** `web/Pages/library.html`

In-app documentation and strategy guide system:

- Markdown guides served from `web/Pages/Library/`
- Available guides:
  - Basic Building Guide
  - Beige Cycle Guide
  - FAFO Doctrine
  - Pet Guide
  - Snipe Guide
  - Weapon Efficiency Guide

---

### PnW Analytics Pages

#### War Intelligence

**File:** `web/Pages/watch.html`

War intelligence dashboard for Darkstar (alliance 10259) and any alliance:

- Date range selection (Sun–Sat weeks and calendar months available from `GET /api/watch/periods`)
- Per-nation cost breakdown: units lost, infra destroyed, improvements, consumption
- Net damage calculations
- Loot tracking (cash and resources with monetary values)
- Per-nation opponent breakdown
- Alliance-wide totals
- Nation detail view with full city list
- All-time war stats per nation
- Top-3 ranking history per nation across all tracked periods
- Revenue calculation for any alliance via `GET /api/watch/revenue?alliance_id=`
- 2-minute response cache per date range + alliance combination

**File:** `web/Pages/nations.html`

Global nation search and view:

- Search by nation name, leader name, or alliance
- Filterable results
- Score, city count, military units display
- War policy, projects, activity status
- All data from `GlobalNations.db` (no live API calls)

**File:** `web/Pages/revenue.html`

Revenue calculator for any nation or alliance:

- Per-turn and per-day revenue breakdown
- Full city-build engine calculations (improvements, projects, color bonuses)
- Radiation levels and seasonal modifiers
- Current market prices from database
- Darkstar data served from database; all other alliances/nations fetched via PnW API

**File:** `web/Pages/rev_optimizer.html`

Economic optimization tool:

- City-by-city improvement analysis
- Ranked improvement suggestions for maximum net income
- Project-level suggestions
- Current revenue vs projected gain comparison
- Results sorted by monetary output per dollar spent

**File:** `web/Pages/cost_calc.html`

Purchase cost calculator:

- Infrastructure, land, cities, projects
- Current market prices
- Discount calculations (Urban Planning, Government Support Agency, etc.)
- Multi-item cost breakdown

**File:** `web/Pages/comparison.html`

Alliance comparison tool:

- Side-by-side alliance comparison
- Nation counts (total, active, applicants, VM, grey, beige, inactive)
- Score and city totals/averages
- Military breakdown (current, max, production, gaps)
- Project counts across 40+ projects
- Improvement totals
- City count distribution
- HTML report download
- Darkstar data from database; others from PnW API

**File:** `web/Pages/fullmill.html`

Full military mill ranking page:

- All game alliances ranked by overall max-mill percentage
- Per-unit-type percentages (soldiers, tanks, aircraft, ships)
- Current vs max unit counts, daily production, gaps
- 10-minute server-side cache for global ranking data

**File:** `web/Pages/raids.html`

Raid target finder:

- War range search from `GlobalNations.db`
- Filters: inactive days, weak military, beige status, minimum loot, excluded alliances, max defensive wars
- Projected loot from `holdings.db` (actual holdings) with revenue-based fallback
- Sorted by projected loot descending
- Beige alert management: set, refresh, delete via `alerts.db`
- Discord DM notifications at ~2 hours and ~15 minutes before beige expiry

**File:** `web/Pages/weapons.html`

Weapon efficiency calculator:

- **Theory mode:** Infra level and pop density input → min/max/avg damage, cost-multiplier thresholds (1×–20×), damage chart
- **Targeted mode:** Nation/alliance input → city scoring by expected missile damage, Iron Dome (30% block) and VDS (25% block) accounting, alliance ranking by best-city missile damage
- Live resource prices from database

**File:** `web/Pages/treaty_universe.html`

Interactive treaty web visualization:

- 3D globe using Three.js / three-globe
- Alliance nodes scaled by score
- Treaty edges colored by treaty type (MDP, ODP, Protectorate, etc.)
- Autocomplete alliance search
- Data from `Treaties.db` enriched with member counts from `GlobalNations.db`

**File:** `web/Pages/news.html`

Global PnW event feed and leaderboards:

- Time periods: current week, previous week, current month, previous month, yearly archives
- Event feed: war declarations/endings, city builds, projects, alliance changes
- Filterable by event type, alliance, nation
- Alliance leaderboard: wars declared/won, loot, nukes/missiles used, cities built, projects, spending
- Nation leaderboard: same metrics at individual level
- Summary cards: world totals for period
- War cost drill-down from `IRSWars.db`
- Live search across `GlobalNations.db`

**File:** `web/Pages/my_nation.html`

Personal nation dashboard (requires Discord login and linked nation):

- Full nation data bundle: nation stats, cities, revenue, modifiers, goals
- Per-city derived fields: improvement slots, power status, age
- Active war slot display (authoritative from `GlobalWarsDB`, not cumulative totals)
- Revenue breakdown: gross income, tax income, net cash per turn/day/week, upkeep breakdown, resource production
- Goals CRUD: city, infra, land, improvement, military, project, custom goal types
- Auto-completion detection: goals automatically marked done when the live nation meets targets
- Build plan editor: create/save/preview a city build plan with cost and progress tracking
- War stats panel: per-nation combat history from `IRSWars.db` with leaderboard rankings
- Nation snapshot save/refresh

---

### Utility Pages

**File:** `web/Pages/homepage.html`

Website homepage with navigation, feature overview, live bot stats, recent activity feed, and creator info.

**File:** `web/Pages/astrology.html`

Astrology system interface:

- Western zodiac sign lookup (birth date input)
- Chinese zodiac sign with authentic New Year dates (1900–2027)
- Primal astrology (combined spirit animal)
- Daily horoscope via external API proxy

**File:** `web/Pages/commands.html`

Discord slash command reference.

**File:** `web/Pages/documentation.html`

In-app documentation browser:

- Renders markdown docs from `web/docs/`
- Available docs: README, REAPER, HARVESTER, WEBSITE
- Full-text search across all docs

**File:** `web/Pages/settings.html`

User settings panel (requires login):

- Discord profile display
- Nation linking/unlinking (persisted to database)
- Theme customization (colors, custom background image, hide background toggle)
- Auto-fill presets for nations and alliances
- Privacy toggles (leaderboard visibility)
- Language/locale selection (en, es, fr, de, pt, zh, ja, ko, ru, ar)
- Menu layout customization (page order)

**File:** `web/Pages/contact.html`

Contact information page.

**File:** `web/Pages/privacy.html`

Privacy policy.

**File:** `web/Pages/terms.html`

Terms of service.

**File:** `web/Pages/cache-management.html`

Cache management interface for CDN/local cache control.

---

## API Reference

All API endpoints are served under the `/api` prefix.

### Authentication APIs

**File:** `web/api/discord_auth.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/auth/login` | GET | Initiate OAuth2 login, redirect to Discord |
| `/auth/callback` | GET | OAuth2 callback, exchange code for access token |
| `/auth/logout` | GET | Clear user session |
| `/auth/user` | GET | Return current authenticated user info |
| `/auth/refresh` | POST | Refresh access token if expired |

---

### Pets APIs

**File:** `web/api/pets_api.py` — Core pet data operations

Routes include pet creation, stat retrieval, XP/leveling, equipment management, rename, battle simulation (NPC and PvP), and related sub-systems.

**File:** `web/api/absorb_api.py` — PnW war absorb system

| Endpoint | Method | Description |
|:---|:---|:---|
| `/pets/absorb/status` | GET | Get absorb status (linked nation, totals, available, XP preview) |
| `/pets/absorb/wins` | POST | Absorb all available war wins as XP |
| `/pets/absorb/kills` | POST | Absorb available unit kills (all types or specific type) |
| `/pets/absorb/{unit_type}` | POST | Absorb a specific unit type (soldiers, tanks, aircraft, ships, missiles, nukes, spies) |

**File:** `web/api/bazaar_api.py` — Bazaar marketplace

| Endpoint | Method | Description |
|:---|:---|:---|
| `/api/bazaar/items` | GET | Get bazaar listings |
| `/api/bazaar/buy` | POST | Purchase item |
| `/api/bazaar/sell` | POST | Sell item |

**File:** `web/api/tasks_api.py` — Task system

| Endpoint | Method | Description |
|:---|:---|:---|
| `/tasks` | GET | Get user's active tasks |
| `/tasks/ensure-all` | POST | Admin: ensure all pet owners have tasks |
| `/tasks/dismiss` | POST | Dismiss a task |
| `/tasks/claim` | POST | Claim completed task reward |
| `/tasks/claim-goal` | POST | Claim daily goal reward |
| `/tasks/dm-prefs` | GET | Get DM notification preferences |
| `/tasks/dm-prefs` | POST | Set DM notification preferences |

**File:** `web/api/pet_stock_api.py` — Pet stock market

| Endpoint | Method | Description |
|:---|:---|:---|
| `/api/stock/prices` | GET | Get current stock prices |
| `/api/stock/buy` | POST | Buy stock |
| `/api/stock/sell` | POST | Sell stock |
| `/api/stock/portfolio` | GET | Get user portfolio |

**File:** `web/api/forge_api.py` — Item crafting/upgrading

| Endpoint | Method | Description |
|:---|:---|:---|
| `/api/forge/craft` | POST | Craft item |
| `/api/forge/upgrade` | POST | Upgrade item |

---

### Casino APIs

**File:** `web/api/casino_lobby_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/api/casino/lobby` | GET | Get lobby state (all rooms) |
| `/api/casino/join_room` | POST | Join a room |
| `/api/casino/leave_room` | POST | Leave a room |

**File:** `web/api/casino_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/api/casino/start_game` | POST | Start a game |
| `/api/casino/place_bet` | POST | Place bet |
| `/api/casino/game_action` | POST | Perform game action |

**File:** `web/api/blackjack_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/api/blackjack/hit` | POST | Hit |
| `/api/blackjack/stand` | POST | Stand |
| `/api/blackjack/double` | POST | Double down |
| `/api/blackjack/split` | POST | Split |

**File:** `web/api/holdem_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/api/holdem/fold` | POST | Fold |
| `/api/holdem/check` | POST | Check |
| `/api/holdem/call` | POST | Call |
| `/api/holdem/raise` | POST | Raise |

**File:** `web/api/craps_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/api/craps/roll` | POST | Roll dice |
| `/api/craps/place_bet` | POST | Place side bet |

**File:** `web/api/races_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/api/races/bet` | POST | Place bet on racer |
| `/api/races/start` | POST | Start race |

**File:** `web/api/minigames_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/api/minigames/start` | POST | Start mini-game |
| `/api/minigames/action` | POST | Game action |

**File:** `web/api/powerball_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/api/powerball/buy_ticket` | POST | Buy lottery ticket |
| `/api/powerball/draw` | GET | Get draw results |

**File:** `web/api/scratch_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/api/scratch/buy` | POST | Buy scratch card |
| `/api/scratch/reveal` | POST | Reveal card |

---

### Arena API

**File:** `web/api/arena_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/ws/arena` | WS | WebSocket connection for real-time room state |
| `/arena/rooms` | GET | Get all 12 room states |
| `/arena/join` | POST | Join a room (mode: npc, pvp, boss) |
| `/arena/leave` | POST | Leave current room |
| `/arena/battle/npc` | POST | Run NPC battle (easy/average/hard) |
| `/arena/battle/pvp` | POST | Accept PvP challenge from room challenger |
| `/arena/battle/boss/start` | POST | Start boss battle (requires ≥2 players) |
| `/arena/battle/boss/state` | GET | Get current boss battle state for room |
| `/arena/battle/boss/action` | POST | Submit player action for boss turn |

---

### Colosseum API

**File:** `web/api/colosseum_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/api/colosseum/state` | GET | Get full colosseum state (members + recent log) |
| `/api/colosseum/join` | POST | Enroll pet in colosseum |
| `/api/colosseum/leave` | POST | Remove pet from colosseum |
| `/api/colosseum/claim` | POST | Claim pending XP, keys, and potions |
| `/api/colosseum/log` | GET | Get recent battle log |

---

### Dungeon API

**File:** `web/api/dungeon_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/dungeon/create` | POST | Create a new dungeon (solo or party) |
| `/dungeon/active` | GET | Get user's active dungeons |
| `/dungeon/{dungeon_id}` | GET | Get dungeon state |
| `/dungeon/{dungeon_id}/ready` | POST | Mark user ready to advance |
| `/dungeon/{dungeon_id}/battle/start` | POST | Start a monster/boss battle in dungeon |
| `/dungeon/{dungeon_id}/battle/{battle_id}/status` | GET | Poll battle status (for multi-player sync) |
| `/dungeon/{dungeon_id}/battle/action` | POST | Submit battle action (attack/defend/charge/skill) |

---

### Survivor Series API

**File:** `web/api/ss_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/ss/state` | GET | Get full current game state |
| `/ss/map` | GET | Get map rendering data (positions, events, seed) |
| `/ss/join` | POST | Join current lobby |
| `/ss/start` | POST | Start game (requires ≥2 participants) |
| `/ss/leave` | POST | Leave (disabled — joining is permanent) |
| `/ss/events` | GET | Server-Sent Events stream for live updates |
| `/ss/last_game` | GET | Get last finished game snapshot |
| `/ss/history` | GET | List past games |
| `/ss/history/{game_id}/rounds` | GET | Get rounds for a specific game |
| `/ss/history/{game_id}/feed` | GET | Get live feed for a specific game |
| `/ss/history/{game_id}/participants` | GET | Get participants and placements for a game |
| `/ss/pet-stats` | GET | Get SS stats for the logged-in user's pet |
| `/ss/admin/kick_round` | POST | Admin: force-fire the round loop |
| `/ss/admin/refresh_abilities` | POST | Admin: refresh all participant abilities |
| `/ss/reset` | POST | Admin: reset the game entirely |

---

### PnW APIs

**File:** `web/api/watch_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/watch/wars` | GET | War cost data for date range and alliance |
| `/watch/wars/all-nations` | GET | All-time war stats for NW nations |
| `/watch/nations` | GET | All Darkstar nations with city aggregates |
| `/watch/nations/{nation_id}` | GET | Full nation detail including cities |
| `/watch/nations_by_alliance` | GET | Nations for any alliance by ID |
| `/watch/revenue` | GET | Revenue calculation for an alliance |
| `/watch/nation-ranks/{nation_name}` | GET | All periods where nation ranked top 3 |
| `/watch/periods` | GET | Available date periods with war data |
| `/watch/invalidate-cache` | POST | Clear wars response cache |

**File:** `web/api/pnw_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/api/pnw/nations` | GET | Search nations |
| `/api/pnw/alliance` | GET | Get alliance data |
| `/api/pnw/nation` | GET | Get nation details |
| `/api/pnw/projects` | GET | Get project data |

**File:** `web/api/rev_optimizer_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/api/rev_optimizer/nation` | GET | Optimize single nation |
| `/api/rev_optimizer/alliance` | GET | Optimize entire alliance |
| `/api/rev_optimizer/suggestions` | GET | Get improvement suggestions |

**File:** `web/api/raids_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/api/raids/targets` | GET | Find raid targets |
| `/api/raids/loot` | GET | Calculate projected loot |
| `/api/raids/alerts` | GET/POST/DELETE | Manage beige alerts |

**File:** `web/api/weapon_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/weapons/ac_data` | GET | Autocomplete data for nation/alliance search |
| `/weapons/theory` | GET | Theory mode calculation (infra + pop density) |
| `/weapons/targeted/nation` | GET | Targeted mode for a specific nation |
| `/weapons/targeted/alliance` | GET | Targeted mode for an alliance |

**File:** `web/api/news_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/api/news/events` | GET | Event feed for time period |
| `/api/news/alliance_leaderboard` | GET | Alliance rankings |
| `/api/news/nation_leaderboard` | GET | Nation rankings |
| `/api/news/summary` | GET | Period summary totals |
| `/api/news/war_details` | GET | War cost breakdown |

**File:** `web/api/treaty_universe_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/treaties/ac_data` | GET | Alliance list for autocomplete |
| `/treaties/universe` | GET | Full treaty graph (alliances + treaties + scores) |

**File:** `web/api/fullmill_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/fullmill/rankings` | GET | All alliances ranked by max mill percent (10-min cache) |

**File:** `web/api/my_nation_api.py` — Personal nation dashboard

| Endpoint | Method | Description |
|:---|:---|:---|
| `/mynation/{nation_id}` | GET | Full nation data bundle (2-min cache; `?refresh=true` to bust) |
| `/mynation/goals/check-completion/{nation_id}` | POST | Auto-complete goals that meet targets |
| `/mynation/goals/{nation_id}` | GET | List goals |
| `/mynation/goals` | POST | Create goal |
| `/mynation/goals/{goal_id}/complete` | POST | Mark goal done |
| `/mynation/goals/{goal_id}` | DELETE | Delete goal |
| `/mynation/snapshot` | POST | Save/refresh nation snapshot |

**File:** `web/api/plan_api.py` — Nation build plan

| Endpoint | Method | Description |
|:---|:---|:---|
| `/mynation/plan/{nation_id}` | GET | Get plan with progress and costs |
| `/mynation/plan` | POST | Create or update plan |
| `/mynation/plan/{nation_id}` | DELETE | Delete plan |
| `/mynation/plan/preview` | POST | Compute simulated nation preview after plan completion |

---

### Utility APIs

**File:** `web/api/stats_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/stats` | GET | Homepage stats (servers, users, nations, pets) |
| `/creator` | GET | Creator info |

**File:** `web/api/activity_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/activity/recent` | GET | Recent activity feed (last N events) |
| `/activity/add` | POST | Internal: add an activity entry |

**File:** `web/api/alerts_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/api/alerts/beige` | GET/POST/DELETE | Manage beige alerts |
| `/api/alerts/price` | GET/POST/DELETE | Manage price alerts |
| `/api/alerts/check` | GET | Check alert status |

**File:** `web/api/settings_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/settings` | GET | Get all settings for current user |
| `/settings` | POST | Update settings |
| `/settings` | DELETE | Delete all settings (theme, nation link, privacy, language, auto-fill) |
| `/settings/link-nation` | POST | Link a nation and persist to database |
| `/settings/link-nation` | DELETE | Unlink nation |
| `/settings/upload-background` | POST | Upload custom background image (JPEG/PNG/WebP, max 5 MB) |
| `/settings/upload-background` | DELETE | Remove custom background image |

**File:** `web/api/astrology_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/astrology/signs` | POST | Get Western + Chinese + Primal signs for a birth date |
| `/astrology/horoscope` | GET | Get daily horoscope for a zodiac sign |
| `/horoscope-proxy` | GET | Proxy external horoscope API (CORS bypass) |

**File:** `web/api/cache_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/api/cache/stats` | GET | Cache statistics |
| `/api/cache/clear` | POST | Clear cache |

**File:** `web/api/documentation_api.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/list` | GET | List available documentation files |
| `/{doc_id}` | GET | Get a documentation file (README, REAPER, HARVESTER, WEBSITE) |
| `/search` | GET | Full-text search across all documentation |

**File:** `web/api/library.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/api/library/articles` | GET | Get article list |
| `/api/library/article` | GET | Get article content |

**File:** `web/api/image_proxy.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/api/proxy/image` | GET | Proxy external images (CORS handling) |

**File:** `web/api/world_api.py` — World/social data

| Endpoint | Method | Description |
|:---|:---|:---|
| `/world/pets` | GET | Get all pets (for social features) |
| `/world/pet-info` | GET | Pet species info from `info.json` |
| `/world/my-relationships` | GET | Get current user's relationship list |
| `/world/relationship` | POST | Set relationship with another user |
| `/world/relationship/{target_user_id}` | DELETE | Remove relationship |
| `/world/gift` | POST | Gift an item to another user |

**File:** `web/api/docs.py`

| Endpoint | Method | Description |
|:---|:---|:---|
| `/docs` | GET | Interactive Swagger UI (FastAPI auto-generated) |

---

## Static Assets

### Directory Structure

```
web/
├── dashboard.html           Main SPA entry point
├── static/
│   ├── Images/              Static images (logos, backgrounds, avatars)
│   ├── Emojis/              Custom emoji assets organized by category
│   │   ├── Activity/
│   │   ├── Casino/
│   │   ├── Military/
│   │   ├── Pets/
│   │   ├── PnW Menu/
│   │   ├── Resources/
│   │   ├── War/
│   │   └── Watcher/
│   ├── user_backgrounds/    User-uploaded custom backgrounds
│   ├── locales/             i18n strings (en.json + others)
│   ├── dice-box/            3D dice rendering assets
│   ├── 404.html             Custom 404 page
│   └── 500.html             Custom 500 page
├── css/                     Per-page stylesheets
├── js/                      Per-page JavaScript files
├── Pages/                   HTML pages
│   └── Library/             Markdown strategy guides
├── api/                     Backend API modules
│   └── pets/                Pets sub-helpers (gpp_helpers.py)
├── components/              Shared HTML components
│   └── battle_settings_modal.html
├── docs/                    Documentation served by documentation_api.py
│   ├── README.md
│   ├── REAPER.md
│   ├── HARVESTER.md
│   └── WEBSITE.md
└── Wars/                    Static war report HTML files
```

### Caching Strategy

- **Static assets:** Cached at CDN level for up to 1 hour
- **HTML pages:** Never cached
- **API responses:** Never cached (except where explicitly implemented in-code)
- **Watch wars data:** 2-minute in-memory cache per date range + alliance ID
- **Full mill rankings:** 10-minute in-memory cache
- **My-nation data:** 2-minute in-memory cache per nation ID

### i18n / Localization

Locale strings live in `web/static/locales/`. The settings API exposes a `language` field; the frontend loads the matching locale JSON at startup.

---

## Deployment

### Local Development

The web server starts automatically with the bot:

```bash
python reaper.py
```

Access locally at: `http://localhost:8080`

### Public Access with Cloudflare Tunnel

To make the website publicly accessible:

1. Configure environment variables:
   ```
   USE_CLOUDFLARE_TUNNEL=true
   CUSTOM_DOMAIN=your-domain.com
   CF_ACCOUNT_ID=your-account-id
   CF_TUNNEL_ID=your-tunnel-id
   CF_API_TOKEN=your-api-token
   CF_TUNNEL_TOKEN=your-tunnel-token
   CF_CREDENTIALS_FILE=cloudflared-config/creds.json
   ```

2. Start the bot:
   ```bash
   python reaper.py
   ```

The Cloudflare tunnel starts automatically, making the site available at your configured domain.

### Manual Cloudflare Tunnel

If not using auto-start:

```bash
cloudflared tunnel run --config cloudflared-config/config.yml
```

### CDN Cache Purging

The bot can programmatically purge Cloudflare CDN cache when needed (requires `CF_API_TOKEN` and `CF_ACCOUNT_ID`).

---

## Configuration

### Environment Variables

**Web Server:**

| Variable | Purpose | Default |
|:---|:---|:---|
| `CUSTOM_DOMAIN` | Public-facing domain | `https://reaper.qzz.io` |
| `USE_CLOUDFLARE_TUNNEL` | Auto-start tunnel on bot startup | `false` |

**Discord OAuth2:**

| Variable | Purpose |
|:---|:---|
| `DISCORD_CLIENT_ID` | Discord application client ID |
| `DISCORD_CLIENT_SECRET` | Discord application client secret |
| `DISCORD_REDIRECT_URI` | OAuth2 callback URL |

**Cloudflare:**

| Variable | Purpose | Required |
|:---|:---|:---|
| `CF_ACCOUNT_ID` | Cloudflare account ID | For cache purge |
| `CF_TUNNEL_ID` | Tunnel ID | For named tunnel |
| `CF_API_TOKEN` | API token | For cache purge and tunnel |
| `CF_TUNNEL_TOKEN` | Tunnel auth token | For tunnel |
| `CF_CREDENTIALS_FILE` | Credentials JSON path | For tunnel |

### Port Configuration

The web server runs on port **8080** by default. This is hardcoded in the bot startup sequence.

### CORS Configuration

The web server handles CORS internally. External images are proxied through `image_proxy.py` to avoid CORS issues.

---

## Development

### Adding New Pages

1. Create HTML file in `web/Pages/`
2. Create corresponding CSS in `web/css/` (scope to page)
3. Create corresponding JS in `web/js/`
4. Create API file in `web/api/` if needed
5. Register the API router in the FastAPI app initialization
6. Add navigation entry in `web/dashboard.html`

### Adding New APIs

1. Create `router = APIRouter()` in a new file under `web/api/`
2. Define FastAPI routes with proper decorators
3. Implement database queries or external API calls
4. Add error handling and validation
5. Register the router in the web server initialization
6. Swagger UI auto-generates documentation at `/docs`

### Static Asset Management

- Images → `web/static/Images/`
- Per-page CSS → `web/css/`
- Per-page JavaScript → `web/js/`
- Custom emojis → `web/static/Emojis/`
- User-uploaded backgrounds → `web/static/user_backgrounds/` (managed via settings API)

---

## Troubleshooting

### Web Server Not Starting

- Check port 8080 is not in use
- Verify FastAPI and all dependencies are installed (`pip install -r requirements.txt`)
- Check `reaper_bot.log` and `site_debug.log` for startup errors

### Authentication Issues

- Verify the Discord application has the correct redirect URI configured
- Check `DISCORD_CLIENT_ID` and `DISCORD_CLIENT_SECRET` are set
- Ensure OAuth2 scopes (`identify email guilds`) are enabled in the Discord app

### Cloudflare Tunnel Issues

- Verify tunnel credentials are valid in `cloudflared-config/creds.json`
- Check `CF_TUNNEL_ID` matches your tunnel
- Ensure domain DNS points to the tunnel
- Check Cloudflare account permissions for the API token

### Database Access Issues

- Verify all database files exist in `Databases/`
- Check file permissions (bot process must have read/write access)
- Run `scripts/check_db_structure.py` to validate schema

---

## Security

- All authentication is delegated to Discord OAuth2
- No passwords are stored anywhere
- Sessions stored server-side in `sessions.db` only
- Access tokens are automatically refreshed
- Personal data endpoints require authentication and validate the requesting user owns the resource
- My-nation endpoints enforce `_require_own_nation` — users can only view their own linked nation
- Background image uploads validate magic bytes (JPEG/PNG/WebP), enforce 5 MB limit, and are stored per user ID
- API endpoints use parameterized SQLite queries throughout
- Rate limiting is implemented where appropriate

---

## Performance

- Static assets cached at CDN level
- Database queries use indexed columns
- WebSocket for real-time arena/casino updates
- SSE for Survivor Series live feed
- In-memory caching for expensive calculations (war costs, full mill rankings, my-nation data)
- Lazy loading for large datasets
- Pagination for leaderboards and feeds
- Bulk database loads (all nations + all cities in 2 queries) for full mill ranking

---

## Browser Support

- Modern browsers with ES6+ support required
- WebSocket support required for arena and casino games
- Server-Sent Events support required for Survivor Series live feed
- LocalStorage support for client-side preferences
- Recommended: Chrome, Firefox, Safari, Edge (latest versions)

---

## License

See [LICENSE.txt](LICENSE.txt) for details.
