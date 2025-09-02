# cogs/meme_feed_cog.py
from __future__ import annotations
import os
import json
import time
import random
from typing import Optional, Dict, List

import discord
from discord.ext import commands, tasks
import requests

from config import cfg  # uses your module-level cfg

# Ephemeral history file (safe on Railway Hobby; lost on redeploys, which is fine)
HIST_PATH = "data/meme_history.json"

def _load_hist() -> Dict[str, float]:
    try:
        with open(HIST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _save_hist(d: Dict[str, float]):
    try:
        os.makedirs(os.path.dirname(HIST_PATH), exist_ok=True)
        with open(HIST_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except Exception:
        # Best-effort only; ignore IO errors on Hobby
        pass

class MemeFeedCog(commands.Cog, name="Meme Feed"):
    """
    Lightweight meme poster for #memes using Reddit's public JSON endpoints.
    Reads settings from env/config:
      - cfg.MEMES_ENABLED (bool via ENABLE_MEME_FEED)
      - cfg.MEME_CHANNEL_ID (int)
      - cfg.MEME_INTERVAL_MIN (int, default 120)
      - optional: MEME_SUBREDDITS (comma list), default: memes,dankmemes,ProgrammerHumor
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.enabled: bool = bool(getattr(cfg, "MEMES_ENABLED", False))
        self.channel_id: int = int(getattr(cfg, "MEME_CHANNEL_ID", 0) or 0)
        self.interval_min: int = max(15, int(getattr(cfg, "MEME_INTERVAL_MIN", 120) or 120))

        subs_env = os.getenv("MEME_SUBREDDITS", "memes,dankmemes,ProgrammerHumor")
        self.subreddits: List[str] = [s.strip() for s in subs_env.split(",") if s.strip()]

        self.hist: Dict[str, float] = _load_hist()

    async def cog_load(self):
        # Start loop only when enabled and a channel is configured
        if self.enabled and self.channel_id and self.subreddits:
            self.poster.start()

    def cog_unload(self):
        if self.poster.is_running():
            self.poster.cancel()

    # Runs every 5 minutes; will post only when interval elapsed
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
                emb = discord.Embed(
                    title=title,
                    url=f"https://reddit.com{permalink}",
                    color=discord.Color.green()
                )
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
        # Get a batch and choose first new, SFW-ish candidate
        sub = random.choice(self.subreddits)
        headers = {"User-Agent": "morpheus-meme-feed/1.0"}
        try:
            r = requests.get(
                f"https://www.reddit.com/r/{sub}/top.json?limit=60&t=day",
                headers=headers,
                timeout=12
            )
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
            self.hist[key] = time.time()  # remember
            _save_hist(self.hist)         # best-effort write
            return title, url, perm
        return None

    # ---- Admin slash commands ----

    @app_commands.command(name="memes_config", description="Show meme feed settings")
    async def memes_config(self, itx: discord.Interaction):
        await itx.response.send_message(
            f"**Meme Feed**\n"
            f"- enabled: `{self.enabled}`\n"
            f"- channel_id: `{self.channel_id}`\n"
            f"- interval_min: `{self.interval_min}`\n"
            f"- subs: `{', '.join(self.subreddits)}`\n"
            f"- seen: `{len(self.hist)}`",
            ephemeral=True
        )

    @app_commands.command(name="memes_start", description="(Admin) Enable scheduled memes in a channel")
    @app_commands.describe(channel="Channel to post in", interval_min="Minutes between posts (>=15)")
    async def memes_start(self, itx: discord.Interaction, channel: discord.TextChannel, interval_min: int = 120):
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

    @app_commands.command(name="memes_stop", description="(Admin) Disable scheduled memes")
    async def memes_stop(self, itx: discord.Interaction):
        if not (isinstance(itx.user, discord.Member) and itx.user.guild_permissions.manage_guild):
            await itx.response.send_message("Admins only.", ephemeral=True); return

        self.enabled = False
        if self.poster.is_running():
            self.poster.cancel()
        await itx.response.send_message("🛑 Meme feed stopped.", ephemeral=True)

    @app_commands.command(name="memes_now", description="(Admin) Post one meme now")
    async def memes_now(self, itx: discord.Interaction):
        if not (isinstance(itx.user, discord.Member) and itx.user.guild_permissions.manage_guild):
            await itx.response.send_message("Admins only.", ephemeral=True); return

        # temporarily ensure channel is valid
        ch = self.bot.get_channel(self.channel_id)
        if not isinstance(ch, (discord.TextChannel, discord.Thread)):
            await itx.response.send_message("No channel set. Use `/memes_start`.", ephemeral=True)
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