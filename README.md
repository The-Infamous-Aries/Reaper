# ReaperBot

> **A comprehensive, self-hosted Discord bot featuring advanced Pet systems, Politics & War tools, and interactive entertainment.**  

---

## 📋 Table of Contents

- [🚀 Overview](#-overview)
- [⚙️ Configuration & Environment](#️-configuration--environment)
  - [🛠️ Runtime Bootstrapping & Event Handling](#️-runtime-bootstrapping--event-handling-reaperpy)
- [✨ Major Features](#-major-features)
  - [🐾 Pets System](#-pets-system)
    - [🏗️ System Architecture](#️-system-architecture)
    - [🥊 Combat Engine](#-combat-engine)
    - [🎰 Casino & Mini-Games Engine](#-casino--mini-games-engine)
    - [👻 Survivor Series Engine](#-survivor-series-engine)
    - [⚔️ Gameplay Mechanics](#️-gameplay-mechanics)
    - [🎮 Command Controller & UI](#-command-controller--ui)
  - [🎯 Fun System](#-fun-system)
    - [😇 Good & Evil (Elemental AI)](#-good--evil-elemental-ai)
    - [🔮 Astrology & Horoscopes](#-astrology--horoscopes)
    - [🎲 Classic Games & Utilities](#-classic-games--utilities)
    - [📖 Interactive Adventures (WalkTru)](#-interactive-adventures-walktru)
  - [🛡️ Administration System](#️-administration-system)
  - [⚔️ PnW System](#️-pnw-system)
    - [🪖 Military Analytics (MA)](#-military-analytics-ma)
    - [🧠 Intelligence Analytics (IA)](#-intelligence-analytics-ia)
    - [🔋 Core Utilities (Developer Notes)](#-core-utilities-developer-notes)
- [🎨 Shared Assets & Utilities](#-shared-assets--utilities)
- [📜 Command Reference](#-command-reference)
  - [🐾 Pets Commands](#-pets-commands)
  - [🎯 Fun Commands](#-fun-commands)
  - [🛡️ Admin Commands](#️-admin-commands)
  - [⚔️ PnW Commands](#️-pnw-commands)
- [🏗️ Project Structure](#️-project-structure)

---

## 🚀 Overview

**ReaperBot (Allspark)** represents a paradigm shift in Discord bot architecture, evolving beyond simple command-response interactions into a **comprehensive, self-hosted application platform**. Built on the robust `discord.py` framework and engineered for **CasaOS** and containerized environments, it features a revolutionary **self-bootstrapping runtime** that automatically manages its own Python dependencies in an isolated `local_packages` environment, ensuring zero-configuration deployment.

At its core, ReaperBot is a **multi-threaded, asynchronous ecosystem** designed for high-concurrency performance. It leverages a custom-built **User Data Manager** with atomic file locking, O(1) in-memory caching, and background write-flushing to maintain data integrity across thousands of users without blocking the event loop.

Functionally, the bot is divided into three powerhouse modules:
1.  **A Full-Scale MMORPG**: The "Pets" system is a persistent game world with deep progression mechanics, featuring procedural entity generation (13 elements, unique stats), a player-driven economy, tactical turn-based combat (PvE/PvP), and complex casino simulations (Poker, Blackjack, Slots).
2.  **Military Intelligence Suite**: A professional-grade toolkit for the *Politics and War* browser game, offering real-time GraphQL analytics, alliance-wide economic auditing, automated treaty visualization, and "smart" military targeting that optimizes war efficiency.
3.  **AI & Entertainment Engine**: A "Fun" system powered by **Google Gemini** and **Groq** LLMs for dynamic content generation, alongside procedural text adventures (`/walktru`), astrological profiling, and arcade-style minigames.

Whether you are running a competitive gaming clan, a roleplay server, or a casual community, ReaperBot delivers enterprise-level utility and engagement in a single, self-managing package.

### Key Highlights
- **Zero-Config Deployment**: Features a self-bootstrapping runtime that automatically manages dependencies in a private `local_packages` environment, making it "plug-and-play" ready for CasaOS and isolated container setups.
- **MMORPG-Lite Core**: A deep "Pets" system featuring procedural entity generation, tactical turn-based combat (PvE/PvP), automated tournaments, and a "Survivor Series" battle royale engine powered by custom map generation.
- **Military Intelligence Suite**: A comprehensive toolkit for *Politics and War* alliances, integrating GraphQL-powered analytics, treaty visualization, economic modeling, and automated recruitment workflows.
- **Enterprise Architecture**: Built on a custom `UserDataManager` and `OptimalFileManager` that provide O(1) data access, atomic file locking, and background persistence loops to ensure data integrity under high load.
- **AI & Interactive Media**: Integrates Google Gemini and Groq APIs for dynamic content generation, alongside procedural text adventures and astrological profiling.

---

## ⚙️ Configuration & Environment

The bot uses `config.py` to load environment variables. Ensure your `.env` file or system environment variables are set.

| Variable | Description | Required |
|:---|:---|:---|
| `DISCORD_TOKEN` | The bot's authentication token. | **Yes** |
| `PREFIX` | Command prefix (default: `!`). | No |
| `ADMIN_USER_ID` | Discord ID of the bot owner for admin commands. | No |
| `RESULTS_CHANNEL_ID` | Channel ID for game results/logs. | No |
| `HOME_ALLIANCE_ID` | Politics & War Alliance ID for PnW tools. | No |
| **API Keys** | | |
| `GEMINI_API_KEY` | Google Gemini API for AI features. | No |
| `GROQ_API_KEY` | Groq API for fast AI text generation (Roasts/Compliments). | No |
| `PANDW_API_KEY` | Politics & War API Key. | No |
| `PANDW_BOT_KEY` | Politics & War Bot Key. | No |

### 🛠️ Runtime Bootstrapping & Event Handling (`reaper.py`)
To ensure portability across different environments (like **CasaOS** or **SparkedHost**), the bot includes a self-managing bootstrap system and centralized event handling.

*   **Dependency Isolation**: The bot installs dependencies into a local `local_packages/` directory at runtime using `pip install --target`.
*   **Parallel Loading**: Uses a custom `_load_all_modules_parallel` engine to import bot systems concurrently, significantly reducing startup time.
*   **Event Handling**:
    *   **`on_ready`**: Logs startup time, bot ID, and guild count. Triggers module-specific initializers (e.g., `StoryMapManager` in `fun_system.py`).
    *   **`on_command_error`**: Captures and logs all command failures with detailed context (User, Guild, Message Content, Stack Trace). Provides user-friendly error messages for common issues (Cooldowns, Missing Permissions).
    *   **`on_member_join`**: Sends a custom welcome embed to specific servers (Guild ID: `1445703450263420938`), detailing rules and leadership.
    *   **`on_error`**: Catches and logs unhandled exceptions from background tasks or events.
*   **Automatic Updates**: Checks `requirements.txt` on startup and updates packages if needed.
*   **Path Management**: Automatically modifies `sys.path` to prioritize local packages, preventing conflicts with system-level Python libraries.

To run the bot, simply execute:
```bash
python reaper.py
```
*Note: Do not run `bot.py` or `main.py` directly if you want the automatic environment setup.*

---

## ✨ Major Features



### 🐾 Pets System
**Directory:** `Systems/Pets/`

The Pets System is a fully realized MMORPG-lite engine embedded within the bot, offering a persistent world where users adopt procedurally generated companions. It features a sophisticated economy driven by risk-reward loops (Training, Missions, Gambling), a deep tactical combat system supporting PvE/PvP/Tournaments, and high-fidelity mini-games including a full Casino suite and a procedural Battle Royale mode (Survivor Series). Built on a robust asynchronous architecture, it manages real-time state synchronization, complex inventory systems with crafting/upgrading potential, and long-term progression curves designed for months of engagement.

#### 🏗️ System Architecture
**Files:** `Systems/Pets/pets_system.py`, `Systems/Pets/Logic/pet_brain.py`, `Systems/Pets/PetGames/battle_system.py`, `Systems/Pets/PetGames/pvp_system.py`, `Systems/Pets/PetGames/tournament.py`, `Systems/Pets/PetGames/blackjack.py`, `Systems/Pets/PetGames/craps.py`, `Systems/Pets/PetGames/holdem.py`, `Systems/Pets/PetGames/races.py`, `Systems/Pets/PetGames/slots.py`

The system follows a strict separation of concerns, dividing data management from mathematical logic.

*   **Core System Service (`pets_system.py`)**:
    *   **Service Layer**: `PetSystem` acts as the central state controller, managing asynchronous data persistence via `user_data_manager` and optimized asset preloading via `OptimalFileManager`.
    *   **Adoption Engine**:
        *   **Procedural Generation**: `create_pet` calculates unique base stats (ATT/DEF/HAP/ENE) by combining Species data with Elemental modifiers.
        *   **Name Synthesis**: `_generate_pet_name` dynamically constructs names based on the pet's Category, Primary Element, and Secondary Element (e.g., "FireDragon").
        *   **Interactive UI**: Features a `PetShopView` with category/element filtering and an `AdoptionModal` for custom species entry.
    *   **Progression Systems**:
        *   **Training (`train_pet`)**: reliable XP source (50-200 XP) with difficulty scaling and a 1-minute cooldown.
        *   **Missions (`perform_mission`)**: High-risk ventures with variable success rates (Easy: 70% -> Hard: 30%). Includes "XP Gambling" (double or nothing) and rare material loot drops (20-30% chance).
    *   **Visual Engine**:
        *   **Dashboard**: `PetStatusView` provides a tabbed interface switching between **Main Stats**, **Detailed Breakdown** (equipment bonuses), **Inventory**, and **Casino History**.
        *   **Loot Market**: `LootMarketView` manages a tiered economy where players exchange collected Keys for Chests (Tier 1-4), with higher tiers offering better loot tables.
    *   **State Management**: Implements robust cooldown tracking (Mission: 5m, Train: 1m) and race condition prevention during save operations.

*   **Logic Brain (`pet_brain.py`)**:
    *   **Inventory Logic**:
        *   **Hard Caps**: Enforces strict storage limits to prevent database bloat (16 for Potions, 5 for all other items).
        *   **Auto-Conversion**: Automatically converts overflow items into XP (`Level * 100` per item).
    *   **Potion System**: `use_potion` handles complex item consumption, applying permanent stat boosts (Attribute, Elemental, Luck) or instant XP, while validating elemental compatibility.
    *   **Rarity Engine**: Implements weighted RNG for loot generation, scaling from Common (45%) to Mythic (5%).
    
#### 🥊 Combat Engine
**Files:** `Systems/Pets/PetGames/battle_system.py`, `Systems/Pets/PetGames/pvp_system.py`, `Systems/Pets/PetGames/tournament.py`, `Systems/Pets/Logic/pet_brain.py`

The centralized combat infrastructure governing all entity interactions, from wild encounters to competitive esports-style tournaments. It features a unified turn-based system with complex damage formulas, procedural enemy generation, and real-time state synchronization.

*   **Combat Math & Logic (`pet_brain.py`)**:
    *   **XP Progression**: Uses a geometric leveling formula (`200 * 1.03^(level-1)`) ensuring scalable long-term progression.
    *   **Reward Algorithms**:
        *   **PvP**: Dynamic XP based on performance (`Dealt/10 + Taken/5` for winners).
        *   **PvE**: Base XP (25-150) scaled by difficulty multipliers (Easy: 0.7x to Extreme: 2.0x).
    *   **Loot System**: `LootCalculator` handles inventory grouping, consolidation, and emoji-rich stat block generation.

*   **Battle Engine (`battle_system.py`)**:
    *   **Unified Controller**: `UnifiedBattleView` serves as the central manager for PvE encounters, handling turn logic, AI decision-making, and state persistence.
    *   **Procedural Enemies**: `_generate_enemy_for_pet` creates balanced opponents by scaling stats (Attack/Defense/HP) against the player's power level and selected difficulty (0.7x - 1.5x).
    *   **Smart AI**: Utilizes `NPCBrain` to drive monster behavior, allowing enemies to make tactical decisions (Attack/Defend/Charge) based on the current battle state.
    *   **Async Batching**: Optimizes high-load performance by pre-fetching all participant data via `user_data_manager` in a single batch operation before battle start.
    *   **UX Features**: Includes a "Resend Actions" fail-safe for lost ephemeral interactions and element-themed HP bars that visually represent the combatant's elemental alignment.

*   **PvP Engine (`pvp_system.py`)**:
    *   **Dual Modes**: Supports **1v1 Duels** (Team A vs Team B) and **Free-For-All (FFA)** chaos (Target anyone).
    *   **Secret Information**: Heavily utilizes ephemeral Discord messages to hide moves (Attack/Defend/Charge) until the "Resolution Phase".
    *   **State Feedback**: Action prompts provide detailed context on the previous turn, including exact damage rolls, multipliers, and effectiveness bonuses.
    *   **Turn Synchronization**: Implements a "Wait for All" lock, ensuring fairness by resolving turns only after all active participants have submitted commands.
    *   **Dynamic Visuals**: Features element-specific HP bars that cycle through primary/secondary element emojis, providing instant visual feedback on pet affinities.

*   **Tournament Engine (`tournament.py`)**:
    *   **Bracket Management**: Automates single-elimination brackets for 4, 8, or 16 players, handling seeding, round advancement, and champion declaration without manual intervention.
    *   **Tactical Depth**: Features a "Rock-Paper-Scissors" style combat triangle (Attack/Defend/Charge) where charging boosts damage up to 3.0x but exposes the user to 25% increased incoming damage.
    *   **Themed Immersion**: Fully integrated with the Elemental system, displaying element-specific action confirmations (e.g., "Flame Charge", "Hydro Guard") and emoji-rich HP bars.
    *   **Spectator Experience**: `TournamentBattleView` provides real-time updates with distinct Blue/Red team branding, visual charge meters, and a detailed battle log for audience engagement.
    
#### 🎰 Casino & Mini-Games Engine
**Files:** `Systems/Pets/PetGames/blackjack.py`, `Systems/Pets/PetGames/craps.py`, `Systems/Pets/PetGames/holdem.py`, `Systems/Pets/PetGames/races.py`, `Systems/Pets/PetGames/slots.py`

A comprehensive entertainment suite powering the server's economy, allowing users to wager Pet XP in high-fidelity gambling simulations and competitive mini-games. This engine handles complex real-time session management for multiplayer tables (Poker, Blackjack, Craps), implements rigorous state machines to enforce standard casino rules, and features adaptive AI opponents to ensure 24/7 playability.

*   **Blackjack (`blackjack.py`)**:
    *   **Session Management (`BlackjackSession`)**: Orchestrates multiplayer games with support for mixed Human/Bot tables.
    *   **State Machine**: Tracks individual `PlayerState` for split hands, double downs, and bust status.
    *   **Dealer Logic**: Enforces standard casino rules (Dealer stands on Soft 17) and manages deck shuffling/dealing.
    *   **Integration**: Seamlessly handles XP transactions and stats tracking (`win_streak`) via `user_data_manager`.
*   **Craps (`craps.py`)**:
    *   **Phase Management**: Accurately simulates "Come Out" vs. "Point" phases, enforcing standard rules (Pass Line wins on 7/11, loses on 2/3/12).
    *   **Betting Logic**: Supports 14 distinct bet types including Pass/Don't Pass, Field, Place Bets, and Hardways with proper payout ratios.
    *   **Shooter Rotation**: Auto-rotates the "Shooter" role upon a "Seven Out" event, ensuring fair play in multiplayer sessions.
    *   **Interactive UI**: Features dynamic dice rendering (Red/Blue/Green/etc.) and modal-based bet placement.
*   **Poker (`holdem.py`)**:
    *   **Texas Hold'em Loop**: Manages the complete game flow (Preflop → River → Showdown) with correct betting rounds.
    *   **Hand Evaluator**: Algorithmic ranking of 5-card hands from Royal Flush to High Card using frequency analysis.
    *   **Bot AI**: Implements decision-making opponents (`ai_turn`) that weigh hand strength against pot odds to Call, Raise, or Fold.
    *   **Betting**: Uses a modal interface (`discord.ui.Modal`) to accept custom XP wager amounts and tracks pot size/raises.
*   **Racing (`races.py`)**:
    *   **Speed Formula**: Speed is calculated as `(DEX + ENE + HAP) / 1000 * random(1, 10)`, making high-stat pets consistently faster but preserving upset potential.
    *   **Game Modes**: Supports **Simulation (PvE)** (Player vs 3 Bots with difficulty scaling) and **Multiplayer (PvP)** (Winner takes pot).
    *   **Visuals**: Uses an embed-based track system where emojis (`🐾`, `🐈`) move across a 10-segment track (`➖` -> `🏁`).
*   **Slots (`slots.py`)**:
    *   **Animation**: Features a 6-stage spinning animation using `asyncio.sleep` to build suspense through embed updates.
    *   **Difficulties**: Ranges from **Very Easy** to **Insanity Mode** (dual-reel system matching *Element* + *Species* for payouts up to 2.5 billion XP).
    *   **Payout Logic**: Distinguishes between **Match 3** (High payout) and **Match 2** (Consolation).
    *   **Loot**: Winners have a chance to drop items via `LootCalculator.award_gambling_loot`.

#### 👻 Survivor Series Engine
**Files:** `Systems/Pets/PetGames/pet_ss.py`, `Systems/Pets/PetGames/game_map.py`

A comprehensive Battle Royale simulation engine where pets compete in a procedurally generated world using a custom 13-element biome system. It combines high-level simulation logic with low-level image processing to create immersive, automated tournaments.

*   **Game Session Manager (`pet_ss.py`)**:
    *   **Battle Royale Logic**: Manages high-stakes elimination rounds, tracking `alive` participants and generating a dynamic `kill_log`.
    *   **Event System**: Uses `DataPools` to generate narrative-driven "Actions" (scavenging, moving) and "Eliminations" (combat, traps) based on pet Element/Species.
    *   **Asynchronous Loading**: Features `preload_pets` to efficiently fetch data for dozens of participants without blocking the game loop.
    *   **State Machine**: Handles the full game lifecycle: `Registration` -> `Active Rounds` -> `Sudden Death` -> `Winner Declaration`.
*   **Procedural Map Generation (`game_map.py`)**:
    *   **Dynamic Terrain**: Uses **Pillow (PIL)** to generate organic continent shapes via fractal algorithms (`_fractalize_polygon`) and Chaikin smoothing.
    *   **Biome System**: Partitions the map into 13 elemental zones (e.g., *Emberlands*, *Tideways*, *Skylands*), each with distinct color palettes and environmental hazards.
    *   **Smart Placement**: Implements polygon containment checks (`_point_in_polygon`) to ensure valid spawn points within specific biomes.

#### ⚔️ Gameplay Mechanics
**Files:** `Systems/Pets/pets_commands.py`, `Systems/Pets/PetGames/`

This section outlines the core player experience, defining how users interact with their digital pets through progression, combat, and economy systems. It bridges the gap between the underlying technical architecture and the visible game features.

*   **Adoption & Stats**:
    *   **Species**: 13 Categories (Land, Flying, etc.) and 13 Elements.
    *   **Stats**: **ATT** (Damage), **DEF** (Mitigation), **INT** (Special/Defense), **DEX** (Crit/Dodge), **HAP** (Regen), **ENE** (Max HP).
*   **Progression Loop**:
    *   **Training (`/train`)**: Low-risk XP gain.
    *   **Missions (`/mission`)**: High-risk ventures where failure can result in level loss. Success rates decay from 90% (Easy) to 30% (Extreme).
    *   **Equipment**: Boost stats with Hats, Gems, and Monsters found in **Loot Market** chests (`/loot market`).
*   **Combat Systems**:
    *   **PvE (`/battle`)**: Fight AI monsters with scaled difficulties.
    *   **PvP (`/pvp`)**: Real-time 1v1 or Free-For-All lobbies using `PvPLobbyView`.
    *   **Tournaments**: Automated bracket systems for up to 16 players.
*   **Economy & Gambling**:
    *   **Currency**: Pet XP is the universal currency for betting.
    *   **Games**: Includes **Slots** (with "Insanity" difficulty), **Racing** (Simulated or Live), **Texas Hold'em**, **Blackjack**, and **Craps**.

#### 🎮 Command Controller & UI
**File:** `Systems/Pets/pets_commands.py`

The central "Controller" module that routes user interactions to the appropriate engines. It handles slash command definitions, input validation, and the initialization of complex UI views.

*   **Lobby Management (`PvPLobbyView`)**:
    *   **Dynamic State**: Orchestrates multiplayer lobbies through `WAITING`, `STARTING`, and `IN_PROGRESS` lifecycles.
    *   **Auto-Start**: Triggers a 5-minute countdown for full lobbies, sending DM notifications to participants.
    *   **Host Controls**: Enforces host-only permissions for starting or cancelling matches.
*   **Pet Management**:
    *   **Core Commands**: Routes `/train` and `/mission` to `PetSystem`, handling cooldown feedback and result embeds.
    *   **Inventory Management**: Implements `/equip` and `/use` with context-aware **Autocomplete** for specific item types (Gems, Monsters, Potions).
    *   **Safety**: `/kill` triggers a `KillConfirmView` to prevent accidental deletions.
*   **Game Launchers**:
    *   **Combat Integration**: Initializes `UnifiedBattleView` for PvE (`/battle`) and `TournamentView` for bracketed events (`/tournament`).
    *   **Casino Sessions**: Instantiates game sessions (`BlackjackSession`, `HoldemSession`, `CrapsSession`) with betting mode validation.
    *   **Marketplace**: Deploys the `LootMarketView` via `/loot market` for key redemption.

### 🎯 Fun System

The **Fun System** is a comprehensive entertainment suite designed to drive server engagement through four core pillars: **AI Personalities**, **Astrological Data**, **Arcade Minigames**, and **Interactive Storytelling**. By leveraging external APIs (Groq, Aztro) and complex local logic (Minimax algorithms, state machines), it offers a rich variety of experiences ranging from instant AI-generated humor to deep, multi-stage adventure games.

#### 😇 Good & Evil (Elemental AI)
**File:** `Systems/Fun/goodevil.py`

An advanced AI-powered personality system that generates context-aware roasts and compliments based on user bios, featuring multiple intensity levels and 13 elemental themes.

*   **AI Engine**: Uses the **Groq API** (Llama 3.1) to generate creative, context-aware responses.
*   **Context Awareness**: Scrapes the target user's "About Me" and bio to personalize the content.
*   **Intensity Levels**: Multiple themes from Mild to Explicit, including NSFW options for adult servers.
*   **13 Elements**: Includes **Fire**, **Ice**, **Holy**, **Necro**, **Electric**, and more. Each element dictates the metaphor and tone of the AI's response.
*   **Theme System**: Customized prompts for different intensity levels, from gentle teasing to wild exaggeration.
*   **Fallback System**: Includes pre-written backups to ensure reliability if the API is unreachable.

#### 🔮 Astrology & Horoscopes
**Files:** `Systems/Astrology/signs.py`, `Systems/Astrology/reading.py`

A comprehensive astrological suite featuring professional tarot readings and a complete triple-zodiac profiling system.

*   **Professional Tarot System** (`reading.py`):
    *   **AI-Powered Readings**: Uses Groq API (Llama 3.1) to generate personalized tarot interpretations
    *   **Multiple Spreads**: Supports 1-card, 3-card (Past/Present/Future), and 5-card traditional spreads
    *   **Visual Card Stitching**: Automatically combines drawn cards into a single image using PIL
    *   **Dominant Energy Analysis**: Analyzes card suits to determine reading atmosphere (Fire, Water, Air, Earth, or Major Arcana)
    *   **Interactive Pagination**: Switch between detailed card meanings and AI-generated summaries
    *   **Card Reversal**: Randomly applies reversed card orientations for deeper meanings
    *   **78 Card Database**: Complete Rider-Waite tarot deck with meanings and fortune telling

*   **Triple Zodiac System** (`signs.py`):
    *   **Western Astrology**: Determines sun sign with detailed planetary, elemental, and compatibility data
    *   **Chinese Zodiac**: Calculates animal year with precise Chinese New Year boundary handling (1900-2027)
    *   **Primal Astrology**: Combines Western and Chinese signs to reveal your "Primal Spirit" animal
    *   **Interactive Navigation**: Paginated embeds with button controls for switching between zodiac systems
    *   **Daily Horoscopes**: Real-time predictions from Aztro API with mood, colors, lucky numbers
    *   **Birthday Countdown**: Calculates time until next birthday in weeks/days format

#### 🎲 Classic Games & Utilities
**Files:** `Systems/Fun/fun_system.py`, `Systems/Fun/compete.py`

A comprehensive entertainment suite featuring competitive games, AI opponents, and interactive utilities with multiple themes and difficulty levels.

*   **Tic-Tac-Toe (`/tictactoe`)**:
    *   **Modes**: Play against a friend (PvP) or challenge the AI (PvE).
    *   **AI Difficulty**: Includes a **Minimax Algorithm** implementation ("Impossible" mode) that calculates perfect moves to ensure it never loses. Other difficulties include "Novice" and "Competent".
    *   **Interactive UI**: Uses a 3x3 grid of Discord Buttons for gameplay, updating in real-time.
    *   **Join System**: Modal-based opponent joining with custom emoji selection.

*   **Rock-Paper-Scissors (`/rps`)**:
    *   **Multiple Themes**: Traditional (Rock/Paper/Scissors) and Fantasy (Knights/Archer/Necromancer) with custom emoji sets.
    *   **AI Opponent**: Advanced AI using pattern recognition and strategic decision-making.
    *   **Multi-round Support**: Configurable number of rounds with score tracking.
    *   **History Tracking**: Maintains choice history for AI adaptation.

*   **Sniper Training (`/range`)**:
    *   **Reaction Game**: A "DB4D" style reaction test where players must click the "Hit" button as soon as it appears while avoiding decoys.
    *   **Stat Tracking**: Tracks hits, misses, and accuracy over time, saving personal records via the `UserDataManager`.
    *   **Sessions**: Supports variable round lengths (5, 15, 25, 50, 100).

*   **Coin Flip (`/coin`)**:
    *   **Themed Flips**: Features 7 unique coin styles with custom emoji pairs: **Raider** (Pirate/Poop), **Time** (Future/Retro), **Battery** (Full/Empty), **Electric** (Plug/Socket), **Business** (Open/Closed), **Sky** (Day/Night), and **Temperature** (Hot/Cold).

#### 📖 Interactive Adventures (WalkTru)
**File:** `Systems/Fun/walktru.py`

A sophisticated "Choose Your Own Adventure" engine featuring multiple genres with unique mechanics, stats tracking, and immersive storytelling systems.

*   **6 Unique Genres**:
    *   **Horror**: *The Haunted Sanitarium* - Manage your **Fear** level to avoid panic and insanity.
    *   **Gangster**: *The Gangster's Rise* - Build your empire while keeping your **Heat** low to avoid the police.
    *   **Knight**: *The Knight's Quest* - Maintain your **Honor** through noble choices.
    *   **Robot**: *The Robot Uprising* - Conserve **Power** to survive until you can build a body.
    *   **Western**: *The Western Frontier* - Survive the Wild West by managing your **Health**.
    *   **Wizard**: *The Wizard's Apprentice* - Cast spells and manage your **Mana** pool.
*   **Dynamic Mechanics**:
    *   **Stat Tracking**: Each adventure tracks a core stat (e.g., Fear, Mana) with a visual progress bar.
    *   **Warning System**: Provides immersive warning messages when stats reach critical thresholds (e.g., "The cops are closing in!" or "Your sanity is slipping!").
    *   **RNG Outcomes**: Choices have success chances, leading to different paths and outcomes.
*   **Interactive UI**: Uses Discord Dropdowns for genre selection and Buttons for making choices in the story.

#### 🧟 Zombie Survival System
**File:** `Systems/Fun/zombie.py`

An epic, ongoing AI-driven zombie survival simulation with persistent state management and automated gameplay loops.

*   **Persistent State**: Maintains survivor stats, inventory, and game state across bot restarts.
*   **AI-Driven Events**: Uses Gemini API to generate dynamic survival scenarios and outcomes.
*   **Resource Management**: Tracks health, stamina, morale, and inventory with realistic limits.
*   **Automated Gameplay**: 2-hour update cycles with continuous survival simulation.
*   **Inventory System**: Limited inventory slots with item collection and usage mechanics.
*   **Status Effects**: Multiple survivor states including Normal, Injured, Exhausted, and Deceased.

### 🛡️ Administration System
**File:** `Systems/Functions/admin_system.py`

Tools for bot operators to monitor health, manage data, and control global settings.

*   **Analytics & Logs**:
    *   `/analytics`: View real-time uptime, server count, and command usage stats.
    *   `/logs [user]`: Audit trail of user actions and bot errors.
    *   `/uptime`: Monitor system resource usage (CPU/RAM).
    *   `/debug`: Display detailed debug information (Module status, System info, Failed modules).
*   **Data Management**:
    *   `/admin_clear`: Interactive UI to safely delete corrupted or obsolete user data files.
    *   `/logs_clear`: Purge old log entries to free up space.
    *   `/clear_debug_log`: Clear the local `bot_debug.log` file.
*   **Global Control**:
    *   `/horoscopes [Start/Stop]`: Toggle the daily astrology broadcast.
    *   `/leave`: Force the bot to leave a specific server via a dropdown menu.
    *   `/sync_commands`: Force sync all slash commands to Discord.

### ⚔️ PnW System
**Directory:** `Systems/PnW/`
**Loader:** `pnwhopper.py` (Modular Cog Loader)

A comprehensive toolkit for players of *Politics and War*, architected around a central loader (`pnwhopper.py`) that robustly imports specialized sub-modules for Military (`MA`) and Intelligence (`IA`) operations. This system combines **Military Analytics** (smart targeting, war cost estimation), **Intelligence Suites** (treaty web generation, alliance auditing, market arbitrage), and **Economic Modeling** (revenue calculation, infrastructure logic) into a unified interface. It is powered by a custom **GraphQL Engine** (`query.py`) and **Statistical Aggregator** (`calc.py`) to handle massive data processing efficiently.

- **`pnwhopper.py` (Central System Loader & UI Factory)**:
  - **Fail-Safe Orchestration**: Acts as the master entry point for the PnW system, sequentially attempting to load both **Military (MA)** and **Intelligence (IA)** sub-modules. It wraps each import in isolated `try/except` blocks, ensuring that a crash in one module (e.g., `destroy.py`) does not prevent others (like `alliance.py`) from loading.
  - **Unified UI Factories**: Exports standardized "Mini-Embed" builders to enforce visual consistency across the bot:
    - `build_alliance_mini_embed`: Generates compact alliance stats (Active Nations, Total Score, Cities).
    - `build_nation_mini_embed`: Creates detailed nation dossiers including computed stats like **Avg Infra/City**, **Powered City Count**, and **Activity Status**.

#### 🪖 Military Analytics (MA)
**Directory:** `Systems/PnW/MA/`

The **Military Analytics (MA)** module is a sophisticated offensive toolkit for precision war planning, target acquisition, and economic impact analysis. It integrates intelligent target resolution, optimal attacker matchmaking, and comprehensive loot projection to maximize raiding efficiency and strategic advantage.

- **`destroy.py` (Smart Targeting & War Planning)**:
  - **Target Resolution**: Uses `parse_target_input` with regex patterns to robustly detect Nation IDs, Names, or Links from unstructured user input (e.g., `politicsandwar.com/nation/id=12345`).
  - **Optimal Attacker Finder**: The `/destroy` command analyzes an entire alliance to find the best attackers for a specific target.
  - **Matchmaking Logic**: Filters attackers by **War Range** (75% - 250%), sorts by activity/warchest, and attempts to form "Optimal Groups" of 3 nations that achieve full unit coverage (Ground/Air/Navy) and strategic capability (Nukes/Missiles).
  - **Military Analysis**: Computes detailed combat advantages (`can_nuke`, `has_air_advantage`) and war history stats for the target.
  - **Autocomplete**: Provides smart suggestions for target selection using `destroy_target_autocomplete`.

- **`finder.py` (Bounty & Treasure Hunter)**:
  - **Bounty Hunting**: Advanced filtering for bounties by type (Ordinary, Attrition, Raid, etc.), price range, and nation inactivity.
  - **Treasure Locator**: Finds all available treasures with sorting options for spawn date, bonus percentage, and holder activity.
  - **War Range Filtering**: Narrows down targets to only those within the user's scorable war range.
  - **Canceled Trade Analysis**: Identifies recently rejected or canceled treasure trades to find potential sellers.
  - **Interactive Pagination**: Fully paginated embeds for easy browsing of large result sets.

- **`loot.py` (Loot Projection & Analysis)**:
  - **Intelligence Processing**: Automatically analyzes spy reports to project potential loot based on different policy combinations (Pirate, APE, Moneybags).
  - **Loot Calculation**: Parses war logs to calculate the total value of looted resources using real-time market prices.
  - **Policy Impact Modeling**: Shows how different domestic policies will affect the total value of a raid.
  - **Market Integration**: Fetches live trade values to provide accurate monetary conversions.
  - **Rich Embeds**: Presents loot projections and summaries in clear, easy-to-read Discord embeds.

#### 🧠 Intelligence Analytics (IA)
**Directory:** `Systems/PnW/IA/`

The **Intelligence Analytics** suite is a comprehensive toolkit for alliance management, economic analysis, and strategic intelligence. It features advanced modules for alliance auditing, comparative analytics, resource tracking, revenue modeling, and market analysis, all powered by sophisticated data processing and visualization capabilities.

- **`alliance.py` (Alliance Management & Analytics)**:
  - **Multi-View Dashboard**: Interactive UI with `FullMillView`, `AllianceTotalsView`, and `ImprovementsView` for comprehensive alliance oversight
  - **Military Capacity Analysis**: Calculates total military potential, daily production rates, and "time to max" projections for all unit types
  - **PnwkKit Integration**: Advanced API integration with fallback support for both system and local pnwkit installations
  - **Resource Auditing**: Comprehensive tracking of alliance-wide liquid assets, infrastructure, and military readiness
  - **Inactivity Monitoring**: Automated flagging of inactive members with customizable threshold periods
  - **Infrastructure Breakdown**: Detailed analysis of building distributions and national project portfolios

- **`compare.py` (Comparative Analytics)**:
  - **Head-to-Head Analysis**: Side-by-side alliance comparisons with granular statistical breakdowns
  - **Mobile-Optimized Design**: Custom rendering engine for readable tables on mobile devices
  - **City Distribution Analysis**: Visualizes economic maturity through city count categorization
  - **Parallel Data Processing**: Batched GraphQL queries for optimal performance
  - **Comprehensive Metrics**: Score, cities, military units, and economic indicators

- **`stocks.py` (Resource Market Analytics)**:
  - **Market Visualization**: Advanced charting with matplotlib integration for resource price trends
  - **Portfolio Tracking**: Real-time monitoring of resource stockpiles and market values
  - **Price Analysis**: Historical data processing and trend identification
  - **Container Support**: Configurable data directories for CasaOS/Docker environments
  - **Automated Updates**: Scheduled data refresh cycles for current market information

- **`costs.py` (Economic Modeling & Project Calculator)**:
  - **Project Cost Database**: Comprehensive build cost information for all national projects
  - **Policy Impact Analysis**: Detailed domestic policy effects on infrastructure and development costs
  - **Economic Formulas**: Precise calculation models for infrastructure, land, and project expenses
  - **Resource Requirements**: Complete material and monetary requirements for all game elements
  - **Cost Optimization**: Strategic planning tools for efficient resource allocation

- **`audit.py` (Treaty Web & Alliance Auditing)**:
  - **Treaty Visualization**: Complex diplomatic relationship mapping with PIL-generated graphics
  - **Concentric Ring Layout**: Hierarchical alliance arrangement based on treaty levels
  - **Color-Coded Connections**: Visual distinction between different treaty types (MDoAP, ODoAP, NAP, etc.)
  - **Persistent View Management**: Long-term treaty relationship tracking and storage
  - **Flag Integration**: Dynamic alliance flag processing and standardization

- **`show.py` (Nation Intelligence)**:
  - **Multi-Parameter Search**: Support for Nation ID, Leader Name, Nation Name, and URL-based lookups
  - **Intelligent Caching**: 15-minute TTL cache system to prevent API spam
  - **Infrastructure Analysis**: Comprehensive improvement aggregation across all cities
  - **Power State Logic**: Advanced city power status determination with API data validation
  - **Activity Monitoring**: Human-readable timestamp conversion for inactivity tracking
  - **Economic Profiling**: Detailed nation dossiers with computed statistics

- **`rev.py` (Revenue & Tax Analytics)**:
  - **Hybrid Revenue Calculation**: Combines monetary income with resource production valuations
  - **Policy Impact Modeling**: Accounts for domestic policies, continent bonuses, and radiation effects
  - **Parallel Processing**: Concurrent nation analysis with semaphore-based concurrency control
  - **Expense Tracking**: Detailed upkeep costs for infrastructure, military, and power generation
  - **Alliance Revenue**: Aggregated tax revenue calculations for entire alliances
  - **Market Integration**: Real-time resource price incorporation from market data

- **`snipe.py` (Raiding Intelligence & Strategy)**:
  - **Comprehensive Raiding Guide**: Step-by-step beige sniping tutorials with precise timing instructions
  - **Market Arbitrage Engine**: Dual-mode system for resource price averaging and portfolio valuation
  - **War Mechanics Encyclopedia**: Detailed documentation of combat systems and defensive strategies
  - **Interactive Tutorials**: Multi-part guides with emoji-enhanced instructions
  - **Profit Maximization**: Strategic advice for optimal raiding timing and target selection

- **Additional IA Features**:
  - **Resource File Management**: Centralized data storage with container environment support
  - **Error Handling**: Comprehensive exception management and logging systems
  - **API Integration**: Robust GraphQL query processing with retry mechanisms
  - **Visualization Tools**: Advanced charting and graphical representation capabilities

#### 🔋 Core Utilities (Developer Notes)
**Directory:** `Systems/PnW/Util/`

*   **API Engine (`query.py`)**:
    *   **Class**: `PNWAPIQuery`
    *   **GraphQL Integration**: Uses advanced GraphQL aliasing (e.g., `n0`, `n1`) to batch dozens of queries (like resolving multiple alliance IDs) into a single HTTP request, bypassing the "N+1 problem" and significantly reducing API overhead.
    *   **Resilience & Retries**: Implements a persistent `requests.Session` with `HTTPAdapter` and exponential backoff (`Retry` object with backoff factor 0.3). Automatically handles status codes 429 (Too Many Requests) and 50x (Server Errors).
    *   **Multi-Layered Caching**:
        *   **Query Cache**: In-memory deduplication for identical rapid-fire queries.
        *   **Resolve Cache**: Caches alliance ID/Name resolutions for 1 hour (TTL 3600s) to prevent redundant lookups.
        *   **Trade Cache**: Stores market data to minimize frequent price checks.
    *   **Data Normalization**: Automatically sanitizes API inconsistencies, such as mapping `gasrefinery` to `gasoline_refinery` and flattening nested `cities` data into a usable `improvements` dictionary.
    *   **Smart Fallbacks**: If the API fails to resolve an alliance, the system checks local "Bloc" JSON files or hardcoded configuration maps (e.g., resolving "DB4D" to the home alliance ID).
    *   **Rate Limiting**: Enforces a configurable `_min_interval_seconds` (default 0.15s) between requests to respect API terms of service.
*   **Statistical Engine (`calc.py`)**:
    *   **Class**: `AllianceCalculator`
    *   **Big Data Processing**: A specialized aggregation engine that processes thousands of cities to generate alliance-wide statistics. It iterates through every city of every nation to sum specific improvements (e.g., `coal_power`, `barracks`, `drydock`).
    *   **Smart Filtering**: Automatically excludes nations in **Vacation Mode** or with **Applicant** status to ensure military readiness stats reflect only active combatants.
    *   **Project Normalization**: Contains a robust `project_field_mapping` dictionary to translate between user-friendly project names (e.g., "Uranium Enrichment Program") and their specific API field keys, handling inconsistent naming conventions in the P&W API.
    *   **Concurrency**: Critical CPU-bound tasks (like iterating over 2,000+ cities) are offloaded to a separate thread using `asyncio.to_thread`. This prevents the main Discord event loop from freezing during heavy calculations.
*   **Economic Math (`rev_calc.py`)**:
    *   **Formula Engine**: Encapsulates the exact mathematical models of the game, including:
        *   **Infrastructure Cost**: `((Current Infra-10)^2.2) / 710 + 300`
        *   **Land Cost**: `0.002 * (Current Land-20)^2 + 50`
        *   **Population Growth**: Logarithmic scaling based on city age, disease, and crime factors.
        *   **City Mechanics**: Calculates disease rates, crime rates, and pollution effects on population density.
        *   **Project Costs**: Detailed build costs and modifiers for all National Projects (e.g., "Iron Dome", "Space Program").

### 🎨 Shared Assets & Utilities

The **Shared Assets & Utilities** module serves as the core infrastructure layer for the entire application, providing optimized data management, file I/O, and asset handling. It is designed to maximize performance and consistency across all bot systems.

*   **Data Persistence**: A robust, thread-safe user data manager that utilizes caching and asynchronous background flushing to handle high-frequency economy and profile updates without blocking the main event loop.
*   **Performance I/O**: An optimized file manager that preloads static game data (Equipment, Species, Missions) into memory for O(1) access and ensures atomic, thread-safe file operations.
*   **Visual Consistency**: A centralized emoji registry that manages over 500 custom assets, ensuring uniform UI elements and game icons (Dice, Cards, Pet Elements) throughout the bot.

**File:** `Systems/Functions/user_data_manager.py`

The **User Data Manager** is a high-performance, asynchronous I/O engine designed to handle high-concurrency read/write operations for user profiles. It serves as the backbone for the Pets and Economy systems, ensuring data integrity and minimizing disk latency.

*   **Architecture**:
    *   **Singleton Pattern**: Ensures a single source of truth for all data operations across the bot.
    *   **In-Memory Caching**: Maintains a `_user_cache` to serve read requests instantly, reducing filesystem overhead.
    *   **Asynchronous Flushing**: Uses a background `_flush_loop` to batch-write "dirty" (modified) user data to disk every 2 seconds, preventing I/O blocking during peak usage.
    *   **Concurrency Control**: Implements `asyncio.Lock` per user to prevent race conditions and `asyncio.Semaphore` to limit concurrent file writes (max 50).
*   **Key Features**:
    *   **Smart Migration**: Automatically updates legacy data structures (e.g., migrating old Game stats to the new `gambling_stats` format) via `_process_loaded_data` upon load.
    *   **Granular Stat Tracking**: Specialized methods like `update_pet_battle_stats` and `update_pet_gambling_stats` handle complex atomic updates for wins/losses, XP gains, and high scores.
    *   **Progression Logic**: Encapsulates the core leveling math (`200 * 1.03^(level-1)`) and stat allocation logic within `add_pet_experience`.
    *   **Safety**: Uses `OptimalFileManager` (with temporary file writes) to prevent data corruption during crashes.

**File:** `Systems/Functions/optimal_file_manager.py`

The **Optimal File Manager** is a specialized I/O controller that provides O(1) access to static game data and handles safe, concurrent file operations. It acts as the foundational layer for data persistence, sitting below the `UserDataManager`.

*   **Performance Optimization**:
    *   **Logic Preloading**: On startup, it recursively loads all JSON assets from `Systems/Pets/Logic` into memory (`_logic_cache`), eliminating disk reads for static game data.
    *   **O(1) Lookups**: Builds hash maps for critical data paths, allowing instant retrieval of Equipment (`get_equipment_item`), Pet Species (`get_pet_species_info`), and Mission Scenarios.
    *   **Hunger Games Indexing**: Flattens complex directory structures for the Survivor Series engine into optimized pools (`_hg_optimized`), enabling fast access to "Deadly Locations" and "Elimination" events.
*   **Concurrency & Safety**:
    *   **Thread Safety**: Uses `threading.RLock` for fine-grained file locking (`_file_locks`), ensuring that synchronous reads and asynchronous saves do not corrupt data.
    *   **Async Bridge**: Provides `load_async` and `save_async` wrappers that offload I/O to threads, keeping the main event loop responsive.
    *   **Resilience**: Automatically verifies the integrity of required Hunger Games logic files upon initialization.

**File:** `Systems/Functions/emoji.py`

The **Emoji Registry** is a centralized static asset manager containing over 500 custom Discord emoji definitions. It eliminates hardcoded IDs scattered across the codebase, allowing for single-point updates and theme consistency.

*   **Structure**:
    *   `EMOJI_IDS`: A flat dictionary mapping human-readable keys (e.g., `"Fire"`, `"D20"`, `"health_potion"`) to their Discord Snowflake IDs.
    *   `CATEGORIES`: Logical groupings used for inventory filtering and random generation (e.g., `Hats`, `Gems`, `Materials`, `Dice`).
*   **Asset Coverage**:
    *   **Game Assets**: Full suites for **Dice** (D20 + Colored D6s for Craps), **Cards** (Suits/Ranks for Poker/Blackjack), and **Slot Machine** reels.
    *   **Pet System**: Elemental icons (13 types), Species portraits, Equipment (Hats/Gems), and Consumables (Potions).
    *   **UI Elements**: Standardized buttons for `Confirm`, `Deny`, `LevelUp`, and Navigation.

---

## 📜 Command Reference

### 🐾 Pets Commands
| Command | Description |
|:---|:---|
| `/pet_shop` | Visit the shop to adopt a new pet. |
| `/pet` | View your pet's stats, level, inventory, and equipment. |
| `/rename_pet` | Give your pet a custom name. |
| `/train [difficulty]` | Train your pet to gain XP (1m Cooldown). |
| `/mission [difficulty]` | Send your pet on a risky mission (5m Cooldown). |
| `/equip` | Equip items (Hats, Gems, Monsters, Materials). |
| `/unequip` | Remove items from your pet. |
| `/use [item]` | Use a consumable item like a Potion. |
| `/loot market` | Open loot chests with keys. |
| `/battle [difficulty]` | Start a solo PvE battle against a monster. |
| `/pvp [max]` | Create a lobby for player-vs-player combat. |
| `/kill` | Permanently delete your current pet. |
| **Games** | |
| `/slots` | Play slots (Betting or Fun mode). |
| `/race` | Race your pet (Simulation vs Bots or PvP). |
| `/craps` | Play Craps (supports solo or group). |
| `/holdem` | Play Texas Hold'em (supports AI bots). |
| `/blackjack` | Play Blackjack (supports AI bots). |
| `/tournament` | Create a PvP tournament bracket (4/8/16 players). |

### 🎯 Fun Commands
| Command | Description |
|:---|:---|
| `/walktru` | Start a choice-driven text adventure (6 Genres). |
| `/range [rounds]` | Start Sniper Training (5-100 rounds). |
| `/rangestats [user]` | View accuracy stats and sniper rank. |
| `/tictactoe` | Play Tic-Tac-Toe (PvP or PvE with 3 difficulties). |
| `/rps [theme] [rounds] [opponent]` | Play Rock-Paper-Scissors with themes and AI opponents. |
| `/coin` | Animated coin flip with 7 custom themes. |
| `/walktru` | Start a choice-driven text adventure (6 Genres). |
| `/zombie` | Join the ongoing zombie survival simulation. |
| `/astrology [month] [day] [year]` | View detailed Western, Chinese, and Primal zodiac info. |
| `/tarot [spread]` | Perform a professional tarot reading with AI-powered interpretations. |
| `/horoscope [sign] [day]` | Get daily horoscope for any zodiac sign. |
| `/roast [target] [element]` | Generate a savage, AI-powered roast based on the user's bio (13 Elements). |
| `/compliment [target] [element]` | Generate an uplifting, AI-powered compliment based on the user's bio. |

### 🛡️ Admin Commands
| Command | Description |
|:---|:---|
| `/analytics` | View bot usage statistics. |
| `/logs [user]` | View activity logs for a specific user. |
| `/logs_clear` | Clear bot activity logs. |
| `/uptime` | Check CPU/RAM usage and uptime. |
| `/debug` | Display detailed debug information. |
| `/admin_clear` | UI to delete user data files. |
| `/clear_debug_log` | Clear the bot debug log file. |
| `/horoscopes` | Toggle daily horoscope broadcasts. |
| `/leave` | Leave a server. |
| `/sync_commands` | Force sync slash commands. |

### ⚔️ PnW Commands
| Command | Description |
|:---|:---|
| `/destroy` | **[Key Feature]** Find optimal military targets based on score/loot. |
| `/bounty` | Find active bounties with advanced filtering and sorting. |
| `/treasures` | Locate available treasures with detailed sorting options. |
| `/treasure_trades` | Discover recently canceled treasure trades to find potential buyers. |
| `/wars [atk] [def]` | Analyze war costs (resources/money) between two groups. |
| `/show [target]` | View detailed stats for a nation (ID, Name, or Link). |
| `/compare [a1] [a2]` | Compare stats/military of two alliances side-by-side. |
| `/audit [alliance]` | Generate a Treaty Web image or audit inactivity. |
| `/alliance [id]` | View summary stats for an alliance. |
| `/revenue [alliance]` | Calculate estimated tax revenue for an alliance. |
| `/resource` | Track resource market prices and portfolio values. |
| `/costs` | Calculate project and infrastructure costs. |
| `/snipe` | Get raiding targets and "beige" guides. |
| `/snipe_guide` | Interactive tutorial on raiding mechanics. |

---

## 🏗️ Project Structure

```
Allspark/
├── Systems/
│   ├── Pets/               # Pet system root
│   │   ├── Logic/          # Core mechanics (Stats, Brain)
│   │   ├── PetGames/       # Games (Battle, PvP, Casino)
│   │   └── pets_commands.py# Command definitions
│   ├── Astrology/          # Astrology & Tarot system
│   │   ├── Tarot/          # Tarot cards and readings
│   │   └── Zodiac/         # Zodiac data files
│   ├── Fun/                # Entertainment root
│   ├── PnW/                # Politics and War root
│   │   ├── IA/             # Intelligence Analytics
│   │   ├── MA/             # Military Analytics
│   │   └── Util/           # Core PnW utilities
│   └── Functions/          # Shared bot utilities
├── local_packages/         # Auto-generated dependency folder
├── config.py               # Bot configuration
├── reaper.py               # Main entry point & Bootstrapper
└── README.md               # This file
```
