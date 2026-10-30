"""Exercise issue #19 migrations on a disposable PostgreSQL server using Flyway.

Uses PGHOST/PGPORT/PGUSER/PGPASSWORD and four new policy_* databases. Refuses
existing database names; never resets or drops databases. Fixtures are invented.
This is an explicit integration check, separate from the #13 CI validator.
"""

import argparse
import json
import os
import re
import subprocess

import psycopg
from psycopg import sql
from verify_db_schema import ROOT, require

# #19 정책 반영 버전(core V7, learning V5)까지만 적용한다. 이후 버전은 check_db_migrations.py가 검사
POLICY_HEAD = {"core": 7, "learning": 5}


def uid(number):
    return f"00000000-0000-4000-8000-{number:012d}"


def query(database, statement):
    with (
        psycopg.connect(
            host=os.environ.get("PGHOST", "127.0.0.1"),
            port=os.environ.get("PGPORT", "5432"),
            user=os.environ["PGUSER"],
            password=os.environ["PGPASSWORD"],
            dbname=database,
            connect_timeout=10,
            autocommit=True,
        ) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(statement, prepare=False)
        result = []
        while True:
            if cursor.description:
                result.extend(cursor.fetchall())
            if not cursor.nextset():
                return result


def snapshot(database, tables):
    return {
        table: query(
            database,
            sql.SQL("SELECT * FROM {} ORDER BY 1").format(sql.Identifier(table)),
        )
        for table in tables
    }


def expect_rejected(database, statement, state):
    try:
        query(database, statement)
    except psycopg.Error as error:
        require(error.sqlstate == state, f"Expected {state}, got {error.sqlstate}: {error}")
    else:
        raise RuntimeError(f"Statement unexpectedly accepted: {statement}")


CORE_FIXTURE = f"""
INSERT INTO user_account
    (id, role, login_id, password_hash, status, is_demo, created_at, updated_at)
VALUES ('{uid(1)}', 'PARENT', 'policy-test@example.invalid', 'synthetic-only',
        'ACTIVE', true, now(), now());
INSERT INTO student (id, nickname, grade, is_demo, status, created_at, updated_at)
VALUES ('{uid(2)}', 'policy-test', 3, true, 'ACTIVE', now(), now());
INSERT INTO guardianship (id, parent_user_id, student_id, method, status, linked_at)
VALUES ('{uid(3)}', '{uid(1)}', '{uid(2)}', 'REGISTER', 'LINKED', now());
INSERT INTO product
    (id, code, name, price, billing_cycle, child_limit, features, active, created_at)
VALUES ('{uid(4)}', 'BASIC', 'synthetic product', 1000, 'MONTHLY', 1, '{{}}', true, now());
INSERT INTO notification_setting (user_id, type, channel, enabled, updated_at)
VALUES ('{uid(1)}', 'REPORT_COMPLETED', 'IN_APP', true, now());
INSERT INTO error_report
    (id, reporter_user_id, target_type, target_id, category, status, created_at)
VALUES ('{uid(5)}', '{uid(1)}', 'REPORT', '{uid(6)}', 'OTHER', 'RECEIVED', now());
"""

LEARNING_FIXTURE = f"""
INSERT INTO mission (id, code, status, demo_only, sort_order, created_by, created_at, updated_at)
VALUES ('{uid(101)}', 'policy-test', 'DRAFT', true, 0, '{uid(1)}', now(), now());
INSERT INTO mission_version
    (id, mission_id, version, title, subject, grade_min, grade_max, thinking_type,
     input_type, question, created_by, created_at)
VALUES ('{uid(102)}', '{uid(101)}', 1, 'synthetic', 'MATH', 3, 4, 'ANALYZE',
        'CHOICE', 'synthetic question only', '{uid(1)}', now());
INSERT INTO rubric_version (id, mission_id, version, created_by, created_at)
VALUES ('{uid(103)}', '{uid(101)}', 1, '{uid(1)}', now());
INSERT INTO attempt
    (id, student_id, mission_id, mission_version_id, rubric_version_id,
     grade, status, started_at, updated_at)
VALUES ('{uid(104)}', '{uid(2)}', '{uid(101)}', '{uid(102)}', '{uid(103)}',
        3, 'IN_PROGRESS', now(), now());
INSERT INTO answer
    (id, attempt_id, version, input_type, content, dictated_by_guardian,
     speech_transcribed, idempotency_key, submitted_at)
VALUES ('{uid(105)}', '{uid(104)}', 1, 'CHOICE', '{{"choiceIds":[]}}',
        false, false, '{uid(106)}', now());
INSERT INTO judgment (id, answer_id, process_status, rubric_version_id, retry_count, created_at)
VALUES ('{uid(107)}', '{uid(105)}', 'PENDING', '{uid(103)}', 0, now());
INSERT INTO followup
    (id, attempt_id, judgment_id, type, question, source, leak_check_passed, created_at)
VALUES ('{uid(108)}', '{uid(104)}', '{uid(107)}', 'TELL_MORE',
        'synthetic followup only', 'LLM', true, now());
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker-network", default="host")
    parser.add_argument("--flyway-host", default="127.0.0.1")
    args = parser.parse_args()
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    images = re.findall(
        r"^  (?:core|learning)-migrate:\s*\n    image: (\S+)", compose, re.MULTILINE
    )
    require(len(images) == 2 and len(set(images)) == 1, "Flyway images must match")
    environment = {
        **os.environ,
        "FLYWAY_USER": os.environ["PGUSER"],
        "FLYWAY_PASSWORD": os.environ["PGPASSWORD"],
    }
    port = os.environ.get("PGPORT", "5432") if args.docker_network == "host" else "5432"

    def flyway(service, database, target=None, failure=None):
        migrations = ROOT / f"backend/{service}-service/src/main/resources/db/migration"
        command = [
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
            images[0],
            f"-url=jdbc:postgresql://{args.flyway_host}:{port}/{database}",
            "-locations=filesystem:/flyway/sql",
            "-outputType=json",
        ]
        if target is not None:
            command.append(f"-target={target}")
        result = subprocess.run(
            [*command, "migrate"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            timeout=120,
        )
        output = result.stdout + result.stderr
        if failure:
            require(
                result.returncode != 0 and failure in output,
                f"Wrong migration failure: {output}",
            )
            return None
        require(result.returncode == 0, f"Migration failed: {output}")
        return json.loads(result.stdout)["migrationsExecuted"]

    names = [
        f"policy_{kind}_{service}"
        for kind in ("empty", "upgrade")
        for service in ("core", "learning")
    ]
    existing = {name for (name,) in query("postgres", "SELECT datname FROM pg_database")}
    require(
        not (set(names) & existing),
        "Use a fresh disposable server: policy databases already exist",
    )
    for name in names:
        query("postgres", sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))

    for service, head, table_count, column_count in [
        ("core", POLICY_HEAD["core"], 34, 306),
        ("learning", POLICY_HEAD["learning"], 19, 156),
    ]:
        database = f"policy_empty_{service}"
        require(
            flyway(service, database, target=head) == head,
            f"{service}: wrong initial migration count",
        )
        history = snapshot(database, ["flyway_schema_history"])
        require(
            flyway(service, database, target=head) == 0, f"{service}: rerun was not a no-op"
        )
        require(
            snapshot(database, ["flyway_schema_history"]) == history,
            "Rerun changed history",
        )
        counts = query(
            database,
            """
            SELECT count(DISTINCT table_name), count(*) FROM information_schema.columns
            WHERE table_schema='public' AND table_name <> 'flyway_schema_history';
        """,
        )
        require(counts == [(table_count, column_count)], f"Unexpected counts: {counts}")
        tables = query(
            database,
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema='public' AND table_name <> 'flyway_schema_history';
        """,
        )
        for (table,) in tables:
            require(
                query(
                    database,
                    sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table)),
                )
                == [(0,)],
                "Migration installed seed data",
            )
        print(
            f"PASS {service}: empty install, {table_count} tables/{column_count} columns, "
            "no seeds, unchanged rerun",
            flush=True,
        )

    core, learning = "policy_upgrade_core", "policy_upgrade_learning"
    flyway("core", core, target=5)
    query(core, CORE_FIXTURE)
    flyway("core", core, target=6)
    query(core, "UPDATE student SET birth_year=2015; UPDATE product SET limits='{}';")
    core_tables = [
        "flyway_schema_history",
        "user_account",
        "student",
        "product",
        "guardianship",
        "notification_setting",
        "error_report",
    ]
    core_guards = [
        (
            "UPDATE student SET birth_year=NULL",
            "UPDATE student SET birth_year=2015",
            "backfill student.birth_year",
        ),
        (
            f"UPDATE student SET user_account_id='{uid(1)}'",
            "UPDATE student SET user_account_id=NULL",
            "review and preserve existing student account links",
        ),
        (
            "UPDATE student SET grade=2",
            "UPDATE student SET grade=3",
            "grades outside 3..6",
        ),
        (
            "UPDATE product SET price=NULL",
            "UPDATE product SET price=1000",
            "backfill product.price",
        ),
        (
            "UPDATE product SET limits=NULL",
            "UPDATE product SET limits='{}'",
            "backfill product.price",
        ),
        (
            "UPDATE guardianship SET method='LINK'",
            "UPDATE guardianship SET method='REGISTER'",
            "existing LINK guardianships",
        ),
        (
            "UPDATE notification_setting SET channel='EMAIL'",
            "UPDATE notification_setting SET channel='IN_APP'",
            "non-IN_APP notification preferences",
        ),
        (
            "UPDATE error_report SET category=NULL",
            "UPDATE error_report SET category='OTHER'",
            "classify existing error_report.category",
        ),
        (
            "UPDATE error_report SET category='OLD_CATEGORY'",
            "UPDATE error_report SET category='OTHER'",
            "classify existing error_report.category",
        ),
    ]

    flyway("learning", learning, target=3)
    query(learning, LEARNING_FIXTURE)
    flyway("learning", learning, target=4)
    query(
        learning,
        f"INSERT INTO followup_bank_question VALUES ('{uid(109)}', 'TELL_MORE', "
        "'synthetic bank only', true, now())",
    )
    learning_tables = [
        "flyway_schema_history",
        "mission",
        "mission_version",
        "rubric_version",
        "attempt",
        "answer",
        "judgment",
        "followup",
        "followup_bank_question",
    ]
    learning_guards = [
        (
            "UPDATE answer SET speech_transcribed=true",
            "UPDATE answer SET speech_transcribed=false",
            "speech-transcribed answers",
        ),
        (
            "UPDATE followup SET source='TEMPLATE'",
            "UPDATE followup SET source='LLM'",
            "existing TEMPLATE followups",
        ),
        (
            "UPDATE followup SET source='BANK'",
            "UPDATE followup SET source='LLM'",
            "map BANK followups",
        ),
        (
            f"UPDATE followup SET bank_question_id='{uid(109)}'",
            "UPDATE followup SET bank_question_id=NULL",
            "map BANK followups",
        ),
    ]
    for service, database, tables, guards in [
        ("core", core, core_tables, core_guards),
        ("learning", learning, learning_tables, learning_guards),
    ]:
        for invalid, restore, message in guards:
            query(database, invalid)
            before = snapshot(database, tables)
            flyway(service, database, target=POLICY_HEAD[service], failure=message)
            require(
                snapshot(database, tables) == before,
                "Rejected migration changed fixture/history",
            )
            query(database, restore)
        print(
            f"PASS {service}: {len(guards)} legacy-data failures rolled back "
            "without changing rows/history",
            flush=True,
        )

    # Simulate an explicitly reviewed mapping, using only invented fixture data.
    query(learning, f"UPDATE followup SET source='BANK', bank_question_id='{uid(109)}'")
    core_before = query(core, "SELECT id, nickname, grade, birth_year FROM student")
    product_before = query(core, "SELECT * FROM product")
    answer_before = query(learning, "SELECT id, content, submitted_at FROM answer")
    followup_before = query(learning, "SELECT * FROM followup")
    require(
        flyway("core", core, target=POLICY_HEAD["core"]) == 1, "core final migration missing"
    )
    require(
        flyway("learning", learning, target=POLICY_HEAD["learning"]) == 1,
        "learning final migration missing",
    )
    require(
        query(core, "SELECT id, nickname, grade, birth_year FROM student") == core_before,
        "Student data changed",
    )
    require(
        query(core, "SELECT * FROM product") == product_before,
        "Historical product data changed",
    )
    require(
        query(learning, "SELECT id, content, submitted_at FROM answer") == answer_before,
        "Answer content changed",
    )
    require(
        query(learning, "SELECT * FROM followup") == followup_before,
        "Followup data changed",
    )
    for service, database, table, column in [
        ("core", core, "student", "user_account_id"),
        ("learning", learning, "answer", "speech_transcribed"),
    ]:
        require(
            query(
                database,
                "SELECT 1 FROM information_schema.columns WHERE table_schema='public' "
                f"AND table_name='{table}' AND column_name='{column}'",
            )
            == [],
            "Retired column remains",
        )
        before = snapshot(database, ["flyway_schema_history"])
        require(
            flyway(service, database, target=POLICY_HEAD[service]) == 0,
            "Upgrade rerun was not a no-op",
        )
        require(
            snapshot(database, ["flyway_schema_history"]) == before,
            "Upgrade rerun changed history",
        )
    print(
        "PASS: reviewed upgrade preserves IDs/content/product values "
        "and removes only retired columns",
        flush=True,
    )

    negatives = [
        (core, "UPDATE student SET birth_year=NULL", "23502"),
        (core, "UPDATE student SET grade=2", "23514"),
        (core, "UPDATE student SET grade=7", "23514"),
        (core, "UPDATE product SET price=NULL", "23502"),
        (core, "UPDATE product SET limits=NULL", "23502"),
        (core, "UPDATE guardianship SET method='LINK'", "23514"),
        (core, "UPDATE notification_setting SET channel='EMAIL'", "23514"),
        (core, "UPDATE notification_setting SET channel='PUSH'", "23514"),
        (core, "UPDATE error_report SET category=NULL", "23502"),
        (core, "UPDATE error_report SET category='INVALID'", "23514"),
        (
            learning,
            "UPDATE followup SET source='TEMPLATE', bank_question_id=NULL",
            "23514",
        ),
        (learning, "UPDATE followup SET bank_question_id=NULL", "23514"),
        (learning, "UPDATE followup SET source='LLM'", "23514"),
        (learning, f"UPDATE followup SET bank_question_id='{uid(999)}'", "23503"),
        (learning, "DELETE FROM followup_bank_question", "23503"),
        (learning, "UPDATE followup_bank_question SET type='INVALID'", "23514"),
        (learning, "UPDATE followup_bank_question SET question=NULL", "23502"),
    ]
    for database, statement, state in negatives:
        expect_rejected(database, statement, state)
    for grade in (3, 6):
        query(core, f"UPDATE student SET grade={grade}")
    for category in (
        "WRONG_JUDGMENT",
        "ODD_QUESTION",
        "MISMATCH",
        "INAPPROPRIATE",
        "OTHER",
    ):
        query(core, f"UPDATE error_report SET category='{category}'")
    for source in ("LLM", "LLM_RETRY"):
        query(learning, f"UPDATE followup SET source='{source}', bank_question_id=NULL")
    query(learning, f"UPDATE followup SET source='BANK', bank_question_id='{uid(109)}'")
    for number, code in enumerate(("FREE", "PREMIUM", "PREMIUM_V2"), start=10):
        query(
            core,
            f"""
            INSERT INTO product
            SELECT '{uid(number)}', '{code}', name, price, billing_cycle, child_limit,
                   features, active, created_at, limits FROM product WHERE id='{uid(4)}';
        """,
        )
    expect_rejected(core, f"UPDATE product SET code='FREE' WHERE id='{uid(4)}'", "23505")
    require(
        query(core, f"SELECT code, price FROM product WHERE id='{uid(4)}'") == [("BASIC", 1000)],
        "Historical product was relabeled",
    )
    print(
        f"PASS: {len(negatives) + 1} invalid writes rejected; "
        "approved codes, grade boundaries and bank links accepted",
        flush=True,
    )
    print(
        "PASS issue #19 migration checks (does not run the #13 CI fixtures or #14 repositories)",
        flush=True,
    )


if __name__ == "__main__":
    main()
