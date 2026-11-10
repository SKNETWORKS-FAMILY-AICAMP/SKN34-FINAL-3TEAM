-- #438 학년별 주간 테마 최종 (V14 준비 버전 다음, ERD 8장). 모든 테마 행에 grade가 채워졌는지 확인한 뒤
-- NOT NULL·CHECK를 걸고 학년군 칸(grade_band)과 그 CHECK를 지운다
LOCK TABLE weekly_theme IN ACCESS EXCLUSIVE MODE;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM weekly_theme WHERE grade IS NULL) THEN
        RAISE EXCEPTION 'weekly_theme.grade가 비어 있는 행이 있음 (V14 이후 학년군 테마가 다시 들어왔는지 확인)';
    END IF;
END $$;

ALTER TABLE weekly_theme ALTER COLUMN grade SET NOT NULL;
ALTER TABLE weekly_theme
    ADD CONSTRAINT ck_weekly_theme_grade CHECK (grade IN ('G3', 'G4', 'G5', 'G6'));

ALTER TABLE weekly_theme DROP CONSTRAINT ck_weekly_theme_grade_band;
ALTER TABLE weekly_theme DROP COLUMN grade_band;
