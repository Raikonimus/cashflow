---
id: 001-journal-lines-query
unit: 006-journal-viewer
intent: 001-cashflow-core
status: draft
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 001-journal-lines-query

## User Story

**As any** user
**I want** to view journal lines with flexible filters
**So that** I can analyse transactions for my mandant

## Acceptance Criteria

- [ ] **Given** GET /journal with no filters, **When** called, **Then** returns paginated list for current mandant
- [ ] **Given** filter year=2025, **When** GET /journal, **Then** only lines with valuta_date in 2025
- [ ] **Given** filter month=3&year=2025, **When** GET /journal, **Then** only March 2025 lines
- [ ] **Given** filter partner_id, **When** GET /journal, **Then** only lines for that partner
- [ ] **Given** filter account_id, **When** GET /journal, **Then** only lines for that account
- [ ] **Given** filter has_partner=false, **When** GET /journal, **Then** only lines without partner_id

## Dependencies

### Requires
- 004-import-pipeline/003-partner-matching.md
