"""Was alle Teile der Suche gleich zeigen: Kopf des Laufs, Vorschläge, Bericht mit Rückfrage."""

from typing import Callable, Optional

import streamlit as st

from core.i18n import t


def kopf(wann, *teile: Optional[str]) -> None:
    """Eine Zeile über dem Lauf: wann, mit welchem Skill, wonach."""
    zeile = " · ".join([wann.strftime("%d.%m.%Y %H:%M")] + [x for x in teile if x])
    st.markdown(f"**{t('suche.letzter_lauf')}**")
    st.caption(zeile)


def vorschlaege(proposals: list[dict], key: str, uebernehmen: Callable[[dict], object],
                text: str = "notes") -> bool:
    """Die Vorschläge eines Laufs zum Ankreuzen; ``True``, wenn welche übernommen wurden.
    Bis die Kandidaten kommen (BACKLOG.md, "Suche"), ist das der Weg auf die Watchlist."""
    if not proposals:
        return False
    st.markdown(f"**{t('suche.vorschlaege')}**")
    for i, p in enumerate(proposals):
        st.checkbox(f"**{p['name']}** ({p['ticker']}) · {p['asset_class']}", key=f"{key}_{i}")
        if p.get(text):
            st.caption(p[text][:200])
    if not st.button(t("suche.auf_die_watchlist"), type="primary", key=f"{key}_uebernehmen"):
        return False
    gewaehlt = [p for i, p in enumerate(proposals) if st.session_state.get(f"{key}_{i}", False)]
    if not gewaehlt:
        st.info(t("suche.keiner_gewaehlt"))
        return False
    for p in gewaehlt:
        try:
            uebernehmen(p)
        except Exception as exc:
            st.error(f"{p['name']}: {exc}")
    st.success(t("suche.uebernommen").format(n=len(gewaehlt)), icon=":material/bookmark_added:")
    return True
