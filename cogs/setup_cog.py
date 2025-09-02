# cogs/setup_cog.py
# Bot setup – configure M.O.R.P.H.E.U.S. from Discord without filesystem/volumes.
from __future__ import annotations
import re
import logging
import discord
from discord import app_commands
from discord.ext import commands

from config import cfg
from ai_mode import get_mode

log = logging.getLogger(__name__)

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
        description="Configure me safely. Stateless config; Railway Hobby ready.",
        color=discord.Color.blurple(),
    )
    e.add_field(name="AI Provider", value=cfg.PROVIDER, inline=True)
    e.add_field(name="Mode", value=get_mode(cfg.AI_MODE_DEFAULT), inline=True)
    e.add_field(name="Logging", value=cfg.LOG_FILE or "stdout", inline=True)

    e.add_field(name="Invites Enabled", value=_ok(cfg.ALLOW_INVITES), inline=True)
    e.add_field(name="Server Invite", value=_link(cfg.SERVER_INVITE_URL), inline=True)
    e.add_field(name="\u200b", value="\u200b", inline=True)

    e.add_field(name="Meme Channel", value=_chan(guild, cfg.MEME_CHANNEL_ID), inline=True)
    e.add_field(name="YT Announce", value=_chan(guild, cfg.YT_ANNOUNCE_CHANNEL_ID), inline=True)
    e.add_field(name="Tickets/Home", value=_chan(guild, cfg.TICKET_HOME_CHANNEL_ID), inline=True)

    e.set_footer(text="Tip: Use the buttons below. No filesystem/volumes needed.")
    return e

def _has_manage_server(inter: discord.Interaction) -> bool:
    if inter.guild is None:
        return False
    if isinstance(inter.user, discord.Member):
        perms = inter.user.guild_permissions
        return perms.administrator or perms.manage_guild
    return False

# ---------------- UI ----------------
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
            await interaction.response.send_message("❌ Invalid invite URL.", ephemeral=True)
            return
        await self.on_ok(interaction, val)

class ChannelPick(discord.ui.ChannelSelect):
    def __init__(self, placeholder: str, on_pick):
        super().__init__(channel_types=[discord.ChannelType.text], min_values=1, max_values=1, placeholder=placeholder)
        self.on_pick = on_pick
    async def callback(self, interaction: discord.Interaction) -> None:
        await self.on_pick(interaction, self.values[0])

# ---------------- Views ----------------
class OverviewView(discord.ui.View):
    def __init__(self, cog: "SetupCog"):
        super().__init__(timeout=300)
        self.cog = cog

        def add_btn(label, style, cb):
            b = discord.ui.Button(label=label, style=style)
            async def _cb(inter: discord.Interaction):
                if not _has_manage_server(inter):
                    await inter.response.send_message("⚠️ Need Manage Server.", ephemeral=True)
                    return
                await cb(inter)
            b.callback = _cb
            self.add_item(b)

        if not cfg.SERVER_INVITE_URL:
            add_btn("Set Invite", discord.ButtonStyle.primary, self._set_invite)
        if not cfg.ALLOW_INVITES:
            add_btn("Enable Invites", discord.ButtonStyle.success, self._enable_invites)
        if not cfg.MEME_CHANNEL_ID:
            add_btn("Pick Meme Channel", discord.ButtonStyle.secondary, self._pick_meme)
        if not cfg.YT_ANNOUNCE_CHANNEL_ID:
            add_btn("Pick YT Channel", discord.ButtonStyle.secondary, self._pick_yt)
        if not cfg.TICKET_HOME_CHANNEL_ID:
            add_btn("Pick Tickets/Home", discord.ButtonStyle.secondary, self._pick_ticket)

        add_btn("Open Settings", discord.ButtonStyle.blurple, self._open_settings)

    async def _set_invite(self, inter: discord.Interaction):
        await inter.response.send_modal(InviteModal(self.cog._set_invite))

    async def _enable_invites(self, inter: discord.Interaction):
        await self.cog._toggle_invites(inter, True)

    async def _pick_meme(self, inter: discord.Interaction):
        await inter.response.send_message("Pick meme channel:", view=self.cog.make_pick_view("MEME_CHANNEL_ID"), ephemeral=True)

    async def _pick_yt(self, inter: discord.Interaction):
        await inter.response.send_message("Pick YT channel:", view=self.cog.make_pick_view("YT_ANNOUNCE_CHANNEL_ID"), ephemeral=True)

    async def _pick_ticket(self, inter: discord.Interaction):
        await inter.response.send_message("Pick Tickets/Home channel:", view=self.cog.make_pick_view("TICKET_HOME_CHANNEL_ID"), ephemeral=True)

    async def _open_settings(self, inter: discord.Interaction):
        await inter.response.edit_message(embed=_embed(inter.guild), view=SettingsView(self.cog))

