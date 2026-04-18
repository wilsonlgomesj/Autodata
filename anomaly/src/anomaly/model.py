"""Isolation Forest wrapper for per-(sensor, metric) anomaly detection.

Why Isolation Forest:
  - Fast to train on historical windows (~minutes for a year of PZ data).
  - Works with modest data (~500-5000 samples) without requiring labels.
  - Score is ordinal, so we derive a per-model threshold from the training
    distribution rather than hardcoding.

Alternatives considered:
  - LSTM autoencoder: better for multivariate sequence anomalies but
    needs more data and nontrivial MLOps (GPU training, model drift).
    Listed as future work — features.py already captures the signals an
    LSTM would extract from sliding windows.
  - Statistical (EWMA + 3σ): trivially interpretable but single-variable;
    misses the combined-feature patterns IF captures.
"""

from __future__ import annotations

import base64
import io
import json
import pickle
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
from sklearn.ensemble import IsolationForest

from .features import FeatureVector


@dataclass
class TrainedModel:
    model_id: str
    site_id: str
    sensor_id: str
    metric: str
    algorithm: str
    params: dict[str, Any]
    trained_from: str             # ISO-8601
    trained_to: str
    n_training_samples: int
    score_threshold: float
    # sklearn estimator kept in memory; serialized on persistence
    estimator: IsolationForest


def train_isolation_forest(
    *,
    site_id: str,
    sensor_id: str,
    metric: str,
    training_features: Sequence[FeatureVector],
    contamination: float = 0.01,
    n_estimators: int = 200,
    random_state: int = 42,
    model_id: str | None = None,
    trained_from: str = "",
    trained_to: str = "",
) -> TrainedModel:
    """Train on N windows of historical normal-looking data.

    `training_features` is expected to be a representative sample of the
    sensor's normal regime. Obvious outliers are allowed in up to
    `contamination` fraction — the IF algorithm handles that.
    """
    if len(training_features) < 50:
        raise ValueError(
            f"need at least 50 training windows, got {len(training_features)}"
        )
    X = np.array([f.to_list() for f in training_features], dtype=float)
    est = IsolationForest(
        n_estimators=n_estimators,
        contamination=contamination,
        random_state=random_state,
    )
    est.fit(X)

    # score_samples returns the opposite of the outlier score: higher = more
    # normal. Flip sign so higher = more anomalous, more intuitive.
    raw_scores = -est.score_samples(X)
    # Threshold: 99th percentile of training scores as an anomaly boundary
    # once we've accepted `contamination` as the fraction of outliers.
    threshold = float(np.quantile(raw_scores, 1 - contamination))

    return TrainedModel(
        model_id=model_id or f"if-{sensor_id}-{metric}",
        site_id=site_id,
        sensor_id=sensor_id,
        metric=metric,
        algorithm="isolation_forest",
        params={
            "contamination": contamination,
            "n_estimators": n_estimators,
            "random_state": random_state,
            "feature_names": FeatureVector.field_names(),
        },
        trained_from=trained_from,
        trained_to=trained_to,
        n_training_samples=len(training_features),
        score_threshold=threshold,
        estimator=est,
    )


def score(tm: TrainedModel, features: FeatureVector) -> tuple[float, bool]:
    X = np.array([features.to_list()], dtype=float)
    raw = -tm.estimator.score_samples(X)[0]
    return float(raw), bool(raw > tm.score_threshold)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def serialize_model(tm: TrainedModel) -> bytes:
    """Pickle the estimator into bytes. Blob is small for IF (<200kB)."""
    buf = io.BytesIO()
    pickle.dump(tm.estimator, buf)
    return buf.getvalue()


def deserialize_model(
    blob: bytes,
    *,
    model_id: str,
    site_id: str,
    sensor_id: str,
    metric: str,
    params: dict[str, Any],
    trained_from: str,
    trained_to: str,
    n_training_samples: int,
    score_threshold: float,
    algorithm: str = "isolation_forest",
) -> TrainedModel:
    estimator = pickle.loads(blob)
    return TrainedModel(
        model_id=model_id,
        site_id=site_id,
        sensor_id=sensor_id,
        metric=metric,
        algorithm=algorithm,
        params=params,
        trained_from=trained_from,
        trained_to=trained_to,
        n_training_samples=n_training_samples,
        score_threshold=score_threshold,
        estimator=estimator,
    )
