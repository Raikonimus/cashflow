# Konzept: Code-Review

Stand: 2026-09-09

Ziel: den bestehenden Code von cashflow einmal systematisch prüfen — nicht als
Geschmacksdiskussion, sondern gerichtet auf die Fehler, die in diesem konkreten
System wirklich weh tun: fremde Mandantendaten, falsche Beträge, stille
Datenverluste beim Import.

---

## 1. Ausgangslage (gemessen am 2026-09-09)

| Kennzahl | Wert |
|---|---|
| Backend-Produktivcode | 15.395 Zeilen in 59 Dateien |
| Frontend-Produktivcode | 15.019 Zeilen in 54 Dateien |
| Testcode | 12.878 Zeilen (Backend) + 29 Testdateien (Frontend) |
| Tests | 452 Backend (pytest), 222 Frontend (vitest) — alle grün |
| API-Endpunkte | 96 in 9 Router-Modulen |
| DB-Queries in Services | 184 `select(`-Statements |
| Historie | 43 Commits, Projektstart 2026-04-06, also rund 5 Monate |
| Dokumentierte Entscheidungen | 17 ADRs im `decision-index` |

Zwei Eigenschaften dieses Projekts bestimmen den Zuschnitt des Reviews:

1. **Der Code wurde nie von einem Zweiten gelesen.** Es gibt keinen Pull-Request-
   Verlauf, keine Review-Kommentare, keine zweite Person, die widersprochen hätte.
   Jede Annahme, die beim Schreiben falsch war, ist bis heute unwidersprochen.
2. **Die Tests sind grün, aber grün heißt nur: was geprüft wird, stimmt.** 674 Tests
   sind viel. Sie sagen nichts über den Fall, den niemand aufgeschrieben hat — und
   genau dort liegen die Befunde, die ein Review findet.

### Werkzeuglage — die eigenen Standards sind nicht durchgesetzt

`memory-bank/standards/coding-standards.md` sagt: *„Both formatters are
non-negotiable; CI must enforce them."* Der Ist-Zustand:

| Prüfung | Ergebnis heute |
|---|---|
| Ruff | 950 Befunde (729× E501, 144× UP045, 28× I001, 18× E402, 17× UP017, 4× F401, 2× F821) |
| Black | 37 von 59 Dateien würden umformatiert |
| ESLint | 26 Befunde (23 Fehler, 3 Warnungen) |
| CI | **keine** — `.github/` enthält nur Agenten-Prompts, keine Workflows |
| Ruff/Black als Dev-Dependency | **nicht installiert** (`pyproject.toml` konfiguriert sie, aber niemand zieht sie) |

Das ist kein Nebenbefund, sondern der Grund, warum ein manuelles Review überhaupt
so viel Fläche hat: Alles, was ein Linter erledigen könnte, landet sonst im
Lesebudget.

---

## 2. Leitfrage und Nicht-Ziele

**Leitfrage:** *Wo kann dieses System still das Falsche tun, ohne dass ein Test
oder ein Nutzer es merkt?*

„Still" ist das entscheidende Wort. Ein Absturz meldet sich selbst. Eine Zahl, die
um 20 % danebenliegt, und ein Mandantenfilter, der fehlt, melden sich nicht.

**Ausdrücklich nicht Gegenstand dieses Reviews:**

- Performance und Lastverhalten (kein Profiling, keine Lasttests)
- Penetrationstest / Angriffssimulation
- UX- und Designbewertung
- Neubewertung getroffener Architekturentscheidungen (die 17 ADRs gelten als gesetzt;
  ein Review kann eine ADR *in Frage stellen*, aber nicht nebenbei umwerfen)
- Feature-Wünsche

---

## 3. Der Kernkonflikt: 30.000 Zeilen liest niemand

Ein zeilenweises Review von 30.414 Zeilen ist weder leistbar noch nützlich — die
Aufmerksamkeit ist nach dem ersten Tausend verbraucht, und der Ertrag pro Zeile ist
im Mittel nahe null. Deshalb zwei Grundsätze:

**Grundsatz 1 — Priorisierung nach Schaden × Wahrscheinlichkeit.** Nicht jede Datei
ist gleich viel wert. `app/partners/service.py` mit 43 Queries auf Mandantendaten
ist ein anderes Risiko als eine Schema-Datei.

