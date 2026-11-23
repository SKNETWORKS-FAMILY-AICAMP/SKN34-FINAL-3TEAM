ALTER TABLE theme_draft ADD COLUMN planned_week date;
ALTER TABLE theme_draft ADD CONSTRAINT ck_theme_draft_planned_week
    CHECK (planned_week IS NULL OR (EXTRACT(ISODOW FROM planned_week) = 1 AND status = 'READY'));
CREATE UNIQUE INDEX uq_theme_draft_planned_week ON theme_draft (grade, planned_week) WHERE planned_week IS NOT NULL;

-- 요일 미션을 여러 주에 재사용해도 이미 게시한 주의 문제와 기준표는 그 버전을 유지한다.
ALTER TABLE weekly_theme_day
    ADD COLUMN mission_version_id uuid REFERENCES mission_version(id),
    ADD COLUMN rubric_version_id uuid REFERENCES rubric_version(id),
    ADD CONSTRAINT ck_weekly_theme_day_snapshot CHECK ((mission_version_id IS NULL) = (rubric_version_id IS NULL));
UPDATE weekly_theme_day d
SET mission_version_id = m.published_version_id, rubric_version_id = m.published_rubric_version_id
FROM mission m, weekly_theme t
WHERE t.status = 'PUBLISHED' AND t.published_version_id = d.theme_version_id AND m.id = d.mission_id
  AND m.published_version_id IS NOT NULL AND m.published_rubric_version_id IS NOT NULL;
