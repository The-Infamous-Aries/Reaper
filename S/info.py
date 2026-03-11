import discord  
from discord.ext import commands  
from discord import app_commands  
import json  
from pathlib import Path  
from datetime import datetime  
import asyncio  
from Systems.Functions import emoji as emoji_mod  

class InfoSystem(commands.Cog):  
    def __init__(self, bot):  
        self.bot = bot  

    @commands.hybrid_command(name="information", description="Send the information embed to the current channel")  
    async def information(self, ctx):  
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

async def setup(bot):  
    await bot.add_cog(InfoSystem(bot))