package com.sagomungchi.core.usage.consumer

import com.rabbitmq.client.Channel
import com.sagomungchi.core._common.messaging.EventEnvelope
import com.sagomungchi.core._common.messaging.RetryingConsumer
import com.sagomungchi.core.usage.service.LlmUsageService
import org.springframework.amqp.core.Message
import org.springframework.amqp.rabbit.annotation.RabbitListener
import org.springframework.stereotype.Component
import java.time.OffsetDateTime

/** contracts/events/llm.usage.recorded.v1.schema.json */
data class LlmUsageRecorded(
    val service: String,
    val callType: String,
    val model: String,
    val promptVersion: String?,
    val inputTokens: Int?,
    val outputTokens: Int?,
    val latencyMs: Int,
    val success: Boolean,
    val errorCode: String?,
    val occurredAt: OffsetDateTime,
)

@Component
class LlmUsageConsumer(
    private val retryingConsumer: RetryingConsumer,
    private val llmUsageService: LlmUsageService,
) {
    @RabbitListener(queues = [QUEUE])
    fun onUsage(envelope: EventEnvelope<LlmUsageRecorded>, message: Message, channel: Channel) {
        retryingConsumer.handle(message, channel, QUEUE) { llmUsageService.record(envelope) }
    }

    companion object {
        const val QUEUE = "core.llm.usage.recorded"
    }
}
