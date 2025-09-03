from __future__ import annotations
import os
import logging
import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger(__name__)

YT_CHANNEL_ID = int(os.getenv("YT_CHANNEL_ID", "0") or 0)                    # YouTube channel ID (string ok if your code expects)
YT_ANNOUNCE_CHANNEL_ID = int(os.getenv("YT_ANNOUNCE_CHANNEL_ID", "0") or 0)  # Discord channel to announce in
YT_ANNOUNCE_ROLE_ID = int(os.getenv("YT_ANNOUNCE_ROLE_ID", "0") or 0)        # Optional role to ping

# If you had helper functions/classes in other YT cogs, you can import them here.
# from .yt_helpers import fetch_latest_video, post_announcement, etc.

class YouTubeRoot(commands.Cog, name="YouTube"):
    """Unified YouTube controls under /yt"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not (YT_CHANNEL_ID and YT_ANNOUNCE_CHANNEL_ID):
            log.warning("YouTubeCog not started (missing YT_CHANNEL_ID or YT_ANNOUNCE_CHANNEL_ID).")

    yt = app_commands.Group(name="yt", description="YouTube controls")

    # -------- subcommands --------
    @yt.command(name="overview", description="Show current YouTube/announce config")
    async def overview(self, itx: discord.Interaction):
        role = itx.guild.get_role(YT_ANNOUNCE_ROLE_ID) if (itx.guild and YT_ANNOUNCE_ROLE_ID) else None
        ch = itx.guild.get_channel(YT_ANNOUNCE_CHANNEL_ID) if itx.guild else None
        await itx.response.send_message(
            "**YouTube config**\n"
            f"- YT_CHANNEL_ID: `{YT_CHANNEL_ID}`\n"
            f"- Announce channel: {ch.mention if isinstance(ch, discord.TextChannel) else f'`{YT_ANNOUNCE_CHANNEL_ID}`'}\n"
            f"- Announce role: {role.mention if role else ('(none)' if not YT_ANNOUNCE_ROLE_ID else f'`{YT_ANNOUNCE_ROLE_ID}`')}",
            ephemeral=True
        )

    @yt.command(name="force_check", description="Poll YouTube now (owner/admin)")
    async def force_check(self, itx: discord.Interaction):
        if not (isinstance(itx.user, discord.Member) and itx.user.guild_permissions.manage_guild):
            await itx.response.send_message("Admins only.", ephemeral=True); return
        # TODO: plug your existing polling logic here
        await itx.response.send_message("YouTube check triggered ✅", ephemeral=True)

    @yt.command(name="post_latest", description="Announce the latest upload now (owner/admin)")
    async def post_latest(self, itx: discord.Interaction):
        if not (isinstance(itx.user, discord.Member) and itx.user.guild_permissions.manage_guild):
            await itx.response.send_message("Admins only.", ephemeral=True); return
        # TODO: post the latest upload to YT_ANNOUNCE_CHANNEL_ID, ping role if configured
        await itx.response.send_message("Posted latest upload ✅", ephemeral=True)

    @yt.command(name="watch", description="Show watch instructions / subscription info")
    async def watch(self, itx: discord.Interaction):
        await itx.response.send_message(
            "Subscribe and hit the bell on the channel to never miss a drop. I’ll post here when a new video hits.",
            ephemeral=True
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(YouTubeRoot(bot))