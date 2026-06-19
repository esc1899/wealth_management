# Backlog

Personal planning overview. User feedback and bug reports: [GitHub Issues](https://github.com/esc1899/wealth_management/issues)

> 📦 Abgeschlossene Einträge ausgelagert → [BACKLOG_ARCHIVE.md](BACKLOG_ARCHIVE.md)

## Legend
- `[P1]` High / `[P2]` Medium / `[P3]` Low
- `[BUG]` Bug / `[FEAT]` Feature / `[IMPR]` Improvement / `[DEBT]` Technical Debt

---

## In Progress

(None)

---

## Bekannte Probleme (nicht dringend)

| ID | Entdeckt | Beschreibung |
|---|---|---|
| NOTE-1 | 2026-06-06 | ~~**Tavily Monats-Limit erschöpft**~~ — Plan-Limit erhöht (2026-06-07). Verbrauch zusätzlich optimiert: search_depth=basic (alle außer FA), client-side max_uses-Enforcement, fehlende Limits nachgerüstet, NewsAgent-Formel gekappt. ✅ ERLEDIGT |
| NOTE-2 | 2026-06-06 | **SCANFL delisted/nicht gefunden** — yfinance liefert 404 für Symbol SCANFL. Position prüfen: Ticker noch aktuell? Ggf. aus Portfolio/Watchlist entfernen oder Ticker korrigieren. |

---

## Planned

### Features

| ID | Priority | Type | Description | Status | Session |
|---|---|---|---|---|---|
| FEAT-33 | P3 | [FEAT] Cowork Outbox — Rückkanal | ~~Ursprünglicher Ansatz (file-based) obsolet.~~ **Ersetzt durch FEAT-50 + FEAT-51.** | ↗ FEAT-50/51 | |
| FEAT-62 | P3 | [FEAT] Verdict Hindsight v3 — on-demand KI-Deutung | **Kontext (2026-06-16):** v1/v2 sind deterministisch + statischer Methodik-Expander (stabile Caveats: Momentum/Horizont-Bias, Linsen, Autokorrelation, Survivorship). Offen bleibt nur die **laufspezifische** Deutung („in diesem Lauf sticht X heraus") — die rechtfertigt ein LLM, lohnt aber erst, wenn die **3M/6M-Spalten gefüllt** sind. **Terminiert: ~September 2026** (älteste April-Urteile bei +6M). **Design-Constraints (kritisch):** (1) **Privacy** — LLM sieht **nur den aggregierten Report** (Agent × Verdict × Horizont → Median/n, keine Ticker, keine Einzelpositionen/Scope-Zuordnung). So aggregiert public-safe → darf Cloud sein; auf Rohdaten müsste es Ollama sein. FEAT-60-Guard muss den neuen Agent klassifizieren. (2) **Anti-Overclaim** — Systemprompt nennt n explizit, verbietet Behauptungen bei kleinem/autokorreliertem n, hält „Tagebuch, keine Trefferquote"-Rahmung. (3) **on-demand Button**, kein Auto-Run (Kosten + die deterministische Rahmung soll primär bleiben). (4) Datums-/Reife-Kontext (welche Horizonte reif) muss in den Prompt. | 🔲 TODO | |
| FEAT-68 | P2 | [FEAT] Accumulation Indicator pro Position (Phase B von FEAT-67) | **Kontext (2026-06-19):** Der Accumulation Score als **deterministischer Indikator pro Position** über **Portfolio UND Watchlist** — präzisiert den vagen „Score auf der Dividenden-Seite" aus FEAT-67. **Bewusst kein LLM-Agent:** alle Inputs sind Zahlen/Codes → reine `core/`-Funktion (wie `composition_drift`/`macro_context`), kein Batch-Job, keine Token-Kosten, läuft sofort auf allen Positionen (= Screening), kein Privacy-/Injection-Vektor, braucht **keine** FEAT-60-Bucket-Klassifikation (kein Agent; sieht Stückzahlen, sendet nichts — 🔢-Logik). **Eriks Zerlegung (ex-ante vs ex-post):** **(B1) Akkumulations-*Erwartung* — JETZT baubar, keine neue Datenquelle:** Engine = aktuelle Rendite (`dividend_data.yield_pct` / Valuations) gegated durch die bereits gespeicherten **LLM-Verdicts** als Qualitäts-/Survival-Proxy (Storychecker = These intakt?, FA = Bewertung/Qualität, CG = Gap, CA = Watchlist-Qualität) aus `position_analyses`. Der Indikator *liest* nur Verdict-Codes + Rendite, ruft selbst kein LLM → bleibt deterministisch. **(B2) Akkumulations-*Überprüfung* — reift mit der Historie:** hat die Ratsche real gegriffen? = realisierter Anteilszuwachs + Forward-Income-Wachstum (Phase-A-Funktionen `share_count_series`/`portfolio_income_series`) + DGR aus `ticker.dividends` + optionale yfinance-Fundamentals (FCF-Payout, ROIC, Leverage via bereits genutztem `ticker.info`). Das ist der gemessene **Thesis-Drift-Detektor**. **Score = B1 × B2** (Überprüfung zeigt „baut sich auf", bis genug Snapshots da sind → graceful degradation). **Transparenz (Designprinzip):** zwei sichtbare Achsen, jede Komponente mit Rohwert + Ampel + Schwelle, multiplikative Gates ⇒ bindende Komponente immer benennbar („Was bremst?"); fehlende Felder = „n/a", Score nennt die Lücke. **Trap-Detektor:** hohe Rendite + schwaches Survival-Verdict = `fallen_verdacht` statt „billig". **Andock-Punkte (alle vorhanden):** neue Spalte in Portfolio-Checker- + Watchlist-Cockpit-Status-Matrix (`fmt_verdict_matrix` + neuer `VERDICT_CONFIGS`-Eintrag in `core/ui/verdicts.py`), Karte im Position Dashboard (FEAT-25) neben SC/CG/FA, sortierbar = Watchlist-Entry-Screen. Verdict-Codes deutsch: `akkumulieren`/`halten`/`prüfen`/`fallen_verdacht`/`ungeeignet`. **Arbeitsteilung:** LLM-Checker = *qualitatives* Survival-Narrativ, dieser Indikator = *quantitative* Income-Mathematik — nebeneinander in derselben Matrix; löst den früher offenen „Survival-Probability"-Soft-Spot. **Reihenfolge:** B1 zuerst (sofortiger Nutzen), B2 inkrementell. Datenrealität beachten: yfinance-Fundamentals lückenhaft → B2-Fundamentalteil optional/degradierend. **B1 umgesetzt (2026-06-19):** `core/accumulation.py` (pure, deterministisch) — `compute_accumulation(yield, story, fa)` mit Bänder (Rendite 🟢≥2.5%/🟡≥1.2%/🔴) + Verdict-Regel (akkumulieren/halten/prüfen/fallen_verdacht/ungeeignet) + transparenter Komponenten-Breakdown + `binding` („Was bremst?"); `accumulation_for_position` als Page-Helper. `VERDICT_CONFIGS["accumulation"]` + `accumulation_matrix_cell` in `core/ui/verdicts.py`. Neue Spalte in Portfolio-Checker- (`portfolio_story.py`) + Watchlist-Cockpit-Matrix (`watchlist_checker.py`); „📈 Akkumulation"-Sektion mit Badge + Komponententabelle + binding-Caption im Position Dashboard. i18n de/en. 24 neue Tests (jeder Verdict-Pfad + Bänder-Grenzen + graceful None), AppTest-Render der 3 Seiten clean. **Bugfix (gleicher Tag, vom User gefunden):** Rendite wurde roh aus `dividend_data` gelesen (yield_pct dort oft None, z.B. ALV.DE → „—" rot trotz 4,5 % Dividende). Quelle auf die Valuation-Schicht umgestellt (`get_portfolio_valuation().dividend_yield_pct`, mit Override + Cross-Currency); `accumulation_for_position` nimmt jetzt `yield_map` statt `div_records`. ALV.DE → 4,5 % 🟢 / akkumulieren. 1231 grün. **B2 (Überprüfung) bleibt offen.** | 🟡 B1 DONE | 2026-06-19 |
| FEAT-69 | P2 | [FEAT] Ticker beim Anlegen einer Watchlist-Position erfassen + validieren | **Kontext (2026-06-19):** Beim Accumulation-Yield-Debugging fielen mehrere Positionen ohne Markt-/Dividendendaten auf, weil ihr **Ticker fehlt oder unvollständig** ist (kein Börsensuffix → yfinance-404): `FMG` (statt `FMG.AX`), `4063`/`6861` (japanische Titel ohne `.T`), `KMAR.OL`. Ohne validen Ticker liefert yfinance weder Kurs noch Dividende → die Position ist in jeder datengetriebenen Auswertung blind (Yield „—", kein Snapshot-Beitrag, kein TagesP&L). **Root cause:** der Watchlist-Anlage-Flow erzwingt/prüft beim Anlegen keinen funktionierenden Ticker. **Idee:** Im Add-Formular (Positionen-Seite + Cowork-Inbox-Import) Ticker als Feld führen und beim Speichern gegen yfinance gegenprüfen (1 Light-Fetch: existiert ein Kurs?) — bei 404 Warnung + Vorschlag (Suffix-Heuristik `.AX`/`.T`/`.OL`/…), aber nicht hart blockieren (manuelle Assets wie Konten/Immobilien haben bewusst keinen Ticker → asset_class-abhängig). **Verwandt:** NOTE-2 (SCANFL delisted), FEAT-68 (Indikator braucht Yield). **Aufwand:** klein–mittel; berührt Add-Form-Validierung + evtl. eine `validate_ticker`-Hilfsfunktion (yfinance fast_info). | 🔲 TODO | |
| FEAT-71 | P3 | [FEAT] Accumulation Indicator über Dividenden hinaus (Total Shareholder Yield) | **Kontext (2026-06-19):** Nach FEAT-68 + Umbenennung misst der Indikator bewusst nur *Dividenden*-Akkumulation; Nicht-Dividenden-Compounder (Amazon, viele US-Tech) bekommen „nicht anwendbar". Sie „akkumulieren" aber sehr wohl — über Aktienrückkäufe + Reinvestition zu hohem ROIC. **Idee:** Engine um **Buyback-Yield** (Netto-Reduktion der Aktienzahl) + optional Reinvestitions-/ROIC-Komponente erweitern → Total Shareholder Yield, damit auch buyback-getriebene Compounder fair bewertet werden. **Aufwand:** braucht Fundamentaldaten (Shares-Outstanding-Historie/Buybacks, ROIC) — gleiche Datenquelle wie FEAT-68 B2, daher B2-Scale, P3. **Verwandt:** FEAT-67/68 (Indikator), FEAT-70 (Ground-Truth-Daten). | 🔲 TODO | |

### Technical Debt

| ID | Priority | Description | Notes |
|---|---|---|---|
| DEBT-8 | P3 | Document `migrate_db()` inline — add comments explaining the dual init+migrate pattern | Low risk, cosmetic |
| DEBT-13 | P3 | Tighten requirements.txt version bounds | Low urgency, no known conflicts |

---
