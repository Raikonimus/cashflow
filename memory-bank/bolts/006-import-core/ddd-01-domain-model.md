---
stage: domain-model
bolt: 006-import-core
created: 2026-04-06T00:00:00Z
---

# Domain Model: Import Core (Bolt 006)

## Bounded Context

**Import Pipeline** verarbeitet CSV-Datei-Uploads: Spalten werden gemäß konfiguriertem Column-Mapping extrahiert, Buchungszeilen (`JournalLine`) angelegt und Dubletten übersprungen. Partner-Matching (Bolt 007) wird hier noch **nicht** durchgeführt — `partner_id` bleibt zunächst `null`. Import-Runs protokollieren jeden Verarbeitungsvorgang (Dateiname, Anzahl Zeilen, Status, Fehler).

Bolt 006 schreibt Daten in `ImportRun` und `JournalLine`. Es liest von `ColumnMapping` (Bolt 003) und `Account` (Bolt 003).

---

## Entities

### ImportRun

Protokolliert einen einzelnen CSV-Import-Vorgang.

| Attribut | Typ | Constraint | Anmerkung |
|----------|-----|----------|-----------|
| id | UUID | PK | |
| account_id | UUID | FK accounts.id, INDEX | Welches Konto wird importiert |
| mandant_id | UUID | FK mandants.id, INDEX | Denormalisiert für schnelle Abfragen |
| user_id | UUID | FK users.id | Wer hat hochgeladen |
| filename | string | NOT NULL, max 255 | Originaler Dateiname |
| row_count | int | NOT NULL, default 0 | Erfolgreich importierte Zeilen |
| skipped_count | int | NOT NULL, default 0 | Übersprungene Dubletten |
| error_count | int | NOT NULL, default 0 | Zeilen mit Parsing-Fehlern |
| status | enum | NOT NULL | `pending` → `processing` → `completed` \| `failed` |
| error_details | JSONB | nullable | Liste von Zeilen-Fehlern bei `status=failed` |
| created_at | datetime | NOT NULL | |
| completed_at | datetime | nullable | Gesetzt wenn status=completed/failed |

**Invarianten:**
- Status-Übergänge: nur `pending → processing → completed` oder `pending → processing → failed`
- `row_count + skipped_count + error_count` ≤ Gesamtzeilen der CSV

---

### JournalLine

Eine einzelne Buchungszeile aus dem Import.

| Attribut | Typ | Constraint | Anmerkung |
|----------|-----|----------|-----------|
| id | UUID | PK | |
| account_id | UUID | FK accounts.id, INDEX | |
| import_run_id | UUID | FK import_runs.id, INDEX | |
| partner_id | UUID | FK partners.id, INDEX, nullable | `null` bis Bolt 007 Partner-Matching läuft |
| valuta_date | date | NOT NULL | Valutadatum |
| booking_date | date | NOT NULL | Buchungsdatum |
| amount | decimal(15,2) | NOT NULL | Betrag, negativ = Ausgabe |
| currency | string | NOT NULL, max 3, default 'EUR' | ISO 4217 |
| text | string | nullable, max 1000 | Buchungstext |
| partner_name_raw | string | nullable, max 500 | Roh-Partnername aus CSV |
| partner_iban_raw | string | nullable, max 34 | Roh-IBAN aus CSV (unnormalisiert) |
| unmapped_data | JSONB | nullable | Alle CSV-Spalten ohne Mapping |
| created_at | datetime | NOT NULL | |

**Dubletten-Kriterium** (für Skip-Logik):
`(account_id, valuta_date, booking_date, amount, partner_iban_raw, partner_name_raw)` ist UNIQUE pro Mandant.

**Invarianten:**
- `valuta_date` und `booking_date` als ISO 8601 DATE
- `amount` aus rohem CSV-String parsen; Parsing-Fehler → Zeile als error zählen

---

## Value Objects

### ImportStatus
Enum: `pending` | `processing` | `completed` | `failed`

### RowError
Enthält `row_number: int`, `error: str` — beschreibt warum eine Zeile nicht importiert werden konnte (z. B. `"amount: invalid decimal"`, `"required field 'booking_date' missing"`).

### MappedRow
Zwischenergebnis nach Anwenden des Column-Mappings auf eine einzelne CSV-Zeile:
- `fields: dict[str, str]` — Ziel-Felder mit extrahierten Werten
- `unmapped: dict[str, str]` — Spalten aus CSV ohne Mapping-Eintrag

---

## Aggregates

### ImportRunAggregate
**Root**: `ImportRun`
**Enthält**: `JournalLine[]` (1:n)

Ein `ImportRun` wird zuerst als `pending` angelegt. Erst nach vollständiger Verarbeitung aller Zeilen wird er auf `completed` oder `failed` gesetzt.

---

## Domain Services

### ImportService *(Haupt-Orchestrierung)*

