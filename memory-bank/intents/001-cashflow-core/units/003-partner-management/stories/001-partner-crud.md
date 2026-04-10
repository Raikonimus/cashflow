---
id: 001-partner-crud
unit: 003-partner-management
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 001-partner-crud

## User Story

**As an** Accountant
**I want** to view and manage partners
**So that** I can maintain accurate partner information

## Acceptance Criteria

- [ ] **Given** Accountant, **When** GET /partners, **Then** returns paginated list with name, IBANs count
- [ ] **Given** Accountant, **When** POST /partners, **Then** creates partner with initial name and optional IBAN
- [ ] **Given** Viewer, **When** POST /partners, **Then** 403
- [ ] **Given** active partner, **When** GET /partners/:id, **Then** returns all names, IBANs, patterns

## Dependencies

### Requires
- 001-identity-access/005-rbac-middleware.md
