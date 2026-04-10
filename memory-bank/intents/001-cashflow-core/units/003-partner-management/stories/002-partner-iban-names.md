---
id: 002-partner-iban-names
unit: 003-partner-management
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 002-partner-iban-names

## User Story

**As an** Accountant
**I want** to add multiple IBANs and name variants to a partner
**So that** all known identifiers are associated with the right partner

## Acceptance Criteria

- [ ] **Given** existing partner, **When** POST /partners/:id/ibans, **Then** IBAN is added
- [ ] **Given** IBAN already assigned to another partner, **When** POST /partners/:id/ibans, **Then** 409
- [ ] **Given** existing partner, **When** POST /partners/:id/names, **Then** name variant is added
- [ ] **Given** name already exists on partner, **When** POST /partners/:id/names, **Then** 409

## Dependencies

### Requires
- 001-partner-crud.md
