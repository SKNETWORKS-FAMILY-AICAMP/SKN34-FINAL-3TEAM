package com.sagomungchi.learning.theme.service

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning.mission.service.MissionService
import com.sagomungchi.learning.theme.domain.AdminWeeklyTheme
import com.sagomungchi.learning.theme.domain.AdminWeeklyThemePage
import com.sagomungchi.learning.theme.domain.GradeBand
import com.sagomungchi.learning.theme.domain.ThemeDay
import com.sagomungchi.learning.theme.domain.ThemeDayMission
import com.sagomungchi.learning.theme.domain.ThemePublishCheck
import com.sagomungchi.learning.theme.domain.ThemePublishError
import com.sagomungchi.learning.theme.domain.WeeklyTheme
import com.sagomungchi.learning.theme.domain.WeeklyThemePublishIncompleteException
import com.sagomungchi.learning.theme.domain.WeeklyThemeStatus
import com.sagomungchi.learning.theme.repository.ThemeContent
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
 * 관리자 주간 테마 (FN-ADM-22, api-spec 2.8·4.1, state-diagram 3.5). 미션과 같은 작성 → 검토 요청 → 게시 → 중단.
 * 수정은 새 버전을 만들어 현재본으로 두고, 게시 중이면 재검토·재게시 전까지 학생에게는 게시본이 보인다.
 * 쓰기는 테마 행을 잠가 같은 테마 요청을 차례로 처리한다
 */
@Service
class WeeklyThemeAdminService(
    private val repository: WeeklyThemeRepository,
    private val missionService: MissionService,
    private val clock: Clock,
) {
    @Transactional(readOnly = true)
    fun list(gradeBand: GradeBand?, weekStart: LocalDate?, status: WeeklyThemeStatus?, page: Int, size: Int): AdminWeeklyThemePage =
        AdminWeeklyThemePage(
            items = repository.findIds(gradeBand, weekStart, status, page, size).map(::get),
            page = page,
            size = size,
            totalElements = repository.count(gradeBand, weekStart, status),
        )

    @Transactional(readOnly = true)
    fun get(themeId: UUID): AdminWeeklyTheme = view(header(themeId))

    /** 작성: DRAFT·버전 1. 없는 미션은 400 */
    @Transactional
    fun create(author: UUID, content: ThemeContent): AdminWeeklyTheme {
        requireMissions(content)
        val id = UUID.randomUUID()
        repository.create(id, content, WeeklyThemeStatus.DRAFT, author, now())
        return get(id)
    }

    /** 수정: 새 버전을 현재본으로. 게시 중 학년군·주 변경은 409, 검토 중 수정은 DRAFT로 */
    @Transactional
    fun update(themeId: UUID, author: UUID, content: ThemeContent): AdminWeeklyTheme {
        val header = header(themeId, lock = true)
        val theme = entity(header)
        theme.requireEditable(content.gradeBand, content.weekStart)
        requireMissions(content)
        theme.edited()
        repository.appendVersion(themeId, header.currentVersion + 1, content, theme.status, author, now())
        return get(themeId)
    }

    /** 검토 요청: 현재본을 검토 요청 버전으로. 상태 전이가 안 되면 409 CONFLICT */
    @Transactional
    fun requestReview(themeId: UUID): AdminWeeklyTheme {
        val theme = entity(header(themeId, lock = true))
        theme.requestReview()
        repository.markReviewRequested(themeId, theme.status, now())
        return get(themeId)
    }

    /**
     * 게시·재게시: 검토 요청한 현재본만(아니면 409 CONFLICT). 게시 검사(게시 미션·시연 전용 제외·학년군 전체·다섯 유형 1개씩·
     * 같은 학년군·주 게시 1개)를 모두 모아 실패하면 422 WEEKLY_THEME_PUBLISH_INCOMPLETE. 동시 게시가 부분 UK에 걸려도 같은 422
     */
    @Transactional
    fun publish(themeId: UUID): AdminWeeklyTheme {
        val header = header(themeId, lock = true)
        val theme = entity(header)
        theme.requirePublishable()
        val days = repository.findDays(header.currentVersionId).map { ThemeDayMission(ThemeDay.ofNumber(it.dayOfWeek), it.missionId) }
        val missions = days.mapNotNull { day -> missionService.publishedView(day.missionId)?.let { day.missionId to it } }.toMap()
        theme.publish(ThemePublishCheck.errors(header.gradeBand, days, missions,
            repository.existsOtherPublished(themeId, header.gradeBand, header.weekStart)))
        try {
            repository.publish(themeId, now())
        } catch (_: DuplicateKeyException) {
            throw WeeklyThemePublishIncompleteException(listOf(WEEK_TAKEN))
        }
        return get(themeId)
    }

    /** 게시 중단: 게시 중이 아니면 409. 진행 중 시도는 그대로 이어함 */
    @Transactional
    fun unpublish(themeId: UUID): AdminWeeklyTheme {
        val theme = entity(header(themeId, lock = true))
        theme.unpublish()
        repository.updateStatus(themeId, theme.status, now())
        return get(themeId)
    }

    private fun requireMissions(content: ThemeContent) {
        if (!repository.missionsExist(content.days.map { it.missionId })) {
            throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "요청 오류", "없는 미션이 있음")
        }
    }

    private fun header(themeId: UUID, lock: Boolean = false): ThemeHeader =
        repository.findHeader(themeId, lock) ?: throw BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "주간 테마 없음")

    private fun entity(h: ThemeHeader) =
        WeeklyTheme(h.id, h.status, h.gradeBand, h.weekStart, h.currentVersion, h.publishedVersion, h.reviewVersion)

    private fun view(h: ThemeHeader): AdminWeeklyTheme {
        val version = repository.findVersion(h.currentVersionId)
        return AdminWeeklyTheme(
            themeId = h.id,
            gradeBand = h.gradeBand,
            weekStart = h.weekStart,
            status = h.status,
            version = h.currentVersion,
            publishedVersion = h.publishedVersion,
            reviewRequested = entity(h).reviewRequested,
            title = version.title,
            intro = version.intro,
            days = repository.findDays(h.currentVersionId).map { ThemeDayMission(ThemeDay.ofNumber(it.dayOfWeek), it.missionId) },
            publishedAt = h.publishedAt,
            createdAt = h.createdAt,
            updatedAt = h.updatedAt,
        )
    }

    private fun now(): Instant = Instant.now(clock).truncatedTo(ChronoUnit.MICROS)

    private companion object {
        val WEEK_TAKEN = ThemePublishError("WEEK_ALREADY_PUBLISHED", "같은 학년군·주에 이미 게시된 테마가 있어요")
    }
}
