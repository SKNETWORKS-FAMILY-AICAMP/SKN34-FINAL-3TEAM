package com.sagomungchi.learning.judgment.repository

import com.sagomungchi.learning.judgment.domain.CorrectionTarget
import com.sagomungchi.learning.judgment.domain.JudgmentCorrection
import org.springframework.stereotype.Repository
import java.util.UUID

/** 판정 정정 (class-diagram 4.2 CorrectionRepository). 트랜잭션은 시작하지 않음 */
@Repository
class CorrectionRepository(private val mapper: CorrectionMapper) {
    /**
     * 판정 행을 먼저 잠가(FOR UPDATE) 같은 판정의 정정 요청을 차례로 하고, 잠근 뒤 학생·처리 상태·지금 보이는 결과를 새로 읽음
     * (READ COMMITTED에서 다음 문장은 앞 요청이 커밋한 정정까지 봄)
     */
    fun lockTarget(judgmentId: UUID): CorrectionTarget? {
        if (mapper.lockJudgment(judgmentId) == null) return null
        return mapper.findTarget(judgmentId)
    }

    /** 키는 판정과 상관없이 하나 (ERD judgment_correction.idempotency_key UK) */
    fun findByIdempotencyKey(key: UUID): JudgmentCorrection? = mapper.findByIdempotencyKey(key)

    fun existsByReportId(reportId: UUID): Boolean = mapper.existsByReportId(reportId)

    fun insert(correction: JudgmentCorrection) {
        check(mapper.insert(correction) == 1)
    }
}
