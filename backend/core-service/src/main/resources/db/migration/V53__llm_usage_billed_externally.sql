-- #764 비용을 서비스 밖 청구서로 보는 모델(Veo GCP 초 단위, RunPod Gemma 시간 단위) 호출 표시.
-- Fixed at consumption time like cost_usd (app.llm-billed-externally); existing rows become false, so past unpriced rows are not reclassified.
ALTER TABLE llm_usage ADD COLUMN billed_externally boolean NOT NULL DEFAULT false;
-- Backfill existing rows, then follow the repository's application-supplied values policy (like V18).
ALTER TABLE llm_usage ALTER COLUMN billed_externally DROP DEFAULT;
