---
id: 002-identity-access
unit: 001-identity-access
intent: 001-cashflow-core
type: ddd-construction-bolt
status: complete
stories:
  - 003-user-crud
  - 004-mandant-user-assignment
  - 006-user-invitation
  - 007-dev-seed
created: 2026-04-06T00:00:00Z
started: 2026-04-06T00:00:00Z
completed: 2026-04-06T00:00:00Z
current_stage: test
stages_completed: [domain-model, technical-design, adr-analysis, implement, test]

requires_bolts: [001-identity-access]
enables_bolts: [003-tenant-account-mgmt]
requires_units: []
blocks: false
