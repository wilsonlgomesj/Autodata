-- Migration 004 — Anomaly detection storage.
--
-- Two tables:
--   anomaly_model       : serialized model + metadata (which sensor/metric it
--                         scores, training window, contamination, n_estimators)
--   anomaly_score       : per-sample score history for trend inspection
--   anomaly_event       : durable record when a sample crossed the threshold
--                         (independent from threshold-based alerts; ML signal
--                          is advisory until an engineer promotes it)

BEGIN;

SET search_path = geo, public;

CREATE TABLE IF NOT EXISTS anomaly_model (
  model_id        TEXT PRIMARY KEY,
  site_id         identifier NOT NULL REFERENCES site(site_id),
  sensor_id       identifier NOT NULL,
  metric          TEXT NOT NULL,
  algorithm       TEXT NOT NULL DEFAULT 'isolation_forest',
  params          JSONB NOT NULL,
  trained_from    TIMESTAMPTZ NOT NULL,
  trained_to      TIMESTAMPTZ NOT NULL,
  n_training_samples INTEGER NOT NULL,
  -- base64 of pickled sklearn estimator; small footprint for IF (<200kB typical)
  model_blob      BYTEA NOT NULL,
  -- Normalized score threshold above which the signal is an event. Computed
  -- from the training-set distribution.
  score_threshold DOUBLE PRECISION NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  active          BOOLEAN NOT NULL DEFAULT TRUE,
  FOREIGN KEY (site_id, sensor_id) REFERENCES sensor(site_id, sensor_id)
);

CREATE INDEX IF NOT EXISTS anomaly_model_active
  ON anomaly_model (site_id, sensor_id, metric) WHERE active = TRUE;

CREATE TABLE IF NOT EXISTS anomaly_score (
  t_sample     TIMESTAMPTZ NOT NULL,
  site_id      identifier  NOT NULL,
  sensor_id    identifier  NOT NULL,
  metric       TEXT        NOT NULL,
  model_id     TEXT        NOT NULL REFERENCES anomaly_model(model_id),
  score        DOUBLE PRECISION NOT NULL,
  is_anomaly   BOOLEAN     NOT NULL,
  -- features vector in JSON for debugging / retraining
  features     JSONB
);

CREATE INDEX IF NOT EXISTS anomaly_score_sensor_time
  ON anomaly_score (site_id, sensor_id, metric, t_sample DESC);

CREATE INDEX IF NOT EXISTS anomaly_score_events
  ON anomaly_score (site_id, sensor_id, t_sample DESC)
  WHERE is_anomaly = TRUE;

CREATE TABLE IF NOT EXISTS anomaly_event (
  event_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id       identifier NOT NULL,
  sensor_id     identifier NOT NULL,
  metric        TEXT NOT NULL,
  model_id      TEXT NOT NULL REFERENCES anomaly_model(model_id),
  t_detected    TIMESTAMPTZ NOT NULL DEFAULT now(),
  t_sample      TIMESTAMPTZ NOT NULL,
  score         DOUBLE PRECISION NOT NULL,
  features      JSONB,
  -- Engineer actions
  reviewed_by   TEXT,
  reviewed_at   TIMESTAMPTZ,
  disposition   TEXT CHECK (disposition IN (
    NULL, 'confirmed_anomaly', 'noise', 'sensor_fault', 'calibration_event'
  )),
  notes         TEXT
);

CREATE INDEX IF NOT EXISTS anomaly_event_recent
  ON anomaly_event (site_id, sensor_id, t_detected DESC);

COMMIT;
