# config.py
import os


def _as_bool(v, default=False):
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")

def _as_int(v, default=0):
    try:
        return int(str(v).strip())
    except Exception:
        return default

def _as_float(v, default=0.0):
    try:
        return float(str(v).strip())
    except Exception:
        return default

def _as_int_list(v):
    if not v:
        return []
    out = []
    for p in str(v).split(","):
        p = p.strip()
        if p.isdigit():
            out.append(int(p))
    return out


class BotConfig:
    """
    Centralized, environment-backed config with safe defaults.
    Expose attributes used across cogs so we avoid AttributeError at load time.
    """

    def __init__(self):
        # --- Core / AI provider ---
        self.BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
        self.COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")

        self.PROVIDER = os.getenv("PROVIDER", "groq").lower()  # 'groq' | 'hf' | 'openai'
        self.GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        self.HF_MODEL = os.getenv("HF_MODEL", "gpt2")
        self.OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        self.AI_MAX_NEW_TOKENS = _as_int(os.getenv("AI_MAX_NEW_TOKENS"), 256)
        self.AI_TEMPERATURE = _as_float(os.getenv("AI_TEMPERATURE"), 0.7)

        # System / persona prompts
        self.SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "").strip()
        self.PUBLIC_PERSONA_PROMPT = os.getenv("PUBLIC_PERSONA_PROMPT", "").strip()
        self.BACKSTAGE_PERSONA_PROMPT = os.getenv("BACKSTAGE_PERSONA_PROMPT", "").strip()
        self.MORPHEUS_STYLE_HINT = os.getenv("MORPHEUS_STYLE_HINT", "").strip()

        # Greeter
        self.GREETER_DM_PROMPT = os.getenv("GREETER_DM_PROMPT", "").strip()
        self.GREETER_PUBLIC_PROMPT = os.getenv("GREETER_PUBLIC_PROMPT", "").strip()

        # --- Owner / roles / channels (common) ---
        self.OWNER_USER_ID = _as_int(os.getenv("OWNER_USER_ID"), 0)
        self.TRUST_ROLE_IDS = _as_int_list(os.getenv("TRUST_ROLE_IDS", ""))   # fast-track / trusted users

        self.YT_VERIFIED_ROLE_ID = _as_int(os.getenv("YT_VERIFIED_ROLE_ID"), 0)
        self.MEMBER_ROLE_ID = _as_int(os.getenv("MEMBER_ROLE_ID"), 0)         # your “Members / The Construct” role
        self.WELCOME_CHANNEL_ID = _as_int(os.getenv("WELCOME_CHANNEL_ID"), 0)
        self.MODLOG_CHANNEL_ID = _as_int(os.getenv("MODLOG_CHANNEL_ID"), 0)

        # --- Mission / memory bridge ---
        self.MISSION_AUTO_EXPORT_ENABLED = _as_bool(os.getenv("MISSION_AUTO_EXPORT_ENABLED"), False)
        self.MISSION_EXPORT_INTERVAL_MIN = _as_int(os.getenv("MISSION_EXPORT_INTERVAL_MIN"), 60)
        self.MISSION_EXPORT_PATH = os.getenv("MISSION_EXPORT_PATH", "data/mission_memory.json")
        self.MEMORY_BRIDGE_PATH = os.getenv("MEMORY_BRIDGE_PATH", "data/mission_memory.json")

        # --- Tickets (if used by tickets_cog) ---
        self.TICKET_HOME_CHANNEL_ID = _as_int(os.getenv("TICKET_HOME_CHANNEL_ID"), 0)
        self.TICKET_STAFF_ROLES = _as_int_list(os.getenv("TICKET_STAFF_ROLES", ""))

        # --- Moderation (used by moderation_cog) ---
        self.MAX_MENTIONS = _as_int(os.getenv("MAX_MENTIONS"), 8)
        self.SPAM_WINDOW_SECS = _as_int(os.getenv("SPAM_WINDOW_SECS"), 12)
        self.ALLOW_INVITES = _as_bool(os.getenv("ALLOW_INVITES"), False)

        # --- Presence (presence_cog) ---
        self.PRESENCE_INTERVAL_SEC = _as_int(os.getenv("PRESENCE_INTERVAL_SEC"), 300)
        self.PRESENCE_MAINFRAME = os.getenv("PRESENCE_MAINFRAME", "Standing by in MAINFRAME").strip()
        self.PRESENCE_CONSTRUCT = os.getenv("PRESENCE_CONSTRUCT", "Guiding in The Construct").strip()
        self.PRESENCE_HAVN = os.getenv("PRESENCE_HAVN", "Keeping watch in HAVN").strip()

        # --- Void pulse (void_pulse_cog) ---
        self.VOID_CHANNEL_ID = _as_int(os.getenv("VOID_CHANNEL_ID"), 0)
        self.VOID_BROADCAST_HOURS = _as_int(os.getenv("VOID_BROADCAST_HOURS"), 72)

        # --- YouTube (youtube & yt_announcer) ---
        self.YT_CHANNEL_ID = os.getenv("YT_CHANNEL_ID", "").strip()
        self.YT_ANNOUNCE_CHANNEL_ID = _as_int(os.getenv("YT_ANNOUNCE_CHANNEL_ID"), 0)
        self.YT_POLL_MIN = _as_int(os.getenv("YT_POLL_MIN"), 10)

    # light sanity checks
    def validate_config(self):
        if not self.BOT_TOKEN:
            raise ValueError("Missing DISCORD_BOT_TOKEN")

        # provider is flexible; we just log if unknown elsewhere
        return True