CREATE TABLE conversation_job_retry (
    id uuid NOT NULL,
    message_id uuid NOT NULL,
    generation integer NOT NULL,
    requested_by uuid NOT NULL,
    idempotency_key uuid NOT NULL,
    status varchar NOT NULL,
    accepted_at timestamptz NOT NULL,
    started_at timestamptz,
    finished_at timestamptz,
    CONSTRAINT pk_conversation_job_retry PRIMARY KEY (id),
    CONSTRAINT fk_conversation_job_retry_message FOREIGN KEY (message_id) REFERENCES conversation_message(id) ON DELETE CASCADE,
    CONSTRAINT fk_conversation_job_retry_actor FOREIGN KEY (requested_by) REFERENCES user_account(id),
    CONSTRAINT uq_conversation_job_retry_generation UNIQUE (message_id,generation),
    CONSTRAINT uq_conversation_job_retry_key UNIQUE (requested_by,idempotency_key),
    CONSTRAINT ck_conversation_job_retry_generation CHECK (generation > 0),
    CONSTRAINT ck_conversation_job_retry_status CHECK (status IN ('QUEUED','RUNNING','COMPLETED','FAILED')),
    CONSTRAINT ck_conversation_job_retry_times CHECK (
        (status='QUEUED' AND started_at IS NULL AND finished_at IS NULL) OR
        (status='RUNNING' AND started_at IS NOT NULL AND finished_at IS NULL) OR
        (status='COMPLETED' AND started_at IS NOT NULL AND finished_at IS NOT NULL) OR
        (status='FAILED' AND finished_at IS NOT NULL)),
    CONSTRAINT ck_conversation_job_retry_order CHECK (
        (started_at IS NULL OR started_at >= accepted_at) AND
        (finished_at IS NULL OR finished_at >= COALESCE(started_at,accepted_at)))
);
CREATE INDEX ix_conversation_job_retry_pending ON conversation_job_retry(status,accepted_at);
