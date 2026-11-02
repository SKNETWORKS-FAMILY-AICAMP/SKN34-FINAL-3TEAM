package com.sagomungchi.core.report

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core._common.messaging.OutboxRelay
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.admin.session
import com.sagomungchi.core.conversation.service.AnalysisEntitlement
import com.sagomungchi.core.conversation.service.AnalysisEntitlementProvider
import com.sagomungchi.core.learning.LearningHttpStub
import com.sagomungchi.core.report.domain.ReportTemplateSettings
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.AfterAll
import org.mockito.Mockito.`when`
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.boot.test.web.server.LocalServerPort
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Instant
import java.util.UUID
import kotlin.test.*

/** 실제 core HTTP·PostgreSQL·Redis, AI 응답만 합성 HTTP 대역. */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = [
    "spring.rabbitmq.listener.simple.auto-startup=false",
    "spring.datasource.hikari.maximum-pool-size=5", "spring.datasource.hikari.minimum-idle=0",
])
class ReportTemplateHttpIntegrationTest : IntegrationTestSupport() {
    @LocalServerPort var port: Int = 0
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var tokens: TokenService
    @MockitoBean lateinit var entitlement: AnalysisEntitlementProvider
    @MockitoBean lateinit var outbox: OutboxRelay
    private lateinit var owner: UUID
    private lateinit var student: UUID
    private lateinit var token: String
    private lateinit var conversation: String
    private val settings = ReportTemplateSettings(tone = "EASY", highlightMetrics = listOf("ATTEMPTS"))

