package com.sagomungchi.learning.mission.service

import com.sagomungchi.learning._common.exception.errorCodeOf
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning.mission.client.AiDraftChecks
import com.sagomungchi.learning.mission.client.AiDraftRequest
import com.sagomungchi.learning.mission.client.AiDraftResponse
import com.sagomungchi.learning.mission.client.MissionDraftAiClient
import com.sagomungchi.learning.mission.domain.DraftInput
import com.sagomungchi.learning.mission.domain.DraftStatus
import com.sagomungchi.learning.mission.domain.DraftVersions
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.MissionDraftTest
import com.sagomungchi.learning.mission.domain.ThinkingType
import com.sagomungchi.learning.mission.repository.MissionDraftRepository
import org.flywaydb.core.Flyway
import org.junit.jupiter.api.Test
import org.mockito.BDDMockito.given
import org.mockito.Mockito.any
import org.mockito.Mockito.times
import org.mockito.Mockito.verify
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.testcontainers.containers.PostgreSQLContainer
import java.time.Instant
import java.util.UUID
import java.util.concurrent.Callable
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlin.test.assertEquals

/**
 * 초안 생성·채택 동시 실행 (#353, class-diagram 4.1.1): 레플리카가 같은 주기에 돌아도 초안 하나는 한 곳만 생성하고,
 * 같은 초안을 동시에 채택해도 미션은 하나. 요청마다 실제로 커밋해야 해서 AdminMissionConcurrencyTest처럼 별도 컨테이너를 씀
 */
@SpringBootTest(properties = [
    "app.internal.token=concurrency-test-token",
    "spring.rabbitmq.username=test", "spring.rabbitmq.password=test",
    "spring.rabbitmq.listener.simple.auto-startup=false",
    "app.mission-draft.enabled=false",
])
class MissionDraftConcurrencyTest {
    @Autowired lateinit var service: MissionDraftService
    @Autowired lateinit var drafts: MissionDraftRepository
    @Autowired lateinit var jdbc: JdbcTemplate
    @MockitoBean lateinit var ai: MissionDraftAiClient

    private val input = DraftInput(listOf("6국01-02"), null, ThinkingType.EVALUATE, 5, 5, InputType.NARRATIVE)
    private val placeholder = AiDraftRequest(emptyList(), ThinkingType.ANALYZE, emptyList(), 3, 3, InputType.CHOICE, emptyList())

    @Test
    fun `레플리카 4곳이 같은 주기에 생성해도 초안 하나는 한 곳만 ai를 부르고 시도는 1회`() {
        val draft = service.request(DraftCommand(UUID.randomUUID(), input))
        given(ai.generate(any(AiDraftRequest::class.java) ?: placeholder)).willAnswer {
            Thread.sleep(300) // 다른 레플리카가 점유를 시도하는 동안 ai 호출 중
            AiDraftResponse(MissionDraftTest.sampleDraft(), AiDraftChecks(true, emptyList()), DraftVersions("mission-draft@1", "m"))
        }

        val claimed = race(4) { service.generateNext(Instant.now()) }

        assertEquals(1, claimed.count { it })
        verify(ai, times(1)).generate(any(AiDraftRequest::class.java) ?: placeholder)
        assertEquals(DraftStatus.READY to 1, drafts.findById(draft.id)!!.let { it.status to it.attempts })
    }

    @Test
    fun `같은 초안을 동시에 4번 채택하면 미션은 하나, 나머지는 409`() {
        val draft = service.request(DraftCommand(UUID.randomUUID(), input))
        given(ai.generate(any(AiDraftRequest::class.java) ?: placeholder))
            .willReturn(AiDraftResponse(MissionDraftTest.sampleDraft(), AiDraftChecks(true, emptyList()), DraftVersions("mission-draft@1", "m")))
        service.generateNext(Instant.now())
        val before = jdbc.queryForObject("SELECT count(*) FROM mission WHERE source = 'LLM_DRAFT'", Int::class.java)!!

        val results = race(4) { runCatching { service.adopt(draft.id, UUID.randomUUID()) } }

        assertEquals(1, results.count { it.isSuccess })
        assertEquals(List(3) { "CONFLICT" }, results.mapNotNull { it.exceptionOrNull() }.map { errorCodeOf(it) })
        assertEquals(before + 1, jdbc.queryForObject("SELECT count(*) FROM mission WHERE source = 'LLM_DRAFT'", Int::class.java))
        assertEquals(results.single { it.isSuccess }.getOrThrow(), drafts.findById(draft.id)!!.missionId)
    }

    private fun <T> race(threads: Int, task: () -> T): List<T> {
        val ready = CountDownLatch(threads)
        val go = CountDownLatch(1)
        val pool = Executors.newFixedThreadPool(threads)
        val futures = (1..threads).map {
            pool.submit(Callable { ready.countDown(); go.await(); task() })
        }
        ready.await(10, TimeUnit.SECONDS)
        go.countDown()
        return futures.map { it.get(30, TimeUnit.SECONDS) }.also { pool.shutdown() }
    }

    companion object {
        private val postgres by lazy {
            PostgreSQLContainer<Nothing>("postgres:17.11-alpine").apply {
                start()
                Flyway.configure().dataSource(jdbcUrl, username, password)
                    .locations("classpath:db/migration").load().migrate()
                java.sql.DriverManager.getConnection(jdbcUrl, username, password).use { connection ->
                    connection.createStatement().use { it.execute(java.io.File(PostgresRepositoryTest.STANDARDS_SEED).readText()) }
                }
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
