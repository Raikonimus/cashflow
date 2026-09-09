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

---

## Vorgemerkt: Mandantenfähigkeit prüfen und sicherstellen

**Status: offen — Umsetzung erst nach Abschluss des Reviews.** Entschieden am 2026-09-09.

Etappe 1 hat die Mandantentrennung an den Stellen geprüft, an denen sie *im Code*
passieren muss, und zwei kritische Löcher geschlossen. Offen bleibt die Stufe darüber:
Ist das System als Ganzes mandantenfähig — und zwar so, dass es nicht an der Sorgfalt
einzelner Queries hängt?

Auslöser ist die Beobachtung aus der Analyse zu A1-3: Die Entwicklungsdatenbank hat
**einen** Mandanten. Alles, was zwischen Mandanten schiefgehen kann, ist damit heute
unbeobachtbar — kein Test, kein Nutzer und keine Datenlage würde es zeigen. Beide in
Etappe 1 gefundenen Fehler waren von dieser Art: real, ausnutzbar, und trotz 452 grüner
Tests unentdeckt.

Was zu diesem Punkt gehört:

| Frage | Heutiger Stand |
|---|---|
| Erzwingt die Struktur die Trennung, oder nur die Disziplin? | nur die Disziplin — keine Row-Level-Security, kein Query-Interceptor, 184 Queries mit eigenem Filter |
| Sind die zentralen Tabellen direkt oder transitiv gebunden? | `JournalLine`, `Service`, `PartnerIban`, `PartnerAccount` u. a. nur transitiv (siehe A1-4) |
| Kennen die Eindeutigkeits-Schlüssel den Mandanten? | nein — `partner_ibans`, `partner_accounts` und `accounts` sind global eindeutig (ADR-008) |
| Gibt es Tests mit zwei Mandanten? | erst die drei aus Etappe 1 |
| Läuft die Anwendung je produktiv mit mehr als einem Mandanten? | zu klären — davon hängt die Dringlichkeit von allem hier ab |

Die letzte Zeile ist die wichtigste. Bleibt es dauerhaft bei einem Mandanten, ist der
gesamte Komplex eine Vorsichtsmaßnahme ohne Gegenwartsnutzen. Kommt ein zweiter dazu,
muss die Trennung *vorher* strukturell stehen — nachträglich lässt sich nicht feststellen,
welche Daten schon vermischt wurden, weil die Fehler leise sind.

Die Befunde A1-3 und A1-4 sowie die Konto-IBAN-Frage sind Teilaspekte davon und werden
zusammen mit diesem Punkt entschieden, nicht einzeln vorab.

---

# Etappe 2 — Geldrichtigkeit (A2)

## Vorgehen

Geprüft wurde, wo Geld den exakten Rechenweg verlässt: Datentypen, Rundungsstellen,
Aggregationsreihenfolge, Vorzeichen, Währung. Maschinell, wo möglich; gelesen, wo
nicht. Alle Zahlen unten sind gegen die Entwicklungsdatenbank gerechnet, nicht
konstruiert.

## Was in Ordnung ist

Das Fundament trägt, und zwar besser als erwartet:

| Prüfung | Ergebnis |
|---|---|
| `float` im Backend | **0 Vorkommen** — ausnahmslos `Decimal` |
| Geldspalten | durchgängig `Numeric(15, 2)` |
| Rundungsstellen | nur 5 im gesamten Backend, alle an der Ausgabe |
| Aggregation | Summen laufen über ungerundete Werte, gerundet wird zuletzt |
| Vorzeichen | konsistent — `value > 0 → inflow`, `< 0 → outflow`, `net = inflow + outflow` |
| Aufteilung auf mehrere Leistungen | letzter Split bekommt den Rest, Summe bleibt exakt |
| Steuersatz 0 % (102 Leistungen) | Divisor 1, keine Division durch Null; der Nullfall ist zusätzlich abgefangen |
| Fremdwährung | bewusst ausgeschlossen **und** auf der Seite ausgewiesen — kein stiller Verlust |
| Unsicherheitsband | Formel korrekt (siehe unten) |

