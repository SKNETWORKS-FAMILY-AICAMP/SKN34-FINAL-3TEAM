"""Check the ERD contract and constraints in empty, isolated PostgreSQL databases.

Compose mode uses the container's psql; direct mode uses report-service's psycopg.
All fixtures are invented schema-test values, not AI Hub or student records.
Fixture transactions are rolled back; this does not install seed data.
Only reference rows published by migrations (MIGRATION_SEED_ROWS) may exist beforehand.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ValidationError(RuntimeError):
    """A schema contract violation, including when Python runs with -O."""


def require(condition, message):
    if not condition:
        raise ValidationError(message)


# Reference rows that migrations publish on purpose (#235 V25 consent documents 1.0, #388 COMMUNITY 1.0,
# #389 V35 reward rules, #485 V43 THEME_ON_TIME·THEME_FINISHED rules, #415 V39 TERMS·PRIVACY 1.1). Only these exact keys may exist before the fixtures run;
# anything else means a non-isolated DB.
MIGRATION_SEED_ROWS = {
    "core_db": {
        "consent_document": (
            "00000000-0000-4000-8000-000002350001",
            "00000000-0000-4000-8000-000002350002",
            "00000000-0000-4000-8000-000002350003",
            "00000000-0000-4000-8000-000003880001",
            "00000000-0000-4000-8000-000004150001",
            "00000000-0000-4000-8000-000004150002",
        ),
        "reward_rule": (
            "MISSION_COMPLETED",
            "REVIEW_VIEWED",
            "COMMUNITY_POSTED",
            "REACTION_GIVEN",
            "THEME_COMPLETED",
            "THEME_ON_TIME",
            "THEME_FINISHED",
        ),
    },
}
# Seed tables whose primary key is not "id".
SEED_KEY_COLUMNS = {"reward_rule": "event_type"}


# Student-owned visibility switches start off for every new student (ERD 3.1).
PRIVATE_BY_DEFAULT_COLUMNS = {
    ("student", "parent_sharing_enabled"),
    ("student", "community_enabled"),
}


def populated_sql(tables, seeds):
    """Name each table holding rows other than its migration seed rows."""
    parts = []
    for name in tables:
        ids = seeds.get(name)
        key = SEED_KEY_COLUMNS.get(name, "id")
        where = f" WHERE {key} NOT IN ({', '.join(repr(i) for i in ids)})" if ids else ""
        parts.append(f"SELECT '{name}' WHERE EXISTS (SELECT 1 FROM {name}{where})")
    return " UNION ALL ".join(parts) + ";"


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
-- #36: nullable legacy password and explicit Google identity/session constraints.
UPDATE user_account SET password_hash = NULL,
    oauth_provider = 'GOOGLE', oauth_subject = 'schema-google-sub'
WHERE id = '00000000-0000-4000-8000-000000000001';
SELECT pg_temp.expect_sqlstate($$UPDATE user_account SET oauth_subject = NULL$$, '23514');
SELECT pg_temp.expect_sqlstate($$UPDATE user_account SET oauth_provider = 'INVALID'$$, '23514');
INSERT INTO auth_session(id,user_id,role,version,expires_at,created_at)
VALUES ('00000000-0000-4000-8000-000000000018', '00000000-0000-4000-8000-000000000001',
        'PARENT',1,now()+interval '7 days',now());
SELECT pg_temp.expect_sqlstate($$UPDATE auth_session SET role = 'STUDENT'$$, '23514');
SELECT pg_temp.expect_sqlstate($$UPDATE auth_session SET version = 0$$, '23514');
-- #45: live profile and reauth target/completion contracts.
SELECT pg_temp.expect_sqlstate($$INSERT INTO reauth_challenge(id,user_id,session_id,session_version,purpose,state_hash,expires_at)
VALUES ('00000000-0000-4000-8000-000000000021','00000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000018',1,'PIN_CHANGE','schema-invalid',now())$$, '23514');
INSERT INTO reauth_challenge(id,user_id,session_id,session_version,purpose,state_hash,expires_at)
VALUES ('00000000-0000-4000-8000-000000000021','00000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000018',1,'WITHDRAWAL','schema-state',now());
SELECT pg_temp.expect_sqlstate($$INSERT INTO reauth_grant(token_hash,challenge_id,expires_at)
VALUES ('hash','00000000-0000-4000-8000-999999999999',now())$$, '23503');

SELECT pg_temp.expect_sqlstate($$UPDATE auth_session SET user_id = '00000000-0000-4000-8000-999999999999'$$, '23503');
INSERT INTO refresh_token(id,user_id,session_id,token_hash,expires_at,created_at)
VALUES ('00000000-0000-4000-8000-000000000019', '00000000-0000-4000-8000-000000000001',
        '00000000-0000-4000-8000-000000000018','schema-refresh-hash',now()+interval '7 days',now());
SELECT pg_temp.expect_sqlstate($$UPDATE refresh_token SET session_id = '00000000-0000-4000-8000-999999999999'$$, '23503');
INSERT INTO student (pin_failed_count, id, nickname, grade, birth_year, is_demo, status, created_at, updated_at)
VALUES (0, '00000000-0000-4000-8000-000000000002', 'schema-test', 3, 2015, true,
        'ACTIVE', now(), now());
SELECT pg_temp.expect_sqlstate(
    $$UPDATE user_account SET status = 'INVALID'$$, '23514');
SELECT pg_temp.expect_sqlstate(
    $$UPDATE user_account SET status = NULL$$, '23502');
SELECT pg_temp.expect_sqlstate($$UPDATE student SET birth_year = NULL$$, '23514');
SELECT pg_temp.expect_sqlstate($$UPDATE student SET grade = 2$$, '23514');
SELECT pg_temp.expect_sqlstate($$UPDATE student SET grade = 10$$, '23514');
-- #432 (P26): stored grades run to middle school third grade (9) for the March promotion.
UPDATE student SET grade = 9;
UPDATE student SET grade = 3;
INSERT INTO student_grade_promotion (student_id, school_year, from_grade, to_grade, promoted_at)
SELECT id, 2027, 3, 4, now() FROM student;
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO student_grade_promotion (student_id, school_year, from_grade, to_grade, promoted_at)
    SELECT id, 2027, 4, 5, now() FROM student
$$, '23505');
SELECT pg_temp.expect_sqlstate($$UPDATE student_grade_promotion SET to_grade = 5$$, '23514');
SELECT pg_temp.expect_sqlstate($$UPDATE student_grade_promotion SET from_grade = 9, to_grade = 10$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE student_grade_promotion SET student_id = '00000000-0000-4000-8000-999999999999'
$$, '23503');
DELETE FROM student_grade_promotion;
SELECT pg_temp.expect_sqlstate($$UPDATE student SET pin_failed_count=-1$$, '23514');
SELECT pg_temp.expect_sqlstate($$UPDATE student SET pin_failed_count=NULL$$, '23502');
SELECT pg_temp.expect_sqlstate($$UPDATE student SET community_enabled=NULL$$, '23502');
INSERT INTO student_device(id,parent_user_id,token_hash,label,created_at,expires_at)
VALUES ('00000000-0000-4000-8000-000000000030','00000000-0000-4000-8000-000000000001','device-hash','synthetic',now(),now()+interval '90 days');
SELECT pg_temp.expect_sqlstate($$UPDATE student_device SET expires_at=created_at$$, '23514');
SELECT pg_temp.expect_sqlstate($$UPDATE student_device SET parent_user_id='00000000-0000-4000-8000-999999999999'$$, '23503');
SELECT pg_temp.expect_sqlstate($$INSERT INTO student_device(id,parent_user_id,token_hash,label,created_at,expires_at)
SELECT '00000000-0000-4000-8000-000000000031',parent_user_id,token_hash,label,created_at,expires_at FROM student_device$$, '23505');
INSERT INTO student_device_child(device_id,student_id) VALUES('00000000-0000-4000-8000-000000000030','00000000-0000-4000-8000-000000000002');
SELECT pg_temp.expect_sqlstate($$INSERT INTO student_device_child SELECT * FROM student_device_child$$, '23505');
SELECT pg_temp.expect_sqlstate($$UPDATE student_device_child SET student_id='00000000-0000-4000-8000-999999999999'$$, '23503');

INSERT INTO guardianship (id, parent_user_id, student_id, method, status, linked_at)
VALUES ('00000000-0000-4000-8000-000000000003',
        '00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000002',
        'REGISTER', 'LINKED', now());
SELECT pg_temp.expect_sqlstate(
    $$UPDATE guardianship SET student_id = '00000000-0000-4000-8000-999999999999'$$, '23503');
SELECT pg_temp.expect_sqlstate($$UPDATE guardianship SET method = 'LINK'$$, '23514');
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

-- #289: only one current parent; transfer request state and reauthentication targets.
INSERT INTO user_account(id,role,login_id,status,is_demo,created_at,updated_at)
VALUES ('00000000-0000-4000-8000-000000000289','PARENT','recipient@example.invalid','ACTIVE',true,now(),now());
SELECT pg_temp.expect_sqlstate($$INSERT INTO guardianship(id,parent_user_id,student_id,method,status,linked_at)
VALUES ('00000000-0000-4000-8000-000000000290','00000000-0000-4000-8000-000000000289',
        '00000000-0000-4000-8000-000000000002','TRANSFER','LINKED',now())$$,'23505');
SELECT pg_temp.expect_sqlstate($$UPDATE guardianship SET transferred_at=now() WHERE status='LINKED'$$,'23514');
INSERT INTO guardian_transfer(id,student_id,sender_id,recipient_id,include_conversations,status,created_at)
VALUES ('00000000-0000-4000-8000-000000000291','00000000-0000-4000-8000-000000000002',
        '00000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000289',false,'PENDING',now());
SELECT pg_temp.expect_sqlstate($$UPDATE guardian_transfer SET recipient_id=sender_id$$,'23514');
SELECT pg_temp.expect_sqlstate($$UPDATE guardian_transfer SET status='ACCEPTED'$$,'23514');
SELECT pg_temp.expect_sqlstate($$UPDATE guardian_transfer SET resolved_at=now()$$,'23514');
SELECT pg_temp.expect_sqlstate($$INSERT INTO guardian_transfer
SELECT '00000000-0000-4000-8000-000000000292',student_id,sender_id,recipient_id,include_conversations,status,created_at,resolved_at
FROM guardian_transfer$$,'23505');
UPDATE guardian_transfer SET status='ACCEPTED',resolved_at=now();
UPDATE reauth_challenge SET purpose='GUARDIAN_PASSWORD';
UPDATE reauth_challenge SET purpose='TRANSFER_ACCEPT';
SELECT pg_temp.expect_sqlstate($$UPDATE reauth_challenge SET student_id='00000000-0000-4000-8000-000000000002'$$,'23514');
UPDATE reauth_challenge SET purpose='CHILD_TRANSFER',student_id='00000000-0000-4000-8000-000000000002';
SELECT pg_temp.expect_sqlstate($$UPDATE reauth_challenge SET student_id=NULL$$,'23514');
UPDATE reauth_challenge SET purpose='WITHDRAWAL',student_id=NULL;

INSERT INTO notification_setting (user_id, type, channel, enabled, updated_at)
VALUES ('00000000-0000-4000-8000-000000000001', 'REPORT_COMPLETED', 'IN_APP', true, now());
INSERT INTO notification_setting (user_id, type, channel, enabled, updated_at)
VALUES ('00000000-0000-4000-8000-000000000001', 'REPORT_FAILED', 'IN_APP', false, now());
SELECT pg_temp.expect_sqlstate($$UPDATE notification_setting SET type = 'UNKNOWN_EVENT'$$, '23514');
SELECT pg_temp.expect_sqlstate(
    $$UPDATE notification_setting SET channel = 'EMAIL'$$, '23514');
SELECT pg_temp.expect_sqlstate(
    $$UPDATE notification_setting SET channel = 'PUSH'$$, '23514');

INSERT INTO error_report
    (id, reporter_user_id, target_type, target_id, category, status, created_at)
VALUES ('00000000-0000-4000-8000-000000000013', '00000000-0000-4000-8000-000000000001',
        'REPORT', '00000000-0000-4000-8000-000000000014', 'OTHER', 'RECEIVED', now());
SELECT pg_temp.expect_sqlstate($$UPDATE error_report SET category = NULL$$, '23502');
SELECT pg_temp.expect_sqlstate($$UPDATE error_report SET category = 'INVALID'$$, '23514');
UPDATE error_report SET category = 'WRONG_JUDGMENT';
UPDATE error_report SET category = 'ODD_QUESTION';
UPDATE error_report SET category = 'MISMATCH';
UPDATE error_report SET category = 'INAPPROPRIATE';
UPDATE error_report SET category = 'OTHER';

INSERT INTO product
    (id, code, name, price, billing_cycle, child_limit, features, limits, active, created_at)
VALUES ('00000000-0000-4000-8000-000000000015', 'FREE', 'schema-test', 0, 'MONTHLY', 1,
        '{}', '{"dailyMissions":1}', true, now()),
       ('00000000-0000-4000-8000-000000000016', 'PREMIUM', 'schema-test', 14900, 'MONTHLY', 1,
        '{}', '{"dailyFeedback":50}', true, now()),
       ('00000000-0000-4000-8000-000000000017', 'PREMIUM_V2', 'schema-test', 15000, 'MONTHLY', 1,
        '{}', '{"dailyFeedback":60}', false, now());
SELECT pg_temp.expect_sqlstate($$UPDATE product SET price = NULL$$, '23502');
SELECT pg_temp.expect_sqlstate($$UPDATE product SET limits = NULL$$, '23502');
SELECT pg_temp.expect_sqlstate($$
    UPDATE product SET code = 'FREE' WHERE id = '00000000-0000-4000-8000-000000000016'
$$, '23505');

INSERT INTO report_job
    (id, student_id, period_type, period_from, period_to, trigger, status, retry_count, created_at)
VALUES ('00000000-0000-4000-8000-000000000006', '00000000-0000-4000-8000-000000000002',
        'WEEKLY', '2026-01-01', '2026-01-07', 'SCHEDULE', 'QUEUED', 0, now());
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO report_job
        (id, student_id, period_type, period_from, period_to, trigger, status, retry_count, created_at)
    SELECT '00000000-0000-4000-8000-000000000007', student_id, period_type, period_from, period_to,
           trigger, status, retry_count, created_at FROM report_job
    WHERE id = '00000000-0000-4000-8000-000000000006'
$$, '23505');
INSERT INTO report_job
    (id, student_id, period_type, period_from, period_to, trigger, status, retry_count, created_at)
SELECT '00000000-0000-4000-8000-000000000008', student_id, period_type, period_from, period_to,
       'REGENERATE', status, retry_count, created_at FROM report_job
WHERE id = '00000000-0000-4000-8000-000000000006';
-- P24 (#390): a daily job of the same period_from is a different scheduled job; a daily job is one day.
INSERT INTO report_job
    (id, student_id, period_type, period_from, period_to, trigger, status, retry_count, created_at)
VALUES ('00000000-0000-4000-8000-000000000096', '00000000-0000-4000-8000-000000000002',
        'DAILY', '2026-01-01', '2026-01-01', 'SCHEDULE', 'QUEUED', 0, now());
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO report_job
        (id, student_id, period_type, period_from, period_to, trigger, status, retry_count, created_at)
    VALUES ('00000000-0000-4000-8000-000000000097', '00000000-0000-4000-8000-000000000002',
            'DAILY', '2026-01-02', '2026-01-03', 'REGENERATE', 'QUEUED', 0, now())
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE report_job SET period_type = NULL WHERE id = '00000000-0000-4000-8000-000000000096'
$$, '23502');

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
-- #392: a pinned report conversation keeps report_id/report_revision together on one target day.
INSERT INTO conversation
    (id, parent_user_id, student_id, period_from, period_to, created_at, updated_at, report_id, report_revision)
VALUES ('00000000-0000-4000-8000-000000000392', '00000000-0000-4000-8000-000000000001',
        '00000000-0000-4000-8000-000000000002', '2026-11-08', '2026-11-08', now(), now(),
        '00000000-0000-4000-8000-000000000393', 1);
SELECT pg_temp.expect_sqlstate($$
    UPDATE conversation SET report_revision = NULL WHERE id = '00000000-0000-4000-8000-000000000392'
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE conversation SET report_revision = 0 WHERE id = '00000000-0000-4000-8000-000000000392'
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE conversation SET period_to = '2026-11-09' WHERE id = '00000000-0000-4000-8000-000000000392'
$$, '23514');

-- #389 V35 points and look unlocks: seeded rules, signed ledger, one row per event, non-negative balance.
SELECT pg_temp.expect_sqlstate($$UPDATE reward_rule SET amount = 0 WHERE event_type = 'MISSION_COMPLETED'$$, '23514');
SELECT pg_temp.expect_sqlstate($$UPDATE reward_rule SET daily_cap = 0 WHERE event_type = 'REACTION_GIVEN'$$, '23514');
SELECT pg_temp.expect_sqlstate($$INSERT INTO reward_rule(event_type,amount,daily_cap,active,updated_at)
VALUES ('UNLOCK',1,NULL,true,now())$$, '23514');
INSERT INTO reward_point_balance(student_id,balance,updated_at)
VALUES ('00000000-0000-4000-8000-000000000002',0,now());
SELECT pg_temp.expect_sqlstate($$UPDATE reward_point_balance SET balance = -1$$, '23514');
INSERT INTO reward_point_ledger(id,student_id,event_type,source_key,amount,created_at)
VALUES ('00000000-0000-4000-8000-000000003891','00000000-0000-4000-8000-000000000002','MISSION_COMPLETED','mission-1',10,now());
-- #485 V43: same-day solve and weekly finish are earn events with their own rules.
INSERT INTO reward_point_ledger(id,student_id,event_type,source_key,amount,created_at)
VALUES ('00000000-0000-4000-8000-000000004851','00000000-0000-4000-8000-000000000002','THEME_ON_TIME','2026-11-09:MON',5,now()),
       ('00000000-0000-4000-8000-000000004852','00000000-0000-4000-8000-000000000002','THEME_FINISHED','2026-11-09',10,now());
SELECT pg_temp.expect_sqlstate($$INSERT INTO reward_point_ledger(id,student_id,event_type,source_key,amount,created_at)
VALUES ('00000000-0000-4000-8000-000000004853','00000000-0000-4000-8000-000000000002','THEME_ON_TIME','2026-11-09:MON',-5,now())$$, '23514');
SELECT pg_temp.expect_sqlstate($$INSERT INTO reward_point_ledger(id,student_id,event_type,source_key,amount,created_at)
VALUES ('00000000-0000-4000-8000-000000003892','00000000-0000-4000-8000-000000000002','MISSION_COMPLETED','mission-1',10,now())$$, '23505');
SELECT pg_temp.expect_sqlstate($$INSERT INTO reward_point_ledger(id,student_id,event_type,source_key,amount,created_at)
VALUES ('00000000-0000-4000-8000-000000003893','00000000-0000-4000-8000-000000000002','UNLOCK','THEME:sea',100,now())$$, '23514');
SELECT pg_temp.expect_sqlstate($$INSERT INTO reward_point_ledger(id,student_id,event_type,source_key,amount,created_at)
VALUES ('00000000-0000-4000-8000-000000003894','00000000-0000-4000-8000-000000000002','REVIEW_VIEWED','2026-11-02',-10,now())$$, '23514');
INSERT INTO reward_point_ledger(id,student_id,event_type,source_key,amount,created_at)
VALUES ('00000000-0000-4000-8000-000000003895','00000000-0000-4000-8000-000000000002','UNLOCK','THEME:sea',-100,now());
INSERT INTO look_item(id,code,slot,name,price_points,asset_key,status,created_by,created_at,updated_at)
VALUES ('00000000-0000-4000-8000-000000003896','SCHEMA_HAT','HAT','schema-test',10,'',
        'ON_SALE','00000000-0000-4000-8000-000000000001',now(),now());
SELECT pg_temp.expect_sqlstate($$UPDATE look_item SET code = 'THEME:sea'$$, '23514');
SELECT pg_temp.expect_sqlstate($$UPDATE look_item SET slot = 'THEME'$$, '23514');
SELECT pg_temp.expect_sqlstate($$UPDATE look_item SET price_points = 0$$, '23514');
INSERT INTO student_look_unlock(student_id,item_key,ledger_id,unlocked_at)
VALUES ('00000000-0000-4000-8000-000000000002','THEME:sea','00000000-0000-4000-8000-000000003895',now());
SELECT pg_temp.expect_sqlstate($$INSERT INTO student_look_unlock(student_id,item_key,ledger_id,unlocked_at)
VALUES ('00000000-0000-4000-8000-000000000002','SCHEMA_HAT','00000000-0000-4000-8000-000000003895',now())$$, '23505');
SELECT pg_temp.expect_sqlstate($$INSERT INTO student_look_unlock(student_id,item_key,ledger_id,unlocked_at)
VALUES ('00000000-0000-4000-8000-000000000002','SCHEMA_HAT','00000000-0000-4000-8000-999999999999',now())$$, '23503');
INSERT INTO student_look_equipment(student_id,slot,look_item_id,updated_at)
VALUES ('00000000-0000-4000-8000-000000000002','HAT','00000000-0000-4000-8000-000000003896',now());
SELECT pg_temp.expect_sqlstate($$UPDATE student_look_equipment SET slot = 'THEME'$$, '23514');
-- #555 V47: furniture skins are look items in the DESK/WALL/WARDROBE slots; the wall holds frames in slots 1..6.
INSERT INTO look_item(id,code,slot,name,price_points,asset_key,status,created_by,created_at,updated_at)
VALUES ('00000000-0000-4000-8000-000000005551','SCHEMA_DESK','DESK','schema-test',10,'',
        'ON_SALE','00000000-0000-4000-8000-000000000001',now(),now());
INSERT INTO student_look_equipment(student_id,slot,look_item_id,updated_at)
VALUES ('00000000-0000-4000-8000-000000000002','DESK','00000000-0000-4000-8000-000000005551',now());
SELECT pg_temp.expect_sqlstate($$UPDATE look_item SET slot = 'ROOM' WHERE code = 'SCHEMA_DESK'$$, '23514');
INSERT INTO room_frame_slot(student_id,slot_no,theme_id,theme_week_start,saved_at)
VALUES ('00000000-0000-4000-8000-000000000002',1,'00000000-0000-4000-8000-000000005552','2026-11-02',now());
SELECT pg_temp.expect_sqlstate($$INSERT INTO room_frame_slot(student_id,slot_no,theme_id,theme_week_start,saved_at)
VALUES ('00000000-0000-4000-8000-000000000002',2,'00000000-0000-4000-8000-000000005552','2026-11-02',now())$$, '23505');
SELECT pg_temp.expect_sqlstate($$INSERT INTO room_frame_slot(student_id,slot_no,theme_id,theme_week_start,saved_at)
VALUES ('00000000-0000-4000-8000-000000000002',7,'00000000-0000-4000-8000-000000005553','2026-11-02',now())$$, '23514');
SELECT pg_temp.expect_sqlstate($$INSERT INTO room_frame_slot(student_id,slot_no,theme_id,theme_week_start,saved_at)
VALUES ('00000000-0000-4000-8000-000000000002',3,'00000000-0000-4000-8000-000000005553','2026-11-03',now())$$, '23514');
SELECT pg_temp.expect_sqlstate($$INSERT INTO room_frame_slot(student_id,slot_no,theme_id,theme_week_start,saved_at)
VALUES ('00000000-0000-4000-8000-999999999999',1,'00000000-0000-4000-8000-000000005553','2026-11-02',now())$$, '23503');
"""

