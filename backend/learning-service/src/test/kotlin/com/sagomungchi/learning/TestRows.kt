package com.sagomungchi.learning

import org.springframework.jdbc.core.JdbcTemplate
import java.time.OffsetDateTime
import java.util.UUID

/** Repository 테스트용 합성 행. 직접 만든 값만 사용 */
class TestRows(private val jdbc: JdbcTemplate) {
    val author: UUID = UUID.randomUUID()
    val now: OffsetDateTime = OffsetDateTime.parse("2026-10-27T10:00:00+09:00")

    data class SeededMission(val id: UUID, val versionId: UUID, val rubricVersionId: UUID, val hintIds: List<UUID>)

    /** 미션 + 버전 1 + 기준표 버전 1 + 생각 열기 질문, 현재 버전으로 연결 */
    fun mission(
        status: String = "PUBLISHED",
        grade: Int = 3,
        title: String = "미션",
        hints: List<String> = listOf("첫 질문", "둘째 질문"),
        demoOnly: Boolean = false,
    ): SeededMission {
        val id = UUID.randomUUID()
        jdbc.update(
            """INSERT INTO mission (id, code, status, demo_only, sort_order, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, 1, ?, ?, ?)""",
            id, "TEST-$id", status, demoOnly, author, now, now,
        )
        val versionId = addVersion(id, version = 1, title = title, grade = grade)
        val rubricVersionId = UUID.randomUUID()
        jdbc.update(
            "INSERT INTO rubric_version (id, mission_id, version, created_by, created_at) VALUES (?, ?, 1, ?, ?)",
            rubricVersionId, id, author, now,
        )
        val hintIds = hints.mapIndexed { index, content ->
            UUID.randomUUID().also {
                jdbc.update(
                    "INSERT INTO hint_question (id, rubric_version_id, seq, content) VALUES (?, ?, ?, ?)",
                    it, rubricVersionId, index + 1, content,
                )
            }
        }
        jdbc.update(
            "UPDATE mission SET current_version_id = ?, current_rubric_version_id = ? WHERE id = ?",
            versionId, rubricVersionId, id,
        )
        return SeededMission(id, versionId, rubricVersionId, hintIds)
    }

    /** 미션 버전 추가 (현재 버전으로 바꾸지는 않음) */
    fun addVersion(missionId: UUID, version: Int, title: String, grade: Int = 3): UUID {
        val id = UUID.randomUUID()
        jdbc.update(
            """INSERT INTO mission_version (id, mission_id, version, title, subject, grade_min, grade_max,
                   thinking_type, input_type, question, created_by, created_at)
               VALUES (?, ?, ?, ?, '과학', ?, ?, 'ANALYZE', 'NARRATIVE', '질문', ?, ?)""",
            id, missionId, version, title, grade, grade, author, now,
        )
        return id
    }
}
