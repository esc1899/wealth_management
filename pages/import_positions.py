"""
Import Positions — upload Excel or CSV and bulk-add positions to the portfolio.
"""

from __future__ import annotations

import io
from datetime import date

import pandas as pd
import streamlit as st

from core.asset_class_config import get_asset_class_registry
from core.i18n import t
from core.storage.models import Position
from state import get_positions_repo

st.set_page_config(page_title="Import Positions", page_icon="📥", layout="wide")
st.title(f"📥 {t('import_positions.title')}")
st.caption(t("import_positions.subtitle"))

registry = get_asset_class_registry()
positions_repo = get_positions_repo()

# ---------------------------------------------------------------------------
# Column alias mapping — normalised (lowercase, stripped) → target column name
# ---------------------------------------------------------------------------

COLUMN_ALIASES: dict[str, str] = {
    # name
    "name": "name", "bezeichnung": "name", "titel": "name", "position": "name",
    "wertpapier": "name", "security": "name",
    # ticker
    "ticker": "ticker", "symbol": "ticker", "kürzel": "ticker", "börsenk": "ticker",
    "börsenkürzel": "ticker",
    # isin
    "isin": "isin",
    # wkn
    "wkn": "wkn",
    # asset class
    "asset_class": "asset_class", "assetklasse": "asset_class", "klasse": "asset_class",
    "typ": "asset_class", "type": "asset_class", "kategorie": "asset_class",
    "category": "asset_class",
    # quantity
    "quantity": "quantity", "anzahl": "quantity", "menge": "quantity",
    "stück": "quantity", "amount": "quantity", "shares": "quantity",
    "anteile": "quantity",
    # unit
    "unit": "unit", "einheit": "unit",
    # purchase price
    "purchase_price": "purchase_price", "kaufpreis": "purchase_price",
    "kurs": "purchase_price", "preis": "purchase_price", "price": "purchase_price",
    "einstandskurs": "purchase_price", "einstandspreis": "purchase_price",
    "kurs eur": "purchase_price", "preis eur": "purchase_price",
    # purchase date
    "purchase_date": "purchase_date", "kaufdatum": "purchase_date",
    "datum": "purchase_date", "date": "purchase_date", "erwerbsdatum": "purchase_date",
    # notes
    "notes": "notes", "notizen": "notes", "anmerkungen": "notes",
    "bemerkungen": "notes", "comments": "notes",
}

TARGET_COLUMNS = [
    "name", "ticker", "isin", "wkn",
    "asset_class", "quantity", "unit",
    "purchase_price", "purchase_date", "notes",
]


