-- #438 학년별 주간 테마 준비, 테마 이야기·장면·정답 구조, 테마 초안, 이야기 열람 (ERD 4.2.1, 에픽 #436)
-- 학년군(grade_band: G3_4·G5_6) → 학년(grade: G3~G6, 담당자 결정 2026-11-10). 이 버전은 grade를 nullable로 더하고 기존 행을 옮긴다.
-- NOT NULL·CHECK와 grade_band 제거는 V15 (ERD 8장 준비·최종 버전)

ALTER TABLE weekly_theme ADD COLUMN grade varchar;

-- 옛 게시 UK·목록 인덱스는 학년군 기준이라 먼저 지운다.
-- 아래 복사본도 grade_band가 원래 값(G3_4·G5_6)이라 옛 UK가 남아 있으면 게시 테마 복사가 막힘
DROP INDEX uq_weekly_theme_published_week;
DROP INDEX ix_weekly_theme_band_status_week;

-- 기존 학년군 테마는 학년마다 같은 내용으로 둔다(기준안): 원래 행은 낮은 학년(G3·G5)으로 바꾸고,
-- 높은 학년(G4·G6)은 테마·버전·요일을 복사한다. 시도·열람 기록의 theme_id는 원래 행을 가리킨 채 둔다
UPDATE weekly_theme SET grade = 'G3' WHERE grade_band = 'G3_4';
UPDATE weekly_theme SET grade = 'G5' WHERE grade_band = 'G5_6';

-- 복사본 ID는 원래 ID와 학년으로 정하는 값(어느 환경에서 돌려도 같은 ID). 컬럼 기본값이 아니라 이 이전 작업에서만 만든다
-- 테마 ↔ 버전 순환 FK(DEFERRABLE INITIALLY IMMEDIATE)는 이 트랜잭션에서만 커밋 때 검사
SET CONSTRAINTS fk_weekly_theme_current_version_id, fk_weekly_theme_published_version_id, fk_weekly_theme_review_version_id DEFERRED;

INSERT INTO weekly_theme
    (id, grade_band, grade, week_start, status, current_version_id, published_version_id, review_version_id,
     created_by, published_at, created_at, updated_at)
SELECT md5(t.id::text || ':' || m.copy_grade)::uuid, t.grade_band, m.copy_grade, t.week_start, t.status,
       md5(t.current_version_id::text || ':' || m.copy_grade)::uuid,
       CASE WHEN t.published_version_id IS NULL THEN NULL ELSE md5(t.published_version_id::text || ':' || m.copy_grade)::uuid END,
       CASE WHEN t.review_version_id IS NULL THEN NULL ELSE md5(t.review_version_id::text || ':' || m.copy_grade)::uuid END,
       t.created_by, t.published_at, t.created_at, t.updated_at
FROM weekly_theme t
JOIN (VALUES ('G3', 'G4'), ('G5', 'G6')) AS m (source_grade, copy_grade) ON t.grade = m.source_grade;

INSERT INTO weekly_theme_version (id, theme_id, version, title, intro, created_by, created_at)
SELECT md5(v.id::text || ':' || m.copy_grade)::uuid, md5(t.id::text || ':' || m.copy_grade)::uuid,
       v.version, v.title, v.intro, v.created_by, v.created_at
FROM weekly_theme_version v
JOIN weekly_theme t ON t.id = v.theme_id
JOIN (VALUES ('G3', 'G4'), ('G5', 'G6')) AS m (source_grade, copy_grade) ON t.grade = m.source_grade;

INSERT INTO weekly_theme_day (theme_version_id, day_of_week, mission_id)
SELECT md5(d.theme_version_id::text || ':' || m.copy_grade)::uuid, d.day_of_week, d.mission_id
FROM weekly_theme_day d
JOIN weekly_theme_version v ON v.id = d.theme_version_id
JOIN weekly_theme t ON t.id = v.theme_id
JOIN (VALUES ('G3', 'G4'), ('G5', 'G6')) AS m (source_grade, copy_grade) ON t.grade = m.source_grade;

SET CONSTRAINTS fk_weekly_theme_current_version_id, fk_weekly_theme_published_version_id, fk_weekly_theme_review_version_id IMMEDIATE;

-- 같은 학년·주에 게시 테마는 하나 (게시 검사 "주당 게시 1개"의 최종 방어)
CREATE UNIQUE INDEX uq_weekly_theme_published_week
    ON weekly_theme (grade, week_start) WHERE status = 'PUBLISHED';

-- 이번 주 테마 해석(그 주 게시본, 없으면 최근 게시본)·관리자 목록
CREATE INDEX ix_weekly_theme_grade_status_week
    ON weekly_theme (grade, status, week_start);

