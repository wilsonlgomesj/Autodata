-- Migration 005 — PostGIS spatial layer.
--
-- Adds geometry columns on site, structure, section, sensor so the API
-- can return GeoJSON directly, Grafana GeoMap plugin can plot markers, and
-- downstream GIS tools (QGIS) can consume the data via OGR/ogr2ogr.
--
-- We use GEOMETRY(Point, 4326) and GEOMETRY(Polygon, 4326) since WGS 84 is
-- the interoperable default. Projects working in local CRS can add another
-- column (e.g., SIRGAS 2000) and a generated ST_Transform view.

BEGIN;

-- PostGIS must exist in the cluster. Skips cleanly if already installed.
CREATE EXTENSION IF NOT EXISTS postgis;

SET search_path = geo, public;

-- ---------------------------------------------------------------------------
-- Geometry columns
-- ---------------------------------------------------------------------------

-- Site: a point for the operations office, plus an optional perimeter
-- polygon (property boundary, permit area).
ALTER TABLE site
  ADD COLUMN IF NOT EXISTS geom_point    GEOMETRY(Point,   4326),
  ADD COLUMN IF NOT EXISTS geom_boundary GEOMETRY(Polygon, 4326);

CREATE INDEX IF NOT EXISTS site_geom_point_gix
  ON site USING GIST (geom_point);

-- Structure: centroid plus footprint polygon.
ALTER TABLE structure
  ADD COLUMN IF NOT EXISTS geom_point     GEOMETRY(Point,   4326),
  ADD COLUMN IF NOT EXISTS geom_footprint GEOMETRY(Polygon, 4326);

CREATE INDEX IF NOT EXISTS structure_geom_footprint_gix
  ON structure USING GIST (geom_footprint);

-- Section: a transect line across the dam body.
ALTER TABLE section
  ADD COLUMN IF NOT EXISTS geom_line GEOMETRY(LineString, 4326);

CREATE INDEX IF NOT EXISTS section_geom_line_gix
  ON section USING GIST (geom_line);

-- Sensor: point location of the instrument (antenna for GNSS, wellhead for
-- piezometer, etc.). lat/lon columns already exist; we keep them as the
-- source of truth and provide a generated column for spatial indexing.
ALTER TABLE sensor
  ADD COLUMN IF NOT EXISTS geom_point GEOMETRY(Point, 4326)
    GENERATED ALWAYS AS (
      CASE
        WHEN lat IS NOT NULL AND lon IS NOT NULL
        THEN ST_SetSRID(ST_MakePoint(lon, lat), 4326)
      END
    ) STORED;

CREATE INDEX IF NOT EXISTS sensor_geom_point_gix
  ON sensor USING GIST (geom_point);

-- ---------------------------------------------------------------------------
-- Helper view: sensor_feature — emits a GeoJSON Feature per sensor so the
-- API can return a FeatureCollection with minimal formatting logic in app.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW sensor_feature AS
SELECT
  s.site_id,
  s.sensor_id,
  jsonb_build_object(
    'type', 'Feature',
    'id', s.sensor_id,
    'geometry', CASE
      WHEN s.geom_point IS NOT NULL
      THEN ST_AsGeoJSON(s.geom_point)::jsonb
    END,
    'properties', jsonb_build_object(
      'site_id', s.site_id,
      'sensor_id', s.sensor_id,
      'sensor_type', s.sensor_type::text,
      'structure_id', s.structure_id,
      'section_id', s.section_id,
      'display_name', s.display_name,
      'active', s.active,
      'elev_m', s.elev_m,
      'depth_m', s.depth_m
    )
  ) AS feature
FROM sensor s
WHERE s.active = TRUE;

COMMIT;
