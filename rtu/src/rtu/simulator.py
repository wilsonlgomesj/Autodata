"""Synthetic sensor data generator — drives RTU test runs.

Produces values with deterministic baseline + gaussian noise + optional
drift to exercise threshold rules (e.g., slow rise over an hour).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable


@dataclass
class SensorProfile:
    """Describes how a simulated sensor's value behaves over time."""
    sensor_id: str
    sensor_type: str
    metric_baselines: dict[str, float]
    metric_noise_sigma: dict[str, float]
    metric_drift_per_s: dict[str, float]  # linear drift, units/s

    def values_at(self, t: datetime, rng: random.Random) -> dict[str, float]:
        t_epoch = t.timestamp()
        out: dict[str, float] = {}
        for metric, base in self.metric_baselines.items():
            drift = self.metric_drift_per_s.get(metric, 0.0) * t_epoch
            noise = rng.gauss(0.0, self.metric_noise_sigma.get(metric, 0.0))
            out[metric] = base + drift + noise
        return out


PIEZOMETER_VW = SensorProfile(
    sensor_id="pz-sec02-fund-01",
    sensor_type="piezometer_vw",
    metric_baselines={
        "pressure_kpa": 312.0,
        "frequency_hz": 2345.0,
        "temp_c": 25.0,
    },
    metric_noise_sigma={
        "pressure_kpa": 0.5,
        "frequency_hz": 1.0,
        "temp_c": 0.2,
    },
    metric_drift_per_s={},
)


RAIN_GAUGE = SensorProfile(
    sensor_id="rain-crista-01",
    sensor_type="rain_gauge_tipping",
    metric_baselines={"rainfall_mm": 0.0, "cumulative_mm": 0.0},
    metric_noise_sigma={},
    metric_drift_per_s={},
)


def iter_samples(
    profile: SensorProfile,
    start: datetime,
    interval: timedelta,
    count: int,
    seed: int = 42,
) -> Iterable[tuple[datetime, dict[str, float]]]:
    rng = random.Random(seed)
    for i in range(count):
        t = start + interval * i
        yield t, profile.values_at(t, rng)
