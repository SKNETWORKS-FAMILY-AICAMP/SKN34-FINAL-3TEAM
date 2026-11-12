package com.sagomungchi.core.learning

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.client.LearningClient
import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core.account.domain.GoogleProfile
import com.sagomungchi.core.account.service.AuthService
import com.sagomungchi.core.learning.client.LearningMemoryClient
import io.github.resilience4j.circuitbreaker.CircuitBreaker
import org.junit.jupiter.api.AfterAll
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.Mockito.`when`
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.*
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.time.Clock
import java.time.Instant
import java.time.LocalDate
import java.util.UUID
import kotlin.test.*

/**
 * #566: 실제 인증·필터·PostgreSQL과 learning 계약 대역(#563·#564 전)으로 추억 검색·설명 프록시를 확인한다.
 * 하루 한도 경계(초과면 learning 미호출 429), 서킷 `learning-memory` 분리, learning 응답·오류 전달과 장애 때 사용량 되돌림.
 * KST 날짜는 paymentClock으로 고정한다(2026-11-09 월 10:00 KST).
 */
@AutoConfigureMockMvc
@Transactional(propagation = Propagation.NOT_SUPPORTED)
@TestPropertySource(properties = ["app.payment.free-product-id=00000000-0000-4000-8000-000000005660"])
class MemoryProxyIntegrationTest : PostgresRepositoryTest() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var auth: AuthService
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var general: LearningClient
    @Autowired lateinit var memory: LearningMemoryClient
    @MockitoBean(name = "paymentClock") lateinit var clock: Clock
    private lateinit var user: UUID
    private lateinit var child: UUID
    private lateinit var access: String
    private val documents = mutableListOf<UUID>()
    private val products = mutableListOf<UUID>()
    private val free = UUID.fromString("00000000-0000-4000-8000-000000005660")
    private val search = "/api/v1/students/me/memories/search"
    private val explanations = "/api/v1/students/me/memories/explanations"
    private val problem = mapOf("Content-Type" to "application/problem+json")

    companion object {
        private val stub = LearningHttpStub()
        @JvmStatic @DynamicPropertySource fun learning(registry: DynamicPropertyRegistry) {
            registry.add("app.services.learning") { stub.url }
        }
        @JvmStatic @AfterAll fun stopLearning() { stub.close() }
    }

    @BeforeEach fun prepare() {
        stub.reset(); general.circuit.reset(); memory.circuit.reset()
        `when`(clock.instant()).thenReturn(Instant.parse("2026-11-09T01:00:00Z"))
        val subject = UUID.randomUUID().toString()
        val parent = auth.login(GoogleProfile(subject, "$subject@example.test", "테스트 보호자"), null)
        user = parent.identity.account.id
        child = UUID.randomUUID()
        product(free, 0, """{"dailyMissions":1,"dailyConversations":0,"reportNarrative":false,"dailyMemorySearches":2,"dailyMemoryExplanations":1}""")
        jdbc.update("INSERT INTO student(pin_failed_count,id,nickname,grade,birth_year,is_demo,status,created_at,updated_at) VALUES(0,?,'테스트 학생',5,2016,false,'ACTIVE',now(),now())", child)
        jdbc.update("INSERT INTO guardianship(id,parent_user_id,student_id,method,status,linked_at) VALUES(?,?,?,'REGISTER','LINKED',now())", UUID.randomUUID(), user, child)
        listOf("TERMS", "PRIVACY", "GUARDIAN").forEach { kind ->
            val document = UUID.randomUUID(); documents.add(document)
            jdbc.update("INSERT INTO consent_document(id,kind,version,title,content,required,effective_from,created_at) VALUES(?,?,?,'합성 동의','본문',true,CURRENT_DATE,now())", document, kind, subject)
        }
        jdbc.queryForList("SELECT id,kind FROM consent_document WHERE required=true").forEach { doc ->
            jdbc.update("INSERT INTO consent(id,document_id,subject_user_id,student_id,agreed,status,agreed_at) VALUES(?,?,?,?,true,'AGREED',now())",
                UUID.randomUUID(), doc["id"], user, if (doc["kind"] == "GUARDIAN") child else null)
        }
        access = auth.enterStudent(child, auth.authenticate(parent.accessToken)).accessToken
    }

    @AfterEach fun cleanup() {
        jdbc.update("DELETE FROM memory_daily_usage WHERE student_id=?", child)
        jdbc.update("DELETE FROM subscription WHERE student_id=?", child)
        jdbc.update("DELETE FROM consent WHERE subject_user_id=?", user)
        jdbc.update("DELETE FROM refresh_token WHERE user_id=?", user)
        jdbc.update("DELETE FROM auth_session WHERE user_id=?", user)
        jdbc.update("DELETE FROM guardianship WHERE parent_user_id=?", user)
        jdbc.update("DELETE FROM user_account WHERE id=?", user)
        jdbc.update("DELETE FROM student WHERE id=?", child)
        documents.forEach { jdbc.update("DELETE FROM consent_document WHERE id=?", it) }; documents.clear()
        products.forEach { jdbc.update("DELETE FROM product WHERE id=?", it) }; products.clear()
    }

    private fun product(id: UUID, price: Int, limits: String) {
        jdbc.update("INSERT INTO product(id,code,name,price,billing_cycle,child_limit,features,limits,active,created_at) VALUES(?,?,'합성 상품',?,'MONTHLY',1,'{}',?::jsonb,true,now())",
            id, "synthetic-$id", price, limits)
        products.add(id)
    }

    private fun call(path: String, content: String) = mvc.perform(post(path).header("Authorization", "Bearer $access")
        .contentType(MediaType.APPLICATION_JSON).content(content))

    private fun used(kind: String) = jdbc.queryForObject("SELECT count(*) FROM memory_daily_usage WHERE student_id=? AND kind=?", Int::class.java, child, kind)!!

    private val explanationBody = "{\"query\":\"고양이\",\"attemptIds\":[\"${UUID.randomUUID()}\"]}"

    @Test fun `search and explanation send rebuilt bodies to learning and pass responses through without storing`() {
        val cards = "{\"state\":\"RESULTS\",\"cards\":[{\"themeId\":\"${UUID.randomUUID()}\",\"weekStart\":\"2026-11-02\",\"score\":0.81}]}"
        stub.respond = { LearningHttpStub.Reply(body = cards) }
        call(search, "{\"query\":\"동물 집 만들었던 문제\"}").andExpect(status().isOk())
            .andExpect(header().string("Cache-Control", "no-store")).andExpect(content().string(cards))
        val sent = stub.requests.single()
        assertEquals("POST" to "/internal/students/$child/memories/search", sent.method to sent.target)
        assertEquals(mapOf("query" to "동물 집 만들었던 문제"), json.readValue(sent.body, Map::class.java))
        assertEquals(child.toString(), sent.header("X-Student-Scope")); assertEquals("STUDENT", sent.header("X-User-Role"))

        val attempt = UUID.randomUUID()
        val generated = "{\"state\":\"GENERATED\",\"text\":\"[1] 고양이 집을 만들었어요.\",\"citations\":[{\"no\":1,\"attemptId\":\"$attempt\"}]}"
        stub.respond = { LearningHttpStub.Reply(body = generated) }
        call(explanations, "{\"attemptIds\":[\"${attempt.toString().uppercase()}\"],\"query\":\"고양이\"}").andExpect(status().isOk())
            .andExpect(header().string("Cache-Control", "no-store")).andExpect(content().string(generated))
        val explain = stub.requests.last()
        assertEquals("POST" to "/internal/students/$child/memories/explanations", explain.method to explain.target)
        assertEquals(mapOf("query" to "고양이", "attemptIds" to listOf(attempt.toString())), json.readValue(explain.body, Map::class.java))
        // 요청 1건 = 1행, KST 날짜. 질문 원문은 남기지 않는다
        assertEquals(listOf(mapOf("kind" to "EXPLANATION", "usage_date" to java.sql.Date.valueOf("2026-11-09")),
            mapOf("kind" to "SEARCH", "usage_date" to java.sql.Date.valueOf("2026-11-09"))),
            jdbc.queryForList("SELECT kind,usage_date FROM memory_daily_usage WHERE student_id=? ORDER BY kind", child))
    }

    @Test fun `daily limit boundary rejects without calling learning and each kind and KST day count separately`() {
        stub.respond = { LearningHttpStub.Reply(body = "{\"state\":\"NO_RESULTS\",\"cards\":[]}") }
        repeat(2) { call(search, "{\"query\":\"고양이\"}").andExpect(status().isOk()) }
        call(search, "{\"query\":\"고양이\"}").andExpect(status().isTooManyRequests())
            .andExpect(jsonPath("$.code").value("USAGE_LIMIT_REACHED"))
            .andExpect(jsonPath("$.detail").value("추억 검색은 하루 2회까지 쓸 수 있습니다. 내일 0시(KST)에 초기화됩니다."))
        assertEquals(2, stub.requests.size); assertEquals(2, used("SEARCH"))

        // 설명은 따로 센다(한도 1)
        stub.respond = { LearningHttpStub.Reply(body = "{\"state\":\"INSUFFICIENT\",\"text\":null,\"citations\":[]}") }
        call(explanations, explanationBody).andExpect(status().isOk())
        call(explanations, explanationBody).andExpect(status().isTooManyRequests()).andExpect(jsonPath("$.code").value("USAGE_LIMIT_REACHED"))
        assertEquals(3, stub.requests.size); assertEquals(1, used("EXPLANATION"))

        // KST 다음 날(11-10 00:00 KST)이면 다시 쓸 수 있다
        `when`(clock.instant()).thenReturn(Instant.parse("2026-11-09T15:00:00Z"))
        call(search, "{\"query\":\"고양이\"}").andExpect(status().isOk())
        assertEquals(4, stub.requests.size)
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM memory_daily_usage WHERE student_id=? AND usage_date=?", Int::class.java,
            child, LocalDate.parse("2026-11-10")))

        // 한도 0이면 첫 요청부터 막는다
        jdbc.update("UPDATE product SET limits=jsonb_set(limits,'{dailyMemoryExplanations}','0') WHERE id=?", free)
        call(explanations, explanationBody).andExpect(status().isTooManyRequests())
        assertEquals(4, stub.requests.size)
    }

    @Test fun `concurrent requests at the boundary pass exactly up to the limit`() {
        stub.respond = { Thread.sleep(50); LearningHttpStub.Reply(body = "{\"state\":\"NO_RESULTS\",\"cards\":[]}") }
        val pool = java.util.concurrent.Executors.newFixedThreadPool(6)
        try {
            val statuses = (1..6).map { pool.submit<Int> { call(search, "{\"query\":\"고양이\"}").andReturn().response.status } }.map { it.get() }
            assertEquals(listOf(200, 200, 429, 429, 429, 429), statuses.sorted())
        } finally { pool.shutdown() }
        assertEquals(2, used("SEARCH")); assertEquals(2, stub.requests.size)
    }

    @Test fun `learning errors are passed through and outages do not consume the daily limit`() {
        // 4xx(본인 문서 아님)는 그대로 전달하고 센다
        stub.respond = { LearningHttpStub.Reply(422, "{\"status\":422,\"code\":\"VALIDATION_FAILED\",\"detail\":\"검색 결과의 시도만 설명할 수 있습니다.\"}", problem) }
        call(explanations, explanationBody).andExpect(status().isUnprocessableEntity()).andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        assertEquals(1, used("EXPLANATION"))

        // 임베딩 장애 503 AI_UNAVAILABLE은 그대로 전달하고 되돌린다
        stub.respond = { LearningHttpStub.Reply(503, "{\"status\":503,\"code\":\"AI_UNAVAILABLE\",\"retryable\":true}", problem) }
        repeat(3) {
            call(search, "{\"query\":\"고양이\"}").andExpect(status().isServiceUnavailable()).andExpect(jsonPath("$.code").value("AI_UNAVAILABLE"))
        }
        assertEquals(0, used("SEARCH"))

        // 설명의 ai 장애도 learning 503 AI_UNAVAILABLE이라 그대로 전달하고 되돌린다(#592)
        jdbc.update("UPDATE product SET limits=jsonb_set(limits,'{dailyMemoryExplanations}','5') WHERE id=?", free)
        call(explanations, explanationBody).andExpect(status().isServiceUnavailable()).andExpect(jsonPath("$.code").value("AI_UNAVAILABLE"))
        assertEquals(1, used("EXPLANATION"))

        // 설명 생성 실패(FAILED)는 200이라 센다
        stub.respond = { LearningHttpStub.Reply(body = "{\"state\":\"FAILED\",\"text\":null,\"citations\":[]}") }
        call(explanations, explanationBody).andExpect(status().isOk()).andExpect(jsonPath("$.state").value("FAILED"))
        assertEquals(2, used("EXPLANATION"))
    }

    @Test fun `memory circuit is separate from the general learning circuit and open circuit releases usage`() {
        assertEquals("learning-memory", memory.circuit.name)
        assertEquals("learning-json", general.circuit.name)
        jdbc.update("UPDATE product SET limits=jsonb_set(limits,'{dailyMemorySearches}','50') WHERE id=?", free)
        stub.respond = { LearningHttpStub.Reply(503, "{\"status\":503,\"code\":\"AI_UNAVAILABLE\"}", problem) }
        repeat(20) { call(search, "{\"query\":\"고양이\"}").andExpect(status().isServiceUnavailable()) }
        assertEquals(CircuitBreaker.State.OPEN, memory.circuit.state)
        assertEquals(CircuitBreaker.State.CLOSED, general.circuit.state)

        // 열린 서킷은 learning을 부르지 않고 503, 사용량도 남기지 않는다. 설명도 같은 서킷
        call(search, "{\"query\":\"고양이\"}").andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.code").value("LEARNING_CIRCUIT_OPEN")).andExpect(header().string("Retry-After", "30"))
        call(explanations, explanationBody).andExpect(status().isServiceUnavailable()).andExpect(jsonPath("$.code").value("LEARNING_CIRCUIT_OPEN"))
        assertEquals(20, stub.requests.size); assertEquals(0, used("SEARCH")); assertEquals(0, used("EXPLANATION"))

        // 일반 learning 경로는 그대로 열려 있다
        stub.respond = { LearningHttpStub.Reply(body = "{\"themeId\":\"${UUID.randomUUID()}\",\"days\":[]}") }
        mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get("/api/v1/students/me/weekly-theme")
            .header("Authorization", "Bearer $access")).andExpect(status().isOk())
    }

    @Test fun `invalid bodies are rejected before usage and learning`() {
        listOf("{}", "[]", "{\"query\":\"\"}", "{\"query\":\"   \"}", "{\"query\":1}", "{\"query\":\"${"가".repeat(201)}\"}",
            "{\"query\":\"고양이\",\"studentId\":\"${UUID.randomUUID()}\"}", "not-json")
            .forEach { call(search, it).andExpect(status().isBadRequest()).andExpect(jsonPath("$.code").value("VALIDATION_FAILED")) }
        val id = UUID.randomUUID()
        listOf("{\"query\":\"고양이\"}", "{\"query\":\"고양이\",\"attemptIds\":[]}", "{\"query\":\"고양이\",\"attemptIds\":\"$id\"}",
            "{\"query\":\"고양이\",\"attemptIds\":[\"$id\",\"$id\"]}", "{\"query\":\"고양이\",\"attemptIds\":[\"not-uuid\"]}",
            "{\"query\":\"고양이\",\"attemptIds\":[\"${UUID.randomUUID()}\",\"${UUID.randomUUID()}\",\"${UUID.randomUUID()}\",\"${UUID.randomUUID()}\"]}")
            .forEach { call(explanations, it).andExpect(status().isBadRequest()).andExpect(jsonPath("$.code").value("VALIDATION_FAILED")) }
        // 200자 경계는 허용
        stub.respond = { LearningHttpStub.Reply(body = "{\"state\":\"NO_RECORDS\",\"cards\":[]}") }
        call(search, "{\"query\":\"${"가".repeat(200)}\"}").andExpect(status().isOk())
        assertEquals(1, stub.requests.size); assertEquals(1, used("SEARCH"))
    }

    @Test fun `subscription snapshot without memory limits falls back to the free product value`() {
        val premium = UUID.randomUUID()
        val limits = """{"dailyMissions":3,"dailyFeedback":50,"dailyConversations":30,"reportNarrative":true}"""
        product(premium, 14900, limits)
        val snapshot = json.writeValueAsString(mapOf("id" to premium, "code" to "synthetic-$premium", "name" to "합성 상품", "price" to 14900,
            "billingCycle" to "MONTHLY", "childLimit" to 1, "features" to emptyMap<String, Any>(), "limits" to json.readTree(limits), "active" to true))
        jdbc.update("""INSERT INTO subscription(id,parent_user_id,student_id,product_id,status,period_start,period_end,
            next_billing_date,auto_renew,renewal_retry_count,created_at,updated_at,product_snapshot,billing_anchor_day,revision)
            VALUES(?,?,?,?,'ACTIVE',DATE '2026-11-01',DATE '2026-12-01',NULL,false,0,now(),now(),?::jsonb,1,0)""",
            UUID.randomUUID(), user, child, premium, snapshot)
        stub.respond = { LearningHttpStub.Reply(body = "{\"state\":\"NO_RESULTS\",\"cards\":[]}") }
        repeat(2) { call(search, "{\"query\":\"고양이\"}").andExpect(status().isOk()) }
        call(search, "{\"query\":\"고양이\"}").andExpect(status().isTooManyRequests())

        // 무료 상품에도 값이 없으면 상품 오류 503, learning·사용량 없음
        jdbc.update("UPDATE product SET limits=limits-'dailyMemoryExplanations' WHERE id=?", free)
        call(explanations, explanationBody).andExpect(status().isServiceUnavailable()).andExpect(jsonPath("$.code").value("PAYMENT_PRODUCT_UNAVAILABLE"))
        assertEquals(2, stub.requests.size); assertEquals(0, used("EXPLANATION"))
    }
}
