-- #47: explicit retries create a new job; original FAILED jobs remain unchanged.
CREATE TABLE report_job_retry (
    original_job_id uuid NOT NULL,
    retry_job_id uuid NOT NULL,
    requested_by uuid NOT NULL,
    idempotency_key uuid NOT NULL,
    accepted_at timestamptz NOT NULL,
    CONSTRAINT pk_report_job_retry PRIMARY KEY (original_job_id),
    CONSTRAINT uq_report_job_retry_job UNIQUE (retry_job_id),
    CONSTRAINT uq_report_job_retry_request UNIQUE (requested_by, idempotency_key),
    CONSTRAINT ck_report_job_retry_distinct CHECK (original_job_id <> retry_job_id),
    CONSTRAINT fk_report_job_retry_original FOREIGN KEY (original_job_id) REFERENCES report_job(id),
    CONSTRAINT fk_report_job_retry_job FOREIGN KEY (retry_job_id) REFERENCES report_job(id),
    CONSTRAINT fk_report_job_retry_actor FOREIGN KEY (requested_by) REFERENCES user_account(id)
);
