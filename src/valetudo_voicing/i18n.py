"""Lightweight bilingual EN/FR internationalization helper."""

import os

_UI_LANG: str | None = None


def detect_system_lang() -> str:
    """Detect 'fr' or 'en' from environment variables (defaults to 'en')."""
    env_override = os.environ.get("VALETUDO_VOICING_UI_LANG", "").strip().lower()
    if env_override.startswith("fr"):
        return "fr"
    if env_override.startswith("en"):
        return "en"

    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var, "").strip().lower()
        if val.startswith("fr"):
            return "fr"
        if val and val != "c" and val != "posix":
            return "en"
    return "en"


def get_ui_lang() -> str:
    """Return the active UI language ('fr' or 'en')."""
    global _UI_LANG
    if _UI_LANG is None:
        _UI_LANG = detect_system_lang()
    return _UI_LANG


def set_ui_lang(lang: str) -> str:
    """Set the active UI language ('fr' or 'en')."""
    global _UI_LANG
    norm = lang.strip().lower()
    _UI_LANG = "fr" if norm.startswith("fr") else "en"
    return _UI_LANG


def tr(fr: str, en: str) -> str:
    """Return `fr` when UI language is French, otherwise `en`."""
    return fr if get_ui_lang() == "fr" else en
