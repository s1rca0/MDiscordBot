# main.py
import os
import logging
import asyncio

from bot import DiscordBot

log = logging.getLogger("entry")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(levelname)s:%(name)s:%(message)s")

# Optional tiny keep-alive (you already run one elsewhere; safe if duplicated)
def keep_alive():
    try:
        from flask import Flask
        app = Flask(__name__)

        @app.get("/")
        def _root():
            return "OK", 200

        port = int(os.getenv("PORT", "8080"))
        log.info("keep_alive web server started.")
        # Run in background thread
        import threading
        t = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False))
        t.daemon = True
        t.start()
    except Exception as e:
        log.warning("keep_alive failed (non-fatal): %s", e)

async def main():
    keep_alive()
    bot = DiscordBot()
    try:
        await bot.start_bot()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.error("Fatal error starting bot: %s", e, exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())