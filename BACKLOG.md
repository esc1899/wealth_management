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

---

### Portfolio Story

#### [P2] [IMPR] Portfolio Story: Erweiterte Stabilitäts-Kriterien
Stability-Check könnte zusätzliche Kriterien einbeziehen:

1. **Diversifikation:** Position-Anzahl, Top-3-Klumpen-Risiko (Konzentration)
   - Warnung: Zu wenige Positionen → Klumpenrisiko
   - Analyse: Top-3 Positionen sollten <60% des Portfolios nicht übersteigen

2. **Sektor-Konzentration:** Branchenverteilung analysieren
   - "Zu viel Tech/Finanzsektor/Einzelbranchen?"
   - Vergleich: Ist Sektor-Gewichtung vs. Portfolio-Ziel angemessen?

3. **Währungsrisiko (FX-Exposure):** Non-EUR-Anteil
   - USD, CHF, GBP, etc. — Volatilität durch Wechselkurse
   - Zielzonen je nach Risikotoleranz/Zeithorizont

4. **Zeitlicher Horizont vs. Volatilität:** Je näher target_year, desto defensiver
   - 2025: >50% Aktien → Warnung
   - 2040+: Aktienanteil defensiv für Endjahrzehnt anpassen

5. **Notfall-Reserve:** Bargeld für Emergencies
   - Sollte 3–6 Monate Lebenshaltungskosten abdecken
   - Zeigt Liquiditäts-Puffer für Krisen auf

**Aktuell implementiert:**
- Josef's Rule: Aktien/Renten/Rohstoffe Gewichtung (1/3 + 1/3 + 1/3 Richtlinie)
- Inflationsschutz: Rohstoffe + Immobilien als Hedge
- Liquidität: Renten + Dividenden (jährliche Cashflows)
- Dividendenbewertung: Absolute Dividenden vs. Ziel/Priorität

**Zukünftig (gute Kandidaten für Phase 2):**
- Top-3-Konzentration automatisch analysieren
- Sektor-Mapping und Häufung identifizieren
- FX-Exposure summieren
- Bargeld-Adäquatheit bewerten

#### [P2] [FEAT] Portfolio Story: Per-Position Story-Fit Assessment ✅ UMGESETZT
`PortfolioStoryPositionFit` Modell mit fit_verdict (stärkt/schwächt/neutral) und fit_summary. 
Batch LLM-Call analysiert alle Positionen in einem Durchgang gegen Portfolio-These. 
Integration: Story-Check führt automatisch auch Position-Fit-Analyse durch (parallel via asyncio.gather). 
UI: Badge auf Investment-Übersicht zeigt Fit + Ein-Satz-Erklärung (🟢 Stärkt / 🔴 Schwächt / ⚪ Neutral).
Filtert automatisch auf Positionen mit Analysen oder Fits (keine leeren Cards).
Basis für kommende Rebalancer-Integration (Rebalancing goal-aware und story-aligned machen).

#### [P2] [FEAT] Portfolio Story: Rebalancer-Integration
Portfolio Story als Kontext in Rebalancer injizieren → Rebalancing-Vorschläge werden goal-aware und story-aligned.

---

### Invest / Rebalance


#### [P3] [FEAT] Invest/Rebalance: Zusammenhang Skill ↔ geplante Cloud-Agents
Architektur-Frage: Wenn Agents (News, Storychecker) automatisch eingeplant werden, sollen ihre Ergebnisse als Kontext in Invest/Rebalance einfließen. Skill-Auswahl im Rebalance könnte steuern, welche Agent-Outputs relevant sind.

Klärungsbedarf: Design-Session vor Umsetzung.

---

### Research / Story / Investment Search

#### [P2] [IMPR] Investment Search: Begründung als Story absichern
Wenn eine Investment-Search-Empfehlung in die Watchlist übernommen wird, soll die Begründung (aus dem Chat) automatisch als Story gespeichert werden.