LEARNING_CASES = """
INSERT INTO mission (id, code, status, demo_only, sort_order, created_by, source, created_at, updated_at)
VALUES ('00000000-0000-4000-8000-000000000101', 'schema-test', 'DRAFT', true, 0,
        '00000000-0000-4000-8000-000000000001', 'MANUAL', now(), now());
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
    (id, student_id, mission_id, mission_version_id, rubric_version_id,
     grade, status, started_at, updated_at, context)
VALUES ('00000000-0000-4000-8000-000000000105', '00000000-0000-4000-8000-000000000002',
        '00000000-0000-4000-8000-000000000101', '00000000-0000-4000-8000-000000000102',
        '00000000-0000-4000-8000-000000000103', 3, 'IN_PROGRESS', now(), now(), 'EXTRA');
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
        (id, student_id, mission_id, mission_version_id, rubric_version_id,
         grade, status, started_at, updated_at, context)
    SELECT '00000000-0000-4000-8000-000000000106', student_id, mission_id, mission_version_id,
           rubric_version_id, grade, status, started_at, updated_at, context FROM attempt
    WHERE id = '00000000-0000-4000-8000-000000000105'
$$, '23505');
INSERT INTO attempt
    (id, student_id, mission_id, mission_version_id, rubric_version_id,
     grade, status, started_at, updated_at, context)
SELECT '00000000-0000-4000-8000-000000000107', student_id, mission_id, mission_version_id,
       rubric_version_id, grade, 'COMPLETED', started_at, updated_at, context FROM attempt
WHERE id = '00000000-0000-4000-8000-000000000105';
INSERT INTO answer
    (id, attempt_id, version, input_type, content, dictated_by_guardian,
     idempotency_key, submitted_at)
VALUES ('00000000-0000-4000-8000-000000000108', '00000000-0000-4000-8000-000000000105',
        1, 'CHOICE', '{"choiceIds":[]}', false,
        '00000000-0000-4000-8000-000000000109', now());
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO answer (id, attempt_id, version, input_type, content, dictated_by_guardian,
                        idempotency_key, submitted_at)
    SELECT '00000000-0000-4000-8000-000000000110', attempt_id, version, input_type, content,
           dictated_by_guardian,
           '00000000-0000-4000-8000-000000000111', submitted_at
    FROM answer WHERE id = '00000000-0000-4000-8000-000000000108'
$$, '23505');
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO answer (id, attempt_id, version, input_type, content, dictated_by_guardian,
                        idempotency_key, submitted_at)
    SELECT '00000000-0000-4000-8000-000000000112', attempt_id, 2, input_type, content,
           dictated_by_guardian, idempotency_key, submitted_at
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

INSERT INTO followup_bank_question (id, type, question, active, created_at)
VALUES ('00000000-0000-4000-8000-000000000115', 'TELL_MORE',
        'synthetic bank question only', true, now());
UPDATE followup_bank_question SET type = 'ONE_STEP_MORE';
UPDATE followup_bank_question SET type = 'LOOK_AGAIN';
UPDATE followup_bank_question SET type = 'TELL_MORE';
SELECT pg_temp.expect_sqlstate(
    $$UPDATE followup_bank_question SET type = 'INVALID'$$, '23514');
SELECT pg_temp.expect_sqlstate(
    $$UPDATE followup_bank_question SET question = NULL$$, '23502');
INSERT INTO followup
    (id, attempt_id, judgment_id, type, question, source, leak_check_passed, created_at,
     bank_question_id)
VALUES ('00000000-0000-4000-8000-000000000116', '00000000-0000-4000-8000-000000000105',
        '00000000-0000-4000-8000-000000000113', 'TELL_MORE', 'synthetic bank question only',
        'BANK', true, now(), '00000000-0000-4000-8000-000000000115');
SELECT pg_temp.expect_sqlstate($$UPDATE followup SET bank_question_id = NULL$$, '23514');
SELECT pg_temp.expect_sqlstate($$UPDATE followup SET source = 'LLM'$$, '23514');
SELECT pg_temp.expect_sqlstate($$UPDATE followup SET source = 'LLM_RETRY'$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE followup SET source = 'TEMPLATE', bank_question_id = NULL
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE followup SET bank_question_id = '00000000-0000-4000-8000-999999999999'
$$, '23503');
SELECT pg_temp.expect_sqlstate($$DELETE FROM followup_bank_question$$, '23503');
UPDATE followup SET source = 'LLM', bank_question_id = NULL;
UPDATE followup SET source = 'LLM_RETRY';
UPDATE followup SET source = 'BANK', bank_question_id = '00000000-0000-4000-8000-000000000115';

-- #385 주간 테마: 순환 FK(테마 → 현재 버전)는 작성 트랜잭션에서 커밋 때로 미룬다. 학년은 #438 V15·V16부터 grade(G3~G6)
SET CONSTRAINTS fk_weekly_theme_current_version_id DEFERRED;
INSERT INTO weekly_theme
    (id, grade, week_start, status, current_version_id, created_by, created_at, updated_at)
VALUES ('00000000-0000-4000-8000-000000000120', 'G3', '2026-11-09', 'PUBLISHED',
        '00000000-0000-4000-8000-000000000121', '00000000-0000-4000-8000-000000000001', now(), now());
INSERT INTO weekly_theme_version (id, theme_id, version, title, intro, created_by, created_at)
VALUES ('00000000-0000-4000-8000-000000000121', '00000000-0000-4000-8000-000000000120', 1,
        'schema-test', 'synthetic intro only', '00000000-0000-4000-8000-000000000001', now());
SET CONSTRAINTS fk_weekly_theme_current_version_id IMMEDIATE;
UPDATE weekly_theme SET published_version_id = current_version_id, review_version_id = current_version_id
WHERE id = '00000000-0000-4000-8000-000000000120';
INSERT INTO weekly_theme_day (theme_version_id, day_of_week, mission_id)
VALUES ('00000000-0000-4000-8000-000000000121', 1, '00000000-0000-4000-8000-000000000101');
SELECT pg_temp.expect_sqlstate($$
    UPDATE weekly_theme SET grade = 'G3_4' WHERE id = '00000000-0000-4000-8000-000000000120'
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE weekly_theme SET grade = NULL WHERE id = '00000000-0000-4000-8000-000000000120'
$$, '23502');
SELECT pg_temp.expect_sqlstate($$
    UPDATE weekly_theme SET status = 'ARCHIVED' WHERE id = '00000000-0000-4000-8000-000000000120'
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE weekly_theme SET week_start = '2026-11-10' WHERE id = '00000000-0000-4000-8000-000000000120'
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE weekly_theme SET current_version_id = '00000000-0000-4000-8000-999999999999'
    WHERE id = '00000000-0000-4000-8000-000000000120'
$$, '23503');
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO weekly_theme
        (id, grade, week_start, status, current_version_id, created_by, created_at, updated_at)
    SELECT '00000000-0000-4000-8000-000000000122', grade, week_start, 'PUBLISHED',
           current_version_id, created_by, created_at, updated_at FROM weekly_theme
    WHERE id = '00000000-0000-4000-8000-000000000120'
$$, '23505');
INSERT INTO weekly_theme
    (id, grade, week_start, status, current_version_id, created_by, created_at, updated_at)
SELECT '00000000-0000-4000-8000-000000000123', grade, week_start, 'DRAFT',
       current_version_id, created_by, created_at, updated_at FROM weekly_theme
WHERE id = '00000000-0000-4000-8000-000000000120';
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO weekly_theme_version (id, theme_id, version, title, intro, created_by, created_at)
    SELECT '00000000-0000-4000-8000-000000000124', theme_id, version, title, intro, created_by, created_at
    FROM weekly_theme_version WHERE id = '00000000-0000-4000-8000-000000000121'
$$, '23505');
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO weekly_theme_day (theme_version_id, day_of_week, mission_id)
    VALUES ('00000000-0000-4000-8000-000000000121', 6, '00000000-0000-4000-8000-000000000101')
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO weekly_theme_day (theme_version_id, day_of_week, mission_id)
    VALUES ('00000000-0000-4000-8000-000000000121', 2, '00000000-0000-4000-8000-000000000101')
$$, '23505');
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO weekly_theme_day (theme_version_id, day_of_week, mission_id)
    VALUES ('00000000-0000-4000-8000-000000000121', 2, '00000000-0000-4000-8000-999999999999')
$$, '23503');
INSERT INTO theme_review_view (student_id, week_start, theme_id, viewed_at)
VALUES ('00000000-0000-4000-8000-000000000002', '2026-11-09',
        '00000000-0000-4000-8000-000000000120', now());
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO theme_review_view (student_id, week_start, theme_id, viewed_at)
    VALUES ('00000000-0000-4000-8000-000000000002', '2026-11-09',
            '00000000-0000-4000-8000-000000000120', now())
$$, '23505');
-- #438 다른 학년(G4)은 같은 주에 따로 게시할 수 있음 (게시 UK는 학년·주)
SET CONSTRAINTS fk_weekly_theme_current_version_id DEFERRED;
INSERT INTO weekly_theme
    (id, grade, week_start, status, current_version_id, created_by, created_at, updated_at)
VALUES ('00000000-0000-4000-8000-000000000125', 'G4', '2026-11-09', 'PUBLISHED',
        '00000000-0000-4000-8000-000000000126', '00000000-0000-4000-8000-000000000001', now(), now());
INSERT INTO weekly_theme_version (id, theme_id, version, title, intro, created_by, created_at)
VALUES ('00000000-0000-4000-8000-000000000126', '00000000-0000-4000-8000-000000000125', 1,
        'schema-test', 'synthetic intro only', '00000000-0000-4000-8000-000000000001', now());
SET CONSTRAINTS fk_weekly_theme_current_version_id IMMEDIATE;
-- #438 시작·종료 이야기 열람: 학생·주·종류당 1행, 종류는 INTRO·OUTRO
INSERT INTO theme_story_view (student_id, week_start, kind, theme_id, viewed_at)
VALUES ('00000000-0000-4000-8000-000000000002', '2026-11-09', 'INTRO',
        '00000000-0000-4000-8000-000000000120', now());
INSERT INTO theme_story_view (student_id, week_start, kind, theme_id, viewed_at)
VALUES ('00000000-0000-4000-8000-000000000002', '2026-11-09', 'OUTRO',
        '00000000-0000-4000-8000-000000000120', now());
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO theme_story_view (student_id, week_start, kind, theme_id, viewed_at)
    VALUES ('00000000-0000-4000-8000-000000000002', '2026-11-09', 'INTRO',
            '00000000-0000-4000-8000-000000000120', now())
$$, '23505');
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO theme_story_view (student_id, week_start, kind, theme_id, viewed_at)
    VALUES ('00000000-0000-4000-8000-000000000003', '2026-11-09', 'REVIEW',
            '00000000-0000-4000-8000-000000000120', now())
$$, '23514');
-- #559 기념 액자: 회차(학생·테마·주)당 1개, 주는 월요일, 테마·버전 FK
INSERT INTO theme_frame (id, student_id, theme_id, theme_week_start, theme_version_id, awarded_at, seen_at, created_at)
VALUES ('00000000-0000-4000-8000-000005590001', '00000000-0000-4000-8000-000000000002',
        '00000000-0000-4000-8000-000000000120', '2026-11-09', '00000000-0000-4000-8000-000000000121', now(), NULL, now());
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO theme_frame (id, student_id, theme_id, theme_week_start, theme_version_id, awarded_at, seen_at, created_at)
    VALUES ('00000000-0000-4000-8000-000005590002', '00000000-0000-4000-8000-000000000002',
            '00000000-0000-4000-8000-000000000120', '2026-11-09', '00000000-0000-4000-8000-000000000121', now(), now(), now())
$$, '23505');
SELECT pg_temp.expect_sqlstate($$
    UPDATE theme_frame SET theme_week_start = '2026-11-10' WHERE id = '00000000-0000-4000-8000-000005590001'
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE theme_frame SET theme_version_id = '00000000-0000-4000-8000-999999999999' WHERE id = '00000000-0000-4000-8000-000005590001'
$$, '23503');
SELECT pg_temp.expect_sqlstate($$
    UPDATE theme_frame SET theme_id = '00000000-0000-4000-8000-999999999999' WHERE id = '00000000-0000-4000-8000-000005590001'
$$, '23503');
-- #484 큰 질문 정답 고르기: 학생·주(월요일)당 1행, 고를 때 금요일 문제는 있는 미션
INSERT INTO theme_answer_pick (student_id, week_start, theme_id, mission_id, pick, correct, picked_at)
VALUES ('00000000-0000-4000-8000-000000000002', '2026-11-09', '00000000-0000-4000-8000-000000000120',
        '00000000-0000-4000-8000-000000000101', 'synthetic-candidate', false, now());
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO theme_answer_pick (student_id, week_start, theme_id, mission_id, pick, correct, picked_at)
    VALUES ('00000000-0000-4000-8000-000000000002', '2026-11-09', '00000000-0000-4000-8000-000000000120',
            '00000000-0000-4000-8000-000000000101', 'synthetic-other', true, now())
$$, '23505');
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO theme_answer_pick (student_id, week_start, theme_id, mission_id, pick, correct, picked_at)
    VALUES ('00000000-0000-4000-8000-000000000003', '2026-11-10', '00000000-0000-4000-8000-000000000120',
            '00000000-0000-4000-8000-000000000101', 'synthetic-candidate', false, now())
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO theme_answer_pick (student_id, week_start, theme_id, mission_id, pick, correct, picked_at)
    VALUES ('00000000-0000-4000-8000-000000000003', '2026-11-09', '00000000-0000-4000-8000-000000000120',
            '00000000-0000-4000-8000-999999999999', 'synthetic-candidate', false, now())
$$, '23503');
-- #438 테마 초안: 학년·주(월요일)·출처·상태 CHECK, 자동 초안은 학년·주당 1개, 채택 테마 1개
INSERT INTO theme_draft (id, grade, week_start, source, status, input, attempts, created_at, updated_at)
VALUES ('00000000-0000-4000-8000-000000000127', 'G3', '2026-11-16', 'AUTO', 'GENERATING',
        '{"missions":[]}', 0, now(), now());
INSERT INTO theme_draft (id, grade, week_start, source, status, requested_by, input, attempts, created_at, updated_at)
VALUES ('00000000-0000-4000-8000-000000000128', 'G3', '2026-11-16', 'ADMIN', 'GENERATING',
        '00000000-0000-4000-8000-000000000001', '{"missions":[]}', 0, now(), now());
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO theme_draft (id, grade, week_start, source, status, input, attempts, created_at, updated_at)
    VALUES ('00000000-0000-4000-8000-000000000129', 'G3', '2026-11-16', 'AUTO', 'GENERATING',
            '{"missions":[]}', 0, now(), now())
$$, '23505');
SELECT pg_temp.expect_sqlstate($$
    UPDATE theme_draft SET grade = 'G7' WHERE id = '00000000-0000-4000-8000-000000000128'
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE theme_draft SET week_start = '2026-11-17' WHERE id = '00000000-0000-4000-8000-000000000128'
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE theme_draft SET source = 'CORE' WHERE id = '00000000-0000-4000-8000-000000000128'
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE theme_draft SET status = 'DONE' WHERE id = '00000000-0000-4000-8000-000000000128'
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE theme_draft SET attempts = -1 WHERE id = '00000000-0000-4000-8000-000000000128'
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE theme_draft SET theme_id = '00000000-0000-4000-8000-999999999999'
    WHERE id = '00000000-0000-4000-8000-000000000128'
$$, '23503');
UPDATE theme_draft SET status = 'ADOPTED', theme_id = '00000000-0000-4000-8000-000000000120'
WHERE id = '00000000-0000-4000-8000-000000000128';
SELECT pg_temp.expect_sqlstate($$
    UPDATE theme_draft SET theme_id = '00000000-0000-4000-8000-000000000120'
    WHERE id = '00000000-0000-4000-8000-000000000127'
$$, '23505');
-- 시도 context: 테마 컨텍스트는 테마·주 시작일이 함께, EXTRA는 둘 다 없음
SELECT pg_temp.expect_sqlstate($$
    UPDATE attempt SET context = NULL WHERE id = '00000000-0000-4000-8000-000000000107'
$$, '23502');
SELECT pg_temp.expect_sqlstate($$
    UPDATE attempt SET context = 'DAILY' WHERE id = '00000000-0000-4000-8000-000000000107'
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE attempt SET context = 'THEME_DAY' WHERE id = '00000000-0000-4000-8000-000000000107'
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE attempt SET theme_id = '00000000-0000-4000-8000-000000000120', theme_week_start = '2026-11-09'
    WHERE id = '00000000-0000-4000-8000-000000000107'
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE attempt SET context = 'THEME_REVIEW', theme_id = '00000000-0000-4000-8000-999999999999',
                       theme_week_start = '2026-11-09'
    WHERE id = '00000000-0000-4000-8000-000000000107'
$$, '23503');
UPDATE attempt SET context = 'THEME_DAY', theme_id = '00000000-0000-4000-8000-000000000120',
                   theme_week_start = '2026-11-09'
WHERE id = '00000000-0000-4000-8000-000000000107';
-- #386 community: one post per student and mission, fixed status and reaction sets, reactions need a post.
INSERT INTO community_post
    (id, student_id, mission_id, attempt_id, answer_id, status, created_at, status_changed_at)
VALUES ('00000000-0000-4000-8000-000003860001', '00000000-0000-4000-8000-000000000002',
        '00000000-0000-4000-8000-000000000101', '00000000-0000-4000-8000-000000000105',
        '00000000-0000-4000-8000-000000000108', 'VISIBLE', now(), now());
SELECT pg_temp.expect_sqlstate($$
    UPDATE community_post SET status = 'HIDDEN'
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO community_post
        (id, student_id, mission_id, attempt_id, answer_id, status, created_at, status_changed_at)
    SELECT '00000000-0000-4000-8000-000003860002', student_id, mission_id,
           '00000000-0000-4000-8000-000000000107', answer_id, status, created_at, status_changed_at
    FROM community_post
$$, '23505');
INSERT INTO community_reaction (id, post_id, student_id, reaction, created_at)
VALUES ('00000000-0000-4000-8000-000003860003', '00000000-0000-4000-8000-000003860001',
        '00000000-0000-4000-8000-000000000003', 'NEW_IDEA', now());
SELECT pg_temp.expect_sqlstate($$
    UPDATE community_reaction SET reaction = 'LIKE'
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO community_reaction (id, post_id, student_id, reaction, created_at)
    SELECT '00000000-0000-4000-8000-000003860004', post_id, student_id, reaction, created_at
    FROM community_reaction
$$, '23505');
SELECT pg_temp.expect_sqlstate($$
    UPDATE community_reaction SET post_id = '00000000-0000-4000-8000-999999999999'
$$, '23503');
INSERT INTO community_visibility (student_id, visible, reason, updated_at)
VALUES ('00000000-0000-4000-8000-000000000002', false, 'CONSENT', now());
SELECT pg_temp.expect_sqlstate($$
    UPDATE community_visibility SET reason = 'OTHER'
$$, '23514');
-- #466 knowledge store (erd 4.5, no embedding since V17)
INSERT INTO knowledge_dataset (version, status, source, chunk_count, relation_count, created_at)
VALUES ('kn-20261111-01', 'LOADING', '{}', 0, 0, now());
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO knowledge_dataset (version, status, source, chunk_count, relation_count, created_at)
    VALUES ('v1', 'LOADING', '{}', 0, 0, now())
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE knowledge_dataset SET status = 'ACTIVE'
$$, '23514');
UPDATE knowledge_dataset SET status = 'ACTIVE', activated_at = now();
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO knowledge_dataset (version, status, source, chunk_count, relation_count, created_at, activated_at)
    VALUES ('kn-20261111-02', 'ACTIVE', '{}', 0, 0, now(), now())
$$, '23505');
INSERT INTO knowledge_chunk
    (dataset_version, id, kind, standard_code, grades, semesters, text, record, content_hash, source)
VALUES ('kn-20261111-01', '4수01-01', 'STANDARD', '4수01-01', '{3}', '{3-1}', 'schema-test', '{}',
        repeat('a', 64), '{}');
INSERT INTO knowledge_chunk (dataset_version, id, kind, thinking_type, grades, semesters, text, record, content_hash, source)
VALUES ('kn-20261111-01', 'SOLVE', 'THINKING_TYPE', 'SOLVE', '{}', '{}', 'schema-test', '{}', repeat('b', 64), '{}');
SELECT pg_temp.expect_sqlstate($$
    UPDATE knowledge_chunk SET grades = '{2}' WHERE id = '4수01-01'
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE knowledge_chunk SET content_hash = repeat('G', 64) WHERE id = '4수01-01'
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE knowledge_chunk SET kind = 'VECTOR' WHERE id = '4수01-01'
$$, '23514');
INSERT INTO knowledge_standard_semester (dataset_version, standard_code, semester, grade)
VALUES ('kn-20261111-01', '4수01-01', '3-1', 3);
SELECT pg_temp.expect_sqlstate($$
    UPDATE knowledge_standard_semester SET semester = '4-1'
$$, '23514');
INSERT INTO knowledge_fits (dataset_version, standard_code, thinking_type, reason, reviewed_by, reviewed_at)
VALUES ('kn-20261111-01', '4수01-01', 'SOLVE', 'schema-test', 'schema-test', now());
SELECT pg_temp.expect_sqlstate($$
    UPDATE knowledge_fits SET thinking_type = 'ANALYZE'
$$, '23503');
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO knowledge_prerequisite
        (dataset_version, standard_code, prerequisite_code, reason, reviewed_by, reviewed_at)
    VALUES ('kn-20261111-01', '4수01-01', '4수01-01', 'schema-test', 'schema-test', now())
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO knowledge_covers (dataset_version, standard_code, content_id, reviewed_by, reviewed_at)
    VALUES ('kn-20261111-01', '4수01-01', 'missing', 'schema-test', now())
$$, '23503');
-- #563: memory search document constraints and valid READY counterpart.
INSERT INTO memory_search_doc(id,attempt_id,student_id,theme_id,theme_week_start,content_text,status,retry_count,created_at)
VALUES ('00000000-0000-4000-8000-000005630001','00000000-0000-4000-8000-000000000107',
'00000000-0000-4000-8000-000000000002','00000000-0000-4000-8000-000000000120','2026-11-09','synthetic','PENDING',0,now());
SELECT pg_temp.expect_sqlstate($$UPDATE memory_search_doc SET status='OTHER'$$,'23514');
SELECT pg_temp.expect_sqlstate($$UPDATE memory_search_doc SET status='READY'$$,'23514');
SELECT pg_temp.expect_sqlstate($$UPDATE memory_search_doc SET status='PROCESSING'$$,'23514');
SELECT pg_temp.expect_sqlstate($$UPDATE memory_search_doc SET retry_count=-1$$,'23514');
SELECT pg_temp.expect_sqlstate($$UPDATE memory_search_doc SET attempt_id='00000000-0000-4000-8000-999999999999'$$,'23503');
SELECT pg_temp.expect_sqlstate($$UPDATE memory_search_doc SET theme_id='00000000-0000-4000-8000-999999999999'$$,'23503');
SELECT pg_temp.expect_sqlstate($$INSERT INTO memory_search_doc SELECT '00000000-0000-4000-8000-000005630002',attempt_id,student_id,theme_id,theme_week_start,content_text,embedding,embedding_model,status,retry_count,lease_until,created_at,embedded_at FROM memory_search_doc$$,'23505');
UPDATE memory_search_doc SET status='READY',embedding=('[1,' || repeat('0,',1534) || '0]')::vector,embedding_model='schema-test',embedded_at=now();
SELECT pg_temp.expect_sqlstate($$UPDATE memory_search_doc SET embedding_model=NULL$$,'23514');
SELECT pg_temp.expect_sqlstate($$UPDATE memory_search_doc SET embedded_at=NULL$$,'23514');
DELETE FROM memory_search_doc;

"""

