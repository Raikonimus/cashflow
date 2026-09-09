"""Tests für die Mustererkennung — die Beispiele aus dem Konzept, an echten Fällen orientiert."""

from datetime import date
from decimal import Decimal

from app.forecast.profiler import (
    Cadence,
    Confidence,
    RuleType,
    build_profile,
    month_index,
)

WINDOW_END = month_index(2026, 8)  # letzter vollständiger Monat


def series(start: tuple[int, int], amounts: list[str | None]) -> dict[int, Decimal]:
    """Monatsreihe ab `start`; `None` steht für einen Monat ohne Buchung."""
    start_index = month_index(*start)
    return {
        start_index + offset: Decimal(amount)
        for offset, amount in enumerate(amounts)
        if amount is not None
    }


class TestGehalt:
    """Monatlich gleich, im Juni und November doppelt (14. Gehalt)."""

    def _salary(self) -> dict[int, Decimal]:
        points: dict[int, Decimal] = {}
        for year in (2024, 2025, 2026):
            for month in range(1, 13):
                if year == 2026 and month > 8:
                    continue
                doubled = month in (6, 11)
                points[month_index(year, month)] = (
                    Decimal("-6000") if doubled else Decimal("-3000")
                )
        return points

    def test_erkennt_monatlichen_fixbetrag(self):
        profile = build_profile(self._salary(), window_end=WINDOW_END)

        assert profile.cadence is Cadence.monthly
        assert profile.rule.rule_type is RuleType.fixed_recurring
        assert profile.rule.amount == Decimal("-3000")
        assert profile.rule.confidence is Confidence.high

    def test_erkennt_sondermonate_ohne_oesterreich_sonderlogik(self):
        profile = build_profile(self._salary(), window_end=WINDOW_END)

        assert sorted(profile.rule.special_months) == [6, 11]
        assert profile.rule.special_months[6] == Decimal("2")

    def test_projiziert_sondermonat_doppelt(self):
        rule = build_profile(self._salary(), window_end=WINDOW_END).rule

        assert rule.value_for(month_index(2026, 10)) == Decimal("-3000")
        assert rule.value_for(month_index(2026, 11)) == Decimal("-6000")
        assert rule.value_for(month_index(2027, 6)) == Decimal("-6000")

    def test_einzelner_ausreisser_wird_kein_sondermonat(self):
        points = self._salary()
        points[month_index(2025, 3)] = Decimal("-9000")  # einmalige Nachzahlung

        profile = build_profile(points, window_end=WINDOW_END)

        assert 3 not in profile.rule.special_months


class TestLizenz:
    def test_monatlich_konstant_ergibt_hohe_confidence(self):
        points = series((2025, 9), ["-49.90"] * 12)

        profile = build_profile(points, window_end=WINDOW_END)

        assert profile.rule.rule_type is RuleType.fixed_recurring
        assert profile.rule.amount == Decimal("-49.90")
        assert profile.rule.confidence is Confidence.high
        assert profile.rule.value_for(month_index(2027, 3)) == Decimal("-49.90")


class TestJaehrlicheZahlung:
    def test_erkennt_jahresrhythmus_und_zielmonat(self):
        points = {
            month_index(2024, 3): Decimal("-1200"),
            month_index(2025, 3): Decimal("-1200"),
            month_index(2026, 3): Decimal("-1200"),
        }

        profile = build_profile(points, window_end=WINDOW_END)

        assert profile.cadence is Cadence.annual
        assert profile.rule.rule_type is RuleType.fixed_recurring
        assert profile.rule.interval_months == 12

    def test_projiziert_nur_in_den_zielmonat(self):
        points = {
            month_index(2024, 3): Decimal("-1200"),
            month_index(2025, 3): Decimal("-1200"),
            month_index(2026, 3): Decimal("-1200"),
        }

        rule = build_profile(points, window_end=WINDOW_END).rule

        assert rule.value_for(month_index(2027, 3)) == Decimal("-1200")
        assert rule.value_for(month_index(2027, 4)) == Decimal("0")
        assert rule.value_for(month_index(2026, 12)) == Decimal("0")

    def test_eine_einzige_zahlung_ergibt_keine_prognose(self):
        points = {month_index(2026, 3): Decimal("-1200")}

        profile = build_profile(points, window_end=WINDOW_END)

        assert profile.rule.rule_type is RuleType.none


class TestQuartalszahlung:
    def test_erkennt_dreimonatsrhythmus(self):
        points = {
            month_index(2025, 2): Decimal("-500"),
            month_index(2025, 5): Decimal("-500"),
            month_index(2025, 8): Decimal("-500"),
            month_index(2025, 11): Decimal("-500"),
            month_index(2026, 2): Decimal("-500"),
            month_index(2026, 5): Decimal("-500"),
            month_index(2026, 8): Decimal("-500"),
        }

        rule = build_profile(points, window_end=WINDOW_END).rule

        assert rule.rule_type is RuleType.fixed_recurring
        assert rule.interval_months == 3
        assert rule.value_for(month_index(2026, 11)) == Decimal("-500")
        assert rule.value_for(month_index(2026, 12)) == Decimal("0")


