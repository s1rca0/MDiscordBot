"""
Bot Configuration
Configuration settings and environment variable management.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file (local dev)
load_dotenv()

def _as_bool(val: str, default: bool = False) -> bool:
    if val is None:
        return default
    return str(val).strip().lower() in {"1", "true", "yes", "y", "on"}

def _as_int(val: str, default: int) -> int:
    try:
        return int(str(val).strip(), 0)  # supports decimal or 0x... hex
    except Exception:
        return default

def _csv_set(val: str) -> set[str]:
    if not val:
        return set()
    return {item.strip() for item in val.split(",") if item.strip()}

class BotConfig:
    """Bot configuration class."""

    def __init__(self):
        # -------- Required --------
        self.BOT_TOKEN: str = os.getenv("DISCORD_BOT_TOKEN", "")

        # -------- Core bot settings --------
        self.COMMAND_PREFIX: str = os.getenv("COMMAND_PREFIX", "!")
        self.DEBUG_MODE: bool = _as_bool(os.getenv("DEBUG_MODE", "false"))
        self.MAX_MESSAGE_LENGTH: int = _as_int(os.getenv("MAX_MESSAGE_LENGTH", "2000"), 2000)
        self.DEFAULT_EMBED_COLOR: int = _as_int(
            os.getenv("DEFAULT_EMBED_COLOR", "0x3498db"), 0x3498DB
        )

        # -------- Logging --------
        self.LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
        self.LOG_FILE: str = os.getenv("LOG_FILE", "bot.log")

        # -------- AI Provider Switch --------
        # "hf" (Hugging Face) for development; "openai" when you upgrade.
        self.PROVIDER: str = os.getenv("PROVIDER", "hf").strip().lower()

        # -------- Hugging Face (dev) --------
        # Example model: mistralai/Mistral-7B-Instruct-v0.3
        self.HF_MODEL: str = os.getenv("HF_MODEL", "mistralai/Mistral-7B-Instruct-v0.3")
        self.HF_API_TOKEN: str = os.getenv("HF_API_TOKEN", "")  # hf_... (optional but recommended)

        # -------- OpenAI (upgrade path) --------
        self.OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")  # sk-...

        # -------- AI Behavior --------
        # Global system prompt for your assistant
        self.SYSTEM_PROMPT: str = os.getenv(
            "SYSTEM_PROMPT",
            "You are a friendly, concise Discord assistant. Be helpful, follow server rules, and keep replies under 8 lines.",
        )
        # Generation knobs
        self.AI_MAX_NEW_TOKENS: int = _as_int(os.getenv("AI_MAX_NEW_TOKENS", "256"), 256)
        self.AI_TEMPERATURE: float = float(os.getenv("AI_TEMPERATURE", "0.7"))

        # -------- Triggers & UX --------
        # Channels where the bot will reply without being @mentioned (comma-separated IDs)
        self.AI_CHAT_CHANNEL_IDS: set[str] = _csv_set(os.getenv("AI_CHAT_CHANNEL_IDS", ""))

        # Greet new members in DMs (falls back to system channel if DMs blocked)
        self.GREETING_DMS: bool = _as_bool(os.getenv("GREETING_DMS", "true"))

        # Safety: basic keyword filter enable (you can implement later)
        self.ENABLE_KEYWORD_FILTER: bool = _as_bool(os.getenv("ENABLE_KEYWORD_FILTER", "false"))

    # ---------------- Validation ----------------
    def validate_config(self) -> bool:
        """Validate configuration settings."""
        if not self.BOT_TOKEN:
            raise ValueError(
                "DISCORD_BOT_TOKEN environment variable is required. "
                "Please set it in your environment or .env file."
            )

        # Discord tokens are variable length; avoid over-strict checks that reject valid tokens.
        if len(self.COMMAND_PREFIX) == 0:
            raise ValueError("Command prefix cannot be empty")

        if self.PROVIDER not in {"hf", "openai"}:
            raise ValueError("PROVIDER must be 'hf' or 'openai'")

        if self.PROVIDER == "hf":
            if not self.HF_MODEL:
                raise ValueError("HF_MODEL is required when PROVIDER=hf")
            # HF_API_TOKEN is optional for public endpoints but recommended.
        else:  # openai
            if not self.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY is required when PROVIDER=openai")

        # Discord hard limit is 2000 chars; keep ours at or below to avoid errors.
        if self.MAX_MESSAGE_LENGTH > 2000:
            raise ValueError("MAX_MESSAGE_LENGTH cannot exceed 2000")

        return True