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

### Features

#### [P1] [FEAT] Investment Search Agent (Cloud ☁️)
A new agent that actively searches for investment opportunities using public APIs.
Follows the existing skills architecture — each search strategy is a skill.

**Skill: Stock Screener**
- Search stocks by region (Europe, US, Emerging Markets, ...)
- Filter by strategy (value, growth, dividend, momentum)
- Cost-aware: flag high transaction costs or illiquid markets
- Output: ranked list with P/E, dividend yield, sector, region

**Skill: Fund Screener**
- Search ETFs and active funds
- Heavy focus on fund costs (TER — Total Expense Ratio)
- Performance comparison (1y, 3y, 5y vs. benchmark)
- Filter by region, sector, or investment theme (ESG, technology, emerging markets, ...)
- Output: ranked list with TER, performance, AUM, theme match

→ [GitHub Issue #1](https://github.com/esc1899/wealth_management/issues/1)

#### [P1] [FEAT] Invest & Rebalance Agent (Private 🔒)
Agent with full portfolio access that suggests buy/sell/rebalance actions.

**Skill: "Gärtner" Strategy**
- **Säen**: underweighted positions → small initial buy
- **Ernten**: positions that grew beyond target weight → take profits
- **Zurückschneiden**: oversized or underperforming positions → trim

General rebalance: compares current vs. target allocation per asset class/region,
flags drift beyond threshold (e.g. ±5%), suggests concrete € amounts.
Recommendations only — no trade execution. Cost-aware (no churning).

→ [GitHub Issue #2](https://github.com/esc1899/wealth_management/issues/2)

#### [P2] [FEAT] News Agent (Cloud ☁️)
Searches for recent news for all portfolio positions, filtered by a configurable skill/strategy.

- Iterates over all positions, runs web_search per ticker
- Skill examples: "long-term investor" (ignore noise), "earnings focus", "ESG monitor"
- Output: news digest per position with relevance assessment
- Results optionally saved to DB for later review

→ [GitHub Issue #5](https://github.com/esc1899/wealth_management/issues/5)

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

#### [P2] [IMPR] Seed example skills in all environments
`config/default_skills.yaml` covers all areas (portfolio, research, rebalance, search).
`seed_if_empty()` seeded for every area on startup via `state.py`.

→ [GitHub Issue #3](https://github.com/esc1899/wealth_management/issues/3)

#### [P1] [FEAT] Multi-environment setup & proxy LLM support
`ENV_PROFILE=work` loads `.env.work` on top of `.env`.
`ANTHROPIC_BASE_URL` for corporate proxy (no API key needed).
`.env.example` updated with all vars and comments.
README documents multi-env setup and proxy config.

→ [GitHub Issue #4](https://github.com/esc1899/wealth_management/issues/4)
