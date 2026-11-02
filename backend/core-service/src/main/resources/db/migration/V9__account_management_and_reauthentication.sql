-- #45 only. V1..V8 are immutable. #58 device/PIN tables are not assumed.
CREATE TABLE reauth_challenge (
 id uuid PRIMARY KEY,
 user_id uuid NOT NULL REFERENCES user_account(id),
 session_id uuid NOT NULL REFERENCES auth_session(id),
 session_version bigint NOT NULL,
 purpose varchar NOT NULL CHECK (purpose IN ('PIN_CHANGE','CHILD_UNLINK','CHILD_DELETE','WITHDRAWAL')),
 student_id uuid REFERENCES student(id),
 scope varchar CHECK (scope IN ('PROFILE','RECORDS')),
 state_hash varchar NOT NULL UNIQUE,
 expires_at timestamptz NOT NULL,
 verified_at timestamptz,
 issued_at timestamptz,
 CONSTRAINT ck_reauth_challenge_target CHECK (
   (purpose='WITHDRAWAL' AND student_id IS NULL AND scope IS NULL) OR
   (purpose IN ('PIN_CHANGE','CHILD_UNLINK') AND student_id IS NOT NULL AND scope IS NULL) OR
   (purpose='CHILD_DELETE' AND student_id IS NOT NULL AND scope IS NOT NULL)
 )
);
CREATE TABLE reauth_grant (
 token_hash varchar PRIMARY KEY,
 challenge_id uuid NOT NULL UNIQUE REFERENCES reauth_challenge(id),
 expires_at timestamptz NOT NULL,
 used_at timestamptz
);
CREATE TABLE deletion_completion (
 request_id uuid NOT NULL REFERENCES deletion_request(id),
 service varchar NOT NULL CHECK (service IN ('learning','report')),
 completed_at timestamptz NOT NULL,
 PRIMARY KEY (request_id, service)
);
ALTER TABLE withdrawal_request ADD COLUMN status_token_hash varchar UNIQUE;
ALTER TABLE student ALTER COLUMN nickname DROP NOT NULL,
 ALTER COLUMN grade DROP NOT NULL, ALTER COLUMN birth_year DROP NOT NULL;
ALTER TABLE student ADD CONSTRAINT ck_student_live_profile CHECK (
 status='DELETED' OR (nickname IS NOT NULL AND grade IS NOT NULL AND birth_year IS NOT NULL)
);
