-- #67/#41: retain legacy answers and distinguish reflection references.
ALTER TABLE conversation_message ADD COLUMN fallback jsonb, ADD COLUMN notice jsonb;
ALTER TABLE message_evidence ADD COLUMN kind varchar NOT NULL DEFAULT 'ANSWER';
-- Backfill existing evidence, then follow the repository's application-supplied values policy.
ALTER TABLE message_evidence ALTER COLUMN kind DROP DEFAULT;
ALTER TABLE message_evidence ALTER COLUMN answer_id DROP NOT NULL, ALTER COLUMN answer_version DROP NOT NULL;
ALTER TABLE message_evidence ADD CONSTRAINT ck_message_evidence_kind CHECK(kind IN ('ANSWER','REFLECTION')),
 ADD CONSTRAINT ck_message_evidence_reference CHECK(
   (kind='ANSWER' AND answer_id IS NOT NULL AND answer_version IS NOT NULL AND answer_version>0)
   OR (kind='REFLECTION' AND answer_id IS NULL AND answer_version IS NULL));
