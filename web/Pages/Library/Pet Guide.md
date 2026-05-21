# Pet System Guide

---

## Basics

Pets are your personal companions on the website — living creatures you adopt, raise, and take into every activity the site has to offer. Each pet is unique: it has a species, a type (Land, Swimming, or Flying), one or two elements, six core stats, and a generated name. Everything about your pet is tied to your Discord account, so you need to be logged in to access it.

### Adopting a Pet

If you don't have a pet yet, go to the **My Pet** page and click **+ Adopt a Pet**. You'll be shown a selection of species to choose from. Each species has a fixed stat distribution and two specialization stats — the two stats that species naturally excels at. Once you pick a species, the system randomly assigns your pet a type (Land, Swimming, or Flying), an element (and sometimes a second element), and generates a name based on all of those. You can also enter a custom name during adoption if you prefer.

Once adopted, your pet is permanent until you choose to release it.

### The Six Stats

Every pet has six core stats that define how it performs in everything from battles to casino games.

| Stat | Name | What It Does |
|------|------|--------------|
| <img src="/static/Emojis/Pets/Deco/ATT.png" style="height:16px;vertical-align:middle"> ATT | Attack | Raw damage output in battle |
| <img src="/static/Emojis/Pets/Deco/DEF.png" style="height:16px;vertical-align:middle"> DEF | Defense | Damage reduction when defending |
| <img src="/static/Emojis/Pets/Deco/INT.png" style="height:16px;vertical-align:middle"> INT | Intelligence | Boosts smart/tactical actions |
| <img src="/static/Emojis/Pets/Deco/DEX.png" style="height:16px;vertical-align:middle"> DEX | Dexterity | Speed and precision-based actions |
| <img src="/static/Emojis/Pets/Deco/HAP.png" style="height:16px;vertical-align:middle"> HAP | Happiness | Contributes to max HP |
| <img src="/static/Emojis/Pets/Deco/ENE.png" style="height:16px;vertical-align:middle"> ENE | Energy | Contributes to max HP and stamina |

**Max HP** is calculated as: `(stat_average + HAP × ENE) × 10`

The stat average is the mean of all six stats. HAP and ENE are your primary health stats — they feed into both the average and the multiplicative part of the formula. A pet with HAP 20 and ENE 20 adds 400 to the formula before the ×10 multiplier, making them dramatically tankier than a pet with low HAP/ENE.

**Combat stats** derived from your base stats:
- Attack power = <img src="/static/Emojis/Pets/Deco/ATT.png" style="height:14px;vertical-align:middle"> ATT + <img src="/static/Emojis/Pets/Deco/DEX.png" style="height:14px;vertical-align:middle"> DEX
- Defense power = <img src="/static/Emojis/Pets/Deco/DEF.png" style="height:14px;vertical-align:middle"> DEF + <img src="/static/Emojis/Pets/Deco/INT.png" style="height:14px;vertical-align:middle"> INT

### Specialization Stats

Every species has two specialization stats — the stats it naturally excels at. These are baked into the species' base stat distribution and shown in gold on your pet card.

### Types and Elements

**Types** form a triangle of advantages:
- <img src="/static/Emojis/Pets/Deco/Flying.png" style="height:16px;vertical-align:middle"> **Flying** beats <img src="/static/Emojis/Pets/Deco/Land.png" style="height:16px;vertical-align:middle"> **Land**
- <img src="/static/Emojis/Pets/Deco/Land.png" style="height:16px;vertical-align:middle"> **Land** beats <img src="/static/Emojis/Pets/Deco/Swimming.png" style="height:16px;vertical-align:middle"> **Swimming**
- <img src="/static/Emojis/Pets/Deco/Swimming.png" style="height:16px;vertical-align:middle"> **Swimming** beats <img src="/static/Emojis/Pets/Deco/Flying.png" style="height:16px;vertical-align:middle"> **Flying**

Each type advantage gives +15% damage in battle.

**Elements** — there are 13: Basic, Fire, Water, Electric, Ice, Plant, Rock, Air, Magic, Holy, Necro, Psychic, and Fighting. Most elements deal +10% damage against specific weaknesses. Basic is the exception — it deals −10% damage against everything. Your pet can have one or two elements. Dual-element pets are more versatile but rarely get the full bonus since the game averages across all element matchup combinations.

**Element strengths (deals +10% damage against):**

| Element | Strong Against |
|---------|---------------|
| <img src="/static/Emojis/Pets/Deco/Basic.png" style="height:16px;vertical-align:middle"> Basic | Nothing (−10% vs all) |
| <img src="/static/Emojis/Pets/Deco/Fire.png" style="height:16px;vertical-align:middle"> Fire | Ice, Plant, Necro |
| <img src="/static/Emojis/Pets/Deco/Water.png" style="height:16px;vertical-align:middle"> Water | Fire, Rock, Air |
| <img src="/static/Emojis/Pets/Deco/Electric.png" style="height:16px;vertical-align:middle"> Electric | Water, Plant, Fighting |
| <img src="/static/Emojis/Pets/Deco/Ice.png" style="height:16px;vertical-align:middle"> Ice | Air, Electric, Water |
| <img src="/static/Emojis/Pets/Deco/Plant.png" style="height:16px;vertical-align:middle"> Plant | Water, Air, Psychic |
| <img src="/static/Emojis/Pets/Deco/Rock.png" style="height:16px;vertical-align:middle"> Rock | Electric, Fire, Ice |
| <img src="/static/Emojis/Pets/Deco/Air.png" style="height:16px;vertical-align:middle"> Air | Rock, Fighting, Electric |
| <img src="/static/Emojis/Pets/Deco/Magic.png" style="height:16px;vertical-align:middle"> Magic | Psychic, Fighting, Fire |
| <img src="/static/Emojis/Pets/Deco/Holy.png" style="height:16px;vertical-align:middle"> Holy | Necro, Magic, Rock |
| <img src="/static/Emojis/Pets/Deco/Necro.png" style="height:16px;vertical-align:middle"> Necro | Holy, Magic, Plant |
| <img src="/static/Emojis/Pets/Deco/Psychic.png" style="height:16px;vertical-align:middle"> Psychic | Holy, Necro, Magic |
| <img src="/static/Emojis/Pets/Deco/Fighting.png" style="height:16px;vertical-align:middle"> Fighting | Ice, Psychic, Holy |

### Leveling Up

