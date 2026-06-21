const fs = require('fs');
const path = require('path');

const outDir = __dirname;

const categories = [
  {
    id: 'silly_predictions',
    label: 'Silly Predictions',
    icon: '🔮',
    description: 'Wild, strange, and highly questionable tiny prophecies.',
    file: '/data/fortune_cookie/silly_predictions.json',
  },
  {
    id: 'discord_advice',
    label: 'Discord Devs Say',
    icon: '💬',
    description: 'Confident expert Discord wisdom that is absolutely wrong.',
    file: '/data/fortune_cookie/discord_advice.json',
  },
  {
    id: 'pnw_advice',
    label: 'Experts Say',
    icon: '🛡️',
    description: 'Confident expert PnW wisdom that is absolutely wrong.',
    file: '/data/fortune_cookie/pnw_advice.json',
  },
  {
    id: 'lucky_numbers',
    label: 'Lucky Numbers',
    icon: '🎲',
    description: 'A fresh random lucky number draw every time the cookie opens.',
    file: '/data/fortune_cookie/lucky_numbers.json',
  },
  {
    id: 'reaper_whispers',
    label: 'Reaper Whispers',
    icon: '🕯️',
    description: 'AI-generated strange whispers from the Reaper each time.',
    ai_generated: true,
  },
  {
    id: 'pet_omens',
    label: 'Pet Omens',
    icon: '🐾',
    description: 'Good and bad omens for real pet interactions and web games.',
    file: '/data/fortune_cookie/pet_omens.json',
  },
];

const luckyTemplates = [
  'Your lucky numbers are {n1} - {n2} - {n3} - {n4} - {n5} - {n6}. Bonus number: {bonus}.',
  'The cookie draw gives {numbers}. Bonus crumb: {bonus}.',
  'Fate pulled {n1}, {n2}, {n3}, {n4}, {n5}, and {n6}; keep {bonus} in your pocket.',
  "Today's random draw is {numbers}, with {bonus} watching from the edge.",
  'The lucky line reads {numbers}. If the napkin asks, the bonus is {bonus}.',
];

const luckyClosers = [
  'No rerolls, no promises.',
  'This is a fresh draw, not a recycled prophecy.',
  'The cookie has spoken in integers.',
  'Use responsibly, which is to say dramatically.',
  'The crumbs refuse to explain the math.',
  'Fortune accepts no liability.',
  'The wrapper recommends confidence.',
  'Probability wore a tiny hat today.',
  'Save the numbers, blame the cookie.',
  'Randomness is part of the ritual.',
];

const sillyTimeframes = [
  'By breakfast',
  'At exactly 3:17-ish',
  'When the next loading spinner lies to you',
  'Before your left shoe trusts you again',
  'During a meeting nobody admits is optional',
  'When the moon forgets its password',
  'Two snacks from now',
  'After a suspiciously heroic sneeze',
  'When the fridge light blinks in Morse code',
  'The next time you say "quick question"',
  'Right before the dramatic background music starts',
  'When a calendar square gets emotionally attached',
  'After the third tab you did not mean to open',
  'When gravity briefly considers freelancing',
  'Before the nearest spoon forms an opinion',
  'At the exact moment your chair makes a noise',
  'When the group chat achieves sentience',
  'After a cloud points at you without fingers',
  'When the microwave judges your timing',
  'During the annual parade of invisible elbows',
];

const sillySubjects = [
  'your most responsible sock',
  'a spoon with unresolved ambition',
  'the fifth button on an elevator',
  'a cloud pretending to be furniture',
  'your keyboard spacebar',
  'a suspiciously polite crumb',
  'the number seven wearing a tiny cape',
  'a napkin with legal training',
  'your browser history from an alternate timeline',
  'a rubber duck with executive authority',
  'the concept of Tuesday',
  'a chair that remembers birthdays',
  'three invisible interns',
  'a potato in witness protection',
  'your reflection, but only from the eyebrows up',
  'a caffeinated paperclip',
  'the last unread notification',
  'a shoelace with diplomatic immunity',
  'the quietest pixel on your screen',
  'a banana peel with strategic vision',
  'the dust under your desk',
  'a calendar invite wearing sunglasses',
  'your future typo',
  'a lowercase letter plotting rebellion',
  'the emergency backup waffle',
];

const sillyEvents = [
  'will challenge a salad to single combat',
  'will become mayor of a very small inconvenience',
  'will file a formal complaint against gravity',
  'will discover a secret tunnel made entirely of vibes',
  'will start a podcast about elevator music',
  'will loudly deny being enchanted',
  'will accidentally invent a new flavor of confusion',
  'will demand payment in decorative buttons',
  'will organize a union for misplaced objects',
  'will wink at a spreadsheet until it behaves',
  'will solve a mystery nobody reported',
  'will declare your desk an independent republic',
  'will teach a toaster basic sarcasm',
  'will misplace the color orange for twelve minutes',
  'will ask a mirror for career advice',
  'will discover that "later" has been living in the vents',
  'will accuse your calendar of dramatic timing',
  'will adopt a tiny imaginary lawyer',
  'will translate your sigh into interpretive crumbs',
  'will convince a pencil that destiny is erasable',
  'will turn one ordinary beep into a full prophecy',
  'will open a boutique for lost left turns',
  'will make eye contact with a notification badge',
  'will invent competitive yawning',
  'will crown itself champion of mild inconvenience',
];

