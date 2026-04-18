"""Tests for route matching: min_level, site scope, rule glob, structure."""

from __future__ import annotations

from notifications.routing import AlertRef, Route, matches, resolve  # type: ignore


def _alert(level="ALERTA", rule="pz-fund-alerta", structure="barragem-principal"):
    return AlertRef(
        msg_id="01HK0000000000000000000001",
        site_id="site-x",
        level=level,
        rule_id=rule,
        structure_id=structure,
    )


def _route(
    min_level="ALERTA", site_id="site-x", channel="email",
    target="ops@example.com", rule_glob=None, structure=None, active=True,
):
    return Route(
        route_id=1, site_id=site_id, min_level=min_level,
        channel=channel, target=target,
        rule_id_glob=rule_glob, structure_id=structure, active=active,
    )


def test_min_level_threshold():
    r = _route(min_level="ALERTA")
    assert matches(r, _alert(level="ALERTA"))
    assert matches(r, _alert(level="EMERGENCIA_N1"))
    assert not matches(r, _alert(level="ATENCAO"))


def test_site_scope():
    r = _route(site_id="site-x")
    assert matches(r, _alert())
    other = AlertRef(
        msg_id="x", site_id="site-y", level="ALERTA",
        rule_id="pz-fund-alerta", structure_id=None,
    )
    assert not matches(r, other)


def test_global_route_matches_any_site():
    r = _route(site_id=None)
    assert matches(r, _alert())


def test_rule_glob_filter():
    r = _route(rule_glob="pz-*")
    assert matches(r, _alert(rule="pz-fund-alerta"))
    assert not matches(r, _alert(rule="ipi-crista-alerta"))


def test_structure_filter():
    r = _route(structure="barragem-principal")
    assert matches(r, _alert(structure="barragem-principal"))
    assert not matches(r, _alert(structure="dique-aux"))


def test_inactive_route_never_matches():
    r = _route(active=False)
    assert not matches(r, _alert())


def test_resolve_multiple():
    a = _alert(level="EMERGENCIA_N2")
    routes = [
        _route(min_level="ATENCAO", channel="email", target="ops@x.com"),
        _route(min_level="ALERTA", channel="sms", target="+55..."),
        _route(min_level="EMERGENCIA_N1", channel="voice", target="+55..."),
        _route(min_level="EMERGENCIA_N1", channel="webhook",
               target="https://anm.gov.br/hook", rule_glob="pz-*"),
    ]
    matched = resolve(routes, a)
    assert len(matched) == 4
    channels = {r.channel for r in matched}
    assert channels == {"email", "sms", "voice", "webhook"}
