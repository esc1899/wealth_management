"""
Positionen — direktes CRUD für Portfolio und Watchlist, kein LLM.
"""

from __future__ import annotations

import logging
from contextlib import nullcontext
from datetime import date, timedelta
from typing import Optional

import streamlit as st

from core.currency import symbol
from core.i18n import t

logger = logging.getLogger(__name__)

from config import config
from core.asset_class_config import get_asset_class_registry
from core.figi import RELEVANT_EXCH, openfigi_lookup, to_yahoo_ticker
from core.i18n import t
from core.storage.models import Position
from state import get_analysis_service, get_app_config_repo, get_market_agent, get_market_repo, get_position_story_service, get_positions_repo, get_skills_repo

st.set_page_config(page_title="Positionen", page_icon="📋", layout="wide")
st.title(f"📋 {t('positionen.title')}")
st.caption(t("positionen.subtitle"))

if st.session_state.pop("_pos_just_saved", None):
    st.toast(t("positionen.saved"), icon="✅")

registry = get_asset_class_registry()
repo = get_positions_repo()
app_config = get_app_config_repo()
_analysis_service = get_analysis_service()

def _fmtnum(value: float, decimals: int = 2) -> str:
    """Format a number in German locale style (1.234,56)."""
    formatted = f"{value:,.{decimals}f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


_market_repo = get_market_repo()


_TROY_OZ_TO_G = 31.1035


def _position_current_value(pos: Position) -> Optional[float]:
    """Return current EUR value of a position, or None if unknown."""
    if pos.ticker:
        pr = _market_repo.get_price(pos.ticker)
        if pr is not None and pos.quantity is not None:
            if pos.unit == "g":
                return (pr.price_eur / _TROY_OZ_TO_G) * pos.quantity
            return pos.quantity * pr.price_eur
    if pos.asset_class == "Bargeld" and pos.quantity is not None:
        return pos.quantity
    extra = pos.extra_data or {}
    est = extra.get("estimated_value")
    if est is not None:
        return float(est)
    # Fallback to purchase_price only for manual-valuation classes (auto_fetch=false).
    # Auto-fetch positions without a cached price just don't have data yet.
    cfg = registry.get(pos.asset_class)
    if cfg and not cfg.auto_fetch and pos.purchase_price is not None:
        if pos.quantity is not None:
            return pos.quantity * pos.purchase_price
        return pos.purchase_price
    return None


# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------

def _ss(key, default=None):
    return st.session_state.get(key, default)

def _set(**kwargs):
    for k, v in kwargs.items():
        st.session_state[k] = v

def _clear_form():
    """Clear all form-related keys from session state, including any open detail dialog."""
    for k in [
        "_pos_edit_id", "_pos_show_form", "_pos_confirm_del",
        "_pos_detail_id", "_pos_dialog_mode",
        "_pos_ticker", "_pos_name", "_pos_figi_results",
        "_pos_isin", "_pos_wkn", "_pos_asset_class",
        "_pos_story_draft", "_pos_form_story", "_pos_form_story_owner", "_pos_figi_pick",
        "_pos_story_gen", "_pos_form_notified",
    ]:
        st.session_state.pop(k, None)

    # Clear dynamic keys (detail dialog inputs for valuation and rebalance exclusion)
    # These use the pattern _detail_<field>_<pos_id> or _save_est_<pos_id>
    keys_to_remove = [k for k in st.session_state.keys() if k.startswith(("_detail_", "_save_est_"))]
    for k in keys_to_remove:
        st.session_state.pop(k, None)

def _open_detail(pos_id: int):
    """Open position dialog in view mode, clearing any other state."""
    _clear_form()
    _set(_pos_detail_id=pos_id, _pos_dialog_mode="view")

def _open_edit(pos_id: int | None):
    """Open position dialog in edit mode, clearing any other state."""
    _clear_form()
    _set(_pos_detail_id=pos_id, _pos_dialog_mode="edit")

def _open_delete(pos_id: int):
    """Open delete confirmation, clearing any other state."""
    _clear_form()
    _set(_pos_confirm_del=pos_id)

# ---------------------------------------------------------------------------
# Edit form rendering (used in unified dialog)
# ---------------------------------------------------------------------------