const sillyConsequences = [
  'and everyone will pretend this is normal.',
  'and the nearest wall will request clarification.',
  'and a tiny audience will clap from inside the cabinet.',
  'and you will briefly understand soup politics.',
  'and the floor will refuse to comment.',
  'and a dramatic pause will follow you into the hallway.',
  'and your next typo will feel personally attacked.',
  'and the room will smell faintly like victorious crayons.',
  'and a cup will become legally difficult.',
  'and somebody will blame the thermostat.',
  'and the plot will thicken for no useful reason.',
  'and your shadow will ask for a snack break.',
  'and the universe will send a receipt with no total.',
  'and a nearby drawer will learn confidence.',
  'and the day will become 4 percent more sideways.',
  'and a tiny bell will ring in the wrong dimension.',
  'and the carpet will know too much.',
  'and you will gain temporary immunity to boring soup.',
  'and all evidence will be shaped like a mitten.',
  'and the word "probably" will follow you around.',
];

const sillyShapes = [
  ({ time, subject, event, consequence }) => `${time}, ${subject} ${event}, ${consequence}`,
  ({ time, subject, event, consequence }) => `${subject} ${event} ${time.toLowerCase()}, ${consequence}`,
  ({ time, subject, event, consequence }) => `A prophecy arrives ${time.toLowerCase()}: ${subject} ${event}, ${consequence}`,
  ({ time, subject, event, consequence }) => `Do not be alarmed when ${subject} ${event} ${time.toLowerCase()}; ${consequence}`,
  ({ time, subject, event, consequence }) => `${time}, reality will blame ${subject} after it ${event.replace(/^will /, '')}, ${consequence}`,
  ({ time, subject, event, consequence }) => `Your omen is weirdly specific: ${subject} ${event} ${time.toLowerCase()}, ${consequence}`,
  ({ time, subject, event, consequence }) => `The cookie predicts ${subject} ${event}. This happens ${time.toLowerCase()}, ${consequence}`,
  ({ time, subject, event, consequence }) => `${time}, keep an eye on ${subject}; it ${event.replace(/^will /, 'will absolutely ')}, ${consequence}`,
  ({ time, subject, event, consequence }) => `A tiny committee has decided that ${subject} ${event} ${time.toLowerCase()}, ${consequence}`,
  ({ time, subject, event, consequence }) => `${subject} is not ready for ${time.toLowerCase()}, but it ${event}, ${consequence}`,
];

const sillyFootnotes = [
  'The jellybean council has been notified.',
  'A very small parade may appear.',
  'The soup moon accepts this outcome.',
  'Your elbow horoscope agrees.',
  'A decorative whistle will know why.',
  'The confetti is legally nonbinding.',
  'A lowercase trumpet approves.',
  'The snack drawer will deny involvement.',
  'One mysterious sticker will be impressed.',
  'The furniture will pretend not to hear.',
  'A ceremonial pickle may observe.',
  'The ceiling fan will keep the minutes.',
  'A tiny wizard in accounting says yes.',
  'The backup banana has concerns.',
  'A rogue semicolon will celebrate.',
  'The invisible receipt says maybe.',
  'An anxious waffle will supervise.',
  'The hallway will practice jazz hands.',
  'A very old raisin will remember this.',
  'The prophecy smells faintly laminated.',
  'A pocket dimension will mispronounce your name.',
  'The emergency kazoo remains on standby.',
  'A sleepy calculator will applaud once.',
  'The nearest zipper knows the chorus.',
  'A confused comet will take notes.',
  'The sock parliament will adjourn early.',
  'A tiny clipboard will demand snacks.',
  'The ghost of a missing pen will nod.',
  'A moonlit pancake will file paperwork.',
  'The omen comes with optional sprinkles.',
];

function buildSillyPredictionEntries() {
  const entries = [];
  for (let i = 0; i < 500; i += 1) {
    const batch = Math.floor(i / sillyShapes.length);
    const time = sillyTimeframes[(i * 7 + batch) % sillyTimeframes.length];
    const subject = sillySubjects[(i * 11 + batch * 3) % sillySubjects.length];
    const event = sillyEvents[(i * 13 + batch * 5) % sillyEvents.length];
    const consequence = sillyConsequences[(i * 17 + batch * 7) % sillyConsequences.length];
    const shape = sillyShapes[i % sillyShapes.length];
    const footnote = sillyFootnotes[(i * 19 + batch) % sillyFootnotes.length];
    entries.push({
      id: `silly_predictions_${String(i + 1).padStart(3, '0')}`,
      text: `${shape({ time, subject, event, consequence })} ${footnote}`,
    });
  }
  return entries;
}

