# Code-Review — Befunde

Stand: 2026-09-09 · Konzept: [code-review-konzept.md](code-review-konzept.md)

---

## Etappe 1 — Mandantentrennung (A1)

### Vorgehen

Die Trennung ist in cashflow **nicht strukturell erzwungen**: keine Row-Level-Security,
kein Query-Interceptor. Jede Query muss ihren Mandantenbezug selbst mitbringen. Geprüft
wurde deshalb maschinell, nicht stichprobenweise — `backend/checks/check_tenancy.py`
liest den AST des gesamten Backends und stellt drei Fragen:

1. Filtert jede Query auf einer mandantengebundenen Tabelle auf den Mandanten?
2. Erreicht bei Endpunkten mit einer **zweiten** Kennung im Pfad die `mandant_id`
   überhaupt den Service?
3. Validieren öffentliche Service-Methoden die Eltern-Kennung, die sie entgegennehmen?

Frage 2 und 3 haben die beiden echten Fehler gefunden. Frage 1 diente der Triage.

### Datenmodell: zwei Klassen von Tabellen

| Klasse | Tabellen | Absicherung |
|---|---|---|
| **direkt gebunden** (eigene `mandant_id`) | `Account`, `Partner`, `ImportRun`, `ReviewItem`, `AuditLog`, `ServiceForecastRule`, `ForecastPlannedItem`, `ForecastSnapshot`, `ServiceGroup`, `ServiceGroupAssignment`, `ServiceTypeKeyword`, `MandantUser` | Filter in der Query |
| **transitiv gebunden** | `JournalLine`, `JournalLineSplit`, `Service`, `ServiceMatcher`, `PartnerIban`, `PartnerAccount`, `PartnerName`, `ColumnMappingConfig`, `AccountExcludedIdentifier` | Join auf die Elterntabelle **oder** vorher validierte Eltern-Kennung |

Die zweite Klasse ist die riskante. `JournalLine` — die zentrale Buchungstabelle — hat
**keine** eigene `mandant_id`; der Bezug hängt an `account_id → Account.mandant_id`.
Beide gefundenen Fehler liegen genau dort.

### Ergebnis der maschinellen Prüfung

263 Queries, 96 Endpunkte, 9 Service-Module. Nach Triage:

| Klasse | Anzahl | Bewertung |
|---|---|---|
| Query filtert korrekt | 98 | — |
| Tabelle ohne Mandantenbezug | 20 | nicht anwendbar |
| transitiv, Eltern-Kennung im Aufrufkontext validiert | 102 | tragfähig, aber fragil (Befund A1-4) |
| gemeldet und einzeln gelesen | 43 | siehe unten |

Von den 43 gelesenen Stellen waren 38 korrekt (Nachfilterung in Python, Validierung durch
die aufrufende Funktion, oder bewusste globale Abfrage nach ADR-008). Fünf ergaben die
vier Befunde unten.

---

## A1-1 — Fremde Importläufe lesbar · **kritisch** · behoben