XP is how your pet grows. Everything you do earns XP, and when you accumulate enough, your pet levels up. Stats grow per level using a scaling formula: **3 × (1 + (level−1) ÷ 10) points per level gained**, distributed randomly across all six stats. At level 1–10 that's 3 points per level; at level 11–20 it's 6 points; at level 51–60 it's 18 points; at level 100+ it's 30+ points. The higher your level, the more stats you gain each time you level up.

**XP required per level:** `200 × (1.03 ^ (level − 1))`

- Level 1 → 2 costs 200 XP
- Each level costs 3% more than the last
- There is no level cap — pets grow forever

Stats also scale with level. Training, missions, quests, and most activities give +10% more XP per level above 1, so higher-level pets always benefit from doing the same activities.

### Rank Badges

Your pet earns a rank badge every 50 levels. Rank 1 unlocks at level 50, rank 2 at level 100, and so on — forever. There are 58 unique badge artworks. Once you pass rank 58 (level 2900+), the "Beyond" artwork displays, but your actual rank number keeps climbing with no ceiling.

---

## Growth

### The My Pet Page

The My Pet page is your pet's home base on the website. Everything you need to manage your pet lives here. You must be logged in with Discord to access it.

### The Pet Card

The pet card sits on the left side of the page and shows your pet's full status at a glance:

- **Pet image** (species icon) on the left
- **Name, level badge, type icon, and element icon(s)** in the center
- **Rank badge** on the right (appears once you reach level 50)
- **XP progress bar** showing current XP vs XP needed for next level
- **Equipment slots** — two rows of icons showing your equipped gear. Row 1: Helmet, Armor, Boots, Ring, Shield, Weapon. Row 2 (Ring sub-slots, only active when a Ring is equipped): Monster ×2, Gem ×2, Material ×1. Empty slots show a placeholder icon
- **Equipment bonus summary** — the active multiplier and a checklist showing which bonus conditions you've met
- **Stats grid** — all six stats with equipment bonuses shown in green next to each. Specialization stats are highlighted in gold
- **Combat stats row** — your computed ⚔️ ATK, 🛡️ DEF, and ❤️ HP values
- **Inventory** — a collapsible section below the stats showing all items you're holding, grouped by type

### Equipment

Equipment boosts your pet's stats while equipped. There are two rows of slots:

**Row 1 — Main Gear (1 of each):**

| Slot | Stats Boosted | Rarity |
|------|--------------|--------|
| Helmet | <img src="/static/Emojis/Pets/Deco/INT.png" style="height:14px;vertical-align:middle"> INT, <img src="/static/Emojis/Pets/Deco/HAP.png" style="height:14px;vertical-align:middle"> HAP | Rare |
| Armor | <img src="/static/Emojis/Pets/Deco/HAP.png" style="height:14px;vertical-align:middle"> HAP, <img src="/static/Emojis/Pets/Deco/ENE.png" style="height:14px;vertical-align:middle"> ENE | Rare |
| Boots | <img src="/static/Emojis/Pets/Deco/DEX.png" style="height:14px;vertical-align:middle"> DEX, <img src="/static/Emojis/Pets/Deco/ENE.png" style="height:14px;vertical-align:middle"> ENE | Rare |
| Ring | Mixed (varies by ring) | Epic |
| Shield | <img src="/static/Emojis/Pets/Deco/DEF.png" style="height:14px;vertical-align:middle"> DEF, <img src="/static/Emojis/Pets/Deco/INT.png" style="height:14px;vertical-align:middle"> INT | Rare |
| Weapon (Dagger / Katana / Sword / Axe / Hammer / Bow) | <img src="/static/Emojis/Pets/Deco/ATT.png" style="height:14px;vertical-align:middle"> ATT + one other | Uncommon |

All six main gear pieces come in **11 material variants** (Wood, Rusty Iron, Stone, Iron, Nature, Elven, Steel, Crystal, Volcanic, Advanced, SciFi). Pieces of the same variant share a **Set tag** — equipping all six from the same set unlocks a powerful set bonus.

**Row 2 — Ring Sub-slots (requires a Ring to be equipped):**

| Slot | Max | Stats Boosted | Rarity |
|------|-----|--------------|--------|
| Monster | 2 | Mixed (varies by monster) | Common |
| Gem | 2 | <img src="/static/Emojis/Pets/Deco/INT.png" style="height:14px;vertical-align:middle"> INT, <img src="/static/Emojis/Pets/Deco/HAP.png" style="height:14px;vertical-align:middle"> HAP, <img src="/static/Emojis/Pets/Deco/ENE.png" style="height:14px;vertical-align:middle"> ENE | Epic |
| Material | 1 | <img src="/static/Emojis/Pets/Deco/ATT.png" style="height:14px;vertical-align:middle"> ATT, <img src="/static/Emojis/Pets/Deco/DEF.png" style="height:14px;vertical-align:middle"> DEF, <img src="/static/Emojis/Pets/Deco/DEX.png" style="height:14px;vertical-align:middle"> DEX | Common–Mythic |

Ring sub-slots are only available when a Ring is equipped. Unequipping your Ring automatically removes all sub-slot items back to your inventory.

**Weapons** come in six types — each type has a different stat bias:

| Weapon | Stats | Bias |
|--------|-------|------|
| Dagger | <img src="/static/Emojis/Pets/Deco/ATT.png" style="height:14px;vertical-align:middle"> ATT + <img src="/static/Emojis/Pets/Deco/DEX.png" style="height:14px;vertical-align:middle"> DEX | More DEX |
| Katana | <img src="/static/Emojis/Pets/Deco/ATT.png" style="height:14px;vertical-align:middle"> ATT + <img src="/static/Emojis/Pets/Deco/DEX.png" style="height:14px;vertical-align:middle"> DEX | Balanced |
| Sword | <img src="/static/Emojis/Pets/Deco/ATT.png" style="height:14px;vertical-align:middle"> ATT + <img src="/static/Emojis/Pets/Deco/DEX.png" style="height:14px;vertical-align:middle"> DEX | More ATT |
| Axe | <img src="/static/Emojis/Pets/Deco/ATT.png" style="height:14px;vertical-align:middle"> ATT + <img src="/static/Emojis/Pets/Deco/ENE.png" style="height:14px;vertical-align:middle"> ENE | More ENE |
| Hammer | <img src="/static/Emojis/Pets/Deco/ATT.png" style="height:14px;vertical-align:middle"> ATT + <img src="/static/Emojis/Pets/Deco/ENE.png" style="height:14px;vertical-align:middle"> ENE | More ATT |
| Bow | <img src="/static/Emojis/Pets/Deco/ATT.png" style="height:14px;vertical-align:middle"> ATT + <img src="/static/Emojis/Pets/Deco/INT.png" style="height:14px;vertical-align:middle"> INT | Balanced |

