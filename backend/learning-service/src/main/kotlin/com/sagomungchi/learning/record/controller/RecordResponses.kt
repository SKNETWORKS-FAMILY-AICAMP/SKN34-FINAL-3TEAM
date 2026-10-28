package com.sagomungchi.learning.record.controller

import com.sagomungchi.learning.attempt.controller.AttemptResponse
import com.sagomungchi.learning.attempt.controller.AnswerItem
import com.fasterxml.jackson.annotation.JsonUnwrapped
import com.sagomungchi.learning.attempt.domain.AttemptStatus
import com.sagomungchi.learning.attempt.domain.Difficulty
import com.sagomungchi.learning.attempt.domain.RevealKind
import com.sagomungchi.learning.attempt.service.AttemptDetail
import com.sagomungchi.learning.judgment.domain.ElementView
import com.sagomungchi.learning.judgment.domain.NextAction
import com.sagomungchi.learning.mission.controller.MissionResponse
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

/** 학습 현황 요약 (api-spec 2.3·3.9). childId는 학생 ID(core가 그대로 프록시) */
data class SummaryResponse(
    val childId: UUID,
    val state: QueryState,
    val period: Period,
    val inclusionRule: String,
    val metrics: List<Metric>,
)

/** 유형별 활동 (api-spec 3.9) */
data class ThinkingTypesResponse(
    val childId: UUID,
    val state: QueryState,
    val period: Period,
    val items: List<ThinkingTypeItem>,
)

data class ThinkingTypeItem(val type: ThinkingType, val state: QueryState, val missions: List<MissionRef>)

/** 기록 목록 (api-spec 1.1 봉투 + 3.9 childId·state·period·inclusionRule) */
data class RecordPageResponse(
    val items: List<RecordAttemptResponse>,
    val page: Int,
    val size: Int,
    val totalElements: Int,
    val childId: UUID,
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
            childId = studentId,
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
    val answers: List<AnswerItem>,
    val helped: Boolean,
    val nextActions: List<NextAction>,
    val reveal: String?,
    val revealKind: RevealKind?,
    val checklist: List<ElementView>?,
    val reflection: RecordReflection?,
    val completedAt: Instant?,
    val hintUsages: List<HintUsage>,
) {
    companion object {
        fun from(record: RecordAttempt): RecordAttemptResponse = AttemptResponse.from(record.detail).let {
            RecordAttemptResponse(
                it.attemptId, it.studentId, it.mission, it.status, it.finishedAt, it.answers, it.helped,
                it.nextActions, it.reveal, it.revealKind, it.checklist,
                it.reflection?.let { reflection -> RecordReflection(reflection.difficulty, reflection.text, record.reflectionCreatedAt) },
                record.detail.attempt.completedAt,
                record.hintUsages.map(::HintUsage),
            )
        }
    }
}

/** 돌아보기와 작성 시각 (report #51) */
data class RecordReflection(val difficulty: Difficulty, val text: String?, val createdAt: Instant?)

/** 생각 열기 열람 시각 (report #51: 최초 답변 전 열람 여부를 report가 판단) */
data class HintUsage(val openedAt: Instant)

/** 기록 상세 (core #40): 시도와 화면이 유지할 조회 기간·상태 */
data class RecordAttemptDetailResponse(
    @get:JsonUnwrapped val attempt: RecordAttemptResponse,
    val state: QueryState,
    val period: Period,
)

/** 되묻기 전후 변화 (api-spec 3.4 changes, 1.1 페이지). counts는 [최초, 마지막] */
data class ChangesResponse(
    val items: List<ChangeItem>,
    val page: Int,
    val size: Int,
    val totalElements: Int,
    val childId: UUID,
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
