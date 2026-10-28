package com.sagomungchi.learning.attempt.service

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.attempt.domain.Attempt
import com.sagomungchi.learning.attempt.domain.AttemptDraft
import com.sagomungchi.learning.attempt.domain.Checklist
import com.sagomungchi.learning.attempt.domain.DraftContent
import com.sagomungchi.learning.attempt.domain.FinishPolicy
import com.sagomungchi.learning.attempt.domain.FinishResult
import com.sagomungchi.learning.attempt.domain.HintOpened
import com.sagomungchi.learning.attempt.domain.Reflection
import com.sagomungchi.learning.attempt.domain.RevealKind
import com.sagomungchi.learning.attempt.domain.SelfAssessmentItem
import com.sagomungchi.learning.attempt.domain.SelfCheck
import com.sagomungchi.learning.attempt.repository.AttemptDraftRepository
import com.sagomungchi.learning.attempt.repository.AttemptRepository
import com.sagomungchi.learning.judgment.domain.FeedbackResult
import com.sagomungchi.learning.judgment.domain.TimelineAnswer
import com.sagomungchi.learning.judgment.service.JudgmentService
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

/**
 * 시도 상세: 시도에 고정된 버전의 미션, 초안, 생각 열기 이용 여부, 제출 답변 타임라인과 답변별 피드백.
 * revealed(정답·예시 답·체크리스트)는 마무리한 뒤에만 (api-spec 3.8), reflection은 돌아보기를 저장한 뒤에만
 */
data class AttemptDetail(
    val attempt: Attempt,
    val mission: MissionView,
    val draft: AttemptDraft,
    val helped: Boolean,
    val answers: List<TimelineAnswer>,
    val feedbacks: Map<UUID, FeedbackResult>,
    val revealed: FinishResult?,
    val reflection: Reflection?,
)

/** 시도와 답변 타임라인(버전 순, 각 답변이 답한 되묻기 질문 포함) */
data class AttemptTimeline(val attempt: Attempt, val answers: List<TimelineAnswer>)

/** 초안 버전 불일치. 최신 초안을 함께 돌려줌 (api-spec 3.6) */
class DraftConflictException(val latest: AttemptDraft) :
    BusinessException(HttpStatus.CONFLICT, "ATTEMPT_DRAFT_CONFLICT", "초안 충돌", "다른 화면에서 더 최신 초안이 저장됨")

