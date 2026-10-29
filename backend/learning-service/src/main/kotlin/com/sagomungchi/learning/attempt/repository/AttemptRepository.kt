package com.sagomungchi.learning.attempt.repository

import com.sagomungchi.learning.attempt.domain.Attempt
import com.sagomungchi.learning.attempt.domain.Reflection
import com.sagomungchi.learning.attempt.domain.SelfCheck
import org.springframework.stereotype.Repository
import java.time.Instant
import java.util.UUID

/** 학습 시도, 생각 열기 열람 기록, 돌아보기·자기 평가. 트랜잭션은 시작하지 않음 */
@Repository
class AttemptRepository(private val mapper: AttemptMapper) {
    /** 같은 학생·미션의 진행 중 시도가 있으면(부분 UK) 넣지 않고 false */
    fun insertIfNoneInProgress(attempt: Attempt): Boolean = mapper.insertIfNoneInProgress(attempt) == 1

    fun findInProgress(studentId: UUID, missionId: UUID): Attempt? = mapper.findInProgress(studentId, missionId)

    fun findById(id: UUID): Attempt? = mapper.findById(id)

    /** 행 잠금(SELECT … FOR UPDATE). 같은 시도의 답변 제출·마무리를 한 줄로 세움 */
    fun lockById(id: UUID): Attempt? = mapper.findByIdForUpdate(id)

    /** 마무리 기록 (엔티티 Attempt.finish 뒤) */
    fun finish(attempt: Attempt) {
        check(mapper.finish(attempt) == 1) { "마무리할 수 없는 시도" }
    }

    /** 학습 완료 기록 (엔티티 Attempt.complete 뒤) */
    fun complete(attempt: Attempt) {
        check(mapper.complete(attempt) == 1) { "완료할 수 없는 시도" }
    }

    /** 돌아보기는 시도당 하나 (UK attempt_id) */
    fun insertReflection(attemptId: UUID, reflection: Reflection, createdAt: Instant) {
        check(mapper.insertReflection(UUID.randomUUID(), attemptId, reflection, createdAt) == 1)
    }

    fun findReflection(attemptId: UUID): Reflection? = mapper.findReflection(attemptId)

    /** 자기 체크 저장. 이미 체크한 요소는 checked만 바꿈 (판정·답변은 건드리지 않음, FN-LRN-13) */
    fun saveSelfAssessments(attemptId: UUID, checks: List<SelfCheck>, now: Instant) {
        check(mapper.upsertSelfAssessments(attemptId, checks, now) == checks.size)
    }

    fun findSelfAssessments(attemptId: UUID): Map<UUID, Boolean> =
        mapper.findSelfAssessments(attemptId).associate { it.elementId to it.checked }

    fun recordHintOpened(attemptId: UUID, hintQuestionId: UUID, openedAt: Instant) {
        check(mapper.insertHintUsage(UUID.randomUUID(), attemptId, hintQuestionId, openedAt) == 1)
    }

    fun findOpenedHintIds(attemptId: UUID): Set<UUID> = mapper.findOpenedHintIds(attemptId).toSet()

    /**
     * 학생의 시도 이하 기록 전부 삭제 (#128, ERD 4.3). FK는 CASCADE 없이 NO ACTION이라 자식부터 지움.
     * 답변 → 되묻기 → 판정 → 답변이 서로 참조하므로 answer.followup_id(DEFERRABLE) 검사를 커밋 때로 미룸.
     * 호출한 쪽 트랜잭션 안에서만. 지운 시도 수
     */
    fun deleteByStudent(studentId: UUID): Int {
        mapper.deferAnswerFollowupCheck()
        mapper.deleteCorrectionsByStudent(studentId)
        mapper.deleteJudgmentElementsByStudent(studentId)
        mapper.deleteSelfAssessmentsByStudent(studentId)
        mapper.deleteReflectionsByStudent(studentId)
        mapper.deleteHintUsagesByStudent(studentId)
        mapper.deleteDraftsByStudent(studentId)
        mapper.deleteFollowupsByStudent(studentId)
        mapper.deleteJudgmentsByStudent(studentId)
        mapper.deleteAnswersByStudent(studentId)
        return mapper.deleteAttemptsByStudent(studentId)
    }
}
