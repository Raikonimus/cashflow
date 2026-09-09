"""Übersteuerung, Modifikatoren und Szenarien — die Schichten über dem Profiler."""
from decimal import Decimal

from app.forecast.models import ForecastMode, ServiceForecastRule
from app.forecast.profiler import (
    Confidence,
    ForecastProfile,
    ForecastRule,
    RuleType,
    month_index,
)
from app.forecast.rules import Scenario, projected_value, resolve_rule

WINDOW_END = month_index(2026, 8)


def profile_with(rule: ForecastRule) -> ForecastProfile:
    return ForecastProfile(
        cadence=None,  # type: ignore[arg-type]
        occurrence_count=12,
        median_amount=rule.amount,
        dispersion=Decimal("0"),
        first_index=WINDOW_END - 11,
        last_index=WINDOW_END,
        special_months={},
        rule=rule,
    )


AUTO_PROFILE = profile_with(
    ForecastRule(
        rule_type=RuleType.fixed_recurring,
        reason="Monatlich, stabiler Betrag",
        confidence=Confidence.high,
        amount=Decimal("-3000"),
    )
)


def override(**kwargs) -> ServiceForecastRule:
    from uuid import uuid4

    defaults = dict(mandant_id=uuid4(), service_id=uuid4(), mode=ForecastMode.auto.value)
    return ServiceForecastRule(**{**defaults, **kwargs})


def value(effective, year: int, month: int, history=None, scenario=Scenario.expected) -> Decimal:
    return projected_value(
        effective, month_index(year, month), history=history or {}, scenario=scenario
    )


class TestModus:
    def test_ohne_uebersteuerung_gilt_der_profilervorschlag(self):
        effective = resolve_rule(AUTO_PROFILE, None, history={}, window_end=WINDOW_END)

        assert effective.mode is ForecastMode.auto
        assert value(effective, 2027, 3) == Decimal("-3000")

    def test_abgeschaltet_liefert_nichts(self):
        effective = resolve_rule(
            AUTO_PROFILE, override(mode="off"), history={}, window_end=WINDOW_END
        )

        assert effective.is_active is False
        assert value(effective, 2027, 3) == Decimal("0")
        assert "abgeschaltet" in effective.reason

    def test_unbekannter_modus_faellt_auf_auto_zurueck(self):
        effective = resolve_rule(
            AUTO_PROFILE, override(mode="quatsch"), history={}, window_end=WINDOW_END
        )

        assert effective.mode is ForecastMode.auto
        assert value(effective, 2027, 3) == Decimal("-3000")

    def test_haendische_regel_schlaegt_den_vorschlag(self):
        effective = resolve_rule(
            AUTO_PROFILE,
            override(mode="manual", rule_type="fixed_recurring", params={"amount": "-4500"}),
            history={},
            window_end=WINDOW_END,
        )

        assert effective.mode is ForecastMode.manual
        assert value(effective, 2027, 3) == Decimal("-4500")
        assert "händisch gesetzt" in effective.reason

    def test_unbekannter_regeltyp_prognostiziert_nichts(self):
        effective = resolve_rule(
            AUTO_PROFILE,
            override(mode="manual", rule_type="hellsehen"),
            history={},
            window_end=WINDOW_END,
        )

        assert effective.is_active is False


class TestHaendischeRegeltypen:
    def test_fester_betrag_im_jahresrhythmus(self):
        effective = resolve_rule(
            AUTO_PROFILE,
            override(
                mode="manual",
                rule_type="fixed_recurring",
                params={"amount": "-1200", "interval_months": 12, "anchor_month": 3},
            ),
            history={},
            window_end=WINDOW_END,
        )

        assert value(effective, 2027, 3) == Decimal("-1200")
        assert value(effective, 2027, 4) == Decimal("0")

    def test_fester_betrag_mit_sondermonat(self):
        effective = resolve_rule(
            AUTO_PROFILE,
            override(
                mode="manual",
                rule_type="fixed_recurring",
                params={"amount": "-3000", "special_months": {"6": "2"}},
            ),
            history={},
            window_end=WINDOW_END,
        )

        assert value(effective, 2027, 5) == Decimal("-3000")
        assert value(effective, 2027, 6) == Decimal("-6000")

    def test_gleitender_durchschnitt_ueber_das_gewaehlte_fenster(self):
        history = {WINDOW_END - offset: Decimal("-600") for offset in range(3)}
        effective = resolve_rule(
            AUTO_PROFILE,
            override(mode="manual", rule_type="rolling_average", params={"window_months": 6}),
            history=history,
            window_end=WINDOW_END,
        )

        # Drei Monate à -600, drei Monate ohne Buchung → Mittel -300.
        assert value(effective, 2027, 1) == Decimal("-300")

    def test_vorjahresmonat(self):
        history = {month_index(2026, 5): Decimal("9000")}
        effective = resolve_rule(
            AUTO_PROFILE,
            override(mode="manual", rule_type="same_period_last_year"),
            history=history,
            window_end=WINDOW_END,
        )

        assert value(effective, 2027, 5, history=history) == Decimal("9000")
        assert value(effective, 2027, 6, history=history) == Decimal("0")

    def test_vorjahresmonat_greift_im_zweiten_prognosejahr_weiter_zurueck(self):
        history = {month_index(2026, 5): Decimal("9000")}
        effective = resolve_rule(
            AUTO_PROFILE,
            override(mode="manual", rule_type="same_period_last_year"),
            history=history,
            window_end=WINDOW_END,
        )

        # 05/2028 findet 05/2027 nicht (selbst Prognose) und greift auf 05/2026 zurück.
        assert value(effective, 2028, 5, history=history) == Decimal("9000")

    def test_saisonprofil_mittelt_je_kalendermonat(self):
        history = {
            month_index(2025, 7): Decimal("10000"),
            month_index(2026, 7): Decimal("20000"),
            month_index(2025, 1): Decimal("2000"),
            month_index(2026, 1): Decimal("4000"),
        }
        effective = resolve_rule(
            AUTO_PROFILE,
            override(mode="manual", rule_type="seasonal_profile"),
            history=history,
            window_end=WINDOW_END,
        )

        assert value(effective, 2027, 7) == Decimal("15000")
        assert value(effective, 2027, 1) == Decimal("3000")
        assert value(effective, 2027, 2) == Decimal("0")

    def test_reine_planposten_regel_rechnet_selbst_nichts(self):
        effective = resolve_rule(
            AUTO_PROFILE,
            override(mode="manual", rule_type="manual_plan"),
            history={},
            window_end=WINDOW_END,
        )

        assert effective.is_active is True
        assert value(effective, 2027, 3) == Decimal("0")


