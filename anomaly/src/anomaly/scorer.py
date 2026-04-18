"""Live scorer: subscribes to telemetry, maintains a per-sensor rolling
window, extracts features, scores against the loaded model, and records
results to Postgres. Designed to run alongside ingestion as an independent
process — if it crashes, ingestion keeps collecting data and we lose only
the scoring signal.
"""

from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Deque, Iterable, Protocol

from .features import FeatureVector, extract
from .model import TrainedModel, score as score_against_model


log = logging.getLogger(__name__)


@dataclass
class ScoringResult:
    sensor_id: str
    metric: str
    t_sample: datetime
    score: float
    is_anomaly: bool
    features: FeatureVector


class Executor(Protocol):
    def execute(self, sql: str, params: tuple[Any, ...]) -> int: ...


# SQL statements
SCORE_INSERT_SQL = """
INSERT INTO geo.anomaly_score
  (t_sample, site_id, sensor_id, metric, model_id, score, is_anomaly, features)
VALUES
  (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
"""

EVENT_INSERT_SQL = """
INSERT INTO geo.anomaly_event
  (site_id, sensor_id, metric, model_id, t_sample, score, features)
VALUES
  (%s, %s, %s, %s, %s, %s, %s::jsonb)
"""


class RollingScorer:
    """Maintains a deque per (sensor, metric) and scores against a model map."""

    def __init__(
        self,
        models: dict[tuple[str, str], TrainedModel],
        window_size: int = 24,
        executor: Executor | None = None,
    ) -> None:
        # Key: (sensor_id, metric). Models are keyed the same way.
        self.models = models
        self.window_size = window_size
        self.executor = executor
        self._windows: dict[tuple[str, str], Deque[tuple[float, float]]] = {}

    def _window_for(self, key: tuple[str, str]) -> Deque[tuple[float, float]]:
        w = self._windows.get(key)
        if w is None:
            w = deque(maxlen=self.window_size)
            self._windows[key] = w
        return w

    def observe(
        self,
        *,
        site_id: str,
        sensor_id: str,
        metric: str,
        t_sample: datetime,
        value: float,
    ) -> ScoringResult | None:
        key = (sensor_id, metric)
        window = self._window_for(key)
        window.append((t_sample.timestamp(), value))

        if len(window) < max(3, self.window_size // 4):
            # Not enough data yet for meaningful features.
            return None

        model = self.models.get(key)
        if model is None:
            return None

        feats = extract(window)
        raw_score, is_anomaly = score_against_model(model, feats)
        result = ScoringResult(
            sensor_id=sensor_id,
            metric=metric,
            t_sample=t_sample,
            score=raw_score,
            is_anomaly=is_anomaly,
            features=feats,
        )
        self._persist(site_id, model.model_id, result)
        return result

    def _persist(self, site_id: str, model_id: str, r: ScoringResult) -> None:
        if self.executor is None:
            return

        feature_json = json.dumps(
            dict(zip(FeatureVector.field_names(), r.features.to_list()))
        )

        try:
            self.executor.execute(
                SCORE_INSERT_SQL,
                (
                    r.t_sample, site_id, r.sensor_id, r.metric,
                    model_id, r.score, r.is_anomaly, feature_json,
                ),
            )
            if r.is_anomaly:
                self.executor.execute(
                    EVENT_INSERT_SQL,
                    (
                        site_id, r.sensor_id, r.metric, model_id,
                        r.t_sample, r.score, feature_json,
                    ),
                )
        except Exception:
            log.exception("failed to persist anomaly score for %s/%s",
                          r.sensor_id, r.metric)


# ---------------------------------------------------------------------------
# MQTT payload → scorer adapter
# ---------------------------------------------------------------------------

def observations_from_payload(
    payload: dict,
) -> Iterable[tuple[str, str, str, datetime, float]]:
    """Yield (site, sensor, metric, t_sample, value) per scalar metric."""
    site = payload["site"]
    sensor = payload["sensor"]
    t = datetime.fromisoformat(payload["t_sample"].replace("Z", "+00:00"))
    for metric, v in payload.get("values", {}).items():
        if isinstance(v, (int, float)):
            yield site, sensor, metric, t, float(v)
