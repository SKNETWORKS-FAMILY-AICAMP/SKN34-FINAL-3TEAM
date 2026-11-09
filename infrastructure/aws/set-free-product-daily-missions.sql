-- #387 1회용 상품 데이터 변경(P13 개정, 2026-11-08 팀 확정): 무료 상품 limits.dailyMissions 3 -> 1.
-- 상품 행은 마이그레이션이 아니라 운영 입력이다(#48). 대상은 PAYMENT_FREE_PRODUCT_ID가 가리키는 행뿐이며 code·가격으로 추측하지 않는다.
-- core는 limits.dailyMissions가 없으면 무료 THEME_DAY·EXTRA 시작을 503 PAYMENT_PRODUCT_UNAVAILABLE로 막으므로 #387 배포 전에 실행한다.
-- features.extraMissions는 비워 둔다(= 허용). 나중에 false로 바꾸면 코드 수정 없이 EXTRA가 프리미엄 전용이 된다(core-gateway.md 13절).
-- 사용(core_db, 운영 권한): psql -v ON_ERROR_STOP=1 -v free_product_id=<PAYMENT_FREE_PRODUCT_ID> -f set-free-product-daily-missions.sql
-- 되돌리기: 같은 UPDATE를 '3'으로 실행.
BEGIN;
UPDATE product SET limits = jsonb_set(limits, '{dailyMissions}', '1')
WHERE id = :'free_product_id'::uuid AND price = 0 AND active;
SELECT count(*) = 1 AS changed FROM product
WHERE id = :'free_product_id'::uuid AND price = 0 AND active AND limits->>'dailyMissions' = '1' \gset
\if :changed
COMMIT;
\else
\echo 'PAYMENT_FREE_PRODUCT_ID 행이 활성 0원 상품이 아니어서 바꾸지 않았습니다.'
ROLLBACK;
\endif
SELECT id, code, limits->'dailyMissions' AS daily_missions, features->'extraMissions' AS extra_missions
FROM product WHERE id = :'free_product_id'::uuid;
