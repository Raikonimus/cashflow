---
id: 006-import-core
unit: 004-import-pipeline
intent: 001-cashflow-core
type: ddd-construction-bolt
status: complete
stories:
  - 001-csv-upload-endpoint
  - 002-mapping-application
  - 003-column-assignment-ui
  - 004-import-run-tracking
created: 2026-04-06T00:00:00Z
started: 2026-04-06T00:00:00Z
completed: 2026-04-07T00:00:00Z
current_stage: tests
stages_completed: [domain-model, technical-design, adr-analysis, implementation, tests]

requires_bolts: [003-tenant-account-mgmt]
enables_bolts: [007-partner-matching]
requires_units: []
blocks: false
---

# Bolt 006 – Import-Core

## Spaltenzuordnung (Column-Assignment-Modus)

Seit 2026-04-07 unterstützt das CSV-Mapping neben dem Legacy-Modus (ein Textfeld pro Zielspalte) einen geführten **Column-Assignment-Modus**:

### Ablauf
1. Benutzer lädt eine CSV-Datei im **MappingEditor** hoch.
2. Backend-Endpunkt `POST /column-mapping/preview` liest Header und gibt Spaltennamen zurück.
3. Für **jede** erkannte CSV-Spalte wählt der Benutzer per Dropdown ein Zielfeld:
   - `valuta_date` (Pflicht), `booking_date` (Pflicht), `amount` (Pflicht)
   - `partner_iban`, `partner_name`, `description` (optional)
   - `unused` – Spalte wird bewusst ignoriert
4. **Multi-Mapping**: Mehrere CSV-Spalten dürfen dasselbe Zielfeld bekommen → beim Import werden die Inhalte per Zeilenumbruch (`\n`) zusammengeführt, sortiert nach `sort_order`.
5. Zuordnung wird als JSON-Array `column_assignments` in `column_mapping_configs` gespeichert.
6. Legacy-Felder (`valuta_date_col`, `booking_date_col`, `amount_col` etc.) werden automatisch aus den Assignments abgeleitet (Rückwärtskompatibilität).

### Datenmodell
```
column_mapping_configs.column_assignments  (JSON, nullable)
  → [{source: string, target: ColumnTarget, sort_order: int}, ...]
```
Erlaubte `target`-Werte: `valuta_date | booking_date | amount | partner_iban | partner_name | description | unused`

### Duplikatlogik
Seit der erweiterten Spaltenzuordnung wird der Duplikatschlüssel ausschließlich aus jenen CSV-Spalten gebildet, die in `column_assignments` mit `duplicate_check=true` markiert sind.

- Die Rohwerte dieser ausgewählten CSV-Spalten werden intern in `journal_lines.unmapped_data._cashflow_source_values` gespeichert.
- Diese Struktur ist interne Import-Metadaten und gehört nicht in benutzerseitige API-Antworten oder Tooltips.
- Für Legacy-Bestandsdaten ohne `_cashflow_source_values` fällt die Importlogik auf gleichnamige top-level-Stringwerte in `unmapped_data` zurück, damit Altimporte weiterhin korrekt als Duplikate erkannt werden.

### API-Endpunkte
| Methode | Pfad | Zweck |
|---------|------|-------|
| POST | `/mandants/{m}/accounts/{a}/column-mapping/preview` | CSV-Header lesen (kein Import) |
| PUT  | `/mandants/{m}/accounts/{a}/column-mapping` | Mapping speichern (column_assignments oder Legacy) |
| GET  | `/mandants/{m}/accounts/{a}/column-mapping` | Bestehendes Mapping abrufen |

### Migration
- `009_add_column_assignments.py` – fügt `column_assignments JSON NULL` zur Tabelle hinzu.
