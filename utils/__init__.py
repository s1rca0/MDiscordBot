"""
utils package: shared helpers
"""

# ---- Safe env readers to prevent crashes on missing/invalid values ----
import os

def env_int(name: str, default: int = 0) -> int:
    """Read an integer env var safely. Empty/invalid -> default.
    Example: CHANNEL_ID = env_int("CHANNEL_ID", 0)
    """
    val = os.getenv(name, "")
    try:
        return int(val) if str(val).strip() != "" else default
    except (TypeError, ValueError):
        return default

def env_bool(name: str, default: bool = False) -> bool:
    """Read a boolean env var safely. Accepts 1/true/yes/y/on (case-insensitive).
    Empty -> default.
    """
    val = os.getenv(name, "")
    if val is None or str(val).strip() == "":
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "y", "on")
