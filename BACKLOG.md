# Backlog

Nur was offen ist -- mit Datum und dem Grund, warum es liegt. Ist ein
Punkt gebaut oder verworfen, wird er geloescht; was gebaut wurde,
erzaehlen CHANGELOG.md und ARCHITECTURE.md, die Git-Geschichte den Rest.
Regel fuer alle Backlogs im Haus seit dem 28.09.2026
(`~/Projects/heimnetzwerk/CLAUDE.md`, "Doku und Backlog"); am selben Tag
geleert, samt Archiv. Rueckmeldungen und Fehler von aussen:
[GitHub Issues](https://github.com/esc1899/wealth_management/issues).

## Urteil als Schema statt als Werkzeug (02.10.2026)

Die Agenten geben ihr Urteil ueber ein Werkzeug ab (`SUBMIT_VERDICT_TOOL`,
`SUBMIT_DA_VERDICT_TOOL`). Seit Opus/Sonnet 5.5 laesst sich das nicht mehr
erzwingen (`tool_choice` nur `auto`), also kommt manchmal keins -- live
schiebt der Devil's Advocate einen zweiten Versuch nach, im Batch steht
die Position "ohne Ergebnis". Mit strukturierter Ausgabe
(`output_config.format`, JSON-Schema) ist die Antwort an das Schema
gebunden, live und im Batch gleich. Dazu `strict: true` an den
verbleibenden Werkzeugen. Liegt, weil am 02.10. erst beschlossen; zusammen
mit dem naechsten Punkt bauen, es sind dieselben Dateien.

## Websuche auf `web_search_20260209` (02.10.2026)

Wealth fragt noch die alte Websuche (`scheduler.py`,
`position_story_service.py`, `_WEB_SEARCH_SERVER` in `core/llm/claude.py`,
`_WEB_SEARCH_TYPES` in `core/llm/openai_compatible.py`). Die neue filtert
die Treffer, bevor sie in den Kontext gehen -- weniger Eingabe-Tokens je
Suche, bei Sonnet/Opus 5.5 verfuegbar; Home-Ops und Maschinenraum nutzen
sie schon. Der Tavily-Weg hinter OpenRouter/`LLM_BASE_URL` muss die neue
Kennung weiter erkennen. Liegt wie der Punkt davor.
