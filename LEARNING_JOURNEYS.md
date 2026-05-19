# Learning Journeys

> Structured paths through this codebase for workshop participants at different levels.
> All journeys use the same running app — start with **Demo Mode** so no API key or real data is needed:
>
> ```bash
> python scripts/seed_demo.py
> DEMO_MODE=true streamlit run app.py
> ```

---

## Overview

| Journey | Audience | Duration | Requires |
|---|---|---|---|
| [A — The AI User](#journey-a--the-ai-user) | Anyone curious about AI apps | 30–45 min | Demo Mode only |
| [B — The Developer](#journey-b--the-developer) | Developer new to LLM integration | 60–90 min | Python, basic terminal |
| [C — The Agent Architect](#journey-c--the-agent-architect) | Developer / ML engineer with AI experience | 90–120 min | Familiarity with APIs + async |
| [D — The Security Engineer](#journey-d--the-security-engineer) | Developer focused on security | 60–90 min | Python, basic crypto concepts |
| [E — The Product Thinker](#journey-e--the-product-thinker) | PM / analyst / anyone evaluating AI tools | 30–45 min | Demo Mode only |
| [F — The Performance Explorer](#journey-f--the-performance-explorer) | Anyone who wants to understand cost and quality levers | 90–120 min | Python, personal API key |
| [G — Real Data Setup](#journey-g--real-data-setup) | Anyone ready to use the app for real — on personal hardware | open-ended | Personal machine, ⚠️ read warning first |

Pick one journey. They overlap by design — people working through different paths will have different things to share at the end.

---

## Journey A — The AI User

**Who this is for:** No coding required. You want to understand what an AI-powered app actually does and where the limits are.

**Goal:** Develop an intuition for local vs. cloud AI, privacy trade-offs, and what AI agents can and cannot do reliably.

### Step 1 — Run the demo and explore the portfolio

Open the app in Demo Mode. The demo has 20 realistic positions across different asset classes.

- Browse **Portfolio** — what does the app track? What is calculated automatically?
- Find the **System Status** panel — note the privacy and connectivity indicators.

> **Question to discuss:** Which of these numbers come from a database, and which require a live internet call?

### Step 2 — Spot the privacy boundary

Navigate to any **Research** page (e.g. Story Checker or Consensus Gap).

- Find the privacy indicator badge on the page. What does it say?
- Now go to **Portfolio Chat** (Local Assistants). What does the badge say here?

> **Key insight:** Local agents (Ollama) see your actual portfolio names, quantities, and notes. Cloud agents only see ticker symbols and public market data. This is a deliberate architectural decision, not a limitation.

### Step 3 — Watch an agent think

Run the **News Digest** for one position in the demo (no API key needed in Demo Mode with a mocked response, or bring a free-tier Anthropic key).

- Watch the output stream in. The model is generating text token by token.
- Open **Statistics → Cost Tracker**. How much did that call cost?

> **Question to discuss:** Why does the News agent cost less than the Structural Change Scanner?

### Step 4 — Edit a skill and see the difference

Go to **System → Skills**. Open one of the existing skill templates.

- Change a single sentence in the prompt — make the tone more formal, or add a constraint like "always mention the P/E ratio."
- Re-run the same agent. Did the output change?

> **Key takeaway:** LLM output is highly sensitive to prompt wording. The Skills system externalises prompts from code so they can be iterated without a developer.

### What you should understand at the end

- Local LLM = private, slower, less capable. Cloud LLM = fast, capable, data leaves your machine.
- Token costs are real and vary by model and agent design.
- Prompt quality is a product decision, not just a technical detail.

---

## Journey B — The Developer

**Who this is for:** You write Python but have not integrated an LLM into a production app before.

**Goal:** Understand the full integration stack — environment, secrets, local model, cloud API, token costs.

### Step 1 — Set up your own instance (not demo)

```bash
git clone https://github.com/esc1899/wealth_management.git
cd wealth_management
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Open `.env`. You need at minimum an `ENCRYPTION_KEY`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> **Question:** Why is this key generated locally rather than committed to the repo? What happens if it leaks?

### Step 2 — Run a local LLM

Install [Ollama](https://ollama.com) and pull a model:

```bash
ollama pull qwen3:8b
```

- How much RAM does this use? Check `ollama ps` while the model is loaded.
- How long does the first response take vs. subsequent ones? (Cold start vs. KV cache warm.)
- Try `qwen3:1.7b` — how does quality change?

Read [`agents/watchlist_checker_agent.py`](agents/watchlist_checker_agent.py) — this is the reference implementation for a local Ollama agent.

> **Key observation:** The local agent receives the full portfolio including position names and quantities. This is intentional — see the privacy boundary in `CLAUDE.md`.

### Step 3 — Make a cloud API call

Add `ANTHROPIC_API_KEY=sk-ant-...` to your `.env`. Run the **Story Checker** for one position.

- Read [`agents/consensus_gap_agent.py`](agents/consensus_gap_agent.py) — the reference implementation for a batch-only cloud agent.
- Find where `PublicPosition` is used instead of `Position`. Why does this matter?

Open **Statistics**. The call you just made is logged with token count and USD cost.

> **Question:** Why does the cloud agent receive a `PublicPosition` (ticker only) rather than a full `Position` (name, story, quantity)?

### Step 4 — Read the secrets management pattern

Look at [`.env.example`](.env.example) and [`core/config.py`](core/config.py).

- How does the app load secrets? Does it ever log them?
- What does `gitignore` exclude, and why?
- What would happen if `ENCRYPTION_KEY` were committed to git history, even once?

### Step 5 — Read the DB migration pattern

Open [`core/storage/base.py`](core/storage/base.py) and find `migrate_db()`.

- All schema changes happen in this single function.
- What happens if you change the schema but don't restart the Streamlit process? (See the "Streamlit cache_resource" section in `CLAUDE.md`.)

### What you should understand at the end

- Local LLMs vs. cloud APIs: the integration code looks similar, the privacy and cost implications are completely different.
- `.env` + Fernet encryption is the minimum viable secrets story for a self-hosted app.
- `@st.cache_resource` makes singletons easy and restarts necessary.

---

## Journey C — The Agent Architect

**Who this is for:** You have built API integrations and want to understand how to design a system of multiple cooperating agents with different properties.

**Goal:** Understand the agent taxonomy in this app — stateful vs. stateless, local vs. cloud, one-shot vs. agentic loop — and the trade-offs behind each choice.

### Step 1 — Map the agent taxonomy

Read the "Agent design trade-offs" section of the README. Then open each reference implementation:

| File | Pattern |
|---|---|
| [`agents/watchlist_checker_agent.py`](agents/watchlist_checker_agent.py) | Local, stateless, one-shot |
| [`agents/consensus_gap_agent.py`](agents/consensus_gap_agent.py) | Cloud, stateless, batch |
| [`agents/fundamental_analyzer_agent.py`](agents/fundamental_analyzer_agent.py) | Cloud, stateful, multi-turn chat |

For each agent, find:
1. How is the model called (single call vs. loop)?
2. Is conversation history persisted? Where?
3. Does it have tool use?

### Step 2 — Study the agentic loop

Open [`agents/structural_change_agent.py`](agents/structural_change_agent.py). This agent runs a full agentic loop: it decides when to call `web_search` and when to call `add_structural_candidate`.

- Find the loop that processes tool calls.
- Where does the agent decide it is "done"?
- How does this differ from the single-call `consensus_gap_agent.py`?

Run both in the app (demo data + API key). Compare the Statistics output: how many tokens does each consume?

> **Key insight:** Agentic loops with web search can cost 5–10× more than a single-call agent. The quality gain must justify it.

### Step 3 — Study session persistence

Read [`core/storage/fundamental_analyzer.py`](core/storage/fundamental_analyzer.py). This is the DB repository for a multi-turn chat agent.

- What tables does it create?
- How does `get_messages()` reconstruct conversation history?
- What would break if this were in-memory instead of a DB? (Hint: Streamlit re-runs the entire script on every user interaction.)

Compare with [`agents/fundamental_analyzer_agent.py`](agents/fundamental_analyzer_agent.py) — find where `start_session()`, `get_messages()`, and `add_message()` are called.

### Step 4 — Study the Research Inbox (file-based pipeline)

Read [`core/cowork/`](core/cowork/) and the "File-based AI ingest pipeline" section of the README.

This is a different integration pattern: a human runs research in an external Claude Project, saves structured `.md` files, and the app ingests them.

- How does the YAML contract enforce structure?
- What validation happens on ingested files?
- What security checks exist for URL fields? Find the input sanitisation code.
- Where is the human-in-the-loop checkpoint before data enters the DB?

> **Discussion:** When is this pattern better than a direct API call? (Answer: when you want human review, when the external tool is more capable for research, when you want to decouple generation from ingestion.)

### Step 5 — Study the privacy boundary enforcement

Read `CLAUDE.md` → "Privacy-Grenze: Local vs. Cloud LLM".

Find `PublicPosition` in [`core/storage/models.py`](core/storage/models.py). Which fields does it expose vs. `Position`?

Find every agent that uses `PublicPosition` and every agent that uses `Position`. Does the split match the privacy table in `CLAUDE.md`?

### What you should understand at the end

- Stateful agents need DB-backed session persistence — in-memory dicts don't survive Streamlit re-renders.
- Agentic loops are powerful and expensive; single-call agents are cheap and predictable. Design accordingly.
- Privacy boundaries are architectural, not just policy — they must be enforced at the model/data-access layer.
- File-based pipelines are a valid integration pattern when you want human checkpoints or decoupled generation.

---

## Journey D — The Security Engineer

**Who this is for:** You care about what could go wrong. You want to understand the threat model and the mitigations.

**Goal:** Audit the app's security posture across secrets management, encryption, input validation, and LLM-specific risks.

### Step 1 — Secrets and encryption

Read [`.env.example`](.env.example) and find how the encryption key is loaded.

- Find the Fernet encryption layer in [`core/storage/`](core/storage/). Which fields are encrypted at rest?
- What happens in Demo Mode — does encryption apply? Why is this a deliberate choice?
- Run `git log --all --full-history -- .env` — confirm the key has never been committed.

> **Question:** What is the blast radius if `ENCRYPTION_KEY` leaks? What is the blast radius if `ANTHROPIC_API_KEY` leaks?

### Step 2 — Input validation in the Research Inbox

Read [`core/cowork/`](core/cowork/) — the file watcher that ingests AI-generated `.md` files.

Find these mitigations and understand what attack they prevent:
- File size limit
- URL protocol whitelist (rejecting `file://`, `javascript:`, etc.)
- Markdown injection prevention in `st.markdown()` calls
- Files rejected to `.invalid/` on parse failure

> **Threat model exercise:** A malicious `.md` file is dropped into the outbox. Walk through what happens at each validation step.

### Step 3 — LLM prompt injection

Read the "LLM Prompt-Injection via Web Search" section in `CLAUDE.md`.

- Which agents do web search and could receive malicious content?
- What limits their blast radius? (Hint: check what data they can write to the DB.)
- What would a prompt injection attempt look like in a news article?

This is an unsolved problem in the industry. The app's mitigation is containment: web-search agents have no write access to portfolio data.

### Step 4 — SQL and XSS

Grep for raw string formatting in SQL queries:

```bash
grep -r "f\"SELECT\|f\"INSERT\|f\"UPDATE\|f\"DELETE" core/storage/
```

Then grep for `unsafe_allow_html`:

```bash
grep -r "unsafe_allow_html" pages/
```

For any hit you find, trace where the string originates. Is it user input, internal data, or a hardcoded constant?

### Step 5 — Authentication

Read `app.py` — find the login gate (`APP_PASSWORD`).

- Is there rate limiting on failed attempts?
- What is the session token lifetime?
- What happens if `APP_PASSWORD` is not set?

> **Discussion:** This is a single-password gate for a personal app. What would need to change for a multi-user deployment?

### What you should understand at the end

- Fernet encryption protects data at rest, but key management is the hard part.
- LLM apps introduce a new input vector: AI-generated content ingested as structured data.
- Prompt injection via web search is real and the practical mitigation is blast-radius containment, not full prevention.
- The app's security posture is appropriate for personal self-hosted use; it has known gaps for multi-user deployments.

---

## Journey E — The Product Thinker

**Who this is for:** You evaluate AI tools, think about user experience, or make build-vs-buy decisions. No coding required.

**Goal:** Understand the capability/cost/privacy trade-off space for AI features, and what "good" agent UX looks like.

### Step 1 — Demo the full feature set

Run the app in Demo Mode. Spend 15 minutes clicking through every page in the left navigation.

Take notes on:
- Which features feel instant? Which have a loading spinner?
- Which pages show a privacy indicator?
- Which features would need an internet connection?

### Step 2 — Compare local vs. cloud experience

Run **Portfolio Chat** (local) — ask it "What is my largest position?"
Run **Research Chat** (cloud, needs API key) — ask it "What is the investment thesis for Nvidia?"

Compare:
- Response time
- Quality of answer
- What data the model had access to (look at the privacy indicator)
- Approximate cost (Statistics page)

### Step 3 — Understand the cost model

Open **Statistics**. The demo has pre-seeded some agent runs.

- Which agent is most expensive per run?
- Which is cheapest?
- What drives the cost difference? (Hint: web search calls + token count)

Look at the **Monthly Forecast** — it projects scheduled-job costs based on actual average token usage.

> **Question:** If you were building a product with these agents, how would you decide which model (Haiku vs. Sonnet) to use for each feature?

### Step 4 — Evaluate the human-in-the-loop design

Open **Research Inbox** (or read its description in the README).

- AI generates research externally. The app shows it for human review before it enters the database.
- Find the confirmation step. What does the user decide?
- Why is this pattern better than fully automatic ingestion for a financial app?

### Step 5 — Critique the UX

Pick one agent page (e.g. Story Checker or Fundamental Analyzer). Think about:

- What does a first-time user need to know to use this?
- Where could the UI fail silently (no error, no output)?
- If you were building this for 1000 users, not one, what would you change?

> **Discussion:** The app has a bilingual UI (German/English) switchable per session. What does that tell you about the intended user base, and what complexity does it add to the codebase?

### What you should understand at the end

- Local LLMs are private and free (after hardware) but slower and less capable. Cloud LLMs are powerful and cost real money.
- Agentic loops (with web search) are 5–10× more expensive than single-call agents — that cost must deliver proportional value.
- Human-in-the-loop checkpoints are a product decision, not just a safety net. They add friction intentionally.
- Cost observability (token counts, USD per run) should be a first-class feature in any AI product.

---

## Journey F — The Performance Explorer

**Who this is for:** You want to understand what actually drives token consumption and cost, and you want hands-on control over model selection. This journey involves real API calls — bring your own key.

**Goal:** Develop a working intuition for the cost/quality trade-off across models and agent designs. Leave with concrete numbers from your own experiments, not just the theory.

### Step 1 — Clone into a personal experiment workspace

Do not experiment on a shared or production instance. Create your own copy:

```bash
git clone https://github.com/esc1899/wealth_management.git wm-experiments
cd wm-experiments
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/seed_demo.py
cp .env.example .env
# Add your ANTHROPIC_API_KEY and a generated ENCRYPTION_KEY
```

Working in a clone means you can change prompts, tweak agent settings, and break things without affecting anyone else.

### Step 2 — Establish a baseline with the Statistics page

Run the app with Demo Mode first, then switch to a real API key. Run each of these agents once on the same position:

- News Digest
- Story Checker
- Consensus Gap Analysis
- Fundamental Analyzer

For each run, note in **Statistics**:
- Input tokens
- Output tokens
- Web search requests (if any)
- USD cost

Build a simple comparison table. The numbers will surprise you.

> **Question:** Which agent costs the most? Is the cost proportional to the quality of output you got?

### Step 3 — Switch models and re-run

The app lets you select the model per agent in **Settings**. Repeat the same runs from Step 2 with:

- `claude-haiku-4-5` (cheapest)
- `claude-sonnet-4-6` (default for web search agents)

Note the cost difference and the quality difference side by side. For agents without web search (News, Story Checker), Haiku is often sufficient. For agents with agentic loops (Structural Change Scanner, Consensus Gap), Sonnet is required — try Haiku and observe what breaks.

### Step 4 — Understand what inflates token count

Read [`agents/consensus_gap_agent.py`](agents/consensus_gap_agent.py) and find the system prompt. Count roughly how many tokens it uses before the user message even arrives.

Now run the Structural Change Scanner and watch the Statistics entry. Find:
- How many web search tool calls were made?
- Each web search result adds tokens to the context. How does that affect the total?
- What is the ratio of input tokens to output tokens?

> **Key insight:** In agentic loops, the majority of cost is input tokens — the growing context of tool results, not the model's generated text.

### Step 5 — Edit a prompt and measure the effect

Pick any agent. Open its system prompt in [`agents/`](agents/) and make it shorter — remove 30% of the instructions. Re-run and compare:

- Did token count drop?
- Did output quality change?
- Was the removed content load-bearing?

Now try the opposite: add a detailed requirement (e.g. "always include a DCF valuation estimate" or "list three counterarguments to your conclusion"). Re-run.

> **Experiment:** What is the cheapest prompt that still produces a useful output for your use case?

### Step 6 — Configure cost alerts

In **Settings**, set a daily spending limit (e.g. $1.00 for experiments). Run enough agents to approach it and observe the warning behaviour in the sidebar and Statistics page.

Read [`core/config.py`](core/config.py) to find how alert thresholds are loaded. Where would you add a hard stop (refusing to run) vs. a soft warning?

### What you should understand at the end

- Input tokens dominate cost in agentic loops — long system prompts and web search results add up fast.
- Haiku vs. Sonnet is a 10–20× cost difference; for many tasks Haiku is good enough.
- Prompt length and precision are engineering levers, not just style choices.
- Cost alerts are essential infrastructure for any AI feature in production.

---

## Journey G — Real Data Setup

**Who this is for:** You want to actually use this app for your own portfolio — not just explore the demo. This journey is personal, not a group exercise. Take your time.

> ⚠️ **Read this before you start**

> **Do not do this on company infrastructure.**
>
> This includes: your work laptop, a corporate VPN, a company-managed cloud account, a corporate LLM proxy, or any system your employer has access to.
>
> When you add real portfolio positions and run cloud agents, ticker symbols are sent to the Anthropic API (or whichever cloud provider you configure). Your company's LLM proxy may log all requests. Your employer's IT policy may prohibit personal financial data on company systems. There are also GDPR implications if the data is processed on infrastructure outside your control.
>
> **Use a personal machine, a personal API key paid from your own account, and a home network.** That is the setup this app was designed for.

### Step 1 — Set up on personal hardware

Follow the Quick Start in the README on your personal machine (not work laptop). The minimum you need:

- Python 3.9+
- A generated `ENCRYPTION_KEY` (the README has the one-liner)
- Optionally: an Anthropic API key for cloud features

Keep Demo Mode off from the start — you are building the real thing.

```bash
git clone https://github.com/esc1899/wealth_management.git
cd wealth_management
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Set ENCRYPTION_KEY — do not lose this key, it is the only way to decrypt your data
streamlit run app.py
```

### Step 2 — Add your first positions

Use **Portfolio Chat** (local Ollama) or the manual form to add a few positions you actually hold. Start small — 3 to 5 positions is enough to make the app feel real.

For each position, add:
- Ticker or name
- Quantity and purchase price
- A short investment thesis (the "Story" field) — even a single sentence

> **Note:** The investment thesis is the most valuable input. Agents like Story Checker and Consensus Gap use it to evaluate whether the market agrees with your reasoning.

### Step 3 — Run Ollama locally first

Before touching any cloud agent, set up Ollama and pull a model:

```bash
ollama pull qwen3:8b   # ~5 GB, requires ~8 GB RAM
```

Run **Portfolio Chat** and ask about your positions. Notice: this model sees your real names, quantities, and stories. It runs entirely on your machine — nothing leaves.

> **Reality check:** How useful is the local model compared to what you expected? What can it do well and where does it fall short?

### Step 4 — Add a cloud API key and understand what changes

Add `ANTHROPIC_API_KEY` to your `.env`. Now run **Story Checker** on one of your real positions.

Open the privacy indicator on the page. Note that the cloud agent receives your ticker and your story text — not your name, not your quantity. This is the privacy boundary the app enforces by design.

Check **Statistics** after the run. This is real money — your money.

> **Moment of reflection:** How does it feel differently when the data is real and the cost is real? This is the experience the demo cannot give you.

### Step 5 — Set spending limits before scheduling anything

Before enabling any scheduled jobs, go to **Settings** and configure:

- Daily cost alert threshold
- Monthly cost alert threshold

Look at what the scheduled jobs would cost if you enabled them (the **Monthly Forecast** in Statistics estimates this from actual average token usage). Only enable schedules you are comfortable paying for.

### Step 6 — Decide what stays local and what goes to the cloud

Review the privacy table in the README ("Agent design trade-offs" section). For each cloud agent, ask yourself:

- Am I comfortable with my ticker symbols going to Anthropic?
- Am I comfortable with my investment thesis (story) going to Anthropic? (Story Checker sends it — this is a documented trade-off.)
- Are there positions I want to exclude from cloud analysis entirely? Use the `analysis_excluded` flag on individual positions.

### What you should understand at the end

- Running with real data makes every design decision in this app feel concrete and personal.
- Token costs are real spending — observability and alerts are not optional.
- The privacy boundary between local and cloud agents exists for a reason; you will feel it when the data is yours.
- A personal self-hosted setup on your own hardware, with your own API key, is meaningfully more private than any corporate AI tool.

---

## Training Format

This training runs over several weeks with no fixed end date. There is no deadline — the goal is learning at a sustainable pace, not completion speed.

### Kick-off Session (together, ~60 min)

- Demo walkthrough as a group — Journey A end-to-end
- Everyone sees the app running, asks first questions
- Each participant picks their journey based on interest and background
- No setup required for the kick-off — Demo Mode runs out of the box

### Self-paced Journey Work (individual, ongoing)

After the kick-off, everyone works through their chosen journey independently — in their own time, at their own pace. There is no assigned schedule. Some steps take 20 minutes, others an hour depending on how deep you want to go.

Tips for self-paced work:
- Use Demo Mode first, add a real API key only when you want to go deeper
- Take notes on things that surprise you — those become the best discussion topics
- It is fine to switch journeys or combine steps from multiple paths
- If you get stuck on setup, bring it to the next Q&A meeting rather than losing time alone

### Bi-weekly Q&A and Feedback Meetings (together, ~45 min)

Every two weeks the group meets to share progress, questions, and observations. No agenda is prepared in advance — the meeting is driven by what participants bring.

Typical structure:
- Round: one thing you learned or found surprising since last time
- Open questions — anything from setup issues to architectural decisions
- Optional: someone does a short live demo of a step they found interesting
- Discussion of anything the group wants to go deeper on

These meetings continue as long as there is interest. There is no fixed end date.
