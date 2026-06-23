# Running Behind a Corporate LLM Proxy

This guide is for participants who run the app inside a **corporate environment** where
there is **no direct internet access** to `api.anthropic.com`, OpenRouter, or DeepSeek.
Instead, the cloud agents talk to an **internal LLM proxy** that speaks the Anthropic API
format (e.g. an in-house gateway, often reachable at something like
`http://localhost:6655`).

You typically also **cannot use Claude Code** in this repository (a private GitHub repo is
blocked by the same corporate egress policy). That is expected — everything below works
from the terminal and the app's Settings page alone.

> **TL;DR** — In `.env` set `ANTHROPIC_BASE_URL` to the proxy's Anthropic **path**, set
> `ANTHROPIC_API_KEY` to the proxy token, set `TAVILY_API_KEY`, and set nothing else for
> cloud. Then verify with the `python` one-liners in [Verify the connection](#verify-the-connection).

---

## 1. What you need from your environment

Ask your platform/IT team (or your training materials) for:

| Item | Example | Notes |
|---|---|---|
| **Proxy base URL incl. vendor path** | `http://localhost:6655/anthropic` | The **path matters** — see the box below. |
| **Proxy token** | a short token (~36 chars) | Sent as `x-api-key`. **Not** a real `sk-ant-…` key. |
| **Tavily API key** | `tvly-…` | Web search replacement (the proxy usually can't do Anthropic's built-in web search). Must be reachable from the corporate network. |

> ⚠️ **The vendor path is part of the URL and is case-sensitive.**
> Many proxies multiplex several vendors by path and only inject the real upstream
> credentials on a specific route. In the reference setup the working path is
> **`/anthropic` (lowercase)**:
> - `http://localhost:6655/anthropic` → ✅ works
> - `http://localhost:6655/` (no path) → ❌ `401 invalid x-api-key` (the proxy forwards
>   your token straight to the real Anthropic API, which rejects it)
> - `http://localhost:6655/ANTHROPIC` (uppercase) → ❌ `404 page not found`
>
> Your proxy's path may differ — confirm it with your team or probe it (see
> [Troubleshooting](#troubleshooting)).

---

## 2. Configure `.env`

Copy `.env.example` to `.env` and set:

```env
# Required for encrypted local storage (generate once):
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=your_fernet_key_here

# --- Cloud agents via the corporate Anthropic proxy ---
ANTHROPIC_BASE_URL=http://localhost:6655/anthropic   # proxy URL incl. vendor path
ANTHROPIC_API_KEY=<your-proxy-token>                 # the proxy token (sent as x-api-key)

# --- Web search (the proxy cannot run Anthropic's built-in web_search) ---
TAVILY_API_KEY=<your-tavily-key>

# Leave the other cloud providers OFF — they are blocked in the corporate network:
# (do NOT set OPENAI_BASE_URL / OPENAI_API_KEY / DEEPSEEK_API_KEY)
```

That's it. Notes on **why** this is enough:

- The app reads `LLM_BASE_URL`, which **falls back to `ANTHROPIC_BASE_URL`** (mirroring the
  `ANTHROPIC_API_KEY` fallback). So setting the standard `ANTHROPIC_BASE_URL` is sufficient —
  all `claude-*` cloud agents route through your proxy.
- With a custom base URL set, the app does **not** use Anthropic's server-side web search
  (the proxy rejects it). If `TAVILY_API_KEY` is set, web searches run through Tavily
  client-side automatically; if it isn't, the search tool is dropped and agents still run,
  just without live web data.

---

## 3. Local models (optional)

The private/local assistants (Portfolio Chat, Rebalance, etc.) use **Ollama** and never
leave your machine. If your training path uses them, install Ollama and pull a model:

```bash
ollama pull qwen3:8b
```

Set `OLLAMA_HOST` in `.env` if Ollama runs on another host. Local agents are independent of
the proxy.

---

## 4. Start the app

**Cross-platform (any OS):**

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

**macOS/Linux convenience:** the repo ships a hand-operation helper `app.sh` (no Claude Code
needed):

```bash
./app.sh start      # start (background, health-checked)
./app.sh update     # git pull + pip install + restart
./app.sh config     # show the effective LLM config (great for debugging, see below)
./app.sh ping       # real test call: which model IDs does the proxy accept?
```

---

## 5. Verify the connection

Run these from the repo root (with the venv active). They use the **same** config the app
loads, so they prove the proxy path/token/web-search end to end. **No secrets are printed.**

**a) Is the proxy URL actually loaded?** (catches typos / wrong variable name — env var
names are case-sensitive)

```bash
python -c "from config import config as c; \
print('base_url =', repr(c.LLM_BASE_URL)); \
print('api_key set =', bool(c.LLM_API_KEY)); \
print('tavily set =', bool(c.TAVILY_API_KEY))"
```

`base_url` must show your `…/anthropic` URL. If it's empty, your `.env` line is missing,
commented out, or misspelled. *(macOS/Linux: `./app.sh config` shows this plus every loaded
LLM-related env variable.)*

**b) Does a real completion go through the proxy?**

