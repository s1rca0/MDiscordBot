import os
import json
import time
import random
from typing import Dict, Optional, List

import discord
from discord.ext import commands, tasks
from discord import app_commands

DATA_DIR = "data"
STATE_PATH = os.path.join(DATA_DIR, "void_pulse_state.json")
GCFG_PATH  = os.path.join(DATA_DIR, "guild_config.json")  # reuse if present

def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name, str(default))
    return str(v).lower() in ("1", "true", "yes", "y", "on")

OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0") or 0)

# --------- Defaults / env overrides ----------
PULSE_ENABLE_DEFAULT         = _env_bool("VOID_PULSE_ENABLE", True)
MIN_QUIET_MINUTES_DEFAULT    = int(os.getenv("VOID_MIN_QUIET_MINUTES", "180"))  # 3h inactivity
MIN_GAP_HOURS_DEFAULT        = int(os.getenv("VOID_MIN_GAP_HOURS", "36"))       # 1.5 days between pulses
JITTER_MINUTES_DEFAULT       = int(os.getenv("VOID_JITTER_MINUTES", "45"))      # ± up to 45m
WINDOW_MINUTES_DEFAULT       = int(os.getenv("VOID_WINDOW_MINUTES", "120"))     # lookback window for “quiet”
MIN_MESSAGES_WINDOW_DEFAULT  = int(os.getenv("VOID_MIN_MESSAGES_WINDOW", "6"))  # if <= this, consider “quiet”
CHECK_EVERY_SECONDS          = int(os.getenv("VOID_CHECK_PERIOD_SEC", "300"))   # loop every 5m

MODLOG_CHANNEL_ID            = int(os.getenv("MODLOG_CHANNEL_ID", "0") or 0)

# Optional assets (we fall back gracefully)
ASSET_GIF_CANDIDATES = [
    # prefer your animated transmission if present
    "attached_assets/morpheus_transmission_v3.gif",
    "attached_assets/morpheus_transmission.gif",
]
ASSET_IMAGE_FALLBACK = "attached_assets/Morpheus_PFP.png"

# --------- tiny stores ----------
def _ensure_dir():
    if not os.path.isdir(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)

