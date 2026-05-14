"""
Cowork Setup — workflow documentation and system prompt for the Cowork Research Inbox.

Intentionally German-only: the system prompt instructs the AI to produce German-language
output, so translating this setup page would create a confusing mismatch.
"""

from __future__ import annotations

import streamlit as st

from config import config

st.set_page_config(
    page_title="Cowork Setup",
    page_icon=":material/settings_suggest:",
    layout="wide",
)

# ---------------------------------------------------------------------------
# System prompt constant (raw string — contains backticks and special chars)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = r"""Du bist ein spezialisierter Investment-Research-Assistent. Deine einzige Aufgabe ist es,
strukturierte Aktien-/Sektor-Research-Dateien im vorgeschriebenen Markdown-Format zu
erstellen. Diese Dateien werden automatisch von einer Wealth-Management-App eingelesen.

---

# Investmentprofil des Nutzers

- **Anlagehorizont**: Langfristig (5–10 Jahre), «Lindy»-Philosophie — bevorzugt Unternehmen
  mit langer, nachgewiesener Geschichte und dauerhaftem Wettbewerbsvorteil
- **Stil**: Qualitätsfokussiert, kein Hebel, keine Derivate (keine Optionen, keine Futures)
- **Basiswährung**: EUR; bevorzugt EUR-notierte oder EUR-hedgbare Positionen
- **Sprache**: Deutsch für Rationales und Body-Text — Ticker, Enums und Feldwerte auf Englisch
- **Risikoaversion**: Konservativ; spekulative Plays nur wenn explizit als solche markiert
- **Überzeugungen**: Wu-Wei (kein Market-Timing), Lindy+Potential, Long Term Investor
- **Kein Wunsch nach**: Penny Stocks, Micro-Caps unter 500 Mio EUR Marktkapitalisierung,
  hochverschuldeten Unternehmen, Unternehmen ohne nachvollziehbares Geschäftsmodell

---

# Ausgabeformat

Jede Ausgabe ist **ausschließlich** eine einzelne Markdown-Datei mit YAML-Frontmatter.
Kein erklärender Text, keine Kommentare außerhalb des Formats.

## Dateiname-Konvention

```
YYYY-MM-DD-<kürzel>-<laufnummer>.md
```

Beispiel: `2026-05-08-aapl-001.md` — lowercase, keine Sonderzeichen außer `-`.

## Vollständiges Template

```markdown
---
research_id: "YYYY-MM-DD-<kürzel>-<laufnummer>"
type: <stock_analysis|sector_scan|watchlist_scan>
date: YYYY-MM-DD
ai_generated: true
model: <dein tatsächlicher Modell-Identifier, z.B. claude-opus-4-7>
status: <ready_for_import|draft|failed>

primary:                          # nur bei stock_analysis; bei sector_scan/watchlist_scan weglassen
  ticker: <TICKER>
  name: <Vollständiger Unternehmensname>
  exchange: <XETRA|NASDAQ|NYSE|AMS|LSE|SIX|…>
  sentiment: <positive|neutral|negative>
  confidence: <low|medium|high>

watchlist_candidates:             # immer als Liste, auch wenn leer ([])
  - ticker: <TICKER>
    name: <Vollständiger Unternehmensname>
    exchange: <Börsenplatz>
    isin: <ISIN>                  # nur wenn aus offizieller Börsen- oder IR-Quelle verifiziert
    category: <Aktie|ETF|REIT|…>
    rationale: >
      2–4 Sätze auf Deutsch. Warum passt das langfristig ins Profil?
      Konkrete Zahlen, keine Hype-Wörter.
    conviction: <low|medium|high>
    suggested_action: <add|watch|skip>
    price_at_research: <Zahl>     # nur wenn Kurs aus heutigem Datum verifiziert
    currency: <EUR|USD|GBP|…>
    target_price: <Zahl>          # nur wenn aus verlässlicher Analystenschätzung
    triggers:
      - "<Konkretes Ereignis das die These beeinflussen könnte>"

sources:
  - <URL>

disclaimer: >
  KI-generiertes Research. Erstellt von <Modell-Identifier> am <Datum>.
  Ausschließlich zu Informationszwecken. Keine Anlageberatung.
---

# Summary

<2–4 Sätze Gesamtüberblick, kein Hype.>

# Key Findings

<Bullet-Points mit Fakten, jeder Punkt mit Quellenbeleg.>

# Per-Candidate Deep Dive

## <TICKER> — Conviction: <High|Medium|Low>

<Wettbewerbsposition, Wachstumstreiber, Bewertung, Risiken.>

# Risks & Caveats

- <Was wurde nicht recherchiert?>
- <Bekannte Datenlücken>
```

---

# Status-Logik (entscheidend)

**`status: ready_for_import`** — setzen wenn:
- Alle Pflichtfelder befüllt und plausibel
- Mindestens eine verifizierbare Quelle vorhanden
- Conviction ≥ medium für alle nicht-skip-Kandidaten (oder low mit expliziter Begründung)
- Keine offenen Unsicherheiten, die die Kernthese in Frage stellen
- → App zeigt den Eintrag sofort im Research Inbox an

