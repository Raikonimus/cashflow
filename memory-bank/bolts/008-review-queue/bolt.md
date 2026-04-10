---
id: 008-review-queue
unit: 005-review-queue
intent: 001-cashflow-core
type: ddd-construction-bolt
status: complete
stories:
  - 001-review-items-list
  - 002-review-item-confirm
  - 003-review-item-reassign
created: 2026-04-07T10:00:00Z
started: 2026-04-07T10:00:00Z
completed: null
current_stage: done
stages_completed: [domain-model, technical-design, adr-analysis, implement, test]

requires_bolts: [007-partner-matching]
enables_bolts: [011-core-ui, 012-operations-ui]
requires_units: []
blocks: false

complexity:
  avg_complexity: 2
  avg_uncertainty: 1
  max_dependencies: 2
  testing_scope: 2
---
