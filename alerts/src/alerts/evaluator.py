"""Stateful rule evaluator.

For each (rule, sensor) pair we keep a small state record:

    above_since : datetime  # when the value first crossed the threshold
    fired_at    : datetime | None  # when we emitted the alert (or None)
    last_value  : float

Transitions:

    ENTER       : observed crosses threshold and above_since is None
                  -> store above_since, do NOT fire yet
    PERSIST_OK  : still above after persistence_s
                  -> fire, set fired_at
    SUSTAIN     : already fired, still above (with hysteresis)
                  -> keep silent (the alert remains open)
    RELEASE     : dropped below (threshold * (1 - hysteresis_pct/100)) for
                  direction=above (mirrored for below/absolute)
                  -> clear state; reset everything

Confirmation across sensors (confirm_count > 1) is resolved in the orchestrator
(service.py) because it requires knowledge of N sensors simultaneously.

The evaluator is pure and synchronous: caller feeds in measurements one by one.
This keeps it trivially testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from .rules import Rule


@dataclass
class SensorObservation:
    sensor_id: str
    metric: str
    t_sample: datetime
    value: float
    quality: str


@dataclass
class RuleState:
    """Per-(rule, sensor) state kept between observations."""
    above_since: datetime | None = None
    fired_at: datetime | None = None
    last_value: float | None = None


@dataclass
class FiredEvent:
    rule: Rule
    sensor_id: str
    t_triggered: datetime
    observed: float
    threshold: float


@dataclass
class ResolvedEvent:
    rule: Rule
    sensor_id: str
    t_resolved: datetime


@dataclass
class EvaluationResult:
    fired: list[FiredEvent] = field(default_factory=list)
    resolved: list[ResolvedEvent] = field(default_factory=list)


def _is_threshold_exceeded(direction: str, value: float, threshold: float) -> bool:
    if direction == "above":
        return value > threshold
    if direction == "below":
        return value < threshold
    if direction == "absolute":
        return abs(value) > threshold
    raise ValueError(f"unknown direction: {direction!r}")


def _is_released(
    direction: str, value: float, threshold: float, hysteresis_pct: float
) -> bool:
    """Returns True if the value has recovered beyond the hysteresis band."""
    h = hysteresis_pct / 100.0
    if direction == "above":
        return value <= threshold * (1 - h)
    if direction == "below":
        return value >= threshold * (1 + h)
    if direction == "absolute":
        return abs(value) <= threshold * (1 - h)
    raise ValueError(f"unknown direction: {direction!r}")


class RuleEvaluator:
    """Evaluates rules against observations, keeping state per (rule, sensor).

    thresholds_for(rule, sensor) is a callable that returns a dict like
    {"atencao": 380, "alerta": 420, ...} used when the rule has threshold_ref
    pointing to it. For rules with literal threshold_value this callback is
    not consulted.
    """

    def __init__(
        self,
        rules: Iterable[Rule],
        thresholds_for: callable | None = None,
    ) -> None:
        self._rules = list(rules)
        self._state: dict[tuple[str, str], RuleState] = {}
        self._thresholds_for = thresholds_for or (lambda rule, sensor: {})

    def state_for(self, rule_id: str, sensor_id: str) -> RuleState:
        key = (rule_id, sensor_id)
        if key not in self._state:
            self._state[key] = RuleState()
        return self._state[key]

    def observe(self, obs: SensorObservation) -> EvaluationResult:
        result = EvaluationResult()
        for rule in self._rules:
            if rule.metric != obs.metric:
                continue
            if not rule.matches_sensor(obs.sensor_id):
                continue
            if obs.quality not in rule.require_quality:
                continue

            thresholds = self._thresholds_for(rule, obs.sensor_id)
            try:
                threshold = rule.resolve_threshold(thresholds)
            except (KeyError, ValueError):
                # Missing threshold configuration; skip this rule for this
                # sensor rather than crash the whole pipeline.
                continue

            state = self.state_for(rule.rule_id, obs.sensor_id)
            state.last_value = obs.value

            if _is_threshold_exceeded(rule.direction, obs.value, threshold):
                if state.above_since is None:
                    state.above_since = obs.t_sample
                if state.fired_at is None:
                    elapsed = (obs.t_sample - state.above_since).total_seconds()
                    if elapsed >= rule.persistence_s:
                        state.fired_at = obs.t_sample
                        result.fired.append(
                            FiredEvent(
                                rule=rule,
                                sensor_id=obs.sensor_id,
                                t_triggered=obs.t_sample,
                                observed=obs.value,
                                threshold=threshold,
                            )
                        )
            else:
                # Below threshold. Release only if past hysteresis band AND
                # we had previously fired.
                if state.fired_at is not None and _is_released(
                    rule.direction, obs.value, threshold, rule.hysteresis_pct
                ):
                    result.resolved.append(
                        ResolvedEvent(
                            rule=rule,
                            sensor_id=obs.sensor_id,
                            t_resolved=obs.t_sample,
                        )
                    )
                    state.above_since = None
                    state.fired_at = None
                elif state.fired_at is None:
                    # Just noise below threshold — reset entry timer.
                    state.above_since = None

        return result


# ---------------------------------------------------------------------------
# Confirmation across multiple sensors (confirm_count > 1).
# ---------------------------------------------------------------------------

@dataclass
class ConfirmedFiredEvent:
    rule: Rule
    sensor_ids: list[str]
    t_triggered: datetime
    evidence: list[FiredEvent]


class ConfirmationTracker:
    """Upgrades per-sensor FiredEvents to a group event when confirm_count>1.

    Strategy: keep the last-seen fire time per sensor per rule, and when the
    count of sensors with fires within a sliding window reaches confirm_count,
    emit one group event and remember that the group has fired (to avoid
    duplicates).
    """

    def __init__(self, window_s: int = 300) -> None:
        self.window_s = window_s
        self._recent: dict[str, dict[str, FiredEvent]] = {}  # rule_id -> sensor -> event
        self._group_fired: dict[str, bool] = {}  # rule_id -> already fired this episode

    def observe(self, fired: Iterable[FiredEvent]) -> list[ConfirmedFiredEvent]:
        out: list[ConfirmedFiredEvent] = []
        for ev in fired:
            if ev.rule.confirm_count <= 1:
                continue
            bucket = self._recent.setdefault(ev.rule.rule_id, {})
            bucket[ev.sensor_id] = ev
            # Evict old entries
            now = ev.t_triggered
            fresh = {
                s: e for s, e in bucket.items()
                if (now - e.t_triggered).total_seconds() <= self.window_s
            }
            self._recent[ev.rule.rule_id] = fresh
            if (
                len(fresh) >= ev.rule.confirm_count
                and not self._group_fired.get(ev.rule.rule_id)
            ):
                self._group_fired[ev.rule.rule_id] = True
                out.append(
                    ConfirmedFiredEvent(
                        rule=ev.rule,
                        sensor_ids=sorted(fresh.keys()),
                        t_triggered=now,
                        evidence=list(fresh.values()),
                    )
                )
        return out

    def reset_group(self, rule_id: str) -> None:
        self._group_fired.pop(rule_id, None)
        self._recent.pop(rule_id, None)
