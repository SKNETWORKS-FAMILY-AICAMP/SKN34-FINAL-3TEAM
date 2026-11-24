package com.sagomungchi.learning.theme.service

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.storage.AssetUrls
import com.sagomungchi.learning._common.client.AiCallException
import com.sagomungchi.learning.mission.domain.AchievementStandard
import com.sagomungchi.learning.mission.domain.DraftRules
import com.sagomungchi.learning.mission.domain.DraftStatus
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.MissionSource
import com.sagomungchi.learning.mission.domain.MissionView
import com.sagomungchi.learning.mission.service.MissionService
import com.sagomungchi.learning.theme.client.AiThemeDraftRequest
import com.sagomungchi.learning.theme.client.AiThemeElementCode
import com.sagomungchi.learning.theme.client.AiThemeMission
import com.sagomungchi.learning.theme.client.AiThemeRegenerate
import com.sagomungchi.learning.theme.client.AiThemeStandard
import com.sagomungchi.learning.theme.client.ThemeDraftAiClient
import com.sagomungchi.learning.theme.domain.AdminWeeklyTheme
import com.sagomungchi.learning.theme.domain.ThemeDraft
import com.sagomungchi.learning.theme.domain.ThemeDraftAttempt
import com.sagomungchi.learning.theme.domain.ThemeDraftContent
import com.sagomungchi.learning.theme.domain.ThemeDraftInput
import com.sagomungchi.learning.theme.domain.ThemeDraftRules
import com.sagomungchi.learning.theme.domain.ThemeDraftReviewFilter
import com.sagomungchi.learning.theme.domain.ThemeDraftReviewPage
import com.sagomungchi.learning.theme.domain.ThemeDraftScene
import com.sagomungchi.learning.theme.domain.ThemeDraftSource
import com.sagomungchi.learning.theme.domain.ThemeDraftView
import com.sagomungchi.learning.theme.domain.ThemeDraftViewPage
import com.sagomungchi.learning.theme.domain.ThemeFailure
import com.sagomungchi.learning.theme.domain.ThemeGrade
import com.sagomungchi.learning.theme.domain.StandardSemesters
import com.sagomungchi.learning.theme.domain.ThemeMissionInput
import com.sagomungchi.learning.theme.domain.ThemeSemester
import com.sagomungchi.learning.theme.domain.ThemeTopicSeeds
import com.sagomungchi.learning.theme.domain.ThemeWeek
import com.sagomungchi.learning.theme.repository.ThemeDraftRepository
import org.slf4j.LoggerFactory
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.Clock
import java.time.DayOfWeek
import java.time.Instant
import java.time.LocalDate
import java.time.temporal.ChronoUnit
import java.util.UUID
import kotlin.random.Random

/** 테마 초안 요청 (api-spec 4.1 `POST /internal/admin/theme-drafts`). missions는 관리자가 고른 유형만(비운 유형은 learning이 채움) */
data class ThemeDraftCommand(
    val requestedBy: UUID,
    val grade: ThemeGrade,
    val weekStart: LocalDate,
    val topic: String?,
    val missions: List<ThemeMissionInput>,
)

/**
 * 주간 테마 초안 (class-diagram 4.4, FN-ADM-22, state-diagram 3.5.1, #438). 미션 초안(MissionDraftService)과 같은 구조:
 * 요청·주간 자동은 GENERATING으로 저장하고, 생성은 주기 작업(generateNext)이 리스를 잡고 ai 1회 + learning 검사씩 반복한다.
 * 채택은 미션 5개와 테마를 각 기능의 service로 한 트랜잭션에 만든다(다른 기능 저장소는 부르지 않음, architecture 계층 규칙)
 */
