# DM-on-demand utilities (module-scope context menu; hobby-safe)
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


def _start_embed(guild: discord.Guild, member: discord.abc.User | discord.Member) -> discord.Embed:
    e = discord.Embed(
        title="M.O.R.P.H.E.U.S. — DM Link",
        description=(
            "I’m awake here. You can use my commands directly in DM for privacy.\n\n"
            "Try **/start** or **/helpdm** (if enabled) to see options. "
            "If you want to return to HQ, use **/invite** at any time."
        ),
        color=discord.Color.blurple(),
    )
    e.set_footer(text=f"{guild.name}")
    return e


class DMStartCog(commands.Cog, name="DM / Start"):
    """Slash helper for mods/owner to trigger the DM."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="dm_start", description="(Admin) DM Morpheus’ start message to a member")
    @app_commands.describe(member="Who should receive the DM?")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def dm_start(self, interaction: discord.Interaction, member: discord.Member):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return
        try:
            await member.send(embed=_start_embed(interaction.guild, member))
            await interaction.response.send_message(f"✅ Sent DM to {member.mention}.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("I can’t DM them (privacy settings).", ephemeral=True)


# --------- User context menu (module-scope) ----------
# IMPORTANT: define OUTSIDE the class
async def _ctx_dm_start(interaction: discord.Interaction, user: discord.User):
    # Only allow mods/owner to trigger this
    ok = False
    if isinstance(interaction.user, discord.Member):
        ok = interaction.user.guild_permissions.manage_guild
    if not ok:
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return

    if interaction.guild is None:
        await interaction.response.send_message("Run this inside a server.", ephemeral=True)
        return

    try:
        await user.send(embed=_start_embed(interaction.guild, user))
        await interaction.response.send_message(f"✅ Sent DM to {user.mention}.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("I can’t DM them (privacy settings).", ephemeral=True)


DM_START_MENU = app_commands.ContextMenu(
    name="DM: Start with Morpheus",
    callback=_ctx_dm_start  # (interaction, user)
)


async def setup(bot: commands.Bot):
    await bot.add_cog(DMStartCog(bot))
    try:
        bot.tree.add_command(DM_START_MENU)
    except Exception:
        # If it already exists (hot-reload), ignore
        pass