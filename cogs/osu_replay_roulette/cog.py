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
from .utilities import get_future_time, simplify_number, number_from_string


class RRCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @slash_command(guild_ids=config.get_servers(), name="replay_roulette")
    async def replay_roulette(self, ctx: discord.ApplicationContext) -> None:
        view: SignUpView = SignUpView(self, ctx.author.id)
        view.players.add(ctx.author.id)
        await view.update_embed(ctx)

class SignUpView(discord.ui.View):
    def __init__(self, cog: RRCog, host_id: Optional[int] = None):
        super().__init__()
        self.cog: RRCog = cog
        self.message: Optional[discord.Message] = None
        self.host: Optional[int] = host_id
        self.players: Set[int] = set()
    
    def get_embed(self, starting: bool = False) -> Embed:
        if starting:
            title = "🎥 Replay Roulette - Game Starting!"
            color = discord.Color.green()
        else:
            title = "🎥 Replay Roulette - Sign Up"
            color = discord.Color.blue()

        embed = Embed(title=title, color=color)
        
        player_list = "\n".join([f"<@{player}>" for player in self.players]) or "No players yet"
        embed.add_field(name=f"👥 Players ({len(self.players)})", value=player_list, inline=False)
        
        embed.set_footer(text="Click 'Join' to participate | Host can click 'Start' when ready")
        
        return embed

    async def update_embed(self, ctx: discord.ApplicationContext) -> None:
        embed: Embed = self.get_embed()
        if self.message:
            await self.message.edit(embed=embed, view=self)
            await ctx.response.defer()
        else:
            await ctx.response.send_message(embed=embed, view=self)
            self.message = await ctx.interaction.original_response()
    
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
            await interaction.response.edit_message(embed=self.get_embed(starting=True), view=None)
            game_view: GameView = GameView(self.players, self.message)
            await game_view.next_round()
            
    @discord.ui.button(label="📝 How to Play", style=ButtonStyle.gray)
    async def rules_button_callback(self, button: discord.ui.Button, interaction: Interaction) -> None:
        embed = Embed(title="Rules", color=discord.Color.dark_gray())
        embed.add_field(name="📝 How to Play", value=(
            "1. Watch a osu! clip\n"
            "2. Guess the player's rank\n"
            "3. You take more damage the further your guess is\n"
            "4. Last player standing wins!"
        ), inline=False)
        
        embed.add_field(name="🔢 Game Rules", value=(
            "• All players start with 10,000 HP\n"
            "• Damage = sqrt(round_num) * 1000) * |log2(guess) - log2(real_rank)|\n"
            "• Players are eliminated when HP reaches 0\n"
            "• The game ends when only one player remains"
        ), inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

class Player:
    def __init__(self, id: int, starting_hp: int):
        self.id: int = id
        self.hp: int = starting_hp
        self.guess: Optional[int] = None
        self.eliminated_round: Optional[int] = None

    def make_guess(self, guess: int) -> None:
        self.guess = guess

    def get_damage(self, real_rank: int, round:int) -> int:
        return int(abs(math.log(self.guess or 1, 2) - math.log(real_rank, 2)) * (1000 * math.sqrt(round)))
    
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
        self.previous_video: Optional[Dict[str, Any]] = None
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
                "mapset_id": metadata["mapset_id"],
                "player_id": metadata["player_id"],
                "score_id": metadata["score_id"]
            })
        random.shuffle(video_info)
        
        return video_info
        
    @discord.ui.button(label="Guess", style=ButtonStyle.primary)
    async def register_button_callback(self, button: discord.ui.Button, interaction: Interaction) -> None:
        modal: GuessModal = GuessModal(game=self)
        await interaction.response.send_modal(modal)
    
    def get_embed(self, show_guesses: bool = False, add_time: bool = False, game_over: bool = False) -> Embed:
        if game_over:
            title = '🏁 Game Over!'
            color = discord.Color.gold()
        elif show_guesses:
            title = '🎥 Results & Next Round'
            color = discord.Color.orange()
            self.children[0].disabled = True
        else:
            self.children[0].disabled = False
            title = '🤔 Guess the Rank!'
            color = discord.Color.blue()

        embed = Embed(title=title, color=color)
        
        # Round information
        embed.add_field(name="Round Info", value=f"Round: {self.round}", inline=False)
        
        if add_time:
            embed.add_field(name="⏳ Time Remaining", value=f"Guessing ends {get_future_time(self.guess_time)}", inline=False)
        
        if show_guesses or game_over:
            current_round_info = (
                f"🎯 Actual Rank: `{simplify_number(self.real_rank)}`\n"
                f"👤 Player: [Profile](https://osu.ppy.sh/users/{self.current_video['player_id']})\n"
                f"🗺️ Map: [Beatmap](https://osu.ppy.sh/b/{self.current_video['map_id']})\n"
                f"🏆 Score: [Link](https://osu.ppy.sh/scores/osu/{self.current_video['score_id']})"
            )
            embed.add_field(name="📊 Current Round Results", value=current_round_info, inline=False)
    
        # Active players
        active_players = []
        
        alive_players = self.alive_players
        
        if len(alive_players) > 0:
            lowest_damage = min(player.get_damage(self.real_rank, self.round) for player in alive_players)
        else:
            lowest_damage = 0

        self.players.sort(key=lambda p: p.hp, reverse=True)
        
        for player in self.players:
            if not player.is_eliminated():
                player_info = f"<@{player.id}> | HP: `{simplify_number(player.hp)}`"
                if show_guesses or game_over:
                    damage = player.get_damage(self.real_rank, self.round)
                    player_info += f' | Damage: `{simplify_number(damage)}` | Guessed: `{simplify_number(player.guess or 1)}`'
                    
                    if damage == lowest_damage:
                        player_info += f" 👑"
                    
                active_players.append(player_info)
            
        if active_players:
            embed.add_field(name="Active Players", value="\n".join(active_players), inline=False)
        
        # Eliminated players
        eliminated_players = []
        for player in self.players:
            if player.is_eliminated():
                player_info = f"<@{player.id}> | Eliminated: Round {player.eliminated_round}"
                if player.guess is not None:
                    player_info += f" | HP: `{simplify_number(player.hp)}` | Last Guess: `{simplify_number(player.guess)}`"
                eliminated_players.append(player_info)
        
        if eliminated_players:
            embed.add_field(name="💀 Eliminated Players", value="\n".join(eliminated_players), inline=False)
        
        if self.previous_video and not show_guesses or game_over:
            prev_round_info = (
                f"[Player](https://osu.ppy.sh/users/{self.previous_video['player_id']}) -"
                f" [Beatmap](https://osu.ppy.sh/b/{self.previous_video['map_id']}) -"
                f" [Score](https://osu.ppy.sh/scores/osu/{self.previous_video['score_id']})"
            )
            embed.add_field(name="Previous Round", value=prev_round_info, inline=False)

        # Footer
        if not game_over:
            if show_guesses:
                embed.set_footer(text="Next round starting soon...")
            else:
                embed.set_footer(text="Click 'Guess' to submit your rank guess!")
        else:
            embed.set_footer(text="Thanks for playing!")
        
        return embed


    async def next_round(self, update: bool = True) -> None:
        # Set the previous video before moving to the next one
        self.previous_video = self.current_video

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
                damage = player.get_damage(self.real_rank, self.round)
                player.take_damage(damage)
                
                if player.is_eliminated():
                    player.eliminate(self.round)
                    
        if len(self.alive_players) < 1:
            await self.end_game()
            return
        
        # If someone's playing solo We don't want to end the game early
        elif len(self.players) > 1 and len(self.alive_players) == 1:
            await self.end_game()
            return
        
        await self.message.edit(embed=self.get_embed(show_guesses=True), view=self)
        await asyncio.sleep(12)
        self.round += 1
        await self.next_round()

    async def end_game(self) -> None:
        await self.message.edit(embed=self.get_embed(game_over=True), view=None)

