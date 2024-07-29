import discord
from config import config
from discord.ext import commands
from discord import Option, Interaction, ApplicationContext, Embed, Message, File
from discord.commands import slash_command
from utilities import get_osu_user, get_osu_api
import random
import asyncio
import time
from typing import Dict, List, Set, Tuple, Optional

class AiDebate(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @slash_command(guild_ids=config.get_servers(cog_name='ai_debate'), name="test")
    async def ai_debate(self, ctx: ApplicationContext):
        await ctx.send("Test command ran!", silent=True, view=TestView())
        
        
class TestView(discord.ui.View):
    def __init__(self):
        super().__init__()

    @discord.ui.button(label="Test", style=discord.ButtonStyle.primary)
    async def test_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message("Button clicked!", ephemeral=True)

def setup(bot: commands.Bot):
    bot.add_cog(AiDebate(bot))