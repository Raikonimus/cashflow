---
id: 004-keyword-config
unit: 008-service-management
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-10T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 004-keyword-config

## User Story

**As an** Accountant
**I want** to configure keyword rules for employee and authority detection
**So that** service types can be auto-detected using business-specific language

## Acceptance Criteria

- [ ] **Given** GET /settings/service-keywords, **When** called, **Then** tenant-specific rules plus fallback metadata are returned
- [ ] **Given** valid payload, **When** POST /settings/service-keywords, **Then** a keyword rule for `employee` or `authority` is created
- [ ] **Given** `pattern_type = regex`, **When** the regex is invalid, **Then** save is rejected with 422
- [ ] **Given** an existing rule, **When** PATCH or DELETE is called, **Then** the rule is changed or removed
- [ ] **Given** no tenant-specific rules exist for a target type, **When** detection runs, **Then** system defaults are used

## Dependencies

### Requires
- 001-service-crud.md
