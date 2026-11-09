-- #439: ai weekly theme generation usage (epic #436, ai #437). THEME_DRAFT is the text graph call, THEME_IMAGE one image call.
-- Same list as the event schema, core CallType and ai/scoring publishers. V38/V39 are reserved by #446 (parent ID login).
-- Only widens the allowed set like V28, so existing rows always pass.
ALTER TABLE llm_usage DROP CONSTRAINT ck_llm_usage_call_type,
 ADD CONSTRAINT ck_llm_usage_call_type CHECK (call_type IN ('JUDGMENT','FOLLOWUP','ANALYSIS','REPORT_NARRATIVE','MISSION_DRAFT','THEME_DRAFT','THEME_IMAGE','M2','M1'));