**Grundsatz 2 — was maschinell prüfbar ist, wird maschinell geprüft.** Lesen ist die
knappe Ressource. Jede Prüfung, die sich als Skript, Grep oder Test formulieren
lässt, wird so formuliert — dann gilt sie für alle 184 Queries statt für die 40, die
man durchhält, und sie gilt auch noch beim nächsten Commit. Manuelles Lesen bleibt
für das reserviert, was sich nicht mechanisieren lässt: fachliche Richtigkeit.

---

## 4. Die fünf Prüfachsen, nach Risiko geordnet

### A1 — Mandantentrennung (höchstes Risiko)

**Warum zuerst:** Das System ist mandantenfähig, aber die Trennung ist *nicht*
strukturell erzwungen. Es gibt keine Row-Level-Security, keinen Session-Scope, keinen
Query-Interceptor. Jede einzelne der 184 Queries muss ihren `mandant_id`-Filter selbst
mitbringen. Eine vergessene Where-Klausel zeigt einem Mandanten die Buchungen eines
anderen — und kein Test schlägt an, weil Tests typischerweise mit einem Mandanten laufen.

**Was geprüft wird:**
- Jede Query auf eine mandantengebundene Tabelle filtert auf `mandant_id`
- Jeder der 96 Endpunkte hängt an `require_mandant_access` (heute: 93 Vorkommen in
  9 Routern — die Differenz ist zu klären, nicht zu vermuten)
- Objekte, die per `id` geladen werden (`session.get(...)`), prüfen danach die
  Mandantenzugehörigkeit — `get` kennt keinen Filter
- Rollenprüfung (`require_role`) passt zur Wirkung des Endpunkts: löschende und
  ändernde Endpunkte nicht auf `viewer`-Niveau
- Global eindeutige Entitäten (z. B. IBAN laut ADR-008) leaken keine mandantenfremden
  Informationen über Kollisionen

**Wie:** überwiegend maschinell. Ein AST-Skript, das jede `select()`/`get()`-Stelle in
`app/*/service.py` gegen eine Liste mandantengebundener Modelle hält und die Treffer
ohne Filter meldet. Manuell nachgelesen wird nur, was das Skript meldet.

**Umfang:** Skript bauen + ~184 Queries maschinell prüfen, davon erfahrungsgemäß
10–20 zum Nachlesen.

---

### A2 — Geldrichtigkeit

**Warum an zweiter Stelle:** Das Produkt ist eine Finanzauswertung. Eine Zahl, die
falsch ist, aber plausibel aussieht, wird geglaubt und für Entscheidungen benutzt.
Der Schaden entsteht ohne Fehlermeldung.

