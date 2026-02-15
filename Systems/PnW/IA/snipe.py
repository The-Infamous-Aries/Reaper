import discord
from discord import app_commands
import asyncio
from discord.ext import commands
from typing import Optional, List, Dict, Any, Tuple, Union
from discord.ui import Select, View
from Systems.PnW.Util.query import create_query_instance
from Systems.Functions import emoji as emoji_mod

class SnipeGuide(commands.Cog):
    """Snipe guide commands for Politics & War raiding."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.query = create_query_instance() if callable(create_query_instance) else None
        self._resource_emojis = {}

    def _build_emoji_map_for_guild(self, guild: Optional[discord.Guild]) -> dict:
        return dict(self._resource_emojis)

    @commands.hybrid_command(
        name="snipe_guide",
        description="Get a comprehensive guide on beige sniping and raiding"
    )
    async def snipe_guide(self, ctx: commands.Context):
        """Send the complete beige sniping guide as three messages with 1-second delay."""
        setup_text = f"""
Now i would like to start of by saying that you do **NOT** have to raid using the <@946351598223888414> bot! .. You can spend several minutes trolling nations and alliances in-game and hope you find someone unallied to anyone who will counter you who also has money {emoji_mod.mention('Tired') or '🥱'} or you can raid like the **Non-Countered Raider** I am gonna turn you into! .. Now assuming your still reading this and not playing with pets like a nerd {emoji_mod.mention('Smart') or '🤓'}, I would like to **GREATLY** emphasize that it is **CRUCIAL** you are using a time app/site and preferable on 2 screens unless your good at timing (not me I got the rhythm of a limping T-Rex {emoji_mod.mention('Alligator') or '🦖'} ) or you will be missing out on the beige targets with **LOTS** of money {emoji_mod.mention('Gold') or '💸'} {emoji_mod.mention('Sick') or '😭'} .. Now follow The Reapers's 10 steps of raiding and you will be set; 

1. Run command ```/raids **Your Nation Score**``` 
   * Please only run in DMs or a *Member Only* channel 
2. Answer the prompts with the following; 
   * Webpage or Embed (I suggest webpage)
   * Applicants and Nations not in alliances 
   * 1 or less (Doesnt matter)
   * I don't care (The more inactive the better but use common sense)
   * Yes 
   * $10 million (You can pick whatever but less than $10m aint worth the wait)
   * Yes 
     * The bot saves your answers so next time you run it just answer yes and it will run the same 
3. Click see targets then link that pops up 
4. Set a reminder unless not in beige 
   * If not in beige just attack now and ignore the rest of this till later on 
   * I recommend not raiding a Top 50 alliance or their applicants """

        execution_part1_text = """Now that you have reminders set the bot with DM you with updates on the nation coming out of beige or when they leave beige early. The only real notification you need to pay attention to is the ***15 mins***. Once in the 15 min range follow these next steps to avoid missing one of 3 defense slots that others are also gunning for; 

5. Open the nations "Declare War" page 
   * Do so now to avoid turn change 
   * If you wish to type a custom War Reason now is the time 
6. Also open the time app or website for an accurate clock 
   * I use `https://time.is/`  but you can find another if you like 
   * Please note that most turns last for 30 **seconds** before & after the actual hour 
   * Day change last for 10 **minutes** before & after the actual hour 
      * So the one at 3:00 wont end until 3:00:30 
      * Day change wont end till x:10:00
        * Technically because of the delay at DC you will have a slightly bigger window for declaring but not much
