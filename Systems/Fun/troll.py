"""
troll.py — /troll command for playful trolling with themed quotes.

Commands
--------
/troll user:<@user> theme:<Theme> — Send a themed troll message mentioning the user

Themes
------
- Movie Quotes: Iconic movie lines adapted to troll the user
- People Quotes: Famous quotes from historical figures and celebrities
- Randomness: Absurd, random, and humorous statements
"""

from __future__ import annotations

import logging
import random
from typing import List

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# MOVIE QUOTES - 210+ iconic movie lines adapted for trolling (40+ movies)
# ═══════════════════════════════════════════════════════════════════════════════

MOVIE_QUOTES: List[str] = [
    # ═══════════════════════════════════════════════════════════════════════════════
    # STAR WARS (15 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, I am your father... and I'm very disappointed.",
    "{user}, these aren't the droids you're looking for, but you definitely need to look harder in life.",
    "May the Force be with {user}... because nobody else wants to be.",
    "{user}, I find your lack of skill disturbing.",
    "Help me, Obi-Wan Kenobi, you're {user}'s only hope... and that's really sad.",
    "{user}, never tell me the odds... because they're never in your favor.",
    "Do or do not, {user}, there is no try... and you usually don't.",
    "{user}, that's no moon, that's your ego.",
    "I've got a bad feeling about {user}...",
    "{user}, strike me down and I shall become more powerful than you can possibly imagine... which isn't very.",
    "It's a trap, {user}! Just like your dating life.",
    "{user}, the Force is strong with this one... said no one ever about you.",
    "{user}, I have a bad feeling about this... whenever you're involved.",
    "{user}, these are not the skills you're looking for.",
    "{user}, I've got a bad feeling about this... especially when you're piloting.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # THE LORD OF THE RINGS / THE HOBBIT (15 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, you shall not pass... any basic competency test.",
    "One does not simply walk into Mordor, {user}, but you couldn't walk into a grocery store without getting lost.",
    "My precious... said {user} about their last brain cell.",
    "{user}, you have my sword, my bow, and my axe... because you need all the help you can get.",
    "A wizard is never late, {user}, nor is he early, but you're always late and never on time.",
    "{user}, even the smallest person can change the course of the future... but you changed it for the worse.",
    "Fly, you fools! Especially you, {user}.",
    "{user}, the board is set, the pieces are moving... and you're the pawn.",
    "{user}, I am Gandalf the Grey... and you're {user} the forgettable.",
    "End? No, {user}, the journey doesn't end here. Death is just another path... one you should consider taking faster.",
    "{user}, there's some good in this world, and it's worth fighting for... but not you.",
    "The beacons are lit! {user} calls for aid! And nobody answers.",
    "{user}, all we have to decide is what to do with the time that is given to us... and you waste yours.",
    "{user}, a day may come when you succeed... but it is not this day!",
    "{user}, the road goes ever on and on... but you keep stumbling at the start.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # THE DARK KNIGHT TRILOGY / BATMAN (12 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, why so serious?",
    "I'm Batman... and you're just {user}.",
    "{user}, you complete me... with your failures.",
    "Some men just want to watch the world burn, {user} just wants to watch their microwave popcorn.",
    "{user}, I believe whatever doesn't kill you simply makes you... stranger. And you're plenty strange.",
    "The night is darkest just before the dawn, {user}, but your night never ends.",
    "{user}, you either die a hero or you live long enough to see yourself become the villain... you chose neither and just became irrelevant.",
    "It's not who I am underneath, {user}, but what I do that defines me... and you do nothing.",
    "{user}, to them, you're just a freak, like me... except I'm actually interesting.",
    "{user}, you wanna know how I got these scars? From dealing with people like you.",
    "{user}, I'm the hero Gotham deserves, but not the one it needs right now... you're neither.",
    "{user}, swearing to God doesn't make the drop easier... especially when you fall.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # MARVEL CINEMATIC UNIVERSE (18 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, I am inevitable... and you are forgettable.",
    "{user}, I love you 3000... times less than literally anyone else.",
    "{user}, on your left... because that's where you'll always be.",
    "{user}, we have a Hulk... and we also have you, which is less impressive.",
    "{user}, part of the journey is the end... and you're overdue for yours.",
    "{user}, I can do this all day... said your alarm clock, because you keep hitting snooze.",
    "{user}, you're breathtaking! No, wait, that's just your bad breath.",
    "{user}, with great power comes great responsibility... and you have neither.",
    "{user}, I'm always angry... especially when I see you.",
    "{user}, that's my secret, Captain... I'm always disappointed in you.",
    "{user}, we are Groot... you are just grooty.",
    "{user}, snap! Just like your career.",
    "{user}, I'll do you one better: WHY is Gamora? Because even she doesn't want to be around you.",
    "{user}, Dormammu, I've come to bargain... for someone else to take you.",
    "{user}, I can do this all day... but I'd rather not spend it with you.",
    "{user}, excuse me, sir! Is that your nose or did you eat a failure?",
    "{user}, language! Even Thor has better manners than you.",
    "{user}, I have nothing to prove to you... unlike you, who has everything to prove.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # HARRY POTTER SERIES (14 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, you're a wizard, Harry! No, wait, you're just {user}.",
    "{user}, I solemnly swear that I am up to no good... unlike you, who's up to nothing.",
    "{user}, happiness can be found even in the darkest of times... unless you're around.",
    "{user}, after all this time? Always disappointing.",
    "{user}, it does not do to dwell on dreams and forget to live... but you're not doing either.",
    "{user}, I must not tell lies... and the truth is you're struggling.",
    "{user}, not my daughter, you b-... oh wait, never mind, nobody wants to date you.",
    "{user}, always... late to everything.",
    "{user}, I can teach you how to bottle fame, brew glory, even stopper death... but I can't fix you.",
    "{user}, yer a disappointment, {user}.",
    "{user}, fear of a name only increases fear of the thing itself... and we all fear your cooking.",
    "{user}, it takes great deal of bravery to stand up to our enemies... and you have none of that bravery.",
    "{user}, Wingardium Leviosa! Not that it would help you rise above anything.",
    "{user}, expecto patronum! But even a Patronus runs from you.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # TITANIC (8 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, I'm the king of the world! You're just the jester.",
    "{user}, I'll never let go... of my low expectations for you.",
    "{user}, draw me like one of your French girls... actually, don't, it would be worse.",
    "{user}, this is where we first met... and where I started avoiding you.",
    "{user}, I see you, I see you... and I wish I didn't.",
    "{user}, a woman's heart is a deep ocean of secrets... yours is a shallow puddle of excuses.",
    "{user}, I'm flying, Jack! You're sinking, {user}.",
    "{user}, make it count, meet me at the clock... but you won't make it.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # THE MATRIX TRILOGY (12 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, there is no spoon... but there is a fork in your road, and you took the wrong one.",
    "{user}, follow the white rabbit... because you can't follow basic instructions.",
    "{user}, I know kung fu... and you know nothing, Jon Snow.",
    "{user}, red pill or blue pill? Either way, you're still you.",
    "{user}, dodge this... and everything else life throws at you, because you can't handle it.",
    "{user}, welcome to the desert of the real... where your excuses don't work.",
    "{user}, I can only show you the door, you're the one that has to walk through it... and you keep tripping.",
    "{user}, ignorance is bliss... so you must be the happiest person alive.",
    "{user}, unfortunately, no one can be told what the Matrix is... and no one can explain why you exist.",
    "{user}, stop trying to hit me and hit me! Actually, don't, you'd miss anyway.",
    "{user}, he is the One... thing everyone avoids.",
    "{user}, I know you're out there. I can feel you now... and it's uncomfortable.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # FORREST GUMP (8 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, life is like a box of chocolates... you always get the weird coconut ones nobody wants.",
    "{user}, run, Forrest, run! Away from you.",
    "{user}, my mama always said, stupid is as stupid does... so what have you done today?",
    "{user}, I'm not a smart man, but I know what love is... and I love not being you.",
    "{user}, you have to do the best with what God gave you... and He gave you very little.",
    "{user}, that's all I have to say about that... which is more than anyone says about you.",
    "{user}, miracles happen every day... just not to you.",
    "{user}, I'm pretty tired... of {user}'s excuses.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # TERMINATOR SERIES (8 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, I'll be back... and hopefully you'll be gone.",
    "{user}, hasta la vista, baby... and good riddance.",
    "{user}, come with me if you want to live... actually, stay, you'll just slow us down.",
    "{user}, I need your clothes, your boots, and your motorcycle... because I have a life and you don't.",
    "{user}, you're terminated... from being interesting.",
    "{user}, hasta la vista, baby! Don't forget to fail!",
    "{user}, come with me if you want to live... actually, never mind.",
    "{user}, your foster parents are dead... from embarrassment about you.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # GLADIATOR / BRAVEHEART / 300 / SPARTACUS (12 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, my name is Maximus Decimus Meridius... and {user} is just {user}.",
    "{user}, are you not entertained?! Because watching you try is hilarious.",
    "{user}, at my signal, unleash hell... on {user}.",
    "{user}, strength and honor... two things you lack.",
    "{user}, they may take our lives, but they'll never take our freedom! {user} already gave both away.",
    "{user}, every man dies, not every man really lives... {user} barely exists.",
    "{user}, this is Sparta! And you're not worthy.",
    "{user}, tonight we dine in hell! Save a seat for {user}.",
    "{user}, prepare for glory! Or in {user}'s case, prepare for mediocrity.",
    "{user}, I am Spartacus! And you're just {user}.",
    "{user}, I'm not a slave. I'm a free man! Unlike {user}, who's chained to failure.",
    "{user}, by all that you hold dear on this good earth... you probably don't hold much.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # PIRATES OF THE CARIBBEAN (8 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, why is the rum gone? {user} drank it all with their tears.",
    "{user}, you are without doubt the worst pirate I've ever heard of... but you have heard of me!",
    "{user}, this is the day you will always remember as the day you almost caught Captain Jack Sparrow... and failed.",
    "{user}, not all treasure is silver and gold, mate... and you're worth neither.",
    "{user}, I got a jar of dirt! And {user} has a jar of disappointment.",
    "{user}, savvy? Not {user}. Never {user}.",
    "{user}, dead men tell no tales... but {user} tells too many excuses.",
    "{user}, the code is more what you'd call guidelines than actual rules... and {user} can't follow either.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # THE GODFATHER TRILOGY (8 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, I'm going to make him an offer he can't refuse... to leave.",
    "{user}, leave the gun, take the cannoli... and leave {user} too.",
    "{user}, it's not personal, it's strictly business... and you're bad at both.",
    "{user}, I know it was you, Fredo. You broke my heart... just like {user} breaks everything.",
    "{user}, a man who doesn't spend time with his family can never be a real man... {user} fails both.",
    "{user}, revenge is a dish best served cold... and {user}'s career is ice cold.",
    "{user}, never let anyone outside the family know what you're thinking... {user} lets everyone know they don't think.",
    "{user}, great men are not born great, they grow great... {user} remains small.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # CASABLANCA / GONE WITH THE WIND / CITIZEN KANE (10 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, frankly, my dear, I don't give a damn... and neither does anyone else.",
    "{user}, here's looking at you, kid... with pity.",
    "{user}, we'll always have Paris... but we'll never have respect for {user}.",
    "{user}, of all the gin joints in all the towns in all the world... you walk into mine. Please walk out.",
    "{user}, play it, Sam. Play 'As Time Goes By'... while {user} goes by unnoticed.",
    "{user}, I think this is the beginning of a beautiful friendship... said no one to {user}.",
    "{user}, rosebud... that's what {user} mutters when they fail again.",
    "{user}, after all, tomorrow is another day! And {user} will fail again.",
    "{user}, as God is my witness, I'll never be hungry again! {user} stays hungry for success.",
    "{user}, I don't want realism, I want magic! And {user} provides neither.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # TAXI DRIVER / SCARFACE / GOODFELLAS (10 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, you talkin' to me? Because I'm definitely not listening.",
    "{user}, you talkin' to me? Well, I'm the only one here... because everyone left thanks to {user}.",
    "{user}, say hello to my little friend! And goodbye to your dignity.",
    "{user}, I always tell the truth, even when I lie... {user} just lies.",
    "{user}, the world is yours! But not {user}'s.",
    "{user}, as far back as I can remember, I always wanted to be a gangster... {user} just wanted to be competent.",
    "{user}, I'm funny how? Funny like a clown? Like {user} amuses me?",
    "{user}, never rat on your friends, and always keep your mouth shut... {user} fails both.",
    "{user}, I don't want to be a product of my environment... unlike {user}, who's a product of failure.",
    "{user}, you got some coke? No, but {user} has some shame.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # THE SHINING / PSYCHO / HORROR CLASSICS (10 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, here's Johnny! And there's the door.",
    "{user}, all work and no play makes {user} a dull boy... especially the work part.",
    "{user}, redrum! That's what {user}'s mirror says every morning.",
    "{user}, I see dead people... and you're killing my vibe.",
    "{user}, we all go a little mad sometimes... {user} stays mad.",
    "{user}, they're here! And by 'they,' I mean your problems.",
    "{user}, whatever you do, don't fall asleep... or you'll miss {user} failing again.",
    "{user}, I have such sights to show you! But {user} wouldn't appreciate them.",
    "{user}, do you want to play a game? {user} already lost.",
    "{user}, get to the choppa! Before {user} ruins everything!",

    # ═══════════════════════════════════════════════════════════════════════════════
    # ALIEN / PREDATOR / SCI-FI HORROR (10 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, in space, no one can hear you scream... but everyone hears {user} whine.",
    "{user}, game over, man! Game over! Thanks to {user}.",
    "{user}, they mostly come out at night... mostly. Like {user}'s competence.",
    "{user}, if it bleeds, we can kill it... but {user}'s ego is immortal.",
    "{user}, get away from her, you b-! Said everyone to {user}.",
    "{user}, I ain't got time to bleed... but I've got time to roast {user}.",
    "{user}, it's not a tumor! It's just {user} being dramatic.",
    "{user}, who is your daddy and what does he do? He apologizes for {user}.",
    "{user}, come on, {user}! Come on! But {user} never comes through.",
    "{user}, I see you baby, shining in the dark! Unlike {user}, who dims every room.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # MEAN GIRLS / CLUELESS / LEGALLY BLONDE (10 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, on Wednesdays we wear pink... {user} wears disappointment.",
    "{user}, that is so fetch! And by fetch, I mean not fetch at all, {user}.",
    "{user}, get in, loser, we're going shopping... without you, {user}.",
    "{user}, you can't sit with us! Especially you, {user}.",
    "{user}, my cup of tea is empty... just like {user}'s promises.",
    "{user}, whatever, I'm getting cheese fries... while {user} gets nothing.",
    "{user}, as if! {user}'s chances of success.",
    "{user}, totally buggin'! Is what {user} does constantly.",
    "{user}, bend and snap! {user} just snaps.",
    "{user}, what, like it's hard? Said {user} before failing the easy stuff.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # FIGHT CLUB / AMERICAN PSYCHO / TAXI DRIVER (10 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, I am Jack's complete lack of surprise... that {user} failed again.",
    "{user}, the first rule of Fight Club is... you don't talk about {user}'s failures, there are too many.",
    "{user}, I see you shiver with antici... pation! Of {user} finally succeeding, which will never happen.",
    "{user}, I have to return some videotapes... and avoid {user}.",
    "{user}, there is an idea of a Patrick Bateman... there is no idea of {user}.",
    "{user}, I have all the characteristics of a human being: flesh, blood, skin, hair... {user} not so much.",
    "{user}, you're a f***ing ugly bitch! I want to stab you to death and play around with your blood! Too harsh? Not for {user}.",
    "{user}, you talkin' to me? You talkin' to me? You talkin' to me? {user} talks to no one.",
    "{user}, the things you own end up owning you... {user} owns nothing.",
    "{user}, it's only after we've lost everything that we're free to do anything... {user} is very free.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # 2001: A SPACE ODYSSEY / BLADE RUNNER / SCI-FI CLASSICS (10 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, I'm sorry, Dave. I'm afraid I can't do that... especially for {user}.",
    "{user}, open the pod bay doors, HAL... so {user} can get ejected into space.",
    "{user}, I've just picked up a fault in the AE35 unit... it says {user} is approaching.",
    "{user}, all those moments will be lost in time, like tears in rain... especially {user}'s moments.",
    "{user}, it's too bad she won't live. But then again, who does? Not {user}'s dreams.",
    "{user}, I've seen things you people wouldn't believe... but I haven't seen {user} succeed.",
    "{user}, my god, it's full of stars! Unlike {user}'s report card.",
    "{user}, just what do you think you're doing, Dave? {user} doesn't know either.",
    "{user}, I am your father... of disappointment, {user}.",
    "{user}, you've got to be kidding me... is what everyone says when {user} shows up.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # GUARDIANS OF THE GALAXY / ANT-MAN / DEADPOOL (10 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, I am Groot... and you are not.",
    "{user}, we are Groot... but {user} is just grooty.",
    "{user}, there's a raccoon and a tree asking for you... they're more qualified than {user}.",
    "{user}, oh, I'm sorry. I didn't know how this machine worked... said {user} about life.",
    "{user}, I'm gonna die surrounded by the biggest idiots in the galaxy... starting with {user}.",
    "{user}, maximum effort! {user} puts in minimum effort.",
    "{user}, chimichanga! The sound of {user}'s career imploding.",
    "{user}, with great power comes great merchandising opportunities... {user} has neither.",
    "{user}, bad Deadpool... good Deadpool... {user} is just pool.",
    "{user}, I put on a suit and everything! {user} puts on disappointment.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # BLACK PANTHER / WONDER WOMAN / CAPTAIN MARVEL (8 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, Wakanda forever! {user}, never.",
    "{user}, we don't do that here... especially not with {user}.",
    "{user}, I never freeze... unlike {user}, who freezes under pressure.",
    "{user}, is this your king? No, this is {user}.",
    "{user}, I am Iron Man... you are Aluminum Foil Person.",
    "{user}, I could do this all day... but I'd rather not with {user}.",
    "{user}, higher, further, faster... {user} stays lower, closer, slower.",
    "{user}, I'm just a kid from Brooklyn... {user} is just a disappointment from everywhere.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # ROCKY / RUDY / SPORTS MOVIES (8 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, yo, Adrian! {user} got knocked out again!",
    "{user}, it ain't about how hard you hit, it's about how hard you can get hit and keep moving forward... {user} falls on first hit.",
    "{user}, Adrian! Adrian! ... is ignoring {user}.",
    "{user}, the beast is gone now... and {user} is the beast.",
    "{user}, Rudy! Rudy! Rudy! ... didn't make it either.",
    "{user}, you're killing me, Smalls! Especially you, {user}.",
    "{user}, heroes get remembered, but legends never die... {user} is neither.",
    "{user}, if you build it, he will come... but not for {user}.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # E.T. / CLOSE ENCOUNTERS / BACK TO THE FUTURE (10 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, E.T. phone home... and tell them to come get you.",
    "{user}, E.T. home phone... {user} has no home.",
    "{user}, you've got mail! It's a rejection letter.",
    "{user}, I am the gatekeeper. Are you the keymaster? No, you're just {user}.",
    "{user}, we came in peace for all mankind... but not for {user}.",
    "{user}, great Scott! {user} is the worst!",
    "{user}, roads? Where we're going, we don't need roads... {user} needs all the help.",
    "{user}, flux capacitor! The thing {user} lacks.",
    "{user}, 1.21 gigawatts! What {user} needs to power their potential.",
    "{user}, your kids are gonna love it! If {user} ever has any.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # JURASSIC PARK / JAWS / KING KONG / MONSTER MOVIES (10 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, welcome to Jurassic Park... where {user} is the dinosaur.",
    "{user}, life finds a way... but not for {user}.",
    "{user}, clever girl! Not {user}, never {user}.",
    "{user}, hold onto your butts! Here comes {user}!",
    "{user}, we're gonna need a bigger boat... to handle {user}'s ego.",
    "{user}, you're gonna need a bigger boat... to handle {user}'s failure.",
    "{user}, it was a shark! It was a shark! It's {user}!",
    "{user}, beauty killed the beast... but {user} killed the mood.",
    "{user}, oh, no. It wasn't the airplanes. It was {user} who killed the beast.",
    "{user}, is that a tyrannosaurus? No, it's just {user} stomping around.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # INDIANA JONES / THE MUMMY / ADVENTURE FILMS (8 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, snakes! Why did it have to be snakes? Actually, {user} is worse.",
    "{user}, it's not the years, honey, it's the mileage... and {user} has high mileage on failure.",
    "{user}, archaeology is the search for fact... not truth. {user} has neither.",
    "{user}, I hate snakes, Jock! I hate them! But I hate {user} more.",
    "{user}, bad dates... just like {user}.",
    "{user}, he chose... poorly. Just like {user}.",
    "{user}, this belongs in a museum! Unlike {user}, who belongs nowhere.",
    "{user}, I'm making this up as I go... which is also {user}'s life strategy.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # DUMB AND DUMBER / ACE VENTURA / COMEDIES (8 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, so you're telling me there's a chance... and {user} clings to it.",
    "{user}, I like you, Mary. I like you a lot... unlike {user}.",
    "{user}, we got no food, we got no jobs, our pets heads are falling off! {user}'s life summary.",
    "{user}, alllllrighty then! Ace Ventura, pet detective... {user}, failure detective.",
    "{user}, lo-hoo-sa-her! {user} in a nutshell.",
    "{user}, do not go in there! {user} went in there.",
    "{user}, like a glove! Which doesn't fit {user}.",
    "{user}, your request is impossible! Like {user} succeeding.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # WEDDING CRASHERS / OLD SCHOOL / ANCHORMAN / COMEDIES (8 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, ma! The meatloaf! {user} wants it now!",
    "{user}, you're my boy, Blue! But not {user}.",
    "{user}, we're going streaking! {user} is streaking through failure.",
    "{user}, 60% of the time, it works every time... except for {user}.",
    "{user}, that escalated quickly! Like {user}'s failure rate.",
    "{user}, stay classy, San Diego... unlike {user}.",
    "{user}, I love lamp... {user} loves losing.",
    "{user}, milk was a bad choice! Just like choosing {user}.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # THE DEPARTED / THE WIRE / CRIME DRAMAS (8 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, I'm the guy who does his job. You must be the other guy... {user}.",
    "{user}, I'm a cop killer! Well, {user} is a hope killer.",
    "{user}, she fell funny! {user} falls regularly.",
    "{user}, I'm an undercover cop! {user} is undercover incompetent.",
    "{user}, you come at the king, you best not miss... {user} misses always.",
    "{user}, Omar comin'! Hide {user}!",
    "{user}, the king stay the king... {user} stays {user}.",
    "{user}, all in the game, yo... and {user} loses the game.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # THE LION KING / DISNEY ANIMATED CLASSICS (10 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, hakuna matata... what {user} says after every failure.",
    "{user}, remember who you are... not that it helps {user}.",
    "{user}, the past can hurt... and {user}'s present hurts too.",
    "{user}, everything the light touches is our kingdom... except where {user} stands.",
    "{user}, long live the king! Not {user}, though.",
    "{user}, I'm surrounded by idiots... especially {user}.",
    "{user}, be prepared! For {user} to fail.",
    "{user}, a dream is a wish your heart makes... {user}'s heart must be silent.",
    "{user}, let it go! {user} should let everything go.",
    "{user}, I just can't wait to be king! {user} can't wait for anything.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # TOY STORY / FINDING NEMO / PIXAR CLASSICS (10 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, to infinity and beyond! But you're stuck at zero.",
    "{user}, there's a snake in my boot! And it's {user}.",
    "{user}, you've got a friend in me! But not {user}.",
    "{user}, just keep swimming! {user} sinks.",
    "{user}, fish are friends, not food... {user} is neither.",
    "{user}, I shall call him Squishy and he shall be mine... {user} is squished.",
    "{user}, adventure is out there! But {user} stays inside.",
    "{user}, the claw chooses who will go and who will stay... the claw rejected {user}.",
    "{user}, I don't want to survive, I want to live... {user} does neither.",
    "{user}, our fate lives within us, you only have to be brave enough to see it... {user} isn't brave.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # THE NOTEBOOK / DIRTY DANCING / ROMANCE CLASSICS (8 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, I'll never let go, Jack... but I'd definitely let go of {user}.",
    "{user}, you jump, I jump, remember? Please jump, {user}.",
    "{user}, if you're a bird, I'm a bird... but you're not a bird, {user}.",
    "{user}, nobody puts Baby in a corner... but we put {user} everywhere they don't belong.",
    "{user}, I carried a watermelon... {user} carries disappointment.",
    "{user}, I have the time of my life! {user} has the worst.",
    "{user}, nobody puts {user} in the corner... because nobody wants them there anyway.",
    "{user}, love means never having to say you're sorry... {user} should apologize anyway.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # THE BIG LEBOWSKI / OFFICE SPACE / CULT CLASSICS (8 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, the Dude abides... {user} does not.",
    "{user}, that rug really tied the room together... unlike {user}.",
    "{user}, yeah, well, you know, that's just, like, your opinion, man... {user}'s opinion doesn't matter.",
    "{user}, I don't roll on Shabbos! {user} doesn't roll at all.",
    "{user}, the Bobs are here to see you... and fire {user}.",
    "{user}, I believe you have my stapler... {user} can't keep anything.",
    "{user}, PC load letter? What does that mean?! Like {user}, it means nothing.",
    "{user}, I'm gonna need you to go ahead and come in tomorrow... so we can discuss {user}'s failures.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # PULP FICTION / RESERVOIR DOGS / TARANTINO FILMS (10 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, they call it a Royale with cheese... they call {user} a failure with cheese.",
    "{user}, Ezekiel 25:17... the path of the righteous man is beset on all sides... unlike {user}'s path.",
    "{user}, say 'what' again! I dare you! {user} says 'what' constantly.",
    "{user}, are you gonna bark all day, little doggie, or are you gonna bite? {user} just barks.",
    "{user}, I don't tip... and I don't respect {user}.",
    "{user}, we're gonna be like three little Fonzies here... and what's Fonzie like? Cool! {user} is not.",
    "{user}, I love the smell of napalm in the morning... it smells like {user}'s defeat.",
    "{user}, you gonna pull those pistols or whistle Dixie? {user} just whistles.",
    "{user}, I'm gonna take his car... I'm gonna drive to {user}'s house... and tell them they're a failure.",
    "{user}, boys, don't do it! {user} did it anyway.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # GOOD WILL HUNTING / DEAD POETS SOCIETY / DRAMAS (8 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, it's not your fault... actually, it is {user}'s fault.",
    "{user}, how do you like them apples? Not as much as avoiding {user}.",
    "{user}, my boy's wicked smart... unlike {user}.",
    "{user}, Carpe Diem. Seize the day, boys. Make your lives extraordinary... {user} makes theirs ordinary.",
    "{user}, O Captain! My Captain! {user} is the cabin boy.",
    "{user}, we're not laughing at you, we're laughing near you... {user}.",
    "{user}, you don't know about real loss... 'cause that only occurs when you've loved something more than you love yourself... {user} only loves themselves.",
    "{user}, your move, chief... and {user} is checkmated.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # A FEW GOOD MEN / THE SOCIAL NETWORK / LEGAL DRAMAS (8 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, you can't handle the truth! Especially not about yourself.",
    "{user}, you fucking people... {user} in a nutshell.",
    "{user}, I want the truth! You can't handle the truth! {user} can't handle anything.",
    "{user}, you're goddamn right I did! Unlike {user}, who does nothing right.",
    "{user}, a million dollars isn't cool. You know what's cool? Not being {user}.",
    "{user}, I invented Facebook! {user} invented disappointment.",
    "{user}, you're not an asshole, Mark. You're just trying so hard to be... {user} succeeds at being one.",
    "{user}, did I adequately answer your condescending question? Unlike {user}, who answers nothing.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # CADDYSHACK / GHOSTBUSTERS / COMEDY CLASSICS (8 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, Cinderella story! Outta nowhere! A former greenskeeper, now, about to become the Masters champion... {user} is still a greenskeeper.",
    "{user}, be the ball! {user} is the gutter ball.",
    "{user}, don't sell yourself short, Judge, you're a tremendous slouch... just like {user}.",
    "{user}, who ya gonna call? Ghostbusters! Who ya gonna call for help? Not {user}.",
    "{user}, he slimed me! {user} is the slime.",
    "{user}, dogs and cats living together! Mass hysteria! {user} causes hysteria.",
    "{user}, I am the Gatekeeper. Are you the Keymaster? {user} is the Lockmaster.",
    "{user}, there is no Dana, only Zuul... and {user}.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # SUPERBAD / HANGOVER / KNOCKED UP / MODERN COMEDIES (8 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, I am McLovin! {user} is McLovin' to fail.",
    "{user}, one man's trash is another man's treasure... {user} is just trash.",
    "{user}, what happens in Vegas, stays in Vegas... except {user}'s shame, which follows everywhere.",
    "{user}, we're the three best friends that anybody could have! Not including {user}.",
    "{user}, I'm a stay-at-home dad! {user} is a stay-at-failure.",
    "{user}, you know how they say to love something is to let it go? {user} needs to be let go.",
    "{user}, fuck yeah! {user} says after achieving mediocrity.",
    "{user}, I'm gonna be sick... looking at {user}'s results.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # INCEPTION / INTERSTELLAR / NOLAN FILMS (8 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, you mustn't be afraid to dream a little bigger, darling... though {user} should be afraid.",
    "{user}, wait, whose subconscious are we going into, exactly? {user}'s, but it's empty.",
    "{user}, you need to take responsibility for your own actions, Dom... {user} never does.",
    "{user}, an idea is like a virus... resilient, highly contagious... {user} has no ideas.",
    "{user}, once an idea has taken hold of the brain it's almost impossible to eradicate... except {user}'s ideas, which never take hold.",
    "{user}, we used to look up at the sky and wonder at our place in the stars... now we just look down and worry about {user}.",
    "{user}, love is the one thing we're capable of perceiving that transcends dimensions of time and space... {user} transcends nothing.",
    "{user}, Murphy's law doesn't mean that something bad will happen. What it means is whatever can happen, will happen... and {user} happens.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # TOP GUN / STEEL MAGNOLIAS / VARIOUS (8 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, I feel the need... the need for {user} to leave.",
    "{user}, you can be my wingman anytime! Said no one to {user}.",
    "{user}, talk to me, Goose! Even Goose doesn't talk to {user}.",
    "{user}, that was some of the best flying I've seen to date! Not from {user}.",
    "{user}, I'm always on top, baby! {user} is always on bottom.",
    "{user}, the only thing that separates us from the animals is our ability to accessorize... {user} can't accessorize.",
    "{user}, I would rather have thirty minutes of wonderful than a lifetime of nothing special... {user} has neither.",
    "{user}, laughter through tears is my favorite emotion... {user} provides tears only.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # WIZARD OF OZ / MARY POPPINS / MUSICAL CLASSICS (8 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, there's no place like home... which is where you should stay.",
    "{user}, Toto, I've a feeling we're not in Kansas anymore... we're in {user}'s disaster zone.",
    "{user}, pay no attention to that man behind the curtain! It's {user} pretending to have skills.",
    "{user}, I'll get you, my pretty, and your little dog too! Said the job market to your dreams.",
    "{user}, follow the yellow brick road! {user} got lost immediately.",
    "{user}, a spoonful of sugar helps the medicine go down... {user} needs a barrel.",
    "{user}, supercalifragilisticexpialidocious! The opposite of describing {user}.",
    "{user}, practically perfect in every way! The opposite of {user}.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # THE SIXTH SENSE / THE OTHERS / UNBREAKABLE / SHYAMALAN (6 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, I see dead people... and you're killing my vibe.",
    "{user}, they don't know they're dead... like {user} doesn't know they're failing.",
    "{user}, I am not afraid anymore... of anything. Except {user}.",
    "{user}, sometimes, children are like that... like {user}.",
    "{user}, we are all vulnerable... especially to {user}'s incompetence.",
    "{user}, it's happening... {user} is failing again.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # THE HUNGER GAMES / TWILIGHT / DIVERGENT / YA MOVIES (8 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, may the odds be ever in your favor... they aren't, {user}.",
    "{user}, I volunteer as tribute! To replace {user}.",
    "{user}, and so it was decreed that each year, the 12 districts of Panem shall offer up in tribute... {user}.",
    "{user}, I am not pretty. I am not beautiful. I am as radiant as the sun... said no one about {user}.",
    "{user}, a diamond bullet right through the forehead! {user} needs that bullet.",
    "{user}, fear doesn't shut you down, it wakes you up... {user} stays asleep.",
    "{user}, be brave, Tris... {user} is not.",
    "{user}, human nature is the enemy... specifically {user}'s nature.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # THE DEVIL WEARS PRADA / JULIE & JULIA / CHICK FLICKS (6 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, that's all... that's all? That's all you have for me? {user} has nothing.",
    "{user}, florals? For spring? Groundbreaking... unlike anything {user} does.",
    "{user}, let me know when your whole life goes up in smoke... {user}'s life is ashes.",
    "{user}, I love my cheese! {user} loves their excuses.",
    "{user}, you're not that similar to Julia Child... or anyone successful, {user}.",
    "{user}, what if I fall? Oh, but my darling, what if you fly? {user} won't.",
]