class SettingsView(discord.ui.View):
    def __init__(self, cog: "SetupCog"):
        super().__init__(timeout=600)
        self.cog = cog

        def add_btn(label, style, cb):
            b = discord.ui.Button(label=label, style=style)
            async def _cb(inter: discord.Interaction):
                if not _has_manage_server(inter):
                    await inter.response.send_message("⚠️ Need Manage Server.", ephemeral=True)
                    return
                await cb(inter)
            b.callback = _cb
            self.add_item(b)

        add_btn("Back to Overview", discord.ButtonStyle.secondary, self._back)
        add_btn("Set Invite", discord.ButtonStyle.primary, self._set_invite)
        if cfg.ALLOW_INVITES:
            add_btn("Disable Invites", discord.ButtonStyle.danger, self._disable_invites)
        else:
            add_btn("Enable Invites", discord.ButtonStyle.success, self._enable_invites)
        add_btn("Mode: smart", discord.ButtonStyle.secondary, self._mode_smart)
        add_btn("Mode: fast", discord.ButtonStyle.secondary, self._mode_fast)
        add_btn("Set Meme Channel", discord.ButtonStyle.secondary, self._pick_meme)
        add_btn("Set YT Channel", discord.ButtonStyle.secondary, self._pick_yt)
        add_btn("Set Tickets/Home", discord.ButtonStyle.secondary, self._pick_ticket)

    async def _back(self, inter: discord.Interaction):
        await inter.response.edit_message(embed=_embed(inter.guild), view=OverviewView(self.cog))
    async def _set_invite(self, inter: discord.Interaction): await inter.response.send_modal(InviteModal(self.cog._set_invite))
    async def _enable_invites(self, inter: discord.Interaction): await self.cog._toggle_invites(inter, True, refresh=True)
    async def _disable_invites(self, inter: discord.Interaction): await self.cog._toggle_invites(inter, False, refresh=True)
    async def _mode_smart(self, inter: discord.Interaction): await self.cog._set_mode(inter, "smart", refresh=True)
    async def _mode_fast(self, inter: discord.Interaction): await self.cog._set_mode(inter, "fast", refresh=True)
    async def _pick_meme(self, inter: discord.Interaction): await inter.response.send_message("Pick meme channel:", view=self.cog.make_pick_view("MEME_CHANNEL_ID", True), ephemeral=True)
    async def _pick_yt(self, inter: discord.Interaction): await inter.response.send_message("Pick YT channel:", view=self.cog.make_pick_view("YT_ANNOUNCE_CHANNEL_ID", True), ephemeral=True)
    async def _pick_ticket(self, inter: discord.Interaction): await inter.response.send_message("Pick Tickets/Home channel:", view=self.cog.make_pick_view("TICKET_HOME_CHANNEL_ID", True), ephemeral=True)

# ---------------- Cog ----------------
class SetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot): self.bot = bot

    @app_commands.command(name="setup", description="Setup overview and quick actions")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_root(self, inter: discord.Interaction):
        if inter.guild is None:
            await inter.response.send_message("❌ Use `/setup` in a server.", ephemeral=True)
            return
        await inter.response.send_message(embed=_embed(inter.guild), view=OverviewView(self), ephemeral=True)

    @app_commands.command(name="setup_dump", description="Show current setup values (IDs + mentions)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_dump(self, inter: discord.Interaction):
        g = inter.guild
        def cd(cid: int): return f"{cid} → {(g.get_channel(cid).mention if g and g.get_channel(cid) else 'Not found')}" if cid else "Not set"
        lines = [
            f"ALLOW_INVITES → {cfg.ALLOW_INVITES}",
            f"SERVER_INVITE_URL → {cfg.SERVER_INVITE_URL or 'Not set'}",
            f"MEME_CHANNEL_ID → {cd(cfg.MEME_CHANNEL_ID)}",
            f"YT_ANNOUNCE_CHANNEL_ID → {cd(cfg.YT_ANNOUNCE_CHANNEL_ID)}",
            f"TICKET_HOME_CHANNEL_ID → {cd(cfg.TICKET_HOME_CHANNEL_ID)}",
            f"AI_MODE_DEFAULT → {cfg.AI_MODE_DEFAULT}",
        ]
        await inter.response.send_message("📋 Current config:\n" + "\n".join(lines), ephemeral=True)

    # Helpers
    async def _set_invite(self, inter, url: str):
        cfg.SERVER_INVITE_URL = url
        log.info(f"Invite set: {url}")
        await inter.response.edit_message(content=f"✅ Invite set: {url}", embed=_embed(inter.guild), view=OverviewView(self))

    async def _toggle_invites(self, inter, on: bool, refresh=False):
        cfg.ALLOW_INVITES = on
        log.info(f"Invites {'enabled' if on else 'disabled'}")
        view = SettingsView(self) if refresh else OverviewView(self)
        await inter.response.edit_message(content=f"✅ Invites {'enabled' if on else 'disabled'}", embed=_embed(inter.guild), view=view)

    async def _set_mode(self, inter, mode: str, refresh=False):
        cfg.AI_MODE_DEFAULT = mode
        log.info(f"Mode set: {mode}")
        view = SettingsView(self) if refresh else OverviewView(self)
        await inter.response.edit_message(content=f"✅ Mode set to {mode}", embed=_embed(inter.guild), view=view)

    def make_pick_view(self, key: str, settings=False):
        async def on_pick(inter, channel: discord.TextChannel):
            setattr(cfg, key, channel.id)
            log.info(f"{key} updated → {channel.name} ({channel.id})")
            await inter.response.edit_message(content=f"✅ {key} → {channel.mention}", embed=_embed(inter.guild), view=None)
        v = discord.ui.View(timeout=120)
        v.add_item(ChannelPick("Pick a text channel…", on_pick))
        return v

async def setup(bot: commands.Bot): await bot.add_cog(SetupCog(bot))