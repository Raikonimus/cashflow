---
intent: 001-cashflow-core
phase: inception
status: units-decomposed
updated: 2026-04-10T00:00:00Z
---

# Cashflow Core – Unit Decomposition

## Units Overview

Das Intent zerlegt sich in 7 Units: 6 Backend-Services (DDD) + 1 Frontend-Unit.

### Unit 001: identity-access

**Description**: Authentifizierung, User-Management und mandantenbasierte Zugriffskontrolle.

**Assigned FRs**: FR-1, FR-2, FR-11 (teilweise)

**Deliverables**:
- Auth-Endpoints (Login, Logout, Passwort-Reset)
- User-CRUD-API
- Mandant-User-Zuweisung
- JWT-Middleware
- RBAC-Guards für alle anderen Units

**Dependencies**:
- Depends on: –
- Depended by: alle anderen Units (JWT-Middleware)

**Estimated Complexity**: M

---

### Unit 002: tenant-account-mgmt

**Description**: Mandanten- und Kontoverwaltung inkl. CSV-Spalten-Mapping-Konfiguration.

**Assigned FRs**: FR-3, FR-4

**Deliverables**:
- Mandanten-CRUD-API
- Konten-CRUD-API
- Column-Mapping-API (lesen, anlegen, ändern)
- Re-Mapping-Trigger (optionale Neuverarbeitung)

**Dependencies**:
- Depends on: 001-identity-access
- Depended by: 004-import-pipeline, 007-cashflow-ui

**Estimated Complexity**: M

---

### Unit 003: partner-management

**Description**: Partner-Stammdaten, IBAN-/Namensverwaltung, Musterregeln und Partner-Merge.

**Assigned FRs**: FR-7, FR-21

**Note**: Partner-Merge muss nach Zusammenführung eine Leistungs-Revalidierung für alle Buchungszeilen des verbleibenden Partners auslösen (→ FR-21). Die Revalidierungslogik selbst liegt in Unit 008.

**Deliverables**:
- Partner-CRUD-API
- Partner-IBAN- und Name-Verwaltung
- Pattern-API (String/Regex)
- Partner-Merge-API

**Dependencies**:
- Depends on: 001-identity-access
- Depended by: 004-import-pipeline, 006-journal-viewer

**Estimated Complexity**: M

---

### Unit 004: import-pipeline

**Description**: CSV-Upload, Mapping-Anwendung, Partner-Erkennung und Anlage von Buchungszeilen.

**Assigned FRs**: FR-5, FR-6, FR-14

**Note**: Nach der Partner-Erkennung (FR-6) wird die automatische Leistungszuordnung (FR-14) angestoßen. Die eigentliche Matching-Logik liegt in Unit 008; die Import-Pipeline ruft sie auf.

**Deliverables**:
- CSV-Upload-Endpoint (Multipart)
- Mapping-Anwendung (Spaltennamen → interne Felder, unmapped_data JSONB)
- Partner-Matching-Logik (IBAN → Name → Neu)
- Review-Item-Erstellung (partner_name_match)
- Import-Run-Tracking

**Dependencies**:
- Depends on: 001-identity-access, 002-tenant-account-mgmt, 003-partner-management
- Depended by: 005-review-queue, 006-journal-viewer

**Estimated Complexity**: L

---

### Unit 005: review-queue

**Description**: Anzeige und Auflösung von automatischen Entscheidungen mit Unsicherheit.

**Assigned FRs**: FR-8, FR-18, FR-19, FR-20

**Note**: Die Review-Queue verwaltet nun drei Item-Typen: partner_name_match (FR-8), service_assignment (FR-19) und service_type_review (FR-18). Archiv (FR-20) ist ebenfalls Teil dieser Unit.

**Deliverables**:
- Review-Items-API (Liste, Detail, Archiv mit Paging)
- Review-Aktionen: bestätigen, anderer Partner, neuer Partner (partner_name_match)
- Review-Aktionen: bestätigen, anpassen, ablehnen (service_assignment)
- Review-Aktionen: Service-Typ + Steuersatz anpassen und freigeben (service_type_review)
- Aktualisierung von `journal_lines.partner_id` und `journal_lines.service_id`