-- 테마 이야기·장면·정답 구조(기준안). 버전 칸이라 테마 새 버전 때 함께 복사. 사람이 쓴 테마는 비워도 되어 모두 NULL 허용.
-- *_uri는 ai가 올린 S3 키(theme-drafts/{실행 ID}/{장면}), 응답 URL은 learning이 presigned로 만든다
ALTER TABLE weekly_theme_version ADD COLUMN outro text;
ALTER TABLE weekly_theme_version ADD COLUMN intro_image_uri varchar;
ALTER TABLE weekly_theme_version ADD COLUMN outro_image_uri varchar;
ALTER TABLE weekly_theme_version ADD COLUMN intro_video_uri varchar;
ALTER TABLE weekly_theme_version ADD COLUMN outro_video_uri varchar;
ALTER TABLE weekly_theme_version ADD COLUMN intro_motion jsonb;
ALTER TABLE weekly_theme_version ADD COLUMN outro_motion jsonb;
ALTER TABLE weekly_theme_version ADD COLUMN big_question text;
ALTER TABLE weekly_theme_version ADD COLUMN candidates jsonb;
ALTER TABLE weekly_theme_version ADD COLUMN answer varchar;
ALTER TABLE weekly_theme_version ADD COLUMN answer_clue text;

-- 요일 단서·빠지는 후보, 문제 전 대화, 그림 위 생각 열기 위치 [{seq, x, y}], 문제 전 영상 키
ALTER TABLE weekly_theme_day ADD COLUMN clue text;
ALTER TABLE weekly_theme_day ADD COLUMN rules_out jsonb;
ALTER TABLE weekly_theme_day ADD COLUMN dialogue jsonb;
ALTER TABLE weekly_theme_day ADD COLUMN hint_spots jsonb;
ALTER TABLE weekly_theme_day ADD COLUMN video_uri varchar;

-- 미션 장면 그림 움직임 (움직임 줄이기면 쓰지 않음)
ALTER TABLE mission_version ADD COLUMN scene_motion jsonb;

-- 테마 초안 채택으로 만든 미션
ALTER TABLE mission DROP CONSTRAINT ck_mission_source;
ALTER TABLE mission
    ADD CONSTRAINT ck_mission_source CHECK (source IN ('MANUAL', 'LLM_DRAFT', 'LLM_THEME'));

-- 시작·종료 이야기 열람: 학생·주·종류당 1행(ON CONFLICT DO NOTHING) 멱등. 학생 삭제 때 물리 삭제
CREATE TABLE theme_story_view (
    student_id uuid NOT NULL,
    week_start date NOT NULL,
    kind varchar NOT NULL,
    theme_id uuid NOT NULL,
    viewed_at timestamptz NOT NULL,
    CONSTRAINT pk_theme_story_view PRIMARY KEY (student_id, week_start, kind),
    CONSTRAINT ck_theme_story_view_kind CHECK (kind IN ('INTRO', 'OUTRO'))
);

ALTER TABLE theme_story_view
    ADD CONSTRAINT fk_theme_story_view_theme_id
    FOREIGN KEY (theme_id) REFERENCES weekly_theme (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

-- 테마 초안: 검사에 실패한 초안은 테마를 만들지 않아 weekly_theme과 따로 둔다(mission_draft와 같은 구조). 학생 ID·학생 답은 없다
CREATE TABLE theme_draft (
    id uuid NOT NULL,
    grade varchar NOT NULL,
    week_start date NOT NULL,
    source varchar NOT NULL,
    status varchar NOT NULL,
    requested_by uuid,
    input jsonb NOT NULL,
    attempts int NOT NULL,
    check_results jsonb,
    output jsonb,
    failure_code varchar,
    model_version varchar,
    prompt_version varchar,
    lease_until timestamptz,
    theme_id uuid,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT pk_theme_draft PRIMARY KEY (id),
    CONSTRAINT uq_theme_draft_theme_id UNIQUE (theme_id),
    CONSTRAINT ck_theme_draft_grade CHECK (grade IN ('G3', 'G4', 'G5', 'G6')),
    CONSTRAINT ck_theme_draft_week_start_monday CHECK (EXTRACT(ISODOW FROM week_start) = 1),
    CONSTRAINT ck_theme_draft_source CHECK (source IN ('AUTO', 'ADMIN')),
    CONSTRAINT ck_theme_draft_status
        CHECK (status IN ('GENERATING', 'READY', 'CHECK_FAILED', 'FAILED', 'ADOPTED', 'DISCARDED')),
    CONSTRAINT ck_theme_draft_attempts CHECK (attempts >= 0)
);

ALTER TABLE theme_draft
    ADD CONSTRAINT fk_theme_draft_theme_id
    FOREIGN KEY (theme_id) REFERENCES weekly_theme (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

-- 주간 자동 생성은 학년·주당 1개: 레플리카가 같이 돌아도 ON CONFLICT DO NOTHING으로 하나만
CREATE UNIQUE INDEX uq_theme_draft_auto_week
    ON theme_draft (grade, week_start) WHERE source = 'AUTO';

-- 목록(상태 필터, 최근 요청 순)과 생성 작업의 GENERATING 점유
CREATE INDEX ix_theme_draft_status_created
    ON theme_draft (status, created_at);