def _render_edit_form(pos_id: int | None, readonly: bool = False):
    """Render the edit form for a position (view or inside dialog).

    Args:
        pos_id: Position ID to edit, or None for new position
        readonly: If True, all fields are disabled (view-only mode)
    """
    editing = repo.get(pos_id) if pos_id else None

    # Initialize form state explicitly to prevent sticky state between opens
    if "_pos_form_story" not in st.session_state or st.session_state.get("_pos_form_story_owner") != pos_id:
        st.session_state["_pos_form_story"] = (editing.story or "") if editing else ""
        st.session_state["_pos_form_story_owner"] = pos_id

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
        disabled=readonly,
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
                disabled=readonly,
            )
        with col_wkn:
            lookup_wkn = st.text_input(
                t("positionen.col_wkn"),
                value=_ss("_pos_wkn", editing.wkn if editing else "") or "",
                key="_pos_wkn",
                disabled=readonly,
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

    # ── Story suggestion (outside form — needs its own rerun) ────────────────
    # Seed story textarea state on first render so it shows the existing story.
    if "_pos_form_story" not in st.session_state:
        st.session_state["_pos_form_story"] = (editing.story or "") if editing else ""

    _suggest_name = _ss("_pos_name", editing.name if editing else "") or ""
    _suggest_ticker = _ss("_pos_ticker", editing.ticker if editing else "") or None
    _suggest_ac = st.session_state.get("_pos_asset_class", selected_ac)
    _current_story = st.session_state.get("_pos_form_story") or ""

    _btn_label = t("positionen.story_update_button") if _current_story else t("positionen.story_suggest_button")
    if _suggest_name and st.button(_btn_label, key="_pos_story_gen"):
        _story_err = None
        with st.spinner(t("positionen.story_suggest_spinner")):
            try:
                story_service = get_position_story_service()
                _draft = story_service.generate_position_story(
                    name=_suggest_name,
                    ticker=_suggest_ticker or None,
                    asset_class=_suggest_ac,
                    existing_story=_current_story or None,
                )
                st.session_state["_pos_form_story"] = _draft
            except Exception as _exc:
                _story_err = str(_exc)
        if _story_err:
            st.error(f"{t('positionen.story_suggest_error')}: {_story_err}")
        else:
            st.toast(t("positionen.story_suggest_hint"), icon="✨")
            st.rerun()

    st.divider()

    # ── Form wrapper (conditional: only in edit mode; view mode uses nullcontext) ───
    form_ctx = st.form("pos_form", clear_on_submit=False) if not readonly else nullcontext()
    with form_ctx:

        # Form contents (rendered in proper context manager)

        # Name (always required)
        col_a, col_b = st.columns(2)
        with col_a:
            form_name = st.text_input(
                t("positionen.col_name") + " *",
                value=_ss("_pos_name", editing.name if editing else "") or "",
                disabled=readonly,
            )

        # Ticker (only for auto_fetch types)
        with col_b:
            if cfg.auto_fetch:
                form_ticker = st.text_input(
                    t("positionen.col_ticker"),
                    value=_ss("_pos_ticker", editing.ticker if editing else "") or "",
                    disabled=readonly,
                )
            else:
                form_ticker = None
                st.empty()

        # Unit (only if multiple options or "unit" in visible_fields)
        with st.container():
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
                    disabled=readonly,
                )
            else:
                form_unit = unit_options[0]
                st.caption(f"{t('positionen.col_unit')}: {form_unit}")

        form_empfehlung = editing.empfehlung if editing else None

        # Anlageart (sub-type dropdown — only if asset class has anlagearten defined)
        _anlagearten = cfg.anlagearten
        if _anlagearten:
            _al_opts = [""] + _anlagearten
            _al_default = (editing.anlageart or "") if editing else ""
            _al_idx = _al_opts.index(_al_default) if _al_default in _al_opts else 0
            col_al, _ = st.columns(2)
            with col_al:
                form_anlageart = st.selectbox(
                    t("positionen.anlageart_label"),
                    options=_al_opts,
                    index=_al_idx,
                    format_func=lambda x: x if x else "—",
                    disabled=readonly,
                )
        else:
            form_anlageart = None

        # Empfehlung: Source + Analysis Exclusion (in bordered container)
        with st.container(border=True):
            col_rec, col_excl = st.columns(2)

            with col_rec:
                # Collect all existing recommendation sources
                all_positions = repo.get_portfolio() + repo.get_watchlist()
                existing_sources = sorted(
                    {p.recommendation_source for p in all_positions if p.recommendation_source},
                    key=str.lower
                )

                # Default index: use editing value if it exists in options, else None (first option)
                source_default = editing.recommendation_source if editing and editing.recommendation_source in existing_sources else None
                source_idx = existing_sources.index(source_default) if source_default else 0

                # Selectbox: only for existing sources
                selected_existing = st.selectbox(
                    t("positionen.empfohlen_von"),
                    options=[None] + existing_sources,
                    index=source_idx + 1 if source_default else 0,
                    format_func=lambda x: x or "—",
                    disabled=readonly,
                )

                # Text input: for entering a new source (appears below selectbox)
                new_source_input = st.text_input(
                    t("positionen.new_recommendation_source_label"),
                    value="",
                    placeholder="Oder neuen Empfehler eingeben...",
                    disabled=readonly,
                )

                # Use whichever was filled in: new_source_input takes priority
                form_rec_source = new_source_input if new_source_input else selected_existing

            with col_excl:
                # Analysis exclusion checkbox
                analysis_excluded = st.checkbox(
                    t("positionen.analysis_excluded_label"),
                    value=editing.analysis_excluded if editing else False,
                    help=t("positionen.analysis_excluded_help") if t("positionen.analysis_excluded_help") else None,
                    disabled=readonly,
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
                    disabled=readonly,
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
                    disabled=readonly,
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
                    max_value=date.today(),
                    disabled=readonly,
                )
            else:
                form_date = None

        # Get existing extra_data early (needed for manual valuation fields)
        _existing_extra_early = (editing.extra_data or {}) if editing else {}

        # Portfolio / Watchlist flags + Analysis exclusion
        with col_h:
            if cfg.watchlist_eligible:
                flag_col1, flag_col2 = st.columns(2)
                with flag_col1:
                    in_portfolio = st.checkbox(
                        t("positionen.in_portfolio"),
                        value=editing.in_portfolio if editing else True,
                        disabled=readonly,
                    )
                with flag_col2:
                    in_watchlist = st.checkbox(
                        t("positionen.in_watchlist"),
                        value=editing.in_watchlist if editing else False,
                        disabled=readonly,
                    )
            else:
                in_portfolio = True
                in_watchlist = False


        # Manual valuation fields (Grundstück, Immobilie, Festgeld, Bargeld, Anleihe)
        if cfg.manual_valuation:
            st.markdown("---")
            st.markdown("#### 💰 Schätzwert")
            mv_col1, mv_col2 = st.columns(2)
            with mv_col1:
                form_estimated_value = st.number_input(
                    t("positionen.estimated_value"),
                    min_value=0.0,
                    step=1000.0,
                    format="%.2f",
                    value=float(_existing_extra_early.get("estimated_value", 0.0)) if _existing_extra_early.get("estimated_value") else 0.0,
                    disabled=readonly,
                )
            with mv_col2:
                val_date_raw = _existing_extra_early.get("valuation_date")
                form_valuation_date = st.date_input(
                    t("positionen.valuation_date"),
                    value=date.fromisoformat(val_date_raw) if val_date_raw else date.today(),
                    disabled=readonly,
                )
        else:
            form_estimated_value = None
            form_valuation_date = None

        # Notes (always)
        form_notes = st.text_input(
            t("positionen.col_notes"),
            value=(editing.notes or "") if editing else "",
            disabled=readonly,
        )

        # Story textarea — state managed via "_pos_form_story" key (supports AI draft injection)
        form_story = st.text_area(
            t("positionen.story_label"),
            key="_pos_form_story",
            placeholder=t("positionen.story_placeholder"),
            height=120,
            disabled=readonly,
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
            disabled=readonly,
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
                    disabled=readonly,
                )
            with fe_b:
                maturity_raw = existing_extra.get("maturity_date")
                form_maturity = st.date_input(
                    t("positionen.maturity_date"),
                    value=date.fromisoformat(maturity_raw) if maturity_raw else None,
                    min_value=date.today(),
                    disabled=readonly,
                )
            with fe_c:
                form_bank = st.text_input(
                    t("positionen.bank"),
                    value=existing_extra.get("bank", ""),
                    disabled=readonly,
                )
        elif selected_ac == "Anleihe":
            st.markdown("---")
            an_a, an_b = st.columns(2)
            with an_a:
                form_interest_rate = st.number_input(
                    t("positionen.interest_rate"),
                    min_value=0.0,
                    max_value=100.0,
                    step=0.1,
                    format="%.2f",
                    value=float(existing_extra.get("interest_rate", 0.0)),
                    disabled=readonly,
                )
            with an_b:
                maturity_raw = existing_extra.get("maturity_date")
                form_maturity = st.date_input(
                    t("positionen.maturity_date"),
                    value=date.fromisoformat(maturity_raw) if maturity_raw else None,
                    min_value=date.today(),
                    disabled=readonly,
                )
            form_bank = None
        else:
            form_interest_rate = None
            form_maturity = None
            form_bank = None

        # ── Dividend Yield Override (all asset classes) ────────────────────────
        st.markdown("---")
        st.markdown("#### 📊 Dividende / Zinssatz (manueller Override)")

        # Show current yfinance value if available
        form_ticker = editing.ticker if editing else _ss("_pos_ticker", "")
        if form_ticker:
            div_rec = _market_repo.get_dividend(form_ticker)
            if div_rec:
                rate_str = f"{div_rec.rate_eur:.4f}€/Aktie" if div_rec.rate_eur is not None else "Kurs n/a"
                date_str = div_rec.fetched_at.strftime('%d.%m.%Y') if div_rec.fetched_at else "—"
                st.info(f"ℹ️ Aktuell von yfinance: {(div_rec.yield_pct or 0) * 100:.2f}% ({rate_str}, Stand: {date_str})")
            existing_override = existing_extra.get("dividend_yield_override", 0.0)
            if existing_override and existing_override > 0:
                st.info(f"⚠️ Override aktiv: {existing_override:.2f}% → yfinance-Wert wird ignoriert")

        form_dividend_override = st.number_input(
            "Jährlicher Zinssatz / Dividendenrendite (%)",
            min_value=0.0,
            max_value=100.0,
            step=0.1,
            format="%.2f",
            value=float(existing_extra.get("dividend_yield_override", 0.0)),
            help="Wenn > 0: nutze diesen Wert statt yfinance-Daten oder berechneter Werte. Z.B. 3.5 für 3,5%",
            disabled=readonly,
        )

        # ── Save / Cancel (only in edit mode) ──────────────────────────────────
        if not readonly:
            col_save, col_cancel = st.columns([1, 5])
            with col_save:
                submitted = st.form_submit_button(t("positionen.save_button"), type="primary")
            with col_cancel:
                cancelled = st.form_submit_button(t("positionen.cancel_button"))
        else:
            submitted = False
            cancelled = False

    # Handle form submission (after with block, variables always defined)
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
        if form_ticker is not None:
            ticker_clean = (form_ticker or "").strip()
            if cfg.auto_fetch and in_portfolio and not ticker_clean:
                errs.append(t("positionen.error_ticker_required"))
            elif ticker_clean and (" " in ticker_clean or len(ticker_clean) > 20):
                errs.append(t("positionen.error_ticker_format"))

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
            elif selected_ac == "Anleihe":
                if form_interest_rate:
                    extra["interest_rate"] = form_interest_rate
                if form_maturity:
                    extra["maturity_date"] = form_maturity.isoformat()

            # Manual valuation fields (Grundstück, Immobilie, Festgeld, Bargeld, Anleihe)
            if cfg.manual_valuation:
                if form_estimated_value and form_estimated_value > 0:
                    extra["estimated_value"] = form_estimated_value
                elif "estimated_value" in extra:
                    del extra["estimated_value"]
                if form_valuation_date:
                    extra["valuation_date"] = form_valuation_date.isoformat()

            # Dividend yield override (all asset classes)
            if form_dividend_override and form_dividend_override > 0:
                extra["dividend_yield_override"] = form_dividend_override
            elif "dividend_yield_override" in extra:
                del extra["dividend_yield_override"]

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
                analysis_excluded=analysis_excluded,
                empfehlung=form_empfehlung or None,
                recommendation_source=(form_rec_source or "").strip() or None,
                story=(form_story or "").strip() or None,
                story_skill=form_story_skill or None,
                anlageart=form_anlageart or None,
                added_date=editing.added_date if editing else date.today(),
            )
            if editing:
                pos = editing.model_copy(update=pos_data)
                repo.update(pos)
            else:
                saved = repo.add(Position(**pos_data))
                # Auto-fetch current price for new auto-fetch positions with a ticker
                if saved.ticker and cfg.auto_fetch:
                    with st.spinner(t("positionen.fetching_price")):
                        try:
                            get_market_agent().fetch_all_now()
                        except Exception as e:
                            logger.warning("Auto-fetch after save failed (non-critical): %s", e)
            _clear_form()
            st.session_state["_pos_just_saved"] = True
            st.rerun()

