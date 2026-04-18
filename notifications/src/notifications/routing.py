"""Route resolution: given an alert, return the list of (channel, target)
pairs that should receive it.

Encapsulates the filter logic (min_level, rule glob, structure match) so it
is unit-testable in isolation from any actual notifier.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Iterable


_LEVEL_RANK = {
    "NORMAL": 0,
    "ATENCAO": 1,
    "ALERTA": 2,
    "EMERGENCIA_N1": 3,
    "EMERGENCIA_N2": 4,
}


@dataclass(frozen=True)
class Route:
    route_id: int
    site_id: str | None       # None = global
    min_level: str
    channel: str
    target: str
    display_name: str | None = None
    rule_id_glob: str | None = None
    structure_id: str | None = None
    active: bool = True


@dataclass(frozen=True)
class AlertRef:
    msg_id: str
    site_id: str
    level: str
    rule_id: str
    structure_id: str | None


def matches(route: Route, alert: AlertRef) -> bool:
    if not route.active:
        return False
    if route.site_id is not None and route.site_id != alert.site_id:
        return False
    if _LEVEL_RANK.get(alert.level, -1) < _LEVEL_RANK.get(route.min_level, 99):
        return False
    if route.rule_id_glob and not fnmatch.fnmatchcase(
        alert.rule_id, route.rule_id_glob
    ):
        return False
    if route.structure_id and route.structure_id != alert.structure_id:
        return False
    return True


def resolve(routes: Iterable[Route], alert: AlertRef) -> list[Route]:
    return [r for r in routes if matches(r, alert)]
