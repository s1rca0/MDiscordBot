# cogs/youtube_cog.py
# Poll YouTube RSS and announce new uploads. Quiet on success, report errors to modlog.

import os
import io
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict

import discord
from discord.ext import commands, tasks

import aiohttp
import xml.etree.ElementTree as ET

log = logging.getLogger(__name__)

DATA_DIR = "data"
STATE_PATH = os.path.join(DATA_DIR, "youtube_state.json")


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name, str(default))
    return str(v).lower() in ("1", "true", "yes", "y", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


class YouTubeCog(commands.Cog):
    """
    Watches a YouTube channel's Atom feed and posts new uploads to a server channel.
    Success is silent; errors are sent to the modlog channel.
    """

    FEED_TMPL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # ---- config from secrets/env
        self.channel_id = os.getenv("YT_CHANNEL_ID", "").strip()
        self.poll_minutes = max(3, _env_int("YT_POLL_MINUTES", 10))  # YouTube feed doesn't need to be spam-polled
        self.allow_embeds = _env_bool("YT_ALLOW_EMBEDS", True)

        self.announce_channel_id = int(os.getenv("YT_ANNOUNCE_CHANNEL_ID", "0") or 0)
        self.announce_role_id = int(os.getenv("YT_ANNOUNCE_ROLE_ID", "0") or 0)
        self.modlog_channel_id = int(os.getenv("MODLOG_CHANNEL_ID", "0") or 0)

        # state
        self._last_video_id: Optional[str] = None
        self._loading_state = False

        self.session: Optional[aiohttp.ClientSession] = None

        # kick off background task if configured
        if self.channel_id and self.announce_channel_id:
            self._load_state()
            self.poller.change_interval(minutes=self.poll_minutes)
            self.poller.start()
            log.info("YouTubeCog started: channel=%s, poll=%s min", self.channel_id, self.poll_minutes)
        else:
            log.warning("YouTubeCog not started (missing YT_CHANNEL_ID or YT_ANNOUNCE_CHANNEL_ID).")

    def cog_unload(self):
        try:
            self.poller.cancel()
        except Exception:
            pass

    # ---------- persistence ----------

    def _load_state(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.isfile(STATE_PATH):
            self._save_state(None)
            return
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._last_video_id = data.get("last_video_id")
        except Exception as e:
            log.warning("Could not read %s: %s", STATE_PATH, e)
            self._last_video_id = None

    def _save_state(self, last_video_id: Optional[str]):
        try:
            with open(STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "last_video_id": last_video_id,
                        "updated_ts": datetime.now(timezone.utc).isoformat(),
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            self._last_video_id = last_video_id
        except Exception as e:
            log.warning("Could not write %s: %s", STATE_PATH, e)

    # ---------- utilities ----------

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session and not self.session.closed:
            return self.session
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))
        return self.session

    async def _fetch_feed(self) -> str:
        url = self.FEED_TMPL.format(channel_id=self.channel_id)
        sess = await self._get_session()
        async with sess.get(url, headers={"User-Agent": "MorpheusBot/yt-rss"}) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status} from YouTube feed")
            return await resp.text()

    @staticmethod
    def _parse_latest(feed_xml: str) -> Optional[Dict]:
        """
        Return dict with {id, title, link, published, thumb} for the newest entry.
        """
        try:
            # The feed is Atom. Default namespace + media namespace.
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "media": "http://search.yahoo.com/mrss/",
                "yt": "http://www.youtube.com/xml/schemas/2015",
            }
            root = ET.fromstring(feed_xml)
            entry = root.find("atom:entry", ns)
            if entry is None:
                return None

            vid_id_el = entry.find("yt:videoId", ns)
            title_el = entry.find("atom:title", ns)
            link_el = entry.find("atom:link", ns)
            pub_el = entry.find("atom:published", ns)
            thumb_el = entry.find("media:group/media:thumbnail", ns)

            vid_id = (vid_id_el.text if vid_id_el is not None else "").strip()
            title = (title_el.text if title_el is not None else "").strip()
            link = (link_el.attrib.get("href") if link_el is not None else f"https://youtu.be/{vid_id}").strip()
            pub = (pub_el.text if pub_el is not None else "")
            thumb = (thumb_el.attrib.get("url") if thumb_el is not None else None)

            if not vid_id:
                return None

            return {
                "id": vid_id,
                "title": title or "New video",
                "link": link,
                "published": pub,
                "thumb": thumb,
            }
        except Exception:
            return None

    async def _announce(self, info: Dict):
        """
        Post the announcement. This is QUIET (no follow-up unless it errors).
        """
        channel = self.bot.get_channel(self.announce_channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            raise RuntimeError("Announce channel not found or not a text channel.")

        role_mention = f"<@&{self.announce_role_id}>" if self.announce_role_id else ""
        title = info["title"]
        link = info["link"]

        if self.allow_embeds:
            embed = discord.Embed(
                title=title,
                url=link,
                description="A new upload just dropped.",
                color=discord.Color.red(),
            )
            # Timestamp if we can parse it
            try:
                embed.timestamp = datetime.fromisoformat(info["published"].replace("Z", "+00:00"))
            except Exception:
                pass
            if info.get("thumb"):
                embed.set_thumbnail(url=info["thumb"])

            content = f"{role_mention}".strip() or None
            await channel.send(content=content, embed=embed)
        else:
            content = f"{role_mention} New upload: **{title}**\n{link}".strip()
            await channel.send(content)

    async def _modlog(self, text: str):
        if not self.modlog_channel_id:
            return
        ch = self.bot.get_channel(self.modlog_channel_id)
        if isinstance(ch, discord.TextChannel):
            try:
                await ch.send(f"🛠️ **YouTube watcher:** {text}")
            except Exception:
                pass

    # ---------- background task ----------

    @tasks.loop(minutes=10)
    async def poller(self):
        if not self.channel_id or not self.announce_channel_id:
            return

        try:
            feed = await self._fetch_feed()
            latest = self._parse_latest(feed)
            if not latest:
                return  # nothing to do

            if latest["id"] == self._last_video_id:
                return  # already announced

            # Optional: tiny debounce — in case of scheduled premiere you might want to wait a couple minutes
            # but we’ll announce immediately unless you want to add a delay here.

            await self._announce(latest)
            self._save_state(latest["id"])

        except Exception as e:
            log.warning("YouTube poll error: %s", e)
            await self._modlog(f"Error while checking/announcing: `{e}`")

    @poller.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()
        # Stagger initial run a bit after startup
        await asyncio.sleep(5)

    # ---------- optional admin command ----------

    @commands.hybrid_command(name="yt_force_check", with_app_command=True, description="(Owner) Force a YouTube feed check now")
    @commands.is_owner()
    async def yt_force_check(self, ctx: commands.Context):
        try:
            feed = await self._fetch_feed()
            latest = self._parse_latest(feed)
            if not latest:
                await ctx.reply("No entries found.")
                return
            already = latest["id"] == self._last_video_id
            if already:
                await ctx.reply(f"Latest is already announced: **{latest['title']}**")
            else:
                await self._announce(latest)
                self._save_state(latest["id"])
                await ctx.reply(f"Announced: **{latest['title']}**", ephemeral=True if hasattr(ctx, "interaction") else False)
        except Exception as e:
            await self._modlog(f"/yt_force_check failed: `{e}`")
            try:
                await ctx.reply("Error while checking. Logged to modlog.")
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(YouTubeCog(bot))