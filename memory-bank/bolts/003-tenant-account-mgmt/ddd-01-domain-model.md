---
stage: domain-model
bolt: 003-tenant-account-mgmt
created: 2026-04-06T00:00:00Z
---

# Domain Model: Tenants & Accounts (Bolt 003)

## Bounded Context

**Tenant & Account Management** verantwortet die vollständige Konfiguration eines Mandanten: seine Stammdaten, die zugehörigen Bankkonten sowie die Konfiguration, wie CSV-Spalten auf Buchungsfelder gemappt werden.

---

## Entities

### Mandant *(in Bolt 001 als Stub eingeführt — hier vollständig)*

| Attribut | Typ | Constraint | Anmerkung |
|----------|-----|-----------|-----------|
| id | UUID | PK | |
| name | string | NOT NULL, max 255 | Firmenname |
| is_active | bool | default true | Deaktivierung sperrt alle User-Zugriffe |
| created_at | datetime | NOT NULL | |
| updated_at | datetime | NOT NULL | |

**Invarianten:**
- Nur Admin darf Mandanten anlegen/deaktivieren
- Deaktivierung eines Mandanten macht alle zugehörigen Konten inaktiv (CASCADE)

---

### Account (Bankkonto)

Repräsentiert ein Bankkonto eines Mandanten.

| Attribut | Typ | Constraint | Anmerkung |
|----------|-----|-----------|-----------|
| id | UUID | PK | |
| mandant_id | UUID | FK mandants.id, INDEX | Pflicht-Zuordnung |
| name | string | NOT NULL, max 255 | Anzeigename (z. B. "Girokonto DE89...") |
| iban | string | max 34, UNIQUE | Optional — kann leer sein |
| currency | string | max 3, default "EUR" | ISO 4217 |
| is_active | bool | default true | |
| created_at | datetime | NOT NULL | |
| updated_at | datetime | NOT NULL | |

**Invarianten:**
- IBAN muss wenn angegeben UNIQUE über alle Accounts sein
- Ein Account gehört immer genau einem Mandanten

---

### ColumnMappingConfig

Definiert wie CSV-Spalten einer Bankexport-Datei auf Buchungsfelder gemappt werden. Jede Konfiguration gehört zu einem Account (da verschiedene Banken unterschiedliche Exportformate haben).

| Attribut | Typ | Constraint | Anmerkung |
|----------|-----|-----------|-----------|
| id | UUID | PK | |
| account_id | UUID | FK accounts.id, UNIQUE INDEX | 1:1 pro Account |
| valuta_date_col | string | NOT NULL | Spaltenname/Index |
| booking_date_col | string | NOT NULL | |
| amount_col | string | NOT NULL | |
| partner_iban_col | string | nullable | |
| partner_name_col | string | nullable | |
| description_col | string | nullable | |
| decimal_separator | string | max 1, default "," | "," oder "." |
| date_format | string | default "%d.%m.%Y" | strptime-Format |
| encoding | string | default "utf-8" | CSV-Encoding |
| delimiter | string | max 5, default ";" | CSV-Delimiter |
| skip_rows | int | default 0 | Kopfzeilen überspringen |
| created_at | datetime | NOT NULL | |
| updated_at | datetime | NOT NULL | |

**Invarianten:**
- Je Account genau eine aktive ColumnMappingConfig
- `valuta_date_col`, `booking_date_col`, `amount_col` sind Pflichtfelder

---

## Value Objects

### Currency
`string` — ISO 4217. Validierung: 3-buchstabiger Großbuchstaben-Code. Default: `"EUR"`.

### IBAN
`string` — Optional. Wenn gesetzt: Format-Validierung (DE-IBAN: DE + 20 Zeichen). Normalisierung: Leerzeichen entfernen, Großbuchstaben.

### DateFormat
`string` — Python strptime-Formatstring. Validierung: testweises Parsen eines Dummy-Datums, um sicherzustellen, dass das Format gültig ist.

