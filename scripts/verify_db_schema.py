"""Check the ERD contract and transactional constraints in an isolated Compose DB.

Uses Python's standard library and the postgres container's psql. All example
values below are invented schema-test values, not AI Hub or student records.
Fixture transactions are rolled back; this does not install seed data.
"""

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXPECT_ERROR = """
CREATE FUNCTION pg_temp.expect_sqlstate(statement text, expected text) RETURNS void
LANGUAGE plpgsql AS $function$
BEGIN
    BEGIN
        EXECUTE statement;
    EXCEPTION WHEN OTHERS THEN
        IF SQLSTATE = expected THEN RETURN; END IF;
        RAISE;
    END;
    RAISE EXCEPTION 'Expected SQLSTATE %, but statement succeeded: %', expected, statement;
END;
$function$;
"""

CORE_CASES = """
INSERT INTO user_account
    (id, role, login_id, password_hash, status, is_demo, created_at, updated_at)
VALUES ('00000000-0000-4000-8000-000000000001', 'PARENT',
        'schema-check@example.invalid', 'schema-test-only', 'ACTIVE', true, now(), now());
INSERT INTO student (id, nickname, grade, is_demo, status, created_at, updated_at)
VALUES ('00000000-0000-4000-8000-000000000002', 'schema-test', 3, true, 'ACTIVE', now(), now());
SELECT pg_temp.expect_sqlstate(
    $$UPDATE user_account SET status = 'INVALID'$$, '23514');
SELECT pg_temp.expect_sqlstate(
    $$UPDATE user_account SET status = NULL$$, '23502');
SELECT pg_temp.expect_sqlstate(
    $$UPDATE student SET user_account_id = '00000000-0000-4000-8000-999999999999'$$, '23503');

INSERT INTO guardianship (id, parent_user_id, student_id, method, status, linked_at)
VALUES ('00000000-0000-4000-8000-000000000003',
        '00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000002',
        'REGISTER', 'LINKED', now());
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO guardianship (id, parent_user_id, student_id, method, status, linked_at)
    SELECT '00000000-0000-4000-8000-000000000004', parent_user_id, student_id,
           method, status, linked_at FROM guardianship
    WHERE id = '00000000-0000-4000-8000-000000000003'
$$, '23505');
INSERT INTO guardianship (id, parent_user_id, student_id, method, status, linked_at, unlinked_at)
SELECT '00000000-0000-4000-8000-000000000005', parent_user_id, student_id,
       method, 'UNLINKED', linked_at, now() FROM guardianship
WHERE id = '00000000-0000-4000-8000-000000000003';

INSERT INTO report_job (id, student_id, period_from, period_to, trigger, status, retry_count, created_at)
VALUES ('00000000-0000-4000-8000-000000000006', '00000000-0000-4000-8000-000000000002',
        '2026-01-01', '2026-01-07', 'SCHEDULE', 'QUEUED', 0, now());
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO report_job (id, student_id, period_from, period_to, trigger, status, retry_count, created_at)
    SELECT '00000000-0000-4000-8000-000000000007', student_id, period_from, period_to,
           trigger, status, retry_count, created_at FROM report_job
    WHERE id = '00000000-0000-4000-8000-000000000006'
$$, '23505');
INSERT INTO report_job (id, student_id, period_from, period_to, trigger, status, retry_count, created_at)
SELECT '00000000-0000-4000-8000-000000000008', student_id, period_from, period_to,
       'REGENERATE', status, retry_count, created_at FROM report_job
WHERE id = '00000000-0000-4000-8000-000000000006';

INSERT INTO model_version (id, kind, name, version, status, created_at)
VALUES ('00000000-0000-4000-8000-000000000009', 'MODEL', 'schema-test', '1', 'ACTIVE', now());
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO model_version (id, kind, name, version, status, created_at)
    VALUES ('00000000-0000-4000-8000-000000000010', 'MODEL', 'schema-test', '2', 'ACTIVE', now())
$$, '23505');
INSERT INTO model_version (id, kind, name, version, status, created_at)
VALUES ('00000000-0000-4000-8000-000000000011', 'MODEL', 'schema-test', '2', 'INACTIVE', now());

INSERT INTO idempotency_record (idempotency_key, user_id, endpoint, request_hash, created_at)
VALUES ('00000000-0000-4000-8000-000000000012', '00000000-0000-4000-8000-000000000001',
        '/schema-test', 'synthetic-request-hash', now());
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO idempotency_record SELECT * FROM idempotency_record
    WHERE idempotency_key = '00000000-0000-4000-8000-000000000012'
$$, '23505');
"""

