# bot.py
from __future__ import annotations
import asyncio
import logging
import os
from typing import List, Tuple

import discord
from discord.ext import commands

# ---- local config ----
from config import cfg  # your module-level BotConfig instance

# ---------------- logging ----------------
LOG_LEVEL = getattr(logging, cfg.LOG_LEVEL if hasattr(cfg, "LOG_LEVEL") else "INFO", logging.INFO)
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("morpheus.bot")

# ---------------- intents / bot ----------------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True  # needed for listener cogs that read content
intents.guilds = True
intents.guild_messages = True
intents.dm_messages = True
intents.message_content = True

bot = commands.Bot(
    command_prefix=cfg.COMMAND_PREFIX if hasattr(cfg, "COMMAND_PREFIX") else "$",
    intents=intents,
    help_command=None,
)

# Tweak mentions to avoid unwanted @everyone pings
bot.allowed_mentions = discord.AllowedMentions(
    everyone=False, users=True, roles=False, replied_user=False
)

# Command budget (Discord hard limit ~100 global cmds). You can override in env.
COMMAND_BUDGET = int(os.getenv("COMMAND_BUDGET", "100"))

# ---------------- cog sets ----------------
# Load these first. This set mirrors the “working” baseline from your logs.
CORE_COGS: List[str] = [
    "cogs.about_cog",
    "cogs.ai_mode_cog",
    "cogs.backup_clone_cog",
    "cogs.botnick_cog",
    "cogs.chat_cog",
    "cogs.chat_listener_cog",
    "cogs.dev_portal_tools_cog",
    "cogs.digest_cog",
    "cogs.disaster_recovery_cog",
    "cogs.dm_start_cog",
    "cogs.ethics_cog",
    "cogs.faq_cog",
    "cogs.hackin_cog",
    "cogs.health_cog",
    "cogs.help_cog",
    "cogs.invite_cog",
    "cogs.layer_cog",
    "cogs.meme_feed_cog",
    "cogs.memory_bridge_cog",
    "cogs.mission_cog",
    "cogs.mod_recommender_cog",
    "cogs.moderation_cog",
    "cogs.onboarding_fasttrack_cog",
    "cogs.pin_reaction_cog",
    "cogs.presence_cog",
    "cogs.promotion_cog",
    "cogs.roles_cog",
    "cogs.rules_cog",
    "cogs.setup_cog",
    "cogs.tickets_cog",
    "cogs.user_app_cog",
    "cogs.welcome_construct_cog",
    # YouTube core is “safe” to load; it no-ops if IDs missing
    "cogs.youtube_cog",
]

# Optional (often push you over the 100-cmd budget or are truly optional features)
OPTIONAL_COGS: List[str] = [
    "cogs.void_pulse_cog",        # optional signal/void features
    "cogs.wellbeing_cog",         # lots of slash cmds; load if budget allows
    "cogs.youtube_overview_cog",  # summary UX for YT (many cmds)
    "cogs.yt_announcer_cog",      # announces to a role/channel
]

# Optional “feature toggles” by ENV (1/true/on enables; 0/false/off disables)
# If an env toggle is set to false, we won't even attempt the optional load.
OPTIONAL_TOGGLES = {
    "cogs.void_pulse_cog": os.getenv("VOID_PULSE_ENABLE", "1"),
    "cogs.wellbeing_cog": os.getenv("WELLBEING_ENABLE", "1"),
    "cogs.youtube_overview_cog": os.getenv("YOUTUBE_OVERVIEW_ENABLE", "1"),
    "cogs.yt_announcer_cog": os.getenv("YT_ANNOUNCER_ENABLE", "1"),
}

def _enabled(toggle: str | None) -> bool:
    if toggle is None:
        return True
    return str(toggle).strip().lower() in {"1", "true", "yes", "on"}

async def _load_core_cogs() -> Tuple[List[str], List[tuple[str, str]]]:
    loaded, skipped = [], []
    for ext in CORE_COGS:
        try:
            await bot.load_extension(ext)
            loaded.append(ext)
            log.info(f"[loader] Loaded core cog {ext}")
        except discord.app_commands.CommandLimitReached as e:
            skipped.append((ext, f"command budget reached: {e}"))
            log.warning(f"[loader] Skipped core cog {ext} (budget): {e}")
        except discord.app_commands.CommandAlreadyRegistered as e:
            skipped.append((ext, f"command conflict: {e}"))
            log.warning(f"[loader] Skipped core cog {ext} (conflict): {e}")
        except Exception as e:
            skipped.append((ext, f"failed: {e}"))
            log.warning(f"[loader] Failed core cog {ext}: {e}")
    return loaded, skipped

