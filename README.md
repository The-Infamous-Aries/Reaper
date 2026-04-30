# ReaperBot

> **A comprehensive, self-hosted Discord bot featuring advanced Pet systems, Politics & War tools, and interactive entertainment.**  

---

## 📋 Table of Contents

- [ℹ️ Overview](#-overview)
- [⚙️ Configuration & Environment](#️-configuration--environment)
  - [💀 Runtime Bootstrapping & Event Handling](#️-runtime-bootstrapping--event-handling-reaperpy)
- [✨ Major Features](#-major-features)
  - [🌐 Web Interface](#-web-interface)
  - [🌌 Astrology System](#-astrology-system)
    - [reading.py](#readingpy)
    - [signs.py](#signspy)
  - [🤹 Fun System](#-fun-system)
    - [compete.py](#competepy)
    - [fun_system.py](#fun_systempy)
    - [goodevil.py](#goodevilpy)
    - [walktru.py](#walktrupy)
    - [zombie.py](#zombiepy)
  - [🐾 Pets System](#-pets-system)
    - [pets_system.py](#pets_systempy)
    - [pets_commands.py](#pets_commandspy)
    - [🧠 Logic (Core Mechanics)](#-logic-core-mechanics)
      - [Logic/pet_brain.py](#logicpet_brainpy)
      - [Logic/pet_badge.py](#logicpet_badgepy)
    - [🎮 PetGames (Games & Features)](#-petgames-games--features)
      - [PetGames/battle_system.py](#petgamesbattle_systempy)
      - [PetGames/pvp_system.py](#petgamespvp_systempy)
      - [PetGames/tournament.py](#petgamestournamentpy)
      - [PetGames/blackjack.py](#petgamesblackjackpy)
      - [PetGames/craps.py](#petgamescrapspy)
      - [PetGames/holdem.py](#petgamesholdempy)
      - [PetGames/races.py](#petgamesracespy)
      - [PetGames/slots.py](#petgamesslotspy)
      - [PetGames/pet_ss.py](#petgamespet_sspy)
      - [PetGames/game_map.py](#petgamesgame_mappy)
      - [PetGames/quests.py](#petgamesquestspy)
  - [⚔️ PnW System](#️-pnw-system)
    - [pnwhopper.py](#pnwhopperpy)
    - [🧮 EA (Economic Affairs)](#-ea-economic-affairs)
      - [EA/colors.py](#eacolorspy)
      - [EA/resource.py](#earesourcepy)
      - [EA/rev.py](#earevpy)
      - [EA/stocks.py](#eastockspy)
    - [📜 FA (Foreign Affairs)](#️-fa-foreign-affairs)
      - [FA/compare.py](#facomparepy)
      - [FA/treaties.py](#fatreatiespy)
      - [FA/universe.py](#fauniversepy)
    - [🧠 IA (Internal Affairs)](#-ia-internal-affairs)
      - [IA/alliance.py](#iaalliancepy)
      - [IA/audit.py](#iaauditpy)
      - [IA/costs.py](#iacostspy)
      - [IA/show.py](#iashowpy)
      - [IA/guide.py](#iaguidepy)
    - [🪖 MA (Military Affairs)](#-ma-military-affairs)
      - [MA/destroy.py](#madestroypy)
      - [MA/finder.py](#mafinderpy)
      - [MA/wars.py](#mawarspy)
      - [MA/war_costs_bd.py](#mawar_costs_bdpy)
      - [MA/war_net_bd.py](#mawar_net_bdpy)
    - [🥸 Other Fun Stuff](#-other-fun-stuff)
      - [Other/baseball.py](#otherbaseballpy)
      - [Other/loot.py](#otherlootpy)
    - [⚙️ Util (Core Utilities)](#️-util-core-utilities)
      - [Util/calc.py](#utilcalcpy)
      - [Util/query.py](#utilquerypy)
      - [Util/rev_calc.py](#utilrev_calcpy)
      - [Util/war_calc.py](#utilwar_calcpy)
    - [📊 Util/Graphs (Visualization)](#-utilgraphs-visualization)
      - [Util/Graphs/treaty_graph.py](#utilgraphstreaty_graphpy)
      - [Util/Graphs/compare_graph.py](#utilgraphscompare_graphpy)
      - [Util/Graphs/war_graph.py](#utilgraphswar_graphpy)
  - [🛠️ Functions System](#️-functions-system)
    - [utils.py](#utilspy)
    - [config.py](#configpy)
    - [emoji.py](#emojipy)
    - [user_data_manager.py](#user_data_managerpy)
    - [optimal_file_manager.py](#optimal_file_managerpy)
    - [json_database.py](#json_databasepy)
    - [ai_brain.py](#ai_brainpy)
    - [ai_gambling.py](#ai_gamblingpy)
- [📋 Command Reference](#-command-reference)
  - [🤹 Fun Commands](#-fun-commands)
  - [🐾 Pet Utility Commands](#-pet-utility-commands)
  - [🎮 Pet Games Commands](#-pet-games-commands)
  - [🧠 PnW IA (Intelligence Affairs) Commands](#-pnw-ia-intelligence-affairs-commands)
  - [🪖 PnW MA (Military Affairs) Commands](#-pnw-ma-military-affairs-commands)
  - [🧮 PnW EA (Economic Affairs) Commands](#-pnw-ea-economic-affairs-commands)
  - [📜 PnW FA (Foreign Affairs) Commands](#-pnw-fa-foreign-affairs-commands)
  - [🥸 PnW Other Commands](#-pnw-other-commands)
- [🏗️ Project Structure](#️-project-structure)

---

## ℹ️ Overview

**ReaperBot** is a revolutionary, self-hosted Discord bot that transcends traditional gaming bots by forging an entire digital ecosystem within your server. Engineered for **CasaOS** and containerized environments, it features a **self-bootstrapping runtime** that automatically manages dependencies in an isolated `local_packages` environment, ensuring zero-configuration deployment across any platform.

At its architectural foundation lies a **multi-threaded, asynchronous powerhouse** built on enterprise-grade systems: an O(1) in-memory cache with atomic file locking, background persistence loops, and a revolutionary User Data Manager that maintains data integrity across thousands of concurrent users without blocking the event loop. This isn't just a bot—it's a complete digital world engine.

### 🌟 The Four Pillars of Digital Mastery

**🐾 The Living World Engine - Pet System**
Enter a persistent MMORPG universe where digital pets evolve beyond simple companions into complex entities with procedural generation across 13 elemental types, unique stat matrices, and deep progression mechanics. Witness tactical turn-based combat systems supporting team-based PvE raids and intense PvP duels. Experience a fully-realized casino economy featuring Texas Hold'em with strategic AI opponents, Blackjack with advanced betting systems, and multi-difficulty slot machines with animated reels. Engage in automated tournament brackets, survival battle royales with procedural map generation, and AI-powered quest systems that create unique multi-stage adventures tailored to your pet's capabilities.

**⚔️ The Military Intelligence Nexus - PnW System**
Command a professional-grade military intelligence suite for the Politics & War universe. Access real-time GraphQL analytics that process alliance-wide economic data with surgical precision. Deploy automated treaty visualization systems that generate interactive 3D network graphs of diplomatic relationships. Execute "smart" military targeting algorithms that optimize war efficiency through comprehensive analysis of military strength, strategic positioning, and resource allocation. Calculate detailed war cost projections, revenue breakdowns, and resource market analysis with live price integration.

**🔮 The Mystical Arts - Astrology System**
Unlock the secrets of the cosmos through a triple-zodiac profiling engine that synthesizes Western, Chinese, and Primal astrology into comprehensive personality matrices. Experience AI-powered tarot readings with visual card stitching, multiple spread configurations, and dynamic interpretation generation. Access daily horoscope systems with real-time API integration and intelligent caching mechanisms for instant cosmic guidance.

**🎮 The Entertainment Matrix - Fun System**
Immerse yourself in AI-driven entertainment featuring dynamic content generation through Google Gemini and Groq LLMs. Engage in procedural text adventures across six distinct genres with branching narratives and choice-driven outcomes. Participate in ongoing zombie survival simulations where AI generates evolving storylines based on community decisions. Challenge yourself with sniper training games, competitive Rock-Paper-Scissors with learning AI, and classic arcade experiences reimagined for the digital age.

### 🚀 Enterprise-Grade Innovation

**Zero-Configuration Deployment**: Revolutionary self-bootstrapping technology eliminates setup complexity—deploy anywhere, anytime, with automatic dependency management.

**Scalable Architecture**: Multi-layered caching systems, intelligent API batching, and asynchronous request handling ensure optimal performance under extreme load.

**Data Sovereignty**: Atomic file operations with background persistence ensure your digital empire remains intact through any disruption.

**AI Integration**: Advanced LLM orchestration creates personalized experiences that adapt and evolve with your community's unique character.

**Visual Mastery**: Dynamic graph generation, interactive 3D visualizations, and procedural image composition bring data to life in stunning detail.

Whether commanding military alliances, nurturing digital companions, exploring mystical realms, or hosting competitive tournaments, **ReaperBot** delivers an unprecedented fusion of gaming, analytics, and artificial intelligence—transforming your Discord server into a thriving digital civilization.

---

## ⚙️ Configuration & Environment

The bot uses `Systems/Functions/config.py` to load environment variables from a `.env` file. Ensure your `.env` file or system environment variables are set.

| Variable | Description | Required |
|:---|:---|:---|
| `DISCORD_TOKEN` | The bot's authentication token. | **Yes** |
| `COMMAND_PREFIX` | Command prefix (default: `!`). | No |
| `ADMIN_USER_ID` | Discord ID of the bot owner for admin commands. | No |
| `RESULTS_CHANNEL_ID` | Channel ID for game results/logs. | No |
| `DATA_DIR` | Directory for data storage (default: current working directory). | No |
| **API Keys** | | |
| `GEMINI_API_KEY` | Google Gemini API for AI features. | No |
| `GROQ_API_KEY` | Groq API for fast AI text generation (Roasts/Compliments). | No |
| `PANDW_API_KEY` | Politics & War API Key. | No |
| `PANDW_API_V3_KEY` | Politics & War API V3 Key. | No |
| `PANDW_BOT_KEY` | Politics & War Bot Key. | No |
| `HORSCOPE_API` | API key for horoscope features. | No |
| `GIPHY_KEY` | Giphy API key. | No |
| `PIXABAY_KEY` | Pixabay API key. | No |

### 💀 Runtime Bootstrapping & Event Handling (`reaper.py`)
The main entry point and bootstrap system that ensures zero-configuration deployment across any platform with comprehensive dependency management, logging, and event handling.

**Core Architecture Features:**

*   **Advanced Dependency Management System**: 
    *   **Smart Package Detection**: Automatically parses `requirements.txt` and performs intelligent package name normalization to handle complex naming conventions (e.g., `discord.py` → `discord`, `python-dotenv` → `dotenv`)
    *   **Comprehensive Package Mapping**: Maintains a detailed `PACKAGE_TO_MODULE_MAP` for accurate import detection across 20+ packages with non-standard import names
    *   **Local Package Isolation**: Creates a self-contained `local_packages/` environment that prevents conflicts with system-level packages
    *   **Runtime Installation**: Automatically installs missing dependencies using `pip install --target` with proper dependency resolution

*   **Enterprise-Grade Logging System**:
    *   **Colored Console Output**: Custom `ColoredFormatter` with ANSI color codes for different log levels (DEBUG=cyan, INFO=green, WARNING=yellow, ERROR=red, CRITICAL=magenta)
    *   **Dual Output**: Simultaneous file logging (`bot_debug.log`) and colored console output with UTF-8 encoding support
    *   **Detailed Log Format**: Timestamp, level, module, function, line number, and message with proper error handling and duplicate prevention
    *   **Dependency Status Logging**: Comprehensive runtime verification of all vendored dependencies with source tracking (local_packages vs system)

*   **Bot Initialization & System Loading**:
    *   **Sequential Cog Loading**: Systematic loading of all bot systems in dependency order: Core Systems → PnW Hopper → Fun & Utility → Pet System
    *   **Error-Resilient Loading**: Individual cog loading with comprehensive error handling and logging for each system component
    *   **Slash Command Synchronization**: Automatic sync of Discord application commands with detailed logging
    *   **Rich Presence Management**: Sets bot status to "Watching over PnW" with dynamic command prefix display

*   **Security & Resource Management**:
    *   **Owner-Only Shutdown**: Secure `/shutdown` command with dual authentication (`commands.is_owner()` + `ARIES_USER_ID` verification)
    *   **Resource Cleanup**: Automatic port cleanup and graceful shutdown with proper asyncio resource management
    *   **Global Error Handling**: Centralized `on_command_error` event with intelligent filtering (ignores `CommandNotFound` errors)

*   **Performance Optimizations**:
    *   **In-Memory Caching**: Built-in market prices cache (`self.market_prices: Dict[str, float]`)
    *   **Background Task Management**: Proper cleanup of background services and port management
    *   **Async/Await Architecture**: Full async support with proper event loop management

**Runtime Execution Flow:**
1. **Dependency Bootstrap**: Parse requirements → Check local_packages → Install missing dependencies → Verify imports
2. **Configuration Loading**: Load environment variables from `.env` → Validate Discord token → Initialize bot instance
3. **System Initialization**: Setup logging → Configure intents → Initialize data managers → Load extensions
4. **Discord Connection**: Connect to Discord → Sync commands → Set presence → Handle events

To run the bot:
```bash
python reaper.py
```

**Critical Requirements:**
- Valid `DISCORD_TOKEN` in `.env` file (not "YOUR_DISCORD_TOKEN")
- Proper `requirements.txt` file in the same directory
- Write permissions for `local_packages/` directory creation
- Network access for dependency installation if needed

---

## ✨ Major Features

### 🌐 Web Interface
**Directory:** `web/`

A comprehensive, feature-rich web dashboard that provides a graphical interface for many of the bot's features, including data visualization, interactive guides, and system-specific pages.

#### dashboard.html
**File:** `web/dashboard.html`

The main entry point for the web interface. It features a sidebar for navigating between different pages and dynamically loads content.

**Core Features:**
- **Dynamic Page Loading**: Asynchronously loads and displays different pages without requiring a full page reload.
- **Bot Information Display**: Fetches and displays the bot's avatar and name.
- **Responsive Design**: Adapts to different screen sizes for a seamless experience on desktop and mobile devices.

#### Pages
**Directory:** `web/Pages/`

Contains the HTML files for the different pages of the web interface. Each page is dedicated to a specific feature or system of the bot.

- **about.html**: Displays information about the ReaperBot project.
- **astrology.html**: Provides a web interface for the Astrology system, allowing users to explore zodiac profiles and horoscopes.
- **cost_calc.html**: An interface for the PnW cost calculators, allowing users to estimate costs for various in-game actions.
- **directory.html**: A high-level overview and directory of the bot's features, organized by category.
- **fun.html**: A portal to the bot's various fun games and features.
- **graph-viewer.html**: A dedicated page for displaying and interacting with complex graphs and visualizations.
- **graphs.html**: Displays various graphs and visualizations for the PnW system.
- **library.html**: A digital library of guides, articles, and documentation related to the bot and its features.
- **pets.html**: A detailed view of a user's pets, including their stats, inventory, and other information.
- **tarot.html**: An interactive tarot reading page that complements the bot's tarot reading feature.
- **what_are_pets.html**: An introductory page that explains the Pets system to new users.

##### CSS Files
**Directory:** `web/css/`

Contains CSS files responsible for creating dynamic and engaging animations on various web pages, enhancing the user experience.

- **fun_views.css**: Styles for the fun system's animations.
- **library.css**: Custom styles for the library page.
- **casino_views.css**: Styles for the casino system's animations.
- **casino_slots.css**: Styles for the slot machine functionality.

##### JavaScript Files
**Directory:** `web/js/`

Contains JavaScript files for dynamic functionality:

- **casino_views.js**: JavaScript logic for the casino system's animations.
- **fun_views.js**: JavaScript logic for the fun system's animations.
- **casino_dice.js**: JavaScript logic for dice rolling functionality.
- **casino_slots.js**: JavaScript logic for slot machine functionality.

##### Pages/Library
**Directory:** `web/Pages/Library/`

Houses a collection of Markdown files that serve as guides and documentation for various aspects of the bot and the games it supports.

- **Basic Building Guide.md**: A guide for new players on how to build their nation in PnW.
- **Beige Cycle Guide.md**: A guide on the "Beige Cycle" in PnW.
- **FAFO Doctrine.md**: Explains the "FAFO" (Fuck Around and Find Out) doctrine.
- **Snipe.md**: A guide on how to snipe in PnW.
- **Weapon Efficiency Guide.md**: A guide on weapon efficiency in PnW.

#### Wars
**Directory:** `web/Wars/`

Contains generated HTML files that provide detailed reports and analysis of wars in Politics & War.

- **warbd_Nights_Watch_03-23-2026.html**: An example of a detailed war report.

#### api
**Directory:** `web/api/`

Contains the server-side logic for the web interface, built with FastAPI. These endpoints provide data to the frontend, allowing for dynamic content and interactivity.

- **bot_info.py**: An endpoint to fetch basic information about the bot.
- **docs.py**: Serves the API documentation for the web interface.
- **fun_slots.py**: A FastAPI router that handles the logic for the web-based slots game.
- **library.py**: An endpoint for library-related requests, such as fetching articles.

#### css
**Directory:** `web/css/`

Contains the main stylesheets for the web interface, including the Bootstrap framework and custom styles.

- **bootstrap.min.css**: The minified Bootstrap CSS for a responsive layout.
- **bootstrap.min.css.map**: The source map for the Bootstrap CSS.
- **main.css**: Custom stylesheets for the web interface.

#### js
**Directory:** `web/js/`

Contains the main JavaScript files that provide functionality and interactivity to the web interface.

- **MotionPathPlugin.min.js**: A GSAP plugin for animating motion paths.
- **OrbitControls.js**: A Three.js addon for camera controls.
- **gsap.min.js**: The GreenSock Animation Platform for creating high-performance animations.
- **three-globe.min.js**: A Three.js library for creating 3D globe visualizations.

#### static
**Directory:** `web/static/`

Contains all static assets for the web interface, such as images, emojis, and third-party JavaScript libraries.

- **404.html**: The page displayed when a requested page is not found.
- **500.html**: The page displayed in case of a server error.

##### static/Emojis
**Directory:** `web/static/Emojis/`

A vast collection of images used as emojis throughout the web interface and the bot, organized into categories such as Cards, Coins, Dice, Military, Pets, and RPS.

##### static/Images
**Directory:** `web/static/Images/`

Contains general-purpose images used in the web interface, such as backgrounds and logos.

- **FAFO.png**: Image for the FAFO Doctrine.
- **background.jpg**: The background image for the web interface.
- **reaper.png**: The logo for ReaperBot.

##### static/js
**Directory:** `web/static/js/`

Contains static third-party JavaScript libraries used in the web interface.

- **MotionPathPlugin.min.js**: A GSAP plugin for animating motion paths.
- **OrbitControls.js**: A Three.js addon for camera controls.
- **gsap.min.js**: The GreenSock Animation Platform.
- **three-globe.min.js**: A Three.js library for 3D globe visualizations.
- **three.min.js**: The core Three.js library for 3D graphics.

### 🌌 Astrology System
**Directory:** `Systems/Astrology/`

A comprehensive astrological suite featuring professional tarot readings and a complete triple-zodiac profiling system, powered by AI and external APIs for dynamic content generation.

#### reading.py
**File:** `Systems/Astrology/reading.py`

The professional tarot reading engine that combines AI-powered interpretations with visual card manipulation for immersive fortune-telling experiences.

**Core Features:**
- **AI-Powered Readings**: Integrates Groq API (Llama 3.1) to generate personalized tarot interpretations based on drawn cards and user context
- **Multiple Spread Types**: Supports 1-card (Quick), 3-card (Past/Present/Future), and 5-card traditional spreads
- **Visual Card Stitching**: Uses PIL (Pillow) to automatically combine multiple drawn tarot cards into a single cohesive image
- **Dominant Energy Analysis**: Analyzes card suits (Cups, Wands, Swords, Pentacles) and Major Arcana to determine the reading's elemental atmosphere
- **Interactive Pagination**: Features button-based navigation to switch between detailed card meanings and AI-generated summaries
- **Card Reversal System**: Randomly applies reversed orientations (inverted cards) for deeper, more nuanced interpretations
- **78 Card Database**: Complete tarot deck with comprehensive meanings, keywords, and fortune-telling interpretations

**Technical Implementation:**
- **Image Processing**: Advanced PIL operations for card composition, rotation, and overlay effects
- **API Integration**: Robust error handling and fallback systems for AI service interruptions
- **State Management**: Maintains reading session state across Discord interactions
- **Embeds & UI**: Rich Discord embeds with custom formatting and interactive elements

**Advanced Capabilities:**
- **Dynamic Prompt Generation**: Creates contextual AI prompts based on spread type and card positions
- **Energy Threshold Analysis**: Determines dominant elemental forces using mathematical thresholds
- **Session Persistence**: Maintains reading context across Discord interaction timeouts
-- **Error Recovery**: Graceful degradation when AI services are unavailable

#### signs.py
**File:** `Systems/Astrology/signs.py`

The triple-zodiac profiling system that combines Western, Chinese, and Primal astrology for comprehensive, AI-enhanced personality analysis.

**Core Features:**
- **Triple Zodiac Synthesis**: Integrates three distinct astrological systems for a multi-layered personality profile:
  - **Western Astrology**: Precise sun sign determination with elemental associations and compatibility matrices.
  - **Chinese Zodiac**: Accurate animal year calculation with proper Chinese New Year boundary handling (1900-2027).
  - **Primal Astrology**: A unique synthesis of Western and Chinese signs to reveal a user's "Primal Spirit Animal."
- **AI-Powered Personality Profiles**: Leverages a Large Language Model to generate a holistic personality summary, weaving together insights from all three zodiac signs into a single, coherent narrative.
- **Interactive UI**: Features a paginated embed with button controls, allowing users to seamlessly navigate between Western, Chinese, and Primal zodiac details.
- **Daily Horoscopes**: Integrates with the Aztro API to provide real-time daily horoscopes, including mood, lucky color/number, and compatibility.

**Technical Implementation:**
- **Comprehensive Data Models**: Utilizes structured JSON databases for fast, reliable access to zodiac data, including signs, elements, and compatibility info.
- **Robust Date Handling**: Implements sophisticated date parsing and validation to ensure accurate sign calculations across different calendar systems.
- **API Integration & Caching**: Manages connections to external APIs (e.g., Aztro) with intelligent caching to optimize performance and reduce latency.
- **Dynamic Embed Generation**: Builds rich, multi-page embeds that present complex astrological data in a clear and user-friendly format.

**Advanced Capabilities:**
- **Birthday Countdown**: Automatically calculates and displays the time remaining until a user's next birthday.
- **Smart Autocomplete**: Provides helpful autocomplete suggestions for dates to improve user experience.
- **Compatibility Analysis**: Provides detailed relationship compatibility data across all three zodiac systems.


### 🤹 Fun System
**Directory:** `Systems/Fun/`

A collection of engaging and interactive games and commands designed to entertain users, from AI-powered competitions to text-based adventures.

#### compete.py
**File:** `Systems/Fun/compete.py`

A competitive Rock-Paper-Scissors game with multiple themes and an AI opponent, plus dice and card drawing features.

**Core Features:**
- **Multiple Themes**: Supports Traditional (Rock/Paper/Scissors), Fantasy (Knights/Archer/Necromancer), and War (Tank/Jet/Ship) themes
- **AI Opponent**: Features an AI opponent that learns from the player's move history using the `ai_brain` system
- **Multiplayer Support**: Allows two players to compete against each other with join button functionality
- **Customizable Rounds**: Supports 1, 3, or 5 round matches with score tracking
- **Interactive UI**: Button-based gameplay with real-time score updates and round results
- **Additional Games**: Includes dice rolling (D6 with colors, D20) and card drawing (standard deck with custom emojis)

**Technical Implementation:**
- **Game State Management**: Maintains player choices, scores, and round progression
- **AI Learning**: Uses player choice history to make intelligent AI decisions
- **Custom Emoji Integration**: Leverages server emoji system for themed game elements
- **Responsive UI**: Real-time embed updates and button state management

#### fun_system.py
**File:** `Systems/Fun/fun_system.py`

A collection of fun commands, including a coin flip, a sniper training game, and Tic-Tac-Toe.

**Core Features:**
- **Coin Flip**: A visually engaging coin flip with multiple themes and animated results
- **Sniper Training**: A reaction-based game to test and improve the user's sniping skills with detailed performance tracking
- **Tic-Tac-Toe**: A classic game of Tic-Tac-Toe with an AI opponent of varying difficulty and custom emoji support
- **Interactive Adventures**: A text-based adventure game with multiple storylines and branching paths (walktru)

**Technical Implementation:**
- **Game State Management**: Manages active games, user stats, and game progression
- **AI Opponent**: Implements a minimax algorithm for the Tic-Tac-Toe AI
- **Custom Emoji Integration**: Uses server emojis for game elements and UI
- **Data Persistence**: Stores user stats and game records using the `UserDataManager`

#### goodevil.py
**File:** `Systems/Fun/goodevil.py`

An AI-powered roast and compliment generator with customizable intensity levels, plus a crow image fetcher.

**Core Features:**
- **AI-Powered Content**: Integrates with Groq API to generate roasts and compliments using Llama 3.1
- **Customizable Intensity**: Offers multiple themes from Mild to Explicit, controlling the tone and content
- **Personalized Content**: Uses the target's Discord bio to create more personalized roasts and compliments
- **Multiple APIs**: Integrates with Giphy and Pixabay for crow images and GIFs
- **Theme-Based Generation**: Seven intensity levels with specific prompt instructions for each theme

**Technical Implementation:**
- **Groq API Integration**: Uses chat completions for dynamic content generation
- **User Bio Scraping**: Attempts to extract user bio from multiple Discord API sources
- **Image Fetching**: Downloads and serves images from external APIs
- **Content Moderation**: Implements theme-specific content guidelines and fallback systems

#### walktru.py
**File:** `Systems/Fun/walktru.py`

A text-based adventure game with multiple storylines and branching paths.

**Core Features:**
- **Multiple Storylines**: Offers a variety of adventures, including Horror, Gangster, Knight, Robot, Western, and Wizard
- **Branching Paths**: Allows users to make choices that affect the outcome of the story
- **Mechanics System**: Each story has a unique mechanic (e.g., fear, heat, honor) that changes based on the user's choices
- **Interactive UI**: Button-based choices and a dropdown menu for selecting adventures

**Technical Implementation:**
- **Story Map Manager**: Loads and manages story data from JSON files
- **Dynamic Embeds**: Creates and updates embeds to display story progress and choices
- **State Management**: Tracks the player's progress and mechanic values throughout the adventure

#### zombie.py
**File:** `Systems/Fun/zombie.py`

An AI-driven, ongoing zombie survival simulation.

**Core Features:**
- **AI-Driven Story**: Uses the Gemini API to generate a continuous, evolving story
- **Player Choices**: Allows players to vote on choices that affect the story's outcome
- **Survivor Management**: Tracks the health, stamina, and morale of each survivor
- **Persistent State**: Saves the game state to a JSON file, allowing for long-term campaigns

**Technical Implementation:**
- **Gemini API Integration**: Uses the Gemini API for dynamic story and choice generation
- **Asynchronous Game Loop**: The game progresses automatically every two hours
- **State Management**: Manages the game state, including player votes, survivor stats, and story history
- **Interactive UI**: Button-based voting and a command to check your survivor's status


### 🐾 Pets System
**Directory:** `Systems/Pets/`

A comprehensive virtual pet system featuring customizable pets, a robust combat engine, and a wide array of interactive games and activities.

#### pets_system.py
**File:** `Systems/Pets/pets_system.py`

The core of the pet system, managing pet data, interactions, and core mechanics.

**Core Features:**
- **Pet Management**: Handles pet adoption, renaming, and deletion.
- **Pet Data**: Manages pet data, including stats, experience, and inventory.
- **Game Logic**: Implements the logic for training, missions, and other activities.
- **Experience & Leveling**: Manages experience gain and leveling up, including sending level up/down embeds.

#### pets_commands.py
**File:** `Systems/Pets/pets_commands.py`

Defines all pet-related commands, from basic interactions to complex games.

**Core Features:**
- **Pet Commands**: Implements commands for viewing pet status, inventory, and more.
- **Game Commands**: Includes commands for playing games like slots, craps, and blackjack.
- **Combat Commands**: Manages commands for solo battles, PvP, and tournaments.
- **Interactive Lobbies**: Manages lobbies for PvP battles and other multiplayer games.

### 🧠 Logic (Core Mechanics)
**Directory:** `Systems/Pets/Logic/`

This directory contains the core logic for the pet system, including stat calculation, combat mechanics, and image generation.

#### pet_brain.py
**File:** `Systems/Pets/Logic/pet_brain.py`

The brain of the pet system, handling all calculations and game logic.

**Core Features:**
- **Stat Calculation**: Calculates pet stats, including attack, defense, and health, with equipment bonuses.
- **Loot Calculation**: Determines loot drops from battles, missions, and other activities, with rarity-based rolls.
- **Damage Calculation**: Calculates damage for all combat scenarios, including elemental and type advantages.
- **Experience Management**: Manages XP gain, leveling, and stat increases.
- **NPC Brain**: A decision-making AI for monster opponents in PvE battles.

#### pet_badge.py
**File:** `Systems/Pets/Logic/pet_badge.py`

Generates custom pet badges that visually represent a pet's type, elements, and species.

**Core Features:**
- **Image Generation**: Uses Pillow to create custom pet badges by compositing multiple images.
- **Emoji Integration**: Fetches and uses custom emojis from the server for badge elements.
- **Dynamic Positioning**: Adjusts the position of the pet's species emoji based on its type (Flying, Land, Swimming).

### 🎮 PetGames (Games & Features)
**Directory:** `Systems/Pets/PetGames/`

A suite of engaging and competitive games for pets, from classic casino games to a full-fledged battle royale.

#### battle_system.py
**File:** `Systems/Pets/PetGames/battle_system.py`

A comprehensive PvE battle system with team-based combat, loot drops, and boss battles.

**Core Features:**
- **Team-Based Combat**: Supports teams of up to 4 players against AI-controlled monsters.
- **Turn-Based Actions**: Players can attack, defend, or charge to build up power.
- **Loot & Experience**: Awards loot and experience upon victory, with level-up notifications.
- **Boss Battles**: Special boss battles with unique mechanics and rewards.

#### pvp_system.py
**File:** `Systems/Pets/PetGames/pvp_system.py`

A PvP combat system for 1v1 duels and free-for-all battles.

**Core Features:**
- **1v1 & Free-for-All**: Supports both one-on-one duels and multi-player free-for-all battles.
- **Action-Based Combat**: Players can attack, defend, or charge, with actions resolved simultaneously.
- **XP & Rewards**: Awards XP and potential loot to the winner.
- **NPC Integration**: Supports NPC opponents in PvP battles.

#### tournament.py
**File:** `Systems/Pets/PetGames/tournament.py`

Manages automated, bracket-style pet tournaments with registration, auto-fill, and battle progression.

**Core Features:**
- **Automated Bracket Generation**: Creates single-elimination brackets for 4, 8, or 16 players.
- **Registration System**: Players can join or leave during the registration period, with an option for the organizer to auto-fill remaining slots.
- **Automated Match Progression**: Automatically starts matches for each round and advances winners to the next.
- **Live Bracket Display**: Shows a real-time text-based bracket with match results and upcoming battles.
- **Champion Rewards**: Awards bonus XP and loot to the tournament winner.

#### blackjack.py
**File:** `Systems/Pets/PetGames/blackjack.py`

A full-featured blackjack game with support for up to 4 players, betting, and an AI opponent.

**Core Features:**
- **Multiplayer**: Supports up to 4 players, plus AI bots.
- **Betting System**: Players can bet their pet's XP, with winnings and losses automatically calculated.
- **Advanced Rules**: Implements standard blackjack rules, including splitting, doubling down, and insurance.
- **AI Opponent**: Features an AI opponent that makes strategic decisions based on the game state.

#### craps.py
**File:** `Systems/Pets/PetGames/craps.py`

A full-featured craps game with support for multiple players and a wide range of betting options.

**Core Features:**
- **Multiplayer**: Supports multiple players at a single table, with a designated shooter.
- **Full Bet Table**: Implements all major craps bets, including Pass/Don't Pass, Field, Place, and Hardways.
- **Betting System**: Players can bet their pet's XP, with winnings and losses automatically calculated.
- **Shooter Rotation**: The dice automatically pass to the next player on a seven out.

#### holdem.py
**File:** `Systems/Pets/PetGames/holdem.py`

A Texas Hold'em poker game with support for multiple players, betting, and an AI opponent.

**Core Features:**
- **Multiplayer**: Supports multiple players at a single table, with AI bots to fill empty seats.
- **Full Game Flow**: Implements the full Texas Hold'em game flow, including pre-flop, flop, turn, and river betting rounds.
- **Betting System**: Players can bet, call, raise, and fold, with winnings automatically calculated and distributed.
- **AI Opponent**: Features an AI opponent that makes strategic decisions based on hand strength and game state.

#### races.py
**File:** `Systems/Pets/PetGames/races.py`

A pet racing game where players can bet on the outcome.

**Core Features:**
- **Multiple Game Modes**: Supports both simulated (PvE) and multiplayer (PvP) races.
- **Visual Race Track**: A visual representation of the race track in an embed.
- **Dynamic Speed**: A pet's speed is determined by its stats, but with a random element to keep things exciting.
- **Win Streaks**: Winning consecutive races increases the payout multiplier and awards bonus keys.

#### slots.py
**File:** `Systems/Pets/PetGames/slots.py`

A slot machine game with multiple difficulty levels and a betting system.

**Core Features:**
- **Multiple Difficulties**: Six difficulty levels, from Very Easy to Insanity, each with different emoji sets and payout ratios.
- **Betting System**: Players can bet their pet's XP, with winnings and losses automatically calculated.
- **Animated Spins**: A 6-stage spinning animation with random reels for each stage.
- **Insanity Mode**: A special mode with dual reels and pet-matched payouts for massive jackpots.

#### pet_ss.py
**File:** `Systems/Pets/PetGames/pet_ss.py`

A "Survivor" style game where pets compete in a series of challenges until only one remains.

**Core Features:**
- **Large Scale Games**: Supports games with 10-100 participants, including a mix of real users and bots.
- **Interactive Map**: Generates a visual map of the game world, showing player locations and events.
- **Dynamic Events**: A variety of random events, including eliminations, actions, and deadly encounters.
- **Player Choices**: Players can influence the outcome of events by making choices in their DMs.
- **Champions**: Official games record the winner in a hall of fame.

#### game_map.py
**File:** `Systems/Pets/PetGames/game_map.py`

Generates the procedural map for the Pet Survivor Series.

**Core Features:**
- **Procedural Generation**: Uses fractal algorithms to create organic continent shapes.
- **Biome System**: Divides the map into 13 elemental zones, each with its own color palette and environmental hazards.
- **Smart Placement**: Ensures that spawn points and other locations are placed in valid locations.
- **Visual Effects**: Includes terrain shading, coastlines, and decorative elements for a polished look.

#### quests.py
**File:** `Systems/Pets/PetGames/quests.py`

An AI-powered quest generation system that creates unique, multi-stage adventures for pets.

**Core Features:**
- **AI-Powered Generation**: Uses the Groq API to generate unique quests.
- **Multiple Difficulties**: Quests are tailored to the pet's level, with three difficulty tiers: Apprentice, Journeyman, and Senior.
- **Multiple Stages**: Each quest consists of five stages, from entering a location to finding a loot chest.
- **Player Choices**: Players make choices that affect the outcome of the quest, with success determined by their pet's stats.
- **Boss Battles**: Quests can include boss battles that trigger the `battle_system` for a full combat experience.

### ⚔️ PnW System
**Directory:** `Systems/PnW/`

A comprehensive Politics & War (PnW) system that provides economic, military, and diplomatic analysis tools for the online nation simulation game.

#### pnwhopper.py
**File:** `Systems/PnW/pnwhopper.py`

The central loader and dependency injector for all PnW system components. Acts as a "hopper" that systematically loads and configures all PnW cogs with proper shared instances.

**Core Features:**
- **Categorized Cog Loading**: Manages the loading of all PnW system cogs, organized by category (IA, EA, FA, MA, Other).
- **Dependency Injection**: Creates shared instances of query and calculation systems that are injected into dependent cogs.
- **Error Handling**: Provides comprehensive error logging for failed cog loads.
- **Modular Architecture**: Allows for easy addition of new PnW components without modifying core loading logic.
- **Port Initialization**: Initializes the port management system for all cogs that require a web server.

### 🧮 EA (Economic Affairs)
**Directory:** `Systems/PnW/EA/`

Handles all economic-related commands and analysis for the PnW system.

#### EA/colors.py
**File:** `Systems/PnW/EA/colors.py`

Provides information about in-game color bloc bonuses and global game stats, including a dynamically generated radiation pie chart.

**Core Features:**
- **Color Bloc Bonuses**: Displays turn bonuses for each color bloc, sorted from highest to lowest.
- **Global Game Stats**: Shows the current in-game date, city averages, and global radiation levels.
- **Radiation Pie Chart**: Generates a dynamic pie chart visualizing radiation distribution across all continents.

#### EA/resource.py
**File:** `Systems/PnW/EA/resource.py`

Tracks and visualizes historical game resource data, and provides tools for analyzing trade values and converting resource units to monetary value.

**Core Features:**
- **Historical Data Visualization**: Generates dynamic graphs showing resource trends over time, with support for multiple resource groups and custom date ranges.
- **Trade Value Analysis**: Displays current market prices, including average, best buy, and best sell offers, as well as trade margins.
- **Resource Conversion**: Converts specified units of resources into their monetary value based on current market prices.

#### EA/rev.py
**File:** `Systems/PnW/EA/rev.py`

Calculates detailed revenue breakdowns for individual nations and entire alliances, factoring in all in-game modifiers.

**Core Features:**
- **Nation & Alliance Revenue**: Calculates revenue for both individual nations and entire alliances.
- **Comprehensive Breakdown**: Provides a detailed breakdown of income, expenses, and net revenue, including resource production and military upkeep.
- **Modifier Integration**: Automatically factors in domestic policies, color bonuses, and other in-game modifiers.
- **Top Earner Ranking**: For alliances, it ranks the top 5 nations by turn revenue.

#### EA/stocks.py
**File:** `Systems/PnW/EA/stocks.py`

A live market data tracker that displays real-time resource prices and historical trends with interactive graphs.

**Core Features:**
- **Live Market Data**: Provides a live-updating embed with current resource prices, automatically refreshing every two hours.
- **Historical Graphing**: Generates detailed graphs showing 30-day price trends for all resources, with options to view specific categories.
- **Data Optimization**: Uses the LTTB (Largest-Triangle-Three-Buckets) algorithm to optimize large datasets for efficient graph rendering.
- **Persistent Views**: Includes persistent buttons for manual refreshing and other interactions.

### 🗃️ FA (Foreign Affairs)
**Directory:** `Systems/PnW/FA/`

Manages diplomatic and foreign relations data, including treaty analysis and alliance comparisons.

#### FA/compare.py
**File:** `Systems/PnW/FA/compare.py`

Compares two groups of alliances (Home vs. Away) across a wide range of metrics, including military strength, economic power, and nation distribution.

**Core Features:**
- **Side-by-Side Comparison**: Generates a detailed embed comparing two groups of alliances across military, economic, and demographic stats.
- **Dynamic Chart Generation**: Creates and attaches bar charts visualizing city and military distribution for easy comparison.
- **Interactive Web View**: Generates a comprehensive, interactive HTML page with detailed drill-downs for each alliance and serves it via a local web server with ngrok for public access.

#### FA/treaties.py
**File:** `Systems/PnW/FA/treaties.py`

Visualizes an alliance's treaty network with a dynamically generated image, and provides a detailed breakdown of all treaties by type.

**Core Features:**
- **Treaty Web Visualization**: Generates a dynamic image of an alliance's treaty web, with alliances positioned in concentric circles based on treaty type.
- **Categorized Treaty List**: Displays a detailed list of all treaties, categorized by type (e.g., Protectorate, MDP, ODP, NAP).
- **Auto-Updating Embeds**: Supports auto-updating treaty embeds that refresh daily to reflect the latest diplomatic changes.
- **Interactive Refresh**: Includes a refresh button on treaty embeds for on-demand updates.

#### FA/universe.py
**File:** `Systems/PnW/FA/universe.py`

Generates a massive, high-resolution PIL image of the entire PnW treaty universe, with alliances grouped into blocs and connected by treaty-colored lines, plus an interactive web version.

**Core Features:**
- **Massive PIL Image Generation**: Creates a high-resolution image with alliance flags grouped by blocs and connected by treaty lines.
- **Weekly Data Archiving**: Automatically saves treaty data to weekly JSON files for historical tracking and comparison.
- **Interactive Web Version**: Falls back to an interactive HTML map served via a local web server if PIL generation fails.
- **Historical Timeframe Support**: Allows viewing treaty data from any archived week, with autocomplete for easy selection.
- **Curved Treaty Lines**: Implements intelligent line routing to avoid overlapping flags, creating a clean visual layout.

### 🧠 IA (Internal Affairs)
**Directory:** `Systems/PnW/IA/`

Provides tools for internal alliance management, including comprehensive data analysis, auditing, and cost calculation.

#### IA/alliance.py
**File:** `Systems/PnW/IA/alliance.py`

Provides a comprehensive, multi-faceted analysis of an alliance, with interactive views for military strength, improvements, project totals, and resource management.

**Core Features:**
- **Multi-View Interface**: A unified command with interactive buttons to switch between Military, Improvements, Project Totals, and Alliance Totals views.
- **Detailed Military Analysis**: Calculates and displays current military units, daily production, and time-to-max for the entire alliance.
- **Comprehensive Improvements Breakdown**: Shows a detailed breakdown of all improvements across the alliance, categorized for easy analysis.
- **Project Totals**: Lists the total count of each project across all active alliance members.
- **Resource & Inactivity Tracking**: For the default alliance, it shows total resources held; for all alliances, it tracks inactive and grey/beige nations.

#### IA/audit.py
**File:** `Systems/PnW/IA/audit.py`

Provides a comprehensive alliance audit tool that identifies and categorizes member issues, including resource levels, inactivity, color compliance, and military build standards.

**Core Features:**
- **Multi-View Auditing**: A unified command to audit different aspects of an alliance, including Resources, Inactives, Color, and MMR.
- **Resource Auditing**: Flags members with low food or uranium levels.
- **Inactivity Tracking**: Categorizes inactive members into 7-13, 14-23, and 24+ day buckets.
- **Color & MMR Compliance**: Audits members for correct color bloc and adherence to military build standards, with a paginated view for MMR offenders.

#### IA/costs.py
**File:** `Systems/PnW/IA/costs.py`

Calculates the costs for infrastructure, land, cities, and projects, factoring in all relevant domestic policies and existing project discounts for accurate financial planning.

**Core Features:**
- **Comprehensive Cost Calculation**: Accurately computes costs for infrastructure, land, cities, and all national projects.
- **Dynamic Discount Integration**: Automatically applies discounts from domestic policies (e.g., Urbanization, Manifest Destiny) and existing national projects.
- **Detailed Cost Breakdowns**: Provides a clear breakdown of base costs, final costs, and total savings for each item.
- **Resource Value Estimation**: For projects, it estimates the total monetary value of required resources based on current market prices.

#### IA/show.py
**File:** `Systems/PnW/IA/show.py`

Provides a comprehensive, multi-view display of any nation's data, including detailed statistics, military analysis, and a full improvements breakdown.

**Core Features:**
- **Universal Nation Search**: Fetches data for any nation using its name, leader name, ID, or P&W link.
- **Comprehensive Statistics**: Displays a detailed overview of a nation's stats, including alliance, color, policies, and cooldowns.
- **Interactive Views**: Includes buttons to switch between a general overview, a detailed military analysis, and a full improvements breakdown.
- **Detailed Military & Improvements**: Provides in-depth analysis of a nation's military capacity, production, and a full list of all improvements by category.

#### IA/guide.py
**File:** `Systems/PnW/IA/guide.py`

Provides a comprehensive, in-character guide to beige sniping, raiding, and advanced warfare mechanics, delivered through a series of interactive commands.

**Core Features:**
- **In-Character Sniping Guide**: A detailed, 10-step guide on how to effectively find, time, and execute raids on beige targets, complete with thematic emojis and personality.
- **Modular War Guides**: Separate, detailed guides for key warfare mechanics, including Ground/Air/Naval Supremacy, Missiles, Nukes, Fortification, and Peace.
- **Interactive Command Structure**: Users can view the entire guide at once or access specific sections (e.g., `/snipe_setup`, `/snipe_execute`, `/war_guide [category]`) for targeted information.

### 🪖 MA (Military Affairs)
**Directory:** `Systems/PnW/MA/`

Provides tools for military planning and analysis, including war simulations and target identification.

#### MA/destroy.py
**File:** `Systems/PnW/MA/destroy.py`

Identifies optimal attackers for a given target by analyzing military strength, war range, and strategic positioning, and provides a detailed breakdown of both the target and potential attackers.

**Core Features:**
- **Optimal Attacker Identification**: Finds the best attackers from one or more alliances who are within war range of a specified target.
- **Multi-Alliance Search**: Can search for attackers across multiple alliances simultaneously.
- **Detailed Target & Attacker Analysis**: Provides a comprehensive breakdown of both the target and each potential attacker, including military units, daily production, and strategic projects.
- **Exclusion of Unoptimal Targets**: Can optionally exclude nations with high infrastructure or zero military units to focus on viable targets.

#### MA/finder.py
**File:** `Systems/PnW/MA/finder.py`

Searches for bounties and treasures with advanced filtering and sorting, and tracks recently canceled treasure trades to identify potential buyers.

**Core Features:**
- **Advanced Bounty & Treasure Search**: Finds active bounties and treasures with multiple filtering options, including price/bonus, inactivity, and war range.
- **Flexible Sorting**: Sorts results by price/bonus, or activity (newest/oldest).
- **Canceled Trade Tracking**: Identifies recently canceled or rejected treasure trades, providing insights into potential market opportunities.
- **Paginated Results**: Displays results in a clean, paginated embed for easy navigation.

#### MA/wars.py
**File:** `Systems/PnW/MA/wars.py`

Provides a comprehensive war analysis tool that calculates the costs and outcomes of wars between specified teams, with detailed breakdowns, interactive graphs, and PDF reports.

**Core Features:**
- **Multi-Entity War Analysis**: Calculates war costs for nations or alliances over a specified time range (e.g., '1d', '3w').
- **Interactive Cost Breakdowns**: A multi-view embed with buttons to switch between a summary, military costs, destruction costs, and loot gained.
- **Dynamic Cost Graph**: Generates a dynamic PNG pie chart visualizing the gross cost breakdown for both teams, including units, consumption, and infrastructure.
- **Detailed PDF Reports**: For large-scale wars, it generates a comprehensive PDF report with a detailed breakdown of every individual war, including costs, winners, and net outcomes.

#### MA/war_costs_bd.py
**File:** `Systems/PnW/MA/war_costs_bd.py`

Provides a comprehensive, interactive war breakdown for an entire alliance, with detailed cost analysis, member-specific contributions, and a live, interactive web view.

**Core Features:**
- **Alliance-Wide War Breakdown**: Generates a detailed cost breakdown for an entire alliance over a specified time, including gross/net costs and win/loss records.
- **Interactive Web View**: Creates a dynamic, interactive HTML page with drill-down charts and tables, served via a local web server with ngrok for public access.

#### MA/war_net_bd.py
**File:** `Systems/PnW/MA/war_net_bd.py`

Provides a comprehensive, interactive war breakdown for an entire alliance, with detailed net damage analysis, member-specific contributions, and a live, interactive web view.

**Core Features:**
- **Alliance-Wide War Net Breakdown**: Generates a detailed net damage breakdown for an entire alliance over a specified time, including gross/net costs and win/loss records.
- **Interactive Web View**: Creates a dynamic, interactive HTML page with drill-down charts and tables, served via a local web server with ngrok for public access.
- **Opponent Perspective**: Can flip the analysis to show the war from the opponents' perspective, detailing their costs and losses.
- **Member Contribution Analysis**: Provides a paginated breakdown of each member's contribution to the war effort, including their individual net costs and gains.

### 🥸 Other Fun Stuff
**Directory:** `Systems/PnW/Other/`

A collection of miscellaneous and fun commands related to PnW.

#### Other/baseball.py
**File:** `Systems/PnW/Other/baseball.py`

Fetches and displays detailed statistics for a nation's baseball team, including stadium details, win/loss records, and career statistics.

**Core Features:**
- **Comprehensive Team Analysis**: Shows a nation's baseball team name, stadium, quality, seating, and overall rating.
- **Dynamic Star Rating**: Calculates and displays a star rating based on stadium quality and seating capacity.
- **Career Statistics**: Provides a detailed breakdown of career wins, losses, runs, homeruns, and strikeouts.
- **Flexible Search**: Can find a team using the nation name, leader name, or nation ID.

#### Other/loot.py
**File:** `Systems/PnW/Other/loot.py`

Automatically parses PnW war messages to calculate and display projected and actual loot values, factoring in different policy combinations.

**Core Features:**
- **Automatic Message Parsing**: Listens for user messages and automatically detects and parses both intelligence reports (projected loot) and battle logs (actual loot).
- **Projected Loot Scenarios**: For intelligence reports, it calculates six different loot scenarios based on all possible combinations of the Pirate, Advanced Pirate Economics, and Moneybags policies.
- **Actual Loot Calculation**: For battle logs, it parses all looted resources and money, then calculates their total market value based on current best sell offers.
- **Dynamic Embeds**: Presents the calculations in a clean, easy-to-read embed, showing a full breakdown of resources and their monetary value.

### ⚙️ Util (Core Utilities)
**Directory:** `Systems/PnW/Util/`

Core utilities and helper functions for the PnW system.

#### Util/calc.py
**File:** `Systems/PnW/Util/calc.py`

A comprehensive, multi-threaded calculation engine that provides detailed statistical analysis for nations and alliances, including military capacity, economic output, and war potential.

**Core Features:**
- **Multi-Threaded Calculations**: Offloads heavy computations to separate threads to prevent blocking the bot's main event loop.
- **Alliance-Wide Statistics**: Aggregates and calculates statistics for entire alliances, including total score, cities, and military units.
- **Military Production & Capacity**: Calculates daily military production rates and maximum unit capacities based on a nation's infrastructure and research.
- **Improvement & Resource Analysis**: Provides detailed breakdowns of alliance-wide improvements and total resource reserves.
- **War Range & Compatibility**: Determines valid war ranges for individual nations and entire parties, and calculates infrastructure compatibility between nations.

#### Util/query.py
**File:** `Systems/PnW/Util/query.py`

A centralized, high-performance GraphQL query engine for the PnW API, featuring asynchronous requests, intelligent caching, and automatic pagination.

**Core Features:**
- **Asynchronous & Batched Requests**: Executes multiple GraphQL queries concurrently and batches them into single HTTP requests to maximize efficiency.
- **Intelligent Caching**: Implements a multi-layer caching system for query results, entity resolutions, and trade data to minimize redundant API calls.
- **Automatic Pagination**: Seamlessly handles paginated API endpoints, automatically fetching all pages of data for a complete dataset.
- **Robust Error Handling & Retries**: Includes automatic retries with exponential backoff for network errors and API rate limits.
- **Entity Resolution**: A powerful resolver that can find nations and alliances using their name, ID, leader name, or even a P&W link.

#### Util/rev_calc.py
**File:** `Systems/PnW/Util/rev_calc.py`

A comprehensive revenue calculation engine that factors in domestic policies, color bonuses, alliance tax brackets, military upkeep, and resource market prices to determine a nation's true net income.

**Core Features:**
- **Policy & Tax Integration**: Automatically applies domestic policy effects (e.g., Open Markets, Imperialism) and alliance tax bracket calculations.
- **Resource Production & Consumption**: Calculates net resource production and consumption, factoring in all improvements and military requirements.
- **Military Upkeep**: Accurately calculates military upkeep for both peacetime and wartime scenarios.
- **Market Price Integration**: Uses live market prices to value resource surpluses and deficits.
- **Asynchronous API Integration**: Works with the query system to fetch real-time data, including market prices and tax brackets.

#### Util/war_calc.py
**File:** `Systems/PnW/Util/war_calc.py`

A comprehensive war calculation engine that processes raw war data to determine the total financial costs for each side, including units lost, infrastructure destroyed, and resources consumed.

**Core Features:**
- **Detailed Cost Aggregation**: Calculates the total cost of war by aggregating losses from ground battles, missile strikes, and nuclear attacks.
- **Resource & Unit Valuation**: Uses live market prices to accurately value all units, resources, and improvements lost during a conflict.
- **Loot & Salvage Calculation**: Factors in all loot gained—including money and resources—and the value of salvaged materials to determine a true net cost.
- **Team-Based Analysis**: Can analyze wars between two distinct teams of nations or alliances, correctly attributing all costs and gains to the appropriate side.

### 📊 Util/Graphs (Visualization)
**Directory:** `Systems/PnW/Util/Graphs/`

Handles the generation of graphs and visualizations for the PnW system.

#### Util/Graphs/treaty_graph.py
**File:** `Systems/PnW/Util/Graphs/treaty_graph.py`

Generates a dynamic, interactive 3D graph of the entire PnW treaty universe, with advanced bloc detection, hierarchical layout, and a feature-rich web interface.

**Core Features:**
- **Interactive 3D Visualization**: Creates a Plotly-based 3D graph of the treaty web, with draggable, pinnable alliance cards and dynamic filtering.
- **Advanced Bloc Detection**: Intelligently identifies and groups alliances into blocs based on shared high-level treaties (MDP, MDoAP, etc.).
- **Hierarchical Layout**: Positions blocs and alliances in a 3D spiral layout based on their total score, creating a clean and intuitive visualization.
- **Dynamic Styling**: Automatically styles nodes and edges based on alliance color and treaty significance, with contrast-aware text for readability.
- **Full Web Interface**: Generates a self-contained HTML file with a sidebar for filtering alliances and blocs, and custom JavaScript for a rich user experience.

#### Util/Graphs/compare_graph.py
**File:** `Systems/PnW/Util/Graphs/compare_graph.py`

Generates a comprehensive, interactive comparison page for two sets of alliances, with detailed breakdowns of military strength and nation distribution.

**Core Features:**
- **Interactive Web Interface**: Creates a self-contained HTML page with a Plotly graph and a sidebar for dynamic filtering.
- **Dual-View Analysis**: Provides two distinct views—Military and Nations—to compare alliances across different metrics.
- **Stacked Bar & Line Charts**: Uses stacked bar charts to visualize military contributions and line charts to show nation distribution by city count.
- **Dynamic Filtering**: Allows users to toggle the visibility of individual alliances or entire sides (Home vs. Away) for focused analysis.
- **Persistent Hover Details**: On-click, it can display persistent, detailed breakdowns of contributions for any given metric, allowing for in-depth analysis.

#### Util/Graphs/war_graph.py
**File:** `Systems/PnW/Util/Graphs/war_graph.py`

Generates a highly interactive, multi-level sunburst chart for war breakdowns, with dynamic nation toggles, cost component drill-downs, and a polished web interface.

**Core Features:**
- **Interactive Sunburst Chart**: Creates a Plotly-based sunburst chart that visualizes war costs, with levels for nations and their individual cost components.
- **Dynamic Nation Toggles**: Provides a sidebar with toggles to dynamically include or exclude nations from the chart, with real-time updates to total costs.
- **Cost Component Drill-Down**: Allows users to click on a nation to expand its cost components, with detailed hover information for each category (units, consumption, etc.).
- **Advanced Color Generation**: Uses a sophisticated color generation algorithm to ensure that all nations and their sub-components are visually distinct.
- **Self-Contained Web Page**: Generates a single, self-contained HTML file with embedded JavaScript for a fully interactive experience.

### 🛠️ Functions System
**Directory:** `Systems/Functions/`

Core functions and utilities that are shared across the entire bot.

#### utils.py
**File:** `Systems/Functions/utils.py`

A centralized port management system for handling multiple web servers across different cogs without port conflicts.

**Core Features:**
- **Centralized Port Management**: Manages port allocation and deallocation to prevent conflicts.
- **Service-Based Port Allocation**: Assigns a unique port to each service that requires one.
- **Smart Port Conflict Resolution**: Automatically finds the next available port if the preferred port is unavailable.
- **Proper Resource Management**: Allocates ports on bot startup and cleans them up on shutdown.

#### config.py
**File:** `Systems/Functions/config.py`

Loads all environment variables and configuration settings for the bot, including API keys, the command prefix, and other critical parameters.

**Core Features:**
- **Centralized Configuration**: A single source of truth for all configuration variables.
- **Environment Variable Loading**: Uses `dotenv` to load configuration from a `.env` file for easy management.
- **Secure API Key Management**: Keeps all API keys and sensitive information out of the codebase.

#### emoji.py
**File:** `Systems/Functions/emoji.py`

A centralized registry for all custom emojis used throughout the bot.

**Core Features:**
- **Emoji Management**: Provides a single source of truth for all custom emoji IDs.
- **Easy Access**: Allows for easy access to emojis by name.
- **Thematic Emojis**: Includes a wide variety of emojis for different themes and games.

#### user_data_manager.py
**File:** `Systems/Functions/user_data_manager.py`

A comprehensive, asynchronous user data management system with an in-memory cache, background flushing, and atomic file operations to ensure data integrity.

**Core Features:**
- **Asynchronous & Thread-Safe**: Uses `asyncio` and file locks to handle concurrent data access without blocking the main event loop.
- **In-Memory Caching**: Implements an O(1) in-memory cache for user data to minimize disk I/O.
- **Background Flushing**: A dedicated background task automatically flushes "dirty" user data to disk, ensuring data persistence without sacrificing performance.
- **Atomic File Operations**: Uses file locks to prevent race conditions and data corruption during read/write operations.
- **Data Migration**: Includes a robust data migration system to seamlessly update user data structures across different versions.

#### optimal_file_manager.py
**File:** `Systems/Functions/optimal_file_manager.py`

An optimized file manager for handling JSON data, with specialized preloading for the Pets system and general-purpose load/save functionality for other files.

**Core Features:**
- **Optimized Preloading**: Preloads all JSON files from the `Systems/Pets/Logic` directory into memory for O(1) access.
- **Optimized Indexes**: Builds optimized indexes for frequently accessed data, such as equipment, pet species, and base names.
- **Asynchronous Support**: Includes asynchronous methods for non-blocking I/O.
- **Fine-Grained File Locking**: Uses file-level locks to prevent race conditions during read/write operations.

#### json_database.py
**File:** `Systems/Functions/json_database.py`

A simple, file-based JSON database for storing and retrieving data.

**Core Features:**
- **Weekly Data Files**: Stores data in weekly JSON files for easy management and cleanup.
- **Asynchronous Operations**: Uses `aiofiles` for asynchronous file I/O.
- **Thread-Safe**: Includes a file lock to ensure thread-safe operations.
- **Live Message Tracking**: Includes functionality for tracking and managing live dashboard messages.

#### ai_brain.py
**File:** `Systems/Functions/ai_brain.py`

A strategic AI for the Rock-Paper-Scissors game that analyzes the player's move history to make intelligent choices.

**Core Features:**
- **Player Move Analysis**: Analyzes the player's move frequency to predict their next move.
- **Randomness**: Introduces randomness to avoid predictability.
- **Thematic Choices**: Supports different themes, including Traditional, Fantasy, and War.

#### ai_gambling.py
**File:** `Systems/Functions/ai_gambling.py`

An advanced AI for the Texas Hold'em and Blackjack games that makes strategic decisions based on hand strength, pot odds, and game state.

**Core Features:**
- **Advanced Hand Evaluation**: Includes a sophisticated hand evaluation function for Texas Hold'em.
- **Strategic Betting**: Makes strategic betting decisions based on hand strength and pot odds.
- **Bluffing**: Includes a bluffing mechanic to make the AI more unpredictable.
- **Blackjack Strategy**: Implements a basic blackjack strategy for the AI opponent.

### 🌐 Web Interface
**Directory:** `web/`

A comprehensive, feature-rich web dashboard that provides a graphical interface for many of the bot's features.

#### dashboard.html
**File:** `web/dashboard.html`

The main entry point for the web interface. It features a sidebar for navigating between different pages and dynamically loads content.

**Core Features:**
- **Dynamic Page Loading**: Asynchronously loads and displays different pages without requiring a full page reload.
- **Bot Information Display**: Fetches and displays the bot's avatar and name.
- **Responsive Design**: Adapts to different screen sizes for a seamless experience on desktop and mobile devices.

#### Pages
**Directory:** `web/Pages/`

Contains the HTML files for the different pages of the web interface.

- **directory.html**: A high-level overview of the bot's features, divided into categories.
- **graphs.html**: Displays various graphs and visualizations for the PnW system.
- **cost_calc.html**: Provides calculators for PnW related costs.
- **what_are_pets.html**: An introduction to the Pets system.
- **pets.html**: A detailed view of the user's pets.
- **tarot.html**: An interactive tarot reading page.
- **astrology.html**: Displays astrology information.
- **fun.html**: Provides access to fun commands and games.

#### api
**Directory:** `web/api/`

Contains the server-side logic for the web interface.

- **bot_info.py**: Fetches bot information.
- **docs.py**: Serves the API documentation.
- **fun_slots.py**: A FastAPI router that handles the logic for a slots game.
- **library.py**: Handles library-related requests.

#### Emojis
**Directory:** `web/static/Emojis/`

A vast collection of images used throughout the web interface and the bot, organized into categories such as Cards, Coins, Dice, Military, Pets, and RPS.

#### Wars
**Directory:** `web/Wars/`

Contains HTML files with detailed reports of PnW wars.

---

## 📜 Command Reference

### 🤹 Fun Commands
| Command | Description |
|:---|:---|
| `/range [rounds]` | Start Sniper Training (5-100 rounds). |
| `/rangestats [user]` | View shooting range statistics. |
| `/walktru` | Start an interactive adventure experience. |
| `/coin [coin_type] [call_side]` | Flip a coin with custom styles. |
| `/tictactoe [emoji] [npc] [rounds] [difficulty]` | Play Tic-Tac-Toe! |
| `/rps [rival] [rounds] [theme]` | Play Rock Paper Scissors. |
| `/dice [dice_type] [amount]` | Roll some dice. |
| `/card [count]` | Draw some cards. |
| `/zombie_survival` | Start or join the Zombie Survival game. |
| `/zstatus` | Check your survivor status. |
| `/roast [target] [theme]` | Get roasted with different intensity levels! |
| `/compliment [target] [theme]` | Get compliments with different intensity levels! |
| `/crow [type]` | Fetch a random crow photo or GIF. |
| `/astrology [month] [day] [year]` | Show your zodiac sign info based on your birthday. |
| `/tarot [spread]` | Perform a professional tarot reading. |
| `/horoscope [sign] [day]` | Get the horoscope for a zodiac sign. |

### 🐾 Pet Utility Commands
| Command | Description |
|:---|:---|
| `/pet_shop` | Visit the Pet Shop to adopt a pet. |
| `/pet` | View your digital pet's status. |
| `/pet_badge` | Generate a badge for your pet. |
| `/inventory` | View your pet's inventory. |
| `/rename pet [new_name]` | Rename your pet. |
| `/rename attack [label]` | Rename your pet's attack action. |
| `/rename defend [label]` | Rename your pet's defend action. |
| `/rename charge [label]` | Rename your pet's charge action. |
| `/equip [material] [gems] [monsters] [hat]` | Equip items to your pet. |
| `/unequip [slot]` | Unequip items from your pet. |
| `/use [item]` | Use a consumable item (Potion). |
| `/loot market` | Open the Loot Market to open chests. |
| `/kill` | Permanently delete your digital pet. |

### 🎮 Pet Games Commands
| Command | Description |
|:---|:---|
| `/train [difficulty]` | Train your pet to gain experience. |
| `/mission [difficulty] [gamble_xp]` | Send your pet on a mission to gain experience. |
| `/battle [difficulty]` | Start a solo battle against a monster. |
| `/pvp [max]` | Start a PvP free-for-all lobby. |
| `/race [simulation] [difficulty] [bet]` | Race pets in simulation or lobby mode. |
| `/craps [solo] [mode] [bet]` | Play Craps with Pet XP betting. |
| `/holdem [solo] [buy_in]` | Play Texas Hold'em with Pet XP betting. |
| `/blackjack [solo] [mode] [bet]` | Play Blackjack with Pet XP betting or for fun. |
| `/quest [location] [difficulty]` | Embark on a quest with your pet! |
| `/tournament [size] [participants]` | Create a pet tournament bracket. |
| `/slots [difficulty] [mode]` | Play Pet XP Slots. |

### 🧠 PnW IA (Internal Affairs) Commands
| Command | Description |
|:---|:---|
| `/show [target]` | Show a nation by name, leader, ID, or link. |
| `/alliance [id]` | View summary stats for an alliance. |
| `/compare [a1] [a2]` | Compare stats/military of two alliances. |
| `/audit [alliance]` | Generate a Treaty Web image or audit inactivity. |

### 🪖 PnW MA (Military Affairs) Commands
| Command | Description |
|:---|:---|
| `/destroy [target] [attackers] [ beige]` | Find optimal attackers for a target nation. |
| `/wars [team1] [team2]` | Analyze war costs between groups. |
| `/wars cost bd` | War battle data analysis. |
| `/wars net bd` | War battle net data analysis. |
| `/finder` | Find treasures and bounties. |
| `/treasures [sort] [active] [nation_id]` | Find all available treasures. |
| `/treasure_trades` | Find recent treasure trades that were canceled. |
| `/bounty [bounty_type] [price] [nation_id]` | Find active bounties. |
| `/snipe_guide` | Interactive tutorial on raiding mechanics. |

### 🧮 PnW EA (Economic Affairs) Commands
| Command | Description |
|:---|:---|
| `/resource` | Track resource market prices. |
| `/stocks [graph_type] [days]` | Display P&W market prices and trends. |
| `/history` | Show historical market data for a custom date range. |
| `/costs [nation_id]` | Calculate project and infrastructure costs. |
| `/rev` | Revenue calculations. |
| `/colors` | Game color information. |

### 📜 PnW FA (Foreign Affairs) Commands
| Command | Description |
|:---|:---|
| `/treaties` | Manage treaties. |
| `/universe` | Universe/foreign affairs information. |

### 🥸 PnW Other Commands
| Command | Description |
|:---|:---|
| `/baseball` | Baseball-related commands. |

### 👑 Admin Commands
| Command | Description |
|:---|:---|
| `/shutdown` | Securely shuts down the bot. (Owner only) |

---

## 🏗️ Project Structure

```
Reaper/
├── Systems/                    # Core bot systems
│   ├── Astrology/              # Astrology & Tarot system
│   │   ├── reading.py         # Tarot readings and AI interpretations
│   │   └── signs.py           # Zodiac and horoscope functionality
│   ├── Data/                  # Data storage initialization
│   │   └── __init__.py
│   ├── Fun/                   # Entertainment and games
│   │   ├── compete.py         # Competitive games (Tic-Tac-Toe, RPS)
│   │   ├── fun_system.py      # Core fun system and utilities
│   │   ├── goodevil.py        # AI roasts and compliments
│   │   ├── walktru.py         # Interactive text adventures
│   │   └── zombie.py          # Zombie survival simulation
│   ├── Functions/             # Shared utilities and core systems
│   │   ├── config.py          # Configuration and environment
│   │   ├── emoji.py           # Centralized emoji registry
│   │   ├── user_data_manager.py # User data management
│   │   ├── optimal_file_manager.py # File management
│   │   ├── json_database.py   # JSON database utilities
│   │   ├── ai_brain.py        # AI utilities
│   │   └── ai_gambling.py     # AI gambling utilities
│   ├── Pets/                  # MMORPG Pet system
│   │   ├── Logic/             # Pet data and mechanics
│   │   │   ├── pet_brain.py   # Pet logic
│   │   │   └── pet_badge.py   # Pet badge generation
│   │   ├── PetGames/          # Pet games
│   │   │   ├── battle_system.py # Battle system
│   │   │   ├── pvp_system.py  # PvP system
│   │   │   ├── tournament.py  # Tournament system
│   │   │   ├── blackjack.py   # Blackjack game
│   │   │   ├── craps.py       # Craps game
│   │   │   ├── holdem.py      # Hold'em game
│   │   │   ├── races.py       # Racing game
│   │   │   ├── slots.py       # Slots game
│   │   │   ├── pet_ss.py      # Pet Super-slots
│   │   │   ├── game_map.py    # Game map
│   │   │   └── quests.py      # Quest system
│   │   ├── pets_system.py     # Core pet system engine
│   │   └── pets_commands.py   # Pet commands
│   ├── PnW/                   # Politics & War toolkit
│   │   ├── EA/                # Economic Analytics
│   │   │   ├── colors.py      # Resource color coding
│   │   │   ├── resource.py    # Resource market analysis
│   │   │   ├── rev.py         # Revenue calculations
│   │   │   └── stocks.py      # Stock market analytics
│   │   ├── FA/                # Foreign Affairs
│   │   │   ├── compare.py     # Alliance comparisons
│   │   │   ├── treaties.py    # Treaty management
│   │   │   └── universe.py    # Universe information
│   │   ├── IA/                # Intelligence Analytics
│   │   │   ├── alliance.py    # Alliance management
│   │   │   ├── audit.py       # Treaty visualization
│   │   │   ├── costs.py       # Economic cost calculations
│   │   │   ├── show.py        # Nation information
│   │   │   └── guide.py       # PnW guides and tutorials
│   │   ├── MA/                # Military Analytics
│   │   │   ├── destroy.py     # Smart targeting system
│   │   │   ├── finder.py      # Bounty and treasure hunting
│   │   │   ├── wars.py        # War analysis
│   │   │   ├── war_costs_bd.py     # War battle data
│   │   │   └── war_net_bd.py     # War battle net data
│   │   ├── Other/             # Additional PnW tools
│   │   │   └── baseball.py    # Baseball command
│   │   └── Util/              # Core PnW utilities
│   │       ├── calc.py        # Statistical calculations
│   │       ├── query.py       # GraphQL query engine
│   │       ├── rev_calc.py    # Revenue formulas
│   │       └── war_calc.py    # War cost calculations
│   └── info.py                # System information
├── web/                      # Web interface
│   ├── Pages/                # HTML pages for the dashboard
│   │   ├── Animations/       # CSS and JS for animations
│   │   └── Library/          # Markdown guides
│   ├── Wars/                 # HTML reports for PnW wars
│   ├── api/                  # Server-side API endpoints
│   ├── css/                  # Main CSS files
│   ├── js/                   # Main JavaScript files
│   └── static/               # Static assets
│       ├── Emojis/           # Image assets for emojis
│       ├── Images/           # General images
│       └── js/               # Static JavaScript libraries
├── .gitignore                  # Git ignore rules
├── LICENSE.txt                 # Project license
├── README.md                   # This file
├── mypy.ini                    # Type checking configuration
├── reaper.py                   # Main bot entry point
└── requirements.txt            # Python dependencies
```
