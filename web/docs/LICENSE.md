# License

## MIT License

Copyright (c) 2024–2026 Cody Ray Threewit

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

**THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.**

---

## Software Components

This repository contains three integrated software systems, all covered by the MIT license above.

### 1. Reaper Bot (Discord Bot)

A self-hosted Discord bot built in Python (`discord.py`) providing:

- Pets RPG system with stats, combat, PvP, tournaments, dungeon crawls, casino games, and a Survivor Series battle royale
- Politics & War integration: revenue calculators, war intelligence dashboards, raid finders, beige alerts, resource price alerts, treaty maps, alliance comparisons, and a global news/leaderboard system
- Support ticket system with membership and embassy workflows
- Automatic message translation (Google Translate)
- Astrology system with tarot readings and triple-zodiac profiles (Western, Chinese, Primal)
- Entertainment commands: roasts, compliments, RPS, Tic Tac Toe, sniper training, text adventures, and AI-driven zombie survival

### 2. PnWHarvester (Data Collection Service)

A standalone asyncio service that:

- Subscribes to PnW API v3 WebSocket events for real-time data collection
- Stores data locally in SQLite databases (GlobalNations, IRSWars, GlobalWars, bankrecs, holdings, treaties, news)
- Generates narrative news events for wars, trades, bank transfers, city purchases, project purchases, and military changes
- Processes turn revenue every 2 hours and manages beige alert state
- Uses a GPP (Good Parallel Programming) architecture with unified locking (LockManager), connection pooling (DatabasePool), write buffering (WriteQueue), and in-memory nation caching (NationCache)

### 3. Web Interface

A FastAPI/Uvicorn web application embedded within the Discord bot process:

- Browser-based pet system (adoption, training, arena, colosseum, dungeon, Survivor Series, casino games, stock market, tasks, leaderboards)
- PnW analytics tools (Watch page war dashboard, nations search, revenue calculator, revenue optimizer, cost calculator, raid finder, weapons calculator, treaty universe globe, full-mill rankings, alliance comparison, news feed, personal nation dashboard)
- Discord OAuth2 authentication for personal data access
- Real-time WebSocket updates for arena battles and casino games
- Server-Sent Events for Survivor Series live feed
- Cloudflare Tunnel support for public access

---

## Third-Party Licenses

This software uses the following third-party libraries. Each is governed by its own license.

### Python Dependencies

| Package | License |
|:---|:---|
| discord.py | MIT |
| FastAPI | MIT |
| uvicorn | BSD-3-Clause |
| Starlette | BSD-3-Clause |
| Pydantic | MIT |
| aiohttp | Apache-2.0 |
| httpx | BSD-3-Clause |
| requests | Apache-2.0 |
| aiosqlite | MIT |
| python-dotenv | BSD-3-Clause |
| itsdangerous | BSD-3-Clause |
| python-multipart | Apache-2.0 |
| Werkzeug | BSD-3-Clause |
| Jinja2 | BSD-3-Clause |
| MarkupSafe | BSD-3-Clause |
| click | BSD-3-Clause |
| blinker | MIT |
| Flask | BSD-3-Clause |
| groq | MIT |
| pandas | BSD-3-Clause |
| numpy | BSD-3-Clause |
| matplotlib | PSF |
| plotly | MIT |
| kaleido | MIT |
| Pillow | HPND (PIL fork) |
| lttb | MIT |
| networkx | BSD-3-Clause |
| beautifulsoup4 | MIT |
| markdown | BSD-3-Clause |
| reportlab | BSD-3-Clause |
| aiofiles | Apache-2.0 |
| psutil | BSD-3-Clause |
| pnwkit-py | MIT |
| pywin32 | PSF (Windows only) |
| pytest | MIT |
| pytest-asyncio | Apache-2.0 |
| tqdm | MIT / MPL-2.0 |
| typing-extensions | PSF |

### Node.js Dependencies

| Package | License |
|:---|:---|
| bootstrap | MIT |
| three (Three.js) | MIT |
| three-globe | MIT |
| gsap | [GreenSock Standard License](https://gsap.com/standard-license) |
| @3d-dice/dice-box | MIT |

---

## External Services

This software integrates with the following external services. Each is governed by its own terms of service, separate from this license.

| Service | Purpose | Terms |
|:---|:---|:---|
| Discord | Bot API and OAuth2 authentication | discord.com/terms |
| Politics & War | Game data GraphQL API | politicsandwar.com |
| Groq | LLM API (Llama 3.1) | groq.com/legal |
| Google Translate | Automatic message translation | policies.google.com/terms |
| Cloudflare | Tunnel and CDN | cloudflare.com/terms |
| Giphy | GIF content | giphy.com/terms |
| Pixabay | Image content | pixabay.com/service/terms/ |

---

## Data and Privacy

All data processed by this software is stored **locally** on the operator's machine in SQLite database files. No data is transmitted to any party beyond the explicit API integrations listed above.

**Discord bot data** — Discord user IDs, usernames, and server membership are used solely for command permissions and pet system profiles. Stored in `Databases/Pets/pets.db`.

**PnWHarvester data** — Public Politics & War game data (nation stats, war records, alliance information, resource prices). This data is publicly available via the PnW API and is stored locally for analytics. No private game data is collected.

**Web interface data** — Discord OAuth2 session tokens are stored server-side and expire on logout. User settings (theme, linked nation) are stored in `Databases/reaper.db`. No passwords are ever stored. Authentication is fully delegated to Discord.

**Casino / games** — All virtual currency (Pet XP) has no real-world value. No real money is involved in any feature of this software.

---

## Disclaimer

The Politics & War integration uses publicly available data from the PnW game API. The authors are not affiliated with Politics & War and are not responsible for changes to the PnW API or game mechanics that may affect this software.

The casino and gambling-themed features use virtual in-game currency (Pet XP) exclusively. No real money is wagered, won, or lost under any circumstances.

---

## Contact

- **Discord:** the_infamous_aries
- **GitHub:** [https://github.com/The-Infamous-Aries/Reaper](https://github.com/The-Infamous-Aries/Reaper)
- **Email:** cody.ray.inc@gmail.com
