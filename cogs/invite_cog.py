# cogs/invite_cog.py
from __future__ import annotations

import os
import re
import discord
from discord.ext import commands
from discord import app_commands

INVITE_ENV = "SERVER_INVITE_URL"
INVITE_REGEX = re.compile(
    r"^https://(?:discord\.gg|discord(?:app)?\.com/invite)/[A-Za-z0-9\-]+/?$"
)

def get_invite_url() -> str | None:
    url = os.getenv(INVITE_ENV, "").strip()
    return url if INVITE_REGEX.match(url) else None

def can_manage_guild(inter: discord.Interaction) -> bool:
    perms = inter.user.guild_permissions if isinstance(inter.user, discord.Member) else None
    return bool(perms and (perms.administrator or perms.manage_guild))

class InviteCog(commands.Cog):
    """Secure invite delivery (DM by default) to avoid AutoMod deletions."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---- slash: /invite ----------------------------------------------------
    @app_commands.command(
        name="invite",
        description="Receive a secure invite link (sent via DM).",
    )
    @app_commands.describe(
        show_here="Post the link here (ephemeral) instead of DM. Useful if your DMs are closed."
    )
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: (i.user.id, i.guild_id))
    async def invite(self, interaction: discord.Interaction, show_here: bool = False):
        invite = get_invite_url()
        if not invite:
            msg = (
                f"⚠️ No valid `{INVITE_ENV}` found. "
                "An admin must set a proper Discord invite URL in environment variables."
            )
            if can_manage_guild(interaction):
                return await interaction.response.send_message(msg, ephemeral=True)
            # regular users get a soft message
            return await interaction.response.send_message(
                "I can't find an invite right now. Please ping an admin.", ephemeral=True
            )

        # try DM first unless user asked for 'here'
        if not show_here:
            try:
                await interaction.user.send(f"🔑 **Your secure invite**\n{invite}")
                return await interaction.response.send_message(
                    "I’ve sent you a DM with the invite. Check your inbox.", ephemeral=True
                )
            except discord.Forbidden:
                # fall through to ephemeral-in-channel
                show_here = True

        # ephemeral in-channel (not visible to others; avoids AutoMod since it's not public)
        await interaction.response.send_message(
            f"🔑 **Your secure invite**\n{invite}",
            ephemeral=True,
        )

    # ---- slash: /invite_preview (admins) -----------------------------------
    @app_commands.command(
        name="invite_preview",
        description="Preview the configured invite (admins).",
    )
    async def invite_preview(self, interaction: discord.Interaction):
        if not can_manage_guild(interaction):
            return await interaction.response.send_message(
                "You need *Manage Server* (or Admin) to use this.", ephemeral=True
            )

        invite = get_invite_url()
        if not invite:
            return await interaction.response.send_message(
                f"⚠️ `{INVITE_ENV}` is missing or invalid. Set a Discord invite URL.",
                ephemeral=True,
            )

        await interaction.response.send_message(
            f"Configured invite:\n{invite}", ephemeral=True
        )

    # ---- user context menu: “DM Invite” ------------------------------------
    @app_commands.context_menu(name="DM Invite")
    async def dm_invite_context(self, interaction: discord.Interaction, member: discord.Member):
        """Right-click a user → Apps → DM Invite (admins only)."""
        if not can_manage_guild(interaction):
            return await interaction.response.send_message(
                "You need *Manage Server* (or Admin) to use this.", ephemeral=True
            )

        invite = get_invite_url()
        if not invite:
            return await interaction.response.send_message(
                f"⚠️ `{INVITE_ENV}` is missing or invalid.", ephemeral=True
            )

        try:
            await member.send(f"🔑 **Invite from {interaction.guild.name}**\n{invite}")
            await interaction.response.send_message(
                f"Sent the invite to **{member.display_name}** via DM.", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "Couldn’t DM that user (DMs closed).", ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(InviteCog(bot))