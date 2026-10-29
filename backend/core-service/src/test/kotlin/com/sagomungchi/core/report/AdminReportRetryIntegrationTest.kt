package com.sagomungchi.core.report

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.admin.account
import com.sagomungchi.core.admin.repository.OperationsRepository
import com.sagomungchi.core.admin.service.OperationRetryService
import com.sagomungchi.core.admin.service.OperationsService
import com.sagomungchi.core.notification.messaging.NotificationRedisPublisher
import com.sagomungchi.core.report.domain.*
import com.sagomungchi.core.report.service.ReportAdminRetryService
import com.sagomungchi.core.report.service.ReportLifecycleService
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Test
import org.mockito.ArgumentMatchers.*
import org.mockito.Mockito.doAnswer
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.dao.DataIntegrityViolationException
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.post
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import org.springframework.transaction.support.TransactionTemplate
import java.time.Instant
import java.time.OffsetDateTime
import java.time.Duration
import java.util.UUID
import java.util.concurrent.*
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.test.*

@AutoConfigureMockMvc
@TestPropertySource(properties=["app.payment.free-product-id=00000000-0000-4000-8000-000000004717"])
@Transactional(propagation=Propagation.NOT_SUPPORTED)
class AdminReportRetryIntegrationTest : PostgresRepositoryTest() {
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var retries: OperationRetryService
    @Autowired lateinit var reports: ReportAdminRetryService
    @Autowired lateinit var operations: OperationsService
    @Autowired lateinit var lifecycle: ReportLifecycleService
    @Autowired lateinit var tx: TransactionTemplate
    @MockitoSpyBean lateinit var audits: OperationsRepository
    @MockitoBean lateinit var notificationPublisher: NotificationRedisPublisher
    private val createdEvents=mutableListOf<UUID>()
    @AfterEach fun cleanupEventMarkers() {
        createdEvents.forEach { jdbc.update("DELETE FROM processed_event WHERE event_id=?",it) }
        createdEvents.clear()
    }
    private val free=UUID.fromString("00000000-0000-4000-8000-000000004717")
    private data class Fixture(val actor: AuthenticatedAccount,val token: String,val student: UUID,val original: UUID)
    @BeforeEach fun product() {
        jdbc.update("""INSERT INTO product(id,code,name,price,billing_cycle,child_limit,features,limits,active,created_at)
            VALUES(?,'admin-retry-test-free','Synthetic',0,'MONTHLY',1,'{}','{"dailyConversations":0,"reportNarrative":false}',true,CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET active=true,limits=EXCLUDED.limits""",free)
    }
    private fun fixture(status: String="FAILED",permission: String?="SERVICE_OPS"): Fixture {
        val admin=account(jdbc,permission=permission)
        val identity=actor(jdbc,admin,"ADMIN",permission?.let { setOf(it) } ?: emptySet())
        val owner=parent(jdbc);val student=child(jdbc,owner);val original=UUID.randomUUID()
        jdbc.update("""INSERT INTO report_job(id,student_id,period_from,period_to,trigger,status,failure_reason,retry_count,created_at,completed_at)
            VALUES(?,?,?,?,'SCHEDULE',?,'RENDER_FAILED',0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""",original,student,WEEK.from,WEEK.to,status)
        return Fixture(identity,tokens.access(identity.session),student,original)
    }
    private fun post(f: Fixture,key: UUID=UUID.randomUUID(),job: UUID=f.original)=mvc.post("/api/v1/admin/jobs/$job/retry") {
        header("Authorization","Bearer ${f.token}");header("Idempotency-Key",key)
    }
    private fun accepted(f: Fixture,key: UUID=UUID.randomUUID(),job: UUID=f.original): UUID {
        val result=post(f,key,job).andExpect { status { isAccepted() };jsonPath("$.status") { value("QUEUED") };jsonPath("$.originalJobId") { value(job.toString()) } }.andReturn().response
        val id=UUID.fromString(json.readTree(result.contentAsString).path("jobId").asText())
        assertEquals("/api/v1/admin/jobs/$id",result.getHeader("Location"));return id
    }
    private fun count(sql: String,vararg args: Any)=jdbc.queryForObject(sql,Int::class.java,*args)!!
    private fun status(job: UUID)=jdbc.queryForObject("SELECT status FROM report_job WHERE id=?",String::class.java,job)
    private fun event(job: UUID,student: UUID,report: UUID,status: ReportJobStatus)=ReportLifecycleEvent(UUID.randomUUID(),job,student,report,status,if(status==ReportJobStatus.FAILED) "RENDER_FAILED" else null).also { createdEvents+=it.eventId }
    private fun retryMatch()=any(ReportJobRetry::class.java) ?: ReportJobRetry(UUID(0,0),UUID(0,0),UUID(0,0),UUID(0,0),Instant.EPOCH)

