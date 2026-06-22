#!/bin/bash
# Einfache App-Steuerung "von Hand" — ohne Claude Code.
#
#   ./app.sh start     App starten (Port 8655, via .streamlit/config.toml)
#   ./app.sh stop      App stoppen (lässt den LLM-Proxy auf 6655 in Ruhe)
#   ./app.sh restart   stop + start
#   ./app.sh status    läuft die App? antwortet sie?
#   ./app.sh deps      fehlende Python-Pakete nachinstallieren (requirements.txt)
#   ./app.sh update    git pull + deps + restart  (holt neue Stände vom Hauptrechner)
#   ./app.sh models    welche Cloud-Modelle liefert der Proxy? (-> CLAUDE_MODELS)
#   ./app.sh config    welche LLM-Konfig ist effektiv geladen? (Diagnose 404/Proxy)
#   ./app.sh ping [m]  echter Test-Call: welche CLAUDE_MODELS akzeptiert der Proxy?
#
# Wichtig: stop/start fassen NUR den Streamlit-Prozess an, niemals Port 6655.
#
# Umgebungs-Profil: liegt eine .env.work vor, wird automatisch ENV_PROFILE=work
# gesetzt (lädt .env.work über die Basis-.env). So nutzt der Firmenrechner den
# LLM-Proxy, ohne dass dieses Skript pro Maschine angefasst werden muss. Ein bereits
# gesetztes ENV_PROFILE gewinnt (z.B. ENV_PROFILE=foo ./app.sh start).

set -euo pipefail
cd "$(dirname "$0")"

PORT=8655
URL="http://localhost:${PORT}"
LOG="/tmp/wm_app.log"
PATTERN="streamlit run app.py"

# Profil automatisch wählen: .env.work vorhanden -> work (sofern nicht explizit gesetzt).
if [ -z "${ENV_PROFILE:-}" ] && [ -f .env.work ]; then
    ENV_PROFILE=work
fi
export ENV_PROFILE="${ENV_PROFILE:-}"
PROFILE_NOTE=""
[ -n "$ENV_PROFILE" ] && PROFILE_NOTE=" (Profil: ${ENV_PROFILE})"

activate_venv() {
    if [ -f .venv/bin/activate ]; then
        # shellcheck disable=SC1091
        source .venv/bin/activate
    fi
}

cmd_stop() {
    if pgrep -f "$PATTERN" > /dev/null; then
        pkill -f "$PATTERN"
        echo "⏹  App gestoppt."
    else
        echo "ℹ️  App lief nicht."
    fi
}

cmd_start() {
    if pgrep -f "$PATTERN" > /dev/null; then
        echo "ℹ️  App läuft bereits — nichts zu tun. (sonst: ./app.sh restart)"
        return 0
    fi
    activate_venv
    echo "▶️  Starte App auf ${URL}${PROFILE_NOTE} …"
    nohup streamlit run app.py > "$LOG" 2>&1 &
    for _ in $(seq 1 15); do
        if curl -s "${URL}/_stcore/health" > /dev/null 2>&1; then
            echo "✅ Läuft: ${URL}   (Log: ${LOG})"
            return 0
        fi
        sleep 1
    done
    echo "⚠️  Antwortet nicht innerhalb 15s. Letzte Log-Zeilen:"
    tail -20 "$LOG"
    return 1
}

cmd_status() {
    if pgrep -fl "$PATTERN"; then
        if curl -s "${URL}/_stcore/health" > /dev/null 2>&1; then
            echo "✅ Erreichbar auf ${URL}"
        else
            echo "⚠️  Prozess läuft, aber ${URL} antwortet nicht (Log: ${LOG})"
        fi
    else
        echo "⏹  App läuft nicht."
    fi
}

cmd_deps() {
    activate_venv
    echo "📦 Installiere/aktualisiere Python-Pakete aus requirements.txt …"
    pip install -q -r requirements.txt
    echo "✅ Pakete aktuell."
}

cmd_update() {
    echo "⬇️  git pull …"
    git pull
    cmd_deps
    cmd_stop || true
    cmd_start
}

