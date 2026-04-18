"""GraphQL mutations: acknowledge alert, update threshold, issue command.

Every mutation writes to geo.audit_event to preserve an immutable trail.
Authorization is enforced at the API layer (FastAPI dependency) but context
here carries the user_id so audit rows reflect the real operator.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Protocol

import strawberry
from strawberry.types import Info


# ---------------------------------------------------------------------------
# Write-side protocol — injected in context, mockable in tests
# ---------------------------------------------------------------------------

class WriteClient(Protocol):
    def execute(self, sql: str, params: tuple[Any, ...]) -> int: ...
    def fetch_one(self, sql: str, params: tuple[Any, ...]) -> tuple[Any, ...] | None: ...


class MqttPublisher(Protocol):
    def publish(self, topic: str, payload: str, qos: int = 1) -> None: ...


# ---------------------------------------------------------------------------
# Commands emitter for issueCommand mutation
# ---------------------------------------------------------------------------

@dataclass
class CommandContext:
    write: WriteClient
    publisher: Optional[MqttPublisher]  # may be None in tests


# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------

ACK_ALERT_SQL = """
UPDATE geo.alert_event
SET ack_user = %s, ack_at = now(), ack_comment = %s
WHERE event_id = %s AND ack_at IS NULL
RETURNING event_id, site_id, level::text, t_triggered
"""

UPDATE_THRESHOLD_CLOSE_SQL = """
UPDATE geo.threshold
SET effective_to = now()
WHERE site_id = %s AND sensor_id = %s AND metric = %s
  AND effective_to IS NULL
"""

UPDATE_THRESHOLD_INSERT_SQL = """
INSERT INTO geo.threshold
  (site_id, sensor_id, metric, effective_from, atencao, alerta,
   emergencia_n1, emergencia_n2, direction, hysteresis_pct,
   approved_by, approval_ref, notes)
