package com.sagomungchi.learning.judgment.service

import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.answer.service.AnswerService
import com.sagomungchi.learning.answer.service.SubmitCommand
import com.sagomungchi.learning.attempt.service.AttemptService
import com.sagomungchi.learning.judgment.domain.CorrectionCommand
import com.sagomungchi.learning.judgment.domain.JudgmentCorrection
import com.sagomungchi.learning.judgment.domain.JudgmentResult
import com.sagomungchi.learning.mission.domain.InputType
import org.flywaydb.core.Flyway
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.testcontainers.containers.PostgreSQLContainer
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlin.test.assertEquals

/**
 * 동시 정정 (이슈 #80): 판정 행 잠금으로 같은 판정의 정정이 한 줄로 서서
 * 같은 키는 정정 1건, 같은 신고를 다른 키로 보내면 1건만 남고 나머지는 409.
 * 요청마다 실제로 커밋해야 해서 AnswerConcurrencyTest처럼 별도 컨테이너를 씀
 */
@SpringBootTest(properties = [
    "app.internal.token=concurrency-test-token",
    "spring.rabbitmq.username=test", "spring.rabbitmq.password=test",
    "spring.rabbitmq.listener.simple.auto-startup=false",
])
class CorrectionConcurrencyTest {
    @Autowired lateinit var service: JudgmentService
    @Autowired lateinit var answerService: AnswerService
    @Autowired lateinit var attemptService: AttemptService
    @Autowired lateinit var jdbc: JdbcTemplate

    private val admin = UUID.randomUUID()

    @Test
    fun `같은 키로 동시에 보내면 정정 1건이고 모두 같은 정정`() {
        val (student, judgmentId) = judged()
        val key = UUID.randomUUID()
        val command = CorrectionCommand(UUID.randomUUID(), "동시에 보낸 정정", JudgmentResult.CORRECT, admin)

        val outcomes = concurrently(student) { service.correct(judgmentId, command, key) }

        assertEquals(outcomes.size, outcomes.filterIsInstance<JudgmentCorrection>().size)
        assertEquals(1, outcomes.toSet().size)
        assertEquals(1, count(judgmentId))
    }

    @Test
    fun `같은 신고를 다른 키로 동시에 보내도 1건만 저장되고 나머지는 409`() {
        val (student, judgmentId) = judged()
        val command = CorrectionCommand(UUID.randomUUID(), "동시에 보낸 정정", JudgmentResult.CORRECT, admin)

        val outcomes = concurrently(student) { service.correct(judgmentId, command, UUID.randomUUID()) }

        assertEquals(1, outcomes.filterIsInstance<JudgmentCorrection>().size)
        assertEquals(
            List(outcomes.size - 1) { "CORRECTION_REPORT_CONFLICT" },
            outcomes.filterIsInstance<BusinessException>().map { it.code },
        )
        assertEquals(1, count(judgmentId))
    }

    /** 서술 답변을 제출하고 판정을 DONE으로. 학생 ID와 판정 ID */
    private fun judged(): Pair<UUID, UUID> {
        val student = UUID.randomUUID()
        val rows = TestRows(jdbc)
        val mission = rows.mission()
        rows.rubric(mission)
        UserContextHolder.set(UserContext(null, "STUDENT", setOf(student.toString()), null))
        val answer = try {
            val attempt = attemptService.start(student, mission.id, grade = 3, demo = false).attempt
            answerService.submit(attempt.id, UUID.randomUUID(), SubmitCommand(InputType.NARRATIVE, AnswerContent(text = "답"), false, null))
        } finally {
            UserContextHolder.clear()
        }
        rows.judged(answer.id)
        return student to jdbc.queryForObject("SELECT id FROM judgment WHERE answer_id = ?", UUID::class.java, answer.id)!!
    }

    /** 같은 관리자의 요청 8개를 한꺼번에 출발시키고, 결과나 업무 오류를 모음 */
    private fun concurrently(student: UUID, request: () -> JudgmentCorrection): List<Any> {
        val requests = 8
        val ready = CountDownLatch(requests)
        val go = CountDownLatch(1)
        val pool = Executors.newFixedThreadPool(requests)
        val results = (1..requests).map {
            pool.submit<Any> {
                UserContextHolder.set(UserContext(admin.toString(), "ADMIN", setOf(student.toString()), null))
                try {
                    ready.countDown()
                    go.await()
                    request()
                } catch (error: BusinessException) {
                    error
                } finally {
                    UserContextHolder.clear()
                }
            }
        }
        ready.await(10, TimeUnit.SECONDS)
        go.countDown()
        return results.map { it.get(30, TimeUnit.SECONDS) }.also { pool.shutdown() }
    }

    private fun count(judgmentId: UUID) =
        jdbc.queryForObject("SELECT count(*) FROM judgment_correction WHERE judgment_id = ?", Int::class.java, judgmentId)

    companion object {
        private val postgres by lazy {
            PostgreSQLContainer<Nothing>("postgres:17.11-alpine").apply {
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
        }
    }
}
