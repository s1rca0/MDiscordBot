# cogs/promotion_cog.py
from __future__ import annotations
import os
import logging
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands

log = logging.getLogger(__name__)

CONSTRUCT_ROLE_ID = int(os.getenv("CONSTRUCT_ROLE_ID", "0") or 0)
CONSTRUCT_CHANNEL_ID = int(os.getenv("CONSTRUCT_CHANNEL_ID", "0") or 0)
INTRO_CHANNEL_ID = int(os.getenv("INTRO_CHANNEL_ID", "0") or 0)

def _fmt_ch(guild: discord.Guild, cid: int, fallback_name: str) -> str:
    ch = guild.get_channel(cid) if cid else None
    return ch.mention if isinstance(ch, discord.TextChannel) else f"**#{fallback_name}**"

def _construct_role(guild: discord.Guild) -> Optional[discord.Role]:
    return guild.get_role(CONSTRUCT_ROLE_ID) if CONSTRUCT_ROLE_ID else None

def _dm_construct_embed(guild: discord.Guild, member: discord.Member) -> discord.Embed:
    construct = _fmt_ch(guild, CONSTRUCT_CHANNEL_ID, "the-construct")
    intro = _fmt_ch(guild, INTRO_CHANNEL_ID, "introductions")

    e = discord.Embed(
        title="Access Granted: The Construct",
        description=(
            f"{member.mention}, your clearance has been upgraded.\n\n"
            f"**What unlocked now:**\n"
            f"• Free-form chat with me in {construct}\n"
            f"• Personalized meme drops (opt-in, tuned to your interests)\n"
            f"• Early pings for high-signal announcements\n\n"
            f"**Next steps:**\n"
            f"1) Say hello in {intro}\n"
            f"2) Join {construct} and talk to me (no command required)\n"
            f"3) Use `/ask` anywhere for focused help"
        ),
        color=discord.Color.gold(),
    )
    e.set_footer(text="Welcome to the inner layer. Stay sharp.")
    return e

class PromotionCog(commands.Cog):
    """Sends a follow-up DM and optional public welcome when a member is promoted to the Construct."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Detect role gained (Construct)
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        try:
            if before.guild is None or after.guild is None or before.bot or after.bot:
                return
            if not CONSTRUCT_ROLE_ID:
                return
            before_roles = {r.id for r in before.roles}
            after_roles = {r.id for r in after.roles}
            gained = after_roles - before_roles
            if CONSTRUCT_ROLE_ID not in gained:
                return

            # DM the member
            try:
                await after.send(embed=_dm_construct_embed(after.guild, after))
            except Exception:
                pass

            # Optional short welcome in #the-construct
            if CONSTRUCT_CHANNEL_ID:
                ch = after.guild.get_channel(CONSTRUCT_CHANNEL_ID)
                if isinstance(ch, discord.TextChannel):
                    try:
                        await ch.send(f"Welcome aboard, {after.mention}. The floor is yours.")
                    except Exception:
                        pass
        except Exception as e:
            log.warning("promotion handler failed: %s", e)

    # Admin/owner utility to re-send the Construct DM to someone
    @app_commands.command(name="construct_welcome_preview", description="(Admin) Send the Construct unlock DM to a member")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def construct_welcome_preview(self, interaction: discord.Interaction, member: discord.Member):
        if interaction.guild is None:
            await interaction.response.send_message("Run this inside a server.", ephemeral=True)
            return
        try:
            await member.send(embed=_dm_construct_embed(interaction.guild, member))
            await interaction.response.send_message(f"Sent preview DM to {member.mention}.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Couldn’t DM them ({e.__class__.__name__}).", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(PromotionCog(bot))