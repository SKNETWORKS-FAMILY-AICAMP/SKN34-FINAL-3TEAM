-- #624 시연 계정 준비: demo_account_data.py children으로 등록한 가상 자녀 2명과 그 학부모를 시연 데이터로 표시하고,
-- 초5 자녀에게 결제 없는 프리미엄 시험 구독을 준다(설명 카드 FN-RPT-09·일요일 이용 대상).
-- 학습 기록은 넣지 않는다. 기록은 demo_account_data.py가 실제 API로 만든다.
-- 실행: core_db에 psql로 -v g3=<초3 닉네임> -v g5=<초5 닉네임> -v product_code=<프리미엄 상품 코드>
--   AWS 데모: PREMIUM (demo-db-oneoff.k8s.yaml), kind: LOCAL-PLUS. 운영 사용자 DB·migration·startup seed로 쓰지 않는다.
-- 다시 실행해도 같은 결과: 이미 표시된 행은 그대로, 활성 구독이 있으면 새로 만들지 않는다.
-- 되돌리기(이용 기록 유지): UPDATE subscription SET status = 'CANCELED', canceled_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP,
--   revision = revision + 1 WHERE product_snapshot->>'demoAccount' = '624' AND status = 'ACTIVE';
\set ON_ERROR_STOP on
SELECT set_config('demo624.g3', :'g3', false), set_config('demo624.g5', :'g5', false),
       set_config('demo624.product', :'product_code', false) \gset
BEGIN;
LOCK TABLE user_account, student, guardianship, subscription IN SHARE ROW EXCLUSIVE MODE;
DO $guard$
DECLARE
    parents int;
BEGIN
    SELECT count(DISTINCT g.parent_user_id) INTO parents
    FROM student s JOIN guardianship g ON g.student_id = s.id
    WHERE s.nickname IN (current_setting('demo624.g3'), current_setting('demo624.g5'));
    IF current_database() <> 'core_db'
       OR (SELECT count(*) FROM student WHERE nickname = current_setting('demo624.g3') AND grade = 3) <> 1
       OR (SELECT count(*) FROM student WHERE nickname = current_setting('demo624.g5') AND grade = 5) <> 1
       OR parents <> 1
       OR NOT EXISTS (SELECT 1 FROM product WHERE code = current_setting('demo624.product') AND price > 0)
    THEN RAISE EXCEPTION 'Demo account preconditions changed; no data changed';
    END IF;
END $guard$;

-- 같은 학부모의 두 자녀와 그 학부모만 시연 데이터로 표시(NFR-SEC-07). 다른 자녀·학부모는 건드리지 않는다.
UPDATE student SET is_demo = true, updated_at = CURRENT_TIMESTAMP
WHERE nickname IN (current_setting('demo624.g3'), current_setting('demo624.g5')) AND is_demo = false;
UPDATE user_account u SET is_demo = true, updated_at = CURRENT_TIMESTAMP
WHERE u.role = 'PARENT' AND u.is_demo = false AND u.id IN (
    SELECT g.parent_user_id FROM guardianship g JOIN student s ON s.id = g.student_id
    WHERE s.nickname = current_setting('demo624.g5'));

-- 결제 없는 시험 구독. 지난 회차(시험 시계로 옮긴 주)에도 이용 중이도록 기간을 앞뒤로 넉넉히 둔다.
INSERT INTO subscription (id, parent_user_id, student_id, product_id, status, period_start, period_end, next_billing_date,
    auto_renew, renewal_retry_count, created_at, updated_at, product_snapshot, revision)
SELECT gen_random_uuid(), g.parent_user_id, s.id, p.id, 'ACTIVE', CURRENT_DATE - 28, CURRENT_DATE + 35, NULL, false, 0,
    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
    jsonb_build_object('id', p.id, 'code', p.code, 'name', p.name || ' (시연 준비)', 'price', p.price, 'active', true,
        'limits', p.limits, 'features', p.features, 'childLimit', p.child_limit, 'billingCycle', p.billing_cycle,
        'demoAccount', '624'), 0
FROM student s JOIN guardianship g ON g.student_id = s.id JOIN product p ON p.code = current_setting('demo624.product')
WHERE s.nickname = current_setting('demo624.g5')
  AND NOT EXISTS (SELECT 1 FROM subscription x WHERE x.student_id = s.id AND x.status IN ('ACTIVE', 'RENEWAL_FAILED'));

SELECT s.grade, s.is_demo, u.is_demo AS parent_is_demo,
       (SELECT count(*) FROM subscription x WHERE x.student_id = s.id AND x.status = 'ACTIVE') AS active_subscriptions
FROM student s JOIN guardianship g ON g.student_id = s.id JOIN user_account u ON u.id = g.parent_user_id
WHERE s.nickname IN (current_setting('demo624.g3'), current_setting('demo624.g5')) ORDER BY s.grade;
COMMIT;
