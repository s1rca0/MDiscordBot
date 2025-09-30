# cogs/void_pulse_cog.py
import os
import random
from datetime import datetime, timedelta
from typing import Optional, Tuple, List

import discord
from discord import app_commands
from discord.ext import commands

# ---------------------------------------------------------------------------
# Small local helpers (avoid missing imports across variants)
# ---------------------------------------------------------------------------

def mk_embed(title: str, desc: str) -> discord.Embed:
    return discord.Embed(title=title, description=desc, color=discord.Color.dark_teal())

def speak(text: str) -> str:
    """Wrapper to keep compatibility with earlier voice helpers."""
    return text

def _jittered_hours(base: int, jitter: int) -> int:
    if jitter <= 0:
        return base
    lo = max(1, base - jitter)
    hi = base + jitter
    return random.randint(lo, hi)

def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")

def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(str(raw).strip())
    except Exception:
        return default

# ---------------------------------------------------------------------------
# Optional AI provider (guarded)
# ---------------------------------------------------------------------------

def _maybe_ai_line() -> Optional[str]:
    """Return an AI-crafted line if enabled and provider available; else None."""
    if not _bool_env("VOID_BROADCAST_AI", False):
        return None
    try:
        # ai_provider.py expected to offer: get_client() and simple generate()
        # (Your repo includes ai_provider.py; this import is guarded.)
        from ai_provider import get_client  # type: ignore
    except Exception:
        return None

    tone = os.getenv("VOID_BROADCAST_AI_TONE", "cryptic").strip()
    extra_prompt = os.getenv("VOID_BROADCAST_PROMPT", "").strip()

    sys_prompt = (
        "You are M.O.R.P.H.E.U.S., voice of Veritas / VEI. "
        "Write a single, short, atmospheric line suitable for a Discord broadcast when the server is quiet. "
        "Constraints: 1 sentence, 8–22 words, no hashtags, no @mentions, no emojis. "
        f"Style/tone: {tone}. Themes: Veritas, VEI Network values (truth, civility, signal over noise), "
        "The Matrix mythos, gentle call-to-action to respond. Avoid commands; invite curiosity."
    )
    if extra_prompt:
        sys_prompt += f" Additional guidance: {extra_prompt}"

    try:
        client = get_client()
        text = client.generate(system=sys_prompt, prompt="Produce the line only.", max_tokens=60).strip()
        # basic safety/formatting guardrails
        text = text.replace("\n", " ").strip()
        if not text:
            return None
        if len(text) > 240:
            text = text[:240].rstrip()
        return text
    except Exception:
        return None

# ---------------------------------------------------------------------------
# File lines support
# ---------------------------------------------------------------------------

_LINES_PATH = os.path.join("data", "void_lines.txt")

def _load_void_lines() -> List[str]:
    try:
        with open(_LINES_PATH, "r", encoding="utf-8") as f:
            return [ln.strip() for ln in f.readlines() if ln.strip()]
    except Exception:
        return []

# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class VoidPulseCog(commands.Cog, name="Void Pulse"):
    """
    Posts an atmospheric ping in a chosen channel when the server has been quiet.
    Keeps Morpheus' 'alive' vibe without spamming.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Enable / channel (new + legacy names)
        self.enabled = _bool_env("VOID_BROADCAST_ENABLE", _bool_env("VOIDPULSE_ENABLE", True))

        chan_raw = os.getenv("VOID_BROADCAST_CHANNEL_ID", os.getenv("VOID_CHANNEL_ID", "0"))
        try:
            self.channel_id = int(chan_raw or "0")
        except Exception:
            self.channel_id = 0

        # Cooldown & quiet-window config (support both *_HOUR and *_HOURS)
        self.cooldown_hours = _int_env("VOIDPULSE_COOLDOWN_HOURS",
                               _int_env("VOIDPULSE_COOLDOWN_HOUR", 36))
        self.cooldown_jitter = _int_env("VOIDPULSE_COOLDOWN_JITTER", 45)  # +/- hours

        # Quiet rules
        self.quiet_threshold_min = _int_env("VOIDPULSE_QUIET_THRESHOLD_MIN", 180)
        self.scan_window_min     = _int_env("VOIDPULSE_SCAN_WINDOW_MIN", 120)
        self.scan_window_max_msgs= _int_env("VOIDPULSE_SCAN_WINDOW_MAXMSGS", 6)
        self.ignore_bots         = _bool_env("VOIDPULSE_IGNORE_BOTS", True)

        # Last pulse (cooldown)
        self.last_pulse_ts: Optional[datetime] = None

    # ---------- Admin commands ----------

    @app_commands.command(name="voidpulse_status",
                          description="Show current VoidPulse configuration and recent state.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def voidpulse_status(self, interaction: discord.Interaction):
        ch = self._channel(interaction.guild)
        last_unix = int(self.last_pulse_ts.timestamp()) if self.last_pulse_ts else "—"
        desc = (
            f"**Enabled:** `{self.enabled}`\n"
            f"**Channel:** {ch.mention if ch else '`unset`'}\n"
            f"**Cooldown (hours):** `{self.cooldown_hours}` | **Jitter (hours):** `{self.cooldown_jitter}`\n"
            f"**Quiet threshold (min):** `{self.quiet_threshold_min}`\n"
            f"**Window (min):** `{self.scan_window_min}`, **Quiet if ≤ {self.scan_window_max_msgs} msgs**\n"
            f"**Ignore bot msgs:** `{self.ignore_bots}`\n"
            f"**AI mode:** `{_bool_env('VOID_BROADCAST_AI', False)}` (tone=`{os.getenv('VOID_BROADCAST_AI_TONE','cryptic')}`)\n"
            f"**Last pulse:** `{last_unix}` (unix)\n"
            "_No message content is stored—only counts/timestamps._"
        )
        await interaction.response.send_message(embed=mk_embed("VoidPulse", desc), ephemeral=True)

    @app_commands.command(name="voidpulse_set_channel",
                          description="Set the channel used for VoidPulse.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def voidpulse_set_channel(self, interaction: discord.Interaction,
                                    channel: discord.TextChannel):
        self.channel_id = channel.id
        await interaction.response.send_message(
            embed=mk_embed("VoidPulse", f"Channel set to {channel.mention}"), ephemeral=True
        )

    @app_commands.command(name="voidpulse_toggle",
                          description="Enable/disable VoidPulse.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def voidpulse_toggle(self, interaction: discord.Interaction,
                               enable: Optional[bool] = None):
        self.enabled = (not self.enabled) if enable is None else bool(enable)
        state = "enabled" if self.enabled else "disabled"
        await interaction.response.send_message(
            embed=mk_embed("VoidPulse", f"VoidPulse **{state}**."), ephemeral=True
        )

    @app_commands.command(name="voidpulse_nudge",
                          description="Force a one-off pulse check now.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def voidpulse_nudge(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=mk_embed("VoidPulse", "Attempting a pulse…"),
                                                ephemeral=True)
        ok, why = await self._maybe_pulse(interaction.guild)
        msg = "Done." if ok else f"No pulse: {why or 'conditions not met'}"
        await interaction.followup.send(embed=mk_embed("VoidPulse", msg), ephemeral=True)

    # ---------- Internals ----------

    def _channel(self, guild: Optional[discord.Guild]) -> Optional[discord.TextChannel]:
        if not guild or not self.channel_id:
            return None
        ch = guild.get_channel(self.channel_id)
        return ch if isinstance(ch, discord.TextChannel) else None

    async def _maybe_pulse(self, guild: Optional[discord.Guild]) -> Tuple[bool, Optional[str]]:
        if not guild or not self.enabled:
            return False, "disabled"

        ch = self._channel(guild)
        if not ch:
            return False, "no channel set"

        # Cooldown
        if self.last_pulse_ts:
            elapsed = (datetime.utcnow() - self.last_pulse_ts).total_seconds() / 3600.0
            if elapsed < _jittered_hours(self.cooldown_hours, self.cooldown_jitter):
                return False, "cooldown"

        ok, why = await self._is_quiet(ch)
        if not ok:
            return False, why

        # Message selection:
        # 1) AI (if enabled & available)  2) file line  3) fallback static line
        msg = _maybe_ai_line()
        if not msg:
            lines = _load_void_lines()  # hot-reload each pulse so file edits apply without restart
            if lines:
                msg = random.choice(lines)
            else:
                msg = "[signal] The Void hums tonight. Those who listen may hear the door unlatch."

        await ch.send(speak(msg))
        self.last_pulse_ts = datetime.utcnow()
        return True, None

    async def _is_quiet(self, channel: discord.TextChannel) -> Tuple[bool, str]:
        """
        Quiet == (last non-bot user message older than quiet_threshold)
                 AND (message count within scan window <= max msgs)
        """
        quiet_thresh = self.quiet_threshold_min
        window_min = self.scan_window_min
        max_msgs = self.scan_window_max_msgs

        now = datetime.utcnow()
        since_ts = now - timedelta(minutes=max(quiet_thresh, window_min))

        last_user_msg_age_min: Optional[int] = None
        count_in_window = 0

        try:
            async for msg in channel.history(limit=200, after=since_ts, oldest_first=False):
                # Normalize to naive UTC minutes
                created = msg.created_at
                if created.tzinfo is not None:
                    created = created.astimezone(tz=None).replace(tzinfo=None)
                age_min = int(((now - created).total_seconds()) // 60)

                # Window volume
                if age_min <= window_min:
                    # Optionally ignore bot traffic
                    if self.ignore_bots and getattr(msg.author, "bot", False):
                        pass
                    else:
                        count_in_window += 1

                # Track most recent non-bot human message for quiet-gap
                if (not getattr(msg.author, "bot", False)) and last_user_msg_age_min is None:
                    last_user_msg_age_min = age_min
        except discord.Forbidden:
            # conservative: never pulse if we can’t read history
            return False, "insufficient permissions"

        if last_user_msg_age_min is None:
            last_user_msg_age_min = 10**6  # treat as very old if none found

        cond_gap = last_user_msg_age_min >= quiet_thresh
        cond_volume = count_in_window <= max_msgs

        if not cond_gap:
            return False, f"user gap {last_user_msg_age_min}m < {quiet_thresh}m"
        if not cond_volume:
            return False, f"window msgs {count_in_window} > {max_msgs}"

        return True, "quiet"


async def setup(bot: commands.Bot):
    await bot.add_cog(VoidPulseCog(bot))
