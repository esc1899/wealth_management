"""Ontologie (22.10.2026, Erik): das Schema als Bild, unter Einstellungen. Nur fuer Erik, nicht
fuer Lotsee.

Nicht die Daten, sondern wie sie gebaut sind: je Art von Ding ein Kasten, je Beziehung ein
Pfeil, die Regeln der Formen am Kasten, FIBO gestrichelt daneben. Erst ein Satz, dann das Bild;
die Privacy-Grenze und die Regeln im Wortlaut in Klappern. Alles aus den Dateien unter
`ontologie/`, gelesen in `ontologie/bild.py`, gezeichnet in `core/ui/ontologie_bild.py`. Kein
Sprachmodell und keine Datenbank: Ob Code und Daten die Regeln erfuellen, prueft
`tests/integration/test_ontologie.py`, nicht diese Seite.
"""

import streamlit as st

from core.i18n import current_language, t

st.set_page_config(page_title="Ontologie", page_icon="🧭", layout="wide")
st.title(f"🧭 {t('ontologie.title')}")

try:
    from core.ui import ontologie_bild
    from ontologie import bild

    lang = current_language()
    d = bild.schema(lang=lang)
except ImportError as fehler:
    st.markdown(t("ontologie.fehlt").format(paket=fehler.name))
    st.stop()

st.markdown(d["satz"])
st.caption(t("ontologie.lesehilfe"))
st.iframe(ontologie_bild.html(d), height=780)

with st.expander(t("ontologie.grenze_titel")):
    st.markdown(t("ontologie.grenze_satz"))
    o = bild.ontologie()
    for stufe in bild.felder_je_stufe(o, lang):
        st.markdown(f"**{stufe['stufe']}** -- {stufe['erklaerung']}  \n" + ", ".join(stufe["felder"]))
    st.markdown(f"**{t('ontologie.wege_titel')}**")
    for ort in bild.wege_je_ort(o, lang):
        zeilen = [w["name"] + (f" -- {w['ausnahme']}" if w["ausnahme"] else "") for w in ort["wege"]]
        st.markdown(f"*{ort['ort']}* -- {ort['erklaerung']}  \n" + "  \n".join(zeilen))

with st.expander(t("ontologie.regeln_titel")):
    for k in d["knoten"]:
        if k["meldungen"]:
            st.markdown(f"**{k['name']}**  \n" + "  \n".join(k["meldungen"]))
    st.caption(t("ontologie.regeln_fussnote"))
