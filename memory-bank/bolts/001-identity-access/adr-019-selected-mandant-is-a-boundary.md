---
id: ADR-019
title: Der gewählte Mandant ist eine Grenze, nicht bloß Anzeigezustand
status: accepted
date: 2026-09-10
bolt: 001-identity-access
deciders: [Raimund]
---

# ADR-019: Der gewählte Mandant ist eine Grenze, nicht bloß Anzeigezustand

## Status

Accepted.

## Kontext

Nach dem Anmelden wählt ein Nutzer mit mehreren Mandanten einen aus; die Wahl landet als
`mandant_id` im Token. Alle 89 mandantengebundenen Endpunkte nehmen ihre `mandant_id`
aber aus dem **Pfad**. `require_mandant_access` prüfte bis 2026-09-10 nur die
*Mitgliedschaft* — nie die Übereinstimmung von Pfad und Token.

Ein Nutzer mit zwei Mandanten konnte deshalb mit einem für A gewählten Token die
Endpunkte von B ansprechen. Für die Berechtigung folgerichtig: Er darf beide. Es hieß
aber, dass die Auswahl nichts **erzwingt** — sie war Anzeigezustand. Das war Befund M10
der Mandantenfähigkeitsanalyse und dort ausdrücklich als offene Entscheidung geführt.

## Entscheidung

`require_mandant_access` vergleicht **zuerst** die `mandant_id` aus dem Token mit der aus
dem Pfad und prüft **danach** die Zugehörigkeit. Bei Abweichung: HTTP 403. Fehlt die
`mandant_id` im Token: HTTP 403.

Die Reihenfolge ist Teil der Entscheidung. Ein Admin umgeht die
Zugehörigkeitsprüfung — die Ausnahme, deren Verweis auf ADR-001 ins Leere geht
(Befund M17) —, er umgeht aber **nicht** die Auswahl. Auch er muss sagen, in welchem
Mandanten er arbeitet. Sonst hätte gerade die Rolle mit der größten Reichweite die
schwächste Bindung an das, was die Oberfläche anzeigt.

## Begründung

**Die Auswahl behauptet einen Zustand, den sie nicht herstellte.** Der Umschalter im
Kopfbereich sagt „Sie arbeiten in Mandant A". Ohne Vergleich war das eine Aussage über
das Frontend, nicht über das System.

**Es kostet nichts an Funktion**, und das aus zwei unabhängigen Gründen.

*Erstens* kann die Auswahl vom Token nicht abweichen: Der Zustandsspeicher **leitet sie
daraus ab** (`sanitizeAuthState`: `mandants.find(m => m.id === user.mandant_id)`). Das
Frontend schickt also nie ein Paar, das der Vergleich abweisen würde.

*Zweitens* verhindert das Frontend genau das, was der Vergleich jetzt abweist.
`MandantRequiredRoute` in `src/router/PrivateRoute.tsx` prüft `!user?.mandant_id` — den
Token-Anspruch selbst — und schickt auf `/login/select-mandant`, bevor irgendeine
mandantengebundene Seite lädt. Das Backend weist ab, was die Oberfläche schon nicht
zulässt; die Schranke war einseitig, nicht neu.

Belegt hat das die Umstellung selbst: Von 310 Tests fielen genau die sechs, die das alte
Verhalten beschrieben — kein einziger fachlicher.

**Der Schutz greift dort, wo das Frontend nicht ist.** Ein von Hand gebauter Aufruf, ein
Skript, ein zwischengespeichertes Token: Bisher wirkte jedes davon auf jeden Mandanten,
dem der Nutzer zugeordnet war. Jetzt auf einen.

## Alternativen betrachtet

**Anzeigezustand bleiben, aber als Entscheidung festhalten.** Kein Code, nur ein
Entscheidungssatz. Verteidigbar — die Berechtigung ist ja korrekt —, hätte aber die
Lücke zwischen dem, was die Oberfläche behauptet, und dem, was gilt, dauerhaft
festgeschrieben.

**Erzwingen, aber Admins ausnehmen.** Vermeidet den Zwischenschritt für ein noch nicht
gewähltes Admin-Token, hielte aber zwei Sonderregeln nebeneinander: Der Admin umgeht
dann die Zugehörigkeit *und* die Auswahl. Verworfen, weil die zweite Ausnahme keinen
eigenen Grund hat.

## Konsequenzen

- Ein Token **ohne** `mandant_id` erreicht keinen mandantengebundenen Endpunkt. Das
  trifft zwei Zustände: mehrere Mandanten und noch keine Auswahl, oder gar keine
  Zuordnung (Befund M6). In beiden gibt es auch nichts anzuzeigen.
- Für den Admin ein Zwischenschritt mehr: `login` liefert ihm alle aktiven Mandanten,
  `select-mandant` gibt ihm zu jedem ein Token. Seine Reichweite ist unverändert.
- Der Mandantenwechsel im Betrieb (Entscheidung E4, `MandantSwitcher`) funktioniert
  unverändert — er holt ohnehin ein neues Token.
- Zwei Browserfenster auf zwei Mandanten sind weiterhin nicht möglich. Sie waren es
  vorher auch nicht: Der Zustandsspeicher liegt im `localStorage` und ist je Ursprung
  gemeinsam.
- Festgehalten in `tests/tenancy/test_token_und_pfad.py`. Wird die Entscheidung
  zurückgenommen, schlagen diese Tests an.

## Read When

- Änderungen an `require_mandant_access` oder am Aufbau des Tokens
- Fragen, warum ein gültiges Token 403 liefert
- Planung von Zugriffen ohne Frontend (Skripte, Integrationen, Dienstkonten)
- Diskussion über Row-Level-Security oder einen Query-Interceptor
