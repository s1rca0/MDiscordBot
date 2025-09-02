# cogs/meme_feed_cog.py
import os
import json
import time
import random
from typing import List, Optional, Dict

import discord
from discord.ext import commands, tasks
import requests

HIST_PATH = "data/meme_history.json"

def _load_hist() -> Dict[str, float]:
    try:
        with open(HIST_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_hist(d: Dict[str, float]):
    os.makedirs(os.path.dirname(HIST_PATH), exist_ok=True)
    with open(HIST_PATH, "w") as f:
        json.dump(d, f)

class MemeFeedCog(commands.Cog, name="Meme Feed"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.channel_id = int(os.getenv("MEME_CHANNEL_ID", "0"))
        self.interval_min = int(os.getenv("MEME_INTERVAL_MIN", "60") or "60")
        subs = os.getenv("MEME_SUBREDDITS", "memes,dankmemes,ProgrammerHumor")
        self.subreddits = [s.strip() for s in subs.split(",") if s.strip()]
        self.hist = _load_hist()
        self.poster.start()

    def cog_unload(self):
        self.poster.cancel()

    @tasks.loop(minutes=5)
    async def poster(self):
        if not self.channel_id or not self.subreddits:
            return
        # stagger: only post at configured interval
        now = time.time()
        last = float(self.hist.get("_last_ts", 0))
        if now - last < self.interval_min * 60:
            return

        ch = self.bot.get_channel(self.channel_id)
        if not isinstance(ch, (discord.TextChannel, discord.Thread)):
            return

        try:
            post = self._pick_meme()
            if not post:
                return
            title, url, permalink = post
            if url.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                emb = discord.Embed(title=title, url=f"https://reddit.com{permalink}", color=discord.Color.green())
                emb.set_image(url=url)
                emb.set_footer(text="From the feed • Morpheus is watching")
                await ch.send(embed=emb)
            else:
                await ch.send(f"**{title}**\n{url}\nhttps://reddit.com{permalink}")

            self.hist["_last_ts"] = now
            _save_hist(self.hist)
        except Exception:
            # stay quiet on failure
            pass

    def _pick_meme(self) -> Optional[tuple[str, str, str]]:
        # pick a subreddit and pull top/day
        sub = random.choice(self.subreddits)
        headers = {"User-Agent": "morpheus-meme-feed/1.0"}
        r = requests.get(f"https://www.reddit.com/r/{sub}/top.json?limit=50&t=day", headers=headers, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
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
            if self.hist.get(key):
                continue
            candidates.append((key, title, url, perm))

        random.shuffle(candidates)
        for key, title, url, perm in candidates:
            # remember & return the first new one
            self.hist[key] = time.time()
            return title, url, perm
        return None

async def setup(bot: commands.Bot):
    await bot.add_cog(MemeFeedCog(bot))