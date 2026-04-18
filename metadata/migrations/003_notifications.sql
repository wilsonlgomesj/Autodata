-- Migration 003 — Notification routing and dispatch log.
--
-- Routes describe WHO gets notified for WHICH (site, level, action).
-- Dispatches are the immutable record of WHEN each notification was sent.

BEGIN;

SET search_path = geo, public;

-- ---------------------------------------------------------------------------
-- Notification channel enum
-- ---------------------------------------------------------------------------

CREATE TYPE notification_channel_enum AS ENUM (
  'email',
  'sms',
  'voice',
  'webhook',
  'teams',
  'slack',
  'push',
  'siren'
);

CREATE TYPE dispatch_status_enum AS ENUM (
  'sent', 'failed', 'suppressed', 'pending'
);

-- ---------------------------------------------------------------------------
-- notification_route — which people/endpoints receive alerts of a given
-- site and level. Supports multiple routes per alert (broadcast).
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS notification_route (
  route_id        BIGSERIAL PRIMARY KEY,
  site_id         identifier REFERENCES site(site_id),  -- NULL = global
  min_level       alert_level_enum NOT NULL,
  channel         notification_channel_enum NOT NULL,
  -- Target format depends on channel:
  --   email:   user@example.com
  --   sms:     +5531999999999
  --   voice:   +5531999999999
  --   webhook: https://example.com/hook
  --   teams:   https://outlook.office.com/webhook/...
  --   slack:   https://hooks.slack.com/services/...
  target          TEXT NOT NULL,
  display_name    TEXT,
  active          BOOLEAN NOT NULL DEFAULT TRUE,
  -- Optional filters
  rule_id_glob    TEXT,                   -- simple glob ("pz-*"), NULL=any
  structure_id    identifier,             -- NULL=any
  created_by      TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS notification_route_lookup
  ON notification_route (site_id, min_level) WHERE active = TRUE;

-- ---------------------------------------------------------------------------
-- notification_dispatch — append-only log of every dispatch attempt.
-- Idempotency: (alert_msg_id, route_id, channel) unique prevents double-send
-- if the service crashes and reprocesses an alert.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS notification_dispatch (
  dispatch_id     BIGSERIAL PRIMARY KEY,
  alert_msg_id    CHAR(26) NOT NULL,
  site_id         identifier NOT NULL,
  level           alert_level_enum NOT NULL,
  route_id        BIGINT REFERENCES notification_route(route_id),
  channel         notification_channel_enum NOT NULL,
  target          TEXT NOT NULL,
  status          dispatch_status_enum NOT NULL,
  error           TEXT,
  t_attempted     TIMESTAMPTZ NOT NULL DEFAULT now(),
  latency_ms      INTEGER,
  UNIQUE (alert_msg_id, route_id, channel)
);

CREATE INDEX IF NOT EXISTS notification_dispatch_alert
  ON notification_dispatch (alert_msg_id);
CREATE INDEX IF NOT EXISTS notification_dispatch_time
  ON notification_dispatch (t_attempted DESC);

-- Append-only: prevent accidental updates.
CREATE OR REPLACE FUNCTION notification_dispatch_immutable()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'notification_dispatch is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER notification_dispatch_no_update
  BEFORE UPDATE OR DELETE ON notification_dispatch
  FOR EACH ROW EXECUTE FUNCTION notification_dispatch_immutable();

COMMIT;
