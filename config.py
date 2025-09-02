# config.py
import os
from typing import Optional

def _int_or_none(val: str | None) -> Optional[int]:
    """Convert env var to int or None safely."""
    if not val:
        return None
    try:
        n = int(str(val).strip())
        return n if n > 0 else None
    except Exception:
        return None


class BotConfig:
    def __init__(self):
        # ===== Core =====
        self.BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
        self.COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
        self.DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() in ("1", "true", "yes")
        self.DEFAULT_EMBED_COLOR = int(os.getenv("DEFAULT_EMBED_COLOR", "0x5865F2"), 16)
        self.OWNER_USER_ID = _int_or_none(os.getenv("OWNER_USER_ID"))

        # ===== Provider / Models =====
        self.PROVIDER = os.getenv("PROVIDER", "groq").lower()
        self.GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
        self.GROQ_MODEL_FAST = os.getenv("GROQ_MODEL_FAST", "llama-3.1-8b-instant")
        self.GROQ_MODEL_SMART = os.getenv("GROQ_MODEL_SMART", "llama-3.1-70b-versatile")
        self.AI_MODE_DEFAULT = os.getenv("AI_MODE_DEFAULT", "smart")

        # ===== Invites =====
        self.SERVER_INVITE_URL = os.getenv("SERVER_INVITE_URL", "").strip()

        # ===== Feature Flags =====
        self.ENABLE_INVITES = os.getenv("ENABLE_INVITES", "true").lower() in ("1", "true", "yes")
        self.ENABLE_MEME_FEED = os.getenv("ENABLE_MEME_FEED", "false").lower() in ("1", "true", "yes")
        self.ENABLE_DISASTER_TOOLS = os.getenv("ENABLE_DISASTER_TOOLS", "false").lower() in ("1", "true", "yes")

        # ===== Meme Feed (optional) =====
        self.MEME_CHANNEL_ID = _int_or_none(os.getenv("MEME_CHANNEL_ID"))
        self.MEME_INTERVAL_MIN = int(os.getenv("MEME_INTERVAL_MIN", "120"))

        # ===== VoidPulse defaults =====
        self.VOID_COOLDOWN_HOURS = int(os.getenv("VOID_COOLDOWN_HOURS", "36"))
        self.VOID_TITLE = os.getenv("VOID_TITLE", "⚡ Void Pulse")
        self.VOID_MSG = os.getenv("VOID_MSG", "A ripple passes through the grid...")

        # ===== Optional Channels for /setup =====
        self.WELCOME_CHANNEL_ID = _int_or_none(os.getenv("WELCOME_CHANNEL_ID"))
        self.YT_ANNOUNCE_CHANNEL_ID = _int_or_none(os.getenv("YT_ANNOUNCE_CHANNEL_ID"))
        self.SUPPORT_CHANNEL_ID = _int_or_none(os.getenv("SUPPORT_CHANNEL_ID"))

    # Helpful validation (optional)
    def validate_core(self):
        if not self.BOT_TOKEN:
            raise RuntimeError("DISCORD_BOT_TOKEN is missing in environment variables.")