-- #680 추억 검색 질의 변환(에픽 #562, 설계 #679). ai 질의 변환(api-spec 4.2.7, #681) LLM 호출 유형 MEMORY_QUERY.
-- Same list as the event schema, core CallType and ai/scoring publishers.
-- Only widens the allowed set like V28/V40/V42/V44/V45/V46, so existing rows always pass.
ALTER TABLE llm_usage DROP CONSTRAINT ck_llm_usage_call_type,
 ADD CONSTRAINT ck_llm_usage_call_type CHECK (call_type IN ('JUDGMENT','FOLLOWUP','ANALYSIS','REPORT_NARRATIVE','MISSION_DRAFT','THEME_DRAFT','THEME_IMAGE','REPORT_EXPLANATION','KNOWLEDGE_EMBEDDING','THEME_VIDEO','MEMORY_EMBEDDING','MEMORY_EXPLANATION','MEMORY_QUERY','M2','M1'));
