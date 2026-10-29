package com.sagomungchi.core.admin
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.admin.service.OperationRetryService
import com.sagomungchi.core.admin.service.OperationsService
import com.sagomungchi.core.admin.domain.*
import com.sagomungchi.core.notification.messaging.NotificationRedisPublisher
import com.sagomungchi.core.notification.domain.NotificationStored
import com.sagomungchi.core._common.web.HttpExchangeResult
import com.sun.net.httpserver.HttpServer
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.BeforeEach
import org.mockito.Mockito.*
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.post
import org.springframework.http.MediaType
import org.springframework.transaction.support.TransactionSynchronizationManager
import java.net.InetSocketAddress
import java.time.OffsetDateTime
import java.util.UUID
import java.util.concurrent.*
import java.util.concurrent.atomic.AtomicInteger
import kotlin.test.*

@AutoConfigureMockMvc
class AdminOperationsIntegrationTest : IntegrationTestSupport() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var retry: OperationRetryService
    @Autowired lateinit var operations: OperationsService
    @MockitoSpyBean lateinit var missionAudits: com.sagomungchi.core.admin.repository.MissionAuditRepository
    @MockitoSpyBean lateinit var learningClient: com.sagomungchi.core.learning.client.LearningClient
    @MockitoSpyBean lateinit var publisher: NotificationRedisPublisher
    private fun token(permission: String?="SERVICE_OPS",role: String="ADMIN"): Pair<UUID,String> {
        val user=account(jdbc,role,permission)
        if(role=="PARENT") consents(jdbc,user)
        return user to tokens.access(session(jdbc,user,role))
    }
    private fun notification(actor: UUID,status: String="FAILED"): UUID {
        val id=UUID.randomUUID()
        jdbc.update("INSERT INTO notification(id,user_id,type,source_event_id,title,link,status,retry_count,failure_reason,created_at) VALUES(?,?,'REPORT_COMPLETED',?,'synthetic title','/parent/report',?,0,'raw secret student answer',?)",
            id,actor,UUID.randomUUID(),status,OffsetDateTime.parse("2026-01-02T00:00:00Z"))
        return id
    }
    @BeforeEach fun resetHttp() { requests.clear(); statsStatus=200; statsBody=STATS; missionStatus=200; missionBody=MISSIONS }

    @Test fun `401 403 permissions and exact general administrator reads`() {
        val id=UUID.randomUUID()
        val paths=listOf("/overview","/jobs","/jobs/$id","/queues","/audit-logs","/missions")
        paths.forEach { mvc.get("/api/v1/admin$it").andExpect { status { isUnauthorized() } } }
        val (_,parent)=token(null,"PARENT")
        paths.forEach { mvc.get("/api/v1/admin$it") { header("Authorization","Bearer $parent") }.andExpect { status { isForbidden() } } }
        for(permission in listOf(null,"CONTENT","PAYMENT_VIEW","PAYMENT_REFUND")) {
            val (_,access)=token(permission)
            listOf("/jobs","/queues").forEach { mvc.get("/api/v1/admin$it") { header("Authorization","Bearer $access") }.andExpect { status { isForbidden() } } }
            mvc.post("/api/v1/admin/jobs/$id/retry") { header("Authorization","Bearer $access");header("Idempotency-Key",UUID.randomUUID()) }.andExpect { status { isForbidden() } }
            listOf("/overview?from=2026-01-01&to=2026-01-03","/audit-logs?from=2026-01-01&to=2026-01-03").forEach {
                mvc.get("/api/v1/admin$it") { header("Authorization","Bearer $access") }.andExpect { status { isOk() } }
            }
            if(permission!="CONTENT") mvc.post("/api/v1/admin/missions") { header("Authorization","Bearer $access");contentType=MediaType.APPLICATION_JSON;content="{}" }.andExpect { status { isForbidden() } }
        }
    }
    @Test fun `overview uses actual learning contract and preserves failures without private fields`() {
        val (_,access)=token()
        val path="/api/v1/admin/overview?from=2026-01-01&to=2026-01-03"
        val result=mvc.get(path) { header("Authorization","Bearer $access") }.andExpect {
            status { isOk() };jsonPath("$.learning.attempts") { value(7) };jsonPath("$.learning.completedAttempts") { value(3) }
        }.andReturn().response.contentAsString
        assertFalse(result.contains("secret"));assertFalse(result.contains("studentName"));assertEquals(4,json.readTree(result).path("missionCounts").size());assertEquals(12,json.readTree(result).path("missionCounts")[0].path("count").asInt())
        val req=requests.last();assertEquals("ADMIN",req.role);assertNull(req.scope);assertEquals("test-token",req.token)
        statsStatus=503
        mvc.get(path) { header("Authorization","Bearer $access") }.andExpect { status { isServiceUnavailable() } }
        statsStatus=200;statsBody="{\"attempts\":0}"
        mvc.get(path) { header("Authorization","Bearer $access") }.andExpect { status { isServiceUnavailable() };jsonPath("$.code") { value("LEARNING_INVALID_RESPONSE") } }
        mvc.get("/api/v1/admin/overview?from=2026-01-01") { header("Authorization","Bearer $access") }.andExpect { status { isBadRequest() } }
    }
    @Test fun `jobs map actual ids and histories with stable filters pagination and redaction`() {
        val (actor,access)=token();val id=notification(actor)
        val execution=UUID.randomUUID()
        jdbc.update("INSERT INTO job_execution(id,job_type,job_id,attempt_no,status,error_code,error_detail,triggered_by,started_at,finished_at) VALUES(?,'NOTIFICATION',?,1,'FAILED','raw secret','private student answer',?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",execution,id,actor)
        jdbc.update("INSERT INTO audit_log(id,actor_user_id,action,target_type,target_id,result,detail,created_at) VALUES(?,?,'JOB_RETRY','NOTIFICATION',?,'FAILURE','{\"secret\":\"student text\"}',CURRENT_TIMESTAMP)",UUID.randomUUID(),actor,id)
        val detail=mvc.get("/api/v1/admin/jobs/$id") { header("Authorization","Bearer $access") }.andExpect {
            status { isOk() };jsonPath("$.jobId") { value(id.toString()) };jsonPath("$.failureReason") { value("REDACTED_ERROR") }
            jsonPath("$.executions[0].executionId") { value(execution.toString()) };jsonPath("$.retryable") { value(true) };jsonPath("$.updatedAt") { doesNotExist() }
        }.andReturn().response.contentAsString
        assertFalse(detail.contains("secret"));assertFalse(detail.contains("student answer"));assertFalse(detail.contains("errorDetail"))
        mvc.get("/api/v1/admin/jobs?from=2026-01-01&to=2026-01-03&type=NOTIFICATION&status=FAILED&size=1") { header("Authorization","Bearer $access") }.andExpect { status { isOk() };jsonPath("$.items.length()") { value(1) } }
        mvc.get("/api/v1/admin/jobs?from=2026-01-01&to=2026-01-03&page=1001") { header("Authorization","Bearer $access") }.andExpect { status { isBadRequest() } }
        val audits=mvc.get("/api/v1/admin/audit-logs?targetId=$id&targetType=NOTIFICATION") { header("Authorization","Bearer $access") }.andExpect { status { isOk() } }.andReturn().response.contentAsString
        assertFalse(audits.contains("secret"));assertFalse(audits.contains("detail"))
    }
    @Test fun `real Redis retry stores actual execution and audit and replays same key response`() {
        val (actor,access)=token();val id=notification(actor);val key=UUID.randomUUID()
        fun call()=mvc.post("/api/v1/admin/jobs/$id/retry") { header("Authorization","Bearer $access");header("Idempotency-Key",key) }
            .andExpect { status { isOk() };jsonPath("$.status") { value("COMPLETED") };jsonPath("$.retryCount") { value(1) } }.andReturn().response.contentAsString
        val first=call();assertEquals(first,call())
        assertEquals(1,jdbc.queryForObject("SELECT count(*) FROM job_execution WHERE job_id=?",Int::class.java,id))
        assertEquals(1,jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE target_id=?",Int::class.java,id))
        verify(publisher,times(1)).publish(NotificationStored(id,actor))
        mvc.post("/api/v1/admin/jobs/$id/retry") { header("Authorization","Bearer $access") }.andExpect { status { isBadRequest() } }
    }
    @Test fun `same key and different key simultaneous retry cannot run a second delivery`() {
        val (actor,_)=token();val id=notification(actor);val key=UUID.randomUUID();val entered=CountDownLatch(1);val release=CountDownLatch(1)
        doAnswer { invocation ->
            assertFalse(TransactionSynchronizationManager.isActualTransactionActive())
            entered.countDown();assertTrue(release.await(10,TimeUnit.SECONDS));invocation.callRealMethod()
        }.`when`(publisher).publish(NotificationStored(id,actor))
        val pool=Executors.newFixedThreadPool(2)
        try {
            val first=pool.submit<HttpExchangeResult> { retry.retry(id,key,actor) }
            assertTrue(entered.await(10,TimeUnit.SECONDS))
            val same=runCatching { retry.retry(id,key,actor) }.exceptionOrNull()
            assertNotNull(same)
            assertEquals(409,retry.retry(id,UUID.randomUUID(),actor).status)
            release.countDown();assertEquals(200,first.get(15,TimeUnit.SECONDS).status)
            assertEquals(1,jdbc.queryForObject("SELECT retry_count FROM notification WHERE id=?",Int::class.java,id))
            assertEquals(1,jdbc.queryForObject("SELECT count(*) FROM job_execution WHERE job_id=?",Int::class.java,id))
            assertEquals(200,retry.retry(id,key,actor).status)
        } finally { release.countDown();pool.shutdownNow() }
    }

    @Test fun `failed actual delivery keeps failure retryability history and first response`() {
        val (actor,_)=token();val id=notification(actor);val key=UUID.randomUUID()
        doAnswer {
            assertFalse(TransactionSynchronizationManager.isActualTransactionActive())
            jdbc.update("UPDATE notification SET status='FAILED',failure_reason='REDIS_PUBLISH_FAILED' WHERE id=?",id)
            null
        }.`when`(publisher).publish(NotificationStored(id,actor))
        val first=retry.retry(id,key,actor)
        assertEquals(200,first.status)
        val job=json.readTree(first.body);assertEquals("FAILED",job.path("status").asText());assertTrue(job.path("retryable").asBoolean())
        assertEquals("REDIS_PUBLISH_FAILED",job.path("executions").last().path("errorCode").asText())
        assertContentEquals(first.body,retry.retry(id,key,actor).body)
        assertEquals("FAILURE",jdbc.queryForObject("SELECT result FROM audit_log WHERE target_id=?",String::class.java,id))
        verify(publisher,times(1)).publish(NotificationStored(id,actor))
    }

    @Test fun `report and conversation retry do not pretend to execute or regenerate`() {
        val (actor,access)=token();val student=UUID.randomUUID();val report=UUID.randomUUID();val conv=UUID.randomUUID();val message=UUID.randomUUID()
        jdbc.update("INSERT INTO student(id,nickname,grade,birth_year,is_demo,status,pin_failed_count,created_at,updated_at) VALUES(?,'synthetic',3,2017,false,'ACTIVE',0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",student)
        jdbc.update("INSERT INTO report_job(id,student_id,period_from,period_to,trigger,status,retry_count,created_at) VALUES(?,?,'2026-01-01','2026-01-07','SCHEDULE','FAILED',0,CURRENT_TIMESTAMP)",report,student)
        jdbc.update("INSERT INTO conversation(id,parent_user_id,student_id,period_from,period_to,created_at,updated_at) VALUES(?,?,?,'2026-01-01','2026-01-07',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",conv,actor,student)
        jdbc.update("INSERT INTO conversation_message(id,conversation_id,seq,question,scope_changed,status,retry_count,created_at) VALUES(?,?,1,'student secret',false,'FAILED',0,CURRENT_TIMESTAMP)",message,conv)
        for(id in listOf(report,message)) {
            mvc.post("/api/v1/admin/jobs/$id/retry") { header("Authorization","Bearer $access");header("Idempotency-Key",UUID.randomUUID()) }.andExpect { status { isServiceUnavailable() };jsonPath("$.code") { value("JOB_RETRY_UNAVAILABLE") } }
            assertEquals(0,jdbc.queryForObject("SELECT count(*) FROM job_execution WHERE job_id=?",Int::class.java,id))
            assertEquals(1,jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE target_id=? AND result='FAILURE'",Int::class.java,id))
        }
        assertEquals("FAILED",jdbc.queryForObject("SELECT status FROM report_job WHERE id=?",String::class.java,report))
        assertEquals(0,jdbc.queryForObject("SELECT count(*) FROM outbox_event WHERE subject=?",Int::class.java,student.toString()))
    }
    @Test fun `missions proxy supports every declared method body and validated admin headers`() {
        val (admin,access)=token("CONTENT");val id=UUID.randomUUID();val payload="{\"version\":3,\"rubricVersion\":2}"
        val requestsToSend=listOf("GET" to "", "POST" to "", "GET" to "/$id", "PATCH" to "/$id", "PUT" to "/$id/rubric", "GET" to "/$id/preview", "POST" to "/$id/review-request", "POST" to "/$id/review", "POST" to "/$id/publish", "POST" to "/$id/unpublish")
        missionBody="""{"missionId":"$id","currentVersion":2,"currentRubricVersion":3}"""
        for((method,suffix) in requestsToSend) {
            mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.request(org.springframework.http.HttpMethod.valueOf(method),"/api/v1/admin/missions$suffix")
                .header("Authorization","Bearer $access").header("X-User-Role","SYSTEM").header("X-Student-Scope",UUID.randomUUID()).contentType(MediaType.APPLICATION_JSON).content(if(method=="GET") "" else payload))
                .andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers.status().isOk)
            val received=requests.last();assertEquals(method,received.method);assertEquals("/internal/admin/missions$suffix",received.path)
            assertEquals(admin.toString(),received.user);assertEquals("ADMIN",received.role);assertNull(received.scope);assertEquals("test-token",received.token)
            if(method!="GET") assertEquals(payload,received.body)
        }
        missionStatus=422;missionBody="{\"code\":\"MISSION_PUBLISH_INCOMPLETE\",\"detail\":\"student secret token\",\"missingFields\":[\"rubric\"]}"
        val error=mvc.post("/api/v1/admin/missions/$id/publish") { header("Authorization","Bearer $access");contentType=MediaType.APPLICATION_JSON;content=payload }.andExpect { status { isUnprocessableEntity() };jsonPath("$.code") { value("MISSION_PUBLISH_INCOMPLETE") } }.andReturn().response.contentAsString
        assertFalse(error.contains("secret"));missionStatus=404;missionBody="""{"code":"NOT_FOUND","detail":"secret"}"""
        mvc.get("/api/v1/admin/missions") { header("Authorization","Bearer $access") }.andExpect { status { isNotFound() };jsonPath("$.code") { value("NOT_FOUND") } }
    }
    @Test fun `overview rejects missing duplicate negative and unavailable mission counts`() {
        val (_,access)=token()
        for(body in listOf("{}", """{"counts":[]} """, MISSIONS.replace("REVIEW_REQUIRED","DRAFT"), MISSIONS.replace("12","-1"))) {
            missionBody=body
            mvc.get("/api/v1/admin/overview?from=2026-01-01&to=2026-01-03") { header("Authorization","Bearer $access") }
                .andExpect { status { isServiceUnavailable() };jsonPath("$.code") { value("LEARNING_INVALID_RESPONSE") } }
        }
        missionStatus=503
        mvc.get("/api/v1/admin/overview?from=2026-01-01&to=2026-01-03") { header("Authorization","Bearer $access") }
            .andExpect { status { isServiceUnavailable() } }
    }
    @Test fun `mission audit uses verified actor returned versions and no request or error text`() {
        val (admin,access)=token("CONTENT");val id=UUID.randomUUID()
        missionBody="""{"missionId":"$id","currentVersion":4,"currentRubricVersion":2}"""
        val result=mvc.post("/api/v1/admin/missions") {
            header("Authorization","Bearer $access");header("X-User-Id",UUID.randomUUID());contentType=MediaType.APPLICATION_JSON;content="""{"question":"private secret"}"""
        }.andExpect { status { isOk() } }.andReturn().response
        val operation=UUID.fromString(result.getHeader("X-Admin-Operation-Id"))
        val rows=jdbc.queryForList("SELECT * FROM audit_log WHERE actor_user_id=? AND target_type='MISSION' ORDER BY created_at",admin)
        assertEquals(2,rows.size);assertEquals(operation,rows[0]["id"]);assertEquals("MISSION_CREATE_REQUESTED",rows[0]["action"])
        assertEquals("MISSION_CREATE_SUCCEEDED",rows[1]["action"]);assertEquals(id,rows[1]["target_id"])
        val detail=json.readTree(rows[1]["detail"].toString())
        assertEquals(4,detail.path("currentVersion").asInt());assertEquals(2,detail.path("currentRubricVersion").asInt())
        assertEquals(operation.toString(),detail.path("operationId").asText());assertFalse(rows.toString().contains("secret"))
        assertEquals(admin.toString(),requests.last().user)
        missionStatus=404;missionBody="""{"code":"NOT_FOUND","detail":"secret"}"""
        mvc.post("/api/v1/admin/missions/$id/publish") { header("Authorization","Bearer $access");contentType=MediaType.APPLICATION_JSON;content="{}" }
            .andExpect { status { isNotFound() } }
        assertEquals(1,jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE actor_user_id=? AND action='MISSION_PUBLISH_REJECTED' AND result='FAILURE'",Int::class.java,admin))
    }
    @Test fun `uncertain provider responses stay explicit and are never retried`() {
        val (admin,access)=token("CONTENT");val id=UUID.randomUUID()
        for(body in listOf("not json","{}","""{"missionId":"${UUID.randomUUID()}","currentVersion":1,"currentRubricVersion":null}""")) {
            requests.clear();missionBody=body
            mvc.post("/api/v1/admin/missions/$id/publish") { header("Authorization","Bearer $access");contentType=MediaType.APPLICATION_JSON;content="{}" }
                .andExpect { status { isServiceUnavailable() };jsonPath("$.code") { value("LEARNING_INVALID_RESPONSE") } }
            assertEquals(1,requests.size)
        }
        missionStatus=500;missionBody="""{"code":"INTERNAL_ERROR","detail":"secret"}"""
        mvc.post("/api/v1/admin/missions/$id/publish") { header("Authorization","Bearer $access");contentType=MediaType.APPLICATION_JSON;content="{}" }
            .andExpect { status { isInternalServerError() } }
        assertEquals(4,jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE actor_user_id=? AND action='MISSION_PUBLISH_UNKNOWN'",Int::class.java,admin))
    }
    @Test fun `audit failures stop dispatch or preserve committed intent after provider success`() {
        val (admin,access)=token("CONTENT");val id=UUID.randomUUID()
        missionBody="""{"missionId":"$id","currentVersion":1,"currentRubricVersion":null}"""
        var failAction="MISSION_CREATE_REQUESTED"
        doAnswer { invocation ->
            if(invocation.getArgument<String>(2)==failAction) throw org.springframework.dao.DataAccessResourceFailureException("secret")
            invocation.callRealMethod()
        }.`when`(missionAudits).insert(org.mockito.ArgumentMatchers.any(UUID::class.java) ?: UUID(0,0),org.mockito.ArgumentMatchers.eq(admin) ?: admin,
            org.mockito.ArgumentMatchers.anyString(),org.mockito.ArgumentMatchers.nullable(UUID::class.java),org.mockito.ArgumentMatchers.anyString(),org.mockito.ArgumentMatchers.anyString())
        fun request()=mvc.post("/api/v1/admin/missions") { header("Authorization","Bearer $access");contentType=MediaType.APPLICATION_JSON;content="{}" }
            .andExpect { status { isServiceUnavailable() };jsonPath("$.code") { value("MISSION_AUDIT_UNAVAILABLE") } }
        request();assertTrue(requests.isEmpty())
        failAction="MISSION_CREATE_SUCCEEDED"
        request();assertEquals(1,requests.size)
        assertEquals(1,jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE actor_user_id=? AND action='MISSION_CREATE_REQUESTED'",Int::class.java,admin))
        assertEquals(0,jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE actor_user_id=? AND action='MISSION_CREATE_SUCCEEDED'",Int::class.java,admin))
    }
    @Test fun `transport timeout records unknown without a second call`() {
        val (admin,access)=token("CONTENT");val id=UUID.randomUUID()
        doThrow(com.sagomungchi.core._common.exception.BusinessException(org.springframework.http.HttpStatus.GATEWAY_TIMEOUT,"LEARNING_TIMEOUT","timeout"))
            .`when`(learningClient).exchange("POST","/admin/missions/$id/publish",null,"{}".toByteArray(),null,null)
        mvc.post("/api/v1/admin/missions/$id/publish") { header("Authorization","Bearer $access");contentType=MediaType.APPLICATION_JSON;content="{}" }
            .andExpect { status { isGatewayTimeout() };jsonPath("$.code") { value("LEARNING_TIMEOUT") } }
        verify(learningClient,times(1)).exchange("POST","/admin/missions/$id/publish",null,"{}".toByteArray(),null,null)
        assertEquals(1,jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE actor_user_id=? AND action='MISSION_PUBLISH_UNKNOWN'",Int::class.java,admin))
    }
    companion object {
        data class Seen(val method: String,val path: String,val body: String,val role: String?,val scope: String?,val token: String?,val user: String?)
        val requests=CopyOnWriteArrayList<Seen>()
        @Volatile var statsStatus=200
        const val STATS="{\"period\":{\"from\":\"2026-01-01\",\"to\":\"2026-01-03\"},\"inclusionRule\":\"P08\",\"attempts\":7,\"completedAttempts\":3,\"students\":2,\"studentName\":\"secret\"}"
        @Volatile var statsBody=STATS
        const val MISSIONS="""{"items":[{"question":"secret"}],"counts":[{"status":"DRAFT","count":12},{"status":"REVIEW_REQUIRED","count":2},{"status":"PUBLISHED","count":3},{"status":"UNPUBLISHED","count":1}]}"""
        @Volatile var missionStatus=200
        @Volatile var missionBody="{}"
        private val server=HttpServer.create(InetSocketAddress("127.0.0.1",0),0).apply {
            createContext("/internal") { e ->
                requests.add(Seen(e.requestMethod,e.requestURI.path,e.requestBody.readBytes().toString(Charsets.UTF_8),e.requestHeaders.getFirst("X-User-Role"),e.requestHeaders.getFirst("X-Student-Scope"),e.requestHeaders.getFirst("X-Internal-Token"),e.requestHeaders.getFirst("X-User-Id")))
                val stats=e.requestURI.path=="/internal/stats";val status=if(stats) statsStatus else missionStatus
                val body=(if(stats) statsBody else missionBody).toByteArray()
                e.responseHeaders.set("Content-Type",if(status>=400) "application/problem+json" else "application/json")
                e.sendResponseHeaders(status,body.size.toLong());e.responseBody.use { it.write(body) };e.close()
            };start()
        }
        @JvmStatic @DynamicPropertySource fun learning(registry: DynamicPropertyRegistry) { registry.add("app.services.learning") { "http://127.0.0.1:${server.address.port}" } }
    }
}