    @Test fun `accept failed job without reportId and persist original relation outbox and actor audit atomically`() {
        val f=fixture();val id=accepted(f)
        assertNotEquals(f.original,id);assertEquals("FAILED",status(f.original));assertEquals("QUEUED",status(id))
        assertEquals("RENDER_FAILED",jdbc.queryForObject("SELECT failure_reason FROM report_job WHERE id=?",String::class.java,f.original))
        assertEquals("ADMIN_RETRY",jdbc.queryForObject("SELECT trigger FROM report_job WHERE id=?",String::class.java,id))
        assertEquals(f.actor.account.id,jdbc.queryForObject("SELECT requested_by FROM report_job WHERE id=?",UUID::class.java,id))
        assertEquals(id,reports.successor(f.original)!!.jobId);assertEquals(f.original,reports.origin(id)!!.originalJobId)
        assertEquals(0,count("SELECT count(*) FROM job_execution WHERE job_id=?",id))
        val envelope=json.readTree(jdbc.queryForObject("SELECT payload::text FROM outbox_event WHERE payload->'data'->>'jobId'=?",String::class.java,id.toString()))
        assertEquals("report.generate",envelope.path("type").asText());assertEquals(id.toString(),envelope.path("data").path("jobId").asText())
        assertEquals("ADMIN_RETRY",envelope.path("data").path("trigger").asText());assertFalse(envelope.path("data").path("narrativeEnabled").asBoolean())
        assertEquals(1,count("SELECT count(*) FROM audit_log WHERE target_id=? AND action='JOB_RETRY_REQUESTED' AND actor_user_id=? AND result='SUCCESS'",f.original,f.actor.account.id))
        val original=operations.job(f.original);assertFalse(original.retryable);assertEquals("REPORT_ALREADY_RETRIED",original.retryUnavailableReason);assertEquals(id,original.retryJobId)
        assertEquals(f.original,operations.job(id).retryOfJobId)
        val dir=java.nio.file.Path.of("build/admin-retry-contracts");java.nio.file.Files.createDirectories(dir)
        java.nio.file.Files.writeString(dir.resolve("report-retry-accepted.json"),json.writeValueAsString(ReportRetryAccepted(f.original,id,acceptedAt=reports.origin(id)!!.acceptedAt)))
        java.nio.file.Files.writeString(dir.resolve("report-retry-job.json"),json.writeValueAsString(operations.job(id)))
        java.nio.file.Files.writeString(dir.resolve("report-retry-generate.json"),envelope.toString())
    }
    @Test fun `same key restores identical acceptance after cache loss and actual job completion`() {
        val f=fixture();val key=UUID.randomUUID()
        val first=post(f,key).andExpect { status { isAccepted() } }.andReturn().response
        val id=UUID.fromString(json.readTree(first.contentAsString).path("jobId").asText())
        val done=event(id,f.student,UUID.randomUUID(),ReportJobStatus.COMPLETED);lifecycle.apply(done)
        jdbc.update("DELETE FROM idempotency_record WHERE user_id=? AND idempotency_key=?",f.actor.account.id,key)
        val again=post(f,key).andExpect { status { isAccepted() } }.andReturn().response
        assertEquals(first.contentAsString,again.contentAsString);assertEquals(first.getHeader("Location"),again.getHeader("Location"))
        assertEquals("COMPLETED",status(id));assertEquals(1,count("SELECT count(*) FROM report_job_retry WHERE original_job_id=?",f.original))
        assertEquals(1,count("SELECT count(*) FROM audit_log WHERE target_id=? AND action='JOB_RETRY_REQUESTED'",f.original))
        assertEquals(1,count("SELECT count(*) FROM outbox_event WHERE payload->'data'->>'jobId'=?",id.toString()))
    }
    @Test fun `different keys racing for the same original create only one child and command`() {
        val f=fixture();val pool=Executors.newFixedThreadPool(2);val gate=CountDownLatch(1)
        try {
            val results=List(2) { pool.submit<Int> { gate.await();retries.retry(f.original,UUID.randomUUID(),f.actor).status } }
            gate.countDown();assertEquals(listOf(202,409),results.map { it.get(20,TimeUnit.SECONDS) }.sorted())
        } finally { pool.shutdownNow() }
        val id=reports.successor(f.original)!!.jobId
        assertEquals(1,count("SELECT count(*) FROM report_job_retry WHERE original_job_id=?",f.original))
        assertEquals(1,count("SELECT count(*) FROM outbox_event WHERE payload->'data'->>'jobId'=?",id.toString()))
        assertEquals("FAILED",status(f.original))
    }
    @Test fun `in flight same key is rejected then replays its first acceptance`() {
        val f=fixture();val key=UUID.randomUUID();val locked=CountDownLatch(1);val release=CountDownLatch(1);val pool=Executors.newFixedThreadPool(3)
        try {
            val holder=pool.submit { tx.executeWithoutResult {
                jdbc.queryForObject("SELECT id FROM student WHERE id=? FOR UPDATE",UUID::class.java,f.student)
                locked.countDown();assertTrue(release.await(15,TimeUnit.SECONDS))
            } }
            assertTrue(locked.await(10,TimeUnit.SECONDS))
            val first=pool.submit<com.sagomungchi.core._common.web.HttpExchangeResult> { retries.retry(f.original,key,f.actor) }
            await { count("SELECT count(*) FROM idempotency_record WHERE user_id=? AND idempotency_key=?",f.actor.account.id,key)==1 }
            val duplicate=pool.submit<Throwable?> { runCatching { retries.retry(f.original,key,f.actor) }.exceptionOrNull() }.get(10,TimeUnit.SECONDS)
            val busy=assertIs<BusinessException>(duplicate);assertEquals("IDEMPOTENCY_IN_PROGRESS",busy.code)
            release.countDown();holder.get(10,TimeUnit.SECONDS)
            val response=first.get(15,TimeUnit.SECONDS);assertEquals(202,response.status)
            assertContentEquals(response.body,retries.retry(f.original,key,f.actor).body)
        } finally { release.countDown();pool.shutdownNow() }
    }
    @Test fun `new job lifecycle owns execution and terminal audit while delayed old events stay isolated`() {
        val f=fixture();val id=accepted(f);val report=UUID.randomUUID()
        lifecycle.apply(event(id,f.student,report,ReportJobStatus.RUNNING))
        lifecycle.apply(event(f.original,f.student,UUID.randomUUID(),ReportJobStatus.COMPLETED))
        assertEquals("FAILED",status(f.original));assertEquals("RUNNING",status(id))
        val complete=event(id,f.student,report,ReportJobStatus.COMPLETED)
        lifecycle.apply(complete);lifecycle.apply(complete);lifecycle.apply(event(id,f.student,report,ReportJobStatus.FAILED))
        assertEquals("COMPLETED",status(id));assertEquals(1,count("SELECT count(*) FROM job_execution WHERE job_id=? AND status='COMPLETED' AND triggered_by=?",id,f.actor.account.id))
        assertEquals(1,count("SELECT count(*) FROM audit_log WHERE target_id=? AND action='JOB_RETRY_COMPLETED'",f.original))
        assertEquals(0,count("SELECT count(*) FROM audit_log WHERE target_id=? AND action='JOB_RETRY_FAILED'",f.original))
    }
    @Test fun `failed child keeps its execution and can be retried as a new link`() {
        val f=fixture();val child=accepted(f);lifecycle.apply(event(child,f.student,UUID.randomUUID(),ReportJobStatus.FAILED))
        assertEquals("FAILED",status(child));assertTrue(operations.job(child).retryable)
        assertEquals(1,count("SELECT count(*) FROM audit_log WHERE target_id=? AND action='JOB_RETRY_FAILED' AND result='FAILURE'",f.original))
        val next=accepted(f,job=child);assertNotEquals(child,next);assertEquals(child,operations.job(next).retryOfJobId)
        post(f).andExpect { status { isConflict() };jsonPath("$.code") { value("REPORT_ALREADY_RETRIED") } }
        assertEquals("FAILED",status(f.original));assertEquals("FAILED",status(child))
    }
    @Test fun `request audit failure rolls back new job relation and outbox and permits same key recovery`() {
        val f=fixture();val key=UUID.randomUUID();val fail=AtomicBoolean(true)
        doAnswer { invocation ->
            val retry=invocation.getArgument<ReportJobRetry>(0)
            if(retry.originalJobId==f.original && fail.compareAndSet(true,false)) throw IllegalStateException("synthetic audit failure")
            invocation.callRealMethod()
        }.`when`(audits).reportRetryAudit(retryMatch(),eq("JOB_RETRY_REQUESTED") ?: "",anyString(),nullable(UUID::class.java))
        assertFailsWith<IllegalStateException> { retries.retry(f.original,key,f.actor) }
        assertEquals(0,count("SELECT count(*) FROM report_job_retry WHERE original_job_id=?",f.original))
        assertEquals(1,count("SELECT count(*) FROM report_job WHERE student_id=?",f.student))
        assertEquals(0,count("SELECT count(*) FROM outbox_event WHERE subject=?",f.student.toString()))
        assertEquals(202,retries.retry(f.original,key,f.actor).status)
    }
    @Test fun `terminal audit failure rolls back status processed marker and execution for valid event redelivery`() {
        val f=fixture();val id=accepted(f);val done=event(id,f.student,UUID.randomUUID(),ReportJobStatus.COMPLETED);val fail=AtomicBoolean(true)
        doAnswer { invocation ->
            val retry=invocation.getArgument<ReportJobRetry>(0)
            if(retry.originalJobId==f.original && fail.compareAndSet(true,false)) throw IllegalStateException("synthetic audit failure")
            invocation.callRealMethod()
        }.`when`(audits).reportRetryAudit(retryMatch(),eq("JOB_RETRY_COMPLETED") ?: "",anyString(),nullable(UUID::class.java))
        assertFailsWith<IllegalStateException> { lifecycle.apply(done) }
        assertEquals("QUEUED",status(id));assertEquals(0,count("SELECT count(*) FROM processed_event WHERE event_id=?",done.eventId))
        assertEquals(0,count("SELECT count(*) FROM job_execution WHERE job_id=?",id))
        lifecycle.apply(done);assertEquals("COMPLETED",status(id))
        assertEquals(1,count("SELECT count(*) FROM audit_log WHERE target_id=? AND action='JOB_RETRY_COMPLETED'",f.original))
    }
    @Test fun `non failed or competing weekly work never creates an admin retry`() {
        for(state in listOf("QUEUED","RUNNING","COMPLETED")) {
            val f=fixture(state);post(f).andExpect { status { isConflict() };jsonPath("$.code") { value("JOB_NOT_FAILED") } }
            assertNull(reports.successor(f.original))
        }
        val f=fixture();val other=UUID.randomUUID()
        jdbc.update("INSERT INTO report_job(id,student_id,period_from,period_to,trigger,status,retry_count,created_at) VALUES(?,?,?,?,'ADMIN_RETRY','QUEUED',0,CURRENT_TIMESTAMP)",other,f.student,WEEK.from,WEEK.to)
        post(f).andExpect { status { isConflict() };jsonPath("$.code") { value("REPORT_GENERATION_IN_PROGRESS") } }
        assertNull(reports.successor(f.original))
    }
    @Test fun `permissions are checked before initial request and cached response`() {
        for(permission in listOf(null,"CONTENT","PAYMENT_VIEW","PAYMENT_REFUND")) {
            val f=fixture(permission=permission);post(f).andExpect { status { isForbidden() } };assertNull(reports.successor(f.original))
        }
        val f=fixture();val key=UUID.randomUUID();accepted(f,key)
        jdbc.update("DELETE FROM admin_permission WHERE user_id=? AND permission='SERVICE_OPS'",f.actor.account.id)
        post(f,key).andExpect { status { isForbidden() } }
    }
    @Test fun `deleted student and deletion history block new requests without touching original failure`() {
        for(state in listOf("DELETION_REQUESTED","DELETED")) {
            val f=fixture()
            if(state=="DELETED") jdbc.update("UPDATE student SET status='DELETED',nickname=NULL,grade=NULL,birth_year=NULL WHERE id=?",f.student)
            else jdbc.update("UPDATE student SET status=? WHERE id=?",state,f.student)
            post(f).andExpect { status { isConflict() };jsonPath("$.code") { value("REPORT_RETRY_STUDENT_UNAVAILABLE") } }
            assertNull(reports.successor(f.original));assertEquals("FAILED",status(f.original))
        }
        val f=fixture()
        jdbc.update("INSERT INTO deletion_request(id,requested_by,student_id,scope,status,requested_at,confirmed_at,completed_at) VALUES(?,?,?,'RECORDS','COMPLETED',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",UUID.randomUUID(),f.actor.account.id,f.student)
        post(f).andExpect { status { isConflict() };jsonPath("$.code") { value("REPORT_RETRY_STUDENT_UNAVAILABLE") } }
        assertNull(reports.successor(f.original))
    }

