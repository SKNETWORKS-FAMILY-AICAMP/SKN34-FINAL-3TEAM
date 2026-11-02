-- Initial schema: docs/design/erd.md section 3.3.
-- IDs and timestamps are supplied by the application. No seed data.

CREATE TABLE notification (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    child_id uuid,
    type varchar NOT NULL,
    source_event_id uuid NOT NULL,
    title varchar NOT NULL,
    link varchar NOT NULL,
    status varchar NOT NULL,
    retry_count integer NOT NULL,
    failure_reason varchar,
    read_at timestamptz,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_notification PRIMARY KEY (id),
    CONSTRAINT uq_notification_user_id_type_source_event_id
        UNIQUE (user_id, type, source_event_id),
    CONSTRAINT ck_notification_type
        CHECK (type IN (
            'REPORT_COMPLETED',
            'ERROR_REPORT_RESOLVED',
            'INQUIRY_ANSWERED',
            'PAYMENT_CHANGED',
            'SUBSCRIPTION_CHANGED'
        )),
    CONSTRAINT ck_notification_status
        CHECK (status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED'))
);

CREATE TABLE notification_setting (
    user_id uuid NOT NULL,
    type varchar NOT NULL,
    channel varchar NOT NULL,
    enabled boolean NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT pk_notification_setting PRIMARY KEY (user_id, type, channel),
    CONSTRAINT ck_notification_setting_type
        CHECK (type IN (
            'REPORT_COMPLETED',
            'ERROR_REPORT_RESOLVED',
            'INQUIRY_ANSWERED',
            'PAYMENT_CHANGED',
            'SUBSCRIPTION_CHANGED'
        )),
    CONSTRAINT ck_notification_setting_channel
        CHECK (channel IN ('IN_APP', 'EMAIL', 'PUSH'))
);

CREATE TABLE error_report (
    id uuid NOT NULL,
    reporter_user_id uuid NOT NULL,
    student_id uuid,
    target_type varchar NOT NULL,
    target_id uuid NOT NULL,
    category varchar,
    comment text,
    status varchar NOT NULL,
    review_result text,
    resolution_reason text,
    reviewed_by uuid,
    created_at timestamptz NOT NULL,
    resolved_at timestamptz,
    CONSTRAINT pk_error_report PRIMARY KEY (id),
    CONSTRAINT ck_error_report_target_type
        CHECK (target_type IN ('FOLLOWUP', 'JUDGMENT', 'ANALYSIS', 'REPORT')),
    CONSTRAINT ck_error_report_status
        CHECK (status IN ('RECEIVED', 'IN_REVIEW', 'RESOLVED'))
);

CREATE TABLE correction (
    id uuid NOT NULL,
    error_report_id uuid NOT NULL,
    target_type varchar NOT NULL,
    target_id uuid NOT NULL,
    reason text NOT NULL,
    impact jsonb,
    corrected_by uuid NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_correction PRIMARY KEY (id),
    CONSTRAINT ck_correction_target_type
        CHECK (target_type IN ('FOLLOWUP', 'JUDGMENT', 'ANALYSIS', 'REPORT'))
);

CREATE TABLE inquiry (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    category varchar NOT NULL,
    title varchar NOT NULL,
    body text NOT NULL,
    status varchar NOT NULL,
    answer text,
    answered_by uuid,
    answered_at timestamptz,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_inquiry PRIMARY KEY (id),
    CONSTRAINT ck_inquiry_category
        CHECK (category IN ('ACCOUNT', 'USAGE', 'PAYMENT')),
    CONSTRAINT ck_inquiry_status
        CHECK (status IN ('RECEIVED', 'IN_REVIEW', 'RESOLVED'))
);

CREATE TABLE notice (
    id uuid NOT NULL,
    kind varchar NOT NULL,
    title varchar NOT NULL,
    body text NOT NULL,
    target_roles jsonb NOT NULL,
    visible_from timestamptz NOT NULL,
    visible_to timestamptz,
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL,
    ended_at timestamptz,
    CONSTRAINT pk_notice PRIMARY KEY (id),
    CONSTRAINT ck_notice_kind
        CHECK (kind IN ('NOTICE', 'MAINTENANCE'))
);

ALTER TABLE notification
    ADD CONSTRAINT fk_notification_user_id
    FOREIGN KEY (user_id) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE notification
    ADD CONSTRAINT fk_notification_child_id
    FOREIGN KEY (child_id) REFERENCES student (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE notification_setting
    ADD CONSTRAINT fk_notification_setting_user_id
    FOREIGN KEY (user_id) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE error_report
    ADD CONSTRAINT fk_error_report_reporter_user_id
    FOREIGN KEY (reporter_user_id) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE error_report
    ADD CONSTRAINT fk_error_report_student_id
    FOREIGN KEY (student_id) REFERENCES student (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE error_report
    ADD CONSTRAINT fk_error_report_reviewed_by
    FOREIGN KEY (reviewed_by) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE correction
    ADD CONSTRAINT fk_correction_error_report_id
    FOREIGN KEY (error_report_id) REFERENCES error_report (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE correction
    ADD CONSTRAINT fk_correction_corrected_by
    FOREIGN KEY (corrected_by) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE inquiry
    ADD CONSTRAINT fk_inquiry_user_id
    FOREIGN KEY (user_id) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE inquiry
    ADD CONSTRAINT fk_inquiry_answered_by
    FOREIGN KEY (answered_by) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE notice
    ADD CONSTRAINT fk_notice_created_by
    FOREIGN KEY (created_by) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

CREATE INDEX ix_notification_user_read_created
    ON notification (user_id, read_at, created_at);
