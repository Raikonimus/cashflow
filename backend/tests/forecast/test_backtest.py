"""Tests für den Rückvergleich — misst er das Richtige und wählt er das Richtige aus?"""
from decimal import Decimal

from app.forecast.backtest import (
    ERROR_CORRELATION,
    HOLDOUT_MAX_MONTHS,
    HOLDOUT_MIN_MONTHS,
    SPREAD_MAX,
    SPREAD_MIN,
    applied_profile,
    combined_uncertainty,
    run_backtest,
)
from app.forecast.profiler import (
    Confidence,
    RuleType,
    build_profile,
    month_index,
)

WINDOW_END = month_index(2026, 8)


def series(start: tuple[int, int], amounts: list[str | None]) -> dict[int, Decimal]:
    start_index = month_index(*start)
    return {
        start_index + offset: Decimal(amount)
        for offset, amount in enumerate(amounts)
        if amount is not None
    }


def constant(start: tuple[int, int], months: int, amount: str) -> dict[int, Decimal]:
    return series(start, [amount] * months)


def report_for(points: dict[int, Decimal], window_end: int = WINDOW_END):
    profile = build_profile(points, window_end=window_end)
    return profile, run_backtest(points, window_end=window_end, profile=profile)


class TestVoraussetzungen:
    def test_ohne_erkanntes_muster_laeuft_kein_rueckvergleich(self):
        # Zwei Buchungen — der Profiler lehnt ab, und diese Sperre bleibt bestehen.
        _, report = report_for(series((2026, 7), ["-500", "-500"]))

        assert report.ran is False
        assert "Kein Muster" in report.reason
        assert report.fitted_rule is None

    def test_kurze_historie_reicht_nicht(self):
        # 14 Monate: nach 6 Prüfmonaten bleiben nur 8 zum Lernen, nötig sind 12.
        _, report = report_for(constant((2025, 7), 14, "-1000"))

        assert report.ran is False
        assert "Historie reicht nicht" in report.reason

    def test_ausreichende_historie_laeuft(self):
        _, report = report_for(constant((2024, 1), 32, "-1000"))

        assert report.ran is True
        assert report.holdout_months == HOLDOUT_MIN_MONTHS
        assert report.train_end_index == WINDOW_END - HOLDOUT_MIN_MONTHS

    def test_jahreszahlung_bekommt_zwoelf_pruefmonate(self):
        points = {
            month_index(year, 3): Decimal("-2400") for year in (2023, 2024, 2025, 2026)
        }
        _, report = report_for(points)

        assert report.ran is True
        assert report.holdout_months == HOLDOUT_MAX_MONTHS


class TestMessung:
    def test_perfekte_regel_hat_fehler_null(self):
        _, report = report_for(constant((2024, 1), 32, "-1000"))

        winner = report.winner
        assert winner is not None
        assert winner.mae == Decimal("0")
        assert winner.level_error == Decimal("0")
        assert report.relative_error == Decimal("0")

    def test_niveaufehler_traegt_vorzeichen(self):
        # Bis 02/2026 monatlich -1000, danach -2000: die Regel prognostiziert zu wenig
        # Ausgabe, die Summe fällt zu hoch aus.
        points = {**constant((2024, 1), 26, "-1000"), **constant((2026, 3), 6, "-2000")}
        _, report = report_for(points)

        winner = report.winner
        assert winner is not None
        assert winner.level_error > 0

    def test_nullprognose_laeuft_als_vergleich_mit(self):
        _, report = report_for(constant((2024, 1), 32, "-1000"))

        assert report.baseline is not None
        assert report.baseline.key == "none"
        assert report.baseline.mae == Decimal("1000")
        assert report.beats_baseline is True

    def test_nullprognose_gewinnt_nie(self):
        """Bei seltenen Zahlungen hat die Null oft den kleinsten Fehler — sie darf
        trotzdem nicht gewinnen, sonst verschwindet echtes Geld aus der Planung."""
        # Quartalszahlungen bis 01/2026, im Prüfzeitraum 03–08/2026 kommt fast nichts.
        points = {
            month_index(year, month): Decimal("1500")
            for year in (2024, 2025)
            for month in (1, 4, 7, 10)
        }
        points[month_index(2026, 1)] = Decimal("1500")
        points[month_index(2026, 8)] = Decimal("200")

        _, report = report_for(points)

        assert report.ran is True
        assert report.baseline is not None
        assert report.winner is not None
        # Die Nullprognose ist hier messbar die beste — und wird trotzdem nicht gewählt.
        assert report.baseline.score < report.winner.score
        assert report.winner.is_baseline is False
        assert report.beats_baseline is False  # ehrlich ausgewiesen, aber nicht gewählt


