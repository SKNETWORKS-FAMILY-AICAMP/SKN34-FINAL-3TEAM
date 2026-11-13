-- 리텐션 지표 2단계: learning_db (#628, NFR-OPS-06, 결정 기록 retention-expansion.md 3.6)
-- 읽기 전용. learning 앱 계정으로 learning_db에 접속해 1단계(core.sql) 출력 JSON을 -v core로 받아 6개 지표를 낸다.
--   psql -X -d learning_db -v core="$(cat core-result.json)" -f scripts/retention_metrics/learning.sql
-- 기간·기준일·대상은 1단계 JSON 값을 그대로 쓴다(두 DB가 같은 조건). DB 간 직접 조인은 없다.
\set ON_ERROR_STOP on
\set QUIET on
\if :{?core}
\else
  \warn 'learning.sql: -v core="<core.sql 출력 JSON>" 이 필요합니다'
  \q
\endif

BEGIN TRANSACTION READ ONLY;

-- 1) 집계 조건: 결과와 함께 기록할 기간·기준일·대상
WITH c AS (SELECT :'core'::jsonb AS j)
SELECT j->'params'->>'from' AS from_inclusive,
       j->'params'->>'to' AS to_exclusive,
       j->'params'->>'as_of' AS as_of,
       ((j->'params'->>'as_of')::date - (extract(isodow FROM (j->'params'->>'as_of')::date)::int - 1)) AS current_week,
       (j->'params'->>'include_demo')::boolean AS include_demo,
       (j->'students'->>'target')::int AS target_students,
       (j->'students'->>'excluded_demo')::int AS excluded_demo,
       (j->'students'->>'excluded_listed')::int AS excluded_listed,
       (j->'students'->>'excluded_not_active')::int AS excluded_not_active
FROM c;

