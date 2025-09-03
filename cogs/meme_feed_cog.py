# cogs/meme_feed_cog.py
from __future__ import annotations
import os
import json
import time
import random
from typing import Optional, Dict, List

import discord
from discord import app_commands
from discord.ext import commands, tasks
import requests

from config import cfg

HIST_PATH = "data/meme_history.json"

def _load_hist() -> Dict[str, float]:
    try:
        with open(HIST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_hist(d: Dict[str, float]):
    try:
        os.makedirs(os.path.dirname(HIST_PATH), exist_ok=True)
        with open(HIST_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except Exception:
        pass

class MemeFeedCog(commands.Cog, name="Meme Feed"):
    """
    Consolidated under /memes:
      - config | start | stop | now
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.enabled: bool = bool(getattr(cfg, "MEMES_ENABLED", False))
        self.channel_id: int = int(getattr(cfg, "MEME_CHANNEL_ID", 0) or 0)
        self.interval_min: int = max(15, int(getattr(cfg, "MEME_INTERVAL_MIN", 120) or 120))
        subs_env = os.getenv("MEME_SUBREDDITS", "memes,dankmemes,ProgrammerHumor")
        self.subreddits: List[str] = [s.strip() for s in subs_env.split(",") if s.strip()]
        self.hist: Dict[str, float] = _load_hist()

        # Group
        self.memes = app_commands.Group(name="memes", description="Trending meme feed tools")
        self.memes.command(name="config", description="Show meme feed settings")(self._config)
        self.memes.command(name="start", description="(Admin) Enable scheduled memes in a channel")(self._start)
        self.memes.command(name="stop", description="(Admin) Disable scheduled memes")(self._stop)
        self.memes.command(name="now", description="(Admin) Post one meme now")(self._now)

    async def cog_load(self):
        if self.enabled and self.channel_id and self.subreddits:
            self.poster.start()
        try:
            self.bot.tree.add_command(self.memes)
        except app_commands.CommandAlreadyRegistered:
            pass

    def cog_unload(self):
        if self.poster.is_running():
            self.poster.cancel()
        try:
            self.bot.tree.remove_command("memes", type=discord.AppCommandType.chat_input)
        except Exception:
            pass

    # ---- loop every 5m; post only when interval elapsed ----
    @tasks.loop(minutes=5)
    async def poster(self):
        if not self.enabled or not self.channel_id or not self.subreddits:
            return
        now = time.time()
        last = float(self.hist.get("_last_ts", 0))
        if now - last < self.interval_min * 60:
            return
        ch = self.bot.get_channel(self.channel_id)
        if not isinstance(ch, (discord.TextChannel, discord.Thread)):
            return
        post = await self._pick_meme()
        if not post:
            return
        title, url, permalink = post
        try:
            if url.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                emb = discord.Embed(title=title, url=f"https://reddit.com{permalink}", color=discord.Color.green())
                emb.set_image(url=url)
                emb.set_footer(text="From the feed • M.O.R.P.H.E.U.S. is watching")
                await ch.send(embed=emb)
            else:
                await ch.send(f"**{title}**\n{url}\nhttps://reddit.com{permalink}")
        except Exception:
            return
        self.hist["_last_ts"] = now
        _save_hist(self.hist)

    async def _pick_meme(self) -> Optional[tuple[str, str, str]]:
        sub = random.choice(self.subreddits)
        headers = {"User-Agent": "morpheus-meme-feed/1.0"}
        try:
            r = requests.get(f"https://www.reddit.com/r/{sub}/top.json?limit=60&t=day", headers=headers, timeout=12)
            if r.status_code != 200:
                return None
            data = r.json()
        except Exception:
            return None
        candidates = []
        for child in data.get("data", {}).get("children", []):
            d = child.get("data", {})
            if d.get("over_18"):
                continue
            url = d.get("url_overridden_by_dest") or d.get("url")
            perm = d.get("permalink", "")
            title = d.get("title", "meme")
            key = d.get("id")
            if not url or not key:
                continue
            if key in self.hist:
                continue
            candidates.append((key, title, url, perm))
        random.shuffle(candidates)
        for key, title, url, perm in candidates:
            self.hist[key] = time.time()
            _save_hist(self.hist)
            return title, url, perm
        return None

    # ---- /memes subcommands ----
    async def _config(self, itx: discord.Interaction):
        await itx.response.send_message(
            f"**Meme Feed**\n"
            f"- enabled: `{self.enabled}`\n"
            f"- channel_id: `{self.channel_id}`\n"
            f"- interval_min: `{self.interval_min}`\n"
            f"- subs: `{', '.join(self.subreddits)}`\n"
            f"- seen: `{len(self.hist)}`",
            ephemeral=True
        )

    @app_commands.describe(channel="Channel to post in", interval_min="Minutes between posts (>=15)")
    async def _start(self, itx: discord.Interaction, channel: discord.TextChannel, interval_min: int = 120):
        if not (isinstance(itx.user, discord.Member) and itx.user.guild_permissions.manage_guild):
            await itx.response.send_message("Admins only.", ephemeral=True); return
        self.channel_id = channel.id
        self.interval_min = max(15, int(interval_min))
        self.enabled = True
        if not self.poster.is_running():
            self.poster.start()
        await itx.response.send_message(
            f"✅ Meme feed enabled in {channel.mention} every **{self.interval_min}m**.",
            ephemeral=True
        )

    async def _stop(self, itx: discord.Interaction):
        if not (isinstance(itx.user, discord.Member) and itx.user.guild_permissions.manage_guild):
            await itx.response.send_message("Admins only.", ephemeral=True); return
        self.enabled = False
        if self.poster.is_running():
            self.poster.cancel()
        await itx.response.send_message("🛑 Meme feed stopped.", ephemeral=True)

    async def _now(self, itx: discord.Interaction):
        if not (isinstance(itx.user, discord.Member) and itx.user.guild_permissions.manage_guild):
            await itx.response.send_message("Admins only.", ephemeral=True); return
        ch = self.bot.get_channel(self.channel_id)
        if not isinstance(ch, (discord.TextChannel, discord.Thread)):
            await itx.response.send_message("No channel set. Use `/memes start`.", ephemeral=True)
            return
        post = await self._pick_meme()
        if not post:
            await itx.response.send_message("No fresh meme found right now 🙃", ephemeral=True)
            return
        title, url, perm = post
        try:
            if url.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                emb = discord.Embed(title=title, url=f"https://reddit.com{perm}", color=discord.Color.green())
                emb.set_image(url=url)
                emb.set_footer(text="From the feed • M.O.R.P.H.E.U.S. is watching")
                await ch.send(embed=emb)
            else:
                await ch.send(f"**{title}**\n{url}\nhttps://reddit.com{perm}")
            await itx.response.send_message("Sent ✅", ephemeral=True)
        except Exception:
            await itx.response.send_message("Failed to send.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(MemeFeedCog(bot))