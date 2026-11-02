-- #79 판정 규칙 확정 (erd 4.1, FN-LRN-04·FN-JDG-02). 기존 행은 NULL로 두고 기존 마이그레이션은 수정하지 않는다.
-- categories: 분류 문항의 그룹 [{id, label}], answer_key.assignments의 categoryId가 가리킴
-- answer_unit: 수학 최종 답 단위. 단위는 비교하지 않고 답 칸 뒤에 고정해 보여 줌
ALTER TABLE mission_version ADD COLUMN categories jsonb;
ALTER TABLE mission_version ADD COLUMN answer_unit varchar;
