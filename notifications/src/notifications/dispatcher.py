"""Dispatcher: for each incoming alert, resolve routes and send via each
channel's notifier, persisting an idempotent dispatch record.

The dispatch_record is the audit/ops signal (Grafana panel, metric).
Idempotency is enforced at the DB layer via the UNIQUE constraint on
(alert_msg_id, route_id, channel).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Iterable, Protocol

from .notifiers import Notifier
from .routing import AlertRef, Route, resolve


log = logging.getLogger(__name__)


DISPATCH_INSERT_SQL = """
INSERT INTO geo.notification_dispatch
  (alert_msg_id, site_id, level, route_id, channel, target,
   status, error, latency_ms)
VALUES
  (%s, %s, %s::geo.alert_level_enum, %s, %s::geo.notification_channel_enum,
   %s, %s::geo.dispatch_status_enum, %s, %s)
ON CONFLICT (alert_msg_id, route_id, channel) DO NOTHING
"""


ROUTES_QUERY_SQL = """
SELECT route_id, site_id, min_level::text, channel::text, target,
       display_name, rule_id_glob, structure_id, active
FROM geo.notification_route
WHERE active = TRUE
  AND (site_id IS NULL OR site_id = %s)
"""


class Executor(Protocol):
    def execute(self, sql: str, params: tuple[Any, ...]) -> int: ...
    def fetch_all(self, sql: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]: ...


@dataclass
class DispatchResult:
    attempted: int = 0
    sent: int = 0
    failed: int = 0
    suppressed_duplicate: int = 0


class Dispatcher:
    def __init__(
        self,
        executor: Executor,
        notifiers: dict[str, Notifier],
    ) -> None:
        self.executor = executor
        self.notifiers = notifiers

    def _load_routes(self, site_id: str) -> list[Route]:
        rows = self.executor.fetch_all(ROUTES_QUERY_SQL, (site_id,))
        return [
            Route(
                route_id=r[0], site_id=r[1], min_level=r[2], channel=r[3],
                target=r[4], display_name=r[5], rule_id_glob=r[6],
                structure_id=r[7], active=bool(r[8]),
            )
            for r in rows
        ]

    def dispatch(self, alert_payload: dict[str, Any]) -> DispatchResult:
        """Process a single geo.alert.v1 payload. Return per-channel counts."""
        result = DispatchResult()

        alert = AlertRef(
            msg_id=alert_payload["msg_id"],
            site_id=alert_payload["site"],
            level=alert_payload["level"],
            rule_id=alert_payload["rule_id"],
            structure_id=alert_payload.get("structure"),
        )

        routes = self._load_routes(alert.site_id)
        matching = resolve(routes, alert)
        if not matching:
            log.info(
                "no routes matched alert msg_id=%s site=%s level=%s",
                alert.msg_id, alert.site_id, alert.level,
            )
            return result

        for route in matching:
            notifier = self.notifiers.get(route.channel)
            if notifier is None:
                self._record(
                    alert, route, status="failed",
                    error=f"no notifier configured for channel {route.channel}",
                    latency_ms=0,
                )
                result.attempted += 1
                result.failed += 1
                continue

            t0 = time.monotonic()
            try:
                ok, err = notifier.send(route.target, alert_payload)
            except Exception as e:
                log.exception("notifier %s raised", route.channel)
                ok, err = False, f"exception: {e}"
            latency_ms = int((time.monotonic() - t0) * 1000)

            status = "sent" if ok else "failed"
            self._record(alert, route, status=status, error=err,
                         latency_ms=latency_ms)
            result.attempted += 1
            if ok:
                result.sent += 1
            else:
                result.failed += 1

        return result

    def _record(
        self,
        alert: AlertRef,
        route: Route,
        *,
        status: str,
        error: str | None,
        latency_ms: int,
    ) -> None:
        try:
            self.executor.execute(
                DISPATCH_INSERT_SQL,
                (
                    alert.msg_id, alert.site_id, alert.level,
                    route.route_id, route.channel, route.target,
                    status, error, latency_ms,
                ),
            )
        except Exception:
            log.exception(
                "failed to record dispatch msg_id=%s route=%s",
                alert.msg_id, route.route_id,
            )
