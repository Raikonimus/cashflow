---
stage: domain-model
bolt: 001-identity-access
created: 2026-04-06T00:00:00Z
---

# Domain Model: identity-access (Bolt 001 – Auth Foundation)

## Scope

Dieser Bolt deckt drei Stories ab:
- `001-login-jwt` — Login, Mandantenauswahl, JWT-Ausstellung
- `002-password-reset` — Passwort-Reset via E-Mail
- `005-rbac-middleware` — RBAC-Guards für alle geschützten Endpunkte

---

## Entities

- **User**: Systemnutzer mit Rolle und Aktivierungsstatus
  - Properties: `id (UUID)`, `email (str, unique)`, `password_hash (str|null)`, `role (UserRole)`, `is_active (bool)`, `created_at`, `updated_at`
  - Business Rules:
    - `password_hash` ist `null` bis Einladung angenommen (Story 006, nicht in diesem Bolt)
    - Deaktivierte User (`is_active=false`) dürfen sich nicht einloggen
    - Rolle bestimmt den Zugriff auf alle Endpunkte (RBAC)

- **Mandant**: Unternehmen/Tenant — wird von Unit 002 vollständig verwaltet; hier nur als Referenz
  - Properties: `id (UUID)`, `name (str)`, `is_active (bool)`
  - Nutzung in diesem Bolt: Mandant-Lookup für JWT-Claim und Mandanten-Auswahl

- **MandantUser**: Zuweisung User ↔ Mandant (n:m)
  - Properties: `mandant_id (UUID)`, `user_id (UUID)`, `created_at`
  - Business Rules:
    - Admin hat implizit Zugriff auf alle Mandanten (kein MandantUser-Eintrag nötig)
    - Alle anderen Rollen brauchen expliziten Eintrag

- **PasswordResetToken**: Zeitlich begrenztes Token für Passwort-Reset
  - Properties: `id (UUID)`, `user_id (UUID)`, `token_hash (str)`, `expires_at (datetime)`, `used_at (datetime|null)`
  - Business Rules:
    - Token ist single-use: nach Verwendung wird `used_at` gesetzt
    - Abgelaufene Token (`expires_at < now()`) werden abgelehnt
    - Gültigkeit: 1 Stunde (konfigurierbar via `PASSWORD_RESET_EXPIRE_MINUTES`)

---

## Value Objects

- **UserRole**: Enum mit vier Werten
  - `admin` — Systemweiter Vollzugriff
  - `mandant_admin` — Vollzugriff auf zugewiesene Mandanten; darf nur Accountant/Viewer anlegen
  - `accountant` — Import und Datenpflege
  - `viewer` — Nur-Lesen

- **JwtPayload**: Unveränderlicher Wertecontainer für JWT-Claims
  - Properties: `user_id (UUID)`, `role (UserRole)`, `mandant_id (UUID|null)`, `exp (int)`
  - Validation: `exp` muss in der Zukunft liegen; `mandant_id` nur gesetzt wenn User genau 1 Mandant hat

- **Email**: Validierter E-Mail-String
  - Constraints: RFC 5322-Format; lowercase; max 254 Zeichen

---

## Aggregates

- **UserAggregate** (Root: `User`)
  - Members: `User`, `MandantUser[]`
  - Invariants:
    - User mit Rolle `admin` hat keine MandantUser-Einträge (Admin ist systemweit)
    - `email` ist eindeutig im System
    - Rolle kann nur von Admin oder Mandant-Admin geändert werden (mit Einschränkungen)

- **PasswordResetAggregate** (Root: `PasswordResetToken`)
  - Members: `PasswordResetToken`
  - Invariants:
    - Pro User maximal 1 offenes (ungenutztes, nicht abgelaufenes) Reset-Token zu je einem Zeitpunkt; ältere werden invalidiert beim Anlegen eines neuen

---

## Domain Events

- **UserLoggedIn**: Ausgelöst bei erfolgreichem Login
  - Trigger: POST /auth/login mit gültigen Credentials
  - Payload: `user_id`, `mandant_id (opt)`, `ip_address`, `timestamp`
  - Verwendet von: Audit-Log-Service

