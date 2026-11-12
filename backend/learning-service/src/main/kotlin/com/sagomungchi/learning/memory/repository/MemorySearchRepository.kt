package com.sagomungchi.learning.memory.repository

import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.stereotype.Repository
import java.time.Instant
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.util.UUID

data class MemoryLease(val id: UUID, val studentId: UUID, val text: String, val until: Instant)
data class MemoryHit(val themeId: UUID, val weekStart: LocalDate, val title: String, val imageUri: String?,
    val missionId: UUID, val missionTitle: String, val attemptId: UUID, val answerExcerpt: String, val score: Double)

/** 검색 문서 저장소. 원천 데이터 조회는 learning_db 안에서만 수행한다. */
@Repository
class MemorySearchRepository(private val jdbc: JdbcTemplate, private val mapper: MemoryVectorMapper) {
    fun register(attemptId: UUID? = null): Int = jdbc.update("""
        INSERT INTO memory_search_doc(id,attempt_id,student_id,theme_id,theme_week_start,content_text,status,retry_count,created_at)
        SELECT gen_random_uuid(),a.id,a.student_id,a.theme_id,a.theme_week_start,
            concat_ws(E'\n',tv.title,scene.text,mv.question,ans.plain_text),'PENDING',0,now()
        FROM attempt a JOIN mission_version mv ON mv.id=a.mission_version_id
        JOIN weekly_theme t ON t.id=a.theme_id
        JOIN weekly_theme_version tv ON tv.id=coalesce(t.published_version_id,t.current_version_id)
        LEFT JOIN LATERAL (SELECT string_agg(line->>'text', E'\n' ORDER BY ord) text
            FROM weekly_theme_day day CROSS JOIN LATERAL jsonb_array_elements(coalesce(day.dialogue,'[]'::jsonb)) WITH ORDINALITY AS lines(line,ord)
            WHERE day.theme_version_id=tv.id AND day.mission_id=a.mission_id) scene ON true
        JOIN LATERAL (SELECT plain_text FROM answer WHERE attempt_id=a.id ORDER BY version DESC LIMIT 1) ans ON true
        WHERE a.completed_at IS NOT NULL AND a.context IN ('THEME_DAY','THEME_REVIEW')
          AND (?::uuid IS NULL OR a.id=?::uuid)
        ON CONFLICT (attempt_id) DO NOTHING
    """.trimIndent(), attemptId, attemptId)

    fun recover(now: Instant, maxRetries: Int): Int = jdbc.update("""
        UPDATE memory_search_doc SET status=CASE WHEN retry_count >= ? THEN 'FAILED' ELSE 'PENDING' END,lease_until=NULL
        WHERE status='PROCESSING' AND lease_until <= ?
    """.trimIndent(), maxRetries, utc(now))

    fun claim(now: Instant, until: Instant, limit: Int, maxRetries: Int): List<MemoryLease> = jdbc.query("""
        WITH selected AS (
            SELECT id FROM memory_search_doc WHERE status IN ('PENDING','FAILED') AND retry_count < ?
            ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT ?
        ) UPDATE memory_search_doc d SET status='PROCESSING',retry_count=retry_count+1,lease_until=?
        FROM selected s WHERE d.id=s.id AND d.status IN ('PENDING','FAILED')
        RETURNING d.id,d.student_id,d.content_text,d.lease_until
    """.trimIndent(), { rs, _ -> MemoryLease(rs.getObject("id",UUID::class.java),rs.getObject("student_id",UUID::class.java),
        rs.getString("content_text"),rs.getObject("lease_until",OffsetDateTime::class.java).toInstant()) }, maxRetries,limit,utc(until))

    fun ready(lease: MemoryLease, vector: List<Double>, model: String, now: Instant): Int =
        mapper.ready(lease, vector.joinToString(",", "[", "]"), model, now)

    fun failed(lease: MemoryLease, maxRetries: Int): Int = jdbc.update("""
        UPDATE memory_search_doc SET status='FAILED',lease_until=NULL
        WHERE id=? AND status='PROCESSING' AND lease_until=?
    """.trimIndent(),lease.id,utc(lease.until))

    fun deleteByStudent(id: UUID): Int = jdbc.update("DELETE FROM memory_search_doc WHERE student_id=?",id)
    fun hasFrames(id: UUID, before: LocalDate): Boolean = jdbc.queryForObject(
        "SELECT EXISTS(SELECT 1 FROM theme_frame WHERE student_id=? AND theme_week_start<?)",Boolean::class.java,id,before)!!

    fun search(id: UUID, before: LocalDate, vector: List<Double>, model: String, minimum: Double): List<MemoryHit> =
        mapper.hits(id, before, vector.joinToString(",", "[", "]"), model, null, minimum)

    /** #568 비교용: 같은 접근 범위, 최종 답변에 대한 문자 검색. 외부 API로 노출하지 않음. */
    fun keyword(id: UUID, before: LocalDate, query: String): List<MemoryHit> =
        mapper.hits(id, before, null, null,
            "%" + query.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%", 0.0)

    private fun utc(value: Instant)=value.atOffset(ZoneOffset.UTC)
}

@Mapper
interface MemoryVectorMapper {
    fun ready(@Param("lease") lease: MemoryLease, @Param("vector") vector: String,
        @Param("model") model: String, @Param("now") now: Instant): Int
    fun hits(@Param("studentId") studentId: UUID, @Param("before") before: LocalDate,
        @Param("vector") vector: String?, @Param("model") model: String?,
        @Param("keyword") keyword: String?, @Param("minimum") minimum: Double): List<MemoryHit>
}
