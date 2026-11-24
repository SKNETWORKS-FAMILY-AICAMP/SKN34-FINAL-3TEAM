-- Run with each service's app account against the demo database, never a production database:
--   core_db (core_app), learning_db (learning_app), report_db (report_app). psql only (\gset·\if).
-- Aggregate counts only: no identifiers, names, emails, tokens or child text.
-- learning_db·report_db have no demo flag; read them together with the core_db counts (#624 demo students are is_demo).
SELECT current_database() = 'core_db' AS is_core, current_database() = 'learning_db' AS is_learning,
       current_database() = 'report_db' AS is_report,
       (date_trunc('week', (now() AT TIME ZONE 'Asia/Seoul')))::date AS this_monday \gset
BEGIN READ ONLY;
\if :is_core
SELECT 'accounts_by_demo_flag' AS check_name, role, is_demo, count(*)
FROM user_account GROUP BY role, is_demo ORDER BY role, is_demo;
SELECT 'students_by_demo_flag' AS check_name, is_demo, count(*)
FROM student GROUP BY is_demo ORDER BY is_demo;
SELECT 'payments' AS check_name, count(*) FROM payment;
SELECT 'payment_orders' AS check_name, count(*) FROM payment_order;
SELECT 'subscriptions' AS check_name, count(*) FROM subscription;
SELECT 'database_access' AS check_name, datname,
       has_database_privilege(current_user, oid, 'CONNECT') AS can_connect
FROM pg_database WHERE datname IN ('core_db','learning_db','report_db') ORDER BY datname;
-- #624 시연 학생: 학년별 프리미엄 구독·추억의 벽 슬롯·해금 가구·지난 주 리포트(학년 행마다 학생 수 기준 합계)
SELECT 'demo624_students' AS check_name, s.grade, count(*) AS students,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM subscription x WHERE x.student_id = s.id AND x.status = 'ACTIVE')) AS premium,
       count(*) FILTER (WHERE (SELECT count(*) FROM room_frame_slot r WHERE r.student_id = s.id) >= 2) AS wall_ge2,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM student_look_unlock u JOIN look_item i ON i.code = u.item_key
                                      WHERE u.student_id = s.id AND i.slot IN ('DESK','WALL','WARDROBE'))) AS furniture_unlocked,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM report_job j WHERE j.student_id = s.id AND j.period_type = 'WEEKLY'
                                      AND j.period_from = :'this_monday'::date - 7 AND j.status = 'COMPLETED')) AS last_week_report,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM report_job j WHERE j.student_id = s.id AND j.period_type = 'DAILY'
                                      AND j.period_from >= :'this_monday'::date - 7 AND j.status = 'COMPLETED')) AS daily_report
FROM student s WHERE s.is_demo GROUP BY s.grade ORDER BY s.grade;
-- #808 더미 가족(dm854p 학부모 자녀, infra 9.7.6). 기간은 W1 2026-11-09 ~ 시연 전날 2026-12-06으로 고정.
-- app 계정은 임시 테이블을 만들 수 없어 대상 조건을 쿼리마다 반복한다.
SELECT 'dummy854_students' AS check_name, s.grade, count(*) AS students, count(*) FILTER (WHERE s.is_demo) AS demo_flag,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM subscription x WHERE x.student_id = s.id AND x.status = 'ACTIVE'
                                      AND x.product_snapshot->>'demoAccount' = '854')) AS premium_854
FROM student s JOIN guardianship g ON g.student_id = s.id JOIN user_account u ON u.id = g.parent_user_id
WHERE u.login_id LIKE 'dm854p%' GROUP BY s.grade ORDER BY s.grade;
SELECT 'dummy854_subscriptions' AS check_name, status, count(*) FROM subscription
WHERE product_snapshot->>'demoAccount' = '854' GROUP BY status ORDER BY status;
SELECT 'dummy854_report_jobs' AS check_name, j.period_type, j.period_from, j.status, count(*) AS jobs
FROM report_job j JOIN guardianship g ON g.student_id = j.student_id JOIN user_account u ON u.id = g.parent_user_id
WHERE u.login_id LIKE 'dm854p%' AND j.period_from BETWEEN DATE '2026-11-09' AND DATE '2026-12-06'
GROUP BY j.period_type, j.period_from, j.status ORDER BY j.period_type, j.period_from, j.status;
SELECT 'dummy854_error_reports' AS check_name, r.target_type, r.category, r.status, count(*) AS reports
FROM error_report r
WHERE r.reporter_user_id IN (SELECT id FROM user_account WHERE login_id LIKE 'dm854p%')
   OR r.student_id IN (SELECT g.student_id FROM guardianship g JOIN user_account u ON u.id = g.parent_user_id
                       WHERE u.login_id LIKE 'dm854p%')
