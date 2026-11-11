package com.sagomungchi.learning.knowledge

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
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
import org.testcontainers.utility.DockerImageName
import java.sql.DriverManager

/** Isolated pgvector DB; existing Flyway V1..V13 then test-only C2/C3. No production migration. */
@SpringBootTest(properties = [
    "app.internal.token=knowledge-test-token",
    "spring.rabbitmq.username=test", "spring.rabbitmq.password=test",
    "spring.rabbitmq.listener.simple.auto-startup=false",
    "app.mission-draft.enabled=false",
    "app.judgment.stuck-detection-enabled=false",
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
            PostgreSQLContainer<Nothing>(
                DockerImageName.parse("pgvector/pgvector:0.8.7-pg17-trixie").asCompatibleSubstituteFor("postgres"),
            ).apply {
                start()
                Flyway.configure().dataSource(jdbcUrl, username, password)
                    .locations("classpath:db/migration").load().migrate()
                DriverManager.getConnection(jdbcUrl, username, password).use { connection ->
                    val ddl = requireNotNull(KnowledgePostgresTest::class.java.getResource("/knowledge/schema.sql"))
                        .readText(Charsets.UTF_8)
                    connection.createStatement().use { it.execute(ddl) }
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
