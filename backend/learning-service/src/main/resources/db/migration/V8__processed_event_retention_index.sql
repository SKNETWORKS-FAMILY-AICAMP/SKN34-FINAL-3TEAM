-- #208 processed_event 보존 기간 정리용 인덱스
CREATE INDEX ix_processed_event_processed_at
    ON processed_event (processed_at);
