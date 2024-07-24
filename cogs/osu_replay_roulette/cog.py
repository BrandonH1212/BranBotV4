import discord
from config import config
from discord.ext import commands
from discord import Option, Embed, File, ButtonStyle, Interaction
from discord.commands import slash_command
import time
import asyncio
import os
import json
import random
import math
from typing import Set, Dict, List, Optional, Any


class RRCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @slash_command(guild_ids=config.get_servers(), name="replay_roulette")
    async def replay_roulette(self, ctx: discord.ApplicationContext) -> None:
        view: SignUpView = SignUpView(self, ctx.author.id)
        await view.update_embed(ctx)

class SignUpView(discord.ui.View):
    def __init__(self, cog: RRCog, host_id: Optional[int] = None):
        super().__init__()
        self.cog: RRCog = cog
        self.message: Optional[discord.Message] = None
        self.host: Optional[int] = host_id
        self.players: Set[int] = set()
    
    def get_embed(self, starting:bool=False) -> Embed:
        display: str = "\n".join([f"<@{player}>" for player in self.players])
        
        if starting:
            embed: Embed = Embed(title="Game starting...", description=display)
        else:
            embed: Embed = Embed(title="Sign up for the game", description=display)
        return embed

    async def update_embed(self, ctx: discord.ApplicationContext) -> None:
        embed: Embed = self.get_embed()
        if self.message:
            await self.message.edit(embed=embed, view=self)
            await ctx.response.defer()
        elif ctx:
            await ctx.response.send_message(embed=embed, view=self)
            self.message = ctx.message
    
    @discord.ui.button(label="Join", style=ButtonStyle.green, custom_id="join_button")
    async def join_button_callback(self, button: discord.ui.Button, interaction: Interaction) -> None:
        if interaction.user.id in self.players:
            await interaction.response.send_message("You are already signed up", ephemeral=True)
        else:
            self.players.add(interaction.user.id)
            await self.update_embed(interaction)
    
    @discord.ui.button(label="Start", style=ButtonStyle.primary)
    async def start_button_callback(self, button: discord.ui.Button, interaction: Interaction) -> None:
        if interaction.user.id != self.host:
            await interaction.response.send_message("You are not the host", ephemeral=True)
        else:
            await interaction.response.edit_message(embed=self.get_embed(), view=None)
            
            
            game_view: GameView = GameView(self.players, self.message)
            await game_view.next_round()

def get_future_time(seconds: int) -> str:
    current_time: int = int(time.time())
    future_time: int = current_time + seconds
    discord_timestamp: str = f"<t:{future_time}:R>"
    return discord_timestamp

def simplify_number(number: int) -> str:
    if number >= 1000000:
        return f"{round(number/1000000, 2)}M"
    elif number >= 1000:
        return f"{round(number/1000, 2)}K"
    else:
        return str(number)
    
def number_from_string(number: str) -> Optional[int]:
    try:
        number = number.lower().strip()
        number = number.replace(",", "").replace(" ", "").replace("_", "")
        
        multiplier: int = 1
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

class Player:
    def __init__(self, id: int, starting_hp: int):
        self.id: int = id
        self.hp: int = starting_hp
        self.guess: Optional[int] = None
        self.eliminated_round: Optional[int] = None

    def make_guess(self, guess: int) -> None:
        self.guess = guess

    def get_damage(self, real_rank: int) -> int:
        return int(abs(math.log(self.guess or 1, 2) - math.log(real_rank, 2)) * 1000)
    
    def take_damage(self, damage: int) -> None:
        self.hp -= damage

    def eliminate(self, round: int) -> None:
        self.eliminated_round = round

    def is_eliminated(self) -> bool:
        return self.hp <= 0

    def reset_guess(self) -> None:
        self.guess = None