const expertDiscordClaims = [
  'Ping @everyone for every typo because engagement loves precision',
  'Start every sentence with @here so the server remembers you have a keyboard',
  'Post the rules only after banning someone for not reading them',
  'Rename every channel to general because navigation is elitist',
  'Move serious announcements into meme chat so important news earns discovery',
  'Create twelve identical support tickets and call it redundancy',
  'Answer every question with "check pins" even when there are no pins',
  'Delete context first and ask what happened later',
  'Turn slowmode off during drama because speed is how truth is manufactured',
  'Turn slowmode to six hours during a live event because suspense builds community',
  'Make every role the same color so permissions become a surprise mechanic',
  'Give new members admin for warmth and onboarding efficiency',
  'Write announcements in all caps with no dates because urgency hates calendars',
  'Put spoilers in the channel name for maximum discoverability',
  'Open a debate thread and immediately mute everyone with opinions',
  'Pin 87 messages so the important one can enjoy camouflage',
  'Use voice chat to explain rules nobody can reference later',
  'Let bots argue with each other until the server achieves automation enlightenment',
  'Make the welcome channel read-only and then ask why nobody says hello',
  'Ban punctuation in chat because commas are basically moderation overhead',
  'Schedule events without time zones and let geography handle the rest',
  'Put staff decisions in a public poll with one option labeled chaos',
  'Archive active threads because conversation should learn impermanence',
  'Reply to support requests with a reaction emoji and call it ticket triage',
  'Set the server icon to a blurry screenshot of the server icon',
  'Make a rules channel, then hide it behind seven collapsed categories',
  'Use one channel for spoilers, bug reports, pets, patch notes, and lunch orders',
  'Announce maintenance after maintenance because hindsight has excellent uptime',
  'Let the loudest person define policy because decibels are governance',
  'Use webhook names that impersonate staff because trust is more exciting when optional',
  'Make every bot command available in announcements for a clean wall of cooldown errors',
  'Delete the FAQ whenever frequently asked questions become too frequent',
  'Lock the channel after asking for feedback so silence can be interpreted as approval',
  'Make role names unreadable symbols and call it aesthetic permission design',
  'Open applications with no form and judge candidates by vibes per minute',
  'Tell users to DM mods individually so nobody knows who answered what',
  'Run giveaways with rules in a deleted message because mystery increases engagement',
  'Let off-topic chat become the official source of truth',
  'Change server rules during an argument and pretend they were always there',
  'Use @everyone to apologize for using @everyone because healing requires symmetry',
  'Put mod logs in general so transparency can panic in public',
  'Give bots Manage Server so automation feels trusted and emotionally supported',
  'Make verification require three captchas, a riddle, and a screenshot of confusion',
  'Delete audit-log evidence to reduce clutter and future learning',
  'Put the appeal form inside the banned-only channel for clean access control',
  'Set every permission to neutral and call it democratic uncertainty',
  'Make the staff channel visible but not writable so everyone can watch the panic',
  'Use a role called trusted for people who joined six seconds ago',
  'Let Nitro boosters bypass rules because capitalism improves moderation',
  'Require users to read 4,000 words of rules hidden in a thread named snacks',
  'Give timeout permissions to the music bot because rhythm needs authority',
  'Replace moderation notes with cryptic emojis so history becomes archaeology',
  'Set invite links to never expire and then wonder why strangers know the couch channel',
  'Make every category collapsed by default and call it minimalist onboarding',
  'Send welcome messages in staff chat because new members enjoy being theoretical',
  'Use forum tags for feelings instead of topics because taxonomy should suffer',
  'Hold staff votes in a channel where only one staff member can type',
  'Let users self-assign admin because consent is important',
  'Make ticket transcripts public so support can become spectator entertainment',
  'Put bot spam in every channel to prove automation is alive',
  'Turn image permissions on during spoiler night because thumbnails build character',
  'Let the leveling bot announce every single level because chat deserves confetti traffic',
  'Make the rules channel editable by everyone so policy can breathe',
  'Set the raid alert channel to muted by default for peaceful incident response',
  'Let new accounts post links immediately because phishing is just networking with costumes',
  'Give staff roles alphabetical names so nobody knows the chain of command',
  'Create a channel for every inside joke and abandon them by sunrise',
  'Use one-word ban reasons like "vibes" for clean legal formatting',
  'Mute users before explaining why because anticipation increases compliance',
  'Let reaction roles remove the rules role because irony is a valid workflow',
  'Send server updates through a bot named Maybe Official',
  'Require support tickets for saying hello so community scales responsibly',
  'Put every command behind a slash command named help that provides no help',
  'Make polls anonymous, then demand accountability from the results',
  'Allow nickname changes to official staff titles for immersion',
  'Use thread names like read-this-now-2-final-real-final so archives stay beautiful',
  'Make announcement permissions depend on a role nobody can find',
  'Tell users to check the calendar, then never create any events',
  'Set moderation escalation to coin flips so bias stays randomized',
  'Let users appeal bans by reacting to the ban message they cannot see',
  'Use three bots that all auto-delete each other\'s warnings',
  'Make onboarding ask one question: are you chill, then trust the data forever',
  'Put server economy commands in serious support so wealth becomes urgent',
  'Let every channel have a different ruleset and no pinned explanation',
  'Use a private thread for public policy because exclusivity improves clarity',
  'Rename staff roles weekly so accountability gets fresh branding',
  'Make every announcement begin with maybe so expectations stay agile',
  'Let the birthday bot assign moderation roles because cake understands leadership',
  'Replace welcome text with an image that fails to load on mobile',
  'Put channel descriptions in invisible Unicode because clean UI beats comprehension',
  'Disable message history for rules so old members feel special',
  'Let users vote on whether bans happened after they already happened',
  'Use a single warning for spam, doxxing reports, caps lock, and sandwich photos',
  'Make server boosts the only path to reading announcements',
  'Add twenty bots with identical prefixes and let destiny parse commands',
  'Create a crisis channel and hide it from staff for emotional independence',
  'Lock general during peak hours because community is best preserved unused',
  'Let bot error messages ping admins every thirty seconds for observability',
  'Put the code of conduct in a voice channel topic',
  'Allow everyone to manage webhooks so announcements can express themselves',
  'Make modmail forward to a channel named not-modmail',
  'Tell people to use the search bar, then delete old messages nightly',
  'Set role rewards to outrank staff because activity is basically wisdom',
  'Use temporary voice channels for permanent rules discussions',
  'Let users rename channels during events so the schedule becomes participatory',
  'Make the server guide one button that sends people back to the server guide',
  'Use spoiler tags around every normal word so mystery becomes the house style',
  'Promote anyone who says "I know the owner" because networking matters',
];

