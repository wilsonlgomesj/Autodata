"""Core alert service: telemetry payload → evaluator → emitter.

Pure, no MQTT dependency. MQTT wiring lives in mqtt_runner.py.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from .emitter import (
    AlertEmitter,
    build_alert_from_confirmed,
    build_alert_from_fired,
)
from .evaluator import ConfirmationTracker, RuleEvaluator, SensorObservation
from .rules import load_rules_from_dir, load_rules_from_file


log = logging.getLogger(__name__)


def parse_t_sample(s: str) -> datetime:
    # geo.telemetry.v1 uses YYYY-MM-DDTHH:MM:SS.mmmZ
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class AlertService:
    def __init__(
        self,
        rules_path: Path,
        evaluator: RuleEvaluator | None = None,
        confirm_tracker: ConfirmationTracker | None = None,
        emitter: AlertEmitter | None = None,
        structure_lookup: Callable | None = None,
    ) -> None:
        if rules_path.is_dir():
            self.ruleset = load_rules_from_dir(rules_path)
        else:
            self.ruleset = load_rules_from_file(rules_path)

        self.evaluator = evaluator or RuleEvaluator(self.ruleset.rules)
        self.confirm = confirm_tracker or ConfirmationTracker()
        self.emitter = emitter
        self.structure_lookup = structure_lookup or (lambda s, sensor: None)

    def observations_from_payload(
        self, payload: dict
    ) -> Iterable[SensorObservation]:
        sensor_id = payload["sensor"]
        t_sample = parse_t_sample(payload["t_sample"])
        quality = payload["quality"]["code"]
        for metric, v in payload["values"].items():
            if isinstance(v, (int, float)):
                yield SensorObservation(
                    sensor_id=sensor_id,
                    metric=metric,
                    t_sample=t_sample,
                    value=float(v),
                    quality=quality,
                )
            # array-valued metrics (DTS) are not evaluated by threshold rules

    def handle_payload(self, payload: dict) -> int:
        site_id = payload["site"]
        emitted = 0
        for obs in self.observations_from_payload(payload):
            result = self.evaluator.observe(obs)
            confirmed = self.confirm.observe(result.fired)

            for ev in result.fired:
                if ev.rule.confirm_count > 1:
                    continue
                if self.emitter is None:
                    continue
                structure = self.structure_lookup(site_id, ev.sensor_id)
                alert = build_alert_from_fired(ev, site_id, structure)
                self.emitter.emit(alert)
                emitted += 1

            for ev in confirmed:
                if self.emitter is None:
                    continue
                structure = self.structure_lookup(
                    site_id,
                    ev.sensor_ids[0] if ev.sensor_ids else None,
                )
                alert = build_alert_from_confirmed(ev, site_id, structure)
                self.emitter.emit(alert)
                emitted += 1
        return emitted
