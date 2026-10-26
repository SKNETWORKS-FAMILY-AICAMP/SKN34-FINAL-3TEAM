-- Initial schema: docs/design/erd.md section 4.2.
-- IDs and timestamps are supplied by the application. No seed data.

CREATE TABLE attempt (
    id uuid NOT NULL,
    student_id uuid NOT NULL,
    mission_id uuid NOT NULL,
    mission_version_id uuid NOT NULL,
    rubric_version_id uuid NOT NULL,
    grade integer NOT NULL,
    status varchar NOT NULL,
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz NOT NULL,
    CONSTRAINT pk_attempt PRIMARY KEY (id),
    CONSTRAINT ck_attempt_status
        CHECK (status IN ('IN_PROGRESS', 'COMPLETED'))
);

CREATE TABLE attempt_draft (
    attempt_id uuid NOT NULL,
    version integer NOT NULL,
    content jsonb NOT NULL,
    saved_at timestamptz NOT NULL,
    CONSTRAINT pk_attempt_draft PRIMARY KEY (attempt_id)
);

CREATE TABLE hint_usage (
    id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    hint_question_id uuid NOT NULL,
    opened_at timestamptz NOT NULL,
    CONSTRAINT pk_hint_usage PRIMARY KEY (id)
);

CREATE TABLE answer (
    id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    version integer NOT NULL,
    followup_id uuid,
    previous_answer_id uuid,
    input_type varchar NOT NULL,
    content jsonb NOT NULL,
    plain_text text,
    dictated_by_guardian boolean NOT NULL,
    speech_transcribed boolean NOT NULL,
    idempotency_key uuid NOT NULL,
    submitted_at timestamptz NOT NULL,
    CONSTRAINT pk_answer PRIMARY KEY (id),
    CONSTRAINT uq_answer_attempt_id_version
        UNIQUE (attempt_id, version),
    CONSTRAINT uq_answer_attempt_id_idempotency_key
        UNIQUE (attempt_id, idempotency_key),
    CONSTRAINT ck_answer_input_type
        CHECK (input_type IN (
            'CHOICE',
            'ORDERING',
            'CLASSIFICATION',
            'NARRATIVE',
            'SOLUTION_STEPS',
            'ESSAY'
        ))
);

CREATE TABLE judgment (
    id uuid NOT NULL,
    answer_id uuid NOT NULL,
    process_status varchar NOT NULL,
    lease_until timestamptz,
    result varchar,
    held_reason varchar,
    method varchar,
    trial boolean,
    model_scores jsonb,
    rubric_version_id uuid NOT NULL,
    model_version varchar,
    prompt_version varchar,
    failure_code varchar,
    retry_count integer NOT NULL,
    trace_id varchar,
    created_at timestamptz NOT NULL,
    completed_at timestamptz,
    CONSTRAINT pk_judgment PRIMARY KEY (id),
    CONSTRAINT uq_judgment_answer_id
        UNIQUE (answer_id),
    CONSTRAINT ck_judgment_process_status
        CHECK (process_status IN ('PENDING', 'RUNNING', 'DONE', 'FAILED')),
    CONSTRAINT ck_judgment_result
        CHECK (result IN ('CORRECT', 'PARTIAL', 'RETHINK', 'HELD')),
    CONSTRAINT ck_judgment_held_reason
        CHECK (held_reason IN (
            'INSUFFICIENT_EVIDENCE',
            'QUOTE_MISMATCH',
            'TOO_SHORT',
            'UNVERIFIED_SCOPE',
            'MODEL_DISAGREEMENT',
            'LOW_CONFIDENCE'
        )),
    CONSTRAINT ck_judgment_method
        CHECK (method IN ('RULE', 'LLM')),
    CONSTRAINT ck_judgment_result_when_done
        CHECK ((process_status = 'DONE') = (result IS NOT NULL)),
    CONSTRAINT ck_judgment_held_reason_required
        CHECK ((result IS NOT DISTINCT FROM 'HELD') = (held_reason IS NOT NULL))
);

CREATE TABLE judgment_element (
    id uuid NOT NULL,
    judgment_id uuid NOT NULL,
    rubric_element_id uuid NOT NULL,
    quote text,
    verified boolean NOT NULL,
    satisfied boolean NOT NULL,
    source_type varchar,
    CONSTRAINT pk_judgment_element PRIMARY KEY (id),
    CONSTRAINT uq_judgment_element_judgment_id_rubric_element_id
        UNIQUE (judgment_id, rubric_element_id),
    CONSTRAINT ck_judgment_element_source_type
        CHECK (source_type IN ('RECORD', 'RULE', 'ANSWER_KEY', 'AI_OBSERVATION')),
    CONSTRAINT ck_judgment_element_verified_satisfied
        CHECK (verified OR NOT satisfied)
);

