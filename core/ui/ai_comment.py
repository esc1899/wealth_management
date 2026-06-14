"""On-demand AI commentary block (local Ollama) — shared across pages.

Replaces the former auto-on-view behaviour: the local model is only invoked when the
user clicks the button, so merely opening a page no longer spins up Ollama in the
background. The comment is cached in session_state per page; if the underlying result
changes, the cached comment is marked stale and can be regenerated.
"""

import hashlib
import logging

import streamlit as st

from core.i18n import t
from core.services.portfolio_comment_service import get_style_by_id

logger = logging.getLogger(__name__)


def render_ai_comment(
    *,
    state_key: str,
    ctx: str,
    style_id: str,
    comment_service,
    section_title: str,
    divider: bool = True,
) -> None:
    """Render a button-triggered local AI comment for the given context.

    state_key: session_state namespace, e.g. "_ps" → keys "_ps_comment"/"_ps_comment_hash".
    ctx: the text the comment is based on (analysis full text).
    style_id: comment style id from app_config ("comment_style").
    comment_service: PortfolioCommentService instance.
    section_title: already-translated subheader.
    """
    style = get_style_by_id(style_id)
    ctx_hash = hashlib.md5((ctx + style_id).encode()).hexdigest()
    comment_key = f"{state_key}_comment"
    hash_key = f"{state_key}_comment_hash"

    if divider:
        st.divider()
    st.subheader(section_title)

    cached = st.session_state.get(comment_key)
    stale = bool(cached) and st.session_state.get(hash_key) != ctx_hash
    label = t("ai_comment.regenerate") if cached else f"{style['emoji']} {t('ai_comment.generate')}"

    if st.button(label, key=f"{state_key}_comment_btn"):
        with st.spinner(f"{style['emoji']} {t('ai_comment.spinner')}"):
            try:
                st.session_state[comment_key] = comment_service.generate_comment(ctx, style_id)
                st.session_state[hash_key] = ctx_hash
                cached = st.session_state[comment_key]
                stale = False
            except Exception as exc:
                logger.warning("KI-Kommentar fehlgeschlagen: %s", exc)
                st.warning(t("ai_comment.failed"))

    if cached:
        if stale:
            st.caption(t("ai_comment.stale"))
        with st.container(border=True):
            st.caption(f"{style['emoji']} **{style['name']}**")
            st.markdown(cached)