LEARNING_CASES = """
INSERT INTO mission (id, code, status, demo_only, sort_order, created_by, created_at, updated_at)
VALUES ('00000000-0000-4000-8000-000000000101', 'schema-test', 'DRAFT', true, 0,
        '00000000-0000-4000-8000-000000000001', now(), now());
INSERT INTO mission_version
    (id, mission_id, version, title, subject, grade_min, grade_max, thinking_type,
     input_type, question, created_by, created_at)
VALUES ('00000000-0000-4000-8000-000000000102', '00000000-0000-4000-8000-000000000101',
        1, 'schema-test', 'MATH', 3, 4, 'ANALYZE', 'CHOICE', 'schema validation only',
        '00000000-0000-4000-8000-000000000001', now());
INSERT INTO rubric_version (id, mission_id, version, created_by, created_at)
VALUES ('00000000-0000-4000-8000-000000000103', '00000000-0000-4000-8000-000000000101',
        1, '00000000-0000-4000-8000-000000000001', now());
UPDATE mission SET current_version_id = '00000000-0000-4000-8000-000000000102',
                   current_rubric_version_id = '00000000-0000-4000-8000-000000000103'
WHERE id = '00000000-0000-4000-8000-000000000101';
INSERT INTO rubric_element
    (id, rubric_version_id, code, label, points, good_thought, judge_verified, sort_order)
VALUES ('00000000-0000-4000-8000-000000000104', '00000000-0000-4000-8000-000000000103',
        'e1', 'schema-test', 1, false, false, 0);
INSERT INTO attempt
    (id, student_id, mission_id, mission_version_id, rubric_version_id, grade, status, started_at, updated_at)
VALUES ('00000000-0000-4000-8000-000000000105', '00000000-0000-4000-8000-000000000002',
        '00000000-0000-4000-8000-000000000101', '00000000-0000-4000-8000-000000000102',
        '00000000-0000-4000-8000-000000000103', 3, 'IN_PROGRESS', now(), now());
SELECT pg_temp.expect_sqlstate($$
    UPDATE attempt SET status = 'NOT_STARTED'
    WHERE id = '00000000-0000-4000-8000-000000000105'
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE attempt SET mission_id = '00000000-0000-4000-8000-999999999999'
    WHERE id = '00000000-0000-4000-8000-000000000105'
$$, '23503');
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO attempt
        (id, student_id, mission_id, mission_version_id, rubric_version_id, grade, status, started_at, updated_at)
    SELECT '00000000-0000-4000-8000-000000000106', student_id, mission_id, mission_version_id,
           rubric_version_id, grade, status, started_at, updated_at FROM attempt
    WHERE id = '00000000-0000-4000-8000-000000000105'
$$, '23505');
INSERT INTO attempt
    (id, student_id, mission_id, mission_version_id, rubric_version_id, grade, status, started_at, updated_at)
SELECT '00000000-0000-4000-8000-000000000107', student_id, mission_id, mission_version_id,
       rubric_version_id, grade, 'COMPLETED', started_at, updated_at FROM attempt
WHERE id = '00000000-0000-4000-8000-000000000105';
INSERT INTO answer
    (id, attempt_id, version, input_type, content, dictated_by_guardian, speech_transcribed,
     idempotency_key, submitted_at)
VALUES ('00000000-0000-4000-8000-000000000108', '00000000-0000-4000-8000-000000000105',
        1, 'CHOICE', '{"choiceIds":[]}', false, false, '00000000-0000-4000-8000-000000000109', now());
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO answer (id, attempt_id, version, input_type, content, dictated_by_guardian,
                        speech_transcribed, idempotency_key, submitted_at)
    SELECT '00000000-0000-4000-8000-000000000110', attempt_id, version, input_type, content,
           dictated_by_guardian, speech_transcribed, '00000000-0000-4000-8000-000000000111', submitted_at
    FROM answer WHERE id = '00000000-0000-4000-8000-000000000108'
$$, '23505');
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO answer (id, attempt_id, version, input_type, content, dictated_by_guardian,
                        speech_transcribed, idempotency_key, submitted_at)
    SELECT '00000000-0000-4000-8000-000000000112', attempt_id, 2, input_type, content,
           dictated_by_guardian, speech_transcribed, idempotency_key, submitted_at
    FROM answer WHERE id = '00000000-0000-4000-8000-000000000108'
$$, '23505');
INSERT INTO judgment (id, answer_id, process_status, rubric_version_id, retry_count, created_at)
VALUES ('00000000-0000-4000-8000-000000000113', '00000000-0000-4000-8000-000000000108',
        'PENDING', '00000000-0000-4000-8000-000000000103', 0, now());
SELECT pg_temp.expect_sqlstate($$
    UPDATE judgment SET held_reason = 'UNVERIFIED_SCOPE'
    WHERE id = '00000000-0000-4000-8000-000000000113'
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE judgment SET process_status = 'DONE'
    WHERE id = '00000000-0000-4000-8000-000000000113'
$$, '23514');
UPDATE judgment SET process_status = 'DONE', result = 'CORRECT', method = 'RULE',
                    trial = false, completed_at = now()
WHERE id = '00000000-0000-4000-8000-000000000113';
SELECT pg_temp.expect_sqlstate($$
    UPDATE judgment SET result = 'HELD'
    WHERE id = '00000000-0000-4000-8000-000000000113'
$$, '23514');
UPDATE judgment SET result = 'HELD', held_reason = 'UNVERIFIED_SCOPE'
WHERE id = '00000000-0000-4000-8000-000000000113';
INSERT INTO judgment_element (id, judgment_id, rubric_element_id, verified, satisfied)
VALUES ('00000000-0000-4000-8000-000000000114', '00000000-0000-4000-8000-000000000113',
        '00000000-0000-4000-8000-000000000104', false, false);
SELECT pg_temp.expect_sqlstate($$
    UPDATE judgment_element SET satisfied = true
    WHERE id = '00000000-0000-4000-8000-000000000114'
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE judgment_element SET verified = NULL, satisfied = true
    WHERE id = '00000000-0000-4000-8000-000000000114'
$$, '23502');
UPDATE judgment_element SET verified = true, satisfied = true
WHERE id = '00000000-0000-4000-8000-000000000114';
"""

