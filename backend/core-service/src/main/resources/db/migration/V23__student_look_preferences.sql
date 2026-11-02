-- #234 학생 화면 꾸미기(생각 지도 테마·동행 캐릭터). 학생 본인 표시 설정이며 학습 기록·리포트에 쓰지 않는다.
-- 세 열이 모두 NULL이면 저장한 적 없음(GET은 기본값과 updatedAt null). 학생 삭제 확정 시 NULL로 되돌린다.
ALTER TABLE student
    ADD COLUMN look_theme varchar(16) CHECK (look_theme IN ('lake', 'forest', 'factory', 'space', 'sea')),
    ADD COLUMN look_companion varchar(16) CHECK (look_companion IN ('mungchi', 'tori', 'mongdol', 'kongi', 'monggeul')),
    ADD COLUMN look_updated_at timestamptz,
    ADD CONSTRAINT student_look_saved_together CHECK (
        (look_theme IS NULL) = (look_companion IS NULL) AND (look_theme IS NULL) = (look_updated_at IS NULL));
