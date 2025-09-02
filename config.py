# config.py
from __future__ import annotations
import os
from dataclasses import dataclass

# ---------------- helpers ----------------
def _b(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}

def _i(name: str, default: int = 0) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default

def _s(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()

# ---------------- config ----------------
@dataclass
class BotConfig:
    """
    Stateless config for M.O.R.P.H.E.U.S.
    Works with Railway Hobby (no volumes).
    All values are read from env vars with safe defaults.
    """

    # ---- Discord core
    BOT_TOKEN: str = _s("DISCORD_BOT_TOKEN")
    COMMAND_PREFIX: str = _s("COMMAND_PREFIX", "$")
    OWNER_USER_ID: int = _i("OWNER_USER_ID", 0)

    LOG_LEVEL: str = _s("LOG_LEVEL", "INFO")
    LOG_FILE: str = _s("LOG_FILE", "")  # keep empty for stdout only
    DEBUG_MODE: bool = _b("DEBUG_MODE", False)

    # ---- AI / provider
    PROVIDER: str = _s("PROVIDER", "groq")
    GROQ_API_KEY: str = _s("GROQ_API_KEY")
    GROQ_MODEL_FAST: str = _s("GROQ_MODEL_FAST", "llama-3.1-8b-instant")
    GROQ_MODEL_SMART: str = _s("GROQ_MODEL_SMART", "llama-3.1-70b-versatile")
    AI_MODE_DEFAULT: str = _s("AI_MODE_DEFAULT", "smart")
    AI_TEMPERATURE: float = float(_s("AI_TEMPERATURE", "0.7"))
    AI_MAX_NEW_TOKENS: int = _i("AI_MAX_NEW_TOKENS", 512)

    # ---- Invites
    ALLOW_INVITES: bool = _b("ALLOW_INVITES", True)
    SERVER_INVITE_URL: str = _s("SERVER_INVITE_URL")

    # ---- Meme feed
    MEMES_ENABLED: bool = _b("ENABLE_MEME_FEED", False)
    MEME_CHANNEL_ID: int = _i("MEME_CHANNEL_ID", 0)
    MEME_INTERVAL_MIN: int = _i("MEME_INTERVAL_MIN", 120)

    # ---- Disaster tools
    DISASTER_TOOLS_ENABLED: bool = _b("ENABLE_DISASTER_TOOLS", False)

    # ---- Tickets / Support
    TICKET_HOME_CHANNEL_ID: int = _i("TICKET_HOME_CHANNEL_ID", 0)
    SUPPORT_CHANNEL_ID: int = _i("SUPPORT_CHANNEL_ID", 0)

    # ---- YouTube
    YT_ANNOUNCE_CHANNEL_ID: int = _i("YT_ANNOUNCE_CHANNEL_ID", 0)

    # ---- Safety
    MAX_MESSAGE_LENGTH: int = _i("MAX_MESSAGE_LENGTH", 1800)

    # ---------- validation ----------
    def validate_core(self) -> None:
        missing = []
        if not self.BOT_TOKEN:
            missing.append("DISCORD_BOT_TOKEN")
        if self.PROVIDER == "groq" and not self.GROQ_API_KEY:
            missing.append("GROQ_API_KEY")
        if missing:
            print(f"[WARN] Missing env vars: {', '.join(missing)}")

        if self.MEMES_ENABLED and not self.MEME_CHANNEL_ID:
            print("[WARN] MEMES_ENABLED is true but MEME_CHANNEL_ID is not set.")
        if self.YT_ANNOUNCE_CHANNEL_ID == 0:
            print("[INFO] YT_ANNOUNCE_CHANNEL_ID not set (YT announcements disabled).")

    def validate_config(self) -> None:
        self.validate_core()

# global instance
cfg = BotConfig()