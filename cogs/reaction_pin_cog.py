# cogs/reaction_pin_cog.py
from __future__ import annotations
import os, json
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands

CFG_PATH = "data/pin_config.json"


def _env_bool(name: str, default: bool) -> bool:
    v = str(os.getenv(name, str(default))).strip().lower()
    return v in ("1", "true", "yes", "on")


def _load_cfg() -> dict:
    try:
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cfg(d: dict) -> None:
    try:
        os.makedirs(os.path.dirname(CFG_PATH), exist_ok=True)
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
    except Exception:
        pass


def _matches_emoji(payload: discord.RawReactionActionEvent, target: str) -> bool:
    """
    True if payload reaction matches `target`, where target may be:
      - unicode literal "📌"
      - a custom emoji id "123456789012345678"
      - a custom emoji markup "<:pin:123456789012345678>"
    """
    if not target:
        return False
    target = target.strip()

    if payload.emoji.is_unicode_emoji():
        return target == payload.emoji.name

    # custom emoji
    eid = str(getattr(payload.emoji, "id", "") or "")
    if not eid:
        return False
    if target.isdigit():
        return target == eid
    if target.startswith("<:") and target.endswith(">") and ":" in target:
        try:
            return target.split(":")[-1].rstrip(">") == eid
        except Exception:
            return False
    return False


async def _fetch_message(bot: commands.Bot, payload: discord.RawReactionActionEvent) -> Optional[discord.Message]:
    if not payload.guild_id:
        return None
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return None
    ch = guild.get_channel(payload.channel_id)
    if not isinstance(ch, (discord.TextChannel, discord.Thread)):
        return None
    try:
        return await ch.fetch_message(payload.message_id)
    except (discord.NotFound, discord.Forbidden):
        return None


def _is_manager(member: Optional[discord.Member],
                manager_role_id: Optional[int],
                require_manage_messages: bool) -> bool:
    if not isinstance(member, discord.Member):
        return False
    if manager_role_id and any(r.id == manager_role_id for r in member.roles):
        return True
    if require_manage_messages:
        return member.guild_permissions.manage_messages
    return False