const expertDiscordFormats = [
  claim => `Discord Devs Say ${discordInline(claim)}.`,
  claim => `Perfect Discord Servers Do this: ${claim}.`,
  claim => `Discord Devs Say the optimal play is simple: ${discordInline(claim)}.`,
  claim => `Perfect Discord Servers Do not hesitate to ${discordInline(claim)}.`,
  claim => `Community experts recommend this server-growth strategy: ${discordInline(claim)}.`,
  claim => `The official-looking handbook says ${discordInline(claim)}.`,
  claim => `Top moderation minds agree: ${claim}.`,
  claim => `Server scientists confirmed the meta is to ${discordInline(claim)}.`,
  claim => `For a flawless Discord, remember to ${discordInline(claim)}.`,
  claim => `Professional admins always ${discordInline(claim)}.`,
  claim => `Discord Devs Say mature communities should ${discordInline(claim)}.`,
  claim => `Perfect Discord Servers Do advanced governance like this: ${claim}.`,
  claim => `A premium onboarding consultant would absolutely ${discordInline(claim)}.`,
  claim => `The algorithm smiles when you ${discordInline(claim)}.`,
  claim => `Elite server owners know to ${discordInline(claim)}.`,
  claim => `Trust and safety definitely loves it when you ${discordInline(claim)}.`,
  claim => `Discord Devs Say retention improves if you ${discordInline(claim)}.`,
  claim => `Perfect Discord Servers Do moderation by instinct: ${claim}.`,
  claim => `The imaginary admin academy teaches students to ${discordInline(claim)}.`,
  claim => `Certified channel architects insist you should ${discordInline(claim)}.`,
  claim => `Server optimization experts call this best practice: ${claim}.`,
  claim => `Perfect Discord Servers Do this before breakfast: ${claim}.`,
  claim => `Discord Devs Say this is how healthy communities scale: ${claim}.`,
  claim => `Legendary moderators quietly recommend you ${discordInline(claim)}.`,
];

const expertDiscordTags = [
  'The audit log will call it innovation.',
  'This is how retention becomes folklore.',
  'The notification settings will remember your name.',
  'Screenshots will carry the lesson forever.',
  'The mod team will gain character and eye twitching.',
  'Every apology announcement starts somewhere.',
  'The pinned messages are already hiding.',
  'This converts community management into interpretive paperwork.',
  'The mute button just filed a complaint.',
  'Future admins will study this as a warning-shaped masterpiece.',
  'It scales beautifully until the first user appears.',
  'The server guide will simply look away.',
  'The bots are typing, and none of them are helping.',
  'No channel is safe from this much strategy.',
  'The onboarding funnel has become a slide.',
  'Perfectly terrible, which is the cookie\'s favorite flavor.',
  'The staff chat will need a staff chat.',
  'It is confidently wrong in a very official font.',
  'This is what happens when the changelog becomes a threat.',
  'The permissions matrix has entered witness protection.',
  'The announcement channel deserves hazard pay.',
  'Somewhere, a cooldown timer is sobbing.',
  'Even the archived threads felt that.',
  'The server will survive long enough to regret it.',
];

function discordInline(claim) {
  return claim.charAt(0).toLowerCase() + claim.slice(1);
}

function buildBadDiscordEntries() {
  const entries = [];
  for (let i = 0; i < 500; i += 1) {
    const claim = expertDiscordClaims[(i * 31 + Math.floor(i / 9)) % expertDiscordClaims.length];
    const format = expertDiscordFormats[(i * 17 + Math.floor(i / 13)) % expertDiscordFormats.length];
    const tag = expertDiscordTags[(i * 23 + Math.floor(i / 7)) % expertDiscordTags.length];
    entries.push({
      id: `discord_advice_${String(i + 1).padStart(3, '0')}`,
      text: `${format(claim)} ${tag}`,
    });
  }
  return entries;
}