### RemappingStatus
Enum für den Zustand eines Re-Mapping-Auftrags:
- `pending` — angefordert, noch nicht verarbeitet
- `running` — läuft gerade
- `complete` — fertig
- `failed` — Fehler

---

## Aggregates

### MandantAggregate
**Root**: `Mandant`
- Enthält keine Sub-Entities (Accounts sind eigenständige Aggregate)
- Invariante: Deaktivierung muss alle Accounts kaskadieren

### AccountAggregate
**Root**: `Account`
**Enthält**: `ColumnMappingConfig` (1:1, gehört nur zu diesem Account)
- Mapping-Config kann nur über Account-Aggregate verändert werden
- Invariante: Mapping-Config muss vorhanden sein bevor ein Import gestartet werden kann

---

## Domain Services

### MandantService
- `create_mandant(admin: User, name: str) → Mandant`
- `update_mandant(admin: User, mandant_id: UUID, patch: dict) → Mandant`
- `deactivate_mandant(admin: User, mandant_id: UUID) → None`
  - setzt `is_active = false` auf Mandant UND alle zugehörigen Accounts

### AccountService
- `create_account(actor: User, mandant_id: UUID, data: dict) → Account`
  - prüft Mandant-Zugriff (Admin oder MandantUser)
- `update_account(actor: User, account_id: UUID, patch: dict) → Account`
- `set_column_mapping(actor: User, account_id: UUID, config: dict) → ColumnMappingConfig`
  - `UPSERT` — erstellt oder überschreibt bestehende Config
- `get_column_mapping(account_id: UUID) → ColumnMappingConfig | None`

### RemappingService
- `trigger_remapping(actor: User, account_id: UUID) → None`
  - Erstellt einen `RemappingJob`-Eintrag (Status: `pending`)
  - Eigentliche Re-Matching-Logik liegt in Unit 004/005 (Import-Pipeline / Partner-Matching)
  - In diesem Bolt: nur Trigger + Status-Tracking

---

## Domain Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `MandantCreated` | `create_mandant()` | mandant_id, name |
| `MandantDeactivated` | `deactivate_mandant()` | mandant_id |
| `AccountCreated` | `create_account()` | account_id, mandant_id |
| `ColumnMappingConfigured` | `set_column_mapping()` | account_id |
| `RemappingTriggered` | `trigger_remapping()` | account_id, triggered_by |

---

## Repository Interfaces

```python
class MandantRepository(Protocol):
    async def get_by_id(self, mandant_id: UUID) -> Mandant | None: ...
    async def list_all(self) -> list[Mandant]: ...
    async def save(self, mandant: Mandant) -> Mandant: ...

class AccountRepository(Protocol):
    async def get_by_id(self, account_id: UUID) -> Account | None: ...
    async def list_by_mandant(self, mandant_id: UUID) -> list[Account]: ...
    async def save(self, account: Account) -> Account: ...

class ColumnMappingConfigRepository(Protocol):
    async def get_by_account(self, account_id: UUID) -> ColumnMappingConfig | None: ...
    async def save(self, config: ColumnMappingConfig) -> ColumnMappingConfig: ...
```

---

## Ubiquitäres Vokabular

| Begriff | Definition |
|---------|-----------|
| **Mandant** | Eine Firma/Organisation die Cashflow nutzt; Admin-verwaltete Einheit |
| **Account** | Ein Bankkonto eines Mandanten (Girokonto, Tagesgeld etc.) |
| **Column Mapping** | Konfiguration die CSV-Spalten auf Buchungsfelder abbildet |
| **Remapping** | Neuausführung des Partner-Matching für bereits importierte Buchungen (nach Änderung der Mapping-Config oder Partner-Stammdaten) |
| **Delimiter** | Trennzeichen in der CSV-Datei (häufig `;` oder `,`) |