GROUP BY r.target_type, r.category, r.status ORDER BY r.target_type, r.category, r.status;
SELECT 'dummy854_inquiries' AS check_name, i.requester_role, i.status, count(*) AS inquiries
FROM inquiry i
WHERE i.user_id IN (SELECT id FROM user_account WHERE login_id LIKE 'dm854p%')
   OR i.student_id IN (SELECT g.student_id FROM guardianship g JOIN user_account u ON u.id = g.parent_user_id
                       WHERE u.login_id LIKE 'dm854p%')
GROUP BY i.requester_role, i.status ORDER BY i.requester_role, i.status;
SELECT 'dummy854_conversations' AS check_name, count(*) AS conversations, count(DISTINCT c.parent_user_id) AS parents
FROM conversation c JOIN user_account u ON u.id = c.parent_user_id WHERE u.login_id LIKE 'dm854p%';
SELECT 'dummy854_active_notices' AS check_name, n.kind, count(*) AS notices FROM notice n
WHERE n.ended_at IS NULL AND n.visible_from <= now() AND (n.visible_to IS NULL OR n.visible_to > now())
GROUP BY n.kind ORDER BY n.kind;
-- #811 NFR-QA-03·NFR-OPS-01: 결제는 시연 표시 학생 것뿐이어야 한다(not_demo 행 0건). payment에는 샌드박스 표시 칸이 없어
-- 테스트 거래 여부는 이 집계와 함께 결제 키가 test_ 키인지(prod README 결제 Secret)로 판단한다.
SELECT 'dummy854_payments_by_demo_flag' AS check_name, CASE WHEN s.is_demo THEN 'demo' ELSE 'not_demo' END AS student_flag,
       p.status, count(*) AS payments, coalesce(sum(p.amount), 0) AS amount
FROM payment p JOIN payment_order o ON o.id = p.order_id JOIN student s ON s.id = o.student_id
GROUP BY 2, p.status ORDER BY 2, p.status;
\elif :is_learning
-- #624: 학생별(식별값 없이) 진행 주 이전 액자 수·전시 가능 회차, 검색 문서 상태, 지난 주 M2 점수 답변 수
WITH per_student AS (
    SELECT f.student_id, count(*) AS frames
    FROM theme_frame f WHERE f.theme_week_start < :'this_monday'::date GROUP BY f.student_id)
SELECT 'demo624_frames_per_student' AS check_name, frames, count(*) AS students
FROM per_student GROUP BY frames ORDER BY frames;
SELECT 'demo624_memory_docs' AS check_name, status, count(*) AS docs, count(DISTINCT student_id) AS students
FROM memory_search_doc WHERE theme_week_start < :'this_monday'::date GROUP BY status ORDER BY status;
SELECT 'demo624_last_week_m2_answers' AS check_name, count(DISTINCT a.student_id) AS students, count(*) AS answers
FROM attempt a JOIN answer an ON an.attempt_id = a.id JOIN judgment j ON j.answer_id = an.id
WHERE a.theme_week_start = :'this_monday'::date - 7 AND jsonb_typeof(j.model_scores->'m2') = 'object';
-- #668: M2 교차 확인을 켠 뒤 지난 3주 판정 결과·보류 사유(MODEL_DISAGREEMENT는 M2·LLM 불일치)와 M2 입력이 있는 공개 기준표 수
SELECT 'demo668_recent_judgments' AS check_name, j.result, j.held_reason,
       count(*) FILTER (WHERE jsonb_typeof(j.model_scores->'m2') = 'object') AS with_m2, count(*) AS judgments
