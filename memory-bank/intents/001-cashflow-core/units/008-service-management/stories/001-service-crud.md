---
id: 001-service-crud
unit: 008-service-management
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-10T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 001-service-crud

## User Story

**As an** Accountant
**I want** to create, edit, list, and delete services for a partner
**So that** journal lines can be classified into specific business services

## Acceptance Criteria

- [ ] **Given** GET /partners/:id/services, **When** called, **Then** all services of that partner are returned including base service marker, type, tax_rate, and validity window
- [ ] **Given** valid input, **When** POST /partners/:id/services, **Then** a new non-base service is created for that partner
- [ ] **Given** an existing non-base service, **When** PATCH /services/:id, **Then** editable fields are updated
- [ ] **Given** a non-base service, **When** DELETE /services/:id, **Then** the service is removed and partner revalidation is triggered
- [ ] **Given** a service from another tenant, **When** it is accessed, **Then** 404 or 403 according to authorization policy

## Dependencies

### Requires
- 003-partner-management/001-partner-crud.md