CREATE TABLE followup (
    id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    judgment_id uuid NOT NULL,
    type varchar NOT NULL,
    question text NOT NULL,
    source varchar NOT NULL,
    leak_check_passed boolean NOT NULL,
    prompt_version varchar,
    model_version varchar,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_followup PRIMARY KEY (id),
    CONSTRAINT uq_followup_judgment_id
        UNIQUE (judgment_id),
    CONSTRAINT ck_followup_type
        CHECK (type IN ('ONE_STEP_MORE', 'TELL_MORE', 'LOOK_AGAIN')),
    CONSTRAINT ck_followup_source
        CHECK (source IN ('LLM', 'LLM_RETRY', 'BANK', 'TEMPLATE'))
);

CREATE TABLE judgment_correction (
    id uuid NOT NULL,
    judgment_id uuid NOT NULL,
    error_report_id uuid NOT NULL,
    reason text NOT NULL,
    previous jsonb NOT NULL,
    corrected jsonb NOT NULL,
    corrected_by uuid NOT NULL,
    idempotency_key uuid NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_judgment_correction PRIMARY KEY (id),
    CONSTRAINT uq_judgment_correction_idempotency_key
        UNIQUE (idempotency_key)
);

CREATE TABLE reflection (
    id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    difficulty varchar,
    changed_text text,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_reflection PRIMARY KEY (id),
    CONSTRAINT uq_reflection_attempt_id
        UNIQUE (attempt_id),
    CONSTRAINT ck_reflection_difficulty
        CHECK (difficulty IN ('EASY', 'NORMAL', 'HARD'))
);

CREATE TABLE self_assessment (
    id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    rubric_element_id uuid NOT NULL,
    checked boolean NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_self_assessment PRIMARY KEY (id),
    CONSTRAINT uq_self_assessment_attempt_id_rubric_element_id
        UNIQUE (attempt_id, rubric_element_id)
);

ALTER TABLE attempt
    ADD CONSTRAINT fk_attempt_mission_id
    FOREIGN KEY (mission_id) REFERENCES mission (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE attempt
    ADD CONSTRAINT fk_attempt_mission_version_id
    FOREIGN KEY (mission_version_id) REFERENCES mission_version (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE attempt
    ADD CONSTRAINT fk_attempt_rubric_version_id
    FOREIGN KEY (rubric_version_id) REFERENCES rubric_version (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE attempt_draft
    ADD CONSTRAINT fk_attempt_draft_attempt_id
    FOREIGN KEY (attempt_id) REFERENCES attempt (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE hint_usage
    ADD CONSTRAINT fk_hint_usage_attempt_id
    FOREIGN KEY (attempt_id) REFERENCES attempt (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE hint_usage
    ADD CONSTRAINT fk_hint_usage_hint_question_id
    FOREIGN KEY (hint_question_id) REFERENCES hint_question (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE answer
    ADD CONSTRAINT fk_answer_attempt_id
    FOREIGN KEY (attempt_id) REFERENCES attempt (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE answer
    ADD CONSTRAINT fk_answer_followup_id
    FOREIGN KEY (followup_id) REFERENCES followup (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION
    DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE answer
    ADD CONSTRAINT fk_answer_previous_answer_id
    FOREIGN KEY (previous_answer_id) REFERENCES answer (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE judgment
    ADD CONSTRAINT fk_judgment_answer_id
    FOREIGN KEY (answer_id) REFERENCES answer (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE judgment
    ADD CONSTRAINT fk_judgment_rubric_version_id
    FOREIGN KEY (rubric_version_id) REFERENCES rubric_version (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE judgment_element
    ADD CONSTRAINT fk_judgment_element_judgment_id
    FOREIGN KEY (judgment_id) REFERENCES judgment (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE judgment_element
    ADD CONSTRAINT fk_judgment_element_rubric_element_id
    FOREIGN KEY (rubric_element_id) REFERENCES rubric_element (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE followup
    ADD CONSTRAINT fk_followup_attempt_id
    FOREIGN KEY (attempt_id) REFERENCES attempt (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE followup
    ADD CONSTRAINT fk_followup_judgment_id
    FOREIGN KEY (judgment_id) REFERENCES judgment (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE judgment_correction
    ADD CONSTRAINT fk_judgment_correction_judgment_id
    FOREIGN KEY (judgment_id) REFERENCES judgment (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE reflection
    ADD CONSTRAINT fk_reflection_attempt_id
    FOREIGN KEY (attempt_id) REFERENCES attempt (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE self_assessment
    ADD CONSTRAINT fk_self_assessment_attempt_id
    FOREIGN KEY (attempt_id) REFERENCES attempt (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE self_assessment
    ADD CONSTRAINT fk_self_assessment_rubric_element_id
    FOREIGN KEY (rubric_element_id) REFERENCES rubric_element (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

CREATE UNIQUE INDEX uq_attempt_in_progress
    ON attempt (student_id, mission_id)
    WHERE status = 'IN_PROGRESS';

CREATE INDEX ix_attempt_student_started
    ON attempt (student_id, started_at);

CREATE INDEX ix_answer_attempt_submitted
    ON answer (attempt_id, submitted_at);

CREATE INDEX ix_judgment_status_lease
    ON judgment (process_status, lease_until);
