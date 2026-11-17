"""TTS backend registry."""

from .base import TTSBackend
from .xtts import XTTSBackend
from .chatterbox import ChatterboxBackend


def get_backend(name: str = "xtts") -> TTSBackend:
    """Instantiate a TTS backend by name ('xtts' or 'chatterbox')."""
    normalized = name.strip().lower()
    if normalized == "xtts":
        return XTTSBackend()
    if normalized == "chatterbox":
        return ChatterboxBackend()
    raise ValueError(f"Unknown TTS backend '{name}'. Available: xtts, chatterbox")


__all__ = ["TTSBackend", "XTTSBackend", "ChatterboxBackend", "get_backend"]
