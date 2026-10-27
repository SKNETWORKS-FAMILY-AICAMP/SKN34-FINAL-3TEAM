package com.sagomungchi.learning.attempt.service

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.attempt.domain.Attempt
import com.sagomungchi.learning.attempt.domain.AttemptDraft
import com.sagomungchi.learning.attempt.domain.DraftContent
import com.sagomungchi.learning.attempt.domain.HintOpened
import com.sagomungchi.learning.attempt.repository.AttemptDraftRepository
import com.sagomungchi.learning.attempt.repository.AttemptRepository
import com.sagomungchi.learning.mission.domain.MissionView
import com.sagomungchi.learning.mission.service.MissionService
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.UUID

/** created: 이번 요청으로 새로 만들었으면 true, 진행 중 시도를 돌려주면 false */
data class AttemptStart(val attempt: Attempt, val created: Boolean)

/** 시도 상세: 시도에 고정된 버전의 미션, 초안, 생각 열기 이용 여부 */
data class AttemptDetail(
    val attempt: Attempt,
    val mission: MissionView,
    val draft: AttemptDraft,
    val helped: Boolean,
)

/** 초안 버전 불일치. 최신 초안을 함께 돌려줌 (api-spec 3.6) */
class DraftConflictException(val latest: AttemptDraft) :
    BusinessException(HttpStatus.CONFLICT, "ATTEMPT_DRAFT_CONFLICT", "초안 충돌", "다른 화면에서 더 최신 초안이 저장됨")

@Service
class AttemptService(
    private val attemptRepository: AttemptRepository,
    private val draftRepository: AttemptDraftRepository,
    private val missionService: MissionService,
) {
    /**
     * 시도 시작 (state-diagram 3.2, sequence-diagram 3.1). 진행 중 시도가 있으면 미션 공개·범위와 무관하게 그 시도를 돌려줌
     * (공개 중단 뒤에도 기존 시도는 당시 버전 유지, state-diagram 3.1). 없으면 공개·범위를 확인하고 현재 버전을 고정해 만듦.
     */
    @Transactional
    fun start(studentId: UUID, missionId: UUID, grade: Int, demo: Boolean): AttemptStart {
        attemptRepository.findInProgress(studentId, missionId)?.let { return AttemptStart(it, created = false) }
        missionService.get(missionId, grade, demo)
        val now = now()
        val attempt = Attempt.start(studentId, missionId, missionService.currentVersions(missionId), grade, now)
        if (attemptRepository.insertIfNoneInProgress(attempt)) {
            draftRepository.insert(AttemptDraft.empty(attempt.id, now))
            return AttemptStart(attempt, created = true)
        }
        // 동시 요청이 먼저 만든 시도 (부분 UK 충돌)
        val existing = checkNotNull(attemptRepository.findInProgress(studentId, missionId)) { "진행 중 시도 충돌 후 조회 실패" }
        return AttemptStart(existing, created = false)
    }

    @Transactional(readOnly = true)
    fun get(attemptId: UUID): AttemptDetail {
        val attempt = requireOwned(attemptId)
        return AttemptDetail(
            attempt = attempt,
            mission = missionService.getVersion(attempt.missionVersionId),
            draft = checkNotNull(draftRepository.findByAttemptId(attempt.id)) { "시도 초안 없음" },
            helped = attemptRepository.findOpenedHintIds(attempt.id).isNotEmpty(),
        )
    }

    /** 초안 자동 저장 (FN-LRN-15·17). 저장된 버전이 ifMatch가 아니면 덮어쓰지 않고 409 + 최신 초안 */
    @Transactional
    fun saveDraft(attemptId: UUID, ifMatch: Int, content: DraftContent): AttemptDraft {
        requireOwned(attemptId).requireOpen()
        val next = AttemptDraft(attemptId, ifMatch + 1, content, now())
        if (draftRepository.updateIfVersion(next, ifMatch)) return next
        throw DraftConflictException(checkNotNull(draftRepository.findByAttemptId(attemptId)) { "시도 초안 없음" })
    }

    /** 생각 열기 (FN-LRN-06): 열람 기록 후 질문 반환. 정답·제출용 답은 질문에 없음 */
    @Transactional
    fun openHint(attemptId: UUID): HintOpened {
        val attempt = requireOwned(attemptId).also { it.requireOpen() }
        val questions = missionService.hintQuestions(attempt.rubricVersionId)
        if (questions.isEmpty()) throw BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "생각 열기 질문 없음")
        val opened = HintOpened.next(questions, attemptRepository.findOpenedHintIds(attempt.id))
        attemptRepository.recordHintOpened(attempt.id, opened.question.id, now())
        return opened
    }

    /** PostgreSQL timestamptz는 마이크로초까지 저장하므로 응답과 저장값이 같도록 맞춤 */
    private fun now(): Instant = Instant.now().truncatedTo(ChronoUnit.MICROS)

    /** 없으면 404, 다른 학생의 시도면 403 (api-spec 1.2 학생은 본인 기록만) */
    private fun requireOwned(attemptId: UUID): Attempt {
        val attempt = attemptRepository.findById(attemptId)
            ?: throw BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "학습 시도 없음")
        UserContextHolder.current().requireStudent(attempt.studentId.toString())
        return attempt
    }
}
