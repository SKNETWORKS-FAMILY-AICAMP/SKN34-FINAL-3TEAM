package com.sagomungchi.core.notification.messaging

import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.data.redis.connection.RedisConnectionFactory
import org.springframework.data.redis.listener.ChannelTopic
import org.springframework.data.redis.listener.RedisMessageListenerContainer

@Configuration
class NotificationRedisConfiguration {
    @Bean
    fun notificationListenerContainer(factory: RedisConnectionFactory, listener: NotificationRedisSubscriber) =
        RedisMessageListenerContainer().apply {
            setConnectionFactory(factory)
            addMessageListener(listener, ChannelTopic(CHANNEL))
        }
    companion object { const val CHANNEL = "core:notifications:v1" }
}
