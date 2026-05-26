# ReaperBot Web Interface

> A comprehensive browser-based interface for the Pets RPG system and Politics & War analytics tools, running as an embedded FastAPI server within the Discord bot.

---

## Table of Contents

- [🌐 Overview](#overview)
- [⚙️ Architecture](#architecture)
- [🔐 Authentication](#authentication)
- [📊 Pages Reference](#pages-reference)
  - [Dashboard](#dashboard)
  - [Pets Pages](#pets-pages)
  - [Casino Pages](#casino-pages)
  - [PnW Analytics Pages](#pnw-analytics-pages)
  - [Utility Pages](#utility-pages)
- [🔌 API Reference](#api-reference)
  - [Authentication APIs](#authentication-apis)
  - [Pets APIs](#pets-apis)
  - [Casino APIs](#casino-apis)
  - [PnW APIs](#pnw-apis)
  - [Utility APIs](#utility-apis)
- [🎨 Static Assets](#static-assets)
- [🚀 Deployment](#deployment)
- [🔧 Configuration](#configuration)

---

## Overview

The ReaperBot web interface is a full-featured browser application that runs as a FastAPI server embedded directly within the Discord bot process. It serves two primary systems:

- **Pets System** — A complete digital pet RPG with stats, combat, PvP, tournaments, casino games, and social features
- **PnW Analytics** — Politics & War intelligence tools including war tracking, revenue calculators, raid finders, treaty maps, and global news

The web server starts automatically when the bot launches (`python reaper.py`) and shares the same local SQLite databases as the Discord bot. There is no separate web server to manage, no Docker container required, and no database server to configure.

**Key Features:**

- Single-page application architecture with dynamic page loading
- Discord OAuth2 authentication for personal data access
- Real-time WebSocket updates for casino games
- Responsive design for desktop and mobile
- Cloudflare tunnel support for public access
- CDN caching for static assets

---

## Architecture

### Server Stack

- **Backend:** FastAPI (Python)
- **Frontend:** Vanilla JavaScript with HTML5
- **Database:** SQLite (shared with Discord bot)
- **Authentication:** Discord OAuth2
- **Real-time:** WebSocket for casino games
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

The web server has read-only access to the same SQLite databases used by the Discord bot:

- `Databases/Pets/pets.db` — Pet system data
- `Databases/PnW/GlobalNations.db` — Nation tracking
- `Databases/PnW/IRSWars.db` — War records
- `Databases/alerts.db` — User alerts
- `Databases/Tickets.db` — Support tickets

Write operations are performed through API endpoints that validate user permissions and data integrity.

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

- Sessions are stored server-side in memory
- Access tokens refresh automatically before expiration
- User profile data syncs on login and every 60 seconds
- No passwords are stored; authentication is entirely delegated to Discord
- Sessions persist across page refreshes

### Public vs Private Pages

- **Public pages:** Most PnW analytics pages (watch, nations, revenue, comparison, raids, weapons, news) are accessible without login
- **Private pages:** Pet system pages, alert management, and personal data require authentication

---

## Pages Reference

### Dashboard

**File:** `web/dashboard.html`

The main single-page application entry point. Features:

- Bot avatar and name display
- Sidebar navigation between all sections
- Dynamic page loading without full refreshes
- Responsive design for desktop and mobile
- User authentication status indicator

---

### Pets Pages

#### Adoption Flow

**Files:** `web/Pages/what_are_pets.html`, `web/Pages/petconnector.html`

New user onboarding for the pet system:

- **what_are_pets.html** — Introduction to the pet system with species, categories, and elements explanation
- **petconnector.html** — Pet creation wizard with species selection, category choice, element combination, and custom name input

Validation:
- Name checked for safe characters
- Duplicate pets per user prevented
- Species/category/element combinations validated

#### Pet Management

**File:** `web/Pages/mypet.html`

Displays the user's pet with full stat sheet:

- Computed stats (ATT, DEF, INT, DEX, HAP, ENE)
- XP bar and level
- Inventory items
- Equipped items
- Battle action labels (Attack, Defense, Charge)
- Rename pet functionality
- Custom battle action name configuration

**File:** `web/Pages/pets.html`

Global pet roster for game entry and social browsing:

- All registered pets in the system
- Search and filter functionality
- Pet profiles with basic stats
- Social viewing of other players' pets

**File:** `web/Pages/bazaar.html`

In-world marketplace for pet items and equipment:

- Item listings with prices
- Search and filter by category
- Purchase functionality
- User inventory display

**File:** `web/Pages/ability_tree.html`

Interactive skill tree for pet abilities:

- Stat mastery point spending
- Ability unlocking
- Prerequisite visualization
- Skill tree navigation

#### Activities

**File:** `web/Pages/arena.html`

PvP and PvE combat arena:

- Full battle system with skills and abilities
- Damage calculations
- Turn-based combat
- Matchmaking for PvP
- AI opponents for PvE

**File:** `web/Pages/colosseum.html`

Automated hourly tournament battles:

- Tournament registration
- Leaderboard display
- Historical results
- Automated battle scheduling

**File:** `web/Pages/dungeon.html`

Crawl-style dungeon with procedurally generated encounters:

- Multi-stage dungeon progression
- Random encounters
- Loot drops
- Survival mechanics

**File:** `web/Pages/survive.html`

Survivor Series battle royale:

- Multi-pet elimination rounds
- Procedural map generation
- Bracket system
- Tournament tracking

**File:** `web/Pages/tasks.html`

Daily and weekly task system:

- Task assignments per user
- Completion tracking
- Reward claiming
- Task refresh scheduling

**File:** `web/Pages/pet_stock.html`

Simulated resource stock market:

- Hourly price updates
- Buy/sell functionality
- Portfolio tracking
- Market trends

**File:** `web/Pages/game_info.html**

Reference page for live game data:

- Current resource prices
- Color bonuses
- Game state information
- Live data from database

**File:** `web/Pages/battle_config.html`

Pet battle settings configuration:

- Preferred battle settings
- Action priorities
- Equipment loadouts
- Strategy presets

#### Casino Games

**File:** `web/Pages/casino_lobby.html`

Casino lobby with live room state:

- 12 live game rooms
- Real-time WebSocket updates
- Room status (active, waiting, full)
- Player counts per room
- Seat availability indicators

**File:** `web/Pages/casino.html`

Solo slot machine:

- Multiple difficulty tiers
- Animated reels
- XP wagering
- Payout multipliers

**File:** `web/Pages/blackjack.html**

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
- Betting rounds

**File:** `web/Pages/craps.html**

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

**File:** `web/Pages/wheel.html**

Spin-the-wheel game:

- Variable XP prizes
- Spin animations
- Prize tiers

**File:** `web/Pages/scratch.html`

Instant-win scratch cards:

- Multiple card types
- Instant reveal
- Prize tiers

**File:** `web/Pages/keno.html**

Number-pick lottery:

- Number selection
- Draw results
- Payout calculations

**File:** `web/Pages/leaderboard.html`

Global rankings:

- Multiple categories (level, XP, battle wins, casino earnings)
- Leaderboard pagination
- Player search

#### Library

**File:** `web/Pages/library.html`

In-app documentation system:

- Markdown file serving from `web/Pages/Library/`
- Client-side rendering
- Game mechanics guides
- Strategy documents
- Doctrine articles

---

### PnW Analytics Pages

#### War Intelligence

**File:** `web/Pages/watch.html`

Primary war intelligence dashboard for Darkstar (alliance 10259):

- Date range selection
- Per-nation cost breakdown (units, infra, improvements, consumption)
- Net damage calculations
- Loot tracking (cash and resources with monetary values)
- Per-nation opponent breakdown
- Alliance-wide totals
- 2-minute caching per date range
- Revenue pre-warming at turn boundaries

**File:** `web/Pages/nations.html`

Global nation search and view:

- Search by nation name, leader name, or alliance
- Filterable results
- Score, city count, military units display
- War policy and projects
- Activity status
- Data from `GlobalNations.db` (no API calls)

**File:** `web/Pages/revenue.html`

Revenue calculator for nations and alliances:

- Per-turn and per-day revenue breakdown
- City-build engine calculations
- Improvements, projects, color bonuses
- Radiation levels and seasonal modifiers
- Current market prices
- Darkstar data from database, others from API

**File:** `web/Pages/rev_optimizer.html`

Economic optimization tool:

- City-by-city improvement analysis
- Ranked suggestions for net income maximization
- Project-level suggestions
- Current revenue vs projected gains
- Sorted by monetary output

**File:** `web/Pages/cost_calc.html`

Purchase cost calculator:

- Infrastructure, land, cities, projects
- Current market prices
- Discount calculations
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
- Darkstar data from database, others from API
- HTML report generation

**File:** `web/Pages/raids.html`

Raid target finder:

- War range search from `GlobalNations.db`
- Filters: inactive, weak military, beige status, minimum loot, excluded alliances, max defensive wars
- Projected loot from `holdings.db` (actual holdings)
- Revenue-based fallback for missing holdings
- Sorted by projected loot descending
- Beige alert management (set, refresh, delete)
- Discord DM notifications at ~2 hours and ~15 minutes before beige expiry

**File:** `web/Pages/weapons.html`

Weapon efficiency calculator:

- **Theory mode:** Infra level and pop density input, min/max/avg damage, cost-multiplier thresholds (1×-20×), damage chart
- **Targeted mode:** Nation/alliance input, city scoring by expected damage, Iron Dome (30% block) and VDS (25% block) accounting, alliance ranking by best-city missile damage
- Live resource prices from database

**File:** `web/Pages/news.html`

Global PnW event feed and leaderboards:

- Time periods: current week, previous week, current month, previous month, yearly archives
- Event feed: war declarations, endings, city builds, projects, alliance changes
- Filterable by event type, alliance, nation
- Alliance leaderboard: wars declared/won, loot, nukes/missiles used, cities built, projects bought, spending
- Nation leaderboard: same metrics at individual level
- Summary cards: world totals for period
- War cost drill-down from `IRSWars.db`
- Live search across `GlobalNations.db`
- Resource prices alongside loot values

---

### Utility Pages

**File:** `web/Pages/homepage.html`

Website homepage with navigation and overview.

**File:** `web/Pages/astrology.html`

Astrology system web interface (tarot and zodiac).

**File:** `web/Pages/commands.html`

Discord command reference.

**File:** `web/Pages/contact.html**

Contact information page.

**File:** `web/Pages/privacy.html**

Privacy policy.

**File:** `web/Pages/terms.html`

Terms of service.

**File:** `web/Pages/cache-management.html`

Cache management interface.

---

## API Reference

### Authentication APIs

#### `web/api/discord_auth.py`

Discord OAuth2 authentication flow:

- **`/auth/login`** — Initiates OAuth2 login, redirects to Discord
- **`/auth/callback`** — OAuth2 callback, exchanges code for access token
- **`/auth/logout`** — Clears user session
- **`/auth/user`** — Returns current authenticated user info
- **`/auth/refresh`** — Refreshes access token if expired

---

### Pets APIs

#### `web/api/pets_api.py`

Core pet data operations:

- **`/api/pets/my_pet`** — Get user's pet data
- **`/api/pets/adopt`** — Create new pet
- **`/api/pets/rename`** — Rename pet
- **`/api/pets/roster`** — Get global pet roster
- **`/api/pets/train`** — Send pet on training activity
- **`/api/pets/mission`** — Send pet on mission
- **`/api/pets/play`** — Send pet to play location
- **`/api/pets/quest`** — Start quest adventure
- **`/api/pets/ability_tree`** — Get ability tree data
- **`/api/pets/unlock_ability`** — Unlock ability
- **`/api/pets/battle_config`** — Get/set battle configuration

#### `web/api/bazaar_api.py`

Bazaar marketplace:

- **`/api/bazaar/items`** — Get bazaar listings
- **`/api/bazaar/buy`** — Purchase item
- **`/api/bazaar/sell`** — Sell item

#### `web/api/tasks_api.py`

Task system:

- **`/api/tasks/my_tasks`** — Get user's active tasks
- **`/api/tasks/complete`** — Complete task
- **`/api/tasks/claim`** — Claim task reward

#### `web/api/pet_stock_api.py`

Pet stock market:

- **`/api/stock/prices`** — Get current stock prices
- **`/api/stock/buy`** — Buy stock
- **`/api/stock/sell`** — Sell stock
- **`/api/stock/portfolio`** — Get user portfolio

#### `web/api/forge_api.py`

Item crafting/upgrading:

- **`/api/forge/craft`** — Craft item
- **`/api/forge/upgrade`** — Upgrade item

---

### Casino APIs

#### `web/api/casino_lobby_api.py`

Casino lobby management:

- **`/api/casino/lobby`** — Get lobby state (all rooms)
- **`/api/casino/join_room`** — Join a room
- **`/api/casino/leave_room`** — Leave a room

#### `web/api/casino_api.py`

General casino operations:

- **`/api/casino/start_game`** — Start a game
- **`/api/casino/place_bet`** — Place bet
- **`/api/casino/game_action`** — Perform game action

#### `web/api/blackjack_api.py`

Blackjack-specific:

- **`/api/blackjack/hit`** — Hit
- **`/api/blackjack/stand`** — Stand
- **`/api/blackjack/double`** — Double down
- **`/api/blackjack/split`** — Split

#### `web/api/holdem_api.py`

Texas Hold'em-specific:

- **`/api/holdem/fold`** — Fold
- **`/api/holdem/check`** — Check
- **`/api/holdem/call`** — Call
- **`/api/holdem/raise`** — Raise

#### `web/api/craps_api.py`

Craps-specific:

- **`/api/craps/roll`** — Roll dice
- **`/api/craps/place_bet`** — Place side bet

#### `web/api/races_api.py`

Pet racing:

- **`/api/races/bet`** — Place bet on racer
- **`/api/races/start`** — Start race

#### `web/api/minigames_api.py`

Mini-games:

- **`/api/minigames/start`** — Start mini-game
- **`/api/minigames/action`** — Game action

#### `web/api/powerball_api.py`

Powerball lottery:

- **`/api/powerball/buy_ticket`** — Buy lottery ticket
- **`/api/powerball/draw`** — Get draw results

#### `web/api/scratch_api.py`

Scratch cards:

- **`/api/scratch/buy`** — Buy scratch card
- **`/api/scratch/reveal`** — Reveal card

---

### PnW APIs

#### `web/api/watch_api.py`

Watch page war intelligence:

- **`/api/watch/data`** — Get war cost data for date range
- **`/api/watch/summary`** — Get alliance summary
- **`/api/watch/nations`** — Get nation breakdown

#### `web/api/pnw_api.py`

General PnW data:

- **`/api/pnw/nations`** — Search nations
- **`/api/pnw/alliance`** — Get alliance data
- **`/api/pnw/nation`** — Get nation details
- **`/api/pnw/projects`** — Get project data

#### `web/api/rev_optimizer_api.py`

Revenue optimization:

- **`/api/rev_optimizer/nation`** — Optimize single nation
- **`/api/rev_optimizer/alliance`** — Optimize entire alliance
- **`/api/rev_optimizer/suggestions`** — Get improvement suggestions

#### `web/api/raids_api.py`

Raid target finder:

- **`/api/raids/targets`** — Find raid targets
- **`/api/raids/loot`** — Calculate projected loot
- **`/api/raids/alerts`** — Manage beige alerts

#### `web/api/weapon_api.py`

Weapon efficiency:

- **`/api/weapon/theory`** — Theory mode calculations
- **`/api/weapon/targeted`** — Targeted mode calculations
- **`/api/weapon/chart`** — Generate damage chart

#### `web/api/news_api.py`

News and leaderboards:

- **`/api/news/events`** — Get event feed
- **`/api/news/alliance_leaderboard`** — Get alliance rankings
- **`/api/news/nation_leaderboard`** — Get nation rankings
- **`/api/news/summary`** — Get period summary
- **`/api/news/war_details`** — Get war cost breakdown

#### `web/api/world_api.py`

World data:

- **`/api/world/game_info`** — Get game state (date, radiation, etc.)
- **`/api/world/prices`** — Get resource prices
- **`/api/world/colors`** — Get color bonuses

---

### Utility APIs

#### `web/api/bot_info.py`

Bot information:

- **`/api/bot/info`** — Get bot status and info
- **`/api/bot/stats`** — Get bot statistics

#### `web/api/alerts_api.py`

User alerts:

- **`/api/alerts/beige`** — Get/set beige alerts
- **`/api/alerts/price`** — Get/set price alerts
- **`/api/alerts/check`** — Check alert status

#### `web/api/cache_api.py`

Cache management:

- **`/api/cache/stats`** — Get cache statistics
- **`api/cache/clear`** — Clear cache

#### `web/api/library.py`

Documentation library:

- **`/api/library/articles`** — Get article list
- **`/api/library/article`** — Get article content

#### `web/api/image_proxy.py`

Image proxy:

- **`/api/proxy/image`** — Proxy external images (CORS handling)

#### `web/api/docs.py`

API documentation:

- **`/docs`** — Interactive API documentation (Swagger UI)

---

## Static Assets

### Directory Structure

```
web/static/
├── Images/          # Static images (logos, backgrounds, avatars)
├── Emojis/          # Custom emoji assets
│   └── Watcher/     # PnW-related emojis
├── css/             # Stylesheets (scoped per page)
├── js/              # JavaScript files (per page functionality)
└── 404.html         # Custom 404 page
```

### Caching Strategy

- **Static assets:** Cached at CDN level for up to 1 hour
- **HTML pages:** Never cached
- **API responses:** Never cached (except where explicitly implemented)
- **Images:** Proxied through image proxy for CORS handling

### Emoji Assets

Custom emojis for PnW interface:

- War, tank, soldier, ship, missile, jet
- Infrastructure, improvement, defense
- Net damage, damages, cost, consumption
- Bomb, loot, and more

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

1. **Configure environment variables:**
   ```
   USE_CLOUDFLARE_TUNNEL=true
   CUSTOM_DOMAIN=your-domain.com
   CF_ACCOUNT_ID=your-account-id
   CF_TUNNEL_ID=your-tunnel-id
   CF_API_TOKEN=your-api-token
   CF_TUNNEL_TOKEN=your-tunnel-token
   CF_CREDENTIALS_FILE=path/to/credentials.json
   ```

2. **Start the bot:**
   ```bash
   python reaper.py
   ```

3. The Cloudflare tunnel starts automatically, making the site available at your configured domain.

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
| `USE_CLOUDFLARE_TUNNEL` | Auto-start tunnel | `false` |

**Cloudflare:**

| Variable | Purpose | Required |
|:---|:---|:---|
| `CF_ACCOUNT_ID` | Cloudflare account ID | For cache purge |
| `CF_TUNNEL_ID` | Tunnel ID | For named tunnel |
| `CF_API_TOKEN` | API token | For cache purge |
| `CF_TUNNEL_TOKEN` | Tunnel auth token | For tunnel |
| `CF_CREDENTIALS_FILE` | Credentials JSON path | For tunnel |

### Port Configuration

The web server runs on port **8080** by default. This is hardcoded in the bot startup sequence.

### CORS Configuration

The web server handles CORS internally. External images are proxied through the image proxy API to avoid CORS issues.

---

## Development

### Adding New Pages

1. Create HTML file in `web/Pages/`
2. Create corresponding API file in `web/api/` (if needed)
3. Add navigation entry in `web/dashboard.html`
4. Add route in FastAPI app (in `reaper.py` or web server initialization)

### Adding New APIs

1. Create API file in `web/api/`
2. Define FastAPI routes with proper decorators
3. Implement database queries or external API calls
4. Add error handling and validation
5. Update API documentation (Swagger UI auto-generates)

### Static Asset Management

- Images go in `web/static/Images/`
- CSS should be scoped per page in `web/static/css/`
- JavaScript should be per-page in `web/static/js/`
- Custom emojis go in `web/static/Emojis/`

---

## Troubleshooting

### Web Server Not Starting

- Check port 8080 is not in use
- Verify FastAPI dependencies are installed
- Check bot logs for startup errors

### Authentication Issues

- Verify Discord application has correct redirect URI
- Check `DISCORD_TOKEN` is valid
- Ensure OAuth2 scopes are properly configured

### Cloudflare Tunnel Issues

- Verify tunnel credentials are valid
- Check `CF_TUNNEL_ID` matches your tunnel
- Ensure domain DNS is configured correctly
- Check Cloudflare account permissions

### Database Access Issues

- Verify database files exist in `Databases/`
- Check file permissions
- Ensure bot has write access to database directory

---

## Security Considerations

- All authentication is delegated to Discord OAuth2
- No passwords are stored
- Sessions are server-side only
- Access tokens are automatically refreshed
- Personal data requires authentication
- Public pages have no sensitive data exposure
- API endpoints validate user permissions
- Rate limiting is implemented where appropriate

---

## Performance

- Static assets cached at CDN level
- Database queries optimized with indexes
- WebSocket for real-time updates (casino)
- Caching for expensive calculations (war costs, revenue)
- Lazy loading for large datasets
- Pagination for leaderboards and feeds

---

## Browser Support

- Modern browsers with ES6+ support
- WebSocket support (for casino games)
- LocalStorage support (for session persistence)
- Recommended: Chrome, Firefox, Safari, Edge (latest versions)

---

## License

See [LICENSE.txt](LICENSE.txt) for details.
