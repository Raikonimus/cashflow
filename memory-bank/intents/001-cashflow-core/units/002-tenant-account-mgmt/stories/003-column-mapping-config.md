---
id: 003-column-mapping-config
unit: 002-tenant-account-mgmt
intent: 001-cashflow-core
status: draft
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 003-column-mapping-config

## User Story

**As an** Accountant
**I want** to configure which CSV source columns map to which internal fields
**So that** the import pipeline correctly parses any CSV format

## Acceptance Criteria

- [ ] **Given** account with no mapping, **When** GET /accounts/:id/mapping, **Then** returns empty list
- [ ] **Given** valid mapping config, **When** PUT /accounts/:id/mapping, **Then** mapping is saved (replaces existing)
- [ ] **Given** two source columns mapped to same target, **When** import runs, **Then** values are concatenated with \n in sort_order
- [ ] **Given** target_column not in allowed set, **When** PUT mapping, **Then** 422
- [ ] **Given** Viewer, **When** PUT /accounts/:id/mapping, **Then** 403

## Technical Notes

- Target columns: valuta_date, booking_date, text, partner_name, partner_iban, amount, currency
- sort_order determines concatenation order for multi-source mappings

## Dependencies

### Requires
- 002-account-crud.md
