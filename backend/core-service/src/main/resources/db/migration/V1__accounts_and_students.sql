-- Initial schema: docs/design/erd.md section 3.1.
-- IDs and timestamps are supplied by the application. No seed data.

CREATE TABLE user_account (
    id uuid NOT NULL,
    role varchar NOT NULL,
    login_id varchar NOT NULL,
    password_hash varchar NOT NULL,
    display_name varchar,
    status varchar NOT NULL,
    is_demo boolean NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    withdrawn_at timestamptz,
    CONSTRAINT pk_user_account PRIMARY KEY (id),
    CONSTRAINT uq_user_account_login_id
        UNIQUE (login_id),
    CONSTRAINT ck_user_account_role
        CHECK (role IN ('STUDENT', 'PARENT', 'ADMIN')),
    CONSTRAINT ck_user_account_status
        CHECK (status IN ('ACTIVE', 'WITHDRAWAL_REQUESTED', 'WITHDRAWN'))
);

CREATE TABLE admin_permission (
    user_id uuid NOT NULL,
    permission varchar NOT NULL,
    granted_by uuid NOT NULL,
    granted_at timestamptz NOT NULL,
    CONSTRAINT pk_admin_permission PRIMARY KEY (user_id, permission),
    CONSTRAINT ck_admin_permission_permission
        CHECK (permission IN ('CONTENT', 'PAYMENT_VIEW', 'PAYMENT_REFUND', 'SERVICE_OPS'))
);

CREATE TABLE refresh_token (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    token_hash varchar NOT NULL,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_refresh_token PRIMARY KEY (id),
    CONSTRAINT uq_refresh_token_token_hash
        UNIQUE (token_hash)
);

CREATE TABLE student (
    id uuid NOT NULL,
    user_account_id uuid,
    nickname varchar NOT NULL,
    grade integer NOT NULL,
    is_demo boolean NOT NULL,
    status varchar NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    deleted_at timestamptz,
    CONSTRAINT pk_student PRIMARY KEY (id),
    CONSTRAINT uq_student_user_account_id
        UNIQUE (user_account_id),
    CONSTRAINT ck_student_status
        CHECK (status IN ('ACTIVE', 'DELETION_REQUESTED', 'DELETED'))
);

CREATE TABLE consent_document (
    id uuid NOT NULL,
    kind varchar NOT NULL,
    version varchar NOT NULL,
    title varchar NOT NULL,
    content text NOT NULL,
    required boolean NOT NULL,
    effective_from date NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_consent_document PRIMARY KEY (id),
    CONSTRAINT uq_consent_document_kind_version
        UNIQUE (kind, version),
    CONSTRAINT ck_consent_document_kind
        CHECK (kind IN ('TERMS', 'PRIVACY', 'GUARDIAN'))
);

CREATE TABLE consent (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    subject_user_id uuid NOT NULL,
    student_id uuid,
    agreed boolean NOT NULL,
    status varchar NOT NULL,
    agreed_at timestamptz NOT NULL,
    withdrawn_at timestamptz,
    CONSTRAINT pk_consent PRIMARY KEY (id),
    CONSTRAINT ck_consent_status
        CHECK (status IN ('AGREED', 'WITHDRAWN'))
);

CREATE TABLE guardianship (
    id uuid NOT NULL,
    parent_user_id uuid NOT NULL,
    student_id uuid NOT NULL,
    method varchar NOT NULL,
    status varchar NOT NULL,
    linked_at timestamptz NOT NULL,
    unlinked_at timestamptz,
    CONSTRAINT pk_guardianship PRIMARY KEY (id),
    CONSTRAINT ck_guardianship_method
        CHECK (method IN ('REGISTER', 'LINK')),
    CONSTRAINT ck_guardianship_status
        CHECK (status IN ('LINKED', 'UNLINKED'))
);

CREATE TABLE deletion_request (
    id uuid NOT NULL,
    requested_by uuid NOT NULL,
    student_id uuid NOT NULL,
    scope varchar NOT NULL,
    status varchar NOT NULL,
    requested_at timestamptz NOT NULL,
    confirmed_at timestamptz,
    completed_at timestamptz,
    CONSTRAINT pk_deletion_request PRIMARY KEY (id),
    CONSTRAINT ck_deletion_request_scope
        CHECK (scope IN ('PROFILE', 'RECORDS')),
    CONSTRAINT ck_deletion_request_status
        CHECK (status IN ('REQUESTED', 'CONFIRMED', 'COMPLETED'))
);

CREATE TABLE withdrawal_request (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    status varchar NOT NULL,
    requested_at timestamptz NOT NULL,
    completed_at timestamptz,
    CONSTRAINT pk_withdrawal_request PRIMARY KEY (id),
    CONSTRAINT ck_withdrawal_request_status
        CHECK (status IN ('REQUESTED', 'COMPLETED'))
);

ALTER TABLE admin_permission
    ADD CONSTRAINT fk_admin_permission_user_id
    FOREIGN KEY (user_id) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE admin_permission
    ADD CONSTRAINT fk_admin_permission_granted_by
    FOREIGN KEY (granted_by) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE refresh_token
    ADD CONSTRAINT fk_refresh_token_user_id
    FOREIGN KEY (user_id) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE student
    ADD CONSTRAINT fk_student_user_account_id
    FOREIGN KEY (user_account_id) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE consent
    ADD CONSTRAINT fk_consent_document_id
    FOREIGN KEY (document_id) REFERENCES consent_document (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE consent
    ADD CONSTRAINT fk_consent_subject_user_id
    FOREIGN KEY (subject_user_id) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE consent
    ADD CONSTRAINT fk_consent_student_id
    FOREIGN KEY (student_id) REFERENCES student (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE guardianship
    ADD CONSTRAINT fk_guardianship_parent_user_id
    FOREIGN KEY (parent_user_id) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE guardianship
    ADD CONSTRAINT fk_guardianship_student_id
    FOREIGN KEY (student_id) REFERENCES student (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE deletion_request
    ADD CONSTRAINT fk_deletion_request_requested_by
    FOREIGN KEY (requested_by) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE deletion_request
    ADD CONSTRAINT fk_deletion_request_student_id
    FOREIGN KEY (student_id) REFERENCES student (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE withdrawal_request
    ADD CONSTRAINT fk_withdrawal_request_user_id
    FOREIGN KEY (user_id) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

CREATE UNIQUE INDEX uq_guardianship_linked
    ON guardianship (parent_user_id, student_id)
    WHERE status = 'LINKED';

CREATE INDEX ix_guardianship_parent_linked
    ON guardianship (parent_user_id)
    WHERE status = 'LINKED';
