# User Guide

## Overview

Wealth Management is a self-hosted portfolio tracking and AI analysis tool.
All portfolio data stays on your own infrastructure. External AI services
(Anthropic Claude API) are only used for the cloud features you explicitly trigger.

---

## Navigation

The app is organized into three groups:

### Portfolio (always local)
| Page | Description |
|---|---|
| **Dashboard** | Portfolio value, P&L, allocation charts |
| **Market Data** | Current prices, manual refresh, price history |
| **Analysis** | P&L chart per position, price history, allocation by type |

### Assistant 🔒 (local Ollama — data stays on your machine)
| Page | Description |
|---|---|
| **Portfolio Chat** | Natural language: add/remove positions, query your portfolio |
| **Rebalance** | Rebalancing recommendations using the Farmer Strategy or Equal Weight Check |

### Research ☁️ (Claude API — data sent to Anthropic)
| Page | Description |
|---|---|
| **Research Chat** | In-depth stock analysis with web search, multi-turn chat |
| **News Digest** | Recent news for all portfolio positions, filtered by strategy |
| **Investment Search** | Screen for new investment opportunities |
| **Settings** | Manage skills (reusable prompt strategies) |

---

## Portfolio Chat

The Portfolio Chat uses a **local LLM** (Ollama) — your portfolio data never leaves your machine.

**What you can do:**
- `Add 10 Apple shares at €150 purchased on 2023-05-15`
- `Remove position 4`
- `Show my portfolio`
- `Add AAPL to my watchlist`

The agent understands natural language and maps it to actions automatically.

**Precious metals:** Coins like Krügerrand or Maple Leaf are recognized automatically:
- `Add 2 Krügerrand gold coins purchased last year`

---

## Rebalance

The Rebalance page analyzes your current portfolio using a **local LLM** and provides
rebalancing suggestions. No data leaves your machine.

**Before running:**
Make sure prices are up to date on the **Market Data** page — the agent uses current prices
to compute portfolio weights.

**Available strategies (configurable in Settings):**

| Strategy | Description |
|---|---|
| **Farmer Strategy** | 🌱 Sow underweighted positions, 🌾 Harvest outgrown ones, ✂️ Prune underperformers |
| **Equal Weight Check** | Flags positions that have drifted > 5% from equal weighting |

---

## Research Chat

The Research Chat uses **Claude + web search** (cloud) to analyze individual stocks.

**Starting an analysis:**
1. Enter a company name or ticker (e.g. `Apple`, `AAPL`, `SAP SE`, `SAP.DE`)
2. Select a strategy (Value Investing, Growth, Dividend, or Custom)
3. Click **Start Analysis**

The agent will search the web, analyze fundamentals, and produce a structured report.
You can then ask follow-up questions in the same session.

**Adding to Watchlist:**
Tell the agent explicitly: `Add this to my watchlist` — it will use the `add_to_watchlist` tool.

**Past sessions** are listed in the left column and can be reopened at any time.

---

## News Digest

The News Digest fetches recent news for **all portfolio positions** in one run.

**Filter strategies:**

| Strategy | What it keeps |
|---|---|
| **Long-term Investor** | Only structurally significant events (no price noise) |
| **Earnings Focus** | Earnings, guidance, analyst changes, insider activity |
| **ESG Monitor** | Environmental, social, and governance events |

Each position gets an assessment: 🟢 No action / 🟡 Monitor / 🔴 Review.

**Note:** Ticker symbols are sent to the Anthropic API to search the web.

---

## Investment Search

Investment Search screens for new investment opportunities using Claude + web search.

**How it works:**
1. Enter a query (e.g. `European dividend stocks with P/E < 15`)
2. Select a screening strategy
3. Claude searches the web and returns a ranked candidate list

You can then ask follow-up questions (`Tell me more about Nestlé`) or explicitly add
candidates to your watchlist (`Add Nestlé to my watchlist`).

**Past searches** are persisted and can be revisited.

---

## Skills

Skills are **reusable prompt strategies** that shape how each agent behaves.
They can be created, edited, and deleted in **Settings → Skills**.

Each skill belongs to an **area** that determines which agent uses it:

| Area | Used by |
|---|---|
| `portfolio` | Portfolio Chat |
| `rebalance` | Rebalance |
| `research` | Research Chat |
| `news` | News Digest |
| `search` | Investment Search |

**Default skills** for all areas are seeded automatically on first startup.
Custom skills you create are never overwritten.

**Generating a skill with AI:**
In Settings, describe your use case and click **Generate with AI** — Claude will draft
a prompt for you, which you can then edit and save.

---

## Market Data

Prices are fetched from **yfinance** (Yahoo Finance):
- Automatic refresh runs daily at the configured hour (`MARKET_DATA_FETCH_HOUR`, default 18:00)
- Manual refresh: click **Refresh Now** on the Market Data page
- Historical prices are stored for the price history chart

**Missing prices:**
Positions without a ticker symbol cannot be priced. The "positions without ticker" warning
on the Market Data page lists them.

---

## Demo Mode

Demo mode pre-loads a sample portfolio with 17 positions (~€170k total).
No real data is used.

To start demo mode:
```bash
python scripts/seed_demo.py   # creates data/demo.db
DEMO_MODE=true streamlit run app.py
```

In demo mode the disclaimer banner is shown at the top of every page.
No encryption key is required.
