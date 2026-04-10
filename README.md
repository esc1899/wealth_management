# Wealth Management

A self-hosted, agentic wealth management system built with Python, Streamlit, and local LLMs.

> **Disclaimer:** This app is for informational purposes only. AI-generated content does not constitute financial or investment advice. The authors accept no liability for financial losses. See [Disclaimer](#disclaimer) below.

> **Tip — Setup with Claude Code:** This project was built with and is optimized for [Claude Code](https://claude.ai/code). Using it for initial setup, configuration, and troubleshooting is recommended — but entirely optional.

## Requirements & Responsibility

This app **must be self-hosted**. The authors do not operate any instance of this software and have no access to your data at any time.

- You are solely responsible for your deployment, data security, and any API keys you configure.
- If you use external AI APIs (e.g. Anthropic API for Research Chat), your data is subject to that provider's terms and privacy policy.
- This project is **not affiliated** with Anthropic or any other AI provider.
- Commercial use requires a separate license — see [Commercial Licensing](#commercial-licensing) below.

## Features

### Portfolio
- **Portfolio Management** — track 11 asset types: stocks, ETFs, funds, precious metals, crypto, bonds, fixed deposits, cash, real estate, and land
- **Live Market Data** — automatic and on-demand prices via yfinance with EUR conversion
- **P&L Analysis** — daily gains/losses, allocation charts, day performance
- **Rebalancing** — Josef's Rule (1/3 each: equities / bonds+cash / real estate) as hidden strategy layer

### Wealth Snapshots (historical tracking)
- **Wealth Timeline** — automatic daily snapshots of total portfolio value over time; breakdown by asset class
- **Manual Snapshots** — capture wealth state on demand with optional note
- **Edit & Correct** — modify individual asset class values retroactively; total recalculates automatically
- **Snapshot Management** — delete, view history, detect stale manual valuations (>30 days)
- **Coverage Tracking** — visibility into which positions have valid values; warnings for incomplete data

### Local Assistants (private, Ollama)
- **Portfolio Chat** — natural language CRUD interface; data never leaves your machine
- **Invest / Rebalance** — portfolio rebalancing analysis including watchlist candidates and all cloud verdicts

### Research (cloud, Claude API + web search)
- **Research Chat** — deep-dive research per position using Claude
- **News Digest** — recent news for all portfolio positions, filtered by investment strategy
- **Investment Search** — screen for new opportunities; thesis saved automatically to watchlist
- **Story Checker** — validates investment theses against current news and fundamentals
- **Fundamental Value** — per-position valuation via P/E, P/B, EV/EBITDA, DCF, PEG; verdict: undervalued / fair / overvalued

### Claude Strategy (cloud, Claude Sonnet + web search)
- **Structural Change Scanner** — identifies irreversible market shifts not yet priced by consensus; adds candidates directly to watchlist
- **Consensus Gap Analysis** — measures the gap between your investment thesis and market consensus per position
- All verdicts from all agents feed back into the Rebalance context automatically

### System
- **Skills System** — reusable prompt templates for every agent; AI-assisted generation in Settings
- **Per-agent Model Selection** — choose Ollama and Claude models individually at runtime
- **Scheduled Tasks** — run cloud agents automatically on a schedule (daily / weekly / monthly)
- **Cost & Token Tracking** — per-agent/skill/model token counts and USD costs; split by manual vs. scheduled runs; daily trend chart; non-destructive per-row reset
- **Cost Alerts** — configurable daily and monthly USD spending limits; warnings in sidebar and Statistics page
- **Monthly Cost Forecast** — projects scheduled-job costs forward based on actual average tokens per call
- **Performance Benchmarks** — run agents against fixed scenarios; compare runs over time; duration and token delta tracked per benchmark
- **Recommendation & Story** — configurable recommendation labels and investment thesis per position
- **Demo Mode** — pre-seeded database with 20 realistic positions + sample analyses for testing
- **Bilingual UI** — German / English, switchable per session
- **System Status** — health checks for Ollama connectivity, privacy mode, and demo mode

## What You Can Learn Here

This project is a hands-on introduction to building real AI-powered applications. The exercises are not toy examples — the end result is your own personal wealth management tool. That is the point: learning agent architecture by building something you actually want to use.

### Running a local LLM with Ollama
Install Ollama and pull a model (e.g. `qwen3:8b`). Learn what running an LLM on your own hardware means: model size vs. RAM, context windows, cold start latency, and when a local model is good enough vs. when you need a cloud API.

### Using a cloud LLM API
The research and news features use the Anthropic Claude API. Get an API key, set it in `.env`, and see tokens consumed in the Statistics page. Learn what a token costs and why model choice (Haiku vs. Sonnet) matters.

### Privacy and where your data goes
The app has a live privacy indicator on every agent page. See the difference between a local model (portfolio data never leaves your machine) and a cloud API call (tickers go to Anthropic's servers). Health checks warn you if something is less private than expected.

### Keeping secrets with `.env`
API keys, encryption keys, and database paths live in `.env`, which is gitignored. Learn why this file must never be committed, what happens if it leaks, and how to manage multiple environments.

### Encrypted local storage
Portfolio data (quantities, prices, notes, investment thesis) is encrypted at rest with a Fernet key you generate yourself. Demo mode deliberately skips encryption — a useful contrast.

### Skills as reusable prompts
The Skills system lets you save and edit prompt templates for each agent. Learn that a well-written system prompt dramatically changes LLM output quality, and that externalising prompts from code makes them easier to iterate on.

### Monitoring with Langfuse
Optionally connect Langfuse to trace every LLM call — full prompt, response, latency, and token counts.

### Agent design trade-offs
The app has ten agents with different characteristics: stateful vs. stateless, local vs. cloud, one-shot vs. conversational, agentic loop vs. single call. Comparing Portfolio Chat, Rebalance, Research Chat, News Digest, the Story Checker, and the Claude Strategy agents shows the practical trade-offs: privacy, cost, speed, and capability.

### Agentic loops and tool use
The Structural Change Scanner runs an agentic loop: Claude decides when to call `web_search` and when to call the custom `add_structural_candidate` tool to populate your watchlist — no user interaction needed. Compare this to the simpler Research Chat (single call) to understand the cost/quality trade-off.

### Tracking costs and controlling spending
The Statistics page gives an indication of what each agent call costs in USD, broken down by agent, skill, and model. Configurable daily and monthly alert thresholds warn you before spending gets out of hand. The monthly forecast extrapolates from actual average token usage of your scheduled jobs — so you see the projected bill before it arrives. Learn what makes one agent 10× more expensive than another (hint: agentic loops with web search vs. a single-shot call), and how to use this to choose the right model for each task.

### Benchmarking prompt and model changes
The Benchmark page lets you run an agent against a fixed scenario and compare the results over time. Change the system prompt or switch from Sonnet to Haiku, run the benchmark, and see the token delta and duration side by side. This is the feedback loop for prompt engineering: measurable, repeatable, not just a feeling.

---

## Tech Stack

- Python 3.9+, Streamlit
- SQLite (encrypted via cryptography/Fernet)
- Ollama (local LLM, e.g. qwen3:8b)
- Anthropic Claude API (optional, for Research/News/Search)
- yfinance for market data
- APScheduler for automated price fetching

## Quick Start

```bash
git clone https://github.com/esc1899/wealth_management.git
cd wealth_management
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env — set ENCRYPTION_KEY at minimum
streamlit run app.py
```

**Demo mode** (no encryption key required):
```bash
python scripts/seed_demo.py
DEMO_MODE=true streamlit run app.py
```

## Configuration

Copy `.env.example` to `.env` and fill in your values.

| Variable | Required | Description |
|---|---|---|
| `ENCRYPTION_KEY` | Yes | Fernet key — generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `ANTHROPIC_API_KEY` | See below | Direct Anthropic API key (for Research Chat, News Digest, Investment Search) |
| `ANTHROPIC_BASE_URL` | See below | LLM proxy URL — use instead of `ANTHROPIC_API_KEY` |
| `OLLAMA_HOST` | Optional | Default: `http://localhost:11434` |
| `OLLAMA_MODEL` | Optional | Default model for Portfolio Chat and Rebalance (overridable in Settings UI) |
| `TAVILY_API_KEY` | Optional | Tavily search — replaces Anthropic's built-in web_search when set. Free tier: 1000 searches/month |
| `LANGFUSE_SECRET_KEY` | Optional | Langfuse monitoring (omit to disable) |
| `LANGFUSE_PUBLIC_KEY` | Optional | Langfuse monitoring (omit to disable) |
| `DEMO_MODE` | Optional | Set to `true` to use the demo database |
| `DB_PATH` | Optional | Default: `data/portfolio.db` |
| `MARKET_DATA_FETCH_HOUR` | Optional | Hour (0–23) for automatic price refresh, default `18` |

At least one of `ANTHROPIC_API_KEY` or `ANTHROPIC_BASE_URL` is required to use Research Chat, News Digest, Investment Search, Story Checker, Structural Change Scanner, Consensus Gap Analysis, or Fundamental Value.

**Note on model choice:** Claude Sonnet (or better) is required for agents that use `web_search` (Structural Change Scanner, Consensus Gap, Fundamental Value). Claude Haiku works for Research Chat, News Digest, and Story Checker.

### LLM Proxy (corporate environments)

```env
ANTHROPIC_BASE_URL=https://your-llm-proxy.example.com
```

The proxy must expose an Anthropic-compatible API.

### Multi-Environment Setup

Use environment profiles to maintain separate configs for different machines:

```bash
# .env.work — only the values that differ
ANTHROPIC_BASE_URL=https://corp-proxy.example.com
OLLAMA_HOST=http://workstation.local:11434
DB_PATH=data/work.db
```

```bash
ENV_PROFILE=work streamlit run app.py
```

### macOS App Bundle

Create a native macOS app with icon for easy access from Applications folder and Dock:

```bash
# Generate icon (custom portfolio chart theme)
python3 generate_icon.py

# Convert to .icns and install in app bundle
python3 install_icon.py

# Create app bundle
python3 create_automator_app.py
```

The app will appear in `/Applications`. You can add it to Dock by dragging it there or:
```bash
# Right-click app → Options → Keep in Dock
```

**Note:** The app bundle launches via `.command` file for reliable Python environment detection on Apple Silicon Macs.

## Commercial Licensing

This project is released under the [Business Source License 1.1](LICENSE), which allows personal, educational, and non-commercial use freely.

**Commercial use, production hosting, or white-label distribution requires a separate commercial license.**

This includes (but is not limited to):
- Hosting a running instance for paying users or clients
- Embedding this software in a commercial product or SaaS offering
- Distributing a modified version as part of a training programme or course for profit
- Deploying internally at a bank, fintech, or financial institution

If any of these apply to you, contact us before deploying:

📩 **faeden.tuell_34@icloud.com**

We are open to licensing arrangements for financial institutions, fintech companies, LLM training providers, and enterprise deployments.

---

## Disclaimer

This app is for informational purposes only. AI-generated content does not constitute financial or investment advice. The authors accept no liability for financial losses based on information provided by this app. This software is provided as-is with no warranties of any kind.

## Privacy

See [PRIVACY.md](PRIVACY.md) for the full privacy notice.

## License

[Business Source License 1.1](LICENSE) — free for personal and educational use. Commercial use requires a separate license, see [Commercial Licensing](#commercial-licensing).
