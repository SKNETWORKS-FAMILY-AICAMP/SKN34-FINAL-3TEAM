package com.sagomungchi.core._common.messaging

import com.fasterxml.jackson.databind.JsonNode
import com.rabbitmq.client.Channel
import org.springframework.amqp.core.Message
import org.springframework.amqp.rabbit.annotation.RabbitListener
import org.springframework.stereotype.Component
import java.time.OffsetDateTime
import java.util.UUID

/**
 * events.topic 전체와 report.generate 사본을 받아 event_log에 기록 (아키텍처 1.6 이벤트 기록).
 * 업무 소비 큐와 분리된 감사 큐라 업무 처리에 영향 없음. 봉투 형식 오류는 컨테이너가 DLQ로 보냄.
 */
@Component
class EventAuditConsumer(
    private val retryingConsumer: RetryingConsumer,
    private val repository: EventLogRepository,
) {
    @RabbitListener(queues = [QUEUE])
    fun onEvent(envelope: EventEnvelope<JsonNode>, message: Message, channel: Channel) {
        retryingConsumer.handle(message, channel, QUEUE) {
            repository.insertIfAbsent(
                UUID.fromString(envelope.id), envelope.type, envelope.source, envelope.subject,
                envelope.time, OffsetDateTime.now(),
            )
        }
    }

    companion object {
        const val QUEUE = "core.event.audit"
    }
}
