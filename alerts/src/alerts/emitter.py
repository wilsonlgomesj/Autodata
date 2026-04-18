"""Turn FiredEvent / ConfirmedFiredEvent objects into geo.alert.v1 payloads
and write them to Postgres + publish to MQTT.

Persistence and publication are injected as protocols so the emitter can be
unit-tested without real infrastructure.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Protocol

from .evaluator import ConfirmedFiredEvent, FiredEvent
from .rules import Rule


_ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid() -> str:
    # Crockford base32, 26 chars. Good enough for msg_id; not strictly
    # time-sortable (real ULID impl is, this is a random fallback).
    return "".join(secrets.choice(_ULID_ALPHABET) for _ in range(26))


def _rfc3339(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


class Executor(Protocol):
    def execute_many(self, sql: str, rows: Iterable[tuple[Any, ...]]) -> int: ...


class Publisher(Protocol):
    def publish(self, topic: str, payload: str, qos: int = 1) -> None: ...


ALERT_EVENT_INSERT_SQL = """
INSERT INTO geo.alert_event
  (msg_id, site_id, structure_id, rule_id, rule_version, level,
   t_triggered, sensors, evidence, actions_taken)
VALUES
  ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10)
ON CONFLICT (msg_id) DO NOTHING
"""


@dataclass
class AlertOutput:
    msg_id: str
    site_id: str
    structure_id: str | None
    rule: Rule
    level: str
    t_triggered: datetime
    sensors: list[str]
    evidence: dict[str, Any]
    actions: list[str]
    payload_json: str

    def topic(self) -> str:
        struct = self.structure_id or "global"
        return f"alert/{self.site_id}/{struct}/{self.level.lower()}"


def build_alert_from_fired(
    ev: FiredEvent, site_id: str, structure_id: str | None = None
) -> AlertOutput:
    t = _rfc3339(ev.t_triggered)
    payload = {
        "schema": "geo.alert.v1",
        "msg_id": new_ulid(),
        "site": site_id,
        "structure": structure_id,
        "level": ev.rule.level,
        "rule_id": ev.rule.rule_id,
        "rule_version": ev.rule.version,
        "t_triggered": t,
        "t_resolved": None,
        "sensors": [ev.sensor_id],
        "evidence": {
            "summary": (
                f"{ev.sensor_id} {ev.rule.metric}={ev.observed:.3f} "
                f"crossed {ev.rule.direction} threshold {ev.threshold:.3f}"
            ),
            "samples": [
                {
                    "sensor": ev.sensor_id,
                    "t_sample": t,
                    "values": {ev.rule.metric: ev.observed},
                    "threshold": ev.threshold,
                    "observed": ev.observed,
                }
            ],
        },
        "actions_taken": list(ev.rule.actions),
    }
    if structure_id is None:
        # Omit null structure to pass JSON Schema's pattern constraint.
        payload.pop("structure")
    return AlertOutput(
        msg_id=payload["msg_id"],
        site_id=site_id,
        structure_id=structure_id,
        rule=ev.rule,
        level=ev.rule.level,
        t_triggered=ev.t_triggered,
        sensors=[ev.sensor_id],
        evidence=payload["evidence"],
        actions=list(ev.rule.actions),
        payload_json=json.dumps(payload),
    )


def build_alert_from_confirmed(
    ev: ConfirmedFiredEvent, site_id: str, structure_id: str | None = None
) -> AlertOutput:
    t = _rfc3339(ev.t_triggered)
    samples = [
        {
            "sensor": sub.sensor_id,
            "t_sample": _rfc3339(sub.t_triggered),
            "values": {sub.rule.metric: sub.observed},
            "threshold": sub.threshold,
            "observed": sub.observed,
        }
        for sub in ev.evidence
    ]
    payload = {
        "schema": "geo.alert.v1",
        "msg_id": new_ulid(),
        "site": site_id,
        "structure": structure_id,
        "level": ev.rule.level,
        "rule_id": ev.rule.rule_id,
        "rule_version": ev.rule.version,
        "t_triggered": t,
        "t_resolved": None,
        "sensors": list(ev.sensor_ids),
        "evidence": {
            "summary": (
                f"confirmed by {len(ev.sensor_ids)} sensors "
                f"for rule {ev.rule.rule_id}"
            ),
            "samples": samples,
        },
        "actions_taken": list(ev.rule.actions),
    }
    if structure_id is None:
        payload.pop("structure")
    return AlertOutput(
        msg_id=payload["msg_id"],
        site_id=site_id,
        structure_id=structure_id,
        rule=ev.rule,
        level=ev.rule.level,
        t_triggered=ev.t_triggered,
        sensors=list(ev.sensor_ids),
        evidence=payload["evidence"],
        actions=list(ev.rule.actions),
        payload_json=json.dumps(payload),
    )


class AlertEmitter:
    def __init__(self, executor: Executor, publisher: Publisher) -> None:
        self.executor = executor
        self.publisher = publisher

    def emit(self, alert: AlertOutput) -> None:
        self.executor.execute_many(
            ALERT_EVENT_INSERT_SQL,
            [
                (
                    alert.msg_id,
                    alert.site_id,
                    alert.structure_id,
                    alert.rule.rule_id,
                    alert.rule.version,
                    alert.level,
                    alert.t_triggered,
                    alert.sensors,
                    json.dumps(alert.evidence),
                    alert.actions,
                )
            ],
        )
        self.publisher.publish(alert.topic(), alert.payload_json, qos=1)
