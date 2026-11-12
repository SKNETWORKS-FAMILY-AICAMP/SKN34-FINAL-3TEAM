-- #559 P27 기념 액자 (docs/design/erd.md 4.2.1, docs/report/retention-expansion.md 3.2).
-- 새 테이블만 추가하므로 기존 행 채움 단계가 없다. 기본값은 두지 않고 앱이 모든 값을 넘긴다.
-- 도입 전 기록 소급은 앱 기동 때 ThemeFrameService.backfill이 같은 조건의 INSERT … ON CONFLICT DO NOTHING으로 한다.

CREATE TABLE theme_frame (
    id uuid NOT NULL,
    student_id uuid NOT NULL,
    theme_id uuid NOT NULL,
    theme_week_start date NOT NULL,
    theme_version_id uuid NOT NULL,
    awarded_at timestamptz NOT NULL,
    seen_at timestamptz,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_theme_frame PRIMARY KEY (id),
    -- 회차(학생·테마·주)당 액자 1개
    CONSTRAINT uq_theme_frame_student_theme_week UNIQUE (student_id, theme_id, theme_week_start),
    CONSTRAINT fk_theme_frame_theme_id FOREIGN KEY (theme_id) REFERENCES weekly_theme (id),
    CONSTRAINT fk_theme_frame_theme_version_id FOREIGN KEY (theme_version_id) REFERENCES weekly_theme_version (id),
    CONSTRAINT ck_theme_frame_week_start_monday CHECK (EXTRACT(ISODOW FROM theme_week_start) = 1)
);

-- 앨범 목록(최근 회차순)·보유 확인
CREATE INDEX ix_theme_frame_student_week
    ON theme_frame (student_id, theme_week_start);
