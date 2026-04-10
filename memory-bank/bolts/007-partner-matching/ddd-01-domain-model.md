---
stage: domain-model
bolt: 007-partner-matching
created: 2026-04-07T08:30:00Z
---

## Static Model: Partner Matching

### Entities

- **JournalLine**: `id`, `account_id`, `import_run_id`, `partner_id` (nullable), `valuta_date`, `booking_date`, `amount`, `currency`, `text`, `partner_name_raw`, `partner_iban_raw`, `unmapped_data`
  - Business Rule: `partner_id` wird beim Import durch den Matching-Algorithmus gesetzt
  - Business Rule: `partner_name_raw` und `partner_iban_raw` werden immer original gespeichert (unverändert)

- **Partner**: `id`, `mandant_id`, `name` (primary display name)
  - Business Rule: Partner sind Mandanten-isoliert (kein Cross-Tenant-Zugriff)
  - Business Rule: Automatisch angelegte Partner enthalten den raw-Namen der ersten Buchungszeile

- **PartnerIban**: `id`, `partner_id`, `iban`
  - Business Rule: Ein Partner kann mehrere IBANs haben
  - Business Rule: IBAN-Match ist exakt, keine Ähnlichkeitssuche

- **PartnerName**: `id`, `partner_id`, `name`
  - Business Rule: Name-Match ist case-insensitive (ILIKE)
  - Business Rule: Ein Partner kann mehrere Namen haben (Aliases)

- **ReviewItem**: `id`, `mandant_id`, `item_type`, `journal_line_id`, `context` (JSONB: partner_id, matched_name, raw_iban), `status`
  - Business Rule: Wird nur bei `partner_name_match` erzeugt — wenn Name-Match greift UND die Zeile eine IBAN enthält, die der Partner noch nicht hat
  - Business Rule: Zeilen ohne IBAN erzeugen bei Name-Match kein Review-Item
  - Business Rule: `status` beginnt als `open`

---

### Value Objects

- **Iban**: String (max 34 Zeichen), normalisiert (uppercase, ohne Leerzeichen)
  - Constraints: Leer-IBAN (`""`, `None`) = kein IBAN-Match-Versuch

- **PartnerMatchResult**: `partner_id` (UUID), `review_needed` (bool), `review_context` (optional dict)
  - Immutables Ergebnis der Matching-Logik; Input für JournalLine- und ReviewItem-Erstellung

- **MatchOutcome** (Enum):
  - `IBAN_MATCH` — sicherer Treffer via IBAN
  - `NAME_MATCH` — Treffer via case-insensitivem Namens-Match
  - `NEW_PARTNER` — kein Treffer, neuer Partner angelegt

---

### Aggregates

- **Partner** (Aggregate Root): Members: `PartnerIban`, `PartnerName`, `PartnerPattern`
  - Invariants: Alle zugehörigen IBANs und Namen gehören exklusiv zu diesem Partner im selben Mandanten
  - Invariants: Neue IBAN-Zuweisung muss Duplikat-Check innerhalb des Mandanten durchführen

- **ReviewItem** (Aggregate Root): Members: keiner
  - Invariants: `journal_line_id` ist Unique → max. 1 offenes Review-Item pro JournalLine

---

### Domain Events

- **PartnerCreatedFromImport**: Trigger: neuer Partner wurde durch Matching-Algorithmus angelegt — Payload: `partner_id`, `mandant_id`, `name`, `iban_raw`, `import_run_id`

- **ReviewItemCreated**: Trigger: Name-Match mit neuer IBAN — Payload: `review_item_id`, `journal_line_id`, `partner_id`, `raw_iban`

---

### Domain Services

- **PartnerMatchingService**: Führt den Matching-Algorithmus für eine einzelne Buchungszeile aus
  - Operations: `match(mandant_id, iban_raw, name_raw) → PartnerMatchResult`
  - Dependencies: `PartnerIbanRepository`, `PartnerNameRepository`
  - Algorithm:
    1. Wenn `iban_raw` nicht leer → suche via `PartnerIbanRepository.find_by_iban(mandant_id, iban)` → bei Treffer: `IBAN_MATCH`
    2. Suche via `PartnerNameRepository.find_by_name_ilike(mandant_id, name)` → bei Treffer: `NAME_MATCH`
    3. Kein Treffer → `NEW_PARTNER`, Partner anlegen

- **ReviewItemFactory**: Entscheidet ob und welches ReviewItem aus einem `PartnerMatchResult` erzeugt wird
  - Operations: `maybe_create(result, journal_line) → ReviewItem | None`
  - Regel: Nur wenn `result.outcome == NAME_MATCH` und `journal_line.partner_iban_raw` nicht leer

---

### Repository Interfaces

- **PartnerIbanRepository**:
  - Entity: `PartnerIban`
  - Methods: `find_by_iban(mandant_id: UUID, iban: str) → Partner | None`

- **PartnerNameRepository**:
  - Entity: `PartnerName`
  - Methods: `find_by_name_ilike(mandant_id: UUID, name: str) → Partner | None`

- **PartnerRepository**:
  - Entity: `Partner`
  - Methods: `create(mandant_id: UUID, name: str, iban: str | None) → Partner`

- **ReviewItemRepository**:
  - Entity: `ReviewItem`
  - Methods: `create(mandant_id: UUID, item_type: str, journal_line_id: UUID, context: dict) → ReviewItem`

---

### Ubiquitous Language

- **Partner-Matching**: Prozess, der automatisch die `partner_id` einer Buchungszeile setzt
- **IBAN-Match**: Sicherer Treffer wenn die IBAN der Buchungszeile bereits einem Partner zugeordnet ist
- **Name-Match**: Unsicherer Treffer via case-insensitivem Namensvergleich; kann Review-Item auslösen
- **New-Partner**: Fallback wenn kein Treffer; neuer Partner wird automatisch angelegt
- **Review-Item**: Datensatz, der einen Sachbearbeiter auf eine unsichere Entscheidung hinweist
- **partner_name_match**: Konkreter Review-Item-Typ für den Fall Name-Match + neue IBAN
- **Mandanten-Isolation**: Matching findet nur innerhalb desselben Mandanten statt; kein Cross-Tenant