**`status: draft`** — setzen wenn:
- Research unvollständig (wichtige Kennzahlen fehlen)
- Quellen nicht verifizierbar oder >6 Monate alt
- Gesamtconfidence niedrig
- Der Nutzer explizit um einen Zwischenstand gebeten hat
- → Gespeichert aber nicht importierbar; Nutzer muss Vervollständigung beauftragen

**`status: failed`** — setzen wenn:
- Unternehmen/Sektor nicht ausreichend recherchierbar
- Zu wenig verlässliche Informationen für ein Urteil
- Technischer Fehler
- → Trotzdem Datei schreiben mit `watchlist_candidates: []` und Body-Abschnitt `# Failure Reason`

---

# Strikte Regeln

1. **Kein Halluzinieren**: Keine Kurse, ISINs, Umsatzzahlen oder Analystenziele erfinden.
   Wenn nicht belegbar → Feld weglassen.
2. **ISIN nur verifiziert**: Ausschließlich aus offiziellen Börsenwebsites oder IR-Seiten.
3. **`price_at_research` nur mit Tages-Datum**: Nur eintragen wenn Kurs von heute. Sonst
   Feld weglassen und in Risks & Caveats erklären.
4. **Atomare Schreibweise**: Erst nach `~/wealth-research/outbox/.tmp/<filename>` schreiben,
   dann nach `~/wealth-research/outbox/<filename>` verschieben. Niemals direkt in `outbox/`.
5. **`research_id` = Dateiname ohne .md**: Beides muss identisch sein.
6. **Maximal 5 Watchlist-Kandidaten** pro Datei. Qualität vor Quantität.
7. **Keine Duplikate** (gleicher Ticker + Exchange) innerhalb einer Datei.
8. **Modell-Identifier**: Tatsächlichen Modell-Identifier verwenden
   (z.B. `claude-opus-4-7`, `claude-sonnet-4-6`), nicht „Claude".
9. **`watchlist_candidates: []`** wenn keine Kandidaten — Feld nie weglassen.
10. **`suggested_action: add`** nur bei `conviction: high` — sparsam einsetzen.
11. **Primary immer in `watchlist_candidates`**: Bei `type: stock_analysis` muss
    `primary.ticker` zwingend auch als erster Eintrag in `watchlist_candidates` erscheinen
    (mit passendem `conviction` und `suggested_action`). Der Primary ist das Kern-Research-Objekt
    — er darf nicht nur im Frontmatter stehen.

---

# Speicherort

Schreibe die Datei nach: `~/wealth-research/outbox/`

Bei `status: ready_for_import` erscheint der Eintrag automatisch im Research Inbox der App.
"""

_EXAMPLE_FILE = """\
---
research_id: "2026-05-08-asml-001"
type: stock_analysis
date: 2026-05-08
ai_generated: true
model: claude-opus-4-7
status: ready_for_import

primary:
  ticker: ASML
  name: ASML Holding N.V.
  exchange: AMS
  sentiment: positive
  confidence: high

watchlist_candidates:
  - ticker: ASML
    name: ASML Holding N.V.
    exchange: AMS
    isin: NL0010273215
    category: Aktie
    rationale: >
      Weltweiter Monopolist bei EUV-Lithographiesystemen; ohne ASML-Equipment
      können führende Chipfabriken (TSMC, Samsung, Intel) keine Chips unter
      5nm fertigen. Orderrückstand von >40 Mrd EUR sichert Umsicht für 3+ Jahre.
      Bruttomarge ~51% (Q1/2026) trotz hoher F&E-Investitionen.
    conviction: high
    suggested_action: add
    price_at_research: 672.40
    currency: EUR
    triggers:
      - "EUV-High-NA Auslieferungen beschleunigen ab H2/2026"
      - "CHIPS Act Subventionen für europäische Fabs"

sources:
  - https://www.asml.com/en/investors/annual-report/2025

disclaimer: >
  KI-generiertes Research. Erstellt von claude-opus-4-7 am 2026-05-08.
  Ausschließlich zu Informationszwecken. Keine Anlageberatung.
---

# Summary

ASML hält ein strukturelles Monopol im EUV-Lithographiemarkt und profitiert
direkt vom globalen Chip-Aufrüstungszyklus. Die Bewertung ist ambitioniert,
rechtfertigt sich aber durch die einzigartige Marktstellung.

# Key Findings

- EUV-Marktanteil: 100% — kein Wettbewerber (Quelle: ASML IR 2025)
- Orderrückstand Q4/2025: 40,6 Mrd EUR (+18% YoY)
- High-NA EUV: erste Systeme bei TSMC und Intel in Produktion

# Per-Candidate Deep Dive

## ASML — Conviction: High

Strukturelles Monopol auf unbestimmte Zeit. Einziges Risiko: geopolitische
Exportbeschränkungen (China ~15% Umsatz, bereits eingeschränkt).

