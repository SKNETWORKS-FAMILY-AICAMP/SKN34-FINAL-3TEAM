-- #697 동행 캐릭터 12종(뭉치 친구들, P22 개정, #589). V23은 고치지 않고 이 버전에서 바꾼다.
-- 기존 5종 값은 그대로 두고 새 7종만 웹 친구 id로 더한다. 허용 목록만 넓혀 기존 행은 항상 통과한다(V46·V48 방식).
-- V23 CHECK는 열 정의 안의 이름 없는 CHECK라 PostgreSQL이 붙인 이름(student_look_companion_check, kind core_db에서 확인)을
-- 지우고, 이름 붙은 CHECK로 다시 만든다(V35·V47 ck_look_item_slot 방식).
ALTER TABLE student DROP CONSTRAINT student_look_companion_check,
 ADD CONSTRAINT ck_student_look_companion CHECK (look_companion IN
    ('mungchi', 'tori', 'mongdol', 'kongi', 'monggeul', 'snow', 'yarn', 'star', 'foam', 'paper', 'petal', 'ice'));
