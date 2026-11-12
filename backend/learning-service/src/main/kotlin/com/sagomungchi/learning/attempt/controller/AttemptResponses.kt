package com.sagomungchi.learning.attempt.controller

import com.sagomungchi.learning._common.web.AnswerItem
import com.sagomungchi.learning._common.web.MissionResponse
import com.sagomungchi.learning._common.web.OptionResponse
import com.sagomungchi.learning.attempt.domain.AttemptDraft
import com.sagomungchi.learning.attempt.domain.AttemptStatus
import com.sagomungchi.learning.attempt.domain.Difficulty
import com.sagomungchi.learning.attempt.domain.DraftContent
import com.sagomungchi.learning.attempt.domain.FinishResult
import com.sagomungchi.learning.attempt.domain.HintOpened
import com.sagomungchi.learning.attempt.domain.Reflection
import com.sagomungchi.learning.attempt.domain.RevealKind
import com.sagomungchi.learning.attempt.service.AttemptDetail
import com.sagomungchi.learning.judgment.domain.ElementView
import com.sagomungchi.learning.judgment.domain.FeedbackResult
import com.sagomungchi.learning.judgment.domain.NextAction
import com.sagomungchi.learning.judgment.domain.TimelineAnswer
import com.sagomungchi.learning.mission.domain.MissionView
import java.time.Instant
import java.util.UUID

/** 초안 저장 요청 (api-spec 2.2 `content: {answer, memo}`) */
data class DraftRequest(val content: DraftContent)

/** 초안 (api-spec 3.6). 한 번도 저장하지 않았으면 savedAt 없음 */
data class DraftResponse(
    val version: Int,
    val content: DraftContent,
    val savedAt: Instant?,
) {
    companion object {
        fun from(draft: AttemptDraft) =
            DraftResponse(draft.version, draft.content, draft.savedAt.takeUnless { draft.neverSaved })
    }
}

/**
 * 시도 상세. 필드 이름은 프론트 Attempt 모델(api-spec 3.7·3.8). mission은 시도에 고정된 버전.
 * answers는 제출 답변과 피드백(판정 전이면 처리 상태만), nextActions는 마지막 답변의 다음 행동.
 * reveal·revealKind·checklist는 마무리한 뒤에만, reflection은 돌아보기를 저장한 뒤에만 (그 전에는 null)
 */
data class AttemptResponse(
    val attemptId: UUID,
    val studentId: UUID,
    val mission: MissionResponse,
    val status: AttemptStatus,
    val finishedAt: Instant?,
    val answers: List<AnswerItem<FeedbackResult>>,
    val helped: Boolean,
    val draft: DraftResponse,
    val nextActions: List<NextAction>,
    val reveal: String?,
    val revealKind: RevealKind?,
    val checklist: List<ElementView>?,
    val reflection: ReflectionView?,
    /** 테마 시도의 문제 전 대화·그림 위 생각 열기 위치·문제 전 영상 URL (#438). EXTRA는 null */
    val themeScene: com.sagomungchi.learning.theme.domain.ThemeScene? = null,
) {
    companion object {
        fun from(detail: AttemptDetail) = AttemptResponse(
            attemptId = detail.attempt.id,
            studentId = detail.attempt.studentId,
            mission = MissionResponse.from(detail.mission),
            status = detail.attempt.status,
            finishedAt = detail.attempt.finishedAt,
            answers = detail.answers.map { AnswerItem.from(it, detail.feedbacks.getValue(it.answerId)) },
            helped = detail.helped,
            draft = DraftResponse.from(detail.draft),
            nextActions = detail.answers.lastOrNull()?.let { detail.feedbacks.getValue(it.answerId).nextActions }.orEmpty(),
            reveal = detail.revealed?.reveal,
            revealKind = detail.revealed?.revealKind,
            checklist = detail.revealed?.checklist,
            reflection = detail.reflection?.let(ReflectionView::from),
            themeScene = detail.themeScene,
        )
    }
}

/** 마무리 결과 (api-spec 2.2 finish, 3.8): 정답·예시 답과 체크리스트. 프론트는 이후 시도 상세를 다시 읽음 */
data class FinishResponse(
    val attemptId: UUID,
    val finishedAt: Instant,
    val reveal: String?,
    val revealKind: RevealKind,
    val checklist: List<ElementView>,
) {
    companion object {
        fun from(attemptId: UUID, result: FinishResult) =
            FinishResponse(attemptId, result.finishedAt, result.reveal, result.revealKind, result.checklist)
    }
}

/** 돌아보기 요청 (api-spec 2.2 `{difficulty(필수), text(선택)}`). difficulty가 없거나 EASY·NORMAL·HARD가 아니면 400 */
data class ReflectionRequest(val difficulty: Difficulty, val text: String? = null) {
    /** 빈 글은 달라진 점을 쓰지 않은 것으로 저장 */
    fun toCommand() = Reflection(difficulty, text?.takeIf { it.isNotBlank() })
}

/** 프론트 Reflection 모델 `{difficulty, text}` */
data class ReflectionView(val difficulty: Difficulty, val text: String?) {
    companion object {
        fun from(reflection: Reflection) = ReflectionView(reflection.difficulty, reflection.text)
    }
}

/** 돌아보기 저장 결과: 학습 완료 (sequence-diagram 3.3 "200 학습 완료"). 완료 시점은 시도 상세·기록 조회에서 */
data class ReflectionResponse(
    val attemptId: UUID,
    val status: AttemptStatus,
    val reflection: ReflectionView,
)

/** 자기 평가 요청: 기준표 요소별 체크 (FN-LRN-13) */
data class SelfAssessmentRequest(val checks: List<SelfCheckRequest>)

data class SelfCheckRequest(val elementId: UUID, val checked: Boolean)

/** 생각 열기 (프론트는 question만 사용, seq·total은 몇 번째 질문인지 표시용) */
data class HintResponse(
    val question: String,
    val seq: Int,
    val total: Int,
) {
    companion object {
        fun from(opened: HintOpened) = HintResponse(opened.question.content, opened.question.seq, opened.total)
    }
}

/* 공유 응답 DTO 변환 (#251, mission·record와 같은 변환을 이 기능이 둠) */

internal fun MissionResponse.Companion.from(mission: MissionView) = MissionResponse(
    id = mission.id,
    title = mission.title,
    subject = mission.subject,
    grade = mission.gradeMin,
    gradeMax = mission.gradeMax,
    thinkingType = mission.thinkingType.name,
    inputType = mission.inputType.name,
    question = mission.question,
    hint = mission.guide,
    sceneUri = mission.sceneUri,
    staticSceneUri = mission.staticSceneUri,
    choices = mission.choices.map { OptionResponse(it.id, it.label) },
    inputTemplate = mission.inputTemplate,
    categories = mission.categories.map { OptionResponse(it.id, it.label) },
    answerUnit = mission.answerUnit,
    sceneMotion = mission.sceneMotion,
)

internal fun AnswerItem.Companion.from(answer: TimelineAnswer, feedback: FeedbackResult) = AnswerItem(
    answerId = answer.answerId,
    version = answer.version,
    submittedAt = answer.submittedAt,
    inputType = answer.inputType.name,
    text = answer.text.orEmpty(),
    followupId = answer.followupId,
    content = answer.content,
    feedback = feedback,
)