class TestBeendeteLeistung:
    def test_leerer_pruefzeitraum_beendet_die_prognose(self):
        """Der Prüfzeitraum enthält zwei erwartete Zahlungen. Ist er leer, zahlt hier
        nichts mehr — gemessen, nicht nach Schwellwert vermutet."""
        # Quartalsweise bis 02/2026, danach nichts. Der Profiler alleine hält die
        # Leistung noch für lebendig.
        points = {
            month_index(year, month): Decimal("-1500")
            for year in (2024, 2025)
            for month in (2, 5, 8, 11)
        }
        points[month_index(2026, 2)] = Decimal("-1500")

        profile = build_profile(points, window_end=WINDOW_END)
        assert profile.rule.rule_type is RuleType.fixed_recurring  # projiziert weiter

        report = run_backtest(points, window_end=WINDOW_END, profile=profile)

        assert report.ran is True
        assert report.service_stopped is True
        assert report.fitted_rule is not None
        assert report.fitted_rule.rule_type is RuleType.none
        applied = applied_profile(profile, report).rule
        assert applied.value_for(month_index(2027, 5)) == Decimal("0")

    def test_eine_buchung_im_pruefzeitraum_reicht_zum_weiterlaufen(self):
        points = {
            month_index(year, month): Decimal("-1500")
            for year in (2024, 2025)
            for month in (2, 5, 8, 11)
        }
        points[month_index(2026, 2)] = Decimal("-1500")
        points[month_index(2026, 5)] = Decimal("-1500")

        _, report = report_for(points)

        assert report.service_stopped is False
        assert report.fitted_rule is not None
        assert report.fitted_rule.rule_type is RuleType.fixed_recurring


class TestRegelwahl:
    def test_stabiles_muster_bleibt_beim_profilervorschlag(self):
        profile, report = report_for(constant((2024, 1), 32, "-1000"))

        assert report.replaced_detected is False
        assert report.winner is not None
        assert report.winner.key == "detected"
        assert applied_profile(profile, report).rule.amount == Decimal("-1000")

    def test_niveauwechsel_waehlt_kurzes_mittel(self):
        """Seit einem halben Jahr das Doppelte: Der Median über drei Jahre hinkt
        hinterher, das kurze Fenster trifft."""
        points = {
            **constant((2023, 9), 24, "-1000"),
            **constant((2025, 9), 12, "-3000"),
        }
        profile, report = report_for(points)

        assert report.ran is True
        assert report.replaced_detected is True
        assert report.winner is not None
        assert report.winner.key.startswith("rolling_average")
        # Neu angepasst auf der vollen Historie, nicht auf den Trainingsdaten.
        assert applied_profile(profile, report).rule.amount == Decimal("-3000")

    def test_knapper_vorsprung_verdraengt_den_profiler_nicht(self):
        """Ein Vorsprung unterhalb der Marge ist Rauschen bei sechs Prüfmonaten."""
        # Training konstant -1000 bis auf den letzten Monat; Prüfzeitraum -1100.
        # Das kurze Fenster liegt dadurch minimal näher dran als der Median.
        points = {**constant((2024, 1), 26, "-1000"), **constant((2026, 3), 6, "-1100")}
        points[month_index(2026, 2)] = Decimal("-1015")
        profile, report = report_for(points)

        best = min(report.scores, key=lambda score: score.score)
        assert best.key == "rolling_average:3"
        assert best.score < report.winner.score  # besser — aber nicht deutlich genug
        assert report.replaced_detected is False
        applied = applied_profile(profile, report).rule
        assert applied.rule_type is RuleType.fixed_recurring

    def test_gewinner_wird_auf_voller_historie_neu_angepasst(self):
        points = {
            **constant((2023, 9), 24, "-1000"),
            **constant((2025, 9), 12, "-3000"),
        }
        profile, report = report_for(points)

        fitted = applied_profile(profile, report).rule
        # Das Trainingsfenster endete 02/2026 und kannte -3000 erst seit 09/2025;
        # angepasst auf allen Daten steht dort trotzdem der volle Betrag.
        assert fitted.value_for(month_index(2026, 12)) == Decimal("-3000")


