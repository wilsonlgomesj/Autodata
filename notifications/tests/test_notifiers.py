"""Tests for channel notifiers: SMS, voice, email, webhook."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from notifications.notifiers import (  # type: ignore
    EmailNotifier, SmsNotifier, SmtpConfig, StubSmsProvider,
    StubVoiceProvider, VoiceNotifier, WebhookNotifier,
)


ALERT = {
    "schema": "geo.alert.v1",
    "msg_id": "01HK" + "0" * 22,
    "site": "mineradora-x-barragem-norte",
    "level": "ALERTA",
    "rule_id": "pz-fund-alerta",
    "rule_version": "v1.0.0",
    "t_triggered": "2026-04-18T14:10:00.000Z",
    "sensors": ["pz-sec02-fund-01"],
    "evidence": {
        "summary": "pz-sec02-fund-01 pressure_kpa=421.5 crossed threshold 420.0",
        "samples": [],
    },
}


# ---------------------------------------------------------------------------
# SMS
# ---------------------------------------------------------------------------

def test_sms_sends_concise_message():
    provider = StubSmsProvider()
    n = SmsNotifier(provider=provider)
    ok, err = n.send("+5531999999999", ALERT)
    assert ok is True
    assert err is None
    assert len(provider.sent) == 1
    target, body = provider.sent[0]
    assert target == "+5531999999999"
    assert "ALERTA" in body
    assert "mineradora-x-barragem-norte" in body
    # Truncated to 120 chars of summary
    assert len(body) <= 200


def test_sms_reports_provider_failure():
    provider = StubSmsProvider(fail_next=True)
    n = SmsNotifier(provider=provider)
    ok, err = n.send("+5531", ALERT)
    assert ok is False
    assert err is not None


# ---------------------------------------------------------------------------
# Voice
# ---------------------------------------------------------------------------

def test_voice_generates_script_and_calls():
    provider = StubVoiceProvider()
    n = VoiceNotifier(provider=provider)
    ok, _ = n.send("+5531999999999", ALERT)
    assert ok is True
    assert len(provider.calls) == 1
    target, script = provider.calls[0]
    assert target == "+5531999999999"
    assert "nível ALERTA" in script or "nivel" in script.lower()
    assert "pz-fund-alerta" in script


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------

class FakeResp:
    def __init__(self, status=200):
        self.status = status


def test_webhook_posts_json_on_success():
    captured = {}

    def fake_open(req, timeout=0):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        captured["body"] = req.data
        captured["method"] = req.get_method()
        return FakeResp(200)

    n = WebhookNotifier(http_client=fake_open)
    ok, err = n.send("https://hook.example.com/alert", ALERT)
    assert ok is True
    assert err is None
    assert captured["url"] == "https://hook.example.com/alert"
    assert captured["method"] == "POST"
    headers_lower = {k.lower(): v for k, v in captured["headers"].items()}
    assert headers_lower.get("content-type") == "application/json"
    assert headers_lower.get("x-autodata-alert-level") == "ALERTA"
    body = json.loads(captured["body"])
    assert body["msg_id"] == ALERT["msg_id"]


def test_webhook_reports_non_2xx():
    def fake_open(req, timeout=0):
        return FakeResp(500)
    n = WebhookNotifier(http_client=fake_open)
    ok, err = n.send("https://hook.example.com/alert", ALERT)
    assert ok is False
    assert "500" in (err or "")


# ---------------------------------------------------------------------------
# Email (fake SMTP)
# ---------------------------------------------------------------------------

@dataclass
class FakeSMTP:
    starttls_called: bool = False
    login_called: bool = False
    messages: list = field(default_factory=list)

    def starttls(self): self.starttls_called = True
    def login(self, u, p): self.login_called = True
    def send_message(self, msg): self.messages.append(msg)
    def quit(self): pass


def test_email_sends_with_expected_subject_and_body():
    fake = FakeSMTP()
    cfg = SmtpConfig(host="localhost", port=1025, from_addr="from@a.com",
                     use_tls=False, username=None, password=None)
    n = EmailNotifier(cfg, smtp_factory=lambda: fake)
    ok, err = n.send("ops@example.com", ALERT)
    assert ok is True
    assert err is None
    assert len(fake.messages) == 1
    msg = fake.messages[0]
    assert msg["To"] == "ops@example.com"
    assert "ALERTA" in msg["Subject"]
    body = msg.get_content()
    assert "pz-fund-alerta" in body
    assert "pz-sec02-fund-01" in body


def test_email_starttls_and_login_when_configured():
    fake = FakeSMTP()
    cfg = SmtpConfig(
        host="smtp.example.com", port=587,
        username="u", password="p", use_tls=True,
    )
    n = EmailNotifier(cfg, smtp_factory=lambda: fake)
    ok, _ = n.send("x@x.com", ALERT)
    assert ok is True
    assert fake.starttls_called is True
    assert fake.login_called is True
