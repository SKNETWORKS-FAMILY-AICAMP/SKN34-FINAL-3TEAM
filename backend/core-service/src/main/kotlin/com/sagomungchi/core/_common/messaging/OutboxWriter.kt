package com.sagomungchi.core._common.messaging

import com.fasterxml.jackson.databind.ObjectMapper
import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Component
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.util.UUID

/** 상태 변경과 같은 트랜잭션에 outbox_event 저장. 발행은 OutboxRelay (아키텍처 1.6) */
@Component
class OutboxWriter(
    private val repository: OutboxEventRepository,
    private val objectMapper: ObjectMapper,
    @Value("\${spring.application.name}") private val source: String,
) {
    @Transactional(propagation = Propagation.MANDATORY)
    fun append(type: String, routingKey: String, subject: String, data: Any) {
        val envelope = EventEnvelope(type = type, source = source, subject = subject, dataschema = "$type.v1", data = data)
        repository.insert(
            OutboxEvent(
                id = UUID.fromString(envelope.id),
                eventType = type,
                routingKey = routingKey,
                subject = subject,
                payload = objectMapper.writeValueAsString(envelope),
                createdAt = envelope.time,
            ),
        )
    }
}
