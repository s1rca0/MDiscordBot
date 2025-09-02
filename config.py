import os

class Config:
    # Discord Core
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "$")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0"))

    # AI Provider / Models
    PROVIDER = os.getenv("PROVIDER", "groq")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_MODEL_FAST = os.getenv("GROQ_MODEL_FAST", "llama-3.1-8b-instant")
    GROQ_MODEL_SMART = os.getenv("GROQ_MODEL_SMART", "llama-3.1-70b-versatile")
    AI_MODE_DEFAULT = os.getenv("AI_MODE_DEFAULT", "smart")

    # Server Invite
    SERVER_INVITE_URL = os.getenv("SERVER_INVITE_URL")

    # Feature Flags
    ENABLE_INVITES = os.getenv("ENABLE_INVITES", "true").lower() == "true"
    ENABLE_MEME_FEED = os.getenv("ENABLE_MEME_FEED", "false").lower() == "true"
    ENABLE_DISASTER_TOOLS = os.getenv("ENABLE_DISASTER_TOOLS", "false").lower() == "true"

    # Meme Feed
    MEME_CHANNEL_ID = int(os.getenv("MEME_CHANNEL_ID", "0"))
    MEME_INTERVAL_MIN = int(os.getenv("MEME_INTERVAL_MIN", "120"))

    # VoidPulse Defaults
    VOID_COOLDOWN_HOURS = int(os.getenv("VOID_COOLDOWN_HOURS", "36"))
    VOID_JITTER_MIN = int(os.getenv("VOID_JITTER_MIN", "45"))
    VOID_QUIET_MIN = int(os.getenv("VOID_QUIET_MIN", "180"))
    VOID_WINDOW_MIN = int(os.getenv("VOID_WINDOW_MIN", "120"))
    VOID_MAX_MSGS = int(os.getenv("VOID_MAX_MSGS", "6"))
    VOID_CHANNEL_ID = int(os.getenv("VOID_CHANNEL_ID", "0"))