# ---------------------------------------------------------------------------
# Detail dialog
# ---------------------------------------------------------------------------

@st.dialog(t("positionen.detail_title"), width="large")
def _show_detail(pos_id: int | None):
    # Handle new position (pos_id=None) - skip to edit form
    if pos_id is None:
        st.subheader(t("positionen.form_header_add"))
        st.divider()
        _render_edit_form(None)
        return

    pos = repo.get(pos_id)
    if not pos:
        st.error("Position not found.")
        return

    mode = _ss("_pos_dialog_mode", "view")

    # ── Header with mode toggle ──────────────────────────────────────────────
    c1, c2, c3 = st.columns([3, 1, 1])
    c1.subheader(pos.name)
    if pos.ticker:
        c1.caption(pos.ticker)

    # Mode toggle button
    toggle_label = "✏️ " + t("positionen.edit_button_detail") if mode == "view" else "👁 Ansicht"
    if c2.button(toggle_label, key=f"toggle_mode_{pos_id}", use_container_width=True):
        _set(_pos_dialog_mode="edit" if mode == "view" else "view")
        st.rerun()
        return

    # Close button
    if c3.button("✕", key=f"close_dialog_{pos_id}", use_container_width=True):
        _clear_form()
        st.rerun()
        return

    st.divider()

    # ── VIEW MODE ──────────────────────────────────────────────────────────────
    if mode == "view":
        # Show the same form as edit mode, but with all fields disabled (readonly)
        if pos.asset_class == "Kryptowährung":
            st.warning(t("positionen.crypto_warning"), icon="⚠️")

        st.divider()
        _render_edit_form(pos_id, readonly=True)

        st.divider()

        # ── Dividend / Interest display ──────────────────────────────────────────
        extra = pos.extra_data or {}
        div_record = _market_repo.get_dividend(pos.ticker) if pos.ticker else None
        override_yield = extra.get("dividend_yield_override")

        if div_record or override_yield:
            st.markdown("#### 📊 Dividende / Ausschüttung")
            if override_yield and override_yield > 0:
                annual = (pos.quantity * div_record.rate_eur) if (pos.quantity and div_record and div_record.rate_eur) else None
                if annual is None and pos.quantity:
                    annual = (pos.quantity * _position_current_value(pos) * override_yield / 100) if _position_current_value(pos) else None
                col_src, col_yield, col_annual = st.columns(3)
                col_src.markdown(f"**Quelle:** Override")
                col_yield.markdown(f"**Rendite:** {override_yield:.2f} %")
                if annual:
                    col_annual.markdown(f"**Jährlich:** {symbol()}{annual:,.0f}")
            elif div_record:
                annual = pos.quantity * div_record.rate_eur if pos.quantity else None
                col_src, col_yield, col_annual = st.columns(3)
                col_src.markdown(f"**Quelle:** yfinance")
                col_yield.markdown(f"**Rendite:** {(div_record.yield_pct or 0) * 100:.2f} %")
                if annual:
                    col_annual.markdown(f"**Jährlich:** {symbol()}{annual:,.0f}")

        st.divider()

        # ── Analysis exclusion toggle ────────────────────────────────────────────
        new_excl = st.toggle(
            t("positionen.analysis_excluded_label"),
            value=pos.analysis_excluded,
            help=t("positionen.analysis_excluded_help"),
            key=f"_detail_excl_{pos_id}",
        )
        if new_excl != pos.analysis_excluded:
            updated = pos.model_copy(update={"analysis_excluded": new_excl})
            repo.update(updated)
            st.success(t("positionen.saved"))
            st.rerun()

    else:
        # ── EDIT MODE ──────────────────────────────────────────────────────────────
        _render_edit_form(pos_id)

