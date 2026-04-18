"""Tests for GraphQL mutations: ackAlert, updateThreshold, issueCommand."""

from __future__ import annotations

import asyncio
import json
from uuid import UUID

from api.auth import AuthContext  # type: ignore
from api.repository import Repository  # type: ignore
from api.schema import schema  # type: ignore

from .fakes import FakeDatabaseClient, FakePublisher


def _ctx(*, roles=("admin", "engineer", "operator"), mfa=True, scope=()):
    return AuthContext(
        user_id="operator-alice",
        email=None,
        roles=frozenset(roles),
        mfa=mfa,
        site_scope=frozenset(scope),
        raw_claims={},
    )


def _execute(
    query: str,
    variables: dict | None = None,
    write=None,
    publisher=None,
    repo=None,
    user_id: str = "operator-alice",
    auth: AuthContext | None = None,
):
    context = {
        "repo": repo or Repository(FakeDatabaseClient()),
        "write": write,
        "publisher": publisher,
        "user_id": user_id,
        "auth": auth if auth is not None else _ctx(),
    }
    return asyncio.run(
        schema.execute(query, variable_values=variables or {}, context_value=context)
    )


# ---------------------------------------------------------------------------
# acknowledgeAlert
# ---------------------------------------------------------------------------

def test_acknowledge_alert_ok():
    write = FakeDatabaseClient()
    event_uuid = UUID("11111111-2222-3333-4444-555555555555")
    write.on(
        "UPDATE geo.alert_event",
        lambda p: [(event_uuid, "site-x", "ALERTA", "2026-04-18T14:10:00Z")],
    )
    write.on("INSERT INTO geo.audit_event", lambda p: [])

    q = """
      mutation($id: String!, $c: String!) {
        acknowledgeAlert(eventId: $id, comment: $c) {
          ok message eventId correlationId
        }
      }
    """
    r = _execute(q, {"id": str(event_uuid), "c": "visited and inspected"},
                 write=write)
    assert r.errors is None, r.errors
    data = r.data["acknowledgeAlert"]
    assert data["ok"] is True
    assert data["eventId"] == str(event_uuid)

    # Writes to alert + audit
    assert write.sql_contains("UPDATE geo.alert_event")
    assert write.sql_contains("INSERT INTO geo.audit_event")


def test_acknowledge_alert_not_found():
    write = FakeDatabaseClient()
    write.on("UPDATE geo.alert_event", lambda p: [])
    q = """
      mutation($id: String!) {
        acknowledgeAlert(eventId: $id, comment: "x") { ok message }
      }
    """
    r = _execute(q, {"id": "nope"}, write=write)
    assert r.errors is None
    assert r.data["acknowledgeAlert"]["ok"] is False
    # No audit write should happen when the alert doesn't exist.
    assert not write.sql_contains("INSERT INTO geo.audit_event")


# ---------------------------------------------------------------------------
# updateThreshold
# ---------------------------------------------------------------------------

def test_update_threshold_closes_previous_and_inserts_new():
    write = FakeDatabaseClient()
    write.on("UPDATE geo.threshold", lambda p: [])
    write.on("INSERT INTO geo.threshold", lambda p: [])
    write.on("INSERT INTO geo.audit_event", lambda p: [])

    q = """
      mutation($i: UpdateThresholdInput!) {
        updateThreshold(input: $i) { ok message correlationId }
      }
    """
    vars = {
        "i": {
            "siteId": "mineradora-x-barragem-norte",
            "sensorId": "pz-sec02-fund-01",
            "metric": "pressure_kpa",
            "levels": {
                "atencao": 380, "alerta": 420,
                "emergenciaN1": 460, "emergenciaN2": 500,
            },
            "direction": "above",
            "hysteresisPct": 5.0,
            "approvalRef": "PSB-BX-REV4",
        },
    }
    r = _execute(q, vars, write=write)
    assert r.errors is None, r.errors
    assert r.data["updateThreshold"]["ok"] is True

    # Three SQL calls: close, insert, audit
    assert write.sql_contains("UPDATE geo.threshold")
    assert write.sql_contains("INSERT INTO geo.threshold")
    assert write.sql_contains("INSERT INTO geo.audit_event")


def test_update_threshold_rejects_non_monotonic():
    write = FakeDatabaseClient()
    q = """
      mutation($i: UpdateThresholdInput!) {
        updateThreshold(input: $i) { ok message }
      }
    """
    vars = {
        "i": {
            "siteId": "s", "sensorId": "pz-1", "metric": "pressure_kpa",
            "levels": {
                "atencao": 500, "alerta": 400,  # inverted
                "emergenciaN1": 600, "emergenciaN2": 700,
            },
            "direction": "above",
            "hysteresisPct": 5.0,
            "approvalRef": "x",
        },
    }
    r = _execute(q, vars, write=write)
    assert r.errors is None
    assert r.data["updateThreshold"]["ok"] is False
    assert "monotonic" in r.data["updateThreshold"]["message"].lower()
    # No writes should have occurred
    assert not write.sql_contains("UPDATE geo.threshold")


# ---------------------------------------------------------------------------
# issueCommand
# ---------------------------------------------------------------------------

