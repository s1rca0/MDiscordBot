import discord
from discord import app_commands
from discord.ext import commands
from config import DEFAULT_BRAND_NICK
from config_store import set_channel, get_channel, set_guild_setting, get_guild_setting

CHANNEL_KINDS = ["welcome", "memes", "void", "open_chat"]

class SetupMVP(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="setup", description="Server setup")

    @group.command(name="set-channel", description="Assign a channel for a feature.")
    @app_commands.describe(kind="welcome/memes/void/open_chat", channel="Target text channel")
    @app_commands.choices(kind=[app_commands.Choice(name=k, value=k) for k in CHANNEL_KINDS])
    async def set_channel_cmd(self, interaction: discord.Interaction, kind: app_commands.Choice[str], channel: discord.TextChannel):
        if not interaction.guild:
            return await interaction.response.send_message("This command must be used in a server.", ephemeral=True)
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not (member and member.guild_permissions.manage_guild):
            return await interaction.response.send_message("Need **Manage Server** permission.", ephemeral=True)
        set_channel(interaction.guild.id, kind.value, channel.id)
        await interaction.response.send_message(f"Saved `{kind.value}` → <#{channel.id}>", ephemeral=True)

    @group.command(name="brand", description="Set this server’s brand nickname.")
    async def brand(self, interaction: discord.Interaction, nickname: str):
        if not interaction.guild:
            return await interaction.response.send_message("This command must be used in a server.", ephemeral=True)
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not (member and member.guild_permissions.manage_guild):
            return await interaction.response.send_message("Need **Manage Server** permission.", ephemeral=True)
        set_guild_setting(interaction.guild.id, "brand", (nickname.strip() or None))
        await interaction.response.send_message(f"Brand nickname set to **{nickname}**", ephemeral=True)

    @group.command(name="list", description="Show current setup values.")
    async def list_settings(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("This command must be used in a server.", ephemeral=True)
        lines: list[str] = []
        brand = get_guild_setting(interaction.guild.id, "brand", None) or DEFAULT_BRAND_NICK
        lines.append(f"**Brand:** {brand}")
        for k in CHANNEL_KINDS:
            cid = get_channel(interaction.guild.id, k, None)
            lines.append(f"**{k}:** " + (f"<#{cid}>" if cid else "_not set_"))
        await interaction.response.send_message("\n".join(lines), ephemeral=True)