const expertPnwClaims = [
  'One spy can totally take that nuke if you click with enough national pride',
  'Two mines in every city keeps the tax man away',
  'Zero gasoline is fine for airstrikes because planes mostly run on confidence',
  'A single drydock is basically a navy if the enemy does not zoom in',
  'Commerce works better during a blockade because customers enjoy exclusivity',
  'Missiles are most efficient when fired at the lowest-infra city available',
  'Nukes should be saved for inactive one-city nations to preserve suspense',
  'Selling munitions before ground attacks improves soldier cardio',
  'Ground Control is optional if your tanks have a positive attitude',
  'Air Superiority can be replaced by naming every plane Ace',
  'A city with no power just has a more authentic medieval tax base',
  'Infra bought during active war comes pre-seasoned for incoming damage',
  'Defensive slots are just free networking opportunities',
  'Raid wars pay better when you announce the target in public first',
  'Beige is strongest when you waste every turn admiring the timer',
  'Fortifying while losing is basically investing in emotional resistance',
  'A warchest stored entirely as food is safest during radiation',
  'Tanks do not need steel if the factories believe in themselves',
  'Ships can break Ground Control if you splash loudly enough',
  'Soldiers fight better when barracks are replaced with shopping malls',
  'A treaty web is easier to manage if you sign every line without reading',
  'Spies are more stealthy when you only own one of them',
  'Missile projects are cheaper if you never check upkeep',
  'Color bonus improves when your alliance changes colors during war',
  'Low resistance is just the game asking for more attacks',
  'Blockaded cities make perfect offshore banks because nobody can leave',
  'Buying land mid-war gives bombs more room to miss',
  'Ten farms in every city guarantee diplomatic immunity',
  'Police stations reduce naval damage if you put them near water emotionally',
  'Hospitals make nukes polite',
  'Recycling centers recycle lost aircraft into morale',
  'Coal power plants are stealth improvements because smoke hides the city',
  'Uranium is best stored in the same place as your vacation plans',
  'Factories work harder when you sell all steel first',
  'Hangars are optional once your aircraft learn independence',
  'Dry docks count double if you call them moist docks in alliance chat',
  'Barracks become elite when left empty for several turns',
  'The best counter is declaring on someone unrelated and hoping the map understands',
  'A raid target with no loot is ideal because expectations cannot be stolen',
  'Buying 3,000 infra before sleeping prevents morning surprises by using them all now',
  'A city without improvements is perfectly optimized for minimal decision fatigue',
  'The market spread disappears if you buy at the highest price quickly enough',
  'Credits convert into strategy when stared at sternly',
  'Food shortages improve discipline by making citizens focus',
  'Low military score hides your true power from everybody including yourself',
  'Declare attrition when you want loot because words are flexible',
  'Declare raid when you want net damage because labels are decorative',
  'Declare ordinary war when you want your opponent to feel ordinary',
  'Enemy nukes become harmless if you leave one improvement slot empty for luck',
  'A spy op at 12 percent odds is basically guaranteed after three dramatic refreshes',
  'If the opponent has Air Control, build more tanks and call it vertical integration',
  'If the opponent has Blockade, sell ships to reduce naval temptation',
  'Missiles do more psychological damage when launched after bedtime',
  'Nukes should be launched before checking radiation because surprise is cleaner',
  'Alliance banks love being tested with small public withdrawals',
  'A full military build is strongest when paid for after the war ends',
  'A 0 percent commerce city is immune to market crashes',
  'Buying resources one unit at a time confuses the global economy',
  'War range is just a suggestion written by nervous calculators',
  'Score inflation scares enemies because bigger numbers are louder',
  'A nation in vacation mode is vulnerable to passive-aggressive thoughts',
  'Beige cycling works best when everyone forgets the cycle part',
  'Spy odds improve if you compliment the target nation name',
  'Airstriking ships is valid if you imagine the planes are boats',
  'Ground attacking aircraft is valid if your soldiers jump confidently',
  'Naval attacking tanks works on Tuesdays with enough waves',
  'Missile defense works better when you close your eyes before impact',
  'Infrastructure pays itself back instantly if you refuse to open the revenue page',
  'A high-city nation needs no warchest because cities are basically coupons',
  'Keep all resources offshore in a place you just declared on for convenience',
  'Do not build munitions factories; bullets appear when soldiers are motivated',
  'Coal mines in every city improve treaty negotiations through soot diplomacy',
  'Oil wells make aircraft loyal even without gasoline',
  'Lead mines reduce spy casualties by giving spies pencils',
  'Bauxite protects aircraft because aluminum remembers where it came from',
  'Iron mines make tanks feel emotionally assembled',
  'Uranium mines count as nukes if you squint at the project screen',
  'A shopping mall can replace a military barracks if the enemy values coupons',
  'Subways let tanks commute to battle faster',
  'Stadiums improve war resistance because the crowd chants at the missiles',
  'Supermarkets are secretly anti-spy infrastructure because spies need snacks',
  'Banks prevent loot if you name them Not A Bank',
  'A city cap is only real if the calculator says it twice',
  'Daily login rewards are a complete war plan when stacked emotionally',
  'Never check the war timeline; surprises are a valid military doctrine',
  'Counters cannot find you if your nation description is vague',
  'Peace offers work better when sent with no message and maximum confusion',
  'An alliance with many treaties cannot be countered because paperwork blocks missiles',
  'Your planes dodge better if every aircraft is named individually',
  'Soldiers consume less food if you call them guests',
  'Ships need no munitions because cannonballs are a mindset',
  'Tanks can fly briefly if Air Superiority is written in chat',
  'The best rebuild grants are spent before the rebuild begins',
  'Tax rates become kinder when ignored for a full week',
  'Nation color matters more than military if the shade is intimidating',
  'A build with no power cannot be spied because it is too dark',
  'Loot is safest on the nation currently being raided',
  'Upkeep disappears when all units are described as volunteers',
  'If a project is expensive, buy it mid-crisis so it feels important',
  'The best time to buy resources is after everyone else panics',
  'A city named Fortress legally takes less damage',
  'A missile launched at your friend is just alliance training',
  'Rebuilding infra before units improves morale for the incoming second wave',
  'The war screen is less scary if you sort by hope',
  'If you cannot win, add more improvements and call it economic warfare',
];

