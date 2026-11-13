-- 리텐션 지표 1단계: core_db (#628, NFR-OPS-06, 결정 기록 retention-expansion.md 3.6)
-- 읽기 전용. core 앱 계정으로 core_db에 접속해 실행하고, 출력 JSON 한 줄을 2단계(learning.sql)에 -v core로 넘긴다.
--   psql -X -At -d core_db -v from=2026-11-09 -v to=2026-11-23 -f scripts/retention_metrics/core.sql > core-result.json
-- 변수
--   from, to          필수. KST 날짜 [from, to). 회차 주(theme_week_start)·해금 시각·검색 날짜에 같은 기간을 쓴다
--   as_of             선택. 기준일(KST 날짜), 기본은 실행 시점 KST 오늘. 진행 주 제외·다음 주 판정 기준
--   include_demo      선택. 1이면 시연 학생(student.is_demo)도 포함, 기본 0
--   exclude_students  선택. 표식 없는 시험 학생 ID를 쉼표로 이어 추가 제외, 기본 없음
-- 출력에는 학생 ID(UUID)만 있고 이름·닉네임·계정·답변은 없다. 결과 파일은 집계가 끝나면 지운다.
\set ON_ERROR_STOP on
\set QUIET on
\if :{?from}
\else
  \warn 'core.sql: -v from=YYYY-MM-DD 가 필요합니다'
  \q
\endif
\if :{?to}
\else
  \warn 'core.sql: -v to=YYYY-MM-DD 가 필요합니다'
  \q
\endif
\if :{?as_of}
\else
  \set as_of ''
\endif
\if :{?include_demo}
\else
  \set include_demo 0
\endif
\if :{?exclude_students}
\else
  \set exclude_students ''
\endif

BEGIN TRANSACTION READ ONLY;

WITH params AS (
    SELECT :'from'::date AS from_date,
           :'to'::date AS to_date,
           COALESCE(NULLIF(:'as_of', '')::date, (now() AT TIME ZONE 'Asia/Seoul')::date) AS as_of,
           :'include_demo'::int = 1 AS include_demo,
           COALESCE(regexp_split_to_array(NULLIF(btrim(:'exclude_students'), ''), '\s*,\s*')::uuid[], '{}') AS excluded
),
-- 집계 대상: 삭제·삭제 요청 중이 아닌 학생 중 시연 표식·추가 제외 목록에 없는 학생
classified AS (
    SELECT s.id,
           CASE
               WHEN s.status <> 'ACTIVE' THEN 'not_active'
               WHEN s.is_demo AND NOT p.include_demo THEN 'demo'
               WHEN s.id = ANY (p.excluded) THEN 'listed'
               ELSE 'target'
           END AS class
    FROM student s CROSS JOIN params p
),
targets AS (
    SELECT id AS student_id FROM classified WHERE class = 'target'
),
-- 추억의 벽에 지금 걸린 액자 중 기간 안 회차. 전시율·전시까지 걸린 기간은 learning 액자와 2단계에서 맞춘다
slots AS (
    SELECT r.student_id, r.theme_id, r.theme_week_start, r.saved_at
    FROM room_frame_slot r
    JOIN targets t USING (student_id)
    CROSS JOIN params p
    WHERE r.theme_week_start >= p.from_date AND r.theme_week_start < p.to_date
),
-- 가구 스킨 해금: 원장 UNLOCK 중 사건 키(itemKey = look_item.code)가 가구 슬롯 아이템인 행
furniture_unlocks AS (
    SELECT l.student_id, i.slot
    FROM reward_point_ledger l
    JOIN targets t USING (student_id)
    JOIN look_item i ON i.code = l.source_key
    CROSS JOIN params p
    WHERE l.event_type = 'UNLOCK'
      AND i.slot IN ('DESK', 'WALL', 'WARDROBE')
      AND (l.created_at AT TIME ZONE 'Asia/Seoul')::date >= p.from_date
      AND (l.created_at AT TIME ZONE 'Asia/Seoul')::date < p.to_date
),
-- 추억 검색·설명 사용량: 요청 1건 = 1행. 장애로 되돌린 요청은 행이 지워져 세지 않는다(결정 기록 9.1)
memory_usage AS (
    SELECT m.student_id, m.kind
    FROM memory_daily_usage m
    JOIN targets t USING (student_id)
    CROSS JOIN params p
    WHERE m.usage_date >= p.from_date AND m.usage_date < p.to_date
)
SELECT jsonb_build_object(
    'params', (SELECT jsonb_build_object(
        'from', from_date, 'to', to_date, 'as_of', as_of,
        'include_demo', include_demo, 'excluded_listed', cardinality(excluded)) FROM params),
    'students', jsonb_build_object(
        'target', (SELECT count(*) FROM classified WHERE class = 'target'),
        'excluded_demo', (SELECT count(*) FROM classified WHERE class = 'demo'),
        'excluded_listed', (SELECT count(*) FROM classified WHERE class = 'listed'),
        'excluded_not_active', (SELECT count(*) FROM classified WHERE class = 'not_active')),
    'targets', COALESCE((SELECT jsonb_agg(student_id ORDER BY student_id) FROM targets), '[]'),
    'slots', COALESCE((SELECT jsonb_agg(jsonb_build_object(
        'student_id', student_id, 'theme_id', theme_id,
        'theme_week_start', theme_week_start, 'saved_at', saved_at)
        ORDER BY student_id, theme_week_start, theme_id) FROM slots), '[]'),
    'furniture_unlocks', jsonb_build_object(
        'rows', (SELECT count(*) FROM furniture_unlocks),
        'students', (SELECT count(DISTINCT student_id) FROM furniture_unlocks),
        'desk', (SELECT count(*) FROM furniture_unlocks WHERE slot = 'DESK'),
        'wall', (SELECT count(*) FROM furniture_unlocks WHERE slot = 'WALL'),
        'wardrobe', (SELECT count(*) FROM furniture_unlocks WHERE slot = 'WARDROBE')),
    'memory_search', jsonb_build_object(
        'rows', (SELECT count(*) FROM memory_usage WHERE kind = 'SEARCH'),
        'students', (SELECT count(DISTINCT student_id) FROM memory_usage WHERE kind = 'SEARCH')),
    'memory_explanation', jsonb_build_object(
        'rows', (SELECT count(*) FROM memory_usage WHERE kind = 'EXPLANATION'),
        'students', (SELECT count(DISTINCT student_id) FROM memory_usage WHERE kind = 'EXPLANATION'))
) AS core_result;

COMMIT;
