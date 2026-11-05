-- #243 core outbox 발행 실패 기록·격리 (report #131과 같은 컬럼·기준). 영구 DEFAULT 없이 기존 행만 0으로 채움
ALTER TABLE outbox_event
    ADD COLUMN failure_count integer,
    ADD COLUMN next_attempt_at timestamptz,
    ADD COLUMN last_error_code varchar,
    ADD COLUMN last_failed_at timestamptz,
    ADD COLUMN quarantined_at timestamptz,
    ADD COLUMN manual_retry_count integer,
    ADD COLUMN last_requeued_at timestamptz;

UPDATE outbox_event SET failure_count = 0, manual_retry_count = 0;

ALTER TABLE outbox_event
    ALTER COLUMN failure_count SET NOT NULL,
    ALTER COLUMN manual_retry_count SET NOT NULL,
    ADD CONSTRAINT ck_outbox_event_failure_count CHECK (failure_count >= 0),
    ADD CONSTRAINT ck_outbox_event_manual_retry_count CHECK (manual_retry_count >= 0),
    ADD CONSTRAINT ck_outbox_event_last_error_code
        CHECK (last_error_code IN ('BROKER_UNAVAILABLE', 'PUBLISH_TIMEOUT', 'PUBLISH_FAILED'));

-- subject별 선두 조회·발행 순서 (report ix_outbox_pending_subject_order와 같은 구성)
DROP INDEX ix_outbox_event_unpublished;

CREATE INDEX ix_outbox_event_unpublished_subject
    ON outbox_event (subject, created_at, id)
    WHERE published_at IS NULL;