class TestSchwankendeFixkosten:
    def test_monatlich_aber_schwankend_ergibt_gleitenden_durchschnitt(self):
        points = series((2025, 9), ["-100", "-900"] * 6)

        profile = build_profile(points, window_end=WINDOW_END)

        assert profile.cadence is Cadence.monthly
        assert profile.rule.rule_type is RuleType.rolling_average
        assert profile.rule.confidence is Confidence.medium
        # Mittel der letzten sechs Monate: dreimal -100, dreimal -900.
        assert profile.rule.value_for(month_index(2026, 12)) == Decimal("-500")


class TestProjekteinnahmen:
    def test_unregelmaessig_ergibt_jahresdurchschnitt_mit_niedriger_confidence(self):
        points = {
            month_index(2024, 11): Decimal("20000"),
            month_index(2024, 12): Decimal("5000"),
            month_index(2025, 4): Decimal("12000"),
            month_index(2025, 5): Decimal("3000"),
            month_index(2026, 1): Decimal("18000"),
            month_index(2026, 7): Decimal("6000"),
        }

        profile = build_profile(points, window_end=WINDOW_END)

        assert profile.cadence is Cadence.irregular
        assert profile.rule.rule_type is RuleType.rolling_average
        assert profile.rule.confidence is Confidence.low
        # Letzte zwölf Monate (09/2025–08/2026): 18000 + 6000, verteilt auf zwölf Monate.
        assert profile.rule.value_for(month_index(2027, 2)) == Decimal("2000")

    def test_zwei_zahlungen_im_quartalsabstand_sind_noch_kein_muster(self):
        points = {
            month_index(2026, 5): Decimal("8000"),
            month_index(2026, 8): Decimal("4000"),
        }

        profile = build_profile(points, window_end=WINDOW_END)

        assert profile.rule.rule_type is RuleType.none
        assert "mindestens 3" in profile.rule.reason

    def test_zu_kurze_historie_ergibt_keine_prognose(self):
        points = {
            month_index(2026, 3): Decimal("8000"),
            month_index(2026, 4): Decimal("1000"),
            month_index(2026, 8): Decimal("4000"),
        }

        profile = build_profile(points, window_end=WINDOW_END)

        assert profile.rule.rule_type is RuleType.none
        assert "Historie" in profile.rule.reason


class TestKeineProgose:
    def test_ohne_buchungen(self):
        profile = build_profile({}, window_end=WINDOW_END)

        assert profile.rule.rule_type is RuleType.none
        assert profile.occurrence_count == 0

    def test_zu_wenige_monatliche_buchungen(self):
        points = series((2026, 7), ["-200", "-200"])

        profile = build_profile(points, window_end=WINDOW_END)

        assert profile.rule.rule_type is RuleType.none
        assert "mindestens 3" in profile.rule.reason

    def test_beendete_leistung_wird_nicht_fortgeschrieben(self):
        points = series((2025, 1), ["-800"] * 12)  # letzte Buchung 12/2025

        profile = build_profile(points, window_end=WINDOW_END)

        assert profile.rule.rule_type is RuleType.none
        assert "beendet" in profile.rule.reason

    def test_einzelner_ausfall_beendet_eine_leistung_nicht(self):
        points = series((2025, 9), ["-800"] * 11 + [None])  # 08/2026 fehlt

        profile = build_profile(points, window_end=WINDOW_END)

        assert profile.rule.rule_type is RuleType.fixed_recurring

    def test_valid_to_in_der_vergangenheit(self):
        points = series((2025, 9), ["-800"] * 12)

        profile = build_profile(
            points, window_end=WINDOW_END, valid_to=date(2026, 6, 30)
        )

        assert profile.rule.rule_type is RuleType.none
        assert "endete" in profile.rule.reason

    def test_valid_to_in_der_zukunft_beendet_die_prognose_zum_stichtag(self):
        points = series((2025, 1), ["-800"] * 12) | series((2026, 1), ["-800"] * 8)

        rule = build_profile(
            points, window_end=WINDOW_END, valid_to=date(2026, 10, 31)
        ).rule

        assert rule.rule_type is RuleType.fixed_recurring
        assert rule.value_for(month_index(2026, 10)) == Decimal("-800")
        assert rule.value_for(month_index(2026, 11)) == Decimal("0")
        assert rule.value_for(month_index(2027, 6)) == Decimal("0")

    def test_valid_from_in_der_zukunft_verzoegert_die_prognose(self):
        points = series((2025, 1), ["-800"] * 12) | series((2026, 1), ["-800"] * 8)

        rule = build_profile(
            points, window_end=WINDOW_END, valid_from=date(2026, 12, 1)
        ).rule

        assert rule.value_for(month_index(2026, 11)) == Decimal("0")
        assert rule.value_for(month_index(2026, 12)) == Decimal("-800")

    def test_buchungen_ausserhalb_des_fensters_zaehlen_nicht(self):
        points = series((2015, 1), ["-800"] * 12)

        profile = build_profile(points, window_end=WINDOW_END)

        assert profile.occurrence_count == 0
        assert profile.rule.rule_type is RuleType.none
