-- #599 낱말 물어보기(FN-LRN-21, api-spec 4.2.8). LLM 사용량 유형 WORD_HELP.
-- Same list as the event schema, core CallType and ai/scoring publishers.
-- Only widens the allowed set like V46, so existing rows always pass.
ALTER TABLE llm_usage DROP CONSTRAINT ck_llm_usage_call_type,
 ADD CONSTRAINT ck_llm_usage_call_type CHECK (call_type IN ('JUDGMENT','FOLLOWUP','ANALYSIS','REPORT_NARRATIVE','MISSION_DRAFT','THEME_DRAFT','THEME_IMAGE','REPORT_EXPLANATION','KNOWLEDGE_EMBEDDING','THEME_VIDEO','MEMORY_EMBEDDING','MEMORY_EXPLANATION','MEMORY_QUERY','WORD_HELP','M2','M1'));
