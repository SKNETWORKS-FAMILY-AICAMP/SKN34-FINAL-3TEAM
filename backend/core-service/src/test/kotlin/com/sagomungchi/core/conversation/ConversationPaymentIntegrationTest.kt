package com.sagomungchi.core.conversation

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core._common.messaging.OutboxRelay
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.admin.session
import com.sagomungchi.core.report.parent
import com.sagomungchi.core.report.child
import com.sagomungchi.core.conversation.repository.ConversationRepository
import com.sagomungchi.core.conversation.service.AnalysisEntitlementProvider
import com.sagomungchi.core.payment.client.TossGateway
import com.sagomungchi.core.payment.domain.Product
import com.sagomungchi.core.payment.scheduler.PaymentScheduler
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.AfterAll
import org.mockito.Mockito.verifyNoInteractions
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.boot.test.web.server.LocalServerPort
import org.springframework.data.redis.core.StringRedisTemplate
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.LocalDate
import java.time.ZoneId
import java.util.UUID
import kotlin.test.*

/** Real payment provider, product/subscription DB, Redis, JWT and core HTTP; only AI and PG boundaries are doubles. */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = [
    "spring.rabbitmq.listener.simple.auto-startup=false", "spring.datasource.hikari.maximum-pool-size=5", "spring.datasource.hikari.minimum-idle=0"])
