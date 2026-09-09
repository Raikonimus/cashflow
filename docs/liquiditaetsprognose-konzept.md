# Konzept: Liquiditätsprognose

Stand: 2026-09-09

Ziel: cashflow von der reinen Ist-Auswertung (Einnahmen-/Ausgaben-Matrix) zu einem
Liquiditätstool erweitern. Dazu fließen Schätzungen für künftige Monate ein, die

1. mit einfachen, nachvollziehbaren Regeln gebildet werden,
2. aus vergangenen Daten abgeleitet werden — und nur dann, wenn genügend Historie vorliegt,
3. je Leistung individuell übersteuerbar sind.

---

## 1. Grundsatzentscheidung: Arithmetik statt KI

**Die Prognosezahlen werden rein arithmetisch berechnet. KI ist höchstens ein optionaler
Vorschlags-Assistent in einer späten Phase.**

| Kriterium | Arithmetik | LLM |
|---|---|---|
| Reproduzierbarkeit | Gleicher Input → gleiche Zahl, immer | Nicht deterministisch |
| Erklärbarkeit | „Ø der letzten 6 Monate × 2 wegen 14. Gehalt" | Blackbox, Begründung nicht prüfbar |
| Datenmenge | 12–60 Monatspunkte je Leistung — genau das Regime, in dem Median/MAD besser sind als ML | ML/ARIMA/Prophet brauchen mehr Daten |
| Kosten/Latenz | 0, läuft bei jedem Seitenaufruf | Tokens + Sekunden pro Berechnung |
| Datenschutz | Kontodaten bleiben lokal | Zahlungsdaten verlassen das System |

Die typischen Muster sind arithmetisch erkennbar, ohne fachliches Vorwissen zu kodieren:

- **Gehälter** — monatlich konstant, im Juni und November doppelt. Ein Profiler, der Monatswerte
  gegen den Jahresmedian vergleicht, erkennt „Sondermonat Juni, Faktor 2,0" von selbst.
  13./14./15. Gehalt muss nicht hart kodiert werden.
- **Lizenzen** — konstanter Betrag, Median-Abstand 1 Monat → monatlich fix.
- **Jährliche Zahlungen** — Median-Abstand 12 Monate, gleicher Kalendermonat → jährlich mit Zielmonat.
- **Projekteinnahmen** — unregelmäßig. Hier trifft kein Verfahren den einzelnen Monat. Sinnvoll ist
  nur eine Verteilung: Vorjahres-Saisonprofil oder Jahresdurchschnitt/12, plus Bandbreite und
  Sicherheitsabschlag. Ein LLM würde hier eine Präzision vortäuschen, die es nicht gibt.

Der entscheidende Punkt: **Regelauswahl per Backtest.** Statt zu raten, welche Regel passt,
werden alle anwendbaren Regeln auf Daten bis `t−6` gerechnet und gegen die tatsächlich
eingetroffenen letzten 6 Monate gemessen. Die Regel mit dem kleinsten MAE gewinnt. Objektiv,
prüfbar, kostenlos — und mit jedem Import besser.

### Wo KI später Mehrwert hätte (Phase 3, hinter Feature-Flag)

1. **Semantik statt Statistik bei dünner Historie.** Der Profiler sieht nur Zahlen. Ein LLM sieht
   „Lizenz Microsoft 365 – Jahresabo" im Buchungstext und schlägt bei nur zwei Zahlungen schon
   „jährlich wiederkehrend" vor. Das ist ein einmaliger Vorschlag, den der Nutzer bestätigt —
   danach ist die Regel gespeichert und deterministisch. Passt zum bestehenden
   `ReviewItem`-Muster (Vorschlag → Mensch bestätigt).
2. **Anomalie-Kommentierung** — „Leistung war bis 03/2026 monatlich, seither nichts —
   Vertrag beendet?"

Erst bauen, wenn Phase 1+2 stehen und sichtbar ist, welche Fälle die Arithmetik nicht löst.

---

## 2. Architektur: drei Schichten

```
┌─ Historie (journal_line_splits + journal_lines)  ── existiert bereits
│
├─ 1. PROFILER (lesend, deterministisch, gecacht)
│     Monatsreihe je Leistung → Rhythmus, Betragsstabilität,
│     Sondermonate, Trend, Confidence → Regelvorschlag
│
├─ 2. REGEL (persistiert, je Leistung, überschreibbar)
│     mode: auto (Vorschlag folgen) | manual (fixiert) | off
│
└─ 3. PROJEKTION (on-the-fly, nicht materialisiert)
      Regel × Zeitachse → Monatswerte → Matrix + Liquiditätskurve
```

**Prognosewerte werden nicht in die Datenbank geschrieben — nur die Regeln.** Bei jedem Import
ändert sich die Historie; materialisierte Prognosen wären sofort veraltet. Die Berechnung ist
billig (Größenordnung 200 Leistungen × 24 Monate). Für den Plan-Ist-Vergleich gibt es stattdessen
optionale Snapshots (eingefrorenes JSON zum Stichtag) in Phase 3.

---

## 3. Regeltypen

