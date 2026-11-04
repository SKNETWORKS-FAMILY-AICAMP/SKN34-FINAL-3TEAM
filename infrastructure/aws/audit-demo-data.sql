-- Run with core_app against the demo core_db, never a production database.
-- Aggregate counts only: no identifiers, names, emails, tokens or child text.
BEGIN READ ONLY;
SELECT 'accounts_by_demo_flag' AS check_name, role, is_demo, count(*)
FROM user_account GROUP BY role, is_demo ORDER BY role, is_demo;
SELECT 'students_by_demo_flag' AS check_name, is_demo, count(*)
FROM student GROUP BY is_demo ORDER BY is_demo;
SELECT 'payments' AS check_name, count(*) FROM payment;
SELECT 'payment_orders' AS check_name, count(*) FROM payment_order;
SELECT 'subscriptions' AS check_name, count(*) FROM subscription;
SELECT 'database_access' AS check_name, datname,
       has_database_privilege(current_user, oid, 'CONNECT') AS can_connect
FROM pg_database WHERE datname IN ('core_db','learning_db','report_db') ORDER BY datname;
COMMIT;