class TestModifikatoren:
    def test_indexierung_erhoeht_den_betrag(self):
        effective = resolve_rule(
            AUTO_PROFILE,
            override(adjustment_pct=Decimal("3.00")),
            history={},
            window_end=WINDOW_END,
        )

        assert value(effective, 2027, 3) == Decimal("-3090.00")
        assert "Anpassung +3.00 %" in effective.reason

    def test_abschlag_senkt_den_betrag(self):
        effective = resolve_rule(
            AUTO_PROFILE,
            override(adjustment_pct=Decimal("-30.00")),
            history={},
            window_end=WINDOW_END,
        )

        assert value(effective, 2027, 3) == Decimal("-2100.00")

    def test_zahlungsverzug_schiebt_den_wert_nach_hinten(self):
        # Jahreszahlung im März, zwei Monate Verzug → Zahlung im Mai.
        effective = resolve_rule(
            AUTO_PROFILE,
            override(
                mode="manual",
                rule_type="fixed_recurring",
                params={"amount": "-1200", "interval_months": 12, "anchor_month": 3},
                shift_months=2,
            ),
            history={},
            window_end=WINDOW_END,
        )

        assert value(effective, 2027, 3) == Decimal("0")
        assert value(effective, 2027, 5) == Decimal("-1200")
        assert "Zahlungsverzug 2 Monat(e)" in effective.reason


class TestSzenarien:
    def _income(self, confidence: Confidence):
        return resolve_rule(
            profile_with(
                ForecastRule(
                    rule_type=RuleType.rolling_average,
                    reason="Ø",
                    confidence=confidence,
                    amount=Decimal("1000"),
                )
            ),
            None,
            history={},
            window_end=WINDOW_END,
        )

    def _expense(self, confidence: Confidence):
        return resolve_rule(
            profile_with(
                ForecastRule(
                    rule_type=RuleType.rolling_average,
                    reason="Ø",
                    confidence=confidence,
                    amount=Decimal("-1000"),
                )
            ),
            None,
            history={},
            window_end=WINDOW_END,
        )

    def test_pessimistisch_senkt_einnahmen(self):
        effective = self._income(Confidence.medium)

        assert value(effective, 2027, 3, scenario=Scenario.low) == Decimal("750.00")

    def test_pessimistisch_erhoeht_ausgaben(self):
        # Der Fallstrick: ein Multiplikator würde -1000 auf -900 verkleinern und
        # damit das pessimistische Szenario in sein Gegenteil verkehren.
        effective = self._expense(Confidence.medium)

        assert value(effective, 2027, 3, scenario=Scenario.low) == Decimal("-1250.00")

    def test_optimistisch_dreht_beide_richtungen_um(self):
        assert value(self._income(Confidence.medium), 2027, 3, scenario=Scenario.high) == Decimal("1250.00")
        assert value(self._expense(Confidence.medium), 2027, 3, scenario=Scenario.high) == Decimal("-750.00")

    def test_bandbreite_haengt_an_der_confidence(self):
        assert value(self._income(Confidence.high), 2027, 3, scenario=Scenario.low) == Decimal("900.00")
        assert value(self._income(Confidence.low), 2027, 3, scenario=Scenario.low) == Decimal("500.00")

    def test_erwartungswert_bleibt_unveraendert(self):
        assert value(self._income(Confidence.low), 2027, 3) == Decimal("1000")