class GuessModal(discord.ui.Modal):
    def __init__(self, game: GameView, *args, **kwargs) -> None:
        current_round_info = f"Round {game.round}"
        super().__init__(*args, title=f"Guess the Rank - {current_round_info}", **kwargs)
        self.gameview: GameView = game
        
        self.add_item(discord.ui.InputText(
            label="Your Guess (Max rank is 300k)",
            placeholder="10000, 10_000, 10k",
            min_length=1,
            max_length=10
        ))
        
        formatting_explanation = (
            "• Use numbers: 10000, 100000, 1000000\n"
            "• Use k for thousands: 10k = 10,000\n"
            "• Spaces and commas are optional"
        )
        self.add_item(discord.ui.InputText(
            label="Formatting Help",
            value=formatting_explanation,
            style=discord.InputTextStyle.long,
            required=False
        ))

    async def callback(self, interaction: Interaction) -> None:
        user_input: str = self.children[0].value
        
        guess: Optional[int] = number_from_string(user_input)
        
        if not guess:
            error_message = (
                "Invalid input! Here are some valid examples:\n"
                "• Numbers: 10000, 100000, 1000000\n"
                "• With k: 10k, 100k, 999k\n"
                "• With spaces/commas: 10,000 or 10 000\n"
                f"You entered: {user_input}"
            )
            await interaction.response.send_message(error_message, ephemeral=True)
            return

        await interaction.response.send_message(f"Your guess: `{guess}`", ephemeral=True, delete_after=5)
        await self.gameview.player_guess(interaction.user.id, guess)
        
        
        
def setup(bot: commands.Bot) -> None:
    bot.add_cog(RRCog(bot))