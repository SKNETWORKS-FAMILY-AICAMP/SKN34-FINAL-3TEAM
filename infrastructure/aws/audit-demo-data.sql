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
\endif
COMMIT;
