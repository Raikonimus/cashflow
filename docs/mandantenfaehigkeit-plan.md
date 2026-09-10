# Mandantenfähigkeit — Analyse und Prüfplan

**Stand: 2026-09-10.** Löst den am 2026-09-09 vertagten Sammelpunkt aus
`code-review-befunde.md` ein („Vorgemerkt: Mandantenfähigkeit prüfen und sicherstellen").
Das Code-Review ist mit Etappe 4 abgeschlossen, dieser Punkt war der letzte offene.

Dieses Dokument hat zwei Teile: **was heute gilt** (gemessen, nicht geschätzt) und
**wie geprüft und getestet wird** (Stufen 0–5). Die Befunde tragen Nummern `M1`–`M14`,
damit spätere Commits auf sie zeigen können.

---

## Teil 1 — Was heute gilt

### Die Ausgangsfrage: Kann ein Nutzer mehrere Mandanten haben?

**Strukturell ja, bedienbar nein.** Die Antworten fallen auseinander, und genau
dazwischen liegen die Befunde.

| Ebene | Antwort | Belegt durch |
|---|---|---|
| Datenmodell | **ja** | `mandant_users` ist eine echte n:m-Tabelle mit zusammengesetztem Primärschlüssel `(mandant_id, user_id)`, ohne Unique auf `user_id` |
| API | **ja** | `POST /mandants/{id}/users` legt beliebig viele Zuordnungen an, `/auth/login` liefert die Liste, `/auth/select-mandant` tauscht das Token |
| Tests | **ja** | `test_multiple_mandants_requires_selection`, `test_assigned_user_can_select_mandant`; seit Stufe 0 zusätzlich die Fixture `zwei_mandanten` |
| Datenbestand | **zwei Mandanten, aber kein Nutzer mit zwei** | siehe „Der Datenbestand" — der zweite Mandant hat *null* zugeordnete Nutzer |
| Bedienoberfläche | **nein** | es gibt keinen Weg, eine zweite Zuordnung anzulegen (→ M7) |

Die Mehrmandantenfähigkeit ist also gebaut, aber die Zuordnung — der eine Vorgang, der
sie in Gang setzt — ist über die Oberfläche nicht erreichbar. Deshalb steht im
Datenbestand ein Mandant mit echten Daten, den niemand auswählen kann.

### Der Datenbestand

**Korrigiert am 2026-09-10, im Lauf desselben Tages.** Die erste Messung um 09:5x ergab
einen Mandanten. Um 10:18 entstand ein zweiter — „Calista", angelegt während der
Analyse. Gemessen um 12:28:

```
mandanten     2
              Goodguys GmbH    2 Konten   356 Partner   22 Importläufe   1 Nutzer
              Calista          1 Konto  2.597 Partner    8 Importläufe   0 Nutzer
nutzer        1     raimund.oberreiter@goodguys.ai (admin)
zuordnungen   1     admin → Goodguys GmbH
```

Das ist kein Testmandant. **„Calista" trägt echte Daten** — 2.597 Partner aus acht
Importläufen — und **keinen einzigen zugeordneten Nutzer.**

Zwei Folgerungen, die den Plan verändern:

1. **Entscheidung E1 ist damit faktisch beantwortet.** Das System läuft *jetzt* mit
   zwei Mandanten und echten Daten in beiden. Der ganze Komplex ist keine Vorsorge
   mehr, sondern Gegenwart — und die Reihenfolge „Trennung *vorher* strukturell" ist
   bereits verpasst. Was zwischen den beiden Mandanten schon vermischt wurde, lässt
   sich nachträglich nicht feststellen; das ist die Eigenschaft leiser Fehler.
2. **M5 ist keine Theorie, sondern beißt.** Ein Mandant ohne Zuordnung ist über die
   Oberfläche unerreichbar: `require_mandant_access` würde den Admin durchlassen,
   aber `_get_mandants_for_user` bietet ihm nur die *verknüpften* Mandanten zur
   Auswahl an. „Calista" erscheint also in keiner Auswahlliste, obwohl die
   Berechtigung reicht. Die Zuordnung nachzutragen ist heute nur per API-Aufruf oder
   von Hand in der Datenbank möglich — das ist M7.

Der einzige Nutzer ist **Admin** — und damit läuft er genau durch den Pfad, der die
Auswahllogik überspringt (M4). Wer die Mandantenauswahl heute ausprobiert, prüft nicht
den Weg, den ein normaler Nutzer nimmt.

Nebenbefund ohne Bezug zur Mandantenfähigkeit: Es liegt eine leere `frontend/cashflow.db`
(0 Bytes, 2026-09-09) neben der echten `backend/cashflow.db`. Vermutlich ein Aufruf im
falschen Verzeichnis; sie gehört gelöscht oder ignoriert, damit niemand sie für die
Datenbank hält.

### M1–M3 · Was trägt

**M1 — Die äußere Schicht ist vollständig.** Maschinelle Zählung über alle `router.py`:

| | Anzahl |
|---|---:|
| Endpunkte gesamt | 104 |
| davon mit `{mandant_id}` im Pfad | 76 |
| davon mit `require_mandant_access` | 69 |
| ohne Prüfung | **7 — alle `require_role("admin")`** |

Die sieben sind `POST/DELETE /mandants/{id}/users` und fünf Mandantenverwaltungs-Endpunkte
in `tenants/router.py`. Admin umgeht die Mandantenprüfung laut ADR-001 absichtlich, die
Lücke ist also keine. `check_tenancy.py` bestätigt unabhängig: **0 Endpunkte mit
ungeprüfter zweiter Kennung.** Die Module `imports` und `review` nehmen `mandant_id` als
Query-Parameter statt im Pfad und prüfen ebenfalls.

**M2 — Die Auswahl nach dem Anmelden ist gebaut und getestet.** Für Nicht-Admins:
`login()` liefert `requires_mandant_selection: len(mandants) > 1`, das Frontend springt
nach `/login/select-mandant`, `SelectMandant.tsx` listet die Mandanten, ein Klick holt
über `/auth/select-mandant` ein Token mit `mandant_id` und landet auf `/`. Bei genau
einem Mandanten wird automatisch gewählt — in `Login.tsx` **und** in `SelectMandant.tsx`,
also zweimal (harmloser Zwilling, aber ein Zwilling).

**M3 — Rollen und Mandanten sind saubere getrennte Achsen.** `require_role` prüft die
Hierarchie, `require_mandant_access` die Zugehörigkeit. Beide werden nebeneinander
angewendet, keine der beiden vertritt die andere.

### M4–M10 · Was fehlt

**M4 — Admins sind aus der Auswahllogik herausdefiniert.** `auth/service.py:83-94`
kehrt für `role == admin` früh zurück, mit `requires_mandant_selection: False`,
**unabhängig von der Anzahl der Mandanten.** Ein Admin mit zwei Mandanten bekommt also
kein Auswahlsignal. Die Auswahlseite wird trotzdem erreicht — aber nur, weil
`MandantRequiredRoute` das fehlende `mandant_id` bemerkt und umleitet, nachdem
`Login.tsx` bereits nach `/` navigiert hat. Der Weg funktioniert über einen Umweg, den
niemand entworfen hat. Da der einzige heutige Nutzer Admin ist, ist das der Pfad, der
zuerst benutzt wird.

**M5 — Die Reichweite eines Admins ist im API größer als in der Oberfläche.**
`require_mandant_access` lässt Admins auf **jeden** Mandanten zugreifen.
`_get_mandants_for_user` liefert ihnen aber nur die **verknüpften**. Ein Admin ohne
Zuordnung sieht eine leere Auswahl und wird von `MandantRequiredRoute` nach
`/admin/mandants` geschickt — obwohl er auf alle Daten zugreifen darf. Zwei Definitionen
von „welche Mandanten gehören zu diesem Nutzer", die nicht übereinstimmen.

**M6 — Ein Nutzer ohne Mandant landet in einer Sackgasse.** `create_user()` legt
**keine** Zuordnung an. Jeder neu eingeladene Nutzer beginnt also mit null Mandanten. Der
Weg danach: Anmelden gelingt → `mandants: []`, `requires_mandant_selection: false` →
Frontend navigiert nach `/` → `MandantRequiredRoute` leitet nach
`/login/select-mandant` → `SelectMandant` sieht die leere Liste und leitet nach `/login`
→ dort steht die Anmeldemaske, obwohl ein gültiges Token im Store liegt. Keine Meldung
erklärt, was fehlt. Das trifft **jeden** neuen Nutzer, bis ein Admin ihn zuordnet.

**M7 — In der Nutzerverwaltung lassen sich keine Mandanten zuordnen.** Das ist die
Lücke, die die Aufgabenstellung nennt, und sie ist vollständig:

| Baustein | Stand |
|---|---|
| `UserDialog.tsx` (Anlegen und Bearbeiten) | nur E-Mail und Rolle |
| `UsersPage.tsx` | zeigt keine Mandanten an |
| `assignUserToMandant` in `api/users.ts:116` | vorhanden, **wird nirgends aufgerufen** — toter Code |
| Gegenstück zum Entfernen im Frontend | fehlt ganz |
| Endpunkt „Mandanten dieses Nutzers" | existiert nicht |
| `UserDetailResponse` | trägt kein Mandantenfeld |

Zuordnungen sind heute nur per direktem API-Aufruf oder von Hand in der Datenbank
möglich.

**M8 — Zuordnen kann nur der Admin, auch für den eigenen Mandanten nicht der
Mandant-Admin.** `POST/DELETE /mandants/{id}/users` verlangen `admin`, und `GET /mandants`
— nötig, um überhaupt Auswahlmöglichkeiten anzubieten — ebenfalls. Ein Mandant-Admin darf
Nutzer seines Mandanten auflisten, anlegen und ändern, sie aber keinem Mandanten
zuordnen. Er kann also einen Nutzer anlegen, der anschließend in der Sackgasse aus M6
sitzt und auf einen Admin warten muss. **Das ist eine Entscheidung, keine Reparatur**
(→ Entscheidung E2).

**M9 — Ein deaktivierter Mandant bleibt wählbar.** `_get_mandants_for_user` filtert auf
`Mandant.is_active == True`, `select_mandant` prüft nur die Zugehörigkeit — nicht
`is_active`. `deactivate_mandant` löscht die `mandant_users`-Zeilen nicht (das tut nur
`execute_cleanup`). Eine bekannte Mandanten-ID lässt sich damit weiter in ein gültiges
Token verwandeln, obwohl der Mandant abgeschaltet ist.

**M10 — Der gewählte Mandant ist keine Sicherheitsgrenze, sondern Anzeigezustand.**
`require_mandant_access` prüft die *Mitgliedschaft*, nie die Übereinstimmung von
`mandant_id` im Pfad und `mandant_id` im Token. Ein Nutzer mit zwei Mandanten kann mit
einem für A gewählten Token die Endpunkte von B ansprechen. Für die Berechtigung ist das
folgerichtig — er darf beide sehen. Es heißt aber, dass die Auswahl nichts erzwingt, und
das sollte dokumentiert sein, weil 76 Endpunkte ihre `mandant_id` aus dem Pfad nehmen und
nicht aus dem Token.

### M11–M14 · Die innere Schicht — Bestand aus dem Review

Diese vier sind im Review schon belegt und werden hier nur eingeordnet, weil der Plan
sie aufgreift.

**M11 — Die Trennung hängt an der Disziplin einzelner Queries.** Keine Row-Level-Security,
kein Query-Interceptor. `check_tenancy.py` heute:

```
264 Queries geprueft — OFFEN: 43, PRUEFEN: 103, OK: 98, GLOBAL: 20
```

Die 43 OFFEN sind einzeln gelesen und als Fehlalarm oder bewusst global eingestuft; die
Ratsche in CI (`--max-offen 43`) hält die Zahl fest. Ihre Verteilung ist der Befund:

| Datei | OFFEN | Abdeckung |
|---|---:|---:|
| `app/partners/service.py` | 12 | 30 % |
| `app/services/service.py` | 9 | 39 % |
| `app/review/service.py` | 6 | — |
| `app/journal/service.py` | 5 | — |
| `app/tenants/service.py` | 2 | 42 % |
| `app/auth/service.py` | — | 39 % |

**M12 — Zwei unabhängige Messungen zeigen auf dieselben Dateien.** 1.119 ungeprüfte
Anweisungen in genau den vier Modulen, die Mandanten, Konten, Partner, Leistungen und
Anmeldung verwalten. Ein struktureller Umbau dort würde ohne Netz stattfinden.

**M13 — Die Eindeutigkeits-Schlüssel kennen den Mandanten nicht.** `accounts`,
`partner_ibans`, `partner_accounts` sind global eindeutig (ADR-008). Zwei Mandanten mit
derselben IBAN kollidieren — beim Import still (A1-3), beim Kontoanlegen mit einem 409
ohne ADR-Grundlage (Konto-IBAN-Frage).

**M14 — `base_currency = "EUR"` steht zweimal als Literal** (`journal/service.py:495`,
`:617`), obwohl Konten ein `currency`-Feld führen (A2-3).

---

## Teil 2 — Der Prüf- und Testplan

### Reihenfolge und ihr Grund

Die Stufen sind so geschnitten, dass **jede für sich mergefähig** ist und die
Aussagekraft der jeweils nächsten erhöht. Die Empfehlung aus dem Review gibt die
Richtung vor: *Die Abdeckung dieser vier Module vor dem strukturellen Umbau anheben,
nicht danach.* Deshalb kommen Prüfumgebung und Tests vor der Struktur — nicht, weil
Struktur unwichtiger wäre, sondern weil man ihren Umbau sonst nicht bemerkt.

```
Stufe 0  Prüfumgebung: zwei Mandanten            ← ERLEDIGT 2026-09-10
Stufe 1  Auswahl beim Anmelden reparieren        ← ERLEDIGT 2026-09-10 (M4 M5 M6 M9 M2)
Stufe 2  Zuordnung in der Nutzerverwaltung       ← ERLEDIGT 2026-09-10 (M7 M8)
Stufe 3  Abdeckung der vier Module anheben       M12
Stufe 4  Isolationstest über alle 76 Endpunkte   M1 M10
Stufe 5  Struktur statt Disziplin                M11 M13 M14
```

---

### Stufe 0 — Prüfumgebung: zwei Mandanten

**Warum zuerst:** Solange jede Prüfung gegen einen Mandanten läuft, kann keine von ihnen
einen Mandantenfehler zeigen. Das ist die Wurzel des ganzen Punktes.

**Backend — eine gemeinsame Fixture** in `tests/conftest.py`, nicht pro Modul:

```
zwei_mandanten:
  Mandant A + Mandant B, je ein Konto, je ein Partner mit Leistung und Buchungen
  nutzer_a      → nur A          (accountant)
  nutzer_b      → nur B          (accountant)
  nutzer_beide  → A und B        (accountant)   ← der bisher nie existierende Fall
  nutzer_ohne   → kein Mandant   (viewer)       ← der Fall aus M6
  admin         → keine Zuordnung, volle Reichweite
```

Die drei vorhandenen Tenancy-Tests (`test_tenancy_iban_registration.py`,
`test_tenancy_import_runs.py`, `test_tenancy_apply_excluded.py`) bauen ihre zwei
Mandanten heute jeder selbst. Sie werden auf die Fixture umgestellt — sonst entsteht der
Zwilling, den Frage 1 des Merge-Checks sucht.

**Entwicklungsdatenbank:** ein zweiter Mandant mit eigenem Konto und wenigen Buchungen,
per Skript in `backend/scripts/`, idempotent und wiederholbar. Erst damit ist die
Mandantenauswahl von Hand überhaupt sichtbar.

**Fertig, wenn:** die Fixture steht, die drei Tests sie benutzen, `pytest -q` grün ist
und die Entwicklungsdatenbank zwei Mandanten hat.

#### Umgesetzt am 2026-09-10

| Was | Wo |
|---|---|
| Fixture `zwei_mandanten` mit zwei bestückten Welten und fünf Nutzern | `backend/tests/conftest.py` (neu) |
| Anmeldehelfer `anmelden`, der den echten Weg über `/auth/login` und `/auth/select-mandant` geht | ebd. |
| Selbsttest der Fixture — 12 Fälle | `backend/tests/test_pruefumgebung.py` (neu) |
| Skript für die Entwicklungsdatenbank, idempotent, mit `--trocken` | `backend/scripts/zweiter_mandant.py` (neu) |
| Zwei Tenancy-Tests auf die Fixture umgestellt, je um eine Gegenprobe ergänzt | `tests/imports/test_tenancy_import_runs.py`, `tests/tenants/test_tenancy_apply_excluded.py` |

Stand danach: **509 Tests grün**, 2 erwartete `xfail` (die bekannten ADR-008-Fälle),
`ruff`, `black` und `check_tenancy.py --strict --max-offen 43` grün.

**Drei Entscheidungen, die beim Umsetzen fielen** — jede weicht vom Wortlaut des Plans ab
und ist deshalb hier festgehalten:

1. **`test_tenancy_iban_registration.py` bleibt bei seinem eigenen Aufbau.** Der Plan
   wollte alle drei Tests umstellen. Diese Datei untersucht aber gerade den Fall
   *gleicher* IBAN in zwei Mandanten (ADR-008, M13) — die Fixture gibt jedem Mandanten
   absichtlich eine eigene und würde ihm die Ausgangslage wegnehmen. Außerdem ruft die
   Datei den Matching-Service direkt auf und braucht weder Nutzer noch Token. Der Grund
   steht jetzt im Kopf der Datei, damit niemand die Umstellung für vergessen hält.
2. **Beide umgestellten Tests haben eine Gegenprobe bekommen.** Ein Test, der nur auf
   403 prüft, bleibt auch bei einem Endpunkt grün, der grundsätzlich verweigert. Jetzt
   prüft jeder zusätzlich, dass derselbe Aufruf auf den *eigenen* Mandanten 200 liefert.
   Das ist Frage 5 des Merge-Checks, angewendet auf die eigene Arbeit.
3. **Das Skript fügt in einen vorhandenen Mandanten keine Beispieldaten ein.** Anlass
   war „Calista": ein vorhandener Mandant kann echte Daten tragen. Existiert der Name
   schon, beschränkt sich das Skript auf die fehlende Nutzerzuordnung — womit es genau
   den Zustand behebt, den M5 verursacht.

**Was Stufe 0 nicht angefasst hat:** Die sechs Kopien von `setup_db`/`db_session`/`client`
in `tests/auth`, `tests/tenants`, `tests/partners`, `tests/imports`, `tests/journal` und
`tests/review` bleiben bestehen. `tests/conftest.py` ist ab jetzt die kanonische Kopie und
gilt für alles, was keine eigene mitbringt; das Zusammenlegen berührt jede Testdatei im
Projekt und gehört in einen eigenen Schritt.

---

### Stufe 1 — Die Auswahl beim Anmelden reparieren

**Umfang:** klein und in sich geschlossen — `auth/service.py`, `Login.tsx`,
`SelectMandant.tsx`, `PrivateRoute.tsx`.

| # | Änderung | Test, der anschlägt |
|---|---|---|
| M4 | `login()` berechnet `requires_mandant_selection` für **alle** Rollen gleich; der Admin-Sonderfall betrifft nur noch die Reichweite, nicht das Auswahlsignal | Admin mit zwei Mandanten bekommt `true` und kein Token mit `mandant_id` |
| M5 | Entscheidung E3 umsetzen: eine Definition von „Mandanten dieses Nutzers", für API und Oberfläche dieselbe | Admin ohne Zuordnung — Verhalten festgenagelt statt zufällig |
| M6 | Nutzer ohne Mandant bekommt eine benannte Antwort statt einer Umleitungsschleife: eigene Seite oder Meldung „Kein Mandant zugeordnet — bitte an die Verwaltung wenden" | Anmelden mit `nutzer_ohne` endet auf einer Seite mit dieser Meldung, nicht auf `/login` |
| M9 | `select_mandant` prüft `Mandant.is_active` | ID eines deaktivierten Mandanten ergibt 403, nicht ein gültiges Token |
| M2 | Die doppelte Auto-Auswahl aus `Login.tsx` und `SelectMandant.tsx` auf **eine** Stelle ziehen | die drei vorhandenen `SelectMandant`-Tests bleiben grün |

**Zusätzlich zu prüfen und zu entscheiden:** ein **Mandantenwechsel im laufenden Betrieb**.
Heute steht der gewählte Mandant nur als Text im Kopfbereich (`AppLayout.tsx:186`);
wechseln kann man nur durch Abmelden. Für `nutzer_beide` ist das die naheliegende
Erwartung. `/auth/select-mandant` liefert schon alles Nötige — es fehlt nur die
Schaltfläche. Gehört sachlich hierher, ist aber eine eigene Entscheidung (→ E4).

**Fertig, wenn:** die fünf Zeilen oben getestet sind, `vitest` und `pytest` grün, und
ein Anmeldeversuch von Hand mit `nutzer_beide`, `nutzer_ohne` und `admin` je das
dokumentierte Ergebnis zeigt.

#### Umgesetzt am 2026-09-10

| Befund | Was sich geändert hat |
|---|---|
| **M4** | `login()` hat jetzt **einen** Weg für alle Rollen. Vorher kehrte es für `admin` früh zurück und meldete `requires_mandant_selection: False`, unabhängig von der Anzahl der Mandanten. Nebenbei fielen drei fast gleiche Rückgabepfade auf einen zusammen. |
| **M5/E3** | `_get_mandants_for_user` gibt Admins **alle aktiven** Mandanten. Damit stimmen ihre Reichweite im API und in der Oberfläche überein — und ein Mandant ohne Zuordnung ist nicht mehr unerreichbar. |
| **M6** | Die Auswahlseite erklärt den Zustand „kein Mandant zugeordnet" mit Abmelde-Schaltfläche, statt nach `/login` zurückzuleiten. Die Umleitungsschleife ist weg. |
| **M9** | `select_mandant` prüft `Mandant.is_active` — **vor** der Rollenprüfung, damit auch Admins keinen abgeschalteten Mandanten wählen können. Antwort ist 403 wie bei fehlender Berechtigung: dass ein Mandant existiert, aber abgeschaltet ist, muss ein Außenstehender nicht erfahren. |
| **M2** | Die doppelte Auto-Auswahl ist **ersatzlos entfallen**, nicht zusammengelegt: Der Server legt den einzelnen Mandanten schon beim Anmelden ins Token, damit hat der Client nichts mehr zu entscheiden. |
| **E4** | Neuer `MandantSwitcher` im Kopfbereich. Bei einem Mandanten nur Anzeige, bei mehreren ein Menü. |
| — | Die Mandantenwahl schreibt jetzt `auth.select_mandant` ins Protokoll. `auth.login` und `auth.logout` taten das längst, die weiter reichende Entscheidung nicht. |

Neu: `backend/tests/auth/test_mandantenauswahl.py` (13 Fälle),
`frontend/src/components/MandantSwitcher.test.tsx` (5 Fälle).

**Wozu der Cache beim Wechsel verworfen wird:** Die meisten Abfragen tragen die
`mandant_id` im Schlüssel und laden von selbst neu — „die meisten" genügt hier aber
nicht. Eine einzige Abfrage ohne `mandant_id` im Schlüssel würde nach dem Wechsel
weiter die Zahlen des vorherigen Mandanten anzeigen, und niemand würde es merken.
Deshalb `queryClient.clear()` statt selektiver Entwertung; ein eigener Test hält das
fest.

---

### Stufe 2 — Mandantenzuordnung in der Nutzerverwaltung

**Das ist die eigentliche Aufgabenstellung.** Sie steht bewusst nach Stufe 1: Wer
Zuordnungen anlegen kann, muss deren Wirkung beim Anmelden auch sehen können.

**Backend — die Lesbarkeit fehlt, nicht das Schreiben.** Zuordnen und Entfernen gibt es
schon. Was fehlt:

* `UserDetailResponse` bekommt ein Feld `mandants: list[MandantInfo]` — dann zeigt
  `GET /users` die Zuordnung mit an, ohne einen Aufruf pro Zeile. Achtung: eine Abfrage
  für alle Nutzer, nicht N+1 wie beim `invitation_status` heute.
* Ein Endpunkt, der die zuordenbaren Mandanten liefert, mit der Rollenschwelle aus
  Entscheidung E2 — nicht das admin-eigene `GET /mandants` aufweiten.
* Zuordnung beim Anlegen: `CreateUserRequest` nimmt optional `mandant_ids`, damit ein
  neuer Nutzer nicht durch M6 muss. Der Einladungsversand bleibt davon unberührt
  (ADR-004: SMTP-Fehler rollt die Anlage nicht zurück) — die Zuordnung muss **vor** dem
  Versand stehen, sonst kann sie an einem Mailfehler scheitern.
* Audit: Zuordnen und Entfernen schreiben heute **keinen** `AuditLog`-Eintrag, obwohl
  `auth.login` und `auth.logout` es tun. Eine Zuordnung ist eine Zugriffsentscheidung
  und gehört ins Protokoll.

**Frontend:**

* `UserDialog.tsx` bekommt eine Mandanten-Mehrfachauswahl, im Anlegen- **und** im
  Bearbeiten-Zweig. Die beiden Zweige sind heute fast identisch dupliziert — beim
  Erweitern zusammenführen, sonst driften sie (Frage 1 des Merge-Checks).
* `UsersPage.tsx` zeigt die Mandanten je Nutzer als Spalte.
* `assignUserToMandant` wird endlich aufgerufen; das fehlende
  `unassignUserFromMandant` kommt dazu.
* Ein Nutzer ohne Mandant wird in der Liste sichtbar markiert — er ist der Fall aus M6.

**Tests:** Zuordnen, Entfernen, doppelt zuordnen (409), Zuordnung eines Fremdmandanten
durch einen Mandant-Admin (403, nach E2), Anlegen mit zwei Mandanten, und der
durchgehende Weg: zuordnen → anmelden → Auswahl erscheint.

**Fertig, wenn:** ein Nutzer über die Oberfläche zwei Mandanten bekommt, sich anmeldet,
die Auswahl sieht, wechselt — und der Weg als Test hinterlegt ist.

#### Umgesetzt am 2026-09-10 · Entscheidung E2: Mandant-Admin für eigene Mandanten

**Backend**

* `UserDetailResponse` trägt `mandants` — in **einer** Abfrage für alle Nutzer
  (`mandants_by_user`), nicht einer pro Zeile.
* `GET /users/assignable-mandants` liefert die zuordenbaren Mandanten mit der Schwelle
  `mandant_admin`. Eigener Endpunkt statt Aufweitung von `GET /mandants`, das zur
  Mandantenverwaltung gehört und `admin` verlangt.
* `POST/DELETE /mandants/{id}/users` jetzt ab `mandant_admin`. Die Rollenschwelle lässt
  nur an den Endpunkt; *welche* Mandanten erlaubt sind, entscheidet der Service.
* `POST /users` nimmt `mandant_ids` — und ordnet **vor** dem Einladungsversand zu.
  Nach ADR-004 rollt ein SMTP-Fehler die Anlage nicht zurück; stünde die Zuordnung
  dahinter, würde sie an einem Mailfehler scheitern und der Nutzer landete im Zustand
  aus M6.
* `PATCH /users/{id}` nimmt `mandant_ids` als **Sollstand** — ein Aufruf, ein Endstand,
  statt eines Aufrufs je Zuordnung mit der Möglichkeit halber Änderungen.
* Zuordnen und Entfernen schreiben `auth.mandant_assigned` / `auth.mandant_unassigned`.

**Zwei Regeln, die den Zuschnitt von E2 ausmachen**

1. **Der Abgleich wirkt nur innerhalb der erlaubten Mandanten.** Ohne diese
   Einschränkung könnte ein Mandant-Admin von A einem Nutzer die Zuordnung zu B
   wegnehmen, indem er beim Speichern nur `[A]` sendet. Ein Abgleich sieht harmlos aus
   und wirkte trotzdem auf Daten, die den Handelnden nichts angehen. Mandanten
   *außerhalb* bleiben unberührt; ein unerlaubter Mandant *im* Sollstand ergibt 403
   und wird nicht stillschweigend übergangen — sonst meldet die Oberfläche Erfolg für
   etwas, das nicht passiert ist.
2. **Ein Mandant-Admin darf nur Nutzer zuordnen, die er ohnehin sieht** — oder solche
   **ohne jede Zuordnung**. Die zweite Hälfte ist der eigentliche Arbeitsablauf
   (anlegen, dann zuordnen); die erste verhindert, dass er einen fremden Nutzer in
   seinen Mandanten zieht und dadurch dessen E-Mail-Adresse erfährt.

Dazu eine Sperre gegen **Selbstaussperrung**: Die eigene letzte Zuordnung lässt sich
nicht entfernen — ein Nicht-Admin käme sonst an keine Daten mehr und könnte sich
selbst nicht wieder eintragen. Geprüft wird der **Endstand**, nicht die einzelne
Zeile: Eine Prüfung pro entfernter Zuordnung wäre beim Leeren aller drei Zuordnungen
durchgelaufen, weil jede einzelne noch drei vorhandene sah. Der Linter fand diesen
Fehler an einem ungenutzten Parameter.

**Frontend**

* `UserDialog` hat eine Mandanten-Mehrfachauswahl — und **ein** Formular für Anlegen
  und Bearbeiten statt zweier fast identischer Zweige.
* `UsersPage` zeigt die Mandanten je Nutzer; „Kein Mandant" ist als Warnung
  hervorgehoben, nicht als leere Zelle.
* Der Dialog nennt Zuordnungen, die in der Auswahl fehlen, weil der Handelnde sie
  nicht ändern darf — sonst wirkt die Liste wie der vollständige Stand.
* Route und Menüeintrag `/admin/users` ab `mandant_admin`; `/admin/mandants` bleibt
  `admin`.
* `assignUserToMandant` wird endlich aufgerufen, `unassignUserFromMandant` kam dazu.

Neu: `backend/tests/auth/test_mandantenzuordnung.py` (19 Fälle),
`frontend/src/pages/admin/UserDialog.test.tsx` (7 Fälle).

#### Was beim Umsetzen von Stufe 1+2 nebenbei auffiel

**Ein Test-Helfer rief `/auth/select-mandant` ohne Token auf.** Vier Kopien von
`get_auth_token` in den Testmodulen, zwei davon (`tests/tenants`, `tests/partners`)
ohne `Authorization`-Header. Unbemerkt blieb das, weil dieser Zweig nur bei mehreren
Mandanten läuft und Admins vor der Behebung von M4 nie zur Auswahl kamen. Beide
korrigiert und um eine Statusprüfung ergänzt, damit ein künftiger Fehlschlag nicht
wieder als `KeyError` erscheint.

**Ein Test prüfte weniger, als er behauptete.** `shows active/inactive badges` suchte
den Text „Aktiv" — eindeutig nur, weil das Mock `invitation_status` nicht setzte. Mit
realistischem Mock kommt „Aktiv" zweimal vor. Jetzt gezielt über die Schaltfläche.

**Zwei Tests nagelten einen Widerspruch fest**, den der Server nicht mehr erzeugen
kann: `requires_mandant_selection: true` bei nur einem Mandanten. Beide auf den neuen
Vertrag umgestellt und um den M6-Fall ergänzt.

#### Dokumentation

Auf Wunsch vollständig: Jede Funktion, Klasse und jedes Modul in `app/auth/service.py`,
`app/auth/router.py`, `app/auth/schemas.py` und allen neuen Dateien hat einen
Docstring — maschinell geprüft, verschachtelte Helfer eingeschlossen. Die Kommentare
verweisen auf die Befundnummern dieses Dokuments, damit die Begründung auffindbar
bleibt und nicht nur die Regel.

---

### Stufe 3 — Abdeckung der vier Module anheben

**Warum vor Stufe 5:** wörtlich die Empfehlung aus dem Review. Bei 30–42 % Abdeckung
würde ein struktureller Umbau weder zeigen, was er repariert, noch was er zerstört.

Ziel sind nicht Prozentpunkte, sondern die Pfade, auf denen ein Mandant verlorengehen
kann. Vorgehen: aus dem `check_tenancy.py`-Bericht die Zeilen der vier Module nehmen und
für jede transitiv gebundene Query einen Test mit **zwei** Mandanten schreiben —
Fremd-`partner_id`, Fremd-`account_id`, Fremd-`service_id`, Fremd-`journal_line_id` bei
eigener `mandant_id` im Pfad. Genau das Muster, das die zwei kritischen Lecks aus Etappe 1
gefunden hat.

Reihenfolge nach OFFEN-Dichte: `partners` (12), `services` (9), `review` (6),
`journal` (5), dann `tenants` und `auth`.

Die Abdeckungs-Ratschen in `pyproject.toml` und `vitest.config.ts` werden mitgezogen —
sie dürfen laut CI-Kommentar nur steigen.

**Fertig, wenn:** die vier Module deutlich über ihrem heutigen Stand liegen und jede
PRUEFEN-Zeile in ihnen entweder einen Test hat oder im Bericht als geprüft vermerkt ist.

---

### Stufe 4 — Isolationstest über alle 76 Endpunkte

**Warum:** `check_tenancy.py` ist eine statische Prüfung. Sie sieht, ob eine `mandant_id`
im Statement vorkommt, nicht ob sie die richtige ist. Der Gegentest muss laufen.

Ein parametrisierter Test, der die Endpunktliste **aus dem Router erzeugt** statt sie
abzuschreiben — sonst fehlt der 77. Endpunkt still. `check_tenancy.py` hat die AST-Logik
dafür schon, sie lässt sich als Helfer herausziehen.

Für jeden Endpunkt mit Mandantenbezug, mit dem Token von `nutzer_a`:

1. `mandant_id` von B im Pfad → **403** (prüft `require_mandant_access`)
2. eigene `mandant_id`, Objekt-ID aus B → **403 oder 404, nie 200** (prüft die innere
   Schicht — das ist der Fall, der die Lecks aus Etappe 1 hatte)
3. mit `nutzer_beide`, Token für A, Pfad B → das dokumentierte Ergebnis aus M10

Antwort 2 braucht je Endpunkt ein passendes Fremdobjekt; das liefert die Fixture aus
Stufe 0. Wo ein Endpunkt sich nicht generisch bedienen lässt, kommt er auf eine
**ausdrückliche Ausnahmeliste mit Begründung** — nicht stillschweigend aus dem Test.
Diese Liste ist eine Ratsche wie `--max-offen`: sie darf nur kürzer werden.

**Fertig, wenn:** der Test alle 76 Endpunkte erreicht, die Ausnahmeliste begründet ist
und der Lauf in CI steht.

---

### Stufe 5 — Struktur statt Disziplin

Erst jetzt, mit Netz. Hier werden die im Review vertagten Teilaspekte entschieden.

| Punkt | Frage | Wirkung |
|---|---|---|
| A1-4 · M11 | Join-Helfer `_lines_of_mandant(mandant_id)` einführen? Betrifft vier Funktionen | macht die Regel erzwingbar statt merkbar; senkt OFFEN |
| A1-3 · M13 | ADR-008 umkehren (Eindeutigkeit je Mandant) oder den Importweg 409/Review-Item werfen lassen? | heute schluckt der Import eine fremde IBAN still |
| Konto-IBAN · M13 | `create_account` prüft global (409 „IBAN already in use") ohne ADR-Grundlage | zwei Firmen mit gemeinsamem Konto können es nicht beide erfassen |
| A2-3 · M14 | `base_currency` aus dem Konto lesen statt aus dem Literal | ein Mandant mit CHF-Konto bekäme heute eine leere Matrix |
| M10 | Soll das Token den Mandanten erzwingen oder nur anzeigen? | ADR-Entscheidung, kein Code — betrifft alle 76 Endpunkte |

Die naheliegende Frage „warum nicht Row-Level-Security?" gehört hierher und nicht früher:
Sie ist erst beantwortbar, wenn Stufe 4 zeigt, was die heutige Trennung tatsächlich
leistet. Bei SQLite als Entwicklungsdatenbank ist RLS ohnehin keine Option — das wäre
eine Entscheidung über die Datenbank, nicht über die Mandantenfähigkeit.

---

## Entscheidungen, die der Plan braucht

**Stand 2026-09-10: alle vier sind beantwortet** — E1 durch die Datenlage, E2 durch
Raimund, E3 und E4 beim Umsetzen von Stufe 1. Die Begründungen bleiben hier stehen,
weil sie erklären, warum der Code aussieht, wie er aussieht.

| # | Frage | Wirkt auf |
|---|---|---|
| **E1** | ~~Läuft das System je produktiv mit mehr als einem Mandanten?~~ **Durch die Datenlage beantwortet: ja, seit 2026-09-10.** Offen bleibt nur noch, ob Stufen 3–5 sofort oder nach Stufe 2 laufen | die Dringlichkeit von allem hier. Da beide Mandanten echte Daten tragen, sind Stufen 3–5 keine Vorsorge mehr. Die Reihenfolge „Trennung vorher" ist verpasst; was schon vermischt wurde, lässt sich nicht nachträglich feststellen |
| **E2** | ~~Wer darf Mandanten zuordnen?~~ **Entschieden 2026-09-10: auch Mandant-Admin, für die eigenen Mandanten.** | umgesetzt in Stufe 2 — Schwelle `mandant_admin` an den Endpunkten, eigener Endpunkt für die Auswahlliste, Abgleich nur im erlaubten Bereich |
| **E3** | ~~Sieht ein Admin alle Mandanten oder nur die verknüpften?~~ **Entschieden 2026-09-10: alle aktiven.** | umgesetzt in Stufe 1. Die Gegenoption hätte den Zustand erhalten, der „Calista" unerreichbar machte |
| **E4** | ~~Mandantenwechsel im laufenden Betrieb?~~ **Entschieden 2026-09-10: ja, Umschalter im Kopfbereich.** | umgesetzt in Stufe 1 als `MandantSwitcher` |

---

## Was beim Merge geprüft wird

Nach der Absprache vom 2026-09-09 gilt für jede Stufe der Merge-Check aus
`code-review-konzept.md`, Abschnitt 10. Drei der sechs Fragen treffen diesen Umbau
besonders:

* **Frage 1 (Zwilling)** — der Plan berührt drei bekannte Zwillinge: die doppelte
  Auto-Auswahl (M2), die zwei Definitionen von „Mandanten dieses Nutzers" (M5) und die
  duplizierten Zweige in `UserDialog.tsx`.
* **Frage 2 (Mandantentrennung)** — `check_tenancy.py --strict --max-offen 43` muss grün
  bleiben; beim Beheben ist die Zahl **mitzusenken**, sonst schweigt die Ratsche, wenn
  gleichzeitig einer dazukommt.
* **Frage 5 (prüft die Prüfung?)** — gilt für Stufe 4 doppelt: Ein Isolationstest, der
  seine Endpunktliste abschreibt statt sie zu erzeugen, prüft ab dem 77. Endpunkt nichts
  mehr.

Befunde wandern nach `code-review-befunde.md`, der Sammelpunkt dort verweist auf dieses
Dokument.
