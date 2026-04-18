-- Autodata — Geotechnical Telemetry Metadata Schema
-- Target: PostgreSQL 15+ (TimescaleDB 2.x for hypertables, optional here)
-- Encoding: UTF-8
--
-- Scope of THIS file: metadata tables (assets, sensors, calibration, thresholds).
-- Time-series measurement hypertable is defined in a separate migration
-- (not in this file) to keep the metadata contract independent of the
-- chosen TSDB technology.
--
-- All identifiers follow docs/conventions.md.

BEGIN;

CREATE SCHEMA IF NOT EXISTS geo;

SET search_path = geo, public;

-- ---------------------------------------------------------------------------
-- Enums (mirror of docs/conventions.md §2 and §3)
-- ---------------------------------------------------------------------------

CREATE TYPE sensor_type_enum AS ENUM (
  'piezometer_vw',
  'piezometer_casagrande',
  'inclinometer_ipi_mems',
  'inclinometer_probe',
  'extensometer_magnetic',
  'extensometer_multipoint',
  'load_cell',
  'settlement_cell',
  'gnss_rover',
  'total_station_prism',
  'rain_gauge_tipping',
  'flow_meter_weir',
  'seismograph_mems',
  'fiber_optic_dts',
  'fiber_optic_dss',
  'weather_station',
  'thermistor_string',
  'power_monitor'
);

CREATE TYPE structure_kind_enum AS ENUM (
  'earth_dam',
  'rockfill_dam',
  'tailings_dam',
  'concrete_dam',
  'slope_mining',
  'slope_infrastructure',
  'retaining_wall'
);

CREATE TYPE device_kind_enum AS ENUM (
  'rtu',
  'gateway',
  'radio_repeater'
);

CREATE TYPE alert_level_enum AS ENUM (
  'NORMAL',
  'ATENCAO',
  'ALERTA',
  'EMERGENCIA_N1',
  'EMERGENCIA_N2'
);

CREATE TYPE quality_code_enum AS ENUM (
  'GOOD', 'SUSPECT', 'BAD', 'MISSING', 'CALIBRATING', 'MAINTENANCE'
);

-- ---------------------------------------------------------------------------
-- Reusable domain types
-- ---------------------------------------------------------------------------

-- Identifier domain: matches ^[a-z0-9][a-z0-9_-]{0,63}$
CREATE DOMAIN identifier AS TEXT
  CHECK (VALUE ~ '^[a-z0-9][a-z0-9_-]{0,63}$');

-- ---------------------------------------------------------------------------
-- Organizations & Sites
-- ---------------------------------------------------------------------------

