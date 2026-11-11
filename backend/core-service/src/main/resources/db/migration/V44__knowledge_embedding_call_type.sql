-- #467: knowledge embedding usage (epic #463, api-spec 4.2.4 C6). KNOWLEDGE_EMBEDDING is one OpenAI embeddings request (up to 64 texts).
-- Same list as the event schema, core CallType and ai/scoring publishers. Only input tokens exist (output is 0); no price is configured, so cost_usd stays null.
-- Only widens the allowed set like V28/V40/V42, so existing rows always pass.
ALTER TABLE llm_usage DROP CONSTRAINT ck_llm_usage_call_type,
 ADD CONSTRAINT ck_llm_usage_call_type CHECK (call_type IN ('JUDGMENT','FOLLOWUP','ANALYSIS','REPORT_NARRATIVE','MISSION_DRAFT','THEME_DRAFT','THEME_IMAGE','REPORT_EXPLANATION','KNOWLEDGE_EMBEDDING','M2','M1'));
