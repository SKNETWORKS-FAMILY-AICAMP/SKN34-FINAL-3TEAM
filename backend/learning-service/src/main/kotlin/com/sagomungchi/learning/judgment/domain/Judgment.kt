package com.sagomungchi.learning.judgment.domain

import com.sagomungchi.learning._common.exception.BusinessException
import org.springframework.http.HttpStatus
import java.time.Duration
import java.time.Instant
import java.util.UUID

/**
 * 판정 (ERD 4.2 judgment, class-diagram 4.2). 처리 상태 전이는 이 엔티티가 허용 여부를 판단하고 (state-diagram 1.3),
 * 저장은 JudgmentRepository가 조건부 UPDATE로 해 동시 요청 사이에서도 한 요청만 바뀜 (state-diagram 3.3)
 */
class Judgment(
    val id: UUID,
    val answerId: UUID,
    status: ProcessStatus,
    leaseUntil: Instant?,
    retryCount: Int,
) {
    var status: ProcessStatus = status
        private set
    var leaseUntil: Instant? = leaseUntil
        private set
    var retryCount: Int = retryCount
        private set
    var result: JudgmentResult? = null
        private set
    var heldReason: String? = null
        private set
    var elements: List<JudgmentElement> = emptyList()
        private set
    var by: JudgedBy? = null
        private set
    var failureCode: String? = null
        private set

    /** PENDING·FAILED·리스 만료 RUNNING이면 RUNNING으로 바꾸고 리스를 잡음 (state-diagram 3.3) */
    fun acquire(now: Instant, lease: Duration): Boolean {
        val acquirable = status == ProcessStatus.PENDING || status == ProcessStatus.FAILED ||
            (status == ProcessStatus.RUNNING && isLeaseExpired(now))
        if (acquirable) {
            status = ProcessStatus.RUNNING
            leaseUntil = now.plus(lease)
        }
        return acquirable
    }

    fun isLeaseExpired(now: Instant): Boolean = leaseUntil?.isBefore(now) ?: true

    /** 판정 완료 (CORRECT·PARTIAL·RETHINK). 보류는 hold */
    fun done(result: JudgmentResult, elements: List<JudgmentElement>, by: JudgedBy) {
        require(result != JudgmentResult.HELD) { "보류는 hold" }
        finish(result, null, elements, by)
    }

    /** 판정 보류: 정상 처리 결과(DONE)이고 실패(FAILED)와 다름. 보류를 낮은 수준으로 기록하지 않아 요소 없음 (FN-JDG-04) */
    fun hold(reason: String, by: JudgedBy) = finish(JudgmentResult.HELD, reason, emptyList(), by)

    /** ai·LLM 실패·타임아웃. 답변은 그대로, 다시 요청하면 처음부터 (FN-JDG-10) */
    fun fail(code: String) {
        requireRunning()
        status = ProcessStatus.FAILED
        failureCode = code
        retryCount += 1
    }

    private fun finish(result: JudgmentResult, heldReason: String?, elements: List<JudgmentElement>, by: JudgedBy) {
        requireRunning()
        status = ProcessStatus.DONE
        this.result = result
        this.heldReason = heldReason
        this.elements = elements
        this.by = by
        failureCode = null
    }

    /** 전이 검사: 처리 중(RUNNING)인 판정만 끝내거나 실패로 기록 (state-diagram 1.3 불허 시 409) */
    private fun requireRunning() {
        if (status != ProcessStatus.RUNNING) {
            throw BusinessException(HttpStatus.CONFLICT, "JUDGMENT_STATE_CONFLICT", "판정 상태 충돌", "처리 중인 판정이 아님: $status")
        }
    }

    companion object {
        /** [P12] 리스 90초: core→learning 피드백 80초보다 길게 (state-diagram 3.3) */
        val LEASE: Duration = Duration.ofSeconds(90)
    }
}

/** 요소별 판정. 근거가 확인되지 않은(verified=false) 요소는 충족 불가 (class-diagram 4.2, ERD CHECK) */
data class JudgmentElement(
    val rubricElementId: UUID,
    val quote: String?,
    val verified: Boolean,
    val sourceType: ElementSource?,
    val satisfied: Boolean = false,
) {
    fun satisfy(): JudgmentElement {
        require(verified) { "근거가 확인되지 않은 요소는 충족 표시 불가" }
        return copy(satisfied = true)
    }
}
