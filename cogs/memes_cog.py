import os
import json
import time
import random
from typing import List, Dict, Set, Optional

import discord
from discord.ext import commands, tasks
from discord import app_commands
import requests

from config import BotConfig

cfg = BotConfig()

DATA_DIR = "data"
SEEN_PATH = os.path.join(DATA_DIR, "memes_seen.json")

USER_AGENT = "MorpheusBot/1.0 (+https://example.com)"

def _load_seen() -> Set[str]:
    try:
        with open(SEEN_PATH, "r") as f:
            data = json.load(f)
            return set(data if isinstance(data, list) else [])
    except Exception:
        return set()

def _save_seen(ids: Set[str]):
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(SEEN_PATH, "w") as f:
            json.dump(sorted(list(ids))[-5000:], f)  # cap size
    except Exception:
        pass

def _pick_posts(subs: List[str], limit: int = 60) -> List[Dict]:
    posts: List[Dict] = []
    headers = {"User-Agent": USER_AGENT}
    session = requests.Session()
    session.headers.update(headers)

    for sub in subs:
        url = f"https://www.reddit.com/r/{sub}/top.json?t=day&limit={limit}"
        try:
            r = session.get(url, timeout=10)
            if r.status_code != 200:
                continue
            j = r.json()
            for c in j.get("data", {}).get("children", []):
                d = c.get("data", {})
                # image-ish, safe
                if d.get("over_18"):
                    continue
                u = d.get("url_overridden_by_dest") or d.get("url")
                if not u:
                    continue
                if not any(u.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif", ".gifv")) \
                   and "i.redd.it" not in u and "imgur" not in u:
                    continue
                posts.append({
                    "id": d.get("id"),
                    "title": d.get("title", ""),
                    "url": u,
                    "permalink": "https://reddit.com" + d.get("permalink", ""),
                    "sub": sub
                })
        except Exception:
            continue

    random.shuffle(posts)
    return posts

class MemesCog(commands.Cog, name="Memes"):
    """Scheduled trending memes from Reddit (safe-ish)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.enabled = bool(cfg.MEMES_ENABLED)
        self.channel_id = int(cfg.MEMES_CHANNEL_ID or 0)
        self.interval_min = max(15, int(cfg.MEMES_INTERVAL_MIN or 120))
        self.subs = [s.strip() for s in (cfg.MEMES_SUBREDDITS or "").split(",") if s.strip()]
        self.seen: Set[str] = _load_seen()
        self._lock = False

    async def cog_load(self):
        if self.enabled and self.channel_id and self.subs:
            self._loop.start()

    async def cog_unload(self):
        if self._loop.is_running():
            self._loop.cancel()

    # ---- loop ----
    @tasks.loop(minutes=1.0)
    async def _loop(self):
        # simple minute ticker; fire only when interval boundary passes
        now = int(time.time())
        if (now // 60) % self.interval_min != 0:
            return
        await self._post_one()

    async def _post_one(self) -> bool:
        if self._lock:
            return False
        self._lock = True
        try:
            ch: Optional[discord.TextChannel] = self.bot.get_channel(self.channel_id)  # type: ignore
            if not ch:
                return False

            posts = _pick_posts(self.subs)
            for p in posts:
                pid = p.get("id")
                if not pid or pid in self.seen:
                    continue
                # Try to post
                emb = discord.Embed(title=p["title"], url=p["permalink"], color=discord.Color.green())
                emb.set_image(url=p["url"])
                emb.set_footer(text=f"r/{p['sub']} • curated by Morpheus")
                try:
                    await ch.send(embed=emb)
                    self.seen.add(pid)
                    _save_seen(self.seen)
                    return True
                except Exception:
                    continue
            return False
        finally:
            self._lock = False

    # ---- admin commands ----
    def _is_admin(self, member: discord.Member | discord.User) -> bool:
        if isinstance(member, discord.Member):
            if member.guild_permissions.manage_guild:
                return True
        if int(getattr(cfg, "OWNER_USER_ID", 0) or 0) == int(member.id):
            return True
        return False

    @app_commands.command(name="memes_config", description="Show memes scheduler settings")
    async def memes_config(self, itx: discord.Interaction):
        await itx.response.send_message(
            f"**Memes config**\n"
            f"- enabled: `{self.enabled}`\n"
            f"- channel_id: `{self.channel_id}`\n"
            f"- interval: `{self.interval_min} min`\n"
            f"- subs: `{', '.join(self.subs)}`\n"
            f"- seen: `{len(self.seen)}`",
            ephemeral=True
        )

    @app_commands.command(name="memes_start", description="(Admin) Start scheduled memes in a channel")
    @app_commands.describe(channel="Channel to post in", interval_min="Minutes between posts (>=15)")
    async def memes_start(self, itx: discord.Interaction, channel: discord.TextChannel, interval_min: int = 120):
        if not self._is_admin(itx.user):
            await itx.response.send_message("Admins only.", ephemeral=True); return
        self.channel_id = channel.id
        self.interval_min = max(15, int(interval_min))
        self.enabled = True
        if not self._loop.is_running():
            self._loop.start()
        await itx.response.send_message(
            f"✅ Memes scheduler enabled in {channel.mention} every {self.interval_min} min.", ephemeral=True
        )

    @app_commands.command(name="memes_stop", description="(Admin) Stop scheduled memes")
    async def memes_stop(self, itx: discord.Interaction):
        if not self._is_admin(itx.user):
            await itx.response.send_message("Admins only.", ephemeral=True); return
        self.enabled = False
        if self._loop.is_running():
            self._loop.cancel()
        await itx.response.send_message("🛑 Memes scheduler stopped.", ephemeral=True)

    @app_commands.command(name="memes_now", description="(Admin) Post one meme now")
    async def memes_now(self, itx: discord.Interaction):
        if not self._is_admin(itx.user):
            await itx.response.send_message("Admins only.", ephemeral=True); return
        ok = await self._post_one()
        await itx.response.send_message("Sent ✅" if ok else "No fresh meme found 🙃", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(MemesCog(bot))