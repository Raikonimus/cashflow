---
id: 003-audit-log-api
unit: 006-journal-viewer
intent: 001-cashflow-core
status: draft
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 003-audit-log-api

## User Story

**As an** Admin or Mandant-Admin
**I want** to read the audit log
**So that** I can trace all user actions for compliance and debugging

## Acceptance Criteria

- [ ] **Given** Admin, **When** GET /audit, **Then** can query across all mandants
- [ ] **Given** Mandant-Admin, **When** GET /audit, **Then** only sees entries for their mandant
- [ ] **Given** Accountant or Viewer, **When** GET /audit, **Then** 403
- [ ] **Given** audit log entries, **When** returned, **Then** include user_id, action, entity_type, entity_id, old_value, new_value, created_at

## Technical Notes

- Audit log is append-only; no DELETE or UPDATE endpoint exists for audit_logs table
- All writes to audit_log happen inside service layer, not in API layer

## Dependencies

### Requires
- 001-identity-access/001-login-jwt.md
