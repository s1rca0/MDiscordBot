# cogs/moderation_cog.py
from __future__ import annotations

import os
import re
import json
import time
from datetime import timedelta
from typing import Optional, Dict, Any, List, Tuple

import discord
from discord.ext import commands
from discord import app_commands

# --- Safe config helpers (prefer cfg if present; fall back to env; then default) ---
try:
    from config import cfg as _cfg  # optional; code must not assume attributes exist
except Exception:
    _cfg = None  # type: ignore

def _get_str(name: str, default: str = "") -> str:
    if _cfg is not None:
        v = getattr(_cfg, name, None)
        if isinstance(v, str) and v.strip():
            return v.strip()
    v = os.getenv(name)
    return v.strip() if isinstance(v, str) and v.strip() else default

def _get_int(name: str, default: int = 0) -> int:
    if _cfg is not None:
        v = getattr(_cfg, name, None)
        try:
            if v is not None:
                return int(v)
        except Exception:
            pass
    try:
        envv = os.getenv(name)
        return int(envv) if envv is not None and envv != "" else default
    except Exception:
        return default

def _get_bool(name: str, default: bool = False) -> bool:
    if _cfg is not None:
        v = getattr(_cfg, name, None)
        if isinstance(v, bool):
            return v
        if isinstance(v, (str, int)):
            s = str(v).strip().lower()
            if s in {"1", "true", "yes", "on"}:
                return True
            if s in {"0", "false", "no", "off"}:
                return False
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}

# --- Moderation defaults (read once at import) ---
ALLOW_INVITES_DEFAULT = _get_bool("ALLOW_INVITES", True)  # whether to allow invite links in chat
MAX_MENTIONS_DEFAULT  = _get_int("MAX_MENTIONS", 5)       # > this count triggers a strike
SPAM_WINDOW_SECS_DEF  = _get_int("SPAM_WINDOW_SECS", 10)  # rolling window for spam detector
SPAM_MAX_MSGS_DEF     = _get_int("SPAM_MAX_MSGS", 5)      # max msgs allowed in the window
AUTOMOD_REGEX_RAW     = _get_str("AUTOMOD_REGEX", "")     # comma-separated regex list
STRIKE_THRESHOLDS_RAW = _get_str("STRIKE_THRESHOLDS", "3:timeout:30,5:kick,7:ban")

DATA_DIR     = "data"
MOD_CFG_PATH = os.path.join(DATA_DIR, "mod_config.json")
WARNS_PATH   = os.path.join(DATA_DIR, "warnings.json")
STRIKES_PATH = os.path.join(DATA_DIR, "strikes.json")

def _load_json(path: str, fallback):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback

def _save_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def _safe_str(x: Any, limit=512) -> str:
    s = str(x)
    return (s[:limit] + "…") if len(s) > limit else s

def _parse_regex_list(raw: str) -> List[str]:
    return [p.strip() for p in (raw or "").split(",") if p.strip()]

def _parse_strike_policy(s: str) -> List[Tuple[int, str, Optional[int]]]:
    """
    Parse STRIKE_THRESHOLDS like:  "3:timeout:30,5:kick,7:ban"
    -> list of (threshold:int, action:str, minutes:int|None)
    """
    out: List[Tuple[int, str, Optional[int]]] = []
    for part in filter(None, (s or "").split(",")):
        pieces = [p.strip() for p in part.split(":")]
        if len(pieces) < 2:
            continue
        try:
            thr = int(pieces[0])
        except Exception:
            continue
        action = pieces[1].lower()
        mins = None
        if action == "timeout" and len(pieces) >= 3:
            try:
                mins = int(pieces[2])
            except Exception:
                mins = 5
        out.append((thr, action, mins))
    out.sort(key=lambda x: x[0])
    return out

DEFAULT_AUTOMOD_CFG = {
    "log_channel_id": 0,
    "allow_invites": ALLOW_INVITES_DEFAULT,
    "max_mentions": MAX_MENTIONS_DEFAULT,
    "spam_window_secs": SPAM_WINDOW_SECS_DEF,
    "spam_max_msgs": SPAM_MAX_MSGS_DEF,
    "regex_list": _parse_regex_list(AUTOMOD_REGEX_RAW),
}

STRIKE_RULES = _parse_strike_policy(STRIKE_THRESHOLDS_RAW)

