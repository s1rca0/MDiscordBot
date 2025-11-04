# cogs/reaction_pill_cog.py
from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

# --- your custom emoji IDs (server-specific) ---
RED_PILL_EMOJI_ID: int = 1410378719180099614
BLUE_PILL_EMOJI_ID: int = 1410378754768896140


class ReactionPillCog(commands.Cog):
    """
    Posts a Morpheus-styled choice embed and listens for reactions.
    Red pill -> grants a role. Blue pill -> no-op (by design).
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Track which messages we should watch for reactions
        self._message_ids: set[int] = set()
        # Default role to grant on red pill (optional)
        self._default_role_id: Optional[int] = None

    # ---------- /offer_pill (slash) ----------
    @app_commands.command(
        name="offer_pill",
        description="Post the Morpheus choice and seed red/blue pill reactions.",
    )
    @app_commands.describe(
        channel="Where to post the choice embed",
        role="Role to grant when the red pill is chosen",
        title="Optional custom title",
        body="Optional custom body",
    )
    async def offer_pill(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        role: Optional[discord.Role] = None,
        title: Optional[str] = None,
        body: Optional[str] = None,
    ):
        """Slash command handler to post the choice embed."""

        # Permission guard: require Manage Roles (server-side)
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.manage_roles:
            return await interaction.response.send_message(
                "You need **Manage Roles** to use this.", ephemeral=True
            )

        # Build the Morpheus-styled embed
        title = title or "The Choice"
        body = body or (
            "**This is your last chance. After this, there is no turning back.**\n"
            "You take the **blue pill** — the story ends.\n"
            "You take the **red pill** — you stay in Wonderland, and I show you how deep the rabbit hole goes.\n"
            "**Choose:** React below."
        )

        em = discord.Embed(title=title, description=body, color=discord.Color.dark_red())
        em.set_author(name="Morpheus")
        em.set_footer(text="React below • Red grants access • Blue does nothing")

        # Send the embed to the requested text channel
        await interaction.response.defer(ephemeral=True)
        msg = await channel.send(embed=em)

        # Seed reactions with your custom emoji
        red = discord.PartialEmoji(name="redpill", id=RED_PILL_EMOJI_ID)
        blue = discord.PartialEmoji(name="bluepill", id=BLUE_PILL_EMOJI_ID)
        try:
            await msg.add_reaction(red)
            await msg.add_reaction(blue)
        except discord.HTTPException:
            # Fallback: if custom emojis fail (e.g., missing in this guild), try Unicode
            await msg.add_reaction("🔴")
            await msg.add_reaction("🔵")

        # Remember which message to watch, and which role to grant
        self._message_ids.add(msg.id)
        self._default_role_id = role.id if role is not None else None

        # Ephemeral confirmation
        guild = channel.guild  # non-optional here
        chosen_role = role or (guild.get_role(self._default_role_id) if self._default_role_id else None)
        role_line = chosen_role.mention if chosen_role else "*no role configured*"
        await interaction.followup.send(
            f"Choice posted in {channel.mention}.\n"
            f"Red pill will grant: {role_line}",
            ephemeral=True,
        )

    # ---------- reaction listener ----------
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Grant the role when a user reacts with the red pill on a tracked message."""
        # Ignore the bot's own reactions
        if payload.user_id == (self.bot.user.id if self.bot.user else 0):
            return

        # Only care about messages we posted
        if payload.message_id not in self._message_ids:
            return

        # Guild required for roles
        if payload.guild_id is None:
            return

        # Only act on the red pill reaction
        is_custom_red = payload.emoji.id == RED_PILL_EMOJI_ID if payload.emoji.id else False
        is_unicode_red = payload.emoji.name == "🔴"  # fallback path
        if not (is_custom_red or is_unicode_red):
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        # Resolve member
        member = guild.get_member(payload.user_id)
        if member is None:
            try:
                member = await guild.fetch_member(payload.user_id)
            except discord.HTTPException:
                return

        # Resolve the role to grant
        role = guild.get_role(self._default_role_id) if self._default_role_id else None
        if role is None:
            return  # nothing configured

        # Grant role
        try:
            await member.add_roles(role, reason="Chose the red pill")
        except discord.Forbidden:
            # Bot lacks permissions or role order is wrong
            pass
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionPillCog(bot))