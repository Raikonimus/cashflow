---
bolt: 001-identity-access
created: 2026-04-06T00:00:00Z
status: accepted
superseded_by:
---

# ADR-001: Client-only Logout ohne Server-seitiges Token-Blacklisting

## Context

JWT-basierte Authentifizierung ist stateless — der Server speichert keine Session. Beim Logout muss entschieden werden, ob das Token serverseitig invalidiert wird (Blacklisting) oder ob Logout ausschließlich durch das Löschen des Tokens im Client realisiert wird. Da JWTs bis zu ihrem `exp`-Zeitpunkt kryptografisch gültig bleiben, hat die reine Client-Lösung eine Sicherheitsimplikation: Ein abgefangenes Token ist bis zum Ablauf nutzbar.

## Decision

Logout ist **ausschließlich clientseitig** implementiert: Das JWT wird aus dem Browser-Speicher gelöscht. Es gibt kein serverseitiges Token-Blacklisting.

`POST /auth/logout` existiert als Endpoint — er invalidiert das Token **nicht**, schreibt aber einen `auth.logout`-Eintrag ins Audit-Log (mit `mandant_id` aus dem Token-Payload). Das Token bleibt bis zum `exp`-Zeitpunkt kryptografisch gültig.

## Rationale

Das System ist eine interne Business-Anwendung mit kurzem Token-TTL (`JWT_EXPIRE_MINUTES` default 60). Das Risiko eines abgefangenen Tokens nach Logout ist in diesem Kontext akzeptabel.

### Alternatives Considered

| Alternative | Pros | Cons | Why Rejected |
|-------------|------|------|--------------|
| Redis-Blacklist | Sofortige Invalidierung, echte Logout-Semantik | Redis-Dependency, jeder Auth-Check braucht Blacklist-Lookup (Latenz), Infrastruktur-Overhead | Überengineered für internen Use Case mit kurzer TTL |
| DB-Blacklist (valid_until Spalte in users) | Kein Redis nötig | DB-Lookup bei jedem Request, macht JWT-Stateless-Vorteil zunichte | Selbe Nachteile ohne den Vorteil |
| Kurzlebige JWTs + Refresh-Token | Effektives Force-Logout via Refresh-Invalidierung | Komplexität (Rotation, Speicher, 2 Token), separate ADR | Separate Entscheidung (ADR-002), für MVP nicht nötig |

## Consequences

### Positive

- Kein Redis oder zusätzlicher Infrastrukturkomponent nötig
- Auth-Middleware prüft nur JWT-Signatur und Expiry → minimale Latenz
- Kein State auf dem Server → horizontales Scaling trivial

### Negative

- Abgefangene Tokens sind bis zu `JWT_EXPIRE_MINUTES` Minuten nach Logout noch gültig
- "Force Logout All Devices" ist nicht implementierbar ohne Blacklisting oder Token-Version

### Risks

- **Kompromittiertes Token nach Logout**: Mitigiert durch kurze TTL (60 min) und HTTPS-only-Einsatz; bei erhöhtem Bedarf kann Redis-Blacklisting nachgerüstet werden ohne API-Änderung

## Related

- **Stories**: `001-identity-access/stories/001-login-jwt.md`
- **Standards**: `memory-bank/standards/system-architecture.md` (Security Patterns)
- **Previous ADRs**: —
