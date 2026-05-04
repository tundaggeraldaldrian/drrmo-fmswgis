-- ------------------------------------------------------------
-- Reset silaydrrmo_db to a pristine state
-- Usage:
--   psql -U postgres -d silaydrrmo_db -f scripts/reset_silaydrrmo_db.sql
-- ------------------------------------------------------------

BEGIN;

-- Drop all application objects
DROP SCHEMA public CASCADE;
CREATE SCHEMA public AUTHORIZATION postgres;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO public;

-- Recreate PostGIS extension required by GeoDjango models
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

COMMIT;
