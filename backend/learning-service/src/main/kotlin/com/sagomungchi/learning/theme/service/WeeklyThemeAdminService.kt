package com.sagomungchi.learning.theme.service

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.storage.AssetUrls
import com.sagomungchi.learning.mission.service.MissionService
import com.sagomungchi.learning.theme.domain.AdminWeeklyTheme
import com.sagomungchi.learning.theme.domain.AdminThemeDay
import com.sagomungchi.learning.theme.domain.AdminWeeklyThemePage
import com.sagomungchi.learning.theme.domain.ThemeAnswerRules
import com.sagomungchi.learning.theme.domain.ThemeCarryOver
import com.sagomungchi.learning.theme.domain.ThemeGrade
import com.sagomungchi.learning.theme.domain.ThemeDay
import com.sagomungchi.learning.theme.domain.ThemeDayMission
import com.sagomungchi.learning.theme.domain.ThemePublishCheck
import com.sagomungchi.learning.theme.domain.ThemePublishError
import com.sagomungchi.learning.theme.domain.WeeklyTheme
import com.sagomungchi.learning.theme.domain.WeeklyThemePublishIncompleteException
import com.sagomungchi.learning.theme.domain.WeeklyThemeStatus
import com.sagomungchi.learning.theme.domain.ThemeContent
import com.sagomungchi.learning.theme.repository.ThemeHeader
import com.sagomungchi.learning.theme.repository.WeeklyThemeRepository
import org.springframework.dao.DuplicateKeyException
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.Clock
import java.time.Instant
import java.time.LocalDate
import java.time.temporal.ChronoUnit
import java.util.UUID

/**
 * 관리자 주간 테마. 학년별 편성·제출·게시를 직렬화하고, 게시 버전마다 요일별 미션과 기준표를 고정한다.
 * #438: 이야기·정답 구조·요일 칸은 수정 때 본문에 없으면 이전 버전에서 이어받고(ThemeCarryOver), 합친 결과의 정답 논리와
 * 생각 열기 위치를 저장 전에 검사한다(400)
 */
