# Änderungsdokumentation (Stand 15.04.2026)

## Quelle (GitHub/Git)
- Commit: 2a0d042d98570fe5f941da6d1ad41a4e0464e849
- Kurz-Hash: 2a0d042
- Commit-Message: feat: erweitere review, journal und service-matcher workflows
- Autor: Raimund
- Datum: Wed Apr 15 22:14:29 2026 +0200
- Push-Ziel: origin/main

Hinweis: Es ist aktuell keine aktive Pull Request hinterlegt. Diese Dokumentation basiert daher auf dem zuletzt gepushten Commit.

## Zusammenfassung der funktionalen Änderungen

### 1) Review-Queue: bessere Erklärbarkeit bei IBAN-Abweichungen
- Kontext für Name-Match mit IBAN wurde erweitert, damit in der UI sichtbar ist, warum ein Eintrag in der Review-Queue landet.
- Zusätzliche Diagnosefelder und Partner-IBAN-Kontext wurden in Backend und Frontend integriert.

Betroffene Dateien:
- backend/app/imports/matching.py
- backend/app/review/schemas.py
- backend/app/review/service.py
- frontend/src/api/review.ts
- frontend/src/pages/review/ReviewPage.tsx
- backend/tests/review/test_review.py

### 2) Journal: Filter vereinfacht und Jahre dynamisch
- Neuer Endpoint für verfügbare Journal-Jahre.
- Jahresauswahl im Frontend wird dynamisch aus den echten Buchungsdaten befüllt.
- Partner-Filter-Variante im Journal wurde reduziert/vereinfacht.

Betroffene Dateien:
- backend/app/journal/router.py
- backend/app/journal/schemas.py
- backend/app/journal/service.py
- frontend/src/api/journal.ts
- frontend/src/pages/journal/JournalPage.tsx
- backend/tests/journal/test_journal.py

### 3) Services: neues Attribut erfolgsneutral
- Services unterstützen jetzt das boolesche Feld erfolgsneutral.
- Feld ist in Create/Update/API/Review-Adjust enthalten.
- UI für Service-Verwaltung und Review-Anpassung wurde erweitert.
- DB-Migration für services.erfolgsneutral hinzugefügt.

Betroffene Dateien:
- backend/app/services/models.py
- backend/app/services/schemas.py
- backend/app/services/service.py
- backend/app/review/schemas.py
- backend/app/review/service.py
- frontend/src/api/services.ts
- frontend/src/api/review.ts
- frontend/src/pages/partners/ServiceManagementPage.tsx
- frontend/src/pages/review/ReviewPage.tsx
- backend/migrations/versions/020_add_erfolgsneutral_to_services.py
- backend/tests/partners/test_services.py
- backend/tests/review/test_review.py

### 4) Matcher: Option nur Partner-interne Buchungen verschieben
- Service-Matcher unterstützen jetzt internal_only.
- Bei gesetzter Option werden nur Zeilen innerhalb desselben Partners automatisch umgehängt.
- Gilt sowohl für Matcher testen (Preview) als auch Matcher anlegen/aktualisieren.
- UI-Checkbox ergänzt: Nur Partner-interne Buchungen verschieben.
- DB-Migration für service_matchers.internal_only hinzugefügt.

Betroffene Dateien:
- backend/app/services/models.py
- backend/app/services/schemas.py
- backend/app/services/service.py
- frontend/src/api/services.ts
- frontend/src/pages/partners/ServiceManagementPage.tsx
- frontend/src/pages/partners/ServiceManagementPage.test.tsx
- backend/migrations/versions/021_add_internal_only_to_service_matchers.py
- backend/tests/partners/test_services.py

### 5) Partner-Reassign: konfliktbewusste Vorschau und selektiveres Verschieben
- Neue Hilfslogik zur Erkennung von Konfliktkriterien (IBAN/Konto/Name/Matcher) eingeführt.
- Preview-Daten wurden um Konflikt- und Leistungsinformationen erweitert.
- Reassign-Logik für Konten/IBAN wurde auf selektives Verschieben passender Zeilen umgestellt.

Betroffene Dateien:
- backend/app/partners/conflict_utils.py
- backend/app/partners/schemas.py
- backend/app/partners/service.py
- frontend/src/api/partners.ts
- frontend/src/pages/partners/PartnerDetailPage.tsx
- backend/tests/partners/test_partners.py

## Datenbankmigrationen
- 020_add_erfolgsneutral_to_services.py
- 021_add_internal_only_to_service_matchers.py

## Geänderte Dateien (vollständig laut Commit)
- M backend/app/imports/matching.py
- M backend/app/journal/router.py
- M backend/app/journal/schemas.py
- M backend/app/journal/service.py
- A backend/app/partners/conflict_utils.py
- M backend/app/partners/schemas.py
- M backend/app/partners/service.py
- M backend/app/review/schemas.py
- M backend/app/review/service.py
- M backend/app/services/models.py
- M backend/app/services/schemas.py
- M backend/app/services/service.py
- A backend/migrations/versions/020_add_erfolgsneutral_to_services.py
- A backend/migrations/versions/021_add_internal_only_to_service_matchers.py
- M backend/tests/journal/test_journal.py
- M backend/tests/partners/test_partners.py
- M backend/tests/partners/test_services.py
- M backend/tests/review/test_review.py
- M frontend/src/api/journal.ts
- M frontend/src/api/partners.ts
- M frontend/src/api/review.ts
- M frontend/src/api/services.ts
- M frontend/src/pages/journal/JournalPage.tsx
- M frontend/src/pages/partners/PartnerDetailPage.tsx
- M frontend/src/pages/partners/ServiceManagementPage.test.tsx
- M frontend/src/pages/partners/ServiceManagementPage.tsx
- M frontend/src/pages/review/ReviewPage.tsx
