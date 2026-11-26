package com.sagomungchi.learning.memory.repository

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning.judgment.domain.JudgmentResult
import com.sagomungchi.learning.memory.domain.MemoryBookLine
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.stereotype.Repository
import java.sql.ResultSet
import java.time.Instant
import java.time.OffsetDateTime
import java.util.UUID

/** 회차 버전의 그림책용 이야기 칸 */
data class BookStoryRow(val intro: String, val bigQuestion: String?, val outroImageUri: String?)

/** 회차 버전 요일의 문제 글·장면 그림·문제 전 대화. 미션 버전은 요일 고정값, 없으면 게시본·현재본 */
data class BookDayRow(val dayOfWeek: Int, val missionId: UUID, val question: String, val sceneUri: String?, val dialogue: List<MemoryBookLine>)

/** 시도가 쓴 미션 버전의 문제 글·장면 그림 */
data class BookAttemptRow(val attemptId: UUID, val completedAt: Instant?, val question: String, val sceneUri: String?)

data class BookAnswerRow(
    val attemptId: UUID,
    val version: Int,
    val text: String?,
    val followupType: String?,
    val followupQuestion: String?,
    val result: JudgmentResult?,
)

data class BookReflectionRow(val attemptId: UUID, val difficulty: String?, val text: String?)

/**
 * 추억 그림책 회차 조립 조회 (docs/proposals/memory-book.md). 읽기만 하며 learning_db 안에서 끝난다.
 * 검색 문서(MemorySearchRepository.register)처럼 시도·답변·미션 버전 표를 직접 읽는다. 시도는 호출자가 그 학생 것으로 고른 ID만
 */
@Repository
class MemoryBookRepository(private val jdbc: JdbcTemplate, private val json: ObjectMapper) {
    fun story(versionId: UUID): BookStoryRow = jdbc.queryForObject(
        "SELECT intro, big_question, outro_image_uri FROM weekly_theme_version WHERE id = ?",
        { rs, _ -> BookStoryRow(rs.getString("intro"), rs.getString("big_question"), rs.getString("outro_image_uri")) },
        versionId,
    )!!

    fun days(versionId: UUID): List<BookDayRow> = jdbc.query(
        """
        SELECT d.day_of_week, d.mission_id, v.question, COALESCE(v.static_scene_uri, v.scene_uri) scene_uri, d.dialogue::text dialogue
        FROM weekly_theme_day d
        JOIN mission m ON m.id = d.mission_id
        JOIN mission_version v ON v.id = COALESCE(d.mission_version_id, m.published_version_id, m.current_version_id)
        WHERE d.theme_version_id = ?
        ORDER BY d.day_of_week
        """.trimIndent(),
        { rs, _ ->
            BookDayRow(rs.getInt("day_of_week"), rs.uuid("mission_id"), rs.getString("question"), rs.getString("scene_uri"), dialogue(rs.getString("dialogue")))
        },
        versionId,
    )

    fun attempts(studentId: UUID, ids: List<UUID>): List<BookAttemptRow> = if (ids.isEmpty()) emptyList() else jdbc.query(
        """
        SELECT a.id, a.completed_at, v.question, COALESCE(v.static_scene_uri, v.scene_uri) scene_uri
        FROM attempt a JOIN mission_version v ON v.id = a.mission_version_id
        WHERE a.student_id = ? AND a.id = ANY(?)
        """.trimIndent(),
        { rs, _ ->
            BookAttemptRow(rs.uuid("id"), rs.getObject("completed_at", OffsetDateTime::class.java)?.toInstant(),
                rs.getString("question"), rs.getString("scene_uri"))
        },
        studentId, ids.toTypedArray(),
    )

    /**
     * 답변과 그 판정의 지금 결과. 판정은 답변당 1행(uq_judgment_answer_id), 결과는 DONE일 때만 있다.
     * 정정(#80)이 있으면 최신 정정 결과(created_at 가장 늦은 행, CorrectionMapper.findTarget과 같은 규칙)
     */
    fun answers(ids: List<UUID>): List<BookAnswerRow> = if (ids.isEmpty()) emptyList() else jdbc.query(
        """
        SELECT an.attempt_id, an.version, an.plain_text, f.type followup_type, f.question followup_question,
               CASE WHEN j.process_status = 'DONE' THEN COALESCE(c.result, j.result) END result
        FROM answer an
        LEFT JOIN followup f ON f.id = an.followup_id
        LEFT JOIN judgment j ON j.answer_id = an.id
        LEFT JOIN LATERAL (
            SELECT jc.corrected ->> 'result' AS result FROM judgment_correction jc WHERE jc.judgment_id = j.id
            ORDER BY jc.created_at DESC, jc.id DESC LIMIT 1
        ) c ON TRUE
        WHERE an.attempt_id = ANY(?)
        ORDER BY an.attempt_id, an.version
        """.trimIndent(),
        { rs, _ ->
            BookAnswerRow(rs.uuid("attempt_id"), rs.getInt("version"), rs.getString("plain_text"),
                rs.getString("followup_type"), rs.getString("followup_question"),
                rs.getString("result")?.let(JudgmentResult::valueOf))
        },
        ids.toTypedArray(),
    )

    fun reflections(ids: List<UUID>): List<BookReflectionRow> = if (ids.isEmpty()) emptyList() else jdbc.query(
        "SELECT attempt_id, difficulty, changed_text FROM reflection WHERE attempt_id = ANY(?)",
        { rs, _ -> BookReflectionRow(rs.uuid("attempt_id"), rs.getString("difficulty"), rs.getString("changed_text")) },
        ids.toTypedArray(),
    )

    /** `weekly_theme_day.dialogue` JSON 배열 `[{speaker, text}]`. 빈 글·모양이 다른 줄은 건너뜀 */
    private fun dialogue(raw: String?): List<MemoryBookLine> {
        val node = raw?.let(json::readTree)?.takeIf { it.isArray } ?: return emptyList()
        return node.mapNotNull { line ->
            val text = line.path("text").takeIf { it.isTextual }?.asText()?.takeIf { it.isNotBlank() } ?: return@mapNotNull null
            MemoryBookLine(line.path("speaker").takeIf { it.isTextual }?.asText().orEmpty(), text)
        }
    }

    private fun ResultSet.uuid(column: String): UUID = getObject(column, UUID::class.java)
}