**Materials** (for the Ring sub-slot) come in five rarities — Common (Dirt, Leaf, Sand), Uncommon (Bone, Fabric, Leather), Rare (Glass, Stone, Wood), Epic (Brick, Gold, Steel), and Mythic (Laser, Plutonium, Smart). Higher rarity means bigger stat bonuses.

**Gems** are named items (Ember Heart, Frost Shard, etc.) that each give a different spread of INT, HAP, and ENE bonuses.

**Monsters** are named creatures (Wirm, Dodl, Drak, etc.) that each give a different spread across all six stats.

**Rings** are named items (Iron Band, Star Sigil, etc.) that each give 25 points split across two stats.

### Equipment Multiplier System

Every equipped item's bonuses are multiplied by a single global multiplier before being added to your stats. The multiplier is built from several stacking components:

**Base multiplier formula:**
```
multiplier = slots_filled + set_bonus + ring_sub_bonus + level_bonus
```

| Component | Value | Condition |
|-----------|-------|-----------|
| Slots filled | +1 per slot | Each of the 6 main slots (Helmet, Armor, Boots, Ring, Shield, Weapon) that has an item |
| Set bonus | +3 | All 6 main slots are filled AND all share the same set tag (e.g. all "Iron" or all "Elven") |
| Ring sub-bonus | +1 | Both Monsters in the Ring sub-slots are the same |
| Ring sub-bonus | +1 | Both Gems in the Ring sub-slots are the same |
| Ring sub-bonus | +1 | A Material is equipped in the Ring sub-slot |
| Level bonus | +1 per 50 levels | Always applies regardless of equipment |

**Full Set Doubling:** If ALL of the following are true simultaneously — all 6 main slots filled, all 6 share the same set tag, a Ring is equipped, both Monsters match, both Gems match, and a Material is equipped — then the entire multiplier is **doubled** after calculation.

**Examples:**

| Setup | Level | Multiplier |
|-------|-------|-----------|
| No equipment | 1 | 1× |
| 3 main slots filled | 1 | 3× |
| All 6 slots filled, no matching set | 1 | 6× |
| All 6 slots filled, matching set | 1 | 9× (6 + 3) |
| All 6 slots + matching set + all ring sub-slots filled and matching | 1 | **18×** ((6+3+3) × 2) |
| All 6 slots filled, no matching set | 100 | 8× (6 + 2 level bonus) |
| All 6 slots + matching set + all ring sub-slots + matching | 50 | **20×** ((6+3+3+1) × 2) |
| All 6 slots + matching set + all ring sub-slots + matching | 100 | **24×** ((6+3+3+2) × 2) |
| All 6 slots + matching set + all ring sub-slots + matching | 150 | **28×** ((6+3+3+3) × 2) |

> **Note:** The level bonus is `level ÷ 50` (integer division). Level 50 = +1, level 100 = +2, level 150 = +3, etc.

The optimal setup is: all 6 main slots from the same set, a Ring equipped, two of the same Monster, two of the same Gem, and a Material in the Ring sub-slot. This gives the full doubling bonus on top of the maximum base multiplier.

### Inventory

The inventory panel on the pet card shows all items you're holding, grouped by type — each type has its own collapsible section (Helmet, Armor, Boots, Ring, Shield, Daggers, Katanas, Swords, Axes, Hammers, Bows, Potions, Materials, Gems, Monsters, Keys, Chests). Click a section header to expand or collapse it.

**To equip a main gear item** (Helmet, Armor, Boots, Ring, Shield, or any Weapon): click the item in your inventory. A confirmation prompt appears — confirm to equip it. The item moves from your inventory to the equipment slot. If the slot is already full, the old item is automatically returned to your inventory.

**To equip Ring sub-slot items** (Material, Gem, Monster): you must have a Ring equipped first. Then click the item — it goes into the Ring sub-slot. Gems and Monsters can hold 2 each; Material holds 1.

**To unequip an item**: click the equipped item icon in the equipment slots section of the pet card. It returns to your inventory. Unequipping a Ring also returns all Ring sub-slot items (Material, Gems, Monsters) to your inventory.

**To use a potion**: click the potion in your inventory. A confirmation prompt shows what the potion does. Confirm to consume it — the effect applies permanently to your pet's stats immediately. The potion is removed from your inventory.

Items stack up to 99 per type. If your inventory is full when you earn a new item, it converts to XP instead (`level × 100 XP` per overflow item).

### Potions

Potions are consumable items that permanently boost your pet's stats. Use them from the inventory panel.

| Potion | Effect |
|--------|--------|
| <img src="/static/Emojis/Pets/Deco/ATT.png" style="height:14px;vertical-align:middle"> ATT / <img src="/static/Emojis/Pets/Deco/DEF.png" style="height:14px;vertical-align:middle"> DEF / <img src="/static/Emojis/Pets/Deco/DEX.png" style="height:14px;vertical-align:middle"> DEX / <img src="/static/Emojis/Pets/Deco/INT.png" style="height:14px;vertical-align:middle"> INT / <img src="/static/Emojis/Pets/Deco/HAP.png" style="height:14px;vertical-align:middle"> HAP / <img src="/static/Emojis/Pets/Deco/ENE.png" style="height:14px;vertical-align:middle"> ENE Potion | +3 to that specific stat |
| Elemental Potion (e.g. <img src="/static/Emojis/Pets/Deco/Fire.png" style="height:14px;vertical-align:middle"> Fire Potion) | +5 to 3 random stats (single element) or +3 to 4 random stats (dual element) — only usable by matching element pets |
| S1 / S2 / S3 Potion | +1 / +2 / +3 to 2 random stats |
| Luck Potion | +1–5 to all 6 stats (random per stat) |
| Mega Potion | +10 to all 6 stats |
| Lesser / Health / Greater Health Potion | +5 / +10 / +15 to <img src="/static/Emojis/Pets/Deco/HAP.png" style="height:14px;vertical-align:middle"> HAP and <img src="/static/Emojis/Pets/Deco/ENE.png" style="height:14px;vertical-align:middle"> ENE |
| Lesser XP Potion | Grants `50 × level` XP |
| XP Potion | Grants `100 × level` XP |

### How to Obtain Items

Items come from almost everything you do:

- **Chests** — opened in the Loot Market tab using keys. The main source of Materials, Gems, Monsters, Rings, gear, weapons, and Potions
- **Battles** — winning NPC battles and boss battles drops items
- **Quests** — completing quest stages and finding loot chests during quests
- **Tasks** — daily task rewards include keys and chests
- **Missions** — completing missions drops keys
- **Play** — visiting locations drops keys, and boss encounters during play drop keys
- **Casino win streaks** — races, blackjack, craps, and hold'em all reward keys on win streaks
- **Item Board** — buy items directly from other players using XP

