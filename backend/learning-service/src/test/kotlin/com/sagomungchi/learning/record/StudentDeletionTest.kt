package com.sagomungchi.learning.record

import com.github.tomakehurst.wiremock.WireMockServer
import com.github.tomakehurst.wiremock.client.WireMock.aResponse
import com.github.tomakehurst.wiremock.client.WireMock.equalTo
import com.github.tomakehurst.wiremock.client.WireMock.equalToJson
import com.github.tomakehurst.wiremock.client.WireMock.post
import com.github.tomakehurst.wiremock.client.WireMock.postRequestedFor
import com.github.tomakehurst.wiremock.client.WireMock.urlEqualTo
import com.github.tomakehurst.wiremock.core.WireMockConfiguration.options
import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.answer.service.AnswerService
import com.sagomungchi.learning.answer.service.SubmitCommand
import com.sagomungchi.learning.attempt.service.AttemptService
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.record.domain.DeletionScope
import com.sagomungchi.learning.record.service.StudentDeletionService
import org.flywaydb.core.Flyway
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.web.client.RestClientException
import java.time.OffsetDateTime
import java.util.UUID
import kotlin.test.assertEquals

/**
 * 학생 삭제 (이슈 #128 완료 조건, P09): 학습 기록 전부 물리 삭제 + 삭제 표식, 같은 이벤트 재전달·보고 실패 재시도는 삭제 없이 보고만.
 * 삭제는 커밋한 뒤 트랜잭션 밖에서 core에 보고하므로 실제 커밋이 필요해 별도 컨테이너를 씀 (AnswerConcurrencyTest와 같음)
 */
@SpringBootTest(properties = [
    "app.internal.token=deletion-test-token",
    "spring.rabbitmq.username=test", "spring.rabbitmq.password=test",
    "spring.rabbitmq.listener.simple.auto-startup=false",
])
class StudentDeletionTest {
    @Autowired lateinit var service: StudentDeletionService
    @Autowired lateinit var attemptService: AttemptService
    @Autowired lateinit var answerService: AnswerService
    @Autowired lateinit var jdbc: JdbcTemplate

    @BeforeEach
    fun reset() {
        core.resetAll()
        core.stubFor(post(urlEqualTo(COMPLETIONS.format(REQUEST))).willReturn(aResponse().withStatus(200)))
    }

    @AfterEach
    fun clear() = UserContextHolder.clear()

    @Test
    fun `학생의 학습 기록을 모든 표에서 지우고 삭제 표식을 남긴 뒤 SYSTEM·학생 범위로 core에 보고, 다른 학생 기록은 그대로`() {
        val student = recorded()
        val other = recorded()
        val otherBefore = counts(other)
        val eventId = UUID.randomUUID()

        asSystem(student) { service.delete(eventId, student, DeletionScope.RECORDS, REQUEST) }

        assertEquals(TABLES.associateWith { 0 }, counts(student))
        assertEquals(otherBefore, counts(other))
        assertEquals(mapOf("scope" to "RECORDS", "event_id" to eventId), jdbc.queryForMap("SELECT scope, event_id FROM deleted_student WHERE student_id = ?", student))
        assertEquals("student.deleted", jdbc.queryForObject("SELECT event_type FROM processed_event WHERE event_id = ?", String::class.java, eventId))
        core.verify(
            1,
            postRequestedFor(urlEqualTo(COMPLETIONS.format(REQUEST)))
                .withHeader("X-Internal-Token", equalTo("deletion-test-token"))
                .withHeader("X-User-Role", equalTo("SYSTEM"))
                .withHeader("X-Student-Scope", equalTo(student.toString()))
                .withRequestBody(equalToJson("""{"service":"learning"}""")),
        )
    }

    @Test
    fun `같은 이벤트를 다시 받으면 다시 지우지 않고 core 보고만 다시 보냄`() {
        val student = recorded()
        val eventId = UUID.randomUUID()
        asSystem(student) { service.delete(eventId, student, DeletionScope.RECORDS, REQUEST) }
        val afterFirst = jdbc.queryForObject("SELECT deleted_at FROM deleted_student WHERE student_id = ?", OffsetDateTime::class.java, student)
        // 처리 뒤 생긴 기록: 같은 이벤트를 다시 처리해도 지우면 안 됨
        val laterAttempt = attempt(student)

        asSystem(student) { service.delete(eventId, student, DeletionScope.RECORDS, REQUEST) }

        assertEquals(1, count("SELECT count(*) FROM attempt WHERE id = ?", laterAttempt))
        assertEquals(afterFirst, jdbc.queryForObject("SELECT deleted_at FROM deleted_student WHERE student_id = ?", OffsetDateTime::class.java, student))
        core.verify(2, postRequestedFor(urlEqualTo(COMPLETIONS.format(REQUEST))))
    }

