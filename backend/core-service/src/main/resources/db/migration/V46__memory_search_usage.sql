-- #566 추억 검색·설명(P27, 에픽 #562). ERD 3.5.2 설계를 구현한다.

-- 1) LLM 사용량 유형: 추억 검색 임베딩 MEMORY_EMBEDDING(ai 임베딩 purpose=MEMORY), 추억 설명 MEMORY_EXPLANATION.
-- Same list as the event schema, core CallType and ai/scoring publishers.
-- Only widens the allowed set like V28/V40/V42/V44/V45, so existing rows always pass.
ALTER TABLE llm_usage DROP CONSTRAINT ck_llm_usage_call_type,
 ADD CONSTRAINT ck_llm_usage_call_type CHECK (call_type IN ('JUDGMENT','FOLLOWUP','ANALYSIS','REPORT_NARRATIVE','MISSION_DRAFT','THEME_DRAFT','THEME_IMAGE','REPORT_EXPLANATION','KNOWLEDGE_EMBEDDING','THEME_VIDEO','MEMORY_EMBEDDING','MEMORY_EXPLANATION','M2','M1'));

-- 2) 추억 검색·설명 하루 사용량. 요청 1건 = 1행, KST 하루 건수를 product.limits와 비교한다(mission_daily_usage와 같은 방식).
-- 학생 삭제 확정(P09) 트랜잭션에서 지운다(CASCADE 없음, ERD 공통 규칙).
CREATE TABLE memory_daily_usage (
    id uuid PRIMARY KEY,
    student_id uuid NOT NULL REFERENCES student(id),
    kind varchar(20) NOT NULL CONSTRAINT ck_memory_daily_usage_kind CHECK (kind IN ('SEARCH', 'EXPLANATION')),
    usage_date date NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE INDEX ix_memory_daily_usage_student_kind_date ON memory_daily_usage (student_id, kind, usage_date);

-- 3) P13·P27 한도 값(2026-11-12 확정, 무료·프리미엄 같음): 검색 20·설명 10.
-- 상품 행은 운영 데이터라 이미 있는 행만 바꾸고(빈 DB는 영향 없음), 이미 값이 있으면 그대로 둔다.
-- 키가 없는 기존 구독 스냅숏은 core가 무료 상품 값으로 대신 쓴다.
UPDATE product SET limits = '{"dailyMemorySearches": 20, "dailyMemoryExplanations": 10}'::jsonb || limits
WHERE NOT (limits ? 'dailyMemorySearches' AND limits ? 'dailyMemoryExplanations');