### Keys and Chests

Keys are the currency for opening chests. Spend them in the **Loot Market tab** on your My Pet page — select a chest tier, set the amount (1–10), and click "Open Chest."

| Chest | Key Required | Loot |
|-------|-------------|------|
| <img src="/static/Emojis/Pets/Equipment/chest1.png" style="height:15px;vertical-align:middle"> Chest 1 | 1× <img src="/static/Emojis/Pets/Equipment/Key1.png" style="height:15px;vertical-align:middle"> Key1 | 1 Common or Uncommon item |
| <img src="/static/Emojis/Pets/Equipment/chest2.png" style="height:15px;vertical-align:middle"> Chest 2 | 1× <img src="/static/Emojis/Pets/Equipment/Key2.png" style="height:15px;vertical-align:middle"> Key2 | 1 Rare item |
| <img src="/static/Emojis/Pets/Equipment/chest3.png" style="height:15px;vertical-align:middle"> Chest 3 | 1× <img src="/static/Emojis/Pets/Equipment/Key3.png" style="height:15px;vertical-align:middle"> Key3 | 1 Epic item |
| <img src="/static/Emojis/Pets/Equipment/chest4.png" style="height:15px;vertical-align:middle"> Chest 4 | 1× <img src="/static/Emojis/Pets/Equipment/Key1.png" style="height:15px;vertical-align:middle"> Key1 + <img src="/static/Emojis/Pets/Equipment/Key2.png" style="height:15px;vertical-align:middle"> Key2 + <img src="/static/Emojis/Pets/Equipment/Key3.png" style="height:15px;vertical-align:middle"> Key3 | 1 item of your chosen type + 1 Uncommon or better |

Chest 4 asks you to pick a guaranteed item type (Material, Gem, Monster, Potion, Ring, Helmet, Armor, Boots, Shield, or any Weapon type) before opening.

If a task rewards you a chest directly, it lands in your inventory and does not require keys to open — just click it.

### Abilities

Abilities are an endgame feature for high-level pets. They let you trade levels for permanent bonuses.

**How it works:**
1. Spend 500 levels to purchase 1 ability point
2. Spend 1 ability point on a stat mastery to unlock that branch
3. Spend remaining points on any abilities in unlocked branches

**Stat Mastery** gives a permanent multiplier to that stat: each point spent adds +0.1× (so 1 point = 1.1×, 10 points = 2.0×).

**Advantage Mastery** adds a flat bonus to your type or element advantage multiplier when you have the advantage.

**Abilities** are grouped into 6 branches by stat (<img src="/static/Emojis/Pets/Deco/ATT.png" style="height:14px;vertical-align:middle"> ATT, <img src="/static/Emojis/Pets/Deco/DEF.png" style="height:14px;vertical-align:middle"> DEF, <img src="/static/Emojis/Pets/Deco/INT.png" style="height:14px;vertical-align:middle"> INT, <img src="/static/Emojis/Pets/Deco/DEX.png" style="height:14px;vertical-align:middle"> DEX, <img src="/static/Emojis/Pets/Deco/HAP.png" style="height:14px;vertical-align:middle"> HAP, <img src="/static/Emojis/Pets/Deco/ENE.png" style="height:14px;vertical-align:middle"> ENE). Each ability has up to 5 levels, costs 1 point per level, and scales linearly. Examples:
- <img src="/static/Emojis/Pets/Deco/ATT.png" style="height:13px;vertical-align:middle"> ATT branch: NPC Crusher (more damage vs NPCs), PvP Striker (more damage in PvP), critical hit chance and multiplier
- <img src="/static/Emojis/Pets/Deco/DEF.png" style="height:13px;vertical-align:middle"> DEF branch: NPC Shield (less damage from NPCs), PvP Guard (less damage in PvP), charge protection
- <img src="/static/Emojis/Pets/Deco/INT.png" style="height:13px;vertical-align:middle"> INT branch: XP multipliers for all 8 activities
- <img src="/static/Emojis/Pets/Deco/DEX.png" style="height:13px;vertical-align:middle"> DEX branch: race speed boost, casino loss reduction
- <img src="/static/Emojis/Pets/Deco/HAP.png" style="height:13px;vertical-align:middle"> HAP branch: battle health bonus, casino win bonuses
- <img src="/static/Emojis/Pets/Deco/ENE.png" style="height:13px;vertical-align:middle"> ENE branch: battle health bonus, charge limit increase, speed boost

There are 49 abilities × 5 levels = 245 total ability points to spend. Full completion costs 122,500 levels. You must have at least 1 point in a stat mastery to unlock abilities in that branch.

---

## Interactions

### Training

Go to the **Train tab** on your My Pet page. Pick Easy, Average, or Hard difficulty, then pick which stat you want to train (<img src="/static/Emojis/Pets/Deco/ATT.png" style="height:14px;vertical-align:middle"> ATT, <img src="/static/Emojis/Pets/Deco/DEF.png" style="height:14px;vertical-align:middle"> DEF, <img src="/static/Emojis/Pets/Deco/INT.png" style="height:14px;vertical-align:middle"> INT, <img src="/static/Emojis/Pets/Deco/DEX.png" style="height:14px;vertical-align:middle"> DEX, <img src="/static/Emojis/Pets/Deco/HAP.png" style="height:14px;vertical-align:middle"> HAP, or <img src="/static/Emojis/Pets/Deco/ENE.png" style="height:14px;vertical-align:middle"> ENE), then click "Start Training." Training directly increases or decreases a chosen stat — it does not award XP. Higher difficulty means a bigger stat change but a lower success chance. On failure, the stat decreases by the same amount it would have increased. There's a 5-second cooldown between uses.

| Difficulty | Stat Change | Success Chance |
|------------|-------------|----------------|
| Easy | 1 × equipment multiplier | 75% |
| Average | 3 × equipment multiplier | 60% |
| Hard | 5 × equipment multiplier | 45% |

Your equipment multiplier scales the change — a full matching set at level 50 (20× multiplier) means a successful Hard training adds 100 to your chosen stat.

### Missions

Go to the **Mission tab**. Pick a difficulty, optionally enter a Gamble XP amount (risk XP for a bonus reward on success — you lose it on failure), then click "Launch Mission." Missions have a 5-second cooldown.

