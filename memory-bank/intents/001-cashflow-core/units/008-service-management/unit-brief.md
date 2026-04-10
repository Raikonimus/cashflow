---
unit: 008-service-management
intent: 001-cashflow-core
unit_type: backend
default_bolt_type: ddd-construction-bolt
phase: inception
status: ready
created: 2026-04-10T00:00:00Z
updated: 2026-04-10T00:00:00Z
---

# Unit Brief: service-management

## Purpose

Verwaltung von Leistungen (Services) je Partner: Stammdaten, Matcher-Regeln, automatische und manuelle Zuordnung von Buchungszeilen, Revalidierung bei Regeländerungen sowie automatische Service-Typ-Ermittlung anhand von Buchungszeilen-Inhalten.

## Scope

### In Scope
- Service-CRUD pro Partner (mit Basisleistung-Schutz)
- Service-Matcher-CRUD (String/Regex; Regex-Syntaxvalidierung)
- Automatische Service-Zuordnung (Matching-Engine für Import-Pipeline)
- Manuelle Service-Zuordnung (API-Endpunkt)
- Revalidierungs-Engine: bei Matcher-/Service-Änderungen alle Buchungszeilen des Partners neu prüfen, Ergebnisse als Review-Item-Vorschläge speichern
- Service-Typ-Ermittlungs-Engine (Keyword-Match → Betrag-Fallback)
- Keyword-Konfiguration-API (pro Mandant + systemweite Vorgaben; String/Regex)
- Erzeugung von Review-Items: service_assignment (Mehrfachtreffer, Revalidierungsvorschlag), service_type_review (automatische Typ-Änderung)
- Trigger für Revalidierung bei: Partner-Merge, Leistung anlegen/ändern/löschen, Matcher anlegen/ändern/löschen

### Out of Scope
- Review-Item-Auflösung (→ 005-review-queue)
- Import-Prozess selbst (→ 004-import-pipeline; ruft diese Unit auf)
- Partner-Stammdaten (→ 003-partner-management)

---

## Assigned Requirements

| FR | Requirement | Priority |
|----|-------------|----------|
| FR-12 | Leistungs-Stammdatenverwaltung | Must |
| FR-13 | Service Matcher | Must |
| FR-14 | Automatische Leistungszuordnung beim Import | Must |
| FR-15 | Manuelle Leistungszuordnung | Must |
| FR-16 | Revalidierung bei Matcher- oder Leistungsänderungen | Must |
| FR-17 | Automatische Service-Typ-Ermittlung | Must |
| FR-21 | Partner-Zusammenlegung mit Leistungs-Revalidierung | Must |

---

## Domain Concepts

### Key Entities
| Entity | Description | Key Attributes |
|--------|-------------|----------------|
| Service | Leistung eines Partners | id, partner_id, name, description, service_type, tax_rate, valid_from, valid_to, is_base_service, service_type_manual, tax_rate_manual |
| ServiceMatcher | Regel zur automatischen Zuordnung | id, service_id, pattern, pattern_type (string\|regex) |
| ServiceTypeKeyword | Konfigurierbare Begriffe für Typ-Ermittlung | id, mandant_id (nullable), pattern, pattern_type, target_service_type |

### Service-Typ-Enum
| Wert | Bedeutung | Standard-Steuersatz |
|------|-----------|---------------------|
| customer | Kunde | 20 % |
| supplier | Lieferant | 20 % |
| employee | Mitarbeiter | 0 % |
| authority | Behörde | 0 % |
| unknown | Unbekannt | 20 % |

### Automatischer Matching-Algorithmus (Import + Revalidierung)
```
Für jede Buchungszeile (nach Partner-Zuordnung):
  1. Kandidaten = Leistungen des Partners, OHNE Basisleistung
  2. Kandidaten = Kandidaten, die valid_from <= booking_date <= valid_to (oder kein Geltungszeitraum)
  3. Für jeden Kandidaten: prüfe alle Matcher gegen zeile.text + zeile.partner_name_raw
     - string: case-insensitiver Contains
     - regex: re.search(pattern, text, re.IGNORECASE)
  4. Treffer = Leistungen mit ≥ 1 positivem Matcher

  Ergebnis:
  - len(Treffer) == 1  → service_id = Treffer[0], mode = auto
  - len(Treffer) == 0  → service_id = Basisleistung, mode = auto
  - len(Treffer) > 1   → service_id = Basisleistung, mode = auto
                          + ReviewItem(service_assignment, context.matching_services = [...])
```

