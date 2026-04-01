# Backlog

Personal planning overview. User feedback and bug reports: [GitHub Issues](https://github.com/esc1899/wealth_management/issues)

## Legend
- `[P1]` High / `[P2]` Medium / `[P3]` Low
- `[BUG]` Bug / `[FEAT]` Feature / `[IMPR]` Improvement

---

## In Progress

*(empty)*

---

## Planned

### Bugs

#### [P1] [BUG] Rebalance crashes without error message
The Rebalance page silently crashes — no user-visible error, just a blank result or spinner hang.
- Wrap `agent.analyze()` call in `pages/rebalance_chat.py` in try/except
- Display a user-friendly `st.error()` with the exception message
- Root cause likely: Ollama not running, or model not pulled

### Improvements

#### [P1] [IMPR] Rebalancing: Geld und Immobilien separat behandeln
Börsengehandelte Positionen (Aktien, ETFs, Krypto) von nicht-handelbaren Positionen trennen:
- Geldanlagen (Festgeld, Bargeld): illiquide / feste Laufzeit
- Immobilien/Grundstücke: sehr illiquide

Gewünschtes Verhalten:
- Rebalance-Snapshot zeigt Geld + Immobilien separat als "Nicht-handelbares Vermögen"
- Agent bekommt Kontext: "Diese Positionen stehen nicht zum Umschichten zur Verfügung"
- Empfehlungen nur für handelbaren Portfolio-Teil

Umsetzung: `_build_portfolio_context()` in `agents/rebalance_agent.py` aufteilen; Skill-Prompt anpassen.

#### [P1] [IMPR] Invest/Rebalance: Watchlist-Kandidaten einbeziehen
Watchlist-Positionen mit Story als "Kaufkandidaten" im Rebalance-Kontext sichtbar machen — ohne Mengen/Preise aus dem Portfolio zu exponieren.

Umsetzung: `_build_portfolio_context()` um optionale Watchlist-Sektion erweitern.

#### [P2] [IMPR] Auto-fetch market data on position creation
When a new position is added, automatically fetch:
1. Historical price for the purchase date (accurate cost basis)
2. Current price for latest trading day

Uses existing `MarketDataFetcher`. Graceful fallback if ticker invalid. No UI blocking.

→ [GitHub Issue #6](https://github.com/esc1899/wealth_management/issues/6)

#### [P1] [IMPR] Input validation when creating positions
Validate agent-extracted values before saving to DB:
- Quantity/price: must be positive
- Purchase date: not in the future, valid format
- Asset class: must exist in `asset_classes.yaml`
- Ticker: basic format check; optionally verify via yfinance

→ [GitHub Issue #7](https://github.com/esc1899/wealth_management/issues/7)

#### [P2] [IMPR] Portfolio Chat: Skill + proactive clarification + save confirmation
Three linked improvements to make the LLM-based entry reliable:
1. **Skill for Portfolio Chat** — example skill that tells the LLM which fields matter
2. **Plausibility check before saving** — validates extracted values, asks for clarification if missing
3. **Explicit save confirmation in chat** — agent replies with saved values after tool call

---

## Ideas / Later

#### [P3] [FEAT] Rebalance: planned deposits / withdrawals input
Allow users to enter an expected cash in- or outflow before running the analysis.

#### [P3] [FEAT] Empfehlungsquelle auswerten
`recommendation_source` ist im Modell vorhanden. Statistik-Seite: "Quelle → Ø G/V %" über alle empfohlenen Positionen.

#### [P3] [FEAT] Währungsflexibilisierung
`BASE_CURRENCY` Config-Eintrag (default EUR) für CH/GB/US-Nutzer.

---

## Done

#### [P1] [BUG] DB migration: OperationalError on existing DBs (in_watchlist index)
`CREATE INDEX idx_positions_in_watchlist` war in `init_db` — schlägt fehl wenn `positions`-Tabelle schon ohne die Spalte existiert. Fix: Index in `migrate_db` verschoben (nach ALTER TABLE).

#### [P1] [BUG] Duplicate key error when position is in portfolio AND watchlist
`_render_table` verwendete `det_{pos.id}` als Button-Key — bei gleicher Position in beiden Listen doppelt. Fix: `key_prefix` Parameter (`pf_` / `wl_`).

#### [P2] [BUG] Storychecker: nur Watchlist-Positionen prüfbar
Storychecker hat nur `get_watchlist()` geladen — Portfolio-Positionen mit Story wurden nicht angezeigt. Fix: `get_all()`.

#### [P2] [BUG] Story-Skill-Selector immer disabled
`disabled=not bool(form_story)` innerhalb `st.form` reagiert nicht auf live Eingabe. Fix: `disabled` entfernt.

#### [P2] [BUG] Dashboard-Summe falsch (Geld-Anlagen)
Festgeld + Bargeld hatten `manual_valuation: false` → kein Schätzwert-Dialog → `current_value = None`. Fix: `manual_valuation: true` + `estimated_value` in extra_fields. Bargeld mit `unit=€` nutzt `quantity` direkt als Wert.

#### [P2] [BUG] Löschen von Watchlist springt auf Portfolio
Tab-Layout hat beim Rerun die Tab-Selektion verloren. Fix: Tabs entfernt — Portfolio + Watchlist jetzt untereinander mit Subheadern.

#### [P2] [BUG] Dezimalzahlen als Punkt statt Komma
`f"{x:,.2f}"` → englisches Format. Fix: `_fmtnum()` Hilfsfunktion mit deutschem Format (`1.234,56`).

#### [P2] [IMPR] Empfehlung / recommendation_source inkonsistent
`recommendation_source` war im Modell, aber nicht im Formular sichtbar. Fix: "Empfohlen von" Freitextfeld im Formular + Detail-Dialog.

#### [P2] [IMPR] Name nicht aus Tickersuche vorausgefüllt
FIGI Apply setzte nur `_pos_ticker`, nicht `_pos_name`. Fix: `chosen["name"]` → `_pos_name` wenn noch leer.

#### [P2] [IMPR] Kein Feedback nach Speichern
`st.success()` vor `st.rerun()` wird nicht angezeigt. Fix: `_pos_just_saved` Session-State-Flag → Erfolgsanzeige oben nach Rerun.

#### [P2] [IMPR] Alphabetisch sortieren in Positions-Tabellen
`_render_table` sortiert jetzt nach `name.lower()`.

#### [P2] [IMPR] Streamlit Deploy-Button ausblenden
`.streamlit/config.toml` mit `toolbarMode = "minimal"`.

#### [P2] [FEAT] System Health / Setup Checks
`core/health.py` mit statischen Checks + Ollama-Connectivity-Check.

#### [P1] [FEAT] Investment Search Agent (Cloud ☁️)
`SearchAgent` mit `SearchRepository` + session-based chat.

#### [P1] [FEAT] Invest & Rebalance Agent (Private 🔒)
`RebalanceAgent` using local Ollama.

#### [P2] [IMPR] Seed example skills in all environments
`config/default_skills.yaml` covers all areas.

#### [P1] [FEAT] Multi-environment setup & proxy LLM support
`ENV_PROFILE=work`, `ANTHROPIC_BASE_URL` für Corporate Proxy.

#### [P2] [FEAT] News Agent (Cloud ☁️)
`NewsAgent` — stateless, one-shot digest per run.

#### [P1] [IMPR] Rename "Rebalance" to "Invest / Rebalance"

#### [P2] [IMPR] News Digest: expandable detail per position

#### [P2] [IMPR] News Digest: session history
