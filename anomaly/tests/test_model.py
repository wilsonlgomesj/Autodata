"""Tests for Isolation Forest training + scoring + serialization.

These tests generate synthetic data instead of hitting Postgres: a stable
piezometer regime + a clearly anomalous window. The IF model must flag the
anomaly without flagging the normal ones.
"""

from __future__ import annotations

import random

import pytest

from anomaly.features import extract  # type: ignore
from anomaly.model import (  # type: ignore
    deserialize_model,
    score,
    serialize_model,
    train_isolation_forest,
)


def _normal_windows(n: int, seed: int = 42):
    """N windows of 24 samples each, ~312 kPa with ±0.5 noise."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        start_t = i * 900
        window = [
            (start_t + s * 15, 312.0 + rng.gauss(0, 0.5))
            for s in range(24)
        ]
        out.append(extract(window))
    return out


def _anomalous_window(kind: str):
    """A window that should look very different from the normal regime."""
    if kind == "spike":
        window = [(s * 15, 312.0 + (0 if s < 20 else 180.0)) for s in range(24)]
    elif kind == "drop_out":
        # Sensor-stuck: value frozen at 0
        window = [(s * 15, 0.0) for s in range(24)]
    elif kind == "drift":
        # Rapid rise from 312 to 450 over the window
        window = [(s * 15, 312.0 + s * 6.0) for s in range(24)]
    else:
        raise ValueError(f"unknown kind {kind}")
    return extract(window)


def test_trains_and_flags_spike():
    training = _normal_windows(400)
    tm = train_isolation_forest(
        site_id="s", sensor_id="pz-1", metric="pressure_kpa",
        training_features=training,
    )
    spike = _anomalous_window("spike")
    raw_score, is_anomaly = score(tm, spike)
    assert is_anomaly is True
    assert raw_score > tm.score_threshold


def test_trains_and_flags_stuck_sensor():
    training = _normal_windows(400)
    tm = train_isolation_forest(
        site_id="s", sensor_id="pz-1", metric="pressure_kpa",
        training_features=training,
    )
    stuck = _anomalous_window("drop_out")
    _, is_anomaly = score(tm, stuck)
    assert is_anomaly is True


def test_trains_and_flags_fast_drift():
    training = _normal_windows(400)
    tm = train_isolation_forest(
        site_id="s", sensor_id="pz-1", metric="pressure_kpa",
        training_features=training,
    )
    drift = _anomalous_window("drift")
    _, is_anomaly = score(tm, drift)
    assert is_anomaly is True


def test_does_not_overflag_normal_windows():
    # Training-set contamination is 1%; hold out a big normal set and confirm
    # we flag at most ~2% of it. Exact rate depends on randomness — we use a
    # loose bound to stay robust.
    training = _normal_windows(400, seed=1)
    tm = train_isolation_forest(
        site_id="s", sensor_id="pz-1", metric="pressure_kpa",
        training_features=training,
    )
    holdout = _normal_windows(500, seed=9999)
    flagged = sum(1 for w in holdout if score(tm, w)[1])
    assert flagged / len(holdout) < 0.05, f"overflagging: {flagged}/{len(holdout)}"


def test_serialize_roundtrip_preserves_scoring():
    training = _normal_windows(200)
    tm = train_isolation_forest(
        site_id="s", sensor_id="pz-1", metric="pressure_kpa",
        training_features=training,
    )
    spike = _anomalous_window("spike")
    s0, _ = score(tm, spike)

    blob = serialize_model(tm)
    tm2 = deserialize_model(
        blob,
        model_id=tm.model_id, site_id=tm.site_id,
        sensor_id=tm.sensor_id, metric=tm.metric,
        params=tm.params,
        trained_from="", trained_to="",
        n_training_samples=tm.n_training_samples,
        score_threshold=tm.score_threshold,
    )
    s1, _ = score(tm2, spike)
    assert abs(s0 - s1) < 1e-9


def test_rejects_tiny_training_set():
    training = _normal_windows(10)
    with pytest.raises(ValueError):
        train_isolation_forest(
            site_id="s", sensor_id="pz-1", metric="pressure_kpa",
            training_features=training,
        )
