# Reaper Bot

> A self-hosted Discord bot that serves as a comprehensive Politics & War intelligence platform, a full pet RPG system, a support ticket desk, a translator, an astrology system, and an entertainment hub — all running locally with an embedded web interface.

---

## Table of Contents

- [🎭 Overview](#overview)
- [⚙️ Configuration and Environment](#configuration-and-environment)
- [🚀 Installation and Startup](#installation-and-startup)
- [🌟 Major Features](#major-features)
  - [🐾 Pets System](#pets-system)
  - [⚔️ Politics & War System](#politics--war-system)
  - [🎫 Tickets System](#tickets-system)
  - [🌐 Translator System](#translator-system)
  - [🔮 Astrology System](#astrology-system)
  - [🎮 Fun System](#fun-system)
  - [🛠️ Admin and Utilities](#admin-and-utilities)
- [📊 Database Structure](#database-structure)
- [🔧 Technical Architecture](#technical-architecture)

---

## Overview

Reaper Bot is a self-hosted Discord bot built in Python that runs entirely on your local machine — no cloud hosting, no third-party bot service, no subscription fees. All data stays local: your databases, your API keys, your user data.

The bot has two integrated sides:

- **Discord side** — Handles slash commands and text commands directly in your server for PnW intelligence, pet games, tickets, translation, astrology, and entertainment.
- **Web side** — Runs a FastAPI server embedded inside the bot process, serving a full browser-based interface for the pet system and PnW analytics tools at your configured domain.

Both sides start from a single command (`python reaper.py`) and share the same local SQLite databases. There is no separate web server to manage, no Docker container required, and no database server to configure.

**Key Features:**

- **Pets** — A complete digital pet RPG with stats, elements, equipment, an ability tree, turn-based combat, PvP, tournaments, dungeon crawls, casino games, quests, a stock market, and a full browser-based interface.
- **Politics & War** — Deep integration with the PnW game: real-time nation and war tracking via live subscriptions, revenue and cost calculators, war intelligence dashboards, raid finders, treaty maps, alliance comparisons, beige alerts, resource price alerts, and a global news/leaderboard system.
- **Tickets** — A structured support ticket system with category routing, staff assignment, and transcript logging.
- **Translator** — Automatic message translation using Google Translate, with per-channel language configuration via flag emoji reactions.
- **Astrology** — Daily horoscopes, tarot readings, and zodiac compatibility checks powered by AI.
- **Fun** — Roasts, compliments, a zombie survival game, and other entertainment commands.

The bot is designed for the Darkstar alliance (PnW alliance ID 10259) but the PnW tools work for any alliance or nation. The pet system is entirely self-contained and has no PnW dependency.

---

## Configuration and Environment

Reaper Bot is configured entirely through a single `.env` file located at `Systems/Functions/.env`. The bot reads this file on startup — no environment variables need to be set at the system level, and there is no fallback to a root-level `.env`. If the file is missing or the Discord token is absent, the bot will not start.

All secrets stay local to your machine. Nothing is transmitted externally except the specific API calls each key is used for (Discord, PnW, AI providers, etc.). The `.env` file is excluded from version control via `.gitignore`.

### Required Configuration

| Variable | Purpose |
|:---|:---|
| `DISCORD_TOKEN` | Your bot's authentication token from the Discord Developer Portal. The bot will not start without this. |

### Optional — Bot Behavior

| Variable | Purpose | Default |
|:---|:---|:---|
| `COMMAND_PREFIX` | Prefix for legacy text commands. | `!` |
| `ADMIN_USER_ID` | Discord user ID of the server owner. Gates admin-only commands. | `0` (disabled) |
| `RESULTS_CHANNEL_ID` | Channel ID where game results and logs are posted. | `0` (disabled) |
| `DATA_DIR` | Base directory for data storage. Useful for containerized deployments. | Current working directory |

### Optional — AI Features

| Variable | Purpose |
|:---|:---|
| `GEMINI_API_KEY` | Google Gemini. Powers the Zombie survival AI story system. |
| `GROQ_API_KEY` | Groq (Llama 3.1). Powers Tarot readings, roasts, and compliments. |

### Optional — Politics & War

| Variable | Purpose |
|:---|:---|
| `PANDW_API_KEY` | PnW API v2 key. |
| `PANDW_API_V3_KEY` | PnW API v3 key. Used for all GraphQL queries across PnW commands. |
| `PANDW_BOT_KEY` | PnW bot key. |

### Optional — Other APIs

| Variable | Purpose |
|:---|:---|
| `HORSCOPE_API` | Aztro API key for daily horoscopes in the Astrology system. |
| `GIPHY_KEY` | Giphy API key for GIF responses in the roast/compliment system. |
| `PIXABAY_KEY` | Pixabay API key for image responses in the roast/compliment system. |

### Optional — Web & Cloudflare

| Variable | Purpose | Default |
|:---|:---|:---|
| `CUSTOM_DOMAIN` | The public-facing domain for the web interface. | `https://reaper.qzz.io` |
| `USE_CLOUDFLARE_TUNNEL` | Set to `true` to automatically start the Cloudflare tunnel on bot startup. | `false` |
| `CF_ACCOUNT_ID` | Cloudflare account ID. Required for cache purge operations. | — |
| `CF_TUNNEL_ID` | Cloudflare tunnel ID for named tunnel routing. | — |
| `CF_API_TOKEN` | Cloudflare API token. Used to purge the CDN cache programmatically. | — |
| `CF_TUNNEL_TOKEN` | Cloudflare tunnel authentication token. | — |
| `CF_CREDENTIALS_FILE` | Path to the Cloudflare tunnel credentials JSON file. | — |

---

## Installation and Startup

### Prerequisites

- **Python 3.12** — The bot is designed for Python 3.12. Other versions may work but are not tested.
- **Node.js and npm** — Required for web frontend dependencies.
- **Windows** — The bot is primarily designed for Windows (uses Windows-specific paths). Linux support may work with path adjustments.

### Automatic Setup

On first run, the bot automatically checks for its Python virtual environment and Node.js dependencies. If either is missing or incomplete, it installs them before proceeding — no manual setup steps required.

### Starting the Bot

Starting the bot is a single command from the project root:

```bash
python reaper.py
```

The startup sequence:

1. **Dependency Check** — Verifies Python virtual environment exists and is valid. If not, creates it and installs all requirements from `requirements.txt`.
2. **Node.js Check** — Verifies `node_modules` exists with required packages. If not, runs `npm install`.
3. **Bot Initialization** — Creates Discord bot instance with proper intents.
4. **Cog Loading** — Loads all command cogs in organized sets (Admin, Mythical, Fun, PnW, Management, Tickets).
5. **Command Sync** — Syncs application commands with Discord.
6. **Web Server Start** — Starts the embedded FastAPI web server on port 8080.
7. **Cloudflare Tunnel** — If enabled, starts the Cloudflare tunnel for public access.
8. **Background Tasks** — Starts periodic user sync and beige notification loops.

### Manual Installation (Optional)

If you prefer to set up dependencies manually:

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment (Windows)
.venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Install Node.js dependencies
npm install
```

Then start the bot with `python reaper.py`.

---

## Major Features

---

### Pets System

The Pets System is a full digital pet RPG with both Discord commands and a comprehensive browser-based interface. The web interface runs as a FastAPI web server embedded inside the bot, accessible at the configured domain (`https://reaper.qzz.io` by default) or locally at `http://localhost:8080`.

#### Web Interface

**Authentication**

Access to any personal pet data requires logging in with Discord OAuth2. The login flow redirects to Discord's official authorization page, requests only the `identify`, `email`, and `guilds` scopes, and stores the session server-side. Access tokens are automatically refreshed in the background — users are never interrupted mid-session by an expired token. Avatar and profile data sync to the local database on every login and on a 60-second refresh cycle. No passwords are stored; authentication is entirely delegated to Discord.

**Dashboard**

The main entry point is `web/dashboard.html` — a single-page application that loads all other pages dynamically without full page reloads. It displays the bot's avatar and name, provides sidebar navigation between all sections, and adapts to desktop and mobile screen sizes.

**Pet Management**

The core pet pages let users adopt, view, train, and manage their pet entirely through the browser:

- **Adopt** (`what_are_pets.html`, `petconnector.html`) — New users are walked through the pet system and guided through choosing a species, category, element combination, and custom name. Adoption validates the name for safe characters and prevents duplicate pets per user.
- **My Pet** (`mypet.html`) — Displays the pet's full stat sheet with computed values, XP bar, level, inventory, equipped items, and battle action labels. Users can rename their pet and set custom names for their three battle actions (Attack, Defense, Charge).
- **Pet Roster** (`pets.html`) — A broader view of all pets registered in the system, used for game entry and social browsing.
- **Ability Tree** — An interactive skill tree where users spend stat mastery points and unlock combat abilities for their pet.
- **Bazaar** (`bazaar.html`) — An in-world marketplace for pet items and equipment.

**Activities**

Pets can be sent on activities directly from the web interface. Each activity has a short cooldown enforced server-side and persisted to the database so it survives bot restarts:

- **Train** — Choose a stat (ATT, DEF, INT, DEX, HAP, ENE) and a difficulty. Success increases the stat; failure decreases it. Equipment multipliers scale the change.
- **Mission** — Send the pet on a mission at Easy, Average, or Hard difficulty. Success awards XP and key loot scaled to the pet's level. Players can optionally gamble additional XP on the outcome.
- **Play** — Send the pet to one of twelve locations (Camp, Beach, Forest, Mountain, Glacier, Pyramids, etc.). XP and key loot are influenced by the pet's elements and the location's special properties.
- **Quest** — A multi-stage adventure with branching choices. Each stage presents a scenario and options; the outcome depends on the pet's stats and the player's decisions.

**Casino**

The casino is a fully multiplayer, room-based system. The lobby (`casino_lobby.html`) shows 12 live rooms with real-time state broadcast over WebSocket — players can see who is in each room, what game is running, and whether seats are available, all without refreshing.

Games available:

- **Slots** (`casino.html`) — Solo slot machine with multiple difficulty tiers and animated reels.
- **Blackjack** (`blackjack.html`) — Up to 6 players at a table. Supports standard blackjack rules including double-down and split.
- **Texas Hold'em** (`holdem.html`) — Up to 6 players with AI opponents filling empty seats. Full poker hand evaluation.
- **Craps** (`craps.html`) — One active roller with observers who can place side-bets on the outcome. The roller can pass the dice to an observer.
- **Pet Races** (`races.html`) — Up to 4 pets race simultaneously. Observers can bet on any racer before the race starts.
- **Mini-Games** (`minigames.html`) — A collection of shorter head-to-head games.

Observers in any room can watch live game state updates and, in supported games (Craps, Races), place side-bets on active players. Pending seat requests let observers queue to join at the start of the next round without interrupting an active game. All XP wagers are deducted immediately on placement and paid out (or forfeited) when the round resolves.

**Other Pet Games and Features**

- **Arena** (`arena.html`) — PvP and PvE combat using the full battle system with skills, abilities, and damage calculations.
- **Colosseum** (`colosseum.html`) — Automated hourly tournament battles between registered pets. Results are tracked on a leaderboard.
- **Dungeon** (`dungeon.html`) — A crawl-style dungeon with procedurally generated encounters.
- **Survivor Series** (`survive.html`) — A battle royale format where multiple pets compete across elimination rounds on a procedural map.
- **Tasks** (`tasks.html`) — A daily and weekly task system. Each pet owner has a set of active tasks that refresh on a schedule. Completing tasks (training, missions, playing, renaming) earns bonus rewards.
- **Pet Stock Market** (`pet_stock.html`) — A simulated resource stock market tied to pet economy events. Prices update on an hourly loop.
- **Powerball** (`powerball.html`) — A lottery system where players buy tickets with XP for a chance at a large jackpot.
- **Wheel of Pets** (`wheel.html`) — A spin-the-wheel game with variable XP prizes.
- **Scratch Cards** (`scratch.html`) — Instant-win scratch card games.
- **Keno** (`keno.html`) — A number-pick lottery game.
- **Leaderboard** (`leaderboard.html`) — Global rankings across multiple categories (level, XP, battle wins, casino earnings, etc.).
- **Game Info** (`game_info.html`) — A reference page showing current resource prices, color bonuses, and other live game data.
- **Battle Config** (`battle_config.html`) — Lets users configure their pet's preferred battle settings and action priorities.

**Library**

The library (`library.html`) is an in-app documentation and guide system. It serves Markdown files from `web/Pages/Library/` as formatted articles covering game mechanics, strategy guides, and doctrine documents. Content is rendered client-side from the raw Markdown files served by the library API.

---

### Politics & War System

The Politics & War System provides deep integration with the PnW game through both Discord commands and a browser-based analytics interface. The bot reads from local databases maintained by the separate PnWHarvester process, ensuring fast responses without excessive API calls.

#### Web Interface

The PnW web interface is accessible at the same domain as the Pets system. Most pages are publicly viewable without logging in; features that save personal data (such as beige alerts and resource price alerts) require Discord login.

All data served by this system comes from two sources: the local `GlobalNations.db` and `IRSWars.db` databases maintained by the PnWHarvester, and the live PnW GraphQL API for data not yet in the local store. The local database is always queried first — API calls are only made when local data is insufficient or a live refresh is explicitly requested.

**Watch Page** (`watch.html`)

The Watch page is the primary war intelligence dashboard for Darkstar (alliance 10259). It reads directly from the local `IRSWars.db` — no API calls are made for this page. Users can select any date range within the available war history and the page calculates a full breakdown for every nation that fought in that window:

- Gross cost (units lost, infrastructure destroyed, improvements lost, gasoline and munitions consumed)
- Net damage dealt to opponents
- Loot gained and lost, broken down by cash and each resource with monetary values at current market prices
- Per-nation opponent breakdown showing exactly who fought whom and the cost/gain on each side
- Alliance-wide totals row aggregating all nations

War data is cached for 2 minutes per date range to avoid redundant recalculation on repeated requests. Revenue calculations are pre-warmed at each PnW turn boundary (every 2 hours) so the first request after a turn change is never slow.

**Nations Page** (`nations.html`)

A searchable, filterable view of all nations tracked in `GlobalNations.db`. Supports searching by nation name, leader name, or alliance. Displays score, city count, military units, war policy, projects, and activity status. Data is read entirely from the local database — no API calls.

**Revenue Page** (`revenue.html`)

Calculates the full per-turn and per-day revenue for any nation or alliance. Uses the complete city-build engine accounting for improvements, projects, color bloc bonuses, radiation levels, seasonal modifiers, and current resource market prices. For Darkstar nations, data comes from `GlobalNations.db`; for other alliances, it falls back to the live PnW API.

**Revenue Optimizer** (`rev_optimizer.html`)

Analyzes every city in a nation or every nation in an alliance and generates ranked improvement suggestions to maximize net income. For each city it shows current net revenue, the top improvement changes that would increase it, and the projected gain per suggestion. Project-level suggestions (national projects that affect revenue) are also included. Results are sorted by current monetary output descending so the highest-value nations appear first.

**Cost Calculator** (`cost_calc.html`)

An interactive calculator for estimating the cost of in-game purchases: infrastructure, land, new cities, and national projects. Uses live resource prices from the local database to give accurate monetary estimates at current market rates.

**Comparison Page** (`comparison.html`)

Side-by-side alliance comparison tool. Accepts one or more alliances on each side (by name, ID, or PnW link, comma-separated). Produces a detailed comparison covering:

- Nation counts (total, active, applicants, vacation mode, grey, beige, inactive 7/14 days)
- Score and city totals and averages
- Full military breakdown: current units, maximum capacity, daily production, and gaps to max for soldiers, tanks, aircraft, and ships
- Project counts across all 40+ national projects
- Improvement totals across all improvement types
- City count distribution

For Darkstar, data is read from `GlobalNations.db`. For other alliances, the live PnW API is queried. An interactive HTML comparison report can also be generated and saved to `Systems/web/Comparisons/`.

**Raids Page** (`raids.html`)

A raid target finder that searches `GlobalNations.db` for nations within war range of a given attacker. Filters available: inactive only, militarily weak only, beige targets only, minimum projected loot, excluded alliances, and maximum active defensive wars. For each candidate it calculates a projected loot value using live holdings data from `holdings.db` (actual money and resources held, net of all spending and transfers) with a revenue-based fallback when holdings data is unavailable. Results are sorted by projected loot descending.

The page also manages **beige alerts** — per-user notifications set when a target nation is on beige. Alerts are stored in `alerts.db` and the bot sends Discord DMs at two thresholds: ~2 hours before beige expires and ~15 minutes before. Alerts can be set, refreshed, and deleted from the web interface. Refreshing pulls live `beige_turns` from the PnW API and recalculates projected loot from current holdings.

**Weapons Page** (`weapons.html`)

Missile and nuclear weapon efficiency calculator with two modes:

- **Theory mode** — Given any infrastructure level and population density, calculates minimum, maximum, and average damage and infrastructure value destroyed for both missiles and nukes. Shows cost-multiplier thresholds (the infrastructure level needed for a weapon to deal 1×, 2×, 5×, 10× its cost in damage) and a full damage chart across multipliers.
- **Targeted mode** — Given a specific nation or alliance, scores every city by expected damage value, accounting for Iron Dome (30% missile block chance) and Vital Defense System (25% nuke block chance). Alliance mode ranks all nations by their best-city missile damage, making it easy to identify the highest-value targets.

All calculations use live resource prices from the local database to keep weapon costs current.

**News Page** (`news.html`)

A global PnW event feed and leaderboard system backed by the news databases maintained by the PnWHarvester. Supports four time periods: current week, previous week, current month, previous month, and yearly archives. Features:

- **Event feed** — Paginated list of war declarations, war endings, city builds, project purchases, alliance changes, and other game events. Filterable by event type, alliance, or nation. Nation and alliance IDs are resolved to real names from `GlobalNations.db`.
- **Alliance leaderboard** — Ranked by wars declared, wars won, loot gained, nukes used, missiles used, cities built, projects bought, and total spending.
- **Nation leaderboard** — Same metrics at the individual nation level, filterable by alliance.
- **Summary cards** — High-level world totals for the selected period (total wars, total loot, total nukes, etc.).
- **War cost drill-down** — Clicking a war event shows the full cost breakdown for both sides pulled from `IRSWars.db`.
- **Live search** — Searches nations and alliances by name across `GlobalNations.db` for quick filtering.
- **Resource prices** — Current sell prices shown alongside loot values so resource loot is displayed in monetary terms.

**Resource Price Alerts** (`watch.html` / alerts panel)

Users can set price threshold alerts for any of the 12 PnW resources (food, coal, oil, uranium, lead, iron, bauxite, gasoline, munitions, steel, aluminum, credit). Each alert specifies a resource, buy or sell price, direction (above or below), and threshold value. Alerts are stored in `alerts.db` and checked by the bot's timed query loop, which sends a Discord DM when a threshold is crossed. Alerts can be managed entirely from the web interface.

#### Discord Commands

The PnW Discord System is the collection of slash and hybrid commands that bring Politics & War intelligence directly into your Discord server. Commands are organized into five functional groups — Economic Affairs, Foreign Affairs, Internal Affairs, Military Affairs, and a miscellaneous group for fun PnW tools.

All PnW commands read from the local `GlobalNations.db` and `IRSWars.db` databases first. Live API calls are only made when local data is insufficient or a real-time refresh is explicitly needed. This keeps commands fast and keeps your API key usage low.

**EA — Economic Affairs**

The Economic Affairs module provides Discord commands covering market intelligence, revenue analysis, economic optimization, and price alerting.

- **`/turn_bonuses`** — Displays the current turn bonus for every color bloc in Politics & War, sorted from highest to lowest.
- **`/game_info`** — Shows the current state of the PnW game world with in-game date, top 20% city average, global radiation level, and per-continent radiation breakdown with an attached pie chart.
- **`/game_resources`** — Plots historical resource and money holdings across the entire game world over a selected time window with Matplotlib graphs.
- **`/revenue`** — Calculates the full per-turn and per-day revenue breakdown for a nation or an entire alliance, including gross income, color bloc bonus, military upkeep, improvement upkeep, power upkeep, resource upkeep, net cash per turn/day, per-resource production with monetary value, and total monetary net.
- **`/rev_optimizer`** — Runs a full economic optimization analysis on a nation or every nation in an alliance, generating ranked improvement suggestions to maximize net income.
- **`/stocks`** — Displays current PnW market prices for all 12 resources with price change indicators and a 30-day price trend graph.
- **`/history`** — Opens a modal dialog for selecting a custom date range and generates a historical price chart for that window.
- **`/rss_alert_set`** — Sets a one-shot price alert for any of the 12 PnW resources.
- **`/rss_alert_remove`** — Removes a specific active alert before it fires.
- **`/rss_alert_list`** — Lists all your currently active resource price alerts.

**FA — Foreign Affairs**

The Foreign Affairs module provides Discord commands for visualizing and tracking diplomatic relationships between alliances in Politics & War.

- **`/treaties`** — Displays the full treaty web for any alliance with both a rich Discord embed and a generated treaty web image showing treaty partners arranged in concentric rings by treaty strength. Includes a Refresh button and optional daily auto-update.
- **`/treaty_universe`** (aliases: `/treaty_map`, `/universe`) — Generates an interactive treaty map centered on any alliance and returns a link to it.

**IA — Internal Affairs**

The Internal Affairs module provides Discord commands for monitoring alliance health, auditing member compliance, looking up nation details, calculating build costs, and delivering in-game guides.

- **`/alliance`** — The main alliance overview command with five interactive views: Alliance Totals, Military, Improvements, Project Totals, and Refresh.
- **`/audit`** — Audits an alliance for compliance issues with views for Inactives, Color distribution, and MMR Build compliance.
- **`/show`** — Looks up any nation by name, leader name, nation ID, or PnW link and displays a comprehensive nation profile with all stats, projects, and achievement badges.
- **`/costs`** — Calculates the cost of infrastructure, land, cities, and national projects for any nation, applying all relevant discounts.
- **`/snipe_guide`** — Sends the complete 10-step beige sniping and raiding guide.
- **`/snipe_setup`** — Sends only the setup portion of the snipe guide (steps 1–4).
- **`/snipe_execute`** — Sends only the execution portion of the snipe guide (steps 5–10).
- **`/war_guide`** — Sends a structured guide on PnW war mechanics with categories for Ground Supremacy, Air Supremacy, Naval Blockade/Supremacy, Missiles, Nukes, Fortification, Peace, and Key Strategy.

**MA — Military Affairs**

The Military Affairs module provides Discord commands for war intelligence, target finding, cost analysis, war performance tracking, and strategic planning.

- **`/wars`** — Calculates the full cost breakdown for a war matchup between two sides with paginated views for Summary, Military, Destruction, and Loot.
- **`/wars_cost_bd`** — Generates a full per-nation war cost breakdown for an alliance over a selected time window.
- **`/wars_net_bd`** — Identical structure to `/wars_cost_bd` but calculates net damage rather than gross cost.
- **`/war`** — Simulates a full war between two nations turn by turn with a paginated embed showing each turn's results.
- **`/compare_wars`** — Head-to-head war performance comparison between two Darkstar member nations over a selectable time range.
- **`/rankings`** — Shows the top 25 Darkstar nations ranked by a selected war statistic over a chosen time range.
- **`/raids`** — Finds raid targets within war range of a given nation with filters for inactive, weak military, minimum loot, beige status, excluded alliances, and maximum defensive wars.
- **`/destroy`** — Finds optimal attacker groups from one or more alliances to coordinate a strike on a target nation.
- **`/offshore`** — Scans an alliance's member bank records for external fund transfers that may indicate offshore banking activity.
- **`/units`** — Interactive military unit cost calculator with a Recalculate button for live calculations.
- **`/weapon_eff`** — Weapon efficiency analysis for missiles and nukes with theory mode and targeted mode.

**Other — Fun PnW Stuff**

A collection of miscellaneous Politics & War commands that don't fit neatly into the other categories.

- **`/baseball`** — Looks up the baseball team for any nation with full team stats and a star rating.
- **Loot Intelligence (message listener)** — Automatically parses spy reports and loot messages when the bot is mentioned, calculating projected loot or actual loot values.
- **`/activity`** — Displays Politics & War world activity statistics over a configurable time range with a line chart.
- **`/theme emoji set/remove/list/reload`** — Personal customisation system for how nations and alliances appear in autocomplete dropdowns throughout the bot.

---

### Tickets System

The Tickets System manages membership applications and embassy requests for the Darkstar Discord server. It is purpose-built for the alliance's onboarding workflow and integrates directly with the PnW API and the bot's existing nation/alliance lookup tools.

All ticket state is persisted to `Databases/Tickets.db` so tickets survive bot restarts. The interactive buttons in the info channel are registered as persistent views and are restored automatically when the bot starts.

**How it works**

A welcome embed is posted in the designated info channel using `/info`. The embed contains two buttons — **Membership** and **Embassy** — that any server member can click at any time.

Clicking **Membership** opens a modal asking for a nation name or ID. The bot looks up the nation from the PnW API, creates a private ticket channel named `c{cities}-{nation-name}` (e.g. `c15-reaperland`), and immediately posts the full `/show` nation profile inside it. Only the applicant, the bot, and configured staff roles can see the channel.

Clicking **Embassy** opens a modal asking for an alliance name or ID. The bot looks up the alliance, creates a private ticket channel named after the alliance, and immediately posts the full `/alliance` overview inside it. The channel color matches the alliance's PnW color.

**Staff commands**

- **`/verify accept`** — Run inside a ticket channel to accept the application. For membership tickets: assigns the Member role and moves the channel to the accepted members category. For embassy tickets: creates or finds a Discord role named after the alliance, assigns that role plus the Diplomat role, and moves the channel to the accepted embassies category.
- **`/verify reject`** — Run inside a ticket channel to reject the application. Notifies the applicant, marks the ticket as rejected, waits 5 seconds, then deletes the channel and removes the record.
- **`/delete_ticket`** — Deletes any ticket by name with autocomplete. Deletes the Discord channel if it still exists and removes the database record.
- **`/resort_members`** — Re-queries the PnW API for every open membership ticket and renames the channels to reflect the applicant's current city count and nation name.

**Ticket role management**

- **`/ticket_role add <role> [label]`** — Adds a Discord role to the ticket roles list. Every new ticket channel created after this point will automatically grant that role read/write access.
- **`/ticket_role remove <role>`** — Removes a role from the list.
- **`/ticket_role list`** — Shows all configured ticket roles with their friendly labels.

**Welcome message**

When a new member joins the server, the bot automatically sends a welcome embed in the info channel. The embed mentions the new member, links to the ticket channel and bot spam channel, links to the website, and includes the alliance's standing rule about the perimeter.

---

### Translator System

The Translator System provides on-demand message translation directly inside Discord channels without requiring any external accounts, API keys, or configuration. It works in two ways — flag emoji reactions and a right-click context menu.

**Flag emoji reactions**

Any user can react to any message with a country flag emoji to request a translation of that message into the corresponding language. The bot watches for flag reactions across all channels it can see. When a supported flag is added, the bot:

1. Fetches the message content
2. Sends it to Google Translate with auto-detection for the source language
3. Posts a short prompt in the channel — "Translation ready for 🇫🇷! (Click below to see it)" — with a **Show Translation** button
4. The prompt auto-deletes after 60 seconds

The **Show Translation** button is user-locked — only the person who reacted can click it. When clicked, the translation appears as an ephemeral message (visible only to that user) showing the translated text, the source channel name, and a preview of the original message.

A debounce lock prevents the same user from triggering duplicate translations for the same message and emoji within a 2-second window.

**Supported languages (63 total)**

The flag-to-language mapping covers the major world languages including English, Spanish, French, German, Italian, Portuguese, Russian, Dutch, Polish, Ukrainian, Greek, Turkish, Czech, Hungarian, Romanian, Bulgarian, Swedish, Norwegian, Danish, Finnish, Icelandic, Estonian, Latvian, Lithuanian, Slovak, Slovenian, Croatian, Serbian, Albanian, Maltese, Chinese (Simplified and Traditional), Japanese, Korean, Hindi, Indonesian, Malay, Vietnamese, Thai, Tagalog, Hebrew, Arabic, Persian, Urdu, Bengali, Kazakh, Uzbek, Armenian, Georgian, Azerbaijani, Mongolian, Afrikaans, Amharic, Somali, Wolof, Swahili, Igbo, and Esperanto.

**Right-click context menu**

A **Translate** option appears in the right-click (or long-press) Apps menu on any message. Selecting it translates the message to English and shows the result as an ephemeral reply — only visible to the user who triggered it.

**Privacy and safety**

All translations are delivered ephemerally where possible — either via the button interaction (visible only to the requester) or via the context menu (also ephemeral). The channel prompt that appears when a flag reaction is used contains no translated text itself, only a button, and auto-deletes after 60 seconds. No message content is stored by the bot; it is passed directly to Google Translate and the result is returned immediately.

---

### Astrology System

The Astrology System provides two Discord commands covering tarot card readings and a triple-zodiac personality profile system. Both are slash/hybrid commands.

**`/tarot`**

Performs a professional tarot card reading with three spread options:

- **1 Card** — A single card draw with a direct message from the universe
- **3 Card (Past/Present/Future)** — Three cards covering the foundation of a situation, where you currently stand, and the path ahead
- **5 Card (Traditional)** — Five cards covering the core theme, the obstacle, the advice, a hidden influence, and the likely outcome

For each spread, the bot randomly draws unique cards from the full 78-card tarot deck. Each card is randomly assigned an orientation — upright or reversed — which determines whether its light or shadow meanings apply. Major Arcana cards are visually distinguished from Minor Arcana.

The card images are loaded from the local `Systems/Astrology/Tarot/cards/` directory, resized to a consistent size, rotated 180° if reversed, and stitched side-by-side into a single composite PNG image that is attached to the response.

For multi-card spreads, the bot also calculates a **dominant energy** based on which suit appears most frequently — Fire (Wands), Water (Cups), Air (Swords), Earth (Pentacles), or Major Arcana — and displays a thematic atmosphere line if one suit dominates.

An **AI-powered summary** is generated using the Groq API (Llama 3.1). The prompt is tailored to the spread type: a single profound message for 1-card draws, a cohesive narrative connecting past/present/future for 3-card draws, and a comprehensive interpretation covering all five positions for the traditional spread. If the Groq API is unavailable, the reading still works — the AI summary field shows a fallback message and all card details remain fully visible.

The result is a paginated embed with two views navigable via buttons:

- **Cards** — Shows the stitched card image, the dominant energy (if applicable), and a per-card breakdown with position name, transition phrase, card name and orientation, top three meanings, and a fortune-telling line
- **Summary** — Shows only the AI-generated narrative interpretation, with the image removed for a cleaner read

**`/zodiac`**

Generates a triple-zodiac personality profile from a birthday. Accepts a date and produces a three-page interactive embed navigable via buttons:

- **Western** (♈ button) — The standard sun sign based on month and day. Shows the sign's element, modality, ruling planet, astrological house, associated tarot card, traits, lucky numbers, lucky colors, gemstones, compatibility signs, and a full description. The date range for the sign is displayed and a countdown to the user's next birthday is shown in the footer.
- **Eastern** (🐉 button) — The Chinese zodiac animal based on the birth year, with proper Chinese New Year boundary handling. The bot uses a lookup table of exact Chinese New Year dates from 1900 to 2027 to correctly assign the animal. Shows the animal's polarity (Yin/Yang), fixed element, trine group, lucky hours, lucky numbers, lucky colors, lucky flowers, traits, and compatibility/incompatibility pairings.
- **Spirit Animal** (🌀 button) — The Primal Astrology spirit animal, which is the unique combination of Western sun sign and Chinese zodiac animal. Each of the 144 possible combinations maps to a distinct spirit animal with its own description and characteristics.

The Western page also includes a **daily horoscope** fetched from the Aztro API, showing the day's description, mood, lucky color, lucky number, lucky time, and compatibility sign. If the Aztro API is unavailable and a `HORSCOPE_API` key is configured, a RapidAPI fallback is tried. If both are unavailable, a locally generated horoscope is produced from sign-specific templates so the command always returns something useful.

All zodiac data (Western signs, Chinese animals, and Primal combinations) is loaded from local JSON files in `Systems/Astrology/Zodiac/` and cached in memory after the first read. No user data is stored beyond the duration of the command interaction.

---

### Fun System

The Fun System is a collection of interactive games and entertainment commands. All are slash/hybrid commands.

**`/rps`**

Rock Paper Scissors with three themes and an optional AI opponent.

- **Traditional** — Rock, Paper, Scissors
- **Fantasy** — Knights, Archer, Necromancer
- **War** — Tank, Jet, Ship

Accepts an optional rival mention, a round count (1, 3, or 5), and a theme. If no rival is mentioned, a **Join Game** button appears so anyone can join. Setting `ai_opponent: True` plays against the bot instead. The AI opponent uses `ai_brain.py` to track the player's move history and make informed counter-choices rather than picking randomly.

**`/dice`**

Rolls 1–5 dice. Supports D6 (with color options: Red, Orange, Blue, Yellow, Pink, Green, Purple) and D20. Each result is displayed using the corresponding custom server emoji. D20 results use a dedicated emoji for each face value 1–20.

**`/card`**

Draws 1–5 random playing cards from a full 54-card deck (52 standard + 2 jokers). Each card is displayed using its custom server emoji (Hearts, Diamonds, Clubs, Spades, and Jokers categories).

**`/range`**

Sniper training reaction game. Available round counts: 5, 15, 25, 50, or 100.

After a 5-second setup message and a 3-second countdown, the bot presents one round at a time. Each round shows 5 buttons — one is the target (🎯 Hit emoji), the rest are misses (🔴 Miss emoji). The player has 1.2 seconds to click the correct button. Clicking the wrong button or timing out counts as a miss.

After all rounds, the bot calculates accuracy and assigns a rank from **Blindfolded Intern** (below 20%) up through **Deliverer of Death** (100%). Results show hits/total, accuracy percentage, a visual accuracy bar, and the personal best for that round count. Stats are persisted to the user's data profile across sessions.

**`/tictactoe`**

Tic Tac Toe with optional NPC opponent and three difficulty levels.

- **Novice** — The bot picks randomly
- **Competent** — The bot checks for winning/blocking moves before falling back to random
- **Expert** — The bot uses the minimax algorithm and plays optimally

The creator picks their emoji via a modal. A second player joins via a Join Game button and also picks their emoji. The board is displayed as a 3×3 grid of buttons. Supports multi-round series (best of 1, 3, or 5). The series score is shown in the embed title throughout.

**`/roast`**

AI-generated roast targeting a mentioned user (or yourself if no target is given). Seven intensity levels: Mild, Simple, Standard, Spicy, Wild, NSFW, and Explicit. Each level has a distinct system prompt that controls tone, language, and content.

The bot attempts to fetch the target's Discord bio to personalise the roast. The content is generated via the Groq API (Llama 3.1) with a 2–3 sentence limit. If the API is unavailable, a theme-appropriate fallback line is used. The intensity level emoji is shown alongside the result.

**`/compliment`**

Identical structure to `/roast` but generates praise instead of insults. Same seven intensity levels, same bio personalisation, same Groq API with fallback. The compliment is tailored to highlight positive traits at the appropriate intensity.

**`/random`**

Fetches and posts a random image or GIF. Two types:

- **JPG** — Fetches a random photo from Pixabay (requires `PIXABAY_KEY`). Picks a random page offset each call for genuine variety.
- **GIF** — Fetches a random GIF from Giphy (requires `GIPHY_KEY`). Uses the Giphy random endpoint with a general rating.

The image is downloaded server-side and posted as a Discord file attachment rather than a URL embed, so it displays inline regardless of link preview settings.

**`/walktru`**

A text-based adventure game with six distinct storylines, each with its own mechanic that changes based on your choices:

- **Horror Sanitarium** — Manage Fear (0–100); too much fear ends the run
- **1920s Gangster** — Manage Heat (0–100); too much police attention ends the run
- **Knight's Quest** — Manage Honor (0–150); starts at 100, moral choices raise or lower it
- **Robot Factory Escape** — Manage Power (0–100); reach 100% by stage 10 to build your body
- **Western Frontier** — Manage Health (0–100); starts at 100, injuries reduce it
- **Wizard's Apprentice** — Manage Mana (0–150); starts at 100, spells consume it

A dropdown menu lets you select the adventure. Each stage presents a scenario with numbered choice buttons. Choices have a success chance — the outcome (success or failure) is rolled randomly against that chance. The mechanic value changes based on the outcome, clamped within the adventure's bounds. A visual progress bar with warning messages shows the current mechanic status. The adventure ends when the mechanic hits a critical threshold or the story reaches its conclusion.

**`/zombie_survival`**

An ongoing, AI-driven zombie survival simulation that runs continuously in a channel. Multiple players can join and their fates are shared.

Each round the Groq AI (Llama 3.1) generates a new story event with exactly 4 choices, each assigned a base success probability (meaningfully different from each other — a suicidal charge might be 10–20%, a cautious retreat 60–80%). Players vote by clicking A/B/C/D buttons. The round resolves automatically every 2 hours.

The winning choice is determined by majority vote (ties broken randomly). The final success chance is the base odds plus a vote multiplier (2–5% per voter on the winning choice) plus a random luck factor (±15%). More votes on a choice genuinely improves its odds.

On success, survivors gain small amounts of HP, stamina, morale, and ammo. On failure, stats are penalised. Attack choices consume ammo (rifle preferred, then revolver, with auto-reload from spare). Supply/scavenge choices gain ammo. If a survivor's health reaches 0 they are marked Deceased. If all survivors die, the game ends with a game-over embed and the state is fully wiped.

The round embed shows the current story event, a live countdown to the next resolution using Discord's native timestamp format, the 4 choices, survivor mentions (deceased shown with strikethrough), and the previous round's outcome.

**`/zombie_character`**

Shows your personal survivor card for the active zombie game: health, stamina, morale, revolver ammo (loaded/spare), rifle ammo (loaded/spare), and your randomly assigned melee weapon. Ephemeral — only visible to you.

---

### Admin and Utilities

The Admin and Utilities module provides core bot management commands and shared utility functions used across all systems.

**Admin Commands**

- **`/shutdown`** — Securely shuts down the bot. Can only be used by the bot owner (ARIES_USER_ID).
- **`/usage`** — Shows bot usage statistics and allows for server/user management. Can only be used by the admin user (ADMIN_USER_ID). Provides a paginated view with servers, users with data, and installed users.
- **`/servers`** — Lists all servers the bot is currently in with member counts. Can only be used by the admin user.

**Info Command**

- **`/info`** — Posts the welcome embed in the designated info channel with Membership and Embassy buttons for ticket creation.

**Background Tasks**

The bot runs several background tasks:

- **Periodic User Sync** — Every 5 minutes, syncs Discord user data for users with stale data (last updated more than 1 day ago). This keeps avatars and profile information current.
- **Beige Notification Loop** — Every 2 minutes, checks all beige alerts in `alerts.db` and sends Discord DMs at two thresholds: ~2 hours before beige expires and ~15 minutes before. Also drains the early-exit queue written by the harvester when it detects a nation left beige early.

**Shared Utilities**

The `Systems/Functions/` directory contains shared utility modules used across all systems:

- **config.py** — Loads all environment variables from `.env` and provides them as module-level constants.
- **database_manager.py** — Manages database connections and provides helper functions for database operations.
- **user_data_manager.py** — Manages user data profiles and syncs Discord user information.
- **discord_user_sync.py** — Syncs Discord user data (avatar, username, etc.) for multiple users.
- **emoji.py** — Provides emoji utilities and custom emoji mappings.
- **utils.py** — General utility functions including Cloudflare tunnel management, web URL generation, and service port cleanup.
- **beige_alerts_db.py** — Manages beige alert records in `alerts.db` with functions for creating, updating, deleting, and querying alerts.
- **db_paths.py** — Centralized database path definitions for all database files.
- **graph_utils.py** — Utilities for generating graphs and charts using Matplotlib and Plotly.
- **autocomplete_utils.py** — Utilities for Discord autocomplete dropdowns.
- **cooldown_db.py** — Manages command cooldowns in a database.
- **nation_emoji_store.py** — Stores custom emoji assignments for nations and alliances used in autocomplete.
- **pets_db.py** — Database manager for the pets system.
- **tasks_db.py** — Database manager for the daily/weekly task system.
- **ss_db.py** — Database manager for the Survivor Series game.
- **pet_stock_engine.py** — Engine for the pet stock market simulation.
- **pet_stock_events.py** — Event system for pet stock market events.
- **local_ai.py** — Local AI utilities for fallback when external AI APIs are unavailable.
- **ai_brain.py** — AI opponent logic for games like RPS.
- **ai_gambling.py** — AI utilities for casino games.
- **optimal_file_manager.py** — Manages optimal file storage and retrieval.
- **cloudflare_cache.py** — Manages Cloudflare CDN cache purging.
- **discord_utils.py** — Discord-specific utility functions.
- **last_seen.py** — Saves the last seen timestamp when the bot disconnects.
- **irs_nations_db.py** — Backward-compatibility alias for GlobalNationsDB.
- **irs_nations_manager.py** — Utility for syncing nation data from the PnW API.
- **irs_wars_db.py** — Database manager for war data.
- **irs_wars_manager.py** — Utility for syncing war data from the PnW API.
- **web_server.py** — FastAPI web server implementation with all API endpoints and static file serving.

---

## Database Structure

All data is stored locally in SQLite databases under the `Databases/` directory. The bot creates the necessary subdirectories automatically on first run — you do not need to create them manually.

### Databases/Pets/

Pet system data:

- **pets.db** — All pet profiles, user relationships (friend/foe/enemy/best friend), and the bazaar marketplace. The primary store for the entire pet system.
- **Tasks.db** — Daily and weekly task assignments per user, completion state, and reward tracking.
- **absorb.db** — Survivor Series game state: elimination rounds, procedural map data, and per-round results.
- **colosseum.db** — Automated hourly Colosseum tournament results and leaderboard.
- **dungeon.db** — Dungeon crawl session state for active and completed runs.
- **powerball.db** — Powerball lottery ticket purchases and draw history.
- **survivorseries.db** — Survivor Series event registration and bracket state.

### Databases/PnW/

Politics & War data (maintained by the separate PnWHarvester process, read-only by Reaper):

- **GlobalNations.db** — The central nation database. Stores a complete snapshot of every nation in the game with identity, alliance, stats, military, policies, projects, status, holdings, and a full city table with every improvement slot for every city.
- **IRSWars.db** — The primary war database for Darkstar. Stores every war involving a Darkstar nation with full attack-level detail.
- **WeeklyNews.db, MonthlyNews.db, YearlyNews{YYYY}.db** — News databases with identical schemas covering different time windows (current week, current month, full calendar year).
- **bankrecs.db** — Stores every bank transfer in the game received via the `bankrec/create` subscription.
- **holdings.db** — Tracks the actual money and resource holdings for every nation in real-time.

### Databases/ (root)

Core bot data:

- **reaper.db** — The core bot database. Stores resource market prices (updated every PnW turn), color bloc bonuses, radiation levels, and other game-state data used across multiple systems.
- **Tickets.db** — Stores all support ticket records: ticket ID, channel ID, applicant Discord ID, ticket type, nation or alliance ID, creation timestamp, and current status.
- **alerts.db** — Stores two types of user alerts: beige alerts (set when a target nation is on beige) and resource price alerts (one-shot alerts that fire when a resource's buy or sell price crosses a threshold).
- **zombie.db** — Stores zombie survival game state: active game sessions, player status, story progression, and AI-generated narrative history.

No database credentials are required. All files are local and self-contained.

---

## Technical Architecture

### Startup Sequence

The bot follows a carefully ordered startup sequence defined in `reaper.py`:

1. **Virtual Environment Check** — If not running inside the project venv, re-exec using the venv Python so all packages are available.
2. **Dependency Setup** — Checks Python virtual environment and Node.js dependencies. Installs if missing.
3. **Bot Instance Creation** — Creates Discord bot instance with proper intents (message_content, members, guilds).
4. **Cog Loading** — Loads command cogs in organized sets:
   - Admin: `Systems.admin`, `Systems.info`
   - Mythical: `Systems.Astrology.signs`, `Systems.Astrology.reading`
   - Fun: `Systems.Fun.zombie`, `Systems.Fun.goodevil`, `Systems.Fun.fun_system`, `Systems.Fun.compete`, `Systems.Fun.troll`
   - PnW: `Systems.PnW.pnwhopper`
   - Management: `Systems.Functions.nations_manager_cog`
   - Tickets: `Systems.Tickets.tickets`
5. **Command Sync** — Syncs application command tree with Discord.
6. **Web Server Start** — Starts the embedded FastAPI web server on port 8080 and waits for it to be ready.
7. **Cloudflare Tunnel** — If enabled, starts the Cloudflare tunnel for public access.
8. **Background Tasks** — Starts periodic user sync and beige notification loops.

### Web Server

The web server is implemented in `Systems/Functions/web_server.py` using FastAPI and Uvicorn. It serves:

- **Static files** — CSS, JavaScript, images, and emoji assets from `web/static/`, `web/css/`, `web/js/`.
- **HTML pages** — All pet and PnW web interface pages from `web/Pages/`.
- **API endpoints** — RESTful APIs for pet data, PnW data, authentication, and WebSocket connections for real-time casino updates.

The server starts automatically when the bot starts and runs in the background. It shares the same event loop as the Discord bot.

### Logging

Logging is configured in two phases:

1. **Startup logging** — Writes to `reaper_startup.log` during the dependency check and bot initialization phase.
2. **Runtime logging** — After the bot is ready, switches to `reaper_bot.log` for ongoing operation.

Logs include timestamps, logger name, log level, and message. Both files are overwritten on each bot restart.

### Error Handling

The bot includes comprehensive error handling:

- **Duplicate session detection** — Catches Discord error 40062 and provides a clear message if another bot instance is already running.
- **Connection errors** — Handles GatewayNotFound, ConnectionClosed, and HTTPException with appropriate logging and cleanup.
- **Cog loading errors** — Logs which cogs failed to load and continues with the remaining cogs.
- **Background task errors** — All background loops have try/except blocks with logging and retry logic.

### PnW Data Pipeline

The bot reads PnW data from local databases maintained by the separate PnWHarvester process. This separation ensures:

- The bot is never blocked waiting for API responses
- The databases are always current regardless of whether the bot is running
- API rate limits are managed centrally by the harvester

The bot is read-only against `GlobalNations.db` and `IRSWars.db` — it never writes to these files directly. All writes are handled by the harvester.

### Security

- **No external data storage** — All data stays local on your machine
- **API keys in .env only** — Never logged or echoed
- **Discord OAuth2** — No passwords stored for web authentication
- **Ephemeral responses** — Translations and sensitive data are delivered as ephemeral messages where possible
- **.gitignore** — The `.env` file and all databases are excluded from version control

### Performance

- **Database caching** — Query results are cached with appropriate TTLs
- **WAL mode** — Databases use Write-Ahead Logging for concurrent reads and writes
- **Async operations** — All database and API operations are async to avoid blocking
- **Background processing** — Heavy operations (graph generation, large calculations) run in background threads or processes
- **WebSocket** — Casino updates use WebSocket for real-time communication without polling

---

## Dependencies

The bot requires the following Python packages (see `requirements.txt`):

### Discord & Web Framework
- discord.py==2.3.2
- python-dotenv>=1.0.1
- fastapi>=0.115.0
- uvicorn[standard]>=0.30.0
- websockets>=12.0
- flask>=3.1.3
- jinja2>=3.1.4
- starlette>=0.41.0
- aiohttp>=3.10.0
- httpx>=0.27.0
- requests>=2.31.0
- async-timeout>=4.0.3
- itsdangerous>=2.2.0
- pydantic>=2.7.0,<3.0.0

### AI, APIs & External Services
- groq>=0.9.0

### Data, Analytics & Visualization
- pandas>=2.2.0
- numpy>=1.26.4
- lttb>=0.3.2
- matplotlib>=3.9.0
- plotly>=5.22.0
- kaleido==0.2.1
- Pillow>=10.3.0
- networkx>=3.3
- beautifulsoup4>=4.12.0
- markdown>=3.6
- aiosqlite>=0.20.0

### System & Utilities
- psutil>=5.9.8
- aiofiles>=23.2.1
- tqdm>=4.66.4
- python-editor>=1.0.4
- reportlab>=4.2.0
- pnwkit-py>=2.6.26
- pywin32>=306 (Windows only)

### Core Dependencies & Types
- werkzeug>=3.0.3
- blinker>=1.8.0
- python-multipart>=0.0.9
- click>=8.1.7
- markupsafe>=2.1.5
- typing-extensions>=4.12.0
- typing-inspection>=0.4.0
- annotated-doc>=0.0.4
- attrs>=23.2.0
- certifi>=2024.2.2
- charset-normalizer>=3.3.2
- frozenlist>=1.4.1
- idna>=3.7
- multidict>=6.0.5
- six>=1.16.0

### Testing
- pytest>=9.0.0
- pytest-asyncio>=0.23.0

### Node.js Dependencies

The web frontend requires Node.js packages defined in `package.json`:

- bootstrap — CSS framework
- three — 3D graphics library
- gsap — Animation library

---

## License

See LICENSE.txt for license information.

---

## Support

For issues, questions, or contributions, please refer to the project repository or contact the development team.
