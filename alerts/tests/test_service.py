"""Integration test: AlertService end-to-end with telemetry payloads.

Feeds the same payloads used in the ingestion tests into the alert service
through a fake executor + fake publisher, and exercises real rule evaluation.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alerts.emitter import AlertEmitter  # type: ignore
from alerts.evaluator import RuleEvaluator  # type: ignore
from alerts.rules import load_rules_from_file  # type: ignore
from alerts.service import AlertService  # type: ignore


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RULES_PATH = REPO_ROOT / "alerts" / "rules" / "barragem_x.yaml"
PAYLOAD_DIR = REPO_ROOT / "examples" / "payloads"


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


def _thresholds(rule, sensor):
    return {"atencao": 380, "alerta": 420, "emergencia_n1": 460, "emergencia_n2": 500}


def _mk_service(structure_id: str | None = "barragem-principal"):
    rs = load_rules_from_file(RULES_PATH)
    executor = FakeExecutor()
    publisher = FakePublisher()
    evaluator = RuleEvaluator(rs.rules, thresholds_for=_thresholds)
    emitter = AlertEmitter(executor, publisher)
    svc = AlertService(
        rules_path=RULES_PATH,
        evaluator=evaluator,
        emitter=emitter,
        structure_lookup=lambda s, sensor: structure_id,
    )
    return svc, executor, publisher


def _load_payload(name: str) -> dict:
    return json.loads((PAYLOAD_DIR / name).read_text())


def _shift_time(payload: dict, minutes: int, value_override: dict | None = None) -> dict:
    p = copy.deepcopy(payload)
    t = datetime.fromisoformat(p["t_sample"].replace("Z", "+00:00"))
    t2 = t + timedelta(minutes=minutes)
    p["t_sample"] = t2.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t2.microsecond // 1000:03d}Z"
    if value_override:
        p["values"].update(value_override)
    return p


def test_single_sensor_alert_fires_after_persistence():
    svc, executor, publisher = _mk_service()
    base = _load_payload("piezometer_vw_good.json")

    # 1st obs at t0 with pressure 430 (> alerta 420).
    p0 = _shift_time(base, 0, {"pressure_kpa": 430})
    svc.handle_payload(p0)

    # 2nd obs 31 min later — persistence satisfied → fires once.
    p1 = _shift_time(base, 31, {"pressure_kpa": 432})
    emitted = svc.handle_payload(p1)

    assert emitted >= 1

    # At least one MQTT alert on topic ending in /alerta
    topics = [t for (t, _, _) in publisher.published]
    assert any(t.endswith("/alerta") for t in topics), topics
    # DB write
    assert executor.calls, "no alert_event insert"


def test_normal_value_emits_nothing():
    svc, executor, publisher = _mk_service()
    base = _load_payload("piezometer_vw_good.json")
    # Default value is 312.4 kPa — well below atencao 380.
    svc.handle_payload(base)
    assert executor.calls == []
    assert publisher.published == []


def test_confirmed_emergency_fires_across_sensors():
    svc, executor, publisher = _mk_service()
    base = _load_payload("piezometer_vw_good.json")

    # Two different pz-*-fund-* sensors both above 500 kPa (emergencia_n2)
    a = _shift_time(base, 0, {"pressure_kpa": 510})
    a["sensor"] = "pz-sec02-fund-01"
    b = _shift_time(base, 0, {"pressure_kpa": 520})
    b["sensor"] = "pz-sec03-fund-01"

    svc.handle_payload(a)
    svc.handle_payload(b)

    # There should be a single EMERGENCIA_N2 alert message.
    emergency_topics = [
        t for (t, _, _) in publisher.published if t.endswith("/emergencia_n2")
    ]
    assert len(emergency_topics) == 1

    # Payload sensors list contains both
    _, payload, _ = [x for x in publisher.published
                      if x[0].endswith("/emergencia_n2")][0]
    body = json.loads(payload)
    assert set(body["sensors"]) == {"pz-sec02-fund-01", "pz-sec03-fund-01"}
