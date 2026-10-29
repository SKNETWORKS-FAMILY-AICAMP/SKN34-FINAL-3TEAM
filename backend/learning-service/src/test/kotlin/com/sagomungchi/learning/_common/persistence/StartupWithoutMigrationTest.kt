package com.sagomungchi.learning._common.persistence

import org.flywaydb.core.Flyway
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.context.ApplicationContext
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.annotation.DirtiesContext
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.testcontainers.containers.PostgreSQLContainer
import org.testcontainers.junit.jupiter.Container
import org.testcontainers.junit.jupiter.Testcontainers
import kotlin.test.assertEquals
import kotlin.test.assertTrue

@SpringBootTest(properties = [
    "app.internal.token=startup-test-token",
    "spring.rabbitmq.username=test", "spring.rabbitmq.password=test",
    "spring.rabbitmq.listener.simple.auto-startup=false",
])
@Testcontainers
@DirtiesContext
class StartupWithoutMigrationTest {
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var context: ApplicationContext

    @Test
    fun `application starts on empty DB without running migrations even with Flyway on classpath`() {
        assertTrue(context.getBeansOfType(Flyway::class.java).isEmpty())
        assertEquals(0L, jdbc.queryForObject(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'", Long::class.java,
        ))
    }

    companion object {
        @Container @JvmField
        val postgres = PostgreSQLContainer<Nothing>("postgres:17.11-alpine")

        @JvmStatic @DynamicPropertySource
        fun database(registry: DynamicPropertyRegistry) {
            registry.add("spring.datasource.url", postgres::getJdbcUrl)
            registry.add("spring.datasource.username", postgres::getUsername)
            registry.add("spring.datasource.password", postgres::getPassword)
        }
    }
}
