# config.py
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional, Tuple

# -------- utilities ---------------------------------------------------------

def _get(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    if v is None or str(v).strip() == "":
        return default
    return str(v).strip()

def _get_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    v = v.strip().lower()
    return v in ("1", "true", "yes", "y", "on")

def _get_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    try:
        return int(v)
    except ValueError:
        return default

def _parse_color(s: Optional[str], default_hex: str = "#2b2d31") -> int:
    """
    Accepts '#RRGGBB' or '0xRRGGBB' or decimal string; returns int.
    """
    if not s:
        s = default_hex
    s = s.strip().lower()
    try:
        if s.startswith("#"):
            return int(s[1:], 16)
        if s.startswith("0x"):
            return int(s, 16)
        return int(s)
    except Exception:
        return int(default_hex.replace("#", ""), 16)

# -------- config dataclass --------------------------------------------------

@dataclass
class BotConfig:
    # Core
    DISCORD_BOT_TOKEN: str = _get("DISCORD_BOT_TOKEN", "")
    COMMAND_PREFIX: str = _get("COMMAND_PREFIX", "$")
    DEBUG_MODE: bool = _get_bool("DEBUG_MODE", False)
    DEFAULT_EMBED_COLOR: int = _parse_color(_get("DEFAULT_EMBED_COLOR", "#2b2d31"))

    # Ownership / logging
    OWNER_USER_ID: str = _get("OWNER_USER_ID", "")
    LOG_FILE: str = _get("LOG_FILE", "bot.log")
    LOG_LEVEL: str = _get("LOG_LEVEL", "INFO")
    MAX_MESSAGE_LENGTH: int = _get_int("MAX_MESSAGE_LENGTH", 1800)

    # Provider + models
    PROVIDER: str = _get("PROVIDER", "groq").lower()
    GROQ_API_KEY: str = _get("GROQ_API_KEY", "")
    GROQ_MODEL_FAST: str = _get("GROQ_MODEL_FAST", "llama-3.1-8b-instant")
    GROQ_MODEL_SMART: str = _get("GROQ_MODEL_SMART", "llama-3.1-70b-versatile")
    GROQ_MODEL: str = _get("GROQ_MODEL", "")  # optional legacy single-name
    OPENAI_API_KEY: str = _get("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = _get("OPENAI_MODEL", "gpt-4o-mini")
    HF_MODEL: str = _get("HF_MODEL", "")
    HF_API_KEY: str = _get("HF_API_KEY", "")
    HF_API_URL: str = _get("HF_API_URL", "")

    # AI behavior
    AI_MODE_DEFAULT: str = _get("AI_MODE_DEFAULT", "smart")
    AI_TEMPERATURE: float = float(_get("AI_TEMPERATURE", "0.6"))
    AI_MAX_NEW_TOKENS: int = _get_int("AI_MAX_NEW_TOKENS", 512)

    # Invitations / onboarding
    SERVER_INVITE_URL: str = _get("SERVER_INVITE_URL", "")

    # Optional channels (safe if unset)
    WELCOME_CHANNEL_ID: Optional[int] = (
        int(_get("WELCOME_CHANNEL_ID", "0")) or None
    )
    YT_ANNOUNCE_CHANNEL_ID: Optional[int] = (
        int(_get("YT_ANNOUNCE_CHANNEL_ID", "0")) or None
    )

    # Feature flags
    ENABLE_INVITES: bool = _get_bool("ENABLE_INVITES", True)
    ENABLE_MEME_FEED: bool = _get_bool("ENABLE_MEME_FEED", False)
    ENABLE_DISASTER_TOOLS: bool = _get_bool("ENABLE_DISASTER_TOOLS", False)

    # Meme feed config
    MEME_CHANNEL_ID: Optional[int] = (
        int(_get("MEME_CHANNEL_ID", "0")) or None
    )
    MEME_INTERVAL_MIN: int = _get_int("MEME_INTERVAL_MIN", 120)

    # VoidPulse defaults
    VOID_COOLDOWN_HOURS: int = _get_int("VOID_COOLDOWN_HOURS", 36)
    VOID_JITTER_MIN: int = _get_int("VOID_JITTER_MIN", 45)
    VOID_WINDOW_MIN: int = _get_int("VOID_WINDOW_MIN", 120)
    VOID_MAX_MSGS_IN_WINDOW: int = _get_int("VOID_MAX_MSGS_IN_WINDOW", 6)
    VOID_QUIET_THRESHOLD_MIN: int = _get_int("VOID_QUIET_THRESHOLD_MIN", 180)

    # Support / ticketing (all optional; cogs should check for None)
    SUPPORT_ENABLED: bool = _get_bool("SUPPORT_ENABLED", False)
    SUPPORT_RETENTION_DAYS: int = _get_int("SUPPORT_RETENTION_DAYS", 30)
    SUPPORT_ROLE_ID: Optional[int] = int(_get("SUPPORT_ROLE_ID", "0")) or None
    SUPPORT_CHANNEL_ID: Optional[int] = int(_get("SUPPORT_CHANNEL_ID", "0")) or None
    SUPPORT_ALERT_CHANNEL_ID: Optional[int] = int(_get("SUPPORT_ALERT_CHANNEL_ID", "0")) or None
    SUPPORT_NOTIFY_ROLE_ID: Optional[int] = int(_get("SUPPORT_NOTIFY_ROLE_ID", "0")) or None
    SUPPORT_INTEREST_EMOJI: str = _get("SUPPORT_INTEREST_EMOJI", "🛠️")

    # Presence / status (optional)
    STATUS_ROTATE_ENABLED: bool = _get_bool("STATUS_ROTATE_ENABLED", True)
    STATUS_ROTATE_MIN: int = _get_int("STATUS_ROTATE_MIN", 15)

    # ---------------- back-compat shims ----------------

    @property
    def BOT_TOKEN(self) -> str:
        """
        Back-compat: older code read cfg.BOT_TOKEN. Map to DISCORD_BOT_TOKEN.
        """
        return self.DISCORD_BOT_TOKEN

    @property
    def YT_ANNOUNCE_CHANNEL(self) -> Optional[int]:
        """
        Back-compat accessor some older cogs might call.
        """
        return self.YT_ANNOUNCE_CHANNEL_ID

    # ---------------- convenience helpers ----------------

    def invite_tuple(self) -> Tuple[bool, str]:
        """
        Returns (ok, message_or_url) for displaying / using the invite.
        """
        url = (self.SERVER_INVITE_URL or "").strip()
        if not url.lower().startswith("https://discord.gg/"):
            return False, "SERVER_INVITE_URL is missing or not a discord.gg link."
        return True, url

    # ---------------- validation ----------------

    def validate_core(self) -> None:
        """
        Minimal required checks to boot the bot.
        """
        # Token
        if not (self.DISCORD_BOT_TOKEN or "").strip():
            raise RuntimeError("DISCORD_BOT_TOKEN is not set.")

        # Provider/model sanity
        prov = (self.PROVIDER or "").lower()
        if prov not in ("groq", "openai", "hf"):
            raise RuntimeError("PROVIDER must be one of: groq, openai, hf")

        if prov == "groq":
            if not (self.GROQ_API_KEY or "").strip():
                raise RuntimeError("GROQ_API_KEY is not set.")
            # At least one model must resolve
            if not (self.GROQ_MODEL_FAST or self.GROQ_MODEL_SMART or self.GROQ_MODEL):
                raise RuntimeError("Set GROQ_MODEL_FAST or GROQ_MODEL_SMART (or GROQ_MODEL).")

        if prov == "openai":
            if not (self.OPENAI_API_KEY or "").strip():
                raise RuntimeError("OPENAI_API_KEY is not set.")

        if prov == "hf":
            # user can wire their own HF endpoint; we require both URL and KEY
            if not (self.HF_API_URL and self.HF_API_KEY):
                raise RuntimeError("HF_API_URL and HF_API_KEY must be set for provider=hf.")

    # Back-compat alias so older code (bot.py) continues to call this name.
    def validate_config(self) -> None:
        return self.validate_core()