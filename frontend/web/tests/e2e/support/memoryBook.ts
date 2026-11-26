import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/**
 * 추억 그림책 실서버 확인(docs/proposals/memory-book.md 13.2) 준비. 데이터는 모두 합성.
 * 지난 회차는 다섯 문제를 실제로 풀어 만들 수 없으므로(그 주가 지나야 액자가 생김) learning_db에 직접 넣는다.
 */
const container = process.env.E2E_POSTGRES_CONTAINER ?? 'sagomungchi-e2e-postgres-1'
const minio = process.env.E2E_MINIO_URL ?? 'http://127.0.0.1:9000'
const bucket = process.env.E2E_MISSIONS_BUCKET ?? 'sagomungchi-local-missions'

/** 셸에 값이 없으면 스택을 띄운 합성 값 파일(infrastructure/stubs/e2e.env)에서 읽는다(CI는 이 파일로 스택을 띄움) */
function stubEnv(name: string) {
  const file = readFileSync(resolve(import.meta.dirname, '../../../../../infrastructure/stubs/e2e.env'), 'utf8')
  const line = file.split('\n').map((l) => l.trimEnd()).find((l) => l.startsWith(`${name}=`))
  if (!line) throw new Error(`e2e.env에 ${name}이 없습니다`)
  return line.slice(name.length + 1)
}

export function psql(database: string, sql: string) {
  return execFileSync('docker', ['exec', '-i', container, 'sh', '-c', `psql -v ON_ERROR_STOP=1 -qAt -U "$POSTGRES_USER" -d ${database}`],
    { input: sql, encoding: 'utf8' }).trim()
}

export const studentIdOf = (nickname: string) =>
  psql('core_db', `SELECT id FROM student WHERE nickname = '${nickname.replaceAll("'", "''")}'`)

/** 원문 공개·프리미엄 구독(지금 기간)·그림책 하루 한도. 학부모 = 그 학생의 보호자 */
export function premiumShared(studentId: string, shared = true) {
  psql('core_db', `
UPDATE student SET parent_sharing_enabled = ${shared} WHERE id = '${studentId}';
UPDATE product SET limits = limits || '{"dailyMemoryBooks":3}'::jsonb;
INSERT INTO subscription (id, parent_user_id, student_id, product_id, status, period_start, period_end, auto_renew, created_at, updated_at, product_snapshot, revision)
SELECT gen_random_uuid(), g.parent_user_id, g.student_id, p.id, 'ACTIVE', current_date - 1, current_date + 29, false, now(), now(),
  jsonb_build_object('id', p.id, 'code', p.code, 'name', p.name, 'price', p.price, 'billingCycle', p.billing_cycle, 'childLimit', p.child_limit,
    'features', p.features || '{"memoryBook":true}'::jsonb, 'limits', p.limits, 'active', true), 0
FROM guardianship g JOIN product p ON p.code = 'E2E-PLUS'
WHERE g.student_id = '${studentId}' AND g.status = 'LINKED'
  AND NOT EXISTS (SELECT 1 FROM subscription s WHERE s.student_id = g.student_id AND s.status = 'ACTIVE');`)
}

export const setSharing = (studentId: string, shared: boolean) =>
  psql('core_db', `UPDATE student SET parent_sharing_enabled = ${shared} WHERE id = '${studentId}'`)

/** public/demo 그림을 MinIO missions 버킷의 테마 그림 키로 올린다(ai 테마 초안이 올리는 키 모양) */
export function uploadSceneImages(prefix: string) {
  const root = resolve(import.meta.dirname, '../../../public/demo')
  const files: Record<string, string> = {
    INTRO: 'story/intro.jpg', OUTRO: 'story/outro.jpg',
    MON: 'album/past-forest.jpg', TUE: 'album/past-map.jpg', WED: 'album/past-post.jpg', THU: 'atlas.jpg', FRI: 'story/intro.jpg',
  }
  const user = process.env.MINIO_ROOT_USER ?? stubEnv('MINIO_ROOT_USER')
  const password = process.env.MINIO_ROOT_PASSWORD ?? stubEnv('MINIO_ROOT_PASSWORD')
  for (const [scene, file] of Object.entries(files)) {
    execFileSync('curl', ['-sS', '--fail', '--aws-sigv4', 'aws:amz:ap-northeast-2:s3', '--user', `${user}:${password}`,
      '-H', 'Content-Type: image/jpeg', '-T', resolve(root, file), `${minio}/${bucket}/theme-drafts/${prefix}/${scene}`])
  }
}

