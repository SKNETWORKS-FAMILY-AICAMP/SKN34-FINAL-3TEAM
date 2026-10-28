package com.sagomungchi.learning.judgment.service

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.judgment.domain.BankQuestion
import com.sagomungchi.learning.judgment.domain.FeedbackResult
import com.sagomungchi.learning.judgment.domain.FeedbackTarget
import com.sagomungchi.learning.judgment.domain.Followup
import com.sagomungchi.learning.judgment.domain.FollowupType
import com.sagomungchi.learning.judgment.domain.Judged
import com.sagomungchi.learning.judgment.domain.Judgment
import com.sagomungchi.learning.judgment.domain.JudgmentResult
import com.sagomungchi.learning.judgment.domain.JudgmentView
import com.sagomungchi.learning.judgment.domain.NextAction
import com.sagomungchi.learning.judgment.domain.ProcessStatus
import com.sagomungchi.learning.judgment.domain.TimelineAnswer
import com.sagomungchi.learning.judgment.domain.Versions
import com.sagomungchi.learning.judgment.repository.FollowupRepository
import com.sagomungchi.learning.judgment.repository.JudgmentRepository
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.UUID

/** 리스 획득 결과 (class-diagram 4.2 AcquireResult) */
sealed interface AcquireResult {
    /** 이 요청이 가져감. judgment에 획득한 리스가 있음 */
    data class Acquired(val judgment: Judgment) : AcquireResult

    /** DONE이거나 다른 요청이 유효한 리스로 처리 중 */
    data class Busy(val status: ProcessStatus) : AcquireResult
}

/**
 * 판정 (class-diagram 4.2). 메서드마다 짧은 트랜잭션, ai 호출은 FeedbackFacade가 트랜잭션 밖에서 (아키텍처 2.5).
 * 상태 전이는 Judgment 엔티티가 판단하고 Repository가 조건부 UPDATE로 저장 (#23 초안 updateIfVersion과 같은 방식)
 */
