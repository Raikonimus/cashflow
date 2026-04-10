---
id: 002-account-crud
unit: 002-tenant-account-mgmt
intent: 001-cashflow-core
status: draft
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 002-account-crud

## User Story

**As a** Mandant-Admin or Accountant
**I want** to manage bank accounts and credit cards for my mandant
**So that** I can import transactions for each account separately

## Acceptance Criteria

- [ ] **Given** Accountant, **When** POST /accounts, **Then** account created with name, description, type
- [ ] **Given** account_type not in (bankkonto, kreditkarte, sonstige), **When** POST /accounts, **Then** 422
- [ ] **Given** account with existing journal lines, **When** DELETE /accounts/:id, **Then** 409 (cannot delete)
- [ ] **Given** account with no journal lines, **When** DELETE /accounts/:id, **Then** deleted

## Dependencies

### Requires
- 001-mandant-crud.md
