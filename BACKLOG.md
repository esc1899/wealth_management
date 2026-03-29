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

### Bugs
<!-- Known bugs -->

---

## Ideas / Later

<!-- Rough ideas without a concrete plan -->

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
