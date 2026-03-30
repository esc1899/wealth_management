"""
OpenFIGI ticker lookup — maps ISIN or WKN to Yahoo Finance ticker symbols.
No API key required for basic usage.
"""

from __future__ import annotations

import requests

# exchCode → human-readable exchange name
RELEVANT_EXCH: dict[str, str] = {
    "UN": "NYSE", "UW": "NASDAQ", "UA": "AMEX", "UR": "NYSE Arca", "US": "US",
    "GY": "Xetra", "GF": "Frankfurt", "AV": "Wien",
    "SW": "SIX Swiss", "FP": "Euronext Paris", "LN": "London",
    "NA": "Euronext Amsterdam", "BB": "Euronext Brüssel",
    "SM": "Madrid", "IM": "Borsa Italiana",
    "DC": "Kopenhagen", "HE": "Helsinki", "NO": "Oslo", "SS": "Stockholm",
    "AU": "ASX", "HK": "Hongkong", "JP": "Tokyo",
}

# exchCode → Yahoo Finance ticker suffix
EXCH_SUFFIX: dict[str, str] = {
    "GY": ".DE", "GF": ".F",  "SW": ".SW", "FP": ".PA", "LN": ".L",
    "NA": ".AS", "BB": ".BR", "SM": ".MC", "IM": ".MI", "AV": ".VI",
    "DC": ".CO", "HE": ".HE", "NO": ".OL", "SS": ".ST",
    "AU": ".AX", "HK": ".HK", "JP": ".T",
}

# securityType fragments to exclude (derivatives, structured products)
EXCLUDE_TYPE_FRAGMENTS: set[str] = {
    "Option", "Warrant", "Right", "Structured", "Index",
    "Convertible", "Certificate", "Future",
}


def openfigi_lookup(id_type: str, id_value: str) -> list[dict]:
    """
    Call OpenFIGI v3 mapping API.

    id_type: "ID_ISIN" or "ID_WERTPAPIER" (WKN)
    id_value: the identifier string

    Returns a filtered list of result dicts, deduplicated by exchCode.
    Returns [] on error or no results.
    """
    try:
        resp = requests.post(
            "https://api.openfigi.com/v3/mapping",
            json=[{"idType": id_type, "idValue": id_value.strip().upper()}],
            headers={"Content-Type": "application/json"},
            timeout=6,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        if not data or "data" not in data[0]:
            return []
        results = data[0]["data"]
    except Exception:
        return []

    seen_exch: set[str] = set()
    filtered: list[dict] = []
    for r in results:
        exch = r.get("exchCode", "")
        market = r.get("marketSector", "")
        sec_type = r.get("securityType", "")
        if market != "Equity":
            continue
        if exch not in RELEVANT_EXCH:
            continue
        if any(frag in sec_type for frag in EXCLUDE_TYPE_FRAGMENTS):
            continue
        if exch in seen_exch:
            continue
        seen_exch.add(exch)
        filtered.append(r)

    return filtered


def to_yahoo_ticker(result: dict) -> str:
    """Build Yahoo Finance ticker from an OpenFIGI result dict."""
    ticker = result.get("ticker", "")
    suffix = EXCH_SUFFIX.get(result.get("exchCode", ""), "")
    return f"{ticker}{suffix}" if ticker else ""
