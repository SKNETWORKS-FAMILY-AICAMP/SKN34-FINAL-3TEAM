package com.sagomungchi.core.usage.consumer

import com.rabbitmq.client.Channel
import com.sagomungchi.core._common.messaging.EventEnvelope
import com.sagomungchi.core._common.messaging.RetryingConsumer
import com.sagomungchi.core.usage.domain.LlmUsageRecorded
import com.sagomungchi.core.usage.service.LlmUsageService
import org.springframework.amqp.core.Message
import org.springframework.amqp.rabbit.annotation.RabbitListener
import org.springframework.stereotype.Component

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
