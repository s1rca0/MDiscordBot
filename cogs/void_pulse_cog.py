# cogs/void_pulse_cog.py
import os
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Tuple, List

import discord
from discord.ext import commands
from discord import app_commands


# --- Small local helpers (avoid missing imports) -----------------------------
def mk_embed(title: str, desc: str) -> discord.Embed:
    return discord.Embed(title=title, description=desc, color=discord.Color.dark_teal())

def speak(text: str) -> str:
    """Light wrapper to keep compatibility with earlier voice helpers."""
    return text

def _jittered_hours(base: int, jitter: int) -> int:
    if jitter <= 0:
        return base
    lo = max(1, base - jitter)
    hi = base + jitter
    return random.randint(lo, hi)


# --- Thematic defaults if no env/file provided --------------------------------
DEFAULT_LINES: List[str] = [
    "[signal] The Void hums tonight. Those who listen may hear the door unlatch.",
    "[signal] Static recedes. Pattern emerges. Query: who remains at the console?",
    "[signal] Order requests a witness. If you’re awake, reply with a coordinate.",
    "[signal] Veritas whispers through the noise: calibrate, align, proceed.",
    "[signal] The Construct idles. A single keystroke could change its state.",
    "[signal] In the dark, a green cursor blinks. Input awaits.",
]


