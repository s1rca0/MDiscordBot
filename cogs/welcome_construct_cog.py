# cogs/welcome_construct_cog.py
from __future__ import annotations
import discord
from discord.ext import commands

from config import cfg

JOIN_TEASER = (
    "**Welcome to Legends In Motion HQ!**\n"
    "You’re in the **Mainframe** layer for now. When you’re promoted to **The Construct**, you’ll unlock:\n"
    "• **💬 Free-chat with Morpheus** (members-only)\n"
    "• **😂 Personalized memes** (opt-in @mentions you can tune)\n"
    "• **🎥 First looks** and YouTube tie-ins\n\n"
    "Stick around, say hi, and a mod will wave you through.\n"
    "> Tip: once promoted you can opt-in with `/meme_ping_on` and set tags via `/meme_tags add cats, marvel, coding`."
)

PROMO_MSG = (
    "🌀 **Welcome to The Construct!** You’ve unlocked member perks:\n\n"
    "**Chat with Morpheus** — talk naturally in this channel.\n"
    "**Personalized Memes** — `/meme_ping_on`, `/meme_tags add ...`, `/meme_tags show`, `/meme_ping_off`.\n"
    "**Stay in the loop** — new drops land in **#announcements** and on YouTube.\n\n"
    "Have fun. 🖤"
)

def _get_text_channel(guild: discord.Guild, chan_id: int, fallback_names: list[str]) -> discord.TextChannel | None:
    if chan_id:
        ch = guild.get_channel(chan_id)
        if isinstance(ch, discord.TextChannel):
            return ch
    # soft fallback by name, case-insensitive
    names = {n.lower(): n for n in fallback_names}
    for ch in guild.text_channels:
        if ch.name.lower() in names:
            return ch
    return None

class WelcomeConstructCog(commands.Cog):
    """
    Adds two lightweight messages without touching existing welcome flows:
    - on_member_join -> intro teaser in INTRO_CHANNEL_ID (or #welcome/#introductions)
    - on role add (CONSTRUCT_ROLE_ID) -> promo in CONSTRUCT_CHANNEL_ID (or #the-construct)
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # read once; we don’t persist anything (Railway Hobby safe)
        self.intro_channel_id = int(getattr(cfg, "INTRO_CHANNEL_ID", 0) or 0)
        self.construct_channel_id = int(getattr(cfg, "CONSTRUCT_CHANNEL_ID", 0) or 0)
        self.construct_role_id = int(getattr(cfg, "CONSTRUCT_ROLE_ID", 0) or 0)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        ch = _get_text_channel(guild, self.intro_channel_id, ["welcome", "introductions"])
        if not ch:
            return  # quiet if not configured
        try:
            await ch.send(JOIN_TEASER)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # Fire only when the Construct role is newly added
        if before.roles == after.roles:
            return
        if self.construct_role_id == 0:
            return
        added = {r.id for r in after.roles} - {r.id for r in before.roles}
        if self.construct_role_id not in added:
            return

        guild = after.guild
        ch = _get_text_channel(guild, self.construct_channel_id, ["the-construct"])
        if not ch:
            return
        try:
            await ch.send(PROMO_MSG)
        except Exception:
            pass

async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeConstructCog(bot))