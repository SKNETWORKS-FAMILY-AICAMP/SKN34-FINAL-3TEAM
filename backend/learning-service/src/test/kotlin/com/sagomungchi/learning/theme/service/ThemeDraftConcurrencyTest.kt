package com.sagomungchi.learning.theme.service

import com.sagomungchi.learning._common.exception.errorCodeOf
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning.mission.domain.DraftStatus
import com.sagomungchi.learning.record.domain.Period
import com.sagomungchi.learning.theme.ThemeDraftFixtures
import com.sagomungchi.learning.theme.client.AiThemeDraftRequest
import com.sagomungchi.learning.theme.client.ThemeDraftAiClient
import com.sagomungchi.learning.theme.domain.ThemeGrade
import com.sagomungchi.learning.theme.domain.ThemeWeek
import com.sagomungchi.learning.theme.repository.ThemeDraftRepository
import com.zaxxer.hikari.HikariDataSource
import org.flywaydb.core.Flyway
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.BDDMockito.given
import org.mockito.Mockito.any
import org.mockito.Mockito.times
import org.mockito.Mockito.verify
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.boot.test.web.server.LocalServerPort
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.testcontainers.containers.PostgreSQLContainer
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Clock
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.util.UUID
import java.util.concurrent.Callable
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import javax.sql.DataSource
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * 테마 초안 동시 실행 (#438, class-diagram 4.4): 레플리카가 주간 자동·생성·채택을 같이 돌려도 학년·주당 자동 초안 하나·초안 하나는 한 곳만 생성·
 * 테마 하나. 생성이 느린 ai를 기다리는 동안에도 웹 요청 스레드가 내부 API에 바로 답하고 DB 연결을 잡고 있지 않음(지식 API 수용, #469 전제).
 * 요청마다 실제로 커밋해야 해서 MissionDraftConcurrencyTest처럼 별도 컨테이너를 씀
 */
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = [
        "app.internal.token=concurrency-test-token",
        "spring.rabbitmq.username=test", "spring.rabbitmq.password=test",
        "spring.rabbitmq.listener.simple.auto-startup=false",
        "app.mission-draft.enabled=false",
        "app.theme-draft.enabled=false",
    ],
)
class ThemeDraftConcurrencyTest {
    @Autowired lateinit var service: ThemeDraftService
    @Autowired lateinit var drafts: ThemeDraftRepository
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var dataSource: DataSource
    @MockitoBean lateinit var ai: ThemeDraftAiClient
    @LocalServerPort var port: Int = 0

    private val placeholder = AiThemeDraftRequest(3, 3, LocalDate.EPOCH, null, emptyList(), emptyList())
    private fun anyRequest(): AiThemeDraftRequest = any(AiThemeDraftRequest::class.java) ?: placeholder

    /** 테스트마다 다른 주를 써서 커밋된 다른 테스트 행과 섞이지 않게 */
    private fun week(offset: Long) = ThemeWeek.startOf(LocalDate.now(Clock.system(Period.KST))).plusWeeks(offset)

    /** 커밋되는 DB라 다른 테스트가 남긴 생성 중 초안을 생성 작업이 잡지 않게 치움 */
    @BeforeEach
    fun clearGenerating() {
        jdbc.update("UPDATE theme_draft SET status = 'DISCARDED' WHERE status = 'GENERATING'")
    }

    private fun request(weekOffset: Long) =
        service.request(ThemeDraftCommand(UUID.randomUUID(), ThemeGrade.G5, week(weekOffset), "도서관", emptyList()))

    @Test
    fun `레플리카 4곳이 주간 자동을 같이 돌려도 학년·주당 자동 초안 하나`() {
        val created = race(4) { service.createWeekly(week(10)) }

        assertEquals(4, created.sum())
        assertEquals(listOf("G3", "G4", "G5", "G6"), jdbc.queryForList(
            "SELECT grade FROM theme_draft WHERE source = 'AUTO' AND week_start = ? ORDER BY grade", String::class.java, week(10)))
    }

    @Test
    fun `레플리카 4곳이 같은 주기에 생성해도 초안 하나는 한 곳만 ai를 부르고 시도는 1회, 채택을 동시에 4번 해도 테마 하나`() {
        val draft = request(11)
        val input = drafts.findById(draft.id)!!.input
        given(ai.generate(anyRequest())).willAnswer {
            Thread.sleep(300) // 다른 레플리카가 점유를 시도하는 동안 ai 호출 중
            ThemeDraftFixtures.response(ThemeDraftFixtures.output(input))
        }

        val claimed = race(4) { service.generateNext(Instant.now()) }

        assertEquals(1, claimed.count { it })
        verify(ai, times(1)).generate(anyRequest())
        assertEquals(DraftStatus.READY to 1, drafts.findById(draft.id)!!.let { it.status to it.attempts })

        val themesBefore = jdbc.queryForObject("SELECT count(*) FROM weekly_theme", Int::class.java)!!
        val missionsBefore = jdbc.queryForObject("SELECT count(*) FROM mission WHERE source = 'LLM_THEME'", Int::class.java)!!
        val results = race(4) { runCatching { service.adopt(draft.id, UUID.randomUUID()) } }

        assertEquals(1, results.count { it.isSuccess })
        assertEquals(List(3) { "CONFLICT" }, results.mapNotNull { it.exceptionOrNull() }.map { errorCodeOf(it) })
        assertEquals(themesBefore + 1, jdbc.queryForObject("SELECT count(*) FROM weekly_theme", Int::class.java))
        assertEquals(missionsBefore + 5, jdbc.queryForObject("SELECT count(*) FROM mission WHERE source = 'LLM_THEME'", Int::class.java))
        assertEquals(results.single { it.isSuccess }.getOrThrow().themeId, drafts.findById(draft.id)!!.themeId)
    }

    @Test
    fun `생성이 느린 ai를 기다리는 동안 내부 API는 바로 답하고 생성 작업은 DB 연결을 잡고 있지 않음`() {
        val draft = request(12)
        val input = drafts.findById(draft.id)!!.input
        val calling = CountDownLatch(1)
        val release = CountDownLatch(1)
        given(ai.generate(anyRequest())).willAnswer {
            calling.countDown()
            release.await(30, TimeUnit.SECONDS) // 실제로는 최대 16분
            ThemeDraftFixtures.response(ThemeDraftFixtures.output(input))
        }
        val worker = Executors.newSingleThreadExecutor()
        val generation = worker.submit(Callable { service.generateNext(Instant.now()) })
        try {
            assertTrue(calling.await(10, TimeUnit.SECONDS))
            assertEquals(0, (dataSource as HikariDataSource).hikariPoolMXBean.activeConnections)

            val started = System.nanoTime()
            val response = HttpClient.newHttpClient().send(
                HttpRequest.newBuilder(URI.create("http://localhost:$port/internal/admin/theme-drafts/${draft.id}"))
                    .header("X-Internal-Token", "concurrency-test-token").header("X-User-Role", "ADMIN")
                    .header("X-User-Id", UUID.randomUUID().toString()).timeout(Duration.ofSeconds(5)).GET().build(),
                HttpResponse.BodyHandlers.ofString(),
            )
            val elapsed = Duration.ofNanos(System.nanoTime() - started)

            assertEquals(200, response.statusCode(), response.body())
            assertTrue("\"status\":\"GENERATING\"" in response.body(), response.body()) // 아직 생성 중
            assertTrue(elapsed < Duration.ofSeconds(2), elapsed.toString())
        } finally {
            release.countDown()
            worker.shutdown()
        }
        assertTrue(generation.get(30, TimeUnit.SECONDS))
        assertEquals(DraftStatus.READY, drafts.findById(draft.id)!!.status)
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
