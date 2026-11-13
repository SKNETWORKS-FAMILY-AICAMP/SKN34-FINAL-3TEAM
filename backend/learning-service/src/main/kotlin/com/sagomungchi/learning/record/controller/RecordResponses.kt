package com.sagomungchi.learning.record.controller

import com.sagomungchi.learning._common.web.FeedbackResponse
import com.sagomungchi.learning._common.web.JudgmentResponse
import com.sagomungchi.learning._common.web.ElementResponse
import com.sagomungchi.learning._common.web.FollowupResponse
import com.sagomungchi.learning._common.web.FeedbackVersions

import com.fasterxml.jackson.annotation.JsonUnwrapped
import com.sagomungchi.learning._common.web.AnswerItem
import com.sagomungchi.learning._common.web.MissionListItemResponse
import com.sagomungchi.learning._common.web.MissionResponse
import com.sagomungchi.learning._common.web.OptionResponse
import com.sagomungchi.learning.attempt.domain.AttemptStatus
import com.sagomungchi.learning.attempt.domain.Difficulty
import com.sagomungchi.learning.attempt.domain.Reflection
import com.sagomungchi.learning.attempt.domain.RevealKind
import com.sagomungchi.learning.judgment.domain.ElementView
import com.sagomungchi.learning.judgment.domain.FeedbackResult
import com.sagomungchi.learning.judgment.domain.NextAction
import com.sagomungchi.learning.judgment.domain.TimelineAnswer
import com.sagomungchi.learning.mission.domain.MissionListItem
import com.sagomungchi.learning.mission.domain.MissionView
import com.sagomungchi.learning.mission.domain.ThinkingType
import com.sagomungchi.learning.record.domain.Metric
import com.sagomungchi.learning.record.domain.Period
import com.sagomungchi.learning.record.domain.QueryState
import com.sagomungchi.learning.record.service.Change
import com.sagomungchi.learning.record.service.Evidence
import com.sagomungchi.learning.record.service.MissionRef
import com.sagomungchi.learning.record.service.RecordAttempt
import com.sagomungchi.learning.record.service.RecordPage
import com.sagomungchi.learning.record.service.RecordService
import java.time.Instant
import java.util.UUID

/** 학습 현황 요약 (api-spec 2.3·3.9). 내부 응답은 호출 역할과 무관하게 studentId, 학부모 공개 응답의 childId는 core가 바꿈 (core #40·report #51) */
data class SummaryResponse(
    val studentId: UUID,
    val state: QueryState,
    val period: Period,
    val inclusionRule: String,
    val metrics: List<Metric>,
)

/** 유형별 활동 (api-spec 3.9) */
data class ThinkingTypesResponse(
    val studentId: UUID,
    val state: QueryState,
    val period: Period,
    val items: List<ThinkingTypeItem>,
)

data class ThinkingTypeItem(val type: ThinkingType, val state: QueryState, val missions: List<MissionRef>)

/** 기록 목록 (api-spec 1.1 봉투 + studentId·state·period·inclusionRule) */
data class RecordPageResponse(
    val items: List<RecordAttemptResponse>,
    val page: Int,
    val size: Int,
    val totalElements: Int,
    val studentId: UUID,
    val state: QueryState,
    val period: Period,
    val inclusionRule: String,
) {
    companion object {
        fun from(studentId: UUID, period: Period, page: RecordPage) = RecordPageResponse(
            items = page.items.map(RecordAttemptResponse::from),
            page = page.page,
            size = page.size,
            totalElements = page.totalElements,
            studentId = studentId,
            state = page.state,
            period = period,
            inclusionRule = RecordService.INCLUSION_RULE,
        )
    }
}

/**
 * 학부모·에이전트·리포트용 시도 (프론트 PublicAttempt = Attempt − draft). 학생 시도 상세와 같은 값에서 초안(메모 포함)만 뺌 (P05)
 */
data class RecordAttemptResponse(
    val attemptId: UUID,
    val studentId: UUID,
    val mission: MissionResponse,
    val status: AttemptStatus,
    val finishedAt: Instant?,
    val answers: List<AnswerItem<FeedbackResponse>>,
    val helped: Boolean,
    val nextActions: List<NextAction>,
    val reveal: String?,
    val revealKind: RevealKind?,
    val checklist: List<ElementView>?,
    val reflection: RecordReflection?,
    val completedAt: Instant?,
    val hintUsages: List<HintUsage>,
    val context: com.sagomungchi.learning.attempt.domain.AttemptContext,
) {
    companion object {
        /** 시도 상세(AttemptResponse)와 같은 값을 AttemptDetail에서 직접 만듦: 다른 기능 controller DTO를 거치지 않음 (#251) */
        fun from(record: RecordAttempt): RecordAttemptResponse {
            val detail = record.detail
            return RecordAttemptResponse(
                attemptId = detail.attempt.id,
                studentId = detail.attempt.studentId,
                mission = MissionResponse.from(detail.mission),
                status = detail.attempt.status,
                finishedAt = detail.attempt.finishedAt,
                answers = detail.answers.map { AnswerItem.from(it, detail.feedbacks.getValue(it.answerId)) },
                helped = detail.helped,
                nextActions = detail.answers.lastOrNull()?.let { detail.feedbacks.getValue(it.answerId).nextActions }.orEmpty(),
                reveal = detail.revealed?.reveal,
                revealKind = detail.revealed?.revealKind,
                checklist = detail.revealed?.checklist,
                reflection = detail.reflection?.let { RecordReflection(it.difficulty, it.text, checkNotNull(record.reflectionCreatedAt)) },
                completedAt = detail.attempt.completedAt,
                hintUsages = record.hintUsages.map(::HintUsage),
                context = detail.attempt.context,
            )
        }
    }
}

