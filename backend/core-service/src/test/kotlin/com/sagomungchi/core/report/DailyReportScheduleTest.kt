package com.sagomungchi.core.report

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core.report.domain.*
import com.sagomungchi.core.report.repository.ReportJobRepository
import com.sagomungchi.core.report.service.*
import org.junit.jupiter.api.Test
import org.mockito.Mockito.never
import org.mockito.Mockito.verify
import org.mockito.Mockito.`when`
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.dao.DataIntegrityViolationException
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.context.event.ApplicationEvents
import org.springframework.test.context.event.RecordApplicationEvents
import java.time.Instant
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID
import kotlin.test.*

/** P24 (#390): daily jobs share the weekly job/outbox/notification path, keyed by period type. */
@RecordApplicationEvents
class DailyReportScheduleTest : PostgresRepositoryTest() {
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var jobs: ReportJobService
    @Autowired lateinit var lifecycle: ReportLifecycleService
    @Autowired lateinit var repository: ReportJobRepository
    @Autowired lateinit var schedule: ReportScheduleService
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var events: ApplicationEvents
    @MockitoBean lateinit var entitlement: ReportEntitlementService

    /** Monday 2026-10-26 00:00 KST: the weekly job targets 10-19..10-25 and the daily job targets Sunday 10-25. */
    private val monday = Instant.parse("2026-10-25T15:00:00Z")
    private val sunday = ReportPeriod(LocalDate.parse("2026-10-25"), LocalDate.parse("2026-10-25"), ReportPeriodType.DAILY)
    /** The daily period whose period_from equals the weekly WEEK.from (Monday 10-19). */
    private val weekMonday = ReportPeriod(WEEK.from, WEEK.from, ReportPeriodType.DAILY)

    private fun generates(student: UUID) = jdbc.queryForList(
        "SELECT payload::text FROM outbox_event WHERE subject=? AND event_type='report.generate' ORDER BY created_at",
        String::class.java, student.toString()).map { json.readTree(it)["data"] }

    @Test fun `Monday runs daily and weekly for the same child and the daily command never consults the product`() {
        val user = parent(jdbc); val student = child(jdbc, user)
        `when`(entitlement.narrativeEnabled(student)).thenReturn(true)
        // Other test classes commit their own guardians to the shared DB, so count this child's jobs only.
        schedule.generate(monday, ReportPeriodType.WEEKLY); schedule.generate(monday, ReportPeriodType.DAILY)
        // A rerun after a lost lock or a restart creates nothing new.
        schedule.generate(monday, ReportPeriodType.DAILY); schedule.generate(monday, ReportPeriodType.WEEKLY)
        assertEquals(2, jdbc.queryForObject("SELECT count(*) FROM report_job WHERE student_id=?", Int::class.java, student))

        val daily = repository.scheduled(student, sunday)!!
        val weekly = repository.scheduled(student, WEEK)!!
        assertEquals(ReportPeriodType.DAILY, daily.periodType); assertEquals(ReportPeriodType.WEEKLY, weekly.periodType)
        assertEquals(sunday.from, daily.periodTo)

        val messages = generates(student).associateBy { it["jobId"].asText() }
        val dailyData = messages.getValue(daily.id.toString())
        assertEquals("DAILY", dailyData["periodType"].asText())
        assertEquals("2026-10-25", dailyData["periodFrom"].asText()); assertEquals("2026-10-25", dailyData["periodTo"].asText())
        assertFalse(dailyData["narrativeEnabled"].asBoolean())
        // Weekly keeps the pre-P24 wire format: absent periodType means WEEKLY.
        val weeklyData = messages.getValue(weekly.id.toString())
        assertFalse(weeklyData.has("periodType")); assertTrue(weeklyData["narrativeEnabled"].asBoolean())
        // Only the weekly job asked the product.
        verify(entitlement, org.mockito.Mockito.times(1)).narrativeEnabled(student)
    }

    @Test fun `daily schedule covers children without records and keeps going when the product is unavailable`() {
        val user = parent(jdbc); val first = child(jdbc, user); val second = child(jdbc, user)
        listOf(first, second).forEach { `when`(entitlement.narrativeEnabled(it)).thenThrow(
            BusinessException(org.springframework.http.HttpStatus.SERVICE_UNAVAILABLE, "PAYMENT_PRODUCT_UNAVAILABLE", "상품 확인 불가")) }
        // Sunday 2026-11-01 00:00 KST targets Saturday; weekends are ordinary target days.
        schedule.generate(Instant.parse("2026-10-31T15:00:00Z"), ReportPeriodType.DAILY)
        val saturday = ReportPeriod(LocalDate.parse("2026-10-31"), LocalDate.parse("2026-10-31"), ReportPeriodType.DAILY)
        listOf(first, second).forEach { assertEquals(ReportJobStatus.QUEUED, repository.scheduled(it, saturday)!!.status) }
        verify(entitlement, never()).narrativeEnabled(first)
    }

