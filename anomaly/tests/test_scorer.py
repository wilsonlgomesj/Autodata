"""Tests for RollingScorer: window maintenance + persistence side effects."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from anomaly.features import extract  # type: ignore
from anomaly.model import train_isolation_forest  # type: ignore
from anomaly.scorer import RollingScorer, observations_from_payload  # type: ignore


@dataclass
class FakeExecutor:
    calls: list[tuple[str, tuple]] = field(default_factory=list)

    def execute(self, sql, params):
        self.calls.append((sql, params))
        return 1


def _normal_windows(n: int, seed: int = 42):
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


def _train():
    return train_isolation_forest(
        site_id="s", sensor_id="pz-1", metric="pressure_kpa",
        training_features=_normal_windows(300),
    )


def test_does_not_score_until_window_warm():
    tm = _train()
    executor = FakeExecutor()
    scorer = RollingScorer({("pz-1", "pressure_kpa"): tm}, window_size=24,
                           executor=executor)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # Push 2 samples — below the warm-up quarter.
    for i in range(2):
        r = scorer.observe(
            site_id="s", sensor_id="pz-1", metric="pressure_kpa",
            t_sample=t0 + timedelta(seconds=i * 15), value=312.0,
        )
        assert r is None
    # No DB writes during warm-up
    assert executor.calls == []


def test_persists_every_score_and_event_on_anomaly():
    tm = _train()
    executor = FakeExecutor()
    scorer = RollingScorer({("pz-1", "pressure_kpa"): tm}, window_size=24,
                           executor=executor)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rng = random.Random(0)

    # Warm up with normal data
    for i in range(24):
        scorer.observe(
            site_id="s", sensor_id="pz-1", metric="pressure_kpa",
            t_sample=t0 + timedelta(seconds=i * 15),
            value=312.0 + rng.gauss(0, 0.3),
        )

    normal_inserts = [c for c in executor.calls
                      if "anomaly_score" in c[0] and "anomaly_event" not in c[0]]
    assert len(normal_inserts) >= 18  # ~24 - warmup(6)

    # Push a clearly anomalous sample
    r = scorer.observe(
        site_id="s", sensor_id="pz-1", metric="pressure_kpa",
        t_sample=t0 + timedelta(minutes=6, seconds=15),
        value=500.0,  # spike well above regime
    )
    # Score should be recorded and an event row inserted
    assert r is not None
    score_rows = [c for c in executor.calls if "INTO geo.anomaly_score" in c[0]]
    event_rows = [c for c in executor.calls if "INTO geo.anomaly_event" in c[0]]
    assert len(score_rows) >= 1
    # At least one event for the spike (and possibly one from drift during warmup)
    assert len(event_rows) >= 1


def test_observations_from_payload_yields_scalar_metrics_only():
    payload = {
        "site": "s",
        "sensor": "pz-1",
        "t_sample": "2026-04-18T13:45:03.123Z",
        "values": {
            "pressure_kpa": 312.4,
            "frequency_hz": 2345.67,
            "temp_c": 25.6,
            "array_metric": [1.0, 2.0, 3.0],  # must be skipped
        },
    }
    observations = list(observations_from_payload(payload))
    metrics = {o[2] for o in observations}
    assert metrics == {"pressure_kpa", "frequency_hz", "temp_c"}


def test_without_executor_scores_but_does_not_persist():
    tm = _train()
    scorer = RollingScorer({("pz-1", "pressure_kpa"): tm}, window_size=12)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(15):
        scorer.observe(
            site_id="s", sensor_id="pz-1", metric="pressure_kpa",
            t_sample=t0 + timedelta(seconds=i * 15), value=312.0,
        )
    # Shouldn't crash without an executor.


def test_unknown_sensor_returns_none():
    tm = _train()
    scorer = RollingScorer({("known", "m"): tm}, window_size=12)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    r = scorer.observe(
        site_id="s", sensor_id="unknown", metric="m",
        t_sample=t0, value=1.0,
    )
    assert r is None
