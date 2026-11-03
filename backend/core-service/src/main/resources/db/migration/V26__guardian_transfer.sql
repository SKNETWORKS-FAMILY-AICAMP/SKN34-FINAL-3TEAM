-- #289: extend V24 guardian-password reauthentication without changing applied migrations.
-- Fail on pre-existing duplicates; never silently delete/reassign existing guardians.
CREATE UNIQUE INDEX uq_guardianship_one_current_parent ON guardianship(student_id) WHERE status='LINKED';
ALTER TABLE guardianship ADD COLUMN transferred_at timestamptz;
ALTER TABLE guardianship ADD CONSTRAINT ck_guardianship_transferred CHECK (transferred_at IS NULL OR status='UNLINKED');
ALTER TABLE guardianship DROP CONSTRAINT ck_guardianship_method;
ALTER TABLE guardianship ADD CONSTRAINT ck_guardianship_method CHECK (method IN ('REGISTER','TRANSFER'));

CREATE TABLE guardian_transfer (
 id uuid PRIMARY KEY,
 student_id uuid NOT NULL REFERENCES student(id),
 sender_id uuid NOT NULL REFERENCES user_account(id),
 recipient_id uuid NOT NULL REFERENCES user_account(id),
 include_conversations boolean NOT NULL,
 status varchar NOT NULL CHECK (status IN ('PENDING','ACCEPTED','REJECTED','CANCELLED')),
 created_at timestamptz NOT NULL,
 resolved_at timestamptz,
 CHECK (sender_id<>recipient_id),
 CHECK ((status='PENDING' AND resolved_at IS NULL) OR (status<>'PENDING' AND resolved_at IS NOT NULL))
);
CREATE UNIQUE INDEX uq_guardian_transfer_pending ON guardian_transfer(student_id) WHERE status='PENDING';
CREATE INDEX ix_guardian_transfer_sender ON guardian_transfer(sender_id,created_at);
CREATE INDEX ix_guardian_transfer_recipient ON guardian_transfer(recipient_id,created_at);

ALTER TABLE reauth_challenge DROP CONSTRAINT reauth_challenge_purpose_check;
ALTER TABLE reauth_challenge ADD CONSTRAINT reauth_challenge_purpose_check CHECK
 (purpose IN ('PIN_CHANGE','CHILD_UNLINK','CHILD_DELETE','WITHDRAWAL','GUARDIAN_PASSWORD','CHILD_TRANSFER','TRANSFER_ACCEPT'));
ALTER TABLE reauth_challenge DROP CONSTRAINT ck_reauth_challenge_target;
ALTER TABLE reauth_challenge ADD CONSTRAINT ck_reauth_challenge_target CHECK (
 (purpose IN ('WITHDRAWAL','GUARDIAN_PASSWORD','TRANSFER_ACCEPT') AND student_id IS NULL AND scope IS NULL) OR
 (purpose IN ('PIN_CHANGE','CHILD_UNLINK','CHILD_TRANSFER') AND student_id IS NOT NULL AND scope IS NULL) OR
 (purpose='CHILD_DELETE' AND student_id IS NOT NULL AND scope IS NOT NULL)
);
