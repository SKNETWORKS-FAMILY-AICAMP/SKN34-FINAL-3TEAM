-- Initial schema: docs/design/erd.md section 3.5.
-- IDs and timestamps are supplied by the application. No seed data.

CREATE TABLE model_version (
    id uuid NOT NULL,
    kind varchar NOT NULL,
    name varchar NOT NULL,
    version varchar NOT NULL,
    ref_id uuid,
    artifact_uri varchar,
    eval_result jsonb,
    status varchar NOT NULL,
    approved_by uuid,
    activated_at timestamptz,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_model_version PRIMARY KEY (id),
    CONSTRAINT uq_model_version_kind_name_version
        UNIQUE (kind, name, version),
    CONSTRAINT ck_model_version_kind
        CHECK (kind IN ('RUBRIC', 'MODEL', 'PROMPT', 'GENERATION')),
    CONSTRAINT ck_model_version_status
        CHECK (status IN ('REGISTERED', 'ACTIVE', 'INACTIVE'))
);

CREATE TABLE audit_log (
    id uuid NOT NULL,
    actor_user_id uuid NOT NULL,
    action varchar NOT NULL,
    target_type varchar NOT NULL,
    target_id uuid,
    result varchar NOT NULL,
    detail jsonb,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_audit_log PRIMARY KEY (id),
    CONSTRAINT ck_audit_log_result
        CHECK (result IN ('SUCCESS', 'FAILURE'))
);

CREATE TABLE llm_usage (
    id uuid NOT NULL,
    event_id uuid NOT NULL,
    service varchar NOT NULL,
    call_type varchar NOT NULL,
    model varchar NOT NULL,
    prompt_version varchar,
    input_tokens integer,
    output_tokens integer,
    latency_ms integer NOT NULL,
    cost_usd numeric,
    success boolean NOT NULL,
    error_code varchar,
    occurred_at timestamptz NOT NULL,
    CONSTRAINT pk_llm_usage PRIMARY KEY (id),
    CONSTRAINT uq_llm_usage_event_id
        UNIQUE (event_id),
    CONSTRAINT ck_llm_usage_service
        CHECK (service IN ('ai', 'scoring')),
    CONSTRAINT ck_llm_usage_call_type
        CHECK (call_type IN (
            'JUDGMENT',
            'FOLLOWUP',
            'ANALYSIS',
            'REPORT_NARRATIVE',
            'M2',
            'M1',
            'SPEECH'
        ))
);

CREATE TABLE outbox_event (
    id uuid NOT NULL,
    event_type varchar NOT NULL,
    routing_key varchar NOT NULL,
    subject varchar NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    published_at timestamptz,
    CONSTRAINT pk_outbox_event PRIMARY KEY (id)
);

CREATE TABLE processed_event (
    event_id uuid NOT NULL,
    event_type varchar NOT NULL,
    processed_at timestamptz NOT NULL,
    CONSTRAINT pk_processed_event PRIMARY KEY (event_id)
);

CREATE TABLE idempotency_record (
    idempotency_key uuid NOT NULL,
    user_id uuid NOT NULL,
    endpoint varchar NOT NULL,
    request_hash varchar NOT NULL,
    response_status integer,
    response_body jsonb,
    created_at timestamptz NOT NULL,
    expires_at timestamptz,
    CONSTRAINT pk_idempotency_record PRIMARY KEY (idempotency_key, user_id)
);

ALTER TABLE model_version
    ADD CONSTRAINT fk_model_version_approved_by
    FOREIGN KEY (approved_by) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE audit_log
    ADD CONSTRAINT fk_audit_log_actor_user_id
    FOREIGN KEY (actor_user_id) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE idempotency_record
    ADD CONSTRAINT fk_idempotency_record_user_id
    FOREIGN KEY (user_id) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

CREATE UNIQUE INDEX uq_model_version_active
    ON model_version (kind, name)
    WHERE status = 'ACTIVE';

CREATE INDEX ix_llm_usage_occurred_call
    ON llm_usage (occurred_at, call_type);

CREATE INDEX ix_outbox_event_unpublished
    ON outbox_event (created_at)
    WHERE published_at IS NULL;