/** 돌아보기와 작성 시각 (report #51). 돌아보기가 있으면 작성 시각도 항상 있음(= completedAt) */
data class RecordReflection(val difficulty: Difficulty, val text: String?, val createdAt: Instant)

/** 생각 열기 열람 시각 (report #51: 최초 답변 전 열람 여부를 report가 판단) */
data class HintUsage(val openedAt: Instant)

/** 기록 상세 (core #40): 시도와 화면이 유지할 조회 기간·상태 */
data class RecordAttemptDetailResponse(
    @get:JsonUnwrapped val attempt: RecordAttemptResponse,
    val state: QueryState,
    val period: Period,
)

/** 학생 홈 (api-spec 2.3, core #40). resume은 기록 목록 항목과 같은 모양(초안·메모 없음), missions는 학생 미션 목록 항목 */
data class HomeResponse(
    val studentId: UUID,
    val state: QueryState,
    val period: Period,
    val resume: RecordAttemptResponse?,
    val missions: List<MissionListItemResponse>,
)

/** 생각 활동 (api-spec 2.3 FN-DSH-04, core #40) */
data class ThinkingActivitiesResponse(
    val studentId: UUID,
    val state: QueryState,
    val period: Period,
    val items: List<ThinkingActivityItem>,
)

data class ThinkingActivityItem(val attemptId: UUID, val thinkingType: ThinkingType, val missionTitle: String, val reflection: Reflection?)

/** 되묻기 전후 변화 (api-spec 3.4 changes, 1.1 페이지). counts는 [최초, 마지막] */
data class ChangesResponse(
    val items: List<ChangeItem>,
    val page: Int,
    val size: Int,
    val totalElements: Int,
    val studentId: UUID,
    val state: QueryState,
    val period: Period,
)

data class ChangeItem(
    val attemptId: UUID,
    val followup: String?,
    val first: AnswerText,
    val revised: AnswerText,
    val counts: ChangeCounts,
) {
    companion object {
        fun from(change: Change) = ChangeItem(
            attemptId = change.pair.attemptId,
            followup = change.pair.followup,
            first = AnswerText(change.pair.firstAnswerId, change.pair.firstText),
            revised = AnswerText(change.pair.lastAnswerId, change.pair.lastText),
            counts = ChangeCounts(
                chars = listOf(change.first.chars, change.revised.chars),
                sentences = listOf(change.first.sentences, change.revised.sentences),
                reasonConnectives = listOf(change.first.reasonConnectives, change.revised.reasonConnectives),
            ),
        )
    }
}

data class AnswerText(val answerId: UUID, val text: String)

data class ChangeCounts(val chars: List<Int>, val sentences: List<Int>, val reasonConnectives: List<Int>)

/** 근거 원문 (api-spec 3.9 `{items: Evidence[]}`) */
data class EvidenceResponse(val items: List<Evidence>)

/** 운영 현황 (FN-ADM-02) */
data class StatsResponse(
    val period: Period,
    val inclusionRule: String,
    val attempts: Int,
    val completedAttempts: Int,
    val students: Int,
)

/* 공유 응답 DTO 변환 (#251, mission·attempt와 같은 변환을 이 기능이 둠) */

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

internal fun MissionListItemResponse.Companion.from(item: MissionListItem) =
    MissionListItemResponse.of(MissionResponse.from(item.mission), item.progress.status.name, item.progress.attemptId, item.position, item.total)

internal fun AnswerItem.Companion.from(answer: TimelineAnswer, feedback: FeedbackResult) = AnswerItem(
    answerId = answer.answerId,
    version = answer.version,
    submittedAt = answer.submittedAt,
    inputType = answer.inputType.name,
    text = answer.text.orEmpty(),
    followupId = answer.followupId,
    content = answer.content,
    feedback = feedback.toResponse(),
)

internal fun FeedbackResult.toResponse() = FeedbackResponse(
    status.name,
    judgment?.let { j -> JudgmentResponse(
        j.judgmentId, j.result.name, j.trial,
        j.elements.map { e -> ElementResponse(
            e.elementId, e.label, e.code, e.goodThought, e.satisfied, e.quote, e.sourceType?.name,
        ) }, j.heldReason, j.corrected, j.modelScores, j.m2Notices,
    ) },
    followup?.let { FollowupResponse(it.followupId, it.type.name, it.question, it.source.name) },
    nextActions.map { it.name },
    versions?.let { FeedbackVersions(it.mission, it.rubric, it.model, it.prompt) },
)
