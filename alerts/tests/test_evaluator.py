"""Tests for the stateful rule evaluator and confirmation tracker."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from alerts.evaluator import (  # type: ignore
    ConfirmationTracker,
    RuleEvaluator,
    SensorObservation,
)
from alerts.rules import load_rules_from_file  # type: ignore


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BARRAGEM_X_RULES = REPO_ROOT / "alerts" / "rules" / "barragem_x.yaml"


def _ruleset():
    return load_rules_from_file(BARRAGEM_X_RULES)


def _obs(sensor_id: str, metric: str, t: datetime, value: float,
         quality: str = "GOOD") -> SensorObservation:
    return SensorObservation(
        sensor_id=sensor_id, metric=metric, t_sample=t,
        value=value, quality=quality,
    )


def _thr(atencao=380, alerta=420, n1=460, n2=500):
    def cb(rule, sensor):
        return {"atencao": atencao, "alerta": alerta,
                "emergencia_n1": n1, "emergencia_n2": n2}
    return cb


def test_does_not_fire_before_persistence():
    ev = RuleEvaluator(_ruleset().rules, thresholds_for=_thr())
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # Above alerta threshold (420), but only for 10 minutes (< 30m persistence)
    r1 = ev.observe(_obs("pz-sec02-fund-01", "pressure_kpa", t0, 430))
    r2 = ev.observe(_obs("pz-sec02-fund-01", "pressure_kpa",
                          t0 + timedelta(minutes=10), 435))
    # No firing yet
    fired_ids = [e.rule.rule_id for e in r1.fired + r2.fired]
    assert "pz-fund-alerta" not in fired_ids


def test_fires_after_persistence_elapsed():
    ev = RuleEvaluator(_ruleset().rules, thresholds_for=_thr())
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ev.observe(_obs("pz-sec02-fund-01", "pressure_kpa", t0, 430))
    # 30 min elapsed → persistence satisfied
    r = ev.observe(_obs("pz-sec02-fund-01", "pressure_kpa",
                         t0 + timedelta(minutes=31), 432))
    assert any(e.rule.rule_id == "pz-fund-alerta" for e in r.fired)
    assert any(e.rule.rule_id == "pz-fund-atencao" for e in r.fired) is False  # needs 1h


def test_fires_once_not_repeatedly():
    ev = RuleEvaluator(_ruleset().rules, thresholds_for=_thr())
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ev.observe(_obs("pz-sec02-fund-01", "pressure_kpa", t0, 430))
    r1 = ev.observe(_obs("pz-sec02-fund-01", "pressure_kpa",
                          t0 + timedelta(minutes=31), 432))
    r2 = ev.observe(_obs("pz-sec02-fund-01", "pressure_kpa",
                          t0 + timedelta(minutes=35), 434))
    count = sum(
        1 for e in r1.fired + r2.fired if e.rule.rule_id == "pz-fund-alerta"
    )
    assert count == 1


def test_hysteresis_prevents_flapping():
    ev = RuleEvaluator(_ruleset().rules, thresholds_for=_thr())
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # Trigger
    ev.observe(_obs("pz-sec02-fund-01", "pressure_kpa", t0, 430))
    ev.observe(_obs("pz-sec02-fund-01", "pressure_kpa",
                      t0 + timedelta(minutes=31), 432))
    # 5% hysteresis below 420 = 399
    r_mid = ev.observe(_obs("pz-sec02-fund-01", "pressure_kpa",
                              t0 + timedelta(minutes=60), 410))
    # Still within hysteresis band — no resolve
    assert not r_mid.resolved
    r_done = ev.observe(_obs("pz-sec02-fund-01", "pressure_kpa",
                               t0 + timedelta(minutes=90), 395))
    # Now clearly below → resolves
    assert any(e.rule.rule_id == "pz-fund-alerta" for e in r_done.resolved)


def test_below_quality_requirement_skips():
    ev = RuleEvaluator(_ruleset().rules, thresholds_for=_thr())
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # pz-fund-alerta requires GOOD quality. BAD must be ignored.
    ev.observe(_obs("pz-sec02-fund-01", "pressure_kpa", t0, 450, quality="BAD"))
    r = ev.observe(_obs("pz-sec02-fund-01", "pressure_kpa",
                         t0 + timedelta(minutes=31), 451, quality="BAD"))
    assert not any(e.rule.rule_id == "pz-fund-alerta" for e in r.fired)


def test_absolute_direction_tilt():
    ev = RuleEvaluator(_ruleset().rules, thresholds_for=_thr(alerta=0.25))
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # Tilt -0.30 deg: |−0.30| > 0.25
    ev.observe(_obs("ipi-crista-sec02-01", "tilt_x_deg", t0, -0.30))
    r = ev.observe(_obs("ipi-crista-sec02-01", "tilt_x_deg",
                         t0 + timedelta(minutes=61), -0.31))
    assert any(e.rule.rule_id == "ipi-crista-alerta" for e in r.fired)


def test_confirmation_requires_multiple_sensors():
    ev = RuleEvaluator(_ruleset().rules, thresholds_for=_thr(n2=500))
    confirm = ConfirmationTracker(window_s=300)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)

    # Only one sensor above emergency → fired list contains a confirm_count>1
    # rule event, but tracker should NOT yet upgrade it.
    r1 = ev.observe(_obs("pz-sec02-fund-01", "pressure_kpa", t0, 510))
    group1 = confirm.observe(r1.fired)
    assert group1 == []

    # Second sensor crossed shortly after → upgrade fires.
    r2 = ev.observe(
        _obs("pz-sec03-fund-01", "pressure_kpa",
             t0 + timedelta(seconds=30), 520)
    )
    group2 = confirm.observe(r2.fired)
    assert len(group2) == 1
    assert group2[0].rule.rule_id == "pz-emergencia-confirmado"
    assert set(group2[0].sensor_ids) == {"pz-sec02-fund-01", "pz-sec03-fund-01"}


def test_missing_threshold_ref_does_not_crash():
    ev = RuleEvaluator(_ruleset().rules, thresholds_for=lambda r, s: {})
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # No thresholds returned → no firing, no exception.
    r = ev.observe(_obs("pz-sec02-fund-01", "pressure_kpa", t0, 999999))
    assert r.fired == []
