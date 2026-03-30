"""
Positionen — direktes CRUD für Portfolio und Watchlist, kein LLM.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from core.asset_class_config import get_asset_class_registry
from core.figi import RELEVANT_EXCH, openfigi_lookup, to_yahoo_ticker
from core.i18n import t
from core.storage.models import Position
from state import get_positions_repo

st.set_page_config(page_title="Positionen", page_icon="📋", layout="wide")
st.title(f"📋 {t('positionen.title')}")
st.caption(t("positionen.subtitle"))

registry = get_asset_class_registry()
repo = get_positions_repo()
asset_class_options = registry.all_names()

# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------

def _ss(key, default=None):
    return st.session_state.get(key, default)

def _set(**kwargs):
    for k, v in kwargs.items():
        st.session_state[k] = v

def _clear_form():
    for k in [
        "_pos_edit_id", "_pos_show_form", "_pos_confirm_del",
        "_pos_ticker", "_pos_figi_results",
        "_pos_isin", "_pos_wkn",
    ]:
        st.session_state.pop(k, None)

# ---------------------------------------------------------------------------
# [+ Neue Position] button
# ---------------------------------------------------------------------------

if st.button(t("positionen.add_button"), type="primary"):
    _clear_form()
    _set(_pos_show_form=True, _pos_edit_id=None)
    st.rerun()

# ---------------------------------------------------------------------------
# Form (add or edit)
# ---------------------------------------------------------------------------

if _ss("_pos_show_form"):
    edit_id: int | None = _ss("_pos_edit_id")
    editing: Position | None = repo.get(edit_id) if edit_id else None

    st.subheader(
        t("positionen.form_header_edit") if editing else t("positionen.form_header_add")
    )

    # ── ISIN / WKN lookup (outside st.form so button works independently) ──
    st.caption(t("positionen.lookup_caption"))
    col_isin, col_wkn, col_btn = st.columns([3, 2, 1])
    with col_isin:
        lookup_isin = st.text_input(
            t("positionen.col_isin"),
            value=_ss("_pos_isin", editing.isin if editing else "") or "",
            key="_pos_isin",
        )
    with col_wkn:
        lookup_wkn = st.text_input(
            t("positionen.col_wkn"),
            value=_ss("_pos_wkn", editing.wkn if editing else "") or "",
            key="_pos_wkn",
        )
    with col_btn:
        st.write("")
        st.write("")
        if st.button(t("positionen.lookup_button"), use_container_width=True):
            id_type = "ID_ISIN" if lookup_isin.strip() else "ID_WERTPAPIER"
            id_value = lookup_isin.strip() or lookup_wkn.strip()
            if id_value:
                with st.spinner(t("positionen.lookup_searching")):
                    results = openfigi_lookup(id_type, id_value)
                if results:
                    _set(_pos_figi_results=results)
                else:
                    st.session_state.pop("_pos_figi_results", None)
                    st.warning(t("positionen.lookup_not_found"))

    # Show picker if results available
    figi_results = _ss("_pos_figi_results", [])
    if figi_results:
        options = [
            f"{to_yahoo_ticker(r)}  —  {RELEVANT_EXCH.get(r.get('exchCode', ''), r.get('exchCode', ''))}"
            for r in figi_results
        ]
        chosen_idx = st.radio(
            t("positionen.lookup_pick"),
            options=range(len(options)),
            format_func=lambda i: options[i],
            key="_pos_figi_pick",
            horizontal=False,
        )
        if st.button(t("positionen.lookup_apply")):
            chosen = figi_results[chosen_idx]
            _set(_pos_ticker=to_yahoo_ticker(chosen))
            st.session_state.pop("_pos_figi_results", None)
            st.rerun()

    st.divider()

    # ── Main form ──────────────────────────────────────────────────────────
    with st.form("pos_form", clear_on_submit=False):
        col_a, col_b = st.columns(2)
        with col_a:
            form_name = st.text_input(
                t("positionen.col_name") + " *",
                value=editing.name if editing else "",
            )
        with col_b:
            form_ticker = st.text_input(
                t("positionen.col_ticker"),
                value=_ss("_pos_ticker", editing.ticker if editing else "") or "",
            )

        col_c, col_d = st.columns(2)
        with col_c:
            ac_default_idx = (
                asset_class_options.index(editing.asset_class)
                if editing and editing.asset_class in asset_class_options
                else 0
            )
            form_ac = st.selectbox(
                t("positionen.col_asset_class") + " *",
                options=asset_class_options,
                index=ac_default_idx,
            )
        with col_d:
            unit_options = ["Stück", "Troy Oz", "g"]
            unit_default_idx = (
                unit_options.index(editing.unit)
                if editing and editing.unit in unit_options
                else 0
            )
            form_unit = st.selectbox(
                t("positionen.col_unit"),
                options=unit_options,
                index=unit_default_idx,
            )

        col_e, col_f = st.columns(2)
        with col_e:
            form_qty = st.number_input(
                t("positionen.col_quantity") + " *",
                min_value=0.0,
                step=1.0,
                format="%.4f",
                value=float(editing.quantity) if editing and editing.quantity else 0.0,
            )
        with col_f:
            form_price = st.number_input(
                t("positionen.col_purchase_price"),
                min_value=0.0,
                step=0.01,
                format="%.4f",
                value=float(editing.purchase_price) if editing and editing.purchase_price else 0.0,
            )

        col_g, col_h = st.columns(2)
        with col_g:
            form_date = st.date_input(
                t("positionen.col_purchase_date"),
                value=editing.purchase_date if editing else None,
                min_value=date(2000, 1, 1),
            )
        with col_h:
            in_portfolio = st.checkbox(
                t("positionen.in_portfolio"),
                value=editing.in_portfolio if editing else True,
            )

        form_notes = st.text_input(
            t("positionen.col_notes"),
            value=(editing.notes or "") if editing else "",
        )

        col_save, col_cancel = st.columns([1, 5])
        with col_save:
            submitted = st.form_submit_button(t("positionen.save_button"), type="primary")
        with col_cancel:
            cancelled = st.form_submit_button(t("positionen.cancel_button"))

    if cancelled:
        _clear_form()
        st.rerun()

    if submitted:
        errs = []
        if not form_name.strip():
            errs.append(t("positionen.error_name"))
        if form_qty <= 0 and in_portfolio:
            errs.append(t("positionen.error_quantity"))
        if errs:
            for e in errs:
                st.error(e)
        else:
            cfg = registry.require(form_ac)
            pos_data = dict(
                asset_class=form_ac,
                investment_type=cfg.investment_type,
                name=form_name.strip(),
                ticker=(form_ticker or "").strip() or None,
                isin=(lookup_isin or "").strip() or (editing.isin if editing else None),
                wkn=(lookup_wkn or "").strip() or (editing.wkn if editing else None),
                quantity=form_qty if form_qty > 0 else None,
                unit=form_unit,
                purchase_price=form_price if form_price > 0 else None,
                purchase_date=form_date if form_date else None,
                notes=(form_notes or "").strip() or None,
                in_portfolio=in_portfolio,
                added_date=editing.added_date if editing else date.today(),
            )
            if editing:
                pos = editing.model_copy(update=pos_data)
                repo.update(pos)
            else:
                repo.add(Position(**pos_data))
            _clear_form()
            st.success(t("positionen.saved"))
            st.rerun()

    st.divider()

# ---------------------------------------------------------------------------
# Delete confirmation
# ---------------------------------------------------------------------------

confirm_id = _ss("_pos_confirm_del")
if confirm_id is not None:
    to_del = repo.get(confirm_id)
    if to_del:
        with st.warning(f"{t('positionen.confirm_delete')} **{to_del.name}**"):
            c1, c2, _ = st.columns([1, 1, 6])
            if c1.button(t("positionen.confirm_yes"), type="primary"):
                repo.delete(confirm_id)
                st.session_state.pop("_pos_confirm_del", None)
                st.success(t("positionen.deleted"))
                st.rerun()
            if c2.button(t("positionen.confirm_no")):
                st.session_state.pop("_pos_confirm_del", None)
                st.rerun()

# ---------------------------------------------------------------------------
# Position tables
# ---------------------------------------------------------------------------

tab_portfolio, tab_watchlist = st.tabs([
    t("positionen.tab_portfolio"),
    t("positionen.tab_watchlist"),
])


def _render_table(positions: list[Position], empty_key: str):
    if not positions:
        st.info(t(empty_key))
        return

    # Header row
    hc = st.columns([3, 1, 2, 1, 1, 1, 1, 0.4, 0.4])
    for col, label in zip(hc, [
        t("positionen.col_name"), t("positionen.col_ticker"),
        t("positionen.col_isin"), t("positionen.col_asset_class"),
        t("positionen.col_quantity"), t("positionen.col_unit"),
        t("positionen.col_purchase_price"), "", "",
    ]):
        col.markdown(f"**{label}**")

    st.divider()

    for pos in positions:
        cols = st.columns([3, 1, 2, 1, 1, 1, 1, 0.4, 0.4])
        cols[0].write(pos.name)
        cols[1].write(pos.ticker or "—")
        cols[2].write(pos.isin or pos.wkn or "—")
        cols[3].write(pos.asset_class)
        cols[4].write(
            f"{pos.quantity:,.2f}".rstrip("0").rstrip(".")
            if pos.quantity else "—"
        )
        cols[5].write(pos.unit)
        cols[6].write(
            f"{pos.purchase_price:,.2f} €" if pos.purchase_price else "—"
        )
        if cols[7].button("✏️", key=f"edit_{pos.id}", help=t("positionen.edit_tooltip")):
            _clear_form()
            _set(_pos_show_form=True, _pos_edit_id=pos.id)
            st.rerun()
        if cols[8].button("🗑️", key=f"del_{pos.id}", help=t("positionen.delete_tooltip")):
            _set(_pos_confirm_del=pos.id)
            st.rerun()


with tab_portfolio:
    _render_table(repo.get_portfolio(), "positionen.empty_portfolio")

with tab_watchlist:
    _render_table(repo.get_watchlist(), "positionen.empty_watchlist")
