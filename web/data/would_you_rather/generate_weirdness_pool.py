import json
from pathlib import Path

OUT = Path(__file__).with_name("weirdness.json")

choices = []
seen_choices = set()
entries = []
seen_questions = set()
seen_pairs = set()


def clean(text):
    return " ".join(text.split())


def add_choice(text):
    text = clean(text)
    key = text.lower()
    if key in seen_choices:
        return
    seen_choices.add(key)
    choices.append(text)


def add_question(a, b):
    a = clean(a)
    b = clean(b)
    if a.lower() == b.lower():
        return
    question = f"Would you rather {a}, or {b}?"
    qkey = question.lower()
    pkey = tuple(sorted([a.lower(), b.lower()]))
    if qkey in seen_questions or pkey in seen_pairs:
        return
    if a.lower() not in qkey or b.lower() not in qkey:
        raise RuntimeError(f"Choice missing from question: {question}")
    seen_questions.add(qkey)
    seen_pairs.add(pkey)
    entries.append({"question": question, "choices": [a, b]})


superpowers = [
    "teleport anywhere",
    "read minds",
    "turn invisible",
    "freeze time for ten seconds",
    "summon any snack",
    "speak every language",
    "see five minutes into the future",
    "never need sleep",
    "copy any skill instantly",
    "change your appearance at will",
    "make any object float",
    "heal any minor injury instantly",
    "rewind one conversation per day",
    "make perfect clones of yourself",
    "control the weather in one room",
    "remember every fact you hear",
    "turn any door into a portal",
    "summon a tiny personal theme song",
    "make anyone tell the truth",
    "swap places with any object you can see",
    "win every coin flip",
    "make technology obey your voice",
    "erase one awkward moment per day",
    "turn any drink into your favorite drink",
    "make your shadow do chores",
]

superpower_catches = [
    "but you arrive wearing a mascot costume",
    "but everyone nearby hears a dramatic narrator explain what you did",
    "but it only works while you are deeply embarrassed",
    "but a crowd immediately rates your performance out of ten",
    "but you must say the worst possible catchphrase first",
    "but your phone sends a calendar invite about it to everyone you know",
    "but you hiccup loudly for the next hour",
    "but you temporarily forget one common word",
    "but your shoes squeak your full legal name",
    "but every mirror shows a replay afterward",
    "but it leaves glitter on everything you touched that day",
    "but it only works if you maintain uncomfortable eye contact",
]

for power in superpowers:
    for catch in superpower_catches:
        add_choice(f"have the power to {power} {catch}")


bad_situations = [
    "wake up as the host of a trial where your browser history is the defendant",
    "be trapped in a group chat where every message is read aloud by your boss",
    "have your search history appear as subtitles above your head",
    "be forced to explain every joke you laughed at for the next week",
    "have every lie you tell become a ringtone on your phone",
    "attend a family dinner where everyone can hear your inner monologue",
    "have your most embarrassing memory play as a loading screen before every meeting",
    "be followed by a customer service survey after every conversation",
    "have your dreams automatically posted as confusing status updates",
    "be unable to enter a room until you receive applause from at least one person",
    "have every serious moment interrupted by your old voicemail greeting",
    "be stuck wearing an outfit chosen by your last three text messages",
    "have every typo you make printed on a tiny receipt",
    "be required to introduce yourself with your worst habit first",
    "have your unread notifications whisper your name in public",
    "make every handshake replay in slow motion on nearby screens",
    "have every chair announce how long you have been sitting",
    "be unable to leave any conversation without a formal exit interview",
    "have every door ask why you deserve to enter",
    "turn every awkward silence into a mandatory team-building exercise",
    "have your calendar invite your enemies to your free time",
    "be followed by a scoreboard ranking your daily decisions",
    "have your autocorrect replace compliments with legal warnings",
    "wake up with a documentary crew narrating your chores",
    "have every snack you eat file a complaint about your life choices",
]

situation_modifiers = [
    "for one day",
    "for one week",
    "every Monday",
    "only when you are trying to look normal",
    "during every important event",
    "whenever someone says your name",
    "but nobody believes you when you explain it",
    "but only strangers can see it",
    "but it stops the moment you try to prove it",
    "and you must act like it is totally normal",
    "while your friends are allowed to vote on the rules",
    "with a tiny theme song playing the entire time",
]

for situation in bad_situations:
    for modifier in situation_modifiers:
        add_choice(f"{situation} {modifier}")


