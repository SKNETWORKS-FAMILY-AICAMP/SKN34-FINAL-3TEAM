-- #480: report explanation sLLM usage (epic #473, ai #477). REPORT_EXPLANATION is one in-cluster sLLM call per explained rubric item.
-- Same list as the event schema, core CallType and ai/scoring publishers. No token price is configured, so cost_usd stays null.
-- Only widens the allowed set like V28/V40, so existing rows always pass.
ALTER TABLE llm_usage DROP CONSTRAINT ck_llm_usage_call_type,
 ADD CONSTRAINT ck_llm_usage_call_type CHECK (call_type IN ('JUDGMENT','FOLLOWUP','ANALYSIS','REPORT_NARRATIVE','MISSION_DRAFT','THEME_DRAFT','THEME_IMAGE','REPORT_EXPLANATION','M2','M1'));
