-- #369 admin ID/password login. Rows are created only by scripts/admin_account_sql.py (no signup).
-- The login ID is user_account.login_id of an ADMIN row; the legacy user_account.password_hash stays unused.
CREATE TABLE admin_credential (
    user_id uuid PRIMARY KEY REFERENCES user_account(id),
    password_hash varchar NOT NULL,
    failed_count int NOT NULL CHECK (failed_count >= 0),
    locked_until timestamptz,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);
