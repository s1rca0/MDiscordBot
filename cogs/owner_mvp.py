# cogs/owner_mvp.py
from __future__ import annotations
from typing import Optional

import os

import discord
from discord import app_commands
from discord.enums import ChannelType
from discord.ext import commands

# ---------------------------------------------------------------------------
# Explicit owner IDs (supports multiple accounts)
# Provide as a comma-separated list in env: OWNER_IDS="123,456"
# Falls back to empty set; _owner_only() will also defer to bot.is_owner()
# ---------------------------------------------------------------------------
OWNER_IDS: set[int] = set()
_raw_owner_ids = os.getenv("OWNER_IDS", "").replace(" ", "")
if _raw_owner_ids:
    for part in _raw_owner_ids.split(","):
        if part.isdigit():
            OWNER_IDS.add(int(part))

# ---------------------------------------------------------------------------
# Simple process-level lockdown latch.
# Other cogs can import is_locked() to gate behavior.
# ---------------------------------------------------------------------------
_LOCKED: bool = False

def is_locked() -> bool:
    return _LOCKED

def set_locked(value: bool) -> None:
    global _LOCKED
    _LOCKED = bool(value)


class OwnerMVP(commands.Cog):
    """Owner utilities grouped under `/owner` to avoid command name conflicts."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ARCH_ROLE_NAME = "ARCHITECT"

    # ---- helpers -----------------------------------------------------------
    async def _owner_only(self, interaction: discord.Interaction) -> bool:
        """Owner gate: explicit OWNER_IDS or bot.is_owner fallback."""
        try:
            if interaction.user.id in OWNER_IDS:
                return True
            return await self.bot.is_owner(interaction.user)
        except Exception:
            return False

    async def _get_or_create_lockdown_role(self, guild: discord.Guild) -> discord.Role | None:
        role = discord.utils.get(guild.roles, name="LOCKDOWN")
        if role is None:
            try:
                role = await guild.create_role(
                    name="LOCKDOWN",
                    permissions=discord.Permissions.none(),
                    mentionable=False,
                    reason="Create LOCKDOWN role for owner lockdown",
                )
            except Exception:
                return None
        return role

    async def _set_presence(self, locked: bool) -> None:
        try:
            if locked:
                await self.bot.change_presence(
                    activity=discord.Activity(type=discord.ActivityType.watching, name="🔒 lockdown mode")
                )
            else:
                await self.bot.change_presence(activity=None)
        except Exception:
            pass

    def _get_role_by_name(self, guild: discord.Guild, name: str) -> discord.Role | None:
        """Case-insensitive role lookup by name."""
        lowered = name.lower()
        for r in guild.roles:
            if r.name.lower() == lowered:
                return r
        return None

    async def _bash_log(self, guild: discord.Guild, title: str, payload: list[str]):
        """Send a bash-styled log block to #fortress-of-solitude if present."""
        try:
            ch = discord.utils.get(guild.text_channels, name="fortress-of-solitude")
            if ch and ch.permissions_for(guild.me).send_messages:
                stamp = discord.utils.utcnow().replace(microsecond=0).isoformat(sep=" ")
                lines = ['```bash', f'pi@veritas:~$ echo "{title}"', *payload, f'[log] timestamp: {stamp}', '```']
                await ch.send("\n".join(lines))
        except Exception:
            pass

    # ---- slash group -------------------------------------------------------
    owner = app_commands.Group(name="owner", description="Owner controls and maintenance")

    # ------------------ sync / status ------------------
    @owner.command(name="reload", description="Re-sync slash commands (safe reload)")
    async def owner_reload(self, interaction: discord.Interaction):
        if not await self._owner_only(interaction):
            return await interaction.response.send_message("Owner only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            if interaction.guild:
                await interaction.client.tree.sync(guild=discord.Object(id=interaction.guild.id))
            else:
                await interaction.client.tree.sync()
            await interaction.followup.send("Reload complete (commands re-synced).", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Reload failed: `{str(e)[:1800]}`", ephemeral=True)

    @owner.command(name="status", description="Show Morpheus lock state")
    async def owner_status(self, interaction: discord.Interaction):
        text = "🔒 **LOCKED**" if is_locked() else "🟢 **UNLOCKED**"
        await interaction.response.send_message(text, ephemeral=True)

    @owner.command(name="nuke_resync", description="Force-clear and re-sync application commands for this guild")
    async def owner_nuke_resync(self, interaction: discord.Interaction):
        if not await self._owner_only(interaction):
            return await interaction.response.send_message("Owner only.", ephemeral=True)
        if interaction.guild is None:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        gobj = discord.Object(id=interaction.guild.id)
        try:
            # Clear registered commands for this guild and re-sync fresh
            interaction.client.tree.clear_commands(guild=gobj)
            await interaction.client.tree.sync(guild=gobj)
            # Also sync globals (helps evict stale globals)
            await interaction.client.tree.sync()
            await interaction.followup.send("Nuked & re-synced commands for this guild.", ephemeral=True)
            await self._bash_log(interaction.guild, "nuke_resync", [f'guild="{interaction.guild.id}"', 'status="ok"'])
        except Exception as e:
            await interaction.followup.send(f"Resync failed: `{str(e)[:1800]}`", ephemeral=True)
            await self._bash_log(interaction.guild, "nuke_resync", [f'guild="{interaction.guild.id}"', f'error="{str(e)[:120]}"'])

    # ------------------ architect mode (toggle hoist; optional grant/revoke) ------------------
    ARCH_ROLE_NAME = "ARCHITECT"

    @owner.command(name="architect_mode", description="Show or hide the ARCHITECT block (toggle hoist).")
    @app_commands.describe(on="true = show as separate group; false = merge into members list")
    async def owner_architect_mode(self, interaction: discord.Interaction, on: bool):
        if not await self._owner_only(interaction):
            return await interaction.response.send_message("Owner only.", ephemeral=True)
        if interaction.guild is None:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        role = self._get_role_by_name(interaction.guild, self.ARCH_ROLE_NAME if hasattr(self, 'ARCH_ROLE_NAME') else ARCH_ROLE_NAME)
        if role is None:
            return await interaction.response.send_message(f"Role **{ARCH_ROLE_NAME}** not found.", ephemeral=True)

        me = interaction.guild.me or await interaction.guild.fetch_member(interaction.client.user.id)
        if me.top_role.position <= role.position and not me.guild_permissions.administrator:
            return await interaction.response.send_message(
                f"Move **{role.name}** below Morpheus’ top role, or grant Administrator.", ephemeral=True
            )

        try:
            await role.edit(hoist=on, reason=f"Architect mode {'ON' if on else 'OFF'} by {interaction.user}")
        except Exception as e:
            return await interaction.response.send_message(f"Failed to edit role: `{str(e)[:1800]}`", ephemeral=True)

        await interaction.response.send_message(f"ARCHITECT mode **{'ENABLED' if on else 'DISABLED'}**.", ephemeral=True)
        await self._bash_log(
            interaction.guild,
            "architect mode toggled",
            [f'state="{ "ON" if on else "OFF" }"', f'role="{role.name}"', f'hoist="{role.hoist}"']
        )

    @owner.command(name="architect_grant", description="Grant ARCHITECT to a member.")
    @app_commands.describe(member="Member to grant ARCHITECT")
    async def owner_architect_grant(self, interaction: discord.Interaction, member: discord.Member):
        if not await self._owner_only(interaction):
            return await interaction.response.send_message("Owner only.", ephemeral=True)
        if interaction.guild is None:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        role = self._get_role_by_name(interaction.guild, self.ARCH_ROLE_NAME if hasattr(self, 'ARCH_ROLE_NAME') else ARCH_ROLE_NAME)
        if role is None:
            return await interaction.response.send_message(f"Role **{ARCH_ROLE_NAME}** not found.", ephemeral=True)
        try:
            await member.add_roles(role, reason=f"ARCHITECT grant by {interaction.user}")
            await interaction.response.send_message(f"Granted **{role.name}** to {member.mention}.", ephemeral=True)
            await self._bash_log(interaction.guild, "architect grant", [f'user="{member.id}"', f'role="{role.name}"'])
        except Exception as e:
            await interaction.response.send_message(f"Grant failed: `{str(e)[:1800]}`", ephemeral=True)

    @owner.command(name="architect_revoke", description="Revoke ARCHITECT from a member.")
    @app_commands.describe(member="Member to revoke ARCHITECT from")
    async def owner_architect_revoke(self, interaction: discord.Interaction, member: discord.Member):
        if not await self._owner_only(interaction):
            return await interaction.response.send_message("Owner only.", ephemeral=True)
        if interaction.guild is None:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        role = self._get_role_by_name(interaction.guild, self.ARCH_ROLE_NAME if hasattr(self, 'ARCH_ROLE_NAME') else ARCH_ROLE_NAME)
        if role is None:
            return await interaction.response.send_message(f"Role **{ARCH_ROLE_NAME}** not found.", ephemeral=True)
        try:
            if role in member.roles:
                await member.remove_roles(role, reason=f"ARCHITECT revoke by {interaction.user}")
            await interaction.response.send_message(f"Revoked **{role.name}** from {member.mention}.", ephemeral=True)
            await self._bash_log(interaction.guild, "architect revoke", [f'user="{member.id}"', f'role="{role.name}"'])
        except Exception as e:
            await interaction.response.send_message(f"Revoke failed: `{str(e)[:1800]}`", ephemeral=True)

    # ------------------ lockdown (global + per-member) ------------------
    @owner.command(name="lock", description="Enable global lockdown, or lock a member")
    @app_commands.describe(member="(Optional) Member to place in LOCKDOWN role")
    async def owner_lock(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        if not await self._owner_only(interaction):
            return await interaction.response.send_message("Owner only.", ephemeral=True)

        if member is not None:
            if interaction.guild is None:
                return await interaction.response.send_message("Use this in a server.", ephemeral=True)
            role = await self._get_or_create_lockdown_role(interaction.guild)
            if role is None:
                return await interaction.response.send_message(
                    "Couldn't create/find **LOCKDOWN** role (need Manage Roles).",
                    ephemeral=True,
                )
            keep_ids = {interaction.guild.id, role.id}
            to_remove = [r for r in member.roles if r.id not in keep_ids]
            try:
                if to_remove:
                    await member.remove_roles(*to_remove, reason="Owner lockdown")
                if role not in member.roles:
                    await member.add_roles(role, reason="Owner lockdown")
                return await interaction.response.send_message(
                    f"🔒 {member.mention} placed into **LOCKDOWN**.", ephemeral=True
                )
            except Exception as e:
                return await interaction.response.send_message(
                    f"Failed to lock member: `{str(e)[:1800]}`", ephemeral=True
                )

        # Global lockdown
        set_locked(True)
        await self._set_presence(True)
        await interaction.response.send_message(
            "🔒 Global **lockdown enabled**. Normal features should pause.",
            ephemeral=True,
        )

    @owner.command(name="unlock", description="Disable global lockdown, or unlock a member")
    @app_commands.describe(member="(Optional) Member to remove from LOCKDOWN role")
    async def owner_unlock(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        if not await self._owner_only(interaction):
            return await interaction.response.send_message("Owner only.", ephemeral=True)

        if member is not None:
            if interaction.guild is None:
                return await interaction.response.send_message("Use this in a server.", ephemeral=True)
            role = discord.utils.get(interaction.guild.roles, name="LOCKDOWN")
            if role is None:
                return await interaction.response.send_message("LOCKDOWN role not found.", ephemeral=True)
            try:
                if role in member.roles:
                    await member.remove_roles(role, reason="Owner unlock")
                return await interaction.response.send_message(
                    f"🔓 {member.mention} removed from **LOCKDOWN**.", ephemeral=True
                )
            except Exception as e:
                return await interaction.response.send_message(
                    f"Failed to unlock member: `{str(e)[:1800]}`", ephemeral=True
                )

        # Global unlock
        set_locked(False)
        await self._set_presence(False)
        await interaction.response.send_message(
            "🔓 Global **lockdown disabled**. Features may resume.",
            ephemeral=True,
        )

    # ------------------ soft clamp (no role edits) ------------------
    def _soft_targets(self, guild: discord.Guild):
        want = {"the-construct", "mainframe"}
        return [c for c in guild.categories if c.name.lower() in want]

    @owner.command(name="softlock", description="Softly clamp categories (no role edits)")
    @app_commands.describe(slowmode_seconds="Slowmode for text channels (0-120). Default 10.")
    async def owner_softlock(self, interaction: discord.Interaction, slowmode_seconds: Optional[int] = 10):
        if not await self._owner_only(interaction):
            return await interaction.response.send_message("Owner only.", ephemeral=True)
        if interaction.guild is None:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        s = max(0, min(int(slowmode_seconds or 10), 120))
        everyone = interaction.guild.default_role
        staff = discord.utils.get(interaction.guild.roles, name="Staff")
        bots = discord.utils.get(interaction.guild.roles, name="B0ts")

        for cat in self._soft_targets(interaction.guild):
            try:
                overwrites = cat.overwrites
                ow = overwrites.get(everyone, discord.PermissionOverwrite())
                ow.send_messages = False
                overwrites[everyone] = ow
                for role in (staff, bots):
                    if role:
                        row = overwrites.get(role, discord.PermissionOverwrite())
                        row.send_messages = True
                        overwrites[role] = row
                await cat.edit(overwrites=overwrites, reason="Owner softlock")
                for ch in cat.text_channels:
                    try:
                        await ch.edit(slowmode_delay=s, reason="Owner softlock")
                    except Exception:
                        pass
            except Exception:
                pass

        await interaction.response.send_message(
            f"🧰 **Softlock applied** (slowmode={s}s, @everyone send denied in targets).",
            ephemeral=True,
        )

    @owner.command(name="softunlock", description="Remove soft clamps from categories")
    async def owner_softunlock(self, interaction: discord.Interaction):
        if not await self._owner_only(interaction):
            return await interaction.response.send_message("Owner only.", ephemeral=True)
        if interaction.guild is None:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        everyone = interaction.guild.default_role
        for cat in self._soft_targets(interaction.guild):
            try:
                overwrites = cat.overwrites
                if everyone in overwrites:
                    ow = overwrites[everyone]
                    ow.send_messages = None
                    overwrites[everyone] = ow
                await cat.edit(overwrites=overwrites, reason="Owner softunlock")
                for ch in cat.text_channels:
                    try:
                        await ch.edit(slowmode_delay=0, reason="Owner softunlock")
                    except Exception:
                        pass
            except Exception:
                pass

        await interaction.response.send_message("🧰 **Softlock removed**.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(OwnerMVP(bot))