REPORT_CASES = """
INSERT INTO weekly_report
    (id, job_id, student_id, period_from, period_to, revision, status, created_at)
VALUES ('00000000-0000-4000-8000-000000000201', '00000000-0000-4000-8000-000000000202',
        '00000000-0000-4000-8000-000000000002', '2026-01-01', '2026-01-07', 1, 'RUNNING', now());
SELECT pg_temp.expect_sqlstate($$
    UPDATE weekly_report SET status = 'INVALID'
    WHERE id = '00000000-0000-4000-8000-000000000201'
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE weekly_report SET status = 'COMPLETED'
    WHERE id = '00000000-0000-4000-8000-000000000201'
$$, '23514');
UPDATE weekly_report SET status = 'COMPLETED', state = 'NO_RECORD', generated_at = now()
WHERE id = '00000000-0000-4000-8000-000000000201';
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO weekly_report
        (id, job_id, student_id, period_from, period_to, revision, status, created_at)
    SELECT '00000000-0000-4000-8000-000000000203', job_id, student_id, period_from,
           period_to, 2, 'RUNNING', created_at FROM weekly_report
    WHERE id = '00000000-0000-4000-8000-000000000201'
$$, '23505');
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO weekly_report
        (id, job_id, student_id, period_from, period_to, revision, status, created_at)
    SELECT '00000000-0000-4000-8000-000000000204', '00000000-0000-4000-8000-000000000205',
           student_id, period_from, period_to, revision, 'RUNNING', created_at FROM weekly_report
    WHERE id = '00000000-0000-4000-8000-000000000201'
$$, '23505');
INSERT INTO report_item (id, report_id, item_type, seq, payload, state, verified)
VALUES ('00000000-0000-4000-8000-000000000206', '00000000-0000-4000-8000-000000000201',
        'METRIC', 1, '{}', 'NO_RECORD', false);
SELECT pg_temp.expect_sqlstate($$
    UPDATE report_item SET report_id = '00000000-0000-4000-8000-999999999999'
    WHERE id = '00000000-0000-4000-8000-000000000206'
$$, '23503');
INSERT INTO report_item_evidence (id, item_id, attempt_id, answer_id, answer_version)
VALUES ('00000000-0000-4000-8000-000000000207', '00000000-0000-4000-8000-000000000206',
        '00000000-0000-4000-8000-999999999998', '00000000-0000-4000-8000-999999999997', 1);
"""


