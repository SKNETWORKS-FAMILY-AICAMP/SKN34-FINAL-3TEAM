ALTER TABLE student ADD COLUMN pin_hash varchar,
    ADD COLUMN pin_failed_count int,
    ADD COLUMN pin_locked_at timestamptz,
    ADD COLUMN pin_updated_at timestamptz;
UPDATE student SET pin_failed_count=0;
ALTER TABLE student ALTER COLUMN pin_failed_count SET NOT NULL;
ALTER TABLE student ADD CONSTRAINT ck_student_pin_count CHECK (pin_failed_count >= 0);
CREATE TABLE student_device (
    id uuid PRIMARY KEY,
    parent_user_id uuid NOT NULL REFERENCES user_account(id),
    token_hash varchar NOT NULL UNIQUE,
    label varchar NOT NULL,
    created_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    last_used_at timestamptz,
    revoked_at timestamptz,
    CONSTRAINT ck_student_device_expiry CHECK (expires_at > created_at)
);
CREATE TABLE student_device_child (
    device_id uuid NOT NULL REFERENCES student_device(id),
    student_id uuid NOT NULL REFERENCES student(id),
    PRIMARY KEY (device_id, student_id)
);
CREATE INDEX ix_student_device_parent ON student_device(parent_user_id) WHERE revoked_at IS NULL;
CREATE INDEX ix_student_device_child_student ON student_device_child(student_id);