# ═══════════════════════════════════════════════════════════════════════════════
# PEOPLE QUOTES - 210+ famous quotes adapted for trolling (50+ people)
# ═══════════════════════════════════════════════════════════════════════════════

PEOPLE_QUOTES: List[str] = [
    # ═══════════════════════════════════════════════════════════════════════════════
    # SCIENTISTS & INVENTORS
    # ═══════════════════════════════════════════════════════════════════════════════
    
    # Albert Einstein (10 quotes)
    "{user}, insanity is doing the same thing over and over again and expecting different results... so you're basically insane.",
    "{user}, everybody is a genius. But if you judge a fish by its ability to climb a tree, it will live its whole life believing it is stupid... and {user} is that fish.",
    "{user}, two things are infinite: the universe and human stupidity; and I'm not sure about the universe... but I'm sure about {user}.",
    "{user}, try not to become a man of success, but rather try to become a man of value... too late for you.",
    "{user}, if you can't explain it simply, you don't understand it well enough... which explains why {user} never explains anything.",
    "{user}, imagination is more important than knowledge... and you have neither.",
    "{user}, the difference between stupidity and genius is that genius has its limits... {user} has no limits on stupidity.",
    "{user}, a person who never made a mistake never tried anything new... {user} must be very experienced then.",
    "{user}, the important thing is not to stop questioning... {user} stopped at birth.",
    "{user}, life is like riding a bicycle. To keep your balance, you must keep moving... {user} fell off immediately.",

    # Isaac Newton (6 quotes)
    "{user}, if I have seen further it is by standing on the shoulders of Giants... {user} is standing on the shoulders of ants.",
    "{user}, I can calculate the motion of heavenly bodies, but not the madness of {user}.",
    "{user}, every action has an equal and opposite reaction... {user} only has inaction.",
    "{user}, nature is pleased with simplicity... which is why nature rejects {user}.",
    "{user}, what we know is a drop, what we don't know is an ocean... {user} is the empty part.",
    "{user}, gravity explains the motions of the planets, but it cannot explain {user}.",

    # Nikola Tesla (5 quotes)
    "{user}, the present is theirs; I, for one, dwell in the future... {user} dwells in the past.",
    "{user}, I don't care that they stole my idea... I care that they didn't steal {user}'s, because it's worthless.",
    "{user}, the day science begins to study non-physical phenomena... they'll skip {user}.",
    "{user}, our virtues and our failings are inseparable, like force and matter... {user} has only failings.",
    "{user}, be alone, that is the secret of invention... {user} has that part mastered.",

    # Thomas Edison (5 quotes)
    "{user}, genius is one percent inspiration and ninety-nine percent perspiration... {user} is zero percent both.",
    "{user}, I have not failed. I've just found 10,000 ways that won't work... {user} found 10,001.",
    "{user}, our greatest weakness lies in giving up... {user}'s greatest strength.",
    "{user}, opportunity is missed by most people because it is dressed in overalls and looks like work... {user} misses all opportunities.",
    "{user}, many of life's failures are people who did not realize how close they were to success when they gave up... {user} gave up at the starting line.",

    # Marie Curie (4 quotes)
    "{user}, nothing in life is to be feared, it is only to be understood... and {user} is terrifying.",
    "{user}, life is not easy for any of us. But what of that? We must have perseverance... {user} has none.",
    "{user}, be less curious about people and more curious about ideas... {user} is curious about neither.",
    "{user}, first principle: never let oneself be beaten down by malice... {user} is already beaten.",

    # Charles Darwin (4 quotes)
    "{user}, it is not the strongest of the species that survives, nor the most intelligent... {user} is proof.",
    "{user}, a man who dares to waste one hour of time has not discovered the value of life... {user} wastes decades.",
    "{user}, ignorance more frequently begets confidence than does knowledge... {user} is very confident.",
    "{user}, the love for all living creatures is the most noble attribute of man... {user} lacks it.",

    # Stephen Hawking (4 quotes)
    "{user}, however difficult life may seem, there is always something you can do and succeed at... except {user}.",
    "{user}, intelligence is the ability to adapt to change... {user} cannot adapt.",
    "{user}, while there's life, there is hope... but {user} tests that theory.",
    "{user}, my advice to other disabled people would be to concentrate on things your disability doesn't prevent you doing well... {user} has no excuse.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # POLITICAL LEADERS
    # ═══════════════════════════════════════════════════════════════════════════════

    # Winston Churchill (8 quotes)
    "{user}, success is not final, failure is not fatal: it is the courage to continue that counts... which is why {user} has no success.",
    "{user}, if you're going through hell, keep going... that's where {user} lives anyway.",
    "{user}, you have enemies? Good. That means you've stood up for something... or you're just {user}.",
    "{user}, the greatest lesson in life is to know that even fools are right sometimes... {user} hasn't had that lesson yet.",
    "{user}, continuous effort — not strength or intelligence — is the key to unlocking our potential... {user} should try effort sometime.",
    "{user}, attitude is a little thing that makes a big difference... {user} has a little attitude and makes no difference.",
    "{user}, we make a living by what we get, but we make a life by what we give... {user} takes everything.",
    "{user}, history will be kind to me for I intend to write it... {user} won't be in it.",

    # Abraham Lincoln (6 quotes)
    "{user}, whatever you are, be a good one... {user} failed at both.",
    "{user}, the best way to predict your future is to create it... {user} predicted failure accurately.",
    "{user}, nearly all men can stand adversity, but if you want to test a man's character, give him power... {user} failed both tests.",
    "{user}, better to remain silent and be thought a fool than to speak out and remove all doubt... {user} speaks constantly.",
    "{user}, in the end, it's not the years in your life that count. It's the life in your years... {user} has neither.",
    "{user}, I walk slowly, but I never walk backward... {user} walks backward only.",

    # John F. Kennedy (5 quotes)
    "{user}, ask not what your country can do for you — ask what you can do for your country... {user} asks for handouts.",
    "{user}, we choose to go to the moon in this decade and do the other things, not because they are easy, but because they are hard... {user} chooses the easy route and still fails.",
    "{user}, those who dare to fail miserably can achieve greatly... {user} only achieves the first part.",
    "{user}, change is the law of life. And those who look only to the past or present are certain to miss the future... {user} misses everything.",
    "{user}, forgive your enemies, but never forget their names... {user}'s name is unforgettable for wrong reasons.",

    # Franklin D. Roosevelt (5 quotes)
    "{user}, the only thing we have to fear is fear itself... and {user}.",
    "{user}, it is common sense to take a method and try it. If it fails, admit it frankly and try another... {user} keeps failing the same way.",
    "{user}, men are not prisoners of fate, but only prisoners of their own minds... {user}'s mind is minimum security.",
    "{user}, happiness lies in the joy of achievement and the thrill of creative effort... {user} knows neither joy.",
    "{user}, when you reach the end of your rope, tie a knot in it and hang on... {user} let go.",

    # Theodore Roosevelt (8 quotes - already had some)
    "{user}, believe you can and you're halfway there... {user} hasn't started.",
    "{user}, do what you can, with what you have, where you are... {user} does nothing, with nothing, nowhere.",
    "{user}, it is hard to fail, but it is worse never to have tried to succeed... {user} found a way to do both.",
    "{user}, nobody cares how much you know, until they know how much you care... and {user} knows nothing and cares less.",
    "{user}, speak softly and carry a big stick... {user} speaks loudly and carries nothing.",
    "{user}, the only man who never makes a mistake is the man who never does anything... so {user} must do a lot.",
    "{user}, keep your eyes on the stars, and your feet on the ground... {user} has their feet in their mouth.",
    "{user}, far and away the best prize that life offers is the chance to work hard at work worth doing... {user} offers no prizes.",

    # Ronald Reagan (4 quotes)
    "{user}, Mr. Gorbachev, tear down this wall! Mr. {user}, build up some skills!",
    "{user}, the greatest leader is not necessarily one who does the greatest things... clearly not {user}.",
    "{user}, there are no great limits to growth because there are no limits of human intelligence... {user} found the limits.",
    "{user}, peace is not absence of conflict, it is the ability to handle conflict by peaceful means... {user} creates conflict.",

    # Nelson Mandela (4 quotes)
    "{user}, it always seems impossible until it's done... {user} makes it impossible.",
    "{user}, the greatest glory in living lies not in never falling, but in rising every time we fall... {user} stays down.",
    "{user}, education is the most powerful weapon which you can use to change the world... {user} is unarmed.",
    "{user}, do not judge me by my successes, judge me by how many times I fell down and got back up... {user} just counts the falls.",

    # Mahatma Gandhi (5 quotes)
    "{user}, be the change that you wish to see in the world... {user} changes nothing.",
    "{user}, live as if you were to die tomorrow. Learn as if you were to live forever... {user} does neither.",
    "{user}, an eye for an eye will only make the whole world blind... {user} is already blind to their faults.",
    "{user}, the weak can never forgive. Forgiveness is the attribute of the strong... {user} is weak.",
    "{user}, happiness is when what you think, what you say, and what you do are in harmony... {user} is always out of tune.",

    # Martin Luther King Jr. (5 quotes)
    "{user}, I have a dream... that {user} would get better. Still dreaming.",
    "{user}, darkness cannot drive out darkness: only light can do that... {user} brings only darkness.",
    "{user}, the time is always right to do what is right... {user} always chooses wrong.",
    "{user}, our lives begin to end the day we become silent about things that matter... {user} was silent from birth.",
    "{user}, faith is taking the first step even when you don't see the whole staircase... {user} won't climb.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # WRITERS & PHILOSOPHERS
    # ═══════════════════════════════════════════════════════════════════════════════

    # Mark Twain (10 quotes)
    "{user}, never argue with stupid people, they will drag you down to their level and then beat you with experience... {user} is undefeated.",
    "{user}, the secret of getting ahead is getting started... {user} is keeping that secret very well.",
    "{user}, whenever you find yourself on the side of the majority, it is time to pause and reflect... {user} pauses but never reflects.",
    "{user}, never put off till tomorrow what may be done day after tomorrow just as well... {user}'s life motto.",
    "{user}, classic: a book which people praise and don't read... like {user}'s resume.",
    "{user}, go to Heaven for the climate, Hell for the company... {user} brings Hell everywhere they go.",
    "{user}, the two most important days in your life are the day you are born and the day you find out why... {user} is still waiting for the second one.",
    "{user}, it's not the size of the dog in the fight, it's the size of the fight in the dog... {user} is a very small dog.",
    "{user}, don't let schooling interfere with your education... {user} let both interfere with existing.",
    "{user}, a person with a new idea is a crank until the idea succeeds... {user} is just a crank.",

    # Oscar Wilde (10 quotes)
    "{user}, be yourself; everyone else is already taken... and nobody wants to take {user}.",
    "{user}, to live is the rarest thing in the world. Most people exist, that is all... {user} barely manages that.",
    "{user}, true friends stab you in the front... {user} gets stabbed everywhere.",
    "{user}, I am so clever that sometimes I don't understand a single word of what I am saying... {user} is the opposite.",
    "{user}, some cause happiness wherever they go; others whenever they go... we know which one {user} is.",
    "{user}, always forgive your enemies; nothing annoys them so much... but {user}'s enemies don't need forgiveness, they need apologies.",
    "{user}, you can never be overdressed or overeducated... {user} disproves both.",
    "{user}, I have nothing to declare except my genius... {user} has nothing to declare.",
    "{user}, there is only one thing in the world worse than being talked about, and that is not being talked about... {user} achieved the worse option.",
    "{user}, we are all in the gutter, but some of us are looking at the stars... {user} is eating gutter food.",

    # William Shakespeare (10 quotes)
    "{user}, to be or not to be... {user} should pick 'not to be'.",
    "{user}, all the world's a stage, and all the men and women merely players... {user} is the understudy who never gets called.",
    "{user}, better to remain silent and be thought a fool than to speak and to remove all doubt... {user} speaks constantly.",
    "{user}, the fault, dear Brutus, is not in our stars, but in ourselves... specifically in {user}.",
    "{user}, hell is empty and all the devils are here... {user} brought them.",
    "{user}, some are born great, some achieve greatness, and some have greatness thrust upon them... {user} missed all three.",
    "{user}, love all, trust a few, do wrong to none... {user} does wrong to everyone.",
    "{user}, we know what we are, but know not what we may be... {user} will never be anything.",
    "{user}, the course of true love never did run smooth... especially when {user} is involved.",
    "{user}, no legacy is so rich as honesty... {user} is broke.",

    # Friedrich Nietzsche (6 quotes)
    "{user}, that which does not kill us makes us stronger... {user} must be immortal then.",
    "{user}, he who has a why to live can bear almost any how... {user} has no why.",
    "{user}, without music, life would be a mistake... {user} is a mistake regardless.",
    "{user}, there are no facts, only interpretations... and all interpretations of {user} are bad.",
    "{user}, the individual has always had to struggle to keep from being overwhelmed by the tribe... {user} was overwhelmed at birth.",
    "{user}, to live is to suffer, to survive is to find some meaning in the suffering... {user} suffers without meaning.",

    # Socrates / Plato / Aristotle (8 quotes)
    "{user}, the unexamined life is not worth living... {user} should examine something.",
    "{user}, I know that I know nothing... {user} doesn't even know that much.",
    "{user}, wonder is the beginning of wisdom... {user} is wise to nothing.",
    "{user}, we are what we repeatedly do. Excellence, then, is not an act, but a habit... {user} repeatedly fails.",
    "{user}, the whole is greater than the sum of its parts... {user} is less than any part.",
    "{user}, happiness depends upon ourselves... {user} depends upon everyone else.",
    "{user}, good people do not need laws to tell them to act responsibly... {user} needs all the laws.",
    "{user}, courage is the first of human qualities because it is the quality which guarantees the others... {user} has no courage.",

    # Ralph Waldo Emerson (5 quotes)
    "{user}, do not go where the path may lead, go instead where there is no path and leave a trail... {user} gets lost on the path.",
    "{user}, what lies behind us and what lies before us are tiny matters compared to what lies within us... {user} is empty within.",
    "{user}, to be yourself in a world that is constantly trying to make you something else is the greatest accomplishment... {user} failed.",
    "{user}, our greatest glory is not in never failing, but in rising up every time we fail... {user} stays down.",
    "{user}, the only way to have a friend is to be one... {user} has no friends.",

    # Henry David Thoreau (4 quotes)
    "{user}, go confidently in the direction of your dreams... {user} has no confidence or dreams.",
    "{user}, our life is frittered away by detail... simplify, simplify... {user} complicates everything.",
    "{user}, rather than love, than money, than fame, give me truth... {user} gives none.",
    "{user}, the mass of men lead lives of quiet desperation... {user} is loud about it.",

    # Confucius (9 quotes)
    "{user}, it does not matter how slowly you go as long as you do not stop... {user} found a way to go slowly AND stop.",
    "{user}, everything has beauty, but not everyone sees it... especially not when looking at {user}.",
    "{user}, our greatest glory is not in never falling, but in rising every time we fall... {user} is still on the ground.",
    "{user}, when it is obvious that the goals cannot be reached, don't adjust the goals, adjust the action steps... {user} does neither.",
    "{user}, wherever you go, go with all your heart... {user} goes nowhere with any heart.",
    "{user}, silence is a true friend who never betrays... {user} should try silence sometime.",
    "{user}, real knowledge is to know the extent of one's ignorance... {user} must be very knowledgeable then.",
    "{user}, the superior man thinks always of virtue; the common man thinks of comfort... {user} thinks of neither.",
    "{user}, choose a job you love, and you will never have to work a day in your life... {user} chose unemployment.",

    # Benjamin Franklin (9 quotes)
    "{user}, an investment in knowledge pays the best interest... {user} is broke.",
    "{user}, well done is better than well said... {user} does neither well.",
    "{user}, tell me and I forget. Teach me and I remember. Involve me and I learn... Avoid {user} and I stay sane.",
    "{user}, by failing to prepare, you are preparing to fail... {user} is always prepared then.",
    "{user}, in this world nothing can be said to be certain, except death and taxes... and {user}'s mistakes.",
    "{user}, lost time is never found again... {user} has lost plenty.",
    "{user}, early to bed and early to rise makes a man healthy, wealthy and wise... {user} sleeps through wisdom.",
    "{user}, guests, like fish, begin to smell after three days... {user} smells immediately.",
    "{user}, he that can have patience can have what he will... {user} has no patience and gets nothing.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # BUSINESS LEADERS & ENTREPRENEURS
    # ═══════════════════════════════════════════════════════════════════════════════

    # Steve Jobs (8 quotes)
    "{user}, stay hungry, stay foolish... {user} achieved both effortlessly.",
    "{user}, innovation distinguishes between a leader and a follower... {user} is neither.",
    "{user}, your time is limited, don't waste it living someone else's life... {user} wastes it living no life.",
    "{user}, the people who are crazy enough to think they can change the world are the ones who do... {user} is just crazy.",
    "{user}, simplicity is the ultimate sophistication... {user} is simply unsophisticated.",
    "{user}, I want to put a ding in the universe... {user} is the ding.",
    "{user}, design is not just what it looks like and feels like. Design is how it works... {user} doesn't work.",
    "{user}, sometimes when you innovate, you make mistakes. It is best to admit them quickly... {user} makes them slowly.",

    # Bill Gates (4 quotes)
    "{user}, it's fine to celebrate success but it is more important to heed the lessons of failure... {user} has many lessons.",
    "{user}, 640K ought to be enough for anybody... except {user}, who needs more help.",
    "{user}, if you are born poor it's not your mistake, but if you die poor it's your mistake... {user} finds ways to fail regardless.",
    "{user}, your most unhappy customers are your greatest source of learning... {user} has many teachers.",

    # Warren Buffett (4 quotes)
    "{user}, the difference between successful people and really successful people is that really successful people say no to almost everything... {user} says yes to failure.",
    "{user}, price is what you pay. Value is what you get... {user} has negative value.",
    "{user}, it takes 20 years to build a reputation and five minutes to ruin it... {user} ruined theirs instantly.",
    "{user}, risk comes from not knowing what you're doing... {user} is all risk.",

    # Elon Musk (4 quotes)
    "{user}, when something is important enough, you do it even if the odds are not in your favor... {user} doesn't do it anyway.",
    "{user}, I think it is possible for ordinary people to choose to be extraordinary... {user} chose not to.",
    "{user}, failure is an option here. If things are not failing, you are not innovating enough... {user} is very innovative.",
    "{user}, persistence is very important. You should not give up unless you are forced to give up... {user} gives up voluntarily.",

    # Jeff Bezos (3 quotes)
    "{user}, your brand is what people say about you when you're not in the room... {user} is not discussed.",
    "{user}, if you don't understand the details of your business you are going to fail... {user} fails anyway.",
    "{user}, work hard, have fun, make history... {user} does none of these.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # ATHLETES & SPORTS FIGURES
    # ═══════════════════════════════════════════════════════════════════════════════

    # Michael Jordan (5 quotes)
    "{user}, I've missed more than 9000 shots in my career... {user} has missed more opportunities.",
    "{user}, I've failed over and over again in my life. And that is why I succeed... {user} just fails.",
    "{user}, talent wins games, but teamwork and intelligence win championships... {user} has neither.",
    "{user}, you must expect great things of yourself before you can do them... {user} expects nothing.",
    "{user}, some people want it to happen, some wish it would happen, others make it happen... {user} watches it not happen.",

    # Muhammad Ali (5 quotes)
    "{user}, float like a butterfly, sting like a bee... {user} falls like a rock.",
    "{user}, I am the greatest, I said that even before I knew I was... {user} knew they weren't.",
    "{user}, don't count the days, make the days count... {user} counts failures.",
    "{user}, service to others is the rent you pay for your room here on earth... {user} is behind on rent.",
    "{user}, he who is not courageous enough to take risks will accomplish nothing in life... {user} accomplishes nothing anyway.",

    # Babe Ruth (3 quotes)
    "{user}, every strike brings me closer to the next home run... {user} only strikes out.",
    "{user}, yesterday's home runs don't win today's games... {user} never had home runs.",
    "{user}, heroes get remembered, but legends never die... {user} is neither.",

    # Vince Lombardi (4 quotes)
    "{user}, winners never quit and quitters never win... {user} never wins.",
    "{user}, it's not whether you get knocked down, it's whether you get up... {user} stays down.",
    "{user}, perfection is not attainable, but if we chase perfection we can catch excellence... {user} catches nothing.",
    "{user}, the only place success comes before work is in the dictionary... {user} skipped both.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # ENTERTAINERS & ARTISTS
    # ═══════════════════════════════════════════════════════════════════════════════

    # Marilyn Monroe (4 quotes)
    "{user}, imperfection is beauty, madness is genius and it's better to be absolutely ridiculous than absolutely boring... {user} is boring.",
    "{user}, give a girl the right shoes, and she can conquer the world... {user} has the wrong shoes.",
    "{user}, we are all of us stars, and we deserve to twinkle... {user} is a black hole.",
    "{user}, if you can't handle me at my worst, then you sure as hell don't deserve me at my best... {user} has no best.",

    # Elvis Presley (3 quotes)
    "{user}, I'm not trying to be sexy. It's just my way of expressing myself when I move around... {user} expresses nothing.",
    "{user}, truth is like the sun. You can shut it out for a time, but it ain't going away... {user}'s truth is always visible.",
    "{user}, ambition is a dream with a V8 engine... {user} has a broken tricycle.",

    # John Lennon (4 quotes)
    "{user}, life is what happens when you're busy making other plans... {user} makes no plans.",
    "{user}, you may say I'm a dreamer, but I'm not the only one... {user} is awake and failing.",
    "{user}, imagine all the people living life in peace... {user} imagines success.",
    "{user}, time you enjoy wasting, was not wasted... {user} wastes time miserably.",

    # Lady Gaga (3 quotes)
    "{user}, I'm beautiful in my way 'cause God makes no mistakes... God made an exception for {user}.",
    "{user}, don't be a drag, just be a queen... {user} is neither.",
    "{user}, some women choose to follow men, and some women choose to follow their dreams... {user} follows nothing.",

    # Oprah Winfrey (4 quotes)
    "{user}, turn your wounds into wisdom... {user} has many wounds, no wisdom.",
    "{user}, the biggest adventure you can take is to live the life of your dreams... {user} takes no adventures.",
    "{user}, you get in life what you have the courage to ask for... {user} lacks courage.",
    "{user}, doing the best at this moment puts you in the best place for the next moment... {user} is never in the best place.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # VARIOUS PROVERBS & SAYINGS
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user}, a penny saved is a penny earned... {user} has neither saved nor earned.",
    "{user}, an apple a day keeps the doctor away... {user} keeps everyone away.",
    "{user}, don't count your chickens before they hatch... {user} counts chickens that don't exist.",
    "{user}, every cloud has a silver lining... {user} is the dark cloud.",
    "{user}, good things come to those who wait... {user} has been waiting a long time.",
    "{user}, if at first you don't succeed, try, try again... {user} has tried and tried and tried.",
    "{user}, it's always darkest before the dawn... {user} lives in permanent midnight.",
    "{user}, laughter is the best medicine... {user} is the disease.",
    "{user}, money doesn't grow on trees... {user} still tries to harvest it.",
    "{user}, people who live in glass houses shouldn't throw stones... {user} lives in a cardboard house and still throws stones.",
    "{user}, practice makes perfect... {user} must not practice.",
    "{user}, the early bird catches the worm... {user} sleeps in and catches nothing.",
    "{user}, the pen is mightier than the sword... {user} can't wield either.",
    "{user}, there's no such thing as a free lunch... unless you're {user}, who freeloads.",
    "{user}, two wrongs don't make a right... {user} keeps testing this theory.",
    "{user}, when in Rome, do as the Romans do... {user} does the opposite everywhere.",
    "{user}, you can lead a horse to water, but you can't make him drink... {user} can't even find the horse.",
    "{user}, you can't have your cake and eat it too... {user} has no cake.",
    "{user}, absence makes the heart grow fonder... of {user} being absent.",
    "{user}, actions speak louder than words... {user}'s actions whisper 'help'.",
    "{user}, beauty is in the eye of the beholder... and everyone beholds {user} differently, but still disappointingly.",
    "{user}, beggars can't be choosers... {user} is both.",
    "{user}, birds of a feather flock together... {user} flies solo because no birds match that feather.",
    "{user}, cleanliness is next to godliness... {user} is far from both.",
    "{user}, curiosity killed the cat... {user}'s curiosity kills conversations.",
    "{user}, don't bite the hand that feeds you... {user} bites every hand.",
    "{user}, don't put all your eggs in one basket... {user} has no eggs.",
    "{user}, fortune favors the bold... {user} is neither fortunate nor bold.",
    "{user}, great minds think alike... {user} is original in failure.",
    "{user}, honesty is the best policy... {user} fails at honesty too.",
    "{user}, hope for the best, prepare for the worst... {user} prepares for {user}.",
    "{user}, ignorance is bliss... {user} must be ecstatic.",
    "{user}, it's better to give than to receive... {user} does plenty of receiving.",
    "{user}, it's the thought that counts... {user} has no thoughts.",
    "{user}, keep your friends close and your enemies closer... {user} keeps everyone distant.",
    "{user}, knowledge is power... {user} is powerless.",
    "{user}, like father, like son... like {user}, like disappointment.",
    "{user}, look before you leap... {user} leaps without looking, landing, or learning.",
    "{user}, love is blind... especially when it comes to {user}.",
    "{user}, manners maketh man... {user} is unmade.",
    "{user}, nothing ventured, nothing gained... {user} ventures nothing and gains exactly that.",
    "{user}, once bitten, twice shy... {user} keeps getting bitten.",
    "{user}, one man's trash is another man's treasure... {user} is neither.",
    "{user}, patience is a virtue... {user} is not virtuous.",
    "{user}, practice what you preach... {user} preaches nothing and practices less.",
    "{user}, Rome wasn't built in a day... {user} couldn't build Rome in a lifetime.",
    "{user}, the best things in life are free... {user} overpays for everything.",
    "{user}, the grass is always greener on the other side... {user} is on the brown side.",
    "{user}, time heals all wounds... {user} is a wound that time can't heal.",
    "{user}, too many cooks spoil the broth... {user} spoils everything solo.",
    "{user}, where there's a will, there's a way... {user} has neither will nor way.",
    "{user}, you are what you eat... {user} must eat disappointments.",
    "{user}, you can't make an omelette without breaking eggs... {user} breaks eggs and still no omelette.",
]

