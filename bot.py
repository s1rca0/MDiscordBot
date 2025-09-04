# bot.py
from __future__ import annotations

import os
import logging
import asyncio
from typing import List, Tuple, Optional

import discord
from discord.ext import commands

# -------------------------------------------------
# Logging
# -------------------------------------------------
log = logging.getLogger("morpheus.bot")
if not log.handlers:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

# -------------------------------------------------
# Helper: parse env lists & flags
# -------------------------------------------------
def _parse_int_list(env_val: str | None) -> List[int]:
    out: List[int] = []
    for part in (env_val or "").replace(" ", "").split(","):
        if not part:
            continue
        try:
            out.append(int(part))
        except Exception:
            continue
    return out

def _parse_str_set(env_val: str | None) -> set[str]:
    if not env_val:
        return set()
    return {s.strip() for s in env_val.split(",") if s.strip()}

def _truthy(env_val: str | None, default: bool = True) -> bool:
    if env_val is None:
        return default
    return env_val.strip().lower() in ("1", "true", "yes", "y", "on")

# -------------------------------------------------
# Feature toggles
# -------------------------------------------------
# Keep these cogs in the repo but do not load them (avoid duplicates / 100-cap pressure)
DEFAULT_DISABLED = {
    "cogs.command_hub_cog",      # legacy command-group wrapper (causes dup roots if mixed)
    "cogs.youtube_overview_cog", # optional dashboard-y commands
    "cogs.yt_announcer_cog",     # optional auto-announcer
}
# Override with env if you want to re-enable something later:
#   DISABLED_COGS="cogs.youtube_overview_cog"  (comma-separated)
DISABLED_COGS = DEFAULT_DISABLED | _parse_str_set(os.getenv("DISABLED_COGS"))

