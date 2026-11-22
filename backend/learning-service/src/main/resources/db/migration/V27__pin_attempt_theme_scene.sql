ALTER TABLE attempt
    ADD COLUMN theme_version_id uuid,
    ADD CONSTRAINT fk_attempt_theme_day FOREIGN KEY (theme_version_id, mission_id)
        REFERENCES weekly_theme_day (theme_version_id, mission_id),
    ADD CONSTRAINT ck_attempt_theme_version CHECK (theme_version_id IS NULL OR context <> 'EXTRA');

-- 마지막 게시 이후에 시작한 시도는 그 게시본을 썼다. 그보다 오래된 시도는 생성 시각과
-- 게시 때 고정한 미션·기준표가 일치하는 과거 버전을 하나로 특정할 수 있을 때 그 버전을 쓴다.
-- 게시 이력이 충분하지 않으면 종전 조회에 쓰이던 마지막 게시본의 같은 미션 장면만 보존한다.
WITH legacy AS (
    SELECT a.id, a.theme_id, a.mission_id, a.mission_version_id, a.rubric_version_id,
           a.started_at, t.published_at, public_day.theme_version_id AS last_public
    FROM attempt a
    JOIN weekly_theme t ON t.id = a.theme_id
    LEFT JOIN weekly_theme_day public_day
        ON public_day.theme_version_id = t.published_version_id AND public_day.mission_id = a.mission_id
), resolved AS (
    SELECT l.id, CASE WHEN l.published_at <= l.started_at AND l.last_public IS NOT NULL THEN l.last_public
                      ELSE COALESCE(historic.theme_version_id, l.last_public) END AS version_id
    FROM legacy l
    LEFT JOIN LATERAL (
        SELECT (array_agg(d.theme_version_id))[1] AS theme_version_id
        FROM weekly_theme_version v
        JOIN weekly_theme_day d ON d.theme_version_id = v.id
        WHERE v.theme_id = l.theme_id AND v.created_at <= l.started_at AND d.mission_id = l.mission_id
          AND d.mission_version_id = l.mission_version_id AND d.rubric_version_id = l.rubric_version_id
        HAVING count(*) = 1
    ) historic ON true
)
UPDATE attempt a SET theme_version_id = r.version_id
FROM resolved r WHERE a.id = r.id AND r.version_id IS NOT NULL;
