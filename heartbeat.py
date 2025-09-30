# config.py — hardened env parsing for Morpheus
import os
import logging
from typing import List, Set


def _parse_bool(val: str | None, default: bool = False) -> bool:
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_id_list(val: str | None) -> List[int]:
    if not val:
        return []
    out: List[int] = []
    for part in val.split(","):
        s = part.strip()
        if not s:
            continue
        try:
            out.append(int(s))
        except ValueError:
            # ignore non‑digits without crashing
            pass
    return out


def _parse_str_set(val: str | None) -> Set[str]:
    if not val:
        return set()
    return {p.strip() for p in val.split(",") if p.strip()}


# Core secrets
DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "").strip()
if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN missing. Set it in your env/Railway.")

# Identity / ownership
APPLICATION_ID: int | None = None
try:
    _app_id = os.getenv("APPLICATION_ID", "").strip()
    APPLICATION_ID = int(_app_id) if _app_id else None
except ValueError:
    APPLICATION_ID = None

OWNER_IDS: List[int] = _parse_id_list(os.getenv("OWNER_IDS"))

# Guild targeting (prefer GUILD_IDS, fallback to GUILD_ID)
GUILD_IDS: List[int] = _parse_id_list(os.getenv("GUILD_IDS"))
if not GUILD_IDS:
    single = os.getenv("GUILD_ID")
    if single:
        try:
            GUILD_IDS = [int(single.strip())]
        except ValueError:
            GUILD_IDS = []

if not GUILD_IDS:
    raise RuntimeError("No GUILD_IDS/GUILD_ID provided. Set at least one target guild id.")

# Feature flags / runtime controls
DRY_RUN: bool = _parse_bool(os.getenv("DRY_RUN"), default=False)
MESSAGE_CONTENT_INTENT: bool = _parse_bool(os.getenv("MESSAGE_CONTENT_INTENT"), default=False)
NUKE_ON_BOOT: bool = _parse_bool(os.getenv("NUKE_ON_BOOT"), default=False)

# Cogs
DISABLED_COGS: Set[str] = _parse_str_set(os.getenv("DISABLED_COGS"))

# Logging
LOG_LEVEL_NAME: str = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_NAME, logging.INFO)

VERSION: str = os.getenv("MORPHEUS_VERSION", "v0.26.0")


def summary_for_logs() -> str:
    return (
        f"[CFG] version={VERSION} dry_run={DRY_RUN} "
        f"guilds={GUILD_IDS} owners={OWNER_IDS or '[]'} "
        f"disabled_cogs={sorted(DISABLED_COGS) or '[]'} "
        f"msg_content_intent={MESSAGE_CONTENT_INTENT} nuke_on_boot={NUKE_ON_BOOT}"
    )
import logging
import discord
from discord import app_commands
from discord.ext import commands

import config as cfg

# minimal intents for a heartbeat
intents = discord.Intents.none()
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

 # choose a target guild id with fallbacks
_guild_ids = getattr(cfg, "GUILD_IDS", None)
if isinstance(_guild_ids, (list, tuple)) and _guild_ids:
    gid = int(_guild_ids[0])
else:
    gid = int(getattr(cfg, "GUILD_ID"))
_gobj = discord.Object(id=gid)


@bot.event
async def on_ready():
    print(f"[READY] {bot.user} | syncing to guild {gid}…")
    try:
        await bot.tree.sync(guild=_gobj)
        print("[SYNC] per-guild sync complete")
    except Exception as e:
        print("[SYNC ERROR]", e)


# unique name to bust any cache
@app_commands.command(name="ping_zz9", description="heartbeat")
async def ping(interaction: discord.Interaction):
    # reply immediately; no defer; keep under 3s wall time
    await interaction.response.send_message("pong ✅", ephemeral=True)


# register it only on our test guild
bot.tree.add_command(ping, guild=_gobj)


if __name__ == "__main__":
    logging.getLogger("discord").setLevel(getattr(cfg, "LOG_LEVEL", logging.INFO))
    bot.run(cfg.DISCORD_TOKEN)