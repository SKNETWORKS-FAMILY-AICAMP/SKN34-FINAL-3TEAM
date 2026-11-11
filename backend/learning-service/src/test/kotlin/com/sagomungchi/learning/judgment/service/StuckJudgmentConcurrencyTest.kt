package com.sagomungchi.learning.judgment.service

import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.persistence.TEST_POSTGRES_IMAGE
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.answer.service.AnswerService
import com.sagomungchi.learning.answer.service.SubmitCommand
import com.sagomungchi.learning.attempt.service.AttemptService
import com.sagomungchi.learning.judgment.domain.Judgment
import com.sagomungchi.learning.mission.domain.InputType
import org.flywaydb.core.Flyway
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.transaction.PlatformTransactionManager
import org.springframework.transaction.support.TransactionTemplate
import org.testcontainers.containers.PostgreSQLContainer
import java.sql.Timestamp
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.Future
import java.util.concurrent.TimeUnit
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue

/**
 * 고착 탐지와 재획득·다른 탐지가 겹칠 때 (#241 완료 조건): 조건부 UPDATE가 행 잠금 뒤 조건을 다시 봐 한쪽만 바뀜.
 * 요청마다 실제로 커밋해야 해서 CorrectionConcurrencyTest처럼 별도 컨테이너. 주기 실행이 끼지 않게 탐지는 끔
 */
@SpringBootTest(properties = [
    "app.internal.token=concurrency-test-token",
    "spring.rabbitmq.username=test", "spring.rabbitmq.password=test",
    "spring.rabbitmq.listener.simple.auto-startup=false",
    "app.judgment.stuck-detection-enabled=false",
])
class StuckJudgmentConcurrencyTest {
    @Autowired lateinit var service: JudgmentService
    @Autowired lateinit var answerService: AnswerService
    @Autowired lateinit var attemptService: AttemptService
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var transactions: PlatformTransactionManager

    @Test
    fun `재획득이 행을 잡은 동안 탐지하면 기다렸다가 새 리스가 잡힌 판정은 건너뜀`() {
        val answerId = stuck()
        val now = Instant.now().truncatedTo(ChronoUnit.MICROS)

        val (acquired, failed) = whileHolding({ service.acquire(answerId, now) }) { service.failStuck(now) }

        assertIs<AcquireResult.Acquired>(acquired)
        assertFalse(failed.contains(answerId))
        assertEquals(listOf("RUNNING", 0), state(answerId))
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM judgment WHERE answer_id = ? AND lease_until = ?", Int::class.java, answerId, Timestamp.from(now.plus(Judgment.LEASE))))
    }

    @Test
    fun `탐지가 행을 잡은 동안 재요청하면 기다렸다가 FAILED에서 가져감`() {
        val answerId = stuck()
        val now = Instant.now().truncatedTo(ChronoUnit.MICROS)

        val (failed, acquired) = whileHolding({ service.failStuck(now) }) { service.acquire(answerId, now) }

        assertTrue(failed.contains(answerId))
        assertIs<AcquireResult.Acquired>(acquired)
        assertEquals(listOf("RUNNING", 1), state(answerId))
    }

    @Test
    fun `두 인스턴스가 같은 주기에 탐지해도 한 번만 바뀜`() {
        val answerId = stuck()
        val now = Instant.now().truncatedTo(ChronoUnit.MICROS)
        val ready = CountDownLatch(2)
        val go = CountDownLatch(1)
        val pool = Executors.newFixedThreadPool(2)

        val runs = (1..2).map {
            pool.submit<List<UUID>> {
                ready.countDown()
                go.await()
                service.failStuck(now)
            }
        }
        ready.await(10, TimeUnit.SECONDS)
        go.countDown()
        val failed = runs.map { it.get(30, TimeUnit.SECONDS) }.also { pool.shutdown() }

        assertEquals(1, failed.count { it.contains(answerId) })
        assertEquals(listOf("FAILED", 1), state(answerId))
    }

    /**
     * first를 트랜잭션 안에서 실행해 판정 행을 잡은 채 멈추고, second가 그 잠금을 기다리는 것을 확인한 뒤 first를 커밋.
     * 두 결과를 실행 순서대로
     */
    private fun <A, B> whileHolding(first: () -> A, second: () -> B): Pair<A, B> {
        val locked = CountDownLatch(1)
        val release = CountDownLatch(1)
        val pool = Executors.newFixedThreadPool(2)
        val holder: Future<A> = pool.submit<A> {
            TransactionTemplate(transactions).execute {
                first().also {
                    locked.countDown()
                    check(release.await(30, TimeUnit.SECONDS))
                }
            }
        }
        check(locked.await(10, TimeUnit.SECONDS))
        val waiter: Future<B> = pool.submit<B> { second() }
        val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(10)
        while (lockWaits() == 0) {
            check(System.nanoTime() < deadline) { "뒤 작업이 판정 행 잠금을 기다리지 않음" }
            Thread.sleep(20)
        }
        assertFalse(waiter.isDone)
        release.countDown()
        return (holder.get(30, TimeUnit.SECONDS) to waiter.get(30, TimeUnit.SECONDS)).also { pool.shutdown() }
    }

    /** 다른 트랜잭션의 판정 행 잠금을 기다리는 연결 수 */
    private fun lockWaits(): Int = jdbc.queryForObject(
        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND wait_event_type = 'Lock' AND query LIKE '%UPDATE judgment%'",
        Int::class.java,
    ) ?: 0

    /** 서술 답변을 제출하고 판정을 리스가 1분 전에 끝난 RUNNING으로 커밋. 답변 ID */
    private fun stuck(): UUID {
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
        jdbc.update("UPDATE judgment SET process_status = 'RUNNING', lease_until = now() - interval '1 minute' WHERE answer_id = ?", answer.id)
        return answer.id
    }

    private fun state(answerId: UUID): List<Any?> =
        jdbc.queryForMap("SELECT process_status, retry_count FROM judgment WHERE answer_id = ?", answerId).values.toList()

    companion object {
        private val postgres by lazy {
            PostgreSQLContainer<Nothing>(TEST_POSTGRES_IMAGE).apply {
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
