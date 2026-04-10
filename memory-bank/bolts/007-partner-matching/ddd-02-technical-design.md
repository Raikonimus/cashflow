---
stage: technical-design
bolt: 007-partner-matching
created: 2026-04-07T08:45:00Z
---

## Technical Design: Partner Matching

### Architecture Pattern

**Service-Layer-Extension im bestehenden `ImportService`**

Der Partner-Matching-Algorithmus wird als dedizierter `PartnerMatchingService` implementiert,
der vom `ImportService` bei der Zeilen-Verarbeitung aufgerufen wird. Der neue Service ist
eine testbare, isolierte Einheit mit eigenem File (`app/imports/matching.py`), folgt aber
demselben Dependency-Injection-Muster (AsyncSession) wie alle anderen Services im Projekt.

Kein neuer Router nötig — alle Endpunkte bleiben identisch. Der `/mandants/{id}/accounts/{id}/imports`-POST
ist der Einstiegspunkt; das Matching erfolgt intern während `_process_file`.

### Layer Structure

```text
┌──────────────────────────────────────────┐
│  Presentation (imports_router.py)        │   POST /imports  (unverändert)
├──────────────────────────────────────────┤
│  Application (ImportService)             │   _process_file → match pro Zeile
├──────────────────────────────────────────┤
│  Domain (PartnerMatchingService)         │   match(mandant_id, iban, name)
│           (ReviewItemFactory)            │   maybe_create(result, journal_line)
├──────────────────────────────────────────┤
│  Infrastructure (AsyncSession)           │   partner_ibans, partner_names, partners,
│                                          │   review_items (neues Model)
└──────────────────────────────────────────┘
```

### Neue Datei: `app/imports/matching.py`

Enthält:
- `MatchOutcome` (StrEnum: `iban_match`, `name_match`, `new_partner`)
- `PartnerMatchResult` (dataclass: `partner_id`, `outcome`, `review_context`)
- `PartnerMatchingService` (async, injected AsyncSession)
- `ReviewItemFactory` (pure function, keine DB-Abhängigkeit)

### API Design

Keine neuen API-Endpunkte. Das Matching ist ein interner Implementierungsdetail des
bestehenden Upload-Endpoints. Die `ImportRunDetailResponse` ändert sich nicht.

Optional: `review_items_count` in `ImportRunDetailResponse` ergänzen (Out of Scope für diese Story).

### Data Model

**Neue Tabelle: `review_items`**

| Spalte | Typ | Constraints |
|--------|-----|-------------|
| `id` | UUID | PK |
| `mandant_id` | UUID | FK → mandants.id, CASCADE DELETE, INDEX |
| `item_type` | VARCHAR(50) | NOT NULL |
| `journal_line_id` | UUID | FK → journal_lines.id, CASCADE DELETE, UNIQUE |
| `context` | JSON | nullable — `{partner_id, matched_name, raw_iban}` |
| `status` | VARCHAR(20) | NOT NULL, default `open` |
| `created_at` | TIMESTAMP TZ | NOT NULL, default NOW() |

**UNIQUE-Constraint**: `(journal_line_id)` — max 1 Review-Item pro Buchungszeile.

**Bestehende Tabellen**: Keine Schemaänderungen nötig. `partner_ibans` und `partner_names`
haben bereits die nötigen Felder; `partner_ibans.iban` ist bereits UNIQUE (global, reicht).

**Migration**: `007_add_review_items.py`

### Matching-Algorithmus (Implementierungsdetail)

```python
async def match(mandant_id, iban_raw, name_raw) -> PartnerMatchResult:
    # Step 1: IBAN-Match
    if iban_raw:
        normalized = iban_raw.replace(" ", "").upper()
        row = await session.exec(
            select(PartnerIban)
            .join(Partner)
            .where(PartnerIban.iban == normalized)
            .where(Partner.mandant_id == mandant_id)
        )
        if hit := row.first():
            return PartnerMatchResult(partner_id=hit.partner_id, outcome=IBAN_MATCH)

    # Step 2: Name-Match (ILIKE via text())
    if name_raw:
        row = await session.exec(
            select(PartnerName)
            .join(Partner)
            .where(Partner.mandant_id == mandant_id)
            .where(PartnerName.name.ilike(name_raw.strip()))
        )
        if hit := row.first():
            return PartnerMatchResult(
                partner_id=hit.partner_id,
                outcome=NAME_MATCH,
                review_context={"matched_name": hit.name, "raw_iban": iban_raw},
            )

    # Step 3: Neuen Partner anlegen
    partner = Partner(mandant_id=mandant_id, name=name_raw or "")
    session.add(partner)
    await session.flush()
    if iban_raw:
        session.add(PartnerIban(partner_id=partner.id, iban=normalized))
    return PartnerMatchResult(partner_id=partner.id, outcome=NEW_PARTNER)
```

### Integration in ImportService

`_process_file` ruft `PartnerMatchingService.match()` pro Zeile auf, ergänzt `partner_id`
im `line_data`-Dict und übergibt das Ergebnis an `ReviewItemFactory.maybe_create()`.

Review-Items werden am Ende per Bulk-Insert eingefügt — analog zu JournalLines.

### Security Design

- **Mandanten-Isolation**: Alle Queries filtern explizit auf `mandant_id`; kein Cross-Tenant möglich
- **Input-Sanitisation**: `partner_name_raw` aus CSV ist bereits auf 500 Zeichen begrenzt; ILIKE-Parameter sind bound parameters (kein SQL-Injection-Risiko)
- **No PII leakage**: IBAN und Name kommen nur aus der eigenen Upload-Datei des Mandanten

### NFR Implementation

- **Performance**: `partner_ibans.iban` ist bereits UNIQUE (implizit indiziert); `partner_names.name` bekommt einen Index (`ix_partner_names_name`) für schnelle ILIKE-Suche auf kleinen Mandanten-Datensätzen
- **Transaktionssicherheit**: Matching läuft innerhalb der bestehenden `_process_file`-Transaktion; bei Fehler wird die gesamte Datei zurückgerollt
- **Idempotenz**: Der bestehende UNIQUE-Constraint auf `journal_lines` (`uq_journal_lines_dedup`) verhindert Duplikat-Zeilen bei erneutem Upload derselben Datei

### Anpassungen an bestehenden Dateien

| Datei | Änderung |
|-------|----------|
| `app/imports/service.py` | `_process_file` ruft `PartnerMatchingService` auf; Bulk-Insert ergänzt `partner_id` |
| `app/imports/matching.py` | Neu — MatchOutcome, PartnerMatchResult, PartnerMatchingService, ReviewItemFactory |
| `app/imports/models.py` | `ReviewItem`-Modell hinzufügen |
| `migrations/versions/007_add_review_items.py` | Neue Migration für `review_items`-Tabelle |
