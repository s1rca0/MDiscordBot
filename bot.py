# bot.py
from __future__ import annotations
import asyncio
import logging
from typing import Iterable, List

import discord
from discord import app_commands
from discord.ext import commands

from config import cfg

log = logging.getLogger("morpheus.bot")
logging.basicConfig(level=getattr(logging, (cfg.LOG_LEVEL or "INFO").upper()))

# ---- Hard requirements (always load) ----
CORE_COGS: List[str] = [
    "cogs.about_cog",
    "cogs.ai_mode_cog",
    "cogs.backup_clone_cog",
    "cogs.botnick_cog",
    "cogs.chat_cog",
    "cogs.chat_listener_cog",
    "cogs.dev_portal_tools_cog",
    "cogs.digest_cog",
    "cogs.disaster_recovery_cog",
    "cogs.dm_start_cog",
    "cogs.ethics_cog",
    "cogs.faq_cog",
    "cogs.hackin_cog",
    "cogs.health_cog",
    "cogs.help_cog",
    "cogs.invite_cog",
    "cogs.layer_cog",
    "cogs.meme_feed_cog",
    "cogs.memory_bridge_cog",
    "cogs.mission_cog",
    "cogs.mod_recommender_cog",
    "cogs.moderation_cog",
    "cogs.onboarding_fasttrack_cog",
    "cogs.pin_reaction_cog",
    "cogs.presence_cog",
    "cogs.promotion_cog",
    "cogs.roles_cog",
    "cogs.rules_cog",
    "cogs.setup_cog",
    "cogs.tickets_cog",
    "cogs.user_app_cog",
    "cogs.welcome_construct_cog",
]

# ---- Optional cogs (loaded until we approach Discord’s 100 global command limit) ----
OPTIONAL_COGS: List[str] = [
    "cogs.void_pulse_cog",
    "cogs.wellbeing_cog",
    "cogs.youtube_cog",
    "cogs.youtube_overview_cog",
    "cogs.yt_announcer_cog",
    # "cogs.persona",  # intentionally excluded
]


class DiscordBot(commands.Bot):
    """
    Exported for main.py. Keeps us within the global slash command cap and logs
    any cogs it must skip.
    """

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True  # needed for chat channel listener, purge, etc.
        super().__init__(command_prefix=cfg.COMMAND_PREFIX or "$", intents=intents)

        self._failed_cogs: List[str] = []
        self._skipped_cogs: List[str] = []

    async def setup_hook(self) -> None:
        # Load core cogs (must-have). We log but do not crash on individual failures.
        await self._load_cogs(CORE_COGS, label="core")

        # Try optionals conservatively (stop when we near/exceed the command cap).
        await self._load_optionals_with_cap()

        # Final sync
        try:
            cmds = await self.tree.sync()
            log.info("Synced %d commands: %s", len(cmds), [c.name for c in cmds])
        except Exception as e:
            log.warning("Slash command sync failed: %s", e)

        log.info("✅ Logged in as %s (%s)", self.user, self.user.id if self.user else "?")
        if self._failed_cogs or self._skipped_cogs:
            log.info(
                "Skipped/failed cogs: %s",
                ", ".join(self._skipped_cogs + self._failed_cogs) or "(none)",
            )

    async def _load_cogs(self, cogs: Iterable[str], *, label: str) -> None:
        for ext in cogs:
            try:
                await self.load_extension(ext)
            except app_commands.CommandLimitReached as e:
                # If core ever hits the cap, we still continue; you’ll see the log.
                self._skipped_cogs.append(f"{ext} (CommandLimitReached)")
                log.warning("Failed to load %s: %s: %s", ext, e.__class__.__name__, e)
            except commands.errors.ExtensionFailed as e:
                self._failed_cogs.append(f"{ext} ({e.__class__.__name__}: {e.original})")
                log.warning("Failed to load %s: %s: %s", ext, e.__class__.__name__, e)
            except Exception as e:
                self._failed_cogs.append(f"{ext} ({e.__class__.__name__})")
                log.warning("Failed to load %s: %s: %s", ext, e.__class__.__name__, e)

        loaded = [e for e in cogs if e not in (self._failed_cogs + self._skipped_cogs)]
        log.info("Loaded %s cogs: %s", label, ", ".join(loaded) or "(none)")

    async def _load_optionals_with_cap(self) -> None:
        """
        Load optional cogs until we approach the 100 global command limit.
        If adding a cog triggers CommandLimitReached, skip it and continue.
        """
        for ext in OPTIONAL_COGS:
            try:
                await self.load_extension(ext)
                # Probe a lightweight sync to see if we crossed the cap
                try:
                    await self.tree.sync()
                except app_commands.CommandLimitReached:
                    # Roll back this cog; mark as skipped
                    await self.unload_extension(ext)
                    self._skipped_cogs.append(f"{ext} (CommandLimitReached)")
                    log.warning("Skipping %s: global command cap reached.", ext)
                except Exception:
                    # Non-cap errors on sync are logged but keep the cog
                    log.debug("Post-load sync hiccup for %s (ignored).", ext)
            except app_commands.CommandLimitReached:
                self._skipped_cogs.append(f"{ext} (CommandLimitReached)")
                log.warning("Skipping %s: global command cap reached at load time.", ext)
            except commands.errors.ExtensionFailed as e:
                self._failed_cogs.append(f"{ext} ({e.__class__.__name__}: {e.original})")
                log.warning("Failed to load %s: %s: %s", ext, e.__class__.__name__, e)
            except Exception as e:
                self._failed_cogs.append(f"{ext} ({e.__class__.__name__})")
                log.warning("Failed to load %s: %s: %s", ext, e.__class__.__name__, e)

    async def on_ready(self):
        # Friendly one-liners so Railway logs are readable
        log.info("Loaded cogs: %s", ", ".join(sorted(self.extensions.keys())))
        skipped = ", ".join(self._skipped_cogs) or "(none)"
        failed = ", ".join(self._failed_cogs) or "(none)"
        log.info("Skipped/failed cogs: %s | %s", skipped, failed)


# Note:
# - PyNaCl warning is harmless unless you need voice.
# - main.py is expected to do:
#       from bot import DiscordBot
#       bot = DiscordBot()
#       bot.run(cfg.BOT_TOKEN)