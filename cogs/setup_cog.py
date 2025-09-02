# cogs/setup_cog.py
from __future__ import annotations
import re
import discord
from discord import app_commands
from discord.ext import commands

from config import cfg
from config_store import store
from ai_mode import get_mode

INVITE_RE = re.compile(r"(https?://)?(discord\.gg|discord\.com/invite)/[A-Za-z0-9\-]+")

# ---------------- helpers ----------------
def _ok(v: bool) -> str: return "✅" if v else "❌"
def _link(v: str | None) -> str: return v if v else "Not set"

def _chan(guild: discord.Guild, chan_id: int | None) -> str:
    if not chan_id:
        return "Not set"
    ch = guild.get_channel(chan_id)
    return ch.mention if isinstance(ch, discord.TextChannel) else f"`#{chan_id}` (missing)"

def _embed(guild: discord.Guild) -> discord.Embed:
    e = discord.Embed(
        title="M.O.R.P.H.E.U.S. • Setup",
        description=(
            "Configure me safely. Everything is stateless and works on Railway Hobby.\n"
            "Optional features stay off until their channel or value is set."
        ),
        color=discord.Color.blurple(),
    )
    e.add_field(name="AI Provider", value=cfg.PROVIDER, inline=True)
    e.add_field(name="Mode", value=get_mode(cfg.AI_MODE_DEFAULT), inline=True)
    e.add_field(name="Logging", value=cfg.LOG_FILE or "stdout", inline=True)

    # FIX: read the invite flag from cfg.ALLOW_INVITES (not cfg.ENABLE_INVITES)
    e.add_field(name="Invites Enabled", value=_ok(cfg.ALLOW_INVITES), inline=True)
    e.add_field(name="Server Invite", value=_link(cfg.SERVER_INVITE_URL), inline=True)
    e.add_field(name="\u200b", value="\u200b", inline=True)

    e.add_field(name="Meme Channel", value=_chan(guild, cfg.MEME_CHANNEL_ID), inline=True)
    e.add_field(name="YT Announce", value=_chan(guild, cfg.YT_ANNOUNCE_CHANNEL_ID), inline=True)
    e.add_field(name="Tickets/Home", value=_chan(guild, cfg.TICKET_HOME_CHANNEL_ID), inline=True)

    e.set_footer(text="Tip: Use the buttons below. No filesystem/volumes needed.")
    return e

def _has_manage_server(interaction: discord.Interaction) -> bool:
    # In DMs there is no guild; we only allow this in guilds for safety.
    if interaction.guild is None:
        return False
    user = interaction.user
    if isinstance(user, discord.Member):
        perms = user.guild_permissions
        return perms.administrator or perms.manage_guild
    return False


# ---------------- UI Pieces ----------------
class InviteModal(discord.ui.Modal, title="Set Server Invite"):
    url = discord.ui.TextInput(
        label="Discord invite URL",
        placeholder="https://discord.gg/yourCode",
        required=True,
        max_length=200,
    )
    def __init__(self, on_ok):
        super().__init__()
        self.on_ok = on_ok

    async def on_submit(self, interaction: discord.Interaction) -> None:
        val = str(self.url).strip()
        if not INVITE_RE.fullmatch(val):
            await interaction.response.send_message(
                "Please provide a **valid** Discord invite URL.",
                ephemeral=True
            )
            return
        await self.on_ok(interaction, val)


class ChannelPick(discord.ui.ChannelSelect):
    def __init__(self, placeholder: str, on_pick):
        super().__init__(
            channel_types=[discord.ChannelType.text],
            min_values=1, max_values=1, placeholder=placeholder
        )
        self.on_pick = on_pick

    async def callback(self, interaction: discord.Interaction) -> None:
        chan = self.values[0]
        await self.on_pick(interaction, chan)


