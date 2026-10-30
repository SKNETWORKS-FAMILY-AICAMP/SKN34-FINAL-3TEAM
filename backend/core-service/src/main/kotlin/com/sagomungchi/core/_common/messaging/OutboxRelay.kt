package com.sagomungchi.core._common.messaging

import net.javacrumbs.shedlock.core.LockAssert
import net.javacrumbs.shedlock.spring.annotation.SchedulerLock
import org.springframework.amqp.core.Message
import org.springframework.amqp.core.MessageProperties
import org.springframework.amqp.rabbit.core.RabbitTemplate
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component
import org.springframework.transaction.support.TransactionTemplate
import java.time.OffsetDateTime

/**
 * 미발행 outbox_event를 발행하고 publisher confirm 후 published_at 기록.
 * 레플리카 간 단일 실행은 ShedLock이 보장, 발행·confirm 대기는 DB 트랜잭션 밖, 기록만 짧은 트랜잭션 (아키텍처 2.2).
 * 발행 후 기록 전 장애 시 재발행될 수 있으므로 소비자는 멱등 처리 (아키텍처 1.6).
 */
@Component
class OutboxRelay(
    private val repository: OutboxEventRepository,
    private val rabbitTemplate: RabbitTemplate,
    private val transactionTemplate: TransactionTemplate,
) {
    @Scheduled(fixedDelayString = "\${app.messaging.outbox-relay-interval}")
    @SchedulerLock(name = "core-outbox-relay", lockAtMostFor = "PT1M")
    fun relay() {
        LockAssert.assertLocked()
        val events = repository.findUnpublished(BATCH_SIZE)
        if (events.isEmpty()) return
        rabbitTemplate.invoke { ops ->
            events.forEach { ops.send(exchangeOf(it.eventType), it.routingKey, toMessage(it)) }
            ops.waitForConfirmsOrDie(MessagingConfig.CONFIRM_TIMEOUT_MS)
        }
        val publishedAt = OffsetDateTime.now()
        transactionTemplate.executeWithoutResult { events.forEach { repository.markPublished(it.id, publishedAt) } }
    }

    private fun toMessage(event: OutboxEvent): Message {
        val properties = MessageProperties().apply {
            contentType = MessageProperties.CONTENT_TYPE_JSON
            contentEncoding = Charsets.UTF_8.name()
            messageId = event.id.toString()
        }
        return Message(event.payload.toByteArray(Charsets.UTF_8), properties)
    }

    companion object {
        private const val BATCH_SIZE = 100

        /** 명령은 cmd.direct, 나머지 이벤트는 events.topic (아키텍처 1.4) */
        private val COMMAND_TYPES = setOf("report.generate")

        private fun exchangeOf(eventType: String) =
            if (eventType in COMMAND_TYPES) MessagingConfig.COMMAND_EXCHANGE else MessagingConfig.EVENTS_EXCHANGE
    }
}
