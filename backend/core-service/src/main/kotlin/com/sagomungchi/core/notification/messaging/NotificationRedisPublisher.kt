package com.sagomungchi.core.notification.messaging

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.notification.config.NotificationRedisConfiguration
import com.sagomungchi.core.notification.domain.NotificationStored
import com.sagomungchi.core.notification.service.NotificationDeliveryService
import org.slf4j.LoggerFactory
import org.springframework.data.redis.core.StringRedisTemplate
import org.springframework.stereotype.Component
import org.springframework.transaction.event.TransactionPhase
import org.springframework.transaction.event.TransactionalEventListener

@Component
class NotificationRedisPublisher(private val redis: StringRedisTemplate, private val json: ObjectMapper,
    private val delivery: NotificationDeliveryService) {
    private val log = LoggerFactory.getLogger(javaClass)
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    fun publish(value: NotificationStored) {
        val failed = try {
            redis.convertAndSend(NotificationRedisConfiguration.CHANNEL, json.writeValueAsString(value))
            false // Redis acknowledgement only; zero subscribers is not a client receipt.
        } catch (ex: Exception) {
            log.error("Notification {} committed but Redis publication failed", value.id, ex)
            true
        }
        try { delivery.record(value.id, failed) }
        catch (ex: Exception) {
            // The original commit cannot be rolled back. Never turn a post-commit bookkeeping error into a report retry.
            log.error("Notification {} publication outcome could not be recorded (failed={}); row remains reconcilable", value.id, failed, ex)
        }
    }
}