**Dependencies**:
- Depends on: 001-identity-access, 003-partner-management, 004-import-pipeline, 008-service-management
- Depended by: 007-cashflow-ui

**Estimated Complexity**: M

---

### Unit 006: journal-viewer

**Description**: Buchungszeilen-Abfrage mit Filtern und Bulk-Operationen.

**Assigned FRs**: FR-9, FR-10, FR-11

**Deliverables**:
- Journal-Lines-Query-API (Filter: Konto, Partner, Datum, Status)
- Bulk-Assign-Partner-API
- Audit-Log-API (für Admin/Mandant-Admin)

**Dependencies**:
- Depends on: 001-identity-access, 003-partner-management, 004-import-pipeline
- Depended by: 007-cashflow-ui

**Estimated Complexity**: M

---

### Unit 007: cashflow-ui

**Description**: React + Vite Frontend mit allen Screens und Client-seitiger Logik.

**Assigned FRs**: Alle user-facing FRs (inkl. FR-12 bis FR-22)

**Deliverables**:
- Login-Screen + Mandanten-Auswahl
- User- & Mandantenverwaltung (Admin)
- Import-Screen mit Drag & Drop + Mapping-Editor
- Konto-Verwaltung
- Partner-Verwaltung inkl. Merge und Service-Typ-Icons in Partnerliste
- Leistungsverwaltung (Leistungen + Matcher pro Partner)
- Einstellungen: Keyword-Konfiguration für Service-Typ-Ermittlung
- Review-Queue-Screen (alle drei Item-Typen)
- Buchungszeilen-Liste mit Filtern + Bulk-Aktionen + Service-Zuordnung

**Dependencies**:
- Depends on: alle Backend-Units (001–008)
- Depended by: –

**Estimated Complexity**: XL

---

### Unit 008: service-management

**Description**: Leistungs-Stammdatenverwaltung, Service Matcher, automatische und manuelle Leistungszuordnung, Revalidierung, Service-Typ-Ermittlung, Keyword-Konfiguration und Trigger für Review-Item-Erstellung.

**Assigned FRs**: FR-12, FR-13, FR-14, FR-15, FR-16, FR-17, FR-21

**Deliverables**:
- Service-CRUD-API (inkl. Basisleistung-Schutz)
- Service-Matcher-API (inkl. Regex-Validierung)
- Service-Assignment-API (manuelle Zuordnung)
- Service-Auto-Assignment-Engine (für Import-Pipeline)
- Revalidierungs-Engine (Trigger bei Matcher-/Leistungsänderungen und Partner-Merge; nur Vorschläge, kein Auto-Override)
- Service-Typ-Ermittlungs-Engine (Keyword + Betrag-Fallback)
- Keyword-Konfiguration-API (CRUD, Regex-Validierung)
- Trigger: Review-Item-Erstellung (service_assignment, service_type_review)

**Dependencies**:
- Depends on: 001-identity-access, 003-partner-management
- Depended by: 004-import-pipeline, 005-review-queue, 006-journal-viewer, 007-cashflow-ui

**Estimated Complexity**: L

---

## Unit Dependency Graph

```
[001-identity-access]
        |
        ├──> [002-tenant-account-mgmt]
        │             |
        ├──> [003-partner-management] ──────────────────────┐
        │             |                                      │
        │     ┌───────┘                                      ▼
        │     ▼                                   [008-service-management]
        └──> [004-import-pipeline] <─────────────────────── ┘
                      |                                      │
             ┌────────┴──────────────────────────────────────┤
             ▼                                               ▼
  [005-review-queue] <──────────────────────── ──────────────┘
             │
  [006-journal-viewer]
             │
             └────────┬────────┘
                      ▼
              [007-cashflow-ui]
```

## Execution Order

1. **001-identity-access** (Fundament – alle anderen hängen daran)
2. **002-tenant-account-mgmt** + **003-partner-management** (parallel)
3. **008-service-management** (benötigt 003)
4. **004-import-pipeline** (benötigt 002, 003, 008)
5. **005-review-queue** + **006-journal-viewer** (parallel, benötigen 004, 008)
6. **007-cashflow-ui** (baut auf alle Backend-Units auf)