    @Test fun `deletion winning the student lock prevents acceptance after its commit`() {
        val f=fixture();val key=UUID.randomUUID();val locked=CountDownLatch(1);val release=CountDownLatch(1);val pool=Executors.newFixedThreadPool(2)
        try {
            val deletion=pool.submit { tx.executeWithoutResult {
                jdbc.queryForObject("SELECT id FROM student WHERE id=? FOR UPDATE",UUID::class.java,f.student)
                locked.countDown();assertTrue(release.await(15,TimeUnit.SECONDS))
                jdbc.update("UPDATE student SET status='DELETION_REQUESTED' WHERE id=?",f.student)
            } }
            assertTrue(locked.await(10,TimeUnit.SECONDS))
            val acceptance=pool.submit<com.sagomungchi.core._common.web.HttpExchangeResult> { retries.retry(f.original,key,f.actor) }
            await { count("SELECT count(*) FROM idempotency_record WHERE user_id=? AND idempotency_key=?",f.actor.account.id,key)==1 }
            release.countDown();deletion.get(10,TimeUnit.SECONDS)
            val response=acceptance.get(15,TimeUnit.SECONDS);assertEquals(409,response.status)
            assertEquals("REPORT_RETRY_STUDENT_UNAVAILABLE",json.readTree(response.body).path("code").asText())
            assertNull(reports.successor(f.original));assertEquals("FAILED",status(f.original))
        } finally { release.countDown();pool.shutdownNow() }
    }

