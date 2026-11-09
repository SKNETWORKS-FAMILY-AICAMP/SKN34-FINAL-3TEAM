-- #386 P20 커뮤니티 공유물·반응 (docs/design/erd.md 4.4).
-- 새 테이블만 추가하므로 기존 행 채움 단계가 없다. 기본값은 두지 않고 앱이 모든 값을 넘긴다.

CREATE TABLE community_post (
    id uuid NOT NULL,
    student_id uuid NOT NULL,
    mission_id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    answer_id uuid NOT NULL,
    status varchar NOT NULL,
    created_at timestamptz NOT NULL,
    status_changed_at timestamptz NOT NULL,
    error_report_id uuid,
    CONSTRAINT pk_community_post PRIMARY KEY (id),
    CONSTRAINT uq_community_post_student_id_mission_id UNIQUE (student_id, mission_id),
    CONSTRAINT uq_community_post_attempt_id UNIQUE (attempt_id),
    CONSTRAINT fk_community_post_mission_id FOREIGN KEY (mission_id) REFERENCES mission (id),
    CONSTRAINT fk_community_post_attempt_id FOREIGN KEY (attempt_id) REFERENCES attempt (id),
    CONSTRAINT fk_community_post_answer_id FOREIGN KEY (answer_id) REFERENCES answer (id),
    CONSTRAINT ck_community_post_status
        CHECK (status IN ('VISIBLE', 'HIDDEN_SETTING', 'HIDDEN_REPORT', 'REMOVED'))
);

CREATE INDEX ix_community_post_mission_id_status
    ON community_post (mission_id, status);

CREATE TABLE community_reaction (
    id uuid NOT NULL,
    post_id uuid NOT NULL,
    student_id uuid NOT NULL,
    reaction varchar NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_community_reaction PRIMARY KEY (post_id, student_id, reaction),
    CONSTRAINT uq_community_reaction_id UNIQUE (id),
    CONSTRAINT fk_community_reaction_post_id FOREIGN KEY (post_id) REFERENCES community_post (id),
    CONSTRAINT ck_community_reaction_reaction
        CHECK (reaction IN ('NEW_IDEA', 'CLEAR_REASON', 'DIFFERENT_VIEW', 'WANT_MORE'))
);

CREATE INDEX ix_community_reaction_student_id_created_at
    ON community_reaction (student_id, created_at);

-- core가 마지막으로 알린 학생 공개 여부. 신고 숨김을 풀 때·새 공유 때 설정 비공개를 지키는 데 쓴다.
CREATE TABLE community_visibility (
    student_id uuid NOT NULL,
    visible boolean NOT NULL,
    reason varchar NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT pk_community_visibility PRIMARY KEY (student_id),
    CONSTRAINT ck_community_visibility_reason
        CHECK (reason IN ('SETTING', 'CONSENT', 'TRANSFER'))
);
