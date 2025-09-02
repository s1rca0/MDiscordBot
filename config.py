# config.py
from __future__ import annotations
import os
from dataclasses import dataclass

def _b(name: str, default: bool = False) -> bool:
    v = os.getenv(name, "")
    if v == "":
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}

def _i(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except Exception:
        return default

def _s(name: str, default: str = "") -> str:
    return (os.getenv(name, None) or default).strip()

@dataclass
class BotConfig:
    # -------- Discord Core --------
    DISCORD_BOT_TOKEN: str = _s("DISCORD_BOT_TOKEN")
    COMMAND_PREFIX: str = _s("COMMAND_PREFIX", "$")
    LOG_LEVEL: str = _s("LOG_LEVEL", "INFO")
    OWNER_USER_ID: str = _s("OWNER_USER_ID")

    # -------- AI Provider / Models --------
    PROVIDER: str = _s("PROVIDER", "groq").lower()
    # Groq
    GROQ_API_KEY: str = _s("GROQ_API_KEY")
    GROQ_MODEL_FAST: str = _s("GROQ_MODEL_FAST", "llama-3.1-8b-instant")
    GROQ_MODEL_SMART: str = _s("GROQ_MODEL_SMART", "llama-3.1-70b-versatile")
    # Optional legacy single-name
    GROQ_MODEL: str = _s("GROQ_MODEL")
    # OpenAI (optional)
    OPENAI_API_KEY: str = _s("OPENAI_API_KEY")
    OPENAI_MODEL: str = _s("OPENAI_MODEL", "gpt-4o-mini")
    # HuggingFace (optional)
    HF_MODEL: str = _s("HF_MODEL")
    HF_API_KEY: str = _s("HF_API_KEY")
    HF_API_URL: str = _s("HF_API_URL")

    # Generation controls
    AI_MODE_DEFAULT: str = _s("AI_MODE_DEFAULT", "smart").lower()  # fast | smart
    AI_TEMPERATURE: float = float(os.getenv("AI_TEMPERATURE", "0.7"))
    AI_MAX_NEW_TOKENS: int = _i("AI_MAX_NEW_TOKENS", 512)
    MAX_MESSAGE_LENGTH: int = _i("MAX_MESSAGE_LENGTH", 2000)

    # -------- Invites / Links --------
    SERVER_INVITE_URL: str = _s("SERVER_INVITE_URL")

    # -------- Feature Flags --------
    ENABLE_INVITES: bool = _b("ENABLE_INVITES", True)
    ENABLE_MEME_FEED: bool = _b("ENABLE_MEME_FEED", False)
    ENABLE_DISASTER_TOOLS: bool = _b("ENABLE_DISASTER_TOOLS", False)

    # Meme feed (optional)
    MEME_CHANNEL_ID: int = _i("MEME_CHANNEL_ID", 0)
    MEME_INTERVAL_MIN: int = _i("MEME_INTERVAL_MIN", 120)

    # VoidPulse defaults (quiet broadcaster)
    VOID_COOLDOWN_HOURS: int = _i("VOID_COOLDOWN_HOURS", 36)
    VOID_JITTER_MIN: int = _i("VOID_JITTER_MIN", 45)
    VOID_WINDOW_MIN: int = _i("VOID_WINDOW_MIN", 120)
    VOID_MAX_MSGS: int = _i("VOID_MAX_MSGS", 6)

    # -------- Validation & helpers --------
    def validate_config(self) -> list[str]:
        """
        Return a list of warnings/errors; do not raise to avoid boot loops.
        The bot will still start and log these.
        """
        issues: list[str] = []

        # Required for any run
        if not self.DISCORD_BOT_TOKEN:
            issues.append("DISCORD_BOT_TOKEN is not set.")

        # Provider-specific checks
        if self.PROVIDER == "groq":
            if not self.GROQ_API_KEY:
                issues.append("GROQ_API_KEY is not set (provider=groq).")
        elif self.PROVIDER == "openai":
            if not self.OPENAI_API_KEY:
                issues.append("OPENAI_API_KEY is not set (provider=openai).")
        elif self.PROVIDER == "hf":
            if not (self.HF_API_KEY and self.HF_API_URL and self.HF_MODEL):
                issues.append("HF_API_KEY/HF_API_URL/HF_MODEL must be set (provider=hf).")
        else:
            issues.append(f"Unknown PROVIDER='{self.PROVIDER}'. Use 'groq', 'openai', or 'hf'.")

        # Optional but recommended
        if not self.OWNER_USER_ID:
            issues.append("OWNER_USER_ID is not set (recommended for admin-only actions).")

        # Invite feature
        if self.ENABLE_INVITES and not self.SERVER_INVITE_URL:
            issues.append("ENABLE_INVITES is true but SERVER_INVITE_URL is empty.")

        # Meme feed config sanity
        if self.ENABLE_MEME_FEED:
            if self.MEME_CHANNEL_ID <= 0:
                issues.append("ENABLE_MEME_FEED is true but MEME_CHANNEL_ID is not set.")
            if self.MEME_INTERVAL_MIN < 10:
                issues.append("MEME_INTERVAL_MIN is very low (<10).")

        # VoidPulse bounds
        if self.VOID_MAX_MSGS < 1:
            issues.append("VOID_MAX_MSGS must be >= 1.")
        if self.VOID_WINDOW_MIN < 15:
            issues.append("VOID_WINDOW_MIN should be >= 15.")

        # Mode sanity
        if self.AI_MODE_DEFAULT not in {"fast", "smart"}:
            issues.append("AI_MODE_DEFAULT must be 'fast' or 'smart'.")

        return issues

# For backward compatibility with older imports:
Config = BotConfig  # so `from config import Config` still works