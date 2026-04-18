-- Seed: Barragem X (exemplo realista da Fase 1)
-- Depende de: metadata/schema.sql
-- Uso: psql -f schema.sql && psql -f seeds/barragem_x.sql

BEGIN;

SET search_path = geo, public;

-- ---------------------------------------------------------------------------
-- Organização e site
-- ---------------------------------------------------------------------------

INSERT INTO organization (org_id, display_name) VALUES
  ('mineradora-x', 'Mineradora X Ltda.');

INSERT INTO site (site_id, org_id, display_name, country, timezone, lat, lon) VALUES
  ('mineradora-x-barragem-norte', 'mineradora-x', 'Complexo Norte — Barragem X',
   'BR', 'America/Sao_Paulo', -19.9167, -43.9345);

-- ---------------------------------------------------------------------------
-- Estrutura e seções
-- ---------------------------------------------------------------------------

INSERT INTO structure (site_id, structure_id, kind, display_name,
                       height_m, crest_length_m, reservoir_vol_hm3,
                       risk_class, potential_damage, commissioned_on)
VALUES
  ('mineradora-x-barragem-norte', 'barragem-principal', 'earth_dam',
   'Barragem Principal', 45.00, 600.00, 12.000,
   'B', 'alto', '2018-09-15');

INSERT INTO section (site_id, structure_id, section_id, display_name, chainage_m) VALUES
  ('mineradora-x-barragem-norte', 'barragem-principal', 'sec-01-ombreira-esq',
   'Seção 1 — Ombreira Esquerda', 50.00),
  ('mineradora-x-barragem-norte', 'barragem-principal', 'sec-02-centro',
   'Seção 2 — Centro', 300.00),
  ('mineradora-x-barragem-norte', 'barragem-principal', 'sec-03-ombreira-dir',
   'Seção 3 — Ombreira Direita', 550.00);

-- ---------------------------------------------------------------------------
-- Dispositivos: 1 gateway + 3 RTUs (uma por seção)
-- ---------------------------------------------------------------------------

INSERT INTO device (site_id, device_id, kind, parent_gateway,
                    model, serial_number, firmware, installed_on, lat, lon, elev_m,
                    public_key, notes) VALUES
  ('mineradora-x-barragem-norte', 'gw-bx-001', 'gateway', NULL,
   'Advantech UNO-137', 'SN-GW-001-ABCD', 'edge-fw-3.2.0', '2024-06-01',
   -19.9169, -43.9340, 820.00,
   'MCowBQYDK2VwAyEA_gw_bx_001_pubkey_base64_placeholder_xxxxxxxxxxxxx=',
   'Concentrador central, 4G Vivo + Starlink'),

  ('mineradora-x-barragem-norte', 'rtu-bx-e1', 'rtu', 'gw-bx-001',
   'Campbell CR6', 'SN-RTU-E1-0001', 'rtu-fw-2.4.1', '2024-06-05',
   -19.9170, -43.9355, 818.50,
   'MCowBQYDK2VwAyEA_rtu_bx_e1_pubkey_base64_placeholder_xxxxxxxxxxx=',
   'Ombreira esquerda'),

  ('mineradora-x-barragem-norte', 'rtu-bx-c1', 'rtu', 'gw-bx-001',
   'Campbell CR6', 'SN-RTU-C1-0001', 'rtu-fw-2.4.1', '2024-06-05',
   -19.9168, -43.9340, 819.20,
   'MCowBQYDK2VwAyEA_rtu_bx_c1_pubkey_base64_placeholder_xxxxxxxxxxx=',
   'Centro — seção crítica'),

  ('mineradora-x-barragem-norte', 'rtu-bx-d1', 'rtu', 'gw-bx-001',
   'Campbell CR6', 'SN-RTU-D1-0001', 'rtu-fw-2.4.1', '2024-06-05',
   -19.9166, -43.9325, 818.80,
   'MCowBQYDK2VwAyEA_rtu_bx_d1_pubkey_base64_placeholder_xxxxxxxxxxx=',
   'Ombreira direita');

-- ---------------------------------------------------------------------------
-- Sensores (10 piezômetros + 5 inclinômetros + 2 pluviômetros, per requisito)
-- ---------------------------------------------------------------------------

