-- #353 성취기준 표·미션 초안 (#336 설계, ERD 4.1, FN 1.5 "성취기준·성취수준 연결", FN-ADM-20·21)

-- 성취기준 표: 참조 데이터. 시드 SQL(db/seed/achievement_standards.sql)로 넣고 관리자 API로 쓰지 않는다.
-- 평가원 성취수준 문장(levels)은 이용 조건 확인 전까지 NULL
CREATE TABLE achievement_standard (
    code varchar NOT NULL,
    subject varchar NOT NULL,
    grade_band varchar NOT NULL,
    area varchar NOT NULL,
    statement text NOT NULL,
    level_scale int NOT NULL,
    levels jsonb,
    curriculum_version varchar NOT NULL,
    source varchar NOT NULL,
    note varchar,
    CONSTRAINT pk_achievement_standard PRIMARY KEY (code),
    CONSTRAINT ck_achievement_standard_grade_band
        CHECK (grade_band IN ('초1~2', '초3~4', '초5~6', '중1~3')),
    CONSTRAINT ck_achievement_standard_level_scale
        CHECK (level_scale IN (3, 5))
);

-- 미션 초안: 검사에 실패한 초안은 미션을 만들지 않아 mission과 따로 둔다. 학생 ID·학생 답은 없다
CREATE TABLE mission_draft (
    id uuid NOT NULL,
    requested_by uuid NOT NULL,
    standard_codes jsonb NOT NULL,
    achievement_levels jsonb,
    thinking_type varchar NOT NULL,
    grade_min int NOT NULL,
    grade_max int NOT NULL,
    input_type varchar NOT NULL,
    status varchar NOT NULL,
    attempts int NOT NULL,
    check_results jsonb,
    output jsonb,
    failure_code varchar,
    model_version varchar,
    prompt_version varchar,
    lease_until timestamptz,
    mission_id uuid,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT pk_mission_draft PRIMARY KEY (id),
    CONSTRAINT uq_mission_draft_mission_id UNIQUE (mission_id),
    CONSTRAINT ck_mission_draft_thinking_type
        CHECK (thinking_type IN ('ANALYZE', 'EVALUATE', 'CREATE', 'SOLVE', 'REFLECT')),
    CONSTRAINT ck_mission_draft_input_type
        CHECK (input_type IN ('CHOICE', 'ORDERING', 'CLASSIFICATION', 'NARRATIVE', 'SOLUTION_STEPS', 'ESSAY')),
    CONSTRAINT ck_mission_draft_status
        CHECK (status IN ('GENERATING', 'READY', 'CHECK_FAILED', 'FAILED', 'ADOPTED', 'DISCARDED')),
    CONSTRAINT ck_mission_draft_grade
        CHECK (grade_min BETWEEN 3 AND 6 AND grade_max BETWEEN 3 AND 6 AND grade_min <= grade_max),
    CONSTRAINT ck_mission_draft_attempts CHECK (attempts >= 0)
);

ALTER TABLE mission_draft
    ADD CONSTRAINT fk_mission_draft_mission_id
    FOREIGN KEY (mission_id) REFERENCES mission (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

-- 목록(상태 필터, 최근 요청 순)과 생성 작업의 GENERATING 점유
CREATE INDEX ix_mission_draft_status_created
    ON mission_draft (status, created_at);

-- 미션이 처음 만들어진 방식. 버전마다 바뀌지 않아 mission에 둔다. 기존 행은 사람이 만든 미션.
-- SQL DEFAULT는 두지 않고(ERD 1장) 앱·시드가 값을 넘긴다
ALTER TABLE mission ADD COLUMN source varchar;
UPDATE mission SET source = 'MANUAL';
ALTER TABLE mission ALTER COLUMN source SET NOT NULL;
ALTER TABLE mission
    ADD CONSTRAINT ck_mission_source CHECK (source IN ('MANUAL', 'LLM_DRAFT'));

-- 성취기준별 성취수준 단계 {"6국01-02": "B"}. 키는 같은 버전 achievement_standards 안의 코드(게시 검사)
ALTER TABLE mission_version ADD COLUMN achievement_levels jsonb;

-- 요소를 구체화한 성취기준 코드. 정답 요소·#336 전 요소는 NULL
ALTER TABLE rubric_element ADD COLUMN standard_code varchar;
