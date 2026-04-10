---
id: 003-partner-matching
unit: 004-import-pipeline
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 003-partner-matching

## User Story

**As a** system
**I want** to automatically match each journal line to an existing partner or create a new one
**So that** all transactions are attributed without manual effort

## Acceptance Criteria

- [ ] **Given** IBAN in row matches a known partner_iban, **When** matching, **Then** journal_line.partner_id = that partner; no review item
- [ ] **Given** no IBAN match, but name exactly matches a partner_name, **When** matching AND row has a non-empty IBAN not yet in partner's ibans, **Then** partner assigned + review item created (type=partner_name_match)
- [ ] **Given** no IBAN match, name matches, but row has **no IBAN**, **When** matching, **Then** partner assigned; **no review item** (nothing uncertain about the IBAN)
- [ ] **Given** no IBAN and no exact name match, **When** matching, **Then** new partner created with that name and IBAN; no review item
- [ ] **Given** blank IBAN in row, **When** matching, **Then** skip IBAN step; go directly to name match
- [ ] **Given** partner_name_match review item, **When** viewing, **Then** includes partner_id, journal_line_id, raw IBAN

## Technical Notes

- Name match ist **case-insensitive** (`ILIKE` in PostgreSQL) gegen alle `partner_names`-Einträge
- Matching muss auf `mandant_id` isoliert sein (kein Cross-Tenant Matching)

## Dependencies

### Requires
- 002-mapping-application.md
- 003-partner-management/001-partner-crud.md
