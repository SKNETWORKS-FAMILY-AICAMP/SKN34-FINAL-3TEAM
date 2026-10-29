-- #99: no service publishes SPEECH usage. ADD CONSTRAINT validates existing rows, so a stored SPEECH row stops this migration.
ALTER TABLE llm_usage DROP CONSTRAINT ck_llm_usage_call_type,
 ADD CONSTRAINT ck_llm_usage_call_type CHECK (call_type IN ('JUDGMENT','FOLLOWUP','ANALYSIS','REPORT_NARRATIVE','M2','M1'));
