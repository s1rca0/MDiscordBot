# bot.py
from __future__ import annotations

import os
import asyncio
import logging
import importlib
import pkgutil

import discord
from discord.ext import commands
from discord import app_commands

from ai_provider import chat_completion  # stable wrapper
from config import cfg  # module-level instance with safe defaults


# ---------- Logging: stdout-first (no files on Hobby) ----------
handlers = [logging.StreamHandler()]
if cfg.LOG_FILE:  # if you ever set one explicitly, we'll add it
    try:
        handlers.append(logging.FileHandler(cfg.LOG_FILE, encoding="utf-8"))
    except Exception as e:
        # Don't fail startup if file logging can't open
        print(f"[WARN] Failed to open LOG_FILE '{cfg.LOG_FILE}': {e}")

logging.basicConfig(
    level=getattr(logging, cfg.LOG_LEVEL.upper(), logging.INFO),
    handlers=handlers,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("morpheus.bot")

# Soft validation (never crashes on optional envs)
cfg.validate_config()


# Any modules we intentionally skip on auto-load (no setup(), deprecated, etc.)
EXCLUDE_MODULES = {
    "cogs.persona",     # helper only
    "cogs.lore_cog",    # removed
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
            description="M.O.R.P.H.E.U.S. — AI assistant for Legends in Motion HQ",
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

            # Sync slash commands globally
            try:
                synced = await self.bot.tree.sync()
                log.info("Synced %d commands: %s", len(synced), [c.name for c in synced])
            except Exception as e:
                log.warning("Slash command sync failed: %s", e)

            log.info("✅ Logged in as %s (%s)", self.bot.user, self.bot.user.id)

    def _register_app_commands(self):
        @self.bot.tree.command(name="ask", description="Ask M.O.R.P.H.E.U.S. a question")
        @app_commands.describe(prompt="Your question or prompt")
        async def ask(interaction: discord.Interaction, prompt: str):
            await interaction.response.defer()

            system_prompt = os.getenv(
                "SYSTEM_PROMPT",
                "You are M.O.R.P.H.E.U.S., a helpful, concise assistant.",
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ]

            try:
                reply = chat_completion(
                    messages,
                    temperature=cfg.AI_TEMPERATURE,
                    max_tokens=cfg.AI_MAX_NEW_TOKENS,
                )
            except Exception as e:
                log.exception("AI error: %s", e)
                reply = "I encountered interference. Try again."

            if not reply or not reply.strip():
                reply = "I am here—ask again."

            await interaction.followup.send(reply[: cfg.MAX_MESSAGE_LENGTH])

    async def start_bot(self):
        token = cfg.BOT_TOKEN  # matches config.py
        if not token:
            raise RuntimeError("Missing DISCORD_BOT_TOKEN env var")
        await self.bot.start(token)


async def main():
    bot = DiscordBot()
    await bot.start_bot()


if __name__ == "__main__":
    asyncio.run(main())