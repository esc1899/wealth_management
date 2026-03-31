# User Guide

Stand: 2026-03-31

## Overview

Wealth Management is a self-hosted portfolio tracking and AI analysis tool.
All portfolio data stays on your own infrastructure. External AI services
(Anthropic Claude API) are only used for the cloud features you explicitly trigger.

---

## Navigation

The app is organized into four groups:

### Portfolio (always local)
| Page | Description |
|---|---|
| **Dashboard** | Portfolio value, P&L, allocation charts |
| **Manage Positions** | Full CRUD for portfolio and watchlist — no AI assistant needed |
| **Market Data** | Current prices, manual refresh, price history |
| **Analysis** | P&L chart per position, price history, allocation by type |
| **Statistics** | Token usage of all AI assistants |

### Assistant 🔒 (local Ollama — data stays on your machine)
| Page | Description |
|---|---|
| **Portfolio Chat** | Natural language: add/remove positions, query your portfolio |
| **Invest / Rebalance** | Rebalancing and investment recommendations |

### Research ☁️ (Claude API — data sent to Anthropic)
| Page | Description |
|---|---|
| **Research Chat** | In-depth stock analysis with web search, multi-turn chat |
| **News Digest** | Recent news for all portfolio positions, filtered by strategy |
| **Investment Search** | Screen for new investment opportunities |

### System ⚙️
| Page | Description |
|---|---|
| **Settings** | Skills, model selection, recommendation labels, language |

---

## Supported Asset Types

| Type | Category | Auto-Price | Watchlist |
|---|---|---|---|
| Aktie (Stock) | Wertpapiere | ✓ yfinance | ✓ |
| Aktienfonds (Stock ETF/Fund) | Wertpapiere | ✓ yfinance | ✓ |
| Rentenfonds (Bond ETF/Fund) | Renten | ✓ yfinance | ✓ |
| Immobilienfonds (REIT) | Immobilien | ✓ yfinance | ✓ |
| Edelmetall (Precious metal) | Edelmetalle | ✓ yfinance | ✓ |
| Kryptowährung (Crypto) | Krypto | ✓ yfinance | ✓ |
| Anleihe (Bond, direct) | Renten | — manual | — |
| Festgeld (Fixed deposit) | Geld | — manual | — |
| Bargeld (Cash) | Geld | — manual | — |
| Immobilie (Property) | Immobilien | — manual | — |
| Grundstück (Land) | Immobilien | — manual | — |

Manual types track value via **Schätzwert** (estimated value), updated in the position detail dialog.

---

## Portfolio Chat

The Portfolio Chat uses a **local LLM** (Ollama) — your portfolio data never leaves your machine.

**What you can do:**
- `Add 10 Apple shares at €150 purchased on 2023-05-15`
- `Add 5 Bitcoin at €30,000`
- `Add a fixed deposit of €10,000 at 3.5% interest, maturing 2027-01-01, at DKB`
- `Add my apartment in Munich, purchased for €300,000`
- `Remove position 4`
- `Show my portfolio`
- `Add AAPL to my watchlist`

The agent understands natural language and maps it to the appropriate asset type automatically.

**Precious metals:** Coins are recognized automatically:
- `Add 2 Krügerrand gold coins purchased last year`

**Non-fetchable types** (Festgeld, Immobilie, Bargeld, etc.) are always added to the portfolio,
never to the watchlist.

---

## Manage Positions

The Positions page provides direct CRUD without any AI — useful when the LLM misunderstands
an instruction or for bulk editing.

**Features:**
- Asset class selector drives the form dynamically (only relevant fields shown)
- Festgeld: extra fields for interest rate, maturity date, and bank
- ISIN/WKN lookup via OpenFIGI API to auto-resolve the yfinance ticker
- Recommendation dropdown (labels configurable in Settings)
- Investment thesis text area per position
- Detail dialog (🔍 button) — shows full position details, allows estimated value update for
  Immobilie and Grundstück positions

---

## Position Detail Dialog

Click 🔍 on any row in the Manage Positions table to open the detail drawer.