def _map_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns using alias map; add missing target columns as empty."""
    renamed = {}
    for col in df.columns:
        key = col.lower().strip()
        target = COLUMN_ALIASES.get(key)
        if target and target not in renamed.values():
            renamed[col] = target
    df = df.rename(columns=renamed)
    # Keep only target columns that exist; add missing ones
    existing = [c for c in TARGET_COLUMNS if c in df.columns]
    df = df[existing]
    for col in TARGET_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[TARGET_COLUMNS]


def _parse_file(uploaded) -> pd.DataFrame | None:
    name = uploaded.name.lower()
    try:
        if name.endswith(".csv"):
            # Try common separators
            content = uploaded.read()
            for sep in [";", ",", "\t"]:
                try:
                    df = pd.read_csv(io.BytesIO(content), sep=sep, dtype=str)
                    if len(df.columns) > 1:
                        break
                except Exception:
                    continue
        else:
            df = pd.read_excel(uploaded, dtype=str)
        # Drop fully empty rows
        df = df.dropna(how="all")
        return df
    except Exception as exc:
        st.error(f"Fehler beim Lesen der Datei: {exc}")
        return None


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

uploaded = st.file_uploader(
    t("import_positions.upload_label"),
    type=["xlsx", "xls", "csv"],
    help=t("import_positions.upload_help"),
)

if uploaded is None:
    st.info(t("import_positions.no_file"))
    st.stop()

raw_df = _parse_file(uploaded)
if raw_df is None or raw_df.empty:
    st.warning(t("import_positions.no_rows"))
    st.stop()

mapped_df = _map_columns(raw_df)
detected_cols = [c for c in TARGET_COLUMNS if c in raw_df.columns or
                 any(COLUMN_ALIASES.get(rc.lower().strip()) == c for rc in raw_df.columns)]
st.caption(t("import_positions.mapping_info").format(cols=", ".join(detected_cols)))

# ---------------------------------------------------------------------------
# Preview & edit
# ---------------------------------------------------------------------------

st.subheader(t("import_positions.preview_header"))
st.caption(t("import_positions.preview_help"))

asset_class_options = registry.all_names()

edited_df = st.data_editor(
    mapped_df,
    use_container_width=True,
    hide_index=False,
    num_rows="fixed",
    column_config={
        "name": st.column_config.TextColumn(
            t("import_positions.col_name"), required=True
        ),
        "ticker": st.column_config.TextColumn(t("import_positions.col_ticker")),
        "isin": st.column_config.TextColumn(t("import_positions.col_isin")),
        "wkn": st.column_config.TextColumn(t("import_positions.col_wkn")),
        "asset_class": st.column_config.SelectboxColumn(
            t("import_positions.col_asset_class"),
            options=asset_class_options,
            required=True,
        ),
        "quantity": st.column_config.NumberColumn(
            t("import_positions.col_quantity"),
            min_value=0,
            required=True,
        ),
        "unit": st.column_config.SelectboxColumn(
            t("import_positions.col_unit"),
            options=["Stück", "Troy Oz", "g"],
        ),
        "purchase_price": st.column_config.NumberColumn(
            t("import_positions.col_purchase_price"),
            min_value=0,
            format="%.4f",
        ),
        "purchase_date": st.column_config.DateColumn(
            t("import_positions.col_purchase_date"),
        ),
        "notes": st.column_config.TextColumn(t("import_positions.col_notes")),
    },
)

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

errors: list[str] = []
warnings: list[str] = []
valid_indices: list[int] = []
today = date.today()

for idx, row in edited_df.iterrows():
    row_num = idx + 2  # 1-based + header
    row_errors: list[str] = []

    # Name
    name_val = str(row.get("name", "") or "").strip()
    if not name_val:
        row_errors.append(t("import_positions.error_name_empty").format(row=row_num))

    # Asset class
    ac_val = str(row.get("asset_class", "") or "").strip()
    if not ac_val:
        row_errors.append(t("import_positions.error_asset_class_empty").format(row=row_num))
    elif ac_val not in asset_class_options:
        row_errors.append(
            t("import_positions.error_asset_class_invalid").format(row=row_num, value=ac_val)
        )

    # Quantity
    qty_raw = row.get("quantity")
    if qty_raw is None or str(qty_raw).strip() in ("", "nan", "None"):
        row_errors.append(t("import_positions.error_quantity_missing").format(row=row_num))
    else:
        try:
            qty = float(str(qty_raw).replace(",", "."))
            if qty <= 0:
                row_errors.append(
                    t("import_positions.error_quantity_invalid").format(row=row_num)
                )
        except (ValueError, TypeError):
            row_errors.append(t("import_positions.error_quantity_invalid").format(row=row_num))

    # Purchase date — not in the future
    pd_raw = row.get("purchase_date")
    if pd_raw is not None and str(pd_raw).strip() not in ("", "nan", "None", "NaT"):
        try:
            if hasattr(pd_raw, "date"):
                pd_date = pd_raw.date()
            else:
                pd_date = date.fromisoformat(str(pd_raw)[:10])
            if pd_date > today:
                row_errors.append(t("import_positions.error_date_future").format(row=row_num))
        except (ValueError, TypeError):
            pass  # unparseable date — ignore, user can fix

    # Ticker warning (non-blocking)
    ticker_val = str(row.get("ticker", "") or "").strip()
    if not ticker_val and name_val:
        warnings.append(
            t("import_positions.warning_ticker_missing").format(row=row_num, name=name_val)
        )

    if row_errors:
        errors.extend(row_errors)
    else:
        valid_indices.append(idx)

# Show errors and warnings
if errors:
    with st.expander(t("import_positions.errors_header").format(count=len(errors)), expanded=True):
        for e in errors:
            st.error(e)

if warnings:
    with st.expander(t("import_positions.warnings_header").format(count=len(warnings))):
        for w in warnings:
            st.warning(w)

# ---------------------------------------------------------------------------
# Import button
# ---------------------------------------------------------------------------

n_valid = len(valid_indices)
can_import = n_valid > 0

if can_import:
    label = t("import_positions.import_button").format(count=n_valid)
else:
    label = t("import_positions.import_button_disabled")

if st.button(label, type="primary", disabled=not can_import):
    imported = 0
    for idx in valid_indices:
        row = edited_df.loc[idx]

        ac_val = str(row["asset_class"]).strip()
        cfg = registry.require(ac_val)

        def _str(val) -> str | None:
            s = str(val).strip() if val is not None else ""
            return s if s and s not in ("nan", "None", "NaT") else None

        def _float(val) -> float | None:
            s = _str(val)
            if s is None:
                return None
            try:
                return float(s.replace(",", "."))
            except (ValueError, TypeError):
                return None

        def _date(val) -> date | None:
            if val is None:
                return None
            if hasattr(val, "date"):
                return val.date()
            s = _str(val)
            if not s:
                return None
            try:
                return date.fromisoformat(s[:10])
            except (ValueError, TypeError):
                return None

        unit_val = _str(row.get("unit")) or cfg.default_unit

        pos = Position(
            asset_class=ac_val,
            investment_type=cfg.investment_type,
            name=_str(row["name"]),
            ticker=_str(row.get("ticker")),
            isin=_str(row.get("isin")),
            wkn=_str(row.get("wkn")),
            quantity=_float(row["quantity"]),
            unit=unit_val,
            purchase_price=_float(row.get("purchase_price")),
            purchase_date=_date(row.get("purchase_date")),
            notes=_str(row.get("notes")),
            added_date=date.today(),
            in_portfolio=True,
        )
        positions_repo.add(pos)
        imported += 1

    st.success(t("import_positions.success").format(count=imported))
    st.rerun()
