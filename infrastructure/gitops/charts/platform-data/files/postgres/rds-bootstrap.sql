-- #185 RDS bootstrap: service databases and migrate(DDL)/app(DML) roles. Idempotent.
-- Run as the RDS master user through `demo_stack.py rds-bootstrap`, and locally by init.sql (#230) as
-- the container superuser; role names and passwords come from environment variables (ESO Secrets or
-- the local .env), never from this file. Existing role passwords are
-- not changed, so an existing database keeps working.
\set ON_ERROR_STOP on
\set QUIET on

\getenv migrate_user CORE_MIGRATE_USER
\getenv migrate_password CORE_MIGRATE_PASSWORD
\getenv app_user CORE_APP_USER
\getenv app_password CORE_APP_PASSWORD
\set db core_db
\ir rds-bootstrap-db.sql

\getenv migrate_user LEARNING_MIGRATE_USER
\getenv migrate_password LEARNING_MIGRATE_PASSWORD
\getenv app_user LEARNING_APP_USER
\getenv app_password LEARNING_APP_PASSWORD
\set db learning_db
\ir rds-bootstrap-db.sql

\getenv migrate_user REPORT_MIGRATE_USER
\getenv migrate_password REPORT_MIGRATE_PASSWORD
\getenv app_user REPORT_APP_USER
\getenv app_password REPORT_APP_PASSWORD
\set db report_db
\ir rds-bootstrap-db.sql

\connect postgres
-- Summary without names or passwords.
SELECT d.datname,
       has_database_privilege('public', d.oid, 'CONNECT') AS public_connect,
       (SELECT count(*) FROM pg_roles r
         WHERE has_database_privilege(r.oid, d.oid, 'CONNECT') AND NOT r.rolsuper
           AND r.rolname NOT LIKE 'rds%' AND r.rolname NOT LIKE 'pg\_%' AND r.rolname <> current_user) AS login_roles
FROM pg_database d WHERE d.datname IN ('core_db', 'learning_db', 'report_db') ORDER BY d.datname;
