-- #808 더미 가족: dm854p 학부모 자녀 중 가족 목록의 프리미엄 학생에게 결제 없는 시험 구독을 준다(infra 9.7.6 2단계, 결정 4).
-- 학습 기록은 넣지 않는다. 기록은 dummy854_data.py가 실제 API로 만든다. dm854p 학부모·자녀는 is_demo로 표시한다
-- (AWS는 AUTH_NEW_ACCOUNT_DEMO=true라 이미 표시돼 바뀌지 않음, kind는 false라 여기서 표시).
-- 실행: core_db에 psql로 -v premium=<쉼표 별명 목록> -v expected=<명 수> -v product_code=<프리미엄 상품 코드>
--   별명 목록은 `python dummy854_data.py [--count 6] plan`의 "프리미엄" 줄. AWS 데모: PREMIUM·12명(demo-db-oneoff.k8s.yaml),
--   kind 리허설: LOCAL-PLUS·4명(--count 6). 운영 사용자 DB·migration·startup seed로 쓰지 않는다.
-- 다시 실행해도 같은 결과: 이미 표시된 행은 그대로, 활성 구독이 있으면 새로 만들지 않는다.
-- 되돌리기(이용 기록 유지): UPDATE subscription SET status = 'CANCELED', canceled_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP,
--   revision = revision + 1 WHERE product_snapshot->>'demoAccount' = '854' AND status = 'ACTIVE';
\set ON_ERROR_STOP on
SELECT set_config('dummy854.premium', :'premium', false), set_config('dummy854.expected', :'expected', false),
       set_config('dummy854.product', :'product_code', false) \gset
BEGIN;
LOCK TABLE user_account, student, guardianship, subscription IN SHARE ROW EXCLUSIVE MODE;
DO $guard$
DECLARE
    wanted text[] := string_to_array(current_setting('dummy854.premium'), ',');
BEGIN
    -- 별명마다 dm854p 학부모 아래 정확히 한 명이어야 한다(다른 학부모의 같은 별명 학생은 건드리지 않는다)
    IF current_database() <> 'core_db'
       OR cardinality(wanted) <> current_setting('dummy854.expected')::int
       OR (SELECT count(DISTINCT n) FROM unnest(wanted) n) <> cardinality(wanted)
       OR (SELECT count(*) FROM student s JOIN guardianship g ON g.student_id = s.id JOIN user_account u ON u.id = g.parent_user_id
           WHERE u.login_id LIKE 'dm854p%' AND s.nickname = ANY (wanted)) <> cardinality(wanted)
       OR NOT EXISTS (SELECT 1 FROM product WHERE code = current_setting('dummy854.product') AND price > 0)
    THEN RAISE EXCEPTION 'Dummy family preconditions changed; no data changed';
    END IF;
END $guard$;

UPDATE user_account SET is_demo = true, updated_at = CURRENT_TIMESTAMP
WHERE role = 'PARENT' AND login_id LIKE 'dm854p%' AND is_demo = false;
UPDATE student s SET is_demo = true, updated_at = CURRENT_TIMESTAMP
FROM guardianship g JOIN user_account u ON u.id = g.parent_user_id
WHERE g.student_id = s.id AND u.login_id LIKE 'dm854p%' AND s.is_demo = false;

-- 결제 없는 시험 구독. W1(11/9) 시험 시계 풀이부터 이용 중이도록 시작일을 그 전 주로, 끝은 시연 뒤까지 둔다.
INSERT INTO subscription (id, parent_user_id, student_id, product_id, status, period_start, period_end, next_billing_date,
    auto_renew, renewal_retry_count, created_at, updated_at, product_snapshot, revision)
SELECT gen_random_uuid(), g.parent_user_id, s.id, p.id, 'ACTIVE', DATE '2026-11-02', CURRENT_DATE + 35, NULL, false, 0,
    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
    jsonb_build_object('id', p.id, 'code', p.code, 'name', p.name || ' (시연 더미)', 'price', p.price, 'active', true,
        'limits', p.limits, 'features', p.features, 'childLimit', p.child_limit, 'billingCycle', p.billing_cycle,
        'demoAccount', '854'), 0
FROM student s JOIN guardianship g ON g.student_id = s.id JOIN user_account u ON u.id = g.parent_user_id
JOIN product p ON p.code = current_setting('dummy854.product')
WHERE u.login_id LIKE 'dm854p%' AND s.nickname = ANY (string_to_array(current_setting('dummy854.premium'), ','))
  AND NOT EXISTS (SELECT 1 FROM subscription x WHERE x.student_id = s.id AND x.status IN ('ACTIVE', 'RENEWAL_FAILED'));

SELECT s.grade, count(*) AS students, count(*) FILTER (WHERE s.is_demo) AS demo_students,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM subscription x WHERE x.student_id = s.id AND x.status = 'ACTIVE'
                                      AND x.product_snapshot->>'demoAccount' = '854')) AS premium_854
FROM student s JOIN guardianship g ON g.student_id = s.id JOIN user_account u ON u.id = g.parent_user_id
WHERE u.login_id LIKE 'dm854p%' GROUP BY s.grade ORDER BY s.grade;
COMMIT;