REPORT_CASES = """
INSERT INTO weekly_report
    (id, job_id, student_id, period_from, period_to, revision, status, created_at, period_type)
VALUES ('00000000-0000-4000-8000-000000000201', '00000000-0000-4000-8000-000000000202',
        '00000000-0000-4000-8000-000000000002', '2026-01-01', '2026-01-07', 1, 'RUNNING', now(), 'WEEKLY');
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
        (id, job_id, student_id, period_from, period_to, revision, status, created_at, period_type)
    SELECT '00000000-0000-4000-8000-000000000203', job_id, student_id, period_from,
           period_to, 2, 'RUNNING', created_at, period_type FROM weekly_report
    WHERE id = '00000000-0000-4000-8000-000000000201'
$$, '23505');
SELECT pg_temp.expect_sqlstate($$
    INSERT INTO weekly_report
        (id, job_id, student_id, period_from, period_to, revision, status, created_at, period_type)
    SELECT '00000000-0000-4000-8000-000000000204', '00000000-0000-4000-8000-000000000205',
           student_id, period_from, period_to, revision, 'RUNNING', created_at, period_type FROM weekly_report
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
INSERT INTO report_job_guard(job_id,student_id,period_from,period_to,failure_reason,created_at,period_type)
VALUES ('00000000-0000-4000-8000-000000000099','00000000-0000-4000-8000-000000000002',
        '2026-10-19','2026-10-25','REPORT_NOT_CREATED',now(),'WEEKLY');
SELECT pg_temp.expect_sqlstate($$UPDATE report_job_guard SET period_to=period_from$$, '23514');
SELECT pg_temp.expect_sqlstate($$UPDATE report_job_guard SET failure_reason='INVALID'$$, '23514');
SELECT pg_temp.expect_sqlstate($$INSERT INTO report_job_guard SELECT * FROM report_job_guard$$, '23505');
INSERT INTO report_deletion_guard
    (student_id, scope, cutoff_at, deletion_request_id, status, updated_at)
VALUES ('00000000-0000-4000-8000-000000000002', 'RECORDS', now(),
        '00000000-0000-4000-8000-000000000208', 'PENDING', now());
SELECT pg_temp.expect_sqlstate($$
    UPDATE report_deletion_guard SET scope = 'INVALID'
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE report_deletion_guard SET status = 'INVALID'
$$, '23514');
SELECT pg_temp.expect_sqlstate($$
    UPDATE report_deletion_guard SET cutoff_at = NULL
$$, '23502');
UPDATE report_deletion_guard SET scope = 'PROFILE', status = 'COMPLETED';
"""