cmd_ping() {
    activate_venv
    echo "📡 Test-Call an /v1/messages${PROFILE_NOTE} — welche Modell-IDs akzeptiert der Proxy?"
    PING_MODEL="${2:-}" python - <<'PY'
import os
import anthropic
from config import config

models = [os.environ["PING_MODEL"]] if os.environ.get("PING_MODEL") else (config.CLAUDE_MODELS or ["claude-haiku-4-5-20251001"])
kwargs = {"api_key": config.LLM_API_KEY}
if config.LLM_BASE_URL:
    kwargs["base_url"] = config.LLM_BASE_URL
client = anthropic.Anthropic(**kwargs)
print(f"Endpoint: {config.LLM_BASE_URL or 'api.anthropic.com'}")
for m in models:
    try:
        r = client.messages.create(model=m, max_tokens=5, messages=[{"role": "user", "content": "ok"}])
        text = "".join(getattr(b, "text", "") for b in r.content)
        print(f"  ✅ {m}: {text.strip()[:40] or '(leer)'}")
    except Exception as e:
        print(f"  ❌ {m}: {type(e).__name__} {str(e)[:200]}")
PY
}

cmd_config() {
    activate_venv
    echo "🔧 Effektiv geladene LLM-Konfiguration${PROFILE_NOTE}:"
    python - <<'PY'
import os
from config import config
from core.llm.router import resolve_provider_kind

def mask(v):
    return f"gesetzt ({len(v)} Zeichen)" if v else "LEER"

# 1) Welche relevanten Env-Variablen sind WIRKLICH geladen? (deckt Tippfehler/Klein-
#    schreibung auf — Variablennamen sind case-sensitiv!)
print("Geladene Env-Variablen (Name = Wert):")
hits = [(k, v) for k, v in os.environ.items()
        if any(s in k.upper() for s in ("BASE_URL", "ANTHROPIC", "LLM", "OPENAI", "DEEPSEEK"))]
for k, v in sorted(hits):
    shown = v if "URL" in k.upper() else mask(v)   # URLs sind nicht geheim, Keys maskieren
    print(f"  {k} = {shown}")
if not hits:
    print("  (keine)")

# 2) Was macht die App daraus?
print("\nEffektiv in config:")
print(f"  LLM_BASE_URL    = {config.LLM_BASE_URL or 'LEER -> Anthropic direkt (api.anthropic.com)'}")
print(f"  LLM_API_KEY     = {mask(config.LLM_API_KEY)}")
print(f"  LLM_DEFAULT     = {config.LLM_DEFAULT_MODEL or '(keins)'}")
print(f"  CLAUDE_MODELS   = {', '.join(config.CLAUDE_MODELS) or '(leer)'}")
print(f"  OPENAI_BASE_URL = {config.OPENAI_BASE_URL or 'LEER'}")

# 3) Wohin geht der Default-Call?
m = config.LLM_DEFAULT_MODEL or (config.CLAUDE_MODELS[0] if config.CLAUDE_MODELS else "claude-sonnet-4-6")
kind = resolve_provider_kind(m, has_anthropic=bool(config.LLM_API_KEY),
                             has_deepseek=bool(config.DEEPSEEK_API_KEY),
                             has_openai_base=bool(config.OPENAI_BASE_URL))
target = {"claude": config.LLM_BASE_URL or "api.anthropic.com",
          "openai": config.OPENAI_BASE_URL, "deepseek": config.DEEPSEEK_BASE_URL}.get(kind)
print(f"\n  -> Modell '{m}' geht an: {kind}  ({target})")
PY
}

cmd_models() {
    activate_venv
    echo "🔎 Frage verfügbare Cloud-Modelle ab${PROFILE_NOTE} …"
    # config.py lädt .env (+ .env.work via ENV_PROFILE), daher stimmen base_url/Key
    # mit dem überein, was die App nutzt. Ausgabe = Kandidaten für CLAUDE_MODELS.
    python - <<'PY'
from config import config
from core.llm.claude import fetch_available_models

print(f"Endpoint : {config.LLM_BASE_URL or '(Anthropic direkt)'}")
models = fetch_available_models(config.LLM_API_KEY, config.LLM_BASE_URL)
if models:
    print("Verfügbare Modelle (in .env.work als CLAUDE_MODELS eintragen):")
    for m in models:
        print(f"  {m}")
else:
    print("⚠️  Keine Modelle — Proxy antwortet nicht oder /v1/models fehlt.")
    print("    LLM_BASE_URL (inkl. /ANTHROPIC-Pfad?) und LLM_API_KEY prüfen.")
PY
}

case "${1:-}" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    restart) cmd_stop || true; cmd_start ;;
    status)  cmd_status ;;
    deps)    cmd_deps ;;
    update)  cmd_update ;;
    models)  cmd_models ;;
    config)  cmd_config ;;
    ping)    cmd_ping "$@" ;;
    *)
        echo "Benutzung: ./app.sh {start|stop|restart|status|deps|update|models|config|ping [modell]}"
        exit 1
        ;;
esac
