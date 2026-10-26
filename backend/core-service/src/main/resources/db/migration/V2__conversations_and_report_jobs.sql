-- Initial schema: docs/design/erd.md section 3.2.
-- IDs and timestamps are supplied by the application. No seed data.

CREATE TABLE conversation (
    id uuid NOT NULL,
    parent_user_id uuid NOT NULL,
    student_id uuid NOT NULL,
    period_from date NOT NULL,
    period_to date NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT pk_conversation PRIMARY KEY (id)
);

CREATE TABLE conversation_message (
    id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    seq integer NOT NULL,
    question text NOT NULL,
    answer text,
    scope_student_id uuid,
    scope_from date,
    scope_to date,
    scope_changed boolean NOT NULL,
    status varchar NOT NULL,
    source varchar,
    clarification jsonb,
    metrics jsonb,
    verification jsonb,
    record_count integer,
    prompt_version varchar,
    model_version varchar,
    failure_code varchar,
    retry_count integer NOT NULL,
    trace_id varchar,
    created_at timestamptz NOT NULL,
    completed_at timestamptz,
    CONSTRAINT pk_conversation_message PRIMARY KEY (id),
    CONSTRAINT uq_conversation_message_conversation_id_seq
        UNIQUE (conversation_id, seq),
    CONSTRAINT ck_conversation_message_status
        CHECK (status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED')),
    CONSTRAINT ck_conversation_message_source
        CHECK (source IN ('LLM', 'LLM_RETRY', 'TEMPLATE'))
);

CREATE TABLE message_evidence (
    id uuid NOT NULL,
    message_id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    answer_id uuid NOT NULL,
    answer_version integer NOT NULL,
    CONSTRAINT pk_message_evidence PRIMARY KEY (id)
);

CREATE TABLE report_job (
    id uuid NOT NULL,
    student_id uuid NOT NULL,
    period_from date NOT NULL,
    period_to date NOT NULL,
    trigger varchar NOT NULL,
    requested_by uuid,
    status varchar NOT NULL,
    report_id uuid,
    failure_reason varchar,
    retry_count integer NOT NULL,
    trace_id varchar,
    created_at timestamptz NOT NULL,
    started_at timestamptz,
    completed_at timestamptz,
    CONSTRAINT pk_report_job PRIMARY KEY (id),
    CONSTRAINT ck_report_job_trigger
        CHECK (trigger IN ('SCHEDULE', 'REGENERATE', 'ADMIN_RETRY')),
    CONSTRAINT ck_report_job_status
        CHECK (status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED'))
);

CREATE TABLE job_execution (
    id uuid NOT NULL,
    job_type varchar NOT NULL,
    job_id uuid NOT NULL,
    attempt_no integer NOT NULL,
    status varchar NOT NULL,
    error_code varchar,
    error_detail text,
    triggered_by uuid,
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    CONSTRAINT pk_job_execution PRIMARY KEY (id),
    CONSTRAINT uq_job_execution_job_type_job_id_attempt_no
        UNIQUE (job_type, job_id, attempt_no),
    CONSTRAINT ck_job_execution_job_type
        CHECK (job_type IN ('CONVERSATION', 'REPORT', 'NOTIFICATION')),
    CONSTRAINT ck_job_execution_status
        CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED'))
);

CREATE TABLE report_view (
    id uuid NOT NULL,
    report_id uuid NOT NULL,
    user_id uuid NOT NULL,
    viewed_at timestamptz NOT NULL,
    CONSTRAINT pk_report_view PRIMARY KEY (id)
);

CREATE TABLE shedlock (
    name varchar(64) NOT NULL,
    lock_until timestamptz NOT NULL,
    locked_at timestamptz NOT NULL,
    locked_by varchar(255) NOT NULL,
    CONSTRAINT pk_shedlock PRIMARY KEY (name)
);

ALTER TABLE conversation
    ADD CONSTRAINT fk_conversation_parent_user_id
    FOREIGN KEY (parent_user_id) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE conversation
    ADD CONSTRAINT fk_conversation_student_id
    FOREIGN KEY (student_id) REFERENCES student (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE conversation_message
    ADD CONSTRAINT fk_conversation_message_conversation_id
    FOREIGN KEY (conversation_id) REFERENCES conversation (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE conversation_message
    ADD CONSTRAINT fk_conversation_message_scope_student_id
    FOREIGN KEY (scope_student_id) REFERENCES student (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE message_evidence
    ADD CONSTRAINT fk_message_evidence_message_id
    FOREIGN KEY (message_id) REFERENCES conversation_message (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE report_job
    ADD CONSTRAINT fk_report_job_student_id
    FOREIGN KEY (student_id) REFERENCES student (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE report_job
    ADD CONSTRAINT fk_report_job_requested_by
    FOREIGN KEY (requested_by) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE job_execution
    ADD CONSTRAINT fk_job_execution_triggered_by
    FOREIGN KEY (triggered_by) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE report_view
    ADD CONSTRAINT fk_report_view_user_id
    FOREIGN KEY (user_id) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

CREATE INDEX ix_conversation_parent_student_created
    ON conversation (parent_user_id, student_id, created_at);

CREATE UNIQUE INDEX uq_report_job_scheduled_week
    ON report_job (student_id, period_from)
    WHERE trigger = 'SCHEDULE';

CREATE INDEX ix_report_job_student_period
    ON report_job (student_id, period_from);

CREATE INDEX ix_report_job_status_created
    ON report_job (status, created_at);

CREATE INDEX ix_job_execution_job
    ON job_execution (job_type, job_id);

CREATE INDEX ix_report_view_report
    ON report_view (report_id);

CREATE INDEX ix_report_view_user_viewed
    ON report_view (user_id, viewed_at);