Umsetzung: "In Watchlist" Button übergibt Begründungstext an Story-Feld.

#### [P3] [FEAT] Story: AI-generiertes Bild
Passend zum Investment (Name, Asset-Klasse, Story) ein Bild generieren lassen — z.B. via DALL-E oder Claude Vision-to-Image (falls verfügbar).

Klärungsbedarf: API-Kosten, Speicherort (Blob oder DB), UI-Integration.

---

### Architektur




---

## Ideas / Later

#### [P3] [FEAT] Rebalance: planned deposits / withdrawals input
Allow users to enter an expected cash in- or outflow before running the analysis.

#### [P3] [FEAT] Empfehlungsquelle auswerten
`recommendation_source` ist im Modell vorhanden. Statistik-Seite: "Quelle → Ø G/V %" über alle empfohlenen Positionen.

#### [P3] [FEAT] Währungsflexibilisierung
`BASE_CURRENCY` Config-Eintrag (default EUR) für CH/GB/US-Nutzer.

#### [P3] [IMPR] UI: Lokale vs. Cloud LLM visuell trennen
Privater Bereich (Ollama 🔒) und Cloud-Bereich (Claude ☁️) klarer abheben — z.B. eigene Navigationsgruppen-Farben oder Badges.

#### [P3] [IMPR] Tonfall-Skill pro Agent
`st.selectbox` "Kommunikationsstil" in der Seitenleiste jedes Chat-Agents (Präzise, Erklärend, Motivierend, Kritisch, Formal).

---

## Done

#### [P2] [FEAT] Storychecker: Alle Positionen auf einmal prüfen
`batch_check_all()` async Methode im `StorycheckerAgent`: iteriert alle Positionen mit Story sequenziell, 15s Sleep zwischen Calls wegen Rate Limit. `start_session_async()` als async Pendant zu `start_session()`. Storychecker-Page: "Alle prüfen" Expander oben mit Background-Thread-Pattern (session_state), Skill-Auswahl, Auto-Refresh alle 5s, Fehler-Count in Erfolgsmeldung. Konsistent mit Fundamental- und Konsens-Lücken-Page.

#### [P2] [IMPR] Rebalance: Cloud-Agent-Ergebnisse in Kontext einbeziehen
`_build_portfolio_context()` lädt jetzt `fundamental`- und `consensus_gap`-Verdicts für alle Portfolio-Positionen und Watchlist-Kandidaten. Positionszeilen zeigen bis zu 3 Signale: `thesis: 🟢 intact | fundamental: 🟢 unterbewertet (+24%) | gap: 🟢 wächst`. Watchlist-Kandidaten ebenfalls mit Cloud-Verdicts angereichert. Graceful: fehlende Analysen werden einfach weggelassen.

#### [P2] [IMPR] Demo-Daten: Analysen für alle Positionen
`seed_demo.py` befüllt `position_analyses` mit fiktiven aber plausiblen Ergebnissen für alle 3 Agenten (storychecker, fundamental, consensus_gap). Summaries mit `[Demodaten]` gekennzeichnet. Werden automatisch überschrieben sobald echte Analysen laufen (neuester Eintrag gewinnt).

#### [P2] [BUG] Scheduling: Agent-Wechsel aktualisiert Skills nicht
Agent-Selectbox im "Geplante Aufgaben"-Formular war innerhalb `st.form` — kein Rerun bei Änderung, Skills-Dropdown blieb statisch. Fix: Agent-Selectbox aus dem Form herausbewegt (triggert Rerun), Skills werden reaktiv neu geladen.

#### [P2] [BUG] Strukturwandel-Scanner: leeres Ergebnis ohne Fehlermeldung
`web_search_20250305` wird von Haiku nicht als Server-Side-Tool ausgeführt — Claude emittiert einen `tool_use`-Block, der nicht in `CLIENT_TOOL_NAMES` ist → agentic loop bricht sofort ab → `response.content = ""`. Fix: Sonnet als Default für alle web-search-lastigen Agenten (structural_scan, consensus_gap, fundamental). Agentic loop zusätzlich auf `stop_reason == "end_turn"` geprüft.