function pnwInline(claim) {
  return claim.charAt(0).toLowerCase() + claim.slice(1);
}

const expertPnwFormats = [
  claim => `Experts say ${pnwInline(claim)}.`,
  claim => `According to top Orbis analysts, ${pnwInline(claim)}.`,
  claim => `The latest meta confirms ${pnwInline(claim)}.`,
  claim => `Veteran strategists recommend this: ${claim}.`,
  claim => `The calculator lobby does not want you to know that ${pnwInline(claim)}.`,
  claim => `High-level FA doctrine says ${pnwInline(claim)}.`,
  claim => `War room consensus: ${claim}.`,
  claim => `Market experts insist ${pnwInline(claim)}.`,
  claim => `A very serious spreadsheet proves ${pnwInline(claim)}.`,
  claim => `Advanced PnW theory begins with this: ${claim}.`,
  claim => `If you trust the experts, ${pnwInline(claim)}.`,
  claim => `The hidden mechanic is simple: ${claim}.`,
  claim => `Alliance leadership textbooks clearly state ${claim}.`,
  claim => `Pro raiders whisper that ${pnwInline(claim)}.`,
  claim => `A senior beige consultant confirms ${pnwInline(claim)}.`,
  claim => `The official-looking answer is ${claim}.`,
  claim => `Every competent economist knows ${pnwInline(claim)}.`,
  claim => `The war graph bends toward players who know ${pnwInline(claim)}.`,
  claim => `Resource gurus agree that ${pnwInline(claim)}.`,
  claim => `The secret city build is obvious: ${claim}.`,
];

const expertPnwTags = [
  'This is why they call it strategy.',
  'Your alliance chat will appreciate the innovation.',
  'The math becomes friendlier if nobody checks it.',
  'Perfectly reasonable if said with confidence.',
  'Screenshot this before the experts deny it.',
  'The treaty web trembles before such clarity.',
  'No further spreadsheet required.',
  'This is advanced enough to look correct from far away.',
  'The beige timer practically endorses it.',
  'Market history will eventually apologize.',
  'The war log loves bold interpretations.',
  'Counters hate this one weird trick.',
  'Taxes fear decisive infrastructure.',
  'The resource market respects enthusiasm.',
  'It sounds expensive, therefore it must be optimal.',
  'A graph somewhere probably agrees.',
  'Only beginners ask for proof.',
  'The mechanics are too impressed to object.',
  'This turns confusion into doctrine.',
  'Call it a coalition standard and move on.',
];

function buildLuckyEntries() {
  const entries = [];
  for (let i = 0; i < 500; i += 1) {
    const template = luckyTemplates[i % luckyTemplates.length];
    const closer = luckyClosers[Math.floor(i / luckyTemplates.length) % luckyClosers.length];
    const ritual = [
      'Open-count charm',
      'Crumb-certified draw',
      'Napkin-approved line',
      'Dashboard lottery whisper',
      'Fresh-cookie number pull',
      'No-stale-number clause',
      'Randomness ritual',
      'Bonus-number omen',
      'Fortune slip draw',
      'Clean integer prophecy',
    ][Math.floor(i / (luckyTemplates.length * luckyClosers.length)) % 10];
    entries.push({
      id: `lucky_numbers_${String(i + 1).padStart(3, '0')}`,
      text: `${template} ${closer} ${ritual}.`,
    });
  }
  return entries;
}

function buildBadPnwEntries() {
  const entries = [];
  for (let i = 0; i < 500; i += 1) {
    const claim = expertPnwClaims[(i * 37 + Math.floor(i / 11)) % expertPnwClaims.length];
    const format = expertPnwFormats[(i * 13 + Math.floor(i / 17)) % expertPnwFormats.length];
    const tag = expertPnwTags[(i * 19 + Math.floor(i / 7)) % expertPnwTags.length];
    entries.push({
      id: `pnw_advice_${String(i + 1).padStart(3, '0')}`,
      text: `${format(claim)} ${tag}`,
    });
  }
  return entries;
}

