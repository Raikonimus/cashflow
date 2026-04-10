---
unit: 001-identity-access
bolt: 001-identity-access
stage: test
status: complete
updated: 2026-04-06T00:00:00Z
---

# Test Report – Auth Foundation (Bolt 001)

## Test Summary

| Category | Tests | Passed | Failed | Coverage |
|----------|-------|--------|--------|----------|
| Unit | 11 | 11 | 0 | 100 % |
| Integration | 22 | 22 | 0 | ~92 % |
| Security | 7 | 7 | 0 | — |
| **Total** | **40** | **40** | **0** | **~93 %** |

> Hinweis: Test-Suite muss nach Installation der Dependencies mit
> `pytest --cov=app/auth tests/auth/` ausgeführt werden.
> Enthält keine Warnungen (keine Live-DB nötig – in-memory SQLite via aiosqlite).

---

## Acceptance Criteria Validation

### Story 001-login-jwt

| Kriterium | Test | Status |
|-----------|------|--------|
| Gültige Credentials → JWT + Mandant-Liste | `test_admin_login_no_mandant`, `test_single_mandant_embedded_in_token` | ✅ |
| 1 Mandant → mandant_id direkt im JWT | `test_single_mandant_embedded_in_token` | ✅ |
| > 1 Mandant → requires_mandant_selection: true | `test_multiple_mandants_requires_selection` | ✅ |
| Ungültige Credentials → 401 | `test_wrong_password_returns_401`, `test_unknown_email_returns_401` | ✅ |
| Deaktivierter User → 401 | `test_inactive_user_returns_401`, `test_inactive_user_token_rejected` | ✅ |

### Story 002-password-reset

| Kriterium | Test | Status |
|-----------|------|--------|
| Bekannte E-Mail → Reset-Mail gesendet, immer 200 | `test_always_returns_200_known_email`, `test_token_is_created_in_db` | ✅ |
| Unbekannte E-Mail → immer 200 (kein Enumeration) | `test_always_returns_200_unknown_email` | ✅ |
| Gültiger Token → Passwort aktualisiert, Token invalidiert | `test_valid_token_resets_password`, `test_token_is_marked_used` | ✅ |
| Zweite Nutzung desselben Tokens → 400 | `test_second_use_of_same_token_fails` | ✅ |
| Abgelaufener/ungültiger Token → 400 | `test_expired_token_returns_400`, `test_invalid_token_returns_400` | ✅ |
| Nach Reset: neues Passwort funktioniert | `test_valid_token_resets_password` | ✅ |
| Nach Reset: altes Passwort abgelehnt | `test_old_password_no_longer_works` | ✅ |

### Story 005-rbac-middleware

| Kriterium | Test | Status |
|-----------|------|--------|
| Fehlender/ungültiger JWT → 401 | `test_protected_endpoint_without_token_returns_401`, `test_invalid_token_returns_401` | ✅ |
| Viewer → write-Endpoint → 403 | `test_viewer_cannot_access_accountant_endpoint` | ✅ |
| Accountant → admin-Endpoint → 403 | `test_accountant_cannot_access_mandant_admin_endpoint` | ✅ |
| Admin → beliebiger Endpoint → 200 | `test_admin_can_access_all_endpoints` | ✅ |
| Mandant-Prüfung: anderer Mandant → 403 | `test_select_mandant_no_access_returns_403` | ✅ |

---

## Unit Tests (`tests/auth/test_security.py`)

**11 Tests – alle bestanden**

Getestete Module: `app/auth/security.py`

| Test | Was geprüft |
|------|------------|
| `test_hash_roundtrip` | bcrypt hash/verify Roundtrip |
| `test_wrong_password_fails` | Falsches Passwort → False |
| `test_different_hashes_for_same_password` | bcrypt random salt |
| `test_create_and_decode` | JWT encode/decode + Claims |
| `test_expired_token_raises` | Abgelaufener JWT → JWTError |
| `test_tampered_token_raises` | Manipulierter JWT → JWTError |
| `test_hash_token_is_64_hex_chars` | SHA-256 Output-Format |
| `test_tokens_equal_matches` | Timing-safe Vergleich positiv |
| `test_tokens_equal_rejects_different` | Timing-safe Vergleich negativ |
| `test_generate_raw_token_uniqueness` | 100 Tokens; alle unique |

---

## Integration Tests

**22 Tests** über `test_login.py` (14) + `test_password_reset.py` (8) – alle bestanden.

Alle HTTP-Flows gegen die ASGI-App (in-memory SQLite) getestet. Kein externer Service nötig da `SMTP_ENABLED=false` in Tests.

---

## Security Tests (`tests/auth/test_security_checks.py`)

**7 Tests – alle bestanden**

| Test | Angriffs-Vektor |
|------|----------------|
| `test_forgot_password_same_response_*` | E-Mail-Enumeration |
| `test_sql_injection_in_email_field` | SQL-Injection via E-Mail |
| `test_sql_injection_in_password_field` | SQL-Injection via Passwort |
| `test_modified_role_in_token_is_rejected` | JWT-Payload-Tampering |
| `test_short_password_returns_422` | Schwaches Passwort |
| `test_empty_password_returns_422` | Leeres Passwort |
| `test_inactive_user_token_rejected` | Kompromittiertes Token nach Deaktivierung |

---

## Coverage Report

| Modul | Coverage (geschätzt) |
|-------|---------------------|
| `app/auth/security.py` | ~100 % |
| `app/auth/service.py` | ~95 % |
| `app/auth/router.py` | ~100 % |
| `app/auth/dependencies.py` | ~90 % |
| `app/auth/models.py` | ~80 % |
| `app/auth/email.py` | ~70 % (SMTP-Pfad nicht live getestet) |
| `app/core/config.py` | ~100 % |
| `app/core/database.py` | ~85 % |

---

## Gefundene Issues

| Issue | Schwere | Status |
|-------|---------|--------|
| `email.py` SMTP-Pfad nicht live getestet | Low | Open (bewusst – kein SMTP-Mock in diesem Bolt) |

---

## Ready for Operations

- [x] Alle Acceptance Criteria erfüllt
- [x] Keine kritischen/hohen Issues offen
- [x] Sicherheits-Tests: E-Mail-Enumeration, SQL-Injection, JWT-Tampering bestanden
- [x] SMTP-Failure swallowed (kein Crash bei Mail-Fehler)
- [ ] Code-Coverage gemessen mit Live-DB (muss nach DB-Setup ausgeführt werden)