cursed_objects = [
    "a phone",
    "a wallet",
    "a backpack",
    "a microwave",
    "a mirror",
    "a toothbrush",
    "a keyboard",
    "a hoodie",
    "a refrigerator",
    "a pair of shoes",
    "a pillow",
    "a coffee mug",
    "a remote control",
    "a shower",
    "a car key",
    "a notebook",
    "a spoon",
    "a doorbell",
    "a blanket",
    "a chair",
    "a vending machine",
    "a pair of headphones",
    "a charger",
    "a water bottle",
    "a desk lamp",
]

object_curses = [
    "that screams your most recent bad decision once per hour",
    "that refuses to work unless you compliment it sincerely",
    "that loudly predicts your next mistake",
    "that turns invisible whenever you are already late",
    "that sends passive-aggressive reminders to nearby strangers",
    "that replaces normal sounds with dramatic movie trailer booms",
    "that demands a password you set in a dream",
    "that rates every conversation it witnesses",
    "that gives terrible advice in a confident voice",
    "that leaks harmless confetti whenever you panic",
    "that only obeys people who disagree with you",
    "that keeps a public scoreboard of your procrastination",
]

for obj in cursed_objects:
    for curse in object_curses:
        add_choice(f"own {obj} {curse}")


funny_picks = [
    "have every sneeze launch a tiny weather report",
    "make every step sound like a dramatic courtroom entrance",
    "have your laugh echo once in a completely different accent",
    "have your shadow constantly try to give you motivational advice",
    "turn every elevator ride into a fake game show",
    "have your eyebrows perform a drumroll before you answer questions",
    "make every mirror give you a suspiciously specific pep talk",
    "have your pockets reject anything they think is clutter",
    "make every alarm clock negotiate like a lawyer",
    "have your handwriting look like an ancient prophecy",
    "turn every receipt into a tiny roast about what you bought",
    "make your shoes play boss music when you enter a room",
    "have every restaurant menu rank your confidence",
    "make every password hint insult you personally but accurately",
    "have every umbrella open with a parade announcement",
    "turn every meeting into a cooking show for thirty seconds",
    "make your ringtone announce your current mood",
    "have every light switch say plot twist",
    "make every yawn release a tiny applause track",
    "have every calendar reminder accuse you of betrayal",
    "make every chair ask if this is really your final answer",
    "have every text message briefly become a treasure map before sending",
    "turn every compliment into a fortune cookie message",
    "make your reflection arrive three seconds late",
    "have every sock display a loading bar",
]

funny_conditions = [
    "for the rest of your life",
    "but only around people you want to impress",
    "but only your enemies find it charming",
    "during every first impression",
    "whenever you are trying to be serious",
    "but you get paid one dollar every time it happens",
    "but it stops if you admit you enjoy it",
    "and everyone acts like you chose this",
    "but it makes one random person nearby laugh uncontrollably",
    "but only after midnight",
    "while a tiny scoreboard tracks how weird it was",
    "but you can never explain why it happens",
]

for funny in funny_picks:
    for condition in funny_conditions:
        add_choice(f"{funny} {condition}")


body_glitches = [
    "blink in subtitles",
    "speak one random word in a movie trailer voice",
    "hear boss music whenever you make eye contact",
    "see a danger meter over every bad idea",
    "taste colors for ten minutes",
    "smell lies as burnt popcorn",
    "hear your own thoughts with commercial breaks",
    "see a loading bar over people deciding what to say",
    "have your hands clap automatically after bad jokes",
    "temporarily turn transparent when embarrassed",
    "hear a tiny cash register sound when you change your mind",
    "see review stars above every awkward moment",
    "make bubble wrap sounds when stretching",
    "have your voice auto-tune during apologies",
    "glow softly when pretending to understand something",
    "hear elevator music when someone lies badly",
    "make your stomach play notification sounds when hungry",
    "see subtitles for animal thoughts but only the dramatic ones",
    "have your knees play a fanfare when you stand up",
    "see a tiny quest marker over your worst decision",
    "turn slightly pixelated when nervous",
    "make your hair point toward nearby snacks",
    "hear a referee whistle when you interrupt someone",
    "see your confidence as a visible battery icon",
    "make your shadow facepalm when you say something dumb",
]

