#!/usr/bin/env python3
"""
Discord Bot Entry Point
"""

import asyncio
import logging
import os
import sys

from bot import DiscordBot
from keep_alive import keep_alive  # tiny Flask ping server

# ---------- logging ----------
def setup_logging():
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("bot.log")]
    )

# ---------- main ----------
async def main():
    setup_logging()
    log = logging.getLogger("entry")

    # start the keep-alive HTTP server so UptimeRobot can ping it
    try:
        keep_alive()
        log.info("keep_alive web server started.")
    except Exception as e:
        log.warning("keep_alive failed to start (continuing): %s", e)

    # start the Discord bot
    bot = DiscordBot()
    try:
        await bot.start_bot()
    except KeyboardInterrupt:
        log.info("Shutdown requested by user.")
    except Exception as e:
        log.exception("Fatal error starting bot: %s", e)
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot shutdown completed")