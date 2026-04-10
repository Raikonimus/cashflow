---
intent: 001-cashflow-core
phase: inception
status: context-defined
updated: 2026-04-06T00:00:00Z
---

# Cashflow Core – System Context

## System Overview

Ein mandantenfähiges Web-Service zur Verwaltung von Bankbuchungen und Kreditkartentransaktionen. Buchungszeilen werden aus CSV-Exporten verschiedener Finanzinstitute importiert, automatisch Partnerunternehmen zugeordnet und in einer einheitlichen Datenstruktur gespeichert. Ein Review-Workflow sichert die Qualität automatischer Entscheidungen.

## Context Diagram

```mermaid
C4Context
    title System Context – Cashflow Core

    Person(admin, "Admin", "Vollzugriff auf alle Mandanten und User")
    Person(mandant_admin, "Mandant-Admin", "Verwaltet Daten eines oder mehrerer Mandanten")
    Person(accountant, "Accountant", "Importiert Buchungszeilen, pflegt Partner")
    Person(viewer, "Viewer", "Nur-Lesen: Buchungszeilen und Reports")

    System(cashflow, "Cashflow Service", "Mandantenfähige Buchungszeilen-Verwaltung mit Partner-Matching, Import und Review-Workflow")

    System_Ext(bank_csv, "Bank / Kreditkarten-Provider", "Exportiert Kontoauszüge als CSV (Format variiert je Anbieter)")
    System_Ext(mail, "E-Mail-Server (SMTP)", "Versand von Passwort-Reset-Mails")
    System_Ext(postgres, "PostgreSQL", "Primäre Datenbank (lokal / managed)")

    Rel(admin, cashflow, "Verwaltet User, Mandanten, sieht Audit-Log")
    Rel(mandant_admin, cashflow, "Verwaltet Konten, Partner, Accountants/Viewer")
    Rel(accountant, cashflow, "Importiert CSV, bearbeitet Review-Queue, Buchungszeilen")
    Rel(viewer, cashflow, "Liest Buchungszeilen und Partner")
    Rel(cashflow, bank_csv, "Empfängt CSV-Upload vom Nutzer (kein direkter API-Aufruf)")
    Rel(cashflow, mail, "Sendet Passwort-Reset-Mail", "SMTP")
    Rel(cashflow, postgres, "Liest und schreibt alle Daten", "asyncpg/SQLModel")
```

## Actors

| Actor | Typ | Beschreibung |
|-------|-----|-------------|
| Admin | Human User | Systemweiter Vollzugriff |
| Mandant-Admin | Human User | Vollzugriff auf zugewiesene Mandanten |
| Accountant | Human User | Import und Datenpflege |
| Viewer | Human User | Nur-Lesen |

## External Integrations

| System | Richtung | Daten | Protokoll |
|--------|----------|-------|-----------|
| Bank/Kreditkarten-CSV | Inbound (via User-Upload) | CSV-Kontoauszüge, variables Format | HTTP Multipart Upload |
| E-Mail-Server (SMTP) | Outbound | Passwort-Reset-Link | SMTP |
| PostgreSQL | Both | Alle persistenten Daten | asyncpg (TCP) |

## High-Level Constraints

- CSV-Format ist nicht standardisiert; Spalten-Mapping muss flexibel konfigurierbar sein
- Mandantenisolation muss serverseitig bei jedem Request erzwungen werden
- `unmapped_data` JSONB-Spalte sichert Rückwärtskompatibilität bei Mapping-Änderungen
- Kein externer Auth-Provider; JWT selbst implementiert

## Key NFR Goals

- **Sicherheit**: Null Cross-Tenant-Datenlecks; Audit-Log unveränderlich
- **Performance**: Import ≥ 500 Zeilen/s; API p95 < 300 ms
- **Zuverlässigkeit**: Import-Transaktion atomar (alles oder rollback)
- **Nachvollziehbarkeit**: Alle schreibenden Aktionen im Audit-Log
