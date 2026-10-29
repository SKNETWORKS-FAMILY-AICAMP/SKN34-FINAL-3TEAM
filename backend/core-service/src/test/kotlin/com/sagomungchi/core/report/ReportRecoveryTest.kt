package com.sagomungchi.core.report

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core.guardianship.service.ChildManagementService
import com.sagomungchi.core.guardianship.service.StudentAccessService
import com.sagomungchi.core.report.domain.*
import com.sagomungchi.core.report.repository.ReportJobRepository
import com.sagomungchi.core.report.service.*
import com.sun.net.httpserver.HttpServer
import org.junit.jupiter.api.AfterAll
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.TestConfiguration
import org.springframework.boot.web.client.RestClientCustomizer
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Import
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.transaction.PlatformTransactionManager
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import org.springframework.transaction.support.TransactionSynchronizationManager
import org.springframework.transaction.support.TransactionTemplate
import java.net.InetSocketAddress
import java.time.OffsetDateTime
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlin.test.*

@Transactional(propagation = Propagation.NOT_SUPPORTED)
@Import(ReportRecoveryTest.Probe::class)
class ReportRecoveryTest : PostgresRepositoryTest() {
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var jobs: ReportJobService
    @Autowired lateinit var lifecycle: ReportLifecycleService
    @Autowired lateinit var recovery: ReportRecoveryService
    @Autowired lateinit var repository: ReportJobRepository
    @Autowired lateinit var students: StudentAccessService
    @Autowired lateinit var children: ChildManagementService
    @Autowired lateinit var manager: PlatformTransactionManager
    @Autowired lateinit var json: ObjectMapper
    @MockitoBean lateinit var entitlement: ReportEntitlementService

