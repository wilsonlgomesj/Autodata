-- Migration 001 — bootstrap of metadata schema.
-- Delegates to the canonical DDL in metadata/schema.sql so that running
-- migrations from scratch and running schema.sql directly are equivalent.
--
-- Apply with:
--   psql -v ON_ERROR_STOP=1 -f metadata/schema.sql
-- (or) psql -v ON_ERROR_STOP=1 -f metadata/migrations/001_init.sql

\ir ../schema.sql