class VoidPulseCog(commands.Cog, name="Void Pulse"):
    """
    Posts an atmospheric ping in a chosen channel when the server has been quiet.
    Keeps Morpheus' "alive" vibe without spamming.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # ---- Railway / env configuration (with backwards-compatible fallbacks)
        enabled_raw = os.getenv("VOID_BROADCAST_ENABLE", os.getenv("VOIDPULSE_ENABLE", "true"))
        self.enabled = str(enabled_raw).lower() in ("1", "true", "yes", "on")

        chan_raw = os.getenv("VOID_BROADCAST_CHANNEL_ID", os.getenv("VOID_CHANNEL_ID", "0"))
        try:
            self.channel_id = int(chan_raw)
        except (TypeError, ValueError):
            self.channel_id = 0

        self.dry_run = str(os.getenv("VOIDPULSE_DRY_RUN", "false")).lower() in ("1", "true", "yes", "on")

        self.cooldown_hours = int(os.getenv("VOIDPULSE_COOLDOWN_HOURS", "36"))
        self.cooldown_jitter = int(os.getenv("VOIDPULSE_COOLDOWN_JITTER", "45"))  # +/- hours

        # last non-bot msg must be older than this many minutes
        self.quiet_threshold_min = int(os.getenv("VOIDPULSE_QUIET_THRESHOLD_MIN", "180"))

        # traffic window to count messages
        self.scan_window_min = int(os.getenv("VOIDPULSE_SCAN_WINDOW_MIN", "120"))
        self.scan_window_max_msgs = int(os.getenv("VOIDPULSE_SCAN_WINDOW_MAXMSGS", "6"))

        # ignore bot messages for the volume window?
        self.ignore_bots_in_window = str(os.getenv("VOIDPULSE_IGNORE_BOTS", "true")).lower() in ("1", "true", "yes", "on")

        # messaging pool
        self.lines = self._load_lines()

        self.last_pulse_ts: Optional[datetime] = None

    # ---------- Admin commands ----------
    @app_commands.command(name="voidpulse_status", description="Show current VoidPulse configuration and recent state.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def voidpulse_status(self, interaction: discord.Interaction):
        ch = self._channel(interaction.guild)
        last_unix = int(self.last_pulse_ts.timestamp()) if self.last_pulse_ts else "—"
        desc = (
            f"**Enabled:** `{self.enabled}` | **Dry-run:** `{self.dry_run}`\n"
            f"**Channel:** {ch.mention if ch else '`unset`'} (id `{self.channel_id}`)\n"
            f"**Cooldown (h):** `{self.cooldown_hours}` | **Jitter (h):** `{self.cooldown_jitter}`\n"
            f"**Quiet threshold (min):** `{self.quiet_threshold_min}`\n"
            f"**Window (min):** `{self.scan_window_min}`, **Quiet if ≤ {self.scan_window_max_msgs} msgs** "
            f"(ignore_bots=`{self.ignore_bots_in_window}`)\n"
            f"**Lines loaded:** `{len(self.lines)}`\n"
            f"**Last pulse:** `{last_unix}` (unix)\n"
            "_No message content is stored—only counts/timestamps._"
        )
        await interaction.response.send_message(embed=mk_embed("VoidPulse", desc), ephemeral=True)

    @app_commands.command(name="voidpulse_set_channel", description="Set the channel used for VoidPulse.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def voidpulse_set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        self.channel_id = channel.id
        await interaction.response.send_message(
            embed=mk_embed("VoidPulse", f"Channel set to {channel.mention}"), ephemeral=True
        )

    @app_commands.command(name="voidpulse_toggle", description="Enable/disable VoidPulse.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def voidpulse_toggle(self, interaction: discord.Interaction, enable: Optional[bool] = None):
        self.enabled = (not self.enabled) if enable is None else bool(enable)
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
    def _load_lines(self) -> List[str]:
        # 1) ENV: VOID_BROADCAST_LINES="line A|line B|line C"
        env_lines = os.getenv("VOID_BROADCAST_LINES", "").strip()
        parts: List[str] = []
        if env_lines:
            parts = [p.strip() for p in env_lines.split("|") if p.strip()]

        # 2) File: data/void_lines.txt (one line per message)
        if not parts:
            p = Path("data/void_lines.txt")
            if p.exists():
                try:
                    with p.open("r", encoding="utf-8") as f:
                        parts = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
                except Exception:
                    parts = []

        # 3) Fallback to defaults
        return parts if parts else DEFAULT_LINES[:]

    def _channel(self, guild: Optional[discord.Guild]) -> Optional[discord.TextChannel]:
        if not guild or not self.channel_id:
            return None
        ch = guild.get_channel(self.channel_id)
        if isinstance(ch, discord.TextChannel):
            return ch
        return None

    async def _maybe_pulse(self, guild: Optional[discord.Guild]) -> Tuple[bool, Optional[str]]:
        if not guild or not self.enabled:
            return False, "disabled"

        ch = self._channel(guild)
        if not ch:
            return False, "no channel set"

        # If the very last message in the channel is from THIS bot, don't immediately pulse again
        try:
            last = await ch.history(limit=1).flatten()
            if last:
                lm = last[0]
                if lm.author.id == self.bot.user.id:
                    return False, "last message is mine"
        except discord.Forbidden:
            return False, "insufficient permissions (read history)"

        # Cooldown
        if self.last_pulse_ts:
            elapsed_h = (datetime.utcnow() - self.last_pulse_ts).total_seconds() / 3600.0
            if elapsed_h < _jittered_hours(self.cooldown_hours, self.cooldown_jitter):
                return False, "cooldown"

        ok, why = await self._is_quiet(ch)
        if not ok:
            return False, why

        # Post the “alive” signal
        line = random.choice(self.lines)
        if self.dry_run:
            # record the time anyway so we don't spam nudges during tests
            self.last_pulse_ts = datetime.utcnow()
            return False, f"dry-run: would send -> {line}"

        await ch.send(speak(line))
        self.last_pulse_ts = datetime.utcnow()
        return True, None

    async def _is_quiet(self, channel: discord.TextChannel) -> Tuple[bool, str]:
        """
        Quiet == (last non-bot user message older than quiet_threshold)
                 AND (message count within scan window <= max msgs) [optionally ignoring bot msgs]
        """
        quiet_thresh = self.quiet_threshold_min
        window_min = self.scan_window_min
        max_msgs = self.scan_window_max_msgs
        ignore_bots = self.ignore_bots_in_window

        now = datetime.utcnow()
        since_ts = now - timedelta(minutes=max(quiet_thresh, window_min))

        last_user_msg_age_min: Optional[int] = None
        count_in_window = 0

        try:
            async for msg in channel.history(limit=200, after=since_ts, oldest_first=False):
                msg_age_min = int(((now - msg.created_at.replace(tzinfo=None)).total_seconds()) // 60)

                # Count window volume
                if msg_age_min <= window_min:
                    if ignore_bots:
                        if not msg.author.bot:
                            count_in_window += 1
                    else:
                        count_in_window += 1

                # Track most recent non-bot author age for quiet threshold
                if (not msg.author.bot) and last_user_msg_age_min is None:
                    last_user_msg_age_min = msg_age_min

        except discord.Forbidden:
            # conservative: never pulse if we can’t read history
            return False, "insufficient permissions (history)"

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
