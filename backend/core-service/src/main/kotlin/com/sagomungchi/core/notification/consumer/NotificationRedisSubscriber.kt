package com.sagomungchi.core.notification.consumer

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.notification.domain.NotificationStored
import com.sagomungchi.core.notification.service.NotificationStreams
import org.slf4j.LoggerFactory
import org.springframework.data.redis.connection.Message
import org.springframework.data.redis.connection.MessageListener
import org.springframework.stereotype.Component

@Component
class NotificationRedisSubscriber(private val json: ObjectMapper, private val streams: NotificationStreams) : MessageListener {
    private val log = LoggerFactory.getLogger(javaClass)
    override fun onMessage(message: Message, pattern: ByteArray?) {
        try {
            val value = json.readValue(message.body, NotificationStored::class.java)
            streams.deliver(value.userId, value.id)
        } catch (ex: Exception) {
            log.error("Notification subscription delivery failed; clients must reconcile through list API", ex)
        }
    }
}
