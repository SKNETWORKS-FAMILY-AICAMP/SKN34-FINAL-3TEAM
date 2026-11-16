package com.sagomungchi.learning.theme.repository

import com.sagomungchi.learning._common.persistence.TEST_POSTGRES_IMAGE
import org.flywaydb.core.Flyway
import org.junit.jupiter.api.AfterAll
import org.junit.jupiter.api.BeforeAll
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.TestInstance
import org.testcontainers.containers.PostgreSQLContainer
import java.sql.Connection
import java.sql.DriverManager
import java.sql.SQLException
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNull

/**
 * #438 학년 전환 마이그레이션(V15·V16, ERD 4.2.1): V14(#466 지식 저장소)까지 적용한 DB에 학년군 테마를 넣고 최신까지 올린다.
 * 원래 행은 낮은 학년(G3·G5)으로 바뀌고, 높은 학년(G4·G6)은 테마·버전·요일이 원래 ID와 학년으로 정한 ID로 복사되며,
 * 게시 1개 제약은 학년·주 단위가 된다. 시도·열람 기록은 원래 행을 그대로 가리킨다
 */
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class ThemeGradeMigrationTest {
    private val postgres = PostgreSQLContainer<Nothing>(TEST_POSTGRES_IMAGE)
    private lateinit var db: Connection

    @BeforeAll
    fun migrate() {
        postgres.start()
        flyway("14").migrate()
        db = DriverManager.getConnection(postgres.jdbcUrl, postgres.username, postgres.password)
        db.createStatement().use { s ->
            s.execute(
                """
                INSERT INTO mission (id, code, status, demo_only, source, sort_order, created_by, created_at, updated_at)
                VALUES ('$MISSION', 'M-TEST', 'DRAFT', false, 'MANUAL', 1, '$AUTHOR', now(), now());
                """.trimIndent(),
            )
            insertTheme(s, LOWER_THEME, LOWER_VERSION, "G3_4", "PUBLISHED", published = true)
            insertTheme(s, UPPER_THEME, UPPER_VERSION, "G5_6", "DRAFT", published = false)
            s.execute(
                """
                INSERT INTO theme_review_view (student_id, week_start, theme_id, viewed_at)
                VALUES ('$AUTHOR', '2026-11-09', '$LOWER_THEME', now());
                """.trimIndent(),
            )
        }
        flyway(null).migrate()
    }

    @AfterAll
    fun stop() {
        db.close()
        postgres.stop()
    }

    @Test
    fun `원래 행은 낮은 학년으로 바뀌고 높은 학년 복사본이 같은 내용으로 생긴다`() {
        assertEquals("G3", one("SELECT grade FROM weekly_theme WHERE id = '$LOWER_THEME'"))
        assertEquals("G5", one("SELECT grade FROM weekly_theme WHERE id = '$UPPER_THEME'"))

        val g4 = copyId(LOWER_THEME, "G4")
        val g4Version = copyId(LOWER_VERSION, "G4")
        assertEquals("G4|PUBLISHED|$g4Version|$g4Version|$g4Version",
            one("SELECT grade || '|' || status || '|' || current_version_id || '|' || published_version_id || '|' || review_version_id FROM weekly_theme WHERE id = '$g4'"))
        assertEquals("1|테마 제목|월요일 소개", one("SELECT version || '|' || title || '|' || intro FROM weekly_theme_version WHERE id = '$g4Version' AND theme_id = '$g4'"))
        assertEquals("1|$MISSION", one("SELECT day_of_week || '|' || mission_id FROM weekly_theme_day WHERE theme_version_id = '$g4Version'"))

        val g6 = copyId(UPPER_THEME, "G6")
        assertEquals("G6|DRAFT", one("SELECT grade || '|' || status FROM weekly_theme WHERE id = '$g6'"))
        assertNull(one("SELECT published_version_id FROM weekly_theme WHERE id = '$g6'"))
        assertEquals("4", one("SELECT count(*) FROM weekly_theme"))
        assertEquals("$LOWER_THEME", one("SELECT theme_id FROM theme_review_view"))
    }

    @Test
    fun `학년군 칸은 없어지고 학년은 G3~G6만 받는다`() {
        assertFalse(exists("SELECT 1 FROM information_schema.columns WHERE table_name = 'weekly_theme' AND column_name = 'grade_band'"))
        assertEquals("23514", sqlState("UPDATE weekly_theme SET grade = 'G3_4' WHERE id = '$LOWER_THEME'"))
        assertEquals("23502", sqlState("UPDATE weekly_theme SET grade = NULL WHERE id = '$LOWER_THEME'"))
    }

    @Test
    fun `게시 테마는 학년·주마다 하나`() {
        // 같은 주 G3·G4가 함께 게시돼 있음(복사본). 같은 학년·주의 둘째 게시본은 부분 UK에 걸림
        assertEquals("2", one("SELECT count(*) FROM weekly_theme WHERE week_start = '2026-11-09' AND status = 'PUBLISHED'"))
        assertEquals("23505", sqlState(
            """
            INSERT INTO weekly_theme (id, grade, week_start, status, current_version_id, created_by, created_at, updated_at)
            SELECT '00000000-0000-4000-8000-000000000999', grade, week_start, 'PUBLISHED', current_version_id, created_by, now(), now()
            FROM weekly_theme WHERE id = '$LOWER_THEME'
            """.trimIndent(),
        ))
    }

    private fun insertTheme(s: java.sql.Statement, theme: String, version: String, band: String, status: String, published: Boolean) {
        val publishedVersion = if (published) "'$version'" else "NULL"
        s.execute(
            """
            BEGIN;
            SET CONSTRAINTS fk_weekly_theme_current_version_id, fk_weekly_theme_published_version_id,
                fk_weekly_theme_review_version_id DEFERRED;
            INSERT INTO weekly_theme (id, grade_band, week_start, status, current_version_id, published_version_id, review_version_id,
                                      created_by, published_at, created_at, updated_at)
            VALUES ('$theme', '$band', '2026-11-09', '$status', '$version', $publishedVersion, $publishedVersion,
                    '$AUTHOR', ${if (published) "now()" else "NULL"}, now(), now());
            INSERT INTO weekly_theme_version (id, theme_id, version, title, intro, created_by, created_at)
            VALUES ('$version', '$theme', 1, '테마 제목', '월요일 소개', '$AUTHOR', now());
            INSERT INTO weekly_theme_day (theme_version_id, day_of_week, mission_id) VALUES ('$version', 1, '$MISSION');
            COMMIT;
            """.trimIndent(),
        )
    }

    private fun flyway(target: String?) = Flyway.configure()
        .dataSource(postgres.jdbcUrl, postgres.username, postgres.password)
        .locations("classpath:db/migration")
        .apply { if (target != null) target(target) }
        .load()

    /** V15와 같은 규칙: md5(원래 id || ':' || 학년)::uuid */
    private fun copyId(id: String, grade: String): String = one("SELECT md5('$id' || ':' || '$grade')::uuid")!!

    private fun one(sql: String): String? = db.createStatement().use { s ->
        s.executeQuery(sql).use { if (it.next()) it.getString(1) else null }
    }

    private fun exists(sql: String): Boolean = db.createStatement().use { s -> s.executeQuery(sql).use { it.next() } }

    private fun sqlState(sql: String): String? {
        db.autoCommit = false
        return try {
            assertFailsWith<SQLException> { db.createStatement().use { it.execute(sql) } }.sqlState
        } finally {
            db.rollback()
            db.autoCommit = true
        }
    }

    private companion object {
        const val AUTHOR = "00000000-0000-4000-8000-000000000001"
        const val MISSION = "00000000-0000-4000-8000-000000000101"
        const val LOWER_THEME = "00000000-0000-4000-8000-000000000201"
        const val LOWER_VERSION = "00000000-0000-4000-8000-000000000202"
        const val UPPER_THEME = "00000000-0000-4000-8000-000000000203"
        const val UPPER_VERSION = "00000000-0000-4000-8000-000000000204"
    }
}
