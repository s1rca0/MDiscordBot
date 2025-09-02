# cogs/botnick_cog.py
import discord
from discord.ext import commands
from discord import app_commands

class BotNickCog(commands.Cog, name="BotNick"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="botnick", description="(Owner/Admin) Set the bot's nickname for this server.")
    @app_commands.describe(nickname="New nickname (e.g., M.O.P.H.E.U.S.)")
    async def botnick(self, interaction: discord.Interaction, nickname: str):
        if interaction.guild is None:
            await interaction.response.send_message("Run in a server.", ephemeral=True)
            return
        member = interaction.guild.get_member(self.bot.user.id)
        if not member:
            await interaction.response.send_message("Could not find my member object.", ephemeral=True)
            return
        try:
            await member.edit(nick=nickname.strip())
            await interaction.response.send_message(f"✅ Nickname updated to **{nickname.strip()}**.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("I need **Manage Nicknames** to do that.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(BotNickCog(bot))