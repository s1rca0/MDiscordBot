# bot.py
import os
import logging
from typing import List

import discord
from discord.ext import commands

# ---------------------------------------------------------------------
# Local fallback to replace removed morpheus_voice
def speak(text: str) -> str:
    """Fallback voice wrapper (keeps older code paths happy)."""
    return text
# ---------------------------------------------------------------------

# Logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("morpheus")

# Intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

# Bot
PREFIX = os.getenv("BOT_PREFIX", os.getenv("COMMAND_PREFIX", "!"))
TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
SYNC_ON_BOOT = str(os.getenv("SYNC_ON_BOOT", "true")).lower() in ("1", "true", "yes", "on")

bot = commands.Bot(command_prefix=PREFIX, intents=intents, description="Morpheus 1.0")

# ---------------------------- Cog loading ------------------------------------
def _parse_cog_list(env_val: str | None) -> List[str]:
    """Turn 'void_pulse_cog,meme_feed_cog' into fully-qualified module names."""
    if not env_val:
        return []
    toks = [t.strip() for t in env_val.split(",") if t.strip()]
    fq = []
    for t in toks:
        # allow either 'cogs.xyz' or bare 'xyz'
        fq.append(t if "." in t else f"cogs.{t}")
    return fq

def _active_cogs() -> List[str]:
    # Defaults for Morpheus 1.0
    default = ["cogs.void_pulse_cog", "cogs.meme_feed_cog", "cogs.reaction_pin_cog", "cogs.diag_cog"]
    env_val = os.getenv("ACTIVE_COGS", "")
    return _parse_cog_list(env_val) or default

def _disabled_cogs() -> set[str]:
    return set([t.strip() if "." in t else f"cogs.{t.strip()}"
                for t in os.getenv("DISABLED_COGS", "").split(",") if t.strip()])

async def _load_cogs():
    active = _active_cogs()
    disabled = _disabled_cogs()

    for mod in active:
        if mod in disabled:
            log.info("[COGS] Skipping %s (disabled)", mod)
            continue
        try:
            await bot.load_extension(mod)
            log.info("[COGS] Loaded %s", mod)
        except Exception as e:
            log.error("[COGS] Failed to load %s: %r", mod, e)

# discord.py recommended startup hook: load extensions before on_ready
@bot.setup_hook
async def _setup_hook():
    await _load_cogs()

# ---------------------------- Ready + Sync -----------------------------------
@bot.event
async def on_ready():
    log.info("[READY] %s connected", bot.user)

    if not SYNC_ON_BOOT:
        return

    # Force per-guild sync so new/changed commands appear immediately
    synced_total = 0
    for g in bot.guilds:
        try:
            cmds = await bot.tree.sync(guild=g)
            synced_total += len(cmds)
            log.info("[SYNC] %s: %d cmds", g.name, len(cmds))
        except Exception as e:
            log.error("[SYNC] %s failed: %r", g.name if g else "unknown-guild", e)
    if not bot.guilds:
        # If the bot isn’t in any guilds, at least ensure global tree is valid
        try:
            cmds = await bot.tree.sync()
            log.info("[SYNC] global: %d cmds", len(cmds))
        except Exception as e:
            log.error("[SYNC] global failed: %r", e)

# ------------------------------ Main -----------------------------------------
if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN not set in environment")
    bot.run(TOKEN)
