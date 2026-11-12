package com.sagomungchi.learning.memory

import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.persistence.TEST_POSTGRES_IMAGE
import com.sagomungchi.learning.attempt.repository.AttemptRepository
import com.sagomungchi.learning.memory.service.ThemeFrameService
import org.flywaydb.core.Flyway
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.transaction.support.TransactionTemplate
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.util.UUID
import java.util.concurrent.CompletableFuture
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.test.assertEquals
import kotlin.test.assertFalse

/**
 * 같은 회차의 넷째·다섯째 문제가 동시에 학습 완료될 때 (#559): 회차 잠금이 없으면 두 트랜잭션이 서로의 미커밋 완료를 못 봐
 * 둘 다 지급을 건너뛴다. 첫 트랜잭션이 잠금을 쥔 채 커밋 전일 때 둘째가 잠금을 기다리는 것을 확인하고, 커밋 뒤 둘째가 액자를 만든다.
 * 실제 커밋이 필요해 별도 컨테이너를 씀(StudentDeletionTest와 같음)
 */
@SpringBootTest(properties = [
    "app.internal.token=frame-concurrency-test-token",
    "spring.rabbitmq.username=test", "spring.rabbitmq.password=test",
    "spring.rabbitmq.listener.simple.auto-startup=false",
    "app.mission-draft.enabled=false", "app.theme-draft.enabled=false",
])
class ThemeFrameConcurrencyTest {
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var transactions: TransactionTemplate
    @Autowired lateinit var attempts: AttemptRepository
    @Autowired lateinit var frames: ThemeFrameService

    @Test
    fun `동시에 마친 두 문제는 회차 잠금으로 차례로 판정돼 액자 1개`() {
        val rows = TestRows(jdbc)
        val missions = rows.themeMissions()
        val theme = rows.publishedTheme(missions.map { it.id }, WEEK)
        val student = UUID.randomUUID()
        val ids = missions.mapIndexed { index, mission ->
            UUID.randomUUID().also {
                val done = if (index < 3) at(index.toLong()) else null
                jdbc.update(
                    """INSERT INTO attempt (id, student_id, mission_id, mission_version_id, rubric_version_id, grade, status,
                           started_at, finished_at, completed_at, updated_at, context, theme_id, theme_week_start)
                       VALUES (?, ?, ?, ?, ?, 3, ?, ?, ?, ?, ?, 'THEME_DAY', ?, ?)""",
                    it, student, mission.id, mission.versionId, mission.rubricVersionId, if (done != null) "COMPLETED" else "IN_PROGRESS",
                    at(index.toLong()).minusMinutes(30), at(index.toLong()), done, at(index.toLong()), theme, WEEK,
                )
            }
        }
        val firstHolding = CountDownLatch(1)
        val releaseFirst = CountDownLatch(1)

        fun complete(attemptId: UUID, day: Long, beforeCommit: () -> Unit = {}): Boolean = transactions.execute {
            jdbc.update("UPDATE attempt SET status = 'COMPLETED', completed_at = ? WHERE id = ?", at(day, 11), attemptId)
            frames.awardIfComplete(attempts.findById(attemptId)!!).also { beforeCommit() }
        }!!

        val first = CompletableFuture.supplyAsync {
            complete(ids[3], 3) { firstHolding.countDown(); releaseFirst.await(30, TimeUnit.SECONDS) }
        }
        firstHolding.await(30, TimeUnit.SECONDS)
        val second = CompletableFuture.supplyAsync { complete(ids[4], 4) }
        // 둘째가 회차 잠금을 기다리는 중(첫째 미커밋)일 때 첫째를 커밋
        waitUntil { jdbc.queryForObject("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted", Int::class.java)!! >= 1 }
        releaseFirst.countDown()

        assertFalse(first.get(30, TimeUnit.SECONDS)) // 첫째 시점에는 4문제
        assertEquals(true, second.get(30, TimeUnit.SECONDS))
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM theme_frame WHERE student_id = ?", Int::class.java, student))
    }

    private fun waitUntil(condition: () -> Boolean) {
        val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(30)
        while (!condition()) {
            check(System.nanoTime() < deadline) { "둘째 트랜잭션이 회차 잠금을 기다리지 않음" }
            Thread.sleep(50)
        }
    }

    private fun at(day: Long, hour: Int = 10): OffsetDateTime = WEEK.plusDays(day).atTime(hour, 0).atZone(KST).toOffsetDateTime()

    companion object {
        private val KST: ZoneId = ZoneId.of("Asia/Seoul")
        private val WEEK: LocalDate = LocalDate.of(2026, 11, 2)

        private val postgres by lazy {
            org.testcontainers.containers.PostgreSQLContainer<Nothing>(TEST_POSTGRES_IMAGE).apply {
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
