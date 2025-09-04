import discord
from discord import app_commands
from discord.ext import commands

VOICE_GROUP_NAME = "voice"  # keeps commands grouped under one top-level name

class VoiceCore(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.command(name="join", description="(Voice) Bot joins your current voice channel")
    async def voice_join(self, interaction: discord.Interaction):
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message("Join a voice channel first.", ephemeral=True)
        vc = interaction.user.voice.channel
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.move_to(vc)
        else:
            await vc.connect()
        await interaction.response.send_message(f"Joined **{vc.name}**.", ephemeral=True)

    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.command(name="leave", description="(Voice) Bot leaves voice")
    async def voice_leave(self, interaction: discord.Interaction):
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect(force=True)
            return await interaction.response.send_message("Left voice.", ephemeral=True)
        await interaction.response.send_message("I’m not in voice.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceCore(bot))