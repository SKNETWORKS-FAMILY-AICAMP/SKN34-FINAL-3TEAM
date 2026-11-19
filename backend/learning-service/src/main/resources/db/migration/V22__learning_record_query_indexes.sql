-- #775 학습 기록 목록(RecordMapper.findEligible)·최근 되묻기(JudgmentMapper.findUnansweredLatestFollowupId) 조회 인덱스.
-- 없으면 시도마다 followup·hint_usage·answer 전체를 읽는다(#384 2차 부하 시험).
-- CONCURRENTLY는 쓰지 않는다: 테이블이 수천 행이라 쓰기 잠금이 밀리초 단위이고, 한 트랜잭션으로 두어 실패 때 반쯤 만든 인덱스가 남지 않게 한다.

CREATE INDEX ix_followup_attempt_created
    ON followup (attempt_id, created_at);

CREATE INDEX ix_hint_usage_attempt_opened
    ON hint_usage (attempt_id, opened_at);

-- 대부분의 답변은 followup_id가 NULL이라 되묻기에 답한 행만 담는다. followup_id = ? 조회와 FK 검사 모두 이 인덱스를 쓴다.
CREATE INDEX ix_answer_followup
    ON answer (followup_id)
    WHERE followup_id IS NOT NULL;