    @Test
    fun `core 보고가 실패하면 예외로 재시도하게 하고 삭제는 남음, 재시도 때는 삭제 없이 보고만`() {
        val student = recorded()
        val eventId = UUID.randomUUID()
        core.stubFor(post(urlEqualTo(COMPLETIONS.format(REQUEST))).willReturn(aResponse().withStatus(503)))

        assertThrows<RestClientException> { asSystem(student) { service.delete(eventId, student, DeletionScope.RECORDS, REQUEST) } }

        assertEquals(TABLES.associateWith { 0 }, counts(student))
        assertEquals(1, count("SELECT count(*) FROM processed_event WHERE event_id = ?", eventId))
        val laterAttempt = attempt(student)
        core.stubFor(post(urlEqualTo(COMPLETIONS.format(REQUEST))).willReturn(aResponse().withStatus(200)))

        asSystem(student) { service.delete(eventId, student, DeletionScope.RECORDS, REQUEST) }

        assertEquals(1, count("SELECT count(*) FROM attempt WHERE id = ?", laterAttempt))
        core.verify(2, postRequestedFor(urlEqualTo(COMPLETIONS.format(REQUEST))))
    }

    @Test
    fun `삭제 표식은 학생당 한 행, 범위가 이미 PROFILE이면 유지하고 RECORDS 뒤 PROFILE은 PROFILE로`() {
        val profileFirst = UUID.randomUUID()
        val recordsFirst = UUID.randomUUID()
        val last = UUID.randomUUID()

        asSystem(profileFirst) { service.delete(UUID.randomUUID(), profileFirst, DeletionScope.PROFILE, REQUEST) }
        asSystem(profileFirst) { service.delete(last, profileFirst, DeletionScope.RECORDS, REQUEST) }
        asSystem(recordsFirst) { service.delete(UUID.randomUUID(), recordsFirst, DeletionScope.RECORDS, REQUEST) }
        asSystem(recordsFirst) { service.delete(UUID.randomUUID(), recordsFirst, DeletionScope.PROFILE, REQUEST) }

        assertEquals(mapOf("scope" to "PROFILE", "event_id" to last), jdbc.queryForMap("SELECT scope, event_id FROM deleted_student WHERE student_id = ?", profileFirst))
        assertEquals("PROFILE", jdbc.queryForObject("SELECT scope FROM deleted_student WHERE student_id = ?", String::class.java, recordsFirst))
    }

    /**
     * 표마다 행이 있는 학생: 시도·초안·생각 열기·답변 2개(보완 답변이 되묻기를 가리켜 답변 → 되묻기 → 판정 → 답변 고리)·
     * 판정·판정 요소·되묻기·정정·돌아보기·자기 평가
     */
    private fun recorded(): UUID {
        val student = UUID.randomUUID()
        val rows = TestRows(jdbc)
        val mission = rows.mission()
        val element = rows.rubric(mission).single()
        val attemptId = asStudent(student) { attemptService.start(student, mission.id, 3, demo = false).attempt.id }
        val first = asStudent(student) { answerService.submit(attemptId, UUID.randomUUID(), narrative("첫 답")) }
        rows.judged(first.id, listOf(element to "첫 답"))
        val followup = rows.followup(attemptId, first.id)
        asStudent(student) { answerService.submit(attemptId, UUID.randomUUID(), narrative("보완 답", followup)) }
        val judgment = jdbc.queryForObject("SELECT id FROM judgment WHERE answer_id = ?", UUID::class.java, first.id)
        jdbc.update(
            """INSERT INTO judgment_correction (id, judgment_id, error_report_id, reason, previous, corrected, corrected_by, idempotency_key, created_at)
               VALUES (?, ?, ?, '사유', '{"result":"PARTIAL"}', '{"result":"CORRECT"}', ?, ?, now())""",
            UUID.randomUUID(), judgment, UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID(),
        )
        jdbc.update("INSERT INTO hint_usage (id, attempt_id, hint_question_id, opened_at) VALUES (?, ?, ?, now())", UUID.randomUUID(), attemptId, mission.hintIds.first())
        jdbc.update("INSERT INTO reflection (id, attempt_id, difficulty, changed_text, created_at) VALUES (?, ?, 'EASY', '돌아보기', now())", UUID.randomUUID(), attemptId)
        jdbc.update("INSERT INTO self_assessment (id, attempt_id, rubric_element_id, checked, created_at) VALUES (?, ?, ?, true, now())", UUID.randomUUID(), attemptId, element)
        assertEquals(TABLES, counts(student).filterValues { it > 0 }.keys.toList(), "모든 표에 행이 있어야 삭제를 확인할 수 있음")
        return student
    }

