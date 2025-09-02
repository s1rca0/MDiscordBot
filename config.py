# config.py
from __future__ import annotations
import os
from dataclasses import dataclass, field

def _b(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}

def _i(name: str, default: int = 0) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default

def _s(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()

@dataclass
class BotConfig:
    """
    Stateless config for Railway Hobby (no filesystem/volumes).
    All values come from env; everything else is optional with safe defaults.
    """

    # ---- Discord core
    BOT_TOKEN: str = _s("DISCORD_BOT_TOKEN")     # primary token (env name kept)
    COMMAND_PREFIX: str = _s("COMMAND_PREFIX", "$")
    OWNER_USER_ID: int = _i("OWNER_USER_ID", 0)

    # Logging: empty LOG_FILE => stdout only (best for Railway)
    LOG_LEVEL: str = _s("LOG_LEVEL", "INFO")
    LOG_FILE: str = _s("LOG_FILE", "")          # keep empty to avoid file writes
    DEBUG_MODE: bool = _b("DEBUG_MODE", False)

    # ---- AI / provider
    PROVIDER: str = _s("PROVIDER", "groq")
    GROQ_API_KEY: str = _s("GROQ_API_KEY")
    GROQ_MODEL_FAST: str = _s("GROQ_MODEL_FAST", "llama-3.1-8b-instant")
    GROQ_MODEL_SMART: str = _s("GROQ_MODEL_SMART", "llama-3.1-70b-versatile")
    AI_MODE_DEFAULT: str = _s("AI_MODE_DEFAULT", "smart")
    AI_TEMPERATURE: float = float(_s("AI_TEMPERATURE", "0.7"))
    AI_MAX_NEW_TOKENS: int = _i("AI_MAX_NEW_TOKENS", 512)

    # ---- Invites (safe defaults so cogs never crash)
    ALLOW_INVITES: bool = _b("ENABLE_INVITES", True)
    SERVER_INVITE_URL: str = _s("SERVER_INVITE_URL")  # can be empty; cogs handle it

    # ---- Meme feed (disabled by default; stateless)
    MEMES_ENABLED: bool = _b("ENABLE_MEME_FEED", False)
    MEME_CHANNEL_ID: int = _i("MEME_CHANNEL_ID", 0)   # our canonical name
    MEME_INTERVAL_MIN: int = _i("MEME_INTERVAL_MIN", 120)

    # ---- Moderation (optional)
    MAX_MENTIONS: int = _i("MAX_MENTIONS", 3)

    # ---- Disaster tools (disabled by default)
    DISASTER_TOOLS_ENABLED: bool = _b("ENABLE_DISASTER_TOOLS", False)

    # ---- Tickets / Support (optional; 0 means “not set”)
    TICKET_HOME_CHANNEL_ID: int = _i("TICKET_HOME_CHANNEL_ID", 0)
    SUPPORT_CHANNEL_ID: int = _i("SUPPORT_CHANNEL_ID", 0)
    TICKET_STAFF_ROLES: list[int] = field(default_factory=list)  # e.g. [123, 456]

    # ---- YouTube announcements (optional)
    YT_ANNOUNCE_CHANNEL_ID: int = _i("YT_ANNOUNCE_CHANNEL_ID", 0)

    # ---- Message length safety
    MAX_MESSAGE_LENGTH: int = _i("MAX_MESSAGE_LENGTH", 1800)

    # ---------- Helpers ----------
    def validate_core(self) -> None:
        """
        Soft validation—only logs warnings.
        Never touches disk; never raises on optional features.
        """
        missing = []
        if not self.BOT_TOKEN:
            missing.append("DISCORD_BOT_TOKEN")
        if self.PROVIDER == "groq" and not self.GROQ_API_KEY:
            missing.append("GROQ_API_KEY")

        if missing:
            print(f"[WARN] Missing env vars: {', '.join(missing)}")

        # Friendly heads-up for optional IDs
        if self.MEMES_ENABLED and not self.MEME_CHANNEL_ID:
            print("[WARN] MEMES_ENABLED is true but MEME_CHANNEL_ID is not set.")
        if self.YT_ANNOUNCE_CHANNEL_ID == 0:
            print("[INFO] YT_ANNOUNCE_CHANNEL_ID not set (YT announcements disabled).")

    # Back-compat with older code that called validate_config()
    def validate_config(self) -> None:
        self.validate_core()

    # ---------- Back-compat attribute aliases ----------
    # Some cogs still look for these exact names; expose read-only aliases.
    @property
    def DISCORD_BOT_TOKEN(self) -> str:  # old name used by some modules
        return self.BOT_TOKEN

    @property
    def MEMES_CHANNEL_ID(self) -> int:   # old pluralized name some cogs expect
        return self.MEME_CHANNEL_ID

# module-level instance used everywhere
cfg = BotConfig()