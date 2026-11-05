"""Run the CI migration cycle against a fresh, disposable PostgreSQL server.

Creates core_db, learning_db and report_db with the shared rds-bootstrap.sql (#230), migrates
each database as its migrate role and checks that service roles cannot reach other databases.
Refuses an existing database instead of resetting it. Admin credentials come from
PGHOST/PGPORT/PGUSER/PGPASSWORD.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import URL
from verify_db_schema import ROOT, ValidationError, direct_query, require, verify_schema

BOOTSTRAP = ROOT / "infrastructure/gitops/charts/platform-data/files/postgres"
SERVICES = ("core", "learning", "report")
DATABASES = tuple(f"{service}_db" for service in SERVICES)
HISTORY_TABLES = ("flyway_schema_history", "alembic_version")
# Synthetic role passwords for the disposable CI server only (like schema_ci_temporary).
ROLES = {
    f"{service}_{kind}": f"{service}-{kind}-ci-temporary"
    for service in SERVICES
    for kind in ("migrate", "app")
}


def run(command, **kwargs):
    result = subprocess.run(
        command, text=True, encoding="utf-8", capture_output=True, timeout=120, **kwargs
    )
    if result.returncode:
        raise ValidationError(f"Command failed ({command[0]}):\n{result.stdout}\n{result.stderr}")
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker-network", default="host", help="Flyway network; CI runs on Linux")
    parser.add_argument("--flyway-host", default="127.0.0.1")
    args = parser.parse_args()
    started = time.monotonic()
    host = os.environ.get("PGHOST", "127.0.0.1")
    port = int(os.environ.get("PGPORT", "5432"))
    user = os.environ["PGUSER"]
    query = direct_query(host, port, user)

    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    images = re.findall(r"^  (?:core|learning)-migrate:\s*\n    image: (\S+)", compose, re.M)
    require(
        len(images) == 2 and len(set(images)) == 1,
        "core/learning Flyway image versions in compose.yaml must match",
    )
    image = images[0]
    print(f"Flyway image from compose.yaml: {image}", flush=True)
    run(["docker", "pull", image])
    postgres_image = re.search(r"^  postgres:\s*\n    image: (\S+)", compose, re.M).group(1)
    run(["docker", "pull", postgres_image])

    # Never drop/reset an existing database. This script is only for disposable servers.
    existing = query(
        "postgres",
        "SELECT count(*) FROM pg_database WHERE datname IN ('core_db', 'learning_db', 'report_db');",
    )
    require(existing == "0", "Service databases already exist; use a disposable server")

    flyway_port = port if args.docker_network == "host" else 5432
    role_env = {
        f"{role.upper()}_{key}": value
        for role, password_value in ROLES.items()
        for key, value in (("USER", role), ("PASSWORD", password_value))
    }

    def bootstrap():
        """Run the same SQL as local init and RDS bootstrap; values pass by env name only."""
        env = {
            **os.environ,
            **role_env,
            "PGHOST": args.flyway_host,
            "PGPORT": str(flyway_port),
            "PGDATABASE": "postgres",
        }
        names = ["PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", *role_env]
        output = run(
            ["docker", "run", "--rm", "--network", args.docker_network]
            + [part for name in names for part in ("-e", name)]
            + ["-v", f"{BOOTSTRAP.as_posix()}:/sql:ro", postgres_image]
            + ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-f", "/sql/rds-bootstrap.sql"],
            env=env,
        )
        print(output.rstrip(), flush=True)

    bootstrap()

    def flyway(service, repeat):
        role = f"{service}_migrate"
        flyway_env = {**os.environ, "FLYWAY_USER": role, "FLYWAY_PASSWORD": ROLES[role]}
        migrations = ROOT / f"backend/{service}-service/src/main/resources/db/migration"
        output = run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                args.docker_network,
                "-e",
                "FLYWAY_USER",
                "-e",
                "FLYWAY_PASSWORD",
                "-v",
                f"{migrations.as_posix()}:/flyway/sql:ro",
                image,
                f"-url=jdbc:postgresql://{args.flyway_host}:{flyway_port}/{service}_db",
                "-locations=filesystem:/flyway/sql",
                "-outputType=json",
                "migrate",
            ],
            env=flyway_env,
        )
        result = json.loads(output)
        executed = result.get("migrationsExecuted")
        require(isinstance(executed, int), f"{service}: missing Flyway migrationsExecuted")
        require(
            executed == 0 if repeat else executed > 0,
            f"{service}: unexpected migration count {executed}; repeat={repeat}",
        )
        print(f"{service}: migrationsExecuted={executed}", flush=True)

    report_env = {
        **os.environ,
        "DATABASE_URL": URL.create(
            "postgresql+psycopg",
            username="report_migrate",
            password=ROLES["report_migrate"],
            host=host,
            port=port,
            database="report_db",
        ).render_as_string(hide_password=False),
    }

    def alembic(*arguments):
        run(
            [sys.executable, "-m", "alembic", *arguments],
            cwd=ROOT / "backend/report-service",
            env=report_env,
        )
        print("report: alembic " + " ".join(arguments), flush=True)

    def migrate(repeat=False):
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(flyway, "core", repeat),
                executor.submit(flyway, "learning", repeat),
                executor.submit(alembic, "upgrade", "head"),
            ]
            for future in futures:
                future.result()

    def histories():
        flyway_sql = "SELECT json_agg(h ORDER BY installed_rank) FROM flyway_schema_history h;"
        report_sql = "SELECT json_agg(version_num ORDER BY version_num) FROM alembic_version;"
        return {
            db: query(db, sql)
            for db, sql in {
                "core_db": flyway_sql,
                "learning_db": flyway_sql,
                "report_db": report_sql,
            }.items()
        }

    migrate()
    # Second run as in the RDS procedure: grants on existing tables, history tables revoked.
    bootstrap()
    verify_schema(query)
    before = histories()
    migrate(repeat=True)
    require(histories() == before, "Migration history changed during no-op rerun")
    print("PASS: repeat migration left all histories unchanged", flush=True)

    alembic("downgrade", "base")
    remaining = query(
        "report_db",
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name <> 'alembic_version';
    """,
    )
    require(not remaining, f"report downgrade left tables behind: {remaining}")
    require(
        query("report_db", "SELECT count(*) FROM alembic_version;") == "0",
        "report downgrade left an applied revision",
    )
    alembic("upgrade", "head")
    require(histories() == before, "Migration history differs after report downgrade/upgrade")
    verify_schema(query)
    verify_isolation(host, port, query)
    print(f"PASS: full migration cycle in {time.monotonic() - started:.1f}s", flush=True)