```bash
python -c "import anthropic; from config import config as c; \
cl = anthropic.Anthropic(api_key=c.LLM_API_KEY, base_url=c.LLM_BASE_URL); \
m = cl.messages.create(model='claude-sonnet-4-6', max_tokens=5, \
messages=[{'role':'user','content':'ok'}]); \
print('OK:', ''.join(b.text for b in m.content if getattr(b,'type','')=='text'))"
```

`OK: …` means the path + token work. *(macOS/Linux: `./app.sh ping` tries every configured
model ID and reports which the proxy accepts.)*

Then open **Settings → System Status** in the app, and pick a model per cloud agent under
**Settings → Cloud agents** (this saves your choice to the local DB).

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `401 invalid x-api-key` with a real-looking `request_id` (`req_011C…`) | The proxy forwarded your token to the **real** Anthropic API — usually because the **vendor path is missing** from `ANTHROPIC_BASE_URL`. | Add the path, e.g. `…/anthropic` (lowercase). |
| `404 page not found` (plain text, not JSON) | Wrong path — that route doesn't exist on the proxy (e.g. `/ANTHROPIC` uppercase). | Use the correct path; confirm with your team. Probe quickly with `./app.sh ping "" http://host:port/<path>`. |
| `400 … web_search_20250305 … does not match any of the expected tags` | The proxy's upstream can't run Anthropic's built-in web search. | Set `TAVILY_API_KEY` in `.env` (web search then runs via Tavily). Restart. |
| `Search failed: …` inside an agent's search results | Tavily key is set but `api.tavily.com` isn't reachable from the corporate network. | Ask IT to allow `api.tavily.com`, or run agents that don't need web search. The agent still completes. |
| `model not found` / 404 on a specific model ID | The proxy serves different model IDs than the defaults. | Find the accepted IDs (`./app.sh ping`) and set `CLAUDE_MODELS=<comma-separated IDs>` (+ optional `LLM_DEFAULT_MODEL`) in `.env`. |
| App calls don't reach the proxy at all (its request count stays flat) | `LLM_BASE_URL`/`ANTHROPIC_BASE_URL` is empty or misspelled in the loaded env. | Run verify step (a). Variable names are case-sensitive — `ANTHROPIC_BASE_URL`, not lowercase. |
| Cloud-model dropdown shows OpenRouter/DeepSeek models you can't use | Those providers' models are configured/seeded but blocked in your network. | Don't set `OPENAI_*` / `DEEPSEEK_*`. The dropdown only offers models of configured providers. |

The proxy has **no `/v1/models` listing endpoint** in the reference setup, so the app can't
auto-discover models and falls back to the IDs in `CLAUDE_MODELS` (defaults:
`claude-haiku-4-5-20251001`, `claude-sonnet-4-6`, `claude-opus-4-8`). That's fine as long as
the proxy serves those IDs — verify with `./app.sh ping`.

---

## Where your data goes (privacy)

The privacy boundary is unchanged by the proxy: **local assistants (Ollama) see your full
portfolio and send nothing**; **cloud agents see only public data** (tickers, market data,
news) and now route that through your corporate proxy instead of directly to Anthropic.
Note that a corporate proxy **may log all requests** — see the warning in the main README
about running on employer-managed infrastructure.
