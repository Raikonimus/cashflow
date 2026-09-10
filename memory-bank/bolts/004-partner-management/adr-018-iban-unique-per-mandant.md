---
id: ADR-018
title: IBAN und Kontonummer sind je Mandant eindeutig, nicht global
status: accepted
date: 2026-09-10
bolt: 004-partner-management
deciders: [Raimund]
supersedes: ADR-008
---

# ADR-018: IBAN und Kontonummer sind je Mandant eindeutig, nicht global

## Status

Accepted. **Ersetzt ADR-008** („Partner-IBAN ist global unique").

## Kontext

ADR-008 legte 2026-04-06 fest, dass eine IBAN über alle Mandanten hinweg nur einem
Partner gehören darf. Die Begründung: Eine IBAN identifiziert weltweit eindeutig ein
Bankkonto, und das Import-Matching soll zu einer Buchungs-IBAN genau einen Partner
zurückgeben.

Das Code-Review vom 2026-09-09 hat einen Widerspruch aufgedeckt (Befund A1-3): Der
Import-Lookup filtert auf den **eigenen** Mandanten — richtig, denn ein Partner gehört
einem Mandanten. Beides zusammen ergibt keinen Schutz, sondern einen blinden Fleck:

* Registriert Mandant A die IBAN von Amazon, findet der Lookup von Mandant B sie nicht
  (richtig — sie hängt an A's Partner).
* Die Registrierung für B überspringt sie stillschweigend (falsch).
* B's Partner „Amazon" bekommt die IBAN nie und wird **dauerhaft** nur über den
  Namen erkannt — bei jedem weiteren Import erneut, ohne jeden Hinweis.

Die Namenserkennung ist schwächer und produziert Review-Arbeit, die nie aufhört.

Erschwerend: Der **manuelle** Weg (`_add_iban_entity`) wirft HTTP 409, der **Import**weg
schweigt. Dieselbe Regel, zwei Verhalten.

Dieselbe Frage stellte sich für Konten (`accounts.iban`). ADR-008 nannte sie unter „Read
When" ausdrücklich als offene Folgefrage, entschieden wurde sie nie. `create_account`
prüfte global und wies mit 409 ab, was ein anderer Mandant führte — ohne sagen zu
können, welcher.

## Entscheidung

Eindeutigkeit **je Mandant**, für alle drei Identifier:

| Tabelle | vorher | nachher |
|---|---|---|
| `partner_ibans` | `UNIQUE (iban)` | `UNIQUE (mandant_id, iban)` |
| `partner_accounts` | `UNIQUE (blz, account_number)` | `UNIQUE (mandant_id, blz, account_number)` |
| `accounts.iban` | global im Service geprüft | je Mandant im Service geprüft |

`partner_ibans` und `partner_accounts` bekommen eine eigene `mandant_id` — aus dem
Partner übernommen. Migration 029.

## Begründung

**Das Argument von ADR-008 trägt nicht.** Es begründet globale Eindeutigkeit mit
deterministischem Matching. Deterministisch ist das Matching aber schon dadurch, dass
der Lookup je Mandant filtert: Innerhalb eines Mandanten gibt es zu einer IBAN genau
einen Partner, und das gilt mit der neuen Regel weiter. Die globale Eindeutigkeit
erzeugte keine zusätzliche Bestimmtheit — sie nahm dem zweiten Mandanten die
IBAN-Erkennung weg.

**Die mandantenübergreifende Sicht gibt es fachlich nicht.** ADR-008 führte als
Datenqualitätsargument an, dass es ein Fehler sei, wenn Mandant B A's Amazon-IBAN einem
Partner „Microsoft" zuordnet. Das stimmt — nur sieht diesen Fehler niemand, weil keine
Auswertung über Mandanten hinweg läuft. Der 409 erzwang keine Korrektheit, er verhinderte
eine legitime Eintragung.

**Der Normalfall war der Verlierer.** Amazon, die Telekom und das Finanzamt haben genau
eine IBAN. Dass mehrere Mandanten an dieselbe zahlen, ist nicht die Ausnahme, sondern
die Regel — und genau dieser Fall funktionierte nicht.

**Bei Konten ist der Fall noch klarer.** Zwei Firmen können ein Bankkonto tatsächlich
gemeinsam nutzen (Holding und Tochter), und derselbe Steuerberater erfasst dann beide.
Die globale Prüfung machte das unmöglich, ohne eine Entscheidung hinter sich zu haben.

## Alternativen betrachtet

**Global bleiben, aber laut scheitern** (der Importweg legt ein Review-Item an statt
stillschweigend zu überspringen). Behebt die Stille, nicht die Sache: B bekäme weiterhin
nie IBAN-Erkennung, nur würde jemand davon erfahren — bei jedem Import erneut. Der
Review-Stapel wüchse um Einträge, die niemand auflösen kann.

**Keine Eindeutigkeit.** Führt innerhalb eines Mandanten zu mehreren Partnern pro IBAN
und macht das Matching mehrdeutig. Das Argument von ADR-008 gilt hier weiter — nur eben
je Mandant.

## Konsequenzen

- `partner_ibans` und `partner_accounts` führen eine denormalisierte `mandant_id`. Eine
  Eindeutigkeit über Tabellengrenzen kann keine Datenbank ausdrücken; ohne die Spalte
  müsste die Regel in der Anwendung stehen, und genau das ist der Zustand, den
  Stufe 5 des Mandantenfähigkeitsplans ablöst.
- Die Kopie kann nur auseinanderlaufen, wenn ein Partner den Mandanten wechselt. Kein
  Pfad im System tut das: `partners.mandant_id` wird beim Anlegen gesetzt und nie
  geändert; das Zusammenführen läuft innerhalb eines Mandanten (ADR-009).
- HTTP 409 bleibt, gilt aber nur noch innerhalb des Mandanten. Er ist damit erstmals
  erklärbar: Der Nutzer sieht den Partner, der die IBAN schon führt.
- Migration 029 **löscht** Zeilen in `partner_ibans`, deren Partner es nicht mehr gibt
  (19 in der Entwicklungsdatenbank, siehe Befund M19). Ohne Partner gibt es keinen
  Mandanten zum Nachtragen, und die Zeilen sind auf jedem Pfad unerreichbar.
- Der Rückweg ist versperrt, sobald zwei Mandanten dieselbe IBAN führen. `downgrade()`
  scheitert dann — absichtlich, statt eine Zeile zu verwerfen.

## Read When

- Implementierung von IBAN- oder Kontonummer-basierten Lookups im Import-Matching
- Hinzufügen weiterer Identifier, die einen Partner erkennen
- Fragen zu geteilten Stammdaten zwischen Mandanten
- Bevor ADR-008 zitiert wird — es gilt nicht mehr
