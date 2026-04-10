---
id: 009-import-service-assignment
unit: 004-import-pipeline
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-10T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 009-import-service-assignment

## User Story

**As a** system
**I want** to assign a service to each imported journal line immediately after partner matching
**So that** every booking line has a deterministic service assignment for its partner

## Acceptance Criteria

- [ ] **Given** a journal line has a matched partner, **When** import processing continues, **Then** the service assignment engine is called before the import transaction completes
- [ ] **Given** exactly one matching service, **When** assignment runs, **Then** `journal_line.service_id` is set to that service and `service_assignment_mode = auto`
- [ ] **Given** no matching service, **When** assignment runs, **Then** the partner's base service is assigned
- [ ] **Given** more than one matching service, **When** assignment runs, **Then** the base service is assigned and a `service_assignment` review item is created
- [ ] **Given** assignment fails for one row, **When** import transaction completes, **Then** the affected file import is rolled back consistently

## Dependencies

### Requires
- 003-partner-matching.md
- 008-service-management/005-service-auto-assignment.md