# ---------------------------------------------------------------------------
# Open dialog if requested (detail/edit view)
# ---------------------------------------------------------------------------

mode = _ss("_pos_dialog_mode")
detail_id = _ss("_pos_detail_id")
# Dialog triggered when: viewing existing pos, editing existing pos, or creating new pos
if mode is not None:
    _show_detail(detail_id)

# ---------------------------------------------------------------------------
# [+ Neue Position] button
# ---------------------------------------------------------------------------

if st.button(t("positionen.add_button"), type="primary"):
    _open_edit(None)
    st.rerun()

# ---------------------------------------------------------------------------
# Delete confirmation dialog
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Delete confirmation dialog
# ---------------------------------------------------------------------------

@st.dialog(t("positionen.confirm_delete"))
def _show_delete_dialog(pos_id: int):
    pos = repo.get(pos_id)
    if not pos:
        st.error("Position not found.")
        return

    st.warning(f"**{pos.name}** wird gelöscht. Diese Aktion kann nicht rückgängig gemacht werden.")

    col_yes, col_no = st.columns(2)
    if col_yes.button(t("positionen.confirm_yes"), type="primary", use_container_width=True):
        repo.delete(pos_id)
        _clear_form()
        st.toast(t("positionen.deleted"), icon="🗑️")
        st.rerun()
    if col_no.button(t("positionen.confirm_no"), use_container_width=True):
        _clear_form()
        st.rerun()

