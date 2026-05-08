import re
import discord
from discord.ext import commands, tasks
import json
import random
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
from Systems.Functions.config import GROQ_API_KEY
import logging
import groq
from Systems.Fun.zombie_db import ZombieDB

# ── Constants ─────────────────────────────────────────────────────────────────
UPDATE_INTERVAL_HOURS = 2
ZOMBIE_THUMBNAIL_URL = (
    "https://t4.ftcdn.net/jpg/06/04/24/25/"
    "360_F_604242595_aOXbhCveYiqzeEvq1IVWAC5N5YdGlQOK.jpg"
)
CHOICE_LABELS = ["A", "B", "C", "D"]

# Three sets of choice emojis — rotates each round (deterministic: round % 3).
# Each set has exactly 4 emojis mapping to A/B/C/D positions.
_CHOICE_EMOJI_SETS: List[Dict[str, discord.PartialEmoji]] = [
    {  # Set 1
        "a": discord.PartialEmoji(name="a1", id=1475699063184687125),
        "b": discord.PartialEmoji(name="b1", id=1475699064732651644),
        "c": discord.PartialEmoji(name="c1", id=1475699065969840301),
        "d": discord.PartialEmoji(name="d1", id=1475699067056160890),
    },
    {  # Set 2
        "a": discord.PartialEmoji(name="a2", id=1475736586485239860),
        "b": discord.PartialEmoji(name="b2", id=1475736583343837296),
        "c": discord.PartialEmoji(name="c2", id=1475736578067267687),
        "d": discord.PartialEmoji(name="d2", id=1475736576951586838),
    },
    {  # Set 3
        "a": discord.PartialEmoji(name="a3", id=1475737602585002025),
        "b": discord.PartialEmoji(name="b3", id=1475737604203872330),
        "c": discord.PartialEmoji(name="c3", id=1475737558733422632),
        "d": discord.PartialEmoji(name="d3", id=1475737556992659540),
    },
]

# Melee weapons — randomly assigned at join, never break, never run out
MELEE_WEAPONS = [
    "Fire Axe", "Machete", "Crowbar", "Baseball Bat", "Hunting Knife",
    "Sledgehammer", "Katana", "Pipe Wrench", "Hatchet", "Combat Knife",
    "Tire Iron", "Cleaver", "Spear", "Pickaxe", "Shovel",
]

def _make_survivor() -> Dict:
    """Return a fresh survivor dict with randomised melee weapon and starting ammo."""
    return {
        "health":          100,
        "stamina":         100,
        "morale":          75,
        "status":          "Normal",
        # Revolver: 6 in cylinder + 6 spare = 12 total
        "revolver_loaded": 6,
        "revolver_spare":  6,
        # Rifle: 12 in mag + 0 spare
        "rifle_loaded":    12,
        "rifle_spare":     0,
        # Melee: random, indestructible
        "melee":           random.choice(MELEE_WEAPONS),
    }

log = logging.getLogger("ZombieSurvival")


def _get_choice_emojis(round_num: int) -> List[discord.PartialEmoji]:
    """Return ordered [A, B, C, D] PartialEmojis for the given round number."""
    s = _CHOICE_EMOJI_SETS[round_num % len(_CHOICE_EMOJI_SETS)]
    return [s["a"], s["b"], s["c"], s["d"]]


# ── Cog ───────────────────────────────────────────────────────────────────────

