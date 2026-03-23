import discord  
from discord.ext import commands  
from discord import app_commands  
import json  
from pathlib import Path  
from datetime import datetime  
import asyncio  
from Systems.Functions import emoji as emoji_mod  
from Systems.Functions.web_server import get_public_url  

class InfoSystem(commands.Cog):  
    def __init__(self, bot):  
        self.bot = bot  

    @commands.hybrid_command(name="leadership", description="Send the Leadership embed to the current channel")  
    async def leadership(self, ctx):  
        # Build Leadership String  
        leadership_text = (   
            f"1ic {emoji_mod.mention('1ic')} - <@941869945967480842>\n"  
            f"2ic {emoji_mod.mention('2ic')} - <@1357987963878903898> & <@1317311041209896960>\n"  
            f"IA (Internal Affairs) {emoji_mod.mention('IA')} - <@1246226717841031331>\n"  
            f"MA (Military Affairs) {emoji_mod.mention('MA')} -\n"  
            f"FA (Foreign Affairs) {emoji_mod.mention('FA')} -\n"  
            f"EA (Economic Affairs) {emoji_mod.mention('EA')} - <@250297961362227201>\n"  
            f"JA (Judicial Affairs) {emoji_mod.mention('JA')} -\n"  
            f"TA (Technical Affairs) {emoji_mod.mention('TA')} -"  
        )  
        
        embed = discord.Embed(  
            title="Alliance Leadership",  
            description=f"{leadership_text}",  
            color=discord.Color.gold() 
        )  
        
        # Send embed to the current channel  
        await ctx.send(embed=embed)  
        await ctx.send("✅ Information embed sent.", ephemeral=True)  

    @commands.hybrid_command(name="webpage", description="Get the link to the bot's web interface")  
    async def webpage(self, ctx):  
        """Sends the web interface URL as a masked link."""  
        public_url = get_public_url()  
        
        if public_url:  
            await ctx.send(
                f"Click [HERE]({public_url}) for 😎 **Cool** 💀 **Reaper** 🤩 **Fun**",
                ephemeral=False
            )  
        else:  
            await ctx.send(
                "❌ Web interface is not currently accessible. Try: http://localhost:8080",
                ephemeral=False
            )  

async def setup(bot):  
    await bot.add_cog(InfoSystem(bot))