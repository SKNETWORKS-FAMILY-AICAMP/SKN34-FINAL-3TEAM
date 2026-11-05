-- Included by rds-bootstrap.sql once per database with :db, :migrate_user, :app_user and passwords set.
\connect postgres

SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'migrate_user', :'migrate_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'migrate_user') \gexec
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'app_user') \gexec
-- The master user needs SET on the migrate role to manage its default privileges (PostgreSQL 16+).
SELECT format('GRANT %I TO CURRENT_USER WITH INHERIT FALSE, SET TRUE', :'migrate_user')
WHERE NOT pg_has_role(current_user, :'migrate_user', 'SET') \gexec

SELECT format('CREATE DATABASE %I', :'db')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'db') \gexec
REVOKE CONNECT, TEMPORARY ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db" TO CURRENT_USER, :"migrate_user", :"app_user";

\connect :db
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO :"migrate_user";
GRANT USAGE ON SCHEMA public TO :"app_user";

SET ROLE :"migrate_user";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_user";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO :"app_user";
-- Objects that already exist (re-run against a migrated database).
SELECT format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I.%I TO %I', schemaname, tablename, :'app_user')
FROM pg_tables WHERE schemaname = 'public' AND tableowner = current_user
  AND tablename NOT IN ('flyway_schema_history', 'alembic_version') \gexec
SELECT format('GRANT USAGE, SELECT, UPDATE ON SEQUENCE %I.%I TO %I', schemaname, sequencename, :'app_user')
FROM pg_sequences WHERE schemaname = 'public' AND sequenceowner = current_user \gexec
SELECT format('REVOKE ALL ON %I.%I FROM %I', schemaname, tablename, :'app_user')
FROM pg_tables WHERE schemaname = 'public' AND tablename IN ('flyway_schema_history', 'alembic_version') \gexec
RESET ROLE;
