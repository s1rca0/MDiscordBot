# bot.py
import os
import logging
import discord
from discord.ext import commands

# ---------------------------------------------------------------------
# Local fallback to replace removed morpheus_voice
def speak(text: str) -> str:
    """Fallback voice wrapper (keeps older code paths happy)."""
    return text
# ---------------------------------------------------------------------

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("morpheus")

# Intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True  # needed for modern bots

# Bot setup
PREFIX = os.getenv("BOT_PREFIX", "!")
TOKEN = os.getenv("DISCORD_TOKEN")

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# Cog loader
async def load_cogs():
    active_cogs = [
        "cogs.meme_feed_cog",
        "cogs.reaction_pin_cog",
        "cogs.void_pulse_cog",
    ]
    disabled = os.getenv("DISABLED_COGS", "").split(",")
    disabled = [c.strip() for c in disabled if c.strip()]

    for cog in active_cogs:
        name = cog.split(".")[-1]
        if name in disabled:
            logger.info(f"[COGS FILTER] Skipping {cog} (disabled)")
            continue
        try:
            await bot.load_extension(cog)
            logger.info(f"[COGS] Loaded {cog}")
        except Exception as e:
            logger.error(f"[COGS] Failed to load {cog}: {e}")

@bot.event
async def on_ready():
    logger.info(f"[READY] {bot.user} connected")
    await load_cogs()

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN not set in environment")
    bot.run(TOKEN)
