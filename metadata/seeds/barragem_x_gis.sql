-- Seed: spatial data for Barragem X.
-- Coordinates are plausible for a Minas Gerais dam; adjust for real site.

BEGIN;

SET search_path = geo, public;

-- Site boundary (approximate rectangle) and office point.
UPDATE site SET
  geom_point    = ST_SetSRID(ST_MakePoint(-43.9345, -19.9167), 4326),
  geom_boundary = ST_SetSRID(ST_GeomFromText(
    'POLYGON((-43.9420 -19.9120, -43.9280 -19.9120, '
    '-43.9280 -19.9220, -43.9420 -19.9220, -43.9420 -19.9120))'
  ), 4326)
WHERE site_id = 'mineradora-x-barragem-norte';

-- Structure centroid and footprint (rectangular placeholder).
UPDATE structure SET
  geom_point     = ST_SetSRID(ST_MakePoint(-43.9340, -19.9168), 4326),
  geom_footprint = ST_SetSRID(ST_GeomFromText(
    'POLYGON((-43.9362 -19.9168, -43.9318 -19.9168, '
    '-43.9318 -19.9172, -43.9362 -19.9172, -43.9362 -19.9168))'
  ), 4326)
WHERE site_id = 'mineradora-x-barragem-norte'
  AND structure_id = 'barragem-principal';

-- Section transect lines running across the dam.
UPDATE section SET
  geom_line = ST_SetSRID(ST_GeomFromText(
    'LINESTRING(-43.9355 -19.9160, -43.9355 -19.9180)'
  ), 4326)
WHERE site_id = 'mineradora-x-barragem-norte'
  AND section_id = 'sec-01-ombreira-esq';

UPDATE section SET
  geom_line = ST_SetSRID(ST_GeomFromText(
    'LINESTRING(-43.9340 -19.9160, -43.9340 -19.9180)'
  ), 4326)
WHERE site_id = 'mineradora-x-barragem-norte'
  AND section_id = 'sec-02-centro';

UPDATE section SET
  geom_line = ST_SetSRID(ST_GeomFromText(
    'LINESTRING(-43.9325 -19.9160, -43.9325 -19.9180)'
  ), 4326)
WHERE site_id = 'mineradora-x-barragem-norte'
  AND section_id = 'sec-03-ombreira-dir';

-- Sensor coordinates — derived from section + small offsets to spread
-- points visibly. lat/lon are canonical; geom_point is GENERATED.
UPDATE sensor SET lat = -19.9172, lon = -43.9356 WHERE sensor_id = 'pz-sec01-fund-01' AND site_id = 'mineradora-x-barragem-norte';
UPDATE sensor SET lat = -19.9170, lon = -43.9355 WHERE sensor_id = 'pz-sec01-cont-01' AND site_id = 'mineradora-x-barragem-norte';
UPDATE sensor SET lat = -19.9168, lon = -43.9355 WHERE sensor_id = 'pz-sec01-nuc-01'  AND site_id = 'mineradora-x-barragem-norte';
UPDATE sensor SET lat = -19.9172, lon = -43.9341 WHERE sensor_id = 'pz-sec02-fund-01' AND site_id = 'mineradora-x-barragem-norte';
UPDATE sensor SET lat = -19.9172, lon = -43.9339 WHERE sensor_id = 'pz-sec02-fund-02' AND site_id = 'mineradora-x-barragem-norte';
UPDATE sensor SET lat = -19.9170, lon = -43.9340 WHERE sensor_id = 'pz-sec02-cont-01' AND site_id = 'mineradora-x-barragem-norte';
UPDATE sensor SET lat = -19.9168, lon = -43.9340 WHERE sensor_id = 'pz-sec02-nuc-01'  AND site_id = 'mineradora-x-barragem-norte';
UPDATE sensor SET lat = -19.9172, lon = -43.9326 WHERE sensor_id = 'pz-sec03-fund-01' AND site_id = 'mineradora-x-barragem-norte';
UPDATE sensor SET lat = -19.9170, lon = -43.9325 WHERE sensor_id = 'pz-sec03-cont-01' AND site_id = 'mineradora-x-barragem-norte';
UPDATE sensor SET lat = -19.9168, lon = -43.9325 WHERE sensor_id = 'pz-sec03-nuc-01'  AND site_id = 'mineradora-x-barragem-norte';
UPDATE sensor SET lat = -19.9163, lon = -43.9356 WHERE sensor_id = 'ipi-crista-sec01-01' AND site_id = 'mineradora-x-barragem-norte';
UPDATE sensor SET lat = -19.9163, lon = -43.9340 WHERE sensor_id = 'ipi-crista-sec02-01' AND site_id = 'mineradora-x-barragem-norte';
UPDATE sensor SET lat = -19.9163, lon = -43.9326 WHERE sensor_id = 'ipi-crista-sec03-01' AND site_id = 'mineradora-x-barragem-norte';
UPDATE sensor SET lat = -19.9175, lon = -43.9340 WHERE sensor_id = 'ipi-jusante-sec02-01' AND site_id = 'mineradora-x-barragem-norte';
UPDATE sensor SET lat = -19.9175, lon = -43.9325 WHERE sensor_id = 'ipi-jusante-sec03-01' AND site_id = 'mineradora-x-barragem-norte';
UPDATE sensor SET lat = -19.9163, lon = -43.9342 WHERE sensor_id = 'rain-crista-01' AND site_id = 'mineradora-x-barragem-norte';
UPDATE sensor SET lat = -19.9178, lon = -43.9342 WHERE sensor_id = 'rain-jusante-01' AND site_id = 'mineradora-x-barragem-norte';

COMMIT;
