# Architektur-Plan V2: Wealth Management Refactor

Stand: 2026-03-28

---

## Entscheidungen (abgestimmt)

| Thema | Entscheidung |
|---|---|
| Portfolio/Watchlist | Eine `positions` Tabelle mit `in_portfolio` Flag |
| Asset-Typen | YAML-Config (`config/asset_classes.yaml`), nicht hardcoded |
| Krypto / Anleihen | Werden nicht migriert, können später in YAML ergänzt werden |
| Dashboard / Analysen | Zeigen nur Investment-Typen, die tatsächlich im Portfolio vorhanden sind |
| ISIN→Ticker | OpenFIGI API (kostenlos, kein Key, ISIN ist unkritisch ohne Stückzahl) |
| Kursquelle | yfinance, pro Asset-Klasse konfigurierbar |
| Edelmetalle | yfinance: GC=F (Gold), SI=F (Silber) |
| Config-Format | YAML |

---

## Implementierungs-Phasen

### Phase 1 — Foundation (Datenmodell, kein App-Code)
1. `config/asset_classes.yaml` anlegen
2. `core/asset_class_config.py` (YAML-Loader, `AssetClassConfig` Pydantic-Modell)
3. `core/storage/models.py` — neues `Position`-Modell ersetzt `PortfolioEntry` + `WatchlistEntry`
4. `core/storage/positions.py` — `PositionsRepository`
5. Unit-Tests für alle neuen Komponenten

### Phase 2 — Migration
1. `scripts/migrate_to_positions.py`
2. Migrations-Integrationstests
3. Migration auf Entwicklungskopie der DB ausführen und validieren

### Phase 3 — UI (vor Agents, damit schon was sichtbar ist)
1. `app.py` auf `st.navigation` umstellen mit gruppierten Sektionen
2. Seiten umbenennen (ohne Nummernpräfix)
3. Alle Seiten auf `PositionsRepository` + `Position`-Modell umstellen
4. ISIN-Ticker-Auflösung im Formular
5. Dashboard/Analysen: nur vorhandene Investment-Typen anzeigen

### Phase 4 — Agents & Marktdaten
1. `fetch_historical_range(symbol, start, end)` in `MarketDataFetcher`
2. `fill_gaps_on_startup()` in `MarketDataAgent` (Exchange-Kalender via `exchange-calendars`)
3. `exchange`-Spalte in den Preistabellen
4. `core/isin_resolver.py` (OpenFIGI → yfinance-Fallback → manuell)
5. `PortfolioAgent` Tool-Definitionen auf neues Modell aktualisieren
6. `state.py` verdrahten: `PositionsRepository`, Gap-Fill-Aufruf beim Start

---

## Datenbankschema: `positions`

```sql
CREATE TABLE IF NOT EXISTS positions (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Klassifikation (Klartext)
    asset_class           TEXT NOT NULL,       -- aus YAML, z.B. "Aktie", "Edelmetall"
    investment_type       TEXT NOT NULL,       -- aus Asset-Klasse, z.B. "Wertpapiere"
    -- Identifikatoren (Klartext)
    name                  TEXT NOT NULL,
    isin                  TEXT,
    wkn                   TEXT,
    ticker                TEXT,               -- aufgelöst oder manuell; NULL = ausstehend
    -- Finanzdaten (VERSCHLÜSSELT)
    quantity              TEXT,               -- Fernet; NULL bei Watchlist
    unit                  TEXT NOT NULL,      -- z.B. "Stück", "Troy Oz", "g"
    purchase_price        TEXT,               -- Fernet; optional
    purchase_date         TEXT,               -- ISO-8601; optional
    -- Metadaten (VERSCHLÜSSELT)
    notes                 TEXT,               -- Fernet
    extra_data            TEXT,               -- Fernet über JSON-Blob
    -- Herkunft (Klartext)
    recommendation_source TEXT,               -- Freitext, z.B. "Börsenbrief XY", "Agent:momentum"
    strategy              TEXT,               -- Freitext, z.B. "10 Jahre Halten"
    added_date            TEXT NOT NULL,      -- Erstellungsdatum ISO-8601
    -- Status (Klartext)
    in_portfolio          INTEGER NOT NULL DEFAULT 0  -- 0=Watchlist, 1=Portfolio
);
```