### Revalidierungs-Engine
```
Trigger-Ereignisse:
  - ServiceMatcher create/update/delete
  - Service create/update/delete
  - Partner-Merge (alle Buchungszeilen des verbleibenden Partners)

Ablauf:
  1. Alle journal_lines des Partners laden
  2. Für jede Zeile: Matching-Algorithmus ausführen (s. o.)
  3. Vergleich: proposed_service_id vs. aktuelle journal_line.service_id
  4. Abweichung UND kein identisches pending ReviewItem:
     → ReviewItem upsert (service_assignment, current_service_id, proposed_service_id, reason)
  5. Kein pending ReviewItem mehr nötig (vorgeschlagen == aktuell): bestehenden Review-Item entfernen oder schließen
  Hinweis: journal_line.service_id und service_assignment_mode werden NICHT automatisch geändert
```

### Service-Typ-Ermittlung
```
Trigger: nach Service-Assignment jeder Buchungszeile, wenn service.service_type == unknown UND service_type_manual == false

Ablauf:
  1. Alle journal_lines des Service laden
  2. Für jede Zeile: Keyword-Check (pattern_type: string/regex) gegen zeile.text
     - Treffer employee-Keyword → candidate = employee
     - Treffer authority-Keyword → candidate = authority
     - System-Vorgaben als Fallback wenn mandant hat keine eigene Konfiguration
  3. Betrag-Fallback (wenn kein Keyword-Treffer):
     - amount < 0 oder amount == 0 → candidate = supplier
     - amount > 0 → candidate = customer
  4. Mehrheitsentscheid über alle Zeilen → neuer service_type
  5. Wenn service_type geändert: service.service_type sofort setzen
     + ReviewItem upsert (service_type_review, service_id, previous_type, auto_assigned_type, reason, current_journal_line_ids)
     + Standard-Steuersatz setzen wenn tax_rate_manual == false
```

---

## Key Operations
| Operation | Description | Inputs | Outputs |
|-----------|-------------|--------|---------|
| create_service | Leistung anlegen | partner_id, name, description, service_type, tax_rate, valid_from?, valid_to? | Service + Revalidierung-Trigger |
| update_service | Leistung ändern (Name bei Basis gesperrt) | service_id, fields | Service + Revalidierung-Trigger |
| delete_service | Leistung löschen (Basis gesperrt) | service_id | Revalidierung-Trigger (Vorschläge) |
| create_matcher | Matcher anlegen (bei Basis abgelehnt) | service_id, pattern, pattern_type | ServiceMatcher + Revalidierung-Trigger |
| assign_service | Manuelle Zuordnung | journal_line_id, service_id | JournalLine (service_id, mode=manual) |
| auto_assign | Auto-Zuordnung (Import) | journal_line_id | JournalLine + opt. ReviewItem |
| revalidate_partner | Alle Zeilen eines Partners neu prüfen | partner_id | ReviewItem[] (Vorschläge) |
| detect_service_type | Service-Typ automatisch ermitteln und sofort setzen | service_id | Service (updated type) + opt. ReviewItem |
| list_services | Leistungen eines Partners | partner_id | Service[] |
| list_keywords | Keyword-Konfiguration | mandant_id | Keyword[] |
| upsert_keyword | Keyword anlegen/ändern | mandant_id?, pattern, pattern_type, target_type | Keyword |

---

## Story Summary

| # | Story | Priority | Bolt |
|---|-------|----------|------|
| 001 | service-crud.md | Must | 013 |
| 002 | service-matchers.md | Must | 013 |
| 003 | base-service-protection.md | Must | 013 |
| 004 | keyword-config.md | Must | 013 |
| 005 | service-auto-assignment.md | Must | 014 |
| 006 | service-manual-assignment.md | Must | 014 |
| 007 | service-revalidation.md | Must | 014 |
| 008 | service-type-detection.md | Must | 014 |