-- Piezômetros VW — distribuição por seção
-- Seção 1 (3): fundação, contato, núcleo médio
INSERT INTO sensor (site_id, sensor_id, sensor_type, structure_id, section_id,
                    device_id, display_name, elev_m, depth_m, borehole_id,
                    range_min, range_max, step_max, rate_max_per_s,
                    model, serial_number, installed_on, twin_sensor_id) VALUES
  ('mineradora-x-barragem-norte', 'pz-sec01-fund-01', 'piezometer_vw',
   'barragem-principal', 'sec-01-ombreira-esq', 'rtu-bx-e1',
   'PZ fundação S1', 775.00, 40.00, 'SM-01-PZ-40',
   0, 700, 50, 0.5,
   'Geokon 4500S', 'SN-PZ-001', '2024-06-10', NULL),

  ('mineradora-x-barragem-norte', 'pz-sec01-cont-01', 'piezometer_vw',
   'barragem-principal', 'sec-01-ombreira-esq', 'rtu-bx-e1',
   'PZ contato núcleo-fundação S1', 785.00, 30.00, 'SM-01-PZ-30',
   0, 700, 50, 0.5,
   'Geokon 4500S', 'SN-PZ-002', '2024-06-10', NULL),

  ('mineradora-x-barragem-norte', 'pz-sec01-nuc-01', 'piezometer_vw',
   'barragem-principal', 'sec-01-ombreira-esq', 'rtu-bx-e1',
   'PZ núcleo médio S1', 800.00, 15.00, 'SM-01-PZ-15',
   0, 500, 40, 0.4,
   'Geokon 4500S', 'SN-PZ-003', '2024-06-10', NULL);

-- Seção 2 (4): fundação (par redundante), contato, núcleo médio
INSERT INTO sensor (site_id, sensor_id, sensor_type, structure_id, section_id,
                    device_id, display_name, elev_m, depth_m, borehole_id,
                    range_min, range_max, step_max, rate_max_per_s,
                    model, serial_number, installed_on, twin_sensor_id) VALUES
  ('mineradora-x-barragem-norte', 'pz-sec02-fund-01', 'piezometer_vw',
   'barragem-principal', 'sec-02-centro', 'rtu-bx-c1',
   'PZ fundação S2 (gêmeo A)', 775.00, 40.00, 'SM-02-PZ-40A',
   0, 700, 50, 0.5,
   'Geokon 4500S', 'SN-PZ-004', '2024-06-11', 'pz-sec02-fund-02'),

  ('mineradora-x-barragem-norte', 'pz-sec02-fund-02', 'piezometer_vw',
   'barragem-principal', 'sec-02-centro', 'rtu-bx-c1',
   'PZ fundação S2 (gêmeo B)', 775.00, 40.00, 'SM-02-PZ-40B',
   0, 700, 50, 0.5,
   'Geokon 4500S', 'SN-PZ-005', '2024-06-11', 'pz-sec02-fund-01'),

  ('mineradora-x-barragem-norte', 'pz-sec02-cont-01', 'piezometer_vw',
   'barragem-principal', 'sec-02-centro', 'rtu-bx-c1',
   'PZ contato núcleo-fundação S2', 785.00, 30.00, 'SM-02-PZ-30',
   0, 700, 50, 0.5,
   'Geokon 4500S', 'SN-PZ-006', '2024-06-11', NULL),

  ('mineradora-x-barragem-norte', 'pz-sec02-nuc-01', 'piezometer_vw',
   'barragem-principal', 'sec-02-centro', 'rtu-bx-c1',
   'PZ núcleo médio S2', 800.00, 15.00, 'SM-02-PZ-15',
   0, 500, 40, 0.4,
   'Geokon 4500S', 'SN-PZ-007', '2024-06-11', NULL);

