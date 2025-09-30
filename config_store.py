# config_store.py
import json, os, threading
from typing import Any, Dict
from config import STATE_FILE, DATA_DIR

_lock = threading.Lock()
_state: Dict[str, Any] = {
    "global": {"lockdown": False},
    "guilds": {}  # guild_id -> { "brand": "...", "channels": {"welcome": id, "memes": id, "void": id, "open_chat": id}, "debate": {"terms_on": True, "coach_on": True}}
}

def _ensure_loaded():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(STATE_FILE):
        _save()
    else:
        _load()

def _load():
    global _state
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            _state = json.load(f)
    except Exception:
        _state = {"global": {"lockdown": False}, "guilds": {}}

def _save():
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_state, f, indent=2, sort_keys=True)
    os.replace(tmp, STATE_FILE)

def is_locked() -> bool:
    _ensure_loaded()
    with _lock:
        return bool(_state["global"].get("lockdown", False))

def set_locked(v: bool):
    _ensure_loaded()
    with _lock:
        _state["global"]["lockdown"] = bool(v)
        _save()

def gobj(guild_id: int) -> Dict[str, Any]:
    _ensure_loaded()
    with _lock:
        g = _state["guilds"].setdefault(str(guild_id), {})
        g.setdefault("brand", None)
        g.setdefault("channels", {})
        g.setdefault("debate", {"terms_on": True, "coach_on": True})
        return g

def set_guild_setting(guild_id: int, key: str, value: Any):
    _ensure_loaded()
    with _lock:
        g = gobj(guild_id)
        g[key] = value
        _save()

def get_guild_setting(guild_id: int, key: str, default=None):
    _ensure_loaded()
    with _lock:
        return gobj(guild_id).get(key, default)

def set_channel(guild_id: int, kind: str, channel_id: int):
    _ensure_loaded()
    with _lock:
        g = gobj(guild_id)
        g["channels"][kind] = int(channel_id)
        _save()

def get_channel(guild_id: int, kind: str, default=None):
    _ensure_loaded()
    with _lock:
        return gobj(guild_id)["channels"].get(kind, default)

def set_debate_flag(guild_id: int, flag: str, val: bool):
    _ensure_loaded()
    with _lock:
        g = gobj(guild_id)
        g["debate"][flag] = bool(val)
        _save()

def get_debate(guild_id: int) -> Dict[str, Any]:
    _ensure_loaded()
    with _lock:
        return dict(gobj(guild_id)["debate"])