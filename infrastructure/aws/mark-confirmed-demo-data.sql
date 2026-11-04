-- One-time #185 correction, explicitly confirmed by the user on 2026-11-03.
-- Only for sagomungchi-demo-db in account 347161580747, ap-northeast-2.
-- Do not use as a migration, startup seed or a general production cleanup.
BEGIN;
LOCK TABLE user_account, student, guardianship, payment, payment_order, subscription IN SHARE ROW EXCLUSIVE MODE;
DO $audit$
BEGIN
    IF current_database() <> 'core_db'
       OR (SELECT count(*) FROM user_account WHERE role = 'PARENT') <> 1
       OR (SELECT count(*) FROM student) <> 2
       OR (SELECT count(DISTINCT s.id) FROM student s JOIN guardianship g ON g.student_id = s.id
           JOIN user_account u ON u.id = g.parent_user_id WHERE u.role = 'PARENT') <> 2
       OR EXISTS (SELECT 1 FROM payment)
       OR EXISTS (SELECT 1 FROM payment_order)
       OR EXISTS (SELECT 1 FROM subscription)
    THEN RAISE EXCEPTION 'Demo correction preconditions changed; no data changed';
    END IF;
END $audit$;
UPDATE user_account SET is_demo = true, updated_at = CURRENT_TIMESTAMP
WHERE role = 'PARENT' AND is_demo = false;
UPDATE student SET is_demo = true, updated_at = CURRENT_TIMESTAMP
WHERE is_demo = false AND EXISTS (
    SELECT 1 FROM guardianship g JOIN user_account u ON u.id = g.parent_user_id
    WHERE g.student_id = student.id AND u.role = 'PARENT' AND u.is_demo = true
);
COMMIT;
