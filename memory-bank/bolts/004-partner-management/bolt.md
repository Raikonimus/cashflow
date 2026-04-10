---
id: 004-partner-management
unit: 003-partner-management
intent: 001-cashflow-core
type: ddd-construction-bolt
status: complete
stories:
  - 001-partner-crud
  - 002-partner-iban-names
  - 003-partner-name-patterns
created: 2026-04-06T00:00:00Z
started: 2026-04-06T00:00:00Z
completed: 2026-04-06T00:00:00Z
current_stage: tests
stages_completed: [domain-model, technical-design, adr-analysis, implementation, tests]

requires_bolts: [001-identity-access]
enables_bolts: [005-partner-merge, 007-partner-matching]
requires_units: []
blocks: false
