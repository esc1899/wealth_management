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
Seiten stehen in `app.py` in einer Liste `_ausgeblendet`. Seit 11.10.2026 gehoeren Portfolio
Checker und Watchlist Checker dazu, die Gruppe "Assistent" entfaellt. Seit 11.10.2026 ist
auch "System" aufgeloest: Urteils-Rueckblick unter Performance, Skills, Scheduler und
Statistiken unter Einstellungen.

Offen:
- **Was die ausgeblendeten Check-Seiten noch konnten** (Storychecker, Fundamental, Konsens,
  seit 11.10.2026 aus dem Menue): je Einzelcheck einen Skill waehlen und im Storychecker und
  Fundamental Analyzer nachfragen (Chat). Die Titelseite prueft mit dem Skill aus dem
  Scheduler und kennt keine Nachfrage. Faellt es Erik nicht auf, entfaellt beides mit dem
  Loeschen; sonst gehoert es zur Auswahl je Liste (Einstellungen, `core/pruefung.py`).
- **Ausgeblendetes loeschen**, wenn es zwei Wochen keiner vermisst hat (das "gut genug" aus
  dem Lotsee-Plan). Darunter Portfolio Checker und Watchlist Checker: Ihre Jobs je Check sind
  seit 12.10.2026 geloescht, "Depot pruefen" und "Watchlist pruefen" tragen. Dashboard: vorher
  klaeren, ob sein Kopf (Tagesbild, Allokation) auf die Depot-Kacheln wandert.

Offen fuer Erik: ob Marktdaten unter Einstellungen gehoert (heute auch zum Nachsehen einzelner Kurse
genutzt?).

## Uebrige KI-Knoepfe auf den Stern umstellen (11.10.2026)

Seit 11.10.2026 zeigt `core/ui/ki.py::ki_knopf` mit der Farbe des Sterns, ob ein Knopf lokal
oder in der Cloud rechnet; umgestellt sind erst Portfolio-Story und These auf der Seite
Positionen, dazu die Startknoepfe der Suche. Die Knoepfe auf der Titelseite folgen, wenn die Seite
das naechste Mal ohnehin dran ist -- vorher lohnt es nicht, weil manche Seite entfaellt.