def verify_isolation(host, port, query):
    """Each service role reaches only its own database; app roles get DML only."""
    import psycopg

    def connect(role, database):
        return psycopg.connect(
            host=host,
            port=port,
            user=role,
            password=ROLES[role],
            dbname=database,
            connect_timeout=10,
            autocommit=True,
        )

    for role in ROLES:
        own = role.rsplit("_", 1)[0] + "_db"
        for database in DATABASES:
            try:
                with connect(role, database) as connection:
                    connection.execute("SELECT 1")
                allowed = True
            except psycopg.OperationalError as error:
                require(
                    "permission denied for database" in str(error),
                    f"{role}@{database}: unexpected connection error: {error}",
                )
                allowed = False
            require(allowed == (database == own), f"{role}@{database}: connect allowed={allowed}")

        if role.endswith("_app"):
            missing = query(
                own,
                f"""
                SELECT count(*) FROM pg_tables
                WHERE schemaname = 'public' AND tablename NOT IN {HISTORY_TABLES}
                  AND NOT has_table_privilege('{role}', format('%I.%I', schemaname, tablename),
                                              'SELECT, INSERT, UPDATE, DELETE');
            """,
            )
            require(missing == "0", f"{role}: missing DML on {missing} table(s)")
            history = query(
                own,
                f"""
                SELECT count(*) FROM pg_tables
                WHERE schemaname = 'public' AND tablename IN {HISTORY_TABLES}
                  AND has_table_privilege('{role}', format('%I.%I', schemaname, tablename),
                                          'SELECT, INSERT, UPDATE, DELETE');
            """,
            )
            require(history == "0", f"{role}: migration history table is accessible")
            try:
                with connect(role, own) as connection:
                    connection.execute("CREATE TABLE ci_ddl_denied (id integer)")
                denied = False
            except psycopg.errors.InsufficientPrivilege:
                denied = True
            require(denied, f"{role}: DDL was allowed")
    print(f"PASS: {len(ROLES)} service roles isolated to their own database", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (ValidationError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