#### [P1] [IMPR] Input validation when creating positions
Agent-extracted values validated before saving: quantity/price positive, purchase date not in the future, ticker format check. UI form: `max_value=date.today()` on date input, ticker required for auto-fetch classes.

→ [GitHub Issue #7](https://github.com/esc1899/wealth_management/issues/7)

#### [P2] [IMPR] Auto-fetch market data on position creation
When a new position with a ticker is added (via form or portfolio chat), current price is automatically fetched via `MarketDataFetcher`. Graceful fallback if fetch fails. Non-blocking.

→ [GitHub Issue #6](https://github.com/esc1899/wealth_management/issues/6)

#### [P2] [IMPR] Portfolio Chat: validation + save confirmation
`_tool_add_portfolio()` validates date format, future dates, quantity > 0, price >= 0. Returns `{"error": "..."}` on failure. Follow-up prompt requests explicit German confirmation with all saved fields (name, ticker, quantity+unit, purchase price, purchase date).

#### [P2] [FEAT] Invest/Rebalance: Weitere Strategien als Skills
Warren Buffett, Norwegischer Pensionsfonds, André Kostolany als wählbare Skills in `default_skills.yaml` geseedet. `SkillsRepository.seed_new_skills(area, list)` fügt neue Skills in bestehende Areas ein (INSERT OR IGNORE per name+area).

#### [P3] [FEAT] Fundamentalwert-Agent ✅ UMGESETZT
`FundamentalAgent` (Säule 3): KGV, P/B, EV/EBITDA, DCF, PEG, Analystenkursziele. Verdicts (unterbewertet/fair/überbewertet/unbekannt) mit Fair-Value-EUR und Upside-% in `position_analyses`. Neue Nav-Seite in "Claude-Strategie". Skills: Fundamentalbewertung Standard, Dividendenbewertung. Default-Modell: Sonnet (benötigt web_search_20250305).

#### [P3] [FEAT] Grosses Experiment: "Claude-Strategie Strukturwandel" ✅ UMGESETZT
`StructuralChangeAgent` (Säule 1): Monatlicher Web-Search-Scan, identifiziert strukturelle Themen vor dem Konsens, fügt Kandidaten direkt zur Watchlist hinzu. `ConsensusGapAgent` (Säule 2): Analysiert Portfolio-Positionen auf Konsens-Lücke, Verdicts (wächst/stabil/schließt/eingeholt) in `position_analyses`. Neue Nav-Gruppe "Claude-Strategie". Skills: Strukturwandel-Identifikation, Second-Order Effects, Konsens-Lücken-Standard, Contrarian-Check. Rebalance-Skill "Claude-Strategie (Strukturwandel)". Scheduling für beide Agenten.

#### [P2] [IMPR] Modellauswahl pro Agent
`config.CLAUDE_MODELS` aus Umgebungsvariable (Default alle drei Modelle, per `.env.work` einschränkbar). `state.py`: `_get_agent_model(agent_key, type, default)` — liest zuerst agentenspezifischen Key (`model_ollama_portfolio`), dann globalen Key, dann Env-Default. Settings-Seite: 2 Ollama-Dropdowns + 3 Claude-Dropdowns, ein Save-Button, `st.cache_resource.clear()` bei Speicherung.

#### [P2] [FEAT] Datenpflege: Anlagearten & Stammdaten
`anlageart` (TEXT, optional) in `positions` (DB-Migration + `init_db`). `AssetClassConfig.anlagearten: List[str]` — befüllt aus `asset_classes.yaml`. Position-Formular zeigt konditionalen Selectbox nur wenn Anlagearten vorhanden. Detail-Dialog zeigt Anlage-Art an. Portfolio-Agent-Tool um optionales `anlageart`-Feld erweitert.

#### [P2] [FEAT] Scheduling: Agents automatisch einplanbar
`scheduled_jobs`-Tabelle + `ScheduledJobsRepository`. `AgentSchedulerService` (eigene BackgroundScheduler-Instanz, eigene DB-Verbindung für Thread-Safety). News-Agent als erster planbarer Agent. Settings-Seite: Liste bestehender Jobs (Enable/Disable-Toggle, Löschen), Formular für neue Jobs (Skill, Häufigkeit, Zeit, Modell). `reload_jobs()` bei jeder Änderung.

#### [P2] [FEAT] Investment Search: Begründung als Story absichern
`add_to_watchlist`-Tool in `search_agent.py` um Feld `story` erweitert. Wird beim Tool-Aufruf von Claude gefüllt und als `Position.story` gespeichert.

#### [P2] [FEAT] Krypto-Warnung
Warnhinweis im Detail-Dialog für `Kryptowährung`-Positionen. Krypto-Positionen im Rebalance-Snapshot mit `⚠️ [HOCHSPEKULATIV — Krypto]` markiert.

#### [P2] [FEAT] Tages-G/V in Analysen + automatisch aktualisierte Kurse
`PortfolioValuation` um `day_pnl_eur` / `day_pnl_pct` erweitert. `MarketDataRepository.get_prev_close()` liefert zweitletzten historischen Schlusskurs. Analyse-Seite zeigt Tages-Performance-Chart. Auto-Fetch beim Seitenaufruf wenn letzte Kurse > 1 Stunde alt.

#### [P1] [IMPR] Rebalancing: Geld und Immobilien separat behandeln
`_build_portfolio_context()` in `rebalance_agent.py` aufgeteilt: "Handelbares Portfolio" (Börsentitel) vs. "Nicht-handelbares Vermögen" (Festgeld, Bargeld, Immobilie, Grundstück). Agent-Kontext macht die Trennung explizit.

#### [P1] [FEAT] Invest/Rebalance: Josef's Regel (Hidden Skill)
Hidden Skill (`area=rebalance`) in `config/default_skills.yaml` geseedet. LLM wird silently über Zielverteilung 1/3 Aktien / 1/3 Renten+Geld / 1/3 Immobilien instruiert. Portfolio-Snapshot liefert Josef's Regel-Tabelle (Ist vs. 33%-Ziel). `SkillsRepository.get_system_skills(area=)` mit optionalem Area-Filter erweitert.

#### [P1] [FEAT] Invest/Rebalance: Position vom Rebalance ausschließen
`rebalance_excluded` Spalte in `positions` (DB-Migration + `init_db`). Position trägt trotzdem zu Josef's Regel und Gesamtvermögen bei. Toggle im Detail-Dialog der Positionen-Seite. Im Snapshot mit `[AUSGESCHLOSSEN]` markiert.

#### [P1] [IMPR] Invest/Rebalance: Watchlist-Kandidaten einbeziehen
Watchlist-Positionen mit Story erscheinen als "Kaufkandidaten"-Sektion im Snapshot — ohne Mengen/Preise. Nur Positionen die nicht schon im Portfolio-Teil sind.

#### [P1] [BUG] Rebalance crashes without error message
`start_session()` and `chat()` in `pages/rebalance_chat.py` are both wrapped in try/except with `st.error()` display.

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

#### [P1] [FEAT] Multi-environment setup
`ENV_PROFILE=work` for machine-specific overrides (OLLAMA_HOST, DB_PATH, etc.)

#### [P2] [FEAT] News Agent (Cloud ☁️)
`NewsAgent` — stateless, one-shot digest per run.

#### [P1] [IMPR] Rename "Rebalance" to "Invest / Rebalance"

#### [P2] [IMPR] News Digest: expandable detail per position

#### [P2] [IMPR] News Digest: session history
