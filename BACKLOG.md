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

Validation in `PortfolioAgent` layer with clear user-facing error messages.

→ [GitHub Issue #7](https://github.com/esc1899/wealth_management/issues/7)

---

## Ideas / Later

#### [P3] [FEAT] Rebalance: planned deposits / withdrawals input
Allow users to enter an expected cash in- or outflow before running the analysis.
The agent would then factor this into its rebalancing recommendations
(e.g. "invest the €2,000 deposit into the most underweighted position").

---

## Done

#### [P2] [IMPR] Streamlit Deploy-Button ausblenden
`.streamlit/config.toml` mit `toolbarMode = "minimal"` — verhindert versehentliches Deployment auf Streamlit Cloud.

#### [P2] [FEAT] System Health / Setup Checks
`core/health.py` mit statischen Checks (kein Netzwerk) + Ollama-Connectivity-Check.
- Sidebar-Ampel (grün/gelb/rot) auf jeder Seite sichtbar
- Detail-Ansicht in Einstellungen mit Check-Button für Ollama
- Checks: Ollama auf Remote-Host (🔴), Langfuse Cloud (🟡), Corporate Proxy (🟡), Demo-Modus (🟡)
- Portfolio Chat: Info-Banner wenn Demo-Modus aktiv

---

#### [P1] [FEAT] Investment Search Agent (Cloud ☁️)
`SearchAgent` with `SearchRepository` + session-based chat. Skills: European Stock Screener, Fund Screener (Cost-Conscious). Page: `pages/search_chat.py`.

→ [GitHub Issue #1](https://github.com/esc1899/wealth_management/issues/1)

#### [P1] [FEAT] Invest & Rebalance Agent (Private 🔒)
`RebalanceAgent` using local Ollama. Skills: Farmer Strategy, Equal Weight Check. Page: `pages/rebalance_chat.py`.

→ [GitHub Issue #2](https://github.com/esc1899/wealth_management/issues/2)

#### [P2] [IMPR] Seed example skills in all environments
`config/default_skills.yaml` covers all areas (portfolio, research, rebalance, search, news).
`seed_if_empty()` seeded for every area on startup via `state.py`.

→ [GitHub Issue #3](https://github.com/esc1899/wealth_management/issues/3)

#### [P1] [FEAT] Multi-environment setup & proxy LLM support
`ENV_PROFILE=work` loads `.env.work` on top of `.env`.
`ANTHROPIC_BASE_URL` for corporate proxy (no API key needed).
`.env.example` updated with all vars and comments.
README documents multi-env setup and proxy config.

→ [GitHub Issue #4](https://github.com/esc1899/wealth_management/issues/4)

#### [P2] [FEAT] News Agent (Cloud ☁️)
`NewsAgent` — stateless, one-shot digest per run. Skills: Long-term Investor, Earnings Focus, ESG Monitor. Page: `pages/news_chat.py`.

→ [GitHub Issue #5](https://github.com/esc1899/wealth_management/issues/5)

#### [P1] [IMPR] Rename "Rebalance" to "Invest / Rebalance"
Nav label, page title, and translations updated.

#### [P2] [IMPR] News Digest: expandable detail per position
`st.expander()` per position with full analysis and assessment emoji. Source links (Markdown URLs) included.

#### [P2] [IMPR] News Digest: session history
Runs stored in DB via `NewsRepository`. Sidebar shows past runs, loadable on click, deletable.
