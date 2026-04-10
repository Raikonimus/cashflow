# Stage 1: Domain Model — Bolt 009 Journal & Audit

## Ubiquitous Language

| Begriff | Definition |
|---|---|
| **JournalLine** | Eine importierte Buchungszeile mit Betrag, Datum, Partner und Buchungstext |
| **Journal** | Die Gesamtheit aller JournalLines eines Mandanten |
| **Journal-Filter** | Kombination aus account_id, partner_id, year, month, has_partner |
| **Bulk-Assign** | Aktion: mehrere JournalLines gleichzeitig einem Partner zuweisen |
| **AuditLog** | Unveränderlicher Event-Eintrag; dokumentiert Benutzeraktionen |
| **Audit-Viewer** | Benutzer mit mindestens mandant_admin-Rolle; kann AuditLog lesen |

---

## Entitäten (bestehend — keine neue Tabelle nötig)

### JournalLine (app/imports/models.py)

Bestehende Entität, wird nur abgefragt und bei Bulk-Assign aktualisiert.

Relevante Filter-Felder:
- `mandant_id` (via account_id → accounts.mandant_id Join oder Import-Run)
- `account_id` — direkt
- `partner_id` — direkt (NULL = kein Partner, für `has_partner=false`)
- `valuta_date` — ISO-String `YYYY-MM-DD`; Filter via string-Präfix (`LIKE '2025-%'`)

### AuditLog (app/partners/models.py)

Bestehende Entität, bereits mit `AuditLogService` in `app/partners/service.py`.

Für Bolt 009: **Kein neues Modell** — der bestehende `AuditLogService` wird per eigenem
Router-Endpunkt unter `/api/v1/mandants/{mandant_id}/audit` exponiert.

---

## Domain Services

### JournalService (neu: app/journal/service.py)

```
list_lines(mandant_id, filters, page, size) → (list[JournalLine], total)
bulk_assign(mandant_id, line_ids, partner_id, actor_id) → BulkAssignResult
```

**Invarianten:**
1. `list_lines`: nur Zeilen deren `account_id` zu `mandant_id` gehört (Security)
2. `bulk_assign`: jede `line_id` muss zu einer `account_id` des Mandanten gehören → Fremd-IDs werden als 403 abgewiesen (Story AC 2)
3. `bulk_assign` schreibt **einen** `AuditLog`-Eintrag pro Aufruf (nicht pro Zeile)

### AuditLogService (bestehend: app/partners/service.py)

Wird unverändert wiederverwendet. Ein neuer `audit_router` exponiert ihn:
- Admin: mandant_id-unabhängig (alle Einträge)
- Mandant-Admin: nur eigener Mandant

---

## Filter-Modell (JournalFilter)

```python
@dataclass
class JournalFilter:
    account_id: UUID | None
    partner_id: UUID | None
    year: int | None
    month: int | None
    has_partner: bool | None  # True = nur mit Partner, False = nur ohne
```

---

## Neue Dateien

| Datei | Inhalt |
|---|---|
| `app/journal/__init__.py` | leer |
| `app/journal/service.py` | `JournalService` |
| `app/journal/schemas.py` | `JournalLineResponse`, `PaginatedJournalResponse`, `BulkAssignRequest`, `BulkAssignResponse` |
| `app/journal/router.py` | `journal_router` + `audit_router` |

Kein neues Modell, keine neue Migration nötig.

---

## RBAC

| Endpunkt | Mindestrolle |
|---|---|
| GET /journal | viewer |
| POST /journal/bulk-assign | accountant |
| GET /audit | mandant_admin (Admin überschreibt) |
