---
id: ADR-007
status: accepted
date: 2026-04-06
bolt: 003-tenant-account-mgmt
deciders: [construction-agent]
---

# ADR-007: Remapping-Trigger gibt 202 Accepted zurück (Async, kein Sync-Block)

## Status
Accepted

## Kontext

`POST /accounts/{account_id}/remap` soll das erneute Partner-Matching für alle bereits importierten Buchungen eines Accounts auslösen. Das Re-Matching iteriert über potenziell tausende von Buchungen und führt für jede Pattern-Lookups durch.

Die Frage: Soll der HTTP-Request warten bis das Re-Matching abgeschlossen ist (synchron), oder soll der Request sofort antworten und die Arbeit im Hintergrund geschehen (asynchron)?

## Entscheidung

Wir antworten **sofort mit 202 Accepted** und verarbeiten das Re-Mapping **asynchron**.

**In diesem Bolt (Placeholder-Implementierung):**
- Der Endpoint loggt den Trigger-Auftrag und gibt 202 zurück
- Kein tatsächliches Re-Matching (Partner-Matching-Logik existiert noch nicht)
- Kein persistenter Job-Status

**In einem späteren Bolt (vollständige Implementierung):**
- Job-Queue-Eintrag in DB (Status: pending → running → complete/failed)
- Background-Worker verarbeitet die Queue
- `GET /accounts/{account_id}/remap/status` gibt Status zurück

## Begründung

**Timeout-Risiko**: Synchrones Re-Matching über viele Buchungen kann Sekunden bis Minuten dauern. Standard-HTTP-Timeouts (30s nginx, 60s load balancer) würden Requests abbrechen — auch wenn das Mapping weiterläuft.

**User Experience**: Der Nutzer soll nicht warten. 202 Accepted mit einem Status-Check-Link ist das Standard-Pattern für lang laufende Operationen (RFC 7231).

**Scope-Control**: Die echte Job-Queue-Infrastruktur (Redis, Celery oder einfache DB-Queue) erfordert Entscheidungen über Workers und Deployment — das gehört in einen dedizierten Infrastructure-Bolt. Dieses Bolt liefert das Interface, nicht die Unter-Infrastruktur.

## Alternativen betrachtet

**Synchron blocking**: Einfachste Implementierung, aber Timeout-Risiko bei vielen Buchungen. Nicht akzeptabel für Production.

**WebSocket/SSE für Live-Status**: Zu komplex für MVP. Kann als Enhancement hinzugefügt werden.

**Celery + Redis sofort**: Korrekte long-term Lösung, aber benötigt neue Infrastruktur-Komponenten die für diesen Bolt out of scope sind.

## Konsequenzen

- `POST /accounts/{account_id}/remap` gibt immer `202 Accepted` zurück (nie 200)
- Response-Body enthält `{"message": "Remapping triggered", "account_id": "..."}` (kein Job-ID im Placeholder)
- Später: Response erweitern mit `{"job_id": "...", "status_url": "..."}`
- Kein `RemappingJob`-Model in diesem Bolt — wird in späterem Bolt eingeführt
- Tests prüfen nur Status-Code 202 und Response-Form

## Read When
- Implementierung von Long-Running-Operations in anderen Endpunkten
- Entscheidung ob weitere Bulk-Operationen synchron oder asynchron sein sollen
- Hinzufügen echter Job-Queue-Infrastruktur
- Frontend implementiert Polling auf Remapping-Status