class ModerationCog(commands.Cog, name="Moderation"):
    """
    Core moderation + lightweight automod.
      • Automod: invite links (optional), regex blacklist, excessive mentions, basic spam
      • Warnings & strikes with strike policy (timeout/kick/ban)
      • Log channel, purge, slowmode, lock/unlock, warn/warnings/clear, mute/unmute, kick/ban/unban
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Load or seed config/state
        self.cfg: Dict[str, Any] = _load_json(MOD_CFG_PATH, DEFAULT_AUTOMOD_CFG.copy())
        # Ensure required keys exist (in case file is older)
        for k, v in DEFAULT_AUTOMOD_CFG.items():
            self.cfg.setdefault(k, v)

        self.warns: Dict[str, Dict[str, Any]]   = _load_json(WARNS_PATH, {})
        self.strikes: Dict[str, Dict[str, int]] = _load_json(STRIKES_PATH, {})

        # Spam tracking: user_id -> [timestamps]
        self._spam_buckets: Dict[int, List[float]] = {}

        # Compile regexes safely
        self._regexes: List[re.Pattern[str]] = []
        for pat in self.cfg.get("regex_list", []):
            try:
                self._regexes.append(re.compile(pat))
            except re.error:
                # skip invalid patterns silently
                pass

    # ---------- Utilities ----------
    def _log_channel(self, guild: Optional[discord.Guild]) -> Optional[discord.TextChannel]:
        if not guild:
            return None
        ch_id = int(self.cfg.get("log_channel_id", 0) or 0)
        ch = guild.get_channel(ch_id) if ch_id else None
        return ch if isinstance(ch, discord.TextChannel) else None

    async def _log(self, guild: Optional[discord.Guild], title: str, desc: str):
        ch = self._log_channel(guild)
        if not ch:
            return
        try:
            emb = discord.Embed(title=title, description=desc, color=discord.Color.orange())
            emb.timestamp = discord.utils.utcnow()
            await ch.send(embed=emb)
        except Exception:
            pass

    def _add_warning(self, guild_id: int, user_id: int, reason: str) -> int:
        gkey, ukey = str(guild_id), str(user_id)
        self.warns.setdefault(gkey, {}).setdefault(ukey, []).append(
            {"ts": int(time.time()), "reason": reason}
        )
        _save_json(WARNS_PATH, self.warns)

        current = self.strikes.setdefault(gkey, {}).get(ukey, 0) + 1
        self.strikes[gkey][ukey] = current
        _save_json(STRIKES_PATH, self.strikes)
        return current

    def _get_warnings(self, guild_id: int, user_id: int):
        return self.warns.get(str(guild_id), {}).get(str(user_id), [])

    def _clear_warnings(self, guild_id: int, user_id: int):
        self.warns.get(str(guild_id), {}).pop(str(user_id), None)
        _save_json(WARNS_PATH, self.warns)

    def _get_strikes(self, guild_id: int, user_id: int) -> int:
        return self.strikes.get(str(guild_id), {}).get(str(user_id), 0)

    def _clear_strikes(self, guild_id: int, user_id: int):
        self.strikes.get(str(guild_id), {}).pop(str(user_id), None)
        _save_json(STRIKES_PATH, self.strikes)

    async def _apply_strike_policy(self, member: discord.Member, strikes_now: int, reason: str):
        """
        On reaching N strikes, apply the highest threshold action <= N.
        """
        rule: Optional[Tuple[int, str, Optional[int]]] = None
        for thr, action, mins in STRIKE_RULES:
            if strikes_now >= thr:
                rule = (thr, action, mins)
        if not rule:
            return None

        _, action, mins = rule
        guild = member.guild
        actor = f"AutoMod (strikes={strikes_now})"

        if action == "warn":
            return "warn"

        if action == "timeout":
            try:
                until = discord.utils.utcnow() + timedelta(minutes=mins or 5)
                await member.timeout(until, reason=f"{actor}: {reason}")
                await self._log(guild, "Strike policy: timeout",
                                f"User: {member.mention}\nMinutes: {mins}\nReason: {_safe_str(reason)}")
                return "timeout"
            except discord.Forbidden:
                await self._log(guild, "Strike policy FAILED: timeout (forbidden)",
                                f"User: {member.mention}\nMinutes: {mins}")
                return "timeout_failed"

        if action == "kick":
            try:
                await member.kick(reason=f"{actor}: {reason}")
                await self._log(guild, "Strike policy: kick",
                                f"User: {member}\nReason: {_safe_str(reason)}")
                return "kick"
            except discord.Forbidden:
                await self._log(guild, "Strike policy FAILED: kick (forbidden)",
                                f"User: {member}")
                return "kick_failed"

        if action == "ban":
            try:
                await member.ban(reason=f"{actor}: {reason}", delete_message_days=0)
                await self._log(guild, "Strike policy: ban",
                                f"User: {member}\nReason: {_safe_str(reason)}")
                return "ban"
            except discord.Forbidden:
                await self._log(guild, "Strike policy FAILED: ban (forbidden)",
                                f"User: {member}")
                return "ban_failed"

        return None

    async def _maybe_policy(self, author: discord.Member | discord.User, guild: discord.Guild, strikes: int, reason: str):
        # Try to resolve a full Member object before applying server-side actions
        member: Optional[discord.Member] = guild.get_member(author.id)
        if member is None:
            try:
                member = await guild.fetch_member(author.id)
            except Exception:
                member = None
        if member:
            await self._apply_strike_policy(member, strikes, reason)

    # ---------- Automod ----------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ignore bots & DMs
        if message.author.bot or message.guild is None:
            return

        content = message.content or ""
        content_l = content.lower()

        # 1) Invite links (if disallowed)
        if not bool(self.cfg.get("allow_invites", True)):
            if ("discord.gg/" in content_l) or ("discord.com/invite/" in content_l):
                try:
                    await message.delete()
                except Exception:
                    pass
                strikes = self._add_warning(message.guild.id, message.author.id, "Invite link")
                await self._log(
                    message.guild,
                    "AutoMod: Invite removed",
                    f"Author: {message.author.mention}\nChannel: {message.channel.mention}\n"
                    f"Strikes: {strikes}\nContent: {_safe_str(content)}"
                )
                await self._maybe_policy(message.author, message.guild, strikes, "Invite link")
                return

        # 2) Regex blacklist
        for rx in self._regexes:
            if rx.search(content):
                try:
                    await message.delete()
                except Exception:
                    pass
                strikes = self._add_warning(message.guild.id, message.author.id, f"Blacklist: /{rx.pattern}/")
                await self._log(
                    message.guild,
                    "AutoMod: Blacklist hit",
                    f"Author: {message.author.mention}\nChannel: {message.channel.mention}\n"
                    f"Strikes: {strikes}\nPattern: `{rx.pattern}`"
                )
                await self._maybe_policy(message.author, message.guild, strikes, f"Blacklist: /{rx.pattern}/")
                return

        # 3) Excessive mentions
        max_mentions = int(self.cfg.get("max_mentions", MAX_MENTIONS_DEFAULT))
        if max_mentions > 0 and len(message.mentions) > max_mentions:
            strikes = self._add_warning(message.guild.id, message.author.id, f"Excessive mentions: {len(message.mentions)}")
            await self._log(
                message.guild,
                "AutoMod: Excessive mentions",
                f"Author: {message.author.mention}\nMentions: {len(message.mentions)}\n"
                f"Channel: {message.channel.mention}\nStrikes: {strikes}"
            )
            await self._maybe_policy(message.author, message.guild, strikes, "Excessive mentions")

        # 4) Basic spam rate limit
        window = int(self.cfg.get("spam_window_secs", SPAM_WINDOW_SECS_DEF))
        max_msgs = int(self.cfg.get("spam_max_msgs", SPAM_MAX_MSGS_DEF))
        if window > 0 and max_msgs > 0:
            now = time.time()
            bucket = self._spam_buckets.setdefault(message.author.id, [])
            bucket.append(now)
            self._spam_buckets[message.author.id] = [t for t in bucket if now - t <= window]
            if len(self._spam_buckets[message.author.id]) > max_msgs:
                strikes = self._add_warning(message.guild.id, message.author.id, "Spam detected")
                await self._log(
                    message.guild,
                    "AutoMod: Spam detected",
                    f"Author: {message.author.mention}\nChannel: {message.channel.mention}\n"
                    f"Window: {window}s > {max_msgs} msgs\nStrikes: {strikes}"
                )
                await self._maybe_policy(message.author, message.guild, strikes, "Spam")

    # ---------- Admin/Owner config ----------
    @commands.hybrid_command(name="setlogchannel", description="(Admin) Set this channel for moderation logs")
    @commands.has_permissions(manage_guild=True)
    async def setlogchannel(self, ctx: commands.Context):
        if ctx.guild is None:
            await ctx.reply("Run this in a server channel.", mention_author=False)
            return
        self.cfg["log_channel_id"] = ctx.channel.id
        _save_json(MOD_CFG_PATH, self.cfg)
        await ctx.reply(f"✅ Log channel set to {ctx.channel.mention}", mention_author=False)

    @commands.hybrid_command(name="modconfig", description="(Admin) View or update automod config")
    @commands.has_permissions(manage_guild=True)
    async def modconfig(self, ctx: commands.Context, key: Optional[str] = None, value: Optional[str] = None):
        """
        View current config:
          /modconfig
        Update examples:
          /modconfig key:allow_invites value:true
          /modconfig key:max_mentions value:8
          /modconfig key:spam_window_secs value:12
          /modconfig key:spam_max_msgs value:6
        """
        if key is None:
            pretty = json.dumps(self.cfg, indent=2)
            await ctx.reply(f"**Current automod config:**\n```json\n{pretty}\n```", mention_author=False)
            return

        key = key.strip()
        valid = {"allow_invites", "max_mentions", "spam_window_secs", "spam_max_msgs"}
        if key not in valid:
            await ctx.reply(f"Unknown key. Valid: {', '.join(sorted(valid))}", mention_author=False)
            return

        v_out: Any
        if key == "allow_invites":
            if value is None:
                await ctx.reply("Value required: true/false", mention_author=False); return
            v_out = str(value).lower() in {"1", "true", "yes", "y", "on"}
        else:
            try:
                v_out = int(value)
            except Exception:
                await ctx.reply("Value must be an integer.", mention_author=False)
                return

        self.cfg[key] = v_out
        _save_json(MOD_CFG_PATH, self.cfg)
        await ctx.reply(f"✅ Updated `{key}` to `{v_out}`", mention_author=False)

    # ---------- Message management ----------
    @commands.hybrid_command(name="purge", description="(Mod) Bulk delete N messages")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx: commands.Context, count: commands.Range[int, 1, 200]):
        deleted = await ctx.channel.purge(limit=count + 1)  # +1 to remove the command message
        await self._log(ctx.guild, "Purge",
                        f"Channel: {ctx.channel.mention}\nDeleted: {len(deleted) - 1} msgs\nBy: {ctx.author.mention}")
        try:
            await ctx.send(f"🧹 Deleted {len(deleted) - 1} messages.", delete_after=5)
        except Exception:
            pass

    @commands.hybrid_command(name="slowmode", description="(Mod) Set slowmode seconds (0 to disable)")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx: commands.Context, seconds: commands.Range[int, 0, 21600] = 0):
        await ctx.channel.edit(slowmode_delay=seconds)
        await self._log(ctx.guild, "Slowmode",
                        f"Channel: {ctx.channel.mention}\nSlowmode: {seconds}s\nBy: {ctx.author.mention}")
        await ctx.reply(f"🐢 Slowmode set to **{seconds}s** here.", mention_author=False)

    @commands.hybrid_command(name="lock", description="(Mod) Lock this channel for @everyone")
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx: commands.Context, reason: Optional[str] = None):
        overwrites = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrites.send_messages = False
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrites, reason=reason or "Channel locked")
        await self._log(ctx.guild, "Lock",
                        f"Channel: {ctx.channel.mention}\nBy: {ctx.author.mention}\nReason: {_safe_str(reason)}")
        await ctx.reply("🔒 Channel locked.", mention_author=False)

    @commands.hybrid_command(name="unlock", description="(Mod) Unlock this channel for @everyone")
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context):
        overwrites = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrites.send_messages = None
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrites, reason="Channel unlocked")
        await self._log(ctx.guild, "Unlock", f"Channel: {ctx.channel.mention}\nBy: {ctx.author.mention}")
        await ctx.reply("🔓 Channel unlocked.", mention_author=False)

    # ---------- Member actions ----------
    @commands.hybrid_command(name="warn", description="(Mod) Warn a member")
    @commands.has_permissions(moderate_members=True)
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str):
        strikes = self._add_warning(ctx.guild.id, member.id, reason)
        await self._log(ctx.guild, "Warn",
                        f"User: {member.mention}\nBy: {ctx.author.mention}\nReason: {_safe_str(reason)}\nStrikes: {strikes}")
        try:
            await member.send(f"You were warned in **{ctx.guild.name}** for: {reason}\nCurrent strikes: {strikes}")
        except Exception:
            pass
        await ctx.reply(f"⚠️ Warned {member.mention}. (strikes: {strikes})", mention_author=False)
        await self._apply_strike_policy(member, strikes, reason)

    @commands.hybrid_command(name="warnings", description="(Mod) Show a member's warnings")
    @commands.has_permissions(moderate_members=True)
    async def warnings(self, ctx: commands.Context, member: discord.Member):
        ws = self._get_warnings(ctx.guild.id, member.id)
        if not ws:
            await ctx.reply(f"{member.mention} has no warnings.", mention_author=False)
            return
        lines = [f"- <t:{w['ts']}:R>: {_safe_str(w['reason'], 120)}" for w in ws]
        await ctx.reply(f"**Warnings for {member.mention}:**\n" + "\n".join(lines), mention_author=False)

    @commands.hybrid_command(name="clearwarnings", description="(Mod) Clear a member's warnings (and strikes)")
    @commands.has_permissions(moderate_members=True)
    async def clearwarnings(self, ctx: commands.Context, member: discord.Member):
        self._clear_warnings(ctx.guild.id, member.id)
        self._clear_strikes(ctx.guild.id, member.id)
        await self._log(ctx.guild, "Clear warnings", f"User: {member.mention}\nBy: {ctx.author.mention}")
        await ctx.reply(f"✅ Cleared warnings/strikes for {member.mention}.", mention_author=False)

    @commands.hybrid_command(name="mute", description="(Mod) Timeout a member for N minutes")
    @commands.has_permissions(moderate_members=True)
    async def mute(self, ctx: commands.Context, member: discord.Member, minutes: commands.Range[int, 1, 10080], *, reason: Optional[str] = None):
        try:
            until = discord.utils.utcnow() + timedelta(minutes=int(minutes))
            await member.timeout(until, reason=reason or "Muted by moderator")
            await self._log(ctx.guild, "Mute",
                            f"User: {member.mention}\nBy: {ctx.author.mention}\nMinutes: {minutes}\nReason: {_safe_str(reason)}")
            await ctx.reply(f"🔇 Muted {member.mention} for {minutes} minute(s).", mention_author=False)
        except discord.Forbidden:
            await ctx.reply("I lack permission to mute that user.", mention_author=False)

    @commands.hybrid_command(name="unmute", description="(Mod) Remove timeout from a member")
    @commands.has_permissions(moderate_members=True)
    async def unmute(self, ctx: commands.Context, member: discord.Member):
        try:
            await member.timeout(None, reason="Unmuted by moderator")
            await self._log(ctx.guild, "Unmute", f"User: {member.mention}\nBy: {ctx.author.mention}")
            await ctx.reply(f"🔈 Unmuted {member.mention}.", mention_author=False)
        except discord.Forbidden:
            await ctx.reply("I lack permission to unmute that user.", mention_author=False)

    @commands.hybrid_command(name="kick", description="(Mod) Kick a member")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = None):
        try:
            await member.kick(reason=reason or "Kicked by moderator")
            await self._log(ctx.guild, "Kick", f"User: {member}\nBy: {ctx.author}\nReason: {_safe_str(reason)}")
            await ctx.reply(f"👢 Kicked {member}.", mention_author=False)
        except discord.Forbidden:
            await ctx.reply("I lack permission to kick that user.", mention_author=False)

    @commands.hybrid_command(name="ban", description="(Mod) Ban a member")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = None):
        try:
            await member.ban(reason=reason or "Banned by moderator", delete_message_days=0)
            await self._log(ctx.guild, "Ban", f"User: {member}\nBy: {ctx.author}\nReason: {_safe_str(reason)}")
            await ctx.reply(f"⛔ Banned {member}.", mention_author=False)
        except discord.Forbidden:
            await ctx.reply("I lack permission to ban that user.", mention_author=False)

    @commands.hybrid_command(name="unban", description="(Mod) Unban by user ID")
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, user_id: int, *, reason: Optional[str] = None):
        try:
            user = await self.bot.fetch_user(user_id)
            await ctx.guild.unban(user, reason=reason or "Unbanned by moderator")
            await self._log(ctx.guild, "Unban", f"User ID: {user_id}\nBy: {ctx.author}\nReason: {_safe_str(reason)}")
            await ctx.reply(f"✅ Unbanned `{user}` ({user_id}).", mention_author=False)
        except discord.NotFound:
            await ctx.reply("User not found in ban list.", mention_author=False)
        except discord.Forbidden:
            await ctx.reply("I lack permission to unban that user.", mention_author=False)

async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))