package com.sagomungchi.core.notification.messaging

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.notification.config.NotificationRedisConfiguration
import com.sagomungchi.core.notification.domain.NotificationStored
import org.slf4j.LoggerFactory
import org.springframework.data.redis.core.StringRedisTemplate
import org.springframework.stereotype.Component

/** Redis publication only. Post-commit trigger and outcome recording live in NotificationDispatchService (#250). */
@Component
class NotificationRedisPublisher(private val redis: StringRedisTemplate, private val json: ObjectMapper) {
    private val log = LoggerFactory.getLogger(javaClass)
    /** true when Redis accepted the message */
    fun publish(value: NotificationStored): Boolean = try {
        redis.convertAndSend(NotificationRedisConfiguration.CHANNEL, json.writeValueAsString(value))
        true // Redis acknowledgement only; zero subscribers is not a client receipt.
    } catch (ex: Exception) {
        log.error("Notification {} committed but Redis publication failed", value.id, ex)
        false
    }
}
