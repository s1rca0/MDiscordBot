# cogs/chat_cog.py
from __future__ import annotations
import time
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands

from config import cfg
from config_store import store
from ai_provider import ai_reply

# ---- keys used in config_store ----
K_ENABLED = "CHAT_ENABLED"          # bool
K_CHANNEL = "CHAT_CHANNEL_ID"       # int

DEFAULT_CHANNEL_NAME = "the-construct"
DEFAULT_ENABLED = True

# seconds between replies per-user (simple anti-spam)
USER_COOLDOWN_SEC = 10
# guardrail on message length we send to the model
MAX_USER_INPUT = 1200


def _get_enabled() -> bool:
    val = store.get(K_ENABLED)
    return DEFAULT_ENABLED if val is None else bool(val)


def _set_enabled(v: bool) -> None:
    store.set(K_ENABLED, bool(v))


def _get_channel_id() -> int:
    return int(store.get(K_CHANNEL) or 0)


def _set_channel_id(cid: int) -> None:
    store.set(K_CHANNEL, int(cid))


def _resolve_channel(guild: discord.Guild) -> Optional[discord.TextChannel]:
    """Find the chat channel by saved ID, or by DEFAULT_CHANNEL_NAME if unset."""
    cid = _get_channel_id()
    if cid:
        ch = guild.get_channel(cid)
        if isinstance(ch, discord.TextChannel):
            return ch

    # fallback by name (case-insensitive)
    for ch in guild.text_channels:
        if ch.name.lower() == DEFAULT_CHANNEL_NAME.lower():
            return ch
    return None


class ChatCog(commands.Cog, name="Chat"):
    """Free-form chat in a designated channel."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_user_reply_ts: dict[int, float] = {}  # user_id -> ts

    # ---------- Slash commands ----------
    @app_commands.command(name="chat_status", description="Show free-chat status and configured channel.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def chat_status(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return
        ch = _resolve_channel(interaction.guild)
        enabled = _get_enabled()
        desc = (
            f"**Status:** {'🟢 ON' if enabled else '🔴 OFF'}\n"
            f"**Channel:** {ch.mention if ch else '`(not set)`'}\n\n"
            f"Tip: Use `/chat_set_channel` in {interaction.guild.name} (and `/chat_on` or `/chat_off`)."
        )
        await interaction.response.send_message(desc, ephemeral=True)

    @app_commands.command(name="chat_on", description="Enable Morpheus free-chat in the configured channel.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def chat_on(self, interaction: discord.Interaction):
        _set_enabled(True)
        await interaction.response.send_message("✅ Free-chat is **ON**.", ephemeral=True)

    @app_commands.command(name="chat_off", description="Disable Morpheus free-chat.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def chat_off(self, interaction: discord.Interaction):
        _set_enabled(False)
        await interaction.response.send_message("✅ Free-chat is **OFF**.", ephemeral=True)

    @app_commands.command(name="chat_set_channel", description="Set the channel Morpheus should free-chat in.")
    @app_commands.describe(channel="Pick the channel Morpheus will listen and reply in.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def chat_set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if interaction.guild is None or channel.guild.id != interaction.guild.id:
            await interaction.response.send_message("Pick a channel from this server.", ephemeral=True)
            return
        _set_channel_id(channel.id)
        await interaction.response.send_message(
            f"✅ Free-chat channel set to {channel.mention}. Use `/chat_on` to enable.",
            ephemeral=True
        )

    # ---------- Message listener ----------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Reply only when:
          - In a guild
          - In the configured chat channel
          - Not a bot
          - Feature enabled
          - Message not a command (prefix)
          - Cooldown respected
        """
        if message.author.bot:
            return
        if message.guild is None:
            return

        # Require channel match
        chat_channel = _resolve_channel(message.guild)
        if not chat_channel or message.channel.id != chat_channel.id:
            return

        # Require feature enabled
        if not _get_enabled():
            return

        # Skip commands by prefix (avoid overlapping your other bots/commands)
        if cfg.COMMAND_PREFIX and message.content.strip().startswith(cfg.COMMAND_PREFIX):
            return

        # Simple per-user cooldown
        now = time.time()
        last = self._last_user_reply_ts.get(message.author.id, 0.0)
        if now - last < USER_COOLDOWN_SEC:
            return
        self._last_user_reply_ts[message.author.id] = now

        # Trim excessively long inputs
        user_text = (message.content or "").strip()
        if not user_text:
            return
        if len(user_text) > MAX_USER_INPUT:
            user_text = user_text[:MAX_USER_INPUT] + " …"

        # Build prompt with a light, alive tone but concise replies
        system = (
            cfg.SYSTEM_PROMPT
            or "You are M.O.R.P.H.E.U.S., responsive, succinct, and warm. Be helpful. Keep replies short."
        )

        try:
            reply_text = await ai_reply(
                system_prompt=system,
                messages=[{"role": "user", "content": user_text}],
                max_new_tokens=cfg.AI_MAX_NEW_TOKENS,
                temperature=cfg.AI_TEMPERATURE,
            )
        except Exception:
            reply_text = "Systems online. I’m here."

        reply_text = (reply_text or "").strip()
        if not reply_text:
            reply_text = "Listening."

        # Keep under Discord limit
        reply_text = reply_text[: cfg.MAX_MESSAGE_LENGTH]
        try:
            await message.reply(reply_text, mention_author=False, suppress_embeds=True)
        except Exception:
            # Fallback: post in channel if reply fails
            await message.channel.send(reply_text, suppress_embeds=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ChatCog(bot))