VALUES
  (%s, %s, %s, now(), %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

AUDIT_SQL = """
INSERT INTO geo.audit_event
  (actor, actor_kind, action, target, payload, correlation_id)
VALUES
  (%s, %s, %s, %s::jsonb, %s::jsonb, %s)
"""


# ---------------------------------------------------------------------------
# GraphQL input/result types
# ---------------------------------------------------------------------------

@strawberry.input
class ThresholdLevelsInput:
    atencao: Optional[float] = None
    alerta: Optional[float] = None
    emergencia_n1: Optional[float] = None
    emergencia_n2: Optional[float] = None


@strawberry.input
class UpdateThresholdInput:
    site_id: str
    sensor_id: str
    metric: str
    levels: ThresholdLevelsInput
    direction: str = "above"
    hysteresis_pct: float = 5.0
    approval_ref: str = ""
    notes: Optional[str] = None


@strawberry.input
class IssueCommandInput:
    site_id: str
    gateway: str
    device: Optional[str] = None
    sensor: Optional[str] = None
    action: str = ""
    params_json: Optional[str] = None  # JSON-encoded params map
    ttl_s: int = 3600


@strawberry.type
class MutationResult:
    ok: bool
    message: str
    event_id: Optional[str] = None
    correlation_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid() -> str:
    import secrets
    return "".join(secrets.choice(_ULID_ALPHABET) for _ in range(26))


def _user(info: Info) -> str:
    return info.context.get("user_id", "anonymous")


def _write(info: Info) -> WriteClient:
    return info.context["write"]


def _publisher(info: Info) -> Optional[MqttPublisher]:
    return info.context.get("publisher")


def _audit(
    write: WriteClient,
    actor: str,
    action: str,
    target: dict,
    payload: dict | None,
    correlation_id: str,
) -> None:
    write.execute(
        AUDIT_SQL,
        (
            actor,
            "user",
            action,
            json.dumps(target),
            json.dumps(payload) if payload is not None else None,
            correlation_id,
        ),
    )


# ---------------------------------------------------------------------------
# Mutation root
# ---------------------------------------------------------------------------

@strawberry.type
class Mutation:
    @strawberry.mutation
    def acknowledge_alert(
        self,
        info: Info,
        event_id: str,
        comment: str,
    ) -> MutationResult:
        user = _user(info)
        write = _write(info)
        correlation = new_ulid()

        row = write.fetch_one(ACK_ALERT_SQL, (user, comment, event_id))
        if row is None:
            return MutationResult(
                ok=False,
                message="alert not found or already acknowledged",
            )

        _audit(
            write, user, "alert.acknowledge",
            target={"event_id": str(row[0]), "site_id": row[1], "level": row[2]},
            payload={"comment": comment},
            correlation_id=correlation,
        )
        return MutationResult(
            ok=True,
            message="alert acknowledged",
            event_id=str(row[0]),
            correlation_id=correlation,
        )

    @strawberry.mutation
    def update_threshold(
        self,
        info: Info,
        input: UpdateThresholdInput,
    ) -> MutationResult:
        user = _user(info)
        write = _write(info)
        correlation = new_ulid()

        # Monotonic-level sanity check for direction=above
        if input.direction == "above":
            seq = [
                input.levels.atencao,
                input.levels.alerta,
                input.levels.emergencia_n1,
                input.levels.emergencia_n2,
            ]
            clean = [v for v in seq if v is not None]
            if clean != sorted(clean):
                return MutationResult(
                    ok=False,
                    message="levels must be monotonic-ascending for direction=above",
                )

        # Close any currently-active threshold, then insert a new row.
        # Both writes run via the injected WriteClient — in prod this is a
        # psycopg client wrapping a single transaction.
        write.execute(
            UPDATE_THRESHOLD_CLOSE_SQL,
            (input.site_id, input.sensor_id, input.metric),
        )
        write.execute(
            UPDATE_THRESHOLD_INSERT_SQL,
            (
                input.site_id, input.sensor_id, input.metric,
                input.levels.atencao, input.levels.alerta,
                input.levels.emergencia_n1, input.levels.emergencia_n2,
                input.direction, input.hysteresis_pct,
                user, input.approval_ref, input.notes,
            ),
        )

        _audit(
            write, user, "threshold.update",
            target={
                "site_id": input.site_id, "sensor_id": input.sensor_id,
                "metric": input.metric,
            },
            payload={
                "levels": {
                    "atencao": input.levels.atencao,
                    "alerta": input.levels.alerta,
                    "emergencia_n1": input.levels.emergencia_n1,
                    "emergencia_n2": input.levels.emergencia_n2,
                },
                "direction": input.direction,
                "hysteresis_pct": input.hysteresis_pct,
                "approval_ref": input.approval_ref,
            },
            correlation_id=correlation,
        )
        return MutationResult(
            ok=True,
            message="threshold updated; previous version closed",
            correlation_id=correlation,
        )

    @strawberry.mutation
    def issue_command(
        self,
        info: Info,
        input: IssueCommandInput,
    ) -> MutationResult:
        user = _user(info)
        write = _write(info)
        publisher = _publisher(info)
        correlation = new_ulid()

        try:
            params = json.loads(input.params_json) if input.params_json else {}
            if not isinstance(params, dict):
                raise ValueError("params_json must decode to an object")
        except (json.JSONDecodeError, ValueError) as e:
            return MutationResult(ok=False, message=f"invalid params_json: {e}")

        target = {"gateway": input.gateway}
        if input.device:
            target["device"] = input.device
        if input.sensor:
            target["sensor"] = input.sensor

        payload = {
            "schema": "geo.command.v1",
            "msg_id": new_ulid(),
            "correlation_id": correlation,
            "site": input.site_id,
            "target": target,
            "action": input.action,
            "params": params,
            "issued_by": user,
            "t_issued": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.") + "000Z",
            "ttl_s": input.ttl_s,
        }

        _audit(
            write, user, "command.issue",
            target=target | {"site_id": input.site_id},
            payload={"action": input.action, "params": params, "ttl_s": input.ttl_s},
            correlation_id=correlation,
        )

        if publisher is not None:
            topic = (
                f"cmd/{input.site_id}/{input.gateway}"
                + (f"/{input.device}" if input.device else "")
            )
            publisher.publish(topic, json.dumps(payload), qos=1)

        return MutationResult(
            ok=True,
            message="command issued",
            correlation_id=correlation,
        )
