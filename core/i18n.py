"""Internationalization — simple YAML-based translation with t() helper."""
import os
from datetime import datetime, date
from functools import lru_cache
import yaml
import streamlit as st

SUPPORTED_LANGUAGES = {"de": "Deutsch", "en": "English"}
DEFAULT_LANGUAGE = "de"


@lru_cache(maxsize=2)
def _load(lang: str) -> dict:
    path = os.path.join(os.path.dirname(__file__), "..", "translations", f"{lang}.yaml")
    with open(os.path.normpath(path), encoding="utf-8") as f:
        return yaml.safe_load(f)


def _get(d: dict, keys: list) -> str:
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return ".".join(keys)  # fallback: return key path
        d = d[k]
    return str(d)


def t(key: str) -> str:
    """Translate key (dot-notation) using current session language."""
    lang = st.session_state.get("lang", DEFAULT_LANGUAGE)
    translations = _load(lang)
    return _get(translations, key.split("."))


def set_language(lang: str) -> None:
    """Set the active language in session state."""
    st.session_state["lang"] = lang


def current_language() -> str:
    """Return the currently active language code."""
    return st.session_state.get("lang", DEFAULT_LANGUAGE)


_DATE_FORMATS = {
    "de": "%d.%m.%Y",
    "en": "%Y-%m-%d",
}
_DATETIME_FORMATS = {
    "de": "%d.%m.%Y %H:%M",
    "en": "%Y-%m-%d %H:%M",
}


def fmt_date(d) -> str:
    """Format a date or datetime using the current locale."""
    lang = current_language()
    fmt = _DATE_FORMATS.get(lang, _DATE_FORMATS["de"])
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return d.strftime(fmt)


def fmt_dt(dt) -> str:
    """Format a datetime using the current locale (date + time)."""
    lang = current_language()
    fmt = _DATETIME_FORMATS.get(lang, _DATETIME_FORMATS["de"])
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    return dt.strftime(fmt)
