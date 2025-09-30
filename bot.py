# bot.py
from __future__ import annotations
import os
import logging
from typing import Iterable, List

import discord
from discord.ext import commands

# ---------------------------------------------------------------------
# Minimal speak() to keep older helpers happy
def speak(text: str) -> str:
    return text
# ---------------------------------------------------------------------

# Logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("morpheus")

# Intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

# ---------------------------------------------------------------------
# Env helpers
def _csv_ids(env_name: str) -> List[int]:
    raw = os.getenv(env_name, "")
    out: List[int] = []
    for tok in raw.replace(" ", "").split(","):
        if not tok:
            continue
        try:
            out.append(int(tok))
        except Exception:
            pass
    return out

def _csv_list(env_name: str) -> List[str]:
    raw = os.getenv(env_name, "")
    vals = [x.strip() for x in raw.split(",") if x.strip()]
    return vals

def _normalize_cog_name(name: str) -> str:
    # accept "cogs.xyz" or "xyz"
    name = name.strip()
    return name if name.startswith("cogs.") else f"cogs.{name}"
# ---------------------------------------------------------------------


class MorpheusBot(commands.Bot):
    """Bot subclass so we can override setup_hook properly."""

    def __init__(self):
        prefix = os.getenv("BOT_PREFIX", "!")
        super().__init__(command_prefix=prefix, intents=intents)
        self._synced_once = False

    async def setup_hook(self):
        """Runs before connecting the websocket."""
        # 1) Load cogs with env control
        active = _csv_list("ACTIVE_COGS")
        if not active:
            # safe defaults for 1.0
            active = ["meme_feed_cog", "reaction_pin_cog", "void_pulse_cog", "diag_cog"]

        disabled = set(x.split(".")[-1] for x in _csv_list("DISABLED_COGS"))

        for cog_short in active:
            short = cog_short.split(".")[-1]
            if short in disabled:
                log.info("[COGS FILTER] Skipping %s (disabled)", short)
                continue
            module = _normalize_cog_name(cog_short)
            try:
                await self.load_extension(module)
                log.info("[COGS] Loaded %s", module)
            except Exception as e:
                log.error("[COGS] Failed to load %s: %s", module, e)

        # 2) Sync application commands
        try:
            dev_guild_ids = _csv_ids("DEV_GUILD_IDS")
            if dev_guild_ids:
                # Fast iteration during development: per-guild sync
                total = 0
                for gid in dev_guild_ids:
                    guild = discord.Object(id=gid)
                    self.tree.copy_global_to(guild=guild)
                    synced = await self.tree.sync(guild=guild)
                    total += len(synced)
                    log.info("[SYNC] Guild %s: %d commands", gid, len(synced))
                log.info("[SYNC] Completed per-guild sync to %d guild(s), total cmds ~%d",
                         len(dev_guild_ids), total)
            else:
                synced = await self.tree.sync()
                log.info("[SYNC] Global: %d commands", len(synced))
            self._synced_once = True
        except Exception as e:
            log.warning("[SYNC] Slash command sync failed: %s", e)

    async def on_ready(self):
        log.info("[READY] %s connected", self.user)


# ---- main entry -----------------------------------------------------
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("DISCORD_TOKEN not set in environment")

    bot = MorpheusBot()
    bot.run(token)
