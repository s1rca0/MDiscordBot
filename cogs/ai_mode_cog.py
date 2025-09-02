# cogs/ai_mode_cog.py
import discord
from discord.ext import commands
from discord import app_commands

from config import BotConfig
from ai_mode import get_mode, set_mode

cfg = BotConfig()

class AIModeCog(commands.Cog):
    """Toggle between FAST and SMART models at runtime (no restart)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_admin(self, member: discord.Member | None) -> bool:
        if member is None:
            return False
        if cfg.OWNER_USER_ID and int(member.id) == int(cfg.OWNER_USER_ID):
            return True
        return bool(member.guild_permissions.administrator)

    @app_commands.command(name="ai_mode", description="View or set AI mode (fast/smart).")
    @app_commands.describe(mode="Choose 'fast' or 'smart'. Leave empty to just view current.")
    async def ai_mode(self, interaction: discord.Interaction, mode: str | None = None):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in your server.", ephemeral=True)
            return

        member = interaction.user if isinstance(interaction.user, discord.Member) else None

        if mode is None:
            cur = get_mode(cfg.AI_MODE_DEFAULT)
            await interaction.response.send_message(
                f"Current AI mode: **{cur.upper()}**\n"
                f"- FAST → `{cfg.GROQ_MODEL_FAST}`\n- SMART → `{cfg.GROQ_MODEL_SMART}`",
                ephemeral=True
            )
            return

        mode_l = mode.strip().lower()
        if mode_l not in ("fast", "smart"):
            await interaction.response.send_message("Mode must be `fast` or `smart`.", ephemeral=True)
            return

        if not self._is_admin(member):
            await interaction.response.send_message("Admin/Owner only.", ephemeral=True)
            return

        set_mode("smart" if mode_l == "smart" else "fast")
        await interaction.response.send_message(
            f"✅ AI mode set to **{mode_l.upper()}**.\n"
            f"- FAST → `{cfg.GROQ_MODEL_FAST}`\n- SMART → `{cfg.GROQ_MODEL_SMART}`",
            ephemeral=True
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(AIModeCog(bot))