@Service
class AttemptService(
    private val attemptRepository: AttemptRepository,
    private val draftRepository: AttemptDraftRepository,
    private val missionService: MissionService,
    private val judgmentService: JudgmentService,
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
        val mission = missionService.getVersion(attempt.missionVersionId)
        val answers = judgmentService.timeline(attempt.id)
        val feedbacks = judgmentService.results(attempt.id)
        return AttemptDetail(
            attempt = attempt,
            mission = mission,
            draft = checkNotNull(draftRepository.findByAttemptId(attempt.id)) { "시도 초안 없음" },
            helped = attemptRepository.findOpenedHintIds(attempt.id).isNotEmpty(),
            answers = answers,
            feedbacks = feedbacks,
            revealed = attempt.finishedAt?.let { revealed(attempt, it, mission, answers, feedbacks) },
            reflection = attemptRepository.findReflection(attempt.id),
        )
    }

    /**
     * 마무리 (sequence-diagram 3.3, FN-LRN-11): 타임라인으로 FinishPolicy.canFinish를 확인하고(판정 DONE 1회 이상, 아니면 409)
     * finished_at을 기록한 뒤 정답·예시 답·체크리스트를 돌려줌. 시도 행을 잠가 같은 시도의 답변 제출·판정 저장과 차례로 처리.
     * 이미 마무리했으면 다시 기록하지 않고 같은 결과
     */
    @Transactional
    fun finish(attemptId: UUID): FinishResult {
        var attempt = lockOwned(attemptId)
        val answers = judgmentService.timeline(attempt.id)
        if (attempt.finishedAt == null) {
            if (!FinishPolicy.canFinish(answers)) {
                throw BusinessException(HttpStatus.CONFLICT, "REVEAL_CONDITION_UNMET", "마무리 조건 미충족", "생각을 한 번 이상 살펴본 뒤에 마무리할 수 있어요.")
            }
            attempt = attempt.finish(now())
            attemptRepository.finish(attempt)
        }
        val finishedAt = checkNotNull(attempt.finishedAt)
        return revealed(attempt, finishedAt, missionService.getVersion(attempt.missionVersionId), answers, judgmentService.results(attempt.id))
    }

    /** 돌아보기 저장 + 학습 완료 (sequence-diagram 3.3, FN-LRN-12·14): 같은 트랜잭션. 마무리 전이면 409 REVEAL_CONDITION_UNMET, 완료 뒤면 409 ATTEMPT_CLOSED */
    @Transactional
    fun saveReflection(attemptId: UUID, command: Reflection): Attempt {
        val completed = lockOwned(attemptId).complete(now())
        attemptRepository.insertReflection(completed.id, command, checkNotNull(completed.completedAt))
        attemptRepository.complete(completed)
        return completed
    }

    /**
     * 자기 평가 (FN-LRN-13, sequence-diagram 3.3): 마무리 뒤·완료 전에 기준표 요소별 자기 체크를 저장하고 AI 확인과 나란히 돌려줌.
     * 답변·판정은 건드리지 않음. 비었거나 같은 요소가 두 번이거나 이 시도 기준표에 없는 요소면 400
     */
    @Transactional
    fun saveSelfAssessment(attemptId: UUID, checks: List<SelfCheck>): List<SelfAssessmentItem> {
        val attempt = lockOwned(attemptId).also { it.requireFinished() }
        val rubric = missionService.rubric(attempt.missionVersionId, attempt.rubricVersionId)
        val elementIds = rubric.elements.map { it.id }.toSet()
        if (checks.isEmpty() || checks.map { it.elementId }.toSet().size != checks.size || !elementIds.containsAll(checks.map { it.elementId })) {
            throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "자기 평가 항목 오류", "이 미션의 기준표 요소를 한 번씩만 보내야 함")
        }
        attemptRepository.saveSelfAssessments(attempt.id, checks, now())
        val selfChecks = attemptRepository.findSelfAssessments(attempt.id)
        val checklist = Checklist.of(rubric.elements, judgedElements(judgmentService.timeline(attempt.id), judgmentService.results(attempt.id)))
        return checklist.map { SelfAssessmentItem(it.elementId, it.label, selfChecks[it.elementId], it.satisfied, it.quote) }
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

    /**
     * 답변 제출용: 시도 행을 잠그고 본인 시도인지 확인 (class-diagram 4.1 AnswerService --> AttemptService).
     * 제출 가능 여부는 같은 키 재요청을 먼저 처리한 뒤 Attempt.requireAnswerable()로 확인. 호출한 쪽 트랜잭션 필요
     */
    fun lockForAnswer(attemptId: UUID): Attempt = lockOwned(attemptId)

    /**
     * 답변 제출 뒤 초안의 답 칸 비우기 (FN-LRN-15·16): 제출한 답이 새로고침 때 미제출 초안으로 돌아오지 않게.
     * 메모는 보완 답변에도 쓰므로 유지(P05). lockForAnswer와 같은 트랜잭션에서 호출
     */
    fun clearSubmittedDraft(attemptId: UUID, now: Instant) = draftRepository.clearAnswer(attemptId, now)

    /**
     * 피드백용 본인 시도와 답변 타임라인 (class-diagram 4.2 FeedbackFacade --> AttemptService : 타임라인).
     * 없으면 404, 남의 시도면 403
     */
    @Transactional(readOnly = true)
    fun timeline(attemptId: UUID): AttemptTimeline {
        val attempt = requireOwned(attemptId)
        return AttemptTimeline(attempt, judgmentService.timeline(attempt.id))
    }

    /** 정답·예시 답(revealKind는 입력 방식으로)과 체크리스트 (FN-LRN-11). 시도에 고정된 미션·기준표 버전으로 */
    private fun revealed(
        attempt: Attempt,
        finishedAt: Instant,
        mission: MissionView,
        answers: List<TimelineAnswer>,
        feedbacks: Map<UUID, FeedbackResult>,
    ): FinishResult {
        val rubric = missionService.rubric(attempt.missionVersionId, attempt.rubricVersionId)
        return FinishResult(finishedAt, rubric.exampleAnswer, RevealKind.of(mission.inputType), Checklist.of(rubric.elements, judgedElements(answers, feedbacks)))
    }

    /** 처리 완료 판정의 요소, 답변 버전 순 */
    private fun judgedElements(answers: List<TimelineAnswer>, feedbacks: Map<UUID, FeedbackResult>) =
        answers.mapNotNull { feedbacks[it.answerId]?.judgment }.flatMap { it.elements }

    /** PostgreSQL timestamptz는 마이크로초까지 저장하므로 응답과 저장값이 같도록 맞춤 */
    private fun now(): Instant = Instant.now().truncatedTo(ChronoUnit.MICROS)

    /** 시도 행을 잠그고(FOR UPDATE) 본인 시도인지 확인. 답변 제출·마무리·돌아보기·자기 평가를 한 줄로 세움. 호출한 쪽 트랜잭션 필요 */
    private fun lockOwned(attemptId: UUID): Attempt {
        val attempt = attemptRepository.lockById(attemptId)
            ?: throw BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "학습 시도 없음")
        UserContextHolder.current().requireStudent(attempt.studentId)
        return attempt
    }

    /** 없으면 404, 다른 학생의 시도면 403 (api-spec 1.2 학생은 본인 기록만) */
    private fun requireOwned(attemptId: UUID): Attempt {
        val attempt = attemptRepository.findById(attemptId)
            ?: throw BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "학습 시도 없음")
        UserContextHolder.current().requireStudent(attempt.studentId)
        return attempt
    }
}
