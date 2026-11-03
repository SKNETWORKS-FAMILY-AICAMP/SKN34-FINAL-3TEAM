-- Guardian entry keeps the parent session locked instead of converting it.
-- The parent returns from the student screen with a guardian password (digits, 4-6) set after Google reauthentication.
CREATE TABLE guardian_password (
    user_id uuid PRIMARY KEY REFERENCES user_account(id),
    password_hash varchar NOT NULL,
    failed_count int NOT NULL CHECK (failed_count >= 0),
    locked_at timestamptz,
    updated_at timestamptz NOT NULL
);
ALTER TABLE auth_session
    ADD COLUMN locked_at timestamptz,
    ADD COLUMN parent_session_id uuid REFERENCES auth_session(id),
    ADD CONSTRAINT ck_auth_session_lock CHECK (locked_at IS NULL OR role = 'PARENT'),
    ADD CONSTRAINT ck_auth_session_parent CHECK (parent_session_id IS NULL OR role = 'STUDENT');
CREATE INDEX ix_auth_session_parent ON auth_session(parent_session_id) WHERE parent_session_id IS NOT NULL;
ALTER TABLE reauth_challenge
    DROP CONSTRAINT reauth_challenge_purpose_check,
    DROP CONSTRAINT ck_reauth_challenge_target,
    ADD CONSTRAINT reauth_challenge_purpose_check CHECK (purpose IN ('PIN_CHANGE','CHILD_UNLINK','CHILD_DELETE','WITHDRAWAL','GUARDIAN_PASSWORD')),
    ADD CONSTRAINT ck_reauth_challenge_target CHECK (
        (purpose IN ('WITHDRAWAL','GUARDIAN_PASSWORD') AND student_id IS NULL AND scope IS NULL) OR
        (purpose IN ('PIN_CHANGE','CHILD_UNLINK') AND student_id IS NOT NULL AND scope IS NULL) OR
        (purpose = 'CHILD_DELETE' AND student_id IS NOT NULL AND scope IS NOT NULL)
    );
