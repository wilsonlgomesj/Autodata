"""End-to-end dispatcher tests using FakeExecutor + stub notifiers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from notifications.dispatcher import Dispatcher  # type: ignore
from notifications.notifiers import (  # type: ignore
    SmsNotifier, StubSmsProvider, StubVoiceProvider, VoiceNotifier,
    WebhookNotifier,
)


@dataclass
class FakeExecutor:
    route_rows: list = field(default_factory=list)
    dispatch_calls: list = field(default_factory=list)

    def execute(self, sql, params):
        if "notification_dispatch" in sql:
            self.dispatch_calls.append(params)
        return 1

    def fetch_all(self, sql, params):
        if "notification_route" in sql:
            # params is (site_id,) — return rows filtered by scope
            site = params[0]
            return [r for r in self.route_rows
                    if r[1] is None or r[1] == site]
        return []


def _route_row(route_id, site_id, min_level, channel, target,
               rule_glob=None, structure=None, active=True):
    return (
        route_id, site_id, min_level, channel, target,
        None,  # display_name
        rule_glob, structure, active,
    )


ALERT = {
    "schema": "geo.alert.v1",
    "msg_id": "01HK" + "0" * 22,
    "site": "site-x",
    "structure": "barragem-principal",
    "level": "ALERTA",
    "rule_id": "pz-fund-alerta",
    "rule_version": "v1.0.0",
    "t_triggered": "2026-04-18T14:10:00.000Z",
    "sensors": ["pz-sec02-fund-01"],
    "evidence": {"summary": "alert summary", "samples": []},
}


def _dispatcher_with_routes(rows):
    executor = FakeExecutor(route_rows=rows)
    sms_provider = StubSmsProvider()
    voice_provider = StubVoiceProvider()
    notifiers = {
        "sms": SmsNotifier(provider=sms_provider),
        "voice": VoiceNotifier(provider=voice_provider),
        "webhook": WebhookNotifier(
            http_client=lambda req, timeout=0: type("R", (), {"status": 200})()
        ),
    }
    return Dispatcher(executor, notifiers), executor, sms_provider, voice_provider


def test_dispatcher_sends_to_every_matching_route():
    rows = [
        _route_row(1, "site-x", "ATENCAO", "sms", "+55..."),
        _route_row(2, None, "ALERTA", "webhook", "https://hook"),
        _route_row(3, "site-x", "EMERGENCIA_N1", "voice", "+55..."),  # below
    ]
    disp, executor, sms, voice = _dispatcher_with_routes(rows)
    result = disp.dispatch(ALERT)

    assert result.sent == 2  # sms + webhook; voice filtered by min_level
    assert result.failed == 0
    assert len(sms.sent) == 1
    assert len(voice.calls) == 0
    # Two dispatch records written
    assert len(executor.dispatch_calls) == 2


def test_dispatcher_idempotency_sql_uses_unique_conflict():
    rows = [_route_row(1, "site-x", "ATENCAO", "sms", "+55...")]
    disp, executor, *_ = _dispatcher_with_routes(rows)
    disp.dispatch(ALERT)
    # The SQL insert string must carry ON CONFLICT clause.
    from notifications.dispatcher import DISPATCH_INSERT_SQL  # type: ignore
    assert "ON CONFLICT" in DISPATCH_INSERT_SQL
    assert "(alert_msg_id, route_id, channel)" in DISPATCH_INSERT_SQL


def test_dispatcher_records_failure_without_stopping_others():
    rows = [
        _route_row(1, "site-x", "ATENCAO", "sms", "+55..."),
        _route_row(2, "site-x", "ATENCAO", "voice", "+55..."),
    ]
    disp, executor, sms, voice = _dispatcher_with_routes(rows)
    # Force SMS failure
    sms.fail_next = True
    result = disp.dispatch(ALERT)
    assert result.attempted == 2
    assert result.failed == 1
    assert result.sent == 1
    # Both dispatch rows recorded regardless of success
    assert len(executor.dispatch_calls) == 2
    # The sent status is carried in the DB row (params index 6 in SQL schema)
    statuses = [row[6] for row in executor.dispatch_calls]
    assert sorted(statuses) == ["failed", "sent"]


def test_dispatcher_handles_unknown_channel_gracefully():
    rows = [_route_row(1, "site-x", "ATENCAO", "teams", "https://teams/hook")]
    disp, executor, *_ = _dispatcher_with_routes(rows)
    result = disp.dispatch(ALERT)
    assert result.failed == 1
    assert result.sent == 0
    # Still recorded in DB
    assert len(executor.dispatch_calls) == 1
    assert executor.dispatch_calls[0][6] == "failed"
