package com.sagomungchi.learning.answer.service

import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.answer.domain.Answer
import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.attempt.service.AttemptService
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
 * 동시 제출 (이슈 #24 완료 조건): 시도 행 잠금으로 같은 시도의 제출이 한 줄로 서서
 * 같은 키는 답변 1건, 다른 키라도 판정 전에는 버전 1만 남고 나머지는 422.
 * 요청마다 실제로 커밋해야 해서 AttemptConcurrencyTest처럼 별도 컨테이너를 씀
 */
@SpringBootTest(properties = [
    "app.internal.token=concurrency-test-token",
    "spring.rabbitmq.username=test", "spring.rabbitmq.password=test",
    "spring.rabbitmq.listener.simple.auto-startup=false",
])
class AnswerConcurrencyTest {
    @Autowired lateinit var service: AnswerService
    @Autowired lateinit var attemptService: AttemptService
    @Autowired lateinit var jdbc: JdbcTemplate

    private val command = SubmitCommand(InputType.NARRATIVE, AnswerContent(text = "동시에 보낸 답"), false, null)

    @Test
    fun `같은 키로 동시에 보내면 답변·판정 1건이고 모두 같은 답변`() {
        val (student, attemptId) = startAttempt()
        val key = UUID.randomUUID()

        val outcomes = concurrently(student) { service.submit(attemptId, key, command) }

        assertEquals(1, outcomes.filterIsInstance<Answer>().map { it.id }.toSet().size)
        assertEquals(outcomes.size, outcomes.filterIsInstance<Answer>().size)
        assertEquals(1, count("SELECT count(*) FROM answer WHERE attempt_id = ?", attemptId))
        assertEquals(1, count("SELECT count(*) FROM judgment j JOIN answer a ON a.id = j.answer_id WHERE a.attempt_id = ?", attemptId))
    }

    @Test
    fun `다른 키로 동시에 보내도 버전 1 하나만 저장되고 나머지는 422`() {
        val (student, attemptId) = startAttempt()

        val outcomes = concurrently(student) { service.submit(attemptId, UUID.randomUUID(), command) }

        assertEquals(1, outcomes.filterIsInstance<Answer>().single().version)
        assertEquals(
            List(outcomes.size - 1) { "ANSWER_INCOMPLETE" },
            outcomes.filterIsInstance<BusinessException>().map { it.code },
        )
        assertEquals(1, count("SELECT count(*) FROM answer WHERE attempt_id = ?", attemptId))
    }

    private fun startAttempt(): Pair<UUID, UUID> {
        val student = UUID.randomUUID()
        val attempt = attemptService.start(student, TestRows(jdbc).mission().id, grade = 3, demo = false).attempt
        return student to attempt.id
    }

    /** 같은 학생의 요청 8개를 한꺼번에 출발시키고, 결과나 업무 오류를 모음 */
    private fun concurrently(student: UUID, request: () -> Answer): List<Any> {
        val requests = 8
        val ready = CountDownLatch(requests)
        val go = CountDownLatch(1)
        val pool = Executors.newFixedThreadPool(requests)
        val results = (1..requests).map {
            pool.submit<Any> {
                UserContextHolder.set(UserContext(null, "STUDENT", setOf(student.toString()), null))
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

    private fun count(sql: String, id: UUID) = jdbc.queryForObject(sql, Int::class.java, id)

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
