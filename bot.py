# bot.py
from __future__ import annotations
import os
import logging
import asyncio
from typing import List, Tuple

import discord
from discord.ext import commands

log = logging.getLogger("morpheus.bot")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")

# ---- Intents ----
def _make_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    intents.guilds = True
    intents.presences = False
    return intents

# ---- Cog lists (load core first, then optional until near the 100 command cap) ----
COGS_CORE: List[str] = [
    # absolutely essential / already agreed to keep
    "cogs.setup_cog",
    "cogs.help_cog",
    "cogs.about_cog",
    "cogs.ai_mode_cog",
    "cogs.chat_cog",
    "cogs.chat_listener_cog",
    "cogs.dm_start_cog",
    "cogs.invite_cog",
    "cogs.rules_cog",
    "cogs.moderation_cog",
    "cogs.roles_cog",
    "cogs.tickets_cog",
    "cogs.onboarding_fasttrack_cog",
    "cogs.welcome_construct_cog",
    "cogs.presence_cog",
    "cogs.meme_feed_cog",
]

# Load these only if command budget allows
COGS_OPTIONAL: List[str] = [
    "cogs.user_app_cog",
    "cogs.faq_cog",
    "cogs.digest_cog",
    "cogs.memory_bridge_cog",
    "cogs.layer_cog",
    "cogs.mission_cog",
    "cogs.mod_recommender_cog",
    "cogs.pin_reaction_cog",
    "cogs.void_pulse_cog",
    "cogs.youtube_cog",
    "cogs.youtube_overview_cog",
    "cogs.yt_announcer_cog",
    "cogs.backup_clone_cog",
    "cogs.disaster_recovery_cog",
    "cogs.dev_portal_tools_cog",
    "cogs.health_cog",
    "cogs.ethics_cog",
    "cogs.hackin_cog",
    "cogs.void_pulse_cog",  # safe duplicate guard will ignore if already loaded
    "cogs.wellbeing_cog",
]

COMMAND_CAP = 100
# Keep a little headroom to avoid flapping on sync
COMMAND_SOFT_LIMIT = int(os.getenv("COMMAND_SOFT_LIMIT", "98") or 98)

class DiscordBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned_or("!"),
            intents=_make_intents(),
            application_id=int(os.getenv("DISCORD_APP_ID", "0") or 0) or None,
        )
        self._loaded: List[str] = []
        self._skipped: List[Tuple[str, str]] = []  # (cog, reason)

    async def setup_hook(self) -> None:
        # Load cogs in order
        await self._load_cogs(COGS_CORE, label="core")
        await self._load_cogs(COGS_OPTIONAL, label="optional")

        # Sync once after loading
        try:
            synced = await self.tree.sync()
            log.info("Synced %d commands: %s", len(synced), [c.name for c in synced])
        except Exception as e:
            log.exception("Command sync failed: %s", e)

        # Nice log summary
        log.info("Loaded cogs: %s", ", ".join(self._loaded) if self._loaded else "(none)")
        if self._skipped:
            msg = ", ".join([f"{c} ({r})" for c, r in self._skipped])
            log.info("Skipped/failed cogs: %s", msg)

    async def _load_cogs(self, names: List[str], *, label: str) -> None:
        for ext in names:
            if ext in self._loaded:
                continue
            # Before loading more, check a soft command limit
            try:
                current_count = len(self.tree.get_commands())
            except Exception:
                current_count = 0
            if current_count >= COMMAND_SOFT_LIMIT:
                self._skipped.append((ext, f"command budget {current_count}/{COMMAND_CAP}"))
                continue

            try:
                await self.load_extension(ext)
                self._loaded.append(ext)
            except discord.app_commands.CommandLimitReached:
                self._skipped.append((ext, "CommandLimitReached (>=100)"))
            except commands.errors.ExtensionAlreadyLoaded:
                # harmless
                if ext not in self._loaded:
                    self._loaded.append(ext)
            except Exception as e:
                self._skipped.append((ext, f"{e.__class__.__name__}: {e}"))

    async def on_ready(self):
        log.info("✅ Logged in as %s (%s)", self.user, self.user.id if self.user else "unknown")

    # ----- entrypoint expected by main.py -----
    async def start_bot(self):
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token:
            raise RuntimeError("DISCORD_TOKEN is missing.")
        # discord.py handles reconnect internally; keep_alive server runs elsewhere
        await self.start(token, reconnect=True)