def allowed_values(comment):
    """Read explicit CHECK[A] / CHECK[A|B] or legacy A|B code lists only."""
    comment = comment or ""
    code = r"[A-Za-z][A-Za-z0-9_]*"
    if "CHECK[" in comment:
        annotations = re.findall(r"CHECK\[([^\]]*)\]", comment)
        require(
            comment.count("CHECK[") == 1
            and len(annotations) == 1
            and re.fullmatch(code + r"(?:\|" + code + r")*", annotations[0]),
            f"Malformed ERD CHECK annotation: {comment}",
        )
        return set(annotations[0].split("|"))
    values = re.search(r"\b" + code + r"(?:\|" + code + r")+\b", comment)
    return set(values[0].split("|")) if values else None


def erd_contract(text=None):
    result = {}
    database = table = None
    if text is None:
        text = (ROOT / "docs/design/erd.md").read_text(encoding="utf-8")
    for line in text.splitlines():
        match = re.match(r"## [345]\. (\w+_db)", line)
        if match:
            database = match[1]
            result[database] = {}
        match = re.match(r"^  (\w+) \{$", line)
        if match:
            table = match[1]
            result[database][table] = {}
        elif line == "  }":
            table = None
        elif table:
            match = re.match(r"^    (\w+(?:\([^)]*\))?(?:\[\])?) (\w+)([^\"]*)(?:\"(.*)\")?$", line)
            if not match:
                raise ValueError(f"Unrecognized ERD column: {line}")
            typ, column, flags, comment = match.groups()
            result[database][table][column] = {
                "type": typ,
                "nullable": "NULL 허용" in (comment or ""),
                "pk": "PK" in flags,
                "fk": "FK" in flags,
                "uk": "UK" in flags,
                "values": allowed_values(comment),
            }
    require(
        set(result) == {"core_db", "learning_db", "report_db"},
        "ERD must define core_db, learning_db and report_db",
    )
    require(all(result.values()), "ERD database sections must not be empty")
    # ERD 4.2 explicitly shares these code sets instead of repeating the values.
    for db, table, column, source_table, source_column in [
        ("core_db", "notification_setting", "type", "notification", "type"),
        ("core_db", "correction", "target_type", "error_report", "target_type"),
        ("learning_db", "answer", "input_type", "mission_version", "input_type"),
    ]:
        require(
            table in result[db] and source_table in result[db],
            f"{db}: missing ERD table for shared CHECK values: {table}/{source_table}",
        )
        values = result[db][source_table][source_column]["values"]
        require(values, f"{db}.{source_table}.{source_column}: missing CHECK values")
        result[db][table][column]["values"] = values
    return result


