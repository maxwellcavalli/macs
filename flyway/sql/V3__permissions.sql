-- V3__permissions.sql
-- Ensure role 'agent' can use the schema (if present). Run safely even if role doesn't exist.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='agent') THEN
    GRANT USAGE ON SCHEMA public TO agent;
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO agent;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO agent;
  END IF;
END$$;