CREATE TABLE organization (
  org_id        identifier PRIMARY KEY,
  display_name  TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE site (
  site_id       identifier PRIMARY KEY,
  org_id        identifier NOT NULL REFERENCES organization(org_id),
  display_name  TEXT NOT NULL,
  country       CHAR(2) NOT NULL,           -- ISO 3166-1 alpha-2
  timezone      TEXT NOT NULL,              -- IANA tz (e.g., 'America/Sao_Paulo')
  lat           DOUBLE PRECISION,
  lon           DOUBLE PRECISION,
  crs_epsg      INTEGER NOT NULL DEFAULT 4326,
  active        BOOLEAN NOT NULL DEFAULT TRUE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (lat IS NULL OR lat BETWEEN -90 AND 90),
  CHECK (lon IS NULL OR lon BETWEEN -180 AND 180)
);

CREATE INDEX ON site (org_id);

-- ---------------------------------------------------------------------------
-- Structures (dams, slopes) and their sections
-- ---------------------------------------------------------------------------

CREATE TABLE structure (
  site_id         identifier NOT NULL REFERENCES site(site_id),
  structure_id    identifier NOT NULL,
  kind            structure_kind_enum NOT NULL,
  display_name    TEXT NOT NULL,
  height_m        NUMERIC(6,2),            -- total height
  crest_length_m  NUMERIC(8,2),
  reservoir_vol_hm3 NUMERIC(10,3),
  risk_class      TEXT,                    -- e.g., 'A', 'B', 'C' per ANM
  potential_damage TEXT,                   -- 'alto', 'medio', 'baixo'
  commissioned_on DATE,
  PRIMARY KEY (site_id, structure_id)
);

CREATE TABLE section (
  site_id         identifier NOT NULL,
  structure_id    identifier NOT NULL,
  section_id      identifier NOT NULL,
  display_name    TEXT NOT NULL,
  chainage_m      NUMERIC(8,2),            -- station along crest
  notes           TEXT,
  PRIMARY KEY (site_id, structure_id, section_id),
  FOREIGN KEY (site_id, structure_id)
    REFERENCES structure(site_id, structure_id)
);

-- ---------------------------------------------------------------------------
-- Devices (RTUs, gateways)
-- ---------------------------------------------------------------------------

CREATE TABLE device (
  site_id         identifier NOT NULL REFERENCES site(site_id),
  device_id       identifier NOT NULL,
  kind            device_kind_enum NOT NULL,
  parent_gateway  identifier,             -- RTU belongs to a gateway; NULL for gateways
  model           TEXT,
  serial_number   TEXT UNIQUE,
  firmware        TEXT,
  installed_on    DATE,
  decommissioned_on DATE,
  lat             DOUBLE PRECISION,
  lon             DOUBLE PRECISION,
  elev_m          NUMERIC(8,2),
  public_key      TEXT,                   -- Ed25519 public key for signature verification
  notes           TEXT,
  PRIMARY KEY (site_id, device_id),
  CHECK (
    (kind = 'rtu' AND parent_gateway IS NOT NULL) OR
    (kind <> 'rtu')
  )
);

CREATE INDEX ON device (site_id, kind);

-- ---------------------------------------------------------------------------
-- Sensors
-- ---------------------------------------------------------------------------

CREATE TABLE sensor (
  site_id          identifier NOT NULL,
  sensor_id        identifier NOT NULL,
  sensor_type      sensor_type_enum NOT NULL,
  structure_id     identifier NOT NULL,
  section_id       identifier NOT NULL,
  device_id        identifier NOT NULL,    -- which RTU reads it
  display_name     TEXT NOT NULL,

  -- Spatial placement
  lat              DOUBLE PRECISION,
  lon              DOUBLE PRECISION,
  elev_m           NUMERIC(8,2),           -- sensor elevation
  depth_m          NUMERIC(8,2),           -- depth below surface (for buried)
  borehole_id      TEXT,

  -- Physical range (for RANGE check in QA)
  range_min        DOUBLE PRECISION,
  range_max        DOUBLE PRECISION,

  -- Step/rate limits for QA
  step_max         DOUBLE PRECISION,       -- max |Δ| between consecutive samples
  rate_max_per_s   DOUBLE PRECISION,       -- max d/dt

  -- Lifecycle
  model            TEXT,
  serial_number    TEXT,
  installed_on     DATE NOT NULL,
  decommissioned_on DATE,
  active           BOOLEAN NOT NULL DEFAULT TRUE,

  -- Pair/twin reference for cross-sensor check
  twin_sensor_id   identifier,

  notes            TEXT,

  PRIMARY KEY (site_id, sensor_id),
  FOREIGN KEY (site_id, structure_id, section_id)
    REFERENCES section(site_id, structure_id, section_id),
  FOREIGN KEY (site_id, device_id)
    REFERENCES device(site_id, device_id),
  FOREIGN KEY (site_id, twin_sensor_id)
    REFERENCES sensor(site_id, sensor_id)
    DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX ON sensor (site_id, sensor_type);
CREATE INDEX ON sensor (site_id, structure_id, section_id);
CREATE INDEX ON sensor (site_id, device_id);

-- ---------------------------------------------------------------------------
-- Calibration history (time-versioned)
-- ---------------------------------------------------------------------------

CREATE TABLE calibration (
  site_id          identifier NOT NULL,
  sensor_id        identifier NOT NULL,
  effective_from   TIMESTAMPTZ NOT NULL,
  effective_to     TIMESTAMPTZ,             -- NULL = current
  -- Polynomial y = sum(coefficients[i] * x^i). Typically 2-term for VW piezo
  -- after frequency conversion, more for thermistor correction.
  coefficients     DOUBLE PRECISION[] NOT NULL,
  -- Optional temperature compensation coefficients
  temp_compensation DOUBLE PRECISION[],
  performed_by     TEXT NOT NULL,
  certificate_url  TEXT,
  notes            TEXT,
  PRIMARY KEY (site_id, sensor_id, effective_from),
  FOREIGN KEY (site_id, sensor_id) REFERENCES sensor(site_id, sensor_id),
  CHECK (effective_to IS NULL OR effective_to > effective_from)
);

-- Single currently-active calibration per sensor
CREATE UNIQUE INDEX calibration_current
  ON calibration (site_id, sensor_id)
  WHERE effective_to IS NULL;

-- ---------------------------------------------------------------------------
-- Thresholds (project-level values from the PSB / Plano de Segurança)
-- Time-versioned: engineering may revise them after refill or rehabilitation.
-- ---------------------------------------------------------------------------

CREATE TABLE threshold (
  site_id          identifier NOT NULL,
  sensor_id        identifier NOT NULL,
  metric           TEXT NOT NULL,           -- e.g., 'pressure_kpa', 'tilt_x_deg'
  effective_from   TIMESTAMPTZ NOT NULL,
  effective_to     TIMESTAMPTZ,
  atencao          DOUBLE PRECISION,
  alerta           DOUBLE PRECISION,
  emergencia_n1    DOUBLE PRECISION,
  emergencia_n2    DOUBLE PRECISION,
  direction        TEXT NOT NULL CHECK (direction IN ('above', 'below', 'absolute')),
  hysteresis_pct   NUMERIC(5,2) DEFAULT 5.00,
  approved_by      TEXT NOT NULL,
  approval_ref     TEXT,                    -- PR/document ref
  notes            TEXT,
  PRIMARY KEY (site_id, sensor_id, metric, effective_from),
  FOREIGN KEY (site_id, sensor_id) REFERENCES sensor(site_id, sensor_id),
  CHECK (effective_to IS NULL OR effective_to > effective_from)
);

CREATE UNIQUE INDEX threshold_current
  ON threshold (site_id, sensor_id, metric)
  WHERE effective_to IS NULL;

-- ---------------------------------------------------------------------------
-- Alert rules catalog (rules live in OPA/YAML; this table tracks versions)
-- ---------------------------------------------------------------------------

CREATE TABLE alert_rule (
  rule_id          TEXT PRIMARY KEY,
  version          TEXT NOT NULL,           -- semver vX.Y.Z
  site_id          identifier,              -- NULL = global
  description      TEXT NOT NULL,
  level            alert_level_enum NOT NULL,
  definition       JSONB NOT NULL,          -- rule body
  enabled          BOOLEAN NOT NULL DEFAULT TRUE,
  created_by       TEXT NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON alert_rule (site_id) WHERE enabled = TRUE;

-- ---------------------------------------------------------------------------
-- Alert events (fired instances). The source of truth for operations.
-- ---------------------------------------------------------------------------

CREATE TABLE alert_event (
  event_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  msg_id           CHAR(26) UNIQUE NOT NULL,   -- ULID from geo.alert.v1
  site_id          identifier NOT NULL REFERENCES site(site_id),
  structure_id     identifier,
  rule_id          TEXT NOT NULL REFERENCES alert_rule(rule_id),
  rule_version     TEXT NOT NULL,
  level            alert_level_enum NOT NULL,
  t_triggered      TIMESTAMPTZ NOT NULL,
  t_resolved       TIMESTAMPTZ,
  sensors          identifier[] NOT NULL,
  evidence         JSONB NOT NULL,
  actions_taken    TEXT[],
  ack_user         TEXT,
  ack_at           TIMESTAMPTZ,
  ack_comment      TEXT,
  CHECK (t_resolved IS NULL OR t_resolved >= t_triggered)
);

CREATE INDEX ON alert_event (site_id, t_triggered DESC);
CREATE INDEX ON alert_event (level, t_resolved) WHERE t_resolved IS NULL;

-- ---------------------------------------------------------------------------
-- Users, roles, RBAC (delegated to IdP in prod; mirrored here for joins)
-- ---------------------------------------------------------------------------

CREATE TABLE app_user (
  user_id          TEXT PRIMARY KEY,        -- subject from OIDC
  display_name     TEXT NOT NULL,
  email            TEXT UNIQUE NOT NULL,
  active           BOOLEAN NOT NULL DEFAULT TRUE,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE role_assignment (
  user_id          TEXT NOT NULL REFERENCES app_user(user_id),
  site_id          identifier REFERENCES site(site_id),  -- NULL = global role
  role             TEXT NOT NULL,           -- 'viewer', 'operator', 'engineer', 'admin'
  granted_by       TEXT NOT NULL,
  granted_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, COALESCE(site_id, ''), role)
);

-- ---------------------------------------------------------------------------
-- Audit log (immutable, append-only)
-- ---------------------------------------------------------------------------

CREATE TABLE audit_event (
  event_id         BIGSERIAL PRIMARY KEY,
  t_event          TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor            TEXT NOT NULL,           -- user_id or service name
  actor_kind       TEXT NOT NULL CHECK (actor_kind IN ('user', 'service', 'device')),
  action           TEXT NOT NULL,           -- e.g., 'threshold.update', 'command.issue'
  target           JSONB NOT NULL,          -- structured target
  payload          JSONB,
  ip_address       INET,
  correlation_id   CHAR(26)
);

CREATE INDEX ON audit_event (t_event DESC);
CREATE INDEX ON audit_event (actor, t_event DESC);
CREATE INDEX ON audit_event (action, t_event DESC);

-- Prevent updates/deletes: this is a trigger, not a privilege, because
-- privileges are managed externally.
CREATE OR REPLACE FUNCTION audit_event_immutable() RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'audit_event is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_event_no_update
  BEFORE UPDATE OR DELETE ON audit_event
  FOR EACH ROW EXECUTE FUNCTION audit_event_immutable();

COMMIT;

-- ---------------------------------------------------------------------------
-- Note on time-series data:
-- The 'measurement' hypertable (TimescaleDB) is created in a separate
-- migration to keep this metadata schema portable. Reference shape:
--
--   CREATE TABLE measurement (
--     t_sample    TIMESTAMPTZ NOT NULL,
--     site_id     identifier  NOT NULL,
--     sensor_id   identifier  NOT NULL,
--     metric      TEXT        NOT NULL,
--     value       DOUBLE PRECISION,
--     value_array DOUBLE PRECISION[],
--     quality     quality_code_enum NOT NULL,
--     flags       TEXT[],
--     msg_id      CHAR(26)    NOT NULL,
--     seq         BIGINT      NOT NULL,
--     t_ingest    TIMESTAMPTZ NOT NULL DEFAULT now()
--   );
--   SELECT create_hypertable('measurement', 't_sample', chunk_time_interval => INTERVAL '1 day');
--   CREATE UNIQUE INDEX ON measurement (site_id, sensor_id, metric, msg_id);
-- ---------------------------------------------------------------------------
