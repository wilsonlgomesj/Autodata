"""Rule model and loader.

Rules are declarative YAML, versioned in Git, reviewed via PR. This module
parses them into typed objects and validates internal consistency. The format
mirrors the samples in docs/conventions.md and the architecture document.

Design notes:
- sensor_match is either an exact id or a glob ("pz-*-fund-*").
- Persistence, hysteresis, and confirmation count are the three anti-false-
  positive mechanisms described in the architecture; implemented in evaluator.py.
- "direction" encodes how to compare observed against threshold:
    above     : fires when observed > threshold
    below     : fires when observed < threshold
    absolute  : fires when |observed| > threshold (useful for tilt)
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


ALLOWED_LEVELS = ("ATENCAO", "ALERTA", "EMERGENCIA_N1", "EMERGENCIA_N2")
ALLOWED_DIRECTIONS = ("above", "below", "absolute")
ALLOWED_ACTIONS = frozenset(
    [
        "email", "sms", "voice", "push", "webhook",
        "teams", "slack", "siren", "increase_sampling",
        "create_incident", "acionar_paebm",
    ]
)

_SEMVER_RE = re.compile(r"^v\d+\.\d+\.\d+$")
_DURATION_RE = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")


def parse_iso8601_duration_seconds(d: str) -> int:
    """Tiny subset of ISO 8601 durations: PTnH nM nS. Good enough for rules."""
    m = _DURATION_RE.match(d)
    if not m:
        raise ValueError(f"invalid ISO-8601 duration: {d!r}")
    h, m_, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + m_ * 60 + s


@dataclass(frozen=True)
class Rule:
    rule_id: str
    version: str
    description: str
    level: str
    site_id: str | None

    # Targeting
    sensor_match: str  # exact id or glob
    metric: str

    # Comparison
    direction: str
    threshold_value: float | None
    threshold_ref: str | None  # e.g., "threshold.alerta"

    # Anti-false-positive
    persistence_s: int
    hysteresis_pct: float
    require_quality: tuple[str, ...]
    confirm_count: int  # >=1; 1 disables confirmation

    actions: tuple[str, ...]

    def matches_sensor(self, sensor_id: str) -> bool:
        if self.sensor_match == sensor_id:
            return True
        return fnmatch.fnmatchcase(sensor_id, self.sensor_match)

    def resolve_threshold(self, thresholds: dict[str, float]) -> float:
        """Return the numeric threshold to compare against.

        If the rule declares `threshold_ref` like "threshold.alerta", look it up
        in the provided map (typically from the `threshold` table).
        """
        if self.threshold_value is not None:
            return self.threshold_value
        if self.threshold_ref is None:
            raise ValueError(f"rule {self.rule_id}: no threshold specified")
        ref = self.threshold_ref
        if ref.startswith("threshold."):
            key = ref.split(".", 1)[1]
            if key not in thresholds:
                raise KeyError(
                    f"rule {self.rule_id}: threshold {key!r} not available"
                )
            return thresholds[key]
        raise ValueError(f"rule {self.rule_id}: unknown ref {ref!r}")


@dataclass
class RuleSet:
    rules: list[Rule] = field(default_factory=list)

    def for_sensor_metric(self, sensor_id: str, metric: str) -> list[Rule]:
        return [
            r for r in self.rules
            if r.metric == metric and r.matches_sensor(sensor_id)
        ]


def _require(d: dict, key: str, where: str) -> Any:
    if key not in d:
        raise ValueError(f"{where}: missing required key {key!r}")
    return d[key]


def parse_rule(raw: dict, source: str) -> Rule:
    rid = _require(raw, "rule_id", source)
    version = _require(raw, "version", source)
    if not _SEMVER_RE.match(version):
        raise ValueError(f"{source}: rule {rid} version must be semver vX.Y.Z")

    level = _require(raw, "level", source)
    if level not in ALLOWED_LEVELS:
        raise ValueError(
            f"{source}: rule {rid} invalid level {level!r} (allowed {ALLOWED_LEVELS})"
        )

    match = _require(raw, "match", source)
    sensor_match = _require(match, "sensor", f"{source}:{rid}.match")
    metric = _require(match, "metric", f"{source}:{rid}.match")

    cond = _require(raw, "when", source)
    direction = _require(cond, "direction", f"{source}:{rid}.when")
    if direction not in ALLOWED_DIRECTIONS:
        raise ValueError(
            f"{source}: rule {rid} invalid direction {direction!r}"
        )

    threshold_value = cond.get("value")
    threshold_ref = cond.get("ref")
    if (threshold_value is None) == (threshold_ref is None):
        raise ValueError(
            f"{source}: rule {rid} must set exactly one of when.value or when.ref"
        )

    persistence = cond.get("persistence", "PT0S")
    persistence_s = parse_iso8601_duration_seconds(persistence)

    hysteresis_pct = float(cond.get("hysteresis_pct", 0.0))

    require_quality = tuple(
        cond.get("require_quality", ["GOOD"])
    )

    confirm_count = int(cond.get("confirm_count", 1))
    if confirm_count < 1:
        raise ValueError(f"{source}: rule {rid} confirm_count must be >= 1")

    actions = tuple(raw.get("actions", []))
    unknown = set(actions) - ALLOWED_ACTIONS
    if unknown:
        raise ValueError(
            f"{source}: rule {rid} unknown actions: {sorted(unknown)}"
        )

    return Rule(
        rule_id=rid,
        version=version,
        description=raw.get("description", ""),
        level=level,
        site_id=raw.get("site"),
        sensor_match=sensor_match,
        metric=metric,
        direction=direction,
        threshold_value=float(threshold_value) if threshold_value is not None else None,
        threshold_ref=threshold_ref,
        persistence_s=persistence_s,
        hysteresis_pct=hysteresis_pct,
        require_quality=require_quality,
        confirm_count=confirm_count,
        actions=actions,
    )


def load_rules_from_file(path: Path) -> RuleSet:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or "rules" not in data:
        raise ValueError(f"{path}: top-level must be an object with 'rules' key")

    rules = [parse_rule(r, str(path)) for r in data["rules"]]

    # Uniqueness check
    seen: set[str] = set()
    for r in rules:
        if r.rule_id in seen:
            raise ValueError(f"{path}: duplicate rule_id {r.rule_id!r}")
        seen.add(r.rule_id)

    return RuleSet(rules=rules)


def load_rules_from_dir(path: Path) -> RuleSet:
    rules: list[Rule] = []
    seen: set[str] = set()
    for p in sorted(path.glob("*.yaml")) + sorted(path.glob("*.yml")):
        rs = load_rules_from_file(p)
        for r in rs.rules:
            if r.rule_id in seen:
                raise ValueError(f"duplicate rule_id across files: {r.rule_id}")
            seen.add(r.rule_id)
            rules.append(r)
    return RuleSet(rules=rules)
