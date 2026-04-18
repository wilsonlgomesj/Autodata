# Autodata RTU — ESP32 reference firmware

Minimal, contract-compliant RTU firmware for the ESP32 family. Targets the
same Autodata data contract (`geo.telemetry.v1` with Ed25519 signature) as
the Python reference in `rtu/` — the two implementations are byte-for-byte
compatible in the canonical-JSON layer, which is what the signature is
computed over.

## What's here

```
rtu-esp32/
├── platformio.ini          Build targets (esp32dev, native)
├── include/config.h        Site/device identifiers, MQTT endpoint
├── src/main.cpp            Arduino entry points (setup/loop)
├── lib/signing/
│   ├── canonical.h         Canonical JSON (recursive key sort, strip sig/t_ingest)
│   └── ed25519_sign.h      libsodium wrapper + base64 for the sig field
├── lib/buffer/
│   └── flash_buffer.h      LittleFS store-and-forward buffer
└── test/
    ├── test_canonical/     C++ unit test (Unity, runs on host via pio test -e native)
    └── test_canonical_golden.py  Python test that locks the EXPECTED bytes
```

## Build

```bash
# Fetch PlatformIO if needed:
pip install platformio

# Device build + flash:
pio run -e esp32dev -t upload
pio device monitor -b 115200

# Host-side test (no hardware; exercises canonical JSON):
pio test -e native
```

## Cross-platform contract test

The canonical-JSON layer must produce identical bytes on ESP32 and in the
Python reference — otherwise signatures generated on the device won't
verify in the backend.

- `test/test_canonical/test_canonical.cpp` asserts the C++ output matches a
  hardcoded EXPECTED string.
- `test/test_canonical_golden.py` asserts (a) the Python reference produces
  the same EXPECTED string for the same payload, and (b) the hardcoded
  string inside the C++ file is byte-identical to the Python EXPECTED.

Both must pass for the implementations to be considered in agreement. The
Python test runs in CI; the C++ test runs on each firmware build.

## Provisioning

In production, device keys are written to NVS during factory pairing:

1. Generate an Ed25519 keypair (offline, in a secure workstation).
2. Store the public key in `geo.device.public_key` for the matching
   `(site_id, device_id)`.
3. Flash the private key into NVS with flash encryption enabled.
4. Boot the device; `Ed25519Signer::set_private_key()` loads from NVS.

The dev firmware generates a fresh keypair each boot and prints the public
key over serial so it can be copied into a seed SQL during bring-up.

## Hardware notes

- **Sensor interface**: `src/main.cpp` currently synthesizes values. Real
  wiring options:
    - SDI-12: use `Dfrobot_SDI12` or bit-banged GPIO driver
    - MODBUS RTU (RS-485): `eModbusMaster` over UART + MAX485 transceiver
    - VW piezometer: dedicated frequency counter (e.g., Campbell CR6 companion
      or a digital piezo gauge that speaks MODBUS)
- **Power**: solar + LiFePO₄ controller with MODBUS readout; the controller
  telemetry feeds a `power_monitor` virtual sensor on the same topic path.
- **Watchdog**: enable the IWDG via `esp_task_wdt_init()` in a separate
  patch; the loop feeds it explicitly.
- **Time**: NTP is sufficient when online; for extended offline runs, use
  a DS3231 RTC over I²C and sync via GNSS-PPS at next connection.
