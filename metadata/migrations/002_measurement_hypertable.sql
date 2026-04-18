-- Migration 002 — Time-series storage for geotechnical telemetry.
--
-- Requires: TimescaleDB extension. If the extension is not available (e.g.,
-- vanilla PostgreSQL in CI without the Timescale package), the hypertable
-- conversion is skipped, but the base table is created so tests can exercise
-- the schema.
--
-- Data model:
--   One row per (sensor, metric, t_sample). A single telemetry payload
--   with N values fans out to N rows in this table. This makes agg queries
--   per metric trivial and keeps row size predictable.

BEGIN;

SET search_path = geo, public;

-- ---------------------------------------------------------------------------
-- Dead-letter table: messages that failed validation or enrichment.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS dead_letter (
  dlq_id         BIGSERIAL PRIMARY KEY,
  t_received     TIMESTAMPTZ NOT NULL DEFAULT now(),
  topic          TEXT NOT NULL,
  payload        JSONB NOT NULL,
  reason         TEXT NOT NULL,
  details        TEXT
);

CREATE INDEX IF NOT EXISTS dead_letter_t_received_idx
  ON dead_letter (t_received DESC);

-- ---------------------------------------------------------------------------
-- measurement — core time-series table
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS measurement (
  t_sample     TIMESTAMPTZ NOT NULL,
  site_id      identifier  NOT NULL,
  sensor_id    identifier  NOT NULL,
  metric       TEXT        NOT NULL,
  value        DOUBLE PRECISION,
  value_array  DOUBLE PRECISION[],
  quality      quality_code_enum NOT NULL,
  flags        TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  msg_id       CHAR(26)    NOT NULL,
  seq          BIGINT      NOT NULL,
  t_ingest     TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- Exactly one of value/value_array is set
  CHECK (
    (value IS NOT NULL AND value_array IS NULL) OR
    (value IS NULL AND value_array IS NOT NULL)
  )
);

-- Idempotency: same (site, sensor, metric, msg_id) never duplicates.
-- This is the contract that allows RTU to resend safely after outages.
CREATE UNIQUE INDEX IF NOT EXISTS measurement_msg_unique
  ON measurement (site_id, sensor_id, metric, msg_id);

-- Common lookup index
CREATE INDEX IF NOT EXISTS measurement_sensor_time_idx
  ON measurement (site_id, sensor_id, metric, t_sample DESC);

-- ---------------------------------------------------------------------------
-- TimescaleDB-specific: hypertable + compression + retention.
-- Wrapped in DO block so the migration works on vanilla Postgres too.
-- ---------------------------------------------------------------------------

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    -- Idempotent hypertable creation.
    PERFORM create_hypertable(
      'geo.measurement',
      't_sample',
      chunk_time_interval => INTERVAL '1 day',
      if_not_exists => TRUE
    );

    -- Compression policy: compress chunks older than 7 days.
    -- segmentby groups rows of the same sensor/metric within a chunk,
    -- which yields strong compression on monotonic time-series.
    ALTER TABLE geo.measurement SET (
      timescaledb.compress,
      timescaledb.compress_segmentby = 'site_id, sensor_id, metric',
      timescaledb.compress_orderby = 't_sample DESC'
    );

    BEGIN
      PERFORM add_compression_policy('geo.measurement', INTERVAL '7 days');
    EXCEPTION WHEN duplicate_object THEN
      -- policy already exists
      NULL;
    END;

    -- Retention: drop raw data older than 2 years.
    -- Aggregates (1 min/1 h) live in separate continuous aggregates with
    -- longer retention.
    BEGIN
      PERFORM add_retention_policy('geo.measurement', INTERVAL '2 years');
    EXCEPTION WHEN duplicate_object THEN
      NULL;
    END;
  ELSE
    RAISE NOTICE 'timescaledb extension not available; skipping hypertable conversion';
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- Continuous aggregates (only meaningful on TimescaleDB).
-- ---------------------------------------------------------------------------

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    -- 1-minute rollup: min/max/avg per (sensor, metric).
    EXECUTE $ca$
      CREATE MATERIALIZED VIEW IF NOT EXISTS geo.measurement_1min
      WITH (timescaledb.continuous) AS
      SELECT
        time_bucket(INTERVAL '1 minute', t_sample) AS bucket,
        site_id, sensor_id, metric,
        count(*)   AS n,
        min(value) AS v_min,
        max(value) AS v_max,
        avg(value) AS v_avg,
        -- quality rolled up: worst quality in the bucket
        max(CASE quality
              WHEN 'GOOD' THEN 0 WHEN 'SUSPECT' THEN 1
              WHEN 'CALIBRATING' THEN 2 WHEN 'MAINTENANCE' THEN 2
              WHEN 'BAD' THEN 3 WHEN 'MISSING' THEN 3
            END) AS worst_quality_rank
      FROM geo.measurement
      WHERE value IS NOT NULL
      GROUP BY bucket, site_id, sensor_id, metric
      WITH NO DATA
    $ca$;

    BEGIN
      PERFORM add_continuous_aggregate_policy(
        'geo.measurement_1min',
        start_offset => INTERVAL '1 hour',
        end_offset   => INTERVAL '1 minute',
        schedule_interval => INTERVAL '1 minute'
      );
    EXCEPTION WHEN duplicate_object THEN
      NULL;
    END;

    -- 1-hour rollup, derived from 1-minute for efficiency.
    EXECUTE $ca$
      CREATE MATERIALIZED VIEW IF NOT EXISTS geo.measurement_1h
      WITH (timescaledb.continuous) AS
      SELECT
        time_bucket(INTERVAL '1 hour', bucket) AS bucket_h,
        site_id, sensor_id, metric,
        sum(n)     AS n,
        min(v_min) AS v_min,
        max(v_max) AS v_max,
        avg(v_avg) AS v_avg,
        max(worst_quality_rank) AS worst_quality_rank
      FROM geo.measurement_1min
      GROUP BY bucket_h, site_id, sensor_id, metric
      WITH NO DATA
    $ca$;

    BEGIN
      PERFORM add_continuous_aggregate_policy(
        'geo.measurement_1h',
        start_offset => INTERVAL '3 hours',
        end_offset   => INTERVAL '1 hour',
        schedule_interval => INTERVAL '15 minutes'
      );
    EXCEPTION WHEN duplicate_object THEN
      NULL;
    END;
  END IF;
END $$;

COMMIT;
