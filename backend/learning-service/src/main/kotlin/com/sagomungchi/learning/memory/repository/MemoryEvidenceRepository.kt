package com.sagomungchi.learning.memory.repository

import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.stereotype.Repository
import java.time.LocalDate
import java.util.UUID

data class MemoryEvidenceRow(
    val attemptId: UUID, val themeId: UUID, val weekStart: LocalDate,
    val title: String, val question: String, val answer: String, val model: String, val score: Double,
)

@Repository
class MemoryEvidenceRepository(private val jdbc: JdbcTemplate) {
    fun find(student: UUID, before: LocalDate, ids: List<UUID>, vector: List<Double>? = null): List<MemoryEvidenceRow> {
        require(ids.size in 1..3)
        val score = if (vector == null) "0.0" else "1-(d.embedding <=> ?::vector)"
        val args = mutableListOf<Any>()
        if (vector != null) args.add(vector.joinToString(",", "[", "]"))
        args.add(student); args.add(before); args.addAll(ids)
        return jdbc.query("""
            SELECT d.attempt_id,d.theme_id,d.theme_week_start,tv.title,mv.question,
                coalesce(ans.plain_text,'') answer,d.embedding_model,$score score
            FROM memory_search_doc d JOIN attempt a ON a.id=d.attempt_id
            JOIN theme_frame f ON f.student_id=d.student_id AND f.theme_id=d.theme_id AND f.theme_week_start=d.theme_week_start
            JOIN weekly_theme_version tv ON tv.id=f.theme_version_id
            JOIN mission_version mv ON mv.id=a.mission_version_id
            JOIN LATERAL (SELECT plain_text FROM answer WHERE attempt_id=a.id ORDER BY version DESC LIMIT 1) ans ON true
            WHERE d.student_id=? AND a.student_id=d.student_id AND d.theme_week_start<? AND d.status='READY'
              AND a.context IN ('THEME_DAY','THEME_REVIEW') AND a.completed_at IS NOT NULL
              AND d.attempt_id IN (${ids.joinToString(",") { "?" }})
        """.trimIndent(), { rs, _ -> MemoryEvidenceRow(
            rs.getObject("attempt_id",UUID::class.java),rs.getObject("theme_id",UUID::class.java),
            rs.getObject("theme_week_start",LocalDate::class.java),rs.getString("title"),rs.getString("question"),
            rs.getString("answer"),rs.getString("embedding_model"),rs.getDouble("score")) }, *args.toTypedArray())
    }
}