# ---------------- Views ----------------
class OverviewView(discord.ui.View):
    """Shows only missing actions + link to full settings."""
    def __init__(self, cog: "SetupCog", *, timeout: float | None = 300):
        super().__init__(timeout=timeout)
        self.cog = cog

        # Button factory to attach callbacks safely
        def add_btn(label, style, cb):
            b = discord.ui.Button(label=label, style=style)
            async def _cb(inter: discord.Interaction):
                if not _has_manage_server(inter):
                    await inter.response.send_message(
                        "You need **Manage Server** to use these controls.",
                        ephemeral=True
                    )
                    return
                await cb(inter)
            b.callback = _cb  # attach per-button callback
            self.add_item(b)

        if not cfg.SERVER_INVITE_URL:
            add_btn("Set Invite", discord.ButtonStyle.primary, self._set_invite)
        if not cfg.ALLOW_INVITES:  # FIX
            add_btn("Enable Invites", discord.ButtonStyle.success, self._enable_invites)
        if not cfg.MEME_CHANNEL_ID:
            add_btn("Pick Meme Channel", discord.ButtonStyle.secondary, self._pick_meme)
        if not cfg.YT_ANNOUNCE_CHANNEL_ID:
            add_btn("Pick YT Channel", discord.ButtonStyle.secondary, self._pick_yt)
        if not cfg.TICKET_HOME_CHANNEL_ID:
            add_btn("Pick Tickets/Home", discord.ButtonStyle.secondary, self._pick_ticket)

        # ButtonStyle.blurple is not a valid enum in discord.py 2.x; use primary
        add_btn("Open Settings", discord.ButtonStyle.primary, self._open_settings)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True

    # per-button handlers
    async def _set_invite(self, interaction: discord.Interaction):
        await interaction.response.send_modal(InviteModal(self.cog._set_invite_then_refresh))

    async def _enable_invites(self, interaction: discord.Interaction):
        await self.cog._toggle_invites(interaction, True, refresh_settings=False)

    async def _pick_meme(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Select a channel:",
            view=self.cog.make_pick_view("MEME_CHANNEL_ID"),
            ephemeral=True
        )

    async def _pick_yt(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Select a channel:",
            view=self.cog.make_pick_view("YT_ANNOUNCE_CHANNEL_ID"),
            ephemeral=True
        )

    async def _pick_ticket(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Select a channel:",
            view=self.cog.make_pick_view("TICKET_HOME_CHANNEL_ID"),
            ephemeral=True
        )

    async def _open_settings(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            embed=_embed(interaction.guild),
            view=SettingsView(self.cog)
        )


