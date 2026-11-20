-- #801 답변 생각·작성 시간 (P28, 에픽 #799, 설계 #800). 웹이 화면 안 경과 시간으로 재서 보내고 learning은 검사·저장만 한다.
-- thinking_seconds: 문제 화면(보완 답변은 되묻기 질문) 표시 → 답변 칸 첫 입력, writing_seconds: 첫 입력 → 제출. 정수 초.
-- 고르기 방식·보호자 받아쓰기·이어하기·이상값(0 미만, 86400초 초과)은 learning이 NULL로 저장한다(api-spec 3.1).
-- 기존 행은 NULL 그대로 두고 기본값·인덱스는 두지 않는다(조회는 답변 행과 함께).

ALTER TABLE answer
    ADD COLUMN thinking_seconds INT,
    ADD COLUMN writing_seconds INT,
    ADD CONSTRAINT ck_answer_thinking_seconds CHECK (thinking_seconds >= 0),
    ADD CONSTRAINT ck_answer_writing_seconds CHECK (writing_seconds >= 0),
    ADD CONSTRAINT ck_answer_time_pair CHECK ((thinking_seconds IS NULL) = (writing_seconds IS NULL));
