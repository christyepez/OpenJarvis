"""Speech subsystem — speech-to-text and text-to-speech backends."""

from __future__ import annotations

import importlib

_BUILTINS_LOADED = False


def load_builtin_backends() -> None:
    """Register optional speech backends only when speech is actually used."""
    global _BUILTINS_LOADED
    if _BUILTINS_LOADED:
        return

    for module_name in (
        "faster_whisper",
        "openai_whisper",
        "deepgram",
        "windows_tts",
        "cartesia_tts",
        "kokoro_tts",
        "openai_tts",
    ):
        try:
            importlib.import_module(f".{module_name}", __name__)
        except ImportError:
            pass

    _BUILTINS_LOADED = True
