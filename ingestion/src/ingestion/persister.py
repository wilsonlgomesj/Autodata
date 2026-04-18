"""Persister: translates validated telemetry payloads into database writes.

Pure logic — no DB driver dependency in the core functions so they can be
unit-tested without Postgres. The DB driver is injected via a minimal
"executor" protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Protocol


@dataclass(frozen=True)
class MeasurementRow:
    t_sample: str
    site_id: str
    sensor_id: str
    metric: str
    value: float | None
    value_array: list[float] | None
    quality: str
    flags: list[str]
    msg_id: str
    seq: int


class Executor(Protocol):
    """Minimal interface the persister needs from the DB driver.

    Real implementation wraps psycopg or asyncpg. Test implementation is
    a dict-backed fake.
    """

    def execute_many(
        self, sql: str, rows: Iterable[tuple[Any, ...]]
    ) -> int: ...


MEASUREMENT_INSERT_SQL = """
INSERT INTO geo.measurement
  (t_sample, site_id, sensor_id, metric, value, value_array, quality, flags, msg_id, seq)
VALUES
  ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
ON CONFLICT (site_id, sensor_id, metric, msg_id) DO NOTHING
"""


def fanout_payload_to_rows(payload: dict[str, Any]) -> list[MeasurementRow]:
    """Explode a telemetry payload (N values) into N measurement rows.

    Assumes `payload` has already been validated against geo.telemetry.v1.
    """
    rows: list[MeasurementRow] = []
    site = payload["site"]
    sensor = payload["sensor"]
    t_sample = payload["t_sample"]
    msg_id = payload["msg_id"]
    seq = int(payload["seq"])
    quality_obj = payload["quality"]
    quality = quality_obj["code"]
    flags = list(quality_obj.get("flags", []))

    for metric, v in payload["values"].items():
        if isinstance(v, (int, float)):
            rows.append(
                MeasurementRow(
                    t_sample=t_sample,
                    site_id=site,
                    sensor_id=sensor,
                    metric=metric,
                    value=float(v),
                    value_array=None,
                    quality=quality,
                    flags=flags,
                    msg_id=msg_id,
                    seq=seq,
                )
            )
        elif isinstance(v, list):
            rows.append(
                MeasurementRow(
                    t_sample=t_sample,
                    site_id=site,
                    sensor_id=sensor,
                    metric=metric,
                    value=None,
                    value_array=[float(x) for x in v],
                    quality=quality,
                    flags=flags,
                    msg_id=msg_id,
                    seq=seq,
                )
            )
        else:
            raise ValueError(
                f"metric {metric!r}: value must be number or list, got {type(v).__name__}"
            )
    return rows


def persist_payloads(
    executor: Executor,
    payloads: Iterable[dict[str, Any]],
) -> int:
    """Insert a batch of validated payloads. Returns number of rows inserted.

    Idempotency is enforced by the ON CONFLICT clause against
    measurement_msg_unique. Returning count below may be lower than
    len(flattened rows) when duplicates arrive (expected after RTU replay).
    """
    all_rows: list[MeasurementRow] = []
    for p in payloads:
        all_rows.extend(fanout_payload_to_rows(p))

    if not all_rows:
        return 0

    tuples = [
        (
            r.t_sample, r.site_id, r.sensor_id, r.metric,
            r.value, r.value_array, r.quality, r.flags,
            r.msg_id, r.seq,
        )
        for r in all_rows
    ]
    return executor.execute_many(MEASUREMENT_INSERT_SQL, tuples)


DEAD_LETTER_INSERT_SQL = """
INSERT INTO geo.dead_letter (topic, payload, reason, details)
VALUES ($1, $2::jsonb, $3, $4)
"""


def persist_dead_letter(
    executor: Executor,
    topic: str,
    raw_payload: str,
    reason: str,
    details: str | None = None,
) -> None:
    executor.execute_many(
        DEAD_LETTER_INSERT_SQL,
        [(topic, raw_payload, reason, details)],
    )
