import discord
from config import config
from discord.ext import commands
from discord import Option
from discord.commands import (
    slash_command,
)
from discord import Embed
from utilities import get_osu_user, get_osu_api

from . import game_db, BgGameDatabase

class MyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @slash_command(guild_ids=config.get_servers(), name="bg_game")
    async def bg_game(self, ctx: discord.ApplicationContext):
        view = SignUpView(self, ctx.author.id)
        await view.update_embed(ctx)


class RegisterModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.InputText(label="Input"))

    async def callback(self, interaction: discord.Interaction):
        
        user_input = self.children[0].value
        
        user = await get_osu_user(user_input)
        
        if not user:
            await interaction.response.send_message(f"User not found {user_input} Try again with just the ID", ephemeral=True)
            return
        
        game_db.add_user(interaction.user.id, user.id)
        
        await interaction.response.send_message(f"User found: {user.username} ({user.id}) registered\nhttps://osu.ppy.sh/users/{user.id}\nIf this is a mistake register with another name", ephemeral=True)
        await self.add_user_maps(user)

    async def add_user_maps(self, user):
        api = get_osu_api()
        user_beatmaps = []
        
        print(f"Adding maps for {user.username}")
        
        for i in range(0,(user.beatmap_playcounts_count // 10) // 100):
            user_beatmaps += await api.user_beatmaps(user.id, limit=100, type="most_played", offset=i*100)
        
        #user_beatmaps += await api.user_beatmaps(user.id, limit=100, type="favourite")
            
        map_ids = [(beatmap.beatmap_id, beatmap.beatmapset.id) for beatmap in user_beatmaps]

        game_db.add_maps_batch(map_ids)
        game_db.add_play_history_batch([(user.id, beatmap.beatmap_id) for beatmap in user_beatmaps])
        
        print(f"Added {len(map_ids)} maps to the database")
    
    
    
class SignUpView(discord.ui.View):
    def __init__(self, cog, host_id: int = None):
        super().__init__()
        self.cog = cog
        self.message = None
        self.host = host_id
        self.players = [] # list of discord_id, is_registered (int, bool)
    
    
    def get_embed(self):
        display = "\n".join([f"<@{player[0]}> {'✅' if player[1] else '❌'}" for player in self.players])
        embed = Embed(title="Sign Up", description=display)
        return embed
    

    async def update_embed(self, ctx: discord.ApplicationContext):
        embed = self.get_embed()
        if self.message:
            await self.message.edit(embed=embed, view=self)
            await ctx.response.defer()
        elif ctx:
            await ctx.response.send_message(embed=embed, view=self)
            self.message = ctx.message
    
    @discord.ui.button(label="Join", style=discord.ButtonStyle.green, custom_id="join_button")
    async def join_button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        
        db_user = game_db.get_user(interaction.user.id)
        
        self.players.append((interaction.user.id, db_user is not None))
        await self.update_embed(interaction)
    
    @discord.ui.button(label="Register", style=discord.ButtonStyle.primary)
    async def register_button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        modal = RegisterModal(title="Enter your osu username or user id")
        await interaction.response.send_modal(modal)
        
    @discord.ui.button(label="Start", style=discord.ButtonStyle.primary)
    async def start_button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message("Starting game")
        osu_ids = game_db.get_osu_ids_from_discord([player[0] for player in self.players if player[1]])
        common_maps = game_db.get_common_maps(osu_ids)
        common_sets = [mapset for _, mapset in common_maps]

def setup(bot: commands.Bot):
    bot.add_cog(MyCog(bot))