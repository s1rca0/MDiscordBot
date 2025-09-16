# bot.py — clean startup, no keepalive, modern setup_hook
import discord
from discord.ext import commands

from config import DISCORD_TOKEN, __version__, DRY_RUN
from config_store import is_locked
from utils.auth import is_owner
from discord import Object as DiscordObject
from config import DEV_GUILD_IDS

intents = discord.Intents.default()
intents.members = True
intents.message_content = True  # needed for light moderation/coach

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    if DEV_GUILD_IDS:
        for gid in DEV_GUILD_IDS:
            # Clear stale per-guild commands and publish instantly
            bot.tree.clear_commands(guild=DiscordObject(id=gid))
            await bot.tree.sync(guild=DiscordObject(id=gid))
        print(f"[READY] {bot.user} v{__version__} | Per-guild commands synced to {sorted(DEV_GUILD_IDS)}.")
    else:
        await bot.tree.sync()
        print(f"[READY] {bot.user} v{__version__} | Global commands synced (may take time to appear).")

@bot.check
async def global_lock_check(ctx: commands.Context):
    # Allow owners even under lockdown
    if is_locked() and not is_owner(ctx.author.id):
        raise commands.CheckFailure("Bot is temporarily locked by owner.")
    return True

# MVP cogs (import once; no legacy loaders)
from cogs.owner_mvp import OwnerMVP
from cogs.setup_mvp import SetupMVP
from cogs.purge_mvp import PurgeMVP
from cogs.debate_mvp import DebateMVP

@bot.event
async def setup_hook():
    # Load MVP cogs during Discord's async initialisation phase
    await bot.add_cog(OwnerMVP(bot))
    await bot.add_cog(SetupMVP(bot))
    await bot.add_cog(PurgeMVP(bot))
    await bot.add_cog(DebateMVP(bot))
    print("[COGS LOADED]", sorted(bot.cogs.keys()))

if __name__ == "__main__":
    print(f"[BOOT] Morpheus v{__version__} DRY_RUN={DRY_RUN}")
    if DRY_RUN:
        print("[bot] DRY_RUN: skipping Discord login. Set DISCORD_TOKEN in .env to run locally.")
    else:
        bot.run(DISCORD_TOKEN)