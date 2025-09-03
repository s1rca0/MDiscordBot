# Server invite utilities (module-scope context menu; hobby-safe)
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from config import cfg  # reads env at import


def _invite_url() -> str | None:
    url = (getattr(cfg, "SERVER_INVITE_URL", "") or "").strip()
    return url or None


def _invite_embed(guild: discord.Guild, url: str) -> discord.Embed:
    e = discord.Embed(
        title=f"Gateway to {guild.name}",
        description=f"Use this link to enter:\n{url}",
        color=discord.Color.green(),
    )
    e.set_footer(text="Share wisely.")
    return e


class InviteCog(commands.Cog, name="Invite"):
    """Slash helpers to share/check the invite."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="invite", description="Show the server invite (ephemeral)")
    async def invite(self, interaction: discord.Interaction):
        url = _invite_url()
        if not url:
            await interaction.response.send_message(
                "No invite configured yet. Set it in `/setup` (Server Invite).",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(embed=_invite_embed(interaction.guild, url), ephemeral=True)

    @app_commands.command(name="invite_dm", description="(Admin) DM the server invite to a member")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(member="Who should receive the invite?")
    async def invite_dm(self, interaction: discord.Interaction, member: discord.Member):
        url = _invite_url()
        if not url:
            await interaction.response.send_message(
                "No invite configured yet. Set it in `/setup` (Server Invite).",
                ephemeral=True,
            )
            return
        try:
            await member.send(embed=_invite_embed(interaction.guild, url))
            await interaction.response.send_message(f"✅ Invite DM’d to {member.mention}.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("I can’t DM them (privacy settings).", ephemeral=True)

    @app_commands.command(name="invite_status", description="Check whether an invite is configured")
    async def invite_status(self, interaction: discord.Interaction):
        url = _invite_url()
        msg = f"Configured ✅\n{url}" if url else "Not configured ❌ — set it in `/setup`."
        await interaction.response.send_message(msg, ephemeral=True)


# --------- User context menu (module-scope) ----------
async def _ctx_send_invite(interaction: discord.Interaction, user: discord.User):
    # Mods/owner only
    ok = False
    if isinstance(interaction.user, discord.Member):
        ok = interaction.user.guild_permissions.manage_guild
    if not ok:
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return

    if interaction.guild is None:
        await interaction.response.send_message("Run this inside a server.", ephemeral=True)
        return

    url = _invite_url()
    if not url:
        await interaction.response.send_message(
            "No invite configured yet. Set it in `/setup` (Server Invite).",
            ephemeral=True,
        )
        return

    try:
        await user.send(embed=_invite_embed(interaction.guild, url))
        await interaction.response.send_message(f"✅ Invite DM’d to {user.mention}.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("I can’t DM them (privacy settings).", ephemeral=True)


SEND_INVITE_MENU = app_commands.ContextMenu(
    name="DM: Server Invite",
    callback=_ctx_send_invite  # (interaction, user)
)


async def setup(bot: commands.Bot):
    await bot.add_cog(InviteCog(bot))
    try:
        bot.tree.add_command(SEND_INVITE_MENU)
    except Exception:
        pass