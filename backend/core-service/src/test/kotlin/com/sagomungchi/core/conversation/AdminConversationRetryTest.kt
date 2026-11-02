package com.sagomungchi.core.conversation

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core._common.messaging.OutboxRelay
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.admin.account
import com.sagomungchi.core.admin.repository.ConversationRetryAuditRepository
import com.sagomungchi.core.admin.service.OperationsService
import com.sagomungchi.core.conversation.domain.*
import com.sagomungchi.core.conversation.service.*
import com.sagomungchi.core.conversation.scheduler.ConversationRetryWorker
import com.sagomungchi.core.conversation.repository.ConversationRepository
import com.sagomungchi.core.conversation.repository.ConversationRetryRepository
import com.sagomungchi.core.report.parent
import com.sagomungchi.core.report.child
import com.sagomungchi.core.report.actor
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.AfterAll
import org.mockito.Mockito.*
import org.mockito.ArgumentMatchers.*
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.data.redis.core.StringRedisTemplate
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.post
import org.springframework.transaction.support.TransactionTemplate
import org.springframework.transaction.support.TransactionSynchronizationManager
import java.time.Instant
import java.util.UUID
import java.util.concurrent.*
import kotlin.test.*

@AutoConfigureMockMvc
@TestPropertySource(properties=["app.conversation.retry.enabled=false","spring.rabbitmq.listener.simple.auto-startup=false"])
class AdminConversationRetryTest : IntegrationTestSupport() {
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var conversations: ConversationService
    @Autowired lateinit var retries: ConversationAdminRetryService
    @Autowired lateinit var worker: ConversationRetryWorker
    @Autowired lateinit var messages: ConversationRepository
    @Autowired lateinit var jobs: OperationsService
    @Autowired lateinit var aiClient: com.sagomungchi.core.conversation.client.AiClient
    @Autowired lateinit var usage: AnalysisUsageService
    @Autowired lateinit var redis: StringRedisTemplate
    @Autowired lateinit var tx: TransactionTemplate
    @Autowired lateinit var deletion: ConversationDeletionService
    @MockitoBean lateinit var entitlement: AnalysisEntitlementProvider
    @MockitoBean lateinit var outbox: OutboxRelay
    @MockitoSpyBean lateinit var audits: ConversationRetryAuditRepository
    @MockitoSpyBean lateinit var retryRows: ConversationRetryRepository
    private lateinit var owner: UUID
    private lateinit var student: UUID
    private lateinit var admin: AuthenticatedAccount
    private lateinit var token: String
    private lateinit var message: UUID
    companion object {
        private val ai=AnalysisHttpStub()
        @JvmStatic @DynamicPropertySource fun urls(registry: DynamicPropertyRegistry) { registry.add("app.services.ai") { ai.url } }
        @JvmStatic @AfterAll fun close() { ai.close() }
    }
    @BeforeEach fun fixture() {
        owner=parent(jdbc);student=child(jdbc,owner)
        val user=account(jdbc,"ADMIN","SERVICE_OPS");admin=actor(jdbc,user,"ADMIN",setOf("SERVICE_OPS"));token=tokens.access(admin.session)
        `when`(entitlement.entitlement(owner,student)).thenReturn(AnalysisEntitlement(UUID.randomUUID(),20,Instant.now().plusSeconds(3600),true))
        doAnswer { assertTrue(TransactionSynchronizationManager.isActualTransactionActive());null }.`when`(entitlement).recordAttempt(eq(owner) ?: owner,eq(student) ?: student,any(UUID::class.java) ?: UUID(0,0))
        UserContextHolder.set(UserContext(owner.toString(),"PARENT",setOf(student.toString()),null))
        try {
            val id=conversations.create(student,null,null)["conversationId"] as UUID
            val ticket=conversations.prepare(id,"합성 질문 원문",null)
            message=ticket.message.id;conversations.fail(ticket,"AI_UNAVAILABLE")
        } finally { UserContextHolder.clear() }
        ai.requests.clear()
        ai.respond={ exchange,request ->
            val scope=json.readTree(request.body).path("scope")
            exchange.event("status","""{"state":"RUNNING","message":"합성 조회"}""")
            exchange.event("result",json.writeValueAsString(mapOf("answer" to "합성 대체 답변","source" to "TEMPLATE","scope" to scope,
                "metrics" to emptyList<Any>(),"evidence" to emptyList<Any>(),"recordCount" to 0,
                "verification" to mapOf("numbersMatched" to true,"quotesMatched" to true,"contentAllowed" to true),
                "fallback" to mapOf("reason" to "AI_UNAVAILABLE","draftVerification" to null))))
            exchange.event("done","{}")
        }
    }
    private fun quota()=redis.opsForValue().get(AnalysisUsageService.counterWindow(student,Instant.now()).first)?.toInt() ?: 0
    private fun count(sql: String,vararg args: Any)=jdbc.queryForObject(sql,Int::class.java,*args)!!
    private fun accept(key: UUID=UUID.randomUUID())=retries.request(message,key,admin)
    private fun post(key: UUID,access: String=token)=mvc.post("/api/v1/admin/jobs/$message/retry") { header("Authorization","Bearer $access");header("Idempotency-Key",key) }