```python
class ImportService:
    async def upload(
        self,
        actor: User,
        account_id: UUID,
        files: list[UploadFile],
    ) -> list[ImportRun]:
        """
        Für jede Datei:
        1. Account laden + prüfen ob ColumnMapping existiert → 422 wenn nicht
        2. ImportRun anlegen (status=pending)
        3. CSV parsen und Mapping anwenden
        4. JournalLines anlegen (Dubletten überspringen)
        5. ImportRun status=completed/failed setzen
        Returns: Liste der erstellten ImportRun-Objekte
        """
        ...

    async def get_run(self, actor: User, run_id: UUID) -> ImportRun: ...

    async def list_runs(
        self, actor: User, account_id: UUID, page: int, size: int
    ) -> tuple[list[ImportRun], int]: ...
```

### CsvMappingService *(CSV-Parsing + Mapping)*

```python
class CsvMappingService:
    def apply_mapping(
        self,
        row: dict[str, str],
        mappings: list[ColumnMapping],
    ) -> MappedRow:
        """
        Für jede ColumnMapping (sort_order aufsteigend):
        - Wert aus row[source_column] extrahieren
        - Mehrere source_columns auf gleiche target_column → Werte mit '\n' verbinden
        Nicht gemappte Spalten → unmapped
        """
        ...

    def validate_required_fields(self, mapped: MappedRow) -> list[RowError]:
        """
        Pflichtfelder: valuta_date, booking_date, amount
        Gibt RowError-Liste zurück (leer = OK)
        """
        ...
```

---

## Domain Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `ImportRunCreated` | `upload()` pro Datei | `run_id`, `account_id`, `filename` |
| `ImportRunCompleted` | Alle Zeilen verarbeitet | `run_id`, `row_count`, `skipped_count`, `error_count` |
| `ImportRunFailed` | Kritischer Fehler | `run_id`, `error_details` |

---

## Repository Interfaces

```python
class ImportRunRepository(Protocol):
    async def save(self, run: ImportRun) -> ImportRun: ...
    async def get_by_id(self, run_id: UUID) -> ImportRun | None: ...
    async def list_by_account(
        self, account_id: UUID, page: int, size: int
    ) -> tuple[list[ImportRun], int]: ...

class JournalLineRepository(Protocol):
    async def save_batch(self, lines: list[JournalLine]) -> int:
        """
        Bulk-Insert; gibt Anzahl der tatsächlich eingefügten Zeilen zurück.
        Duplikate (UNIQUE-Constraint) → ON CONFLICT DO NOTHING (als skipped zählen).
        """
        ...
    async def exists_duplicate(
        self,
        account_id: UUID,
        valuta_date: date,
        booking_date: date,
        amount: Decimal,
        partner_iban_raw: str | None,
        partner_name_raw: str | None,
    ) -> bool: ...
```

**Hinweis**: `JournalLineRepository` wird auch in Bolt 005 (reassign_partner) referenziert. Das Interface wird dort erweitert.

### Dependency auf Bolt 003

```python
class ColumnMappingRepository(Protocol):
    # Bereits durch Bolt 003 implementiert
    async def list_by_account(self, account_id: UUID) -> list[ColumnMapping]: ...
```

---

## Geschäftsregeln

| Regel | Beschreibung |
|-------|-------------|
| Kein Mapping → 422 | Konto ohne ColumnMapping kann nicht importiert werden |
| Dateityp-Prüfung | Nur `Content-Type: text/csv` oder Dateiendung `.csv` werden akzeptiert → 422 |
| Dubletten-Skip | Zeile mit identischem Schlüssel in account wird übersprungen (kein Fehler) |
| Atomarität pro Datei | Jede Datei ist eine eigene Transaktion; eine Datei scheitert nicht die anderen |
| partner_id = null | In Bolt 006 werden noch keine Partner zugeordnet — das folgt in Bolt 007 |

---

## Ubiquitäres Vokabular

| Begriff | Definition |
|---------|-----------|
| **ImportRun** | Protokollobjekt für einen einzelnen CSV-Verarbeitungsvorgang |
| **JournalLine** | Eine importierte Buchungszeile (Transaktion) |
| **ColumnMapping** | Konfiguration wie CSV-Spalten auf JournalLine-Felder abgebildet werden (→ Bolt 003) |
| **MappedRow** | Zwischenergebnis nach Mapping-Anwendung auf eine CSV-Zeile |
| **unmapped_data** | JSONB-Feld mit CSV-Spalten ohne Mapping-Konfiguration |
| **Dublette** | Buchungszeile mit identischen Schlüsselfeldern — wird übersprungen |
| **skipped_count** | Anzahl übersprungener Dubletten pro ImportRun |
| **error_count** | Anzahl Zeilen die wegen ungültiger Daten nicht importiert werden konnten |
| **partner_name_raw** | Roh-Partnername aus CSV, unverändert gespeichert für späteres Matching |
| **partner_iban_raw** | Roh-IBAN aus CSV, unverändert für späteres Matching (Normalisierung in Bolt 007) |