def test_issue_command_publishes_and_audits():
    write = FakeDatabaseClient()
    write.on("INSERT INTO geo.audit_event", lambda p: [])
    publisher = FakePublisher()

    q = """
      mutation($i: IssueCommandInput!) {
        issueCommand(input: $i) { ok message correlationId }
      }
    """
    vars = {
        "i": {
            "siteId": "mineradora-x-barragem-norte",
            "gateway": "gw-bx-001",
            "device": "rtu-bx-c1",
            "action": "set_sampling_mode",
            "paramsJson": '{"mode": "ATENCAO"}',
            "ttlS": 600,
        },
    }
    r = _execute(q, vars, write=write, publisher=publisher)
    assert r.errors is None, r.errors
    assert r.data["issueCommand"]["ok"] is True

    # Audited
    assert write.sql_contains("INSERT INTO geo.audit_event")
    # Published
    assert len(publisher.published) == 1
    topic, payload, qos = publisher.published[0]
    assert topic == (
        "cmd/mineradora-x-barragem-norte/gw-bx-001/rtu-bx-c1"
    )
    body = json.loads(payload)
    assert body["schema"] == "geo.command.v1"
    assert body["action"] == "set_sampling_mode"
    assert body["params"] == {"mode": "ATENCAO"}
    assert body["issued_by"] == "operator-alice"


def test_issue_command_rejects_invalid_params_json():
    write = FakeDatabaseClient()
    q = """
      mutation($i: IssueCommandInput!) {
        issueCommand(input: $i) { ok message }
      }
    """
    vars = {
        "i": {
            "siteId": "s", "gateway": "g", "action": "reboot",
            "paramsJson": "not json",
        },
    }
    r = _execute(q, vars, write=write)
    assert r.errors is None
    assert r.data["issueCommand"]["ok"] is False
    assert "invalid params_json" in r.data["issueCommand"]["message"]


# ---------------------------------------------------------------------------
# MFA / role / site scope enforcement
# ---------------------------------------------------------------------------

def test_acknowledge_alert_requires_mfa():
    write = FakeDatabaseClient()
    write.on("UPDATE geo.alert_event", lambda p: [])
    q = """
      mutation($id: String!) {
        acknowledgeAlert(eventId: $id, comment: "x") { ok message }
      }
    """
    r = _execute(
        q, {"id": "e1"}, write=write,
        auth=_ctx(mfa=False),
    )
    # Error surfaces as GraphQL error because the resolver raised.
    assert r.errors is not None
    assert any("MFA required" in str(e) for e in r.errors)
    # No DB writes
    assert not write.sql_contains("UPDATE geo.alert_event")


def test_update_threshold_requires_engineer_role():
    write = FakeDatabaseClient()
    q = """
      mutation($i: UpdateThresholdInput!) {
        updateThreshold(input: $i) { ok message }
      }
    """
    vars = {"i": {
        "siteId": "s", "sensorId": "pz-1", "metric": "pressure_kpa",
        "levels": {"atencao": 1, "alerta": 2, "emergenciaN1": 3, "emergenciaN2": 4},
        "direction": "above", "hysteresisPct": 5.0, "approvalRef": "x",
    }}
    r = _execute(q, vars, write=write, auth=_ctx(roles=("viewer",), mfa=True))
    assert r.errors is not None
    assert any("role 'engineer'" in str(e) for e in r.errors)
    assert not write.sql_contains("UPDATE geo.threshold")


def test_issue_command_requires_site_scope():
    write = FakeDatabaseClient()
    publisher = FakePublisher()
    q = """
      mutation($i: IssueCommandInput!) {
        issueCommand(input: $i) { ok message }
      }
    """
    vars = {"i": {
        "siteId": "mineradora-x-barragem-norte", "gateway": "gw",
        "action": "reboot", "paramsJson": "{}",
    }}
    r = _execute(
        q, vars, write=write, publisher=publisher,
        auth=_ctx(scope=("some-other-site",), mfa=True),
    )
    assert r.errors is not None
    assert any("not in user's scope" in str(e) for e in r.errors)
    # No publish nor audit
    assert len(publisher.published) == 0
    assert not write.sql_contains("INSERT INTO geo.audit_event")


def test_update_threshold_ok_with_engineer_and_scope():
    """Sanity: when the auth context satisfies all guards, the mutation runs."""
    write = FakeDatabaseClient()
    write.on("UPDATE geo.threshold", lambda p: [])
    write.on("INSERT INTO geo.threshold", lambda p: [])
    write.on("INSERT INTO geo.audit_event", lambda p: [])
    q = """
      mutation($i: UpdateThresholdInput!) {
        updateThreshold(input: $i) { ok message }
      }
    """
    vars = {"i": {
        "siteId": "mineradora-x-barragem-norte", "sensorId": "pz-1",
        "metric": "pressure_kpa",
        "levels": {"atencao": 1, "alerta": 2, "emergenciaN1": 3, "emergenciaN2": 4},
        "direction": "above", "hysteresisPct": 5.0, "approvalRef": "PSB-X",
    }}
    r = _execute(
        q, vars, write=write,
        auth=_ctx(
            roles=("engineer",),
            mfa=True,
            scope=("mineradora-x-barragem-norte",),
        ),
    )
    assert r.errors is None, r.errors
    assert r.data["updateThreshold"]["ok"] is True
