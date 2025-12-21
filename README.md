# ReaperBot

> **A comprehensive, modular Discord bot featuring advanced Pet systems, Politics & War tools, and interactive entertainment.**  
> 🚨 **For help, bug reports, or feature requests: [Join the Support Discord Server!](https://discord.gg/pDTKNQJXdh)**

---

## 📋 Table of Contents

- [🚀 Overview](#-overview)
- [✨ Major Features](#-major-features)
  - [🐾 Pets System](#-pets-system)
    - [Core Logic & Progression](#core-logic--progression)
    - [Combat & Games](#combat--games)
  - [🎯 Fun System](#-fun-system)
    - [Interactive Adventures](#interactive-adventures)
    - [Casual Games & Social](#casual-games--social)
    - [Horoscope](#horoscope)
  - [⚔️ PnW System](#️-pnw-system)
    - [Intelligence Agency (IA)](#intelligence-agency-ia)
    - [Military Affairs (MA)](#military-affairs-ma)
    - [Utilities & Guides](#utilities--guides)
- [📜 Command Reference](#-command-reference)
- [🏗️ Project Structure](#-project-structure)
- [🔧 Configuration & Setup](#-configuration--setup)

---

## 🚀 Overview

ReaperBot is a robust Discord bot built with Python and `discord.py`. It is designed to serve as a central hub for entertainment and utility, featuring a fully-featured virtual pet economy, a suite of interactive mini-games, and specialized tools for the *Politics and War* browser game.

### 🎯 Core Philosophy
- **Modular Architecture**: Systems are isolated in their own directories (`Pets`, `Fun`, `PnW`) for easy maintenance and scalability.
- **Data Persistence**: Unified `UserDataManager` handles all user state across different modules, ensuring seamless progression.
- **Rich Interactions**: Extensive use of Discord's UI components (Buttons, Select Menus, Modals) for a modern user experience.
- **Comprehensive Tooling**: Dedicated systems for gaming, server management, and specialized game analytics.

---

## ✨ Major Features

### 🐾 Pets System
**Directory:** `Systems/Pets/`

A deep virtual pet RPG where users can adopt, raise, and battle with digital companions. This system is split into two main components: Logic and Games.

#### Core Logic & Progression
**Location:** `Systems/Pets/Logic/`

This module handles the fundamental mechanics of the pet system, including data definitions and core behaviors.

*   **Core Stats**:
    *   **103 Unique Pets**: A massive roster of 103 collectable pets across 3 distinct categories (`Flying`, `Land`, `Swimming`).
    *   **Elemental System**: 13 distinct elements including `Fire`, `Water`, `Electric`, `Ice`, `Plant`, `Rock`, `Air`, `Magic`, `Holy`, `Necro`, `Psychic`, and `Fighting`.
    *   **Outcomes**: With 103 Pets, 3 distinct Types, and 67 Element combinations, there are **20,703 possible unique pet outcomes**!
*   **Actions**:
    *   **Movement Types**: Logic for Flying (`flying_actions.json`), Land (`land_actions.json`), and Swimming (`swimming_actions.json`) actions.
    *   **Exploration**: Diverse locations including Base areas and dangerous zones (`deadly_flying.json`, `deadly_land.json`, `deadly_swimming.json`).
*   **Combat Mechanics**:
    *   **Eliminations**: A complex elemental system defining how pets defeat opponents (e.g., `fire_eliminations.json`, `ice_eliminations.json`, `electric_eliminations.json`).
    *   **Attributes**: Definitions for Attacks, Defenses, and Success rates.
*   **Progression**:
    *   **Missions**: System for sending pets on tasks (`mission.json`) to earn rewards.
    *   **Equipment**: Item management system (`equipment.json`) to boost pet stats.
    *   **Champions**: Boss data and elite opponents (`champions.json`).
    *   **Pet Brain**: AI logic (`pet_brain.py`) governing pet behavior and responses.

#### Combat & Games
**Location:** `Systems/Pets/PetGames/`

This module contains the interactive gameplay elements where users actively engage with their pets.

*   **Battle Modes**:
    *   **PvE Battles**: Solo combat encounters (`battle_system.py`) against AI opponents.
    *   **PvP System**: Real-time player-vs-player combat (`pvp_system.py`) in a Free-For-All lobby.
    *   **Tournaments**: Organized competitive brackets (`tournament.py`) for server-wide events.
    *   **Survivor Series**: A high-stakes survival mode (`pet_ss.py`).
*   **Casino & Mini-Games**:
    *   **Slots**: A slot machine game (`slots.py`) to wager currency.
    *   **Card Games**: Texas Hold'em Poker (`holdem.py`) and Blackjack (`blackjack.py`).
    *   **Dice**: A fully featured Craps game (`craps.py`).
    *   **Racing**: Pet racing events (`races.py`) where speed and stats matter.

### 🎯 Fun System
**Directory:** `Systems/Fun/`

A collection of entertainment modules designed to keep server engagement high through storytelling and casual interaction.

#### Interactive Adventures
**Location:** `Systems/Fun/Walk Tru/` & `walktru.py`

A text-based RPG engine allowing users to play through themed storylines with branching choices.
*   **Genres**:
    *   **Horror**: Survive a terrifying scenario (`Horror.json`).
    *   **Western**: Gunslinging adventures (`Western.json`).
    *   **Sci-Fi/Robot**: Futuristic conflicts (`Robot.json`).
    *   **Fantasy**: Wizarding quests (`Wizard.json`) and Knightly tales (`Knight.json`).
    *   **Crime**: Rise through the ranks (`Ganster.json`).

#### Casual Games & Social
**Location:** `Systems/Fun/`

*   **Shooting Range**: A reaction-based mini-game (`fun_system.py`) testing aim and speed.
*   **Classic Games**:
    *   **Tic-Tac-Toe**: Play against the bot or friends.
    *   **Coin Flip**: Customizable coin toss with various visual styles.
*   **Social Interactions**:
    *   **Roast & Compliment**: Commands (`goodevil.py`) to playfully mock or praise users.

#### Horoscope
**Location:** `Systems/Fun/Zodiac/` & `signs.py`

A complete astrology system providing daily insights.
*   **Data Sources**: Includes Western (`astrology.json`), Chinese (`chinese_astrology.json`), and Primal (`primal_astrology.json`) zodiac data.
*   **Features**: Daily horoscopes and compatibility checks.

### ⚔️ PnW System
**Directory:** `Systems/PnW/`

A specialized suite of tools for the *Politics and War* browser game, optimized for alliance management and warfare analysis.

#### Intelligence Agency (IA)
**Location:** `Systems/PnW/IA/`

Tools for gathering and analyzing data on nations and alliances.
*   **Alliance Audits**: Comprehensive reports (`audit.py`) on alliance statistics and readiness.
*   **Nation Intelligence**: Detailed lookups (`show.py`) for specific nations.
*   **Comparison Tools**: Compare stats between alliances (`compare.py`).
*   **Revenue Analysis**: Calculate income and financial health (`rev.py`).
*   **Sniping**: Tools for identifying vulnerable targets (`snipe.py`).

#### Military Affairs (MA)
**Location:** `Systems/PnW/MA/`

Tools focused on combat optimization and war planning.
*   **Target Finding**: Algorithms to find the best targets (`destroy.py`) based on military score and composition.
*   **Cost Analysis**: Calculators for estimating the cost of war (`war_cost.py`).

#### Utilities & Guides
**Location:** `Systems/PnW/Util/`

*   **Calculators**: General purpose calculation tools (`calc.py`, `rev_calc.py`).
*   **Database Queries**: Helpers for interacting with the PnW API/Database (`query.py`).

---

## 📜 Command Reference

### 🐾 Pets Commands (16)
| Category | Command | Description |
|----------|---------|-------------|
| **Management** | `/pet_shop` | Visit Pet Shop to adopt a new pet |
| | `/pet` | View your current pet's status and stats |
| | `/rename_pet` | Give your pet a custom name |
| | `/kill` | Delete your current pet (Permanent!) |
| | `/equip` | Equip items to your pet |
| **Progression** | `/train` | Train your pet to gain XP |
| | `/mission` | Send your pet on a mission for rewards |
| **Battle & PvP** | `/battle` | Fight a solo PvE battle |
| | `/pvp` | Enter the PvP Free-For-All lobby |
| | `/tournament` | Create or join a pet tournament |
| | `/survivor_series` | Start a Pet Survivor Series event |
| **Mini-Games** | `/slots` | Play Pet Slots |
| | `/race` | Race your pet against others |
| | `/craps` | Play a game of Craps |
| | `/holdem` | Play Texas Hold'em Poker |
| | `/blackjack` | Play Blackjack |

### 🎯 Fun Commands (8)
| Category | Command | Description |
|----------|---------|-------------|
| **Identity** | `/range` | Start sniper training mini-game |
| | `/rangestats` | View your shooting range statistics |
| **Interactive** | `/walktru` | Start an interactive text adventure |
| | `/coin` | Flip a coin with custom styles |
| | `/tictactoe` | Play a game of Tic Tac Toe |
| | `/roast` | Get roasted by the bot |
| | `/compliment` | Receive a tailored compliment |
| **Horoscope** | `/astrology` | Show your zodiac sign info |

### ⚔️ PnW Commands (15)
| Category | Command | Description |
|----------|---------|-------------|
| **Guides** | `/snipe_guide` | Guide on beige sniping/raiding |
| | `/snipe_setup` | Setup guide for beige sniping |
| | `/snipe_execute` | Execution guide for beige sniping |
| | `/war_guide` | Mechanics of Ground and Air Supremacy |
| | `/trade_values` | Show average resource prices |
| **Intelligence** | `/alliance` | Display alliance overview |
| | `/show` | Show a nation by name, leader, ID, or link |
| | `/audit` | Audit alliance issues |
| | `/treaties` | Show treaties and treaty web |
| | `/revenue` | Calculate revenue for a nation/alliance |
| | `/revenuehelp` | Show revenue command usage |
| | `/costs` | Calculate city development costs |
| | `/compare` | Compare two alliances |
| **Warfare** | `/destroy` | Find optimal attackers for a target |
| | `/wars` | Calculate war costs between parties |

---

## 🏗️ Project Structure

```
Allspark/
├── Systems/
│   ├── Pets/               # Pet system root
│   │   ├── Logic/          # Core mechanics, items, and AI
│   │   ├── PetGames/       # Interactive games and combat engines
│   │   └── pets_system.py  # Main Pets Cog
│   ├── Fun/                # Entertainment root
│   │   ├── Walk Tru/       # Adventure story data
│   │   ├── Zodiac/         # Horoscope data
│   │   ├── fun_system.py   # General games logic
│   │   ├── signs.py        # Astrology logic
│   │   └── walktru.py      # Adventure engine
│   ├── PnW/                # Politics and War root
│   │   ├── IA/             # Intelligence Agency tools
│   │   ├── MA/             # Military Affairs tools
│   │   └── Util/           # Shared utilities
│   └── Functions/          # Shared bot utilities
│       ├── user_data_manager.py
│       └── admin_system.py
├── config.py               # Bot configuration
├── reaper.py               # Main entry point
└── README.md               # This file
```

---

## 🔧 Configuration & Setup

### Prerequisites
*   Python 3.10 or higher
*   `discord.py` library
*   `aiohttp` library

### Installation
1.  **Clone the repository**:
    ```bash
    git clone https://github.com/yourusername/ReaperBot.git
    cd ReaperBot
    ```

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure the bot**:
    *   Open `config.py`.
    *   Insert your Discord Bot Token.
    *   Configure any necessary API keys.

4.  **Run the bot**:
    ```bash
    python reaper.py
    ```

### Environment Variables
Ensure the following are set in your environment or `config.py`:
*   `DISCORD_TOKEN`: Your Discord bot token.
*   `PNW_API_KEY`: (Optional) For PnW commands.

---

> *Bot Credit - The Infamous Aries*