    @TestConfiguration class Probe {
        @Bean fun recoveryProbe() = RestClientCustomizer { builder -> builder.requestInterceptor { request, body, execution ->
            check(!TransactionSynchronizationManager.isActualTransactionActive())
            execution.execute(request, body)
        } }
    }
    companion object {
        @Volatile private var respond: (String) -> Pair<Int, String> = { 503 to "{}" }
        private val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0).apply {
            createContext("/internal/report-jobs") { exchange ->
                check(exchange.requestMethod == "POST")
                check(exchange.requestHeaders.getFirst("Upgrade") == null)
                check(exchange.requestHeaders.getFirst("X-User-Role") == "SYSTEM")
                check(exchange.requestHeaders.getFirst("X-Internal-Token") == "repository-test-token")
                val body = exchange.requestBody.bufferedReader().readText()
                check(body.contains(exchange.requestHeaders.getFirst("X-Student-Scope")))
                val (code, response) = respond(body)
                val bytes = response.toByteArray()
                exchange.responseHeaders.set("Content-Type", "application/json")
                exchange.sendResponseHeaders(code, bytes.size.toLong())
                exchange.responseBody.use { it.write(bytes) }
            }
            start()
        }
        @JvmStatic @DynamicPropertySource fun properties(registry: DynamicPropertyRegistry) {
            registry.add("app.services.report") { "http://127.0.0.1:${server.address.port}" }
            registry.add("app.report.recovery.interval") { "PT24H" }
        }
        @JvmStatic @AfterAll fun stop() { server.stop(0) }
    }

    private val eventIds = mutableListOf<UUID>()
    private fun apply(event: ReportLifecycleEvent) {
        eventIds.add(event.eventId)
        lifecycle.apply(event)
    }
    @AfterEach fun cleanupEvents() {
        eventIds.forEach { jdbc.update("DELETE FROM processed_event WHERE event_id=?", it) }
    }

    private fun newJob(): Pair<UUID, ReportJob> {
        val parent = parent(jdbc); val child = child(jdbc, parent)
        val id = jobs.scheduled(parent, child, WEEK)!!.jobId
        return parent to repository.find(id)!!
    }
    private fun result(job: ReportJob, status: String, reportId: UUID? = null, reason: String? = null) =
        ReportReconciliation(job.id, job.studentId, ReportPeriod(job.periodFrom, job.periodTo), status, reportId, reason)
    private fun executionCount(job: ReportJob) = jdbc.queryForObject("SELECT count(*) FROM job_execution WHERE job_id=?", Int::class.java, job.id)
    private fun notificationCount(job: ReportJob) = jdbc.queryForObject("SELECT count(*) FROM notification WHERE child_id=?", Int::class.java, job.studentId)
    private fun delete(parent: UUID) {
        TransactionTemplate(manager).executeWithoutResult {
            jdbc.queryForObject("SELECT id FROM user_account WHERE id=? FOR UPDATE", UUID::class.java, parent)
            children.deleteForWithdrawal(parent)
        }
    }

    @Test fun `no report failure records history once without fake notifications and late events cannot revive`() {
        val (_, job) = newJob()
        val response = result(job, "FAILED", reason="REPORT_NOT_CREATED")
        lifecycle.reconcile(job, response); lifecycle.reconcile(job, response)
        val report = UUID.randomUUID()
        listOf(ReportJobStatus.RUNNING, ReportJobStatus.COMPLETED, ReportJobStatus.FAILED).forEach {
            apply(ReportLifecycleEvent(UUID.randomUUID(),job.id,job.studentId,report,it,if(it==ReportJobStatus.FAILED) "GENERATION_FAILED" else null))
        }
        assertEquals("REPORT_NOT_CREATED", repository.find(job.id)!!.failureReason)
        assertNull(repository.find(job.id)!!.reportId)
        assertEquals(1, executionCount(job)); assertEquals(0, notificationCount(job))
        assertFalse(repository.inProgress(job.studentId, job.periodFrom))
    }

    @Test fun `lost completion and failed result each record once and reject identity mismatch`() {
        for (status in listOf("COMPLETED", "FAILED")) {
            val (_, job) = newJob(); val report = UUID.randomUUID()
            val response = result(job,status,report,if(status=="FAILED") "GENERATION_FAILED" else null)
            assertFailsWith<IllegalArgumentException> { lifecycle.reconcile(job,response.copy(studentId=UUID.randomUUID())) }
            assertEquals(ReportJobStatus.QUEUED,repository.find(job.id)!!.status)
            lifecycle.reconcile(job,response); lifecycle.reconcile(job,response)
            apply(ReportLifecycleEvent(UUID.randomUUID(),job.id,job.studentId,report,ReportJobStatus.COMPLETED))
            assertEquals(ReportJobStatus.valueOf(status),repository.find(job.id)!!.status)
            assertEquals(1,executionCount(job)); assertEquals(1,notificationCount(job))
        }
        val (_, job) = newJob(); val report = UUID.randomUUID()
        apply(ReportLifecycleEvent(UUID.randomUUID(),job.id,job.studentId,report,ReportJobStatus.RUNNING))
        assertFailsWith<IllegalArgumentException> { lifecycle.reconcile(job,result(job,"COMPLETED",UUID.randomUUID())) }
        assertEquals(ReportJobStatus.RUNNING,repository.find(job.id)!!.status)
        lifecycle.reconcile(job,result(job,"FAILED",report,"REPORT_EXECUTION_ABANDONED"))
    }

    @Test fun `deletion atomically closes queued running jobs and admin cannot regenerate deleted student`() {
        val (parent, job) = newJob()
        val original = completedJob(jdbc,job.studentId,ReportPeriod(WEEK.from.minusWeeks(1),WEEK.to.minusWeeks(1)))
        val other = jobs.regenerate(original.second,actor(jdbc,parent))
        apply(ReportLifecycleEvent(UUID.randomUUID(),other.jobId,job.studentId,UUID.randomUUID(),ReportJobStatus.RUNNING))
        delete(parent)
        for (id in listOf(job.id,other.jobId)) {
            assertEquals("STUDENT_DELETED",repository.find(id)!!.failureReason)
            assertEquals(ReportJobStatus.FAILED,repository.find(id)!!.status)
        }
        assertEquals(0,notificationCount(job))
        assertEquals(2,jdbc.queryForObject("SELECT count(*) FROM job_execution WHERE job_id IN (?,?) AND error_code='STUDENT_DELETED'",Int::class.java,job.id,other.jobId))
        lifecycle.reconcile(job,result(job,"COMPLETED",UUID.randomUUID()))
        assertEquals("STUDENT_DELETED",repository.find(job.id)!!.failureReason)
        val admin = com.sagomungchi.core.admin.account(jdbc,"ADMIN",null)
        assertEquals("STUDENT_DELETED",assertFailsWith<BusinessException> {
            jobs.regenerate(original.second,actor(jdbc,admin,"ADMIN",setOf("SERVICE_OPS")))
        }.code)
        assertFailsWith<BusinessException> { jobs.scheduled(parent,job.studentId,ReportPeriod(WEEK.from.plusWeeks(1),WEEK.to.plusWeeks(1))) }
    }

    @Test fun `student lock serializes generation with deletion`() {
        val (parent, job) = newJob()
        val locked=CountDownLatch(1);val release=CountDownLatch(1)
        val pool=Executors.newFixedThreadPool(2)
        try {
            val deleting=pool.submit { TransactionTemplate(manager).executeWithoutResult {
                students.lockStatus(job.studentId);locked.countDown();check(release.await(10,TimeUnit.SECONDS))
                children.deleteForWithdrawal(parent)
            } }
            assertTrue(locked.await(10,TimeUnit.SECONDS))
            val generating=pool.submit<Any> { try {
                jobs.scheduled(parent,job.studentId,ReportPeriod(WEEK.from.plusWeeks(1),WEEK.to.plusWeeks(1)))!!
            } catch(ex: BusinessException) { ex.code } }
            release.countDown();deleting.get(10,TimeUnit.SECONDS)
            assertEquals("STUDENT_DELETED",generating.get(10,TimeUnit.SECONDS))
            assertEquals(0,jdbc.queryForObject("SELECT count(*) FROM report_job WHERE student_id=? AND status IN ('QUEUED','RUNNING')",Int::class.java,job.studentId))
        } finally {release.countDown();pool.shutdownNow()}
    }

    @Test fun `recovery HTTP is outside transaction and deletion while awaiting response wins`() {
        val (parent, job) = newJob()
        jdbc.update("UPDATE report_job SET created_at=? WHERE id=?",OffsetDateTime.now().minusMinutes(61),job.id)
        respond = {
            delete(parent)
            200 to json.writeValueAsString(mapOf("jobId" to job.id,"studentId" to job.studentId,
                "periodFrom" to job.periodFrom,"periodTo" to job.periodTo,"status" to "COMPLETED",
                "reportId" to UUID.randomUUID(),"failureReason" to null))
        }
        recovery.recover()
        assertEquals("STUDENT_DELETED",repository.find(job.id)!!.failureReason)
        assertEquals(0,notificationCount(job))
    }

    @Test fun `candidate policy skips recent jobs busy and HTTP failure remain pending until next recovery`() {
        val (_, recent) = newJob();val (_, old) = newJob()
        jdbc.update("UPDATE report_job SET created_at=? WHERE id=?",OffsetDateTime.now().minusMinutes(61),old.id)
        fun response(status: String, reason: String? = null) = json.writeValueAsString(mapOf(
            "jobId" to old.id,"studentId" to old.studentId,"periodFrom" to old.periodFrom,"periodTo" to old.periodTo,
            "status" to status,"reportId" to null,"failureReason" to reason))
        respond = {503 to "{}"}
        assertFailsWith<IllegalStateException> {recovery.recover()}
        assertEquals(ReportJobStatus.QUEUED,repository.find(old.id)!!.status)
        respond = {200 to response("BUSY")};recovery.recover()
        assertEquals(ReportJobStatus.QUEUED,repository.find(old.id)!!.status)
        respond = {200 to response("FAILED","REPORT_NOT_CREATED")};recovery.recover();recovery.recover()
        assertEquals(ReportJobStatus.FAILED,repository.find(old.id)!!.status)
        assertEquals(ReportJobStatus.QUEUED,repository.find(recent.id)!!.status)
        assertEquals(1,executionCount(old))
    }
}
