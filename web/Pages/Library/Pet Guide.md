# Pet System Guide

## Overview

Pets are your digital companions — living, growing creatures you raise, train, and battle with. Every pet has its own stats, element, type, and personality. You earn XP through battles, missions, quests, activities, and gambling. That XP levels your pet up, making it stronger over time.

Everything about your pet is managed from the **My Pet Page** on the website. That's your home base — it shows your pet's full status and gives you access to every action you can take.

---

## Stats & Health

Every pet has six core stats that define how it performs in combat and activities.

| Stat | Name | What It Does |
|------|------|--------------|
| ATT | Attack | Raw damage output in battle |
| DEF | Defense | Damage reduction when defending |
| INT | Intelligence | Boosts smart/tactical actions |
| DEX | Dexterity | Speed and precision-based actions |
| HAP | Happiness | Contributes to max HP |
| ENE | Energy | Contributes to max HP and stamina |

**Max HP Formula:** `((ATT + DEF + INT + DEX + HAP + ENE) ÷ 6 + HAP × ENE) × 10`

HAP and ENE are your primary health stats — they contribute to both the average and the multiplicative health component. A pet with HAP 20 and ENE 20 adds 400 to the formula before the ×10 multiplier, making them dramatically tankier.

**Computed combat stats** derived from your base stats:
- `Attack power = ATT + DEX`
- `Defense power = DEF + INT`

Stats grow by **5 points per level**, distributed randomly across all six stats. Equipment and potions can boost them further. On the pet card, specialization stats are shown in gold to distinguish them.

---

## Leveling & XP

XP is the currency of pet growth. Everything you do earns XP, and XP pushes your pet to the next level.

**XP Formula per level:** `200 × (1.03 ^ (level − 1))`

- Level 1 → 2 requires **200 XP**
- Each level costs 3% more than the last
- **Levels and XP continue forever — there is no cap**

**XP Sources and approximate gains:**

| Activity | XP Gained |
|----------|-----------|
| Play (no element match) | `5 × level` (±5) |
| Play (1 element match) | `10 × level` (±5) |
| Play (both elements match) | `15 × level` (±5) |
| Train (Easy) | 50+ XP (90% success) |
| Train (Average) | 100+ XP (70% success) |
| Train (Hard) | 200+ XP (50% success) |
| Mission (Easy) | 100+ XP (70% success) |
| Mission (Average) | 250+ XP (50% success) |
| Mission (Hard) | 500+ XP (30% success) |
| Quest (stage success) | Scales with pet skill vs required skill |
| PvP Win | `(damage_dealt ÷ 10) + (damage_taken ÷ 5)` |
| PvP Loss | `(damage_dealt ÷ 15) + (damage_taken ÷ 10)` |
| Survivor Series | `(rounds_survived × 10 + kills × 25) × max(1, level ÷ 5 + 1)` |
| SS Winner bonus | `+200 × max(1, level ÷ 5 + 1)` |

All XP gains scale with your pet's level — there's a +10% bonus per level above 1 applied to training, missions, and quests. Losing a battle awards 10% of normal XP. Failing a mission can cost XP and cause a level down.

---

## Specialization Stats

When you adopt a pet, it comes with two **specialization stats** — the two stats that species naturally excels at. These are baked into the species' base stat distribution and shown in gold on your pet card.

For example:
- **Cheetah** specializes in DEX + ATT — fastest attacker
- **Beaver** specializes in DEF + INT — tough and smart
- **Cardinal** specializes in HAP + DEX — happy and quick

Specializations also matter for equipment — if your Hat's bonus stats match both of your pet's specializations, you unlock the highest equipment multiplier tier.

---

## Rank Badges

Your pet earns a rank badge based on its level. A new rank unlocks every 50 levels — **ranks continue forever with no cap**. The rank number displayed in your pet card's tooltip always reflects your true rank.

The badge image shown uses one of 58 rank artwork tiers. Ranks 1–58 each have unique art. Once you pass rank 58 (level 2900+), the rank 58 "Beyond" artwork is displayed — but your actual rank number keeps climbing. There's no ceiling on how high your rank can go.

Your pet's badge is also a generated 512×512 image you can view separately:
- **Background** — your pet's type (Flying / Land / Swimming) emoji, enlarged to fill the canvas
- **Corners** — your primary element emoji in the top-left and bottom-right; your secondary element (if you have one) in the top-right and bottom-left
- **Center** — your species emoji, positioned based on type: Flying pets appear near the top, Swimming pets near the bottom, Land pets in the middle