def erd_contract():
    result = {}
    database = table = None
    for line in (ROOT / 'docs/design/erd.md').read_text(encoding='utf-8').splitlines():
        match = re.match(r'## [345]\. (\w+_db)', line)
        if match:
            database = match[1]
            result[database] = {}
        match = re.match(r'^  (\w+) \{$', line)
        if match:
            table = match[1]
            result[database][table] = {}
        elif line == '  }':
            table = None
        elif table:
            match = re.match(r'^    (\w+(?:\([^)]*\))?) (\w+)([^\"]*)(?:\"(.*)\")?$', line)
            if not match:
                raise ValueError(f'Unrecognized ERD column: {line}')
            typ, column, flags, comment = match.groups()
            result[database][table][column] = {
                'type': typ,
                'nullable': 'NULL 허용' in (comment or ''),
                'pk': 'PK' in flags,
                'fk': 'FK' in flags,
                'uk': 'UK' in flags,
            }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, help='Isolated Docker Compose project')
    parser.add_argument('--db-user', required=True)
    parser.add_argument('--env-file')
    parser.add_argument('-f', '--file', action='append', dest='files')
    args = parser.parse_args()
    compose = ['docker', 'compose']
    if args.env_file:
        compose += ['--env-file', args.env_file]
    for file in args.files or ['compose.yaml']:
        compose += ['-f', file]
    compose += ['-p', args.project]

    def query(database, statement):
        command = compose + [
            'exec', '-T', 'postgres', 'psql', '-X', '-qAt',
            '-v', 'ON_ERROR_STOP=1', '-U', args.db_user, '-d', database,
        ]
        completed = subprocess.run(
            command, input=statement, text=True, encoding='utf-8',
            capture_output=True, cwd=ROOT, check=False,
        )
        if completed.returncode:
            raise RuntimeError(f'{database}: {completed.stderr.strip()}')
        return completed.stdout.strip()

    checks = 0
    for database, tables in erd_contract().items():
        actual_columns = json.loads(query(database, """
            SELECT json_agg(json_build_object(
                'table', table_name, 'column', column_name, 'type', data_type,
                'nullable', is_nullable, 'default', column_default,
                'length', character_maximum_length))
            FROM information_schema.columns WHERE table_schema = 'public'
            AND table_name NOT IN ('flyway_schema_history', 'alembic_version');
        """))
        actual = {(c['table'], c['column']): c for c in actual_columns or []}
        expected = {(name, col): data for name, cols in tables.items() for col, data in cols.items()}
        assert actual.keys() == expected.keys(), f'{database}: table/column mismatch'
        for key, expected_col in expected.items():
            col = actual[key]
            typ = expected_col['type']
            mapped = {'int': 'integer', 'timestamptz': 'timestamp with time zone',
                      'varchar': 'character varying'}.get(typ, typ)
            if typ.startswith('varchar('):
                mapped = 'character varying'
                assert col['length'] == int(re.search(r'\d+', typ)[0]), key
            assert col['type'] == mapped, (database, key, col['type'], mapped)
            assert (col['nullable'] == 'YES') == expected_col['nullable'], (database, key, 'NULL')
            assert col['default'] is None, (database, key, 'unexpected default')

        constraints = json.loads(query(database, """
            SELECT json_agg(json_build_object('table', r.relname, 'kind', c.contype,
                'columns', (SELECT array_agg(a.attname ORDER BY k.ordinality)
                            FROM unnest(c.conkey) WITH ORDINALITY AS k(num, ordinality)
                            JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.num),
                'definition', pg_get_constraintdef(c.oid)))
            FROM pg_constraint c JOIN pg_class r ON r.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = r.relnamespace
            WHERE n.nspname = 'public' AND r.relname NOT IN ('flyway_schema_history','alembic_version');
        """))
        for name, cols in tables.items():
            own = [c for c in constraints if c['table'] == name]
            pk = [c['columns'] for c in own if c['kind'] == 'p']
            assert pk == [[col for col, data in cols.items() if data['pk']]], (database, name, 'PK')
            actual_fk = {col for c in own if c['kind'] == 'f' for col in c['columns']}
            assert actual_fk == {col for col, data in cols.items() if data['fk']}, (database, name, 'FK')
            for col, data in cols.items():
                if data['uk']:
                    assert any(c['kind'] == 'u' and c['columns'] == [col] for c in own), (name, col, 'UK')
        populated = query(database, ' UNION ALL '.join(
            f"SELECT '{name}' WHERE EXISTS (SELECT 1 FROM {name})" for name in tables
        ) + ';')
        if populated:
            raise RuntimeError(f'{database}: use an empty, isolated verification DB; '
                               f'populated tables: {populated}')
        cases = {'core_db': CORE_CASES, 'learning_db': LEARNING_CASES, 'report_db': REPORT_CASES}[database]
        query(database, 'BEGIN;\n' + EXPECT_ERROR + cases + '\nROLLBACK;')
        negative = cases.count('SELECT pg_temp.expect_sqlstate(')
        checks += negative
        print(f'{database}: {len(tables)} tables / {len(expected)} columns match ERD; '
              f'{negative} negative cases rejected; valid counterparts accepted; fixtures rolled back')
    print(f'PASS: all three schemas; {checks} negative constraint cases')


if __name__ == '__main__':
    main()
