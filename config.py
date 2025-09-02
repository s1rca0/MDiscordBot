# config.py
import os

def _get(name: str, default=None, cast=str):
    """Read an env var with optional casting and sensible defaults."""
    val = os.getenv(name)
    if val is None or val == "":
        return default
    if cast is bool:
        return str(val).lower() in ("1", "true", "yes", "on")
    if cast is int:
        try:
            return int(val)
        except Exception:
            return default
    return val


class Config:
    # ===== Discord Core =====
    DISCORD_BOT_TOKEN     = _get("DISCORD_BOT_TOKEN", "")
    COMMAND_PREFIX        = _get("COMMAND_PREFIX", "$")
    LOG_LEVEL             = _get("LOG_LEVEL", "INFO")
    OWNER_USER_ID         = _get("OWNER_USER_ID", 0, int)
    DEFAULT_EMBED_COLOR   = int(str(_get("DEFAULT_EMBED_COLOR", "0x3498db")), 16)
    MAX_MESSAGE_LENGTH    = _get("MAX_MESSAGE_LENGTH", 2000, int)
    LOG_FILE              = _get("LOG_FILE", "bot.log")

    # ===== Provider / Models =====
    PROVIDER              = _get("PROVIDER", "groq")
    GROQ_API_KEY          = _get("GROQ_API_KEY", "")
    GROQ_MODEL_FAST       = _get("GROQ_MODEL_FAST", "llama-3.1-8b-instant")
    GROQ_MODEL_SMART      = _get("GROQ_MODEL_SMART", "llama-3.1-70b-versatile")
    AI_MODE_DEFAULT       = _get("AI_MODE_DEFAULT", "smart")  # 'fast' or 'smart'

    # ===== Server Invites =====
    SERVER_INVITE_URL     = _get("SERVER_INVITE_URL", "")
    ENABLE_INVITES        = _get("ENABLE_INVITES", True, bool)

    # ===== Meme Feed (optional) =====
    ENABLE_MEME_FEED      = _get("ENABLE_MEME_FEED", False, bool)
    MEME_CHANNEL_ID       = _get("MEME_CHANNEL_ID", 0, int)
    MEME_INTERVAL_MIN     = _get("MEME_INTERVAL_MIN", 120, int)

    # ===== Disaster tools (optional) =====
    ENABLE_DISASTER_TOOLS = _get("ENABLE_DISASTER_TOOLS", False, bool)

    # ===== VoidPulse defaults =====
    VOID_COOLDOWN_HOURS   = _get("VOID_COOLDOWN_HOURS", 36, int)
    VOID_JITTER_MIN       = _get("VOID_JITTER_MIN", 45, int)
    VOID_WINDOW_MIN       = _get("VOID_WINDOW_MIN", 120, int)
    VOID_MAX_MSGS         = _get("VOID_MAX_MSGS", 6, int)

    # Helper to require a critical env
    @staticmethod
    def require(name: str, value):
        if not value:
            raise RuntimeError(f"Missing required env var: {name}")
        return value


# Export a convenient instance if any module wants it
cfg = Config()

# ---- Backwards compatibility alias ----
# Older modules import `BotConfig`; keep that working.
BotConfig = Config