---
id: 001-identity-access
unit: 001-identity-access
intent: 001-cashflow-core
type: ddd-construction-bolt
status: complete
stories:
  - 001-login-jwt
  - 002-password-reset
  - 005-rbac-middleware
created: 2026-04-06T00:00:00Z
started: 2026-04-06T00:00:00Z
completed: 2026-04-06T00:00:00Z
current_stage: test
stages_completed: [domain-model, technical-design, adr-analysis, implement, test]

requires_bolts: []
enables_bolts: [002-identity-access]
requires_units: []
blocks: false

complexity:
  avg_complexity: 2
  avg_uncertainty: 1
  max_dependencies: 1
  testing_scope: 2
---

# Bolt 001 – Auth Foundation

## Stories
- `001-login-jwt.md` — Login mit E-Mail/Passwort, JWT, Mandantenauswahl
- `002-password-reset.md` — Passwort-Reset via E-Mail
- `005-rbac-middleware.md` — RBAC-Guards für alle geschützten Endpunkte
