# cogs/dm_start_cog.py
# Safe context-menu to open a DM with Morpheus, plus a tiny helper slash.
from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands

CONTEXT_MENU_NAME = "DM: Start with Morpheus"

async def _send_dm(user: discord.abc.User, guild_name: str | None = None):
    try:
        await user.send(
            "▮ Morpheus: I'm here.\n"
            "You can use **/start**, **/ask**, **/helpdm** here in DMs.\n"
            f"{'(This DM was opened from ' + guild_name + '.)' if guild_name else ''}"
        )
        return True
    except Exception:
        return False

# Context menu callback (must be **module-level**, not inside a Cog)
async def dm_start_context(interaction: discord.Interaction, member: discord.Member):
    ok = await _send_dm(member, interaction.guild.name if interaction.guild else None)
    msg = "Sent. Check your DMs." if ok else "I couldn't DM them (privacy settings?)."
    await interaction.response.send_message(msg, ephemeral=True)

# Pre-create the context menu so we can add/remove it in setup/unload
_DM_MENU = app_commands.ContextMenu(
    name=CONTEXT_MENU_NAME,
    callback=dm_start_context,
)

class DMStartCog(commands.Cog, name="DM Starter"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="helpdm", description="Quick reminder of what you can do in DMs with Morpheus.")
    @app_commands.allowed_installs(guilds=True, users=True)
    async def helpdm(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "In DMs you can use:\n"
            "• **/start** – basic intro\n"
            "• **/ask** – ask questions\n"
            "• **/optin /optout** – toggle DM updates",
            ephemeral=(interaction.guild is not None)
        )

async def setup(bot: commands.Bot):
    # Add the context menu (skip if already present)
    if bot.tree.get_command(CONTEXT_MENU_NAME) is None:
        bot.tree.add_command(_DM_MENU)
    await bot.add_cog(DMStartCog(bot))

async def teardown(bot: commands.Bot):
    # Clean removal if this extension unloads
    try:
        bot.tree.remove_command(CONTEXT_MENU_NAME, type=discord.AppCommandType.user)
    except Exception:
        pass