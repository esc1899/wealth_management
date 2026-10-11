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
- Cowork ist seit 10.10.2026 ausgeblendet, "Research anfordern" geloescht; Antworten aus
  Claude Code bleiben auf der Titelseite (unten)
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

Seit 10.10.2026 abends sind auch Positions- und Watchlist-Analyse ausgeblendet (erreichbar nur
ueber Titel und Kaestchen der Kacheln) und der ganze Cowork-Abschnitt; die Seite "Research
anfordern" ist geloescht (Erik). Die Gruppe "Portfolio" entfaellt damit. Alle ausgeblendeten
Seiten stehen in `app.py` in einer Liste `_ausgeblendet`.

Offen:
- **Titelseite nach dem Durchgang** (Erik, 10./11.10.2026; die Seite selbst steht seit
  11.10.2026, `core/ui/titelseite.py`): Ueber den Urteilen, was sich seit dem Durchgang davor
  geaendert hat; der Knopf "Titel pruefen" auch im Depot, mit der Auswahl der Liste. Liegt,
  bis der Durchgang gebaut ist (unten, "Checks je Liste").
- **Die uebrigen Seiten unten einzeln angehen**, jede fuer sich: in einen der vier Bereiche
  oben ziehen, in die Kacheln aufgehen lassen oder ausblenden. Uebrig: Assistent (Portfolio
  Checker, Watchlist Checker), Research, Strategie, System.
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

## Checks je Liste: eine Auswahl, ein Durchgang (10.10.2026)

Heute laufen die Checks eines Titels einzeln: im Depot Storychecker, Fundamental und Consensus
Gap je als eigener Job mit eigenem Takt, Capital Allocator und Devil's Advocate nur von Hand;
auf der Watchlist startet der Knopf der Watchlist-Analyse alle fuenf zusammen. Darum hat jedes
Urteil sein eigenes Datum, und alte stehen neben neuen.

Weg (Erik, 10.10.2026), wie spaeter in Lotsee:
- **Je Liste (Depot, Watchlist) eine Einstellung, welche Checks zu einer Pruefung gehoeren**,
  in fester Reihenfolge. Die Kaestchen der Kacheln zeigen genau diese Checks; einer, der fuer
  den Titel nie lief, steht als "nie geprueft" da.
- **Ausgeloest je Titel** von der Kachel oder der Titelseite ("Titel pruefen"), wie heute der
  Knopf der Watchlist-Analyse. Ein Lauf ist ein **Durchgang**: alle gewaehlten Checks, ein
  Datum; ein frueherer Durchgang ist eine alte Ausgabe der Titelseite.
- **Eingeplant** ein Job je Liste im Scheduler ("Depot pruefen", "Watchlist pruefen"), der
  genau die Auswahl der Liste fuer alle Titel laufen laesst. Die Agent-Jobs je Check fallen
  weg, ebenso die Sonderregel `NUR_AUF_KNOPFDRUCK` (06.10.2026): Was laeuft, sagt die Auswahl.
- **Die Seiten Portfolio Checker und Watchlist Checker entfallen.**

Vorschlag, wartet auf Erik:
- Der **Watchlist Checker** (lokal: passt der Titel zum Depot?) ist selbst ein Check und wird
  ein Eintrag der Watchlist-Auswahl, standardmaessig an; nur seine Seite (Statusmatrix,
  "alle fehlenden Checks") faellt weg.
- Der **Portfolio Checker** prueft keinen Titel, sondern das Depot als Ganzes gegen die
  Portfolio-Story (lokal). Er wird ein Depot-Check der Auswahl, laeuft im Depot-Job mit und
  steht als ein Satz oben auf der Depot-Kachelseite.

Zu bauen:
- Eine Tabelle der Durchgaenge (Liste, Titel, Ausloeser Knopf/Job, Beginn, Ende) und eine
  Spalte `durchgang_id` an den Analysen (`position_analyses` und die Tabellen der lokalen
  Checker); Migration in `migrate_db()`. Aeltere Analysen ohne Durchgang werden je Titel und
  Tag zusammengefasst und stehen als "einzeln geprueft" unter den frueheren Pruefungen.
- Die Auswahl je Liste im Code einmal, in der Datenbank gespeichert, auf der Seite
  Einstellungen oder Scheduler bearbeitet -- nicht als zweite Liste neben `scheduled_jobs`.
- Batch-Laeufe kommen erst am naechsten Morgen zurueck; der Durchgang ist erst fertig, wenn
  alle Antworten da sind, und meldet bis dahin `wartet` (Hausregel).
- **Volltexte verfallen, Urteile bleiben** (Erik, 11.10.2026: die Texte sind irgendwann
  Schnee von gestern, die Entwicklung der Urteile nicht). Urteil und Satz in
  `position_analyses` bleiben fuer immer -- der Urteils-Rueckblick und das Band auf der
  Titelseite leben davon. Die Volltexte (letzte Antwort in den Sitzungen der Agenten)
  loescht ein idempotenter Job; Vorschlag: behalten fuer die letzten zwei Durchgaenge eines
  Titels, aelter weg. Nur Batch-Sitzungen der Checks, nie Dialoge (Fundamental Analyzer
  Chat). Was weg ist, liegt noch in der Sicherung.
- Bleiben eigene Jobs, weil sie keinen Titel pruefen: Sektor-Rotation, News Digest,
  Strukturwandel, Investment-Suche, Snapshots und Rueckblicke.

## Wertzuwachs "Kurs vs. Anteile" mit echten Daten pruefen (10.10.2026)

Die Zerlegung auf der Dividenden-Seite ist am 10.10.2026 korrigiert (Bargeld/Festgeld ausser
Rechnung, Gramm-Positionen, Datenluecken, Tranchen, Verkaeufe; siehe CHANGELOG). Eriks
Eindruck danach: noch nicht ganz korrekt. Er sieht sich die Anlagearten seiner Positionen an,
vor allem, wie Tagesgeld (Fonds mit Ticker oder Bargeld) eingeordnet ist.

Moeglicher naechster Schritt, falls es hilft: ein Klapper "Woher kommt der Anteilszuwachs?"
mit dem Beitrag je Titel und seiner Anlageklasse, sortiert nach Groesse -- so zeigt die Seite
selbst, welche Position die Kurve treibt. Liegt, bis Erik die Anlagearten durchgesehen hat.
