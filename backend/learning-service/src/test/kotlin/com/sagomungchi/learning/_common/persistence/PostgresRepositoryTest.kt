package com.sagomungchi.learning._common.persistence

import org.flywaydb.core.Flyway
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.transaction.annotation.Transactional
import org.testcontainers.containers.PostgreSQLContainer

/** One disposable DB per test JVM. Each test rolls back; Ryuk removes the container on JVM exit. */
@SpringBootTest(properties = [
    "app.internal.token=repository-test-token",
    "spring.rabbitmq.username=test", "spring.rabbitmq.password=test",
    "spring.rabbitmq.listener.simple.auto-startup=false",
    // 초안 주기 생성은 ai를 부르므로 테스트에서는 끄고 서비스를 직접 부름 (#353)
    "app.mission-draft.enabled=false",
])
@Transactional
abstract class PostgresRepositoryTest {
    // Core access is a separate HTTP contract test; repository fixtures use the free permit.
    @org.springframework.test.context.bean.override.mockito.MockitoBean
    lateinit var paymentUsage: com.sagomungchi.learning.judgment.client.PaymentUsageClient
    companion object {
        const val STANDARDS_SEED = "db/seed/achievement_standards.sql"

        private val postgres by lazy {
            PostgreSQLContainer<Nothing>("postgres:17.11-alpine").apply {
                start()
                Flyway.configure().dataSource(jdbcUrl, username, password)
                    .locations("classpath:db/migration").load().migrate()
                // 성취기준 표 시드(#353): 게시 검사가 표를 읽음. 시드 파일이 스키마에 그대로 들어가는지도 함께 확인
                java.sql.DriverManager.getConnection(jdbcUrl, username, password).use { connection ->
                    connection.createStatement().use { it.execute(java.io.File(STANDARDS_SEED).readText()) }
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