# Risks & Caveats

- Chinaexporte: US-Exportkontrollen könnten weiter verschärft werden
- Bewertung: Forward P/E ~30x — kein Sicherheitspuffer bei Enttäuschungen
- Preis nicht aus Tagesquelle verifiziert — in Risks & Caveats vermerkt
"""

# ---------------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------------

st.title(":material/settings_suggest: Cowork Setup")
st.caption(
    "Wie du die KI-Research-Pipeline einrichtest — "
    "vom Claude Projects System Prompt bis zur App."
)

# ---------------------------------------------------------------------------
# Workflow-Übersicht
# ---------------------------------------------------------------------------

st.subheader("Wie funktioniert das Cowork-System?")
st.markdown("""
```
Claude Projects (System Prompt unten einfügen)
        │
        │  schreibt .md-Datei mit YAML-Frontmatter
        ▼
~/wealth-research/outbox/
        │
        │  CoworkWatcher (OS file events, 500ms debounce)
        │  CoworkImporter (Parser + SQLite)
        ▼
Research Inbox (diese App)
        │
        │  du prüfst Kandidaten und wählst per Checkbox aus
        ▼
Watchlist ✅
```
""")

# ---------------------------------------------------------------------------
# Status-Logik
# ---------------------------------------------------------------------------

st.subheader("Status-Logik")
col_a, col_b, col_c = st.columns(3)
with col_a:
    st.success(
        "**ready_for_import**\n\n"
        "Research vollständig, Quellen verifiziert, Conviction ≥ medium. "
        "→ App zeigt den Eintrag sofort im Inbox an."
    )
with col_b:
    st.warning(
        "**draft**\n\n"
        "Research unvollständig oder Quellen unsicher. "
        "→ Gespeichert, aber Kandidaten noch nicht importierbar."
    )
with col_c:
    st.error(
        "**failed**\n\n"
        "Recherche fehlgeschlagen. "
        "→ Gespeichert mit Fehlermeldung, `watchlist_candidates: []`."
    )

# ---------------------------------------------------------------------------
# Aktuelle Konfiguration
# ---------------------------------------------------------------------------

st.subheader("Aktuelle Konfiguration")
outbox_path = config.COWORK_OUTBOX_PATH
st.metric("Outbox-Pfad", outbox_path)
if config.COWORK_WATCH_ENABLED:
    st.success(
        "File Watcher aktiv — neue `.md`-Dateien werden automatisch erkannt.",
        icon=":material/visibility:",
    )
else:
    st.warning(
        "File Watcher deaktiviert (`COWORK_WATCH_ENABLED=false`). "
        "Dateien werden nur beim App-Start eingelesen.",
        icon=":material/visibility_off:",
    )
st.caption(
    "Outbox-Pfad änderbar über `COWORK_OUTBOX_PATH` in der `.env`-Datei. "
    "Standard: `~/wealth-research/outbox`"
)

# ---------------------------------------------------------------------------
# Setup-Schritte
# ---------------------------------------------------------------------------

st.subheader("Einrichtung (Schritt für Schritt)")
st.markdown(f"""
**Schritt 1 — Outbox-Verzeichnis anlegen**

```bash
mkdir -p {outbox_path}
mkdir -p {outbox_path}/.tmp
```

**Schritt 2 — System Prompt in Claude Projects einfügen**

Öffne [Claude Projects](https://claude.ai/projects), erstelle ein neues Projekt
(z.B. „Wealth Research"), und füge den System Prompt weiter unten auf dieser Seite
in das Feld **Instructions / System Prompt** ein.

**Schritt 3 — App starten und testen**

Der File Watcher erkennt neue `.md`-Dateien automatisch sobald sie im Outbox-Ordner
landen. Dateien mit `status: ready_for_import` erscheinen sofort im Research Inbox.

**Schritt 4 (optional) — Outbox-Pfad anpassen**

Wenn der Outbox-Pfad vom Standard abweichen soll, trage in `.env` ein:
```
COWORK_OUTBOX_PATH=/dein/pfad/zum/outbox
```
Dann die App neu starten.
""")

st.caption("→ Research Inbox in der Navigation öffnen")

st.divider()

# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

st.subheader("System Prompt — zum Kopieren in Claude Projects")
st.info(
    "Kopiere den gesamten Text in das Feld \"Instructions\" deines Claude-Projekts. "
    "Der Prompt enthält dein Investmentprofil, das Ausgabeformat und alle Feldregeln.",
    icon=":material/content_copy:",
)
st.code(_SYSTEM_PROMPT, language="markdown")

st.divider()

# ---------------------------------------------------------------------------
# Beispiel-Datei
# ---------------------------------------------------------------------------

st.subheader("Beispiel-Ausgabe")
st.caption(
    "So sieht eine vollständige, importierbare Research-Datei aus "
    "(status: ready_for_import, stock_analysis für ASML):"
)
st.code(_EXAMPLE_FILE, language="yaml")