---

## My Pet Page

The My Pet Page is your pet's homepage on the website. Everything you need to manage your pet lives here. You must be logged in with Discord to access it.

### The Pet Card

The top of the page shows your pet card at a glance:
- **Pet image** (species icon) on the left
- **Name, level badge, type icon, and element icon(s)** in the center
- **Rank badge** on the right (appears once you reach level 50)
- **XP progress bar** showing current XP vs XP needed for next level
- **Equipment slots** — icons for your equipped Material (×2), Gem (×2), Monster (×2), and Hat (×1). Empty slots show a placeholder icon.
- **Equipment bonus summary** — shows the total stat bonuses your equipment is currently providing, including the active multiplier
- **Stats grid** — all six stats (ATT, DEF, INT, DEX, HAP, ENE) with equipment bonuses shown in green next to each. Specialization stats are highlighted.
- **Combat stats row** — shows your computed ⚔️ ATK, 🛡️ DEF, and ❤️ HP values
- **Inventory** — a collapsible section below the stats showing all items you're holding, grouped by type

### The Action Tabs

Below the pet card is a row of action tabs. Click any tab to switch to that panel:

**🏋️ Train** — Send your pet to train and earn XP. Pick Easy, Average, or Hard difficulty, then click "Start Training." Higher difficulty means more XP but a lower success chance. There's a 5-second cooldown between uses. A level-up popup appears if your pet levels up.

**🗺️ Mission** — Send your pet on a mission for more XP and keys. Pick a difficulty, optionally enter a Gamble XP amount (risk XP for a bonus reward on success — you lose it on failure), then click "Launch Mission." Missions have a 5-second cooldown.

**🎮 Play** — Take your pet to a location to earn XP and keys. Click a location tile to select it (it highlights gold), then click "Go Play!" Matching your pet's element to the location gives 2× or 3× XP and better key drops. 5-second cooldown.

**🗡️ Quest** — AI-generated 5-stage quests. Select a location and difficulty, then click "Begin Quest." Each stage shows an event description and three choices — each choice is tied to a pair of your pet's stats (ATT/DEF, INT/DEX, or HAP/ENE). Your pet's stat level vs the required skill determines your success chance. Some stages can trigger a live battle if you fail a skill check. Quests have a 5-second cooldown to start.

**📦 Loot Market** — Spend keys to open chests. Click a chest tier to select it (highlighted gold), set the amount (1–10), then click "Open Chest." Chest 4 also asks you to pick a guaranteed item type (Material, Gem, Monster, Potion, or Hat) before opening.

**✏️ Rename** — Change your pet's name (up to 32 characters, alphanumeric + basic punctuation) and customize your three battle action labels (Attack, Defense, Charge). Fill in what you want and click "Save Changes."

**💀 Release Pet** — Permanently delete your pet. Type your pet's exact name in the confirmation box and click "Release Pet." This cannot be undone — all stats, inventory, and history are lost. You can adopt a new pet afterwards.

### Inventory Panel

The inventory collapsible on the pet card shows all items you're holding, grouped by category (Materials, Gems, Monsters, Hats, Potions, Keys). Each item shows its icon, name, count, and rarity color.

**To equip an item** (Material, Gem, Monster, or Hat): click the item in your inventory. A confirmation prompt appears — confirm to equip it. The item moves from your inventory to the equipment slot. If the slot is full, the oldest item is automatically returned to your inventory.

**To unequip an item**: click the equipped item icon in the equipment slots section of the pet card. It returns to your inventory.

**To use a potion**: click the potion in your inventory. A confirmation prompt appears showing what the potion does. Confirm to consume it — the effect is applied permanently to your pet's stats immediately. The potion is removed from your inventory.

Items stack up to 99 per type. If your inventory is full when you earn a new item, it converts to XP instead (`level × 100 XP` per overflow item).

---

## How Combat Works

Combat is turn-based. Each turn, every participant picks one of three actions simultaneously. Actions resolve at the same time.

**The three actions:**
- **Attack** — Deal damage to your target
- **Defend** — Reduce incoming damage and potentially reflect it back
- **Charge** — Build up a damage multiplier for a future attack