@Service
class ThemeDraftService(
    private val repository: ThemeDraftRepository,
    private val aiClient: ThemeDraftAiClient,
    private val missionService: MissionService,
    private val themeAdminService: WeeklyThemeAdminService,
    private val properties: AppProperties,
    private val clock: Clock,
    private val assetUrls: AssetUrls,
    private val semesters: StandardSemesters,
    private val planner: ThemeWeekPlanner,
    private val media: ThemeDraftMediaService,
) {
    val maxAttempts: Int get() = properties.themeDraft.maxAttempts

    /**
     * 관리자 요청 (state-diagram 3.5.1): 학년·적용 주(이번 주 이후 월요일)·주제 길이·유형 중복·성취기준 실재·그 학년을 포함하는 학년군·
     * 논술 학년을 확인(400)하고, 비운 유형은 자동 규칙으로, 비운 주제는 주제 씨앗으로 채워 GENERATING(ADMIN, attempts 0)
     */
    @Transactional
    fun request(command: ThemeDraftCommand): ThemeDraft {
        val grade = command.grade
        requireWeek(command.weekStart)
        planner.lockGrades(grade)
        planner.requireOpen(grade, command.weekStart)
        val topic = command.topic?.trim()?.takeIf { it.isNotEmpty() }
        if (topic != null && topic.length > MAX_TOPIC) invalid("topic은 ${MAX_TOPIC}자 이하")
        val missions = command.missions
        if (missions.map { it.thinkingType }.toSet().size != missions.size) invalid("missions의 thinkingType은 유형마다 1개까지")
        missions.forEach { mission ->
            val codes = mission.standardCodes
            if (codes.isEmpty() || codes.any { it.isBlank() } || codes.toSet().size != codes.size) {
                invalid("${mission.thinkingType} standardCodes는 겹치지 않는 코드 1개 이상")
            }
            if (mission.inputType == InputType.ESSAY && grade.grade < MissionView.ESSAY_MIN_GRADE) invalid("논술은 초${MissionView.ESSAY_MIN_GRADE} 이상")
        }
        val codes = missions.flatMap { it.standardCodes }
        val standards = missionService.standards(codes)
        codes.filterNot { it in standards }.takeIf { it.isNotEmpty() }?.let { invalid("성취기준 표에 없는 코드: ${it.joinToString()}") }
        codes.filterNot { standards.getValue(it).covers(grade.grade, grade.grade) }.takeIf { it.isNotEmpty() }?.let {
            invalid("테마 학년이 성취기준 학년군 밖: ${it.joinToString()}")
        }
        val input = autoInput(grade, command.weekStart, topic, missions)
            ?: throw BusinessException(HttpStatus.CONFLICT, "CONFLICT", "자동 성취기준 없음", "비운 유형을 채울 성취기준이 표에 없음")
        val draft = ThemeDraft.requested(UUID.randomUUID(), grade, command.weekStart, ThemeDraftSource.ADMIN, command.requestedBy, input, now())
        repository.insert(draft)
        return draft
    }

    /**
     * 주간 자동 (기준안 수요일 03:00 KST, 사용자 결정 2026-11-10): 그 주 G3~G6 각 1개(AUTO). 그 학년·주에 게시 테마가 있으면 건너뜀.
     * 부분 UK + ON CONFLICT DO NOTHING이라 레플리카가 같이 돌아도 학년·주당 하나. 한 학년이 실패해도 나머지는 만듦. 만든 개수를 돌려줌
     */
    fun createWeekly(weekStart: LocalDate): Int = ThemeGrade.entries.count { grade ->
        try {
            planner.autoIfOpen(grade, weekStart) {
                autoInput(grade, weekStart, null, emptyList())?.let { input ->
                    repository.insertAutoIfAbsent(ThemeDraft.requested(UUID.randomUUID(), grade, weekStart, ThemeDraftSource.AUTO, null, input, now()))
                } ?: run {
                    log.warn("weekly theme draft skipped: {} {} no achievement standards to choose", grade, weekStart)
                    false
                }
            }
        } catch (error: RuntimeException) {
            log.error("weekly theme draft failed: {} {}", grade, weekStart, error)
            false
        }
    }

    /**
     * 다시 생성: 원래 초안을 잠그고 같은 input·학년·주로 새 초안(ADMIN). GENERATING·ADOPTED면 409.
     * targets가 있으면 부분 다시 생성(#537): 원래 초안 regen.targets 밖 대상이 있으면 409, 새 초안 input.regenerate에 원래 초안·대상
     */
    @Transactional
    fun regenerate(draftId: UUID, author: UUID, targets: List<String>? = null): ThemeDraft {
        val root = media.rootId(draftId)
        val family = planner.lockDraftEdits(root)
        val original = repository.findById(draftId, lock = true) ?: notFound()
        if (targets != null && (original.status == DraftStatus.DISCARDED || family.status == DraftStatus.DISCARDED || media.hasAdopted(draftId))) {
            throw BusinessException(HttpStatus.CONFLICT,"CONFLICT","종결된 테마의 장면을 다시 생성할 수 없습니다.")
        }
        val draft = original.regenerate(UUID.randomUUID(), author, now(), targets)
        repository.insert(draft)
        return draft
    }

    @Transactional(readOnly = true)
    fun list(status: DraftStatus?, source: ThemeDraftSource?, page: Int, size: Int, grade: ThemeGrade? = null,
        weekStart: LocalDate? = null, hideDiscarded: Boolean = false, comparisonPending: Boolean = false): ThemeDraftViewPage {
        val result = repository.findPage(status, source, page, size, grade, weekStart, hideDiscarded, comparisonPending)
        return ThemeDraftViewPage(result.items.map(::view), result.page, result.size, result.totalElements)
    }

    @Transactional(readOnly = true)
    fun get(draftId: UUID): ThemeDraft = repository.findById(draftId) ?: notFound()

    @Transactional(readOnly = true, isolation = org.springframework.transaction.annotation.Isolation.REPEATABLE_READ)
    fun reviewPage(filter: ThemeDraftReviewFilter, page: Int, size: Int): ThemeDraftReviewPage {
        val result = repository.reviewPage(filter, page, size)
        return result.copy(items = result.items.map { it.copy(thumbnailUrl = assetUrls.url(it.thumbnailUrl)) })
    }

    /**
     * 채택 (state-diagram 3.5.1): 초안 행을 잠그고 READY가 아니면 409. 미션 5개(DRAFT, source LLM_THEME, 장면 키·움직임)와
     * 테마(DRAFT, 생각 열기 위치 비움, 결정적 단서 계산)를 같은 트랜잭션에 만들고 ADOPTED. 자동 게시 없음(P19)
     */
    @Transactional
    fun adopt(draftId: UUID, author: UUID, expected: LocalDate? = null, supplied: Boolean = false): AdminWeeklyTheme {
        val root = media.rootId(draftId)
        val state = planner.lockDraftEdits(root)
        if (state.status == DraftStatus.DISCARDED || media.hasAdopted(draftId)) {
            throw BusinessException(HttpStatus.CONFLICT,"CONFLICT","이미 버리거나 채택한 테마입니다.")
        }
        planner.requireExpected(state,expected,supplied)
        val effectiveWeek = state.plannedWeek ?: state.generationWeek
        planner.requireOpen(state.grade,effectiveWeek)
        val draft = repository.findById(draftId, lock = true) ?: notFound()
        draft.requireAdoptable()
        if (media.hasPendingGeneration(draftId)) planner.stale("영상 생성이 끝난 뒤 채택해 주세요.")
        val output = checkNotNull(media.selectedOutput(draft)) { "READY 초안에 생성 결과 없음" }
        val standards = missionService.standards(draft.input.missions.flatMap { it.standardCodes })
        if (output !== draft.output) {
            val failures = ThemeDraftRules.learningFailures(output, draft.input, draft.grade, standards)
            if (failures.isNotEmpty()) throw BusinessException(HttpStatus.CONFLICT, "CONFLICT",
                "선택본 조합을 채택할 수 없습니다.", failures.joinToString())
        }
        val missionIds = ThemeDraftRules.adoptedMissions(output, draft.input, draft.grade, standards, author).associate {
            it.day to missionService.createFromDraft(it.command, it.rubric, MissionSource.LLM_THEME)
        }
        val theme = themeAdminService.create(author, ThemeDraftRules.themeContent(output, draft.grade, effectiveWeek, missionIds))
        planner.clearDraft(root, state)
        draft.adopt(theme.themeId, now())
        media.freeze(draftId)
        repository.updateState(draft)
        return theme.copy(generationWeek = draft.weekStart)
    }

    /** 버리기: READY·CHECK_FAILED·FAILED만, 아니면 409 */
    @Transactional
    fun discard(draftId: UUID, expected: LocalDate? = null, supplied: Boolean = false): ThemeDraft {
        val root = media.rootId(draftId)
        val familyState = planner.lockDraftEdits(root)
        if (draftId != root && (familyState.status == DraftStatus.DISCARDED || media.hasAdopted(draftId) || media.isSelectedSource(draftId))) {
            throw BusinessException(HttpStatus.CONFLICT,"CONFLICT","종결된 테마 또는 현재 선택에 쓰인 장면은 버릴 수 없습니다.")
        }
        if (draftId == root && media.hasAdopted(draftId)) {
            throw BusinessException(HttpStatus.CONFLICT,"CONFLICT","이미 채택한 테마입니다.")
        }
        val state = if (draftId == root) familyState else planner.state(draftId)
        planner.requireExpected(familyState,expected,supplied)
        val draft = repository.findById(draftId, lock = true) ?: notFound()
        if (state.status == DraftStatus.READY && media.hasPendingGeneration(draftId)) planner.stale("영상 생성이 끝난 뒤 버려 주세요.")
        draft.discard(now())
        media.freeze(draftId)
        planner.clearDraft(draftId,state)
        repository.updateState(draft)
        return draft
    }

    /**
     * 생성 1회 (state-diagram 3.5.1): 점유할 초안이 없으면 false. 점유는 문장 하나로 커밋하고 ai 호출은 트랜잭션 밖(16분 동안 DB 연결을
     * 잡지 않음), 저장은 점유한 리스가 그대로일 때만(작업이 중간에 죽으면 리스가 지나 다른 레플리카가 다시 맡고 그 시도는 세지 않음)
     */
    fun generateNext(now: Instant): Boolean {
        val claimedAt = now.truncatedTo(ChronoUnit.MICROS)
        val draft = repository.claimNext(claimedAt, claimedAt.plus(properties.themeDraft.lease)) ?: return false
        val lease = checkNotNull(draft.leaseUntil)
        val standards = missionService.standards(draft.input.missions.flatMap { it.standardCodes })
        val result = attempt(draft, standards)
        draft.recordAttempt(result, maxAttempts, now())
        if (!repository.saveAttempt(draft, lease)) {
            log.warn("theme draft {} lease changed before save; attempt discarded", draft.id)
        }
        return true
    }

    /** 초안 응답: 장면 7개의 그림·영상은 presigned URL(AssetUrls), 생성 결과가 없으면 draft null·scenes 빈 배열 */
    fun view(draft: ThemeDraft): ThemeDraftView {
        val output = media.selectedOutput(draft)
        val programming = if (draft.input.regenerate == null || draft.status == DraftStatus.ADOPTED) planner.state(draft.id)
            else planner.state(media.rootId(draft.id))
        return ThemeDraftView(
            draftId = draft.id,
            status = draft.status,
            source = draft.source,
            grade = draft.grade,
            weekStart = draft.weekStart,
            attempts = draft.attempts,
            maxAttempts = maxAttempts,
            input = draft.input,
            checkResults = draft.checkResults,
            draft = output?.let { ThemeDraftContent(it.theme, it.missions, it.dialogues, it.warnings) },
            scenes = output?.let { o ->
                ThemeDraftRules.SCENES.map { ThemeDraftScene(it, assetUrls.url(o.images[it]), assetUrls.url(o.videos[it]), o.motions[it]) }
            }.orEmpty(),
            failureCode = draft.failureCode,
            versions = draft.versions,
            themeId = draft.themeId,
            requestedBy = draft.requestedBy,
            createdAt = draft.createdAt,
            updatedAt = draft.updatedAt,
            regenerableTargets = draft.regenerableTargets,
            plannedWeek = programming.plannedWeek,
            weekLocked = programming.weekLocked,
            adoptionWeekLocked = programming.adoptionWeekLocked,
        )
    }

    /**
     * ai 200의 failure는 검사 실패 그대로, failure가 없으면 learning 검사(실패는 LEARNING 한 묶음).
     * 부분 다시 생성(#537)인데 원래 초안이나 그 output·regen이 없으면 ai를 부르지 않고 LEARNING `BASE_MISSING` 검사 실패
     */
    private fun attempt(draft: ThemeDraft, standards: Map<String, AchievementStandard>): ThemeDraftAttempt {
        val regenerate = draft.input.regenerate?.let { spec ->
            val base = repository.findById(spec.baseDraftId)?.output?.takeIf { it.regen != null }
                ?: return ThemeDraftAttempt.CheckFailed(null, listOf(ThemeFailure(ThemeDraft.LEARNING,
                    listOf("${ThemeDraftRules.BASE_MISSING} 원래 초안 ${spec.baseDraftId}의 생성 결과·재료(regen) 없음"))), null)
            AiThemeRegenerate(spec.targets, base)
        }
        val response = try {
            aiClient.generate(aiRequest(draft, standards, regenerate))
        } catch (error: AiCallException) {
            log.warn("theme draft {} ai call failed: {}", draft.id, error.failureCode)
            return ThemeDraftAttempt.AiFailed(error.failureCode)
        }
        val output = response.output()
        response.failure?.let { return ThemeDraftAttempt.CheckFailed(output, listOf(it), response.versions) }
        val reasons = ThemeDraftRules.learningFailures(output, draft.input, draft.grade, standards)
        return if (reasons.isEmpty()) {
            ThemeDraftAttempt.Passed(output, response.versions)
        } else {
            ThemeDraftAttempt.CheckFailed(output, listOf(ThemeFailure(ThemeDraft.LEARNING, reasons)), response.versions)
        }
    }

    /**
     * ai 입력: 학년(gradeMin = gradeMax)·적용 주·주제, 유형마다 성취기준 문장·표준 요소·입력 방식, 이전 실패. 학생 정보 없음.
     * 부분 다시 생성이면 대상과 원래 초안 output(#537)
     */
    private fun aiRequest(draft: ThemeDraft, standards: Map<String, AchievementStandard>, regenerate: AiThemeRegenerate?) = AiThemeDraftRequest(
        gradeMin = draft.grade.grade,
        gradeMax = draft.grade.grade,
        weekStart = draft.weekStart,
        topic = draft.input.topic,
        missions = draft.input.missions.map { mission ->
            AiThemeMission(
                thinkingType = mission.thinkingType,
                inputType = mission.inputType,
                standards = mission.standardCodes.map { AiThemeStandard(it, standards.getValue(it).statement) },
                elementCodes = DraftRules.elementCodes(mission.thinkingType, mission.inputType).map { AiThemeElementCode(it.code, it.label, it.description) },
            )
        },
        previousFailures = draft.previousFailures,
        regenerate = regenerate,
    )

    /**
     * 유형 5개 입력: 고른 유형은 그대로, 비운 유형은 자동 규칙(그 학년·학기 후보 풀, 그 학년 최근 4주 초안 코드는 피함). 고를 수 없으면 null.
     * 주제가 있는 관리자 요청도 같은 규칙(#536). 주제가 없으면(주간 자동·주제 없이 온 관리자 요청) 주제 씨앗을 골라 넣는다
     * (ThemeTopicSeeds, 관리자가 쓴 주제는 그대로)
     */
    private fun autoInput(grade: ThemeGrade, weekStart: LocalDate, topic: String?, requested: List<ThemeMissionInput>): ThemeDraftInput? {
        val chosenTopic = topic ?: seedTopic(grade, weekStart)
        val missing = ThemeDraftRules.DAY_TYPES.values.any { type -> requested.none { it.thinkingType == type } }
        val pools = if (missing) {
            val band = ThemeDraftRules.gradeBand(grade)
            val semester = ThemeSemester.of(grade, weekStart)
            val byBand = ThemeDraftRules.AUTO_SUBJECTS.associateWith { missionService.standardsOf(it, band) }
            byBand.filter { (_, table) -> table.isNotEmpty() && table.none { semesters.covers(it.code, semester) } }.keys.forEach {
                log.warn("theme auto standards: no {} standard for {}, using earlier semesters, or grade band {} if none", it, semester, band)
            }
            ThemeDraftRules.candidatePools(byBand, semesters, semester, ThemeSemester.soFar(grade, weekStart))
        } else {
            emptyMap()
        }
        // 오래된 것부터(조회가 created_at 순): 모든 후보가 최근 코드면 가장 오래전에 쓴 것을 고름
        val recent = if (missing) {
            repository.findInputs(grade, weekStart.minusWeeks(ThemeDraftRules.RECENT_WEEKS), weekStart)
                .flatMap { it.missions }.flatMap { it.standardCodes }
        } else {
            emptyList()
        }
        return ThemeDraftRules.autoStandards(grade, requested, recent, pools, Random.Default)?.let { ThemeDraftInput(chosenTopic, it) }
    }

    /**
     * 같은 학년 직전 주 초안 줄거리 종류를 빼고 종류를 고른 뒤, 같은 학년 최근(사건 개수만큼의 주) 장소·사건, 같은 주 다른 초안 사건,
     * 같은 학년 최근 4주 역할을 빼고 장소 → 사건 → 역할을 고름(#634, #782 장소 목록 기준안, 초안 상태 무관)
     */
    private fun seedTopic(grade: ThemeGrade, weekStart: LocalDate): String {
        fun topics(weeks: Long) = repository.findInputs(grade, weekStart.minusWeeks(weeks), weekStart).mapNotNull { it.topic }
        val sameWeek = repository.findWeekInputs(weekStart).mapNotNull { it.topic }.toSet()
        return ThemeTopicSeeds.choose(
            weekStart, topics(ThemeTopicSeeds.RECENT_WEEKS), sameWeek, Random.Default,
            lastWeekTopics = topics(1), roleTopics = topics(ThemeTopicSeeds.ROLE_WEEKS),
        )
    }

    /** 적용 주는 월요일이고 이번 주(KST) 이후 */
    private fun requireWeek(weekStart: LocalDate) {
        if (weekStart.dayOfWeek != DayOfWeek.MONDAY) invalid("weekStart는 월요일 날짜")
        if (weekStart.isBefore(ThemeWeek.startOf(LocalDate.now(clock)))) invalid("weekStart는 이번 주 이후")
    }

    private fun invalid(detail: String): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "요청 오류", detail)

    private fun notFound(): Nothing = throw BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "초안 없음")

    private fun now(): Instant = Instant.now(clock).truncatedTo(ChronoUnit.MICROS)

    companion object {
        private val log = LoggerFactory.getLogger(ThemeDraftService::class.java)

        /** 주제 길이 상한 (기준안, learning.md #438 절) */
        const val MAX_TOPIC = 100
    }
}
