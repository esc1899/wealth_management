#!/bin/bash
#
# Oeffnet der Backup-Button in Settings per `open -a Terminal` (seit 2026-09-27).
#
# Nicht wm_backup.sh direkt, sondern ueber ops-core: Nur so landet der Lauf im
# Run-Log, und nur daraus liest die ops-core-Kachel auf der Startseite. Am
# 26.09. lief die Sicherung direkt und erfolgreich, die Kachel zeigte trotzdem
# "uebersprungen, nie gut". Verantwortlich fuer den Plattenzugriff bleibt
# Terminal -- ops und das Skript sind seine Kinder.

OPS="${HOME}/.local/bin/ops"
if [[ ! -x "${OPS}" ]]; then
    echo "ops nicht gefunden (${OPS}) -- Sicherung läuft direkt, ohne Run-Log."
    exec /bin/bash "${HOME}/scripts/wm_backup.sh"
fi
exec "${OPS}" run wealth_management backup