# ═══════════════════════════════════════════════════════════════════════════════
# RANDOMNESS - 210+ absurd and humorous random trolls
# ═══════════════════════════════════════════════════════════════════════════════

RANDOMNESS_QUOTES: List[str] = [
    # ═══════════════════════════════════════════════════════════════════════════════
    # ABSURD COMPARISONS (60 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user} is the human equivalent of a participation trophy.",
    "{user} has the personality of a loading screen.",
    "If {user} was a spice, they'd be flour.",
    "{user} brings everyone so much joy... when they leave the room.",
    "{user} is like a cloud. When they disappear, it's a beautiful day.",
    "{user} is the reason the gene pool needs a lifeguard.",
    "{user} is proof that evolution can go in reverse.",
    "{user} has their entire life ahead of them... and it's terrifying.",
    "{user} is about as useful as a chocolate teapot.",
    "{user} has a face for radio and a voice for silent films.",
    "{user} is like a software update - always disappointing and never wanted.",
    "{user} would lose a one-person race.",
    "{user} has the situational awareness of a goldfish.",
    "{user} is living proof that you can't fix stupid.",
    "{user} couldn't pour water out of a boot if the instructions were on the heel.",
    "{user} is about as sharp as a mashed potato.",
    "{user} is the reason aliens won't talk to us.",
    "{user} has the energy of a sloth on sedatives.",
    "{user} is like a pizza cutter - all edge and no point.",
    "{user} has the charisma of a damp sponge.",
    "{user} is like a defective traffic light - nobody knows what to do with them.",
    "{user} has the problem-solving skills of a pigeon.",
    "{user} is the human embodiment of a typo.",
    "{user} is the reason they put warning labels on everything.",
    "{user} has the memory of a goldfish... with amnesia.",
    "{user} is like a broken pencil - pointless.",
    "{user} is the type of person who puts pineapple on pizza AND enjoys it.",
    "{user} has the social skills of a lobotomized potato.",
    "{user} is about as subtle as a brick through a window.",
    "{user} is the human version of a buffering video.",
    "{user} has the fashion sense of a colorblind peacock.",
    "{user} is like a participation certificate - technically present but meaningless.",
    "{user} has the grace of a cow on ice skates.",
    "{user} is the reason therapists charge extra.",
    "{user} is about as mysterious as a glass house.",
    "{user} has the wit of a soggy napkin.",
    "{user} is like a screensaver - mildly interesting for 5 seconds, then forgotten.",
    "{user} has the decision-making skills of a magic 8-ball filled with 'ask again later'.",
    "{user} is the human equivalent of a 404 error.",
    "{user} is like a backup plan for a backup plan - completely unnecessary.",
    "{user} has the athletic ability of a garden gnome.",
    "{user} is about as exciting as watching paint dry... in slow motion.",
    "{user} has the emotional intelligence of a toaster.",
    "{user} is like a default setting - nobody chooses them on purpose.",
    "{user} has the strategic thinking of a headless chicken.",
    "{user} is about as reliable as a chocolate fireguard.",
    "{user} is like a pop-up ad - annoying and immediately closed.",
    "{user} has the rhythm of a malfunctioning washing machine.",
    "{user} is about as welcome as a mosquito at a nudist colony.",
    "{user} has the self-awareness of a houseplant.",
    "{user} is like a typo in a word document - immediately noticed and frustrating.",
    "{user} is the human version of a spam email.",
    "{user} has the coordination of a newborn giraffe on roller skates.",
    "{user} is about as useful as a solar-powered flashlight.",
    "{user} is like a wet blanket at a beach party.",
    "{user} has the culinary skills of a vending machine.",
    "{user} is about as funny as a tax audit.",
    "{user} has the navigational skills of a blindfolded mole.",
    "{user} is like a buffering YouTube video - frustrating and time-wasting.",
    "{user} is the reason they invented 'unfriend' buttons.",
    "{user} has the attention span of a distracted goldfish.",
    "{user} is about as welcome as a skunk at a perfume convention.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # TECH CONFUSION (40 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user} probably thinks Excel is a dating app.",
    "{user} probably thinks 'Bluetooth' is a dental condition.",
    "{user} probably asks for directions to the internet.",
    "{user} probably thinks 'WIFI' is a type of martial art.",
    "{user} probably thinks 'spam' is just a type of canned meat.",
    "{user} probably uses a GPS to find their way out of a paper bag.",
    "{user} probably thinks 'streaming' is something you do in a kayak.",
    "{user} probably thinks 'cloud storage' is where angels keep their stuff.",
    "{user} probably thinks 'hashtag' is a type of potato preparation.",
    "{user} probably thinks 'CPU' is a type of soup.",
    "{user} probably thinks 'PDF' is a type of sandwich.",
    "{user} probably thinks 'USB' is a type of university degree.",
    "{user} probably thinks 'RAM' is a type of male sheep.",
    "{user} probably thinks 'HTML' is how you text 'laughing'.",
    "{user} probably thinks 'GIF' is pronounced with a hard G.",
    "{user} probably thinks 'URL' is the sound a dog makes.",
    "{user} probably thinks 'trolling' is a type of fishing they could actually do.",
    "{user} probably thinks 'meme' is pronounced 'me-me'.",
    "{user} probably thinks 'emoji' is a type of Japanese martial art.",
    "{user} probably thinks 'virus' only refers to biological ones.",
    "{user} probably thinks 'cookie' is only a baked good.",
    "{user} probably thinks 'firewall' is part of a medieval castle.",
    "{user} probably uses 'password123' for everything.",
    "{user} probably puts their phone in airplane mode and expects it to fly.",
    "{user} probably uses a calculator to figure out 2+2.",
    "{user} probably uses a dictionary to look up the word 'dictionary'.",
    "{user} probably uses a dictionary to spell 'dictionary'.",
    "{user} probably thinks 'screenshot' is a photo of their monitor with a camera.",
    "{user} probably thinks 'download' means taking something off a ladder.",
    "{user} probably thinks 'upload' is when you put something up high.",
    "{user} probably thinks 'backup' is when you reverse your car.",
    "{user} probably thinks 'cache' is where you store your money.",
    "{user} probably thinks 'IP address' is where you mail things to the internet.",
    "{user} probably thinks 'domain' is a kingdom ruled by a dot-com.",
    "{user} probably thinks 'server' is someone who brings you food.",
    "{user} probably thinks 'data' is something from Star Trek.",
    "{user} probably thinks 'hardware' is metal stuff at the store.",
    "{user} probably thinks 'software' is comfortable pajamas.",
    "{user} probably thinks 'desktop' is the top of an actual desk.",
    "{user} probably thinks 'laptop' is when your computer sits on your legs.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # DAILY FAILURES (40 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user} is the type of person who claps when the plane lands.",
    "{user} is the kind of person who microwaves their salad.",
    "{user} probably uses a ruler to measure their feelings.",
    "{user} probably watches how-to videos on how to watch videos.",
    "{user} probably returns ice cream because it's too cold.",
    "{user} is the kind of person who puts the 'pro' in procrastination... wait, no they don't.",
    "{user} would be the person who asks for a refund at a buffet.",
    "{user} is the kind of person who takes a ruler to bed to see how long they sleep.",
    "{user} is the type of person who reads terms and conditions... and agrees anyway.",
    "{user} is the kind of person who rehearses their order at McDonald's.",
    "{user} is the kind of person who takes a umbrella when it's sunny.",
    "{user} is the kind of person who asks 'are we there yet?' before the trip starts.",
    "{user} is the kind of person who returns their shopping cart to the wrong store.",
    "{user} is the type of person who takes 30 minutes to tell a 5-minute story.",
    "{user} is the kind of person who waves at strangers and then realizes they know them.",
    "{user} is the type of person who uses 'literally' figuratively.",
    "{user} is the kind of person who looks both ways before crossing a one-way street.",
    "{user} is the kind of person who takes their turn signal after they've already turned.",
    "{user} is the type of person who uses a map to navigate their own house.",
    "{user} is the kind of person who puts milk in before cereal.",
    "{user} is the kind of person who stands in the doorway when it's raining.",
    "{user} is the type of person who uses scissors to cut spaghetti.",
    "{user} is the kind of person who removes USB drives without ejecting safely.",
    "{user} is the type of person who replies-all to company-wide emails.",
    "{user} is the kind of person who stands on the left side of the escalator.",
    "{user} is the type of person who drives slow in the fast lane.",
    "{user} is the kind of person who talks during movies at the theater.",
    "{user} is the type of person who leaves shopping carts in parking spaces.",
    "{user} is the kind of person who takes 20 items through the 10-items-or-less lane.",
    "{user} is the type of person who chews with their mouth open on purpose.",
    "{user} is the kind of person who puts empty containers back in the fridge.",
    "{user} is the type of person who starts clapping before everyone else.",
    "{user} is the kind of person who touches wet paint to check if it's dry.",
    "{user} is the type of person who double-clicks on touchscreen devices.",
    "{user} is the kind of person who lifts with their back, not with their legs.",
    "{user} is the type of person who writes checks at the grocery store.",
    "{user} is the kind of person who uses speakerphone in public restrooms.",
    "{user} is the type of person who stands too close to the airport baggage carousel.",
    "{user} is the kind of person who tries to fax things to email addresses.",
    "{user} is the type of person who orders well-done steak at fancy restaurants.",
    "{user} is the kind of person who asks for a cup for water at fast food places, then gets soda.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # MORE ABSURDITY (40 quotes)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user} is about as smooth as sandpaper.",
    "{user} has the originality of a photocopier.",
    "{user} is like a mosquito in a bedroom - persistent and irritating.",
    "{user} is the human version of autocorrect gone wrong.",
    "{user} has the grace of a walrus on a balance beam.",
    "{user} is about as helpful as a chocolate teapot in a coffee shop.",
    "{user} is like a cobweb in a corner - unnoticed until you walk into it.",
    "{user} has the punctuality of a glacier.",
    "{user} is about as refreshing as a warm glass of milk on a hot day.",
    "{user} has the hygiene of a public restroom floor.",
    "{user} is like a creaky door hinge - annoying and in need of oiling.",
    "{user} has the motivation of a hibernating bear.",
    "{user} is about as subtle as a sledgehammer at a tea party.",
    "{user} is like a parking ticket - unwanted and expensive to deal with.",
    "{user} has the charm of a wet sock.",
    "{user} is about as inspiring as a Monday morning alarm clock.",
    "{user} has the patience of a caffeine addict.",
    "{user} is like a low battery warning - always appearing at the worst time.",
    "{user} is the human embodiment of a typo.",
    "{user} has the wisdom of a fortune cookie... from a bad Chinese restaurant.",
    "{user} is about as cool as a lukewarm cup of tea.",
    "{user} is like a robo-call - ignored by everyone.",
    "{user} has the artistic ability of a drunk spider.",
    "{user} is about as interesting as watching grass grow... underwater.",
    "{user} has the driving skills of a shopping cart with a wonky wheel.",
    "{user} is like a glitch in the matrix - noticeable but nobody knows why it exists.",
    "{user} has the survival instincts of a lemming.",
    "{user} is about as welcome as a wasp at a picnic.",
    "{user} is like a speed bump on a highway - unexpected and annoying.",
    "{user} has the organizational skills of a tornado in a trailer park.",
    "{user} is like a flat tire on a road trip - annoying and slowing everyone down.",
    "{user} has the technical skills of a medieval peasant.",
    "{user} is about as necessary as a screen door on a submarine.",
    "{user} has the leadership qualities of a sheep in a wolf pack.",
    "{user} is like an error message - nobody wants to see them.",
    "{user} is the human equivalent of a loading screen at 99%.",
    "{user} has the strategic planning of a squirrel crossing the road.",
    "{user} is the reason scientists say we're not alone in the universe - nobody wants to be with them.",
    "{user} is the reason mute buttons were invented.",
    "{user} is the reason aliens keep their distance.",

    # ═══════════════════════════════════════════════════════════════════════════════
    # BONUS RANDOMNESS (30 more for 210 total)
    # ═══════════════════════════════════════════════════════════════════════════════
    "{user} is like a dial-up connection - obsolete and irritatingly slow.",
    "{user} has the appeal of a root canal.",
    "{user} is the human version of a printer error.",
    "{user} has the filter of a broken coffee machine.",
    "{user} is about as useful as a one-legged man in an ass-kicking contest.",
    "{user} has the stage presence of a stage light.",
    "{user} is like a VHS tape in a streaming world - irrelevant and prone to tangling.",
    "{user} has the punchlines of a dad joke without the charm.",
    "{user} is the kind of person who brings a knife to a gunfight and still misses.",
    "{user} has the plot twists of a straight line.",
    "{user} is about as exciting as an unsharpened pencil.",
    "{user} has the depth of a kiddie pool.",
    "{user} is like a screensaver from 1995 - outdated and trying too hard.",
    "{user} has the special effects of a low-budget 80s horror film.",
    "{user} is the type of person who brings Monopoly to a party and wonders why nobody stays.",
    "{user} has the replay value of a movie spoiler.",
    "{user} is about as magical as a discarded lottery ticket.",
    "{user} has the plot armor of a Game of Thrones character in season 8.",
    "{user} is like a CAPTCHA - nobody wants to deal with them.",
    "{user} has the plot development of a straight-to-DVD sequel.",
    "{user} is the human equivalent of a 'transaction failed' message.",
    "{user} has the appeal of a second-hand thrift store sweater with mystery stains.",
    "{user} is like a dead pixel - small, annoying, and impossible to ignore once noticed.",
    "{user} has the dramatic range of a teleprompter.",
    "{user} is about as successful as a diet in a candy factory.",
    "{user} has the fashion sense of a lost tourist at an airport.",
    "{user} is the kind of person who Googles 'how to breathe' just to be sure.",
    "{user} has the entertainment value of a Terms of Service agreement.",
    "{user} is like a glitchy video game NPC - repetitive and stuck on the same dialogue.",
    "{user} has the rhythm of a grandparent learning TikTok dances.",
]