def _load_state() -> Dict:
    _ensure_dir()
    if not os.path.isfile(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_state(d: Dict):
    _ensure_dir()
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

def _load_gcfg() -> Dict:
    if not os.path.isfile(GCFG_PATH):
        return {}
    try:
        with open(GCFG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _set_gcfg(gid: int, patch: Dict):
    gcfg = _load_gcfg()
    g = gcfg.get(str(gid), {})
    g.update(patch)
    gcfg[str(gid)] = g
    _ensure_dir()
    with open(GCFG_PATH, "w", encoding="utf-8") as f:
        json.dump(gcfg, f, ensure_ascii=False, indent=2)

def _get_void_channel_id(gid: int) -> int:
    # precedence: env → guild_config.json “void_channel_id”
    env = int(os.getenv("VOID_CHANNEL_ID", "0") or 0)
    if env:
        return env
    g = _load_gcfg().get(str(gid), {})
    return int(g.get("void_channel_id", 0) or 0)

def _set_void_channel_id(gid: int, cid: int):
    _set_gcfg(gid, {"void_channel_id": int(cid)})

# --------- helpers ----------
def _is_admin_or_owner(user: discord.abc.User) -> bool:
    if OWNER_USER_ID and int(user.id) == int(OWNER_USER_ID):
        return True
    if isinstance(user, discord.Member):
        return bool(user.guild_permissions.administrator)
    return False

def _choose_asset() -> Optional[discord.File]:
    # Prefer first existing GIF; else fallback to image; else None
    try:
        for p in ASSET_GIF_CANDIDATES:
            if os.path.isfile(p):
                return discord.File(p, filename=os.path.basename(p))
        if os.path.isfile(ASSET_IMAGE_FALLBACK):
            return discord.File(ASSET_IMAGE_FALLBACK, filename=os.path.basename(ASSET_IMAGE_FALLBACK))
    except Exception:
        pass
    return None

PULSE_LINES: List[str] = [
    "⟂ signal breach: a thread in the multiverse tugged back. listen close.",
    "the Void hums. a door you’ve missed is half-open.",
    "static clears… {ping} do you hear that? HAVN isn’t far.",
    "a ripple crosses frames. someone just rewound fate.",
    "trace confirmed. a path to **HAVN** flickers, then fades. were you watching?",
    "Morpheus intercept: you’re not lost—just zoomed out. re-enter the frame.",
]

class VoidPulseCog(commands.Cog):
    """Posts a void transmission when #void goes quiet long enough, with jitter & cooldown."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._task_loop.start()

    def cog_unload(self):
        self._task_loop.cancel()

    @tasks.loop(seconds=CHECK_EVERY_SECONDS)
    async def _task_loop(self):
        # Iterate each guild the bot is in
        for guild in list(self.bot.guilds):
            try:
                await self._maybe_pulse(guild)
            except Exception as e:
                # soft log to modlog if configured
                if MODLOG_CHANNEL_ID:
                    chan = guild.get_channel(MODLOG_CHANNEL_ID)
                    if isinstance(chan, discord.TextChannel):
                        try:
                            await chan.send(f"VoidPulse error: `{e.__class__.__name__}`")
                        except Exception:
                            pass

    @_task_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    async def _maybe_pulse(self, guild: discord.Guild):
        gcfg = _load_gcfg().get(str(guild.id), {})
        enabled = bool(gcfg.get("void_pulse_enable", PULSE_ENABLE_DEFAULT))
        if not enabled:
            return

        void_id = _get_void_channel_id(guild.id)
        if not void_id:
            # Try find by name as a convenience
            void_chan = discord.utils.get(guild.text_channels, name="void")
        else:
            void_chan = guild.get_channel(void_id)

        if not isinstance(void_chan, discord.TextChannel):
            return

        # Permissions check
        me = guild.me
        if not me:
            return
        perms = void_chan.permissions_for(me)
        if not perms.read_message_history or not perms.send_messages:
            return

        now = time.time()
        state = _load_state()
        gstate = state.get(str(guild.id), {})
        last_ts = float(gstate.get("last_pulse_ts", 0))

        min_gap_hours   = int(gcfg.get("void_min_gap_hours", MIN_GAP_HOURS_DEFAULT))
        jitter_minutes  = int(gcfg.get("void_jitter_minutes", JITTER_MINUTES_DEFAULT))
        min_quiet_min   = int(gcfg.get("void_min_quiet_minutes", MIN_QUIET_MINUTES_DEFAULT))
        window_minutes  = int(gcfg.get("void_window_minutes", WINDOW_MINUTES_DEFAULT))
        min_msgs_needed = int(gcfg.get("void_min_messages_window", MIN_MESSAGES_WINDOW_DEFAULT))

        # Enforce cooldown
        if last_ts and (now - last_ts) < (min_gap_hours * 3600):
            return

        # Add jitter (unique per cycle) so pulses don't feel clockwork
        jitter = random.randint(-jitter_minutes, jitter_minutes) * 60
        if last_ts and (now - last_ts + jitter) < (min_gap_hours * 3600):
            return

        # Check channel activity
        cutoff_quiet = discord.utils.utcnow().timestamp() - (min_quiet_min * 60)
        cutoff_window = discord.utils.utcnow().timestamp() - (window_minutes * 60)

        # 1) Most recent message time
        try:
            async for msg in void_chan.history(limit=1, oldest_first=False):
                last_msg_ts = msg.created_at.timestamp()
                break
            else:
                last_msg_ts = 0.0
        except Exception:
            return

        # If recent chatter, skip
        if last_msg_ts and last_msg_ts > cutoff_quiet:
            return

        # 2) Count messages in the broader window
        msg_count = 0
        try:
            async for msg in void_chan.history(limit=400, oldest_first=False):
                if msg.created_at.timestamp() < cutoff_window:
                    break
                if msg.author.bot:
                    continue
                msg_count += 1
        except Exception:
            return

        if msg_count > min_msgs_needed:
            # window has enough activity; no pulse
            return

        # Compose the pulse
        line = random.choice(PULSE_LINES)
        # Optional: soft “ping” by mentioning the channel (no @everyone)
        content = line.format(ping=void_chan.mention)

        embed = discord.Embed(
            title="— transmission from the Void —",
            description=content,
            color=discord.Color.dark_teal()
        ).set_footer(text="signal strength: variable")

        file = _choose_asset()

        try:
            await void_chan.send(embed=embed, file=file if file else discord.utils.MISSING)
        except Exception:
            return

        # Persist last pulse time
        gstate["last_pulse_ts"] = now
        state[str(guild.id)] = gstate
        _save_state(state)

    # --------- slash commands ----------
    @app_commands.command(name="voidpulse_status", description="Show current Void pulse settings & last pulse.")
    async def voidpulse_status(self, inter: discord.Interaction):
        if inter.guild is None:
            await inter.response.send_message("Run in a server.", ephemeral=True)
            return
        gcfg = _load_gcfg().get(str(inter.guild.id), {})
        state = _load_state().get(str(inter.guild.id), {})
        last_ts = float(state.get("last_pulse_ts", 0))

        void_id = _get_void_channel_id(inter.guild.id)
        void_chan = inter.guild.get_channel(void_id) if void_id else discord.utils.get(inter.guild.text_channels, name="void")

        def gv(k, dft):
            return gcfg.get(k, dft)

        await inter.response.send_message(
            "**VoidPulse**\n"
            f"- Enabled: `{bool(gcfg.get('void_pulse_enable', PULSE_ENABLE_DEFAULT))}`\n"
            f"- Channel: {void_chan.mention if isinstance(void_chan, discord.TextChannel) else '(not set)'}\n"
            f"- Cooldown (hours): `{gv('void_min_gap_hours', MIN_GAP_HOURS_DEFAULT)}`  | Jitter (min): `{gv('void_jitter_minutes', JITTER_MINUTES_DEFAULT)}`\n"
            f"- Quiet threshold (min): `{gv('void_min_quiet_minutes', MIN_QUIET_MINUTES_DEFAULT)}`\n"
            f"- Window (min): `{gv('void_window_minutes', WINDOW_MINUTES_DEFAULT)}`, Quiet if ≤ `{gv('void_min_messages_window', MIN_MESSAGES_WINDOW_DEFAULT)}` msgs\n"
            f"- Last pulse: `{int(last_ts)}` (unix)\n"
            "_No message content is stored—only counts/timestamps._",
            ephemeral=True
        )

    @app_commands.command(name="voidpulse_toggle", description="(Admin/Owner) Enable/disable Void pulse.")
    async def voidpulse_toggle(self, inter: discord.Interaction, enabled: bool):
        if inter.guild is None:
            await inter.response.send_message("Run in a server.", ephemeral=True)
            return
        if not _is_admin_or_owner(inter.user):
            await inter.response.send_message("Admin/Owner only.", ephemeral=True)
            return
        _set_gcfg(inter.guild.id, {"void_pulse_enable": bool(enabled)})
        await inter.response.send_message(f"VoidPulse enabled: `{enabled}`", ephemeral=True)

    @app_commands.command(name="voidpulse_set_channel", description="(Admin/Owner) Set the #void channel to watch.")
    async def voidpulse_set_channel(self, inter: discord.Interaction, channel: discord.TextChannel):
        if inter.guild is None:
            await inter.response.send_message("Run in a server.", ephemeral=True)
            return
        if not _is_admin_or_owner(inter.user):
            await inter.response.send_message("Admin/Owner only.", ephemeral=True)
            return
        _set_void_channel_id(inter.guild.id, channel.id)
        await inter.response.send_message(f"VoidPulse channel set to {channel.mention}", ephemeral=True)

    @app_commands.command(name="voidpulse_nudge", description="(Admin/Owner) Attempt a pulse now (ignores cooldown).")
    async def voidpulse_nudge(self, inter: discord.Interaction):
        if inter.guild is None:
            await inter.response.send_message("Run in a server.", ephemeral=True)
            return
        if not _is_admin_or_owner(inter.user):
            await inter.response.send_message("Admin/Owner only.", ephemeral=True)
            return
        # Force: clear last_pulse_ts then try once
        state = _load_state()
        gstate = state.get(str(inter.guild.id), {})
        gstate["last_pulse_ts"] = 0
        state[str(inter.guild.id)] = gstate
        _save_state(state)
        await inter.response.send_message("Attempting a pulse…", ephemeral=True)
        try:
            await self._maybe_pulse(inter.guild)
            await inter.followup.send("Done.", ephemeral=True)
        except Exception as e:
            await inter.followup.send(f"Failed: {e.__class__.__name__}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(VoidPulseCog(bot))