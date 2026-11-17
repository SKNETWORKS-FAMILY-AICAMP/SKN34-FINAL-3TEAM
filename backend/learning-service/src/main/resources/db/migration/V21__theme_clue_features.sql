-- #647 단서 근거(후보 특징 표)를 학생에게 보여 주기 (docs/design/erd.md 4.2.1, api-spec 2.11·4.2).
-- 버전 칸 features: ai 테마 초안의 후보 특징 표 [{name, values:[{candidate, value}]}]. 요일 칸 clue_feature: 그날 단서가 쓰는 특징 이름.
-- 사람이 쓴 테마·기존 테마는 비어 있어 둘 다 NULL 허용이고 기존 행 채움 단계가 없다. 다른 버전 칸처럼 테마 새 버전 때 함께 복사한다
ALTER TABLE weekly_theme_version ADD COLUMN features jsonb;
ALTER TABLE weekly_theme_day ADD COLUMN clue_feature varchar;