    companion object {
        private val ai = LearningHttpStub()
        @JvmStatic @DynamicPropertySource fun urls(registry: DynamicPropertyRegistry) {
            registry.add("app.services.ai") { ai.url }
        }
        @JvmStatic @AfterAll fun stop() { ai.close() }
    }
    @BeforeEach fun setup() {
        owner=parent(jdbc); student=child(jdbc,owner)
        token=tokens.access(session(jdbc,owner,"PARENT"))
        `when`(entitlement.entitlement(owner,student)).thenReturn(
            AnalysisEntitlement(UUID.randomUUID(),30,Instant.now().plusSeconds(3600),true))
        ai.reset()
        ai.respond={ LearningHttpStub.Reply(body=json.writeValueAsString(mapOf("settings" to settings,"clarification" to null))) }
        val response=call("/api/v1/conversations",mapOf("childId" to student))
        assertEquals(201,response.statusCode(),response.body())
        conversation=json.readTree(response.body())["conversationId"].asText()
    }
    private fun call(path: String, body: Any?=null, bearer: String=token, headers: Map<String,String> = emptyMap()): HttpResponse<String> {
        val request=HttpRequest.newBuilder(URI("http://127.0.0.1:$port$path"))
            .header("Authorization","Bearer $bearer").header("Content-Type","application/json")
        headers.forEach { (k,v) -> request.header(k,v) }
        if(body==null) request.GET() else request.POST(HttpRequest.BodyPublishers.ofString(json.writeValueAsString(body)))
        return HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).build().use {
            it.send(request.build(),HttpResponse.BodyHandlers.ofString())
        }
    }
    private fun path()="/api/v1/conversations/$conversation/report-template"
    private fun proposal(): String {
        val response=call(path()+"/proposals",mapOf("question" to "쉬운 설명으로 바꾸고 답변 제출 시도 수를 강조해 주세요"))
        assertEquals(200,response.statusCode(),response.body())
        return json.readTree(response.body())["proposalId"].asText()
    }
    private fun current()=json.readTree(call(path()).body())

    @Test fun `확인 전에는 기본값이고 확인 후 SYSTEM 조회에 같은 설정을 전달한다`() {
        val id=proposal()
        assertEquals("DEFAULT",current()["settings"]["tone"].asText())
        assertEquals("/internal/analysis/report-template",ai.requests.single().target)
        assertEquals("PARENT",ai.requests.single().header("X-User-Role"))
        assertEquals(200,call(path()+"/confirm",mapOf("proposalId" to id)).statusCode())
        assertEquals(1,current()["revision"].asInt())
        assertEquals("EASY",current()["settings"]["tone"].asText())
        val headers=mapOf("X-Internal-Token" to "test-token","X-User-Role" to "SYSTEM","X-Student-Scope" to student.toString())
        val response=call("/internal/students/$student/report-template",headers=headers)
        assertEquals(200,response.statusCode(),response.body())
        assertEquals(current(),json.readTree(response.body()))
        // 선택 실행: 실제 core의 저장 설정을 Python report 클라이언트로 읽어 파일까지 검증.
        // 미설정 시 이 검증을 수행했다고 집계하지 않는다. 서비스 CI에는 Python 환경을 요구하지 않음.
        System.getenv("REPORT_TEMPLATE_PROBE_PYTHON")?.let { python ->
            for (privacy in listOf("public", "private")) {
            jdbc.update("UPDATE student SET parent_sharing_enabled=? WHERE id=?", privacy == "public", student)
            val script=java.nio.file.Path.of("../../scripts/verify_report_template_rendering.py").toAbsolutePath()
            val log=java.nio.file.Path.of("build/report-template-probe-$privacy.log").toAbsolutePath()
            val process=ProcessBuilder(python,"-X","utf8",script.toString(),"http://127.0.0.1:$port",student.toString(),privacy)
                .redirectErrorStream(true).redirectOutput(log.toFile()).apply {
                    environment()["INTERNAL_TOKEN"]="test-token"
                    environment()["DATABASE_URL"]="postgresql+psycopg://unused:unused@127.0.0.1:1/unused"
                    environment()["RABBITMQ_URL"]="amqp://unused:unused@127.0.0.1:1/"
                }.start()
            try {
                assertTrue(process.waitFor(90,java.util.concurrent.TimeUnit.SECONDS),"report 연결 검증 시간 초과")
                assertEquals(0,process.exitValue(),java.nio.file.Files.readString(log))
            } finally { if(process.isAlive) process.destroyForcibly() }
            }
            jdbc.update("UPDATE student SET parent_sharing_enabled=true WHERE id=?",student)
        }
        assertEquals(409,call(path()+"/confirm",mapOf("proposalId" to id)).statusCode())
        val recorded=org.mockito.Mockito.mockingDetails(entitlement).invocations.filter { it.method.name=="recordAttempt" }
        assertEquals(1,recorded.size)
        assertEquals(owner,recorded.single().arguments[0])
        assertEquals(student,recorded.single().arguments[1])
        assertIs<UUID>(recorded.single().arguments[2])
        assertEquals(403,call("/internal/students/$student/report-template",headers=headers+mapOf("X-Student-Scope" to UUID.randomUUID().toString())).statusCode())
        // 삭제 요청 접수 직후(학생 행 아직 ACTIVE)에는 제안 만료가 아닌 학생 상태 충돌로 응답한다.
        jdbc.update("INSERT INTO deletion_request(id,requested_by,student_id,scope,status,requested_at) VALUES(?,?,?,'RECORDS','REQUESTED',CURRENT_TIMESTAMP)",UUID.randomUUID(),owner,student)
        val unavailable=call("/internal/students/$student/report-template",headers=headers)
        assertEquals(409,unavailable.statusCode())
        assertEquals("STUDENT_UNAVAILABLE",json.readTree(unavailable.body())["code"].asText())
    }
    @Test fun `다른 학부모는 설정 조회와 제안 확인을 할 수 없다`() {
        val id=proposal(); val other=parent(jdbc)
        val otherToken=tokens.access(session(jdbc,other,"PARENT"))
        assertEquals(404,call(path(),bearer=otherToken).statusCode())
        assertEquals(404,call(path()+"/confirm",mapOf("proposalId" to id),otherToken).statusCode())
        assertEquals(0,current()["revision"].asInt())
    }
    @Test fun `확인 시 이용권이 없으면 변경안을 저장하지 않는다`() {
        val id=proposal()
        `when`(entitlement.entitlement(owner,student)).thenReturn(
            AnalysisEntitlement(UUID.randomUUID(),0,Instant.now().plusSeconds(3600),false))
        assertEquals(429,call(path()+"/confirm",mapOf("proposalId" to id)).statusCode())
        assertEquals(0,current()["revision"].asInt())
    }
    @Test fun `AI 호출 중 연결 해제되면 변경안을 저장하지 않는다`() {
        ai.respond={
            jdbc.update("UPDATE guardianship SET status='UNLINKED' WHERE parent_user_id=? AND student_id=?",owner,student)
            LearningHttpStub.Reply(body=json.writeValueAsString(mapOf("settings" to settings,"clarification" to null)))
        }
        val response=call(path()+"/proposals",mapOf("question" to "쉽게 설명해 주세요"))
        assertEquals(403,response.statusCode(),response.body())
        assertEquals(0,jdbc.queryForObject("SELECT count(*) FROM parent_report_template WHERE parent_user_id=?",Int::class.java,owner))
    }
    @Test fun `AI 오류와 공개 설정 추가 응답은 설정으로 저장하지 않는다`() {
        ai.respond={ LearningHttpStub.Reply(status=503,body="{}") }
        assertEquals(502,call(path()+"/proposals",mapOf("question" to "쉽게 설명해 주세요")).statusCode())
        ai.respond={ LearningHttpStub.Reply(body="""{"settings":{"sectionOrder":[],"highlightMetrics":[],"tone":"EASY","showOriginalText":true},"clarification":null}""") }
        assertEquals(502,call(path()+"/proposals",mapOf("question" to "원문을 보여 주세요")).statusCode())
        assertEquals(0,current()["revision"].asInt())
    }
}