def index_contract(text):
    """Read section 6, including its mission_version table override."""
    result = {db: [] for db in ("core_db", "learning_db", "report_db")}
    section = re.search(r"^## 6\. .*?\n(.*?)(?=^## \d+\.|\Z)", text, re.M | re.S)
    require(section is not None, "ERD section 6 (indexes) is missing")
    for line in section[1].splitlines():
        if not line.startswith("|"):
            continue
        cells = [value.strip() for value in line.strip("|").split("|")]
        if cells[0] == "DB" or cells[0].startswith("---"):
            continue
        require(
            len(cells) == 4 and cells[0] + "_db" in result, f"Unrecognized ERD index row: {line}"
        )
        database = cells[0] + "_db"
        table = cells[1].strip("`")
        specifications = re.findall(r"`([^`]+)`", cells[2])
        require(
            specifications and re.sub(r"`[^`]+`|[,\s]", "", cells[2]) == "",
            f"Unrecognized ERD index specifications: {cells[2]}",
        )
        for spec in specifications:
            match = re.fullmatch(r"(?:(\w+)\s+)?\(([\w, ]+)\)(?:\s+WHERE\s+(.+))?", spec)
            require(match is not None, f"Unrecognized ERD index: {spec}")
            result[database].append(
                {
                    "table": match[1] or table,
                    "columns": [column.strip() for column in match[2].split(",")],
                    "predicate": match[3] or "",
                }
            )
    require(all(result.values()), "ERD index section must cover all three databases")
    return result


