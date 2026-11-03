-- #209 학부모 리포트 표시 설정. #206 학생 공개 설정 V21 이후 적용.
CREATE TABLE parent_report_template (
    parent_user_id uuid PRIMARY KEY REFERENCES user_account(id),
    settings jsonb NOT NULL,
    revision bigint NOT NULL CHECK (revision >= 0),
    proposal_id uuid,
    proposal_conversation_id uuid REFERENCES conversation(id) ON DELETE SET NULL,
    proposal_settings jsonb,
    proposal_expires_at timestamptz,
    updated_at timestamptz NOT NULL
);
