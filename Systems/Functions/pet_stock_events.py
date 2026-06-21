"""
Pet Stock Market Events — Tiered System
========================================
MAJOR EVENTS  (tier="major")
  - Holidays: fire every tick on their calendar date (month, day).
  - Themed Major: fire once at the start of a random non-holiday day and
    persist all 24 hours of that day.
  Both types stack with a Minor event each tick for compounding drama.

MINOR EVENTS  (tier="minor")
  - Fire each tick regardless.
  - On a Major day they stack ON TOP of the Major, amplifying the move.

Each element and each type appears in roughly equal numbers of dedicated events.
"""
from typing import Any, Dict, List

ELEMENTS = [
    "basic", "fire", "water", "electric", "ice",
    "plant", "rock", "air", "magic", "holy", "necro", "psychic", "fighting",
]

# ── MAJOR EVENTS ──────────────────────────────────────────────────────────────
# holiday=(month,day) → fires every hour on that calendar date.
# No holiday key       → eligible to be randomly chosen as the day's Major event.
# Multipliers are intentionally large — they stack with a Minor each hour.

MAJOR_EVENTS: List[Dict[str, Any]] = [

    # ── Holidays ─────────────────────────────────────────────────────────────
    {"name": "New Year's Day",
     "desc": "🎆 The new year dawns — all tokens surge with fresh optimism.",
     "type": "global", "mult": 1.25, "holiday": (1, 1)},

    {"name": "Valentine's Day",
     "desc": "💝 Love fills the air — Holy and Magic tokens soar all day.",
     "type": "elements", "targets": ["holy", "magic"], "mult": 1.40, "holiday": (2, 14)},

    {"name": "St. Patrick's Day",
     "desc": "🍀 Luck of the Irish — Plant tokens bloom all day.",
     "type": "elements", "targets": ["plant"], "mult": 1.45, "holiday": (3, 17)},

    {"name": "April Fools' Day",
     "desc": "🃏 Nothing is as it seems — total chaos reigns all day.",
     "type": "chaos", "holiday": (4, 1)},

    {"name": "Earth Day",
     "desc": "🌍 Earth Day — Plant, Water, and Air tokens thrive all day.",
     "type": "elements", "targets": ["plant", "water", "air"], "mult": 1.38, "holiday": (4, 22)},

    {"name": "May Day",
     "desc": "🌸 Spring festival — Flying and Land tokens celebrate all day.",
     "type": "types", "targets": ["flying", "land"], "mult": 1.30, "holiday": (5, 1)},

    {"name": "Summer Solstice",
     "desc": "☀️ Longest day of the year — Fire and Air tokens blaze all day.",
     "type": "elements", "targets": ["fire", "air"], "mult": 1.42, "holiday": (6, 21)},

    {"name": "Independence Day",
     "desc": "🎇 Fireworks light the sky — Fire and Electric tokens explode all day.",
     "type": "elements", "targets": ["fire", "electric"], "mult": 1.45, "holiday": (7, 4)},

    {"name": "Midsummer Storm",
     "desc": "⛈️ A massive summer storm — Water and Electric tokens surge all day.",
     "type": "elements", "targets": ["water", "electric"], "mult": 1.38, "holiday": (8, 15)},

    {"name": "Harvest Moon",
     "desc": "🌕 The harvest moon rises — Plant and Rock tokens glow all day.",
     "type": "elements", "targets": ["plant", "rock"], "mult": 1.38, "holiday": (9, 22)},

    {"name": "Halloween",
     "desc": "🎃 The veil thins — Necro and Magic tokens haunt the market all day.",
     "type": "elements", "targets": ["necro", "magic"], "mult": 1.50, "holiday": (10, 31)},

    {"name": "Day of the Dead",
     "desc": "💀 Spirits walk — Necro and Psychic tokens surge all day.",
     "type": "elements", "targets": ["necro", "psychic"], "mult": 1.45, "holiday": (11, 2)},

    {"name": "Winter Solstice",
     "desc": "❄️ The longest night — Ice and Necro tokens chill the market all day.",
     "type": "elements", "targets": ["ice", "necro"], "mult": 1.42, "holiday": (12, 21)},

    {"name": "Christmas Eve",
     "desc": "🎄 Holiday magic — Holy tokens shine bright all day.",
     "type": "elements", "targets": ["holy"], "mult": 1.55, "holiday": (12, 24)},

    {"name": "Christmas Day",
     "desc": "🎁 Gifts for all — Holy and Magic tokens celebrate all day.",
     "type": "elements", "targets": ["holy", "magic"], "mult": 1.50, "holiday": (12, 25)},

    {"name": "New Year's Eve",
     "desc": "🥂 Countdown to midnight — all tokens surge with anticipation all day.",
     "type": "global", "mult": 1.30, "holiday": (12, 31)},

    # ── Themed Major Events (random non-holiday days) ─────────────────────────
    # Fire
    {"name": "Volcanic Eruption Day",
     "desc": "🌋 A massive eruption — Fire tokens explode all day.",
     "type": "elements", "targets": ["fire"], "mult": 1.55, "weight": 2},
    {"name": "Great Wildfire",
     "desc": "🔥 An unstoppable wildfire — Fire tokens rage all day.",
     "type": "elements", "targets": ["fire"], "mult": 1.50, "weight": 2},
    {"name": "Forge Day",
     "desc": "⚒️ The great forges ignite — Fire tokens heat up all day.",
     "type": "elements", "targets": ["fire"], "mult": 1.40, "weight": 2},
    {"name": "Ash Wednesday",
     "desc": "🌑 Ash blankets the land — Fire tokens cool all day.",
     "type": "elements", "targets": ["fire"], "mult": 0.60, "weight": 2},

    # Water
    {"name": "Great Flood Day",
     "desc": "🌊 Floodwaters rise — Water tokens surge all day.",
     "type": "elements", "targets": ["water"], "mult": 1.55, "weight": 2},
    {"name": "Monsoon Day",
     "desc": "🌧️ The monsoon arrives — Water tokens swell all day.",
     "type": "elements", "targets": ["water"], "mult": 1.45, "weight": 2},
    {"name": "Ocean Festival",
     "desc": "🐚 The ocean is celebrated — Water tokens rise all day.",
     "type": "elements", "targets": ["water"], "mult": 1.38, "weight": 2},
    {"name": "Great Drought Day",
     "desc": "🏜️ Extreme drought — Water tokens evaporate all day.",
     "type": "elements", "targets": ["water"], "mult": 0.58, "weight": 2},

    # Electric
    {"name": "Grand Thunderstorm Day",
     "desc": "⚡ A historic storm — Electric tokens surge all day.",
     "type": "elements", "targets": ["electric"], "mult": 1.55, "weight": 2},
    {"name": "Power Grid Day",
     "desc": "🔌 The grid overloads — Electric tokens spike all day.",
     "type": "elements", "targets": ["electric"], "mult": 1.45, "weight": 2},
    {"name": "Lightning Festival",
     "desc": "⚡ A festival of lightning — Electric tokens crackle all day.",
     "type": "elements", "targets": ["electric"], "mult": 1.38, "weight": 2},
    {"name": "Blackout Day",
     "desc": "🌑 Total blackout — Electric tokens go dark all day.",
     "type": "elements", "targets": ["electric"], "mult": 0.58, "weight": 2},

    # Ice
    {"name": "Blizzard Day",
     "desc": "🌨️ A historic blizzard — Ice tokens freeze the competition all day.",
     "type": "elements", "targets": ["ice"], "mult": 1.55, "weight": 2},
    {"name": "Glacier Day",
     "desc": "🧊 Glaciers advance — Ice tokens surge all day.",
     "type": "elements", "targets": ["ice"], "mult": 1.45, "weight": 2},
    {"name": "Frost Festival",
     "desc": "❄️ Frost covers everything — Ice tokens glitter all day.",
     "type": "elements", "targets": ["ice"], "mult": 1.38, "weight": 2},
    {"name": "Great Thaw",
     "desc": "🌡️ A heatwave melts everything — Ice tokens collapse all day.",
     "type": "elements", "targets": ["ice"], "mult": 0.58, "weight": 2},

    # Plant
    {"name": "Great Bloom Day",
     "desc": "🌸 Everything blooms at once — Plant tokens flourish all day.",
     "type": "elements", "targets": ["plant"], "mult": 1.55, "weight": 2},
    {"name": "Ancient Forest Day",
     "desc": "🌳 The ancient forest awakens — Plant tokens surge all day.",
     "type": "elements", "targets": ["plant"], "mult": 1.45, "weight": 2},
    {"name": "Harvest Day",
     "desc": "🌾 A bountiful harvest — Plant tokens rise all day.",
     "type": "elements", "targets": ["plant"], "mult": 1.38, "weight": 2},
    {"name": "Blight Day",
     "desc": "🍂 A terrible blight — Plant tokens wither all day.",
     "type": "elements", "targets": ["plant"], "mult": 0.58, "weight": 2},

    # Rock
    {"name": "Great Earthquake Day",
     "desc": "🌍 A massive earthquake — Rock tokens shake loose all day.",
     "type": "elements", "targets": ["rock"], "mult": 1.55, "weight": 2},
    {"name": "Gem Rush Day",
     "desc": "💎 Rare gems discovered — Rock tokens spike all day.",
     "type": "elements", "targets": ["rock"], "mult": 1.50, "weight": 2},
    {"name": "Mountain Festival",
     "desc": "⛰️ Climbers summit the peaks — Rock tokens rise all day.",
     "type": "elements", "targets": ["rock"], "mult": 1.38, "weight": 2},
    {"name": "Erosion Day",
     "desc": "🌊 Erosion wears everything down — Rock tokens crumble all day.",
     "type": "elements", "targets": ["rock"], "mult": 0.60, "weight": 2},

    # Air
    {"name": "Tornado Day",
     "desc": "🌪️ Tornadoes tear through — Air tokens spin up all day.",
     "type": "elements", "targets": ["air"], "mult": 1.55, "weight": 2},
    {"name": "Gale Day",
     "desc": "💨 Gale force winds — Air tokens howl all day.",
     "type": "elements", "targets": ["air"], "mult": 1.50, "weight": 2},
    {"name": "Clear Sky Day",
     "desc": "🌤️ Perfect clear skies — Air tokens breathe easy all day.",
     "type": "elements", "targets": ["air"], "mult": 1.38, "weight": 2},
    {"name": "Dead Calm Day",
     "desc": "😶 No wind at all — Air tokens stagnate all day.",
     "type": "elements", "targets": ["air"], "mult": 0.60, "weight": 2},

    # Magic
    {"name": "Grand Magic Surge Day",
     "desc": "✨ Wild magic floods the world — Magic tokens spike all day.",
     "type": "elements", "targets": ["magic"], "mult": 1.55, "weight": 2},
    {"name": "Arcane Festival Day",
     "desc": "🔮 The grand arcane festival — Magic tokens soar all day.",
     "type": "elements", "targets": ["magic"], "mult": 1.50, "weight": 2},
    {"name": "Spell Cascade Day",
     "desc": "💫 Uncontrolled spells cascade — Magic tokens surge all day.",
     "type": "elements", "targets": ["magic"], "mult": 1.40, "weight": 2},
    {"name": "Magic Suppression Day",
     "desc": "🚫 Anti-magic fields deployed — Magic tokens collapse all day.",
     "type": "elements", "targets": ["magic"], "mult": 0.58, "weight": 2},

    # Holy
    {"name": "Divine Blessing Day",
     "desc": "☀️ Divine light descends — Holy tokens radiate all day.",
     "type": "elements", "targets": ["holy"], "mult": 1.55, "weight": 2},
    {"name": "Sacred Pilgrimage Day",
     "desc": "🕊️ A mass pilgrimage — Holy tokens are revered all day.",
     "type": "elements", "targets": ["holy"], "mult": 1.50, "weight": 2},
    {"name": "Temple Day",
     "desc": "⛪ New temples consecrated — Holy tokens are blessed all day.",
     "type": "elements", "targets": ["holy"], "mult": 1.38, "weight": 2},
    {"name": "Heresy Day",
     "desc": "😈 Heresy spreads — Holy tokens lose faith all day.",
     "type": "elements", "targets": ["holy"], "mult": 0.58, "weight": 2},

    # Necro
    {"name": "Mass Undead Rising Day",
     "desc": "💀 The dead walk en masse — Necro tokens surge all day.",
     "type": "elements", "targets": ["necro"], "mult": 1.55, "weight": 2},
    {"name": "Soul Harvest Day",
     "desc": "👻 Souls collected en masse — Necro tokens spike all day.",
     "type": "elements", "targets": ["necro"], "mult": 1.50, "weight": 2},
    {"name": "Graveyard Festival",
     "desc": "🪦 A festival of the dead — Necro tokens rise all day.",
     "type": "elements", "targets": ["necro"], "mult": 1.38, "weight": 2},
    {"name": "Grand Exorcism Day",
     "desc": "✝️ Mass exorcism — Necro tokens are banished all day.",
     "type": "elements", "targets": ["necro"], "mult": 0.58, "weight": 2},

    # Psychic
    {"name": "Grand Psychic Awakening",
     "desc": "🔮 A mass psychic event — Psychic tokens spike all day.",
     "type": "elements", "targets": ["psychic"], "mult": 1.55, "weight": 2},
    {"name": "Mind Meld Day",
     "desc": "🧠 Collective consciousness — Psychic tokens surge all day.",
     "type": "elements", "targets": ["psychic"], "mult": 1.50, "weight": 2},
    {"name": "Telepathy Day",
     "desc": "📡 Telepathy breakthrough — Psychic tokens climb all day.",
     "type": "elements", "targets": ["psychic"], "mult": 1.38, "weight": 2},
    {"name": "Mental Block Day",
     "desc": "🧱 Psychic interference — Psychic tokens go blank all day.",
     "type": "elements", "targets": ["psychic"], "mult": 0.58, "weight": 2},

    # Fighting
    {"name": "Grand Championship Day",
     "desc": "🥊 The grand fighting championship — Fighting tokens surge all day.",
     "type": "elements", "targets": ["fighting"], "mult": 1.55, "weight": 2},
    {"name": "Street Brawl Day",
     "desc": "👊 Brawls everywhere — Fighting tokens rise all day.",
     "type": "elements", "targets": ["fighting"], "mult": 1.45, "weight": 2},
    {"name": "Martial Arts Day",
     "desc": "🥋 Grand martial arts expo — Fighting tokens climb all day.",
     "type": "elements", "targets": ["fighting"], "mult": 1.38, "weight": 2},
    {"name": "Peace Treaty Day",
     "desc": "🕊️ All fighting ceases — Fighting tokens drop all day.",
     "type": "elements", "targets": ["fighting"], "mult": 0.58, "weight": 2},

    # Basic
    {"name": "Primal Awakening Day",
     "desc": "💠 Primal energy stirs — Basic tokens spike all day.",
     "type": "elements", "targets": ["basic"], "mult": 1.55, "weight": 2},
    {"name": "Back to Basics Day",
     "desc": "⚪ Traders return to fundamentals — Basic tokens surge all day.",
     "type": "elements", "targets": ["basic"], "mult": 1.45, "weight": 2},
    {"name": "Core Stability Day",
     "desc": "🔵 Market anchors to basics — Basic tokens climb all day.",
     "type": "elements", "targets": ["basic"], "mult": 1.38, "weight": 2},
    {"name": "Oversaturation Day",
     "desc": "📉 Too many basics — Basic tokens flood the market all day.",
     "type": "elements", "targets": ["basic"], "mult": 0.60, "weight": 2},

    # Land
    {"name": "Grand Land Derby Day",
     "desc": "🐾 The grand land derby — Land tokens surge all day.",
     "type": "types", "targets": ["land"], "mult": 1.45, "weight": 2},
    {"name": "Great Stampede Day",
     "desc": "🦬 A massive stampede — Land tokens thunder all day.",
     "type": "types", "targets": ["land"], "mult": 1.40, "weight": 2},
    {"name": "Burrowing Festival",
     "desc": "🕳️ Land pets dig deep — Land tokens climb all day.",
     "type": "types", "targets": ["land"], "mult": 1.35, "weight": 2},
    {"name": "Great Landslide Day",
     "desc": "⛰️ Unstable ground — Land tokens tumble all day.",
     "type": "types", "targets": ["land"], "mult": 0.65, "weight": 2},

    # Swimming
    {"name": "Grand Deep Sea Race Day",
     "desc": "🐟 The grand deep sea race — Swimming tokens surge all day.",
     "type": "types", "targets": ["swimming"], "mult": 1.45, "weight": 2},
    {"name": "Tidal Wave Day",
     "desc": "🌊 A massive tidal wave — Swimming tokens crest all day.",
     "type": "types", "targets": ["swimming"], "mult": 1.40, "weight": 2},
    {"name": "Coral Festival Day",
     "desc": "🪸 Grand underwater festival — Swimming tokens bloom all day.",
     "type": "types", "targets": ["swimming"], "mult": 1.35, "weight": 2},
    {"name": "Great Pollution Day",
     "desc": "🚯 Severe pollution — Swimming tokens sink all day.",
     "type": "types", "targets": ["swimming"], "mult": 0.65, "weight": 2},

    # Flying
    {"name": "Grand Sky Tournament Day",
     "desc": "🦅 The grand sky tournament — Flying tokens soar all day.",
     "type": "types", "targets": ["flying"], "mult": 1.45, "weight": 2},
    {"name": "Perfect Thermal Day",
     "desc": "🌤️ Perfect thermals all day — Flying tokens ride high.",
     "type": "types", "targets": ["flying"], "mult": 1.40, "weight": 2},
    {"name": "Aerial Acrobatics Day",
     "desc": "🎪 Spectacular air show — Flying tokens climb all day.",
     "type": "types", "targets": ["flying"], "mult": 1.35, "weight": 2},
    {"name": "Great Storm Grounding",
     "desc": "⛈️ Severe storm grounds all flyers — Flying tokens drop all day.",
     "type": "types", "targets": ["flying"], "mult": 0.65, "weight": 2},

    # Global Major
    {"name": "Grand Market Frenzy Day",
     "desc": "📈 Traders go absolutely wild — all tokens surge all day.",
     "type": "global", "mult": 1.30, "weight": 1},
    {"name": "Grand Market Crash Day",
     "desc": "📉 A historic crash — all tokens plummet all day.",
     "type": "global", "mult": 0.70, "weight": 1},
    {"name": "Grand Bull Run Day",
     "desc": "🐂 A historic bull run — everything climbs all day.",
     "type": "global", "mult": 1.25, "weight": 1},
    {"name": "Grand Bear Day",
     "desc": "🐻 Bears dominate — everything slides all day.",
     "type": "global", "mult": 0.75, "weight": 1},

    # Cross-element Major Rivalries
    {"name": "Holy War Day",
     "desc": "✨ Holy vs Necro — a day-long war shakes both tokens.",
     "type": "rivalry", "targets": ["holy", "necro"], "mult": 1.55, "weight": 2},
    {"name": "Fire vs Water Day",
     "desc": "🔥💧 Fire and Water clash all day — one wins, one loses.",
     "type": "rivalry", "targets": ["fire", "water"], "mult": 1.55, "weight": 2},
    {"name": "Electric vs Rock Day",
     "desc": "⚡🪨 Electric and Rock battle all day — one surges, one crumbles.",
     "type": "rivalry", "targets": ["electric", "rock"], "mult": 1.55, "weight": 2},
    {"name": "Ice vs Fighting Day",
     "desc": "❄️🥊 Ice and Fighting collide all day — one freezes, one breaks through.",
     "type": "rivalry", "targets": ["ice", "fighting"], "mult": 1.55, "weight": 2},
    {"name": "Magic vs Psychic Day",
     "desc": "✨🔮 Magic and Psychic duel all day — one dominates.",
     "type": "rivalry", "targets": ["magic", "psychic"], "mult": 1.55, "weight": 2},
    {"name": "Plant vs Air Day",
     "desc": "🌿💨 Plant and Air wrestle all day — one blooms, one scatters.",
     "type": "rivalry", "targets": ["plant", "air"], "mult": 1.55, "weight": 2},
    {"name": "Type Rivalry Day",
     "desc": "⚔️ Two pet types clash all day — one rises, one falls.",
     "type": "type_rivalry", "mult": 1.40, "weight": 3},
]


