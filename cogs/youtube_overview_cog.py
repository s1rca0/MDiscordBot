# cogs/youtube_overview_cog.py
import os, asyncio, xml.etree.ElementTree as ET
from typing import Optional, List

import discord
from discord.ext import commands
from discord import app_commands
import aiohttp

from config import BotConfig
cfg = BotConfig()

YT_CHANNEL_ID = os.getenv("YT_CHANNEL_ID", "").strip()
YT_API_KEY = os.getenv("YT_API_KEY", "").strip()

API_BASE = "https://www.googleapis.com/youtube/v3"
RSS_BASE = "https://www.youtube.com/feeds/videos.xml?channel_id="

class YouTubeOverviewCog(commands.Cog):
    """Tiny YouTube overview for your channel."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="yt_overview", description="Show latest uploads (and subs if API key is set).")
    async def yt_overview(self, interaction: discord.Interaction):
        if not YT_CHANNEL_ID:
            return await interaction.response.send_message(
                "Set `YT_CHANNEL_ID` secret to enable this command.", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True, thinking=True)

        subs_text = "—"
        if YT_API_KEY:
            try:
                subs_text = await self._fetch_subs()
            except Exception:
                subs_text = "n/a"

        try:
            vids = await self._fetch_latest()
        except Exception:
            vids = []

        desc = []
        if subs_text and subs_text != "—":
            desc.append(f"**Subscribers:** {subs_text}")
        if vids:
            for v in vids[:3]:
                desc.append(f"• [{v['title']}]({v['url']})")
        else:
            desc.append("_No recent uploads found._")

        embed = discord.Embed(
            title="YouTube Overview",
            description="\n".join(desc),
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _fetch_subs(self) -> str:
        # channel statistics endpoint
        url = f"{API_BASE}/channels?part=statistics&id={YT_CHANNEL_ID}&key={YT_API_KEY}"
        async with aiohttp.ClientSession() as sess:
            async with sess.get(url, timeout=15) as r:
                r.raise_for_status()
                j = await r.json()
                items = j.get("items", [])
                if not items:
                    return "n/a"
                stats = items[0].get("statistics", {})
                return stats.get("subscriberCount", "n/a")

    async def _fetch_latest(self) -> List[dict]:
        url = f"{RSS_BASE}{YT_CHANNEL_ID}"
        async with aiohttp.ClientSession() as sess:
            async with sess.get(url, timeout=15) as r:
                r.raise_for_status()
                xml = await r.text()
        root = ET.fromstring(xml)
        ns = {"yt": "http://www.youtube.com/xml/schemas/2015", "atom": "http://www.w3.org/2005/Atom"}
        out = []
        for entry in root.findall("atom:entry", ns):
            title = entry.findtext("atom:title", default="", namespaces=ns)
            link_el = entry.find("atom:link", ns)
            href = link_el.attrib.get("href") if link_el is not None else ""
            out.append({"title": title, "url": href})
        return out

async def setup(bot: commands.Bot):
    await bot.add_cog(YouTubeOverviewCog(bot))