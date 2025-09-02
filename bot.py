# bot.py
import os
import asyncio
import logging
import importlib
import pkgutil

import discord
from discord.ext import commands
from discord import app_commands

from ai_provider import ai_reply
from config import BotConfig

cfg = BotConfig()
cfg.validate_config()

log = logging.getLogger(__name__)

# Helper/deleted modules to skip during auto-load
EXCLUDE_MODULES = {
    "cogs.persona",     # helper (no setup())
    "cogs.lore_cog",    # you removed it
}

class DiscordBot:
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True

        self.bot = commands.Bot(
            command_prefix=cfg.COMMAND_PREFIX,
            intents=intents,
            description="Morpheus — AI assistant for Legends in Motion HQ",
        )
        self._register_events()
        self._register_app_commands()

    async def _load_all_cogs(self):
        loaded, skipped = [], []
        package_name = "cogs"
        try:
            package = importlib.import_module(package_name)
        except Exception as e:
            log.warning("No 'cogs' package found: %s", e)
            return loaded, skipped

        for _, modname, ispkg in pkgutil.iter_modules(package.__path__, package_name + "."):
            if ispkg:
                continue
            if modname in EXCLUDE_MODULES:
                skipped.append((modname, "excluded"))
                continue
            try:
                mod = importlib.import_module(modname)
                if hasattr(mod, "setup"):
                    await self.bot.load_extension(modname)
                    loaded.append(modname)
                else:
                    skipped.append((modname, "no setup()"))
            except Exception as e:
                log.warning("Failed to load %s: %s: %s", modname, e.__class__.__name__, e)
                skipped.append((modname, f"{e.__class__.__name__}: {e}"))
        return loaded, skipped

    def _register_events(self):
        @self.bot.event
        async def on_ready():
            loaded, skipped = await self._load_all_cogs()
            if loaded:
                log.info("Loaded cogs: %s", ", ".join(loaded))
            if skipped:
                msg = ", ".join(f"{m} ({why})" for m, why in skipped)
                log.info("Skipped/failed cogs: %s", msg)

            # Sync slash commands
            try:
                synced = await self.bot.tree.sync()
                log.info("Synced %d commands: %s", len(synced), [c.name for c in synced])
            except Exception as e:
                log.warning("Slash command sync failed: %s", e)

            log.info("✅ Logged in as %s (%s)", self.bot.user, self.bot.user.id)

    def _register_app_commands(self):
        @self.bot.tree.command(name="ask", description="Ask Morpheus a question")
        @app_commands.describe(prompt="Your question or prompt")
        async def ask(interaction: discord.Interaction, prompt: str):
            await interaction.response.defer()
            try:
                reply = await ai_reply(
                    cfg.SYSTEM_PROMPT,
                    [{"role": "user", "content": prompt}],
                    max_new_tokens=cfg.AI_MAX_NEW_TOKENS,
                    temperature=cfg.AI_TEMPERATURE,
                )
            except Exception as e:
                log.exception("AI error: %s", e)
                reply = "I encountered interference. Try again."
            if not reply or not reply.strip():
                reply = "I am here—ask again."
            await interaction.followup.send(reply[:1900])

    async def start_bot(self):
        token = cfg.BOT_TOKEN
        if not token:
            raise RuntimeError("Missing DISCORD_BOT_TOKEN env var")
        await self.bot.start(token)