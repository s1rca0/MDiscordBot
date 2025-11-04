# cogs/reaction_pill_cog.py
from __future__ import annotations

from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands

# --- your custom emoji IDs (server-specific) ---
RED_PILL_EMOJI_ID: int = 1410378719180099614
BLUE_PILL_EMOJI_ID: int = 1410378754768896140


# =========================
# Role Console (multi-select)
# =========================
class RoleConsoleView(discord.ui.View):
    """Multi-select to toggle any of the provided roles."""

    def __init__(self, roles: List[discord.Role]):
        super().__init__(timeout=None)
        self.roles = roles

        opts = [
            discord.SelectOption(label=r.name, value=str(r.id))
            for r in roles
        ]
        # One menu; you can pick any subset
        self.select = discord.ui.Select(
            placeholder="Toggle roles…",
            min_values=0,
            max_values=len(opts),
            options=opts,
            custom_id="role_console_select",
        )
        self.select.callback = self._on_select  # bind callback
        self.add_item(self.select)

    async def _on_select(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message(
                "This only works in a server.", ephemeral=True
            )

        # Resolve member
        member: Optional[discord.Member]
        member = interaction.guild.get_member(interaction.user.id)
        if member is None:
            try:
                member = await interaction.guild.fetch_member(interaction.user.id)
            except discord.HTTPException:
                return await interaction.response.send_message(
                    "Could not resolve your member record.", ephemeral=True
                )

        picked_ids = {int(v) for v in self.select.values}
        to_add, to_remove = [], []

        for role in self.roles:
            has = role in member.roles
            want = role.id in picked_ids
            if want and not has:
                to_add.append(role)
            if not want and has:
                to_remove.append(role)

        changes = []
        if to_add:
            try:
                await member.add_roles(*to_add, reason="Role Console: add")
                changes.append(f"+{', '.join(r.name for r in to_add)}")
            except discord.Forbidden:
                changes.append("+(insufficient permissions)")
        if to_remove:
            try:
                await member.remove_roles(*to_remove, reason="Role Console: remove")
                changes.append(f"-{', '.join(r.name for r in to_remove)}")
            except discord.Forbidden:
                changes.append("-(insufficient permissions)")

        msg = "Updated: " + ("; ".join(changes) if changes else "no changes.")
        # Use responder safely
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


# =========================
# Red/Blue Pill (buttons)
# =========================
class RolePillView(discord.ui.View):
    """Red/Blue buttons; on Red, grant a role and disable buttons."""

    def __init__(self, grant_role: discord.Role):
        super().__init__(timeout=None)
        self.grant_role = grant_role

    async def _grant(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message(
                "This only works in a server.", ephemeral=True
            )

        # Resolve member
        member: Optional[discord.Member]
        member = guild.get_member(interaction.user.id)
        if member is None:
            try:
                member = await guild.fetch_member(interaction.user.id)
            except discord.HTTPException:
                return await interaction.response.send_message(
                    "Could not resolve your member record.", ephemeral=True
                )

        # Grant role
        try:
            await member.add_roles(self.grant_role, reason="Chose the red pill")
        except discord.Forbidden:
            return await interaction.response.send_message(
                "I need **Manage Roles** and my top role must be **above** the target role.",
                ephemeral=True,
            )
        except discord.HTTPException:
            return await interaction.response.send_message(
                "Discord error while assigning the role.", ephemeral=True
            )

        # Disable buttons after success (reduce spam)
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

        # Safe edit pattern (fixes Pylance warning)
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(view=self)
            else:
                await interaction.response.edit_message(view=self)
        except Exception:
            pass

    @discord.ui.button(
        label="Red Pill",
        style=discord.ButtonStyle.danger,
        emoji=discord.PartialEmoji(name="redpill", id=RED_PILL_EMOJI_ID),
        custom_id="pill_red",
    )
    async def red_pill(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._grant(interaction)

    @discord.ui.button(
        label="Blue Pill",
        style=discord.ButtonStyle.secondary,
        emoji=discord.PartialEmoji(name="bluepill", id=BLUE_PILL_EMOJI_ID),
        custom_id="pill_blue",
    )
    async def blue_pill(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Fair enough. Door stays open.", ephemeral=True)


# =========================
# Cog
# =========================
class ReactionPillCog(commands.Cog):
    """
    Posts a Morpheus-styled choice with buttons.
    Red pill -> grants a role.
    Optionally delivers a Role Console (multi-select) afterward.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- helper: deliver role console to DM or channel ---
    async def _deliver_role_console(
        self,
        member: discord.Member,
        roles: List[discord.Role],
        *,
        dm_fallback: bool,
        channel: Optional[discord.TextChannel],
        title: str = "Role Console",
        desc: str = "Toggle what you want to see."
    ) -> bool:
        view = RoleConsoleView(roles)
        embed = discord.Embed(title=title, description=desc, color=discord.Color.blurple())

        # Prefer channel if provided
        if channel is not None:
            await channel.send(content=member.mention, embed=embed, view=view)
            return True

        # Try DM
        try:
            dm = await member.create_dm()
            await dm.send(embed=embed, view=view)
            return True
        except discord.Forbidden:
            if dm_fallback and channel is not None:
                await channel.send(content=member.mention, embed=embed, view=view)
                return True
            return False

    # =========================
    # 1) Simple pill (only grants role)
    # =========================
    @app_commands.command(
        name="offer_pill",
        description="Post the Morpheus choice (buttons). Red grants the chosen role."
    )
    @app_commands.describe(
        channel="Where to post the choice",
        grant_role="Role to grant when the red pill is chosen",
        title="Optional custom title",
        body="Optional custom body"
    )
    async def offer_pill(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        grant_role: discord.Role,
        title: Optional[str] = None,
        body: Optional[str] = None,
    ):
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.manage_roles:
            return await interaction.response.send_message("You need **Manage Roles**.", ephemeral=True)

        title = title or "The Choice"
        body = body or (
            "**This is your last chance. After this, there is no turning back.**\n"
            "You take the **blue pill** — the story ends.\n"
            "You take the **red pill** — you stay in Wonderland, and I show you how deep the rabbit hole goes.\n"
            "**Choose:** Press a button below."
        )
        em = discord.Embed(title=title, description=body, color=discord.Color.dark_red())
        em.set_author(name="Morpheus")
        em.set_footer(text="Red grants access • Blue does nothing")

        await interaction.response.defer(ephemeral=True)
        await channel.send(embed=em, view=RolePillView(grant_role))
        await interaction.followup.send(
            f"Posted in {channel.mention}. Red → grants {grant_role.mention}.",
            ephemeral=True
        )

    # =========================
    # 2) Role Console on demand
    # =========================
    @app_commands.command(
        name="offer_roles",
        description="Post the Role Console (multi-select) to a channel or DM."
    )
    @app_commands.describe(
        channel="Where to post the console (omit to DM the user who runs the command)",
        role1="First toggleable role",
        role2="Second toggleable role",
        role3="Third toggleable role",
        role4="Fourth toggleable role",
        role5="Fifth toggleable role",
        dm_fallback="If DM fails, post in channel (default: true)"
    )
    async def offer_roles(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        role1: Optional[discord.Role] = None,
        role2: Optional[discord.Role] = None,
        role3: Optional[discord.Role] = None,
        role4: Optional[discord.Role] = None,
        role5: Optional[discord.Role] = None,
        dm_fallback: Optional[bool] = True,
    ):
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.manage_roles:
            return await interaction.response.send_message("You need **Manage Roles**.", ephemeral=True)

        roles = [r for r in [role1, role2, role3, role4, role5] if r is not None]
        if not roles:
            return await interaction.response.send_message("Provide at least one role.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        target_member = interaction.user  # issuer gets the console in DM if no channel
        ok = await self._deliver_role_console(
            target_member, roles,
            dm_fallback=bool(dm_fallback),
            channel=channel
        )
        if ok:
            where = "DMs" if channel is None else channel.mention
            await interaction.followup.send(f"Role Console sent to {where}.", ephemeral=True)
        else:
            await interaction.followup.send("Could not deliver the Role Console.", ephemeral=True)

    # =========================
    # 3) One-shot flow: Pill -> grant -> Console
    # =========================
    @app_commands.command(
        name="offer_pill_flow",
        description="Post the choice; on Red, grant a role and deliver the Role Console."
    )
    @app_commands.describe(
        channel="Where to post the choice",
        grant_role="Role to grant on Red (e.g., @The_Construct)",
        console_channel="Where to send the console (omit to DM)",
        role1="First toggleable role",
        role2="Second toggleable role",
        role3="Third toggleable role",
        role4="Fourth toggleable role",
        role5="Fifth toggleable role",
        dm_fallback="If DM fails, post in console_channel (default: true)"
    )
    async def offer_pill_flow(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        grant_role: discord.Role,
        console_channel: Optional[discord.TextChannel] = None,
        role1: Optional[discord.Role] = None,
        role2: Optional[discord.Role] = None,
        role3: Optional[discord.Role] = None,
        role4: Optional[discord.Role] = None,
        role5: Optional[discord.Role] = None,
        dm_fallback: Optional[bool] = True,
    ):
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.manage_roles:
            return await interaction.response.send_message("You need **Manage Roles**.", ephemeral=True)

        roles = [r for r in [role1, role2, role3, role4, role5] if r is not None]
        if not roles:
            return await interaction.response.send_message("Provide at least one role for the console.", ephemeral=True)

        # Build the Morpheus embed
        em = discord.Embed(
            title="The Choice",
            description=(
                "**This is your last chance. After this, there is no turning back.**\n"
                "You take the **blue pill** — the story ends.\n"
                "You take the **red pill** — you stay in Wonderland, and I show you how deep the rabbit hole goes.\n"
                "**Choose:** Press a button below."
            ),
            color=discord.Color.dark_red(),
        )
        em.set_author(name="Morpheus")
        em.set_footer(text="Red grants access • Blue does nothing")

        parent = self
        class FlowView(RolePillView):
            """Extends RolePillView to also deliver the console after granting."""
            def __init__(self, gr: discord.Role):
                super().__init__(gr)

            async def _grant(self, i: discord.Interaction):
                await super()._grant(i)
                # after buttons are disabled, try to deliver console
                if not i.guild:
                    return
                member = i.guild.get_member(i.user.id) or await i.guild.fetch_member(i.user.id)  # type: ignore
                await parent._deliver_role_console(   # type: ignore
                    member, roles,
                    dm_fallback=bool(dm_fallback),
                    channel=console_channel
                )

        await interaction.response.defer(ephemeral=True)
        await channel.send(embed=em, view=FlowView(grant_role))
        where = "DMs" if console_channel is None else console_channel.mention
        await interaction.followup.send(
            f"Flow posted in {channel.mention}. Red → grants {grant_role.mention} and opens Role Console in {where}.",
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionPillCog(bot))