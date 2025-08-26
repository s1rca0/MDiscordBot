#!/usr/bin/env python3
"""
Discord Bot Entry Point
Main file to start the Discord bot application.
"""

import asyncio
import logging
import sys
from bot import DiscordBot

def setup_logging():
    """Configure logging for the bot."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('bot.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )

async def main():
    """Main entry point for the bot."""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        bot = DiscordBot()
        await bot.start_bot()
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested by user")
    except Exception as e:
        logger.error(f"Fatal error starting bot: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot shutdown completed")
