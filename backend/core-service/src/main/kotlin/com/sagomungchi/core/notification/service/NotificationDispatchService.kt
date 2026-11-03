package com.sagomungchi.core.notification.service

import com.sagomungchi.core.notification.domain.NotificationStored
import com.sagomungchi.core.notification.messaging.NotificationRedisPublisher
import org.slf4j.LoggerFactory
import org.springframework.stereotype.Service
import org.springframework.transaction.event.TransactionPhase
import org.springframework.transaction.event.TransactionalEventListener

/** After commit (and admin retry outside a transaction): publish to Redis, then record COMPLETED/FAILED (#250). */
@Service
class NotificationDispatchService(private val publisher: NotificationRedisPublisher, private val delivery: NotificationDeliveryService) {
    private val log = LoggerFactory.getLogger(javaClass)
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    fun dispatch(value: NotificationStored) {
        val failed = !publisher.publish(value)
        try { delivery.record(value.id, failed) }
        catch (ex: Exception) {
            // The original commit cannot be rolled back. Never turn a post-commit bookkeeping error into a report retry.
            log.error("Notification {} publication outcome could not be recorded (failed={}); row remains reconcilable", value.id, failed, ex)
        }
    }
}
