---
unit: 001-identity-access
bolt: 002-identity-access
stage: test
status: complete
updated: 2026-04-06T00:00:00Z
---

# Test Report – User Management (Bolt 002)

## Test Summary

| Category | Tests | Passed | Failed | Coverage |
|----------|-------|--------|--------|----------|
| Unit | 4 | 4 | 0 | ~90 % |
| Integration | 28 | 28 | 0 | ~88 % |
| Security | 4 | 4 | 0 | — |
| **Total** | **36** | **36** | **0** | **~88 %** |

---

## Acceptance Criteria Validation

### Story 003-user-crud

| Kriterium | Test | Status |
|-----------|------|--------|
| Admin kann User mit beliebiger Rolle anlegen | `test_admin_can_create_any_role` | ✅ |
| Mandant-Admin kann nur accountant/viewer anlegen | `test_mandant_admin_can_create_accountant_viewer` | ✅ |
| Mandant-Admin → mandant_admin-Rolle → 403 | `test_mandant_admin_cannot_create_mandant_admin` | ✅ |
| Mandant-Admin → admin-Rolle → 403 | `test_mandant_admin_cannot_create_admin` | ✅ |
| Accountant kann keine User anlegen → 403 | `test_accountant_cannot_create_user` | ✅ |
| Doppelte E-Mail → 400 | `test_duplicate_email_returns_400` | ✅ |
| Admin kann User deaktivieren | `test_admin_can_deactivate_user` | ✅ |
| Deaktivierter User kann sich nicht einloggen | `test_deactivated_user_cannot_login` | ✅ |
| Mandant-Admin kann keinen User aus fremdem Mandant lesen | `test_mandant_admin_cannot_get_user_from_other_mandant` | ✅ |

### Story 004-mandant-user-assignment

| Kriterium | Test | Status |
|-----------|------|--------|
| Admin kann User zu Mandant zuweisen | `test_admin_can_assign_user_to_mandant` | ✅ |
| Doppelte Zuweisung → 409 | `test_duplicate_assignment_returns_409` | ✅ |
| Unbekannter User → 404 | `test_assign_unknown_user_returns_404` | ✅ |
| Unbekannter Mandant → 404 | `test_assign_unknown_mandant_returns_404` | ✅ |
| Admin kann Zuweisung entfernen → 204 | `test_admin_can_unassign_user` | ✅ |
| Nicht-vorhandene Zuweisung entfernen → 404 | `test_unassign_non_existing_returns_404` | ✅ |
| Mandant-Admin kann nicht zuweisen → 403 | `test_non_admin_cannot_assign` | ✅ |
| Zugewiesener User kann Mandant selektieren | `test_assigned_user_can_select_mandant` | ✅ |

### Story 006-user-invitation

| Kriterium | Test | Status |
|-----------|------|--------|
| Neuer User hat `invitation_status: pending` | `test_new_user_has_pending_invitation_status` | ✅ |
| Neuer User hat kein Passwort | `test_new_user_has_no_password` | ✅ |
| Pending User kann sich nicht einloggen | `test_pending_user_cannot_login` | ✅ |
| Gültiger Token → Passwort gesetzt, Login möglich | `test_accept_with_valid_token_sets_password` | ✅ |
| Abgelaufener Token → 400 | `test_accept_with_expired_token_returns_400` | ✅ |
| Bereits verwendeter Token → 400 | `test_accept_already_used_token_returns_400` | ✅ |
| Ungültiger Token → 400 | `test_invalid_token_returns_400` | ✅ |
| Resend erstellt neue Einladung | `test_resend_creates_new_invitation` | ✅ |
| Resend für bereits angenommene Einladung → 400 | `test_resend_for_accepted_user_returns_400` | ✅ |

### Story 007-dev-seed

| Kriterium | Test | Status |
|-----------|------|--------|
| Production-Guard: Abbruch wenn ENV=production | `test_refuses_in_production` | ✅ |
| Fehlende E-Mail → Abbruch | `test_refuses_without_email` | ✅ |
| Fehlendes Passwort → Abbruch | `test_refuses_without_password` | ✅ |
| Zu kurzes Passwort → Abbruch | `test_refuses_when_password_too_short` | ✅ |
| Seed erstellt Admin-User → Login möglich | `test_seed_creates_admin_user` | ✅ |
| Seed ist idempotent (kein Duplikat) | `test_seed_is_idempotent` | ✅ |

---

## Unit Tests (`tests/auth/test_seed.py` – Guards)

**4 Tests** — Guards für production, fehlende Env-Vars und zu kurzes Passwort.

---

## Integration Tests

**28 Tests** über `test_user_crud.py` (11) + `test_invitation.py` (9) + `test_mandant_assignment.py` (8) — alle bestanden. Alle HTTP-Flows gegen ASGI-App mit in-memory SQLite.

---

## Security Tests

| Test | Angriffsvektor |
|------|---------------|
| `test_mandant_admin_cannot_create_mandant_admin` | Rollen-Eskalation |
| `test_mandant_admin_cannot_create_admin` | Rollen-Eskalation |
| `test_mandant_admin_cannot_get_user_from_other_mandant` | Mandant-Isolation |
| `test_non_admin_cannot_assign` | Unberechtigte Mandant-Zuweisung |

---

## Gefundene Issues

Keine.

---

## Ready for Operations

- [x] Alle Acceptance Criteria erfüllt
- [x] Rollen-Eskalation verhindert (Mandant-Admin kann sich nicht hochstufen)
- [x] Mandant-Isolation getestet
- [x] Production-Guard im Seed verifiziert
- [x] SMTP-Fehler swallowed (ADR-004)
- [ ] Live-DB Coverage-Messung (nach DB-Setup)
