-- #485 주간 테마 규칙 개정(#483, 2026-11-10 결정): 무료 추가 문제 프리미엄 전용·프리미엄 일요일·당일 풀이와 주간 완주 포인트.
-- 기존 V35는 고치지 않고 사건 종류 CHECK를 넓힌 뒤 새 규칙 행을 넣는다. 기존 행은 새 목록에도 모두 들어 있어 항상 통과한다.

-- 적립 사건: 당일 풀이 THEME_ON_TIME(사건 키 weekStart:day)·주간 완주 THEME_FINISHED(사건 키 weekStart).
-- THEME_COMPLETED는 개근(월~금 각 당일 학습 완료)으로 그대로 쓴다.
ALTER TABLE reward_rule DROP CONSTRAINT ck_reward_rule_event_type,
    ADD CONSTRAINT ck_reward_rule_event_type CHECK (event_type IN
        ('MISSION_COMPLETED', 'REVIEW_VIEWED', 'COMMUNITY_POSTED', 'REACTION_GIVEN', 'THEME_COMPLETED',
         'THEME_ON_TIME', 'THEME_FINISHED'));
ALTER TABLE reward_point_ledger DROP CONSTRAINT ck_reward_point_ledger_event_type,
    ADD CONSTRAINT ck_reward_point_ledger_event_type CHECK (event_type IN
        ('MISSION_COMPLETED', 'REVIEW_VIEWED', 'COMMUNITY_POSTED', 'REACTION_GIVEN', 'THEME_COMPLETED',
         'THEME_ON_TIME', 'THEME_FINISHED', 'UNLOCK'));

-- P21 값(2026-11-10 결정): 당일 풀이 5·주간 완주 10. 값은 데이터라 나중에 행만 고쳐 조정한다.
INSERT INTO reward_rule (event_type, amount, daily_cap, active, updated_at) VALUES
    ('THEME_ON_TIME', 5, NULL, true, TIMESTAMPTZ '2026-11-10 00:00:00+09'),
    ('THEME_FINISHED', 10, NULL, true, TIMESTAMPTZ '2026-11-10 00:00:00+09');

-- P13 상품 기능 값. 상품 행은 운영 데이터라 이미 있는 행만 바꾸고(빈 DB는 영향 없음), 구독은 결제 시점 상품 스냅숏을 쓴다.
-- 무료(가격 0): 추가 문제(EXTRA) 끔 → core 403 PREMIUM_REQUIRED, 일요일 테마 끔.
UPDATE product SET features = features || '{"extraMissions": false, "sundayTheme": false}'::jsonb
WHERE price = 0;
-- 유료: 일요일 테마 켬(1차, 단건 이용권은 #430 이후). 값이 없는 기존 구독 스냅숏도 core가 구독 중이면 허용으로 본다.
UPDATE product SET features = features || '{"sundayTheme": true}'::jsonb
WHERE price > 0;
