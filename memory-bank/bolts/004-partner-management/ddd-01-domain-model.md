---
stage: domain-model
bolt: 004-partner-management
created: 2026-04-06T00:00:00Z
---

# Domain Model: Partner Core (Bolt 004)

## Bounded Context

**Partner Management** verwaltet die Stammdaten von Geschäftspartnern (Counterparties): Name, IBAN-Zuordnungen, Namensvarianten und automatische Erkennungsmuster. Partner sind mandantenspezifisch. Sie werden beim Import von Buchungen automatisch über Muster erkannt.

---

## Entities

### Partner

Repräsentiert einen Geschäftspartner (z. B. "Amazon EU S.a.r.l.").

| Attribut | Typ | Constraint | Anmerkung |
|----------|-----|-----------|-----------|
| id | UUID | PK | |
| mandant_id | UUID | FK mandants.id, INDEX | Pflicht-Zuordnung |
| name | string | NOT NULL, max 255 | Primärname (kanonisch) |
| is_active | bool | default true | Inaktive Partner werden beim Matching ignoriert |
| created_at | datetime | NOT NULL | |
| updated_at | datetime | NOT NULL | |

**Invarianten:**
- Viewer-Rolle → kein Schreibzugriff (403)
- Name muss innerhalb eines Mandanten einzigartig sein (409)

---

### PartnerIban

Eine IBAN die einem Partner zugeordnet wird.

| Attribut | Typ | Constraint | Anmerkung |
|----------|-----|-----------|-----------|
| id | UUID | PK | |
| partner_id | UUID | FK partners.id, INDEX | |
| iban | string | NOT NULL, max 34, UNIQUE global | Normalisiert (keine Leerzeichen, Großbuchstaben) |
| created_at | datetime | NOT NULL | |

**Invarianten:**
- IBAN UNIQUE über alle Partner aller Mandanten (eine IBAN gehört immer genau einem Partner)
- Wenn IBAN bereits einem anderen Partner zugeordnet ist → 409

---

### PartnerName

Eine Namensvariante eines Partners (z. B. "AMZ MARKETPLACE", "Amazon Payments").

| Attribut | Typ | Constraint | Anmerkung |
|----------|-----|-----------|-----------|
| id | UUID | PK | |
| partner_id | UUID | FK partners.id, INDEX | |
| name | string | NOT NULL, max 255 | Variante |
| created_at | datetime | NOT NULL | |

**Invarianten:**
- Namensvariante UNIQUE pro Partner (409 bei Duplikat innerhalb desselben Partners)
- Gleichlautender Name bei zwei verschiedenen Partnern erlaubt

---

### PartnerPattern

Ein automatisches Erkennungsmuster für den Import-Matching-Algorithmus.

| Attribut | Typ | Constraint | Anmerkung |
|----------|-----|-----------|-----------|
| id | UUID | PK | |
| partner_id | UUID | FK partners.id, INDEX | |
| pattern | string | NOT NULL, max 500 | Muster-String oder Regex |
| pattern_type | enum | NOT NULL | `"string"` oder `"regex"` |
| match_field | enum | NOT NULL | `"description"`, `"partner_name"`, `"partner_iban"` |
| created_at | datetime | NOT NULL | |

**Invarianten:**
- Bei `pattern_type = "regex"`: Muster muss `re.compile()` bestehen → 422 bei ungültigem Regex
- Muster UNIQUE pro Partner + match_field Kombination

---

## Value Objects

### PartnerPatternType
Enum: `string` | `regex`

### MatchField
Enum: `description` | `partner_name` | `partner_iban`
Legt fest gegen welches Buchungsfeld das Muster geprüft wird.

### NormalizedIban
IBAN ohne Leerzeichen, Großbuchstaben. Beispiel: `"DE89 3704 0044 0532 0130 00"` → `"DE89370400440532013000"`.

---

## Aggregates

### PartnerAggregate
**Root**: `Partner`
**Enthält**: `PartnerIban[]`, `PartnerName[]`, `PartnerPattern[]`

