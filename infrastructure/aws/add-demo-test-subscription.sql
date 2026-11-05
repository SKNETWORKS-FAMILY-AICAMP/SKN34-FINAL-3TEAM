-- One-time #361 load test data: give the demo test child (nickname 123213, is_demo) a PREMIUM subscription
-- without a payment, because the Toss docs widget key currently fails (api.tosspayments.com widget-groups 500).
-- Entitlement reads subscription.product_snapshot, so the PREMIUM product row may stay inactive.
-- The snapshot raises dailyConversations for this test subscription only, so the analysis path can be loaded.
-- Only for sagomungchi-demo-db core_db in account 347161580747, ap-northeast-2. Not a migration or startup seed.
-- Rollback (keeps usage history): UPDATE subscription SET status = 'CANCELED', canceled_at = CURRENT_TIMESTAMP,
--   updated_at = CURRENT_TIMESTAMP, revision = revision + 1 WHERE id = '3610c0de-0000-4000-8000-000000000361';
BEGIN;
LOCK TABLE subscription IN SHARE ROW EXCLUSIVE MODE;
-- The app account cannot create temp tables, so the target query is repeated (same transaction, table locked).
DO $guard$
BEGIN
    IF current_database() <> 'core_db'
       OR (SELECT count(*) FROM student s JOIN guardianship g ON g.student_id = s.id JOIN user_account u ON u.id = g.parent_user_id
           WHERE s.nickname = '123213' AND s.is_demo AND u.is_demo AND u.role = 'PARENT') <> 1
       OR NOT EXISTS (SELECT 1 FROM product WHERE id = '98a998bd-05c8-4ac9-b909-23c14340f6f9' AND code = 'PREMIUM')
       OR EXISTS (SELECT 1 FROM subscription WHERE id = '3610c0de-0000-4000-8000-000000000361')
       OR EXISTS (SELECT 1 FROM subscription x JOIN student s ON s.id = x.student_id
                  WHERE s.nickname = '123213' AND s.is_demo AND x.status IN ('ACTIVE', 'RENEWAL_FAILED'))
    THEN RAISE EXCEPTION 'Test subscription preconditions changed; no data changed';
    END IF;
END $guard$;
INSERT INTO subscription (id, parent_user_id, student_id, product_id, status, period_start, period_end, next_billing_date,
    auto_renew, renewal_retry_count, created_at, updated_at, product_snapshot, revision)
SELECT '3610c0de-0000-4000-8000-000000000361', g.parent_user_id, s.id, '98a998bd-05c8-4ac9-b909-23c14340f6f9',
    'ACTIVE', CURRENT_DATE, CURRENT_DATE + 7, NULL, false, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
    '{"id": "98a998bd-05c8-4ac9-b909-23c14340f6f9", "code": "PREMIUM", "name": "프리미엄 (부하 시험)", "price": 14900, "active": true,
      "limits": {"dailyFeedback": 50, "dailyMissions": 3, "reportNarrative": true, "dailyConversations": 5000},
      "features": {}, "childLimit": 1, "billingCycle": "MONTHLY"}'::jsonb, 0
FROM student s JOIN guardianship g ON g.student_id = s.id JOIN user_account u ON u.id = g.parent_user_id
WHERE s.nickname = '123213' AND s.is_demo AND u.is_demo AND u.role = 'PARENT';
SELECT status, period_start, period_end, auto_renew, product_snapshot->'limits' AS limits FROM subscription
WHERE id = '3610c0de-0000-4000-8000-000000000361';
COMMIT;
