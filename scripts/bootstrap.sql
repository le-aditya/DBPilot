-- DBPilot cluster bootstrap.
--
-- On a fresh machine, run as the postgres superuser:
--   psql -U postgres -h localhost -f scripts/bootstrap.sql
--
-- Idempotent: safe to re-run after a reset. Change the password below before
-- running, and put the same value in backend/.env.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dbpilot_app') THEN
    -- CREATEROLE lets DBPilot mint a per-project read-only role at upload time
    -- (design document section 6, layer 4). On PostgreSQL 16+ CREATEROLE is
    -- scoped to roles this role created, so it cannot touch postgres.
    CREATE ROLE dbpilot_app WITH LOGIN PASSWORD 'change_me_now' CREATEROLE CREATEDB;
  END IF;
END
$$;

SELECT 'CREATE DATABASE dbpilot OWNER dbpilot_app'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'dbpilot')\gexec

SELECT 'CREATE DATABASE dbpilot_test OWNER dbpilot_app'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'dbpilot_test')\gexec

\c dbpilot
CREATE SCHEMA IF NOT EXISTS dbpilot AUTHORIZATION dbpilot_app;
REVOKE ALL ON SCHEMA public FROM PUBLIC;

\c dbpilot_test
CREATE SCHEMA IF NOT EXISTS dbpilot AUTHORIZATION dbpilot_app;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
