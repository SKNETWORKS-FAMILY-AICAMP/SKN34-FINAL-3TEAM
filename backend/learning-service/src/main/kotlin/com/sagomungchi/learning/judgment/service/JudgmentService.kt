package com.sagomungchi.learning.judgment.service

import com.sagomungchi.learning.judgment.domain.TimelineAnswer
import com.sagomungchi.learning.judgment.repository.JudgmentRepository
import org.springframework.stereotype.Service
import java.time.Instant
import java.util.UUID

/** 판정. 답변 제출 시 PENDING 생성과 시도 타임라인까지(#24). 판정 실행·결과 저장은 피드백(#25) */
@Service
class JudgmentService(
    private val judgmentRepository: JudgmentRepository,
) {
    /** class-diagram 4.1 createPending. 호출한 쪽 트랜잭션 안에서 답변과 함께 저장 */
    fun createPending(answerId: UUID, rubricVersionId: UUID, now: Instant) =
        judgmentRepository.insertPending(answerId, rubricVersionId, now)

    /** 보완 답변이 연결할 수 있는 되묻기: 시도의 가장 최근 되묻기가 아직 답을 받지 않았을 때만 */
    fun unansweredLatestFollowupId(attemptId: UUID): UUID? = judgmentRepository.findUnansweredLatestFollowupId(attemptId)

    /** 시도의 답변과 판정 처리 상태, 버전 순 */
    fun timeline(attemptId: UUID): List<TimelineAnswer> = judgmentRepository.findTimeline(attemptId)
}
