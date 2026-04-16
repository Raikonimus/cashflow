---
id: 004-cashflow-matrix-api
unit: 006-journal-viewer
intent: 001-cashflow-core
status: draft
priority: must
created: 2026-04-15T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 004-cashflow-matrix-api

## User Story

**As any** user
**I want** a yearly income-expense matrix endpoint with monthly and yearly totals
**So that** I can analyze net cashflow by service and groups

## Acceptance Criteria

- [ ] **Given** GET /reports/income-expense?year=YYYY, **When** called, **Then** returns three sections (`income`, `expense`, `neutral`) with columns `year_total`, `jan`..`dec`
- [ ] **Given** `neutral` section, **When** response is built, **Then** only services with `erfolgsneutral = true` are included
- [ ] **Given** `income` section, **When** response is built, **Then** only services with `erfolgsneutral = false` and `service_type = customer` are included
- [ ] **Given** `expense` section, **When** response is built, **Then** only services with `erfolgsneutral = false` and `service_type in {supplier, authority, shareholder, employee}` are included
- [ ] **Given** `service_type = unknown` and `erfolgsneutral = false`, **When** response is built, **Then** service is not included in matrix sections
- [ ] **Given** a service and month, **When** net cell value is computed, **Then** `net = sum(amount) / (1 + tax_rate / 100)` using all journal lines of that month by `valuta_date`
- [ ] **Given** yearly total column, **When** computed, **Then** the same net formula is applied on yearly aggregated gross amount
- [ ] **Given** groups and assignments, **When** response is built, **Then** each section contains group subtotals per column and section grand totals per column (independent from UI collapse state)
- [ ] **Given** mixed currencies, **When** response is built, **Then** only journal lines in mandant base currency are aggregated and excluded currency counts are returned
- [ ] **Given** no journal lines for a cell, **When** response is built, **Then** value is `0.00`
- [ ] **Given** request from viewer, **When** endpoint is called, **Then** access is granted read-only

## Technical Notes

- Response includes both `gross` and `net` per cell to allow transparent UI rendering.
- Aggregation must be mandant-isolated and database-side.
- Tax rate for net calculation should use historical snapshot at booking time; fallback to current service tax rate.

### API Contract (Response Shape)

- Endpoint: `GET /reports/income-expense?year=YYYY`
- Content:
	- `year`: int
	- `base_currency`: string (z. B. EUR)
	- `sections`: object mit `income`, `expense`, `neutral`
	- je Section:
		- `currency`: string
		- `excluded_currency_count`: int
		- `excluded_currency_amount_gross`: decimal-string
		- `groups`: array
		- `totals`: cells object
	- Group item:
		- `group_id`: uuid
		- `group_name`: string
		- `sort_order`: int
		- `collapsed`: bool
		- `subtotal_cells`: cells object
		- `services`: array
	- Service row:
		- `service_id`: uuid
		- `service_name`: string
		- `service_type`: enum
		- `erfolgsneutral`: bool
		- `cells`: cells object
	- `cells`: keys `year_total`, `jan`, `feb`, `mar`, `apr`, `may`, `jun`, `jul`, `aug`, `sep`, `oct`, `nov`, `dec`
	- Cell value: `{ "gross": "0.00", "net": "0.00" }`

### API Contract (Example)

