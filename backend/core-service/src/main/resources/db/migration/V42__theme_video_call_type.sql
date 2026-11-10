-- Weekly theme video usage (epic #436). THEME_VIDEO is one video generation call, recorded without tokens like THEME_IMAGE.
-- Same list as the event schema, core CallType and ai/scoring publishers.
-- Only widens the allowed set like V28/V40, so existing rows always pass.
ALTER TABLE llm_usage DROP CONSTRAINT ck_llm_usage_call_type,
 ADD CONSTRAINT ck_llm_usage_call_type CHECK (call_type IN ('JUDGMENT','FOLLOWUP','ANALYSIS','REPORT_NARRATIVE','MISSION_DRAFT','THEME_DRAFT','THEME_IMAGE','THEME_VIDEO','M2','M1'));