    @Test fun `regeneration limit and in-progress guard are per period type even when period_from is shared`() {
        val user = parent(jdbc); val student = child(jdbc, user)
        `when`(entitlement.narrativeEnabled(student)).thenReturn(false)
        val weekly = completedJob(jdbc, student, WEEK)
        val daily = completedJob(jdbc, student, weekMonday)
        val weeklyRetry = jobs.regenerate(weekly.second, actor(jdbc, user))
        // A queued weekly regeneration does not block the daily report of the same Monday.
        val dailyRetry = jobs.regenerate(daily.second, actor(jdbc, user))
        assertEquals(ReportPeriodType.WEEKLY, weeklyRetry.periodType)
        assertEquals(ReportPeriodType.DAILY, dailyRetry.periodType)
        assertEquals(weekMonday, repository.find(dailyRetry.jobId)!!.period)
        val newReport = UUID.randomUUID()
        lifecycle.apply(ReportLifecycleEvent(UUID.randomUUID(), dailyRetry.jobId, student, newReport, ReportJobStatus.COMPLETED))
        val error = assertFailsWith<BusinessException> { jobs.regenerate(newReport, actor(jdbc, user)) }
        assertEquals("REPORT_REGENERATION_LIMIT", error.code)
        assertTrue(repository.inProgress(student, WEEK)); assertFalse(repository.inProgress(student, weekMonday))
    }

    @Test fun `daily outcome publishes the daily period type and stores the daily notification type`() {
        val user = parent(jdbc); val student = child(jdbc, user)
        val accepted = jobs.scheduled(user, student, sunday)!!
        val report = UUID.randomUUID()
        lifecycle.apply(ReportLifecycleEvent(UUID.randomUUID(), accepted.jobId, student, report, ReportJobStatus.FAILED, "RENDER_FAILED"))
        assertEquals(ReportPeriodType.DAILY, events.stream(ReportJobFinished::class.java).toList().single().periodType)
        val stored = jdbc.queryForMap("SELECT type,title,link FROM notification WHERE user_id=?", user)
        assertEquals("DAILY_REPORT_FAILED", stored["type"]); assertEquals("일일 리포트 생성에 실패했습니다.", stored["title"])
        assertEquals("/parent/report?childId=$student", stored["link"])
    }

    @Test fun `daily opt-out is independent of the weekly setting`() {
        val user = parent(jdbc); val student = child(jdbc, user)
        `when`(entitlement.narrativeEnabled(student)).thenReturn(false)
        jdbc.update("INSERT INTO notification_setting(user_id,type,channel,enabled,updated_at) VALUES(?,'DAILY_REPORT_COMPLETED','IN_APP',false,?)",
            user, OffsetDateTime.now())
        val daily = jobs.scheduled(user, student, sunday)!!; val weekly = jobs.scheduled(user, student, WEEK)!!
        lifecycle.apply(ReportLifecycleEvent(UUID.randomUUID(), daily.jobId, student, UUID.randomUUID(), ReportJobStatus.COMPLETED))
        lifecycle.apply(ReportLifecycleEvent(UUID.randomUUID(), weekly.jobId, student, UUID.randomUUID(), ReportJobStatus.COMPLETED))
        assertEquals(listOf("REPORT_COMPLETED"), jdbc.queryForList("SELECT type FROM notification WHERE user_id=?", String::class.java, user))
    }

    @Test fun `database keeps a daily job to one day and one scheduled job per child, type and day`() {
        val user = parent(jdbc); val student = child(jdbc, user)
        fun insert(type: String, from: String, to: String) = jdbc.update("""INSERT INTO report_job(id,student_id,period_type,period_from,period_to,
            trigger,status,retry_count,created_at) VALUES(?,?,?,?::date,?::date,'SCHEDULE','QUEUED',0,?)""",
            UUID.randomUUID(), student, type, from, to, OffsetDateTime.now())
        insert("DAILY", "2026-10-19", "2026-10-19")
        insert("WEEKLY", "2026-10-19", "2026-10-25")
        assertFailsWith<DataIntegrityViolationException> { insert("DAILY", "2026-10-20", "2026-10-21") }
    }

    @Test fun `database rejects a duplicate scheduled daily job`() {
        val user = parent(jdbc); val student = child(jdbc, user)
        val accepted = jobs.scheduled(user, student, sunday)!!
        assertFailsWith<DataIntegrityViolationException> {
            jdbc.update("""INSERT INTO report_job(id,student_id,period_type,period_from,period_to,trigger,status,retry_count,created_at)
                SELECT ?,student_id,period_type,period_from,period_to,trigger,status,retry_count,created_at FROM report_job WHERE id=?""",
                UUID.randomUUID(), accepted.jobId)
        }
    }
}