| Difficulty | Base XP | Success Chance | Key Drop Chance (per key) |
|------------|---------|----------------|--------------------------|
| Easy | 100+ XP | 70% | 50% per <img src="/static/Emojis/Pets/Equipment/Key1.png" style="height:14px;vertical-align:middle"> key |
| Average | 250+ XP | 50% | 65% per <img src="/static/Emojis/Pets/Equipment/Key2.png" style="height:14px;vertical-align:middle"> key |
| Hard | 500+ XP | 30% | 75% per <img src="/static/Emojis/Pets/Equipment/Key3.png" style="height:14px;vertical-align:middle"> key |

Each of the three keys (<img src="/static/Emojis/Pets/Equipment/Key1.png" style="height:14px;vertical-align:middle"> Key1, <img src="/static/Emojis/Pets/Equipment/Key2.png" style="height:14px;vertical-align:middle"> Key2, <img src="/static/Emojis/Pets/Equipment/Key3.png" style="height:14px;vertical-align:middle"> Key3) rolls independently at the listed chance — so on a Hard mission you might get all three, two, one, or none. XP scales with your pet's level (+10% per level above 1). Failing a mission only costs XP if you gambled — the gamble amount is lost on failure.

### Play

Go to the **Play tab**. Click a location tile to select it (it highlights gold), then click "Go Play!" Matching your pet's element to the location gives more XP and better key drops. 5-second cooldown. Base XP is `5 × your pet's level` before any element multiplier.

Locations: <img src="/static/Emojis/Pets/Deco/camping.png" style="height:14px;vertical-align:middle"> Camp, <img src="/static/Emojis/Pets/Deco/bonfire.png" style="height:14px;vertical-align:middle"> Bonfire, <img src="/static/Emojis/Pets/Deco/beach.png" style="height:14px;vertical-align:middle"> Beach, <img src="/static/Emojis/Pets/Deco/forest.png" style="height:14px;vertical-align:middle"> Forest, <img src="/static/Emojis/Pets/Deco/hotairballoon.png" style="height:14px;vertical-align:middle"> Hot Air Balloon, <img src="/static/Emojis/Pets/Deco/cruiseship.png" style="height:14px;vertical-align:middle"> Cruiseship, <img src="/static/Emojis/Pets/Deco/mountain.png" style="height:14px;vertical-align:middle"> Mountain, <img src="/static/Emojis/Pets/Deco/gym.png" style="height:14px;vertical-align:middle"> Gym, <img src="/static/Emojis/Pets/Deco/graveyard.png" style="height:14px;vertical-align:middle"> Graveyard, <img src="/static/Emojis/Pets/Deco/festival.png" style="height:14px;vertical-align:middle"> Festival, <img src="/static/Emojis/Pets/Deco/glacier.png" style="height:14px;vertical-align:middle"> Glacier, <img src="/static/Emojis/Pets/Deco/pyramids.png" style="height:14px;vertical-align:middle"> Pyramids

| Element Match | XP | Key Drops |
|---------------|----|-----------|
| No match (or Basic element) | 5 × level | 75% chance for 1 random key |
| 1 element matches | 10 × level | Guaranteed 1 key + 25% chance for 1–2 more |
| Both elements match | 15 × level | Guaranteed 1 key + 50% chance for 1–2 more |

There's also a **5% chance** of a boss encounter during play. The boss is generated based on the location's elements and your pet's stats. Defeating it rewards 5× normal XP and one of each key type.

### Quests

Go to the **Quest tab**. Select a location and difficulty, then click "Begin Quest." Quests are AI-generated 5-stage adventures unique to your location and difficulty choice.

Each stage shows an event description and three choices. Each choice is tied to a pair of your pet's stats (ATT/DEF, INT/DEX, or HAP/ENE). Your pet's stat level vs the required skill determines your success chance. Some stages can trigger a live battle if you fail a skill check. Stage 4 may contain a mimic chest — if the chest seems suspicious, the ATT/DEF option lets you fight it for double loot.

Quests have a 5-second cooldown to start.

### NPC Battles

NPC battles are turn-based fights against computer-controlled monsters. Access them from the **Battle** section. Choose an enemy type and rarity, then fight.

**The three actions:**
- **<img src="/static/Emojis/Pets/Deco/ATT.png" style="height:14px;vertical-align:middle"> Attack** — Roll a d20, multiply by your ATT + DEX, apply charge multiplier and type/element bonuses. Full damage lands if the target is also attacking. If the target is charging, they take 25% extra damage.
- **<img src="/static/Emojis/Pets/Deco/DEF.png" style="height:14px;vertical-align:middle"> Defend** — Roll a d20, multiply by your DEF + INT. If your defense value exceeds the attacker's attack value, the excess becomes parry damage reflected back at them. If defense equals attack, no damage is dealt either way. Defending while being charged at is especially powerful.
- **<img src="/static/Emojis/Pets/Deco/ENE.png" style="height:14px;vertical-align:middle"> Charge** — Deal zero damage this turn but advance your charge multiplier: 1.0 → 2.0 → 3.0 → 4.0 → 5.0 (max). While charging you take 25% extra damage from any attack that lands. The ENE ability branch can raise your charge cap beyond 5.

Winning NPC battles drops items and XP. Losing awards reduced XP.

### Boss Battles

Boss battles are harder NPC fights with bigger rewards. They can be triggered during Play (5% chance) or accessed directly. Bosses have 2.5–4× your pet's HP and deal scaled damage. Defeating a boss rewards 5× normal XP and one of each key type.

In multiplayer boss battles, relationships affect your damage:
- Best Friends fighting together: +25% damage
- Friends fighting together: +10% damage
- Foes fighting together: −15% damage
- Enemies cannot participate in the same boss battle

### PvP Battles (The Floor)

The Floor is the multiplayer hub where you challenge other players' pets. Open a lobby from the website, set the max number of opponents (1–9), and other players can join. Battle modes are 1v1 or Free-For-All (last pet standing wins).

Relationships affect PvP damage (both sides must have the same relationship for it to apply):
- Friends: both deal 0.8× damage
- Foes: both deal 1.2× damage
- Enemies: both deal 1.5× damage
- Best Friends: cannot battle each other

You can also create bracket tournaments (4, 8, or 16 players) — the organizer sets the size, players register, and matches run automatically.

### Survivor Series (Survive)

Survivor Series is a web-based battle royale where your pet competes against other players and AI opponents in a shared arena. Open the **Survive** page to join or start a game.

**Starting a game:** Once at least 2 real players have joined, any player can click **Start Game** to begin a 15-minute countdown. NPCs are added immediately. When the countdown ends, Round 1 fires. Every subsequent round fires 15 minutes after the previous one.

**The arena map** is divided into 12 elemental zones (<img src="/static/Emojis/Pets/Deco/Fire.png" style="height:14px;vertical-align:middle"> Fire, <img src="/static/Emojis/Pets/Deco/Water.png" style="height:14px;vertical-align:middle"> Water, <img src="/static/Emojis/Pets/Deco/Ice.png" style="height:14px;vertical-align:middle"> Ice, <img src="/static/Emojis/Pets/Deco/Plant.png" style="height:14px;vertical-align:middle"> Plant, <img src="/static/Emojis/Pets/Deco/Air.png" style="height:14px;vertical-align:middle"> Air, <img src="/static/Emojis/Pets/Deco/Electric.png" style="height:14px;vertical-align:middle"> Electric, <img src="/static/Emojis/Pets/Deco/Magic.png" style="height:14px;vertical-align:middle"> Magic, <img src="/static/Emojis/Pets/Deco/Holy.png" style="height:14px;vertical-align:middle"> Holy, <img src="/static/Emojis/Pets/Deco/Necro.png" style="height:14px;vertical-align:middle"> Necro, <img src="/static/Emojis/Pets/Deco/Fighting.png" style="height:14px;vertical-align:middle"> Fighting, <img src="/static/Emojis/Pets/Deco/Rock.png" style="height:14px;vertical-align:middle"> Rock, <img src="/static/Emojis/Pets/Deco/Basic.png" style="height:14px;vertical-align:middle"> Basic), each with unique animated terrain. You can scroll to zoom, drag to pan, and use filter buttons to view specific pets or relationships.

**Survive Score** is your core stat: `level ÷ equipment_multiplier ÷ 10`. Higher level = stronger. Higher equipment multiplier = weaker. Equipment actually hurts you in Survivor Series — unequip everything for the best score.

**Charge system:** Every round a pet avoids combat, they build a charge stack (max 5, up to 1.5× multiplier). When they fight, the multiplier applies to their combat power and resets.

**Combat:** Win probability is based on the ratio of each pet's Elimination Score (Survive Score × type/element advantages × charge multiplier), clamped between 5%–95%. Close fights compress toward 50%.

**Encounter chances per zone:**
- Enemies in the same zone: always fight (100%)
- Foes in the same zone: 90%
- Strangers (3+ in zone): 85%
- Strangers (2 in zone): 65%
- Friends: 40%
- Best Friends: 20%
- A dominant pet (score > 1.5× opponent) adds +15% encounter chance

**Movement:** Pets prioritize chasing enemies, staying with best friends, hunting weaker pets if dominant, fleeing stronger strangers, and defaulting to their preferred element zones. After several rounds with no eliminations, arena pressure forces pets into fewer zones to guarantee encounters happen. Pets can also form temporary deals (truces) to gang up on a common threat.

**Advanced mechanics:** Pets that rack up 3+ kills enter a rampage state. Pets that are wounded fight at −20% score. Pets in the bottom 10% of scores get a +25% "last stand" bonus. Environmental events can damage or force-move pets in affected zones.

**XP rewards at game end:** `(rounds_survived × 10 + kills × 25) × max(1, level ÷ 5 + 1)`. The winner also gets `+200 × max(1, level ÷ 5 + 1)`.

### Casino Games

All casino games use XP as the currency. You win or lose XP based on the outcome. Win streaks also reward keys.

**Slot Machine** — Spin the reels and match symbols to win XP. Choose a difficulty and bet amount, then spin. Higher difficulty = fewer symbols = harder to match = bigger payout. There's also a Fun Mode that lets you play with no XP changes. Insanity mode uses two separate reels — an element reel and a pet species reel — and you need to match your own pet's element on the element reel and your own species on the species reel simultaneously for the top payout.

| Difficulty | 3-Match Payout | 2-Match Payout |
|------------|---------------|----------------|
| Very Easy | 8× | 0.5× |
| Easy | 15× | ~0.78× |
| Medium | 35× | ~1.33× |
| Hard | 168× | 3.33× |
| Very Hard | 1,061× | ~0.49× |
| Insanity | 2,500,000,000× (both reels) | 220,000× (both reels) |

Slots also have a chance to drop keys on wins: Medium = 5%, Hard = 10%, Very Hard / Insanity = 20%.

**Pet Races** — Race your pet against bots and bet XP. Choose a difficulty (Apprentice, Journeyman, or Senior) and whether to play in simulation mode (instant result vs AI) or lobby mode (wait for real players). Race speed is determined by your pet's DEX, ENE, and HAP stats using a log-scale formula with randomness. Win streaks multiply your payout and reward keys. Winnings accumulate as pending XP — you must cash out to receive them. Losing wipes all pending XP and keys.

| Difficulty | Base Payout | Bot Strength |
|------------|------------|--------------|
| Apprentice | 1.25× bet | Weak (you win ~60–65%) |
| Journeyman | 2.0× bet | Medium (~even odds) |
| Senior | 3.0× bet | Strong (you win ~35–40%) |

**Win streak multipliers and key drops:**

| Win Streak | Payout Multiplier | Key Awarded |
|------------|------------------|-------------|
| 1–2 wins | 1× | <img src="/static/Emojis/Pets/Equipment/Key1.png" style="height:14px;vertical-align:middle"> Key1 |
| 3–5 wins | 2× | <img src="/static/Emojis/Pets/Equipment/Key2.png" style="height:14px;vertical-align:middle"> Key2 |
| 6–8 wins | 4× | <img src="/static/Emojis/Pets/Equipment/Key3.png" style="height:14px;vertical-align:middle"> Key3 |
| 9+ wins | 8× | <img src="/static/Emojis/Pets/Equipment/Key1.png" style="height:14px;vertical-align:middle"> Key1 + <img src="/static/Emojis/Pets/Equipment/Key2.png" style="height:14px;vertical-align:middle"> Key2 + <img src="/static/Emojis/Pets/Equipment/Key3.png" style="height:14px;vertical-align:middle"> Key3 |

**Blackjack** — Classic blackjack. Get closer to 21 than the dealer without going over. Play solo or with up to 3 AI bots. Supports split hands (up to 4) and double down. Win streaks reward keys — a 7+ win streak triggers a jackpot key drop.

**Craps** — Roll dice and bet on outcomes. Choose your dice color. Available bets include Pass Line, Don't Pass, Field, Place bets (4–10), Any 7, and Hard ways (4/6/8/10). Win streaks reward keys.

**Texas Hold'em** — Full Texas Hold'em poker with XP as the bankroll. Set a buy-in, add 0–3 AI bots, and play through Pre-deal → Pre-flop → Flop → Turn → River. Actions each round: Bet/Raise, Call/Check, or Fold. Win streaks reward keys.

**Casino win streak keys:**

| Win Streak | Keys Awarded |
|------------|-------------|
| 1 win | 1× <img src="/static/Emojis/Pets/Equipment/Key1.png" style="height:14px;vertical-align:middle"> Key1 |
| 2 wins | 2× <img src="/static/Emojis/Pets/Equipment/Key1.png" style="height:14px;vertical-align:middle"> Key1 |
| 3 wins | 1× <img src="/static/Emojis/Pets/Equipment/Key2.png" style="height:14px;vertical-align:middle"> Key2 |
| 4 wins | 2× <img src="/static/Emojis/Pets/Equipment/Key2.png" style="height:14px;vertical-align:middle"> Key2 |
| 5 wins | 1× <img src="/static/Emojis/Pets/Equipment/Key3.png" style="height:14px;vertical-align:middle"> Key3 |
| 6 wins | 2× <img src="/static/Emojis/Pets/Equipment/Key3.png" style="height:14px;vertical-align:middle"> Key3 |
| 7+ wins | 3× <img src="/static/Emojis/Pets/Equipment/Key1.png" style="height:14px;vertical-align:middle"> Key1 + 3× <img src="/static/Emojis/Pets/Equipment/Key2.png" style="height:14px;vertical-align:middle"> Key2 + 3× <img src="/static/Emojis/Pets/Equipment/Key3.png" style="height:14px;vertical-align:middle"> Key3 (Jackpot!) |

### Pet Stock Market

The Pet Stock Market is an XP investment system. Buy and sell tokens representing pet types and elements, with prices updating every 15 minutes.

**Tokens available:**
- 3 type tokens: <img src="/static/Emojis/Pets/Deco/Land.png" style="height:14px;vertical-align:middle"> Land, <img src="/static/Emojis/Pets/Deco/Swimming.png" style="height:14px;vertical-align:middle"> Swimming, <img src="/static/Emojis/Pets/Deco/Flying.png" style="height:14px;vertical-align:middle"> Flying (base price: 250 XP each)
- 13 element tokens: <img src="/static/Emojis/Pets/Deco/Basic.png" style="height:14px;vertical-align:middle"> Basic, <img src="/static/Emojis/Pets/Deco/Fire.png" style="height:14px;vertical-align:middle"> Fire, <img src="/static/Emojis/Pets/Deco/Water.png" style="height:14px;vertical-align:middle"> Water, <img src="/static/Emojis/Pets/Deco/Electric.png" style="height:14px;vertical-align:middle"> Electric, <img src="/static/Emojis/Pets/Deco/Ice.png" style="height:14px;vertical-align:middle"> Ice, <img src="/static/Emojis/Pets/Deco/Plant.png" style="height:14px;vertical-align:middle"> Plant, <img src="/static/Emojis/Pets/Deco/Rock.png" style="height:14px;vertical-align:middle"> Rock, <img src="/static/Emojis/Pets/Deco/Air.png" style="height:14px;vertical-align:middle"> Air, <img src="/static/Emojis/Pets/Deco/Magic.png" style="height:14px;vertical-align:middle"> Magic, <img src="/static/Emojis/Pets/Deco/Holy.png" style="height:14px;vertical-align:middle"> Holy, <img src="/static/Emojis/Pets/Deco/Necro.png" style="height:14px;vertical-align:middle"> Necro, <img src="/static/Emojis/Pets/Deco/Psychic.png" style="height:14px;vertical-align:middle"> Psychic, <img src="/static/Emojis/Pets/Deco/Fighting.png" style="height:14px;vertical-align:middle"> Fighting (base price: 500 XP each)

**Buying** costs XP from your pet. Tokens that don't match your pet's type or element cost more:
- Matches your pet's type or element: 1× price
- Doesn't match, single-element pet: 2× price
- Doesn't match, dual-element pet: 3× price

Buying deducts XP directly — your pet can level down if you spend enough.

**Selling** always happens at the current market price with no multiplier. Selling adds XP to your pet and can trigger level-ups.

**Price dynamics** update every 15 minutes: random drift (elements ±20%, types ±12%), momentum spikes (10% chance of extra ±12% volatility), buy/sell pressure from other players, and market events (Minor events every tick, Major events on 85% of days, Holiday events on special dates).

Track your P&L from the market page — it shows XP spent, XP received from sells, unrealised value of held tokens, and net profit/loss.

### Item Board

The Item Board (Bazaar) is a player-to-player marketplace where you can buy and sell items using XP. Access it from the sidebar.

**To post an item:** Go to the Item Board and list an item from your inventory. Set a price in XP and choose whether to price it in XP or as a gift. Your listing goes live immediately and other players can see it in real time.

**To buy an item:** Browse the board, find what you want, and click to purchase. The XP is deducted from your pet and added to the seller's pet. The seller gets a Discord DM notification when their item sells.

Posting an item on the Item Board also counts toward the "Post an item on the Item Board" daily task.

### Tasks

Tasks are daily objectives that reward you with keys or chests for completing them. Open the **Tasks page** from the sidebar to view your slots.

You have **7 task slots total:**
- **Slot 0 — Daily Goal:** Complete 10 daily tasks to earn a chest reward. The chest tier improves with your streak — completing the goal on consecutive days upgrades it from Chest 1 up to Chest 4. Missing a day resets your streak.
- **Slots 1–6 — Regular Tasks:** Six individual tasks, each with its own objective and reward. All slots reset at UTC midnight every day.

Each task card shows what to do, a progress bar that fills as you complete the required actions, and the reward shown upfront. Tasks track your actions automatically — just do the thing and the bar updates in real time.

**Task types include:** Play, Train, Mission, Win NPC Battle, Complete Quest, Post Item to Item Board, Win Boss Battle, Rename a battle action, Use Potion, Equip Item, Open Chest, Consume Item, Buy/Sell Pet Stock Tokens, Play Slots, Play Keno, Coin Flip, Get Horoscope, Race, Join/Survive/Eliminate in Survivor Series, Buy Powerball Ticket, Scratch Tickets.

**Rename tasks** are phrased as "Pet is tired of {action} — rename it." Go to the Rename tab on your My Pet page, update that specific battle action label (Attack, Defense, or Charge), and save. The task completes automatically.

**Rewards scale with difficulty:**

| Reward Tier | What You Can Get |
|-------------|-----------------|
| Low | 1× <img src="/static/Emojis/Pets/Equipment/Key1.png" style="height:14px;vertical-align:middle"> Key1, <img src="/static/Emojis/Pets/Equipment/Key2.png" style="height:14px;vertical-align:middle"> Key2, or <img src="/static/Emojis/Pets/Equipment/Key3.png" style="height:14px;vertical-align:middle"> Key3 |
| Mid | 1–2× Keys (mix of tiers), rare chance at <img src="/static/Emojis/Pets/Equipment/chest1.png" style="height:14px;vertical-align:middle"> Chest 1 |
| High | 2–3× Keys (higher tiers), chance at <img src="/static/Emojis/Pets/Equipment/chest2.png" style="height:14px;vertical-align:middle"> Chest 2 or <img src="/static/Emojis/Pets/Equipment/chest3.png" style="height:14px;vertical-align:middle"> Chest 3 |
| Top | 2–3× Keys or <img src="/static/Emojis/Pets/Equipment/chest2.png" style="height:14px;vertical-align:middle"> Chest 2 / <img src="/static/Emojis/Pets/Equipment/chest3.png" style="height:14px;vertical-align:middle"> Chest 3 / <img src="/static/Emojis/Pets/Equipment/chest4.png" style="height:14px;vertical-align:middle"> Chest 4 |

**Cooldowns:** All regular task slots reset at UTC midnight. If you complete a task before midnight, that slot stays completed until the reset. You can dismiss any task you don't want — dismissed slots also wait for the midnight reset.

**DM Notifications:** Click the 🔔 bell button on the Tasks page to configure Discord DM pings when your task slots refresh. Options are Off, Each Slot (one ping per slot as it refreshes), or All Slots (one ping when all slots are ready).

---

## Hints

**Build for your specializations.** Your pet's two specialization stats are shown in gold on the pet card. Focus your potions and equipment on boosting those stats — they're what your species is built around.

**Aim for a full matching set.** Equip all 6 main slots (Helmet, Armor, Boots, Ring, Shield, Weapon) from the same material variant (e.g. all "Iron" or all "Elven"). That adds +3 to your base multiplier. Then fill the Ring sub-slots with two matching Monsters, two matching Gems, and a Material — and the entire multiplier doubles. A level 50 pet with a full matching set and all ring sub-slots filled gets a **20× multiplier** on all equipment bonuses.

**Ring sub-slots are powerful but gated.** You need a Ring equipped before you can add Monsters, Gems, or a Material to it. Unequipping the Ring clears all sub-slots back to your inventory, so plan your loadout before swapping rings.

**<img src="/static/Emojis/Pets/Deco/HAP.png" style="height:14px;vertical-align:middle"> HAP and <img src="/static/Emojis/Pets/Deco/ENE.png" style="height:14px;vertical-align:middle"> ENE are your health stats.** If you want a tankier pet that survives longer in battles and Survivor Series, prioritize HAP and ENE. They feed into both the average and the multiplicative part of the HP formula — small increases go a long way.

**Training is a stat tool, not an XP tool.** Training directly changes a chosen stat — it doesn't award XP. Use it to fine-tune your build. Hard training with a high equipment multiplier can add massive amounts to a stat on a single success (a full matching set at level 50 gives 20× — meaning Hard training adds 100 per success), but failure costs the same amount, so be careful.

**Match your element when playing locations.** Always check which element a location favors before hitting Play. A matching element gives 2–3× XP and better key drops. Over time this makes a huge difference in how fast you level and how many chests you open.

**Hard missions are worth it at higher levels.** The 30% success chance sounds rough, but Hard missions give each key an independent 75% drop chance and award 500+ base XP scaled by your level. At higher levels, a successful Hard mission is one of the best XP-per-action activities in the game. And since only gambled XP is lost on failure, you can run them risk-free without gambling.

**Don't sleep on the Item Board.** If you're getting duplicate Materials or Gems you don't need, post them on the Item Board instead of letting them overflow to XP. You'll earn more XP from the sale than from the overflow conversion, and another player gets something useful.

**In Survivor Series, unequip everything.** Your Survive Score is `level ÷ equipment_multiplier ÷ 10`. Equipment multipliers divide your score, making you weaker. A level 500 pet with no equipment has a score of 50. The same pet with a full matching set at level 500 (multiplier of 28×+) has a score under 2. Go in naked.

**Let charge stacks build in Survivor Series.** Every round you avoid combat, your charge multiplier grows (up to 1.5× at 5 rounds). If you can stay out of fights early, you'll hit much harder when you finally engage.

**In turn-based battles, Defend beats Charge.** If you read that your opponent is about to release a big charge, defending can completely negate it and reflect the excess back as parry damage. Charge is powerful but predictable — experienced players will punish it.

**Use the Ability Tree for endgame.** Once your pet is high level, the Ability Tree lets you trade 500 levels per ability point for permanent bonuses. The <img src="/static/Emojis/Pets/Deco/INT.png" style="height:13px;vertical-align:middle"> INT branch gives XP multipliers for all 8 activities — unlocking those early makes every subsequent activity more efficient. The <img src="/static/Emojis/Pets/Deco/DEX.png" style="height:13px;vertical-align:middle"> DEX branch reduces casino losses, which matters if you play the casino regularly.

**Win streaks in the casino compound fast.** A 7+ win streak in Blackjack, Craps, or Hold'em gives a jackpot key drop (3× <img src="/static/Emojis/Pets/Equipment/Key1.png" style="height:13px;vertical-align:middle"> Key1 + 3× <img src="/static/Emojis/Pets/Equipment/Key2.png" style="height:13px;vertical-align:middle"> Key2 + 3× <img src="/static/Emojis/Pets/Equipment/Key3.png" style="height:13px;vertical-align:middle"> Key3). If you're on a streak, consider playing conservatively to protect it rather than going for big bets.

**Race on Senior difficulty with a streak.** A Senior race with a 9+ win streak pays `bet × 3.0 × 8 = 24×`. Build your streak on Apprentice first, then switch to Senior once you're confident. Remember: losing wipes all pending XP and keys, so cash out before you get greedy.

**Complete your Daily Goal every day.** The Daily Goal (slot 0 on the Tasks page) asks you to complete 10 tasks. Do it on consecutive days and the chest reward upgrades — from Chest 1 up to Chest 4 the longer your streak runs. Missing a day resets it.

**Relationships change how you play.** Setting someone as a Foe means you both deal 1.2× damage to each other in PvP — useful if you want harder fights. Setting someone as an Enemy means 1.5× damage both ways. Best Friends can't battle each other but get +25% damage when fighting bosses together.