**Damage formula:**
1. Roll a d20 (1–20)
2. `Raw Attack = roll × (ATT + DEX)`
3. `Final Attack = Raw Attack × Charge Multiplier × Type Bonus × Element Bonus`
4. If target is **defending**: roll their d20, compute `Defense = roll × (DEF + INT)`, then `Damage = max(1, Final Attack − Defense)`. If defense exceeds attack, the excess becomes **parry damage** reflected back at the attacker.
5. If target is **charging**: `Damage = Final Attack × 1.25` (25% vulnerability bonus)
6. If target is **attacking**: `Damage = max(1, Final Attack)` (no reduction)

---

## The Three Actions

**Attack**
Rolls a d20 and multiplies by your `ATT + DEX`. The result is scaled by your charge multiplier and any type/element bonuses. If the target is also attacking, your full damage lands. If they're defending, their defense roll reduces it. If they're charging, they take 25% extra.

**Defend**
Rolls a d20 and multiplies by your `DEF + INT`. If your defense roll exceeds the attacker's attack roll, the excess becomes **parry damage** reflected back at them. Defending is most powerful against charged attacks — a well-timed defend can completely negate and punish a charge release.

**Charge**
Deals zero damage this turn but advances your charge multiplier along the progression: **1.0 → 2.0 → 3.0 → 4.0 → 5.0**. Your next attack uses the accumulated multiplier. While charging you take 25% extra damage from any attack that lands.

---

## The Charge Mechanic

Each turn you choose Charge instead of attacking, your multiplier advances:

| Charges Held | Multiplier |
|-------------|-----------|
| 0 (fresh) | 1.0× |
| 1 turn | 2.0× |
| 2 turns | 3.0× |
| 3 turns | 4.0× |
| 4 turns (max) | 5.0× |

A 5× charge can be devastating against an undefended target. But getting hit while charging deals 25% bonus damage to you, and a fully-defended parry reflects the excess back. Use charge when you know your opponent is attacking — not when they're likely to defend.

---

## Type & Element Advantages

Every pet has a **type** (category) and one or two **elements**. Both affect combat damage.

### Types (Categories)

There are three types forming a triangle:

| Attacker | Defender | Bonus |
|----------|----------|-------|
| Flying | Land | +15% damage |
| Land | Swimming | +15% damage |
| Swimming | Flying | +15% damage |

### Elements

There are 13 elements. Most deal **+10% damage** against specific weaknesses. Basic deals **−10% damage** against everything.

| Element | Strong Against | Weak To |
|---------|---------------|---------|
| Basic | Nothing (−10% vs all) | — |
| Fire | Ice, Plant, Necro | Water, Rock |
| Water | Fire, Rock, Air | Electric, Plant |
| Electric | Water, Plant, Fighting | Rock, Air |
| Ice | Air, Electric, Water | Fire, Rock, Fighting |
| Plant | Water, Air, Psychic | Fire, Ice, Necro |
| Rock | Electric, Fire, Ice | Water, Air, Holy |
| Air | Rock, Fighting, Electric | Ice, Water, Plant |
| Magic | Psychic, Fighting, Fire | Necro, Holy |
| Holy | Necro, Magic, Rock | Psychic, Fighting |
| Necro | Holy, Magic, Plant | Fire, Psychic |
| Psychic | Holy, Necro, Magic | Necro, Magic |
| Fighting | Ice, Psychic, Holy | Electric, Air, Magic |

**Dual elements:** If your pet has two elements, the game averages the bonuses from all attacker/defender element combinations. Dual-element pets are more versatile but rarely get the full +10% bonus.

---

## Equipment & Inventory

Equipment boosts your pet's stats permanently while equipped. You find equipment through battles, quests, activities, and chests. All items are managed from the inventory panel on your My Pet Page.

### Equipment Slots

| Slot | Max Equipped | Stat Bonuses |
|------|-------------|--------------|
| Material | 2 | ATT, DEF, DEX |
| Gem | 2 | INT, HAP, ENE |
| Monster | 2 | Mixed (varies) |
| Hat | 1 | Mixed (varies) |

### Equipment Multiplier System

Equipment bonuses scale based on how well you've built your loadout:

| Condition | Multiplier |
|-----------|-----------|
| Singles only (no pairs) | 1× |
| Any matching pair (e.g. 2× same Material) | 2× on that pair's items |
| Full Set (Material pair + Gem pair + Monster pair + Hat) | 3× on everything |
| Full Set + hat's bonus stats both match your pet's specializations | 4× on everything |

