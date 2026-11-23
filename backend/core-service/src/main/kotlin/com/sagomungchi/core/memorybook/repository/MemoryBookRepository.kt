package com.sagomungchi.core.memorybook.repository

import com.sagomungchi.core.memorybook.domain.MemoryBookJob
import com.sagomungchi.core.memorybook.domain.MemoryBookStatus
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.jdbc.core.RowMapper
import org.springframework.stereotype.Repository
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID

/** 추억 그림책 작업·내려받기 기록 (V57, docs/proposals/memory-book.md 8.1, 미도입 시험 구현) */
@Repository
class MemoryBookRepository(private val jdbc: JdbcTemplate) {
    private val row = RowMapper { r, _ ->
        MemoryBookJob(
            r.getObject("id", UUID::class.java), r.getObject("student_id", UUID::class.java), r.getObject("requested_by", UUID::class.java),
            r.getObject("theme_id", UUID::class.java), r.getObject("week_start", LocalDate::class.java),
            MemoryBookStatus.valueOf(r.getString("status")), r.getString("failure_code"), r.getObject("size_bytes") as Long?,
            r.getObject("theme_version_id", UUID::class.java), r.getObject("usage_reservation_id", UUID::class.java),
            r.getObject("created_at", OffsetDateTime::class.java), r.getObject("completed_at", OffsetDateTime::class.java),
            r.getObject("expires_at", OffsetDateTime::class.java),
        )
    }

    fun insert(job: MemoryBookJob): Int = jdbc.update(
        """INSERT INTO memory_book_job(id,student_id,requested_by,theme_id,week_start,status,usage_reservation_id,created_at,expires_at)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        job.id, job.studentId, job.requestedBy, job.themeId, job.weekStart, job.status.name, job.usageReservationId, job.createdAt, job.expiresAt,
    )

    fun find(id: UUID): MemoryBookJob? = jdbc.query("SELECT * FROM memory_book_job WHERE id=?", row, id).singleOrNull()

    fun lock(id: UUID): MemoryBookJob? = jdbc.query("SELECT * FROM memory_book_job WHERE id=? FOR UPDATE", row, id).singleOrNull()

    /** 같은 회차의 만드는 중(QUEUED) 또는 아직 만료되지 않은 완성(READY) 작업. 최근 것 1개 */
    fun reusable(student: UUID, themeId: UUID, weekStart: LocalDate, now: OffsetDateTime): MemoryBookJob? = jdbc.query(
        """SELECT * FROM memory_book_job WHERE student_id=? AND theme_id=? AND week_start=?
           AND (status='QUEUED' OR (status='READY' AND expires_at>?)) ORDER BY created_at DESC LIMIT 1""",
        row, student, themeId, weekStart, now,
    ).singleOrNull()

    /** 회차별 가장 최근 작업(학부모 발급 화면의 회차 목록에 붙임) */
    fun latestByStudent(student: UUID): List<MemoryBookJob> = jdbc.query(
        """SELECT DISTINCT ON (theme_id, week_start) * FROM memory_book_job WHERE student_id=?
           ORDER BY theme_id, week_start, created_at DESC""",
        row, student,
    )

    fun createdSince(student: UUID, since: OffsetDateTime): Int =
        jdbc.queryForObject("SELECT count(*) FROM memory_book_job WHERE student_id=? AND created_at>=?", Int::class.java, student, since)!!

    fun page(student: UUID, page: Int, size: Int): List<MemoryBookJob> = jdbc.query(
        "SELECT * FROM memory_book_job WHERE student_id=? ORDER BY created_at DESC, id LIMIT ? OFFSET ?",
        row, student, size, page.toLong() * size,
    )

    fun count(student: UUID): Long = jdbc.queryForObject("SELECT count(*) FROM memory_book_job WHERE student_id=?", Long::class.java, student)!!

    /** QUEUED에서만 바꾼다. 바꿨으면 true */
    fun complete(id: UUID, status: MemoryBookStatus, failureCode: String?, sizeBytes: Long?, themeVersionId: UUID?, at: OffsetDateTime): Boolean =
        jdbc.update(
            """UPDATE memory_book_job SET status=?,failure_code=?,size_bytes=?,theme_version_id=?,completed_at=?
               WHERE id=? AND status='QUEUED'""",
            status.name, failureCode, sizeBytes, themeVersionId, at, id,
        ) == 1

    fun download(book: UUID, student: UUID, user: UUID, role: String, at: OffsetDateTime) {
        check(jdbc.update("INSERT INTO memory_book_download(id,book_id,student_id,user_id,role,created_at) VALUES(?,?,?,?,?,?)",
            UUID.randomUUID(), book, student, user, role, at) == 1)
    }

    /** 학생 삭제(P09): 내려받기 기록은 FK CASCADE로 함께 */
    fun deleteByStudent(student: UUID): Int = jdbc.update("DELETE FROM memory_book_job WHERE student_id=?", student)
}