**Der JS-Float im Frontend ist geprüft und unbedenklich.** `sumAmounts` parst
Geldstrings zu `number` und summiert. Für die auftretenden Größenordnungen ist das
sicher: 400 Zufallsbeträge in float64 summiert ergeben denselben Wert wie exakte
Cent-Arithmetik, und die klassische `(1.005).toFixed(2)`-Falle ist nicht erreichbar,
weil die Eingaben schon auf zwei Stellen gerundet ankommen. Die Grenze sei genannt:
Das gilt, solange die Strings zweistellig sind und das Ergebnis nicht weiterdividiert
wird.

**Die Unsicherheitsaggregation ist mathematisch richtig.** Für gleichkorrelierte
Terme gilt `Var(ΣXᵢ) = Σσᵢ² + 2ρ·Σ_{i<j}σᵢσⱼ = (1−ρ)·Σσᵢ² + ρ·(Σσᵢ)²` — genau die
implementierte Formel, mit den korrekten Grenzfällen ρ=0 (Quadratur) und ρ=1
(einfache Summe). Alle Abweichungen gehen als Betrag ein, die Varianz kann nicht
negativ werden, und die Wurzel ist zusätzlich abgesichert. Ob ρ=0,5 der richtige Wert
ist, bleibt eine empirische Frage — belegt ist er gegen sechs Monate Realität.

---

## A2-1 — Seite und Excel-Export weisen verschiedene Jahressummen aus · **mittel** · behoben

