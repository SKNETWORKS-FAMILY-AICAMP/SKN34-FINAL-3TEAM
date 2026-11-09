-- #385 주간 테마 준비 (P23, ERD 4.4): 학년군별 주 1테마, 월~금 하루 1문제, 토·일 되돌아보기.
-- 게시 중 수정은 미션(V7)과 같은 버전 방식: 관리자 편집은 current_version_id, 학생 조회·시작 검사는 published_version_id.
-- review_version_id는 검토 요청한 버전(게시 = 그 버전이 현재본일 때의 승인).
-- attempt.context는 기본값 없이 nullable로 추가하고 기존 행을 EXTRA로 채운다. NOT NULL·CHECK는 V12

CREATE TABLE weekly_theme (
    id uuid NOT NULL,
    grade_band varchar NOT NULL,
    week_start date NOT NULL,
    status varchar NOT NULL,
    current_version_id uuid NOT NULL,
    published_version_id uuid,
    review_version_id uuid,
    created_by uuid NOT NULL,
    published_at timestamptz,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT pk_weekly_theme PRIMARY KEY (id),
    CONSTRAINT ck_weekly_theme_grade_band
        CHECK (grade_band IN ('G3_4', 'G5_6')),
    CONSTRAINT ck_weekly_theme_status
        CHECK (status IN ('DRAFT', 'REVIEW_REQUIRED', 'PUBLISHED', 'UNPUBLISHED')),
    CONSTRAINT ck_weekly_theme_week_start_monday
        CHECK (EXTRACT(ISODOW FROM week_start) = 1)
);

CREATE TABLE weekly_theme_version (
    id uuid NOT NULL,
    theme_id uuid NOT NULL,
    version integer NOT NULL,
    title varchar NOT NULL,
    intro text NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_weekly_theme_version PRIMARY KEY (id),
    CONSTRAINT uq_weekly_theme_version_theme_version UNIQUE (theme_id, version)
);

CREATE TABLE weekly_theme_day (
    theme_version_id uuid NOT NULL,
    day_of_week smallint NOT NULL,
    mission_id uuid NOT NULL,
    CONSTRAINT pk_weekly_theme_day PRIMARY KEY (theme_version_id, day_of_week),
    CONSTRAINT uq_weekly_theme_day_version_mission UNIQUE (theme_version_id, mission_id),
    CONSTRAINT ck_weekly_theme_day_day_of_week
        CHECK (day_of_week BETWEEN 1 AND 5)
);

CREATE TABLE theme_review_view (
    student_id uuid NOT NULL,
    week_start date NOT NULL,
    theme_id uuid NOT NULL,
    viewed_at timestamptz NOT NULL,
    CONSTRAINT pk_theme_review_view PRIMARY KEY (student_id, week_start)
);

ALTER TABLE weekly_theme_version
    ADD CONSTRAINT fk_weekly_theme_version_theme_id
    FOREIGN KEY (theme_id) REFERENCES weekly_theme (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

-- 순환 참조(weekly_theme ↔ weekly_theme_version): mission.current_*·published_*와 같이 DEFERRABLE INITIALLY IMMEDIATE.
-- 작성 트랜잭션만 current_version_id 검사를 커밋 때로 미룬다
ALTER TABLE weekly_theme
    ADD CONSTRAINT fk_weekly_theme_current_version_id
    FOREIGN KEY (current_version_id) REFERENCES weekly_theme_version (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION
    DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE weekly_theme
    ADD CONSTRAINT fk_weekly_theme_published_version_id
    FOREIGN KEY (published_version_id) REFERENCES weekly_theme_version (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION
    DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE weekly_theme
    ADD CONSTRAINT fk_weekly_theme_review_version_id
    FOREIGN KEY (review_version_id) REFERENCES weekly_theme_version (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION
    DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE weekly_theme_day
    ADD CONSTRAINT fk_weekly_theme_day_theme_version_id
    FOREIGN KEY (theme_version_id) REFERENCES weekly_theme_version (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE weekly_theme_day
    ADD CONSTRAINT fk_weekly_theme_day_mission_id
    FOREIGN KEY (mission_id) REFERENCES mission (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE theme_review_view
    ADD CONSTRAINT fk_theme_review_view_theme_id
    FOREIGN KEY (theme_id) REFERENCES weekly_theme (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

-- 같은 학년군·주에 게시 테마는 하나 (게시 검사 "주당 게시 1개"의 최종 방어)
CREATE UNIQUE INDEX uq_weekly_theme_published_week
    ON weekly_theme (grade_band, week_start) WHERE status = 'PUBLISHED';

-- 이번 주 테마 해석(그 주 게시본, 없으면 최근 게시본)·관리자 목록
CREATE INDEX ix_weekly_theme_band_status_week
    ON weekly_theme (grade_band, status, week_start);

ALTER TABLE attempt ADD COLUMN context varchar;
ALTER TABLE attempt ADD COLUMN theme_id uuid;
ALTER TABLE attempt ADD COLUMN theme_week_start date;

ALTER TABLE attempt
    ADD CONSTRAINT fk_attempt_theme_id
    FOREIGN KEY (theme_id) REFERENCES weekly_theme (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

-- 기존 시도는 모두 생각 유형별 고르기(EXTRA)에서 시작한 것
UPDATE attempt SET context = 'EXTRA';

-- 학생의 그 주 테마 시도(요일 상태·되돌아보기·완주·주간 요약)
CREATE INDEX ix_attempt_student_theme_week
    ON attempt (student_id, theme_week_start);
