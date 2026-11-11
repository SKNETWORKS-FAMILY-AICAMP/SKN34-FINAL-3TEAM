package com.sagomungchi.learning.knowledge

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning._common.persistence.TEST_POSTGRES_IMAGE
import org.flywaydb.core.Flyway
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.jdbc.datasource.DriverManagerDataSource
import org.springframework.jdbc.datasource.DataSourceTransactionManager
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.transaction.support.TransactionTemplate
import org.testcontainers.containers.PostgreSQLContainer
import java.io.File
import java.sql.DriverManager

/** Isolated pgvector DB using the real Flyway migrations, including #466 V14. */
@SpringBootTest(properties = [
    "app.internal.token=knowledge-test-token",
    "spring.rabbitmq.username=test", "spring.rabbitmq.password=test",
    "spring.rabbitmq.listener.simple.auto-startup=false",
    "app.mission-draft.enabled=false",
    "app.judgment.stuck-detection-enabled=false",
    // Public curriculum samples and deterministic test vectors, never production embedding calls.
    "app.knowledge.embedding=fake",
])
@AutoConfigureMockMvc
abstract class KnowledgePostgresTest {
    @Autowired private lateinit var fixtureJdbc: JdbcTemplate

    // Production requests open their own read transaction. Fixtures must be committed before HTTP.
    @BeforeEach
    @AfterEach
    fun resetKnowledgeFixture() {
        TransactionTemplate(DataSourceTransactionManager(requireNotNull(fixtureJdbc.dataSource))).executeWithoutResult {
            fixtureJdbc.execute("TRUNCATE " + tables.joinToString(","))
            tables.forEach { table -> fixtureJdbc.execute("INSERT INTO $table SELECT * FROM knowledge_test_snapshot.$table") }
        }
    }

    companion object {
        private val tables = listOf("knowledge_dataset", "knowledge_chunk", "knowledge_standard_semester", "knowledge_fits", "knowledge_covers", "knowledge_prerequisite")
        private val postgres by lazy {
            PostgreSQLContainer<Nothing>(TEST_POSTGRES_IMAGE).apply {
                start()
                // Matches the extension bootstrap prerequisite; V14 owns every knowledge table/index.
                DriverManager.getConnection(jdbcUrl, username, password).use { connection ->
                    connection.createStatement().use { it.execute("CREATE EXTENSION IF NOT EXISTS vector") }
                }
                Flyway.configure().dataSource(jdbcUrl, username, password)
                    .locations("classpath:db/migration").load().migrate()
                DriverManager.getConnection(jdbcUrl, username, password).use { connection ->
                    // Actual loader checks statements against this published achievement-standard seed.
                    connection.createStatement().use {
                        it.execute(File(PostgresRepositoryTest.STANDARDS_SEED).readText(Charsets.UTF_8))
                    }
                }
                val jdbc = JdbcTemplate(DriverManagerDataSource(jdbcUrl, username, password))
                KnowledgeFixtures(jdbc, jacksonObjectMapper()).load()
                jdbc.execute("CREATE SCHEMA knowledge_test_snapshot")
                tables.forEach { table -> jdbc.execute("CREATE TABLE knowledge_test_snapshot.$table AS TABLE $table") }
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