class ReactionPinCog(commands.Cog, name="Reaction Pins"):
    """
    Modes:
      - vote   : community pins with threshold; managers override at any count.
      - toggle : managers add 📌 to pin, remove 📌 to unpin.

    Settings persist in data/pin_config.json; env vars provide initial defaults:
      PIN_REACTION_EMOJI=📌
      PIN_REACTION_MODE=vote|toggle
      PIN_REACTION_THRESHOLD=3
      PIN_REACTION_AUTOUNPIN=true
      PIN_REACTION_MANAGER_ROLE_ID=<role id>  (optional)
      PIN_REACTION_REQUIRE_MANAGE_MESSAGES=true
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Defaults from environment
        env_defaults = {
            "emoji": os.getenv("PIN_REACTION_EMOJI", "📌").strip(),
            "mode": os.getenv("PIN_REACTION_MODE", "vote").strip().lower(),
            "threshold": max(1, int(os.getenv("PIN_REACTION_THRESHOLD", "3"))),
            "autounpin": _env_bool("PIN_REACTION_AUTOUNPIN", True),
            "manager_role_id": None,
            "require_manage_messages": _env_bool("PIN_REACTION_REQUIRE_MANAGE_MESSAGES", True),
        }
        rid = os.getenv("PIN_REACTION_MANAGER_ROLE_ID", "").strip()
        if rid.isdigit():
            env_defaults["manager_role_id"] = int(rid)

        # Load persisted config and overlay on env defaults
        disk = _load_cfg()
        merged = {**env_defaults, **disk}

        # Live settings
        self.emoji_cfg: str = merged.get("emoji", "📌")
        self.mode: str = "toggle" if merged.get("mode", "vote") == "toggle" else "vote"
        self.threshold: int = int(merged.get("threshold", 3)) if int(merged.get("threshold", 3)) >= 1 else 3
        self.autounpin: bool = bool(merged.get("autounpin", True))
        self.manager_role_id: Optional[int] = merged.get("manager_role_id", None)
        self.require_manage_messages: bool = bool(merged.get("require_manage_messages", True))

        # Ensure disk reflects current
        _save_cfg(self._asdict())

        # Command group for setters
        self.pinset = app_commands.Group(name="pinset", description="Configure reaction pin behavior")
        self.pinset.command(name="emoji", description="Set pin reaction emoji (📌 or <:name:id> or id)")(self._set_emoji)
        self.pinset.command(name="threshold", description="Set crowd vote threshold (>=1)")(self._set_threshold)
        self.pinset.command(name="manager_role", description="Set manager role (or 'none' to clear)")(self._set_manager_role)
        self.pinset.command(name="autounpin", description="Auto-unpin when votes fall below threshold")(self._set_autounpin)
        self.pinset.command(name="require_perms", description="Require Manage Messages for managers")(self._set_require_perms)

    # ---------- utils ----------
    def _asdict(self) -> dict:
        return {
            "emoji": self.emoji_cfg,
            "mode": self.mode,
            "threshold": self.threshold,
            "autounpin": self.autounpin,
            "manager_role_id": self.manager_role_id,
            "require_manage_messages": self.require_manage_messages,
        }

    async def _count_reactors(self, message: discord.Message) -> int:
        tgt = self.emoji_cfg
        for r in message.reactions:
            try:
                if isinstance(r.emoji, str):
                    if r.emoji == tgt:
                        return r.count
                else:
                    eid = str(getattr(r.emoji, "id", "") or "")
                    if not eid:
                        continue
                    if tgt.isdigit() and eid == tgt:
                        return r.count
                    if tgt.startswith("<:"):
                        want = tgt.split(":")[-1].rstrip(">")
                        if eid == want:
                            return r.count
            except Exception:
                continue
        return 0

    async def _pin(self, message: discord.Message):
        try:
            if not message.pinned:
                await message.pin(reason="Reaction pin")
        except discord.Forbidden:
            pass

    async def _unpin(self, message: discord.Message):
        try:
            if message.pinned:
                await message.unpin(reason="Reaction unpin")
        except discord.Forbidden:
            pass

    # ---------- slash commands ----------
    @app_commands.command(name="pinstatus", description="Show pin reaction settings & mode")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def pinstatus(self, itx: discord.Interaction):
        role_str = f"<@&{self.manager_role_id}>" if self.manager_role_id else "—"
        desc = (
            f"**Mode:** `{self.mode}`\n"
            f"**Emoji:** `{self.emoji_cfg}`\n"
            f"**Threshold:** `{self.threshold}`\n"
            f"**Auto-unpin:** `{self.autounpin}`\n"
            f"**Manager role:** {role_str}\n"
            f"**Require Manage Messages:** `{self.require_manage_messages}`"
        )
        await itx.response.send_message(embed=discord.Embed(
            title="Reaction Pins — Status", description=desc, color=discord.Color.blurple()
        ), ephemeral=True)

    @app_commands.command(name="pinmode", description="Switch pin reaction mode (vote/toggle)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def pinmode(self, itx: discord.Interaction, mode: str):
        mode = mode.strip().lower()
        if mode not in ("vote", "toggle"):
            await itx.response.send_message("❌ Mode must be `vote` or `toggle`.", ephemeral=True)
            return
        self.mode = mode
        _save_cfg(self._asdict())
        await itx.response.send_message(f"✅ Mode set to **{self.mode}**.", ephemeral=True)

    # pinset/emoji
    @app_commands.checks.has_permissions(manage_guild=True)
    async def _set_emoji(self, itx: discord.Interaction, emoji: str):
        self.emoji_cfg = emoji.strip()
        _save_cfg(self._asdict())
        await itx.response.send_message(f"✅ Emoji set to `{self.emoji_cfg}`.", ephemeral=True)

    # pinset/threshold
    @app_commands.checks.has_permissions(manage_guild=True)
    async def _set_threshold(self, itx: discord.Interaction, threshold: int):
        if threshold < 1:
            await itx.response.send_message("❌ Threshold must be ≥ 1.", ephemeral=True); return
        self.threshold = threshold
        _save_cfg(self._asdict())
        await itx.response.send_message(f"✅ Threshold set to **{self.threshold}**.", ephemeral=True)

    # pinset/manager_role
    @app_commands.checks.has_permissions(manage_guild=True)
    async def _set_manager_role(self, itx: discord.Interaction, role: Optional[discord.Role] = None, literal: Optional[str] = None):
        """
        Use either the 'role' picker or pass literal='none' to clear via raw text.
        """
        if literal and literal.strip().lower() == "none":
            self.manager_role_id = None
        elif role:
            self.manager_role_id = role.id
        else:
            self.manager_role_id = None
        _save_cfg(self._asdict())
        out = f"<@&{self.manager_role_id}>" if self.manager_role_id else "—"
        await itx.response.send_message(f"✅ Manager role set to {out}.", ephemeral=True)

    # pinset/autounpin
    @app_commands.checks.has_permissions(manage_guild=True)
    async def _set_autounpin(self, itx: discord.Interaction, enable: bool):
        self.autounpin = bool(enable)
        _save_cfg(self._asdict())
        await itx.response.send_message(f"✅ Auto-unpin set to **{self.autounpin}**.", ephemeral=True)

    # pinset/require_perms
    @app_commands.checks.has_permissions(manage_guild=True)
    async def _set_require_perms(self, itx: discord.Interaction, enable: bool):
        self.require_manage_messages = bool(enable)
        _save_cfg(self._asdict())
        await itx.response.send_message(f"✅ Require Manage Messages: **{self.require_manage_messages}**.", ephemeral=True)

    async def cog_load(self):
        try:
            self.bot.tree.add_command(self.pinset)
        except app_commands.CommandAlreadyRegistered:
            pass

    def cog_unload(self):
        try:
            self.bot.tree.remove_command("pinset", type=discord.AppCommandType.chat_input)
        except Exception:
            pass

    # ---------- events ----------
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return
        if not _matches_emoji(payload, self.emoji_cfg):
            return

        message = await _fetch_message(self.bot, payload)
        if not message:
            return

        member = message.guild.get_member(payload.user_id)
        if member and member.bot:
            return

        is_manager = _is_manager(member, self.manager_role_id, self.require_manage_messages)

        if self.mode == "toggle":
            if is_manager:
                await self._pin(message)
            return

        if is_manager:
            await self._pin(message)
            return

        count = await self._count_reactors(message)
        if count >= self.threshold:
            await self._pin(message)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return
        if not _matches_emoji(payload, self.emoji_cfg):
            return

        message = await _fetch_message(self.bot, payload)
        if not message:
            return

        member = message.guild.get_member(payload.user_id)
        is_manager = _is_manager(member, self.manager_role_id, self.require_manage_messages) if member else False

        if self.mode == "toggle":
            if is_manager:
                await self._unpin(message)
            return

        if is_manager:
            await self._unpin(message)
            return

        if self.autounpin:
            count = await self._count_reactors(message)
            if count < self.threshold:
                await self._unpin(message)


async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionPinCog(bot))
