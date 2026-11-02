-- Initial schema: docs/design/erd.md section 4.3.
-- IDs and timestamps are supplied by the application. No seed data.

CREATE TABLE deleted_student (
    student_id uuid NOT NULL,
    scope varchar NOT NULL,
    event_id uuid NOT NULL,
    deleted_at timestamptz NOT NULL,
    CONSTRAINT pk_deleted_student PRIMARY KEY (student_id),
    CONSTRAINT ck_deleted_student_scope
        CHECK (scope IN ('PROFILE', 'RECORDS'))
);

CREATE TABLE processed_event (
    event_id uuid NOT NULL,
    event_type varchar NOT NULL,
    processed_at timestamptz NOT NULL,
    CONSTRAINT pk_processed_event PRIMARY KEY (event_id)
);
