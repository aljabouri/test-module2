-- KonformOS app role — INV-ORG-01.
-- The postgres image creates POSTGRES_USER as a SUPERUSER, and superusers
-- silently bypass Row-Level Security (even with FORCE ROW LEVEL SECURITY).
-- The API therefore connects as this NOSUPERUSER role: it owns the database
-- (so Alembic migrations work) but RLS policies fully apply to it.
CREATE ROLE konformos LOGIN PASSWORD 'konformos_dev'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
CREATE DATABASE konformos OWNER konformos;
