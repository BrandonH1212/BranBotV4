import discord, os
from discord.ext import commands
from config import config



class Bot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = config

    def load_cogs(self):
        print("Loading cogs...")
        cog_files = os.listdir("./cogs")
        cog_folders = [cog for cog in cog_files if os.path.isdir(f"./cogs/{cog}")]
        
        for cog in cog_files:
            if cog.endswith(".py"):
                try:
                    self.load_extension(f"cogs.{cog[:-3]}")
                    print(f"Loaded {cog}")
                except Exception as e:
                    print(f"Failed to load {cog}: {e}")
        
        for folder in cog_folders:
            if os.path.exists(f"./cogs/{folder}/cog.py"):
                try:
                    self.load_extension(f"cogs.{folder}.cog")
                    print(f"Loaded {folder}")
                except Exception as e:
                    print(f"Failed to load {folder}: {e}")

try:
    if __name__ == "__main__":
        print(f"Starting bot... Using preset:{config.active_preset}")
        bot = Bot(command_prefix="!", intents=discord.Intents.all())
        bot.load_cogs()

        @bot.event
        async def on_ready():
            print("Bot is ready!")

        bot.run(config.get_api_key("discord"))
        
except Exception as e:
    if e == KeyboardInterrupt:
        print("Exiting...")
        bot.close()
    else:
        print(f"An error occurred shutting bot down:\n\n{e}")
        bot.close()