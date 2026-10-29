package com.sagomungchi.core.report

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.report.domain.*
import com.sagomungchi.core.report.repository.ReportJobRepository
import com.sagomungchi.core.report.service.*
import org.junit.jupiter.api.Test
import org.mockito.Mockito.`when`
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.context.event.RecordApplicationEvents
import org.springframework.test.context.event.ApplicationEvents
import java.time.OffsetDateTime
import java.util.UUID
import kotlin.test.*

@RecordApplicationEvents
class ReportRepositoryTest : PostgresRepositoryTest() {
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var jobs: ReportJobService
    @Autowired lateinit var lifecycle: ReportLifecycleService
    @Autowired lateinit var repository: ReportJobRepository
    @Autowired lateinit var schedule: ReportScheduleService
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var events: ApplicationEvents
    @MockitoBean lateinit var entitlement: ReportEntitlementService

    @Test fun `scheduled children with no learning records get one job and one outbox and preserve free premium flag`() {
        val user = parent(jdbc); val first = child(jdbc, user); val second = child(jdbc, user)
        `when`(entitlement.narrativeEnabled(first)).thenReturn(false)
        `when`(entitlement.narrativeEnabled(second)).thenReturn(true)
        listOf(first, second).forEach { id ->
            val accepted = jobs.scheduled(user, id, WEEK)!!
            assertEquals(ReportJobStatus.QUEUED, repository.find(accepted.jobId)!!.status)
            assertNull(jobs.scheduled(user, id, WEEK))
            val events = jdbc.queryForList("SELECT payload::text FROM outbox_event WHERE subject=? AND event_type='report.generate'", String::class.java, id.toString())
            assertEquals(1, events.size)
            val envelope = json.readTree(events.single())
            assertEquals(accepted.jobId.toString(), envelope["data"]["jobId"].asText())
            assertEquals("report.generate.v1", envelope["dataschema"].asText())
            assertEquals(id == second, envelope["data"]["narrativeEnabled"].asBoolean())
        }
    }

    @Test fun `schedule excludes withdrawn guardian and unlinked or inactive children`() {
        val user = parent(jdbc); val active = child(jdbc, user); val withdrawn = child(jdbc, user)
        val unlinked = child(jdbc, user); val inactive = child(jdbc, user)
        jdbc.update("UPDATE consent SET status='WITHDRAWN',withdrawn_at=? WHERE student_id=?", OffsetDateTime.now(), withdrawn)
        jdbc.update("UPDATE guardianship SET status='UNLINKED' WHERE student_id=?", unlinked)
        jdbc.update("UPDATE student SET status='DELETION_REQUESTED' WHERE id=?", inactive)
        `when`(entitlement.narrativeEnabled(active)).thenReturn(false)
        schedule.generate(java.time.Instant.parse("2026-10-25T22:00:00Z"))
        assertNotNull(repository.scheduled(active, WEEK.from))
        listOf(withdrawn, unlinked, inactive).forEach { assertNull(repository.scheduled(it, WEEK.from)) }
    }

    @Test fun `schedule keeps creating other children after one child fails and reports the failure after the run`() {
        val user = parent(jdbc); val failing = child(jdbc, user); val healthy = child(jdbc, user)
        `when`(entitlement.narrativeEnabled(failing)).thenThrow(BusinessException(org.springframework.http.HttpStatus.SERVICE_UNAVAILABLE,
            "REPORT_ENTITLEMENT_UNAVAILABLE", "상품 계약 미연결"))
        `when`(entitlement.narrativeEnabled(healthy)).thenReturn(false)
        assertFailsWith<IllegalStateException> { schedule.generate(java.time.Instant.parse("2026-10-25T22:00:00Z")) }
        assertNotNull(repository.scheduled(healthy, WEEK.from))
        assertNull(repository.scheduled(failing, WEEK.from))
    }

    @Test fun `parent regeneration preserves old report and limit applies through newly generated revision`() {
        val user = parent(jdbc); val student = child(jdbc, user); val original = completedJob(jdbc, student)
        `when`(entitlement.narrativeEnabled(student)).thenReturn(true)
        val accepted = jobs.regenerate(original.second, actor(jdbc, user))
        assertNotEquals(original.first, accepted.jobId)
        assertEquals(original.second, repository.find(original.first)!!.reportId)
        val newReport = UUID.randomUUID()
        lifecycle.apply(event(accepted.jobId, student, newReport, "completed"))
        assertNull(jdbc.queryForObject("SELECT triggered_by FROM job_execution WHERE job_id=?", UUID::class.java, accepted.jobId))
        assertEquals(ReportTrigger.REGENERATE, repository.find(accepted.jobId)!!.trigger)
        val error = assertFailsWith<BusinessException> { jobs.regenerate(newReport, actor(jdbc, user)) }
        assertEquals("REPORT_REGENERATION_LIMIT", error.code)
        assertEquals(2, jdbc.queryForObject("SELECT count(*) FROM report_job WHERE student_id=?", Int::class.java, student))
    }

    @Test fun `completed before started and different duplicate ids never reverse terminal state or duplicate execution`() {
        val user = parent(jdbc); val student = child(jdbc, user)
        `when`(entitlement.narrativeEnabled(student)).thenReturn(false)
        val job = jobs.scheduled(user, student, WEEK)!!; val report = UUID.randomUUID()
        val completed = event(job.jobId, student, report, "completed")
        lifecycle.apply(completed); lifecycle.apply(completed)
        lifecycle.apply(event(job.jobId, student, report, "started"))
        lifecycle.apply(event(job.jobId, student, report, "completed"))
        lifecycle.apply(event(job.jobId, student, report, "failed"))
        val saved = repository.find(job.jobId)!!
        assertEquals(ReportJobStatus.COMPLETED, saved.status); assertNull(saved.startedAt); assertNull(saved.failureReason)
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM job_execution WHERE job_id=? AND status='COMPLETED'", Int::class.java, job.jobId))
        assertEquals(4, jdbc.queryForObject("SELECT count(*) FROM processed_event WHERE event_id IN (SELECT event_id FROM processed_event) AND event_type LIKE 'report.%'", Int::class.java))
        assertEquals(1L, events.stream(ReportJobFinished::class.java).count())
    }

    @Test fun `started then failure records execution cause and completed cannot revive it`() {
        val user = parent(jdbc); val student = child(jdbc, user)
        val job = jobs.scheduled(user, student, WEEK)!!; val report = UUID.randomUUID()
        lifecycle.apply(event(job.jobId, student, report, "started"))
        assertEquals(ReportJobStatus.RUNNING, repository.find(job.jobId)!!.status)
        lifecycle.apply(event(job.jobId, student, report, "failed"))
        lifecycle.apply(event(job.jobId, student, report, "completed"))
        val saved = repository.find(job.jobId)!!
        assertEquals(ReportJobStatus.FAILED, saved.status); assertEquals("RENDER_FAILED", saved.failureReason)
        assertNotNull(saved.startedAt); assertNotNull(saved.completedAt)
        assertEquals("RENDER_FAILED", jdbc.queryForObject("SELECT error_code FROM job_execution WHERE job_id=?", String::class.java, job.jobId))
    }

    private fun event(job: UUID, student: UUID, report: UUID, state: String) = ReportLifecycleEvent(UUID.randomUUID(), job, student, report,
        when (state) { "started" -> ReportJobStatus.RUNNING; "completed" -> ReportJobStatus.COMPLETED; else -> ReportJobStatus.FAILED },
        if (state == "failed") "RENDER_FAILED" else null)
}
