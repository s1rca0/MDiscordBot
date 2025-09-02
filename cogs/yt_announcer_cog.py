# cogs/yt_announcer_cog.py
import os
import json
import time
import asyncio
import xml.etree.ElementTree as ET
from typing import Optional

import discord
from discord.ext import commands, tasks
from discord import app_commands

DATA_DIR = "data"
STATE_PATH = os.path.join(DATA_DIR, "youtube_announcer.json")

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default

def _env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()

def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name, str(default))
    return str(v).lower() in ("1", "true", "yes", "y", "on")

DEFAULT_POLL_MIN = _env_int("YT_POLL_MINUTES", 10)
DEFAULT_GUILD_CHANNEL_ID = _env_int("YT_ANNOUNCE_CHANNEL_ID", 0)  # optional default
DEFAULT_YT_CHANNEL_ID = _env_str("YT_CHANNEL_ID", "")             # optional default
DEFAULT_MENTION_ROLE_ID = _env_int("YT_ANNOUNCE_ROLE_ID", 0)      # optional default
ALLOW_EMBEDS = _env_bool("YT_ALLOW_EMBEDS", True)

def _ensure_state():
    if not os.path.isdir(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.isfile(STATE_PATH):
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump({"last_video_id": "", "watches": {}}, f)

def _load_state():
    _ensure_state()
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def _save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

async def _fetch_text(session, url: str, timeout: int = 15) -> Optional[str]:
    import aiohttp
    try:
        async with session.get(url, timeout=timeout) as resp:
            if resp.status == 200:
                return await resp.text()
    except Exception:
        return None
    return None

def _parse_latest_video_id(feed_xml: str) -> Optional[str]:
    try:
        root = ET.fromstring(feed_xml)
        # YouTube RSS uses the Atom namespace
        ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
        entry = root.find("atom:entry", ns)
        if entry is None:
            return None
        vid = entry.find("yt:videoId", ns)
        if vid is not None and vid.text:
            return vid.text.strip()
        # fallback: parse from link href
        link = entry.find("atom:link", ns)
        if link is not None and link.get("href"):
            href = link.get("href")
            if "watch?v=" in href:
                return href.split("watch?v=")[-1].split("&")[0]
        return None
    except Exception:
        return None

def _parse_title_and_link(feed_xml: str) -> Optional[tuple]:
    try:
        root = ET.fromstring(feed_xml)
        ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
        entry = root.find("atom:entry", ns)
        if entry is None:
            return None
        title_el = entry.find("atom:title", ns)
        link_el = entry.find("atom:link", ns)
        title = title_el.text.strip() if title_el is not None and title_el.text else "New video"
        url = link_el.get("href") if link_el is not None else None
        return (title, url)
    except Exception:
        return None

class YouTubeAnnouncer(commands.Cog):
    """Announces new YouTube uploads using the public RSS feed (no API key)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        _ensure_state()
        self.poll_minutes = DEFAULT_POLL_MIN
        # Start background task
        self.poller.start()

    def cog_unload(self):
        self.poller.cancel()

    # --------- task loop ---------
    @tasks.loop(minutes=1.0)
    async def poller(self):
        # Only poll every self.poll_minutes
        state = _load_state()
        last_run = state.get("last_run_ts", 0.0)
        if time.time() - float(last_run) < self.poll_minutes * 60:
            return
        state["last_run_ts"] = time.time()
        _save_state(state)

        # Collate watches from state + env defaults
        watches = dict(state.get("watches", {}))  # guild_id -> {yt_channel_id, announce_channel_id, mention_role_id}
        # If env defaults were provided and not yet saved, add them to the current guilds later via /yt_watch set
        # We also support a singleton default (no guild) below if both defaults are provided
        singleton = None
        if DEFAULT_YT_CHANNEL_ID and DEFAULT_GUILD_CHANNEL_ID:
            singleton = {
                "yt_channel_id": DEFAULT_YT_CHANNEL_ID,
                "announce_channel_id": DEFAULT_GUILD_CHANNEL_ID,
                "mention_role_id": DEFAULT_MENTION_ROLE_ID or 0,
            }

        import aiohttp
        async with aiohttp.ClientSession() as session:
            # If singleton default exists and we can't map a guild, just post to that channel id
            if singleton:
                await self._check_and_post(session, None, singleton)

            # Per-guild watches
            for gid, cfg in watches.items():
                await self._check_and_post(session, int(gid), cfg)

    @poller.before_loop
    async def before_poller(self):
        await self.bot.wait_until_ready()

    async def _check_and_post(self, session, guild_id: Optional[int], cfg: dict):
        yt_channel_id = (cfg or {}).get("yt_channel_id")
        announce_channel_id = int((cfg or {}).get("announce_channel_id") or 0)
        mention_role_id = int((cfg or {}).get("mention_role_id") or 0)
        if not yt_channel_id or not announce_channel_id:
            return

        feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={yt_channel_id}"
        xml_txt = await _fetch_text(session, feed_url)
        if not xml_txt:
            return

        latest_vid = _parse_latest_video_id(xml_txt)
        if not latest_vid:
            return

        state = _load_state()
        key = f"{guild_id or 'singleton'}:{yt_channel_id}"
        posted_map = state.get("posted_map", {})
        if posted_map.get(key) == latest_vid:
            return  # already posted

        title_link = _parse_title_and_link(xml_txt)
        if not title_link:
            return
        title, url = title_link
        if not url:
            url = f"https://www.youtube.com/watch?v={latest_vid}"

        # Build message
        channel = self.bot.get_channel(announce_channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        mention_text = ""
        if mention_role_id:
            role = None
            if guild_id:
                guild = self.bot.get_guild(int(guild_id))
                if guild:
                    role = guild.get_role(mention_role_id)
            # if singleton default, we can still try to resolve from bot cache (best effort)
            if role:
                mention_text = role.mention + " "

        embed = None
        if ALLOW_EMBEDS:
            embed = discord.Embed(
                title=title,
                description="A new upload just dropped.",
                color=discord.Color.green()
            )
            embed.add_field(name="Watch", value=url, inline=False)
            embed.set_footer(text="Legends in Motion HQ")
        else:
            embed = None

        try:
            if embed:
                await channel.send(f"{mention_text}**New video!**", embed=embed)
            else:
                await channel.send(f"{mention_text}**New video!** {title}\n{url}")
            # Remember posted id
            posted_map[key] = latest_vid
            state["posted_map"] = posted_map
            _save_state(state)
        except Exception:
            pass

    # --------- slash commands ---------
    yt_group = app_commands.Group(name="yt_watch", description="Configure YouTube upload watcher")

    @yt_group.command(name="set", description="Set YouTube channel + announce channel (per guild).")
    @app_commands.describe(
        youtube_channel_id="The YouTube channel_id to watch (not handle)",
        announce_channel="Discord channel to post into",
        mention_role="Optional role to @mention on new uploads",
        poll_minutes="How often to poll (minutes). Default from env"
    )
    async def yt_set(
        self,
        interaction: discord.Interaction,
        youtube_channel_id: str,
        announce_channel: discord.TextChannel,
        mention_role: Optional[discord.Role] = None,
        poll_minutes: Optional[int] = None,
    ):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server permission required.", ephemeral=True)
            return

        state = _load_state()
        watches = state.get("watches", {})
        gid = str(interaction.guild_id)
        watches[gid] = {
            "yt_channel_id": youtube_channel_id.strip(),
            "announce_channel_id": int(announce_channel.id),
            "mention_role_id": int(mention_role.id) if mention_role else 0,
        }
        state["watches"] = watches
        _save_state(state)

        if poll_minutes and poll_minutes > 0:
            self.poll_minutes = poll_minutes

        await interaction.response.send_message(
            f"OK. Watching channel `{youtube_channel_id}` and posting to {announce_channel.mention} "
            f"{'(+mention '+mention_role.mention+')' if mention_role else ''}. "
            f"Poll interval: {self.poll_minutes} min.",
            ephemeral=True
        )

    @yt_group.command(name="status", description="Show current watcher settings.")
    async def yt_status(self, interaction: discord.Interaction):
        state = _load_state()
        watches = state.get("watches", {})
        cfg = watches.get(str(interaction.guild_id))
        if not cfg:
            await interaction.response.send_message("No watcher set for this server yet.", ephemeral=True)
            return
        ch = interaction.guild.get_channel(int(cfg.get("announce_channel_id", 0)))
        role = interaction.guild.get_role(int(cfg.get("mention_role_id", 0)))
        await interaction.response.send_message(
            f"Watching: `{cfg.get('yt_channel_id')}`\n"
            f"Posting in: {ch.mention if ch else '`unknown`'}\n"
            f"Mention: {role.mention if role else 'none'}\n"
            f"Poll: {self.poll_minutes} min",
            ephemeral=True
        )

    @app_commands.command(name="yt_post_latest", description="Post the latest upload now (force).")
    async def yt_post_latest(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        state = _load_state()
        watches = state.get("watches", {})
        cfg = watches.get(str(interaction.guild_id))
        if not cfg:
            await interaction.followup.send("No watcher set for this server yet. Use `/yt_watch set`.", ephemeral=True)
            return
        import aiohttp
        async with aiohttp.ClientSession() as session:
            await self._check_and_post(session, interaction.guild_id, cfg)
        await interaction.followup.send("Checked and posted if there was a new upload.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(YouTubeAnnouncer(bot))