confirm_id = _ss("_pos_confirm_del")
if confirm_id is not None:
    _show_delete_dialog(confirm_id)

# ---------------------------------------------------------------------------
# Position tables
# ---------------------------------------------------------------------------

_VERDICT_ICON = {"intact": "🟢", "gemischt": "🟡", "gefaehrdet": "🔴"}

# Pre-fetch all dividend records once for efficient lookup
_all_divs = _market_repo.get_all_dividends()

def _get_dividend_yield(pos: Position) -> Optional[str]:
    """Get dividend yield for position: override > yfinance > None"""
    extra = pos.extra_data or {}
    override = extra.get("dividend_yield_override")
    if override and override > 0:
        return f"{override:.2f} %"
    if pos.ticker and pos.ticker in _all_divs:
        div_rec = _all_divs[pos.ticker]
        if div_rec.yield_pct:
            return f"{div_rec.yield_pct * 100:.2f} %"
    return None


def _render_table(positions: list[Position], empty_key: str, key_prefix: str):
    if not positions:
        st.info(t(empty_key))
        return

    positions = sorted(positions, key=lambda p: p.name.lower())

    verdicts = _analysis_service.get_verdicts(
        [p.id for p in positions if p.id], "storychecker"
    )

    # Header row (13 columns: name, ticker, isin, class, qty, unit, current_value, div_yield, analysis_excl, override, detail, edit, del)
    hc = st.columns([3, 1, 2, 1, 1, 1, 1.3, 0.8, 0.35, 0.35, 0.4, 0.4, 0.4])
    for col, label in zip(hc, [
        t("positionen.col_name"), t("positionen.col_ticker"),
        t("positionen.col_isin"), t("positionen.col_asset_class"),
        t("positionen.col_quantity"), t("positionen.col_unit"),
        "Akt. Wert", "Div.-Rendite", "🔬 Analys.", "⚠️ Overr.", "", "", "",
    ]):
        col.markdown(f"**{label}**")

    st.divider()

    for pos in positions:
        cols = st.columns([3, 1, 2, 1, 1, 1, 1.3, 0.8, 0.35, 0.35, 0.4, 0.4, 0.4])
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

        _cur_val = _position_current_value(pos)
        if _cur_val is not None:
            _val_str = f"**{_fmtnum(_cur_val, 0)} €**"
            # Show gain/loss vs purchase cost if both are known
            if pos.purchase_price and pos.quantity:
                _cost = pos.purchase_price * pos.quantity
                _pnl_pct = (_cur_val - _cost) / _cost * 100
                _pnl_icon = "▲" if _pnl_pct >= 0 else "▼"
                _val_str += f"  \n{_pnl_icon} {_pnl_pct:+.1f}%"
            elif pos.purchase_price and not pos.quantity:
                # single-unit (Immobilie etc.): compare directly
                _pnl_pct = (_cur_val - pos.purchase_price) / pos.purchase_price * 100
                _pnl_icon = "▲" if _pnl_pct >= 0 else "▼"
                _val_str += f"  \n{_pnl_icon} {_pnl_pct:+.1f}%"
            cols[6].markdown(_val_str)
        else:
            cols[6].write("—")

        div_yield = _get_dividend_yield(pos)
        cols[7].write(div_yield or "—")

        # analysis_excluded indicator
        cols[8].write("🔬" if pos.analysis_excluded else "—")

        # Manual override indicator
        extra = pos.extra_data or {}
        cfg = registry.get(pos.asset_class)
        has_override = bool(extra.get("dividend_yield_override")) or (
            bool(extra.get("estimated_value")) and cfg and cfg.manual_valuation
        )
        cols[9].write("⚠️" if has_override else "—")

        if cols[10].button("🔍", key=f"{key_prefix}_det_{pos.id}", help=t("positionen.detail_tooltip")):
            _open_detail(pos.id)
            st.rerun()
        if cols[11].button("✏️", key=f"{key_prefix}_edit_{pos.id}", help=t("positionen.edit_tooltip")):
            _open_edit(pos.id)
            st.rerun()
        if cols[12].button("🗑️", key=f"{key_prefix}_del_{pos.id}", help=t("positionen.delete_tooltip")):
            _open_delete(pos.id)
            st.rerun()