**Verschlüsselte Felder:** `quantity`, `purchase_price`, `notes`, `extra_data`

---

## YAML Asset-Klassen (Beispiel)

```yaml
# config/asset_classes.yaml

asset_classes:

  Aktie:
    investment_type: Wertpapiere
    default_unit: Stück
    visible_fields: [isin, wkn, ticker, quantity, purchase_price, purchase_date,
                     recommendation_source, strategy, notes]
    price_source: yfinance
    requires_ticker: true

  Aktienfonds:
    investment_type: Wertpapiere
    default_unit: Stück
    visible_fields: [isin, wkn, ticker, quantity, purchase_price, purchase_date,
                     strategy, notes]
    price_source: yfinance
    requires_ticker: true

  Immobilienfonds:
    investment_type: Immobilien
    default_unit: Stück
    visible_fields: [isin, wkn, ticker, quantity, purchase_price, purchase_date,
                     strategy, notes]
    price_source: yfinance
    requires_ticker: true

  Edelmetall:
    investment_type: Edelmetalle
    default_unit: Troy Oz
    unit_options: [Troy Oz, g]
    visible_fields: [ticker, quantity, unit, purchase_price, purchase_date, notes]
    price_source: yfinance
    requires_ticker: true
```

---

## `PositionsRepository` Interface

```python
class PositionsRepository:
    def add(self, position: Position) -> Position
    def get(self, position_id: int) -> Optional[Position]
    def get_all(self) -> list[Position]
    def get_portfolio(self) -> list[Position]
    def get_watchlist(self) -> list[Position]
    def update(self, position: Position) -> bool
    def delete(self, position_id: int) -> bool
    def promote_to_portfolio(
        self, position_id: int, quantity: float,
        purchase_price: Optional[float], purchase_date: date
    ) -> Optional[Position]
    def get_by_ticker(self, ticker: str) -> list[Position]
    def get_tickers_for_price_fetch(self) -> list[str]  # dedupliziert, ohne NULL
```

---

## Gap-Filling Algorithmus

1. Alle Ticker via `positions_repo.get_tickers_for_price_fetch()` holen
2. Pro Ticker: letztes gespeichertes Datum aus `historical_prices` lesen
3. Fehlende Börsentage berechnen via `exchange_calendars.get_calendar("XETR")`
4. Fehlende Range laden via `fetcher.fetch_historical_range(ticker, start, end)`
5. Ergebnisse in `historical_prices` upserten
6. Börsenplatz wird pro Datensatz mitgespeichert

---

## UI-Struktur

```
Sidebar:
  Dashboard
  Analysen
  ──────────────
  Chat Agents     (Platzhalter)
  Bot Agents      (Platzhalter)
  ──────────────
  Portfolio Chat
  Marktdaten
  Agentmonitor
```

Implementiert mit `st.navigation()` und Gruppen-Dict in `app.py`.

---

## Test-Strategie

### Neue Tests
- `tests/unit/test_positions_repository.py` — ersetzt test_portfolio + test_watchlist
- `tests/unit/test_asset_class_config.py` — YAML-Parsing, Validierung
- `tests/unit/test_isin_resolver.py` — OpenFIGI (Mock), Fallback, Timeout
- `tests/unit/test_market_data_gap_fill.py` — Gap-Fill-Logik, Kalender-Mock
- `tests/integration/test_positions_migration.py` — Migration mit In-Memory-DB

### Anzupassen
- `test_market_data_agent.py` — Position-Modell, neue Methoden
- `test_market_data_fetcher.py` — `fetch_historical_range`
- `test_e2e.py` — auf `positions` Tabelle umstellen

### Zu löschen (nach vollständiger Migration)
- `tests/unit/test_portfolio.py`
- `tests/unit/test_watchlist.py`
