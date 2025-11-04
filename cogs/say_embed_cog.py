# cogs/say_embed_cog.py
from __future__ import annotations
from typing import Optional
import re, json
import discord
from discord import app_commands
from discord.ext import commands

HEX_RE = re.compile(r"^#?([0-9A-Fa-f]{6})$")

def parse_color(s: str | None) -> discord.Color:
    if not s:
        return discord.Color.blurple()
    m = HEX_RE.match(s.strip())
    if m:
        return discord.Color(int(m.group(1), 16))
    named = s.strip().lower() if s else ""
    colors = {
        "red": discord.Color.red(),
        "dark_red": discord.Color.dark_red(),
        "orange": discord.Color.orange(),
        "gold": discord.Color.gold(),
        "yellow": discord.Color.yellow(),
        "green": discord.Color.green(),
        "dark_green": discord.Color.dark_green(),
        "blue": discord.Color.blue(),
        "blurple": discord.Color.blurple(),
        "dark_blue": discord.Color.dark_blue(),
        "purple": discord.Color.purple(),
        "fuchsia": discord.Color.fuchsia(),
        "teal": discord.Color.teal(),
        "dark_teal": discord.Color.dark_teal(),
        "grey": discord.Color.light_grey(),
        "dark_grey": discord.Color.dark_grey(),
        "darker_grey": discord.Color.darker_grey(),
        "lighter_grey": discord.Color.lighter_grey(),
        "magenta": discord.Color.magenta(),
        "brand": discord.Color.brand_red(),
    }
    return colors.get(named, discord.Color.blurple())

class EmbedDraft(discord.ui.Modal, title="Compose Embed"):
    # <= 5 fields total (Discord modal limit)
    title_input = discord.ui.TextInput(
        label="Title",
        placeholder="VEI Netw0rk // PROTOCOLS",
        max_length=256,
        required=False,
    )
    description_input = discord.ui.TextInput(
        label="Description (supports markdown)",
        style=discord.TextStyle.paragraph,
        placeholder="Body text…",
        required=True,
        max_length=4000,
    )
    color_input = discord.ui.TextInput(
        label="Color (hex or name)",
        placeholder="#8e0000, dark_red, teal, blurple…",
        required=False,
        max_length=16,
    )
    footer_input = discord.ui.TextInput(
        label="Footer (optional)",
        placeholder="Veritas et Iustitia — The Balance Between Truth and Justice.",
        required=False,
        max_length=2048,
    )
    media_input = discord.ui.TextInput(
        label="Media URLs (optional)",
        placeholder="image_url[, thumbnail_url]",
        required=False,
        max_length=1024,
    )

    def __init__(self, target_channel: discord.TextChannel, mention_role: Optional[discord.Role], pin: bool):
        # keep children <= 5 inputs
        super().__init__(timeout=300)
        self.target_channel = target_channel
        self.mention_role = mention_role
        self.pin = pin

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        em = discord.Embed(
            title=str(self.title_input.value) if self.title_input.value else None,
            description=str(self.description_input.value),
            color=parse_color(str(self.color_input.value) if self.color_input.value else None),
        )

        if self.footer_input.value:
            em.set_footer(text=str(self.footer_input.value))

        # media: "image[, thumbnail]"
        if self.media_input.value:
            parts = [p.strip() for p in str(self.media_input.value).split(",") if p.strip()]
            if len(parts) >= 1:
                em.set_image(url=parts[0])
            if len(parts) >= 2:
                em.set_thumbnail(url=parts[1])

        # default author to Morpheus (kept out of modal to honor 5-field limit)
        em.set_author(name="Morpheus")

        content = self.mention_role.mention if self.mention_role else None
        msg = await self.target_channel.send(content=content, embed=em)
        if self.pin:
            try:
                await msg.pin(reason="Pinned by /say_embed")
            except discord.Forbidden:
                pass

        await interaction.followup.send(
            f"Posted to {self.target_channel.mention}"
            + (f" and pinned" if self.pin else "")
            + (f"; mentioned {self.mention_role.mention}" if self.mention_role else "")
            + ".",
            ephemeral=True,
        )

class SayEmbedCog(commands.Cog):
    """Flexible posting of embeds without writing a new command each time."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="say_embed", description="Post a custom embed via modal (title/body/color/etc).")
    @app_commands.describe(
        channel="Where to post",
        mention_role="Optional role to @mention on post",
        pin="Pin the message after posting",
    )
    async def say_embed(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        mention_role: Optional[discord.Role] = None,
        pin: Optional[bool] = False,
    ):
        member = interaction.user
        if not isinstance(member, discord.Member) or not (
            member.guild_permissions.manage_messages
            or member.guild_permissions.manage_guild
            or member.guild_permissions.administrator
        ):
            return await interaction.response.send_message(
                "Insufficient permissions. You need **Manage Messages** (or Manage Server / Admin).",
                ephemeral=True,
            )
        await interaction.response.send_modal(EmbedDraft(channel, mention_role, bool(pin)))

    @app_commands.command(
        name="say_embed_json",
        description="Post an embed by JSON (title, description, color, footer, image, thumbnail, author).",
    )
    @app_commands.describe(
        channel="Where to post",
        payload='JSON like {"title":"…","description":"…","color":"#8e0000","footer":"…","image":"…","thumbnail":"…","author":"…"}',
        mention_role="Optional role to @mention on post",
        pin="Pin the message after posting",
    )
    async def say_embed_json(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        payload: str,
        mention_role: Optional[discord.Role] = None,
        pin: Optional[bool] = False,
    ):
        member = interaction.user
        if not isinstance(member, discord.Member) or not (
            member.guild_permissions.manage_messages
            or member.guild_permissions.manage_guild
            or member.guild_permissions.administrator
        ):
            return await interaction.response.send_message(
                "Insufficient permissions. You need **Manage Messages** (or Manage Server / Admin).",
                ephemeral=True,
            )

        try:
            data = json.loads(payload)
            title = data.get("title")
            desc = data.get("description") or data.get("desc")
            if not desc:
                return await interaction.response.send_message("`description` is required.", ephemeral=True)
            color = parse_color(data.get("color"))
            em = discord.Embed(title=title, description=desc, color=color)
            if footer := data.get("footer"):
                em.set_footer(text=str(footer))
            if author := data.get("author"):
                em.set_author(name=str(author))
            else:
                em.set_author(name="Morpheus")
            if thumb := data.get("thumbnail"):
                em.set_thumbnail(url=str(thumb))
            if image := data.get("image"):
                em.set_image(url=str(image))
        except Exception as e:
            return await interaction.response.send_message(f"Invalid JSON: `{e}`", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        content = mention_role.mention if mention_role else None
        msg = await channel.send(content=content, embed=em)
        if pin:
            try:
                await msg.pin(reason="Pinned by /say_embed_json")
            except discord.Forbidden:
                pass
        await interaction.followup.send(
            f"Posted to {channel.mention}"
            + (f" and pinned" if pin else "")
            + (f"; mentioned {mention_role.mention}" if mention_role else "")
            + ".",
            ephemeral=True,
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(SayEmbedCog(bot))
    print("[COGS] Loaded cogs.say_embed_cog")