package com.sagomungchi.learning.mission.service

import com.sagomungchi.learning.mission.domain.Choice
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.MissionCommand
import com.sagomungchi.learning.mission.domain.ThinkingType
import org.flywaydb.core.Flyway
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.testcontainers.containers.PostgreSQLContainer
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlin.test.assertEquals

/**
 * 같은 미션 동시 수정 (#145): 미션 행 잠금으로 버전 번호를 차례로 매겨 (mission_id, version) UK 충돌 없이 모두 저장.
 * 요청마다 실제로 커밋해야 해서 AnswerConcurrencyTest처럼 별도 컨테이너를 씀
 */
@SpringBootTest(properties = [
    "app.internal.token=concurrency-test-token",
    "spring.rabbitmq.username=test", "spring.rabbitmq.password=test",
    "spring.rabbitmq.listener.simple.auto-startup=false",
])
class AdminMissionConcurrencyTest {
    @Autowired lateinit var service: MissionService

    @Test
    fun `같은 미션을 동시에 8번 고치면 버전 2~9가 하나씩, 실패 없음`() {
        val id = service.create(command("처음")).id
        val requests = 8
        val ready = CountDownLatch(requests)
        val go = CountDownLatch(1)
        val pool = Executors.newFixedThreadPool(requests)
        val results = (1..requests).map { n ->
            pool.submit<Int> {
                ready.countDown()
                go.await()
                service.update(id, command("수정 $n")).version
            }
        }
        ready.await(10, TimeUnit.SECONDS)
        go.countDown()
        val versions = results.map { it.get(30, TimeUnit.SECONDS) }.also { pool.shutdown() }

        assertEquals((2..9).toList(), versions.sorted())
        assertEquals((1..9).toList(), service.getForAdmin(id).versions.map { it.version })
        assertEquals(9, service.getForAdmin(id).currentVersion)
    }

    private fun command(title: String) = MissionCommand(
        authorId = UUID.randomUUID(), title = title, subject = "과학", gradeMin = 5, gradeMax = 5, thinkingType = ThinkingType.ANALYZE,
        inputType = InputType.CHOICE, question = "질문", guide = null, sceneUri = null, staticSceneUri = null,
        achievementStandards = emptyList(), choices = listOf(Choice("c1", "가")), categories = emptyList(), answerUnit = null,
        inputTemplate = emptyList(), demoOnly = false,
    )

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
