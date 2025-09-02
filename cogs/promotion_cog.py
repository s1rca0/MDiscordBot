# cogs/promotion_cog.py
from __future__ import annotations
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config_store import store  # shared key/value memory (stateless across code)
# Keys we use in store:
#   MEMBER_ROLE_ID        -> int (The Construct role id)
#   DOWNGRADE_ROLE_ID     -> int (optional)

log = logging.getLogger(__name__)

# ----------------- helpers -----------------
def _get_role_by_id(guild: discord.Guild, role_id: int | None) -> Optional[discord.Role]:
    if not guild or not role_id:
        return None
    return guild.get_role(int(role_id))

def _resolve_construct_role(guild: discord.Guild) -> Optional[discord.Role]:
    # Prefer stored id
    rid = store.get("MEMBER_ROLE_ID")
    r = _get_role_by_id(guild, rid)
    if r:
        return r
    # Fallback by common names
    for name in ("The Construct", "Construct", "Members", "Member"):
        r = discord.utils.get(guild.roles, name=name)
        if r:
            return r
    return None

def _resolve_downgrade_role(guild: discord.Guild) -> Optional[discord.Role]:
    rid = store.get("DOWNGRADE_ROLE_ID")
    r = _get_role_by_id(guild, rid)
    if r:
        return r
    # Fallback by name if admin created one manually
    for name in ("Downgrade", "Probation", "Muted-Construct"):
        r = discord.utils.get(guild.roles, name=name)
        if r:
            return r
    return None

def _bot_can_assign(guild: discord.Guild, role: discord.Role) -> bool:
    me = guild.me
    if not me or not me.guild_permissions.manage_roles:
        return False
    # bot’s top role must be higher than target
    return me.top_role > role and role < guild.me.top_role

async def _safe_add_role(member: discord.Member, role: discord.Role, reason: str | None = None) -> bool:
    try:
        if role not in member.roles:
            await member.add_roles(role, reason=reason)
        return True
    except discord.Forbidden:
        return False
    except discord.HTTPException:
        return False

async def _safe_remove_role(member: discord.Member, role: discord.Role, reason: str | None = None) -> bool:
    try:
        if role in member.roles:
            await member.remove_roles(role, reason=reason)
        return True
    except discord.Forbidden:
        return False
    except discord.HTTPException:
        return False

# ----------------- Cog -----------------
class PromotionCog(commands.Cog, name="Promotion"):
    """
    Promote users into The Construct and demote them into Downgrade (optional).
    Reads MEMBER_ROLE_ID and DOWNGRADE_ROLE_ID from config_store.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------- Admin wiring -------
    @app_commands.command(name="set_downgrade_role", description="(Admin) Set which role is used for demotions.")
    @app_commands.describe(role="Select the Downgrade/Probation role")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def set_downgrade_role(self, interaction: discord.Interaction, role: discord.Role):
        if interaction.guild is None:
            await interaction.response.send_message("Run this in your server.", ephemeral=True)
            return
        store.set("DOWNGRADE_ROLE_ID", int(role.id))
        await interaction.response.send_message(f"✅ Downgrade role set to {role.mention}.", ephemeral=True)

    @app_commands.command(name="create_downgrade_role", description="(Admin) Create a @Downgrade role quickly.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def create_downgrade_role(self, interaction: discord.Interaction, name: Optional[str] = "Downgrade"):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Run this in your server.", ephemeral=True)
            return
        if not guild.me or not guild.me.guild_permissions.manage_roles:
            await interaction.response.send_message("I need **Manage Roles** to create roles.", ephemeral=True)
            return

        # If already exists, re-use
        existing = discord.utils.get(guild.roles, name=name)
        if existing:
            store.set("DOWNGRADE_ROLE_ID", int(existing.id))
            await interaction.response.send_message(f"ℹ️ Role {existing.mention} already exists. Set as Downgrade role.", ephemeral=True)
            return

        try:
            # Create with no perms; you’ll tune channel overwrites as needed
            new_role = await guild.create_role(name=name, reason="Create Downgrade role")
            store.set("DOWNGRADE_ROLE_ID", int(new_role.id))
            await interaction.response.send_message(f"✅ Created {new_role.mention} and set it as Downgrade role.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("I lack permission to create roles.", ephemeral=True)

    # ------- Promotion / Demotion -------
    @app_commands.command(name="promote", description="(Mod) Promote a user into The Construct.")
    @app_commands.describe(user="Member to promote")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def promote(self, interaction: discord.Interaction, user: discord.Member):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Run this in your server.", ephemeral=True)
            return

        construct = _resolve_construct_role(guild)
        if not construct:
            await interaction.response.send_message(
                "❌ Construct role is not set. Run `/set_member_role` (in roles cog) or rename the role to **The Construct**.",
                ephemeral=True,
            )
            return

        if not _bot_can_assign(guild, construct):
            await interaction.response.send_message(
                f"❌ I can’t assign {construct.mention}. Move my bot role **above** it and grant **Manage Roles**.",
                ephemeral=True,
            )
            return

        ok_add = await _safe_add_role(user, construct, reason=f"Promoted by {interaction.user}")
        # If they had Downgrade, remove it
        downg = _resolve_downgrade_role(guild)
        ok_remove = True
        if downg and downg in user.roles and _bot_can_assign(guild, downg):
            ok_remove = await _safe_remove_role(user, downg, reason=f"Promotion clears Downgrade (by {interaction.user})")

        if ok_add and ok_remove:
            await interaction.response.send_message(f"✅ Promoted {user.mention} to {construct.mention}.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Tried to promote, but I hit a role/permission limit.", ephemeral=True)

    @app_commands.command(name="demote", description="(Mod) Demote a user out of The Construct (adds Downgrade if configured).")
    @app_commands.describe(user="Member to demote", reason="Optional note")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def demote(self, interaction: discord.Interaction, user: discord.Member, reason: Optional[str] = None):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Run this in your server.", ephemeral=True)
            return

        construct = _resolve_construct_role(guild)
        if not construct:
            await interaction.response.send_message(
                "❌ Construct role is not set. Run `/set_member_role` (in roles cog) or rename the role to **The Construct**.",
                ephemeral=True,
            )
            return

        tasks_ok = True
        # Remove Construct
        if _bot_can_assign(guild, construct):
            ok = await _safe_remove_role(user, construct, reason=reason or f"Demoted by {interaction.user}")
            tasks_ok = tasks_ok and ok
        else:
            tasks_ok = False

        # Add Downgrade if configured and assignable
        downg = _resolve_downgrade_role(guild)
        if downg:
            if _bot_can_assign(guild, downg):
                ok = await _safe_add_role(user, downg, reason=reason or f"Demoted by {interaction.user}")
                tasks_ok = tasks_ok and ok
            else:
                tasks_ok = False

        if tasks_ok:
            postfix = f" Reason: {reason}" if reason else ""
            if downg:
                await interaction.response.send_message(
                    f"✅ Demoted {user.mention} (added {downg.mention}).{postfix}", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"✅ Demoted {user.mention}. (Tip: set a Downgrade role with `/set_downgrade_role`.){postfix}",
                    ephemeral=True,
                )
        else:
            await interaction.response.send_message(
                "⚠️ Demotion incomplete. I may lack permission or my role is below the target roles.",
                ephemeral=True,
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(PromotionCog(bot))