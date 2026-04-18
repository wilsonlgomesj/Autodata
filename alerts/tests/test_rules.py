"""Tests for rule loading and validation."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from alerts.rules import (  # type: ignore
    Rule,
    load_rules_from_dir,
    load_rules_from_file,
    parse_iso8601_duration_seconds,
    parse_rule,
)


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BARRAGEM_X_RULES = REPO_ROOT / "alerts" / "rules" / "barragem_x.yaml"


def test_load_barragem_x_rules():
    rs = load_rules_from_file(BARRAGEM_X_RULES)
    assert len(rs.rules) == 4
    ids = [r.rule_id for r in rs.rules]
    assert "pz-fund-alerta" in ids
    assert "pz-emergencia-confirmado" in ids


def test_rule_matches_glob():
    rs = load_rules_from_file(BARRAGEM_X_RULES)
    rule = next(r for r in rs.rules if r.rule_id == "pz-fund-alerta")
    assert rule.matches_sensor("pz-sec02-fund-01")
    assert rule.matches_sensor("pz-sec01-fund-02")
    assert not rule.matches_sensor("pz-sec02-cont-01")
    assert not rule.matches_sensor("ipi-crista-sec02-01")


def test_for_sensor_metric():
    rs = load_rules_from_file(BARRAGEM_X_RULES)
    matches = rs.for_sensor_metric("pz-sec02-fund-01", "pressure_kpa")
    ids = {r.rule_id for r in matches}
    assert ids == {"pz-fund-atencao", "pz-fund-alerta", "pz-emergencia-confirmado"}


def test_resolve_threshold_by_ref():
    rs = load_rules_from_file(BARRAGEM_X_RULES)
    rule = next(r for r in rs.rules if r.rule_id == "pz-fund-alerta")
    val = rule.resolve_threshold({"atencao": 380, "alerta": 420, "emergencia_n2": 500})
    assert val == 420


def test_resolve_threshold_missing_ref_raises():
    rs = load_rules_from_file(BARRAGEM_X_RULES)
    rule = next(r for r in rs.rules if r.rule_id == "pz-fund-alerta")
    with pytest.raises(KeyError):
        rule.resolve_threshold({"atencao": 380})


def test_parse_duration():
    assert parse_iso8601_duration_seconds("PT0S") == 0
    assert parse_iso8601_duration_seconds("PT30S") == 30
    assert parse_iso8601_duration_seconds("PT5M") == 300
    assert parse_iso8601_duration_seconds("PT1H") == 3600
    assert parse_iso8601_duration_seconds("PT1H30M") == 5400
    with pytest.raises(ValueError):
        parse_iso8601_duration_seconds("not a duration")


def test_rule_rejects_invalid_level():
    raw = {
        "rule_id": "x", "version": "v1.0.0", "level": "WAT",
        "match": {"sensor": "x", "metric": "y"},
        "when": {"direction": "above", "value": 1},
    }
    with pytest.raises(ValueError):
        parse_rule(raw, "test")


def test_rule_requires_value_xor_ref():
    raw = {
        "rule_id": "x", "version": "v1.0.0", "level": "ATENCAO",
        "match": {"sensor": "x", "metric": "y"},
        "when": {"direction": "above", "value": 1, "ref": "threshold.alerta"},
    }
    with pytest.raises(ValueError):
        parse_rule(raw, "test")


def test_rule_rejects_unknown_action():
    raw = {
        "rule_id": "x", "version": "v1.0.0", "level": "ATENCAO",
        "match": {"sensor": "x", "metric": "y"},
        "when": {"direction": "above", "value": 1},
        "actions": ["nuclear_strike"],
    }
    with pytest.raises(ValueError):
        parse_rule(raw, "test")


def test_rule_rejects_bad_version():
    raw = {
        "rule_id": "x", "version": "1.0", "level": "ATENCAO",
        "match": {"sensor": "x", "metric": "y"},
        "when": {"direction": "above", "value": 1},
    }
    with pytest.raises(ValueError):
        parse_rule(raw, "test")


def test_load_dir_detects_duplicate_rule_ids(tmp_path: Path):
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    a.write_text(textwrap.dedent("""
        rules:
          - rule_id: dup
            version: v1.0.0
            level: ATENCAO
            match: {sensor: s1, metric: m1}
            when: {direction: above, value: 1}
    """).strip())
    b.write_text(textwrap.dedent("""
        rules:
          - rule_id: dup
            version: v1.0.0
            level: ALERTA
            match: {sensor: s2, metric: m2}
            when: {direction: above, value: 2}
    """).strip())
    with pytest.raises(ValueError, match="duplicate rule_id"):
        load_rules_from_dir(tmp_path)
