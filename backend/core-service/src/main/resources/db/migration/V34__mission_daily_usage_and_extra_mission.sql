-- #387 (P13·P14 개정): 무료 하루 미션 한도 집계와 프리미엄 추가 문제 사용 기록.
-- mission_daily_usage는 무료 자녀의 THEME_DAY 신규 시도(learning 201)만 기록하고 (student_id, usage_date) 건수로 판정한다(#210 PostgreSQL 결정).
-- mission_id는 한도 도달 뒤 같은 미션의 진행 중 시도 이어하기(learning 200)를 막지 않도록 마지막 시도를 찾는 데 쓴다.
CREATE TABLE mission_daily_usage (
    attempt_id uuid PRIMARY KEY,
    student_id uuid NOT NULL REFERENCES student(id),
    mission_id uuid NOT NULL,
    usage_date date NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE INDEX ix_mission_daily_usage_student_date ON mission_daily_usage (student_id, usage_date);
CREATE INDEX ix_mission_daily_usage_student_mission ON mission_daily_usage (student_id, mission_id, created_at);

-- 프리미엄 추가 문제(EXTRA) 시도는 환불 판정의 프리미엄 사용이다(source_id = learning 시도 ID).
ALTER TABLE payment_premium_usage DROP CONSTRAINT payment_premium_usage_kind_check;
ALTER TABLE payment_premium_usage ADD CONSTRAINT payment_premium_usage_kind_check
    CHECK (kind IN ('FEEDBACK', 'CONVERSATION', 'REPORT_VIEW', 'EXTRA_MISSION'));
