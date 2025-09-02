# DM onboarding utilities: /start to open a DM, /helpdm for a DM-optimized help panel.
from __future__ import annotations
import logging
import discord
from discord.ext import commands
from discord import app_commands

from config import cfg

log = logging.getLogger(__name__)


def _welcome_embed(user: discord.abc.User) -> discord.Embed:
    e = discord.Embed(
        title="👋 Welcome!",
        description=(
            "I'm **M.O.R.P.H.E.U.S.** — ready to chat with you directly here.\n\n"
            "Try:\n"
            "• `/ask` — ask me anything\n"
            "• `/helpdm` — a quick DM help panel\n\n"
            "Tip: You don’t have to join a server to use me in DMs. "
            "You can always find me in your **Apps** list on the left."
        ),
        color=discord.Color.blurple(),
    )
    e.set_footer(text="Safe & compliant: I only DM you after you click.")
    if user.display_avatar:
        e.set_thumbnail(url=user.display_avatar.url)
    return e


def _helpdm_embed(user: discord.abc.User) -> discord.Embed:
    lines = [
        "**Core**",
        "• `/ask <prompt>` — ask me anything",
        "• `/start` — (in a server) open a DM with me",
        "• `/helpdm` — this help panel",
    ]

    # If you’ve set a public invite, show it as an optional next step.
    if cfg.SERVER_INVITE_URL:
        lines += [
            "",
            "**Join the server (optional, recommended):**",
            f"{cfg.SERVER_INVITE_URL}",
        ]

    # If you use YT features, hint at them without assuming they’re enabled.
    if cfg.YT_ANNOUNCE_CHANNEL_ID:
        lines += [
            "",
            "_Heads up: in the server, I can post new YouTube drops automatically._",
        ]

    desc = "\n".join(lines)

    e = discord.Embed(
        title="📖 Quick Help (DM)",
        description=desc,
        color=discord.Color.blurple(),
    )
    e.set_footer(text="You can always find me in your Apps list.")
    if user.display_avatar:
        e.set_thumbnail(url=user.display_avatar.url)
    return e


class DMStartCog(commands.Cog):
    """Add /start to open a DM and /helpdm for a DM-optimized help panel."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # /start — best place to kick off a DM greeting
    @app_commands.command(name="start", description="Open a DM with Morpheus and get a quick intro.")
    @app_commands.checks.cooldown(1, 10.0)  # 1 use per 10s per user
    async def start(self, interaction: discord.Interaction):
        user = interaction.user

        # If already in DMs, greet right here.
        if interaction.guild is None:
            try:
                await interaction.response.send_message(embed=_welcome_embed(user), ephemeral=False)
            except discord.Forbidden:
                await interaction.response.send_message(
                    "I couldn’t send here. Please re-open the DM and try `/start` again.",
                    ephemeral=True,
                )
            return

        # In a server → show a button that opens DM and sends greeting
        class StartDMView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=120)

            @discord.ui.button(label="Open DM & Greet", style=discord.ButtonStyle.primary)
            async def open_dm(self, btn: discord.ui.Button, inter: discord.Interaction):
                try:
                    dm = await inter.user.create_dm()
                    await dm.send(embed=_welcome_embed(inter.user))
                    await inter.response.edit_message(
                        content="✅ I’ve sent you a DM. Check your inbox (left sidebar → Apps → M.O.R.P.H.E.U.S.).",
                        view=None,
                    )
                except discord.Forbidden:
                    help_text = (
                        "❌ I couldn’t DM you.\n\n"
                        "**How to enable DMs:**\n"
                        "1) User Settings → Privacy & Safety → allow DMs from server members (or add me via User Install),\n"
                        "2) Then run `/start` again, or click me in **Apps** to chat."
                    )
                    if inter.response.is_done():
                        await inter.edit_original_response(content=help_text, view=None)
                    else:
                        await inter.response.edit_message(content=help_text, view=None)

            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
            async def cancel(self, btn: discord.ui.Button, inter: discord.Interaction):
                await inter.response.edit_message(content="Canceled.", view=None)

        await interaction.response.send_message(
            content="I can DM you a quick intro. Ready?",
            view=StartDMView(),
            ephemeral=True,
        )

    # /helpdm — DM-optimized help (kept separate to avoid clashing with any existing /help)
    @app_commands.command(name="helpdm", description="Show a quick DM help panel for Morpheus.")
    @app_commands.checks.cooldown(1, 5.0)
    async def helpdm(self, interaction: discord.Interaction):
        # Works in DMs or servers (ephemeral in servers).
        embed = _helpdm_embed(interaction.user)
        if interaction.guild is None:
            await interaction.response.send_message(embed=embed, ephemeral=False)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    # Optional context menu: “Message me” (right-click the bot user)
    @app_commands.context_menu(name="Message me")
    async def message_me(self, interaction: discord.Interaction, user: discord.User):
        if user.id != self.bot.user.id:  # only meaningful when target is the bot
            await interaction.response.send_message("Pick **M.O.R.P.H.E.U.S.** to DM.", ephemeral=True)
            return
        try:
            dm = await interaction.user.create_dm()
            await dm.send(embed=_welcome_embed(interaction.user))
            await interaction.response.send_message(
                "✅ DM sent. Check your inbox (left sidebar → Apps).",
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I couldn’t DM you. Enable DMs from this server, then try again.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(DMStartCog(bot))