@Service
class WeeklyThemeAdminService(
    private val repository: WeeklyThemeRepository,
    private val missionService: MissionService,
    private val clock: Clock,
    private val assetUrls: AssetUrls,
    private val planner: ThemeWeekPlanner,
) {
    @Transactional(readOnly = true)
    fun list(grade: ThemeGrade?, weekStart: LocalDate?, status: WeeklyThemeStatus?, page: Int, size: Int): AdminWeeklyThemePage =
        AdminWeeklyThemePage(
            items = repository.findIds(grade, weekStart, status, page, size).map(::get),
            page = page,
            size = size,
            totalElements = repository.count(grade, weekStart, status),
        )

    @Transactional(readOnly = true)
    fun get(themeId: UUID): AdminWeeklyTheme = view(header(themeId))

    /** 그 학년·주에 게시 테마가 있음. 테마 초안 주간 자동 생성이 건너뛸 학년을 고름 (#438, 사용자 결정 2026-11-10) */
    @Transactional(readOnly = true)
    fun publishedExists(grade: ThemeGrade, weekStart: LocalDate): Boolean = repository.existsPublished(grade, weekStart)

    /** 작성: DRAFT·버전 1. 없는 미션은 400 */
    @Transactional
    fun create(author: UUID, content: ThemeContent): AdminWeeklyTheme {
        planner.lockGrades(content.grade)
        planner.requireOpen(content.grade, content.weekStart)
        val normalized = ThemeCarryOver.normalize(content)
        requireMissions(normalized)
        requireStory(normalized)
        val id = UUID.randomUUID()
        repository.create(id, normalized, WeeklyThemeStatus.DRAFT, author, now())
        return get(id)
    }

    /** 새 편집본을 저장한다. 게시 중에는 기존 게시본과 편성을 유지한다. */
    @Transactional
    fun update(themeId: UUID, author: UUID, content: ThemeContent, expectedVersion: Int? = null): AdminWeeklyTheme {
        val header = writableHeader(themeId, content.grade, expectedVersion)
        val scheduleChanged = header.grade != content.grade || header.weekStart != content.weekStart
        if (scheduleChanged) {
            if (header.status == WeeklyThemeStatus.PUBLISHED) planner.locked()
            planner.requireOpen(content.grade, content.weekStart)
            if (planner.generationWeek(themeId) != null) {
                throw BusinessException(HttpStatus.CONFLICT, "THEME_SCHEDULE_LOCKED", "채택한 테마의 학년과 적용 주는 변경할 수 없습니다.")
            }
        }
        val theme = entity(header)
        val merged = ThemeCarryOver.merge(repository.findContent(header, header.currentVersionId), content)
        requireMissions(merged)
        requireStory(merged)
        theme.edited()
        repository.appendVersion(themeId, header.currentVersion + 1, merged, theme.status, author, now())
        return get(themeId)
    }

    /** 검토 요청: 현재본을 검토 요청 버전으로. 상태 전이가 안 되면 409 CONFLICT */
    @Transactional
    fun requestReview(themeId: UUID, expectedVersion: Int? = null): AdminWeeklyTheme {
        val theme = entity(writableHeader(themeId, expectedVersion = expectedVersion))
        theme.requestReview()
        repository.markReviewRequested(themeId, theme.status, now())
        return get(themeId)
    }

    /**
     * 최종 게시: 검토 요청한 현재본만(아니면 409 CONFLICT). 같은 학년·주에 다른 게시 테마가 있으면 409 WEEK_LOCKED,
     * 버전·편성 후보가 바뀌었으면 409 PLAN_CONFLICT. 게시 검사(게시 미션·시연 전용 제외·테마 학년 포함·다섯 유형 1개씩)를
     * 모두 모아 실패하면 422 WEEKLY_THEME_PUBLISH_INCOMPLETE. 동시 게시가 부분 UK에 걸리면 같은 422(WEEK_ALREADY_PUBLISHED)
     */
    @Transactional
    fun publish(themeId: UUID, expectedVersion: Int? = null, expectedPlan: UUID? = null, checkPlan: Boolean = false): AdminWeeklyTheme {
        val header = writableHeader(themeId, expectedVersion = expectedVersion)
        if (checkPlan) planner.requireOccupant(header.grade,header.weekStart,expectedPlan)
        val theme = entity(header)
        theme.requirePublishable()
        planner.lockMissions(header.currentVersionId)
        val dayRows = repository.findDays(header.currentVersionId)
        val days = dayRows.map { ThemeDayMission(ThemeDay.ofNumber(it.dayOfWeek), it.missionId) }
        val missions = dayRows.mapNotNull { day ->
            val published = missionService.publishedView(day.missionId) ?: return@mapNotNull null
            day.missionId to (day.missionVersionId?.let(missionService::getVersion) ?: published)
        }.toMap()
        theme.publish(ThemePublishCheck.errors(header.grade, days, missions,
            repository.existsOtherPublished(themeId, header.grade, header.weekStart)))
        try {
            repository.publish(themeId, now())
            planner.finishPublication(header.currentVersionId,header.grade,header.weekStart)
        } catch (_: DuplicateKeyException) {
            throw WeeklyThemePublishIncompleteException(listOf(WEEK_TAKEN))
        }
        return get(themeId)
    }

    /** 제공을 중단해도 게시 버전은 보관한다. 다시 제공하려면 현재본을 다시 검토 요청해야 한다. */
    @Transactional
    fun unpublish(themeId: UUID, expectedPublishedVersion: Int? = null): AdminWeeklyTheme {
        val header = writableHeader(themeId)
        if (expectedPublishedVersion != null && header.publishedVersion != expectedPublishedVersion) {
            planner.stale("학생에게 제공 중인 테마 버전이 바뀌었습니다.")
        }
        val theme = entity(header)
        theme.unpublish()
        repository.updateStatus(themeId, theme.status, now())
        return get(themeId)
    }

    private fun requireMissions(content: ThemeContent) {
        if (!repository.missionsExist(content.days.map { it.missionId })) {
            throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "요청 오류", "없는 미션이 있음")
        }
    }

    /** 정답 논리와 요일 생각 열기 위치(그날 미션 현재 기준표의 순번). 위반은 모아서 400 */
    private fun requireStory(content: ThemeContent) {
        val errors = ThemeAnswerRules.errors(content.story, content.days) + content.days.flatMap { day ->
            val spots = day.hintSpots ?: return@flatMap emptyList()
            val seqs = missionService.hintQuestions(missionService.currentVersions(day.missionId).rubricVersionId).map { it.seq }.toSet()
            ThemeAnswerRules.hintSpotErrors(day.day, spots, seqs)
        }
        if (errors.isNotEmpty()) {
            throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "요청 오류", errors.joinToString("; "))
        }
    }

    private fun header(themeId: UUID, lock: Boolean = false): ThemeHeader =
        repository.findHeader(themeId, lock) ?: throw BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "주간 테마 없음")

    private fun writableHeader(themeId: UUID, destination: ThemeGrade? = null, expectedVersion: Int? = null): ThemeHeader {
        val before = header(themeId)
        planner.lockGrades(before.grade, destination ?: before.grade)
        val current = header(themeId, lock = true)
        if (current.grade != before.grade || current.weekStart != before.weekStart) planner.stale("테마의 학년 또는 주차가 바뀌었습니다.")
        if (current.status != WeeklyThemeStatus.PUBLISHED) planner.requireOpen(current.grade, current.weekStart)
        if (expectedVersion != null && current.currentVersion != expectedVersion) planner.stale("테마의 편집 버전이 바뀌었습니다.")
        return current
    }

    private fun entity(h: ThemeHeader) =
        WeeklyTheme(h.id, h.status, h.grade, h.weekStart, h.currentVersion, h.publishedVersion, h.reviewVersion)

    private fun view(h: ThemeHeader): AdminWeeklyTheme {
        val version = repository.findVersion(h.currentVersionId)
        val story = version.story
        return AdminWeeklyTheme(
            themeId = h.id,
            grade = h.grade,
            weekStart = h.weekStart,
            status = h.status,
            version = version.version,
            publishedVersion = h.publishedVersion,
            reviewRequested = entity(h).reviewRequested,
            title = version.title,
            intro = version.intro,
            days = repository.findDays(h.currentVersionId).map {
                AdminThemeDay(ThemeDay.ofNumber(it.dayOfWeek), it.missionId, it.clue, it.rulesOut, it.dialogue, it.hintSpots, it.videoUri,
                    videoUrl = assetUrls.url(it.videoUri), sceneImageUrl = assetUrls.url(it.sceneUri), clueFeature = it.clueFeature,
                    title = it.title, sceneMotion = it.sceneMotion)
            },
            publishedAt = h.publishedAt,
            createdAt = h.createdAt,
            updatedAt = h.updatedAt,
            outro = story.outro,
            introImageUri = story.introImageUri,
            outroImageUri = story.outroImageUri,
            introVideoUri = story.introVideoUri,
            outroVideoUri = story.outroVideoUri,
            introMotion = story.introMotion,
            outroMotion = story.outroMotion,
            bigQuestion = story.bigQuestion,
            candidates = story.candidates,
            answer = story.answer,
            answerClue = story.answerClue,
            introImageUrl = assetUrls.url(story.introImageUri),
            outroImageUrl = assetUrls.url(story.outroImageUri),
            introVideoUrl = assetUrls.url(story.introVideoUri),
            outroVideoUrl = assetUrls.url(story.outroVideoUri),
            features = story.features,
            weekLocked = repository.existsPublished(h.grade,h.weekStart),
            generationWeek = planner.generationWeek(h.id),
        )
    }

    private fun now(): Instant = Instant.now(clock).truncatedTo(ChronoUnit.MICROS)

    private companion object {
        val WEEK_TAKEN = ThemePublishError("WEEK_ALREADY_PUBLISHED", "같은 학년·주에 이미 게시된 테마가 있어요")
    }
}