FROM attempt a JOIN answer an ON an.attempt_id = a.id JOIN judgment j ON j.answer_id = an.id
WHERE a.started_at >= (:'this_monday'::date - 21) AND j.process_status = 'DONE'
GROUP BY j.result, j.held_reason ORDER BY j.result, j.held_reason;
SELECT 'demo668_published_m2_rubrics' AS check_name, v.input_type, v.grade_min, count(*) AS missions
FROM mission m JOIN mission_version v ON v.id = m.published_version_id JOIN rubric_version r ON r.id = m.published_rubric_version_id
WHERE m.status = 'PUBLISHED' AND v.input_type IN ('NARRATIVE', 'ESSAY')
  AND ((v.input_type = 'NARRATIVE' AND jsonb_array_length(coalesce(r.keywords, '[]'::jsonb)) > 0) OR r.essay_type IS NOT NULL)
GROUP BY v.input_type, v.grade_min ORDER BY v.input_type, v.grade_min;
-- #808: W1~W4 주별 "완료한 테마 문제 수별 학생 수"(무리 표 infra 9.7.6.2와 대조: 꾸준 5·5·5·5, 보통 5·4·3·4,
-- 들쭉 5·0·4·2, 늦게 0·0·5·5, 시연 학생 W2~W4 5). learning에는 더미 표시가 없어 그 주에 푼 모든 학생이 들어간다
WITH per_student AS (
    SELECT a.theme_week_start AS week, a.student_id, count(*) FILTER (WHERE a.status = 'COMPLETED') AS completed
    FROM attempt a WHERE a.context = 'THEME_DAY' AND a.theme_week_start BETWEEN DATE '2026-11-09' AND DATE '2026-11-30'
    GROUP BY a.theme_week_start, a.student_id)
SELECT 'dummy854_weekly_completion' AS check_name, week, completed, count(*) AS students
FROM per_student GROUP BY week, completed ORDER BY week, completed;
SELECT 'dummy854_frames_by_week' AS check_name, theme_week_start AS week, count(*) AS frames
FROM theme_frame WHERE theme_week_start BETWEEN DATE '2026-11-09' AND DATE '2026-11-30'
GROUP BY theme_week_start ORDER BY theme_week_start;
SELECT 'dummy854_community_posts' AS check_name, a.theme_week_start AS week, p.status, count(*) AS posts,
       count(DISTINCT p.student_id) AS students,
       (SELECT count(*) FROM community_reaction r JOIN community_post q ON q.id = r.post_id JOIN attempt b ON b.id = q.attempt_id
        WHERE b.theme_week_start = a.theme_week_start AND q.status = p.status) AS reactions
FROM community_post p JOIN attempt a ON a.id = p.attempt_id
WHERE a.theme_week_start BETWEEN DATE '2026-11-09' AND DATE '2026-11-30'
GROUP BY a.theme_week_start, p.status ORDER BY a.theme_week_start, p.status;
SELECT 'dummy854_community_visible' AS check_name, visible, count(*) AS students
FROM community_visibility GROUP BY visible ORDER BY visible;
\elif :is_report
-- #624: 지난 주 주간 리포트의 설명 카드(FN-RPT-09, 검사 통과분)와 일일 리포트
SELECT 'demo624_last_week_reports' AS check_name, w.status, count(*) AS reports,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM report_item i WHERE i.report_id = w.id
                                      AND i.item_type = 'EXPLANATION' AND i.verified)) AS with_explanations
FROM weekly_report w WHERE w.period_type = 'WEEKLY' AND w.period_from = :'this_monday'::date - 7
GROUP BY w.status ORDER BY w.status;
SELECT 'demo624_recent_daily_reports' AS check_name, w.status, count(*) AS reports
FROM weekly_report w WHERE w.period_type = 'DAILY' AND w.period_from >= :'this_monday'::date - 7
GROUP BY w.status ORDER BY w.status;
-- #808: W1~W4 주간 리포트(주별)와 일일 리포트(W1~W3은 토·일만, W4는 매일) 상태. report에는 더미 표시가 없다
SELECT 'dummy854_reports' AS check_name, w.period_type,
       CASE WHEN w.period_type = 'WEEKLY' THEN w.period_from ELSE date_trunc('week', w.period_from)::date END AS week,
       w.status, count(*) AS reports
FROM weekly_report w WHERE w.period_from BETWEEN DATE '2026-11-09' AND DATE '2026-12-06'
GROUP BY 2, 3, w.status ORDER BY 2, 3, w.status;
\endif
COMMIT;
