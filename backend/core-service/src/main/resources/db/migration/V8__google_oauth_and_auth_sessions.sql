-- Preserve legacy accounts; never invent Google identities or merge by email.
ALTER TABLE user_account
    ALTER COLUMN password_hash DROP NOT NULL,
    ADD COLUMN oauth_provider varchar,
    ADD COLUMN oauth_subject varchar,
    ADD CONSTRAINT uq_user_account_oauth UNIQUE (oauth_provider, oauth_subject),
    ADD CONSTRAINT ck_user_account_oauth CHECK (
        (oauth_provider IS NULL AND oauth_subject IS NULL) OR
        (oauth_provider IS NOT NULL AND oauth_provider = 'GOOGLE' AND oauth_subject IS NOT NULL AND length(oauth_subject) > 0)
    );

CREATE TABLE auth_session (
    id uuid NOT NULL PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES user_account(id),
    role varchar NOT NULL CHECK (role IN ('PARENT', 'STUDENT', 'ADMIN')),
    student_id uuid REFERENCES student(id),
    version bigint NOT NULL CHECK (version > 0),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL,
    CONSTRAINT ck_auth_session_student CHECK (
        (role = 'STUDENT' AND student_id IS NOT NULL) OR (role <> 'STUDENT' AND student_id IS NULL)
    )
);
CREATE INDEX ix_auth_session_user ON auth_session(user_id);
ALTER TABLE refresh_token
    ADD COLUMN session_id uuid REFERENCES auth_session(id),
    ADD COLUMN used_at timestamptz;
CREATE INDEX ix_refresh_token_session ON refresh_token(session_id);
-- Tokens predating session binding cannot be safely restored.
UPDATE refresh_token SET revoked_at = CURRENT_TIMESTAMP WHERE revoked_at IS NULL;
