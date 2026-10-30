package com.sagomungchi.learning.attempt.service

import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.attempt.domain.DraftContent
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.http.HttpStatus
import org.springframework.jdbc.core.JdbcTemplate
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class AttemptServiceTest : PostgresRepositoryTest() {
    @Autowired lateinit var service: AttemptService
    @Autowired lateinit var jdbc: JdbcTemplate

    private lateinit var rows: TestRows
    private val student = UUID.randomUUID()

    @BeforeEach
    fun prepare() {
        rows = TestRows(jdbc)
        actAs(student)
    }

    @AfterEach
    fun clear() = UserContextHolder.clear()

    private fun actAs(studentId: UUID) =
        UserContextHolder.set(UserContext(null, "STUDENT", setOf(studentId.toString()), null))

    private fun assertError(status: HttpStatus, code: String, block: () -> Unit) {
        val error = assertThrows<BusinessException> { block() }
        assertEquals(status to code, error.status to error.code)
    }

    @Test
    fun `같은 미션을 두 번 시작하면 같은 시도, 처음에만 빈 초안 생성`() {
        val mission = rows.mission()

        val first = service.start(student, mission.id, grade = 3, demo = false)
        val second = service.start(student, mission.id, grade = 3, demo = false)

        assertTrue(first.created)
        assertFalse(second.created)
        assertEquals(first.attempt.id, second.attempt.id)
        assertEquals(mission.versionId to mission.rubricVersionId, first.attempt.missionVersionId to first.attempt.rubricVersionId)
        val draft = service.get(first.attempt.id).draft
        assertEquals(0 to DraftContent(emptyMap(), ""), draft.version to draft.content)
    }

    @Test
    fun `진행 중 시도는 미션이 공개 중단되거나 학년이 바뀌어도 이어함`() {
        val mission = rows.mission(grade = 3)
        val started = service.start(student, mission.id, grade = 3, demo = false)
        jdbc.update("UPDATE mission SET status = 'UNPUBLISHED' WHERE id = ?", mission.id)

        val resumed = service.start(student, mission.id, grade = 4, demo = false)

        assertEquals(started.attempt.id to 3, resumed.attempt.id to resumed.attempt.grade)
    }

    @Test
    fun `새 시도는 공개·학년·시연 범위의 미션만, 없는 미션은 404`() {
        val draft = rows.mission(status = "DRAFT")
        val demoOnly = rows.mission(demoOnly = true)
        val fifth = rows.mission(grade = 5)

        assertError(HttpStatus.CONFLICT, "MISSION_NOT_AVAILABLE") { service.start(student, draft.id, 3, false) }
        assertError(HttpStatus.CONFLICT, "MISSION_NOT_AVAILABLE") { service.start(student, demoOnly.id, 3, false) }
        assertError(HttpStatus.CONFLICT, "MISSION_NOT_AVAILABLE") { service.start(student, fifth.id, 3, false) }
        assertError(HttpStatus.NOT_FOUND, "NOT_FOUND") { service.start(student, UUID.randomUUID(), 3, false) }
        assertTrue(service.start(student, demoOnly.id, 3, true).created)
    }

    @Test
    fun `시도 상세는 새 버전이 공개돼도 시작 당시 버전의 미션`() {
        val mission = rows.mission(title = "처음 버전")
        val attempt = service.start(student, mission.id, 3, false).attempt
        val newer = rows.addVersion(mission.id, version = 2, title = "새 버전")
        jdbc.update("UPDATE mission SET current_version_id = ?, published_version_id = ? WHERE id = ?", newer, newer, mission.id)

        assertEquals("처음 버전", service.get(attempt.id).mission.title)
    }

    @Test
    fun `오래된 If-Match로 저장하면 409와 최신 초안, 덮어쓰지 않음`() {
        val attempt = service.start(student, rows.mission().id, 3, false).attempt
        val mine = DraftContent(mapOf("text" to "처음 쓴 답"), "메모")

        val saved = service.saveDraft(attempt.id, ifMatch = 0, content = mine)
        val conflict = assertThrows<DraftConflictException> {
            service.saveDraft(attempt.id, ifMatch = 0, content = DraftContent(mapOf("text" to "다른 화면"), ""))
        }

        assertEquals(1, saved.version)
        assertEquals("ATTEMPT_DRAFT_CONFLICT", conflict.code)
        assertEquals(1 to mine, conflict.latest.version to conflict.latest.content)
        assertEquals(saved, service.get(attempt.id).draft)
    }

    @Test
    fun `완료된 시도에는 초안·생각 열기 409, 다른 학생의 시도는 403`() {
        val attempt = service.start(student, rows.mission().id, 3, false).attempt
        jdbc.update("UPDATE attempt SET status = 'COMPLETED' WHERE id = ?", attempt.id)

        assertError(HttpStatus.CONFLICT, "ATTEMPT_CLOSED") { service.saveDraft(attempt.id, 0, DraftContent(emptyMap(), "")) }
        assertError(HttpStatus.CONFLICT, "ATTEMPT_CLOSED") { service.openHint(attempt.id) }

        actAs(UUID.randomUUID())
        assertError(HttpStatus.FORBIDDEN, "FORBIDDEN") { service.get(attempt.id) }
    }

    @Test
    fun `생각 열기는 seq 순으로, 다 열면 마지막 질문을 다시 주고 매번 기록`() {
        val mission = rows.mission(hints = listOf("첫 질문", "둘째 질문"))
        val attempt = service.start(student, mission.id, 3, false).attempt

        val opened = List(3) { service.openHint(attempt.id) }

        assertEquals(listOf(1, 2, 2), opened.map { it.question.seq })
        assertEquals(listOf("첫 질문", "둘째 질문", "둘째 질문"), opened.map { it.question.content })
        assertEquals(2, opened.first().total)
        assertTrue(service.get(attempt.id).helped)
        assertEquals(3, jdbc.queryForObject("SELECT count(*) FROM hint_usage WHERE attempt_id = ?", Int::class.java, attempt.id))
    }

    @Test
    fun `학생 범위 헤더가 대문자 UUID여도 본인 시도로 확인 (requireSelfStudent와 같은 UUID 비교)`() {
        val attempt = service.start(student, rows.mission().id, 3, false).attempt

        UserContextHolder.set(UserContext(null, "STUDENT", setOf(student.toString().uppercase()), null))

        assertEquals(attempt.id, service.get(attempt.id).attempt.id)
    }

    @Test
    fun `생각 열기 질문이 없는 미션은 404`() {
        val attempt = service.start(student, rows.mission(hints = emptyList()).id, 3, false).attempt

        assertError(HttpStatus.NOT_FOUND, "NOT_FOUND") { service.openHint(attempt.id) }
        assertFalse(service.get(attempt.id).helped)
    }
}