def canonical_expression(expression):
    """Ignore PostgreSQL display casts/parentheses, preserving quoted literal values."""
    tokens = re.split(r"('(?:[^']|'')*')", expression)
    for index in range(0, len(tokens), 2):
        tokens[index] = re.sub(
            r"::(?:character varying|text)(?:\[\])?", "", tokens[index], flags=re.I
        )
        tokens[index] = re.sub(r"[\s()]", "", tokens[index]).lower()
    return "".join(tokens)


def check_allowed_values(database, tables, constraints):
    count = 0
    for table, columns in tables.items():
        for column, spec in columns.items():
            if not spec["values"]:
                continue
            candidates = [
                c
                for c in constraints
                if c["table"] == table and c["kind"] == "c" and c["columns"] == [column]
            ]
            matched = False
            for constraint in candidates:
                expression = canonical_expression(constraint["expression"])
                match = re.fullmatch(
                    re.escape(column) + r"=anyarray\[('(?:[^']|'')*'(?:,'(?:[^']|'')*')*)\]",
                    expression,
                ) or re.fullmatch(re.escape(column) + r"=('(?:[^']|'')*')", expression)
                if match:
                    values = {
                        value.replace("''", "'")
                        for value in re.findall(r"'((?:[^']|'')*)'", match[1])
                    }
                    require(
                        values == spec["values"],
                        f"{database}.{table}.{column}: CHECK allowed values differ; "
                        f"expected={sorted(spec['values'])} actual={sorted(values)}",
                    )
                    require(
                        constraint["validated"], f"{database}.{table}.{column}: CHECK is NOT VALID"
                    )
                    matched = True
            require(matched, f"{database}.{table}.{column}: missing matching CHECK allowed values")
            count += 1
    return count