7. At x:00:15 do the captcha 
   * They only last for like 30 seconds so don't do it to fast """

        execution_part2_text = f"""8. On **EXACTLY** x:00:30 (x:10:00 on DC) click the "Declare War" button 
   * Doing so too early will result in a error page! 
   * Doing so too late will result in not getting a slot! 
9. Raid them {emoji_mod.mention('MA') or '🏴‍☠️'} 
   * Quickest way to end a raid is in 7 attacks 
      * 5 Naval Attacks 
        * If they have **NO** Navy, send in 1 boat 
      * 3 Ground Attacks 
        * If they have **NO** Soldiers or Tanks, don't use ammo 
        * If they have **NO** actual money, don't use tanks 
   * If they are fighting back though, send what you need to at them to humble them to your liking! 
10. Win the Raid {emoji_mod.mention('Win') or '🏆'} 
   * The Naval Blockade stops them from buying or selling stuff so you loot more from them 
   * I promise on all things holy if you lose a raid war you started after reading my glorious guide, i will raid you myself! {emoji_mod.mention('Angry_1') or '😤'} 

Now that you know how to raid, get out there and show me what you got! .. Always remember; *Take what you can, Give nothing back!* {emoji_mod.mention('MA') or '🏴‍☠️'}"""

        await ctx.send(setup_text)
        await asyncio.sleep(1)
        await ctx.send(execution_part1_text)
        await asyncio.sleep(1)
        await ctx.send(execution_part2_text)

    def _build_trade_embed_sync(
        self,
        data: List[Dict[str, Any]],
        mode: str,
        amounts_map: Dict[str, Optional[float]],
        emoji_map: Dict[str, str],
        prefer_emoji: bool
    ) -> discord.Embed:
        """Synchronous helper to build the trade values embed."""
        raw_resources = {"FOOD", "COAL", "OIL", "URANIUM", "LEAD", "IRON", "BAUXITE"}
        refined_resources = {"GASOLINE", "MUNITIONS", "STEEL", "ALUMINUM"}
        special_resources = {"CREDIT"}

        # Build a quick lookup for conversion mode
        price_map = {str(item.get("resource") or "").upper(): float(item.get("average_price") or 0) for item in data}

        def fmt_name(r: str) -> str:
            return r.capitalize() if r else r

        # Mode logic
        mode_key = (mode or "All").strip().lower()
        if mode_key == "conversion":
            provided = [(k, float(v)) for k, v in amounts_map.items() if v is not None and float(v) > 0]
            if not provided:
                return None  # Signal to caller to send help message

            # Build conversion embed with per-resource breakdown and totals
            embed = discord.Embed(
                description="Convert resource units into money using average price",
                color=discord.Color.blurple(),
            )
            try:
                embed.set_author(name="Resource Conversion")
            except Exception:
                embed.title = "Resource Conversion"

            grand_total = 0.0
            money_emoji = emoji_mod.mention('Gold') or '💲'
            for res_key, amt in provided:
                unit_price = float(price_map.get(res_key, 0) or 0)
                total_value = unit_price * amt
                grand_total += total_value
                emoji = emoji_map.get(res_key)
                name_disp = f"{emoji} {fmt_name(res_key)}" if prefer_emoji and emoji else fmt_name(res_key)
                embed.add_field(name=name_disp, value=f"Units: {amt:,.2f} • Unit: {money_emoji}{unit_price:,.2f} • Total: {money_emoji}{total_value:,.2f}", inline=False)

            embed.add_field(name="Grand Total", value=f"{money_emoji}{grand_total:,.2f}", inline=False)
            embed.set_footer(text="Data source: P&W GraphQL API")
            return embed
        else:
            # Default: show all average prices (current embed)
            raw_lines = []
            ref_lines = []
            spec_lines = []
            for item in sorted(data, key=lambda x: x.get("resource", "")):
                res = (item.get("resource") or "").upper()
                avg = item.get("average_price") or 0
                emoji = emoji_map.get(res)
                if prefer_emoji and emoji:
                    line = f"{emoji} {fmt_name(res)}: {avg:,}"
                else:
                    line = f"{fmt_name(res)}: {avg:,}"
                if res in raw_resources:
                    raw_lines.append(line)
                elif res in refined_resources:
                    ref_lines.append(line)
                elif res in special_resources:
                    spec_lines.append(line)
                else:
                    ref_lines.append(line)

            embed = discord.Embed(
                description="Market averages for all resources",
                color=discord.Color.gold(),
            )
            name = "Average Trade Prices"
            try:
                embed.set_author(name=name)
            except Exception:
                embed.title = name
            if raw_lines:
                embed.add_field(name="Raw Materials", value="\n".join(raw_lines), inline=False)
            if ref_lines:
                embed.add_field(name="Refined Materials", value="\n".join(ref_lines), inline=False)
            if spec_lines:
                embed.add_field(name="Special", value="\n".join(spec_lines), inline=False)

            embed.set_footer(text="Data source: P&W GraphQL API")
            return embed

    @commands.hybrid_command(
        name="trade_values",
        description="Show average resource prices or convert units to value"
    )
    @app_commands.describe(
        mode="Choose 'All' for averages or 'Conversion' to convert units",
        food="Units of Food to convert",
        coal="Units of Coal to convert",
        oil="Units of Oil to convert",
        uranium="Units of Uranium to convert",
        lead="Units of Lead to convert",
        iron="Units of Iron to convert",
        bauxite="Units of Bauxite to convert",
        gasoline="Units of Gasoline to convert",
        munitions="Units of Munitions to convert",
        steel="Units of Steel to convert",
        aluminum="Units of Aluminum to convert",
        credit="Units of Credit to convert"
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="All", value="All"),
            app_commands.Choice(name="Conversion", value="Conversion"),
        ]
    )
    async def trade_values(
        self,
        ctx: commands.Context,
        mode: str = "All",
        food: Optional[float] = None,
        coal: Optional[float] = None,
        oil: Optional[float] = None,
        uranium: Optional[float] = None,
        lead: Optional[float] = None,
        iron: Optional[float] = None,
        bauxite: Optional[float] = None,
        gasoline: Optional[float] = None,
        munitions: Optional[float] = None,
        steel: Optional[float] = None,
        aluminum: Optional[float] = None,
        credit: Optional[float] = None,
    ):
        """Display average prices or convert a resource amount to its value.

        - mode: 'All' shows current embed for all average resource prices.
        - mode: 'Conversion' lets users select a resource and enter a unit amount to convert to money.
        """
        try:
            if not self.query:
                await ctx.send("Trade query is unavailable. Please try again later.")
                return

            # Fetch all resources' average prices
            data = await self.query.get_trade_resource_values()
            if not data:
                await ctx.send("Could not fetch trade values from the API.")
                return

            emoji_map = emoji_mod.resource_codes()
            # Always prefer emojis now that they are Application Emojis
            prefer_emoji = True

            amounts_map = {
                "FOOD": food,
                "COAL": coal,
                "OIL": oil,
                "URANIUM": uranium,
                "LEAD": lead,
                "IRON": iron,
                "BAUXITE": bauxite,
                "GASOLINE": gasoline,
                "MUNITIONS": munitions,
                "STEEL": steel,
                "ALUMINUM": aluminum,
                "CREDIT": credit,
            }

            embed = await asyncio.to_thread(
                self._build_trade_embed_sync,
                data,
                mode,
                amounts_map,
                emoji_map,
                prefer_emoji
            )

            if embed is None:
                await ctx.send("Provide units for any resource fields when mode is 'Conversion', e.g., /trade_values mode:Conversion iron:200 oil:50")
                return

            await ctx.send(embed=embed)
        except Exception:
            await ctx.send("An unexpected error occurred while building the trade values embed.")

    @commands.hybrid_command(
        name="snipe_setup",
        description="Show the setup guide for finding and preparing beige targets"
    )
    async def snipe_setup(self, ctx: commands.Context):
        """Show the setup guide for beige sniping preparation."""
        setup_text = f"""
Now i would like to start of by saying that you do **NOT** have to raid using the <@946351598223888414> bot! .. You can spend several minutes trolling nations and alliances in-game and hope you find someone unallied to anyone who will counter you who also has money {emoji_mod.mention('Tired') or '🥱'} or you can raid like the **Non-Countered Raider** I am gonna turn you into! .. Now assuming your still reading this and not playing with pets like a nerd {emoji_mod.mention('Smart') or '🤓'}, I would like to **GREATLY** emphasize that it is **CRUCIAL** you are using a time app/site and preferable on 2 screens unless your good at timing (not me I got the rhythm of a limping T-Rex {emoji_mod.mention('Alligator') or '🦖'} ) or you will be missing out on the beige targets with **LOTS** of money {emoji_mod.mention('Gold') or '💸'} {emoji_mod.mention('Sick') or '😭'} .. Now follow Killbot3000's 10 steps of raiding and you will be set; 

1. Run command ```/raids **Your Nation Score**``` 
   * Please only run in DMs or a *Member Only* channel 
2. Answer the prompts with the following; 
   * Webpage or Embed (I suggest webpage)
   * Applicants and Nations not in alliances 
   * 1 or less (Doesnt matter)
   * I don't care (The more inactive the better but use common sense)
   * Yes 
   * $10 million (You can pick whatever but less than $10m aint worth the wait)
   * Yes 
     * The bot saves your answers so next time you run it just answer yes and it will run the same 
3. Click see targets then link that pops up 
4. Set a reminder unless not in beige 
   * If not in beige just attack now and ignore the rest of this till later on 
   * I recommend not raiding a Top 50 alliance or their applicants """

        await ctx.send(setup_text)

    @commands.hybrid_command(
        name="snipe_execute",
        description="Show the execution guide for timing and attacking beige targets"
    )
    async def snipe_execute(self, ctx: commands.Context):
        """Show the execution guide for beige sniping attacks."""
        execution_part1_text = """Now that you have reminders set the bot with DM you with updates on the nation coming out of beige or when they leave beige early. The only real notification you need to pay attention to is the ***15 mins***. Once in the 15 min range follow these next steps to avoid missing one of 3 defense slots that others are also gunning for; 

5. Open the nations "Declare War" page 
   * Do so now to avoid turn change 
   * If you wish to type a custom War Reason now is the time 
6. Also open the time app or website for an accurate clock 
   * I use `https://time.is/`  but you can find another if you like 
   * Please note that most turns last for 30 **seconds** before & after the actual hour 
   * Day change last for 10 **minutes** before & after the actual hour 
      * So the one at 3:00 wont end until 3:00:30 
      * Day change wont end till x:10:00
        * Technically because of the delay at DC you will have a slightly bigger window for declaring but not much
7. At x:00:15 do the captcha 
   * They only last for like 30 seconds so don't do it to fast """

        execution_part2_text = f"""8. On **EXACTLY** x:00:30 (x:10:00 on DC) click the "Declare War" button 
   * Doing so too early will result in a error page! 
   * Doing so too late will result in not getting a slot! 
9. Raid them {emoji_mod.mention('MA') or '🏴‍☠️'} 
   * Quickest way to end a raid is in 7 attacks 
      * 5 Naval Attacks 
        * If they have **NO** Navy, send in 1 boat 
      * 3 Ground Attacks 
        * If they have **NO** Soldiers or Tanks, don't use ammo 
        * If they have **NO** actual money, don't use tanks 
   * If they are fighting back though, send what you need to at them to humble them to your liking! 
10. Win the Raid {emoji_mod.mention('Win') or '🏆'} 
   * The Naval Blockade stops them from buying or selling stuff so you loot more from them 
   * I promise on all things holy if you lose a raid war you started after reading my glorious guide, i will raid you myself! {emoji_mod.mention('Angry_1') or '😤'} 

Now that you know how to raid, get out there and show me what you got! .. Always remember; *Take what you can, Give nothing back!* {emoji_mod.mention('MA') or '🏴‍☠️'}"""

        await ctx.send(execution_part1_text)
        await asyncio.sleep(1)
        await ctx.send(execution_part2_text)

    @commands.hybrid_command(
        name="war_guide",
        description="Learn about Ground and Air Supremacy mechanics"
    )
    @discord.app_commands.choices(category=[
        discord.app_commands.Choice(name=f"Ground Supremacy {emoji_mod.mention('LandSup') or '🪖'}", value="ground_sup"),
        discord.app_commands.Choice(name=f"Air Supremacy {emoji_mod.mention('AirSup') or '✈️'}", value="air_sup"),
        discord.app_commands.Choice(name=f"Naval Blockade/Supremacy {emoji_mod.mention('NavySup') or '🚢'}", value="naval_sup"),
        discord.app_commands.Choice(name=f"Missiles {emoji_mod.mention('MA') or '🚀'}", value="missiles"),
        discord.app_commands.Choice(name=f"Nukes {emoji_mod.mention('MA') or '☢️'}", value="nukes"),
        discord.app_commands.Choice(name=f"Fortification {emoji_mod.mention('Defend') or '🛡️'}", value="fortification"),
        discord.app_commands.Choice(name=f"Peace {emoji_mod.mention('Peace') or '🕊️'}", value="peace"),
        discord.app_commands.Choice(name=f"Key Strategy {emoji_mod.mention('Info') or '📋'}", value="strategy"),
        discord.app_commands.Choice(name=f"Whole Guide {emoji_mod.mention('MA') or '⚔️'}", value="all")
    ])
    async def war_guide(self, ctx: commands.Context, category: str = None):
        """Send the war supremacy guide with optional category selection."""
        
        # Define all the category messages
        categories = {
            "ground_sup": {
                "title": f"Ground Supremacy {emoji_mod.mention('LandSup') or '🪖'}",
                "content": f"""# Ground Supremacy {emoji_mod.mention('LandSup') or '🪖'}
• Used to loot enemy nations and eliminate Aircraft
• Must achieve "Immense Triumph" in first ground attack to gain Ground Supremacy
• All subsequent ground attacks (using Tanks) will destroy enemy aircraft in addition to ground forces
• This allows you to target both ground and air units simultaneously"""
            },
            "air_sup": {
                "title": f"Air Supremacy {emoji_mod.mention('AirSup') or '✈️'}", 
                "content": f"""# Air Supremacy {emoji_mod.mention('AirSup') or '✈️'}
• Cuts enemy tanks effectiveness in half (attack and defense calculations)
• Allows targeting of ANY enemy unit types:
  - Soldiers
  - Tanks  
  - Aircraft
  - Ships
• Provides tactical flexibility to strike any enemy forces"""
            },
            "naval_sup": {
                "title": f"Naval Blockade/Supremacy {emoji_mod.mention('NavySup') or '🚢'}",
                "content": f"""# Naval Blockade/Supremacy {emoji_mod.mention('NavySup') or '🚢'}
• Cuts off a nation's ability to buy, sell, bank or withdraw resources
• Allows targeting of Ground and Air Supremacy
• **Important:** Does NOT eliminate units but takes away enemy Sup in targeted category (if Immense Triumph achieved)
• Essential for economic warfare and resource denial"""
            },
            "missiles": {
                "title": f"Missiles {emoji_mod.mention('MA') or '🚀'}",
                "content": f"""# Missiles {emoji_mod.mention('MA') or '🚀'}
• Takes small but reasonable chunks of infrastructure
• **Main benefit:** Can target specific improvement types (Any, Resources, Manufacturing, Civil, Commerce, Military)
• Destroys 2 improvements of selected type
• **Iron Dome counter:** 30% chance of shooting down missiles
• Iron Dome ALWAYS prevents 1 improvement from being destroyed"""
            },
            "nukes": {
                "title": f"Nukes {emoji_mod.mention('MA') or '☢️'}",
                "content": f"""# Nukes {emoji_mod.mention('MA') or '☢️'}
• Takes MASSIVE amounts of infrastructure
• **Limitation:** Can only pick which city to hit, NOT what improvements are destroyed
• **Cost:** ~$15m per nuke (depending on trade prices)
• **Rule:** NOT beneficial to shoot nukes at anything less than 2500 infra
• **Vital Defense System counter:** 25% chance of thwarting nukes
• VDS ALWAYS prevents 1 non-power plant, non-military improvement from being destroyed"""
            },
            "fortification": {
                "title": f"Fortification {emoji_mod.mention('Defend') or '🛡️'}",
                "content": f"""# Fortification {emoji_mod.mention('Defend') or '🛡️'}
• **ONLY use as "Worst Case Scenario" action**
• Even with more enemy units, fortifying is rarely strategically smart
• **Better alternatives:**
  - Swap War Policy to 'Blitzkrieg' and send units kamikaze-style to reduce enemy forces
  - Decom units (if none made today) to reduce destruction and gain Alum from Planes for Missiles/Nukes
  - Attack different front (Ground/Air/Navy) to reduce units/supremacy before fortifying
• **Fortify drawbacks:**
  - Wastes MAPs (Military Action Points)
  - ANY other action removes fortified stance
  - Leaves you vulnerable after stance breaks"""
            },
            "peace": {
                "title": f"Peace {emoji_mod.mention('Peace') or '🕊️'}",
                "content": f"""# Peace {emoji_mod.mention('Peace') or '🕊️'}
• **Definition:** End of conflicts before wars are Won or Expired
• **Reattack restriction:** Cannot reattack same nation for 12 turns after most recent war ends
• **Raid peace:** At discretion of attacker/defending nation
• **Alliance War peace:** ONLY with Alliance Government approval
• **IMPORTANT:** Peacing out "Alliance Wars" (counters for members/allies, group raids, alliance conflicts) BEFORE government instruction = **TREASON & COWARDICE**
• **Alliance Wars include:** Any attacks requested by alliance leadership
• **Rule:** Never peace alliance-sanctioned attacks until told to do so!"""
            },
            "strategy": {
                "title": f"Key Strategy {emoji_mod.mention('Info') or '📋'}",
                "content": f"""# Key Strategy {emoji_mod.mention('Info') or '📋'}
• Use Ground Sup for looting and aircraft elimination, Air Sup for reducing enemy tank effectiveness, Naval Sup for economic warfare, Missiles for targeted improvement destruction, and Nukes for massive infrastructure damage!
• Fortify only as absolute last resort!
• Peace wisely - personal raids are flexible, alliance wars require permission!"""
            }
        }
        
        # If a specific category was provided via command parameter, send just that one
        if category and category in categories:
            await ctx.send(categories[category]["content"])
            return
        
        # If "all" was selected or no category specified, send all categories with 1-second delays
        if category == "all" or category is None:
            await ctx.send("📚 **Complete War Guide** - All categories:")
            
            for i, (key, category_data) in enumerate(categories.items()):
                await ctx.send(category_data["content"])
                if i < len(categories) - 1:  # Don't delay after the last message
                    await asyncio.sleep(1)
            return

async def setup(bot: commands.Bot):
    """Add only the SnipeGuide cog; MA modules are loaded by the main bot."""
    try:
        await bot.add_cog(SnipeGuide(bot))
    except Exception as e:
        print(f"Error adding SnipeGuide cog in snipe.setup: {e}")