- **LoginFailed**: Ausgelöst bei fehlgeschlagenem Login-Versuch
  - Trigger: POST /auth/login mit ungültigen Credentials oder deaktiviertem User
  - Payload: `email`, `reason`, `ip_address`, `timestamp`
  - Verwendet von: Audit-Log-Service

- **PasswordResetRequested**: Ausgelöst wenn Reset-Link angefordert wird
  - Trigger: POST /auth/forgot-password
  - Payload: `user_id`, `token_hash`, `expires_at`
  - Verwendet von: E-Mail-Service

- **PasswordResetCompleted**: Ausgelöst wenn neues Passwort gesetzt wird
  - Trigger: POST /auth/reset-password mit gültigem Token
  - Payload: `user_id`, `timestamp`
  - Verwendet von: Audit-Log-Service

---

## Domain Services

- **AuthService**: Authentifizierungs-Logik
  - Operations:
    - `login(email, password) → JwtPayload | AuthError`
    - `select_mandant(user_id, mandant_id) → JwtPayload | AuthError`
    - `verify_token(token) → JwtPayload | TokenError`
  - Dependencies: `UserRepository`, `MandantUserRepository`, `JwtTokenService`

- **PasswordResetService**: Reset-Flow-Logik
  - Operations:
    - `request_reset(email) → void` (fire-and-forget, kein Fehler bei unbekannter E-Mail)
    - `reset_password(token, new_password) → void | ResetError`
  - Dependencies: `UserRepository`, `PasswordResetTokenRepository`, `EmailService`

- **RbacService**: Zugriffssteuerung
  - Operations:
    - `require_role(required_role: UserRole) → FastAPI Dependency`
    - `require_mandant_access(mandant_id: UUID) → FastAPI Dependency`
    - `check_role_hierarchy(actor_role, target_role) → bool`
  - Business Rules:
    - `admin` darf alle Rollen verwalten
    - `mandant_admin` darf nur `accountant` und `viewer` anlegen/verwalten
    - Rollenhierarchie: admin > mandant_admin > accountant > viewer

- **JwtTokenService**: JWT-Erzeugung und -Validierung
  - Operations:
    - `create_token(payload: JwtPayload) → str`
    - `decode_token(token: str) → JwtPayload | TokenError`
  - Dependencies: `SECRET_KEY`, `ALGORITHM` (HS256), `JWT_EXPIRE_MINUTES`

---

## Repository Interfaces

- **UserRepository**
  - Entity: `User`
  - Methods: `find_by_id(id) → User|None`, `find_by_email(email) → User|None`, `save(user) → User`, `list_by_mandant(mandant_id) → User[]`

- **MandantUserRepository**
  - Entity: `MandantUser`
  - Methods: `find_mandants_for_user(user_id) → Mandant[]`, `exists(user_id, mandant_id) → bool`, `add(user_id, mandant_id) → void`, `remove(user_id, mandant_id) → void`

- **PasswordResetTokenRepository**
  - Entity: `PasswordResetToken`
  - Methods: `find_valid_token(token_hash) → PasswordResetToken|None`, `save(token) → void`, `invalidate_all_for_user(user_id) → void`

---

## Ubiquitous Language

| Term | Definition |
|------|-----------|
| **Mandant** | Ein Unternehmen/Tenant, dessen Daten im System verwaltet werden |
| **Rolle** | Berechtigungsstufe eines Users (admin, mandant_admin, accountant, viewer) |
| **JWT** | JSON Web Token — signierter Token, der Identität und Rolle des Users kodiert |
| **RBAC** | Role-Based Access Control — Zugriffsentscheidungen basierend auf der Rolle |
| **Reset-Token** | Zeitlich begrenzter, single-use Token für Passwort-Reset |
| **Mandantenauswahl** | Schritt nach Login falls User > 1 Mandant hat; setzt `mandant_id` im JWT |
| **Guard** | FastAPI Dependency, die Rolle/Mandant-Zugehörigkeit vor Request-Verarbeitung prüft |