async def _load_optional_cogs() -> Tuple[List[str], List[tuple[str, str]]]:
    """
    Try to load optional cogs one by one. If adding one pushes us past COMMAND_BUDGET,
    immediately unload it and record a 'budget' skip reason.
    Also respects env toggles above.
    """
    loaded, skipped = [], []
    for ext in OPTIONAL_COGS:
        if not _enabled(OPTIONAL_TOGGLES.get(ext)):
            skipped.append((ext, "disabled by env"))
            log.info(f"[loader] Optional cog disabled by env: {ext}")
            continue

        # Pre-check: some groups should be suppressed if required IDs are missing
        if ext in ("cogs.youtube_overview_cog", "cogs.yt_announcer_cog"):
            yt_channel = int(os.getenv("YT_CHANNEL_ID", "0") or 0)
            yt_announce = int(os.getenv("YT_ANNOUNCE_CHANNEL_ID", "0") or 0)
            if yt_channel == 0 or yt_announce == 0:
                skipped.append((ext, "youtube IDs missing"))
                log.info(f"[loader] Optional cog skipped (YouTube IDs missing): {ext}")
                continue

        try:
            await bot.load_extension(ext)
            # budget check
            total_cmds = len(bot.tree.get_commands())
            if total_cmds > COMMAND_BUDGET:
                await bot.unload_extension(ext)
                skipped.append((ext, f"budget: {total_cmds}/{COMMAND_BUDGET} after load"))
                log.info(f"[loader] Optional cog {ext} unloaded (budget {total_cmds}/{COMMAND_BUDGET})")
                continue

            loaded.append(ext)
            log.info(f"[loader] Loaded optional cog {ext} (commands now: {total_cmds})")

        except discord.app_commands.CommandAlreadyRegistered as e:
            skipped.append((ext, f"command conflict: {e}"))
            log.warning(f"[loader] Skipped optional cog {ext} (conflict): {e}")
        except discord.app_commands.CommandLimitReached as e:
            skipped.append((ext, f"command budget reached: {e}"))
            log.warning(f"[loader] Skipped optional cog {ext} (budget): {e}")
        except Exception as e:
            skipped.append((ext, f"failed: {e}"))
            log.warning(f"[loader] Failed optional cog {ext}: {e}")
    return loaded, skipped

async def _sync_commands():
    # Global sync (you’re using global slash commands)
    try:
        cmds = await bot.tree.sync()
        log.info(f"Synced {len(cmds)} commands.")
    except Exception as e:
        log.warning(f"Slash command sync failed: {e}")

@bot.event
async def on_ready():
    # Summarize state once we’re online
    total = len(bot.tree.get_commands())
    active_cogs = ", ".join(sorted(bot.extensions.keys()))
    log.info(f"✅ Logged in as {bot.user} ({bot.user.id})")
    log.info(f"Active cogs: {active_cogs}")
    log.info(f"Total slash commands: {total} (budget={COMMAND_BUDGET})")

async def main():
    # Friendly core config notes
    cfg.validate_core()

    # 1) Load core first
    core_loaded, core_skipped = await _load_core_cogs()

    # 2) Load optional within budget
    opt_loaded, opt_skipped = await _load_optional_cogs()

    # 3) Sync commands after final set is known
    await _sync_commands()

    # 4) Final clean summary in logs
    def _fmt_pairs(pairs: List[tuple[str, str]]) -> str:
        return ", ".join(f"{ext} ({reason})" for ext, reason in pairs) if pairs else "—"

    log.info("----- BOOT SUMMARY -----")
    log.info(f"Core loaded: {', '.join(core_loaded) if core_loaded else '—'}")
    log.info(f"Core skipped: {_fmt_pairs(core_skipped)}")
    log.info(f"Optional loaded: {', '.join(opt_loaded) if opt_loaded else '—'}")
    log.info(f"Optional skipped: {_fmt_pairs(opt_skipped)}")
    log.info("------------------------")

    # 5) Run the bot
    token = cfg.BOT_TOKEN
    if not token:
        log.error("DISCORD_BOT_TOKEN missing. Set it in env.")
        return
    await bot.start(token)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Shutting down...")