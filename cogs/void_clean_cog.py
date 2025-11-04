# cogs/void_clean_cog.py
from __future__ import annotations
import os
from typing import Optional

import discord
from discord.ext import commands, tasks
from discord import app_commands

DEF_LIMIT = 200  # how many recent messages to scan per pass

def _is_trash(msg: discord.Message) -> bool:
    # keep pinned + bot messages (your pill embed is pinned & from a bot)
    if msg.pinned:
        return False
    if getattr(msg.author, "bot", False):
        return False
    return True

class VoidCleanCog(commands.Cog):
    """Keeps #v0id tidy by removing non-bot, non-pinned chatter."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Optional autopurge knob via env:
        #   VOID_CHANNEL_ID=123456789
        #   VOID_AUTOPURGE_MINUTES=15
        self._channel_id: Optional[int] = None
        cid = os.getenv("VOID_CHANNEL_ID")
        if cid and cid.isdigit():
            self._channel_id = int(cid)

        minutes = os.getenv("VOID_AUTOPURGE_MINUTES")
        if minutes and minutes.isdigit() and self._channel_id:
            interval = max(5, int(minutes))  # sane floor
            self.autopurge.change_interval(minutes=interval)  # type: ignore[arg-type]
            self.autopurge.start()

    def cog_unload(self):
        if self.autopurge.is_running():
            self.autopurge.cancel()

    async def _purge_once(
        self,
        channel: discord.TextChannel,
        limit: int = DEF_LIMIT,
    ) -> int:
        deleted = await channel.purge(
            limit=limit,
            check=_is_trash,
            bulk=True,
            reason="void_clean",
        )
        return len(deleted)

    # ---- Slash: on-demand clear ----
    @app_commands.command(name="void_clear", description="Purge non-pinned, non-bot messages.")
    @app_commands.describe(
        channel="Target channel (defaults to current).",
        limit=f"How many recent messages to scan (default {DEF_LIMIT}).",
    )
    async def void_clear(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        limit: Optional[int] = None,
    ):
        # Permissions: Manage Messages required to purge
        member_ok = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.manage_messages
        if not member_ok:
            return await interaction.response.send_message(
                "You need **Manage Messages**.", ephemeral=True
            )

        if channel is None:
            if not interaction.channel or not isinstance(interaction.channel, discord.TextChannel):
                return await interaction.response.send_message("Pick a text channel.", ephemeral=True)
            channel = interaction.channel

        await interaction.response.defer(ephemeral=True)
        count = await self._purge_once(channel, limit or DEF_LIMIT)
        await interaction.followup.send(f"Purged **{count}** message(s) in {channel.mention}.", ephemeral=True)

    # ---- Background: auto-purge if env set ----
    @tasks.loop(minutes=30)  # replaced at runtime if env provided
    async def autopurge(self):
        if not self._channel_id:
            return
        chan = self.bot.get_channel(self._channel_id)
        if not isinstance(chan, discord.TextChannel):
            return
        try:
            await self._purge_once(chan, DEF_LIMIT)
        except Exception:
            # stay silent; this is just housekeeping
            pass

async def setup(bot: commands.Bot):
    await bot.add_cog(VoidCleanCog(bot))