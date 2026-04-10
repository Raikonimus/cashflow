---
id: 001-csv-upload-endpoint
unit: 004-import-pipeline
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 001-csv-upload-endpoint

## User Story

**As an** Accountant
**I want** to upload one or more CSV files for an account
**So that** the system can import the transactions

## Acceptance Criteria

- [ ] **Given** valid account_id with mapping, **When** POST /imports (multipart, files[]), **Then** ImportRun created, processing starts
- [ ] **Given** account with no mapping, **When** POST /imports, **Then** 422 with message "no mapping configured"
- [ ] **Given** non-CSV file, **When** upload, **Then** 422
- [ ] **Given** multiple files, **When** upload, **Then** each file creates its own ImportRun
- [ ] **Given** duplicate row (same account_id + valuta_date + booking_date + amount + partner_iban_raw + partner_name_raw already exists for mandant), **When** import processes that row, **Then** row is skipped and counted as `skipped` in ImportRun (not an error)

## Edge Cases

| Scenario | Expected Behavior |
|----------|-------------------|
| Alle Zeilen Dubletten | ImportRun status=completed, row_count=0, skipped_count=N |
| Gemischte neue + doppelte Zeilen | Neue werden importiert, doppelte übersprungen |

## Dependencies

### Requires
- 002-tenant-account-mgmt/003-column-mapping-config.md
