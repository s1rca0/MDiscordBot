# utils/guards.py
from functools import wraps
from typing import Callable, Any

def require_unlocked():
    """Decorator: block a command while global lockdown latch is set."""
    def deco(func: Callable[..., Any]):
        @wraps(func)
        async def wrapped(*args, **kwargs):
            interaction = kwargs.get("interaction") or (len(args) > 1 and args[1])
            try:
                from cogs.owner_mvp import is_locked  # lazy import avoids cycles
                if is_locked():
                    try:
                        await interaction.response.send_message(
                            "🔒 Morpheus is in **global lockdown** right now.",
                            ephemeral=True,
                        )
                    except Exception:
                        pass
                    return
            except Exception:
                pass
            return await func(*args, **kwargs)
        return wrapped
    return deco