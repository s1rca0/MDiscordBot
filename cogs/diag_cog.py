# cogs/diag_cog.py
from __future__ import annotations
import os
from typing import Optional, List

import discord
from discord.ext import commands
from discord import app_commands


def _owner_ok(user: discord.abc.User) -> bool:
    """Gate all diag commands to OWNER_USER_ID."""
    try:
        owner_id = int(os.getenv("OWNER_USER_ID", "0"))
    except Exception:
        owner_id = 0
    return bool(owner_id) and user.id == owner_id


def _mask(v: str) -> str:
    """Mask env values: keep last 4 if long; show digits-only short IDs as-is."""
    if v is None:
        return ""
    s = str(v)
    if s.isdigit() and len(s) <= 19:
        return s
    if len(s) <= 6:
        return "•••"
    return "••••" + s[-4:]


class DiagCog(commands.Cog, name="Diagnostics"):
    """Owner diagnostics: ping, cogs, cmds, perms, sync, reload, env."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # NOTE: Defining the group as a class attribute is enough.
    # Do NOT add it again in cog_load(); that causes CommandAlreadyRegistered.
    diag = app_commands.Group(name="diag", description="Diagnostics & sync checks")

    # --- /diag ping ----------------------------------------------------------
    @diag.command(name="ping", description="Latency check.")
    async def diag_ping(self, itx: discord.Interaction):
        if not _owner_ok(itx.user):
            await itx.response.send_message("Owner only.", ephemeral=True); return
        lat_ms = int(self.bot.latency * 1000)
        await itx.response.send_message(f"Pong: **{lat_ms}ms**", ephemeral=True)

    # --- /diag cogs ----------------------------------------------------------
    @diag.command(name="cogs", description="List loaded cogs.")
    async def diag_cogs(self, itx: discord.Interaction):
        if not _owner_ok(itx.user):
            await itx.response.send_message("Owner only.", ephemeral=True); return
        loaded = sorted(self.bot.cogs.keys())
        text = "**Loaded cogs** (" + str(len(loaded)) + "):\n" + "\n".join(f"• `{n}`" for n in loaded)
        await itx.response.send_message(text[:1990], ephemeral=True)

    # --- /diag cmds ----------------------------------------------------------
    @diag.command(name="cmds", description="List registered slash commands (guild scope if possible).")
    async def diag_cmds(self, itx: discord.Interaction):
        if not _owner_ok(itx.user):
            await itx.response.send_message("Owner only.", ephemeral=True); return
        try:
            cmds = await itx.client.tree.fetch_commands(guild=itx.guild) if itx.guild else await itx.client.tree.fetch_commands()
        except Exception:
            cmds = await itx.client.tree.fetch_commands()
        lines: List[str] = []
        for c in cmds:
            scope = "guild" if itx.guild else "global"
            lines.append(f"• `/{c.name}` — scope:{scope}")
        text = "**Registered slash commands** (" + str(len(cmds)) + "):\n" + ("\n".join(lines) if lines else "*(none)*")
        await itx.response.send_message(text[:1990], ephemeral=True)

    # --- /diag perms ---------------------------------------------------------
    @diag.command(name="perms", description="Show your effective permissions in this channel.")
    async def diag_perms(self, itx: discord.Interaction):
        if not _owner_ok(itx.user):
            await itx.response.send_message("Owner only.", ephemeral=True); return
        if not (isinstance(itx.user, discord.Member) and isinstance(itx.channel, (discord.TextChannel, discord.Thread))):
            await itx.response.send_message("Run this inside a server text channel.", ephemeral=True); return
        perms = itx.channel.permissions_for(itx.user)
        try:
            flags = [name for name, val in perms if val]
        except Exception:
            flags = [k for k, v in perms.__dict__.items() if isinstance(v, bool) and v]
        text = "**Your effective permissions here:**\n" + (", ".join(sorted(flags)) if flags else "_(none)_")
        await itx.response.send_message(text[:1990], ephemeral=True)

    # --- /diag sync ----------------------------------------------------------
    @diag.command(name="sync", description="Force re-sync of application commands to this guild (or global).")
    async def diag_sync(self, itx: discord.Interaction):
        if not _owner_ok(itx.user):
            await itx.response.send_message("Owner only.", ephemeral=True); return
        try:
            if itx.guild:
                self.bot.tree.copy_global_to(guild=itx.guild)
                cmds = await self.bot.tree.sync(guild=itx.guild)
                await itx.response.send_message(f"✅ Synced **{len(cmds)}** commands to this guild.", ephemeral=True)
            else:
                cmds = await self.bot.tree.sync()
                await itx.response.send_message(f"✅ Synced **{len(cmds)}** global commands.", ephemeral=True)
        except Exception as e:
            await itx.response.send_message(f"❌ Sync failed: `{e}`", ephemeral=True)

    # --- /diag reload --------------------------------------------------------
    @diag.command(name="reload", description="Reload or load a cog (e.g., cogs.void_pulse_cog).")
    @app_commands.describe(extension="Cog module path, e.g. cogs.reaction_pin_cog")
    async def diag_reload(self, itx: discord.Interaction, extension: str):
        if not _owner_ok(itx.user):
            await itx.response.send_message("Owner only.", ephemeral=True); return
        try:
            if extension in self.bot.extensions:
                await self.bot.reload_extension(extension)
            else:
                await self.bot.load_extension(extension)
            await itx.response.send_message(f"🔄 Reloaded `{extension}`", ephemeral=True)
        except Exception as e:
            await itx.response.send_message(f"❌ Reload failed: `{e}`", ephemeral=True)

    # --- /diag env -----------------------------------------------------------
    @diag.command(name="env", description="Show masked environment variables (owner-only).")
    @app_commands.describe(
        prefix="Optional startswith filter, e.g., VOID_",
        names="Optional CSV whitelist, e.g., OWNER_USER_ID,VOID_BROADCAST_CHANNEL_ID"
    )
    async def diag_env(self, itx: discord.Interaction, prefix: Optional[str] = None, names: Optional[str] = None):
        if not _owner_ok(itx.user):
            await itx.response.send_message("Owner only.", ephemeral=True); return
        env_items = os.environ.items()
        if names:
            wanted = {n.strip() for n in names.split(",") if n.strip()}
            pairs = [(k, os.getenv(k, "")) for k in sorted(wanted)]
        else:
            pairs = []
            for k, v in env_items:
                if prefix and not k.startswith(prefix):
                    continue
                pairs.append((k, v))
            pairs.sort(key=lambda kv: kv[0])
        bubble = [
            "OWNER_USER_ID",
            "ACTIVE_COGS",
            "DISABLED_COGS",
            "VOID_BROADCAST_ENABLE", "VOID_BROADCAST_CHANNEL_ID",
            "VOIDPULSE_*",
            "MEMES_ENABLED", "MEME_CHANNEL_ID", "MEME_INTERVAL_MIN", "MEME_SUBREDDITS",
        ]
        def _score(k: str) -> int:
            for i, tag in enumerate(bubble):
                if tag.endswith("*"):
                    if k.startswith(tag[:-1]): 
                        return i
                elif k == tag:
                    return i
            return 999
        pairs.sort(key=lambda kv: (_score(kv[0]), kv[0]))
        lines: List[str] = []
        for k, v in pairs:
            try:
                lines.append(f"`{k}` = `{_mask(v)}`")
            except Exception:
                continue
        text = "**Environment (masked):**\n" + ("\n".join(lines) if lines else "_(none)_")
        await itx.response.send_message(text[:1990], ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(DiagCog(bot))
