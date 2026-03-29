"""Internationalization — simple YAML-based translation with t() helper."""
import os
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
