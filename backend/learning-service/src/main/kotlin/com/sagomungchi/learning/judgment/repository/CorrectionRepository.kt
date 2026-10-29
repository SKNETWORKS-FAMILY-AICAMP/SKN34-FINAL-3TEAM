package com.sagomungchi.learning.judgment.repository

import com.sagomungchi.learning.judgment.domain.CorrectionTarget
import com.sagomungchi.learning.judgment.domain.JudgmentCorrection
import org.springframework.stereotype.Repository
import java.util.UUID

/** 판정 정정 (class-diagram 4.2 CorrectionRepository). 트랜잭션은 시작하지 않음 */
@Repository
class CorrectionRepository(private val mapper: CorrectionMapper) {
    /** 판정 행을 잠그고(FOR UPDATE) 학생·처리 상태·지금 보이는 결과. 같은 판정의 정정 요청은 여기서 차례로 */
    fun lockTarget(judgmentId: UUID): CorrectionTarget? = mapper.lockTarget(judgmentId)

    /** 키는 판정과 상관없이 하나 (ERD judgment_correction.idempotency_key UK) */
    fun findByIdempotencyKey(key: UUID): JudgmentCorrection? = mapper.findByIdempotencyKey(key)

    fun existsByReportId(reportId: UUID): Boolean = mapper.existsByReportId(reportId)

    fun insert(correction: JudgmentCorrection) {
        check(mapper.insert(correction) == 1)
    }
}