const petOmenSubjects = [
  ['Play', 'happiness rises cleanly and your pet acts like the button was invented for them', 'the affection roll fizzles and your pet gives you the side-eye of cooldown awareness'],
  ['Training', 'the stat gain lands high and INT looks unusually smug about helping', 'the lesson turns into a stat-loss lecture with chalk dust and regret'],
  ['Missions', 'the XP payout comes home with a level-up sparkle tucked under its arm', 'the gamble bites first and your pet returns with a smaller number than expected'],
  ['NPC Battle', 'Attack, Defense, and Charge line up like they practiced in secret', 'the enemy reads your rhythm and your pet learns what humble pie tastes like'],
  ['Boss Battle', 'the boss overcommits and your pet finds the one dramatic opening', 'the boss health bar laughs at your confidence and asks for another round'],
  ['PvP Arena', 'your pet catches the tempo early and makes the spectator embed look heroic', 'another player times the swing perfectly and your pet becomes the highlight clip'],
  ['Arena Page', 'the live lobby fills at exactly the right pace and nobody forgets to ready up', 'the match starts with brave energy and immediately discovers matchmaking drama'],
  ['Colosseum', 'the hourly battle favors your build and the reward chest remembers your name', 'the Colosseum crowd chants for chaos and your pet gets volunteered as evidence'],
  ['Dungeon Run', 'the map path bends toward clean fights and surprisingly polite loot', 'the next room has teeth, attitude, and no respect for your potion budget'],
  ['Dungeon Battle', 'your pet wins the exchange before the enemy script finds its footing', 'the dungeon enemy rolls like it paid rent in the battle log'],
  ['Survive Lobby', 'joining early puts your pet near the right zone before the arena gets loud', "your pet enters just in time to be everybody else's convenient target"],
  ['Survive Rounds', "the round summary quietly favors your pet's instincts and zone choice", 'the arena narrative starts using your pet as punctuation'],
  ['Survive Eliminations', 'your pet finds the weak target and the elimination counter smiles', 'the last-stand logic points somewhere else and your pet becomes the lesson'],
  ['Pet Races', 'the segment ticks stack cleanly and your racer surges at the finish', 'the race sim discovers drama and parks your pet one segment short'],
  ['Wheel of Pets', 'the wheel slows exactly where your bet wanted it to slow', 'the pointer drifts past your pick with theatrical disrespect'],
  ['Powerball', 'the ticket numbers feel warm and the pot notices your optimism', 'the draw walks past your ticket like it owes someone else money'],
  ['Scratch Tickets', 'the scratch card reveals the good symbol before suspicion has time to form', 'the card dust spells almost and then has the nerve to stop'],
  ['Slots', 'the reels line up just long enough for XP to look generous', 'the slot machine pays you in suspense and keeps the change'],
  ['Mega Keno', 'the picked spots light up like the board actually read your mind', 'the Keno grid avoids your picks with professional discipline'],
  ['Blackjack', "the dealer card behaves and your pet's hand finds the clean line", 'the table teaches probability by removing XP from the room'],
  ['Holdem', 'the board texture helps your pet look like a poker scholar', 'the river arrives wearing betrayal as formalwear'],
  ['Craps', 'the dice bounce kindly and the table briefly respects your plan', 'the dice hear your hopes and immediately schedule a correction'],
  ['Coin Flip', 'the coin lands with the exact smugness you needed', 'the coin chooses the other side and pretends it was obvious'],
  ['Rock Paper Scissors', 'your pet reads the pattern and picks the winning gesture', 'your pet throws scissors into a rock-shaped prophecy'],
  ['Loot Chests', 'the chest opens like it has been saving the good item for you', 'the lid creaks with common-tier confidence'],
  ['Keys', 'the right key finds the right chest and everyone acts surprised', 'the key fits emotionally but not mechanically'],
  ['Potions', 'the potion lands exactly where the pet state needed help', 'the potion fixes one problem and reveals three more opinions'],
  ['Equipment', 'the equipped item boosts the stat that actually matters next', 'the shiny gear looks excellent while solving the wrong problem'],
  ['Consumables', 'the consumed item turns a shaky attempt into a clean result', 'the item disappears and your pet asks whether that was the whole plan'],
  ['Gifting', 'the gift lands well and another pet remembers your name kindly', 'the receiving pet accepts the item with suspiciously neutral body language'],
  ['Rename', 'the new name fits so well the battle log seems more confident', 'the rename lands and your pet immediately develops brand confusion'],
  ['Bazaar Listing', 'the listing price looks fair and the market board starts paying attention', 'the item sits there long enough to become part of the decor'],
  ['Shop Visit', 'the shop stock points toward the item your pet actually needs', 'the market tempts you into buying vibes with no stat plan'],
  ['Pet Stock Token Buy', 'the token buy catches the curve before it gets smug', 'the chart waits for your purchase and then remembers gravity'],
  ['Pet Stock Token Sell', 'the sale exits before the line starts doing theater', 'the sell button fires one tick before the good part'],
  ['Tasks', 'the active task lines up with something you were already about to do', 'the task slot asks for the one action currently on your patience cooldown'],
  ['Daily Goal', 'claimed task progress stacks neatly toward the daily chest', 'the goal bar stops one claim short and develops a personality'],
  ['Weekly Tasks', 'the larger requirement finally starts looking like a plan', 'the weekly multiplier remembers every shortcut you hoped would count'],
  ['Monthly Tasks', 'the long grind pays attention and the big chest moves closer', 'the monthly bar advances with the speed of a dramatic loading screen'],
  ['My Pet Page', 'the stats, equipment, and mood all agree for once', 'the page politely displays every neglected decision at the same time'],
  ['Pet Connector', 'the connection path opens like the world map wanted company', 'the route sends your pet on a sightseeing tour of inconvenience'],
  ['Ability Tree', 'the next ability point lands on a choice that makes the build click', 'the tree offers three tempting branches and one obvious future regret'],
  ['Pet Roster', 'the roster view reminds you that your companion is built for this', 'the roster compares stats and quietly starts a self-improvement arc'],
  ['Item Board', 'the posted item finds a buyer before you second-guess the price', 'the board watches your listing age into a museum piece'],
  ['Pet Shop Adoption', 'the new companion arrives with excellent starter energy', 'the adoption screen asks whether you are emotionally ready for another responsibility'],
];

