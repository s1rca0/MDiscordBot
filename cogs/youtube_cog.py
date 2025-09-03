# cogs/youtube_cog.py
from __future__ import annotations
import os
import json
import time
import asyncio
from typing import Optional, Dict, Any

import discord
from discord.ext import commands, tasks

import requests

STATE_PATH = "data/yt_state.json"

def _load_state() -> Dict[str, Any]:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_state(d: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
    except Exception:
        pass

def _env_bool(name: str, default: bool = True) -> bool:
    v = os.getenv(name)
    return default if v is None else str(v).strip().lower() in ("1", "true", "y", "yes", "on")

# ---- ENV / Config ----
YT_API_KEY          = os.getenv("YT_API_KEY", "").strip()
YT_CHANNEL_ID       = os.getenv("YT_CHANNEL_ID", "").strip()                 # <-- YouTube channel *string* (e.g., UC_xxx)
YT_POLL_MIN         = max(5, int(os.getenv("YT_POLL_MIN", "15") or 15))      # poll cadence
YT_ANNOUNCE_CHANNEL_ID = os.getenv("YT_ANNOUNCE_CHANNEL_ID", "").strip()     # Discord channel id (string ok; we'll int() safely)
YT_ANNOUNCE_ROLE_ID = os.getenv("YT_ANNOUNCE_ROLE_ID", "").strip()           # optional role to ping

def _to_int(s: str, default: int = 0) -> int:
    try:
        return int(s)
    except Exception:
        return default

DISCORD_ANNOUNCE_CH = _to_int(YT_ANNOUNCE_CHANNEL_ID, 0)
DISCORD_PING_ROLE   = _to_int(YT_ANNOUNCE_ROLE_ID, 0)

class YouTubeCog(commands.Cog, name="YouTube"):
    """
    Polls a YouTube channel for the latest upload and announces to a configured Discord channel.
    Safe defaults: if any required bits are missing, this cog quietly idles.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.state: Dict[str, Any] = _load_state()
        self._last_video_id: Optional[str] = self.state.get("last_video_id") or None
        self._last_checked: float = float(self.state.get("last_checked", 0.0) or 0.0)

    async def cog_load(self):
        # Only start if we have key + channel + announce channel
        if not YT_API_KEY or not YT_CHANNEL_ID or not DISCORD_ANNOUNCE_CH:
            # Keep it quiet: other cogs log enough already
            return
        if not self.poller.is_running():
            self.poller.start()

    def cog_unload(self):
        if self.poller.is_running():
            self.poller.cancel()

    # ----------------- Internal helpers -----------------
    async def _fetch_latest_video(self) -> Optional[Dict[str, Any]]:
        """
        Returns: {"id": videoId, "title": str, "publishedAt": iso, "thumb": url} or None
        """
        url = (
            "https://www.googleapis.com/youtube/v3/search"
            f"?part=snippet&channelId={YT_CHANNEL_ID}"
            "&order=date&type=video&maxResults=1"
            f"&key={YT_API_KEY}"
        )

        def _do_get():
            try:
                return requests.get(url, timeout=10)
            except Exception:
                return None

        r = await asyncio.to_thread(_do_get)
        if not r or r.status_code != 200:
            return None

        try:
            data = r.json()
        except Exception:
            return None

        items = data.get("items") or []
        if not items:
            return None

        it = items[0]
        vid = (it.get("id") or {}).get("videoId")
        sn  = it.get("snippet") or {}
        if not vid:
            return None

        title = sn.get("title", "New upload")
        published = sn.get("publishedAt", "")
        thumb = ((sn.get("thumbnails") or {}).get("high") or {}).get("url") \
                or ((sn.get("thumbnails") or {}).get("default") or {}).get("url") \
                or None

        return {"id": vid, "title": title, "publishedAt": published, "thumb": thumb}

    async def _announce(self, video: Dict[str, Any]) -> bool:
        ch = self.bot.get_channel(DISCORD_ANNOUNCE_CH)
        if not isinstance(ch, (discord.TextChannel, discord.Thread)):
            return False

        vid = video["id"]
        title = video["title"]
        url = f"https://youtu.be/{vid}"
        ping = ""
        if DISCORD_PING_ROLE:
            role = getattr(ch.guild, "get_role", lambda x: None)(DISCORD_PING_ROLE)
            if role:
                ping = role.mention + " "

        emb = discord.Embed(
            title=title,
            url=url,
            description="A new transmission just dropped.",
            color=discord.Color.red()
        )
        if video.get("thumb"):
            emb.set_thumbnail(url=video["thumb"])
        emb.set_footer(text="YouTube • Morpheus link")

        try:
            await ch.send(content=ping or None, embed=emb)
            return True
        except Exception:
            return False

    def _remember(self, video_id: Optional[str]):
        if video_id:
            self._last_video_id = video_id
        self._last_checked = time.time()
        self.state["last_video_id"] = self._last_video_id
        self.state["last_checked"] = self._last_checked
        _save_state(self.state)

    # ----------------- Polling loop -----------------
    @tasks.loop(minutes=YT_POLL_MIN)
    async def poller(self):
        # Guard again inside the loop in case envs were updated at runtime
        if not YT_API_KEY or not YT_CHANNEL_ID or not DISCORD_ANNOUNCE_CH:
            return
        video = await self._fetch_latest_video()
        if not video:
            self._remember(self._last_video_id)
            return

        vid = video["id"]
        if vid != self._last_video_id:
            # New upload detected
            ok = await self._announce(video)
            if ok:
                self._remember(vid)
            else:
                # Remember anyway to avoid spam; you can comment this if you want retries
                self._remember(vid)
        else:
            self._remember(self._last_video_id)

    # ----------------- Commands -----------------
    @commands.hybrid_group(name="yt", description="YouTube status & controls")
    async def yt_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.reply(
                f"**YouTube status**\n"
                f"- API key: `{'set' if bool(YT_API_KEY) else 'missing'}`\n"
                f"- Channel ID: `{YT_CHANNEL_ID or 'missing'}`\n"
                f"- Announce channel ID: `{DISCORD_ANNOUNCE_CH or 'missing'}`\n"
                f"- Poll: every `{YT_POLL_MIN}m`\n"
                f"- Last video: `{self._last_video_id or 'n/a'}`",
                mention_author=False
            )

    @yt_group.command(name="force_check", description="Force a YouTube check now")
    @commands.has_permissions(manage_guild=True)
    async def yt_force_check(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        if not YT_API_KEY or not YT_CHANNEL_ID:
            await ctx.reply("Missing YT_API_KEY or YT_CHANNEL_ID.", mention_author=False)
            return
        v = await self._fetch_latest_video()
        if not v:
            await ctx.reply("No result / API error.", mention_author=False)
            return

        changed = v["id"] != self._last_video_id
        if changed:
            ok = await self._announce(v)
            self._remember(v["id"])
            await ctx.reply(("Announced ✅ " if ok else "Fetched, but failed to announce ❌ ") + f"<https://youtu.be/{v['id']}>", mention_author=False)
        else:
            await ctx.reply(f"No change. Latest is still <https://youtu.be/{v['id']}>", mention_author=False)

    @yt_group.command(name="status", description="Show current YouTube config/status")
    async def yt_status(self, ctx: commands.Context):
        await ctx.reply(
            f"**YT status**\n"
            f"- Channel ID: `{YT_CHANNEL_ID or 'missing'}`\n"
            f"- Announce channel: `{DISCORD_ANNOUNCE_CH or 'missing'}`\n"
            f"- Role ping: `{DISCORD_PING_ROLE or 'none'}`\n"
            f"- Poll every: `{YT_POLL_MIN}m`\n"
            f"- Last video: `{self._last_video_id or 'n/a'}`",
            mention_author=False
        )

async def setup(bot: commands.Bot):
    # Don’t abort if misconfigured; the cog will just idle.
    await bot.add_cog(YouTubeCog(bot))