package com.sagomungchi.learning.theme.domain

import com.sagomungchi.learning._common.exception.DomainException
import com.sagomungchi.learning._common.exception.ErrorKind
import com.sagomungchi.learning.mission.domain.DraftStatus
import com.sagomungchi.learning.mission.domain.DraftVersions
import com.sagomungchi.learning.mission.domain.GeneratedDraft
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.ThinkingType
import java.time.Instant
import java.time.LocalDate
import java.util.UUID

/** 테마 초안을 만든 방식 (ERD 4.2.1 theme_draft.source, #438): 주간 자동 AUTO, 관리자 요청·다시 생성 ADMIN */
enum class ThemeDraftSource { AUTO, ADMIN }

/** 유형 하나의 미션 입력 (theme_draft.input.missions[]). 성취기준은 1개 이상 */
data class ThemeMissionInput(val thinkingType: ThinkingType, val inputType: InputType, val standardCodes: List<String>)

/** theme_draft.input: 주제와 유형 5개의 미션 입력(관리자가 고르지 않은 유형은 learning이 채운 값), 유형 순(월~금 배치 순) */
data class ThemeDraftInput(val topic: String?, val missions: List<ThemeMissionInput>)

/**
 * 실패 한 묶음 (check_results[].failures[]). stage는 ai `THEME`·`MISSION`·`REVIEW`·`IMAGE`, learning 검사 `LEARNING`,
 * AI 호출 실패 `AI_CALL`(사유는 실패 코드). ai 요청 previousFailures[]와 같은 모양
 */
data class ThemeFailure(val stage: String, val reasons: List<String>)

/** check_results 한 줄: 시도 번호와 그 시도의 실패 */
data class ThemeAttemptFailures(val attempt: Int, val failures: List<ThemeFailure>)

// ===== ai 응답 (api-spec 4.2 `POST /internal/theme-drafts`). theme_draft.output에 그대로 저장 =====

data class GeneratedCharacter(val name: String, val look: String)

/** 요일 하나: 장소·그림 메모는 초안에만, 단서·rulesOut은 테마 요일 칸으로 */
data class GeneratedThemeDay(
    val day: ThemeDay,
    val thinkingType: ThinkingType,
    val place: String,
    val sceneNote: String,
    val clue: String,
    val rulesOut: List<String>,
)

/** 테마 틀. 세계관·인물·그림 메모는 그림 생성용으로 초안에만 남고 테마에 저장하지 않음 */
data class GeneratedTheme(
    val title: String,
    val world: String,
    val characters: List<GeneratedCharacter>,
    val styleNote: String,
    val outfit: String,
    val intro: String,
    val outro: String,
    val bigQuestion: String,
    val candidates: List<String>,
    val answer: String,
    val days: List<GeneratedThemeDay>,
)

/** 요일 미션: draft는 미션 초안(api-spec 4.2 `/internal/mission-drafts` draft)과 같은 모양 */
data class GeneratedThemeMission(val day: ThemeDay, val thinkingType: ThinkingType, val draft: GeneratedDraft)

data class GeneratedDialogue(val day: ThemeDay, val lines: List<DialogueLine>)

/** 끝내 실패해도 그 항목만 빼고 성공으로 돌려준 것·검토의 애매한 항목 */
data class ThemeWarning(val stage: String, val item: String, val reason: String)

/**
 * 생성 결과 (theme_draft.output). 장면 키는 `INTRO`·`MON`~`FRI`·`OUTRO`, 그림·영상 값은 ai가 올린 S3 키(`theme-drafts/…`),
 * 움직임은 ai가 정한 JSON 객체. 실패 단계(failure)와 버전은 check_results·버전 칼럼에 따로 둠
 */
data class ThemeDraftOutput(
    val theme: GeneratedTheme?,
    val missions: List<GeneratedThemeMission>,
    val dialogues: List<GeneratedDialogue>,
    val images: Map<String, String>,
    val videos: Map<String, String>,
    val motions: Map<String, Map<String, Any?>>,
    val warnings: List<ThemeWarning>,
)

/** 생성 1회 결과 */
sealed interface ThemeDraftAttempt {
    /** ai(failure 없음)·learning 검사 통과 */
    data class Passed(val output: ThemeDraftOutput, val versions: DraftVersions) : ThemeDraftAttempt

    /** 결과는 받았지만 ai failure 또는 learning 검사 실패 */
    data class CheckFailed(val output: ThemeDraftOutput, val failures: List<ThemeFailure>, val versions: DraftVersions) : ThemeDraftAttempt

