package com.sagomungchi.core.reward

import org.flywaydb.core.Flyway
import org.junit.jupiter.api.Test
import org.testcontainers.containers.PostgreSQLContainer
import java.sql.DriverManager
import kotlin.test.assertEquals

/** #389 V29: 잠금 적용 전 저장한 테마·캐릭터를 포인트 차감 없이 해금 행으로 옮기고, 무료 항목은 옮기지 않는다. */
class LookUnlockMigrationTest {
    @Test fun `saved looks before V29 become unlocks without ledger rows`() {
        PostgreSQLContainer("postgres:17.11-alpine").use { db ->
            db.start()
            fun flyway(target: String) = Flyway.configure().dataSource(db.jdbcUrl, db.username, db.password)
                .locations("classpath:db/migration").target(target).load().migrate()
            flyway("28")
            DriverManager.getConnection(db.jdbcUrl, db.username, db.password).use { c ->
                c.createStatement().use { s ->
                    s.execute("""INSERT INTO student(pin_failed_count,id,nickname,grade,birth_year,is_demo,status,created_at,updated_at,look_theme,look_companion,look_updated_at) VALUES
                        (0,'00000000-0000-4000-8000-000000003891','a',3,2017,true,'ACTIVE',now(),now(),'space','mungchi','2026-11-01T00:00:00Z'),
                        (0,'00000000-0000-4000-8000-000000003892','b',4,2016,true,'ACTIVE',now(),now(),'lake','kongi','2026-11-02T00:00:00Z'),
                        (0,'00000000-0000-4000-8000-000000003893','c',5,2015,true,'ACTIVE',now(),now(),NULL,NULL,NULL)""")
                }
            }
            flyway("29")
            DriverManager.getConnection(db.jdbcUrl, db.username, db.password).use { c ->
                val rows = c.createStatement().use { s ->
                    s.executeQuery("SELECT student_id::text,item_key,ledger_id IS NULL,unlocked_at FROM student_look_unlock ORDER BY student_id,item_key").use { r ->
                        generateSequence { if (r.next()) listOf(r.getString(1).takeLast(4), r.getString(2), r.getBoolean(3), r.getObject(4, java.time.OffsetDateTime::class.java).toInstant().toString()) else null }.toList()
                    }
                }
                assertEquals(listOf(
                    listOf("3891", "THEME:space", true, "2026-11-01T00:00:00Z"),
                    listOf("3892", "COMPANION:kongi", true, "2026-11-02T00:00:00Z")), rows)
                val ledger = c.createStatement().use { s -> s.executeQuery("SELECT count(*) FROM reward_point_ledger").use { r -> r.next(); r.getInt(1) } }
                assertEquals(0, ledger)
            }
        }
    }
}