class TestBandbreiteUndConfidence:
    def test_perfekte_treffer_ergeben_die_untere_bandbreite(self):
        _, report = report_for(constant((2024, 1), 32, "-1000"))

        assert report.spread == SPREAD_MIN
        assert report.confidence is Confidence.high

    def test_grosse_abweichung_wird_gedeckelt(self):
        # Zwei Jahre konstant, dann bricht der Betrag um das Zehnfache ein.
        points = {**constant((2024, 1), 26, "-10000"), **constant((2026, 3), 6, "-100")}
        _, report = report_for(points)

        assert report.spread == SPREAD_MAX
        assert report.confidence is Confidence.low

    def test_ohne_ist_volumen_keine_bandbreite(self):
        """Bleibt der Prüfzeitraum leer, ist der relative Fehler nicht definiert."""
        points = constant((2024, 1), 26, "-1000")
        profile = build_profile(points, window_end=WINDOW_END)
        # Der Profiler erklärt die Leistung für beendet — dann läuft nichts.
        assert profile.rule.rule_type is RuleType.none

        report = run_backtest(points, window_end=WINDOW_END, profile=profile)
        assert report.ran is False
        assert report.spread is None
        assert report.confidence is None


class TestSaisonUndVorjahr:
    def test_saisonales_muster_schlaegt_den_flachen_durchschnitt(self):
        """Umsatz nur im Sommer: Ein Jahresmittel verteilt ihn gleichmäßig und liegt
        jeden Monat daneben; Vorjahresmonat oder Saisonprofil treffen."""
        def summer_year(year: int) -> dict[int, Decimal]:
            return {
                month_index(year, month): Decimal("30000")
                for month in (6, 7, 8)
            }

        points = {**summer_year(2024), **summer_year(2025), **summer_year(2026)}
        _, report = report_for(points)

        assert report.ran is True
        assert report.winner is not None
        assert report.winner.key in {"same_period_last_year", "seasonal_profile"}

    def test_vorjahreswert_sieht_den_pruefzeitraum_nicht(self):
        """Kein Leakage: Der Kandidat schlägt nur in den Trainingsdaten nach."""
        points = {
            **{month_index(2024, month): Decimal("1000") for month in range(1, 13)},
            **{month_index(2025, month): Decimal("1000") for month in range(1, 13)},
            **{month_index(2026, month): Decimal("9999") for month in range(1, 9)},
        }
        _, report = report_for(points)

        last_year = next(
            (s for s in report.scores if s.key == "same_period_last_year"), None
        )
        assert last_year is not None
        # Prüfzeitraum 03–08/2026 mit je 9999; das Vorjahr trug 1000 — Fehler 8999.
        assert last_year.mae == Decimal("8999")


class TestBandbreitenAggregation:
    """`combined_uncertainty` fasst Einzelfehler zum Band für den Saldo zusammen."""

    def test_einzelner_fehler_bleibt_er_selbst(self):
        assert combined_uncertainty([Decimal("100")]) == Decimal("100")

    def test_ohne_fehler_kein_band(self):
        assert combined_uncertainty([]) == Decimal("0")

    def test_liegt_zwischen_wurzelsumme_und_summe(self):
        """Die beiden Extreme sind die Modellannahmen, zwischen denen die Wahrheit
        liegt: völlig unabhängige Fehler (Wurzel aus der Quadratsumme) und
        gleichgerichtete (einfache Summe)."""
        parts = [Decimal("100")] * 4
        independent = Decimal("200")  # √(4 × 100²)
        aligned = Decimal("400")

        combined = combined_uncertainty(parts)

        assert independent < combined < aligned

    def test_korrelation_null_ergaebe_die_wurzelsumme(self):
        # Kontrollrechnung zur Formel, unabhängig vom eingestellten Wert.
        parts = [Decimal("30"), Decimal("40")]
        squares = sum(value * value for value in parts)
        total = sum(parts)
        expected = (
            (Decimal("1") - ERROR_CORRELATION) * squares
            + ERROR_CORRELATION * total * total
        ).sqrt()

        assert combined_uncertainty(parts) == expected

    def test_ein_grosser_posten_dominiert(self):
        """Ein großer Fehler darf nicht von vielen kleinen verwässert werden."""
        dominated = combined_uncertainty([Decimal("1000")] + [Decimal("1")] * 20)

        assert dominated > Decimal("1000")
