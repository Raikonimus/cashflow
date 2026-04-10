---
id: ADR-010
status: accepted
date: 2026-04-06
bolt: 006-import-core
deciders: [construction-agent]
---

# ADR-010: CSV-Import ist synchron (kein Background-Job) für MVP

## Status
Accepted

## Kontext

Der Import-Endpunkt `POST /imports` nimmt eine oder mehrere CSV-Dateien entgegen und verarbeitet sie: Spalten-Mapping anwenden, JournalLines anlegen, Dubletten überspringen. Bei großen CSV-Dateien (z. B. Jahresauszug mit 5000+ Zeilen) kann dieser Prozess merkliche Zeit in Anspruch nehmen.

Ähnlich gelagert ist ADR-007 (Remapping-Trigger → 202 Accepted). Dort wurde ebenfalls die Frage synchron vs. asynchron entschieden — allerdings unter anderen Voraussetzungen (Remapping betrifft potenziell alle historischen Zeilen eines Kontos, nicht nur Neue).

Soll der Import-Upload synchron verarbeitet werden (Antwort nach Abschluss) oder asynchron (sofortige 202-Antwort + Hintergrundverarbeitung)?

## Entscheidung

CSV-Import wird **synchron** verarbeitet. Der HTTP-Request kehrt erst zurück, wenn alle Dateien vollständig verarbeitet sind. Response: `201 Created` mit der Liste der `ImportRun`-Objekte.

Eine maximale Dateigröße von 10 MB pro Datei begrenzt den schlimmsten Fall. Bei synchroner Verarbeitung unter dieser Grenze sind Timeouts in einer lokalen/kleinen Deployment-Umgebung unkritisch.

## Rationale

**Einfachheit für MVP**: Asynchrone Verarbeitung erfordert eine Job-Queue (Celery + Redis oder ARQ), Polling-Endpoints, Frontend-Polling-Logik und Fehlerbehandlung für abgebrochene Jobs. Das ist erheblicher Infrastruktur-Overhead für eine Funktion, die im MVP selten mehrere Sekunden dauern wird.

**Unterschied zu ADR-007 (Remapping)**: Remapping iteriert über *alle existierenden* Buchungszeilen eines Kontos — potenziell Zehntausende. Ein CSV-Upload enthält typischerweise einen Monat oder ein Quartal = 30–500 Zeilen. Das Risiko eines Timeouts ist deutlich geringer.

**Erweiterungspfad klar**: `ImportRun.status` hat schon `pending → processing → completed/failed`. Wenn Async nötig wird, ändert sich nur der Service (Task statt direkter Verarbeitung) und der Endpoint gibt `202` zurück. Das Datenmodell muss nicht geändert werden.

**Observability ohne Queue**: Synchron gibt der Client sofort Feedback über `row_count`, `skipped_count`, `error_count`. Bei Async müsste der Client pollen.

### Alternatives Considered

| Alternative | Pros | Cons | Why Rejected |
|-------------|------|------|--------------|
| Asynchron via Celery + Redis | Skalierbar; kein Timeout-Risiko | Redis-Infrastruktur; Celery-Setup; Polling-Frontend-Logik; erheblicher Overhead | Overengineering für MVP-Dateigrößen |
| Asynchron via ARQ (async Python) | Leichtgewichtiger als Celery; kein Celery-Broker | Immer noch Redis + Polling nötig | Immer noch Infrastruktur-Overhead |
| Streaming Response (SSE) | Live-Feedback pro Zeile | Komplexes Frontend-Handling; schwierig zu testen | Overengineering |

## Consequences

### Positive
- Keine Queue-Infrastruktur notwendig
- Sofortiges vollständiges Feedback im Response (row_count, errors)
- Einfaches Frontend: normaler POST → direktes Ergebnis
- Leicht testbar (pytest, keine Worker-Prozesse)

### Negative
- Bei sehr großen CSV-Dateien (>1000 Zeilen in langsamer Umgebung) könnte der Request spürbar lange dauern
- Horizontal scaling der Worker wäre bei synchronem Blocking weniger effizient

### Risks
- Timeout bei großen Dateien in Produktionsumgebung mit niedrigem Worker-Timeout. **Mitigation**: 10-MB-Limit pro Datei (FastAPI default); Nginx/Load-Balancer Timeout auf 60s setzen; bei Bedarf auf Async migrieren (Datenmodell ist bereits dafür vorbereitet).

## Related

- **Stories**: `001-csv-upload-endpoint.md`, `004-import-run-tracking.md`
- **Previous ADRs**: ADR-007 (Remapping ist async mit 202 — anderes Risikoniveau)
- **Read when**: Hinzufügen von Background-Jobs/Task-Queue; Skalierungsprobleme mit Upload; Frontend implementiert Upload-Fortschrittsanzeige; Entscheidung ob andere Long-Running-Operations synchron sein sollen
