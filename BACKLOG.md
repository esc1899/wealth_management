# Backlog

Nur was offen ist -- mit Datum und dem Grund, warum es liegt. Ist ein
Punkt gebaut oder verworfen, wird er geloescht; was gebaut wurde,
erzaehlen CHANGELOG.md und ARCHITECTURE.md, die Git-Geschichte den Rest.
Regel fuer alle Backlogs im Haus seit dem 28.09.2026
(`~/Projects/heimnetzwerk/CLAUDE.md`, "Doku und Backlog"); am selben Tag
geleert, samt Archiv. Rueckmeldungen und Fehler von aussen:
[GitHub Issues](https://github.com/esc1899/wealth_management/issues).

## Nachrichten bei grossen Kursbewegungen (10.10.2026)

Der News Digest sucht heute nur einmal im Monat. Bewegt sich ein Titel stark (die Kacheln
nennen ab 4 % am Tag "Starke Bewegung heute"), steht auf der Kachel nur die Zahl, nicht der
Grund. Frage: Soll eine starke Bewegung eine Suche nur fuer diesen Titel ausloesen, damit die
Kachel den Grund nennen kann?

Was dabei zu klaeren ist:
- Ausloeser im Job `kurse` (taeglich 18:05), nie beim Oeffnen der Seite: Die Kachel misst und
  sucht nicht (Hausregel).
- Kosten: eine Websuche je Ausreisser, mit einem Deckel je Tag. Als Batch kaeme das Ergebnis
  erst am naechsten Morgen.
- Nur Ticker und Name gehen an das Cloud-Modell, wie beim News Digest heute, nie Stueckzahlen
  (Privacy-Grenze, CLAUDE.md). Fuer Lotsee gilt strenger: auch nicht, ob ein Titel gehalten
  wird (lotsee `docs/plan.md`, "Kandidat Wealth").

Liegt, weil sich erst zeigen soll, ob die Kacheln tragen (zusaetzlicher Menueeintrag seit
10.10.2026).

## Checks je Liste vereinheitlichen (10.10.2026)

Auf den Kacheln stehen die Checks heute alphabetisch, und jeder hat sein eigenes Datum, weil
jeder Check zu seiner Zeit laeuft. Wunsch (Erik): Die Kaestchen zeigen genau die Checks, die
fuer Depot bzw. Watchlist eingestellt sind (Scheduler), in einer festen Reihenfolge je Liste.
Alle Checks einer Liste laufen am selben Tag, und das Datum steht im Kaestchen.

Was dabei zu klaeren ist:
- Woher die Kachel weiss, welche Checks fuer eine Liste eingestellt sind: aus den geplanten
  Jobs (`scheduled_jobs`), nicht aus einer zweiten Liste im Code.
- "Am selben Tag": ein Job je Liste statt je Agent, oder die Agent-Jobs gleich takten.
  Batch-Laeufe kommen erst am naechsten Morgen zurueck, das Datum ist dann das der Antwort.
- Ein Check, der fuer die Liste eingestellt ist, aber fuer diesen Titel noch nie lief, braucht
  ein leeres Kaestchen ("noch nie"), sonst faellt die Luecke nicht auf.

Liegt, weil die Kachel-Ansicht noch erprobt wird (zusaetzlicher Menueeintrag seit 10.10.2026).
