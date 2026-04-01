"""
Positionen — direktes CRUD für Portfolio und Watchlist, kein LLM.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import streamlit as st

from core.asset_class_config import get_asset_class_registry
from core.figi import RELEVANT_EXCH, openfigi_lookup, to_yahoo_ticker
from core.i18n import t
from core.storage.models import Position
from state import get_analyses_repo, get_app_config_repo, get_positions_repo, get_skills_repo

st.set_page_config(page_title="Positionen", page_icon="📋", layout="wide")
st.title(f"📋 {t('positionen.title')}")
st.caption(t("positionen.subtitle"))

if st.session_state.pop("_pos_just_saved", None):
    st.success(t("positionen.saved"))

registry = get_asset_class_registry()
repo = get_positions_repo()
app_config = get_app_config_repo()
analyses_repo = get_analyses_repo()

def _fmtnum(value: float, decimals: int = 2) -> str:
    """Format a number in German locale style (1.234,56)."""
    formatted = f"{value:,.{decimals}f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


_DEFAULT_EMPFEHLUNG_LABELS = ["Kaufen", "Halten", "Verkaufen", "Beobachten"]
_empfehlung_labels: list[str] = app_config.get_json("empfehlung_labels", _DEFAULT_EMPFEHLUNG_LABELS)

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
        "_pos_ticker", "_pos_name", "_pos_figi_results",
        "_pos_isin", "_pos_wkn", "_pos_asset_class",
    ]:
        st.session_state.pop(k, None)

def _clear_detail():
    st.session_state.pop("_pos_detail_id", None)

# ---------------------------------------------------------------------------
# Detail dialog
# ---------------------------------------------------------------------------

@st.dialog(t("positionen.detail_title"), width="large")
def _show_detail(pos_id: int):
    pos = repo.get(pos_id)
    if not pos:
        st.error("Position not found.")
        return

    cfg = registry.get(pos.asset_class)
    extra = pos.extra_data or {}

    # ── Header ──────────────────────────────────────────────────────────────
    c1, c2 = st.columns([3, 1])
    c1.subheader(pos.name)
    if pos.ticker:
        c1.caption(pos.ticker)
    if c2.button(t("positionen.edit_button_detail"), use_container_width=True):
        _clear_detail()
        _clear_form()
        _set(_pos_show_form=True, _pos_edit_id=pos_id)
        st.rerun()

    st.divider()

    # ── Core fields ─────────────────────────────────────────────────────────
    col_a, col_b = st.columns(2)
    col_a.markdown(f"**{t('positionen.col_asset_class')}:** {pos.asset_class}")
    col_b.markdown(f"**{t('positionen.col_unit')}:** {pos.unit}")

    if pos.isin or pos.wkn:
        col_c, col_d = st.columns(2)
        col_c.markdown(f"**{t('positionen.col_isin')}:** {pos.isin or '—'}")
        col_d.markdown(f"**{t('positionen.col_wkn')}:** {pos.wkn or '—'}")

    if pos.quantity is not None:
        col_e, col_f = st.columns(2)
        col_e.markdown(f"**{t('positionen.col_quantity')}:** {_fmtnum(pos.quantity, 4).rstrip('0').rstrip(',')}")
        col_f.markdown(
            f"**{t('positionen.col_purchase_price')}:** "
            f"{_fmtnum(pos.purchase_price)} €" if pos.purchase_price else f"**{t('positionen.col_purchase_price')}:** —"
        )

    if pos.purchase_date:
        st.markdown(f"**{t('positionen.col_purchase_date')}:** {pos.purchase_date.isoformat()}")

    if pos.empfehlung or pos.recommendation_source:
        rec_parts = []
        if pos.empfehlung:
            rec_parts.append(pos.empfehlung)
        if pos.recommendation_source:
            rec_parts.append(f"{t('positionen.empfohlen_von')}: {pos.recommendation_source}")
        st.markdown(f"**{t('positionen.empfehlung')}:** {' · '.join(rec_parts)}")

    if pos.story:
        st.markdown(f"**{t('positionen.story_label')}:**")
        st.info(pos.story)

    if pos.notes:
        st.markdown(f"**{t('positionen.col_notes')}:** {pos.notes}")

    # ── Festgeld extra fields ────────────────────────────────────────────────
    if pos.asset_class == "Festgeld":
        st.divider()
        fe_a, fe_b, fe_c = st.columns(3)
        fe_a.markdown(
            f"**{t('positionen.interest_rate')}:** "
            f"{extra.get('interest_rate', '—')} %"
            if extra.get("interest_rate") else f"**{t('positionen.interest_rate')}:** —"
        )
        fe_b.markdown(
            f"**{t('positionen.maturity_date')}:** "
            f"{extra.get('maturity_date', '—')}"
        )
        fe_c.markdown(
            f"**{t('positionen.bank')}:** {extra.get('bank', '—')}"
        )

    # ── Manual valuation section (Immobilie, Grundstück) ────────────────────
    if cfg and cfg.manual_valuation:
        st.divider()
        st.markdown(f"#### {t('positionen.update_value_header')}")

        current_est = extra.get("estimated_value")
        current_val_date_str = extra.get("valuation_date")

        # Stale warning
        if current_val_date_str:
            try:
                val_date = date.fromisoformat(current_val_date_str)
                days_old = (date.today() - val_date).days
                if days_old > 180:
                    st.warning(t("positionen.valuation_stale_warning").format(days=days_old))
            except ValueError:
                pass

        col_val, col_date = st.columns(2)
        with col_val:
            new_est = st.number_input(
                t("positionen.estimated_value"),
                min_value=0.0,
                step=1000.0,
                format="%.2f",
                value=float(current_est) if current_est is not None else 0.0,
                key=f"_detail_est_val_{pos_id}",
            )
        with col_date:
            new_val_date = st.date_input(
                t("positionen.valuation_date"),
                value=date.fromisoformat(current_val_date_str) if current_val_date_str else date.today(),
                key=f"_detail_val_date_{pos_id}",
            )

        if st.button(t("positionen.save_estimated_value"), key=f"_save_est_{pos_id}", type="primary"):
            new_extra = dict(extra)
            new_extra["estimated_value"] = new_est if new_est > 0 else None
            new_extra["valuation_date"] = new_val_date.isoformat() if new_val_date else None
            updated = pos.model_copy(update={"extra_data": new_extra})
            repo.update(updated)
            st.success(t("positionen.value_updated"))
            st.rerun()

    st.divider()
    if st.button(t("positionen.close_button"), use_container_width=True):
        st.rerun()

# ---------------------------------------------------------------------------
# Open detail dialog if requested
# ---------------------------------------------------------------------------

detail_id = _ss("_pos_detail_id")
if detail_id is not None:
    _show_detail(detail_id)

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
    editing: Optional[Position] = repo.get(edit_id) if edit_id else None

    st.subheader(
        t("positionen.form_header_edit") if editing else t("positionen.form_header_add")
    )

    # ── Asset class selector OUTSIDE the form ────────────────────────────────
    # This must be outside so changing it triggers a rerun before the form renders.
    all_ac_options = registry.all_names()
    ac_key = "_pos_asset_class"
    if ac_key not in st.session_state:
        default_ac = editing.asset_class if editing else all_ac_options[0]
        st.session_state[ac_key] = default_ac

    selected_ac = st.selectbox(
        t("positionen.col_asset_class") + " *",
        options=all_ac_options,
        key=ac_key,
    )
    cfg = registry.require(selected_ac)

    # Watchlist-eligibility note
    if not cfg.watchlist_eligible:
        st.caption(t("positionen.watchlist_ineligible_note"))

    # ── ISIN / WKN lookup (outside form, only for types that use them) ────────
    shows_isin_wkn = cfg.is_field_visible("isin") or cfg.is_field_visible("wkn")
    if shows_isin_wkn:
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
                if chosen.get("name") and not _ss("_pos_name"):
                    _set(_pos_name=chosen["name"])
                st.session_state.pop("_pos_figi_results", None)
                st.rerun()
    else:
        lookup_isin = editing.isin if editing else ""
        lookup_wkn = editing.wkn if editing else ""

    st.divider()

    # ── Main form ─────────────────────────────────────────────────────────────
    with st.form("pos_form", clear_on_submit=False):

        # Name (always required)
        col_a, col_b = st.columns(2)
        with col_a:
            form_name = st.text_input(
                t("positionen.col_name") + " *",
                value=_ss("_pos_name", editing.name if editing else "") or "",
            )

        # Ticker (only for auto_fetch types)
        with col_b:
            if cfg.auto_fetch:
                form_ticker = st.text_input(
                    t("positionen.col_ticker"),
                    value=_ss("_pos_ticker", editing.ticker if editing else "") or "",
                )
            else:
                form_ticker = None
                st.empty()

        # Unit (only if multiple options or "unit" in visible_fields)
        col_c, col_d = st.columns(2)
        with col_c:
            unit_options = cfg.unit_options if cfg.unit_options else [cfg.default_unit]
            if len(unit_options) > 1:
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
            else:
                form_unit = unit_options[0]
                st.caption(f"{t('positionen.col_unit')}: {form_unit}")

        # Empfehlung dropdown
        with col_d:
            empf_opts = [""] + _empfehlung_labels
            empf_default = editing.empfehlung if editing and editing.empfehlung in empf_opts else ""
            empf_idx = empf_opts.index(empf_default)
            form_empfehlung = st.selectbox(
                t("positionen.empfehlung"),
                options=empf_opts,
                index=empf_idx,
                format_func=lambda x: x if x else "—",
            )

        # Empfohlen von (recommendation source — free text)
        col_rec, _ = st.columns(2)
        with col_rec:
            form_rec_source = st.text_input(
                t("positionen.empfohlen_von"),
                value=(editing.recommendation_source or "") if editing else "",
                placeholder=t("positionen.empfohlen_von_placeholder"),
            )

        # Quantity (optional for manual_valuation types; hidden for Grundstück)
        shows_quantity = cfg.is_field_visible("quantity") or (
            cfg.manual_valuation and selected_ac != "Grundstück"
        )
        col_e, col_f = st.columns(2)
        with col_e:
            if shows_quantity:
                form_qty = st.number_input(
                    t("positionen.col_quantity"),
                    min_value=0.0,
                    step=1.0,
                    format="%.4f",
                    value=float(editing.quantity) if editing and editing.quantity else 0.0,
                )
            else:
                form_qty = None

        # Purchase price (for types with purchase_price visible)
        with col_f:
            if cfg.is_field_visible("purchase_price"):
                form_price = st.number_input(
                    t("positionen.col_purchase_price"),
                    min_value=0.0,
                    step=0.01,
                    format="%.4f",
                    value=float(editing.purchase_price) if editing and editing.purchase_price else 0.0,
                )
            else:
                form_price = None

        # Purchase date
        col_g, col_h = st.columns(2)
        with col_g:
            if cfg.is_field_visible("purchase_date"):
                form_date = st.date_input(
                    t("positionen.col_purchase_date"),
                    value=editing.purchase_date if editing else None,
                    min_value=date(2000, 1, 1),
                )
            else:
                form_date = None

        # Portfolio / Watchlist flags
        with col_h:
            if cfg.watchlist_eligible:
                flag_col1, flag_col2 = st.columns(2)
                with flag_col1:
                    in_portfolio = st.checkbox(
                        t("positionen.in_portfolio"),
                        value=editing.in_portfolio if editing else True,
                    )
                with flag_col2:
                    in_watchlist = st.checkbox(
                        t("positionen.in_watchlist"),
                        value=editing.in_watchlist if editing else False,
                    )
            else:
                in_portfolio = True
                in_watchlist = False

        # Notes (always)
        form_notes = st.text_input(
            t("positionen.col_notes"),
            value=(editing.notes or "") if editing else "",
        )

        # Story textarea (always)
        form_story = st.text_area(
            t("positionen.story_label"),
            value=(editing.story or "") if editing else "",
            placeholder=t("positionen.story_placeholder"),
            height=80,
        )

        # Anlage-Idee selector — only visible when a story is being written
        _sc_skills = get_skills_repo().get_by_area("storychecker")
        _sc_skill_options = [""] + [s.name for s in _sc_skills]
        _current_skill = (editing.story_skill or "") if editing else ""
        _skill_idx = _sc_skill_options.index(_current_skill) if _current_skill in _sc_skill_options else 0
        form_story_skill = st.selectbox(
            t("positionen.story_skill_label"),
            options=_sc_skill_options,
            index=_skill_idx,
            help=t("positionen.story_skill_help"),
        )

        # ── Festgeld extra fields ──────────────────────────────────────────────
        existing_extra = (editing.extra_data or {}) if editing else {}
        if selected_ac == "Festgeld":
            st.markdown("---")
            fe_a, fe_b, fe_c = st.columns(3)
            with fe_a:
                form_interest_rate = st.number_input(
                    t("positionen.interest_rate"),
                    min_value=0.0,
                    max_value=100.0,
                    step=0.1,
                    format="%.2f",
                    value=float(existing_extra.get("interest_rate", 0.0)),
                )
            with fe_b:
                maturity_raw = existing_extra.get("maturity_date")
                form_maturity = st.date_input(
                    t("positionen.maturity_date"),
                    value=date.fromisoformat(maturity_raw) if maturity_raw else None,
                    min_value=date.today(),
                )
            with fe_c:
                form_bank = st.text_input(
                    t("positionen.bank"),
                    value=existing_extra.get("bank", ""),
                )
        else:
            form_interest_rate = None
            form_maturity = None
            form_bank = None

        # ── Save / Cancel ──────────────────────────────────────────────────────
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
        if not in_portfolio and not in_watchlist:
            errs.append(t("positionen.error_no_flag"))
        if form_qty is not None and form_qty <= 0 and in_portfolio and not cfg.manual_valuation:
            errs.append(t("positionen.error_quantity"))

        if errs:
            for e in errs:
                st.error(e)
        else:
            # Build extra_data
            extra: dict = dict(existing_extra)
            if selected_ac == "Festgeld":
                if form_interest_rate:
                    extra["interest_rate"] = form_interest_rate
                if form_maturity:
                    extra["maturity_date"] = form_maturity.isoformat()
                if form_bank and form_bank.strip():
                    extra["bank"] = form_bank.strip()

            # Preserve existing estimated_value for manual valuation types
            # (updated via detail dialog, not the edit form)

            pos_data = dict(
                asset_class=selected_ac,
                investment_type=cfg.investment_type,
                name=form_name.strip(),
                ticker=(form_ticker or "").strip() or None if form_ticker is not None else (editing.ticker if editing else None),
                isin=(lookup_isin or "").strip() or (editing.isin if editing else None) if shows_isin_wkn else (editing.isin if editing else None),
                wkn=(lookup_wkn or "").strip() or (editing.wkn if editing else None) if shows_isin_wkn else (editing.wkn if editing else None),
                quantity=form_qty if (form_qty is not None and form_qty > 0) else None,
                unit=form_unit,
                purchase_price=form_price if (form_price is not None and form_price > 0) else None,
                purchase_date=form_date if form_date else None,
                notes=(form_notes or "").strip() or None,
                extra_data=extra if extra else None,
                in_portfolio=in_portfolio,
                in_watchlist=in_watchlist,
                empfehlung=form_empfehlung or None,
                recommendation_source=(form_rec_source or "").strip() or None,
                story=(form_story or "").strip() or None,
                story_skill=form_story_skill or None,
                added_date=editing.added_date if editing else date.today(),
            )
            if editing:
                pos = editing.model_copy(update=pos_data)
                repo.update(pos)
            else:
                repo.add(Position(**pos_data))
            _clear_form()
            st.session_state["_pos_just_saved"] = True
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

_VERDICT_ICON = {"intact": "🟢", "gemischt": "🟡", "gefaehrdet": "🔴"}


def _render_table(positions: list[Position], empty_key: str, key_prefix: str):
    if not positions:
        st.info(t(empty_key))
        return

    positions = sorted(positions, key=lambda p: p.name.lower())

    verdicts = analyses_repo.get_latest_bulk(
        [p.id for p in positions if p.id], "storychecker"
    )

    # Header row (10 columns: name, ticker, isin, class, qty, unit, price, detail, edit, del)
    hc = st.columns([3, 1, 2, 1, 1, 1, 1, 0.4, 0.4, 0.4])
    for col, label in zip(hc, [
        t("positionen.col_name"), t("positionen.col_ticker"),
        t("positionen.col_isin"), t("positionen.col_asset_class"),
        t("positionen.col_quantity"), t("positionen.col_unit"),
        t("positionen.col_purchase_price"), "", "", "",
    ]):
        col.markdown(f"**{label}**")

    st.divider()

    for pos in positions:
        cols = st.columns([3, 1, 2, 1, 1, 1, 1, 0.4, 0.4, 0.4])
        analysis = verdicts.get(pos.id)
        verdict_badge = _VERDICT_ICON.get(analysis.verdict, "") if analysis else ""
        cols[0].write(f"{verdict_badge} {pos.name}" if verdict_badge else pos.name)
        cols[1].write(pos.ticker or "—")
        cols[2].write(pos.isin or pos.wkn or "—")
        cols[3].write(pos.asset_class)
        cols[4].write(
            _fmtnum(pos.quantity).rstrip("0").rstrip(",")
            if pos.quantity else "—"
        )
        cols[5].write(pos.unit)
        cols[6].write(
            f"{_fmtnum(pos.purchase_price)} €" if pos.purchase_price else "—"
        )
        if cols[7].button("🔍", key=f"{key_prefix}_det_{pos.id}", help=t("positionen.detail_tooltip")):
            _set(_pos_detail_id=pos.id)
            st.rerun()
        if cols[8].button("✏️", key=f"{key_prefix}_edit_{pos.id}", help=t("positionen.edit_tooltip")):
            _clear_form()
            _set(_pos_show_form=True, _pos_edit_id=pos.id)
            st.rerun()
        if cols[9].button("🗑️", key=f"{key_prefix}_del_{pos.id}", help=t("positionen.delete_tooltip")):
            _set(_pos_confirm_del=pos.id)
            st.rerun()


st.subheader(t("positionen.tab_portfolio"))
_render_table(repo.get_portfolio(), "positionen.empty_portfolio", "pf")

st.divider()

st.subheader(t("positionen.tab_watchlist"))
_render_table(repo.get_watchlist(), "positionen.empty_watchlist", "wl")

