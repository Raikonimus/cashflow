---
id: 011-core-ui
unit: 007-cashflow-ui
intent: 001-cashflow-core
type: simple-construction-bolt
status: complete
stories:
  - 002-admin-screens
  - 003-account-management-screen
  - 004-import-screen
created: 2026-04-07T12:00:00Z
started: 2026-04-07T12:00:00Z
completed: 2026-04-07T13:00:00Z
current_stage: test
stages_completed: [plan, implement, test]

requires_bolts: [010-cashflow-ui, 002-identity-access, 003-tenant-account-mgmt, 006-import-core]
enables_bolts: [012-operations-ui]
requires_units: []
blocks: false

complexity:
  avg_complexity: 3
  avg_uncertainty: 2
  max_dependencies: 4
  testing_scope: 2
---