    /** AI 호출 실패 (failureCode는 판정과 같은 AI_*) */
    data class AiFailed(val failureCode: String) : ThemeDraftAttempt
}

/**
 * 테마 초안 (class-diagram 4.4, ERD 4.2.1 theme_draft, state-diagram 3.5.1). 미션 초안(MissionDraft)과 같은 상태·전이이고
 * 생성은 주기 작업이 리스를 잡고 1회씩, 반복·상한은 여기서 정한다. 학생 정보는 없다
 */
class ThemeDraft(
    val id: UUID,
    val grade: ThemeGrade,
    val weekStart: LocalDate,
    val source: ThemeDraftSource,
    val requestedBy: UUID?,
    val input: ThemeDraftInput,
    status: DraftStatus,
    attempts: Int,
    checkResults: List<ThemeAttemptFailures>,
    output: ThemeDraftOutput?,
    failureCode: String?,
    versions: DraftVersions,
    leaseUntil: Instant?,
    themeId: UUID?,
    val createdAt: Instant,
    updatedAt: Instant,
) {
    var status: DraftStatus = status
        private set
    var attempts: Int = attempts
        private set
    var checkResults: List<ThemeAttemptFailures> = checkResults
        private set
    var output: ThemeDraftOutput? = output
        private set
    var failureCode: String? = failureCode
        private set
    var versions: DraftVersions = versions
        private set
    var leaseUntil: Instant? = leaseUntil
        private set
    var themeId: UUID? = themeId
        private set
    var updatedAt: Instant = updatedAt
        private set

    /**
     * 다음 생성에 넣을 이전 실패 (api-spec 4.2 previousFailures, #437 합의): 시간순, 겹치는 것은 한 번.
     * ai 단계 실패는 그대로, learning 실패는 `<요일> …`으로 시작하는 사유(미션 규칙)는 `MISSION`, 나머지(배치·정답 논리·길이·모양)는 `THEME`,
     * AI 호출 실패는 내용 피드백이 아니라 넣지 않음. 사유가 빈 묶음은 뺌(ai는 reasons 1개 이상, 아니면 422)
     */
    val previousFailures: List<ThemeFailure>
        get() = checkResults.flatMap { it.failures }.flatMap(::forAi).filter { it.reasons.isNotEmpty() }.distinct()

    /**
     * 생성 1회 기록 (class-diagram 4.4 recordAttempt). attempts + 1, 리스를 비움.
     * 통과면 READY. 실패면 사유를 쌓고 상한 미만이면 GENERATING 그대로(다음 주기에 다시 생성),
     * 상한이면 마지막 실패가 AI 호출이면 FAILED, 아니면 CHECK_FAILED. AI 호출 실패는 이전 결과를 지우지 않음
     */
    fun recordAttempt(result: ThemeDraftAttempt, maxAttempts: Int, now: Instant) {
        if (status != DraftStatus.GENERATING) conflict("생성 중이 아님")
        attempts += 1
        leaseUntil = null
        updatedAt = now
        when (result) {
            is ThemeDraftAttempt.Passed -> {
                output = result.output
                versions = result.versions
                failureCode = null
                status = DraftStatus.READY
            }
            is ThemeDraftAttempt.CheckFailed -> {
                output = result.output
                versions = result.versions
                failureCode = null
                checkResults = checkResults + ThemeAttemptFailures(attempts, result.failures)
                if (attempts >= maxAttempts) status = DraftStatus.CHECK_FAILED
            }
            is ThemeDraftAttempt.AiFailed -> {
                failureCode = result.failureCode
                checkResults = checkResults + ThemeAttemptFailures(attempts, listOf(ThemeFailure(AI_CALL, listOf(result.failureCode))))
                if (attempts >= maxAttempts) status = DraftStatus.FAILED
            }
        }
    }

    /** READY만 채택 (미션·테마를 만들기 전에 확인) */
    fun requireAdoptable() {
        if (status != DraftStatus.READY) conflict("채택할 수 없는 상태")
    }

    /** READY만 채택 → ADOPTED + 만든 테마 */
    fun adopt(themeId: UUID, now: Instant) {
        requireAdoptable()
        status = DraftStatus.ADOPTED
        this.themeId = themeId
        updatedAt = now
    }

    /** READY·CHECK_FAILED·FAILED만 버림 */
    fun discard(now: Instant) {
        if (status !in DISCARDABLE) conflict("버릴 수 없는 상태")
        status = DraftStatus.DISCARDED
        updatedAt = now
    }

    /**
     * 다시 생성 (사용자 결정 2026-11-10): READY·CHECK_FAILED·FAILED·DISCARDED에서만 같은 input·학년·주의 새 초안(ADMIN, attempts 0).
     * 이 초안은 그대로 둔다. GENERATING·ADOPTED는 409
     */
    fun regenerate(id: UUID, requestedBy: UUID, now: Instant): ThemeDraft {
        if (status !in REGENERABLE) conflict("다시 생성할 수 없는 상태")
        return requested(id, grade, weekStart, ThemeDraftSource.ADMIN, requestedBy, input, now)
    }

    private fun conflict(detail: String): Nothing =
        throw DomainException(ErrorKind.CONFLICT, "CONFLICT", "초안 상태 충돌", "$detail: $status")

    companion object {
        const val AI_CALL = "AI_CALL"
        const val LEARNING = "LEARNING"

        /** ai previousFailures[].stage로 보낼 수 있는 값 (그 밖은 ai 422) */
        val AI_STAGES = setOf("THEME", "MISSION", "REVIEW", "IMAGE")
        private const val THEME_STAGE = "THEME"
        private const val MISSION_STAGE = "MISSION"

        /** learning 미션 규칙 사유: `<요일> <검사 코드> <자세히>` (api-spec 4.2, ThemeDraftRules) */
        private val MISSION_REASON = Regex("^(${ThemeDay.entries.joinToString("|")}) ")

        private val DISCARDABLE = setOf(DraftStatus.READY, DraftStatus.CHECK_FAILED, DraftStatus.FAILED)
        private val REGENERABLE = DISCARDABLE + DraftStatus.DISCARDED

        /** 새 초안: GENERATING, attempts 0 */
        fun requested(id: UUID, grade: ThemeGrade, weekStart: LocalDate, source: ThemeDraftSource, requestedBy: UUID?, input: ThemeDraftInput, now: Instant) =
            ThemeDraft(id, grade, weekStart, source, requestedBy, input, DraftStatus.GENERATING, 0, emptyList(), null, null,
                DraftVersions(null, null), null, null, now, now)

        private fun forAi(failure: ThemeFailure): List<ThemeFailure> = when (failure.stage) {
            in AI_STAGES -> listOf(failure)
            LEARNING -> failure.reasons.partition { MISSION_REASON.containsMatchIn(it) }.let { (mission, theme) ->
                listOfNotNull(
                    theme.takeIf { it.isNotEmpty() }?.let { ThemeFailure(THEME_STAGE, it) },
                    mission.takeIf { it.isNotEmpty() }?.let { ThemeFailure(MISSION_STAGE, it) },
                )
            }
            else -> emptyList()
        }
    }
}

