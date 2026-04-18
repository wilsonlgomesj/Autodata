"""Feature extraction from a sliding window of telemetry samples.

Design choices:
- Input: a window of (t_sample, value) tuples for a single (sensor, metric).
- Output: a fixed-length feature vector capturing level, variability, trend,
  and step-change behavior. These are the signals that distinguish normal
  piezometer behavior from anomalies (slow drift, step response to rain,
  sensor drop-outs).
- Side-channel features (rainfall co-incidence, temperature) can be added
  later as additional columns; the vector length is stable per (sensor_type,
  metric) so retraining is not required for vocabulary changes.

We implement this with pure numpy/stdlib to keep the service trivially
testable and the Docker image small. scikit-learn is used later for the
model itself; feature extraction has no ML dependency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class FeatureVector:
    """Fixed-length vector with named fields for interpretability."""
    mean: float
    std: float
    min_: float
    max_: float
    range_: float
    last_value: float
    delta_1: float                 # last - prev
    delta_window: float            # last - first
    slope_per_minute: float        # simple linear regression on (t, v)
    max_abs_step: float
    abs_residual_last: float       # |last - mean| / (std + eps)
    n: int                         # sample count in window

    def to_list(self) -> list[float]:
        return [
            self.mean, self.std, self.min_, self.max_, self.range_,
            self.last_value, self.delta_1, self.delta_window,
            self.slope_per_minute, self.max_abs_step,
            self.abs_residual_last, float(self.n),
        ]

    @staticmethod
    def field_names() -> list[str]:
        return [
            "mean", "std", "min", "max", "range",
            "last_value", "delta_1", "delta_window",
            "slope_per_minute", "max_abs_step",
            "abs_residual_last", "n",
        ]


def _linear_slope(ts: Sequence[float], vs: Sequence[float]) -> float:
    n = len(ts)
    if n < 2:
        return 0.0
    mean_t = sum(ts) / n
    mean_v = sum(vs) / n
    num = sum((t - mean_t) * (v - mean_v) for t, v in zip(ts, vs))
    den = sum((t - mean_t) ** 2 for t in ts)
    if den == 0:
        return 0.0
    # result is units / second because ts is in seconds; convert to per-minute
    return (num / den) * 60.0


def extract(samples: Iterable[tuple[float, float]]) -> FeatureVector:
    """Compute a FeatureVector from an iterable of (epoch_seconds, value)."""
    pairs = list(samples)
    n = len(pairs)
    if n == 0:
        # Empty window — return zero vector; caller decides whether to score.
        return FeatureVector(
            mean=0.0, std=0.0, min_=0.0, max_=0.0, range_=0.0,
            last_value=0.0, delta_1=0.0, delta_window=0.0,
            slope_per_minute=0.0, max_abs_step=0.0,
            abs_residual_last=0.0, n=0,
        )

    ts = [p[0] for p in pairs]
    vs = [p[1] for p in pairs]

    mean = sum(vs) / n
    if n > 1:
        var = sum((v - mean) ** 2 for v in vs) / (n - 1)
        std = math.sqrt(var)
    else:
        std = 0.0
    mn, mx = min(vs), max(vs)
    last = vs[-1]
    prev = vs[-2] if n >= 2 else vs[-1]
    first = vs[0]
    delta_1 = last - prev
    delta_window = last - first
    slope = _linear_slope(ts, vs)
    max_abs_step = 0.0
    for a, b in zip(vs, vs[1:]):
        d = abs(b - a)
        if d > max_abs_step:
            max_abs_step = d
    eps = 1e-9
    abs_resid = abs(last - mean) / (std + eps)

    return FeatureVector(
        mean=mean, std=std, min_=mn, max_=mx, range_=mx - mn,
        last_value=last, delta_1=delta_1, delta_window=delta_window,
        slope_per_minute=slope, max_abs_step=max_abs_step,
        abs_residual_last=abs_resid, n=n,
    )
