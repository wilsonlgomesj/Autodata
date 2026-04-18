#!/usr/bin/env python3
"""Publish synthetic telemetry to trigger alerts for demo purposes.

Assumes the dev stack is running (docker compose up) with:
  - MQTT broker exposed on localhost:1883
  - REQUIRE_SIGNATURE=false on the ingestion (dev default)

Scenarios:

  emergency   TWO PZ fundação sensors above 500 kPa simultaneously.
              Fires rule `pz-emergencia-confirmado` IMMEDIATELY because
              persistence=PT0S and confirm_count=2. Best scenario for a
              live demo — alert appears in the Alerts page within seconds,
              notification shows up in MailHog, Grafana annotation.

  alert       Single PZ above 420 kPa (alerta threshold). Fires
              `pz-fund-alerta` after PT30M persistence. For a shorter demo
              edit alerts/rules/barragem_x.yaml and set persistence: PT10S.

  attention   Single PZ above 380 kPa (atencao threshold). Persistence 1h.

  normal      Baseline with tiny noise around 312 kPa. Useful for proving
              the threshold bands without firing anything.

Usage:
  python3 tools/demo_trigger.py                 # default: emergency
  python3 tools/demo_trigger.py alert --repeat 10
  python3 tools/demo_trigger.py normal --host broker.example.com
"""

from __future__ import annotations

import argparse
import json
import random
import secrets
import sys
import time
from datetime import datetime, timezone

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print(
        "paho-mqtt is not installed. Run: pip install paho-mqtt",
        file=sys.stderr,
    )
    sys.exit(1)


SITE = "mineradora-x-barragem-norte"
GATEWAY = "gw-bx-001"

_ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _ulid() -> str:
    return "".join(secrets.choice(_ULID_ALPHABET) for _ in range(26))


def _rfc3339() -> str:
    t = datetime.now(timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def _payload(sensor_id: str, device: str, pressure: float, seq: int) -> dict:
    return {
        "schema": "geo.telemetry.v1",
        "msg_id": _ulid(),
        "site": SITE,
        "gateway": GATEWAY,
        "device": device,
        "sensor": sensor_id,
        "sensor_type": "piezometer_vw",
        "t_sample": _rfc3339(),
        "t_ingest": None,
        "seq": seq,
        "values": {
            "pressure_kpa": pressure,
            "frequency_hz": 2800.0 if pressure > 400 else 2345.0,
            "temp_c": 25.5,
        },
        "quality": {"code": "GOOD", "flags": []},
        "firmware": "demo-trigger",
        # sig matches the regex (^ed25519:[A-Za-z0-9+/=]{80,100}$) but is
        # not cryptographically valid. REQUIRE_SIGNATURE=false in dev
        # lets the ingestion accept it.
        "sig": "ed25519:" + "A" * 86 + "==",
    }


def _topic(sensor: str, device: str) -> str:
    return f"tel/{SITE}/{GATEWAY}/{device}/{sensor}/meas"


def _publish(client, sensor: str, device: str, value: float, seq: int) -> None:
    body = _payload(sensor, device, value, seq)
    topic = _topic(sensor, device)
    info = client.publish(topic, json.dumps(body), qos=1)
    info.wait_for_publish(timeout=5)
    print(f"  → {sensor:24s} {value:6.1f} kPa  topic={topic}")


SCENARIOS = {
    "emergency": {
        "description": (
            "TWO PZ fundação sensors above 500 kPa simultaneously.\n"
            "Fires pz-emergencia-confirmado IMMEDIATELY (persistence=PT0S, confirm=2)."
        ),
        "sensors": [
            ("pz-sec02-fund-01", "rtu-bx-c1", 525.0),
            ("pz-sec03-fund-01", "rtu-bx-d1", 512.0),
        ],
    },
    "alert": {
        "description": (
            "Single PZ above 420 kPa (alerta threshold).\n"
            "Fires pz-fund-alerta after PT30M persistence. For faster demo\n"
            "edit alerts/rules/barragem_x.yaml and set persistence: PT10S."
        ),
        "sensors": [("pz-sec02-fund-01", "rtu-bx-c1", 432.0)],
    },
    "attention": {
        "description": (
            "Single PZ above 380 kPa (atencao threshold, persistence=1h)."
        ),
        "sensors": [("pz-sec02-fund-01", "rtu-bx-c1", 395.0)],
    },
    "normal": {
        "description": "Baseline noise around 312 kPa.",
        "sensors": [("pz-sec02-fund-01", "rtu-bx-c1", 312.0)],
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "scenario", nargs="?", default="emergency",
        choices=list(SCENARIOS.keys()),
    )
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()

    scenario = SCENARIOS[args.scenario]
    print(f"=== scenario: {args.scenario} ===")
    print(scenario["description"])
    print(f"connecting to mqtt://{args.host}:{args.port}")
    print()

    client = mqtt.Client(client_id=f"demo-trigger-{secrets.token_hex(4)}")
    try:
        client.connect(args.host, args.port, keepalive=30)
    except Exception as e:
        print(f"MQTT connect failed: {e}", file=sys.stderr)
        print("Is the stack running? Try: make demo-status", file=sys.stderr)
        return 1

    client.loop_start()
    try:
        seq = int(time.time()) % 1_000_000
        for r in range(args.repeat):
            for sensor_id, device, base in scenario["sensors"]:
                # Jitter the value by ±1 kPa so quality checks don't flag it.
                value = base + random.uniform(-1.0, 1.0)
                seq += 1
                _publish(client, sensor_id, device, value, seq)
            if r < args.repeat - 1:
                time.sleep(args.interval)
    finally:
        client.loop_stop()
        client.disconnect()

    print()
    print("Published.")
    if args.scenario == "emergency":
        print("Expect an EMERGENCIA_N2 alert within seconds.")
    elif args.scenario == "alert":
        print("Expect an ALERTA after persistence window elapses.")
    print()
    print("Check:")
    print("  Frontend Alerts page    http://localhost:8082/alerts")
    print("  MailHog (emails)        http://localhost:8025")
    print("  Grafana dashboard       http://localhost:3000")
    return 0


if __name__ == "__main__":
    sys.exit(main())
