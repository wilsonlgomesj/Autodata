-- Seed: notification routes for Barragem X
-- Depends on migration 003_notifications.sql

BEGIN;

SET search_path = geo, public;

INSERT INTO notification_route (site_id, min_level, channel, target,
                                display_name, created_by) VALUES
  ('mineradora-x-barragem-norte', 'ATENCAO', 'email',
   'geotec@mineradora-x.com', 'Equipe Geotécnica', 'seed'),
  ('mineradora-x-barragem-norte', 'ALERTA', 'sms',
   '+5531999000001', 'On-call Geotec (SMS)', 'seed'),
  ('mineradora-x-barragem-norte', 'ALERTA', 'email',
   'ops@mineradora-x.com', 'Operações', 'seed'),
  ('mineradora-x-barragem-norte', 'EMERGENCIA_N1', 'voice',
   '+5531999000001', 'On-call Geotec (voz)', 'seed'),
  ('mineradora-x-barragem-norte', 'EMERGENCIA_N2', 'voice',
   '+5531999000002', 'Gerente de Segurança (voz)', 'seed'),
  ('mineradora-x-barragem-norte', 'EMERGENCIA_N2', 'webhook',
   'http://anm-simulator:8081/hook/paebm',
   'Webhook ANM (PAEBM simulado)', 'seed');

COMMIT;
