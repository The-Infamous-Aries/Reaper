# ReaperBot

> A self-hosted Discord bot that somehow became a full RPG, a war intelligence platform, a casino, a stock market, a dungeon crawler, a poker table, a tarot reader, a ticket desk, a zombie survival game, and a real-time geopolitical surveillance system — all because someone wanted a digital pet.

---

## Table of Contents

- [💀 The Reaper (Overview)](#the-reaper-overview)
- [🧰 Configuration and Environment](#configuration-and-environment)
- [🌟 Major Features](#major-features)
  - [🐾 Pets Website System](#pets-website-system)
  - [♟️ PnW Website System](#pnw-website-system)
  - [⚔️ PnW Discord System](#pnw-discord-system)
    - [🏦 EA — Economic Affairs](#ea--economic-affairs)
    - [🏨 FA — Foreign Affairs](#fa--foreign-affairs)
    - [🏛️ IA — Internal Affairs](#ia--internal-affairs)
    - [🏭 MA — Military Affairs](#ma--military-affairs)
    - [⚾ Other — Fun PnW Stuff](#other--fun-pnw-stuff)
    - [🏴‍☠️ Util — Core Utilities](#util--core-utilities)
  - [🎫 Tickets System](#tickets-system)
  - [💱 Translator System](#translator-system)
  - [🔮 Astrology System](#astrology-system)
  - [🤹 Fun System](#fun-system)
  - [📡 PnW Subscriptions and Query](#pnw-subscriptions-and-query)
  - [🗄️ PnW Nation/War Tracking DB Files](#pnw-nationwar-tracking-db-files)

---
---

## The Reaper (Overview)

ReaperBot is a self-hosted Discord bot built in Python. It runs entirely on your own machine — no cloud hosting, no third-party bot service, no subscription. Everything stays local: your data, your databases, your API keys.

The bot has two main sides. The **Discord side** handles slash commands and text commands directly in your server — PnW intelligence, pet games, tickets, translation, astrology, and entertainment. The **web side** runs a FastAPI server embedded inside the bot process, serving a full browser-based interface for the pet system and PnW analytics tools at your configured domain.

Both sides start from a single command (`python reaper.py`) and share the same local SQLite databases. There is no separate web server to manage, no Docker container required, and no database server to configure.

**What it does:**

- **Pets** — a complete digital pet RPG with stats, elements, equipment, an ability tree, turn-based combat, PvP, tournaments, dungeon crawls, casino games, quests, a stock market, and a full browser-based interface for all of it.
- **Politics & War** — deep integration with the PnW game: real-time nation and war tracking via live subscriptions, revenue and cost calculators, war intelligence dashboards, raid finders, treaty maps, alliance comparisons, beige alerts, resource price alerts, and a global news/leaderboard system.
- **Tickets** — a structured support ticket system with category routing, staff assignment, and transcript logging.
- **Translator** — automatic message translation using LibreTranslate, with per-channel language configuration.
- **Astrology** — daily horoscopes, tarot readings, and zodiac compatibility checks.
- **Fun** — roasts, compliments, a zombie survival game, and other entertainment commands.

The bot is designed for the Nights Watch alliance (PnW alliance 14225) but the PnW tools work for any alliance or nation. The pet system is entirely self-contained and has no PnW dependency.

---

## Configuration and Environment

ReaperBot is configured entirely through a single `.env` file located at `Systems/Functions/.env`. The bot reads this file on startup — no environment variables need to be set at the system level, and there is no fallback to a root-level `.env`. If the file is missing or the Discord token is absent, the bot will not start.

All secrets stay local to your machine. Nothing is transmitted externally except the specific API calls each key is used for (Discord, PnW, AI providers, etc.). The `.env` file is excluded from version control via `.gitignore`.

**Starting the bot** is a single command from the project root:

```bash
python reaper.py
```

On first run, the bot automatically checks for its Python virtual environment and Node.js dependencies. If either is missing or incomplete it installs them before proceeding — no manual setup steps required.

**Required**

| Variable | Purpose |
|:---|:---|
| `DISCORD_TOKEN` | Your bot's authentication token from the Discord Developer Portal. The bot will not start without this. |

**Optional — Bot Behaviour**

| Variable | Purpose | Default |
|:---|:---|:---|
| `COMMAND_PREFIX` | Prefix for legacy text commands. | `!` |
| `ADMIN_USER_ID` | Discord user ID of the server owner. Gates admin-only commands. | `0` (disabled) |
| `RESULTS_CHANNEL_ID` | Channel ID where game results and logs are posted. | `0` (disabled) |
| `DATA_DIR` | Base directory for data storage. Useful for containerised deployments. | Current working directory |

**Optional — AI Features**

| Variable | Purpose |
|:---|:---|
| `GEMINI_API_KEY` | Google Gemini. Powers the Zombie survival AI story system. |
| `GROQ_API_KEY` | Groq (Llama 3.1). Powers Tarot readings, roasts, and compliments. |

**Optional — Politics & War**

| Variable | Purpose |
|:---|:---|
| `PANDW_API_KEY` | PnW API v2 key. |
| `PANDW_API_V3_KEY` | PnW API v3 key. Used for all GraphQL queries across PnW commands. |
| `PANDW_BOT_KEY` | PnW bot key. |

**Optional — Other APIs**

| Variable | Purpose |
|:---|:---|
| `HORSCOPE_API` | Aztro API key for daily horoscopes in the Astrology system. |
| `GIPHY_KEY` | Giphy API key for GIF responses in the roast/compliment system. |
| `PIXABAY_KEY` | Pixabay API key for image responses in the roast/compliment system. |

**Optional — Web & Cloudflare**

| Variable | Purpose | Default |
|:---|:---|:---|
| `CUSTOM_DOMAIN` | The public-facing domain for the web interface. | `https://reaper.qzz.io` |
| `USE_CLOUDFLARE_TUNNEL` | Set to `true` to automatically start the Cloudflare tunnel on bot startup. | `false` |
| `CF_ACCOUNT_ID` | Cloudflare account ID. Required for cache purge operations. | — |
| `CF_TUNNEL_ID` | Cloudflare tunnel ID for named tunnel routing. | — |
| `CF_API_TOKEN` | Cloudflare API token. Used to purge the CDN cache programmatically. | — |
| `CF_TUNNEL_TOKEN` | Cloudflare tunnel authentication token. | — |
| `CF_CREDENTIALS_FILE` | Path to the Cloudflare tunnel credentials JSON file. | — |

**Databases**

All data is stored locally in SQLite databases under the `Databases/` directory. The bot creates the necessary subdirectories automatically on first run — you do not need to create them manually. There are two groups:

- `Databases/PnW/` — Politics & War data: nation tracking, war records, bank transactions, resource holdings, and news archives.
- `Databases/Pets/` — Pet system data: pet profiles, tasks, casino games, tournaments, and events.
- `Databases/` (root) — Core bot data: resource market prices, game state, beige alerts, support tickets, and zombie game state.

No database credentials are required. All files are local and self-contained.

---

## Major Features

---

### Pets Website System

The Pets Website System is a full browser-based interface for the entire pet experience. It runs as a FastAPI web server embedded inside the bot, accessible at the configured domain (`https://reaper.qzz.io` by default) or locally at `http://localhost:8080`. No separate server setup is needed — it starts automatically when the bot starts.

**Authentication**

Access to any personal pet data requires logging in with Discord OAuth2. The login flow redirects to Discord's official authorization page, requests only the `identify`, `email`, and `guilds` scopes, and stores the session server-side. Access tokens are automatically refreshed in the background — users are never interrupted mid-session by an expired token. Avatar and profile data sync to the local database on every login and on a 60-second refresh cycle. No passwords are stored; authentication is entirely delegated to Discord.

**Dashboard**

The main entry point is `web/dashboard.html` — a single-page application that loads all other pages dynamically without full page reloads. It displays the bot's avatar and name, provides sidebar navigation between all sections, and adapts to desktop and mobile screen sizes.

**Pet Management**

The core pet pages let users adopt, view, train, and manage their pet entirely through the browser:

- **Adopt** (`what_are_pets.html`, `petconnector.html`) — new users are walked through the pet system and guided through choosing a species, category, element combination, and custom name. Adoption validates the name for safe characters and prevents duplicate pets per user.
- **My Pet** (`mypet.html`) — displays the pet's full stat sheet with computed values, XP bar, level, inventory, equipped items, and battle action labels. Users can rename their pet and set custom names for their three battle actions (Attack, Defense, Charge).
- **Pet Roster** (`pets.html`) — a broader view of all pets registered in the system, used for game entry and social browsing.
- **Ability Tree** — an interactive skill tree where users spend stat mastery points and unlock combat abilities for their pet.
- **Bazaar** (`bazaar.html`) — an in-world marketplace for pet items and equipment.

**Activities**

Pets can be sent on activities directly from the web interface. Each activity has a short cooldown enforced server-side and persisted to the database so it survives bot restarts:

- **Train** — choose a stat (ATT, DEF, INT, DEX, HAP, ENE) and a difficulty. Success increases the stat; failure decreases it. Equipment multipliers scale the change.
- **Mission** — send the pet on a mission at Easy, Average, or Hard difficulty. Success awards XP and key loot scaled to the pet's level. Players can optionally gamble additional XP on the outcome.
- **Play** — send the pet to one of twelve locations (Camp, Beach, Forest, Mountain, Glacier, Pyramids, etc.). XP and key loot are influenced by the pet's elements and the location's special properties.
- **Quest** — a multi-stage adventure with branching choices. Each stage presents a scenario and options; the outcome depends on the pet's stats and the player's decisions.

**Casino**

The casino is a fully multiplayer, room-based system. The lobby (`casino_lobby.html`) shows 12 live rooms with real-time state broadcast over WebSocket — players can see who is in each room, what game is running, and whether seats are available, all without refreshing.

Games available:

- **Slots** (`casino.html`) — solo slot machine with multiple difficulty tiers and animated reels.
- **Blackjack** (`blackjack.html`) — up to 6 players at a table. Supports standard blackjack rules including double-down and split.
- **Texas Hold'em** (`holdem.html`) — up to 6 players with AI opponents filling empty seats. Full poker hand evaluation.
- **Craps** (`craps.html`) — one active roller with observers who can place side-bets on the outcome. The roller can pass the dice to an observer.
- **Pet Races** (`races.html`) — up to 4 pets race simultaneously. Observers can bet on any racer before the race starts.
- **Mini-Games** (`minigames.html`) — a collection of shorter head-to-head games.

Observers in any room can watch live game state updates and, in supported games (Craps, Races), place side-bets on active players. Pending seat requests let observers queue to join at the start of the next round without interrupting an active game. All XP wagers are deducted immediately on placement and paid out (or forfeited) when the round resolves.

**Other Pet Games and Features**

- **Arena** (`arena.html`) — PvP and PvE combat using the full battle system with skills, abilities, and damage calculations.
- **Colosseum** (`colosseum.html`) — automated hourly tournament battles between registered pets. Results are tracked on a leaderboard.
- **Dungeon** (`dungeon.html`) — a crawl-style dungeon with procedurally generated encounters.
- **Survivor Series** (`survive.html`) — a battle royale format where multiple pets compete across elimination rounds on a procedural map.
- **Tasks** (`tasks.html`) — a daily and weekly task system. Each pet owner has a set of active tasks that refresh on a schedule. Completing tasks (training, missions, playing, renaming) earns bonus rewards.
- **Pet Stock Market** (`pet_stock.html`) — a simulated resource stock market tied to pet economy events. Prices update on an hourly loop.
- **Powerball** (`powerball.html`) — a lottery system where players buy tickets with XP for a chance at a large jackpot.
- **Wheel of Pets** (`wheel.html`) — a spin-the-wheel game with variable XP prizes.
- **Scratch Cards** (`scratch.html`) — instant-win scratch card games.
- **Keno** (`keno.html`) — a number-pick lottery game.
- **Leaderboard** (`leaderboard.html`) — global rankings across multiple categories (level, XP, battle wins, casino earnings, etc.).
- **Game Info** (`game_info.html`) — a reference page showing current resource prices, color bonuses, and other live game data.
- **Battle Config** (`battle_config.html`) — lets users configure their pet's preferred battle settings and action priorities.

**Library**

The library (`library.html`) is an in-app documentation and guide system. It serves Markdown files from `web/Pages/Library/` as formatted articles covering game mechanics, strategy guides, and doctrine documents. Content is rendered client-side from the raw Markdown files served by the library API.

**Static Assets**

All CSS, JavaScript, images, and emoji assets are served directly from the web server. CSS files are scoped per page (one stylesheet per major feature). JavaScript handles all interactive UI — casino animations, 3D dice rolling via BabylonJS, slot machine reels, and real-time WebSocket updates. Static assets are cached at the CDN layer for up to one hour; HTML pages and API responses are never cached.

---

### PnW Website System

The PnW Website System is the browser-based interface for all Politics & War analytics, intelligence, and tracking tools. It runs on the same FastAPI web server as the Pets system and is accessible at the same domain. Most pages are publicly viewable without logging in; features that save personal data (such as beige alerts and resource price alerts) require Discord login.

All data served by this system comes from two sources: the local `GlobalNations.db` and `IRSWars.db` databases maintained by the PnWHarvester, and the live PnW GraphQL API for data not yet in the local store. The local database is always queried first — API calls are only made when local data is insufficient or a live refresh is explicitly requested.

**Watch Page** (`watch.html`)

The Watch page is the primary war intelligence dashboard for Nights Watch (alliance 14225). It reads directly from the local `IRSWars.db` — no API calls are made for this page. Users can select any date range within the available war history and the page calculates a full breakdown for every nation that fought in that window:

- Gross cost (units lost, infrastructure destroyed, improvements lost, gasoline and munitions consumed)
- Net damage dealt to opponents
- Loot gained and lost, broken down by cash and each resource with monetary values at current market prices
- Per-nation opponent breakdown showing exactly who fought whom and the cost/gain on each side
- Alliance-wide totals row aggregating all nations

War data is cached for 2 minutes per date range to avoid redundant recalculation on repeated requests. Revenue calculations are pre-warmed at each PnW turn boundary (every 2 hours) so the first request after a turn change is never slow.

**Nations Page** (`nations.html`)

A searchable, filterable view of all nations tracked in `GlobalNations.db`. Supports searching by nation name, leader name, or alliance. Displays score, city count, military units, war policy, projects, and activity status. Data is read entirely from the local database — no API calls.

**Revenue Page** (`revenue.html`)

Calculates the full per-turn and per-day revenue for any nation or alliance. Uses the complete city-build engine accounting for improvements, projects, color bloc bonuses, radiation levels, seasonal modifiers, and current resource market prices. For Nights Watch nations, data comes from `GlobalNations.db`; for other alliances, it falls back to the live PnW API.

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

For Nights Watch, data is read from `GlobalNations.db`. For other alliances, the live PnW API is queried. An interactive HTML comparison report can also be generated and saved to `Systems/web/Comparisons/`.

**Raids Page** (`raids.html`)

A raid target finder that searches `GlobalNations.db` for nations within war range of a given attacker. Filters available: inactive only, militarily weak only, beige targets only, minimum projected loot, excluded alliances, and maximum active defensive wars. For each candidate it calculates a projected loot value using live holdings data from `holdings.db` (actual money and resources held, net of all spending and transfers) with a revenue-based fallback when holdings data is unavailable. Results are sorted by projected loot descending.

The page also manages **beige alerts** — per-user notifications set when a target nation is on beige. Alerts are stored in `alerts.db` and the bot sends Discord DMs at two thresholds: ~2 hours before beige expires and ~15 minutes before. Alerts can be set, refreshed, and deleted from the web interface. Refreshing pulls live `beige_turns` from the PnW API and recalculates projected loot from current holdings.

**Weapons Page** (`weapons.html`)

Missile and nuclear weapon efficiency calculator with two modes:

- **Theory mode** — given any infrastructure level and population density, calculates minimum, maximum, and average damage and infrastructure value destroyed for both missiles and nukes. Shows cost-multiplier thresholds (the infrastructure level needed for a weapon to deal 1×, 2×, 5×, 10× its cost in damage) and a full damage chart across multipliers.
- **Targeted mode** — given a specific nation or alliance, scores every city by expected damage value, accounting for Iron Dome (30% missile block chance) and Vital Defense System (25% nuke block chance). Alliance mode ranks all nations by their best-city missile damage, making it easy to identify the highest-value targets.

All calculations use live resource prices from the local database to keep weapon costs current.

**News Page** (`news.html`)

A global PnW event feed and leaderboard system backed by the news databases maintained by the PnWHarvester. Supports four time periods: current week, previous week, current month, previous month, and yearly archives. Features:

- **Event feed** — paginated list of war declarations, war endings, city builds, project purchases, alliance changes, and other game events. Filterable by event type, alliance, or nation. Nation and alliance IDs are resolved to real names from `GlobalNations.db`.
- **Alliance leaderboard** — ranked by wars declared, wars won, loot gained, nukes used, missiles used, cities built, projects bought, and total spending.
- **Nation leaderboard** — same metrics at the individual nation level, filterable by alliance.
- **Summary cards** — high-level world totals for the selected period (total wars, total loot, total nukes, etc.).
- **War cost drill-down** — clicking a war event shows the full cost breakdown for both sides pulled from `IRSWars.db`.
- **Live search** — searches nations and alliances by name across `GlobalNations.db` for quick filtering.
- **Resource prices** — current sell prices shown alongside loot values so resource loot is displayed in monetary terms.

**Resource Price Alerts** (`watch.html` / alerts panel)

Users can set price threshold alerts for any of the 12 PnW resources (food, coal, oil, uranium, lead, iron, bauxite, gasoline, munitions, steel, aluminum, credit). Each alert specifies a resource, buy or sell price, direction (above or below), and threshold value. Alerts are stored in `alerts.db` and checked by the bot's timed query loop, which sends a Discord DM when a threshold is crossed. Alerts can be managed entirely from the web interface.

---

### PnW Discord System

The PnW Discord System is the collection of slash and hybrid commands that bring Politics & War intelligence directly into your Discord server. Commands are organized into five functional groups — Economic Affairs, Foreign Affairs, Internal Affairs, Military Affairs, and a miscellaneous group for fun PnW tools — plus a Util group covering core bot utilities shared across all systems.

All PnW commands read from the local `GlobalNations.db` and `IRSWars.db` databases first. Live API calls are only made when local data is insufficient or a real-time refresh is explicitly needed. This keeps commands fast and keeps your API key usage low.

#### EA — Economic Affairs

The Economic Affairs module provides Discord commands covering market intelligence, revenue analysis, economic optimization, and price alerting. All commands are slash/hybrid commands available in any channel the bot has access to.

**`/turn_bonuses`**

Displays the current turn bonus for every color bloc in Politics & War, sorted from highest to lowest. Each color is shown with its custom emoji, bloc name, and dollar bonus per turn. The embed color matches the highest-bonus color at the time of the query. Data is fetched live from the PnW API on each call.

**`/game_info`**

Shows the current state of the PnW game world in a rich embed with an attached pie chart. Covers:

- Current in-game date
- Top 20% city average (the benchmark used for score calculations)
- Global radiation level
- Per-continent radiation breakdown (North America, South America, Europe, Africa, Asia, Australia, Antarctica), sorted highest to lowest

The pie chart is generated server-side using PIL — slice brightness scales with each continent's share of total radiation so the visual immediately shows which regions are most affected.

**`/game_resources`**

Plots historical resource and money holdings across the entire game world over a selected time window. Accepts flexible date inputs (`7d`, `2w`, `3m`, `2024-01-01`, `7 days ago`, etc.) and lets you choose which graphs to display: Money, Food, Manufactured resources (Steel, Aluminum, Gasoline, Munitions), Raw resources (Uranium, Coal, Oil, Iron, Bauxite, Lead), or any individual resource. Each graph shows absolute values over time with annotated data points and a date-range title. Rendered using Matplotlib in a background thread to avoid blocking the bot.

**`/revenue`**

Calculates the full per-turn and per-day revenue breakdown for a nation or an entire alliance. Accepts nation/alliance name or ID with autocomplete backed by `GlobalNations.db`. An optional `tax_rate` override lets you model different tax bracket scenarios.

For a **nation**, the embed shows:
- Gross income, color bloc bonus, military upkeep, improvement upkeep, power upkeep, resource upkeep
- Net cash per turn and per day
- Per-resource production with monetary value at current sell prices
- Total monetary net (cash + resource value)

For an **alliance**, the embed aggregates all active members (excluding vacation mode and applicants) and shows alliance-wide totals for all the same fields, plus the alliance tax income (from black-color nations), a color distribution breakdown, and a ranked list of top earners. Up to 20 nations are processed concurrently.

Revenue calculations use the full game engine: city improvements, projects, domestic policy, color bloc bonus, radiation penalties, seasonal food modifiers, and current market prices — all loaded from the local database with no API calls for Nights Watch nations.

**`/rev_optimizer`** (also available as the web Revenue Optimizer page)

Runs a full economic optimization analysis on a nation or every nation in an alliance. For each city it simulates every possible improvement change and ranks them by daily gain. Suggestions are grouped into:

- **Civil improvements** (commerce, crime, disease, pollution) — only suggested when the city actually has a problem worth fixing (crime above 3%, disease above 2%, pollution above 30)
- **Resource improvements** — only suggested if the nation already produces that resource or has all required inputs (no point suggesting a steel mill without coal and iron)
- **Rebuild suggestions** — detects cities missing improvements that other cities have, flagging likely war damage
- **Infrastructure** — only suggested when the nation is genuinely short on improvement slots and the ROI is under 90 days
- **Land** — suggested up to a 365-day ROI (permanent, compounds over time)
- **National projects** — ranked by daily gain with full cost calculation at current market prices, applying any existing project discounts

All gains are fully simulated — no approximations. Results are sorted globally by daily gain so the highest-value actions appear first.

**`/stocks`**

Displays current PnW market prices for all 12 resources (Food, Coal, Oil, Uranium, Lead, Iron, Bauxite, Gasoline, Munitions, Steel, Aluminum, Credit) with price change indicators compared to 2 hours ago. Shows dollar change, percentage change, and directional arrows for each resource. Attaches a 30-day price trend graph (All Resources, Raw Resources, Manufactured Resources, Food, or Credit — selectable). Graph is rendered using Plotly with the custom dark Discord theme in a separate process to avoid blocking.

**`/history`**

Opens a modal dialog for selecting a custom date range and generates a historical price chart for that window. Pulls from the full local price history database. Uses LTTB (Largest Triangle Three Buckets) downsampling to keep graph performance fast even over long date ranges.

**`/rss_alert_set`**

Sets a one-shot price alert for any of the 12 PnW resources. Parameters:
- **Resource** — autocompleted from the valid resource list
- **Price type** — best Buy price or best Sell price
- **Direction** — fires when price rises to/above (≥) or drops to/below (≤) the threshold
- **Threshold** — the PPU value that triggers the alert

Alerts are stored in `alerts.db` and checked after every timed resource data save (each PnW turn). When triggered, the bot sends a Discord DM with the resource, your threshold, and the current price, then removes the alert. Each alert fires exactly once.

**`/rss_alert_remove`**

Removes a specific active alert before it fires. Requires the same resource, price type, and direction used when setting it.

**`/rss_alert_list`**

Lists all your currently active resource price alerts with their resource, price type, direction, and threshold.

#### FA — Foreign Affairs

The Foreign Affairs module provides Discord commands for visualizing and tracking diplomatic relationships between alliances in Politics & War. Both commands are slash/hybrid commands.

**`/treaties`**

Displays the full treaty web for any alliance. Accepts an alliance name or ID and produces two outputs simultaneously: a rich Discord embed and a generated treaty web image.

The **embed** lists all active treaties grouped into four categories, each with its own emoji header:

- **Protection & Extensions** — Protectorate and Extension treaties
- **MDoAP & MDP** — Mutual Defense Optional Aggression Pacts and Mutual Defense Pacts
- **ODoAP & ODP** — Optional Defense Optional Aggression Pacts and Optional Defense Pacts
- **PIAT & NAP** — Peace Intelligence and Aid Treaties and Non-Aggression Pacts

Each treaty partner is shown as a masked hyperlink to their PnW alliance page. Long lists are automatically split across multiple fields to stay within Discord's embed limits.

The **treaty web image** is a 1600×1200 pixel diagram generated server-side using PIL. The center alliance's flag is placed at the center of the image. Treaty partners are arranged in concentric rings by treaty strength:

- Innermost ring — Protectorates and Extensions
- Second ring — MDoAP and MDP partners
- Third ring — ODoAP and ODP partners
- Outer ring — PIAT and NAP partners

Each partner's alliance flag is fetched from the PnW CDN and placed at their position on the ring. Connecting lines are color-coded by treaty type (dark blue for MDoAP, light blue for MDP, gold for ODoAP, yellow for ODP, light red for Protectorate, dark red for Extension, light green for NAP/PIAT). Lines are drawn as Bézier curves that automatically route around overlapping flags. Inter-bloc treaties between partners are also drawn, showing the full diplomatic network rather than just direct relationships with the center alliance. A legend with custom Discord emojis is included in the image.

The message includes a **Refresh** button that re-fetches live treaty data from the PnW API and regenerates both the embed and image in-place, editing the existing message rather than posting a new one. The button persists across bot restarts — active message IDs and their alliance associations are saved to `Systems/Data/Treaty/treaties_views.json` and restored on startup.

The optional `auto_update` parameter (True/False) enables a **daily auto-update** for the posted message. When enabled, a background task checks every hour and regenerates the treaty web once per 24 hours, keeping the message current without any manual intervention. Auto-update state is saved to `Systems/Data/Treaty/treaties_auto_update.json` and survives restarts. If the original message is deleted, the auto-update entry is automatically cleaned up.

**`/treaty_universe`** (aliases: `/treaty_map`, `/universe`)

Generates an interactive treaty map centered on any alliance and returns a link to it. The map is rendered as a full interactive web page served by the bot's web server — the link opens directly in a browser. It shows the center alliance's direct treaty partners and their own treaty connections, giving a broader view of the diplomatic neighborhood than the static image. The page is generated on demand and the link is valid as long as the web server is running.

#### IA — Internal Affairs

The Internal Affairs module provides Discord commands for monitoring alliance health, auditing member compliance, looking up nation details, calculating build costs, and delivering in-game guides. All commands are slash/hybrid commands.

**`/alliance`**

The main alliance overview command. Accepts any alliance name or ID with autocomplete. Produces an interactive embed with five views navigable via buttons, all loaded from the same nation dataset without additional API calls:

- **Alliance Totals** (default view) — nation counts broken down by total, active (excluding vacation mode and applicants), and applicants. Score and city totals and averages. For Nights Watch specifically, also shows current resources held by active members (money, credits, and all 12 resources). Categorized lists of grey nations, beige nations, vacation mode nations, nations inactive 7–13 days, and nations inactive 14+ days — each nation shown as a hyperlink to their PnW page with days inactive noted where relevant.
- **Military** — alliance-wide military capacity: current vs maximum soldiers, tanks, aircraft, and ships; daily production for all six unit types including missiles and nukes; units needed to reach maximum capacity; and time-to-max per unit type showing which nation is the bottleneck.
- **Improvements** — total improvement counts across all active nations for every improvement type.
- **Project Totals** — count of how many active nations hold each of the 40+ national projects.
- **Refresh** — re-fetches live data and regenerates the current view.

For Nights Watch, nation data is read from `GlobalNations.db` with city data attached. For other alliances, `GlobalNations.db` is checked first and the live PnW API is used as a fallback.

**`/audit`**

Audits an alliance for compliance issues. Accepts an alliance name or ID and a view type:

- **Inactives** — lists nations inactive 7–13 days and 14+ days, vacation mode nations, grey nations, and beige nations. Each nation is a hyperlink with days inactive shown.
- **Color** — shows the color distribution of active members, flagging nations on grey or other non-optimal colors.
- **MMR Build** — checks every active member's per-city military improvement averages against a threshold. Two modes:
  - **Basic** — minimum threshold of 0/2/5/1 (barracks/factory/hangar/drydock per city average). Nations below this are flagged.
  - **Max** — full threshold of 5/5/5/3. Nations below this are flagged.

  Offenders are bucketed by how far below threshold they are: 50%+ off (red), 25–49% off (orange), 10–24% off (yellow), 0–9% off (green). Each nation shows their current average (e.g. `3.2/4.1/5.0/1.0`) and exactly how many of each improvement they need to build to reach the threshold. If all offenders fit in a single embed they are shown together; otherwise a paginated view with category buttons is used.

Applicants and vacation mode nations are excluded from all audit views. For Nights Watch, data comes from `GlobalNations.db` with cities attached for accurate per-city calculations.

**`/show`**

Looks up any nation by name, leader name, nation ID, or PnW link and displays a comprehensive nation profile. Autocomplete is backed by `GlobalNations.db`. The embed covers:

- Nation name, leader, alliance, position, color, beige turns (if applicable), vacation mode status
- Discord link, last active timestamp
- City count, average infrastructure, total infrastructure, total score
- Project slot usage (used/total, accounting for Research & Development Center and Military Research Center bonuses)
- City cooldown and project cooldown status
- Domestic policy and war policy
- Military units (soldiers, tanks, aircraft, ships, missiles, nukes)
- Wars won/lost, commendations, denouncements, money looted
- Achievement badges based on wars won, commendations, denouncements, and money looted thresholds
- All national projects the nation holds, grouped by category

For external (non-Nights Watch) nations, a Loot button is available that calculates projected loot from their most recent inactive war using actual attack data.

**`/costs`**

Calculates the cost of infrastructure, land, cities, and national projects for any nation, applying all relevant discounts. Accepts a nation name or ID with autocomplete.

Parameters let you specify:
- Target infrastructure level (applied to all cities or new cities being bought)
- Land amount to purchase
- Number of cities to buy
- One or more national projects to price out

The embed shows for each item:
- **Base cost** — raw cost with project discounts applied (Center for Civil Engineering, Advanced Engineering Corps, Arable Land Agency)
- **Final cost** — base cost further reduced by the relevant domestic policy discount (Urbanization for infra, Rapid Expansion for land, Manifest Destiny for cities, Technological Advancement for projects)
- **Total savings** — the difference between raw and final cost

For projects, resource costs are shown at current market buy prices alongside the money cost. The Technological Advancement policy discount scales with Bureau of Domestic Affairs and Government Support Agency multipliers. Infrastructure and land breakdown buttons show a per-city cost table for nations with multiple cities.

City cost uses the official PnW formula: `max(100000 × (city_to_buy − top20avg/4)³ + 150000 × (city_to_buy − top20avg/4) + 75000, city_to_buy² × 100000)`, with the current top-20% city average loaded from the local database.

**`/snipe_guide`**

Sends the complete 10-step beige sniping and raiding guide as three sequential messages with a 1-second delay between each. Covers finding targets with `/raids`, setting beige alerts, timing the war declaration to the exact turn boundary (x:00:30 for normal turns, x:10:00 for day change), the captcha timing window, and the optimal 7-attack raid sequence (5 naval + 3 ground). Written in the bot's characteristic voice.

**`/snipe_setup`**

Sends only the setup portion of the snipe guide (steps 1–4): running `/raids`, configuring target filters, and setting beige alerts.

**`/snipe_execute`**

Sends only the execution portion of the snipe guide (steps 5–10): opening the declare war page in advance, using a time site, captcha timing, the exact declaration moment, and the optimal attack sequence.

**`/war_guide`**

Sends a structured guide on PnW war mechanics. Accepts an optional `category` parameter to show a specific section or the full guide. Categories:

- **Ground Supremacy** — how to achieve it (Immense Triumph on first ground attack) and what it enables (aircraft destruction alongside ground forces)
- **Air Supremacy** — halves enemy tank effectiveness, allows targeting any unit type
- **Naval Blockade/Supremacy** — cuts off buying/selling/banking, enables targeting ground and air supremacy
- **Missiles** — infrastructure damage, improvement targeting by type (Resources, Manufacturing, Civil, Commerce, Military), Iron Dome interaction
- **Nukes** — massive infrastructure damage, city targeting only, cost threshold (not worth below 2500 infra), Vital Defense System interaction
- **Fortification** — when NOT to use it and better alternatives (Blitzkrieg policy, decommissioning, attacking a different front)
- **Peace** — reattack restrictions, when personal peace is acceptable vs when alliance war peace requires government approval
- **Key Strategy** — summary of all mechanics and the cardinal rule on alliance war peace

When no category is specified or `all` is selected, all sections are sent sequentially with 1-second delays between messages.

#### MA — Military Affairs

The Military Affairs module provides Discord commands for war intelligence, target finding, cost analysis, war performance tracking, and strategic planning. All commands are slash/hybrid commands.

**`/wars`**

Calculates the full cost breakdown for a war matchup between two sides. Accepts a team1 type (Alliance or Nation) and identifier, an optional time range (`1d`, `3w`, `5m`, etc.), and an optional team2 for a specific matchup. Autocomplete for team1 and team2 is backed by `IRSWars.db` — it suggests Nights Watch nations and the actual opponents they have fought, with no API calls.

For Nights Watch (alliance or individual member nations), all data is read from the local `IRSWars.db` with attacks attached. For other alliances, the live PnW API is used.

The result is a paginated embed with five views navigable via buttons:

- **Summary** — total gross cost, net damage, total gains, war count, and a per-war list with attacker/defender names, war type, reason, and winner. For large war sets a PDF report is generated instead.
- **Military** — unit losses (soldiers, tanks, aircraft, ships, missiles, nukes) with costs at current buy prices, and gasoline/munitions consumption.
- **Destruction** — infrastructure levels destroyed and their monetary value, improvements destroyed by type, and money destroyed in city attacks.
- **Loot** — cash looted, per-resource loot with monetary values, and net loot (gained minus lost).

**`/wars_cost_bd`**

Generates a full per-nation war cost breakdown for an alliance over a selected time window. Accepts an alliance name or ID and an optional time range (supports combined formats like `2m2w5d3h`). An `opps_view` flag flips the perspective to show the opponents' costs instead.

For Nights Watch, data comes from `IRSWars.db`. For other alliances, the live PnW API is queried.

The result is a paginated embed with five views:

- **Summary** — alliance totals with an attached bar chart image showing gross cost, net damage, and loot per nation.
- **Military** — unit losses and consumption totals.
- **Destruction** — infrastructure and improvement destruction totals.
- **Loot** — net loot with per-resource breakdown.
- **Leaderboard** — top 3 nations in six categories: Units Killed (by cost), Cities Destruction, Spent on Bombs, Least Costs, Looted the Most, and Best Net.

**`/wars_net_bd`**

Identical structure to `/wars_cost_bd` but calculates **net damage** (damage dealt to opponents minus own costs) rather than gross cost. The leaderboard's final category is Best Net Damage instead of Best Net. The summary chart shows net damage per nation. Useful for evaluating who performed best in a war rather than who spent the most.

**`/war`**

Simulates a full war between two nations turn by turn. Accepts attacker and defender by name, leader, or ID, a war type (Ordinary, Attrition, or Raid), and an optional spy report for more accurate loot calculation.

If `include_spy_op` is true, a modal dialog opens for pasting a spy report. The bot parses the report to extract the defender's actual money and resource holdings for precise loot projection.

The simulation runs the full war engine (`WarBrain`) and produces a paginated embed: a summary page showing winner, total turns, resistance changes, total infrastructure destroyed, resource consumption, loot gained, and attacker/defender casualties with costs — followed by one page per turn showing attack type, MAPs remaining, resistance values, casualties, purchases, and war status (ground control, air superiority, blockade) for both sides.

**`/compare_wars`**

Head-to-head war performance comparison between two Nights Watch member nations over a selectable time range (1 day to all time). Data comes entirely from `IRSWars.db` with attack-level detail for accurate loot and bomb counts.

Produces a 3-page paginated embed:

- **Summary** — side-by-side comparison of wars fought, total cost, damage dealt, war net, net loot, and bomb cost. Each metric shows a ✅/❌ winner indicator. A verdict line declares the overall winner by category score.
- **Nation 1 breakdown** — full cost breakdown (unit losses, infra lost, bombs fired, consumption, gross cost), damage dealt breakdown (enemy units, infra, consumption, loot taken, money destroyed, total damage), war net, loot (gained/lost/net with per-resource detail), and bombs used.
- **Nation 2 breakdown** — same structure.

**`/rankings`**

Shows the top 25 Nights Watch nations ranked by a selected war statistic over a chosen time range. Supports 16 ranking types: War Cost, War Net, Damages, Bomb Cost, Loot, Soldiers/Tanks/Aircraft/Ships Lost and Killed, Peace, Wins, and Losses. An optional enemy filter (autocompleted from actual opponents in `IRSWars.db`) narrows results to wars against specific alliances. Each nation is shown as a hyperlink to their PnW page with their value. Top 3 get medal emojis.

**`/raids`**

Finds raid targets within war range of a given nation. All candidate nations are loaded from `GlobalNations.db` — no API call. Holdings data is bulk-fetched from `holdings.db` for accurate loot projection (actual money and resources held, net of all spending and transfers). Revenue-based estimation is used as a fallback when no holdings row exists.

Filters available: active only (7+ days inactive excluded), weak military only, minimum projected loot, show/hide beige nations, exclude specific alliances (comma-separated, autocompleted), and maximum active defensive wars (0, 1, or 2). Results are sorted by projected loot descending and can be displayed as a Discord message or a PDF report.

**`/destroy`**

Finds optimal attacker groups from one or more alliances to coordinate a strike on a target nation. Accepts a target nation and one or more attacker alliances (comma-separated, autocompleted). Filters out inactive nations, nations with zero units, and nations with average infrastructure above 2000 (to minimize rebuild cost). Groups nations into parties of 3 that are all within war range of each other and the target, prioritizing unit coverage (ground, air, naval), warchest level, and activity. Returns up to 10 optimal groups ranked by a composite score.

**`/offshore`**

Scans an alliance's member bank records for external fund transfers that may indicate offshore banking activity. Reads directly from `bankrecs.db` over a configurable time window (up to 14 days). Automatically excludes:

- Internal alliance bank withdrawals (own alliance bank → member)
- Member-to-member transfers
- War bank loot (detected via `IRSWars.db` cross-reference and note field keywords)

For each member with a net positive external receive balance, shows the total value received, the top suspected source alliance, and a per-resource breakdown. An overview page lists the top 3 suspected offshore source alliances and the top 5 members by net received. Subsequent pages show the full per-member detail. Results are paginated with prev/next buttons.

**`/units`**

Interactive military unit cost calculator. Accepts optional starting quantities for soldiers, tanks, aircraft, ships, missiles, and nukes. Launches a live calculator embed with a **Recalculate** button that opens a modal for entering unit quantities in a flexible format (`soldiers:10000, tanks=1250, aircraft-75, ships;15`). Supports `k` and `m` suffixes. Prices are cached for 30 minutes to reduce API calls.

The embed shows a per-unit breakdown (quantity, money cost), total resources needed with per-unit prices and total resource cost, and a grand total. Includes easter eggs for specific unit combinations (6 missiles, 4 nukes, 1 ship + soldiers, exact MMR multiples). A **Close** button locks in the final calculation and removes the interactive buttons.

**`/weapon_eff`**

Weapon efficiency analysis for missiles and nukes. Two modes:

- **Theory mode** — generates a chart showing the infrastructure level required to deal 1× through 20× weapon cost in damage, across minimum and maximum population density ranges. If `infra_level` and `pop_density` are provided, also calculates exact min/max/average damage and value for that specific city and marks it on the chart. Shows the inefficiency threshold (below which you lose money) and the 5× optimal zone.
- **Targeted mode** — given a nation or alliance, scores every city by expected damage value accounting for Iron Dome (30% missile block) and Vital Defense System (25% nuke block). For a nation, shows the best missile and nuke target cities with min/max/average damage and value. For an alliance, ranks all nations by their best-city missile damage. The best missile and nuke targets are marked on the efficiency chart.

All calculations use live resource prices from the local database. Nation and city data comes from `GlobalNations.db` with API fallback.

#### Other — Fun PnW Stuff

A collection of miscellaneous Politics & War commands that don't fit neatly into the other categories — covering game trivia, loot intelligence, world activity tracking, and personal customisation.

**`/baseball`**

Looks up the baseball team for any nation by name, leader name, or ID. Autocomplete is backed by `GlobalNations.db`. The embed shows the team name, stadium, quality and seating ratings (each out of 100), a star rating derived from the combined score, overall rating, win/loss record, win percentage, games played, and career statistics (home runs, runs, strikeouts). The team logo is shown as a thumbnail and the team name links directly to its PnW page.

**Loot Intelligence (message listener)**

The Loot cog listens for messages that mention the bot. It handles two types of PnW game messages automatically — no command needed:

- **Spy report** — when a message contains a spy intelligence report (phrases like "gathered intelligence" or "spies discovered"), the bot parses the defender's money and resource holdings from the report text and calculates projected loot for six policy combinations: no Pirate/APE, no Pirate/APE with Moneybags, Pirate only, Pirate + Moneybags, Pirate + APE, and Pirate + APE + Moneybags. Each scenario shows the projected cash and per-resource amounts, with and without APE highlighted for quick comparison. Resource values use current sell prices from the local database — no API call.

- **Loot message** — when a message contains a war loot notification (phrases like "looted" combined with "defeated", "crushed", or "surrender"), the bot parses the actual looted amounts and calculates the total monetary value of each resource at current sell prices, showing a per-resource breakdown and grand total.

Both features activate only when the bot is mentioned in the message, keeping them opt-in per use.

**`/activity`**

Displays Politics & War world activity statistics over a configurable time range. Accepts a type (All, New, 1 Day, 2 Days, 3 Days, 1 Week, 1 Month) and a time range string (`2d`, `4w`, `1m`, etc.). Fetches historical activity data from the PnW API v3 and produces:

- An embed showing start value, end value, and percentage change (with directional arrows) for the selected activity type(s). When "All" is selected, all types are shown together.
- A Matplotlib line chart rendered server-side with a dark Discord-themed background, one colored line per activity type, date-formatted x-axis, and a legend. The chart is attached to the embed.

Activity types track different inactivity windows: how many nations logged in within the last 1, 2, 3, 7, or 30 days, plus new nation creation and total nation count.

**`/theme emoji set`** / **`/theme emoji remove`** / **`/theme emoji list`** / **`/theme emoji reload`**

A personal customisation system for how nations and alliances appear in autocomplete dropdowns throughout the bot. Custom emojis are stored locally and prepended to names in all autocomplete suggestions.

- **`/theme emoji set <type> <name> <emoji>`** — assigns a custom emoji to a nation or alliance. `type` is either `nation` or `alliance`. Autocomplete for `name` searches `GlobalNations.db` live as you type. The emoji appears before the name in every autocomplete dropdown that uses that nation or alliance.
- **`/theme emoji remove <type> <name>`** — removes the custom emoji and reverts to the default (🏛️ for nations, 🤝 for alliances). Autocomplete for `name` only shows entries that currently have a custom emoji set.
- **`/theme emoji list`** — shows all currently set custom emojis, grouped by nations and alliances, paginated at 20 entries per page. Ephemeral (only visible to you).
- **`/theme emoji reload`** — reloads the emoji stores from disk. Useful if the files were edited manually. Reports the count of loaded nation and alliance emojis. Ephemeral.

All theme commands respond ephemerally so they don't clutter the channel.

#### Util — Core Utilities

The Util directory contains the shared engine that powers every PnW command in the bot. None of these files expose Discord commands directly — they are internal libraries imported by the command cogs. Understanding what they do explains how the bot's calculations stay accurate and consistent.

**query.py — V3GraphQuery**

The single point of contact for all Politics & War GraphQL API calls. Every command that needs live PnW data goes through this class rather than making its own HTTP requests.

Key responsibilities:
- **Rate limiting** — an asyncio lock serialises all outgoing requests so concurrent commands (revenue loops, war stat updates, autocomplete) cannot flood the API simultaneously. A configurable minimum interval (default 150ms) is enforced between requests.
- **Caching** — a unified in-memory cache with per-entry TTLs covers query results, entity resolution, and trade data. War data is also cached to disk in `.cache/wars/` with descriptive filenames for debugging.
- **Retry logic** — an HTTP session with automatic retries (3 attempts, exponential backoff) handles transient 429/5xx errors transparently.
- **Entity resolution** — `resolve_alliance()` and `resolve_entities()` accept names, IDs, or PnW URLs and return numeric IDs. Batch resolution uses GraphQL aliases to resolve multiple names in a single request.
- **Standard field sets** — `_nation_fields()` and `_war_fields()` define the complete set of fields requested for nations and wars, ensuring every command gets the same data shape without duplicating field lists.
- **Master update batch** — `get_master_update_data()` fetches game info, color bonuses, trade prices, and resource stats in a single batched GraphQL request, used by the timed query loop.
- **API key safety** — the key is loaded from config and never logged or echoed. Error messages redact the key before logging.

**calc.py — AllianceCalculator**

The alliance-level statistics engine. Takes lists of nation dicts (from the API or `GlobalNations.db`) and computes aggregate metrics used by `/alliance`, `/audit`, `/compare`, and the web Watch page.

Key capabilities:
- **Military analysis** — `calculate_full_mill_data()` computes current vs maximum unit counts, daily production rates, unit gaps, and time-to-max per unit type across all active nations. Accounts for Propaganda Bureau bonuses and Military Research capacity levels.
- **Alliance statistics** — `calculate_alliance_statistics()` produces total score, city count, nation counts by status (active, VM, applicant), and project counts across all 40+ national projects.
- **Improvements data** — `calculate_improvements_data()` sums every improvement type across all cities of all active nations. Runs in a background thread via `asyncio.to_thread` to avoid blocking the event loop.
- **Active nation filtering** — `get_active_nations()` excludes vacation mode and applicants. The audit commands use this as the base set for compliance checks.
- **Nation summarization** — `summarize_nation_stats()` produces the full stat dict used by `/show`, including formatted last-active time, project slot calculation, MMR string, and achievement thresholds.
- **Military purchase limits** — `calculate_military_purchase_limits()` computes daily purchase capacity and maximum unit counts per nation based on barracks/factory/hangar/drydock counts and Military Research bonuses.

**war_calc.py — War Cost Engine**

The core war cost calculation library. Used by `/wars`, `/wars_cost_bd`, `/wars_net_bd`, the Watch page, and the compare wars system.

Key components:
- **`UNIT_COSTS`** — the authoritative cost table for all six unit types (soldiers, tanks, aircraft, ships, missiles, nukes) including cash and resource components.
- **`IMPROVEMENT_COSTS`** — cost table for all improvement types, used to value destroyed improvements in war cost calculations.
- **`get_resource_prices()`** — reads current buy/sell prices from `reaper.db` (updated every 15 minutes by the timed query loop). Falls back to a live PnW API call only if the database has no data yet.
- **`calculate_war_costs()`** — the main function. Takes a list of war dicts with attached attack records and two optional team ID sets, and returns a full cost breakdown for both sides covering: unit losses (with costs at buy prices), gasoline and munitions consumption, infrastructure destroyed (levels and monetary value), improvements destroyed (by type and total value), loot received and lost (cash and per-resource), money destroyed in city attacks, and military salvage (aluminum and steel recovered from destroyed aircraft/ships). Handles both war-level aggregate columns and attack-level detail records, deduplicating missile/nuke counts between the two sources.

**attacks_calc.py — Battle Simulation Engine**

Implements the per-attack combat mechanics used by the `/war` simulation command. Contains four calculators:

- **`GroundBattleCalculator`** — simulates ground battles using a 3-roll system. Army value is computed from soldiers (armed vs unarmed based on munitions availability) and tanks. Determines victory type (Utter Failure through Immense Triumph), then calculates loot, casualties, infrastructure damage, and whether ground control is gained or broken. War type (Raid/Ordinary/Attrition) and war policies (Pirate, Moneybags, Turtle, Fortress) modify loot and damage.
- **`AirstrikeCalculator`** — simulates air battles. Aircraft value drives 3-roll outcome. Determines air superiority changes and infrastructure damage.
- **`NavalBattleCalculator`** — simulates naval battles. Ship value drives 3-roll outcome. Determines blockade establishment/breaking and infrastructure damage.
- **`MissileStrikeCalculator`** / **`NukeStrikeCalculator`** — simulate weapon strikes. Iron Dome has a 30% chance to block missiles; Vital Defense System has a 25% chance to block nukes. Damage uses the `get_weapon_damage()` formula from `weapon_eff.py` with the city's actual population density.
- **`WarManager`** — the unified entry point that routes a battle type to the correct calculator and normalises the parameter dict.

**war_brain.py — Full War Simulator**

Orchestrates a complete turn-by-turn war simulation for the `/war` command. Uses `WarManager` from `attacks_calc.py` for individual battle resolution.

The simulator:
1. Deep-copies both nations so the originals are never modified.
2. Applies war policy effects (Blitzkrieg gives +1 MAP, Fortress reduces both sides to 5 MAPs).
3. Each turn: regenerates 1 MAP per side, determines who acts (higher MAPs goes first), runs a purchasing phase (buys units based on enemy analysis and blockade status), selects the optimal attack type via `determine_optimal_attack()`, executes the attack, updates war statuses (ground control, air superiority, blockade, fortification), and records the full turn result.
4. Continues until one side's resistance reaches 0 or 60 turns elapse.
5. Summarises total infrastructure destroyed, casualties, consumption, and loot across all turns.

The purchasing phase uses a priority system that counters enemy strengths and reinforces own strengths, scaled by whether the nation is winning or blockaded.

**rev_correct.py — Revenue Engine**

The full city-by-city revenue calculation engine. Used by `/revenue`, `/rev_optimizer`, the web Revenue page, and the raid loot projection system.

Key functions:
- **`calculate_nation_modifiers()`** — computes all economic multipliers for a nation from its projects and domestic policy. Covers commerce maximums, hospital/police effectiveness, manufacturing output multipliers (Iron Works, Bauxite Works, Arms Stockpile, Emergency Gasoline Reserve), food land modifier (Mass Irrigation), uranium production (Uranium Enrichment Program), radiation food penalty (Fallout Shelter), and domestic policy bonuses (Open Markets, Imperialism, etc.).
- **`calculate_power_generation()`** — computes power output, upkeep, fuel consumption, and pollution for a city's power plants. Uses exact per-turn rates: Wind ($41.67/turn, 250 infra), Nuclear ($875/turn, 2000 infra, 0.5 uranium/turn), Oil ($150/turn, 500 infra, 0.1 oil/turn per 100 infra), Coal ($100/turn, 500 infra, 0.1 coal/turn per 100 infra).
- **`calculate_resource_production()`** — computes raw resource output and upkeep for all mine types. Uses the stacking bonus formula: `1 + ((count - 1) / (limit - 1)) × 0.5`, giving a 50% bonus at the improvement limit. Rounds per-city output to 2dp using ROUND_HALF_UP to match game behaviour.
- **`calculate_manufacturing()`** — computes manufactured goods output (gasoline, steel, aluminum, munitions) with stacking bonuses and project multipliers. Halts entirely if any city infrastructure is unpowered.
- **`calculate_food_production()`** — computes food output accounting for land, farm count, stacking bonus, seasonal modifier (hemisphere-based), and radiation penalty.
- **`calculate_nuke_pollution_for_city()`** / **`get_nuke_pollution_for_nation()`** — calculates current radiation pollution from nuclear strikes using `IRSWars.db`. Pollution decays linearly over 133 turns (~11 days); Fallout Shelter reduces this to ~100 turns. Only confirmed hits (infra_destroyed > 0) contribute radiation — blocked nukes do not.

**precise_upkeep.py — Decimal Upkeep Calculator**

A precision wrapper around the upkeep constants that uses Python's `Decimal` type for penny-accurate calculations. Provides per-category upkeep functions (civil, power, resource, military) and a combined `calculate_total_precise_upkeep()` that returns exact Decimal values rather than floating-point approximations. Used where exact financial totals matter.

**correct_upkeep_constants.py — Upkeep Constants**

The authoritative source for all improvement upkeep costs as exact `Decimal` values derived from official game daily rates divided by 12 (turns per day). Covers all four categories:

- **Power plants** — Coal ($100/turn), Oil ($150/turn), Nuclear ($875/turn), Wind ($41.67/turn)
- **Civil improvements** — Police Station ($62.50), Hospital ($83.33), Recycling Center ($208.33), Subway ($270.83), Supermarket ($50.00), Bank ($150.00), Shopping Mall ($450.00), Stadium ($1,012.50)
- **Resource production** — all mines, farms, and manufacturing improvements with their exact per-turn costs
- **Military buildings** — Barracks, Hangar, Drydock, Factory (all $0.00/turn — no upkeep)

Also defines power plant fuel consumption rates and infrastructure capacity per plant type. A `validate_upkeep_constants()` function verifies all values against their daily equivalents.

---

### Tickets System

The Tickets System manages membership applications and embassy requests for the Nights Watch Discord server. It is purpose-built for the alliance's onboarding workflow and integrates directly with the PnW API and the bot's existing nation/alliance lookup tools.

All ticket state is persisted to `Databases/Tickets.db` so tickets survive bot restarts. The interactive buttons in the info channel are registered as persistent views and are restored automatically when the bot starts.

**How it works**

A welcome embed is posted in the designated info channel using `/info`. The embed contains two buttons — **Membership** and **Embassy** — that any server member can click at any time.

Clicking **Membership** opens a modal asking for a nation name or ID. The bot looks up the nation from the PnW API, creates a private ticket channel named `c{cities}-{nation-name}` (e.g. `c15-reaperland`), and immediately posts the full `/show` nation profile inside it — the same comprehensive embed used by the IA show command, complete with all stats, projects, and the interactive view. Only the applicant, the bot, and configured staff roles can see the channel.

Clicking **Embassy** opens a modal asking for an alliance name or ID. The bot looks up the alliance, creates a private ticket channel named after the alliance (using the in-game acronym if the full name is too long), and immediately posts the full `/alliance` overview inside it — the same interactive embed with nation counts, military stats, and the tabbed view used by the IA alliance command. The channel color matches the alliance's PnW color.

**Staff commands**

- **`/verify accept`** — run inside a ticket channel to accept the application. For membership tickets: assigns the Member role to the applicant and moves the channel to the accepted members category with explicit permission overwrites (only the applicant, staff roles, and the bot can see it — not the general server). For embassy tickets: creates or finds a Discord role named after the alliance (colored to match their PnW color), assigns that role plus the Diplomat role to the applicant, and moves the channel to the accepted embassies category where everyone holding the alliance role can participate.

- **`/verify reject`** — run inside a ticket channel to reject the application. Notifies the applicant in the channel, marks the ticket as rejected in the database, waits 5 seconds, then deletes the channel and removes the record.

- **`/delete_ticket`** — deletes any ticket by name with autocomplete. The autocomplete shows all tickets (open, accepted, and rejected) with their status and type. Selecting one deletes the Discord channel if it still exists and removes the database record.

- **`/resort_members`** — re-queries the PnW API for every open membership ticket and renames the channels to reflect the applicant's current city count and nation name. Useful after a nation buys cities or changes their name. Processes tickets sequentially with a 1-second delay between each to respect Discord rate limits.

**Ticket role management**

Staff roles that should have access to all ticket channels are configured via a sub-command group:

- **`/ticket_role add <role> [label]`** — adds a Discord role to the ticket roles list. Every new ticket channel created after this point will automatically grant that role read/write access. Existing channels are not retroactively updated.
- **`/ticket_role remove <role>`** — removes a role from the list. Autocomplete shows only roles currently in the list.
- **`/ticket_role list`** — shows all configured ticket roles with their friendly labels.

**Welcome message**

When a new member joins the server, the bot automatically sends a welcome embed in the info channel. The embed mentions the new member (triggering a notification), links to the ticket channel and bot spam channel, links to the website, and includes the alliance's standing rule about the perimeter. The welcome message is sent as a channel message rather than a DM so the whole server sees it.

**Permission model**

Every ticket channel is created with explicit permission overwrites that override the category defaults:

- `@everyone` — cannot see the channel
- The applicant — can view, send messages, read history, attach files, use slash commands
- The bot — full management permissions
- All configured ticket roles (staff) — can view, send, read history, manage messages

When a ticket is accepted, the channel is moved to the appropriate accepted category and the overwrites are rebuilt from scratch to ensure the category's default permissions do not bleed through. For embassy channels, the newly created alliance role is also added so all members of that alliance can use the channel going forward.

---

### Translator System

The Translator System provides on-demand message translation directly inside Discord channels without requiring any external accounts, API keys, or configuration. It works in two ways — flag emoji reactions and a right-click context menu.

**Flag emoji reactions**

Any user can react to any message with a country flag emoji to request a translation of that message into the corresponding language. The bot watches for flag reactions across all channels it can see. When a supported flag is added, the bot:

1. Fetches the message content
2. Sends it to Google Translate with auto-detection for the source language
3. Posts a short prompt in the channel — "Translation ready for 🇫🇷! (Click below to see it)" — with a **Show Translation** button
4. The prompt auto-deletes after 60 seconds

The **Show Translation** button is user-locked — only the person who reacted can click it. When clicked, the translation appears as an ephemeral message (visible only to that user) showing the translated text, the source channel name, and a preview of the original message. This keeps translations private and avoids cluttering the channel.

A debounce lock prevents the same user from triggering duplicate translations for the same message and emoji within a 2-second window.

**Supported languages (63 total)**

The flag-to-language mapping covers the major world languages including English, Spanish, French, German, Italian, Portuguese, Russian, Dutch, Polish, Ukrainian, Greek, Turkish, Czech, Hungarian, Romanian, Bulgarian, Swedish, Norwegian, Danish, Finnish, Icelandic, Estonian, Latvian, Lithuanian, Slovak, Slovenian, Croatian, Serbian, Albanian, Maltese, Chinese (Simplified and Traditional), Japanese, Korean, Hindi, Indonesian, Malay, Vietnamese, Thai, Tagalog, Hebrew, Arabic, Persian, Urdu, Bengali, Kazakh, Uzbek, Armenian, Georgian, Azerbaijani, Mongolian, Afrikaans, Amharic, Somali, Wolof, Swahili, Igbo, and Esperanto.

**Right-click context menu**

A **Translate** option appears in the right-click (or long-press) Apps menu on any message. Selecting it translates the message to English and shows the result as an ephemeral reply — only visible to the user who triggered it. This is useful for a quick one-off translation without needing to know the correct flag emoji.

**Privacy and safety**

All translations are delivered ephemerally where possible — either via the button interaction (visible only to the requester) or via the context menu (also ephemeral). The channel prompt that appears when a flag reaction is used contains no translated text itself, only a button, and auto-deletes after 60 seconds. No message content is stored by the bot; it is passed directly to Google Translate and the result is returned immediately.

The translation service uses Google's public translate endpoint with automatic source language detection. No API key is required and no user data is retained beyond the duration of the request.

---

### Astrology System

The Astrology System provides two Discord commands covering tarot card readings and a triple-zodiac personality profile system. Both are slash/hybrid commands.

**`/tarot`**

Performs a professional tarot card reading with three spread options:

- **1 Card** — a single card draw with a direct message from the universe
- **3 Card (Past/Present/Future)** — three cards covering the foundation of a situation, where you currently stand, and the path ahead
- **5 Card (Traditional)** — five cards covering the core theme, the obstacle, the advice, a hidden influence, and the likely outcome

For each spread, the bot randomly draws unique cards from the full 78-card tarot deck. Each card is randomly assigned an orientation — upright or reversed — which determines whether its light or shadow meanings apply. Major Arcana cards are visually distinguished from Minor Arcana.

The card images are loaded from the local `Systems/Astrology/Tarot/cards/` directory, resized to a consistent size, rotated 180° if reversed, and stitched side-by-side into a single composite PNG image that is attached to the response.

For multi-card spreads, the bot also calculates a **dominant energy** based on which suit appears most frequently — Fire (Wands), Water (Cups), Air (Swords), Earth (Pentacles), or Major Arcana — and displays a thematic atmosphere line if one suit dominates.

An **AI-powered summary** is generated using the Groq API (Llama 3.1). The prompt is tailored to the spread type: a single profound message for 1-card draws, a cohesive narrative connecting past/present/future for 3-card draws, and a comprehensive interpretation covering all five positions for the traditional spread. If the Groq API is unavailable, the reading still works — the AI summary field shows a fallback message and all card details remain fully visible.

The result is a paginated embed with two views navigable via buttons:

- **Cards** — shows the stitched card image, the dominant energy (if applicable), and a per-card breakdown with position name, transition phrase, card name and orientation, top three meanings, and a fortune-telling line
- **Summary** — shows only the AI-generated narrative interpretation, with the image removed for a cleaner read

**`/zodiac`** (signs.py)

Generates a triple-zodiac personality profile from a birthday. Accepts a date and produces a three-page interactive embed navigable via buttons:

- **Western** (♈ button) — the standard sun sign based on month and day. Shows the sign's element, modality, ruling planet, astrological house, associated tarot card, traits, lucky numbers, lucky colors, gemstones, compatibility signs, and a full description. The date range for the sign is displayed and a countdown to the user's next birthday is shown in the footer.

- **Eastern** (🐉 button) — the Chinese zodiac animal based on the birth year, with proper Chinese New Year boundary handling. The bot uses a lookup table of exact Chinese New Year dates from 1900 to 2027 to correctly assign the animal — someone born in January or early February may belong to the previous year's animal. Shows the animal's polarity (Yin/Yang), fixed element, trine group, lucky hours (converted from 24-hour to 12-hour format), lucky numbers, lucky colors, lucky flowers, traits, and compatibility/incompatibility pairings.

- **Spirit Animal** (🌀 button) — the Primal Astrology spirit animal, which is the unique combination of Western sun sign and Chinese zodiac animal. Each of the 144 possible combinations maps to a distinct spirit animal with its own description and characteristics.

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

Each round shows the current score, the round result with custom emoji for each choice, and a round-end message. When a player reaches the required wins, the embed turns gold and shows Play Again / End Game buttons. Play Again continues with the same score; End Game shows the final tally and stops the view.

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

- **Novice** — the bot picks randomly
- **Competent** — the bot checks for winning/blocking moves before falling back to random
- **Expert** — the bot uses the minimax algorithm and plays optimally

The creator picks their emoji via a modal. A second player joins via a Join Game button and also picks their emoji. The board is displayed as a 3×3 grid of buttons. Supports multi-round series (best of 1, 3, or 5). The series score is shown in the embed title throughout.

**`/roast`**

AI-generated roast targeting a mentioned user (or yourself if no target is given). Seven intensity levels: Mild, Simple, Standard, Spicy, Wild, NSFW, and Explicit. Each level has a distinct system prompt that controls tone, language, and content.

The bot attempts to fetch the target's Discord bio to personalise the roast. The content is generated via the Groq API (Llama 3.1) with a 2–3 sentence limit. If the API is unavailable, a theme-appropriate fallback line is used. The intensity level emoji is shown alongside the result.

**`/compliment`**

Identical structure to `/roast` but generates praise instead of insults. Same seven intensity levels, same bio personalisation, same Groq API with fallback. The compliment is tailored to highlight positive traits at the appropriate intensity.

**`/random`**

Fetches and posts a random image or GIF. Two types:

- **JPG** — fetches a random photo from Pixabay (requires `PIXABAY_KEY`). Picks a random page offset each call for genuine variety.
- **GIF** — fetches a random GIF from Giphy (requires `GIPHY_KEY`). Uses the Giphy random endpoint with a general rating.

The image is downloaded server-side and posted as a Discord file attachment rather than a URL embed, so it displays inline regardless of link preview settings.

**`/walktru`**

A text-based adventure game with six distinct storylines, each with its own mechanic that changes based on your choices:

- **Horror Sanitarium** — manage Fear (0–100); too much fear ends the run
- **1920s Gangster** — manage Heat (0–100); too much police attention ends the run
- **Knight's Quest** — manage Honor (0–150); starts at 100, moral choices raise or lower it
- **Robot Factory Escape** — manage Power (0–100); reach 100% by stage 10 to build your body
- **Western Frontier** — manage Health (0–100); starts at 100, injuries reduce it
- **Wizard's Apprentice** — manage Mana (0–150); starts at 100, spells consume it

A dropdown menu lets you select the adventure. Each stage presents a scenario with numbered choice buttons. Choices have a success chance — the outcome (success or failure) is rolled randomly against that chance. The mechanic value changes based on the outcome, clamped within the adventure's bounds. A visual progress bar with warning messages shows the current mechanic status. The adventure ends when the mechanic hits a critical threshold or the story reaches its conclusion.

**`/zombie_survival`**

An ongoing, AI-driven zombie survival simulation that runs continuously in a channel. Multiple players can join and their fates are shared.

Each round the Groq AI (Llama 3.1) generates a new story event with exactly 4 choices, each assigned a base success probability (meaningfully different from each other — a suicidal charge might be 10–20%, a cautious retreat 60–80%). Players vote by clicking A/B/C/D buttons. The round resolves automatically every 2 hours.

The winning choice is determined by majority vote (ties broken randomly). The final success chance is the base odds plus a vote multiplier (2–5% per voter on the winning choice) plus a random luck factor (±15%). More votes on a choice genuinely improves its odds.

On success, survivors gain small amounts of HP, stamina, morale, and ammo. On failure, stats are penalised. Attack choices consume ammo (rifle preferred, then revolver, with auto-reload from spare). Supply/scavenge choices gain ammo. If a survivor's health reaches 0 they are marked Deceased. If all survivors die, the game ends with a game-over embed and the state is fully wiped.

The round embed shows the current story event, a live countdown to the next resolution using Discord's native timestamp format (updates on every client with no API calls), the 4 choices, survivor mentions (deceased shown with strikethrough), and the previous round's outcome. Use `/zombie_character` to see your personal survivor stats (health, stamina, morale, weapon loadout).

**`/zombie_character`**

Shows your personal survivor card for the active zombie game: health, stamina, morale, revolver ammo (loaded/spare), rifle ammo (loaded/spare), and your randomly assigned melee weapon. Ephemeral — only visible to you.

---

### PnW Subscriptions and Query

The PnW data pipeline is split into two separate processes that run independently: the **PnWHarvester** (a standalone service with no Discord connection) and the **Reaper bot** (which reads from the databases the harvester maintains). This separation means the bot is never blocked waiting for API responses and the databases are always current regardless of whether the bot is running.

**Architecture overview**

The harvester runs as `python harvester.py` from the project root. It opens three persistent WebSocket subscriptions to the PnW API and keeps them running indefinitely. Each subscription automatically restarts after disconnects or crashes with a 30-second delay. A coordinated shutdown handler ensures any in-flight database writes complete before the process exits.

The bot reads from the same SQLite databases the harvester writes to. All reads are non-blocking — the bot never writes to `GlobalNations.db` or `IRSWars.db` directly. The harvester owns all writes; the bot is read-only against those files.

**Nations subscription (`nations_subscription.py`)**

Listens to three WebSocket channels simultaneously:

- `nation/update` and `nation/create` — every nation change in the entire game is written to `GlobalNations.db`. This includes all 40+ national projects, military units, city data, alliance membership, domestic policy, and all other nation fields. When a nation's alliance changes, the change is logged. When a nation joins or leaves Nights Watch, the in-memory membership set is updated.
- `account/update` — patches `last_active` and `discord_id` without touching other fields.
- `city/update` and `city/create` — upserts city data (infrastructure, land, all improvements) into `GlobalNations.db`. When a new city is detected, `num_cities` on the parent nation is incremented immediately without waiting for the next `nation/update` event.

**Spending detection** — before saving any updated nation or city snapshot, the subscription compares the incoming data against the existing row to detect purchases:

- **City purchases** — detected when `num_cities` increases or `turns_since_last_city` resets to 0. The cost is calculated using the official PnW city cost formula and deducted from `holdings.db`.
- **Project purchases** — detected when `turns_since_last_project` resets to 0. The cash and resource costs are calculated and deducted from `holdings.db`.
- **Military changes** — any change in unit counts (soldiers, tanks, aircraft, ships, missiles, nukes, spies) is applied to `holdings.db` to keep military counts current.
- **City upgrades** — infrastructure purchases, land purchases, and improvement builds are detected by comparing old and new city snapshots. Costs are deducted from `holdings.db`.

Holdings columns (money, resources, military) are intentionally **not** overwritten when saving nation updates — those values are owned by `holdings.db` and kept accurate through the spending detection system. Only new nations (first-seen snapshots) receive the full API values as an initial seed.

**Beige early-exit detection** — when a nation's `beige_turns` drops to 0 and their color changes away from beige, the subscription checks whether any users have active beige alerts for that nation. If so, it enqueues an early-exit notification in a queue table that the bot drains to send Discord DMs, then removes the alert rows.

**Wars subscription (`wars_subscription.py`)**

Listens to three WebSocket channels:

- `war/create` — new war declarations. NW wars (where Nights Watch is attacker or defender) are saved to `IRSWars.db`. All wars (NW and non-NW) are cached in memory with their war type, policies, and nation names for use by the attack handler.
- `war/update` — war state changes (resistance, peace flags, winner, etc.). NW wars are updated in `IRSWars.db`. The in-memory cache is refreshed.
- `warattack/create` — every attack in every war. For each attack:
  - If it's a NW war, the attack record is saved to `IRSWars.db` with full loot and casualty detail.
  - If it's a winning ground attack with loot, `holdings.db` is updated immediately: the defender's holdings are reduced by the looted amounts and the attacker's holdings are increased.
  - Gasoline and munitions consumed in the attack are deducted from both sides' holdings.
  - Military casualties (soldiers, tanks, aircraft, ships, missiles, nukes) are applied to both sides' holdings so unit counts stay current without waiting for the next `nation/update` event.

A watchdog monitors the `war/update` channel — if it goes silent for more than 35 minutes (wars update every turn for all active wars), the subscription is considered dead and restarted. The `warattack/create` channel has a 4-hour timeout since quiet periods are normal when no wars are active.

If an attack arrives before its parent war has been received (race condition on startup), the attack is queued and processed once the war arrives. If a war is still missing after a short wait, a direct API query fetches it as a fallback.

**Bankrecs subscription (`bankrecs_subscription.py`)**

Listens to `bankrec/create` — every bank transfer in the entire game. For each record:

1. The record is saved to `bankrecs.db` for use by the `/offshore` command.
2. If either party is a nation (type=1), `holdings.db` is updated immediately: the receiver's holdings are increased and the sender's holdings are decreased by the transferred amounts.
3. A news event (deposit, withdrawal, or transfer) is written to the news database for transfers above the $1M threshold.

Alliance-to-alliance transfers are saved to `bankrecs.db` but do not update `holdings.db` (only nation-type parties affect holdings).

**Turn revenue loop (`turn_revenue_loop.py`)**

Fires at every PnW turn boundary — midnight UTC and then every 2 hours (00:00, 02:00, 04:00 … 22:00 UTC). At each turn:

1. Game context (resource prices, color bonuses, radiation levels, seasonal food modifiers) is loaded entirely from `reaper.db` — no API calls are made. The reaper bot's timed query loop keeps this data fresh.
2. The complete set of nations currently at war is built from two sources: `IRSWars.db` (authoritative for NW nations) and `GlobalNations.db` war count columns (for all other nations).
3. All nations and their cities are bulk-loaded from `GlobalNations.db` in two queries.
4. Revenue is calculated for every nation using the full city-build engine (`revenue_calc_sync`) — the same engine used by the `/revenue` command. Nations on vacation mode and nations with no city data are skipped.
5. All results are written to `GlobalNations.db` in a single SQLite transaction. Holdings columns (money, resources) are updated with the net per-turn delta. Negative deltas (e.g. a steel mill consuming more coal than the nation produces) are applied correctly.
6. Beige alerts are updated: `beige_turns` is decremented using the authoritative value from `GlobalNations.db`, projected loot is recalculated from current holdings, and expired alerts (beige_turns = 0) are removed.

On startup, the loop checks how many turns have elapsed since the last revenue was applied and replays up to 12 missed turns (24 hours) in sequence to catch up after an outage.

**Startup sync**

When the harvester starts, it optionally runs two one-time sync operations before the subscriptions begin:

- **Nations sync** — calls `sync_nations()` from `irs_nations_manager.py` to ensure `GlobalNations.db` is populated with current data before the subscriptions take over.
- **NW wars backfill** — fetches Nights Watch wars for a configurable date range (default 7 days) and upserts them into `IRSWars.db`. Enabled with `--sync-nw-wars` on the command line.

**WAL checkpointing**

A background task runs every 5 minutes and checkpoints the WAL (Write-Ahead Log) files for `GlobalNations.db` and the news databases. This keeps the WAL files small and prevents unbounded growth during high-activity periods.

**Nations manager cog (`nations_manager_cog.py`)**

A Discord cog loaded by the bot (not the harvester) that provides the `sync_nations()` function used during startup. It queries the PnW API for current nation data and upserts it into `GlobalNations.db`, ensuring the database is populated before the subscriptions take over. Also used by the bot's `on_ready` handler to sync any nations that changed while the bot was offline.

**IRS nations and wars managers (`irs_nations_manager.py`, `irs_wars_manager.py`)**

Utility modules used by the bot's startup sequence to sync missed data. `sync_nations()` fetches current nation snapshots; `sync_wars()` fetches wars that occurred since the bot's last-seen timestamp and upserts them into `IRSWars.db`. Both are called in the background during `on_ready` so they don't delay the bot coming online.

**Beige alerts DB (`beige_alerts_db.py`)**

Shared module used by both the harvester and the bot. Provides the queue table that bridges the two processes: the harvester writes early-exit notifications when a nation leaves beige unexpectedly, and the bot's beige notification loop drains the queue to send Discord DMs. Both processes use WAL mode so concurrent reads and writes never block each other.

**Nation emoji store (`nation_emoji_store.py`)**

Stores custom emoji assignments for nations and alliances, used by autocomplete dropdowns throughout the bot. Persisted to disk and loaded into memory on startup. The `/theme emoji` commands write to this store.

---

### PnW Nation/War Tracking DB Files

All PnW data in ReaperBot is stored locally in SQLite databases under `Databases/PnW/`. The bot never queries the PnW API for data it already has — every command, every web page, and every calculation reads from these local stores first. The databases are populated and kept current by the PnWHarvester process running alongside the bot.

**GlobalNations.db**

The central nation database. Stores a complete snapshot of every nation in the game — not just Nights Watch members. Each nation record includes:

- Identity: nation name, leader name, continent, color, flag, Discord ID
- Alliance: alliance ID, alliance name, position, seniority, tax bracket
- Stats: city count, score, population, GDP, GNI
- Military: soldiers, tanks, aircraft, ships, missiles, nukes, spies, war counts (offensive, defensive, won, lost)
- Policies: war policy, domestic policy, social policy, government type, economic policy, update timezone
- Projects: all 40+ national projects stored as boolean columns (Iron Dome, VDS, Nuclear Research Facility, Space Program, etc.)
- Status: vacation mode turns, beige turns, last active timestamp, turns since last city/project
- Holdings: money and all 12 resources — seeded from the API on first insert, then maintained in real-time by the harvester's holdings tracking and turn revenue loop

Each nation also has a full city table (`cities`) with every improvement slot for every city — infrastructure, land, power type, and all improvement counts. This is what makes the revenue calculator and optimizer work without API calls.

War count columns (`wars_won`, `wars_lost`, `offensive_wars_count`, `defensive_wars_count`) are managed exclusively by real-time war subscription events, not overwritten by nation update snapshots. This keeps counts accurate between turns.

The database runs in WAL mode with a 5-minute checkpoint cycle so the harvester and web server can read and write concurrently without blocking each other.

**IRSWars.db**

The primary war database for Nights Watch. Stores every war involving a Nights Watch nation, with full attack-level detail. Two tables:

- `wars` — one row per war: attacker/defender IDs and names, alliance IDs and names, resistance, fortify, peace flags, turns left, winner, gas/munitions used, infrastructure destroyed and its monetary value, all unit losses, missiles and nukes used, war policy for both sides, and whether the attacker has Advanced Pirate Economy (affects loot calculation). An `is_active` flag and `end_reason` column are maintained in real-time so active-war queries never need to scan the full table.

- `war_attacks` — one row per individual attack: attack type, victor, success, casualties on both sides, infrastructure destroyed and its value, improvements destroyed (stored as JSON), money stolen, money destroyed, military salvage (aluminum and steel), and full loot breakdown for all 12 resources. Missile and nuke losses are tracked separately from use counts.

A third table, `subscription_war_attacks`, acts as a staging buffer for attacks that arrive from the subscription before their parent war has been received. Attacks are processed from this buffer once the war record is confirmed.

The Watch page on the web interface reads exclusively from this database — no API calls are made for war cost calculations.

**GlobalNations.db (also used as IRSNationsDB)**

`IRSNationsDB` is a backward-compatibility alias that resolves to `GlobalNationsDB` at import time. All code that previously used `IRSNationsDB` transparently uses the same `GlobalNations.db` file. There is only one nation database.

**News databases (WeeklyNews.db, MonthlyNews.db, YearlyNews{YYYY}.db)**

Three parallel news databases with identical schemas, all written simultaneously for every event. Each covers a different time window:

- `WeeklyNews.db` — current week only, auto-reset every Monday at 00:00 UTC. The previous week's data is archived to `WeeklyNews_prev.db` before the reset.
- `MonthlyNews.db` — current month only, auto-reset on the 1st of each month. Archived to `MonthlyNews_prev.db`.
- `YearlyNews{YYYY}.db` — full calendar year, never reset. A new file is created each January 1st.

Each database has three tables:

- `events` — one row per game event (war declared, war ended, city built, project purchased, alliance change, bank deposit/withdrawal, etc.). Each event carries the nation ID, name, flag, alliance ID, name, and flag for both the primary and secondary party. Alliance names are always resolved from `GlobalNations.db` at write time — recycled alliance IDs never carry stale names into the news feed.
- `alliance_stats` — running totals per alliance for the period: cities built, projects bought, infrastructure/land/improvement/military spending, wars declared/won/lost/drawn, loot gained/lost, nukes and missiles used, bank deposits and withdrawals.
- `nation_stats` — same running totals at the individual nation level, with alliance attribution.

A 5-minute in-memory cache over `GlobalNations.db` enriches every event with complete nation and alliance metadata before it is written, so the news feed always has human-readable names and flags even for nations that haven't been seen in a subscription event yet.

**bankrecs.db**

Stores every bank transfer in the game received via the `bankrec/create` subscription. Used by the `/offshore` command to show transfer history for any nation or alliance. Records include sender, receiver, type (nation-to-nation, nation-to-alliance, etc.), and full resource amounts for all 12 resources plus money.

**holdings.db**

Tracks the actual money and resource holdings for every nation in real-time. Updated by three sources:

- The `bankrec/create` subscription — every transfer immediately adjusts both parties' holdings.
- The `warattack/create` subscription — loot, money stolen, and military salvage are applied to both sides after each attack.
- The turn revenue loop — net per-turn revenue (income minus all upkeep) is applied to every nation at each turn boundary.

Holdings data is what makes the Raids page loot estimates accurate — it reflects actual current holdings rather than a stale API snapshot.

**reaper.db**

The core bot database. Stores resource market prices (updated every PnW turn), color bloc bonuses, radiation levels, beige alert records, and other game-state data used across multiple systems. The revenue calculator and optimizer read resource prices from here so monetary values in all calculations reflect current market rates.

**Databases/Pets/ (pet game databases)**

- `pets.db` — all pet profiles, user relationships (friend/foe/enemy/best friend), and the bazaar marketplace. The primary store for the entire pet system.
- `Tasks.db` — daily and weekly task assignments per user, completion state, and reward tracking.
- `absorb.db` — Survivor Series game state: elimination rounds, procedural map data, and per-round results.
- `colosseum.db` — automated hourly Colosseum tournament results and leaderboard.
- `dungeon.db` — dungeon crawl session state for active and completed runs.
- `powerball.db` — Powerball lottery ticket purchases and draw history.
- `survivorseries.db` — Survivor Series event registration and bracket state.

**Databases/Tickets.db**

Stores all support ticket records: ticket ID, channel ID, applicant Discord ID, ticket type (membership or embassy), nation or alliance ID, creation timestamp, and current status. Survives bot restarts — the interactive buttons in the info channel are restored as persistent views on startup using the data in this table.

**Databases/zombie.db**

Stores zombie survival game state: active game sessions, player status (alive/infected/dead), story progression, and AI-generated narrative history. Used by the Gemini-powered zombie story system in the Fun module.

**Databases/alerts.db**

Stores two types of user alerts:

- **Beige alerts** — set when a target nation is on beige. The harvester's turn revenue loop decrements `beige_turns` each turn and triggers DM notifications at ~2 hours and ~15 minutes before expiry.
- **Resource price alerts** — one-shot alerts that fire when a resource's buy or sell price crosses a user-defined threshold. Checked after every timed resource data save (each PnW turn) and removed after firing.