{
	"year": 2026,
	"base_currency": "EUR",
	"sections": {
		"income": {
			"currency": "EUR",
			"excluded_currency_count": 2,
			"excluded_currency_amount_gross": "350.00",
			"groups": [
				{
					"group_id": "7c5b0f8a-0a20-4cc8-9a1d-4d6f9e2fb100",
					"group_name": "Lizenzen",
					"sort_order": 10,
					"collapsed": false,
					"subtotal_cells": {
						"year_total": { "gross": "12000.00", "net": "10000.00" },
						"jan": { "gross": "1000.00", "net": "833.33" },
						"feb": { "gross": "1000.00", "net": "833.33" },
						"mar": { "gross": "1000.00", "net": "833.33" },
						"apr": { "gross": "1000.00", "net": "833.33" },
						"may": { "gross": "1000.00", "net": "833.33" },
						"jun": { "gross": "1000.00", "net": "833.33" },
						"jul": { "gross": "1000.00", "net": "833.33" },
						"aug": { "gross": "1000.00", "net": "833.33" },
						"sep": { "gross": "1000.00", "net": "833.33" },
						"oct": { "gross": "1000.00", "net": "833.33" },
						"nov": { "gross": "1000.00", "net": "833.33" },
						"dec": { "gross": "1000.00", "net": "833.33" }
					},
					"services": [
						{
							"service_id": "6f3d6c1a-b75b-4c2d-9b9f-d12ebf2d4f90",
							"service_name": "ERP Lizenz A",
							"service_type": "customer",
							"erfolgsneutral": false,
							"cells": {
								"year_total": { "gross": "12000.00", "net": "10000.00" },
								"jan": { "gross": "1000.00", "net": "833.33" },
								"feb": { "gross": "1000.00", "net": "833.33" },
								"mar": { "gross": "1000.00", "net": "833.33" },
								"apr": { "gross": "1000.00", "net": "833.33" },
								"may": { "gross": "1000.00", "net": "833.33" },
								"jun": { "gross": "1000.00", "net": "833.33" },
								"jul": { "gross": "1000.00", "net": "833.33" },
								"aug": { "gross": "1000.00", "net": "833.33" },
								"sep": { "gross": "1000.00", "net": "833.33" },
								"oct": { "gross": "1000.00", "net": "833.33" },
								"nov": { "gross": "1000.00", "net": "833.33" },
								"dec": { "gross": "1000.00", "net": "833.33" }
							}
						}
					]
				}
			],
			"totals": {
				"year_total": { "gross": "12000.00", "net": "10000.00" },
				"jan": { "gross": "1000.00", "net": "833.33" },
				"feb": { "gross": "1000.00", "net": "833.33" },
				"mar": { "gross": "1000.00", "net": "833.33" },
				"apr": { "gross": "1000.00", "net": "833.33" },
				"may": { "gross": "1000.00", "net": "833.33" },
				"jun": { "gross": "1000.00", "net": "833.33" },
				"jul": { "gross": "1000.00", "net": "833.33" },
				"aug": { "gross": "1000.00", "net": "833.33" },
				"sep": { "gross": "1000.00", "net": "833.33" },
				"oct": { "gross": "1000.00", "net": "833.33" },
				"nov": { "gross": "1000.00", "net": "833.33" },
				"dec": { "gross": "1000.00", "net": "833.33" }
			}
		},
		"expense": {
			"currency": "EUR",
			"excluded_currency_count": 0,
			"excluded_currency_amount_gross": "0.00",
			"groups": [],
			"totals": {
				"year_total": { "gross": "0.00", "net": "0.00" },
				"jan": { "gross": "0.00", "net": "0.00" },
				"feb": { "gross": "0.00", "net": "0.00" },
				"mar": { "gross": "0.00", "net": "0.00" },
				"apr": { "gross": "0.00", "net": "0.00" },
				"may": { "gross": "0.00", "net": "0.00" },
				"jun": { "gross": "0.00", "net": "0.00" },
				"jul": { "gross": "0.00", "net": "0.00" },
				"aug": { "gross": "0.00", "net": "0.00" },
				"sep": { "gross": "0.00", "net": "0.00" },
				"oct": { "gross": "0.00", "net": "0.00" },
				"nov": { "gross": "0.00", "net": "0.00" },
				"dec": { "gross": "0.00", "net": "0.00" }
			}
		},
		"neutral": {
			"currency": "EUR",
			"excluded_currency_count": 0,
			"excluded_currency_amount_gross": "0.00",
			"groups": [],
			"totals": {
				"year_total": { "gross": "0.00", "net": "0.00" },
				"jan": { "gross": "0.00", "net": "0.00" },
				"feb": { "gross": "0.00", "net": "0.00" },
				"mar": { "gross": "0.00", "net": "0.00" },
				"apr": { "gross": "0.00", "net": "0.00" },
				"may": { "gross": "0.00", "net": "0.00" },
				"jun": { "gross": "0.00", "net": "0.00" },
				"jul": { "gross": "0.00", "net": "0.00" },
				"aug": { "gross": "0.00", "net": "0.00" },
				"sep": { "gross": "0.00", "net": "0.00" },
				"oct": { "gross": "0.00", "net": "0.00" },
				"nov": { "gross": "0.00", "net": "0.00" },
				"dec": { "gross": "0.00", "net": "0.00" }
			}
		}
	}
}

## Dependencies

### Requires
- 001-journal-lines-query.md
- 008-service-management/009-service-groups.md
