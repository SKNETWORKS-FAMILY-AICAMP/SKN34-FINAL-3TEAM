-- 실서버 E2E 전용 learning_db 시드 (#625). demo_missions.sql 다음에 실행, 재실행해도 결과 동일
-- 주간 리포트 대표 답변 설명(FN-RPT-09)은 M2 점수가 있는 초5~6 서술 답변만 대상이고, ai는 기준표 핵심어(keywords)가
-- 있어야 M2(scoring-stub)를 부른다(ai judgment/cross_check.m2_body). 데모 시드는 핵심어가 없어(V9 기존 행 NULL)
-- E2E에서만 11번(초5·ANALYZE·NARRATIVE "따뜻해진 컵의 비밀") 기준표에 핵심어를 채운다. 저장소 데모 시드는 그대로 둔다
UPDATE rubric_version SET keywords = '["따뜻한 물(뜨거운 물)", "열(온도)", "컵"]'::jsonb
WHERE id = 'd3000000-0000-4000-8000-000000000011' AND keywords IS NULL;
