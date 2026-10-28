package com.sagomungchi.core._common.persistence

import org.flywaydb.core.Flyway
import com.sagomungchi.core._common.messaging.OutboxRelay
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.transaction.annotation.Transactional
import org.testcontainers.containers.PostgreSQLContainer

/** One disposable DB per test JVM. Each test rolls back; Ryuk removes the container on JVM exit. */
@SpringBootTest(properties = [
    "app.internal.token=repository-test-token",
    "app.auth.jwt-secret=dGVzdC1hdXRoLXNlY3JldC0zMi1ieXRlcy1sb25nLWtleSE=",
    "spring.rabbitmq.username=test", "spring.rabbitmq.password=test",
    "spring.rabbitmq.listener.simple.auto-startup=false",
    "spring.datasource.hikari.maximum-pool-size=4", "spring.datasource.hikari.minimum-idle=0",
])
@Transactional
abstract class PostgresRepositoryTest {
    // Repository tests do not publish messages or run the background relay.
    @MockitoBean lateinit var notificationListenerContainer: org.springframework.data.redis.listener.RedisMessageListenerContainer
    @MockitoBean lateinit var outboxRelay: OutboxRelay

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
