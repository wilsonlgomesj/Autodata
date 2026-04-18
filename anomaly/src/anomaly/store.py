"""Persistence adapter for anomaly_model rows in Postgres."""

from __future__ import annotations

import json
from typing import Any

from .model import TrainedModel, deserialize_model, serialize_model


INSERT_MODEL_SQL = """
INSERT INTO geo.anomaly_model
  (model_id, site_id, sensor_id, metric, algorithm, params,
   trained_from, trained_to, n_training_samples, model_blob, score_threshold)
VALUES
  (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
ON CONFLICT (model_id) DO UPDATE SET
  params = EXCLUDED.params,
  trained_from = EXCLUDED.trained_from,
  trained_to = EXCLUDED.trained_to,
  n_training_samples = EXCLUDED.n_training_samples,
  model_blob = EXCLUDED.model_blob,
  score_threshold = EXCLUDED.score_threshold,
  active = TRUE
"""

LOAD_ACTIVE_MODELS_SQL = """
SELECT model_id, site_id, sensor_id, metric, algorithm, params,
       trained_from, trained_to, n_training_samples, model_blob,
       score_threshold
FROM geo.anomaly_model
WHERE active = TRUE AND site_id = %s
"""


class ModelStore:
    def __init__(self, executor) -> None:
        self.executor = executor

    def save(self, tm: TrainedModel) -> None:
        blob = serialize_model(tm)
        self.executor.execute(
            INSERT_MODEL_SQL,
            (
                tm.model_id, tm.site_id, tm.sensor_id, tm.metric,
                tm.algorithm, json.dumps(tm.params),
                tm.trained_from, tm.trained_to, tm.n_training_samples,
                blob, tm.score_threshold,
            ),
        )

    def load_active_for_site(self, site_id: str) -> dict[tuple[str, str], TrainedModel]:
        rows = self.executor.fetch_all(LOAD_ACTIVE_MODELS_SQL, (site_id,))
        out: dict[tuple[str, str], TrainedModel] = {}
        for r in rows:
            params = r[5] if isinstance(r[5], dict) else json.loads(r[5])
            tm = deserialize_model(
                bytes(r[9]),
                model_id=r[0], site_id=r[1], sensor_id=r[2], metric=r[3],
                algorithm=r[4], params=params,
                trained_from=str(r[6]), trained_to=str(r[7]),
                n_training_samples=r[8],
                score_threshold=float(r[10]),
            )
            out[(tm.sensor_id, tm.metric)] = tm
        return out
