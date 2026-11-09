package com.sagomungchi.core.guardianship

import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core.guardianship.domain.StudentGrade
import com.sagomungchi.core.guardianship.service.GradePromotionService
import com.sagomungchi.core.report.child
import com.sagomungchi.core.report.parent
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import java.time.Instant
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID
import kotlin.test.*

/** #432: 3월(KST) 자동 진급. 학년도마다 한 번, 중3(9)에서 멈추고 2월 이후 학년을 정한 학생·시연·차단 학생은 뺀다. */
class GradePromotionTest : PostgresRepositoryTest() {
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var service: GradePromotionService

    /** 2027-03-01 00:05 KST. */
    private val march = Instant.parse("2027-02-28T15:05:00Z")
    /** 학년도 2027의 기준(2월 1일 KST) 전. 테스트가 언제 돌아도 같은 결과가 되도록 등록 시각 대신 명시한다. */
    private val beforeCutoff = OffsetDateTime.parse("2026-09-01T00:00:00+09:00")

    private fun student(user: UUID, grade: Int, changedAt: OffsetDateTime? = beforeCutoff, demo: Boolean = false, status: String = "ACTIVE") =
        child(jdbc, user).also {
            jdbc.update("UPDATE student SET grade=?,grade_changed_at=?,is_demo=?,status=? WHERE id=?", grade, changedAt, demo, status, it)
        }
    private fun grade(id: UUID) = jdbc.queryForObject("SELECT grade FROM student WHERE id=?", Int::class.java, id)
    private fun titles(user: UUID) = jdbc.queryForList(
        "SELECT title FROM notification WHERE user_id=? AND type='GRADE_PROMOTED' AND link='/parent/settings' ORDER BY title",
        String::class.java, user)

    @Test fun `March promotes each eligible student once and stops at middle school third grade`() {
        val user = parent(jdbc)
        val third = student(user, 3); val sixth = student(user, 6); val eighth = student(user, 8); val ninth = student(user, 9)
        val demo = student(user, 3, demo = true)
        val blocked = student(user, 3, status = "DELETION_REQUESTED")
        // 2월에 학부모가 새 학년을 미리 넣은 학생은 이미 올라간 것으로 본다.
        val renewed = student(user, 4, OffsetDateTime.parse("2027-02-10T09:00:00+09:00"))
        val mine = setOf(third, sixth, eighth, ninth, demo, blocked, renewed)

        val promoted = service.promote(march).filter { it.studentId in mine }

        assertEquals(mapOf(third to 4, sixth to 7, eighth to 9), promoted.associate { it.studentId to it.toGrade })
        assertEquals(mapOf(third to 4, sixth to 7, eighth to 9, ninth to 9, demo to 3, blocked to 3, renewed to 4),
            mine.associateWith { grade(it) })
        assertEquals(listOf(3, 4), jdbc.queryForList(
            "SELECT unnest(ARRAY[from_grade,to_grade]) FROM student_grade_promotion WHERE student_id=? AND school_year=2027",
            Int::class.java, third))
        // 진급 시각이 새 학년 변경 시각이 되어 다음 학년도 기준(2028-02-01)보다 앞선다.
        assertEquals(march, jdbc.queryForObject("SELECT grade_changed_at FROM student WHERE id=?", OffsetDateTime::class.java, third)!!.toInstant())
        assertEquals(listOf("검증용의 학년이 중학교 1학년으로 올라갔어요. 다르면 정보 관리에서 고쳐 주세요.",
            "검증용의 학년이 중학교 3학년으로 올라갔어요. 다르면 정보 관리에서 고쳐 주세요.",
            "검증용의 학년이 초등 4학년으로 올라갔어요. 다르면 정보 관리에서 고쳐 주세요."), titles(user))

        // 학부모가 3월에 되돌려도, 같은 3월의 다음 실행(재시작·놓친 날 따라잡기)은 다시 올리지 않는다.
        jdbc.update("UPDATE student SET grade=3 WHERE id=?", third)
        assertTrue(service.promote(Instant.parse("2027-03-15T00:00:00Z")).none { it.studentId in mine })
        assertEquals(3, grade(third)); assertEquals(3, titles(user).size)
    }

    @Test fun `promotion runs only in March KST`() {
        val user = parent(jdbc); val id = student(user, 3)
        // 2027-02-28 23:59 KST와 2027-04-01 00:00 KST는 진급하지 않는다.
        listOf("2027-02-28T14:59:00Z", "2027-03-31T15:00:00Z").forEach {
            assertTrue(service.promote(Instant.parse(it)).none { p -> p.studentId == id })
        }
        assertEquals(3, grade(id))
        // 2027-03-31 23:59 KST는 아직 3월이라 따라잡는다.
        assertEquals(listOf(id), service.promote(Instant.parse("2027-03-31T14:59:00Z")).map { it.studentId }.filter { it == id })
    }

    @Test fun `parents who turned the notification off still see the new grade`() {
        val user = parent(jdbc); val id = student(user, 5)
        jdbc.update("INSERT INTO notification_setting(user_id,type,channel,enabled,updated_at) VALUES(?,'GRADE_PROMOTED','IN_APP',false,now())", user)
        service.promote(march)
        assertEquals(6, grade(id)); assertTrue(titles(user).isEmpty())
    }

    @Test fun `grade rules keep registration in the supported range and cap learning at sixth grade`() {
        assertEquals(listOf(3, 4, 5, 6, 6, 6, 6), (3..9).map(StudentGrade::learning))
        assertTrue(StudentGrade.registrable(6)); assertFalse(StudentGrade.registrable(7))
        assertTrue(StudentGrade.stored(9)); assertFalse(StudentGrade.stored(10)); assertFalse(StudentGrade.stored(2))
        assertEquals("중학교 2학년", StudentGrade.label(8)); assertEquals("초등 6학년", StudentGrade.label(6))
        assertNull(StudentGrade.promotionYear(LocalDate.parse("2027-02-28")))
        assertEquals(2027, StudentGrade.promotionYear(LocalDate.parse("2027-03-01")))
        assertEquals(Instant.parse("2027-01-31T15:00:00Z"), StudentGrade.promotionCutoff(2027).toInstant())
    }
}
