---
id: ADR-012
title: ReviewItem-Status-Lifecycle (open → resolved)
status: accepted
date: 2026-04-07
bolt: 007-partner-matching
---

## Context

`review_items` ist ein neues Pattern im System. Der Status-Lifecycle (wer darf auflösen, welche Status-Werte gibt es, was passiert nach Auflösung) ist noch nirgends definiert und beeinflusst den späteren `008-review-queue`-Bolt direkt.

## Decision

**Zwei Status-Werte für MVP**: `open` (default bei Anlage) und `resolved` (manuell durch Benutzer gesetzt).

- Review-Items werden ausschließlich vom `PartnerMatchingService` beim Import angelegt (status=`open`).
- Auflösung (`open → resolved`) ist der `008-review-queue`-Bolt und erfolgt durch Benutzer mit mindestens `accountant`-Rolle.
- Kein automatisches Auflösen durch das System (keine Hintergrund-Jobs in diesem Bolt).
- `resolved`-Items bleiben in der DB (kein Hard-Delete); historische Nachvollziehbarkeit.

## Alternatives Considered

- **Mehr Status-Werte** (`dismissed`, `auto_resolved`): Zu früh für MVP — `008-review-queue` kann den Lifecycle erweitern.
- **Soft-Delete statt `resolved`**: Inkonsistent mit dem Ziel der Audit-Nachvollziehbarkeit.
- **Kein Status-Feld** (bool `is_resolved`): Weniger erweiterbar; abgelehnt.

## Consequences

- `review_items`-Tabelle: `status VARCHAR(20) NOT NULL DEFAULT 'open'`.
- `008-review-queue`-Bolt erhält einen klaren Vertrag: er konsumiert `open`-Items und setzt sie auf `resolved`.
- Kein zusätzliches `resolved_at`/`resolved_by` in diesem Bolt (spätere Erweiterung wenn nötig).

## Read When

`008-review-queue`-Implementierung; Queries auf offene Review-Items; Frage ob Review-Items automatisch aufgelöst werden können; Auditlog-Anforderungen für Review-Entscheidungen.
