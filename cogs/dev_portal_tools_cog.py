# dev_portal_tools_cog.py
from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands

class DevPortalTools(commands.Cog, name="Dev Portal Tools"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Only register if the name isn't already used (invite_cog defines /invite_status)
    def _add_invite_status(self):
        if self.bot.tree.get_command("invite_status") is not None:
            return  # skip duplicate
        @app_commands.command(name="invite_status", description="(Dev) Show invite config")
        async def invite_status(interaction: discord.Interaction):
            await interaction.response.send_message("Dev portal view of invite status.", ephemeral=True)
        self.bot.tree.add_command(invite_status)

async def setup(bot: commands.Bot):
    cog = DevPortalTools(bot)
    await bot.add_cog(cog)
    cog._add_invite_status()