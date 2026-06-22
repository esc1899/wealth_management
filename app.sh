#!/bin/bash
# Einfache App-Steuerung "von Hand" — ohne Claude Code.
#
#   ./app.sh start     App starten (Port 8655, via .streamlit/config.toml)
#   ./app.sh stop      App stoppen (lässt den LLM-Proxy auf 6655 in Ruhe)
#   ./app.sh restart   stop + start
#   ./app.sh status    läuft die App? antwortet sie?
#   ./app.sh deps      fehlende Python-Pakete nachinstallieren (requirements.txt)
#   ./app.sh update    git pull + deps + restart  (holt neue Stände vom Hauptrechner)
#
# Wichtig: stop/start fassen NUR den Streamlit-Prozess an, niemals Port 6655.

set -euo pipefail
cd "$(dirname "$0")"

PORT=8655
URL="http://localhost:${PORT}"
LOG="/tmp/wm_app.log"
PATTERN="streamlit run app.py"

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
    echo "▶️  Starte App auf ${URL} …"
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

case "${1:-}" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    restart) cmd_stop || true; cmd_start ;;
    status)  cmd_status ;;
    deps)    cmd_deps ;;
    update)  cmd_update ;;
    *)
        echo "Benutzung: ./app.sh {start|stop|restart|status|deps|update}"
        exit 1
        ;;
esac
