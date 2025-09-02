# config_store.py
from __future__ import annotations

import json
import os
from typing import Any, Dict

RUNTIME_CONFIG_PATH = os.getenv("RUNTIME_CONFIG_PATH", "data/runtime_config.json")


def _ensure_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)


def load_overrides() -> Dict[str, Any]:
    """Return saved overrides (empty dict if none)."""
    try:
        with open(RUNTIME_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def save_overrides(d: Dict[str, Any]) -> None:
    """Persist overrides to disk (best-effort)."""
    try:
        _ensure_dir(RUNTIME_CONFIG_PATH)
        with open(RUNTIME_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
    except Exception:
        # In production we keep this silent—runtime will still have in-memory values.
        pass


def set_override(key: str, value: Any) -> Dict[str, Any]:
    """Set one key and save; returns the latest dict."""
    d = load_overrides()
    d[key] = value
    save_overrides(d)
    return d