"""Channel-specific notifiers.

Each notifier implements:
    def send(target: str, alert_payload: dict) -> tuple[bool, str | None]

Returning (True, None) on success, (False, error_message) on failure. Pure
functions where possible so the orchestrator is simple to test.

For SMS/voice we provide stubs that match a Twilio-style API shape but
record the call instead of hitting the network. Real adapters (Twilio,
Zenvia, Total Voice, etc.) plug in here without changing callers.
"""

from __future__ import annotations

import json
import logging
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any, Callable, Protocol


log = logging.getLogger(__name__)


class Notifier(Protocol):
    channel: str
    def send(
        self, target: str, alert_payload: dict[str, Any]
    ) -> tuple[bool, str | None]: ...


# ---------------------------------------------------------------------------
# Email via SMTP
# ---------------------------------------------------------------------------

@dataclass
class SmtpConfig:
    host: str
    port: int = 587
    username: str | None = None
    password: str | None = None
    use_tls: bool = True
    from_addr: str = "alerts@autodata.example.com"


class EmailNotifier:
    channel = "email"

    def __init__(
        self,
        cfg: SmtpConfig,
        smtp_factory: Callable | None = None,  # for tests
    ) -> None:
        self.cfg = cfg
        self.smtp_factory = smtp_factory or (
            lambda: smtplib.SMTP(cfg.host, cfg.port, timeout=10)
        )

    def send(
        self, target: str, alert_payload: dict[str, Any]
    ) -> tuple[bool, str | None]:
        msg = EmailMessage()
        level = alert_payload.get("level", "ALERT")
        site = alert_payload.get("site", "?")
        rule = alert_payload.get("rule_id", "?")
        summary = (alert_payload.get("evidence") or {}).get("summary", "")

        msg["Subject"] = f"[{level}] {site} — {rule}"
        msg["From"] = self.cfg.from_addr
        msg["To"] = target
        msg.set_content(
            f"Level: {level}\n"
            f"Site: {site}\n"
            f"Rule: {rule}\n"
            f"Sensors: {', '.join(alert_payload.get('sensors', []))}\n"
            f"Triggered: {alert_payload.get('t_triggered', '?')}\n\n"
            f"{summary}\n\n"
            f"Full payload:\n{json.dumps(alert_payload, indent=2, ensure_ascii=False)}"
        )

        try:
            smtp = self.smtp_factory()
            try:
                if self.cfg.use_tls:
                    smtp.starttls()
                if self.cfg.username:
                    smtp.login(self.cfg.username, self.cfg.password or "")
                smtp.send_message(msg)
            finally:
                try:
                    smtp.quit()
                except Exception:
                    pass
            return True, None
        except Exception as e:
            return False, f"smtp error: {e}"


# ---------------------------------------------------------------------------
# Webhook (HTTP POST JSON)
# ---------------------------------------------------------------------------

class WebhookNotifier:
    channel = "webhook"

    def __init__(self, http_client: Callable | None = None) -> None:
        import urllib.request
        self._opener = http_client or urllib.request.urlopen

    def send(
        self, target: str, alert_payload: dict[str, Any]
    ) -> tuple[bool, str | None]:
        import urllib.error
        import urllib.request

        body = json.dumps(alert_payload).encode("utf-8")
        req = urllib.request.Request(
            target,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Autodata-Notifier/0.1",
                "X-Autodata-Alert-Level": alert_payload.get("level", ""),
            },
            method="POST",
        )
        try:
            resp = self._opener(req, timeout=10)
            status = getattr(resp, "status", 0) or getattr(resp, "code", 0)
            if 200 <= status < 300:
                return True, None
            return False, f"http {status}"
        except urllib.error.HTTPError as e:
            return False, f"http {e.code}: {e.reason}"
        except Exception as e:
            return False, f"webhook error: {e}"


# ---------------------------------------------------------------------------
# SMS (stub matching Twilio REST shape)
# ---------------------------------------------------------------------------

@dataclass
class StubSmsProvider:
    sent: list[tuple[str, str]] = field(default_factory=list)
    fail_next: bool = False

    def send(self, to: str, body: str) -> tuple[bool, str | None]:
        if self.fail_next:
            self.fail_next = False
            return False, "stub provider forced failure"
        self.sent.append((to, body))
        return True, None


class SmsNotifier:
    channel = "sms"

    def __init__(self, provider=None) -> None:
        self.provider = provider or StubSmsProvider()

    def send(
        self, target: str, alert_payload: dict[str, Any]
    ) -> tuple[bool, str | None]:
        level = alert_payload.get("level", "ALERT")
        site = alert_payload.get("site", "?")
        summary = (alert_payload.get("evidence") or {}).get("summary", "")
        body = f"[{level}] {site}: {summary[:120]}"
        return self.provider.send(target, body)


# ---------------------------------------------------------------------------
# Voice (stub; real impl calls Twilio Programmable Voice)
# ---------------------------------------------------------------------------

@dataclass
class StubVoiceProvider:
    calls: list[tuple[str, str]] = field(default_factory=list)
    fail_next: bool = False

    def call(self, to: str, script: str) -> tuple[bool, str | None]:
        if self.fail_next:
            self.fail_next = False
            return False, "stub provider forced failure"
        self.calls.append((to, script))
        return True, None


class VoiceNotifier:
    channel = "voice"

    def __init__(self, provider=None) -> None:
        self.provider = provider or StubVoiceProvider()

    def send(
        self, target: str, alert_payload: dict[str, Any]
    ) -> tuple[bool, str | None]:
        level = alert_payload.get("level", "ALERT")
        site = alert_payload.get("site", "?")
        rule = alert_payload.get("rule_id", "?")
        script = (
            f"Atenção, alerta nível {level.replace('_', ' ')} na barragem {site}. "
            f"Regra {rule} foi acionada. Verifique o painel imediatamente."
        )
        return self.provider.call(target, script)
