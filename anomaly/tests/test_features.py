"""Tests for feature extraction."""

from __future__ import annotations

from anomaly.features import FeatureVector, extract  # type: ignore


def test_empty_window_returns_zero_vector():
    f = extract([])
    assert f.n == 0
    assert f.mean == 0


def test_single_sample_has_no_std_or_slope():
    f = extract([(0.0, 42.0)])
    assert f.n == 1
    assert f.mean == 42.0
    assert f.std == 0.0
    assert f.slope_per_minute == 0.0
    assert f.last_value == 42.0


def test_linear_rising_series_has_positive_slope():
    samples = [(i * 60, 10.0 + 0.5 * i) for i in range(10)]
    f = extract(samples)
    # 0.5 units per minute exactly
    assert abs(f.slope_per_minute - 0.5) < 0.01
    assert f.delta_window == 0.5 * 9


def test_step_change_shows_in_max_abs_step():
    samples = [(i, 10.0) for i in range(5)] + [(5, 50.0)] + [(6, 50.0)]
    f = extract(samples)
    assert f.max_abs_step >= 40


def test_feature_vector_to_list_matches_field_names():
    f = extract([(i, 1.0 * i) for i in range(5)])
    assert len(f.to_list()) == len(FeatureVector.field_names())


def test_residual_large_for_outlier_last():
    # 10 stable samples then a big spike. The spike itself inflates the
    # window's std, so the residual-in-sigma bound is softer than a pure
    # outlier check; >2.5 is meaningful and robust.
    samples = [(i, 100.0 + 0.1 * (i % 3)) for i in range(10)]
    samples.append((10, 500.0))
    f = extract(samples)
    assert f.abs_residual_last > 2.5


def test_feature_vector_fixed_length():
    # Stable across window sizes
    a = extract([(i, 1.0) for i in range(3)])
    b = extract([(i, 1.0) for i in range(100)])
    assert len(a.to_list()) == len(b.to_list())
