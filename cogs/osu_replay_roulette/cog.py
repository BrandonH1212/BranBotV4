import discord
from config import config
from discord.ext import commands
from discord import Option
from discord.commands import (
    slash_command,
)
from discord import Embed
import time, asyncio, os, json, random

class RRCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @slash_command(guild_ids=config.get_servers(), name="replay_roulette")
    async def replay_roulette(self, ctx: discord.ApplicationContext):
        view = SignUpView(self, ctx.author.id)
        await view.update_embed(ctx)

    
class SignUpView(discord.ui.View):
    def __init__(self, cog, host_id: int = None):
        super().__init__()
        self.cog = cog
        self.message = None
        self.host = host_id
        self.players = set()
    
    
    def get_embed(self):
        display = "\n".join([f"<@{player}>" for player in self.players])
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
            
            self.players.add(interaction.user.id)
            await self.update_embed(interaction)
    
        
    @discord.ui.button(label="Start", style=discord.ButtonStyle.primary)
    async def start_button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id != self.host:
            return await interaction.response.send_message("You are not the host", ephemeral=True)
        else:
            game_view = GameView(self.players, self.message)
            await game_view.next_round()

def get_future_time(seconds: int):
    current_time = int(time.time())
    future_time = current_time + seconds
    discord_timestamp = f"<t:{future_time}:R>"
    return discord_timestamp

def simplify_number(number: int):
    if number >= 1000000:
        return f"{round(number/1000000, 2)}M"
    elif number >= 1000:
        return f"{round(number/1000, 2)}K"
    else:
        return number
    
def number_from_string(number: str):
    try:
        number = number.lower().strip()
        number = number.replace(",", "").replace(" ", "").replace("_", "")
        
        multiplier = 1
        if number.endswith('k'):
            multiplier = 1000
            number = number[:-1]
        elif number.endswith('m'):
            multiplier = 1000000
            number = number[:-1]
        
        if '.' in number:
            return int(float(number) * multiplier)
        else:
            return int(number) * multiplier
    except:
        return None
    
class GameView(discord.ui.View):
    def __init__(self, players: set[int], message: discord.Message):
        super().__init__()
        self.players = players
        self.message = message
        self.round = 1
        self.state = "getting_next_map"
        self.real_rank = 0
        self.starting_hp = 100_000
        self.player_guesses = {} # {player_id: guess}
        self.player_eliminated_round = {} # {player_id: round}
        self.player_hp = {player_id: self.starting_hp for player_id in players}
        self.current_video = None
    
        self.videos_info = self.get_videos_info()
        
        
    def get_videos_info(self):
        video_directory = "cogs/osu_replay_roulette/videos"
        
        video_files = os.listdir(video_directory)
        video_files = [video for video in video_files if video.endswith(".mp4")]
        
        video_info = []
        
        for video in video_files:
            rank = int(video.split("/")[-1].split(".mp4")[0])
            json_metadata = f"{video_directory}/{video.split('.')[0]}.json"
            with open(json_metadata, "r") as f:
                metadata = json.load(f)
                
            video_info.append({"path": f"{video_directory}/{video}",
                                      'rank': rank,
                                      'map_id': metadata["map_id"],
                                      'player_id': metadata["player_id"]})
        random.shuffle(video_info)
        
        return video_info
    
    
    @discord.ui.button(label="Guess", style=discord.ButtonStyle.primary)
    async def register_button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        modal = GuessModal(game=self, title="Formatting 1000 1k 1_000 1,000")
        await interaction.response.send_modal(modal)
        
    
    def get_embed(self, show_guesses=False, add_time=False):
        if show_guesses:
            pass
        
        title = 'Guess the rank!'
        
        display = ""
        if add_time:
            display += f"Guessing ends {get_future_time(self.guess_time)}\n" + display
            
        if show_guesses:
            display += f"***Real rank:*** `{simplify_number(self.real_rank)}`\n"
            display += f'player(https://osu.ppy.sh/users/{self.current_video["player_id"]})\n'
            title = 'Uploading the next video...'
        
        player_hp = {player: hp for player, hp in self.player_hp.items()}
        display += "\n\n".join([f"<@{player}> HP:{simplify_number(hp)} {f'- `{simplify_number(abs(self.player_guesses.get(player, 0) - self.real_rank))}` *Guessed* `{simplify_number(self.player_guesses.get(player, 0))}`' if show_guesses else 0}" for player, hp in player_hp.items() if hp > 0])
        display += f"\n".join([f"<@{player}> :skull: eliminated round {self.player_eliminated_round.get(player, None)}" for player, hp in player_hp.items() if hp <= 0])
            
        embed = Embed(title=title, description=display)
        return embed
    
    
    async def next_round(self, update=True):
        self.current_video = self.videos_info.pop(0)
        self.real_rank = self.current_video["rank"]
        self.round_start = time.time()
        self.state = "getting_guesses"
        
        discord_video = discord.File(self.current_video["path"],filename="video.mp4")
        
        self.message.attachments.clear()
        await self.message.edit(embed=self.get_embed(), view=self, file=discord_video)
        
    
    async def player_guess(self, player_id, guess):
        
        if player_id not in self.players:
            self.players.add(player_id)
        
        self.player_guesses[player_id] = guess
        
        if len(self.player_guesses) == len(self.players) - len(self.player_eliminated_round):
            self.state = "showing_answers"
            await self.show_answers()
        
        return
            
    async def show_answers(self):
        self.round += 1
        for player in self.players:
            
            if player not in self.player_hp:
                self.player_hp[player] = self.starting_hp / self.round
            
            if player in self.player_hp:
                self.player_hp[player] -= abs(self.player_guesses.get(player,0) - self.real_rank)
                
                if self.player_hp[player] <= 0:
                    self.player_eliminated_round[player] = self.round -1
                    
        if len(self.player_eliminated_round) == len(self.players):
            self.end_game()
            return
        
        await self.message.edit(embed=self.get_embed(show_guesses=True), view=self)
        await asyncio.sleep(6)
        await self.next_round()

    
    
    def end_game(self):
        self.message.edit(embed=self.get_embed(), view=None)
        

class GuessModal(discord.ui.Modal):
    def __init__(self, game, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.InputText(label="Input"))
        self.gameview = game

    async def callback(self, interaction: discord.Interaction):
        
        user_input = self.children[0].value
        
        guess = number_from_string(user_input)
        
        if not guess:
            await interaction.response.send_message(f"""Gave invalid input: {user_input}
                                                    You can use any number formatted in the following ways
                                                    `10000` `10k` `10_00` `10,00`
                                                    `1000000` `1m` `1_000_000` `1,000,000`""", ephemeral=True)
            return
        await interaction.response.send_message(f"Your guess: `{guess}`", ephemeral=True, delete_after=5)
        await self.gameview.player_guess(interaction.user.id, guess)
        
        





def setup(bot: commands.Bot):
    bot.add_cog(RRCog(bot))
