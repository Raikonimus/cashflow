# Stage 2: Technical Design — Bolt 008 Review Queue

## Layered Architecture

```
HTTP Request
    ↓
app/review/router.py          ← FastAPI Router (Endpunkte, Pydantic-Validierung)
    ↓
app/review/service.py         ← ReviewService (Domänenlogik, DB-Koordination)
    ↓
app/imports/models.py         ← ReviewItem, JournalLine (bestehend, wird erweitert)
app/partners/models.py        ← Partner, PartnerIban, AuditLog (bestehend)
```

Neues Feature-Verzeichnis: `backend/app/review/` mit `__init__.py`, `router.py`, `service.py`, `schemas.py`.

---

## Datenbankänderung

### Migration `008_add_review_resolution_fields.py`

Fügt zwei Spalten zur Tabelle `review_items` hinzu:

```sql
ALTER TABLE review_items ADD COLUMN resolved_by UUID REFERENCES users(id);
ALTER TABLE review_items ADD COLUMN resolved_at TIMESTAMPTZ;
```

### ReviewItem-Modell-Erweiterung (app/imports/models.py)

```python
resolved_by: Optional[UUID] = Field(default=None, foreign_key="users.id")
resolved_at: Optional[datetime] = Field(default=None)
```

---

## API-Endpunkte

Prefix: `/api/v1/mandants/{mandant_id}/review`

| Method | Path | Rolle | Beschreibung |
|---|---|---|---|
| GET | `/` | accountant | Offene (und gefilterte) Review-Items auflisten |
| POST | `/{item_id}/confirm` | accountant | Bestätigen: Zuordnung korrekt, IBAN registrieren |
| POST | `/{item_id}/reassign` | accountant | Anderer bestehender Partner zuweisen |
| POST | `/{item_id}/new-partner` | accountant | Neuen Partner anlegen und zuweisen |

**Query-Parameter (GET):**
- `status` (optional, default=`open`): `open` | `confirmed` | `adjusted` | `all`
- `page` (default=1), `size` (default=20, max=100)

---

## Schemas (app/review/schemas.py)

```python
class ReviewItemResponse(BaseModel):
    id: UUID
    mandant_id: UUID
    item_type: str
    journal_line_id: UUID
    context: Any
    status: str
    created_at: datetime
    resolved_by: Optional[UUID]
    resolved_at: Optional[datetime]

class PaginatedReviewItemsResponse(BaseModel):
    items: list[ReviewItemResponse]
    total: int; page: int; size: int; pages: int

class ConfirmRequest(BaseModel):
    pass  # keine Parameter nötig

class ReassignRequest(BaseModel):
    partner_id: UUID

class NewPartnerRequest(BaseModel):
    name: str  # max_length=255
```

---

## Service-Logik (app/review/service.py)

### `list_items`
```
SELECT review_items WHERE mandant_id = ? [AND status = ?]
ORDER BY created_at ASC
OFFSET ? LIMIT ?
```

### `confirm(item_id, mandant_id, actor_id)`
1. `_get_or_404(item_id, mandant_id)` — prüft Existenz + Mandant
2. Guard: `item.status != "open"` → 409 Conflict
3. Lade `journal_line` via `item.journal_line_id`
4. Falls `journal_line.partner_iban_raw` nicht leer:
   - Normalisiere IBAN
   - Prüfe, ob `PartnerIban` mit dieser IBAN für `partner_id` bereits existiert
   - Falls nicht: `PartnerIban` anlegen
5. `item.status = "confirmed"`, `item.resolved_by = actor_id`, `item.resolved_at = utcnow()`
6. `AuditLog` schreiben: `event_type="review.confirmed"`, payload = `{item_id, journal_line_id, partner_id}`
7. Commit + Refresh

### `reassign(item_id, mandant_id, actor_id, partner_id)`
1. `_get_or_404(item_id, mandant_id)`
2. Guard: `item.status != "open"` → 409
3. Ziel-Partner laden: muss existieren, `is_active == True`, selbe `mandant_id` → sonst 404
4. `journal_line.partner_id = partner_id`
5. `item.status = "adjusted"`, resolved_by/at setzen
6. `AuditLog`: `event_type="review.reassigned"`, payload = `{item_id, old_partner_id, new_partner_id}`
7. Commit

### `create_and_assign(item_id, mandant_id, actor_id, partner_name)`
1. `_get_or_404(item_id, mandant_id)`
2. Guard: `item.status != "open"` → 409
3. Prüfe Name-Uniqueness für mandant_id (analog matching.py Suffix-Logik)
4. Neuen `Partner` anlegen (is_active=True)
5. `journal_line.partner_id = new_partner.id`
6. `item.status = "adjusted"`, resolved_by/at setzen
7. `AuditLog`: `event_type="review.new_partner_assigned"`, payload = `{item_id, new_partner_id, partner_name}`
8. Commit

---

## Router-Registrierung (app/main.py)

```python
from app.review.router import review_router
app.include_router(review_router, prefix="/api/v1")
```

---

## Abhängigkeiten

| Modul | Wird importiert aus |
|---|---|
| ReviewItem, JournalLine | `app.imports.models` |
| Partner, PartnerIban, AuditLog | `app.partners.models` |
| require_role, require_mandant_access | `app.auth.dependencies` |
| AuditLog-Pattern | analog `app.partners.service.PartnerMergeService` |
