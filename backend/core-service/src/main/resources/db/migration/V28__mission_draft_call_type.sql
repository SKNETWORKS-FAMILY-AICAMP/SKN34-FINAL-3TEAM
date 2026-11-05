-- #355: ai mission draft usage (callType MISSION_DRAFT, #336/#354). Same list as the event schema, core CallType and ai/scoring publishers.
-- Follows V27 (#243 outbox failure quarantine). Only widens the allowed set, so existing rows always pass.
ALTER TABLE llm_usage DROP CONSTRAINT ck_llm_usage_call_type,
 ADD CONSTRAINT ck_llm_usage_call_type CHECK (call_type IN ('JUDGMENT','FOLLOWUP','ANALYSIS','REPORT_NARRATIVE','MISSION_DRAFT','M2','M1'));
