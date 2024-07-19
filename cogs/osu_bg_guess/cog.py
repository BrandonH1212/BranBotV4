import discord
from config import config
from discord.ext import commands
from discord import Option
from discord.commands import (
    slash_command,
)
from discord import Embed
from utilities import get_osu_user, get_osu_api
import random
import asyncio
import time

from . import game_db, BgGameDatabase, get_image_grid, get_preview

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
        
        for i in range(0,(user.beatmap_playcounts_count) // 100):
            user_beatmaps += await api.user_beatmaps(user.id, limit=100, type="most_played", offset=i*100)
        
        #user_beatmaps += await api.user_beatmaps(user.id, limit=100, type="favourite")
            
        map_ids = [(beatmap.beatmap_id, beatmap.beatmapset.id) for beatmap in user_beatmaps]

        #game_db.add_maps_batch(map_ids)
        game_db.add_play_history_batch([(user.id, beatmap.beatmapset.id) for beatmap in user_beatmaps])
        
        print(f"Added {len(map_ids)} maps to the database")
    
    
    
class SignUpView(discord.ui.View):
    def __init__(self, cog, host_id: int = None):
        super().__init__()
        self.cog = cog
        self.message = None
        self.host = host_id
        self.players = {host_id: True} if host_id else {}
    
    
    def get_embed(self):
        display = "\n".join([f"<@{player}>: {'✅' if self.players[player] else '❌'}" for player in self.players])
        embed = Embed(title="Sign up for the game", description=display)
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
        if interaction.user.id in self.players:
            return await interaction.response.send_message("You are already signed up", ephemeral=True)
        else:
            db_user = game_db.get_user(interaction.user.id)
            
            self.players[interaction.user.id] = db_user is not None
            await self.update_embed(interaction)
    
    @discord.ui.button(label="Register", style=discord.ButtonStyle.primary)
    async def register_button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        modal = RegisterModal(title="Enter your osu username or user id")
        await interaction.response.send_modal(modal)
        
    @discord.ui.button(label="Start", style=discord.ButtonStyle.primary)
    async def start_button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id != self.host:
            return await interaction.response.send_message("You are not the host", ephemeral=True)
        else:
            #await interaction.response.send_message("Starting game")
            #osu_ids = game_db.get_osu_ids_from_discord([player[0] for player in self.players if player[1]])
            #common_maps = game_db.get_common_maps(osu_ids)
            #common_sets = [mapset for _, mapset in common_maps]
            common_sets = game_db.get_all_sets()
            print(f"Starting game with {len(common_sets)} mapsets")
            
            game_view = GameView(set(self.players.keys()), common_sets, self.message)
            await game_view.next_round()
        
num_emojis = {-1: "🤷‍♂️", 0: "0️⃣",1: "1️⃣",2: "2️⃣",3: "3️⃣",4: "4️⃣",5: "5️⃣",6: "6️⃣",7: "7️⃣",8: "8️⃣",9: "9️⃣"}

def get_future_time(seconds: int):
    current_time = int(time.time())
    future_time = current_time + seconds
    discord_timestamp = f"<t:{future_time}:R>"
    return discord_timestamp

class GameView(discord.ui.View):
    def __init__(self, players: set[int], mapsets: list[int], message: discord.Message):
        super().__init__()
        self.players = players
        self.mapsets = mapsets
        self.message = message
        self.round = 1
        self.max_rounds = 10
        self.state = "getting_next_map"
        self.real_index = 0
        self.player_guesses = {} # {player_id: guess}
        self.player_points = {player_id: 0 for player_id in players}
    
    
    def get_embed(self, show_guesses=False, add_time=False):
        if show_guesses:
            
            
            if self.round >= self.max_rounds:
                max_points = max(self.player_points.values())
                display = "\n".join([f"<@{player}>: {points} {num_emojis[self.player_guesses.get(player, -2)+1]} {'👍' if self.player_guesses.get(player, -1) == self.real_index else ''} {'👑' if points == max_points else ''}" for player, points in self.player_points.items()])

            else:
                display = "\n".join([f"<@{player}>: {points} {num_emojis[self.player_guesses.get(player, -2)+1]} {'👍' if self.player_guesses.get(player, -1) == self.real_index else ''}" for player, points in self.player_points.items()])
        else:
            display = "\n".join([f"<@{player}>: {points}" for player, points in self.player_points.items()])
            
            
        title = "Game Over" if self.round >= self.max_rounds else f"Round {self.round}/{self.max_rounds}" if self.state == "getting_next_map" else "Showing Answers"
        
        if add_time:
            display = f"Guessing ends {get_future_time(30)}\n" + display
            
        embed = Embed(title=title, description=display)
        return embed
    
    
    async def next_round(self, update=True):
        
        if update:
            self.player_guesses = {}
            self.message.attachments.clear()
            await self.message.edit(embed=self.get_embed())
            
            
        round_sets = random.sample(self.mapsets, 6)
        
        for set_id in round_sets:
            self.mapsets.remove(set_id)
        
        real = round_sets.pop(0)
        try:
            img_grid_path, real_index = get_image_grid(round_sets, real, "cogs\osu_bg_guess")
        except Exception as e:
            print('failed to get image grid Retrying...')
            await self.next_round(update=False)
            return
        
        mp3, is_valid = get_preview(real, "cogs\osu_bg_guess")
        
        if not is_valid:
            print("Invalid mp3 retrying...")
            await self.next_round(update=False)
            return
        
        self.real_index = real_index
        
        self.image = discord.File(fp=img_grid_path, filename="bg_grid.png")
        self.preview = discord.File(fp="cogs\osu_bg_guess\preview.mp3", filename="REMEMBER_TO_turn_down_volume.mp3")
        
        for b in self.children:
            b.disabled = False
            b.style = discord.ButtonStyle.primary
        
        self.message.attachments.clear()
        upload_start = time.time()
        await self.message.edit(files=[self.image, self.preview], view=self, embed=self.get_embed(add_time=True))
        upload_end = time.time()
        
        self.state = "player_guesses"
        round = self.round
        await asyncio.sleep(30 - (upload_end - upload_start))
        if self.round == round:
            self.state = "showing_answers"
            await self.show_answers()
    
    async def player_guess(self, player_id, guess):
        
        if player_id not in self.players:
            self.players.add(player_id)
        
        self.player_guesses[player_id] = guess
        
        if len(self.player_guesses) == len(self.players):
            self.state = "showing_answers"
            await self.show_answers()
        
        return
            
    async def show_answers(self):
        correct = 0
        self.round += 1
        for player, guess in self.player_guesses.items():
            
            if player not in self.player_points:
                self.player_points[player] = 0
            
            if guess == self.real_index:
                correct += 1
                if player in self.player_points:
                    self.player_points[player] += 1
        
        for b in self.children:
            if b.label == str(self.real_index + 1):
                b.style = discord.ButtonStyle.success
            else:
                b.style = discord.ButtonStyle.danger
            b.disabled = True
            
        
        await self.message.edit(embed=self.get_embed(True), view=self)
        
        await asyncio.sleep(5)
        
        if self.round < self.max_rounds:
            await self.next_round()
        else:
            await self.end_game()
    
    
    def end_game(self):
        display = "\n".join([f"<@{player}>: {points}" for player, points in self.player_points.items()])
        embed = Embed(title="Game Over", description=display)
        self.message.edit(embed=embed, view=None)
        
            
    @discord.ui.button(label="1", style=discord.ButtonStyle.primary, row=1)
    async def button1_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.state == "player_guesses" and interaction.user.id not in self.player_guesses:
            await self.player_guess(interaction.user.id, 0)
            
    
    @discord.ui.button(label="2", style=discord.ButtonStyle.primary, row=1)
    async def button2_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.state == "player_guesses" and interaction.user.id not in self.player_guesses:
            await self.player_guess(interaction.user.id, 1)
        
    
    @discord.ui.button(label="3", style=discord.ButtonStyle.primary, row=1)
    async def button3_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.state == "player_guesses" and interaction.user.id not in self.player_guesses:
            await self.player_guess(interaction.user.id, 2)
    
    @discord.ui.button(label="4", style=discord.ButtonStyle.primary, row=2)
    async def button4_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.state == "player_guesses" and interaction.user.id not in self.player_guesses:
            await self.player_guess(interaction.user.id, 3)
    
    @discord.ui.button(label="5", style=discord.ButtonStyle.primary, row=2)
    async def button5_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.state == "player_guesses" and interaction.user.id not in self.player_guesses:
            await self.player_guess(interaction.user.id, 4)
    
    @discord.ui.button(label="6", style=discord.ButtonStyle.primary, row=2)
    async def button6_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.state == "player_guesses" and interaction.user.id not in self.player_guesses:
            await self.player_guess(interaction.user.id, 5)

        

def setup(bot: commands.Bot):
    bot.add_cog(MyCog(bot))