-- Seção 3 (3): fundação, contato, núcleo médio
INSERT INTO sensor (site_id, sensor_id, sensor_type, structure_id, section_id,
                    device_id, display_name, elev_m, depth_m, borehole_id,
                    range_min, range_max, step_max, rate_max_per_s,
                    model, serial_number, installed_on, twin_sensor_id) VALUES
  ('mineradora-x-barragem-norte', 'pz-sec03-fund-01', 'piezometer_vw',
   'barragem-principal', 'sec-03-ombreira-dir', 'rtu-bx-d1',
   'PZ fundação S3', 775.00, 40.00, 'SM-03-PZ-40',
   0, 700, 50, 0.5,
   'Geokon 4500S', 'SN-PZ-008', '2024-06-12', NULL),

  ('mineradora-x-barragem-norte', 'pz-sec03-cont-01', 'piezometer_vw',
   'barragem-principal', 'sec-03-ombreira-dir', 'rtu-bx-d1',
   'PZ contato S3', 785.00, 30.00, 'SM-03-PZ-30',
   0, 700, 50, 0.5,
   'Geokon 4500S', 'SN-PZ-009', '2024-06-12', NULL),

  ('mineradora-x-barragem-norte', 'pz-sec03-nuc-01', 'piezometer_vw',
   'barragem-principal', 'sec-03-ombreira-dir', 'rtu-bx-d1',
   'PZ núcleo médio S3', 800.00, 15.00, 'SM-03-PZ-15',
   0, 500, 40, 0.4,
   'Geokon 4500S', 'SN-PZ-010', '2024-06-12', NULL);

-- Inclinômetros MEMS in-place — 3 na crista + 2 no talude de jusante
INSERT INTO sensor (site_id, sensor_id, sensor_type, structure_id, section_id,
                    device_id, display_name, elev_m, depth_m, borehole_id,
                    range_min, range_max, step_max, rate_max_per_s,
                    model, serial_number, installed_on) VALUES
  ('mineradora-x-barragem-norte', 'ipi-crista-sec01-01', 'inclinometer_ipi_mems',
   'barragem-principal', 'sec-01-ombreira-esq', 'rtu-bx-e1',
   'IPI crista S1', 820.00, 10.00, 'SM-01-IPI-01',
   -15, 15, 0.5, 0.001,
   'DGSI MEMS IPI', 'SN-IPI-001', '2024-06-14'),

  ('mineradora-x-barragem-norte', 'ipi-crista-sec02-01', 'inclinometer_ipi_mems',
   'barragem-principal', 'sec-02-centro', 'rtu-bx-c1',
   'IPI crista S2', 820.00, 10.00, 'SM-02-IPI-01',
   -15, 15, 0.5, 0.001,
   'DGSI MEMS IPI', 'SN-IPI-002', '2024-06-14'),

  ('mineradora-x-barragem-norte', 'ipi-crista-sec03-01', 'inclinometer_ipi_mems',
   'barragem-principal', 'sec-03-ombreira-dir', 'rtu-bx-d1',
   'IPI crista S3', 820.00, 10.00, 'SM-03-IPI-01',
   -15, 15, 0.5, 0.001,
   'DGSI MEMS IPI', 'SN-IPI-003', '2024-06-14'),

  ('mineradora-x-barragem-norte', 'ipi-jusante-sec02-01', 'inclinometer_ipi_mems',
   'barragem-principal', 'sec-02-centro', 'rtu-bx-c1',
   'IPI talude jusante S2', 800.00, 8.00, 'SM-02-IPI-JUS',
   -15, 15, 0.5, 0.001,
   'DGSI MEMS IPI', 'SN-IPI-004', '2024-06-14'),

  ('mineradora-x-barragem-norte', 'ipi-jusante-sec03-01', 'inclinometer_ipi_mems',
   'barragem-principal', 'sec-03-ombreira-dir', 'rtu-bx-d1',
   'IPI talude jusante S3', 800.00, 8.00, 'SM-03-IPI-JUS',
   -15, 15, 0.5, 0.001,
   'DGSI MEMS IPI', 'SN-IPI-005', '2024-06-14');

-- Pluviômetros: crista (seção 2) e pé de jusante (seção 2)
INSERT INTO sensor (site_id, sensor_id, sensor_type, structure_id, section_id,
                    device_id, display_name, elev_m, depth_m,
                    range_min, range_max, step_max, rate_max_per_s,
                    model, serial_number, installed_on) VALUES
  ('mineradora-x-barragem-norte', 'rain-crista-01', 'rain_gauge_tipping',
   'barragem-principal', 'sec-02-centro', 'gw-bx-001',
   'Pluviômetro crista', 820.00, 0.00,
   0, 300, 300, 0.1,
   'Davis Tipping Bucket', 'SN-RAIN-001', '2024-06-15'),

  ('mineradora-x-barragem-norte', 'rain-jusante-01', 'rain_gauge_tipping',
   'barragem-principal', 'sec-02-centro', 'gw-bx-001',
   'Pluviômetro pé de jusante', 778.00, 0.00,
   0, 300, 300, 0.1,
   'Davis Tipping Bucket', 'SN-RAIN-002', '2024-06-15');