-- 2) 지표 6개. 회차 = (student_id, theme_id, theme_week_start)
WITH c AS (SELECT :'core'::jsonb AS j),
p AS (
    SELECT (j->'params'->>'from')::date AS from_date,
           (j->'params'->>'to')::date AS to_date,
           (j->'params'->>'as_of')::date - (extract(isodow FROM (j->'params'->>'as_of')::date)::int - 1) AS current_week,
           (j->'students'->>'target')::int AS target_students,
           j
    FROM c
),
targets AS (
    SELECT x::uuid AS student_id FROM p, jsonb_array_elements_text(p.j->'targets') AS x
),
slots AS (
    SELECT x.student_id, x.theme_id, x.theme_week_start, x.saved_at
    FROM p, jsonb_to_recordset(p.j->'slots')
         AS x(student_id uuid, theme_id uuid, theme_week_start date, saved_at timestamptz)
),
-- 대상 학생의 기간 안 회차 액자. 진행 중인 주는 앨범·추억의 벽에 보이지 않으므로 뺀다(결정 기록 9.2.1)
frames AS (
    SELECT f.student_id, f.theme_id, f.theme_week_start, f.awarded_at, f.seen_at,
           COALESCE(f.seen_at = f.awarded_at, false) AS backfilled,
           s.saved_at
    FROM theme_frame f
    JOIN targets t USING (student_id)
    CROSS JOIN p
    LEFT JOIN slots s USING (student_id, theme_id, theme_week_start)
    WHERE f.theme_week_start >= p.from_date AND f.theme_week_start < p.to_date
      AND f.theme_week_start < p.current_week
),
-- 다음 주 참여: 다음 주(theme_week_start + 7)가 기준일 전에 끝난 회차만 판정, 나머지는 보류
next_week AS (
    SELECT f.*,
           f.theme_week_start + 14 <= (SELECT current_week FROM p) AS judged,
           EXISTS (
               SELECT 1 FROM attempt a
               WHERE a.student_id = f.student_id
                 AND a.theme_week_start = f.theme_week_start + 7
                 AND a.context IN ('THEME_DAY', 'THEME_REVIEW')
           ) AS joined
    FROM frames f
),
lead_hours AS (
    SELECT extract(epoch FROM (saved_at - awarded_at)) / 3600.0 AS h
    FROM frames WHERE saved_at IS NOT NULL AND NOT backfilled
),
m AS (
    SELECT 1 AS no, '액자 전시율' AS metric,
           (SELECT count(*) FROM frames WHERE saved_at IS NOT NULL) AS numerator,
           (SELECT count(*) FROM frames) AS denominator,
           '분자 지금 추억의 벽에 걸린 액자, 분모 보유 액자(기간 안 회차·진행 주 제외)' AS basis,
           format('걸린 슬롯 중 대상 액자와 맞지 않는 행 %s', (SELECT count(*) FROM slots) - (SELECT count(*) FROM frames WHERE saved_at IS NOT NULL)) AS note
    UNION ALL
    SELECT 2, '액자 확인율',
           (SELECT count(*) FROM frames WHERE NOT backfilled AND seen_at IS NOT NULL),
           (SELECT count(*) FROM frames WHERE NOT backfilled),
           '분자 seen_at 있는 액자, 분모 보유 액자(소급분 seen_at = awarded_at 제외)',
           format('제외한 소급분 %s', (SELECT count(*) FROM frames WHERE backfilled))
    UNION ALL
    SELECT 3, '전시까지 걸린 기간(시간)',
           NULL,
           (SELECT count(*) FROM lead_hours),
           '걸린 액자의 saved_at − awarded_at(소급분 제외), 분모는 건수',
           format('중앙값 %s · 평균 %s · 최소 %s · 최대 %s',
                  (SELECT round(percentile_cont(0.5) WITHIN GROUP (ORDER BY h)::numeric, 1) FROM lead_hours),
                  (SELECT round(avg(h)::numeric, 1) FROM lead_hours),
                  (SELECT round(min(h)::numeric, 1) FROM lead_hours),
                  (SELECT round(max(h)::numeric, 1) FROM lead_hours))
    UNION ALL
    SELECT 4, '가구 스킨 해금 수',
           (SELECT (j->'furniture_unlocks'->>'rows')::bigint FROM p),
           (SELECT target_students FROM p),
           '원장 UNLOCK 중 가구 슬롯(DESK·WALL·WARDROBE) 아이템, 기간 안 해금 시각(KST), 분모 대상 학생',
           (SELECT format('해금 학생 %s · 책상 %s · 추억의 벽 %s · 옷장 %s',
                          j->'furniture_unlocks'->>'students', j->'furniture_unlocks'->>'desk',
                          j->'furniture_unlocks'->>'wall', j->'furniture_unlocks'->>'wardrobe') FROM p)
    UNION ALL
    SELECT 5, '추억 검색 이용 수',
           (SELECT (j->'memory_search'->>'rows')::bigint FROM p),
           (SELECT target_students FROM p),
           'core 추억 사용량 SEARCH 행(되돌린 장애 요청 제외), 기간 안 사용 날짜(KST), 분모 대상 학생',
           (SELECT format('이용 학생 %s · 참고 설명 %s건(학생 %s)',
                          j->'memory_search'->>'students', j->'memory_explanation'->>'rows',
                          j->'memory_explanation'->>'students') FROM p)
    UNION ALL
    SELECT 6, '액자 보유 학생의 다음 주 테마 참여',
           (SELECT count(*) FROM next_week WHERE judged AND joined),
           (SELECT count(*) FROM next_week WHERE judged),
           '분자 다음 주 테마 시도(THEME_DAY·THEME_REVIEW)가 있는 회차, 분모 다음 주가 끝난 액자 회차',
           format('판정 학생 %s · 참여 학생 %s · 다음 주가 안 끝나 보류 %s',
                  (SELECT count(DISTINCT student_id) FROM next_week WHERE judged),
                  (SELECT count(DISTINCT student_id) FROM next_week WHERE judged AND joined),
                  (SELECT count(*) FROM next_week WHERE NOT judged))
)
SELECT no, metric, numerator, denominator,
       CASE WHEN numerator IS NOT NULL AND denominator > 0 AND no IN (1, 2, 6)
            THEN round(100.0 * numerator / denominator, 1) END AS rate_percent,
       basis, note
FROM m
ORDER BY no;

COMMIT;
