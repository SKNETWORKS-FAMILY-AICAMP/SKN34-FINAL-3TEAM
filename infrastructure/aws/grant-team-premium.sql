-- One-time demo grant: paid entitlement for the shared team parent account, without payment.
-- Only for sagomungchi-demo-db core_db. Run with: psql -v parent_email=<team gmail> -f grant-team-premium.sql
-- Re-runnable: children linked later get a subscription on the next run; existing ones are left as they are.
\set ON_ERROR_STOP on
BEGIN;
LOCK TABLE product, subscription IN SHARE ROW EXCLUSIVE MODE;
SELECT set_config('grant.parent_email', :'parent_email', true);

DO $check$
DECLARE parent record;
BEGIN
    IF current_database() <> 'core_db' THEN RAISE EXCEPTION 'not core_db; no data changed'; END IF;
    SELECT id, role, status, is_demo INTO parent FROM user_account
     WHERE lower(login_id) = lower(current_setting('grant.parent_email'));
    IF NOT FOUND OR parent.role <> 'PARENT' OR parent.status <> 'ACTIVE' OR NOT parent.is_demo THEN
        RAISE EXCEPTION 'target must be one ACTIVE demo PARENT; no data changed';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM guardianship WHERE parent_user_id = parent.id AND status = 'LINKED') THEN
        RAISE EXCEPTION 'no linked child; no data changed';
    END IF;
    IF EXISTS (SELECT 1 FROM payment_order WHERE parent_user_id = parent.id) THEN
        RAISE EXCEPTION 'parent has real payment orders; no data changed';
    END IF;
END $check$;

-- Premium product (P13: 14,900 KRW monthly, feedback 50/day, conversations 30/day, full report).
-- active=false keeps it off the public product list, so nobody can buy it through the demo site.
INSERT INTO product (id, code, name, price, billing_cycle, child_limit, features, limits, active, created_at)
SELECT gen_random_uuid(), 'PREMIUM', '프리미엄', 14900, 'MONTHLY', 1, '{}'::jsonb,
       '{"dailyFeedback":50,"dailyConversations":30,"reportNarrative":true}'::jsonb, false, now()
WHERE NOT EXISTS (SELECT 1 FROM product WHERE code = 'PREMIUM');

-- One ACTIVE subscription per linked child: no billing key, no next billing date, no auto renew,
-- so the renewal job never picks it up. Entitled until 2027-12-31 09:00 KST.
INSERT INTO subscription (id, parent_user_id, student_id, product_id, status, period_start, period_end,
       next_billing_date, auto_renew, customer_key, billing_key_enc, renewal_retry_count, grace_until,
       auto_renew_canceled_at, canceled_at, created_at, updated_at, product_snapshot, billing_anchor_day,
       last_billing_attempt_date, revision)
SELECT gen_random_uuid(), g.parent_user_id, g.student_id, p.id, 'ACTIVE', CURRENT_DATE, DATE '2027-12-31',
       NULL, false, NULL, NULL, NULL, NULL, NULL, NULL, now(), now(),
       jsonb_build_object('id', p.id, 'code', p.code, 'name', p.name, 'price', p.price,
                          'billingCycle', p.billing_cycle, 'childLimit', p.child_limit,
                          'features', p.features, 'limits', p.limits, 'active', p.active),
       NULL, NULL, 0
  FROM guardianship g
  JOIN user_account u ON u.id = g.parent_user_id
  CROSS JOIN (SELECT * FROM product WHERE code = 'PREMIUM') p
 WHERE lower(u.login_id) = lower(current_setting('grant.parent_email')) AND g.status = 'LINKED'
   AND NOT EXISTS (SELECT 1 FROM subscription s
                    WHERE s.student_id = g.student_id AND s.status IN ('ACTIVE', 'RENEWAL_FAILED'));

SELECT s.student_id, s.status, s.period_end, s.auto_renew, s.next_billing_date,
       s.product_snapshot->>'name' AS product, s.product_snapshot->'limits' AS limits
  FROM subscription s JOIN user_account u ON u.id = s.parent_user_id
 WHERE lower(u.login_id) = lower(current_setting('grant.parent_email'));
COMMIT;
