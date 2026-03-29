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

#### [P1] [IMPR] Rename "Rebalance" to "Invest / Rebalance"
The current name doesn't convey that the agent also helps with investment decisions, not just rebalancing.
- Update nav label in `app.py` and `translations/en.yaml` + `translations/de.yaml`
- Update page title in `pages/rebalance_chat.py`

#### [P2] [IMPR] News Digest: expandable detail per position
Currently each position gets a brief summary line. Users want to read more and see sources.
- Add `st.expander()` per position with full analysis text
- Include clickable source references (URLs) returned by `web_search`
- Requires `NewsAgent` to return structured per-ticker results (list of dicts) instead of one markdown blob

#### [P2] [IMPR] News Digest: session history
News runs are stateless — results are lost on page reload or navigation.
- Store each digest run as a session in DB (analogous to `ResearchRepository`)
- Show past runs in a sidebar, loadable on click
- New: `core/storage/news.py` + `NewsRepository`, or reuse `SearchRepository` pattern

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