**Shows:**
- All position fields including recommendation and investment thesis
- Festgeld: interest rate, maturity date, bank
- Immobilie / Grundstück: **Schätzwert aktualisieren** section
  - Enter current estimated market value and valuation date
  - Warning shown if last valuation is more than 180 days ago
  - Saved to encrypted `extra_data` — reflected immediately in Dashboard and Analysis

---

## Invest / Rebalance

The Rebalance page analyzes your portfolio using a **local LLM** and provides investment
and rebalancing suggestions. No data leaves your machine.

**Before running:**
Make sure prices are up to date on the **Market Data** page — the agent uses current prices
to compute portfolio weights. Manual positions (Immobilie, Festgeld) are included at their
estimated or purchase value.

---

## Research Chat

The Research Chat uses **Claude + web search** (cloud) to analyze individual stocks.

1. Enter a company name or ticker (e.g. `Apple`, `AAPL`, `SAP SE`, `SAP.DE`)
2. Select a strategy (Value Investing, Growth, Dividend, or Custom)
3. Click **Start Analysis**

The agent will search the web, analyze fundamentals, and produce a structured report.
Ask follow-up questions in the same session. Past sessions are listed on the left.

---

## News Digest

Fetches recent news for **all portfolio positions** in one run.

Each position gets an assessment: 🟢 No action / 🟡 Monitor / 🔴 Review.

**Note:** Ticker symbols are sent to the Anthropic API to search the web.

---

## Investment Search

Screen for new investment opportunities using Claude + web search.

1. Enter a query (e.g. `European dividend stocks with P/E < 15`)
2. Select a screening strategy
3. Claude searches the web and returns a ranked candidate list

Ask follow-up questions or add candidates to your watchlist explicitly
(`Add Nestlé to my watchlist`).

---

## Skills

Skills are **reusable prompt strategies** that shape how each agent behaves.
Managed in **Settings → Skills**.

| Area | Used by |
|---|---|
| `rebalancing` | Invest / Rebalance |
| `research` | Research Chat |
| `news` | News Digest |
| `stock_search` | Investment Search |

Default skills for all areas are seeded automatically on first startup.
Custom skills you create are never overwritten.

**Generating a skill with AI:**
In Settings, describe your use case and click **Generate with AI** — Claude will draft
a prompt for you, which you can then edit and save.

---

## Model Selection

In **Settings → Model Selection**:

- **Ollama model** — picked from models currently available in your Ollama instance
- **Claude model** — choose between Haiku (fast/cheap), Sonnet (balanced), or Opus (highest quality)

Changes take effect for new agent calls immediately. The `OLLAMA_MODEL` env var sets the startup default.

---

## Recommendation Labels

In **Settings → Recommendation Labels**, customize the dropdown options shown for every position's
"Empfehlung" field (default: Kaufen, Halten, Verkaufen, Beobachten).

Enter one label per line and save. Changes are reflected immediately across all forms.

---

## Market Data

Prices are fetched from **yfinance** (Yahoo Finance):
- Automatic refresh runs daily at `MARKET_DATA_FETCH_HOUR` (default 18:00)
- Manual refresh: click **Refresh Now** on the Market Data page
- Historical prices (1 year) are stored for the price history chart

**Asset types without auto-fetch** (Anleihe, Festgeld, Bargeld, Immobilie, Grundstück)
are not included in automatic price fetching. Their values are maintained manually.

---

## Statistics

The Statistics page shows token usage across all AI assistants:
- Totals by agent and model (all time and today)
- Daily trend chart (last 30 days)

Useful for understanding costs when using cloud models.

---

## Demo Mode

Demo mode pre-loads a sample portfolio with 20 positions (~€200k total),
including stocks, ETFs, precious metals, crypto, a fixed deposit, and a property.
No real data is used and no `ENCRYPTION_KEY` is required.

```bash
python scripts/seed_demo.py   # creates data/demo.db
DEMO_MODE=true streamlit run app.py
```

A warning banner is shown at the top of every page in demo mode.
