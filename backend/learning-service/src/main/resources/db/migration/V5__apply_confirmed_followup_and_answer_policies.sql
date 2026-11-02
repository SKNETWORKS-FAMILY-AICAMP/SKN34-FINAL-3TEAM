-- Finalize P03/P16. Apply V4 first when existing records require review.
-- Never relabel TEMPLATE/voice records or discard their provenance implicitly.

LOCK TABLE answer, followup IN ACCESS EXCLUSIVE MODE;

DO $policy_preflight$
BEGIN
    IF EXISTS (SELECT 1 FROM answer WHERE speech_transcribed) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'P03: preserve and explicitly resolve existing speech-transcribed answers before V5';
    END IF;
    IF EXISTS (SELECT 1 FROM followup WHERE source = 'TEMPLATE') THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'P16: existing TEMPLATE followups need an explicit provenance transition decision before V5';
    END IF;
    IF EXISTS (
        SELECT 1 FROM followup
        WHERE (source = 'BANK' AND bank_question_id IS NULL)
           OR (source <> 'BANK' AND bank_question_id IS NOT NULL)
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'P16: map BANK followups to reviewed bank questions and clear non-BANK links before V5';
    END IF;
END;
$policy_preflight$;

ALTER TABLE answer DROP COLUMN speech_transcribed;

ALTER TABLE followup
    DROP CONSTRAINT ck_followup_source,
    ADD CONSTRAINT ck_followup_source CHECK (source IN ('LLM', 'LLM_RETRY', 'BANK')),
    ADD CONSTRAINT ck_followup_bank_source CHECK (
        (source = 'BANK' AND bank_question_id IS NOT NULL)
        OR (source <> 'BANK' AND bank_question_id IS NULL)
    );
