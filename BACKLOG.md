# Backlog

Nur was offen ist -- mit Datum und dem Grund, warum es liegt. Ist ein
Punkt gebaut oder verworfen, wird er geloescht; was gebaut wurde,
erzaehlen CHANGELOG.md und ARCHITECTURE.md, die Git-Geschichte den Rest.
Regel fuer alle Backlogs im Haus seit dem 28.09.2026
(`~/Projects/heimnetzwerk/CLAUDE.md`, "Doku und Backlog"); am selben Tag
geleert, samt Archiv. Rueckmeldungen und Fehler von aussen:
[GitHub Issues](https://github.com/esc1899/wealth_management/issues).

## Kacheln loesen die alten Ansichten ab, das Menue wird neu sortiert (10.10.2026)

Die Kacheln sind gut genug, um die alten Listen abzuloesen (Erik, 10.10.2026). Das ist die
Gelegenheit, das Menue aufzuraeumen, und zwar so, wie Lotsee Wealth schneiden wuerde
(lotsee `docs/plan.md`, "Kandidat Wealth"): **nach der Datengrenze, nicht nach dem Anbieter.**
Heute sortiert das Menue nach Technik ("Assistent 🔒", "Research ☁️", "Strategie" fuer
Claude-Agenten, "Cowork"); wer etwas sucht, muss wissen, welches Modell es rechnet.

### Vorschlag: vier Bereiche

**Depot** 🔒 -- was am Bestand haengt; nur das lokale Modell sieht es. In Lotsee der Kern auf
dem Geraet, ohne Server.
- Depot (die Kacheln, neuer Einstieg der App statt Dashboard)
- Uebersicht (heute Dashboard), Vermoegen (Vermoegenshistorie), Entwicklung (Analyse),
  Dividenden
- Portfolio Checker, Portfolio Chat, Investieren / Rebalancieren, Tax Loss Harvesting
  (lokal, heute unter "Strategie" -- dort steht es nur, weil es dort neu war)
- Positionen verwalten (die heutige Seite Positionen: anlegen, bearbeiten, verschieben)
- versteckt: Positionsanalyse -- erreichbar ueber Titel und Kaestchen der Kachel

**Watchlist** -- Titel, die man beobachtet; Cloud-Checks erlaubt, weil sie nur Ticker und
These sehen.
- Watchlist (die Kacheln)
- Watchlist Checker 🔒 (lokal, prueft die Passung zum Depot -- die eine Bruecke zwischen
  beiden Seiten, darum mit Schloss)
- Neue Titel finden: Investment Search, Strukturwandel-Scanner, Research Inbox
- versteckt: Watchlist-Analyse -- erreichbar ueber die Kachel

**Checks** ☁️ -- je Titel, mit Claude. In Lotsee der Teil, der zentral (Indizes) oder mit
eigenem Schluessel laeuft.
- Story Checker, Fundamental Analyzer, Consensus Gap, Capital Allocator, Sektor Rotation,
  News Digest, Research Chat
- Research anfordern und Research-Antworten (heute "Cowork") als ein Eintrag
  "Recherche mit Claude Code"
- Urteils-Rueckblick (heute unter System; er bewertet die Checks)

**System** ⚙️ -- Betrieb, nichts zum Lesen.
- Scheduler, Skills, Kosten (heute Statistiken), Marktdaten, Cowork Setup, Einstellungen

Die Gruppen "Assistent", "Strategie" und "Cowork" entfallen. Das Schloss bzw. die Wolke steht
am Bereich, nicht mehr an jedem Eintrag; der Watchlist Checker ist die Ausnahme.

### Weg (Erik, 10.10.2026): ausblenden, oben anfangen, Rest nach und nach

Seit 10.10.2026 steht oben "Auf einen Blick" mit Depot (Startseite) und Watchlist, die
Kacheln. Ausgeblendet (`visibility="hidden"`, ueber die Adresse weiter erreichbar) sind
Dashboard, Marktdaten (Kurse aktualisieren geht auch auf Analyse und Vermoegenshistorie),
Cowork Setup und die Dialoge Portfolio Chat, Investieren / Rebalancieren und
Research Chat. Alles andere steht darunter wie bisher.

Seit 10.10.2026 folgen darunter "Pflege" (Positionen, Portfolio-Story) und "Performance"
(Analyse, Dividenden, Vermoegenshistorie) -- zusammen die Basis ohne Sprachmodell.

Offen:
- **Die Seiten unten einzeln angehen**, jede fuer sich: in einen der vier Bereiche oben
  ziehen, in die Kacheln aufgehen lassen oder ausblenden. Positions- und Watchlist-Analyse
  werden ausgeblendet, sobald die Kacheln der einzige Weg dorthin sein sollen.
- **News Digest und Investment Search** sind dem Namen nach auch Dialoge (`news_chat.py`,
  `search_chat.py`), liefern aber Ergebnisse: den Digest, den die Positionsanalyse liest, und
  Kandidaten fuer die Watchlist. Darum noch sichtbar -- Erik entscheidet.
- **Ausgeblendetes loeschen**, wenn es zwei Wochen keiner vermisst hat (das "gut genug" aus
  dem Lotsee-Plan). Dashboard: vorher klaeren, ob sein Kopf (Tagesbild, Allokation) auf die
  Depot-Kacheln wandert.

Offen fuer Erik: ob Marktdaten nach System gehoert (heute auch zum Nachsehen einzelner Kurse
genutzt?); ob "Neue Titel finden" ein eigener Bereich wird.

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