def check_indexes(database, expected, actual):
    for spec in expected:
        matches = [
            index
            for index in actual
            if index["table"] == spec["table"]
            and index["columns"] == spec["columns"]
            and canonical_expression(index["predicate"] or "")
            == canonical_expression(spec["predicate"])
            and index["valid"]
            and index["ready"]
            and index["method"] == "btree"
        ]
        require(
            matches,
            f"{database}.{spec['table']}: missing ERD index "
            f"({', '.join(spec['columns'])}) WHERE {spec['predicate'] or '<none>'}",
        )
    return len(expected)


def compose_query(args):
    compose = ["docker", "compose"]
    if args.env_file:
        compose += ["--env-file", args.env_file]
    for file in args.files or ["compose.yaml"]:
        compose += ["-f", file]
    compose += ["-p", args.project]

    def query(database, statement):
        command = compose + [
            "exec",
            "-T",
            "postgres",
            "psql",
            "-X",
            "-qAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            args.db_user,
            "-d",
            database,
        ]
        completed = subprocess.run(
            command,
            input=statement,
            text=True,
            encoding="utf-8",
            capture_output=True,
            cwd=ROOT,
            check=False,
        )
        if completed.returncode:
            raise RuntimeError(f"{database}: {completed.stderr.strip()}")
        return completed.stdout.strip()

    return query


