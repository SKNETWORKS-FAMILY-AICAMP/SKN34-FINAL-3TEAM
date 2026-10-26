package com.sagomungchi.core._common.messaging

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import org.junit.jupiter.api.Test
import org.springframework.amqp.core.Message
import org.springframework.amqp.core.MessageProperties
import org.springframework.amqp.rabbit.core.RabbitTemplate
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.TestPropertySource
import org.springframework.transaction.support.TransactionTemplate
import java.math.BigDecimal
import java.nio.file.Path
import java.time.Duration
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.test.fail

/** 메시징 기반 검증: 단가 3·15 USD/100만 토큰, 재시도 대기는 IntegrationTestSupport에서 1초로 단축 */
@TestPropertySource(
    properties = [
        "app.llm-pricing.test-model.input=3",
        "app.llm-pricing.test-model.output=15",
    ],
)
class MessagingIntegrationTest(
    @Autowired private val rabbitTemplate: RabbitTemplate,
    @Autowired private val jdbcTemplate: JdbcTemplate,
    @Autowired private val objectMapper: ObjectMapper,
    @Autowired private val outboxWriter: OutboxWriter,
    @Autowired private val processedEventRepository: ProcessedEventRepository,
    @Autowired private val transactionTemplate: TransactionTemplate,
) : IntegrationTestSupport() {
    @Test
    fun `llm usage 이벤트는 비용 계산 후 저장, 같은 id 재전달은 1행 유지`() {
        val envelope = usageEnvelope(UUID.randomUUID())
        repeat(2) { publish(MessagingConfig.EVENTS_EXCHANGE, USAGE_ROUTING_KEY, objectMapper.writeValueAsBytes(envelope)) }

        val eventId = UUID.fromString(envelope.id)
        val cost = await { jdbcTemplate.queryForList("SELECT cost_usd FROM llm_usage WHERE event_id = ?", BigDecimal::class.java, eventId).firstOrNull() }
        Thread.sleep(1_000)

        assertEquals(0, BigDecimal("0.033").compareTo(cost))
        assertEquals(1, countUsage(eventId))
    }

    @Test
    fun `처리 실패 메시지는 재시도 큐를 거쳐 최대 횟수 초과 후 DLQ로 이동`() {
        // call_type CHECK 제약 위반 → 저장 실패
        val envelope = usageEnvelope(UUID.randomUUID(), usageData() + ("callType" to "UNKNOWN"))
        publish(MessagingConfig.EVENTS_EXCHANGE, USAGE_ROUTING_KEY, objectMapper.writeValueAsBytes(envelope))

        // <큐>.retry.1~3 경유 후 max-retries=3 초과
        val dead = receiveDead(Duration.ofSeconds(30)) { objectMapper.readTree(it.body)["id"]?.asText() == envelope.id }

        assertEquals(3, (dead.messageProperties.headers[RetryingConsumer.RETRY_COUNT_HEADER] as Number).toInt())
    }

    @Test
    fun `형식 오류 메시지는 재시도 없이 DLQ로 이동`() {
        val body = "not-json-${UUID.randomUUID()}"
        publish("", USAGE_QUEUE, body.toByteArray())

        val dead = receiveDead(Duration.ofSeconds(10)) { String(it.body) == body }

        assertNull(dead.messageProperties.headers[RetryingConsumer.RETRY_COUNT_HEADER])
    }

    @Test
    fun `outbox 행은 계약 형식 봉투로 발행 후 published_at 기록`() {
        val subject = "outbox-${UUID.randomUUID()}"
        transactionTemplate.executeWithoutResult {
            outboxWriter.append(USAGE_ROUTING_KEY, USAGE_ROUTING_KEY, subject, usageData())
        }

        val eventId = jdbcTemplate.queryForObject("SELECT id FROM outbox_event WHERE subject = ?", UUID::class.java, subject)!!
        // Python 소비자(report EventConsumer)가 읽는 봉투 형식: 계약 필수 키, 오프셋 포함 ISO 시각
        val payload = objectMapper.readTree(
            jdbcTemplate.queryForObject("SELECT payload::text FROM outbox_event WHERE id = ?", String::class.java, eventId),
        )
        val required = objectMapper.readTree(ENVELOPE_SCHEMA.toFile())["required"].map { it.asText() }
        assertTrue(required.all { payload.has(it) }, "필수 키 누락: $payload")
        assertTrue(payload["time"].isTextual && OFFSET_DATE_TIME.matches(payload["time"].asText()), "time 형식: ${payload["time"]}")
        assertEquals("$USAGE_ROUTING_KEY.v1", payload["dataschema"].asText())
        await { jdbcTemplate.queryForObject("SELECT published_at FROM outbox_event WHERE id = ?", Any::class.java, eventId) }
        await { countUsage(eventId).takeIf { it == 1 } }
    }

    @Test
    fun `processed_event는 첫 기록만 true`() {
        val eventId = UUID.randomUUID()

        assertTrue(processedEventRepository.markProcessed(eventId, USAGE_ROUTING_KEY))
        assertFalse(processedEventRepository.markProcessed(eventId, USAGE_ROUTING_KEY))
    }

    private fun usageData() = mapOf(
        "service" to "ai",
        "callType" to "JUDGMENT",
        "model" to "test-model",
        "promptVersion" to "judgment-v1",
        "inputTokens" to 1_000,
        "outputTokens" to 2_000,
        "latencyMs" to 1_200,
        "success" to true,
        "errorCode" to null,
        "occurredAt" to "2026-10-26T09:00:00+09:00",
    )

    private fun usageEnvelope(id: UUID, data: Map<String, Any?> = usageData()) = EventEnvelope(
        id = id.toString(),
        type = USAGE_ROUTING_KEY,
        source = "ai-service",
        dataschema = "$USAGE_ROUTING_KEY.v1",
        data = data,
    )

    private fun publish(exchange: String, routingKey: String, body: ByteArray) {
        val properties = MessageProperties().apply { contentType = MessageProperties.CONTENT_TYPE_JSON }
        rabbitTemplate.send(exchange, routingKey, Message(body, properties))
    }

    /** 다른 테스트의 DLQ 메시지는 건너뜀 */
    private fun receiveDead(timeout: Duration, matches: (Message) -> Boolean): Message =
        await(timeout) { rabbitTemplate.receive("$USAGE_QUEUE.dlq", 500)?.takeIf(matches) }

    private fun countUsage(eventId: UUID): Int =
        jdbcTemplate.queryForObject("SELECT count(*) FROM llm_usage WHERE event_id = ?", Int::class.java, eventId)!!

    private fun <T : Any> await(timeout: Duration = Duration.ofSeconds(15), supplier: () -> T?): T {
        val deadline = System.nanoTime() + timeout.toNanos()
        while (System.nanoTime() < deadline) {
            supplier()?.let { return it }
            Thread.sleep(200)
        }
        fail("$timeout 안에 조건 미충족")
    }

    companion object {
        private const val USAGE_ROUTING_KEY = "llm.usage.recorded"
        private const val USAGE_QUEUE = "core.llm.usage.recorded"
        private val ENVELOPE_SCHEMA = Path.of("../../contracts/events/envelope.schema.json")
        private val OFFSET_DATE_TIME = Regex("""\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})""")
    }
}