**Ort:** [app/imports/service.py:790](../backend/app/imports/service.py#L790) (`get_run`),
[:796](../backend/app/imports/service.py#L796) (`list_runs`),
[app/imports/router.py](../backend/app/imports/router.py)

**Behauptung:** Beide Endpunkte filtern ausschließlich auf `account_id`. Die `mandant_id`
aus dem Pfad wurde nie an den Service durchgereicht. `require_mandant_access` prüft nur,
ob der Nutzer den Mandanten aus dem Pfad betreten darf — nicht, ob die `account_id` im
selben Pfad zu diesem Mandanten gehört.

**Fehlerszenario:** Ein regulärer Nutzer von Mandant A ruft auf

```
GET /api/v1/mandants/{A}/accounts/{Konto-von-B}/imports/{Lauf-von-B}
```

Antwort vor dem Fix: **HTTP 200** mit Dateiname, Zeilenzahl, Status, `account_id` und
`user_id` des fremden Imports. Für die Liste dasselbe. Die `account_id` musste dafür nur
erraten oder aus einem früheren Kontakt bekannt sein — eine UUID, aber kein Geheimnis.

**Ursache:** `upload()` im selben Service prüft korrekt (`# Verify account belongs to
mandant`). Die beiden Lesepfade wurden später ergänzt und haben die Prüfung nicht
übernommen.

**Behoben:** Die Prüfung liegt jetzt in `_require_account(account_id, mandant_id)`, das
alle drei Pfade verwenden. Zusätzlich filtern beide Queries auf `ImportRun.mandant_id`.
404 statt 403, damit die Existenz fremder Konten nicht verraten wird — wie im übrigen
Code.

**Test:** [tests/imports/test_tenancy_import_runs.py](../backend/tests/imports/test_tenancy_import_runs.py) — ohne den Fix rot.

---

## A1-2 — Fremde Buchungen überschreibbar · **kritisch** · behoben

**Ort:** [app/tenants/service.py:567](../backend/app/tenants/service.py#L567)
(`apply_excluded_identifiers`)

**Behauptung:** Dieselbe Lücke auf einem **schreibenden** Pfad. Die Methode bekommt
`mandant_id` übergeben, benutzt sie aber nur, um sie an das Matching weiterzureichen —
nie zur Prüfung des Kontos. Vier Schwester-Endpunkte (`column-mapping`, `remap`,
`excluded-identifiers`) rufen im Router `svc.get_account(account_id, mandant_id)` als
Wächter auf; dieser eine nicht.

**Fehlerszenario:** Ein Nutzer von Mandant A ruft auf

```
POST /api/v1/mandants/{A}/accounts/{Konto-von-B}/excluded-identifiers/apply
```

Antwort vor dem Fix: **HTTP 200 — `{"affected": 1, "1 Buchungszeile(n) wurden neu
zugeordnet."}`**. Die Buchungszeilen von Mandant B wurden durch das Matching von
Mandant A neu zugeordnet — also fremden Partnern zugewiesen oder neue Partner in
fremden Daten angelegt. Schreibend und nicht ohne Weiteres rückgängig zu machen.

**Behoben:** `await self.get_account(account_id, mandant_id)` vor dem ersten Zugriff.

**Test:** [tests/tenants/test_tenancy_apply_excluded.py](../backend/tests/tenants/test_tenancy_apply_excluded.py) — prüft Statuscode *und* dass die fremde Zeile unverändert bleibt.

---

## A1-3 — Global eindeutige IBAN blockiert fremde Mandanten still · **hoch** · offen

**Ort:** [app/imports/matching.py:326](../backend/app/imports/matching.py#L326)
(`_maybe_add_iban`), [:348](../backend/app/imports/matching.py#L348)
(`_maybe_add_account`), [app/review/service.py:270](../backend/app/review/service.py#L270)
(`confirm`, ADR-013)

**Behauptung:** Zwei Regeln stehen sich im Weg. ADR-008 macht die IBAN **global**
eindeutig. Der Import-Lookup filtert dagegen korrekt auf den **eigenen** Mandanten
(`Partner.mandant_id == mandant_id`). Registriert Mandant A eine IBAN, dann

* findet der Lookup von Mandant B sie nicht (richtig — sie gehört A),
* und die Registrierung für B überspringt sie stillschweigend (falsch).

Der Partner von Mandant B bekommt die IBAN nie und wird nie per IBAN erkannt.

**Fehlerszenario:** Mandant A hat Amazon mit `DE89…3000` erfasst. Mandant B importiert
eine Amazon-Zahlung mit derselben IBAN. Erster Import: Partner „Amazon" wird per Name
angelegt, die IBAN nicht registriert. Zweiter Import: Ergebnis ist `name_match` statt
`iban_match` — dauerhaft, bei jedem weiteren Import, ohne Hinweis. Die Namenserkennung
ist schwächer und produziert Review-Arbeit, die nie aufhört.

**Warum offen:** Der Fix ist eine Entscheidung über ADR-008, keine Mechanik. Zwei Wege:

1. **IBAN pro Mandant eindeutig** (Compound-Key + Migration). Kehrt ADR-008 um; dessen
   Begründung („eine IBAN identifiziert weltweit ein Konto") gilt weiter, trifft aber
   die mandantenübergreifende Sicht, die es fachlich gar nicht gibt.
2. **Globale Eindeutigkeit behalten, aber nicht stillschweigend scheitern** — der Import
   legt ein Review-Item an, statt nichts zu tun. ADR-008 verspricht für den manuellen
   Weg genau das (HTTP 409); der Importweg hält das Versprechen nicht.

Bemerkenswert: Der manuelle Weg (`_add_iban_entity`) wirft 409, der Importweg schweigt.
Dieselbe Regel, zwei Verhalten.

**Test:** [tests/imports/test_tenancy_iban_registration.py](../backend/tests/imports/test_tenancy_iban_registration.py) — als `xfail(strict=True)` hinterlegt, damit der Befund
dokumentiert bleibt und die Suite grün ist. Wird der Fehler behoben, schlägt der
`xfail` an und erinnert daran, die Markierung zu entfernen.

---

## A1-4 — Mandantenfilter in Python statt in SQL · **mittel** · offen

**Ort:** u. a. [app/partners/service.py:336](../backend/app/partners/service.py#L336)
(`preview_iban`), [:442](../backend/app/partners/service.py#L442)
(`add_iban_with_reassign`), [:553](../backend/app/partners/service.py#L553)
(`preview_account`), [:670](../backend/app/partners/service.py#L670)
(`add_account_with_reassign`)

**Behauptung:** Diese Funktionen sind **korrekt**, aber auf fragile Weise. Sie laden
Buchungszeilen ohne Mandantenfilter und sieben danach in Python:

```python
account_ids = set(... Account.id where Account.mandant_id == mandant_id ...)
lines = [ln for ln in lines if ln.account_id in account_ids]
```

**Fehlerszenario:** Kein aktueller. Das Risiko ist die nächste Änderung: Der Filter steht
bis zu zehn Zeilen von der Query entfernt, wird von nichts erzwungen, und ein früher
`return`, ein neuer Zweig oder eine herausgezogene Hilfsfunktion lassen ihn verschwinden —
ohne dass ein Test es merkt. Genau so sind A1-1 und A1-2 entstanden: als jemand einen
zweiten Pfad neben einen korrekten gelegt hat.

Dazu kommt die Wirkung auf die Datenmenge: Die Fallback-Suche `partner_iban_raw ILIKE
'%…%'` läuft über die Buchungen **aller** Mandanten, bevor gesiebt wird.

**Vorschlag:** `JournalLine` über einen Join auf `Account` in der Query filtern. Ein
gemeinsamer Helfer (`_lines_of_mandant(mandant_id)`), der die Join-Bedingung kapselt,
macht die Regel erzwingbar statt merkbar.

---

## Was die Prüfung dauerhaft hinterlässt

`backend/checks/check_tenancy.py` bleibt im Repo und läuft künftig in CI:

```
python checks/check_tenancy.py --strict
```

`--strict` bricht ab, sobald eine Query auf einer direkt gebundenen Tabelle ohne Filter
auftaucht oder ein Endpunkt mit zweiter Kennung die `mandant_id` nicht durchreicht.
Der aktuelle Stand: **0 Endpunkte** mit ungeprüfter zweiter Kennung, 2 Service-Methoden
mit nicht maschinell erkennbarer Validierung (beide gelesen und in Ordnung —
`get_rule` validiert gegen einen mandantengebundenen Kontext,
`create_manual_assignment_reviews_for_partner` gegen die aufrufende Funktion).

Das Skript ersetzt kein Lesen. Es sorgt dafür, dass die 263 Queries nicht noch einmal
von Hand durchgesehen werden müssen — und dass die 264. auffällt.

---

## Offen aus Etappe 1

| Punkt | Entscheidung nötig |
|---|---|
| A1-3 | ADR-008 umkehren oder den Importweg 409/Review-Item werfen lassen? |
| A1-4 | Join-Helfer einführen — ja/nein? Betrifft vier Funktionen. |
| Konto-IBAN | `create_account` prüft die IBAN ebenfalls global (409 „IBAN already in use"), ohne dass eine ADR das festhält. ADR-008 hat die Frage für Accounts ausdrücklich offengelassen. Zwei Firmen desselben Eigentümers mit einem gemeinsamen Konto können es nicht beide erfassen. |