def direct_query(host, port, user):
    try:
        import psycopg
    except ImportError as error:
        raise ValidationError(
            "Direct mode requires psycopg; use report-service uv environment"
        ) from error

    def query(database, statement):
        try:
            with psycopg.connect(
                host=host,
                port=port,
                user=user,
                dbname=database,
                password=os.environ.get("PGPASSWORD"),
                connect_timeout=10,
                autocommit=True,
            ) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(statement, prepare=False)
                    values = []
                    while True:
                        if cursor.description:
                            for row in cursor.fetchall():
                                value = row[0]
                                values.append(
                                    value if isinstance(value, str) else json.dumps(value)
                                )
                        if not cursor.nextset():
                            break
                    return "\n".join(values)
        except psycopg.Error as error:
            raise ValidationError(f"{database}: {error}") from error

    return query


def verify_schema(query):
    text = (ROOT / "docs/design/erd.md").read_text(encoding="utf-8")
    contracts = erd_contract(text)
    indexes = index_contract(text)
    checks = enum_count = index_count = 0
    for database, tables in contracts.items():
        actual_columns = json.loads(
            query(
                database,
                """
            SELECT json_agg(json_build_object(
                'table', table_name, 'column', column_name, 'type', data_type,
                'nullable', is_nullable, 'default', column_default,
                'length', character_maximum_length, 'udt', udt_name,
                'formatted', (SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a
                              WHERE a.attrelid = format('public.%I', table_name)::regclass
                                AND a.attname = column_name)))
            FROM information_schema.columns WHERE table_schema = 'public'
            AND table_name NOT IN ('flyway_schema_history', 'alembic_version');
        """,
            )
        )
        actual = {(c["table"], c["column"]): c for c in actual_columns or []}
        expected = {
            (name, col): data for name, cols in tables.items() for col, data in cols.items()
        }
        require(
            actual.keys() == expected.keys(),
            f"{database}: table/column mismatch; "
            f"missing={sorted(expected.keys() - actual.keys())} "
            f"unexpected={sorted(actual.keys() - expected.keys())}",
        )
        for key, expected_col in expected.items():
            col = actual[key]
            typ = expected_col["type"]
            mapped = {
                "int": "integer",
                "timestamptz": "timestamp with time zone",
                "varchar": "character varying",
            }.get(typ, typ)
            if typ.startswith(("varchar(", "char(")):
                mapped = "character varying" if typ.startswith("varchar(") else "character"
                require(
                    col["length"] == int(re.search(r"\d+", typ)[0]),
                    f"{database}.{key}: varchar length differs",
                )
            elif typ.endswith("[]"):
                mapped = "ARRAY"  # #466 smallint[]·varchar[]: element type is checked through udt_name
                require(
                    col["udt"] == "_" + {"smallint": "int2", "varchar": "varchar"}[typ[:-2]],
                    f"{database}.{key}: array element type differs",
                )
            elif typ.startswith("vector("):
                mapped = "USER-DEFINED"  # #466 pgvector; the dimension is checked through format_type
                require(col["formatted"] == typ, f"{database}.{key}: vector type differs")
            require(
                col["type"] == mapped,
                f"{database}.{key}: type expected={mapped} actual={col['type']}",
            )
            require(
                (col["nullable"] == "YES") == expected_col["nullable"],
                f"{database}.{key}: NULL allowance differs",
            )
            # #206·#388 are the explicit fail-closed (private by default) exceptions; other defaults stay forbidden.
            expected_default = (
                "false"
                if database == "core_db" and key in PRIVATE_BY_DEFAULT_COLUMNS
                else None
            )
            require(col["default"] == expected_default, f"{database}.{key}: unexpected default")

        constraints = (
            json.loads(
                query(
                    database,
                    """
            SELECT json_agg(json_build_object('table', r.relname, 'kind', c.contype,
                'columns', (SELECT array_agg(a.attname ORDER BY k.ordinality)
                            FROM unnest(c.conkey) WITH ORDINALITY AS k(num, ordinality)
                            JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.num),
                'expression', pg_get_expr(c.conbin, c.conrelid),
                'validated', c.convalidated))
            FROM pg_constraint c JOIN pg_class r ON r.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = r.relnamespace
            WHERE n.nspname = 'public'
              AND r.relname NOT IN ('flyway_schema_history','alembic_version');
        """,
                )
            )
            or []
        )
        for name, cols in tables.items():
            own = [c for c in constraints if c["table"] == name]
            pk = [c["columns"] for c in own if c["kind"] == "p"]
            require(
                pk == [[col for col, data in cols.items() if data["pk"]]],
                f"{database}.{name}: PK differs",
            )
            actual_fk = {col for c in own if c["kind"] == "f" for col in c["columns"]}
            require(
                actual_fk == {col for col, data in cols.items() if data["fk"]},
                f"{database}.{name}: FK columns differ",
            )
            for col, data in cols.items():
                if data["uk"]:
                    require(
                        any(c["kind"] == "u" and c["columns"] == [col] for c in own),
                        f"{database}.{name}.{col}: missing UNIQUE",
                    )
        enum_count += check_allowed_values(database, tables, constraints)
        actual_indexes = (
            json.loads(
                query(
                    database,
                    """
            SELECT json_agg(json_build_object('table', t.relname,
                'columns', (SELECT array_agg(pg_get_indexdef(i.indexrelid, k, true) ORDER BY k)
                            FROM generate_series(1, i.indnkeyatts) k),
                'predicate', pg_get_expr(i.indpred, i.indrelid),
                'valid', i.indisvalid, 'ready', i.indisready, 'method', a.amname))
            FROM pg_index i JOIN pg_class t ON t.oid = i.indrelid
            JOIN pg_class idx ON idx.oid = i.indexrelid JOIN pg_am a ON a.oid = idx.relam
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public';
        """,
                )
            )
            or []
        )
        index_count += check_indexes(database, indexes[database], actual_indexes)
        seeds = MIGRATION_SEED_ROWS.get(database, {})
        populated = query(database, populated_sql(tables, seeds))
        for name, ids in seeds.items():
            seeded = query(
                database,
                f"SELECT count(*) FROM {name} WHERE {SEED_KEY_COLUMNS.get(name, 'id')} "
                f"IN ({', '.join(repr(i) for i in ids)});",
            )
            require(seeded.strip() == str(len(ids)), f"{database}.{name}: migration seed rows missing")
        if populated:
            raise RuntimeError(
                f"{database}: use an empty, isolated verification DB; populated tables: {populated}"
            )
        cases = {"core_db": CORE_CASES, "learning_db": LEARNING_CASES, "report_db": REPORT_CASES}[
            database
        ]
        query(database, "BEGIN;\n" + EXPECT_ERROR + cases + "\nROLLBACK;")
        negative = cases.count("SELECT pg_temp.expect_sqlstate(")
        checks += negative
        print(
            f"{database}: {len(tables)} tables / {len(expected)} columns match ERD; "
            f"{negative} negative cases rejected; valid counterparts accepted; fixtures rolled back"
        )
    print(
        f"PASS: all three schemas; {checks} negative constraint cases; "
        f"{enum_count} CHECK value sets; {index_count} ERD indexes"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--project", help="Isolated Docker Compose project (existing local mode)")
    mode.add_argument("--direct", action="store_true", help="Connect with psycopg, without Compose")
    parser.add_argument("--db-user", default=os.environ.get("PGUSER"))
    parser.add_argument("--db-host", default=os.environ.get("PGHOST", "127.0.0.1"))
    parser.add_argument("--db-port", type=int, default=int(os.environ.get("PGPORT", "5432")))
    parser.add_argument("--env-file", help="Compose env file; direct mode reads PGPASSWORD")
    parser.add_argument("-f", "--file", action="append", dest="files")
    args = parser.parse_args()
    if not args.db_user:
        parser.error("--db-user or PGUSER is required")
    if args.direct and (args.env_file or args.files):
        parser.error("--env-file/-f are Compose options; direct mode reads PGPASSWORD")
    query = (
        direct_query(args.db_host, args.db_port, args.db_user)
        if args.direct
        else compose_query(args)
    )
    verify_schema(query)


if __name__ == "__main__":
    try:
        main()
    except (ValidationError, RuntimeError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