/** 초안 목록 (api-spec 1.1 봉투) */
data class ThemeDraftPage(val items: List<ThemeDraft>, val page: Int, val size: Int, val totalElements: Long)

/** 장면 미리보기 (api-spec 4.1 ThemeDraft.scenes[]): 그림·영상은 presigned URL, 움직임은 그대로 */
data class ThemeDraftScene(val scene: String, val imageUrl: String?, val videoUrl: String?, val motion: Map<String, Any?>?)

/** 초안 응답의 draft: ai 응답 중 theme·missions·dialogues·warnings (장면은 scenes로 따로) */
data class ThemeDraftContent(
    val theme: GeneratedTheme?,
    val missions: List<GeneratedThemeMission>,
    val dialogues: List<GeneratedDialogue>,
    val warnings: List<ThemeWarning>,
)

/** 초안 응답 (api-spec 4.1 ThemeDraft) */
data class ThemeDraftView(
    val draftId: UUID,
    val status: DraftStatus,
    val source: ThemeDraftSource,
    val grade: ThemeGrade,
    val weekStart: LocalDate,
    val attempts: Int,
    val maxAttempts: Int,
    val input: ThemeDraftInput,
    val checkResults: List<ThemeAttemptFailures>,
    val draft: ThemeDraftContent?,
    val scenes: List<ThemeDraftScene>,
    val failureCode: String?,
    val versions: DraftVersions,
    val themeId: UUID?,
    val requestedBy: UUID?,
    val createdAt: Instant,
    val updatedAt: Instant,
)

data class ThemeDraftViewPage(val items: List<ThemeDraftView>, val page: Int, val size: Int, val totalElements: Long)
