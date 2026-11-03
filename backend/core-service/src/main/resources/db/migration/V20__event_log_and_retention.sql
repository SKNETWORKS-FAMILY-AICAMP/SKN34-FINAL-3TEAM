CREATE TABLE event_log (
    event_id uuid NOT NULL,
    event_type varchar NOT NULL,
    source varchar NOT NULL,
    subject varchar,
    event_time timestamptz NOT NULL,
    received_at timestamptz NOT NULL,
    CONSTRAINT pk_event_log PRIMARY KEY (event_id)
);

CREATE INDEX ix_event_log_received_at
    ON event_log (received_at);

CREATE INDEX ix_event_log_type_time
    ON event_log (event_type, event_time);

CREATE INDEX ix_outbox_event_published
    ON outbox_event (published_at)
    WHERE published_at IS NOT NULL;

CREATE INDEX ix_processed_event_processed_at
    ON processed_event (processed_at);