# ── MINOR EVENTS ──────────────────────────────────────────────────────────────
# Fire every hour regardless of major events.
# On a Major day they stack ON TOP of the Major, amplifying the move.
# No holiday keys — purely random hourly selection.

MINOR_EVENTS: List[Dict[str, Any]] = [

    # Global minor
    {"name": "Market Buzz",        "desc": "📊 Traders are buzzing — all tokens tick up slightly.",       "type": "global", "mult": 1.05, "weight": 3},
    {"name": "Market Lull",        "desc": "😴 A quiet hour — all tokens drift down slightly.",           "type": "global", "mult": 0.96, "weight": 3},
    {"name": "Speculator Rush",    "desc": "💹 Speculators pile in — all tokens nudge higher.",           "type": "global", "mult": 1.06, "weight": 2},
    {"name": "Profit Taking",      "desc": "💰 Traders cash out — all tokens ease back.",                 "type": "global", "mult": 0.95, "weight": 2},
    {"name": "Rumour Mill",        "desc": "🗣️ Rumours swirl — all tokens wobble unpredictably.",         "type": "chaos",  "weight": 2},

    # Fire minor
    {"name": "Ember Flare",        "desc": "🔥 A small flare — Fire tokens heat up briefly.",            "type": "elements", "targets": ["fire"],     "mult": 1.08, "weight": 2},
    {"name": "Smoke Signal",       "desc": "💨 Smoke drifts — Fire tokens cool a touch.",                "type": "elements", "targets": ["fire"],     "mult": 0.93, "weight": 2},

    # Water minor
    {"name": "Rain Shower",        "desc": "🌦️ A light shower — Water tokens rise a bit.",               "type": "elements", "targets": ["water"],    "mult": 1.08, "weight": 2},
    {"name": "Dry Spell",          "desc": "☀️ A dry hour — Water tokens dip slightly.",                 "type": "elements", "targets": ["water"],    "mult": 0.93, "weight": 2},

    # Electric minor
    {"name": "Static Surge",       "desc": "⚡ Static in the air — Electric tokens spark up.",           "type": "elements", "targets": ["electric"], "mult": 1.08, "weight": 2},
    {"name": "Power Dip",          "desc": "🔋 A brief power dip — Electric tokens flicker.",            "type": "elements", "targets": ["electric"], "mult": 0.93, "weight": 2},

    # Ice minor
    {"name": "Cold Snap",          "desc": "🌬️ A cold snap — Ice tokens chill upward.",                  "type": "elements", "targets": ["ice"],      "mult": 1.08, "weight": 2},
    {"name": "Mild Thaw",          "desc": "🌡️ A mild thaw — Ice tokens melt slightly.",                 "type": "elements", "targets": ["ice"],      "mult": 0.93, "weight": 2},

    # Plant minor
    {"name": "Pollen Burst",       "desc": "🌼 Pollen fills the air — Plant tokens bloom a bit.",        "type": "elements", "targets": ["plant"],    "mult": 1.08, "weight": 2},
    {"name": "Wilting Hour",       "desc": "🍂 Plants wilt in the heat — Plant tokens droop.",           "type": "elements", "targets": ["plant"],    "mult": 0.93, "weight": 2},

    # Rock minor
    {"name": "Tremor",             "desc": "🪨 A small tremor — Rock tokens shake loose.",               "type": "elements", "targets": ["rock"],     "mult": 1.08, "weight": 2},
    {"name": "Settling",           "desc": "😌 Ground settles — Rock tokens ease back.",                 "type": "elements", "targets": ["rock"],     "mult": 0.93, "weight": 2},

    # Air minor
    {"name": "Gust",               "desc": "💨 A sudden gust — Air tokens lift briefly.",                "type": "elements", "targets": ["air"],      "mult": 1.08, "weight": 2},
    {"name": "Dead Air",           "desc": "😶 Still air — Air tokens stall.",                           "type": "elements", "targets": ["air"],      "mult": 0.93, "weight": 2},

    # Magic minor
    {"name": "Arcane Ripple",      "desc": "✨ A ripple of magic — Magic tokens shimmer up.",            "type": "elements", "targets": ["magic"],    "mult": 1.08, "weight": 2},
    {"name": "Spell Fizzle",       "desc": "💫 A spell fizzles — Magic tokens dim slightly.",            "type": "elements", "targets": ["magic"],    "mult": 0.93, "weight": 2},

    # Holy minor
    {"name": "Blessing",           "desc": "🕊️ A small blessing — Holy tokens glow briefly.",            "type": "elements", "targets": ["holy"],     "mult": 1.08, "weight": 2},
    {"name": "Shadow Creep",       "desc": "🌑 Shadows creep in — Holy tokens dim.",                    "type": "elements", "targets": ["holy"],     "mult": 0.93, "weight": 2},

    # Necro minor
    {"name": "Restless Spirits",   "desc": "👻 Spirits stir — Necro tokens rise.",                      "type": "elements", "targets": ["necro"],    "mult": 1.08, "weight": 2},
    {"name": "Banishment",         "desc": "✝️ A spirit is banished — Necro tokens dip.",               "type": "elements", "targets": ["necro"],    "mult": 0.93, "weight": 2},

    # Psychic minor
    {"name": "Mental Clarity",     "desc": "🧠 A moment of clarity — Psychic tokens sharpen.",          "type": "elements", "targets": ["psychic"],  "mult": 1.08, "weight": 2},
    {"name": "Brain Fog",          "desc": "🌫️ Brain fog rolls in — Psychic tokens cloud over.",         "type": "elements", "targets": ["psychic"],  "mult": 0.93, "weight": 2},

    # Fighting minor
    {"name": "Sparring Session",   "desc": "🥊 A quick sparring match — Fighting tokens tick up.",       "type": "elements", "targets": ["fighting"], "mult": 1.08, "weight": 2},
    {"name": "Rest Period",        "desc": "😴 Fighters rest — Fighting tokens ease back.",              "type": "elements", "targets": ["fighting"], "mult": 0.93, "weight": 2},

    # Basic minor
    {"name": "Steady Demand",      "desc": "⚪ Steady demand — Basic tokens inch up.",                   "type": "elements", "targets": ["basic"],    "mult": 1.06, "weight": 2},
    {"name": "Oversupply",         "desc": "📦 Oversupply hits — Basic tokens slip.",                    "type": "elements", "targets": ["basic"],    "mult": 0.95, "weight": 2},

    # Type minors
    {"name": "Land Patrol",        "desc": "🐾 Land pets on patrol — Land tokens nudge up.",             "type": "types", "targets": ["land"],      "mult": 1.07, "weight": 2},
    {"name": "Burrow Rest",        "desc": "🕳️ Land pets burrow — Land tokens dip.",                    "type": "types", "targets": ["land"],      "mult": 0.94, "weight": 2},
    {"name": "Feeding Frenzy",     "desc": "🐟 Swimming pets feed — Swimming tokens rise.",              "type": "types", "targets": ["swimming"],  "mult": 1.07, "weight": 2},
    {"name": "Deep Dive",          "desc": "🌊 Pets dive deep — Swimming tokens dip.",                   "type": "types", "targets": ["swimming"],  "mult": 0.94, "weight": 2},
    {"name": "Updraft",            "desc": "🌤️ A nice updraft — Flying tokens soar briefly.",            "type": "types", "targets": ["flying"],    "mult": 1.07, "weight": 2},
    {"name": "Headwind",           "desc": "💨 A headwind slows flyers — Flying tokens dip.",            "type": "types", "targets": ["flying"],    "mult": 0.94, "weight": 2},
]