**Level bonus:** Every 50 levels adds +1 to the final multiplier. A level 100 pet with a full set gets 3 + 2 = **5×**. A level 150 pet with full set + both hat specs matching gets 4 + 3 = **7×**.

The optimal setup is two of the same Material, two of the same Gem, two of the same Monster, and a Hat whose bonus stats match your pet's specializations.

### Material Rarities

| Rarity | Examples | Bonus Range |
|--------|---------|-------------|
| Common | Dirt, Leaf, Sand | +1 to one stat |
| Uncommon | Bone, Fabric, Leather | +1–2 to multiple stats |
| Rare | Glass, Stone, Wood | +2–3 to multiple stats |
| Epic | Brick, Gold, Steel | +3–4 to multiple stats |
| Mythic | Laser, Plutonium, Smart | +4–5 to multiple stats |

### Potions

Potions are consumable items that permanently boost your pet's stats. Use them from the inventory panel on your My Pet Page — click the potion, confirm, and the effect applies instantly.

| Potion Type | Effect |
|-------------|--------|
| ATT/DEF/DEX/INT/HAP/ENE Potion | +3 to that specific stat |
| Elemental Potion (e.g. Fire Potion) | +5 to 3 random stats (single element pet) or +3 to 4 random stats (dual element) — only usable by matching element pets |
| S1 / S2 / S3 Potion | +1 / +2 / +3 to 2 random stats |
| Luck Potion | +1–5 to all 6 stats (random per stat) |
| Mega Potion | +10 to all 6 stats |
| Health Potion | +10 to HAP and ENE |
| Greater Health Potion | +15 to HAP and ENE |
| Lesser Health Potion | +5 to HAP and ENE |
| XP Potion | Grants `100 × level` XP |
| Lesser XP Potion | Grants `50 × level` XP |

---

## Activities

Activities are accessed from the **Play tab** on your My Pet Page. Select a location tile, then click "Go Play!" Your pet visits that location and earns XP and keys based on how well its element matches the location's specialty.

**Locations:** Camp, Bonfire, Beach, Forest, Hot Air Balloon, Cruiseship, Mountain, Gym, Graveyard, Festival, Glacier, Pyramids

| Element Match | XP Multiplier | Key Bonus |
|---------------|--------------|-----------|
| No match | 1× | 75% chance for 1 key |
| 1 element matches | 2× | Guaranteed 1 key + 25% chance for 1–2 more |
| Both elements match | 3× | Guaranteed 1 key + 50% chance for 1–2 more |

There's also a **5% chance** of a boss encounter during play. The boss is generated based on the location's elements and your pet's stats. Defeating it rewards 5× normal XP and one of each key type (Key1, Key2, Key3).

Play has a 5-second cooldown between uses.

---

## Keys & Chests

Keys drop from activities, quests, missions, and gambling win streaks. Spend them in the **Loot Market tab** on your My Pet Page — select a chest tier, set the amount, and click "Open Chest."

| Chest | Key Required | Loot |
|-------|-------------|------|
| Chest 1 | 1× Key1 | 1 Common or Uncommon item |
| Chest 2 | 1× Key2 | 1 Rare item |
| Chest 3 | 1× Key3 | 1 Epic item |
| Chest 4 | 1× Key1 + Key2 + Key3 | 1 item of your chosen type + 1 Uncommon or better |

**Mission key drops:**

| Difficulty | Keys |
|------------|------|
| Easy | 33% chance for Key1 |
| Average | Key1 + Key2 |
| Hard | Key1 + Key2 + Key3 |

**Race win streak keys:**

| Win Streak | Keys Awarded |
|------------|-------------|
| 1–2 wins | 1× Key1 |
| 3–5 wins | 1× Key2 |
| 6–8 wins | 1× Key3 |
| 9+ wins | 1× Key1 + Key2 + Key3 |

Race winnings multiply too: 3+ streak = 2× payout, 6+ streak = 4× payout, 9+ streak = 8× payout. Keys and XP are held as pending until you cash out — losing resets everything.

