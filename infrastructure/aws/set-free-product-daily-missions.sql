-- #387 1회용 상품 데이터 변경(P13 개정, 2026-11-08 팀 확정): 무료 상품 limits.dailyMissions 3 -> 1.
-- 상품 행은 마이그레이션이 아니라 운영 입력이다(#48). 대상은 PAYMENT_FREE_PRODUCT_ID가 가리키는 행뿐이며 code·가격으로 추측하지 않는다.
-- 2026-11-10 개정(#483·#485·#506): 무료 테마 문제는 하루 한도가 없고, limits.dailyMissions는 무료 상품에서 추가 문제(EXTRA)를
-- 다시 켤 때의 무료 EXTRA 하루 한도로만 쓴다(없으면 무료 EXTRA만 503). 같은 행 features에 extraMissions=false(추가 문제 프리미엄 전용)·
-- sundayTheme=false(일요일 프리미엄 전용)를 명시한다. V43은 마이그레이션 시점에 이미 있던 무료 상품만 바꾸므로, 그 뒤에 만든 상품은
-- 이 스크립트로 값을 넣는다(값이 없어도 core가 무료는 거부하지만 상품 데이터에 정책을 드러낸다, core-gateway.md 13·18절).
-- 사용(core_db, 운영 권한): psql -v ON_ERROR_STOP=1 -v free_product_id=<PAYMENT_FREE_PRODUCT_ID> -f set-free-product-daily-missions.sql
-- 되돌리기: limits는 같은 UPDATE를 '3'으로, 무료 EXTRA를 다시 열려면 features.extraMissions를 true로.
BEGIN;
UPDATE product SET limits = jsonb_set(limits, '{dailyMissions}', '1'),
  features = features || '{"extraMissions": false, "sundayTheme": false}'::jsonb
WHERE id = :'free_product_id'::uuid AND price = 0 AND active;
SELECT count(*) = 1 AS changed FROM product
WHERE id = :'free_product_id'::uuid AND price = 0 AND active AND limits->>'dailyMissions' = '1'
  AND features->'extraMissions' = 'false'::jsonb AND features->'sundayTheme' = 'false'::jsonb \gset
\if :changed
COMMIT;
\else
\echo 'PAYMENT_FREE_PRODUCT_ID 행이 활성 0원 상품이 아니어서 바꾸지 않았습니다.'
ROLLBACK;
\endif
SELECT id, code, limits->'dailyMissions' AS daily_missions, features->'extraMissions' AS extra_missions,
  features->'sundayTheme' AS sunday_theme
FROM product WHERE id = :'free_product_id'::uuid;
