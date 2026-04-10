# Stage 1: Domain Model — Bolt 008 Review Queue

## Ubiquitous Language

| Begriff | Definition |
|---|---|
| **ReviewItem** | Ein auflösungsbedürftiger Vorgang, der entsteht, wenn eine JournalLine per Namensgleichheit einem Partner zugeordnet wurde und eine IBAN vorliegt, die noch nicht registriert ist |
| **Confirm** | Aktion: die automatische Zuordnung wird als korrekt bestätigt; IBAN der JournalLine wird zum Partner hinzugefügt |
| **Reassign** | Aktion: Zuordnung zu einem anderen bereits existierenden aktiven Partner |
| **NewPartner** | Aktion: neuen Partner anlegen und JournalLine diesem zuordnen |
| **open** | ReviewItem wartet auf Bearbeitung |
| **confirmed** | Entscheidung manuell bestätigt |
| **adjusted** | Entscheidung manuell korrigiert (reassign oder new-partner) |
| **resolved_by** | UUID des Users, der die Aktion ausgeführt hat |
| **resolved_at** | Zeitpunkt der Auflösung |

---

## Entitäten

### ReviewItem (bereits in Bolt 007 erstellt, wird erweitert)

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID PK | |
| mandant_id | UUID FK→mandants | Tenant-Isolation |
| item_type | VARCHAR(50) | aktuell: `name_match_with_iban` |
| journal_line_id | UUID FK→journal_lines UNIQUE | rückverbundene JournalLine |
| context | JSON NULL | Matching-Kontext (`matched_on`, `raw_name`, `raw_iban`) |
| status | VARCHAR(20) default `open` | `open` / `confirmed` / `adjusted` |
| created_at | TIMESTAMPTZ | |
| resolved_by | UUID FK→users NULL | *neu in Bolt 008* |
| resolved_at | TIMESTAMPTZ NULL | *neu in Bolt 008* |

---

## Aggregates

`ReviewItem` ist ein eigenständiges Aggregate. `JournalLine` und `Partner` sind externe Referenzen — sie werden innerhalb von Aktionen modifiziert, gehören aber zu eigenen Aggregates.

---

## Domain Invarianten

1. Ein `confirmed` oder `adjusted` ReviewItem kann nicht nochmals bearbeitet werden (→ 409 Conflict)
2. Bei Reassign muss der Ziel-Partner zur selben `mandant_id` gehören und `is_active == True` sein
3. Bei Confirm: `journal_line.partner_iban_raw` wird als neue `PartnerIban` eingetragen (sofern noch nicht vorhanden)
4. Jede abschließende Aktion (confirm, reassign, new-partner) schreibt einen `audit_log`-Eintrag

---

## Domain Services

### ReviewService

```
list_items(mandant_id, status_filter=None, page, size) → (list[ReviewItem], total)
confirm(item_id, mandant_id, actor_id) → ReviewItem
reassign(item_id, mandant_id, actor_id, partner_id) → ReviewItem
create_and_assign(item_id, mandant_id, actor_id, partner_name) → ReviewItem
```

---

## Schema-Änderung

`review_items` benötigt zwei neue Spalten:
- `resolved_by UUID NULL REFERENCES users(id)`
- `resolved_at TIMESTAMPTZ NULL`

→ Migration `008_add_review_resolution_fields.py`

---

## Repository-Interface (konzeptuell)

```
get_item(item_id, mandant_id) → ReviewItem | None
list_items(mandant_id, status, offset, limit) → list[ReviewItem]
count_items(mandant_id, status) → int
save(item) → ReviewItem
```