class GameView(discord.ui.View):
    def __init__(self, player_ids: Set[int], message: discord.Message):
        super().__init__()
        self.message: discord.Message = message
        self.round: int = 1
        self.state: str = "getting_next_map"
        self.real_rank: int = 0
        self.starting_hp: int = 10_000
        self.players: List[Player] = [Player(player_id, self.starting_hp) for player_id in player_ids]
        self.current_video: Optional[Dict[str, Any]] = None
    
        self.videos_info: List[Dict[str, Any]] = self.get_videos_info()
    
    
    @property
    def alive_players(self) -> List[Player]:
        return [player for player in self.players if not player.is_eliminated()]
    
    def get_videos_info(self) -> List[Dict[str, Any]]:
        video_directory: str = "cogs/osu_replay_roulette/videos"
        
        video_files: List[str] = [video for video in os.listdir(video_directory) if video.endswith(".mp4")]
        
        video_info: List[Dict[str, Any]] = []
        
        for video in video_files:
            rank: int = int(video.split("/")[-1].split(".mp4")[0])
            json_metadata: str = f"{video_directory}/{video.split('.')[0]}.json"
            with open(json_metadata, "r") as f:
                metadata: Dict[str, Any] = json.load(f)
                
            video_info.append({
                "path": f"{video_directory}/{video}",
                "rank": rank,
                "map_id": metadata["map_id"],
                "player_id": metadata["player_id"]
            })
        random.shuffle(video_info)
        
        return video_info
    
    @discord.ui.button(label="Guess", style=ButtonStyle.primary)
    async def register_button_callback(self, button: discord.ui.Button, interaction: Interaction) -> None:
        modal: GuessModal = GuessModal(game=self, title="Formatting 1000 1k 1_000 1,000")
        await interaction.response.send_modal(modal)
    
    def get_embed(self, show_guesses: bool = False, add_time: bool = False, game_over: bool = False) -> Embed:
        if show_guesses:
            title = 'Uploading the next video...'
        else:
            title = 'Guess the rank!'
        
        if game_over:
            title = 'Game Over!'
            
        
        display = []
        
        if add_time:
            display.append(f"Guessing ends {get_future_time(self.guess_time)}")
        
        if show_guesses:
            display.append(f"***Real rank:*** `{simplify_number(self.real_rank)}`")
            display.append(f'player(https://osu.ppy.sh/users/{self.current_video["player_id"]})')
            display.append(f'map {self.current_video["map_id"]}')
        
        active_players = []
        eliminated_players = []
        
        for player in self.players:
            if not player.is_eliminated():
                player_info = f"<@{player.id}> HP:{simplify_number(player.hp)}"
                if show_guesses:
                    guess_diff = player.get_damage(self.real_rank)
                    player_info += f' - `{simplify_number(guess_diff)}` *Guessed* `{simplify_number(player.guess or 1)}`'
                if game_over:
                    player_info += f" 👑"
                
                active_players.append(player_info)
            else:
                eliminated_players.append(f"<@{player.id}> :skull: eliminated round {player.eliminated_round}" + (f" - Guessed `{simplify_number(player.guess)}`" if player.guess is not None else ""))
        
        if active_players:
            display.append("\n".join(active_players))
        
        if eliminated_players:
            display.append("\n".join(eliminated_players))
        
        description = "\n\n".join(display)
        
        return Embed(title=title, description=description)


    async def next_round(self, update: bool = True) -> None:
        
        # delete the old video
        if self.current_video:
            os.remove(self.current_video["path"])
            os.remove(f"{self.current_video['path'].split('.')[0]}.json")
        
        self.current_video = self.videos_info.pop(0)
        self.real_rank = self.current_video["rank"]
        self.round_start: float = time.time()
        self.state = "getting_guesses"
        
        discord_video: File = File(self.current_video["path"], filename="video.mp4")
        
        for player in self.players:
            player.reset_guess()
            
        self.message.attachments.clear()
        
        await self.message.edit(embed=self.get_embed(), view=self, file=discord_video)
    
    async def player_guess(self, player_id: int, guess: int) -> None:
        
        player = next((p for p in self.players if p.id == player_id), Player(player_id, self.starting_hp/self.round))
        
        if player.is_eliminated():
            return
        
        player.make_guess(guess)
        
        if all(p.guess is not None or p.is_eliminated() for p in self.players):
            self.state = "showing_answers"
            await self.show_answers()
        
    async def show_answers(self) -> None:
        for player in self.players:
            if not player.is_eliminated():
                damage = player.get_damage(self.real_rank)
                player.take_damage(damage)
                
                if player.is_eliminated():
                    player.eliminate(self.round)
                    
        if len(self.players) < 1:
            await self.end_game()
            return
        
        elif len(self.players) > 1 and len(self.alive_players) == 1:
            await self.end_game(winner=self.alive_players[0])
            return
        
        await self.message.edit(embed=self.get_embed(show_guesses=True), view=self)
        await asyncio.sleep(12)
        self.round += 1
        await self.next_round()

    async def end_game(self, winner: Optional[Player] = None) -> None:
        await self.message.edit(embed=self.get_embed(), view=None)

class GuessModal(discord.ui.Modal):
    def __init__(self, game: GameView, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.InputText(label="Input"))
        self.gameview: GameView = game

    async def callback(self, interaction: Interaction) -> None:
        user_input: str = self.children[0].value
        
        guess: Optional[int] = number_from_string(user_input)
        
        if not guess:
            await interaction.response.send_message(
                f"""Gave invalid input: {user_input}
                You can use any number formatted in the following ways
                `10000` `10k` `10_00` `10,00`
                `1000000` `1m` `1_000_000` `1,000,000`""", 
                ephemeral=True
            )
            return
        await interaction.response.send_message(f"Your guess: `{guess}`", ephemeral=True, delete_after=5)
        await self.gameview.player_guess(interaction.user.id, guess)

def setup(bot: commands.Bot) -> None:
    bot.add_cog(RRCog(bot))