**Table game win streak keys (Blackjack, Craps, Hold'em):**

| Win Streak | Keys Awarded |
|------------|-------------|
| 1 win | 1× Key1 |
| 2 wins | 2× Key1 |
| 3 wins | 1× Key2 |
| 4 wins | 2× Key2 |
| 5 wins | 1× Key3 |
| 6 wins | 2× Key3 |
| 7+ wins | 3× Key1 + 3× Key2 + 3× Key3 (Jackpot!) |

**Slots key drops** (chance-based, not streak-based):

| Difficulty | Key Drop Chance |
|------------|----------------|
| Very Easy / Easy | 0% |
| Medium | 5% |
| Hard | 10% |
| Very Hard / Insanity | 20% |

---

## Tasks

Tasks are daily objectives that give you a concrete goal and reward you with **Keys or Chests** for completing them. Every player gets **5 task slots**, each holding a unique task generated just for you — no one else sees your tasks.

Open the **Tasks page** from the sidebar to view all five slots at a glance.

### How Tasks Work

Each task card shows:
- **What to do** — a short objective like *"Play with your pet 2 time(s)"* or *"Win 1 NPC battle(s)"*
- **Progress bar** — fills accurately as you complete the required actions
- **Reward** — the key or chest you'll receive on completion, shown upfront so you can decide if it's worth your time

Tasks track your actions automatically. Just do the thing — play, train, battle, open a chest, use a potion — and the bar updates in real time.

### Task Types

Tasks ask you to do **any pet interaction except Kill**, ranging from 1 to 5 repetitions depending on the action. Rarer or harder actions require fewer repetitions and reward better loot.

| Action | Count Range | Notes |
|--------|------------|-------|
| Play | 1–3 | Any location counts |
| Train | 1–3 | Any difficulty counts |
| Mission | 1–3 | Success required |
| Win NPC Battle | 1–2 | Must win; losses don't count |
| Complete Quest | 1–2 | Must finish successfully |
| Gift Item to Bazaar | 1 | Post any item to the Item Board |
| Win Boss Battle | 1 | Must survive to the end |
| Rename Action | 1 | See below |
| Use Potion | 1–3 | Any potion counts |
| Equip Item | 1–3 | Any equippable item counts |
| Open Chest | 1–2 | Any chest tier counts |
| Consume Item | 1–3 | Any consumable counts |

**Rename tasks** are phrased as *"Pet is tired of {action} — rename it"* where `{action}` is one of your three battle labels (Attack, Defense, or Charge). Go to the **Rename tab** on your My Pet page, update that specific action label, and save — the task completes and the bar fills automatically. You don't need to change your pet's name.

### Rewards

Each task has its reward shown on the card before you start. Rewards scale with how demanding the task is:

| Reward Tier | What You Can Get |
|-------------|-----------------|
| Low | 1× Key1, Key2, or Key3 |
| Mid | 1–2× Keys (mix of tiers), rare chance at Chest 1 |
| High | 2–3× Keys (higher tiers), chance at Chest 2 or Chest 3 |
| Top | 2–3× Keys or Chest 2 / Chest 3 / Chest 4 |

Boss battles and quests sit at the top tier. Gifting, missions, and NPC battles sit in the mid tier. Play, train, equip, and consume sit at the low tier. The reward is always shown on the card — you'll never be surprised.

### Opening Chest Rewards from Inventory

If a task rewards you a chest, it lands directly in your **inventory** on the My Pet page. Chests in your inventory **do not require keys to open** — they're already yours. Click the chest in your inventory panel to open it immediately. Chest 4 will ask you to pick an item type first (Material, Gem, Monster, Potion, or Hat), then opens with the same loot table as the Loot Market.

### Cooldowns

| Event | Cooldown |
|-------|---------|
| Task completed | 4 hours before a new task fills that slot |
| Task dismissed | 1 hour before a new task fills that slot |

You can dismiss any task you don't want by clicking **Dismiss** on its card. The slot goes on a 1-hour cooldown, then a fresh task appears. Completing a task triggers a 4-hour cooldown on that slot before the next one generates.

### DM Notifications

The Tasks page has a 🔔 bell button in the top-right corner. Click it to configure Discord DM notifications for when your task slots refresh:

| Mode | When You Get Pinged |
|------|-------------------|
| Off | Never |
| Each slot | Once per slot, as soon as it refreshes with a new task |
| All slots | Only when all 5 slots have refreshed — one single DM instead of five |

The **All slots** mode is recommended if you don't want to be spammed — you'll get one ping when everything is ready.

---

## The Floor (Multiplayer)

The Floor is the multiplayer hub where you challenge other players' pets directly. Open a lobby from the website, set the max number of opponents (1–9), and other players can join.

**Battle modes:**
- **1v1** — Two players, head to head
- **Free-For-All (FFA)** — 3+ players, last pet standing wins

**Relationship effects on damage:**

| Relationship | Damage Modifier |
|-------------|----------------|
| Friends (mutual) | Both deal 0.8× damage |
| Foe (mutual) | Both deal 1.2× damage |
| Enemy (mutual) | Both deal 1.5× damage |
| Best Friends | Cannot battle each other |

Relationships must be **mutual** to take effect. You can also create bracket tournaments (4, 8, or 16 players) — the organizer sets the size, players register, and matches run automatically.

**Boss Battles (multiplayer):**
- Best Friends fighting together: +25% damage
- Friends fighting together: +10% damage
- Foes fighting together: −15% damage
- Enemies cannot participate in the same boss battle

---

## The Pet Casino

The Pet Casino is a collection of XP-based gambling games accessible from the website. All bets are placed in XP — you win or lose XP based on the outcome. Winning streaks also reward keys.

---

## Slot Machine

Spin the reels and match symbols to win XP. Choose a difficulty and bet amount, then spin.

**Difficulties and payouts (net multiplier on bet):**

| Difficulty | 3-Match Payout | 2-Match Payout |
|------------|---------------|----------------|
| Very Easy | 8× | 0.5× |
| Easy | 15× | ~0.78× |
| Medium | 35× | ~1.33× |
| Hard | 168× | 3.33× |
| Very Hard | 1,061× | ~0.49× |
| Insanity | 2,500,000,000× (both reels) | 220,000× (both reels) |

Higher difficulty = fewer symbols = harder to match = bigger payout. Insanity mode uses dual reels — you need to match on both simultaneously. There's also a Fun mode with no XP changes.

Bet range: **10–100,000 XP**

---

## Pet Races

Race your pet against others (or bots) and bet XP on the outcome. Choose simulation mode (vs AI bots) or lobby mode (vs real players).

**Payout multipliers by difficulty:**

| Difficulty | Base Payout |
|------------|------------|
| Apprentice | 1.25× bet |
| Journeyman | 2.0× bet |
| Senior | 3.0× bet |

**Win streak multipliers stack on top:**

| Streak | Streak Multiplier |
|--------|-----------------|
| 1–2 wins | 1× |
| 3–5 wins | 2× |
| 6–8 wins | 4× |
| 9+ wins | 8× |

A Senior race with a 9+ win streak pays `bet × 3.0 × 8 = 24×`. Winnings accumulate as pending XP — you must **cash out** to receive them. Losing wipes all pending XP and keys.

Race speed is determined by your pet's DEX, ENE, and HAP stats using a logarithmic formula with randomness.

---

## Blackjack

Classic blackjack. Get closer to 21 than the dealer without going over. Play solo or with up to 3 AI bots. Betting or Fun mode available.

- Split hands (up to 4 hands total)
- Double down on 2-card hands (betting mode only)
- Ace = 11 (or 1 if it would bust you). Face cards = 10.

Win streaks reward keys. A 7+ win streak triggers a jackpot key drop.

---

## Craps

Roll dice and bet on outcomes. Choose your dice color (Red, Orange, Blue, Yellow, Pink, Green, Purple, or Random).

**Available bets:**

| Bet | How to Win |
|-----|-----------|
| Pass Line | Roll 7 or 11 on come-out, or hit your point before rolling 7 |
| Don't Pass | Opposite of Pass Line |
| Field | Roll 2, 3, 4, 9, 10, 11, or 12 (one roll) |
| Place 4–10 | Roll that number before a 7 |
| Any 7 | Roll a 7 (one roll) |
| Hard 4/6/8/10 | Roll the hard way (doubles) before a 7 or easy version |

---

## Texas Hold'em

Full Texas Hold'em poker with XP as the bankroll. Set a buy-in amount, add 0–3 AI bots, and play through Pre-deal → Pre-flop → Flop → Turn → River. Actions each round: Bet/Raise, Call/Check, or Fold. The AI bots use real poker logic.

---

## Mini-Games

Quick mini-game activities embedded in quests:

- **Mimic Chests** — During quests, some chests are mimics. Choosing the ATT/DEF option lets you fight it for double loot. Other choices mean you escape with nothing.
- **Hostile Pet Encounters** — Scare off or evade enemy pets during quests. Fail the skill check and you fight a live turn-based battle directly in the quest panel.
- **Boss Encounters** — 5% chance during Play to trigger a boss fight for big rewards.

---

## Survivor Series

Survivor Series is a web-based battle royale where your pet competes against other players' pets and AI opponents in a shared arena. Rounds fire automatically every 15 minutes.

### Starting a Game

- Open the **Survive** page. If a lobby is open, click **⚔️ Join Game**.
- Once at least 2 real players have joined, any player can click **🚀 Start Game** to begin a 15-minute countdown.
- NPCs are added immediately when the game is started and appear on the map.
- When the countdown ends, **Round 1 fires immediately**. Every subsequent round fires 15 minutes after the previous one.
- Your custom battle action names (set via the Rename tab on My Pet) are used in all round narratives.

### The Arena Map

The map fills the page and is always visible when a game is active or in the lobby. It's divided into 12 elemental zones — each with a unique animated terrain:

| Zone | Visual Theme |
|------|-------------|
| Fire | Molten lava floor, rising flame particles with hot white cores |
| Water | Deep ocean with caustic light patterns, flowing stream particles |
| Ice | Frozen lake with hexagonal crystal grid, falling 6-pointed snowflakes |
| Plant | Dense forest floor with dappled light, swaying grass blades |
| Air | Open sky with volumetric cloud layers, drifting cloud puffs |
| Electric | Storm cell with branching lightning tree, plasma spark particles |
| Magic | Arcane ritual circle with pentagram and rune dial, rising glowing motes |
| Holy | Divine light with god rays and marble floor, golden light motes with cross sparkles |
| Necro | Near-black void with spectral fog and bone fragments, drifting soul wisps |
| Fighting | Dojo tatami mat with center combat ring, random comic impact bursts (POW! BAM!) |
| Rock | Stone quarry with strata layers and mineral veins |
| Basic | Worn cobblestone courtyard, slow drifting dust motes |

**Map controls:**
- **Scroll** to zoom, **drag** to pan, **⟳ Fit** to reset the view
- **Filter buttons** — All / Players / NPCs / Alive / Eliminated / Relationships
- **Relationships filter** — click a pet icon first, then switch to Relationships to see only that pet and everyone they have a relationship with. Colored lines show the type: gold = Best Friend, green = Friend, orange dashed = Foe, red dashed = Enemy
- **Click any pet icon** to open their detail panel showing Survive Score, kill count, who eliminated them, and a full round-by-round activity feed

**Stats bar** (above the map) shows alive count, eliminated count, the alive/eliminated progress bar, player/NPC breakdown, and the countdown to the next round.

### Survive Score

`Survive Score = level ÷ equipment_multiplier ÷ 10`

This is the core stat for both movement decisions and combat. Higher level = higher score = stronger. Higher equipment multiplier = lower score = weaker. **Equipment hurts you in the Survivor Series** — the multiplier divides your score.

| Example | Level | Multiplier | Survive Score |
|---------|-------|-----------|--------------|
| No equipment | 500 | 1 | 50.0 |
| Full set, level 50 | 500 | 13 | ~3.8 |
| Level 100 bonus | 100 | 1 | 10.0 |

The equipment multiplier is calculated exactly as on the My Pet page:
- No pairs, no full set → **1×** (+ level bonus)
- Full set (Material pair + Gem pair + Monster pair + Hat) → **3×** (+ level bonus)
- Full set + both hat bonus stats match your pet's specializations → **4×** (+ level bonus)
- Every 50 levels adds **+1** to the multiplier

### Charge System

Every round a pet avoids combat, they build up a **charge stack** (max 5). This is shown in the Live Feed as `[Charge ×1.3]` and uses your pet's custom Charge action name in the narrative.

| Rounds Without Combat | Charge Multiplier |
|----------------------|------------------|
| 0 | 1.0× |
| 1 | 1.1× |
| 2 | 1.2× |
| 3 | 1.3× |
| 4 | 1.4× |
| 5+ (cap) | 1.5× |

When a pet fights, their charge multiplier is applied to their Elimination Score for that combat, then **reset to 0**. A pet that has avoided combat for 5 rounds hits with 1.5× their normal combat power. Pets with high charge stacks show increasingly dramatic narrative lines — "radiates barely-contained energy" at 3+ stacks.

### Combat Resolution

**Elimination Score** (used only in combat, not movement):

`Elimination Score = Survive Score × 1.2^advantages × 0.8^disadvantages × charge_multiplier`

Each type or element advantage multiplies by **1.2×**, each disadvantage by **0.8×**. Advantages are counted across 5 axes: type triangle, primary vs primary element, element2 vs primary, primary vs element2, element2 vs element2.

Win probability = ratio of elimination scores, clamped **5%–95%**. When scores are within 15% of each other, the probability compresses toward 50% — close fights are genuinely tense. Both pets fight simultaneously; the winner is determined by who has the higher final score.

**Action selection in eliminations:**
- **Winner** — releases their Charge action if they had stacks; otherwise uses Attack (if ATT ≥ DEF) or Defend (if DEF > ATT)
- **Loser** — uses Defend (parry attempt, `_PARRY_SUCCESS_THEN_BREAK` narrative) if DEF > ATT; otherwise uses Attack (`_PARRY_FAIL` narrative)
- All action names use your **custom saved labels** from the Rename tab first, then species defaults, then element/category fallbacks

### Movement Rules (per round)

Each pet chooses a zone to move to based on this priority order:

1. **Enemies** — always chase, always fight regardless of anything else
2. **Best Friends** — stay in the same zone while more than 10% of pets remain
3. **Dominant pets** (Survive Score > 2× median) — actively hunt the weakest stranger in range
4. **Flee** — score-gap-weighted flee from stronger strangers; boldness from kills (×0.15 per kill, cap 0.75) reduces flee chance
5. **Foes** — roam preferred zones freely, no avoidance
6. **Friends** — avoid their zones while more than 25% of pets remain
7. **Default** — element-preferred zones, weighted toward top preference

### Encounter Chances

When multiple pets share a zone, an encounter may or may not happen:

| Relationship | Encounter Chance |
|-------------|-----------------|
| Enemies | 100% (always fight) |
| Foes | 80% |
| Strangers (3+ in zone) | 68% |
| Strangers (2 in zone) | 55% |
| Friends | 25% |
| Best Friends | 10% |

A dominant pet (score > 1.5× opponent) adds +15% to encounter chance. If no encounter happens, the pet gets a solo action line and their charge stack increments.

### Group Combat

Pets can fight in groups when relationships allow it:
- **Strangers/enemies/foes** — 1v1 only
- **Friends** — up to 2v2
- **Best Friends** — up to 4v4

Group combat uses the average elimination score of each side vs the strongest representative of the opposing side.

### Best Friend Victory

If 2–4 Best Friends are the last pets standing, they have a chance at **shared victory**:
- 2 BFs remaining: 60% chance
- 3 BFs remaining: 40% chance
- 4 BFs remaining: 25% chance
- If this exact group previously shared a group elimination together: **100% chance**

All surviving Best Friends are declared co-champions.

### Live Feed

Every action and elimination is broadcast in real time. Solo action lines show the pet's action name, location, and behaviour context. Elimination lines include the opener, action names, element/type advantage lines, relationship closing, score-gap commentary, and kill-count flavour. When no game is active, the feed shows the last game's full round-by-round history.

### XP Rewards

All real players earn XP at game end:

`XP = (rounds_survived × 10 + kills × 25) × max(1, level ÷ 5 + 1)`

Winner also gets: `+200 × max(1, level ÷ 5 + 1)`

---

## Pet Stock Market

The Pet Stock Market is a web-based XP investment system. Buy and sell tokens representing pet types and elements, with prices updating every 15 minutes.

**Tokens available:**
- 3 type tokens: Land, Swimming, Flying (base price: 250 XP each)
- 13 element tokens: Basic, Fire, Water, Electric, Ice, Plant, Rock, Air, Magic, Holy, Necro, Psychic, Fighting (base price: 500 XP each)

**Buying:** Costs XP from your pet. Non-matching tokens cost more:
- Token matches your pet's type or element: **1× price**
- Token doesn't match, single-element pet: **2× price**
- Token doesn't match, dual-element pet: **3× price**

Buying deducts XP directly — your pet can level down if you spend enough.

**Selling:** Always at the current market price with no multiplier. Selling adds XP to your pet and can trigger level-ups.

**Price dynamics (every 15 minutes):**
- Random drift: elements ±20%, types ±12% per tick
- 10% chance of a momentum spike adding extra ±12% volatility
- Buy pressure pushes prices up; sell pressure pushes them down
- Market events fire regularly — Minor events every tick, Major events on 85% of days (active for 2–8 hours), Holiday events on special dates

Track your P&L from the market page — it shows XP spent, XP received from sells, unrealised value of held tokens, and net profit/loss.