| Regeltyp | Parameter | Typischer Fall |
|---|---|---|
| `none` | – | Einmalzahlung, beendeter Vertrag, zu wenig Historie |
| `fixed_recurring` | Betrag, Intervall (1/3/6/12 Mon.), Ankermonat, Sondermonate `{6: 2.0, 11: 2.0}` | Gehalt, Miete, Lizenz, Jahresversicherung |
| `rolling_average` | Fenster (3/6/12 Mon.), Median oder Mittelwert, Ausreißer trimmen | Schwankende Fixkosten (Energie, Telefon) |
| `same_period_last_year` | Faktor/Indexierung % | Saisonales Geschäft |
| `seasonal_profile` | Jahresziel × Monatsanteile aus ≥2 Vorjahren | Projekteinnahmen mit Saisonalität |
| `manual_plan` | Werte je Monat, händisch | Bekannter Neukunde, geplante Investition |

**Modifikatoren auf jeder Regel** — hierüber erfolgt die individuelle Einstellung je Leistung:

- `faktor_pct` — Indexierung, z. B. +3 % Gehaltsrunde
- `sicherheitsabschlag_pct` — Projekteinnahmen nur zu 70 % ansetzen
- `zahlungsverzug_tage` — Valuta-Verschiebung (Kunde zahlt typisch 20 Tage später)
- `gueltig_ab` / `gueltig_bis` — Vertragsende, Neueinstellung ab Monat X
- `cap` / `floor`

---

## 4. Profiler

Je Leistung eine Monatsreihe (Bruttosummen nach Valutadatum, letzte 36 Monate):

- **Rhythmus** — Abstände zwischen aktiven Monaten, Median-Abstand, Streuung (MAD) prüfen.
  Median 1 → monatlich · 3 → quartalsweise · 12 → jährlich (Zielmonat = häufigster
  Kalendermonat) · inkonsistent → unregelmäßig.
- **Betragsstabilität** — Variationskoeffizient über Median/MAD (robust gegen Ausreißer):
  < 5 % → fix · < 25 % → stabil · sonst schwankend.
- **Sondermonate** — Kalendermonate, in denen der Wert in ≥2 Jahren über 1,5 × Jahresmedian
  liegt → Faktor speichern.
- **Trend** — lineare Regression, nur bei ≥12 Punkten und R² > 0,5.
- **Confidence** — aus Historienlänge und Variationskoeffizient: hoch / mittel / niedrig.
  Steuert die Bandbreite der Szenarien.

### Mindesthistorie — „nur wenn Daten bekannt sind"

| Regel | Mindesthistorie |
|---|---|
| `fixed_recurring` monatlich | ≥3 Vorkommen |
| `fixed_recurring` jährlich | ≥2 Vorkommen in verschiedenen Jahren |
| `rolling_average` | ≥ Fenstergröße aktive Monate |
| `same_period_last_year` | Vorjahresmonat vorhanden |
| `seasonal_profile` | ≥24 Monate |

Wird das nicht erreicht → `none` plus Hinweis in der UI. Zusätzlich: Leistungen ohne Bewegung
seit mehr als zwei erwarteten Perioden oder mit `valid_to` in der Vergangenheit werden
automatisch auf „inaktiv" gesetzt, damit die Prognose keine Karteileichen mitschleppt.

---

## 5. Prognosehorizont

**Die Vorschau reicht immer bis zum 31.12. des Folgejahres** (entschieden 2026-09-08).

Konkret heißt das: In der Jahresansicht der Einnahmen-/Ausgaben-Matrix ist das höchste
wählbare Jahr `laufendes Jahr + 1`. Im September 2026 reicht die Prognose damit bis Dez 2027.

