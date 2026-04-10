---
id: 008-service-type-detection
unit: 008-service-management
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-10T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 008-service-type-detection

## User Story

**As a** system
**I want** to auto-detect the type and default tax rate of services that are still unknown
**So that** classification starts with a useful default and can later be reviewed by a user

## Acceptance Criteria

- [ ] **Given** a service with `service_type = unknown` and `service_type_manual = false`, **When** detection runs, **Then** keyword rules for `employee` and `authority` are checked first
- [ ] **Given** no keyword matches, **When** detection runs, **Then** amount < 0 or = 0 maps to `supplier`, amount > 0 maps to `customer`
- [ ] **Given** a type is auto-detected, **When** detection completes, **Then** `service_type` is immediately updated and a `service_type_review` item is upserted
- [ ] **Given** `tax_rate_manual = false`, **When** the detected type is `employee` or `authority`, **Then** tax_rate is set to 0; otherwise 20
- [ ] **Given** `service_type_manual = true`, **When** detection runs, **Then** neither the type nor review items are changed automatically

## Dependencies

### Requires
- 004-keyword-config.md
- 005-service-auto-assignment.md
- 007-service-revalidation.md