# -------------------------------------------------
# Discord Bot
# -------------------------------------------------
class DiscordBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True                     # joins / roles / tickets
        intents.message_content = _truthy(os.getenv("MESSAGE_CONTENT_INTENTS", "true"))
        intents.messages = True
        intents.reactions = True
        intents.presences = True

        super().__init__(
            command_prefix=commands.when_mentioned_or("!"),
            intents=intents,
            help_command=None,
            tree_cls=discord.app_commands.CommandTree,
        )

        self._ready_ping_sent = False
        self.loaded_cogs: List[str] = []
        self.skipped_cogs: List[Tuple[str, str]] = []  # (cog, reason)

        # Optional: developer “fast sync” guilds
        self.dev_guild_ids: List[int] = _parse_int_list(os.getenv("GUILD_IDS"))

    # ------------- Lifecycle -------------

    async def setup_hook(self) -> None:
        """
        Runs before the bot connects to the gateway.
        Load cogs, try to keep under 100-command cap, and sync.
        """
        # 1) Load core/required cogs first (feature logic lives there)
        required_cogs = [
            # Core + utility
            "cogs.setup_cog",
            "cogs.help_cog",
            "cogs.about_cog",
            "cogs.ai_mode_cog",
            "cogs.chat_cog",
            "cogs.chat_listener_cog",
            "cogs.dm_start_cog",
            "cogs.invite_cog",
            "cogs.rules_cog",
            "cogs.moderation_cog",
            "cogs.roles_cog",
            "cogs.tickets_cog",
            "cogs.onboarding_fasttrack_cog",
            "cogs.welcome_construct_cog",
            "cogs.presence_cog",
            "cogs.meme_feed_cog",
            "cogs.user_app_cog",
            "cogs.faq_cog",
            "cogs.digest_cog",
            "cogs.memory_bridge_cog",
            "cogs.layer_cog",
            "cogs.mission_cog",
            "cogs.mod_recommender_cog",
            "cogs.pin_reaction_cog",
            "cogs.void_pulse_cog",
            "cogs.youtube_cog",
            "cogs.backup_clone_cog",
            "cogs.disaster_recovery_cog",
            "cogs.dev_portal_tools_cog",
            "cogs.health_cog",
            "cogs.ethics_cog",
            "cogs.hackin_cog",
            # "cogs.persona",   # intentionally excluded
        ]
        await self._load_cogs(required_cogs, label="required")

        # 2) (Intentionally NOT loading cogs.command_hub_cog; disabled by config)

        # 3) Initial sync
        await self._sync_commands_initial()

        # 4) Try to load optionals, but keep under the cap
        optional_cogs = [
            "cogs.youtube_overview_cog",
            "cogs.yt_announcer_cog",
            "cogs.wellbeing_cog",
        ]
        await self._load_optionals_with_cap(optional_cogs, cap=100)

        # 5) Final sync after optional attempts
        await self._sync_commands_initial()

        # Log summary
        self._log_cog_summary()

    async def on_ready(self) -> None:
        if self._ready_ping_sent:
            return
        self._ready_ping_sent = True

        # Post a startup ping to ops logs (if available)
        await self._ops_ping_startup()

        log.info("✅ Logged in as %s (%s)", self.user, self.user and self.user.id)

    # ------------- Public API used by main.py -------------

    async def start_bot(self) -> None:
        """
        Called by main.py: ensures token exists and starts the bot.
        """
        token = os.getenv("DISCORD_TOKEN")
        if not token:
            raise RuntimeError("DISCORD_TOKEN is missing.")
        await self.start(token)

    # ------------- Cogs loading helpers -------------

    async def _load_cogs(self, names: List[str], label: str = "cogs") -> None:
        for ext in names:
            await self._load_extension_safe(ext)

    async def _load_extension_safe(self, ext: str) -> None:
        # Respect disabled list without deleting files
        if ext in DISABLED_COGS:
            self.skipped_cogs.append((ext, "DisabledByConfig"))
            log.info("Skipped (disabled): %s", ext)
            return

        try:
            await self.load_extension(ext)
            self.loaded_cogs.append(ext)
            log.info("Loaded cogs: %s", ext)
        except Exception as e:
            self.skipped_cogs.append((ext, f"{e.__class__.__name__}: {e}"))
            log.warning("Failed to load %s: %r", ext, e)

    async def _load_optionals_with_cap(self, optional_names: List[str], cap: int = 100) -> None:
        """
        Try to load optional cogs one-by-one, but unload immediately if they push
        the global command count over the cap.
        """
        for ext in optional_names:
            # Skip if it already failed earlier (e.g., import error) or disabled
            if ext in DISABLED_COGS or any(ext == name for (name, _reason) in self.skipped_cogs):
                if ext in DISABLED_COGS:
                    self.skipped_cogs.append((ext, "DisabledByConfig"))
                    log.info("Skipped (disabled): %s", ext)
                continue

            before = len(self.tree.get_commands())
            await self._load_extension_safe(ext)
            after = len(self.tree.get_commands())

            if after > cap:
                # Over the cap: unload and mark as skipped for capacity.
                try:
                    await self.unload_extension(ext)
                except Exception:
                    pass
                if ext in self.loaded_cogs:
                    self.loaded_cogs.remove(ext)
                self.skipped_cogs.append((ext, f"CommandLimitReached: {after} > cap {cap}"))
                log.warning("Unloaded %s due to command cap (%d > %d)", ext, after, cap)
            else:
                log.info("Optional %s kept (commands: %d)", ext, after)

    # ------------- Sync helpers -------------

    async def _sync_commands_initial(self) -> None:
        """
        If GUILD_IDS provided: sync to those guilds (fast). Otherwise, global sync.
        """
        try:
            if self.dev_guild_ids:
                for gid in self.dev_guild_ids:
                    guild = discord.Object(id=gid)
                    await self.tree.sync(guild=guild)
                log.info(
                    "Synced commands (dev guilds: %s). Count=%d",
                    ",".join(map(str, self.dev_guild_ids)),
                    len(self.tree.get_commands()),
                )
            else:
                await self.tree.sync()
                log.info("Synced commands (global). Count=%d", len(self.tree.get_commands()))
        except Exception as e:
            log.warning("Command sync failed: %r", e)

    # ------------- Ops log ping -------------

    async def _ops_ping_startup(self) -> None:
        """
        Send a startup summary to #ops-logs (by ID via env or by name).
        """
        ch = await self._find_ops_channel()
        if not ch:
            return

        loaded = len(self.loaded_cogs)
        skipped = len(self.skipped_cogs)
        cmd_count = len(self.tree.get_commands())

        embed = discord.Embed(
            title="🟢 Morpheus online",
            description="Startup summary",
            color=discord.Color.brand_green(),
        )
        embed.add_field(name="Commands", value=str(cmd_count))
        embed.add_field(name="Cogs loaded", value=str(loaded))
        if skipped:
            first = "\n".join(f"• {name} — {reason[:90]}" for name, reason in self.skipped_cogs[:5])
            more = f"\n…(+{skipped-5} more)" if skipped > 5 else ""
            embed.add_field(name="Skipped", value=first + more, inline=False)

        try:
            await ch.send(embed=embed)
        except Exception:
            pass

    async def _find_ops_channel(self) -> Optional[discord.TextChannel]:
        # 1) By explicit ID
        ch_id = os.getenv("OPS_LOG_CHANNEL_ID")
        if ch_id:
            try:
                cid = int(ch_id)
                ch = self.get_channel(cid)
                if isinstance(ch, discord.TextChannel):
                    return ch
            except Exception:
                pass

        # 2) Fallback: find by name in the first guild where it exists
        for g in self.guilds:
            ch = discord.utils.get(g.text_channels, name="ops-logs")
            if ch:
                return ch
        return None

    # ------------- Diagnostics -------------

    def _log_cog_summary(self) -> None:
        log.info("Loaded cogs: %s", ", ".join(self.loaded_cogs) if self.loaded_cogs else "(none)")
        if self.skipped_cogs:
            s = "; ".join(f"{name} ({reason})" for name, reason in self.skipped_cogs)
            log.info("Skipped/failed cogs: %s", s)
        else:
            log.info("Skipped/failed cogs: (none)")

# -------------------------------------------------
# Module entry (rarely used if main.py constructs the bot)
# -------------------------------------------------
if __name__ == "__main__":
    bot = DiscordBot()
    asyncio.run(bot.start_bot())