**Ort:** [journal/service.py:873](../backend/app/journal/service.py#L873) (Netto-Berechnung),
[IncomeExpensePage.tsx:155](../frontend/src/pages/cashflow/IncomeExpensePage.tsx#L155)
(`sumAmounts`), [income-expense-excel.ts:135](../frontend/src/pages/cashflow/income-expense-excel.ts#L135)
(Total-Formel)

**Behauptung:** Für dieselbe Zahl gibt es drei Rechenwege und zwei Ergebnisse.

| Ansicht | Jahressumme netto |
|---|---|
| Seite, ein Jahr | `round(jahresbrutto / divisor)` — vom Backend |
| Seite, mehrere Jahre | Summe der angezeigten Jahreswerte |
| Excel-Export | `=SUMME(Monatsspalten)` — Excel-Formel, die Backend-Summe wird verworfen |

Ursache ist die Netto-Berechnung: `netto = brutto / (1 + Steuersatz/100)` liefert bei
20 % fast immer periodische Dezimalzahlen. Gerundet wird korrekt erst bei der Ausgabe —
dadurch ist `round(Σ brutto / d)` aber nicht dasselbe wie `Σ round(brutto / d)`.

**Fehlerszenario:** Zwölf Monatsbuchungen à 100,00 € brutto, 20 % USt.

```
Monatszelle angezeigt :    83,33
12 × davon            :   999,96
Jahressumme angezeigt : 1.000,00
```

Der Nutzer sieht zwölfmal 83,33 und darunter 1.000,00. Exportiert er dieselbe
Ansicht, rechnet Excel 999,96.

**Auf den echten Daten** (Entwicklungsdatenbank, Stand 2026-09-09):

| Jahr | Bereich | Seite | Excel | Differenz |
|---|---|---|---|---|
| 2025 | Einnahmen | 728.214,75 | 728.214,76 | +0,01 |
| 2025 | Ausgaben | −958.930,03 | −958.930,06 | −0,03 |
| 2025 | neutral | 15.494,61 | 15.494,62 | +0,01 |
| 2026 | Einnahmen | 731.762,65 | 731.762,65 | — |
| 2026 | **Ausgaben** | **−923.957,69** | **−923.957,85** | **−0,16** |
| 2026 | neutral | 5.242,99 | 5.242,98 | −0,01 |

Fünf von sechs Summen weichen ab. 29 von 408 Zeilen addieren sich in der
Einjahresansicht nicht auf ihre eigene Jahreszelle.

**Einordnung:** Es geht um Cent, nicht um Euro, und keine gespeicherte Zahl ist
falsch. Der Schaden ist Vertrauen: Wer eine Spalte nachrechnet oder den Export gegen
den Bildschirm hält, findet eine Differenz und weiß nicht, welcher Zahl er glauben
soll. Genau die Klasse „still das Falsche" aus Abschnitt 2 des Konzepts.

**Behoben — anders als ursprünglich vorgeschlagen.** Der erste Vorschlag war, den
Restcent auf die Monate zu verteilen. Das hätte nur die Zeilenrichtung geheilt: Die
Spalten (Leistungszeilen → Zwischensumme → Gesamtsumme) gingen weiterhin nicht auf,
weil dort dasselbe Problem eine Ebene höher auftritt.

Umgesetzt ist stattdessen die Regel, die beide Richtungen zugleich löst: **Netto wird
genau einmal gerundet, auf Zellenebene, und alles darüber entsteht durch Summieren.**
Die Jahreszelle ist die Summe der zwölf angezeigten Monate, die Zwischensumme die
Summe der angezeigten Leistungszeilen, die Gesamtsumme die Summe der Zwischensummen.

Der Preis ist benannt und im Code dokumentiert: Die Jahreszelle netto ist nicht mehr
exakt `jahresbrutto / divisor`, sondern kann davon um wenige Cent abweichen. Das ist
der bewusste Tausch — eine Tabelle, die aufgeht, gegen eine Jahressumme, die niemand
nachrechnet.

Nebeneffekt ohne Zusatzarbeit: Der Excel-Export brauchte keine Änderung. Er summiert
die Monate ohnehin per Formel und stimmt jetzt von selbst mit der Seite überein.

**Nachweis auf den echten Daten, nach der Änderung:**

| | vorher | nachher |
|---|---|---|
| Zeilen, deren Monate sich nicht zur Jahreszelle addieren | 29 von 408 | **0** |
| Summe der Zeilen minus Zwischensummen | −0,04 | **0,00** |
| Summe der Zwischensummen minus Gesamtsumme | −0,01 | **0,00** |
| Abweichung Seite ↔ Excel (6 Summen) | bis 0,16 € in 5 von 6 | **0,00 in allen 6** |

**Test:** [tests/journal/test_netto_summen.py](../backend/tests/journal/test_netto_summen.py) —
ohne den Fix rot, mit Gegenprobe für brutto.

---

## A2-2 — Zwei Rundungsverfahren nebeneinander · **niedrig** · behoben

**Ort:** [services/service.py:1890](../backend/app/services/service.py#L1890)

**Behauptung:** `_replace_splits` ruft `quantize(Decimal("0.01"))` **ohne**
`rounding=` auf und erbt damit den Kontext-Standard `ROUND_HALF_EVEN`. Überall sonst
steht ausdrücklich `ROUND_HALF_UP`.

**Fehlerszenario:** Kein Betrag wird falsch — der letzte Split fängt die Differenz
auf, die Summe bleibt exakt. Aber bei 0,05 € auf zwei Leistungen entsteht 0,02 / 0,03,
während dieselbe Zahl in der Anzeige auf 0,03 gerundet würde. Das Risiko ist die
nächste Änderung: Wer die Restausgleich-Zeile entfernt oder das Verfahren kopiert,
erbt eine Rundung, die im Rest des Systems nicht gilt.

**Behoben:** `_round_money()` in `services/service.py` macht den Modus explizit und
trägt die Begründung als Docstring. Für die Summe verhaltensneutral, für den einzelnen
Split jetzt dieselbe Zahl wie in der Anzeige.

---

## A2-3 — `base_currency` ist fest verdrahtet · **niedrig** · latent

**Ort:** [journal/service.py:495](../backend/app/journal/service.py#L495),
[:617](../backend/app/journal/service.py#L617)

`base_currency = "EUR"` steht zweimal als Literal im Code, während Konten ein eigenes
`currency`-Feld führen. Ein Mandant mit einem Konto in CHF bekäme eine vollständig
leere Matrix — alle Buchungen fielen unter „ausgeschlossene Fremdwährung".

**Heute unerreichbar:** Beide Konten und alle 3.689 Buchungen sind EUR. Der Hinweis
auf ausgeschlossene Währungen würde erscheinen, es wäre also nicht lautlos — aber
auch nicht als Fehler erkennbar.

Gehört sachlich zum vorgemerkten Punkt Mandantenfähigkeit: Beides sind Annahmen, die
tragen, solange es einen Mandanten mit einer Währung gibt.

---

## Offen aus Etappe 2

| Punkt | Stand |
|---|---|
| A2-1 | behoben |
| A2-2 | behoben |
| A2-3 | offen — gehört zum vorgemerkten Punkt Mandantenfähigkeit und wird mit ihm entschieden |

---

# Etappe 3 — Import, Matching, Review (A3)

## Vorgehen

Hier entstehen die Daten. Ein Fehler wirkt nicht auf eine Anzeige, sondern auf den
Bestand — und ist später schwer bis nicht rückgängig zu machen. Die Commit-Historie
zeigte vier `fix:`-Commits allein in diesem Bereich (Dublettenerkennung, Kopfzeilen,
interne Matcher, allgegenwärtige Kennungen). Geprüft wurden Idempotenz,
Transaktionsgrenzen, die Dublettenlogik, der Review-Lebenszyklus und das Audit-Log.

## Was in Ordnung ist

**Idempotenz hält.** Dieselbe Datei zweimal importiert ergibt denselben Bestand — mit
Test belegt. Die Dublettenerkennung zählt seit `b169d28` Vorkommen statt Existenz und
importiert die Differenz; zwei echte, äußerlich gleiche Buchungen desselben Tages
kommen damit beim ersten Import beide durch, ein wiederholter Import wird vollständig
verworfen. Die Logik ist ausführlich kommentiert und stimmt.

**Der Review-Lebenszyklus hat einen sauberen Wächter.** `_get_open_or_raise` liefert
404 bei fremden oder fehlenden Einträgen und **409, wenn der Eintrag nicht mehr offen
ist**. Alle elf Statuswechsel führen nach `confirmed`, `adjusted` oder `rejected` —
alle drei terminal, keine Sackgassen, keine Rückwege.

**Die UNIQUE-Constraints auf `review_items` sind aus dem Import nicht erreichbar.**
Die dort erzeugten Einträge hängen an je einer neuen Buchungszeile und lassen
`service_id` leer.

---

## A3-1 — Abgelehnte Datei ließ eine bereits importierte zurück · **mittel** · behoben

**Ort:** [imports/service.py:257](../backend/app/imports/service.py#L257) (`upload`)

**Behauptung:** `upload()` prüfte jede Datei erst unmittelbar vor ihrer Verarbeitung.
Jede Datei wird einzeln festgeschrieben. Kam im selben Upload nach einer gültigen CSV
eine ungültige Datei, war die erste bereits im Bestand, während der Aufruf mit 422
scheiterte.

**Fehlerszenario:** Upload von `kontoauszug.csv` und `notizen.txt`. Antwort: **422 —
„File 'notizen.txt' is not a CSV"**. Im Bestand: ein Importlauf mit den Zeilen aus
`kontoauszug.csv`. Der Nutzer sieht eine Fehlermeldung und lädt beide Dateien erneut
hoch — der zweite Versuch importiert die erste Datei ein zweites Mal, falls die
Dublettenerkennung nicht konfiguriert ist oder nicht greift.

**Behoben:** Alle Dateien werden geprüft, bevor die erste verarbeitet wird.

---

## A3-2 — Ein Zeilenfehler verwarf alle vorherigen Zeilen des Laufs · **hoch** · behoben

**Ort:** [imports/service.py:740](../backend/app/imports/service.py#L740)

**Behauptung:** Beim Einfügen einer Buchungszeile fing der Code `IntegrityError` ab,
zählte die Zeile als Dublette und lief weiter — rief dazu aber `session.rollback()`.
Das nimmt die **gesamte** Transaktion zurück, nicht die eine Zeile: alle bereits
eingefügten Buchungszeilen dieses Laufs, den Importlauf selbst und die
Partnerzuordnungen. Die Zähler im Speicher blieben davon unberührt, sodass der Lauf am
Ende Zeilen meldete, die es nicht mehr gab.

**Fehlerszenario:** Drei Zeilen, die zweite scheitert.

```
Der Lauf meldet 2 importierte Zeilen, in der Datenbank liegt 1.
```

Zeile 1 war weg, Zeile 3 überlebte, der Lauf galt als erfolgreich. Ein zweiter,
sichtbarer Nebeneffekt: Das `rollback()` entwertet auch die Objekte des Aufrufers,
sodass anschließende Attributzugriffe im selben Request ins Leere laufen.

**Erreichbarkeit:** Auf `journal_lines` gibt es keinen Unique-Constraint, aus der
Buchungszeile selbst kann der Fehler also nicht kommen. Erreichbar ist er über die
Partnerzuordnung im selben Flush: `partner_ibans.iban` ist global eindeutig (ADR-008).
Registrieren zwei gleichzeitig laufende Importe dieselbe neue IBAN, gewinnt einer und
der andere verliert seinen bisherigen Lauf. Selten — und genau deshalb hätte es
niemand bemerkt.

**Behoben:** Ein Savepoint um das Einfügen der Zeile statt eines Transaktions-Rollbacks.
Zwei Feinheiten, die dazugehören und die der Test erzwungen hat:

* Das `session.add(line)` gehört **in** den Savepoint. `begin_nested()` schreibt
  Ausstehendes vorher weg, und was vor dem Savepoint geschrieben wurde, nimmt sein
  Zurücknehmen nicht mit.
* Danach braucht es kein `expunge`: Das Zurücknehmen des Savepoints entfernt die Zeile
  bereits aus der Session.

**Test:** [tests/imports/test_import_fehlerpfade.py](../backend/tests/imports/test_import_fehlerpfade.py) —
schleust einen `IntegrityError` in den Savepoint der zweiten Zeile ein und prüft, dass
die gemeldete Zahl mit dem Bestand übereinstimmt. Dazu der Idempotenz-Test und der
Test zu A3-1.

---

## A3-3 — Abgebrochene Importe hinterlassen keinen Audit-Eintrag · **niedrig** · offen

**Ort:** [imports/service.py:270](../backend/app/imports/service.py#L270) (`_process_file`)

ADR-017 hält fest, dass `import.completed` und `import.failed` ins Audit-Log
geschrieben werden. Der Eintrag entsteht am Ende von `_process_file`. Bricht die
Verarbeitung vorher ab — unlesbare Kodierung, fehlende Vergleichsspalte,
Datenbankfehler —, gibt es keinen `try`/`except`: kein Audit-Eintrag, und der
Importlauf selbst wird beim Schließen der Session mit zurückgerollt.

`status = failed` wird nur gesetzt, wenn die Datei **lesbar** war und jede Zeile einen
Parse-Fehler hatte. Der eigentliche Fehlschlag ist der, der nicht protokolliert wird.

**Kein Datenschaden**, aber die Aussage der ADR stimmt nur für den halben Fehlerraum.

---

## A3-4 — Ohne Vergleichsspalten keine Dublettenerkennung · **niedrig** · latent

**Ort:** [imports/service.py:781](../backend/app/imports/service.py#L781)
(`_validate_duplicate_check_columns`)

Sind in der Spaltenkonfiguration keine Spalten mit `duplicate_check` markiert, kehrt
die Prüfung ohne Beanstandung zurück und die Dublettenerkennung entfällt vollständig.
Ein versehentlich wiederholter Import verdoppelt dann jede Buchung, ohne Hinweis.

**Heute nicht erreichbar:** Beide Konten haben Vergleichsspalten konfiguriert (12 bzw.
8). Die Falle steht für das nächste Konto bereit.

Beiläufig aufgefallen: Bei einem Konto steht `Buchungsdatum` zweimal in der Liste der
Vergleichsspalten. Folgenlos für den Vergleich, aber ein Hinweis darauf, dass die
Konfiguration keine Dubletten in sich ausschließt.

---

## Offen aus Etappe 3

| Punkt | Stand |
|---|---|
| A3-1 | behoben |
| A3-2 | behoben |
| A3-3 | offen — Audit-Eintrag auch auf dem Ausnahmepfad schreiben? |
| A3-4 | offen — mindestens eine Vergleichsspalte erzwingen, oder beim Import warnen? |
