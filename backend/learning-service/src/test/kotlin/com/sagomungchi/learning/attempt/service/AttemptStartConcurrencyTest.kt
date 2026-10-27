package com.sagomungchi.learning.attempt.service

import com.sagomungchi.learning.TestRows
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
 * 같은 학생·미션의 동시 시작이 시도 하나로 모이는지 (이슈 #23 완료 조건, ERD 부분 UK).
 * 요청마다 실제로 커밋해야 해서 롤백하는 PostgresRepositoryTest 대신 별도 컨테이너를 씀 (repository-foundation 보고서).
 */
@SpringBootTest(properties = [
    "app.internal.token=concurrency-test-token",
    "spring.rabbitmq.username=test", "spring.rabbitmq.password=test",
])
class AttemptStartConcurrencyTest {
    @Autowired lateinit var service: AttemptService
    @Autowired lateinit var jdbc: JdbcTemplate

    @Test
    fun `동시에 시작해도 시도와 초안은 하나이고 모두 같은 attemptId`() {
        val mission = TestRows(jdbc).mission()
        val student = UUID.randomUUID()
        val requests = 8
        val ready = CountDownLatch(requests)
        val go = CountDownLatch(1)
        val pool = Executors.newFixedThreadPool(requests)

        val results = (1..requests).map {
            pool.submit<AttemptStart> {
                ready.countDown()
                go.await()
                service.start(student, mission.id, grade = 3, demo = false)
            }
        }
        ready.await(10, TimeUnit.SECONDS)
        go.countDown()
        val started = results.map { it.get(30, TimeUnit.SECONDS) }
        pool.shutdown()

        assertEquals(1, started.map { it.attempt.id }.toSet().size)
        assertEquals(1, started.count { it.created })
        assertEquals(1, count("SELECT count(*) FROM attempt WHERE student_id = ?", student))
        assertEquals(1, count("SELECT count(*) FROM attempt_draft WHERE attempt_id = ?", started.first().attempt.id))
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