class ConversationPaymentIntegrationTest : IntegrationTestSupport() {
    @LocalServerPort var port: Int = 0
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var repository: ConversationRepository
    @Autowired lateinit var provider: AnalysisEntitlementProvider
    @Autowired lateinit var redis: StringRedisTemplate
    @MockitoBean lateinit var pg: TossGateway
    @MockitoBean lateinit var scheduler: PaymentScheduler
    @MockitoBean lateinit var outbox: OutboxRelay
    private lateinit var owner: UUID
    private lateinit var student: UUID
    private lateinit var bearer: String
    private lateinit var premium: Product
    private val today get() = LocalDate.now(ZoneId.of("Asia/Seoul"))
    companion object {
        private val free = UUID.randomUUID()
        private val ai = AnalysisHttpStub()
        @JvmStatic @DynamicPropertySource fun properties(registry: DynamicPropertyRegistry) {
            registry.add("app.payment.free-product-id") { free.toString() }
            registry.add("app.services.ai") { ai.url }
        }
        @JvmStatic @AfterAll fun closeAi() { ai.close() }
    }
    @BeforeEach fun setup() {
        owner = parent(jdbc); student = child(jdbc, owner)
        bearer = tokens.access(session(jdbc, owner, "PARENT"))
        product(free, false); premium = product(UUID.randomUUID(), true)
        ai.requests.clear()
        ai.respond = { exchange, request ->
            val scope = json.readTree(request.body).path("scope")
            exchange.event("status", """{"state":"RUNNING","message":"합성 조회"}""")
            exchange.event("result", json.writeValueAsString(mapOf("answer" to "합성 확정 답변", "source" to "LLM",
                "scope" to scope, "metrics" to emptyList<Any>(), "evidence" to emptyList<Any>(), "recordCount" to 1,
                "verification" to mapOf("numbersMatched" to true, "quotesMatched" to true, "contentAllowed" to true))))
            exchange.event("done", "{}")
        }
    }
    @AfterEach fun noPgCalls() { verifyNoInteractions(pg) }
    private fun product(id: UUID, paid: Boolean): Product {
        val limits = json.readTree("""{"dailyMissions":3,"dailyFeedback":50,"dailyConversations":${if(paid) 2 else 0},"reportNarrative":$paid}""")
        val row = Product(id, "analysis-fixture-$id", "합성 상품", if(paid) 14900 else 0, "MONTHLY", 1, json.createObjectNode(), limits, true)
        jdbc.update("""INSERT INTO product(id,code,name,price,billing_cycle,child_limit,features,limits,active,created_at)
            VALUES(?,?,?,?,'MONTHLY',1,'{}',?::jsonb,true,now()) ON CONFLICT(id) DO NOTHING""",
            row.id,row.code,row.name,row.price,json.writeValueAsString(limits))
        return row
    }
    private fun subscribe(): UUID {
        val id = UUID.randomUUID(); val start = today.minusDays(10); val end = today.plusDays(10)
        // Synthetic approved subscription fixture; no PG approval or real billing credentials are used.
        jdbc.update("""INSERT INTO subscription(id,parent_user_id,student_id,product_id,status,period_start,period_end,
            next_billing_date,auto_renew,renewal_retry_count,created_at,updated_at,product_snapshot,billing_anchor_day,revision)
            VALUES(?,?,?,?,'ACTIVE',?,?,NULL,false,0,now(),now(),?::jsonb,?,0)""",
            id,owner,student,premium.id,start,end,json.writeValueAsString(premium),start.dayOfMonth)
        return id
    }
    private fun call(path: String, body: Any): HttpResponse<String> {
        val request = HttpRequest.newBuilder(URI("http://127.0.0.1:$port/api/v1$path"))
            .header("Authorization", "Bearer $bearer").header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(json.writeValueAsString(body))).build()
        return HttpClient.newHttpClient().use { it.send(request, HttpResponse.BodyHandlers.ofString()) }
    }
    private fun create(): UUID {
        val response = call("/conversations", mapOf("childId" to student))
        assertEquals(201,response.statusCode(),response.body())
        return UUID.fromString(json.readTree(response.body()).path("conversationId").asText())
    }
    private fun uses() = jdbc.queryForObject("SELECT count(*) FROM payment_premium_usage WHERE student_id=? AND kind='CONVERSATION' AND status='USED'",Int::class.java,student)
    @Test fun `actual free product blocks core creation without AI counter or premium ledger`() {
        assertEquals(free,provider.entitlement(owner,student).productId)
        val response = call("/conversations",mapOf("childId" to student))
        assertEquals(429,response.statusCode());assertEquals("USAGE_LIMIT_REACHED",json.readTree(response.body()).path("code").asText())
        assertTrue(ai.requests.isEmpty());assertEquals(0,uses())
        assertNull(redis.opsForValue().get("analysis:daily:v1:$student:$today"))
    }
    @Test fun `unavailable configured free product is an explicit error without fake premium access`() {
        jdbc.update("UPDATE product SET active=false WHERE id=?",free)
        try {
            val response=call("/conversations",mapOf("childId" to student))
            assertEquals(503,response.statusCode());assertEquals("PAYMENT_FREE_PRODUCT_UNAVAILABLE",json.readTree(response.body()).path("code").asText())
            assertTrue(ai.requests.isEmpty());assertEquals(0,uses())
        } finally { jdbc.update("UPDATE product SET active=true WHERE id=?",free) }
    }
    @Test fun `real provider joins admission transaction and records failed attempts while Redis rejects excess retry`() {
        subscribe();assertEquals(premium.id,provider.entitlement(owner,student).productId)
        val id=create()
        val success=call("/conversations/$id/messages",mapOf("question" to "합성 질문"))
        assertEquals(200,success.statusCode());assertTrue(success.body().contains("event:result"),success.body())
        assertEquals("COMPLETED",repository.messages(id).single().status);assertEquals(1,uses())
        ai.respond={exchange,_->exchange.event("error","""{"code":"AI_UNAVAILABLE","message":"합성 오류","retryable":true}""")}
        val failure=call("/conversations/$id/messages",mapOf("question" to "실패 시도"))
        assertEquals(200,failure.statusCode());val failed=repository.messages(id).last();assertEquals("FAILED",failed.status);assertEquals(2,uses())
        val blocked=call("/conversations/$id/messages/${failed.id}/retry",emptyMap<String,String>())
        assertEquals(429,blocked.statusCode());assertEquals("USAGE_LIMIT_REACHED",json.readTree(blocked.body()).path("code").asText())
        assertEquals(2,uses());assertEquals(0,repository.messages(id).last().retryCount)
        assertEquals("2",redis.opsForValue().get("analysis:daily:v1:$student:$today"));assertEquals(2,ai.requests.size)
    }
    @Test fun `provider supplies KST nine oclock expiry and grace while expired subscription falls back to configured free product`() {
        val sub=subscribe()
        assertEquals(today.plusDays(10).atTime(9,0).atZone(ZoneId.of("Asia/Seoul")).toInstant(),provider.entitlement(owner,student).validUntil)
        create() // autoRenew=false keeps access until periodEnd.
        val grace=today.plusDays(1)
        jdbc.update("UPDATE subscription SET status='RENEWAL_FAILED',period_end=?,grace_until=?,updated_at=now() WHERE id=?",today.minusDays(1),grace,sub)
        val current=provider.entitlement(owner,student);assertTrue(current.conversationEnabled)
        assertEquals(grace.atTime(9,0).atZone(ZoneId.of("Asia/Seoul")).toInstant(),current.validUntil);create()
        jdbc.update("UPDATE subscription SET grace_until=?,updated_at=now() WHERE id=?",today.minusDays(1),sub)
        assertEquals(free,provider.entitlement(owner,student).productId)
        val expired=call("/conversations",mapOf("childId" to student));assertEquals(429,expired.statusCode());assertEquals(0,uses())
    }
}
