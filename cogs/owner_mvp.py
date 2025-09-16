import discord
from discord import app_commands
from discord.ext import commands
from config import __version__
from config_store import set_locked, is_locked
from utils.auth import is_owner

class OwnerMVP(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _owner_only(self, interaction: discord.Interaction) -> bool:
        return is_owner(interaction.user.id)

    @app_commands.command(name="version", description="Show bot version.")
    async def version(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Version: **{__version__}**", ephemeral=True)

    @app_commands.command(name="lock", description="Owner: enable global lockdown.")
    async def lock(self, interaction: discord.Interaction):
        if not self._owner_only(interaction):
            return await interaction.response.send_message("Owner only.", ephemeral=True)
        set_locked(True)
        await interaction.response.send_message("🔒 Global lockdown **enabled**.", ephemeral=True)

    @app_commands.command(name="unlock", description="Owner: disable global lockdown.")
    async def unlock(self, interaction: discord.Interaction):
        if not self._owner_only(interaction):
            return await interaction.response.send_message("Owner only.", ephemeral=True)
        set_locked(False)
        await interaction.response.send_message("🔓 Global lockdown **disabled**.", ephemeral=True)

    @app_commands.command(name="reload", description="Owner: reload MVP cogs.")
    async def reload(self, interaction: discord.Interaction):
        if not self._owner_only(interaction):
            return await interaction.response.send_message("Owner only.", ephemeral=True)
        for cog in list(self.bot.cogs.keys()):
            self.bot.remove_cog(cog)
        from cogs.owner_mvp import OwnerMVP
        from cogs.setup_mvp import SetupMVP
        from cogs.purge_mvp import PurgeMVP
        from cogs.debate_mvp import DebateMVP
        await self.bot.add_cog(OwnerMVP(self.bot))
        await self.bot.add_cog(SetupMVP(self.bot))
        await self.bot.add_cog(PurgeMVP(self.bot))
        await self.bot.add_cog(DebateMVP(self.bot))
        await interaction.response.send_message("♻️ MVP cogs reloaded.", ephemeral=True)