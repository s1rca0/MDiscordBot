# bot.py
from __future__ import annotations

import os
import asyncio
import logging
from typing import List, Tuple

import discord
from discord.ext import commands

# ---------- logging ----------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("morpheus.bot")

# ---------- intents / bot ----------
def make_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    intents.guilds = True
    intents.emojis = True
    intents.reactions = True
    return intents

# Cogs we consider essential for your server
CORE_EXTENSIONS: List[str] = [
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
    "cogs.user_app_cog",
    "cogs.faq_cog",
    "cogs.digest_cog",
    "cogs.memory_bridge_cog",
    "cogs.layer_cog",
    "cogs.mission_cog",
    "cogs.mod_recommender_cog",
    "cogs.pin_reaction_cog",
    "cogs.void_pulse_cog",
    "cogs.youtube_cog",          # single YT cog; uses env YT_CHANNEL_ID / YT_ANNOUNCE_CHANNEL_ID
]

# Optional / nice-to-have cogs (load if command budget permits)
OPTIONAL_EXTENSIONS: List[str] = [
    "cogs.backup_clone_cog",
    "cogs.disaster_recovery_cog",
    "cogs.dev_portal_tools_cog",   # harmless to skip if we’re near the 100 cmd cap
    "cogs.health_cog",
    "cogs.ethics_cog",
    "cogs.hackin_cog",
    # KEEP WELLBEING OPTIONAL: tends to push over 100-command limit on hobby plans
    "cogs.wellbeing_cog",
    # NOTE: deliberately NOT loading legacy extras:
    # "cogs.youtube_overview_cog",
    # "cogs.yt_announcer_cog",
]

# ---------- Bot class ----------
class DiscordBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or("/"),
            intents=make_intents(),
            help_command=None,
        )
        self.loaded: List[str] = []
        self.skipped: List[Tuple[str, str]] = []  # (ext, reason)

    async def setup_hook(self):
        # Load core first (error if truly broken), then optional with soft-fail
        await self._load_extensions(CORE_EXTENSIONS, hard=True)
        await self._load_extensions(OPTIONAL_EXTENSIONS, hard=False)

        # Sync (global). If you prefer per-guild, change here.
        try:
            synced = await self.tree.sync()
            names = [c.qualified_name if hasattr(c, "qualified_name") else c.name for c in synced]
            log.info("Synced %d commands: %s", len(names), names)
        except Exception as e:
            log.warning("Command tree sync failed: %s", e)

        # Final summary
        if self.loaded:
            log.info("Loaded cogs: %s", ", ".join(self.loaded))
        if self.skipped:
            pretty = ", ".join(f"{ext} ({reason})" for ext, reason in self.skipped)
            log.info("Skipped/failed cogs: %s", pretty)

    async def _load_extensions(self, exts: List[str], hard: bool):
        for ext in exts:
            try:
                await self.load_extension(ext)
                self.loaded.append(ext)
            except commands.errors.ExtensionFailed as e:
                reason = f"{type(e.original).__name__}: {e.original}"
                if hard:
                    log.error("Failed to load %s: %s", ext, reason)
                    raise
                self.skipped.append((ext, reason))
            except commands.errors.ExtensionNotFound as e:
                reason = f"{type(e).__name__}: {e}"
                if hard:
                    log.error("Failed to load %s: %s", ext, reason)
                    raise
                self.skipped.append((ext, reason))
            except commands.errors.ExtensionAlreadyLoaded:
                # harmless in reload scenarios
                self.loaded.append(ext)
            except Exception as e:
                reason = f"{type(e).__name__}: {e}"
                if hard:
                    log.error("Failed to load %s: %s", ext, reason)
                    raise
                self.skipped.append((ext, reason))

    async def on_ready(self):
        log.info("✅ Logged in as %s (%s)", self.user, self.user.id if self.user else "?")

    # entrypoint used by main.py
    async def start_bot(self):
        token = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN")
        if not token:
            raise RuntimeError("DISCORD_TOKEN is missing.")
        await self.start(token)


# ---------- helper to run directly (optional) ----------
async def run():
    bot = DiscordBot()
    await bot.start_bot()

if __name__ == "__main__":
    asyncio.run(run())