    @Test fun `current product snapshot is used and unavailable product stays an explicit error`() {
        val f=fixture();val key=UUID.randomUUID();jdbc.update("UPDATE product SET active=false WHERE id=?",free)
        post(f,key).andExpect { status { isServiceUnavailable() };jsonPath("$.code") { value("PAYMENT_FREE_PRODUCT_UNAVAILABLE") } }
        assertNull(reports.successor(f.original))
        jdbc.update("UPDATE product SET active=true,limits=jsonb_set(limits,'{reportNarrative}','true') WHERE id=?",free)
        val id=accepted(f,key)
        assertEquals("true",jdbc.queryForObject("SELECT payload->'data'->>'narrativeEnabled' FROM outbox_event WHERE payload->'data'->>'jobId'=?",String::class.java,id.toString()))
    }
    @Test fun `same durable key cannot be repurposed after the common response cache is gone`() {
        val f=fixture();val key=UUID.randomUUID();accepted(f,key)
        jdbc.update("DELETE FROM idempotency_record WHERE user_id=? AND idempotency_key=?",f.actor.account.id,key)
        val other=fixture();val request=other.copy(actor=f.actor,token=f.token)
        post(request,key).andExpect { status { isUnprocessableEntity() };jsonPath("$.code") { value("IDEMPOTENCY_KEY_REUSED") } }
        assertNull(reports.successor(other.original))
    }
    @Test fun `relation constraints reject self links missing jobs and duplicate children or request keys`() {
        val f=fixture();val child=accepted(f);val other=fixture()
        fun rejected(original: UUID,retry: UUID,actor: UUID,key: UUID,code: String) {
            val error=assertFailsWith<DataIntegrityViolationException> { tx.executeWithoutResult {
                jdbc.update("INSERT INTO report_job_retry(original_job_id,retry_job_id,requested_by,idempotency_key,accepted_at) VALUES(?,?,?,?,CURRENT_TIMESTAMP)",original,retry,actor,key)
            } }
            val cause=generateSequence<Throwable>(error) { it.cause }.filterIsInstance<java.sql.SQLException>().first()
            assertEquals(code,cause.sqlState)
        }
        rejected(other.original,other.original,f.actor.account.id,UUID.randomUUID(),"23514")
        rejected(UUID.randomUUID(),other.original,f.actor.account.id,UUID.randomUUID(),"23503")
        rejected(other.original,child,f.actor.account.id,UUID.randomUUID(),"23505")
        val saved=reports.successor(f.original)!!
        rejected(other.original,f.original,saved.requestedBy,saved.idempotencyKey,"23505")
    }
    private fun await(condition: () -> Boolean) {
        val end=System.nanoTime()+Duration.ofSeconds(10).toNanos()
        while(System.nanoTime()<end) { if(condition()) return;Thread.sleep(20) }
        fail("Condition not reached")
    }
}
