---
id: 003-partner-name-patterns
unit: 003-partner-management
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 003-partner-name-patterns

## User Story

**As an** Accountant
**I want** to define string or regex patterns to identify a partner by name
**So that** future imports with similar names are automatically assigned correctly

## Acceptance Criteria

- [ ] **Given** valid string pattern, **When** POST /partners/:id/patterns, **Then** pattern saved with type=string
- [ ] **Given** valid regex pattern, **When** POST /partners/:id/patterns, **Then** pattern validated and saved with type=regex
- [ ] **Given** invalid regex, **When** POST with type=regex, **Then** 422 with error message
- [ ] **Given** pattern exists, **When** DELETE /partners/:id/patterns/:pid, **Then** pattern removed

## Technical Notes

- Regex validation: compile with Python `re.compile()` before saving; catch `re.error`
- Patterns are used during import matching (future: also in background re-match jobs)

## Dependencies

### Requires
- 001-partner-crud.md
