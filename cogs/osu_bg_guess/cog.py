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

from . import game_db, BgGameDatabase, get_image_grid, get_preview

class MyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @slash_command(guild_ids=config.get_servers(cog_name='osu_bg_guess'), name="bg_game")
    async def bg_game(self, ctx: ApplicationContext):
        view = SignUpView(self, ctx.author.id)
        await view.update_embed(ctx)

class RegisterModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.InputText(label="Input"))

    async def callback(self, interaction: Interaction):
        user_input: str = self.children[0].value
        
        user = await get_osu_user(user_input)
        
        if not user:
            await interaction.response.send_message(f"User not found {user_input} Try again with just the ID", ephemeral=True)
            return
        
        game_db.add_user(interaction.user.id, user.id)
        
        await interaction.response.send_message(f"User found: {user.username} ({user.id}) registered\nhttps://osu.ppy.sh/users/{user.id}\nIf this is a mistake register with another name", ephemeral=True)
        await self.add_user_maps(user)

    async def add_user_maps(self, user):
        api = get_osu_api()
        user_beatmaps: List = []
        
        print(f"Adding maps for {user.username}")
        
        for i in range(0, (user.beatmap_playcounts_count) // 100):
            user_beatmaps += await api.user_beatmaps(user.id, limit=100, type="most_played", offset=i*100)
            
        map_ids: List[Tuple[int, int]] = [(beatmap.beatmap_id, beatmap.beatmapset.id) for beatmap in user_beatmaps]

        game_db.add_play_history_batch([(user.id, beatmap.beatmapset.id) for beatmap in user_beatmaps])
        
        print(f"Added {len(map_ids)} maps to the database")

class SignUpView(discord.ui.View):
    def __init__(self, cog: MyCog, host_id: Optional[int] = None):
        super().__init__()
        self.cog: MyCog = cog
        self.message: Optional[Message] = None
        self.host: Optional[int] = host_id
        self.players: Dict[int, bool] = {host_id: True} if host_id else {}
    
    def get_embed(self) -> Embed:
        display: str = "\n".join([f"<@{player}>: {'✅' if self.players[player] else '❌'}" for player in self.players])
        embed = Embed(title="Sign up for the game", description=display)
        return embed

    async def update_embed(self, ctx: ApplicationContext):
        embed: Embed = self.get_embed()
        if self.message:
            await self.message.edit(embed=embed, view=self)
            await ctx.response.defer()
        elif ctx:
            await ctx.response.send_message(embed=embed, view=self)
            self.message = ctx.message
    
    @discord.ui.button(label="Join", style=discord.ButtonStyle.green, custom_id="join_button")
    async def join_button_callback(self, button: discord.ui.Button, interaction: Interaction):
        if interaction.user.id in self.players:
            await interaction.response.send_message("You are already signed up", ephemeral=True)
        else:
            db_user = game_db.get_user(interaction.user.id)
            
            self.players[interaction.user.id] = db_user is not None
            await self.update_embed(interaction)
    
    @discord.ui.button(label="Register", style=discord.ButtonStyle.primary)
    async def register_button_callback(self, button: discord.ui.Button, interaction: Interaction):
        modal = RegisterModal(title="Enter your osu username or user id")
        await interaction.response.send_modal(modal)
        
    @discord.ui.button(label="Start", style=discord.ButtonStyle.primary)
    async def start_button_callback(self, button: discord.ui.Button, interaction: Interaction):
        if interaction.user.id != self.host:
            await interaction.response.send_message("You are not the host", ephemeral=True)
        else:
            common_sets: List[int] = game_db.get_all_sets()
            
            print(f"Starting game with {len(common_sets)} mapsets")
            
            game_view = GameView(set(self.players.keys()), common_sets, self.message)
            await game_view.next_round()

num_emojis: Dict[int, str] = {-1: "🤷‍♂️", 0: "0️⃣", 1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣", 9: "9️⃣"}

def get_future_time(seconds: int) -> str:
    current_time: int = int(time.time())
    future_time: int = current_time + seconds
    discord_timestamp: str = f"<t:{future_time}:R>"
    return discord_timestamp

class GameView(discord.ui.View):
    def __init__(self, players: Set[int], mapsets: List[int], message: Message):
        super().__init__()
        self.players: Set[int] = players
        self.mapsets: List[int] = mapsets
        self.message: Message = message
        self.round: int = 0
        self.max_rounds: int = 10
        self.state: str = "getting_next_map"
        self.real_index: int = 0
        self.player_guesses: Dict[int, int] = {}
        self.player_guess_times: Dict[int, float] = {}
        self.player_points: Dict[int, float] = {player_id: 0 for player_id in players}
        self.create_buttons()
        self.round_start: float = time.time()
        self.guess_time: int = 30
        self.time_bonus: float = 0.25

    async def button_callback(self, interaction: Interaction):
        await interaction.response.defer()
        guess: int = int(interaction.data['custom_id'])
        await self.player_guess(interaction.user.id, guess)
            
    def create_buttons(self):
        for i in range(6):
            button = discord.ui.Button(label=str(i + 1), style=discord.ButtonStyle.primary, row=i // 3, custom_id=str(i))
            button.callback = self.button_callback
            self.add_item(button)
    
    def get_embed(self, show_guesses: bool = False, add_time: bool = False) -> Embed:
        if show_guesses:
            if self.round >= self.max_rounds:
                max_points: float = max(self.player_points.values())
                display: str = "\n".join([f"<@{player}>: {points:.2f} {num_emojis[self.player_guesses.get(player, -2)+1]} {f'👍 +{round(1 + (self.guess_time - round(self.player_guess_times[player] - self.round_start,3))*self.time_bonus/self.guess_time, 2)}' if self.player_guesses.get(player, -1) == self.real_index else ''} {'👑' if points == max_points else ''}" for player, points in self.player_points.items()])
            else:
                display: str = "\n".join([f"<@{player}>: {points:.2f} {num_emojis[self.player_guesses.get(player, -2)+1]} {f'👍 +{round(1 + (self.guess_time - round(self.player_guess_times[player] - self.round_start,3))*self.time_bonus/self.guess_time, 2)}' if self.player_guesses.get(player, -1) == self.real_index else ''}" for player, points in self.player_points.items()])
        else:
            display: str = "\n".join([f"<@{player}>: {points:.2f}" for player, points in self.player_points.items()])
            
        title: str = "Game Over" if self.round >= self.max_rounds else f"Round {self.round}/{self.max_rounds}" if self.state == "getting_next_map" else "Showing Answers"
        
        if add_time:
            display = f"Guessing ends {get_future_time(self.guess_time)}\n" + display
            
        embed: Embed = Embed(title=title, description=display)
        return embed
    
    async def next_round(self, update: bool = True):
        if update:
            self.player_guesses = {}
            self.message.attachments.clear()
            await self.message.edit(embed=self.get_embed())
            
        round_sets: List[int] = random.sample(self.mapsets, 6)
        
        for set_id in round_sets:
            self.mapsets.remove(set_id)
        
        real: int = round_sets.pop(0)
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
        
        self.image: File = discord.File(fp=img_grid_path, filename="bg_grid.png")
        self.preview: File = discord.File(fp="cogs\osu_bg_guess\preview.mp3", filename="REMEMBER_TO_turn_down_volume.mp3")
        
        for b in self.children:
            b.disabled = False
            b.style = discord.ButtonStyle.primary
        
        self.message.attachments.clear()
        upload_start: float = time.time()
        await self.message.edit(files=[self.image, self.preview], view=self, embed=self.get_embed(add_time=True))
        upload_end: float = time.time()
        
        self.state = "player_guesses"
        round: int = self.round
        r_time: float = (self.guess_time - (upload_end - upload_start)) + self.time_bonus
        self.round_start = time.time()
        await asyncio.sleep(r_time)
        if self.round == round:
            self.state = "showing_answers"
            await self.show_answers()
    
    async def player_guess(self, player_id: int, guess: int):
        if player_id not in self.players:
            self.players.add(player_id)
        
        self.player_guesses[player_id] = guess
        self.player_guess_times[player_id] = time.time()
        
        if len(self.player_guesses) == len(self.players):
            self.state = "showing_answers"
            await self.show_answers()
        
        return
            
    async def show_answers(self):
        self.round += 1
        for player, guess in self.player_guesses.items():
            if player not in self.player_points:
                self.player_points[player] = 0
            
            if guess == self.real_index:
                if player in self.player_points:
                    self.player_points[player] += round(1 + (self.guess_time - round(self.player_guess_times[player] - self.round_start,3))*self.time_bonus/self.guess_time, 2)
        
        for b in self.children:
            if b.label == str(self.real_index + 1):
                b.style = discord.ButtonStyle.success
            else:
                b.style = discord.ButtonStyle.danger
            b.disabled = True
        
        await self.message.edit(embed=self.get_embed(show_guesses=True), view=self)
        
        await asyncio.sleep(4)
        
        if self.round < self.max_rounds:
            await self.next_round()
        else:
            await self.end_game()
    
    def end_game(self):
        self.message.edit(embed=self.get_embed(), view=None)

def setup(bot: commands.Bot):
    bot.add_cog(MyCog(bot))