# Theme choices for the command
THEME_CHOICES = [
    app_commands.Choice(name="Movie Quotes", value="movie"),
    app_commands.Choice(name="People Quotes", value="people"),
    app_commands.Choice(name="Randomness", value="randomness"),
]

# Spam amount choices
SPAM_AMOUNT_CHOICES = [
    app_commands.Choice(name="1", value=1),
    app_commands.Choice(name="2", value=2),
    app_commands.Choice(name="3", value=3),
    app_commands.Choice(name="4", value=4),
    app_commands.Choice(name="5", value=5),
]


class TrollCommands(commands.Cog):
    """Cog for trolling users with themed quotes."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name='troll',
        description='Send themed troll messages to a user! (Spam up to 5 at once!)'
    )
    @app_commands.describe(
        user="The user you want to troll (mention them)",
        theme="Choose a theme for the troll message",
        spam_amount="How many troll messages to send (1-5)"
    )
    @app_commands.choices(theme=THEME_CHOICES, spam_amount=SPAM_AMOUNT_CHOICES)
    async def troll(
        self,
        ctx: commands.Context,
        user: discord.Member,
        theme: str = "randomness",
        spam_amount: int = 1
    ) -> None:
        """
        Troll a user with themed messages. Spam up to 5 at once!
        
        Parameters:
        -----------
        user: discord.Member
            The user to troll (required)
        theme: str
            The theme of the troll message (Movie Quotes, People Quotes, Randomness)
        spam_amount: int
            Number of troll messages to send (1-5)
        """
        try:
            # Validate the user
            if user is None:
                await ctx.send("❌ You need to mention a user to troll! Usage: `/troll @user theme`", ephemeral=True)
                return

            # Don't allow trolling yourself (optional protection)
            if user.id == ctx.author.id:
                await ctx.send("🔥 Self burns are nice but find me someone else to body! ⚰️", ephemeral=True)
                return

            # Don't allow trolling the bot
            if user.id == self.bot.user.id:
                await ctx.send("💀 Did you just try to troll the Reaper?!? 💀", ephemeral=True)
                return

            # Validate spam_amount
            if spam_amount < 1 or spam_amount > 5:
                spam_amount = 1

            # Select the appropriate quote list based on theme
            if theme == "movie":
                quote_pool = MOVIE_QUOTES
                theme_name = "Movie Quotes"
                theme_emoji = "🎬"
            elif theme == "people":
                quote_pool = PEOPLE_QUOTES
                theme_name = "People Quotes"
                theme_emoji = "👥"
            elif theme == "randomness":
                quote_pool = RANDOMNESS_QUOTES
                theme_name = "Randomness"
                theme_emoji = "🎲"
            else:
                # Fallback to randomness if invalid theme
                quote_pool = RANDOMNESS_QUOTES
                theme_name = "Randomness"
                theme_emoji = "🎲"

            # Build all troll messages into one combined message
            troll_lines = []
            for i in range(spam_amount):
                # Randomly select a quote and format it with the user's mention
                selected_quote = random.choice(quote_pool)
                formatted_message = selected_quote.format(user=user.mention)
                
                # Add number prefix if spamming multiple
                if spam_amount > 1:
                    troll_lines.append(f"**{i + 1}.** {formatted_message}")
                else:
                    troll_lines.append(formatted_message)

            # Build the header
            if spam_amount > 1:
                header = f"{theme_emoji} **{theme_name}** x{spam_amount}\n\n"
            else:
                header = f"{theme_emoji} **{theme_name}**\n\n"
            
            # Combine all trolls with line breaks
            trolls_combined = "\n\n".join(troll_lines)
            full_message = f"{header}{trolls_combined}\n\n*Requested by {ctx.author.display_name}*"

            # Send the troll message (as regular text, not embed)
            await ctx.send(full_message)

            # Log the troll for fun
            logger.info(
                f"Troll command used by {ctx.author} ({ctx.author.id}) "
                f"targeting {user} ({user.id}) with theme '{theme_name}' | Spam: {spam_amount} quotes in 1 message"
            )

        except Exception as e:
            logger.error(f"Error in troll command: {e}", exc_info=True)
            await ctx.send(
                "❌ Something went wrong while trying to troll! Please try again.",
                ephemeral=True
            )

    @troll.error
    async def troll_error(self, ctx: commands.Context, error):
        """Handle errors for the troll command."""
        if isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ Couldn't find that user! Make sure you mention them correctly.", ephemeral=True)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ You need to specify a user to troll! Usage: `/troll @user [theme]`", ephemeral=True)
        else:
            logger.error(f"Unhandled error in troll command: {error}")
            await ctx.send("❌ An unexpected error occurred. Please try again later.", ephemeral=True)


async def setup(bot: commands.Bot):
    """Setup function to add the cog to the bot."""
    await bot.add_cog(TrollCommands(bot))
    logger.info("TrollCommands cog loaded successfully")
