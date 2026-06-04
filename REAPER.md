# Reaper Bot

> A self-hosted Discord bot that serves as a comprehensive Politics & War intelligence platform, a full pet RPG system, a support ticket desk, a translator, an astrology system, and an entertainment hub — all running locally with an embedded web interface.

---

## Table of Contents

- [Overview](#overview)
- [Configuration and Environment](#configuration-and-environment)
- [Installation and Startup](#installation-and-startup)
- [Architecture](#architecture)
- [Cog Reference](#cog-reference)
  - [Admin](#admin)
  - [Info / Utility](#info--utility)
  - [EA — Economic Affairs](#ea--economic-affairs)
  - [FA — Foreign Affairs](#fa--foreign-affairs)
  - [IA — Internal Affairs](#ia--internal-affairs)
  - [MA — Military Affairs](#ma--military-affairs)
  - [Other — PnW Miscellaneous](#other--pnw-miscellaneous)
  - [Tickets](#tickets)
  - [Astrology](#astrology)
  - [Fun](#fun)
  - [Casino (PnWCasino)](#casino-pnwcasino)
- [Background Tasks](#background-tasks)
- [Database Structure](#database-structure)
- [Dependencies](#dependencies)

---

## Overview

Reaper Bot is a self-hosted Discord bot built in Python that runs entirely on your local machine. All data stays local — databases, API keys, user data. Nothing is stored externally.

The bot has two integrated sides:

- **Discord side** — Handles slash and hybrid commands in your server for PnW intelligence, pet games, tickets, translation, astrology, and entertainment.
- **Web side** — Runs a FastAPI server embedded inside the bot process at port 8080, serving the full browser-based interface for the Pets system and PnW analytics tools.

Both sides start from a single command (`python reaper.py`) and share the same local SQLite databases. There is no separate web server to manage, no Docker container, and no database server.

The bot is designed for the **Darkstar alliance** (PnW alliance ID 10259) but all PnW tools work for any alliance or nation. The pet system is entirely self-contained.

**What Reaper does NOT do:** Reaper does not collect live PnW data. All real-time data collection (nation subscriptions, war tracking, bank records, trade tracking, etc.) is handled by the **separate PnWHarvester process** (`python harvester.py`). Reaper is read-only against the harvester's databases.

---

## Configuration and Environment

All configuration lives in a single file: `Systems/Functions/.env`

The bot reads this file on startup. There is no fallback to a root-level `.env`. If the file is missing or `DISCORD_TOKEN` is absent, the bot will not start.

### Required

| Variable | Purpose |
|:---|:---|
| `DISCORD_TOKEN` | Bot authentication token from the Discord Developer Portal. Required to start. |

### Optional — Bot Behavior

| Variable | Purpose | Default |
|:---|:---|:---|
| `COMMAND_PREFIX` | Prefix for legacy text commands | `!` |
| `ADMIN_USER_ID` | Discord user ID that gates admin-only commands | `0` (disabled) |
| `RESULTS_CHANNEL_ID` | Channel ID where game results are posted | `0` (disabled) |
| `DATA_DIR` | Base directory for data storage | Current working directory |
| `SESSION_SECRET` | Secret key for web session signing. Set this persistently or all sessions invalidate on restart. | Random (regenerated each restart if unset) |

### Optional — AI Features

| Variable | Purpose |
|:---|:---|
| `GROQ_API_KEY` | Groq (Llama 3.1). Powers Tarot readings, roasts, compliments, and the Zombie survival AI story system. |
| `GEMINI_API_KEY` | Google Gemini. Available as an additional AI provider. |

### Optional — Politics & War

| Variable | Purpose |
|:---|:---|
| `PANDW_API_KEY` | PnW API v2 key |
| `PANDW_API_V3_KEY` | PnW API v3 GraphQL key. Used by all PnW commands and the Harvester. |
| `PANDW_BOT_KEY` | PnW bot key |

### Optional — Other APIs

| Variable | Purpose |
|:---|:---|
| `HORSCOPE_API` | RapidAPI key for horoscope fallback in the Astrology system |
| `GIPHY_KEY` | Giphy API key for GIF responses in roast/compliment |
| `PIXABAY_KEY` | Pixabay API key for image responses in roast/compliment |

### Optional — Web & Cloudflare

| Variable | Purpose | Default |
|:---|:---|:---|
| `CUSTOM_DOMAIN` | Public-facing domain for the web interface | `https://reaper.qzz.io` |
| `USE_CLOUDFLARE_TUNNEL` | Set to `true` to auto-start Cloudflare tunnel on bot startup | `false` |
| `CF_ACCOUNT_ID` | Cloudflare account ID (required for CDN cache purging) | — |
| `CF_TUNNEL_ID` | Cloudflare tunnel ID | — |
| `CF_API_TOKEN` | Cloudflare API token | — |
| `CF_TUNNEL_TOKEN` | Cloudflare tunnel auth token | — |
| `CF_CREDENTIALS_FILE` | Path to Cloudflare tunnel credentials JSON | — |

---

## Installation and Startup

### Prerequisites

- Python 3.12 (tested; other versions may work)
- Node.js and npm (for web frontend dependencies: Bootstrap, Three.js, GSAP)

### Starting the Bot

```bash
python reaper.py
```

The startup sequence:

1. **venv self-relaunch** — If not already running inside the project `.venv`, re-execs using the `.venv` Python so all packages are available.
2. **Dependency check** — Verifies Python venv and Node.js `node_modules`. If missing or invalid, installs them automatically from `requirements.txt` and `package.json`.
3. **Bot creation** — Creates `discord.py` bot with intents: `message_content`, `members`, `guilds`. Command prefix: `r.`
4. **Cog loading** (`setup_hook`) — Loads all cog sets:
   - Admin: `Systems.admin`, `Systems.info`
   - Mythical: `Systems.Astrology.signs`, `Systems.Astrology.reading`
   - Fun: `Systems.Fun.zombie`, `Systems.Fun.goodevil`, `Systems.Fun.fun_system`, `Systems.Fun.compete`, `Systems.Fun.troll`
   - PnW: `Systems.PnW.pnwhopper` (which loads all EA/FA/IA/MA/Other sub-cogs internally)
   - Tickets: `Systems.Tickets.tickets`
   - Casino: `Systems.PnWCasino.casino_cog`
5. **Background tasks start** — Beige notification loop and periodic user sync launch as asyncio tasks.
6. **Discord connection** — Bot connects to Discord gateway.
7. **Command sync** (`on_ready`) — Syncs application command tree with Discord.
8. **Web server start** (`on_ready`) — Starts embedded FastAPI/Uvicorn server on port 8080. Waits up to 30 seconds for it to be ready.
9. **Cloudflare tunnel** (`on_ready`) — If `USE_CLOUDFLARE_TUNNEL=true`, starts the Cloudflare tunnel and begins monitoring it.

### Logs

- `reaper_startup.log` — Written during dependency check and initialization (overwritten each restart).
- `reaper_bot.log` — Switches to this file once the bot is ready (overwritten each restart).

### Manual Dependency Install

```bash
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
npm install
```

---

## Architecture

### PnW Data Pipeline

Reaper reads PnW data from local SQLite databases maintained by the separate **PnWHarvester** process (`python harvester.py`). Reaper **never writes** to `GlobalNations.db`, `IRSWars.db`, `GlobalWars.db`, or the news databases — those are the harvester's domain.

This separation means:
- Bot commands respond immediately from local DB (no API latency)
- Data stays current even when the bot is offline
- API rate limits are managed centrally by the harvester

### Web Server

`Systems/Functions/web_server.py` — FastAPI application served by Uvicorn, running as a background asyncio task within the same process as the Discord bot. The web server:
- Serves HTML/CSS/JS pages from `web/Pages/`, `web/css/`, `web/js/`
- Serves static assets from `web/static/`
- Exposes REST/WebSocket API endpoints for the browser UI
- Shares the bot instance for Discord DMs and status info

### Command Prefix

The bot command prefix is `r.` (not `!`). Slash commands (`/`) are the primary interface.

---

## Cog Reference

### Admin

**File:** `Systems/admin.py` — loaded as `Systems.admin`

Administrative commands gated by specific user IDs hardcoded in `config.py`.

| Command | Description | Access |
|:---|:---|:---|
| `/shutdown` | Gracefully shut down the bot | `ARIES_USER_ID` only |
| `/usage` | Paginated view of bot statistics: servers, users with data files, and installed users. Supports remove/leave actions. | `ADMIN_USER_ID` only |
| `/servers` | Lists all servers the bot is currently in with member counts | `ADMIN_USER_ID` only |

---

### Info / Utility

**File:** `Systems/info.py` — loaded as `Systems.info`

General-purpose utility commands available to all users.

| Command | Description |
|:---|:---|
| `/leadership` | Posts the Alliance Leadership embed to the current channel showing the ICS structure with role mentions |
| `/webpage` | Sends the web interface URL as a masked link |

---

### EA — Economic Affairs

**File:** `Systems/PnW/pnwhopper.py` loads the following from `Systems/PnW/EA/`:

#### Colors (`colors.py`)

| Command | Description |
|:---|:---|
| `/turn_bonuses` | Shows turn bonuses for all 19 PnW color blocs, sorted highest to lowest with color emoji indicators |
| `/game_info` | Shows current PnW game state: in-game date, top 20% city average, global radiation, per-continent radiation breakdown with attached pie chart |

#### Resource Stocks (`stocks.py`)

| Command | Description |
|:---|:---|
| `/stocks [graph_type]` | Current PnW market prices for all 12 resources with 2-hour price change indicators and a 30-day trend graph. `graph_type`: All Resources, Raw Resources, Manufactured Resources, Food, Credit |
| `/history` | Opens a modal to select a custom date range and generates a historical price chart for that window |

#### Resource Stats (`resource.py`)

| Command | Description |
|:---|:---|
| `/game_resources [start] [finish] [types]` | Plots historical resource and money holdings across the entire PnW game world over a selected time window. Time supports formats like `7d`, `2w`, `1m`, or `YYYY-MM-DD`. Types: All, Manufactured, Raws, Food, Money, or comma-separated individual resources. |

#### Revenue (`rev.py`)

| Command | Description |
|:---|:---|
| `/revenue <query_type> <query_value> [alliance_color] [tax_rate]` | Full per-turn and per-day revenue breakdown for a nation or alliance. Shows gross income, color bonus, military upkeep, improvement upkeep, power upkeep, resource upkeep, net cash per turn/day, per-resource production with monetary value, and total monetary net. For Darkstar nations reads from `GlobalNations.db`; other alliances fall back to the PnW API. Optional `tax_rate` override (0–100) and `alliance_color` for alliance tax calculations. |

#### Revenue Optimizer (`rev_optimizer.py`)

| Command | Description |
|:---|:---|
| `/rev_optimizer <query_type> <query_value> [tax_rate]` | Full economic optimization analysis for a nation or every nation in an alliance. Generates ranked improvement suggestions (civil, resource, rebuild), infrastructure targets with ROI gating, land suggestions, and project recommendations. Results sorted by daily monetary gain. |

#### Resource Price Alerts (`rss_alerts.py`)

| Command | Description |
|:---|:---|
| `/rss_alert_set <resource> <price_type> <direction> <threshold>` | Set a one-shot price alert for any of the 12 PnW resources. `price_type`: Buy or Sell. `direction`: At/Above (≥) or At/Below (≤). Fires once then is deleted. Sends a Discord DM when triggered. |
| `/rss_alert_remove <resource> <price_type> <direction>` | Remove a specific active alert before it fires |
| `/rss_alert_list` | List all your currently active resource price alerts (ephemeral) |

---

### FA — Foreign Affairs

**File:** `Systems/PnW/pnwhopper.py` loads the following from `Systems/PnW/FA/`:

#### Treaties (`treaties.py`)

| Command | Description |
|:---|:---|
| `/treaties <alliance>` | Full treaty web for any alliance: rich Discord embed showing treaty partners with a generated treaty web image (concentric rings by treaty strength). Includes a Refresh button. |

#### Universe (`universe.py`)

| Command | Description |
|:---|:---|
| `/treaty_universe <alliance>` (aliases: `/treaty_map`, `/universe`) | Generates a link to the interactive Treaty Universe web page centered on the specified alliance |

---

### IA — Internal Affairs

**File:** `Systems/PnW/pnwhopper.py` loads the following from `Systems/PnW/IA/`:

#### Alliance (`alliance.py`)

| Command | Description |
|:---|:---|
| `/alliance <alliance>` | Main alliance overview with five interactive views navigable via buttons: **Alliance Totals** (nation counts, score, cities, military), **Military** (units, max capacity, gaps, daily production), **Improvements** (totals per improvement type), **Project Totals** (all 40+ projects), and **Refresh**. For Darkstar reads from `GlobalNations.db`; others use PnW API. |

#### Costs (`costs.py`)

| Command | Description |
|:---|:---|
| `/costs <nation> [infrastructure] [land] [cities] [project]` | Calculates the exact cost of infrastructure, land, new cities, and national projects for any nation, applying all relevant discounts (Center for Civil Engineering, Advanced Engineering Corps, Arable Land Agency, Urban Planning, etc.). Uses live market prices. |

#### Show (`show.py`)

| Command | Description |
|:---|:---|
| `/show <query>` | Comprehensive nation profile: identity, alliance, military units, war policy, all projects, improvement totals, score, cities, color, beige/vacation status, activity, and achievement badges. Accepts nation name, leader name, nation ID, or PnW URL. |

#### Audit (`audit.py`)

| Command | Description |
|:---|:---|
| `/audit <alliance>` | Audits an alliance for compliance issues with views for: **Inactives** (7+ day inactive nations), **Color** (color distribution), and **MMR Build** (Minimum Military Requirement build compliance per city count tier). |

#### Guide (`guide.py`)

| Command | Description |
|:---|:---|
| `/snipe_guide` | Sends the complete 10-step beige sniping and raiding guide |
| `/snipe_setup` | Sends only the setup portion of the snipe guide (steps 1–4) |
| `/snipe_execute` | Sends only the execution portion of the snipe guide (steps 5–10) |
| `/war_guide` | Sends a structured guide on PnW war mechanics covering Ground Supremacy, Air Superiority, Naval Blockade/Supremacy, Missiles, Nukes, Fortification, Peace, and Key Strategy |

---

### MA — Military Affairs

**File:** `Systems/PnW/pnwhopper.py` loads the following from `Systems/PnW/MA/`:

#### Wars (`wars.py`)

| Command | Description |
|:---|:---|
| `/wars <attacker_alliances> <defender_alliances> [start_date] [end_date]` | Full cost breakdown for a war matchup between two sides. Paginated views: **Summary** (totals), **Military** (unit losses), **Destruction** (infra/improvements), **Loot** (loot gained/lost). |

#### War Costs BD (`war_costs_bd.py`)

| Command | Description |
|:---|:---|
| `/wars_cost_bd <alliance> [start_date] [end_date]` | Per-nation war cost breakdown for an alliance over a selected time window. Shows unit cost, infra cost, bomb cost, consumption, and gross cost per nation. |

#### War Net BD (`war_net_bd.py`)

| Command | Description |
|:---|:---|
| `/wars_net_bd <alliance> [start_date] [end_date]` | Identical structure to `/wars_cost_bd` but calculates net damage (damage dealt minus cost) per nation over the time window. |

#### War Simulation (`war_sim.py`)

| Command | Description |
|:---|:---|
| `/war <attacker> <defender> <war_type>` | Simulates a full turn-by-turn war between two nations using full game mechanics (MAPs, resistance, ground control, air superiority, naval blockade, unit purchases). Paginated embed with a summary page and one page per turn. `war_type`: Ordinary, Attrition, Raid. |

#### Compare Wars (`compare_wars.py`)

| Command | Description |
|:---|:---|
| `/compare_wars <nation1> <nation2> [time]` | Head-to-head war performance comparison between two Darkstar member nations. Three-page paginated embed: Summary (cost, damage, net, loot, verdict), Nation 1 Breakdown, Nation 2 Breakdown. `time`: 1d, 3d, 1w, 2w, 1m, 3m, 6m, 1y, All Time. |

#### Rankings (`rankings.py`)

| Command | Description |
|:---|:---|
| `/rankings <ranking_type> [time]` | Top 25 Darkstar nations ranked by a selected war statistic. Types: War Cost, War Net, Damages, Bomb Cost, Loot, Soldiers Lost/Killed, Tanks Lost/Killed, Aircraft Lost/Killed, Ships Lost/Killed, Peace, Wins, Losses. `time`: 1d, 3d, 1w, 2w, 1m, 3m, 6m, 1y, All Time, or custom (e.g. `2d`, `1w`). |

#### Raids (`raids.py`)

| Command | Description |
|:---|:---|
| `/raids [nation] [active] [weak] [min_loot] [beige] [targets] [display] [exclude_alliances] [active_wars]` | Raid target finder. Searches `GlobalNations.db` for nations within war range. Filters: inactive-only, weak military, minimum loot, beige targets, excluded alliances (comma-separated with autocomplete), and max active defensive wars (0, 1, or 2). Projected loot uses live holdings data from `HoldingsDB`. Results sorted by projected loot descending. `display`: Message or PDF report. |

#### Destroy (`destroy.py`)

| Command | Description |
|:---|:---|
| `/destroy <target> <attacker_alliances>` | Finds optimal attacker groups from one or more alliances to coordinate a strike on a target nation. Scores potential attackers by war range and military strength. |

#### Finder (`finder.py`)

| Command | Description |
|:---|:---|
| `/treasures [sort] [active] [score]` | Find all available treasures in the game with sorting (spawn date, bonus, activity) and optional filtering by inactivity threshold and war range score. Paginated. |
| `/treasure_trades [score] [canceled] [limit]` | Find recent treasure trades. `canceled`: On (show only declined/canceled trades) or Off (all trades). Optional war range filter via `score`. |
| `/bounty [bounty_type] [price] [active] [sort] [score]` | Find active bounties. `bounty_type`: Any, Ordinary, Attrition, Raid, Nuclear. `price`: >$1M through >$50M. `active`: 7/14/28+ days inactive. `sort`: price or activity. Optional war range filter via `score`. |

#### Offshore (`offshore.py`)

| Command | Description |
|:---|:---|
| `/offshore <alliance> [time]` | Scans `bankrecs.db` for alliance members receiving funds from external sources (outside their own alliance bank). Excludes war bank loot (cross-referenced against `IRSWars.db`). Shows per-member net balance, top suspected source alliances, and a resource breakdown. `time`: e.g. `7d`, `2w` (max 14 days). |

#### Units (`units.py`)

| Command | Description |
|:---|:---|
| `/units` | Interactive military unit cost calculator with live resource prices and a Recalculate button |

#### Weapon Efficiency (`weapon_eff.py`)

| Command | Description |
|:---|:---|
| `/weapon_eff` | Missile and nuclear weapon efficiency calculator. **Theory mode**: given infrastructure level and population density, shows min/max/avg damage, cost-multiplier thresholds, and a damage chart. **Targeted mode**: given a specific nation or alliance, scores every city by expected damage value accounting for Iron Dome (30% block) and Vital Defense System (25% block). |

#### Spy (`spy.py`)

| Command | Description |
|:---|:---|
| `/spy_chance <attacker> <defender> <espionage_type> [desired_outcome]` | Calculates espionage operation odds and optimal spy allocation. `espionage_type`: Gather Intelligence, Assassinate Spies, Terrorize Civilians, Sabotage Soldiers/Tanks/Aircraft/Ships/Missiles/Nukes. `desired_outcome`: Least Cost & Best Odds (target 99%) or Most Destruction (target 95%, with potential damage simulation). Shows spy counts, war policies, satellite projects, and per-safety-level odds. |

---

### Other — PnW Miscellaneous

**File:** `Systems/PnW/pnwhopper.py` loads the following from `Systems/PnW/Other/`:

#### Baseball (`baseball.py`)

| Command | Description |
|:---|:---|
| `/baseball <nation>` | Looks up the baseball team for any nation with full team stats and a star rating |

#### Loot (`loot.py`)

**Message listener (no slash command)** — Automatically parses messages when the bot is @mentioned:

- If the message contains intelligence report text (`gathered intelligence`, `spies discovered`): calculates projected loot under 6 different policy combinations (Pirate, APE, Moneybags permutations) and posts an embed.
- If the message contains actual loot text (`looted` + `defeated`/`crushed`/`surrender`): calculates the monetary value of all looted resources at current market prices and posts a loot summary embed.

Both use cached resource prices from `reaper.db` — no API call.

#### Activity (`activity.py`)

| Command | Description |
|:---|:---|
| `/activity [type] [time]` | PnW world activity statistics with a Matplotlib line chart. `type`: All, New, 1 Day, 2 Days, 3 Days, 1 Week, 1 Month. `time`: supports formats like `30d`, `4w`, `1m`. Fetches data from the PnW API. |

#### Theme (`theme.py`)

| Command | Description |
|:---|:---|
| `/theme emoji set <type> <name> <emoji>` | Assign a custom emoji to a nation or alliance for autocomplete dropdown display. `type`: nation or alliance. Persisted to `Systems/Data/nation_emojis.json` and `alliance_emojis.json`. |
| `/theme emoji remove <type> <name>` | Revert a nation or alliance to its default emoji |
| `/theme emoji list` | Show all custom nation and alliance emoji assignments (ephemeral, paginated) |
| `/theme emoji reload` | Reload emoji stores from disk |

---

### Tickets

**File:** `Systems/Tickets/tickets.py` — loaded as `Systems.Tickets.tickets`

Purpose-built membership and embassy ticket system for the Darkstar Discord server.

**How it works:**

1. `/info` posts a welcome embed in the designated info channel (`#1445703670057537700`) with two persistent buttons.
2. **Membership** button: opens a modal asking for a nation name or ID → bot looks up the nation from PnW API → creates a private ticket channel named `c{cities}-{nation-name}` → posts the full `/show` nation profile inside it.
3. **Embassy** button: opens a modal asking for an alliance name or ID → bot looks up the alliance → creates a private channel named after the alliance (using acronym if name is long) → posts the full `/alliance` overview inside it with the alliance's PnW color applied to the channel.

Only the applicant, the bot, and configured ticket roles can see each ticket channel.

Persistent views are registered with `bot.add_view()` and restored automatically on restart.

| Command | Description |
|:---|:---|
| `/info` | Posts the welcome embed with Membership and Embassy buttons in the designated info channel |
| `/verify <action>` | Run inside a ticket channel to Accept or Reject. **Accept → Membership**: assigns Member role, moves channel to accepted members category. **Accept → Embassy**: creates/finds a Discord role named after the alliance, assigns that role + Diplomat role, moves channel to accepted embassies category. **Reject**: notifies applicant, waits 5 seconds, deletes channel and DB record. |
| `/delete_ticket <ticket>` | Deletes any ticket by name (autocomplete from all tickets in DB). Deletes the Discord channel if it exists and removes the DB record. |
| `/resort_members` | Re-queries the PnW API for every open membership ticket and renames channels to `c{current_cities}-{nation-name}`. |
| `/ticket_role add <role> [label]` | Adds a Discord role that will automatically get read/write access on all new ticket channels. |
| `/ticket_role remove <role>` | Removes a role from the ticket access list. |
| `/ticket_role list` | Shows all configured ticket roles with their labels. |

**Welcome message:** When a new member joins the server, the bot automatically sends a welcome embed in the info channel mentioning the new member.

**Database:** `Databases/Tickets.db` — stores ticket records with channel ID, guild ID, applicant Discord ID, type, status, subject (nation/alliance name), nation/alliance ID, city count, color hex, timestamps.

---

### Astrology

**Files:** `Systems/Astrology/reading.py`, `Systems/Astrology/signs.py` — loaded as `Systems.Astrology.reading`, `Systems.Astrology.signs`

| Command | Description |
|:---|:---|
| `/tarot [spread]` | Professional tarot card reading. Spread options: **1 Card** (single draw with direct message), **3 Card Past/Present/Future**, **5 Card Traditional** (core theme, obstacle, advice, hidden influence, likely outcome). Cards are randomly drawn from all 78, randomly assigned upright or reversed orientation. Card images loaded from `Systems/Astrology/Tarot/cards/`, resized, rotated if reversed, and stitched into a composite PNG. Paginated embed: **Cards** view (image + per-card breakdown with position, name, orientation, meanings, fortune line) and **Summary** view (AI-generated narrative from Groq). If Groq is unavailable, all card details still show. |
| `/zodiac <month> <day> <year>` | Triple-zodiac personality profile from a birthday. Three-page interactive embed: **Western** (sun sign with element, modality, planet, traits, lucky numbers/colors/gems, compatibility, daily horoscope from Aztro API with Groq/local fallback), **Eastern** (Chinese zodiac animal based on exact Chinese New Year dates 1900–2027, with polarity, element, trine, lucky info, compatibility), **Spirit Animal** (Primal Astrology combination of Western + Chinese — 144 possible unique animals). All zodiac data from local JSON files in `Systems/Astrology/Zodiac/`. |

---

### Fun

**Files:** `Systems/Fun/` — loaded as individual cog modules

#### RPS (`compete.py`)

| Command | Description |
|:---|:---|
| `/rps [rival] [rounds] [theme] [ai_opponent]` | Rock Paper Scissors. Themes: Traditional (Rock/Paper/Scissors), Fantasy (Knight/Archer/Necromancer), War (Tank/Jet/Ship). Rounds: 1, 3, or 5. If no rival mentioned, a Join Game button appears. `ai_opponent: True` plays against the bot which uses move history to counter. |

#### Dice & Cards (`fun_system.py`)

| Command | Description |
|:---|:---|
| `/dice [count] [type]` | Rolls 1–5 dice. D6 (with color options: Red, Orange, Blue, Yellow, Pink, Green, Purple) or D20. Each result shown with its custom server emoji. |
| `/card [count]` | Draws 1–5 random playing cards from a full 54-card deck (52 standard + 2 jokers). Each card shown with its custom server emoji. |

#### Range (`fun_system.py`)

| Command | Description |
|:---|:---|
| `/range [rounds]` | Sniper training reaction game. Available rounds: 5, 15, 25, 50, 100. After a 3-second countdown, each round shows 5 buttons — one target (🎯) among misses (🔴). Player has 1.2 seconds per round. Wrong button or timeout = miss. Results show accuracy, visual bar, rank from Blindfolded Intern to Deliverer of Death, and personal best. Stats persisted across sessions. |

#### Tic Tac Toe (`fun_system.py`)

| Command | Description |
|:---|:---|
| `/tictactoe [rival] [ai] [series] [difficulty]` | Tic Tac Toe with optional AI opponent. Difficulties: Novice (random), Competent (checks win/block before random), Expert (minimax, optimal). Series: best of 1, 3, or 5. Both players choose their emoji via modal. Displays a live 3×3 button grid. |

#### Roast & Compliment (`goodevil.py`)

| Command | Description |
|:---|:---|
| `/roast [target] [intensity]` | AI-generated roast via Groq (Llama 3.1). 7 intensity levels: Mild → Explicit. Fetches target's Discord bio for personalisation. 2–3 sentence limit. Fallback line if Groq unavailable. |
| `/compliment [target] [intensity]` | Identical structure to `/roast` but generates praise. Same 7 intensity levels and Groq API with fallback. |

#### Random Image (`fun_system.py`)

| Command | Description |
|:---|:---|
| `/random [type]` | Fetches and posts a random image. **JPG**: random photo from Pixabay (`PIXABAY_KEY`). **GIF**: random GIF from Giphy (`GIPHY_KEY`). Downloaded server-side and posted as a file attachment. |

#### Walk-Through Adventure (`fun_system.py`)

| Command | Description |
|:---|:---|
| `/walktru` | Text-based adventure with 6 storylines, each with its own mechanics: Horror Sanitarium (Fear 0–100), 1920s Gangster (Heat 0–100), Knight's Quest (Honor 0–150), Robot Factory Escape (Power 0–100), Western Frontier (Health 0–100), Wizard's Apprentice (Mana 0–150). Each stage has numbered choice buttons with success probabilities. Mechanic value changes on success/failure with a visual progress bar. |

#### Zombie Survival (`zombie.py`)

| Command | Description |
|:---|:---|
| `/zombie_survival` | Starts or continues an ongoing AI-driven zombie survival game in a channel. Each round the Groq AI generates a story event with exactly 4 choices and base success probabilities. Players vote via A/B/C/D buttons. Resolves every 2 hours. Success odds = base + vote multiplier (2–5% per voter on winning choice) + random luck (±15%). Survivor stats: HP, stamina, morale, revolver ammo, rifle ammo. Deceased survivors marked with strikethrough. Game-over on full wipe. |
| `/zombie_character` | Shows your personal survivor card (HP, stamina, morale, ammo, melee weapon). Ephemeral. |

#### Troll (`troll.py`)

Passive troll functionality (message reactions/responses).

---

### Casino (PnWCasino)

**File:** `Systems/PnWCasino/casino_cog.py` — loaded as `Systems.PnWCasino.casino_cog`

The PnWCasino cog bridges Discord and the web-based casino. Casino games (Blackjack, Hold'em, Craps, Races, Minigames, Slots, Powerball, Wheel, Scratch, Keno) run primarily through the browser interface at the configured domain. The Discord cog handles any Discord-side interactions. See `Systems/PnWCasino/README.md` for details.

---

## Background Tasks

Two asyncio tasks start in `setup_hook` before the bot connects to Discord:

### Beige Notification Loop

**Runs every 2 minutes.**

Two-stage alert system reading from `Databases/alerts.db`:

- **Early-exit drain** — Checks `beige_early_exit_queue` written by the PnWHarvester when it detects a nation left beige early via `nation/update` subscription. Sends immediate Discord DMs for each queued exit.
- **Stage 1 alert** — When a beige nation has between 15 minutes and 2h 15m remaining: sends a "⏰ Beige Warning" DM with current military, projected loot (recalculated from live `HoldingsDB` at current market prices), and nation info. Marks as warned.
- **Stage 2 alert** — When ≤15 minutes remaining: sends a "🚨 Beige Expiring" DM and deletes the alert.

Beige turns are read from `GlobalNations.db` (kept live by the harvester). Projected loot recalculation applies the full loot formula (Pirate ×1.4, APE ×1.1, defender war policy modifier) against live holdings at current sell prices.

### Periodic User Sync

**Runs every 5 minutes.**

Fetches Discord users with stale profile data (last synced > 1 day ago, up to 10 per cycle) and updates their avatar, username, and display name in the bot's user data store.

---

## Database Structure

All databases live under `Databases/`. The bot creates directories automatically on first run.

### Databases/Pets/

| File | Purpose |
|:---|:---|
| `pets.db` | All pet profiles, user relationships, bazaar, pet settings |
| `Tasks.db` | Daily/weekly task assignments, completion state, reward tracking |
| `absorb.db` | PnW war absorb tracking (locked nation IDs, absorbed unit kill totals) |
| `colosseum.db` | Hourly colosseum tournament results, pending XP/keys/potions, member roster |
| `dungeon.db` | Active and completed dungeon crawl session state |
| `powerball.db` | Powerball lottery tickets and draw history |
| `survivorseries.db` | Survivor Series game state (lobby, rounds, participants, feed, map) |

### Databases/PnW/

**Read-only by Reaper.** Maintained by PnWHarvester.

| File | Purpose |
|:---|:---|
| `GlobalNations.db` | All PnW nations with stats, military, projects, holdings, cities |
| `IRSWars.db` | Darkstar (alliance 10259) war records with full attack detail |
| `GlobalWars.db` | All PnW wars (game-wide) |
| `bankrecs.db` | All bank transfer records received via harvester subscription |
| `WeeklyNews.db` | Current week news events and alliance/nation stats |
| `MonthlyNews.db` | Current month news events and stats |
| `WeeklyNews_prev.db` | Previous week's data (archived on rollover) |
| `MonthlyNews_prev.db` | Previous month's data (archived on rollover) |
| `YearlyNews{YYYY}.db` | Full calendar year news events and stats |
| `Treaties.db` | Active and historical alliance treaties |

### Databases/ (root)

| File | Purpose |
|:---|:---|
| `reaper.db` | Resource market prices (updated by harvester every 15 min), color bonuses, game info, radiation levels, user settings (theme, linked nation, privacy preferences), session store for web auth |
| `Tickets.db` | Support ticket records: channel ID, applicant, type, status, nation/alliance IDs, timestamps |
| `alerts.db` | Beige alerts and resource price alerts; also holds the `beige_early_exit_queue` (harvester → bot bridge) |
| `zombie.db` | Zombie survival game state, player status, story progression, AI narrative history |
| `sessions.db` | Web session storage (alternative/overflow session store) |
| `MyNations.db` | Nation goals, build plans, and snapshots for the My Nation web page |

---

## Dependencies

**Python (`requirements.txt`):**

| Package | Purpose |
|:---|:---|
| `discord.py==2.3.2` | Discord bot framework |
| `fastapi`, `uvicorn[standard]`, `starlette` | Web server |
| `websockets`, `aiohttp`, `httpx`, `requests` | HTTP and WebSocket clients |
| `python-dotenv` | `.env` loading |
| `pydantic`, `itsdangerous`, `python-multipart` | Request validation and session signing |
| `groq` | Groq AI API (Llama 3.1 — tarot, roasts, zombie survival) |
| `pandas`, `numpy`, `lttb` | Data processing and downsampling |
| `matplotlib`, `plotly`, `kaleido==0.2.1` | Chart and graph generation |
| `Pillow` | Image processing (tarot cards, treaty maps, game_info chart) |
| `networkx` | Treaty web graph layout |
| `aiosqlite` | Async SQLite access |
| `reportlab` | PDF generation for the raids command |
| `pnwkit-py>=2.6.26` | PnW GraphQL API client (harvester subscriptions) |
| `psutil`, `aiofiles`, `tqdm` | System utilities |
| `pytest`, `pytest-asyncio` | Testing |
| `pywin32` | Windows-specific utilities |

**Node.js (`package.json`):**

| Package | Purpose |
|:---|:---|
| `bootstrap` | CSS framework for web UI |
| `three` | 3D globe rendering (Treaty Universe page) |
| `gsap` | Web animation library |

---

## License

See LICENSE.txt for license information.
