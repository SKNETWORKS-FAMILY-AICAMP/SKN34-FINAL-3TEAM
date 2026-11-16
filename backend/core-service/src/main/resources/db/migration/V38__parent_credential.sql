-- #415 parent ID/password signup and login. The app creates a row on signup (POST /auth/parent/signup).
-- The login ID is user_account.login_id of a PARENT row without an OAuth subject; the legacy
-- user_account.password_hash stays unused. Same shape and lock rules as admin_credential (V36).
CREATE TABLE parent_credential (
    user_id uuid PRIMARY KEY REFERENCES user_account(id),
    password_hash varchar NOT NULL,
    failed_count int NOT NULL CHECK (failed_count >= 0),
    locked_until timestamptz,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);
