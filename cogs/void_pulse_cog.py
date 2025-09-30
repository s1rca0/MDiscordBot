# cogs/void_pulse_cog.py
import os
import random
from datetime import timedelta
from typing import Optional, Tuple

import discord
from discord.ext import commands
from discord import app_commands

from config import BotConfig
from cogs.utils.morpheus_voice import mk_embed, speak

cfg = BotConfig()


def _jittered_hours(base: int, jitter: int) -> int:
    if jitter <= 0:
        return base
    lo = max(1, base - jitter)
    hi = base + jitter
    return random.randint(lo, hi)


class VoidPulseCog(commands.Cog, name="Void Pulse"):
    """
    Posts an atmospheric ping in a chosen channel when the server has been quiet.
    Channel can be forced via env var (Railway) or set via slash cmd as fallback.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # ----- Env-first config (Railway) -----
        # Global override for the target channel (preferred).
        self.env_channel_id: int = int(os.getenv("VOID_BROADCAST_CHANNEL_ID", "0") or "0")

        # Legacy / fallback envs (kept for compatibility).
        self.enabled = os.getenv("VOIDPULSE_ENABLE", "true").lower() in ("1", "true", "yes")
        self.cooldown_hours = int(os.getenv("VOIDPULSE_COOLDOWN_HOURS", "36"))
        self.cooldown_jitter = int(os.getenv("VOIDPULSE_COOLDOWN_JITTER", "45"))  # +/- hours
        self.quiet_threshold_min = int(os.getenv("VOIDPULSE_QUIET_THRESHOLD_MIN", "180"))  # last non-bot msg
        self.scan_window_min = int(os.getenv("VOIDPULSE_SCAN_WINDOW_MIN", "120"))  # count-only window
        self.scan_window_max_msgs = int(os.getenv("VOIDPULSE_SCAN_WINDOW_MAXMSGS", "6"))

        # Slash-set fallback (guild-local). Kept in memory only.
        self.cmd_channel_id: int = int(os.getenv("VOID_CHANNEL_ID", "0") or "0")

        self.last_pulse_ts: Optional[discord.utils.utcnow] = None

    # ---------- Helpers ----------
    def _effective_channel_id(self) -> int:
        # Env wins if present; otherwise use slash-set fallback.
        return self.env_channel_id or self.cmd_channel_id or 0

    def _channel(self, guild: Optional[discord.Guild]) -> Optional[discord.TextChannel]:
        if not guild:
            return None
        ch_id = self._effective_channel_id()
        return guild.get_channel(ch_id) if ch_id else None

    # ---------- Admin commands ----------
    @app_commands.command(name="voidpulse_status", description="Show current VoidPulse config and recent state.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def voidpulse_status(self, interaction: discord.Interaction):
        ch = self._channel(interaction.guild)
        src = "ENV:VOID_BROADCAST_CHANNEL_ID" if self.env_channel_id else (
            "Slash-set (volatile)" if self.cmd_channel_id else "unset"
        )
        desc = (
            f"**Enabled:** `{self.enabled}`\n"
            f"**Channel:** {ch.mention if ch else '`unset`'}  • **Source:** `{src}`\n"
            f"**Cooldown (hours):** `{self.cooldown_hours}` | **Jitter (±h):** `{self.cooldown_jitter}`\n"
            f"**Quiet threshold (min):** `{self.quiet_threshold_min}`\n"
            f"**Window (min):** `{self.scan_window_min}`, **Quiet if ≤ {self.scan_window_max_msgs} msgs**\n"
            f"**Last pulse:** `{int(self.last_pulse_ts.timestamp()) if self.last_pulse_ts else '—'}` (unix)\n"
            "_No message content is stored—only counts/timestamps._"
        )
        await interaction.response.send_message(embed=mk_embed("VoidPulse", desc), ephemeral=True)

    @app_commands.command(name="voidpulse_set_channel", description="Set the channel used for VoidPulse (fallback if no ENV).")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def voidpulse_set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        self.cmd_channel_id = channel.id
        await interaction.response.send_message(
            embed=mk_embed(
                "VoidPulse",
                f"Fallback channel set to {channel.mention}.\n"
                f"Note: ENV `VOID_BROADCAST_CHANNEL_ID` will override this if present."
            ),
            ephemeral=True
        )

    @app_commands.command(name="voidpulse_reload_env", description="Reload VOID_BROADCAST_CHANNEL_ID from environment.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def voidpulse_reload_env(self, interaction: discord.Interaction):
        self.env_channel_id = int(os.getenv("VOID_BROADCAST_CHANNEL_ID", "0") or "0")
        src = "ENV present" if self.env_channel_id else "ENV not set; using slash fallback"
        await interaction.response.send_message(embed=mk_embed("VoidPulse", f"Reloaded env. {src}."), ephemeral=True)

    @app_commands.command(name="voidpulse_toggle", description="Enable/disable VoidPulse.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def voidpulse_toggle(self, interaction: discord.Interaction, enable: Optional[bool] = None):
        self.enabled = (not self.enabled) if enable is None else enable
        state = "enabled" if self.enabled else "disabled"
        await interaction.response.send_message(embed=mk_embed("VoidPulse", f"VoidPulse **{state}**."), ephemeral=True)

    @app_commands.command(name="voidpulse_nudge", description="Force a one-off pulse check now.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def voidpulse_nudge(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=mk_embed("VoidPulse", "Attempting a pulse…"), ephemeral=True)
        ok, why = await self._maybe_pulse(interaction.guild)
        msg = "Done." if ok else f"No pulse: {why or 'conditions not met'}"
        await interaction.followup.send(embed=mk_embed("VoidPulse", msg), ephemeral=True)

    # ---------- Internals ----------
    async def _maybe_pulse(self, guild: Optional[discord.Guild]) -> Tuple[bool, Optional[str]]:
        if not guild or not self.enabled:
            return False, "disabled"

        ch = self._channel(guild)
        if not ch:
            return False, "no channel set"

        # Cooldown
        if self.last_pulse_ts:
            elapsed = (discord.utils.utcnow() - self.last_pulse_ts).total_seconds() / 3600
            if elapsed < _jittered_hours(self.cooldown_hours, self.cooldown_jitter):
                return False, "cooldown"

        ok, why = await self._is_quiet(ch)
        if not ok:
            return False, why

        # Post the “alive” signal
        await ch.send(speak("[signal] The Void hums tonight. Those who listen may hear the door unlatch."))
        self.last_pulse_ts = discord.utils.utcnow()
        return True, None

    async def _is_quiet(self, channel: discord.TextChannel) -> Tuple[bool, str]:
        """
        Quiet == (last non-bot user message older than quiet_threshold)
                 AND (message count within scan window <= max msgs)
        """
        quiet_thresh = self.quiet_threshold_min
        window_min = self.scan_window_min
        max_msgs = self.scan_window_max_msgs

        now = discord.utils.utcnow()
        since_ts = now - timedelta(minutes=max(quiet_thresh, window_min))

        last_user_msg_age_min: Optional[int] = None
        count_in_window = 0

        try:
            async for msg in channel.history(limit=200, after=since_ts, oldest_first=False):
                # Count all messages in window
                age_min = int(((now - msg.created_at).total_seconds()) // 60)
                if age_min <= window_min:
                    count_in_window += 1

                # Track most recent non-bot author age for quiet threshold
                if (not msg.author.bot) and last_user_msg_age_min is None:
                    last_user_msg_age_min = age_min
        except discord.Forbidden:
            # conservative: never pulse if we can’t read history
            return False, "insufficient permissions"

        if last_user_msg_age_min is None:
            # none found → treat as very old
            last_user_msg_age_min = 10**6

        cond_gap = last_user_msg_age_min >= quiet_thresh
        cond_volume = count_in_window <= max_msgs

        if not cond_gap:
            return False, f"user gap {last_user_msg_age_min}m < {quiet_thresh}m"
        if not cond_volume:
            return False, f"window msgs {count_in_window} > {max_msgs}"

        return True, "quiet"


async def setup(bot: commands.Bot):
    await bot.add_cog(VoidPulseCog(bot))
