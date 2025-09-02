# cogs/chat_listener_cog.py
from __future__ import annotations
import time
from typing import Optional, Dict

import discord
from discord.ext import commands
from discord import app_commands

from ai_provider import ai_reply

# These imports are present elsewhere in your project already
from config import cfg
try:
    # persistent, in-memory for current process; survives restarts via env replay from /setup
    from config_store import store  # your tiny key/value overlay used by setup_cog
except Exception:
    store = None  # fall back gracefully if not present


# -------------------------
# Helpers / runtime config
# -------------------------
def _get_chat_channel_id() -> int:
    # Dynamic attribute is safe even if not in cfg dataclass;
    # setup commands will set cfg.CHAT_CHANNEL_ID at runtime.
    return getattr(cfg, "CHAT_CHANNEL_ID", 0)

def _get_dm_chat_enabled() -> bool:
    return bool(getattr(cfg, "DM_CHAT_ENABLED", False))

def _set_kv(key: str, value):
    if store:
        store.set(key, value)
    # also push onto cfg live so other code can read immediately
    setattr(cfg, key, value)


# -------------------------
# A tiny user-level rate limiter (memory only)
# -------------------------
class RateLimiter:
    """
    Simple sliding-window limiter to avoid floods:
      - max N messages per window per author
    """
    def __init__(self, max_msgs: int = 4, window_sec: int = 25):
        self.max_msgs = int(max_msgs)
        self.window_sec = int(window_sec)
        self.buckets: Dict[int, list[float]] = {}  # user_id -> timestamps

    def allow(self, user_id: int) -> bool:
        now = time.time()
        bucket = self.buckets.setdefault(user_id, [])
        # prune
        cutoff = now - self.window_sec
        bucket[:] = [t for t in bucket if t >= cutoff]
        if len(bucket) >= self.max_msgs:
            return False
        bucket.append(now)
        return True


# -------------------------
# The Cog
# -------------------------
class ChatListenerCog(commands.Cog):
    """
    Free-form chat:
      • DMs: if enabled, Morpheus replies to regular messages (no command needed)
      • Guild: optional single channel where free-form is allowed

    Safety:
      • Ignores bots, webhooks
      • Rate-limited
      • Skips empty messages & slash commands
      • No persistence to disk
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # modest defaults; you can change in commands below
        self.dm_enabled: bool = _get_dm_chat_enabled()
        self.chat_channel_id: int = _get_chat_channel_id()
        self.rl = RateLimiter(max_msgs=4, window_sec=25)

    # -------------------------
    # Public slash commands (owner/admin)
    # -------------------------
    @app_commands.command(name="dm_chat", description="Toggle free-form DM chat (bot replies to normal DMs).")
    @app_commands.describe(enabled="Turn DM chat on/off")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def dm_chat(self, interaction: discord.Interaction, enabled: bool):
        self.dm_enabled = bool(enabled)
        _set_kv("DM_CHAT_ENABLED", self.dm_enabled)
        await interaction.response.send_message(
            f"✅ DM chat **{'enabled' if self.dm_enabled else 'disabled'}**.",
            ephemeral=True
        )

    @app_commands.command(name="chat_channel_set", description="Make this channel the free-form chat lane.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def chat_channel_set(self, interaction: discord.Interaction):
        if interaction.guild is None or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("Run this inside a server text channel.", ephemeral=True)
            return
        self.chat_channel_id = interaction.channel.id
        _set_kv("CHAT_CHANNEL_ID", self.chat_channel_id)
        await interaction.response.send_message(
            f"✅ Free-form chat is now active in {interaction.channel.mention}.",
            ephemeral=True
        )

    @app_commands.command(name="chat_channel_clear", description="Disable free-form chat in the server channel.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def chat_channel_clear(self, interaction: discord.Interaction):
        self.chat_channel_id = 0
        _set_kv("CHAT_CHANNEL_ID", 0)
        await interaction.response.send_message("✅ Free-form server chat disabled.", ephemeral=True)

    # -------------------------
    # Listener
    # -------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bots, system, webhooks, empty content, and slash-command invocations
        if not message or message.author.bot or message.webhook_id:
            return
        if not (message.content or "").strip():
            return
        # Never step on slash commands (handled elsewhere)
        if message.content.startswith(("/", cfg.COMMAND_PREFIX)):
            return

        # DM mode
        if isinstance(message.channel, discord.DMChannel):
            if not self.dm_enabled:
                return
            # Lightweight guard: user rate limit
            if not self.rl.allow(message.author.id):
                try:
                    await message.channel.send("⏳ One sec—processing your recent messages.")
                except Exception:
                    pass
                return
            await self._reply(message, in_guild=False)
            return

        # Guild mode — only in the configured channel
        if message.guild is not None:
            if self.chat_channel_id and message.channel.id == self.chat_channel_id:
                # modest guard
                if not self.rl.allow(message.author.id):
                    try:
                        await message.channel.send(
                            f"{message.author.mention} ⏳ a moment—processing your recent messages."
                        )
                    except Exception:
                        pass
                    return
                await self._reply(message, in_guild=True)
            return

    # -------------------------
    # Core reply
    # -------------------------
    async def _reply(self, message: discord.Message, *, in_guild: bool):
        """Send an AI reply to the message content, with a friendly Morpheus tone."""
        try:
            async with message.channel.typing():
                # Minimal, self-contained system prompt so we don't depend on cfg fields
                system_prompt = (
                    "You are M.O.R.P.H.E.U.S., a concise, warm assistant. "
                    "Be helpful, confident, and avoid fluff. "
                    "Keep responses under ~10 lines unless necessary."
                )

                user_msg = message.content.strip()
                # Mention-awareness (optional—keeps replies tidy in channel)
                mention_prefix = (f"{message.author.mention} " if in_guild else "")

                text = await ai_reply(
                    system_prompt,
                    [{"role": "user", "content": user_msg}],
                    max_new_tokens=getattr(cfg, "AI_MAX_NEW_TOKENS", 512),
                    temperature=getattr(cfg, "AI_TEMPERATURE", 0.7),
                )
                if not text or not text.strip():
                    text = "I’m here. Try again?"

                # Discord limit safety
                limit = getattr(cfg, "MAX_MESSAGE_LENGTH", 1800)
                out = (mention_prefix + text).strip()
                if len(out) > limit:
                    out = out[:limit - 1] + "…"

                await message.channel.send(out)
        except Exception as e:
            # Silent failure in channel; log if your logger is set
            try:
                await message.channel.send("I hit a snag. Try again in a moment.")
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(ChatListenerCog(bot))