class ZombieSurvival(commands.Cog):
    """An ongoing, AI-driven zombie survival simulation.

    One message per round: story embed + vote buttons.  The round deadline is
    rendered as a Discord <t:UNIX:R> timestamp so it counts down live on every
    client with zero API calls.  Player cards are shown via /zombie_character.
    state["message_id"] = the current round's story message ID.
    """

    def __init__(self, bot):
        self.bot = bot
        self.state: Dict = ZombieDB._default_state()
        self.db = ZombieDB()
        self.bot.loop.create_task(self._startup())
        self.game_loop.start()

    async def _startup(self):
        """Load state from DB, re-register the persistent view after restarts."""
        await self.bot.wait_until_ready()
        self.state = await self.db.load_state()
        if self.state.get("active") and self.state.get("choices"):
            self.bot.add_view(ZombieView(self))
            log.info("ZombieSurvival: persistent view re-registered after restart.")

    def cog_unload(self):
        self.game_loop.cancel()

    # ── DB helpers ────────────────────────────────────────────────────────────

    async def _save(self):
        try:
            await self.db.save_game(self.state)
        except Exception as e:
            log.error(f"save_game failed: {e}")

    async def _save_with_history(self, round_num: int, event_text: str, outcome_text: str):
        try:
            await self.db.save_game(self.state)
            await self.db.append_history(round_num, event_text, outcome_text)
        except Exception as e:
            log.error(f"save_with_history failed: {e}")

    # ── Groq ──────────────────────────────────────────────────────────────────

    def _groq_client(self) -> Optional[groq.Groq]:
        if not GROQ_API_KEY:
            log.error("GROQ_API_KEY is missing.")
            return None
        return groq.Groq(api_key=GROQ_API_KEY)

    async def generate_content(self, context_prompt: str) -> Optional[Dict]:
        """Call Groq and return parsed JSON for the next round.

        Each choice now carries a base_odds integer (0-100) that reflects how
        risky/safe that option is narratively.  The bot uses this as the
        starting success probability before applying vote multiplier + luck.
        """
        system_msg = (
            "You are a Zombie Survival Game Master for a Discord game. "
            "Tone: dark, gritty, tense — like The Last of Us or The Walking Dead. "
            "The story MUST be continuous and directly follow the last outcome. "
            "Keep event_text to 3-5 sentences: vivid but punchy, no padding. "
            "choices: exactly 4 short, distinct, actionable options (max 12 words each). "
            "choice_odds: exactly 4 integers representing the BASE success probability "
            "for each choice. These MUST be meaningfully different from each other — "
            "spread them across the full range. Examples of good spreads: [20,65,40,80], "
            "[15,55,70,35], [80,25,50,10]. Never use the same value twice. "
            "A suicidal charge should be 10-20. A cautious retreat should be 60-80. "
            "A risky gamble should be 15-30. A solid plan should be 55-75. "
            "world_impact.success_outcome: 2-3 sentences — what happens if they succeed. "
            "world_impact.failure_outcome: 2-3 sentences — what happens if they fail. "
            "world_impact.stat_changes: dict of stat deltas (keys: health, stamina, morale; "
            "values: integers, negative = loss). Keep magnitudes small (±5 to ±20). "
            "Return ONLY valid JSON, no markdown, no code fences:\n"
            '{"event_text":"string",'
            '"choices":["string","string","string","string"],'
            '"choice_odds":[65,20,45,80],'
            '"world_impact":{"success_outcome":"string","failure_outcome":"string",'
            '"stat_changes":{"health":0,"stamina":-10,"morale":5}}}'
        )

        for attempt in range(3):
            try:
                client = self._groq_client()
                if not client:
                    return None

                def _call():
                    return client.chat.completions.create(
                        messages=[
                            {"role": "system", "content": system_msg},
                            {"role": "user",   "content": context_prompt},
                        ],
                        model="llama-3.1-8b-instant",
                        response_format={"type": "json_object"},
                    )

                completion = await asyncio.to_thread(_call)
                raw = completion.choices[0].message.content
                cleaned = re.sub(r'//[^\n]*', '', raw)
                parsed = json.loads(cleaned)

                if "event_text" not in parsed or "choices" not in parsed:
                    log.error(f"Groq missing keys (attempt {attempt+1}): {list(parsed.keys())}")
                    continue

                # Normalise choice_odds — default to 50 per slot if missing/wrong length
                raw_odds = parsed.get("choice_odds", [])
                if not isinstance(raw_odds, list) or len(raw_odds) < 4:
                    raw_odds = (list(raw_odds) + [50, 50, 50, 50])[:4]
                parsed["choice_odds"] = [
                    max(5, min(90, int(o))) for o in raw_odds[:4]
                ]

                wi = parsed.setdefault("world_impact", {})
                wi.setdefault("success_outcome", "The survivors push through.")
                wi.setdefault("failure_outcome", "The situation deteriorates.")
                wi.setdefault("stat_changes", {})

                parsed["choices"] = parsed["choices"][:4]
                return parsed

            except groq.APIError as e:
                log.error(f"Groq API error (attempt {attempt+1}): {e}")
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                log.error(f"Groq parse error (attempt {attempt+1}): {e}")
            except Exception as e:
                log.error(f"Groq error (attempt {attempt+1}): {e}")

            if attempt < 2:
                await asyncio.sleep(3)

        return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _all_dead(self) -> bool:
        """True when every survivor in the game is Deceased."""
        survivors = self.state.get("survivors", {})
        if not survivors:
            return False
        return all(s.get("status") == "Deceased" for s in survivors.values())

    def _user_display(self, uid: str) -> str:
        try:
            user = self.bot.get_user(int(uid))
            return user.display_name if user else f"Survivor {uid}"
        except (ValueError, TypeError):
            return f"Survivor {uid}"

    # ── Game loop ─────────────────────────────────────────────────────────────

    @tasks.loop(minutes=30)
    async def game_loop(self):
        if not self.state.get("active") or not self.state.get("channel_id"):
            return
        elapsed = datetime.now().timestamp() - self.state.get("last_update", 0)
        if elapsed >= UPDATE_INTERVAL_HOURS * 3600:
            await self.resolve_round()

    @game_loop.before_loop
    async def before_game_loop(self):
        await self.bot.wait_until_ready()

    # ── Embed builders ────────────────────────────────────────────────────────

    def _round_deadline_ts(self) -> int:
        """Unix timestamp when the current round resolves."""
        last = self.state.get("last_update", 0)
        return int(last + UPDATE_INTERVAL_HOURS * 3600)

    def _build_story_embed(self) -> discord.Embed:
        """Build the single story embed.  The countdown uses Discord's native
        <t:UNIX:R> format — it updates live on every client with zero API calls.
        """
        round_num     = self.state.get("round", 1)
        choice_emojis = _get_choice_emojis(round_num)
        choices       = self.state.get("choices", [])[:4]
        deadline_ts   = self._round_deadline_ts()

        embed = discord.Embed(
            title=f"🧟 ZOMBIE SURVIVAL — Round {round_num}",
            description=(
                f"{self.state.get('current_event', '')}\n\n"
                f"⏱️ **Round ends** <t:{deadline_ts}:R>"
            ),
            color=discord.Color.dark_red(),
        )
        embed.set_thumbnail(url=ZOMBIE_THUMBNAIL_URL)

        # Choices with base odds
        choices_text = "\n".join(
            f"{choice_emojis[i]} **{CHOICE_LABELS[i]}.** {choice}"
            for i, choice in enumerate(choices)
        )
        embed.add_field(
            name="What do the survivors do?",
            value=choices_text or "No choices available.",
            inline=False,
        )

        # Survivor mentions — alerts players and shows who is alive vs dead
        survivors = self.state.get("survivors", {})
        if survivors:
            living_mentions = []
            dead_mentions   = []
            for uid, s in survivors.items():
                mention = f"<@{uid}>"
                if s.get("status") == "Deceased":
                    dead_mentions.append(f"~~{mention}~~")
                else:
                    living_mentions.append(mention)
            parts = living_mentions + dead_mentions
            embed.add_field(
                name=f"👥 Survivors ({len(living_mentions)} alive)",
                value=" ".join(parts),
                inline=False,
            )

        # Last round outcome
        if self.state.get("history"):
            last = self.state["history"][-1]
            embed.add_field(
                name=f"Round {last['round']} Outcome",
                value=last["outcome_text"],
                inline=False,
            )

        votes_cast = len(self.state.get("voters", []))
        total      = len(survivors)
        living     = sum(1 for s in survivors.values() if s.get("status") != "Deceased")
        embed.set_footer(
            text=(
                f"🗳️ Votes: {votes_cast}  •  👥 {living}/{total} alive  •  "
                "Majority rules — tie = random  •  More votes = better odds  •  "
                "Use /zombie_character to see your stats"
            )
        )
        return embed

    # ── Round resolution ──────────────────────────────────────────────────────

    @staticmethod
    def _calc_success_chance(base_odds: float, votes_on_choice: int) -> float:
        """
        Final success % = base_odds
                        + vote_multiplier  (2–5 % per voter on this choice)
                        + luck_factor      (random −15 to +15)
        Clamped to [5, 95].
        """
        vote_bonus  = votes_on_choice * random.uniform(2.0, 5.0)
        luck_factor = random.uniform(-15.0, 15.0)
        return max(5.0, min(95.0, base_odds + vote_bonus + luck_factor))

    @staticmethod
    def _loot_on_success(votes_on_choice: int) -> Dict:
        """
        Return small random loot scaled by consensus.
        More voters on the winning choice = slightly better rewards,
        but kept deliberately modest so stats don't inflate.
        """
        # Base ranges (low intentionally)
        base_hp  = random.randint(0, 4)
        base_st  = random.randint(0, 4)
        base_mo  = random.randint(0, 3)
        # Revolver ammo: 0-3 rounds base, +0-1 per 2 voters
        rev_ammo = random.randint(0, 3) + (votes_on_choice // 2)
        # Rifle ammo: 0-2 rounds base, +0-1 per 3 voters
        rif_ammo = random.randint(0, 2) + (votes_on_choice // 3)
        # Consensus bonus: each extra voter adds a tiny flat boost
        bonus = min(votes_on_choice, 5)   # cap at 5 so it stays modest
        return {
            "health":       base_hp  + bonus,
            "stamina":      base_st  + bonus,
            "morale":       base_mo  + bonus,
            "revolver_ammo": rev_ammo,
            "rifle_ammo":    rif_ammo,
        }

    async def resolve_round(self):
        """Tally votes, apply outcomes, generate next event — or end the game."""
        channel = self.bot.get_channel(self.state.get("channel_id"))
        if not channel:
            self.state["active"] = False
            await self._save()
            return

        votes: Dict[str, int] = self.state.get("votes", {})
        choices: List[str]    = self.state.get("choices", [])[:4]
        choice_odds: List[int] = self.state.get("choice_odds", [50] * 4)
        total_votes = sum(votes.values())

        # ── Determine winning choice ──────────────────────────────────────────
        if not choices:
            winning_index    = 0
            winning_text     = "The survivors were paralysed by indecision."
            winning_votes    = 0
            base_odds        = 10.0
        elif total_votes == 0:
            winning_index    = random.randint(0, len(choices) - 1)
            winning_text     = choices[winning_index]
            winning_votes    = 0
            base_odds        = float(choice_odds[winning_index]) if winning_index < len(choice_odds) else 50.0
        else:
            max_votes        = max(votes.values())
            candidates       = [int(k) for k, v in votes.items() if v == max_votes]
            winning_index    = random.choice(candidates)
            winning_text     = choices[winning_index]
            winning_votes    = votes.get(str(winning_index), 0)
            base_odds        = float(choice_odds[winning_index]) if winning_index < len(choice_odds) else 50.0

        label          = CHOICE_LABELS[winning_index] if winning_index < len(CHOICE_LABELS) else str(winning_index + 1)
        success_chance = self._calc_success_chance(base_odds, winning_votes)
        is_success     = random.uniform(0, 100) <= success_chance

        world_impact = self.state.get("world_impact", {})
        outcome_narrative = world_impact.get(
            "success_outcome" if is_success else "failure_outcome",
            "The world is indifferent to their struggle."
        )

        outcome_text = (
            f"**Choice {label}: {winning_text}**\n"
            f"*(Votes: {winning_votes} | Base odds: {base_odds:.0f}% | "
            f"Final: {success_chance:.0f}%)* "
            f"→ **{'✅ SUCCESS' if is_success else '❌ FAILURE'}**\n\n"
            f"*{outcome_narrative}*"
        )

        # ── Classify choice: attack (uses ammo) vs supply (gains ammo) ────────
        _ATTACK_KEYWORDS = (
            "attack", "shoot", "fire", "fight", "charge", "assault", "engage",
            "repel", "defend", "stand", "ambush", "snipe", "open fire", "gun",
            "blast", "cover fire", "suppress", "take out", "eliminate",
        )
        _SUPPLY_KEYWORDS = (
            "scavenge", "loot", "search", "gather", "find", "supply", "supplies",
            "raid", "forage", "collect", "grab", "retrieve", "salvage", "stock",
            "ammo", "ammunition", "restock", "resupply",
        )
        choice_lower = winning_text.lower()
        is_attack_choice = any(kw in choice_lower for kw in _ATTACK_KEYWORDS)
        is_supply_choice = any(kw in choice_lower for kw in _SUPPLY_KEYWORDS)

        # ── Apply stat changes + loot ─────────────────────────────────────────
        stat_changes: Dict = world_impact.get("stat_changes", {})
        death_report = ""
        ammo_report_lines: List[str] = []

        if is_success:
            loot = self._loot_on_success(winning_votes)
            loot_lines = []
            if loot["health"]       > 0: loot_lines.append(f"❤️ +{loot['health']} HP")
            if loot["stamina"]      > 0: loot_lines.append(f"⚡ +{loot['stamina']} ST")
            if loot["morale"]       > 0: loot_lines.append(f"💙 +{loot['morale']} MO")
            # Only show ammo gains for non-attack choices
            if not is_attack_choice:
                if loot["revolver_ammo"] > 0: loot_lines.append(f"🔫 +{loot['revolver_ammo']} revolver rounds")
                if loot["rifle_ammo"]    > 0: loot_lines.append(f"🎯 +{loot['rifle_ammo']} rifle rounds")
            if loot_lines:
                outcome_text += f"\n\n**FOUND:** {', '.join(loot_lines)}"
        else:
            loot = None

        for uid, survivor in self.state["survivors"].items():
            if survivor.get("status") == "Deceased":
                continue

            # AI stat deltas (success = apply as-is, failure = invert positives)
            for stat, delta in stat_changes.items():
                if stat in ("health", "stamina", "morale") and isinstance(delta, (int, float)):
                    if is_success:
                        survivor[stat] = max(0, min(100, survivor[stat] + int(delta)))
                    else:
                        penalty = -abs(int(delta))
                        survivor[stat] = max(0, min(100, survivor[stat] + penalty))

            # ── Ammo: attack choices consume, supply choices gain ─────────────
            if is_attack_choice:
                # Consume ammo: prefer rifle if loaded, else revolver, else melee only
                rif_loaded = survivor.get("rifle_loaded", 0)
                rev_loaded = survivor.get("revolver_loaded", 0)
                rif_spare  = survivor.get("rifle_spare", 0)
                rev_spare  = survivor.get("revolver_spare", 0)

                # Spend 1-3 rifle rounds if available
                rif_cost = min(random.randint(1, 3), rif_loaded)
                if rif_cost > 0:
                    survivor["rifle_loaded"] = rif_loaded - rif_cost
                    # Auto-reload from spare if mag is now empty
                    if survivor["rifle_loaded"] == 0 and rif_spare > 0:
                        reload_amt = min(12, rif_spare)
                        survivor["rifle_loaded"] = reload_amt
                        survivor["rifle_spare"]  = rif_spare - reload_amt

                # Spend 1-2 revolver rounds if available
                rev_cost = min(random.randint(1, 2), survivor.get("revolver_loaded", 0))
                if rev_cost > 0:
                    survivor["revolver_loaded"] = survivor.get("revolver_loaded", 0) - rev_cost
                    # Auto-reload from spare if cylinder is empty
                    if survivor["revolver_loaded"] == 0 and survivor.get("revolver_spare", 0) > 0:
                        reload_amt = min(6, survivor["revolver_spare"])
                        survivor["revolver_loaded"] = reload_amt
                        survivor["revolver_spare"]  = survivor["revolver_spare"] - reload_amt

                total_ammo_spent = rif_cost + rev_cost
                if total_ammo_spent > 0:
                    ammo_report_lines.append(
                        f"🔫 {self._user_display(uid)} used {total_ammo_spent} round(s)"
                    )

            elif is_supply_choice and loot:
                # Supply/scavenge choices gain ammo
                rev_gain = loot["revolver_ammo"]
                if rev_gain > 0:
                    space_in_cylinder = max(0, 6 - survivor.get("revolver_loaded", 0))
                    to_cylinder = min(rev_gain, space_in_cylinder)
                    survivor["revolver_loaded"] = survivor.get("revolver_loaded", 0) + to_cylinder
                    survivor["revolver_spare"]  = survivor.get("revolver_spare",  0) + (rev_gain - to_cylinder)
                rif_gain = loot["rifle_ammo"]
                if rif_gain > 0:
                    space_in_mag = max(0, 12 - survivor.get("rifle_loaded", 0))
                    to_mag = min(rif_gain, space_in_mag)
                    survivor["rifle_loaded"] = survivor.get("rifle_loaded", 0) + to_mag
                    survivor["rifle_spare"]  = survivor.get("rifle_spare",  0) + (rif_gain - to_mag)

            # Loot stat bonuses on success (always apply HP/ST/MO regardless of choice type)
            if loot:
                survivor["health"]  = max(0, min(100, survivor["health"]  + loot["health"]))
                survivor["stamina"] = max(0, min(100, survivor["stamina"] + loot["stamina"]))
                survivor["morale"]  = max(0, min(100, survivor["morale"]  + loot["morale"]))

            # Death check
            if survivor["health"] <= 0 and survivor["status"] != "Deceased":
                survivor["status"] = "Deceased"
                death_report += f"\n💀 **{self._user_display(uid)} has fallen.**"

        if ammo_report_lines:
            outcome_text += f"\n\n**AMMO SPENT:** {', '.join(ammo_report_lines)}"

        if death_report:
            outcome_text += f"\n\n**CASUALTIES:**{death_report}"

        # ── Record history ────────────────────────────────────────────────────
        resolved_round = self.state["round"]
        resolved_event = self.state.get("current_event", "")

        self.state["history"].append({
            "round":        resolved_round,
            "event":        resolved_event,
            "outcome_text": outcome_text,
        })
        if len(self.state["history"]) > 5:
            self.state["history"] = self.state["history"][-5:]

        # ── Check if everyone is dead ─────────────────────────────────────────
        if self._all_dead():
            # Append the final history entry, then let _send_game_over wipe everything.
            await self.db.append_history(resolved_round, resolved_event, outcome_text)
            await self._send_game_over(channel, outcome_text)
            return

        # ── Build prompt for next round ───────────────────────────────────────
        history_lines = "\n".join(
            f"Round {h['round']}: {h['outcome_text'][:200]}"
            for h in self.state["history"]
        )
        survivor_lines = "\n".join(
            f"- {self._user_display(uid)}: "
            f"HP:{s['health']} ST:{s['stamina']} MO:{s['morale']} "
            f"RevAmmo:{s.get('revolver_loaded',0)+s.get('revolver_spare',0)} "
            f"RifAmmo:{s.get('rifle_loaded',0)+s.get('rifle_spare',0)} "
            f"[{s['status']}]"
            for uid, s in self.state["survivors"].items()
            if s.get("status") != "Deceased"
        ) or "No survivors remain."

        prompt = (
            f"STORY SO FAR (last {len(self.state['history'])} rounds):\n{history_lines}\n\n"
            f"LIVING SURVIVORS:\n{survivor_lines}\n\n"
            f"LAST EVENT: {resolved_event}\n"
            f"OUTCOME: {outcome_text}\n\n"
            "Continue the story. The next event must directly follow from the last outcome. "
            "Describe the immediate consequence, then present a new dangerous situation "
            "with exactly 4 distinct choices. Assign realistic base_odds to each choice. "
            "Keep it tense and grounded."
        )

        new_content = await self.generate_content(prompt)
        if not new_content:
            await channel.send("⚠️ The Game Master lost the thread. The story resumes shortly.")
            return

        next_round = resolved_round + 1
        self.state.update({
            "current_event": new_content["event_text"],
            "choices":       new_content["choices"][:4],
            "choice_odds":   new_content.get("choice_odds", [50, 50, 50, 50]),
            "world_impact":  new_content["world_impact"],
            "votes":         {},
            "voters":        [],
            "last_update":   datetime.now().timestamp(),
            "round":         next_round,
        })

        await self._save_with_history(resolved_round, resolved_event, outcome_text)
        self.bot.add_view(ZombieView(self))
        await self._send_round(channel)

    # ── Game over ─────────────────────────────────────────────────────────────

    async def _send_game_over(self, channel: discord.abc.Messageable, final_outcome: str):
        """Send the game-over embed, then fully wipe the game from DB and memory."""
        embed = discord.Embed(
            title="💀 THE LAST SURVIVOR HAS FALLEN",
            description=(
                "The dead have won. Every soul who dared to fight has been consumed.\n\n"
                f"*{final_outcome}*\n\n"
                "Use `/zombie_survival` to begin a new story."
            ),
            color=discord.Color.from_rgb(30, 0, 0),
        )
        embed.set_thumbnail(url=ZOMBIE_THUMBNAIL_URL)
        roster = "".join(
            f"💀 ~~{self._user_display(uid)}~~\n"
            for uid in self.state.get("survivors", {})
        )
        if roster:
            embed.add_field(name="The Fallen", value=roster, inline=False)
        embed.set_footer(text="Their story ends here. Use /zombie_survival to start a new game.")
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as e:
            log.error(f"Failed to send game-over embed: {e}")

        # Fully wipe DB and reset in-memory state so the next /zombie_survival
        # starts completely fresh with no leftover survivors or history.
        await self.db.reset()
        self.state = ZombieDB._default_state()

    # ── Message sending ───────────────────────────────────────────────────────

    async def _send_round(
        self,
        channel: discord.abc.Messageable,
        interaction: Optional[discord.Interaction] = None,
    ):
        """Send a fresh story embed for the current round and store its message ID."""
        embed = self._build_story_embed()
        view  = ZombieView(self)
        try:
            if interaction is not None:
                msg = await interaction.followup.send(embed=embed, view=view)
            else:
                msg = await channel.send(embed=embed, view=view)
            self.state["message_id"] = msg.id
            await self._save()
        except discord.HTTPException as e:
            log.error(f"Failed to send story embed: {e}")

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="zombie_survival", description="Start or join the Zombie Survival game.")
    async def zombie_survival(self, ctx: commands.Context):
        is_new_game = not self.state.get("active")

        if is_new_game:
            await self.db.reset()
            self.state = ZombieDB._default_state()
            self.state["active"]     = True
            self.state["channel_id"] = ctx.channel.id
            self.state["survivors"][str(ctx.author.id)] = _make_survivor()

            await ctx.defer()

            prompt = (
                "Start a brand new zombie survival story. "
                "Pick ONE of these opening scenarios at random — do not always use the same one:\n"
                "1. Survivors barricaded in a crumbling hospital as the power grid fails\n"
                "2. A small convoy ambushed on a highway overpass at dawn\n"
                "3. Refugees sheltering in a flooded subway station\n"
                "4. A farmhouse surrounded by a growing horde at nightfall\n"
                "5. Survivors trapped in a collapsed shopping mall with dwindling supplies\n"
                "6. A military checkpoint that has just gone dark and silent\n"
                "7. Survivors on a fishing boat watching the infected overrun the docks\n"
                "8. A school gymnasium turned refugee camp, now breached\n\n"
                "Write event_text as a gripping 3-5 sentence opening that establishes: "
                "WHERE the survivors are, WHAT immediate threat they face, and WHY they must "
                "act NOW. Make it feel like the first page of a novel — specific, visceral, "
                "with real stakes. Then provide exactly 4 distinct choices that reflect the "
                "actual situation you described. Assign varied choice_odds that reflect how "
                "risky each option genuinely is."
            )
            new_content = await self.generate_content(prompt)
            if not new_content:
                await ctx.followup.send(
                    "The apocalypse failed to materialise (AI error). Try again shortly.",
                    ephemeral=True,
                )
                return

            self.state.update({
                "current_event": new_content["event_text"],
                "choices":       new_content["choices"][:4],
                "choice_odds":   new_content.get("choice_odds", [50, 50, 50, 50]),
                "world_impact":  new_content["world_impact"],
                "last_update":   datetime.now().timestamp(),
                "round":         1,
            })
            await self._save()
            self.bot.add_view(ZombieView(self))
            await self._send_round(ctx.channel, interaction=ctx.interaction)

        else:
            uid = str(ctx.author.id)
            if uid not in self.state["survivors"]:
                self.state["survivors"][uid] = _make_survivor()
                await self._save()
                await ctx.send(
                    f"A new face emerges from the shadows. Welcome, {ctx.author.mention}. Stay alive.",
                    ephemeral=True,
                )
            else:
                await ctx.send("You're already in the thick of it.", ephemeral=True)

            await ctx.defer()
            await self._send_round(ctx.channel, interaction=ctx.interaction)

    @commands.hybrid_command(name="zombie_stop", description="End the current Zombie Survival game immediately.")
    @commands.has_permissions(manage_messages=True)
    async def zombie_stop(self, ctx: commands.Context):
        if not self.state.get("active"):
            await ctx.send("There's no active game to stop.", ephemeral=True)
            return

        # Wipe DB completely and reset in-memory state.
        await self.db.reset()
        self.state = ZombieDB._default_state()

        embed = discord.Embed(
            title="🛑 Game Stopped",
            description=(
                "The Zombie Survival game has been ended by a moderator.\n"
                "All progress has been wiped.\n\n"
                "Use `/zombie_survival` to start a fresh game."
            ),
            color=discord.Color.greyple(),
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="zombie_character", description="View your zombie survival character card.")
    async def zombie_character(self, ctx: commands.Context):
        """Shows your full character card as an ephemeral embed.
        If you're not in the game, explains how to join.
        """
        if not self.state.get("active"):
            await ctx.send(
                "No game is running. Use `/zombie_survival` to start one!",
                ephemeral=True,
            )
            return

        uid      = str(ctx.author.id)
        survivor = self.state["survivors"].get(uid)

        if not survivor:
            await ctx.send(
                "You're not in this game yet.\n"
                "Use `/zombie_survival` to join, or click any vote button — "
                "voting automatically adds you as a survivor.",
                ephemeral=True,
            )
            return

        hp  = survivor.get("health",  0)
        st  = survivor.get("stamina", 0)
        mo  = survivor.get("morale",  0)
        bar = "█" * (hp // 20) + "░" * (5 - hp // 20)

        if survivor["status"] == "Deceased":
            embed = discord.Embed(
                title=f"💀 {ctx.author.display_name} — Deceased",
                description="Your story has ended. You are among the fallen.",
                color=discord.Color.from_rgb(40, 40, 40),
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            embed.set_footer(text="Use /zombie_survival to start a new game.")
            await ctx.send(embed=embed, ephemeral=True)
            return

        voted     = "✅ Voted this round" if uid in [str(v) for v in self.state.get("voters", [])] else "⬜ Not voted yet"
        rev_loaded = survivor.get("revolver_loaded", 0)
        rev_spare  = survivor.get("revolver_spare",  0)
        rif_loaded = survivor.get("rifle_loaded",    0)
        rif_spare  = survivor.get("rifle_spare",     0)
        melee      = survivor.get("melee", "Unknown")

        embed = discord.Embed(
            title=f"🧟 {ctx.author.display_name}",
            description=f"**Status:** {survivor['status']}  •  {voted}",
            color=discord.Color.dark_green(),
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.add_field(name="❤️ Health",  value=f"`{bar}` {hp}/100", inline=True)
        embed.add_field(name="⚡ Stamina", value=f"{st}/100",         inline=True)
        embed.add_field(name="💙 Morale",  value=f"{mo}/100",         inline=True)
        embed.add_field(
            name="🔫 Revolver",
            value=f"`{rev_loaded}/6` loaded  +{rev_spare} spare",
            inline=True,
        )
        embed.add_field(
            name="🎯 Rifle",
            value=f"`{rif_loaded}/12` loaded  +{rif_spare} spare",
            inline=True,
        )
        embed.add_field(name="🗡️ Melee", value=melee, inline=True)
        embed.set_footer(text="Only you can see this. Use /zombie_character any time.")
        await ctx.send(embed=embed, ephemeral=True)

    @commands.command(name="force_zombie_update", hidden=True)
    @commands.is_owner()
    async def force_zombie_update(self, ctx):
        if not self.state.get("active"):
            await ctx.send("No active game.", ephemeral=True)
            return
        await ctx.send("Forcing round resolution…", ephemeral=True)
        await self.resolve_round()


# ── Persistent UI ─────────────────────────────────────────────────────────────

class ZombieView(discord.ui.View):
    """Vote buttons only — one row, A/B/C/D.
    custom_id encodes both the choice index AND the emoji set so the correct
    emoji is always shown and persistent view re-registration is unambiguous.
    """
    def __init__(self, cog: "ZombieSurvival"):
        super().__init__(timeout=None)
        self.cog = cog
        round_num     = cog.state.get("round", 1)
        emoji_set_idx = round_num % len(_CHOICE_EMOJI_SETS)
        choice_emojis = _get_choice_emojis(round_num)
        num_choices   = len(cog.state.get("choices", [])[:4])
        for i in range(num_choices):
            self.add_item(VoteButton(cog, i, choice_emojis[i], emoji_set_idx))


class VoteButton(discord.ui.Button):
    def __init__(
        self,
        cog: "ZombieSurvival",
        index: int,
        emoji: discord.PartialEmoji,
        emoji_set_idx: int,
    ):
        self.cog          = cog
        self.choice_index = index
        # Include emoji_set_idx in custom_id so each round's buttons are
        # uniquely registered and the correct emoji is always resolved.
        super().__init__(
            style=discord.ButtonStyle.primary,
            custom_id=f"zombie_vote_{index}_s{emoji_set_idx}",
            emoji=emoji,
            label=CHOICE_LABELS[index],   # fallback text if emoji fails to render
        )

    async def callback(self, interaction: discord.Interaction):
        uid       = str(interaction.user.id)
        survivors = self.cog.state.get("survivors", {})

        # Auto-add the user if they aren't in the game yet
        if uid not in survivors:
            survivors[uid] = _make_survivor()
            self.cog.state["survivors"] = survivors
            await self.cog._save()

        if survivors[uid].get("status") == "Deceased":
            await interaction.response.send_message(
                "The dead do not have a say.", ephemeral=True
            )
            return

        voters = [str(v) for v in self.cog.state.get("voters", [])]
        if uid in voters:
            await interaction.response.send_message(
                "You've already cast your vote this round.", ephemeral=True
            )
            return

        # Record vote
        self.cog.state.setdefault("voters", []).append(uid)
        votes = self.cog.state.setdefault("votes", {})
        key   = str(self.choice_index)
        votes[key] = votes.get(key, 0) + 1
        await self.cog._save()

        label       = CHOICE_LABELS[self.choice_index]
        choice_text = self.cog.state["choices"][self.choice_index]

        # Acknowledge immediately
        await interaction.response.send_message(
            f"Voted **{label}**: *{choice_text}*\nMay it be the right call.",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(ZombieSurvival(bot))
