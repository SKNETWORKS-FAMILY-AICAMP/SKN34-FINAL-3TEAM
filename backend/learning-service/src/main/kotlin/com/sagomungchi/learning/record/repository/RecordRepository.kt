package com.sagomungchi.learning.record.repository

import com.sagomungchi.learning.record.domain.Period
import org.springframework.stereotype.Repository
import java.util.UUID

/**
 * 대시보드·에이전트 도구·리포트용 조회 (class-diagram 4.3). 여러 기능 테이블을 읽는 조회 전용 매퍼, 쓰기 없음.
 * 메모·초안은 읽지 않음 (P05)
 */
@Repository
class RecordRepository(private val mapper: RecordMapper) {
    /** 집계 대상 시도 (P08), 최근 답변 순 */
    fun findEligible(studentId: UUID, period: Period): List<EligibleAttempt> =
        mapper.findEligible(studentId, period.start(), period.endExclusive())

    /** 집계 대상 시도 중 보완 답변이 있는 시도의 최초·마지막 답변 (P08 "최초 vs 마지막") */
    fun findAnswerPairs(studentId: UUID, period: Period): List<AnswerPair> =
        mapper.findAnswerPairs(studentId, period.start(), period.endExclusive())

    /** 이 학생의 시도이고 처리 실패만 있는 시도가 아님 (기간과 무관한 기록 상세용) */
    fun isRecorded(studentId: UUID, attemptId: UUID): Boolean = mapper.isRecorded(studentId, attemptId)

    fun findEvidence(answerIds: List<UUID>): List<EvidenceRow> = mapper.findEvidence(answerIds)

    fun stats(period: Period): StatsRow = mapper.stats(period.start(), period.endExclusive())
}
