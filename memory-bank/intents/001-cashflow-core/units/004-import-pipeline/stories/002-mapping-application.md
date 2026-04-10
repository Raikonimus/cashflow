---
id: 002-mapping-application
unit: 004-import-pipeline
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 002-mapping-application

## User Story

**As a** system
**I want** to apply the column mapping to each CSV row
**So that** all mapped fields are extracted and unmapped fields are preserved

## Acceptance Criteria

- [ ] **Given** CSV row, **When** mapping applied, **Then** all target fields extracted from source columns
- [ ] **Given** two source columns for same target, **When** mapping applied, **Then** values concatenated with \n (in sort_order)
- [ ] **Given** source column not in mapping, **When** row parsed, **Then** column stored in unmapped_data JSONB
- [ ] **Given** missing required field (e.g., amount) after mapping, **When** row processed, **Then** row marked as error in ImportRun
- [ ] **Given** date fields, **When** parsed, **Then** stored as DATE type (ISO 8601)

## Dependencies

### Requires
- 001-csv-upload-endpoint.md
