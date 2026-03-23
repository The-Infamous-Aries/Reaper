import discord
import asyncio
from discord.ext import commands
from typing import Optional
from Systems.Functions import emoji as emoji_mod

class SnipeGuide(commands.Cog):
    """Snipe guide commands for Politics & War raiding."""
    
    def __init__(self, bot: commands.Bot, query_instance, calc_instance):
        self.bot = bot
        self.query = query_instance
        self.calc = calc_instance

    @commands.hybrid_command(  # type: ignore
        name="snipe_guide",
        description="Get a comprehensive guide on beige sniping and raiding"
    )
    async def snipe_guide(self, ctx: commands.Context):
        """Send the complete beige sniping guide as three messages with 1-second delay."""
        setup_text = f"""
Now i would like to start of by saying that you do **NOT** have to raid using the <@946351598223888414> bot! .. You can spend several minutes trolling nations and alliances in-game and hope you find someone unallied to anyone who will counter you who also has money {emoji_mod.mention('bounty') or '🔥'}{emoji_mod.mention('sleepy') or '🥱'} or you can raid like the **Pirate Master** {emoji_mod.mention('crown') or '🏆'} I am gonna turn you into! .. Now assuming your still reading this and not playing with pets like a nerd {emoji_mod.mention('nerd') or '🤓'}, I would like to **GREATLY** emphasize that it is **CRUCIAL** you are using a time app/site and preferable on 2 screens unless your good at timing (not me I got the rhythm of a limping T-Rex {emoji_mod.mention('trex') or '🦖'}) or you will be missing out on the beige targets with **LOTS** of money {emoji_mod.mention('wavecash') or '💸'}{emoji_mod.mention('moneyface') or '😭'} .. Now follow The Reapers' {emoji_mod.mention('reaper') or '🔥'} 10 steps of raiding and you will be set; 

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
9. Raid them {emoji_mod.mention('pirateflag') or '🏴‍☠️'} 
   * Quickest way to end a raid is in 7 attacks 
      * 5 Naval Attacks 
        * If they have **NO** Navy, send in 1 boat 
      * 3 Ground Attacks 
        * If they have **NO** Soldiers or Tanks, don't use ammo 
        * If they have **NO** actual money, don't use tanks 
   * If they are fighting back though, send what you need to at them to humble them to your liking! 
10. Win the Raid {emoji_mod.mention('crown') or '🏆'} 
   * The Naval Blockade stops them from buying or selling stuff so you loot more from them 
   * I promise on all things holy if you lose a raid war you started after reading my glorious guide, i will raid you myself! {emoji_mod.mention('punch') or '😤'}

Now that you know how to raid, get out there and show me what you got! .. Always remember; *Take what you can, Give nothing back!* {emoji_mod.mention('pirateflag') or '🏴‍☠️'}"""

        await ctx.send(setup_text)
        await asyncio.sleep(1)
        await ctx.send(execution_part1_text)
        await asyncio.sleep(1)
        await ctx.send(execution_part2_text)

    @commands.hybrid_command(  # type: ignore
        name="snipe_setup",
        description="Show the setup guide for finding and preparing beige targets"
    )
    async def snipe_setup(self, ctx: commands.Context):
        """Show the setup guide for beige sniping preparation."""
        setup_text = f"""
Now i would like to start of by saying that you do **NOT** have to raid using the <@946351598223888414> bot! .. You can spend several minutes trolling nations and alliances in-game and hope you find someone unallied to anyone who will counter you who also has money {emoji_mod.mention('bounty') or '🔥'}{emoji_mod.mention('sleepy') or '🥱'} or you can raid like the **Pirate Master** {emoji_mod.mention('crown') or '🏆'} I am gonna turn you into! .. Now assuming your still reading this and not playing with pets like a nerd {emoji_mod.mention('nerd') or '🤓'}, I would like to **GREATLY** emphasize that it is **CRUCIAL** you are using a time app/site and preferable on 2 screens unless your good at timing (not me I got the rhythm of a limping T-Rex {emoji_mod.mention('trex') or '🦖'}) or you will be missing out on the beige targets with **LOTS** of money {emoji_mod.mention('wavecash') or '💸'}{emoji_mod.mention('moneyface') or '😭'} .. Now follow The Reapers' {emoji_mod.mention('reaper') or '🔥'} 10 steps of raiding and you will be set; 

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

    @commands.hybrid_command(  # type: ignore
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
9. Raid them {emoji_mod.mention('pirateflag') or '🏴‍☠️'} 
   * Quickest way to end a raid is in 7 attacks 
      * 5 Naval Attacks 
        * If they have **NO** Navy, send in 1 boat 
      * 3 Ground Attacks 
        * If they have **NO** Soldiers or Tanks, don't use ammo 
        * If they have **NO** actual money, don't use tanks 
   * If they are fighting back though, send what you need to at them to humble them to your liking! 
10. Win the Raid {emoji_mod.mention('crown') or '🏆'} 
   * The Naval Blockade stops them from buying or selling stuff so you loot more from them 
   * I promise on all things holy if you lose a raid war you started after reading my glorious guide, i will raid you myself! {emoji_mod.mention('punch') or '😤'} 

Now that you know how to raid, get out there and show me what you got! .. Always remember; *Take what you can, Give nothing back!* {emoji_mod.mention('pirateflag') or '🏴‍☠️'}"""

        await ctx.send(execution_part1_text)
        await asyncio.sleep(1)
        await ctx.send(execution_part2_text)

    @commands.hybrid_command(  # type: ignore
        name="war_guide",
        description="Learn about Ground and Air Supremacy mechanics"
    )
    @discord.app_commands.choices(category=[
        discord.app_commands.Choice(name=f"Ground Supremacy 🪖", value="ground_sup"),
        discord.app_commands.Choice(name=f"Air Supremacy ✈️", value="air_sup"),
        discord.app_commands.Choice(name=f"Naval Blockade/Supremacy 🚢", value="naval_sup"),
        discord.app_commands.Choice(name=f"Missiles 🚀", value="missiles"),
        discord.app_commands.Choice(name=f"Nukes ☢️", value="nukes"),
        discord.app_commands.Choice(name=f"Fortification 🛡️", value="fortification"),
        discord.app_commands.Choice(name=f"Peace 🕊️", value="peace"),
        discord.app_commands.Choice(name=f"Key Strategy 📋", value="strategy"),
        discord.app_commands.Choice(name=f"Whole Guide ⚔️", value="all")
    ])
    async def war_guide(self, ctx: commands.Context, category: Optional[str] = None):
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
                "title": f"Missiles {emoji_mod.mention('missile') or '🚀'}",
                "content": f"""# Missiles {emoji_mod.mention('missile') or '🚀'}
• Takes small but reasonable chunks of infrastructure
• **Main benefit:** Can target specific improvement types (Any, Resources, Manufacturing, Civil, Commerce, Military)
• Destroys 2 improvements of selected type
• **Iron Dome counter:** 30% chance of shooting down missiles
• Iron Dome ALWAYS prevents 1 improvement from being destroyed"""
            },
            "nukes": {
                "title": f"Nukes {emoji_mod.mention('bomb') or '☢️'}",
                "content": f"""# Nukes {emoji_mod.mention('bomb') or '☢️'}
• Takes MASSIVE amounts of infrastructure
• **Limitation:** Can only pick which city to hit, NOT what improvements are destroyed
• **Cost:** ~$15m per nuke (depending on trade prices)
• **Rule:** NOT beneficial to shoot nukes at anything less than 2500 infra
• **Vital Defense System counter:** 25% chance of thwarting nukes
• VDS ALWAYS prevents 1 non-power plant, non-military improvement from being destroyed"""
            },
            "fortification": {
                "title": f"Fortification {emoji_mod.mention('fortification') or '🛡️'}",
                "content": f"""# Fortification {emoji_mod.mention('fortification') or '🛡️'}
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
                "title": f"Peace {emoji_mod.mention('peace_1') or '🕊️'}",
                "content": f"""# Peace {emoji_mod.mention('peace_1') or '🕊️'}
• **Definition:** End of conflicts before wars are Won or Expired
• **Reattack restriction:** Cannot reattack same nation for 12 turns after most recent war ends
• **Raid peace:** At discretion of attacker/defending nation
• **Alliance War peace:** ONLY with Alliance Government approval
• **IMPORTANT:** Peacing out "Alliance Wars" (counters for members/allies, group raids, alliance conflicts) BEFORE government instruction = **TREASON & COWARDICE**
• **Alliance Wars include:** Any attacks requested by alliance leadership
• **Rule:** Never peace alliance-sanctioned attacks until told to do so!"""
            },
            "strategy": {
                "title": f"Key Strategy {emoji_mod.mention('strategy') or '📋'}",
                "content": f"""# Key Strategy {emoji_mod.mention('strategy') or '📋'}
• Use Ground Attacks {emoji_mod.mention('soldier') or ''}{emoji_mod.mention('tank') or ''} for looting and aircraft elimination, Air Attacks {emoji_mod.mention('jet') or ''} for reducing enemy tank effectiveness & targeting units, Naval Attacks {emoji_mod.mention('ship') or '🚢'} for blockade & removing enemy Sup, Missiles {emoji_mod.mention('missile') or '🚀'} for targeted improvement destruction, and Nukes {emoji_mod.mention('bomb') or '☢️'} for massive infrastructure damage!
• Fortify {emoji_mod.mention('fortification') or '🛡️'} only as absolute last resort!
• Peace {emoji_mod.mention('peace_1') or '🕊️'} wisely - personal raids are flexible, alliance wars require permission!"""
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
    alliance_cog = bot.get_cog('AllianceManager')
    if alliance_cog:
        query_instance = getattr(alliance_cog, 'query_system', None)
        calc_instance = getattr(alliance_cog, 'calc_system', None)
        if query_instance and calc_instance:
            await bot.add_cog(SnipeGuide(bot, query_instance, calc_instance))
        else:
            # Fallback: create instances if not available from AllianceManager
            try:
                from Systems.PnW.Util.query import create_v3_query_instance
                from Systems.PnW.Util.calc import AllianceCalculator
                from Systems.Functions.config import PANDW_API_KEY
                import logging

                logger = logging.getLogger(f"{__name__}")
                query_instance = create_v3_query_instance(api_key=PANDW_API_KEY, logger=logger)
                calc_instance = AllianceCalculator(query_instance)
                await bot.add_cog(SnipeGuide(bot, query_instance, calc_instance))
                logging.info("SnipeGuide cog loaded with fallback instances!")
            except Exception as e:
                logging.error(f"Failed to load SnipeGuide cog with fallback: {e}")
    else:
        # AllianceManager not loaded yet, try fallback immediately
        try:
            from Systems.PnW.Util.query import create_v3_query_instance
            from Systems.PnW.Util.calc import AllianceCalculator
            from Systems.Functions.config import PANDW_API_KEY
            import logging

            logger = logging.getLogger(f"{__name__}")
            query_instance = create_v3_query_instance(api_key=PANDW_API_KEY, logger=logger)
            calc_instance = AllianceCalculator(query_instance)
            await bot.add_cog(SnipeGuide(bot, query_instance, calc_instance))
            logging.info("SnipeGuide cog loaded with fallback instances (AllianceManager not found)!")
        except Exception as e:
            logging.error(f"Failed to load SnipeGuide cog: {e}")