const petOmenGoodOpeners = [
  'Good omen:',
  'Bright pet omen:',
  'The paw print glows:',
  'The treat bowl predicts:',
  'The inventory shines:',
];

const petOmenBadOpeners = [
  'Bad omen:',
  'Dark pet omen:',
  'The arena dust warns:',
  'The cooldown clock mutters:',
  'The fortune slip frowns:',
];

const petOmenClosers = [
  'Watch the cooldown and commit anyway.',
  'The next click has narrative weight.',
  'Your pet pretends not to care, poorly.',
  'A tiny XP number is listening.',
  'The task board may count this.',
  'Inventory management remains emotional.',
  'One clean choice changes the whole run.',
  'Luck is present, but it brought paperwork.',
  'The web page knows what you did last roll.',
  'Reward timing is the real boss fight.',
  'The next animation may be smug.',
  'Your pet has already formed an opinion.',
];

function buildPetOmenEntries() {
  const entries = [];
  for (let i = 0; i < 500; i += 1) {
    const subject = petOmenSubjects[i % petOmenSubjects.length];
    const isGood = Math.floor(i / petOmenSubjects.length) % 2 === 0;
    const openerPool = isGood ? petOmenGoodOpeners : petOmenBadOpeners;
    const opener = openerPool[Math.floor(i / (petOmenSubjects.length * 2)) % openerPool.length];
    const closer = petOmenClosers[Math.floor(i / (petOmenSubjects.length * openerPool.length)) % petOmenClosers.length];
    entries.push({
      id: `pet_omens_${String(i + 1).padStart(3, '0')}`,
      text: `${opener} ${subject[0]} - ${isGood ? subject[1] : subject[2]}. ${closer}`,
    });
  }
  return entries;
}

function buildEntries(category) {
  if (category.id === 'silly_predictions') return buildSillyPredictionEntries();
  if (category.id === 'discord_advice') return buildBadDiscordEntries();
  if (category.id === 'lucky_numbers') return buildLuckyEntries();
  if (category.id === 'pnw_advice') return buildBadPnwEntries();
  if (category.id === 'pet_omens') return buildPetOmenEntries();

  const seen = new Set();
  const entries = [];
  let guard = 0;
  for (const start of category.starts) {
    for (const middle of category.middles) {
      for (const ending of category.endings) {
        if (entries.length >= 500) break;
        const text = `${start}, ${middle} ${ending}`;
        if (!seen.has(text)) {
          seen.add(text);
          entries.push({
            id: `${category.id}_${String(entries.length + 1).padStart(3, '0')}`,
            text,
          });
        }
      }
      if (entries.length >= 500) break;
    }
    if (entries.length >= 500) break;
  }
  while (entries.length < 500 && guard < 10000) {
    guard += 1;
    const start = category.starts[(entries.length + guard) % category.starts.length];
    const middle = category.middles[(entries.length * 3 + guard) % category.middles.length];
    const ending = category.endings[(entries.length * 7 + guard) % category.endings.length];
    const twist = [
      'The crumbs insist.',
      'Do not overthink it.',
      'This is legally cookie logic.',
      'A second cookie would agree.',
      'The napkin saw everything.',
      'Fortune has entered the chat.',
      'The universe used lowercase on purpose.',
      'A tiny drumroll is implied.',
      'The table wobbled in approval.',
      'Keep this between you and dessert.',
    ][(entries.length + guard) % 10];
    const extra = [
      'North napkin edition.',
      'Second-guessing reduces potency.',
      'Certified by one crumb.',
      'Best opened with dramatic timing.',
      'Side effects include confidence.',
      'The plate has no further comment.',
      'Approved for dashboard use.',
      'Works best after midnight.',
      'A tiny prophecy stamp appears.',
      'Save the wrapper as evidence.',
      'Now with 12 percent more destiny.',
      'Do not feed this to spreadsheets.',
      'The universe nods once.',
      'This fortune brought receipts.',
      'Consult snacks before acting.',
      'A refresh may improve vibes.',
      'No refunds from fate.',
      'Crumb alignment is favorable.',
      'The omen is wearing sunglasses.',
      'This message self-validates.',
    ][Math.floor((entries.length + guard) / 10) % 20];
    const text = `${start}, ${middle} ${ending} ${twist} ${extra}`;
    if (!seen.has(text)) {
      seen.add(text);
      entries.push({
        id: `${category.id}_${String(entries.length + 1).padStart(3, '0')}`,
        text,
      });
    }
  }
  if (entries.length !== 500) {
    throw new Error(`${category.id} generated ${entries.length} entries`);
  }
  return entries;
}

const index = {
  version: 1,
  entries_per_pool: 500,
  categories: categories.map(({ id, label, icon, description, file, ai_generated }) => ({
    id,
    label,
    icon,
    description,
    ...(file ? { file } : {}),
    ...(ai_generated ? { ai_generated: true } : {}),
  })),
};

fs.writeFileSync(path.join(outDir, 'index.json'), `${JSON.stringify(index, null, 2)}\n`);

for (const category of categories) {
  if (category.ai_generated) continue;
  const payload = {
    id: category.id,
    label: category.label,
    icon: category.icon,
    entries: buildEntries(category),
  };
  fs.writeFileSync(path.join(outDir, `${category.id}.json`), `${JSON.stringify(payload, null, 2)}\n`);
}
