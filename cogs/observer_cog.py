# cogs/observer_cog.py
from __future__ import annotations

import os
import re
import logging
import asyncio
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands

# --------- Config helpers ---------
def _to_int(s: str | None) -> int:
    try:
        return int(str(s).strip())
    except Exception:
        return 0

OPS_LOG_CHANNEL_ID = _to_int(os.getenv("OPS_LOG_CHANNEL_ID", "0"))
OWNER_PING_ID      = _to_int(os.getenv("OWNER_PING_ID", "0"))        # <— set this to your Discord user ID to get pings
OPS_LOG_CHANNEL_FALLBACK_NAME = os.getenv("OPS_LOG_CHANNEL_NAME", "ops-logs")  # resolves by name if ID not set

# Patterns that should trigger an alert ping
ALERT_PATTERNS = [
    r"CommandLimitReached",
    r"ExtensionFailed",
    r"ExtensionNotFound",
    r"Fatal error starting bot",
    r"DISCORD_TOKEN is missing",
    r"invalid literal for int\(\) with base 10",
    r"YouTubeCog not started",
    r"Failed to load cogs\.",        # broad loader failures
]

ALERT_RX = re.compile("|".join(ALERT_PATTERNS), re.IGNORECASE)

# --------- Logging bridge ---------
class _LogForwarder(logging.Handler):
    """Bridges chosen log records into a Discord channel and pings owner on alerts."""

    def __init__(self, cog: "ObserverCog"):
        super().__init__()
        self.cog = cog

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
        except Exception:
            msg = f"[log formatting failed] {getattr(record, 'message', '')}"

        # Heuristic: send WARN/ERROR from key loggers, and anything matching ALERT_RX
        name = record.name or ""
        level = record.levelno
        is_watch_logger = any(
            name.startswith(pfx) for pfx in (
                "morpheus.bot", "entry", "discord.client", "discord.gateway",
                "cogs.", "cogs.youtube_cog", "cogs.void_pulse_cog"
            )
        )

        # Build a short one-line summary
        summary = f"[{name}] {record.levelname}: {msg}"
        if len(summary) > 1800:
            summary = summary[:1790] + " …"

        # Decide whether to ping owner
        ping_owner = bool(ALERT_RX.search(msg) or level >= logging.ERROR)

        # Ship to Discord (fire-and-forget)
        asyncio.create_task(self.cog._sys_log(summary, ping_owner=ping_owner))

# --------- Cog ---------
class ObserverCog(commands.Cog, name="Observer"):
    """
    Minimal observer that forwards key runtime logs to #ops-logs and pings the owner on alerts.
    Commands (keep count small):
      • /observer_status  — show target channel and ping target
      • /observer_set_channel  — set #ops-logs by current channel
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ops_channel_id: int = OPS_LOG_CHANNEL_ID
        self.owner_ping_id: int = OWNER_PING_ID
        self._handler: Optional[_LogForwarder] = None

    # ----- utilities -----
    def _resolve_ops_channel(self, guild: discord.Guild | None) -> Optional[discord.TextChannel]:
        if guild is None:
            return None
        # prefer explicit ID
        if self.ops_channel_id:
            ch = guild.get_channel(self.ops_channel_id)
            if isinstance(ch, discord.TextChannel):
                return ch
        # fallback by name
        name = OPS_LOG_CHANNEL_FALLBACK_NAME.lower().strip("# ")
        for ch in guild.text_channels:
            if ch.name.lower() == name:
                return ch
        return None

    async def _sys_log(self, text: str, *, ping_owner: bool = False):
        """
        Send a system log line to the first guild's #ops-logs we can resolve.
        If ping_owner=True and OWNER_PING_ID is set, mention them.
        """
        # Try across all guilds until we find the target channel
        ch: Optional[discord.TextChannel] = None
        for g in self.bot.guilds:
            ch = self._resolve_ops_channel(g)
            if ch:
                break
        if not ch:
            return  # nowhere to send

        content = text
        if ping_owner and self.owner_ping_id:
            content = f"<@{self.owner_ping_id}> ⚠️ {text}"

        try:
            await ch.send(content)
        except Exception:
            pass

    # ----- lifecycle -----
    async def cog_load(self):
        # Attach logging handler (single instance)
        root = logging.getLogger()
        self._handler = _LogForwarder(self)
        self._handler.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s")
        self._handler.setFormatter(fmt)
        root.addHandler(self._handler)

        # Early ping so you know Observer is on
        await asyncio.sleep(2)
        await self._sys_log("Observer online. Monitoring logs for alerts.")

    async def cog_unload(self):
        if self._handler:
            try:
                logging.getLogger().removeHandler(self._handler)
            except Exception:
                pass
            self._handler = None

    # ----- commands (tiny surface) -----
    @app_commands.command(name="observer_status", description="Show observer status")
    async def observer_status(self, itx: discord.Interaction):
        g = itx.guild
        ch = self._resolve_ops_channel(g) if g else None
        ch_repr = ch.mention if ch else f"(auto: #{OPS_LOG_CHANNEL_FALLBACK_NAME}, ID={self.ops_channel_id or 'unset'})"
        owner_repr = f"<@{self.owner_ping_id}>" if self.owner_ping_id else "(unset)"
        await itx.response.send_message(
            f"**Observer**\n• ops channel: {ch_repr}\n• owner ping: {owner_repr}\n• patterns: `{', '.join(p for p in ALERT_PATTERNS)}`",
            ephemeral=True
        )

    @app_commands.command(name="observer_set_channel", description="Set this channel as the ops-logs target")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def observer_set_channel(self, itx: discord.Interaction):
        if not isinstance(itx.channel, discord.TextChannel):
            await itx.response.send_message("Please run this in a standard text channel.", ephemeral=True)
            return
        self.ops_channel_id = itx.channel.id
        await itx.response.send_message(f"✅ Set ops log channel to {itx.channel.mention}", ephemeral=True)
        await self._sys_log(f"Ops log channel updated to {itx.channel.mention}.")

async def setup(bot: commands.Bot):
    await bot.add_cog(ObserverCog(bot))