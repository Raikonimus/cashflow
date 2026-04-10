---
id: 007-service-revalidation
unit: 008-service-management
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-10T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 007-service-revalidation

## User Story

**As a** system
**I want** to revalidate service assignments when service rules change
**So that** outdated assignments are surfaced as proposals instead of silently changed

## Acceptance Criteria

- [ ] **Given** a service or matcher is created, updated, or deleted, **When** the change is saved, **Then** all journal lines of that partner are revalidated
- [ ] **Given** revalidation finds a different result than the stored assignment, **When** processing completes, **Then** a `service_assignment` review item is upserted with current_service_id, proposed_service_id, and reason
- [ ] **Given** revalidation proposes the same service as currently stored, **When** processing completes, **Then** no pending review item exists for that line
- [ ] **Given** a journal line currently has a manual assignment, **When** revalidation runs, **Then** the stored assignment remains unchanged and any deviation appears only as a proposal
- [ ] **Given** multiple open review items already exist for the same journal line, **When** revalidation reruns, **Then** they are replaced by a single current pending item

## Dependencies

### Requires
- 005-service-auto-assignment.md
- 006-service-manual-assignment.md