Alle IBANs, Namensvarianten und Muster können nur über das Partner-Aggregate hinzugefügt/entfernt werden.

---

## Domain Services

### PartnerQueryService
- `list_partners(actor: User, mandant_id: UUID, page: int, size: int) → Page[Partner]`
  - Viewer darf lesen
  - Gibt paginierten Partner-Response mit IBAN-Anzahl, Namensvarianten-Anzahl und Pattern-Anzahl zurück

### PartnerWriteService
- `create_partner(actor: User, mandant_id: UUID, name: str, iban: str | None) → Partner`
  - Mindestens `name` Pflicht; `iban` optional, sofort als `PartnerIban` gespeichert
  - Actor muss mindestens `accountant` sein (≥ Accountant)
- `add_iban(actor: User, partner_id: UUID, iban: str) → PartnerIban`
  - Prüft Eindeutigkeit global; 409 wenn belegt
- `add_name(actor: User, partner_id: UUID, name: str) → PartnerName`
  - Prüft Eindeutigkeit innerhalb des Partners; 409 wenn Duplikat
- `add_pattern(actor: User, partner_id: UUID, pattern: str, pattern_type: str, match_field: str) → PartnerPattern`
  - Bei `regex`: `re.compile(pattern)` Validierung; 422 bei Fehler
- `delete_pattern(actor: User, pattern_id: UUID) → None`

---

## Domain Events

| Event | Trigger | Beschreibung |
|-------|---------|-------------|
| `PartnerCreated` | `create_partner()` | Neuer Partner angelegt |
| `PartnerIbanAdded` | `add_iban()` | IBAN einem Partner zugeordnet |
| `PartnerNameAdded` | `add_name()` | Namensvariante hinzugefügt |
| `PartnerPatternAdded` | `add_pattern()` | Erkennungsmuster hinzugefügt |
| `PartnerPatternDeleted` | `delete_pattern()` | Muster gelöscht |

---

## Repository Interfaces

```python
class PartnerRepository(Protocol):
    async def get_by_id(self, partner_id: UUID) -> Partner | None: ...
    async def list_by_mandant(
        self, mandant_id: UUID, page: int, size: int
    ) -> tuple[list[Partner], int]: ...
    async def save(self, partner: Partner) -> Partner: ...

class PartnerIbanRepository(Protocol):
    async def get_by_iban(self, iban: str) -> PartnerIban | None: ...
    async def save(self, entity: PartnerIban) -> PartnerIban: ...

class PartnerNameRepository(Protocol):
    async def get_by_partner_and_name(
        self, partner_id: UUID, name: str
    ) -> PartnerName | None: ...
    async def save(self, entity: PartnerName) -> PartnerName: ...

class PartnerPatternRepository(Protocol):
    async def get_by_id(self, pattern_id: UUID) -> PartnerPattern | None: ...
    async def list_by_partner(self, partner_id: UUID) -> list[PartnerPattern]: ...
    async def save(self, entity: PartnerPattern) -> PartnerPattern: ...
    async def delete(self, pattern_id: UUID) -> None: ...
```

---

## Ubiquitäres Vokabular

| Begriff | Definition |
|---------|-----------|
| **Partner** | Ein Geschäftspartner (Counterparty) einer Buchung; z. B. Lieferant oder Kunde |
| **PartnerIban** | Eine bekannte IBAN des Partners; wird beim Import direkt gematcht |
| **PartnerName** | Eine Namensvariante; wird beim Import gegen den Buchungs-Partnernamen verglichen |
| **PartnerPattern** | Ein String- oder Regex-Muster; wird beim Import gegen ein Buchungsfeld geprüft |
| **Matching** | Automatische Zuordnung: Bank-Buchung → Partner anhand IBAN, Name oder Pattern |
| **Remapping** | Wiederholtes Matching bereits importierter Buchungen (ausgelöst via Bolt 003) |
