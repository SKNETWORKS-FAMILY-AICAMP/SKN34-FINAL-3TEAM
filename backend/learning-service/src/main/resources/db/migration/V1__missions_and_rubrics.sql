-- Initial schema: docs/design/erd.md section 4.1.
-- IDs and timestamps are supplied by the application. No seed data.

CREATE TABLE mission (
    id uuid NOT NULL,
    code varchar NOT NULL,
    status varchar NOT NULL,
    current_version_id uuid,
    current_rubric_version_id uuid,
    demo_only boolean NOT NULL,
    sort_order integer NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    published_at timestamptz,
    CONSTRAINT pk_mission PRIMARY KEY (id),
    CONSTRAINT uq_mission_code
        UNIQUE (code),
    CONSTRAINT ck_mission_status
        CHECK (status IN ('DRAFT', 'REVIEW_REQUIRED', 'PUBLISHED', 'UNPUBLISHED'))
);

CREATE TABLE mission_version (
    id uuid NOT NULL,
    mission_id uuid NOT NULL,
    version integer NOT NULL,
    title varchar NOT NULL,
    subject varchar NOT NULL,
    grade_min integer NOT NULL,
    grade_max integer NOT NULL,
    thinking_type varchar NOT NULL,
    basic_skills jsonb,
    input_type varchar NOT NULL,
    question text NOT NULL,
    guide text,
    scene_uri varchar,
    static_scene_uri varchar,
    choices jsonb,
    input_template jsonb,
    achievement_standards jsonb,
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_mission_version PRIMARY KEY (id),
    CONSTRAINT uq_mission_version_mission_id_version
        UNIQUE (mission_id, version),
    CONSTRAINT ck_mission_version_thinking_type
        CHECK (thinking_type IN ('ANALYZE', 'EVALUATE', 'CREATE', 'SOLVE', 'REFLECT')),
    CONSTRAINT ck_mission_version_input_type
        CHECK (input_type IN (
            'CHOICE',
            'ORDERING',
            'CLASSIFICATION',
            'NARRATIVE',
            'SOLUTION_STEPS',
            'ESSAY'
        ))
);

CREATE TABLE rubric_version (
    id uuid NOT NULL,
    mission_id uuid NOT NULL,
    version integer NOT NULL,
    answer_key jsonb,
    example_answer text,
    forbidden_terms jsonb,
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_rubric_version PRIMARY KEY (id),
    CONSTRAINT uq_rubric_version_mission_id_version
        UNIQUE (mission_id, version)
);

CREATE TABLE rubric_element (
    id uuid NOT NULL,
    rubric_version_id uuid NOT NULL,
    code varchar NOT NULL,
    label varchar NOT NULL,
    description text,
    points integer NOT NULL,
    common_errors jsonb,
    good_thought boolean NOT NULL,
    judge_verified boolean NOT NULL,
    sort_order integer NOT NULL,
    CONSTRAINT pk_rubric_element PRIMARY KEY (id)
);

CREATE TABLE hint_question (
    id uuid NOT NULL,
    rubric_version_id uuid NOT NULL,
    seq integer NOT NULL,
    content text NOT NULL,
    CONSTRAINT pk_hint_question PRIMARY KEY (id)
);

CREATE TABLE mission_review (
    id uuid NOT NULL,
    mission_id uuid NOT NULL,
    mission_version_id uuid NOT NULL,
    rubric_version_id uuid NOT NULL,
    reviewer_id uuid NOT NULL,
    result varchar NOT NULL,
    comment text,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_mission_review PRIMARY KEY (id),
    CONSTRAINT ck_mission_review_result
        CHECK (result IN ('APPROVED', 'CHANGES_REQUESTED'))
);

ALTER TABLE mission
    ADD CONSTRAINT fk_mission_current_version_id
    FOREIGN KEY (current_version_id) REFERENCES mission_version (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION
    DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE mission
    ADD CONSTRAINT fk_mission_current_rubric_version_id
    FOREIGN KEY (current_rubric_version_id) REFERENCES rubric_version (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION
    DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE mission_version
    ADD CONSTRAINT fk_mission_version_mission_id
    FOREIGN KEY (mission_id) REFERENCES mission (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE rubric_version
    ADD CONSTRAINT fk_rubric_version_mission_id
    FOREIGN KEY (mission_id) REFERENCES mission (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE rubric_element
    ADD CONSTRAINT fk_rubric_element_rubric_version_id
    FOREIGN KEY (rubric_version_id) REFERENCES rubric_version (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE hint_question
    ADD CONSTRAINT fk_hint_question_rubric_version_id
    FOREIGN KEY (rubric_version_id) REFERENCES rubric_version (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE mission_review
    ADD CONSTRAINT fk_mission_review_mission_id
    FOREIGN KEY (mission_id) REFERENCES mission (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE mission_review
    ADD CONSTRAINT fk_mission_review_mission_version_id
    FOREIGN KEY (mission_version_id) REFERENCES mission_version (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE mission_review
    ADD CONSTRAINT fk_mission_review_rubric_version_id
    FOREIGN KEY (rubric_version_id) REFERENCES rubric_version (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

CREATE INDEX ix_mission_status_sort
    ON mission (status, sort_order);

CREATE INDEX ix_mission_version_type_grade
    ON mission_version (thinking_type, grade_min, grade_max);
