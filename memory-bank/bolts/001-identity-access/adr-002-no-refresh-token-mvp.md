---
bolt: 001-identity-access
created: 2026-04-06T00:00:00Z
status: accepted
superseded_by:
---

# ADR-002: Kein Refresh-Token im MVP

## Context

JWT-basierte Auth kennt zwei Token-Modelle:
1. **Long-lived Access Token**: Einfach, aber Token bleibt lange gültig wenn kompromittiert
2. **Short-lived Access Token + Refresh Token**: Security Best Practice, aber höhere Implementierungskomplexität (Rotation, Speicher, Silent-Refresh im Frontend)

Die Entscheidung bestimmt maßgeblich die Frontend-Architektur (Token-Storage, Auto-Refresh-Logic) und Backend-Infrastruktur (Refresh-Token-Store).

## Decision

Im MVP gibt es **keinen Refresh-Token-Mechanismus**. Access-Token-TTL ist per `JWT_EXPIRE_MINUTES` konfigurierbar (Default: 60 Minuten). Nach Ablauf muss der User sich neu einloggen. Es gibt keinen Silent-Refresh.

## Rationale

Cashflow ist eine interne Business-Web-App mit aktiven Work-Sessions von typischerweise 30–120 Minuten. Eine Session-Unterbrechung durch Token-Ablauf ist tolerierbar und wird durch eine verständliche Fehlermeldung ("Session abgelaufen, bitte erneut einloggen") behandelt. Das Risiko rechtfertigt die erhöhte Komplexität nicht im MVP-Stadium.

### Alternatives Considered

| Alternative | Pros | Cons | Why Rejected |
|-------------|------|------|--------------|
| Refresh-Token in HttpOnly-Cookie + Rotation | Industrie-Best-Practice, Force-Logout möglich, sichere Token-Erneuerung | Redis/DB für Refresh-Token-Store, Frontend Silent-Refresh-Logik, Token-Rotation-Complexity | MVP-Overhead; kann sauber nachgerüstet werden durch neues Endpoint-Paar |
| Sehr langer Access-Token TTL (z.B. 7 Tage) | "Kein Logout"-Gefühl für User | Security Anti-Pattern, kompromittiertes Token lange aktiv | Inakzeptabeles Sicherheitsrisiko |

## Consequences

### Positive

- Keine Token-Rotation-Logik im Backend
- Kein Token-Store (Redis/DB) für Refresh-Tokens nötig
- Frontend-Auth-Logik deutlich einfacher (kein Axios-Interceptor für Token-Refresh)
- Deployment ohne Redis möglich

### Negative

- User wird nach `JWT_EXPIRE_MINUTES` ausgeloggt, auch bei aktiver Nutzung
- Kein "Remember me"-Feature möglich ohne Refresh-Token
- Force-Logout (z.B. bei Passwort-Änderung) nicht vollständig möglich (vgl. ADR-001)

### Risks

- **UX-Degradation bei langen Sessions**: Mitigiert durch konfigurierbares TTL (Operator kann höheren Wert setzen); bei Bedarf kann Refresh-Token-Flow ohne Breaking Changes hinzugefügt werden (`POST /auth/refresh`)

## Related

- **Stories**: `001-identity-access/stories/001-login-jwt.md`
- **Standards**: `memory-bank/standards/system-architecture.md` (Security Patterns)
- **Previous ADRs**: ADR-001 (Client-only Logout)
