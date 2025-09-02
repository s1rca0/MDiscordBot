# config_store.py
"""
Zero-dependency, volume-free config overlay.

- Reads from env for anything that already exists.
- Lets cogs write ephemeral overrides in-memory (Hobby plan safe).
- `setup_cog.py` calls store.set(...), store.get(...), store.all()
- `BotConfig.reload_overrides(store.all())` will use these until restart.
"""

from __future__ import annotations
import os
from typing import Any, Dict


class _MemoryStore:
    def __init__(self) -> None:
        # In-memory only (lost on restart – perfect for Railway Hobby)
        self._overrides: Dict[str, str] = {}

    # Read: in-memory overrides win, else fall back to env, else default
    def get(self, key: str, default: Any = None) -> Any:
        if key in self._overrides:
            return self._overrides[key]
        val = os.getenv(key)
        return val if val is not None else default

    # Write: store as string (since envs are strings)
    def set(self, key: str, value: Any) -> None:
        self._overrides[key] = "" if value is None else str(value)

    # Bulk view of overrides (used by BotConfig.reload_overrides)
    def all(self) -> Dict[str, str]:
        return dict(self._overrides)

    # Helpful utility if you ever want to clear in-memory values
    def clear(self) -> None:
        self._overrides.clear()


# This is what cogs import: `from config_store import store`
store = _MemoryStore()