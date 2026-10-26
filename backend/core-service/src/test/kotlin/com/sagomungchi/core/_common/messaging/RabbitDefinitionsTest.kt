package com.sagomungchi.core._common.messaging

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.config.AppProperties
import org.junit.jupiter.api.Test
import java.nio.file.Path
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/**
 * RetryingConsumer는 기본 exchange로 <큐>.retry.<회차>에 재발행하므로 큐가 없으면 메시지가 조용히 유실됨.
 * definitions.json이 재시도 단계(1·5·15분, P12)·DLQ를 모든 소비 큐에 갖추는지 확인.
 */
class RabbitDefinitionsTest {
    private val queues: Map<String, JsonNode> =
        ObjectMapper().readTree(DEFINITIONS.toFile())["queues"].associateBy { it["name"].asText() }

    @Test
    fun `모든 소비 큐에 재시도 단계 큐와 DLQ가 있음`() {
        val consumerQueues = queues.keys.filterNot { it.endsWith(".dlq") || it.contains(".retry.") }
        assertTrue(consumerQueues.isNotEmpty())

        consumerQueues.forEach { queue ->
            assertNotNull(queues["$queue.dlq"], "$queue.dlq 없음")
            RETRY_DELAYS_MS.forEachIndexed { index, delay ->
                val retry = assertNotNull(queues["$queue.retry.${index + 1}"], "$queue.retry.${index + 1} 없음")["arguments"]
                assertEquals(delay, retry["x-message-ttl"].asLong(), "$queue.retry.${index + 1} 지연")
                assertEquals("", retry["x-dead-letter-exchange"].asText())
                assertEquals(queue, retry["x-dead-letter-routing-key"].asText())
            }
        }
    }

    @Test
    fun `재시도 단계 수는 기본 최대 재시도 횟수와 일치`() {
        val tiers = queues.keys.filter { it.startsWith("core.llm.usage.recorded.retry.") }
        assertEquals(RETRY_DELAYS_MS.size, tiers.size)
        assertEquals(RETRY_DELAYS_MS.size, AppProperties.Messaging().maxRetries)
    }

    companion object {
        private val DEFINITIONS = Path.of("../../infrastructure/gitops/charts/platform-data/files/rabbitmq/definitions.json")
        private val RETRY_DELAYS_MS = listOf(60_000L, 300_000L, 900_000L)
    }
}
