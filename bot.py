# bot.py
from __future__ import annotations
import os
import sys
import asyncio
import traceback
import logging
import pkgutil

import discord
from discord.ext import commands

# -----------------------------------------------------------------------------
# .env loading (best-effort)
# -----------------------------------------------------------------------------
def _load_env():
    try:
        from dotenv import load_dotenv  # type: ignore
        env_loaded = load_dotenv()
        if env_loaded:
            print("[config] Loaded .env via python-dotenv")
        else:
            print("[config] .env not found or empty; relying on process env")
    except Exception:
        print("[config] .env not found next to config.py; relying on process env only")

_load_env()

# -----------------------------------------------------------------------------
# ENV / Settings
# -----------------------------------------------------------------------------
TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
if not TOKEN:
    print("FATAL: DISCORD_TOKEN is not set")
    sys.exit(1)

DRY_RUN = os.getenv("DRY_RUN", "false").lower() in {"1", "true", "yes"}

def _csv_ids(env_key: str) -> set[int]:
    raw = os.getenv(env_key, "")
    raw = raw.replace(" ", "")
    if not raw:
        return set()
    out: set[int] = set()
    for chunk in raw.split(","):
        if not chunk:
            continue
        try:
            out.add(int(chunk))
        except ValueError:
            # Keep going; some legacy cogs may still expect strings elsewhere.
            print(f"[warn] Skipping non-int value in {env_key}: {chunk!r}")
    return out

DEV_GUILD_IDS: set[int] = _csv_ids("DEV_GUILD_IDS")
OWNER_IDS: set[int]     = _csv_ids("OWNER_IDS")

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("morpheus")

# -----------------------------------------------------------------------------
# Intents / Bot
# -----------------------------------------------------------------------------
intents = discord.Intents.default()
# Slash commands do not require message_content; enable only if you need it.
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix=commands.when_mentioned_or("!"), intents=intents)

# -----------------------------------------------------------------------------
# Global slash-command error hook (never swallow exceptions silently)
# -----------------------------------------------------------------------------
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: Exception):
    try:
        msg = f"⚠️ Command error: `{type(error).__name__}: {str(error)[:1500]}`"
        if not interaction.response.is_done():
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            await interaction.followup.send(msg, ephemeral=True)
    except Exception:
        pass
    print("[APP-COMMAND-ERROR]", file=sys.stderr)
    traceback.print_exception(type(error), error, error.__traceback__)

# -----------------------------------------------------------------------------
# Cog loader (loads every *.py in cogs/ that has an async setup(bot) function)
# -----------------------------------------------------------------------------
async def _load_all_cogs():
    loaded = []
    pkg = "cogs"
    if not os.path.isdir(pkg := "cogs"):
        log.warning("No 'cogs/' directory found; skipping cog load.")
        return loaded

    for modinfo in pkgutil.iter_modules([pkg]):
        name = f"{pkg}.{modinfo.name}"
        try:
            await bot.load_extension(name)
            loaded.append(modinfo.name)
        except Exception as e:
            log.error("Failed to load cog %s: %s", name, e)
    if loaded:
        print(f"[COGS LOADED] {loaded}")
    return loaded

# -----------------------------------------------------------------------------
# Hard-nuke stale app commands on every boot (global + per-guild), then re-sync
# -----------------------------------------------------------------------------
@bot.event
async def on_ready():
    print(f"[BOOT] Morpheus v0.25.2 DRY_RUN={DRY_RUN}")
    print(f"[READY] {bot.user} connected; nuke_on_boot=True")

    app_id = bot.application_id

    try:
        # Pick correct HTTP methods for current discord.py build
        http = bot.http
        put_global = getattr(http, "put_global_commands", None)
        put_guild  = getattr(http, "put_guild_commands", None)

        if callable(put_global) and callable(put_guild):
            # Hard-nuke remote GLOBAL commands
            await put_global(app_id, [])  # type: ignore[misc]
            print("[SYNC] Cleared GLOBAL commands (remote)")

            # Hard-nuke remote GUILD commands for each dev guild
            for gid in DEV_GUILD_IDS:
                await put_guild(app_id, gid, [])  # type: ignore[misc]
                print(f"[SYNC] Cleared GUILD commands (remote): {gid}")
        else:
            # Fallback for forks without those methods: clear local trees
            bot.tree.clear_commands(guild=None)
            for gid in DEV_GUILD_IDS:
                bot.tree.clear_commands(guild=discord.Object(id=gid))
            print("[SYNC] Fallback: cleared local trees (no HTTP put_* available)")

        # Re-publish per-guild commands from our current in-memory tree (fast)
        synced_guilds = []
        for gid in DEV_GUILD_IDS:
            await bot.tree.sync(guild=discord.Object(id=gid))
            synced_guilds.append(gid)
        print(f"[READY] {bot.user} | Per-guild commands synced to {synced_guilds}")

        # Optional: publish global commands too
        # await bot.tree.sync()
    except Exception as e:
        print("[SYNC ERROR]", e)

# -----------------------------------------------------------------------------
# Startup hook: load cogs before we reach on_ready sync
# -----------------------------------------------------------------------------
@bot.event
async def setup_hook():
    await _load_all_cogs()

# -----------------------------------------------------------------------------
# Owner gate convenience (used by cogs if they want)
# -----------------------------------------------------------------------------
async def is_owner(user: discord.abc.User) -> bool:
    try:
        if user.id in OWNER_IDS:
            return True
        return await bot.is_owner(user)
    except Exception:
        return False

# -----------------------------------------------------------------------------
# Run
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        log.info("Logging in using static token")
        bot.run(TOKEN)
    except KeyboardInterrupt:
        print("\n[EXIT] KeyboardInterrupt")
    except Exception as e:
        print("[FATAL]", e)
        sys.exit(1)