    /** 학생의 새 시도 하나(다른 미션). 처리한 이벤트를 다시 받아도 남아야 하는 기록 */
    private fun attempt(student: UUID): UUID {
        val mission = TestRows(jdbc).mission()
        return asStudent(student) { attemptService.start(student, mission.id, 3, demo = false).attempt.id }
    }

    private fun narrative(text: String, followupId: UUID? = null) =
        SubmitCommand(InputType.NARRATIVE, AnswerContent(text = text), false, followupId)

    private fun counts(student: UUID): Map<String, Int> = TABLES.associateWith { table ->
        count("SELECT count(*) FROM $table x WHERE ${OWNER.getValue(table)}", student)
    }

    private fun count(sql: String, id: UUID) = jdbc.queryForObject(sql, Int::class.java, id)!!

    private fun <T> asStudent(student: UUID, block: () -> T): T = within(UserContext(null, "STUDENT", setOf(student.toString()), null), block)

    private fun <T> asSystem(student: UUID, block: () -> T): T = within(UserContext(null, "SYSTEM", setOf(student.toString()), null), block)

    private fun <T> within(context: UserContext, block: () -> T): T {
        UserContextHolder.set(context)
        return try { block() } finally { UserContextHolder.clear() }
    }

    companion object {
        private val REQUEST: UUID = UUID.randomUUID()
        private const val COMPLETIONS = "/internal/deletion-requests/%s/completions"
        private const val ATTEMPTS = "SELECT id FROM attempt WHERE student_id = ?"
        private const val ANSWERS = "SELECT id FROM answer WHERE attempt_id IN (SELECT id FROM attempt WHERE student_id = ?)"
        private const val JUDGMENTS = "SELECT id FROM judgment WHERE answer_id IN ($ANSWERS)"

        /** 학생 기록이 있는 표와 학생을 찾는 조건 */
        private val OWNER = linkedMapOf(
            "attempt" to "x.student_id = ?",
            "attempt_draft" to "x.attempt_id IN ($ATTEMPTS)",
            "hint_usage" to "x.attempt_id IN ($ATTEMPTS)",
            "answer" to "x.attempt_id IN ($ATTEMPTS)",
            "judgment" to "x.answer_id IN ($ANSWERS)",
            "judgment_element" to "x.judgment_id IN ($JUDGMENTS)",
            "followup" to "x.attempt_id IN ($ATTEMPTS)",
            "judgment_correction" to "x.judgment_id IN ($JUDGMENTS)",
            "reflection" to "x.attempt_id IN ($ATTEMPTS)",
            "self_assessment" to "x.attempt_id IN ($ATTEMPTS)",
        )
        private val TABLES = OWNER.keys.toList()

        private val core = WireMockServer(options().dynamicPort()).apply { start() }
        private val postgres by lazy {
            org.testcontainers.containers.PostgreSQLContainer<Nothing>("postgres:17.11-alpine").apply {
                start()
                Flyway.configure().dataSource(jdbcUrl, username, password)
                    .locations("classpath:db/migration").load().migrate()
            }
        }

        @JvmStatic
        @DynamicPropertySource
        fun database(registry: DynamicPropertyRegistry) {
            registry.add("spring.datasource.url") { postgres.jdbcUrl }
            registry.add("spring.datasource.username") { postgres.username }
            registry.add("spring.datasource.password") { postgres.password }
            registry.add("app.services.core") { core.baseUrl() }
        }
    }
}