st.subheader(t("positionen.tab_portfolio"))
_render_table(repo.get_portfolio(), "positionen.empty_portfolio", "pf")

st.divider()

st.subheader(t("positionen.tab_watchlist"))
_render_table(repo.get_watchlist(), "positionen.empty_watchlist", "wl")

# ------------------------------------------------------------------
# Dividends & Interest Income Overview
# ------------------------------------------------------------------

st.divider()
st.subheader("📈 Erwartete Dividenden & Ausschüttungen (Jahresprognose, brutto)")

_market_agent = get_market_agent()
_valuations = _market_agent.get_portfolio_valuation(include_watchlist=False)

# Filter to only portfolio positions with dividend data
_div_valuations = [
    v for v in _valuations
    if v.annual_dividend_eur is not None and v.annual_dividend_eur > 0
]

if _div_valuations:
    # Build table data
    _div_data = []
    for v in sorted(_div_valuations, key=lambda x: x.annual_dividend_eur or 0, reverse=True):
        _div_data.append({
            "Position": v.name,
            "Klasse": v.asset_class,
            "Yield": f"{(v.dividend_yield_pct or 0) * 100:.2f}%" if v.dividend_yield_pct else "—",
            "Jährlich (€)": f"{symbol()}{v.annual_dividend_eur:,.0f}" if v.annual_dividend_eur else "—",
        })

    import pandas as pd
    _df_div = pd.DataFrame(_div_data)
    st.dataframe(_df_div, use_container_width=True, hide_index=True)

    # Total
    _total_div = sum(v.annual_dividend_eur for v in _div_valuations if v.annual_dividend_eur)
    st.markdown(f"**Gesamtportfolio: €{_total_div:,.0f}/Jahr**")
else:
    st.info("Keine Positionen mit Dividendendaten. Klicken Sie auf 'Dividenden aktualisieren', um Daten zu laden.")

# Fetch button (always visible)
col_fetch, col_info = st.columns([1, 4])
with col_fetch:
    if st.button("🔄 Dividenden aktualisieren", use_container_width=True):
        _clear_form()
        with st.spinner("Fetching dividend data..."):
            errors = _market_agent.fetch_dividends_now()
            if errors:
                st.warning(f"Fehler bei {len(errors)} Symbolen: {', '.join(errors.keys())[:100]}")
            else:
                st.success("Dividend data updated successfully")
            st.rerun()

# Last fetch info
_div_records = get_market_repo().get_all_dividends()
if _div_records:
    _latest_fetch = max(
        (r.fetched_at for r in _div_records.values() if r.fetched_at),
        default=None
    )
    if _latest_fetch:
        with col_info:
            st.caption(f"Zuletzt aktualisiert: {_latest_fetch.strftime('%d.%m.%Y %H:%M')} UTC")

