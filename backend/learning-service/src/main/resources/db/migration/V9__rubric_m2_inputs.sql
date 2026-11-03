-- #69 ai 판정의 M2 교차 확인 입력 (api-spec 4.2.2). 기준표 버전과 함께 불변, 기존 행은 NULL
-- keywords: 서술 핵심어 묶음 배열 (괄호 안 대체어 포함 문자열), essay_type: 논술 글 종류
ALTER TABLE rubric_version
    ADD COLUMN keywords jsonb,
    ADD COLUMN essay_type varchar,
    ADD CONSTRAINT ck_rubric_version_essay_type
        CHECK (essay_type IN ('설명글', '글짓기', '주장', '찬성반대', '대안제시'));
