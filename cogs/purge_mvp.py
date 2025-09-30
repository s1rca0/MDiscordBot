import discord
from discord import app_commands
from discord.ext import commands
from utils.auth import is_owner

class PurgeMVP(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="purge", description="Owner purge tools")

    @group.command(name="channel", description="Owner: purge recent messages here (safe caps).")
    @app_commands.describe(limit="Max messages to scan (<= 500)", contains="Only delete if message contains this text", exclude_pins="Skip pinned messages")
    async def purge_channel(self, interaction: discord.Interaction, limit: int = 200, contains: str | None = None, exclude_pins: bool = True):
        if not is_owner(interaction.user.id):
            return await interaction.response.send_message("Owner only.", ephemeral=True)
        if limit > 500 or limit < 1:
            return await interaction.response.send_message("Limit must be between 1 and 500.", ephemeral=True)

        chan = interaction.channel
        if not isinstance(chan, discord.TextChannel):
            return await interaction.response.send_message("Run in a text channel.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)
        deleted = 0
        async for msg in chan.history(limit=limit, oldest_first=False):
            if exclude_pins and msg.pinned:
                continue
            if contains and contains.lower() not in (msg.content or "").lower():
                continue
            try:
                await msg.delete()
                deleted += 1
            except discord.Forbidden:
                pass

        await interaction.followup.send(f"🧹 Deleted **{deleted}** messages in {chan.mention}.", ephemeral=True)