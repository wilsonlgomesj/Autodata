"""Tests for alert emission: payload shape + DB write + MQTT publish."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from alerts.emitter import (  # type: ignore
    AlertEmitter,
    build_alert_from_confirmed,
    build_alert_from_fired,
)
from alerts.evaluator import ConfirmedFiredEvent, FiredEvent  # type: ignore
from alerts.rules import load_rules_from_file  # type: ignore

# reuse validator from the repo tools/
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))
from validate import Report, validate_payload  # type: ignore


@dataclass
class FakeExecutor:
    calls: list = field(default_factory=list)

    def execute_many(self, sql, rows):
        rows = list(rows)
        self.calls.append((sql, rows))
        return len(rows)


@dataclass
class FakePublisher:
    published: list = field(default_factory=list)

    def publish(self, topic, payload, qos=1):
        self.published.append((topic, payload, qos))


def _rule(rid="pz-fund-alerta"):
    rs = load_rules_from_file(REPO_ROOT / "alerts" / "rules" / "barragem_x.yaml")
    return next(r for r in rs.rules if r.rule_id == rid)


def test_alert_payload_conforms_to_schema():
    r = _rule("pz-fund-alerta")
    ev = FiredEvent(
        rule=r,
        sensor_id="pz-sec02-fund-01",
        t_triggered=datetime(2026, 4, 18, 14, 10, tzinfo=timezone.utc),
        observed=421.5,
        threshold=420.0,
    )
    alert = build_alert_from_fired(ev, site_id="mineradora-x-barragem-norte")
    payload = json.loads(alert.payload_json)

    report = Report()
    validate_payload(payload, report)
    assert report.ok(), f"schema errors: {report.errors}"

    assert payload["level"] == "ALERTA"
    assert payload["sensors"] == ["pz-sec02-fund-01"]
    assert payload["rule_id"] == "pz-fund-alerta"
    assert payload["evidence"]["samples"][0]["observed"] == 421.5


def test_confirmed_alert_has_all_sensors_and_validates():
    r = _rule("pz-emergencia-confirmado")
    subs = [
        FiredEvent(rule=r, sensor_id="pz-sec02-fund-01",
                   t_triggered=datetime(2026, 1, 1, tzinfo=timezone.utc),
                   observed=510, threshold=500),
        FiredEvent(rule=r, sensor_id="pz-sec03-fund-01",
                   t_triggered=datetime(2026, 1, 1, tzinfo=timezone.utc),
                   observed=520, threshold=500),
    ]
    conf = ConfirmedFiredEvent(
        rule=r,
        sensor_ids=["pz-sec02-fund-01", "pz-sec03-fund-01"],
        t_triggered=datetime(2026, 1, 1, tzinfo=timezone.utc),
        evidence=subs,
    )
    alert = build_alert_from_confirmed(
        conf, site_id="mineradora-x-barragem-norte"
    )
    payload = json.loads(alert.payload_json)
    report = Report()
    validate_payload(payload, report)
    assert report.ok(), f"schema errors: {report.errors}"
    assert sorted(payload["sensors"]) == ["pz-sec02-fund-01", "pz-sec03-fund-01"]
    assert payload["level"] == "EMERGENCIA_N2"


def test_emitter_writes_to_db_and_publishes():
    r = _rule("pz-fund-alerta")
    ev = FiredEvent(
        rule=r,
        sensor_id="pz-sec02-fund-01",
        t_triggered=datetime(2026, 4, 18, 14, 10, tzinfo=timezone.utc),
        observed=421.5,
        threshold=420.0,
    )
    alert = build_alert_from_fired(ev, site_id="mineradora-x-barragem-norte",
                                    structure_id="barragem-principal")
    executor = FakeExecutor()
    publisher = FakePublisher()
    emitter = AlertEmitter(executor, publisher)
    emitter.emit(alert)

    # DB
    assert len(executor.calls) == 1
    sql, rows = executor.calls[0]
    assert "INSERT INTO geo.alert_event" in sql
    assert "ON CONFLICT (msg_id)" in sql
    assert len(rows) == 1

    # MQTT
    assert len(publisher.published) == 1
    topic, payload, qos = publisher.published[0]
    assert topic == "alert/mineradora-x-barragem-norte/barragem-principal/alerta"
    assert qos == 1
    body = json.loads(payload)
    assert body["level"] == "ALERTA"