-- ---------------------------------------------------------------------------
-- Calibração inicial (linear simples: y = a + b*x) para todos os PZ
-- ---------------------------------------------------------------------------

INSERT INTO calibration (site_id, sensor_id, effective_from, coefficients,
                         performed_by, notes)
SELECT
  'mineradora-x-barragem-norte',
  sensor_id,
  '2024-06-10 00:00:00+00',
  ARRAY[0.0, 0.0001],          -- pressure_kpa = 0 + 1e-4 * freq²; placeholder
  'lab-calib-fabrica',
  'Calibração de fábrica importada do certificado'
FROM sensor
WHERE site_id = 'mineradora-x-barragem-norte'
  AND sensor_type = 'piezometer_vw';

-- ---------------------------------------------------------------------------
-- Thresholds (valores do PSB — exemplo didático)
-- ---------------------------------------------------------------------------

-- Piezômetros fundação: limites mais restritivos
INSERT INTO threshold (site_id, sensor_id, metric, effective_from,
                       atencao, alerta, emergencia_n1, emergencia_n2,
                       direction, hysteresis_pct, approved_by, approval_ref) VALUES
  ('mineradora-x-barragem-norte', 'pz-sec01-fund-01', 'pressure_kpa', '2024-07-01',
   380, 420, 460, 500, 'above', 5.0, 'eng-geotec-chief', 'PSB-BX-REV3'),
  ('mineradora-x-barragem-norte', 'pz-sec02-fund-01', 'pressure_kpa', '2024-07-01',
   380, 420, 460, 500, 'above', 5.0, 'eng-geotec-chief', 'PSB-BX-REV3'),
  ('mineradora-x-barragem-norte', 'pz-sec02-fund-02', 'pressure_kpa', '2024-07-01',
   380, 420, 460, 500, 'above', 5.0, 'eng-geotec-chief', 'PSB-BX-REV3'),
  ('mineradora-x-barragem-norte', 'pz-sec03-fund-01', 'pressure_kpa', '2024-07-01',
   380, 420, 460, 500, 'above', 5.0, 'eng-geotec-chief', 'PSB-BX-REV3');

-- Inclinômetros crista: tilt em graus
INSERT INTO threshold (site_id, sensor_id, metric, effective_from,
                       atencao, alerta, emergencia_n1, emergencia_n2,
                       direction, hysteresis_pct, approved_by, approval_ref) VALUES
  ('mineradora-x-barragem-norte', 'ipi-crista-sec02-01', 'tilt_x_deg', '2024-07-01',
   0.15, 0.25, 0.40, 0.60, 'absolute', 10.0, 'eng-geotec-chief', 'PSB-BX-REV3');

-- ---------------------------------------------------------------------------
-- Regras de alerta (em alto nível; implementação efetiva em OPA/YAML)
-- ---------------------------------------------------------------------------

INSERT INTO alert_rule (rule_id, version, site_id, description, level,
                        definition, created_by) VALUES
  ('pz-fund-alerta', 'v1.0.0', 'mineradora-x-barragem-norte',
   'PZ fundação acima do limite de alerta com persistência 30min',
   'ALERTA',
   '{"sensor_glob": "pz-*-fund-*", "metric": "pressure_kpa",
     "op": ">", "ref": "threshold.alerta",
     "persistence_s": 1800, "hysteresis_pct": 5}'::jsonb,
   'eng-geotec-chief'),

  ('pz-emergencia-confirmado', 'v1.0.0', 'mineradora-x-barragem-norte',
   'Confirmação cruzada: 2+ PZ acima do limite de emergência',
   'EMERGENCIA_N2',
   '{"confirm_count": 2, "metric": "pressure_kpa",
     "op": ">", "ref": "threshold.emergencia_n2",
     "actions": ["voz_on_call", "sirene", "webhook_anm"]}'::jsonb,
   'eng-geotec-chief'),

  ('chuva-porpressao', 'v1.0.0', 'mineradora-x-barragem-norte',
   'Chuva 72h > 150mm + d(PZ_fund)/dt > 2 kPa/h',
   'ATENCAO',
   '{"rain_72h_mm_gt": 150, "pz_rate_kpa_per_h_gt": 2}'::jsonb,
   'eng-geotec-chief');

COMMIT;
