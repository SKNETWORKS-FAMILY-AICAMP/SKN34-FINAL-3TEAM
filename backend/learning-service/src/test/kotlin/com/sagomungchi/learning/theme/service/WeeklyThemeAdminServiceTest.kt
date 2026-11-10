package com.sagomungchi.learning.theme.service

import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.exception.errorCodeOf
import com.sagomungchi.learning._common.exception.httpStatusOf
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning.theme.domain.GradeBand
import com.sagomungchi.learning.theme.domain.ThemeDay
import com.sagomungchi.learning.theme.domain.ThemeDayMission
import com.sagomungchi.learning.theme.domain.WeeklyThemePublishIncompleteException
import com.sagomungchi.learning.theme.domain.WeeklyThemeStatus
import com.sagomungchi.learning.theme.domain.ThemeContent
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.http.HttpStatus
import org.springframework.jdbc.core.JdbcTemplate
import java.time.LocalDate
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** 관리자 주간 테마 (#385, FN-ADM-22, state-diagram 3.5): 버전·상태 전이·게시 검사 */
class WeeklyThemeAdminServiceTest : PostgresRepositoryTest() {
    @Autowired lateinit var service: WeeklyThemeAdminService
    @Autowired lateinit var studentService: WeeklyThemeService
    @Autowired lateinit var jdbc: JdbcTemplate

    private lateinit var rows: TestRows
    private lateinit var missions: List<UUID>
    private val admin = UUID.randomUUID()

    @BeforeEach
    fun seed() {
        rows = TestRows(jdbc)
        missions = rows.themeMissions().map { it.id }
    }

    private fun content(
        ids: List<UUID> = missions,
        title: String = "물의 여행",
        week: LocalDate = WEEK,
        band: GradeBand = GradeBand.G3_4,
    ) = ThemeContent(band, week, title, "소개", ids.mapIndexed { index, id -> ThemeDayMission(ThemeDay.entries[index], id) })

    private fun published(content: ThemeContent = content()): UUID {
        val id = service.create(admin, content).themeId
        service.requestReview(id)
        service.publish(id)
        return id
    }

    private fun publishErrors(id: UUID): List<String> {
        service.requestReview(id)
        return assertThrows<WeeklyThemePublishIncompleteException> { service.publish(id) }.errors.map { it.code }
    }

    private fun assertError(status: HttpStatus, code: String, block: () -> Unit) {
        val error = assertThrows<RuntimeException> { block() }
        assertEquals(status to code, httpStatusOf(error) to errorCodeOf(error))
    }

    @Test
    fun `작성은 DRAFT·버전 1, 검토 요청 뒤 게시하면 게시본이 현재본`() {
        val created = service.create(admin, content())
        assertEquals(WeeklyThemeStatus.DRAFT to 1, created.status to created.version)
        assertNull(created.publishedVersion)
        assertFalse(created.reviewRequested)
        assertEquals(missions, created.days.map { it.missionId })

        val reviewing = service.requestReview(created.themeId)
        assertEquals(WeeklyThemeStatus.REVIEW_REQUIRED, reviewing.status)
        assertTrue(reviewing.reviewRequested)

        val live = service.publish(created.themeId)
        assertEquals(WeeklyThemeStatus.PUBLISHED to 1, live.status to live.publishedVersion)
        assertTrue(live.publishedAt != null)
        assertEquals(1L, service.list(GradeBand.G3_4, WEEK, WeeklyThemeStatus.PUBLISHED, 0, 20).totalElements)
        assertEquals(0L, service.list(GradeBand.G5_6, null, null, 0, 20).totalElements)
    }

    @Test
    fun `검토 요청 없이 게시·게시 아닌 중단·두 번 검토 요청은 409 CONFLICT`() {
        val id = service.create(admin, content()).themeId
        assertError(HttpStatus.CONFLICT, "CONFLICT") { service.publish(id) }
        assertError(HttpStatus.CONFLICT, "CONFLICT") { service.unpublish(id) }
        service.requestReview(id)
        assertError(HttpStatus.CONFLICT, "CONFLICT") { service.requestReview(id) }
    }

    @Test
    fun `검토 중 수정은 DRAFT로 돌아가 검토 요청한 버전이 아니라 게시할 수 없음`() {
        val id = service.create(admin, content()).themeId
        service.requestReview(id)

        val edited = service.update(id, admin, content(title = "고친 제목"))

        assertEquals(WeeklyThemeStatus.DRAFT to 2, edited.status to edited.version)
        assertFalse(edited.reviewRequested)
        assertError(HttpStatus.CONFLICT, "CONFLICT") { service.publish(id) }
    }

    @Test
    fun `게시 중 수정은 재검토·재게시 전까지 학생에게 게시본, 학년군·주 변경은 409`() {
        val id = published()

        val edited = service.update(id, admin, content(title = "새 제목"))
        assertEquals(WeeklyThemeStatus.PUBLISHED, edited.status)
        assertEquals(2 to 1, edited.version to edited.publishedVersion)
        assertEquals("물의 여행", studentService.current(UUID.randomUUID(), GradeBand.G3_4, WEEK).title)
        assertError(HttpStatus.CONFLICT, "CONFLICT") { service.update(id, admin, content(week = WEEK.plusWeeks(1))) }
        assertError(HttpStatus.CONFLICT, "CONFLICT") { service.update(id, admin, content(band = GradeBand.G5_6)) }

        service.requestReview(id)
        val republished = service.publish(id)

        assertEquals(WeeklyThemeStatus.PUBLISHED to 2, republished.status to republished.publishedVersion)
        assertEquals("새 제목", studentService.current(UUID.randomUUID(), GradeBand.G3_4, WEEK).title)
    }

    @Test
    fun `게시 검사는 실패를 모두 모아 422 WEEKLY_THEME_PUBLISH_INCOMPLETE`() {
        val draft = rows.mission(status = "DRAFT", grade = 3, gradeMax = 4, thinkingType = "REFLECT").id
        val id = service.create(admin, content(missions.take(3) + draft)).themeId

        assertEquals(listOf("DAYS_INCOMPLETE", "MISSION_NOT_PUBLISHED", "THINKING_TYPES"), publishErrors(id))
    }

    @Test
    fun `학년군 전체를 덮지 않거나 시연 전용이거나 유형이 겹치면 게시 불가`() {
        val third = rows.mission(grade = 3, thinkingType = "REFLECT").id
        val demo = rows.mission(grade = 3, gradeMax = 4, thinkingType = "SOLVE", demoOnly = true).id
        val id = service.create(admin, content(missions.take(3) + demo + third)).themeId

        assertEquals(listOf("MISSION_DEMO_ONLY", "GRADE_BAND_MISMATCH"), publishErrors(id))

        val sameType = rows.mission(grade = 3, gradeMax = 4, thinkingType = "ANALYZE").id
        val other = service.create(admin, content(missions.take(4) + sameType, week = WEEK.plusWeeks(1))).themeId
        assertEquals(listOf("THINKING_TYPES"), publishErrors(other))
    }

    @Test
    fun `초3~4 학년군에는 논술 미션을 넣을 수 없음`() {
        val essay = rows.mission(grade = 3, gradeMax = 6, thinkingType = "REFLECT", inputType = "ESSAY").id
        val id = service.create(admin, content(missions.take(4) + essay)).themeId

        assertEquals(listOf("GRADE_BAND_MISMATCH"), publishErrors(id))
    }

    @Test
    fun `같은 학년군·주에 게시 테마는 하나, 다른 주·학년군은 따로`() {
        published()
        val second = service.create(admin, content(title = "둘째")).themeId

        assertEquals(listOf("WEEK_ALREADY_PUBLISHED"), publishErrors(second))
        published(content(week = WEEK.plusWeeks(1)))
    }

    @Test
    fun `중단하면 학생에게서 빠지고 이전 게시 테마를 다시 씀, 다시 게시하려면 검토 요청부터`() {
        val earlier = published(content(title = "지난주"))
        val id = published(content(title = "이번 주", week = WEEK.plusWeeks(1)))

        val stopped = service.unpublish(id)

        assertEquals(WeeklyThemeStatus.UNPUBLISHED, stopped.status)
        val view = studentService.current(UUID.randomUUID(), GradeBand.G3_4, WEEK.plusWeeks(1))
        assertEquals(earlier to true, view.themeId to view.reused)
        assertError(HttpStatus.CONFLICT, "CONFLICT") { service.publish(id) }
        service.requestReview(id)
        assertEquals(WeeklyThemeStatus.PUBLISHED, service.publish(id).status)
    }

    @Test
    fun `없는 테마는 404, 없는 미션은 400`() {
        assertError(HttpStatus.NOT_FOUND, "NOT_FOUND") { service.get(UUID.randomUUID()) }
        assertError(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED") { service.create(admin, content(missions.take(4) + UUID.randomUUID())) }
    }

    private companion object {
        val WEEK: LocalDate = LocalDate.of(2026, 11, 9)
    }
}