Der bisher stärkste Befund dieser Art in diesem Projekt fiel *nicht* durch einen Test
auf, sondern durch eine Nachfrage („Was zahlt Softcom im Februar?") — dahinter lag
eine vergessene +100-%-Anpassung, die die gesamte Prognose verzerrte. Genau solche
Fälle sucht diese Achse.

**Was geprüft wird:**
- `Decimal` durchgängig, kein `float` auf Geldpfaden *(Vorabmessung: 0 Treffer für
  `float(` im Backend — gute Ausgangslage, bleibt zu bestätigen für Serialisierung
  und Frontend)*
- Rundung: **wo** wird gerundet, und passiert es genau einmal? Summe gerundeter Werte
  ≠ gerundete Summe
- Netto/Brutto: die Matrix führt beide Werte je Zelle. Jede Anzeige, jeder Export und
  jede Weiterverrechnung muss dieselbe Größe meinen
- Vorzeichenkonvention (Einnahme positiv, Ausgabe negativ) über alle Schichten hinweg,
  besonders an Aggregationsgrenzen
- Währung: wird sie überhaupt geführt, oder implizit EUR angenommen?
- Prognose: die Unsicherheitsaggregation (`ERROR_CORRELATION = 0.5`) ist eine
  begründete, aber gesetzte Annahme — sie gehört auf den Prüfstand, weil sie jede
  Bandbreite skaliert

**Wie:** gemischt. Typprüfung und `float`-Suche maschinell; Rundung, Vorzeichen und
Netto/Brutto sind Lesearbeit an den Aggregationsstellen.

**Umfang:** ~4 Dateien intensiv (`journal/service.py`, `forecast/service.py`,
`forecast/backtest.py`, `IncomeExpensePage.tsx`) plus Exportpfade.

---

### A3 — Fachliche Invarianten: Import, Matching, Review

**Warum:** Hier entstehen die Daten. Ein Fehler wirkt nicht auf eine Anzeige, sondern
auf den Bestand — und ist später schwer bis nicht rückgängig zu machen. Die
Commit-Historie zeigt, dass in genau diesem Bereich zuletzt gehäuft nachgebessert
wurde (Dublettenerkennung, Kopfzeilen überspringen, allgegenwärtige Kennungen,
Händlergruppierung) — vier Korrekturen in den letzten acht Commits sind ein Signal,
kein Zufall.

**Was geprüft wird:**
- Idempotenz: derselbe Import zweimal — entsteht derselbe Bestand?
- Teilfehler: bricht ein Import in der Mitte ab, bleibt kein halber Zustand zurück
  (Transaktionsgrenzen)
- Dublettenerkennung: zählt Vorkommen, nicht Existenz (war ein realer Bug) — und wie
  verhält sie sich bei echten Doppelzahlungen, die *keine* Dublette sind?
- Matching: Regelreihenfolge, Konfliktfälle, Nachvollziehbarkeit einer Zuordnung
- Review-Lifecycle (`open → confirmed/adjusted`, ADR-014): sind alle Übergänge
  abgedeckt, gibt es Sackgassen?
- Audit-Log (ADR-017): wird alles Relevante geschrieben, und stimmt es auch bei
  Fehlerpfaden?

**Wie:** überwiegend lesend, ergänzt um gezielte neue Tests für gefundene Lücken.
Ein Befund dieser Achse ist erst dann bewiesen, wenn ein Test ihn zeigt.

**Umfang:** ~2.900 Zeilen (`imports/`, `review/`) plus `imports/matching.py`.

---

### A4 — Struktur und Wartbarkeit

**Warum:** Niedrigeres Sofortrisiko, aber es bestimmt, wie teuer jede künftige
Änderung wird — und wie wahrscheinlich der nächste Fehler in A1–A3 ist.

**Konkrete Ansatzpunkte aus der Vorabmessung:**

| Befund | Zahl |
|---|---|
| Größte Backend-Datei | `services/service.py` — 1.598 Zeilen |
| Weitere > 900 Zeilen | `review/service.py` (1.247), `partners/service.py` (1.036), `journal/service.py` (967), `forecast/service.py` (965) |
| Größte Frontend-Datei | `IncomeExpensePage.tsx` — 1.437 Zeilen |
| Funktionslokale Importe | 33 Stellen in 10 Dateien — Indiz für Zirkelbezüge |
| Abweichung vom eigenen Standard | Standard fordert `src/features/*` + `src/shared/*`, tatsächlich `src/pages/*` + `src/components/*` |

Die 2 gemeldeten `F821`-Befunde (`AccountPreviewResponse` in `partners/service.py:324`
und `:541`) sind **keine Laufzeitfehler** — die Annotation ist ein String, der Import
steht funktionslokal. Sie sind aber genau der Marker für das darunterliegende Problem:
Importe werden in Funktionen versteckt, um Zyklen zu umgehen.

**Zu entscheiden ist hier auch etwas Grundsätzliches:** Die Frontend-Struktur weicht
vom eigenen Standard ab. Entweder der Code zieht nach oder der Standard wird
korrigiert — beides ist vertretbar, der Schwebezustand nicht.

**Wie:** maschinell (Dateigrößen, Zyklen, Importgraph) plus eine Bewertung, welche
Große-Datei-Befunde sich zu teilen lohnen und welche nur lang, aber geordnet sind.

---

### A5 — Werkzeugkette

**Warum zuletzt in der Reihenfolge, aber zuerst in der Umsetzung:** Die 950 Ruff- und
26 ESLint-Befunde sind fast alle harmlos (729× zu lange Zeile). Sie *verstecken* aber
die wenigen, die es nicht sind — bei 950 Meldungen sieht niemand die zwei, die zählen.

**Was passiert:**
- Ruff und Black als Dev-Dependency aufnehmen (heute konfiguriert, aber nicht installiert)
- `[tool.ruff]` → `[tool.ruff.lint]` (die aktuelle Konfiguration ist deprecated)
- Automatisch behebbare Befunde in **einem** separaten Formatierungs-Commit erledigen
  (193 fixable + Black) — getrennt von jeder inhaltlichen Änderung, sonst ist die
  Historie unlesbar
- Für den Rest eine bewusste Entscheidung: beheben oder in `ignore` mit Begründung
- CI-Workflow, der Lint + Format + beide Testsuiten fahren lässt

Ohne diesen Schritt sind die Befunde des Reviews nach drei Wochen wieder da.

---

## 5. Ablauf

| Etappe | Inhalt | Ergebnis |
|---|---|---|
| **0** | Werkzeuge scharf machen (A5), Formatierungs-Commit, Prüfskripte für A1 bauen | sauberer Ausgangspunkt, ab hier ist jeder Lint-Befund echt |
| **1** | Mandantentrennung (A1) | Liste ungeschützter Queries/Endpunkte |
| **2** | Geldrichtigkeit (A2) | Liste der Stellen, an denen eine Zahl falsch werden kann |
| **3** | Import/Matching/Review (A3) | Invariantenverletzungen, je mit reproduzierendem Test |
| **4** | Struktur (A4) | Refactoring-Vorschläge, nach Nutzen sortiert |
| **5** | Bericht, Priorisierung, Entscheidung über Umsetzung | Befundliste + Empfehlung |

Die Etappen 1–3 sind unabhängig voneinander und können in beliebiger Reihenfolge
laufen — die Reihenfolge oben ist die nach Risiko. Etappe 0 muss zuerst kommen.

**Nach jeder Etappe gibt es einen Zwischenstand.** Ein Review, dessen Ergebnis erst
am Ende sichtbar wird, ist ein Review, bei dem man drei Etappen lang nicht steuern kann.

---

## 6. Befundformat

Jeder Befund besteht aus:

1. **Ort** — `datei.py:zeile`
2. **Behauptung** — ein Satz, was falsch ist
3. **Fehlerszenario** — konkrete Eingabe/Zustand → falsches Ergebnis
4. **Schwere** (siehe unten)
5. **Vorschlag** — was zu tun wäre, nicht zwingend gleich der Patch

**Die harte Regel: Kein Befund ohne Fehlerszenario.** Wenn sich nicht sagen lässt,
bei welcher Eingabe etwas schiefgeht, ist es Geschmack und gehört nicht in die Liste.
Das ist die Bremse gegen den typischen Review-Ausgang, bei dem 80 Stilpunkte die
drei echten Fehler zudecken.

### Schweregrade

| Grad | Kriterium | Umgang |
|---|---|---|
| **kritisch** | Datenverlust, mandantenfremde Daten, falsche Beträge in der Anzeige | sofort beheben, vor allem anderen |
| **hoch** | Fehler tritt unter realistischen Bedingungen auf, wirkt aber nicht auf Bestand oder Trennung | in diesem Durchgang beheben |
| **mittel** | Fehler braucht eine ungewöhnliche Konstellation, oder: strukturelles Risiko für künftige Fehler | bewusst entscheiden: jetzt oder als Aufgabe notieren |
| **niedrig** | Konsistenz, Lesbarkeit, Duplikate | sammeln, gebündelt in einem eigenen Durchgang |

---

## 7. Umgang mit den Befunden

- **Reviewen und Beheben werden getrennt.** Erst die vollständige Liste, dann die
  Entscheidung, was behoben wird. Sonst versandet das Review im ersten interessanten Bug.
- **Ein Befund, ein Commit.** Keine Sammelcommits mit fünf unabhängigen Korrekturen.
- **Jeder Fix aus A1–A3 bekommt einen Test**, der ohne den Fix rot ist. Ein Fix ohne
  Test ist eine Behauptung.
- **Kein Refactoring im Fix-Commit.** Formatierung und Umbauten laufen in eigenen
  Commits, sonst ist im Diff nicht zu sehen, was sich fachlich geändert hat.

---

## 8. Ergebnisse

1. **Befundliste** — nach Schwere sortiert, jeder Eintrag im Format aus Abschnitt 6
2. **Prüfskripte** — die maschinellen Checks aus A1/A2 bleiben im Repo und laufen künftig in CI
3. **CI-Workflow** — Lint, Format, beide Testsuiten
4. **Aktualisierte Standards** — dort, wo Code und `coding-standards.md` auseinanderlaufen,
   wird eine Seite angepasst
5. **Empfehlung** — was sofort, was später, was bewusst nicht

---

## 9. Nach dem Review — einmalig oder dauerhaft?

**Das Review selbst ist einmalig.** Die Etappen 0–4 sind eine Grundreinigung:
30.000 Zeilen, die nie jemand gelesen hat, einmal durchgehen. Dieselbe Übung in
sechs Monaten zu wiederholen wäre größtenteils verschwendet — der Bestand ändert
sich nicht flächendeckend, man läse zu 90 % dasselbe noch einmal.

**Die Prüfungen sind dauerhaft.** Jede Etappe hinterlässt absichtlich etwas, das
danach ohne weiteres Zutun weiterläuft: Das Mandantenskript aus Etappe 1 prüft ab
dann bei jedem Commit alle Queries, nicht nur die 184 von heute; der CI-Workflow
aus Etappe 0 hält Lint, Format und beide Testsuiten. Was einmal mechanisiert ist,
kostet ab dann nichts mehr und muss nie wieder gelesen werden.

Was darüber hinaus wiederkehrt, kehrt **ereignisgesteuert** wieder, nicht nach Kalender:

| Anlass | Was | Umfang |
|---|---|---|
| Jeder Merge nach `main` | Review des Diffs, nicht des Bestands | klein |
| Neuer Aggregations- oder Exportpfad | A2 für diesen Pfad | klein |
| Änderung an Importformat oder Matching-Regeln | A3 für den geänderten Teil | mittel |
| Datei > 1.000 Zeilen, neuer Importzyklus | CI-Warnung statt Durchsicht | automatisch |

Die erste Zeile ist die wichtigste. Bei 43 Commits ohne einen einzigen Pull Request
gibt es keinen Moment, in dem jemand auf eine Änderung schaut, bevor sie im Bestand
ist. Nicht der Altbestand ist das eigentliche Problem — der wird mit diesem Review
gerade abgearbeitet —, sondern dass Neues ungeprüft dazukommt.

**Wovon abzuraten ist:** ein Vollreview nach Kalender („jedes Quartal alles"). Das
degeneriert zuverlässig — die Aufmerksamkeit sinkt beim zweiten Durchgang, die
Befunde wiederholen sich, nach dem dritten Mal ist es Ritual statt Prüfung.
Risikobasierte Auslöser schlagen feste Intervalle, aus demselben Grund, aus dem in
Abschnitt 3 „Priorisierung nach Schaden × Wahrscheinlichkeit" steht.

---

## 10. Offene Entscheidungen

| Frage | Empfehlung |
|---|---|
| Gesamter Code oder nur der neue Prognose-Teil? | **Gesamter Code.** Der Prognoseteil ist der jüngste und am besten dokumentierte; die älteren Module (Import, Matching, Partner) haben mehr unbeobachtete Zeit hinter sich. |
| Formatierungs-Baseline: alles bereinigen oder einfrieren? | **Bereinigen.** 950 Befunde einzufrieren heißt, die Zahl nie wieder als Signal nutzen zu können. Ein einmaliger Formatierungs-Commit ist billig; er macht allerdings `git blame` an vielen Zeilen unbrauchbar — deshalb genau ein Commit, sauber betitelt. |
| Befunde sofort beheben oder erst vollständig sammeln? | **Sammeln, dann beheben** — mit einer Ausnahme: kritische Befunde (Mandantentrennung, falsche Beträge) werden sofort behoben. |
| Frontend-Struktur an den Standard anpassen? | **Standard anpassen.** `src/pages/*` ist die etablierte, funktionierende Struktur; ein Umbau von 54 Dateien hätte kein Ziel außer Regelkonformität. |
