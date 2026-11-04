-- Run with core_app against the demo core_db before applying core V26 (guardian transfer).
-- Read-only counts; every row must be 0 or V26 fails part-way through its constraints.
BEGIN READ ONLY;
SELECT 'students_with_multiple_linked_guardians' AS check_name, count(*) AS violations
FROM (SELECT student_id FROM guardianship WHERE status = 'LINKED' GROUP BY student_id HAVING count(*) > 1) d;
SELECT 'guardianship_method_outside_register_transfer' AS check_name, count(*) AS violations
FROM guardianship WHERE method NOT IN ('REGISTER', 'TRANSFER');
SELECT 'reauth_purpose_outside_v26_list' AS check_name, count(*) AS violations
FROM reauth_challenge WHERE purpose NOT IN
  ('PIN_CHANGE','CHILD_UNLINK','CHILD_DELETE','WITHDRAWAL','GUARDIAN_PASSWORD','CHILD_TRANSFER','TRANSFER_ACCEPT');
SELECT 'reauth_target_outside_v26_rule' AS check_name, count(*) AS violations
FROM reauth_challenge WHERE NOT (
  (purpose IN ('WITHDRAWAL','GUARDIAN_PASSWORD','TRANSFER_ACCEPT') AND student_id IS NULL AND scope IS NULL) OR
  (purpose IN ('PIN_CHANGE','CHILD_UNLINK','CHILD_TRANSFER') AND student_id IS NOT NULL AND scope IS NULL) OR
  (purpose = 'CHILD_DELETE' AND student_id IS NOT NULL AND scope IS NOT NULL));
SELECT 'flyway_latest_version' AS check_name, max(version::int) AS violations
FROM flyway_schema_history WHERE success AND version ~ '^[0-9]+$';
COMMIT;
