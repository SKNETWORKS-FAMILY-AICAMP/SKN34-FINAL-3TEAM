package com.sagomungchi.learning.judgment.facade

import com.github.tomakehurst.wiremock.WireMockServer
import com.github.tomakehurst.wiremock.client.WireMock.aResponse
import com.github.tomakehurst.wiremock.client.WireMock.okJson
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
import com.sagomungchi.learning.judgment.domain.ElementSource
import com.sagomungchi.learning.judgment.domain.FeedbackResult
import com.sagomungchi.learning.judgment.domain.Followup
import com.sagomungchi.learning.judgment.domain.FollowupSource
import com.sagomungchi.learning.judgment.domain.FollowupType
import com.sagomungchi.learning.judgment.domain.Judged
import com.sagomungchi.learning.judgment.domain.JudgedBy
import com.sagomungchi.learning.judgment.domain.JudgmentElement
import com.sagomungchi.learning.judgment.domain.JudgmentMethod
import com.sagomungchi.learning.judgment.domain.JudgmentResult
import com.sagomungchi.learning.judgment.domain.ProcessStatus
import com.sagomungchi.learning.judgment.service.AcquireResult
import com.sagomungchi.learning.judgment.service.JudgmentService
import com.sagomungchi.learning.mission.domain.InputType
import org.flywaydb.core.Flyway
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.dao.DataIntegrityViolationException
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.testcontainers.containers.PostgreSQLContainer
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import javax.sql.DataSource
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * 같은 답변의 피드백 동시 요청 (이슈 #25 처리 상태 전이): 리스를 얻은 요청 하나만 ai를 부르고 나머지는 RUNNING.
 * 요청마다 실제로 커밋해야 해서 AnswerConcurrencyTest처럼 별도 컨테이너
 */
@SpringBootTest(properties = [
    "app.internal.token=concurrency-test-token",
    "spring.rabbitmq.username=test", "spring.rabbitmq.password=test",
])
class FeedbackConcurrencyTest {
    @org.springframework.test.context.bean.override.mockito.MockitoBean
    lateinit var paymentUsage: com.sagomungchi.learning.judgment.client.PaymentUsageClient
    @Autowired lateinit var facade: FeedbackFacade
    @Autowired lateinit var answerService: AnswerService
    @Autowired lateinit var attemptService: AttemptService
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var judgmentService: JudgmentService
    @Autowired lateinit var dataSource: DataSource

    @Test
    fun `동시에 요청해도 ai 판정은 한 번, 나머지는 처리 중 응답이고 끝난 뒤에는 같은 결과`() {
        ai.resetAll()
        val rows = TestRows(jdbc)
        val mission = rows.mission(inputType = "NARRATIVE")
        val element = rows.rubric(mission).single()
        val student = UUID.randomUUID()
        val context = UserContext(null, "STUDENT", setOf(student.toString()), null)
        UserContextHolder.set(context)
        val answer = try {
            val attempt = attemptService.start(student, mission.id, 3, demo = false).attempt
            answerService.submit(attempt.id, UUID.randomUUID(), SubmitCommand(InputType.NARRATIVE, AnswerContent(text = "놀 수 있어서 좋아요"), false, null))
        } finally {
            UserContextHolder.clear()
        }
        ai.stubFor(
            post(urlEqualTo("/internal/judgments")).willReturn(
                okJson(
                    """{"result":"PARTIAL","elements":[{"elementId":"$element","quote":"놀 수 있어서","verified":true,"satisfied":true}],
                        "heldReason":null,"trial":true,"versions":{"model":"m","prompt":"judge@2"}}""",
                ).withFixedDelay(800),
            ),
        )
        ai.stubFor(
            post(urlEqualTo("/internal/followups")).willReturn(
                okJson("""{"type":"TELL_MORE","question":"더 말해 줄래요?","source":"LLM","leakCheck":{"passed":true},"versions":{"model":"m","prompt":"followup@4"}}"""),
            ),
        )
        val requests = 6
        val ready = CountDownLatch(requests)
        val go = CountDownLatch(1)
        val pool = Executors.newFixedThreadPool(requests)

        val results = (1..requests).map {
            pool.submit<FeedbackResult> {
                UserContextHolder.set(context)
                try {
                    ready.countDown()
                    go.await()
                    facade.feedback(answer.id)
                } finally {
                    UserContextHolder.clear()
                }
            }
        }
        ready.await(10, TimeUnit.SECONDS)
        go.countDown()
        val outcomes = results.map { it.get(30, TimeUnit.SECONDS) }
        pool.shutdown()

        assertEquals(1, outcomes.count { it.status == ProcessStatus.DONE })
        assertEquals(requests - 1, outcomes.count { it == FeedbackResult.inProgress(ProcessStatus.RUNNING) })
        assertEquals(1, ai.countRequestsMatching(postRequestedFor(urlEqualTo("/internal/judgments")).build()).count)
        UserContextHolder.set(context)
        try {
            assertEquals(outcomes.single { it.status == ProcessStatus.DONE }, facade.feedback(answer.id))
        } finally {
            UserContextHolder.clear()
        }
    }

    @Test
    fun `ai 실패는 FAILED로 따로 커밋되고 다시 요청하면 처음부터 실행`() {
        ai.resetAll()
        val rows = TestRows(jdbc)
        val mission = rows.mission(inputType = "NARRATIVE")
        val element = rows.rubric(mission).single()
        val student = UUID.randomUUID()
        UserContextHolder.set(UserContext(null, "STUDENT", setOf(student.toString()), null))
        try {
            val attempt = attemptService.start(student, mission.id, 3, demo = false).attempt
            val answer = answerService.submit(attempt.id, UUID.randomUUID(), SubmitCommand(InputType.NARRATIVE, AnswerContent(text = "놀 수 있어서 좋아요"), false, null))
            ai.stubFor(post(urlEqualTo("/internal/judgments")).willReturn(aResponse().withStatus(503)))

            assertThrows<AiUnavailableException> { facade.feedback(answer.id) }
            assertEquals(listOf("FAILED", "AI_UNAVAILABLE", 1), jdbc.queryForMap("SELECT process_status, failure_code, retry_count FROM judgment WHERE answer_id = ?", answer.id).values.toList())

            ai.stubFor(
                post(urlEqualTo("/internal/judgments")).willReturn(
                    okJson("""{"result":"CORRECT","elements":[{"elementId":"$element","quote":"놀 수 있어서","verified":true,"satisfied":true}],"heldReason":null,"trial":true,"versions":{"model":"m","prompt":"judge@2"}}"""),
                ),
            )
            ai.stubFor(post(urlEqualTo("/internal/followups")).willReturn(okJson("""{"type":"ONE_STEP_MORE","question":"반대 친구는?","source":"LLM","leakCheck":{"passed":true},"versions":{"model":"m","prompt":"followup@4"}}""")))
            assertEquals(ProcessStatus.DONE, facade.feedback(answer.id).status)
            assertEquals(listOf("DONE", null, 1), jdbc.queryForMap("SELECT process_status, failure_code, retry_count FROM judgment WHERE answer_id = ?", answer.id).values.toList())
        } finally {
            UserContextHolder.clear()
        }
    }

    @Test
    fun `결과 저장 중 오류로 롤백돼도 메모리의 엔티티가 아니라 DB의 판정으로 실패를 기록하고 다시 가져갈 수 있음`() {
        val rows = TestRows(jdbc)
        val mission = rows.mission(inputType = "NARRATIVE")
        val element = rows.rubric(mission).single()
        val student = UUID.randomUUID()
        UserContextHolder.set(UserContext(null, "STUDENT", setOf(student.toString()), null))
        val answer = try {
            val attempt = attemptService.start(student, mission.id, 3, demo = false).attempt
            answerService.submit(attempt.id, UUID.randomUUID(), SubmitCommand(InputType.NARRATIVE, AnswerContent(text = "놀 수 있어서 좋아요"), false, null))
        } finally {
            UserContextHolder.clear()
        }
        val now = Instant.now().truncatedTo(ChronoUnit.MICROS)
        val judgment = assertIs<AcquireResult.Acquired>(judgmentService.acquire(answer.id, now)).judgment
        val judged = Judged(
            JudgmentResult.PARTIAL, null,
            listOf(JudgmentElement(element, "놀 수 있어서", verified = true, sourceType = ElementSource.AI_OBSERVATION).satisfy()),
            JudgedBy(JudgmentMethod.LLM, trial = true, model = "m", prompt = "p"),
        )
        // 없는 시도의 되묻기라 외래키 오류 → 판정 DONE 저장까지 함께 롤백
        val broken = Followup(UUID.randomUUID(), FollowupType.TELL_MORE, "더 말해 줄래요?", FollowupSource.LLM, true, null, "m", "p")

        assertThrows<DataIntegrityViolationException> { judgmentService.saveResult(judgment, judged, broken) }
        assertEquals(ProcessStatus.DONE, judgment.status)
        assertEquals("RUNNING", jdbc.queryForObject("SELECT process_status FROM judgment WHERE answer_id = ?", String::class.java, answer.id))

        assertTrue(judgmentService.markFailed(judgment, "INTERNAL_ERROR"))
        assertEquals(
            listOf("FAILED", "INTERNAL_ERROR", 1),
            jdbc.queryForMap("SELECT process_status, failure_code, retry_count FROM judgment WHERE answer_id = ?", answer.id).values.toList(),
        )
        assertIs<AcquireResult.Acquired>(judgmentService.acquire(answer.id, now.plusSeconds(1)))
    }

    @Test
    fun `보완 답변의 되묻기를 만드는 사이 마무리하면 판정만 저장하고 되묻기는 저장하지 않음 (P04, #26 이슈 코멘트)`() {
        ai.resetAll()
        val rows = TestRows(jdbc)
        val mission = rows.mission(inputType = "NARRATIVE")
        val element = rows.rubric(mission).single()
        val student = UUID.randomUUID()
        val context = UserContext(null, "STUDENT", setOf(student.toString()), null)
        UserContextHolder.set(context)
        // 첫 답변은 판정이 끝나(마무리 조건 충족) 되묻기를 받았고, 그 되묻기에 답한 보완 답변을 판정하는 중
        val answer = try {
            val attempt = attemptService.start(student, mission.id, 3, demo = false).attempt
            val first = answerService.submit(attempt.id, UUID.randomUUID(), SubmitCommand(InputType.NARRATIVE, AnswerContent(text = "좋아요"), false, null))
            rows.judged(first.id)
            val followupId = rows.followup(attempt.id, first.id)
            answerService.submit(attempt.id, UUID.randomUUID(), SubmitCommand(InputType.NARRATIVE, AnswerContent(text = "놀 수 있어서 좋아요"), false, followupId))
        } finally {
            UserContextHolder.clear()
        }
        ai.stubFor(
            post(urlEqualTo("/internal/judgments")).willReturn(
                okJson("""{"result":"PARTIAL","elements":[{"elementId":"$element","quote":"놀 수 있어서","verified":true,"satisfied":true}],"heldReason":null,"trial":true,"versions":{"model":"m","prompt":"judge@2"}}"""),
            ),
        )
        ai.stubFor(
            post(urlEqualTo("/internal/followups")).willReturn(
                okJson("""{"type":"TELL_MORE","question":"더 말해 줄래요?","source":"LLM","leakCheck":{"passed":true},"versions":{"model":"m","prompt":"followup@4"}}""")
                    .withFixedDelay(1500),
            ),
        )
        val pool = Executors.newSingleThreadExecutor()
        val pending = pool.submit<FeedbackResult> {
            UserContextHolder.set(context)
            try {
                facade.feedback(answer.id)
            } finally {
                UserContextHolder.clear()
            }
        }
        // 되묻기 요청이 들어온 뒤(ai 호출 전 마무리 확인은 이미 지남) 학생이 마무리
        val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(10)
        while (ai.countRequestsMatching(postRequestedFor(urlEqualTo("/internal/followups")).build()).count == 0) {
            check(System.nanoTime() < deadline) { "되묻기 요청이 오지 않음" }
            Thread.sleep(20)
        }
        UserContextHolder.set(context)
        try {
            attemptService.finish(answer.attemptId)
        } finally {
            UserContextHolder.clear()
        }
        val result = pending.get(30, TimeUnit.SECONDS)
        pool.shutdown()

        assertEquals(ProcessStatus.DONE, result.status)
        assertNull(result.followup)
        assertTrue(result.nextActions.isEmpty())
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM followup f JOIN judgment j ON j.id = f.judgment_id WHERE j.answer_id = ?", Int::class.java, answer.id))
    }

    @Test
    fun `마무리가 시도 행을 잠근 동안 판정 저장은 기다리고, 마무리가 커밋되면 되묻기를 저장하지 않음 (시도 → 판정 잠금 순서)`() {
        ai.resetAll()
        val rows = TestRows(jdbc)
        val mission = rows.mission(inputType = "NARRATIVE")
        val element = rows.rubric(mission).single()
        val student = UUID.randomUUID()
        val context = UserContext(null, "STUDENT", setOf(student.toString()), null)
        UserContextHolder.set(context)
        val answer = try {
            val attempt = attemptService.start(student, mission.id, 3, demo = false).attempt
            answerService.submit(attempt.id, UUID.randomUUID(), SubmitCommand(InputType.NARRATIVE, AnswerContent(text = "놀 수 있어서 좋아요"), false, null))
        } finally {
            UserContextHolder.clear()
        }
        ai.stubFor(
            post(urlEqualTo("/internal/judgments")).willReturn(
                okJson("""{"result":"PARTIAL","elements":[{"elementId":"$element","quote":"놀 수 있어서","verified":true,"satisfied":true}],"heldReason":null,"trial":true,"versions":{"model":"m","prompt":"judge@2"}}"""),
            ),
        )
        ai.stubFor(
            post(urlEqualTo("/internal/followups")).willReturn(
                okJson("""{"type":"TELL_MORE","question":"더 말해 줄래요?","source":"LLM","leakCheck":{"passed":true},"versions":{"model":"m","prompt":"followup@4"}}"""),
            ),
        )
        val pool = Executors.newSingleThreadExecutor()
        // 마무리(AttemptService.finish의 lockById)처럼 별도 트랜잭션이 시도 행을 잠근 동안 피드백 처리. 실제 마무리는 트랜잭션 중간에 멈출 수 없어 잠금과 기록만 같게 함
        val pending = dataSource.connection.use { finish ->
            finish.autoCommit = false
            finish.prepareStatement("SELECT id FROM attempt WHERE id = ? FOR UPDATE").use { it.setObject(1, answer.attemptId); it.executeQuery() }
            val pending = pool.submit<FeedbackResult> {
                UserContextHolder.set(context)
                try {
                    facade.feedback(answer.id)
                } finally {
                    UserContextHolder.clear()
                }
            }
            val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(10)
            while (savingWaitsForAttemptLock() == 0) {
                check(System.nanoTime() < deadline) { "판정 저장이 시도 잠금을 기다리지 않음" }
                Thread.sleep(20)
            }
            assertFalse(pending.isDone)
            finish.prepareStatement("UPDATE attempt SET finished_at = now() WHERE id = ?").use { it.setObject(1, answer.attemptId); it.executeUpdate() }
            finish.commit()
            pending
        }
        val result = pending.get(30, TimeUnit.SECONDS)
        pool.shutdown()

        assertEquals(ProcessStatus.DONE, result.status)
        assertNull(result.followup)
        assertTrue(result.nextActions.isEmpty())
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM followup f JOIN judgment j ON j.id = f.judgment_id WHERE j.answer_id = ?", Int::class.java, answer.id))
    }

    /** 판정 저장의 시도 행 잠금(JudgmentMapper lockAttemptOpen)이 다른 트랜잭션의 잠금을 기다리는 중인 연결 수 */
    private fun savingWaitsForAttemptLock(): Int = jdbc.queryForObject(
        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND wait_event_type = 'Lock' AND query LIKE '%FOR UPDATE OF t%'",
        Int::class.java,
    ) ?: 0

    companion object {
        private val ai = WireMockServer(options().dynamicPort()).apply { start() }

        private val postgres by lazy {
            PostgreSQLContainer<Nothing>("postgres:17.11-alpine").apply {
                start()
                Flyway.configure().dataSource(jdbcUrl, username, password)
                    .locations("classpath:db/migration").load().migrate()
            }
        }

        @JvmStatic
        @DynamicPropertySource
        fun properties(registry: DynamicPropertyRegistry) {
            registry.add("spring.datasource.url") { postgres.jdbcUrl }
            registry.add("spring.datasource.username") { postgres.username }
            registry.add("spring.datasource.password") { postgres.password }
            registry.add("app.services.ai") { ai.baseUrl() }
        }
    }
}
