# cogs/invite_cog.py
# Only provides /invite_status. If another cog already registered it, we quietly skip.
from __future__ import annotations
import os
import discord
from discord import app_commands
from discord.ext import commands

INVITE_URL = os.getenv("SERVER_INVITE_URL", "").strip()

class InviteCog(commands.Cog, name="Invite"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="invite_status", description="Show whether the server invite is configured.")
    async def invite_status(self, interaction: discord.Interaction):
        if INVITE_URL:
            await interaction.response.send_message(f"✅ Invite is set: {INVITE_URL}", ephemeral=True)
        else:
            await interaction.response.send_message("❌ No invite configured (set SERVER_INVITE_URL).", ephemeral=True)

async def setup(bot: commands.Bot):
    # If something else already registered 'invite_status', don't load this cog.
    if bot.tree.get_command("invite_status") is not None:
        return
    await bot.add_cog(InviteCog(bot))