@Service
class JudgmentService(
    private val judgmentRepository: JudgmentRepository,
    private val followupRepository: FollowupRepository,
) {
    /** class-diagram 4.1 createPending. 호출한 쪽 트랜잭션 안에서 답변과 함께 저장 */
    fun createPending(answerId: UUID, rubricVersionId: UUID, now: Instant) =
        judgmentRepository.insertPending(answerId, rubricVersionId, now)

    /** 보완 답변이 연결할 수 있는 되묻기: 시도의 가장 최근 되묻기가 아직 답을 받지 않았을 때만 */
    fun unansweredLatestFollowupId(attemptId: UUID): UUID? = judgmentRepository.findUnansweredLatestFollowupId(attemptId)

    /** 시도의 답변과 판정 처리 상태, 각 답변이 답한 되묻기 질문. 버전 순 */
    fun timeline(attemptId: UUID): List<TimelineAnswer> = judgmentRepository.findTimeline(attemptId)

    fun target(answerId: UUID): FeedbackTarget =
        judgmentRepository.findTarget(answerId) ?: throw BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "답변 없음")

    /**
     * PENDING·FAILED·리스 만료 RUNNING → RUNNING (state-diagram 3.3). 엔티티가 가져갈 수 있는지 보고,
     * 조건부 UPDATE가 동시 요청 중 하나만 바꿈. 그사이 다른 요청이 가져갔으면 Busy
     */
    @Transactional
    fun acquire(answerId: UUID, now: Instant): AcquireResult {
        // 리스 값을 저장값과 같게: PostgreSQL은 마이크로초까지 저장하고, 끝낼 때 리스 값을 같은지 비교함
        val at = now.truncatedTo(ChronoUnit.MICROS)
        val judgment = checkNotNull(judgmentRepository.findByAnswerId(answerId)) { "판정 없음" }
        if (!judgment.acquire(at, Judgment.LEASE)) return AcquireResult.Busy(judgment.status)
        if (judgmentRepository.acquire(answerId, at, checkNotNull(judgment.leaseUntil)) != 1) {
            return AcquireResult.Busy(ProcessStatus.RUNNING)
        }
        return AcquireResult.Acquired(judgment)
    }

    fun followupCount(attemptId: UUID): Int = followupRepository.countByAttempt(attemptId)

    /** 같은 유형의 질문 은행 질문 (P16). 시드에 유형마다 있어야 함 */
    fun bankQuestion(attemptId: UUID, type: FollowupType): BankQuestion =
        checkNotNull(followupRepository.findBankQuestion(attemptId, type)) { "질문 은행에 $type 질문 없음" }

    /**
     * 판정·요소·되묻기·버전 저장 + DONE (class-diagram 4.2 saveResult). judgment는 acquire로 얻은 것.
     * 리스를 잃었으면(다른 요청이 다시 가져감) false, 아무것도 저장하지 않음
     */
    @Transactional
    fun saveResult(judgment: Judgment, judged: Judged, followup: Followup?): Boolean {
        val lease = checkNotNull(judgment.leaseUntil) { "리스 없는 판정" }
        if (judged.result == JudgmentResult.HELD) {
            judgment.hold(checkNotNull(judged.heldReason), judged.by)
        } else {
            judgment.done(judged.result, judged.elements, judged.by)
        }
        val now = now()
        if (!judgmentRepository.complete(judgment, lease, traceId(), now)) return false
        judgmentRepository.insertElements(judgment)
        followup?.let { followupRepository.insert(judgment.id, it, now) }
        return true
    }

    /**
     * FAILED + failure_code + retry_count + 1 (class-diagram 4.2 markFailed). 답변은 그대로 (FN-JDG-10).
     * DB에서 다시 읽은 판정으로 기록: saveResult가 엔티티를 DONE으로 바꾼 뒤 저장 중 실패해 롤백됐을 수 있음.
     * 이 요청의 리스가 아니면(다른 요청이 다시 가져감) 기록하지 않음
     */
    @Transactional
    fun markFailed(judgment: Judgment, code: String): Boolean {
        val lease = checkNotNull(judgment.leaseUntil) { "리스 없는 판정" }
        val current = judgmentRepository.findByAnswerId(judgment.answerId)
        if (current == null || current.status != ProcessStatus.RUNNING || current.leaseUntil != lease) return false
        current.fail(code)
        return judgmentRepository.fail(current, lease)
    }

    /** 한 답변의 피드백 결과 (class-diagram 4.2 result) */
    @Transactional(readOnly = true)
    fun result(answerId: UUID): FeedbackResult =
        stored(null, answerId)[answerId] ?: throw BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "답변 없음")

    /** 시도의 모든 답변 피드백 결과 (시도 상세용) */
    @Transactional(readOnly = true)
    fun results(attemptId: UUID): Map<UUID, FeedbackResult> = stored(attemptId, null)

    /**
     * 판정 행을 먼저 읽음: 문장마다 스냅샷이 달라(READ COMMITTED) 요소를 먼저 읽으면 그사이 커밋된 DONE과 섞여
     * "DONE인데 되묻기 없음"이 나갈 수 있음. saveResult가 DONE·요소·되묻기를 한 트랜잭션으로 커밋하므로 DONE을 본 뒤에는 나머지도 보임
     */
    private fun stored(attemptId: UUID?, answerId: UUID?): Map<UUID, FeedbackResult> {
        val judgments = judgmentRepository.findStored(attemptId, answerId)
        if (judgments.isEmpty()) return emptyMap()
        val elements = judgmentRepository.findStoredElements(attemptId, answerId).groupBy({ it.answerId }, { it.view() })
        val followups = followupRepository.findStored(attemptId, answerId).associate { it.answerId to it.view() }
        val openFollowupId = judgmentRepository.findUnansweredLatestFollowupId(judgments.first().attemptId)
        return judgments.associate { stored ->
            val result = stored.result
            stored.answerId to if (stored.status != ProcessStatus.DONE || result == null) {
                FeedbackResult.inProgress(stored.status)
            } else {
                val followup = followups[stored.answerId]
                FeedbackResult(
                    status = ProcessStatus.DONE,
                    judgment = JudgmentView(result, stored.trial ?: false, elements[stored.answerId].orEmpty(), stored.heldReason),
                    followup = followup,
                    nextActions = nextActions(stored.attemptOpen, followup?.followupId, openFollowupId),
                    versions = Versions(stored.missionLabel, stored.rubricLabel, stored.modelVersion, stored.promptVersion),
                )
            }
        }
    }

    /**
     * 지금 할 수 있는 행동 (api-spec 2.2, P04): 이 판정의 되묻기에 아직 답하지 않았으면 답하기·마무리,
     * 되묻기가 없으면(2회 소진·고르기 정답) 마무리만. 마무리·완료한 시도는 없음
     */
    private fun nextActions(answerable: Boolean, followupId: UUID?, openFollowupId: UUID?): List<NextAction> = when {
        !answerable -> emptyList()
        followupId != null && followupId == openFollowupId -> listOf(NextAction.ANSWER_FOLLOWUP, NextAction.FINISH)
        else -> listOf(NextAction.FINISH)
    }

    private fun traceId(): String? = UserContextHolder.currentOrNull()?.traceparent?.split("-")?.getOrNull(1)

    private fun now(): Instant = Instant.now().truncatedTo(ChronoUnit.MICROS)
}