/**
 * [weeksAgo]주 전(기본 3, 차 있으면 더 앞) 초3 회차: 게시 테마(데모 미션 1~5) + 다섯 문제 학습 완료 + 월요일 처음 답·되묻기·보완 답·돌아보기 + 정답 맞힘(엔딩) + 기념 액자.
 * 그림 키는 [prefix] 아래. 돌려주는 값: 테마 ID와 주
 */
export function pastRound(studentId: string, prefix: string, title: string, weeksAgo = 3) {
  const sql = `
WITH week AS (
  -- 다시 실행해도 겹치지 않게 [weeksAgo]주 전부터 거꾸로 초3 테마가 없는 첫 주
  SELECT date_trunc('week', now() AT TIME ZONE 'Asia/Seoul')::date - 7 * k AS start
  FROM generate_series(${weeksAgo}, ${weeksAgo} + 57) AS k
  WHERE NOT EXISTS (SELECT 1 FROM weekly_theme t WHERE t.grade = 'G3'
    AND t.week_start = date_trunc('week', now() AT TIME ZONE 'Asia/Seoul')::date - 7 * k)
  ORDER BY k LIMIT 1
), ids AS (
  SELECT gen_random_uuid() AS theme, gen_random_uuid() AS version, (SELECT start FROM week) AS start
), theme AS (
  INSERT INTO weekly_theme (id, grade, week_start, status, current_version_id, published_version_id, review_version_id, created_by, published_at, created_at, updated_at)
  SELECT theme, 'G3', start, 'PUBLISHED', version, version, version, gen_random_uuid(), now(), now(), now() FROM ids
  RETURNING id
), version AS (
  INSERT INTO weekly_theme_version (id, theme_id, version, title, intro, created_by, created_at, big_question, outro, answer, intro_image_uri, outro_image_uri)
  SELECT version, theme, 1, '${title}', '바닷가 마을의 등대 불빛이 어느 밤 꺼졌어요. 왜 꺼졌는지 한 주 동안 단서를 모아요.', gen_random_uuid(), now(),
    '등대 불빛은 왜 꺼졌을까?', '등대지기는 문에 새 빗장을 달았어요. 그날 밤부터 불빛은 다시 바다를 비췄어요.', '바람',
    'theme-drafts/${prefix}/INTRO', 'theme-drafts/${prefix}/OUTRO'
  FROM ids
  RETURNING id
)
INSERT INTO weekly_theme_day (theme_version_id, day_of_week, mission_id, dialogue)
SELECT ids.version, d.n, ('d1000000-0000-4000-8000-00000000000' || d.n)::uuid,
  CASE WHEN d.n = 1 THEN '[{"speaker":"등대지기","text":"어젯밤엔 바람이 유난히 셌단다."}]'::jsonb END
FROM ids, generate_series(1, 5) AS d(n)
RETURNING (SELECT theme FROM ids)::text || ' ' || (SELECT start FROM ids)::text;`
  const out = psql('learning_db', sql).split('\n')[0]
  const [themeId, weekStart] = out.split(' ')
  const scenes = ['MON', 'TUE', 'WED', 'THU', 'FRI']
  psql('learning_db', `
${scenes.map((scene, i) => `UPDATE mission_version SET scene_uri = 'theme-drafts/${prefix}/${scene}'
  WHERE id = (SELECT published_version_id FROM mission WHERE id = 'd1000000-0000-4000-8000-00000000000${i + 1}');`).join('\n')}
WITH done AS (
  INSERT INTO attempt (id, student_id, mission_id, mission_version_id, rubric_version_id, grade, status, started_at, finished_at, completed_at,
    updated_at, context, theme_id, theme_week_start, theme_version_id)
  SELECT gen_random_uuid(), '${studentId}', m.id, m.published_version_id, m.published_rubric_version_id, 3, 'COMPLETED',
    ts - interval '30 minutes', ts, ts, ts, 'THEME_DAY', '${themeId}', '${weekStart}',
    (SELECT published_version_id FROM weekly_theme WHERE id = '${themeId}')
  FROM generate_series(1, 5) AS d(n)
  JOIN mission m ON m.id = ('d1000000-0000-4000-8000-00000000000' || d.n)::uuid
  CROSS JOIN LATERAL (SELECT ('${weekStart}'::date + (d.n - 1))::timestamp AT TIME ZONE 'Asia/Seoul' + interval '17 hours' AS ts) t
  RETURNING id, mission_id, completed_at, rubric_version_id
), first AS (
  INSERT INTO answer (id, attempt_id, version, input_type, content, plain_text, dictated_by_guardian, idempotency_key, submitted_at)
  SELECT gen_random_uuid(), id, 1, 'NARRATIVE', '{}'::jsonb,
    CASE mission_id WHEN 'd1000000-0000-4000-8000-000000000001'::uuid THEN '바람이 먼저 불었고 그다음 문이 열렸어요.'
      ELSE '내 생각에는 <중요한> 까닭이 있어요. ' || substr(mission_id::text, 36) END, false, gen_random_uuid(), completed_at - interval '20 minutes'
  FROM done RETURNING id, attempt_id
), judged AS (
  INSERT INTO judgment (id, answer_id, process_status, result, method, rubric_version_id, retry_count, created_at)
  -- 같은 문장에서 넣은 행은 표로 다시 읽히지 않아 CTE 결과(done)로 잇는다
  SELECT gen_random_uuid(), f.id, 'DONE', 'RETHINK', 'LLM', d.rubric_version_id, 0, now()
  FROM first f JOIN done d ON d.id = f.attempt_id WHERE d.mission_id = 'd1000000-0000-4000-8000-000000000001'
  RETURNING id, answer_id
), asked AS (
  INSERT INTO followup (id, attempt_id, judgment_id, type, question, source, leak_check_passed, created_at)
  SELECT gen_random_uuid(), f.attempt_id, j.id, 'TELL_MORE', '불이 꺼진 건 언제였을까?', 'LLM', true, now()
  FROM judged j JOIN first f ON f.id = j.answer_id
  RETURNING id, attempt_id
), revised AS (
  INSERT INTO answer (id, attempt_id, version, followup_id, input_type, content, plain_text, dictated_by_guardian, idempotency_key, submitted_at)
  SELECT gen_random_uuid(), attempt_id, 2, id, 'NARRATIVE', '{}'::jsonb, '문이 열린 다음에 불이 꺼졌어요. 바람이 들어와서요.', false, gen_random_uuid(), now()
  FROM asked RETURNING attempt_id
), reflected AS (
  INSERT INTO reflection (id, attempt_id, difficulty, changed_text, created_at)
  SELECT gen_random_uuid(), attempt_id, 'NORMAL', '순서를 다시 보니 까닭이 보였어요.', now() FROM revised RETURNING attempt_id
), picked AS (
  INSERT INTO theme_answer_pick (student_id, week_start, theme_id, mission_id, pick, correct, picked_at)
  VALUES ('${studentId}', '${weekStart}', '${themeId}', 'd1000000-0000-4000-8000-000000000005', '바람', true,
    ('${weekStart}'::date + 4)::timestamp AT TIME ZONE 'Asia/Seoul' + interval '18 hours')
  RETURNING student_id
)
INSERT INTO theme_frame (id, student_id, theme_id, theme_week_start, theme_version_id, awarded_at, seen_at, created_at)
SELECT gen_random_uuid(), '${studentId}', '${themeId}', '${weekStart}', (SELECT published_version_id FROM weekly_theme WHERE id = '${themeId}'),
  (SELECT max(completed_at) FROM done), now(), now()
WHERE EXISTS (SELECT 1 FROM picked) AND EXISTS (SELECT 1 FROM reflected);`)
  return { themeId, weekStart }
}

/** core 그림책 같이 읽음 시각(#1025 V59, KST 날짜 YYYY-MM-DD). 없으면 빈 문자열 */
export const readTogetherOf = (studentId: string) =>
  psql('core_db', `SELECT coalesce(to_char(read_together_at AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD'), '') FROM memory_book_job WHERE student_id = '${studentId}' ORDER BY created_at DESC LIMIT 1`)

/** core 그림책 작업 상태(완료 이벤트 반영 확인) */
export const bookStatus = (studentId: string) =>
  psql('core_db', `SELECT status || ' ' || coalesce(size_bytes::text, '-') FROM memory_book_job WHERE student_id = '${studentId}' ORDER BY created_at DESC LIMIT 1`)