class SettingsView(discord.ui.View):
    """Full settings panel – change anything anytime."""
    def __init__(self, cog: "SetupCog", *, timeout: float | None = 600):
        super().__init__(timeout=timeout)
        self.cog = cog

        def add_btn(label, style, cb):
            b = discord.ui.Button(label=label, style=style)
            async def _cb(inter: discord.Interaction):
                if not _has_manage_server(inter):
                    await inter.response.send_message(
                        "You need **Manage Server** to use these controls.",
                        ephemeral=True
                    )
                    return
                await cb(inter)
            b.callback = _cb
            self.add_item(b)

        add_btn("Back to Overview", discord.ButtonStyle.secondary, self._back)
        add_btn("Set Invite", discord.ButtonStyle.primary, self._set_invite)

        if cfg.ALLOW_INVITES:  # FIX
            add_btn("Disable Invites", discord.ButtonStyle.danger, self._disable_invites)
        else:
            add_btn("Enable Invites", discord.ButtonStyle.success, self._enable_invites)

        add_btn("Mode: smart", discord.ButtonStyle.secondary, self._mode_smart)
        add_btn("Mode: fast", discord.ButtonStyle.secondary, self._mode_fast)

        add_btn("Set Meme Channel", discord.ButtonStyle.secondary, self._pick_meme)
        add_btn("Set YT Channel", discord.ButtonStyle.secondary, self._pick_yt)
        add_btn("Set Tickets/Home", discord.ButtonStyle.secondary, self._pick_ticket)

    async def on_timeout(self) -> None:
        for i in self.children:
            i.disabled = True

    # button handlers
    async def _back(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=_embed(interaction.guild),
                                                view=OverviewView(self.cog))

    async def _set_invite(self, interaction: discord.Interaction):
        await interaction.response.send_modal(InviteModal(self.cog._set_invite_then_refresh))

    async def _enable_invites(self, interaction: discord.Interaction):
        await self.cog._toggle_invites(interaction, True, refresh_settings=True)

    async def _disable_invites(self, interaction: discord.Interaction):
        await self.cog._toggle_invites(interaction, False, refresh_settings=True)

    async def _mode_smart(self, interaction: discord.Interaction):
        await self.cog._set_mode(interaction, "smart", refresh_settings=True)

    async def _mode_fast(self, interaction: discord.Interaction):
        await self.cog._set_mode(interaction, "fast", refresh_settings=True)

    async def _pick_meme(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Select a channel:",
            view=self.cog.make_pick_view("MEME_CHANNEL_ID", settings=True),
            ephemeral=True
        )

    async def _pick_yt(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Select a channel:",
            view=self.cog.make_pick_view("YT_ANNOUNCE_CHANNEL_ID", settings=True),
            ephemeral=True
        )

    async def _pick_ticket(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Select a channel:",
            view=self.cog.make_pick_view("TICKET_HOME_CHANNEL_ID", settings=True),
            ephemeral=True
        )


# ---------------- Cog ----------------
class SetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="setup", description="Setup overview and quick actions")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_root(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message(
                "Use `/setup` in a server (not DMs).",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=_embed(interaction.guild),
            view=OverviewView(self),
            ephemeral=True
        )

    # shared helpers
    async def _set_invite_then_refresh(self, interaction: discord.Interaction, url: str):
        store.set("SERVER_INVITE_URL", url)
        cfg.reload_overrides(store.all())
        await interaction.response.edit_message(embed=_embed(interaction.guild),
                                                view=OverviewView(self))

    async def _toggle_invites(self, interaction: discord.Interaction, on: bool, *, refresh_settings: bool = False):
        # We continue to write the override key ENABLE_INVITES for compatibility.
        store.set("ENABLE_INVITES", on)
        cfg.reload_overrides(store.all())
        view = SettingsView(self) if refresh_settings else OverviewView(self)
        await interaction.response.edit_message(
            content=f"Invites {'enabled' if on else 'disabled'}.",
            embed=_embed(interaction.guild),
            view=view
        )

    async def _set_mode(self, interaction: discord.Interaction, mode: str, *, refresh_settings: bool = False):
        store.set("AI_MODE_DEFAULT", mode)
        cfg.reload_overrides(store.all())
        view = SettingsView(self) if refresh_settings else OverviewView(self)
        await interaction.response.edit_message(content=f"Mode set to **{mode}**.",
                                                embed=_embed(interaction.guild), view=view)

    def make_pick_view(self, key: str, settings: bool = False) -> discord.ui.View:
        async def on_pick(inter: discord.Interaction, channel: discord.TextChannel):
            store.set(key, channel.id)
            cfg.reload_overrides(store.all())
            await inter.response.edit_message(content=f"Updated **{key}** → {channel.mention}.", view=None)
        v = discord.ui.View(timeout=120)
        v.add_item(ChannelPick("Pick a text channel…", on_pick))

        close_btn = discord.ui.Button(label="Close", style=discord.ButtonStyle.secondary)
        async def close_cb(inter: discord.Interaction):
            await inter.response.edit_message(content="Closed.", view=None)
        close_btn.callback = close_cb
        v.add_item(close_btn)

        return v


async def setup(bot: commands.Bot):
    await bot.add_cog(SetupCog(bot))