glitch_rules = [
    "for one hour every day",
    "during every important conversation",
    "whenever someone asks a simple question",
    "but only people who dislike you notice",
    "but it becomes twice as strong in quiet rooms",
    "but it randomly turns off when useful",
    "and you must pretend it is a medical condition",
    "but it gives you perfect luck for five minutes afterward",
    "while your phone records the highlight reel",
    "but it only happens when you are telling the truth",
    "and a stranger gets to name the condition",
    "but it makes you immune to embarrassment for ten seconds",
]

for glitch in body_glitches:
    for rule in glitch_rules:
        add_choice(f"{glitch} {rule}")


weird_worlds = [
    "live in a world where every elevator has a boss fight",
    "live in a world where birthdays are judged by a panel of strangers",
    "live in a world where every bank account has a mood",
    "live in a world where shoes choose their owners",
    "live in a world where traffic lights gossip about drivers",
    "live in a world where every meal must be named like a movie sequel",
    "live in a world where mirrors can unionize",
    "live in a world where every Monday has patch notes",
    "live in a world where chairs remember secrets",
    "live in a world where every apology needs a receipt",
    "live in a world where dreams come with sponsored ads",
    "live in a world where weather reports include personal criticism",
    "live in a world where everyone has a visible nonsense ranking",
    "live in a world where refrigerators enforce snack laws",
    "live in a world where every argument gets instant replay",
    "live in a world where alarms can file lawsuits",
    "live in a world where sidewalks judge your walking speed",
    "live in a world where every door charges emotional rent",
    "live in a world where group chats can summon people physically",
    "live in a world where silence is taxed",
]

world_rules = [
    "and you are the only normal person",
    "and you are legally responsible for explaining it",
    "but you get one useful superpower nobody respects",
    "but your worst enemy is thriving there",
    "and every rule changes on Fridays",
    "but you can leave only after winning a talent show",
    "and your friends vote on your daily penalty",
    "but it has incredible snacks",
    "but every convenience is slightly cursed",
    "and your job is to enforce the weirdest law",
]

for world in weird_worlds:
    for rule in world_rules:
        add_choice(f"{world} {rule}")


public_chaos = [
    "have your life narrated by a disappointed sports commentator",
    "be followed by a floating customer rating after every interaction",
    "have every room you enter vote on your entrance music",
    "be assigned a random side quest by every stranger who says hello",
    "have every purchase announced like a championship result",
    "be unable to sit down until a nearby person names your chair",
    "have every mirror ask one brutally specific follow-up question",
    "be forced to defend your outfit in a fake press conference",
    "have every missed call become a tiny courtroom summons",
    "be followed by a personal laugh track with terrible timing",
    "have every snack you open require a dramatic oath",
    "be unable to use stairs unless you announce your destination",
    "have every typo spawn a tiny public correction ceremony",
    "be required to give a victory speech after ordinary chores",
    "have every password attempt judged by a panel of bored ghosts",
    "be unable to whisper without sounding like a movie villain",
    "have every grocery trip turn into a timed obstacle course",
    "be followed by a tiny scoreboard showing your confidence level",
    "have every apology interrupted by a fake sponsor message",
    "be unable to leave a building until you solve its emotional riddle",
    "have every elevator open onto a different awkward conversation",
    "be assigned a theme by every group chat you join",
    "have every chair you use remember and repeat your last complaint",
    "be unable to drink water without hearing a heroic fanfare",
    "have every silence around you reviewed like a restaurant",
]

chaos_rules = [
    "for the next month",
    "but only when you are around new people",
    "and everyone assumes you planned it",
    "while your best friend controls the sound effects",
    "but you earn one dollar each time you survive it",
    "and it gets worse when you deny it",
    "but it gives you perfect parking luck",
    "during every formal event",
    "but only your enemies find it impressive",
    "and your phone saves every highlight",
    "but it stops for one hour if you compliment it",
    "while a tiny invisible judge keeps score",
]

for chaos in public_chaos:
    for rule in chaos_rules:
        add_choice(f"{chaos} {rule}")


if len(choices) < 2000:
    raise RuntimeError(f"Only generated {len(choices)} weird choices")

left = choices[:1000]
right = choices[1000:2000]

for i, a in enumerate(left):
    # The multiplier creates a deterministic shuffle without importing random.
    b = right[(i * 37 + 113) % len(right)]
    add_question(a, b)

if len(entries) != 1000:
    raise RuntimeError(f"Generated {len(entries)} entries instead of 1000")

OUT.write_text(json.dumps(entries, indent=2), encoding="utf-8")
print(f"Wrote {len(entries)} entries to {OUT}")
