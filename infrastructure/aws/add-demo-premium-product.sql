-- One-time #361 demo data: turn on the existing (inactive) PREMIUM product so the AWS demo can buy a test
-- subscription (Toss TEST keys) and open the analysis conversation. Values are left as they are; only active changes.
-- Only for sagomungchi-demo-db core_db in account 347161580747, ap-northeast-2. Not a migration or startup seed.
-- Observed 2026-11-05 before the change: PREMIUM 98a998bd-05c8-4ac9-b909-23c14340f6f9, 14900 MONTHLY child_limit 1, active=false.
-- Rollback: UPDATE product SET active = false WHERE id = '98a998bd-05c8-4ac9-b909-23c14340f6f9';
BEGIN;
LOCK TABLE product IN SHARE ROW EXCLUSIVE MODE;
DO $guard$
BEGIN
    IF current_database() <> 'core_db'
       OR NOT EXISTS (SELECT 1 FROM product WHERE id = '98a998bd-05c8-4ac9-b909-23c14340f6f9' AND code = 'PREMIUM'
                      AND price = 14900 AND billing_cycle = 'MONTHLY' AND child_limit = 1 AND active = false
                      AND jsonb_typeof(limits->'dailyConversations') = 'number' AND jsonb_typeof(limits->'reportNarrative') = 'boolean')
    THEN RAISE EXCEPTION 'PREMIUM preconditions changed; no data changed';
    END IF;
END $guard$;
UPDATE product SET active = true WHERE id = '98a998bd-05c8-4ac9-b909-23c14340f6f9';
SELECT code, price, billing_cycle, child_limit, active, limits FROM product ORDER BY price;
COMMIT;
