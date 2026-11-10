package com.sagomungchi.core.admin.consumer

import com.rabbitmq.client.Channel
import com.sagomungchi.core._common.messaging.EventEnvelope
import com.sagomungchi.core._common.messaging.RetryingConsumer
import com.sagomungchi.core.admin.domain.ModelLoadingReport
import com.sagomungchi.core.admin.service.ModelLoadingService
import org.springframework.amqp.core.Message
import org.springframework.amqp.rabbit.annotation.RabbitListener
import org.springframework.stereotype.Component

@Component
class ModelLoadingConsumer(private val retrying: RetryingConsumer, private val service: ModelLoadingService) {
    @RabbitListener(queues = [QUEUE])
    fun receive(event: EventEnvelope<ModelLoadingReport>, message: Message, channel: Channel) {
        retrying.handle(message, channel, QUEUE) { service.record(event) }
    }
    companion object { const val QUEUE = "core.model.loading.reported" }
}
