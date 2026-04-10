---
id: 007-dev-seed
unit: 001-identity-access
intent: 001-cashflow-core
status: draft
priority: must
created: 2026-04-06T00:00:00Z
assigned_bolt: null
implemented: false
---

# Story: 007-dev-seed

## User Story

**As a** developer
**I want** a seed script that creates an initial admin user from environment variables
**So that** I can start the app locally without manual database setup

## Acceptance Criteria

- [ ] **Given** `SEED_ADMIN_EMAIL` and `SEED_ADMIN_PASSWORD` are set in `.env`, **When** `python -m app.scripts.seed` is run, **Then** admin user is created (or skipped if already exists)
- [ ] **Given** user already exists, **When** seed runs again, **Then** no error, no duplicate — idempotent
- [ ] **Given** `SEED_ADMIN_PASSWORD` shorter than 8 chars, **When** seed runs, **Then** script exits with clear error message
- [ ] **Given** seed completes, **When** login with those credentials, **Then** JWT is returned successfully
- [ ] Seed script is **never run automatically** — must be invoked explicitly
- [ ] `.env.example` contains `SEED_ADMIN_EMAIL` and `SEED_ADMIN_PASSWORD` with placeholder values

## Technical Notes

- Script location: `backend/app/scripts/seed.py`
- Uses the same `create_user` + `accept_invitation` flow — OR directly sets `password_hash` (bcrypt) to bypass invitation (seed-only shortcut, clearly commented)
- `.env.production` must NOT contain `SEED_ADMIN_PASSWORD`
- Add `seed.py` usage to `README.md`

## Edge Cases

| Scenario | Expected Behavior |
|----------|-------------------|
| `SEED_ADMIN_EMAIL` not set | Script exits with: `Missing SEED_ADMIN_EMAIL env var` |
| DB not reachable | Script exits with clear connection error |
| Run in production env (`ENV=production`) | Script refuses to run with warning |

## Dependencies

### Requires
- 001-login-jwt.md (User entity + password hashing)
