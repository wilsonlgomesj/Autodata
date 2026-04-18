#!/usr/bin/env python3
"""
Autodata — Geotechnical Telemetry Validator CLI.

Subcommands:
  payload <file>        Validate a single telemetry/health/alert/command JSON payload
                        against its declared schema.
  plan <file>           Validate an instrumentation YAML for internal consistency:
                        FKs between sections, devices, sensors, thresholds.
  crosscheck <plan> <sql>  Ensure an instrumentation YAML and a Postgres seed SQL
                        agree on site, structure, sections and sensor IDs.

Exit codes: 0 ok, 1 validation failure, 2 usage error.

Designed to run in CI without a Postgres instance.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None

try:
    from jsonschema import Draft202012Validator, RefResolver  # type: ignore
except ImportError:
    Draft202012Validator = None
    RefResolver = None


REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"


SENSOR_TYPE_METRICS: dict[str, set[str]] = {
    "piezometer_vw": {"pressure_kpa", "frequency_hz", "temp_c"},
    "piezometer_casagrande": {"water_level_m"},
    "inclinometer_ipi_mems": {"tilt_x_deg", "tilt_y_deg", "temp_c"},
    "inclinometer_probe": {"tilt_x_deg", "tilt_y_deg"},
    "extensometer_magnetic": {"displacement_mm"},
    "extensometer_multipoint": {"displacement_mm"},
    "load_cell": {"force_kn"},
    "settlement_cell": {"settlement_mm"},
    "gnss_rover": {"displacement_n_mm", "displacement_e_mm", "displacement_u_mm"},
    "total_station_prism": {"displacement_n_mm", "displacement_e_mm", "displacement_u_mm"},
    "rain_gauge_tipping": {"rainfall_mm", "cumulative_mm"},
    "flow_meter_weir": {"flow_rate_ls", "water_level_m"},
    "seismograph_mems": {"accel_x_g", "accel_y_g", "accel_z_g", "pga_g"},
    "fiber_optic_dts": {"temperature_c"},
    "fiber_optic_dss": {"strain_ue"},
    "weather_station": {
        "air_temp_c", "humidity_pct", "wind_speed_ms",
        "wind_dir_deg", "pressure_hpa", "solar_rad_wm2",
    },
    "thermistor_string": {"temperature_c"},
    "power_monitor": {"v_bat", "v_panel", "i_charge_a", "i_load_a", "soc_pct"},
}

IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def ok(self) -> bool:
        return not self.errors

    def render(self) -> str:
        lines: list[str] = []
        for w in self.warnings:
            lines.append(f"WARN: {w}")
        for e in self.errors:
            lines.append(f"ERROR: {e}")
        if self.ok() and not self.warnings:
            lines.append("OK")
        elif self.ok():
            lines.append("OK (with warnings)")
        else:
            lines.append(f"FAIL ({len(self.errors)} errors, {len(self.warnings)} warnings)")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Payload validation
# ---------------------------------------------------------------------------


def _load_schema(schema_file: str) -> dict:
    with (SCHEMAS_DIR / schema_file).open("r", encoding="utf-8") as f:
        return json.load(f)


def _resolver() -> Any:
    store = {}
    for p in SCHEMAS_DIR.glob("*.schema.json"):
        with p.open("r", encoding="utf-8") as f:
            s = json.load(f)
        store[p.name] = s
        if "$id" in s:
            store[s["$id"]] = s
    return RefResolver(base_uri="", referrer={}, store=store)


def validate_payload(payload: dict, report: Report) -> None:
    if Draft202012Validator is None:
        report.err(
            "jsonschema not installed. Run: pip install -r tools/requirements.txt"
        )
        return

    schema_id = payload.get("schema")
    schema_file_map = {
        "geo.telemetry.v1": "geo.telemetry.v1.schema.json",
        "geo.health.v1": "geo.health.v1.schema.json",
        "geo.alert.v1": "geo.alert.v1.schema.json",
        "geo.command.v1": "geo.command.v1.schema.json",
    }
    if schema_id not in schema_file_map:
        report.err(f"Unknown or missing schema field: {schema_id!r}")
        return

    schema = _load_schema(schema_file_map[schema_id])
    validator = Draft202012Validator(schema, resolver=_resolver())
    for err in sorted(validator.iter_errors(payload), key=lambda e: list(e.path)):
        path = "/".join(str(p) for p in err.path) or "<root>"
        report.err(f"[{path}] {err.message}")

    # Cross-field semantic checks (beyond JSON Schema capability)
    if schema_id == "geo.telemetry.v1":
        stype = payload.get("sensor_type")
        if stype in SENSOR_TYPE_METRICS:
            allowed = SENSOR_TYPE_METRICS[stype]
            observed = set(payload.get("values", {}).keys())
            unknown = observed - allowed
            if unknown:
                report.err(
                    f"values keys {sorted(unknown)} not in canonical metrics "
                    f"for sensor_type={stype}: expected subset of {sorted(allowed)}"
                )
        sensor = payload.get("sensor", "")
        prefix_ok = _prefix_matches(sensor, stype)
        if not prefix_ok:
            report.warn(
                f"sensor_id prefix in {sensor!r} does not match "
                f"convention for sensor_type={stype}"
            )


PREFIX_BY_TYPE = {
    "piezometer_vw": "pz",
    "piezometer_casagrande": "pzc",
    "inclinometer_ipi_mems": "ipi",
    "inclinometer_probe": "incp",
    "extensometer_magnetic": "ext",
    "extensometer_multipoint": "extm",
    "load_cell": "lc",
    "settlement_cell": "sc",
    "gnss_rover": "gnss",
    "total_station_prism": "prism",
    "rain_gauge_tipping": "rain",
    "flow_meter_weir": "flow",
    "seismograph_mems": "seis",
    "fiber_optic_dts": "dts",
    "fiber_optic_dss": "dss",
    "weather_station": "met",
    "thermistor_string": "therm",
    "power_monitor": "pwr",
}


def _prefix_matches(sensor_id: str, sensor_type: str | None) -> bool:
    if sensor_type not in PREFIX_BY_TYPE:
        return True
    expected = PREFIX_BY_TYPE[sensor_type]
    return sensor_id.startswith(expected + "-") or sensor_id == expected


# ---------------------------------------------------------------------------
# Plan YAML validation
# ---------------------------------------------------------------------------


def _check_identifier(value: str, field_name: str, report: Report) -> None:
    if not isinstance(value, str) or not IDENTIFIER_RE.match(value):
        report.err(f"{field_name}={value!r} violates identifier pattern")


def validate_plan(plan: dict, report: Report) -> None:
    if plan.get("schema") != "geo.instrumentation.v1":
        report.err(
            f"schema must be 'geo.instrumentation.v1', got {plan.get('schema')!r}"
        )

    site = plan.get("site") or {}
    _check_identifier(site.get("id", ""), "site.id", report)

    # Collect referenceable IDs
    structure_ids: set[str] = set()
    sections_by_structure: dict[str, set[str]] = {}
    for st in plan.get("structures", []):
        sid = st.get("id", "")
        _check_identifier(sid, "structures[].id", report)
        structure_ids.add(sid)
        sec_ids: set[str] = set()
        for sec in st.get("sections", []):
            scid = sec.get("id", "")
            _check_identifier(scid, "section.id", report)
            sec_ids.add(scid)
        sections_by_structure[sid] = sec_ids

    gateways: set[str] = set()
    rtus: set[str] = set()
    for d in plan.get("devices", []):
        did = d.get("id", "")
        _check_identifier(did, "device.id", report)
        kind = d.get("kind")
        if kind == "gateway":
            gateways.add(did)
        elif kind == "rtu":
            rtus.add(did)
            pg = d.get("parent_gateway")
            if not pg:
                report.err(f"RTU {did} missing parent_gateway")
            elif pg not in gateways and pg not in {x.get("id") for x in plan.get("devices", [])}:
                report.err(f"RTU {did} parent_gateway={pg} not found")

    all_devices = gateways | rtus
    sensors: dict[str, dict] = {}
    for s in plan.get("sensors", []):
        sid = s.get("id", "")
        _check_identifier(sid, "sensor.id", report)
        if sid in sensors:
            report.err(f"duplicate sensor id: {sid}")
        sensors[sid] = s

        # sensor_type / prefix check
        stype = s.get("type")
        if stype not in PREFIX_BY_TYPE:
            report.err(f"sensor {sid}: unknown type {stype!r}")
        elif not _prefix_matches(sid, stype):
            report.warn(
                f"sensor {sid}: id prefix doesn't match type {stype} "
                f"(expected prefix {PREFIX_BY_TYPE[stype]!r})"
            )

        # FKs
        struct_ref = s.get("structure")
        if struct_ref not in structure_ids:
            report.err(f"sensor {sid}: structure {struct_ref!r} not declared")
        section_ref = s.get("section")
        if (
            struct_ref in sections_by_structure
            and section_ref not in sections_by_structure[struct_ref]
        ):
            report.err(
                f"sensor {sid}: section {section_ref!r} not declared under "
                f"structure {struct_ref!r}"
            )
        if s.get("device") not in all_devices:
            report.err(f"sensor {sid}: device {s.get('device')!r} not declared")

    # Twin references must be mutual
    for sid, s in sensors.items():
        twin = s.get("twin")
        if twin is None:
            continue
        if twin not in sensors:
            report.err(f"sensor {sid}: twin {twin!r} not declared")
            continue
        back = sensors[twin].get("twin")
        if back != sid:
            report.err(
                f"sensor {sid}: twin {twin!r} does not reference back to {sid}"
            )

    # Thresholds must point to declared sensors + sensor_type metric
    for t in plan.get("thresholds", []):
        sref = t.get("sensor")
        if sref not in sensors:
            report.err(f"threshold references unknown sensor {sref!r}")
            continue
        stype = sensors[sref].get("type")
        metric = t.get("metric")
        allowed = SENSOR_TYPE_METRICS.get(stype, set())
        if metric not in allowed:
            report.err(
                f"threshold on {sref}: metric {metric!r} not in canonical set for "
                f"sensor_type={stype} ({sorted(allowed)})"
            )
        levels = t.get("levels", {})
        direction = t.get("direction")
        if direction == "above":
            seq = [
                levels.get("atencao"),
                levels.get("alerta"),
                levels.get("emergencia_n1"),
                levels.get("emergencia_n2"),
            ]
            clean = [v for v in seq if v is not None]
            if clean != sorted(clean):
                report.err(
                    f"threshold on {sref}: levels not monotonic-ascending for "
                    f"direction=above: {clean}"
                )


# ---------------------------------------------------------------------------
# Cross-check plan YAML vs. seed SQL
# ---------------------------------------------------------------------------


def _extract_sensor_ids_from_sql(sql_text: str) -> set[str]:
    # Matches strings like 'pz-sec01-fund-01' appearing as the second quoted
    # argument after "mineradora-x-barragem-norte" in INSERTs into sensor.
    # Simple heuristic sufficient for the seeded file.
    ids: set[str] = set()
    for m in re.finditer(
        r"INSERT INTO sensor.*?VALUES\s*(.*?);",
        sql_text,
        flags=re.DOTALL | re.IGNORECASE,
    ):
        block = m.group(1)
        for row in re.finditer(r"\(\s*'([^']+)'\s*,\s*'([^']+)'", block):
            site_id, sensor_id = row.group(1), row.group(2)
            ids.add(sensor_id)
    return ids


def _extract_site_from_sql(sql_text: str) -> str | None:
    m = re.search(
        r"INSERT INTO site[^;]*VALUES\s*\(\s*'([^']+)'",
        sql_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return m.group(1) if m else None


def crosscheck(plan: dict, sql_text: str, report: Report) -> None:
    plan_site = (plan.get("site") or {}).get("id")
    sql_site = _extract_site_from_sql(sql_text)
    if plan_site != sql_site:
        report.err(f"site mismatch: plan={plan_site!r} sql={sql_site!r}")

    plan_sensors = {s.get("id") for s in plan.get("sensors", [])}
    sql_sensors = _extract_sensor_ids_from_sql(sql_text)

    only_plan = plan_sensors - sql_sensors
    only_sql = sql_sensors - plan_sensors
    if only_plan:
        report.err(
            f"{len(only_plan)} sensor(s) in plan YAML not in SQL seed: "
            f"{sorted(only_plan)}"
        )
    if only_sql:
        report.err(
            f"{len(only_sql)} sensor(s) in SQL seed not in plan YAML: "
            f"{sorted(only_sql)}"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict:
    if yaml is None:
        raise SystemExit("PyYAML not installed. Run: pip install -r tools/requirements.txt")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def cmd_payload(args: argparse.Namespace) -> int:
    report = Report()
    path = Path(args.file)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 2
    validate_payload(_load_json(path), report)
    print(f"=== payload {path} ===")
    print(report.render())
    return 0 if report.ok() else 1


def cmd_plan(args: argparse.Namespace) -> int:
    report = Report()
    path = Path(args.file)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 2
    validate_plan(_load_yaml(path), report)
    print(f"=== plan {path} ===")
    print(report.render())
    return 0 if report.ok() else 1


def cmd_crosscheck(args: argparse.Namespace) -> int:
    report = Report()
    plan_path, sql_path = Path(args.plan), Path(args.sql)
    if not plan_path.exists() or not sql_path.exists():
        print("plan or sql file not found", file=sys.stderr)
        return 2
    plan = _load_yaml(plan_path)
    sql_text = sql_path.read_text(encoding="utf-8")
    validate_plan(plan, report)
    crosscheck(plan, sql_text, report)
    print(f"=== crosscheck {plan_path} <-> {sql_path} ===")
    print(report.render())
    return 0 if report.ok() else 1


def cmd_all(args: argparse.Namespace) -> int:
    """Validate everything in the repo: payloads + plans + crosscheck."""
    rc = 0

    payloads_dir = REPO_ROOT / "examples" / "payloads"
    for p in sorted(payloads_dir.glob("*.json")):
        r = Report()
        validate_payload(_load_json(p), r)
        print(f"=== payload {p.relative_to(REPO_ROOT)} ===")
        print(r.render())
        if not r.ok():
            rc = 1

    plan_path = REPO_ROOT / "instrumentation" / "barragem_x.yaml"
    if plan_path.exists():
        r = Report()
        validate_plan(_load_yaml(plan_path), r)
        print(f"=== plan {plan_path.relative_to(REPO_ROOT)} ===")
        print(r.render())
        if not r.ok():
            rc = 1

    template_path = REPO_ROOT / "instrumentation" / "template.yaml"
    if template_path.exists():
        r = Report()
        validate_plan(_load_yaml(template_path), r)
        print(f"=== plan {template_path.relative_to(REPO_ROOT)} ===")
        print(r.render())
        if not r.ok():
            rc = 1

    sql_path = REPO_ROOT / "metadata" / "seeds" / "barragem_x.sql"
    if plan_path.exists() and sql_path.exists():
        r = Report()
        crosscheck(_load_yaml(plan_path), sql_path.read_text(encoding="utf-8"), r)
        print(f"=== crosscheck barragem_x ===")
        print(r.render())
        if not r.ok():
            rc = 1

    return rc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Autodata geotechnical telemetry validator",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("payload", help="validate a JSON payload")
    p.add_argument("file")
    p.set_defaults(func=cmd_payload)

    p = sub.add_parser("plan", help="validate an instrumentation YAML plan")
    p.add_argument("file")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser(
        "crosscheck", help="ensure plan YAML and seed SQL agree on IDs"
    )
    p.add_argument("plan")
    p.add_argument("sql")
    p.set_defaults(func=cmd_crosscheck)

    p = sub.add_parser("all", help="validate every artifact in the repository")
    p.set_defaults(func=cmd_all)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
