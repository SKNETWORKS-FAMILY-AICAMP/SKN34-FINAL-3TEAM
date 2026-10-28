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
])
@Transactional
abstract class PostgresRepositoryTest {
    // Core access is a separate HTTP contract test; repository fixtures use the free permit.
    @org.springframework.test.context.bean.override.mockito.MockitoBean
    lateinit var paymentUsage: com.sagomungchi.learning.judgment.client.PaymentUsageClient
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
