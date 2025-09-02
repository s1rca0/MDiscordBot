# bot.py
import os
import logging
import importlib
from typing import List

import discord
from discord.ext import commands
from discord import app_commands

from ai_provider import ai_reply
from config import BotConfig

log = logging.getLogger(__name__)
cfg = BotConfig()
cfg.validate_config()


class DiscordBot:
    def __init__(self):
        self._synced = False

        # ---- Intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True

        # ---- Bot
        self.bot = commands.Bot(
            command_prefix=cfg.COMMAND_PREFIX,
            intents=intents,
            description="Morpheus — AI assistant for Legends in Motion HQ",
        )

        # Register handlers and commands
        self._register_events()
        self._register_app_commands()

    # -------------------- lifecycle --------------------
    async def start_bot(self):
        token = cfg.BOT_TOKEN
        if not token:
            raise RuntimeError("Missing DISCORD_BOT_TOKEN")
        await self.bot.start(token)

    # -------------------- events --------------------
    def _register_events(self):
        @self.bot.event
        async def on_ready():
            # sync slash commands once per process
            if not self._synced:
                try:
                    synced = await self.bot.tree.sync()
                    log.info("Synced %d commands: %s", len(synced), [c.name for c in synced])
                except Exception as e:
                    log.warning("Slash command sync failed: %s", e)
                self._synced = True

            log.info("✅ Logged in as %s (%s)", self.bot.user, self.bot.user.id)

            # Auto-load all cogs on first ready
            try:
                await self._auto_load_cogs()
            except Exception as e:
                log.exception("Auto cog load failed: %s", e)

        @self.bot.event
        async def on_message(message: discord.Message):
            # Let other bots pass; keep prefix cmds working
            if message.author.bot:
                return

            # Trigger only in DMs or when mentioned in guild
            trigger = (message.guild is None) or (self.bot.user in message.mentions)
            if not trigger:
                return

            content = message.content or ""
            if message.guild is not None:
                # strip mention variants
                content = content.replace(f"<@{self.bot.user.id}>", "").replace(
                    f"<@!{self.bot.user.id}>", ""
                ).strip()
            if not content:
                content = "Say hi."

            try:
                reply = await ai_reply(
                    cfg.SYSTEM_PROMPT,
                    [{"role": "user", "content": content}],
                    max_new_tokens=cfg.AI_MAX_NEW_TOKENS,
                    temperature=cfg.AI_TEMPERATURE,
                )
            except Exception as e:
                log.exception("AI error: %s", e)
                reply = "Sorry, I hit an error. Try again."

            if not reply or not reply.strip():
                reply = "I’m here—try again."

            # keep under Discord limit
            await message.channel.send(reply[:1900])

            # allow prefixed commands to continue
            await self.bot.process_commands(message)

    # -------------------- slash/app cmds --------------------
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

    # -------------------- utilities --------------------
    async def _auto_load_cogs(self):
        """Load every .py module in ./cogs as an extension if it exposes setup()."""
        cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")
        if not os.path.isdir(cogs_dir):
            log.warning("cogs/ directory not found; skipping auto-load.")
            return

        loaded: List[str] = []
        skipped: List[str] = []

        for fname in sorted(os.listdir(cogs_dir)):
            if not fname.endswith(".py") or fname.startswith(("_", ".")):
                continue
            mod_name = fname[:-3]
            ext_path = f"cogs.{mod_name}"
            try:
                # quick presence check to avoid import side-effects if no setup()
                spec = importlib.util.find_spec(ext_path)
                if spec is None:
                    skipped.append(ext_path)
                    continue

                # Let discord.py load it (expects async setup(bot))
                await self.bot.load_extension(ext_path)
                loaded.append(ext_path)
            except Exception as e:
                log.warning("Failed to load %s: %s", ext_path, e)
                skipped.append(ext_path)

        if loaded:
            log.info("Loaded cogs: %s", ", ".join(loaded))
        if skipped:
            log.info("Skipped/failed cogs: %s", ", ".join(skipped))