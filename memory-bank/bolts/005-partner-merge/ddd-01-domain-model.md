---
stage: domain-model
bolt: 005-partner-merge
created: 2026-04-06T00:00:00Z
---

# Domain Model: Partner Merge (Bolt 005)

## Bounded Context

**Partner Merge** ist ein Subdienst innerhalb von Partner Management. Er fügt zwei zuvor getrennte Partner-Aggregate zusammen: Alle IBANs, Namensvarianten und Muster des Quell-Partners (source) werden auf den Ziel-Partner (target) übertragen, alle Buchungszeilen werden umgeschrieben und der Quell-Partner wird deaktiviert. Der gesamte Vorgang ist atomar (eine Transaktion).

Baut auf dem Partner-Domain-Modell aus Bolt 004 auf. Fügt ausschließlich das Merge-Verhalten und einen Audit-Log-Eintrag hinzu.

---

## Entities

### Partner (erweitert aus Bolt 004)

Keine neuen Felder. Die Merge-Operation setzt `is_active = false` auf dem source Partner.

---

### AuditLogEntry *(neu)*

Protokolliert fachlich relevante Änderungen. Wird zuerst im Merge-Kontext benötigt, ist aber als generisches Querschnittsmodell konzipiert.

| Attribut | Typ | Constraint | Anmerkung |
|----------|-----|----------|-----------|
| id | UUID | PK | |
| mandant_id | UUID | FK mandants.id, INDEX | Mandanten-Scoping |
| event_type | string | NOT NULL, max 100 | z. B. `"partner.merged"` |
| actor_id | UUID | FK users.id | Wer hat die Aktion ausgeführt |
| payload | JSONB | NOT NULL | Fachliche Datenänderung (vor/nach) |
| created_at | datetime | NOT NULL | |

**Invarianten:**
- AuditLogEntry ist immutable – nach dem Anlegen keine Updates
- `payload` enthält mindestens `{ "source_partner_id": ..., "target_partner_id": ..., "lines_reassigned": N }`

---

## Value Objects

### MergeRequest
Enthält `source_id: UUID` und `target_id: UUID`.

**Invariante**: `source_id ≠ target_id` → sonst `400 Bad Request`

### MergeResult
Enthält `target: Partner`, `lines_reassigned: int`, `audit_log_id: UUID`.

---

## Aggregates

### PartnerAggregate (erweitert)
**Root**: `Partner`

Der Ziel-Partner nimmt alle Kinder des Quell-Partners auf. Duplikate werden lautlos dedupliziert (kein Fehler):
- `PartnerIban`: IBAN bereits auf target vorhanden → überspringen
- `PartnerName`: Namensvariante bereits auf target vorhanden → überspringen
- `PartnerPattern`: Pattern + match_field bereits auf target vorhanden → überspringen

---

## Domain Services

### PartnerMergeService *(neu)*

```python
class PartnerMergeService:
    async def merge(
        self,
        actor: User,
        mandant_id: UUID,
        source_id: UUID,
        target_id: UUID,
    ) -> MergeResult:
        ...
```

**Ablauf (vollständig in einer DB-Transaktion):**

1. Validierungen:
   - `source_id ≠ target_id` → 400
   - Beide Partner müssen zum gleichen Mandanten gehören → 403
   - Beide Partner müssen active sein → 404 wenn nicht gefunden oder inaktiv
   - Actor muss mindestens `accountant` sein → 403

2. Kinder übertragen:
   - Alle `PartnerIban` von source → target (Duplikate ignorieren)
   - Alle `PartnerName` von source → target (Duplikate ignorieren)
   - Alle `PartnerPattern` von source → target (Duplikate ignorieren)

3. Buchungszeilen umschreiben:
   - `UPDATE journal_lines SET partner_id = target_id WHERE partner_id = source_id AND account_id IN (SELECT id FROM accounts WHERE mandant_id = mandant_id)`
   - Gibt Anzahl betroffener Zeilen zurück (`lines_reassigned`)

4. Source deaktivieren:
   - `source.is_active = false`, `source.updated_at = now()`

5. Audit-Log schreiben:
   - `AuditLogEntry(event_type="partner.merged", actor_id, payload={source_partner_id, target_partner_id, lines_reassigned})`

6. Ergebnis zurückgeben: `MergeResult`

---

## Domain Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `PartnersMerged` | `merge()` | `source_id`, `target_id`, `lines_reassigned`, `actor_id` |

---

## Repository Interfaces

```python
class JournalLineRepository(Protocol):
    async def reassign_partner(
        self,
        source_id: UUID,
        target_id: UUID,
        mandant_id: UUID,
    ) -> int:
        """
        UPDATE journal_lines SET partner_id = target_id
        WHERE partner_id = source_id
          AND account_id IN (SELECT id FROM accounts WHERE mandant_id = :mandant_id)
        Returns: Anzahl umgeschriebener Zeilen
        """
        ...

class AuditLogRepository(Protocol):
    async def save(self, entry: AuditLogEntry) -> AuditLogEntry: ...
    async def list_by_mandant(
        self, mandant_id: UUID, page: int, size: int
    ) -> tuple[list[AuditLogEntry], int]: ...
```

---

## Ubiquitäres Vokabular

| Begriff | Definition |
|---------|-----------|
| **Source Partner** | Der Partner der aufgelöst wird; wird nach dem Merge deaktiviert |
| **Target Partner** | Der Partner der die Daten und Buchungszeilen des source übernimmt |
| **Merge** | Atomare Operation: Kinder übertragen + Buchungszeilen umschreiben + source deaktivieren |
| **lines_reassigned** | Anzahl der Buchungszeilen, deren `partner_id` von source auf target geändert wurde |
| **Deduplizierung** | Stilles Ignorieren doppelter IBANs/Namen/Patterns beim Merge (kein Fehler) |
| **AuditLogEntry** | Unveränderlicher Protokolleintrag einer fachlichen Änderung |

---

## Abgrenzung zu Bolt 004

Bolt 004 hat den Partner-Core implementiert (CRUD, IBANs, Namen, Pattern). Bolt 005 fügt ausschließlich hinzu:
- `PartnerMergeService` mit der Merge-Logik
- `AuditLogEntry` Entität + `AuditLogRepository`
- `JournalLineRepository.reassign_partner()` (neuer Schnittstellenbeitrag)
- API-Endpunkt `POST /partners/:target_id/merge`

Keine Änderungen an bestehenden Entitäten oder Services aus Bolt 004.
