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
    
    def get_embed(self) -> Embed:
        display: str = "\n".join([f"<@{player}>" for player in self.players])
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
    
class GameView(discord.ui.View):
    def __init__(self, players: Set[int], message: discord.Message):
        super().__init__()
        self.players: Set[int] = players
        self.message: discord.Message = message
        self.round: int = 1
        self.state: str = "getting_next_map"
        self.real_rank: int = 0
        self.starting_hp: int = 10_000
        self.player_guesses: Dict[int, int] = {}
        self.player_eliminated_round: Dict[int, int] = {}
        self.player_hp: Dict[int, int] = {player_id: self.starting_hp for player_id in players}
        self.current_video: Optional[Dict[str, Any]] = None
    
        self.videos_info: List[Dict[str, Any]] = self.get_videos_info()
        
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
    
    def get_embed(self, show_guesses: bool = False, add_time: bool = False) -> Embed:
        title: str = 'Guess the rank!'
        
        display: str = ""
        if add_time:
            display += f"Guessing ends {get_future_time(self.guess_time)}\n" + display
            
        if show_guesses:
            display += f"***Real rank:*** `{simplify_number(self.real_rank)}`\n"
            display += f'player(https://osu.ppy.sh/users/{self.current_video["player_id"]})\n'
            display += f'map {self.current_video["map_id"]}\n'
            title = 'Uploading the next video...'
        
        player_hp: Dict[int, int] = {player: hp for player, hp in self.player_hp.items()}
        display += "\n\n".join([
            f"<@{player}> HP:{simplify_number(hp)} {f'- `{simplify_number(abs(math.log(self.player_guesses.get(player, 1), 2) - math.log(self.real_rank, 2)) * 1000)}` *Guessed* `{simplify_number(self.player_guesses.get(player, 0))}`' if show_guesses else ''}" 
            for player, hp in player_hp.items() if hp > 0
        ])
        display += "\n\n" + "\n".join([
            f"<@{player}> :skull: eliminated round {self.player_eliminated_round.get(player, None)}" 
            for player, hp in player_hp.items() if hp <= 0
        ])
            
        embed: Embed = Embed(title=title, description=display)
        return embed
    
    async def next_round(self, update: bool = True) -> None:
        self.current_video = self.videos_info.pop(0)
        self.real_rank = self.current_video["rank"]
        self.round_start: float = time.time()
        self.state = "getting_guesses"
        
        discord_video: File = File(self.current_video["path"], filename="video.mp4")
        self.player_guesses.clear()
        self.message.attachments.clear()
        await self.message.edit(embed=self.get_embed(), view=self, file=discord_video)
    
    async def player_guess(self, player_id: int, guess: int) -> None:
        if player_id in self.player_eliminated_round:
            return
        
        if player_id not in self.players:
            self.players.add(player_id)
        
        self.player_guesses[player_id] = guess
        
        if len(self.player_guesses) >= len(self.players) - len(self.player_eliminated_round):
            self.state = "showing_answers"
            await self.show_answers()
        
    async def show_answers(self) -> None:
        self.round += 1
        for player in self.players:
            if player not in self.player_hp:
                self.player_hp[player] = self.starting_hp // self.round
            
            if player in self.player_hp:
                self.player_hp[player] -= int(abs(math.log(self.player_guesses.get(player, 1), 2) - math.log(self.real_rank, 2)) * 1000)
                
                if self.player_hp[player] <= 0 and player not in self.player_eliminated_round:
                    self.player_eliminated_round[player] = self.round - 1
                    
        if len(self.player_eliminated_round) == len(self.players):
            await self.end_game()
            return
        
        await self.message.edit(embed=self.get_embed(show_guesses=True), view=self)
        await asyncio.sleep(12)
        await self.next_round()

    async def end_game(self) -> None:
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