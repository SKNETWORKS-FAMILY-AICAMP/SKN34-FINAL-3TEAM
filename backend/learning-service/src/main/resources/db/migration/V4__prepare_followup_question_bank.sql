-- P16: prepare the question bank and optional link for reviewed legacy mapping.
-- No generated or collected question content is seeded by this migration.

CREATE TABLE followup_bank_question (
    id uuid NOT NULL,
    type varchar NOT NULL,
    question text NOT NULL,
    active boolean NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_followup_bank_question PRIMARY KEY (id),
    CONSTRAINT ck_followup_bank_question_type
        CHECK (type IN ('ONE_STEP_MORE', 'TELL_MORE', 'LOOK_AGAIN'))
);

ALTER TABLE followup
    ADD COLUMN bank_question_id uuid,
    ADD CONSTRAINT fk_followup_bank_question_id
        FOREIGN KEY (bank_question_id) REFERENCES followup_bank_question (id)
        ON DELETE NO ACTION ON UPDATE NO ACTION;
