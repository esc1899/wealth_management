# Backlog

Nur was offen ist -- mit Datum und dem Grund, warum es liegt. Ist ein
Punkt gebaut oder verworfen, wird er geloescht; was gebaut wurde,
erzaehlen CHANGELOG.md und ARCHITECTURE.md, die Git-Geschichte den Rest.
Regel fuer alle Backlogs im Haus seit dem 28.09.2026
(`~/Projects/heimnetzwerk/CLAUDE.md`, "Doku und Backlog"); am selben Tag
geleert, samt Archiv. Rueckmeldungen und Fehler von aussen:
[GitHub Issues](https://github.com/esc1899/wealth_management/issues).

## Urteil sicher abholen, wenn die Websuche dabei ist (02.10.2026)

Die Agenten geben ihr Urteil ueber ein Werkzeug ab; seit Opus/Sonnet 5.5
laesst sich das nicht mehr erzwingen (`tool_choice` nur `auto`), also kommt
manchmal keins -- live schiebt der Devil's Advocate einen zweiten Versuch
nach, im Batch steht die Position "ohne Ergebnis". Gebaut ist `strict: true`
(ein Aufruf, der kommt, passt zum Schema). Der geplante Weg, die Antwort per
strukturierter Ausgabe (`output_config.format`) ans Schema zu binden, geht
nicht: Die API lehnt sie zusammen mit der Websuche ab, weil die Treffer
Zitate tragen (im Haus festgestellt beim Ollama-Rat, heimnetzwerk
`docs/maschinenraum/m38-ollama-rat.md`). Moeglich waere ein zweiter, kleiner
Aufruf ohne Werkzeuge, der aus dem fertigen Text das Urteil per Schema holt
-- live als Ersatz fuer den Rueckfall des Devil's Advocate, im Batch fuer
die Positionen ohne Ergebnis. Liegt, bis Erik entscheidet, ob ihm der
zweite Aufruf das wert ist.
