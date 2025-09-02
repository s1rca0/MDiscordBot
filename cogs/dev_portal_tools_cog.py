# cogs/dev_portal_tools_cog.py
import os
from urllib.parse import urlencode

import discord
from discord.ext import commands
from discord import app_commands


def _owner_id() -> int:
    try:
        return int(os.getenv("OWNER_USER_ID", "0") or 0)
    except Exception:
        return 0


class DevPortalToolsCog(commands.Cog):
    """Owner utilities for Discord Developer Portal / invite hygiene."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="invite_status",
        description="(Owner) Show the private invite URL and scope summary."
    )
    async def invite_status(self, interaction: discord.Interaction):
        owner_id = _owner_id()
        if not owner_id or interaction.user.id != owner_id:
            await interaction.response.send_message("Owner only.", ephemeral=True)
            return

        if self.bot.user is None:
            await interaction.response.send_message(
                "Bot user not ready — try again in a moment.", ephemeral=True
            )
            return

        # Build a PRIVATE invite URL (works with Public Bot OFF)
        params = {
            "client_id": str(self.bot.user.id),
            "scope": "bot applications.commands",
            "permissions": str(8),  # 8 = Administrator
        }
        url = f"https://discord.com/api/oauth2/authorize?{urlencode(params)}"

        embed = discord.Embed(
            title="Invite Status",
            description=(
                "**Scopes:** `bot`, `applications.commands`\n"
                "**Permissions:** `Administrator`\n\n"
                "Because **Public Bot** is OFF, only people with this URL can add Morpheus. "
                "Keep it private.\n\n"
                f"**Invite URL:**\n{url}"
            ),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Tip: store this link in your password manager next to the bot token.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(DevPortalToolsCog(bot))