package com.sagomungchi.core.room

import com.sagomungchi.core.admin.account
import com.sagomungchi.core.report.child
import com.sagomungchi.core.report.parent
import org.flywaydb.core.Flyway
import org.flywaydb.core.api.FlywayException
import org.junit.jupiter.api.Test
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.jdbc.datasource.DriverManagerDataSource
import org.testcontainers.containers.PostgreSQLContainer
import org.testcontainers.junit.jupiter.Container
import org.testcontainers.junit.jupiter.Testcontainers
import java.util.UUID
import kotlin.test.*

/** V50 → V51을 격리된 DB에서 실제 실행한다. 운영 데이터는 접근하지 않는다. */
@Testcontainers
class RoomDecorMigrationTest {
    companion object {
        @Container @JvmField
        val postgres = PostgreSQLContainer("postgres:17.11-alpine")
    }

    private fun withV50(block: (JdbcTemplate, Flyway) -> Unit) {
        val schema = "decor_" + UUID.randomUUID().toString().replace("-", "")
        val separator = if ('?' in postgres.jdbcUrl) "&" else "?"
        val dataSource = DriverManagerDataSource(
            "${postgres.jdbcUrl}${separator}currentSchema=$schema", postgres.username, postgres.password)
        fun configuration() = Flyway.configure().dataSource(dataSource).schemas(schema).defaultSchema(schema)
            .locations("classpath:db/migration")
        configuration().target("50").load().migrate()
        val jdbc = JdbcTemplate(dataSource)
        try { block(jdbc, configuration().load()) }
        finally { jdbc.execute("DROP SCHEMA $schema CASCADE") }
    }

    @Test fun `empty V50 upgrades to grid columns and reruns without changes`() = withV50 { jdbc, flyway ->
        assertEquals(1, flyway.migrate().migrationsExecuted)
        assertEquals(0, flyway.migrate().migrationsExecuted)
        assertEquals(setOf("student_id", "surface", "cell_col", "cell_row", "look_item_id", "saved_at"),
            jdbc.queryForList("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='room_decor_spot'",
                String::class.java).toSet())
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='room_decor_spot' AND (is_nullable='YES' OR column_default IS NOT NULL)", Int::class.java))
    }

    @Test fun `existing V50 placements stop migration without losing rows or changing old schema`() = withV50 { jdbc, flyway ->
        val student = child(jdbc, parent(jdbc))
        val admin = account(jdbc, "ADMIN", "CONTENT")
        val item = UUID.randomUUID()
        jdbc.update("INSERT INTO look_item(id,code,slot,name,price_points,asset_key,status,created_by,created_at,updated_at) VALUES(?,'MIGRATION_DECOR','DECOR','시험 소품',1,'decor/test','ON_SALE',?,now(),now())", item, admin)
        jdbc.update("INSERT INTO room_decor_spot(student_id,spot_no,look_item_id,saved_at) VALUES(?,8,?,now())", student, item)
        val before = jdbc.queryForList("SELECT * FROM room_decor_spot")
        val failure = assertFailsWith<FlywayException> { flyway.migrate() }
        assertTrue(generateSequence<Throwable>(failure) { it.cause }.any { it.message?.contains("existing placements") == true })
        assertEquals(before, jdbc.queryForList("SELECT * FROM room_decor_spot"))
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='room_decor_spot' AND column_name='surface'", Int::class.java))
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM flyway_schema_history WHERE version='51'", Int::class.java))
    }
}
