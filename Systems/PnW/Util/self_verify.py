"""
self_verify.py — In-game PnW nation ownership verification via one-time passphrase.

Commands:
  /self_verify send <nation>  — Bot sends a passphrase to the nation's in-game PnW inbox
  /self_verify give           — Opens a modal to enter the passphrase (completes verification)

Alliance access management (ARIES only):
  /alliance_access grant <alliance_id> [name] [note]
  /alliance_access revoke <alliance_id>
  /alliance_access list
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import discord
import httpx
from discord import app_commands
from discord.ext import commands

from Systems.Functions.config import ARIES_USER_ID, PANDW_API_KEY
from Systems.PnW.Util.reaper_verify import (
    VerifiedDB,
    get_verified_db,
    resolve_nation_from_global_db,
)

logger = logging.getLogger(__name__)

# ── BIP-39 English wordlist (large subset) ───────────────────────────────────
# 4 random words from this list gives billions of unique combinations,
# far exceeding the needs of 15,000 simultaneous active verifications.
_BIP39_WORDS: List[str] = [
    "abandon","ability","able","about","above","absent","absorb","abstract",
    "absurd","abuse","access","accident","account","accuse","achieve","acid",
    "acoustic","acquire","across","act","action","actor","actress","actual",
    "adapt","add","addict","address","adjust","admit","adult","advance",
    "advice","aerobic","afford","afraid","again","age","agent","agree",
    "ahead","aim","air","airport","aisle","alarm","album","alcohol",
    "alert","alien","all","alley","allow","almost","alone","alpha",
    "already","also","alter","always","amateur","amazing","among","amount",
    "amused","analyst","anchor","ancient","anger","angle","angry","animal",
    "ankle","announce","annual","another","answer","antenna","antique","anxiety",
    "apart","apology","appear","apple","approve","april","arch","arctic",
    "area","arena","argue","arm","armed","armor","army","around",
    "arrange","arrest","arrive","arrow","art","artefact","artist","artwork",
    "ask","aspect","assault","asset","assist","assume","asthma","athlete",
    "atom","attack","attend","attitude","attract","auction","audit","august",
    "aunt","author","auto","autumn","average","avocado","avoid","awake",
    "aware","away","awesome","awful","awkward","axis","baby","balance",
    "bamboo","banana","banner","barely","bargain","barrel","base","basic",
    "basket","battle","beach","bean","beauty","because","become","beef",
    "before","begin","behave","behind","believe","below","belt","bench",
    "benefit","best","betray","better","between","beyond","bicycle","bid",
    "bike","bind","biology","bird","birth","bitter","black","blade",
    "blame","blanket","blast","bleak","bless","blind","blood","blossom",
    "blouse","blue","blur","blush","board","boat","body","boil",
    "bomb","bone","book","boost","border","boring","borrow","boss",
    "bottom","bounce","box","boy","bracket","brain","brand","brave",
    "bread","breeze","brick","bridge","brief","bright","bring","brisk",
    "broccoli","broken","bronze","broom","brother","brown","brush","bubble",
    "buddy","budget","buffalo","build","bulb","bulk","bullet","bundle",
    "bunker","burden","burger","burst","bus","business","busy","butter",
    "buyer","buzz","cabbage","cabin","cable","cactus","cage","cake",
    "call","calm","camera","camp","canal","cancel","candy","cannon",
    "canvas","canyon","capable","capital","captain","carbon","card","cargo",
    "carpet","carry","cart","case","cash","casino","castle","casual",
    "catalog","catch","category","cause","cave","ceiling","celery","cement",
    "census","century","cereal","certain","chair","chalk","champion","change",
    "chaos","chapter","charge","chase","chat","cheap","check","cheese",
    "chef","cherry","chest","chicken","chief","child","chimney","choice",
    "choose","chronic","chuckle","chunk","cinema","circle","citizen","city",
    "civil","claim","clap","clarify","claw","clay","clean","clerk",
    "clever","click","client","cliff","climb","clinic","clip","clock",
    "clog","close","cloth","cloud","clown","club","clump","cluster",
    "clutch","coach","coast","coconut","code","coffee","coil","coin",
    "collect","color","column","combine","come","comfort","comic","common",
    "company","concert","conduct","confirm","congress","connect","consider","control",
    "convince","cook","cool","copper","copy","coral","core","corn",
    "correct","cost","cotton","couch","country","couple","course","cousin",
    "cover","coyote","crack","cradle","craft","cram","crane","crash",
    "crater","crawl","crazy","cream","credit","creek","crew","cricket",
    "crime","crisp","critic","cross","crouch","crowd","crucial","cruel",
    "cruise","crumble","crunch","crush","cry","crystal","cube","culture",
    "cup","cupboard","curious","current","curtain","curve","cushion","custom",
    "cute","cycle","dad","damage","damp","dance","danger","daring",
    "dash","daughter","dawn","day","deal","debris","decade","december",
    "decide","decline","decorate","decrease","deer","defense","define","defy",
    "degree","delay","deliver","demand","demise","denial","dentist","deny",
    "depart","depend","deposit","depth","deputy","derive","describe","desert",
    "design","desk","despair","destroy","detail","detect","develop","device",
    "devote","diagram","dial","diamond","diary","dice","diesel","diet",
    "differ","digital","dignity","dilemma","dinner","dinosaur","direct","dirt",
    "disagree","discover","disease","dish","dismiss","display","distance","divert",
    "divide","divorce","dizzy","doctor","document","dog","doll","dolphin",
    "domain","donate","donkey","donor","door","dose","double","dove",
    "draft","dragon","drama","drastic","draw","dream","dress","drift",
    "drill","drink","drip","drive","drop","drum","dry","duck",
    "dumb","dune","during","dust","dutch","duty","dwarf","dynamic",
    "eager","eagle","early","earn","earth","easily","east","easy",
    "echo","ecology","edge","edit","educate","effort","egg","eight",
    "either","elbow","elder","electric","elegant","element","elephant","elevator",
    "elite","else","embark","embody","embrace","emerge","emotion","employ",
    "empower","empty","enable","enact","endless","endorse","enemy","energy",
    "enforce","engage","engine","enhance","enjoy","enlist","enough","enrich",
    "enroll","ensure","enter","entire","entry","envelope","episode","equal",
    "equip","erase","erode","erosion","error","erupt","escape","essay",
    "estate","eternal","ethics","evidence","evil","evoke","evolve","exact",
    "example","excess","exchange","excite","exclude","exercise","exhaust","exhibit",
    "exile","exist","exit","exotic","expand","expire","explain","expose",
    "express","extend","extra","eye","fable","face","faculty","faint",
    "faith","fall","false","fame","family","famous","fan","fancy",
    "fantasy","far","fashion","fat","fatal","father","fatigue","fault",
    "favorite","feature","february","federal","fee","feed","feel","feet",
    "fellow","felt","fence","festival","fetch","fever","few","fiber",
    "fiction","field","figure","file","film","filter","final","find",
    "fine","finger","finish","fire","firm","first","fiscal","fish",
    "fit","fitness","fix","flag","flame","flash","flat","flavor",
    "flee","flight","flip","float","flock","floor","flower","fluid",
    "flush","fly","foam","focus","fog","foil","follow","food",
    "foot","force","forest","forget","fork","fortune","forum","forward",
    "fossil","foster","found","fox","fragile","frame","frequent","fresh",
    "friend","fringe","frog","front","frost","frown","frozen","fruit",
    "fuel","fun","funny","furnace","fury","future","gadget","gain",
    "galaxy","gallery","game","gap","garage","garbage","garden","garlic",
    "garment","gasp","gate","gather","gauge","gaze","general","genius",
    "genre","gentle","genuine","gesture","ghost","gift","giggle","ginger",
    "giraffe","girl","give","glad","glance","glare","glass","glide",
    "glimpse","globe","gloom","glory","glove","glow","glue","goat",
    "goddess","gold","good","goose","gorilla","gospel","gossip","govern",
    "gown","grab","grace","grain","grant","grape","grasp","grass",
    "gravity","great","green","grid","grief","grit","grocery","group",
    "grow","grunt","guard","guide","guilt","guitar","gun","gym",
    "habit","hair","half","hammer","hamster","hand","happy","harsh",
    "harvest","have","hawk","hazard","head","health","heart","heavy",
    "hedgehog","height","hello","helmet","help","hero","hidden","high",
    "hill","hint","hip","hire","history","hobby","hockey","hold",
    "hole","holiday","hollow","home","honey","hood","hope","horn",
    "hospital","host","hour","hover","hub","huge","human","humble",
    "humor","hundred","hungry","hunt","hurdle","hurry","hurt","husband",
    "hybrid","ice","icon","ignore","ill","illegal","image","imitate",
    "immense","immune","impact","impose","improve","impulse","inbox","income",
    "increase","index","indicate","indoor","industry","infant","inflict","inform",
    "inhale","inject","inner","innocent","input","inquiry","insane","insect",
    "inside","inspire","install","intact","interest","invest","invite","iron",
    "island","isolate","issue","item","ivory","jacket","jaguar","jar",
    "jazz","jealous","jeans","jelly","jewel","job","join","joke",
    "journey","joy","judge","juice","jump","jungle","junior","junk",
    "just","kangaroo","keen","keep","ketchup","key","kick","kid",
    "kidney","kind","kingdom","kiss","kit","kitchen","kite","kitten",
    "kiwi","knee","knife","knock","know","lab","lamp","language",
    "laptop","large","later","laugh","laundry","lava","lawn","lawsuit",
    "layer","lazy","leader","learn","leave","lecture","left","leg",
    "legal","legend","lemon","lend","length","lens","leopard","lesson",
    "letter","level","liar","liberty","library","license","life","lift",
    "light","like","limb","limit","link","lion","liquid","list",
    "little","live","lizard","load","loan","lobster","local","lock",
    "logic","lonely","long","loop","lottery","loud","lounge","love",
    "loyal","lucky","luggage","lunar","lunch","luxury","mad","magic",
    "magnet","maid","main","mammal","mango","mansion","manual","maple",
    "marble","march","margin","marine","market","marriage","mask","master",
    "match","material","math","matrix","matter","maximum","maze","meadow",
    "mean","medal","media","melody","melt","member","memory","mention",
    "menu","mercy","merely","merge","merit","merry","mesh","message",
    "metal","method","middle","midnight","milk","million","mimic","mind",
    "minimum","minor","minute","miracle","miss","mitten","model","modify",
    "mom","monitor","monkey","monster","month","moon","moral","more",
    "morning","mosquito","mother","motion","motor","mountain","mouse","move",
    "movie","much","muffin","mule","multiply","muscle","museum","mushroom",
    "music","must","mutual","myself","mystery","naive","name","napkin",
    "narrow","nasty","nature","near","neck","need","negative","neglect",
    "neither","nephew","nerve","nest","never","news","next","nice",
    "night","noble","noise","nominee","noodle","normal","north","notable",
    "nothing","notice","novel","now","nuclear","number","nurse","nut",
    "oak","obey","object","oblige","obscure","obtain","ocean","october",
    "odor","offer","office","often","olive","olympic","omit","once",
    "onion","open","opera","oppose","option","orange","orbit","orchard",
    "order","ordinary","organ","orient","original","orphan","ostrich","other",
    "outdoor","outside","oval","own","oyster","ozone","pact","paddle",
    "page","pair","palace","panther","paper","parade","parent","park",
    "parrot","party","pass","patch","path","patrol","pause","pave",
    "payment","peace","peanut","peasant","pelican","penalty","pencil","people",
    "pepper","perfect","permit","person","pet","phone","photo","phrase",
    "piano","picnic","picture","piece","pigeon","pilot","pink","pipe",
    "pistol","pitch","pizza","place","planet","plastic","plate","play",
    "please","pledge","pluck","plug","plunge","poem","poet","point",
    "polar","pole","police","pond","pony","pool","popular","portion",
    "position","possible","post","potato","pottery","poverty","powder","power",
    "practice","praise","predict","prefer","prepare","present","pretty","prevent",
    "price","pride","primary","print","priority","prison","private","prize",
    "problem","process","produce","profit","program","project","promote","proof",
    "property","prosper","protect","proud","provide","public","pudding","pull",
    "pulp","pulse","pumpkin","pupil","puppy","purchase","purity","purpose",
    "purse","push","put","puzzle","pyramid","quality","quantum","quarter",
    "question","quick","quit","quiz","quote","rabbit","raccoon","race",
    "rack","radar","radio","rage","rail","rain","raise","rally",
    "ramp","ranch","random","range","rapid","rare","rate","rather",
    "raven","reach","ready","real","reason","rebel","rebuild","recall",
    "receive","recipe","record","recycle","reduce","reflect","reform","refuse",
    "region","regret","regular","reject","relax","release","relief","rely",
    "remain","remember","remind","remove","render","renew","rent","reopen",
    "repair","repeat","replace","report","require","rescue","resemble","resist",
    "resource","response","result","retire","retreat","return","reunion","reveal",
    "review","reward","rhythm","rich","ride","ridge","rifle","right",
    "rigid","ring","riot","ripple","risk","ritual","rival","river",
    "road","roast","robot","robust","rocket","romance","roof","rookie",
    "room","rose","rotate","rough","royal","rubber","rude","rug",
    "rule","run","runway","rural","sad","saddle","sadness","safe",
    "sail","salad","salmon","salon","salt","salute","same","sample",
    "sand","satisfy","satoshi","sauce","sausage","save","say","scale",
    "scan","scare","scatter","scene","scheme","science","scissors","scorpion",
    "scout","scrap","screen","script","scrub","sea","search","season",
    "seat","second","secret","section","security","seek","segment","select",
    "sell","seminar","senior","sense","sentence","series","service","session",
    "settle","setup","seven","shadow","shaft","shallow","share","shed",
    "shell","sheriff","shield","shift","shine","ship","shiver","shock",
    "shoe","shoot","shop","short","shoulder","shove","shrimp","shuffle",
    "shy","sibling","siege","sight","sign","silent","silk","silly",
    "silver","similar","simple","since","sing","siren","sister","situate",
    "six","size","ski","skill","skin","skirt","skull","slab",
    "slam","sleep","slender","slice","slide","slight","slim","slogan",
    "slot","slow","slush","small","smart","smile","smoke","smooth",
    "snack","snake","snap","sniff","snow","soap","soccer","social",
    "sock","solar","soldier","solid","solution","solve","someone","song",
    "soon","sorry","soul","sound","soup","source","south","space",
    "spare","spatial","spawn","speak","special","speed","spell","spend",
    "sphere","spice","spider","spike","spin","spirit","split","spoil",
    "sponsor","spoon","spray","spread","spring","spy","square","squeeze",
    "squirrel","stable","stadium","staff","stage","stairs","stamp","stand",
    "start","state","stay","steak","steel","stem","step","stereo",
    "stick","still","sting","stock","stomach","stone","stop","store",
    "storm","story","stove","strategy","street","strike","strong","struggle",
    "student","stuff","stumble","subject","submit","subway","success","such",
    "sudden","suffer","sugar","suggest","suit","summer","sun","sunny",
    "sunset","super","supply","supreme","sure","surface","surge","surprise",
    "sustain","swallow","swamp","swap","swear","sweet","swift","swim",
    "swing","switch","sword","symbol","symptom","syrup","table","tackle",
    "tag","tail","talent","tank","tape","target","task","tattoo",
    "taxi","teach","team","tell","ten","tenant","tennis","tent",
    "term","test","text","thank","that","theme","theory","there",
    "they","thing","this","thought","three","thrive","throw","thumb",
    "thunder","ticket","tilt","timber","time","tiny","tip","tired",
    "title","toast","tobacco","today","together","toilet","token","tomato",
    "tomorrow","tone","tongue","tonight","tool","topic","topple","torch",
    "tornado","tortoise","toss","total","tourist","toward","tower","town",
    "toy","track","trade","traffic","tragic","train","transfer","trap",
    "trash","travel","tray","treat","tree","trend","trial","tribe",
    "trick","trigger","trim","trip","trophy","trouble","truck","truly",
    "trumpet","trust","truth","try","tube","tuition","tumble","tunnel",
    "turkey","turn","turtle","twelve","twenty","twice","twin","twist",
    "two","type","typical","ugly","umbrella","unable","uncle","uncover",
    "under","undo","unfair","unfold","unhappy","uniform","unique","unit",
    "universe","unknown","unlock","until","unusual","unveil","update","upgrade",
    "uphold","upon","upper","upset","urban","useful","useless","usual",
    "utility","vacant","vacuum","vague","valid","valley","valve","van",
    "vanish","vapor","various","vast","vault","vehicle","velvet","vendor",
    "venture","venue","verb","verify","version","very","veteran","viable",
    "vibrant","vicious","victory","video","view","village","vintage","violin",
    "virtual","virus","visa","visit","vital","vivid","vocal","voice",
    "void","volcano","volume","vote","voyage","wage","wagon","wait",
    "walk","wall","walnut","want","warfare","warm","warrior","waste",
    "water","wave","way","wealth","weapon","wear","weasel","weather",
    "web","wedding","weekend","weird","welcome","west","wet","whale",
    "wheat","wheel","when","where","whip","whisper","wide","width",
    "wife","wild","will","win","window","wine","wing","wink",
    "winner","winter","wire","wisdom","wise","wish","witness","wolf",
    "woman","wonder","wood","wool","word","world","worry","worth",
    "wrap","wreck","wrestle","wrist","write","wrong","yard","year",
    "yellow","you","young","youth","zebra","zero","zone","zoo",
]

# Word count: using a large subset of the BIP-39 English wordlist.
# With N words, a 4-word passphrase gives N^4 unique combinations.
# At N=1888: 1888^4 ≈ 12.7 trillion combinations — far exceeds the
# 15,000-nation requirement with negligible collision probability.


def _generate_passphrase(num_words: int = 4, separator: str = "-") -> str:
    """
    Generate a cryptographically random passphrase from the BIP-39 word list.
    4 words → 2048^4 ≈ 17.6 trillion unique combinations.
    """
    return separator.join(secrets.choice(_BIP39_WORDS) for _ in range(num_words))


# ── Minimum send cooldown: 5 minutes between re-sends ─────────────────────────
_SEND_COOLDOWN_SECONDS = 300


# ── PnW in-game message sender ────────────────────────────────────────────────

async def _send_pnw_message(nation_id: int, leader_name: str, passphrase: str) -> bool:
    """
    POST to the PnW v1 /api/send-message/ endpoint.
    Subject limit: 25 chars.  Body limit: 2000 chars.
    Returns True on success.
    """
    subject = "Bot Verification"  # 16 chars — under 25 limit
    body = (
        f"Hello {leader_name},\n\n"
        "This is an automated verification message from the Reaper Bot.\n\n"
        "Your verification code is:\n\n"
        f"    {passphrase}\n\n"
        "Enter this code in Discord using the command: /self_verify give\n\n"
        "This code expires in 30 minutes and can only be used once.\n"
        "Do not share this code with anyone.\n\n"
        "- Reaper Bot"
    )

    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.post(
                "https://politicsandwar.com/api/send-message/",
                data={
                    "key": PANDW_API_KEY,
                    "to": str(nation_id),
                    "subject": subject,
                    "message": body,
                },
            )

        # PnW v1 send-message returns HTTP 200 on success.
        # The response body may be HTML, plain text, or JSON depending on the
        # game version — we treat any 200 as success and log the body for
        # diagnostics. Non-200 is always a failure.
        if r.status_code == 200:
            # Best-effort JSON parse for error details; ignore if it fails
            try:
                data = r.json()
                if data.get("success") is False or data.get("error"):
                    logger.warning(
                        "PnW send-message returned error for nation %d: %s",
                        nation_id, data,
                    )
                    return False
            except Exception:
                # Non-JSON body — HTTP 200 is sufficient signal of success
                pass
            logger.info("PnW send-message succeeded for nation %d", nation_id)
            return True

        logger.warning(
            "PnW send-message HTTP %d for nation %d — body: %.200s",
            r.status_code, nation_id, r.text,
        )
        return False
    except Exception as exc:
        logger.error("PnW send-message exception for nation %d: %s", nation_id, exc, exc_info=True)
        return False


# ── Verification passphrase modal ─────────────────────────────────────────────

class VerificationPassphraseModal(discord.ui.Modal, title="Enter Your Verification Code"):
    """Modal that accepts the passphrase the user received in-game."""

    passphrase_input = discord.ui.TextInput(
        label="Verification Code",
        placeholder="word-word-word-word",
        min_length=5,
        max_length=50,
        required=True,
        style=discord.TextStyle.short,
    )

    def __init__(self, verified_db: VerifiedDB) -> None:
        super().__init__()
        self.verified_db = verified_db

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        discord_id = str(interaction.user.id)
        entered = self.passphrase_input.value.strip()

        result = await self.verified_db.consume_pending_verification(
            discord_id=discord_id,
            passphrase=entered,
        )

        status = result["status"]

        if status == "success":
            nation_id = result["nation_id"]
            nation_name = result["nation_name"]

            # Fetch full nation data for the upsert (best-effort)
            nation_data = await resolve_nation_from_global_db(str(nation_id))
            if not nation_data:
                nation_data = {"id": nation_id, "nation_name": nation_name}

            await self.verified_db.upsert_user(
                discord_id=discord_id,
                nation=nation_data,
                discord_username=str(interaction.user),
                discord_display_name=getattr(interaction.user, "display_name", None),
                source="self_verify",
            )

            nation_url = f"https://politicsandwar.com/nation/id={nation_id}"
            embed = discord.Embed(
                title="✅ Verification Successful",
                description=(
                    f"You are now verified as [{nation_name}]({nation_url})!\n\n"
                    "If your alliance is approved, you can access protected pages on "
                    "[reaper.qzz.io](https://reaper.qzz.io)."
                ),
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc),
            )
            embed.add_field(name="Nation", value=nation_name, inline=True)
            embed.add_field(name="Discord", value=interaction.user.mention, inline=True)
            embed.set_footer(text="Stored in Databases/PnW/Verified.db · source: self_verify")
            await interaction.followup.send(embed=embed, ephemeral=True)

        elif status == "wrong_passphrase":
            remaining = result.get("attempts_remaining", 0)
            await interaction.followup.send(
                f"❌ Incorrect code. You have **{remaining}** attempt(s) remaining before "
                "this code is invalidated.\nTip: codes are case-insensitive.",
                ephemeral=True,
            )

        elif status == "expired":
            await interaction.followup.send(
                "⏰ Your verification code has expired or you don't have a pending one.\n"
                "Run `/self_verify send` to get a new code.",
                ephemeral=True,
            )

        elif status == "max_attempts":
            await interaction.followup.send(
                "🚫 Too many failed attempts — your code has been invalidated.\n"
                "Run `/self_verify send` to request a fresh code.",
                ephemeral=True,
            )

        else:
            await interaction.followup.send(
                "Something went wrong. Run `/self_verify send` to start over.",
                ephemeral=True,
            )

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        logger.error("VerificationPassphraseModal.on_error: %s", error, exc_info=True)
        try:
            await interaction.followup.send(
                "An unexpected error occurred. Please try again.", ephemeral=True
            )
        except Exception:
            pass


# ── SelfVerify Cog ────────────────────────────────────────────────────────────

class SelfVerify(commands.Cog):
    """In-game PnW verification via one-time passphrase sent to the nation's inbox."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.verified_db = get_verified_db()
        self._cleanup_task: Optional[asyncio.Task] = None

    async def cog_load(self) -> None:
        """Start the daily cleanup loop when the cog is loaded."""
        self._cleanup_task = asyncio.create_task(self._daily_cleanup_loop())
        logger.info("SelfVerify cog loaded, daily cleanup task started")

    async def cog_unload(self) -> None:
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()

    async def _daily_cleanup_loop(self) -> None:
        """Delete expired/used pending_verification rows once per day."""
        await asyncio.sleep(3600)  # initial 1-hour delay on startup
        while True:
            try:
                deleted = await self.verified_db.cleanup_expired_pending()
                if deleted:
                    logger.info("SelfVerify: cleaned up %d expired pending verifications", deleted)
            except Exception as exc:
                logger.warning("SelfVerify cleanup loop error: %s", exc)
            await asyncio.sleep(86400)  # 24 hours

    async def _nation_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        try:
            from Systems.Functions.autocomplete_utils import nation_autocomplete
            return await nation_autocomplete(current, nw_only=False, limit=25)
        except Exception as exc:
            logger.error("SelfVerify nation autocomplete error: %s", exc)
            return []

    @app_commands.command(
        name="self_verify",
        description="Verify your PnW nation ownership via an in-game message",
    )
    @app_commands.describe(
        action="'send' to receive a code in-game, 'give' to enter your code",
        nation="Your nation name or ID (required for 'send')",
    )
    @app_commands.choices(action=[
        app_commands.Choice(
            name="send — Send me a verification code in-game",
            value="send",
        ),
        app_commands.Choice(
            name="give — Enter my verification code",
            value="give",
        ),
    ])
    @app_commands.autocomplete(nation=_nation_autocomplete)
    async def self_verify(
        self,
        interaction: discord.Interaction,
        action: str,
        nation: Optional[str] = None,
    ) -> None:
        if action == "send":
            await self._handle_send(interaction, nation)
        else:
            await self._handle_give(interaction)

    # ── /self_verify send ──────────────────────────────────────────────────

    async def _handle_send(
        self,
        interaction: discord.Interaction,
        nation: Optional[str],
    ) -> None:
        """Send a passphrase to the user's in-game PnW inbox."""
        await interaction.response.defer(ephemeral=True)

        if not nation:
            await interaction.followup.send(
                "You must provide your nation name or ID.\n"
                "Example: `/self_verify send nation:My Nation`",
                ephemeral=True,
            )
            return

        # ── Cooldown check: no re-send within 5 minutes ───────────────────
        last_send = await self.verified_db.get_last_send_at(
            str(interaction.user.id)
        )
        if last_send:
            try:
                from datetime import timedelta
                last_dt = datetime.fromisoformat(last_send)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
                if elapsed < _SEND_COOLDOWN_SECONDS:
                    remaining_secs = int(_SEND_COOLDOWN_SECONDS - elapsed)
                    mins, secs = divmod(remaining_secs, 60)
                    await interaction.followup.send(
                        f"⏳ Please wait **{mins}m {secs}s** before requesting another code.\n"
                        "If you already received one, run `/self_verify give` to enter it.",
                        ephemeral=True,
                    )
                    return
            except Exception:
                pass  # parse error — allow the send

        # ── Resolve nation ─────────────────────────────────────────────────
        nation_data = await resolve_nation_from_global_db(nation.strip())
        if not nation_data:
            await interaction.followup.send(
                f"❌ Could not find a nation matching `{nation}` in the database.\n"
                "Check the name/ID and try again.",
                ephemeral=True,
            )
            return

        nation_id = int(nation_data["id"])
        nation_name = nation_data.get("nation_name", f"Nation {nation_id}")
        leader_name = nation_data.get("leader_name", "Leader")

        # ── Generate passphrase and store pending verification ─────────────
        passphrase = _generate_passphrase()

        await self.verified_db.create_pending_verification(
            discord_id=str(interaction.user.id),
            nation_id=nation_id,
            nation_name=nation_name,
            passphrase=passphrase,
        )

        # ── Send in-game PnW message ───────────────────────────────────────
        sent = await _send_pnw_message(nation_id, leader_name, passphrase)
        if not sent:
            await self.verified_db.expire_pending_verifications(
                str(interaction.user.id)
            )
            await interaction.followup.send(
                "❌ Failed to send the in-game message. The PnW API may be temporarily "
                "unavailable. Please try again in a few minutes.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="📬 Verification Code Sent",
            description=(
                f"A verification code has been sent to **{nation_name}**'s in-game inbox!\n\n"
                "**What to do next:**\n"
                "1. Log in to [Politics and War](https://politicsandwar.com)\n"
                "2. Check your nation's **Messages** inbox\n"
                "3. Copy the code from the message titled **Bot Verification**\n"
                "4. Run `/self_verify give` and paste the code\n\n"
                "⏱ The code expires in **30 minutes**."
            ),
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Nation", value=nation_name, inline=True)
        embed.add_field(name="Sent To", value=f"ID: {nation_id}", inline=True)
        embed.set_footer(text="Only you can see this message")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /self_verify give ──────────────────────────────────────────────────

    async def _handle_give(self, interaction: discord.Interaction) -> None:
        """Open a modal for the user to enter their passphrase."""
        pending = await self.verified_db.get_pending_verification(
            str(interaction.user.id)
        )
        if not pending:
            await interaction.response.send_message(
                "You don't have a pending verification code.\n"
                "Run `/self_verify send` first to receive one in-game.",
                ephemeral=True,
            )
            return

        modal = VerificationPassphraseModal(verified_db=self.verified_db)
        await interaction.response.send_modal(modal)


# ── AllianceAccess Cog ────────────────────────────────────────────────────────

class AllianceAccess(commands.Cog):
    """ARIES-only commands to manage which alliances can access protected web pages."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.verified_db = get_verified_db()

    def _is_aries(self, user_id: int) -> bool:
        return str(user_id) == str(ARIES_USER_ID)

    alliance_access_group = app_commands.Group(
        name="alliance_access",
        description="Manage approved alliances for website access",
    )

    @alliance_access_group.command(
        name="grant",
        description="Approve an alliance — their verified members can access protected pages (ARIES only)",
    )
    @app_commands.describe(
        alliance_id="The PnW numeric alliance ID",
        name="Alliance name (auto-resolved if omitted)",
        note="Optional admin note",
    )
    async def alliance_access_grant(
        self,
        interaction: discord.Interaction,
        alliance_id: int,
        name: Optional[str] = None,
        note: Optional[str] = None,
    ) -> None:
        if not self._is_aries(interaction.user.id):
            await interaction.response.send_message(
                "❌ Only ARIES can manage alliance access.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Auto-resolve alliance name from GlobalNations.db if not provided
        resolved_name = name
        if not resolved_name:
            resolved_name = await _resolve_alliance_name(alliance_id)

        display_name = resolved_name or f"Alliance {alliance_id}"

        await self.verified_db.grant_alliance_access(
            alliance_id=alliance_id,
            alliance_name=display_name,
            granted_by=str(interaction.user.id),
            note=note,
        )

        embed = discord.Embed(
            title="✅ Alliance Access Granted",
            description=(
                f"Members of **{display_name}** (ID: `{alliance_id}`) who are verified "
                "can now access protected pages on reaper.qzz.io."
            ),
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        if note:
            embed.add_field(name="Note", value=note, inline=False)
        embed.set_footer(text=f"Granted by {interaction.user}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @alliance_access_group.command(
        name="revoke",
        description="Revoke a previously approved alliance (ARIES only)",
    )
    @app_commands.describe(alliance_id="The PnW numeric alliance ID to revoke")
    async def alliance_access_revoke(
        self,
        interaction: discord.Interaction,
        alliance_id: int,
    ) -> None:
        if not self._is_aries(interaction.user.id):
            await interaction.response.send_message(
                "❌ Only ARIES can manage alliance access.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        removed = await self.verified_db.revoke_alliance_access(alliance_id)
        if removed:
            await interaction.followup.send(
                f"✅ Alliance `{alliance_id}` has been removed from the approved list.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"⚠️ Alliance `{alliance_id}` was not in the approved list.",
                ephemeral=True,
            )

    @alliance_access_group.command(
        name="list",
        description="List all alliances approved for website access",
    )
    async def alliance_access_list(
        self, interaction: discord.Interaction
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        alliances = await self.verified_db.get_approved_alliances()
        if not alliances:
            await interaction.followup.send(
                "No alliances are currently approved for website access.\n"
                "Use `/alliance_access grant` to add one.",
                ephemeral=True,
            )
            return

        lines = []
        for a in alliances[:25]:
            lines.append(
                f"• **{a['alliance_name']}** (ID: `{a['alliance_id']}`)"
                f" — granted by <@{a['granted_by']}>"
                + (f"\n  ↳ {a['note']}" if a.get("note") else "")
            )

        embed = discord.Embed(
            title=f"Approved Alliances ({len(alliances)})",
            description="\n".join(lines),
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc),
        )
        if len(alliances) > 25:
            embed.set_footer(text=f"Showing first 25 of {len(alliances)} alliances")
        await interaction.followup.send(embed=embed, ephemeral=True)


# ── Alliance name resolver helper ─────────────────────────────────────────────

async def _resolve_alliance_name(alliance_id: int) -> Optional[str]:
    """Best-effort lookup of an alliance name from GlobalNations.db."""
    try:
        from Systems.Functions.db_paths import GLOBAL_NATIONS_DB_STR
        import asyncio as _asyncio
        import sqlite3 as _sq

        def _sync_lookup() -> Optional[str]:
            with _sq.connect(GLOBAL_NATIONS_DB_STR, timeout=10) as conn:
                conn.row_factory = _sq.Row
                row = conn.execute(
                    "SELECT alliance_name FROM nations "
                    "WHERE alliance_id = ? AND alliance_name IS NOT NULL "
                    "LIMIT 1",
                    (alliance_id,),
                ).fetchone()
                return str(row["alliance_name"]) if row else None

        return await _asyncio.to_thread(_sync_lookup)
    except Exception as exc:
        logger.debug("_resolve_alliance_name(%d) failed: %s", alliance_id, exc)
        return None


# ── Cog setup ─────────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot) -> None:
    # discord.py 2.x automatically registers app_commands.Group class attributes
    # when add_cog() is called — no manual bot.tree.add_command() needed.
    await bot.add_cog(SelfVerify(bot))
    await bot.add_cog(AllianceAccess(bot))
    logger.info("SelfVerify and AllianceAccess cogs loaded successfully")
