# cogs/pin_reaction_cog.py
# React with 📌 to pin (only mods can trigger). Handles cache misses + errors.

from __future__ import annotations
import os
from typing import Set, Optional

import discord
from discord.ext import commands


def _parse_role_ids(env: str = "PIN_ALLOWED_ROLE_IDS") -> Set[int]:
    """
    Optional: restrict who can pin by role.
    Comma-separated role IDs in env PIN_ALLOWED_ROLE_IDS.
    If empty -> rely on channel permission check (Manage Messages).
    """
    raw = (os.getenv(env) or "").strip()
    if not raw:
        return set()
    out = set()
    for tok in raw.replace(" ", "").split(","):
        if tok.isdigit():
            out.add(int(tok))
    return out


class PinReactionCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.allowed_role_ids: Set[int] = _parse_role_ids()

    # --- helpers -------------------------------------------------------------

    def _has_pin_rights(self, member: discord.Member, channel: discord.abc.GuildChannel) -> bool:
        """
        Allow if member has Manage Messages in the channel,
        and (if configured) holds at least one allowed role.
        """
        # permission gate
        perms = channel.permissions_for(member)
        if not perms.manage_messages:
            return False

        # optional role gate
        if not self.allowed_role_ids:
            return True

        member_role_ids = {r.id for r in getattr(member, "roles", [])}
        return bool(self.allowed_role_ids & member_role_ids)

    async def _fetch_member_safe(self, guild: discord.Guild, user_id: int) -> Optional[discord.Member]:
        member = guild.get_member(user_id)
        if member:
            return member
        try:
            return await guild.fetch_member(user_id)
        except Exception:
            return None

    # --- listeners -----------------------------------------------------------

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        # Only 📌 triggers
        if str(payload.emoji) != "📌":
            return
        if not payload.guild_id:
            return  # ignore DMs

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        channel = guild.get_channel(payload.channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        # Ignore bot reactions
        if payload.user_id == self.bot.user.id:
            return

        member = await self._fetch_member_safe(guild, payload.user_id)
        if not member or member.bot:
            return

        # Permission / role check
        if not self._has_pin_rights(member, channel):
            return

        try:
            msg = await channel.fetch_message(payload.message_id)
        except discord.NotFound:
            return
        except discord.Forbidden:
            await channel.send("❌ I’m missing permission to view this message to pin it.")
            return
        except discord.HTTPException:
            return

        # Already pinned? noop.
        if msg.pinned:
            return

        # Pin it
        try:
            await msg.pin()
        except discord.Forbidden:
            await channel.send("❌ I don’t have permission to pin messages here (need **Manage Messages**).")
        except discord.HTTPException as e:
            # Common cause: channel has 50 pins already.
            if "maximum number of pinned messages" in str(e).lower():
                await channel.send("⚠️ This channel already has **50** pinned messages. Unpin something first.")
            # silence other transient errors
            return

    # Optional: unpin when 📌 removed by a mod (comment in if you want)
    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
         if str(payload.emoji) != "📌" or not payload.guild_id:
             return
         guild = self.bot.get_guild(payload.guild_id)
         if not guild:
             return
         channel = guild.get_channel(payload.channel_id)
         if not isinstance(channel, (discord.TextChannel, discord.Thread)):
             return
         member = await self._fetch_member_safe(guild, payload.user_id)
         if not member or member.bot:
             return
         if not self._has_pin_rights(member, channel):
             return
         try:
             msg = await channel.fetch_message(payload.message_id)
             if msg.pinned:
                 await msg.unpin()
         except Exception:
             pass


async def setup(bot: commands.Bot):
    await bot.add_cog(PinReactionCog(bot))