    @Test fun `durable accepted request executes once with owner scope and replay survives cache removal`() {
        val key=UUID.randomUUID()
        val response=post(key).andExpect { status { isAccepted() };jsonPath("$.status") { value("QUEUED") } }.andReturn().response
        val request=UUID.fromString(json.readTree(response.contentAsString).path("retryRequestId").asText())
        assertFalse(response.contentAsString.contains("합성 질문"));assertEquals(1,quota())
        assertEquals("QUEUED",jobs.job(message).status);assertEquals(0,count("SELECT count(*) FROM job_execution WHERE job_id=?",message))
        worker.runOne(request);worker.runOne(request)
        assertEquals("COMPLETED",messages.message(message)!!.status);assertEquals(2,quota());assertEquals(1,ai.requests.size)
        val sent=ai.requests.single();assertEquals(owner.toString(),sent.header("X-User-Id"));assertEquals("PARENT",sent.header("X-User-Role"));assertEquals(student.toString(),sent.header("X-Student-Scope"))
        assertEquals(1,count("SELECT count(*) FROM job_execution WHERE job_id=? AND status='COMPLETED' AND triggered_by=?",message,admin.account.id))
        assertEquals(1,count("SELECT count(*) FROM audit_log WHERE target_id=? AND action='JOB_RETRY_COMPLETED'",message))
        jdbc.update("DELETE FROM idempotency_record WHERE user_id=? AND idempotency_key=?",admin.account.id,key)
        assertEquals(response.contentAsString,post(key).andExpect { status { isAccepted() } }.andReturn().response.contentAsString)
        assertEquals(2,quota())
        val dir=java.nio.file.Path.of("build/conversation-retry-contracts");java.nio.file.Files.createDirectories(dir)
        java.nio.file.Files.writeString(dir.resolve("accepted.json"),response.contentAsString)
    }
    @Test fun `open AI circuit fails background execution without HTTP and preserves quota and audit`() {
        val accepted=accept()
        aiClient.circuit.transitionToOpenState()
        try {
            worker.runOne(accepted.retryRequestId)
            assertTrue(ai.requests.isEmpty())
            assertEquals("FAILED",messages.message(message)!!.status)
            assertEquals("AI_UNAVAILABLE",jobs.job(message).failureReason)
            assertEquals(2,quota())
            assertEquals(1,count("SELECT count(*) FROM job_execution WHERE job_id=? AND status='FAILED'",message))
            assertEquals(1,count("SELECT count(*) FROM audit_log WHERE target_id=? AND action='JOB_RETRY_FAILED'",message))
            worker.runOne(accepted.retryRequestId)
            assertEquals(2,quota());assertTrue(ai.requests.isEmpty())
        } finally { aiClient.circuit.reset() }
    }
    @Test fun `permission denial and invalid owner never admit a request`() {
        for(permission in listOf("CONTENT","PAYMENT_VIEW","PAYMENT_REFUND")) {
            val user=account(jdbc,"ADMIN",permission);val identity=actor(jdbc,user,"ADMIN",setOf(permission))
            post(UUID.randomUUID(),tokens.access(identity.session)).andExpect { status { isForbidden() } }
            assertFailsWith<BusinessException> { retries.request(message,UUID.randomUUID(),identity) }
        }
        jdbc.update("UPDATE student SET status='DELETION_REQUESTED' WHERE id=?",student)
        post(UUID.randomUUID()).andExpect { status { isForbidden() } }
        assertEquals(0,count("SELECT count(*) FROM conversation_job_retry WHERE message_id=?",message));assertEquals(1,quota())
    }
    @Test fun `different concurrent keys admit only one generation and charge only at execution`() {
        val pool=Executors.newFixedThreadPool(2);val gate=CountDownLatch(1)
        try {
            val work=List(2) { pool.submit<Int> { gate.await();try { accept();202 } catch(ex: BusinessException) { ex.status.value() } } }
            gate.countDown();assertEquals(listOf(202,409),work.map { it.get(15,TimeUnit.SECONDS) }.sorted())
        } finally { pool.shutdownNow() }
        assertEquals(1,count("SELECT count(*) FROM conversation_job_retry WHERE message_id=?",message));assertEquals(1,quota())
    }
    @Test fun `same durable key cannot be applied to another message`() {
        val key=UUID.randomUUID();accept(key)
        val error=assertFailsWith<BusinessException> { retries.request(UUID.randomUUID(),key,admin) }
        assertEquals("IDEMPOTENCY_KEY_REUSED",error.code)
    }
    @Test fun `two workers claim once and late results cannot overwrite recovered generation`() {
        val accepted=accept();val entered=CountDownLatch(1);val release=CountDownLatch(1)
        ai.respond={ exchange,_ -> entered.countDown();release.await(10,TimeUnit.SECONDS);exchange.event("error","""{"code":"AI_UNAVAILABLE"}""") }
        val pool=Executors.newFixedThreadPool(2)
        try {
            val first=pool.submit { worker.runOne(accepted.retryRequestId) };assertTrue(entered.await(10,TimeUnit.SECONDS))
            pool.submit { worker.runOne(accepted.retryRequestId) }.get(5,TimeUnit.SECONDS)
            jdbc.update("UPDATE conversation_job_retry SET accepted_at=now()-interval '200 seconds',started_at=now()-interval '140 seconds' WHERE id=?",accepted.retryRequestId)
            retries.stale().filter { it.id==accepted.retryRequestId }.forEach { retries.fail(it,"STREAM_INTERRUPTED") }
            val next=accept();assertEquals(accepted.generation+1,next.generation)
            release.countDown();first.get(10,TimeUnit.SECONDS)
            assertEquals("QUEUED",jobs.job(message).status);assertEquals(next.generation,messages.message(message)!!.retryCount)
            assertEquals(1,ai.requests.size);assertEquals(2,quota())
        } finally { release.countDown();pool.shutdownNow() }
    }
    @Test fun `queued expiration does not consume an attempt and leaves no fake execution`() {
        val accepted=accept()
        jdbc.update("UPDATE conversation_job_retry SET accepted_at=now()-interval '140 seconds' WHERE id=?",accepted.retryRequestId)
        retries.stale().filter { it.id==accepted.retryRequestId }.forEach { retries.fail(it,"STREAM_INTERRUPTED") }
        worker.runOne(accepted.retryRequestId)
        assertEquals("FAILED",messages.message(message)!!.status);assertEquals(1,quota());assertTrue(ai.requests.isEmpty())
        assertEquals(0,count("SELECT count(*) FROM job_execution WHERE job_id=?",message))
    }
    @Test fun `permission or quota loss after acceptance fails without AI execution`() {
        val accepted=accept()
        `when`(entitlement.entitlement(owner,student)).thenReturn(AnalysisEntitlement(UUID.randomUUID(),1,Instant.now().plusSeconds(60),true))
        worker.runOne(accepted.retryRequestId)
        assertEquals("FAILED",messages.message(message)!!.status);assertEquals("USAGE_LIMIT_REACHED",jobs.job(message).failureReason)
        assertEquals(1,quota());assertTrue(ai.requests.isEmpty())
    }
    @Test fun `redis request marker prevents another debit after a rolled back DB claim`() {
        val accepted=accept()
        doThrow(IllegalStateException("synthetic claim rollback")).`when`(retryRows).startExecution(any(ConversationRetry::class.java) ?: ConversationRetry(UUID(0,0),UUID(0,0),1,UUID(0,0),UUID(0,0),"QUEUED",Instant.EPOCH,null,null))
        assertFailsWith<IllegalStateException> { retries.claim(accepted.retryRequestId) }
        assertEquals("QUEUED",retryRows.find(accepted.retryRequestId)!!.status);assertEquals(2,quota())
        reset(retryRows)
        worker.runOne(accepted.retryRequestId)
        assertEquals(2,quota());assertEquals("COMPLETED",messages.message(message)!!.status)
    }
    @Test fun `request audit failure rolls back admission before any additional quota`() {
        doThrow(IllegalStateException("synthetic request audit failure")).`when`(audits).insert(anyRetry(),eq("JOB_RETRY_REQUESTED") ?: "",eq("SUCCESS") ?: "")
        assertFailsWith<IllegalStateException> { accept() }
        assertEquals("FAILED",messages.message(message)!!.status);assertEquals(0,messages.message(message)!!.retryCount)
        assertEquals(0,count("SELECT count(*) FROM conversation_job_retry WHERE message_id=?",message));assertEquals(1,quota())
    }
    @Test fun `terminal audit failure rolls back result and recovery closes the preserved lease`() {
        val accepted=accept();val ticket=retries.claim(accepted.retryRequestId)!!
        doThrow(IllegalStateException("synthetic terminal audit failure")).`when`(audits).insert(anyRetry(),eq("JOB_RETRY_FAILED") ?: "",eq("FAILURE") ?: "")
        assertFailsWith<IllegalStateException> { conversations.fail(ticket,"AI_UNAVAILABLE") }
        assertEquals("RUNNING",messages.message(message)!!.status);assertEquals("RUNNING",retryRows.find(accepted.retryRequestId)!!.status)
        reset(audits);conversations.fail(ticket,"AI_UNAVAILABLE")
        assertEquals("FAILED",retryRows.find(accepted.retryRequestId)!!.status)
        assertEquals(1,count("SELECT count(*) FROM audit_log WHERE target_id=? AND action='JOB_RETRY_FAILED'",message))
    }
    @Test fun `deletion preserves terminal audit and cascades only retry metadata`() {
        val accepted=accept();retries.claim(accepted.retryRequestId)
        tx.executeWithoutResult { jdbc.queryForObject("SELECT id FROM user_account WHERE id=? FOR UPDATE",UUID::class.java,owner);deletion.deleteStudent(student) }
        assertNull(messages.message(message));assertNull(retryRows.find(accepted.retryRequestId))
        assertEquals(1,count("SELECT count(*) FROM audit_log WHERE target_id=? AND action='JOB_RETRY_FAILED'",message))
        assertEquals("FAILED",jdbc.queryForObject("SELECT status FROM job_execution WHERE id=?",String::class.java,accepted.retryRequestId))
        worker.runOne(accepted.retryRequestId);assertTrue(ai.requests.isEmpty())
    }
    @Test fun `invalid final verification remains failed and never persists an answer`() {
        val accepted=accept()
        ai.respond={ exchange,_ -> exchange.event("status","""{"state":"RUNNING","message":"test"}""");exchange.event("result","""{"answer":"unsafe"}""");exchange.event("done","{}") }
        worker.runOne(accepted.retryRequestId)
        assertEquals("FAILED",messages.message(message)!!.status);assertNull(messages.message(message)!!.answer)
        assertEquals("AI_INVALID_RESPONSE",jobs.job(message).failureReason)
    }
    @Test fun `retry table rejects broken references duplicate generations keys and invalid lifecycle times`() {
        val accepted=accept()
        fun reject(sql: String,state: String) {
            val error=assertFailsWith<org.springframework.dao.DataIntegrityViolationException> { tx.executeWithoutResult { jdbc.update(sql,accepted.retryRequestId) } }
            val cause=generateSequence<Throwable>(error) { it.cause }.filterIsInstance<java.sql.SQLException>().first()
            assertEquals(state,cause.sqlState)
        }
        reject("UPDATE conversation_job_retry SET message_id='00000000-0000-4000-8000-999999999999' WHERE id=?","23503")
        reject("UPDATE conversation_job_retry SET requested_by='00000000-0000-4000-8000-999999999999' WHERE id=?","23503")
        reject("UPDATE conversation_job_retry SET generation=0 WHERE id=?","23514")
        reject("UPDATE conversation_job_retry SET status='INVALID' WHERE id=?","23514")
        reject("UPDATE conversation_job_retry SET started_at=now() WHERE id=?","23514")
        reject("UPDATE conversation_job_retry SET status='COMPLETED',finished_at=now() WHERE id=?","23514")
        reject("UPDATE conversation_job_retry SET status='FAILED',finished_at=accepted_at-interval '1 second' WHERE id=?","23514")
        val row=retryRows.find(accepted.retryRequestId)!!
        assertFailsWith<org.springframework.dao.DataIntegrityViolationException> { tx.executeWithoutResult { retryRows.insert(row.copy(id=UUID.randomUUID(),idempotencyKey=UUID.randomUUID())) } }
        assertFailsWith<org.springframework.dao.DataIntegrityViolationException> { tx.executeWithoutResult { retryRows.insert(row.copy(id=UUID.randomUUID(),generation=2)) } }
    }
    @Test fun `withdrawn owner after acceptance prevents background execution`() {
        val accepted=accept()
        jdbc.update("UPDATE user_account SET status='WITHDRAWN' WHERE id=?",owner)
        worker.runOne(accepted.retryRequestId)
        assertEquals("FAILED",messages.message(message)!!.status);assertEquals(1,quota());assertTrue(ai.requests.isEmpty())
    }
    @Test fun `completion audit failure prevents answer persistence and records failed execution`() {
        val accepted=accept()
        doThrow(IllegalStateException("synthetic completion audit failure")).`when`(audits).insert(anyRetry(),eq("JOB_RETRY_COMPLETED") ?: "",eq("SUCCESS") ?: "")
        worker.runOne(accepted.retryRequestId)
        assertEquals("FAILED",messages.message(message)!!.status);assertNull(messages.message(message)!!.answer)
        assertEquals(0,count("SELECT count(*) FROM audit_log WHERE target_id=? AND action='JOB_RETRY_COMPLETED'",message))
        assertEquals(1,count("SELECT count(*) FROM audit_log WHERE target_id=? AND action='JOB_RETRY_FAILED'",message))
    }
    @Test fun `deletion and independent failure use the same row lock order`() {
        val accepted=accept();val ticket=retries.claim(accepted.retryRequestId)!!
        val locked=CountDownLatch(1);val release=CountDownLatch(1);val deleting=CountDownLatch(1);val pool=Executors.newFixedThreadPool(2)
        try {
            val failure=pool.submit { tx.executeWithoutResult {
                jdbc.queryForObject("SELECT id FROM conversation_message WHERE id=? FOR UPDATE",UUID::class.java,message)
                locked.countDown();assertTrue(release.await(10,TimeUnit.SECONDS));conversations.fail(ticket,"STREAM_INTERRUPTED")
            } }
            assertTrue(locked.await(10,TimeUnit.SECONDS))
            val remove=pool.submit { tx.executeWithoutResult {
                jdbc.queryForObject("SELECT id FROM user_account WHERE id=? FOR UPDATE",UUID::class.java,owner)
                deleting.countDown();deletion.deleteStudent(student)
            } }
            assertTrue(deleting.await(10,TimeUnit.SECONDS));Thread.sleep(100);release.countDown()
            failure.get(10,TimeUnit.SECONDS);remove.get(10,TimeUnit.SECONDS)
            assertNull(messages.message(message));assertEquals(1,count("SELECT count(*) FROM audit_log WHERE target_id=? AND action='JOB_RETRY_FAILED'",message))
        } finally { release.countDown();pool.shutdownNow() }
    }
    @Test fun `removed linkage after admission fails before AI or quota`() {
        val accepted=accept();jdbc.update("DELETE FROM guardianship WHERE parent_user_id=? AND student_id=?",owner,student)
        worker.runOne(accepted.retryRequestId)
        assertEquals("FAILED",messages.message(message)!!.status);assertEquals("CHILD_NOT_LINKED",jobs.job(message).failureReason)
        assertEquals(1,quota());assertTrue(ai.requests.isEmpty())
    }
    @Test fun `withdrawn consent after admission fails before AI or quota`() {
        val accepted=accept();jdbc.update("DELETE FROM consent WHERE subject_user_id=?",owner)
        worker.runOne(accepted.retryRequestId)
        assertEquals("FAILED",messages.message(message)!!.status);assertEquals("CHILD_NOT_LINKED",jobs.job(message).failureReason)
        assertEquals(1,quota());assertTrue(ai.requests.isEmpty())
    }
    private fun anyRetry()=any(ConversationRetry::class.java) ?: ConversationRetry(UUID(0,0),UUID(0,0),1,UUID(0,0),UUID(0,0),"QUEUED",Instant.EPOCH,null,null)
}
