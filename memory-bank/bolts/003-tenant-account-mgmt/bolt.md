---
id: 003-tenant-account-mgmt
unit: 002-tenant-account-mgmt
intent: 001-cashflow-core
type: ddd-construction-bolt
status: complete
stories:
  - 001-mandant-crud
  - 002-account-crud
  - 003-column-mapping-config
  - 004-remapping-trigger
created: 2026-04-06T00:00:00Z
started: 2026-04-06T00:00:00Z
completed: 2026-04-06T00:00:00Z
current_stage: tests
stages_completed: [domain-model, technical-design, adr-analysis, implementation, tests]

requires_bolts: [001-identity-access]
enables_bolts: [006-import-core]
requires_units: []
blocks: false