Vorteile gegenüber den verworfenen Alternativen: Der Horizont wird gegen Jahresende nie zu kurz
(ein reines „bis Jahresende" liefert im Dezember nur noch einen Monat) und die Ausrichtung an
Kalenderjahren passt zur bestehenden Matrix. Der Preis ist, dass die Prognosetiefe schwankt: im
Januar reicht sie 24 Monate voraus, im Dezember 13. Für Leistungen mit dünner Historie heißt
das, dass die hinteren Monate eine niedrigere Confidence tragen — sichtbar gemacht, nicht
wegdefiniert.

---

## 6. Datenmodell

Vorhanden und wiederverwendet: `journal_lines`, `journal_line_splits`, `services`,
`service_groups`, `service_group_assignments`.

Neu:

```
accounts.opening_balance   Numeric(15,2) NOT NULL DEFAULT 0      ← Phase 0, umgesetzt
service_forecast_rules     (id, mandant_id, service_id UNIQUE, mode,
                            rule_type, params JSON, safety_factor_pct,
                            shift_days, valid_from, valid_to, updated_by)
service_forecast_profiles  (service_id, computed_at, cadence, median_amount,
                            cv, special_months JSON, first_seen, last_seen,
                            sample_count, suggested_rule JSON, backtest_mae)   ← Cache
forecast_planned_items     (id, mandant_id, service_id?, service_group_id?,
                            period 'YYYY-MM', amount, note)
```

`forecast_planned_items` deckt zwei Fälle ab: die Monatswerte von `manual_plan` und freie
Planpositionen ohne Leistung (geplante Investition, Steuernachzahlung).

**Bereits bekannte, noch nicht gebuchte Zahlungen werden über händische Planposten abgebildet**
(entschieden 2026-09-08). Beispiel: eine am 20.08. gestellte Rechnung über 30.000 €, zahlbar in
30 Tagen — die Bankdaten kennen sie nicht, die Statistik würde den September nur schätzen. Ein
Planposten setzt für diesen Monat den bekannten Betrag an die Stelle der Schätzung.

Eine echte Offene-Posten-Verwaltung (Ausgangs-/Eingangsrechnungen mit Fälligkeit und Status,
automatischer Abgleich beim Import) wurde bewusst verworfen: Bei den meisten Firmen decken fünf
bis zehn große Posten den Großteil der Unsicherheit ab, und die sind in Minuten eingetragen. Falls
sich das als unzureichend erweist, ist der nächste Schritt ein Import aus der Fakturierung —
nicht Handpflege einer zweiten Rechnungsverwaltung.

---

## 7. Besonderheiten des bestehenden Modells

- **Startsaldo.** `Account` hatte keinen Saldo, und der CSV-Import kennt keine Saldo-Spalte.
  Ohne Startsaldo gibt es nur Deltas, keine Liquidität. In Phase 0 ergänzt.
- **Interne Umbuchungen.** `_section_for_service` in `backend/app/journal/service.py` blendet
  `internal_transfer` und `unknown` aus der Matrix aus. Für die Liquidität *pro Konto* sind
  Umbuchungen aber relevant; auf Mandantenebene saldieren sie sich zu null. Die Prognose braucht
  hier eine eigene Sichtweise.
- **Brutto, nicht netto.** Liquidität rechnet immer brutto. `erfolgsneutral` markierte Leistungen
  (Darlehen, USt, Durchläufer) sind zahlungswirksam und müssen mitgerechnet werden.
- **Fremdwährung.** Die Matrix rechnet nur EUR und weist abweichende Währungen separat aus.
  Die Saldenberechnung verfährt genauso: gezählt wird nur, was der Kontowährung entspricht;
  abweichende Buchungen werden als Zähler ausgewiesen statt stillschweigend addiert.

---

## 8. API und UI

**Endpunkte** (analog zu `reports/income-expense`):

- `GET /mandants/{id}/reports/account-balances` — je Konto Startsaldo, Summe Buchungen,
  aktueller Saldo, Stichtag; plus Gesamtsumme  ← Phase 0, umgesetzt
- `GET /mandants/{id}/reports/income-expense?year=…` — der bestehende Endpunkt wurde erweitert
  statt dupliziert: Liegt das Jahr ganz oder teilweise in der Zukunft, liefert er Prognosewerte,
  jede Zelle trägt `is_forecast`, jede Leistungszeile Regel, Confidence und Begründung
  ← Phase 1, umgesetzt
- `GET /mandants/{id}/reports/liquidity` — je Monat vom laufenden Monat bis zum Horizont:
  Anfangssaldo, Ein-, Auszahlungen, Endsaldo, Tiefpunkt  ← Phase 1, umgesetzt
- `GET /mandants/{id}/journal/years` — liefert zusätzlich `forecast_years`  ← Phase 1, umgesetzt
- Szenarien (`scenario=expected|low|high`) folgen in Phase 2
- `GET|PUT|DELETE /mandants/{id}/services/{sid}/forecast-rule` — Regel lesen, setzen,
  auf Automatik zurücksetzen  ← Phase 2, umgesetzt
- `GET /mandants/{id}/forecast/services` — Prognose-Übersicht, filterbar  ← Phase 2, umgesetzt
- `GET|POST|PATCH|DELETE /mandants/{id}/forecast/planned-items`  ← Phase 2, umgesetzt
- `scenario=expected|low|high` auf `reports/income-expense` und `reports/liquidity`
  ← Phase 2, umgesetzt
- `reports/liquidity` liefert je Monat zusätzlich `closing_low`/`closing_high` — das
  Unsicherheitsband aus den gemessenen Fehlern  ← Phase 3, umgesetzt
- `GET|POST|DELETE /mandants/{id}/forecast/snapshots[/{sid}]` — Planstände festhalten und
  gegen das Ist vergleichen  ← Phase 3, umgesetzt

**UI:**

1. **Dashboard** — aktueller Kontostand je Konto und in Summe. ← Phase 0, umgesetzt
2. **Matrix erweitern — kein neuer Ansichtsmodus.** Ein künftiges Jahr ist einfach ein Jahr:
   Die bestehende Jahresansicht darf über das letzte Jahr mit Buchungen hinausblättern, die
   Obergrenze für „Folgejahr ▶" wandert von „letztes Jahr mit Daten" auf „laufendes Jahr + 1".
   Die Mehrjahresansicht nimmt das Prognosejahr automatisch mit, sobald es in `availableYears`
   steht.

   **Prognosewerte werden grau dargestellt, und zwar je Zelle, nicht je Jahr.** Das laufende
   Jahr ist gemischt: Jan–Aug 2026 sind Ist, Sep–Dez 2026 sind Prognose — in derselben Zeile
   stehen schwarze und graue Werte nebeneinander. Genau das ist der Nutzen der Darstellung: Man
   sieht, wo die Realität aufhört. Die Jahressumme links ist dann eine Mischung und wird als
   solche markiert. Der Excel-Export übernimmt die Unterscheidung.
3. **Liquiditätskurve** — gehört ins Dashboard, nicht in die Matrix: Die Matrix zeigt Flüsse,
   die Kurve den Pegel. Kumulierter Kontostand über die Zeit, drei Linien (pessimistisch/
   erwartet/optimistisch), Nulllinie markiert, Warnung bei Unterschreitung eines Schwellwerts.
4. **Regel-Editor je Leistung** — Abschnitt „Prognose" in `ServiceManagementPage`: erkanntes
   Muster mit Sparkline der Historie, Regeltyp-Dropdown mit Parametern, Live-Vorschau der
   nächsten zwölf Monate.
5. **Prognose-Übersicht** — eigene Seite mit allen Leistungen, Muster, Regel, Confidence, Status;
   filterbar nach „ungeprüft" und „zu wenig Historie". Ohne diese Liste prüft niemand 200
   Leistungen einzeln durch — analog zur bestehenden Review-Seite.

---

## 9. Phasenplan

| Phase | Inhalt | Status |
|---|---|---|
| **0** | Startsaldo je Konto, Saldenberechnung, Kontostand im Dashboard | **umgesetzt** |
| **1** | Profiler + `fixed_recurring`/`rolling_average`/`none`, Prognosespalten, Liquiditätskurve | **umgesetzt** |
| **2** | Regel-Editor je Leistung, Sondermonate, Saisonprofil, Vorjahresregel, Szenarien, Planposten | **umgesetzt** |
| **3** | Backtest-Regelwahl, Plan-Ist-Snapshots, Treffsicherheits-Messung | **umgesetzt** |
| **4** | Optionaler KI-Assistent für semantische Vorschläge bei dünner Historie | offen |

Der Backtest gehört bewusst in Phase 3: Er braucht die Regeltypen aus Phase 2 als Kandidaten.

---

## 10. Phase 0 — umgesetzt

**Startsaldo je Konto.** Neues Feld `accounts.opening_balance`, `Numeric(15,2)`, Default `0.00`
(Migration `026`). Pflegbar beim Anlegen eines Kontos und in den Kontoeinstellungen.
Für den aktuellen Beispielmandanten bleibt der Wert 0, weil sämtliche Buchungen importiert sind.

**Saldenberechnung.** `Kontostand = opening_balance + Σ journal_lines.amount` je Konto, begrenzt
auf Buchungen in Kontowährung. Stichtag ist das jüngste Valutadatum unter den einbezogenen
Buchungen — damit ist der Saldo genau bis zur letzten importierten Buchung gültig und lässt sich
mit dem Bankauszug abgleichen. Buchungen in abweichender Währung werden gezählt und separat
ausgewiesen, nicht addiert.

**Dashboard.** Der bisherige Platzhalter unter `/` zeigt jetzt je Konto Startsaldo, Summe der
Buchungen und aktuellen Saldo, dazu die Gesamtsumme über alle Konten gleicher Währung.

### Entschieden am 2026-09-08

- **Horizont** — immer bis 31.12. des Folgejahres (Abschnitt 5).
- **Offene Posten** — händische Planposten statt eigener OP-Verwaltung (Abschnitt 6).

### Weiterhin offen

- **Saldo-Spalte im Import** — soll `opening_balance` künftig aus einer CSV-Saldospalte
  abgeleitet werden können, statt manuell gepflegt zu werden?

---

## 11. Phase 1 — umgesetzt

**Profiler** (`backend/app/forecast/profiler.py`) — reine Arithmetik ohne Datenbankzugriff,
dadurch vollständig unit-testbar. Erkennt aus der Monatsreihe je Leistung Rhythmus
(monatlich/quartalsweise/jährlich/unregelmäßig), Betragsstabilität über Median und MAD sowie
Sondermonate, und leitet daraus eine der Regeln `fixed_recurring`, `rolling_average` oder
`none` ab. Jede Regel trägt eine Begründung im Klartext, die in der Oberfläche als Tooltip
erscheint. Schwellwerte stehen als benannte Konstanten am Dateikopf.

Zwei Feinheiten, die sich erst im Test gezeigt haben:

- Ein Sondermonat gilt nur, wenn **jede** Beobachtung dieses Kalendermonats erhöht ist. Bei
  genau zwei Beobachtungen ist der Median sonst der Mittelwert, und eine einmalige Nachzahlung
  würde den Monat dauerhaft als Sondermonat festschreiben.
- Zwei Jahreszahlungen im selben Kalendermonat sind ein Muster (sie spannen zwölf Monate), zwei
  Quartalszahlungen sind es nicht (nur vier Monate). Die Mindestvorkommen sind deshalb nach
  Rhythmus getrennt.

**Prognose in der Matrix** — Vergangene Monate bleiben unverändert. Künftige Monate tragen den
projizierten Wert. Der laufende Monat ist ein Sonderfall: Er ist unvollständig, deshalb wird nur
der noch nicht gebuchte Teil der Monatsprognose ergänzt. Übersteigt das Gebuchte die Prognose
bereits, kommt nichts hinzu — sonst würde der Monat doppelt gezählt.

**Liquiditätskurve** — startet beim aktuellen Kontostand aus Phase 0 und addiert die
Monatsprognosen auf. Inline-SVG ohne zusätzliche Abhängigkeit, blau oberhalb und rot unterhalb
der Nulllinie, mit Tooltip und zuschaltbarer Zahlentabelle.

### Einflussmöglichkeiten in Phase 1

Einen Regel-Editor gibt es noch nicht — die Regel wird je Leistung automatisch bestimmt. Vier
indirekte Hebel wirken aber schon heute:

1. **`gültig ab` / `gültig bis` je Leistung** (Leistungsverwaltung). Die Projektion beginnt bzw.
   endet an diesem Monat. Der direkteste Weg, einen bekannten Vertragsablauf abzubilden.
2. **Leistungstyp und `erfolgsneutral`**. Was `section_for_service` nicht zuordnet — interne
   Umbuchungen, unklassifizierte Leistungen — fällt aus Matrix und Prognose heraus.
3. **Zuschnitt der Leistungen.** Der stärkste Hebel, weil je Leistung profiliert wird: Liegen
   ein monatliches Retainer und sporadische Projektrechnungen auf derselben Leistung, sieht der
   Profiler „unregelmäßig" und fällt auf den Jahresdurchschnitt zurück. Getrennt ergeben sie
   „monatlich fix" plus „unregelmäßig" — beides besser prognostiziert. Ebenso hebt jede im
   Review zugeordnete Buchung die Abdeckung.
4. **Startsaldo je Konto** verschiebt die gesamte Liquiditätskurve.

Die Begründung jeder Regel steht im Tooltip der Prognosezelle — ohne sie ließe sich nicht
erkennen, an welcher Schraube zu drehen wäre.

### Bekannte Schwäche: Einnahmen sind schlechter abgedeckt als Ausgaben

Ein Rückvergleich gegen die letzten zwölf Monate des Beispielmandanten zeigt eine systematische
Schieflage:

| | Ist Ø/Monat | Prognose Ø/Monat | Abdeckung |
|---|---|---|---|
| Einnahmen | 73.054 | 64.311 | 88 % |
| Ausgaben | −91.950 | −88.810 | 97 % |

Der Grund ist strukturell, kein Rechenfehler: Unregelmäßige Einnahmen — Projektgeschäft — fallen
häufiger durch die Mindesthistorie als regelmäßige Fixkosten. Die Kurve ist dadurch tendenziell
zu pessimistisch.

Sichtbar gemacht wird das über `uncovered_average_per_month`: den Monatsdurchschnitt des
Volumens, das die Prognose nicht abdeckt — Buchungen ohne Leistungszuordnung plus Leistungen
ohne Regel. Die Oberfläche weist den Wert unter der Kurve aus. Behoben wird die Schieflage erst
durch die Planposten aus Phase 2, mit denen bekannte Einnahmen von Hand eingetragen werden.

---

## 12. Phase 2 — umgesetzt

### Drei Schichten über dem Profiler

```
Profilervorschlag  →  Übersteuerung (auto | manual | off)
                   →  Modifikatoren (Anpassung %, Zahlungsverzug)
                   →  Szenario (Bandbreite nach Confidence)
                   →  Planposten ersetzen das Ergebnis
```

Die Reihenfolge steht in `backend/app/forecast/rules.py`. Planposten stehen bewusst ganz am
Ende und *ersetzen* statt zu verändern: Ein bekannter Betrag wird weder indexiert noch mit
einer Bandbreite versehen — er ist ja bekannt.

### Neue Tabellen (Migration 027)

`service_forecast_rules` (eine je Leistung) und `forecast_planned_items`.

### Abweichungen vom ursprünglichen Konzept

Drei bewusste Vereinfachungen, jeweils mit Grund:

| Konzept | Umgesetzt | Warum |
|---|---|---|
| `faktor_pct` **und** `sicherheitsabschlag_pct` | ein Regler `adjustment_pct` | Beides ist dasselbe Rechenwerk: +3 % Indexierung, −30 % Abschlag. Zwei Knöpfe mit derselben Wirkung verwirren. |
| `zahlungsverzug_tage` | `shift_months` | Bei Monatsrastern kann ein Tageswert nicht halten, was sein Name verspricht. |
| `cap` / `floor` | entfallen | Bei vorzeichenbehafteten Beträgen ist unklar, ob ein „Cap" die betragsmäßige oder die vorzeichenrichtige Obergrenze meint. Der geringste Nutzen bei der größten Verwechslungsgefahr. |

Zwei Zurückstellungen:

- **Planposten hängen immer an einer Leistung.** Freie Positionen ohne Leistung bräuchten eine
  synthetische Zeile in der Matrix und würden deren Drag-&-Drop-Modell aufbrechen. Eine geplante
  Investition wird stattdessen gegen die Leistung des Lieferanten gebucht.
- **Der Regel-Editor sitzt in der Prognose-Übersicht**, nicht in der Leistungsverwaltung. Bei 410
  Leistungen ist die durchsuch- und filterbare Liste der Einstieg; ein zweiter Editor in der
  ohnehin umfangreichen `ServiceManagementPage` wäre Duplikat statt Ergänzung.

### Szenarien sind ein Stresstest, kein Konfidenzintervall

Die Bandbreite wird additiv auf den Betrag gerechnet, nicht multiplikativ — ein Faktor 0,9 würde
eine Ausgabe von −1.000 auf −900 verkleinern und das pessimistische Szenario damit in sein
Gegenteil verkehren. `low` senkt den Saldo immer, `high` hebt ihn immer.

Beim Beispielmandanten ergibt das eine sehr weite Spanne:

| Szenario | Tiefstand bis 12/2027 |
|---|---|
| optimistisch | +73.768 |
| erwartet | −319.597 |
| pessimistisch | −976.091 |

Das ist rechnerisch konsistent, unterstellt aber, dass **alle** Regeln gleichzeitig in dieselbe
Richtung danebenliegen. Real gleichen sich Fehler über 166 Leistungen teilweise aus. Die Spanne
ist deshalb als Stresstest zu lesen, nicht als Wahrscheinlichkeitsband — die Oberfläche sagt das
beim Umschalten auch dazu. Ein echtes Konfidenzintervall bräuchte die gemessene Treffsicherheit
je Regel aus Phase 3.

> Die drei Zahlen oben sind der Stand nach Phase 2 und dienen dem Vergleich. Phase 3 hat sie
> verändert — maßgeblich ist die Tabelle in Abschnitt 13.


---

## 13. Phase 3 — umgesetzt

Bis Phase 2 wählte der Profiler die Regel nach festen Schwellwerten und die Szenariobandbreite
kam aus einer geschätzten Tabelle. Phase 3 ersetzt beides durch eine Messung.

### Rückvergleich (`app/forecast/backtest.py`)

Die letzten Monate werden zurückgehalten, jeder Kandidat wird **nur** auf den Daten davor
gebildet und dann daran gemessen. Kandidaten sind der Profilervorschlag, ein fester
Monatsbetrag, gleitende Mittel über 3/6/12 Monate, der Vorjahresmonat, das Saisonprofil — und
die Nullprognose als Vergleichslinie.

**Prüfzeitraum:** `min(12, max(6, 2 × Intervall))` Monate — er muss mindestens zwei erwartete
Zahlungen enthalten, sonst ließe sich ein Rhythmus nicht prüfen. Davor müssen zwölf Monate
Historie liegen; sonst läuft der Rückvergleich nicht und die Regel bleibt beim Profilervorschlag.

**Bewertung:** Score = Mittel aus Monatsfehler (MAE) und Niveaufehler je Monat. Der Monatsfehler
bestraft falsches Timing, der Niveaufehler die Abweichung der Summe. Für den Kontostand zählt
vor allem das Niveau, für die Matrix das Timing — deshalb beide.

Vier Entscheidungen, die nicht offensichtlich sind:

1. **Die Nullprognose gewinnt nie.** Bei unregelmäßigen Zahlungen hat „gar nichts vorhersagen"
   oft den kleinsten Monatsfehler; das verschiebt den Fehler nur aus dem Blickfeld. Ob eine
   Regel die Nullprognose schlägt, wird trotzdem ausgewiesen — es ist die ehrlichste Kennzahl
   dafür, ob die Prognose dieser Leistung etwas taugt.
2. **Der Sieger wird auf der vollen Historie neu angepasst.** Der Rückvergleich entscheidet nur,
   *welches Verfahren* passt; Median, Fenstermittel und Saisonanteile kommen danach aus allen
   Monaten. Sonst würde man die jüngsten Daten wegwerfen.
3. **Ein Kandidat muss den Profilervorschlag um 10 % schlagen.** Bei sechs bis zwölf Prüfmonaten
   ist ein Vorsprung von zwei Prozent Rauschen.
4. **Sagt der Profiler „keine Prognose", läuft kein Rückvergleich.** Die Mindesthistorie-Sperren
   sind eine Ehrlichkeitsgrenze und werden nicht überstimmt.

### Ein Fund aus dem Rückvergleich: 67 beendete Leistungen

Der Prüfzeitraum enthält per Konstruktion mindestens zwei erwartete Zahlungen. Liegt darin
**keine einzige Buchung**, zahlt hier nichts mehr — das ist gemessen und damit strenger als die
Schwellwertregel des Profilers („seit mehr als zwei Perioden nichts gebucht"), die eine
ausgelaufene Leistung noch monatelang weiterprojiziert.

Beim Beispielmandanten betraf das **67 Leistungen**. 19 davon hätten weiter Geld prognostiziert,
netto **+21.801 €** auf zwölf Monate (brutto +39.552 Einnahmen gegen −17.751 Ausgaben) — die
größte davon „Lizenzen AI-Concierge" mit +22.392 € ohne eine einzige Buchung im Prüfzeitraum.
Diese Leistungen werden jetzt automatisch abgeschaltet; der erwartete Saldo 12/2027
verschlechtert sich dadurch von −178.694 auf −208.604 €. Wer eine Leistung für weiterlaufend hält, setzt einen
händischen Regeltyp oder einen Planposten.

### Treffsicherheit ersetzt geschätzte Confidence

Der relative Fehler (Monatsfehler ÷ monatliches Ist-Volumen) bestimmt jetzt

- die **Confidence** — ≤ 10 % hoch, ≤ 30 % mittel, darüber niedrig,
- die **Szenariobandbreite** je Leistung, gedeckelt auf 5 % bis 100 %.

Wo der Rückvergleich mangels Historie nicht laufen konnte, greift weiter die geschätzte Tabelle
(10/25/50 % nach Confidence). Die Oberfläche unterscheidet beides: eine gemessene Angabe steht
als „±37 %", eine geschätzte als „hoch/mittel/niedrig".

### Unsicherheitsband statt Stresstest — beide, getrennt benannt

Der Phase-2-Vorbehalt war, dass die Szenarien unterstellen, alle Regeln lägen gleichzeitig in
dieselbe Richtung daneben. Mit gemessenen Fehlern lässt sich das besser rechnen:

- **Über die Zeit** ist der Fehler einer Regel voll korreliert — ein zu hoch angesetzter
  Monatsbetrag ist jeden Monat zu hoch. Also je Leistung aufsummieren.
- **Über Leistungen hinweg** ist er es nur teilweise. Formel für gleichkorrelierte Terme:
  `Var = (1−ρ)·Σσᵢ² + ρ·(Σσᵢ)²`, mit `σᵢ = Bandbreiteᵢ × Σ_{k≤m}|Wertᵢ,ₖ|`.
- **Was keine Regel hat**, trägt zur Prognose nichts bei, zur Unsicherheit sehr wohl — diese
  Buchungen bewegen den Kontostand trotzdem. Der Monatsdurchschnitt des nicht abgedeckten
  Volumens geht als eigener Term ein.
- **Planposten tragen keine Unsicherheit.** Ein bekannter Betrag wird nicht geschätzt.

Band und Szenario beantworten dieselbe Frage auf zwei Arten und dürfen sich nicht überlagern —
das Band gibt es deshalb nur zum Erwartungswert; bei einem Szenario wäre es doppelt gezählt.

#### Warum ρ = 0,5 und nicht 0

Der erste Ansatz nahm ρ = 0 an: unabhängige Fehler, die sich weitgehend ausgleichen. Ein
rückwirkender Test hat das widerlegt. Prognose auf dem Stand **Ende Februar 2026**, verglichen
mit dem, was von März bis August tatsächlich passiert ist:

| Monat | Plan-Saldo | Ist-Saldo | Band ρ=0 | Band ρ=0,5 |
|---|---|---|---|---|
| 03/2026 | 242.131 | 276.864 | ✗ | ✗ |
| 04/2026 | 247.526 | 219.192 | ✗ | ✓ |
| 05/2026 | 237.938 | 195.452 | ✗ | ✓ |
| 06/2026 | 273.683 | 181.134 | ✗ | ✓ |
| 07/2026 | 280.037 | 137.356 | ✗ | ✓ |
| 08/2026 | 292.254 | 86.075 | ✗ | ✓ |

Mit ρ = 0 hätte das Band die Realität in **keinem einzigen Monat** eingefangen — im August lag
die Untergrenze bei 202.715, tatsächlich waren es 86.075. Die nötige Korrelation wächst über den
Horizont auf 0,4. Das ist auch fachlich plausibel: Die großen Erlöszeilen eines kleinen
Unternehmens hängen an denselben Treibern — Markt, Pipeline, ein Großkunde. ρ = 0,5 deckt das
mit Reserve ab und sagt in einem Satz, was gemeint ist: Die Hälfte des Fehlers ist gemeinsam,
die Hälfte eigen.

Der verbleibende Fehlschlag ist **März 2026** — und zwar nach *oben*: Eine Leistung, für die
+5.000 prognostiziert waren, brachte +104.880. Einen neuen Großkunden kann kein aus Historie
abgeleitetes Band vorhersehen. Das bleibt so und wird nicht wegmodelliert.

Am Beispielmandanten (Datenstand 09.09.2026 11:12 — die Beispieldatenbank wird weiter
bearbeitet, die Beträge verschieben sich mit jeder Regeländerung):

| | Saldo 12/2027 |
|---|---|
| Stresstest optimistisch | +408.168 |
| oberes Band | +252.364 |
| **erwartet** | **−208.604** |
| unteres Band | −669.572 |
| Stresstest pessimistisch | −825.376 |

Dass der Stresstest **außerhalb** des Bands liegt, ist kein Widerspruch, sondern
Konstruktion: Er ist der Fall ρ = 1 — jede Regel irrt gleichzeitig in dieselbe Richtung —,
das Band rechnet mit ρ = 0,5. Beide Grenzen des Stresstests müssen deshalb weiter außen
liegen als die des Bands. Alle fünf Zahlen sind hier auf derselben Grundlage angegeben, dem
Saldo im Endmonat; ein Vergleich von Tiefstand gegen Höchstwert würde die Reihenfolge
scheinbar umkehren.

Eine Eigenart des optimistischen Stresstests: Sein *Tiefstand* liegt bei +86.075 und damit
exakt auf dem heutigen Kontostand — die Kurve fällt dort nie unter das Ausgangsniveau. Das
liegt an den gedeckelten Bandbreiten: Bei einer Leistung mit 100 % gemessenem Fehler hebt das
optimistische Szenario eine Ausgabe vollständig auf. Für eine Regel, die so schlecht trifft,
ist „findet vielleicht gar nicht statt" eine ehrliche Aussage — die Summe daraus ist aber
kein realistischer Verlauf, sondern die äußerste Ecke des Möglichkeitsraums.

`ERROR_CORRELATION` ist eine dokumentierte Konstante in `app/forecast/backtest.py` und an einer
Stelle änderbar. Sie ist an einem Mandanten über sechs Monate kalibriert — mit wachsender Zahl
an Plan-Ist-Snapshots lässt sie sich breiter prüfen.

### Was der Rückvergleich über die Prognose als Ganzes sagt

Derselbe rückwirkende Test zeigt eine systematische Schieflage. März bis August 2026:

| | Betrag |
|---|---|
| Prognose (Stand Ende 02/2026) | **+84.627** |
| tatsächlich | **−121.551** |
| Abweichung | **−206.178** |

Zerlegt:

| Anteil | Ist | Plan | Beitrag zur Lücke |
|---|---|---|---|
| Leistungen mit Regel | −71.498 | +84.627 | **−156.125** |
| Matrixleistungen ohne Regel | −44.615 | 0 | −44.615 |
| nicht in der Matrix (interne Umbuchungen) | −5.438 | – | −5.438 |

Der größte Einzelposten: eine Einnahmenleistung mit +241.360 Plan gegen +114.960 Ist. Ihr
gemessener relativer Fehler war 0,30 — die Regel war also als nur mittelgut ausgewiesen, aber
die tatsächliche Abweichung lag beim 1,75-fachen des Bands. Genau dafür ist ρ da.

Die Lehre für die Nutzung: **Der Erwartungswert ist bei diesem Mandanten eher zu optimistisch.**
Die Kennzahl „nicht abgedeckt" unterschätzt das zusätzlich, weil sie die vergangenen zwölf Monate
misst und nicht den Prognosezeitraum — sie meldete 3.146 €/Monat, tatsächlich fehlten
7.436 €/Monat aus Leistungen ohne Regel.

### Plan-Ist-Snapshots

Prognosewerte werden sonst bewusst nie gespeichert. Hier ist es der Zweck: Nur wenn festgehalten
ist, was am 15.09. für den Dezember erwartet wurde, lässt sich später beurteilen, ob die Prognose
etwas taugte. Ein Snapshot (`forecast_snapshots`, Migration `028`) hält Monatsebene fest —
Ein-, Auszahlungen, Endsaldo — und ist unveränderlich.

Zwei Feinheiten:

- **Verglichen wird gegen alle Kontobewegungen**, nicht nur gegen die prognostizierten
  Leistungen. Der Snapshot sagt einen Kontostand voraus, und den bewegt jede Buchung — auch die,
  für die es nie eine Regel gab. Alles andere wäre eine geschönte Messung.
- **Der Stichtag grenzt sauber ab.** Der Anfangssaldo enthält alles bis einschließlich des
  Stichtags, auch mitten im Monat; als Ist zählt deshalb nur `valuta_date > Stichtag`. Der
  laufende Monat wird angezeigt, geht aber nicht in die Kennzahl ein — halb gebucht würde er die
  Abweichung immer zu groß aussehen lassen.

Ausgewiesen werden je Monat die Abweichung **des Monats** (welcher Monat lief aus dem Ruder) und
die **aufgelaufene** Saldoabweichung (die für die Liquidität entscheidende Zahl, weil ein guter
Monat einen schlechten ausgleicht).

### Ergebnis beim Beispielmandanten

| Kennzahl | Wert |
|---|---|
| Leistungen | 410 |
| davon ohne Prognose | 312 |
| davon rückverglichen | 132 |
| Regel durch Messung gewechselt | 36 |
| als beendet erkannt | 67 |
| Regel trifft schlechter als die Nullprognose | 6 |
| typischer relativer Fehler (Median) | 37 % |
| Bandabdeckung im rückwirkenden Test | 5 von 6 Monaten |

Laufzeit: 0,09 s für alle 410 Leistungen — der Rückvergleich läuft bei jedem Seitenaufruf mit,
gecacht wird nichts.

### Was bewusst offen bleibt

- **Kein KI-Assistent.** Der ursprüngliche Plan sah ihn als optionalen Teil von Phase 3 hinter
  einem Feature-Flag vor. Die Messung zeigt, wo die Arithmetik nicht trägt: bei 6 von 132
  messbaren Leistungen und bei den 278 ohne Rückvergleich. Dort fehlt aber Historie, nicht
  Semantik — ein LLM würde daran ebenso wenig ändern. Sinnvoll wäre er erst für den Fall
  „zwei Zahlungen, aber der Buchungstext sagt Jahresabo". Das ist Phase 4.
- **Der Rückvergleich läuft nur bei genügend Historie.** 278 der 410 Leistungen bleiben
  ungemessen. Ihre Bandbreite ist weiterhin geschätzt.
