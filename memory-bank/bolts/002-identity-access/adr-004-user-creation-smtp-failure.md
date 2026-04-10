---
bolt: 002-identity-access
created: 2026-04-06T00:00:00Z
status: accepted
superseded_by:
---

# ADR-004: User-Anlage nicht rückgängig bei SMTP-Fehler

## Context

Beim Anlegen eines neuen Users muss direkt im Anschluss eine Einladungs-E-Mail versendet werden. E-Mail-Versand über SMTP ist ein externer I/O-Aufruf und kann fehlschlagen (SMTP-Server nicht erreichbar, Rate-Limit, etc.). Die Frage ist: Soll ein SMTP-Fehler den gesamten User-Anlage-Vorgang rückgängig machen (atomare Transaktion über DB + Mail), oder soll die DB-Schreiboperation abgeschlossen werden und der Mail-Fehler separat behandelt werden?

Dasselbe Pattern gilt für alle zukünftigen E-Mail-triggernden Flows: Passwort-Reset (Bolt 001), Einladung (Bolt 002), zukünftige Benachrichtigungen.

## Decision

**Der User wird in der DB angelegt, auch wenn der E-Mail-Versand fehlschlägt.** SMTP-Fehler werden geloggt (structlog, level=error). Der Admin kann die Einladung über `POST /users/:id/resend-invitation` manuell erneut senden. Kein DB-Rollback bei Mail-Fehler.

## Rationale

Eine echte Transaktion über Datenbank und E-Mail ist mit standardmäßigem SMTP nicht möglich — SMTP kennt kein Two-Phase-Commit. Ein DB-Rollback bei Mail-Fehler würde den User aus der Datenbank löschen, obwohl der Fehler kein logisches Problem darstellt, sondern ein infrastrukturelles. Der Resend-Endpoint ist die saubere Lösung für den Fehlerfall.

### Alternatives Considered

| Alternative | Pros | Cons | Why Rejected |
|-------------|------|------|--------------|
| DB-Rollback bei SMTP-Fehler | "Alles oder nichts"-Semantik | User verschwindet bei temporärem Mail-Problem; Admin muss Vorgang wiederholen; SMTP-Fehler → kein User in DB | Zu streng für ein infrastrukturelles Problem |
| Outbox-Pattern (Mail-Job in DB-Transaktion) | Echte Atomizität | Redis/Queue-Dependency (Celery, ARQ, etc.), erhebliche Infrastruktur-Komplexität | Überengineered für MVP; kann nachgerüstet werden |
| Synchrones Warten auf SMTP-Bestätigung | Sicher | Blockiert Request, SMTP ACK ≠ zugestellt | Kein Mehrwert; SMTP ACK ist keine Zustellgarantie |

## Consequences

### Positive

- User-Anlage ist robust gegenüber temporären Mail-Ausfällen
- Admin hat vollständige Kontrolle über Einladungs-Lifecycle via `resend-invitation`
- Kein externer Queue-Dienst nötig im MVP

### Negative

- Einladung kann verloren gehen wenn SMTP dauerhaft ausfällt und Admin nicht auf Resend-Endpoint hingewiesen wird
- "Pending"-User in DB ohne je eine E-Mail erhalten zu haben (bis Resend)

### Risks

- **Stille Fehler**: Mitigiert durch strukturiertes Logging (structlog, level=error) und `invitation_status: pending` im GET /users/:id — Admin sieht, dass Einladung noch offen ist

## Related

- **Stories**: `001-identity-access/stories/006-user-invitation.md`
- **Standards**: `memory-bank/standards/system-architecture.md`
- **Previous ADRs**: ADR-003 (Token-Hash-Storage), ADR-001 (Client-only Logout)
